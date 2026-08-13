"""Unit tests for idempotent and fail-loud database preparation."""

import gzip
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import genome_to_diffraction.databases.common as common_module
import genome_to_diffraction.databases.sources as sources_module
from genome_to_diffraction.databases.cache import (
    CachedCoordinate,
    exclusive_lock,
    initialise_coordinate_cache,
    publish_pdb_coordinate,
    verify_cached_pdb_coordinate,
)
from genome_to_diffraction.databases.common import (
    DatabaseCommandError,
    DatabaseError,
    copy_inventoried_resource,
    inventory_resource,
    tool_version,
    verify_inventory,
)
from genome_to_diffraction.databases.network import DownloadMetadata
from genome_to_diffraction.databases.prepare import (
    DatabasePreparationRequest,
    SmokeHit,
    prepare,
)
from genome_to_diffraction.databases.sources import (
    PDB_COORDINATE_SMOKE_URL,
    PDB_SEQUENCE_URL,
    SOURCE_SPECS,
    SourceBundleRequest,
    stage_source_bundle,
)
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    DatabaseManifest,
    DatabaseResource,
    SmokeTestStatus,
)

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


def test_database_root_lock_serialises_administrative_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    original = cast(
        Callable[
            [DatabasePreparationRequest, Path, DatabaseManifest | None, Path],
            DatabaseManifest,
        ],
        prepare_module._prepare_locked,
    )
    state_lock = threading.Lock()
    active = 0
    maximum_active = 0

    def delayed(
        delayed_request: DatabasePreparationRequest,
        delayed_root: Path,
        delayed_expected: DatabaseManifest | None,
        delayed_scratch: Path,
    ) -> DatabaseManifest:
        nonlocal active, maximum_active
        with state_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            time.sleep(0.1)
            return original(
                delayed_request,
                delayed_root,
                delayed_expected,
                delayed_scratch,
            )
        finally:
            with state_lock:
                active -= 1

    monkeypatch.setattr(prepare_module, "_prepare_locked", delayed)
    with ThreadPoolExecutor(max_workers=2) as executor:
        manifests = list(
            executor.map(
                prepare,
                (
                    request,
                    replace(request, manifest_path=tmp_path / "second.json"),
                ),
            )
        )

    assert len(manifests) == 2
    assert maximum_active == 1


def test_database_root_lock_timeout_fails_without_starting_work(tmp_path: Path) -> None:
    request = _request(tmp_path, lock_timeout_seconds=0.05)
    root = request.database_root
    lock_path = root / "tmp" / "locks" / "database-administration.lock"
    acquired = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with exclusive_lock(lock_path, timeout_seconds=1, progress=False):
            acquired.set()
            release.wait(timeout=2)

    thread = threading.Thread(target=hold_lock)
    thread.start()
    assert acquired.wait(timeout=1)
    try:
        with pytest.raises(DatabaseError, match="timed out waiting for database lock"):
            prepare(request)
    finally:
        release.set()
        thread.join(timeout=2)
    assert not request.manifest_path.exists()


def test_tool_version_uses_a_documented_version_subcommand(tmp_path: Path) -> None:
    bin_directory = tmp_path / "tool bin"
    bin_directory.mkdir()
    executable = bin_directory / "foldseek"
    executable.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        '[[ "${1-}" == version ]] || exit 64\n'
        "printf '10.941cd33\\n'\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)

    assert tool_version(str(executable), arguments=("version",)) == "10.941cd33"


