"""Exact-accession AlphaFold DB retrieval with sequence-verified coordinates."""

import csv
import hashlib
import json
import logging
import math
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import gemmi
from pydantic import JsonValue, ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.databases.cache import (
    publish_afdb_coordinate,
    verify_coordinate_cache,
)
from genome_to_diffraction.ids import (
    canonical_digest,
    canonical_sequence,
    content_id,
    sequence_digest,
)
from genome_to_diffraction.schemas.base import ContractModel
from genome_to_diffraction.schemas.io import (
    ContractLoadError,
    load_contract,
    parse_json_document,
)
from genome_to_diffraction.schemas.manifests import (
    DatabaseManifest,
    DatabaseResource,
    DatabaseResourceStatus,
    SmokeTestStatus,
)
from genome_to_diffraction.schemas.providers import ProviderKey
from genome_to_diffraction.schemas.results import (
    CoordinateSourceRecord,
    EligibilityStatus,
    SearchScientificStatus,
    SequenceGroupRecord,
    SourceProteinRecord,
    StructuralSearchHit,
    StructuralSearchResult,
)
from genome_to_diffraction.status import (
    ExecutionStatus,
    InfrastructureError,
    InputContractError,
    ResultParseError,
)
from genome_to_diffraction.structure_search.provider_plan import (
    load_enabled_provider_route,
)
from genome_to_diffraction.time import utc_now, utc_now_iso

_LOGGER = logging.getLogger("genome_to_diffraction.structure_search.afdb_exact")
_ADAPTER_VERSION = "afdb-exact-v2"
_PROVIDER = "afdb_exact"
_TOOL = "AlphaFold DB prediction API"
_TOOL_VERSION = "2026-06-field-contract"
_DATABASE_ID = "afdb_prediction_api_2026_06"
_METADATA_URL = "https://alphafold.ebi.ac.uk/api/prediction/{accession}"
_LICENSE = "AlphaFold DB CC-BY-4.0"
_USER_AGENT = "nf-genome-to-diffraction/0.1"
_MAX_METADATA_BYTES = 10 * 1024 * 1024
_MAX_COORDINATE_BYTES = 100 * 1024 * 1024
_UNIPROT_ACCESSION = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|"
    r"[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})"
    r"(?:-[1-9][0-9]*)?$"
)
_ALLOWED_DOWNLOAD_HOSTS = frozenset(
    {
        "alphafold.ebi.ac.uk",
        "www.alphafold.ebi.ac.uk",
        "alphafold.com",
        "www.alphafold.com",
        "ftp.ebi.ac.uk",
    }
)


@dataclass(frozen=True)
class AfdbExactRequest:
    """Inputs and bounded HTTP policy for exact AFDB retrieval."""

    sequence_groups_jsonl: Path
    source_records_jsonl: Path
    database_manifest: Path
    output_directory: Path
    provider_plan_json: Path | None = None
    provider_entry_json: Path | None = None
    accession_map_tsv: Path | None = None
    request_timeout_seconds: float = 60.0
    retry_count: int = 3
    progress: bool = True


@dataclass(frozen=True)
class AfdbExactOutput:
    """Published exact-search records and cached coordinate provenance."""

    results: tuple[StructuralSearchResult, ...]
    coordinate_sources: tuple[CoordinateSourceRecord, ...]
    results_jsonl: Path
    hits_jsonl: Path
    coordinate_sources_jsonl: Path
    search_manifest: Path


@dataclass(frozen=True)
class _HttpResponse:
    requested_url: str
    url: str
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class _AfdbCandidate:
    accession: str
    model_entity_id: str
    sequence: str
    latest_version: int
    cif_url: str
    global_metric_value: float | None
    provider_id: str | None
    reviewed: bool
    reference_proteome: bool
    raw_response_pointer: str
    raw_response_sha256: str


@dataclass(frozen=True)
class _GroupOutcome:
    sequence_group: SequenceGroupRecord
    accessions: tuple[str, ...]
    hit: StructuralSearchHit | None
    execution_status: ExecutionStatus
    scientific_status: SearchScientificStatus
    warnings: tuple[str, ...]


