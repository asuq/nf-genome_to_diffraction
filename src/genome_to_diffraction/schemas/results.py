"""Typed scientific and execution result contracts.

These records preserve raw metrics and keep execution outcomes separate from
scientific interpretation. They contain no external-tool execution logic.
"""

import hashlib
import math
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, JsonValue, model_validator

from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    PositiveFloat,
    PositiveInt,
    Sha256Hex,
    UtcTimestamp,
)
from genome_to_diffraction.schemas.manifests import PrototypeProfile, SdsPageCondition
from genome_to_diffraction.status import ExecutionStatus, ScientificStatus


class SequenceGroupRecord(ContractModel):
    """One canonical exact amino-acid sequence and its mass assessment."""

    schema_version: Literal["1.0"]
    sequence_group_id: NonEmptyString
    sha256: Sha256Hex
    sequence: NonEmptyString
    length_aa: PositiveInt
    molecular_mass_da: PositiveFloat | None = None
    molecular_mass_lower_da: PositiveFloat | None = None
    molecular_mass_upper_da: PositiveFloat | None = None
    mass_method: NonEmptyString
    residue_policy: NonEmptyString
    source_record_count: PositiveInt
    quality_flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_content_identity_and_mass(self) -> Self:
        if self.sequence != "".join(self.sequence.split()).upper():
            raise ValueError("sequence must already be canonical uppercase text")
        if self.length_aa != len(self.sequence):
            raise ValueError("length_aa does not match sequence length")
        digest = hashlib.sha256(self.sequence.encode("ascii")).hexdigest()
        if self.sha256 != digest:
            raise ValueError("sha256 does not match canonical sequence")
        if self.sequence_group_id != f"seq_{digest}":
            raise ValueError("sequence_group_id does not match canonical sequence")
        if (self.molecular_mass_lower_da is None) != (
            self.molecular_mass_upper_da is None
        ):
            raise ValueError("mass lower and upper bounds must be supplied together")
        if (
            self.molecular_mass_lower_da is not None
            and self.molecular_mass_upper_da is not None
            and self.molecular_mass_lower_da > self.molecular_mass_upper_da
        ):
            raise ValueError("mass lower bound must not exceed upper bound")
        return self


class SourceProteinRecord(ContractModel):
    """One original catalogue protein linked to an exact sequence group."""

    schema_version: Literal["1.0"]
    source_record_id: NonEmptyString
    catalogue_id: NonEmptyString
    original_protein_id: NonEmptyString
    original_header: NonEmptyString
    description: str | None = None
    sequence_group_id: NonEmptyString
    locus_tag: str | None = None
    contig: str | None = None
    start: PositiveInt | None = None
    end: PositiveInt | None = None
    strand: Literal["+", "-", "."] | None = None
    gene_name: str | None = None
    product: str | None = None
    source_annotation_provider: NonEmptyString
    quality_flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _ordered_coordinates(self) -> Self:
        if (self.start is None) != (self.end is None):
            raise ValueError("start and end must be supplied together")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start must not exceed end")
        return self


class EligibilityStatus(StrEnum):
    """Machine-readable structural-hit eligibility."""

    SELECTED = "selected"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class SearchScientificStatus(StrEnum):
    """Scientific interpretation of one completed provider query."""

    HITS_FOUND = "hits_found"
    NO_HIT = "no_hit"
    NOT_INTERPRETABLE = "not_interpretable"


