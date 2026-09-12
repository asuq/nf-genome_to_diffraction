"""Authenticate the bounded PDB prerequisite for the fixed M6 native control.

Inputs are a complete frozen truthless request snapshot, its authenticated offline
inspection, a fixed-URL gzip bundle, and the unchanged qualified database manifest.
Outputs are a strict content-addressed manifest and a read-only publication plan.
No network, external commands, cache writes or scientific selection runs here.
Python/Gemmi use the pinned project runtime. Every requested mapping is replayed
with the unchanged entity/author-chain/SEQRES parser and cache preference rules.

Unknown bindings, extra files, malformed gzip, resource-limit violations, cache
collisions, stale inspection or incomplete prospective mappings fail before any
publication. A 1 GiB streaming expansion guard precedes the unchanged parser;
expanded coordinate files are never persisted. The caller must publish through
the original per-ID-locked publisher, then authenticate a complete offline
reinspection. This is not a cross-process batch transaction or native acceptance.
Manifest IDs cover all provenance and bounds; no persistent validity cache exists.
Tests cover exact conservation, tampering, unsafe objects, batch collisions,
cross-case compatibility and the first-selected-object/later-hit rule.
"""

import gzip
import re
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.databases.cache import (
    CachedCoordinate,
    find_cached_pdb_coordinates,
    preflight_pdb_coordinate,
)
from genome_to_diffraction.hpc.m6_coordinate_cache import (
    _frozen_file,
    _Inventory,
    inspect_coordinate_cache,
    load_frozen_request_inventory,
)
from genome_to_diffraction.hpc.m6_coordinate_inspection_client import (
    _Report,
    _validate_mappings,
)
from genome_to_diffraction.hpc.m6_coordinate_requests import CASES
from genome_to_diffraction.hpc.models import ValidationError
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.schemas.results import StructuralSearchHit
from genome_to_diffraction.structure_search.pdb_coordinates import (
    PdbCoordinateParseError,
    _pdb_entity,
    _PdbEntity,
    _read_jsonl,
    _resources,
)

MAX_COORDINATE_TOTAL_BYTES = 3 * 1024**3
MAX_COORDINATE_OBJECT_BYTES = 128 * 1024**2
MAX_ADDITIONAL_DISK_BYTES = 12 * 1024**3
MAX_EXPANDED_COORDINATE_BYTES = 1024**3
MAX_PREFETCH_MANIFEST_BYTES = 128 * 1024**2
MAX_PREFETCH_ARCHIVE_BYTES = MAX_COORDINATE_TOTAL_BYTES + 256 * 1024**2
PREFETCH_MANIFEST = "prefetch_manifest.json"


class PrefetchedCoordinate(ContractModel):
    """Exact public retrieval provenance for one compressed PDB entry."""

    relative_path: str
    requested_url: str
    source_url: str
    retrieved_at: str
    etag: str | None
    last_modified: str | None
    content_type: str | None
    sha256: Sha256Hex
    size_bytes: int = Field(gt=0, le=MAX_COORDINATE_OBJECT_BYTES)

    @field_validator("retrieved_at")
    @classmethod
    def validate_retrieval_timestamp(cls, value: str) -> str:
        """Require UTC without changing the original retrieval timestamp bytes."""

        if datetime.fromisoformat(value).utcoffset() != timedelta(0):
            raise ValueError("coordinate retrieval timestamp must be UTC")
        return value


class PrefetchManifest(ContractModel):
    """Closed missing-entry set bound to the original complete request."""

    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-coordinate-prefetch-v1"]
    request_run_id: str
    producer_commit: str
    request_inventory_sha256: Sha256Hex
    request_inventory_id: str
    inspection_sha256: Sha256Hex
    inspection_id: str
    database_manifest_sha256: Sha256Hex
    objects: dict[str, PrefetchedCoordinate]
    total_size_bytes: int = Field(ge=0, le=MAX_COORDINATE_TOTAL_BYTES)
    prefetch_id: str


@dataclass(frozen=True)
class CoordinateImportPlan:
    """Prevalidated sources and exact prospective offline inspection report."""

    manifest: PrefetchManifest
    cache_root: Path
    coordinates: tuple[tuple[Path, CachedCoordinate], ...]
    proposed_report: dict[str, object]


def fixed_pdb_url(pdb_id: str) -> str:
    """Return the sole approved public endpoint for a canonical PDB entry."""

    if re.fullmatch(r"[0-9][A-Z0-9]{3}", pdb_id) is None:
        raise ValidationError("coordinate prefetch PDB identifier is not canonical")
    token = pdb_id.lower()
    return (
        "https://files.rcsb.org/pub/pdb/data/structures/divided/mmCIF/"
        f"{token[1:3]}/{token}.cif.gz"
    )


