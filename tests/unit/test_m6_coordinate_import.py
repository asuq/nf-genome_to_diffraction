"""Fixed remote budget, batch-before-write and preserved import-failure evidence."""

import base64
import hashlib
import io
import json
import shutil
import sys
import tarfile
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from genome_to_diffraction.databases.cache import publish_pdb_coordinate
from genome_to_diffraction.hpc import m6_coordinate_import as remote
from genome_to_diffraction.hpc.client import _decode_remote_fields
from genome_to_diffraction.hpc.m6_coordinate_archive import (
    extract_import_response_archive,
)
from genome_to_diffraction.hpc.models import ValidationError
from genome_to_diffraction.ids import content_id
from tests.unit.test_m6_coordinate_cache import _file_digests
from tests.unit.test_m6_coordinate_inspection import (
    NEW_OWNER,
    OLD_OWNER,
    InspectionFixture,
    _fixture,
    _inspect,
)
from tests.unit.test_m6_coordinate_prefetch import _bundle


@dataclass(frozen=True)
class _Fixture:
    base: InspectionFixture
    archive: bytes
    manifest_sha: str
    inspection_sha: str


def _import_fixture(
    tmp_path: Path, *, project: Path | None = None, full: bool = False
) -> _Fixture:
    base = _fixture(tmp_path, project=project, full_source=full)
    result = _inspect(base, io.BytesIO())
    builder = tmp_path / "local-prefetch-builder"
    builder.mkdir()
    copied_snapshot = builder / "request-snapshot"
    shutil.copytree(
        base.new / "artifacts/m6-coordinate-inspection/request-snapshot",
        copied_snapshot,
    )
    bundle, _, bindings = _bundle(copied_snapshot, base.database, base.inventory_sha256)
    assert bindings["expected_inspection_sha256"] == result["inspection_sha256"]
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                member = tarfile.TarInfo(path.relative_to(bundle).as_posix())
                member.size = path.stat().st_size
                member.mode = 0o444
                with path.open("rb") as source:
                    archive.addfile(member, source)
    return _Fixture(
        base,
        output.getvalue(),
        bindings["expected_manifest_sha256"],
        bindings["expected_inspection_sha256"],
    )


def _run_import(
    fixture: _Fixture, output: io.BytesIO, **overrides: object
) -> dict[str, object]:
    arguments = {
        "new_owner": NEW_OWNER,
        "old_owner": OLD_OWNER,
        "inspection_sha256": fixture.inspection_sha,
        "archive_sha256": hashlib.sha256(fixture.archive).hexdigest(),
        "archive_size_bytes": len(fixture.archive),
        "prefetch_manifest_sha256": fixture.manifest_sha,
        "request_stream": io.BytesIO(fixture.archive),
        "response_stream": output,
        **overrides,
    }
    return remote.import_coordinate_cache(
        fixture.base.new, fixture.base.old, **arguments
    )


def _preflight(fixture: _Fixture) -> dict[str, object]:
    return remote.storage_preflight(
        fixture.base.new,
        fixture.base.old,
        new_owner=NEW_OWNER,
        old_owner=OLD_OWNER,
        inspection_sha256=fixture.inspection_sha,
    )


@pytest.mark.parametrize("separate", [False, True])
def test_storage_preflight_is_read_only_and_aggregates_real_devices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, separate: bool
) -> None:
    fixture = _import_fixture(tmp_path)
    before = _file_digests(tmp_path)

    def filesystem(path: Path) -> tuple[int, int, int]:
        device = 2 if separate and path.name == "coordinate cache with spaces" else 1
        return device, path.stat().st_ino, 20 * 1024**3

    monkeypatch.setattr(remote, "_filesystem", filesystem)
    monkeypatch.setattr(
        remote.os, "statvfs", lambda _path: SimpleNamespace(f_frsize=4096)
    )
    report = _preflight(fixture)
    expected = (
        [8055296000, 4829605888] if separate else [remote.MAX_ADDITIONAL_DISK_BYTES]
    )
    filesystems = report["filesystems"]
    assert isinstance(filesystems, list)
    assert [row["required_bytes"] for row in filesystems] == expected
    assert report["additional_disk_limit_bytes"] == 12 * 1024**3
    assert report["preflight_id"] == content_id(
        "m6coordstorage_",
        {key: value for key, value in report.items() if key != "preflight_id"},
    )
    assert _file_digests(tmp_path) == before


