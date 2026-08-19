"""Shared inventory, command, and storage safeguards for database preparation.

External downloads and tools run only through the explicit database-preparation
entry point. Each command is logged as an argument array, streams output to a
preserved log, and is terminated if the configured project storage cap or
free-space headroom is crossed within its declared write roots.
"""

import logging
import os
import shutil
import signal
import subprocess
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Literal

from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.status import InfrastructureError, ToolExecutionError

_LOGGER = logging.getLogger("genome_to_diffraction.databases")
_SIDECARS = frozenset({".gtd-inventory.json", ".gtd-resource.json"})


class DatabaseError(InfrastructureError):
    """A database resource could not be prepared or verified safely."""


class StorageLimitError(DatabaseError):
    """The configured database-project storage cap was exceeded."""


class StorageWatchdogError(DatabaseError):
    """The scoped storage watchdog could not measure or stop writes safely."""


class ScratchLimitError(DatabaseError):
    """The explicit database-build scratch filesystem lost required headroom."""


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


def _load_json_document(path: Path, label: str) -> object:
    try:
        return load_json_document(path)
    except ContractLoadError as error:
        raise DatabaseError(f"cannot read {label} {path}: {error}") from error


@dataclass(frozen=True)
class FileRecord:
    """Path-independent integrity record for one resource file."""

    path: str
    size_bytes: int
    sha256: str
    kind: Literal["file", "symlink"] = "file"
    symlink_target: str | None = None


def iter_resource_files(root: Path) -> list[Path]:
    """Return stable files and links, excluding generated inventory sidecars."""

    return sorted(
        path
        for path in root.rglob("*")
        if (path.is_file() or path.is_symlink()) and path.name not in _SIDECARS
    )


