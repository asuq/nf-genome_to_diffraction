"""Validated configuration and run-state types for fixed Marmic test profiles."""

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from genome_to_diffraction.checksums import atomic_write_json

RUN_ID_PATTERN = re.compile(
    r"^gtd-(smoke|p0|database)-[0-9]{8}T[0-9]{6}Z-"
    r"[0-9a-f]{12}-[0-9a-f]{8}$"
)
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
OWNER_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SSH_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
REMOTE_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9._/-]+$")
JOB_ID_PATTERN = re.compile(r"^[0-9]+$")

MAX_LOG_LINES = 2_000
MAX_ARTIFACT_FILE_BYTES = 20 * 1024 * 1024
MAX_ARTIFACT_TOTAL_BYTES = 100 * 1024 * 1024
MAX_FEEDBACK_RUNS = 6
QUEUE_TIMEOUT_SECONDS = 30 * 60
EXECUTION_TIMEOUT_SECONDS = 45 * 60
P0_EXECUTION_TIMEOUT_SECONDS = 24 * 60 * 60
DATABASE_EXECUTION_TIMEOUT_SECONDS = 48 * 60 * 60
POLL_SECONDS = 15
PROFILES = frozenset({"smoke", "p0", "database"})


class FailureClass(StrEnum):
    """Stable failure classifications returned by the HPC interface."""

    SUCCESS = "success"
    SOFTWARE_FAILURE = "software_failure"
    TEST_FAILURE = "test_failure"
    SCHEDULER_REJECTION = "scheduler_rejection"
    QUEUE_TIMEOUT = "queue_timeout"
    NODE_FAILURE = "node_failure"
    ENVIRONMENT_FAILURE = "environment_failure"
    FILESYSTEM_FAILURE = "filesystem_failure"
    TRANSFER_FAILURE = "transfer_failure"
    WRAPPER_FAILURE = "wrapper_failure"
    UNKNOWN_FAILURE = "unknown_failure"


class HpcInterfaceError(Exception):
    """Base class for expected local HPC-interface failures."""

    failure_class = FailureClass.WRAPPER_FAILURE


class ConfigurationError(HpcInterfaceError):
    """The user-owned HPC configuration is absent or unsafe."""


class ValidationError(HpcInterfaceError):
    """An identifier or state transition is not permitted."""


