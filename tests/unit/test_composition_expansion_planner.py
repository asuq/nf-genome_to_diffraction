"""Focused tests for deterministic schema-v2 composition expansion planning."""

import json
from collections.abc import Iterable

import pytest
from pydantic import ValidationError

from genome_to_diffraction.ranking.composition import (
    ComponentExpansionInput,
    CompositionExpansionOutput,
    CompositionExpansionRequest,
    ExpansionEvidenceLevel,
    ParentExpansionInput,
    build_composition_expansion_plan,
)
from genome_to_diffraction.schemas.v2 import (
    ComponentIdentitySupport,
    ComponentPlacement,
    ComponentSpec,
    CompositionExpansionDepthPlan,
    CompositionState,
    CompositionSupportState,
    ExpansionDisposition,
)
from genome_to_diffraction.status import ExecutionStatus


def _sha(index: int) -> str:
    return f"{index:064x}"


def _component_specs(
    *,
    label: str,
    sequence_index: int,
    model_index: int,
    model_evidence_index: int | None = None,
) -> tuple[ComponentSpec, ...]:
    sequence_sha256 = _sha(sequence_index)
    return tuple(
        ComponentSpec.from_content(
            label=label,
            sequence_group_id=f"seq_{sequence_sha256}",
            sequence_sha256=sequence_sha256,
            model_id=f"model_{model_index}",
            model_sha256=_sha(model_index),
            requested_copy_count=copy_count,
            sequence_mass_da=20_000.0 + sequence_index,
            mass_evidence_sha256=_sha(500 + sequence_index),
            model_evidence_sha256=_sha(
                model_evidence_index
                if model_evidence_index is not None
                else 700 + model_index
            ),
        )
        for copy_count in range(1, 5)
    )


def _parent(rank: int) -> ParentExpansionInput:
    component = _component_specs(
        label="A",
        sequence_index=1,
        model_index=10 + rank,
    )[rank - 1]
    placement = ComponentPlacement.from_content(
        component_spec_id=component.component_spec_id,
        component_label=component.label,
        sequence_group_id=component.sequence_group_id,
        model_id=component.model_id,
        model_sha256=component.model_sha256,
        requested_copy_count=component.requested_copy_count,
        observed_copy_count=component.requested_copy_count,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        component_tfz=10.0 + rank,
        incremental_llg=100.0 + rank,
        packing_passed=True,
        coordinate_sha256=_sha(30 + rank),
        identity_support=ComponentIdentitySupport.SEQUENCE_EQUIVALENCE_GROUP,
    )
    state = CompositionState.from_content(
        crystal_id="crystal_1",
        diffraction_dataset_id="diffraction_1",
        diffraction_sha256=_sha(40),
        parent_state_id=None,
        depth=1,
        components=(component,),
        placements=(placement,),
        combined_coordinate_sha256=_sha(30 + rank),
        physical_mass_lower_da=10_000.0,
        physical_mass_upper_da=100_000.0,
        support_state=CompositionSupportState.PACKED,
    )
    return ParentExpansionInput(parent_rank=rank, state=state)


def _candidate(
    rank: int,
    sequence_index: int,
    *,
    parent: ParentExpansionInput,
    eligible: tuple[int, ...] = (1, 2, 3, 4),
    evidence: ExpansionEvidenceLevel | None = None,
    model_available: bool = True,
    model_identity_supported: bool = True,
    model_evidence_index: int | None = None,
) -> ComponentExpansionInput:
    return ComponentExpansionInput(
        parent_state_id=parent.state.state_id,
        candidate_rank=rank,
        component_specs=_component_specs(
            label="B",
            sequence_index=sequence_index,
            model_index=100 + sequence_index,
            model_evidence_index=model_evidence_index,
        ),
        physically_eligible_copy_counts=eligible,
        model_available=model_available,
        model_identity_supported=model_identity_supported,
        sds_page_evidence=evidence,
    )


