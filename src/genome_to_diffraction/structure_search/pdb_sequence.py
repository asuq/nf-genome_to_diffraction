"""Local MMseqs2 sequence search against an immutable PDB SEQRES resource."""

import csv
import logging
import math
import os
import shlex
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.databases.common import tool_version
from genome_to_diffraction.ids import canonical_digest, canonical_json_text, content_id
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    DatabaseManifest,
    DatabaseResource,
    DatabaseResourceStatus,
    SmokeTestStatus,
)
from genome_to_diffraction.schemas.results import (
    EligibilityStatus,
    SearchScientificStatus,
    SequenceGroupRecord,
    StructuralSearchHit,
    StructuralSearchResult,
)
from genome_to_diffraction.status import (
    ExecutionStatus,
    InputContractError,
    ResultParseError,
    ToolExecutionError,
)
from genome_to_diffraction.time import utc_now

_LOGGER = logging.getLogger("genome_to_diffraction.structure_search.pdb_sequence")
_ADAPTER_VERSION = "pdb-sequence-mmseqs-v1"
_PROVIDER = "pdb_sequence_mmseqs"
_STANDARD_AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
_RESULT_FIELDS = (
    "query",
    "target",
    "qstart",
    "qend",
    "tstart",
    "tend",
    "alnlen",
    "qcov",
    "tcov",
    "fident",
    "evalue",
    "bits",
)


@dataclass(frozen=True)
class PdbSequenceSearchRequest:
    """Inputs and bounded parameters for one catalogue-wide search."""

    sequence_groups_jsonl: Path
    database_manifest: Path
    output_directory: Path
    threads: int = 4
    maximum_hits_per_query: int = 25
    maximum_evalue: float = 1.0e-5
    minimum_query_coverage: float = 0.5
    maximum_query_length: int = 10_000
    progress: bool = True


@dataclass(frozen=True)
class PdbSequenceSearchOutput:
    """Published records from a successful search invocation."""

    results: tuple[StructuralSearchResult, ...]
    results_jsonl: Path
    hits_jsonl: Path
    search_manifest: Path


@dataclass(frozen=True)
class _RawHit:
    query: str
    target: str
    query_start: int
    query_end: int
    target_start: int
    target_end: int
    aligned_length: int
    query_coverage: float
    target_coverage: float
    identity_fraction: float
    evalue: float
    bits: float


@dataclass(frozen=True)
class _TargetMapping:
    target_id: str
    pdb_id: str
    namespace: str
    token: str


def _validate_request(request: PdbSequenceSearchRequest) -> None:
    if request.threads < 1:
        raise ValueError("threads must be positive")
    if request.maximum_hits_per_query < 1 or request.maximum_hits_per_query > 1000:
        raise ValueError("maximum_hits_per_query must be between 1 and 1000")
    if not math.isfinite(request.maximum_evalue) or request.maximum_evalue <= 0:
        raise ValueError("maximum_evalue must be positive and finite")
    if (
        not math.isfinite(request.minimum_query_coverage)
        or not 0 <= request.minimum_query_coverage <= 1
    ):
        raise ValueError("minimum_query_coverage must be between 0 and 1")
    if request.maximum_query_length < 1:
        raise ValueError("maximum_query_length must be positive")


def _load_sequence_groups(
    path: Path, *, progress: bool
) -> tuple[SequenceGroupRecord, ...]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise InputContractError(f"sequence-group input is not a file: {resolved}")
    records: list[SequenceGroupRecord] = []
    identifiers: set[str] = set()
    with resolved.open(encoding="utf-8") as handle:
        iterator = tqdm(
            enumerate(handle, start=1),
            desc="Validate sequence groups",
            unit="sequence",
            disable=not progress,
        )
        for line_number, line in iterator:
            if not line.strip():
                raise InputContractError(
                    f"blank sequence-group record at line {line_number}: {resolved}"
                )
            try:
                record = SequenceGroupRecord.model_validate_json(line)
            except ValidationError as error:
                raise InputContractError(
                    f"invalid sequence-group record at line {line_number}: {resolved}"
                ) from error
            if record.sequence_group_id in identifiers:
                raise InputContractError(
                    f"duplicate sequence_group_id: {record.sequence_group_id}"
                )
            identifiers.add(record.sequence_group_id)
            records.append(record)
    if not records:
        raise InputContractError(f"sequence-group input is empty: {resolved}")
    return tuple(sorted(records, key=lambda item: item.sequence_group_id))


