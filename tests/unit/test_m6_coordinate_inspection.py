"""Exercise the fixed new-run inspection bridge with original producer evidence."""

import base64
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc import m6_coordinate_inspection as bridge
from genome_to_diffraction.hpc.client import _decode_remote_fields
from genome_to_diffraction.hpc.m6_coordinate_requests import (
    RUNNER,
    extract_request_archive,
    freeze_request_inventory,
)
from genome_to_diffraction.hpc.models import ValidationError
from genome_to_diffraction.ids import content_id
from tests.unit.test_m6_coordinate_cache import _file_digests
from tests.unit.test_m6_coordinate_requests import _export, _failed_coordinate_tree
from tests.unit.test_pdb_coordinates import _inputs

REPOSITORY = Path(__file__).resolve().parents[2]
NEW_OWNER = "7a" * 16
OLD_OWNER = "1f" * 16


@dataclass(frozen=True)
class InspectionFixture:
    new: Path
    old: Path
    database: Path
    request: bytes
    inventory_sha256: str


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("ascii").strip()


def _write(root: Path, relative: str, payload: str | bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload.encode("ascii") if isinstance(payload, str) else payload)


def _source(root: Path, *, new: bool, full: bool = False) -> str:
    root.mkdir()
    if full:
        shutil.copytree(
            REPOSITORY / "src",
            root / "src",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        shutil.copytree(REPOSITORY / "schemas", root / "schemas")
    else:
        for relative in bridge._SELECTORS:
            _write(root, relative, (REPOSITORY / relative).read_bytes())
        if new:
            relative = "src/genome_to_diffraction/hpc/m6_coordinate_inspection.py"
            _write(root, relative, (REPOSITORY / relative).read_bytes())
    _write(root, "pixi.lock", "locked\n")
    _write(root, ".gitignore", ".pixi/\n__pycache__/\n*.pyc\n")
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Inspection Fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "immutable synthetic inspection source")
    return _git(root, "rev-parse", "HEAD")


def _fixture(
    tmp_path: Path, *, project: Path | None = None, full_source: bool = False
) -> InspectionFixture:
    tmp_path = tmp_path.resolve()
    project = (project or tmp_path / "owned-project").resolve()
    runs = project / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    old_source, new_source = tmp_path / "original-source", tmp_path / "new-source"
    old_commit = _source(old_source, new=False)
    new_commit = _source(new_source, new=True, full=full_source)
    old = runs / f"gtd-m6-native-control-20260912T100000Z-{old_commit[:12]}-12345678"
    new = runs / f"gtd-m6-native-control-20260912T110000Z-{new_commit[:12]}-87654321"
    _failed_coordinate_tree(old)
    database_root = tmp_path / "database-fixture"
    database_root.mkdir()
    _, _, database, _ = _inputs(database_root)
    database_sha = sha256_file(database)
    lock_sha = hashlib.sha256(b"locked\n").hexdigest()
    for run, source, commit, owner, phase in (
        (old, old_source, old_commit, OLD_OWNER, "completed"),
        (new, new_source, new_commit, NEW_OWNER, "staged"),
    ):
        run.mkdir(exist_ok=True)
        source.rename(run / "source")
        for directory in ("logs", "artifacts", "state", "environment/.pixi"):
            (run / directory).mkdir(parents=True, exist_ok=True)
        (run / "source/.pixi").symlink_to(
            run / "environment/.pixi", target_is_directory=True
        )
        for name, value in {
            "owner-id": owner,
            "site-id": "marmic",
            "profile": "m6-native-control",
            "controller-kind": "slurm_job",
            "m6-execution-purpose": "native_control",
            "m6-track": "operational",
            "phase": phase,
            "commit": commit,
            "pixi-lock-sha256": lock_sha,
            "database-manifest": str(database),
            "database-manifest-sha256": database_sha,
        }.items():
            _write(run, f"state/{name}", value + "\n")
        atomic_write_json(
            run / "manifest.json",
            {
                "schema_version": "1.0",
                "run_id": run.name,
                "site_id": "marmic",
                "profile": "m6-native-control",
                "controller_kind": "slurm_job",
                "commit": commit,
                "source_snapshot_status": "immutable",
                "pixi_lock_sha256": lock_sha,
                "database_manifest_sha256": database_sha,
            },
        )
    _write(new, RUNNER, (old / RUNNER).read_bytes())
    _write(new, "state/m6-runner-manifest-sha256", sha256_file(new / RUNNER) + "\n")
    atomic_write_json(
        old / "state/job-result.json",
        {
            "run_id": old.name,
            "profile": "m6-native-control",
            "job_id": "42",
            "exit_code": 1,
            "failure_class": "test_failure",
        },
    )
    for path in old.rglob("track_plan.json"):
        document = json.loads(path.read_text())
        document["input_sha256"]["database_manifest"] = database_sha
        atomic_write_json(path, document)
    for path in old.glob(
        "cache/m6-nextflow-operational/work/*/*/m6_policy_bundle/bundle_manifest.json"
    ):
        document = json.loads(path.read_text())
        document["input_sha256"]["database_manifest"] = database_sha
        atomic_write_json(path, document)
    result = _export(old)
    assert result.returncode == 0, result.stderr.decode()
    archive = tmp_path / "original-request-export.tar.gz"
    archive.write_bytes(result.stdout)
    snapshot = tmp_path / "confirmed-original-snapshot"
    collection = extract_request_archive(archive, snapshot)
    freeze_request_inventory(
        snapshot,
        collection=collection,
        prior=old,
        remote_root=PurePosixPath(old),
        run_id=old.name,
        source_commit=old_commit,
    )
    return InspectionFixture(
        new,
        old,
        database,
        result.stdout,
        sha256_file(snapshot / "request_inventory.json"),
    )


