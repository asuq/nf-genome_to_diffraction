"""Authenticate one explicitly confirmed, incomplete M6 acquisition prefix.

The original client supplies owned Marmic run identities, the original truthless
request snapshot and its saved inspection. This read-only helper returns a
content-addressed inventory of every retained file, original retrieval record and
completed coordinate object. It accepts only an original single-attempt staging
tree with a nonempty serial success prefix and the next request interrupted before
any body or retrieval record. A finished bundle, partial body, previous continuation,
unknown file, changed binding or unsafe path fails explicitly. Operator-confirmed
termination is required; directory contents do not establish process termination.
Nonblocking checks reject currently held downloader locks without modifying them.

Python uses the locked project environment; no external command, HTTP operation,
cache publication or scientific selection runs here. Every byte is rehashed at each
entry; no persistent validity cache or retry chain exists. The returned digest must
be explicitly confirmed for a fresh acquisition, which copies rather than mutates
the original evidence and rechecks this inventory before final publication. Full
gzip/entity/SEQRES qualification remains mandatory for the complete new bundle.
Tests cover prefix conservation, provenance, tampering, links, storage bounds,
incomplete/finished state and unchanged retained evidence through continuation.
"""

import fcntl
import hashlib
import os
import stat
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.hpc.m6_coordinate_prefetch import (
    MAX_ADDITIONAL_DISK_BYTES,
    MAX_COORDINATE_OBJECT_BYTES,
    MAX_COORDINATE_TOTAL_BYTES,
    MAX_PREFETCH_MANIFEST_BYTES,
    PrefetchedCoordinate,
    authenticate_inspection,
    fixed_pdb_url,
)
from genome_to_diffraction.hpc.models import LocalRunRecord, ValidationError
from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.io import load_json_document


def _utc_text(value: str) -> str:
    if datetime.fromisoformat(value).utcoffset() != timedelta(0):
        raise ValueError("retained acquisition timestamp must be explicit UTC text")
    return value


RecordedUtc = Annotated[str, AfterValidator(_utc_text)]


class _Acquisition(ContractModel):
    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-coordinate-staged-acquisition-v1"]
    request_inventory_sha256: Sha256Hex
    inspection_sha256: Sha256Hex
    missing_pdb_ids: list[str]
    started_at: RecordedUtc
    http_concurrency: int
    attempts_per_object: int
    allow_redirects: bool
    compressed_total_limit_bytes: int
    object_limit_bytes: int
    additional_disk_limit_bytes: int
    minimum_free_bytes: int


class _Request(ContractModel):
    pdb_id: str
    requested_url: str
    requested_at: RecordedUtc


class _Retrieval(ContractModel):
    pdb_id: str
    requested_url: str
    url: str
    retrieved_at: RecordedUtc
    etag: str | None
    last_modified: str | None
    content_type: str | None
    size_bytes: int = Field(gt=0, le=MAX_COORDINATE_OBJECT_BYTES)
    sha256: Sha256Hex


class RetainedFile(ContractModel):
    """Frozen byte identity of one regular original staging file."""

    size_bytes: int = Field(ge=0, le=MAX_PREFETCH_MANIFEST_BYTES)
    sha256: Sha256Hex


class RetainedPrefetch(ContractModel):
    """Original run and complete byte inventory bound to the retained prefix."""

    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-coordinate-retained-prefetch-v1"]
    run_id: str
    commit: str
    owner_id: str
    request_run_id: str
    producer_commit: str
    request_owner_id: str
    request_inventory_sha256: Sha256Hex
    inspection_sha256: Sha256Hex
    files: dict[str, RetainedFile]
    objects: dict[str, PrefetchedCoordinate]
    failed_request_pdb_id: str
    total_coordinate_bytes: int = Field(gt=0, le=MAX_COORDINATE_TOTAL_BYTES)
    allocated_bytes: int = Field(gt=0, le=MAX_COORDINATE_TOTAL_BYTES)
    retained_id: str

    def checksum(self) -> str:
        """Return the deterministic digest explicitly confirmed by the caller."""

        return canonical_digest(self.model_dump(mode="json"))


