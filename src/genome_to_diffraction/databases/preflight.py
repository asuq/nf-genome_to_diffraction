"""Fail-loud compute-node preflight for large database administration."""

import logging
import os
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast

from pydantic import JsonValue
from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.databases import sources as source_module
from genome_to_diffraction.databases.common import (
    DatabaseError,
    tool_version,
    tree_size,
)
from genome_to_diffraction.time import utc_now

_LOGGER = logging.getLogger("genome_to_diffraction.databases")

# Retain the established module-level constants for callers and tests while the
# source-bundle module owns their single definitions.
FOLDSEEK_PDB_ARCHIVE_URL = source_module.FOLDSEEK_PDB_ARCHIVE_URL
FOLDSEEK_PDB_VERSION_URL = source_module.FOLDSEEK_PDB_VERSION_URL
FOLDSEEK_PROSTT5_ARCHIVE_URL = source_module.FOLDSEEK_PROSTT5_ARCHIVE_URL
PDB_COORDINATE_SMOKE_URL = source_module.PDB_COORDINATE_SMOKE_URL
PDB_SEQUENCE_URL = source_module.PDB_SEQUENCE_URL
load_source_bundle = source_module.load_source_bundle

_FIXED_PROBES = (
    ("foldseek_pdb_archive", FOLDSEEK_PDB_ARCHIVE_URL),
    ("foldseek_pdb_version", FOLDSEEK_PDB_VERSION_URL),
    ("foldseek_prostt5_archive", FOLDSEEK_PROSTT5_ARCHIVE_URL),
    ("rcsb_pdb_seqres", PDB_SEQUENCE_URL),
    ("rcsb_1ubq_coordinate", PDB_COORDINATE_SMOKE_URL),
)
_CONTENT_RANGE = re.compile(r"^bytes 0-0/(?P<total>[1-9][0-9]*)$")
_ROUTE_PROBE_USER_AGENT = "nf-genome-to-diffraction/0.1 database-preflight"


@dataclass(frozen=True)
class DatabasePreflightRequest:
    """Fixed capacity, scratch, tool, and public-route checks for one build."""

    database_root: Path
    scratch_root: Path
    report_path: Path
    storage_limit_bytes: int
    minimum_free_bytes: int
    required_database_capacity_bytes: int
    minimum_scratch_free_bytes: int
    source_bundle_path: Path | None = None
    probe_timeout_seconds: int = 60
    progress: bool = True


