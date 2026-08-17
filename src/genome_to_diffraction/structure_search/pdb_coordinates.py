"""Register selected direct-search PDB coordinates with immutable mappings.

The adapter reads normalised direct-PDB hits, reserves sequence-group diversity
before taking additional homologues, retrieves each selected PDB entry at most
once, and publishes the verified mmCIF bytes through the shared content-addressed
coordinate cache.  It validates the exact SEQRES entity/author-chain token and
retains a typed hit-to-coordinate alignment record.  It does not prepare an MR
model or treat an external PDB sequence as a catalogue identity.
"""

import gzip
import logging
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import gemmi
from pydantic import ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.databases.cache import (
    CachedCoordinate,
    find_cached_pdb_coordinates,
    publish_pdb_coordinate,
    verify_coordinate_cache,
)
from genome_to_diffraction.databases.network import (
    DownloadMetadata,
    download_public_resource,
)
from genome_to_diffraction.ids import canonical_json_text, content_id, sequence_digest
from genome_to_diffraction.schemas.base import ContractModel
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    DatabaseManifest,
    DatabaseResource,
    DatabaseResourceStatus,
    SmokeTestStatus,
)
from genome_to_diffraction.schemas.results import (
    CoordinateHitMappingRecord,
    CoordinateSourceRecord,
    EligibilityStatus,
    SequenceGroupRecord,
    StructuralSearchHit,
)
from genome_to_diffraction.status import InputContractError, ResultParseError
from genome_to_diffraction.time import utc_now_iso

_LOGGER = logging.getLogger("genome_to_diffraction.structure_search.pdb_coordinates")
_ADAPTER_VERSION = "pdb-coordinate-registration-v1"
_PDB_COORDINATE_URL = "https://files.rcsb.org/download/{pdb_id}.cif.gz"
_DIRECT_PROVIDER = "pdb_sequence_mmseqs"
_PROSTT5_PROVIDER = "foldseek_prostt5_pdb"
_PROVIDERS = frozenset({_DIRECT_PROVIDER, _PROSTT5_PROVIDER})
_PROTEIN_ALPHABET = frozenset("ABCDEFGHIKLMNPQRSTVWXYZOUJ")


class PdbCoordinateInputError(InputContractError):
    """PDB hits or database resources cannot be joined without ambiguity."""


class PdbCoordinateParseError(ResultParseError):
    """A downloaded PDB entry does not match the selected search target."""


@dataclass(frozen=True)
class PdbCoordinateRegistrationRequest:
    """Inputs and hard bounds for direct-PDB coordinate registration."""

    structural_hits_jsonl: Path
    sequence_groups_jsonl: Path
    database_manifest: Path
    output_directory: Path
    maximum_hits_per_sequence_group: int = 3
    maximum_mappings: int = 25
    hit_ids: tuple[str, ...] = ()
    storage_limit_bytes: int = 100_000_000_000
    minimum_free_bytes: int = 1_000_000_000
    progress: bool = True


@dataclass(frozen=True)
class PdbCoordinateRegistrationOutput:
    """Published source, alignment-mapping, and integrity-manifest files."""

    coordinate_sources: tuple[CoordinateSourceRecord, ...]
    mappings: tuple[CoordinateHitMappingRecord, ...]
    coordinate_sources_jsonl: Path
    mappings_jsonl: Path
    manifest_json: Path


@dataclass(frozen=True)
class _PdbEntity:
    entry_id: str
    entity_id: str
    seqres_token: str
    label_asym_ids: tuple[str, ...]
    polymer_type: str
    sequence: str
    sequence_sha256: str


def _read_jsonl[T: ContractModel](
    path: Path,
    model: type[T],
    *,
    label: str,
    identifier: Callable[[T], str],
    progress: bool,
) -> tuple[T, ...]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise PdbCoordinateInputError(f"{label} input is not a file: {resolved}")
    records: list[T] = []
    seen: set[str] = set()
    with resolved.open(encoding="utf-8") as handle:
        iterator = tqdm(
            enumerate(handle, start=1),
            desc=f"Validate {label}",
            unit="record",
            disable=not progress,
        )
        for line_number, line in iterator:
            if not line.strip():
                raise PdbCoordinateInputError(
                    f"blank {label} record at line {line_number}: {resolved}"
                )
            try:
                record = model.model_validate_json(line)
            except (ValidationError, TypeError, ValueError) as error:
                raise PdbCoordinateInputError(
                    f"invalid {label} record at line {line_number}: {resolved}"
                ) from error
            record_id = identifier(record)
            if record_id in seen:
                raise PdbCoordinateInputError(f"duplicate {label} ID: {record_id}")
            seen.add(record_id)
            records.append(record)
    if not records:
        raise PdbCoordinateInputError(f"{label} input is empty: {resolved}")
    return tuple(records)