def _bind_provider_route(request: AfdbExactRequest) -> AfdbExactRequest:
    if request.provider_plan_json is None and request.provider_entry_json is None:
        return request
    if request.provider_plan_json is None or request.provider_entry_json is None:
        raise InputContractError(
            "AFDB exact search requires both provider plan and provider entry"
        )
    load_enabled_provider_route(
        provider_plan_json=request.provider_plan_json,
        provider_entry_json=request.provider_entry_json,
        database_manifest=request.database_manifest,
        expected_provider=ProviderKey.AFDB_EXACT,
        expected_adapter_version=_ADAPTER_VERSION,
    )
    return request


def _validate_request(request: AfdbExactRequest) -> None:
    if (
        not math.isfinite(request.request_timeout_seconds)
        or request.request_timeout_seconds <= 0
        or request.request_timeout_seconds > 600
    ):
        raise ValueError("request_timeout_seconds must be in (0, 600]")
    if request.retry_count < 1 or request.retry_count > 5:
        raise ValueError("retry_count must be between 1 and 5")


def _load_jsonl_records[T: ContractModel](
    path: Path, model: type[T], *, label: str, progress: bool
) -> tuple[T, ...]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise InputContractError(f"{label} input is not a file: {resolved}")
    records: list[T] = []
    with resolved.open(encoding="utf-8") as handle:
        iterator = tqdm(
            enumerate(handle, start=1),
            desc=f"Validate {label}",
            unit="record",
            disable=not progress,
        )
        for line_number, line in iterator:
            if not line.strip():
                raise InputContractError(
                    f"blank {label} record at line {line_number}: {resolved}"
                )
            try:
                records.append(model.model_validate_json(line))
            except (ValidationError, TypeError, ValueError) as error:
                raise InputContractError(
                    f"invalid {label} record at line {line_number}: {resolved}"
                ) from error
    if not records:
        raise InputContractError(f"{label} input is empty: {resolved}")
    return tuple(records)


def _normalise_accession(identifier: str) -> str | None:
    token = identifier.strip()
    parts = token.split("|")
    if len(parts) >= 2 and parts[0].casefold() in {"sp", "tr"}:
        token = parts[1]
    token = token.upper()
    return token if _UNIPROT_ACCESSION.fullmatch(token) is not None else None


def _load_accession_map(
    path: Path | None,
    *,
    source_records: dict[str, SourceProteinRecord],
) -> dict[str, str]:
    if path is None:
        return {}
    resolved = path.resolve(strict=True)
    mappings: dict[str, str] = {}
    with resolved.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != ["source_record_id", "uniprot_accession"]:
            raise InputContractError(
                "AFDB accession map headers must be exactly "
                "source_record_id and uniprot_accession"
            )
        for line_number, row in enumerate(reader, start=2):
            source_record_id = row["source_record_id"].strip()
            accession = _normalise_accession(row["uniprot_accession"])
            if source_record_id not in source_records:
                raise InputContractError(
                    f"unknown source_record_id in AFDB map at line {line_number}"
                )
            if accession is None:
                raise InputContractError(
                    f"invalid UniProt accession in AFDB map at line {line_number}"
                )
            if source_record_id in mappings:
                raise InputContractError(
                    f"duplicate source_record_id in AFDB map: {source_record_id}"
                )
            mappings[source_record_id] = accession
    return mappings


def _candidate_accessions(
    groups: tuple[SequenceGroupRecord, ...],
    source_records: tuple[SourceProteinRecord, ...],
    explicit: dict[str, str],
) -> dict[str, tuple[str, ...]]:
    group_ids = {group.sequence_group_id for group in groups}
    by_group: dict[str, set[str]] = {group_id: set() for group_id in group_ids}
    source_ids: set[str] = set()
    for source in source_records:
        if source.source_record_id in source_ids:
            raise InputContractError(
                f"duplicate source_record_id: {source.source_record_id}"
            )
        source_ids.add(source.source_record_id)
        if source.sequence_group_id not in group_ids:
            raise InputContractError(
                "source record refers to an unknown sequence group: "
                f"{source.sequence_group_id}"
            )
        accession = explicit.get(source.source_record_id)
        if accession is None:
            accession = _normalise_accession(source.original_protein_id)
        if accession is not None:
            by_group[source.sequence_group_id].add(accession)
    accession_groups: dict[str, str] = {}
    for group_id, accessions in by_group.items():
        for accession in accessions:
            previous = accession_groups.setdefault(accession, group_id)
            if previous != group_id:
                raise InputContractError(
                    "one UniProt accession maps to more than one exact sequence group: "
                    f"{accession}"
                )
    return {key: tuple(sorted(value)) for key, value in by_group.items()}


