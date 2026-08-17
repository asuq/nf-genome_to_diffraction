"""Focused contracts for checksum-bound runner-side M6 identity decisions."""

import gzip
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from genome_to_diffraction.benchmarks.m6_identity import (
    M6IdentityCandidate,
    M6IdentityDecision,
    derive_m6_identity_decision,
    verify_m6_identity_decision_evidence,
)
from genome_to_diffraction.benchmarks.m6_scientific import (
    m6_track_case_ids,
    verify_m6_scientific_output,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_digest, sequence_digest
from genome_to_diffraction.schemas.results import SequenceGroupRecord


def _group(sequence: str) -> SequenceGroupRecord:
    digest = sequence_digest(sequence)
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=100.0,
        mass_method="test",
        residue_policy="test",
        source_record_count=1,
    )


def _seed(group: SequenceGroupRecord, seed_id: str) -> dict[str, object]:
    return {
        "sequence_group_id": group.sequence_group_id,
        "seed_solution_id": seed_id,
    }


def test_identity_decision_states_and_canonical_replay() -> None:
    first = _group("AAAA")
    second = _group("CCCC")

    abstained = derive_m6_identity_decision(
        case_id="M6C001",
        selected_seed_results=(),
        sequence_groups=(first, second),
    )
    assert abstained.decision == "abstained"
    assert abstained.candidates == ()

    reported = derive_m6_identity_decision(
        case_id="M6C001",
        selected_seed_results=(
            _seed(first, "sol_z"),
            _seed(first, "sol_a"),
            _seed(first, "sol_a"),
        ),
        sequence_groups=(second, first),
    )
    replay = derive_m6_identity_decision(
        case_id="M6C001",
        selected_seed_results=(
            _seed(first, "sol_a"),
            _seed(first, "sol_z"),
        ),
        sequence_groups=(first, second),
    )
    assert reported.decision == "reported"
    assert reported.candidates[0].sequence_sha256 == first.sha256
    assert tuple(
        pointer.seed_solution_id for pointer in reported.candidates[0].evidence_pointers
    ) == (
        "sol_a",
        "sol_z",
    )
    assert replay == reported

    ambiguous = derive_m6_identity_decision(
        case_id="M6C001",
        selected_seed_results=(
            _seed(second, "sol_second"),
            _seed(first, "sol_first"),
        ),
        sequence_groups=(second, first),
    )
    assert ambiguous.decision == "ambiguous"
    assert tuple(item.sequence_sha256 for item in ambiguous.candidates) == tuple(
        sorted((first.sha256, second.sha256))
    )


def test_identity_contract_rejects_tampering_and_inconsistent_evidence() -> None:
    first = _group("AAAA")
    second = _group("CCCC")
    decision = derive_m6_identity_decision(
        case_id="M6C001",
        selected_seed_results=(_seed(first, "sol_a"),),
        sequence_groups=(first, second),
    )
    raw = decision.model_dump(mode="json")
    raw["identity_decision_id"] = "m6identity_tampered"
    with pytest.raises(ValidationError, match="content identifier changed"):
        M6IdentityDecision.model_validate(raw)

    candidate = decision.candidates[0].model_dump(mode="json")
    pointer = candidate["evidence_pointers"][0]
    candidate["evidence_pointers"] = [pointer, pointer]
    with pytest.raises(ValidationError, match="unique and sorted"):
        M6IdentityCandidate.model_validate(candidate)

    with pytest.raises(ValueError, match="unknown sequence group"):
        derive_m6_identity_decision(
            case_id="M6C001",
            selected_seed_results=(
                {
                    "sequence_group_id": f"seq_{'f' * 64}",
                    "seed_solution_id": "sol_unknown",
                },
            ),
            sequence_groups=(first, second),
        )
    with pytest.raises(ValueError, match="conflicting identities"):
        derive_m6_identity_decision(
            case_id="M6C001",
            selected_seed_results=(
                _seed(first, "sol_same"),
                _seed(second, "sol_same"),
            ),
            sequence_groups=(first, second),
        )


def test_identity_evidence_digest_detects_a_mutated_selected_seed_row() -> None:
    group = _group("AAAA")
    selected = {
        **_seed(group, "sol_a"),
        "hypothesis_id": "mrhyp_a",
        "llg": 120.0,
    }
    decision = derive_m6_identity_decision(
        case_id="M6C001",
        selected_seed_results=(selected,),
        sequence_groups=(group,),
    )

    selected["llg"] = 121.0
    with pytest.raises(ValueError, match="does not match selected-seed evidence"):
        verify_m6_identity_decision_evidence(decision, (selected,))
    changed = derive_m6_identity_decision(
        case_id="M6C001",
        selected_seed_results=(selected,),
        sequence_groups=(group,),
    )
    assert changed.identity_decision_id != decision.identity_decision_id
    assert (
        changed.candidates[0].evidence_pointers[0].record_sha256
        != decision.candidates[0].evidence_pointers[0].record_sha256
    )