class StructuralSearchHit(ContractModel):
    """Normalised provider hit with provider-specific metrics left nullable."""

    schema_version: Literal["1.0"]
    hit_id: NonEmptyString
    sequence_group_id: NonEmptyString
    provider: NonEmptyString
    provider_rank: PositiveInt
    target_id: NonEmptyString
    model_key: NonEmptyString
    target_chain_or_entity: str | None = None
    pdb_id: str | None = Field(default=None, pattern=r"^[0-9A-Za-z]{4}$")
    identifier_namespace: str | None = None
    query_start: PositiveInt | None = None
    query_end: PositiveInt | None = None
    target_start: PositiveInt | None = None
    target_end: PositiveInt | None = None
    aligned_length: PositiveInt | None = None
    query_coverage: float | None = Field(default=None, ge=0, le=1)
    target_coverage: float | None = Field(default=None, ge=0, le=1)
    sequence_identity: float | None = Field(default=None, ge=0, le=1)
    evalue: float | None = Field(default=None, ge=0)
    bits: float | None = None
    probability: float | None = Field(default=None, ge=0, le=1)
    database_id: NonEmptyString
    raw_result_pointer: NonEmptyString
    raw_metrics: dict[str, JsonValue] = Field(default_factory=dict)
    eligibility_status: EligibilityStatus
    eligibility_reason: NonEmptyString


class StructuralSearchResult(ContractModel):
    """One provider query with explicit execution and scientific outcomes."""

    schema_version: Literal["1.0"]
    search_id: NonEmptyString
    sequence_group_id: NonEmptyString
    provider: NonEmptyString
    database_id: NonEmptyString
    tool: NonEmptyString
    tool_version: NonEmptyString
    adapter_version: NonEmptyString
    cache_key: Sha256Hex
    execution_status: ExecutionStatus
    scientific_status: SearchScientificStatus
    hit_count: int = Field(ge=0)
    hits: tuple[StructuralSearchHit, ...] = ()
    raw_result_pointer: NonEmptyString
    raw_result_sha256: Sha256Hex
    command_log_pointer: NonEmptyString
    command_log_sha256: Sha256Hex
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _statuses_match_hits(self) -> Self:
        if self.hit_count != len(self.hits):
            raise ValueError("hit_count does not match hits")
        if self.execution_status is ExecutionStatus.COMPLETED_HIT:
            if self.scientific_status is not SearchScientificStatus.HITS_FOUND:
                raise ValueError("completed_hit requires hits_found")
            if not self.hits:
                raise ValueError("completed_hit requires at least one hit")
        elif self.execution_status is ExecutionStatus.COMPLETED_NO_HIT:
            if self.scientific_status is not SearchScientificStatus.NO_HIT:
                raise ValueError("completed_no_hit requires no_hit")
            if self.hits:
                raise ValueError("completed_no_hit cannot contain hits")
        elif self.execution_status in {
            ExecutionStatus.SKIPPED_POLICY,
            ExecutionStatus.SKIPPED_INELIGIBLE,
        }:
            if self.scientific_status is not SearchScientificStatus.NOT_INTERPRETABLE:
                raise ValueError("skipped search must be not_interpretable")
            if self.hits:
                raise ValueError("skipped search cannot contain hits")
        else:
            raise ValueError("structural-search result has unsupported terminal status")
        for hit in self.hits:
            if (
                hit.sequence_group_id != self.sequence_group_id
                or hit.provider != self.provider
                or hit.database_id != self.database_id
            ):
                raise ValueError("hit identity does not match its search result")
        return self


class CoordinateSourceRecord(ContractModel):
    """Immutable experimental or predicted coordinate source."""

    schema_version: Literal["1.0"]
    coordinate_id: NonEmptyString
    provider: NonEmptyString
    provider_accession: NonEmptyString
    retrieval_date: UtcTimestamp
    source_release: str | None = None
    coordinate_path: NonEmptyString
    coordinate_sha256: Sha256Hex
    source_sequence_sha256: Sha256Hex | None = None
    confidence_summary: dict[str, JsonValue] = Field(default_factory=dict)
    license_or_provenance: NonEmptyString


