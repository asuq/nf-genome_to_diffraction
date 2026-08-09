"""HTTP-level tests for safe resumable public database downloads."""

import hashlib
import json
import socket
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from genome_to_diffraction.databases.common import DatabaseError, StorageLimitError
from genome_to_diffraction.databases.network import download_public_resource


@dataclass
class _HttpState:
    mode: str
    first_payload: bytes
    final_payload: bytes
    requests: list[dict[str, str]] = field(default_factory=list)
    request_count: int = 0


class _DownloadServer(ThreadingHTTPServer):
    download_state: _HttpState


class _DownloadHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _state(self) -> _HttpState:
        if not isinstance(self.server, _DownloadServer):
            raise AssertionError("test HTTP server lacks download state")
        return self.server.download_state

    def _headers(self, *, etag: str | None, length: int | None) -> None:
        if etag is not None:
            self.send_header("ETag", etag)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()

    def _truncate(self, payload: bytes, *, etag: str | None) -> None:
        cut = max(len(payload) // 3, 1)
        self.send_response(200)
        self._headers(etag=etag, length=len(payload))
        self.wfile.write(payload[:cut])
        self.wfile.flush()
        with suppress(OSError):
            self.connection.shutdown(socket.SHUT_RDWR)
        self.connection.close()

    def do_GET(self) -> None:
        state = self._state()
        state.request_count += 1
        state.requests.append({key: value for key, value in self.headers.items()})
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/data")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path != "/data":
            self.send_error(404)
            return

        if state.mode == "encoded":
            self.send_response(200)
            self.send_header("Content-Encoding", "GZip")
            self._headers(etag='"snapshot-v1"', length=len(state.final_payload))
            self.wfile.write(state.final_payload)
            return

        range_header = self.headers.get("Range")
        if (
            state.mode
            in {
                "resume",
                "changed",
                "malformed",
                "no-validator",
                "weak-validator",
                "416",
            }
            and state.request_count == 1
        ):
            etag = {
                "no-validator": None,
                "weak-validator": 'W/"snapshot-v1"',
            }.get(state.mode, '"snapshot-v1"')
            self._truncate(state.first_payload, etag=etag)
            return

        if state.mode == "changed" and range_header is not None:
            self.send_response(200)
            self._headers(etag='"snapshot-v2"', length=len(state.final_payload))
            self.wfile.write(state.final_payload)
            return
        if state.mode == "416" and range_header is not None:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{len(state.final_payload)}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if range_header is not None:
            offset = int(range_header.removeprefix("bytes=").removesuffix("-"))
            start = offset + 1 if state.mode == "malformed" else offset
            body = state.final_payload[offset:]
            self.send_response(206)
            self.send_header(
                "Content-Range",
                f"bytes {start}-{len(state.final_payload) - 1}/"
                f"{len(state.final_payload)}",
            )
            self._headers(etag='"snapshot-v1"', length=len(body))
            self.wfile.write(body)
            return

        self.send_response(200)
        content_length = (
            None if state.mode == "unknown-length" else len(state.final_payload)
        )
        self._headers(etag='"snapshot-v1"', length=content_length)
        self.wfile.write(state.final_payload)
        if content_length is None:
            self.close_connection = True


@contextmanager
def _serve(
    mode: str,
    *,
    first_payload: bytes = b"abcdefghij",
    final_payload: bytes | None = None,
) -> Iterator[tuple[str, _HttpState]]:
    state = _HttpState(
        mode=mode,
        first_payload=first_payload,
        final_payload=final_payload or first_payload,
    )
    server = _DownloadServer(("127.0.0.1", 0), _DownloadHandler)
    server.download_state = state
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture(autouse=True)
def _disable_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "genome_to_diffraction.databases.network.time.sleep", lambda _: None
    )


def _download(
    root: Path, url: str, *, retries: int = 3, minimum_free_bytes: int = 0
) -> Path:
    destination = root / "staging" / "resource.bin"
    download_public_resource(
        url,
        destination,
        storage_root=root,
        storage_limit_bytes=10_000_000,
        minimum_free_bytes=minimum_free_bytes,
        progress=False,
        retries=retries,
    )
    return destination


def test_interrupted_download_resumes_with_range_and_if_range(tmp_path: Path) -> None:
    payload = b"validator-bound-content"
    with _serve("resume", first_payload=payload) as (base_url, state):
        destination = _download(tmp_path, f"{base_url}/data")

    assert destination.read_bytes() == payload
    assert state.request_count == 2
    assert state.requests[0]["Accept-Encoding"] == "identity"
    assert state.requests[1]["Range"].startswith("bytes=")
    assert state.requests[1]["If-Range"] == '"snapshot-v1"'
    assert not list(destination.parent.glob(".*.partial*"))


def test_changed_validator_causes_clean_full_restart(tmp_path: Path) -> None:
    with _serve(
        "changed", first_payload=b"old-representation", final_payload=b"new-snapshot"
    ) as (base_url, state):
        destination = _download(tmp_path, f"{base_url}/data")

    assert destination.read_bytes() == b"new-snapshot"
    assert state.requests[1]["If-Range"] == '"snapshot-v1"'


def test_malformed_content_range_fails_without_promotion(tmp_path: Path) -> None:
    with _serve("malformed") as (base_url, _):
        destination = tmp_path / "staging" / "resource.bin"
        with pytest.raises(DatabaseError, match="Content-Range is inconsistent"):
            _download(tmp_path, f"{base_url}/data", retries=2)

    assert not destination.exists()


