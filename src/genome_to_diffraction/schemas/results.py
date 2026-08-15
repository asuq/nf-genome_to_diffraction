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


class CoordinateHitMappingRecord(ContractModel):
    """Reviewable mapping from one catalogue hit to a cached PDB entity."""

    schema_version: Literal["1.0"]
    mapping_id: NonEmptyString
    hit_id: NonEmptyString
    coordinate_id: NonEmptyString
    sequence_group_id: NonEmptyString
    candidate_sequence_sha256: Sha256Hex
    pdb_id: str = Field(pattern=r"^[0-9A-Za-z]{4}$")
    identifier_namespace: NonEmptyString
    seqres_token: NonEmptyString
    entity_id: NonEmptyString
    label_asym_ids: tuple[NonEmptyString, ...] = Field(min_length=1)
    source_sequence_sha256: Sha256Hex
    source_sequence_length: PositiveInt
    query_start: PositiveInt
    query_end: PositiveInt
    target_start: PositiveInt
    target_end: PositiveInt
    aligned_length: PositiveInt
    query_coverage: float = Field(ge=0, le=1)
    target_coverage: float = Field(ge=0, le=1)
    sequence_identity: float = Field(ge=0, le=1)
    exact_sequence_match: bool

    @model_validator(mode="after")
    def _valid_alignment_ranges(self) -> Self:
        if self.query_start > self.query_end:
            raise ValueError("query_start must not exceed query_end")
        if self.target_start > self.target_end:
            raise ValueError("target_start must not exceed target_end")
        if self.target_end > self.source_sequence_length:
            raise ValueError("target alignment exceeds the PDB source sequence")
        return self


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


class AdditionalCopyResult(ContractModel):
    """One fixed-parent Phaser attempt to place one same-component copy."""

    schema_version: Literal["1.0"]
    attempt_id: NonEmptyString
    review_id: NonEmptyString
    seed_solution_id: NonEmptyString
    parent_solution_id: NonEmptyString
    child_solution_id: NonEmptyString | None = None
    hypothesis_id: NonEmptyString
    sequence_group_id: NonEmptyString
    parent_copy_count: PositiveInt
    attempted_copy_number: PositiveInt
    expected_copy_count: PositiveInt
    execution_status: ExecutionStatus
    llg: float | None = None
    llg_delta_from_parent: float | None = None
    tfz: float | None = None
    phaser_placement_count: int = Field(ge=0)
    top_solution_packed: bool
    additional_copy_supported: bool
    best_supported_copy_count: PositiveInt
    output_coordinate_path: str | None = None
    output_coordinate_sha256: Sha256Hex | None = None
    output_mtz_path: str | None = None
    output_mtz_sha256: Sha256Hex | None = None
    raw_log_pointer: NonEmptyString
    command_pointer: NonEmptyString
    parent_retained: Literal[True] = True
    failed_addition_proves_absence: Literal[False] = False
    warnings: tuple[str, ...] = ()
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def _validate_copy_transition(self) -> Self:
        if self.attempted_copy_number != self.parent_copy_count + 1:
            raise ValueError("attempted copy number must follow the parent count")
        if self.best_supported_copy_count not in {
            self.parent_copy_count,
            self.attempted_copy_number,
        }:
            raise ValueError("best supported count must be parent or attempted count")
        if self.additional_copy_supported:
            if (
                self.child_solution_id is None
                or self.output_coordinate_path is None
                or self.output_coordinate_sha256 is None
                or self.output_mtz_path is None
                or self.output_mtz_sha256 is None
                or not self.top_solution_packed
                or self.best_supported_copy_count != self.attempted_copy_number
            ):
                raise ValueError(
                    "supported additional copy lacks packed child evidence"
                )
        elif self.best_supported_copy_count != self.parent_copy_count:
            raise ValueError("unsupported addition must retain the parent count")
        return self


class CopyCountAssessment(ContractModel):
    """Matthews-intended and empirically supported count for one retained seed."""

    schema_version: Literal["1.0"]
    assessment_id: NonEmptyString
    review_id: NonEmptyString
    seed_solution_id: NonEmptyString
    hypothesis_id: NonEmptyString
    sequence_group_id: NonEmptyString
    expected_copy_count: PositiveInt
    best_supported_copy_count: PositiveInt
    attempted_transition_count: PositiveInt
    reached_expected_copy_count: bool
    final_execution_status: ExecutionStatus
    final_llg: float | None = None
    final_tfz: float | None = None
    final_llg_delta_from_parent: float | None = None
    final_top_solution_packed: bool
    final_placement_count: int = Field(ge=0)
    terminal_reason: Literal[
        "expected_copy_count_reached",
        "additional_copy_not_supported",
    ]
    parent_states_retained: Literal[True] = True
    failed_addition_proves_absence: Literal[False] = False
    review_flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_count_assessment(self) -> Self:
        if self.best_supported_copy_count > self.expected_copy_count:
            raise ValueError("supported count must not exceed expected count")
        reached = self.best_supported_copy_count == self.expected_copy_count
        if reached != self.reached_expected_copy_count:
            raise ValueError("reached-expected flag disagrees with copy counts")
        if reached != (self.terminal_reason == "expected_copy_count_reached"):
            raise ValueError("terminal reason disagrees with copy counts")
        return self


