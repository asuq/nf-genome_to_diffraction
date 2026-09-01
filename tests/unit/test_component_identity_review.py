"""Component identity follows exact owned review, model, map, and human evidence."""

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import gemmi
import pytest
from pydantic import ValidationError

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.review import (
    ComponentIdentityReviewError,
    ComponentIdentityReviewRequest,
    CompositionDecisionReviewRequest,
    PhaseIIIReviewEvidenceSource,
    PhaseIIIReviewPackageRequest,
    build_component_sequence_review_evidence,
    build_composition_decision_review_evidence,
    build_phase3_review_package,
)
from genome_to_diffraction.schemas.results import (
    BriefRefinementResult,
    SequenceMapCandidate,
    SequenceMapResult,
)
from genome_to_diffraction.schemas.v2 import (
    ComponentIdentitySupport,
    ComponentPlacement,
    ComponentScopeDecision,
    ComponentScopeStatus,
    ComponentSpec,
    CompositionAssessment,
    CompositionClaimBoundary,
    CompositionScientificStatus,
    CompositionState,
    CompositionStopReason,
    CompositionSupportState,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecision,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
    ResidualContentState,
)
from genome_to_diffraction.status import ExecutionStatus

CRYSTAL = "3U7Q"
PARENT = "gtd-unknown-single-component-owned-public-control"
EXECUTION = f"phase3exec_{'a' * 64}"
REVIEWED_STATE = "solution_control_B"
CREATED_AT = datetime(2026, 8, 25, 20, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _ReviewCase:
    request: ComponentIdentityReviewRequest
    component: ComponentSpec
    decision_file: Path


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _write_map(path: Path) -> None:
    grid = gemmi.FloatGrid(4, 4, 4)
    grid.spacegroup = gemmi.find_spacegroup_by_name("P 1")
    grid.unit_cell = gemmi.UnitCell(40, 50, 60, 90, 90, 90)
    grid.fill(1.0)
    review_map = gemmi.Ccp4Map()
    review_map.grid = grid
    review_map.update_ccp4_header(2, True)
    review_map.write_ccp4_map(str(path))


def _case(
    root: Path,
    *,
    source_record_ids: tuple[str, ...] = ("HisH_locus",),
    malformed_map: bool = False,
    decision: PhaseIIIReviewDecisionValue = PhaseIIIReviewDecisionValue.APPROVE,
) -> _ReviewCase:
    source_root = root / "sources"
    source_root.mkdir(parents=True)
    model = source_root / "model.pdb"
    model.write_text(
        "ATOM      1  CA  GLY A   1      11.104  13.207   9.115"
        "  1.00 20.00           C\nEND\n",
        encoding="ascii",
    )
    combined = source_root / "combined.pdb"
    combined.write_text(model.read_text(encoding="ascii"), encoding="ascii")
    group_digest = _sha("HisH sequence")
    component = ComponentSpec.from_content(
        label="B",
        sequence_group_id=f"seq_{group_digest}",
        sequence_sha256=group_digest,
        model_id="model_HisH",
        model_sha256=sha256_file(model),
        requested_copy_count=2,
        sequence_mass_da=20_000.0,
        mass_evidence_sha256=_sha("mass"),
        model_evidence_sha256=_sha("model provenance"),
    )
    map_path = source_root / "review.ccp4"
    if malformed_map:
        map_path.write_bytes(b"placeholder is not density")
    else:
        _write_map(map_path)

    refinement = BriefRefinementResult(
        schema_version="1.0",
        refinement_id="refinement_B",
        seed_solution_id=REVIEWED_STATE,
        sequence_group_id=component.sequence_group_id,
        input_copy_count=component.requested_copy_count,
        tool_version="public-control-fixture",
        execution_status=ExecutionStatus.COMPLETED_SUCCESS,
        final_r_work=0.22,
        final_r_free=0.27,
        refined_model_path="refined.pdb",
        refined_model_sha256=_sha("refined model"),
        refined_mtz_path="refined.mtz",
        refined_mtz_sha256=_sha("refined MTZ"),
        map_path="review.ccp4",
        map_sha256=sha256_file(map_path),
        command_pointer="refinement-command.json",
        raw_log_pointer="refinement.log",
    )
    sequence = SequenceMapResult(
        schema_version="1.0",
        sequence_assessment_id="sequence_assessment_B",
        refinement_id=refinement.refinement_id,
        seed_solution_id=REVIEWED_STATE,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        tool_version="public-control-fixture",
        complete_catalogue_group_count=1,
        scored_group_count=1,
        candidates=(
            SequenceMapCandidate(
                schema_version="1.0",
                refinement_id=refinement.refinement_id,
                rank=1,
                sequence_group_id=component.sequence_group_id,
                sequence_length=100,
                raw_score=10,
                source_record_ids=source_record_ids,
            ),
        ),
        command_pointer="sequence-command.json",
        raw_log_pointer="sequence.log",
    )
    refinement_path = source_root / "refinement.json"
    sequence_path = source_root / "sequence.json"
    atomic_write_json(refinement_path, refinement.model_dump(mode="json"))
    atomic_write_json(sequence_path, sequence.model_dump(mode="json"))

    package_root = root / "package"
    package_root.mkdir()
    result = build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=PhaseIIIReviewCheckpoint.SEQUENCE,
            owned_parent_run_id=PARENT,
            parent_profile="unknown-single-component",
            parent_phase="phase3-pass1",
            execution_identity_id=EXECUTION,
            crystal_id=CRYSTAL,
            target_item_ids=(component.sequence_group_id,),
            created_at=CREATED_AT,
            input_root=source_root,
            evidence_sources=(
                PhaseIIIReviewEvidenceSource("component_model", model.name),
                PhaseIIIReviewEvidenceSource("combined_coordinates", combined.name),
                PhaseIIIReviewEvidenceSource("refinement_result", refinement_path.name),
                PhaseIIIReviewEvidenceSource("review_map", map_path.name),
                PhaseIIIReviewEvidenceSource("sequence_result", sequence_path.name),
            ),
            output_directory=package_root,
        )
    )
    decision_file = PhaseIIIReviewDecisionFile.from_content(
        checkpoint=PhaseIIIReviewCheckpoint.SEQUENCE,
        owned_parent_run_id=PARENT,
        review_package_id=result.review_package_id,
        review_package_manifest_sha256=sha256_file(result.manifest),
        decisions=(
            PhaseIIIReviewDecision(
                crystal_id=CRYSTAL,
                item_id=component.sequence_group_id,
                decision=decision,
                reviewer="public-control-reviewer",
                reviewed_at=CREATED_AT,
                reason="independently inspected complete sequence-map evidence",
            ),
        ),
    )
    decision_path = root / "approved_sequence.json"
    atomic_write_json(decision_path, decision_file.model_dump(mode="json"))

    return _ReviewCase(
        request=ComponentIdentityReviewRequest(
            component=component,
            crystal_id=CRYSTAL,
            owned_parent_run_id=PARENT,
            execution_identity_id=EXECUTION,
            reviewed_state_id=REVIEWED_STATE,
            review_package_directory=package_root,
            decision_file=decision_path,
            sequence_map_result=package_root / "evidence" / sequence_path.name,
            refinement_result=package_root / "evidence" / refinement_path.name,
            review_map=package_root / "evidence" / map_path.name,
        ),
        component=component,
        decision_file=decision_path,
    )