class ProcessedModelRecord(ContractModel):
    """MR-ready model derived from an immutable coordinate source."""

    schema_version: Literal["1.0"]
    model_id: NonEmptyString
    coordinate_id: NonEmptyString
    variant_type: NonEmptyString
    residue_ranges: tuple[str, ...]
    processing_tool: NonEmptyString
    processing_version: NonEmptyString
    processing_parameters: dict[str, JsonValue] = Field(default_factory=dict)
    estimated_coordinate_error: float | None = Field(default=None, ge=0)
    model_mass_da: PositiveFloat
    full_candidate_sequence_group_id: NonEmptyString
    model_sha256: Sha256Hex
    quality_flags: tuple[str, ...] = ()


class PhysicalStatus(StrEnum):
    """Physical plausibility class for an ASU composition."""

    PLAUSIBLE = "plausible"
    IMPOSSIBLE = "impossible"
    REVIEW = "review"


class MatthewsHypothesis(ContractModel):
    """One candidate-specific ASU copy hypothesis."""

    schema_version: Literal["1.0"]
    hypothesis_id: NonEmptyString
    crystal_id: NonEmptyString
    sequence_group_id: NonEmptyString
    copy_count: PositiveInt
    sequence_mass_da: PositiveFloat | None = None
    sequence_mass_lower_da: PositiveFloat | None = None
    sequence_mass_upper_da: PositiveFloat | None = None
    total_mass_da: PositiveFloat | None = None
    total_mass_lower_da: PositiveFloat | None = None
    total_mass_upper_da: PositiveFloat | None = None
    v_asu_a3: PositiveFloat
    matthews_coefficient: PositiveFloat | None = None
    matthews_coefficient_lower: PositiveFloat | None = None
    matthews_coefficient_upper: PositiveFloat | None = None
    solvent_fraction: float | None = None
    solvent_fraction_lower: float | None = None
    solvent_fraction_upper: float | None = None
    matthews_prior: float = Field(ge=0, le=1)
    prior_backend: NonEmptyString
    rank_within_candidate: PositiveInt
    retained: bool
    physical_status: PhysicalStatus
    sds_page_nearest_band_kda: PositiveFloat | None = None
    sds_page_absolute_difference_kda: float | None = Field(default=None, ge=0)
    sds_page_fractional_difference: float | None = Field(default=None, ge=0)
    sds_page_prior_label: Literal["strong", "compatible", "weak", "unavailable"]
    sds_page_condition: SdsPageCondition | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _mass_representation_is_explicit(self) -> Self:
        exact = self.sequence_mass_da is not None
        bounded = (
            self.sequence_mass_lower_da is not None
            or self.sequence_mass_upper_da is not None
        )
        if exact == bounded:
            raise ValueError("supply either exact sequence mass or both mass bounds")
        if bounded and (
            self.sequence_mass_lower_da is None or self.sequence_mass_upper_da is None
        ):
            raise ValueError("both mass bounds are required")
        exact_metrics = (
            self.total_mass_da,
            self.matthews_coefficient,
            self.solvent_fraction,
        )
        bounded_metrics = (
            self.total_mass_lower_da,
            self.total_mass_upper_da,
            self.matthews_coefficient_lower,
            self.matthews_coefficient_upper,
            self.solvent_fraction_lower,
            self.solvent_fraction_upper,
        )
        if exact and any(value is None for value in exact_metrics):
            raise ValueError("exact sequence mass requires exact Matthews metrics")
        if exact and any(value is not None for value in bounded_metrics):
            raise ValueError("exact sequence mass cannot use bounded Matthews metrics")
        if bounded and any(value is None for value in bounded_metrics):
            raise ValueError("bounded sequence mass requires bounded Matthews metrics")
        if bounded and any(value is not None for value in exact_metrics):
            raise ValueError("bounded sequence mass cannot use exact Matthews metrics")
        for lower, upper, name in (
            (
                self.total_mass_lower_da,
                self.total_mass_upper_da,
                "total mass",
            ),
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
        ):
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"{name} lower bound must not exceed upper bound")
        return self


class PreflightDecision(StrEnum):
    """MTZ handling decision before candidate search."""

    PASS = "pass"
    PASS_WITH_REVIEW = "pass_with_review"
    FAIL = "fail"


