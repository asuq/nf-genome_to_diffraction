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
from genome_to_diffraction.ids import canonical_digest, canonical_json_text, content_id
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
class EnabledProviderRoute:
    """One aggregate-plan-authenticated enabled provider entry."""

    plan: ProviderExecutionPlan
    entry: ProviderPlanEntry


@dataclass(frozen=True)
class FrozenM6RawProviderAuthorisation:
    """Frozen M6 task inputs authorising its separate blind discovery envelope."""

    batch_task_json: Path
    execution_policy: Path
    software_lock: Path


@dataclass(frozen=True)
class FrozenM6RawProviderRoute:
    """One independently verified, truthless M6 raw-discovery provider route."""

    authorisation_id: str
    provider: ProviderKey
    site_id: str
    batch_task_sha256: str
    database_manifest_sha256: str
    execution_policy_sha256: str
    software_lock_sha256: str
    raw_hit_cap: int
    accepted_hit_cap: int


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
        provider_adapter_version="afdb-exact-v3",
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
        provider_adapter_version="prostt5-foldseek-pdb-v6",
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
        provider_adapter_version="pdb-sequence-mmseqs-v4",
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


def load_enabled_provider_route(
    *,
    provider_plan_json: Path,
    provider_entry_json: Path,
    database_manifest: Path,
    expected_provider: ProviderKey,
    expected_adapter_version: str,
) -> EnabledProviderRoute:
    """Authenticate one enabled route against its aggregate plan and databases."""

    plan_path = provider_plan_json.resolve(strict=True)
    entry_path = provider_entry_json.resolve(strict=True)
    database_path = database_manifest.resolve(strict=True)
    plan = load_contract(plan_path, "provider-execution-plan", progress=False)
    database = load_contract(database_path, "database-manifest", progress=False)
    if not isinstance(plan, ProviderExecutionPlan) or not isinstance(
        database, DatabaseManifest
    ):
        raise AssertionError("provider-route contract registry returned wrong models")
    try:
        entry = ProviderPlanEntry.model_validate_json(entry_path.read_bytes())
    except (OSError, ValueError) as error:
        raise ProviderPlanError(
            f"invalid provider entry {entry_path}: {error}"
        ) from error
    if entry.provider is not expected_provider:
        raise ProviderPlanError(
            f"provider entry is {entry.provider.value}, expected "
            f"{expected_provider.value}"
        )
    planned = next(
        (item for item in plan.entries if item.provider is expected_provider), None
    )
    if planned is None or entry != planned:
        raise ProviderPlanError(
            f"provider entry differs from aggregate plan: {expected_provider.value}"
        )
    if sha256_file(entry_path) != plan.entry_sha256[expected_provider]:
        raise ProviderPlanError(
            f"provider entry checksum differs from aggregate plan: "
            f"{expected_provider.value}"
        )
    if sha256_file(database_path) != plan.database_manifest_sha256:
        raise ProviderPlanError(
            "database manifest checksum differs from aggregate provider plan"
        )
    if not entry.enabled:
        raise ProviderPlanError(
            f"provider route is disabled: {expected_provider.value}"
        )
    if entry.provider_adapter_version != expected_adapter_version:
        raise ProviderPlanError(
            f"provider adapter version differs from route: {expected_provider.value}"
        )

    resources = _resource_index(database)
    for binding in entry.database_resources:
        resource = resources.get(binding.resource_name)
        if resource is None:
            raise ProviderPlanError(
                f"provider route resource is absent: {binding.resource_name}"
            )
        if resource.status is not DatabaseResourceStatus.READY:
            raise ProviderPlanError(
                f"provider route resource is not ready: {binding.resource_name}"
            )
        if (
            resource.database_id != binding.database_id
            or resource.manifest_sha256 != binding.resource_manifest_sha256
        ):
            raise ProviderPlanError(
                f"provider route resource identity changed: {binding.resource_name}"
            )
    return EnabledProviderRoute(plan=plan, entry=entry)


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


