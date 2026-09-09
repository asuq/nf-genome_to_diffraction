"""Stage-specific metric regressions using explicitly synthetic inventories."""

from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.m6_collection import _edge_outcome_verified
from genome_to_diffraction.benchmarks.m6_evaluation import _positive_metrics
from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
from genome_to_diffraction.benchmarks.m6_stages import (
    M6StageInventory,
    M6StageRow,
    _copy_receipt,
    stage_counts,
)
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from tests.unit.test_m6_benchmark import (
    HASH,
    PROTOCOL,
    _evidence,
    _measured_edge_observation,
    _private_case,
    _stage_inventory,
)


def test_provider_rank_never_counts_as_scheduled_or_advanced() -> None:
    protocol = load_m6_protocol(PROTOCOL)
    cases = {case.case_id: case for case in protocol.cases}
    assessments = {item.case_id: item for item in _evidence(protocol).assessments}
    original = assessments["M6C001"]
    assessments["M6C001"] = original.model_copy(
        update={
            "stage_inventory": _stage_inventory("M6C001"),
            "target_provider_rank": 1,
            "target_scheduled_rank": None,
            "target_recommended_rank": None,
            "target_advanced_rank": None,
            "credible_seed_recovered": False,
            "supported_copy_count": None,
        }
    )
    metrics = _positive_metrics(
        protocol, cases, assessments, kind="operational_positive"
    )
    assert metrics["top_25"] == metrics["top_10"] == metrics["top_5"] == 11

    recommendation = original.stage_inventory.rows[0].model_copy(
        update={
            "advanced_rank": None,
            "continuation_receipt_sha256": None,
        }
    )
    stages = M6StageInventory(
        case_id="M6C001",
        hypotheses_sha256=HASH,
        benchmark_advancement_sha256=HASH,
        rows=(recommendation,),
        scheduled=stage_counts((recommendation,)),
        recommended=stage_counts((recommendation,)),
        advanced=stage_counts(()),
    )
    assessments["M6C001"] = original.model_copy(
        update={
            "stage_inventory": stages,
            "target_advanced_rank": None,
            "credible_seed_recovered": False,
            "supported_copy_count": None,
        }
    )
    metrics = _positive_metrics(
        protocol, cases, assessments, kind="operational_positive"
    )
    assert metrics["top_25"] == metrics["top_10"] == metrics["recommended_top_5"] == 12
    assert metrics["top_5"] == metrics["credible_seed"] == 11


def test_counts_keep_proteins_models_copy_states_and_tasks_distinct() -> None:
    base = _stage_inventory("M6C001", HASH).rows[0]
    rows = (
        base,
        base.model_copy(
            update={
                "hypothesis_id": "hyp_second_model",
                "solution_id": "sol_second_model",
                "model_id": "second_model",
                "scheduled_rank": 2,
                "review_priority_rank": 2,
                "recommendation_rank": None,
                "recommended": False,
                "advanced_rank": None,
                "continuation_receipt_sha256": None,
            }
        ),
        base.model_copy(
            update={
                "hypothesis_id": "hyp_second_copy",
                "solution_id": "sol_second_copy",
                "expected_copy_count": 2,
                "scheduled_rank": 3,
                "review_priority_rank": 3,
                "recommendation_rank": None,
                "recommended": False,
                "advanced_rank": None,
                "continuation_receipt_sha256": None,
            }
        ),
    )
    counts = stage_counts(rows)
    assert counts.unique_proteins == 1
    assert counts.unique_models == counts.expected_copy_states == 2
    assert counts.hypothesis_tasks == 3
    document = base.model_dump(mode="json")
    document["continuation_receipt_sha256"] = None
    with pytest.raises(ValueError, match="continuation receipt"):
        M6StageRow.model_validate(document)
    document = _stage_inventory("M6C001", HASH).model_dump(mode="json")
    document["scheduled"]["unique_proteins"] = 25
    with pytest.raises(ValueError, match="counts disagree"):
        M6StageInventory.model_validate(document)


def test_completed_parent_receipt_does_not_invent_a_native_copy_attempt(
    tmp_path: Path,
) -> None:
    task: dict[str, object] = {
        "case_id": "M6C001",
        "seed_solution_id": "seed_synthetic",
        "sequence_group_id": f"seq_{HASH}",
        "first_copy_placed_count": 1,
        "expected_copy_count": 1,
        "advancement_id": "m6advance_synthetic",
        "advancement_manifest_sha256": HASH,
    }
    (tmp_path / "best_parent.pdb").write_text("explicit synthetic coordinate receipt\n")
    parent_sha = sha256_file(tmp_path / "best_parent.pdb")
    authority = {
        "seed_solution_id": task["seed_solution_id"],
        "parent_retained": True,
        "execution_authority_kind": "truth_blind_m6_benchmark",
        "benchmark_advancement_id": task["advancement_id"],
        "benchmark_advancement_manifest_sha256": HASH,
        "human_approval_granted": False,
    }
    atomic_write_json(tmp_path / "seed_task.json", task)
    atomic_write_json(
        tmp_path / "best_parent.json",
        {
            **authority,
            "case_id": task["case_id"],
            "sequence_group_id": task["sequence_group_id"],
            "best_supported_copy_count": 1,
            "parent_coordinate_sha256": parent_sha,
        },
    )
    atomic_write_json(
        tmp_path / "additional_copy_series_summary.json",
        {
            **authority,
            "expected_copy_count": 1,
            "attempt_count": 0,
            "best_supported_copy_count": 1,
            "reached_expected_copy_count": True,
            "stop_reason": "first_copy_already_reached_expected_count",
        },
    )
    (tmp_path / "additional_copy_series_results.jsonl").write_text("")
    receipt, attempted = _copy_receipt(
        tmp_path,
        task=task,
        parent_sha256=parent_sha,
        parent_result_sha256=HASH,
        mtz_sha256=HASH,
    )
    assert len(receipt) == 64
    assert attempted == 0
    assert not (tmp_path / "series").exists()


def test_non_top_copy_edge_requires_scheduled_completed_execution() -> None:
    protocol = load_m6_protocol(PROTOCOL)
    case = next(case for case in protocol.cases if case.case_kind == "non_top_matthews")
    truth = _private_case(protocol, case.case_id)
    observations = (_measured_edge_observation(protocol, case.case_id),)
    assert not _edge_outcome_verified(
        case, truth, observations, _stage_inventory(case.case_id), ()
    )
    stages = _stage_inventory(case.case_id, truth.target_sequence_sha256[0])
    row = stages.rows[0].model_copy(
        update={"expected_copy_count": truth.expected_asu_copy_count}
    )
    stages = stages.model_copy(update={"rows": (row,)})
    result = {"hypothesis_id": row.hypothesis_id, "execution_status": "failed_parse"}
    assert not _edge_outcome_verified(
        case, truth, observations, stages, ({"result": result},)
    )
    result["execution_status"] = "completed_no_hit"
    assert _edge_outcome_verified(
        case, truth, observations, stages, ({"result": result},)
    )