def _composition_request(
    case: _ReviewCase,
    *,
    decision: PhaseIIIReviewDecisionValue = PhaseIIIReviewDecisionValue.APPROVE,
) -> CompositionDecisionReviewRequest:
    root = case.request.review_package_directory.parent
    source_root = root / "sources"
    package_root = root / "composition-package"
    package_root.mkdir()
    result = build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=PhaseIIIReviewCheckpoint.COMPOSITION,
            owned_parent_run_id=PARENT,
            parent_profile="unknown-single-component",
            parent_phase="phase3-pass1",
            execution_identity_id=EXECUTION,
            crystal_id=CRYSTAL,
            target_item_ids=(REVIEWED_STATE,),
            created_at=CREATED_AT,
            input_root=source_root,
            evidence_sources=(
                PhaseIIIReviewEvidenceSource("component_model", "model.pdb"),
                PhaseIIIReviewEvidenceSource("combined_coordinates", "combined.pdb"),
                PhaseIIIReviewEvidenceSource("refinement_result", "refinement.json"),
                PhaseIIIReviewEvidenceSource("review_map", "review.ccp4"),
                PhaseIIIReviewEvidenceSource("sequence_result", "sequence.json"),
            ),
            output_directory=package_root,
        )
    )
    decision_file = PhaseIIIReviewDecisionFile.from_content(
        checkpoint=PhaseIIIReviewCheckpoint.COMPOSITION,
        owned_parent_run_id=PARENT,
        review_package_id=result.review_package_id,
        review_package_manifest_sha256=sha256_file(result.manifest),
        decisions=(
            PhaseIIIReviewDecision(
                crystal_id=CRYSTAL,
                item_id=REVIEWED_STATE,
                decision=decision,
                reviewer="public-control-reviewer",
                reviewed_at=CREATED_AT,
                reason="independently inspected complete component composition",
            ),
        ),
    )
    decision_path = root / "approved_composition.json"
    atomic_write_json(decision_path, decision_file.model_dump(mode="json"))
    return CompositionDecisionReviewRequest(
        components=(case.component,),
        crystal_id=CRYSTAL,
        owned_parent_run_id=PARENT,
        execution_identity_id=EXECUTION,
        reviewed_state_id=REVIEWED_STATE,
        review_package_directory=package_root,
        decision_file=decision_path,
        combined_coordinates=package_root / "evidence" / "combined.pdb",
        refinement_result=package_root / "evidence" / "refinement.json",
        review_map=package_root / "evidence" / "review.ccp4",
    )