def _resources(
    manifest_path: Path,
) -> tuple[DatabaseResource, DatabaseResource, DatabaseResource]:
    manifest = load_contract(manifest_path, "database-manifest", progress=False)
    if not isinstance(manifest, DatabaseManifest):
        raise AssertionError("database-manifest loader returned an unexpected model")

    def exactly_one(name: str) -> DatabaseResource:
        matches = tuple(item for item in manifest.resources if item.name == name)
        if len(matches) != 1:
            raise PdbCoordinateInputError(
                f"database manifest must contain exactly one {name} resource"
            )
        resource = matches[0]
        if (
            resource.status is not DatabaseResourceStatus.READY
            or resource.smoke_test_status is not SmokeTestStatus.PASSED
        ):
            raise PdbCoordinateInputError(f"{name} resource is not qualified")
        return resource

    sequences = exactly_one("pdb_sequences")
    foldseek = exactly_one("pdb_foldseek")
    cache = exactly_one("coordinate_cache")
    verify_coordinate_cache(Path(cache.root_path).resolve(strict=True))
    return sequences, foldseek, cache


def _required_metric[T](hit: StructuralSearchHit, name: str, expected: type[T]) -> T:
    value = hit.raw_metrics.get(name)
    if not isinstance(value, expected) or isinstance(value, bool):
        raise PdbCoordinateInputError(
            f"direct-PDB hit lacks typed {name}; rerun pdb-sequence adapter v2: "
            f"{hit.hit_id}"
        )
    return value


def _validate_hit(
    hit: StructuralSearchHit, groups: dict[str, SequenceGroupRecord]
) -> None:
    if (
        hit.provider not in _PROVIDERS
        or hit.eligibility_status is not EligibilityStatus.SELECTED
    ):
        raise PdbCoordinateInputError(
            "coordinate registration accepts selected direct-PDB hits only: "
            f"{hit.hit_id}"
        )
    if hit.sequence_group_id not in groups:
        raise PdbCoordinateInputError(
            f"hit references an unknown sequence group: {hit.hit_id}"
        )
    if (
        hit.pdb_id is None
        or hit.identifier_namespace is None
        or hit.target_chain_or_entity is None
        or hit.query_start is None
        or hit.query_end is None
        or hit.target_start is None
        or hit.target_end is None
        or hit.aligned_length is None
        or hit.query_coverage is None
        or hit.target_coverage is None
        or hit.sequence_identity is None
    ):
        raise PdbCoordinateInputError(
            f"direct-PDB hit lacks a complete coordinate mapping: {hit.hit_id}"
        )
    source_length = _required_metric(hit, "target_sequence_length", int)
    source_sha256 = _required_metric(hit, "target_sequence_sha256", str)
    if (
        source_length < 1
        or len(source_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_sha256)
        or hit.target_end > source_length
        or hit.query_end > groups[hit.sequence_group_id].length_aa
    ):
        raise PdbCoordinateInputError(
            f"direct-PDB alignment exceeds its declared sequences: {hit.hit_id}"
        )


def _hit_sort_key(hit: StructuralSearchHit) -> tuple[object, ...]:
    return (
        -(hit.sequence_identity or 0.0),
        -(hit.query_coverage or 0.0),
        hit.evalue if hit.evalue is not None else float("inf"),
        -(hit.bits or 0.0),
        hit.provider_rank,
        hit.sequence_group_id,
        hit.hit_id,
    )


