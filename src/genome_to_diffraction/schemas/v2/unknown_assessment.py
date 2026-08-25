"""Crystal-bound terminal statuses for Phase III unknown-pass 1.

These records execute no tools.  They content-bind terminal execution evidence,
potential single-component solution evidence, and exact human review package and
decision identities.  Promotion requires complete evidence for the same crystal and
state.  Missing or mismatched evidence becomes ``insufficient_evidence``; scientific
no-hit remains completion and classified execution failures remain failures.

``UnknownPass1PanelSummary`` embeds exactly three independent assessments and has no
panel-wide scientific status, preventing a successful sibling from promoting another
crystal.  The canonical cache keys are ``assessment_id`` and ``panel_id``.
"""

from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.schemas.base import (
    ContractModel,
    OperatorIdentifier,
    Sha256Hex,
)
from genome_to_diffraction.schemas.v2.composition import (
    SequenceGroupIdentifier,
    _ContentAddressedContract,
)
from genome_to_diffraction.schemas.v2.execution import ExecutionIdentityIdentifier
from genome_to_diffraction.schemas.v2.review import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecisionFileIdentifier,
    PhaseIIIReviewDecisionValue,
    PhaseIIIReviewPackageIdentifier,
)
from genome_to_diffraction.status import ExecutionStatus

UnknownPass1AssessmentIdentifier = Annotated[
    str, Field(pattern=r"^unknownpass1assessment_[a-f0-9]{64}$")
]
UnknownPass1PanelIdentifier = Annotated[
    str, Field(pattern=r"^unknownpass1panel_[a-f0-9]{64}$")
]


class UnknownPass1ScientificStatus(StrEnum):
    """Exact approved Phase III pass-1 endpoint vocabulary."""

    CREDIBLE_SINGLE_COMPONENT_SOLUTION = "credible_single_component_solution"
    CREDIBLE_PARTIAL_OR_RESIDUAL = "credible_partial_or_residual"
    CANDIDATE_SHORTLIST_NO_CREDIBLE_MR_SOLUTION = (
        "candidate_shortlist_no_credible_mr_solution"
    )
    NO_SUPPORTED_CATALOGUE_CANDIDATE = "no_supported_catalogue_candidate"
    MTZ_OR_SYMMETRY_REVIEW_REQUIRED = "mtz_or_symmetry_review_required"
    EXECUTION_FAILURE = "execution_failure"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class UnknownPass1ResidualContentState(StrEnum):
    """Residual-content interpretation after reviewed refinement."""

    NONE_DETECTED = "none_detected"
    PRESENT_OR_SUSPECTED = "present_or_suspected"
    UNASSESSED = "unassessed"


class UnknownPass1TerminalEvidence(ContractModel):
    """One owned scientific terminal record before assessment interpretation."""

    schema_version: Literal["2.0"]
    owned_parent_run_id: OperatorIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    crystal_id: OperatorIdentifier
    execution_status: ExecutionStatus
    candidate_shortlist_present: bool
    state_id: OperatorIdentifier | None = None
    sequence_group_id: SequenceGroupIdentifier | None = None

    @model_validator(mode="after")
    def _validate_solution_identity(self) -> Self:
        if (self.state_id is None) != (self.sequence_group_id is None):
            raise ValueError("terminal state and sequence identities must be paired")
        return self


class UnknownPass1FinalMetricsEvidence(ContractModel):
    """Independently owned final metrics and reviewed residual interpretation."""

    schema_version: Literal["2.0"]
    owned_parent_run_id: OperatorIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    crystal_id: OperatorIdentifier
    state_id: OperatorIdentifier
    sequence_group_id: SequenceGroupIdentifier
    refinement_id: OperatorIdentifier
    final_r_work: Annotated[float, Field(ge=0, le=1)]
    final_r_free: Annotated[float, Field(ge=0, le=1)]
    residual_content_state: UnknownPass1ResidualContentState


class UnknownPass1ReviewEvidence(ContractModel):
    """One review package/decision pair with both sides' crystal binding."""

    checkpoint: PhaseIIIReviewCheckpoint
    package_crystal_id: OperatorIdentifier
    package_item_id: OperatorIdentifier
    review_package_id: PhaseIIIReviewPackageIdentifier
    review_package_manifest_sha256: Sha256Hex
    decision_crystal_id: OperatorIdentifier
    decision_item_id: OperatorIdentifier
    decision_file_id: PhaseIIIReviewDecisionFileIdentifier
    decision_file_sha256: Sha256Hex
    decision: PhaseIIIReviewDecisionValue