class BriefRefinementResult(ContractModel):
    """Comparable one-cycle refinement and review-map result for one finalist."""

    schema_version: Literal["1.0"]
    refinement_id: NonEmptyString
    seed_solution_id: NonEmptyString
    sequence_group_id: NonEmptyString
    input_copy_count: PositiveInt
    tool_version: NonEmptyString
    execution_status: ExecutionStatus
    initial_r_work: float | None = Field(default=None, ge=0, le=1)
    initial_r_free: float | None = Field(default=None, ge=0, le=1)
    final_r_work: float | None = Field(default=None, ge=0, le=1)
    final_r_free: float | None = Field(default=None, ge=0, le=1)
    rms_bonds: float | None = Field(default=None, ge=0)
    rms_angles: float | None = Field(default=None, ge=0)
    refined_model_path: str | None = None
    refined_model_sha256: Sha256Hex | None = None
    refined_mtz_path: str | None = None
    refined_mtz_sha256: Sha256Hex | None = None
    map_path: str | None = None
    map_sha256: Sha256Hex | None = None
    map_type: Literal["2mFo-DFc"] = "2mFo-DFc"
    difference_map_path: str | None = None
    difference_map_sha256: Sha256Hex | None = None
    difference_map_type: Literal["mFo-DFc"] = "mFo-DFc"
    map_scale: Literal["sigma"] = "sigma"
    map_region: Literal["cell"] = "cell"
    command_pointer: NonEmptyString
    raw_log_pointer: NonEmptyString
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _completed_result_has_required_assets(self) -> Self:
        if (self.difference_map_path is None) != (self.difference_map_sha256 is None):
            raise ValueError("difference-map path and checksum must be paired")
        if self.execution_status in {
            ExecutionStatus.COMPLETED_SUCCESS,
            ExecutionStatus.COMPLETED_WARNING,
        }:
            required = (
                self.refined_model_path,
                self.refined_model_sha256,
                self.refined_mtz_path,
                self.refined_mtz_sha256,
                self.map_path,
                self.map_sha256,
            )
            if any(value is None for value in required):
                raise ValueError("completed refinement lacks required model/map assets")
        return self


class SequenceMapCandidate(ContractModel):
    """One exact-sequence catalogue group ranked against a stable density map."""

    schema_version: Literal["1.0"]
    refinement_id: NonEmptyString
    rank: PositiveInt
    sequence_group_id: NonEmptyString
    sequence_length: PositiveInt
    raw_score: float
    score_z: float | None = None
    source_record_ids: tuple[NonEmptyString, ...] = Field(min_length=1)
    source_loci: tuple[NonEmptyString, ...] = ()
    segment_ranges: tuple[str, ...] = ()
    coverage: float | None = Field(default=None, ge=0, le=1)
    warnings: tuple[str, ...] = ()