def _select_hits(
    hits: Sequence[StructuralSearchHit], request: PdbCoordinateRegistrationRequest
) -> tuple[StructuralSearchHit, ...]:
    if request.maximum_hits_per_sequence_group < 1:
        raise ValueError("maximum_hits_per_sequence_group must be positive")
    if request.maximum_mappings < 1 or request.maximum_mappings > 1000:
        raise ValueError("maximum_mappings must be between 1 and 1000")
    requested = tuple(request.hit_ids)
    if len(set(requested)) != len(requested):
        raise PdbCoordinateInputError("hit selection contains duplicates")
    by_id = {hit.hit_id: hit for hit in hits}
    unknown = sorted(set(requested) - set(by_id))
    if unknown:
        raise PdbCoordinateInputError(
            "unknown selected hit_id(s): " + ", ".join(unknown)
        )
    candidates = tuple(by_id[item] for item in requested) if requested else tuple(hits)
    grouped: dict[str, list[StructuralSearchHit]] = defaultdict(list)
    for hit in candidates:
        grouped[hit.sequence_group_id].append(hit)
    for group_hits in grouped.values():
        group_hits.sort(key=lambda item: (item.provider_rank, *_hit_sort_key(item)))
        del group_hits[request.maximum_hits_per_sequence_group :]
    selected: list[StructuralSearchHit] = []
    for round_index in range(request.maximum_hits_per_sequence_group):
        diverse_round = sorted(
            (
                group_hits[round_index]
                for group_hits in grouped.values()
                if len(group_hits) > round_index
            ),
            key=_hit_sort_key,
        )
        selected.extend(diverse_round)
        if len(selected) >= request.maximum_mappings:
            break
    return tuple(selected[: request.maximum_mappings])


def _pdb_entity(path: Path, *, hit: StructuralSearchHit) -> _PdbEntity:
    if hit.pdb_id is None or hit.target_chain_or_entity is None:
        raise AssertionError("validated PDB hit lost its coordinate key")
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            block = gemmi.cif.read_string(handle.read()).sole_block()
    except (OSError, RuntimeError, ValueError) as error:
        raise PdbCoordinateParseError(
            f"PDB coordinate is not valid compressed mmCIF: {path}: {error}"
        ) from error
    entry_id = block.find_value("_entry.id")
    if entry_id is None or entry_id.upper() != hit.pdb_id.upper():
        raise PdbCoordinateParseError(
            f"PDB coordinate entry does not match {hit.pdb_id}: {entry_id!r}"
        )
    labels_by_entity: dict[str, list[str]] = defaultdict(list)
    for row in block.find(["_struct_asym.id", "_struct_asym.entity_id"]):
        label, entity_key = (gemmi.cif.as_string(str(value)) for value in row)
        labels_by_entity[entity_key].append(label)
    candidates: list[_PdbEntity] = []
    for row in block.find(
        [
            "_entity_poly.entity_id",
            "_entity_poly.type",
            "_entity_poly.pdbx_strand_id",
            "_entity_poly.pdbx_seq_one_letter_code_can",
        ]
    ):
        entity_id, polymer_type, raw_chains, raw_sequence = (
            gemmi.cif.as_string(str(value)) for value in row
        )
        author_chains = {item.strip() for item in raw_chains.split(",") if item.strip()}
        if hit.target_chain_or_entity not in author_chains:
            continue
        if not polymer_type.casefold().startswith("polypeptide("):
            continue
        sequence = "".join(raw_sequence.split()).upper()
        invalid = sorted(set(sequence) - _PROTEIN_ALPHABET)
        if not sequence or invalid:
            raise PdbCoordinateParseError(
                f"PDB entity has unsupported canonical residues: {hit.hit_id}"
            )
        candidates.append(
            _PdbEntity(
                entry_id=entry_id.upper(),
                entity_id=entity_id,
                seqres_token=hit.target_chain_or_entity,
                label_asym_ids=tuple(sorted(set(labels_by_entity[entity_id]))),
                polymer_type=polymer_type,
                sequence=sequence,
                sequence_sha256=sequence_digest(sequence),
            )
        )
    if len(candidates) != 1 or not candidates[0].label_asym_ids:
        raise PdbCoordinateParseError(
            "PDB author-chain token did not resolve to exactly one protein entity: "
            f"{hit.pdb_id}_{hit.target_chain_or_entity}"
        )
    expected_length = _required_metric(hit, "target_sequence_length", int)
    expected_sha256 = _required_metric(hit, "target_sequence_sha256", str)
    pdb_entity = candidates[0]
    if (
        len(pdb_entity.sequence) != expected_length
        or pdb_entity.sequence_sha256 != expected_sha256
    ):
        raise PdbCoordinateParseError(
            "PDB coordinate entity differs from the searched SEQRES snapshot: "
            f"{hit.hit_id}"
        )
    return pdb_entity


