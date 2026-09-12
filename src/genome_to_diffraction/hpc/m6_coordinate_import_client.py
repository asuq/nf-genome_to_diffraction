"""Authenticate bounded Marmic coordinate import inputs and returned evidence.

This is a helper of the original HPC client, not a second execution interface.
It binds the existing owned-run inspection, checks the approved storage limits,
packages only the complete validated prefetch bundle, and authenticates every
imported provenance record and every original ordered mapping in the response.
It does not download, select scientific candidates, access the remote cache or
submit jobs. Python/Gemmi come from the pinned project runtime. IDs bind exact
source, request, inspection and retrieval evidence; observations do not promise
future cache validity. Unsafe paths, changed bytes, incomplete inventories and
failed/ambiguous imports fail before local success publication. Tests cover these
boundaries through the original controller, including preserved failed attempts.
"""

import hashlib
import re
import shutil
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import Field

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.hpc.m6_coordinate_archive import (
    extract_import_response_archive,
)
from genome_to_diffraction.hpc.m6_coordinate_cache import _frozen_file, _Inventory
from genome_to_diffraction.hpc.m6_coordinate_inspection_client import (
    _Bundle,
    _Coordinate,
    _Report,
    _validate_mappings,
)
from genome_to_diffraction.hpc.m6_coordinate_prefetch import (
    MAX_ADDITIONAL_DISK_BYTES,
    MAX_COORDINATE_OBJECT_BYTES,
    MAX_COORDINATE_TOTAL_BYTES,
    MAX_PREFETCH_ARCHIVE_BYTES,
    PrefetchManifest,
    authenticate_inspection,
    load_prefetch_bundle,
)
from genome_to_diffraction.hpc.m6_coordinate_requests import CASES
from genome_to_diffraction.hpc.m6_coordinate_storage import (
    coordinate_storage_reservations,
)
from genome_to_diffraction.hpc.models import (
    MAX_REVIEW_ARTIFACT_FILE_BYTES,
    MAX_REVIEW_ARTIFACT_TOTAL_BYTES,
    LocalRunRecord,
    ValidationError,
)
from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex, UtcTimestamp
from genome_to_diffraction.schemas.io import load_json_document, parse_json_document
from genome_to_diffraction.schemas.results import StructuralSearchHit
from genome_to_diffraction.structure_search.pdb_coordinates import (
    _pdb_entity,
    _read_jsonl,
)


class _Filesystem(ContractModel):
    device: int = Field(ge=0)
    free_bytes: int = Field(ge=0)
    required_bytes: int = Field(gt=0)


class _StorageRoot(ContractModel):
    device: int = Field(ge=0)
    frsize_bytes: int = Field(gt=0)


class _StorageLayout(ContractModel):
    artifacts: _StorageRoot
    cache: _StorageRoot


class _StoragePreflight(ContractModel):
    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-coordinate-storage-preflight-v2"]
    run_id: str
    commit: str
    request_run_id: str
    producer_commit: str
    request_inventory_sha256: Sha256Hex
    inspection_sha256: Sha256Hex
    database_manifest_sha256: Sha256Hex
    coordinate_total_limit_bytes: int
    coordinate_object_limit_bytes: int
    additional_disk_limit_bytes: int
    layout: _StorageLayout
    filesystems: list[_Filesystem]
    checked_at: UtcTimestamp
    preflight_id: str


class _ImportBundle(ContractModel):
    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-coordinate-import-bundle-v1"]
    run_id: str
    commit: str
    request_run_id: str
    producer_commit: str
    request_inventory_sha256: Sha256Hex
    request_inventory_id: str
    inspection_sha256: Sha256Hex
    inspection_id: str
    database_manifest_sha256: Sha256Hex
    prefetch_manifest_sha256: Sha256Hex
    prefetch_id: str
    archive_sha256: Sha256Hex
    archive_size_bytes: int = Field(gt=0, le=MAX_PREFETCH_ARCHIVE_BYTES)
    postinspection_sha256: Sha256Hex
    postinspection_size_bytes: int = Field(gt=0, le=MAX_REVIEW_ARTIFACT_FILE_BYTES)
    postinspection_id: str
    imported_coordinates: dict[str, _Coordinate]
    total_coordinate_bytes: int = Field(gt=0, le=MAX_COORDINATE_TOTAL_BYTES)
    imported_at: UtcTimestamp
    network_acquisition_performed: Literal[False]
    cache_import_performed: Literal[True]
    status: Literal["complete"]
    bundle_id: str


