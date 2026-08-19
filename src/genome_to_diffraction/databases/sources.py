"""Stage immutable public inputs for offline database preparation.

The command accepts one canonical durable database root plus explicit storage
limits and writes a small source-bundle JSON manifest. It downloads only the
fixed Foldseek PDB/ProstT5 and RCSB SEQRES/1UBQ inputs defined here, records HTTP
provenance and streaming SHA-256 values, and publishes files by a content-based
bundle ID. Partial transfers resume only through the validator-bound downloader;
completed sources are journalled so an interrupted multi-file stage can resume.

Status is either a fully verified ``ready`` bundle or a retained ``.failed``
staging directory. Network, integrity, storage, path, and concurrency failures
raise :class:`DatabaseError`; no incomplete bundle is reported as ready. The
bundle ID is the cache key consumed by compute-node preflight and preparation.
Unit tests cover fixed URL selection, reuse, interruption, tampering, and unsafe
staging entries; integration tests cover the login-node/Slurm hand-off.
"""

import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from pydantic import JsonValue
from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.databases.cache import exclusive_lock
from genome_to_diffraction.databases.common import (
    DatabaseError,
    enforce_free_space,
    enforce_storage_limit,
)
from genome_to_diffraction.databases.network import (
    DownloadMetadata,
    download_public_resource,
)
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.time import utc_now

_LOGGER = logging.getLogger("genome_to_diffraction.databases")

FOLDSEEK_PDB_ARCHIVE_URL = "https://foldseek.steineggerlab.workers.dev/pdb100.tar.gz"
FOLDSEEK_PDB_VERSION_URL = "https://foldseek.steineggerlab.workers.dev/pdb100.version"
FOLDSEEK_PROSTT5_ARCHIVE_URL = (
    "https://foldseek.steineggerlab.workers.dev/prostt5-f16-gguf.tar.gz"
)
PDB_SEQUENCE_URL = "https://files.rcsb.org/pub/pdb/derived_data/pdb_seqres.txt.gz"
PDB_COORDINATE_SMOKE_URL = "https://files.rcsb.org/download/1ubq.cif.gz"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_BUNDLE_ID = re.compile(r"^dbsrc_[0-9a-f]{64}$")
_STAGING = re.compile(r"^\.staging-[0-9a-f]{32}$")
_FAILED_STAGING = re.compile(r"^\.staging-[0-9a-f]{32}\.failed$")
_PUBLISHED_BUNDLE = re.compile(r"^bundle-[0-9a-f]{64}$")


@dataclass(frozen=True)
class SourceSpec:
    """One fixed public input admitted to the database source boundary."""

    name: str
    filename: str
    requested_url: str


SOURCE_SPECS = (
    SourceSpec("foldseek_pdb_archive", "pdb100.tar.gz", FOLDSEEK_PDB_ARCHIVE_URL),
    SourceSpec("foldseek_pdb_version", "pdb100.version", FOLDSEEK_PDB_VERSION_URL),
    SourceSpec(
        "foldseek_prostt5_archive",
        "prostt5-f16-gguf.tar.gz",
        FOLDSEEK_PROSTT5_ARCHIVE_URL,
    ),
    SourceSpec("pdb_sequences", "pdb_seqres.txt.gz", PDB_SEQUENCE_URL),
    SourceSpec("pdb_coordinate_1ubq", "1ubq.cif.gz", PDB_COORDINATE_SMOKE_URL),
)
_SPECS_BY_NAME = {spec.name: spec for spec in SOURCE_SPECS}


@dataclass(frozen=True)
class SourceRecord:
    """Checksummed provenance for one file in a source bundle."""

    name: str
    filename: str
    requested_url: str
    effective_url: str
    etag: str | None
    last_modified: str | None
    content_type: str | None
    size_bytes: int
    sha256: str

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "filename": self.filename,
            "requested_url": self.requested_url,
            "effective_url": self.effective_url,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }

    def download_metadata(self) -> DownloadMetadata:
        """Return the original HTTP provenance in downloader form."""

        return DownloadMetadata(
            requested_url=self.requested_url,
            url=self.effective_url,
            etag=self.etag,
            last_modified=self.last_modified,
            content_type=self.content_type,
            size_bytes=self.size_bytes,
            sha256=self.sha256,
        )