class UnknownPass1SolutionEvidence(ContractModel):
    crystal_id: OperatorIdentifier
    state_id: OperatorIdentifier
    sequence_group_id: SequenceGroupIdentifier
    requested_copy_count: Annotated[int, Field(gt=0, le=4)] | None = None
    observed_copy_count: Annotated[int, Field(ge=0, le=4)] | None = None
    copy_counts_supported: bool
    copy_support_evidence_sha256: Sha256Hex | None = None
    packing_passed: bool
    packing_evidence_sha256: Sha256Hex | None = None
    refinement_completed: bool
    combined_coordinate_sha256: Sha256Hex | None = None
    refined_coordinate_sha256: Sha256Hex | None = None
    refined_mtz_sha256: Sha256Hex | None = None
    review_map_sha256: Sha256Hex | None = None
    refinement_evidence_sha256: Sha256Hex | None = None
    sequence_evidence_sha256: Sha256Hex | None = None
    final_r_work: Annotated[float, Field(ge=0, le=1)] | None = None
    final_r_free: Annotated[float, Field(ge=0, le=1)] | None = None
    parsed_final_metrics_evidence_sha256: Sha256Hex | None = None
    residual_content_state: UnknownPass1ResidualContentState


_FAILURE_STATUSES = frozenset(
    {
        ExecutionStatus.FAILED_INPUT_CONTRACT,
        ExecutionStatus.FAILED_TOOL_EXECUTION,
        ExecutionStatus.FAILED_PARSE,
        ExecutionStatus.FAILED_INFRASTRUCTURE,
    }
)


def _has_one_review(
    evidence: tuple[UnknownPass1ReviewEvidence, ...],
    *,
    checkpoint: PhaseIIIReviewCheckpoint,
    crystal_id: str,
    item_id: str,
    decision: PhaseIIIReviewDecisionValue,
) -> bool:
    matches = tuple(
        item
        for item in evidence
        if item.checkpoint is checkpoint
        and item.package_crystal_id == crystal_id
        and item.decision_crystal_id == crystal_id
        and item.package_item_id == item_id
        and item.decision_item_id == item_id
    )
    return len(matches) == 1 and matches[0].decision is decision


def _solution_can_promote(
    *,
    crystal_id: str,
    solution: UnknownPass1SolutionEvidence,
    reviews: tuple[UnknownPass1ReviewEvidence, ...],
) -> bool:
    requested = solution.requested_copy_count
    observed = solution.observed_copy_count
    copies_supported = (
        requested is not None
        and observed is not None
        and requested == observed
        and solution.copy_counts_supported
        and solution.copy_support_evidence_sha256 is not None
    )
    packed = solution.packing_passed and solution.packing_evidence_sha256 is not None
    refined = (
        solution.refinement_completed
        and solution.combined_coordinate_sha256 is not None
        and solution.refined_coordinate_sha256 is not None
        and solution.refined_mtz_sha256 is not None
        and solution.review_map_sha256 is not None
        and solution.refinement_evidence_sha256 is not None
        and solution.sequence_evidence_sha256 is not None
        and solution.final_r_work is not None
        and solution.final_r_free is not None
        and solution.parsed_final_metrics_evidence_sha256 is not None
    )
    seed_approved = _has_one_review(
        reviews,
        checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
        crystal_id=crystal_id,
        item_id=solution.state_id,
        decision=PhaseIIIReviewDecisionValue.APPROVE,
    )
    sequence_approved = _has_one_review(
        reviews,
        checkpoint=PhaseIIIReviewCheckpoint.SEQUENCE,
        crystal_id=crystal_id,
        item_id=solution.sequence_group_id,
        decision=PhaseIIIReviewDecisionValue.APPROVE,
    )
    return (
        solution.crystal_id == crystal_id
        and copies_supported
        and packed
        and refined
        and seed_approved
        and sequence_approved
    )


