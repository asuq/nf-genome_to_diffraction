"""Local controller for the fixed Marmic remote test dispatcher."""

import base64
import hashlib
import io
import json
import logging
import os
import secrets
import shlex
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol

from tqdm import tqdm

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.hpc.models import (
    COMMIT_PATTERN,
    MAX_ARTIFACT_FILE_BYTES,
    MAX_ARTIFACT_TOTAL_BYTES,
    MAX_FEEDBACK_RUNS,
    FailureClass,
    HpcConfig,
    LocalRunRecord,
    RemoteOperationError,
    ValidationError,
    load_local_run,
    validate_commit,
    validate_log_lines,
    validate_profile,
    validate_run_id,
)

_TERMINAL_STATES = frozenset(
    {
        "BOOT_FAIL",
        "CANCELLED",
        "COMPLETED",
        "DEADLINE",
        "FAILED",
        "NODE_FAIL",
        "OUT_OF_MEMORY",
        "PREEMPTED",
        "REVOKED",
        "TIMEOUT",
    }
)
_QUEUED_STATES = frozenset(
    {"CONFIGURING", "PENDING", "REQUEUE_FED", "REQUEUE_HOLD", "REQUEUED"}
)
_REMOTE_TOOL_PATHS = (
    PurePosixPath("bootstrap/nf-gtd-hpc-remote"),
    PurePosixPath("bootstrap/nf-gtd-hpc-smoke-job"),
)
SSH_CONNECT_TIMEOUT_SECONDS = 15
SSH_OPERATION_TIMEOUT_SECONDS = 60
DATABASE_STAGE_TIMEOUT_SECONDS = 6 * 60 * 60
SSH_COLLECTION_TIMEOUT_SECONDS = 10 * 60
_SSH_FIXED_OPTIONS = (
    "-o",
    "BatchMode=yes",
    "-o",
    f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
    "-o",
    "ConnectionAttempts=1",
    "-o",
    "ServerAliveInterval=15",
    "-o",
    "ServerAliveCountMax=2",
)


class TextTransport(Protocol):
    """Transport contract used by the controller and deterministic fakes."""

    def run(self, operation: str, arguments: Sequence[str]) -> dict[str, str]:
        """Run one fixed remote operation and return decoded scalar fields."""

    def collect(self, run_id: str, owner_id: str) -> bytes:
        """Return the fixed whitelisted artefact archive for an owned run."""


class GitRepository(Protocol):
    """Local immutable-revision checks needed before staging."""

    def ensure_clean(self) -> None:
        """Fail unless tracked, untracked, and submodule state is clean."""

    def resolve_commit(self, revision: str) -> str:
        """Resolve HEAD or a full SHA to a full commit SHA."""

    def read_file_at_commit(self, commit: str, path: PurePosixPath) -> bytes:
        """Read one fixed repository file from an exact commit."""


