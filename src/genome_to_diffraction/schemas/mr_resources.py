"""Deterministic resource planning contract for one Phase III Phaser task.

The resource plan is operational evidence, never candidate-quality evidence.
It binds only immutable pre-execution workload measurements and the reviewed
linear retry policy. Scientific scores, candidate rank, elapsed time, and
outcomes are deliberately absent.
"""

from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import Field, ValidationInfo, model_validator

from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    PositiveInt,
)

MrResourcePlanIdentifier = Annotated[
    str,
    Field(pattern=r"^mrresource_[a-f0-9]{64}$"),
]

MR_RESOURCE_ADAPTER_VERSION = "phase3-mr-resource-allocation-v2-overprovisioned"
MR_RESOURCE_SYMMETRY_CAP = 8
MR_RESOURCE_STANDARD_MAX_SCORE = 1_000_000_000
MR_RESOURCE_HEAVY_MAX_SCORE = 10_000_000_000
MR_RESOURCE_MAX_CPUS = 16
MR_RESOURCE_MAX_MEMORY_GB = 64
MR_RESOURCE_MAX_TIME_HOURS = 48
MR_RESOURCE_MAX_RETRIES = 1

_CONTENT_BUILD_TOKEN = object()


class MrResourceTier(StrEnum):
    """Reviewed first-attempt workload tier."""

    STANDARD = "standard"
    HEAVY = "heavy"
    VERY_HEAVY = "very_heavy"


MR_RESOURCE_TIER_RESOURCES: dict[MrResourceTier, tuple[int, int, int]] = {
    MrResourceTier.STANDARD: (8, 32, 24),
    MrResourceTier.HEAVY: (12, 48, 36),
    MrResourceTier.VERY_HEAVY: (16, 64, 48),
}


def mr_resource_tier(workload_score: int) -> MrResourceTier:
    """Return the reviewed tier for a positive workload score."""

    if workload_score <= MR_RESOURCE_STANDARD_MAX_SCORE:
        return MrResourceTier.STANDARD
    if workload_score <= MR_RESOURCE_HEAVY_MAX_SCORE:
        return MrResourceTier.HEAVY
    return MrResourceTier.VERY_HEAVY


class MrResourcePlan(ContractModel):
    """Content-addressed first-attempt resources and bounded retry policy."""

    _identity_field: ClassVar[str] = "resource_plan_id"
    _identity_prefix: ClassVar[str] = "mrresource_"

    schema_version: Literal["2.0"]
    resource_plan_id: MrResourcePlanIdentifier
    adapter_version: Literal["phase3-mr-resource-allocation-v2-overprovisioned"] = (
        MR_RESOURCE_ADAPTER_VERSION
    )
    owner_kind: Literal["mr_hypothesis", "component_execution_input"]
    owner_id: NonEmptyString
    formula: Literal[
        "reflection_count*(moving_atoms*searched_copies+fixed_atoms)*"
        "min(symmetry_multiplicity,8)"
    ] = (
        "reflection_count*(moving_atoms*searched_copies+fixed_atoms)*"
        "min(symmetry_multiplicity,8)"
    )
    reflection_count: PositiveInt
    moving_atom_count: PositiveInt
    searched_copy_count: PositiveInt
    fixed_atom_count: int = Field(ge=0)
    symmetry_multiplicity: PositiveInt
    symmetry_cost_factor: PositiveInt = Field(le=MR_RESOURCE_SYMMETRY_CAP)
    coordinate_atom_workload: PositiveInt
    workload_score: PositiveInt
    tier: MrResourceTier
    standard_max_score: Literal[1_000_000_000] = MR_RESOURCE_STANDARD_MAX_SCORE
    heavy_max_score: Literal[10_000_000_000] = MR_RESOURCE_HEAVY_MAX_SCORE
    base_cpus: PositiveInt
    base_memory_gb: PositiveInt
    base_time_hours: PositiveInt
    retry_scaling: Literal["linear_task_attempt"] = "linear_task_attempt"
    retryable_exit_status_policy: Literal["75,104,130-145,175-177"] = (
        "75,104,130-145,175-177"
    )
    retryable_failure_classes: tuple[
        Literal["transient_infrastructure"],
        Literal["scheduler_resource_or_interruption"],
    ] = (
        "transient_infrastructure",
        "scheduler_resource_or_interruption",
    )
    max_retries: Literal[1] = MR_RESOURCE_MAX_RETRIES
    max_cpus: Literal[16] = MR_RESOURCE_MAX_CPUS
    max_memory_gb: Literal[64] = MR_RESOURCE_MAX_MEMORY_GB
    max_time_hours: Literal[48] = MR_RESOURCE_MAX_TIME_HOURS

    @classmethod
    def from_content(cls, **values: Any) -> Self:
        """Validate resource content, derive its ID, then revalidate it."""

        raw = dict(values)
        raw.setdefault("schema_version", "2.0")
        raw[cls._identity_field] = f"{cls._identity_prefix}{'0' * 64}"
        provisional = cls.model_validate(
            raw,
            context={"content_build_token": _CONTENT_BUILD_TOKEN},
        )
        complete = provisional.model_dump(mode="python")
        payload = {
            key: value for key, value in complete.items() if key != cls._identity_field
        }
        complete[cls._identity_field] = content_id(cls._identity_prefix, payload)
        return cls.model_validate(complete)

    @model_validator(mode="after")
    def _validate_derived_allocation(self, info: ValidationInfo) -> Self:
        symmetry = min(self.symmetry_multiplicity, MR_RESOURCE_SYMMETRY_CAP)
        coordinate_workload = (
            self.moving_atom_count * self.searched_copy_count + self.fixed_atom_count
        )
        workload_score = self.reflection_count * coordinate_workload * symmetry
        if self.symmetry_cost_factor != symmetry:
            raise ValueError("MR resource symmetry factor is not derived")
        if self.coordinate_atom_workload != coordinate_workload:
            raise ValueError("MR resource coordinate workload is not derived")
        if self.workload_score != workload_score:
            raise ValueError("MR resource workload score is not derived")
        expected_tier = mr_resource_tier(workload_score)
        if self.tier is not expected_tier:
            raise ValueError("MR resource tier does not match workload score")
        if (
            self.base_cpus,
            self.base_memory_gb,
            self.base_time_hours,
        ) != MR_RESOURCE_TIER_RESOURCES[expected_tier]:
            raise ValueError("MR resource request does not match its tier")
        if (
            info.context is not None
            and info.context.get("content_build_token") is _CONTENT_BUILD_TOKEN
        ):
            return self
        payload = self.model_dump(mode="python", exclude={self._identity_field})
        if self.resource_plan_id != content_id(self._identity_prefix, payload):
            raise ValueError("resource_plan_id does not match canonical content")
        return self


__all__ = [
    "MR_RESOURCE_ADAPTER_VERSION",
    "MR_RESOURCE_HEAVY_MAX_SCORE",
    "MR_RESOURCE_MAX_CPUS",
    "MR_RESOURCE_MAX_MEMORY_GB",
    "MR_RESOURCE_MAX_RETRIES",
    "MR_RESOURCE_MAX_TIME_HOURS",
    "MR_RESOURCE_STANDARD_MAX_SCORE",
    "MR_RESOURCE_SYMMETRY_CAP",
    "MR_RESOURCE_TIER_RESOURCES",
    "MrResourcePlan",
    "MrResourcePlanIdentifier",
    "MrResourceTier",
    "mr_resource_tier",
]
