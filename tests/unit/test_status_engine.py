"""T13.1 status derivation keeps execution and interpretation separate."""

import json
from dataclasses import replace
from pathlib import Path

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.review.status_engine import (
    StatusRequest,
    build_status_record,
)
from genome_to_diffraction.schemas.results import PrototypeAssumptionStatus
from genome_to_diffraction.status import ExecutionStatus, ScientificStatus

_DECISION_HEADER = (
    "checkpoint\titem_id\tdecision\treviewer\treviewed_at\tcomment\toverride_reason\n"
)


def _write_inputs(root: Path, decisions: str) -> StatusRequest:
    summary = root / "t12-summary.json"
    summary.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "gtd-t12-test",
                "candidate_count": 1,
                "completed_refinement_count": 1,
                "failed_refinement_count": 0,
                "completed_sequence_count": 1,
                "failed_sequence_count": 0,
                "all_candidates_retained": True,
            }
        ),
        encoding="utf-8",
    )
    job = root / "job-result.json"
    job.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "gtd-t12-test",
                "completed_at": "2026-08-15T07:33:27Z",
                "scheduler_state": "COMPLETED",
                "exit_code": 0,
                "failure_class": "success",
            }
        ),
        encoding="utf-8",
    )
    refinements = root / "t12-refinement-results.jsonl"
    refinements.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "refinement_id": "refine_test",
                "seed_solution_id": "sol_test",
                "sequence_group_id": "seq_seed",
                "input_copy_count": 2,
                "tool_version": "2.1-6048",
                "execution_status": "completed_success",
                "refined_model_path": "brief_refine_001.pdb",
                "refined_model_sha256": "1" * 64,
                "refined_mtz_path": "brief_refine_001.mtz",
                "refined_mtz_sha256": "2" * 64,
                "map_path": "brief_refine_2mFo-DFc.ccp4",
                "map_sha256": "3" * 64,
                "command_pointer": "t12_command.json",
                "raw_log_pointer": "phenix.refine.log",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    candidates = root / "sequence_approval_candidates.tsv"
    candidates.write_text(
        "sequence_group_id\tbest_candidate_rank\nseq_candidate\t1\n",
        encoding="utf-8",
    )
    checkpoint = root / "sequence_checkpoint_manifest.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "gtd-t12-test",
                "finalist_count": 1,
                "outputs": {candidates.name: sha256_file(candidates)},
            }
        ),
        encoding="utf-8",
    )
    decision_path = root / "approved_sequence_groups.tsv"
    decision_path.write_text(_DECISION_HEADER + decisions, encoding="utf-8")
    return StatusRequest(
        crystal_id="crystal_test",
        t12_summary_json=summary,
        job_result_json=job,
        refinement_results_jsonl=refinements,
        checkpoint_manifest_json=checkpoint,
        approval_candidates_tsv=candidates,
        decisions_tsv=decision_path,
        output_json=root / "scientific-status.json",
    )


def test_empty_decisions_preserve_success_without_scientific_promotion(
    tmp_path: Path,
) -> None:
    request = _write_inputs(tmp_path, "")

    record = build_status_record(request)

    assert record.execution_status is ExecutionStatus.COMPLETED_SUCCESS
    assert record.scientific_status is ScientificStatus.INSUFFICIENT_EVIDENCE
    assert record.prototype_assumption_status is PrototypeAssumptionStatus.UNKNOWN
    assert record.primary_sequence_groups == ()
    assert record.best_supported_copy_counts == {"sol_test": 2}
    assert set(record.warnings) == {
        "human_sequence_approval_pending",
        "prototype_assumption_not_assessed",
    }
    assert request.output_json.is_file()


def test_explicit_approval_and_consistent_assumption_enable_credible_status(
    tmp_path: Path,
) -> None:
    request = _write_inputs(
        tmp_path,
        "sequence_candidate\tseq_candidate\tapprove\treviewer\t"
        "2026-08-15T08:00:00Z\tReviewed in Coot\t\n",
    )
    request = replace(
        request,
        prototype_assumption_status=PrototypeAssumptionStatus.CONSISTENT,
    )

    record = build_status_record(request)

    assert record.execution_status is ExecutionStatus.COMPLETED_SUCCESS
    assert (
        record.scientific_status is ScientificStatus.CREDIBLE_SINGLE_COMPONENT_SOLUTION
    )
    assert record.primary_sequence_groups == ("seq_candidate",)
    assert record.warnings == ()
    assert record.completed_at.isoformat() == "2026-08-15T08:00:00+00:00"
