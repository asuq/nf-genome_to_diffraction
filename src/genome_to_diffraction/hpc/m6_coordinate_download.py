"""Acquire the exact missing public PDB prerequisite into new local staging.

Inputs are the complete frozen truthless request snapshot, its authenticated
offline inspection and their confirmed checksums. Only canonical public PDB IDs
are sent to the fixed divided-mmCIF endpoint; no sequence, truth or private input
is submitted. One serial, redirect-disabled attempt per missing ID reuses the
project's bounded HTTP downloader. The pinned Python/Gemmi environment is required.

The output is ``staging_root/bundle/prefetch_manifest.json`` plus its exact gzip
object inventory. Original per-object requests, HTTP metadata and failed partial
bytes remain outside that bundle. Source/inspection, gzip and every originally
missing mapping are validated before the final bundle directory is published.
This helper never writes the shared coordinate cache or executes scientific jobs.

Staging must be new, owned and link-free. A 12 GiB free-space preflight reserves
the complete preparation budget; writes retain 9 GiB for later packaging and
validation. Serial downloader limits conservatively count staging metadata along
with the 3 GiB compressed payload ceiling and 128 MiB per-object ceiling. Every
other local write is checked against the additional-disk and metadata bounds.
Failures propagate, retain staging and cannot trigger an automatic retry/repair.

The canonical prefetch content ID binds every original request/inspection/source
field and the original UTC/HTTP/size/SHA-256 provenance. It is not a persistent
cache-validity claim: the original client must still qualify the complete remote
cache union and reinspection before use. Tests cover authenticated conservation,
fixed URLs, strict redirects, streaming quotas/headroom, partial preservation,
metadata/byte changes and full local mapping qualification without public traffic.
"""

import json
import logging
import os
import shutil
import stat
from dataclasses import asdict
from pathlib import Path

from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_bytes, sha256_file
from genome_to_diffraction.databases.common import StorageLimitError
from genome_to_diffraction.databases.network import download_public_resource
from genome_to_diffraction.hpc.m6_coordinate_prefetch import (
    MAX_ADDITIONAL_DISK_BYTES,
    MAX_COORDINATE_OBJECT_BYTES,
    MAX_COORDINATE_TOTAL_BYTES,
    MAX_PREFETCH_MANIFEST_BYTES,
    PREFETCH_MANIFEST,
    PrefetchedCoordinate,
    PrefetchManifest,
    authenticate_inspection,
    fixed_pdb_url,
    validate_prefetched_mappings,
)
from genome_to_diffraction.hpc.models import ValidationError
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.time import utc_now_iso

_LOGGER = logging.getLogger(__name__)


def _new_staging_parent(staging_root: Path) -> Path:
    if not staging_root.is_absolute() or ".." in staging_root.parts:
        raise ValidationError("coordinate staging path must be absolute and canonical")
    if staging_root.exists() or staging_root.is_symlink():
        raise ValidationError("coordinate staging already exists; preserve it")
    parent = staging_root.parent
    state = parent.lstat()
    if (
        not stat.S_ISDIR(state.st_mode)
        or state.st_uid != os.getuid()
        or parent.resolve(strict=True) != parent
    ):
        raise ValidationError("coordinate staging parent is not owned and link-free")
    return parent


def _stage_bytes(root: Path) -> int:
    """Measure the owned tree without ignoring missing or unsafe state."""

    pending = [root]
    total = 0
    while pending:
        directory = pending.pop()
        state = directory.lstat()
        if not stat.S_ISDIR(state.st_mode) or state.st_uid != os.getuid():
            raise ValidationError("coordinate staging contains an unsafe directory")
        with os.scandir(directory) as entries:
            for entry in entries:
                record = entry.stat(follow_symlinks=False)
                if record.st_uid != os.getuid():
                    raise ValidationError("coordinate staging ownership changed")
                if stat.S_ISDIR(record.st_mode):
                    pending.append(Path(entry.path))
                elif stat.S_ISREG(record.st_mode) and record.st_nlink == 1:
                    total += record.st_size
                else:
                    raise ValidationError("coordinate staging contains a linked file")
    return total


def _headroom(root: Path, minimum: int, *, pending_bytes: int = 0) -> int:
    free = shutil.disk_usage(root).free
    if free - pending_bytes < minimum:
        raise StorageLimitError(
            "coordinate staging lacks measured free-space headroom: "
            f"{free} bytes before a {pending_bytes}-byte write; "
            f"{minimum} bytes must remain"
        )
    return free