def _download_coordinate(
    cache_root: Path,
    *,
    pdb_id: str,
    storage_limit_bytes: int,
    minimum_free_bytes: int,
    progress: bool,
) -> tuple[CachedCoordinate, Path]:
    temporary = cache_root / "pdb" / "tmp" / f"{pdb_id.lower()}.registration.cif.gz"
    url = _PDB_COORDINATE_URL.format(pdb_id=pdb_id.lower())
    metadata: DownloadMetadata = download_public_resource(
        url,
        temporary,
        storage_root=cache_root,
        storage_limit_bytes=storage_limit_bytes,
        minimum_free_bytes=minimum_free_bytes,
        progress=progress,
    )
    retrieved_at = utc_now_iso()
    cached = publish_pdb_coordinate(
        cache_root,
        temporary,
        pdb_id=pdb_id,
        requested_url=metadata.requested_url,
        source_url=metadata.url,
        retrieved_at=retrieved_at,
        etag=metadata.etag,
        last_modified=metadata.last_modified,
        content_type=metadata.content_type,
        progress=progress,
    )
    return cached, temporary


def _cached_or_downloaded(
    cache_root: Path,
    *,
    hit: StructuralSearchHit,
    request: PdbCoordinateRegistrationRequest,
) -> tuple[CachedCoordinate, _PdbEntity, bool]:
    if hit.pdb_id is None:
        raise AssertionError("validated PDB hit lost its entry ID")
    cached_records = find_cached_pdb_coordinates(
        cache_root,
        pdb_id=hit.pdb_id,
        full_checksum=True,
        progress=request.progress,
    )
    for cached in sorted(
        cached_records,
        key=lambda item: (item.retrieved_at, item.object_sha256),
        reverse=True,
    ):
        try:
            entity = _pdb_entity(cache_root / cached.object_relative_path, hit=hit)
        except PdbCoordinateParseError:
            continue
        _LOGGER.info(
            "reused cached PDB coordinate",
            extra={"pdb_id": hit.pdb_id, "coordinate_sha256": cached.object_sha256},
        )
        return cached, entity, True
    cached, temporary = _download_coordinate(
        cache_root,
        pdb_id=hit.pdb_id,
        storage_limit_bytes=request.storage_limit_bytes,
        minimum_free_bytes=request.minimum_free_bytes,
        progress=request.progress,
    )
    try:
        entity = _pdb_entity(cache_root / cached.object_relative_path, hit=hit)
    finally:
        temporary.unlink(missing_ok=True)
    return cached, entity, False