def _bounded_file(path: Path, maximum: int, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f"{label} is not a regular link-free file")
    state = path.stat()
    if state.st_nlink != 1 or not 0 < state.st_size <= maximum:
        raise ValidationError(f"{label} is linked, empty or exceeds its byte limit")


def authenticate_inspection(
    snapshot: Path,
    inspection_path: Path,
    *,
    expected_inventory_sha256: str,
    expected_inspection_sha256: str,
) -> tuple[_Inventory, _Report]:
    """Authenticate the full frozen inventory and every ordered inspected hit."""

    inventory = load_frozen_request_inventory(
        snapshot, expected_inventory_sha256=expected_inventory_sha256
    )
    _bounded_file(inspection_path, MAX_PREFETCH_MANIFEST_BYTES, "coordinate inspection")
    if sha256_file(inspection_path) != expected_inspection_sha256:
        raise ValidationError("coordinate inspection checksum changed")
    report = _Report.model_validate(load_json_document(inspection_path), strict=True)
    if (
        report.inspection_id
        != content_id(
            "m6cache_", report.model_dump(mode="json", exclude={"inspection_id"})
        )
        or report.request_run_id != inventory.run_id
        or report.producer_commit != inventory.producer_commit
        or report.request_inventory_sha256 != expected_inventory_sha256
        or report.request_inventory_id != inventory.inventory_id
        or report.database_manifest_sha256 != inventory.database_manifest_sha256
    ):
        raise ValidationError("coordinate inspection source bindings changed")
    _validate_mappings(report, inventory, snapshot)
    for pdb_id in inventory.pdb_ids:
        fixed_pdb_url(pdb_id)
    return inventory, report


def _validate_gzip(path: Path) -> None:
    """Check the entire gzip stream including CRC, with bounded expansion."""

    total = 0
    try:
        with gzip.open(path, "rb") as handle:
            while block := handle.read(
                min(1024 * 1024, MAX_EXPANDED_COORDINATE_BYTES - total + 1)
            ):
                total += len(block)
                if total > MAX_EXPANDED_COORDINATE_BYTES:
                    raise ValidationError(
                        "coordinate gzip exceeds the expanded byte limit"
                    )
    except (OSError, EOFError, zlib.error) as error:
        raise ValidationError(
            f"coordinate object is not valid complete gzip: {path.name}"
        ) from error
    if total == 0:
        raise ValidationError("coordinate object has an empty expanded gzip stream")


def load_prefetch_bundle(
    bundle_root: Path,
    snapshot: Path,
    inspection_path: Path,
    *,
    expected_manifest_sha256: str,
    expected_inventory_sha256: str,
    expected_inspection_sha256: str,
) -> PrefetchManifest:
    """Validate the exact bounded missing-object bundle without cache access."""

    inventory, report = authenticate_inspection(
        snapshot,
        inspection_path,
        expected_inventory_sha256=expected_inventory_sha256,
        expected_inspection_sha256=expected_inspection_sha256,
    )
    if bundle_root.is_symlink() or not bundle_root.is_dir():
        raise ValidationError("coordinate prefetch root is not a regular directory")
    root = bundle_root.resolve(strict=True)
    path = _frozen_file(root, PREFETCH_MANIFEST)
    _bounded_file(path, MAX_PREFETCH_MANIFEST_BYTES, "coordinate prefetch manifest")
    if sha256_file(path) != expected_manifest_sha256:
        raise ValidationError("coordinate prefetch manifest checksum changed")
    manifest = PrefetchManifest.model_validate(load_json_document(path), strict=True)
    if (
        manifest.prefetch_id
        != content_id(
            "m6prefetch_", manifest.model_dump(mode="json", exclude={"prefetch_id"})
        )
        or manifest.request_run_id != inventory.run_id
        or manifest.producer_commit != inventory.producer_commit
        or manifest.request_inventory_sha256 != expected_inventory_sha256
        or manifest.request_inventory_id != inventory.inventory_id
        or manifest.inspection_sha256 != expected_inspection_sha256
        or manifest.inspection_id != report.inspection_id
        or manifest.database_manifest_sha256 != inventory.database_manifest_sha256
        or sorted(manifest.objects) != report.missing_pdb_ids
    ):
        raise ValidationError(
            "coordinate prefetch source bindings or missing-ID set changed"
        )
    expected_paths = {PREFETCH_MANIFEST, "objects"} | {
        f"objects/{pdb_id.lower()}.cif.gz" for pdb_id in manifest.objects
    }
    paths = tuple(root.rglob("*"))
    if (
        {item.relative_to(root).as_posix() for item in paths} != expected_paths
        or any(item.is_symlink() for item in paths)
        or not (root / "objects").is_dir()
    ):
        raise ValidationError(
            "coordinate prefetch file inventory is not exact and link-free"
        )
    total = 0
    for pdb_id, coordinate in manifest.objects.items():
        expected_path = f"objects/{pdb_id.lower()}.cif.gz"
        url = fixed_pdb_url(pdb_id)
        if (
            coordinate.relative_path != expected_path
            or coordinate.requested_url != url
            or coordinate.source_url != url
        ):
            raise ValidationError("coordinate prefetch path or URL provenance changed")
        source = _frozen_file(root, expected_path)
        _bounded_file(
            source, MAX_COORDINATE_OBJECT_BYTES, "prefetched coordinate object"
        )
        size = source.stat().st_size
        total += size
        if (
            size != coordinate.size_bytes
            or sha256_file(source) != coordinate.sha256
            or total > MAX_COORDINATE_TOTAL_BYTES
        ):
            raise ValidationError(
                "coordinate prefetch object checksum or byte budget changed"
            )
        _validate_gzip(source)
    if total != manifest.total_size_bytes:
        raise ValidationError("coordinate prefetch total byte count changed")
    return manifest


