"""Fixed USTAR extraction rejects unsafe headers before reading their payloads."""

import gzip
import io
import shutil
import tarfile
from pathlib import Path
from typing import BinaryIO

import pytest

from genome_to_diffraction.hpc import m6_coordinate_archive as archive_module
from genome_to_diffraction.hpc.m6_coordinate_archive import (
    extract_import_response_archive,
    extract_prefetch_archive,
)
from genome_to_diffraction.hpc.models import ValidationError


def _tar(members: list[tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, payload in members:
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            member.mode = 0o444
            tar.addfile(member, io.BytesIO(payload))
    return output.getvalue()


def _input(tmp_path: Path, payload: bytes, *, compressed: bool) -> Path:
    path = tmp_path / ("response.tar.gz" if compressed else "prefetch.tar")
    path.write_bytes(gzip.compress(payload, mtime=0) if compressed else payload)
    return path


@pytest.mark.parametrize("compressed", [False, True])
def test_exact_roundtrip_preserves_sender_bytes(
    tmp_path: Path, compressed: bool
) -> None:
    members = (
        [
            ("postinspection.json", b'{"inspection":"exact"}\n'),
            ("import_bundle.json", b"{}\n"),
        ]
        if compressed
        else [
            ("prefetch_manifest.json", b"{}\n"),
            ("objects/1abc.cif.gz", gzip.compress(b"source", mtime=0)),
        ]
    )
    source = _input(tmp_path, _tar(members), compressed=compressed)
    before = source.read_bytes()
    destination = tmp_path / "extracted"
    if compressed:
        extract_import_response_archive(source, destination)
    else:
        extract_prefetch_archive(source, destination, expected_pdb_ids=["1ABC"])
    assert source.read_bytes() == before
    assert {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    } == dict(members)
    with pytest.raises(ValidationError, match="absent"):
        extract_import_response_archive(source, destination)
    assert {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    } == dict(members)


@pytest.mark.parametrize(
    "kind",
    [
        tarfile.XHDTYPE,
        tarfile.XGLTYPE,
        tarfile.GNUTYPE_LONGNAME,
        tarfile.GNUTYPE_LONGLINK,
        tarfile.GNUTYPE_SPARSE,
        tarfile.SYMTYPE,
        tarfile.LNKTYPE,
        tarfile.DIRTYPE,
    ],
)
@pytest.mark.parametrize("compressed", [False, True])
def test_oversized_extensions_and_nonfiles_fail_before_payload_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: bytes,
    compressed: bool,
) -> None:
    member = tarfile.TarInfo(
        "postinspection.json" if compressed else "prefetch_manifest.json"
    )
    member.type = kind
    member.size = 1024**3
    source = _input(
        tmp_path, member.tobuf(format=tarfile.USTAR_FORMAT), compressed=compressed
    )
    assert source.stat().st_size <= 512
    reads: list[int] = []
    original = archive_module._exact

    def observe(stream: BinaryIO | gzip.GzipFile, size: int) -> bytes:
        reads.append(size)
        return original(stream, size)

    monkeypatch.setattr(archive_module, "_exact", observe)
    destination = tmp_path / "rejected"
    with pytest.raises(ValidationError, match=r"extensions|non-files"):
        if compressed:
            extract_import_response_archive(source, destination)
        else:
            extract_prefetch_archive(source, destination, expected_pdb_ids=[])
    assert reads == [512]
    assert destination.is_dir()
    assert not any(path.is_file() for path in destination.rglob("*"))


@pytest.mark.parametrize("kind", ["duplicate", "unknown", "traversal", "missing"])
def test_response_inventory_is_closed_and_failed_files_remain(
    tmp_path: Path, kind: str
) -> None:
    members = [("postinspection.json", b"first\n")]
    if kind != "missing":
        members.append(
            (
                {
                    "duplicate": "postinspection.json",
                    "unknown": "unexpected.json",
                    "traversal": "../import_bundle.json",
                }[kind],
                b"second\n",
            )
        )
    source = _input(tmp_path, _tar(members), compressed=True)
    destination = tmp_path / "failed"
    with pytest.raises(ValidationError, match=r"inventory|unknown|duplicate"):
        extract_import_response_archive(source, destination)
    assert (destination / "postinspection.json").read_bytes() == b"first\n"
    assert not (tmp_path / "import_bundle.json").exists()


@pytest.mark.parametrize(
    "kind",
    [
        "checksum",
        "magic",
        "payload",
        "member_padding",
        "end_block",
        "end_padding",
        "extra_zero_record",
        "gzip_crc",
        "gzip_trailer",
    ],
)
def test_corrupt_or_noncanonical_stream_is_rejected(tmp_path: Path, kind: str) -> None:
    raw = bytearray(
        _tar([("postinspection.json", b"{}"), ("import_bundle.json", b"{}")])
    )
    if kind == "checksum":
        raw[0] ^= 1
    elif kind == "magic":
        raw[257] = ord("X")
    elif kind == "payload":
        raw = raw[:513]
    elif kind == "member_padding":
        raw[514] = 1
    elif kind == "end_block":
        raw[2560] = 1
    elif kind == "end_padding":
        raw[-1] = 1
    elif kind == "extra_zero_record":
        raw.extend(bytes(10240))
    source = _input(tmp_path, bytes(raw), compressed=True)
    if kind == "gzip_crc":
        payload = bytearray(source.read_bytes())
        payload[-8] ^= 1
        source.write_bytes(payload)
    elif kind == "gzip_trailer":
        source.write_bytes(source.read_bytes()[:-4])
    with pytest.raises(ValidationError):
        extract_import_response_archive(source, tmp_path / "failed")


@pytest.mark.parametrize(
    "bound",
    [
        "MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES",
        "MAX_REVIEW_ARTIFACT_FILE_BYTES",
        "MAX_REVIEW_ARTIFACT_TOTAL_BYTES",
    ],
)
def test_response_size_limits_before_payload_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bound: str
) -> None:
    source = _input(
        tmp_path,
        _tar([("postinspection.json", b"first"), ("import_bundle.json", b"second")]),
        compressed=True,
    )
    monkeypatch.setattr(archive_module, bound, 1)
    destination = tmp_path / "failed"
    with pytest.raises(ValidationError, match="byte limit"):
        extract_import_response_archive(source, destination)
    assert not any(path.is_file() for path in destination.rglob("*"))


