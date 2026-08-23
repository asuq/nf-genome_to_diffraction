"""Phase III contracts for one immutable diffraction-data selection.

These records bind one crystal to one checksum-qualified MTZ interpretation:
the MTZ-internal observation dataset, observation labels/type, selected space
group, resolution limits, and the source of every override.  Free-R records are
separate because their raw HKL-to-flag identity can be validated without
guessing which integer value denotes the test set or claiming that a Phenix
adapter already propagates the selection.

``DiffractionBoundHypothesis`` makes the complete legacy hypothesis payload and
the diffraction selection part of a new Phase III identity without changing or
reinterpreting the version-1 hypothesis.  ``DiffractionCommandBinding`` records
which selected values are explicit external-tool arguments and which are only
verified against the checksum-bound MTZ/preflight while a supported Phenix
parameter remains to be qualified.
"""

from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    PositiveFloat,
    PositiveInt,
    Sha256Hex,
)
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract

DiffractionDatasetIdentifier = Annotated[
    str,
    Field(pattern=r"^diffraction_[a-f0-9]{64}$"),
]
DiffractionSelectionIdentifier = Annotated[
    str,
    Field(pattern=r"^diffsel_[a-f0-9]{64}$"),
]
PhaseIIIHypothesisIdentifier = Annotated[
    str,
    Field(pattern=r"^mrhyp2_[a-f0-9]{64}$"),
]
DiffractionCommandBindingIdentifier = Annotated[
    str,
    Field(pattern=r"^diffbind_[a-f0-9]{64}$"),
]
FreeRIdentityIdentifier = Annotated[
    str,
    Field(pattern=r"^freerid_[a-f0-9]{64}$"),
]
FreeRMembershipComparisonIdentifier = Annotated[
    str,
    Field(pattern=r"^freercompare_[a-f0-9]{64}$"),
]


class DiffractionValueSource(StrEnum):
    """Origin of one selected diffraction value."""

    MTZ_PREFLIGHT_AUTOMATIC = "mtz_preflight_automatic"
    MTZ_HEADER = "mtz_header"
    MTZ_RESOLUTION_RANGE = "mtz_resolution_range"
    CRYSTAL_MANIFEST_OVERRIDE = "crystal_manifest_override"


class FreeRConventionStatus(StrEnum):
    """Whether a test value is unresolved or was supplied explicitly."""

    UNRESOLVED = "unresolved_raw_flag_values_only"
    EXPLICIT_TEST_VALUE = "explicit_test_value_supplied"


class FreeRFlagCount(ContractModel):
    """Exact count for one observed integral Free-R flag value."""

    flag_value: int
    reflection_count: PositiveInt


