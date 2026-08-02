"""Shared inventory, command, and storage safeguards for database preparation.

External downloads and tools run only through the explicit database-preparation
entry point. Each command is logged as an argument array, streams output to a
preserved log, and is terminated if the configured project storage cap is crossed.
"""

import json
import logging
import subprocess
import threading
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.status import InfrastructureError, ToolExecutionError

_LOGGER = logging.getLogger("genome_to_diffraction.databases")
_SIDECARS = frozenset({".gtd-inventory.json", ".gtd-resource.json"})


class DatabaseError(InfrastructureError):
    """A database resource could not be prepared or verified safely."""


class StorageLimitError(DatabaseError):
    """The configured database-project storage cap was exceeded."""


class DatabaseCommandError(ToolExecutionError):
    """A database preparation command returned a non-zero exit status."""

    def __init__(self, command: Sequence[str], returncode: int, log_path: Path) -> None:
        super().__init__(
            f"database command failed with exit status {returncode}: "
            f"{command[0]}; see {log_path}"
        )
        self.command = tuple(command)
        self.returncode = returncode
        self.log_path = log_path


@dataclass(frozen=True)
class FileRecord:
    """Path-independent integrity record for one resource file."""

    path: str
    size_bytes: int
    sha256: str


def iter_resource_files(root: Path) -> list[Path]:
    """Return stable regular-file paths, excluding generated inventory sidecars."""

    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name not in _SIDECARS and not path.is_symlink()
    )


def tree_size(root: Path) -> int:
    """Return bytes in regular files below *root* without following symlinks."""

    if not root.exists():
        return 0
    total = 0
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            total += path.stat().st_size
    return total


def enforce_storage_limit(root: Path, limit_bytes: int) -> int:
    """Fail loudly when the project tree is over its configured hard cap."""

    if limit_bytes <= 0:
        raise ValueError("storage limit must be positive")
    used = tree_size(root)
    _LOGGER.info(
        "database storage check",
        extra={"root": str(root), "used_bytes": used, "limit_bytes": limit_bytes},
    )
    if used > limit_bytes:
        raise StorageLimitError(
            f"database root uses {used} bytes, exceeding the {limit_bytes}-byte cap"
        )
    return used


def inventory_resource(
    root: Path, *, progress: bool = True
) -> tuple[list[FileRecord], str]:
    """Stream checksums for every resource file and write a stable inventory."""

    paths = iter_resource_files(root)
    total_bytes = sum(path.stat().st_size for path in paths)
    records: list[FileRecord] = []
    with tqdm(
        total=total_bytes,
        desc=f"Inventory {root.name}",
        unit="B",
        unit_scale=True,
        disable=not progress,
    ) as progress_bar:
        for path in paths:
            size = path.stat().st_size
            records.append(
                FileRecord(
                    path=path.relative_to(root).as_posix(),
                    size_bytes=size,
                    sha256=sha256_file(path, logger=_LOGGER),
                )
            )
            progress_bar.update(size)
    payload = {
        "schema_version": "1.0",
        "files": [asdict(record) for record in records],
    }
    digest = canonical_digest(payload)
    atomic_write_json(root / ".gtd-inventory.json", payload)
    _LOGGER.info(
        "database resource inventory complete",
        extra={
            "root": str(root),
            "file_count": len(records),
            "total_bytes": total_bytes,
            "manifest_sha256": digest,
        },
    )
    return records, digest


def verify_inventory(
    root: Path,
    expected_digest: str,
    *,
    full_checksums: bool,
    progress: bool = True,
) -> tuple[int, int]:
    """Verify a stored inventory using sizes and optional full SHA-256 checks."""

    inventory_path = root / ".gtd-inventory.json"
    try:
        document = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatabaseError(
            f"cannot read resource inventory {inventory_path}: {error}"
        ) from error
    if canonical_digest(document) != expected_digest:
        raise DatabaseError(f"inventory digest mismatch for {root}")
    raw_records = document.get("files")
    if not isinstance(raw_records, list) or not raw_records:
        raise DatabaseError(f"resource inventory has no files: {inventory_path}")
    total_bytes = 0
    iterator: Iterable[object] = tqdm(
        raw_records,
        desc=f"Verify {root.name}",
        unit="file",
        disable=not progress,
    )
    for raw in iterator:
        if not isinstance(raw, dict):
            raise DatabaseError(f"invalid inventory record in {inventory_path}")
        relative = raw.get("path")
        size = raw.get("size_bytes")
        digest = raw.get("sha256")
        if (
            not isinstance(relative, str)
            or not isinstance(size, int)
            or not isinstance(digest, str)
        ):
            raise DatabaseError(f"invalid inventory record in {inventory_path}")
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise DatabaseError(f"resource file is missing or unsafe: {path}")
        actual_size = path.stat().st_size
        if actual_size != size:
            raise DatabaseError(
                f"resource file size mismatch for {path}: "
                f"expected {size}, found {actual_size}"
            )
        if full_checksums and sha256_file(path, logger=_LOGGER) != digest:
            raise DatabaseError(f"resource checksum mismatch for {path}")
        total_bytes += actual_size
    return len(raw_records), total_bytes


def tool_version(executable: str) -> str:
    """Return the first non-empty version line for an external database tool."""

    completed = subprocess.run(
        [executable, "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise DatabaseError(
            f"cannot determine {executable} version (exit {completed.returncode})"
        )
    output = f"{completed.stdout}\n{completed.stderr}"
    line = next((item.strip() for item in output.splitlines() if item.strip()), "")
    if not line:
        raise DatabaseError(f"{executable} --version returned no version text")
    return line


def run_command(
    command: Sequence[str],
    *,
    log_path: Path,
    storage_root: Path,
    storage_limit_bytes: int,
    progress: bool,
) -> None:
    """Run one exact argument array with log streaming and a storage watchdog."""

    if not command:
        raise ValueError("database command must not be empty")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _LOGGER.info(
        "starting database command",
        extra={"command": list(command), "log": str(log_path)},
    )
    stop = threading.Event()
    exceeded = threading.Event()
    process: subprocess.Popen[str]

    def watch_storage() -> None:
        while not stop.wait(20):
            try:
                used = tree_size(storage_root)
            except OSError as error:
                _LOGGER.error("storage watchdog failed", extra={"error": str(error)})
                exceeded.set()
                process.terminate()
                return
            _LOGGER.info(
                "database command storage progress",
                extra={"used_bytes": used, "limit_bytes": storage_limit_bytes},
            )
            if used > storage_limit_bytes:
                exceeded.set()
                process.terminate()
                return

    with (
        log_path.open("w", encoding="utf-8") as log_handle,
        tqdm(
            total=1,
            desc=f"Run {Path(command[0]).name}",
            unit="command",
            disable=not progress,
        ) as progress_bar,
    ):
        process = subprocess.Popen(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        watchdog = threading.Thread(target=watch_storage, daemon=True)
        watchdog.start()
        if process.stdout is None:
            raise AssertionError("database command stdout pipe was not created")
        for line in process.stdout:
            log_handle.write(line)
            log_handle.flush()
            _LOGGER.debug("database command output", extra={"line": line.rstrip("\n")})
        returncode = process.wait()
        stop.set()
        watchdog.join(timeout=2)
        if returncode == 0 and not exceeded.is_set():
            progress_bar.update(1)
    if exceeded.is_set():
        raise StorageLimitError(
            f"database command crossed the {storage_limit_bytes}-byte project cap; "
            f"see {log_path}"
        )
    if returncode != 0:
        raise DatabaseCommandError(command, returncode, log_path)
    enforce_storage_limit(storage_root, storage_limit_bytes)
