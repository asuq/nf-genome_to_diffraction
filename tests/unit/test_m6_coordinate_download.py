"""Bounded staged acquisition with real authentication and simulated HTTP only."""

import gzip
import io
import json
import random
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from http.client import HTTPMessage
from pathlib import Path
from types import SimpleNamespace

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.databases import network as network_module
from genome_to_diffraction.databases.common import DatabaseError, StorageLimitError
from genome_to_diffraction.databases.network import DownloadMetadata
from genome_to_diffraction.hpc import m6_coordinate_download as download_module
from genome_to_diffraction.hpc.m6_coordinate_cache import inspect_coordinate_cache
from genome_to_diffraction.hpc.m6_coordinate_download import acquire_coordinate_prefetch
from genome_to_diffraction.hpc.m6_coordinate_prefetch import (
    MAX_ADDITIONAL_DISK_BYTES,
    MAX_COORDINATE_TOTAL_BYTES,
    load_prefetch_bundle,
    prevalidate_proposed_cache,
)
from genome_to_diffraction.hpc.models import ValidationError
from genome_to_diffraction.structure_search import pdb_coordinates
from genome_to_diffraction.structure_search.pdb_coordinates import (
    PdbCoordinateParseError,
)
from tests.unit.test_m6_coordinate_cache import _file_digests, _publish, _snapshot
from tests.unit.test_pdb_coordinates import _compressed_mmcif

SEQUENCES = {"1ABC": "ACDE", "2ABC": "ACDF", "3ABC": "FGHA"}
RETRIEVED = "2026-09-12T09:00:00Z"


@dataclass(frozen=True)
class Inputs:
    snapshot: Path
    inspection: Path
    database: Path
    cache: Path
    inventory_sha256: str
    inspection_sha256: str


def _inputs(tmp_path: Path, *, cached: tuple[str, ...] = ("1ABC",)) -> Inputs:
    snapshot, database, cache, digest = _snapshot(tmp_path)
    for pdb_id in cached:
        _publish(
            cache, pdb_id=pdb_id, payload=_compressed_mmcif(pdb_id, SEQUENCES[pdb_id])
        )
    report = inspect_coordinate_cache(
        snapshot, database, expected_inventory_sha256=digest
    )
    inspection = tmp_path / "inspection.json"
    atomic_write_json(inspection, report)
    return Inputs(
        snapshot, inspection, database, cache, digest, sha256_file(inspection)
    )


def _acquire(inputs: Inputs, staging: Path, *, progress: bool = False) -> Path:
    return acquire_coordinate_prefetch(
        inputs.snapshot,
        inputs.inspection,
        staging,
        expected_inventory_sha256=inputs.inventory_sha256,
        expected_inspection_sha256=inputs.inspection_sha256,
        progress=progress,
    )


class Response(io.BytesIO):
    status = 200

    def __init__(
        self,
        payload: bytes,
        url: str,
        *,
        chunk_size: int,
        fail_after: int | None,
        free: list[int],
        lose_headroom: bool,
    ) -> None:
        super().__init__(payload)
        self.url = url
        self.chunk_size = chunk_size
        self.fail_after = fail_after
        self.free = free
        self.lose_headroom = lose_headroom
        token = url.rsplit("/", 1)[-1].split(".", 1)[0]
        self.headers = {
            "ETag": f'W/"{token}-original"',
            "Last-Modified": "Fri, 11 Sep 2026 00:00:00 GMT",
            "Content-Length": str(len(payload)),
        }
        if token == "2abc":
            self.headers["Content-Type"] = "application/gzip"

    def geturl(self) -> str:
        return self.url

    def read(self, size: int | None = -1) -> bytes:
        if self.fail_after is not None and self.tell() >= self.fail_after:
            raise OSError("simulated interrupted coordinate response")
        if self.lose_headroom and self.tell() >= self.chunk_size:
            self.free[0] = (
                MAX_ADDITIONAL_DISK_BYTES
                - MAX_COORDINATE_TOTAL_BYTES
                + self.chunk_size
                - 1
            )
        requested = (
            self.chunk_size if size is None or size < 0 else min(size, self.chunk_size)
        )
        return super().read(requested)