def _canonical_directory(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise DatabaseError(f"{label} must be an absolute path")
    if path.is_symlink() or not path.is_dir():
        raise DatabaseError(f"{label} must be an existing non-symlink directory")
    resolved = path.resolve(strict=True)
    if resolved != path:
        raise DatabaseError(f"{label} must be a canonical path")
    if resolved == Path("/") or resolved == Path.home().resolve():
        raise DatabaseError(f"{label} is too broad")
    if not os.access(resolved, os.R_OK | os.W_OK | os.X_OK):
        raise DatabaseError(f"{label} is not readable, writable, and searchable")
    return resolved


def _validate_report_path(path: Path) -> Path:
    if not path.is_absolute():
        raise DatabaseError("database preflight report must be an absolute path")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise DatabaseError(
            "database preflight report must be a regular non-symlink file"
        )
    return path


def _device_id(path: Path) -> int:
    return path.stat().st_dev


def _available_capacity(
    root: Path,
    *,
    storage_limit_bytes: int,
    minimum_free_bytes: int,
    progress: bool,
) -> tuple[int, int, int]:
    _LOGGER.info("measuring database root capacity", extra={"path": str(root)})
    with tqdm(
        total=1,
        desc="Measure database capacity",
        unit="root",
        disable=not progress,
    ) as progress_bar:
        used_bytes = tree_size(root)
        usage = shutil.disk_usage(root)
        progress_bar.update(1)
    remaining_project_bytes = max(storage_limit_bytes - used_bytes, 0)
    remaining_filesystem_bytes = max(usage.free - minimum_free_bytes, 0)
    available_bytes = min(remaining_project_bytes, remaining_filesystem_bytes)
    _LOGGER.info(
        "database root capacity measured",
        extra={
            "path": str(root),
            "used_bytes": used_bytes,
            "free_bytes": usage.free,
            "available_bytes": available_bytes,
        },
    )
    return used_bytes, usage.free, available_bytes


def _probe_one_byte(url: str, *, timeout_seconds: int) -> dict[str, JsonValue]:
    """Verify one fixed HTTPS representation without downloading its payload."""

    request = urllib.request.Request(
        url,
        headers={
            "Accept-Encoding": "identity",
            "Range": "bytes=0-0",
            "User-Agent": _ROUTE_PROBE_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", None)
            content_length = response.headers.get("Content-Length")
            if status == 206:
                content_range = response.headers.get("Content-Range")
                match = (
                    _CONTENT_RANGE.fullmatch(content_range)
                    if content_range is not None
                    else None
                )
                if match is None:
                    raise DatabaseError(
                        f"fixed database route returned invalid Content-Range: {url}"
                    )
                if content_length != "1":
                    raise DatabaseError(
                        "fixed database route returned an unbounded ranged body "
                        f"length: {url}"
                    )
                total_size = int(match.group("total"))
                range_honoured = True
            elif status == 200:
                if content_length is None:
                    total_size = None
                elif not content_length.isascii() or not content_length.isdecimal():
                    raise DatabaseError(
                        f"fixed database route returned an invalid body length: {url}"
                    )
                else:
                    total_size = int(content_length)
                    if total_size <= 0:
                        raise DatabaseError(
                            f"fixed database route returned an empty body length: {url}"
                        )
                range_honoured = False
            else:
                raise DatabaseError(
                    f"fixed database route returned unsupported HTTP status: {url}"
                )
            content_encoding = response.headers.get("Content-Encoding")
            if content_encoding not in {None, "identity"}:
                raise DatabaseError(
                    f"fixed database route ignored identity encoding: {url}"
                )
            payload = response.read(2 if range_honoured else 1)
            if len(payload) != 1:
                raise DatabaseError(
                    f"fixed database route probe did not return exactly one byte: {url}"
                )
            effective_url = response.geturl()
            if not effective_url.startswith("https://"):
                raise DatabaseError(
                    f"fixed database route redirected outside HTTPS: {url}"
                )
            return {
                "effective_url": effective_url,
                "representation_size_bytes": total_size,
                "range_honoured": range_honoured,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "sample_sha256": sha256(payload).hexdigest(),
                "sample_size_bytes": len(payload),
            }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        raise DatabaseError(
            f"fixed database route probe failed: {url}: {error}"
        ) from error


def _probe_public_routes(
    scratch_root: Path,
    *,
    timeout_seconds: int,
    progress: bool,
) -> tuple[str, list[dict[str, JsonValue]]]:
    """Probe only pinned routes with bounded one-byte HTTPS requests."""

    aria2c = shutil.which("aria2c")
    if aria2c is None or not Path(aria2c).is_absolute():
        raise DatabaseError("pinned aria2c is required for Foldseek route preflight")
    aria2_version = tool_version(aria2c)
    if "1.37.0" not in aria2_version:
        raise DatabaseError("aria2 1.37.0 is required")
    probes: list[dict[str, JsonValue]] = []
    _LOGGER.info(
        "starting bounded public database route probes",
        extra={"scratch_root": str(scratch_root)},
    )
    with tqdm(
        _FIXED_PROBES,
        desc="Probe database routes",
        unit="route",
        disable=not progress,
    ) as routes:
        for name, url in routes:
            _LOGGER.info(
                "probing fixed public database route",
                extra={"route_name": name, "url": url},
            )
            observation = _probe_one_byte(url, timeout_seconds=timeout_seconds)
            probes.append(
                {
                    "name": name,
                    "url": url,
                    "probe": "HTTPS Range bytes=0-0; exactly one response byte",
                    "status": "reachable",
                    **observation,
                }
            )
    return aria2_version, probes


def preflight_database_administration(
    request: DatabasePreflightRequest,
) -> dict[str, JsonValue]:
    """Validate a compute node before any large database payload is written."""

    report_path = _validate_report_path(request.report_path)
    started_at = utc_now()
    report: dict[str, JsonValue] = {
        "schema_version": "1.0",
        "status": "running",
        "started_at": started_at.isoformat(),
    }
    try:
        if request.storage_limit_bytes <= 0:
            raise ValueError("storage limit must be positive")
        if request.minimum_free_bytes < 0:
            raise ValueError("minimum free bytes must not be negative")
        if request.required_database_capacity_bytes <= 0:
            raise ValueError("required database capacity must be positive")
        if request.minimum_scratch_free_bytes <= 0:
            raise ValueError("minimum scratch free bytes must be positive")
        if request.probe_timeout_seconds < 1:
            raise ValueError("route probe timeout must be positive")

        database_root = _canonical_directory(request.database_root, "database_root")
        scratch_root = _canonical_directory(request.scratch_root, "scratch_root")
        if (
            database_root == scratch_root
            or database_root in scratch_root.parents
            or scratch_root in database_root.parents
        ):
            raise DatabaseError(
                "scratch_root must be separate from and outside database_root"
            )
        database_device = _device_id(database_root)
        scratch_device = _device_id(scratch_root)
        if database_device == scratch_device:
            raise DatabaseError(
                "scratch_root must use a filesystem distinct from database_root"
            )

        used_bytes, free_bytes, available_bytes = _available_capacity(
            database_root,
            storage_limit_bytes=request.storage_limit_bytes,
            minimum_free_bytes=request.minimum_free_bytes,
            progress=request.progress,
        )
        if available_bytes < request.required_database_capacity_bytes:
            raise DatabaseError(
                "database root lacks the explicitly required build capacity: "
                f"available={available_bytes}, "
                f"required={request.required_database_capacity_bytes}"
            )
        scratch_free_bytes = shutil.disk_usage(scratch_root).free
        if scratch_free_bytes < request.minimum_scratch_free_bytes:
            raise DatabaseError(
                "scratch root lacks required free capacity: "
                f"available={scratch_free_bytes}, "
                f"required={request.minimum_scratch_free_bytes}"
            )

        foldseek_version = tool_version("foldseek", arguments=("version",))
        mmseqs_version = tool_version("mmseqs", arguments=("version",))
        if "10.941cd33" not in foldseek_version:
            raise DatabaseError("Foldseek 10.941cd33 is required")
        if "18.8cc5c" not in mmseqs_version:
            raise DatabaseError("MMseqs2 18.8cc5c is required")
        source_bundle_id: str | None = None
        if request.source_bundle_path is None:
            aria2_version, probes = _probe_public_routes(
                scratch_root,
                timeout_seconds=request.probe_timeout_seconds,
                progress=request.progress,
            )
        else:
            aria2c = shutil.which("aria2c")
            if aria2c is None or not Path(aria2c).is_absolute():
                raise DatabaseError(
                    "pinned aria2c is required for offline Foldseek extraction"
                )
            aria2_version = tool_version(aria2c)
            if "1.37.0" not in aria2_version:
                raise DatabaseError("aria2 1.37.0 is required")
            source_bundle = load_source_bundle(
                database_root,
                request.source_bundle_path,
                full_verify=True,
                progress=request.progress,
            )
            source_bundle_id = source_bundle.bundle_id
            probes = [
                {
                    "name": resource.name,
                    "url": resource.requested_url,
                    "effective_url": resource.effective_url,
                    "representation_size_bytes": resource.size_bytes,
                    "etag": resource.etag,
                    "last_modified": resource.last_modified,
                    "sha256": resource.sha256,
                    "status": "durable_source_verified",
                }
                for resource in source_bundle.resources
            ]

        report.update(
            {
                "status": "passed",
                "completed_at": utc_now().isoformat(),
                "database_root": str(database_root),
                "scratch_root": str(scratch_root),
                "database_device": database_device,
                "scratch_device": scratch_device,
                "database_used_bytes": used_bytes,
                "database_filesystem_free_bytes": free_bytes,
                "database_available_build_bytes": available_bytes,
                "storage_limit_bytes": request.storage_limit_bytes,
                "minimum_free_bytes": request.minimum_free_bytes,
                "required_database_capacity_bytes": (
                    request.required_database_capacity_bytes
                ),
                "scratch_free_bytes": scratch_free_bytes,
                "minimum_scratch_free_bytes": request.minimum_scratch_free_bytes,
                "foldseek_version": foldseek_version,
                "mmseqs_version": mmseqs_version,
                "aria2_version": aria2_version,
                "source_bundle_id": source_bundle_id,
                "network_probes": cast(JsonValue, probes),
                "large_payload_started": False,
            }
        )
        atomic_write_json(report_path, report)
        _LOGGER.info(
            "database administration preflight passed",
            extra={"report_path": str(report_path)},
        )
        return report
    except BaseException as error:
        report.update(
            {
                "status": "failed",
                "completed_at": utc_now().isoformat(),
                "failure_type": type(error).__name__,
                "failure_message": str(error),
                "large_payload_started": False,
            }
        )
        atomic_write_json(report_path, report)
        _LOGGER.error(
            "database administration preflight failed",
            extra={
                "report_path": str(report_path),
                "error": str(error),
            },
        )
        raise
