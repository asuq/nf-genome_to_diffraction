"""Concurrent-safe initialisation of the content-addressed coordinate cache.

The cache is initially empty and mutable by design. Provider objects are written
atomically elsewhere; this module creates and verifies only the stable namespace,
lock, temporary-download, metadata, and digest-index layout.
"""

import fcntl
import json
import logging
import os
import re
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import JsonValue
from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.databases.common import DatabaseError
from genome_to_diffraction.ids import canonical_digest

_LOGGER = logging.getLogger("genome_to_diffraction.databases")
_PROVIDERS = ("pdb", "afdb", "esm_atlas")
_PDB_ID = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
_AFDB_MODEL_ID = re.compile(r"^AF-[A-Za-z0-9][A-Za-z0-9._-]{1,198}$")


@dataclass(frozen=True)
class CachedCoordinate:
    """Integrity and provenance record for one cached PDB coordinate object."""

    provider: str
    source_id: str
    requested_url: str
    source_url: str
    retrieved_at: str
    etag: str | None
    last_modified: str | None
    content_type: str | None
    object_sha256: str
    size_bytes: int
    object_relative_path: str
    metadata_relative_path: str
    metadata_sha256: str

    def as_json(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible qualification record."""

        return asdict(self)


@contextmanager
def exclusive_lock(
    path: Path, *, timeout_seconds: float = 30.0, progress: bool = True
) -> Iterator[None]:
    """Acquire an automatically released POSIX advisory lock with a timeout."""

    if timeout_seconds <= 0:
        raise ValueError("database lock timeout must be positive")
    started = time.monotonic()
    deadline = time.monotonic() + timeout_seconds
    path.parent.mkdir(parents=True, exist_ok=True)
    _LOGGER.info(
        "waiting for database lock",
        extra={"lock_path": str(path), "timeout_seconds": timeout_seconds},
    )
    with (
        path.open("a+", encoding="ascii") as handle,
        tqdm(
            total=max(int(timeout_seconds * 10), 1),
            desc=f"Lock {path.name}",
            unit="wait",
            disable=not progress,
        ) as progress_bar,
    ):
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as error:
                if time.monotonic() >= deadline:
                    raise DatabaseError(
                        f"timed out waiting for database lock: {path}"
                    ) from error
                time.sleep(0.1)
                progress_bar.update(1)
        waited_seconds = time.monotonic() - started
        _LOGGER.info(
            "database lock acquired",
            extra={"lock_path": str(path), "waited_seconds": waited_seconds},
        )
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            _LOGGER.info(
                "database lock released",
                extra={"lock_path": str(path)},
            )


def _layout() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "providers": list(_PROVIDERS),
        "object_addressing": "sha256",
        "temporary_suffix": ".partial",
        "metadata_sidecar": "json",
        "lock_strategy": "atomic-create-per-source-id",
    }


def initialise_coordinate_cache(
    root: Path, *, progress: bool = True
) -> tuple[str, int, int]:
    """Create or verify the cache layout and return its digest/count/size."""

    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".initialise.lock"
    layout_path = root / ".cache-layout.json"
    with exclusive_lock(lock_path, progress=progress):
        for provider in _PROVIDERS:
            provider_root = root / provider
            for name in ("objects", "metadata", "tmp", "locks"):
                (provider_root / name).mkdir(parents=True, exist_ok=True)
        (root / "digest_index").mkdir(exist_ok=True)
        layout = _layout()
        if layout_path.exists():
            try:
                existing = json.loads(layout_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise DatabaseError(
                    f"invalid coordinate-cache layout: {error}"
                ) from error
            if existing != layout:
                raise DatabaseError(
                    f"coordinate-cache layout differs from policy: {layout_path}"
                )
        else:
            atomic_write_json(layout_path, layout)
        probe = root / ".write-probe"
        try:
            probe.write_text("probe\n", encoding="ascii")
        finally:
            probe.unlink(missing_ok=True)
    digest = canonical_digest(layout)
    size = layout_path.stat().st_size
    _LOGGER.info(
        "coordinate cache ready",
        extra={"root": str(root), "layout_sha256": digest},
    )
    return digest, 1, size


def verify_coordinate_cache(root: Path) -> tuple[str, int, int]:
    """Verify the cache namespace without creating or repairing missing paths."""

    layout_path = root / ".cache-layout.json"
    required = [root / "digest_index"]
    for provider in _PROVIDERS:
        required.extend(
            root / provider / name for name in ("objects", "metadata", "tmp", "locks")
        )
    missing = [str(path) for path in required if not path.is_dir()]
    if missing:
        raise DatabaseError(
            "coordinate-cache directories are missing: " + ", ".join(missing)
        )
    try:
        existing = json.loads(layout_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatabaseError(f"invalid coordinate-cache layout: {error}") from error
    layout = _layout()
    if existing != layout:
        raise DatabaseError(
            f"coordinate-cache layout differs from policy: {layout_path}"
        )
    return canonical_digest(layout), 1, layout_path.stat().st_size


def _atomic_copy(source: Path, destination: Path, *, progress: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with (
            source.open("rb") as input_handle,
            temporary.open("xb") as output_handle,
            tqdm(
                total=source.stat().st_size,
                desc=f"Cache {destination.name}",
                unit="B",
                unit_scale=True,
                disable=not progress,
            ) as progress_bar,
        ):
            while chunk := input_handle.read(1024 * 1024):
                output_handle.write(chunk)
                progress_bar.update(len(chunk))
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def publish_pdb_coordinate(
    root: Path,
    source: Path,
    *,
    pdb_id: str,
    requested_url: str,
    source_url: str,
    retrieved_at: str,
    etag: str | None,
    last_modified: str | None,
    content_type: str | None,
    progress: bool = True,
) -> CachedCoordinate:
    """Atomically publish one verified public PDB mmCIF object into the cache."""

    verify_coordinate_cache(root)
    if _PDB_ID.fullmatch(pdb_id) is None:
        raise DatabaseError(f"invalid PDB cache source identifier: {pdb_id!r}")
    if not source.is_file() or source.is_symlink() or source.stat().st_size == 0:
        raise DatabaseError(f"PDB coordinate source is missing or unsafe: {source}")
    normalised_id = pdb_id.lower()
    digest = sha256_file(source, progress=progress, logger=_LOGGER)
    size_bytes = source.stat().st_size
    object_relative = Path("pdb") / "objects" / digest[:2] / f"{digest}.cif.gz"
    metadata = {
        "schema_version": "1.0",
        "provider": "pdb",
        "source_id": normalised_id,
        "requested_url": requested_url,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "etag": etag,
        "last_modified": last_modified,
        "content_type": content_type,
        "object_relative_path": object_relative.as_posix(),
        "object_sha256": digest,
        "size_bytes": size_bytes,
    }
    metadata_id = canonical_digest(metadata)
    metadata_relative = Path("pdb") / "metadata" / normalised_id / f"{metadata_id}.json"
    object_path = root / object_relative
    metadata_path = root / metadata_relative
    lock_path = root / "pdb" / "locks" / f"{normalised_id}.lock"
    with exclusive_lock(lock_path, progress=progress):
        if object_path.exists():
            if object_path.is_symlink() or not object_path.is_file():
                raise DatabaseError(f"cached PDB object is unsafe: {object_path}")
            if sha256_file(object_path, progress=progress, logger=_LOGGER) != digest:
                raise DatabaseError(
                    f"cached PDB object checksum mismatch: {object_path}"
                )
        else:
            _atomic_copy(source, object_path, progress=progress)
            if sha256_file(object_path, progress=False) != digest:
                raise DatabaseError(
                    f"published PDB object checksum mismatch: {object_path}"
                )
        index_path = root / "digest_index" / f"{digest}.json"
        atomic_write_json(
            index_path,
            {
                "schema_version": "1.0",
                "provider": "pdb",
                "object_relative_path": object_relative.as_posix(),
                "object_sha256": digest,
                "size_bytes": size_bytes,
            },
        )
        if metadata_path.exists():
            try:
                existing_metadata = json.loads(
                    metadata_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as error:
                raise DatabaseError(
                    f"invalid cached PDB coordinate metadata: {metadata_path}"
                ) from error
            if existing_metadata != metadata:
                raise DatabaseError(
                    f"cached PDB coordinate metadata collision: {metadata_path}"
                )
        else:
            atomic_write_json(metadata_path, metadata)
        metadata_sha256 = sha256_file(metadata_path, progress=False)
    record = CachedCoordinate(
        provider="pdb",
        source_id=normalised_id,
        requested_url=requested_url,
        source_url=source_url,
        retrieved_at=retrieved_at,
        etag=etag,
        last_modified=last_modified,
        content_type=content_type,
        object_sha256=digest,
        size_bytes=size_bytes,
        object_relative_path=object_relative.as_posix(),
        metadata_relative_path=metadata_relative.as_posix(),
        metadata_sha256=metadata_sha256,
    )
    _LOGGER.info(
        "PDB coordinate cached",
        extra={
            "pdb_id": normalised_id,
            "object_sha256": digest,
            "size_bytes": record.size_bytes,
        },
    )
    return record


def publish_afdb_coordinate(
    root: Path,
    source: Path,
    *,
    model_entity_id: str,
    accession: str,
    requested_url: str,
    source_url: str,
    retrieved_at: str,
    source_release: str,
    source_sequence_sha256: str,
    confidence_summary: dict[str, JsonValue],
    etag: str | None,
    last_modified: str | None,
    content_type: str | None,
    progress: bool = True,
) -> CachedCoordinate:
    """Atomically publish one exact-sequence AFDB mmCIF object into the cache."""

    verify_coordinate_cache(root)
    if _AFDB_MODEL_ID.fullmatch(model_entity_id) is None:
        raise DatabaseError(
            f"invalid AFDB model entity identifier: {model_entity_id!r}"
        )
    if not accession or any(character in accession for character in "/\\\0"):
        raise DatabaseError(f"invalid AFDB source accession: {accession!r}")
    if len(source_sequence_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in source_sequence_sha256
    ):
        raise DatabaseError("invalid AFDB source-sequence checksum")
    if not source.is_file() or source.is_symlink() or source.stat().st_size == 0:
        raise DatabaseError(f"AFDB coordinate source is missing or unsafe: {source}")

    digest = sha256_file(source, progress=progress, logger=_LOGGER)
    size_bytes = source.stat().st_size
    object_relative = Path("afdb") / "objects" / digest[:2] / f"{digest}.cif"
    metadata = {
        "schema_version": "1.0",
        "provider": "afdb",
        "source_id": model_entity_id,
        "source_accession": accession,
        "source_release": source_release,
        "source_sequence_sha256": source_sequence_sha256,
        "exact_sequence_match": True,
        "confidence_summary": confidence_summary,
        "license_or_provenance": "AlphaFold DB CC-BY-4.0",
        "requested_url": requested_url,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "etag": etag,
        "last_modified": last_modified,
        "content_type": content_type,
        "object_relative_path": object_relative.as_posix(),
        "object_sha256": digest,
        "size_bytes": size_bytes,
    }
    metadata_id = canonical_digest(metadata)
    metadata_relative = (
        Path("afdb") / "metadata" / model_entity_id / f"{metadata_id}.json"
    )
    object_path = root / object_relative
    metadata_path = root / metadata_relative
    lock_path = root / "afdb" / "locks" / f"{model_entity_id}.lock"
    with exclusive_lock(lock_path, progress=progress):
        if object_path.exists():
            if object_path.is_symlink() or not object_path.is_file():
                raise DatabaseError(f"cached AFDB object is unsafe: {object_path}")
            if sha256_file(object_path, progress=progress, logger=_LOGGER) != digest:
                raise DatabaseError(
                    f"cached AFDB object checksum mismatch: {object_path}"
                )
        else:
            _atomic_copy(source, object_path, progress=progress)
            if sha256_file(object_path, progress=False) != digest:
                raise DatabaseError(
                    f"published AFDB object checksum mismatch: {object_path}"
                )
        index_path = root / "digest_index" / f"{digest}.json"
        expected_index = {
            "schema_version": "1.0",
            "provider": "afdb",
            "object_relative_path": object_relative.as_posix(),
            "object_sha256": digest,
            "size_bytes": size_bytes,
        }
        if index_path.exists():
            try:
                existing_index = json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise DatabaseError(
                    f"invalid coordinate digest index: {index_path}"
                ) from error
            if existing_index != expected_index:
                raise DatabaseError(f"coordinate digest index collision: {index_path}")
        else:
            atomic_write_json(index_path, expected_index)
        if metadata_path.exists():
            try:
                existing_metadata = json.loads(
                    metadata_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as error:
                raise DatabaseError(
                    f"invalid cached AFDB coordinate metadata: {metadata_path}"
                ) from error
            if existing_metadata != metadata:
                raise DatabaseError(
                    f"cached AFDB coordinate metadata collision: {metadata_path}"
                )
        else:
            atomic_write_json(metadata_path, metadata)
        metadata_sha256 = sha256_file(metadata_path, progress=False)

    record = CachedCoordinate(
        provider="afdb",
        source_id=model_entity_id,
        requested_url=requested_url,
        source_url=source_url,
        retrieved_at=retrieved_at,
        etag=etag,
        last_modified=last_modified,
        content_type=content_type,
        object_sha256=digest,
        size_bytes=size_bytes,
        object_relative_path=object_relative.as_posix(),
        metadata_relative_path=metadata_relative.as_posix(),
        metadata_sha256=metadata_sha256,
    )
    _LOGGER.info(
        "AFDB coordinate cached",
        extra={
            "model_entity_id": model_entity_id,
            "source_accession": accession,
            "object_sha256": digest,
            "size_bytes": size_bytes,
        },
    )
    return record


def verify_cached_pdb_coordinate(
    root: Path,
    raw_record: object,
    *,
    full_checksum: bool,
    progress: bool = True,
) -> CachedCoordinate:
    """Verify one recorded cache entry without downloading or repairing it."""

    if not isinstance(raw_record, dict):
        raise DatabaseError("coordinate-cache qualification record is invalid")
    required = {
        "provider",
        "source_id",
        "requested_url",
        "source_url",
        "retrieved_at",
        "etag",
        "last_modified",
        "content_type",
        "object_sha256",
        "size_bytes",
        "object_relative_path",
        "metadata_relative_path",
        "metadata_sha256",
    }
    if set(raw_record) != required:
        raise DatabaseError("coordinate-cache qualification fields are invalid")
    textual = (
        "provider",
        "source_id",
        "requested_url",
        "source_url",
        "retrieved_at",
        "object_sha256",
        "object_relative_path",
        "metadata_relative_path",
        "metadata_sha256",
    )
    nullable_textual = ("etag", "last_modified", "content_type")
    if any(not isinstance(raw_record[key], str) for key in textual) or any(
        raw_record[key] is not None and not isinstance(raw_record[key], str)
        for key in nullable_textual
    ):
        raise DatabaseError("coordinate-cache qualification value types are invalid")
    size_bytes = raw_record["size_bytes"]
    if (
        not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes < 1
    ):
        raise DatabaseError("coordinate-cache qualification size is invalid")

    def optional_text(key: str) -> str | None:
        value = raw_record[key]
        if value is None or isinstance(value, str):
            return value
        raise AssertionError("coordinate-cache optional text was already validated")

    record = CachedCoordinate(
        provider=str(raw_record["provider"]),
        source_id=str(raw_record["source_id"]),
        requested_url=str(raw_record["requested_url"]),
        source_url=str(raw_record["source_url"]),
        retrieved_at=str(raw_record["retrieved_at"]),
        etag=optional_text("etag"),
        last_modified=optional_text("last_modified"),
        content_type=optional_text("content_type"),
        object_sha256=str(raw_record["object_sha256"]),
        size_bytes=size_bytes,
        object_relative_path=str(raw_record["object_relative_path"]),
        metadata_relative_path=str(raw_record["metadata_relative_path"]),
        metadata_sha256=str(raw_record["metadata_sha256"]),
    )
    if record.provider != "pdb" or _PDB_ID.fullmatch(record.source_id) is None:
        raise DatabaseError("coordinate-cache qualification source is invalid")
    digest = record.object_sha256
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise DatabaseError("coordinate-cache qualification digest is invalid")
    if len(record.metadata_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in record.metadata_sha256
    ):
        raise DatabaseError("coordinate-cache metadata digest is invalid")
    expected_object = (
        Path("pdb") / "objects" / digest[:2] / f"{digest}.cif.gz"
    ).as_posix()
    expected_metadata_document = {
        "schema_version": "1.0",
        "provider": record.provider,
        "source_id": record.source_id,
        "requested_url": record.requested_url,
        "source_url": record.source_url,
        "retrieved_at": record.retrieved_at,
        "etag": record.etag,
        "last_modified": record.last_modified,
        "content_type": record.content_type,
        "object_relative_path": record.object_relative_path,
        "object_sha256": record.object_sha256,
        "size_bytes": record.size_bytes,
    }
    metadata_id = canonical_digest(expected_metadata_document)
    expected_metadata = (
        Path("pdb") / "metadata" / record.source_id.lower() / f"{metadata_id}.json"
    ).as_posix()
    if (
        record.object_relative_path != expected_object
        or record.metadata_relative_path != expected_metadata
    ):
        raise DatabaseError("coordinate-cache qualification paths are inconsistent")
    object_path = root / expected_object
    metadata_path = root / expected_metadata
    index_path = root / "digest_index" / f"{digest}.json"
    if (
        not object_path.is_file()
        or object_path.is_symlink()
        or object_path.stat().st_size != record.size_bytes
    ):
        raise DatabaseError("cached PDB coordinate object is missing or inconsistent")
    if not metadata_path.is_file() or metadata_path.is_symlink():
        raise DatabaseError("cached PDB coordinate metadata is missing or unsafe")
    if sha256_file(metadata_path, progress=False) != record.metadata_sha256:
        raise DatabaseError("cached PDB coordinate metadata checksum mismatch")
    try:
        actual_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatabaseError("cached PDB coordinate metadata is invalid") from error
    if actual_metadata != expected_metadata_document:
        raise DatabaseError("cached PDB coordinate metadata is inconsistent")
    expected_index = {
        "schema_version": "1.0",
        "provider": "pdb",
        "object_relative_path": expected_object,
        "object_sha256": digest,
        "size_bytes": record.size_bytes,
    }
    if not index_path.is_file() or index_path.is_symlink():
        raise DatabaseError("cached PDB coordinate digest index is missing or unsafe")
    try:
        actual_index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatabaseError("cached PDB coordinate digest index is invalid") from error
    if actual_index != expected_index:
        raise DatabaseError("cached PDB coordinate digest index is inconsistent")
    if (
        full_checksum
        and sha256_file(object_path, progress=progress, logger=_LOGGER)
        != record.object_sha256
    ):
        raise DatabaseError("cached PDB coordinate object checksum mismatch")
    return record