def _inspect(
    fixture: InspectionFixture, output: io.BytesIO, **overrides: object
) -> dict[str, object]:
    arguments = {
        "new_owner": NEW_OWNER,
        "old_owner": OLD_OWNER,
        "request_archive_sha256": hashlib.sha256(fixture.request).hexdigest(),
        "request_archive_size_bytes": len(fixture.request),
        "request_inventory_sha256": fixture.inventory_sha256,
        "request_stream": io.BytesIO(fixture.request),
        "response_stream": output,
        **overrides,
    }
    return bridge.inspect_owned_coordinate_cache(fixture.new, fixture.old, **arguments)


def test_bridge_preserves_original_and_returns_only_two_bound_reports(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    before = _file_digests(fixture.old)
    output = io.BytesIO()
    bundle = _inspect(fixture, output)
    assert _file_digests(fixture.old) == before
    with tarfile.open(fileobj=io.BytesIO(output.getvalue()), mode="r:gz") as archive:
        assert archive.getnames() == list(bridge.REPORT_FILES)
        records = {}
        for name in archive.getnames():
            stream = archive.extractfile(name)
            assert stream is not None
            records[name] = stream.read()
    assert json.loads(records["inspection_bundle.json"]) == bundle
    report = json.loads(records["inspection.json"])
    assert report["requested_mapping_count"] == 186
    assert report["missing_pdb_ids"] == ["1ABC"]
    assert (
        hashlib.sha256(records["inspection.json"]).hexdigest()
        == bundle["inspection_sha256"]
    )
    assert bundle["bundle_id"] == content_id(
        "m6inspect_",
        {key: value for key, value in bundle.items() if key != "bundle_id"},
    )
    assert bundle["request_inventory_sha256"] == fixture.inventory_sha256
    assert bundle["run_id"] == fixture.new.name
    assert bundle["request_run_id"] == fixture.old.name
    publication = fixture.new / bridge.PUBLICATION_RELATIVE
    assert (
        sha256_file(publication / "request-snapshot/request_inventory.json")
        == fixture.inventory_sha256
    )
    for payload in records.values():
        assert NEW_OWNER.encode() not in payload
        assert OLD_OWNER.encode() not in payload
        assert b'"sequence":' not in payload
    frozen = _file_digests(publication)
    repeated = io.BytesIO()
    with pytest.raises(ValidationError, match="already exists"):
        _inspect(fixture, repeated)
    assert repeated.getvalue() == b""
    assert _file_digests(publication) == frozen


@pytest.mark.parametrize(
    "invalid",
    [
        "new_owner",
        "old_owner",
        "active",
        "job",
        "controller",
        "dirty_source",
        "database",
        "runner",
        "archive_checksum",
        "extra_bytes",
        "inventory_checksum",
    ],
)
def test_bridge_rejects_bad_authority_before_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    fixture = _fixture(tmp_path)
    overrides: dict[str, object] = {}
    if invalid in {"new_owner", "old_owner"}:
        overrides[invalid] = "ff" * 16
    elif invalid == "active":
        _write(fixture.new, "state/phase", "running\n")
    elif invalid in {"job", "controller"}:
        name = "job-id" if invalid == "job" else "controller.json"
        _write(fixture.new, f"state/{name}", "1\n")
    elif invalid == "dirty_source":
        _write(fixture.new / "source", bridge._SELECTORS[0], "changed source\n")
    elif invalid == "database":
        fixture.database.write_text("{}\n", encoding="ascii")
    elif invalid == "runner":
        _write(fixture.new, RUNNER, "changed runner\n")
    elif invalid == "archive_checksum":
        overrides["request_archive_sha256"] = "00" * 32
    elif invalid == "extra_bytes":
        overrides["request_stream"] = io.BytesIO(fixture.request + b"unexpected")
    else:
        overrides["request_inventory_sha256"] = "00" * 32

    def unexpected_inspection(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid binding reached cache inspection")

    monkeypatch.setattr(bridge, "inspect_coordinate_cache", unexpected_inspection)
    before = _file_digests(fixture.old)
    output = io.BytesIO()
    with pytest.raises(ValidationError):
        _inspect(fixture, output, **overrides)
    assert output.getvalue() == b""
    assert _file_digests(fixture.old) == before
    assert not (fixture.new / bridge.PUBLICATION_RELATIVE).exists()


@pytest.mark.parametrize("bound", ["file", "total", "archive"])
def test_report_archive_enforces_existing_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bound: str
) -> None:
    payload = tmp_path / "payload"
    payload.mkdir()
    for name in bridge.REPORT_FILES:
        _write(payload, name, "bounded report\n")
    constant = {
        "file": "MAX_REVIEW_ARTIFACT_FILE_BYTES",
        "total": "MAX_REVIEW_ARTIFACT_TOTAL_BYTES",
        "archive": "MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES",
    }[bound]
    monkeypatch.setattr(bridge, constant, 1)
    with pytest.raises(ValidationError):
        bridge._report_archive(payload, tmp_path / "response.tar.gz")


def test_report_failure_prevents_publication_and_binary_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path)

    def oversized(_payload: Path, _archive: Path) -> None:
        raise ValidationError("response bound exceeded")

    monkeypatch.setattr(bridge, "_report_archive", oversized)
    output = io.BytesIO()
    with pytest.raises(ValidationError, match="bound exceeded"):
        _inspect(fixture, output)
    assert output.getvalue() == b""
    assert not (fixture.new / bridge.PUBLICATION_RELATIVE).exists()