def _coordinate_cache_resource(manifest_path: Path) -> DatabaseResource:
    manifest = load_contract(manifest_path, "database-manifest", progress=False)
    if not isinstance(manifest, DatabaseManifest):
        raise AssertionError("database-manifest loader returned an unexpected model")
    matches = tuple(
        resource
        for resource in manifest.resources
        if resource.name == "coordinate_cache"
    )
    if len(matches) != 1:
        raise InputContractError(
            "database manifest must contain exactly one coordinate_cache resource"
        )
    resource = matches[0]
    if (
        resource.status is not DatabaseResourceStatus.READY
        or resource.smoke_test_status is not SmokeTestStatus.PASSED
    ):
        raise InputContractError("coordinate_cache resource is not qualified")
    verify_coordinate_cache(Path(resource.root_path).resolve(strict=True))
    return resource


def _safe_download_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in _ALLOWED_DOWNLOAD_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or not parsed.path.startswith("/")
        or parsed.fragment
    ):
        raise ResultParseError(f"unsafe AFDB download URL: {url!r}")
    return url


def _selected_headers(headers: Any) -> dict[str, str]:
    selected: dict[str, str] = {}
    for name in ("Content-Type", "ETag", "Last-Modified"):
        value = headers.get(name)
        if value:
            selected[name.casefold()] = str(value)
    return selected