class _PrefetchReceipt(ContractModel):
    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-coordinate-prefetch-receipt-v1"]
    run_id: str
    commit: str
    request_run_id: str
    producer_commit: str
    request_inventory_sha256: Sha256Hex
    inspection_sha256: Sha256Hex
    prefetch_manifest_sha256: Sha256Hex
    prefetch_id: str
    archive_sha256: Sha256Hex
    archive_size_bytes: int = Field(gt=0, le=MAX_PREFETCH_ARCHIVE_BYTES)
    storage_preflight_sha256: Sha256Hex
    object_count: int = Field(gt=0)
    total_coordinate_bytes: int = Field(gt=0, le=MAX_COORDINATE_TOTAL_BYTES)
    completed_at: UtcTimestamp
    network_acquisition_performed: Literal[True]
    cache_import_performed: Literal[False]
    status: Literal["ready"]
    receipt_id: str


def _regular_file(path: Path, *, maximum: int = MAX_REVIEW_ARTIFACT_FILE_BYTES) -> Path:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.resolve(strict=True) != path
        or not 0 < path.stat().st_size <= maximum
    ):
        raise ValidationError("coordinate import input is unsafe or exceeds its bound")
    return path


def _check_identity(document: object, *, field: str, prefix: str) -> None:
    if not isinstance(document, dict) or document.get(field) != content_id(
        prefix, {key: value for key, value in document.items() if key != field}
    ):
        raise ValidationError("coordinate import evidence content identity changed")


def _check_timestamp(document: object, field: str) -> None:
    if not isinstance(document, dict) or not isinstance(document.get(field), str):
        raise ValidationError("coordinate import timestamp must be explicit UTC text")
    try:
        timestamp = datetime.fromisoformat(document[field])
    except ValueError as error:
        raise ValidationError("coordinate import timestamp is not ISO 8601") from error
    if timestamp.utcoffset() != timedelta(0):
        raise ValidationError("coordinate import timestamp is not explicitly UTC")


def load_saved_inspection(
    inspection_root: Path,
    snapshot: Path,
    *,
    record: LocalRunRecord,
    request_record: LocalRunRecord,
    confirmed_inspection_sha256: str,
) -> tuple[_Inventory, _Report]:
    """Authenticate the saved inspection's complete original and new-run bindings."""

    if re.fullmatch(r"[0-9a-f]{64}", confirmed_inspection_sha256) is None:
        raise ValidationError("confirm the exact coordinate inspection checksum")
    if (
        inspection_root.is_symlink()
        or not inspection_root.is_dir()
        or inspection_root.resolve(strict=True) != inspection_root
        or {path.name for path in inspection_root.iterdir()}
        != {"inspection.json", "inspection_bundle.json"}
    ):
        raise ValidationError("saved coordinate inspection inventory is unsafe")
    report_path = _regular_file(inspection_root / "inspection.json")
    bundle_path = _regular_file(inspection_root / "inspection_bundle.json")
    bundle = _Bundle.model_validate_json(bundle_path.read_bytes())
    _check_identity(
        load_json_document(bundle_path), field="bundle_id", prefix="m6inspect_"
    )
    _check_timestamp(load_json_document(bundle_path), "inspected_at")
    inventory, report = authenticate_inspection(
        snapshot,
        report_path,
        expected_inventory_sha256=bundle.request_inventory_sha256,
        expected_inspection_sha256=confirmed_inspection_sha256,
    )
    if (
        bundle.run_id != record.run_id
        or bundle.commit != record.commit
        or bundle.request_run_id != request_record.run_id
        or bundle.producer_commit != request_record.commit
        or bundle.request_run_id != inventory.run_id
        or bundle.producer_commit != inventory.producer_commit
        or bundle.request_inventory_id != inventory.inventory_id
        or bundle.database_manifest_sha256 != inventory.database_manifest_sha256
        or bundle.inspection_sha256 != confirmed_inspection_sha256
        or bundle.inspection_sha256 != sha256_file(report_path)
        or bundle.inspection_size_bytes != report_path.stat().st_size
        or bundle.inspection_id != report.inspection_id
    ):
        raise ValidationError("saved coordinate inspection run/source binding changed")
    return inventory, report


