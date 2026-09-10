"""Internal process lifecycle for the common fixed HPC dispatcher.

The dispatcher supplies an owned, immutable Raven run and its capability. This
module supervises the existing shared job body; it does not implement scientific
work, SSH transport, staging or collection. Nextflow owns all scientific Slurm
children. Linux /proc, pidfds and Python 3.14 are required. Process records bind
host, boot ID, PID and start ticks; missing completion evidence is an error, never
an inferred success. STARTING/RUNNING/CANCELLING are nonterminal; terminal results
use COMPLETED/FAILED/CANCELLED. There is no scientific cache. Unit tests cover
ownership, PID reuse, signal targeting, command construction and result failures.
"""

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import resource
import select
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from genome_to_diffraction.checksums import atomic_write_json, atomic_write_text
from genome_to_diffraction.execution_evidence import (
    validate_login_result_binding,
    validate_process_identity,
)
from genome_to_diffraction.hpc.client import (
    _validated_failure_outcome,
    _validated_terminal_inventory,
    _validated_terminal_timestamps,
)
from genome_to_diffraction.hpc.models import (
    COMMIT_PATTERN,
    OWNER_PATTERN,
    controller_kind_for_profile,
    validate_run_id,
)
from genome_to_diffraction.schemas.io import parse_json_document

MAX_RECORD_BYTES = 2 * 1024**2
_ACTIVE_STATES = frozenset({"STARTING", "RUNNING", "CANCELLING"})


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _project_root() -> Path:
    user = os.environ.get("USER", "")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", user) is None:
        raise ValueError("unsafe Raven account identity")
    return Path("/ptmp") / user / "nf-genome_to_diffraction"


def _host() -> str:
    host = socket.gethostname().split(".")[0]
    if re.fullmatch(r"raven0[1-4]i?", host) is None:
        raise ValueError("login controller requires a Raven login host")
    return host


def _owned_file(path: Path) -> bytes:
    record = path.lstat()
    if (
        not stat.S_ISREG(record.st_mode)
        or record.st_uid != os.getuid()
        or not 0 < record.st_size <= MAX_RECORD_BYTES
    ):
        raise ValueError(f"unsafe, empty or oversized owned record: {path.name}")
    payload = path.read_bytes()
    if len(payload) != record.st_size:
        raise ValueError(f"owned record changed while reading: {path.name}")
    return payload


def _text(path: Path) -> str:
    return _owned_file(path).decode("ascii").removesuffix("\n")


def _json(path: Path) -> dict[str, object]:
    value = parse_json_document(_owned_file(path).decode("utf-8"), label=path.name)
    if not isinstance(value, dict):
        raise ValueError(f"owned record is not an object: {path.name}")
    return value


