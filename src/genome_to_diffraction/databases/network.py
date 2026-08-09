"""Bounded, resumable public-resource download for explicit database preparation."""

import hashlib
import http.client
import json
import logging
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.databases.cache import exclusive_lock
from genome_to_diffraction.databases.common import (
    DatabaseError,
    StorageLimitError,
    enforce_free_space,
    enforce_storage_limit,
)

_LOGGER = logging.getLogger("genome_to_diffraction.databases")
_CONTENT_RANGE = re.compile(
    r"^bytes (?P<start>[0-9]+)-(?P<end>[0-9]+)/(?P<total>[0-9]+)$"
)
_USER_AGENT = "nf-genome-to-diffraction/0.1"


@dataclass(frozen=True)
class DownloadMetadata:
    """HTTP provenance retained for an immutable downloaded snapshot."""

    requested_url: str
    url: str
    etag: str | None
    last_modified: str | None
    content_type: str | None
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class _PartialState:
    requested_url: str
    resolved_url: str
    validator_header: str | None
    validator_value: str | None
    total_bytes: int | None
    completed_bytes: int
    prefix_sha256: str
    etag: str | None
    last_modified: str | None
    content_type: str | None

    def as_json(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "requested_url": self.requested_url,
            "resolved_url": self.resolved_url,
            "validator_header": self.validator_header,
            "validator_value": self.validator_value,
            "total_bytes": self.total_bytes,
            "completed_bytes": self.completed_bytes,
            "prefix_sha256": self.prefix_sha256,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "content_type": self.content_type,
        }


def _optional_header(headers: Mapping[str, str], name: str) -> str | None:
    value = next(
        (value for key, value in headers.items() if key.casefold() == name.casefold()),
        None,
    )
    return value if value else None


def _select_validator(
    etag: str | None, last_modified: str | None
) -> tuple[str | None, str | None]:
    if etag is not None and not etag.strip().casefold().startswith("w/"):
        return "ETag", etag
    if last_modified is not None:
        return "Last-Modified", last_modified
    return None, None


