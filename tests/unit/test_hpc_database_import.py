"""Read-only handover of the one existing database bootstrap into the common CLI."""

import base64
import hashlib
import io
import json
import socket
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from genome_to_diffraction.hpc.client import (
    GitRepository,
    HpcController,
    TextTransport,
    _decode_remote_fields,
)
from genome_to_diffraction.hpc.models import HpcConfig, RemoteOperationError

ROOT = Path(__file__).resolve().parents[2]
COMMIT = "1" * 40
RUNTIME = "2" * 40
RUN = f"gtd-raven-database-login-{COMMIT[:12]}-20260911-abcdef"
PROCESS = {
    "pid": 12345,
    "start_ticks": "1234567",
    "boot_id": "01234567-89ab-cdef-0123-456789abcdef",
}


def _write(path: Path, value: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(payload)
    return payload


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, object]]:
    root = tmp_path / "remote"
    bootstrap = root / "bootstrap/database-login-20260911-seqres-v5"
    run = root / "runs" / RUN
    source = run / "source"
    source.mkdir(parents=True)
    lock = b"locked fixture\n"
    (source / "pixi.lock").write_bytes(lock)
    launch = {
        "schema_version": "1.0",
        "run_id": RUN,
        "source_commit": COMMIT,
        "runtime_source_commit": RUNTIME,
        "pixi_lock_sha256": hashlib.sha256(lock).hexdigest(),
        "purpose": "reference_database_login_build_not_M6",
        "execution_site": "raven_login",
        "threads": 1,
    }
    launch_path = bootstrap / "launch.json"
    _write(launch_path, launch)
    script = bootstrap / "run_login_database.py"
    script.write_text("raise RuntimeError('must never execute this historical file')\n")
    members = {
        name: {
            "sha256": hashlib.sha256((bootstrap / name).read_bytes()).hexdigest(),
            "size_bytes": (bootstrap / name).stat().st_size,
        }
        for name in ("launch.json", "run_login_database.py")
    }
    members["source.tar"] = {"sha256": "a" * 64, "size_bytes": 100}
    _write(bootstrap / "deployment-index.json", members)
    _write(bootstrap / "deployment-record.json", {"members": members})
    controller = {"run_id": RUN, "host": "raven03", "process": PROCESS}
    _write(run / "controller.json", controller)
    manifest = {"fixture": "original"}
    current_bytes = _write(root / "databases/database_manifest.json", manifest)
    _write(run / "artifacts/database_manifest.json", manifest)
    verified_bytes = _write(
        run / "artifacts/database_manifest.full-verified.json", {"fixture": "verified"}
    )
    _write(run / "artifacts/preflight.json", {"fixture": "preflight"})
    state = {
        **controller,
        "phase": "completed",
        "source_commit": COMMIT,
        "runtime_source_commit": RUNTIME,
        "threads": 1,
        "allowed_cpus": [0],
        "native_M6_qualification": False,
        "database_manifest": str(root / "databases/database_manifest.json"),
        "database_manifest_sha256": hashlib.sha256(current_bytes).hexdigest(),
        "verified_manifest_sha256": hashlib.sha256(verified_bytes).hexdigest(),
    }
    _write(run / "state.json", state)
    (run / "build.log").write_text("original build evidence\n")
    observation = bootstrap / "start-observation.json"
    _write(observation, {**state, "phase": "building"})
    tooling = root / "_tooling"
    tooling.mkdir()
    site = tooling / "site.paths"
    site.write_text(
        "\n".join(
            [
                "raven",
                str(root),
                "fixed-pixi",
                RUNTIME,
                launch["pixi_lock_sha256"],
                "f" * 64,
                "mmm_cpu",
                "raven03",
                "",
            ]
        )
    )
    dispatcher = tooling / "nf-gtd-hpc-remote"
    dispatcher.write_bytes((ROOT / "bootstrap/nf-gtd-hpc-remote").read_bytes())
    authority = {
        "launch": launch,
        "run_id": RUN,
        "host": "raven03",
        "process": PROCESS,
        "deployment_members": members,
        "dispatcher_sha256": hashlib.sha256(dispatcher.read_bytes()).hexdigest(),
    }
    return root, launch_path, observation, authority


