"""Unit tests for immutable, resumable login-node database source staging."""

import hashlib
import json
from pathlib import Path

import pytest

import genome_to_diffraction.databases.sources as sources_module
from genome_to_diffraction.databases.common import DatabaseError
from genome_to_diffraction.databases.network import DownloadMetadata
from genome_to_diffraction.databases.sources import (
    SOURCE_SPECS,
    SourceBundleRequest,
    load_source_bundle,
    stage_source_bundle,
)


def _request(tmp_path: Path, name: str = "source-bundle.json") -> SourceBundleRequest:
    root = tmp_path / "database root"
    root.mkdir(exist_ok=True)
    return SourceBundleRequest(
        database_root=root,
        manifest_path=tmp_path / name,
        storage_limit_bytes=100_000_000,
        minimum_free_bytes=0,
        progress=False,
    )


def _payload(url: str) -> bytes:
    return f"fixed payload for {url}\n".encode()


def _successful_download(
    url: str,
    destination: Path,
    **_kwargs: object,
) -> DownloadMetadata:
    payload = _payload(url)
    destination.write_bytes(payload)
    return DownloadMetadata(
        requested_url=url,
        url=url,
        etag='"fixed"',
        last_modified="Sun, 09 Aug 2026 00:00:00 GMT",
        content_type="application/octet-stream",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def test_source_bundle_stages_fixed_urls_and_reuses_verified_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def download(url: str, destination: Path, **kwargs: object) -> DownloadMetadata:
        calls.append(url)
        return _successful_download(url, destination, **kwargs)

    monkeypatch.setattr(sources_module, "download_public_resource", download)
    first_request = _request(tmp_path)

    first = stage_source_bundle(first_request)
    second_request = _request(tmp_path, "reused-source-bundle.json")
    second = stage_source_bundle(second_request)

    assert calls == [spec.requested_url for spec in SOURCE_SPECS]
    assert first == second
    assert first.bundle_id.startswith("dbsrc_")
    assert json.loads(first_request.manifest_path.read_text(encoding="utf-8")) == (
        json.loads(second_request.manifest_path.read_text(encoding="utf-8"))
    )
    bundle_root = (
        first_request.database_root
        / "sources"
        / f"bundle-{first.bundle_id.removeprefix('dbsrc_')}"
    )
    assert {path.name for path in bundle_root.iterdir()} == {
        *(spec.filename for spec in SOURCE_SPECS),
        "source_bundle.json",
    }
    assert all(path.stat().st_mode & 0o222 == 0 for path in bundle_root.iterdir())


def test_source_bundle_resumes_completed_and_partial_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts: list[str] = []
    interrupted = True

    def download(url: str, destination: Path, **kwargs: object) -> DownloadMetadata:
        nonlocal interrupted
        attempts.append(url)
        if url == SOURCE_SPECS[1].requested_url and interrupted:
            interrupted = False
            destination.with_name(f".{destination.name}.partial").write_bytes(b"part")
            raise DatabaseError("injected interrupted transfer")
        destination.with_name(f".{destination.name}.partial").unlink(missing_ok=True)
        return _successful_download(url, destination, **kwargs)

    monkeypatch.setattr(sources_module, "download_public_resource", download)
    first_request = _request(tmp_path)
    with pytest.raises(DatabaseError, match="interrupted transfer"):
        stage_source_bundle(first_request)
    retained = list((first_request.database_root / "sources").glob("*.failed"))
    assert len(retained) == 1

    resumed_request = _request(tmp_path, "resumed-source-bundle.json")
    bundle = stage_source_bundle(resumed_request)

    assert bundle.bundle_id.startswith("dbsrc_")
    assert attempts.count(SOURCE_SPECS[0].requested_url) == 1
    assert attempts.count(SOURCE_SPECS[1].requested_url) == 2
    assert not list((first_request.database_root / "sources").glob(".staging-*"))


def test_source_bundle_full_verification_rejects_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sources_module, "download_public_resource", _successful_download
    )
    request = _request(tmp_path)
    bundle = stage_source_bundle(request)
    target = bundle.path(request.database_root, SOURCE_SPECS[0].name)
    target.chmod(0o644)
    target.write_bytes(b"tampered")

    with pytest.raises(DatabaseError, match=r"missing or changed|checksum mismatch"):
        load_source_bundle(
            request.database_root,
            request.manifest_path,
            full_verify=True,
            progress=False,
        )


def test_source_bundle_rejects_unsafe_retained_staging_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sources_module, "download_public_resource", _successful_download
    )
    request = _request(tmp_path)
    staging = request.database_root / "sources" / f".staging-{'a' * 32}.failed"
    staging.mkdir(parents=True)
    (staging / "unapproved").write_text("unsafe\n", encoding="ascii")

    with pytest.raises(DatabaseError, match="unsafe entry"):
        stage_source_bundle(request)