def _selected_signature(
    output: CompositionExpansionOutput,
    *,
    parents: Iterable[ParentExpansionInput],
    candidates: Iterable[ComponentExpansionInput],
) -> tuple[tuple[int, int, int], ...]:
    parent_ranks = {parent.state.state_id: parent.parent_rank for parent in parents}
    components = {
        spec.component_spec_id: (
            candidate.candidate_rank,
            spec.requested_copy_count,
        )
        for candidate in candidates
        for spec in candidate.component_specs
    }
    return tuple(
        (
            parent_ranks[attempt.parent_state_id],
            *components[attempt.component_spec_id],
        )
        for attempt in output.selected_attempts
    )


def test_planner_orders_evidence_and_excludes_represented_sequence_groups() -> None:
    parent = _parent(1)
    represented = _candidate(
        1,
        1,
        parent=parent,
        evidence=ExpansionEvidenceLevel.SUPPORTING,
    )
    neutral = _candidate(2, 2, parent=parent)
    supporting = _candidate(
        3,
        3,
        parent=parent,
        evidence=ExpansionEvidenceLevel.SUPPORTING,
    )

    first = build_composition_expansion_plan(
        CompositionExpansionRequest(
            parents=(parent,),
            candidates=(neutral, represented, supporting),
        )
    )
    repeated = build_composition_expansion_plan(
        CompositionExpansionRequest(
            parents=(parent,),
            candidates=(supporting, neutral, represented),
        )
    )

    assert first == repeated
    plan = first.depth_plan
    assert plan.candidate_count == 8
    assert all(
        candidate.hypothesis.component.sequence_group_id
        != parent.state.components[0].sequence_group_id
        for candidate in plan.candidates
    )
    assert (
        tuple(
            candidate.hypothesis.component.sequence_group_id
            for candidate in plan.candidates[:4]
        )
        == (supporting.sequence_group_id,) * 4
    )
    assert tuple(
        candidate.hypothesis.component.requested_copy_count
        for candidate in plan.candidates[:4]
    ) == (1, 2, 3, 4)


def test_round_robin_is_fair_across_parents_candidates_and_copy_counts() -> None:
    parents = (_parent(1), _parent(2), _parent(3))
    candidates = tuple(
        _candidate(rank, sequence_index, parent=parent)
        for parent in parents
        for rank, sequence_index in ((1, 2), (2, 3))
    )
    output = build_composition_expansion_plan(
        CompositionExpansionRequest(
            parents=(parents[2], parents[0], parents[1]),
            candidates=candidates,
            per_depth_attempt_budget=9,
        )
    )

    assert _selected_signature(
        output,
        parents=parents,
        candidates=candidates,
    ) == (
        (1, 1, 1),
        (2, 1, 1),
        (3, 1, 1),
        (1, 1, 2),
        (2, 1, 2),
        (3, 1, 2),
        (1, 2, 1),
        (2, 2, 1),
        (3, 2, 1),
    )
    assert output.depth_plan.selected_attempt_count == 9
    assert all(
        candidate.hypothesis.disposition
        is not ExpansionDisposition.DEFERRED_GLOBAL_BUDGET
        for candidate in output.depth_plan.candidates
    )


def test_depth_and_global_budgets_have_distinct_retained_dispositions() -> None:
    parents = (_parent(1), _parent(2))
    candidates = tuple(
        _candidate(rank, sequence_index, parent=parent)
        for parent in parents
        for rank, sequence_index in ((1, 2), (2, 3))
    )
    depth_limited = build_composition_expansion_plan(
        CompositionExpansionRequest(
            parents=parents,
            candidates=candidates,
            per_depth_attempt_budget=5,
        )
    )
    global_limited = build_composition_expansion_plan(
        CompositionExpansionRequest(
            parents=parents,
            candidates=candidates,
            per_depth_attempt_budget=5,
            global_attempt_budget=100,
            global_attempts_used_before=98,
        )
    )

    assert len(depth_limited.selected_attempts) == 5
    assert len(global_limited.selected_attempts) == 2
    assert global_limited.remaining_global_attempt_budget == 0
    assert {
        candidate.hypothesis.disposition
        for candidate in depth_limited.depth_plan.candidates
        if candidate.hypothesis.disposition is not ExpansionDisposition.SELECTED
    } == {ExpansionDisposition.DEFERRED_DEPTH_BUDGET}
    assert {
        candidate.hypothesis.disposition
        for candidate in global_limited.depth_plan.candidates
        if candidate.hypothesis.disposition is not ExpansionDisposition.SELECTED
    } == {ExpansionDisposition.DEFERRED_GLOBAL_BUDGET}

    invalid_shared_budget = global_limited.depth_plan.model_dump(
        mode="python",
        exclude={"depth_plan_id"},
    )
    invalid_shared_budget["per_depth_attempt_budget"] = 1
    with pytest.raises(ValidationError, match="shared depth or global budget"):
        CompositionExpansionDepthPlan.from_content(**invalid_shared_budget)


