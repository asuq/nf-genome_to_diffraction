"""Focused validation and mutation tests for Phase III composition contracts."""

import json

import pytest
from pydantic import ValidationError

from genome_to_diffraction.schemas.results import (
    ComponentScopeDecision as ComponentScopeDecisionV1,
)
from genome_to_diffraction.schemas.results import (
    ComponentScopeStatus as ComponentScopeStatusV1,
)
from genome_to_diffraction.schemas.v2 import (
    ComponentIdentitySupport,
    ComponentPlacement,
    ComponentScopeDecision,
    ComponentScopeStatus,
    ComponentSpec,
    CompositionAssessment,
    CompositionCandidateHypothesis,
    CompositionClaimBoundary,
    CompositionExpansionPlan,
    CompositionScientificStatus,
    CompositionState,
    CompositionStopReason,
    CompositionSupportState,
    ExpansionDisposition,
    ResidualContentState,
)
from genome_to_diffraction.status import ExecutionStatus

HASHES = tuple(f"{index:x}" * 64 for index in range(1, 16))


def _component(
    label: str,
    digest: str,
    *,
    copies: int = 1,
) -> ComponentSpec:
    return ComponentSpec.from_content(
        label=label,
        sequence_group_id=f"seq_{digest}",
        sequence_sha256=digest,
        model_id=f"model_{label.lower()}",
        model_sha256=HASHES[10],
        requested_copy_count=copies,
        sequence_mass_da=20_000.0 + (100.0 * copies),
        mass_evidence_sha256=HASHES[11],
        model_evidence_sha256=HASHES[12],
    )


def _placement(
    component: ComponentSpec,
    *,
    packed: bool = True,
    identity_support: ComponentIdentitySupport = (
        ComponentIdentitySupport.SEQUENCE_EQUIVALENCE_GROUP
    ),
) -> ComponentPlacement:
    return ComponentPlacement.from_content(
        component_spec_id=component.component_spec_id,
        component_label=component.label,
        sequence_group_id=component.sequence_group_id,
        model_id=component.model_id,
        model_sha256=component.model_sha256,
        requested_copy_count=component.requested_copy_count,
        observed_copy_count=component.requested_copy_count,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        component_tfz=12.5,
        incremental_llg=145.0,
        packing_passed=packed,
        coordinate_sha256=HASHES[9],
        identity_support=identity_support,
    )


def test_component_mass_is_explicitly_exact_bounded_or_unavailable() -> None:
    common = {
        "label": "B",
        "sequence_group_id": f"seq_{HASHES[1]}",
        "sequence_sha256": HASHES[1],
        "model_id": "model_mass_forms",
        "model_sha256": HASHES[10],
        "requested_copy_count": 1,
        "mass_evidence_sha256": HASHES[11],
        "model_evidence_sha256": HASHES[12],
    }
    bounded = ComponentSpec.from_content(
        **common,
        sequence_mass_lower_da=19_900.0,
        sequence_mass_upper_da=20_100.0,
    )
    unavailable = ComponentSpec.from_content(
        **common,
        warnings=("sequence_mass_unavailable",),
    )

    assert bounded.sequence_mass_da is None
    assert bounded.sequence_mass_lower_da == 19_900.0
    assert bounded.sequence_mass_upper_da == 20_100.0
    assert unavailable.sequence_mass_da is None
    assert unavailable.sequence_mass_lower_da is None
    assert unavailable.sequence_mass_upper_da is None

    with pytest.raises(ValidationError, match="both exact and bounded"):
        ComponentSpec.from_content(
            **common,
            sequence_mass_da=20_000.0,
            sequence_mass_lower_da=19_900.0,
            sequence_mass_upper_da=20_100.0,
        )
    with pytest.raises(ValidationError, match="bounds must be supplied together"):
        ComponentSpec.from_content(
            **common,
            sequence_mass_lower_da=19_900.0,
        )
    with pytest.raises(ValidationError, match="mass lower bound exceeds"):
        ComponentSpec.from_content(
            **common,
            sequence_mass_lower_da=20_100.0,
            sequence_mass_upper_da=19_900.0,
        )
    with pytest.raises(ValidationError, match="requires sequence_mass_unavailable"):
        ComponentSpec.from_content(**common)