def _http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payloads: dict[str, bytes] | None = None,
    fail_after: int | None = None,
    chunk_size: int = 1024 * 1024,
    redirect: bool = False,
    changed_url: bool = False,
    lose_headroom: bool = False,
    fail_open_pdb_id: str | None = None,
) -> tuple[list[str], list[int]]:
    calls: list[str] = []
    free = [20 * 1024**3]
    responses: list[Response] = []
    content = payloads or {
        pdb_id: _compressed_mmcif(pdb_id, sequence)
        for pdb_id, sequence in SEQUENCES.items()
    }

    def build_opener(*handlers: urllib.request.BaseHandler) -> SimpleNamespace:
        assert len(handlers) == 1
        handler = handlers[0]
        assert isinstance(handler, urllib.request.HTTPRedirectHandler)

        def open_url(request: urllib.request.Request, *, timeout: int) -> Response:
            assert timeout == 60
            assert request.data is None
            assert request.get_header("Accept-encoding") == "identity"
            assert not request.has_header("Range")
            assert not request.has_header("If-range")
            assert all(response.closed for response in responses)
            url = request.full_url
            pdb_id = url.rsplit("/", 1)[-1].split(".", 1)[0].upper()
            assert url == (
                "https://files.rcsb.org/pub/pdb/data/structures/divided/mmCIF/"
                f"{pdb_id[1:3].lower()}/{pdb_id.lower()}.cif.gz"
            )
            calls.append(pdb_id)
            if pdb_id == fail_open_pdb_id:
                raise urllib.error.URLError(
                    ConnectionResetError(54, "Connection reset by peer")
                )
            if redirect:
                with io.BytesIO() as redirect_body:
                    handler.redirect_request(
                        request,
                        redirect_body,
                        302,
                        "Found",
                        HTTPMessage(),
                        "https://other.invalid/object",
                    )
                raise AssertionError("fixed endpoint followed a redirect")
            response = Response(
                content[pdb_id],
                "https://other.invalid/object" if changed_url else url,
                chunk_size=chunk_size,
                fail_after=fail_after,
                free=free,
                lose_headroom=lose_headroom,
            )
            responses.append(response)
            return response

        return SimpleNamespace(open=open_url)

    def unexpected_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("acquisition used an unrestricted/global network opener")

    monkeypatch.setattr(network_module.urllib.request, "build_opener", build_opener)
    monkeypatch.setattr(network_module.urllib.request, "urlopen", unexpected_network)
    monkeypatch.setattr(
        download_module.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(total=100 * 1024**3, used=0, free=free[0]),
    )
    monkeypatch.setattr(download_module, "utc_now_iso", lambda: RETRIEVED)
    return calls, free