def test_tool_version_uses_unbounded_default_and_logs_elapsed_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_timeouts: list[float | None] = []
    log_records: list[tuple[str, dict[str, object]]] = []

    def complete(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        timeout = kwargs.get("timeout")
        assert timeout is None
        observed_timeouts.append(timeout)
        return subprocess.CompletedProcess(command, 0, "10.941cd33\n", "")

    monkeypatch.setattr(
        "genome_to_diffraction.databases.common.subprocess.run", complete
    )
    monkeypatch.setattr(
        common_module._LOGGER,
        "info",
        lambda message, *, extra: log_records.append((message, extra)),
    )
    assert tool_version("foldseek", arguments=("version",)) == "10.941cd33"

    assert observed_timeouts == [None]
    assert [message for message, _ in log_records] == [
        "version probe started",
        "version probe completed",
    ]
    assert log_records[0][1]["timeout_seconds"] is None
    assert log_records[1][1]["version"] == "10.941cd33"
    assert isinstance(log_records[1][1]["elapsed_seconds"], float)


def test_tool_version_converts_timeout_to_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=["foldseek", "version"], timeout=0.5)

    monkeypatch.setattr(
        "genome_to_diffraction.databases.common.subprocess.run", time_out
    )

    with pytest.raises(DatabaseError, match="version probe timed out"):
        tool_version(
            "foldseek",
            arguments=("version",),
            timeout_seconds=0.5,
        )


def _write_mock_tool(path: Path, name: str) -> None:
    script = f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "${{1-}}" == "--version" || "${{1-}}" == "version" ]]; then
  printf '{name} mock-1.0\n'
  exit 0
fi
case "${{1-}}" in
  databases)
    if [[ -n "${{FAKE_DATABASE_COMMAND_RECORD:-}}" ]]; then
      printf '%s\n' "$*" >> "$FAKE_DATABASE_COMMAND_RECORD"
    fi
    if [[ "${{FAKE_DATABASE_FAILURE:-0}}" == 1 ]]; then
      printf 'injected database failure\n' >&2
      exit 70
    fi
    if [[ -n "${{FAKE_DATABASE_TMP_RECORD:-}}" ]]; then
      printf '%s\n' "$4" >> "$FAKE_DATABASE_TMP_RECORD"
    fi
    if [[ -n "${{FAKE_DATABASE_TMPDIR_RECORD:-}}" ]]; then
      printf '%s\n' "${{TMPDIR:-}}" >> "$FAKE_DATABASE_TMPDIR_RECORD"
    fi
    mkdir -p "$(dirname "$3")"
    printf '%s\n' "$2 database" > "$3"
    printf 'index\n' > "$3.index"
    if [[ "$2" == PDB ]]; then
      if [[ "${{FAKE_BAD_PDB_VERSION:-0}}" == 1 ]]; then
        printf 'malformed provider version\n' > "$3.version"
      else
        printf '%s\n' \
          'aefd75e0a5d6acbe8a2b7791b53eb479  pdb100.tar.gz' \
          $'250101\tPDB_DATE' \
          $'1815f0d76d7b5807e63b13f9d446dcef43c1f3b1\tFOLDSEEK_COMMIT' \
          > "$3.version"
      fi
    fi
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


def test_pdb_seqres_chain_tokens_are_case_sensitive(tmp_path: Path) -> None:
    source = tmp_path / "case-sensitive-seqres.txt.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write(">10eg_A mol:protein length:2 upper chain\nAA\n")
        handle.write(">10eg_a mol:protein length:2 lower chain\nAA\n")
    fasta = tmp_path / "normalised.faa"
    mapping = tmp_path / "mapping.tsv"

    count, skipped = prepare_module._normalise_pdb_sequences(
        source, fasta, mapping, progress=False
    )

    assert (count, skipped) == (2, 0)
    assert fasta.read_text(encoding="utf-8") == ">10eg_A\nAA\n>10eg_a\nAA\n"
    mapping_text = mapping.read_text(encoding="utf-8")
    assert "10eg_A\t10EG\tlegacy_seqres_suffix\tA\t" in mapping_text
    assert "10eg_a\t10EG\tlegacy_seqres_suffix\ta\t" in mapping_text

    selected = prepare_module._select_functional_smoke_hit(
        (
            SmokeHit("ubiquitin_smoke", "1ubq_a", 1e-20, 100.0, 1.0, 1.0),
            SmokeHit("ubiquitin_smoke", "1ubq_A", 1e-20, 100.0, 1.0, 1.0),
        )
    )
    assert selected.target == "1ubq_A"