def allocated_staging_bytes(root: Path) -> int:
    """Count allocated bytes in an owned, link-free local staging tree."""

    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValidationError("coordinate staging root is not canonical")
    pending = [root]
    total = 0
    while pending:
        path = pending.pop()
        record = path.lstat()
        if record.st_uid != os.getuid():
            raise ValidationError("coordinate staging ownership changed")
        if stat.S_ISDIR(record.st_mode):
            pending.extend(path.iterdir())
        elif not stat.S_ISREG(record.st_mode) or record.st_nlink != 1:
            raise ValidationError("coordinate staging contains linked or unsafe state")
        total += max(
            record.st_size if stat.S_ISREG(record.st_mode) else 0,
            record.st_blocks * 512,
        )
    return total


def _tree(root: Path) -> tuple[dict[str, RetainedFile], int]:
    allocated = allocated_staging_bytes(root)
    if allocated > MAX_COORDINATE_TOTAL_BYTES:
        raise ValidationError("retained staging exceeds its original bounded allowance")
    directories = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()
    }
    if directories != {
        ".pending-bundle",
        ".pending-bundle/objects",
        "incoming",
        "retrievals",
        "tmp",
        "tmp/download-locks",
    }:
        raise ValidationError("retained acquisition is not an original incomplete tree")
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            if path.parent == root / "tmp/download-locks":
                with path.open("rb") as handle:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError as error:
                        raise ValidationError(
                            "retained acquisition still has an active download lock"
                        ) from error
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            if path.stat().st_size > MAX_PREFETCH_MANIFEST_BYTES:
                raise ValidationError("retained acquisition file exceeds its byte cap")
            files[path.relative_to(root).as_posix()] = RetainedFile(
                size_bytes=path.stat().st_size, sha256=sha256_file(path)
            )
    return files, allocated