def _placement(case: _ReviewCase) -> ComponentPlacement:
    evidence = build_component_sequence_review_evidence(case.request)
    return ComponentPlacement.from_content(
        component_spec_id=case.component.component_spec_id,
        component_label=case.component.label,
        sequence_group_id=case.component.sequence_group_id,
        model_id=case.component.model_id,
        model_sha256=case.component.model_sha256,
        requested_copy_count=case.component.requested_copy_count,
        observed_copy_count=case.component.requested_copy_count,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        component_tfz=12.1,
        incremental_llg=145.0,
        packing_passed=True,
        coordinate_sha256=_sha("observed component coordinates"),
        identity_support=evidence.derived_identity_support,
        sequence_review_evidence=evidence,
    )


@pytest.mark.parametrize(
    ("source_record_ids", "expected_support"),
    (
        (("HisH_locus",), ComponentIdentitySupport.EXACT_SEQUENCE),
        (
            ("HisH_locus_one", "HisH_locus_two"),
            ComponentIdentitySupport.SEQUENCE_EQUIVALENCE_GROUP,
        ),
    ),
)
def test_component_identity_requires_independent_owned_map_and_human_approval(
    tmp_path: Path,
    source_record_ids: tuple[str, ...],
    expected_support: ComponentIdentitySupport,
) -> None:
    case = _case(tmp_path, source_record_ids=source_record_ids)

    evidence = build_component_sequence_review_evidence(case.request)
    placement = _placement(case)

    assert placement.identity_support is expected_support
    assert placement.sequence_review_evidence == evidence
    assert evidence.derived_identity_support is expected_support


@pytest.mark.parametrize("mutation", ("crystal", "state", "owner", "execution"))
def test_component_review_rejects_cross_bound_ownership(
    tmp_path: Path,
    mutation: str,
) -> None:
    case = _case(tmp_path)
    changes = {
        "crystal": {"crystal_id": "another_crystal"},
        "state": {"reviewed_state_id": "another_state"},
        "owner": {"owned_parent_run_id": "gtd-unknown-single-component-another-run"},
        "execution": {"execution_identity_id": f"phase3exec_{'b' * 64}"},
    }[mutation]

    with pytest.raises(ComponentIdentityReviewError):
        build_component_sequence_review_evidence(replace(case.request, **changes))


def test_component_review_rejects_reviewer_nonapproval(tmp_path: Path) -> None:
    case = _case(tmp_path, decision=PhaseIIIReviewDecisionValue.NO_ASSIGNMENT)

    with pytest.raises(ComponentIdentityReviewError, match="human approval"):
        build_component_sequence_review_evidence(case.request)


def test_component_review_rejects_checksum_bound_placeholder_map(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, malformed_map=True)

    with pytest.raises(ComponentIdentityReviewError, match="map-supported"):
        build_component_sequence_review_evidence(case.request)


def test_component_review_rejects_forged_identity_promotion(tmp_path: Path) -> None:
    case = _case(
        tmp_path,
        source_record_ids=("HisH_locus_one", "HisH_locus_two"),
    )
    evidence = build_component_sequence_review_evidence(case.request)

    with pytest.raises(ValidationError, match="sequence approval differs"):
        ComponentPlacement.from_content(
            component_spec_id=case.component.component_spec_id,
            component_label=case.component.label,
            sequence_group_id=case.component.sequence_group_id,
            model_id=case.component.model_id,
            model_sha256=case.component.model_sha256,
            requested_copy_count=case.component.requested_copy_count,
            observed_copy_count=case.component.requested_copy_count,
            execution_status=ExecutionStatus.COMPLETED_HIT,
            component_tfz=5.1,
            incremental_llg=327.049,
            packing_passed=True,
            coordinate_sha256=_sha("wrong-B packed coordinates"),
            identity_support=ComponentIdentitySupport.EXACT_SEQUENCE,
            sequence_review_evidence=evidence,
        )


