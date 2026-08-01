"""Unit tests for idempotent and fail-loud database preparation."""

import gzip
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.databases.cache import initialise_coordinate_cache
from genome_to_diffraction.databases.common import DatabaseError
from genome_to_diffraction.databases.prepare import (
    DatabasePreparationRequest,
    prepare,
)
from genome_to_diffraction.schemas.io import load_contract


def _request(tmp_path: Path, **updates: object) -> DatabasePreparationRequest:
    values: dict[str, object] = {
        "database_root": tmp_path / "database root",
        "manifest_path": tmp_path / "database manifest.json",
        "initialise_coordinate_cache": True,
        "storage_limit_bytes": 10_000_000,
        "minimum_free_bytes": 0,
        "progress": False,
    }
    values.update(updates)
    return DatabasePreparationRequest(**values)  # type: ignore[arg-type]


def _write_mock_tool(path: Path, name: str) -> None:
    script = f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "${{1-}}" == "--version" ]]; then
  printf '{name} mock-1.0\n'
  exit 0
fi
case "${{1-}}" in
  databases)
    mkdir -p "$(dirname "$3")"
    printf '%s\n' "$2 database" > "$3"
    printf 'index\n' > "$3.index"
    ;;
  createdb)
    mkdir -p "$(dirname "$3")"
    printf 'database\n' > "$3"
    ;;
  createindex)
    printf 'index\n' > "$2.index"
    ;;
  easy-search)
    mkdir -p "$(dirname "$4")"
    printf 'query\ttarget\t0\t100\n' > "$4"
    ;;
  *)
    exit 64
    ;;
esac
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def test_coordinate_cache_initialisation_is_concurrent_safe(tmp_path: Path) -> None:
    root = tmp_path / "coordinate cache"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: initialise_coordinate_cache(root, progress=False), range(2)
            )
        )
    assert results[0] == results[1]
    assert (root / ".cache-layout.json").is_file()
    assert not list(root.rglob("*.partial"))


def test_coordinate_cache_is_reused_and_combined_manifest_validates(
    tmp_path: Path,
) -> None:
    first_request = _request(tmp_path)
    first = prepare(first_request)
    sidecar = Path(first.resources[0].root_path) / ".gtd-resource.json"
    sidecar_before = sidecar.read_text(encoding="utf-8")

    second = prepare(replace(first_request, manifest_path=tmp_path / "second.json"))

    assert first.resources[0].database_id == second.resources[0].database_id
    assert sidecar.read_text(encoding="utf-8") == sidecar_before
    loaded = load_contract(
        tmp_path / "second.json", "database-manifest", progress=False
    )
    assert loaded.model_dump(mode="json")["manifest_id"] == second.manifest_id


def test_verify_only_detects_incomplete_coordinate_cache(tmp_path: Path) -> None:
    request = _request(tmp_path)
    manifest = prepare(request)
    root = Path(manifest.resources[0].root_path)
    (root / "pdb" / "metadata").rmdir()
    verify_request = replace(
        request,
        manifest_path=tmp_path / "verify.json",
        verify_only=True,
    )
    with pytest.raises(DatabaseError, match="directories are missing"):
        prepare(verify_request)


def test_force_rebuild_keeps_content_addressed_coordinate_identity(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    first = prepare(request)
    rebuilt = prepare(
        replace(
            request,
            manifest_path=tmp_path / "rebuilt.json",
            force_rebuild=True,
        )
    )
    assert rebuilt.resources[0].database_id == first.resources[0].database_id


def test_mocked_foldseek_resources_prepare_smoke_and_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "mock bin"
    bin_dir.mkdir()
    _write_mock_tool(bin_dir / "foldseek", "foldseek")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    request = _request(
        tmp_path,
        initialise_coordinate_cache=False,
        prepare_pdb_foldseek=True,
        prepare_prostt5=True,
        storage_limit_bytes=100_000_000,
    )

    first = prepare(request)
    reused = prepare(replace(request, manifest_path=tmp_path / "reused.json"))

    assert {resource.name for resource in first.resources} == {
        "pdb_foldseek",
        "prostt5",
    }
    assert all(resource.smoke_test_status == "passed" for resource in first.resources)
    assert [resource.database_id for resource in first.resources] == [
        resource.database_id for resource in reused.resources
    ]


def test_mocked_pdb_sequence_resource_preserves_target_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "mock bin"
    bin_dir.mkdir()
    _write_mock_tool(bin_dir / "mmseqs", "mmseqs")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    source = tmp_path / "pdb_seqres.txt.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write(">1ubq_A mol:protein length:76 Ubiquitin\n")
        handle.write(
            "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG\n"
        )
    request = _request(
        tmp_path,
        initialise_coordinate_cache=False,
        prepare_pdb_sequences=True,
        pdb_sequence_url=source.as_uri(),
        storage_limit_bytes=100_000_000,
    )

    manifest = prepare(request)

    resource = manifest.resources[0]
    mapping = (Path(resource.root_path) / "target_mapping.tsv").read_text(
        encoding="utf-8"
    )
    assert "1ubq_A\t1UBQ\tA" in mapping
    assert resource.parameters["sequence_count"] == 1


def test_manifest_json_contains_no_temporary_staging_paths(tmp_path: Path) -> None:
    manifest = prepare(_request(tmp_path))
    payload = json.dumps(manifest.model_dump(mode="json"))
    assert ".staging-" not in payload


def test_esm_connectivity_probe_uses_only_public_accession_response(
    tmp_path: Path,
) -> None:
    response = tmp_path / "public_response.json"
    response.write_text('{"sequence":"ACDEFG"}\n', encoding="utf-8")
    manifest = prepare(
        _request(
            tmp_path,
            initialise_coordinate_cache=False,
            verify_esm_atlas_connectivity=True,
            esm_atlas_probe_url=response.as_uri(),
        )
    )
    resource = manifest.resources[0]
    assert resource.name == "esm_atlas_connectivity"
    assert resource.parameters["submitted_user_sequence"] is False