@dataclass(frozen=True)
class DatabaseSourceBundle:
    """A complete immutable set of network inputs for one offline build."""

    bundle_id: str
    created_at: str
    resources: tuple[SourceRecord, ...]

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "schema_version": "1.0",
            "status": "ready",
            "bundle_id": self.bundle_id,
            "created_at": self.created_at,
            "resources": [resource.as_json() for resource in self.resources],
        }

    def record(self, name: str) -> SourceRecord:
        """Return one required source record by its fixed name."""

        matches = [resource for resource in self.resources if resource.name == name]
        if len(matches) != 1:
            raise DatabaseError(f"database source bundle lacks exactly one {name}")
        return matches[0]

    def path(self, database_root: Path, name: str) -> Path:
        """Resolve a verified bundle file below the durable database root."""

        record = self.record(name)
        return _bundle_directory(database_root, self.bundle_id) / record.filename


@dataclass(frozen=True)
class SourceBundleRequest:
    """Storage and output controls for staging fixed public source files."""

    database_root: Path
    manifest_path: Path
    storage_limit_bytes: int
    minimum_free_bytes: int
    progress: bool = True


def _database_root(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise DatabaseError("database_root must be an existing absolute directory")
    root = path.resolve(strict=True)
    if root in {Path("/"), Path.home().resolve()}:
        raise DatabaseError("database_root must be canonical and narrowly scoped")
    return root


def _bundle_directory(database_root: Path, bundle_id: str) -> Path:
    if _BUNDLE_ID.fullmatch(bundle_id) is None:
        raise DatabaseError("invalid database source bundle identifier")
    return database_root / "sources" / f"bundle-{bundle_id.removeprefix('dbsrc_')}"


def _strict_optional_text(value: object, *, label: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value):
        raise DatabaseError(f"invalid database source {label}")
    return value


def _parse_record(value: object) -> SourceRecord:
    if not isinstance(value, dict) or set(value) != {
        "name",
        "filename",
        "requested_url",
        "effective_url",
        "etag",
        "last_modified",
        "content_type",
        "size_bytes",
        "sha256",
    }:
        raise DatabaseError("invalid database source record fields")
    name = value.get("name")
    if not isinstance(name, str) or name not in _SPECS_BY_NAME:
        raise DatabaseError("invalid database source name")
    spec = _SPECS_BY_NAME[name]
    filename = value.get("filename")
    requested_url = value.get("requested_url")
    effective_url = value.get("effective_url")
    size_bytes = value.get("size_bytes")
    digest = value.get("sha256")
    if filename != spec.filename or requested_url != spec.requested_url:
        raise DatabaseError(f"database source identity differs for {name}")
    if not isinstance(effective_url, str) or not effective_url.startswith("https://"):
        raise DatabaseError(f"database source effective URL is unsafe for {name}")
    if (
        isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or size_bytes < 1
    ):
        raise DatabaseError(f"database source size is invalid for {name}")
    if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
        raise DatabaseError(f"database source checksum is invalid for {name}")
    return SourceRecord(
        name=name,
        filename=spec.filename,
        requested_url=spec.requested_url,
        effective_url=effective_url,
        etag=_strict_optional_text(value.get("etag"), label=f"{name} ETag"),
        last_modified=_strict_optional_text(
            value.get("last_modified"), label=f"{name} Last-Modified"
        ),
        content_type=_strict_optional_text(
            value.get("content_type"), label=f"{name} content type"
        ),
        size_bytes=size_bytes,
        sha256=digest,
    )


def _parse_bundle(value: object) -> DatabaseSourceBundle:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "status",
        "bundle_id",
        "created_at",
        "resources",
    }:
        raise DatabaseError("invalid database source bundle fields")
    if value.get("schema_version") != "1.0" or value.get("status") != "ready":
        raise DatabaseError("database source bundle is not ready schema 1.0")
    bundle_id = value.get("bundle_id")
    created_at = value.get("created_at")
    raw_resources = value.get("resources")
    if not isinstance(bundle_id, str) or _BUNDLE_ID.fullmatch(bundle_id) is None:
        raise DatabaseError("invalid database source bundle identifier")
    if not isinstance(created_at, str) or not created_at.endswith("Z"):
        raise DatabaseError("invalid database source bundle timestamp")
    if not isinstance(raw_resources, list):
        raise DatabaseError("database source bundle resources must be a list")
    resources = tuple(_parse_record(record) for record in raw_resources)
    if [resource.name for resource in resources] != [
        spec.name for spec in SOURCE_SPECS
    ]:
        raise DatabaseError("database source bundle resource order or set is invalid")
    identity = [resource.as_json() for resource in resources]
    if bundle_id != f"dbsrc_{canonical_digest(identity)}":
        raise DatabaseError(
            "database source bundle identity does not match its records"
        )
    return DatabaseSourceBundle(
        bundle_id=bundle_id,
        created_at=created_at,
        resources=resources,
    )


