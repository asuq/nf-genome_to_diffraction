"""Focused evidence-mutation tests for unknown-pass terminal assessments."""

import json

import pytest
from pydantic import ValidationError

from genome_to_diffraction.schemas.v2 import (
    UnknownPass1CrystalAssessment,
    UnknownPass1PanelSummary,
    UnknownPass1ResidualContentState,
    UnknownPass1ReviewEvidence,
    UnknownPass1ScientificStatus,
    UnknownPass1SolutionEvidence,
)
from genome_to_diffraction.schemas.v2.review import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecisionValue,
)
from genome_to_diffraction.status import ExecutionStatus

HASHES = tuple(f"{index:064x}" for index in range(1, 48))
EXECUTION_ID = f"phase3exec_{HASHES[0]}"
PARENT_RUN = "phase3_unknown_pass1"


def _review(
    checkpoint: PhaseIIIReviewCheckpoint,
    *,
    crystal_id: str,
    item_id: str,
    decision: PhaseIIIReviewDecisionValue,
    salt: int,
    package_crystal_id: str | None = None,
    decision_crystal_id: str | None = None,
    package_item_id: str | None = None,
    decision_item_id: str | None = None,
) -> UnknownPass1ReviewEvidence:
    return UnknownPass1ReviewEvidence(
        checkpoint=checkpoint,
        package_crystal_id=package_crystal_id or crystal_id,
        package_item_id=package_item_id or item_id,
        review_package_id=f"phase3reviewpkg_{HASHES[salt]}",
        review_package_manifest_sha256=HASHES[salt + 1],
        decision_crystal_id=decision_crystal_id or crystal_id,
        decision_item_id=decision_item_id or item_id,
        decision_file_id=f"phase3review_{HASHES[salt + 2]}",
        decision_file_sha256=HASHES[salt + 3],
        decision=decision,
    )


def _ordered_reviews(
    *items: UnknownPass1ReviewEvidence,
) -> tuple[UnknownPass1ReviewEvidence, ...]:
    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.checkpoint.value,
                item.package_crystal_id,
                item.package_item_id,
                item.decision_crystal_id,
                item.decision_item_id,
                item.review_package_id,
                item.decision_file_id,
            ),
        )
    )


def _crystallographic_review(
    crystal_id: str,
    *,
    decision: PhaseIIIReviewDecisionValue = PhaseIIIReviewDecisionValue.PROCEED,
) -> UnknownPass1ReviewEvidence:
    return _review(
        PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        crystal_id=crystal_id,
        item_id=f"{crystal_id}_mtz_review",
        decision=decision,
        salt=1,
    )


def _solution(
    default_crystal_id: str,
    *,
    residual: UnknownPass1ResidualContentState = (
        UnknownPass1ResidualContentState.NONE_DETECTED
    ),
    updates: dict[str, object] | None = None,
) -> UnknownPass1SolutionEvidence:
    values: dict[str, object] = {
        "crystal_id": default_crystal_id,
        "state_id": f"{default_crystal_id}_state_A",
        "sequence_group_id": f"seq_{HASHES[16]}",
        "requested_copy_count": 2,
        "observed_copy_count": 2,
        "copy_counts_supported": True,
        "copy_support_evidence_sha256": HASHES[10],
        "packing_passed": True,
        "packing_evidence_sha256": HASHES[11],
        "refinement_completed": True,
        "combined_coordinate_sha256": HASHES[12],
        "refined_coordinate_sha256": HASHES[39],
        "refined_mtz_sha256": HASHES[13],
        "review_map_sha256": HASHES[40],
        "refinement_evidence_sha256": HASHES[14],
        "sequence_evidence_sha256": HASHES[41],
        "final_r_work": 0.22,
        "final_r_free": 0.27,
        "parsed_final_metrics_evidence_sha256": HASHES[15],
        "residual_content_state": residual,
    }
    values.update(updates or {})
    return UnknownPass1SolutionEvidence.model_validate(values)