def _pdb_sequence_resource(manifest_path: Path) -> DatabaseResource:
    manifest = load_contract(
        manifest_path,
        "database-manifest",
        progress=False,
    )
    if not isinstance(manifest, DatabaseManifest):
        raise AssertionError("database-manifest loader returned an unexpected model")
    matches = tuple(
        resource for resource in manifest.resources if resource.name == "pdb_sequences"
    )
    if len(matches) != 1:
        raise InputContractError(
            "database manifest must contain exactly one pdb_sequences resource"
        )
    resource = matches[0]
    if (
        resource.status is not DatabaseResourceStatus.READY
        or resource.smoke_test_status is not SmokeTestStatus.PASSED
        or resource.prepared_with.tool != "mmseqs"
    ):
        raise InputContractError("pdb_sequences resource is not qualified for search")
    return resource


def _eligibility(record: SequenceGroupRecord, maximum_length: int) -> str | None:
    if any(flag.startswith("excluded_") for flag in record.quality_flags):
        return "catalogue record is excluded by its quality policy"
    unsupported = sorted(set(record.sequence) - _STANDARD_AMINO_ACIDS)
    if unsupported:
        return "query contains ambiguous or non-standard residues: " + "".join(
            unsupported
        )
    if record.length_aa > maximum_length:
        return f"query exceeds maximum length {maximum_length}"
    return None


def _write_query_fasta(path: Path, records: tuple[SequenceGroupRecord, ...]) -> None:
    text = "".join(
        f">{record.sequence_group_id}\n{record.sequence}\n" for record in records
    )
    atomic_write_text(path, text, encoding="ascii")