def test_foldseek_assembly_target_resolves_to_case_sensitive_seqres_chain(
    tmp_path: Path,
) -> None:
    source = tmp_path / "pdb-seqres.txt.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write(">6isu_C mol:protein length:2 upper chain\nAA\n")
        handle.write(">6isu_c mol:protein length:2 lower chain\nAA\n")
    sequence_root = tmp_path / "pdb-sequences"
    sequence_root.mkdir()
    prepare_module._normalise_pdb_sequences(
        source,
        sequence_root / "pdb_seqres.faa",
        sequence_root / "target_mapping.tsv",
        progress=False,
    )

    assert prepare_module._parse_pdb_seqres_target("6isu-assembly1_C") == (
        "6ISU",
        "C",
    )
    assert prepare_module._parse_pdb_seqres_target("6ISU-assembly12_c") == (
        "6ISU",
        "c",
    )
    mapping = prepare_module._require_seqres_mapping(sequence_root, "6isu-assembly1_C")
    assert mapping["target_id"] == "6isu_C"
    assert mapping["seqres_token"] == "C"
    selected = prepare_module._select_functional_smoke_hit(
        (
            SmokeHit(
                "ubiquitin_smoke",
                "6isu-assembly1_C",
                1e-20,
                100.0,
                1.0,
                1.0,
            ),
        )
    )
    assert selected.target == "6isu-assembly1_C"


@pytest.mark.parametrize(
    "target",
    (
        "6isu-assembly0_C",
        "6isu-assembly01_C",
        "6isu-assembly_C",
        "6isu-assemblyx_C",
        "6isu-assembly1_",
    ),
)
def test_foldseek_assembly_target_rejects_malformed_identifier(target: str) -> None:
    with pytest.raises(DatabaseError, match="unsupported PDB SEQRES target"):
        prepare_module._parse_pdb_seqres_target(target)


def test_pdb_smoke_logs_bounded_result_evidence_without_requiring_fixed_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_records: list[tuple[str, dict[str, object]]] = []

    hits = tuple(
        SmokeHit("ubiquitin_smoke", f"2a{index:02d}_A", 1e-20, 100.0, 1.0, 1.0)
        for index in range(11)
    )

    monkeypatch.setattr(
        prepare_module._LOGGER,
        "info",
        lambda message, *, extra: log_records.append((message, extra)),
    )
    selected = prepare_module._select_functional_smoke_hit(hits)

    evidence = next(
        extra
        for message, extra in log_records
        if message == "database smoke results parsed"
    )
    assert evidence["hit_count"] == 11
    assert evidence["expected_match_count"] == 0
    assert len(cast(list[object], evidence["top_hits"])) == 10
    assert evidence["top_hits_truncated"] is True
    assert selected.target == "2a00_A"


def test_pdb_smoke_rejects_weak_best_hit() -> None:
    with pytest.raises(DatabaseError, match="best database smoke hit failed"):
        prepare_module._select_functional_smoke_hit(
            (SmokeHit("ubiquitin_smoke", "2xyz_Z", 1e-2, 20.0, 0.8, 0.8),)
        )


