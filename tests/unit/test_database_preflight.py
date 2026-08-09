"""Unit tests for the fixed large-database compute-node preflight."""

import json
import os
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from genome_to_diffraction.databases.common import DatabaseError
from genome_to_diffraction.databases.preflight import (
    FOLDSEEK_PDB_ARCHIVE_URL,
    FOLDSEEK_PDB_VERSION_URL,
    FOLDSEEK_PROSTT5_ARCHIVE_URL,
    PDB_COORDINATE_SMOKE_URL,
    PDB_SEQUENCE_URL,
    DatabasePreflightRequest,
    _probe_one_byte,
    _probe_public_routes,
    preflight_database_administration,
)


def _request(tmp_path: Path) -> DatabasePreflightRequest:
    database_root = tmp_path / "database root"
    scratch_root = tmp_path / "scratch root"
    database_root.mkdir()
    scratch_root.mkdir()
    return DatabasePreflightRequest(
        database_root=database_root,
        scratch_root=scratch_root,
        report_path=tmp_path / "preflight report.json",
        storage_limit_bytes=2_000,
        minimum_free_bytes=100,
        required_database_capacity_bytes=1_000,
        minimum_scratch_free_bytes=500,
        probe_timeout_seconds=5,
        progress=False,
    )


def _mock_successful_system(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight._device_id",
        lambda path: 1 if path.name == "database root" else 2,
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.tree_size", lambda _: 100
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.shutil.disk_usage",
        lambda path: SimpleNamespace(
            total=4_000,
            used=1_000,
            free=3_000 if path.name == "database root" else 2_000,
        ),
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.tool_version",
        lambda executable, **_kwargs: (
            "foldseek 10.941cd33" if executable == "foldseek" else "mmseqs 18.8cc5c"
        ),
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight._probe_public_routes",
        lambda *_args, **_kwargs: (
            "aria2 version 1.37.0",
            [
                {
                    "name": "fixed",
                    "url": FOLDSEEK_PDB_VERSION_URL,
                    "probe": "HTTPS Range bytes=0-0; exactly one response byte",
                    "status": "reachable",
                }
            ],
        ),
    )


def test_preflight_records_distinct_scratch_capacity_tools_and_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    _mock_successful_system(monkeypatch)

    report = preflight_database_administration(request)

    assert report["status"] == "passed"
    assert report["database_device"] == 1
    assert report["scratch_device"] == 2
    assert report["database_available_build_bytes"] == 1_900
    assert report["large_payload_started"] is False
    persisted = json.loads(request.report_path.read_text(encoding="utf-8"))
    assert persisted == report


def test_preflight_verifies_durable_bundle_without_compute_node_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    source_bundle = tmp_path / "source-bundle.json"
    source_bundle.write_text("{}\n", encoding="ascii")
    request = replace(request, source_bundle_path=source_bundle)
    _mock_successful_system(monkeypatch)
    aria2c = tmp_path / "aria2c"
    aria2c.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="ascii")
    aria2c.chmod(0o755)
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.shutil.which",
        lambda _: str(aria2c),
    )

    def version(executable: str, **_kwargs: object) -> str:
        if executable == "foldseek":
            return "foldseek 10.941cd33"
        if executable == "mmseqs":
            return "mmseqs 18.8cc5c"
        return "aria2 version 1.37.0"

    resources = [
        SimpleNamespace(
            name="fixed",
            requested_url=FOLDSEEK_PDB_VERSION_URL,
            effective_url=FOLDSEEK_PDB_VERSION_URL,
            size_bytes=12,
            etag='"fixed"',
            last_modified=None,
            sha256="a" * 64,
        )
    ]
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.tool_version", version
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.load_source_bundle",
        lambda *_args, **_kwargs: SimpleNamespace(
            bundle_id=f"dbsrc_{'b' * 64}", resources=resources
        ),
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight._probe_public_routes",
        lambda *_args, **_kwargs: pytest.fail("offline preflight contacted a route"),
    )

    report = preflight_database_administration(request)

    assert report["status"] == "passed"
    assert report["source_bundle_id"] == f"dbsrc_{'b' * 64}"
    assert report["network_probes"] == [
        {
            "name": "fixed",
            "url": FOLDSEEK_PDB_VERSION_URL,
            "effective_url": FOLDSEEK_PDB_VERSION_URL,
            "representation_size_bytes": 12,
            "etag": '"fixed"',
            "last_modified": None,
            "sha256": "a" * 64,
            "status": "durable_source_verified",
        }
    ]