def _safe_relative_path(root: Path, value: str) -> Path:
    """Resolve one canonical inventory path while forbidding root escape."""

    pure = PurePosixPath(value)
    if (
        not value
        or pure.is_absolute()
        or value != pure.as_posix()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise DatabaseError(f"unsafe resource inventory path: {value!r}")
    path = root.joinpath(*pure.parts)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise DatabaseError(
            f"resource inventory path escapes root: {value!r}"
        ) from error
    return path


def _safe_symlink_target(root: Path, path: Path, target: str) -> Path:
    """Resolve an inventory symlink target and require it to stay below *root*."""

    if not target or Path(target).is_absolute() or "\x00" in target:
        raise DatabaseError(f"unsafe resource symlink target: {path}: {target!r}")
    try:
        resolved = (path.parent / target).resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise DatabaseError(
            f"resource symlink target is missing or escapes root: {path}: {target!r}"
        ) from error
    return resolved


def tree_size(root: Path) -> int:
    """Return bytes in regular files below *root* without following symlinks."""

    if not root.exists():
        return 0
    total = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except FileNotFoundError:
                        continue
        except FileNotFoundError:
            continue
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


def enforce_free_space(root: Path, minimum_free_bytes: int) -> int:
    """Fail loudly when the backing filesystem lacks configured headroom."""

    if minimum_free_bytes < 0:
        raise ValueError("minimum free bytes must not be negative")
    free_bytes = shutil.disk_usage(root).free
    _LOGGER.info(
        "database filesystem headroom check",
        extra={
            "root": str(root),
            "free_bytes": free_bytes,
            "minimum_free_bytes": minimum_free_bytes,
        },
    )
    if free_bytes < minimum_free_bytes:
        raise StorageLimitError(
            f"database filesystem has {free_bytes} free bytes; "
            f"{minimum_free_bytes} required"
        )
    return free_bytes


def _enforce_scratch_free_space(root: Path, minimum_free_bytes: int) -> int:
    if minimum_free_bytes <= 0:
        raise ValueError("scratch minimum free bytes must be positive")
    free_bytes = shutil.disk_usage(root).free
    _LOGGER.info(
        "database scratch headroom check",
        extra={
            "root": str(root),
            "free_bytes": free_bytes,
            "minimum_free_bytes": minimum_free_bytes,
        },
    )
    if free_bytes < minimum_free_bytes:
        raise ScratchLimitError(
            f"database scratch has {free_bytes} free bytes; "
            f"{minimum_free_bytes} required"
        )
    return free_bytes


def _validated_write_roots(
    storage_root: Path, write_roots: Sequence[Path]
) -> tuple[Path, ...]:
    if not write_roots:
        raise ValueError("database command requires at least one scoped write root")
    resolved_storage = storage_root.resolve(strict=True)
    resolved: list[Path] = []
    for root in write_roots:
        if root.is_symlink():
            raise DatabaseError(f"database command write root is unsafe: {root}")
        try:
            candidate = root.resolve(strict=True)
            candidate.relative_to(resolved_storage)
        except (OSError, ValueError) as error:
            raise DatabaseError(
                f"database command write root is missing or escapes storage: {root}"
            ) from error
        if not candidate.is_dir():
            raise DatabaseError(f"database command write root is unsafe: {root}")
        if any(
            candidate == existing or candidate.is_relative_to(existing)
            for existing in resolved
        ):
            continue
        resolved = [
            existing for existing in resolved if not existing.is_relative_to(candidate)
        ]
        resolved.append(candidate)
    return tuple(resolved)


def _device_id(path: Path) -> int:
    return path.stat().st_dev


def _validated_scratch_roots(
    storage_root: Path, scratch_roots: Sequence[Path]
) -> tuple[Path, ...]:
    resolved_storage = storage_root.resolve(strict=True)
    resolved: list[Path] = []
    for root in scratch_roots:
        if not root.is_absolute() or root.is_symlink():
            raise DatabaseError(f"database command scratch root is unsafe: {root}")
        try:
            candidate = root.resolve(strict=True)
        except OSError as error:
            raise DatabaseError(
                f"database command scratch root is missing: {root}"
            ) from error
        if not candidate.is_dir() or candidate != root:
            raise DatabaseError(f"database command scratch root is unsafe: {root}")
        if (
            candidate == resolved_storage
            or candidate.is_relative_to(resolved_storage)
            or resolved_storage.is_relative_to(candidate)
        ):
            raise DatabaseError(
                f"database command scratch root overlaps storage: {root}"
            )
        if any(
            candidate == existing or candidate.is_relative_to(existing)
            for existing in resolved
        ):
            continue
        resolved = [
            existing for existing in resolved if not existing.is_relative_to(candidate)
        ]
        resolved.append(candidate)
    return tuple(resolved)


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    """Terminate one isolated command process group, escalating after a grace period."""

    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired as error:
            raise OSError("process group survived SIGKILL") from error


def inventory_resource(
    root: Path, *, progress: bool = True
) -> tuple[list[FileRecord], str]:
    """Stream checksums for every resource file and write a stable inventory."""

    paths = iter_resource_files(root)
    total_bytes = sum(
        path.stat().st_size
        for path in paths
        if path.is_file() and not path.is_symlink()
    )
    records: list[FileRecord] = []
    with tqdm(
        total=total_bytes,
        desc=f"Inventory {root.name}",
        unit="B",
        unit_scale=True,
        disable=not progress,
    ) as progress_bar:
        for path in paths:
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                target = path.readlink().as_posix()
                _safe_symlink_target(root, path, target)
                records.append(
                    FileRecord(
                        path=relative,
                        size_bytes=0,
                        sha256=sha256(target.encode("utf-8")).hexdigest(),
                        kind="symlink",
                        symlink_target=target,
                    )
                )
                continue
            size = path.stat().st_size
            records.append(
                FileRecord(
                    path=relative,
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


def copy_inventoried_resource(
    source: Path,
    destination: Path,
    records: Sequence[FileRecord],
    expected_digest: str,
    *,
    storage_root: Path,
    storage_limit_bytes: int,
    minimum_free_bytes: int,
    progress: bool = True,
) -> tuple[int, int]:
    """Copy a scratch-built resource once and fully verify the durable copy."""

    if source.is_symlink() or not source.is_dir():
        raise DatabaseError(f"resource copy source is unsafe: {source}")
    if destination.is_symlink() or not destination.is_dir():
        raise DatabaseError(f"resource copy destination is unsafe: {destination}")
    try:
        destination.resolve(strict=True).relative_to(storage_root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise DatabaseError(
            f"resource copy destination escapes durable storage: {destination}"
        ) from error
    try:
        source.resolve(strict=True).relative_to(storage_root.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise DatabaseError("resource copy source must use external build scratch")
    if any(destination.iterdir()):
        raise DatabaseError(f"resource copy destination is not empty: {destination}")
    inventory_path = source / ".gtd-inventory.json"
    inventory_document = _load_json_document(
        inventory_path, "scratch resource inventory"
    )
    if canonical_digest(inventory_document) != expected_digest:
        raise DatabaseError(f"scratch resource inventory digest mismatch: {source}")
    expected_inventory = {
        "schema_version": "1.0",
        "files": [asdict(record) for record in records],
    }
    if inventory_document != expected_inventory:
        raise DatabaseError("scratch resource records do not match their inventory")
    total_bytes = sum(record.size_bytes for record in records)
    scratch_bytes = tree_size(source)
    used_bytes = enforce_storage_limit(storage_root, storage_limit_bytes)
    free_bytes = enforce_free_space(storage_root, minimum_free_bytes)
    prospective_bytes = used_bytes + scratch_bytes + total_bytes
    if prospective_bytes > storage_limit_bytes:
        raise StorageLimitError(
            "build scratch plus durable copy-back would use "
            f"{prospective_bytes} bytes, exceeding the "
            f"{storage_limit_bytes}-byte project cap"
        )
    if free_bytes - total_bytes < minimum_free_bytes:
        raise StorageLimitError(
            f"copying {total_bytes} bytes would leave less than "
            f"{minimum_free_bytes} bytes free"
        )
    _LOGGER.info(
        "database resource copy-back started",
        extra={
            "source": str(source),
            "destination": str(destination),
            "file_count": len(records),
            "total_bytes": total_bytes,
            "scratch_bytes": scratch_bytes,
            "storage_used_bytes": used_bytes,
            "storage_limit_bytes": storage_limit_bytes,
            "prospective_storage_bytes": prospective_bytes,
        },
    )
    copied_bytes = 0
    next_log_bytes = 1 << 30
    with tqdm(
        total=total_bytes,
        desc=f"Publish {destination.parent.name}",
        unit="B",
        unit_scale=True,
        disable=not progress,
    ) as progress_bar:
        for record in records:
            source_path = _safe_relative_path(source, record.path)
            destination_path = _safe_relative_path(destination, record.path)
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            if record.kind == "symlink":
                if record.symlink_target is None or not source_path.is_symlink():
                    raise DatabaseError(
                        f"scratch resource symlink changed during copy: {source_path}"
                    )
                actual_target = source_path.readlink().as_posix()
                _safe_symlink_target(source, source_path, actual_target)
                if (
                    actual_target != record.symlink_target
                    or sha256(actual_target.encode("utf-8")).hexdigest()
                    != record.sha256
                ):
                    raise DatabaseError(
                        f"scratch resource symlink changed during copy: {source_path}"
                    )
                destination_path.symlink_to(actual_target)
                continue
            if source_path.is_symlink() or not source_path.is_file():
                raise DatabaseError(
                    f"scratch resource file changed during copy: {source_path}"
                )
            digest = sha256()
            copied_file_bytes = 0
            with (
                source_path.open("rb") as input_handle,
                destination_path.open("xb") as output_handle,
            ):
                while chunk := input_handle.read(1024 * 1024):
                    output_handle.write(chunk)
                    digest.update(chunk)
                    chunk_bytes = len(chunk)
                    copied_file_bytes += chunk_bytes
                    copied_bytes += chunk_bytes
                    progress_bar.update(chunk_bytes)
                    if copied_bytes >= next_log_bytes:
                        current_free = shutil.disk_usage(storage_root).free
                        _LOGGER.info(
                            "database resource copy-back progress",
                            extra={
                                "destination": str(destination),
                                "copied_bytes": copied_bytes,
                                "total_bytes": total_bytes,
                                "free_bytes": current_free,
                                "minimum_free_bytes": minimum_free_bytes,
                            },
                        )
                        if current_free < minimum_free_bytes:
                            raise StorageLimitError(
                                "database filesystem lost required headroom during "
                                "resource copy-back"
                            )
                        next_log_bytes += 1 << 30
            if (
                copied_file_bytes != record.size_bytes
                or digest.hexdigest() != record.sha256
            ):
                raise DatabaseError(
                    f"scratch resource file changed during copy: {source_path}"
                )
            shutil.copymode(source_path, destination_path)
    atomic_write_json(destination / ".gtd-inventory.json", inventory_document)
    file_count, verified_bytes = verify_inventory(
        destination,
        expected_digest,
        full_checksums=True,
        progress=progress,
    )
    if file_count != len(records) or verified_bytes != total_bytes:
        raise DatabaseError(f"durable resource copy summary mismatch: {destination}")
    enforce_storage_limit(storage_root, storage_limit_bytes)
    enforce_free_space(storage_root, minimum_free_bytes)
    _LOGGER.info(
        "database resource copy-back complete",
        extra={
            "source": str(source),
            "destination": str(destination),
            "file_count": file_count,
            "total_bytes": verified_bytes,
            "manifest_sha256": expected_digest,
        },
    )
    return file_count, verified_bytes


def verify_inventory(
    root: Path,
    expected_digest: str,
    *,
    full_checksums: bool,
    progress: bool = True,
) -> tuple[int, int]:
    """Verify a stored inventory using sizes and optional full SHA-256 checks."""

    inventory_path = root / ".gtd-inventory.json"
    document = _load_json_document(inventory_path, "resource inventory")
    if not isinstance(document, dict):
        raise DatabaseError(f"resource inventory is not an object: {inventory_path}")
    if canonical_digest(document) != expected_digest:
        raise DatabaseError(f"inventory digest mismatch for {root}")
    raw_records = document.get("files")
    if not isinstance(raw_records, list) or not raw_records:
        raise DatabaseError(f"resource inventory has no files: {inventory_path}")
    actual_paths = {
        path.relative_to(root).as_posix() for path in iter_resource_files(root)
    }
    recorded_paths: set[str] = set()
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
        kind = raw.get("kind", "file")
        symlink_target = raw.get("symlink_target")
        if (
            not isinstance(relative, str)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or kind not in {"file", "symlink"}
        ):
            raise DatabaseError(f"invalid inventory record in {inventory_path}")
        if relative in recorded_paths:
            raise DatabaseError(f"duplicate resource inventory path: {relative}")
        recorded_paths.add(relative)
        path = _safe_relative_path(root, relative)
        if kind == "symlink":
            if not isinstance(symlink_target, str) or size != 0:
                raise DatabaseError(f"invalid symlink inventory record: {path}")
            if not path.is_symlink():
                raise DatabaseError(f"resource symlink is missing: {path}")
            actual_target = path.readlink().as_posix()
            _safe_symlink_target(root, path, actual_target)
            if actual_target != symlink_target:
                raise DatabaseError(f"resource symlink target mismatch: {path}")
            if sha256(actual_target.encode("utf-8")).hexdigest() != digest:
                raise DatabaseError(f"resource symlink digest mismatch: {path}")
            continue
        if symlink_target is not None:
            raise DatabaseError(f"regular file has a symlink target: {path}")
        if not path.is_file() or path.is_symlink():
            raise DatabaseError(f"resource file is missing or unsafe: {path}")
        try:
            path.resolve(strict=True).relative_to(root.resolve(strict=True))
        except (OSError, ValueError) as error:
            raise DatabaseError(f"resource file escapes its root: {path}") from error
        actual_size = path.stat().st_size
        if actual_size != size:
            raise DatabaseError(
                f"resource file size mismatch for {path}: "
                f"expected {size}, found {actual_size}"
            )
        if full_checksums and sha256_file(path, logger=_LOGGER) != digest:
            raise DatabaseError(f"resource checksum mismatch for {path}")
        total_bytes += actual_size
    if recorded_paths != actual_paths:
        unexpected = sorted(actual_paths - recorded_paths)
        missing = sorted(recorded_paths - actual_paths)
        details = []
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected[:10]))
        if missing:
            details.append("missing=" + ",".join(missing[:10]))
        raise DatabaseError(
            "resource inventory path set mismatch: " + "; ".join(details)
        )
    return len(raw_records), total_bytes


def tool_version(
    executable: str,
    *,
    arguments: Sequence[str] = ("--version",),
    timeout_seconds: float | None = None,
) -> str:
    """Return the first version line using the tool's documented invocation."""

    if not executable:
        raise ValueError("version-probe executable must not be empty")
    if not arguments or any(not argument for argument in arguments):
        raise ValueError("version-probe arguments must not be empty")
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("version-probe timeout must be positive")
    command = [executable, *arguments]
    started = monotonic()
    _LOGGER.info(
        "version probe started",
        extra={"command": command, "timeout_seconds": timeout_seconds},
    )
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        if timeout_seconds is None:
            raise AssertionError(
                "unbounded version probe reported a timeout"
            ) from error
        raise DatabaseError(
            f"version probe timed out after {timeout_seconds:g} seconds: "
            f"{' '.join(command)}"
        ) from error
    except OSError as error:
        raise DatabaseError(
            f"cannot execute version probe for {executable}: {error}"
        ) from error
    if completed.returncode != 0:
        raise DatabaseError(
            f"cannot determine {executable} version (exit {completed.returncode})"
        )
    output = f"{completed.stdout}\n{completed.stderr}"
    line = next((item.strip() for item in output.splitlines() if item.strip()), "")
    if not line:
        raise DatabaseError(
            f"version probe returned no version text: {' '.join(command)}"
        )
    _LOGGER.info(
        "version probe completed",
        extra={
            "command": command,
            "elapsed_seconds": monotonic() - started,
            "version": line,
        },
    )
    return line


def run_command(
    command: Sequence[str],
    *,
    log_path: Path,
    storage_root: Path,
    write_roots: Sequence[Path],
    storage_limit_bytes: int,
    minimum_free_bytes: int,
    progress: bool,
    scratch_roots: Sequence[Path] = (),
    minimum_scratch_free_bytes: int = 0,
    watchdog_interval_seconds: float = 20.0,
    environment_overrides: Mapping[str, str] | None = None,
) -> None:
    """Run an argument array with scoped storage and process-group safeguards."""

    if not command:
        raise ValueError("database command must not be empty")
    if watchdog_interval_seconds <= 0:
        raise ValueError("watchdog interval must be positive")
    if scratch_roots and minimum_scratch_free_bytes <= 0:
        raise ValueError("scratch minimum free bytes must be positive")
    if not scratch_roots and minimum_scratch_free_bytes != 0:
        raise ValueError("scratch headroom requires an explicit scratch root")
    if environment_overrides is not None and any(
        not key or "=" in key or "\0" in key or "\0" in value
        for key, value in environment_overrides.items()
    ):
        raise ValueError("database command environment override is invalid")
    child_environment = None
    if environment_overrides:
        child_environment = os.environ.copy()
        child_environment.update(environment_overrides)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    scoped_roots = _validated_write_roots(storage_root, write_roots)
    scoped_scratch = _validated_scratch_roots(storage_root, scratch_roots)
    initial_used = enforce_storage_limit(storage_root, storage_limit_bytes)
    enforce_free_space(storage_root, minimum_free_bytes)
    for scratch_root in scoped_scratch:
        _enforce_scratch_free_space(scratch_root, minimum_scratch_free_bytes)
    initial_scratch = sum(tree_size(root) for root in scoped_scratch)
    if initial_used + initial_scratch > storage_limit_bytes:
        raise StorageLimitError(
            "database root and build scratch use "
            f"{initial_used + initial_scratch} bytes, exceeding the "
            f"{storage_limit_bytes}-byte cap"
        )
    initial_scoped = sum(tree_size(root) for root in scoped_roots)
    initial_log_bytes = log_path.stat().st_size if log_path.is_file() else 0
    inactive_bytes = max(initial_used - initial_scoped - initial_log_bytes, 0)
    _LOGGER.info(
        "starting database command",
        extra={
            "command": list(command),
            "log": str(log_path),
            "write_roots": [str(root) for root in scoped_roots],
            "scratch_roots": [str(root) for root in scoped_scratch],
            "environment_override_keys": sorted(environment_overrides or ()),
            "inactive_bytes": inactive_bytes,
            "initial_scratch_bytes": initial_scratch,
        },
    )
    stop = threading.Event()
    exceeded = threading.Event()
    scratch_exceeded = threading.Event()
    watchdog_failed = threading.Event()
    watchdog_message: list[str] = []
    process: subprocess.Popen[str]

    def stop_process_group() -> None:
        try:
            _terminate_process_group(process)
        except OSError as error:
            watchdog_message.append(f"cannot stop process group: {error}")
            watchdog_failed.set()

    def watch_storage() -> None:
        while not stop.wait(watchdog_interval_seconds):
            try:
                scoped_bytes = sum(tree_size(root) for root in scoped_roots)
                log_bytes = log_path.stat().st_size if log_path.is_file() else 0
                scratch_bytes = sum(tree_size(root) for root in scoped_scratch)
                used = inactive_bytes + scoped_bytes + scratch_bytes + log_bytes
                free_bytes = shutil.disk_usage(storage_root).free
                scratch_free_bytes = min(
                    (shutil.disk_usage(root).free for root in scoped_scratch),
                    default=0,
                )
            except OSError as error:
                _LOGGER.error("storage watchdog failed", extra={"error": str(error)})
                watchdog_message.append(str(error))
                watchdog_failed.set()
                stop_process_group()
                return
            _LOGGER.info(
                "database command storage progress",
                extra={
                    "used_bytes": used,
                    "limit_bytes": storage_limit_bytes,
                    "free_bytes": free_bytes,
                    "minimum_free_bytes": minimum_free_bytes,
                    "scoped_bytes": scoped_bytes,
                    "log_bytes": log_bytes,
                    "scratch_bytes": scratch_bytes,
                    "prospective_storage_bytes": used,
                    "scratch_free_bytes": scratch_free_bytes,
                    "minimum_scratch_free_bytes": minimum_scratch_free_bytes,
                },
            )
            if used > storage_limit_bytes or free_bytes < minimum_free_bytes:
                exceeded.set()
                stop_process_group()
                return
            if scoped_scratch and scratch_free_bytes < minimum_scratch_free_bytes:
                scratch_exceeded.set()
                stop_process_group()
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
            start_new_session=True,
            env=child_environment,
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
    if watchdog_failed.is_set():
        detail = watchdog_message[0] if watchdog_message else "unknown scan error"
        raise StorageWatchdogError(
            f"database storage watchdog failed: {detail}; see {log_path}"
        )
    if exceeded.is_set():
        raise StorageLimitError(
            "database command crossed its project cap or free-space headroom; "
            f"cap={storage_limit_bytes}, minimum_free={minimum_free_bytes}; "
            f"see {log_path}"
        )
    if scratch_exceeded.is_set():
        raise ScratchLimitError(
            "database command crossed its scratch free-space headroom; "
            f"minimum_free={minimum_scratch_free_bytes}; see {log_path}"
        )
    if returncode != 0:
        raise DatabaseCommandError(command, returncode, log_path)
    enforce_storage_limit(storage_root, storage_limit_bytes)
    enforce_free_space(storage_root, minimum_free_bytes)
    for scratch_root in scoped_scratch:
        _enforce_scratch_free_space(scratch_root, minimum_scratch_free_bytes)
