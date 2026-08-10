"""ProstT5 sequence-to-3Di search against an immutable Foldseek PDB resource."""

import csv
import logging
import math
import os
import re
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

_LOGGER = logging.getLogger("genome_to_diffraction.structure_search.prostt5_foldseek")
_ADAPTER_VERSION = "prostt5-foldseek-pdb-v2"
_PROVIDER = "foldseek_prostt5_pdb"
_RAW_HIT_LIMIT = 1000
_FAILURE_LOG_TAIL_BYTES = 16 * 1024
_FAILURE_LOG_TAIL_LINES = 40
_STANDARD_AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
_PDB_TARGET = re.compile(
    r"^(?P<pdb_id>[0-9][A-Za-z0-9]{3})"
    r"(?:-assembly(?P<assembly_number>[1-9][0-9]*))?"
    r"_(?P<chain>[^\s\t]+)$"
)
_RESULT_FIELDS = (
    "query",
    "target",
    "fident",
    "alnlen",
    "qstart",
    "qend",
    "tstart",
    "tend",
    "qlen",
    "tlen",
    "qcov",
    "tcov",
    "evalue",
    "bits",
)
_PROBABILITY_UNAVAILABLE_REASON = (
    "Foldseek prob requires query and target C-alpha coordinates; "
    "ProstT5 sequence queries do not provide query C-alpha coordinates"
)


@dataclass(frozen=True)
class ProstT5FoldseekSearchRequest:
    """Inputs and bounded parameters for one catalogue-wide structural search."""

    sequence_groups_jsonl: Path
    database_manifest: Path
    output_directory: Path
    threads: int = 4
    maximum_hits_per_query: int = 3
    maximum_evalue: float = 1.0e-3
    minimum_query_coverage: float = 0.5
    maximum_query_length: int = 10_000
    maximum_queries: int = 0
    gpu: bool = False
    progress: bool = True


@dataclass(frozen=True)
class ProstT5FoldseekSearchOutput:
    """Published records from a successful ProstT5/Foldseek invocation."""

    results: tuple[StructuralSearchResult, ...]
    results_jsonl: Path
    hits_jsonl: Path
    search_manifest: Path


@dataclass(frozen=True)
class _Resources:
    pdb_foldseek: DatabaseResource
    prostt5: DatabaseResource
    pdb_sequences: DatabaseResource


@dataclass(frozen=True)
class _RawHit:
    query: str
    target: str
    query_start: int
    query_end: int
    target_start: int
    target_end: int
    aligned_length: int
    query_length: int
    target_length: int
    identity_fraction: float
    query_coverage: float
    target_coverage: float
    evalue: float
    bits: float


@dataclass(frozen=True)
class _TargetMapping:
    pdb_id: str
    namespace: str
    token: str
    seqres_target: str


def _validate_request(request: ProstT5FoldseekSearchRequest) -> None:
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
    if request.maximum_queries < 0:
        raise ValueError("maximum_queries cannot be negative")


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


def _load_resources(manifest_path: Path) -> _Resources:
    manifest = load_contract(manifest_path, "database-manifest", progress=False)
    if not isinstance(manifest, DatabaseManifest):
        raise AssertionError("database-manifest loader returned an unexpected model")
    resources: dict[str, DatabaseResource] = {}
    for name in ("pdb_foldseek", "prostt5", "pdb_sequences"):
        matches = tuple(
            resource for resource in manifest.resources if resource.name == name
        )
        if len(matches) != 1:
            raise InputContractError(
                f"database manifest must contain exactly one {name} resource"
            )
        resource = matches[0]
        if (
            resource.status is not DatabaseResourceStatus.READY
            or resource.smoke_test_status is not SmokeTestStatus.PASSED
        ):
            raise InputContractError(f"{name} resource is not qualified for search")
        resources[name] = resource
    pdb = resources["pdb_foldseek"]
    prostt5 = resources["prostt5"]
    sequences = resources["pdb_sequences"]
    if pdb.prepared_with.tool != "foldseek" or prostt5.prepared_with.tool != "foldseek":
        raise InputContractError("Foldseek resources have incompatible provenance")
    if sequences.prepared_with.tool != "mmseqs":
        raise InputContractError("PDB target crosswalk has incompatible provenance")
    if pdb.prepared_with.version != prostt5.prepared_with.version:
        raise InputContractError(
            "PDB and ProstT5 resources use different Foldseek versions"
        )
    return _Resources(
        pdb_foldseek=pdb,
        prostt5=prostt5,
        pdb_sequences=sequences,
    )


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
    atomic_write_text(
        path,
        "".join(
            f">{record.sequence_group_id}\n{record.sequence}\n" for record in records
        ),
        encoding="ascii",
    )