def load_frozen_m6_raw_provider_route(
    *,
    authorisation: FrozenM6RawProviderAuthorisation,
    database_manifest: Path,
    expected_provider: ProviderKey,
    expected_adapter_version: str,
    threads: int,
    maximum_hits_per_query: int,
) -> FrozenM6RawProviderRoute:
    """Authenticate M6 blind discovery without weakening application policy.

    M6 must retain 25 raw proposals before leakage filtering and only then cap
    accepted models at three. Its truthless, frozen task contract is therefore
    deliberately distinct from the ordinary reviewed application-provider plan.
    """

    from genome_to_diffraction.benchmarks import m6_nextflow
    from genome_to_diffraction.benchmarks.m6_execution import load_m6_execution_policy
    from genome_to_diffraction.benchmarks.m6_model_policy import (
        M6_ACCEPTED_HIT_CAP_PER_QUERY_ROUTE,
        M6_RAW_DISCOVERY_HIT_CAP_PER_QUERY_ROUTE,
    )

    if expected_provider not in {
        ProviderKey.PDB_SEQUENCE,
        ProviderKey.FOLDSEEK_PROSTT5_PDB,
    }:
        raise ProviderPlanError(
            "frozen M6 authorisation does not support this provider"
        )
    if _CAPABILITIES[expected_provider].provider_adapter_version != (
        expected_adapter_version
    ):
        raise ProviderPlanError("frozen M6 provider adapter version changed")
    if (
        M6_RAW_DISCOVERY_HIT_CAP_PER_QUERY_ROUTE != 25
        or M6_ACCEPTED_HIT_CAP_PER_QUERY_ROUTE != 3
        or maximum_hits_per_query != M6_RAW_DISCOVERY_HIT_CAP_PER_QUERY_ROUTE
    ):
        raise ProviderPlanError("frozen M6 raw or accepted discovery hit cap changed")

    try:
        task_path = authorisation.batch_task_json.resolve(strict=True)
        task = m6_nextflow.M6SearchBatchTask.model_validate_json(task_path.read_bytes())
        policy_path = authorisation.execution_policy.resolve(strict=True)
        lock_path = authorisation.software_lock.resolve(strict=True)
        database_path = database_manifest.resolve(strict=True)
    except (OSError, ValueError) as error:
        raise ProviderPlanError(
            f"invalid frozen M6 provider authorisation: {error}"
        ) from error

    expected_task_provider = {
        ProviderKey.PDB_SEQUENCE: "pdb_sequence",
        ProviderKey.FOLDSEEK_PROSTT5_PDB: "prostt5_foldseek",
    }[expected_provider]
    if task.provider != expected_task_provider:
        raise ProviderPlanError("frozen M6 provider does not match its search batch")
    policy = load_m6_execution_policy(policy_path)
    expected_threads = (
        policy.search_batching.mmseqs2.cpus
        if expected_provider is ProviderKey.PDB_SEQUENCE
        else policy.search_batching.foldseek.cpus
    )
    if task.threads != expected_threads or threads != expected_threads:
        raise ProviderPlanError("frozen M6 provider thread allocation changed")

    database_sha256 = sha256_file(database_path)
    policy_sha256 = sha256_file(policy_path)
    lock_sha256 = sha256_file(lock_path)
    if (
        task.database_manifest_sha256 != database_sha256
        or task.execution_policy_sha256 != policy_sha256
        or task.software_lock_sha256 != lock_sha256
    ):
        raise ProviderPlanError("frozen M6 provider provenance changed")

    parameters: dict[str, int | float | bool] = {
        "threads": threads,
        "maximum_hits_per_query": M6_RAW_DISCOVERY_HIT_CAP_PER_QUERY_ROUTE,
        "maximum_evalue": 1.0e-5
        if expected_provider is ProviderKey.PDB_SEQUENCE
        else 1.0e-3,
        "minimum_query_coverage": 0.5,
        "maximum_query_length": 10_000,
    }
    task_adapter = m6_nextflow._PDB_ADAPTER
    if expected_provider is ProviderKey.FOLDSEEK_PROSTT5_PDB:
        parameters.update({"maximum_queries": 0, "retain_unmapped_targets": True})
        task_adapter = m6_nextflow._FOLDSEEK_ADAPTER
    expected_search_cache_key = canonical_digest(
        {
            "adapter_version": task_adapter,
            "batch_id": task.batch_id,
            "database_manifest_sha256": database_sha256,
            "software_lock_sha256": lock_sha256,
            "execution_policy_sha256": policy_sha256,
            "parameters": parameters,
        }
    )
    if task.search_cache_key != expected_search_cache_key:
        raise ProviderPlanError("frozen M6 provider search-cache identity changed")

    database = load_contract(database_path, "database-manifest", progress=False)
    if not isinstance(database, DatabaseManifest):
        raise AssertionError("frozen M6 provider loaded an unexpected database model")
    _database_bindings(
        expected_provider,
        _CAPABILITIES[expected_provider],
        _resource_index(database),
    )

    task_sha256 = sha256_file(task_path)
    identity = {
        "provider": expected_provider.value,
        "provider_adapter_version": expected_adapter_version,
        "site_id": policy.site_id,
        "batch_task_sha256": task_sha256,
        "search_cache_key": task.search_cache_key,
        "database_manifest_sha256": database_sha256,
        "execution_policy_sha256": policy_sha256,
        "software_lock_sha256": lock_sha256,
        "raw_hit_cap": M6_RAW_DISCOVERY_HIT_CAP_PER_QUERY_ROUTE,
        "accepted_hit_cap": M6_ACCEPTED_HIT_CAP_PER_QUERY_ROUTE,
    }
    return FrozenM6RawProviderRoute(
        authorisation_id=content_id("m6rawprovider_", identity),
        provider=expected_provider,
        site_id=policy.site_id,
        batch_task_sha256=task_sha256,
        database_manifest_sha256=database_sha256,
        execution_policy_sha256=policy_sha256,
        software_lock_sha256=lock_sha256,
        raw_hit_cap=M6_RAW_DISCOVERY_HIT_CAP_PER_QUERY_ROUTE,
        accepted_hit_cap=M6_ACCEPTED_HIT_CAP_PER_QUERY_ROUTE,
    )


def frozen_m6_raw_authorisation_payload(
    route: FrozenM6RawProviderRoute,
) -> dict[str, str | int | None]:
    """Expose path-free M6 authorisation evidence for provider/cache identity."""

    return {
        "authorisation_scope": "m6_frozen_raw_discovery",
        "authorisation_id": route.authorisation_id,
        "provider_plan_sha256": None,
        "provider_entry_sha256": None,
        "site_id": route.site_id,
        "batch_task_sha256": route.batch_task_sha256,
        "database_manifest_sha256": route.database_manifest_sha256,
        "execution_policy_sha256": route.execution_policy_sha256,
        "software_lock_sha256": route.software_lock_sha256,
        "raw_hit_cap": route.raw_hit_cap,
        "accepted_hit_cap": route.accepted_hit_cap,
    }


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
