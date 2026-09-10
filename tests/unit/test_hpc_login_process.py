"""Test the internal process backend without scheduling scientific work."""

import hashlib
import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

from genome_to_diffraction.hpc import login_process as login

RUN = "gtd-m6-operational-20260911T000000Z-111111111111-01234567"
OWNER = "a" * 32
COMMIT = "1" * 40
PROCESS = {
    "host": "raven03",
    "pid": 12345,
    "start_ticks": "1234567",
    "boot_id": "01234567-89ab-cdef-0123-456789abcdef",
}


def _context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> login.Context:
    run = tmp_path / "runs" / RUN
    for directory in (run / "state", run / "logs", run / "source"):
        directory.mkdir(parents=True)
    runtime_commit = "2" * 40
    runtime = tmp_path / "sources" / runtime_commit
    python = runtime / ".pixi/envs/hpc/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("test runtime\n")
    (runtime / "pixi.lock").write_text("test lock\n")
    lock_sha = hashlib.sha256((runtime / "pixi.lock").read_bytes()).hexdigest()
    (run / "source/.pixi").symlink_to(runtime / ".pixi", target_is_directory=True)
    (tmp_path / "_tooling").mkdir()
    site = tmp_path / "_tooling/site.paths"
    site.write_text(
        "\n".join(
            [
                "raven",
                str(tmp_path),
                str(tmp_path / "software/pixi-0.76.2/pixi"),
                runtime_commit,
                lock_sha,
                "f" * 64,
                "mmm_cpu",
                "raven03",
                "",
            ]
        )
    )
    monkeypatch.setattr(login.sys, "executable", str(python))
    fields = {
        "owner-id": OWNER,
        "site-id": "raven",
        "profile": "m6-operational",
        "commit": COMMIT,
        "controller-kind": "login_process",
        "phase": "staged",
        "runtime-source-commit": runtime_commit,
        "pixi-lock-sha256": lock_sha,
        "login-host": "raven03",
        "site-config-sha256": hashlib.sha256(site.read_bytes()).hexdigest(),
    }
    for name, value in fields.items():
        (run / "state" / name).write_text(value + "\n")
    manifest = {
        "schema_version": "1.1",
        "run_id": RUN,
        "site_id": "raven",
        "profile": "m6-operational",
        "commit": COMMIT,
        "controller_kind": "login_process",
        "source_snapshot_status": "immutable",
    }
    (run / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(login, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(login, "_host", lambda: "raven03")
    monkeypatch.setattr(
        login,
        "__file__",
        str(run / "source/src/genome_to_diffraction/hpc/login_process.py"),
    )
    return login._context(run, OWNER)


def _identity(context: login.Context) -> dict[str, object]:
    identity = {
        **context.identity_fields,
        "process": dict(PROCESS),
        "started_at": "2026-09-11T00:00:00Z",
    }
    (context.run / "state/controller.json").write_text(json.dumps(identity))
    (context.run / "state/phase").write_text("running\n")
    (context.run / "state/controller-state").write_text("RUNNING\n")
    return identity


@pytest.mark.parametrize(
    "change",
    ["owner", "site", "source", "kind", "symlink", "runtime", "lock", "binding"],
)
def test_login_context_rejects_unowned_or_cross_kind_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    context = _context(tmp_path, monkeypatch)
    state = context.run / "state"
    if change == "owner":
        (state / "owner-id").write_text("b" * 32)
    elif change == "site":
        (state / "site-id").write_text("marmic")
    elif change == "source":
        (state / "commit").write_text("f" * 40)
    elif change == "kind":
        (state / "controller-kind").write_text("slurm_job")
    elif change == "symlink":
        (state / "owner-id").unlink()
        (state / "owner-id").symlink_to(state / "commit")
    elif change == "runtime":
        monkeypatch.setattr(login.sys, "executable", "/unrelated/python")
    elif change == "lock":
        (tmp_path / "sources" / ("2" * 40) / "pixi.lock").write_text("changed\n")
    else:
        (state / "site-config-sha256").write_text("f" * 64)
    with pytest.raises(ValueError):
        login._context(context.run, OWNER)


def test_login_status_never_infers_completion_after_pid_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    _identity(context)
    monkeypatch.setattr(login, "_process_identity", lambda pid: dict(PROCESS))
    assert login.status(context)["controller_state"] == "RUNNING"
    monkeypatch.setattr(
        login, "_process_identity", lambda pid: {**PROCESS, "start_ticks": "1234568"}
    )
    with pytest.raises(ValueError, match="without terminal evidence"):
        login.status(context)
    assert not (context.run / "state/controller-result.json").exists()


@pytest.mark.parametrize("race", [False, True])
def test_login_cancellation_signals_only_the_verified_pidfd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    race: bool,
) -> None:
    context = _context(tmp_path, monkeypatch)
    _identity(context)
    observations = iter(
        [dict(PROCESS), {**PROCESS, "start_ticks": "9"} if race else dict(PROCESS)]
    )
    monkeypatch.setattr(login, "_process_identity", lambda pid: next(observations))
    monkeypatch.setattr(login.sys, "platform", "linux")
    signals, closed = [], []
    monkeypatch.setattr(
        login.os, "pidfd_open", lambda pid: 99 if pid == 12345 else -1, raising=False
    )
    monkeypatch.setattr(
        login.signal,
        "pidfd_send_signal",
        lambda fd, signum: signals.append((fd, signum)),
        raising=False,
    )
    monkeypatch.setattr(login.os, "close", lambda fd: closed.append(fd))
    if race:
        with pytest.raises(ValueError, match="identity changed"):
            login.cancel(context)
        assert signals == []
    else:
        result = login.cancel(context)
        assert result["controller_state"] == "CANCELLING"
        assert signals == [(99, signal.SIGTERM)]
        assert "job_id" not in result and "scheduler_state" not in result
    assert closed == [99]


@pytest.mark.parametrize("body", ["success", "missing", "contradictory", "cancelled"])
def test_login_supervisor_reuses_shared_body_and_requires_its_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body: str,
) -> None:
    context = _context(tmp_path, monkeypatch)
    monkeypatch.setattr(login, "_process_identity", lambda pid: dict(PROCESS))
    monkeypatch.setattr(login, "_affinity", lambda: [4, 5])
    affinity, commands, handlers, forwarded = [], [], {}, []
    monkeypatch.setattr(login, "_set_affinity", lambda cpus: affinity.append(cpus))
    monkeypatch.setattr(
        login.signal, "signal", lambda signum, fn: handlers.update({signum: fn})
    )
    monkeypatch.setattr(
        login.os, "killpg", lambda pid, signum: forwarded.append((pid, signum))
    )
    exit_code = 143 if body == "cancelled" else 0

    def wait() -> int:
        if body == "cancelled":
            handlers[signal.SIGTERM](signal.SIGTERM, None)
        return exit_code

    def popen(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append((command, kwargs))
        if body != "missing":
            payload = {
                "run_id": RUN,
                "profile": "m6-operational",
                "controller_kind": "login_process",
                "controller_state": "CANCELLED" if body == "cancelled" else "COMPLETED",
                "exit_code": 1 if body == "contradictory" else exit_code,
                "failure_class": "unknown_failure"
                if body == "cancelled"
                else "success",
                "started_at": "2026-09-11T00:00:00Z",
                "completed_at": "2026-09-11T00:01:00Z",
                "structured_test_reports": [],
                "retained_artifacts": [],
            }
            (context.run / "state/body-result.json").write_text(json.dumps(payload))
        return SimpleNamespace(pid=12346, wait=wait, poll=lambda: None)

    monkeypatch.setattr(login.subprocess, "Popen", popen)
    read_fd, ready_fd = os.pipe()
    try:
        result_code = login._supervise(context, ready_fd)
        assert os.read(read_fd, 1) == b"1"
    finally:
        os.close(read_fd)
    assert affinity == [[4, 5]]
    command, kwargs = commands[0]
    assert command == [
        "/bin/bash",
        str(context.run / "source/bootstrap/nf-gtd-hpc-smoke-job"),
        RUN,
        str(context.root),
        "m6-operational",
    ]
    assert kwargs["start_new_session"] is True
    result = json.loads((context.run / "state/controller-result.json").read_text())
    assert result["controller_kind"] == "login_process" and result["process"] == PROCESS
    assert "scheduler_state" not in result and "job_id" not in result
    if body in {"missing", "contradictory"}:
        assert result_code != 0 and result["failure_class"] == "wrapper_failure"
    elif body == "cancelled":
        assert result_code == 143 and result["controller_state"] == "CANCELLED"
        assert forwarded == [(12346, signal.SIGTERM)]
    else:
        assert result_code == 0 and result["controller_state"] == "COMPLETED"
    assert login.status(context)["terminal"] == "true"


def test_login_start_refuses_a_previous_submission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    _identity(context)

    def unexpected_start(*args: object, **kwargs: object) -> None:
        raise AssertionError("restarted")

    monkeypatch.setattr(login.subprocess, "Popen", unexpected_start)
    with pytest.raises(ValueError, match="unsubmitted staged"):
        login.start(context)
