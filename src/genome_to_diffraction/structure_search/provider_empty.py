"""Emit one typed empty structural-search bundle for a disabled provider.

The adapter consumes one content-addressed disabled provider-plan entry and the
complete sequence-group catalogue. It executes no provider software and makes
no network request. Each sequence group receives an explicit ``skipped_policy``
and ``not_interpretable`` result; this is distinct from an executed scientific
no-hit. Structural-hit and coordinate-source outputs are present but empty, so
downstream channels remain total. Invalid, enabled, tampered, duplicate, or
empty inputs fail before the output directory is created. The provider entry,
sequence identities, adapter version, and output checksums form the cache and
provenance boundary.
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_digest, canonical_json_text, content_id
from genome_to_diffraction.schemas.providers import ProviderPlanEntry
from genome_to_diffraction.schemas.results import (
    SearchScientificStatus,
    SequenceGroupRecord,
    StructuralSearchResult,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_ADAPTER_VERSION = "disabled-provider-bundle-v1"
_TOOL = "provider-plan"
_TOOL_VERSION = "provider-plan-v1"


class DisabledProviderBundleError(InputContractError):
    """A provider-plan entry cannot form a typed disabled result bundle."""


@dataclass(frozen=True)
class DisabledProviderBundleRequest:
    """Inputs for one side-effect-free disabled-provider bundle."""

    provider_entry_json: Path
    sequence_groups_jsonl: Path
    output_directory: Path


@dataclass(frozen=True)
class DisabledProviderBundleOutput:
    """Canonical empty bundle and its typed skipped-policy results."""

    results: tuple[StructuralSearchResult, ...]
    results_jsonl: Path
    hits_jsonl: Path
    coordinate_sources_jsonl: Path
    search_manifest: Path


def _load_entry(path: Path) -> tuple[Path, ProviderPlanEntry]:
    resolved = path.resolve(strict=True)
    try:
        entry = ProviderPlanEntry.model_validate_json(resolved.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise DisabledProviderBundleError(
            f"invalid disabled provider-plan entry: {resolved}: {error}"
        ) from error
    if entry.enabled:
        raise DisabledProviderBundleError(
            f"provider-plan entry is enabled, not disabled: {entry.provider.value}"
        )
    if not entry.disabled_reason:
        raise DisabledProviderBundleError("disabled provider entry lacks its reason")
    return resolved, entry


def _load_sequence_groups(path: Path) -> tuple[Path, tuple[SequenceGroupRecord, ...]]:
    resolved = path.resolve(strict=True)
    records: list[SequenceGroupRecord] = []
    identifiers: set[str] = set()
    try:
        lines = resolved.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise DisabledProviderBundleError(
            f"cannot read sequence-group input: {resolved}"
        ) from error
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = SequenceGroupRecord.model_validate_json(line)
        except (ValidationError, ValueError) as error:
            raise DisabledProviderBundleError(
                f"invalid sequence-group record at {resolved}:{line_number}: {error}"
            ) from error
        if record.sequence_group_id in identifiers:
            raise DisabledProviderBundleError(
                f"duplicate sequence-group identifier: {record.sequence_group_id}"
            )
        identifiers.add(record.sequence_group_id)
        records.append(record)
    if not records:
        raise DisabledProviderBundleError(f"sequence-group input is empty: {resolved}")
    return resolved, tuple(sorted(records, key=lambda item: item.sequence_group_id))


def emit_disabled_provider_bundle(
    request: DisabledProviderBundleRequest,
) -> DisabledProviderBundleOutput:
    """Write deterministic skipped-policy evidence for one disabled provider."""

    entry_path, entry = _load_entry(request.provider_entry_json)
    sequence_path, groups = _load_sequence_groups(request.sequence_groups_jsonl)
    output = request.output_directory.absolute()
    if output.exists():
        raise DisabledProviderBundleError(
            f"disabled-provider output already exists: {output}"
        )

    raw_directory = output / "raw"
    raw_directory.mkdir(parents=True)
    raw_result = raw_directory / "disabled.jsonl"
    command_log = raw_directory / "disabled.log"
    atomic_write_text(raw_result, "")
    atomic_write_text(
        command_log,
        f"provider={entry.provider.value}\n"
        f"entry_id={entry.entry_id}\n"
        f"reason={entry.disabled_reason}\n",
    )
    raw_sha256 = sha256_file(raw_result, progress=False)
    log_sha256 = sha256_file(command_log, progress=False)

    results: list[StructuralSearchResult] = []
    for group in groups:
        identity = {
            "adapter_version": _ADAPTER_VERSION,
            "provider_entry_id": entry.entry_id,
            "sequence_group_id": group.sequence_group_id,
            "sequence_sha256": group.sha256,
        }
        results.append(
            StructuralSearchResult(
                schema_version="1.0",
                search_id=content_id("search_", identity),
                sequence_group_id=group.sequence_group_id,
                provider=entry.result_provider,
                database_id=f"disabled_{entry.provider.value}",
                tool=_TOOL,
                tool_version=_TOOL_VERSION,
                adapter_version=_ADAPTER_VERSION,
                cache_key=canonical_digest(identity),
                execution_status=ExecutionStatus.SKIPPED_POLICY,
                scientific_status=SearchScientificStatus.NOT_INTERPRETABLE,
                hit_count=0,
                hits=(),
                raw_result_pointer="raw/disabled.jsonl",
                raw_result_sha256=raw_sha256,
                command_log_pointer="raw/disabled.log",
                command_log_sha256=log_sha256,
                warnings=(f"provider_disabled:{entry.disabled_reason}",),
            )
        )

    results_path = output / "search_results.jsonl"
    hits_path = output / "structural_hits.jsonl"
    coordinates_path = output / "coordinate_sources.jsonl"
    atomic_write_text(
        results_path,
        "".join(f"{canonical_json_text(item)}\n" for item in results),
    )
    atomic_write_text(hits_path, "")
    atomic_write_text(coordinates_path, "")
    manifest_path = output / "search_manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "provider": entry.provider.value,
            "result_provider": entry.result_provider,
            "provider_entry_id": entry.entry_id,
            "provider_entry_sha256": sha256_file(entry_path, progress=False),
            "sequence_groups_sha256": sha256_file(sequence_path, progress=False),
            "disabled_reason": entry.disabled_reason,
            "query_count": len(groups),
            "hit_count": 0,
            "status_counts": {ExecutionStatus.SKIPPED_POLICY.value: len(groups)},
            "outputs": {
                "search_results": {
                    "path": results_path.name,
                    "sha256": sha256_file(results_path, progress=False),
                },
                "structural_hits": {
                    "path": hits_path.name,
                    "sha256": sha256_file(hits_path, progress=False),
                },
                "coordinate_sources": {
                    "path": coordinates_path.name,
                    "sha256": sha256_file(coordinates_path, progress=False),
                },
                "raw_result": {
                    "path": "raw/disabled.jsonl",
                    "sha256": raw_sha256,
                },
                "command_log": {
                    "path": "raw/disabled.log",
                    "sha256": log_sha256,
                },
            },
        },
    )
    return DisabledProviderBundleOutput(
        results=tuple(results),
        results_jsonl=results_path,
        hits_jsonl=hits_path,
        coordinate_sources_jsonl=coordinates_path,
        search_manifest=manifest_path,
    )