class FreeRDistributionSummary(ContractModel):
    """Complete non-constant distribution of validated integral flag values."""

    validation_status: Literal["validated_finite_integral_non_constant"] = (
        "validated_finite_integral_non_constant"
    )
    reflection_count: PositiveInt
    distinct_flag_values: int = Field(ge=2)
    flag_counts: tuple[FreeRFlagCount, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def _validate_distribution(self) -> Self:
        values = tuple(item.flag_value for item in self.flag_counts)
        if values != tuple(sorted(set(values))):
            raise ValueError("Free-R flag counts must be unique and sorted by value")
        if self.distinct_flag_values != len(values):
            raise ValueError("distinct Free-R flag count does not match distribution")
        if sum(item.reflection_count for item in self.flag_counts) != (
            self.reflection_count
        ):
            raise ValueError("Free-R flag counts do not cover every reflection")
        return self


class FreeRIdentity(_ContentAddressedContract):
    """Dataset-qualified raw Free-R mapping for one selected source MTZ.

    The membership digest commits the exact sorted ``(H, K, L, raw_flag)``
    rows.  It deliberately does not convert the raw flags to work/test booleans
    while ``convention_status`` is unresolved.
    """

    _identity_field: ClassVar[str] = "free_r_identity_id"
    _identity_prefix: ClassVar[str] = "freerid_"

    schema_version: Literal["2.0"]
    free_r_identity_id: FreeRIdentityIdentifier
    diffraction_selection_id: DiffractionSelectionIdentifier
    diffraction_dataset_id: DiffractionDatasetIdentifier
    crystal_id: NonEmptyString
    mtz_sha256: Sha256Hex
    observation_dataset_id: int = Field(ge=0)
    free_r_dataset_id: int = Field(ge=0)
    free_r_label: NonEmptyString
    free_r_type_code: Literal["I"] = "I"
    distribution: FreeRDistributionSummary
    hkl_set_sha256: Sha256Hex
    hkl_set_digest_algorithm: Literal["sha256_nf_gtd_sorted_be_int64_hkl_v1"] = (
        "sha256_nf_gtd_sorted_be_int64_hkl_v1"
    )
    hkl_to_flag_membership_sha256: Sha256Hex
    membership_digest_algorithm: Literal[
        "sha256_nf_gtd_sorted_be_int64_hkl_flag_v1"
    ] = "sha256_nf_gtd_sorted_be_int64_hkl_flag_v1"
    convention_status: FreeRConventionStatus
    test_flag_value: int | None = None

    @model_validator(mode="after")
    def _validate_free_r_identity(self) -> Self:
        expected_dataset_id = diffraction_dataset_id(
            crystal_id=self.crystal_id,
            mtz_sha256=self.mtz_sha256,
        )
        if self.diffraction_dataset_id != expected_dataset_id:
            raise ValueError("Free-R diffraction dataset identity is inconsistent")
        if self.free_r_dataset_id != self.observation_dataset_id:
            raise ValueError(
                "Free-R and selected observation columns must share one MTZ dataset"
            )
        observed_values = {item.flag_value for item in self.distribution.flag_counts}
        if self.convention_status is FreeRConventionStatus.UNRESOLVED:
            if self.test_flag_value is not None:
                raise ValueError(
                    "unresolved Free-R convention cannot carry a test flag value"
                )
        elif self.test_flag_value is None:
            raise ValueError(
                "explicit Free-R convention requires a supplied test flag value"
            )
        elif self.test_flag_value not in observed_values:
            raise ValueError(
                "supplied Free-R test flag value is absent from the distribution"
            )
        return self


class FreeRMembershipComparison(_ContentAddressedContract):
    """Proof that one derived MTZ preserves a selected raw Free-R mapping."""

    _identity_field: ClassVar[str] = "comparison_id"
    _identity_prefix: ClassVar[str] = "freercompare_"

    schema_version: Literal["2.0"]
    comparison_id: FreeRMembershipComparisonIdentifier
    source_free_r_identity_id: FreeRIdentityIdentifier
    diffraction_selection_id: DiffractionSelectionIdentifier
    diffraction_dataset_id: DiffractionDatasetIdentifier
    crystal_id: NonEmptyString
    source_mtz_sha256: Sha256Hex
    derived_mtz_sha256: Sha256Hex
    source_free_r_dataset_id: int = Field(ge=0)
    derived_free_r_dataset_id: int = Field(ge=0)
    source_free_r_label: NonEmptyString
    derived_free_r_label: NonEmptyString
    source_distribution: FreeRDistributionSummary
    derived_distribution: FreeRDistributionSummary
    source_hkl_set_sha256: Sha256Hex
    derived_hkl_set_sha256: Sha256Hex
    source_hkl_to_flag_membership_sha256: Sha256Hex
    derived_hkl_to_flag_membership_sha256: Sha256Hex
    hkl_set_digest_algorithm: Literal["sha256_nf_gtd_sorted_be_int64_hkl_v1"] = (
        "sha256_nf_gtd_sorted_be_int64_hkl_v1"
    )
    membership_digest_algorithm: Literal[
        "sha256_nf_gtd_sorted_be_int64_hkl_flag_v1"
    ] = "sha256_nf_gtd_sorted_be_int64_hkl_flag_v1"
    convention_status: FreeRConventionStatus
    test_flag_value: int | None = None
    preservation_status: Literal["preserved_exact_hkl_to_raw_flag_mapping"] = (
        "preserved_exact_hkl_to_raw_flag_mapping"
    )

    @model_validator(mode="after")
    def _validate_preservation_claim(self) -> Self:
        expected_dataset_id = diffraction_dataset_id(
            crystal_id=self.crystal_id,
            mtz_sha256=self.source_mtz_sha256,
        )
        if self.diffraction_dataset_id != expected_dataset_id:
            raise ValueError("comparison diffraction dataset identity is inconsistent")
        expected_source_identity = FreeRIdentity.from_content(
            diffraction_selection_id=self.diffraction_selection_id,
            diffraction_dataset_id=self.diffraction_dataset_id,
            crystal_id=self.crystal_id,
            mtz_sha256=self.source_mtz_sha256,
            observation_dataset_id=self.source_free_r_dataset_id,
            free_r_dataset_id=self.source_free_r_dataset_id,
            free_r_label=self.source_free_r_label,
            distribution=self.source_distribution,
            hkl_set_sha256=self.source_hkl_set_sha256,
            hkl_to_flag_membership_sha256=(self.source_hkl_to_flag_membership_sha256),
            convention_status=self.convention_status,
            test_flag_value=self.test_flag_value,
        )
        if self.source_free_r_identity_id != (
            expected_source_identity.free_r_identity_id
        ):
            raise ValueError("comparison source Free-R identity is inconsistent")
        if self.source_free_r_dataset_id != self.derived_free_r_dataset_id:
            raise ValueError("derived Free-R dataset identity changed")
        if self.source_free_r_label != self.derived_free_r_label:
            raise ValueError("derived Free-R label changed")
        if self.source_distribution != self.derived_distribution:
            raise ValueError("derived Free-R distribution changed")
        if self.source_hkl_set_sha256 != self.derived_hkl_set_sha256:
            raise ValueError("derived MTZ HKL set changed")
        if (
            self.source_hkl_to_flag_membership_sha256
            != self.derived_hkl_to_flag_membership_sha256
        ):
            raise ValueError("derived Free-R HKL-to-flag membership changed")
        if self.convention_status is FreeRConventionStatus.UNRESOLVED:
            if self.test_flag_value is not None:
                raise ValueError("unresolved comparison cannot carry a test flag value")
        elif self.test_flag_value is None:
            raise ValueError(
                "explicit comparison convention requires a test flag value"
            )
        elif self.test_flag_value not in {
            item.flag_value for item in self.source_distribution.flag_counts
        }:
            raise ValueError(
                "comparison test flag value is absent from the distribution"
            )
        return self


class DiffractionSelection(_ContentAddressedContract):
    """One dataset-qualified and content-addressed diffraction interpretation."""

    _identity_field: ClassVar[str] = "diffraction_selection_id"
    _identity_prefix: ClassVar[str] = "diffsel_"

    schema_version: Literal["2.0"]
    diffraction_selection_id: DiffractionSelectionIdentifier
    crystal_id: NonEmptyString
    diffraction_dataset_id: DiffractionDatasetIdentifier
    mtz_sha256: Sha256Hex
    preflight_id: NonEmptyString
    preflight_record_sha256: Sha256Hex
    crystal_manifest_sha256: Sha256Hex
    observation_dataset_id: int = Field(ge=0)
    observation_labels: tuple[NonEmptyString, ...] = Field(
        min_length=2,
        max_length=4,
    )
    observation_type: Literal["intensity", "amplitude"]
    selected_space_group: NonEmptyString
    resolution_low_a: PositiveFloat
    resolution_high_a: PositiveFloat
    observation_source: DiffractionValueSource
    space_group_source: DiffractionValueSource
    resolution_low_source: DiffractionValueSource
    resolution_high_source: DiffractionValueSource
    free_r_membership_boundary: Literal[
        "identity_placeholder_only_membership_validation_pending"
    ] = "identity_placeholder_only_membership_validation_pending"

    @model_validator(mode="after")
    def _validate_selection(self) -> Self:
        expected_dataset_id = content_id(
            "diffraction_",
            {
                "crystal_id": self.crystal_id,
                "mtz_sha256": self.mtz_sha256,
            },
        )
        if self.diffraction_dataset_id != expected_dataset_id:
            raise ValueError(
                "diffraction_dataset_id does not match crystal and MTZ digest"
            )
        if len(self.observation_labels) not in {2, 4}:
            raise ValueError("observation labels must be a pair or anomalous quartet")
        if any("," in label for label in self.observation_labels):
            raise ValueError("individual observation labels cannot contain commas")
        if self.resolution_high_a > self.resolution_low_a:
            raise ValueError(
                "high-resolution limit must not exceed low-resolution limit"
            )
        if self.observation_source not in {
            DiffractionValueSource.MTZ_PREFLIGHT_AUTOMATIC,
            DiffractionValueSource.CRYSTAL_MANIFEST_OVERRIDE,
        }:
            raise ValueError(
                "observation_source is not valid for observation selection"
            )
        if self.space_group_source not in {
            DiffractionValueSource.MTZ_HEADER,
            DiffractionValueSource.CRYSTAL_MANIFEST_OVERRIDE,
        }:
            raise ValueError(
                "space_group_source is not valid for space-group selection"
            )
        resolution_sources = {
            DiffractionValueSource.MTZ_RESOLUTION_RANGE,
            DiffractionValueSource.CRYSTAL_MANIFEST_OVERRIDE,
        }
        if (
            self.resolution_low_source not in resolution_sources
            or self.resolution_high_source not in resolution_sources
        ):
            raise ValueError("resolution source is not valid for resolution selection")
        return self

    @property
    def rendered_observation_labels(self) -> str:
        """Return the verified comma-separated Phenix label value."""

        return ",".join(self.observation_labels)


class DiffractionBoundHypothesis(_ContentAddressedContract):
    """Phase III identity binding one complete v1 hypothesis to one selection."""

    _identity_field: ClassVar[str] = "hypothesis_id"
    _identity_prefix: ClassVar[str] = "mrhyp2_"

    schema_version: Literal["2.0"]
    hypothesis_id: PhaseIIIHypothesisIdentifier
    legacy_hypothesis_id: NonEmptyString
    legacy_hypothesis_sha256: Sha256Hex
    crystal_id: NonEmptyString
    diffraction_selection_id: DiffractionSelectionIdentifier
    diffraction_dataset_id: DiffractionDatasetIdentifier
    mtz_sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_dataset_identity(self) -> Self:
        expected = diffraction_dataset_id(
            crystal_id=self.crystal_id,
            mtz_sha256=self.mtz_sha256,
        )
        if self.diffraction_dataset_id != expected:
            raise ValueError(
                "bound hypothesis diffraction dataset identity is inconsistent"
            )
        return self


class DiffractionCommandConsumer(StrEnum):
    """External command record that consumes one diffraction selection."""

    FIRST_COPY_PHASER = "phase3_first_copy_phaser"
    BRIEF_REFINEMENT = "phase3_brief_refinement"


class DiffractionCommandBinding(_ContentAddressedContract):
    """Typed propagation boundary retained beside an external command array."""

    _identity_field: ClassVar[str] = "binding_id"
    _identity_prefix: ClassVar[str] = "diffbind_"

    schema_version: Literal["2.0"]
    binding_id: DiffractionCommandBindingIdentifier
    command_owner_id: NonEmptyString
    consumer: DiffractionCommandConsumer
    diffraction_selection_id: DiffractionSelectionIdentifier
    diffraction_dataset_id: DiffractionDatasetIdentifier
    mtz_sha256: Sha256Hex
    command_mtz_binding: Literal[
        "exact_selected_mtz",
        "derived_parent_mtz_recorded_derivation_verification_pending",
    ]
    observation_dataset_id: int = Field(ge=0)
    observation_labels: tuple[NonEmptyString, ...]
    observation_type: Literal["intensity", "amplitude"]
    observation_command_binding: Literal[
        "explicit_parameter_after_unique_dataset_selection"
    ] = "explicit_parameter_after_unique_dataset_selection"
    observation_dataset_binding: Literal[
        "verified_by_mtz_preflight_no_dataset_qualified_phenix_parameter"
    ] = "verified_by_mtz_preflight_no_dataset_qualified_phenix_parameter"
    selected_space_group: NonEmptyString
    space_group_command_binding: Literal[
        "verified_by_mtz_preflight_explicit_parameter_pending"
    ] = "verified_by_mtz_preflight_explicit_parameter_pending"
    resolution_low_a: PositiveFloat
    resolution_high_a: PositiveFloat
    resolution_command_binding: Literal[
        "verified_by_mtz_preflight_explicit_refinement_limits_pending",
        "sequence_from_map_high_resolution_explicit_refinement_limits_pending",
    ]
    free_r_membership_binding: Literal[
        "identity_placeholder_only_membership_validation_pending"
    ] = "identity_placeholder_only_membership_validation_pending"

    @model_validator(mode="after")
    def _validate_consumer_boundary(self) -> Self:
        if len(self.observation_labels) not in {2, 4}:
            raise ValueError("command observation labels must be a pair or quartet")
        if self.resolution_high_a > self.resolution_low_a:
            raise ValueError("command resolution limits are inverted")
        expected_resolution_binding = (
            "verified_by_mtz_preflight_explicit_refinement_limits_pending"
            if self.consumer is DiffractionCommandConsumer.FIRST_COPY_PHASER
            else "sequence_from_map_high_resolution_explicit_refinement_limits_pending"
        )
        if self.resolution_command_binding != expected_resolution_binding:
            raise ValueError("resolution command boundary does not match the consumer")
        expected_mtz_binding = (
            "exact_selected_mtz"
            if self.consumer is DiffractionCommandConsumer.FIRST_COPY_PHASER
            else "derived_parent_mtz_recorded_derivation_verification_pending"
        )
        if self.command_mtz_binding != expected_mtz_binding:
            raise ValueError("MTZ command boundary does not match the consumer")
        return self


def diffraction_dataset_id(*, crystal_id: str, mtz_sha256: str) -> str:
    """Derive the external diffraction-dataset identity from crystal and MTZ."""

    return content_id(
        "diffraction_",
        {"crystal_id": crystal_id, "mtz_sha256": mtz_sha256},
    )


__all__ = [
    "DiffractionBoundHypothesis",
    "DiffractionCommandBinding",
    "DiffractionCommandConsumer",
    "DiffractionSelection",
    "DiffractionValueSource",
    "FreeRConventionStatus",
    "FreeRDistributionSummary",
    "FreeRFlagCount",
    "FreeRIdentity",
    "FreeRMembershipComparison",
    "diffraction_dataset_id",
]