def _read_remote(
    root: Path, authority: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    dispatcher = root / "_tooling/nf-gtd-hpc-remote"
    program = (
        dispatcher.read_text()
        .split("<<'RAVEN_DATABASE_IMPORT_PY'\n", 1)[1]
        .split("\nRAVEN_DATABASE_IMPORT_PY\n", 1)[0]
    )
    monkeypatch.setattr(socket, "gethostname", lambda: "raven03")

    def git_probe(arguments: list[str], **kwargs: object) -> SimpleNamespace:
        assert arguments[:3] == ["git", "-C", str(root / "runs" / RUN / "source")]
        assert arguments[3:] in (
            ["rev-parse", "HEAD"],
            ["status", "--porcelain=v1", "--untracked-files=all"],
        )
        return SimpleNamespace(stdout=COMMIT if arguments[3] == "rev-parse" else "")

    monkeypatch.setattr(subprocess, "run", git_probe)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "-",
            str(root),
            str(root / "_tooling/site.paths"),
            str(dispatcher),
            base64.b64encode(json.dumps(authority).encode()).decode(),
        ],
    )
    output = io.StringIO()
    with redirect_stdout(output):
        exec(compile(program, "database-import-test", "exec"), {})
    return _decode_remote_fields(output.getvalue().encode())


def test_existing_database_import_is_read_only_and_keeps_original_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, launch, observation, authority = _fixture(tmp_path)
    before = {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }

    def transport(operation: str, arguments: list[str]) -> dict[str, str]:
        assert operation == "raven-database-import" and len(arguments) == 1
        supplied = json.loads(base64.b64decode(arguments[0]))
        assert supplied == authority
        return _read_remote(root, supplied, monkeypatch)

    config = HpcConfig(
        repository=ROOT,
        site_id="raven",
        ssh_alias="raven",
        remote_dispatcher="/ptmp/test/nf-genome_to_diffraction/_tooling/nf-gtd-hpc-remote",
        local_state_root=tmp_path / "local-state",
    )
    git = SimpleNamespace(
        ensure_clean=lambda: None,
        resolve_commit=lambda revision: COMMIT,
        ensure_reachable_from_origin_main=lambda commit: None,
        read_file_at_commit=lambda commit, path: ROOT.joinpath(
            *path.parts
        ).read_bytes(),
    )
    controller = HpcController(
        config,
        git=cast(GitRepository, git),
        transport=cast(TextTransport, SimpleNamespace(run=transport)),
        progress=False,
    )
    result = controller.raven_database_import("HEAD", launch, observation)
    assert result["database_verified"] is True and result["terminal"] is True
    assert result["run_id"] == RUN and result["native_M6_qualification"] is False
    evidence = json.loads(Path(str(result["imported_evidence"])).read_bytes())
    assert evidence["managed_run"] is False
    assert "scheduler_state" not in evidence["state"]
    assert "job_id" not in evidence["state"] and "exit_code" not in evidence["state"]
    assert {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    } == before
    assert not (tmp_path / "local-state/runs").exists()
    assert controller.raven_database_import("HEAD", launch, observation) == result


@pytest.mark.parametrize("tampering", ["process", "script", "manifest", "disappeared"])
def test_existing_database_import_fails_on_changed_or_missing_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tampering: str,
) -> None:
    root, _, _, authority = _fixture(tmp_path)
    run = root / "runs" / RUN
    if tampering == "script":
        (
            root / "bootstrap/database-login-20260911-seqres-v5/run_login_database.py"
        ).write_text("changed")
    elif tampering == "manifest":
        (root / "databases/database_manifest.json").write_text("{}")
    else:
        path = run / "state.json"
        state = json.loads(path.read_bytes())
        if tampering == "process":
            state["process"]["start_ticks"] = "9"
        else:
            state["phase"] = "building"
            authority["process"] = {**PROCESS, "pid": 2147483647}
            state["process"] = authority["process"]
            controller = json.loads((run / "controller.json").read_bytes())
            controller["process"] = authority["process"]
            _write(run / "controller.json", controller)
        _write(path, state)
    with pytest.raises((ValueError, FileNotFoundError, RemoteOperationError)):
        _read_remote(root, authority, monkeypatch)