def _solution_reviews(
    crystal_id: str,
    state_id: str,
    *,
    composition_decision: PhaseIIIReviewDecisionValue,
) -> tuple[UnknownPass1ReviewEvidence, ...]:
    return _ordered_reviews(
        _crystallographic_review(crystal_id),
        _review(
            PhaseIIIReviewCheckpoint.A_SEED,
            crystal_id=crystal_id,
            item_id=state_id,
            decision=PhaseIIIReviewDecisionValue.APPROVE,
            salt=18,
        ),
        _review(
            PhaseIIIReviewCheckpoint.COMPOSITION,
            crystal_id=crystal_id,
            item_id=state_id,
            decision=composition_decision,
            salt=23,
        ),
        _review(
            PhaseIIIReviewCheckpoint.SEQUENCE,
            crystal_id=crystal_id,
            item_id=f"seq_{HASHES[16]}",
            decision=PhaseIIIReviewDecisionValue.APPROVE,
            salt=33,
        ),
    )


def _assessment(
    crystal_id: str,
    *,
    execution_status: ExecutionStatus,
    candidate_shortlist_present: bool,
    solution: UnknownPass1SolutionEvidence | None = None,
    reviews: tuple[UnknownPass1ReviewEvidence, ...] | None = None,
    parent_run: str = PARENT_RUN,
) -> UnknownPass1CrystalAssessment:
    return UnknownPass1CrystalAssessment.from_evidence(
        owned_parent_run_id=parent_run,
        execution_identity_id=EXECUTION_ID,
        crystal_id=crystal_id,
        crystallographic_review_item_id=f"{crystal_id}_mtz_review",
        execution_status=execution_status,
        terminal_evidence_sha256=HASHES[30],
        candidate_shortlist_present=candidate_shortlist_present,
        solution_evidence=solution,
        review_evidence=(
            reviews
            if reviews is not None
            else _ordered_reviews(_crystallographic_review(crystal_id))
        ),
    )


def _credible_assessment(crystal_id: str) -> UnknownPass1CrystalAssessment:
    solution = _solution(crystal_id)
    return _assessment(
        crystal_id,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        candidate_shortlist_present=True,
        solution=solution,
        reviews=_solution_reviews(
            crystal_id,
            solution.state_id,
            composition_decision=PhaseIIIReviewDecisionValue.APPROVE,
        ),
    )


def test_pass1_endpoint_vocabulary_is_exact() -> None:
    assert {status.value for status in UnknownPass1ScientificStatus} == {
        "credible_single_component_solution",
        "credible_partial_or_residual",
        "candidate_shortlist_no_credible_mr_solution",
        "no_supported_catalogue_candidate",
        "mtz_or_symmetry_review_required",
        "execution_failure",
        "insufficient_evidence",
    }


def test_credible_and_partial_statuses_require_matching_review_decisions() -> None:
    credible = _credible_assessment("AD4QS1P4G2_18")
    partial_solution = _solution(
        "CD4QS2P2G1_15",
        residual=UnknownPass1ResidualContentState.PRESENT_OR_SUSPECTED,
    )
    partial = _assessment(
        "CD4QS2P2G1_15",
        execution_status=ExecutionStatus.COMPLETED_HIT,
        candidate_shortlist_present=True,
        solution=partial_solution,
        reviews=_solution_reviews(
            "CD4QS2P2G1_15",
            partial_solution.state_id,
            composition_decision=PhaseIIIReviewDecisionValue.RETAIN_PARTIAL,
        ),
    )

    assert (
        credible.scientific_status
        is UnknownPass1ScientificStatus.CREDIBLE_SINGLE_COMPONENT_SOLUTION
    )
    assert (
        partial.scientific_status
        is UnknownPass1ScientificStatus.CREDIBLE_PARTIAL_OR_RESIDUAL
    )
    assert credible.assessment_id != partial.assessment_id


def test_solution_without_owned_sequence_review_cannot_be_credible() -> None:
    crystal_id = "AD4QS1P4G2_18"
    solution = _solution(crystal_id)
    reviews = tuple(
        item
        for item in _solution_reviews(
            crystal_id,
            solution.state_id,
            composition_decision=PhaseIIIReviewDecisionValue.APPROVE,
        )
        if item.checkpoint is not PhaseIIIReviewCheckpoint.SEQUENCE
    )

    assessment = _assessment(
        crystal_id,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        candidate_shortlist_present=True,
        solution=solution,
        reviews=reviews,
    )

    assert (
        assessment.scientific_status
        is UnknownPass1ScientificStatus.INSUFFICIENT_EVIDENCE
    )


