"""Extract only the two fixed M6 coordinate-import USTAR wire formats.

The input is either a bounded plain prefetch archive (one manifest and every
expected PDB gzip object) or a bounded gzip response (the two fixed JSON files).
Output is an absent, link-free destination populated with exactly those files.
These are transport checks, not scientific mapping or manifest authentication;
the caller must still perform the complete checksum/source/mapping qualification.

Only regular USTAR headers are accepted. PAX/GNU extensions and every link or
directory record fail before any declared payload is read. Header checksums,
per-file and total limits, zero padding, end blocks, gzip integrity and current
free space are checked while streaming at most 1 MiB per read. No decompressed
archive is persisted. Failed attempts remain as partial evidence, never repaired
or implicitly removed. No external commands or network run; Python is pinned by
the project lock. There is no cache key or persistent validity promise. Tests
cover both round trips, extension bombs, closed inventories and failure bounds.
"""

import gzip
import shutil
import tarfile
import zlib
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO

from genome_to_diffraction.hpc.m6_coordinate_prefetch import (
    MAX_COORDINATE_OBJECT_BYTES,
    MAX_COORDINATE_TOTAL_BYTES,
    MAX_PREFETCH_ARCHIVE_BYTES,
    MAX_PREFETCH_MANIFEST_BYTES,
    PREFETCH_MANIFEST,
    fixed_pdb_url,
)
from genome_to_diffraction.hpc.models import (
    MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES,
    MAX_REVIEW_ARTIFACT_FILE_BYTES,
    MAX_REVIEW_ARTIFACT_TOTAL_BYTES,
    ValidationError,
)

_BLOCK = 512
_RECORD = 10240
_CHUNK = 1024 * 1024
_ZERO_BLOCK = bytes(_BLOCK)


def _read(stream: BinaryIO | gzip.GzipFile, size: int) -> bytes:
    if not 0 < size <= _CHUNK:
        raise AssertionError("coordinate archive read lost its fixed bound")
    try:
        return stream.read(size)
    except (OSError, EOFError, zlib.error) as error:
        raise ValidationError(
            "coordinate archive stream is corrupt or truncated"
        ) from error


def _exact(stream: BinaryIO | gzip.GzipFile, size: int) -> bytes:
    block = _read(stream, size)
    if len(block) != size:
        raise ValidationError("coordinate archive stream is truncated")
    return block


def _free_space(directory: Path, required_bytes: int) -> None:
    # Aggregate reservations are the caller's responsibility. Already received
    # archive bytes must not trigger a fresh full-run reservation during extraction.
    if shutil.disk_usage(directory).free < required_bytes:
        raise ValidationError("insufficient free space for coordinate archive member")


def _prepare(archive: Path, destination: Path, maximum: int, *, prefetch: bool) -> None:
    if (
        not archive.is_absolute()
        or archive.is_symlink()
        or not archive.is_file()
        or archive.resolve(strict=True) != archive
        or archive.stat().st_nlink != 1
        or not 0 < archive.stat().st_size <= maximum
    ):
        raise ValidationError("coordinate archive is unsafe or exceeds its byte limit")
    if (
        not destination.is_absolute()
        or destination.exists()
        or destination.is_symlink()
        or not destination.parent.is_dir()
        or destination.parent.resolve(strict=True) != destination.parent
    ):
        raise ValidationError(
            "coordinate archive destination must be absent and link-free"
        )
    destination.mkdir()
    if prefetch:
        (destination / "objects").mkdir()


def _header(block: bytes) -> tarfile.TarInfo:
    if block[257:265] != b"ustar\x0000":
        raise ValidationError("coordinate archive header is not regular USTAR")
    try:
        member = tarfile.TarInfo.frombuf(block, encoding="ascii", errors="strict")
    except (tarfile.HeaderError, UnicodeError, ValueError) as error:
        raise ValidationError("coordinate archive header is invalid") from error
    if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE) or member.linkname:
        raise ValidationError(
            "coordinate archive extensions, links and non-files are forbidden"
        )
    return member


