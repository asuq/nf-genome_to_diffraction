"""Streaming checksums and atomic file writes."""

import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tqdm import tqdm

DEFAULT_CHUNK_SIZE = 1024 * 1024


def sha256_file(
    path: Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    progress: bool = False,
    description: str | None = None,
    logger: logging.Logger | None = None,
    log_interval_bytes: int = 1024 * 1024 * 1024,
) -> str:
    """Calculate SHA-256 with optional terminal and structured-log progress."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if log_interval_bytes < 1:
        raise ValueError("log_interval_bytes must be positive")

    digest = hashlib.sha256()
    total_bytes = path.stat().st_size
    progress_logger = logger if total_bytes >= log_interval_bytes else None
    processed_bytes = 0
    next_log_bytes = log_interval_bytes
    if progress_logger is not None:
        progress_logger.info(
            "checksum started",
            extra={"path": str(path), "total_bytes": total_bytes},
        )
    with (
        path.open("rb") as handle,
        tqdm(
            total=total_bytes,
            desc=description or f"Checksumming {path.name}",
            unit="B",
            unit_scale=True,
            disable=not progress,
        ) as progress_bar,
    ):
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
            processed_bytes += len(chunk)
            progress_bar.update(len(chunk))
            while progress_logger is not None and processed_bytes >= next_log_bytes:
                progress_logger.info(
                    "checksum progress",
                    extra={
                        "path": str(path),
                        "processed_bytes": processed_bytes,
                        "total_bytes": total_bytes,
                    },
                )
                next_log_bytes += log_interval_bytes
    result = digest.hexdigest()
    if progress_logger is not None:
        progress_logger.info(
            "checksum complete",
            extra={
                "path": str(path),
                "processed_bytes": processed_bytes,
                "total_bytes": total_bytes,
                "sha256": result,
            },
        )
    return result


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Atomically replace *path* with text using a temporary sibling file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Atomically replace *path* with binary content."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


JsonValue = (
    None | bool | int | float | str | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
)


def atomic_write_json(path: Path, value: JsonValue | Any) -> None:
    """Write human-readable JSON atomically with deterministic key ordering."""

    payload = json.dumps(
        value,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    atomic_write_text(path, f"{payload}\n")
