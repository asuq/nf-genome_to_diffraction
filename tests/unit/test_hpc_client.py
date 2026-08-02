"""Tests for local ownership, transitions, collection, and feedback limits."""

import base64
import io
import json
import tarfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from genome_to_diffraction.hpc.client import HpcController
from genome_to_diffraction.hpc.models import (
    FailureClass,
    HpcConfig,
    RemoteOperationError,
    ValidationError,
)

COMMIT = "1" * 40


@dataclass
class FakeGit:
    dirty: bool = False

    def ensure_clean(self) -> None:
        if self.dirty:
            raise ValidationError("dirty")

    def resolve_commit(self, revision: str) -> str:
        if revision not in {"HEAD", COMMIT}:
            raise ValidationError("revision")
        return COMMIT


@dataclass
class FakeTransport:
    archive: bytes = b""
    status_responses: list[dict[str, str]] = field(default_factory=list)
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def run(self, operation: str, arguments: Sequence[str]) -> dict[str, str]:
        self.calls.append((operation, tuple(arguments)))
        if operation == "status" and self.status_responses:
            return self.status_responses.pop(0)
        if operation == "logs":
            return {
                "run_id": arguments[0],
                "content_base64": base64.b64encode(b"line one\nline two\n").decode(),
            }
        return {"run_id": arguments[0], "remote_operation": operation}

    def collect(self, run_id: str, owner_id: str) -> bytes:
        self.calls.append(("collect", (run_id, owner_id)))
        return self.archive


def _config(repository: Path) -> HpcConfig:
    return HpcConfig(
        repository=repository,
        ssh_alias="marmic",
        remote_dispatcher="/approved/root/_tooling/nf-gtd-hpc-remote",
        local_state_root=repository / ".untracked" / "hpc-test",
        poll_seconds=1,
        queue_timeout_seconds=1,
        execution_timeout_seconds=1,
    )


def _archive(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        for name, payload in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return output.getvalue()


def _controller(tmp_path: Path, transport: FakeTransport) -> HpcController:
    (tmp_path / "pixi.lock").write_text("locked\n", encoding="utf-8")
    return HpcController(
        _config(tmp_path),
        transport=transport,
        git=FakeGit(),
        progress=False,
    )


def test_all_owned_operations_use_the_recorded_capability(tmp_path: Path) -> None:
    transport = FakeTransport(
        status_responses=[
            {
                "run_id": "placeholder",
                "scheduler_state": "COMPLETED",
                "terminal": "true",
                "failure_class": "success",
            }
        ]
    )
    controller = _controller(tmp_path, transport)

    staged = controller.stage("smoke", "HEAD")
    run_id = str(staged["run_id"])
    assert controller.submit("smoke", run_id)["operation"] == "submit"
    assert controller.status(run_id)["operation"] == "status"
    assert controller.logs(run_id, 200)["log"] == "line one\nline two\n"
    assert controller.cancel(run_id)["operation"] == "cancel"
    assert controller.clean(run_id, run_id)["operation"] == "clean"

    owner_values = {
        arguments[1]
        for operation, arguments in transport.calls
        if operation in {"submit", "status", "logs", "cancel", "clean"}
    }
    assert len(owner_values) == 1


def test_stage_refuses_dirty_or_injected_revisions(tmp_path: Path) -> None:
    (tmp_path / "pixi.lock").write_text("locked\n", encoding="utf-8")
    transport = FakeTransport()
    dirty = HpcController(
        _config(tmp_path), transport=transport, git=FakeGit(dirty=True), progress=False
    )
    with pytest.raises(ValidationError, match="dirty"):
        dirty.stage("smoke", "HEAD")

    clean = HpcController(
        _config(tmp_path), transport=transport, git=FakeGit(), progress=False
    )
    with pytest.raises(ValidationError):
        clean.stage("smoke", "HEAD; touch bad")
    assert transport.calls == []


def test_wait_reports_bounded_queue_timeout_without_cancelling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = FakeTransport(
        status_responses=[
            {"scheduler_state": "PENDING", "terminal": "false"},
        ]
    )
    controller = _controller(tmp_path, transport)
    run_id = str(controller.stage("smoke", "HEAD")["run_id"])
    monkeypatch.setattr("genome_to_diffraction.hpc.client.time.sleep", lambda _: None)

    result = controller.wait(run_id)

    assert result["failure_class"] == FailureClass.QUEUE_TIMEOUT
    assert all(operation != "cancel" for operation, _ in transport.calls)


def test_collection_extracts_regular_whitelisted_payload_safely(tmp_path: Path) -> None:
    job_result = json.dumps(
        {
            "failure_class": "test_failure",
            "exit_code": 1,
            "scheduler_state": "FAILED",
        }
    ).encode()
    transport = FakeTransport(
        archive=_archive(
            {
                "manifest.json": b"{}\n",
                "state/job-result.json": job_result,
                "logs/smoke.log": b"failed\n",
            }
        )
    )
    controller = _controller(tmp_path, transport)
    run_id = str(controller.stage("smoke", "HEAD")["run_id"])

    result = controller.collect(run_id)

    assert result["failure_signature"] is not None
    assert (Path(str(result["destination"])) / "logs" / "smoke.log").read_text() == (
        "failed\n"
    )


def test_collection_rejects_path_traversal(tmp_path: Path) -> None:
    transport = FakeTransport(archive=_archive({"../outside": b"bad"}))
    controller = _controller(tmp_path, transport)
    run_id = str(controller.stage("smoke", "HEAD")["run_id"])

    with pytest.raises(RemoteOperationError, match="unsafe archive member"):
        controller.collect(run_id)
    assert not (tmp_path / "outside").exists()


def test_collection_rejects_symlinked_parent(tmp_path: Path) -> None:
    transport = FakeTransport(archive=_archive({"logs/smoke.log": b"bad"}))
    controller = _controller(tmp_path, transport)
    run_id = str(controller.stage("smoke", "HEAD")["run_id"])
    destination = tmp_path / ".untracked" / "hpc-test" / run_id / "collected"
    outside = tmp_path / "outside"
    outside.mkdir()
    destination.mkdir(parents=True)
    (destination / "logs").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RemoteOperationError, match="escaped collection root"):
        controller.collect(run_id)
    assert list(outside.iterdir()) == []


def test_same_failure_twice_stops_the_feedback_chain(tmp_path: Path) -> None:
    job_result = json.dumps(
        {
            "failure_class": "test_failure",
            "exit_code": 1,
            "scheduler_state": "FAILED",
        }
    ).encode()
    transport = FakeTransport(archive=_archive({"state/job-result.json": job_result}))
    controller = _controller(tmp_path, transport)
    first = str(controller.stage("smoke", "HEAD")["run_id"])
    controller.collect(first)
    second = str(controller.stage("smoke", "HEAD", parent_run_id=first)["run_id"])
    controller.collect(second)

    with pytest.raises(ValidationError, match="occurred twice"):
        controller.stage("smoke", "HEAD", parent_run_id=second)


def test_unowned_run_cannot_be_cancelled(tmp_path: Path) -> None:
    transport = FakeTransport()
    controller = _controller(tmp_path, transport)
    run_id = "gtd-smoke-20260802T120000Z-0123456789ab-01234567"
    with pytest.raises(ValidationError, match="not found"):
        controller.cancel(run_id)
    assert transport.calls == []