@pytest.mark.parametrize(
    ("artifact_unit", "artifact_reserve", "cache_reserve"),
    [(32768, 8193671168, 4691230720), (4096, 8072474624, 4812427264)],
)
@pytest.mark.parametrize("separate", [False, True])
def test_full_count_reservations_fit_the_unchanged_total_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_unit: int,
    artifact_reserve: int,
    cache_reserve: int,
    separate: bool,
) -> None:
    fixture = _import_fixture(tmp_path)
    context = remote._context(
        fixture.base.new, fixture.base.old, NEW_OWNER, OLD_OWNER, fixture.inspection_sha
    )
    # Isolate allocation arithmetic, not scientific mapping validation.
    context = replace(
        context,
        report=context.report.model_copy(
            update={
                "missing_pdb_ids": [f"{index + 0x1000:04X}" for index in range(4195)]
            }
        ),
    )
    units = {context.new / "artifacts": artifact_unit, context.cache_root: 32768}
    free = {1: 12 * 1024**3, 2: 12 * 1024**3}

    def filesystem(path: Path) -> tuple[int, int, int]:
        device = 2 if separate and path == context.cache_root else 1
        return device, path.stat().st_ino, free[device]

    monkeypatch.setattr(remote, "_filesystem", filesystem)
    monkeypatch.setattr(
        remote.os, "statvfs", lambda path: SimpleNamespace(f_frsize=units[path])
    )
    before = _file_digests(tmp_path)
    space = remote._Space(context)
    assert space.limits == {"artifacts": artifact_reserve, "cache": cache_reserve}
    assert sum(space.limits.values()) == 12 * 1024**3
    report = remote._storage_report(context, space)
    expected = [artifact_reserve, cache_reserve] if separate else [12 * 1024**3]
    filesystems = report["filesystems"]
    assert isinstance(filesystems, list)
    assert [row["required_bytes"] for row in filesystems] == expected
    assert report["adapter_version"] == "m6-coordinate-storage-preflight-v2"
    assert report["layout"] == {
        "artifacts": {"device": 1, "frsize_bytes": artifact_unit},
        "cache": {"device": 2 if separate else 1, "frsize_bytes": 32768},
    }
    with pytest.raises(ValidationError, match="additional-disk allocation"):
        space.check("cache", cache_reserve + 1)
    if separate:
        free[1], free[2] = artifact_reserve, cache_reserve
    expected_at_limit = (
        [
            {
                "device": 1,
                "free_bytes": artifact_reserve,
                "required_bytes": artifact_reserve,
            },
            {"device": 2, "free_bytes": cache_reserve, "required_bytes": cache_reserve},
        ]
        if separate
        else filesystems
    )
    assert space.check() == expected_at_limit
    free[2 if separate else 1] -= 1
    with pytest.raises(ValidationError, match="headroom"):
        space.check()
    assert _file_digests(tmp_path) == before


@pytest.mark.parametrize(
    ("count", "artifact_unit", "cache_unit"),
    [(-1, 32768, 32768), (True, 32768, 32768), (4195, 0, 32768), (4195, 32768, True)],
)
def test_storage_reservations_reject_unknown_or_invalid_inputs(
    count: int, artifact_unit: int, cache_unit: int
) -> None:
    with pytest.raises(ValidationError):
        remote.coordinate_storage_reservations(
            count, artifacts_frsize_bytes=artifact_unit, cache_frsize_bytes=cache_unit
        )


@pytest.mark.parametrize(
    ("artifact_unit", "cache_unit", "artifact_peak", "cache_peak"),
    [
        (4096, 65536, 8072474624, 5726899200),
        (1048576, 1048576, 12487491584, 39221038080),
    ],
)
def test_full_count_layout_failure_reports_bounded_arithmetic_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_unit: int,
    cache_unit: int,
    artifact_peak: int,
    cache_peak: int,
) -> None:
    fixture = _import_fixture(tmp_path)
    context = remote._context(
        fixture.base.new,
        fixture.base.old,
        NEW_OWNER,
        OLD_OWNER,
        fixture.inspection_sha,
    )
    # Isolate layout arithmetic at the real inventory's cardinality.
    context = replace(
        context,
        report=context.report.model_copy(
            update={
                "missing_pdb_ids": [f"{index + 0x1000:04X}" for index in range(4195)]
            }
        ),
    )
    units = {
        context.new / "artifacts": artifact_unit,
        context.cache_root: cache_unit,
    }
    monkeypatch.setattr(
        remote, "_filesystem", lambda path: (1, path.stat().st_ino, 100 * 1024**3)
    )
    monkeypatch.setattr(
        remote.os, "statvfs", lambda path: SimpleNamespace(f_frsize=units[path])
    )
    before = _file_digests(tmp_path)
    with pytest.raises(ValidationError, match="declared layout") as caught:
        remote._Space(context)
    message = str(caught.value)
    expected = {
        "missing_pdb_count": 4195,
        "artifacts_frsize_bytes": artifact_unit,
        "cache_frsize_bytes": cache_unit,
        "artifacts_estimated_peak_bytes": artifact_peak,
        "cache_estimated_peak_bytes": cache_peak,
        "total_estimated_peak_bytes": artifact_peak + cache_peak,
        "additional_disk_limit_bytes": 12 * 1024**3,
    }
    assert all(f"{key}={value}" in message for key, value in expected.items())
    assert len(message.encode("ascii")) < 1024
    assert all(value not in message for value in (NEW_OWNER, OLD_OWNER, str(tmp_path)))
    assert _file_digests(tmp_path) == before


