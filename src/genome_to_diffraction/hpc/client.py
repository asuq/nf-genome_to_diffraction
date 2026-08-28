"""Local controller for the fixed site-isolated remote test dispatcher."""

import base64
import binascii
import hashlib
import io
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

from genome_to_diffraction.benchmarks.m6_runner import (
    verify_m6_runner_truth_isolation,
)
from genome_to_diffraction.benchmarks.m6_verification import (
    M6RunnerInventorySpec,
    M6RunnerVerificationRequest,
    verify_m6_runner_bundle,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import atomic_write_text, sha256_file
from genome_to_diffraction.hpc.control_matrix import build_fixed_control_matrix_bundle
from genome_to_diffraction.hpc.control_slice import build_fixed_control_slice_bundle
from genome_to_diffraction.hpc.m4_import import build_fixed_m4_import_bundle
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
    validate_site_id,
)
from genome_to_diffraction.hpc.p0_inputs import (
    P0_PATHS_FILENAME,
    build_p0_input_bundle,
)
from genome_to_diffraction.hpc.unknown_inputs import (
    build_unknown_discovery_input_bundle,
)
from genome_to_diffraction.hpc.unknown_single_inputs import (
    build_unknown_single_component_input_bundle,
)
from genome_to_diffraction.review import (
    SequenceCheckpointRequest,
    build_sequence_checkpoint,
)
from genome_to_diffraction.schemas.io import (
    ContractLoadError,
    load_json_document,
    parse_json_document,
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
_RUNNING_STATES = frozenset(
    {"COMPLETING", "RESIZING", "RUNNING", "STOPPED", "SUSPENDED"}
)
_RUN_SCOPED_REMOTE_OPERATIONS = frozenset(
    {
        "cancel",
        "clean",
        "database-archive-failed",
        "database-stage",
        "database-submit",
        "logs",
        "m4-copy-stage",
        "stage",
        "status",
        "submit",
    }
)
_SITE_REQUIRED_REMOTE_OPERATIONS = frozenset({"logs", "status"})
_REMOTE_TOOL_PATHS = (
    PurePosixPath("bootstrap/nf-gtd-hpc-remote"),
    PurePosixPath("bootstrap/nf-gtd-hpc-smoke-job"),
    PurePosixPath("bootstrap/nf-gtd-hpc-recover-tools"),
)
SSH_CONNECT_TIMEOUT_SECONDS = 15
# Marmic login-node commands may block on NFS-cold executables and metadata.
# Keep the transport bounded, but give routine fixed dispatcher operations the
# same conservative margin as immutable source/environment staging.
SSH_OPERATION_TIMEOUT_SECONDS = 45 * 60
P0_STAGE_TIMEOUT_SECONDS = 45 * 60
DATABASE_STAGE_TIMEOUT_SECONDS = 6 * 60 * 60
P0_INPUT_STAGE_TIMEOUT_SECONDS = 15 * 60
UNKNOWN_PROVIDER_STAGE_TIMEOUT_SECONDS = 60 * 60
SSH_COLLECTION_TIMEOUT_SECONDS = 10 * 60
SSH_REVIEW_COLLECTION_TIMEOUT_SECONDS = 30 * 60
MAX_LOG_BYTES = 2 * 1024 * 1024
MAX_P0_PATHS_BYTES = 4096
MAX_SOURCE_ARCHIVE_BYTES = 64 * 1024 * 1024
FAILURE_SIGNATURE_LOG_BYTES = 64 * 1024
MAX_M6_RUNNER_ARCHIVE_BYTES = 256 * 1024 * 1024
_FAILURE_APPLICATION_LOGS = frozenset(
    {
        "logs/smoke.log",
        "logs/p0.log",
        "logs/p1.log",
        "logs/p2.log",
        "logs/p2-diverse.log",
        "logs/p2-control.log",
        "logs/heteromer-smoke.log",
        "logs/phase3-phenix-probe.log",
        "logs/phase3-network-probe.log",
        "logs/unknown-discovery.log",
        "logs/unknown-screen.log",
        "logs/unknown-single-component.log",
        "logs/control-slice.log",
        "logs/control-matrix.log",
        "logs/m6-inputs.log",
        "logs/m6-nextflow-smoke.log",
        "logs/m6-operational.log",
        "logs/m6-leakage.log",
        "logs/m4-copy.log",
        "logs/t12.log",
        "logs/database.log",
    }
)
_SIGNATURE_RUN_ID_RE = re.compile(
    r"gtd-(?:smoke|p0|p1|p2-diverse|p2-control|p2|heteromer-smoke|phase3-phenix-probe|phase3-network-probe|unknown-discovery|unknown-screen|unknown-single-component|control-slice|control-matrix|m6-inputs|m6-nextflow-smoke|m6-operational|m6-leakage|m4-copy|t12|database)-"
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
_REVIEW_OUTPUT_BASENAMES = {
    "approval_candidates_tsv": "mr_seed_approval_candidates.tsv",
    "approval_template_tsv": "approved_mr_seeds.tsv",
    "review_html": "mr_seed_candidates.html",
    "review_tsv": "mr_seed_candidates.tsv",
}
_T12_SUMMARY_RELATIVE = PurePosixPath("artifacts/qualification/t12-summary.json")
_T12_REFINEMENT_RELATIVE = PurePosixPath(
    "artifacts/qualification/t12-refinement-results.jsonl"
)
_T12_SEQUENCE_RELATIVE = PurePosixPath(
    "artifacts/qualification/t12-sequence-results.jsonl"
)
_T12_STAGE_MANIFEST_RELATIVE = PurePosixPath(
    "artifacts/t12-inputs/t12_stage_manifest.json"
)
_T12_SEQUENCE_GROUPS_RELATIVE = PurePosixPath(
    "artifacts/t12-inputs/inputs/sequence_groups.jsonl"
)
_T12_SOURCE_RECORDS_RELATIVE = PurePosixPath(
    "artifacts/t12-inputs/inputs/source_records.jsonl"
)
_T12_PREFLIGHT_RELATIVE = PurePosixPath("artifacts/t12-inputs/inputs/preflight.jsonl")
_T12_ASSET_BASENAMES = (
    "brief_refine_001.pdb",
    "brief_refine_001.mtz",
    "brief_refine_2mFo-DFc.ccp4",
    "brief_refine_mFo-DFc.ccp4",
    "sequence_from_map.pdb",
)
_P0_QUALIFICATION_RELATIVE = Path(".untracked/m0-qualification")
_P0_INPUT_SPEC_NAME = "p0-inputs.json"


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


def _validated_database_runtime_paths_payload(path: Path) -> bytes:
    """Load one canonical seven-line private database runtime configuration."""

    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_uid != os.getuid()
        or path.stat().st_mode & 0o777 != 0o600
    ):
        raise ValidationError(
            "database runtime paths must be an owned mode-0600 regular file"
        )
    payload = path.read_bytes()
    if not payload or len(payload) > MAX_P0_PATHS_BYTES:
        raise ValidationError(
            f"database runtime paths must contain 1..{MAX_P0_PATHS_BYTES} bytes"
        )
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValidationError("database runtime paths must be ASCII") from error
    lines = text.splitlines()
    canonical = "\n".join(lines) + "\n"
    if text != canonical or len(lines) != 7 or any(not line for line in lines):
        raise ValidationError(
            "database runtime paths must be exactly seven non-empty LF-terminated lines"
        )
    for index, value in enumerate(lines[:3], start=1):
        validate_remote_path(value, f"database runtime paths line {index}")
    if any(
        re.fullmatch(r"(?:0|[1-9][0-9]*)", value) is None or len(value) > 13
        for value in lines[3:]
    ):
        raise ValidationError("database runtime capacities must be canonical integers")
    storage, reserve, required, scratch = (int(value) for value in lines[3:])
    if not (
        0 < storage <= 2_000_000_000_000
        and 0 <= reserve < storage
        and 0 < required <= storage
        and scratch > 0
    ):
        raise ValidationError("database runtime capacities are out of bounds")
    return payload


def _fixed_heteromer_phenix_binding(repository: Path) -> tuple[str, str]:
    """Return the preserved Marmic Phenix path and independently frozen digest."""

    qualification = repository / _P0_QUALIFICATION_RELATIVE
    paths = qualification / P0_PATHS_FILENAME
    lines = _validated_p0_paths_payload(paths).decode("ascii").splitlines()
    phenix_manifest = lines[6]
    validate_remote_path(phenix_manifest, "fixed heteromer Phenix manifest")
    spec_path = qualification / _P0_INPUT_SPEC_NAME
    try:
        spec = load_json_document(spec_path)
    except (OSError, ContractLoadError) as error:
        raise ValidationError(
            f"cannot read fixed P0 identity specification: {spec_path}"
        ) from error
    if not isinstance(spec, dict):
        raise ValidationError("fixed P0 identity specification must be an object")
    digest = spec.get("phenix_manifest_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
        raise ValidationError("fixed heteromer Phenix checksum is invalid")
    return phenix_manifest, digest


def _inspect_m6_runner_archive(
    archive: Path,
    *,
    protocol: Path,
    expected_sha256: str,
) -> tuple[Path, str, int, str, int, int]:
    """Validate one explicitly confirmed M6 archive before remote transfer."""

    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ValidationError("confirmed M6 archive SHA-256 is invalid")
    if archive.is_symlink():
        raise ValidationError("M6 runner archive must not be a symlink")
    try:
        resolved = archive.resolve(strict=True)
    except OSError as error:
        raise ValidationError(f"M6 runner archive is missing: {archive}") from error
    if not resolved.is_file():
        raise ValidationError("M6 runner archive must be a regular file")
    size = resolved.stat().st_size
    if not 1 <= size <= MAX_M6_RUNNER_ARCHIVE_BYTES:
        raise ValidationError("M6 runner archive is outside the reviewed size bound")
    actual_sha256 = sha256_file(resolved)
    if actual_sha256 != expected_sha256:
        raise ValidationError("M6 runner archive differs from the confirmed SHA-256")

    with tempfile.TemporaryDirectory(prefix="nf-gtd-m6-inspect-", dir="/tmp") as temp:
        root = Path(temp) / "runner"
        root.mkdir()
        try:
            with tarfile.open(resolved, mode="r:") as handle:
                members = handle.getmembers()
                names: list[str] = []
                total_size = 0
                for member in members:
                    relative = PurePosixPath(member.name)
                    if (
                        relative.is_absolute()
                        or not relative.parts
                        or ".." in relative.parts
                        or not member.isfile()
                    ):
                        raise ValidationError("M6 runner archive has an unsafe member")
                    names.append(relative.as_posix())
                    total_size += member.size
                if len(names) != len(set(names)):
                    raise ValidationError("M6 runner archive has duplicate members")
                if total_size > MAX_M6_RUNNER_ARCHIVE_BYTES:
                    raise ValidationError("M6 runner extraction exceeds its size bound")
                manifest_member = handle.getmember("runner_manifest.json")
                manifest_handle = handle.extractfile(manifest_member)
                if manifest_handle is None:
                    raise ValidationError("M6 runner manifest cannot be read")
                manifest_bytes = manifest_handle.read()
                manifest = M6RunnerInventorySpec.model_validate_json(manifest_bytes)
                expected_names = {
                    "runner_manifest.json",
                    *(f"objects/{digest}" for digest in manifest.objects),
                }
                if set(names) != expected_names:
                    raise ValidationError("M6 runner archive inventory differs")
                handle.extractall(root, members=members, filter="data")
        except (KeyError, tarfile.TarError, ValueError) as error:
            raise ValidationError(f"invalid M6 runner archive: {error}") from error

        try:
            verify_m6_runner_truth_isolation(protocol, root)
            qualification = verify_m6_runner_bundle(
                M6RunnerVerificationRequest(
                    runner_root=root,
                    output=Path(temp) / "qualification.json",
                )
            )
        except PublicControlError as error:
            raise ValidationError(f"M6 runner qualification failed: {error}") from error
        manifest_sha256 = qualification.runner_manifest_sha256
        case_count = qualification.case_count
        object_count = qualification.object_count
    return (
        resolved,
        actual_sha256,
        size,
        manifest_sha256,
        case_count,
        object_count,
    )


_M6_OPERATIONAL_PRECHECK_PATHS = (
    "manifest.json",
    "state/job-result.json",
    "artifacts/qualification/m6-scientific-summary.json",
    "artifacts/qualification/m6-scientific-checksums.sha256",
)


def _m6_operational_precheck(
    collected: Path,
    record: LocalRunRecord,
) -> str:
    """Authenticate one collected successful operational track before leakage."""

    if collected.is_symlink() or not collected.is_dir():
        raise ValidationError("M6 leakage requires its collected operational parent")
    paths: list[tuple[str, Path]] = []
    for relative in _M6_OPERATIONAL_PRECHECK_PATHS:
        path = collected.joinpath(*PurePosixPath(relative).parts)
        if path.is_symlink() or not path.is_file():
            raise ValidationError(
                f"M6 operational precheck is missing {relative}"
            )
        paths.append((relative, path))
    manifest = load_json_document(paths[0][1])
    result = load_json_document(paths[1][1])
    summary = load_json_document(paths[2][1])
    if (
        not isinstance(manifest, dict)
        or not isinstance(result, dict)
        or not isinstance(summary, dict)
        or manifest.get("run_id") != record.run_id
        or manifest.get("profile") != "m6-operational"
        or manifest.get("commit") != record.commit
        or manifest.get("site_id") != record.site_id
        or result.get("run_id") != record.run_id
        or result.get("profile") != "m6-operational"
        or result.get("scheduler_state") != "COMPLETED"
        or result.get("failure_class") != "success"
        or result.get("exit_code") != 0
        or summary.get("track") != "operational"
        or summary.get("schema_version") != "2.0"
        or summary.get("adapter_version") != "m6-nextflow-run-v2"
    ):
        raise ValidationError(
            "M6 operational parent is not a collected successful exact track"
        )
    inventory = "".join(
        f"{sha256_file(path)}  {relative}\n" for relative, path in paths
    )
    return hashlib.sha256(inventory.encode("ascii")).hexdigest()


class TextTransport(Protocol):
    """Transport contract used by the controller and deterministic fakes."""

    def run(self, operation: str, arguments: Sequence[str]) -> dict[str, str]:
        """Run one fixed remote operation and return decoded scalar fields."""

    def recover_tools(
        self,
        recovery_script: bytes,
        dispatcher_script: bytes,
        smoke_job_script: bytes,
        commit: str,
        dispatcher_checksum: str,
        smoke_job_checksum: str,
    ) -> dict[str, str]:
        """Recover only the two fixed tools from one reviewed commit."""

    def collect(self, run_id: str, owner_id: str) -> bytes:
        """Return the fixed whitelisted artefact archive for an owned run."""

    def review_collect(self, run_id: str, owner_id: str, manifest_sha256: str) -> bytes:
        """Return manifest-selected and checksum-gated MR review assets."""

    def t12_review_collect(
        self,
        run_id: str,
        owner_id: str,
        summary_sha256: str,
        refinement_results_sha256: str,
        sequence_results_sha256: str,
    ) -> bytes:
        """Return checksum-gated T12 finalist assets for the second checkpoint."""

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

    def stage_archive(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream one fixed immutable source checkout archive."""

    def unknown_discovery_inputs_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Attach one fixed private review/input archive to a staged run."""

    def unknown_screen_stage(
        self,
        arguments: Sequence[str],
    ) -> dict[str, str]:
        """Run bounded login acquisition from one owned discovery parent."""

    def unknown_single_component_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Attach reviewed A-seed decisions to one owned screen child."""

    def m4_import_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream the one fixed checksum-gated cross-site M4 archive."""

    def control_slice_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream the fixed six-case prokaryotic control archive."""

    def control_matrix_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream the fixed 23-case prokaryotic control archive."""

    def m6_inputs_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream one confirmed truth-isolated M6 runner archive."""

    def m6_scientific_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream one confirmed M6 runner for a fixed scientific track."""

    def t12_stage(
        self,
        arguments: Sequence[str],
        source_records_path: Path,
    ) -> dict[str, str]:
        """Stream only the fixed catalogue source-record crosswalk for T12."""


class GitRepository(Protocol):
    """Local immutable-revision checks needed before staging."""

    def ensure_clean(self) -> None:
        """Fail unless tracked, untracked, and submodule state is clean."""

    def resolve_commit(self, revision: str) -> str:
        """Resolve HEAD or a full SHA to a full commit SHA."""

    def read_file_at_commit(self, commit: str, path: PurePosixPath) -> bytes:
        """Read one fixed repository file from an exact commit."""

    def ensure_reachable_from_origin_main(self, commit: str) -> None:
        """Fail unless the exact commit is contained in tracked origin/main."""

    def ensure_reachable_from_origin_branch(self, commit: str, branch: str) -> None:
        """Fail unless the exact commit is contained in one fixed tracked branch."""

    def create_source_archive(
        self,
        commit: str,
        destination: Path,
    ) -> tuple[str, int, str]:
        """Create one detached source checkout archive with pinned submodules."""


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

    def ensure_reachable_from_origin_main(self, commit: str) -> None:
        """Require the commit in the locally tracked immutable main history."""

        validate_commit(commit)
        self._run(["rev-parse", "--verify", "refs/remotes/origin/main^{commit}"])
        self._run(["merge-base", "--is-ancestor", commit, "refs/remotes/origin/main"])

    def ensure_reachable_from_origin_branch(self, commit: str, branch: str) -> None:
        """Require the commit in one explicitly allowed tracked remote branch."""

        validate_commit(commit)
        if branch not in {"dev/phase3"}:
            raise ValidationError("remote branch is not approved for HPC staging")
        reference = f"refs/remotes/origin/{branch}"
        self._run(["rev-parse", "--verify", f"{reference}^{{commit}}"])
        self._run(["merge-base", "--is-ancestor", commit, reference])

    def create_source_archive(
        self,
        commit: str,
        destination: Path,
    ) -> tuple[str, int, str]:
        """Archive an exact detached checkout without machine-local Git URLs."""

        validate_commit(commit)
        origin_url = self._run(["remote", "get-url", "origin"])
        helper_url = self._run(
            [
                "config",
                "--file",
                ".gitmodules",
                "--get",
                "submodule.external/nf-helper.url",
            ]
        )
        helper_source = self._repository / "external" / "nf-helper"
        if not helper_source.is_dir():
            raise ValidationError("checked-out nf-helper submodule is absent")

        with tempfile.TemporaryDirectory(prefix="nf-gtd-source-") as temporary:
            checkout = Path(temporary) / "source"

            def run(arguments: Sequence[str]) -> str:
                result = subprocess.run(
                    ["git", *arguments],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    detail = result.stderr.strip() or result.stdout.strip()
                    raise ValidationError(
                        f"cannot create immutable source archive: {detail}"
                    )
                return result.stdout.strip()

            checkout.mkdir()
            run(["-C", str(checkout), "init", "--quiet"])
            run(["-C", str(checkout), "remote", "add", "origin", origin_url])
            run(
                [
                    "-C",
                    str(checkout),
                    "fetch",
                    "--depth=1",
                    "--no-tags",
                    str(self._repository),
                    commit,
                ]
            )
            run(["-C", str(checkout), "checkout", "--detach", "FETCH_HEAD"])
            run(
                [
                    "-C",
                    str(checkout),
                    "config",
                    "submodule.external/nf-helper.url",
                    str(helper_source),
                ]
            )
            run(
                [
                    "-c",
                    "protocol.file.allow=always",
                    "-C",
                    str(checkout),
                    "submodule",
                    "update",
                    "--init",
                    "--recursive",
                ]
            )
            helper_commit = validate_commit(
                run(
                    [
                        "-C",
                        str(checkout / "external" / "nf-helper"),
                        "rev-parse",
                        "HEAD",
                    ]
                )
            )
            run(
                [
                    "-C",
                    str(checkout),
                    "config",
                    "--unset",
                    "submodule.external/nf-helper.url",
                ]
            )
            run(
                [
                    "-C",
                    str(checkout / "external" / "nf-helper"),
                    "remote",
                    "set-url",
                    "origin",
                    helper_url,
                ]
            )
            if run(["-C", str(checkout), "rev-parse", "HEAD"]) != commit:
                raise ValidationError("source archive commit verification failed")
            if run(
                [
                    "-C",
                    str(checkout),
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=all",
                    "--ignore-submodules=none",
                ]
            ):
                raise ValidationError("source archive checkout is not clean")
            with tarfile.open(destination, mode="w") as archive:
                archive.add(checkout, arcname=".", recursive=True)

        size = destination.stat().st_size
        if size < 1 or size > MAX_SOURCE_ARCHIVE_BYTES:
            raise ValidationError(
                f"source archive must contain 1..{MAX_SOURCE_ARCHIVE_BYTES} bytes"
            )
        return sha256_file(destination), size, helper_commit


class SshTransport:
    """Invoke only the configured dispatcher through one SSH alias."""

    def __init__(self, config: HpcConfig) -> None:
        self._config = config

    def _remote_command(self, operation: str, arguments: Sequence[str]) -> str:
        return shlex.join(
            [
                "/usr/bin/env",
                "-u",
                "BASH_ENV",
                "-u",
                "ENV",
                "/bin/bash",
                "--noprofile",
                "--norc",
                "-p",
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
        ) or operation == "m4-copy-stage":
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
        reported_operation = "stage" if operation == "database-stage" else operation
        if fields.get("operation") != reported_operation:
            raise RemoteOperationError(
                f"remote {operation} returned an inconsistent operation identity",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        if operation in _RUN_SCOPED_REMOTE_OPERATIONS and (
            not arguments or fields.get("run_id") != arguments[0]
        ):
            raise RemoteOperationError(
                f"remote {operation} returned an inconsistent owned run identity",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        remote_site = fields.get("site_id")
        if operation in _SITE_REQUIRED_REMOTE_OPERATIONS and remote_site is None:
            raise RemoteOperationError(
                f"remote {operation} omitted its mandatory site identity",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        if remote_site is not None and remote_site != self._config.site_id:
            raise RemoteOperationError(
                f"remote {operation} returned an inconsistent site identity",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        return fields

    def recover_tools(
        self,
        recovery_script: bytes,
        dispatcher_script: bytes,
        smoke_job_script: bytes,
        commit: str,
        dispatcher_checksum: str,
        smoke_job_checksum: str,
    ) -> dict[str, str]:
        """Run the fixed reviewed recovery script after normal deploy breaks."""

        try:
            recovery_text = recovery_script.decode("ascii")
        except UnicodeDecodeError as error:
            raise ValidationError("committed recovery script must be ASCII") from error

        remote_command = shlex.join(
            [
                "/usr/bin/env",
                "-u",
                "BASH_ENV",
                "-u",
                "ENV",
                "/bin/bash",
                "--noprofile",
                "--norc",
                "-p",
                "-c",
                recovery_text,
                "nf-gtd-hpc-recover-tools",
                self._config.remote_dispatcher,
                commit,
                dispatcher_checksum,
                smoke_job_checksum,
                str(len(dispatcher_script)),
                str(len(smoke_job_script)),
            ]
        )
        command = [
            "ssh",
            *_SSH_FIXED_OPTIONS,
            "--",
            self._config.ssh_alias,
            remote_command,
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                input=dispatcher_script + smoke_job_script,
                timeout=SSH_OPERATION_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote checksum-gated tool recovery exceeded the transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        if result.returncode != 0 or result.stdout != b"deployed\n":
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RemoteOperationError(
                detail or "remote checksum-gated tool recovery failed",
                failure_class=FailureClass.WRAPPER_FAILURE,
            )
        return {
            "deployed": "true",
            "deployment_record": str(
                PurePosixPath(self._config.remote_dispatcher).parent
                / "deployed-tools.json"
            ),
            "recovery_used": "true",
        }

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

    def t12_review_collect(
        self,
        run_id: str,
        owner_id: str,
        summary_sha256: str,
        refinement_results_sha256: str,
        sequence_results_sha256: str,
    ) -> bytes:
        """Stream only T12 assets named and hashed by collected typed results."""

        arguments = [
            run_id,
            owner_id,
            summary_sha256,
            refinement_results_sha256,
            sequence_results_sha256,
        ]
        try:
            result = subprocess.run(
                self._command("t12-review-collect", arguments),
                check=False,
                capture_output=True,
                timeout=SSH_REVIEW_COLLECTION_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote T12 review collection exceeded the fixed "
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
                message or "remote T12 review collection failed",
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

    def stage_archive(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream one bounded immutable checkout when login-node Git is broken."""

        try:
            with archive_path.open("rb") as handle:
                result = subprocess.run(
                    self._command("stage-archive", arguments),
                    stdin=handle,
                    check=False,
                    capture_output=True,
                    timeout=P0_STAGE_TIMEOUT_SECONDS,
                )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote source-archive staging exceeded the fixed transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        fields = _decode_remote_fields(result.stdout)
        if result.returncode != 0:
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
                or "remote source-archive staging failed"
            )
            raise RemoteOperationError(
                message,
                failure_class=_failure_class(fields.get("failure_class")),
            )
        if not fields:
            raise RemoteOperationError(
                "remote source-archive staging returned no structured fields",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        return fields

    def unknown_discovery_inputs_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream one bounded private unknown-discovery input archive."""

        try:
            with archive_path.open("rb") as handle:
                result = subprocess.run(
                    self._command("unknown-discovery-inputs-stage", arguments),
                    stdin=handle,
                    check=False,
                    capture_output=True,
                    timeout=P0_INPUT_STAGE_TIMEOUT_SECONDS,
                )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote unknown-discovery input staging exceeded the fixed "
                f"{P0_INPUT_STAGE_TIMEOUT_SECONDS}-second transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        fields = _decode_remote_fields(result.stdout)
        if result.returncode != 0:
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
                or "remote unknown-discovery input staging failed"
            )
            raise RemoteOperationError(
                message,
                failure_class=_failure_class(fields.get("failure_class")),
            )
        if not fields:
            raise RemoteOperationError(
                "remote unknown-discovery input staging returned no fields",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        return fields

    def unknown_screen_stage(
        self,
        arguments: Sequence[str],
    ) -> dict[str, str]:
        """Run one parent-bound provider staging operation on the login node."""

        try:
            result = subprocess.run(
                self._command("unknown-screen-stage", arguments),
                check=False,
                capture_output=True,
                timeout=UNKNOWN_PROVIDER_STAGE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote unknown-screen staging exceeded the fixed "
                f"{UNKNOWN_PROVIDER_STAGE_TIMEOUT_SECONDS}-second timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        fields = _decode_remote_fields(result.stdout)
        if result.returncode != 0:
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
                or "remote unknown-screen staging failed"
            )
            raise RemoteOperationError(
                message,
                failure_class=_failure_class(fields.get("failure_class")),
            )
        if not fields:
            raise RemoteOperationError(
                "remote unknown-screen staging returned no fields",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        return fields

    def unknown_single_component_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream checksum-confirmed A-seed decisions for one continuation."""

        try:
            with archive_path.open("rb") as handle:
                result = subprocess.run(
                    self._command("unknown-single-component-stage", arguments),
                    stdin=handle,
                    check=False,
                    capture_output=True,
                    timeout=P0_INPUT_STAGE_TIMEOUT_SECONDS,
                )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote unknown-single-component staging exceeded the fixed "
                f"{P0_INPUT_STAGE_TIMEOUT_SECONDS}-second timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        fields = _decode_remote_fields(result.stdout)
        if result.returncode != 0:
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
                or "remote unknown-single-component staging failed"
            )
            raise RemoteOperationError(
                message,
                failure_class=_failure_class(fields.get("failure_class")),
            )
        if not fields:
            raise RemoteOperationError(
                "remote unknown-single-component staging returned no fields",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        return fields

    def m4_import_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream the fixed local P2 handoff without arbitrary remote paths."""

        try:
            with archive_path.open("rb") as handle:
                result = subprocess.run(
                    self._command("m4-import-stage", arguments),
                    stdin=handle,
                    check=False,
                    capture_output=True,
                    timeout=SSH_REVIEW_COLLECTION_TIMEOUT_SECONDS,
                )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote M4 import exceeded the fixed transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        fields = _decode_remote_fields(result.stdout)
        if result.returncode != 0:
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
                or "remote M4 import failed"
            )
            raise RemoteOperationError(
                message,
                failure_class=_failure_class(fields.get("failure_class")),
            )
        if not fields:
            raise RemoteOperationError(
                "remote M4 import returned no structured fields",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        return fields

    def control_slice_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream the bounded six-case control archive to Viper."""

        try:
            with archive_path.open("rb") as handle:
                result = subprocess.run(
                    self._command("control-slice-stage", arguments),
                    stdin=handle,
                    check=False,
                    capture_output=True,
                    timeout=P0_INPUT_STAGE_TIMEOUT_SECONDS,
                )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote control-slice staging exceeded the fixed transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        fields = _decode_remote_fields(result.stdout)
        if result.returncode != 0:
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
                or "remote control-slice staging failed"
            )
            raise RemoteOperationError(
                message,
                failure_class=_failure_class(fields.get("failure_class")),
            )
        if not fields:
            raise RemoteOperationError(
                "remote control-slice staging returned no structured fields",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        return fields

    def control_matrix_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream the bounded 23-case control archive to Viper."""

        try:
            with archive_path.open("rb") as handle:
                result = subprocess.run(
                    self._command("control-matrix-stage", arguments),
                    stdin=handle,
                    check=False,
                    capture_output=True,
                    timeout=P0_INPUT_STAGE_TIMEOUT_SECONDS,
                )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote control-matrix staging exceeded the fixed transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        fields = _decode_remote_fields(result.stdout)
        if result.returncode != 0:
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
                or "remote control-matrix staging failed"
            )
            raise RemoteOperationError(
                message,
                failure_class=_failure_class(fields.get("failure_class")),
            )
        if not fields:
            raise RemoteOperationError(
                "remote control-matrix staging returned no structured fields",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        return fields

    def m6_inputs_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream one confirmed truth-isolated M6 runner archive to Viper."""

        try:
            with archive_path.open("rb") as handle:
                result = subprocess.run(
                    self._command("m6-inputs-stage", arguments),
                    stdin=handle,
                    check=False,
                    capture_output=True,
                    timeout=P0_INPUT_STAGE_TIMEOUT_SECONDS,
                )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote M6 input staging exceeded the fixed transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        fields = _decode_remote_fields(result.stdout)
        if result.returncode != 0:
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
                or "remote M6 input staging failed"
            )
            raise RemoteOperationError(
                message,
                failure_class=_failure_class(fields.get("failure_class")),
            )
        if not fields:
            raise RemoteOperationError(
                "remote M6 input staging returned no structured fields",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        return fields

    def m6_scientific_stage(
        self,
        arguments: Sequence[str],
        archive_path: Path,
    ) -> dict[str, str]:
        """Stream one confirmed runner to a fixed M6 scientific profile."""

        try:
            with archive_path.open("rb") as handle:
                result = subprocess.run(
                    self._command("m6-scientific-stage", arguments),
                    stdin=handle,
                    check=False,
                    capture_output=True,
                    timeout=P0_INPUT_STAGE_TIMEOUT_SECONDS,
                )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote M6 scientific staging exceeded the fixed transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        fields = _decode_remote_fields(result.stdout)
        if result.returncode != 0:
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
                or "remote M6 scientific staging failed"
            )
            raise RemoteOperationError(
                message,
                failure_class=_failure_class(fields.get("failure_class")),
            )
        if not fields:
            raise RemoteOperationError(
                "remote M6 scientific staging returned no structured fields",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        return fields

    def t12_stage(
        self,
        arguments: Sequence[str],
        source_records_path: Path,
    ) -> dict[str, str]:
        """Stream the fixed source-record crosswalk without arbitrary paths."""

        try:
            with source_records_path.open("rb") as handle:
                result = subprocess.run(
                    self._command("t12-stage", arguments),
                    stdin=handle,
                    check=False,
                    capture_output=True,
                    timeout=P0_INPUT_STAGE_TIMEOUT_SECONDS,
                )
        except subprocess.TimeoutExpired as error:
            raise RemoteOperationError(
                "remote T12 staging exceeded the fixed transport timeout",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        fields = _decode_remote_fields(result.stdout)
        if result.returncode != 0:
            message = (
                fields.get("message")
                or result.stderr.decode("utf-8", errors="replace").strip()
                or "remote T12 staging failed"
            )
            raise RemoteOperationError(
                message,
                failure_class=_failure_class(fields.get("failure_class")),
            )
        if not fields:
            raise RemoteOperationError(
                "remote T12 staging returned no structured fields",
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

    def deploy_tools(
        self, revision: str, *, source_branch: str = "main"
    ) -> dict[str, object]:
        """Install the two fixed remote scripts from one clean pushed commit."""

        self.git.ensure_clean()
        commit = self.git.resolve_commit(revision)
        if source_branch == "main":
            self.git.ensure_reachable_from_origin_main(commit)
        elif source_branch == "dev/phase3":
            self.git.ensure_reachable_from_origin_branch(commit, source_branch)
        else:
            raise ValidationError("remote tool source branch is not approved")
        checksums: dict[str, str] = {}
        committed_tools: dict[str, bytes] = {}
        for relative in _REMOTE_TOOL_PATHS:
            committed = self.git.read_file_at_commit(commit, relative)
            if source_branch == "main":
                worktree_path = self.config.repository.joinpath(*relative.parts)
                if worktree_path.is_symlink() or not worktree_path.is_file():
                    raise ValidationError(
                        f"remote tool must be a regular tracked file: {relative}"
                    )
                if worktree_path.read_bytes() != committed:
                    raise ValidationError(
                        f"worktree content differs from commit {commit}: {relative}"
                    )
            committed_tools[relative.name] = committed
            checksums[relative.name] = hashlib.sha256(committed).hexdigest()

        dispatcher_checksum = checksums["nf-gtd-hpc-remote"]
        smoke_job_checksum = checksums["nf-gtd-hpc-smoke-job"]
        recovery_checksum = checksums["nf-gtd-hpc-recover-tools"]
        self.logger.warning(
            "deploying checksum-verified remote HPC tools",
            extra={
                "commit": commit,
                "dispatcher_sha256": dispatcher_checksum,
                "smoke_job_sha256": smoke_job_checksum,
                "recovery_sha256": recovery_checksum,
            },
        )
        try:
            remote = self.transport.run(
                "deploy-tools",
                [commit, dispatcher_checksum, smoke_job_checksum],
            )
        except RemoteOperationError as error:
            missing_dispatcher = (
                f"/bin/bash: {self.config.remote_dispatcher}: No such file or directory"
            )
            if not (
                (
                    error.failure_class is FailureClass.ENVIRONMENT_FAILURE
                    and str(error) == "base64 is unavailable"
                )
                or (
                    error.failure_class is FailureClass.FILESYSTEM_FAILURE
                    and str(error)
                    in {
                        "bare Git mirror is absent",
                        "configured Git mirror is not bare",
                    }
                )
                or (
                    error.failure_class is FailureClass.TRANSFER_FAILURE
                    and str(error) == missing_dispatcher
                )
            ):
                raise
            recovery_script = self.git.read_file_at_commit(
                commit, PurePosixPath("bootstrap/nf-gtd-hpc-recover-tools")
            )
            self.logger.warning(
                "using checksum-gated remote tool recovery",
                extra={"commit": commit, "recovery_sha256": recovery_checksum},
            )
            remote = self.transport.recover_tools(
                recovery_script,
                committed_tools["nf-gtd-hpc-remote"],
                committed_tools["nf-gtd-hpc-smoke-job"],
                commit,
                dispatcher_checksum,
                smoke_job_checksum,
            )
        return {
            **remote,
            "operation": "deploy-tools",
            "commit": commit,
            "source_branch": source_branch,
            "dispatcher_sha256": dispatcher_checksum,
            "smoke_job_sha256": smoke_job_checksum,
            "recovery_sha256": recovery_checksum,
        }

    def stage(
        self,
        profile: str,
        revision: str,
        *,
        parent_run_id: str | None = None,
        source_branch: str | None = None,
    ) -> dict[str, object]:
        """Stage one clean immutable commit and create its local capability record."""

        validate_profile(profile)
        if profile == "database":
            raise ValidationError(
                "database administration requires the separate database-stage operation"
            )
        self.git.ensure_clean()
        commit = self.git.resolve_commit(revision)
        approved_source_branch = source_branch or (
            "dev/phase3"
            if profile
            in {
                "phase3-phenix-probe",
                "phase3-network-probe",
                "unknown-discovery",
                "unknown-screen",
                "unknown-single-component",
            }
            else "main"
        )
        if approved_source_branch == "dev/phase3":
            if profile not in {
                "heteromer-smoke",
                "phase3-phenix-probe",
                "phase3-network-probe",
                "unknown-discovery",
                "unknown-screen",
                "unknown-single-component",
                "m6-nextflow-smoke",
            }:
                raise ValidationError(
                    "dev/phase3 staging is limited to fixed Phase III controls "
                    "and M6 orchestration"
                )
            self.git.ensure_reachable_from_origin_branch(commit, "dev/phase3")
        elif approved_source_branch == "main":
            self.git.ensure_reachable_from_origin_main(commit)
        else:
            raise ValidationError("source branch is not approved for HPC staging")
        screen_parent: LocalRunRecord | None = None
        single_parent: LocalRunRecord | None = None
        if profile == "unknown-screen":
            if parent_run_id is None:
                raise ValidationError(
                    "unknown-screen staging requires an owned unknown-discovery parent"
                )
            screen_parent = self._owned_run(parent_run_id)
            if screen_parent.profile != "unknown-discovery":
                raise ValidationError(
                    "unknown-screen parent must use the unknown-discovery profile"
                )
            if screen_parent.site_id != self.config.site_id:
                raise ValidationError(
                    "unknown-screen parent must belong to the configured HPC site"
                )
            if screen_parent.commit != commit:
                raise ValidationError(
                    "unknown-screen child must use the exact discovery source commit"
                )
        if profile == "unknown-single-component":
            if parent_run_id is None:
                raise ValidationError(
                    "unknown-single-component staging requires an owned "
                    "unknown-screen parent"
                )
            single_parent = self._owned_run(parent_run_id)
            if single_parent.profile != "unknown-screen":
                raise ValidationError(
                    "unknown-single-component parent must use unknown-screen"
                )
            if single_parent.site_id != self.config.site_id:
                raise ValidationError(
                    "unknown-single-component parent belongs to another HPC site"
                )
            if single_parent.commit != commit:
                raise ValidationError(
                    "unknown-single-component child must use the exact screen "
                    "source commit"
                )
        iteration, parent = self._next_iteration(parent_run_id)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"gtd-{profile}-{timestamp}-{commit[:12]}-{secrets.token_hex(4)}"
        owner_id = secrets.token_hex(16)
        validate_run_id(run_id)
        lock_checksum = hashlib.sha256(
            self.git.read_file_at_commit(commit, PurePosixPath("pixi.lock"))
        ).hexdigest()
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
            site_id=self.config.site_id,
            commit=commit,
            owner_id=owner_id,
            profile=profile,
            iteration=iteration,
            parent_run_id=parent,
        )
        local_path = record.write(self.config.local_state_root)
        arguments = [run_id, commit, lock_checksum, owner_id, str(iteration), profile]
        if profile in {
            "heteromer-smoke",
            "phase3-phenix-probe",
            "unknown-discovery",
            "unknown-screen",
            "unknown-single-component",
        }:
            phenix_manifest, phenix_sha256 = _fixed_heteromer_phenix_binding(
                self.config.repository
            )
            arguments.extend((phenix_manifest, phenix_sha256))
        try:
            remote = self.transport.run("stage", arguments)
        except RemoteOperationError as error:
            if not (
                error.failure_class is FailureClass.FILESYSTEM_FAILURE
                and str(error)
                in {
                    "bare Git mirror is absent",
                    "configured Git mirror is not bare",
                }
            ):
                raise
            self.logger.warning(
                "using checksum-gated source archive staging",
                extra={"commit": commit, "profile": profile, "run_id": run_id},
            )
            with tempfile.TemporaryDirectory(
                prefix="nf-gtd-stage-", dir="/tmp"
            ) as temporary:
                archive_path = Path(temporary) / "source.tar"
                archive_checksum, archive_size, helper_commit = (
                    self.git.create_source_archive(commit, archive_path)
                )
                remote = self.transport.stage_archive(
                    [
                        *arguments,
                        archive_checksum,
                        str(archive_size),
                        helper_commit,
                    ],
                    archive_path,
                )
        if profile == "unknown-discovery":
            with tempfile.TemporaryDirectory(
                prefix="nf-gtd-unknown-discovery-",
                dir="/tmp",
            ) as temporary:
                archive_path = Path(temporary) / "unknown-discovery-inputs.tar"
                bundle = build_unknown_discovery_input_bundle(
                    repository=self.config.repository,
                    archive_path=archive_path,
                )
                attached = self.transport.unknown_discovery_inputs_stage(
                    [
                        run_id,
                        owner_id,
                        bundle.input_id,
                        bundle.archive_sha256,
                        str(bundle.archive_size_bytes),
                        bundle.execution_identity_id,
                        bundle.review_stage_index_id,
                    ],
                    bundle.archive_path,
                )
            if (
                attached.get("run_id") != run_id
                or attached.get("input_id") != bundle.input_id
                or attached.get("archive_sha256") != bundle.archive_sha256
            ):
                raise RemoteOperationError(
                    "remote unknown-discovery input identity differs",
                    failure_class=FailureClass.TRANSFER_FAILURE,
                )
            remote = {
                **remote,
                "unknown_input_id": bundle.input_id,
                "unknown_input_sha256": bundle.archive_sha256,
                "unknown_input_file_count": str(bundle.file_count),
            }
        if profile == "unknown-screen":
            if screen_parent is None:
                raise AssertionError("validated unknown-screen parent is absent")
            attached = self.transport.unknown_screen_stage(
                [
                    run_id,
                    owner_id,
                    screen_parent.run_id,
                    screen_parent.owner_id,
                ]
            )
            if (
                attached.get("run_id") != run_id
                or attached.get("parent_run_id") != screen_parent.run_id
                or not attached.get("provider_preparation_sha256")
            ):
                raise RemoteOperationError(
                    "remote unknown-screen staging identity differs",
                    failure_class=FailureClass.TRANSFER_FAILURE,
                )
            remote = {
                **remote,
                "unknown_discovery_parent_run_id": screen_parent.run_id,
                "provider_preparation_sha256": attached["provider_preparation_sha256"],
            }
        if profile == "unknown-single-component":
            if single_parent is None:
                raise AssertionError(
                    "validated unknown-single-component parent is absent"
                )
            with tempfile.TemporaryDirectory(
                prefix="nf-gtd-unknown-single-component-",
                dir="/tmp",
            ) as temporary:
                archive_path = Path(temporary) / "unknown-single-inputs.tar"
                bundle = build_unknown_single_component_input_bundle(
                    repository=self.config.repository,
                    parent_run_id=single_parent.run_id,
                    archive_path=archive_path,
                )
                attached = self.transport.unknown_single_component_stage(
                    [
                        run_id,
                        owner_id,
                        single_parent.run_id,
                        single_parent.owner_id,
                        bundle.input_id,
                        bundle.archive_sha256,
                        str(bundle.archive_size_bytes),
                    ],
                    bundle.archive_path,
                )
            if (
                attached.get("run_id") != run_id
                or attached.get("parent_run_id") != single_parent.run_id
                or attached.get("input_id") != bundle.input_id
            ):
                raise RemoteOperationError(
                    "remote unknown-single-component staging identity differs",
                    failure_class=FailureClass.TRANSFER_FAILURE,
                )
            remote = {
                **remote,
                "unknown_screen_parent_run_id": single_parent.run_id,
                "unknown_single_input_id": bundle.input_id,
                "unknown_single_decision_count": str(bundle.decision_count),
            }
        if profile == "m6-nextflow-smoke":
            remote_site = remote.get("site_id")
            if not isinstance(remote_site, str):
                raise ValidationError("M6 stage response omits the fixed site identity")
            validate_site_id(remote_site)
            if remote_site != self.config.site_id:
                replace(record, site_id=remote_site).write(self.config.local_state_root)
                raise ValidationError(
                    "M6 stage endpoint site differs from the configured site: "
                    f"{remote_site} != {self.config.site_id}"
                )
        return {
            **remote,
            "operation": "stage",
            "run_id": run_id,
            "commit": commit,
            "profile": profile,
            "source_branch": approved_source_branch,
            "iteration": iteration,
            "local_record": str(local_path),
        }

    def m4_copy_stage(
        self,
        revision: str,
        parent_run_id: str,
        decisions: Path,
        confirmation: str,
    ) -> dict[str, object]:
        """Stage all explicitly approved retained seeds for copy-two screening."""

        self.git.ensure_clean()
        parent = self._owned_run(parent_run_id)
        if parent.profile != "p2-diverse":
            raise ValidationError("M4 copy staging requires a retained p2-diverse run")
        decisions_path = decisions.resolve(strict=True)
        if decisions.is_symlink() or not decisions_path.is_file():
            raise ValidationError("M4 decisions must be a regular non-symlink file")
        payload = decisions_path.read_bytes()
        if not payload or len(payload) > 32 * 1024:
            raise ValidationError("M4 decisions must contain 1..32768 bytes")
        try:
            payload.decode("ascii")
        except UnicodeDecodeError as error:
            raise ValidationError("M4 decisions must be ASCII TSV") from error
        decisions_sha256 = hashlib.sha256(payload).hexdigest()
        if confirmation != decisions_sha256:
            raise ValidationError(
                "M4 decision confirmation must exactly equal its SHA-256"
            )
        review_manifest = (
            self.config.local_state_root
            / parent_run_id
            / "review-assets-all/artifacts/qualification/p2-diverse-review/"
            "mr_seed_review_manifest.json"
        )
        if not review_manifest.is_file() or review_manifest.is_symlink():
            raise ValidationError(
                "verified retain-all review manifest is absent locally"
            )
        review_sha256 = sha256_file(review_manifest)
        commit = self.git.resolve_commit(revision)
        self.git.ensure_reachable_from_origin_main(commit)
        iteration, _ = self._next_iteration(parent_run_id)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"gtd-m4-copy-{timestamp}-{commit[:12]}-{secrets.token_hex(4)}"
        owner_id = secrets.token_hex(16)
        validate_run_id(run_id)
        lock_checksum = sha256_file(self.config.repository / "pixi.lock")
        record = LocalRunRecord(
            run_id=run_id,
            site_id=self.config.site_id,
            commit=commit,
            owner_id=owner_id,
            profile="m4-copy",
            iteration=iteration,
            parent_run_id=parent_run_id,
        )
        local_path = record.write(self.config.local_state_root)
        self.logger.info(
            "staging comparative M4 copy screen",
            extra={
                "run_id": run_id,
                "parent_run_id": parent_run_id,
                "seed_decisions_sha256": decisions_sha256,
            },
        )
        remote = self.transport.run(
            "m4-copy-stage",
            [
                run_id,
                commit,
                lock_checksum,
                owner_id,
                str(iteration),
                parent_run_id,
                parent.owner_id,
                decisions_sha256,
                review_sha256,
                base64.b64encode(payload).decode("ascii"),
            ],
        )
        return {
            **remote,
            "operation": "m4-copy-stage",
            "run_id": run_id,
            "commit": commit,
            "profile": "m4-copy",
            "iteration": iteration,
            "parent_run_id": parent_run_id,
            "decisions_sha256": decisions_sha256,
            "review_manifest_sha256": review_sha256,
            "local_record": str(local_path),
        }

    def m4_import_stage(self, revision: str) -> dict[str, object]:
        """Create a Viper-owned M4 run from the fixed collected Marmic evidence."""

        if self.config.site_id != "viper-cpu":
            raise ValidationError("m4-import-stage is available only for viper-cpu")
        self.git.ensure_clean()
        commit = self.git.resolve_commit(revision)
        self.git.ensure_reachable_from_origin_main(commit)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"gtd-m4-copy-{timestamp}-{commit[:12]}-{secrets.token_hex(4)}"
        owner_id = secrets.token_hex(16)
        validate_run_id(run_id)
        lock_checksum = sha256_file(self.config.repository / "pixi.lock")
        record = LocalRunRecord(
            run_id=run_id,
            site_id=self.config.site_id,
            commit=commit,
            owner_id=owner_id,
            profile="m4-copy",
            iteration=1,
            parent_run_id=None,
        )
        local_path = record.write(self.config.local_state_root)
        with tempfile.TemporaryDirectory(
            prefix="nf-gtd-m4-import-", dir="/tmp"
        ) as temporary:
            bundle = build_fixed_m4_import_bundle(
                self.config.repository,
                Path(temporary) / "m4-import.tar.gz",
                progress=self.progress,
            )
            self.logger.info(
                "staging fixed cross-site M4 evidence",
                extra={
                    "run_id": run_id,
                    "archive_sha256": bundle.archive_sha256,
                    "seed_count": bundle.seed_count,
                },
            )
            remote = self.transport.m4_import_stage(
                [
                    run_id,
                    commit,
                    lock_checksum,
                    owner_id,
                    bundle.archive_sha256,
                    str(bundle.archive_size_bytes),
                    bundle.review_manifest_sha256,
                    bundle.decisions_sha256,
                    bundle.mtz_sha256,
                ],
                bundle.archive,
            )
        return {
            **remote,
            "operation": "m4-import-stage",
            "run_id": run_id,
            "site_id": self.config.site_id,
            "commit": commit,
            "profile": "m4-copy",
            "source_site_id": "marmic",
            "seed_count": bundle.seed_count,
            "archive_sha256": bundle.archive_sha256,
            "review_manifest_sha256": bundle.review_manifest_sha256,
            "decisions_sha256": bundle.decisions_sha256,
            "mtz_sha256": bundle.mtz_sha256,
            "local_record": str(local_path),
        }

    def control_slice_stage(self, revision: str) -> dict[str, object]:
        """Stage the fixed six-case truth-labelled control slice on Viper."""

        if self.config.site_id != "viper-cpu":
            raise ValidationError("control-slice-stage is available only for viper-cpu")
        self.git.ensure_clean()
        commit = self.git.resolve_commit(revision)
        self.git.ensure_reachable_from_origin_main(commit)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"gtd-control-slice-{timestamp}-{commit[:12]}-{secrets.token_hex(4)}"
        owner_id = secrets.token_hex(16)
        validate_run_id(run_id)
        lock_checksum = sha256_file(self.config.repository / "pixi.lock")
        record = LocalRunRecord(
            run_id=run_id,
            site_id=self.config.site_id,
            commit=commit,
            owner_id=owner_id,
            profile="control-slice",
            iteration=1,
            parent_run_id=None,
        )
        local_path = record.write(self.config.local_state_root)
        with tempfile.TemporaryDirectory(
            prefix="nf-gtd-control-slice-", dir="/tmp"
        ) as temporary:
            bundle = build_fixed_control_slice_bundle(
                self.config.repository,
                Path(temporary) / "control-slice.tar.gz",
                progress=self.progress,
            )
            self.logger.info(
                "staging fixed prokaryotic control slice",
                extra={
                    "run_id": run_id,
                    "archive_sha256": bundle.archive_sha256,
                    "case_count": bundle.case_count,
                },
            )
            remote = self.transport.control_slice_stage(
                [
                    run_id,
                    commit,
                    lock_checksum,
                    owner_id,
                    bundle.archive_sha256,
                    str(bundle.archive_size_bytes),
                    bundle.manifest_sha256,
                    str(bundle.case_count),
                ],
                bundle.archive,
            )
        return {
            **remote,
            "operation": "control-slice-stage",
            "run_id": run_id,
            "site_id": self.config.site_id,
            "commit": commit,
            "profile": "control-slice",
            "slice_id": "prokaryote_homomer_smoke_v1",
            "case_count": bundle.case_count,
            "archive_sha256": bundle.archive_sha256,
            "manifest_sha256": bundle.manifest_sha256,
            "local_record": str(local_path),
        }

    def control_matrix_stage(self, revision: str) -> dict[str, object]:
        """Stage the complete fixed 23-case truth-labelled matrix on Viper."""

        if self.config.site_id != "viper-cpu":
            raise ValidationError(
                "control-matrix-stage is available only for viper-cpu"
            )
        self.git.ensure_clean()
        commit = self.git.resolve_commit(revision)
        self.git.ensure_reachable_from_origin_main(commit)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"gtd-control-matrix-{timestamp}-{commit[:12]}-{secrets.token_hex(4)}"
        owner_id = secrets.token_hex(16)
        validate_run_id(run_id)
        lock_checksum = sha256_file(self.config.repository / "pixi.lock")
        record = LocalRunRecord(
            run_id=run_id,
            site_id=self.config.site_id,
            commit=commit,
            owner_id=owner_id,
            profile="control-matrix",
            iteration=1,
            parent_run_id=None,
        )
        local_path = record.write(self.config.local_state_root)
        with tempfile.TemporaryDirectory(
            prefix="nf-gtd-control-matrix-", dir="/tmp"
        ) as temporary:
            bundle = build_fixed_control_matrix_bundle(
                self.config.repository,
                Path(temporary) / "control-matrix.tar.gz",
                progress=self.progress,
            )
            self.logger.info(
                "staging complete prokaryotic control matrix",
                extra={
                    "run_id": run_id,
                    "archive_sha256": bundle.archive_sha256,
                    "case_count": bundle.case_count,
                },
            )
            remote = self.transport.control_matrix_stage(
                [
                    run_id,
                    commit,
                    lock_checksum,
                    owner_id,
                    bundle.archive_sha256,
                    str(bundle.archive_size_bytes),
                    bundle.manifest_sha256,
                    str(bundle.case_count),
                ],
                bundle.archive,
            )
        return {
            **remote,
            "operation": "control-matrix-stage",
            "run_id": run_id,
            "site_id": self.config.site_id,
            "commit": commit,
            "profile": "control-matrix",
            "suite_id": "prokaryote_homomer_workflow_v1",
            "case_count": bundle.case_count,
            "positive_count": bundle.positive_count,
            "real_search_count": bundle.real_search_count,
            "archive_sha256": bundle.archive_sha256,
            "manifest_sha256": bundle.manifest_sha256,
            "local_record": str(local_path),
        }

    def m6_inputs_stage(
        self,
        revision: str,
        archive: Path,
        expected_archive_sha256: str,
        *,
        source_branch: str = "main",
    ) -> dict[str, object]:
        """Stage one explicitly confirmed truth-isolated 63-case M6 archive."""

        if self.config.site_id not in {"viper-cpu", "marmic"}:
            raise ValidationError("m6-inputs-stage requires a reviewed HPC site")
        self.git.ensure_clean()
        commit = self.git.resolve_commit(revision)
        if source_branch == "main":
            self.git.ensure_reachable_from_origin_main(commit)
        elif source_branch == "dev/phase3":
            self.git.ensure_reachable_from_origin_branch(commit, source_branch)
        else:
            raise ValidationError("source branch is not approved for M6 staging")
        untracked_root = (self.config.repository / ".untracked").resolve(strict=True)
        try:
            archive.resolve(strict=True).relative_to(untracked_root)
        except (OSError, ValueError) as error:
            raise ValidationError(
                "M6 runner archive must be below the repository .untracked directory"
            ) from error
        (
            archive_path,
            archive_sha256,
            archive_size,
            manifest_sha256,
            case_count,
            object_count,
        ) = _inspect_m6_runner_archive(
            archive,
            protocol=self.config.repository / "benchmarks/m6/protocol.yaml",
            expected_sha256=expected_archive_sha256,
        )
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"gtd-m6-inputs-{timestamp}-{commit[:12]}-{secrets.token_hex(4)}"
        owner_id = secrets.token_hex(16)
        validate_run_id(run_id)
        lock_checksum = sha256_file(self.config.repository / "pixi.lock")
        record = LocalRunRecord(
            run_id=run_id,
            site_id=self.config.site_id,
            commit=commit,
            owner_id=owner_id,
            profile="m6-inputs",
            iteration=1,
            parent_run_id=None,
        )
        local_path = record.write(self.config.local_state_root)
        self.logger.info(
            "staging truth-isolated M6 runner inputs",
            extra={
                "run_id": run_id,
                "archive_sha256": archive_sha256,
                "case_count": case_count,
                "object_count": object_count,
            },
        )
        remote = self.transport.m6_inputs_stage(
            [
                run_id,
                commit,
                lock_checksum,
                owner_id,
                archive_sha256,
                str(archive_size),
                manifest_sha256,
                str(case_count),
                str(object_count),
            ],
            archive_path,
        )
        return {
            **remote,
            "operation": "m6-inputs-stage",
            "run_id": run_id,
            "site_id": self.config.site_id,
            "commit": commit,
            "source_branch": source_branch,
            "profile": "m6-inputs",
            "protocol_id": "m6_independent_prokaryote_homomer_v1",
            "case_count": case_count,
            "object_count": object_count,
            "archive_sha256": archive_sha256,
            "manifest_sha256": manifest_sha256,
            "local_record": str(local_path),
        }

    def m6_scientific_stage(
        self,
        revision: str,
        archive: Path,
        expected_archive_sha256: str,
        track: str,
        *,
        source_branch: str = "main",
        operational_parent_run_id: str | None = None,
    ) -> dict[str, object]:
        """Stage one fixed truth-isolated M6 track at its reviewed site."""

        if self.config.site_id not in {"viper-cpu", "marmic"}:
            raise ValidationError("M6 scientific staging requires a reviewed HPC site")
        if track not in {"operational", "leakage"}:
            raise ValidationError("M6 scientific track must be operational or leakage")
        self.git.ensure_clean()
        commit = self.git.resolve_commit(revision)
        operational_parent: LocalRunRecord | None = None
        operational_precheck_sha256: str | None = None
        if track == "operational":
            if operational_parent_run_id is not None:
                raise ValidationError("M6 operational staging cannot have a parent")
        else:
            if operational_parent_run_id is None:
                raise ValidationError(
                    "M6 leakage requires its collected operational parent"
                )
            operational_parent = self._owned_run(operational_parent_run_id)
            if (
                operational_parent.profile != "m6-operational"
                or operational_parent.site_id != self.config.site_id
                or operational_parent.commit != commit
            ):
                raise ValidationError(
                    "M6 leakage parent differs in profile, site, or source"
                )
            operational_precheck_sha256 = _m6_operational_precheck(
                self.config.local_state_root
                / operational_parent.run_id
                / "collected",
                operational_parent,
            )
        if source_branch == "main":
            self.git.ensure_reachable_from_origin_main(commit)
        elif source_branch == "dev/phase3":
            self.git.ensure_reachable_from_origin_branch(commit, source_branch)
        else:
            raise ValidationError("source branch is not approved for M6 staging")
        untracked_root = (self.config.repository / ".untracked").resolve(strict=True)
        try:
            archive.resolve(strict=True).relative_to(untracked_root)
        except (OSError, ValueError) as error:
            raise ValidationError(
                "M6 runner archive must be below the repository .untracked directory"
            ) from error
        (
            archive_path,
            archive_sha256,
            archive_size,
            manifest_sha256,
            case_count,
            object_count,
        ) = _inspect_m6_runner_archive(
            archive,
            protocol=self.config.repository / "benchmarks/m6/protocol.yaml",
            expected_sha256=expected_archive_sha256,
        )
        profile = f"m6-{track}"
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"gtd-{profile}-{timestamp}-{commit[:12]}-{secrets.token_hex(4)}"
        owner_id = secrets.token_hex(16)
        validate_run_id(run_id)
        lock_checksum = sha256_file(self.config.repository / "pixi.lock")
        record = LocalRunRecord(
            run_id=run_id,
            site_id=self.config.site_id,
            commit=commit,
            owner_id=owner_id,
            profile=profile,
            iteration=1,
            parent_run_id=(
                operational_parent.run_id
                if operational_parent is not None
                else None
            ),
        )
        local_path = record.write(self.config.local_state_root)
        self.logger.info(
            "staging truth-isolated M6 scientific track",
            extra={
                "run_id": run_id,
                "track": track,
                "archive_sha256": archive_sha256,
                "case_count": case_count,
                "object_count": object_count,
            },
        )
        arguments = [
            run_id,
            commit,
            lock_checksum,
            owner_id,
            archive_sha256,
            str(archive_size),
            manifest_sha256,
            str(case_count),
            str(object_count),
            track,
        ]
        if self.config.site_id == "marmic":
            arguments.extend(_fixed_heteromer_phenix_binding(self.config.repository))
        try:
            remote = self.transport.m6_scientific_stage(arguments, archive_path)
        except RemoteOperationError as error:
            if not (
                error.failure_class is FailureClass.FILESYSTEM_FAILURE
                and str(error)
                in {"bare Git mirror is absent", "configured Git mirror is not bare"}
            ):
                raise
            self.logger.warning(
                "using checksum-gated M6 source archive staging",
                extra={"commit": commit, "profile": profile, "run_id": run_id},
            )
            with tempfile.TemporaryDirectory(
                prefix="nf-gtd-m6-stage-", dir="/tmp"
            ) as temporary:
                source_archive = Path(temporary) / "source.tar"
                source_sha256, source_size, helper_commit = (
                    self.git.create_source_archive(commit, source_archive)
                )
                combined_archive = Path(temporary) / "source-and-runner.bin"
                with combined_archive.open("wb") as output:
                    with source_archive.open("rb") as source:
                        shutil.copyfileobj(source, output)
                    with archive_path.open("rb") as runner:
                        shutil.copyfileobj(runner, output)
                remote = self.transport.m6_scientific_stage(
                    [*arguments, source_sha256, str(source_size), helper_commit],
                    combined_archive,
                )
        if operational_parent is not None:
            assert operational_precheck_sha256 is not None
            bound = self.transport.run(
                "m6-leakage-parent-bind",
                [
                    run_id,
                    owner_id,
                    operational_parent.run_id,
                    operational_parent.owner_id,
                    operational_precheck_sha256,
                ],
            )
            if (
                bound.get("run_id") != run_id
                or bound.get("parent_run_id") != operational_parent.run_id
                or bound.get("operational_precheck_sha256")
                != operational_precheck_sha256
            ):
                raise RemoteOperationError(
                    "M6 leakage parent binding differs",
                    failure_class=FailureClass.TRANSFER_FAILURE,
                )
            remote = {**remote, **bound}
        remote_site = remote.get("site_id")
        if not isinstance(remote_site, str):
            raise ValidationError("M6 stage response omits the fixed site identity")
        validate_site_id(remote_site)
        if remote_site != self.config.site_id:
            replace(record, site_id=remote_site).write(self.config.local_state_root)
            raise ValidationError(
                "M6 stage endpoint site differs from the configured site: "
                f"{remote_site} != {self.config.site_id}"
            )
        return {
            **remote,
            "operation": "m6-scientific-stage",
            "run_id": run_id,
            "site_id": self.config.site_id,
            "commit": commit,
            "source_branch": source_branch,
            "profile": profile,
            "track": track,
            "protocol_id": "m6_independent_prokaryote_homomer_v1",
            "case_count": case_count,
            "object_count": object_count,
            "driver_cpu_count": 2,
            "driver_memory_gb": 8.0,
            "maximum_cpu_count": 32,
            "maximum_memory_gb": 16.0,
            "maximum_concurrent_phenix_attempts": "scheduler_managed",
            "scheduler_ceiling_hours": 24.0,
            "archive_sha256": archive_sha256,
            "manifest_sha256": manifest_sha256,
            "local_record": str(local_path),
        }

    def t12_stage(self, revision: str, parent_run_id: str) -> dict[str, object]:
        """Stage all retained copy-two parents plus the fixed source crosswalk."""

        if self.config.site_id != "viper-cpu":
            raise ValidationError("t12-stage is available only for viper-cpu")
        self.git.ensure_clean()
        parent = self._owned_run(parent_run_id)
        if parent.profile != "m4-copy":
            raise ValidationError("T12 staging requires a retained M4 parent")
        commit = self.git.resolve_commit(revision)
        self.git.ensure_reachable_from_origin_main(commit)
        source_records = (
            self.config.repository
            / ".untracked/m0-qualification/results/catalogue-reference-637975d"
            / "source_records.jsonl"
        )
        source_records_resolved = source_records.resolve(strict=True)
        if source_records.is_symlink() or not source_records_resolved.is_file():
            raise ValidationError(
                "fixed authoritative source-record crosswalk is absent or unsafe"
            )
        source_size = source_records_resolved.stat().st_size
        if source_size < 1 or source_size > 2 * 1024 * 1024:
            raise ValidationError("fixed source-record crosswalk is outside size limit")
        source_sha256 = sha256_file(source_records_resolved)
        iteration, _ = self._next_iteration(parent_run_id)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"gtd-t12-{timestamp}-{commit[:12]}-{secrets.token_hex(4)}"
        owner_id = secrets.token_hex(16)
        validate_run_id(run_id)
        lock_checksum = sha256_file(self.config.repository / "pixi.lock")
        record = LocalRunRecord(
            run_id=run_id,
            site_id=self.config.site_id,
            commit=commit,
            owner_id=owner_id,
            profile="t12",
            iteration=iteration,
            parent_run_id=parent_run_id,
        )
        local_path = record.write(self.config.local_state_root)
        self.logger.info(
            "staging fixed T12 parent boundary",
            extra={
                "run_id": run_id,
                "parent_run_id": parent_run_id,
                "source_records_sha256": source_sha256,
            },
        )
        remote = self.transport.t12_stage(
            [
                run_id,
                commit,
                lock_checksum,
                owner_id,
                str(iteration),
                parent_run_id,
                parent.owner_id,
                source_sha256,
                str(source_size),
            ],
            source_records_resolved,
        )
        return {
            **remote,
            "operation": "t12-stage",
            "run_id": run_id,
            "site_id": self.config.site_id,
            "commit": commit,
            "profile": "t12",
            "parent_run_id": parent_run_id,
            "source_records_sha256": source_sha256,
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

    def database_runtime_configure(
        self,
        paths_file: Path,
        confirmation: str,
    ) -> dict[str, object]:
        """Install one absent configuration for an existing immutable database."""

        payload = _validated_database_runtime_paths_payload(paths_file)
        checksum = hashlib.sha256(payload).hexdigest()
        if confirmation != checksum:
            raise ValidationError(
                "database runtime confirmation must exactly equal its SHA-256"
            )
        encoded = base64.b64encode(payload).decode("ascii")
        self.logger.warning(
            "installing validated fixed database runtime configuration",
            extra={"database_config_sha256": checksum},
        )
        return {
            **self.transport.run(
                "database-runtime-configure",
                [checksum, encoded],
            ),
            "operation": "database-runtime-configure",
            "database_config_sha256": checksum,
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
            site_id=self.config.site_id,
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
                        if record.profile
                        in {
                            "p2",
                            "p2-diverse",
                            "p2-control",
                            "heteromer-smoke",
                            "unknown-discovery",
                            "unknown-screen",
                            "unknown-single-component",
                            "control-slice",
                            "control-matrix",
                            "m6-nextflow-smoke",
                            "m6-operational",
                            "m6-leakage",
                            "m4-copy",
                            "t12",
                        }
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
                scheduler_state = result.get("scheduler_state")
                if not isinstance(scheduler_state, str) or scheduler_state not in (
                    _QUEUED_STATES | _RUNNING_STATES | _TERMINAL_STATES
                ):
                    raise RemoteOperationError(
                        "remote scheduler state is missing or unsupported",
                        failure_class=FailureClass.TRANSFER_FAILURE,
                    )
                terminal = result.get("terminal")
                if (
                    not isinstance(terminal, str)
                    or terminal not in {"true", "false"}
                    or ((terminal == "true") != (scheduler_state in _TERMINAL_STATES))
                ):
                    raise RemoteOperationError(
                        "remote terminal flag contradicts its scheduler state",
                        failure_class=FailureClass.TRANSFER_FAILURE,
                    )
                if terminal == "true":
                    return {**result, "operation": "wait"}
                if scheduler_state in _RUNNING_STATES and phase == "queue":
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
                            "terminal": "false",
                            "wait_timeout_class": FailureClass.QUEUE_TIMEOUT,
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
                            "terminal": "false",
                            "wait_timeout_class": "execution_wait_timeout",
                            "message": (
                                "execution wait limit reached; inspect scheduler state"
                            ),
                        }

    def logs(self, run_id: str, lines: int) -> dict[str, object]:
        """Retrieve a bounded tail through the dispatcher and return UTF-8 text."""

        record = self._owned_run(run_id)
        validate_log_lines(lines)
        result = self.transport.run("logs", [run_id, record.owner_id, str(lines)])
        if result.get("operation") != "logs":
            raise RemoteOperationError(
                "remote log operation identity is missing or invalid",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        if result.get("run_id") != run_id:
            raise RemoteOperationError(
                "remote log run identity does not match the owned run",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        if "content_base64" not in result:
            raise RemoteOperationError(
                "remote log content was not explicitly declared",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        encoded = result.pop("content_base64")
        try:
            payload = base64.b64decode(encoded, validate=True)
        except ValueError as error:
            raise RemoteOperationError(
                "remote log content was not valid base64",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from error
        if len(payload) > MAX_LOG_BYTES:
            raise RemoteOperationError(
                "remote log content exceeded the local byte limit",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        content = payload.decode("utf-8", errors="replace")
        return {**result, "operation": "logs", "log": content}

    def collect(self, run_id: str) -> dict[str, object]:
        """Collect and safely extract only the remote dispatcher's whitelist."""

        record = self._owned_run(run_id)
        self.logger.info("collecting HPC run artefacts", extra={"run_id": run_id})
        archive = self.transport.collect(run_id, record.owner_id)
        source_lock_sha256 = hashlib.sha256(
            self.git.read_file_at_commit(record.commit, PurePosixPath("pixi.lock"))
        ).hexdigest()
        _validated_owned_terminal_result(
            archive,
            record,
            source_lock_sha256=source_lock_sha256,
        )
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
        """Collect checksum-bound assets for every Coot-inspectable MR solution."""

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
                "inspectable_solution_count": len(solution_ids),
                "manifest_sha256": manifest_sha256,
            },
        )
        archive = self.transport.review_collect(
            run_id, record.owner_id, manifest_sha256
        )
        destination = self.config.local_state_root / run_id / "review-assets-all"
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
            "inspectable_solution_count": len(solution_ids),
            "solution_ids": solution_ids,
            "files": files,
        }

    def t12_review_collect(self, run_id: str) -> dict[str, object]:
        """Collect T12 finalist assets and render the second review checkpoint."""

        record = self._owned_run(run_id)
        if record.profile != "t12":
            raise ValidationError("t12-review-collect requires a t12 run")
        collected = self.config.local_state_root / run_id / "collected"
        expectations, summary_sha, refinement_sha, sequence_sha, seed_ids = (
            _t12_review_asset_expectations(collected, record)
        )
        self.logger.info(
            "collecting checksum-gated T12 finalist assets",
            extra={"run_id": run_id, "finalist_count": len(seed_ids)},
        )
        archive = self.transport.t12_review_collect(
            run_id,
            record.owner_id,
            summary_sha,
            refinement_sha,
            sequence_sha,
        )
        asset_root = self.config.local_state_root / run_id / "t12-review-assets"
        files = _extract_verified_review_archive(
            archive,
            asset_root,
            expectations,
            progress=self.progress,
        )
        package_root = self.config.local_state_root / run_id / "t12-sequence-checkpoint"
        package = build_sequence_checkpoint(
            SequenceCheckpointRequest(
                run_id=run_id,
                refinement_results_jsonl=collected.joinpath(
                    *_T12_REFINEMENT_RELATIVE.parts
                ),
                sequence_results_jsonl=collected.joinpath(
                    *_T12_SEQUENCE_RELATIVE.parts
                ),
                stage_manifest_json=collected.joinpath(
                    *_T12_STAGE_MANIFEST_RELATIVE.parts
                ),
                job_result_json=collected.joinpath(*_REVIEW_JOB_RESULT_RELATIVE.parts),
                sequence_groups_jsonl=asset_root.joinpath(
                    *_T12_SEQUENCE_GROUPS_RELATIVE.parts
                ),
                source_records_jsonl=asset_root.joinpath(
                    *_T12_SOURCE_RECORDS_RELATIVE.parts
                ),
                preflight_jsonl=asset_root.joinpath(*_T12_PREFLIGHT_RELATIVE.parts),
                asset_root=asset_root,
                output_directory=package_root,
                progress=self.progress,
            )
        )
        return {
            "operation": "t12-review-collect",
            "run_id": run_id,
            "destination": str(package_root),
            "package_id": package.package_id,
            "finalist_count": package.finalist_count,
            "seed_solution_ids": seed_ids,
            "asset_files": files,
            "manifest": str(package.manifest_json),
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
        record = load_local_run(self.config.local_state_root, validate_run_id(run_id))
        if record.site_id != self.config.site_id:
            raise ValidationError(
                f"run {run_id} belongs to site {record.site_id}, not "
                f"{self.config.site_id}"
            )
        return record

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
            raise RemoteOperationError(
                "remote dispatcher returned a malformed protocol field",
                failure_class=FailureClass.TRANSFER_FAILURE,
            ) from None
        if re.fullmatch(r"[a-z][a-z0-9_]*", key) is None:
            raise RemoteOperationError(
                "remote dispatcher returned an unsupported protocol field",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
        if key in fields:
            raise RemoteOperationError(
                "remote dispatcher returned a duplicate protocol field",
                failure_class=FailureClass.TRANSFER_FAILURE,
            )
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


def _terminal_evidence_error(reason: str) -> RemoteOperationError:
    return RemoteOperationError(
        f"owned terminal HPC evidence is invalid: {reason}",
        failure_class=FailureClass.TRANSFER_FAILURE,
    )


def _terminal_evidence_mapping(payload: bytes, *, label: str) -> Mapping[str, object]:
    try:
        value = parse_json_document(payload.decode("utf-8"), label=label)
    except (UnicodeDecodeError, ContractLoadError) as error:
        raise _terminal_evidence_error(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise _terminal_evidence_error(f"{label} must be a JSON object")
    return value


def _validated_failure_outcome(result: Mapping[str, object]) -> FailureClass:
    failure_value = result.get("failure_class")
    if not isinstance(failure_value, str):
        raise _terminal_evidence_error("failure_class must be explicitly declared")
    try:
        failure = FailureClass(failure_value)
    except ValueError as error:
        raise _terminal_evidence_error(
            f"failure_class is unsupported: {failure_value!r}"
        ) from error

    scheduler_state = result.get("scheduler_state")
    if not isinstance(scheduler_state, str) or scheduler_state not in _TERMINAL_STATES:
        raise _terminal_evidence_error("scheduler_state is not a terminal state")
    exit_code = result.get("exit_code")
    if type(exit_code) is not int or exit_code < 0:
        raise _terminal_evidence_error("exit_code must be a non-negative integer")
    if failure is FailureClass.SUCCESS:
        if scheduler_state != "COMPLETED" or exit_code != 0:
            raise _terminal_evidence_error(
                "success requires COMPLETED and exit_code zero"
            )
    elif scheduler_state == "COMPLETED" or exit_code == 0:
        raise _terminal_evidence_error(
            "failure requires a non-success terminal state and nonzero exit_code"
        )
    return failure


def _validated_terminal_timestamps(result: Mapping[str, object]) -> None:
    parsed: list[datetime] = []
    for field in ("started_at", "completed_at"):
        value = result.get(field)
        if not isinstance(value, str):
            raise _terminal_evidence_error(f"{field} must be an explicit timestamp")
        try:
            parsed.append(datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
        except ValueError as error:
            raise _terminal_evidence_error(
                f"{field} must be a canonical UTC timestamp"
            ) from error
    if parsed[1] < parsed[0]:
        raise _terminal_evidence_error("completed_at precedes started_at")


def _validated_terminal_inventory(result: Mapping[str, object]) -> None:
    for field in ("structured_test_reports", "retained_artifacts"):
        inventory = result.get(field)
        if not isinstance(inventory, list):
            raise _terminal_evidence_error(f"{field} must be an explicit list")
        seen: set[str] = set()
        for value in inventory:
            if not isinstance(value, str):
                raise _terminal_evidence_error(f"{field} contains a non-path value")
            relative = PurePosixPath(value)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not relative.parts
                or relative.parts[0] != "artifacts"
                or value != relative.as_posix()
                or value in seen
            ):
                raise _terminal_evidence_error(
                    f"{field} contains an unsafe or duplicated path"
                )
            seen.add(value)


def _owned_terminal_archive_evidence(archive: bytes) -> dict[str, bytes]:
    required = frozenset({"manifest.json", "state/job-id", "state/job-result.json"})
    if len(archive) > MAX_ARTIFACT_TOTAL_BYTES:
        raise _terminal_evidence_error(
            "compressed archive exceeds the collection limit"
        )
    evidence: dict[str, bytes] = {}
    seen: set[str] = set()
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            for member in tar.getmembers():
                relative = PurePosixPath(member.name)
                if (
                    not member.isfile()
                    or relative.is_absolute()
                    or ".." in relative.parts
                    or not relative.parts
                ):
                    raise _terminal_evidence_error(
                        f"unsafe archive member: {member.name!r}"
                    )
                name = relative.as_posix()
                if name in seen:
                    raise _terminal_evidence_error(
                        f"archive member is duplicated: {name}"
                    )
                seen.add(name)
                if member.size > MAX_ARTIFACT_FILE_BYTES:
                    raise _terminal_evidence_error(
                        f"artefact exceeds per-file limit: {name}"
                    )
                total += member.size
                if total > MAX_ARTIFACT_TOTAL_BYTES:
                    raise _terminal_evidence_error(
                        "artefacts exceed total collection limit"
                    )
                if name in required:
                    if member.size > MAX_LOG_BYTES:
                        raise _terminal_evidence_error(
                            f"terminal evidence exceeds its bounded size: {name}"
                        )
                    source = tar.extractfile(member)
                    if source is None:
                        raise _terminal_evidence_error(
                            f"cannot read required terminal evidence: {name}"
                        )
                    evidence[name] = source.read()
    except (OSError, EOFError, tarfile.TarError) as error:
        raise _terminal_evidence_error("remote artefact archive is invalid") from error

    missing = sorted(required - evidence.keys())
    if missing:
        raise _terminal_evidence_error(
            f"required terminal evidence is absent: {', '.join(missing)}"
        )
    return evidence


def _validated_owned_terminal_result(
    archive: bytes,
    record: LocalRunRecord,
    *,
    source_lock_sha256: str,
) -> Mapping[str, object]:
    evidence = _owned_terminal_archive_evidence(archive)
    manifest = _terminal_evidence_mapping(
        evidence["manifest.json"], label="manifest.json"
    )
    expected_manifest = {
        "schema_version": "1.0",
        "run_id": record.run_id,
        "site_id": record.site_id,
        "project": "nf-genome_to_diffraction",
        "profile": record.profile,
        "iteration": record.iteration,
        "commit": record.commit,
        "pixi_lock_sha256": source_lock_sha256,
        "source_snapshot_status": "immutable",
    }
    for field, expected in expected_manifest.items():
        if manifest.get(field) != expected:
            raise _terminal_evidence_error(
                f"manifest {field} does not match the owned immutable run"
            )
    helper_commit = manifest.get("nf_helper_commit")
    if not isinstance(helper_commit, str) or not COMMIT_PATTERN.fullmatch(
        helper_commit
    ):
        raise _terminal_evidence_error("manifest nf_helper_commit is invalid")
    for field in ("pixi_executable", "pixi_version"):
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip():
            raise _terminal_evidence_error(f"manifest {field} is absent")

    try:
        job_id = evidence["state/job-id"].decode("ascii").removesuffix("\n")
    except UnicodeDecodeError as error:
        raise _terminal_evidence_error("scheduler job ID is not ASCII") from error
    if not re.fullmatch(r"[0-9]+", job_id):
        raise _terminal_evidence_error("scheduler job ID is not canonical")

    result = _terminal_evidence_mapping(
        evidence["state/job-result.json"], label="state/job-result.json"
    )
    expected_result = {
        "schema_version": "1.0",
        "run_id": record.run_id,
        "profile": record.profile,
        "job_id": job_id,
        "standard_output": f"logs/slurm-{job_id}.out",
        "standard_error": f"logs/slurm-{job_id}.out",
        "application_log": f"logs/{record.profile}.log",
    }
    for field, expected in expected_result.items():
        if result.get(field) != expected:
            raise _terminal_evidence_error(
                f"job result {field} does not match the owned scheduler run"
            )
    _validated_terminal_timestamps(result)
    _validated_failure_outcome(result)
    _validated_terminal_inventory(result)
    return result


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
        value = load_json_document(path)
    except ContractLoadError as error:
        raise ValidationError(f"{label} is not valid strict JSON: {error}") from error
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
    adapter_version = manifest.get("adapter_version")
    if (
        adapter_version not in {"mr-seed-review-v2", "mr-seed-review-v3"}
        or manifest.get("score_gate") != expected_gate
        or summary.get("run_id") != record.run_id
        or summary.get("profile") != "p2-diverse"
        or summary.get("mr_seed_review_package_id") != package_id
        or summary.get("mr_seed_review_manifest_sha256") != manifest_sha256
    ):
        raise ValidationError("MR review evidence identity or policy does not match")
    if adapter_version == "mr-seed-review-v3" and (
        manifest.get("numeric_screen_excludes_candidates") is not False
        or manifest.get("approval_requires_explicit_human_decision") is not True
    ):
        raise ValidationError("MR review evidence identity or policy does not match")

    items = manifest.get("items")
    if not isinstance(items, list):
        raise ValidationError("MR review manifest items must be an array")
    if adapter_version == "mr-seed-review-v3":
        inspectable = [
            item
            for item in items
            if isinstance(item, Mapping) and item.get("inspectable_solution") is True
        ]
    else:
        inspectable = [
            item
            for item in items
            if isinstance(item, Mapping)
            and isinstance(item.get("copied_assets"), Mapping)
            and set(item["copied_assets"]) == set(_REVIEW_ASSET_BASENAMES)
        ]
    if not 1 <= len(inspectable) <= 25:
        raise ValidationError("MR review package must have 1..25 inspectable solutions")
    if adapter_version == "mr-seed-review-v3" and (
        manifest.get("inspectable_solution_count") != len(inspectable)
    ):
        raise ValidationError("inspectable review count differs from the manifest")

    expectations = {
        _REVIEW_MANIFEST_RELATIVE.as_posix(): manifest_sha256,
        _REVIEW_SUMMARY_RELATIVE.as_posix(): sha256_file(summary_path),
        _REVIEW_JOB_RESULT_RELATIVE.as_posix(): sha256_file(job_result_path),
    }
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping) or set(outputs) != set(
        _REVIEW_OUTPUT_BASENAMES
    ):
        raise ValidationError("MR review output inventory is incomplete")
    for key, basename in _REVIEW_OUTPUT_BASENAMES.items():
        record_value = outputs.get(key)
        if not isinstance(record_value, Mapping):
            raise ValidationError("MR review output inventory is invalid")
        digest = record_value.get("sha256")
        if (
            record_value.get("path") != basename
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValidationError("MR review output identity is invalid")
        archive_relative = (_REVIEW_MANIFEST_RELATIVE.parent / basename).as_posix()
        expectations[archive_relative] = digest
    solution_ids: list[str] = []
    for item in inspectable:
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
            raise ValidationError("inspectable MR review item identity is invalid")
        if set(copied_assets) != set(_REVIEW_ASSET_BASENAMES) or set(
            copied_sha256
        ) != set(_REVIEW_ASSET_BASENAMES):
            raise ValidationError("inspectable MR review asset set is incomplete")
        solution_ids.append(solution_id)
        for key, basename in _REVIEW_ASSET_BASENAMES.items():
            expected_local = f"assets/{solution_id}/{basename}"
            digest = copied_sha256.get(key)
            if (
                copied_assets.get(key) != expected_local
                or not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            ):
                raise ValidationError("inspectable MR review asset identity is invalid")
            archive_relative = (
                _REVIEW_MANIFEST_RELATIVE.parent / expected_local
            ).as_posix()
            if archive_relative in expectations:
                raise ValidationError("inspectable MR review asset path is duplicated")
            expectations[archive_relative] = digest
    return expectations, package_id, solution_ids, manifest_sha256


def _jsonl_mappings(path: Path, label: str) -> list[Mapping[str, object]]:
    records: list[Mapping[str, object]] = []
    try:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            value = parse_json_document(line, label=f"{path}:{line_number}")
            if not isinstance(value, Mapping):
                raise ValidationError(
                    f"{label} record {line_number} must be a JSON object"
                )
            records.append(value)
    except (OSError, UnicodeDecodeError, ContractLoadError) as error:
        raise ValidationError(f"{label} is not valid strict JSONL: {error}") from error
    if not records:
        raise ValidationError(f"{label} contains no records")
    return records


def _t12_review_asset_expectations(
    collected: Path,
    record: LocalRunRecord,
) -> tuple[dict[str, str], str, str, str, list[str]]:
    """Derive the exact T12 asset set from collected typed result checksums."""

    summary_path = _safe_local_evidence_file(collected, _T12_SUMMARY_RELATIVE)
    refinement_path = _safe_local_evidence_file(collected, _T12_REFINEMENT_RELATIVE)
    sequence_path = _safe_local_evidence_file(collected, _T12_SEQUENCE_RELATIVE)
    job_path = _safe_local_evidence_file(collected, _REVIEW_JOB_RESULT_RELATIVE)
    stage_path = _safe_local_evidence_file(collected, _T12_STAGE_MANIFEST_RELATIVE)
    summary = _json_mapping(summary_path, "T12 summary")
    job = _json_mapping(job_path, "T12 job result")
    stage = _json_mapping(stage_path, "T12 stage manifest")
    refinements = _jsonl_mappings(refinement_path, "T12 refinement results")
    sequences = _jsonl_mappings(sequence_path, "T12 sequence results")
    if not (
        job.get("run_id") == record.run_id
        and job.get("profile") == "t12"
        and job.get("failure_class") == FailureClass.SUCCESS
        and job.get("scheduler_state") == "COMPLETED"
        and job.get("exit_code") == 0
        and summary.get("run_id") == record.run_id
        and summary.get("profile") == "t12"
        and summary.get("candidate_count") == len(refinements)
        and summary.get("completed_refinement_count") == len(refinements)
        and summary.get("failed_refinement_count") == 0
        and summary.get("completed_sequence_count") == len(sequences)
        and summary.get("failed_sequence_count") == 0
        and summary.get("all_candidates_retained") is True
        and summary.get("all_resume_processes_cached") is True
        and stage.get("seed_count") == len(refinements)
        and 1 <= len(refinements) <= 25
        and len(refinements) == len(sequences)
    ):
        raise ValidationError(
            "T12 review assets require complete retained results and cached resume"
        )

    digest_pattern = re.compile(r"[0-9a-f]{64}")
    seed_pattern = re.compile(r"sol_[0-9a-f]{64}")
    refinement_by_seed: dict[str, Mapping[str, object]] = {}
    for result in refinements:
        seed = result.get("seed_solution_id")
        if (
            not isinstance(seed, str)
            or seed_pattern.fullmatch(seed) is None
            or seed in refinement_by_seed
            or result.get("execution_status")
            not in {"completed_success", "completed_warning"}
            or result.get("refined_model_path") != "brief_refine_001.pdb"
            or result.get("refined_mtz_path") != "brief_refine_001.mtz"
            or result.get("map_path") != "brief_refine_2mFo-DFc.ccp4"
            or result.get("difference_map_path") != "brief_refine_mFo-DFc.ccp4"
        ):
            raise ValidationError("T12 refinement result asset identity is invalid")
        refinement_by_seed[seed] = result
    sequence_by_seed: dict[str, Mapping[str, object]] = {}
    for result in sequences:
        seed = result.get("seed_solution_id")
        if (
            not isinstance(seed, str)
            or seed_pattern.fullmatch(seed) is None
            or seed in sequence_by_seed
            or result.get("execution_status")
            not in {"completed_hit", "completed_warning"}
            or result.get("output_model_path") != "sequence_from_map.pdb"
        ):
            raise ValidationError("T12 sequence result asset identity is invalid")
        sequence_by_seed[seed] = result
    if set(refinement_by_seed) != set(sequence_by_seed):
        raise ValidationError("T12 refinement and sequence seed identities differ")

    expectations: dict[str, str] = {}
    digest_fields = {
        "brief_refine_001.pdb": "refined_model_sha256",
        "brief_refine_001.mtz": "refined_mtz_sha256",
        "brief_refine_2mFo-DFc.ccp4": "map_sha256",
        "brief_refine_mFo-DFc.ccp4": "difference_map_sha256",
    }
    for seed in sorted(refinement_by_seed):
        refinement = refinement_by_seed[seed]
        sequence = sequence_by_seed[seed]
        for basename, field in digest_fields.items():
            digest = refinement.get(field)
            if not isinstance(digest, str) or digest_pattern.fullmatch(digest) is None:
                raise ValidationError("T12 refinement asset checksum is invalid")
            relative = f"artifacts/t12/t12_{seed}/{basename}"
            expectations[relative] = digest
        sequence_digest = sequence.get("output_model_sha256")
        if (
            not isinstance(sequence_digest, str)
            or digest_pattern.fullmatch(sequence_digest) is None
        ):
            raise ValidationError("T12 sequence asset checksum is invalid")
        expectations[f"artifacts/t12/t12_{seed}/sequence_from_map.pdb"] = (
            sequence_digest
        )
    input_digests = {
        _T12_SEQUENCE_GROUPS_RELATIVE: stage.get("sequence_groups_sha256"),
        _T12_SOURCE_RECORDS_RELATIVE: stage.get("source_records_sha256"),
        _T12_PREFLIGHT_RELATIVE: stage.get("preflight_sha256"),
    }
    for relative, digest in input_digests.items():
        if not isinstance(digest, str) or digest_pattern.fullmatch(digest) is None:
            raise ValidationError("T12 scientific-context checksum is invalid")
        expectations[relative.as_posix()] = digest
    if len(expectations) != (
        len(refinements) * len(_T12_ASSET_BASENAMES) + len(input_digests)
    ):
        raise ValidationError("T12 review asset inventory is incomplete")
    return (
        expectations,
        sha256_file(summary_path),
        sha256_file(refinement_path),
        sha256_file(sequence_path),
        sorted(refinement_by_seed),
    )


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
                _validate_inspectable_review_result(temporary_root / name, name)
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


def _validate_inspectable_review_result(path: Path, label: str) -> None:
    """Verify that one collected result has Coot-inspectable solution assets."""

    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise RemoteOperationError(
            f"inspectable review result must contain one record: {label}",
            failure_class=FailureClass.TRANSFER_FAILURE,
        )
    try:
        result = parse_json_document(lines[0], label=path)
    except ContractLoadError as error:
        raise RemoteOperationError(
            f"inspectable review result is invalid strict JSON: {label}: {error}",
            failure_class=FailureClass.TRANSFER_FAILURE,
        ) from error
    if not isinstance(result, Mapping):
        raise RemoteOperationError(
            f"inspectable review result is not an object: {label}",
            failure_class=FailureClass.TRANSFER_FAILURE,
        )
    if not (
        result.get("execution_status") in {"completed_hit", "completed_no_hit"}
        and isinstance(result.get("solution_coordinate_path"), str)
        and isinstance(result.get("output_mtz_path"), str)
    ):
        raise RemoteOperationError(
            f"review result is not an inspectable first-copy solution: {label}",
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
        raise _terminal_evidence_error("job-result.json is absent after collection")
    try:
        value = load_json_document(result_path)
    except ContractLoadError as error:
        raise _terminal_evidence_error(
            "job-result.json is invalid after collection"
        ) from error
    if not isinstance(value, Mapping):
        raise _terminal_evidence_error("job-result.json must be a JSON object")
    failure = _validated_failure_outcome(value)
    if failure is FailureClass.SUCCESS:
        return None
    exit_code = str(value["exit_code"])
    scheduler_state = str(value["scheduler_state"])
    diagnostic = _failure_log_digest(destination, value)
    return hashlib.sha256(
        f"{failure.value}\0{exit_code}\0{scheduler_state}\0{diagnostic}".encode()
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
