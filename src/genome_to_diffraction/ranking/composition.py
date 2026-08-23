"""Plan one bounded deterministic Phase III component-expansion depth.

The planner consumes retained schema-v2 composition states and schema-v2
component specifications.  It performs no Phaser, refinement, or scientific
assessment work.  ``selected`` means only that an attempt may be scheduled;
packing, LLG, TFZ, and selection never promote identity or composition support.

Inputs explicitly enumerate component copy hypotheses 1--4 and identify which
copy counts were physically assessed and which are possible. Missing physical
evidence remains typed unsearchable rather than physically impossible; missing
ranking evidence is neutral.
Every non-parent hypothesis is retained with a selected, deferred, or
unsearchable reason.  Searchable hypotheses are allocated in deterministic
diagonal rounds across candidate rank and copy count, with parent rank as the
fastest-changing dimension.  This gives each of at most three retained parents
an opportunity before another parent receives the same candidate/copy slot.

The output is one :class:`CompositionExpansionDepthPlan` for the complete parent
beam plus an ordered fan-out boundary.  Its schema-v2 content identity binds
every parent, component, ranking evidence summary, disposition, and shared
budget.  The registry-bound adapter reloads the authoritative all-eligible
registry, verifies its records and model bytes, and binds a content-addressed
resolution for every parent component and candidate copy.  Valid model absence
is typed and retained as unsearchable; a malformed or checksum-corrupted
registry fails the input contract.  No external command, provider request,
Phaser, or refinement is run.  The depth-plan identity is the cache key.
Focused tests cover ordering, fairness, budgets, registry/source mutation,
typed absence, neutral missing evidence, and checksum failures.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated, Self

from pydantic import Field, model_validator

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.model_registry.all_eligible import (
    AllEligibleModelEntry,
    AllEligibleModelLookupResult,
    AllEligibleModelRegistry,
    AllEligibleModelRegistryError,
    load_all_eligible_model_registry,
)
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    PositiveInt,
)
from genome_to_diffraction.schemas.v2 import (
    AllModelRegistryIdentifier,
    ComponentSpec,
    CompositionCandidateHypothesis,
    CompositionExpansionDepthCandidate,
    CompositionExpansionDepthParent,
    CompositionExpansionDepthPlan,
    CompositionState,
    CompositionSupportState,
    ExpansionDisposition,
    ModelUnavailableReason,
    RegistryModelResolution,
    RegistryModelResolutionScope,
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


def _resolution_matches_component(
    resolution: RegistryModelResolution,
    component: ComponentSpec,
) -> bool:
    return (
        resolution.component_spec_id == component.component_spec_id
        and resolution.requested_copy_count == component.requested_copy_count
        and resolution.sequence_group_id == component.sequence_group_id
        and resolution.sequence_sha256 == component.sequence_sha256
        and resolution.model_id == component.model_id
        and resolution.model_sha256 == component.model_sha256
    )


class ParentExpansionInput(ContractModel):
    """One retained packed parent, beam rank, and optional registry bindings."""

    parent_rank: PositiveInt = Field(le=3)
    state: CompositionState
    model_resolutions: tuple[RegistryModelResolution, ...] = ()

    @model_validator(mode="after")
    def _validate_parent(self) -> Self:
        if self.state.support_state not in _PACKED_PARENT_STATES:
            raise ValueError("component expansion requires a retained packed parent")
        if self.model_resolutions:
            resolution_by_spec = {
                resolution.component_spec_id: resolution
                for resolution in self.model_resolutions
            }
            if len(resolution_by_spec) != len(self.model_resolutions):
                raise ValueError("duplicate parent model resolution")
            if set(resolution_by_spec) != {
                component.component_spec_id for component in self.state.components
            }:
                raise ValueError(
                    "parent model resolutions do not cover every parent component"
                )
            for component in self.state.components:
                resolution = resolution_by_spec[component.component_spec_id]
                if (
                    resolution.scope
                    is not RegistryModelResolutionScope.PARENT_COMPONENT
                    or resolution.parent_state_id != self.state.state_id
                    or resolution.parent_rank != self.parent_rank
                    or not _resolution_matches_component(resolution, component)
                ):
                    raise ValueError(
                        "parent model resolution does not match its component"
                    )
        return self


class ComponentExpansionInput(ContractModel):
    """One parent-bound catalogue candidate with copy and ranking evidence.

    ``component_specs`` must contain the same proposed component at copy counts
    1, 2, 3, and 4.  ``physically_assessed_copy_counts`` distinguishes an
    assessed impossible copy from missing physical evidence, while
    ``physically_eligible_copy_counts`` is the independently supplied
    total-composition Matthews/mass decision for ``parent_state_id``; the
    planner never infers either state from scores.
    ``model_available`` refers to verified runtime availability of the model
    named by the specifications.  The authoritative registry adapter derives
    it and attaches one typed resolution per copy; a missing artefact remains a
    typed unsearchable hypothesis. ``localisation_wave_eligible`` and
    ``reviewer_allowed`` are independent scheduling gates and cannot substitute
    for one another.
    """

    parent_state_id: CompositionStateIdentifier
    candidate_rank: PositiveInt
    component_specs: tuple[ComponentSpec, ...] = Field(min_length=4, max_length=4)
    physically_assessed_copy_counts: tuple[CopyCount, ...] = _COPY_COUNTS
    physically_eligible_copy_counts: tuple[CopyCount, ...] = ()
    model_available: bool = True
    model_identity_supported: bool = True
    localisation_wave_eligible: bool = True
    reviewer_allowed: bool = True
    model_provider: NonEmptyString | None = None
    model_variant_type: NonEmptyString | None = None
    model_resolutions: tuple[RegistryModelResolution, ...] = ()
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
        if tuple(sorted(set(self.physically_assessed_copy_counts))) != (
            self.physically_assessed_copy_counts
        ):
            raise ValueError(
                "physically assessed copy counts must be sorted and unique"
            )
        if not set(self.physically_eligible_copy_counts) <= set(
            self.physically_assessed_copy_counts
        ):
            raise ValueError("physically eligible copy counts must have an assessment")

        first = self.component_specs[0]
        invariant_fields = (
            "label",
            "sequence_group_id",
            "sequence_sha256",
            "model_id",
            "model_sha256",
            "sequence_mass_da",
            "sequence_mass_lower_da",
            "sequence_mass_upper_da",
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
        mass_unavailable = (
            first.sequence_mass_da is None
            and first.sequence_mass_lower_da is None
            and first.sequence_mass_upper_da is None
        )
        if mass_unavailable and (
            self.physically_assessed_copy_counts or self.physically_eligible_copy_counts
        ):
            raise ValueError(
                "mass-unavailable candidate cannot carry assessed or eligible copies"
            )
        if self.model_resolutions:
            resolution_by_spec = {
                resolution.component_spec_id: resolution
                for resolution in self.model_resolutions
            }
            if len(resolution_by_spec) != len(self.model_resolutions):
                raise ValueError("duplicate candidate-copy model resolution")
            if set(resolution_by_spec) != {
                component.component_spec_id for component in self.component_specs
            }:
                raise ValueError("model resolutions do not cover every candidate copy")
            for component in self.component_specs:
                resolution = resolution_by_spec[component.component_spec_id]
                if (
                    resolution.scope is not RegistryModelResolutionScope.CANDIDATE_COPY
                    or resolution.parent_state_id != self.parent_state_id
                    or resolution.candidate_rank != self.candidate_rank
                    or resolution.requested_provider != self.model_provider
                    or resolution.requested_variant_type != self.model_variant_type
                    or not _resolution_matches_component(resolution, component)
                ):
                    raise ValueError(
                        "candidate-copy model resolution does not match its input"
                    )
            if self.model_available != all(
                resolution.available for resolution in self.model_resolutions
            ):
                raise ValueError(
                    "candidate model availability disagrees with registry resolutions"
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
    model_registry_id: AllModelRegistryIdentifier | None = None

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
        resolutions = tuple(
            resolution
            for parent in self.parents
            for resolution in parent.model_resolutions
        ) + tuple(
            resolution
            for candidate in self.candidates
            for resolution in candidate.model_resolutions
        )
        if (self.model_registry_id is None) != (not resolutions):
            raise ValueError(
                "model registry identity and complete resolutions must be paired"
            )
        if self.model_registry_id is not None:
            if any(
                resolution.model_registry_id != self.model_registry_id
                for resolution in resolutions
            ):
                raise ValueError("model resolution uses a different registry")
            if any(not parent.model_resolutions for parent in self.parents) or any(
                not candidate.model_resolutions for candidate in self.candidates
            ):
                raise ValueError(
                    "registry-bound request requires every model resolution"
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


def _parent_models_available(parent: ParentExpansionInput) -> bool:
    return not parent.model_resolutions or all(
        resolution.available for resolution in parent.model_resolutions
    )


def _candidate_copy_resolution(
    candidate: ComponentExpansionInput,
    component: ComponentSpec,
) -> RegistryModelResolution | None:
    return next(
        (
            resolution
            for resolution in candidate.model_resolutions
            if resolution.component_spec_id == component.component_spec_id
        ),
        None,
    )


def _unavailable_model_reason(
    parent: ParentExpansionInput,
    candidate: ComponentExpansionInput,
    component: ComponentSpec,
) -> str:
    details = [
        f"parent:{resolution.component_spec_id}:{resolution.unavailable_reason.value}"
        for resolution in parent.model_resolutions
        if resolution.unavailable_reason is not None
    ]
    resolution = _candidate_copy_resolution(candidate, component)
    if resolution is not None and resolution.unavailable_reason is not None:
        details.append(f"candidate:{resolution.unavailable_reason.value}")
    if not details:
        return "verified model artefact is unavailable"
    return "model_registry_unavailable=" + ",".join(details)


def _base_disposition(
    parent: ParentExpansionInput,
    candidate: ComponentExpansionInput,
    component: ComponentSpec,
) -> tuple[ExpansionDisposition | None, str | None]:
    evidence = _evidence_reason(candidate)
    if component.requested_copy_count not in candidate.physically_assessed_copy_counts:
        return (
            ExpansionDisposition.UNSEARCHABLE_PHYSICAL_EVIDENCE,
            f"total-composition Matthews evidence is unavailable; {evidence}",
        )
    if component.requested_copy_count not in candidate.physically_eligible_copy_counts:
        return (
            ExpansionDisposition.EXCLUDED_PHYSICAL_IMPOSSIBLE,
            f"copy count is not physically eligible; {evidence}",
        )
    if not candidate.model_available or not _parent_models_available(parent):
        return (
            ExpansionDisposition.UNSEARCHABLE_NO_MODEL,
            f"{_unavailable_model_reason(parent, candidate, component)}; {evidence}",
        )
    if not candidate.model_identity_supported:
        return (
            ExpansionDisposition.UNSEARCHABLE_MODEL_IDENTITY,
            "model identity cannot be bound to the supplied sequence group; "
            f"{evidence}",
        )
    if not candidate.localisation_wave_eligible:
        return (
            ExpansionDisposition.DEFERRED_LOCALISATION_WAVE,
            f"localisation policy holds this scheduling wave; {evidence}",
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
                    parent,
                    candidate,
                    component,
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


def _resolution_sort_key(
    resolution: RegistryModelResolution,
) -> tuple[int, int, int, str]:
    scope_rank = (
        0 if resolution.scope is RegistryModelResolutionScope.PARENT_COMPONENT else 1
    )
    return (
        resolution.parent_rank,
        scope_rank,
        resolution.candidate_rank or 0,
        resolution.component_spec_id,
    )


def _verified_exact_model(
    registry: AllEligibleModelRegistry,
    component: ComponentSpec,
    *,
    provider: str | None,
    variant_type: str | None,
) -> tuple[AllEligibleModelEntry | None, ModelUnavailableReason | None]:
    lookup: AllEligibleModelLookupResult = registry.lookup(
        component.sequence_group_id,
        provider=provider,
        variant_type=variant_type,
    )
    if lookup.unavailable_reason is not None:
        return None, lookup.unavailable_reason
    entry = next(
        (model for model in lookup.models if model.model_id == component.model_id),
        None,
    )
    if entry is None:
        return None, ModelUnavailableReason.MODEL_NOT_REGISTERED
    if (
        entry.sequence_sha256 != component.sequence_sha256
        or entry.model_sha256 != component.model_sha256
    ):
        raise CompositionPlanningError(
            "composition model identity disagrees with the all-model registry: "
            f"{component.model_id}"
        )
    relative = PurePosixPath(entry.model_path)
    try:
        model_path = (registry.root / Path(*relative.parts)).resolve(strict=True)
    except OSError as error:
        raise CompositionPlanningError(
            f"registered model cannot be resolved: {entry.model_id}"
        ) from error
    if not model_path.is_file() or not model_path.is_relative_to(registry.root):
        raise CompositionPlanningError(
            f"registered model escaped its checksum-verified root: {entry.model_id}"
        )
    if sha256_file(model_path, progress=False) != entry.model_sha256:
        raise CompositionPlanningError(
            f"registered model checksum changed before planning: {entry.model_id}"
        )
    return entry, None


def _registry_resolution(
    *,
    registry: AllEligibleModelRegistry,
    scope: RegistryModelResolutionScope,
    parent: ParentExpansionInput,
    component: ComponentSpec,
    candidate_rank: int | None = None,
    provider: str | None = None,
    variant_type: str | None = None,
) -> RegistryModelResolution:
    entry, unavailable_reason = _verified_exact_model(
        registry,
        component,
        provider=provider,
        variant_type=variant_type,
    )
    return RegistryModelResolution.from_content(
        model_registry_id=registry.manifest.registry_id,
        scope=scope,
        parent_state_id=parent.state.state_id,
        parent_rank=parent.parent_rank,
        candidate_rank=candidate_rank,
        component_spec_id=component.component_spec_id,
        requested_copy_count=component.requested_copy_count,
        sequence_group_id=component.sequence_group_id,
        sequence_sha256=component.sequence_sha256,
        model_id=component.model_id,
        model_sha256=component.model_sha256,
        requested_provider=provider,
        requested_variant_type=variant_type,
        registry_entry_sha256=(canonical_digest(entry) if entry is not None else None),
        resolved_provider=entry.provider if entry is not None else None,
        resolved_variant_type=entry.variant_type if entry is not None else None,
        unavailable_reason=unavailable_reason,
    )


def _bind_request_to_registry(
    request: CompositionExpansionRequest,
    registry: AllEligibleModelRegistry,
) -> CompositionExpansionRequest:
    if (
        request.model_registry_id is not None
        or any(parent.model_resolutions for parent in request.parents)
        or any(candidate.model_resolutions for candidate in request.candidates)
    ):
        raise CompositionPlanningError(
            "registry adapter requires an unbound composition request"
        )
    parents_by_id = {parent.state.state_id: parent for parent in request.parents}
    bound_parents: list[ParentExpansionInput] = []
    for parent in request.parents:
        resolutions = tuple(
            _registry_resolution(
                registry=registry,
                scope=RegistryModelResolutionScope.PARENT_COMPONENT,
                parent=parent,
                component=component,
            )
            for component in parent.state.components
        )
        payload = parent.model_dump(mode="python", exclude={"model_resolutions"})
        bound_parents.append(
            ParentExpansionInput.model_validate(
                {**payload, "model_resolutions": resolutions}
            )
        )

    bound_candidates: list[ComponentExpansionInput] = []
    for candidate in request.candidates:
        parent = parents_by_id[candidate.parent_state_id]
        resolutions = tuple(
            _registry_resolution(
                registry=registry,
                scope=RegistryModelResolutionScope.CANDIDATE_COPY,
                parent=parent,
                component=component,
                candidate_rank=candidate.candidate_rank,
                provider=candidate.model_provider,
                variant_type=candidate.model_variant_type,
            )
            for component in candidate.component_specs
        )
        payload = candidate.model_dump(mode="python", exclude={"model_resolutions"})
        bound_candidates.append(
            ComponentExpansionInput.model_validate(
                {
                    **payload,
                    "model_available": all(
                        resolution.available for resolution in resolutions
                    ),
                    "model_resolutions": resolutions,
                }
            )
        )

    payload = request.model_dump(
        mode="python",
        exclude={"parents", "candidates", "model_registry_id"},
    )
    return CompositionExpansionRequest.model_validate(
        {
            **payload,
            "parents": tuple(bound_parents),
            "candidates": tuple(bound_candidates),
            "model_registry_id": registry.manifest.registry_id,
        }
    )


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
                physical_assessed=(
                    proposal.component.requested_copy_count
                    in proposal.candidate.physically_assessed_copy_counts
                ),
                physical_possible=(
                    proposal.component.requested_copy_count
                    in proposal.candidate.physically_eligible_copy_counts
                ),
                model_available=(
                    proposal.candidate.model_available
                    and _parent_models_available(proposal.parent)
                ),
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
            ExpansionDisposition.DEFERRED_LOCALISATION_WAVE,
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
    model_resolutions = tuple(
        sorted(
            (
                resolution
                for parent in parents
                for resolution in parent.model_resolutions
            ),
            key=_resolution_sort_key,
        )
    ) + tuple(
        sorted(
            (
                resolution
                for candidate in candidates
                for resolution in candidate.model_resolutions
            ),
            key=_resolution_sort_key,
        )
    )
    model_resolutions = tuple(sorted(model_resolutions, key=_resolution_sort_key))
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
        model_registry_id=request.model_registry_id,
        model_resolutions=model_resolutions,
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


def build_registry_bound_composition_expansion_plan(
    request: CompositionExpansionRequest,
    *,
    model_registry_json: Path,
) -> CompositionExpansionOutput:
    """Verify the all-model registry, bind every model input, and plan one depth.

    Registry file, record, and model checksum failures are input-contract
    failures.  A valid registry that lacks the requested sequence group,
    provider, variant, or exact model instead produces typed unavailable
    resolutions and retained unsearchable hypotheses.
    """

    try:
        registry = load_all_eligible_model_registry(model_registry_json)
    except (AllEligibleModelRegistryError, OSError) as error:
        raise CompositionPlanningError(
            "all-model registry could not be checksum verified"
        ) from error
    bound_request = _bind_request_to_registry(request, registry)
    return build_composition_expansion_plan(bound_request)