class AssessmentStatus(StrEnum):
    """Normalised Xtriage assessment when a condition can be detected."""

    NOT_ASSESSED = "not_assessed"
    NOT_DETECTED = "not_detected"
    SUSPECTED = "suspected"


class MtzColumnRecord(ContractModel):
    """One independently inspected MTZ column."""

    label: NonEmptyString
    type_code: NonEmptyString
    dataset_id: int = Field(ge=0)


class MtzPreflightRecord(ContractModel):
    """Independent MTZ/Xtriage inspection result."""

    schema_version: Literal["1.0"]
    preflight_id: NonEmptyString
    crystal_id: NonEmptyString
    mtz_sha256: Sha256Hex
    selected_observation_labels: str | None = None
    selected_observation_type: Literal["intensity", "amplitude"] | None = None
    free_flag_labels: str | None = None
    free_flag_status: Literal["present", "missing", "generated"]
    unit_cell: tuple[
        PositiveFloat,
        PositiveFloat,
        PositiveFloat,
        PositiveFloat,
        PositiveFloat,
        PositiveFloat,
    ]
    space_group: NonEmptyString
    general_position_multiplicity: PositiveInt
    cell_volume_a3: PositiveFloat
    asu_volume_a3: PositiveFloat
    resolution_low_a: PositiveFloat
    resolution_high_a: PositiveFloat
    reflection_count: int = Field(ge=0)
    available_columns: tuple[MtzColumnRecord, ...] = ()
    observation_candidates: tuple[str, ...] = ()
    completeness: float | None = Field(default=None, ge=0, le=1)
    mean_i_over_sigma: float | None = None
    anisotropy_status: AssessmentStatus = AssessmentStatus.NOT_ASSESSED
    tncs_status: AssessmentStatus = AssessmentStatus.NOT_ASSESSED
    twinning_status: AssessmentStatus = AssessmentStatus.NOT_ASSESSED
    symmetry_status: AssessmentStatus = AssessmentStatus.NOT_ASSESSED
    xtriage_version: str | None = None
    xtriage_command: tuple[str, ...] = ()
    xtriage_log: str | None = None
    xtriage_summary: dict[str, JsonValue] = Field(default_factory=dict)
    decision: PreflightDecision
    warning_codes: tuple[str, ...] = ()
    execution_status: ExecutionStatus

    @model_validator(mode="after")
    def _validate_geometry_and_decision(self) -> Self:
        expected_asu = self.cell_volume_a3 / self.general_position_multiplicity
        if not math.isclose(
            self.asu_volume_a3, expected_asu, rel_tol=1e-8, abs_tol=1e-6
        ):
            raise ValueError("asu_volume_a3 does not match cell volume/multiplicity")
        if self.resolution_high_a > self.resolution_low_a:
            raise ValueError("resolution_high_a must not exceed resolution_low_a")
        if self.decision is PreflightDecision.PASS and (
            self.selected_observation_labels is None
            or self.selected_observation_type is None
        ):
            raise ValueError("pass decision requires selected observations")
        return self


class FreeRGenerationRecord(ContractModel):
    """One immutable, dedicated Phenix Free-R generation operation."""

    schema_version: Literal["1.0"]
    generation_id: NonEmptyString
    source_mtz_path: NonEmptyString
    source_mtz_sha256: Sha256Hex
    output_mtz_path: NonEmptyString
    output_mtz_sha256: Sha256Hex
    free_flag_labels: NonEmptyString
    test_fraction: float = Field(gt=0, lt=1)
    maximum_free_reflections: PositiveInt
    random_seed: PositiveInt
    use_lattice_symmetry: bool
    flag_convention: Literal["cns"]
    phenix_manifest_sha256: Sha256Hex
    command: tuple[str, ...] = Field(min_length=1)
    command_log: NonEmptyString
    generated_at: UtcTimestamp