def test_acquires_exact_missing_union_with_original_provenance_and_no_cache_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    before = _file_digests(inputs.cache)
    calls, _ = _http(monkeypatch)

    def unexpected_publication(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("staged acquisition entered coordinate publication")

    monkeypatch.setattr(pdb_coordinates, "_download_coordinate", unexpected_publication)
    monkeypatch.setattr(
        pdb_coordinates, "register_pdb_coordinates", unexpected_publication
    )
    staging = tmp_path / "coordinate-prefetch"
    path = _acquire(inputs, staging)
    assert path == staging / "bundle/prefetch_manifest.json"
    assert calls == ["2ABC", "3ABC"]
    manifest = load_prefetch_bundle(
        path.parent,
        inputs.snapshot,
        inputs.inspection,
        expected_manifest_sha256=sha256_file(path),
        expected_inventory_sha256=inputs.inventory_sha256,
        expected_inspection_sha256=inputs.inspection_sha256,
    )
    assert set(manifest.objects) == {"2ABC", "3ABC"}
    assert manifest.total_size_bytes == sum(
        row.size_bytes for row in manifest.objects.values()
    )
    assert manifest.objects["2ABC"].etag == 'W/"2abc-original"'
    assert manifest.objects["2ABC"].retrieved_at == RETRIEVED
    assert manifest.objects["3ABC"].content_type is None
    assert set(_file_digests(path.parent)) == {
        "prefetch_manifest.json",
        "objects/2abc.cif.gz",
        "objects/3abc.cif.gz",
    }
    assert not (staging / ".pending-bundle").exists()
    assert (staging / "retrievals/2abc.retrieval.json").is_file()
    assert (path.stat().st_mode & 0o222) == 0
    plan = prevalidate_proposed_cache(
        path.parent,
        inputs.snapshot,
        inputs.database,
        inputs.inspection,
        expected_manifest_sha256=sha256_file(path),
        expected_inventory_sha256=inputs.inventory_sha256,
        expected_inspection_sha256=inputs.inspection_sha256,
    )
    assert len(plan.coordinates) == 2
    assert plan.proposed_report["missing_pdb_ids"] == []
    assert _file_digests(inputs.cache) == before


def test_authenticates_full_frozen_inputs_before_staging_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    calls, _ = _http(monkeypatch)
    target = next(inputs.snapshot.glob("requests/*/selected_structural_hits.jsonl"))
    target.write_bytes(target.read_bytes() + b"\n")
    staging = tmp_path / "coordinate-prefetch"
    with pytest.raises(ValidationError, match="snapshot input checksum changed"):
        _acquire(inputs, staging)
    assert not calls
    assert not staging.exists()


def test_checks_full_initial_disk_headroom_before_creating_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    calls, free = _http(monkeypatch)
    free[0] = MAX_ADDITIONAL_DISK_BYTES - 1
    staging = tmp_path / "coordinate-prefetch"
    with pytest.raises(StorageLimitError, match="headroom"):
        _acquire(inputs, staging)
    assert not calls
    assert not staging.exists()


def test_interrupted_acquisition_keeps_partial_bytes_and_refuses_automatic_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    calls, _ = _http(monkeypatch, fail_after=64, chunk_size=64)
    staging = tmp_path / "coordinate-prefetch"
    with pytest.raises(DatabaseError, match="after 1 attempts"):
        _acquire(inputs, staging)
    partial = staging / "incoming/.2abc.cif.gz.partial"
    assert partial.stat().st_size == 64
    state = json.loads(partial.with_name(partial.name + ".json").read_text())
    assert state["completed_bytes"] == 64
    assert state["prefix_sha256"] == sha256_file(partial)
    before = _file_digests(staging)
    with pytest.raises(ValidationError, match="already exists"):
        _acquire(inputs, staging)
    assert calls == ["2ABC"]
    assert _file_digests(staging) == before
    assert not (staging / "bundle").exists()


@pytest.mark.parametrize("field", ("sha256", "size_bytes"))
def test_download_metadata_must_match_bytes_before_next_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    inputs = _inputs(tmp_path)
    calls, _ = _http(monkeypatch)
    original = download_module.download_public_resource

    def inconsistent(
        url: str,
        destination: Path,
        *,
        storage_root: Path,
        storage_limit_bytes: int,
        minimum_free_bytes: int,
        progress: bool,
        retries: int,
        allow_redirects: bool,
    ) -> DownloadMetadata:
        metadata = original(
            url,
            destination,
            storage_root=storage_root,
            storage_limit_bytes=storage_limit_bytes,
            minimum_free_bytes=minimum_free_bytes,
            progress=progress,
            retries=retries,
            allow_redirects=allow_redirects,
        )
        return (
            replace(metadata, sha256="0" * 64)
            if field == "sha256"
            else replace(metadata, size_bytes=metadata.size_bytes + 1)
        )

    monkeypatch.setattr(download_module, "download_public_resource", inconsistent)
    staging = tmp_path / "coordinate-prefetch"
    with pytest.raises(ValidationError, match="bytes or fixed-URL provenance changed"):
        _acquire(inputs, staging)
    assert calls == ["2ABC"]
    assert (staging / "incoming/2abc.cif.gz").is_file()
    assert (staging / "retrievals/2abc.retrieval.json").is_file()
    assert not (staging / "bundle").exists()


@pytest.mark.parametrize("limit", ("object", "total"))
def test_streaming_coordinate_caps_preserve_bounded_partial_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: str
) -> None:
    inputs = _inputs(tmp_path)
    payload = gzip.compress(random.Random(0).randbytes(4096), mtime=0)
    calls, _ = _http(
        monkeypatch, payloads={"2ABC": payload, "3ABC": payload}, chunk_size=1024
    )
    if limit == "object":
        monkeypatch.setattr(download_module, "MAX_COORDINATE_OBJECT_BYTES", 4096)
        maximum = 4096
    else:
        monkeypatch.setattr(download_module, "MAX_COORDINATE_TOTAL_BYTES", 8192)
        monkeypatch.setattr(download_module, "MAX_COORDINATE_OBJECT_BYTES", 10_240)
        maximum = 8192
    staging = tmp_path / "coordinate-prefetch"
    with pytest.raises(StorageLimitError, match="configured project cap"):
        _acquire(inputs, staging)
    assert calls
    coordinate_bytes = sum(
        path.stat().st_size
        for path in staging.rglob("*")
        if path.is_file()
        and (path.name.endswith(".cif.gz") or path.name.endswith(".partial"))
    )
    assert 0 < coordinate_bytes <= maximum
    assert not (staging / "bundle").exists()