def test_response_without_validator_restarts_without_range(tmp_path: Path) -> None:
    with _serve("no-validator") as (base_url, state):
        destination = _download(tmp_path, f"{base_url}/data")

    assert destination.read_bytes() == state.final_payload
    assert state.request_count == 2
    assert "Range" not in state.requests[1]
    assert "If-Range" not in state.requests[1]


def test_weak_etag_is_not_used_for_if_range(tmp_path: Path) -> None:
    with _serve("weak-validator") as (base_url, state):
        destination = _download(tmp_path, f"{base_url}/data")

    assert destination.read_bytes() == state.final_payload
    assert state.request_count == 2
    assert "Range" not in state.requests[1]


def test_http_416_discards_partial_before_retry(tmp_path: Path) -> None:
    with _serve("416") as (base_url, state):
        destination = _download(tmp_path, f"{base_url}/data")

    assert destination.read_bytes() == state.final_payload
    assert state.request_count == 3
    assert "Range" in state.requests[1]
    assert "Range" not in state.requests[2]


def test_orphan_or_tampered_partial_is_not_appended(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / ".resource.bin.partial").write_bytes(b"untrusted-prefix")
    (staging / ".resource.bin.partial.json").write_text(
        json.dumps({"schema_version": "tampered"}), encoding="utf-8"
    )
    with _serve("complete") as (base_url, state):
        destination = _download(tmp_path, f"{base_url}/data")

    assert destination.read_bytes() == state.final_payload
    assert "Range" not in state.requests[0]


def test_symlinked_partial_is_rejected(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    (staging / ".resource.bin.partial").symlink_to(outside)
    (staging / ".resource.bin.partial.json").write_text("{}\n", encoding="utf-8")
    with (
        _serve("complete") as (base_url, _),
        pytest.raises(DatabaseError, match="must not contain symlinks"),
    ):
        _download(tmp_path, f"{base_url}/data")
    assert outside.read_bytes() == b"outside"


def test_destination_outside_storage_root_is_rejected(tmp_path: Path) -> None:
    storage_root = tmp_path / "database"
    storage_root.mkdir()
    destination = tmp_path / "outside" / "resource.bin"
    with pytest.raises(DatabaseError, match="escapes the storage root"):
        download_public_resource(
            "https://example.invalid/resource",
            destination,
            storage_root=storage_root,
            storage_limit_bytes=10_000_000,
            minimum_free_bytes=0,
            progress=False,
        )
    assert not destination.parent.exists()


def test_effective_redirect_url_and_size_are_recorded(tmp_path: Path) -> None:
    with _serve("complete") as (base_url, state):
        destination = tmp_path / "staging" / "resource.bin"
        metadata = download_public_resource(
            f"{base_url}/redirect",
            destination,
            storage_root=tmp_path,
            storage_limit_bytes=10_000_000,
            minimum_free_bytes=0,
            progress=False,
        )

    assert metadata.requested_url == f"{base_url}/redirect"
    assert metadata.url == f"{base_url}/data"
    assert metadata.size_bytes == len(state.final_payload)
    assert metadata.sha256 == hashlib.sha256(state.final_payload).hexdigest()


def test_nonidentity_content_encoding_is_rejected(tmp_path: Path) -> None:
    with (
        _serve("encoded") as (base_url, _),
        pytest.raises(DatabaseError, match="ignored identity content encoding"),
    ):
        _download(tmp_path, f"{base_url}/data")


@pytest.mark.parametrize(
    ("free_bytes", "fails"),
    [(17, False), (16, True)],
)
def test_pending_chunk_preserves_exact_free_space_headroom(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    free_bytes: int,
    fails: bool,
) -> None:
    payload = b"1234567"
    monkeypatch.setattr(
        "genome_to_diffraction.databases.network.shutil.disk_usage",
        lambda _: SimpleNamespace(total=100, used=100 - free_bytes, free=free_bytes),
    )
    with _serve("complete", first_payload=payload) as (base_url, _):
        if fails:
            with pytest.raises(StorageLimitError, match="must remain"):
                _download(
                    tmp_path,
                    f"{base_url}/data",
                    minimum_free_bytes=10,
                )
        else:
            destination = _download(
                tmp_path,
                f"{base_url}/data",
                minimum_free_bytes=10,
            )
            assert destination.read_bytes() == payload


def test_unknown_length_response_still_obeys_storage_cap(tmp_path: Path) -> None:
    payload = b"x" * 4096
    with _serve("unknown-length", first_payload=payload) as (base_url, _):
        destination = tmp_path / "staging" / "resource.bin"
        with pytest.raises(StorageLimitError, match="configured project cap"):
            download_public_resource(
                f"{base_url}/data",
                destination,
                storage_root=tmp_path,
                storage_limit_bytes=1024,
                minimum_free_bytes=0,
                progress=False,
            )

    assert not destination.exists()


def test_concurrent_downloads_to_one_destination_are_serialised(tmp_path: Path) -> None:
    with (
        _serve("complete") as (base_url, state),
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        destinations = list(
            executor.map(lambda _: _download(tmp_path, f"{base_url}/data"), range(2))
        )

    assert destinations[0] == destinations[1]
    assert destinations[0].read_bytes() == state.final_payload
    assert state.request_count == 2
