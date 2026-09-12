"""Bounded request upload and authenticated offline inspection response.

Only original producer files from a confirmed complete request snapshot are sent.
The response contains exactly two regular JSON files, authenticated against the
owned source/run, database, request inventory and every ordered selected hit.
Missing and cached mappings remain distinct; this is neither model acquisition
nor native scientific acceptance. No external executable or network runs here.
Python comes from the locked project runtime. Report IDs bind observed state,
not a persistent cache-validity promise. Boundary tests cover mutation, unsafe
archives, conservation and absence-only publication by the original controller.
"""

import hashlib
import io
import re
import tarfile
from pathlib import Path
from typing import Literal

from pydantic import Field

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.hpc.m6_coordinate_cache import (
    _frozen_file,
    _Inventory,
    load_frozen_request_inventory,
)
from genome_to_diffraction.hpc.m6_coordinate_requests import (
    CASES,
    COLLECTION,
    _Collection,
)
from genome_to_diffraction.hpc.models import (
    MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES,
    MAX_REVIEW_ARTIFACT_FILE_BYTES,
    MAX_REVIEW_ARTIFACT_TOTAL_BYTES,
    LocalRunRecord,
    ValidationError,
)
from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex, UtcTimestamp
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.schemas.results import StructuralSearchHit
from genome_to_diffraction.structure_search.pdb_coordinates import _read_jsonl


class _Mapping(ContractModel):
    hit_id: str
    sequence_group_id: str
    pdb_id: str
    target_chain_or_entity: str
    target_sequence_sha256: Sha256Hex
    target_sequence_length: int = Field(gt=0)
    status: Literal["cached", "missing"]
    coordinate_sha256: Sha256Hex | None
    metadata_sha256: Sha256Hex | None
    entity_id: str | None
    source_sequence_sha256: Sha256Hex | None


class _Case(ContractModel):
    catalogue_key: Sha256Hex
    requested_mapping_count: int = Field(ge=0)
    cached_mapping_count: int = Field(ge=0)
    missing_mapping_count: int = Field(ge=0)
    missing_pdb_ids: list[str]
    mappings: list[_Mapping]


class _Coordinate(ContractModel):
    provider: Literal["pdb"]
    source_id: str
    requested_url: str
    source_url: str
    retrieved_at: str
    etag: str | None
    last_modified: str | None
    content_type: str | None
    object_sha256: Sha256Hex
    size_bytes: int = Field(gt=0)
    object_relative_path: str
    metadata_relative_path: str
    metadata_sha256: Sha256Hex


class _Report(ContractModel):
    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-coordinate-cache-inspection-v1"]
    request_run_id: str
    producer_commit: str
    request_inventory_id: str
    request_inventory_sha256: Sha256Hex
    database_manifest_sha256: Sha256Hex
    coordinate_cache_database_id: str
    requested_mapping_count: int = Field(ge=0)
    distinct_pdb_count: int = Field(ge=0)
    missing_pdb_ids: list[str]
    cached_coordinates: dict[str, _Coordinate]
    cases: dict[str, _Case]
    network_acquisition_performed: Literal[False]
    cache_import_performed: Literal[False]
    inspection_id: str


class _Bundle(ContractModel):
    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-coordinate-inspection-bundle-v1"]
    run_id: str
    commit: str
    request_run_id: str
    producer_commit: str
    request_archive_sha256: Sha256Hex
    request_archive_size_bytes: int = Field(gt=0)
    request_inventory_sha256: Sha256Hex
    request_inventory_id: str
    database_manifest_sha256: Sha256Hex
    inspection_sha256: Sha256Hex
    inspection_size_bytes: int = Field(gt=0, le=MAX_REVIEW_ARTIFACT_FILE_BYTES)
    inspection_id: str
    inspected_at: UtcTimestamp
    network_acquisition_performed: Literal[False]
    cache_import_performed: Literal[False]
    bundle_id: str


