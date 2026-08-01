"""Concurrent-safe initialisation of the content-addressed coordinate cache.

The cache is initially empty and mutable by design. Provider objects are written
atomically elsewhere; this module creates and verifies only the stable namespace,
lock, temporary-download, metadata, and digest-index layout.
"""

import fcntl
import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.databases.common import DatabaseError
from genome_to_diffraction.ids import canonical_digest

_LOGGER = logging.getLogger("genome_to_diffraction.databases")
_PROVIDERS = ("pdb", "afdb", "esm_atlas")


@contextmanager
def exclusive_lock(
    path: Path, *, timeout_seconds: float = 30.0, progress: bool = True
) -> Iterator[None]:
    """Acquire an automatically released POSIX advisory lock with a timeout."""

    deadline = time.monotonic() + timeout_seconds
    path.parent.mkdir(parents=True, exist_ok=True)
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
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