def test_component_evidence_mutation_changes_content_identity_not_support() -> None:
    parent = _parent(1)
    original = _candidate(1, 2, parent=parent, model_evidence_index=900)
    mutated = _candidate(1, 2, parent=parent, model_evidence_index=901)
    first = build_composition_expansion_plan(
        CompositionExpansionRequest(parents=(parent,), candidates=(original,))
    )
    second = build_composition_expansion_plan(
        CompositionExpansionRequest(parents=(parent,), candidates=(mutated,))
    )

    assert first.depth_plan.depth_plan_id != second.depth_plan.depth_plan_id
    assert first.selected_attempts[0].component_spec_id != (
        second.selected_attempts[0].component_spec_id
    )
    assert first.depth_plan.selected_attempt_count == 4
    assert second.depth_plan.selected_attempt_count == 4
    assert all(
        candidate.hypothesis.disposition is ExpansionDisposition.SELECTED
        for candidate in first.depth_plan.candidates
    )
    assert all(
        "selection is not scientific support" in candidate.hypothesis.disposition_reason
        for candidate in first.depth_plan.candidates
    )

    mutated_payload = json.loads(first.depth_plan.model_dump_json())
    mutated_payload["candidates"][0]["parent_rank"] = 2
    with pytest.raises(ValidationError, match="depth_candidate_id"):
        CompositionExpansionDepthPlan.model_validate(mutated_payload)


def test_missing_ranking_evidence_is_explicitly_neutral() -> None:
    parent = _parent(1)
    missing = _candidate(1, 2, parent=parent)
    explicit_neutral = ComponentExpansionInput(
        parent_state_id=parent.state.state_id,
        candidate_rank=missing.candidate_rank,
        component_specs=missing.component_specs,
        physically_eligible_copy_counts=missing.physically_eligible_copy_counts,
        model_available=True,
        model_identity_supported=True,
        reviewer_allowed=True,
        localisation_evidence=ExpansionEvidenceLevel.NEUTRAL,
        sds_page_evidence=ExpansionEvidenceLevel.NEUTRAL,
        native_page_evidence=ExpansionEvidenceLevel.NEUTRAL,
        matthews_evidence=ExpansionEvidenceLevel.NEUTRAL,
        model_quality_evidence=ExpansionEvidenceLevel.NEUTRAL,
        structural_diversity_evidence=ExpansionEvidenceLevel.NEUTRAL,
    )

    missing_output = build_composition_expansion_plan(
        CompositionExpansionRequest(parents=(parent,), candidates=(missing,))
    )
    neutral_output = build_composition_expansion_plan(
        CompositionExpansionRequest(
            parents=(parent,),
            candidates=(explicit_neutral,),
        )
    )

    assert missing_output == neutral_output
    assert missing_output.depth_plan.selected_attempt_count == 4
    assert all(
        "sds_page:neutral" in candidate.hypothesis.disposition_reason
        for candidate in missing_output.depth_plan.candidates
    )


def test_no_physical_hypothesis_is_complete_without_scheduling() -> None:
    parent = _parent(1)
    impossible = _candidate(1, 2, parent=parent, eligible=())
    output = build_composition_expansion_plan(
        CompositionExpansionRequest(parents=(parent,), candidates=(impossible,))
    )

    assert output.depth_plan.physical_hypothesis_count == 0
    assert output.selected_attempts == ()
    assert output.remaining_global_attempt_budget == 100
    assert output.depth_plan.selected_attempt_count == 0
    assert output.depth_plan.deferred_candidate_count == 0
    assert output.depth_plan.unsearchable_candidate_count == 4
    assert {
        candidate.hypothesis.disposition for candidate in output.depth_plan.candidates
    } == {ExpansionDisposition.EXCLUDED_PHYSICAL_IMPOSSIBLE}