@pytest.mark.parametrize("mutation", ("sequence-group", "crystal", "decision"))
def test_solution_rejects_unbound_or_unapproved_sequence_decisions(
    mutation: str,
) -> None:
    crystal_id = "AD4QS1P4G2_18"
    solution = _solution(crystal_id)
    reviews = list(
        _solution_reviews(
            crystal_id,
            solution.state_id,
            composition_decision=PhaseIIIReviewDecisionValue.APPROVE,
        )
    )
    sequence_index = next(
        index
        for index, item in enumerate(reviews)
        if item.checkpoint is PhaseIIIReviewCheckpoint.SEQUENCE
    )
    update: dict[str, object]
    if mutation == "sequence-group":
        other_group = f"seq_{HASHES[17]}"
        update = {"package_item_id": other_group, "decision_item_id": other_group}
    elif mutation == "crystal":
        update = {"decision_crystal_id": "another_crystal"}
    else:
        update = {"decision": PhaseIIIReviewDecisionValue.NO_ASSIGNMENT}
    reviews[sequence_index] = reviews[sequence_index].model_copy(update=update)

    assessment = _assessment(
        crystal_id,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        candidate_shortlist_present=True,
        solution=solution,
        reviews=_ordered_reviews(*reviews),
    )

    assert (
        assessment.scientific_status
        is UnknownPass1ScientificStatus.INSUFFICIENT_EVIDENCE
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"observed_copy_count": 1},
        {"copy_counts_supported": False},
        {"packing_passed": False},
        {"refinement_completed": False},
        {"final_r_free": None},
        {"refined_coordinate_sha256": None},
        {"review_map_sha256": None},
        {"sequence_evidence_sha256": None},
        {"crystal_id": "another_crystal"},
    ],
    ids=[
        "copy-mismatch",
        "copy-unassessed",
        "packing-failed",
        "refinement-incomplete",
        "final-metrics-missing",
        "refined-coordinates-missing",
        "review-map-missing",
        "sequence-evidence-missing",
        "crystal-mismatch",
    ],
)
def test_incomplete_or_mismatched_solution_evidence_never_promotes(
    updates: dict[str, object],
) -> None:
    crystal_id = "AD4QS1P4G2_18"
    solution = _solution(crystal_id, updates=updates)
    assessment = _assessment(
        crystal_id,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        candidate_shortlist_present=True,
        solution=solution,
        reviews=_solution_reviews(
            crystal_id,
            solution.state_id,
            composition_decision=PhaseIIIReviewDecisionValue.APPROVE,
        ),
    )

    assert (
        assessment.scientific_status
        is UnknownPass1ScientificStatus.INSUFFICIENT_EVIDENCE
    )


def test_mismatched_or_missing_review_evidence_never_promotes() -> None:
    crystal_id = "AD4QS1P4G2_18"
    solution = _solution(crystal_id)
    reviews = list(
        _solution_reviews(
            crystal_id,
            solution.state_id,
            composition_decision=PhaseIIIReviewDecisionValue.APPROVE,
        )
    )
    composition_index = next(
        index
        for index, evidence in enumerate(reviews)
        if evidence.checkpoint is PhaseIIIReviewCheckpoint.COMPOSITION
    )
    mutated = reviews[composition_index].model_copy(
        update={"decision_crystal_id": "another_crystal"}
    )
    reviews[composition_index] = mutated
    mismatch = _assessment(
        crystal_id,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        candidate_shortlist_present=True,
        solution=solution,
        reviews=_ordered_reviews(*reviews),
    )
    missing = _assessment(
        crystal_id,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        candidate_shortlist_present=True,
        solution=solution,
        reviews=tuple(
            item
            for item in _solution_reviews(
                crystal_id,
                solution.state_id,
                composition_decision=PhaseIIIReviewDecisionValue.APPROVE,
            )
            if item.checkpoint is not PhaseIIIReviewCheckpoint.COMPOSITION
        ),
    )

    assert (
        mismatch.scientific_status is UnknownPass1ScientificStatus.INSUFFICIENT_EVIDENCE
    )
    assert (
        missing.scientific_status is UnknownPass1ScientificStatus.INSUFFICIENT_EVIDENCE
    )