def test_streaming_writes_keep_measured_free_space_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    calls, _ = _http(monkeypatch, chunk_size=64, lose_headroom=True)
    staging = tmp_path / "coordinate-prefetch"
    with pytest.raises(StorageLimitError, match="must remain"):
        _acquire(inputs, staging)
    assert calls == ["2ABC"]
    assert (staging / "incoming/.2abc.cif.gz.partial").stat().st_size == 64
    assert not (staging / "bundle").exists()


@pytest.mark.parametrize("mode", ("redirect", "changed_url"))
def test_fixed_endpoint_provenance_cannot_be_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    inputs = _inputs(tmp_path)
    calls, _ = _http(
        monkeypatch, redirect=mode == "redirect", changed_url=mode == "changed_url"
    )
    staging = tmp_path / "coordinate-prefetch"
    with pytest.raises((DatabaseError, ValidationError), match=r"redirects|fixed-URL"):
        _acquire(inputs, staging)
    assert calls == ["2ABC"]
    assert not (staging / "bundle").exists()
    if mode == "redirect":
        assert not list((staging / "incoming").iterdir())
    else:
        assert (staging / "incoming/2abc.cif.gz").is_file()
        assert (staging / "retrievals/2abc.retrieval.json").is_file()


@pytest.mark.parametrize("invalid", ("gzip", "mapping"))
def test_no_final_bundle_until_every_original_missing_mapping_is_qualified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    inputs = _inputs(tmp_path)
    payloads = {
        pdb_id: _compressed_mmcif(pdb_id, sequence)
        for pdb_id, sequence in SEQUENCES.items()
    }
    payloads["3ABC"] = (
        b"not-gzip" if invalid == "gzip" else _compressed_mmcif("3ABC", "ACDE")
    )
    calls, _ = _http(monkeypatch, payloads=payloads)
    staging = tmp_path / "coordinate-prefetch"
    with pytest.raises(
        (ValidationError, PdbCoordinateParseError), match=r"gzip|SEQRES"
    ):
        _acquire(inputs, staging)
    assert calls == ["2ABC", "3ABC"]
    assert not (staging / "bundle").exists()
    assert (staging / ".pending-bundle/objects/3abc.cif.gz").read_bytes() == payloads[
        "3ABC"
    ]


def test_authentic_empty_missing_set_needs_no_http_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path, cached=tuple(SEQUENCES))
    calls, _ = _http(monkeypatch)
    path = _acquire(inputs, tmp_path / "coordinate-prefetch")
    assert not calls
    manifest = json.loads(path.read_text())
    assert manifest["objects"] == {}
    assert manifest["total_size_bytes"] == 0
    assert (path.parent / "objects").is_dir()