def test_composition_claim_requires_distinct_owned_component_reviews(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    placement = _placement(case)
    assert placement.sequence_review_evidence is not None
    sequence = placement.sequence_review_evidence
    composition = build_composition_decision_review_evidence(_composition_request(case))
    state = CompositionState.from_content(
        crystal_id=CRYSTAL,
        diffraction_dataset_id="diffraction_public_control",
        diffraction_sha256=_sha("control diffraction"),
        parent_state_id=None,
        depth=1,
        components=(case.component,),
        placements=(placement,),
        combined_coordinate_sha256=composition.combined_coordinate_sha256,
        combined_mtz_sha256=_sha("refined MTZ"),
        refinement_evidence_sha256=sequence.refinement_result_sha256,
        map_evidence_sha256=sequence.review_map_sha256,
        review_evidence_sha256=sequence.review_package_manifest_sha256,
        composition_decision_sha256=composition.decision_file_sha256,
        composition_review_evidence=composition,
        physical_mass_lower_da=39_000,
        physical_mass_upper_da=41_000,
        support_state=CompositionSupportState.COMPOSITION_SUPPORTED,
    )
    scope = ComponentScopeDecision.from_content(
        crystal_id=CRYSTAL,
        state_id=state.state_id,
        search_depth_reached=1,
        maximum_search_depth=6,
        validated_component_depth=3,
        total_additional_attempt_budget=100,
        total_additional_attempts_used=0,
        remaining_physical_hypothesis_count=0,
        retained_packed_state_count=1,
        state_support_state=CompositionSupportState.COMPOSITION_SUPPORTED,
        stop_reason=CompositionStopReason.NO_PHYSICALLY_POSSIBLE_REMAINING_COMPONENT,
        residual_content_state=ResidualContentState.NONE_DETECTED,
        scope_status=ComponentScopeStatus.WITHIN_VALIDATED_COMPONENT_DEPTH,
        claim_boundary=CompositionClaimBoundary.COMPLETE_COMPOSITION_REVIEW_ELIGIBLE,
        complete_composition_claim_eligible=True,
    )
    state_json = state.model_dump_json()
    assessment = CompositionAssessment.from_content(
        crystal_id=CRYSTAL,
        state_id=state.state_id,
        scope_decision=scope,
        execution_status=ExecutionStatus.COMPLETED_SUCCESS,
        state_support_state=CompositionSupportState.COMPOSITION_SUPPORTED,
        scientific_status=CompositionScientificStatus.COMPOSITION_SUPPORTED,
        complete_composition_claim_eligible=True,
        complete_composition_claimed=True,
        final_review_decision_sha256=composition.decision_file_sha256,
        composition_state_json=state_json,
        evidence_sha256={
            "composition_state": hashlib.sha256(state_json.encode()).hexdigest()
        },
    )

    assert assessment.complete_composition_claimed is True
    assert (
        CompositionAssessment.model_validate_json(assessment.model_dump_json())
        == assessment
    )


def test_composition_review_rejects_retained_partial_as_complete_approval(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    request = _composition_request(
        case,
        decision=PhaseIIIReviewDecisionValue.RETAIN_PARTIAL,
    )

    with pytest.raises(ComponentIdentityReviewError, match="human approval"):
        build_composition_decision_review_evidence(request)


@pytest.mark.parametrize("mutation", ("crystal", "state", "owner", "execution"))
def test_composition_review_rejects_cross_bound_ownership(
    tmp_path: Path,
    mutation: str,
) -> None:
    case = _case(tmp_path)
    request = _composition_request(case)
    changes = {
        "crystal": {"crystal_id": "another_crystal"},
        "state": {"reviewed_state_id": "another_state"},
        "owner": {"owned_parent_run_id": "gtd-unknown-single-component-another-run"},
        "execution": {"execution_identity_id": f"phase3exec_{'b' * 64}"},
    }[mutation]

    with pytest.raises(ComponentIdentityReviewError):
        build_composition_decision_review_evidence(replace(request, **changes))
