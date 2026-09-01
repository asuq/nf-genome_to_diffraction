"""Bound complete Phase III ProstT5/Foldseek catalogue searches.

One typed catalogue is sorted into deterministic batches of at most 128 sequence
groups. Nextflow owns each independent Foldseek invocation; this adapter only
plans batches and merges their complete, checksum-verified result inventories.
No sequence is discarded, no external tool is started, and no scientific status
is promoted. Batch content and provider output checksums are cache identities.
"""

import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.schemas.io import ContractLoadError, parse_json_document
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    StructuralSearchHit,
    StructuralSearchResult,
)
from genome_to_diffraction.status import InputContractError

_BATCH_SIZE = 128
_PLAN_ADAPTER = "phase3-foldseek-batch-plan-v1"
_MERGE_ADAPTER = "phase3-foldseek-batch-merge-v1"
_PROVIDER = "foldseek_prostt5_pdb"


class PhaseIIIFoldseekBatchError(InputContractError):
    """Bounded Foldseek batches are incomplete, changed, or inconsistent."""


def _groups(path: Path) -> tuple[SequenceGroupRecord, ...]:
    try:
        lines = path.resolve(strict=True).read_text(encoding="utf-8").splitlines()
        records = tuple(SequenceGroupRecord.model_validate_json(line) for line in lines)
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise PhaseIIIFoldseekBatchError("invalid catalogue sequence groups") from error
    identifiers = tuple(record.sequence_group_id for record in records)
    if not records or len(identifiers) != len(set(identifiers)):
        raise PhaseIIIFoldseekBatchError(
            "Foldseek batching requires unique non-empty sequence groups"
        )
    return tuple(sorted(records, key=lambda item: item.sequence_group_id))


def _document(path: Path, *, label: str) -> dict[str, Any]:
    try:
        document = parse_json_document(path.read_text(encoding="utf-8"), label=label)
    except (ContractLoadError, OSError, UnicodeError) as error:
        raise PhaseIIIFoldseekBatchError(f"invalid {label}") from error
    if not isinstance(document, dict):
        raise PhaseIIIFoldseekBatchError(f"invalid {label}")
    return document


def build_phase3_foldseek_batches(
    *,
    sequence_groups: Path,
    output_directory: Path,
) -> Path:
    """Publish the complete deterministic fixed-128-query batch inventory."""

    groups = _groups(sequence_groups)
    output = output_directory.absolute()
    if output.exists():
        raise PhaseIIIFoldseekBatchError("Foldseek batch output already exists")
    output.mkdir(parents=True)
    root = output / "batches"
    root.mkdir()
    batches: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, len(groups), _BATCH_SIZE), start=1):
        selected = groups[start : start + _BATCH_SIZE]
        identifiers = [record.sequence_group_id for record in selected]
        batch_id = content_id(
            "foldbatch_",
            {
                "adapter_version": _PLAN_ADAPTER,
                "sequence_group_ids": identifiers,
                "sequence_sha256": [record.sha256 for record in selected],
            },
        )
        destination = root / batch_id
        destination.mkdir()
        sequence_path = destination / "sequence_groups.jsonl"
        atomic_write_text(
            sequence_path,
            "".join(f"{canonical_json_text(record)}\n" for record in selected),
        )
        batch = {
            "schema_version": "2.0",
            "batch_id": batch_id,
            "batch_index": index,
            "sequence_count": len(selected),
            "sequence_group_ids": identifiers,
            "sequence_groups_sha256": sha256_file(sequence_path, progress=False),
        }
        atomic_write_json(destination / "batch.json", batch)
        batches.append(batch)
    atomic_write_json(
        output / "batch_plan.json",
        {
            "schema_version": "2.0",
            "adapter_version": _PLAN_ADAPTER,
            "sequence_groups_sha256": sha256_file(sequence_groups, progress=False),
            "query_count": len(groups),
            "maximum_queries_per_batch": _BATCH_SIZE,
            "batch_count": len(batches),
            "batches": batches,
        },
    )
    return output