def _state(
    components: tuple[ComponentSpec, ...],
    placements: tuple[ComponentPlacement, ...],
    *,
    support_state: CompositionSupportState,
) -> CompositionState:
    review_or_higher = support_state in {
        CompositionSupportState.REVIEW_SUPPORTED,
        CompositionSupportState.COMPOSITION_SUPPORTED,
    }
    refined_or_higher = support_state in {
        CompositionSupportState.REFINED,
        CompositionSupportState.REVIEW_SUPPORTED,
        CompositionSupportState.COMPOSITION_SUPPORTED,
    }
    return CompositionState.from_content(
        crystal_id="crystal_1",
        diffraction_dataset_id="diffraction_1",
        diffraction_sha256=HASHES[0],
        parent_state_id=(None if len(components) == 1 else f"compstate_{HASHES[1]}"),
        depth=len(components),
        components=components,
        placements=placements,
        combined_coordinate_sha256=HASHES[2],
        combined_mtz_sha256=HASHES[3] if refined_or_higher else None,
        refinement_evidence_sha256=HASHES[4] if refined_or_higher else None,
        map_evidence_sha256=HASHES[5] if review_or_higher else None,
        review_evidence_sha256=HASHES[6] if review_or_higher else None,
        composition_decision_sha256=(
            HASHES[7]
            if support_state is CompositionSupportState.COMPOSITION_SUPPORTED
            else None
        ),
        physical_mass_lower_da=40_000.0,
        physical_mass_upper_da=90_000.0,
        support_state=support_state,
    )


def test_component_spec_is_content_addressed_and_frozen() -> None:
    component = _component("A", HASHES[0], copies=2)
    loaded = ComponentSpec.model_validate_json(component.model_dump_json())
    assert loaded == component
    assert component.component_spec_id.startswith("compspec_")

    mutated = json.loads(component.model_dump_json())
    mutated["requested_copy_count"] = 3
    with pytest.raises(ValidationError, match="component_spec_id"):
        ComponentSpec.model_validate(mutated)
    frozen_field = "requested_copy_count"
    with pytest.raises(ValidationError, match="frozen"):
        setattr(component, frozen_field, 3)


def test_component_placement_separates_packing_from_identity_support() -> None:
    component = _component("B", HASHES[1])
    wrong_b_search_evidence = _placement(
        component,
        identity_support=ComponentIdentitySupport.UNRESOLVED,
    )
    assert wrong_b_search_evidence.packing_passed is True
    assert (
        wrong_b_search_evidence.identity_support is ComponentIdentitySupport.UNRESOLVED
    )

    with pytest.raises(ValidationError, match="non-hit placement"):
        ComponentPlacement.from_content(
            component_spec_id=component.component_spec_id,
            component_label=component.label,
            sequence_group_id=component.sequence_group_id,
            model_id=component.model_id,
            model_sha256=component.model_sha256,
            requested_copy_count=1,
            observed_copy_count=1,
            execution_status=ExecutionStatus.COMPLETED_NO_HIT,
            component_tfz=5.1,
            incremental_llg=327.049,
            packing_passed=True,
            coordinate_sha256=HASHES[2],
            identity_support=ComponentIdentitySupport.UNRESOLVED,
        )


def test_composition_state_preserves_order_and_rejects_identity_mismatch() -> None:
    component_a = _component("A", HASHES[0])
    component_b = _component("B", HASHES[1])
    placement_a = _placement(component_a)
    placement_b = _placement(component_b)

    state_ab = _state(
        (component_a, component_b),
        (placement_a, placement_b),
        support_state=CompositionSupportState.PACKED,
    )
    state_ba = _state(
        (component_b, component_a),
        (placement_b, placement_a),
        support_state=CompositionSupportState.PACKED,
    )
    assert state_ab.state_id != state_ba.state_id
    assert tuple(component.label for component in state_ab.components) == ("A", "B")

    with pytest.raises(ValidationError, match="ordered placement identity"):
        _state(
            (component_b, component_a),
            (placement_a, placement_b),
            support_state=CompositionSupportState.PACKED,
        )


def test_composition_state_support_promotions_require_matching_evidence() -> None:
    component = _component("A", HASHES[0])
    unresolved = _placement(
        component,
        identity_support=ComponentIdentitySupport.UNRESOLVED,
    )
    search_evidence = _state(
        (component,),
        (unresolved,),
        support_state=CompositionSupportState.SEARCH_EVIDENCE_ONLY,
    )
    assert search_evidence.support_state is CompositionSupportState.SEARCH_EVIDENCE_ONLY

    with pytest.raises(ValidationError, match="map, review, or identity"):
        _state(
            (component,),
            (unresolved,),
            support_state=CompositionSupportState.REVIEW_SUPPORTED,
        )


def test_composition_state_accepts_arbitrary_ordered_component_lists() -> None:
    components = tuple(
        _component(label, digest)
        for label, digest in zip(
            ("A", "B", "C", "D"),
            HASHES[:4],
            strict=True,
        )
    )
    placements = tuple(_placement(component) for component in components)
    state = _state(
        components,
        placements,
        support_state=CompositionSupportState.PACKED,
    )
    assert state.depth == 4
    assert tuple(component.label for component in state.components) == (
        "A",
        "B",
        "C",
        "D",
    )


