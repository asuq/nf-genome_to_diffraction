"""Typed models for operator inputs and runtime manifests."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, JsonValue, model_validator

from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    OperatorIdentifier,
    PositiveFloat,
    PositiveInt,
    Sha256Hex,
    UtcTimestamp,
)


class CatalogueEntry(ContractModel):
    """One trusted protein catalogue from exactly one annotation provider."""

    catalogue_id: OperatorIdentifier
    proteome_faa: NonEmptyString
    annotation_provider: NonEmptyString
    annotation_version: NonEmptyString
    assembly_accession: str | None = None
    assembly_version: str | None = None
    genome_fasta: str | None = None
    annotation_gff: str | None = None
    annotation_gbff: str | None = None
    protein_locus_map: str | None = None
    translation_table: PositiveInt | None = None
    source_pipeline: str | None = None
    source_pipeline_version: str | None = None
    is_contaminant_catalogue: bool
    notes: str | None = None


class CatalogueManifest(ContractModel):
    """Collection of uniquely named trusted catalogues."""

    schema_version: Literal["1.0"]
    catalogues: tuple[CatalogueEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_catalogue_ids(self) -> Self:
        identifiers = [entry.catalogue_id for entry in self.catalogues]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("catalogue_id values must be unique")
        return self


class SdsPageCondition(StrEnum):
    """Conditions under which an apparent SDS-PAGE mass was measured."""

    REDUCING = "reducing"
    NONREDUCING = "nonreducing"
    UNKNOWN = "unknown"


class SdsBandRole(StrEnum):
    """Operator interpretation of an SDS-PAGE band."""

    DOMINANT = "dominant"
    MINOR = "minor"
    UNCERTAIN = "uncertain"


class CrystalEntry(ContractModel):
    """One integrated/scaled MTZ dataset and its identity universe."""

    crystal_id: OperatorIdentifier
    mtz: NonEmptyString
    catalogue_id: NonEmptyString
    obs_labels: str | None = None
    free_flag_labels: str | None = None
    space_group_override: str | None = None
    high_resolution_override: PositiveFloat | None = None
    low_resolution_override: PositiveFloat | None = None
    sds_page_mass_kda: tuple[PositiveFloat, ...] = ()
    sds_page_condition: SdsPageCondition | None = None
    sds_page_band_roles: tuple[SdsBandRole, ...] = ()
    sds_page_tolerance_fraction: float = Field(default=0.3, ge=0, le=2)
    allow_remote_sequence_submission: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def _consistent_sds_arrays_and_resolution(self) -> Self:
        if self.sds_page_band_roles and len(self.sds_page_band_roles) != len(
            self.sds_page_mass_kda
        ):
            raise ValueError("sds_page_band_roles must match sds_page_mass_kda")
        if (
            self.high_resolution_override is not None
            and self.low_resolution_override is not None
            and self.high_resolution_override > self.low_resolution_override
        ):
            raise ValueError(
                "high_resolution_override must be no larger than "
                "low_resolution_override"
            )
        return self


class CrystalManifest(ContractModel):
    """Collection of uniquely named crystal datasets."""

    schema_version: Literal["1.0"]
    crystals: tuple[CrystalEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_crystal_ids(self) -> Self:
        identifiers = [entry.crystal_id for entry in self.crystals]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("crystal_id values must be unique")
        return self


class PrototypeProfile(StrEnum):
    """Bounded execution profile."""

    SMOKE = "smoke"
    PILOT = "pilot"
    EXTENDED = "extended"


class PrototypeConfig(ContractModel):
    """Scientific prototype boundary."""

    asu_model: Literal["single_protein_species_multi_copy"]
    profile: PrototypeProfile


class AmbiguousResiduePolicy(StrEnum):
    """Configured handling of ambiguous protein residues."""

    WARN = "warn"
    EXCLUDE = "exclude"
    ERROR = "error"


class CatalogueConfig(ContractModel):
    """Catalogue-normalisation controls."""

    min_length_aa: PositiveInt
    ambiguous_residue_policy: AmbiguousResiduePolicy
    remove_terminal_stop: bool = True


class ProviderConfig(ContractModel):
    """Common provider enablement and hit cap."""

    enabled: bool
    max_hits: int = Field(ge=0)


class EsmAtlasProviderConfig(ProviderConfig):
    """Remote ESM Atlas safeguards."""

    requests_per_minute: PositiveInt
    max_sequence_length: PositiveInt


class ProvidersConfig(ContractModel):
    """Structural evidence provider configuration."""

    pdb_sequence: ProviderConfig
    foldseek_prostt5_pdb: ProviderConfig
    esm_atlas: EsmAtlasProviderConfig
    afdb_exact: ProviderConfig


class MatthewsConfig(ContractModel):
    """Candidate-specific copy enumeration controls."""

    min_copy_count: PositiveInt
    max_copy_count: PositiveInt
    max_hypotheses_per_candidate: PositiveInt
    min_solvent_fraction: float = Field(ge=0, le=1)
    max_solvent_fraction: float = Field(ge=0, le=1)
    reference_backend: Literal["phenix_xtriage", "none"] | None = None

    @model_validator(mode="after")
    def _ordered_bounds(self) -> Self:
        if self.min_copy_count > self.max_copy_count:
            raise ValueError("min_copy_count must not exceed max_copy_count")
        if self.min_solvent_fraction > self.max_solvent_fraction:
            raise ValueError(
                "min_solvent_fraction must not exceed max_solvent_fraction"
            )
        return self


class SearchLimitsConfig(ContractModel):
    """Hard caps preventing unbounded candidate expansion."""

    max_structural_hypotheses: PositiveInt
    max_first_copy_jobs: PositiveInt
    max_refinement_finalists: PositiveInt
    max_sequence_map_finalists: PositiveInt
    max_concurrent_mr_jobs: PositiveInt | None = None


class ReviewConfig(ContractModel):
    """Human checkpoint sizes and requirements."""

    primary_shortlist_size: PositiveInt
    extended_shortlist_size: PositiveInt
    require_mr_seed_checkpoint: bool
    require_sequence_checkpoint: bool

    @model_validator(mode="after")
    def _ordered_shortlists(self) -> Self:
        if self.primary_shortlist_size > self.extended_shortlist_size:
            raise ValueError(
                "primary_shortlist_size must not exceed extended_shortlist_size"
            )
        return self


class RetentionConfig(ContractModel):
    """Stable-output retention controls."""

    max_full_artifact_finalists: PositiveInt
    retain_all_logs: bool
    retain_all_normalised_results: bool


class PipelineConfig(ContractModel):
    """Resolved scientific and resource configuration."""

    schema_version: Literal["1.0"]
    prototype: PrototypeConfig
    catalogue: CatalogueConfig
    providers: ProvidersConfig
    matthews: MatthewsConfig
    search_limits: SearchLimitsConfig
    review: ReviewConfig
    retention: RetentionConfig


class PreparedWith(ContractModel):
    """Tool provenance for a prepared resource."""

    tool: NonEmptyString
    version: NonEmptyString


class SmokeTestStatus(StrEnum):
    """Outcome of a resource or executable smoke test."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