def build_request_archive(
    snapshot: Path,
    archive: Path,
    *,
    record: LocalRunRecord,
    confirmed_sha256: str,
) -> _Inventory:
    """Package only original bytes, with no caller-controlled paths or subsets."""

    if re.fullmatch(r"[a-f0-9]{64}", confirmed_sha256) is None:
        raise ValidationError("confirm the exact frozen request inventory checksum")
    inventory = load_frozen_request_inventory(
        snapshot, expected_inventory_sha256=confirmed_sha256
    )
    if inventory.run_id != record.run_id or inventory.producer_commit != record.commit:
        raise ValidationError("coordinate request snapshot ownership binding changed")
    root = snapshot.resolve(strict=True)
    collection = _Collection.model_validate(
        load_json_document(_frozen_file(root, COLLECTION)), strict=True
    )
    if collection.run_id != record.run_id:
        raise ValidationError("coordinate producer collection run binding changed")
    names = sorted(set(collection.files) | {COLLECTION})
    if len(names) > 64 or not set(names) <= set(inventory.input_and_request_sha256):
        raise ValidationError("coordinate original producer inventory is invalid")
    total = 0
    with archive.open("xb") as output, tarfile.open(fileobj=output, mode="w:gz") as tar:
        for name in names:
            path = _frozen_file(root, name)
            size = path.stat().st_size
            total += size
            if (
                size > MAX_REVIEW_ARTIFACT_FILE_BYTES
                or total > MAX_REVIEW_ARTIFACT_TOTAL_BYTES
            ):
                raise ValidationError(
                    "coordinate producer upload exceeds the byte limit"
                )
            # Read each bounded file once so its hash authenticates the sent bytes.
            payload = path.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            if (
                len(payload) != size
                or digest != inventory.input_and_request_sha256[name]
            ):
                raise ValidationError(
                    "coordinate producer changed during upload preparation"
                )
            if name != COLLECTION and (
                collection.files[name].sha256 != digest
                or collection.files[name].size_bytes != size
            ):
                raise ValidationError("coordinate producer collection checksum changed")
            member = tarfile.TarInfo(name)
            member.size = size
            member.mode = 0o444
            tar.addfile(member, io.BytesIO(payload))
    if archive.stat().st_size > MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES:
        raise ValidationError("coordinate producer archive exceeds the byte limit")
    return inventory


def _extract_response(archive: Path, destination: Path) -> None:
    if archive.stat().st_size > MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES:
        raise ValidationError("coordinate inspection archive exceeds the byte limit")
    destination.mkdir(exist_ok=False)
    expected = {"inspection.json", "inspection_bundle.json"}
    seen: set[str] = set()
    total = 0
    with tarfile.open(archive, mode="r|gz") as tar:
        for member in tar:
            total += member.size
            if (
                member.name not in expected
                or member.name in seen
                or not member.isfile()
                or not 0 <= member.size <= MAX_REVIEW_ARTIFACT_FILE_BYTES
                or total > MAX_REVIEW_ARTIFACT_TOTAL_BYTES
            ):
                raise ValidationError(
                    "unsafe or oversized coordinate inspection member"
                )
            seen.add(member.name)
            source = tar.extractfile(member)
            if source is None:
                raise ValidationError("unreadable coordinate inspection member")
            with (destination / member.name).open("xb") as output:
                while data := source.read(1024 * 1024):
                    output.write(data)
    if seen != expected:
        raise ValidationError("coordinate inspection response inventory is incomplete")


def _validate_mappings(report: _Report, inventory: _Inventory, snapshot: Path) -> None:
    if set(report.cases) != set(CASES):
        raise ValidationError("coordinate inspection lacks the fixed two cases")
    all_missing: set[str] = set()
    used_coordinates: set[str] = set()
    total = 0
    for case_id in CASES:
        case = report.cases[case_id]
        original = inventory.cases[case_id]
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
        if (
            case.catalogue_key != original.catalogue_key
            or len(case.mappings) != len(hits)
            or len(hits) != original.requested_mapping_count
            or case.requested_mapping_count != len(hits)
        ):
            raise ValidationError("coordinate inspection case conservation changed")
        missing: set[str] = set()
        missing_count = 0
        selected_objects: dict[str, tuple[str | None, str | None]] = {}
        for item, hit in zip(case.mappings, hits, strict=True):
            if (
                item.hit_id != hit.hit_id
                or item.sequence_group_id != hit.sequence_group_id
                or item.pdb_id != str(hit.pdb_id).upper()
                or item.target_chain_or_entity != hit.target_chain_or_entity
                or item.target_sequence_sha256
                != hit.raw_metrics["target_sequence_sha256"]
                or item.target_sequence_length
                != hit.raw_metrics["target_sequence_length"]
            ):
                raise ValidationError(
                    "coordinate inspection ordered request mapping changed"
                )
            selected = (item.coordinate_sha256, item.metadata_sha256)
            if selected_objects.setdefault(item.pdb_id, selected) != selected:
                raise ValidationError(
                    "coordinate inspection mixes objects for one case entry"
                )
            fields = (
                item.coordinate_sha256,
                item.metadata_sha256,
                item.entity_id,
                item.source_sequence_sha256,
            )
            if item.status == "missing":
                if any(value is not None for value in fields):
                    raise ValidationError(
                        "missing coordinate has fabricated qualification"
                    )
                missing.add(item.pdb_id)
                missing_count += 1
            else:
                if any(value is None or value == "" for value in fields):
                    raise ValidationError("cached coordinate lacks its qualification")
                coordinate = report.cached_coordinates.get(str(item.metadata_sha256))
                if (
                    coordinate is None
                    or coordinate.metadata_sha256 != item.metadata_sha256
                    or coordinate.object_sha256 != item.coordinate_sha256
                    or coordinate.source_id.upper() != item.pdb_id
                    or item.source_sequence_sha256 != item.target_sequence_sha256
                ):
                    raise ValidationError("cached coordinate record binding changed")
                metadata = coordinate.model_dump(
                    exclude={"metadata_relative_path", "metadata_sha256"}
                ) | {"schema_version": "1.0"}
                metadata_id = canonical_digest(metadata)
                digest = coordinate.object_sha256
                if (
                    coordinate.object_relative_path
                    != f"pdb/objects/{digest[:2]}/{digest}.cif.gz"
                    or coordinate.metadata_relative_path
                    != f"pdb/metadata/{item.pdb_id.lower()}/{metadata_id}.json"
                ):
                    raise ValidationError(
                        "cached coordinate qualification paths changed"
                    )
                used_coordinates.add(str(item.metadata_sha256))
        if (
            case.missing_pdb_ids != sorted(missing)
            or case.missing_mapping_count != missing_count
            or case.cached_mapping_count != len(hits) - missing_count
        ):
            raise ValidationError(
                "coordinate inspection missing/cached conservation changed"
            )
        total += len(hits)
        all_missing.update(missing)
    if (
        report.requested_mapping_count != total
        or report.distinct_pdb_count != inventory.distinct_pdb_count
        or report.missing_pdb_ids != sorted(all_missing)
        or set(report.cached_coordinates) != used_coordinates
    ):
        raise ValidationError("coordinate inspection global conservation changed")