def _exclusive_json(path: Path, value: Mapping[str, object]) -> None:
    """Publish launch identity once; never replace an existing capability."""

    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=".controller-", mode="w", encoding="utf-8"
    ) as handle:
        json.dump(value, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        os.link(handle.name, path, follow_symlinks=False)


@dataclass(frozen=True)
class Context:
    """Run-owned source and capability, not a user-selectable execution command."""

    root: Path
    run: Path
    owner: str
    profile: str
    commit: str

    @property
    def identity_fields(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "run_id": self.run.name,
            "owner_id": self.owner,
            "site_id": "raven",
            "profile": self.profile,
            "source_commit": self.commit,
            "controller_kind": "login_process",
        }


def _context(run: Path, owner: str) -> Context:
    root = _project_root()
    _host()
    validate_run_id(run.name)
    if not OWNER_PATTERN.fullmatch(owner) or run.parent != root / "runs":
        raise ValueError("run is outside the fixed owned namespace")
    for path in (root, root / "runs", run, run / "state", run / "logs", run / "source"):
        record = path.lstat()
        if not stat.S_ISDIR(record.st_mode) or record.st_uid != os.getuid():
            raise ValueError("unsafe owned run directory")
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("owned run directory escapes the project root")
    state = run / "state"
    if _text(state / "owner-id") != owner or _text(state / "site-id") != "raven":
        raise ValueError("run ownership or site differs")
    site_payload = _owned_file(root / "_tooling/site.paths")
    site_fields = site_payload.decode("ascii").splitlines()
    runtime_commit = _text(state / "runtime-source-commit")
    if (
        len(site_fields) != 8
        or site_fields[:2] != ["raven", str(root)]
        or site_fields[3] != runtime_commit
        or not COMMIT_PATTERN.fullmatch(runtime_commit)
        or site_fields[4] != _text(state / "pixi-lock-sha256")
        or site_fields[7] != _host()
        or _text(state / "login-host") != _host()
        or hashlib.sha256(site_payload).hexdigest()
        != _text(state / "site-config-sha256")
    ):
        raise ValueError("staged login site/runtime binding changed")
    runtime = root / "sources" / runtime_commit
    runtime_environment = (runtime / ".pixi").resolve(strict=True)
    if (
        not runtime_environment.is_relative_to(root.resolve())
        or (run / "source/.pixi").resolve(strict=True) != runtime_environment
        or Path(sys.executable).resolve()
        != (runtime_environment / "envs/hpc/bin/python").resolve(strict=True)
        or hashlib.sha256(_owned_file(runtime / "pixi.lock")).hexdigest()
        != site_fields[4]
    ):
        raise ValueError("controller is not using the anchored locked runtime")
    profile, commit = _text(state / "profile"), _text(state / "commit")
    if (
        controller_kind_for_profile("raven", profile) != "login_process"
        or _text(state / "controller-kind") != "login_process"
        or not COMMIT_PATTERN.fullmatch(commit)
        or run.name.split("-")[-2] != commit[:12]
    ):
        raise ValueError("run source/profile/controller kind differs")
    context = Context(root, run, owner, profile, commit)
    if (
        Path(__file__).resolve()
        != (run / "source/src/genome_to_diffraction/hpc/login_process.py").resolve()
    ):
        raise ValueError("controller implementation is not the owned immutable source")
    manifest = _json(run / "manifest.json")
    for key, expected in {
        "schema_version": "1.1",
        "run_id": run.name,
        "site_id": "raven",
        "profile": profile,
        "commit": commit,
        "controller_kind": "login_process",
        "source_snapshot_status": "immutable",
    }.items():
        if manifest.get(key) != expected:
            raise ValueError(f"run manifest {key} differs")
    return context


def _process_identity(pid: int) -> dict[str, object] | None:
    if type(pid) is not int or pid <= 0:
        raise ValueError("controller PID must be positive")
    proc = Path("/proc") / str(pid)
    try:
        record = proc.stat()
        fields = (proc / "stat").read_text().rsplit(") ", 1)[1].split()
        if record.st_uid != os.getuid() or fields[0] == "Z":
            return None
        identity = {
            "host": _host(),
            "pid": pid,
            "start_ticks": fields[19],
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        }
    except FileNotFoundError:
        return None
    validate_process_identity(identity)
    return identity


def _identity(context: Context) -> dict[str, object]:
    record = _json(context.run / "state/controller.json")
    if any(
        record.get(key) != expected for key, expected in context.identity_fields.items()
    ):
        raise ValueError("controller identity belongs to another source/profile/owner")
    process = validate_process_identity(record.get("process"))
    if process["host"] != _host():
        raise ValueError("controller belongs to a different login host")
    return record


def _terminal_result(
    context: Context, identity: Mapping[str, object]
) -> dict[str, object]:
    result = _json(context.run / "state/controller-result.json")
    validate_login_result_binding(
        identity,
        result,
        run_id=context.run.name,
        owner_id=context.owner,
        profile=context.profile,
        source_commit=context.commit,
    )
    _validated_failure_outcome(result, controller_kind="login_process")
    _validated_terminal_timestamps(result)
    _validated_terminal_inventory(result)
    return result


def status(context: Context) -> dict[str, str]:
    """Inspect only the owned process; missing terminal evidence fails explicitly."""

    state = context.run / "state"
    phase = _text(state / "phase")
    base = {
        "operation": "status",
        "run_id": context.run.name,
        "site_id": "raven",
        "profile": context.profile,
        "commit": context.commit,
        "controller_kind": "login_process",
        "phase": phase,
    }
    if not (state / "controller.json").exists():
        if phase not in {"staged", "stage_failed"}:
            raise ValueError(
                "controller launch identity is absent; inspect its retained log"
            )
        return {
            **base,
            "controller_state": phase.upper(),
            "terminal": "true" if phase == "stage_failed" else "false",
        }
    identity = _identity(context)
    process = validate_process_identity(identity["process"])
    details = {f"controller_{key}": str(value) for key, value in process.items()}
    if (state / "controller-result.json").exists():
        result = _terminal_result(context, identity)
        return {
            **base,
            **details,
            "controller_state": str(result["controller_state"]),
            "terminal": "true",
            "exit_code": str(result["exit_code"]),
            "failure_class": str(result["failure_class"]),
        }
    if _process_identity(cast(int, process["pid"])) != process:
        raise ValueError("owned controller disappeared without terminal evidence")
    observed = _text(state / "controller-state")
    if observed not in _ACTIVE_STATES:
        raise ValueError("controller state is invalid without terminal evidence")
    return {**base, **details, "controller_state": observed, "terminal": "false"}


def start(context: Context) -> dict[str, str]:
    """Detach one source-owned supervisor and wait for its identity handshake."""

    state = context.run / "state"
    lock_path = state / "login-start.lock"
    if lock_path.is_symlink():
        raise ValueError("unsafe login start lock")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if _text(state / "phase") != "staged" or any(
            (state / name).exists() or (state / name).is_symlink()
            for name in ("controller.json", "controller-result.json", "job-id")
        ):
            raise ValueError("run is not an unsubmitted staged login controller")
        atomic_write_text(state / "phase", "submitting\n")
        read_fd, ready_fd = os.pipe()
        try:
            with (context.run / "logs/controller.log").open("xb") as log:
                environment = os.environ.copy()
                environment["PYTHONPATH"] = str(context.run / "source/src")
                try:
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "genome_to_diffraction.hpc.login_process",
                            "supervise",
                            "--run",
                            str(context.run),
                            "--owner",
                            context.owner,
                            "--ready-fd",
                            str(ready_fd),
                        ],
                        cwd=context.run,
                        env=environment,
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                        pass_fds=(ready_fd,),
                    )
                except OSError:
                    atomic_write_text(state / "failure-class", "wrapper_failure\n")
                    atomic_write_text(state / "exit-code", "1\n")
                    atomic_write_text(state / "phase", "stage_failed\n")
                    raise
            os.close(ready_fd)
            ready_fd = -1
            readable, _, _ = select.select([read_fd], [], [], 10)
            if not readable or os.read(read_fd, 1) != b"1":
                raise RuntimeError(
                    "controller launch handshake failed; do not restart this run"
                )
        finally:
            os.close(read_fd)
            if ready_fd >= 0:
                os.close(ready_fd)
    return {**status(context), "operation": "submit"}