def test_insufficient_headroom_fails_before_receiving_or_publishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _import_fixture(tmp_path)
    before = _file_digests(tmp_path)
    monkeypatch.setattr(
        remote,
        "_filesystem",
        lambda path: (1, path.stat().st_ino, remote.MAX_ADDITIONAL_DISK_BYTES - 1),
    )
    output = io.BytesIO()
    with pytest.raises(ValidationError, match="headroom"):
        _run_import(fixture, output)
    assert output.getvalue() == b""
    assert _file_digests(tmp_path) == before


def test_complete_import_returns_all_provenance_and_preserves_prior_evidence(
    tmp_path: Path,
) -> None:
    fixture = _import_fixture(tmp_path)
    old_before = _file_digests(fixture.base.old)
    inspection = fixture.base.new / "artifacts/m6-coordinate-inspection"
    inspected_before = _file_digests(inspection)
    output = io.BytesIO()
    bundle = _run_import(fixture, output)
    response = tmp_path / "response.tar.gz"
    response.write_bytes(output.getvalue())
    extracted = tmp_path / "response"
    extract_import_response_archive(response, extracted)
    post = json.loads((extracted / "postinspection.json").read_text())
    assert post["missing_pdb_ids"] == []
    assert post["requested_mapping_count"] == 186
    assert post["cache_import_performed"] is False
    assert bundle["cache_import_performed"] is True
    assert bundle["status"] == "complete"
    imported_coordinates = bundle["imported_coordinates"]
    assert isinstance(imported_coordinates, dict)
    assert set(imported_coordinates) == {"1ABC"}
    assert bundle == json.loads((extracted / "import_bundle.json").read_text())
    assert bundle["bundle_id"] == content_id(
        "m6coordimport_",
        {key: value for key, value in bundle.items() if key != "bundle_id"},
    )
    attempt = fixture.base.new / remote.IMPORT_RELATIVE
    assert (attempt / "prefetch.tar").read_bytes() == fixture.archive
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "complete"
    assert _file_digests(fixture.base.old) == old_before
    assert _file_digests(inspection) == inspected_before
    repeated = io.BytesIO()
    with pytest.raises(ValidationError, match="already exists"):
        _run_import(fixture, repeated)
    assert repeated.getvalue() == b""


@pytest.mark.parametrize(
    "change", ["checksum", "extra_bytes", "manifest", "extension_header"]
)
def test_bad_import_archive_keeps_failed_attempt_without_shared_writes(
    tmp_path: Path, change: str
) -> None:
    fixture = _import_fixture(tmp_path)
    cache = fixture.base.database.parent / "coordinate cache with spaces"
    before = _file_digests(cache)
    overrides: dict[str, object] = {}
    if change == "checksum":
        overrides["archive_sha256"] = "a" * 64
    elif change == "extra_bytes":
        overrides["request_stream"] = io.BytesIO(fixture.archive + b"extra")
    elif change == "manifest":
        overrides["prefetch_manifest_sha256"] = "b" * 64
    else:
        member = tarfile.TarInfo("untrusted-pax")
        member.type = tarfile.XHDTYPE
        member.size = 2**30
        data = member.tobuf(format=tarfile.USTAR_FORMAT)
        overrides.update(
            archive_sha256=hashlib.sha256(data).hexdigest(),
            archive_size_bytes=len(data),
            request_stream=io.BytesIO(data),
        )
    output = io.BytesIO()
    with pytest.raises(ValidationError):
        _run_import(fixture, output, **overrides)
    attempt = fixture.base.new / remote.IMPORT_RELATIVE
    assert json.loads((attempt / "attempt.json").read_text())["status"] == "failed"
    assert (attempt / "prefetch.tar").is_file()
    assert not (attempt / "import_bundle.json").exists()
    assert _file_digests(cache) == before
    assert output.getvalue() == b""


