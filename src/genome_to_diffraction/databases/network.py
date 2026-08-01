"""Bounded, resumable public-resource download for explicit database preparation."""

import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

from genome_to_diffraction.databases.common import (
    DatabaseError,
    enforce_storage_limit,
)

_LOGGER = logging.getLogger("genome_to_diffraction.databases")


@dataclass(frozen=True)
class DownloadMetadata:
    """HTTP provenance retained for an immutable downloaded snapshot."""

    url: str
    etag: str | None
    last_modified: str | None
    content_type: str | None


def download_public_resource(
    url: str,
    destination: Path,
    *,
    storage_root: Path,
    storage_limit_bytes: int,
    progress: bool,
    retries: int = 3,
) -> DownloadMetadata:
    """Download to ``.partial``, resume by byte range, and atomically promote."""

    if retries < 1:
        raise ValueError("download retries must be positive")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.name}.partial")
    _LOGGER.info(
        "downloading public database resource",
        extra={"url": url, "destination": str(destination)},
    )
    for attempt in range(1, retries + 1):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "nf-genome-to-diffraction/0.1"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = getattr(response, "status", 200)
                if offset and status != 206:
                    offset = 0
                mode = "ab" if offset else "wb"
                remaining = response.headers.get("Content-Length")
                total = offset + int(remaining) if remaining is not None else None
                with (
                    partial.open(mode) as handle,
                    tqdm(
                        total=total,
                        initial=offset,
                        desc=f"Download {destination.name}",
                        unit="B",
                        unit_scale=True,
                        disable=not progress,
                    ) as progress_bar,
                ):
                    bytes_since_storage_check = 0
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                        progress_bar.update(len(chunk))
                        bytes_since_storage_check += len(chunk)
                        if bytes_since_storage_check >= 1024**3:
                            enforce_storage_limit(storage_root, storage_limit_bytes)
                            bytes_since_storage_check = 0
                    handle.flush()
                    os.fsync(handle.fileno())
                enforce_storage_limit(storage_root, storage_limit_bytes)
                metadata = DownloadMetadata(
                    url=url,
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                    content_type=response.headers.get("Content-Type"),
                )
            os.replace(partial, destination)
            return metadata
        except (OSError, urllib.error.URLError) as error:
            _LOGGER.warning(
                "database download attempt failed",
                extra={"attempt": attempt, "error": str(error), "url": url},
            )
            if attempt == retries:
                raise DatabaseError(
                    f"download failed after {retries} attempts: {url}: {error}"
                ) from error
            time.sleep(2 ** (attempt - 1))
    raise AssertionError("download retry loop exited unexpectedly")