def validate_inspection_response(
    archive: Path,
    destination: Path,
    *,
    snapshot: Path,
    record: LocalRunRecord,
    request_record: LocalRunRecord,
    request_archive: Path,
    confirmed_sha256: str,
) -> dict[str, object]:
    """Extract and authenticate both report files before the caller publishes."""

    inventory = load_frozen_request_inventory(
        snapshot, expected_inventory_sha256=confirmed_sha256
    )
    _extract_response(archive, destination)
    report_path = destination / "inspection.json"
    bundle_path = destination / "inspection_bundle.json"
    report = _Report.model_validate_json(report_path.read_bytes())
    bundle = _Bundle.model_validate_json(bundle_path.read_bytes())
    raw_bundle = load_json_document(bundle_path)
    assert isinstance(raw_bundle, dict)
    if bundle.bundle_id != content_id(
        "m6inspect_",
        {key: value for key, value in raw_bundle.items() if key != "bundle_id"},
    ):
        raise ValidationError("coordinate inspection bundle identity changed")
    if report.inspection_id != content_id(
        "m6cache_", report.model_dump(mode="json", exclude={"inspection_id"})
    ):
        raise ValidationError("coordinate inspection report identity changed")
    for value in (bundle, report):
        if (
            value.request_run_id != request_record.run_id
            or value.producer_commit != request_record.commit
            or value.request_inventory_sha256 != confirmed_sha256
            or value.request_inventory_id != inventory.inventory_id
            or value.database_manifest_sha256 != inventory.database_manifest_sha256
        ):
            raise ValidationError(
                "coordinate inspection request/source/database binding changed"
            )
    if (
        bundle.run_id != record.run_id
        or bundle.commit != record.commit
        or bundle.request_archive_sha256 != sha256_file(request_archive)
        or bundle.request_archive_size_bytes != request_archive.stat().st_size
        or bundle.inspection_sha256 != sha256_file(report_path)
        or bundle.inspection_size_bytes != report_path.stat().st_size
        or bundle.inspection_id != report.inspection_id
    ):
        raise ValidationError(
            "coordinate inspection archive/run/report binding changed"
        )
    _validate_mappings(report, inventory, snapshot)
    return {
        "inspection_id": report.inspection_id,
        "bundle_id": bundle.bundle_id,
        "inspection_sha256": bundle.inspection_sha256,
        "request_inventory_sha256": confirmed_sha256,
        "distinct_pdb_count": report.distinct_pdb_count,
        "missing_pdb_count": len(report.missing_pdb_ids),
        "requested_mapping_count": report.requested_mapping_count,
        "cases": {
            case_id: case.model_dump(exclude={"mappings", "missing_pdb_ids"})
            | {"missing_pdb_count": len(case.missing_pdb_ids)}
            for case_id, case in report.cases.items()
        },
        "network_acquisition_performed": False,
        "cache_import_performed": False,
    }