def inspect_retained_prefetch(
    root: Path,
    snapshot: Path,
    inspection_path: Path,
    *,
    record: LocalRunRecord,
    request_record: LocalRunRecord,
    expected_inventory_sha256: str,
    expected_inspection_sha256: str,
) -> RetainedPrefetch:
    """Rehash and qualify exactly the reusable prefix; never infer HTTP success."""

    inventory, report = authenticate_inspection(
        snapshot,
        inspection_path,
        expected_inventory_sha256=expected_inventory_sha256,
        expected_inspection_sha256=expected_inspection_sha256,
    )
    if (
        record.run_id == request_record.run_id
        or record.site_id != "marmic"
        or request_record.site_id != "marmic"
        or record.profile != "m6-native-control"
        or request_record.profile != "m6-native-control"
        or inventory.run_id != request_record.run_id
        or inventory.producer_commit != request_record.commit
    ):
        raise ValidationError("retained acquisition requires the bound Marmic controls")
    files, allocated = _tree(root)
    if "acquisition.json" not in files:
        raise ValidationError(
            "retained acquisition lacks its original acquisition record"
        )
    acquisition = _Acquisition.model_validate(
        load_json_document(root / "acquisition.json"), strict=True
    )
    if (
        acquisition.request_inventory_sha256 != expected_inventory_sha256
        or acquisition.inspection_sha256 != expected_inspection_sha256
        or acquisition.missing_pdb_ids != report.missing_pdb_ids
        or acquisition.http_concurrency != 1
        or acquisition.attempts_per_object != 1
        or acquisition.allow_redirects is not False
        or acquisition.compressed_total_limit_bytes != MAX_COORDINATE_TOTAL_BYTES
        or acquisition.object_limit_bytes != MAX_COORDINATE_OBJECT_BYTES
        or acquisition.additional_disk_limit_bytes != MAX_ADDITIONAL_DISK_BYTES
        or acquisition.minimum_free_bytes
        != MAX_ADDITIONAL_DISK_BYTES - MAX_COORDINATE_TOTAL_BYTES
    ):
        raise ValidationError("retained acquisition input or resource policy changed")
    paths = sorted(
        name for name in files if name.startswith(".pending-bundle/objects/")
    )
    count = len(paths)
    if not 0 < count < len(report.missing_pdb_ids):
        raise ValidationError(
            "retained acquisition must contain a proper nonempty prefix"
        )
    prefix = report.missing_pdb_ids[:count]
    failed_id = report.missing_pdb_ids[count]
    expected_paths = [
        f".pending-bundle/objects/{pdb_id.lower()}.cif.gz" for pdb_id in prefix
    ]
    if paths != expected_paths:
        raise ValidationError(
            "retained objects are not the exact serial inventory prefix"
        )
    expected = {"acquisition.json", *paths}
    objects = {}
    for pdb_id in [*prefix, failed_id]:
        token = pdb_id.lower()
        url = fixed_pdb_url(pdb_id)
        request_name = f"retrievals/{token}.request.json"
        destination = root / "incoming" / f"{token}.cif.gz"
        lock_name = hashlib.sha256(str(destination).encode("utf-8")).hexdigest()
        lock_path = f"tmp/download-locks/{lock_name}.lock"
        if (
            request_name not in files
            or lock_path not in files
            or files[lock_path].size_bytes
        ):
            raise ValidationError(
                "retained request/lock evidence is missing or changed"
            )
        expected.update((request_name, lock_path))
        request = _Request.model_validate(
            load_json_document(root / request_name), strict=True
        )
        if request.pdb_id != pdb_id or request.requested_url != url:
            raise ValidationError(
                "retained request does not use its fixed public PDB URL"
            )
        if datetime.fromisoformat(request.requested_at) < datetime.fromisoformat(
            acquisition.started_at
        ):
            raise ValidationError("retained request predates its acquisition")
        if pdb_id == failed_id:
            continue
        retrieval_name = f"retrievals/{token}.retrieval.json"
        if retrieval_name not in files:
            raise ValidationError(
                "retained completed object lacks retrieval provenance"
            )
        expected.add(retrieval_name)
        retrieval = _Retrieval.model_validate(
            load_json_document(root / retrieval_name), strict=True
        )
        coordinate = files[f".pending-bundle/objects/{token}.cif.gz"]
        if (
            retrieval.pdb_id != pdb_id
            or retrieval.requested_url != url
            or retrieval.url != url
            or retrieval.size_bytes != coordinate.size_bytes
            or retrieval.sha256 != coordinate.sha256
            or datetime.fromisoformat(retrieval.retrieved_at)
            < datetime.fromisoformat(request.requested_at)
        ):
            raise ValidationError(
                "retained coordinate bytes or retrieval provenance changed"
            )
        objects[pdb_id] = PrefetchedCoordinate(
            relative_path=f"objects/{token}.cif.gz",
            requested_url=url,
            source_url=url,
            retrieved_at=retrieval.retrieved_at,
            etag=retrieval.etag,
            last_modified=retrieval.last_modified,
            content_type=retrieval.content_type,
            sha256=coordinate.sha256,
            size_bytes=coordinate.size_bytes,
        )
    if set(files) != expected:
        raise ValidationError("retained acquisition has unexpected or partial evidence")
    document = RetainedPrefetch(
        schema_version="1.0",
        adapter_version="m6-coordinate-retained-prefetch-v1",
        run_id=record.run_id,
        commit=record.commit,
        owner_id=record.owner_id,
        request_run_id=request_record.run_id,
        producer_commit=request_record.commit,
        request_owner_id=request_record.owner_id,
        request_inventory_sha256=expected_inventory_sha256,
        inspection_sha256=expected_inspection_sha256,
        files=files,
        objects=objects,
        failed_request_pdb_id=failed_id,
        total_coordinate_bytes=sum(row.size_bytes for row in objects.values()),
        allocated_bytes=allocated,
        retained_id="pending",
    )
    document = document.model_copy(
        update={
            "retained_id": content_id(
                "m6coordretained_",
                document.model_dump(mode="json", exclude={"retained_id"}),
            )
        }
    )
    verify_retained_prefetch(root, document)
    return document


def verify_retained_prefetch(root: Path, retained: RetainedPrefetch) -> None:
    """Reject changed retained bytes or paths before/after copying and acquisition."""

    files, allocated = _tree(root)
    if files != retained.files or allocated != retained.allocated_bytes:
        raise ValidationError(
            "retained acquisition changed after its confirmed inspection"
        )


def load_retained_prefetch(path: Path, confirmed_sha256: str) -> RetainedPrefetch:
    """Authenticate the immutable retained-evidence manifest saved with new staging."""

    if (
        path.is_symlink()
        or not path.is_file()
        or path.resolve(strict=True) != path
        or path.stat().st_nlink != 1
        or not 0 < path.stat().st_size <= MAX_PREFETCH_MANIFEST_BYTES
    ):
        raise ValidationError(
            "retained prefetch manifest is unsafe or exceeds its byte cap"
        )
    retained = RetainedPrefetch.model_validate(load_json_document(path), strict=True)
    if retained.checksum() != confirmed_sha256 or retained.retained_id != content_id(
        "m6coordretained_", retained.model_dump(mode="json", exclude={"retained_id"})
    ):
        raise ValidationError("retained prefetch manifest content identity changed")
    return retained
