"""Resolve one immutable provider plan without executing provider software.

Inputs are a strict pipeline configuration and prepared-database manifest.
Outputs are one canonical aggregate plan and one canonical entry per provider.
Enabled routes bind the exact database resource identities they require;
disabled routes bind no resources and cannot schedule a provider adapter. No
external command or network request is allowed. Unsupported enablement, invalid
caps, missing resources, or unsafe output paths fail with ``ProviderPlanError``
and produce no valid plan. Entry and plan content IDs are the cache/provenance
keys. Focused tests cover enablement, caps, ESM fail-closed behaviour, resource
binding, byte determinism, CLI output, and tamper rejection.
"""

from dataclasses import dataclass
from pathlib import Path

from genome_to_diffraction.checksums import atomic_write_text, sha256_file
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    DatabaseManifest,
    DatabaseResource,
    DatabaseResourceStatus,
    EsmAtlasProviderConfig,
    PipelineConfig,
    ProviderConfig,
)
from genome_to_diffraction.schemas.providers import (
    ProviderDatabaseBinding,
    ProviderExecutionClass,
    ProviderExecutionPlan,
    ProviderKey,
    ProviderPlanEntry,
    ProviderSupportStatus,
    provider_entry_file_sha256,
)
from genome_to_diffraction.status import InputContractError

_PLAN_ADAPTER_VERSION = "provider-plan-v1"


class ProviderPlanError(InputContractError):
    """Provider policy cannot be resolved into supported immutable routes."""


@dataclass(frozen=True)
class ProviderPlanRequest:
    """Inputs controlling one side-effect-free provider-plan resolution."""

    pipeline_config: Path
    database_manifest: Path
    output_directory: Path


@dataclass(frozen=True)
class ProviderPlanOutput:
    """Canonical provider-plan files and their validated models."""

    plan: ProviderExecutionPlan
    plan_json: Path
    entry_json: dict[ProviderKey, Path]


@dataclass(frozen=True)
class _ProviderCapability:
    result_provider: str
    execution_class: ProviderExecutionClass | None
    support_status: ProviderSupportStatus
    provider_adapter_version: str | None
    required_resource_names: tuple[str, ...]


_CAPABILITIES = {
    ProviderKey.AFDB_EXACT: _ProviderCapability(
        result_provider="afdb_exact",
        execution_class=ProviderExecutionClass.NEEDS_INTERNET,
        support_status=ProviderSupportStatus.AVAILABLE,
        provider_adapter_version="afdb-exact-v1",
        required_resource_names=("coordinate_cache",),
    ),
    ProviderKey.ESM_ATLAS: _ProviderCapability(
        result_provider="esm_atlas",
        execution_class=None,
        support_status=ProviderSupportStatus.UNSUPPORTED,
        provider_adapter_version=None,
        required_resource_names=(),
    ),
    ProviderKey.FOLDSEEK_PROSTT5_PDB: _ProviderCapability(
        result_provider="foldseek_prostt5_pdb",
        execution_class=ProviderExecutionClass.LOCAL_COMPUTE,
        support_status=ProviderSupportStatus.AVAILABLE,
        provider_adapter_version="prostt5-foldseek-pdb-v4",
        required_resource_names=(
            "coordinate_cache",
            "pdb_foldseek",
            "pdb_sequences",
            "prostt5",
        ),
    ),
    ProviderKey.PDB_SEQUENCE: _ProviderCapability(
        result_provider="pdb_sequence_mmseqs",
        execution_class=ProviderExecutionClass.LOCAL_COMPUTE,
        support_status=ProviderSupportStatus.AVAILABLE,
        provider_adapter_version="pdb-sequence-mmseqs-v2",
        required_resource_names=("coordinate_cache", "pdb_sequences"),
    ),
}


def _provider_config(config: PipelineConfig, provider: ProviderKey) -> ProviderConfig:
    value = getattr(config.providers, provider.value)
    if not isinstance(value, ProviderConfig):
        raise AssertionError("provider configuration has an unexpected model")
    return value


def _resource_index(manifest: DatabaseManifest) -> dict[str, DatabaseResource]:
    by_name: dict[str, DatabaseResource] = {}
    for resource in manifest.resources:
        if resource.name in by_name:
            raise ProviderPlanError(
                f"database manifest contains duplicate resource name: {resource.name}"
            )
        by_name[resource.name] = resource
    return by_name


def _database_bindings(
    provider: ProviderKey,
    capability: _ProviderCapability,
    resources: dict[str, DatabaseResource],
) -> tuple[ProviderDatabaseBinding, ...]:
    bindings: list[ProviderDatabaseBinding] = []
    for name in capability.required_resource_names:
        resource = resources.get(name)
        if resource is None:
            raise ProviderPlanError(
                f"enabled provider {provider.value} requires database resource {name}"
            )
        if resource.status is not DatabaseResourceStatus.READY:
            raise ProviderPlanError(
                f"enabled provider {provider.value} requires ready resource {name}"
            )
        bindings.append(
            ProviderDatabaseBinding(
                resource_name=name,
                database_id=resource.database_id,
                resource_manifest_sha256=resource.manifest_sha256,
            )
        )
    return tuple(bindings)