def _failure_log_tail(log_path: Path) -> str:
    """Return a bounded, printable tail suitable for durable error records."""

    try:
        with log_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - _FAILURE_LOG_TAIL_BYTES))
            content = handle.read().decode("utf-8", errors="replace")
    except OSError as error:
        return f"<unable to read Foldseek log: {error}>"
    lines = content.splitlines()[-_FAILURE_LOG_TAIL_LINES:]
    return "\n".join(lines) if lines else "<Foldseek log was empty>"


def _execute_foldseek(command: list[str], log_path: Path) -> None:
    _LOGGER.info(
        "ProstT5/Foldseek PDB search started",
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
        raise ToolExecutionError(f"cannot execute Foldseek search: {error}") from error
    if completed.returncode != 0:
        log_tail = _failure_log_tail(log_path)
        raise ToolExecutionError(
            f"Foldseek search failed with exit status {completed.returncode}; "
            f"bounded tail of {log_path}:\n{log_tail}"
        )
    _LOGGER.info(
        "ProstT5/Foldseek PDB search completed",
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
            f"non-numeric Foldseek {name} at result line {line_number}"
        ) from error
    if not math.isfinite(parsed):
        raise ResultParseError(
            f"non-finite Foldseek {name} at result line {line_number}"
        )
    return parsed


def _parse_positive_int(value: str, *, line_number: int, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ResultParseError(
            f"non-integer Foldseek {name} at result line {line_number}"
        ) from error
    if parsed < 1:
        raise ResultParseError(
            f"non-positive Foldseek {name} at result line {line_number}"
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
            desc="Parse ProstT5/Foldseek hits",
            unit="hit",
            disable=not progress,
        )
        for line_number, line in iterator:
            fields = line.rstrip("\n").split("\t")
            if len(fields) != len(_RESULT_FIELDS):
                raise ResultParseError(
                    f"Foldseek result line {line_number} has {len(fields)} fields; "
                    f"expected {len(_RESULT_FIELDS)}"
                )
            values = dict(zip(_RESULT_FIELDS, fields, strict=True))
            query = values["query"]
            target = values["target"]
            if query not in query_ids:
                raise ResultParseError(
                    f"Foldseek returned unknown query at line {line_number}: {query}"
                )
            if not target or any(character.isspace() for character in target):
                raise ResultParseError(
                    f"invalid Foldseek target at result line {line_number}"
                )
            key = (query, target)
            if key in seen:
                raise ResultParseError(
                    f"duplicate Foldseek query/target result: {query}/{target}"
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
            query_length = _parse_positive_int(
                values["qlen"], line_number=line_number, name="qlen"
            )
            target_length = _parse_positive_int(
                values["tlen"], line_number=line_number, name="tlen"
            )
            identity_fraction = _parse_float(
                values["fident"], line_number=line_number, name="fident"
            )
            evalue = _parse_float(
                values["evalue"], line_number=line_number, name="evalue"
            )
            bits = _parse_float(values["bits"], line_number=line_number, name="bits")
            query_coverage = _parse_float(
                values["qcov"], line_number=line_number, name="qcov"
            )
            target_coverage = _parse_float(
                values["tcov"], line_number=line_number, name="tcov"
            )
            if (
                query_start > query_end
                or query_end > query_length
                or target_start > target_end
                or target_end > target_length
                or not 0 <= identity_fraction <= 1
                or not 0 <= query_coverage <= 1
                or not 0 <= target_coverage <= 1
                or evalue < 0
                or bits <= 0
            ):
                raise ResultParseError(
                    f"out-of-range Foldseek metric at result line {line_number}"
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
                    query_length=query_length,
                    target_length=target_length,
                    identity_fraction=identity_fraction,
                    query_coverage=query_coverage,
                    target_coverage=target_coverage,
                    evalue=evalue,
                    bits=bits,
                )
            )
            if len(grouped[query]) > _RAW_HIT_LIMIT:
                raise ResultParseError(
                    f"Foldseek exceeded the raw per-query hit limit for {query}"
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
                    hit.target,
                ),
            )[:maximum_hits_per_query]
        )
        for query, hits in grouped.items()
    }


def _target_key(target: str) -> tuple[str, str]:
    match = _PDB_TARGET.fullmatch(target)
    if match is None:
        raise ResultParseError(f"unsupported Foldseek PDB target identifier: {target}")
    return match.group("pdb_id").upper(), match.group("chain")