def _typed_jsonl[T: BaseModel](path: Path, record_type: type[T]) -> tuple[T, ...]:
    try:
        return tuple(
            record_type.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise PhaseIIIFoldseekBatchError(
            f"invalid batch result: {path.name}"
        ) from error


def merge_phase3_foldseek_batches(
    *,
    sequence_groups: Path,
    batch_plan: Path,
    batch_outputs: tuple[Path, ...],
    output_directory: Path,
) -> Path:
    """Merge every bounded search without losing query, hit, or raw evidence."""

    groups = _groups(sequence_groups)
    plan = _document(batch_plan / "batch_plan.json", label="Foldseek batch plan")
    if (
        plan.get("adapter_version") != _PLAN_ADAPTER
        or plan.get("query_count") != len(groups)
        or plan.get("sequence_groups_sha256")
        != sha256_file(sequence_groups, progress=False)
        or plan.get("maximum_queries_per_batch") != _BATCH_SIZE
        or not isinstance(plan.get("batches"), list)
        or plan.get("batch_count") != len(plan["batches"])
    ):
        raise PhaseIIIFoldseekBatchError("Foldseek batch plan changed or lost queries")
    expected = {item["batch_id"]: item for item in plan["batches"]}
    observed: dict[str, tuple[Path, dict[str, Any]]] = {}
    for directory in batch_outputs:
        batch = _document(directory / "batch.json", label="Foldseek batch identity")
        batch_id = batch.get("batch_id")
        if not isinstance(batch_id, str) or batch_id in observed:
            raise PhaseIIIFoldseekBatchError("Foldseek batch is duplicated or invalid")
        if batch != expected.get(batch_id):
            raise PhaseIIIFoldseekBatchError("Foldseek batch differs from its plan")
        observed[batch_id] = (directory, batch)
    if set(observed) != set(expected):
        raise PhaseIIIFoldseekBatchError("Foldseek search lost or added a query batch")

    output = output_directory.absolute()
    if output.exists():
        raise PhaseIIIFoldseekBatchError("merged Foldseek output already exists")
    output.mkdir(parents=True)
    raw_root = output / "raw"
    raw_root.mkdir()
    results: list[StructuralSearchResult] = []
    hits: list[StructuralSearchHit] = []
    manifest_digests: dict[str, str] = {}
    for batch_id, (directory, batch) in sorted(observed.items()):
        search = directory / "search"
        manifest_path = search / "search_manifest.json"
        manifest = _document(manifest_path, label="Foldseek search manifest")
        result_path = search / "search_results.jsonl"
        hit_path = search / "structural_hits.jsonl"
        outputs = manifest.get("outputs")
        if (
            manifest.get("provider") != _PROVIDER
            or manifest.get("query_count") != batch["sequence_count"]
            or manifest.get("deferred_query_count") != 0
            or not isinstance(outputs, dict)
            or outputs.get("search_results", {}).get("sha256")
            != sha256_file(result_path, progress=False)
            or outputs.get("structural_hits", {}).get("sha256")
            != sha256_file(hit_path, progress=False)
        ):
            raise PhaseIIIFoldseekBatchError(
                f"Foldseek batch output changed or deferred queries: {batch_id}"
            )
        batch_results = _typed_jsonl(result_path, StructuralSearchResult)
        batch_hits = _typed_jsonl(hit_path, StructuralSearchHit)
        try:
            raw_sha256 = sha256_file(
                search / "raw/foldseek-results.tsv", progress=False
            )
            log_sha256 = sha256_file(search / "raw/foldseek.log", progress=False)
        except OSError as error:
            raise PhaseIIIFoldseekBatchError(
                f"Foldseek batch raw evidence is missing: {batch_id}"
            ) from error
        if any(
            result.raw_result_sha256 != raw_sha256
            or result.command_log_sha256 != log_sha256
            for result in batch_results
        ):
            raise PhaseIIIFoldseekBatchError(
                f"Foldseek batch raw evidence changed: {batch_id}"
            )
        if {item.sequence_group_id for item in batch_results} != set(
            batch["sequence_group_ids"]
        ):
            raise PhaseIIIFoldseekBatchError(
                f"Foldseek batch result lost a catalogue sequence: {batch_id}"
            )
        if {hit.hit_id for result in batch_results for hit in result.hits} != {
            hit.hit_id for hit in batch_hits
        }:
            raise PhaseIIIFoldseekBatchError(
                f"Foldseek batch result and hit inventories differ: {batch_id}"
            )
        shutil.copytree(search / "raw", raw_root / batch_id)
        for result in batch_results:
            replaced_hits = tuple(
                hit.model_copy(
                    update={
                        "raw_result_pointer": f"raw/{batch_id}/foldseek-results.tsv"
                    }
                )
                for hit in result.hits
            )
            results.append(
                result.model_copy(
                    update={
                        "raw_result_pointer": f"raw/{batch_id}/foldseek-results.tsv",
                        "command_log_pointer": f"raw/{batch_id}/foldseek.log",
                        "hits": replaced_hits,
                    }
                )
            )
            hits.extend(replaced_hits)
        manifest_digests[batch_id] = sha256_file(manifest_path, progress=False)

    results.sort(key=lambda item: (item.sequence_group_id, item.search_id))
    hits.sort(
        key=lambda item: (item.sequence_group_id, item.provider_rank, item.hit_id)
    )
    if len(results) != len(groups) or {item.sequence_group_id for item in results} != {
        item.sequence_group_id for item in groups
    }:
        raise PhaseIIIFoldseekBatchError(
            "merged Foldseek results lost catalogue groups"
        )
    result_path = output / "search_results.jsonl"
    hit_path = output / "structural_hits.jsonl"
    atomic_write_text(
        result_path,
        "".join(f"{canonical_json_text(item)}\n" for item in results),
    )
    atomic_write_text(
        hit_path, "".join(f"{canonical_json_text(item)}\n" for item in hits)
    )
    atomic_write_json(
        output / "search_manifest.json",
        {
            "schema_version": "2.0",
            "adapter_version": _MERGE_ADAPTER,
            "provider": _PROVIDER,
            "query_count": len(results),
            "batch_count": len(observed),
            "maximum_queries_per_batch": _BATCH_SIZE,
            "deferred_query_count": 0,
            "hit_count": len(hits),
            "status_counts": dict(
                sorted(Counter(item.execution_status.value for item in results).items())
            ),
            "source_batch_manifest_sha256": manifest_digests,
            "outputs": {
                "search_results": {
                    "path": result_path.name,
                    "sha256": sha256_file(result_path, progress=False),
                },
                "structural_hits": {
                    "path": hit_path.name,
                    "sha256": sha256_file(hit_path, progress=False),
                },
            },
        },
    )
    return output


__all__ = [
    "PhaseIIIFoldseekBatchError",
    "build_phase3_foldseek_batches",
    "merge_phase3_foldseek_batches",
]
