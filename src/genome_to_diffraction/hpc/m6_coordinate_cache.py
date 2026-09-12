"""Inspect every frozen M6 native-control coordinate request without writing.

The caller must first validate/rederive the original producer snapshot with
``freeze_request_inventory``. This helper verifies its confirmed inventory,
all frozen file checksums, and the bound database manifest, then uses the unchanged
offline registration resolver. It never downloads, publishes, or selects models.
The returned report retains every selected hit in case-local order, distinguishes
``cached`` from ``missing``, and deduplicates only missing public PDB identifiers.

Metadata/index/layout/checksum errors and later-hit mapping conflicts propagate.
The existing resolver skips checksum-consistent coordinate format/mapping parse
failures while choosing an entry's first-hit object; this is not a full malformed-
mmCIF rejection boundary. Subsequent same-entry hits must use that chosen object.
Python and Gemmi come from the pinned project runtime; no external command runs.
The report content ID covers the request/database bindings and observed objects,
not a durable cache-validity claim: inspection must be repeated before import/use.
Tests cover conservation, shared missing IDs, source bindings, integrity failures,
and the unchanged first-object selection rule. This is not native acceptance.
"""

from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.databases.cache import CachedCoordinate
from genome_to_diffraction.hpc.m6_coordinate_requests import CASES
from genome_to_diffraction.hpc.models import ValidationError
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    StructuralSearchHit,
)
from genome_to_diffraction.structure_search.pdb_coordinates import (
    _DIRECT_PROVIDER,
    _PROSTT5_PROVIDER,
    PdbCoordinateInputError,
    PdbCoordinateRegistrationRequest,
    _cached_or_downloaded,
    _pdb_entity,
    _read_jsonl,
    _resources,
    _validate_hit,
)


class _Case(ContractModel):
    catalogue_key: Sha256Hex
    eligible_group_count: int = Field(ge=0)
    accepted_hit_count: int = Field(ge=0)
    registration_mapping_bound: int = Field(ge=0)
    requested_mapping_count: int = Field(ge=0)
    pdb_ids: list[str]
    selected_hits_sha256: Sha256Hex


class _Inventory(ContractModel):
    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-coordinate-requests-v1"]
    run_id: str
    producer_commit: str
    database_manifest_sha256: Sha256Hex
    cases: dict[str, _Case]
    distinct_pdb_count: int = Field(ge=0)
    pdb_ids: list[str]
    input_and_request_sha256: dict[str, Sha256Hex]
    network_acquisition_performed: Literal[False]
    cache_import_performed: Literal[False]
    inventory_id: str


def _frozen_file(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
        raise ValidationError("coordinate snapshot path is not canonical")
    target = root.joinpath(*path.parts)
    if (
        target.is_symlink()
        or target.resolve(strict=True) != target
        or not target.is_file()
    ):
        raise ValidationError("coordinate snapshot file is not regular and link-free")
    return target


def load_frozen_request_inventory(
    snapshot: Path,
    *,
    expected_inventory_sha256: str,
) -> _Inventory:
    """Authenticate the complete frozen file set without opening a remote cache."""

    if snapshot.is_symlink() or not snapshot.is_dir():
        raise ValidationError("coordinate request snapshot is not a regular directory")
    root = snapshot.resolve(strict=True)
    inventory_path = _frozen_file(root, "request_inventory.json")
    if sha256_file(inventory_path) != expected_inventory_sha256:
        raise ValidationError("coordinate request inventory checksum changed")
    inventory = _Inventory.model_validate(
        load_json_document(inventory_path), strict=True
    )
    if inventory.inventory_id != content_id(
        "m6coords_", inventory.model_dump(mode="json", exclude={"inventory_id"})
    ):
        raise ValidationError("coordinate request inventory identity changed")
    if set(inventory.cases) != set(CASES):
        raise ValidationError("coordinate request inventory lacks the fixed two cases")
    expected_files = set(inventory.input_and_request_sha256) | {
        "request_inventory.json"
    }
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if not path.is_dir() or path.is_symlink()
    }
    if actual_files != expected_files:
        raise ValidationError("coordinate snapshot file inventory changed")
    for name, expected_sha256 in inventory.input_and_request_sha256.items():
        if sha256_file(_frozen_file(root, name)) != expected_sha256:
            raise ValidationError("coordinate snapshot input checksum changed")
    return inventory


