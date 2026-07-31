"""Streaming checksums and atomic file writes."""

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

DEFAULT_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """Calculate a SHA-256 digest without loading the full file into memory."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