def test_all_target_preflight_finishes_before_publisher_is_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _import_fixture(tmp_path)

    def collision(*_args: object, **_kwargs: object) -> None:
        raise ValidationError("last proposed destination collides")

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("publication began before complete preflight")

    monkeypatch.setattr(remote, "prevalidate_proposed_cache", collision)
    monkeypatch.setattr(remote, "publish_pdb_coordinate", unexpected)
    with pytest.raises(ValidationError, match="last proposed destination"):
        _run_import(fixture, io.BytesIO())
    state = json.loads(
        (fixture.base.new / remote.IMPORT_RELATIVE / "attempt.json").read_text()
    )
    assert state["phase"] == "validating" and state["imported_pdb_count"] == 0


def test_io_failure_after_cache_write_is_retained_and_never_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _import_fixture(tmp_path)
    calls = []

    def fail_after_publication(*args: Any, **kwargs: Any) -> None:
        calls.append(1)
        publish_pdb_coordinate(*args, **kwargs)
        raise OSError("simulated publication I/O failure")

    monkeypatch.setattr(remote, "publish_pdb_coordinate", fail_after_publication)
    output = io.BytesIO()
    with pytest.raises(OSError, match="publication I/O"):
        _run_import(fixture, output)
    attempt = fixture.base.new / remote.IMPORT_RELATIVE
    state = json.loads((attempt / "attempt.json").read_text())
    assert state["status"] == "failed" and state["phase"] == "publishing"
    assert state["active_pdb_id"] == "1ABC"
    assert (attempt / "publication_receipts.jsonl").read_text().count("\n") == 1
    with pytest.raises(ValidationError, match="already exists"):
        _run_import(fixture, output)
    assert calls == [1]
    assert output.getvalue() == b""


def test_current_free_space_is_rechecked_after_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _import_fixture(tmp_path)
    original = remote._filesystem
    after_write = False

    def filesystem(path: Path) -> tuple[int, int, int]:
        device, inode, free = original(path)
        return device, inode, 0 if after_write else free

    def consume_space(*args: Any, **kwargs: Any) -> object:
        nonlocal after_write
        result = publish_pdb_coordinate(*args, **kwargs)
        after_write = True
        return result

    monkeypatch.setattr(remote, "_filesystem", filesystem)
    monkeypatch.setattr(remote, "publish_pdb_coordinate", consume_space)
    with pytest.raises(ValidationError, match="headroom"):
        _run_import(fixture, io.BytesIO())
    assert (
        json.loads(
            (fixture.base.new / remote.IMPORT_RELATIVE / "attempt.json").read_text()
        )["status"]
        == "failed"
    )


def test_actual_dispatcher_preflight_import_and_fixed_failure_log(
    tmp_path: Path,
) -> None:
    from tests.integration.test_hpc_remote_dispatcher import (
        _prepare_remote_layout,
        _run,
    )

    dispatcher, smoke, environment, _ = _prepare_remote_layout(tmp_path)
    site = dispatcher.parent / "site.paths"
    site.write_text("marmic\n", encoding="ascii")
    site.chmod(0o600)
    fixture = _import_fixture(tmp_path, project=smoke.parent.parent, full=True)
    python = fixture.base.new / "environment/.pixi/envs/hpc/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    common = [
        fixture.base.new.name,
        NEW_OWNER,
        fixture.base.old.name,
        OLD_OWNER,
        fixture.inspection_sha,
    ]
    preflight = _run(
        [str(dispatcher), "coordinate-import-preflight", *common],
        cwd=tmp_path,
        environment=environment,
    )
    fields = _decode_remote_fields(preflight.stdout)
    assert (
        fields["operation"] == "coordinate-import-preflight"
        and fields["status"] == "ready"
    )
    storage = json.loads(fields["storage_preflight"])
    assert sum(row["required_bytes"] for row in storage["filesystems"]) == 12 * 1024**3
    command = [
        str(dispatcher),
        "import-coordinate-cache",
        *common,
        hashlib.sha256(fixture.archive).hexdigest(),
        str(len(fixture.archive)),
        fixture.manifest_sha,
    ]
    result = _run(
        command, cwd=tmp_path, environment=environment, input_data=fixture.archive
    )
    response = tmp_path / "remote-response.tar.gz"
    response.write_bytes(result.stdout)
    extract_import_response_archive(response, tmp_path / "remote-response")
    replay = _run(
        command,
        cwd=tmp_path,
        environment=environment,
        input_data=fixture.archive,
        success=False,
    )
    assert _decode_remote_fields(replay.stdout)["failure_class"] == "wrapper_failure"
    logs = _run(
        [str(dispatcher), "logs", fixture.base.new.name, NEW_OWNER, "40"],
        cwd=tmp_path,
        environment=environment,
    )
    fields = _decode_remote_fields(logs.stdout)
    assert fields["log_path"].endswith("/logs/m6-coordinate-import.log")
    text = base64.b64decode(fields["content_base64"]).decode()
    assert "already exists" in text and NEW_OWNER not in text and OLD_OWNER not in text
