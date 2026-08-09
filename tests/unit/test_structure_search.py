"""Focused tests for the first local structural-search provider."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.results import (
    SearchScientificStatus,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import ExecutionStatus, ResultParseError
from genome_to_diffraction.structure_search import (
    PdbSequenceSearchRequest,
    search_pdb_sequences,
)


def _sequence_group(
    sequence: str, *, flags: tuple[str, ...] = ()
) -> SequenceGroupRecord:
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    if "X" in sequence:
        exact_mass = None
        lower_mass = 100.0
        upper_mass = 200.0
    else:
        exact_mass = 400.0
        lower_mass = None
        upper_mass = None
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=exact_mass,
        molecular_mass_lower_da=lower_mass,
        molecular_mass_upper_da=upper_mass,
        mass_method="test mass",
        residue_policy="test policy",
        source_record_count=1,
        quality_flags=flags,
    )


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, tuple[SequenceGroupRecord, ...]]:
    hit = _sequence_group("ACDE")
    no_hit = _sequence_group("FGHI")
    ineligible = _sequence_group(
        "ACDX", flags=("excluded_ambiguous_or_nonstandard_residue",)
    )
    groups = (hit, no_hit, ineligible)
    sequence_path = tmp_path / "input with spaces" / "sequence groups.jsonl"
    sequence_path.parent.mkdir()
    sequence_path.write_text(
        "".join(f"{canonical_json_text(record)}\n" for record in groups),
        encoding="utf-8",
    )

    resource_root = tmp_path / "database with spaces"
    resource_root.mkdir()
    (resource_root / "pdb_seqres").write_text("mock database\n", encoding="utf-8")
    (resource_root / "target_mapping.tsv").write_text(
        "target_id\tpdb_id\tidentifier_namespace\tseqres_token\t"
        "sequence_length\tsequence_sha256\toriginal_header\n"
        f"1abc_A\t1ABC\tlegacy_seqres_suffix\tA\t4\t{'a' * 64}\t1abc_A\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "database manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "manifest_id": "dbm_test",
                "created_at": "2026-08-09T00:00:00Z",
                "resources": [
                    {
                        "database_id": "db_test_pdb_sequences",
                        "name": "pdb_sequences",
                        "source": "test",
                        "root_path": str(resource_root),
                        "prepared_with": {"tool": "mmseqs", "version": "mock-1.0"},
                        "prepared_at": "2026-08-09T00:00:00Z",
                        "manifest_sha256": "b" * 64,
                        "smoke_test_status": "passed",
                        "status": "ready",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return sequence_path, manifest_path, groups


def _write_mmseqs(path: Path, query_id: str, *, target: str = "1abc_A") -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "${1-}" == version ]]; then\n'
        "  printf 'mock-1.0\\n'\n"
        "  exit 0\n"
        "fi\n"
        '[[ "${1-}" == easy-search ]] || exit 64\n'
        "printf '%s\\t%s\\t1\\t4\\t1\\t4\\t4\\t1\\t1\\t0.75\\t1e-20\\t80\\n' "
        f"'{query_id}' '{target}' > \"$4\"\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_pdb_sequence_search_preserves_hit_no_hit_and_ineligible_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sequence_path, manifest_path, groups = _write_inputs(tmp_path)
    bin_directory = tmp_path / "mock bin"
    bin_directory.mkdir()
    _write_mmseqs(bin_directory / "mmseqs", groups[0].sequence_group_id)
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")

    output = search_pdb_sequences(
        PdbSequenceSearchRequest(
            sequence_groups_jsonl=sequence_path,
            database_manifest=manifest_path,
            output_directory=tmp_path / "output with spaces",
            threads=3,
            maximum_hits_per_query=5,
            progress=False,
        )
    )

    by_query = {result.sequence_group_id: result for result in output.results}
    hit_result = by_query[groups[0].sequence_group_id]
    assert hit_result.execution_status is ExecutionStatus.COMPLETED_HIT
    assert hit_result.scientific_status is SearchScientificStatus.HITS_FOUND
    assert hit_result.hits[0].pdb_id == "1ABC"
    assert hit_result.hits[0].target_chain_or_entity == "A"
    assert hit_result.hits[0].sequence_identity == pytest.approx(0.75)
    assert by_query[groups[1].sequence_group_id].execution_status is (
        ExecutionStatus.COMPLETED_NO_HIT
    )
    assert by_query[groups[2].sequence_group_id].execution_status is (
        ExecutionStatus.SKIPPED_INELIGIBLE
    )
    assert output.results_jsonl.is_file()
    assert output.hits_jsonl.is_file()
    manifest = json.loads(output.search_manifest.read_text(encoding="utf-8"))
    assert manifest["query_count"] == 3
    assert manifest["eligible_query_count"] == 2
    assert manifest["hit_count"] == 1
    command_log = (output.search_manifest.parent / "raw" / "mmseqs.log").read_text(
        encoding="utf-8"
    )
    assert "--threads 3" in command_log
    assert "--max-seqs 5" in command_log
    assert "--alignment-mode 3" in command_log


def test_pdb_sequence_search_rejects_unmapped_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sequence_path, manifest_path, groups = _write_inputs(tmp_path)
    bin_directory = tmp_path / "mock bin"
    bin_directory.mkdir()
    _write_mmseqs(
        bin_directory / "mmseqs", groups[0].sequence_group_id, target="9zzz_Z"
    )
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")

    with pytest.raises(ResultParseError, match="lack coordinate mappings"):
        search_pdb_sequences(
            PdbSequenceSearchRequest(
                sequence_groups_jsonl=sequence_path,
                database_manifest=manifest_path,
                output_directory=tmp_path / "output",
                progress=False,
            )
        )