def validate_storage_preflight(
    fields: dict[str, str],
    *,
    record: LocalRunRecord,
    request_record: LocalRunRecord,
    inventory: _Inventory,
    report: _Report,
    inspection_sha256: str,
) -> dict[str, object]:
    """Rederive exact reservations and check observed space on each filesystem."""

    if (
        set(fields) != {"operation", "run_id", "status", "storage_preflight"}
        or fields["operation"] != "coordinate-import-preflight"
        or fields["run_id"] != record.run_id
        or fields["status"] != "ready"
        or len(fields["storage_preflight"].encode("utf-8")) > 64 * 1024
    ):
        raise ValidationError("coordinate storage preflight is incomplete or invalid")
    raw = parse_json_document(fields["storage_preflight"], label="coordinate storage")
    preflight = _StoragePreflight.model_validate_json(fields["storage_preflight"])
    _check_identity(raw, field="preflight_id", prefix="m6coordstorage_")
    _check_timestamp(raw, "checked_at")
    assert isinstance(raw, dict)
    if (
        preflight.run_id != record.run_id
        or preflight.commit != record.commit
        or preflight.request_run_id != request_record.run_id
        or preflight.producer_commit != request_record.commit
        or preflight.request_inventory_sha256 != report.request_inventory_sha256
        or preflight.inspection_sha256 != inspection_sha256
        or preflight.database_manifest_sha256 != inventory.database_manifest_sha256
        or preflight.coordinate_total_limit_bytes != MAX_COORDINATE_TOTAL_BYTES
        or preflight.coordinate_object_limit_bytes != MAX_COORDINATE_OBJECT_BYTES
        or preflight.additional_disk_limit_bytes != MAX_ADDITIONAL_DISK_BYTES
    ):
        raise ValidationError(
            "coordinate storage scope, source or approved limit changed"
        )
    filesystems = preflight.filesystems
    reservations = coordinate_storage_reservations(
        len(report.missing_pdb_ids),
        artifacts_frsize_bytes=preflight.layout.artifacts.frsize_bytes,
        cache_frsize_bytes=preflight.layout.cache.frsize_bytes,
    )
    expected: dict[int, int] = {}
    for root, required in zip(
        (preflight.layout.artifacts, preflight.layout.cache), reservations, strict=True
    ):
        expected[root.device] = expected.get(root.device, 0) + required
    if (
        len(filesystems) not in {1, 2}
        or len({item.device for item in filesystems}) != len(filesystems)
        or {item.device: item.required_bytes for item in filesystems} != expected
        or any(item.free_bytes < item.required_bytes for item in filesystems)
    ):
        raise ValidationError(
            "coordinate storage does not meet the derived reservations"
        )
    return raw


