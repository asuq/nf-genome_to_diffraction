"""Generate complete schema-v2 component-expansion candidate inputs.

Scientific purpose
------------------
This module is the deterministic join between the complete catalogue and the
bounded B--F composition planner.  It retains one row for every catalogue
sequence group not already represented in each packed parent and enumerates
parent-specific total-composition copy evidence for copies 1--4.  Localisation,
SDS-PAGE, native-PAGE, Matthews plausibility, model quality, and structural
diversity remain separate inspectable priors; none is identity or composition
support.

Inputs are validated catalogue groups, packed parent states, the complete
catalogue localisation policy, its exact active-wave completion and reopen
decision, a typed gel manifest, one Matthews context per parent, optional
checksum-bound model-ranking evidence, and the checksum-verified all-eligible
model registry.  The registry is independent of the bounded A shortlist.

Outputs are complete :class:`ComponentExpansionInput` rows plus one immutable
inventory that binds all source identities, derived copy evidence, retained
counts, and deterministic ranks.  No external command, provider request,
Nextflow process, Phaser search, support promotion, or sequence submission is
performed.  A malformed join raises :class:`CandidateGenerationError`; missing
gel/model-ranking evidence and uncertain/failed localisation are neutral, while
valid no-model and mass-unavailable groups remain typed retained rows.

``inventory_id`` is the cache key.  Focused coverage lives in
``tests/unit/test_component_candidate_generation.py``.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.localisation.contracts import LocalisationOutcome
from genome_to_diffraction.localisation.policy import (
    ActiveWaveCompletion,
    CatalogueLocalisationWavePolicy,
    FirstWaveDisposition,
    LocalisationReopenPlan,
)
from genome_to_diffraction.localisation.policy import (
    first_wave_disposition as localisation_first_wave_disposition,
)
from genome_to_diffraction.matthews.enumerate import physical_status, prior_score
from genome_to_diffraction.model_registry.all_eligible import (
    AllEligibleModelEntry,
    AllEligibleModelRegistry,
    AllEligibleModelRegistryError,
    SequenceGroupModelInventory,
    load_all_eligible_model_registry,
)
from genome_to_diffraction.ranking.composition import (
    ComponentExpansionInput,
    CompositionExpansionRequest,
    ExpansionEvidenceLevel,
    ParentExpansionInput,
)
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    PositiveFloat,
    PositiveInt,
    Sha256Hex,
)
from genome_to_diffraction.schemas.manifests import (
    GelEvidenceManifest,
    GelEvidenceObservation,
    GelMethod,
    SdsBandRole,
)
from genome_to_diffraction.schemas.results import PhysicalStatus, SequenceGroupRecord
from genome_to_diffraction.schemas.v2 import (
    AllModelRegistryIdentifier,
    ComponentSpec,
)
from genome_to_diffraction.schemas.v2.composition import (
    CompositionStateIdentifier,
    SequenceGroupIdentifier,
)
from genome_to_diffraction.status import InputContractError

_GENERATOR_VERSION = "phase3-component-candidate-generation-v1"
_MATTHEWS_BACKEND = "broad_solvent_centrality_total_composition_v1_uncalibrated"
_SOLVENT_MASS_DENSITY_DA_PER_A3 = 1.23
_COMPONENT_LABELS = ("A", "B", "C", "D", "E", "F")
_COPY_COUNTS = (1, 2, 3, 4)
_EVIDENCE_ORDER = {
    ExpansionEvidenceLevel.SUPPORTING: 0,
    ExpansionEvidenceLevel.COMPATIBLE: 1,
    ExpansionEvidenceLevel.NEUTRAL: 2,
    ExpansionEvidenceLevel.CONFLICTING: 3,
}


class CandidateGenerationError(InputContractError):
    """Candidate sources cannot form one complete deterministic inventory."""


class ParentMatthewsContext(ContractModel):
    """Parent-bound ASU volume and broad solvent bounds for copies 1--4."""

    schema_version: Literal["2.0"] = "2.0"
    backend: Literal["broad_solvent_centrality_total_composition_v1_uncalibrated"] = (
        _MATTHEWS_BACKEND
    )
    parent_state_id: CompositionStateIdentifier
    asu_volume_a3: PositiveFloat
    minimum_solvent_fraction: float = Field(ge=0, lt=1)
    maximum_solvent_fraction: float = Field(gt=0, le=1)
    source_evidence_sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_bounds(self) -> Self:
        if self.minimum_solvent_fraction >= self.maximum_solvent_fraction:
            raise ValueError("Matthews solvent bounds do not span an interval")
        return self


class ParentModelRankingEvidence(ContractModel):
    """Optional parent-specific quality/diversity evidence for one registry model."""

    schema_version: Literal["2.0"] = "2.0"
    parent_state_id: CompositionStateIdentifier
    model_id: NonEmptyString
    model_sha256: Sha256Hex
    policy_version: NonEmptyString
    model_quality_evidence: ExpansionEvidenceLevel
    structural_diversity_evidence: ExpansionEvidenceLevel
    evidence_sha256: Sha256Hex


class TotalCompositionCopyEvidence(ContractModel):
    """One candidate-copy Matthews assessment using the complete parent mass."""

    schema_version: Literal["2.0"] = "2.0"
    backend: Literal["broad_solvent_centrality_total_composition_v1_uncalibrated"] = (
        _MATTHEWS_BACKEND
    )
    parent_state_id: CompositionStateIdentifier
    sequence_group_id: SequenceGroupIdentifier
    copy_count: PositiveInt = Field(le=4)
    matthews_context_sha256: Sha256Hex
    total_mass_lower_da: PositiveFloat | None = None
    total_mass_upper_da: PositiveFloat | None = None
    matthews_coefficient_lower: PositiveFloat | None = None
    matthews_coefficient_upper: PositiveFloat | None = None
    solvent_fraction_lower: float | None = None
    solvent_fraction_upper: float | None = None
    matthews_prior: float | None = Field(default=None, ge=0, le=1)
    physical_status: PhysicalStatus | None = None
    physically_eligible: bool
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_assessment(self) -> Self:
        if self.copy_count not in _COPY_COUNTS:
            raise ValueError("total-composition copy count must be between 1 and 4")
        metrics = (
            self.total_mass_lower_da,
            self.total_mass_upper_da,
            self.matthews_coefficient_lower,
            self.matthews_coefficient_upper,
            self.solvent_fraction_lower,
            self.solvent_fraction_upper,
            self.matthews_prior,
        )
        if self.physical_status is None:
            if any(value is not None for value in metrics) or self.physically_eligible:
                raise ValueError("unassessed copy cannot retain Matthews metrics")
            if "sequence_mass_unavailable" not in self.warnings:
                raise ValueError("unassessed copy lacks its mass-unavailable warning")
            return self
        if any(value is None for value in metrics):
            raise ValueError("assessed copy lacks total-composition Matthews metrics")
        ordered_bounds = (
            (self.total_mass_lower_da, self.total_mass_upper_da, "total mass"),
            (
                self.matthews_coefficient_lower,
                self.matthews_coefficient_upper,
                "Matthews coefficient",
            ),
            (
                self.solvent_fraction_lower,
                self.solvent_fraction_upper,
                "solvent fraction",
            ),
        )
        for lower, upper, label in ordered_bounds:
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"{label} lower bound exceeds upper bound")
        expected_eligible = self.physical_status is not PhysicalStatus.IMPOSSIBLE
        if self.physically_eligible != expected_eligible:
            raise ValueError("copy eligibility disagrees with its physical status")
        return self


def _localisation_level(
    disposition: FirstWaveDisposition,
) -> ExpansionEvidenceLevel:
    if disposition is FirstWaveDisposition.ACTIVE:
        return ExpansionEvidenceLevel.SUPPORTING
    if disposition is FirstWaveDisposition.EXCLUDED:
        return ExpansionEvidenceLevel.CONFLICTING
    return ExpansionEvidenceLevel.NEUTRAL


def _matthews_level(
    evidence: Sequence[TotalCompositionCopyEvidence],
) -> ExpansionEvidenceLevel:
    statuses = {item.physical_status for item in evidence}
    if PhysicalStatus.PLAUSIBLE in statuses:
        return ExpansionEvidenceLevel.SUPPORTING
    if PhysicalStatus.REVIEW in statuses:
        return ExpansionEvidenceLevel.COMPATIBLE
    if statuses == {PhysicalStatus.IMPOSSIBLE}:
        return ExpansionEvidenceLevel.CONFLICTING
    return ExpansionEvidenceLevel.NEUTRAL


class GeneratedComponentExpansionRow(ContractModel):
    """One complete retained parent/catalogue join and its planner input."""

    schema_version: Literal["2.0"] = "2.0"
    parent_rank: PositiveInt = Field(le=3)
    parent_state_id: CompositionStateIdentifier
    sequence_group_id: SequenceGroupIdentifier
    localisation_outcome: LocalisationOutcome
    first_wave_disposition: FirstWaveDisposition
    first_wave_eligible: bool
    reopened: bool
    wave_eligible: bool
    selected_model_registry_entry_sha256: Sha256Hex | None = None
    total_composition_evidence: tuple[TotalCompositionCopyEvidence, ...] = Field(
        min_length=4,
        max_length=4,
    )
    component_input: ComponentExpansionInput

    @model_validator(mode="after")
    def _validate_complete_row(self) -> Self:
        candidate = self.component_input
        if (
            candidate.parent_state_id != self.parent_state_id
            or candidate.sequence_group_id != self.sequence_group_id
        ):
            raise ValueError("component input differs from its retained row")
        if tuple(item.copy_count for item in self.total_composition_evidence) != (
            _COPY_COUNTS
        ):
            raise ValueError("row does not retain ordered copy evidence 1..4")
        if any(
            item.parent_state_id != self.parent_state_id
            or item.sequence_group_id != self.sequence_group_id
            for item in self.total_composition_evidence
        ):
            raise ValueError("total-composition evidence differs from its row")
        eligible = tuple(
            item.copy_count
            for item in self.total_composition_evidence
            if item.physically_eligible
        )
        assessed = tuple(
            item.copy_count
            for item in self.total_composition_evidence
            if item.physical_status is not None
        )
        if candidate.physically_assessed_copy_counts != assessed:
            raise ValueError("candidate physical assessment coverage is incomplete")
        if candidate.physically_eligible_copy_counts != eligible:
            raise ValueError(
                "candidate copy eligibility differs from Matthews evidence"
            )
        if candidate.matthews_evidence is not _matthews_level(
            self.total_composition_evidence
        ):
            raise ValueError("candidate Matthews level differs from copy evidence")
        explicit_levels = (
            candidate.localisation_evidence,
            candidate.sds_page_evidence,
            candidate.native_page_evidence,
            candidate.matthews_evidence,
            candidate.model_quality_evidence,
            candidate.structural_diversity_evidence,
        )
        if any(value is None for value in explicit_levels):
            raise ValueError("generated candidate contains implicit ranking evidence")
        if candidate.localisation_evidence is not _localisation_level(
            self.first_wave_disposition
        ):
            raise ValueError("candidate localisation level differs from wave policy")
        if self.first_wave_disposition is not localisation_first_wave_disposition(
            self.localisation_outcome
        ):
            raise ValueError("localisation outcome differs from first-wave disposition")
        expected_first_wave = (
            self.first_wave_disposition is not FirstWaveDisposition.EXCLUDED
        )
        if self.first_wave_eligible != expected_first_wave:
            raise ValueError("first-wave eligibility differs from localisation policy")
        if (
            self.reopened
            and self.first_wave_disposition is not FirstWaveDisposition.EXCLUDED
        ):
            raise ValueError("only an excluded group may be reopened")
        if self.wave_eligible != (self.first_wave_eligible or self.reopened):
            raise ValueError("wave eligibility differs from first-wave/reopen state")
        if candidate.localisation_wave_eligible != self.wave_eligible:
            raise ValueError("planner localisation flag differs from wave eligibility")
        if not candidate.reviewer_allowed:
            raise ValueError("candidate generation cannot fabricate a reviewer hold")
        if candidate.model_available != (
            self.selected_model_registry_entry_sha256 is not None
        ):
            raise ValueError("candidate model availability lacks registry evidence")
        if candidate.model_identity_supported != candidate.model_available:
            raise ValueError("candidate model identity support lacks registry evidence")
        return self


class ParentCandidateCoverage(ContractModel):
    """Exact represented and retained catalogue groups for one parent."""

    schema_version: Literal["2.0"] = "2.0"
    parent_rank: PositiveInt = Field(le=3)
    parent_state_id: CompositionStateIdentifier
    represented_sequence_group_ids: tuple[SequenceGroupIdentifier, ...] = Field(
        min_length=1,
        max_length=5,
    )
    candidate_sequence_group_ids: tuple[SequenceGroupIdentifier, ...]

    @model_validator(mode="after")
    def _validate_partition(self) -> Self:
        represented = set(self.represented_sequence_group_ids)
        candidates = set(self.candidate_sequence_group_ids)
        if len(represented) != len(self.represented_sequence_group_ids):
            raise ValueError("duplicate represented sequence group")
        if len(candidates) != len(self.candidate_sequence_group_ids):
            raise ValueError("duplicate retained candidate sequence group")
        if represented & candidates:
            raise ValueError("represented group remains in candidate coverage")
        return self


class ComponentExpansionInputInventory(ContractModel):
    """Complete deterministic candidate-generation inventory for one depth."""

    _identity_prefix: ClassVar[str] = "compinputgen_"

    schema_version: Literal["2.0"] = "2.0"
    generator_version: Literal["phase3-component-candidate-generation-v1"] = (
        _GENERATOR_VERSION
    )
    inventory_id: NonEmptyString
    crystal_id: NonEmptyString
    diffraction_dataset_id: NonEmptyString
    parent_depth: PositiveInt = Field(le=5)
    target_component_label: Literal["B", "C", "D", "E", "F"]
    catalogue_sequence_group_ids: tuple[SequenceGroupIdentifier, ...] = Field(
        min_length=1
    )
    parent_state_ids: tuple[CompositionStateIdentifier, ...] = Field(
        min_length=1,
        max_length=3,
    )
    parent_coverages: tuple[ParentCandidateCoverage, ...] = Field(
        min_length=1,
        max_length=3,
    )
    catalogue_groups_sha256: Sha256Hex
    localisation_policy_id: NonEmptyString
    active_wave_completion_id: NonEmptyString
    localisation_reopen_plan_id: NonEmptyString
    gel_evidence_sha256: Sha256Hex
    matthews_contexts_sha256: Sha256Hex
    model_registry_id: AllModelRegistryIdentifier
    model_ranking_evidence_sha256: Sha256Hex
    catalogue_group_count: PositiveInt
    parent_count: PositiveInt = Field(le=3)
    represented_group_occurrence_count: int = Field(ge=0)
    expected_candidate_row_count: int = Field(ge=0)
    candidate_row_count: int = Field(ge=0)
    first_wave_eligible_row_count: int = Field(ge=0)
    retained_first_wave_excluded_row_count: int = Field(ge=0)
    reopened_row_count: int = Field(ge=0)
    wave_eligible_row_count: int = Field(ge=0)
    model_available_row_count: int = Field(ge=0)
    model_unavailable_row_count: int = Field(ge=0)
    total_composition_copy_evidence_count: int = Field(ge=0)
    assessed_copy_evidence_count: int = Field(ge=0)
    unassessed_copy_evidence_count: int = Field(ge=0)
    physically_eligible_copy_hypothesis_count: int = Field(ge=0)
    selection_semantics: Literal[
        "scheduling_prior_only_no_identity_or_composition_support"
    ] = "scheduling_prior_only_no_identity_or_composition_support"
    rows: tuple[GeneratedComponentExpansionRow, ...]

    @classmethod
    def from_rows(cls, **values: object) -> Self:
        """Build a content-addressed inventory from complete normalised values."""

        payload = {"schema_version": "2.0", **values}
        payload.setdefault("generator_version", _GENERATOR_VERSION)
        payload.setdefault(
            "selection_semantics",
            "scheduling_prior_only_no_identity_or_composition_support",
        )
        return cls.model_validate(
            {
                **payload,
                "inventory_id": content_id(cls._identity_prefix, payload),
            }
        )

    @model_validator(mode="after")
    def _validate_inventory(self) -> Self:
        expected_order = tuple(
            sorted(
                self.rows,
                key=lambda item: (
                    item.parent_rank,
                    item.component_input.candidate_rank,
                    item.sequence_group_id,
                ),
            )
        )
        if self.rows != expected_order:
            raise ValueError("candidate rows are not deterministically ordered")
        if self.parent_count != len(self.parent_state_ids):
            raise ValueError("parent count differs from parent identities")
        if self.target_component_label != _COMPONENT_LABELS[self.parent_depth]:
            raise ValueError("target component label differs from parent depth")
        if len(set(self.parent_state_ids)) != len(self.parent_state_ids):
            raise ValueError("duplicate parent state identity")
        if self.catalogue_sequence_group_ids != tuple(
            sorted(self.catalogue_sequence_group_ids)
        ) or len(set(self.catalogue_sequence_group_ids)) != len(
            self.catalogue_sequence_group_ids
        ):
            raise ValueError("catalogue sequence groups are incomplete or unordered")
        if self.catalogue_group_count != len(self.catalogue_sequence_group_ids):
            raise ValueError("catalogue count differs from its sequence groups")
        if len(self.parent_coverages) != self.parent_count:
            raise ValueError("parent coverages differ from parent count")
        if any(
            len(item.represented_sequence_group_ids) != self.parent_depth
            for item in self.parent_coverages
        ):
            raise ValueError("parent coverage differs from parent depth")
        if (
            tuple(item.parent_rank for item in self.parent_coverages)
            != tuple(range(1, self.parent_count + 1))
            or tuple(item.parent_state_id for item in self.parent_coverages)
            != self.parent_state_ids
        ):
            raise ValueError("parent coverages differ from ranked parent identities")
        row_keys = tuple(
            (row.parent_state_id, row.sequence_group_id) for row in self.rows
        )
        if len(set(row_keys)) != len(row_keys):
            raise ValueError("duplicate parent/catalogue candidate row")
        for parent_rank, parent_state_id in enumerate(self.parent_state_ids, start=1):
            ranks = tuple(
                row.component_input.candidate_rank
                for row in self.rows
                if row.parent_state_id == parent_state_id
            )
            if ranks != tuple(range(1, len(ranks) + 1)):
                raise ValueError("candidate ranks are not contiguous within parent")
            if any(
                row.parent_rank != parent_rank
                for row in self.rows
                if row.parent_state_id == parent_state_id
            ):
                raise ValueError("candidate row parent rank is inconsistent")
            coverage = self.parent_coverages[parent_rank - 1]
            row_groups = tuple(
                row.sequence_group_id
                for row in self.rows
                if row.parent_state_id == parent_state_id
            )
            if row_groups != coverage.candidate_sequence_group_ids:
                raise ValueError("candidate rows differ from parent coverage")
            if set(coverage.represented_sequence_group_ids) | set(row_groups) != set(
                self.catalogue_sequence_group_ids
            ):
                raise ValueError("parent coverage does not partition the catalogue")
        covered_represented = sum(
            len(item.represented_sequence_group_ids) for item in self.parent_coverages
        )
        if self.represented_group_occurrence_count != covered_represented:
            raise ValueError("represented count differs from parent coverages")
        expected_rows = (
            self.parent_count * self.catalogue_group_count
            - self.represented_group_occurrence_count
        )
        calculated = (
            len(self.rows),
            sum(row.first_wave_eligible for row in self.rows),
            sum(
                row.first_wave_disposition is FirstWaveDisposition.EXCLUDED
                for row in self.rows
            ),
            sum(row.reopened for row in self.rows),
            sum(row.wave_eligible for row in self.rows),
            sum(row.component_input.model_available for row in self.rows),
            sum(not row.component_input.model_available for row in self.rows),
            sum(len(row.total_composition_evidence) for row in self.rows),
            sum(
                evidence.physical_status is not None
                for row in self.rows
                for evidence in row.total_composition_evidence
            ),
            sum(
                evidence.physical_status is None
                for row in self.rows
                for evidence in row.total_composition_evidence
            ),
            sum(
                evidence.physically_eligible
                for row in self.rows
                for evidence in row.total_composition_evidence
            ),
        )
        retained = (
            self.candidate_row_count,
            self.first_wave_eligible_row_count,
            self.retained_first_wave_excluded_row_count,
            self.reopened_row_count,
            self.wave_eligible_row_count,
            self.model_available_row_count,
            self.model_unavailable_row_count,
            self.total_composition_copy_evidence_count,
            self.assessed_copy_evidence_count,
            self.unassessed_copy_evidence_count,
            self.physically_eligible_copy_hypothesis_count,
        )
        if self.expected_candidate_row_count != expected_rows:
            raise ValueError("expected candidate count differs from complete catalogue")
        if retained != calculated or self.candidate_row_count != expected_rows:
            raise ValueError("candidate inventory counts differ from retained rows")
        payload = self.model_dump(mode="python", exclude={"inventory_id"})
        if self.inventory_id != content_id(self._identity_prefix, payload):
            raise ValueError("inventory_id does not match canonical inventory content")
        return self


@dataclass(frozen=True)
class ComponentExpansionInputGeneration:
    """Complete generated rows and the unbound inputs accepted by the planner."""

    parents: tuple[ParentExpansionInput, ...]
    inventory: ComponentExpansionInputInventory

    @property
    def candidates(self) -> tuple[ComponentExpansionInput, ...]:
        """Return complete deterministic planner inputs."""

        return tuple(row.component_input for row in self.inventory.rows)

    def as_request(self) -> CompositionExpansionRequest:
        """Create an unbound bounded request for registry verification/planning."""

        return CompositionExpansionRequest(
            parents=self.parents,
            candidates=self.candidates,
        )


@dataclass(frozen=True)
class _CandidateDraft:
    parent: ParentExpansionInput
    group: SequenceGroupRecord
    localisation_outcome: LocalisationOutcome
    first_wave_disposition: FirstWaveDisposition
    first_wave_eligible: bool
    reopened: bool
    wave_eligible: bool
    model_entry: AllEligibleModelEntry | None
    model_quality_evidence: ExpansionEvidenceLevel
    structural_diversity_evidence: ExpansionEvidenceLevel
    component_specs: tuple[ComponentSpec, ...]
    total_composition_evidence: tuple[TotalCompositionCopyEvidence, ...]
    localisation_evidence: ExpansionEvidenceLevel
    sds_page_evidence: ExpansionEvidenceLevel
    native_page_evidence: ExpansionEvidenceLevel
    matthews_evidence: ExpansionEvidenceLevel

    @property
    def sort_key(self) -> tuple[object, ...]:
        best_prior = max(
            (
                item.matthews_prior
                for item in self.total_composition_evidence
                if item.physically_eligible and item.matthews_prior is not None
            ),
            default=-1.0,
        )
        return (
            _EVIDENCE_ORDER[self.localisation_evidence],
            _EVIDENCE_ORDER[self.sds_page_evidence],
            _EVIDENCE_ORDER[self.native_page_evidence],
            _EVIDENCE_ORDER[self.matthews_evidence],
            _EVIDENCE_ORDER[self.model_quality_evidence],
            _EVIDENCE_ORDER[self.structural_diversity_evidence],
            -best_prior,
            self.group.sequence_group_id,
        )


def _validated_inputs(
    parents: Sequence[ParentExpansionInput],
    sequence_groups: Sequence[SequenceGroupRecord],
) -> tuple[tuple[ParentExpansionInput, ...], tuple[SequenceGroupRecord, ...]]:
    try:
        validated_parents = tuple(
            ParentExpansionInput.model_validate(item.model_dump(mode="python"))
            for item in parents
        )
        if any(parent.model_resolutions for parent in validated_parents):
            raise CandidateGenerationError(
                "candidate generation requires unbound parent model inputs"
            )
        parent_request = CompositionExpansionRequest(
            parents=validated_parents,
            candidates=(),
        )
        ordered_parents = tuple(
            sorted(parent_request.parents, key=lambda item: item.parent_rank)
        )
        groups = tuple(
            sorted(
                (
                    SequenceGroupRecord.model_validate(item.model_dump(mode="python"))
                    for item in sequence_groups
                ),
                key=lambda item: item.sequence_group_id,
            )
        )
    except (TypeError, ValueError) as error:
        raise CandidateGenerationError("invalid candidate-generation input") from error
    if not groups:
        raise CandidateGenerationError("candidate catalogue is empty")
    if len({group.sequence_group_id for group in groups}) != len(groups):
        raise CandidateGenerationError("duplicate catalogue sequence group")
    catalogue_ids = {group.sequence_group_id for group in groups}
    for parent in ordered_parents:
        labels = tuple(component.label for component in parent.state.components)
        if labels != _COMPONENT_LABELS[: parent.state.depth]:
            raise CandidateGenerationError(
                "parent components are not the ordered A--F prefix"
            )
        represented = {
            component.sequence_group_id for component in parent.state.components
        }
        if not represented <= catalogue_ids:
            raise CandidateGenerationError(
                "parent component is absent from the complete catalogue"
            )
    return ordered_parents, groups


def _validated_localisation(
    policy: CatalogueLocalisationWavePolicy,
    completion: ActiveWaveCompletion,
    reopen_plan: LocalisationReopenPlan,
    groups: Sequence[SequenceGroupRecord],
) -> tuple[
    CatalogueLocalisationWavePolicy,
    ActiveWaveCompletion,
    LocalisationReopenPlan,
]:
    try:
        checked_policy = CatalogueLocalisationWavePolicy.model_validate(
            policy.model_dump(mode="python")
        )
        checked_completion = ActiveWaveCompletion.model_validate(
            completion.model_dump(mode="python")
        )
        checked_plan = LocalisationReopenPlan.model_validate(
            reopen_plan.model_dump(mode="python")
        )
    except (TypeError, ValueError) as error:
        raise CandidateGenerationError("invalid localisation wave evidence") from error
    group_index = {group.sequence_group_id: group for group in groups}
    evidence_index = {
        item.sequence_group_id: item for item in checked_policy.group_evidence
    }
    if set(evidence_index) != set(group_index):
        raise CandidateGenerationError(
            "localisation policy does not cover the complete catalogue"
        )
    if any(
        item.sequence_sha256 != group_index[group_id].sha256
        for group_id, item in evidence_index.items()
    ):
        raise CandidateGenerationError(
            "localisation policy sequence identity differs from catalogue"
        )
    if checked_completion.first_wave_group_ids != checked_policy.first_wave_group_ids:
        raise CandidateGenerationError(
            "active-wave completion differs from localisation policy"
        )
    expected_plan = LocalisationReopenPlan.from_policy(
        checked_policy,
        checked_completion,
    )
    if checked_plan != expected_plan:
        raise CandidateGenerationError(
            "reopen decision is not derived from the supplied active-wave completion"
        )
    return checked_policy, checked_completion, checked_plan


def _validated_contexts(
    contexts: Sequence[ParentMatthewsContext],
    parents: Sequence[ParentExpansionInput],
) -> dict[str, ParentMatthewsContext]:
    try:
        checked = tuple(
            ParentMatthewsContext.model_validate(item.model_dump(mode="python"))
            for item in contexts
        )
    except (TypeError, ValueError) as error:
        raise CandidateGenerationError("invalid parent Matthews context") from error
    by_parent = {item.parent_state_id: item for item in checked}
    if len(by_parent) != len(checked):
        raise CandidateGenerationError("duplicate parent Matthews context")
    if set(by_parent) != {parent.state.state_id for parent in parents}:
        raise CandidateGenerationError(
            "Matthews contexts do not cover every retained parent"
        )
    return by_parent


def _registry_inventory(
    registry: AllEligibleModelRegistry,
    groups: Sequence[SequenceGroupRecord],
) -> dict[str, SequenceGroupModelInventory]:
    inventories = {
        item.sequence_group_id: item for item in registry.manifest.sequence_groups
    }
    group_index = {group.sequence_group_id: group for group in groups}
    if set(inventories) != set(group_index):
        raise CandidateGenerationError(
            "all-model registry does not cover the complete catalogue"
        )
    if any(
        inventory.sequence_sha256 != group_index[group_id].sha256
        for group_id, inventory in inventories.items()
    ):
        raise CandidateGenerationError(
            "all-model registry sequence identity differs from catalogue"
        )
    return inventories


def _model_evidence_index(
    evidence: Sequence[ParentModelRankingEvidence],
    *,
    parents: Sequence[ParentExpansionInput],
    registry: AllEligibleModelRegistry,
) -> dict[tuple[str, str], ParentModelRankingEvidence]:
    try:
        checked = tuple(
            ParentModelRankingEvidence.model_validate(item.model_dump(mode="python"))
            for item in evidence
        )
    except (TypeError, ValueError) as error:
        raise CandidateGenerationError("invalid model-ranking evidence") from error
    parent_ids = {parent.state.state_id for parent in parents}
    registry_entries = {
        entry.model_id: entry
        for inventory in registry.manifest.sequence_groups
        for entry in inventory.models
    }
    index: dict[tuple[str, str], ParentModelRankingEvidence] = {}
    for item in checked:
        key = item.parent_state_id, item.model_id
        if key in index:
            raise CandidateGenerationError("duplicate parent/model ranking evidence")
        entry = registry_entries.get(item.model_id)
        if item.parent_state_id not in parent_ids or entry is None:
            raise CandidateGenerationError(
                "model-ranking evidence refers to an unknown parent or model"
            )
        if entry.model_sha256 != item.model_sha256:
            raise CandidateGenerationError(
                "model-ranking evidence checksum differs from registry"
            )
        index[key] = item
    return index


def _mass_bounds(
    group: SequenceGroupRecord,
) -> tuple[float | None, float | None, tuple[str, ...]]:
    if group.molecular_mass_da is not None:
        return group.molecular_mass_da, group.molecular_mass_da, ()
    if (
        group.molecular_mass_lower_da is not None
        and group.molecular_mass_upper_da is not None
    ):
        return (
            group.molecular_mass_lower_da,
            group.molecular_mass_upper_da,
            ("sequence_mass_bounded",),
        )
    return None, None, ("sequence_mass_unavailable",)


def _total_composition_evidence(
    parent: ParentExpansionInput,
    group: SequenceGroupRecord,
    context: ParentMatthewsContext,
) -> tuple[TotalCompositionCopyEvidence, ...]:
    lower, upper, mass_warnings = _mass_bounds(group)
    context_sha256 = canonical_digest(context)
    if lower is None or upper is None:
        return tuple(
            TotalCompositionCopyEvidence(
                parent_state_id=parent.state.state_id,
                sequence_group_id=group.sequence_group_id,
                copy_count=copy_count,
                matthews_context_sha256=context_sha256,
                physically_eligible=False,
                warnings=mass_warnings,
            )
            for copy_count in _COPY_COUNTS
        )
    rows: list[TotalCompositionCopyEvidence] = []
    for copy_count in _COPY_COUNTS:
        total_lower = parent.state.physical_mass_lower_da + lower * copy_count
        total_upper = parent.state.physical_mass_upper_da + upper * copy_count
        coefficient_lower = context.asu_volume_a3 / total_upper
        coefficient_upper = context.asu_volume_a3 / total_lower
        solvent_lower = 1.0 - _SOLVENT_MASS_DENSITY_DA_PER_A3 / coefficient_lower
        solvent_upper = 1.0 - _SOLVENT_MASS_DENSITY_DA_PER_A3 / coefficient_upper
        status = physical_status(
            solvent_lower,
            solvent_upper,
            minimum=context.minimum_solvent_fraction,
            maximum=context.maximum_solvent_fraction,
        )
        prior = prior_score(
            (solvent_lower + solvent_upper) / 2.0,
            minimum=context.minimum_solvent_fraction,
            maximum=context.maximum_solvent_fraction,
        )
        rows.append(
            TotalCompositionCopyEvidence(
                parent_state_id=parent.state.state_id,
                sequence_group_id=group.sequence_group_id,
                copy_count=copy_count,
                matthews_context_sha256=context_sha256,
                total_mass_lower_da=total_lower,
                total_mass_upper_da=total_upper,
                matthews_coefficient_lower=coefficient_lower,
                matthews_coefficient_upper=coefficient_upper,
                solvent_fraction_lower=solvent_lower,
                solvent_fraction_upper=solvent_upper,
                matthews_prior=prior,
                physical_status=status,
                physically_eligible=status is not PhysicalStatus.IMPOSSIBLE,
                warnings=mass_warnings,
            )
        )
    return tuple(rows)


def _intervals_overlap(
    lower_kda: float,
    upper_kda: float,
    observation: GelEvidenceObservation,
) -> bool:
    observed_lower = max(
        0.0,
        observation.apparent_mass_kda - observation.absolute_uncertainty_kda,
    )
    observed_upper = (
        observation.apparent_mass_kda + observation.absolute_uncertainty_kda
    )
    return lower_kda <= observed_upper and observed_lower <= upper_kda


def _gel_level(
    intervals_kda: Sequence[tuple[float, float]],
    observations: Sequence[GelEvidenceObservation],
    *,
    method: GelMethod,
) -> ExpansionEvidenceLevel:
    if not observations or not intervals_kda:
        return ExpansionEvidenceLevel.NEUTRAL
    matches = tuple(
        observation
        for observation in observations
        if any(
            _intervals_overlap(lower, upper, observation)
            for lower, upper in intervals_kda
        )
    )
    if not matches:
        return ExpansionEvidenceLevel.CONFLICTING
    strong = any(
        observation.band_role is SdsBandRole.DOMINANT
        and (
            method is GelMethod.NATIVE_PAGE
            or observation.condition.strip().casefold() == "reducing"
        )
        for observation in matches
    )
    return (
        ExpansionEvidenceLevel.SUPPORTING
        if strong
        else ExpansionEvidenceLevel.COMPATIBLE
    )


def _gel_evidence_levels(
    *,
    group: SequenceGroupRecord,
    copy_evidence: Sequence[TotalCompositionCopyEvidence],
    observations: Sequence[GelEvidenceObservation],
) -> tuple[ExpansionEvidenceLevel, ExpansionEvidenceLevel]:
    lower, upper, _ = _mass_bounds(group)
    sds_intervals = (
        ((lower / 1000.0, upper / 1000.0),)
        if lower is not None and upper is not None
        else ()
    )
    native_intervals = tuple(
        (item.total_mass_lower_da / 1000.0, item.total_mass_upper_da / 1000.0)
        for item in copy_evidence
        if item.physically_eligible
        and item.total_mass_lower_da is not None
        and item.total_mass_upper_da is not None
    )
    sds = tuple(item for item in observations if item.method is GelMethod.SDS_PAGE)
    native = tuple(
        item for item in observations if item.method is GelMethod.NATIVE_PAGE
    )
    return (
        _gel_level(sds_intervals, sds, method=GelMethod.SDS_PAGE),
        _gel_level(native_intervals, native, method=GelMethod.NATIVE_PAGE),
    )


def _selected_model(
    inventory: SequenceGroupModelInventory,
    *,
    parent_state_id: str,
    evidence: dict[tuple[str, str], ParentModelRankingEvidence],
) -> tuple[
    AllEligibleModelEntry | None,
    ExpansionEvidenceLevel,
    ExpansionEvidenceLevel,
]:
    neutral = ExpansionEvidenceLevel.NEUTRAL
    if not inventory.models:
        return None, neutral, neutral

    def sort_key(entry: AllEligibleModelEntry) -> tuple[object, ...]:
        ranking = evidence.get((parent_state_id, entry.model_id))
        quality = ranking.model_quality_evidence if ranking is not None else neutral
        diversity = (
            ranking.structural_diversity_evidence if ranking is not None else neutral
        )
        error = (
            entry.estimated_coordinate_error
            if entry.estimated_coordinate_error is not None
            else float("inf")
        )
        return (
            _EVIDENCE_ORDER[quality],
            _EVIDENCE_ORDER[diversity],
            -entry.retained_fraction,
            error,
            len(entry.quality_flags),
            entry.provider,
            entry.variant_type,
            entry.provider_accession,
            entry.model_id,
        )

    selected = min(inventory.models, key=sort_key)
    ranking = evidence.get((parent_state_id, selected.model_id))
    return (
        selected,
        ranking.model_quality_evidence if ranking is not None else neutral,
        ranking.structural_diversity_evidence if ranking is not None else neutral,
    )


def _component_specs(
    *,
    parent: ParentExpansionInput,
    group: SequenceGroupRecord,
    model_entry: AllEligibleModelEntry | None,
    registry_inventory: SequenceGroupModelInventory,
) -> tuple[ComponentSpec, ...]:
    exact_mass = group.molecular_mass_da
    lower_mass = group.molecular_mass_lower_da
    upper_mass = group.molecular_mass_upper_da
    warnings = list(_mass_bounds(group)[2])
    if model_entry is None:
        unavailable_payload = {
            "generator_version": _GENERATOR_VERSION,
            "sequence_group_id": group.sequence_group_id,
            "registry_inventory": registry_inventory,
            "status": "no_eligible_model",
        }
        unavailable_digest = canonical_digest(unavailable_payload)
        model_id = f"unavailable_model_{unavailable_digest}"
        model_sha256 = unavailable_digest
        model_evidence_sha256 = canonical_digest(registry_inventory)
        warnings.append("no_eligible_model_typed_placeholder")
    else:
        model_id = model_entry.model_id
        model_sha256 = model_entry.model_sha256
        model_evidence_sha256 = model_entry.processed_model_record_sha256
    label = _COMPONENT_LABELS[parent.state.depth]
    mass_evidence_sha256 = canonical_digest(group)
    return tuple(
        ComponentSpec.from_content(
            label=label,
            sequence_group_id=group.sequence_group_id,
            sequence_sha256=group.sha256,
            model_id=model_id,
            model_sha256=model_sha256,
            requested_copy_count=copy_count,
            sequence_mass_da=exact_mass,
            sequence_mass_lower_da=lower_mass,
            sequence_mass_upper_da=upper_mass,
            mass_evidence_sha256=mass_evidence_sha256,
            model_evidence_sha256=model_evidence_sha256,
            warnings=tuple(sorted(warnings)),
        )
        for copy_count in _COPY_COUNTS
    )


def _drafts(
    *,
    parents: Sequence[ParentExpansionInput],
    groups: Sequence[SequenceGroupRecord],
    policy: CatalogueLocalisationWavePolicy,
    reopen_plan: LocalisationReopenPlan,
    gel: GelEvidenceManifest,
    contexts: dict[str, ParentMatthewsContext],
    registry_inventories: dict[str, SequenceGroupModelInventory],
    model_evidence: dict[tuple[str, str], ParentModelRankingEvidence],
) -> tuple[_CandidateDraft, ...]:
    localisation = {item.sequence_group_id: item for item in policy.group_evidence}
    reopened_ids = set(reopen_plan.reopened_group_ids)
    observations = tuple(
        item
        for item in gel.observations
        if item.crystal_id == parents[0].state.crystal_id
    )
    drafts: list[_CandidateDraft] = []
    for parent in parents:
        represented = {
            component.sequence_group_id for component in parent.state.components
        }
        for group in groups:
            if group.sequence_group_id in represented:
                continue
            localisation_item = localisation[group.sequence_group_id]
            disposition = localisation_item.first_wave_disposition
            first_wave_eligible = localisation_item.first_wave_eligible
            reopened = group.sequence_group_id in reopened_ids
            wave_eligible = first_wave_eligible or reopened
            copy_evidence = _total_composition_evidence(
                parent,
                group,
                contexts[parent.state.state_id],
            )
            sds_level, native_level = _gel_evidence_levels(
                group=group,
                copy_evidence=copy_evidence,
                observations=observations,
            )
            registry_inventory = registry_inventories[group.sequence_group_id]
            model_entry, quality_level, diversity_level = _selected_model(
                registry_inventory,
                parent_state_id=parent.state.state_id,
                evidence=model_evidence,
            )
            drafts.append(
                _CandidateDraft(
                    parent=parent,
                    group=group,
                    localisation_outcome=localisation_item.merged_outcome,
                    first_wave_disposition=disposition,
                    first_wave_eligible=first_wave_eligible,
                    reopened=reopened,
                    wave_eligible=wave_eligible,
                    model_entry=model_entry,
                    model_quality_evidence=quality_level,
                    structural_diversity_evidence=diversity_level,
                    component_specs=_component_specs(
                        parent=parent,
                        group=group,
                        model_entry=model_entry,
                        registry_inventory=registry_inventory,
                    ),
                    total_composition_evidence=copy_evidence,
                    localisation_evidence=_localisation_level(disposition),
                    sds_page_evidence=sds_level,
                    native_page_evidence=native_level,
                    matthews_evidence=_matthews_level(copy_evidence),
                )
            )
    return tuple(drafts)


def build_component_expansion_inputs(
    *,
    parents: Sequence[ParentExpansionInput],
    sequence_groups: Sequence[SequenceGroupRecord],
    localisation_policy: CatalogueLocalisationWavePolicy,
    active_wave_completion: ActiveWaveCompletion,
    localisation_reopen_plan: LocalisationReopenPlan,
    gel_evidence: GelEvidenceManifest,
    matthews_contexts: Sequence[ParentMatthewsContext],
    model_registry_json: Path,
    model_ranking_evidence: Sequence[ParentModelRankingEvidence] = (),
) -> ComponentExpansionInputGeneration:
    """Join complete evidence into deterministic planner inputs without execution."""

    ordered_parents, groups = _validated_inputs(parents, sequence_groups)
    policy, completion, reopen_plan = _validated_localisation(
        localisation_policy,
        active_wave_completion,
        localisation_reopen_plan,
        groups,
    )
    try:
        checked_gel = GelEvidenceManifest.model_validate(
            gel_evidence.model_dump(mode="python")
        )
        ordered_observations: tuple[GelEvidenceObservation, ...] = tuple(
            sorted(
                checked_gel.observations,
                key=lambda item: item.observation_id,
            )
        )
        gel = GelEvidenceManifest(
            schema_version="2.0",
            observations=ordered_observations,
        )
    except (TypeError, ValueError) as error:
        raise CandidateGenerationError("invalid typed gel evidence") from error
    contexts = _validated_contexts(matthews_contexts, ordered_parents)
    try:
        registry = load_all_eligible_model_registry(model_registry_json)
    except (AllEligibleModelRegistryError, OSError) as error:
        raise CandidateGenerationError(
            "all-model registry could not be checksum verified"
        ) from error
    registry_inventories = _registry_inventory(registry, groups)
    model_evidence = _model_evidence_index(
        model_ranking_evidence,
        parents=ordered_parents,
        registry=registry,
    )
    drafts = _drafts(
        parents=ordered_parents,
        groups=groups,
        policy=policy,
        reopen_plan=reopen_plan,
        gel=gel,
        contexts=contexts,
        registry_inventories=registry_inventories,
        model_evidence=model_evidence,
    )
    rows: list[GeneratedComponentExpansionRow] = []
    for parent in ordered_parents:
        parent_drafts = sorted(
            (item for item in drafts if item.parent == parent),
            key=lambda item: item.sort_key,
        )
        for candidate_rank, draft in enumerate(parent_drafts, start=1):
            candidate = ComponentExpansionInput(
                parent_state_id=parent.state.state_id,
                candidate_rank=candidate_rank,
                component_specs=draft.component_specs,
                physically_assessed_copy_counts=tuple(
                    item.copy_count
                    for item in draft.total_composition_evidence
                    if item.physical_status is not None
                ),
                physically_eligible_copy_counts=tuple(
                    item.copy_count
                    for item in draft.total_composition_evidence
                    if item.physically_eligible
                ),
                model_available=draft.model_entry is not None,
                model_identity_supported=draft.model_entry is not None,
                localisation_wave_eligible=draft.wave_eligible,
                reviewer_allowed=True,
                model_provider=(
                    draft.model_entry.provider
                    if draft.model_entry is not None
                    else None
                ),
                model_variant_type=(
                    draft.model_entry.variant_type
                    if draft.model_entry is not None
                    else None
                ),
                localisation_evidence=draft.localisation_evidence,
                sds_page_evidence=draft.sds_page_evidence,
                native_page_evidence=draft.native_page_evidence,
                matthews_evidence=draft.matthews_evidence,
                model_quality_evidence=draft.model_quality_evidence,
                structural_diversity_evidence=(draft.structural_diversity_evidence),
            )
            rows.append(
                GeneratedComponentExpansionRow(
                    parent_rank=parent.parent_rank,
                    parent_state_id=parent.state.state_id,
                    sequence_group_id=draft.group.sequence_group_id,
                    localisation_outcome=draft.localisation_outcome,
                    first_wave_disposition=draft.first_wave_disposition,
                    first_wave_eligible=draft.first_wave_eligible,
                    reopened=draft.reopened,
                    wave_eligible=draft.wave_eligible,
                    selected_model_registry_entry_sha256=(
                        canonical_digest(draft.model_entry)
                        if draft.model_entry is not None
                        else None
                    ),
                    total_composition_evidence=draft.total_composition_evidence,
                    component_input=candidate,
                )
            )
    ordered_rows = tuple(
        sorted(
            rows,
            key=lambda item: (
                item.parent_rank,
                item.component_input.candidate_rank,
                item.sequence_group_id,
            ),
        )
    )
    represented_occurrences = sum(parent.state.depth for parent in ordered_parents)
    expected_rows = len(ordered_parents) * len(groups) - represented_occurrences
    first_wave_eligible_count = sum(row.first_wave_eligible for row in ordered_rows)
    excluded_count = sum(
        row.first_wave_disposition is FirstWaveDisposition.EXCLUDED
        for row in ordered_rows
    )
    reopened_count = sum(row.reopened for row in ordered_rows)
    wave_eligible_count = sum(row.wave_eligible for row in ordered_rows)
    model_available_count = sum(
        row.component_input.model_available for row in ordered_rows
    )
    physical_count = sum(
        item.physically_eligible
        for row in ordered_rows
        for item in row.total_composition_evidence
    )
    assessed_count = sum(
        item.physical_status is not None
        for row in ordered_rows
        for item in row.total_composition_evidence
    )
    inventory = ComponentExpansionInputInventory.from_rows(
        crystal_id=ordered_parents[0].state.crystal_id,
        diffraction_dataset_id=(ordered_parents[0].state.diffraction_dataset_id),
        parent_depth=ordered_parents[0].state.depth,
        target_component_label=_COMPONENT_LABELS[ordered_parents[0].state.depth],
        catalogue_sequence_group_ids=tuple(group.sequence_group_id for group in groups),
        parent_state_ids=tuple(parent.state.state_id for parent in ordered_parents),
        parent_coverages=tuple(
            ParentCandidateCoverage(
                parent_rank=parent.parent_rank,
                parent_state_id=parent.state.state_id,
                represented_sequence_group_ids=tuple(
                    component.sequence_group_id for component in parent.state.components
                ),
                candidate_sequence_group_ids=tuple(
                    row.sequence_group_id
                    for row in ordered_rows
                    if row.parent_state_id == parent.state.state_id
                ),
            )
            for parent in ordered_parents
        ),
        catalogue_groups_sha256=canonical_digest(tuple(groups)),
        localisation_policy_id=policy.policy_id,
        active_wave_completion_id=completion.completion_id,
        localisation_reopen_plan_id=reopen_plan.reopen_plan_id,
        gel_evidence_sha256=canonical_digest(gel),
        matthews_contexts_sha256=canonical_digest(
            tuple(contexts[parent.state.state_id] for parent in ordered_parents)
        ),
        model_registry_id=registry.manifest.registry_id,
        model_ranking_evidence_sha256=canonical_digest(
            tuple(
                sorted(
                    model_evidence.values(),
                    key=lambda item: (item.parent_state_id, item.model_id),
                )
            )
        ),
        catalogue_group_count=len(groups),
        parent_count=len(ordered_parents),
        represented_group_occurrence_count=represented_occurrences,
        expected_candidate_row_count=expected_rows,
        candidate_row_count=len(ordered_rows),
        first_wave_eligible_row_count=first_wave_eligible_count,
        retained_first_wave_excluded_row_count=excluded_count,
        reopened_row_count=reopened_count,
        wave_eligible_row_count=wave_eligible_count,
        model_available_row_count=model_available_count,
        model_unavailable_row_count=len(ordered_rows) - model_available_count,
        total_composition_copy_evidence_count=4 * len(ordered_rows),
        assessed_copy_evidence_count=assessed_count,
        unassessed_copy_evidence_count=4 * len(ordered_rows) - assessed_count,
        physically_eligible_copy_hypothesis_count=physical_count,
        rows=ordered_rows,
    )
    return ComponentExpansionInputGeneration(
        parents=ordered_parents,
        inventory=inventory,
    )


__all__ = [
    "CandidateGenerationError",
    "ComponentExpansionInputGeneration",
    "ComponentExpansionInputInventory",
    "GeneratedComponentExpansionRow",
    "ParentCandidateCoverage",
    "ParentMatthewsContext",
    "ParentModelRankingEvidence",
    "TotalCompositionCopyEvidence",
    "build_component_expansion_inputs",
]