def validate_prefetched_mappings(
    bundle_root: Path,
    snapshot: Path,
    inspection_path: Path,
    *,
    expected_manifest_sha256: str,
    expected_inventory_sha256: str,
    expected_inspection_sha256: str,
) -> None:
    """Qualify all originally missing mappings locally before their upload.

    Already cached case mappings may legitimately need older objects and are
    left for the complete remote proposed-union check. An exact parser-key memo
    lives only in this call; complete bundle/input authentication at entry and
    exit detects changed source bytes even when a repeated key was reused.
    """

    manifest = load_prefetch_bundle(
        bundle_root,
        snapshot,
        inspection_path,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_inventory_sha256=expected_inventory_sha256,
        expected_inspection_sha256=expected_inspection_sha256,
    )
    _, report = authenticate_inspection(
        snapshot,
        inspection_path,
        expected_inventory_sha256=expected_inventory_sha256,
        expected_inspection_sha256=expected_inspection_sha256,
    )
    qualified: set[tuple[str, str, str, int, str]] = set()
    for case_id in CASES:
        hits = _read_jsonl(
            _frozen_file(
                snapshot.resolve(strict=True),
                f"requests/{case_id}/selected_structural_hits.jsonl",
            ),
            StructuralSearchHit,
            label="frozen selected coordinate hits",
            identifier=lambda hit: hit.hit_id,
            progress=False,
            allow_empty=True,
        )
        for hit, mapping in zip(hits, report.cases[case_id].mappings, strict=True):
            if mapping.status != "missing":
                continue
            coordinate = manifest.objects[mapping.pdb_id]
            key = (
                coordinate.sha256,
                mapping.pdb_id,
                mapping.target_chain_or_entity,
                mapping.target_sequence_length,
                mapping.target_sequence_sha256,
            )
            if key not in qualified:
                _pdb_entity(
                    _frozen_file(
                        bundle_root.resolve(strict=True), coordinate.relative_path
                    ),
                    hit=hit,
                )
                qualified.add(key)
    load_prefetch_bundle(
        bundle_root,
        snapshot,
        inspection_path,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_inventory_sha256=expected_inventory_sha256,
        expected_inspection_sha256=expected_inspection_sha256,
    )


def _choose_first(
    candidates: list[tuple[Path, CachedCoordinate]],
    hit: StructuralSearchHit,
) -> tuple[Path, CachedCoordinate, _PdbEntity]:
    # Match stable ordering of find_cached_pdb_coordinates plus the unchanged
    # resolver, including equal date/digest records with different provenance.
    ordered = sorted(candidates, key=lambda item: item[1].metadata_relative_path)
    ordered.sort(
        key=lambda item: (item[1].retrieved_at, item[1].object_sha256), reverse=True
    )
    for source, record in ordered:
        try:
            entity = _pdb_entity(source, hit=hit)
        except PdbCoordinateParseError:
            continue
        return source, record, entity
    raise ValidationError(
        f"proposed coordinate cache still lacks {hit.pdb_id}: {hit.hit_id}"
    )