def build_prefetch_archive(
    bundle_root: Path,
    archive: Path,
    *,
    snapshot: Path,
    inspection_path: Path,
    confirmed_manifest_sha256: str,
    confirmed_inventory_sha256: str,
    confirmed_inspection_sha256: str,
) -> PrefetchManifest:
    """Package the complete canonical bundle as plain tar with verified member bytes."""

    manifest = load_prefetch_bundle(
        bundle_root,
        snapshot,
        inspection_path,
        expected_manifest_sha256=confirmed_manifest_sha256,
        expected_inventory_sha256=confirmed_inventory_sha256,
        expected_inspection_sha256=confirmed_inspection_sha256,
    )
    names = {"prefetch_manifest.json": confirmed_manifest_sha256} | {
        value.relative_path: value.sha256 for value in manifest.objects.values()
    }
    lengths = {name: _regular_file(bundle_root / name).stat().st_size for name in names}
    # USTAR headers plus block padding are deterministic for these ASCII short paths.
    expected_size = (
        (
            sum(512 + ((size + 511) // 512) * 512 for size in lengths.values())
            + 1024
            + 10239
        )
        // 10240
    ) * 10240
    if expected_size > MAX_PREFETCH_ARCHIVE_BYTES:
        raise ValidationError("coordinate import archive exceeds the approved bound")
    if (
        archive.exists()
        or archive.is_symlink()
        or archive.parent.resolve() != archive.parent
    ):
        raise ValidationError(
            "coordinate import archive destination must be new and safe"
        )
    if (
        shutil.disk_usage(archive.parent).free
        < expected_size + MAX_REVIEW_ARTIFACT_TOTAL_BYTES
    ):
        raise ValidationError(
            "insufficient local space for the coordinate archive and evidence"
        )
    with (
        archive.open("xb") as output,
        tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as tar,
    ):
        for name in sorted(names):
            path = _regular_file(bundle_root / name)
            size = lengths[name]
            if path.stat().st_size != size or sha256_file(path) != names[name]:
                raise ValidationError(
                    "coordinate input changed before archive packaging"
                )
            if (
                shutil.disk_usage(archive.parent).free
                < size + MAX_REVIEW_ARTIFACT_TOTAL_BYTES
            ):
                raise ValidationError(
                    "local space changed during coordinate archive packaging"
                )
            member = tarfile.TarInfo(name)
            member.size = size
            member.mode = 0o444
            with path.open("rb") as source:
                tar.addfile(member, source)
            if path.stat().st_size != size or sha256_file(path) != names[name]:
                raise ValidationError(
                    "coordinate input changed during archive packaging"
                )
    if archive.stat().st_size != expected_size:
        raise ValidationError(
            "coordinate archive size differs from its exact inventory"
        )
    # Re-read the bytes actually sent, not just the source paths on either side.
    with tarfile.open(archive, mode="r|") as tar:
        seen: set[str] = set()
        for member in tar:
            if member.name not in names or member.name in seen or not member.isfile():
                raise ValidationError("coordinate archive member inventory changed")
            seen.add(member.name)
            source = tar.extractfile(member)
            if source is None:
                raise ValidationError("coordinate archive member is unreadable")
            digest = hashlib.sha256()
            with source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != names[member.name]:
                raise ValidationError("coordinate archive member checksum changed")
        if seen != set(names):
            raise ValidationError("coordinate archive is incomplete")
    archive.chmod(0o444)
    return manifest


def validate_prefetch_receipt(
    prefetch_root: Path,
    *,
    record: LocalRunRecord,
    request_record: LocalRunRecord,
    manifest: PrefetchManifest,
    confirmed_manifest_sha256: str,
) -> _PrefetchReceipt:
    """Require completed acquisition/packaging, never infer success from partials."""

    path = _regular_file(prefetch_root / "prefetch_receipt.json")
    receipt = _PrefetchReceipt.model_validate_json(path.read_bytes())
    _check_identity(
        load_json_document(path), field="receipt_id", prefix="m6coordprefetch_"
    )
    _check_timestamp(load_json_document(path), "completed_at")
    archive = _regular_file(
        prefetch_root / "coordinate-import.tar", maximum=MAX_PREFETCH_ARCHIVE_BYTES
    )
    storage = _regular_file(prefetch_root.parent / "coordinate-prefetch-storage.json")
    if (
        receipt.run_id != record.run_id
        or receipt.commit != record.commit
        or receipt.request_run_id != request_record.run_id
        or receipt.producer_commit != request_record.commit
        or receipt.request_inventory_sha256 != manifest.request_inventory_sha256
        or receipt.inspection_sha256 != manifest.inspection_sha256
        or receipt.prefetch_manifest_sha256 != confirmed_manifest_sha256
        or receipt.prefetch_id != manifest.prefetch_id
        or receipt.archive_sha256 != sha256_file(archive)
        or receipt.archive_size_bytes != archive.stat().st_size
        or receipt.storage_preflight_sha256 != sha256_file(storage)
        or receipt.object_count != len(manifest.objects)
        or receipt.total_coordinate_bytes != manifest.total_size_bytes
    ):
        raise ValidationError("coordinate prefetch completion receipt binding changed")
    return receipt


def _validate_mapping_sources(
    snapshot: Path,
    bundle_root: Path,
    original: _Report,
    report: _Report,
    imported: dict[str, _Coordinate],
    manifest: PrefetchManifest,
) -> None:
    """Pin repaired mappings to imported bytes; retain exact unchanged old evidence."""

    parsed: dict[tuple[str, str, str, int, str], tuple[str, str]] = {}
    used_imports: set[str] = set()
    for case_id in CASES:
        hits = _read_jsonl(
            _frozen_file(
                snapshot.resolve(strict=True),
                f"requests/{case_id}/selected_structural_hits.jsonl",
            ),
            StructuralSearchHit,
            label="frozen coordinate import mappings",
            identifier=lambda hit: hit.hit_id,
            progress=False,
            allow_empty=True,
        )
        for hit, before, after in zip(
            hits,
            original.cases[case_id].mappings,
            report.cases[case_id].mappings,
            strict=True,
        ):
            coordinate = imported.get(after.pdb_id)
            from_import = coordinate is not None and (
                after.coordinate_sha256 == coordinate.object_sha256
                and after.metadata_sha256 == coordinate.metadata_sha256
            )
            if before.status == "missing" and not from_import:
                raise ValidationError(
                    "repaired mapping does not use its imported object"
                )
            if not from_import:
                if after != before:
                    raise ValidationError(
                        "post-import cached mapping changed without new coordinates"
                    )
                continue
            assert coordinate is not None
            used_imports.add(after.pdb_id)
            key = (
                coordinate.object_sha256,
                after.pdb_id,
                after.target_chain_or_entity,
                after.target_sequence_length,
                after.target_sequence_sha256,
            )
            if key not in parsed:
                entity = _pdb_entity(
                    _frozen_file(
                        bundle_root.resolve(strict=True),
                        manifest.objects[after.pdb_id].relative_path,
                    ),
                    hit=hit,
                )
                parsed[key] = entity.entity_id, entity.sequence_sha256
            if parsed[key] != (after.entity_id, after.source_sequence_sha256):
                raise ValidationError(
                    "post-import mapping differs from actual staged coordinates"
                )
    if used_imports != set(imported):
        raise ValidationError("imported object is not used by any requested mapping")


def validate_import_response(
    response_archive: Path,
    destination: Path,
    *,
    snapshot: Path,
    inspection_path: Path,
    bundle_root: Path,
    upload_archive: Path,
    record: LocalRunRecord,
    request_record: LocalRunRecord,
    confirmed_manifest_sha256: str,
    confirmed_inventory_sha256: str,
    confirmed_inspection_sha256: str,
) -> dict[str, object]:
    """Accept only a complete bound import and fully conserved offline reinspection."""

    manifest = load_prefetch_bundle(
        bundle_root,
        snapshot,
        inspection_path,
        expected_manifest_sha256=confirmed_manifest_sha256,
        expected_inventory_sha256=confirmed_inventory_sha256,
        expected_inspection_sha256=confirmed_inspection_sha256,
    )
    inventory, original_report = authenticate_inspection(
        snapshot,
        inspection_path,
        expected_inventory_sha256=confirmed_inventory_sha256,
        expected_inspection_sha256=confirmed_inspection_sha256,
    )
    extract_import_response_archive(response_archive, destination)
    bundle_path = destination / "import_bundle.json"
    bundle = _ImportBundle.model_validate_json(bundle_path.read_bytes())
    _check_identity(
        load_json_document(bundle_path), field="bundle_id", prefix="m6coordimport_"
    )
    _check_timestamp(load_json_document(bundle_path), "imported_at")
    report_path = destination / "postinspection.json"
    report = _Report.model_validate_json(report_path.read_bytes())
    _check_identity(
        load_json_document(report_path), field="inspection_id", prefix="m6cache_"
    )
    if (
        bundle.run_id != record.run_id
        or bundle.commit != record.commit
        or bundle.request_run_id != request_record.run_id
        or bundle.producer_commit != request_record.commit
        or bundle.request_inventory_id != inventory.inventory_id
        or bundle.request_inventory_sha256 != confirmed_inventory_sha256
        or bundle.database_manifest_sha256 != inventory.database_manifest_sha256
        or bundle.inspection_sha256 != confirmed_inspection_sha256
        or bundle.inspection_id != original_report.inspection_id
        or bundle.prefetch_manifest_sha256 != confirmed_manifest_sha256
        or bundle.prefetch_id != manifest.prefetch_id
        or bundle.archive_sha256 != sha256_file(upload_archive)
        or bundle.archive_size_bytes != upload_archive.stat().st_size
        or bundle.postinspection_sha256 != sha256_file(report_path)
        or bundle.postinspection_size_bytes != report_path.stat().st_size
        or bundle.postinspection_id != report.inspection_id
        or bundle.total_coordinate_bytes != manifest.total_size_bytes
        or set(bundle.imported_coordinates) != set(manifest.objects)
    ):
        raise ValidationError(
            "coordinate import run/source/request/payload binding changed"
        )
    for pdb_id, expected in manifest.objects.items():
        actual = bundle.imported_coordinates[pdb_id]
        if (
            actual.source_id != pdb_id.lower()
            or actual.object_sha256 != expected.sha256
            or actual.size_bytes != expected.size_bytes
            or actual.requested_url != expected.requested_url
            or actual.source_url != expected.source_url
            or actual.retrieved_at != expected.retrieved_at
            or actual.etag != expected.etag
            or actual.last_modified != expected.last_modified
            or actual.content_type != expected.content_type
        ):
            raise ValidationError("imported coordinate retrieval provenance changed")
        metadata = actual.model_dump(
            exclude={"metadata_relative_path", "metadata_sha256"}
        ) | {"schema_version": "1.0"}
        digest = actual.object_sha256
        if (
            actual.object_relative_path != f"pdb/objects/{digest[:2]}/{digest}.cif.gz"
            or actual.metadata_relative_path
            != f"pdb/metadata/{pdb_id.lower()}/{canonical_digest(metadata)}.json"
        ):
            raise ValidationError("imported coordinate publication paths changed")
    if (
        report.request_run_id != request_record.run_id
        or report.producer_commit != request_record.commit
        or report.request_inventory_id != inventory.inventory_id
        or report.request_inventory_sha256 != confirmed_inventory_sha256
        or report.database_manifest_sha256 != inventory.database_manifest_sha256
        or report.coordinate_cache_database_id
        != original_report.coordinate_cache_database_id
        or report.missing_pdb_ids
    ):
        raise ValidationError(
            "post-import inspection is incomplete or differently bound"
        )
    _validate_mappings(report, inventory, snapshot)
    admitted = dict(original_report.cached_coordinates)
    for coordinate in bundle.imported_coordinates.values():
        existing = admitted.get(coordinate.metadata_sha256)
        if existing is not None and existing != coordinate:
            raise ValidationError(
                "imported coordinate collides with original provenance"
            )
        admitted[coordinate.metadata_sha256] = coordinate
    if any(
        admitted.get(digest) != coordinate
        for digest, coordinate in report.cached_coordinates.items()
    ):
        raise ValidationError(
            "post-import inspection uses an unrecorded coordinate retrieval"
        )
    if any(case.missing_mapping_count != 0 for case in report.cases.values()):
        raise ValidationError("post-import inspection still contains missing mappings")
    _validate_mapping_sources(
        snapshot,
        bundle_root,
        original_report,
        report,
        bundle.imported_coordinates,
        manifest,
    )
    # The local parser memo is call-scoped; complete exit authentication still runs.
    load_prefetch_bundle(
        bundle_root,
        snapshot,
        inspection_path,
        expected_manifest_sha256=confirmed_manifest_sha256,
        expected_inventory_sha256=confirmed_inventory_sha256,
        expected_inspection_sha256=confirmed_inspection_sha256,
    )
    return {
        "bundle_id": bundle.bundle_id,
        "prefetch_id": manifest.prefetch_id,
        "imported_object_count": len(manifest.objects),
        "total_coordinate_bytes": manifest.total_size_bytes,
        "postinspection_id": report.inspection_id,
        "postinspection_sha256": bundle.postinspection_sha256,
        "requested_mapping_count": report.requested_mapping_count,
        "missing_mapping_count": 0,
        "network_acquisition_performed": False,
        "cache_import_performed": True,
        "native_control_accepted": False,
    }
