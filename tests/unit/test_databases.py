"""Unit tests for idempotent and fail-loud database preparation."""

import gzip
import hashlib
import importlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.databases.cache import (
    CachedCoordinate,
    initialise_coordinate_cache,
    publish_pdb_coordinate,
    verify_cached_pdb_coordinate,
)
from genome_to_diffraction.databases.common import (
    DatabaseError,
    inventory_resource,
    verify_inventory,
)
from genome_to_diffraction.databases.prepare import (
    DatabasePreparationRequest,
    prepare,
)
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import DatabaseResource, SmokeTestStatus

prepare_module = importlib.import_module("genome_to_diffraction.databases.prepare")


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
    if [[ "${{FAKE_EMPTY_SEARCH:-0}}" == 1 ]]; then
      : > "$4"
    else
      printf 'ubiquitin_smoke\t%s\t%s\t%s\t%s\t%s\n' \
        "${{FAKE_SEARCH_TARGET:-1ubq_A}}" \
        "${{FAKE_EVALUE:-0}}" \
        "${{FAKE_BITS:-100}}" \
        "${{FAKE_QCOV:-1}}" \
        "${{FAKE_TCOV:-1}}" > "$4"
    fi
    ;;
  *)
    exit 64
    ;;
esac
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def _write_pdb_sequence_source(path: Path) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(">1ubq_A mol:protein length:76 Ubiquitin\n")
        handle.write(
            "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG\n"
        )
        handle.write(">1ubq_B mol:dna length:4 synthetic DNA\nACGT\n")


def _write_pdb_coordinate(path: Path, *, sequence: str | None = None) -> None:
    ubiquitin = sequence or (
        "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"
    )
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(
            "data_1UBQ\n"
            "_entry.id 1UBQ\n"
            "loop_\n"
            "_struct_asym.id\n"
            "_struct_asym.entity_id\n"
            "X 1\n"
            "A 2\n"
            "loop_\n"
            "_entity_poly.entity_id\n"
            "_entity_poly.type\n"
            "_entity_poly.pdbx_strand_id\n"
            "_entity_poly.pdbx_seq_one_letter_code_can\n"
            f"1 'polypeptide(L)' A {ubiquitin}\n"
            "2 polyribonucleotide A ACGU\n"
        )


def _mocked_full_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    coordinate_sequence: str | None = None,
) -> DatabasePreparationRequest:
    bin_dir = tmp_path / "mock bin"
    bin_dir.mkdir()
    _write_mock_tool(bin_dir / "foldseek", "foldseek")
    _write_mock_tool(bin_dir / "mmseqs", "mmseqs")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    sequence_source = tmp_path / "pdb_seqres.txt.gz"
    _write_pdb_sequence_source(sequence_source)
    coordinate_directory = tmp_path / "coordinates"
    coordinate_directory.mkdir()
    _write_pdb_coordinate(
        coordinate_directory / "1ubq.cif.gz", sequence=coordinate_sequence
    )
    return _request(
        tmp_path,
        prepare_pdb_foldseek=True,
        prepare_pdb_sequences=True,
        prepare_prostt5=True,
        pdb_sequence_url=sequence_source.as_uri(),
        pdb_coordinate_url_template=(
            coordinate_directory.as_uri() + "/{pdb_id}.cif.gz"
        ),
        storage_limit_bytes=100_000_000,
    )


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