def _derive_status(
    *,
    crystal_id: str,
    crystallographic_item_id: str,
    execution_status: ExecutionStatus,
    shortlist_present: bool,
    solution: UnknownPass1SolutionEvidence | None,
    reviews: tuple[UnknownPass1ReviewEvidence, ...],
) -> UnknownPass1ScientificStatus:
    if execution_status in _FAILURE_STATUSES:
        return UnknownPass1ScientificStatus.EXECUTION_FAILURE
    if _has_one_review(
        reviews,
        checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        crystal_id=crystal_id,
        item_id=crystallographic_item_id,
        decision=PhaseIIIReviewDecisionValue.HOLD,
    ):
        return UnknownPass1ScientificStatus.MTZ_OR_SYMMETRY_REVIEW_REQUIRED
    if not _has_one_review(
        reviews,
        checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        crystal_id=crystal_id,
        item_id=crystallographic_item_id,
        decision=PhaseIIIReviewDecisionValue.PROCEED,
    ):
        return UnknownPass1ScientificStatus.INSUFFICIENT_EVIDENCE

    if execution_status is ExecutionStatus.COMPLETED_NO_HIT:
        if solution is None and not shortlist_present:
            return UnknownPass1ScientificStatus.NO_SUPPORTED_CATALOGUE_CANDIDATE
        return UnknownPass1ScientificStatus.INSUFFICIENT_EVIDENCE
    if solution is None:
        if (
            execution_status
            in {
                ExecutionStatus.COMPLETED_SUCCESS,
                ExecutionStatus.COMPLETED_WARNING,
            }
            and shortlist_present
        ):
            return (
                UnknownPass1ScientificStatus.CANDIDATE_SHORTLIST_NO_CREDIBLE_MR_SOLUTION
            )
        return UnknownPass1ScientificStatus.INSUFFICIENT_EVIDENCE
    if (
        execution_status
        not in {ExecutionStatus.COMPLETED_SUCCESS, ExecutionStatus.COMPLETED_HIT}
        or not shortlist_present
        or not _solution_can_promote(
            crystal_id=crystal_id,
            solution=solution,
            reviews=reviews,
        )
    ):
        return UnknownPass1ScientificStatus.INSUFFICIENT_EVIDENCE

    approved = _has_one_review(
        reviews,
        checkpoint=PhaseIIIReviewCheckpoint.COMPOSITION,
        crystal_id=crystal_id,
        item_id=solution.state_id,
        decision=PhaseIIIReviewDecisionValue.APPROVE,
    )
    retained_partial = _has_one_review(
        reviews,
        checkpoint=PhaseIIIReviewCheckpoint.COMPOSITION,
        crystal_id=crystal_id,
        item_id=solution.state_id,
        decision=PhaseIIIReviewDecisionValue.RETAIN_PARTIAL,
    )
    if approved and (
        solution.residual_content_state
        is UnknownPass1ResidualContentState.NONE_DETECTED
    ):
        return UnknownPass1ScientificStatus.CREDIBLE_SINGLE_COMPONENT_SOLUTION
    if retained_partial and (
        solution.residual_content_state
        is UnknownPass1ResidualContentState.PRESENT_OR_SUSPECTED
    ):
        return UnknownPass1ScientificStatus.CREDIBLE_PARTIAL_OR_RESIDUAL
    return UnknownPass1ScientificStatus.INSUFFICIENT_EVIDENCE


