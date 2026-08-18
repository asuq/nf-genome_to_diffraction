"""Typed, content-addressed structural-provider execution plans.

The plan resolves operator provider policy against immutable database resources.
It contains no scheduler operation and performs no provider request. Disabled
providers remain explicit, while an enabled unsupported provider cannot form a
valid plan. Identity validation makes tampered entry or plan content fail before
it can be used as cache or execution provenance.
"""

import hashlib
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.ids import canonical_json_bytes, content_id
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    PositiveInt,
    Sha256Hex,
)


class ProviderKey(StrEnum):
    """Operator-facing structural-provider key."""

    AFDB_EXACT = "afdb_exact"
    ESM_ATLAS = "esm_atlas"
    FOLDSEEK_PROSTT5_PDB = "foldseek_prostt5_pdb"
    PDB_SEQUENCE = "pdb_sequence"


class ProviderExecutionClass(StrEnum):
    """Execution boundary required by a provider adapter."""

    DISABLED = "disabled"
    LOCAL_COMPUTE = "local_compute"
    NEEDS_INTERNET = "needs_internet"


class ProviderSupportStatus(StrEnum):
    """Whether this software version contains a routable provider adapter."""

    AVAILABLE = "available"
    UNSUPPORTED = "unsupported"


class ProviderDatabaseBinding(ContractModel):
    """One prepared database resource bound into a provider entry."""

    resource_name: NonEmptyString
    database_id: NonEmptyString
    resource_manifest_sha256: Sha256Hex


class ProviderPlanEntry(ContractModel):
    """One resolved enabled or disabled provider route."""

    schema_version: Literal["1.0"]
    entry_id: NonEmptyString
    provider: ProviderKey
    result_provider: NonEmptyString
    enabled: bool
    configured_max_hits: int = Field(ge=0, le=1000)
    effective_max_hits: int = Field(ge=0, le=1000)
    execution_class: ProviderExecutionClass
    support_status: ProviderSupportStatus
    provider_adapter_version: str | None = None
    database_resources: tuple[ProviderDatabaseBinding, ...] = ()
    requests_per_minute: PositiveInt | None = None
    max_sequence_length: PositiveInt | None = None
    disabled_reason: str | None = None

    def identity_payload(self) -> dict[str, object]:
        """Return the exact fields defining this provider entry."""

        return self.model_dump(mode="json", exclude={"entry_id"})

    @model_validator(mode="after")
    def _validate_state_and_identity(self) -> Self:
        resource_names = tuple(item.resource_name for item in self.database_resources)
        if resource_names != tuple(sorted(resource_names)) or len(
            resource_names
        ) != len(set(resource_names)):
            raise ValueError("provider database resources must be unique and sorted")
        if self.provider is ProviderKey.ESM_ATLAS:
            if self.requests_per_minute is None or self.max_sequence_length is None:
                raise ValueError("ESM Atlas entry requires rate and sequence limits")
            if self.enabled:
                raise ValueError("ESM Atlas cannot form an enabled provider entry")
        elif (
            self.requests_per_minute is not None or self.max_sequence_length is not None
        ):
            raise ValueError("only ESM Atlas may carry rate and sequence limits")
        if self.enabled:
            if self.configured_max_hits < 1 or self.effective_max_hits < 1:
                raise ValueError("enabled provider requires a positive hit cap")
            if self.execution_class is ProviderExecutionClass.DISABLED:
                raise ValueError("enabled provider cannot use the disabled route")
            if self.support_status is not ProviderSupportStatus.AVAILABLE:
                raise ValueError("enabled provider requires an available adapter")
            if self.provider_adapter_version is None:
                raise ValueError("enabled provider requires an adapter version")
            if self.disabled_reason is not None:
                raise ValueError("enabled provider cannot carry a disabled reason")
        else:
            if self.effective_max_hits != 0:
                raise ValueError("disabled provider effective hit cap must be zero")
            if self.execution_class is not ProviderExecutionClass.DISABLED:
                raise ValueError("disabled provider must use the disabled route")
            if self.database_resources:
                raise ValueError("disabled provider cannot bind database resources")
            if not self.disabled_reason:
                raise ValueError("disabled provider requires an explicit reason")
        if self.provider is ProviderKey.AFDB_EXACT and self.effective_max_hits > 1:
            raise ValueError("AFDB exact effective hit cap cannot exceed one")
        expected_id = content_id("providerentry_", self.identity_payload())
        if self.entry_id != expected_id:
            raise ValueError("provider entry ID does not match its identity payload")
        return self


def provider_entry_file_sha256(entry: ProviderPlanEntry) -> str:
    """Return the SHA-256 of the canonical newline-terminated entry file."""

    return hashlib.sha256(canonical_json_bytes(entry) + b"\n").hexdigest()


class ProviderExecutionPlan(ContractModel):
    """Complete immutable provider plan for one validated analysis config."""

    schema_version: Literal["1.0"]
    plan_id: NonEmptyString
    adapter_version: Literal["provider-plan-v1"]
    pipeline_config_sha256: Sha256Hex
    database_manifest_sha256: Sha256Hex
    entries: tuple[ProviderPlanEntry, ...] = Field(min_length=4, max_length=4)
    entry_sha256: dict[ProviderKey, Sha256Hex]
    enabled_providers: tuple[ProviderKey, ...]
    disabled_providers: tuple[ProviderKey, ...]

    def identity_payload(self) -> dict[str, object]:
        """Return the fields defining the complete provider plan."""

        return self.model_dump(mode="json", exclude={"plan_id"})

    @model_validator(mode="after")
    def _validate_inventory_and_identity(self) -> Self:
        providers = tuple(entry.provider for entry in self.entries)
        expected_providers = tuple(sorted(ProviderKey, key=lambda item: item.value))
        if providers != expected_providers:
            raise ValueError(
                "provider plan entries must contain every provider in order"
            )
        expected_enabled = tuple(
            entry.provider for entry in self.entries if entry.enabled
        )
        expected_disabled = tuple(
            entry.provider for entry in self.entries if not entry.enabled
        )
        if self.enabled_providers != expected_enabled:
            raise ValueError("enabled provider inventory differs from plan entries")
        if self.disabled_providers != expected_disabled:
            raise ValueError("disabled provider inventory differs from plan entries")
        expected_sha256 = {
            entry.provider: provider_entry_file_sha256(entry) for entry in self.entries
        }
        if self.entry_sha256 != expected_sha256:
            raise ValueError("provider entry checksum inventory is inconsistent")
        expected_id = content_id("providerplan_", self.identity_payload())
        if self.plan_id != expected_id:
            raise ValueError("provider plan ID does not match its identity payload")
        return self