_OUTPUT_FILES = {
    "case_results": "m6_case_results.jsonl",
    "candidate_rankings": "m6_candidate_rankings.jsonl",
    "candidate_rankings_gzip": "m6_candidate_rankings.jsonl.gz",
    "model_policy_results": "m6_model_policy_results.jsonl",
    "first_copy_results": "m6_first_copy_results.jsonl",
    "additional_copy_results": "m6_additional_copy_results.jsonl",
    "refinement_results": "m6_refinement_results.jsonl",
    "sequence_results": "m6_sequence_results.jsonl",
    "sequence_summary": "m6_sequence_summary.jsonl",
}


def _scientific_output(
    root: Path,
    *,
    adapter_version: str,
    omit_identity_for: str | None = None,
) -> Path:
    output = root / adapter_version
    output.mkdir(parents=True)
    cases: list[dict[str, object]] = []
    for case_id in m6_track_case_ids("operational"):
        row: dict[str, object] = {
            "schema_version": (
                "2.0" if adapter_version == "m6-nextflow-run-v2" else "1.0"
            ),
            "adapter_version": (
                "m6-nextflow-case-evidence-v2"
                if adapter_version == "m6-nextflow-run-v2"
                else "m6-nextflow-case-evidence-v1"
            ),
            "case_id": case_id,
            "candidate_count": 0,
            "retained_candidate_count": 0,
            "all_candidates_retained": True,
            "candidate_ranking_path": None,
            "selected_seed_results": [],
        }
        if adapter_version == "m6-nextflow-run-v2" and case_id != omit_identity_for:
            row["identity_decision"] = derive_m6_identity_decision(
                case_id=case_id,
                selected_seed_results=(),
                sequence_groups=(),
            ).model_dump(mode="json")
            row["edge_observations"] = []
        cases.append(row)
    (output / _OUTPUT_FILES["case_results"]).write_text(
        "".join(f"{json.dumps(row, sort_keys=True)}\n" for row in cases),
        encoding="utf-8",
    )
    ranking_bytes = b""
    (output / _OUTPUT_FILES["candidate_rankings"]).write_bytes(ranking_bytes)
    (output / _OUTPUT_FILES["candidate_rankings_gzip"]).write_bytes(
        gzip.compress(ranking_bytes, compresslevel=9, mtime=0)
    )
    for key in (
        "model_policy_results",
        "first_copy_results",
        "additional_copy_results",
        "refinement_results",
        "sequence_results",
        "sequence_summary",
    ):
        (output / _OUTPUT_FILES[key]).write_text("", encoding="utf-8")
    output_sha256 = {
        key: sha256_file(output / filename) for key, filename in _OUTPUT_FILES.items()
    }
    input_sha256 = {
        "runner_manifest": "1" * 64,
        "protocol": "2" * 64,
        "database_manifest": "3" * 64,
        "phenix_manifest": "4" * 64,
    }
    summary = {
        "schema_version": ("2.0" if adapter_version == "m6-nextflow-run-v2" else "1.0"),
        "adapter_version": adapter_version,
        "track": "operational",
        "case_ids": list(m6_track_case_ids("operational")),
        "case_evidence_digest": canonical_digest(cases),
        "scientific_output_digest": canonical_digest(output_sha256),
        "input_sha256": input_sha256,
        "cache_key": canonical_digest(
            {
                "adapter_version": adapter_version,
                "track": "operational",
                "input_sha256": input_sha256,
            }
        ),
        "outputs": output_sha256,
        "execution_model": "nextflow_dsl2_slurm_fanout",
        "first_copy_attempt_count": 0,
        "additional_copy_attempt_count": 0,
        "refinement_attempt_count": 0,
        "sequence_assessment_count": 0,
    }
    (output / "m6_scientific_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output


def test_v2_verifier_requires_valid_identity_decisions_and_keeps_v1_readable(
    tmp_path: Path,
) -> None:
    v2 = _scientific_output(tmp_path, adapter_version="m6-nextflow-run-v2")
    report = json.loads(
        verify_m6_scientific_output(v2, "operational").read_text(encoding="utf-8")
    )
    assert report["schema_version"] == "2.0"
    assert report["adapter_version"] == "m6-nextflow-run-v2"

    v1 = _scientific_output(tmp_path, adapter_version="m6-nextflow-run-v1")
    legacy_report = json.loads(
        verify_m6_scientific_output(v1, "operational").read_text(encoding="utf-8")
    )
    assert legacy_report["adapter_version"] == "m6-nextflow-run-v1"

    first_case = m6_track_case_ids("operational")[0]
    missing = _scientific_output(
        tmp_path / "missing",
        adapter_version="m6-nextflow-run-v2",
        omit_identity_for=first_case,
    )
    with pytest.raises(
        PublicControlError,
        match=f"identity decision is invalid: {first_case}",
    ):
        verify_m6_scientific_output(missing, "operational")