def test_pdb_sequence_smoke_accepts_equivalent_hit_with_independent_1ubq_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_root = tmp_path / "database"
    sequence_root = database_root / "pdb-sequences"
    (database_root / "tmp").mkdir(parents=True)
    sequence_root.mkdir()
    source = tmp_path / "pdb-seqres.txt.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        for target in ("1ubq_A", "2xyz_Z"):
            handle.write(f">{target} mol:protein length:76 ubiquitin\n")
            handle.write(f"{prepare_module._SMOKE_SEQUENCE}\n")
    prepare_module._normalise_pdb_sequences(
        source,
        sequence_root / "pdb_seqres.faa",
        sequence_root / "target_mapping.tsv",
        progress=False,
    )

    def write_equivalent_result(
        command: list[str], **options: object
    ) -> subprocess.CompletedProcess[str]:
        Path(command[4]).write_text(
            "ubiquitin_smoke\t2xyz_Z\t1e-42\t152\t1\t1\n",
            encoding="utf-8",
        )
        log_path = options["log_path"]
        assert isinstance(log_path, Path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("fake mmseqs success\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(prepare_module, "run_command", write_equivalent_result)
    qualification = prepare_module._run_pdb_sequence_smoke(
        _request(tmp_path, database_root=database_root),
        database_root,
        sequence_root,
    )

    selected = qualification["selected_hit"]
    mapping = qualification["mapping"]
    assert isinstance(selected, dict)
    assert isinstance(mapping, dict)
    assert selected["target"] == "2xyz_Z"
    assert mapping["target_id"] == "1ubq_A"
    assert "expected_hit" not in qualification


def test_search_smoke_comparison_accepts_tied_hit_order_variation() -> None:
    fixed_mapping = {
        "target_id": "1ubq_A",
        "pdb_id": "1UBQ",
        "identifier_namespace": "legacy_seqres_suffix",
        "seqres_token": "A",
        "sequence_length": 76,
        "sequence_sha256": hashlib.sha256(
            prepare_module._SMOKE_SEQUENCE.encode("ascii")
        ).hexdigest(),
    }
    expected = {
        "kind": "known_ubiquitin_mmseqs_search",
        "query_id": "ubiquitin_smoke",
        "query_sequence_sha256": fixed_mapping["sequence_sha256"],
        "thresholds": prepare_module._smoke_thresholds(),
        "hit_count": 684,
        "selected_hit": {
            "query": "ubiquitin_smoke",
            "target": "11sy_H",
            "evalue": 1e-42,
            "bits": 152.0,
            "query_coverage": 1.0,
            "target_coverage": 1.0,
        },
        "selected_hit_mapping": {"target_id": "11sy_H"},
        "mapping": fixed_mapping,
        "query": {"path": "/old/query.faa", "sha256": "a" * 64},
        "result": {"path": "/old/result.tsv", "sha256": "b" * 64},
    }
    observed = {
        **expected,
        "hit_count": 676,
        "selected_hit": {
            "query": "ubiquitin_smoke",
            "target": "1wr6_F",
            "evalue": 1e-42,
            "bits": 152.0,
            "query_coverage": 1.0,
            "target_coverage": 1.0,
        },
        "selected_hit_mapping": {"target_id": "1wr6_F"},
        "query": {"path": "/new/query.faa", "sha256": "a" * 64},
        "result": {"path": "/new/result.tsv", "sha256": "c" * 64},
    }

    prepare_module._require_matching_smoke_evidence(
        expected,
        observed,
        keys=prepare_module._SEARCH_SMOKE_STABLE_KEYS,
        label="PDB-sequence",
    )


def test_search_smoke_comparison_rejects_fixed_mapping_change() -> None:
    expected = {
        "kind": "known_ubiquitin_mmseqs_search",
        "query_id": "ubiquitin_smoke",
        "query_sequence_sha256": "a" * 64,
        "thresholds": prepare_module._smoke_thresholds(),
        "selected_hit": {
            "query": "ubiquitin_smoke",
            "target": "1ubq_A",
            "evalue": 1e-42,
            "bits": 152.0,
            "query_coverage": 1.0,
            "target_coverage": 1.0,
        },
        "mapping": {"target_id": "1ubq_A", "sequence_sha256": "a" * 64},
        "query": {"path": "/old/query.faa", "sha256": "b" * 64},
    }
    observed = {
        **expected,
        "mapping": {"target_id": "1ubq_A", "sequence_sha256": "c" * 64},
    }

    with pytest.raises(DatabaseError, match="differs from expected qualification"):
        prepare_module._require_matching_smoke_evidence(
            expected,
            observed,
            keys=prepare_module._SEARCH_SMOKE_STABLE_KEYS,
            label="PDB-sequence",
        )


def test_pdb_smoke_requires_selected_hit_to_match_query_sequence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "pdb-seqres.txt.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write(">1ubq_A mol:protein length:76 Ubiquitin\n")
        handle.write(f"{prepare_module._SMOKE_SEQUENCE}\n")
        handle.write(">2xyz_Z mol:protein length:76 unrelated\n")
        handle.write(f"{'A' * 76}\n")
    sequence_root = tmp_path / "pdb-sequences"
    sequence_root.mkdir()
    prepare_module._normalise_pdb_sequences(
        source,
        sequence_root / "pdb_seqres.faa",
        sequence_root / "target_mapping.tsv",
        progress=False,
    )
    hit = SmokeHit("ubiquitin_smoke", "2xyz_Z", 1e-20, 100.0, 1.0, 1.0)

    with pytest.raises(DatabaseError, match="not sequence-equivalent"):
        prepare_module._require_query_equivalent_smoke_mapping(sequence_root, hit)

    fixed_mapping = prepare_module._require_expected_smoke_mapping(sequence_root)
    assert fixed_mapping["target_id"] == "1ubq_A"


def test_pdb_seqres_rejects_exact_duplicate_chain_token(tmp_path: Path) -> None:
    source = tmp_path / "duplicate-seqres.txt.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write(">10eg_A mol:protein length:2 first\nAA\n")
        handle.write(">10EG_A mol:protein length:2 duplicate\nAA\n")

    with pytest.raises(DatabaseError, match="duplicate PDB protein SEQRES target"):
        prepare_module._normalise_pdb_sequences(
            source,
            tmp_path / "normalised.faa",
            tmp_path / "mapping.tsv",
            progress=False,
        )


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


def _stage_mock_source_bundle(
    request: DatabasePreparationRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    request.database_root.mkdir(parents=True, exist_ok=True)

    def download(url: str, destination: Path, **_kwargs: object) -> DownloadMetadata:
        if url == PDB_SEQUENCE_URL:
            _write_pdb_sequence_source(destination)
        elif url == PDB_COORDINATE_SMOKE_URL:
            _write_pdb_coordinate(destination)
        else:
            destination.write_bytes(f"fixed source for {url}\n".encode())
        payload = destination.read_bytes()
        return DownloadMetadata(
            requested_url=url,
            url=url,
            etag='"fixed"',
            last_modified="Sun, 09 Aug 2026 00:00:00 GMT",
            content_type="application/octet-stream",
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )

    monkeypatch.setattr(
        "genome_to_diffraction.databases.sources.download_public_resource", download
    )
    manifest = tmp_path / "source-bundle.json"
    stage_source_bundle(
        SourceBundleRequest(
            database_root=request.database_root,
            manifest_path=manifest,
            storage_limit_bytes=request.storage_limit_bytes,
            minimum_free_bytes=0,
            progress=False,
        )
    )
    return manifest


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
            requested_url="https://files.rcsb.org/download/1ubq.cif.gz",
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
        requested_url="https://files.rcsb.org/download/1ubq.cif.gz",
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


def test_copy_back_detects_durable_corruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "scratch resource"
    source.mkdir()
    (source / "payload").write_bytes(b"trusted")
    records, digest = inventory_resource(source, progress=False)
    storage_root = tmp_path / "durable"
    destination = storage_root / "resources" / ".staging"
    destination.mkdir(parents=True)
    real_copymode = shutil.copymode

    def corrupt_after_copy(source_path: Path, destination_path: Path) -> None:
        real_copymode(source_path, destination_path)
        destination_path.write_bytes(b"corrupt")

    monkeypatch.setattr(
        "genome_to_diffraction.databases.common.shutil.copymode",
        corrupt_after_copy,
    )
    with pytest.raises(DatabaseError, match="checksum mismatch"):
        copy_inventoried_resource(
            source,
            destination,
            records,
            digest,
            storage_root=storage_root,
            storage_limit_bytes=1_000_000,
            minimum_free_bytes=0,
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
    verification = json.loads(
        (tmp_path / "verified.verification.json").read_text(encoding="utf-8")
    )
    assert verification["verification_level"] == (
        "inventory_metadata_and_functional_smoke"
    )
    assert verification["full_checksums"] is False

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


def test_failed_foldseek_staging_blocks_space_consuming_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "mock bin"
    bin_dir.mkdir()
    _write_mock_tool(bin_dir / "foldseek", "foldseek")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_DATABASE_FAILURE", "1")
    request = _request(
        tmp_path,
        initialise_coordinate_cache=False,
        prepare_prostt5=True,
    )

    with pytest.raises(
        DatabaseCommandError, match="command failed with exit status 70"
    ):
        prepare(request)
    failed = list(
        (request.database_root / "resources" / "prostt5").glob(".staging-*.failed")
    )
    assert len(failed) == 1

    monkeypatch.delenv("FAKE_DATABASE_FAILURE")
    with pytest.raises(DatabaseError, match="retained incomplete database staging"):
        prepare(request)
    assert (
        list(
            (request.database_root / "resources" / "prostt5").glob(".staging-*.failed")
        )
        == failed
    )


@pytest.mark.parametrize(
    "retained_name",
    (
        f".staging-{'a' * 32}",
        f"..staging-{'b' * 32}.failed",
    ),
)
def test_crash_or_legacy_staging_blocks_new_allocation(
    tmp_path: Path, retained_name: str
) -> None:
    database_root = tmp_path / "database root"
    resource_base = database_root / "resources" / "prostt5"
    retained = resource_base / retained_name
    retained.mkdir(parents=True)

    with pytest.raises(
        DatabaseError,
        match="retained incomplete database staging",
    ):
        prepare_module._staging(database_root, "prostt5")


def test_mocked_foldseek_resources_prepare_smoke_and_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command_record = tmp_path / "foldseek-databases-commands.txt"
    monkeypatch.setenv("FAKE_DATABASE_COMMAND_RECORD", str(command_record))
    request = replace(_mocked_full_request(tmp_path, monkeypatch), threads=3)

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
    database_commands = command_record.read_text(encoding="utf-8").splitlines()
    assert len(database_commands) == 2
    assert all(command.endswith("--threads 3") for command in database_commands)
    resources = {resource.name: resource for resource in first.resources}
    pdb_resource = resources["pdb_foldseek"]
    assert pdb_resource.release_or_snapshot == "pdb-2025-01-01"
    provider_snapshot = pdb_resource.parameters["provider_snapshot"]
    assert isinstance(provider_snapshot, dict)
    assert provider_snapshot == {
        "pdb_date": "2025-01-01",
        "archive_basename": "pdb100.tar.gz",
        "archive_md5": "aefd75e0a5d6acbe8a2b7791b53eb479",
        "archive_digest_algorithm": "MD5 (provider record; not trust anchor)",
        "foldseek_database_commit": ("1815f0d76d7b5807e63b13f9d446dcef43c1f3b1"),
        "version_file_sha256": hashlib.sha256(
            (
                "aefd75e0a5d6acbe8a2b7791b53eb479  pdb100.tar.gz\n"
                "250101\tPDB_DATE\n"
                "1815f0d76d7b5807e63b13f9d446dcef43c1f3b1\t"
                "FOLDSEEK_COMMIT\n"
            ).encode("ascii")
        ).hexdigest(),
    }
    pdb_qualification = resources["pdb_foldseek"].parameters["qualification"]
    assert isinstance(pdb_qualification, dict)
    mapping_evidence = pdb_qualification["mapping"]
    selected_mapping_evidence = pdb_qualification["selected_hit_mapping"]
    coordinate_evidence = pdb_qualification["coordinate_mapping"]
    assert isinstance(mapping_evidence, dict)
    assert isinstance(selected_mapping_evidence, dict)
    assert isinstance(coordinate_evidence, dict)
    assert mapping_evidence["target_id"] == "1ubq_A"
    assert (
        selected_mapping_evidence["sequence_sha256"]
        == hashlib.sha256(prepare_module._SMOKE_SEQUENCE.encode("ascii")).hexdigest()
    )
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
    assert verification["verification_level"] == ("full_checksums_and_functional_smoke")
    assert verification["full_checksums"] is True
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


def test_mocked_database_prepare_consumes_only_verified_offline_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _mocked_full_request(tmp_path, monkeypatch)
    source_manifest = _stage_mock_source_bundle(request, tmp_path, monkeypatch)
    aria2c = tmp_path / "mock bin" / "aria2c"
    aria2c.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="ascii")
    aria2c.chmod(0o755)

    def reject_network(*_args: object, **_kwargs: object) -> None:
        pytest.fail("offline database preparation attempted a network download")

    monkeypatch.setattr(prepare_module, "download_public_resource", reject_network)
    offline_request = replace(request, source_bundle_path=source_manifest)

    manifest = prepare(offline_request)

    resources = {resource.name: resource for resource in manifest.resources}
    for name in ("pdb_foldseek", "pdb_sequences", "prostt5"):
        bundle_id = resources[name].parameters["source_bundle_id"]
        assert isinstance(bundle_id, str)
        assert bundle_id.startswith("dbsrc_")


@pytest.mark.parametrize(
    ("tool", "arguments", "relative_destination"),
    (
        ("aria2c", (), "pdb100.tar.gz"),
        ("aria2c", ("--dir", "payloads", "--out", "pdb.tar.gz"), "payloads/pdb.tar.gz"),
        (
            "curl",
            ("--location", "--output", "payloads/pdb.tar.gz"),
            "payloads/pdb.tar.gz",
        ),
        ("wget", ("--output-document", "payloads/pdb.tar.gz"), "payloads/pdb.tar.gz"),
    ),
)
def test_offline_foldseek_wrappers_copy_fixed_urls_and_reject_other_network(
    tool: str,
    arguments: tuple[str, ...],
    relative_destination: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _mocked_full_request(tmp_path, monkeypatch)
    source_manifest = _stage_mock_source_bundle(request, tmp_path, monkeypatch)
    bundle = sources_module.load_source_bundle(
        request.database_root,
        source_manifest,
        full_verify=True,
        progress=False,
    )
    bin_dir = tmp_path / "aria bin"
    bin_dir.mkdir()
    aria2c = bin_dir / "aria2c"
    aria2c.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="ascii")
    aria2c.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    staging = tmp_path / "offline staging"
    scratch = staging / "tmp"
    scratch.mkdir(parents=True)
    (scratch / "payloads").mkdir()

    with prepare_module._offline_foldseek_environment(
        staging, request.database_root, bundle, scratch
    ) as environment:
        mapped = subprocess.run(
            [tool, *arguments, SOURCE_SPECS[0].requested_url],
            check=False,
            capture_output=True,
            text=True,
            cwd=scratch,
            env={**os.environ, **environment},
        )
        rejected = subprocess.run(
            [tool, "https://unapproved.example.test/payload"],
            check=False,
            capture_output=True,
            text=True,
            cwd=scratch,
            env={**os.environ, **environment},
        )

    assert mapped.returncode == 0
    assert (scratch / relative_destination).read_bytes() == bundle.path(
        request.database_root, SOURCE_SPECS[0].name
    ).read_bytes()
    assert f"copied via {tool}" in mapped.stderr
    assert rejected.returncode == 64
    assert "unapproved network URL" in rejected.stderr


def test_offline_foldseek_wrapper_rejects_destination_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _mocked_full_request(tmp_path, monkeypatch)
    source_manifest = _stage_mock_source_bundle(request, tmp_path, monkeypatch)
    bundle = sources_module.load_source_bundle(
        request.database_root,
        source_manifest,
        full_verify=True,
        progress=False,
    )
    bin_dir = tmp_path / "aria bin"
    bin_dir.mkdir()
    aria2c = bin_dir / "aria2c"
    aria2c.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="ascii")
    aria2c.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    staging = tmp_path / "offline staging"
    scratch = staging / "tmp"
    scratch.mkdir(parents=True)

    with prepare_module._offline_foldseek_environment(
        staging, request.database_root, bundle, scratch
    ) as environment:
        rejected = subprocess.run(
            [
                "wget",
                "--output-document",
                str(tmp_path / "escaped.tar.gz"),
                SOURCE_SPECS[0].requested_url,
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=scratch,
            env={**os.environ, **environment},
        )

    assert rejected.returncode == 64
    assert "destination escaped staging" in rejected.stderr
    assert not (tmp_path / "escaped.tar.gz").exists()


def test_pdb_foldseek_rejects_malformed_provider_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _mocked_full_request(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_BAD_PDB_VERSION", "1")

    with pytest.raises(DatabaseError, match="version record must contain three lines"):
        prepare(request)

    retained = list(
        (request.database_root / "resources" / "pdb_foldseek").glob("*.failed")
    )
    assert len(retained) == 1


def test_database_resources_build_on_same_filesystem_scratch_and_publish_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _mocked_full_request(tmp_path, monkeypatch)
    scratch = tmp_path / "compute scratch"
    scratch.mkdir()
    scratch_record = tmp_path / "scratch-record.txt"
    tmpdir_record = tmp_path / "tmpdir-record.txt"
    monkeypatch.setenv("FAKE_DATABASE_TMP_RECORD", str(scratch_record))
    monkeypatch.setenv("FAKE_DATABASE_TMPDIR_RECORD", str(tmpdir_record))
    monkeypatch.setattr(
        prepare_module,
        "_device_id",
        lambda _path: 1,
    )
    monkeypatch.setattr(
        common_module,
        "_device_id",
        lambda _path: 1,
    )
    request = replace(
        request,
        scratch_root=scratch,
        minimum_scratch_free_bytes=1,
    )

    manifest = prepare(request)

    assert len(manifest.resources) == 4
    recorded = scratch_record.read_text(encoding="utf-8").splitlines()
    assert len(recorded) == 2
    assert all(Path(path).is_relative_to(scratch) for path in recorded)
    inherited_tmpdirs = tmpdir_record.read_text(encoding="utf-8").splitlines()
    assert inherited_tmpdirs == recorded
    for resource in manifest.resources:
        assert Path(resource.root_path).is_relative_to(request.database_root)
        if resource.name != "coordinate_cache":
            assert resource.parameters["build_storage"] == "compute_scratch"
    assert list(scratch.iterdir()) == []


def test_failed_copy_back_retains_durable_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _mocked_full_request(tmp_path, monkeypatch)
    scratch = tmp_path / "compute scratch"
    scratch.mkdir()
    monkeypatch.setattr(
        prepare_module,
        "_device_id",
        lambda path: 2 if path.is_relative_to(scratch) else 1,
    )
    monkeypatch.setattr(
        common_module,
        "_device_id",
        lambda path: 2 if path.is_relative_to(scratch) else 1,
    )

    def fail_copy(
        _source: Path, destination: Path, *_args: object, **_kwargs: object
    ) -> None:
        (destination / "partial").write_text("incomplete\n", encoding="ascii")
        raise DatabaseError("simulated copy-back failure")

    monkeypatch.setattr(prepare_module, "copy_inventoried_resource", fail_copy)
    with pytest.raises(DatabaseError, match="simulated copy-back failure"):
        prepare(
            replace(
                request,
                scratch_root=scratch,
                minimum_scratch_free_bytes=1,
            )
        )

    retained = list((request.database_root / "resources" / "prostt5").glob("*.failed"))
    assert len(retained) == 1
    assert (retained[0] / "partial").read_text(encoding="ascii") == "incomplete\n"
    assert list(scratch.iterdir()) == []


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


def test_pdb_sequence_smoke_requires_selected_target_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "mock bin"
    bin_dir.mkdir()
    _write_mock_tool(bin_dir / "mmseqs", "mmseqs")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_SEARCH_TARGET", "2xyz_Z")
    source = tmp_path / "pdb_seqres.txt.gz"
    _write_pdb_sequence_source(source)
    with pytest.raises(DatabaseError, match="does not map to PDB SEQRES"):
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