def _read_manifest(path: Path) -> object:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise DatabaseError("database source manifest is missing or unsafe")
    try:
        return load_json_document(path)
    except ContractLoadError as error:
        raise DatabaseError(
            f"database source manifest is not valid strict JSON: {error}"
        ) from error


def load_source_bundle(
    database_root: Path,
    manifest_path: Path,
    *,
    full_verify: bool,
    progress: bool,
) -> DatabaseSourceBundle:
    """Load one strict bundle and verify its durable files."""

    root = _database_root(database_root)
    bundle = _parse_bundle(_read_manifest(manifest_path))
    bundle_root = _bundle_directory(root, bundle.bundle_id)
    if bundle_root.is_symlink() or not bundle_root.is_dir():
        raise DatabaseError("database source bundle directory is missing or unsafe")
    for record in bundle.resources:
        path = bundle_root / record.filename
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != record.size_bytes
        ):
            raise DatabaseError(
                f"database source file is missing or changed: {record.name}"
            )
        if (
            full_verify
            and sha256_file(
                path,
                progress=progress,
                description=f"Verify {record.filename}",
                logger=_LOGGER,
            )
            != record.sha256
        ):
            raise DatabaseError(f"database source checksum mismatch: {record.name}")
    return bundle


def _record(spec: SourceSpec, metadata: DownloadMetadata, path: Path) -> SourceRecord:
    if path.stat().st_size != metadata.size_bytes:
        raise DatabaseError(f"downloaded database source size changed: {spec.name}")
    if _HEX64.fullmatch(metadata.sha256) is None:
        raise DatabaseError(
            f"downloaded database source checksum is invalid: {spec.name}"
        )
    return SourceRecord(
        name=spec.name,
        filename=spec.filename,
        requested_url=spec.requested_url,
        effective_url=metadata.url,
        etag=metadata.etag,
        last_modified=metadata.last_modified,
        content_type=metadata.content_type,
        size_bytes=metadata.size_bytes,
        sha256=metadata.sha256,
    )


def _record_path(staging: Path, spec: SourceSpec) -> Path:
    return staging / f".{spec.name}.record.json"


def _completed_record(
    staging: Path, spec: SourceSpec, *, progress: bool
) -> SourceRecord | None:
    journal = _record_path(staging, spec)
    if not journal.exists() and not journal.is_symlink():
        return None
    record = _parse_record(_read_manifest(journal))
    if record.name != spec.name:
        raise DatabaseError("database source completion record has the wrong identity")
    path = staging / spec.filename
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size != record.size_bytes
    ):
        raise DatabaseError(f"completed database source changed: {spec.name}")
    if (
        sha256_file(
            path,
            progress=progress,
            description=f"Verify completed {spec.filename}",
            logger=_LOGGER,
        )
        != record.sha256
    ):
        raise DatabaseError(f"completed database source checksum mismatch: {spec.name}")
    return record


def _validate_staging_entries(staging: Path) -> None:
    allowed = {"source_bundle.json"}
    for spec in SOURCE_SPECS:
        allowed.update(
            {
                spec.filename,
                f".{spec.filename}.partial",
                f".{spec.filename}.partial.json",
                _record_path(staging, spec).name,
            }
        )
    for path in staging.iterdir():
        if path.name not in allowed or path.is_symlink() or not path.is_file():
            raise DatabaseError(f"unsafe entry in database source staging: {path.name}")


def _recover_published_bundle(
    root: Path, sources_root: Path
) -> DatabaseSourceBundle | None:
    published = sorted(
        path
        for path in sources_root.iterdir()
        if _PUBLISHED_BUNDLE.fullmatch(path.name)
    )
    if len(published) != 1:
        return None
    candidate = published[0]
    bundle = load_source_bundle(
        root,
        candidate / "source_bundle.json",
        full_verify=True,
        progress=False,
    )
    atomic_write_json(sources_root / "current.json", bundle.as_json())
    _LOGGER.warning(
        "recovered database source publication after an interrupted pointer write",
        extra={"bundle_id": bundle.bundle_id},
    )
    return bundle