class MrSearchStage(StrEnum):
    """Bounded molecular-replacement stage."""

    FIRST_COPY = "first_copy"
    ADD_COPY = "add_copy"
    MULTI_COPY_RESCUE = "multi_copy_rescue"


class MrHypothesisStatus(StrEnum):
    """Lifecycle state of an MR hypothesis."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED_HIT = "completed_hit"
    COMPLETED_NO_HIT = "completed_no_hit"
    SKIPPED = "skipped"
    FAILED = "failed"


class MrHypothesis(ContractModel):
    """Versioned molecular-replacement hypothesis contract."""

    schema_version: Literal["1.0"]
    hypothesis_id: str
    crystal_id: str
    sequence_group_id: str
    model_id: str
    copy_count_expected: PositiveInt
    copy_number_to_search: PositiveInt
    fixed_solution_id: str | None = None
    space_group: str
    obs_labels: str | None = None
    search_stage: MrSearchStage
    resource_profile: PrototypeProfile
    priority_features: dict[str, JsonValue] = Field(default_factory=dict)
    status: MrHypothesisStatus


class NormalisedMrResult(ContractModel):
    """Normalised MR result that does not conflate no-hit with failure."""

    schema_version: Literal["1.0"]
    hypothesis_id: NonEmptyString
    tool_version: NonEmptyString
    execution_status: ExecutionStatus
    llg: float | None = None
    llgi: float | None = None
    tfz: float | None = None
    placed_copy_count: int = Field(ge=0)
    packing_summary: dict[str, JsonValue] = Field(default_factory=dict)
    solution_coordinate_path: str | None = None
    solution_coordinate_sha256: Sha256Hex | None = None
    solution_file_path: str | None = None
    rotation_file_path: str | None = None
    output_mtz_path: str | None = None
    output_mtz_sha256: Sha256Hex | None = None
    parser_warnings: tuple[str, ...] = ()
    raw_log_pointer: NonEmptyString
    preliminary_credibility_class: str | None = None
    rejection_reason: str | None = None


class ReviewDecision(ContractModel):
    """One immutable human checkpoint decision."""

    checkpoint: Literal["mr_seed", "sequence_candidate"]
    item_id: NonEmptyString
    decision: Literal["approve", "reject", "defer", "retain_alternative"]
    reviewer: NonEmptyString
    reviewed_at: UtcTimestamp
    comment: str | None = None
    override_reason: str | None = None


class ReviewDecisionManifest(ContractModel):
    """Collection of non-conflicting human decisions."""

    schema_version: Literal["1.0"]
    decisions: tuple[ReviewDecision, ...]

    @model_validator(mode="after")
    def _unique_items_per_checkpoint(self) -> Self:
        keys = [(item.checkpoint, item.item_id) for item in self.decisions]
        if len(keys) != len(set(keys)):
            raise ValueError("review decisions duplicate a checkpoint/item_id pair")
        return self


class PrototypeAssumptionStatus(StrEnum):
    """Evidence for or against the single-species ASU assumption."""

    CONSISTENT = "consistent"
    POSSIBLY_VIOLATED = "possibly_violated"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


class ScientificStatusRecord(ContractModel):
    """Terminal per-crystal outcome and provenance summary."""

    schema_version: Literal["1.0"]
    crystal_id: NonEmptyString
    execution_status: ExecutionStatus
    scientific_status: ScientificStatus
    prototype_assumption_status: PrototypeAssumptionStatus
    credible_seed_count: int = Field(ge=0)
    approved_seed_count: int = Field(ge=0)
    primary_sequence_groups: tuple[str, ...] = ()
    extended_sequence_groups: tuple[str, ...] = ()
    best_supported_copy_counts: dict[str, PositiveInt] = Field(default_factory=dict)
    residual_content_suspected: bool
    warnings: tuple[str, ...] = ()
    completed_at: UtcTimestamp
    provenance_pointers: tuple[NonEmptyString, ...] = Field(min_length=1)
