"""Focused tests for the first local structural-search provider."""

import hashlib
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.results import (
    SearchScientificStatus,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import (
    ExecutionStatus,
    ResultParseError,
    ToolExecutionError,
)
from genome_to_diffraction.structure_search import (
    P1QualificationRequest,
    PdbSequenceSearchRequest,
    ProstT5FoldseekSearchRequest,
    qualify_p1_search,
    search_pdb_sequences,
    search_prostt5_foldseek,
)
from genome_to_diffraction.structure_search import (
    prostt5_foldseek as prostt5_foldseek_module,
)
from genome_to_diffraction.structure_search import qualification as qualification_module

REPOSITORY = Path(__file__).resolve().parents[2]


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
        "1abc_A\t1ABC\tlegacy_seqres_suffix\tA\t4\t"
        f"{hashlib.sha256(b'ACDE').hexdigest()}\t1abc_A\n",
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
    assert hit_result.hits[0].raw_metrics["target_sequence_length"] == 4
    assert hit_result.hits[0].raw_metrics["target_sequence_sha256"] == (
        hashlib.sha256(b"ACDE").hexdigest()
    )
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
    assert manifest["adapter_version"] == "pdb-sequence-mmseqs-v2"
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


def _write_foldseek_inputs(
    tmp_path: Path,
) -> tuple[Path, Path, tuple[SequenceGroupRecord, ...]]:
    sequence_path, sequence_manifest_path, groups = _write_inputs(tmp_path)
    sequence_manifest = json.loads(sequence_manifest_path.read_text(encoding="utf-8"))
    sequence_resource = sequence_manifest["resources"][0]
    sequence_resource["database_id"] = "db_test_pdb_sequences"

    pdb_root = tmp_path / "Foldseek PDB with spaces"
    pdb_root.mkdir()
    (pdb_root / "pdb").write_text("mock Foldseek database\n", encoding="utf-8")
    prostt5_root = tmp_path / "ProstT5 weights with spaces"
    prostt5_root.mkdir()
    (prostt5_root / "weights").write_text("mock weights\n", encoding="utf-8")
    common = {
        "source": "test",
        "prepared_at": "2026-08-09T00:00:00Z",
        "manifest_sha256": "c" * 64,
        "smoke_test_status": "passed",
        "status": "ready",
    }
    resources = [
        sequence_resource,
        {
            **common,
            "database_id": "db_test_pdb_foldseek",
            "name": "pdb_foldseek",
            "root_path": str(pdb_root),
            "prepared_with": {"tool": "foldseek", "version": "mock-foldseek-1.0"},
        },
        {
            **common,
            "database_id": "db_test_prostt5",
            "name": "prostt5",
            "root_path": str(prostt5_root),
            "prepared_with": {"tool": "foldseek", "version": "mock-foldseek-1.0"},
        },
    ]
    manifest_path = tmp_path / "Foldseek database manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "manifest_id": "dbm_foldseek_test",
                "created_at": "2026-08-09T00:00:00Z",
                "resources": resources,
            }
        ),
        encoding="utf-8",
    )
    return sequence_path, manifest_path, groups


def _write_foldseek(
    path: Path,
    query_id: str,
    *,
    target: str = "1abc-assembly1_A-2",
    bits: str = "60",
) -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "${1-}" == version ]]; then\n'
        "  printf 'mock-foldseek-1.0\\n'\n"
        "  exit 0\n"
        "fi\n"
        '[[ "${1-}" == easy-search ]] || exit 64\n'
        "printf '%s\\t%s\\t0.25\\t4\\t1\\t4\\t1\\t4\\t4\\t4\\t"
        "1\\t1\\t1e-8\\t%s\\n' "
        f"'{query_id}' '{target}' '{bits}' > \"$4\"\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


@pytest.mark.parametrize(
    (
        "target",
        "expected_chain",
        "expected_seqres_token",
        "expected_assembly",
        "expected_operators",
    ),
    (
        ("1iom-assembly1_A-2", "A-2", "A", 1, (2,)),
        ("1abc-assembly12_A-12-60", "A-12-60", "A", 12, (12, 60)),
        ("1abc_A-2", "A-2", "A-2", None, ()),
    ),
)
def test_foldseek_target_preserves_assembly_copy_provenance(
    target: str,
    expected_chain: str,
    expected_seqres_token: str,
    expected_assembly: int | None,
    expected_operators: tuple[int, ...],
) -> None:
    parsed = prostt5_foldseek_module._parse_target(target)

    assert parsed.chain == expected_chain
    assert parsed.seqres_token == expected_seqres_token
    assert parsed.assembly_number == expected_assembly
    assert parsed.operator_indices == expected_operators


