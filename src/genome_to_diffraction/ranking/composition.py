"""Plan one bounded deterministic Phase III component-expansion depth.

The planner consumes retained schema-v2 composition states and schema-v2
component specifications.  It performs no Phaser, refinement, or scientific
assessment work.  ``selected`` means only that an attempt may be scheduled;
packing, LLG, TFZ, and selection never promote identity or composition support.

Inputs explicitly enumerate component copy hypotheses 1--4 and identify which
copy counts are physically possible.  Missing ranking evidence is neutral.
Every non-parent hypothesis is retained with a selected, deferred, or
unsearchable reason.  Searchable hypotheses are allocated in deterministic
diagonal rounds across candidate rank and copy count, with parent rank as the
fastest-changing dimension.  This gives each of at most three retained parents
an opportunity before another parent receives the same candidate/copy slot.

The output is one :class:`CompositionExpansionDepthPlan` for the complete parent
beam plus an ordered fan-out boundary.  Its schema-v2 content identity binds
every parent, component, ranking evidence summary, disposition, and shared
budget.  Focused tests cover ordering, fairness, budgets, mutation, neutral
missing evidence, and the zero-physical-hypothesis path.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, model_validator

from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    PositiveInt,
)
from genome_to_diffraction.schemas.v2 import (
    ComponentSpec,
    CompositionCandidateHypothesis,
    CompositionExpansionDepthCandidate,
    CompositionExpansionDepthParent,
    CompositionExpansionDepthPlan,
    CompositionState,
    CompositionSupportState,
    ExpansionDisposition,
)
from genome_to_diffraction.schemas.v2.composition import CompositionStateIdentifier
from genome_to_diffraction.status import InputContractError

CopyCount = Annotated[int, Field(ge=1, le=4)]

_RANKING_POLICY_VERSION = "phase3-round-robin-v1"
_COPY_COUNTS = (1, 2, 3, 4)
_PACKED_PARENT_STATES = frozenset(
    {
        CompositionSupportState.PACKED,
        CompositionSupportState.REFINED,
        CompositionSupportState.REVIEW_SUPPORTED,
        CompositionSupportState.COMPOSITION_SUPPORTED,
    }
)


class CompositionPlanningError(InputContractError):
    """Expansion inputs cannot form one deterministic bounded search depth."""


class ExpansionEvidenceLevel(StrEnum):
    """Small inspectable evidence ordering used only for scheduling rank."""

    SUPPORTING = "supporting"
    COMPATIBLE = "compatible"
    NEUTRAL = "neutral"
    CONFLICTING = "conflicting"


_EVIDENCE_ORDER = {
    ExpansionEvidenceLevel.SUPPORTING: 0,
    ExpansionEvidenceLevel.COMPATIBLE: 1,
    ExpansionEvidenceLevel.NEUTRAL: 2,
    ExpansionEvidenceLevel.CONFLICTING: 3,
}


class ParentExpansionInput(ContractModel):
    """One retained packed parent and its explicit beam rank."""

    parent_rank: PositiveInt = Field(le=3)
    state: CompositionState

    @model_validator(mode="after")
    def _validate_parent(self) -> Self:
        if self.state.support_state not in _PACKED_PARENT_STATES:
            raise ValueError("component expansion requires a retained packed parent")
        return self


class ComponentExpansionInput(ContractModel):
    """One parent-bound catalogue candidate with copy and ranking evidence.

    ``component_specs`` must contain the same proposed component at copy counts
    1, 2, 3, and 4.  ``physically_eligible_copy_counts`` is the independently
    supplied total-composition Matthews/mass decision for ``parent_state_id``;
    the planner never infers it from scores.
    ``model_available`` refers to verified runtime availability of the model
    named by the specifications, so a missing artefact can still be retained as
    a typed unsearchable hypothesis.
    """

    parent_state_id: CompositionStateIdentifier
    candidate_rank: PositiveInt
    component_specs: tuple[ComponentSpec, ...] = Field(min_length=4, max_length=4)
    physically_eligible_copy_counts: tuple[CopyCount, ...] = ()
    model_available: bool = True
    model_identity_supported: bool = True
    reviewer_allowed: bool = True
    localisation_evidence: ExpansionEvidenceLevel | None = None
    sds_page_evidence: ExpansionEvidenceLevel | None = None
    native_page_evidence: ExpansionEvidenceLevel | None = None
    matthews_evidence: ExpansionEvidenceLevel | None = None
    model_quality_evidence: ExpansionEvidenceLevel | None = None
    structural_diversity_evidence: ExpansionEvidenceLevel | None = None

    @model_validator(mode="after")
    def _validate_copy_hypotheses(self) -> Self:
        counts = tuple(spec.requested_copy_count for spec in self.component_specs)
        if counts != _COPY_COUNTS:
            raise ValueError("component specifications must enumerate copy counts 1..4")
        if tuple(sorted(set(self.physically_eligible_copy_counts))) != (
            self.physically_eligible_copy_counts
        ):
            raise ValueError(
                "physically eligible copy counts must be sorted and unique"
            )

        first = self.component_specs[0]
        invariant_fields = (
            "label",
            "sequence_group_id",
            "sequence_sha256",
            "model_id",
            "model_sha256",
            "sequence_mass_da",
            "mass_evidence_sha256",
            "model_evidence_sha256",
        )
        for spec in self.component_specs[1:]:
            if any(
                getattr(spec, field) != getattr(first, field)
                for field in invariant_fields
            ):
                raise ValueError(
                    "copy hypotheses must describe one invariant component/model"
                )
        return self

    @property
    def sequence_group_id(self) -> str:
        """Return the invariant exact sequence-equivalence group."""

        return self.component_specs[0].sequence_group_id


class CompositionExpansionRequest(ContractModel):
    """Typed input for one crystal and one additional-component depth."""

    parents: tuple[ParentExpansionInput, ...] = Field(min_length=1, max_length=3)
    candidates: tuple[ComponentExpansionInput, ...]
    maximum_component_depth: PositiveInt = Field(default=6, le=6)
    beam_width: PositiveInt = Field(default=3, le=3)
    per_depth_attempt_budget: PositiveInt = Field(default=25, le=25)
    global_attempt_budget: PositiveInt = Field(default=100, le=100)
    global_attempts_used_before: int = Field(default=0, ge=0)
    ranking_policy_version: NonEmptyString = _RANKING_POLICY_VERSION

    @model_validator(mode="after")
    def _validate_one_depth(self) -> Self:
        parents = tuple(sorted(self.parents, key=lambda item: item.parent_rank))
        if tuple(parent.parent_rank for parent in parents) != tuple(
            range(1, len(parents) + 1)
        ):
            raise ValueError("parent ranks must be contiguous and unique")
        if len(parents) > self.beam_width:
            raise ValueError("parent count exceeds the configured beam width")

        first_state = parents[0].state
        for parent in parents[1:]:
            state = parent.state
            if (
                state.crystal_id != first_state.crystal_id
                or state.diffraction_dataset_id != first_state.diffraction_dataset_id
                or state.diffraction_sha256 != first_state.diffraction_sha256
                or state.depth != first_state.depth
            ):
                raise ValueError(
                    "all retained parents must describe one crystal and one depth"
                )
        if first_state.depth + 1 > self.maximum_component_depth:
            raise ValueError("target depth exceeds the configured maximum")
        if self.global_attempts_used_before > self.global_attempt_budget:
            raise ValueError("used attempts exceed the global budget")

        parent_ids = {parent.state.state_id for parent in parents}
        candidates_by_parent: dict[str, list[ComponentExpansionInput]] = {
            parent_id: [] for parent_id in parent_ids
        }
        for candidate in self.candidates:
            if candidate.parent_state_id not in parent_ids:
                raise ValueError("candidate refers to an unknown parent state")
            candidates_by_parent[candidate.parent_state_id].append(candidate)
        for candidates in candidates_by_parent.values():
            candidates.sort(key=lambda item: item.candidate_rank)
            if tuple(candidate.candidate_rank for candidate in candidates) != tuple(
                range(1, len(candidates) + 1)
            ):
                raise ValueError(
                    "candidate ranks must be contiguous within each parent"
                )
            groups = tuple(candidate.sequence_group_id for candidate in candidates)
            if len(set(groups)) != len(groups):
                raise ValueError(
                    "candidate sequence-equivalence groups must be unique per parent"
                )
        return self


@dataclass(frozen=True)
class PlannedCompositionAttempt:
    """One ordered selected fan-out item; it carries no support promotion."""

    allocation_rank: int
    parent_state_id: str
    depth_candidate_id: str
    component_spec_id: str


@dataclass(frozen=True)
class CompositionExpansionOutput:
    """One shared depth plan and its ordered selected attempt boundary."""

    depth_plan: CompositionExpansionDepthPlan
    selected_attempts: tuple[PlannedCompositionAttempt, ...]
    remaining_global_attempt_budget: int


@dataclass(frozen=True)
class _Proposal:
    parent: ParentExpansionInput
    candidate: ComponentExpansionInput
    candidate_position: int
    copy_position: int
    component: ComponentSpec
    base_disposition: ExpansionDisposition | None
    base_reason: str | None

    @property
    def key(self) -> tuple[str, str]:
        return self.parent.state.state_id, self.component.component_spec_id


def _normalised_evidence(
    value: ExpansionEvidenceLevel | None,
) -> ExpansionEvidenceLevel:
    return value or ExpansionEvidenceLevel.NEUTRAL


def _evidence_values(
    candidate: ComponentExpansionInput,
) -> tuple[ExpansionEvidenceLevel, ...]:
    return tuple(
        _normalised_evidence(value)
        for value in (
            candidate.localisation_evidence,
            candidate.sds_page_evidence,
            candidate.native_page_evidence,
            candidate.matthews_evidence,
            candidate.model_quality_evidence,
            candidate.structural_diversity_evidence,
        )
    )


def _candidate_sort_key(
    candidate: ComponentExpansionInput,
) -> tuple[object, ...]:
    evidence = _evidence_values(candidate)
    return (
        *(_EVIDENCE_ORDER[value] for value in evidence),
        candidate.candidate_rank,
        candidate.sequence_group_id,
    )


def _evidence_reason(candidate: ComponentExpansionInput) -> str:
    names = (
        "localisation",
        "sds_page",
        "native_page",
        "matthews",
        "model_quality",
        "structural_diversity",
    )
    return "ranking=" + ",".join(
        f"{name}:{value.value}"
        for name, value in zip(names, _evidence_values(candidate), strict=True)
    )


def _base_disposition(
    candidate: ComponentExpansionInput,
    copy_count: int,
) -> tuple[ExpansionDisposition | None, str | None]:
    evidence = _evidence_reason(candidate)
    if copy_count not in candidate.physically_eligible_copy_counts:
        return (
            ExpansionDisposition.EXCLUDED_PHYSICAL_IMPOSSIBLE,
            f"copy count is not physically eligible; {evidence}",
        )
    if not candidate.model_available:
        return (
            ExpansionDisposition.UNSEARCHABLE_NO_MODEL,
            f"verified model artefact is unavailable; {evidence}",
        )
    if not candidate.model_identity_supported:
        return (
            ExpansionDisposition.UNSEARCHABLE_MODEL_IDENTITY,
            "model identity cannot be bound to the supplied sequence group; "
            f"{evidence}",
        )
    if not candidate.reviewer_allowed:
        return (
            ExpansionDisposition.DEFERRED_REVIEWER,
            f"reviewer hold excludes this scheduling wave; {evidence}",
        )
    return None, None


def _proposals(
    parents: tuple[ParentExpansionInput, ...],
    candidates: tuple[ComponentExpansionInput, ...],
) -> tuple[_Proposal, ...]:
    proposals: list[_Proposal] = []
    for parent in parents:
        parent_candidates = sorted(
            (
                candidate
                for candidate in candidates
                if candidate.parent_state_id == parent.state.state_id
            ),
            key=_candidate_sort_key,
        )
        represented = {
            component.sequence_group_id for component in parent.state.components
        }
        parent_labels = {component.label for component in parent.state.components}
        for candidate_position, candidate in enumerate(parent_candidates):
            if candidate.sequence_group_id in represented:
                continue
            for copy_position, component in enumerate(candidate.component_specs):
                if component.label in parent_labels:
                    raise CompositionPlanningError(
                        "candidate component label already exists in a parent state"
                    )
                disposition, reason = _base_disposition(
                    candidate,
                    component.requested_copy_count,
                )
                proposals.append(
                    _Proposal(
                        parent=parent,
                        candidate=candidate,
                        candidate_position=candidate_position,
                        copy_position=copy_position,
                        component=component,
                        base_disposition=disposition,
                        base_reason=reason,
                    )
                )
    return tuple(proposals)


def _round_robin_searchable(
    proposals: Iterable[_Proposal],
    *,
    parent_count: int,
    candidate_count: int,
) -> tuple[_Proposal, ...]:
    by_position = {
        (
            proposal.candidate_position,
            proposal.copy_position,
            proposal.parent.parent_rank,
        ): proposal
        for proposal in proposals
        if proposal.base_disposition is None
    }
    ordered: list[_Proposal] = []
    for diagonal in range(candidate_count + len(_COPY_COUNTS) - 1):
        for candidate_position in range(candidate_count):
            copy_position = diagonal - candidate_position
            if copy_position not in range(len(_COPY_COUNTS)):
                continue
            for parent_rank in range(1, parent_count + 1):
                proposal = by_position.get(
                    (candidate_position, copy_position, parent_rank)
                )
                if proposal is not None:
                    ordered.append(proposal)
    return tuple(ordered)


def build_composition_expansion_plan(
    request: CompositionExpansionRequest,
) -> CompositionExpansionOutput:
    """Build one bounded depth without executing or interpreting a search."""

    parents = tuple(sorted(request.parents, key=lambda item: item.parent_rank))
    candidates = request.candidates
    proposals = _proposals(parents, candidates)
    allocation = _round_robin_searchable(
        proposals,
        parent_count=len(parents),
        candidate_count=(
            max(
                (proposal.candidate_position for proposal in proposals),
                default=-1,
            )
            + 1
        ),
    )
    remaining_global = (
        request.global_attempt_budget - request.global_attempts_used_before
    )
    selected_limit = min(request.per_depth_attempt_budget, remaining_global)
    selected_keys = {proposal.key for proposal in allocation[:selected_limit]}
    global_budget_is_limiting = remaining_global <= request.per_depth_attempt_budget

    allocation_rank_by_key = {
        proposal.key: index
        for index, proposal in enumerate(allocation[:selected_limit], start=1)
    }
    depth_candidates_by_key: dict[
        tuple[str, str], CompositionExpansionDepthCandidate
    ] = {}
    depth_candidates: list[CompositionExpansionDepthCandidate] = []
    for parent in parents:
        parent_proposals = sorted(
            (proposal for proposal in proposals if proposal.parent == parent),
            key=lambda proposal: (
                proposal.candidate_position,
                proposal.copy_position,
                proposal.component.component_spec_id,
            ),
        )
        for rank, proposal in enumerate(parent_proposals, start=1):
            evidence = _evidence_reason(proposal.candidate)
            if proposal.base_disposition is not None:
                disposition = proposal.base_disposition
                reason = proposal.base_reason
            elif proposal.key in selected_keys:
                disposition = ExpansionDisposition.SELECTED
                reason = (
                    "scheduled by deterministic round-robin within depth and "
                    f"global budgets; selection is not scientific support; {evidence}"
                )
            elif global_budget_is_limiting:
                disposition = ExpansionDisposition.DEFERRED_GLOBAL_BUDGET
                reason = (
                    f"global additional-component attempt budget exhausted; {evidence}"
                )
            else:
                disposition = ExpansionDisposition.DEFERRED_DEPTH_BUDGET
                reason = (
                    "per-depth additional-component attempt budget exhausted; "
                    f"{evidence}"
                )
            if reason is None:  # pragma: no cover - exhaustive guard
                raise AssertionError("composition disposition lacks a reason")
            hypothesis = CompositionCandidateHypothesis.from_content(
                component=proposal.component,
                rank=rank,
                disposition=disposition,
                disposition_reason=reason,
                physical_possible=(
                    proposal.component.requested_copy_count
                    in proposal.candidate.physically_eligible_copy_counts
                ),
                model_available=proposal.candidate.model_available,
            )
            depth_candidate = CompositionExpansionDepthCandidate.from_content(
                parent_state_id=parent.state.state_id,
                parent_rank=parent.parent_rank,
                hypothesis=hypothesis,
                allocation_rank=allocation_rank_by_key.get(proposal.key),
            )
            depth_candidates_by_key[proposal.key] = depth_candidate
            depth_candidates.append(depth_candidate)

    selected_count = sum(
        item.hypothesis.disposition is ExpansionDisposition.SELECTED
        for item in depth_candidates
    )
    deferred_count = sum(
        item.hypothesis.disposition
        in {
            ExpansionDisposition.DEFERRED_DEPTH_BUDGET,
            ExpansionDisposition.DEFERRED_GLOBAL_BUDGET,
            ExpansionDisposition.DEFERRED_REVIEWER,
        }
        for item in depth_candidates
    )
    depth_parents = tuple(
        CompositionExpansionDepthParent.from_content(
            parent_state_id=parent.state.state_id,
            parent_rank=parent.parent_rank,
            parent_component_labels=tuple(
                component.label for component in parent.state.components
            ),
            parent_sequence_group_ids=tuple(
                component.sequence_group_id for component in parent.state.components
            ),
        )
        for parent in parents
    )
    physical_hypothesis_count = sum(
        proposal.component.requested_copy_count
        in proposal.candidate.physically_eligible_copy_counts
        for proposal in proposals
    )
    depth_plan = CompositionExpansionDepthPlan.from_content(
        crystal_id=parents[0].state.crystal_id,
        diffraction_dataset_id=parents[0].state.diffraction_dataset_id,
        parent_depth=parents[0].state.depth,
        target_depth=parents[0].state.depth + 1,
        parents=depth_parents,
        maximum_component_depth=request.maximum_component_depth,
        beam_width=request.beam_width,
        per_depth_attempt_budget=request.per_depth_attempt_budget,
        global_attempt_budget=request.global_attempt_budget,
        global_attempts_used_before=request.global_attempts_used_before,
        ranking_policy_version=request.ranking_policy_version,
        candidate_count=len(depth_candidates),
        physical_hypothesis_count=physical_hypothesis_count,
        selected_attempt_count=selected_count,
        deferred_candidate_count=deferred_count,
        unsearchable_candidate_count=(
            len(depth_candidates) - selected_count - deferred_count
        ),
        candidates=tuple(depth_candidates),
    )

    selected_attempts = tuple(
        PlannedCompositionAttempt(
            allocation_rank=index,
            parent_state_id=proposal.parent.state.state_id,
            depth_candidate_id=depth_candidates_by_key[proposal.key].depth_candidate_id,
            component_spec_id=proposal.component.component_spec_id,
        )
        for index, proposal in enumerate(allocation[:selected_limit], start=1)
    )
    return CompositionExpansionOutput(
        depth_plan=depth_plan,
        selected_attempts=selected_attempts,
        remaining_global_attempt_budget=remaining_global - len(selected_attempts),
    )