class RemoteOperationError(HpcInterfaceError):
    """The fixed remote dispatcher rejected or failed an operation."""

    def __init__(
        self,
        message: str,
        *,
        failure_class: FailureClass = FailureClass.WRAPPER_FAILURE,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class


@dataclass(frozen=True, slots=True)
class HpcConfig:
    """User-owned configuration for one repository and one HPC endpoint."""

    repository: Path
    ssh_alias: str
    remote_dispatcher: str
    local_state_root: Path
    poll_seconds: int = POLL_SECONDS
    queue_timeout_seconds: int = QUEUE_TIMEOUT_SECONDS
    execution_timeout_seconds: int = EXECUTION_TIMEOUT_SECONDS
    database_execution_timeout_seconds: int = DATABASE_EXECUTION_TIMEOUT_SECONDS

    @classmethod
    def load(cls, path: Path) -> HpcConfig:
        """Load and strictly validate a JSON configuration file."""

        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ConfigurationError(f"HPC configuration not found: {path}") from error
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigurationError(
                f"cannot read HPC configuration {path}: {error}"
            ) from error
        if not isinstance(raw, dict):
            raise ConfigurationError("HPC configuration must be a JSON object")
        allowed = {
            "schema_version",
            "repository",
            "ssh_alias",
            "remote_dispatcher",
            "local_state_root",
            "poll_seconds",
            "queue_timeout_seconds",
            "execution_timeout_seconds",
            "database_execution_timeout_seconds",
        }
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise ConfigurationError(f"unknown HPC configuration keys: {unknown}")
        if raw.get("schema_version") != "1.0":
            raise ConfigurationError("HPC configuration schema_version must be '1.0'")

        repository = _absolute_local_path(raw.get("repository"), "repository")
        if not repository.is_dir() or not (repository / ".git").exists():
            raise ConfigurationError("repository must be an existing Git checkout")
        local_state_root = _absolute_local_path(
            raw.get("local_state_root"), "local_state_root"
        )
        expected_state_root = repository / ".untracked" / "hpc-test"
        if local_state_root != expected_state_root:
            raise ConfigurationError(
                "local_state_root must be <repository>/.untracked/hpc-test"
            )

        ssh_alias = _required_string(raw.get("ssh_alias"), "ssh_alias")
        if SSH_ALIAS_PATTERN.fullmatch(ssh_alias) is None:
            raise ConfigurationError("ssh_alias contains unsafe characters")
        remote_dispatcher = _required_string(
            raw.get("remote_dispatcher"), "remote_dispatcher"
        )
        validate_remote_path(remote_dispatcher, "remote_dispatcher")
        if PurePosixPath(remote_dispatcher).name != "nf-gtd-hpc-remote":
            raise ConfigurationError(
                "remote_dispatcher must name the fixed nf-gtd-hpc-remote executable"
            )

        return cls(
            repository=repository,
            ssh_alias=ssh_alias,
            remote_dispatcher=remote_dispatcher,
            local_state_root=local_state_root,
            poll_seconds=_bounded_integer(raw, "poll_seconds", POLL_SECONDS, 1, 60),
            queue_timeout_seconds=_bounded_integer(
                raw,
                "queue_timeout_seconds",
                QUEUE_TIMEOUT_SECONDS,
                60,
                QUEUE_TIMEOUT_SECONDS,
            ),
            execution_timeout_seconds=_bounded_integer(
                raw,
                "execution_timeout_seconds",
                EXECUTION_TIMEOUT_SECONDS,
                60,
                EXECUTION_TIMEOUT_SECONDS,
            ),
            database_execution_timeout_seconds=_bounded_integer(
                raw,
                "database_execution_timeout_seconds",
                DATABASE_EXECUTION_TIMEOUT_SECONDS,
                60,
                DATABASE_EXECUTION_TIMEOUT_SECONDS,
            ),
        )


@dataclass(frozen=True, slots=True)
class LocalRunRecord:
    """Minimum local capability record for an owned remote run."""

    run_id: str
    commit: str
    owner_id: str
    profile: str
    iteration: int
    parent_run_id: str | None
    failure_signature: str | None = None

    @classmethod
    def from_json(cls, value: object) -> LocalRunRecord:
        """Validate a deserialised local run record."""

        if not isinstance(value, dict):
            raise ValidationError("local run record must be a JSON object")
        run_id = str(value.get("run_id", ""))
        commit = str(value.get("commit", ""))
        owner_id = str(value.get("owner_id", ""))
        profile = str(value.get("profile", ""))
        iteration = value.get("iteration")
        parent = value.get("parent_run_id")
        signature = value.get("failure_signature")
        validate_run_id(run_id)
        validate_commit(commit)
        validate_owner_id(owner_id)
        validate_profile(profile)
        if not run_id.startswith(f"gtd-{profile}-"):
            raise ValidationError("run ID profile does not match the run record")
        if not isinstance(iteration, int) or not 1 <= iteration <= MAX_FEEDBACK_RUNS:
            raise ValidationError("local run iteration is invalid")
        if parent is not None:
            if not isinstance(parent, str):
                raise ValidationError("parent_run_id must be a string or null")
            validate_run_id(parent)
        if signature is not None and not isinstance(signature, str):
            raise ValidationError("failure_signature must be a string or null")
        return cls(
            run_id=run_id,
            commit=commit,
            owner_id=owner_id,
            profile=profile,
            iteration=iteration,
            parent_run_id=parent,
            failure_signature=signature,
        )

    def write(self, root: Path) -> Path:
        """Write this record atomically below the configured local state root."""

        path = root / self.run_id / "run.json"
        atomic_write_json(
            path,
            {
                "schema_version": "1.0",
                "run_id": self.run_id,
                "commit": self.commit,
                "owner_id": self.owner_id,
                "profile": self.profile,
                "iteration": self.iteration,
                "parent_run_id": self.parent_run_id,
                "failure_signature": self.failure_signature,
            },
        )
        return path


def load_local_run(root: Path, run_id: str) -> LocalRunRecord:
    """Load an owned local run capability after validating its identifier."""

    validate_run_id(run_id)
    path = root / run_id / "run.json"
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValidationError(f"local run record not found: {run_id}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(
            f"cannot read local run record {run_id}: {error}"
        ) from error
    return LocalRunRecord.from_json(value)


def validate_run_id(value: str) -> str:
    """Return a run ID only when it matches the generated closed format."""

    if RUN_ID_PATTERN.fullmatch(value) is None:
        raise ValidationError(f"invalid run ID: {value!r}")
    return value


def validate_commit(value: str) -> str:
    """Return a full lowercase Git commit SHA after validation."""

    if COMMIT_PATTERN.fullmatch(value) is None:
        raise ValidationError("commit must be a full lowercase SHA-1")
    return value


def validate_owner_id(value: str) -> str:
    """Return a local ownership identifier after validation."""

    if OWNER_PATTERN.fullmatch(value) is None:
        raise ValidationError("owner ID is invalid")
    return value


def validate_profile(value: str) -> str:
    """Permit only the reviewed fixed execution profiles."""

    if value not in PROFILES:
        raise ValidationError("profile must be one of: p0, smoke")
    return value


def validate_job_id(value: str) -> str:
    """Return a numeric Slurm job identifier after validation."""

    if JOB_ID_PATTERN.fullmatch(value) is None:
        raise ValidationError("Slurm job ID must contain decimal digits only")
    return value


def validate_log_lines(value: int) -> int:
    """Validate a bounded scheduler-log tail length."""

    if not 1 <= value <= MAX_LOG_LINES:
        raise ValidationError(f"log lines must be between 1 and {MAX_LOG_LINES}")
    return value


def validate_remote_path(value: str, name: str) -> str:
    """Reject remote paths that could alter shell parsing or escape absoluteness."""

    if REMOTE_PATH_PATTERN.fullmatch(value) is None or "//" in value:
        raise ConfigurationError(f"{name} must be a conservative absolute POSIX path")
    path = PurePosixPath(value)
    if ".." in path.parts:
        raise ConfigurationError(f"{name} must not contain '..'")
    return value


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{name} must be a non-empty string")
    return value


def _absolute_local_path(value: object, name: str) -> Path:
    raw = _required_string(value, name)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ConfigurationError(f"{name} must be an absolute path")
    return path.resolve()


def _bounded_integer(
    raw: dict[str, Any], name: str, default: int, minimum: int, maximum: int
) -> int:
    value = raw.get(name, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value