def test_prostt5_foldseek_search_preserves_states_and_safe_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sequence_path, manifest_path, groups = _write_foldseek_inputs(tmp_path)
    bin_directory = tmp_path / "mock Foldseek bin"
    bin_directory.mkdir()
    _write_foldseek(bin_directory / "foldseek", groups[0].sequence_group_id)
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")

    output = search_prostt5_foldseek(
        ProstT5FoldseekSearchRequest(
            sequence_groups_jsonl=sequence_path,
            database_manifest=manifest_path,
            output_directory=tmp_path / "Foldseek output with spaces",
            threads=7,
            progress=False,
        )
    )

    by_query = {result.sequence_group_id: result for result in output.results}
    hit = by_query[groups[0].sequence_group_id].hits[0]
    assert hit.provider == "foldseek_prostt5_pdb"
    assert hit.model_key == "pdb:1ABC:legacy_seqres_suffix:A"
    assert hit.target_id == "1abc-assembly1_A-2"
    assert hit.target_chain_or_entity == "A"
    assert hit.query_coverage == 1.0
    assert hit.target_coverage == 1.0
    assert hit.probability is None
    probability_reason = hit.raw_metrics["probability_unavailable_reason"]
    assert isinstance(probability_reason, str)
    assert "query C-alpha" in probability_reason
    assert by_query[groups[1].sequence_group_id].execution_status is (
        ExecutionStatus.COMPLETED_NO_HIT
    )
    assert by_query[groups[2].sequence_group_id].execution_status is (
        ExecutionStatus.SKIPPED_INELIGIBLE
    )
    manifest = json.loads(output.search_manifest.read_text(encoding="utf-8"))
    assert hit.raw_metrics["foldseek_target_chain"] == "A-2"
    assert hit.raw_metrics["biological_assembly_number"] == 1
    assert hit.raw_metrics["assembly_operator_indices"] == [2]
    assert manifest["adapter_version"] == "prostt5-foldseek-pdb-v3"
    assert "prob" not in manifest["parameters"]["output_fields"]
    assert manifest["resource_ids"] == {
        "pdb_foldseek": "db_test_pdb_foldseek",
        "pdb_sequences": "db_test_pdb_sequences",
        "prostt5": "db_test_prostt5",
    }
    command_log = (output.search_manifest.parent / "raw" / "foldseek.log").read_text(
        encoding="utf-8"
    )
    assert "--prostt5-model" in command_log
    assert "--threads 7" in command_log
    assert "--max-seqs 1000" in command_log
    assert "--cov-mode 2" in command_log
    assert "query,target,fident,alnlen,qstart,qend,tstart,tend,qlen,tlen,qcov,tcov" in (
        command_log
    )
    assert ",evalue,bits" in command_log
    for forbidden in (
        ",prob",
        "qca",
        "qtmscore",
        "alntmscore",
        "lddt",
        "--gpu",
    ):
        assert forbidden not in command_log


def test_prostt5_foldseek_query_cap_is_deterministic_and_not_a_no_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sequence_path, manifest_path, groups = _write_foldseek_inputs(tmp_path)
    eligible = sorted(groups[:2], key=lambda item: item.sequence_group_id)
    selected, deferred = eligible
    bin_directory = tmp_path / "mock capped Foldseek bin"
    bin_directory.mkdir()
    _write_foldseek(bin_directory / "foldseek", selected.sequence_group_id)
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")

    output = search_prostt5_foldseek(
        ProstT5FoldseekSearchRequest(
            sequence_groups_jsonl=sequence_path,
            database_manifest=manifest_path,
            output_directory=tmp_path / "capped output",
            maximum_queries=1,
            progress=False,
        )
    )

    by_query = {result.sequence_group_id: result for result in output.results}
    assert by_query[selected.sequence_group_id].execution_status is (
        ExecutionStatus.COMPLETED_HIT
    )
    deferred_result = by_query[deferred.sequence_group_id]
    assert deferred_result.execution_status is ExecutionStatus.SKIPPED_POLICY
    assert deferred_result.scientific_status is SearchScientificStatus.NOT_INTERPRETABLE
    assert deferred_result.warnings == (
        "query deferred by the configured deterministic pilot cap of 1 sequences",
    )
    assert by_query[groups[2].sequence_group_id].execution_status is (
        ExecutionStatus.SKIPPED_INELIGIBLE
    )
    manifest = json.loads(output.search_manifest.read_text(encoding="utf-8"))
    assert manifest["eligible_before_query_cap_count"] == 2
    assert manifest["eligible_query_count"] == 1
    assert manifest["deferred_query_count"] == 1
    assert manifest["parameters"]["maximum_queries"] == 1
    query_fasta = (output.search_manifest.parent / "raw" / "queries.faa").read_text(
        encoding="ascii"
    )
    assert selected.sequence_group_id in query_fasta
    assert deferred.sequence_group_id not in query_fasta


def test_prostt5_foldseek_failure_includes_bounded_native_log_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sequence_path, manifest_path, _ = _write_foldseek_inputs(tmp_path)
    bin_directory = tmp_path / "failing Foldseek bin"
    bin_directory.mkdir()
    foldseek = bin_directory / "foldseek"
    foldseek.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "${1-}" == version ]]; then\n'
        "  printf 'mock-foldseek-1.0\\n'\n"
        "  exit 0\n"
        "fi\n"
        '[[ "${1-}" == easy-search ]] || exit 64\n'
        "for ((i=1; i<=80; i++)); do printf 'diagnostic-%02d\\n' \"$i\"; done\n"
        "printf 'fatal-prostt5-marker\\n'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    foldseek.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")

    with pytest.raises(ToolExecutionError) as raised:
        search_prostt5_foldseek(
            ProstT5FoldseekSearchRequest(
                sequence_groups_jsonl=sequence_path,
                database_manifest=manifest_path,
                output_directory=tmp_path / "failed output",
                progress=False,
            )
        )

    message = str(raised.value)
    assert "Foldseek search failed with exit status 1" in message
    assert "fatal-prostt5-marker" in message
    assert "diagnostic-80" in message
    assert "diagnostic-01" not in message