def _stage_source_bundle_locked(
    request: SourceBundleRequest, root: Path
) -> DatabaseSourceBundle:
    """Perform a serialised fixed-source stage under the database root lock."""

    enforce_storage_limit(root, request.storage_limit_bytes)
    enforce_free_space(root, request.minimum_free_bytes)
    sources_root = root / "sources"
    sources_root.mkdir(exist_ok=True)
    if sources_root.is_symlink() or sources_root.resolve(strict=True) != sources_root:
        raise DatabaseError("database sources root is unsafe")
    current = sources_root / "current.json"
    if current.exists() or current.is_symlink():
        bundle = load_source_bundle(
            root,
            current,
            full_verify=True,
            progress=request.progress,
        )
        atomic_write_json(request.manifest_path, bundle.as_json())
        _LOGGER.info(
            "reused verified durable database source bundle",
            extra={"bundle_id": bundle.bundle_id},
        )
        return bundle
    recovered = _recover_published_bundle(root, sources_root)
    if recovered is not None:
        atomic_write_json(request.manifest_path, recovered.as_json())
        return recovered
    retained = sorted(
        path
        for path in sources_root.iterdir()
        if _STAGING.fullmatch(path.name) or _FAILED_STAGING.fullmatch(path.name)
    )
    if len(retained) > 1:
        raise DatabaseError(
            "multiple retained database source staging directories require review"
        )
    if retained:
        staging = retained[0]
        if staging.is_symlink() or not staging.is_dir():
            raise DatabaseError("retained database source staging is unsafe")
        if _FAILED_STAGING.fullmatch(staging.name):
            resumed = staging.with_name(staging.name.removesuffix(".failed"))
            if resumed.exists() or resumed.is_symlink():
                raise DatabaseError("database source resume destination is occupied")
            os.replace(staging, resumed)
            staging = resumed
        _validate_staging_entries(staging)
        _LOGGER.info(
            "resuming retained database source staging",
            extra={"staging_path": str(staging)},
        )
    else:
        staging = sources_root / f".staging-{uuid.uuid4().hex}"
        staging.mkdir()
    records: list[SourceRecord] = []
    try:
        with tqdm(
            SOURCE_SPECS,
            desc="Stage database sources",
            unit="source",
            disable=not request.progress,
        ) as sources:
            for spec in sources:
                completed = _completed_record(staging, spec, progress=request.progress)
                if completed is not None:
                    records.append(completed)
                    _LOGGER.info(
                        "reused completed database source from retained staging",
                        extra={"source_name": spec.name},
                    )
                    continue
                _LOGGER.info(
                    "staging fixed database source on durable storage",
                    extra={"source_name": spec.name, "url": spec.requested_url},
                )
                destination = staging / spec.filename
                metadata = download_public_resource(
                    spec.requested_url,
                    destination,
                    storage_root=root,
                    storage_limit_bytes=request.storage_limit_bytes,
                    minimum_free_bytes=request.minimum_free_bytes,
                    progress=request.progress,
                )
                completed = _record(spec, metadata, destination)
                atomic_write_json(_record_path(staging, spec), completed.as_json())
                records.append(completed)
        identity = [record.as_json() for record in records]
        bundle = DatabaseSourceBundle(
            bundle_id=f"dbsrc_{canonical_digest(identity)}",
            created_at=utc_now().isoformat().replace("+00:00", "Z"),
            resources=tuple(records),
        )
        atomic_write_json(staging / "source_bundle.json", bundle.as_json())
        for spec in SOURCE_SPECS:
            _record_path(staging, spec).unlink()
        final = _bundle_directory(root, bundle.bundle_id)
        if final.exists() or final.is_symlink():
            raise DatabaseError("database source bundle destination already exists")
        os.replace(staging, final)
        for path in final.iterdir():
            path.chmod(0o444)
        final.chmod(0o555)
        atomic_write_json(current, bundle.as_json())
        atomic_write_json(request.manifest_path, bundle.as_json())
        _LOGGER.info(
            "published immutable durable database source bundle",
            extra={"bundle_id": bundle.bundle_id, "resource_count": len(records)},
        )
        return bundle
    except BaseException:
        if staging.exists():
            failed = staging.with_name(f"{staging.name}.failed")
            os.replace(staging, failed)
            _LOGGER.error(
                "retained incomplete database source staging",
                extra={"staging_path": str(failed)},
            )
        raise


def stage_source_bundle(request: SourceBundleRequest) -> DatabaseSourceBundle:
    """Download the fixed source set directly into immutable durable storage."""

    root = _database_root(request.database_root)
    if not request.manifest_path.is_absolute():
        raise DatabaseError("database source manifest output must be absolute")
    if request.manifest_path.is_symlink() or request.manifest_path.exists():
        raise DatabaseError(
            "database source manifest output must be new and non-symlink"
        )
    parent = request.manifest_path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise DatabaseError("database source manifest parent is missing or unsafe")
    lock_path = root / "tmp" / "locks" / "database-source-stage.lock"
    with exclusive_lock(lock_path, timeout_seconds=30.0, progress=request.progress):
        return _stage_source_bundle_locked(request, root)