def register_pdb_coordinates(
    request: PdbCoordinateRegistrationRequest,
) -> PdbCoordinateRegistrationOutput:
    """Register a diversity-reserved, hard-capped set of direct-PDB hits."""

    if request.storage_limit_bytes < 1 or request.minimum_free_bytes < 0:
        raise ValueError("storage bounds must be positive/non-negative")
    groups = _read_jsonl(
        request.sequence_groups_jsonl,
        SequenceGroupRecord,
        label="sequence groups",
        identifier=lambda item: item.sequence_group_id,
        progress=request.progress,
    )
    group_index = {item.sequence_group_id: item for item in groups}
    hits = _read_jsonl(
        request.structural_hits_jsonl,
        StructuralSearchHit,
        label="structural hits",
        identifier=lambda item: item.hit_id,
        progress=request.progress,
    )
    for hit in hits:
        _validate_hit(hit, group_index)
    sequence_resource, foldseek_resource, cache_resource = _resources(
        request.database_manifest
    )
    expected_database_ids = {
        _DIRECT_PROVIDER: sequence_resource.database_id,
        _PROSTT5_PROVIDER: foldseek_resource.database_id,
    }
    if any(hit.database_id != expected_database_ids.get(hit.provider) for hit in hits):
        raise PdbCoordinateInputError(
            "PDB hit database_id differs from its qualified discovery resource"
        )
    selected = _select_hits(hits, request)
    if not selected:
        raise PdbCoordinateInputError("no direct-PDB hits were selected")
    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise PdbCoordinateInputError(
            f"coordinate-registration output directory is not empty: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)
    cache_root = Path(cache_resource.root_path).resolve(strict=True)
    sources: dict[str, CoordinateSourceRecord] = {}
    mappings: list[CoordinateHitMappingRecord] = []
    entry_cache: dict[str, tuple[CachedCoordinate, bool]] = {}
    iterator = tqdm(
        selected,
        desc="Register PDB coordinates",
        unit="mapping",
        disable=not request.progress,
    )
    for hit in iterator:
        if hit.pdb_id is None or hit.identifier_namespace is None:
            raise AssertionError("validated PDB hit lost its coordinate namespace")
        cached_entry = entry_cache.get(hit.pdb_id.upper())
        if cached_entry is None:
            cached, entity, reused = _cached_or_downloaded(
                cache_root, hit=hit, request=request
            )
            entry_cache[hit.pdb_id.upper()] = (cached, reused)
        else:
            cached, reused = cached_entry
            entity = _pdb_entity(cache_root / cached.object_relative_path, hit=hit)
        coordinate_identity = {
            "provider": "pdb",
            "pdb_id": hit.pdb_id.upper(),
            "entity_id": entity.entity_id,
            "seqres_token": entity.seqres_token,
            "coordinate_sha256": cached.object_sha256,
            "source_sequence_sha256": entity.sequence_sha256,
        }
        coordinate_id = content_id("coord_", coordinate_identity)
        retrieved_at = datetime.fromisoformat(
            cached.retrieved_at.replace("Z", "+00:00")
        )
        sources.setdefault(
            coordinate_id,
            CoordinateSourceRecord(
                schema_version="1.0",
                coordinate_id=coordinate_id,
                provider="pdb",
                provider_accession=(
                    f"{hit.pdb_id.upper()}:{entity.entity_id}:{entity.seqres_token}"
                ),
                retrieval_date=retrieved_at,
                source_release=f"retrieved-{retrieved_at.date().isoformat()}",
                coordinate_path=str(cache_root / cached.object_relative_path),
                coordinate_sha256=cached.object_sha256,
                source_sequence_sha256=entity.sequence_sha256,
                confidence_summary={
                    "coordinate_kind": "experimental",
                    "pdb_entry_id": hit.pdb_id.upper(),
                    "entity_id": entity.entity_id,
                    "seqres_token": entity.seqres_token,
                    "label_asym_ids": list(entity.label_asym_ids),
                    "polymer_type": entity.polymer_type,
                },
                license_or_provenance=(
                    "wwPDB public archive; HTTP and checksum provenance retained "
                    "in the coordinate cache"
                ),
            ),
        )
        group = group_index[hit.sequence_group_id]
        query_start = hit.query_start
        query_end = hit.query_end
        target_start = hit.target_start
        target_end = hit.target_end
        aligned_length = hit.aligned_length
        query_coverage = hit.query_coverage
        target_coverage = hit.target_coverage
        sequence_identity = hit.sequence_identity
        if (
            query_start is None
            or query_end is None
            or target_start is None
            or target_end is None
            or aligned_length is None
            or query_coverage is None
            or target_coverage is None
            or sequence_identity is None
        ):
            raise AssertionError("validated PDB hit lost its alignment metrics")
        mapping_identity = {
            "hit_id": hit.hit_id,
            "coordinate_id": coordinate_id,
            "candidate_sequence_sha256": group.sha256,
            "source_sequence_sha256": entity.sequence_sha256,
        }
        mappings.append(
            CoordinateHitMappingRecord(
                schema_version="1.0",
                mapping_id=content_id("coordmap_", mapping_identity),
                hit_id=hit.hit_id,
                coordinate_id=coordinate_id,
                sequence_group_id=group.sequence_group_id,
                candidate_sequence_sha256=group.sha256,
                pdb_id=hit.pdb_id.upper(),
                identifier_namespace=hit.identifier_namespace,
                seqres_token=entity.seqres_token,
                entity_id=entity.entity_id,
                label_asym_ids=entity.label_asym_ids,
                source_sequence_sha256=entity.sequence_sha256,
                source_sequence_length=len(entity.sequence),
                query_start=query_start,
                query_end=query_end,
                target_start=target_start,
                target_end=target_end,
                aligned_length=aligned_length,
                query_coverage=query_coverage,
                target_coverage=target_coverage,
                sequence_identity=sequence_identity,
                exact_sequence_match=(group.sha256 == entity.sequence_sha256),
            )
        )
        _LOGGER.info(
            "PDB hit mapped to cached coordinate",
            extra={
                "hit_id": hit.hit_id,
                "coordinate_id": coordinate_id,
                "pdb_id": hit.pdb_id.upper(),
                "cache_reused": reused,
            },
        )

    source_rows = tuple(sorted(sources.values(), key=lambda item: item.coordinate_id))
    mapping_rows = tuple(mappings)
    sources_path = output / "coordinate_sources.jsonl"
    mappings_path = output / "coordinate_hit_mappings.jsonl"
    atomic_write_text(
        sources_path,
        "".join(f"{canonical_json_text(item)}\n" for item in source_rows),
    )
    atomic_write_text(
        mappings_path,
        "".join(f"{canonical_json_text(item)}\n" for item in mapping_rows),
    )
    input_sha256 = {
        "structural_hits": sha256_file(request.structural_hits_jsonl, progress=False),
        "sequence_groups": sha256_file(request.sequence_groups_jsonl, progress=False),
        "database_manifest": sha256_file(request.database_manifest, progress=False),
    }
    manifest_identity = {
        "adapter_version": _ADAPTER_VERSION,
        "input_sha256": input_sha256,
        "selected_hit_ids": [item.hit_id for item in selected],
        "coordinate_ids": [item.coordinate_id for item in source_rows],
        "mapping_ids": [item.mapping_id for item in mapping_rows],
    }
    manifest_path = output / "registration_manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "registration_id": content_id("coordreg_", manifest_identity),
            "created_at": utc_now_iso(),
            "adapter_version": _ADAPTER_VERSION,
            "scope": "pdb_sequence_and_prostt5_foldseek_hits",
            "source_database_ids": {
                _DIRECT_PROVIDER: sequence_resource.database_id,
                _PROSTT5_PROVIDER: foldseek_resource.database_id,
            },
            "source_database_releases": {
                _DIRECT_PROVIDER: sequence_resource.release_or_snapshot,
                _PROSTT5_PROVIDER: foldseek_resource.release_or_snapshot,
            },
            "coordinate_cache_database_id": cache_resource.database_id,
            "input_sha256": input_sha256,
            "parameters": {
                "maximum_hits_per_sequence_group": (
                    request.maximum_hits_per_sequence_group
                ),
                "maximum_mappings": request.maximum_mappings,
                "explicit_hit_selection": bool(request.hit_ids),
                "selection_policy": "diversity_rounds_then_alignment_quality",
            },
            "input_hit_count": len(hits),
            "selected_mapping_count": len(mapping_rows),
            "coordinate_source_count": len(source_rows),
            "cache_reused_entry_count": sum(
                reused for _, reused in entry_cache.values()
            ),
            "downloaded_entry_count": sum(
                not reused for _, reused in entry_cache.values()
            ),
            "outputs": {
                "coordinate_sources": {
                    "path": sources_path.name,
                    "sha256": sha256_file(sources_path, progress=False),
                },
                "coordinate_hit_mappings": {
                    "path": mappings_path.name,
                    "sha256": sha256_file(mappings_path, progress=False),
                },
            },
        },
    )
    _LOGGER.info(
        "direct-PDB coordinate registration complete",
        extra={
            "input_hit_count": len(hits),
            "selected_mapping_count": len(mapping_rows),
            "coordinate_source_count": len(source_rows),
            "manifest": str(manifest_path),
        },
    )
    return PdbCoordinateRegistrationOutput(
        coordinate_sources=source_rows,
        mappings=mapping_rows,
        coordinate_sources_jsonl=sources_path,
        mappings_jsonl=mappings_path,
        manifest_json=manifest_path,
    )