def test_coordinate_cache_publication_is_atomic_reusable_and_verified(
    tmp_path: Path,
) -> None:
    root = tmp_path / "coordinate cache"
    initialise_coordinate_cache(root, progress=False)
    source = tmp_path / "1ubq.cif.gz"
    _write_pdb_coordinate(source)

    def publish(_: int) -> CachedCoordinate:
        return publish_pdb_coordinate(
            root,
            source,
            pdb_id="1UBQ",
            source_url="https://files.rcsb.org/download/1ubq.cif.gz",
            retrieved_at="2026-08-02T00:00:00Z",
            etag=None,
            last_modified=None,
            content_type="application/gzip",
            progress=False,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        records = list(executor.map(publish, range(2)))
    assert records[0] == records[1]
    record = records[0]
    raw_record = record.as_json()
    verify_cached_pdb_coordinate(root, raw_record, full_checksum=True, progress=False)
    later_record = publish_pdb_coordinate(
        root,
        source,
        pdb_id="1UBQ",
        source_url="https://files.rcsb.org/download/1ubq.cif.gz",
        retrieved_at="2026-08-03T00:00:00Z",
        etag=None,
        last_modified=None,
        content_type="application/gzip",
        progress=False,
    )
    assert later_record.object_sha256 == record.object_sha256
    assert later_record.metadata_relative_path != record.metadata_relative_path
    verify_cached_pdb_coordinate(root, raw_record, full_checksum=True, progress=False)
    assert len(list((root / "pdb" / "metadata" / "1ubq").glob("*.json"))) == 2
    index_path = root / "digest_index" / f"{record.object_sha256}.json"
    index_document = json.loads(index_path.read_text(encoding="utf-8"))
    index_document["size_bytes"] = 1
    index_path.write_text(json.dumps(index_document), encoding="utf-8")
    with pytest.raises(DatabaseError, match="digest index is inconsistent"):
        verify_cached_pdb_coordinate(
            root, raw_record, full_checksum=True, progress=False
        )
    index_document["size_bytes"] = record.size_bytes
    index_path.write_text(json.dumps(index_document), encoding="utf-8")
    object_path = root / str(raw_record["object_relative_path"])
    object_path.write_bytes(b"0" * object_path.stat().st_size)
    with pytest.raises(DatabaseError, match="object checksum mismatch"):
        verify_cached_pdb_coordinate(
            root, raw_record, full_checksum=True, progress=False
        )


def test_inventory_records_internal_symlinks_and_detects_retargeting(
    tmp_path: Path,
) -> None:
    root = tmp_path / "resource"
    root.mkdir()
    (root / "target-a").write_text("a\n", encoding="ascii")
    (root / "target-b").write_text("b\n", encoding="ascii")
    (root / "current").symlink_to("target-a")
    records, digest = inventory_resource(root, progress=False)

    assert (
        next(record for record in records if record.path == "current").kind == "symlink"
    )
    assert verify_inventory(root, digest, full_checksums=True, progress=False) == (3, 4)

    (root / "current").unlink()
    (root / "current").symlink_to("target-b")
    with pytest.raises(DatabaseError, match="symlink target mismatch"):
        verify_inventory(root, digest, full_checksums=True, progress=False)


def test_inventory_rejects_unlisted_and_escaping_paths(tmp_path: Path) -> None:
    root = tmp_path / "resource"
    root.mkdir()
    (root / "listed").write_text("listed\n", encoding="ascii")
    _, digest = inventory_resource(root, progress=False)
    (root / "unexpected").write_text("unexpected\n", encoding="ascii")
    with pytest.raises(DatabaseError, match="path set mismatch"):
        verify_inventory(root, digest, full_checksums=True, progress=False)

    inventory_path = root / ".gtd-inventory.json"
    document = json.loads(inventory_path.read_text(encoding="utf-8"))
    document["files"][0]["path"] = "../outside"
    inventory_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(DatabaseError, match="unsafe resource inventory path"):
        verify_inventory(
            root,
            canonical_digest(document),
            full_checksums=True,
            progress=False,
        )


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
    expected_manifest = request.manifest_path
    verify_request = replace(
        request,
        manifest_path=tmp_path / "verify.json",
        verify_only=True,
        expected_manifest_path=expected_manifest,
        expected_manifest_sha256=hashlib.sha256(
            expected_manifest.read_bytes()
        ).hexdigest(),
    )
    with pytest.raises(DatabaseError, match="directories are missing"):
        prepare(verify_request)


def test_verify_only_requires_and_enforces_external_manifest_anchor(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    prepared = prepare(request)
    with pytest.raises(DatabaseError, match="requires an expected manifest"):
        prepare(
            replace(
                request,
                manifest_path=tmp_path / "unanchored.json",
                verify_only=True,
            )
        )

    expected_path = request.manifest_path
    expected_sha256 = hashlib.sha256(expected_path.read_bytes()).hexdigest()
    verified = prepare(
        replace(
            request,
            manifest_path=tmp_path / "verified.json",
            verify_only=True,
            expected_manifest_path=expected_path,
            expected_manifest_sha256=expected_sha256,
        )
    )
    assert verified.manifest_id == prepared.manifest_id

    sidecar = Path(prepared.resources[0].root_path) / ".gtd-resource.json"
    document = json.loads(sidecar.read_text(encoding="utf-8"))
    document["source"] = "tampered source"
    sidecar.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(DatabaseError, match="differs from expected manifest"):
        prepare(
            replace(
                request,
                manifest_path=tmp_path / "tampered.json",
                verify_only=True,
                expected_manifest_path=expected_path,
                expected_manifest_sha256=expected_sha256,
            )
        )


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
    request = _mocked_full_request(tmp_path, monkeypatch)

    first = prepare(request)
    reused = prepare(replace(request, manifest_path=tmp_path / "reused.json"))

    assert {resource.name for resource in first.resources} == {
        "coordinate_cache",
        "pdb_foldseek",
        "pdb_sequences",
        "prostt5",
    }
    assert all(resource.smoke_test_status == "passed" for resource in first.resources)
    assert [resource.database_id for resource in first.resources] == [
        resource.database_id for resource in reused.resources
    ]
    resources = {resource.name: resource for resource in first.resources}
    pdb_qualification = resources["pdb_foldseek"].parameters["qualification"]
    assert isinstance(pdb_qualification, dict)
    mapping_evidence = pdb_qualification["mapping"]
    coordinate_evidence = pdb_qualification["coordinate_mapping"]
    assert isinstance(mapping_evidence, dict)
    assert isinstance(coordinate_evidence, dict)
    assert mapping_evidence["target_id"] == "1ubq_A"
    assert coordinate_evidence["entry_id"] == "1UBQ"
    assert coordinate_evidence["label_asym_ids"] == ["X"]
    assert coordinate_evidence["resolved_identifier_namespace"] == (
        "auth_asym_id_via_entity_poly.pdbx_strand_id"
    )
    for evidence_name in ("query", "result", "log"):
        evidence = pdb_qualification[evidence_name]
        assert isinstance(evidence, dict)
        evidence_path = evidence["path"]
        assert isinstance(evidence_path, str)
        assert Path(evidence_path).is_file()
    cache_qualification = resources["coordinate_cache"].parameters["qualification"]
    assert isinstance(cache_qualification, dict)
    object_relative_path = cache_qualification["object_relative_path"]
    assert isinstance(object_relative_path, str)
    cached_object = Path(resources["coordinate_cache"].root_path) / object_relative_path
    assert cached_object.is_file()

    expected_sha256 = hashlib.sha256(request.manifest_path.read_bytes()).hexdigest()
    verified = prepare(
        replace(
            request,
            manifest_path=tmp_path / "verified-all.json",
            verify_only=True,
            expected_manifest_path=request.manifest_path,
            expected_manifest_sha256=expected_sha256,
            full_verify=True,
        )
    )
    assert verified.manifest_id == first.manifest_id
    verification_path = (tmp_path / "verified-all.json").with_suffix(
        ".verification.json"
    )
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    assert set(verification["checks"]) == {
        "pdb_foldseek",
        "pdb_sequences",
        "prostt5",
    }
    assert verification["checks"]["pdb_foldseek"]["selected_hit"]["target"] == (
        "1ubq_A"
    )

    log_evidence = pdb_qualification["log"]
    assert isinstance(log_evidence, dict)
    log_path = log_evidence["path"]
    assert isinstance(log_path, str)
    Path(log_path).unlink()
    with pytest.raises(DatabaseError, match=r"log escaped|log is missing"):
        prepare(
            replace(
                request,
                manifest_path=tmp_path / "missing-log.json",
                verify_only=True,
                expected_manifest_path=request.manifest_path,
                expected_manifest_sha256=expected_sha256,
                full_verify=True,
            )
        )


def test_verify_only_rejects_changed_search_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _mocked_full_request(tmp_path, monkeypatch)
    prepare(request)
    expected_sha256 = hashlib.sha256(request.manifest_path.read_bytes()).hexdigest()
    monkeypatch.setenv("FAKE_BITS", "101")

    with pytest.raises(DatabaseError, match="smoke differs"):
        prepare(
            replace(
                request,
                manifest_path=tmp_path / "drifted-verify.json",
                verify_only=True,
                expected_manifest_path=request.manifest_path,
                expected_manifest_sha256=expected_sha256,
                full_verify=True,
            )
        )


def test_pdb_foldseek_rejects_coordinate_sequence_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mismatched = (
        "AQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"
    )
    request = _mocked_full_request(
        tmp_path, monkeypatch, coordinate_sequence=mismatched
    )
    with pytest.raises(DatabaseError, match="differs from the mapped SEQRES"):
        prepare(request)


def test_coupled_pdb_cache_qualification_recovers_after_final_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _mocked_full_request(tmp_path, monkeypatch)
    original_write = prepare_module._write_resource
    injected = False

    def fail_final_pdb_write(resource: DatabaseResource) -> None:
        nonlocal injected
        if (
            not injected
            and getattr(resource, "name", None) == "pdb_foldseek"
            and getattr(resource, "smoke_test_status", None) == SmokeTestStatus.PASSED
        ):
            injected = True
            raise OSError("injected final PDB sidecar failure")
        original_write(resource)

    monkeypatch.setattr(prepare_module, "_write_resource", fail_final_pdb_write)
    with pytest.raises(OSError, match="injected final PDB sidecar failure"):
        prepare(request)
    assert injected
    pdb_current = (
        tmp_path / "database root" / "resources" / "pdb_foldseek" / "current"
    ).resolve(strict=True)
    interrupted_pdb = json.loads(
        (pdb_current / ".gtd-resource.json").read_text(encoding="utf-8")
    )
    assert interrupted_pdb["smoke_test_status"] == "not_run"

    monkeypatch.setattr(prepare_module, "_write_resource", original_write)
    recovered = prepare(replace(request, manifest_path=tmp_path / "recovered.json"))
    resources = {resource.name: resource for resource in recovered.resources}
    pdb_qualification = resources["pdb_foldseek"].parameters["qualification"]
    cache_qualification = resources["coordinate_cache"].parameters["qualification"]
    assert isinstance(pdb_qualification, dict)
    assert pdb_qualification["cache_entry"] == cache_qualification


def test_mocked_pdb_sequence_resource_preserves_target_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "mock bin"
    bin_dir.mkdir()
    _write_mock_tool(bin_dir / "mmseqs", "mmseqs")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    source = tmp_path / "pdb_seqres.txt.gz"
    _write_pdb_sequence_source(source)
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
    assert "1ubq_A\t1UBQ\tlegacy_seqres_suffix\tA" in mapping
    assert resource.parameters["sequence_count"] == 1
    assert resource.parameters["skipped_non_protein_count"] == 1


def test_pdb_sequence_smoke_requires_expected_1ubq_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "mock bin"
    bin_dir.mkdir()
    _write_mock_tool(bin_dir / "mmseqs", "mmseqs")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_SEARCH_TARGET", "2xyz_Z")
    source = tmp_path / "pdb_seqres.txt.gz"
    _write_pdb_sequence_source(source)
    with pytest.raises(DatabaseError, match="expected 1UBQ_A hit"):
        prepare(
            _request(
                tmp_path,
                initialise_coordinate_cache=False,
                prepare_pdb_sequences=True,
                pdb_sequence_url=source.as_uri(),
            )
        )


def test_pdb_sequence_smoke_rejects_empty_successful_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "mock bin"
    bin_dir.mkdir()
    _write_mock_tool(bin_dir / "mmseqs", "mmseqs")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_EMPTY_SEARCH", "1")
    source = tmp_path / "pdb_seqres.txt.gz"
    _write_pdb_sequence_source(source)

    with pytest.raises(DatabaseError, match="produced no result rows"):
        prepare(
            _request(
                tmp_path,
                initialise_coordinate_cache=False,
                prepare_pdb_sequences=True,
                pdb_sequence_url=source.as_uri(),
            )
        )


def test_pdb_foldseek_companions_are_required_before_tool_execution(
    tmp_path: Path,
) -> None:
    with pytest.raises(DatabaseError, match="requires companion resources"):
        prepare(
            _request(
                tmp_path,
                initialise_coordinate_cache=False,
                prepare_pdb_foldseek=True,
            )
        )


def test_pdb_sequence_normalisation_rejects_declared_length_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "mock bin"
    bin_dir.mkdir()
    _write_mock_tool(bin_dir / "mmseqs", "mmseqs")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    source = tmp_path / "bad_seqres.txt.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write(">1ubq_A mol:protein length:75 Ubiquitin\n")
        handle.write(
            "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG\n"
        )

    with pytest.raises(DatabaseError, match="declared length mismatch"):
        prepare(
            _request(
                tmp_path,
                initialise_coordinate_cache=False,
                prepare_pdb_sequences=True,
                pdb_sequence_url=source.as_uri(),
            )
        )


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