def _load_target_mappings(
    path: Path, targets: frozenset[str], *, progress: bool
) -> dict[str, _TargetMapping]:
    target_keys = {target: _target_key(target) for target in targets}
    if not target_keys:
        return {}
    needed = frozenset(target_keys.values())
    by_key: dict[tuple[str, str], _TargetMapping] = {}
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
            desc="Resolve Foldseek PDB targets",
            unit="mapping",
            disable=not progress,
        )
        for row in iterator:
            key = (row["pdb_id"].upper(), row["seqres_token"])
            if key not in needed:
                continue
            if key in by_key:
                raise ResultParseError(
                    f"duplicate PDB target mapping: {row['target_id']}"
                )
            by_key[key] = _TargetMapping(
                pdb_id=key[0],
                namespace=row["identifier_namespace"],
                token=key[1],
                seqres_target=row["target_id"],
            )
            if len(by_key) == len(needed):
                break
    missing = sorted(needed - by_key.keys())
    if missing:
        formatted = ", ".join(f"{pdb_id}_{chain}" for pdb_id, chain in missing[:10])
        raise ResultParseError(
            "Foldseek PDB targets lack coordinate mappings: " + formatted
        )
    return {target: by_key[key] for target, key in target_keys.items()}


def search_prostt5_foldseek(
    request: ProstT5FoldseekSearchRequest,
) -> ProstT5FoldseekSearchOutput:
    """Search every eligible exact sequence and retain explicit no-hits."""

    _validate_request(request)
    sequence_groups = _load_sequence_groups(
        request.sequence_groups_jsonl, progress=request.progress
    )
    resources = _load_resources(request.database_manifest)
    pdb_root = Path(resources.pdb_foldseek.root_path).resolve(strict=True)
    prostt5_root = Path(resources.prostt5.root_path).resolve(strict=True)
    sequence_root = Path(resources.pdb_sequences.root_path).resolve(strict=True)
    database_prefix = pdb_root / "pdb"
    weights_prefix = prostt5_root / "weights"
    target_mapping_path = sequence_root / "target_mapping.tsv"
    if not database_prefix.exists():
        raise InputContractError(f"Foldseek PDB database is missing: {database_prefix}")
    if not weights_prefix.exists():
        raise InputContractError(f"ProstT5 weights are missing: {weights_prefix}")
    if not target_mapping_path.is_file():
        raise InputContractError(
            f"PDB target mapping is missing: {target_mapping_path}"
        )
    foldseek_version = tool_version("foldseek", arguments=("version",))
    if foldseek_version != resources.pdb_foldseek.prepared_with.version:
        raise InputContractError(
            "current Foldseek version differs from PDB/ProstT5 provenance"
        )

    outdir = request.output_directory.resolve()
    if outdir.exists() and any(outdir.iterdir()):
        raise ValueError(f"structural-search output directory is not empty: {outdir}")
    raw_directory = outdir / "raw"
    raw_directory.mkdir(parents=True, exist_ok=True)
    query_path = raw_directory / "queries.faa"
    result_path = raw_directory / "foldseek-results.tsv"
    log_path = raw_directory / "foldseek.log"

    eligible: list[SequenceGroupRecord] = []
    ineligible: dict[str, str] = {}
    for record in sequence_groups:
        reason = _eligibility(record, request.maximum_query_length)
        if reason is None:
            eligible.append(record)
        else:
            ineligible[record.sequence_group_id] = reason
    eligible_before_query_cap = tuple(eligible)
    policy_skipped: dict[str, str] = {}
    if request.maximum_queries and len(eligible) > request.maximum_queries:
        for record in eligible[request.maximum_queries :]:
            policy_skipped[record.sequence_group_id] = (
                "query deferred by the configured deterministic pilot cap of "
                f"{request.maximum_queries} sequences"
            )
        eligible_records = tuple(eligible[: request.maximum_queries])
    else:
        eligible_records = eligible_before_query_cap
    _LOGGER.info(
        "ProstT5/Foldseek query batch selected",
        extra={
            "query_count": len(sequence_groups),
            "eligible_before_query_cap_count": len(eligible_before_query_cap),
            "selected_query_count": len(eligible_records),
            "deferred_query_count": len(policy_skipped),
            "maximum_queries": request.maximum_queries,
        },
    )
    _write_query_fasta(query_path, eligible_records)

    parameters = {
        "maximum_hits_per_query": request.maximum_hits_per_query,
        "raw_hit_limit_per_query": _RAW_HIT_LIMIT,
        "maximum_evalue": request.maximum_evalue,
        "minimum_query_coverage": request.minimum_query_coverage,
        "maximum_query_length": request.maximum_query_length,
        "maximum_queries": request.maximum_queries,
        "coverage_mode": 2,
        "gpu": request.gpu,
        "output_fields": list(_RESULT_FIELDS),
    }
    resource_ids = {
        "pdb_foldseek": resources.pdb_foldseek.database_id,
        "prostt5": resources.prostt5.database_id,
        "pdb_sequences": resources.pdb_sequences.database_id,
    }
    identity_payload = {
        "adapter_version": _ADAPTER_VERSION,
        "resources": resource_ids,
        "sequence_groups_sha256": sha256_file(
            request.sequence_groups_jsonl, progress=request.progress, logger=_LOGGER
        ),
        "tool": "foldseek",
        "tool_version": foldseek_version,
        "parameters": parameters,
    }
    batch_cache_key = canonical_digest(identity_payload)
    if eligible_records:
        command = [
            "foldseek",
            "easy-search",
            str(query_path),
            str(database_prefix),
            str(result_path),
            str(raw_directory / "tmp"),
            "--prostt5-model",
            str(weights_prefix),
            "--threads",
            str(request.threads),
            "--max-seqs",
            str(_RAW_HIT_LIMIT),
            "-e",
            str(request.maximum_evalue),
            "-c",
            str(request.minimum_query_coverage),
            "--cov-mode",
            "2",
            "--format-output",
            ",".join(_RESULT_FIELDS),
        ]
        if request.gpu:
            command.extend(("--gpu", "1"))
        _execute_foldseek(command, log_path)
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
    raw_pointer = "raw/foldseek-results.tsv"
    log_pointer = "raw/foldseek.log"

    results: list[StructuralSearchResult] = []
    all_hits: list[StructuralSearchHit] = []
    for record in sequence_groups:
        record_hits: list[StructuralSearchHit] = []
        for rank, raw_hit in enumerate(raw_hits.get(record.sequence_group_id, ()), 1):
            mapping = target_mappings[raw_hit.target]
            hit_identity = {
                "sequence_group_id": record.sequence_group_id,
                "provider": _PROVIDER,
                "resources": resource_ids,
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
                model_key=(f"pdb:{mapping.pdb_id}:{mapping.namespace}:{mapping.token}"),
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
                database_id=resources.pdb_foldseek.database_id,
                raw_result_pointer=raw_pointer,
                raw_metrics={
                    "identity_fraction": raw_hit.identity_fraction,
                    "query_length": raw_hit.query_length,
                    "target_length": raw_hit.target_length,
                    "seqres_target": mapping.seqres_target,
                    "prostt5_database_id": resources.prostt5.database_id,
                    "mapping_database_id": resources.pdb_sequences.database_id,
                    "probability_unavailable_reason": (_PROBABILITY_UNAVAILABLE_REASON),
                },
                eligibility_status=EligibilityStatus.SELECTED,
                eligibility_reason=(
                    "passed configured ProstT5/Foldseek PDB search thresholds"
                ),
            )
            record_hits.append(hit)
            all_hits.append(hit)

        policy_reason = policy_skipped.get(record.sequence_group_id)
        reason = ineligible.get(record.sequence_group_id)
        warnings: tuple[str, ...]
        if policy_reason is not None:
            execution_status = ExecutionStatus.SKIPPED_POLICY
            scientific_status = SearchScientificStatus.NOT_INTERPRETABLE
            warnings = (policy_reason,)
        elif reason is not None:
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
                "resources": resource_ids,
                "tool": "foldseek",
                "tool_version": foldseek_version,
                "parameters": parameters,
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
                database_id=resources.pdb_foldseek.database_id,
                tool="foldseek",
                tool_version=foldseek_version,
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
            "database_id": resources.pdb_foldseek.database_id,
            "resource_ids": resource_ids,
            "tool": "foldseek",
            "tool_version": foldseek_version,
            "batch_cache_key": batch_cache_key,
            "query_count": len(sequence_groups),
            "eligible_before_query_cap_count": len(eligible_before_query_cap),
            "eligible_query_count": len(eligible_records),
            "deferred_query_count": len(policy_skipped),
            "hit_count": len(all_hits),
            "status_counts": dict(sorted(status_counts.items())),
            "parameters": parameters,
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
        "ProstT5/Foldseek PDB outputs published",
        extra={
            "query_count": len(results),
            "eligible_before_query_cap_count": len(eligible_before_query_cap),
            "eligible_query_count": len(eligible_records),
            "deferred_query_count": len(policy_skipped),
            "hit_count": len(all_hits),
            "output_directory": str(outdir),
        },
    )
    return ProstT5FoldseekSearchOutput(
        results=tuple(results),
        results_jsonl=results_path,
        hits_jsonl=hits_path,
        search_manifest=manifest_path,
    )