def test_hold_no_hit_and_completed_shortlist_are_distinct_scientific_endpoints() -> (
    None
):
    held_crystal = "CD4QS2P2G1_15"
    held = _assessment(
        held_crystal,
        execution_status=ExecutionStatus.SKIPPED_POLICY,
        candidate_shortlist_present=False,
        reviews=_ordered_reviews(
            _crystallographic_review(
                held_crystal,
                decision=PhaseIIIReviewDecisionValue.HOLD,
            )
        ),
    )
    no_hit = _assessment(
        "CD6QS2P2G1_5",
        execution_status=ExecutionStatus.COMPLETED_NO_HIT,
        candidate_shortlist_present=False,
    )
    shortlist = _assessment(
        "AD4QS1P4G2_18",
        execution_status=ExecutionStatus.COMPLETED_SUCCESS,
        candidate_shortlist_present=True,
    )

    assert (
        held.scientific_status
        is UnknownPass1ScientificStatus.MTZ_OR_SYMMETRY_REVIEW_REQUIRED
    )
    assert no_hit.execution_status is ExecutionStatus.COMPLETED_NO_HIT
    assert (
        no_hit.scientific_status
        is UnknownPass1ScientificStatus.NO_SUPPORTED_CATALOGUE_CANDIDATE
    )
    assert (
        shortlist.scientific_status
        is UnknownPass1ScientificStatus.CANDIDATE_SHORTLIST_NO_CREDIBLE_MR_SOLUTION
    )


@pytest.mark.parametrize(
    "execution_status",
    [
        ExecutionStatus.FAILED_TOOL_EXECUTION,
        ExecutionStatus.FAILED_PARSE,
        ExecutionStatus.FAILED_INFRASTRUCTURE,
    ],
)
def test_tool_parse_and_infrastructure_failures_remain_execution_failures(
    execution_status: ExecutionStatus,
) -> None:
    assessment = _assessment(
        "CD6QS2P2G1_5",
        execution_status=execution_status,
        candidate_shortlist_present=False,
        reviews=(),
    )
    assert (
        assessment.scientific_status is UnknownPass1ScientificStatus.EXECUTION_FAILURE
    )


def test_mixed_three_crystal_panel_finalises_without_sibling_promotion() -> None:
    credible = _credible_assessment("AD4QS1P4G2_18")
    no_hit = _assessment(
        "CD4QS2P2G1_15",
        execution_status=ExecutionStatus.COMPLETED_NO_HIT,
        candidate_shortlist_present=False,
    )
    parse_failure = _assessment(
        "CD6QS2P2G1_5",
        execution_status=ExecutionStatus.FAILED_PARSE,
        candidate_shortlist_present=False,
        reviews=(),
    )

    panel = UnknownPass1PanelSummary.from_assessments((parse_failure, credible, no_hit))
    by_crystal = {item.crystal_id: item for item in panel.assessments}

    assert panel.panel_status == "terminal_complete"
    assert (
        by_crystal["AD4QS1P4G2_18"].scientific_status
        is UnknownPass1ScientificStatus.CREDIBLE_SINGLE_COMPONENT_SOLUTION
    )
    assert (
        by_crystal["CD4QS2P2G1_15"].scientific_status
        is UnknownPass1ScientificStatus.NO_SUPPORTED_CATALOGUE_CANDIDATE
    )
    assert (
        by_crystal["CD6QS2P2G1_5"].scientific_status
        is UnknownPass1ScientificStatus.EXECUTION_FAILURE
    )
    assert len({item.scientific_status for item in panel.assessments}) == 3


def test_content_mutation_and_cross_run_panel_are_rejected() -> None:
    assessment = _credible_assessment("AD4QS1P4G2_18")
    mutated = json.loads(assessment.model_dump_json())
    mutated["terminal_evidence_sha256"] = HASHES[31]
    with pytest.raises(ValidationError, match="assessment_id"):
        UnknownPass1CrystalAssessment.model_validate(mutated)

    no_hit = _assessment(
        "CD4QS2P2G1_15",
        execution_status=ExecutionStatus.COMPLETED_NO_HIT,
        candidate_shortlist_present=False,
    )
    other_run_failure = _assessment(
        "CD6QS2P2G1_5",
        execution_status=ExecutionStatus.FAILED_TOOL_EXECUTION,
        candidate_shortlist_present=False,
        reviews=(),
        parent_run="different_parent_run",
    )
    with pytest.raises(ValidationError, match="share one owned execution"):
        UnknownPass1PanelSummary.from_assessments(
            (assessment, no_hit, other_run_failure)
        )