def test_expansion_plan_binds_ranking_inventory_and_budgets() -> None:
    parent = _component("A", HASHES[0])
    component_b = _component("B", HASHES[1], copies=2)
    component_c = _component("C", HASHES[2])
    candidate_b = CompositionCandidateHypothesis.from_content(
        component=component_b,
        rank=1,
        disposition=ExpansionDisposition.SELECTED,
        disposition_reason="highest deterministic rank within depth budget",
        physical_possible=True,
        model_available=True,
    )
    candidate_c = CompositionCandidateHypothesis.from_content(
        component=component_c,
        rank=2,
        disposition=ExpansionDisposition.DEFERRED_DEPTH_BUDGET,
        disposition_reason="per-depth attempt budget exhausted",
        physical_possible=True,
        model_available=True,
    )
    plan = CompositionExpansionPlan.from_content(
        crystal_id="crystal_1",
        parent_state_id=f"compstate_{HASHES[3]}",
        parent_depth=1,
        target_depth=2,
        parent_component_labels=(parent.label,),
        parent_sequence_group_ids=(parent.sequence_group_id,),
        maximum_component_depth=6,
        beam_width=3,
        per_depth_attempt_budget=1,
        global_attempt_budget=100,
        global_attempts_used_before=0,
        ranking_policy_version="phase3-round-robin-v1",
        candidate_count=2,
        selected_attempt_count=1,
        deferred_candidate_count=1,
        unsearchable_candidate_count=0,
        candidates=(candidate_b, candidate_c),
    )
    assert plan.selected_attempt_count == 1

    with pytest.raises(ValidationError, match="candidate ranks"):
        CompositionExpansionPlan.from_content(
            **{
                **plan.model_dump(
                    exclude={"plan_id", "candidates"},
                    mode="python",
                ),
                "candidates": (
                    candidate_b,
                    CompositionCandidateHypothesis.from_content(
                        component=component_c,
                        rank=3,
                        disposition=ExpansionDisposition.DEFERRED_DEPTH_BUDGET,
                        disposition_reason="per-depth attempt budget exhausted",
                        physical_possible=True,
                        model_available=True,
                    ),
                ),
            }
        )


def test_unassessed_physical_evidence_has_a_distinct_disposition() -> None:
    component = _component("B", HASHES[1])
    unassessed = CompositionCandidateHypothesis.from_content(
        component=component,
        rank=1,
        disposition=ExpansionDisposition.UNSEARCHABLE_PHYSICAL_EVIDENCE,
        disposition_reason="total-composition mass is unavailable",
        physical_assessed=False,
        physical_possible=False,
        model_available=True,
    )

    assert not unassessed.physical_assessed
    assert unassessed.disposition is ExpansionDisposition.UNSEARCHABLE_PHYSICAL_EVIDENCE
    with pytest.raises(ValidationError, match="requires its typed disposition"):
        CompositionCandidateHypothesis.from_content(
            component=component,
            rank=1,
            disposition=ExpansionDisposition.EXCLUDED_PHYSICAL_IMPOSSIBLE,
            disposition_reason="invalid unassessed impossibility",
            physical_assessed=False,
            physical_possible=False,
            model_available=True,
        )
    with pytest.raises(ValidationError, match=r"unsearchable physical.*was assessed"):
        CompositionCandidateHypothesis.from_content(
            component=component,
            rank=1,
            disposition=ExpansionDisposition.UNSEARCHABLE_PHYSICAL_EVIDENCE,
            disposition_reason="invalid assessed absence",
            physical_assessed=True,
            physical_possible=False,
            model_available=True,
        )


def test_expansion_plan_rejects_existing_sequence_group() -> None:
    parent = _component("A", HASHES[0])
    duplicate_group = _component("B", HASHES[0])
    candidate = CompositionCandidateHypothesis.from_content(
        component=duplicate_group,
        rank=1,
        disposition=ExpansionDisposition.SELECTED,
        disposition_reason="synthetic invalid duplicate",
        physical_possible=True,
        model_available=True,
    )
    with pytest.raises(ValidationError, match="already exists in parent"):
        CompositionExpansionPlan.from_content(
            crystal_id="crystal_1",
            parent_state_id=f"compstate_{HASHES[3]}",
            parent_depth=1,
            target_depth=2,
            parent_component_labels=(parent.label,),
            parent_sequence_group_ids=(parent.sequence_group_id,),
            maximum_component_depth=6,
            beam_width=3,
            per_depth_attempt_budget=25,
            global_attempt_budget=100,
            global_attempts_used_before=0,
            ranking_policy_version="phase3-round-robin-v1",
            candidate_count=1,
            selected_attempt_count=1,
            deferred_candidate_count=0,
            unsearchable_candidate_count=0,
            candidates=(candidate,),
        )


