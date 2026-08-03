"""Fail-loud compute-node preflight for large database administration."""

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import JsonValue
from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.databases.common import (
    DatabaseError,
    tool_version,
    tree_size,
)
from genome_to_diffraction.time import utc_now

_LOGGER = logging.getLogger("genome_to_diffraction.databases")

FOLDSEEK_PDB_ARCHIVE_URL = "https://foldseek.steineggerlab.workers.dev/pdb100.tar.gz"
FOLDSEEK_PDB_VERSION_URL = "https://foldseek.steineggerlab.workers.dev/pdb100.version"
FOLDSEEK_PROSTT5_ARCHIVE_URL = (
    "https://foldseek.steineggerlab.workers.dev/prostt5-f16-gguf.tar.gz"
)
PDB_SEQUENCE_URL = "https://files.rcsb.org/pub/pdb/derived_data/pdb_seqres.txt.gz"
PDB_COORDINATE_SMOKE_URL = "https://files.rcsb.org/download/1ubq.cif.gz"

_FIXED_PROBES = (
    ("foldseek_pdb_archive", FOLDSEEK_PDB_ARCHIVE_URL),
    ("foldseek_pdb_version", FOLDSEEK_PDB_VERSION_URL),
    ("foldseek_prostt5_archive", FOLDSEEK_PROSTT5_ARCHIVE_URL),
    ("rcsb_pdb_seqres", PDB_SEQUENCE_URL),
    ("rcsb_1ubq_coordinate", PDB_COORDINATE_SMOKE_URL),
)


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


def _probe_public_routes(
    scratch_root: Path,
    *,
    timeout_seconds: int,
    progress: bool,
) -> tuple[str, list[dict[str, JsonValue]]]:
    aria2c = shutil.which("aria2c")
    if aria2c is None or not Path(aria2c).is_absolute():
        raise DatabaseError("pinned aria2c is required for Foldseek route preflight")
    aria2_version = tool_version(aria2c)
    probes: list[dict[str, JsonValue]] = []
    with (
        tempfile.TemporaryDirectory(
            prefix="nf-gtd-route-probe-", dir=scratch_root
        ) as temporary,
        tqdm(
            _FIXED_PROBES,
            desc="Probe database routes",
            unit="route",
            disable=not progress,
        ) as routes,
    ):
        for name, url in routes:
            _LOGGER.info(
                "probing fixed public database route",
                extra={"route_name": name, "url": url},
            )
            command = [
                aria2c,
                "--dry-run=true",
                "--max-tries=1",
                "--retry-wait=0",
                "--check-certificate=true",
                f"--connect-timeout={timeout_seconds}",
                f"--timeout={timeout_seconds}",
                f"--dir={temporary}",
                url,
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds + 10,
                )
            except subprocess.TimeoutExpired as error:
                raise DatabaseError(
                    f"fixed database route probe timed out: {name}"
                ) from error
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()[-1000:]
                raise DatabaseError(
                    f"fixed database route probe failed: {name}: {detail}"
                )
            probes.append(
                {
                    "name": name,
                    "url": url,
                    "probe": "aria2c --dry-run=true",
                    "status": "reachable",
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

        foldseek_version = tool_version("foldseek")
        mmseqs_version = tool_version("mmseqs")
        if "10.941cd33" not in foldseek_version:
            raise DatabaseError("Foldseek 10.941cd33 is required")
        if "18.8cc5c" not in mmseqs_version:
            raise DatabaseError("MMseqs2 18.8cc5c is required")
        aria2_version, probes = _probe_public_routes(
            scratch_root,
            timeout_seconds=request.probe_timeout_seconds,
            progress=request.progress,
        )

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