class SubprocessGitRepository:
    """Git implementation restricted to one configured local repository."""

    def __init__(self, repository: Path) -> None:
        self._repository = repository

    def _run(self, arguments: Sequence[str]) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self._repository,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise ValidationError(f"local Git check failed: {detail}")
        return result.stdout.strip()

    def ensure_clean(self) -> None:
        """Reject any local source, submodule, or untracked-file changes."""

        status = self._run(
            [
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignore-submodules=none",
            ]
        )
        if status:
            raise ValidationError(
                "stage requires a clean worktree and clean submodules; "
                "commit or remove the reported changes first"
            )

    def resolve_commit(self, revision: str) -> str:
        """Resolve only HEAD or an already-full commit SHA."""

        if revision != "HEAD" and COMMIT_PATTERN.fullmatch(revision) is None:
            raise ValidationError(
                "revision must be HEAD or a full lowercase commit SHA"
            )
        commit = self._run(["rev-parse", "--verify", f"{revision}^{{commit}}"])
        return validate_commit(commit)

    def read_file_at_commit(self, commit: str, path: PurePosixPath) -> bytes:
        """Read a fixed path without checking out or interpreting shell syntax."""

        validate_commit(commit)
        result = subprocess.run(
            ["git", "show", f"{commit}:{path.as_posix()}"],
            cwd=self._repository,
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ValidationError(
                f"cannot read {path.as_posix()} from commit {commit}: {detail}"
            )
        return result.stdout


class SshTransport:
    """Invoke only the configured dispatcher through one SSH alias."""

    def __init__(self, config: HpcConfig) -> None:
        self._config = config

    def _remote_command(self, operation: str, arguments: Sequence[str]) -> str:
        return shlex.join([self._config.remote_dispatcher, operation, *arguments])

    def _command(self, operation: str, arguments: Sequence[str]) -> list[str]:
        """Build the fixed non-interactive SSH invocation."""

        return [
            "ssh",
            *_SSH_FIXED_OPTIONS,
            "--",
            self._config.ssh_alias,
            self._remote_command(operation, arguments),
        ]

    def run(self, operation: str, arguments: Sequence[str]) -> dict[str, str]:
        """Execute an operation and decode its base64 scalar protocol."""

        operation_timeout = (
            DATABASE_STAGE_TIMEOUT_SECONDS
            if operation == "database-stage"
            else SSH_OPERATION_TIMEOUT_SECONDS
        )
        try:
            result = subprocess.run(
                self._command(operation, arguments),
                check=False,
                capture_output=True,
                timeout=operation_timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                f"remote {operation} exceeded the fixed "
                f"{operation_timeout}-second transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        fields = _decode_remote_fields(result.stdout)
        if result.returncode != 0:
            failure = _failure_class(fields.get("failure_class"))
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
            )
            if not message:
                message = (
                    f"remote {operation} failed with exit status {result.returncode}"
                )
            raise RemoteOperationError(message, failure_class=failure)
        if not fields:
            raise RemoteOperationError(
                f"remote {operation} returned no structured fields",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        return fields

    def collect(self, run_id: str, owner_id: str) -> bytes:
        """Stream the fixed remote archive without scp or arbitrary paths."""

        try:
            result = subprocess.run(
                self._command("collect", [run_id, owner_id]),
                check=False,
                capture_output=True,
                timeout=SSH_COLLECTION_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote collection exceeded the fixed "
                f"{SSH_COLLECTION_TIMEOUT_SECONDS}-second transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        if result.returncode != 0:
            fields = _decode_remote_fields(result.stdout)
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
            )
            raise RemoteOperationError(
                message or "remote artefact collection failed",
                failure_class=_failure_class(fields.get("failure_class")),
            )
        return result.stdout


class HpcController:
    """Apply local ownership, iteration, timeout, and collection safeguards."""

    def __init__(
        self,
        config: HpcConfig,
        *,
        transport: TextTransport | None = None,
        git: GitRepository | None = None,
        logger: logging.Logger | None = None,
        progress: bool = True,
    ) -> None:
        self.config = config
        self.transport = transport or SshTransport(config)
        self.git = git or SubprocessGitRepository(config.repository)
        self.logger = logger or logging.getLogger("genome_to_diffraction.hpc")
        self.progress = progress

    def deploy_tools(self, revision: str) -> dict[str, object]:
        """Install the two fixed remote scripts from one clean pushed commit."""

        self.git.ensure_clean()
        commit = self.git.resolve_commit(revision)
        checksums: dict[str, str] = {}
        for relative in _REMOTE_TOOL_PATHS:
            committed = self.git.read_file_at_commit(commit, relative)
            worktree_path = self.config.repository.joinpath(*relative.parts)
            if worktree_path.is_symlink() or not worktree_path.is_file():
                raise ValidationError(
                    f"remote tool must be a regular tracked file: {relative}"
                )
            if worktree_path.read_bytes() != committed:
                raise ValidationError(
                    f"worktree content differs from commit {commit}: {relative}"
                )
            checksums[relative.name] = hashlib.sha256(committed).hexdigest()

        dispatcher_checksum = checksums["nf-gtd-hpc-remote"]
        smoke_job_checksum = checksums["nf-gtd-hpc-smoke-job"]
        self.logger.warning(
            "deploying checksum-verified remote HPC tools",
            extra={
                "commit": commit,
                "dispatcher_sha256": dispatcher_checksum,
                "smoke_job_sha256": smoke_job_checksum,
            },
        )
        remote = self.transport.run(
            "deploy-tools",
            [commit, dispatcher_checksum, smoke_job_checksum],
        )
        return {
            **remote,
            "operation": "deploy-tools",
            "commit": commit,
            "dispatcher_sha256": dispatcher_checksum,
            "smoke_job_sha256": smoke_job_checksum,
        }

    def stage(
        self,
        profile: str,
        revision: str,
        *,
        parent_run_id: str | None = None,
    ) -> dict[str, object]:
        """Stage one clean immutable commit and create its local capability record."""

        validate_profile(profile)
        if profile == "database":
            raise ValidationError(
                "database administration requires the separate database-stage operation"
            )
        self.git.ensure_clean()
        commit = self.git.resolve_commit(revision)
        iteration, parent = self._next_iteration(parent_run_id)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"gtd-{profile}-{timestamp}-{commit[:12]}-{secrets.token_hex(4)}"
        owner_id = secrets.token_hex(16)
        validate_run_id(run_id)
        lock_checksum = sha256_file(self.config.repository / "pixi.lock")
        self.logger.info(
            "staging immutable HPC run",
            extra={
                "run_id": run_id,
                "commit": commit,
                "profile": profile,
                "iteration": iteration,
            },
        )
        record = LocalRunRecord(
            run_id=run_id,
            commit=commit,
            owner_id=owner_id,
            profile=profile,
            iteration=iteration,
            parent_run_id=parent,
        )
        local_path = record.write(self.config.local_state_root)
        remote = self.transport.run(
            "stage",
            [run_id, commit, lock_checksum, owner_id, str(iteration), profile],
        )
        return {
            **remote,
            "operation": "stage",
            "run_id": run_id,
            "commit": commit,
            "profile": profile,
            "iteration": iteration,
            "local_record": str(local_path),
        }

    def readiness(self, profile: str) -> dict[str, object]:
        """Inspect one fixed profile's remote prerequisites without creating a run."""

        validate_profile(profile)
        if profile != "p0":
            raise ValidationError("readiness inspection is available only for p0")
        self.logger.info(
            "inspecting fixed HPC profile readiness",
            extra={"profile": profile},
        )
        return {
            **self.transport.run("readiness", [profile]),
            "operation": "readiness",
            "profile": profile,
        }

    def database_readiness(self) -> dict[str, object]:
        """Inspect fixed database-administration prerequisites without a run."""

        self.logger.info("inspecting fixed database-administration readiness")
        return {
            **self.transport.run("database-readiness", []),
            "operation": "database-readiness",
            "profile": "database",
        }

    def database_stage(self, revision: str) -> dict[str, object]:
        """Stage one immutable commit through the separately named admin boundary."""

        self.git.ensure_clean()
        commit = self.git.resolve_commit(revision)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"gtd-database-{timestamp}-{commit[:12]}-{secrets.token_hex(4)}"
        owner_id = secrets.token_hex(16)
        validate_run_id(run_id)
        lock_checksum = sha256_file(self.config.repository / "pixi.lock")
        record = LocalRunRecord(
            run_id=run_id,
            commit=commit,
            owner_id=owner_id,
            profile="database",
            iteration=1,
            parent_run_id=None,
        )
        local_path = record.write(self.config.local_state_root)
        self.logger.warning(
            "staging immutable database-administration run",
            extra={"run_id": run_id, "commit": commit},
        )
        remote = self.transport.run(
            "database-stage",
            [run_id, commit, lock_checksum, owner_id],
        )
        return {
            **remote,
            "operation": "database-stage",
            "run_id": run_id,
            "commit": commit,
            "profile": "database",
            "local_record": str(local_path),
        }

    def database_submit(self, run_id: str) -> dict[str, object]:
        """Submit only an owned run staged by the admin-specific operation."""

        record = self._owned_run(run_id)
        if record.profile != "database":
            raise ValidationError("database-submit requires a database run")
        self.logger.warning(
            "submitting fixed database-administration job",
            extra={"run_id": run_id},
        )
        return {
            **self.transport.run("database-submit", [run_id, record.owner_id]),
            "operation": "database-submit",
        }

    def submit(self, profile: str, run_id: str) -> dict[str, object]:
        """Submit one reviewed fixed profile for an owned staged run."""

        validate_profile(profile)
        if profile == "database":
            raise ValidationError(
                "database administration requires the separate "
                "database-submit operation"
            )
        record = self._owned_run(run_id)
        if record.profile != profile:
            raise ValidationError("requested profile does not match the staged run")
        self.logger.info(
            "submitting fixed HPC run",
            extra={"run_id": run_id, "profile": profile},
        )
        return {
            **self.transport.run("submit", [run_id, record.owner_id]),
            "operation": "submit",
        }

    def status(self, run_id: str) -> dict[str, object]:
        """Return scheduler and recorded process state for an owned run."""

        record = self._owned_run(run_id)
        return {
            **self.transport.run("status", [run_id, record.owner_id]),
            "operation": "status",
        }

    def wait(self, run_id: str) -> dict[str, object]:
        """Poll with fixed queue and execution deadlines; never cancel implicitly."""

        record = self._owned_run(run_id)
        execution_timeout = (
            self.config.database_execution_timeout_seconds
            if record.profile == "database"
            else self.config.execution_timeout_seconds
        )
        queued_elapsed = 0
        running_elapsed = 0
        phase = "queue"
        total = self.config.queue_timeout_seconds
        progress_enabled = self.progress
        with tqdm(
            total=total,
            desc=f"Waiting for {run_id}",
            unit="s",
            disable=not progress_enabled,
        ) as progress_bar:
            while True:
                result = self.status(run_id)
                scheduler_state = str(result.get("scheduler_state", "UNKNOWN")).upper()
                if (
                    scheduler_state in _TERMINAL_STATES
                    or result.get("terminal") == "true"
                ):
                    return {**result, "operation": "wait"}
                if scheduler_state not in _QUEUED_STATES and phase == "queue":
                    phase = "execution"
                    total = execution_timeout
                    progress_bar.reset(total=total)
                    progress_bar.set_description(f"Running {run_id}")

                time.sleep(self.config.poll_seconds)
                progress_bar.update(self.config.poll_seconds)
                if phase == "queue":
                    queued_elapsed += self.config.poll_seconds
                    if queued_elapsed >= self.config.queue_timeout_seconds:
                        return {
                            **result,
                            "operation": "wait",
                            "terminal": True,
                            "failure_class": FailureClass.QUEUE_TIMEOUT,
                            "message": (
                                "queue wait limit reached; job was not cancelled"
                            ),
                        }
                else:
                    running_elapsed += self.config.poll_seconds
                    if running_elapsed >= execution_timeout:
                        return {
                            **result,
                            "operation": "wait",
                            "terminal": True,
                            "failure_class": FailureClass.UNKNOWN_FAILURE,
                            "message": (
                                "execution wait limit reached; inspect scheduler state"
                            ),
                        }

    def logs(self, run_id: str, lines: int) -> dict[str, object]:
        """Retrieve a bounded tail through the dispatcher and return UTF-8 text."""

        record = self._owned_run(run_id)
        validate_log_lines(lines)
        result = self.transport.run("logs", [run_id, record.owner_id, str(lines)])
        encoded = result.pop("content_base64", "")
        try:
            content = base64.b64decode(encoded, validate=True).decode(
                "utf-8", errors="replace"
            )
        except ValueError as error:
            raise RemoteOperationError(
                "remote log content was not valid base64",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        return {**result, "operation": "logs", "log": content}

    def collect(self, run_id: str) -> dict[str, object]:
        """Collect and safely extract only the remote dispatcher's whitelist."""

        record = self._owned_run(run_id)
        self.logger.info("collecting HPC run artefacts", extra={"run_id": run_id})
        archive = self.transport.collect(run_id, record.owner_id)
        destination = self.config.local_state_root / run_id / "collected"
        files = _extract_approved_archive(
            archive,
            destination,
            progress=self.progress,
        )
        failure_signature = _failure_signature(destination)
        if failure_signature is not None:
            replace(record, failure_signature=failure_signature).write(
                self.config.local_state_root
            )
        return {
            "operation": "collect",
            "run_id": run_id,
            "destination": str(destination),
            "files": files,
            "failure_signature": failure_signature,
        }

    def cancel(self, run_id: str) -> dict[str, object]:
        """Cancel only the scheduler job bound to an owned local run record."""

        record = self._owned_run(run_id)
        self.logger.warning("cancelling owned HPC run", extra={"run_id": run_id})
        return {
            **self.transport.run("cancel", [run_id, record.owner_id]),
            "operation": "cancel",
        }

    def clean(self, run_id: str, confirmation: str) -> dict[str, object]:
        """Request explicit deletion only when the exact run ID is repeated."""

        record = self._owned_run(run_id)
        if confirmation != run_id:
            raise ValidationError("clean confirmation must exactly equal the run ID")
        return {
            **self.transport.run("clean", [run_id, record.owner_id, confirmation]),
            "operation": "clean",
        }

    def _owned_run(self, run_id: str) -> LocalRunRecord:
        return load_local_run(self.config.local_state_root, validate_run_id(run_id))

    def _next_iteration(self, parent_run_id: str | None) -> tuple[int, str | None]:
        if parent_run_id is None:
            return 1, None
        parent = self._owned_run(parent_run_id)
        iteration = parent.iteration + 1
        if iteration > MAX_FEEDBACK_RUNS:
            raise ValidationError(
                f"feedback loop is limited to {MAX_FEEDBACK_RUNS} smoke runs"
            )
        if parent.failure_signature and parent.parent_run_id:
            grandparent = self._owned_run(parent.parent_run_id)
            if grandparent.failure_signature == parent.failure_signature:
                raise ValidationError(
                    "the same failure signature occurred twice; "
                    "manual diagnosis is required"
                )
        return iteration, parent.run_id


def _decode_remote_fields(payload: bytes) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in payload.splitlines():
        try:
            raw_key, encoded = raw_line.split(b"\t", maxsplit=1)
            key = raw_key.decode("ascii")
            value = base64.b64decode(encoded, validate=True).decode("utf-8")
        except ValueError, UnicodeDecodeError:
            continue
        if key.replace("_", "").isalnum():
            fields[key] = value
    return fields


def _failure_class(value: str | None) -> FailureClass:
    if value is None:
        return FailureClass.TRANSFER_FAILURE
    try:
        return FailureClass(value)
    except ValueError:
        return FailureClass.UNKNOWN_FAILURE


def _extract_approved_archive(
    archive: bytes,
    destination: Path,
    *,
    progress: bool,
) -> list[str]:
    if len(archive) > MAX_ARTIFACT_TOTAL_BYTES:
        raise RemoteOperationError(
            "compressed artefact archive exceeds the local collection limit",
            failure_class=FailureClass.TRANSFER_FAILURE,
        )
    extracted: list[str] = []
    total = 0
    destination.mkdir(parents=True, exist_ok=True)
    destination_resolved = destination.resolve()
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            members = tar.getmembers()
            with tqdm(
                total=len(members),
                desc="Collecting HPC artefacts",
                unit="file",
                disable=not progress,
            ) as progress_bar:
                for member in members:
                    relative = PurePosixPath(member.name)
                    if (
                        not member.isfile()
                        or relative.is_absolute()
                        or ".." in relative.parts
                        or not relative.parts
                    ):
                        raise RemoteOperationError(
                            f"unsafe archive member: {member.name!r}",
                            failure_class=FailureClass.TRANSFER_FAILURE,
                        )
                    if member.size > MAX_ARTIFACT_FILE_BYTES:
                        raise RemoteOperationError(
                            f"artefact exceeds per-file limit: {member.name}",
                            failure_class=FailureClass.TRANSFER_FAILURE,
                        )
                    total += member.size
                    if total > MAX_ARTIFACT_TOTAL_BYTES:
                        raise RemoteOperationError(
                            "artefacts exceed total collection limit",
                            failure_class=FailureClass.TRANSFER_FAILURE,
                        )
                    source = tar.extractfile(member)
                    if source is None:
                        raise RemoteOperationError(
                            f"cannot read archive member: {member.name}",
                            failure_class=FailureClass.TRANSFER_FAILURE,
                        )
                    target = destination.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    resolved_parent = target.parent.resolve()
                    if (
                        resolved_parent != destination_resolved
                        and destination_resolved not in resolved_parent.parents
                    ):
                        raise RemoteOperationError(
                            f"archive target escaped collection root: {member.name!r}",
                            failure_class=FailureClass.TRANSFER_FAILURE,
                        )
                    _atomic_write_bytes(target, source.read())
                    extracted.append(relative.as_posix())
                    progress_bar.update(1)
    except tarfile.TarError as error:
        raise RemoteOperationError(
            "remote artefact archive is invalid",
            failure_class=FailureClass.TRANSFER_FAILURE,
        ) from error
    return sorted(extracted)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _failure_signature(destination: Path) -> str | None:
    result_path = destination / "state" / "job-result.json"
    if not result_path.is_file():
        return None
    try:
        value: object = json.loads(result_path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return None
    if not isinstance(value, Mapping):
        return None
    failure = str(value.get("failure_class", "unknown_failure"))
    if failure == FailureClass.SUCCESS:
        return None
    exit_code = str(value.get("exit_code", "unknown"))
    scheduler_state = str(value.get("scheduler_state", "unknown"))
    return hashlib.sha256(
        f"{failure}\0{exit_code}\0{scheduler_state}".encode()
    ).hexdigest()