class SequenceMapResult(ContractModel):
    """Full open-set catalogue ranking from one refined finalist map."""

    schema_version: Literal["1.0"]
    sequence_assessment_id: NonEmptyString
    refinement_id: NonEmptyString
    seed_solution_id: NonEmptyString
    execution_status: ExecutionStatus
    tool_version: NonEmptyString
    complete_catalogue_group_count: PositiveInt
    scored_group_count: int = Field(ge=0)
    candidates: tuple[SequenceMapCandidate, ...] = ()
    best_score: float | None = None
    mean_score: float | None = None
    score_sd: float | None = Field(default=None, ge=0)
    best_score_z: float | None = None
    command_pointer: NonEmptyString
    raw_log_pointer: NonEmptyString
    output_model_path: str | None = None
    output_model_sha256: Sha256Hex | None = None
    output_model_role: Literal[
        "map_derived_sequence_assignment_hypothesis_not_independently_refined"
    ] = "map_derived_sequence_assignment_hypothesis_not_independently_refined"
    input_map_type: Literal["2mFo-DFc"] = "2mFo-DFc"
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _ranking_is_complete_and_ordered(self) -> Self:
        if self.scored_group_count != len(self.candidates):
            raise ValueError("scored_group_count does not match candidates")
        if tuple(candidate.rank for candidate in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("sequence-map candidates are not consecutively ranked")
        if len({item.sequence_group_id for item in self.candidates}) != len(
            self.candidates
        ):
            raise ValueError("sequence-map candidates contain duplicate groups")
        if self.scored_group_count > self.complete_catalogue_group_count:
            raise ValueError("scored groups exceed complete catalogue size")
        return self


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


class ProcessResourceSummary(ContractModel):
    """Measured and allocated resources for one Nextflow invocation."""

    process_count: int = Field(ge=0)
    executed_process_count: int = Field(ge=0)
    cached_process_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    status_counts: dict[str, int]
    wall_span_seconds: float | None = Field(default=None, ge=0)
    process_realtime_seconds_sum: float | None = Field(default=None, ge=0)
    estimated_cpu_hours: float | None = Field(default=None, ge=0)
    allocated_cpu_hours: float | None = Field(default=None, ge=0)
    peak_rss_bytes: int | None = Field(default=None, ge=0)
    total_rchar_bytes: int | None = Field(default=None, ge=0)
    total_wchar_bytes: int | None = Field(default=None, ge=0)
    total_read_bytes: int | None = Field(default=None, ge=0)
    total_write_bytes: int | None = Field(default=None, ge=0)
    allocated_cpus_per_process_min: int | None = Field(default=None, ge=1)
    allocated_cpus_per_process_max: int | None = Field(default=None, ge=1)
    allocated_memory_bytes_per_process_min: int | None = Field(default=None, ge=1)
    allocated_memory_bytes_per_process_max: int | None = Field(default=None, ge=1)
    allocated_time_limit_seconds_per_process_min: float | None = Field(
        default=None, gt=0
    )
    allocated_time_limit_seconds_per_process_max: float | None = Field(
        default=None, gt=0
    )
    observed_max_concurrent_processes: int | None = Field(default=None, ge=1)
    observed_max_concurrent_allocated_cpus: int | None = Field(default=None, ge=1)
    observed_max_concurrent_allocated_memory_bytes: int | None = Field(
        default=None, ge=1
    )
    measurement_note: NonEmptyString

    @model_validator(mode="after")
    def _consistent_counts_and_ranges(self) -> Self:
        if sum(self.status_counts.values()) != self.process_count:
            raise ValueError("resource status counts do not match process_count")
        if (
            self.executed_process_count + self.cached_process_count
            != self.process_count
        ):
            raise ValueError("executed and cached counts do not match process_count")
        ranges = (
            (
                self.allocated_cpus_per_process_min,
                self.allocated_cpus_per_process_max,
            ),
            (
                self.allocated_memory_bytes_per_process_min,
                self.allocated_memory_bytes_per_process_max,
            ),
            (
                self.allocated_time_limit_seconds_per_process_min,
                self.allocated_time_limit_seconds_per_process_max,
            ),
        )
        for lower, upper in ranges:
            if (lower is None) != (upper is None):
                raise ValueError("resource allocation ranges require both bounds")
            if lower is not None and upper is not None and lower > upper:
                raise ValueError("resource allocation lower bound exceeds upper bound")
        return self


class OuterJobResourceSummary(ContractModel):
    """Measurements available from the fixed outer Slurm result contract."""

    job_id: NonEmptyString
    scheduler_state: NonEmptyString
    started_at: UtcTimestamp
    completed_at: UtcTimestamp
    elapsed_seconds: float = Field(ge=0)
    allocated_cpus: int | None = Field(default=None, ge=1)
    allocated_memory_bytes: int | None = Field(default=None, ge=1)
    peak_rss_bytes: int | None = Field(default=None, ge=0)
    measurement_note: NonEmptyString

    @model_validator(mode="after")
    def _ordered_timestamps(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("outer job completion precedes its start")
        return self


class PackageResourceInventory(ContractModel):
    """Logical size of the self-contained review package before this summary."""

    file_count_excluding_summary: int = Field(ge=0)
    total_bytes_excluding_summary: int = Field(ge=0)
    inventory_id: str = Field(pattern=r"^inventory_[a-f0-9]{64}$")
    measurement_note: NonEmptyString


class ResourceSummaryRecord(ContractModel):
    """T13.3 resource evidence kept separate from scientific interpretation."""

    schema_version: Literal["1.0"]
    summary_id: str = Field(pattern=r"^resources_[a-f0-9]{64}$")
    run_id: NonEmptyString
    site_id: NonEmptyString
    profile: NonEmptyString
    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    checkpoint_package_id: NonEmptyString
    outer_job: OuterJobResourceSummary
    first_execution: ProcessResourceSummary
    resume_execution: ProcessResourceSummary
    package_inventory: PackageResourceInventory
    database_io_bytes: int | None = Field(default=None, ge=0)
    database_io_status: Literal["measured", "not_measured", "not_applicable"]
    remote_request_count: int | None = Field(default=None, ge=0)
    remote_request_status: Literal["measured", "not_measured", "not_applicable"]
    io_measurement_semantics: NonEmptyString
    evidence_sha256: dict[str, Sha256Hex]
