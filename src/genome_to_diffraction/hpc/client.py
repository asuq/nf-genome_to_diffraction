"""Local controller for the fixed Marmic remote test dispatcher."""

import base64
import binascii
import hashlib
import io
import json
import logging
import os
import re
import secrets
import shlex
import shutil
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

from genome_to_diffraction.checksums import atomic_write_text, sha256_file
from genome_to_diffraction.hpc.models import (
    COMMIT_PATTERN,
    MAX_ARTIFACT_FILE_BYTES,
    MAX_ARTIFACT_TOTAL_BYTES,
    MAX_FEEDBACK_RUNS,
    MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES,
    MAX_REVIEW_ARTIFACT_FILE_BYTES,
    MAX_REVIEW_ARTIFACT_TOTAL_BYTES,
    P0_EXECUTION_TIMEOUT_SECONDS,
    P1_EXECUTION_TIMEOUT_SECONDS,
    P2_EXECUTION_TIMEOUT_SECONDS,
    FailureClass,
    HpcConfig,
    LocalRunRecord,
    RemoteOperationError,
    ValidationError,
    load_local_run,
    validate_commit,
    validate_log_lines,
    validate_profile,
    validate_remote_path,
    validate_run_id,
)
from genome_to_diffraction.hpc.p0_inputs import (
    P0_PATHS_FILENAME,
    build_p0_input_bundle,
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
# Marmic login-node commands may block on NFS-cold executables and metadata.
# Keep the transport bounded, but give routine fixed dispatcher operations the
# same conservative margin as immutable source/environment staging.
SSH_OPERATION_TIMEOUT_SECONDS = 45 * 60
P0_STAGE_TIMEOUT_SECONDS = 45 * 60
DATABASE_STAGE_TIMEOUT_SECONDS = 6 * 60 * 60
P0_INPUT_STAGE_TIMEOUT_SECONDS = 15 * 60
SSH_COLLECTION_TIMEOUT_SECONDS = 10 * 60
SSH_REVIEW_COLLECTION_TIMEOUT_SECONDS = 30 * 60
MAX_P0_PATHS_BYTES = 4096
FAILURE_SIGNATURE_LOG_BYTES = 64 * 1024
_FAILURE_APPLICATION_LOGS = frozenset(
    {
        "logs/smoke.log",
        "logs/p0.log",
        "logs/p1.log",
        "logs/p2.log",
        "logs/p2-diverse.log",
        "logs/p2-control.log",
        "logs/database.log",
    }
)
_SIGNATURE_RUN_ID_RE = re.compile(
    r"gtd-(?:smoke|p0|p1|p2-diverse|p2-control|p2|database)-"
    r"[0-9]{8}T[0-9]{6}Z-"
    r"[0-9a-f]{12}-[0-9a-f]{8}"
)
_SIGNATURE_TIMESTAMP_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z"
)
_SIGNATURE_SHA_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{40,64}(?![0-9a-f])")
_SIGNATURE_SLURM_LOG_RE = re.compile(r"slurm-[0-9]+")
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
_REMOTE_SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
_REVIEW_MANIFEST_RELATIVE = PurePosixPath(
    "artifacts/qualification/p2-diverse-review/mr_seed_review_manifest.json"
)
_REVIEW_SUMMARY_RELATIVE = PurePosixPath(
    "artifacts/qualification/p2-diverse-summary.json"
)
_REVIEW_JOB_RESULT_RELATIVE = PurePosixPath("state/job-result.json")
_REVIEW_PACKAGE_ID_RE = re.compile(r"^reviewpkg_[0-9a-f]{64}$")
_REVIEW_SOLUTION_ID_RE = re.compile(r"^sol_[0-9a-f]{64}$")
_REVIEW_ASSET_BASENAMES = {
    "command": "phaser_command.json",
    "normalised_result": "normalised_mr_result.jsonl",
    "output_mtz": "solution.mtz",
    "raw_log": "phaser.log",
    "solution_coordinate": "solution.pdb",
}