def _http_get(
    url: str,
    *,
    accept: str,
    timeout_seconds: float,
    retry_count: int,
    maximum_bytes: int,
) -> _HttpResponse:
    request = urllib.request.Request(
        url,
        headers={"Accept": accept, "User-Agent": _USER_AGENT},
        method="GET",
    )
    for attempt in range(1, retry_count + 1):
        _LOGGER.info(
            "AFDB request started",
            extra={"url": url, "attempt": attempt, "maximum_attempts": retry_count},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = response.read(maximum_bytes + 1)
                if len(body) > maximum_bytes:
                    raise InfrastructureError(
                        f"AFDB response exceeds {maximum_bytes} bytes: {url}"
                    )
                result = _HttpResponse(
                    requested_url=url,
                    url=response.geturl(),
                    status=response.status,
                    headers=_selected_headers(response.headers),
                    body=body,
                )
                _LOGGER.info(
                    "AFDB request completed",
                    extra={
                        "url": url,
                        "response_url": result.url,
                        "status": result.status,
                        "size_bytes": len(body),
                    },
                )
                return result
        except urllib.error.HTTPError as error:
            if error.code == 404:
                body = error.read(maximum_bytes + 1)
                if len(body) > maximum_bytes:
                    raise InfrastructureError(
                        f"AFDB response exceeds {maximum_bytes} bytes: {url}"
                    ) from error
                return _HttpResponse(
                    requested_url=url,
                    url=error.url,
                    status=404,
                    headers=_selected_headers(error.headers),
                    body=body,
                )
            if error.code < 500 or attempt == retry_count:
                raise InfrastructureError(
                    f"AFDB request failed with HTTP {error.code}: {url}"
                ) from error
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            if attempt == retry_count:
                raise InfrastructureError(
                    f"AFDB request failed: {url}: {error}"
                ) from error
        if attempt < retry_count:
            time.sleep(min(2 ** (attempt - 1), 4))
    raise AssertionError("AFDB retry loop ended without a result")


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ResultParseError(f"AFDB metadata lacks valid {key}")
    return value


def _parse_metadata(
    body: bytes,
    *,
    accession: str,
    raw_response_pointer: str,
    raw_response_sha256: str,
) -> tuple[tuple[_AfdbCandidate, ...], tuple[dict[str, JsonValue], ...]]:
    try:
        payload = parse_json_document(body.decode("utf-8"), label="AFDB metadata")
    except (UnicodeDecodeError, ContractLoadError) as error:
        raise ResultParseError(
            f"AFDB metadata response is not valid strict JSON: {error}"
        ) from error
    if not isinstance(payload, list):
        raise ResultParseError("AFDB metadata response must be a JSON array")
    candidates: list[_AfdbCandidate] = []
    rejections: list[dict[str, JsonValue]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ResultParseError(f"AFDB metadata record {index} is not an object")
        model_entity_id = _required_text(item, "modelEntityId")
        source_sequence = _required_text(item, "sequence")
        response_accession = _required_text(item, "uniprotAccession").upper()
        try:
            sequence = canonical_sequence(source_sequence)
        except ValueError as error:
            raise ResultParseError(
                f"AFDB metadata contains an invalid sequence for {model_entity_id}"
            ) from error
        start = item.get("sequenceStart")
        end = item.get("sequenceEnd")
        version = item.get("latestVersion")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not isinstance(version, int)
            or isinstance(version, bool)
            or version < 1
        ):
            raise ResultParseError(
                f"AFDB metadata has invalid sequence span/version for {model_entity_id}"
            )
        rejection_reason: str | None = None
        if response_accession != accession:
            rejection_reason = "response accession differs from requested accession"
        elif item.get("isComplex") is not False:
            rejection_reason = "complex model is outside the single-component provider"
        elif str(item.get("entityType", "")).casefold() != "protein":
            rejection_reason = "entity is not a protein"
        elif start != 1 or end != len(sequence):
            rejection_reason = "model is a fragment rather than a full-sequence model"
        if rejection_reason is not None:
            rejections.append(
                {
                    "accession": accession,
                    "model_entity_id": model_entity_id,
                    "reason": rejection_reason,
                    "source_sequence_sha256": sequence_digest(sequence),
                }
            )
            continue
        cif_url = _safe_download_url(_required_text(item, "cifUrl"))
        metric_raw = item.get("globalMetricValue")
        metric: float | None
        if metric_raw is None:
            metric = None
        elif isinstance(metric_raw, int | float) and not isinstance(metric_raw, bool):
            metric = float(metric_raw)
            if not math.isfinite(metric) or not 0 <= metric <= 100:
                raise ResultParseError(
                    f"AFDB global metric is out of range for {model_entity_id}"
                )
        else:
            raise ResultParseError(
                f"AFDB global metric is invalid for {model_entity_id}"
            )
        provider_id = item.get("providerId")
        if provider_id is not None and not isinstance(provider_id, str):
            raise ResultParseError(
                f"AFDB provider identifier is invalid for {model_entity_id}"
            )
        candidates.append(
            _AfdbCandidate(
                accession=accession,
                model_entity_id=model_entity_id,
                sequence=sequence,
                latest_version=version,
                cif_url=cif_url,
                global_metric_value=metric,
                provider_id=provider_id,
                reviewed=item.get("isUniProtReviewed") is True,
                reference_proteome=item.get("isUniProtReferenceProteome") is True,
                raw_response_pointer=raw_response_pointer,
                raw_response_sha256=raw_response_sha256,
            )
        )
    return tuple(candidates), tuple(rejections)


def _coordinate_sequence(path: Path) -> str:
    try:
        structure = gemmi.read_structure(str(path))
        structure.setup_entities()
    except (RuntimeError, ValueError) as error:
        raise ResultParseError(
            f"AFDB coordinate file is not parseable: {path}"
        ) from error
    sequences = {
        sequence
        for model in structure
        for chain in model
        if (sequence := chain.get_polymer().make_one_letter_sequence())
    }
    if len(sequences) != 1:
        raise ResultParseError(
            "AFDB monomer coordinate file must contain one unique polymer sequence"
        )
    return canonical_sequence(sequences.pop())


def _event(response: _HttpResponse, *, kind: str) -> dict[str, JsonValue]:
    return {
        "kind": kind,
        "requested_url": response.requested_url,
        "response_url": response.url,
        "status": response.status,
        "size_bytes": len(response.body),
        "etag": response.headers.get("etag"),
        "last_modified": response.headers.get("last-modified"),
        "content_type": response.headers.get("content-type"),
        "response_sha256": hashlib.sha256(response.body).hexdigest(),
    }


def _jsonl(records: tuple[Any, ...] | list[Any]) -> str:
    return "".join(
        json.dumps(
            record.model_dump(mode="json") if hasattr(record, "model_dump") else record,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
        for record in records
    )


def search_afdb_exact(request: AfdbExactRequest) -> AfdbExactOutput:
    """Retrieve at most one sequence-exact AFDB monomer per sequence group."""

    request = _bind_provider_route(request)
    _validate_request(request)
    groups = _load_jsonl_records(
        request.sequence_groups_jsonl,
        SequenceGroupRecord,
        label="sequence-group",
        progress=request.progress,
    )
    source_records = _load_jsonl_records(
        request.source_records_jsonl,
        SourceProteinRecord,
        label="source-protein",
        progress=request.progress,
    )
    typed_groups = tuple(groups)
    typed_sources = tuple(source_records)
    source_by_id = {source.source_record_id: source for source in typed_sources}
    if len(source_by_id) != len(typed_sources):
        raise InputContractError("source-protein input contains duplicate identifiers")
    explicit = _load_accession_map(
        request.accession_map_tsv, source_records=source_by_id
    )
    accessions_by_group = _candidate_accessions(typed_groups, typed_sources, explicit)
    cache_resource = _coordinate_cache_resource(request.database_manifest)
    cache_root = Path(cache_resource.root_path).resolve(strict=True)

    outdir = request.output_directory.resolve()
    if outdir.exists() and any(outdir.iterdir()):
        raise ValueError(f"structural-search output directory is not empty: {outdir}")
    raw_directory = outdir / "raw"
    api_directory = raw_directory / "api"
    model_directory = raw_directory / "models"
    api_directory.mkdir(parents=True, exist_ok=True)
    model_directory.mkdir(parents=True, exist_ok=True)

    http_events: list[dict[str, JsonValue]] = []
    query_summaries: list[dict[str, JsonValue]] = []
    outcomes: list[_GroupOutcome] = []
    all_hits: list[StructuralSearchHit] = []
    coordinate_sources: list[CoordinateSourceRecord] = []
    iterator = tqdm(
        typed_groups,
        desc="Retrieve exact AFDB models",
        unit="sequence",
        disable=not request.progress,
    )
    for group in iterator:
        accessions = accessions_by_group[group.sequence_group_id]
        raw_api_responses: list[JsonValue] = []
        candidates: list[_AfdbCandidate] = []
        rejections: list[JsonValue] = []
        for accession in accessions:
            metadata_url = _METADATA_URL.format(accession=quote(accession, safe="-"))
            response = _http_get(
                metadata_url,
                accept="application/json",
                timeout_seconds=request.request_timeout_seconds,
                retry_count=request.retry_count,
                maximum_bytes=_MAX_METADATA_BYTES,
            )
            http_events.append(_event(response, kind="metadata"))
            _safe_download_url(response.url)
            if response.status == 404:
                rejections.append(
                    {"accession": accession, "reason": "AFDB accession not found"}
                )
                continue
            response_pointer = f"raw/api/{accession}.json"
            response_path = outdir / response_pointer
            atomic_write_bytes(response_path, response.body)
            response_sha256 = sha256_file(response_path, progress=False)
            raw_api_responses.append(
                {"path": response_pointer, "sha256": response_sha256}
            )
            parsed, rejected = _parse_metadata(
                response.body,
                accession=accession,
                raw_response_pointer=response_pointer,
                raw_response_sha256=response_sha256,
            )
            candidates.extend(parsed)
            rejections.extend(rejected)

        exact_candidates = [
            candidate
            for candidate in candidates
            if sequence_digest(candidate.sequence) == group.sha256
        ]
        for candidate in candidates:
            if sequence_digest(candidate.sequence) != group.sha256:
                rejections.append(
                    {
                        "accession": candidate.accession,
                        "model_entity_id": candidate.model_entity_id,
                        "reason": "AFDB source sequence is not exact",
                        "source_sequence_sha256": sequence_digest(candidate.sequence),
                    }
                )
        exact_candidates.sort(
            key=lambda candidate: (
                candidate.provider_id != "GDM",
                not candidate.reviewed,
                not candidate.reference_proteome,
                candidate.accession,
                candidate.model_entity_id,
                -candidate.latest_version,
            )
        )

        hit: StructuralSearchHit | None = None
        warnings: list[str] = []
        selected_summary: dict[str, JsonValue] | None = None
        if exact_candidates:
            selected = exact_candidates[0]
            if len(exact_candidates) > 1:
                warnings.append(
                    "multiple exact AFDB models were available; selected one by the "
                    "documented deterministic provider/review/accession order"
                )
            coordinate_response = _http_get(
                selected.cif_url,
                accept="chemical/x-mmcif,text/plain",
                timeout_seconds=request.request_timeout_seconds,
                retry_count=request.retry_count,
                maximum_bytes=_MAX_COORDINATE_BYTES,
            )
            if coordinate_response.status != 200:
                raise InfrastructureError(
                    f"AFDB coordinate returned HTTP {coordinate_response.status}"
                )
            _safe_download_url(coordinate_response.url)
            http_events.append(_event(coordinate_response, kind="coordinate"))
            temporary_model = model_directory / f"{selected.model_entity_id}.cif"
            atomic_write_bytes(temporary_model, coordinate_response.body)
            coordinate_sequence = _coordinate_sequence(temporary_model)
            coordinate_sequence_sha256 = sequence_digest(coordinate_sequence)
            if (
                coordinate_sequence_sha256 != group.sha256
                or coordinate_sequence_sha256 != sequence_digest(selected.sequence)
            ):
                raise ResultParseError(
                    "AFDB coordinate sequence differs from API and catalogue sequence: "
                    f"{selected.model_entity_id}"
                )
            retrieval_date = utc_now()
            retrieved_at = retrieval_date.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            )
            confidence_summary: dict[str, JsonValue] = {
                "metric": "mean_plddt",
                "value": selected.global_metric_value,
            }
            cached = publish_afdb_coordinate(
                cache_root,
                temporary_model,
                model_entity_id=selected.model_entity_id,
                accession=selected.accession,
                requested_url=coordinate_response.requested_url,
                source_url=coordinate_response.url,
                retrieved_at=retrieved_at,
                source_release=f"model-version-{selected.latest_version}",
                source_sequence_sha256=group.sha256,
                confidence_summary=confidence_summary,
                etag=coordinate_response.headers.get("etag"),
                last_modified=coordinate_response.headers.get("last-modified"),
                content_type=coordinate_response.headers.get("content-type"),
                progress=request.progress,
            )
            temporary_model.unlink()
            model_key = f"afdb:{selected.model_entity_id}:v{selected.latest_version}"
            raw_metrics: dict[str, JsonValue] = {
                "accession": selected.accession,
                "model_entity_id": selected.model_entity_id,
                "latest_version": selected.latest_version,
                "global_metric_name": "mean_plddt",
                "global_metric_value": selected.global_metric_value,
                "provider_id": selected.provider_id,
                "is_uniprot_reviewed": selected.reviewed,
                "is_uniprot_reference_proteome": selected.reference_proteome,
                "coordinate_sha256": cached.object_sha256,
                "coordinate_metadata_sha256": cached.metadata_sha256,
                "coordinate_metadata_path": cached.metadata_relative_path,
                "metadata_response_sha256": selected.raw_response_sha256,
            }
            hit = StructuralSearchHit(
                schema_version="1.0",
                hit_id=content_id(
                    "hit_",
                    {
                        "provider": _PROVIDER,
                        "sequence_group_id": group.sequence_group_id,
                        "model_key": model_key,
                        "coordinate_sha256": cached.object_sha256,
                    },
                ),
                sequence_group_id=group.sequence_group_id,
                provider=_PROVIDER,
                provider_rank=1,
                target_id=selected.model_entity_id,
                model_key=model_key,
                target_chain_or_entity=selected.model_entity_id,
                identifier_namespace="alphafold_db_model_entity",
                query_start=1,
                query_end=group.length_aa,
                target_start=1,
                target_end=group.length_aa,
                aligned_length=group.length_aa,
                query_coverage=1.0,
                target_coverage=1.0,
                sequence_identity=1.0,
                database_id=_DATABASE_ID,
                raw_result_pointer=selected.raw_response_pointer,
                raw_metrics=raw_metrics,
                eligibility_status=EligibilityStatus.SELECTED,
                eligibility_reason=(
                    "nominal UniProt mapping, API sequence, and coordinate polymer "
                    "all match the catalogue sequence digest exactly"
                ),
            )
            coordinate_source = CoordinateSourceRecord(
                schema_version="1.0",
                coordinate_id=content_id(
                    "coord_",
                    {
                        "provider": "afdb",
                        "model_entity_id": selected.model_entity_id,
                        "model_version": selected.latest_version,
                        "coordinate_sha256": cached.object_sha256,
                    },
                ),
                provider="afdb",
                provider_accession=selected.accession,
                retrieval_date=retrieval_date,
                source_release=f"model-version-{selected.latest_version}",
                coordinate_path=str(cache_root / cached.object_relative_path),
                coordinate_sha256=cached.object_sha256,
                source_sequence_sha256=group.sha256,
                confidence_summary=confidence_summary,
                license_or_provenance=_LICENSE,
            )
            all_hits.append(hit)
            coordinate_sources.append(coordinate_source)
            execution_status = ExecutionStatus.COMPLETED_HIT
            scientific_status = SearchScientificStatus.HITS_FOUND
            selected_summary = {
                "accession": selected.accession,
                "model_entity_id": selected.model_entity_id,
                "model_version": selected.latest_version,
                "coordinate_sha256": cached.object_sha256,
            }
        elif not accessions:
            execution_status = ExecutionStatus.SKIPPED_INELIGIBLE
            scientific_status = SearchScientificStatus.NOT_INTERPRETABLE
            warnings.append(
                "no strict UniProt accession or explicit accession mapping is available"
            )
        else:
            execution_status = ExecutionStatus.COMPLETED_NO_HIT
            scientific_status = SearchScientificStatus.NO_HIT
            if candidates:
                warnings.append(
                    "AFDB returned metadata, but no model sequence matched the "
                    "catalogue sequence digest exactly"
                )

        raw_summary: dict[str, JsonValue] = {
            "schema_version": "1.0",
            "provider": _PROVIDER,
            "sequence_group_id": group.sequence_group_id,
            "sequence_sha256": group.sha256,
            "candidate_accessions": list(accessions),
            "api_responses": raw_api_responses,
            "selected": selected_summary,
            "rejections": rejections,
        }
        query_summaries.append(raw_summary)
        outcomes.append(
            _GroupOutcome(
                sequence_group=group,
                accessions=accessions,
                hit=hit,
                execution_status=execution_status,
                scientific_status=scientific_status,
                warnings=tuple(warnings),
            )
        )

    raw_results_path = raw_directory / "afdb-query-results.jsonl"
    atomic_write_text(raw_results_path, _jsonl(query_summaries))
    raw_results_sha256 = sha256_file(raw_results_path, progress=False)
    log_path = raw_directory / "http.log"
    atomic_write_text(log_path, _jsonl(http_events))
    log_sha256 = sha256_file(log_path, progress=False)
    results: list[StructuralSearchResult] = []
    mapping_digest = (
        sha256_file(request.accession_map_tsv, progress=False)
        if request.accession_map_tsv is not None
        else None
    )
    parameters = {
        "provider_plan_sha256": (
            None
            if request.provider_plan_json is None
            else sha256_file(request.provider_plan_json, progress=False)
        ),
        "provider_entry_sha256": (
            None
            if request.provider_entry_json is None
            else sha256_file(request.provider_entry_json, progress=False)
        ),
        "metadata_endpoint": _METADATA_URL,
        "metadata_contract": _TOOL_VERSION,
        "maximum_models_per_sequence_group": 1,
        "require_exact_api_sequence": True,
        "require_exact_coordinate_sequence": True,
        "allow_complex_models": False,
    }
    for outcome in outcomes:
        cache_key = canonical_digest(
            {
                "adapter_version": _ADAPTER_VERSION,
                "coordinate_cache_database_id": cache_resource.database_id,
                "provider_database_id": _DATABASE_ID,
                "sequence_sha256": outcome.sequence_group.sha256,
                "accessions": outcome.accessions,
                "accession_map_sha256": mapping_digest,
                "parameters": parameters,
            }
        )
        hits = (outcome.hit,) if outcome.hit is not None else ()
        results.append(
            StructuralSearchResult(
                schema_version="1.0",
                search_id=content_id(
                    "srch_",
                    {
                        "cache_key": cache_key,
                        "provider": _PROVIDER,
                        "sequence_group_id": outcome.sequence_group.sequence_group_id,
                    },
                ),
                sequence_group_id=outcome.sequence_group.sequence_group_id,
                provider=_PROVIDER,
                database_id=_DATABASE_ID,
                tool=_TOOL,
                tool_version=_TOOL_VERSION,
                adapter_version=_ADAPTER_VERSION,
                cache_key=cache_key,
                execution_status=outcome.execution_status,
                scientific_status=outcome.scientific_status,
                hit_count=len(hits),
                hits=hits,
                raw_result_pointer="raw/afdb-query-results.jsonl",
                raw_result_sha256=raw_results_sha256,
                command_log_pointer="raw/http.log",
                command_log_sha256=log_sha256,
                warnings=outcome.warnings,
            )
        )

    results_path = outdir / "search_results.jsonl"
    hits_path = outdir / "structural_hits.jsonl"
    coordinate_sources_path = outdir / "coordinate_sources.jsonl"
    atomic_write_text(results_path, _jsonl(results))
    atomic_write_text(hits_path, _jsonl(all_hits))
    atomic_write_text(coordinate_sources_path, _jsonl(coordinate_sources))
    manifest_path = outdir / "search_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "provider": _PROVIDER,
        "adapter_version": _ADAPTER_VERSION,
        "tool": _TOOL,
        "tool_version": _TOOL_VERSION,
        "database_id": _DATABASE_ID,
        "coordinate_cache_database_id": cache_resource.database_id,
        "created_at": utc_now_iso(),
        "query_count": len(results),
        "eligible_query_count": sum(bool(item.accessions) for item in outcomes),
        "hit_count": len(all_hits),
        "coordinate_source_count": len(coordinate_sources),
        "parameters": parameters,
        "inputs": {
            "sequence_groups_sha256": sha256_file(
                request.sequence_groups_jsonl, progress=False
            ),
            "source_records_sha256": sha256_file(
                request.source_records_jsonl, progress=False
            ),
            "accession_map_sha256": mapping_digest,
        },
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
                "path": coordinate_sources_path.name,
                "sha256": sha256_file(coordinate_sources_path, progress=False),
            },
            "http_log": {"path": "raw/http.log", "sha256": log_sha256},
            "raw_query_results": {
                "path": "raw/afdb-query-results.jsonl",
                "sha256": raw_results_sha256,
            },
        },
    }
    atomic_write_json(manifest_path, manifest)
    _LOGGER.info(
        "exact AFDB retrieval completed",
        extra={
            "query_count": len(results),
            "eligible_query_count": manifest["eligible_query_count"],
            "hit_count": len(all_hits),
            "manifest": str(manifest_path),
        },
    )
    return AfdbExactOutput(
        results=tuple(results),
        coordinate_sources=tuple(coordinate_sources),
        results_jsonl=results_path,
        hits_jsonl=hits_path,
        coordinate_sources_jsonl=coordinate_sources_path,
        search_manifest=manifest_path,
    )