@pytest.mark.parametrize(
    "bound",
    [
        "MAX_PREFETCH_ARCHIVE_BYTES",
        "MAX_PREFETCH_MANIFEST_BYTES",
        "MAX_COORDINATE_OBJECT_BYTES",
        "MAX_COORDINATE_TOTAL_BYTES",
    ],
)
def test_prefetch_limits_and_exact_missing_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bound: str
) -> None:
    source = _input(
        tmp_path,
        _tar([("prefetch_manifest.json", b"{}"), ("objects/1abc.cif.gz", b"object")]),
        compressed=False,
    )
    monkeypatch.setattr(archive_module, bound, 1)
    with pytest.raises(ValidationError, match="byte limit"):
        extract_prefetch_archive(source, tmp_path / "failed", expected_pdb_ids=["1ABC"])


def test_prefetch_rejects_duplicates_and_identifier_substitutions(
    tmp_path: Path,
) -> None:
    source = _input(
        tmp_path,
        _tar([("prefetch_manifest.json", b"{}"), ("objects/2abc.cif.gz", b"object")]),
        compressed=False,
    )
    for index, expected in enumerate((["1ABC", "1ABC"], ["1abc"], ["1ABC"])):
        with pytest.raises(ValidationError):
            extract_prefetch_archive(
                source, tmp_path / f"failed-{index}", expected_pdb_ids=expected
            )


@pytest.mark.parametrize("location", ["archive", "parent", "destination"])
def test_aliases_are_rejected_without_writing_targets(
    tmp_path: Path, location: str
) -> None:
    source = _input(
        tmp_path,
        _tar([("postinspection.json", b"{}"), ("import_bundle.json", b"{}")]),
        compressed=True,
    )
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    destination = actual / "new"
    if location == "archive":
        alias.symlink_to(source)
        source = alias
    elif location == "parent":
        alias.symlink_to(actual, target_is_directory=True)
        destination = alias / "new"
    else:
        alias.symlink_to(actual / "absent")
        destination = alias
    with pytest.raises(ValidationError, match=r"unsafe|link-free"):
        extract_import_response_archive(source, destination)
    assert list(actual.iterdir()) == []


def test_streaming_free_space_checks_preserve_partial_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = bytes(1024 * 1024 + 1)
    source = _input(
        tmp_path,
        _tar([("postinspection.json", payload), ("import_bundle.json", b"{}")]),
        compressed=True,
    )
    measured = shutil.disk_usage(tmp_path)
    checks = 0

    def available(_path: object) -> tuple[int, int, int]:
        nonlocal checks
        checks += 1
        return measured._replace(free=2 * len(payload) if checks < 3 else 0)

    monkeypatch.setattr(archive_module.shutil, "disk_usage", available)
    destination = tmp_path / "failed"
    with pytest.raises(ValidationError, match="free space"):
        extract_import_response_archive(source, destination)
    assert (destination / "postinspection.json").stat().st_size == 1024 * 1024
    assert not (destination / "import_bundle.json").exists()


def test_empty_missing_set_retains_canonical_objects_directory(tmp_path: Path) -> None:
    source = _input(
        tmp_path, _tar([("prefetch_manifest.json", b"{}")]), compressed=False
    )
    destination = tmp_path / "complete"
    extract_prefetch_archive(source, destination, expected_pdb_ids=[])
    assert (destination / "objects").is_dir()
    assert (destination / "prefetch_manifest.json").read_bytes() == b"{}"