def _parse_nonnegative_integer(value: object, *, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DatabaseError(f"invalid partial-download {label}")
    return value


def _load_partial_state(path: Path, *, requested_url: str) -> _PartialState:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatabaseError("invalid partial-download state") from error
    if not isinstance(raw, dict) or raw.get("schema_version") != "1.0":
        raise DatabaseError("invalid partial-download state")
    allowed = {
        "schema_version",
        "requested_url",
        "resolved_url",
        "validator_header",
        "validator_value",
        "total_bytes",
        "completed_bytes",
        "prefix_sha256",
        "etag",
        "last_modified",
        "content_type",
    }
    if set(raw) != allowed:
        raise DatabaseError("invalid partial-download state fields")

    def optional_text(key: str) -> str | None:
        value = raw[key]
        if value is not None and not isinstance(value, str):
            raise DatabaseError(f"invalid partial-download {key}")
        return value

    state_requested_url = raw.get("requested_url")
    resolved_url = raw.get("resolved_url")
    if (
        not isinstance(state_requested_url, str)
        or state_requested_url != requested_url
        or not isinstance(resolved_url, str)
        or not resolved_url
    ):
        raise DatabaseError("partial-download URL does not match the request")
    validator_header = optional_text("validator_header")
    validator_value = optional_text("validator_value")
    if (validator_header, validator_value) == (None, None):
        pass
    elif (
        validator_header not in {"ETag", "Last-Modified"}
        or validator_value is None
        or not validator_value
    ):
        raise DatabaseError("invalid partial-download validator")
    completed_bytes = _parse_nonnegative_integer(
        raw.get("completed_bytes"), label="completed_bytes"
    )
    prefix_sha256 = raw.get("prefix_sha256")
    if completed_bytes is None or not isinstance(prefix_sha256, str):
        raise DatabaseError("invalid partial-download prefix record")
    return _PartialState(
        requested_url=state_requested_url,
        resolved_url=resolved_url,
        validator_header=validator_header,
        validator_value=validator_value,
        total_bytes=_parse_nonnegative_integer(
            raw.get("total_bytes"), label="total_bytes"
        ),
        completed_bytes=completed_bytes,
        prefix_sha256=prefix_sha256,
        etag=optional_text("etag"),
        last_modified=optional_text("last_modified"),
        content_type=optional_text("content_type"),
    )


def _clear_partial(partial: Path, state_path: Path, *, reason: str) -> None:
    if partial.exists() or state_path.exists():
        _LOGGER.warning(
            "restarting partial database download",
            extra={"partial": str(partial), "reason": reason},
        )
    partial.unlink(missing_ok=True)
    state_path.unlink(missing_ok=True)


def _resume_state(
    partial: Path, state_path: Path, *, requested_url: str, progress: bool
) -> tuple[int, _PartialState | None, _HashState]:
    if not partial.exists() and not state_path.exists():
        return 0, None, hashlib.sha256()
    if partial.is_symlink() or state_path.is_symlink():
        raise DatabaseError("partial-download state pair must not contain symlinks")
    if (partial.exists() and not partial.is_file()) or (
        state_path.exists() and not state_path.is_file()
    ):
        raise DatabaseError("partial-download state pair is not regular files")
    if not partial.is_file() or not state_path.is_file():
        _clear_partial(partial, state_path, reason="missing or unsafe state pair")
        return 0, None, hashlib.sha256()
    try:
        state = _load_partial_state(state_path, requested_url=requested_url)
    except DatabaseError as error:
        _clear_partial(partial, state_path, reason=str(error))
        return 0, None, hashlib.sha256()
    offset = partial.stat().st_size
    if (
        len(state.prefix_sha256) != 64
        or any(character not in "0123456789abcdef" for character in state.prefix_sha256)
        or state.completed_bytes != offset
    ):
        _clear_partial(partial, state_path, reason="partial prefix record mismatch")
        return 0, None, hashlib.sha256()
    digest, prefix_hash = _hash_partial(partial, progress=progress)
    if digest != state.prefix_sha256:
        _clear_partial(partial, state_path, reason="partial prefix checksum mismatch")
        return 0, None, hashlib.sha256()
    if offset == 0 or state.validator_value is None:
        _clear_partial(partial, state_path, reason="no resumable validator")
        return 0, None, hashlib.sha256()
    if state.total_bytes is not None and offset >= state.total_bytes:
        _clear_partial(partial, state_path, reason="partial size is not below total")
        return 0, None, hashlib.sha256()
    return offset, state, prefix_hash


def _content_length(headers: Mapping[str, str]) -> int | None:
    raw = _optional_header(headers, "Content-Length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError as error:
        raise DatabaseError("download response has invalid Content-Length") from error
    if value < 0:
        raise DatabaseError("download response has negative Content-Length")
    return value


def _response_state(
    *,
    requested_url: str,
    resolved_url: str,
    headers: Mapping[str, str],
    total_bytes: int | None,
    completed_bytes: int,
    prefix_sha256: str,
) -> _PartialState:
    etag = _optional_header(headers, "ETag")
    last_modified = _optional_header(headers, "Last-Modified")
    validator_header, validator_value = _select_validator(etag, last_modified)
    return _PartialState(
        requested_url=requested_url,
        resolved_url=resolved_url,
        validator_header=validator_header,
        validator_value=validator_value,
        total_bytes=total_bytes,
        completed_bytes=completed_bytes,
        prefix_sha256=prefix_sha256,
        etag=etag,
        last_modified=last_modified,
        content_type=_optional_header(headers, "Content-Type"),
    )


def _validate_partial_response(
    *,
    offset: int,
    state: _PartialState,
    resolved_url: str,
    headers: Mapping[str, str],
) -> int:
    if resolved_url != state.resolved_url:
        raise DatabaseError("resumed download resolved to a different URL")
    if state.validator_header is None or state.validator_value is None:
        raise AssertionError("resumed download lacks its validated If-Range value")
    if _optional_header(headers, state.validator_header) != state.validator_value:
        raise DatabaseError("resumed download validator changed unexpectedly")
    raw_range = _optional_header(headers, "Content-Range")
    match = _CONTENT_RANGE.fullmatch(raw_range or "")
    if match is None:
        raise DatabaseError("resumed download lacks a valid Content-Range")
    start = int(match.group("start"))
    end = int(match.group("end"))
    total = int(match.group("total"))
    if start != offset or end < start or total <= end:
        raise DatabaseError("resumed download Content-Range is inconsistent")
    if state.total_bytes is not None and total != state.total_bytes:
        raise DatabaseError("resumed download total size changed unexpectedly")
    content_length = _content_length(headers)
    if content_length is not None and content_length != end - start + 1:
        raise DatabaseError("resumed download Content-Length is inconsistent")
    return total


class _HashState(Protocol):
    def update(self, data: bytes, /) -> None: ...

    def hexdigest(self) -> str: ...


def _hash_partial(path: Path, *, progress: bool) -> tuple[str, _HashState]:
    digest = hashlib.sha256()
    total_bytes = path.stat().st_size
    processed_bytes = 0
    next_log_bytes = 1024**3
    _LOGGER.info(
        "partial-download prefix verification started",
        extra={"path": str(path), "total_bytes": total_bytes},
    )
    with (
        path.open("rb") as handle,
        tqdm(
            total=total_bytes,
            desc=f"Verify partial {path.name}",
            unit="B",
            unit_scale=True,
            disable=not progress,
        ) as progress_bar,
    ):
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            processed_bytes += len(chunk)
            progress_bar.update(len(chunk))
            if processed_bytes >= next_log_bytes:
                _LOGGER.info(
                    "partial-download prefix verification progress",
                    extra={
                        "path": str(path),
                        "processed_bytes": processed_bytes,
                        "total_bytes": total_bytes,
                    },
                )
                next_log_bytes += 1024**3
    result = digest.hexdigest()
    _LOGGER.info(
        "partial-download prefix verification complete",
        extra={"path": str(path), "total_bytes": total_bytes, "sha256": result},
    )
    return result, digest


def _checkpoint_partial(
    *,
    handle: Any,
    state_path: Path,
    state: _PartialState,
    completed_bytes: int,
    digest: _HashState,
) -> _PartialState:
    handle.flush()
    os.fsync(handle.fileno())
    updated = replace(
        state,
        completed_bytes=completed_bytes,
        prefix_sha256=digest.hexdigest(),
    )
    atomic_write_json(state_path, updated.as_json())
    return updated


def download_public_resource(
    url: str,
    destination: Path,
    *,
    storage_root: Path,
    storage_limit_bytes: int,
    minimum_free_bytes: int,
    progress: bool,
    retries: int = 3,
) -> DownloadMetadata:
    """Download atomically, resuming only a validator-bound verified prefix."""

    if retries < 1:
        raise ValueError("download retries must be positive")
    try:
        destination.absolute().relative_to(storage_root.absolute())
    except ValueError as error:
        raise DatabaseError("download destination escapes the storage root") from error
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise DatabaseError(f"download destination is unsafe: {destination}")
    try:
        destination.parent.resolve(strict=True).relative_to(
            storage_root.resolve(strict=True)
        )
    except (OSError, ValueError) as error:
        raise DatabaseError("download destination escapes the storage root") from error
    partial = destination.with_name(f".{destination.name}.partial")
    state_path = destination.with_name(f".{destination.name}.partial.json")
    destination_identity = destination.parent.resolve(strict=True) / destination.name
    lock_name = hashlib.sha256(str(destination_identity).encode("utf-8")).hexdigest()
    lock_path = storage_root / "tmp" / "download-locks" / f"{lock_name}.lock"
    _LOGGER.info(
        "downloading public database resource",
        extra={"url": url, "destination": str(destination)},
    )
    with exclusive_lock(lock_path, timeout_seconds=30.0, progress=progress):
        initial_partial_bytes = (
            partial.stat().st_size
            if partial.is_file() and not partial.is_symlink()
            else 0
        )
        initial_state_bytes = (
            state_path.stat().st_size
            if state_path.is_file() and not state_path.is_symlink()
            else 0
        )
        initial_used = enforce_storage_limit(storage_root, storage_limit_bytes)
        enforce_free_space(storage_root, minimum_free_bytes)
        inactive_bytes = max(
            initial_used - initial_partial_bytes - initial_state_bytes, 0
        )

        def enforce_active_limit(
            next_partial_bytes: int, *, pending_bytes: int = 0
        ) -> None:
            if pending_bytes < 0:
                raise ValueError("pending download bytes must not be negative")
            state_bytes = (
                state_path.stat().st_size
                if state_path.is_file() and not state_path.is_symlink()
                else 0
            )
            estimated = inactive_bytes + next_partial_bytes + state_bytes
            if estimated > storage_limit_bytes:
                raise StorageLimitError(
                    "database download would cross the configured project cap: "
                    f"{estimated} > {storage_limit_bytes} bytes"
                )
            free_bytes = shutil.disk_usage(storage_root).free
            if free_bytes - pending_bytes < minimum_free_bytes:
                raise StorageLimitError(
                    f"database filesystem has {free_bytes} free bytes before a "
                    f"{pending_bytes}-byte write; {minimum_free_bytes} must remain"
                )

        for attempt in range(1, retries + 1):
            offset, prior_state, prefix_hash = _resume_state(
                partial, state_path, requested_url=url, progress=progress
            )
            request_headers = {
                "User-Agent": _USER_AGENT,
                "Accept-Encoding": "identity",
            }
            if offset:
                if prior_state is None or prior_state.validator_value is None:
                    raise AssertionError("resume offset lacks validated state")
                request_headers["Range"] = f"bytes={offset}-"
                request_headers["If-Range"] = prior_state.validator_value
            request = urllib.request.Request(url, headers=request_headers)
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    status_value = getattr(response, "status", None)
                    status = 200 if status_value is None else int(status_value)
                    response_headers = {
                        str(key): str(value) for key, value in response.headers.items()
                    }
                    content_encoding = _optional_header(
                        response_headers, "Content-Encoding"
                    )
                    if (
                        content_encoding is not None
                        and content_encoding.casefold() != "identity"
                    ):
                        raise DatabaseError(
                            "database download ignored identity content encoding"
                        )
                    resolved_url = str(response.geturl())
                    if url.casefold().startswith("https://") and not (
                        resolved_url.casefold().startswith("https://")
                    ):
                        raise DatabaseError("database download redirected below HTTPS")
                    total: int | None
                    if offset and status == 206:
                        if prior_state is None:
                            raise AssertionError("partial response lacks prior state")
                        total = _validate_partial_response(
                            offset=offset,
                            state=prior_state,
                            resolved_url=resolved_url,
                            headers=response_headers,
                        )
                        mode = "ab"
                        state = _response_state(
                            requested_url=url,
                            resolved_url=resolved_url,
                            headers=response_headers,
                            total_bytes=total,
                            completed_bytes=offset,
                            prefix_sha256=prefix_hash.hexdigest(),
                        )
                    elif status == 200:
                        if offset:
                            _LOGGER.info(
                                "server declined partial resume; restarting response",
                                extra={"url": url, "offset": offset},
                            )
                        offset = 0
                        prefix_hash = hashlib.sha256()
                        total = _content_length(response_headers)
                        mode = "wb"
                        state = _response_state(
                            requested_url=url,
                            resolved_url=resolved_url,
                            headers=response_headers,
                            total_bytes=total,
                            completed_bytes=0,
                            prefix_sha256=prefix_hash.hexdigest(),
                        )
                    else:
                        raise DatabaseError(
                            f"unexpected database download HTTP status: {status}"
                        )
                    atomic_write_json(state_path, state.as_json())
                    enforce_active_limit(offset)
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
                        completed = offset
                        bytes_since_checkpoint = 0
                        next_log_bytes = ((completed // (1024**3)) + 1) * 1024**3
                        try:
                            while True:
                                read_error: http.client.IncompleteRead | None = None
                                try:
                                    chunk = response.read(1024 * 1024)
                                except http.client.IncompleteRead as error:
                                    chunk = error.partial
                                    read_error = error
                                if chunk:
                                    enforce_active_limit(
                                        completed + len(chunk),
                                        pending_bytes=len(chunk),
                                    )
                                    handle.write(chunk)
                                    prefix_hash.update(chunk)
                                    completed += len(chunk)
                                    bytes_since_checkpoint += len(chunk)
                                    progress_bar.update(len(chunk))
                                    if completed >= next_log_bytes:
                                        _LOGGER.info(
                                            "database download progress",
                                            extra={
                                                "requested_url": url,
                                                "resolved_url": resolved_url,
                                                "completed_bytes": completed,
                                                "total_bytes": total,
                                            },
                                        )
                                        next_log_bytes += 1024**3
                                    if bytes_since_checkpoint >= 64 * 1024 * 1024:
                                        state = _checkpoint_partial(
                                            handle=handle,
                                            state_path=state_path,
                                            state=state,
                                            completed_bytes=completed,
                                            digest=prefix_hash,
                                        )
                                        bytes_since_checkpoint = 0
                                if read_error is not None:
                                    raise read_error
                                if not chunk:
                                    break
                        finally:
                            state = _checkpoint_partial(
                                handle=handle,
                                state_path=state_path,
                                state=state,
                                completed_bytes=completed,
                                digest=prefix_hash,
                            )
                    if total is not None and completed != total:
                        raise OSError(
                            "database download ended before its advertised total: "
                            f"{completed} != {total}"
                        )
                    if partial.stat().st_size != state.completed_bytes:
                        raise DatabaseError(
                            "partial-download size changed before atomic promotion"
                        )
                    metadata = DownloadMetadata(
                        requested_url=url,
                        url=resolved_url,
                        etag=state.etag,
                        last_modified=state.last_modified,
                        content_type=state.content_type,
                        size_bytes=completed,
                        sha256=state.prefix_sha256,
                    )
                os.replace(partial, destination)
                state_path.unlink(missing_ok=True)
                enforce_storage_limit(storage_root, storage_limit_bytes)
                enforce_free_space(storage_root, minimum_free_bytes)
                return metadata
            except urllib.error.HTTPError as error:
                if error.code in {412, 416}:
                    _clear_partial(
                        partial,
                        state_path,
                        reason=f"server rejected byte resume with HTTP {error.code}",
                    )
                caught: BaseException = error
            except (OSError, urllib.error.URLError, http.client.HTTPException) as error:
                caught = error
            _LOGGER.warning(
                "database download attempt failed",
                extra={"attempt": attempt, "error": str(caught), "url": url},
            )
            if attempt == retries:
                raise DatabaseError(
                    f"download failed after {retries} attempts: {url}: {caught}"
                ) from caught
            time.sleep(2 ** (attempt - 1))
    raise AssertionError("download retry loop exited unexpectedly")