def _execute_mmseqs(command: list[str], log_path: Path) -> None:
    _LOGGER.info(
        "PDB sequence search started",
        extra={"command": command, "log": str(log_path)},
    )
    started = utc_now()
    try:
        with log_path.open("w", encoding="utf-8") as log_handle:
            log_handle.write("resolved_command=" + shlex.join(command) + "\n")
            log_handle.flush()
            completed = subprocess.run(
                command,
                check=False,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            log_handle.flush()
            os.fsync(log_handle.fileno())
    except OSError as error:
        raise ToolExecutionError(f"cannot execute MMseqs2 search: {error}") from error
    if completed.returncode != 0:
        raise ToolExecutionError(
            f"MMseqs2 search failed with exit status {completed.returncode}; "
            f"see {log_path}"
        )
    _LOGGER.info(
        "PDB sequence search completed",
        extra={
            "exit_status": completed.returncode,
            "started_at": started.isoformat(),
            "finished_at": utc_now().isoformat(),
        },
    )


def _parse_float(value: str, *, line_number: int, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise ResultParseError(
            f"non-numeric MMseqs2 {name} at result line {line_number}"
        ) from error
    if not math.isfinite(parsed):
        raise ResultParseError(
            f"non-finite MMseqs2 {name} at result line {line_number}"
        )
    return parsed


def _parse_positive_int(value: str, *, line_number: int, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ResultParseError(
            f"non-integer MMseqs2 {name} at result line {line_number}"
        ) from error
    if parsed < 1:
        raise ResultParseError(
            f"non-positive MMseqs2 {name} at result line {line_number}"
        )
    return parsed


def _parse_results(
    path: Path,
    *,
    query_ids: frozenset[str],
    maximum_hits_per_query: int,
    progress: bool,
) -> dict[str, tuple[_RawHit, ...]]:
    grouped: dict[str, list[_RawHit]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8") as handle:
        iterator = tqdm(
            enumerate(handle, start=1),
            desc="Parse PDB sequence hits",
            unit="hit",
            disable=not progress,
        )
        for line_number, line in iterator:
            fields = line.rstrip("\n").split("\t")
            if len(fields) != len(_RESULT_FIELDS):
                raise ResultParseError(
                    f"MMseqs2 result line {line_number} has {len(fields)} fields; "
                    f"expected {len(_RESULT_FIELDS)}"
                )
            values = dict(zip(_RESULT_FIELDS, fields, strict=True))
            query = values["query"]
            target = values["target"]
            if query not in query_ids:
                raise ResultParseError(
                    f"MMseqs2 returned unknown query at line {line_number}: {query}"
                )
            if not target or any(character.isspace() for character in target):
                raise ResultParseError(
                    f"invalid MMseqs2 target at result line {line_number}"
                )
            key = (query, target)
            if key in seen:
                raise ResultParseError(
                    f"duplicate MMseqs2 query/target result: {query}/{target}"
                )
            seen.add(key)
            query_start = _parse_positive_int(
                values["qstart"], line_number=line_number, name="qstart"
            )
            query_end = _parse_positive_int(
                values["qend"], line_number=line_number, name="qend"
            )
            target_start = _parse_positive_int(
                values["tstart"], line_number=line_number, name="tstart"
            )
            target_end = _parse_positive_int(
                values["tend"], line_number=line_number, name="tend"
            )
            aligned_length = _parse_positive_int(
                values["alnlen"], line_number=line_number, name="alnlen"
            )
            query_coverage = _parse_float(
                values["qcov"], line_number=line_number, name="qcov"
            )
            target_coverage = _parse_float(
                values["tcov"], line_number=line_number, name="tcov"
            )
            identity_fraction = _parse_float(
                values["fident"], line_number=line_number, name="fident"
            )
            evalue = _parse_float(
                values["evalue"], line_number=line_number, name="evalue"
            )
            bits = _parse_float(values["bits"], line_number=line_number, name="bits")
            if (
                query_start > query_end
                or target_start > target_end
                or not 0 <= query_coverage <= 1
                or not 0 <= target_coverage <= 1
                or not 0 <= identity_fraction <= 1
                or evalue < 0
                or bits <= 0
            ):
                raise ResultParseError(
                    f"out-of-range MMseqs2 metric at result line {line_number}"
                )
            grouped[query].append(
                _RawHit(
                    query=query,
                    target=target,
                    query_start=query_start,
                    query_end=query_end,
                    target_start=target_start,
                    target_end=target_end,
                    aligned_length=aligned_length,
                    query_coverage=query_coverage,
                    target_coverage=target_coverage,
                    identity_fraction=identity_fraction,
                    evalue=evalue,
                    bits=bits,
                )
            )
            if len(grouped[query]) > maximum_hits_per_query:
                raise ResultParseError(
                    f"MMseqs2 exceeded the per-query hit cap for {query}"
                )
    return {
        query: tuple(
            sorted(
                hits,
                key=lambda hit: (
                    hit.evalue,
                    -hit.bits,
                    -hit.query_coverage,
                    -hit.target_coverage,
                    -hit.identity_fraction,
                    hit.target,
                ),
            )
        )
        for query, hits in grouped.items()
    }


def _load_target_mappings(
    path: Path, targets: frozenset[str], *, progress: bool
) -> dict[str, _TargetMapping]:
    if not targets:
        return {}
    mappings: dict[str, _TargetMapping] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {
            "target_id",
            "pdb_id",
            "identifier_namespace",
            "seqres_token",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ResultParseError("PDB target mapping has invalid headers")
        iterator = tqdm(
            reader,
            desc="Resolve PDB target mappings",
            unit="mapping",
            disable=not progress,
        )
        for row in iterator:
            target = row["target_id"]
            if target not in targets:
                continue
            if target in mappings:
                raise ResultParseError(f"duplicate PDB target mapping: {target}")
            mappings[target] = _TargetMapping(
                target_id=target,
                pdb_id=row["pdb_id"],
                namespace=row["identifier_namespace"],
                token=row["seqres_token"],
            )
            if len(mappings) == len(targets):
                break
    missing = sorted(targets - mappings.keys())
    if missing:
        raise ResultParseError(
            "PDB search targets lack coordinate mappings: " + ", ".join(missing[:10])
        )
    return mappings


def search_pdb_sequences(
    request: PdbSequenceSearchRequest,
) -> PdbSequenceSearchOutput:
    """Search every eligible exact sequence once and retain explicit no-hits."""

    _validate_request(request)
    sequence_groups = _load_sequence_groups(
        request.sequence_groups_jsonl, progress=request.progress
    )
    resource = _pdb_sequence_resource(request.database_manifest)
    resource_root = Path(resource.root_path).resolve(strict=True)
    database_prefix = resource_root / "pdb_seqres"
    target_mapping_path = resource_root / "target_mapping.tsv"
    if not database_prefix.exists():
        raise InputContractError(f"PDB sequence database is missing: {database_prefix}")
    if not target_mapping_path.is_file():
        raise InputContractError(
            f"PDB target mapping is missing: {target_mapping_path}"
        )
    mmseqs_version = tool_version("mmseqs", arguments=("version",))
    if mmseqs_version != resource.prepared_with.version:
        raise InputContractError(
            "current MMseqs2 version differs from PDB-sequence provenance"
        )

    outdir = request.output_directory.resolve()
    if outdir.exists() and any(outdir.iterdir()):
        raise ValueError(f"structural-search output directory is not empty: {outdir}")
    raw_directory = outdir / "raw"
    raw_directory.mkdir(parents=True, exist_ok=True)
    query_path = raw_directory / "queries.faa"
    result_path = raw_directory / "mmseqs-results.tsv"
    log_path = raw_directory / "mmseqs.log"

    eligible: list[SequenceGroupRecord] = []
    ineligible: dict[str, str] = {}
    for record in sequence_groups:
        reason = _eligibility(record, request.maximum_query_length)
        if reason is None:
            eligible.append(record)
        else:
            ineligible[record.sequence_group_id] = reason
    eligible_records = tuple(eligible)
    _write_query_fasta(query_path, eligible_records)

    identity_payload = {
        "adapter_version": _ADAPTER_VERSION,
        "database_id": resource.database_id,
        "sequence_groups_sha256": sha256_file(
            request.sequence_groups_jsonl, progress=request.progress, logger=_LOGGER
        ),
        "tool": "mmseqs",
        "tool_version": mmseqs_version,
        "parameters": {
            "maximum_hits_per_query": request.maximum_hits_per_query,
            "maximum_evalue": request.maximum_evalue,
            "minimum_query_coverage": request.minimum_query_coverage,
            "maximum_query_length": request.maximum_query_length,
            "alignment_mode": 3,
        },
    }
    batch_cache_key = canonical_digest(identity_payload)
    if eligible_records:
        command = [
            "mmseqs",
            "easy-search",
            str(query_path),
            str(database_prefix),
            str(result_path),
            str(raw_directory / "tmp"),
            "--threads",
            str(request.threads),
            "--max-seqs",
            str(request.maximum_hits_per_query),
            "-e",
            str(request.maximum_evalue),
            "-c",
            str(request.minimum_query_coverage),
            "--cov-mode",
            "0",
            "--alignment-mode",
            "3",
            "--format-output",
            ",".join(_RESULT_FIELDS),
        ]
        _execute_mmseqs(command, log_path)
    else:
        atomic_write_text(result_path, "")
        atomic_write_text(log_path, "no eligible query sequences\n")

    raw_hits = _parse_results(
        result_path,
        query_ids=frozenset(record.sequence_group_id for record in eligible_records),
        maximum_hits_per_query=request.maximum_hits_per_query,
        progress=request.progress,
    )
    target_mappings = _load_target_mappings(
        target_mapping_path,
        frozenset(hit.target for hits in raw_hits.values() for hit in hits),
        progress=request.progress,
    )
    raw_result_sha256 = sha256_file(result_path, progress=False)
    command_log_sha256 = sha256_file(log_path, progress=False)
    raw_pointer = "raw/mmseqs-results.tsv"
    log_pointer = "raw/mmseqs.log"

    results: list[StructuralSearchResult] = []
    all_hits: list[StructuralSearchHit] = []
    for record in sequence_groups:
        record_hits: list[StructuralSearchHit] = []
        for rank, raw_hit in enumerate(raw_hits.get(record.sequence_group_id, ()), 1):
            mapping = target_mappings[raw_hit.target]
            hit_identity = {
                "sequence_group_id": record.sequence_group_id,
                "provider": _PROVIDER,
                "database_id": resource.database_id,
                "target": raw_hit.target,
                "query_start": raw_hit.query_start,
                "query_end": raw_hit.query_end,
                "target_start": raw_hit.target_start,
                "target_end": raw_hit.target_end,
                "evalue": raw_hit.evalue,
                "bits": raw_hit.bits,
            }
            hit = StructuralSearchHit(
                schema_version="1.0",
                hit_id=content_id("hit_", hit_identity),
                sequence_group_id=record.sequence_group_id,
                provider=_PROVIDER,
                provider_rank=rank,
                target_id=raw_hit.target,
                target_chain_or_entity=mapping.token,
                pdb_id=mapping.pdb_id,
                identifier_namespace=mapping.namespace,
                query_start=raw_hit.query_start,
                query_end=raw_hit.query_end,
                target_start=raw_hit.target_start,
                target_end=raw_hit.target_end,
                aligned_length=raw_hit.aligned_length,
                query_coverage=raw_hit.query_coverage,
                target_coverage=raw_hit.target_coverage,
                sequence_identity=raw_hit.identity_fraction,
                evalue=raw_hit.evalue,
                bits=raw_hit.bits,
                database_id=resource.database_id,
                raw_result_pointer=raw_pointer,
                raw_metrics={"identity_fraction": raw_hit.identity_fraction},
                eligibility_status=EligibilityStatus.SELECTED,
                eligibility_reason="passed configured PDB sequence-search thresholds",
            )
            record_hits.append(hit)
            all_hits.append(hit)

        reason = ineligible.get(record.sequence_group_id)
        warnings: tuple[str, ...]
        if reason is not None:
            execution_status = ExecutionStatus.SKIPPED_INELIGIBLE
            scientific_status = SearchScientificStatus.NOT_INTERPRETABLE
            warnings = (reason,)
        elif record_hits:
            execution_status = ExecutionStatus.COMPLETED_HIT
            scientific_status = SearchScientificStatus.HITS_FOUND
            warnings = ()
        else:
            execution_status = ExecutionStatus.COMPLETED_NO_HIT
            scientific_status = SearchScientificStatus.NO_HIT
            warnings = ()
        cache_key = canonical_digest(
            {
                "adapter_version": _ADAPTER_VERSION,
                "database_id": resource.database_id,
                "tool": "mmseqs",
                "tool_version": mmseqs_version,
                "parameters": identity_payload["parameters"],
                "sequence_sha256": record.sha256,
                "quality_flags": record.quality_flags,
            }
        )
        results.append(
            StructuralSearchResult(
                schema_version="1.0",
                search_id=content_id(
                    "srch_",
                    {
                        "cache_key": cache_key,
                        "provider": _PROVIDER,
                        "sequence_group_id": record.sequence_group_id,
                    },
                ),
                sequence_group_id=record.sequence_group_id,
                provider=_PROVIDER,
                database_id=resource.database_id,
                tool="mmseqs",
                tool_version=mmseqs_version,
                adapter_version=_ADAPTER_VERSION,
                cache_key=cache_key,
                execution_status=execution_status,
                scientific_status=scientific_status,
                hit_count=len(record_hits),
                hits=tuple(record_hits),
                raw_result_pointer=raw_pointer,
                raw_result_sha256=raw_result_sha256,
                command_log_pointer=log_pointer,
                command_log_sha256=command_log_sha256,
                warnings=warnings,
            )
        )

    results_path = outdir / "search_results.jsonl"
    hits_path = outdir / "structural_hits.jsonl"
    manifest_path = outdir / "search_manifest.json"
    atomic_write_text(
        results_path,
        "".join(f"{canonical_json_text(result)}\n" for result in results),
    )
    atomic_write_text(
        hits_path,
        "".join(f"{canonical_json_text(hit)}\n" for hit in all_hits),
    )
    status_counts: dict[str, int] = defaultdict(int)
    for result in results:
        status_counts[result.execution_status.value] += 1
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "provider": _PROVIDER,
            "adapter_version": _ADAPTER_VERSION,
            "database_id": resource.database_id,
            "tool": "mmseqs",
            "tool_version": mmseqs_version,
            "batch_cache_key": batch_cache_key,
            "query_count": len(sequence_groups),
            "eligible_query_count": len(eligible_records),
            "hit_count": len(all_hits),
            "status_counts": dict(sorted(status_counts.items())),
            "parameters": identity_payload["parameters"],
            "outputs": {
                "search_results": {
                    "path": results_path.name,
                    "sha256": sha256_file(results_path, progress=False),
                },
                "structural_hits": {
                    "path": hits_path.name,
                    "sha256": sha256_file(hits_path, progress=False),
                },
                "raw_result": {
                    "path": raw_pointer,
                    "sha256": raw_result_sha256,
                },
                "command_log": {
                    "path": log_pointer,
                    "sha256": command_log_sha256,
                },
            },
        },
    )
    _LOGGER.info(
        "PDB sequence-search outputs published",
        extra={
            "query_count": len(results),
            "eligible_query_count": len(eligible_records),
            "hit_count": len(all_hits),
            "output_directory": str(outdir),
        },
    )
    return PdbSequenceSearchOutput(
        results=tuple(results),
        results_jsonl=results_path,
        hits_jsonl=hits_path,
        search_manifest=manifest_path,
    )