def test_scope_decision_prohibits_complete_claim_beyond_validated_depth() -> None:
    decision = ComponentScopeDecision.from_content(
        crystal_id="crystal_1",
        state_id=f"compstate_{HASHES[0]}",
        search_depth_reached=4,
        maximum_search_depth=6,
        validated_component_depth=3,
        total_additional_attempt_budget=100,
        total_additional_attempts_used=50,
        remaining_physical_hypothesis_count=8,
        retained_packed_state_count=0,
        state_support_state=CompositionSupportState.COMPOSITION_SUPPORTED,
        stop_reason=CompositionStopReason.NO_RETAINED_PACKED_STATE,
        residual_content_state=ResidualContentState.NONE_DETECTED,
        scope_status=(ComponentScopeStatus.PROVISIONAL_UNVALIDATED_COMPONENT_DEPTH),
        claim_boundary=(
            CompositionClaimBoundary.PROVISIONAL_UNVALIDATED_COMPONENT_DEPTH
        ),
        complete_composition_claim_eligible=False,
    )
    assert decision.complete_composition_claim_eligible is False

    mutated = decision.model_dump(mode="python", exclude={"decision_id"})
    mutated["complete_composition_claim_eligible"] = True
    with pytest.raises(ValidationError, match="claim eligibility"):
        ComponentScopeDecision.from_content(**mutated)


def test_assessment_requires_supported_status_and_final_review_for_claim() -> None:
    decision = ComponentScopeDecision.from_content(
        crystal_id="crystal_1",
        state_id=f"compstate_{HASHES[0]}",
        search_depth_reached=2,
        maximum_search_depth=6,
        validated_component_depth=3,
        total_additional_attempt_budget=100,
        total_additional_attempts_used=12,
        remaining_physical_hypothesis_count=0,
        retained_packed_state_count=1,
        state_support_state=CompositionSupportState.COMPOSITION_SUPPORTED,
        stop_reason=(CompositionStopReason.NO_PHYSICALLY_POSSIBLE_REMAINING_COMPONENT),
        residual_content_state=ResidualContentState.NONE_DETECTED,
        scope_status=ComponentScopeStatus.WITHIN_VALIDATED_COMPONENT_DEPTH,
        claim_boundary=(CompositionClaimBoundary.COMPLETE_COMPOSITION_REVIEW_ELIGIBLE),
        complete_composition_claim_eligible=True,
    )
    assessment = CompositionAssessment.from_content(
        crystal_id="crystal_1",
        state_id=decision.state_id,
        scope_decision=decision,
        execution_status=ExecutionStatus.COMPLETED_SUCCESS,
        state_support_state=CompositionSupportState.COMPOSITION_SUPPORTED,
        scientific_status=CompositionScientificStatus.COMPOSITION_SUPPORTED,
        complete_composition_claim_eligible=True,
        complete_composition_claimed=True,
        final_review_decision_sha256=HASHES[4],
        evidence_sha256={"composition_state": HASHES[5]},
    )
    assert assessment.complete_composition_claimed is True
    assert (
        CompositionAssessment.model_validate_json(assessment.model_dump_json())
        == assessment
    )

    with pytest.raises(ValidationError, match="final review"):
        CompositionAssessment.from_content(
            **{
                **assessment.model_dump(
                    mode="python",
                    exclude={"assessment_id", "final_review_decision_sha256"},
                ),
                "final_review_decision_sha256": None,
            }
        )


def test_v1_scope_evidence_remains_readable_and_separate_from_v2() -> None:
    legacy = ComponentScopeDecisionV1(
        schema_version="1.0",
        decision_id="legacy_scope",
        target_key="9ECN",
        crystal_id="9ECN",
        protocol_id="protocol_1",
        protocol_sha256=HASHES[0],
        observed_distinct_component_count=3,
        supported_distinct_component_count=2,
        status=ComponentScopeStatusV1.UNSUPPORTED_COMPONENT_COUNT,
        retain_partial_a_b_evidence=True,
        complete_composition_claim_eligible=False,
    )
    assert (
        ComponentScopeDecisionV1.model_validate_json(legacy.model_dump_json()) == legacy
    )
    legacy_field = "complete_composition_claim_eligible"
    with pytest.raises(ValidationError, match="frozen"):
        setattr(legacy, legacy_field, True)
    with pytest.raises(ValidationError):
        ComponentScopeDecision.model_validate_json(legacy.model_dump_json())