def test_preflight_fails_before_network_when_scratch_shares_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight._device_id", lambda _: 1
    )

    with pytest.raises(DatabaseError, match="filesystem distinct"):
        preflight_database_administration(request)

    report = json.loads(request.report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["large_payload_started"] is False


def test_preflight_fails_when_explicit_capacity_requirement_is_not_met(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    _mock_successful_system(monkeypatch)
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.tree_size", lambda _: 1_500
    )

    with pytest.raises(DatabaseError, match="explicitly required build capacity"):
        preflight_database_administration(request)

    report = json.loads(request.report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["large_payload_started"] is False


def test_route_probe_uses_pinned_aria2_and_bounded_gets_for_only_fixed_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    aria2c = bin_directory / "aria2c"
    aria2c.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    aria2c.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.tool_version",
        lambda _: "aria2 version 1.37.0",
    )
    calls: list[tuple[str, int]] = []

    def probe(url: str, *, timeout_seconds: int) -> dict[str, object]:
        calls.append((url, timeout_seconds))
        return {
            "effective_url": url,
            "representation_size_bytes": 123,
            "range_honoured": True,
            "etag": '"snapshot"',
            "last_modified": None,
            "sample_sha256": "0" * 64,
            "sample_size_bytes": 1,
        }

    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight._probe_one_byte", probe
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    version, probes = _probe_public_routes(
        scratch,
        timeout_seconds=5,
        progress=False,
    )

    assert version == "aria2 version 1.37.0"
    expected_urls = [
        FOLDSEEK_PDB_ARCHIVE_URL,
        FOLDSEEK_PDB_VERSION_URL,
        FOLDSEEK_PROSTT5_ARCHIVE_URL,
        PDB_SEQUENCE_URL,
        PDB_COORDINATE_SMOKE_URL,
    ]
    assert [probe["url"] for probe in probes] == expected_urls
    assert calls == [(url, 5) for url in expected_urls]
    assert all(probe["sample_size_bytes"] == 1 for probe in probes)


def test_route_probe_rejects_unpinned_aria2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    aria2c = tmp_path / "aria2c"
    aria2c.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    aria2c.chmod(0o755)
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.shutil.which",
        lambda _: str(aria2c),
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.tool_version",
        lambda _: "aria2 version 1.36.0",
    )

    with pytest.raises(DatabaseError, match=r"aria2 1\.37\.0 is required"):
        _probe_public_routes(tmp_path, timeout_seconds=5, progress=False)


class _ProbeResponse:
    def __init__(
        self,
        *,
        status: int = 206,
        body: bytes = b"x",
        content_range: str | None = "bytes 0-0/123",
        content_length: str | None = "1",
        effective_url: str = "https://objects.example.test/resource",
    ) -> None:
        self.status = status
        self.body = body
        self.headers = {"ETag": '"snapshot"'}
        if content_range is not None:
            self.headers["Content-Range"] = content_range
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self.effective_url = effective_url
        self.read_sizes: list[int] = []

    def __enter__(self) -> _ProbeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        return self.body[:size]

    def geturl(self) -> str:
        return self.effective_url


def test_one_byte_probe_records_bounded_redirect_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_headers: dict[str, str] = {}

    def urlopen(request: urllib.request.Request, *, timeout: int) -> _ProbeResponse:
        assert timeout == 5
        observed_headers.update(request.headers)
        return _ProbeResponse()

    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.urllib.request.urlopen", urlopen
    )

    result = _probe_one_byte("https://example.test/resource", timeout_seconds=5)

    assert observed_headers["Range"] == "bytes=0-0"
    assert observed_headers["Accept-encoding"] == "identity"
    assert result["representation_size_bytes"] == 123
    assert result["sample_size_bytes"] == 1
    assert result["effective_url"] == "https://objects.example.test/resource"
    assert result["range_honoured"] is True


@pytest.mark.parametrize("content_length", ["4321", None])
def test_one_byte_probe_accepts_declared_or_streamed_ignored_range(
    monkeypatch: pytest.MonkeyPatch,
    content_length: str | None,
) -> None:
    response = _ProbeResponse(
        status=200,
        body=b"more-than-one-byte",
        content_range=None,
        content_length=content_length,
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.urllib.request.urlopen",
        lambda *_args, **_kwargs: response,
    )

    result = _probe_one_byte("https://example.test/resource", timeout_seconds=5)

    assert result["representation_size_bytes"] == (
        int(content_length) if content_length is not None else None
    )
    assert result["range_honoured"] is False
    assert result["sample_size_bytes"] == 1
    assert response.read_sizes == [1]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_ProbeResponse(status=500), "unsupported HTTP status"),
        (_ProbeResponse(status=200, content_length="invalid"), "invalid body length"),
        (_ProbeResponse(content_range="bytes 0-1/123"), "invalid Content-Range"),
        (_ProbeResponse(content_length="123"), "unbounded ranged body length"),
        (_ProbeResponse(body=b""), "exactly one byte"),
        (
            _ProbeResponse(effective_url="http://objects.example.test/resource"),
            "redirected outside HTTPS",
        ),
    ],
)
def test_one_byte_probe_rejects_unbounded_or_unsafe_responses(
    monkeypatch: pytest.MonkeyPatch,
    response: _ProbeResponse,
    message: str,
) -> None:
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.urllib.request.urlopen",
        lambda *_args, **_kwargs: response,
    )

    with pytest.raises(DatabaseError, match=message):
        _probe_one_byte("https://example.test/resource", timeout_seconds=5)


def test_one_byte_probe_normalises_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise urllib.error.URLError("injected route outage")

    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.urllib.request.urlopen", fail
    )

    with pytest.raises(DatabaseError, match="fixed database route probe failed"):
        _probe_one_byte("https://example.test/resource", timeout_seconds=5)