def _extract(
    stream: BinaryIO | gzip.GzipFile,
    destination: Path,
    *,
    names: dict[str, int],
    payload_limit: int,
    stream_limit: int,
    prefetch: bool,
) -> None:
    seen: set[str] = set()
    total = 0
    coordinates = 0
    consumed = 0
    while True:
        if consumed + _BLOCK > stream_limit:
            raise ValidationError(
                "coordinate archive expanded stream exceeds its byte limit"
            )
        block = _exact(stream, _BLOCK)
        consumed += _BLOCK
        if block == _ZERO_BLOCK:
            if (
                consumed + _BLOCK > stream_limit
                or _exact(stream, _BLOCK) != _ZERO_BLOCK
            ):
                raise ValidationError("coordinate archive requires two zero end blocks")
            consumed += _BLOCK
            # The fixed senders use tarfile's 10,240-byte records. At most one
            # record's remaining zero padding is admitted, never arbitrary tails.
            padding = (-consumed) % _RECORD
            if consumed + padding > stream_limit:
                raise ValidationError(
                    "coordinate archive padding exceeds its byte limit"
                )
            if padding and any(_exact(stream, padding)):
                raise ValidationError("coordinate archive has nonzero end padding")
            if _read(stream, 1):
                raise ValidationError("coordinate archive has trailing data")
            if seen != set(names):
                raise ValidationError("coordinate archive file inventory is incomplete")
            return
        member = _header(block)
        if member.name not in names or member.name in seen:
            raise ValidationError(
                "coordinate archive has an unknown or duplicate member"
            )
        total += member.size
        if prefetch and member.name != PREFETCH_MANIFEST:
            coordinates += member.size
        if (
            not 0 < member.size <= names[member.name]
            or total > payload_limit
            or coordinates > MAX_COORDINATE_TOTAL_BYTES
        ):
            raise ValidationError("coordinate archive member exceeds its byte limit")
        padding = (-member.size) % _BLOCK
        if consumed + member.size + padding + 2 * _BLOCK > stream_limit:
            raise ValidationError(
                "coordinate archive expanded stream exceeds its byte limit"
            )
        target = destination / member.name
        if target.parent.resolve(strict=True) != target.parent:
            raise ValidationError("coordinate archive member parent is not link-free")
        _free_space(target.parent, member.size)
        seen.add(member.name)
        with target.open("xb") as output:
            remaining = member.size
            while remaining:
                _free_space(target.parent, remaining)
                payload = _exact(stream, min(remaining, _CHUNK))
                output.write(payload)
                remaining -= len(payload)
                consumed += len(payload)
        if padding and any(_exact(stream, padding)):
            raise ValidationError("coordinate archive member has nonzero padding")
        consumed += padding


def extract_prefetch_archive(
    archive: Path,
    destination: Path,
    *,
    expected_pdb_ids: Sequence[str],
) -> None:
    """Extract the exact plain-USTAR missing-PDB bundle, retaining failures."""

    if len(set(expected_pdb_ids)) != len(expected_pdb_ids):
        raise ValidationError(
            "coordinate archive expected PDB identifiers are duplicated"
        )
    for pdb_id in expected_pdb_ids:
        fixed_pdb_url(pdb_id)
    names = {PREFETCH_MANIFEST: MAX_PREFETCH_MANIFEST_BYTES} | {
        f"objects/{pdb_id.lower()}.cif.gz": MAX_COORDINATE_OBJECT_BYTES
        for pdb_id in expected_pdb_ids
    }
    _prepare(archive, destination, MAX_PREFETCH_ARCHIVE_BYTES, prefetch=True)
    with archive.open("rb") as stream:
        _extract(
            stream,
            destination,
            names=names,
            payload_limit=MAX_COORDINATE_TOTAL_BYTES + MAX_PREFETCH_MANIFEST_BYTES,
            stream_limit=MAX_PREFETCH_ARCHIVE_BYTES,
            prefetch=True,
        )


def extract_import_response_archive(archive: Path, destination: Path) -> None:
    """Extract only the two gzip-USTAR response records, retaining failures."""

    names = {
        "postinspection.json": MAX_REVIEW_ARTIFACT_FILE_BYTES,
        "import_bundle.json": MAX_REVIEW_ARTIFACT_FILE_BYTES,
    }
    _prepare(archive, destination, MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES, prefetch=False)
    with gzip.open(archive, "rb") as stream:
        _extract(
            stream,
            destination,
            names=names,
            payload_limit=MAX_REVIEW_ARTIFACT_TOTAL_BYTES,
            stream_limit=MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES,
            prefetch=False,
        )