def _write_record(root: Path, path: Path, document: object) -> None:
    if path.exists() or path.is_symlink():
        raise ValidationError("coordinate acquisition record already exists")
    payload = (
        json.dumps(
            document, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False
        )
        + "\n"
    ).encode("ascii")
    if len(payload) > MAX_PREFETCH_MANIFEST_BYTES:
        raise StorageLimitError("coordinate acquisition metadata exceeds its byte cap")
    if _stage_bytes(root) + len(payload) > MAX_ADDITIONAL_DISK_BYTES:
        raise StorageLimitError("coordinate acquisition exceeds additional-disk cap")
    _headroom(
        root,
        MAX_ADDITIONAL_DISK_BYTES - MAX_COORDINATE_TOTAL_BYTES,
        pending_bytes=len(payload),
    )
    atomic_write_bytes(path, payload)
    path.chmod(0o444)


def acquire_coordinate_prefetch(
    snapshot: Path,
    inspection_path: Path,
    staging_root: Path,
    *,
    expected_inventory_sha256: str,
    expected_inspection_sha256: str,
    progress: bool = False,
) -> Path:
    """Freeze all missing coordinate objects, never a subset or a cache publication."""

    if type(progress) is not bool:
        raise ValidationError("coordinate acquisition progress must be boolean")
    inventory, report = authenticate_inspection(
        snapshot,
        inspection_path,
        expected_inventory_sha256=expected_inventory_sha256,
        expected_inspection_sha256=expected_inspection_sha256,
    )
    parent = _new_staging_parent(staging_root)
    _headroom(parent, MAX_ADDITIONAL_DISK_BYTES)
    staging_root.mkdir(mode=0o700)
    pending = staging_root / ".pending-bundle"
    incoming = staging_root / "incoming"
    retrievals = staging_root / "retrievals"
    for directory in (pending, pending / "objects", incoming, retrievals):
        directory.mkdir(mode=0o700)
    objects: dict[str, PrefetchedCoordinate] = {}
    completed_bytes = 0
    current_id: str | None = None
    minimum_free = MAX_ADDITIONAL_DISK_BYTES - MAX_COORDINATE_TOTAL_BYTES
    try:
        _write_record(
            staging_root,
            staging_root / "acquisition.json",
            {
                "schema_version": "1.0",
                "adapter_version": "m6-coordinate-staged-acquisition-v1",
                "request_inventory_sha256": expected_inventory_sha256,
                "inspection_sha256": expected_inspection_sha256,
                "missing_pdb_ids": report.missing_pdb_ids,
                "started_at": utc_now_iso(),
                "http_concurrency": 1,
                "attempts_per_object": 1,
                "allow_redirects": False,
                "compressed_total_limit_bytes": MAX_COORDINATE_TOTAL_BYTES,
                "object_limit_bytes": MAX_COORDINATE_OBJECT_BYTES,
                "additional_disk_limit_bytes": MAX_ADDITIONAL_DISK_BYTES,
                "minimum_free_bytes": minimum_free,
            },
        )
        with tqdm(
            total=len(report.missing_pdb_ids),
            desc="Prefetch PDB coordinates",
            unit="entry",
            disable=not progress,
        ) as bar:
            for index, pdb_id in enumerate(report.missing_pdb_ids, start=1):
                current_id = pdb_id
                url = fixed_pdb_url(pdb_id)
                source = incoming / f"{pdb_id.lower()}.cif.gz"
                _write_record(
                    staging_root,
                    retrievals / f"{pdb_id.lower()}.request.json",
                    {
                        "pdb_id": pdb_id,
                        "requested_url": url,
                        "requested_at": utc_now_iso(),
                    },
                )
                used = _stage_bytes(staging_root)
                if used >= MAX_COORDINATE_TOTAL_BYTES:
                    raise StorageLimitError(
                        "coordinate acquisition staging cap is exhausted"
                    )
                _headroom(staging_root, minimum_free)
                _LOGGER.info(
                    "coordinate prefetch object started",
                    extra={
                        "pdb_id": pdb_id,
                        "object_number": index,
                        "object_count": len(report.missing_pdb_ids),
                        "completed_bytes": completed_bytes,
                    },
                )
                # Serial calls are essential: the downloader's inactive-byte
                # snapshot is not a cross-process global-quota reservation.
                metadata = download_public_resource(
                    url,
                    source,
                    storage_root=staging_root,
                    storage_limit_bytes=min(
                        MAX_COORDINATE_TOTAL_BYTES, used + MAX_COORDINATE_OBJECT_BYTES
                    ),
                    minimum_free_bytes=minimum_free,
                    progress=progress,
                    retries=1,
                    allow_redirects=False,
                )
                retrieved_at = utc_now_iso()
                _write_record(
                    staging_root,
                    retrievals / f"{pdb_id.lower()}.retrieval.json",
                    {
                        "pdb_id": pdb_id,
                        "retrieved_at": retrieved_at,
                        **asdict(metadata),
                    },
                )
                state = source.lstat()
                if (
                    not stat.S_ISREG(state.st_mode)
                    or state.st_uid != os.getuid()
                    or state.st_nlink != 1
                    or metadata.requested_url != url
                    or metadata.url != url
                    or type(metadata.size_bytes) is not int
                    or not 0 < metadata.size_bytes <= MAX_COORDINATE_OBJECT_BYTES
                    or state.st_size != metadata.size_bytes
                    or sha256_file(source) != metadata.sha256
                ):
                    raise ValidationError(
                        "downloaded coordinate bytes or fixed-URL provenance changed"
                    )
                completed_bytes += metadata.size_bytes
                if completed_bytes > MAX_COORDINATE_TOTAL_BYTES:
                    raise StorageLimitError(
                        "coordinate payload exceeds the total compressed cap"
                    )
                relative = f"objects/{pdb_id.lower()}.cif.gz"
                objects[pdb_id] = PrefetchedCoordinate.model_validate(
                    {
                        "relative_path": relative,
                        "requested_url": metadata.requested_url,
                        "source_url": metadata.url,
                        "retrieved_at": retrieved_at,
                        "etag": metadata.etag,
                        "last_modified": metadata.last_modified,
                        "content_type": metadata.content_type,
                        "sha256": metadata.sha256,
                        "size_bytes": metadata.size_bytes,
                    },
                    strict=True,
                )
                source.rename(pending / relative)
                _LOGGER.info(
                    "coordinate prefetch object completed",
                    extra={
                        "pdb_id": pdb_id,
                        "object_number": index,
                        "object_count": len(report.missing_pdb_ids),
                        "object_size_bytes": metadata.size_bytes,
                        "completed_bytes": completed_bytes,
                    },
                )
                bar.update(1)
        manifest = PrefetchManifest(
            schema_version="1.0",
            adapter_version="m6-coordinate-prefetch-v1",
            request_run_id=inventory.run_id,
            producer_commit=inventory.producer_commit,
            request_inventory_sha256=expected_inventory_sha256,
            request_inventory_id=inventory.inventory_id,
            inspection_sha256=expected_inspection_sha256,
            inspection_id=report.inspection_id,
            database_manifest_sha256=inventory.database_manifest_sha256,
            objects=objects,
            total_size_bytes=completed_bytes,
            prefetch_id="pending",
        )
        manifest = manifest.model_copy(
            update={
                "prefetch_id": content_id(
                    "m6prefetch_",
                    manifest.model_dump(mode="json", exclude={"prefetch_id"}),
                )
            }
        )
        manifest_path = pending / PREFETCH_MANIFEST
        _write_record(staging_root, manifest_path, manifest.model_dump(mode="json"))
        manifest_sha256 = sha256_file(manifest_path)
        _headroom(staging_root, minimum_free)
        _LOGGER.info(
            "coordinate prefetch complete mapping qualification started",
            extra={"object_count": len(objects), "completed_bytes": completed_bytes},
        )
        validate_prefetched_mappings(
            pending,
            snapshot,
            inspection_path,
            expected_manifest_sha256=manifest_sha256,
            expected_inventory_sha256=expected_inventory_sha256,
            expected_inspection_sha256=expected_inspection_sha256,
        )
        if _stage_bytes(staging_root) > MAX_ADDITIONAL_DISK_BYTES:
            raise StorageLimitError("coordinate staging exceeds additional-disk cap")
        _headroom(staging_root, minimum_free)
        for path in (pending / "objects").iterdir():
            path.chmod(0o444)
        destination = staging_root / "bundle"
        if destination.exists() or destination.is_symlink():
            raise ValidationError("coordinate prefetch bundle already exists")
        pending.rename(destination)
        _LOGGER.info(
            "coordinate prefetch bundle qualified",
            extra={
                "object_count": len(objects),
                "completed_bytes": completed_bytes,
                "prefetch_id": manifest.prefetch_id,
            },
        )
        return destination / PREFETCH_MANIFEST
    except BaseException:
        _LOGGER.exception(
            "coordinate prefetch failed; preserve staged evidence",
            extra={"pdb_id": current_id, "staging_root": str(staging_root)},
        )
        raise
