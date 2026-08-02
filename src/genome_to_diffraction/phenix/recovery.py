"""Requalify an installer-preserved Phenix tree after verifier correction.

This recovery boundary never runs an installer and never adopts an arbitrary
runtime. It accepts only the exact failed manifest and sibling quarantine name
created by :func:`install_phenix`, restores that tree atomically, reruns the
fixed command probes, and publishes a new manifest plus link only on success.
"""

import json
import logging
import os
import re
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.phenix.errors import (
    PhenixInstallationExistsError,
    PhenixRecoveryError,
    UnsafePhenixPathError,
)
from genome_to_diffraction.phenix.runtime import inspect_runtime, platform_record
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import PhenixInstallManifest
from genome_to_diffraction.time import utc_now

_LOGGER = logging.getLogger("genome_to_diffraction.phenix")
_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")
_GIT_SHA = re.compile(r"^[a-f0-9]{40}$")
_FAILED_SUFFIX = re.compile(r"^[a-f0-9]{32}$")


@dataclass(frozen=True)
class RecoveryRequest:
    """Inputs for one checksum-bound failed-installation recovery."""

    failed_prefix: Path
    installation_prefix: Path
    failed_manifest: Path
    failed_manifest_sha256: str
    recovered_manifest: Path
    expected_release: str
    expected_build: str
    tool_revision: str
    current_symlink: Path
    progress: bool = True
    command_timeout_seconds: float = 120.0


def _absolute(path: Path, *, name: str) -> Path:
    if not path.is_absolute():
        raise UnsafePhenixPathError(f"{name} must be absolute: {path}")
    return Path(os.path.abspath(path))


def _path_exists(path: Path) -> bool:
    """Return true for ordinary entries and dangling symlinks."""

    return os.path.lexists(path)


def _validate_digest(value: str) -> str:
    if _SHA256.fullmatch(value) is None:
        raise ValueError(
            "failed manifest SHA-256 must contain exactly 64 hexadecimal digits"
        )
    return value.lower()


def _load_failed_manifest(path: Path) -> PhenixInstallManifest:
    model = load_contract(path, "phenix-install-manifest", progress=False)
    if not isinstance(model, PhenixInstallManifest):
        raise AssertionError("phenix manifest registry returned the wrong model")
    if model.status != "failed":
        raise PhenixRecoveryError(
            f"recovery requires a failed Phenix manifest, found {model.status!r}"
        )
    return model


def _validate_paths(
    request: RecoveryRequest, manifest: PhenixInstallManifest
) -> tuple[Path, Path, Path, Path]:
    failed_prefix = _absolute(request.failed_prefix, name="failed prefix")
    prefix = _absolute(request.installation_prefix, name="installation prefix")
    recovered_manifest = _absolute(
        request.recovered_manifest, name="recovered manifest"
    )
    current_symlink = _absolute(request.current_symlink, name="current symlink")

    parent = prefix.parent.resolve(strict=True)
    if failed_prefix.parent.resolve(strict=True) != parent:
        raise UnsafePhenixPathError(
            "failed and restored Phenix prefixes must be direct siblings"
        )
    expected_stem = f".{prefix.name}.failed-"
    if (
        not failed_prefix.name.startswith(expected_stem)
        or _FAILED_SUFFIX.fullmatch(failed_prefix.name.removeprefix(expected_stem))
        is None
    ):
        raise UnsafePhenixPathError(
            "failed prefix does not match the installer quarantine naming policy"
        )
    failed_stat = os.lstat(failed_prefix)
    if stat.S_ISLNK(failed_stat.st_mode) or not stat.S_ISDIR(failed_stat.st_mode):
        raise UnsafePhenixPathError("failed prefix must be a real directory")
    parent_stat = parent.stat()
    if failed_stat.st_uid != os.geteuid() or parent_stat.st_uid != os.geteuid():
        raise UnsafePhenixPathError(
            "failed prefix and installation parent must be owned by the current user"
        )
    if failed_stat.st_dev != parent_stat.st_dev:
        raise UnsafePhenixPathError(
            "failed prefix and installation target must share one filesystem"
        )
    if _path_exists(prefix):
        raise PhenixInstallationExistsError(
            f"refusing to replace existing Phenix target: {prefix}"
        )
    if current_symlink.parent.resolve(strict=True) != parent:
        raise UnsafePhenixPathError(
            "current symlink must be a direct sibling of the installation prefix"
        )
    if _path_exists(current_symlink):
        raise PhenixInstallationExistsError(
            f"refusing to replace existing current link: {current_symlink}"
        )
    if _path_exists(recovered_manifest):
        raise PhenixInstallationExistsError(
            f"refusing to replace recovered manifest: {recovered_manifest}"
        )
    if Path(manifest.installation_prefix) != prefix:
        raise PhenixRecoveryError(
            "failed manifest installation prefix does not match the recovery target"
        )
    expected_environment = prefix / Path(manifest.phenix_env_sh).name
    if Path(manifest.phenix_env_sh) != expected_environment:
        raise PhenixRecoveryError(
            "failed manifest environment path does not match the recovery target"
        )
    return failed_prefix, prefix, recovered_manifest, current_symlink