def _validated_p0_paths_payload(path: Path) -> bytes:
    """Load one canonical seven-line private P0 path configuration."""

    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_uid != os.getuid()
        or path.stat().st_mode & 0o777 != 0o600
    ):
        raise ValidationError(
            "P0 paths input must be an owned mode-0600 regular non-symlink file"
        )
    payload = path.read_bytes()
    if not payload or len(payload) > MAX_P0_PATHS_BYTES:
        raise ValidationError(
            f"P0 paths input must contain 1..{MAX_P0_PATHS_BYTES} bytes"
        )
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValidationError("P0 paths input must be ASCII") from error
    lines = text.splitlines()
    canonical = "\n".join(lines) + "\n"
    if text != canonical or len(lines) != 7 or any(not line for line in lines):
        raise ValidationError(
            "P0 paths input must be exactly seven non-empty LF-terminated lines"
        )
    for index, value in enumerate(lines, start=1):
        validate_remote_path(value, f"P0 paths line {index}")
    return payload


class TextTransport(Protocol):
    """Transport contract used by the controller and deterministic fakes."""

    def run(self, operation: str, arguments: Sequence[str]) -> dict[str, str]:
        """Run one fixed remote operation and return decoded scalar fields."""

    def collect(self, run_id: str, owner_id: str) -> bytes:
        """Return the fixed whitelisted artefact archive for an owned run."""

    def review_collect(self, run_id: str, owner_id: str, manifest_sha256: str) -> bytes:
        """Return manifest-selected and checksum-gated MR review assets."""

    def p0_inputs_stage(
        self,
        source_id: str,
        archive_sha256: str,
        archive_size_bytes: int,
        database_manifest_sha256: str,
        phenix_manifest_sha256: str,
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream one fixed P0 input archive to the reviewed dispatcher."""


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
        return shlex.join(
            [
                "/usr/bin/env",
                f"PATH={_REMOTE_SYSTEM_PATH}",
                self._config.remote_dispatcher,
                operation,
                *arguments,
            ]
        )

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

        operation_timeout = SSH_OPERATION_TIMEOUT_SECONDS
        if operation == "database-stage":
            operation_timeout = DATABASE_STAGE_TIMEOUT_SECONDS
        elif (
            operation == "stage"
            and len(arguments) == 6
            and arguments[5] in {"p0", "p1", "p2", "p2-diverse", "p2-control"}
        ):
            operation_timeout = P0_STAGE_TIMEOUT_SECONDS
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

    def review_collect(self, run_id: str, owner_id: str, manifest_sha256: str) -> bytes:
        """Stream only assets selected by one immutable MR review manifest."""

        try:
            result = subprocess.run(
                self._command("review-collect", [run_id, owner_id, manifest_sha256]),
                check=False,
                capture_output=True,
                timeout=SSH_REVIEW_COLLECTION_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote review-asset collection exceeded the fixed "
                f"{SSH_REVIEW_COLLECTION_TIMEOUT_SECONDS}-second transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        if result.returncode != 0:
            fields = _decode_remote_fields(result.stdout)
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
            )
            raise RemoteOperationError(
                message or "remote review-asset collection failed",
                failure_class=_failure_class(fields.get("failure_class")),
            )
        return result.stdout

    def p0_inputs_stage(
        self,
        source_id: str,
        archive_sha256: str,
        archive_size_bytes: int,
        database_manifest_sha256: str,
        phenix_manifest_sha256: str,
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream the fixed archive on stdin without raw transfer authority."""

        arguments = [
            source_id,
            archive_sha256,
            str(archive_size_bytes),
            database_manifest_sha256,
            phenix_manifest_sha256,
        ]
        try:
            with archive_path.open("rb") as handle:
                result = subprocess.run(
                    self._command("p0-inputs-stage", arguments),
                    stdin=handle,
                    check=False,
                    capture_output=True,
                    timeout=P0_INPUT_STAGE_TIMEOUT_SECONDS,
                )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote P0 input staging exceeded the fixed "
                f"{P0_INPUT_STAGE_TIMEOUT_SECONDS}-second transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        fields = _decode_remote_fields(result.stdout)
        if result.returncode != 0:
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
                or "remote P0 input staging failed"
            )
            raise RemoteOperationError(
                message,
                failure_class=_failure_class(fields.get("failure_class")),
            )
        if not fields:
            raise RemoteOperationError(
                "remote P0 input staging returned no structured fields",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        return fields


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
        if profile not in {"p0", "p1", "p2", "p2-diverse", "p2-control"}:
            raise ValidationError(
                "readiness inspection is available only for p0, p1, p2, "
                "p2-diverse, and p2-control"
            )
        self.logger.info(
            "inspecting fixed HPC profile readiness",
            extra={"profile": profile},
        )
        return {
            **self.transport.run("readiness", [profile]),
            "operation": "readiness",
            "profile": profile,
        }

    def p0_configure(self, paths_file: Path, confirmation: str) -> dict[str, object]:
        """Install one absent, validated seven-line P0 site configuration."""

        payload = _validated_p0_paths_payload(paths_file)
        checksum = hashlib.sha256(payload).hexdigest()
        if confirmation != checksum:
            raise ValidationError(
                "P0 configuration confirmation must exactly equal its SHA-256"
            )
        encoded = base64.b64encode(payload).decode("ascii")
        self.logger.warning(
            "installing validated fixed P0 site configuration",
            extra={"p0_config_sha256": checksum},
        )
        return {
            **self.transport.run("p0-configure", [checksum, encoded]),
            "operation": "p0-configure",
            "p0_config_sha256": checksum,
        }

    def p0_inputs_stage(self, spec_confirmation: str) -> dict[str, object]:
        """Stage the fixed frozen pilot bundle and write its private path candidate."""

        self.git.ensure_clean()
        remote_root = PurePosixPath(self.config.remote_dispatcher).parent.parent
        qualification_root = self.config.repository / ".untracked" / "m0-qualification"
        paths_output = qualification_root / P0_PATHS_FILENAME
        with tempfile.TemporaryDirectory(prefix="nf-gtd-p0-inputs-") as temporary:
            archive_path = Path(temporary) / "p0-inputs.tar.gz"
            bundle = build_p0_input_bundle(
                repository=self.config.repository,
                remote_root=remote_root,
                spec_confirmation=spec_confirmation,
                archive_path=archive_path,
                progress=self.progress,
                logger=self.logger,
            )
            self.logger.warning(
                "staging checksum-verified fixed P0 inputs",
                extra={
                    "source_id": f"p0i_{bundle.source_id}",
                    "archive_sha256": bundle.archive_sha256,
                    "archive_size_bytes": bundle.archive_size_bytes,
                    "scientific_input_count": bundle.scientific_input_count,
                },
            )
            remote = self.transport.p0_inputs_stage(
                bundle.source_id,
                bundle.archive_sha256,
                bundle.archive_size_bytes,
                bundle.database_manifest_sha256,
                bundle.phenix_manifest_sha256,
                bundle.archive_path,
            )

        expected_id = f"p0i_{bundle.source_id}"
        if (
            remote.get("p0_input_id") != expected_id
            or remote.get("archive_sha256") != bundle.archive_sha256
        ):
            raise RemoteOperationError(
                "remote P0 input identity differs from the reviewed local archive",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        encoded_paths = remote.pop("p0_paths_base64", None)
        if encoded_paths is None:
            raise RemoteOperationError(
                "remote P0 input staging returned no configuration candidate",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        try:
            paths_payload = base64.b64decode(encoded_paths, validate=True)
        except (ValueError, binascii.Error) as error:
            raise RemoteOperationError(
                "remote P0 configuration candidate is not valid base64",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        candidate_checksum = hashlib.sha256(paths_payload).hexdigest()
        if remote.get("p0_config_sha256") != candidate_checksum:
            raise RemoteOperationError(
                "remote P0 configuration candidate checksum differs",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        with tempfile.NamedTemporaryFile(
            prefix="nf-gtd-p0-paths-", dir="/tmp", delete=False
        ) as handle:
            temporary_paths = Path(handle.name)
            handle.write(paths_payload)
        try:
            _validated_p0_paths_payload(temporary_paths)
        finally:
            temporary_paths.unlink(missing_ok=True)
        if paths_output.exists() or paths_output.is_symlink():
            if (
                paths_output.is_symlink()
                or not paths_output.is_file()
                or paths_output.stat().st_uid != os.getuid()
                or paths_output.stat().st_mode & 0o777 != 0o600
                or paths_output.read_bytes() != paths_payload
            ):
                raise ValidationError(
                    "private P0 paths candidate already exists with unsafe identity"
                )
        else:
            atomic_write_text(
                paths_output, paths_payload.decode("ascii"), encoding="ascii"
            )
            paths_output.chmod(0o600)
        return {
            **remote,
            "operation": "p0-inputs-stage",
            "p0_input_id": expected_id,
            "archive_sha256": bundle.archive_sha256,
            "archive_size_bytes": bundle.archive_size_bytes,
            "scientific_input_count": bundle.scientific_input_count,
            "p0_config_sha256": candidate_checksum,
            "local_paths_file": str(paths_output),
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

    def database_archive_failed(
        self, run_id: str, confirmation: str
    ) -> dict[str, object]:
        """Archive retained staging cited by one collected terminal database run."""

        record = self._owned_run(run_id)
        if record.profile != "database":
            raise ValidationError("database-archive-failed requires a database run")
        collected_manifest = (
            self.config.local_state_root / run_id / "collected" / "manifest.json"
        )
        if record.failure_signature is None and (
            collected_manifest.is_symlink() or not collected_manifest.is_file()
        ):
            raise ValidationError(
                "collect the terminal database run before archiving its staging"
            )
        if confirmation != run_id:
            raise ValidationError(
                "database archive confirmation must exactly equal the run ID"
            )
        self.logger.warning(
            "archiving reviewed retained database staging",
            extra={"run_id": run_id, "failure_signature": record.failure_signature},
        )
        return {
            **self.transport.run(
                "database-archive-failed",
                [run_id, record.owner_id, confirmation],
            ),
            "operation": "database-archive-failed",
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
            else (
                P0_EXECUTION_TIMEOUT_SECONDS
                if record.profile == "p0"
                else (
                    P1_EXECUTION_TIMEOUT_SECONDS
                    if record.profile == "p1"
                    else (
                        P2_EXECUTION_TIMEOUT_SECONDS
                        if record.profile in {"p2", "p2-diverse", "p2-control"}
                        else self.config.execution_timeout_seconds
                    )
                )
            )
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

    def review_collect(self, run_id: str) -> dict[str, object]:
        """Collect only checksum-bound assets for automatically eligible MR seeds."""

        record = self._owned_run(run_id)
        if record.profile != "p2-diverse":
            raise ValidationError("review-collect requires a p2-diverse run")
        collected = self.config.local_state_root / run_id / "collected"
        expectations, package_id, solution_ids, manifest_sha256 = (
            _review_asset_expectations(collected, record)
        )
        self.logger.info(
            "collecting checksum-gated MR review assets",
            extra={
                "run_id": run_id,
                "package_id": package_id,
                "eligible_solution_count": len(solution_ids),
                "manifest_sha256": manifest_sha256,
            },
        )
        archive = self.transport.review_collect(
            run_id, record.owner_id, manifest_sha256
        )
        destination = self.config.local_state_root / run_id / "review-assets"
        files = _extract_verified_review_archive(
            archive,
            destination,
            expectations,
            progress=self.progress,
        )
        return {
            "operation": "review-collect",
            "run_id": run_id,
            "destination": str(destination),
            "package_id": package_id,
            "manifest_sha256": manifest_sha256,
            "eligible_solution_count": len(solution_ids),
            "solution_ids": solution_ids,
            "files": files,
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


def _safe_local_evidence_file(root: Path, relative: PurePosixPath) -> Path:
    """Resolve one required collected evidence file without following symlinks."""

    if relative.is_absolute() or ".." in relative.parts:
        raise ValidationError("review evidence path is unsafe")
    path = root.joinpath(*relative.parts)
    root_resolved = root.resolve()
    if path.is_symlink() or not path.is_file():
        raise ValidationError(
            f"collect the terminal run before review assets: {relative.as_posix()}"
        )
    parent = path.parent.resolve()
    if parent != root_resolved and root_resolved not in parent.parents:
        raise ValidationError("collected review evidence escaped its run root")
    return path


def _json_mapping(path: Path, label: str) -> Mapping[str, object]:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"{label} is not valid JSON") from error
    if not isinstance(value, Mapping):
        raise ValidationError(f"{label} must be a JSON object")
    return value


def _review_asset_expectations(
    collected: Path,
    record: LocalRunRecord,
) -> tuple[dict[str, str], str, list[str], str]:
    """Validate compact evidence and derive the only permitted review assets."""

    manifest_path = _safe_local_evidence_file(collected, _REVIEW_MANIFEST_RELATIVE)
    summary_path = _safe_local_evidence_file(collected, _REVIEW_SUMMARY_RELATIVE)
    job_result_path = _safe_local_evidence_file(collected, _REVIEW_JOB_RESULT_RELATIVE)
    manifest_sha256 = sha256_file(manifest_path)
    manifest = _json_mapping(manifest_path, "MR review manifest")
    summary = _json_mapping(summary_path, "P2-diverse summary")
    job_result = _json_mapping(job_result_path, "HPC job result")

    if (
        job_result.get("run_id") != record.run_id
        or job_result.get("profile") != "p2-diverse"
        or job_result.get("failure_class") != FailureClass.SUCCESS
        or job_result.get("scheduler_state") != "COMPLETED"
        or job_result.get("exit_code") != 0
    ):
        raise ValidationError("review assets require a collected successful P2 run")
    package_id = manifest.get("package_id")
    if (
        not isinstance(package_id, str)
        or _REVIEW_PACKAGE_ID_RE.fullmatch(package_id) is None
    ):
        raise ValidationError("MR review package ID is invalid")
    expected_gate = {
        "llg_strictly_greater_than": 50.0,
        "operator": "or",
        "policy_id": "strict_llg_gt_50_or_tfz_gt_5",
        "tfz_strictly_greater_than": 5.0,
    }
    if (
        manifest.get("adapter_version") != "mr-seed-review-v2"
        or manifest.get("score_gate") != expected_gate
        or summary.get("run_id") != record.run_id
        or summary.get("profile") != "p2-diverse"
        or summary.get("mr_seed_review_package_id") != package_id
        or summary.get("mr_seed_review_manifest_sha256") != manifest_sha256
    ):
        raise ValidationError("MR review evidence identity or policy does not match")

    items = manifest.get("items")
    if not isinstance(items, list):
        raise ValidationError("MR review manifest items must be an array")
    eligible = [
        item
        for item in items
        if isinstance(item, Mapping) and item.get("automatic_eligibility") is True
    ]
    if not 1 <= len(eligible) <= 25:
        raise ValidationError("MR review package must have 1..25 eligible seeds")
    if summary.get("completed_hit_count") != len(eligible):
        raise ValidationError("eligible review count differs from the run summary")

    expectations = {
        _REVIEW_MANIFEST_RELATIVE.as_posix(): manifest_sha256,
        _REVIEW_SUMMARY_RELATIVE.as_posix(): sha256_file(summary_path),
        _REVIEW_JOB_RESULT_RELATIVE.as_posix(): sha256_file(job_result_path),
    }
    solution_ids: list[str] = []
    for item in eligible:
        solution_id = item.get("solution_id")
        copied_assets = item.get("copied_assets")
        copied_sha256 = item.get("copied_asset_sha256")
        if (
            not isinstance(solution_id, str)
            or _REVIEW_SOLUTION_ID_RE.fullmatch(solution_id) is None
            or solution_id in solution_ids
            or not isinstance(copied_assets, Mapping)
            or not isinstance(copied_sha256, Mapping)
        ):
            raise ValidationError("eligible MR review item identity is invalid")
        if set(copied_assets) != set(_REVIEW_ASSET_BASENAMES) or set(
            copied_sha256
        ) != set(_REVIEW_ASSET_BASENAMES):
            raise ValidationError("eligible MR review asset set is incomplete")
        solution_ids.append(solution_id)
        for key, basename in _REVIEW_ASSET_BASENAMES.items():
            expected_local = f"assets/{solution_id}/{basename}"
            digest = copied_sha256.get(key)
            if (
                copied_assets.get(key) != expected_local
                or not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            ):
                raise ValidationError("eligible MR review asset identity is invalid")
            archive_relative = (
                _REVIEW_MANIFEST_RELATIVE.parent / expected_local
            ).as_posix()
            if archive_relative in expectations:
                raise ValidationError("eligible MR review asset path is duplicated")
            expectations[archive_relative] = digest
    return expectations, package_id, solution_ids, manifest_sha256


def _extract_verified_review_archive(
    archive: bytes,
    destination: Path,
    expectations: Mapping[str, str],
    *,
    progress: bool,
) -> list[str]:
    """Extract an exact manifest-derived archive after hashing every member."""

    if len(archive) > MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES:
        raise RemoteOperationError(
            "compressed review archive exceeds the local collection limit",
            failure_class=FailureClass.TRANSFER_FAILURE,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    published = False
    extracted: dict[str, str] = {}
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            members = tar.getmembers()
            with tqdm(
                total=len(members),
                desc="Collecting MR review assets",
                unit="file",
                disable=not progress,
            ) as progress_bar:
                for member in members:
                    relative = PurePosixPath(member.name)
                    name = relative.as_posix()
                    if (
                        not member.isfile()
                        or relative.is_absolute()
                        or ".." in relative.parts
                        or name not in expectations
                        or name in extracted
                    ):
                        raise RemoteOperationError(
                            f"unexpected review archive member: {member.name!r}",
                            failure_class=FailureClass.TRANSFER_FAILURE,
                        )
                    if member.size > MAX_REVIEW_ARTIFACT_FILE_BYTES:
                        raise RemoteOperationError(
                            f"review asset exceeds per-file limit: {name}",
                            failure_class=FailureClass.TRANSFER_FAILURE,
                        )
                    total += member.size
                    if total > MAX_REVIEW_ARTIFACT_TOTAL_BYTES:
                        raise RemoteOperationError(
                            "review assets exceed total collection limit",
                            failure_class=FailureClass.TRANSFER_FAILURE,
                        )
                    source = tar.extractfile(member)
                    if source is None:
                        raise RemoteOperationError(
                            f"cannot read review archive member: {name}",
                            failure_class=FailureClass.TRANSFER_FAILURE,
                        )
                    payload = source.read()
                    digest = hashlib.sha256(payload).hexdigest()
                    if digest != expectations[name]:
                        raise RemoteOperationError(
                            f"review asset checksum mismatch: {name}",
                            failure_class=FailureClass.TRANSFER_FAILURE,
                        )
                    _atomic_write_bytes(
                        temporary_root.joinpath(*relative.parts), payload
                    )
                    extracted[name] = digest
                    progress_bar.update(1)
        missing = sorted(set(expectations) - set(extracted))
        if missing:
            raise RemoteOperationError(
                f"review archive omitted expected assets: {missing}",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        for name in extracted:
            if name.endswith("/normalised_mr_result.jsonl"):
                _validate_eligible_review_result(temporary_root / name, name)
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_dir():
                raise RemoteOperationError(
                    "review-asset destination has unsafe identity",
                    failure_class=FailureClass.TRANSFER_FAILURE,
                )
            existing = {
                path.relative_to(destination).as_posix(): sha256_file(path)
                for path in destination.rglob("*")
                if path.is_file() and not path.is_symlink()
            }
            if existing != extracted:
                raise RemoteOperationError(
                    "existing review assets differ from the immutable package",
                    failure_class=FailureClass.TRANSFER_FAILURE,
                )
        else:
            os.replace(temporary_root, destination)
            published = True
    except (tarfile.TarError, OSError) as error:
        raise RemoteOperationError(
            "remote review archive is invalid",
            failure_class=FailureClass.TRANSFER_FAILURE,
        ) from error
    finally:
        if not published:
            shutil.rmtree(temporary_root, ignore_errors=True)
    return sorted(extracted)


def _validate_eligible_review_result(path: Path, label: str) -> None:
    """Recompute fixed first-copy eligibility from one normalised result."""

    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise RemoteOperationError(
            f"eligible review result must contain one record: {label}",
            failure_class=FailureClass.TRANSFER_FAILURE,
        )
    try:
        result: object = json.loads(lines[0])
    except json.JSONDecodeError as error:
        raise RemoteOperationError(
            f"eligible review result is invalid JSON: {label}",
            failure_class=FailureClass.TRANSFER_FAILURE,
        ) from error
    if not isinstance(result, Mapping):
        raise RemoteOperationError(
            f"eligible review result is not an object: {label}",
            failure_class=FailureClass.TRANSFER_FAILURE,
        )
    llg = result.get("llg")
    tfz = result.get("tfz")
    score_passed = (
        isinstance(llg, int | float) and not isinstance(llg, bool) and llg > 50.0
    ) or (isinstance(tfz, int | float) and not isinstance(tfz, bool) and tfz > 5.0)
    packing = result.get("packing_summary")
    if not (
        result.get("execution_status") == "completed_hit"
        and score_passed
        and isinstance(packing, Mapping)
        and packing.get("top_solution_packed") is True
        and packing.get("score_gate_operator") == "or"
        and packing.get("score_gate_llg_strictly_greater_than") == 50
        and packing.get("score_gate_tfz_strictly_greater_than") == 5
        and packing.get("score_gate_passed") is True
        and result.get("placed_copy_count") == 1
        and isinstance(result.get("solution_coordinate_path"), str)
        and isinstance(result.get("output_mtz_path"), str)
    ):
        raise RemoteOperationError(
            f"eligible review result fails the fixed first-copy gate: {label}",
            failure_class=FailureClass.TRANSFER_FAILURE,
        )


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
    diagnostic = _failure_log_digest(destination, value)
    return hashlib.sha256(
        f"{failure}\0{exit_code}\0{scheduler_state}\0{diagnostic}".encode()
    ).hexdigest()


def _failure_log_digest(destination: Path, result: Mapping[object, object]) -> str:
    relative_value = result.get("application_log")
    if not isinstance(relative_value, str) or relative_value not in (
        _FAILURE_APPLICATION_LOGS
    ):
        return "no-approved-application-log"
    relative = PurePosixPath(relative_value)
    path = destination.joinpath(*relative.parts)
    try:
        if path.is_symlink() or not path.is_file():
            return "no-approved-application-log"
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - FAILURE_SIGNATURE_LOG_BYTES))
            payload = handle.read(FAILURE_SIGNATURE_LOG_BYTES)
    except OSError:
        return "no-approved-application-log"
    text = payload.decode("utf-8", errors="replace")
    text = _SIGNATURE_RUN_ID_RE.sub("<run-id>", text)
    text = _SIGNATURE_TIMESTAMP_RE.sub("<timestamp>", text)
    text = _SIGNATURE_SHA_RE.sub("<sha>", text)
    text = _SIGNATURE_SLURM_LOG_RE.sub("slurm-<job-id>", text)
    stable_lines = [
        line
        for line in text.splitlines()
        if not line.startswith(("job_id=", "compute_host="))
    ]
    normalised = "\n".join(stable_lines).encode("utf-8")
    return hashlib.sha256(normalised).hexdigest()