def prevalidate_proposed_cache(
    bundle_root: Path,
    snapshot: Path,
    database_manifest: Path,
    inspection_path: Path,
    *,
    expected_manifest_sha256: str,
    expected_inventory_sha256: str,
    expected_inspection_sha256: str,
) -> CoordinateImportPlan:
    """Validate every proposed destination and complete two-case cache union.

    Existing entries may remain necessary for one case while a fetched version
    supplies the other. A later hit in either case must use that case's first
    selected object; no alternate-object rescue or request reselection occurs.
    """

    manifest = load_prefetch_bundle(
        bundle_root,
        snapshot,
        inspection_path,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_inventory_sha256=expected_inventory_sha256,
        expected_inspection_sha256=expected_inspection_sha256,
    )
    inventory, original = authenticate_inspection(
        snapshot,
        inspection_path,
        expected_inventory_sha256=expected_inventory_sha256,
        expected_inspection_sha256=expected_inspection_sha256,
    )
    if (
        database_manifest.is_symlink()
        or sha256_file(database_manifest) != inventory.database_manifest_sha256
    ):
        raise ValidationError("coordinate import database binding changed")
    _, _, resource = _resources(database_manifest)
    cache_root = Path(resource.root_path).resolve(strict=True)
    candidates: dict[str, list[tuple[Path, CachedCoordinate]]] = {}
    checked_gzip: set[str] = set()
    for pdb_id in inventory.pdb_ids:
        existing = find_cached_pdb_coordinates(
            cache_root, pdb_id=pdb_id, full_checksum=True, progress=False
        )
        candidates[pdb_id] = []
        for record in existing:
            source = cache_root / record.object_relative_path
            if record.object_sha256 not in checked_gzip:
                _validate_gzip(source)
                checked_gzip.add(record.object_sha256)
            candidates[pdb_id].append((source, record))
    current = inspect_coordinate_cache(
        snapshot, database_manifest, expected_inventory_sha256=expected_inventory_sha256
    )
    if current != original.model_dump(mode="json"):
        raise ValidationError(
            "coordinate cache changed since the authenticated inspection"
        )
    coordinates = []
    for pdb_id, fetched in sorted(manifest.objects.items()):
        source = _frozen_file(bundle_root.resolve(strict=True), fetched.relative_path)
        record = preflight_pdb_coordinate(
            cache_root,
            source,
            pdb_id=pdb_id,
            requested_url=fetched.requested_url,
            source_url=fetched.source_url,
            retrieved_at=fetched.retrieved_at,
            etag=fetched.etag,
            last_modified=fetched.last_modified,
            content_type=fetched.content_type,
            progress=False,
        )
        if (
            record.object_sha256 != fetched.sha256
            or record.size_bytes != fetched.size_bytes
        ):
            raise ValidationError("coordinate prefetch source changed during preflight")
        coordinates.append((source, record))
        if not any(
            item[1].metadata_relative_path == record.metadata_relative_path
            for item in candidates[pdb_id]
        ):
            candidates[pdb_id].append((source, record))
    proposed = original.model_copy(deep=True)
    qualified: dict[str, dict[str, object]] = {}
    used_new: set[str] = set()
    new_metadata = {record.metadata_sha256 for _, record in coordinates}
    for case_id in CASES:
        hits = _read_jsonl(
            _frozen_file(
                snapshot.resolve(strict=True),
                f"requests/{case_id}/selected_structural_hits.jsonl",
            ),
            StructuralSearchHit,
            label="frozen selected coordinate hits",
            identifier=lambda hit: hit.hit_id,
            progress=False,
            allow_empty=True,
        )
        selected: dict[str, tuple[Path, CachedCoordinate]] = {}
        for index, (hit, mapping) in enumerate(
            zip(hits, proposed.cases[case_id].mappings, strict=True)
        ):
            pdb_id = str(hit.pdb_id).upper()
            if pdb_id not in selected:
                source, record, entity = _choose_first(candidates[pdb_id], hit)
                selected[pdb_id] = source, record
            else:
                source, record = selected[pdb_id]
                entity = _pdb_entity(source, hit=hit)
            qualified[record.metadata_sha256] = dict(record.as_json())
            if record.metadata_sha256 in new_metadata:
                used_new.add(pdb_id)
            # Construct new immutable mapping records rather than mutating models.
            replacement = mapping.model_copy(
                update={
                    "status": "cached",
                    "coordinate_sha256": record.object_sha256,
                    "metadata_sha256": record.metadata_sha256,
                    "entity_id": entity.entity_id,
                    "source_sequence_sha256": entity.sequence_sha256,
                }
            )
            proposed.cases[case_id].mappings[index] = replacement
    if used_new != set(manifest.objects):
        raise ValidationError("prefetched object did not qualify a requested mapping")
    report = proposed.model_dump(mode="json")
    report["cached_coordinates"] = qualified
    report["missing_pdb_ids"] = []
    for case in report["cases"].values():
        case["cached_mapping_count"] = case["requested_mapping_count"]
        case["missing_mapping_count"] = 0
        case["missing_pdb_ids"] = []
    report.pop("inspection_id")
    report["inspection_id"] = content_id("m6cache_", report)
    _validate_mappings(_Report.model_validate(report, strict=True), inventory, snapshot)
    # Detect source or frozen-binding changes while checking the complete union.
    load_prefetch_bundle(
        bundle_root,
        snapshot,
        inspection_path,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_inventory_sha256=expected_inventory_sha256,
        expected_inspection_sha256=expected_inspection_sha256,
    )
    return CoordinateImportPlan(manifest, cache_root, tuple(coordinates), report)
