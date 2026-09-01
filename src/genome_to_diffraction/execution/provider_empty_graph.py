"""Close the fixed four-route provider graph after a complete no-model result.

The adapter executes no provider. It verifies the existing authoritative
``ProviderExecutionPlan`` and existing search-result bundles, then publishes the
existing all-eligible-model registry with typed ``no_eligible_model`` rows plus
one content-addressed terminal record. The fixed local path accepts an enabled
local scientific no-hit, configured-disabled routes, and an unsupported route;
enabled network routes fail closed.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.model_registry.all_eligible import (
    AllEligibleModelRegistryManifest,
    build_all_eligible_model_registry,
)
from genome_to_diffraction.schemas.base import ContractModel, NonEmptyString, Sha256Hex
from genome_to_diffraction.schemas.io import load_contract, load_json_document
from genome_to_diffraction.schemas.providers import (
    ProviderExecutionClass,
    ProviderExecutionPlan,
    ProviderKey,
    ProviderPlanEntry,
    ProviderSupportStatus,
)
from genome_to_diffraction.schemas.results import (
    SearchScientificStatus,
    SequenceGroupRecord,
    StructuralSearchResult,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_ADAPTER_VERSION = "provider-empty-graph-v1"


class ProviderEmptyGraphError(InputContractError):
    """The routed bundles cannot form one complete empty provider graph."""


class ProviderEmptyOutcome(StrEnum):
    """Allowed terminal branch outcomes in the fixed local graph."""

    ENABLED_NO_HIT = "enabled_no_hit"
    DISABLED = "disabled"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


class ProviderEmptyBranch(ContractModel):
    """Content-bound terminal evidence for one provider-plan entry."""

    provider: ProviderKey
    provider_entry_id: NonEmptyString
    outcome: ProviderEmptyOutcome
    result_ids: tuple[NonEmptyString, ...] = Field(min_length=1)
    result_records_sha256: tuple[Sha256Hex, ...] = Field(min_length=1)
    bundle_sha256: Sha256Hex

    @model_validator(mode="after")
    def _complete_results(self) -> Self:
        if len(self.result_ids) != len(self.result_records_sha256):
            raise ValueError("branch result IDs and digests differ in length")
        if len(set(self.result_ids)) != len(self.result_ids):
            raise ValueError("branch result IDs are duplicated")
        return self


class ProviderEmptyGraphCompletion(ContractModel):
    """Typed content-addressed terminal for the fixed four-provider graph."""

    schema_version: Literal["2.0"]
    completion_id: NonEmptyString
    adapter_version: Literal["provider-empty-graph-v1"]
    provider_plan_id: NonEmptyString
    provider_plan_sha256: Sha256Hex
    pipeline_config_sha256: Sha256Hex
    sequence_groups_sha256: Sha256Hex
    query_count: int = Field(ge=1)
    branches: tuple[ProviderEmptyBranch, ...] = Field(min_length=4, max_length=4)
    terminal_status: Literal["completed_no_model"]
    all_model_registry_id: NonEmptyString
    all_model_registry_sha256: Sha256Hex
    network_request_count: Literal[0]

    @model_validator(mode="after")
    def _content_addressed(self) -> Self:
        providers = tuple(item.provider for item in self.branches)
        if providers != tuple(sorted(ProviderKey, key=lambda item: item.value)):
            raise ValueError("branches do not cover each provider exactly once")
        if any(len(item.result_ids) != self.query_count for item in self.branches):
            raise ValueError("a provider branch does not cover every query")
        expected = content_id(
            "providerempty_",
            self.model_dump(mode="python", exclude={"completion_id"}),
        )
        if self.completion_id != expected:
            raise ValueError("completion_id does not match terminal content")
        return self


@dataclass(frozen=True)
class ProviderEmptyGraphRequest:
    """Inputs for one fixed plan-driven empty-provider completion."""

    pipeline_config: Path
    provider_plan_json: Path
    sequence_groups_jsonl: Path
    provider_bundle_directories: tuple[Path, ...]
    output_directory: Path


@dataclass(frozen=True)
class ProviderEmptyGraphOutput:
    """Published terminal and existing typed no-model registry."""

    completion: ProviderEmptyGraphCompletion
    completion_json: Path
    all_model_registry: AllEligibleModelRegistryManifest
    all_model_registry_json: Path


def _groups(path: Path) -> tuple[SequenceGroupRecord, ...]:
    try:
        lines = path.resolve(strict=True).read_text(encoding="utf-8").splitlines()
        groups = tuple(SequenceGroupRecord.model_validate_json(line) for line in lines)
    except (OSError, UnicodeDecodeError, ValidationError, ValueError) as error:
        raise ProviderEmptyGraphError(
            "invalid provider-graph sequence groups"
        ) from error
    identifiers = tuple(item.sequence_group_id for item in groups)
    if not groups or len(set(identifiers)) != len(groups):
        raise ProviderEmptyGraphError("sequence groups are empty or duplicated")
    return tuple(sorted(groups, key=lambda item: item.sequence_group_id))


def _entry(
    document: dict[str, object], plan: ProviderExecutionPlan
) -> ProviderPlanEntry:
    entry_id = document.get("provider_entry_id")
    entry_sha256 = document.get("provider_entry_sha256")
    matches = tuple(
        item
        for item in plan.entries
        if entry_id == item.entry_id or entry_sha256 == plan.entry_sha256[item.provider]
    )
    if len(matches) != 1:
        raise ProviderEmptyGraphError(
            "bundle does not bind exactly one authoritative provider entry"
        )
    return matches[0]


def _output_file(root: Path, outputs: dict[str, object], name: str) -> tuple[Path, str]:
    value = outputs.get(name)
    if not isinstance(value, dict):
        raise ProviderEmptyGraphError(f"bundle lacks {name} output metadata")
    relative = value.get("path")
    checksum = value.get("sha256")
    if not isinstance(relative, str) or not isinstance(checksum, str):
        raise ProviderEmptyGraphError(f"bundle has incomplete {name} metadata")
    path = (root / relative).resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(root):
        raise ProviderEmptyGraphError(f"bundle has unsafe {name} output")
    if sha256_file(path, progress=False) != checksum:
        raise ProviderEmptyGraphError(f"bundle {name} checksum differs")
    return path, checksum


def _branch(
    directory: Path,
    *,
    plan: ProviderExecutionPlan,
    groups: tuple[SequenceGroupRecord, ...],
) -> ProviderEmptyBranch:
    root = directory.resolve(strict=True)
    document = load_json_document(root / "search_manifest.json")
    if not isinstance(document, dict) or not isinstance(document.get("outputs"), dict):
        raise ProviderEmptyGraphError("invalid provider bundle manifest")
    entry = _entry(document, plan)
    outputs = document["outputs"]
    assert isinstance(outputs, dict)
    results_path, _ = _output_file(root, outputs, "search_results")
    hits_path, hits_sha256 = _output_file(root, outputs, "structural_hits")
    coordinates_path, coordinates_sha256 = _output_file(
        root, outputs, "coordinate_sources"
    )
    if hits_path.read_bytes() or coordinates_path.read_bytes():
        raise ProviderEmptyGraphError("empty graph contains hits or coordinates")
    try:
        results = tuple(
            StructuralSearchResult.model_validate_json(line)
            for line in results_path.read_text(encoding="utf-8").splitlines()
        )
    except (OSError, UnicodeDecodeError, ValidationError, ValueError) as error:
        raise ProviderEmptyGraphError("invalid typed provider results") from error
    if tuple(sorted(item.sequence_group_id for item in results)) != tuple(
        item.sequence_group_id for item in groups
    ):
        raise ProviderEmptyGraphError(
            "provider bundle does not cover every sequence group exactly once"
        )
    if entry.enabled:
        if entry.execution_class is not ProviderExecutionClass.LOCAL_COMPUTE:
            raise ProviderEmptyGraphError(
                "enabled network route is not locally runnable"
            )
        outcome = ProviderEmptyOutcome.ENABLED_NO_HIT
        valid = all(
            item.execution_status is ExecutionStatus.COMPLETED_NO_HIT
            and item.scientific_status is SearchScientificStatus.NO_HIT
            and item.hit_count == 0
            for item in results
        )
    else:
        outcome = (
            ProviderEmptyOutcome.PROVIDER_UNAVAILABLE
            if entry.support_status is ProviderSupportStatus.UNSUPPORTED
            else ProviderEmptyOutcome.DISABLED
        )
        valid = all(
            item.execution_status is ExecutionStatus.SKIPPED_POLICY
            and item.scientific_status is SearchScientificStatus.NOT_INTERPRETABLE
            and item.hit_count == 0
            for item in results
        )
    if not valid:
        raise ProviderEmptyGraphError("provider branch has the wrong typed outcome")
    return ProviderEmptyBranch(
        provider=entry.provider,
        provider_entry_id=entry.entry_id,
        outcome=outcome,
        result_ids=tuple(item.search_id for item in results),
        result_records_sha256=tuple(canonical_digest(item) for item in results),
        bundle_sha256=canonical_digest(
            {
                "manifest": sha256_file(root / "search_manifest.json", progress=False),
                "results": sha256_file(results_path, progress=False),
                "hits": hits_sha256,
                "coordinates": coordinates_sha256,
            }
        ),
    )


def complete_provider_empty_graph(
    request: ProviderEmptyGraphRequest,
) -> ProviderEmptyGraphOutput:
    """Publish a no-model terminal only after exact four-branch validation."""

    plan_path = request.provider_plan_json.resolve(strict=True)
    loaded = load_contract(plan_path, "provider-execution-plan", progress=False)
    if not isinstance(loaded, ProviderExecutionPlan):
        raise AssertionError("provider-plan loader returned the wrong model")
    config_sha256 = sha256_file(request.pipeline_config.resolve(strict=True))
    if config_sha256 != loaded.pipeline_config_sha256:
        raise ProviderEmptyGraphError("pipeline config differs from provider plan")
    groups = _groups(request.sequence_groups_jsonl)
    if len(request.provider_bundle_directories) != len(ProviderKey):
        raise ProviderEmptyGraphError("provider graph requires four branch bundles")
    branches = tuple(
        sorted(
            (
                _branch(path, plan=loaded, groups=groups)
                for path in request.provider_bundle_directories
            ),
            key=lambda item: item.provider.value,
        )
    )
    if len({item.provider for item in branches}) != len(ProviderKey):
        raise ProviderEmptyGraphError(
            "provider graph has a missing or duplicate branch"
        )
    output = request.output_directory.absolute()
    if output.exists():
        raise ProviderEmptyGraphError(f"provider-graph output exists: {output}")
    registry = build_all_eligible_model_registry(
        models=(),
        sequence_groups=groups,
        output_directory=output / "all_model_registry",
    )
    payload: dict[str, object] = {
        "schema_version": "2.0",
        "adapter_version": _ADAPTER_VERSION,
        "provider_plan_id": loaded.plan_id,
        "provider_plan_sha256": sha256_file(plan_path, progress=False),
        "pipeline_config_sha256": config_sha256,
        "sequence_groups_sha256": sha256_file(
            request.sequence_groups_jsonl.resolve(strict=True), progress=False
        ),
        "query_count": len(groups),
        "branches": branches,
        "terminal_status": "completed_no_model",
        "all_model_registry_id": registry.registry.registry_id,
        "all_model_registry_sha256": sha256_file(
            registry.registry_json, progress=False
        ),
        "network_request_count": 0,
    }
    completion = ProviderEmptyGraphCompletion.model_validate(
        {**payload, "completion_id": content_id("providerempty_", payload)}
    )
    completion_json = output / "provider_empty_graph_completion.json"
    atomic_write_json(completion_json, completion.model_dump(mode="json"))
    return ProviderEmptyGraphOutput(
        completion=completion,
        completion_json=completion_json,
        all_model_registry=registry.registry,
        all_model_registry_json=registry.registry_json,
    )