def _update_current_link(path: Path, prefix: Path) -> None:
    temporary_link = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        os.symlink(prefix.name, temporary_link, target_is_directory=True)
        os.replace(temporary_link, path)
    finally:
        temporary_link.unlink(missing_ok=True)


def recover_failed_install(request: RecoveryRequest) -> PhenixInstallManifest:
    """Restore and requalify one exact installer-preserved Phenix tree.

    The failed manifest remains byte-for-byte unchanged. A distinct verified
    manifest is written only after all fixed probes pass. Verification failure
    atomically returns the tree to its original quarantine name.
    """

    failed_manifest = _absolute(request.failed_manifest, name="failed manifest")
    if not failed_manifest.is_file() or failed_manifest.is_symlink():
        raise FileNotFoundError(
            f"failed Phenix manifest is not a regular file: {failed_manifest}"
        )
    expected_digest = _validate_digest(request.failed_manifest_sha256)
    actual_digest = sha256_file(
        failed_manifest,
        progress=request.progress,
        description="Checksumming failed Phenix manifest",
        logger=_LOGGER,
    )
    if actual_digest != expected_digest:
        raise PhenixRecoveryError(
            "failed Phenix manifest SHA-256 mismatch: "
            f"expected {expected_digest}, found {actual_digest}"
        )
    manifest = _load_failed_manifest(failed_manifest)
    if _GIT_SHA.fullmatch(request.tool_revision) is None:
        raise ValueError("recovery tool revision must be a full lowercase Git SHA")
    if manifest.requested_release != request.expected_release:
        raise PhenixRecoveryError(
            "failed manifest release does not match the recovery expectation"
        )
    if manifest.requested_build != request.expected_build:
        raise PhenixRecoveryError(
            "failed manifest build does not match the recovery expectation"
        )
    if manifest.phenix_version != request.expected_build:
        raise PhenixRecoveryError(
            "failed manifest detected version does not match the expected build"
        )
    if manifest.phenix_env_sha256 is None:
        raise PhenixRecoveryError(
            "failed manifest lacks the installed phenix_env.sh checksum"
        )

    failed_prefix, prefix, recovered_manifest, current_symlink = _validate_paths(
        request, manifest
    )
    failed_environment = failed_prefix / Path(manifest.phenix_env_sh).name
    if not failed_environment.is_file() or failed_environment.is_symlink():
        raise PhenixRecoveryError(
            f"preserved phenix_env.sh is missing or unsafe: {failed_environment}"
        )
    environment_digest = sha256_file(failed_environment)
    if environment_digest != manifest.phenix_env_sha256:
        raise PhenixRecoveryError(
            "preserved phenix_env.sh checksum does not match the failed manifest"
        )
    current_platform = platform_record()
    if (
        current_platform.os != manifest.platform.os
        or current_platform.architecture != manifest.platform.architecture
    ):
        raise PhenixRecoveryError(
            "recovery host platform does not match the failed installation manifest"
        )

    verification_log = recovered_manifest.with_suffix(".verify.log")
    if _path_exists(verification_log):
        raise PhenixInstallationExistsError(
            f"refusing to replace recovery verification log: {verification_log}"
        )
    recovered_manifest.parent.mkdir(parents=True, exist_ok=True)
    lock_path = prefix.parent / f".{prefix.name}.recover.lock"
    try:
        lock_descriptor = os.open(
            lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
    except FileExistsError as error:
        raise PhenixRecoveryError(
            f"another Phenix recovery owns the lock: {lock_path}"
        ) from error
    with os.fdopen(lock_descriptor, "w", encoding="utf-8") as lock_handle:
        json.dump(
            {
                "failed_manifest_sha256": expected_digest,
                "failed_prefix": str(failed_prefix),
                "prefix": str(prefix),
                "started_at": utc_now().isoformat(),
            },
            lock_handle,
            sort_keys=True,
        )
        lock_handle.write("\n")
        lock_handle.flush()
        os.fsync(lock_handle.fileno())

    moved = False
    manifest_committed = False
    try:
        if sha256_file(failed_manifest) != expected_digest:
            raise PhenixRecoveryError(
                "failed Phenix manifest changed after initial validation"
            )
        os.rename(failed_prefix, prefix)
        moved = True
        inspection = inspect_runtime(
            prefix,
            expected_release=request.expected_release,
            expected_build=request.expected_build,
            progress=request.progress,
            timeout_seconds=request.command_timeout_seconds,
            verification_log=verification_log,
        )
        if sha256_file(failed_manifest) != expected_digest:
            raise PhenixRecoveryError(
                "failed Phenix manifest changed during runtime verification"
            )
        recovered = PhenixInstallManifest.model_validate(
            {
                **manifest.model_dump(mode="json"),
                "status": "verified",
                "phenix_version": inspection.phenix_version,
                "installation_prefix": str(prefix),
                "phenix_env_sh": str(prefix / Path(manifest.phenix_env_sh).name),
                "phenix_env_sha256": environment_digest,
                "required_commands": [
                    command.model_dump(mode="json") for command in inspection.commands
                ],
                "verification_log": str(verification_log),
                "current_symlink": str(current_symlink),
                "operator_notes": [
                    *manifest.operator_notes,
                    "Requalified from the installer-preserved failed tree; "
                    f"source manifest SHA-256 {expected_digest}; recovery tool "
                    f"revision {request.tool_revision}.",
                ],
                "warnings": [
                    "A prior verifier rejected documented non-zero Phenix help "
                    "statuses; the immutable failed manifest is retained at "
                    f"{failed_manifest} with SHA-256 {expected_digest}."
                ],
            }
        )
        atomic_write_json(recovered_manifest, recovered.model_dump(mode="json"))
        manifest_committed = True
        _update_current_link(current_symlink, prefix)
        _LOGGER.info(
            "recovered and verified preserved Phenix installation",
            extra={
                "failed_manifest_sha256": expected_digest,
                "manifest": str(recovered_manifest),
                "prefix": str(prefix),
            },
        )
        return recovered
    except BaseException:
        if moved and not manifest_committed:
            try:
                if _path_exists(prefix) and not _path_exists(failed_prefix):
                    os.rename(prefix, failed_prefix)
            except OSError as rollback_error:
                raise PhenixRecoveryError(
                    "Phenix recovery failed and the installation could not be "
                    f"returned to {failed_prefix}; inspect {prefix}"
                ) from rollback_error
        raise
    finally:
        lock_path.unlink(missing_ok=True)