def cancel(context: Context) -> dict[str, str]:
    """Signal exactly the authenticated supervisor through a Linux pidfd."""

    current = status(context)
    if current["terminal"] == "true":
        raise ValueError("owned controller is already terminal")
    identity = _identity(context)
    process = validate_process_identity(identity["process"])
    pid = cast(int, process["pid"])
    if sys.platform == "linux":
        descriptor = os.pidfd_open(pid)
        try:
            if _process_identity(pid) != process:
                raise ValueError("controller PID identity changed before cancellation")
            atomic_write_text(context.run / "state/controller-state", "CANCELLING\n")
            signal.pidfd_send_signal(descriptor, signal.SIGTERM)
        finally:
            os.close(descriptor)
    else:
        raise RuntimeError("Raven cancellation requires Linux pidfd support")
    return {
        **current,
        "operation": "cancel",
        "controller_state": "CANCELLING",
        "cancel_requested": "true",
    }


def _affinity() -> list[int]:
    if sys.platform == "linux":
        return sorted(os.sched_getaffinity(0))
    raise RuntimeError("Raven supervision requires Linux CPU affinity support")


def _set_affinity(cpus: list[int]) -> None:
    if sys.platform == "linux":
        os.sched_setaffinity(0, cpus)
    else:
        raise RuntimeError("Raven supervision requires Linux CPU affinity support")