def inspect_coordinate_cache(
    snapshot: Path,
    database_manifest: Path,
    *,
    expected_inventory_sha256: str,
) -> dict[str, object]:
    """Report every original C001/C025 mapping using only the qualified cache.

    ``snapshot`` is the validated/rederived request-export directory, never a hit
    subset. ``database_manifest`` must have its frozen original checksum. No path is
    created or modified. Only the offline resolver's typed first-hit absence becomes
    ``missing``; an incompatible later hit aborts rather than selecting another file.
    """

    inventory = load_frozen_request_inventory(
        snapshot, expected_inventory_sha256=expected_inventory_sha256
    )
    root = snapshot.resolve(strict=True)
    if (
        database_manifest.is_symlink()
        or not database_manifest.is_file()
        or sha256_file(database_manifest) != inventory.database_manifest_sha256
    ):
        raise ValidationError("coordinate inspection database binding changed")
    sequence_resource, foldseek_resource, cache_resource = _resources(database_manifest)
    expected_database_ids = {
        _DIRECT_PROVIDER: sequence_resource.database_id,
        _PROSTT5_PROVIDER: foldseek_resource.database_id,
    }
    cache_root = Path(cache_resource.root_path).resolve(strict=True)
    cases: dict[str, object] = {}
    coordinates: dict[str, object] = {}
    all_entries: set[str] = set()
    missing_entries: set[str] = set()
    mapping_count = 0
    for case_id in CASES:
        case = inventory.cases[case_id]
        selected_path = _frozen_file(
            root, f"requests/{case_id}/selected_structural_hits.jsonl"
        )
        groups_path = _frozen_file(
            root, f"requests/{case_id}/eligible-candidates/sequence_groups.jsonl"
        )
        groups = _read_jsonl(
            groups_path,
            SequenceGroupRecord,
            label="frozen coordinate groups",
            identifier=lambda group: group.sequence_group_id,
            progress=False,
            allow_empty=True,
        )
        hits = _read_jsonl(
            selected_path,
            StructuralSearchHit,
            label="frozen selected coordinate hits",
            identifier=lambda hit: hit.hit_id,
            progress=False,
            allow_empty=True,
        )
        group_index = {group.sequence_group_id: group for group in groups}
        for hit in hits:
            _validate_hit(hit, group_index)
            if hit.database_id != expected_database_ids[hit.provider]:
                raise ValidationError(
                    "coordinate hit discovery database binding changed"
                )
        entries = {str(hit.pdb_id).upper() for hit in hits}
        if (
            len(groups) != case.eligible_group_count
            or len(hits) != case.requested_mapping_count
            or len(hits) > case.registration_mapping_bound
            or len(hits) > case.accepted_hit_count
            or sorted(entries) != case.pdb_ids
            or sha256_file(selected_path) != case.selected_hits_sha256
        ):
            raise ValidationError("coordinate case request inventory changed")
        all_entries.update(entries)
        request = PdbCoordinateRegistrationRequest(
            structural_hits_jsonl=selected_path,
            sequence_groups_jsonl=groups_path,
            database_manifest=database_manifest,
            output_directory=root,
            allow_network_acquisition=False,
            progress=False,
        )
        entry_cache: dict[str, CachedCoordinate | None] = {}
        mappings: list[dict[str, object]] = []
        for hit in hits:
            pdb_id = str(hit.pdb_id).upper()
            if pdb_id not in entry_cache:
                try:
                    cached, entity, _ = _cached_or_downloaded(
                        cache_root, hit=hit, request=request
                    )
                except PdbCoordinateInputError:
                    # For this prevalidated hit and offline request, the unchanged
                    # resolver's sole typed input error means qualified absence.
                    cached = None
                    entity = None
                entry_cache[pdb_id] = cached
            else:
                cached = entry_cache[pdb_id]
                entity = (
                    _pdb_entity(cache_root / cached.object_relative_path, hit=hit)
                    if cached is not None
                    else None
                )
            if cached is not None:
                coordinates[cached.metadata_sha256] = cached.as_json()
            mappings.append(
                {
                    "hit_id": hit.hit_id,
                    "sequence_group_id": hit.sequence_group_id,
                    "pdb_id": pdb_id,
                    "target_chain_or_entity": hit.target_chain_or_entity,
                    "target_sequence_sha256": hit.raw_metrics["target_sequence_sha256"],
                    "target_sequence_length": hit.raw_metrics["target_sequence_length"],
                    "status": "cached" if cached is not None else "missing",
                    "coordinate_sha256": cached.object_sha256 if cached else None,
                    "metadata_sha256": cached.metadata_sha256 if cached else None,
                    "entity_id": entity.entity_id if entity else None,
                    "source_sequence_sha256": entity.sequence_sha256
                    if entity
                    else None,
                }
            )
        missing = sorted(key for key, value in entry_cache.items() if value is None)
        missing_entries.update(missing)
        mapping_count += len(mappings)
        missing_count = sum(item["status"] == "missing" for item in mappings)
        cases[case_id] = {
            "catalogue_key": case.catalogue_key,
            "requested_mapping_count": len(mappings),
            "cached_mapping_count": len(mappings) - missing_count,
            "missing_mapping_count": missing_count,
            "missing_pdb_ids": missing,
            "mappings": mappings,
        }
    if (
        sorted(all_entries) != inventory.pdb_ids
        or len(all_entries) != inventory.distinct_pdb_count
    ):
        raise ValidationError("coordinate request union changed")
    report = {
        "schema_version": "1.0",
        "adapter_version": "m6-coordinate-cache-inspection-v1",
        "request_run_id": inventory.run_id,
        "producer_commit": inventory.producer_commit,
        "request_inventory_id": inventory.inventory_id,
        "request_inventory_sha256": expected_inventory_sha256,
        "database_manifest_sha256": inventory.database_manifest_sha256,
        "coordinate_cache_database_id": cache_resource.database_id,
        "requested_mapping_count": mapping_count,
        "distinct_pdb_count": len(all_entries),
        "missing_pdb_ids": sorted(missing_entries),
        "cached_coordinates": coordinates,
        "cases": cases,
        "network_acquisition_performed": False,
        "cache_import_performed": False,
    }
    report["inspection_id"] = content_id("m6cache_", report)
    return report