class UnknownPass1CrystalAssessment(_ContentAddressedContract):
    """One evidence-derived terminal assessment for one crystal."""

    _identity_field: ClassVar[str] = "assessment_id"
    _identity_prefix: ClassVar[str] = "unknownpass1assessment_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["unknown-pass1-terminal-assessment-v2"]
    assessment_id: UnknownPass1AssessmentIdentifier
    owned_parent_run_id: OperatorIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    crystal_id: OperatorIdentifier
    crystallographic_review_item_id: OperatorIdentifier
    execution_status: ExecutionStatus
    terminal_evidence_sha256: Sha256Hex
    candidate_shortlist_present: bool
    solution_evidence: UnknownPass1SolutionEvidence | None = None
    review_evidence: tuple[UnknownPass1ReviewEvidence, ...] = ()
    scientific_status: UnknownPass1ScientificStatus

    @classmethod
    def from_evidence(
        cls,
        *,
        owned_parent_run_id: str,
        execution_identity_id: str,
        crystal_id: str,
        crystallographic_review_item_id: str,
        execution_status: ExecutionStatus,
        terminal_evidence_sha256: str,
        candidate_shortlist_present: bool,
        solution_evidence: UnknownPass1SolutionEvidence | None = None,
        review_evidence: tuple[UnknownPass1ReviewEvidence, ...] = (),
    ) -> Self:
        """Derive the endpoint and construct its canonical content identifier."""

        status = _derive_status(
            crystal_id=crystal_id,
            crystallographic_item_id=crystallographic_review_item_id,
            execution_status=execution_status,
            shortlist_present=candidate_shortlist_present,
            solution=solution_evidence,
            reviews=review_evidence,
        )
        return cls.from_content(
            adapter_version="unknown-pass1-terminal-assessment-v2",
            owned_parent_run_id=owned_parent_run_id,
            execution_identity_id=execution_identity_id,
            crystal_id=crystal_id,
            crystallographic_review_item_id=crystallographic_review_item_id,
            execution_status=execution_status,
            terminal_evidence_sha256=terminal_evidence_sha256,
            candidate_shortlist_present=candidate_shortlist_present,
            solution_evidence=solution_evidence,
            review_evidence=review_evidence,
            scientific_status=status,
        )

    @model_validator(mode="after")
    def _validate_assessment(self) -> Self:
        keys = tuple(
            (
                item.checkpoint.value,
                item.package_crystal_id,
                item.package_item_id,
                item.decision_crystal_id,
                item.decision_item_id,
                item.review_package_id,
                item.decision_file_id,
            )
            for item in self.review_evidence
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("review evidence must be unique and canonically sorted")
        expected = _derive_status(
            crystal_id=self.crystal_id,
            crystallographic_item_id=self.crystallographic_review_item_id,
            execution_status=self.execution_status,
            shortlist_present=self.candidate_shortlist_present,
            solution=self.solution_evidence,
            reviews=self.review_evidence,
        )
        if self.scientific_status is not expected:
            raise ValueError("scientific status disagrees with crystal-bound evidence")
        return self


class UnknownPass1PanelSummary(_ContentAddressedContract):
    """Exactly three terminal assessments from one owned execution."""

    _identity_field: ClassVar[str] = "panel_id"
    _identity_prefix: ClassVar[str] = "unknownpass1panel_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["unknown-pass1-panel-summary-v1"]
    panel_id: UnknownPass1PanelIdentifier
    owned_parent_run_id: OperatorIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    assessments: tuple[
        UnknownPass1CrystalAssessment,
        UnknownPass1CrystalAssessment,
        UnknownPass1CrystalAssessment,
    ]
    panel_status: Literal["terminal_complete"]

    @classmethod
    def from_assessments(
        cls,
        assessments: tuple[
            UnknownPass1CrystalAssessment,
            UnknownPass1CrystalAssessment,
            UnknownPass1CrystalAssessment,
        ],
    ) -> Self:
        """Sort and content-bind three independent terminal assessments."""

        ordered = tuple(sorted(assessments, key=lambda item: item.crystal_id))
        first = ordered[0]
        return cls.from_content(
            adapter_version="unknown-pass1-panel-summary-v1",
            owned_parent_run_id=first.owned_parent_run_id,
            execution_identity_id=first.execution_identity_id,
            assessments=ordered,
            panel_status="terminal_complete",
        )

    @model_validator(mode="after")
    def _validate_panel(self) -> Self:
        crystals = tuple(item.crystal_id for item in self.assessments)
        if crystals != tuple(sorted(set(crystals))):
            raise ValueError("panel crystal assessments must be unique and sorted")
        if any(
            item.owned_parent_run_id != self.owned_parent_run_id
            or item.execution_identity_id != self.execution_identity_id
            for item in self.assessments
        ):
            raise ValueError("panel assessments must share one owned execution")
        return self


__all__ = [
    "UnknownPass1CrystalAssessment",
    "UnknownPass1PanelSummary",
    "UnknownPass1ResidualContentState",
    "UnknownPass1ReviewEvidence",
    "UnknownPass1ScientificStatus",
    "UnknownPass1SolutionEvidence",
]