def _supervise(context: Context, ready_fd: int) -> int:
    state = context.run / "state"
    child: subprocess.Popen[bytes] | None = None
    cancellation_requested = False

    def forward_signal(signum: int, frame: object) -> None:
        nonlocal cancellation_requested
        cancellation_requested = True
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signum)

    signal.signal(signal.SIGTERM, forward_signal)
    signal.signal(signal.SIGINT, forward_signal)
    process = _process_identity(os.getpid())
    if process is None:
        raise RuntimeError("cannot record supervisor process identity")
    identity = {
        **context.identity_fields,
        "process": process,
        "started_at": _timestamp(),
    }
    _exclusive_json(state / "controller.json", identity)
    atomic_write_text(state / "controller-state", "STARTING\n")
    os.write(ready_fd, b"1")
    os.close(ready_fd)
    result: dict[str, object] = {}
    exit_code = 1
    observed_affinity: list[int] | None = None
    try:
        cpus = _affinity()[:2]
        if not cpus:
            raise RuntimeError("login controller has no available CPU affinity")
        _set_affinity(cpus)
        observed_affinity = _affinity()
        environment = os.environ.copy()
        environment["GTD_CONTROLLER_KIND"] = "login_process"
        environment["PYTHONPATH"] = str(context.run / "source/src")
        command = [
            "/bin/bash",
            str(context.run / "source/bootstrap/nf-gtd-hpc-smoke-job"),
            context.run.name,
            str(context.root),
            context.profile,
        ]
        if cancellation_requested:
            raise RuntimeError("controller cancellation requested before body launch")
        child = subprocess.Popen(
            command,
            cwd=context.run,
            env=environment,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        atomic_write_text(state / "controller-state", "RUNNING\n")
        return_code = child.wait()
        exit_code = return_code if return_code >= 0 else 128 - return_code
        result = _json(state / "body-result.json")
        if (
            result.get("run_id") != context.run.name
            or result.get("profile") != context.profile
            or result.get("exit_code") != exit_code
        ):
            raise ValueError("shared body result does not match its owned execution")
        _validated_failure_outcome(result, controller_kind="login_process")
        _validated_terminal_timestamps(result)
        _validated_terminal_inventory(result)
    except Exception as error:
        traceback.print_exc()
        before_body_cancelled = cancellation_requested and child is None
        exit_code = 143 if before_body_cancelled else exit_code or 1
        result = {
            "controller_state": "CANCELLED" if before_body_cancelled else "FAILED",
            "exit_code": exit_code,
            "failure_class": "unknown_failure"
            if before_body_cancelled
            else "wrapper_failure",
            "structured_test_reports": [],
            "retained_artifacts": [],
            "completion_error": str(error),
        }
    result.update(
        {
            **identity,
            "completed_at": _timestamp(),
            "exit_code": exit_code,
            "standard_output": "logs/controller.log",
            "standard_error": "logs/controller.log",
            "application_log": f"logs/{context.profile}.log",
            "cancellation_requested": cancellation_requested,
            "child_max_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            "controller_cpu_affinity": observed_affinity,
        }
    )
    atomic_write_text(state / "exit-code", f"{exit_code}\n")
    atomic_write_text(state / "failure-class", f"{result['failure_class']}\n")
    atomic_write_text(state / "phase", "completed\n")
    atomic_write_json(state / "controller-result.json", result)
    return exit_code


def main() -> int:
    """Internal fixed-dispatcher boundary; not a separate user-facing client."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("start", "status", "cancel", "supervise"))
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--ready-fd", type=int)
    args = parser.parse_args()
    context = _context(args.run, args.owner)
    if args.operation == "supervise":
        if args.ready_fd is None or args.ready_fd <= 2:
            raise ValueError("supervisor requires its inherited launch handshake")
        return _supervise(context, args.ready_fd)
    if args.ready_fd is not None:
        raise ValueError("handshake descriptor is private to the supervisor")
    operations = {"start": start, "status": status, "cancel": cancel}
    for key, value in operations[args.operation](context).items():
        print(f"{key}\t{base64.b64encode(value.encode()).decode('ascii')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