def _entry(
    provider: ProviderKey,
    config: ProviderConfig,
    capability: _ProviderCapability,
    resources: dict[str, DatabaseResource],
) -> ProviderPlanEntry:
    if config.max_hits > 1000:
        raise ProviderPlanError(
            f"provider {provider.value} max_hits must not exceed 1000"
        )
    if config.enabled and config.max_hits < 1:
        raise ProviderPlanError(
            f"enabled provider {provider.value} requires max_hits of at least one"
        )
    if (
        config.enabled
        and capability.support_status is ProviderSupportStatus.UNSUPPORTED
    ):
        raise ProviderPlanError(
            f"provider {provider.value} is enabled, but this release has no adapter "
            "or approved compute-network route"
        )

    if config.enabled:
        if capability.execution_class is None:
            raise AssertionError("available provider lost its execution class")
        effective_max_hits = (
            min(config.max_hits, 1)
            if provider is ProviderKey.AFDB_EXACT
            else config.max_hits
        )
        execution_class = capability.execution_class
        bindings = _database_bindings(provider, capability, resources)
        disabled_reason = None
    else:
        effective_max_hits = 0
        execution_class = ProviderExecutionClass.DISABLED
        bindings = ()
        disabled_reason = "disabled_by_pipeline_config"

    requests_per_minute: int | None = None
    max_sequence_length: int | None = None
    if provider is ProviderKey.ESM_ATLAS:
        if not isinstance(config, EsmAtlasProviderConfig):
            raise AssertionError("ESM Atlas configuration has an unexpected model")
        requests_per_minute = config.requests_per_minute
        max_sequence_length = config.max_sequence_length

    document: dict[str, object] = {
        "schema_version": "1.0",
        "provider": provider.value,
        "result_provider": capability.result_provider,
        "enabled": config.enabled,
        "configured_max_hits": config.max_hits,
        "effective_max_hits": effective_max_hits,
        "execution_class": execution_class.value,
        "support_status": capability.support_status.value,
        "provider_adapter_version": capability.provider_adapter_version,
        "database_resources": [item.model_dump(mode="json") for item in bindings],
        "requests_per_minute": requests_per_minute,
        "max_sequence_length": max_sequence_length,
        "disabled_reason": disabled_reason,
    }
    return ProviderPlanEntry.model_validate(
        {"entry_id": content_id("providerentry_", document), **document}
    )


def resolve_provider_plan(request: ProviderPlanRequest) -> ProviderPlanOutput:
    """Resolve and write a deterministic provider plan without provider execution."""

    config_path = request.pipeline_config.resolve(strict=True)
    database_path = request.database_manifest.resolve(strict=True)
    config = load_contract(config_path, "pipeline-config", progress=False)
    database = load_contract(database_path, "database-manifest", progress=False)
    if not isinstance(config, PipelineConfig) or not isinstance(
        database, DatabaseManifest
    ):
        raise AssertionError("provider-plan contract registry returned wrong models")
    if config.providers.esm_atlas.enabled:
        raise ProviderPlanError(
            "provider esm_atlas is enabled, but this release has no adapter or "
            "approved compute-network route"
        )

    resources = _resource_index(database)
    entries = tuple(
        _entry(
            provider,
            _provider_config(config, provider),
            _CAPABILITIES[provider],
            resources,
        )
        for provider in sorted(ProviderKey, key=lambda item: item.value)
    )
    entry_sha256 = {
        entry.provider.value: provider_entry_file_sha256(entry) for entry in entries
    }
    plan_document: dict[str, object] = {
        "schema_version": "1.0",
        "adapter_version": _PLAN_ADAPTER_VERSION,
        "pipeline_config_sha256": sha256_file(config_path),
        "database_manifest_sha256": sha256_file(database_path),
        "entries": [entry.model_dump(mode="json") for entry in entries],
        "entry_sha256": entry_sha256,
        "enabled_providers": [
            entry.provider.value for entry in entries if entry.enabled
        ],
        "disabled_providers": [
            entry.provider.value for entry in entries if not entry.enabled
        ],
    }
    plan = ProviderExecutionPlan.model_validate(
        {"plan_id": content_id("providerplan_", plan_document), **plan_document}
    )

    output = request.output_directory.absolute()
    if output.exists():
        raise ProviderPlanError(f"provider-plan output already exists: {output}")
    entry_root = output / "entries"
    entry_root.mkdir(parents=True)
    entry_paths: dict[ProviderKey, Path] = {}
    for entry in entries:
        path = entry_root / f"{entry.provider.value}.json"
        atomic_write_text(path, f"{canonical_json_text(entry)}\n")
        if sha256_file(path) != plan.entry_sha256[entry.provider]:
            raise ProviderPlanError(
                f"provider entry checksum verification failed: {entry.provider.value}"
            )
        entry_paths[entry.provider] = path
    plan_path = output / "provider_plan.json"
    atomic_write_text(plan_path, f"{canonical_json_text(plan)}\n")
    return ProviderPlanOutput(plan=plan, plan_json=plan_path, entry_json=entry_paths)