def test_new_pinned_module_runs_through_actual_fixed_dispatcher(tmp_path: Path) -> None:
    from tests.integration.test_hpc_remote_dispatcher import (
        _prepare_remote_layout,
        _run,
    )

    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    site = dispatcher.parent / "site.paths"
    site.write_text("marmic\n", encoding="ascii")
    site.chmod(0o600)
    fixture = _fixture(tmp_path, project=smoke_job.parent.parent, full_source=True)
    python = fixture.new / "environment/.pixi/envs/hpc/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    old_before = _file_digests(fixture.old)
    command = [
        str(dispatcher),
        "inspect-coordinate-cache",
        fixture.new.name,
        NEW_OWNER,
        fixture.old.name,
        OLD_OWNER,
        hashlib.sha256(fixture.request).hexdigest(),
        str(len(fixture.request)),
        fixture.inventory_sha256,
    ]
    # Full-source mock checks use the approved bounded test-only hang guard.
    result = _run(
        command,
        cwd=tmp_path,
        environment=environment,
        input_data=fixture.request,
        timeout_seconds=120.0,
    )
    assert _file_digests(fixture.old) == old_before
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:gz") as archive:
        assert archive.getnames() == list(bridge.REPORT_FILES)
    assert (fixture.new / bridge.PUBLICATION_RELATIVE / "inspection.json").is_file()
    log = (fixture.new / "logs/m6-coordinate-inspection.log").read_text()
    assert NEW_OWNER not in log and OLD_OWNER not in log
    replay = _run(
        command,
        cwd=tmp_path,
        environment=environment,
        input_data=fixture.request,
        success=False,
        timeout_seconds=120.0,
    )
    assert _decode_remote_fields(replay.stdout)["failure_class"] == "wrapper_failure"
    logs = _run(
        [str(dispatcher), "logs", fixture.new.name, NEW_OWNER, "40"],
        cwd=tmp_path,
        environment=environment,
    )
    fields = _decode_remote_fields(logs.stdout)
    assert fields["log_path"] == str(fixture.new / "logs/m6-coordinate-inspection.log")
    content = base64.b64decode(fields["content_base64"]).decode("utf-8")
    assert "already exists; preserve it" in content
    assert NEW_OWNER not in content and OLD_OWNER not in content
    assert _file_digests(fixture.old) == old_before
