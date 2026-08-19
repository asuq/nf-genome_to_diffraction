"""Fail-loud qualification of one real P1 direct-PDB discovery run."""

import csv
import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError
from tqdm import tqdm

from genome_to_diffraction.benchmarks.public_control import (
    load_public_control_spec,
)
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    StructuralSearchHit,
    StructuralSearchResult,
)
from genome_to_diffraction.status import InputContractError, ResultParseError
from genome_to_diffraction.time import utc_now

_LOGGER = logging.getLogger("genome_to_diffraction.structure_search.qualification")
_REQUIRED_OUTPUTS = frozenset(
    {"search_results", "structural_hits", "raw_result", "command_log"}
)
_TRACE_FIELDS = (
    "task_id",
    "native_id",
    "name",
    "status",
    "exit",
    "duration",
    "realtime",
    "%cpu",
    "peak_rss",
    "peak_vmem",
    "rchar",
    "wchar",
)


@dataclass(frozen=True)
class P1QualificationRequest:
    """Inputs for the fixed direct-PDB positive-control and resume gate."""

    sequence_groups_jsonl: Path
    search_directory: Path
    control_specification: Path
    first_trace_tsv: Path
    resume_trace_tsv: Path
    output_json: Path
    progress: bool = True


def _read_sequence_groups(path: Path, *, progress: bool) -> list[SequenceGroupRecord]:
    records: list[SequenceGroupRecord] = []
    with path.resolve(strict=True).open(encoding="utf-8") as handle:
        iterator = tqdm(
            enumerate(handle, start=1),
            desc="Qualify sequence groups",
            unit="sequence",
            disable=not progress,
        )
        for line_number, line in iterator:
            try:
                records.append(SequenceGroupRecord.model_validate_json(line))
            except ValidationError as error:
                raise InputContractError(
                    f"invalid sequence-group record at line {line_number}: {path}"
                ) from error
    if not records:
        raise InputContractError(f"sequence-group input is empty: {path}")
    identifiers = [record.sequence_group_id for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise InputContractError("sequence-group input contains duplicate identifiers")
    return records


def _read_results(path: Path, *, progress: bool) -> list[StructuralSearchResult]:
    records: list[StructuralSearchResult] = []
    with path.resolve(strict=True).open(encoding="utf-8") as handle:
        iterator = tqdm(
            enumerate(handle, start=1),
            desc="Qualify PDB search results",
            unit="query",
            disable=not progress,
        )
        for line_number, line in iterator:
            try:
                records.append(StructuralSearchResult.model_validate_json(line))
            except ValidationError as error:
                raise ResultParseError(
                    f"invalid structural-search result at line {line_number}: {path}"
                ) from error
    if not records:
        raise ResultParseError(f"structural-search result is empty: {path}")
    return records


def _read_hits(path: Path, *, progress: bool) -> list[StructuralSearchHit]:
    records: list[StructuralSearchHit] = []
    with path.resolve(strict=True).open(encoding="utf-8") as handle:
        iterator = tqdm(
            enumerate(handle, start=1),
            desc="Qualify flattened PDB hits",
            unit="hit",
            disable=not progress,
        )
        for line_number, line in iterator:
            try:
                records.append(StructuralSearchHit.model_validate_json(line))
            except ValidationError as error:
                raise ResultParseError(
                    f"invalid structural hit at line {line_number}: {path}"
                ) from error
    return records


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = load_json_document(path.resolve(strict=True))
    except ContractLoadError as error:
        raise ResultParseError(
            f"cannot load structural-search manifest: {error}"
        ) from error
    if not isinstance(value, dict):
        raise ResultParseError("structural-search manifest must be a JSON object")
    return value


def _resolved_output(root: Path, record: object, *, name: str) -> tuple[Path, str]:
    if not isinstance(record, dict):
        raise ResultParseError(f"search manifest output {name} must be an object")
    relative_value = record.get("path")
    digest = record.get("sha256")
    if not isinstance(relative_value, str) or not isinstance(digest, str):
        raise ResultParseError(f"search manifest output {name} is incomplete")
    relative = PurePosixPath(relative_value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ResultParseError(f"search manifest output {name} has an unsafe path")
    path = root.joinpath(*relative.parts)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ResultParseError(
            f"search manifest output {name} escapes or is missing"
        ) from error
    if path.is_symlink() or not resolved.is_file():
        raise ResultParseError(f"search manifest output {name} is not a regular file")
    return resolved, digest


def _trace(path: Path, *, expected_status: str) -> list[dict[str, str]]:
    resolved = path.resolve(strict=True)
    with resolved.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or not set(_TRACE_FIELDS).issubset(
            reader.fieldnames
        ):
            raise ResultParseError(f"Nextflow trace has incomplete headers: {resolved}")
        rows = list(reader)
    if not rows:
        raise ResultParseError(f"Nextflow trace contains no process rows: {resolved}")
    if any(row["status"] != expected_status for row in rows):
        raise ResultParseError(
            "Nextflow trace does not contain only "
            f"{expected_status} processes: {resolved}"
        )
    return rows


def _trace_measurements(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{field: row.get(field, "") for field in _TRACE_FIELDS} for row in rows]


def _tree_size(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ResultParseError(f"search output contains a symbolic link: {path}")
        if path.is_file():
            total += path.stat().st_size
    return total


def qualify_p1_search(request: P1QualificationRequest) -> Path:
    """Validate one real direct-PDB run and write its P1 evidence record."""

    search_root = request.search_directory.resolve(strict=True)
    if not search_root.is_dir() or request.search_directory.is_symlink():
        raise ResultParseError("P1 search directory is not a regular directory")
    sequence_groups = _read_sequence_groups(
        request.sequence_groups_jsonl, progress=request.progress
    )
    control = load_public_control_spec(request.control_specification)
    manifest_path = search_root / "search_manifest.json"
    manifest = _load_manifest(manifest_path)
    if (
        manifest.get("schema_version") != "1.0"
        or manifest.get("provider") != "pdb_sequence_mmseqs"
    ):
        raise ResultParseError("P1 search manifest has an unexpected provider contract")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != _REQUIRED_OUTPUTS:
        raise ResultParseError("P1 search manifest output inventory is incomplete")

    resolved_outputs: dict[str, Path] = {}
    for name in sorted(_REQUIRED_OUTPUTS):
        path, expected_digest = _resolved_output(search_root, outputs[name], name=name)
        actual_digest = sha256_file(path, progress=request.progress, logger=_LOGGER)
        if actual_digest != expected_digest:
            raise ResultParseError(f"P1 search output checksum differs: {name}")
        resolved_outputs[name] = path

    results = _read_results(
        resolved_outputs["search_results"], progress=request.progress
    )
    hits = _read_hits(resolved_outputs["structural_hits"], progress=request.progress)
    group_ids = {record.sequence_group_id for record in sequence_groups}
    result_ids = [record.sequence_group_id for record in results]
    if len(result_ids) != len(set(result_ids)) or set(result_ids) != group_ids:
        raise ResultParseError(
            "P1 results do not contain exactly one record per supplied sequence group"
        )
    embedded_hits = [hit for result in results for hit in result.hits]
    embedded_ids = [hit.hit_id for hit in embedded_hits]
    flattened_ids = [hit.hit_id for hit in hits]
    if (
        len(embedded_ids) != len(set(embedded_ids))
        or len(flattened_ids) != len(set(flattened_ids))
        or set(embedded_ids) != set(flattened_ids)
    ):
        raise ResultParseError("embedded and flattened P1 hit identities differ")
    for hit in hits:
        if (
            hit.pdb_id is None
            or hit.identifier_namespace is None
            or hit.target_chain_or_entity is None
            or hit.model_key
            != (
                f"pdb:{hit.pdb_id}:{hit.identifier_namespace}:"
                f"{hit.target_chain_or_entity}"
            )
        ):
            raise ResultParseError(
                f"P1 hit lacks a retrievable PDB model key: {hit.hit_id}"
            )

    target_group_id = f"seq_{control.target_sequence_sha256}"
    group_by_id = {record.sequence_group_id: record for record in sequence_groups}
    target_group = group_by_id.get(target_group_id)
    if target_group is None or target_group.sha256 != control.target_sequence_sha256:
        raise ResultParseError("8OOX control sequence is absent from the P1 catalogue")
    family_pdb_ids = {control.target_pdb_id}
    family_pdb_ids.update(
        resource.pdb_id
        for resource in control.resources
        if resource.role in {"target_coordinates", "exact_mr_coordinates"}
    )
    control_hits = [
        hit
        for hit in hits
        if hit.sequence_group_id == target_group_id
        and hit.pdb_id is not None
        and hit.pdb_id.upper() in family_pdb_ids
    ]
    if not control_hits:
        raise ResultParseError(
            "P1 direct PDB search did not retain the 8OOX exact structural family"
        )

    first_rows = _trace(request.first_trace_tsv, expected_status="COMPLETED")
    resume_rows = _trace(request.resume_trace_tsv, expected_status="CACHED")
    if len(first_rows) != len(resume_rows):
        raise ResultParseError(
            "P1 first and resume traces have different process counts"
        )
    if manifest.get("query_count") != len(sequence_groups) or manifest.get(
        "hit_count"
    ) != len(hits):
        raise ResultParseError("P1 manifest counts differ from the validated records")

    evidence = {
        "schema_version": "1.0",
        "qualified_at": utc_now().isoformat().replace("+00:00", "Z"),
        "profile": "p1",
        "status": "passed",
        "provider": "pdb_sequence_mmseqs",
        "control_id": control.control_id,
        "control_sequence_group_id": target_group_id,
        "accepted_control_pdb_ids": sorted(family_pdb_ids),
        "retained_control_hits": [
            {
                "hit_id": hit.hit_id,
                "pdb_id": hit.pdb_id,
                "model_key": hit.model_key,
                "provider_rank": hit.provider_rank,
                "evalue": hit.evalue,
                "bits": hit.bits,
                "query_coverage": hit.query_coverage,
                "sequence_identity": hit.sequence_identity,
            }
            for hit in control_hits
        ],
        "query_count": len(sequence_groups),
        "hit_count": len(hits),
        "result_size_bytes": _tree_size(search_root),
        "search_manifest_sha256": sha256_file(manifest_path, progress=False),
        "first_process_count": len(first_rows),
        "resume_process_count": len(resume_rows),
        "cached_process_count": len(resume_rows),
        "all_resume_processes_cached": True,
        "first_process_measurements": _trace_measurements(first_rows),
        "resume_process_measurements": _trace_measurements(resume_rows),
        "io_measurement_semantics": (
            "Nextflow trace rchar/wchar counters; these include process I/O and are "
            "not guaranteed to equal physical database-device bytes"
        ),
    }
    atomic_write_json(request.output_json, evidence)
    _LOGGER.info(
        "P1 direct-PDB search qualified",
        extra={
            "query_count": len(sequence_groups),
            "hit_count": len(hits),
            "control_hit_count": len(control_hits),
            "result_size_bytes": evidence["result_size_bytes"],
            "report": str(request.output_json),
        },
    )
    return request.output_json