def test_prostt5_foldseek_gpu_is_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sequence_path, manifest_path, groups = _write_foldseek_inputs(tmp_path)
    bin_directory = tmp_path / "mock-bin"
    bin_directory.mkdir()
    _write_foldseek(bin_directory / "foldseek", groups[0].sequence_group_id)
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")

    output = search_prostt5_foldseek(
        ProstT5FoldseekSearchRequest(
            sequence_groups_jsonl=sequence_path,
            database_manifest=manifest_path,
            output_directory=tmp_path / "gpu-output",
            gpu=True,
            progress=False,
        )
    )

    command_log = (output.search_manifest.parent / "raw" / "foldseek.log").read_text(
        encoding="utf-8"
    )
    assert "--gpu 1" in command_log


def test_prostt5_foldseek_rejects_non_positive_bit_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sequence_path, manifest_path, groups = _write_foldseek_inputs(tmp_path)
    bin_directory = tmp_path / "mock-bin"
    bin_directory.mkdir()
    _write_foldseek(
        bin_directory / "foldseek",
        groups[0].sequence_group_id,
        bits="0",
    )
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")

    with pytest.raises(ResultParseError, match="out-of-range Foldseek metric"):
        search_prostt5_foldseek(
            ProstT5FoldseekSearchRequest(
                sequence_groups_jsonl=sequence_path,
                database_manifest=manifest_path,
                output_directory=tmp_path / "bad-bit-score",
                progress=False,
            )
        )


def _write_trace(path: Path, status: str) -> None:
    path.write_text(
        "task_id\tnative_id\tname\tstatus\texit\tduration\trealtime\t%cpu\t"
        "peak_rss\tpeak_vmem\trchar\twchar\n"
        f"1\t42\tSEARCH_PDB_SEQUENCES\t{status}\t0\t2s\t1s\t100%\t"
        "10 MB\t20 MB\t30 MB\t4 MB\n",
        encoding="utf-8",
    )


def test_p1_qualification_requires_control_family_and_cached_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    search_directory = tmp_path / "search output"
    shutil.copytree(
        REPOSITORY / "tests/fixtures/stubs/structure_search", search_directory
    )
    first_trace = tmp_path / "first trace.tsv"
    resume_trace = tmp_path / "resume trace.tsv"
    _write_trace(first_trace, "COMPLETED")
    _write_trace(resume_trace, "CACHED")
    target_digest = "f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e"
    monkeypatch.setattr(
        qualification_module,
        "load_public_control_spec",
        lambda _: SimpleNamespace(
            control_id="TEST_CONTROL",
            target_sequence_sha256=target_digest,
            target_pdb_id="1UBQ",
            resources=(),
        ),
    )

    report = qualify_p1_search(
        P1QualificationRequest(
            sequence_groups_jsonl=REPOSITORY
            / "tests/fixtures/stubs/sequence_groups.jsonl",
            search_directory=search_directory,
            control_specification=tmp_path / "unused.yaml",
            first_trace_tsv=first_trace,
            resume_trace_tsv=resume_trace,
            output_json=tmp_path / "p1 qualification.json",
            progress=False,
        )
    )

    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["status"] == "passed"
    assert result["all_resume_processes_cached"] is True
    assert result["retained_control_hits"][0]["model_key"] == (
        "pdb:1UBQ:legacy_seqres_suffix:A"
    )


def test_p1_qualification_rejects_uncached_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    search_directory = tmp_path / "search"
    shutil.copytree(
        REPOSITORY / "tests/fixtures/stubs/structure_search", search_directory
    )
    first_trace = tmp_path / "first.tsv"
    resume_trace = tmp_path / "resume.tsv"
    _write_trace(first_trace, "COMPLETED")
    _write_trace(resume_trace, "COMPLETED")
    target_digest = "f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e"
    monkeypatch.setattr(
        qualification_module,
        "load_public_control_spec",
        lambda _: SimpleNamespace(
            control_id="TEST_CONTROL",
            target_sequence_sha256=target_digest,
            target_pdb_id="1UBQ",
            resources=(),
        ),
    )

    with pytest.raises(ResultParseError, match="only CACHED"):
        qualify_p1_search(
            P1QualificationRequest(
                sequence_groups_jsonl=REPOSITORY
                / "tests/fixtures/stubs/sequence_groups.jsonl",
                search_directory=search_directory,
                control_specification=tmp_path / "unused.yaml",
                first_trace_tsv=first_trace,
                resume_trace_tsv=resume_trace,
                output_json=tmp_path / "qualification.json",
                progress=False,
            )
        )