class DatabaseResourceStatus(StrEnum):
    """Integrity status of a database resource."""

    READY = "ready"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


class DatabaseResource(ContractModel):
    """One immutable prepared database or cache resource."""

    database_id: str
    name: str
    source: str
    release_or_snapshot: str | None = None
    retrieved_at: UtcTimestamp | None = None
    root_path: str
    prepared_with: PreparedWith
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    prepared_at: UtcTimestamp
    file_count: int | None = Field(default=None, ge=0)
    total_bytes: int | None = Field(default=None, ge=0)
    manifest_sha256: Sha256Hex
    smoke_test_status: SmokeTestStatus | None = None
    status: DatabaseResourceStatus
    warnings: tuple[str, ...] = ()


class DatabaseManifest(ContractModel):
    """Combined immutable inventory of prepared resources."""

    schema_version: Literal["1.0"]
    manifest_id: NonEmptyString
    created_at: UtcTimestamp
    resources: tuple[DatabaseResource, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_database_ids(self) -> Self:
        identifiers = [resource.database_id for resource in self.resources]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("database_id values must be unique")
        return self


class PlatformRecord(ContractModel):
    """Platform on which Phenix was installed and verified."""

    os: str
    architecture: str
    glibc: str | None = None
    os_version: str | None = None


class PhenixCommandRecord(ContractModel):
    """Resolution and smoke-test result for one required Phenix command."""

    name: str
    path: str
    executable_sha256: Sha256Hex | None = None
    smoke_test_status: SmokeTestStatus
    version_text: str | None = None


class PhenixInstallManifest(ContractModel):
    """Verified external Phenix installation consumed by analysis runs."""

    schema_version: Literal["1.0"]
    status: Literal["verified", "failed"]
    requested_release: str | None = None
    requested_build: str | None = None
    phenix_version: NonEmptyString
    installation_prefix: NonEmptyString
    phenix_env_sh: NonEmptyString
    phenix_env_sha256: Sha256Hex | None = None
    installer_basename: str | None = None
    installer_sha256: Sha256Hex
    platform: PlatformRecord
    installed_at: UtcTimestamp
    required_commands: tuple[PhenixCommandRecord, ...] = Field(min_length=1)
    install_log: str | None = None
    verification_log: str | None = None
    current_symlink: str | None = None
    operator_notes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _verified_runtime_is_complete(self) -> Self:
        command_names = [command.name for command in self.required_commands]
        if len(command_names) != len(set(command_names)):
            raise ValueError("required Phenix command names must be unique")
        if self.status == "verified":
            if self.phenix_env_sha256 is None:
                raise ValueError("verified Phenix manifest requires phenix_env_sha256")
            missing_digests = [
                command.name
                for command in self.required_commands
                if command.executable_sha256 is None
            ]
            if missing_digests:
                raise ValueError(
                    "verified Phenix manifest contains commands without "
                    "executable_sha256: " + ", ".join(missing_digests)
                )
            failed = [
                command.name
                for command in self.required_commands
                if command.smoke_test_status is not SmokeTestStatus.PASSED
            ]
            if failed:
                raise ValueError(
                    "verified Phenix manifest contains unverified commands: "
                    + ", ".join(failed)
                )
        return self


class RunInputRecord(ContractModel):
    """Resolved input path and content checksum retained for provenance."""

    logical_name: NonEmptyString
    path: NonEmptyString
    sha256: Sha256Hex


class CatalogueInputRecord(ContractModel):
    """Resolved catalogue input retained in the import provenance."""

    catalogue_id: NonEmptyString
    role: NonEmptyString
    path: NonEmptyString
    sha256: Sha256Hex


class OutputArtifactRecord(ContractModel):
    """One checksummed stable output from catalogue normalisation."""

    role: NonEmptyString
    path: NonEmptyString
    size_bytes: int = Field(ge=0)
    sha256: Sha256Hex


class CatalogueImportManifest(ContractModel):
    """Immutable provenance and output inventory for a catalogue import."""

    schema_version: Literal["1.0"]
    import_id: NonEmptyString
    created_at: UtcTimestamp
    software_version: NonEmptyString
    catalogue_ids: tuple[NonEmptyString, ...] = Field(min_length=1)
    catalogue_manifest_sha256: Sha256Hex
    pipeline_config_sha256: Sha256Hex
    inputs: tuple[CatalogueInputRecord, ...] = Field(min_length=1)
    outputs: tuple[OutputArtifactRecord, ...] = Field(min_length=1)
    source_record_count: PositiveInt
    sequence_group_count: PositiveInt
    warning_count: int = Field(ge=0)
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _unique_catalogues_and_outputs(self) -> Self:
        if len(self.catalogue_ids) != len(set(self.catalogue_ids)):
            raise ValueError("catalogue_ids must be unique")
        roles = [output.role for output in self.outputs]
        if len(roles) != len(set(roles)):
            raise ValueError("catalogue output roles must be unique")
        return self


class RunManifest(ContractModel):
    """Immutable resolved run identity and its versioned dependencies."""

    schema_version: Literal["1.0"]
    run_id: NonEmptyString
    created_at: UtcTimestamp
    profile: PrototypeProfile
    catalogue_manifest_sha256: Sha256Hex
    crystal_manifest_sha256: Sha256Hex
    pipeline_config_sha256: Sha256Hex
    database_manifest_id: NonEmptyString
    phenix_manifest_sha256: Sha256Hex
    inputs: tuple[RunInputRecord, ...] = Field(min_length=1)


def validate_manifest_references(
    catalogues: CatalogueManifest, crystals: CrystalManifest
) -> None:
    """Validate that every crystal uses a supplied catalogue identity universe."""

    catalogue_ids = {entry.catalogue_id for entry in catalogues.catalogues}
    missing = sorted(
        {
            entry.catalogue_id
            for entry in crystals.crystals
            if entry.catalogue_id not in catalogue_ids
        }
    )
    if missing:
        raise ValueError(
            "crystals reference unknown catalogue_id values: " + ", ".join(missing)
        )


def require_remote_submission_authorisation(
    crystal: CrystalEntry, *, run_allows_remote: bool
) -> None:
    """Require both run-level and per-crystal consent before sequence submission."""

    if not run_allows_remote:
        raise ValueError("remote sequence submission is disabled for this run")
    if not crystal.allow_remote_sequence_submission:
        raise ValueError(
            f"remote sequence submission is disabled for crystal {crystal.crystal_id}"
        )
