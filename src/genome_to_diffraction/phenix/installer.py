"""Checksum-gated, side-by-side installation of user-supplied Phenix.

The installer is never downloaded. Inputs include its expected SHA-256, a new
versioned absolute prefix, a temporary directory, and version expectations.
Outputs are preserved logs and a schema-valid installation manifest. Installer
or verification failures are loud and never fabricate a verified runtime.
"""

import logging
import os
import platform
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.phenix.errors import (
    PhenixInstallationExistsError,
    PhenixInstallCommandError,
    PhenixInstallerChecksumError,
    PhenixRuntimeVerificationError,
    UnsafePhenixPathError,
    UnsupportedPhenixPlatformError,
)
from genome_to_diffraction.phenix.runtime import (
    REQUIRED_COMMANDS,
    RuntimeInspection,
    inspect_runtime,
    platform_record,
)
from genome_to_diffraction.schemas.manifests import (
    PhenixCommandRecord,
    PhenixInstallManifest,
    SmokeTestStatus,
)
from genome_to_diffraction.time import utc_now

_LOGGER = logging.getLogger("genome_to_diffraction.phenix")
_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")
_GIB = 1024**3


@dataclass(frozen=True)
class InstallRequest:
    """Explicit inputs controlling one non-destructive Phenix installation."""

    installer: Path
    installer_sha256: str
    installation_prefix: Path
    expected_release: str
    temporary_directory: Path
    manifest_path: Path
    expected_build: str | None = None
    current_symlink: Path | None = None
    operator_notes: tuple[str, ...] = ()
    minimum_install_free_bytes: int = 15 * _GIB
    minimum_temporary_free_bytes: int = 25 * _GIB
    allow_home_root: bool = False
    progress: bool = True
    command_timeout_seconds: float = 120.0


def _validate_sha256(value: str) -> str:
    if _SHA256.fullmatch(value) is None:
        raise ValueError("installer SHA-256 must contain exactly 64 hexadecimal digits")
    return value.lower()


def _validate_absolute_directory(
    path: Path, *, name: str, allow_home_root: bool
) -> Path:
    if not path.is_absolute():
        raise UnsafePhenixPathError(f"{name} must be an absolute path: {path}")
    resolved = path.resolve()
    if resolved == Path("/"):
        raise UnsafePhenixPathError(f"{name} must not be the filesystem root")
    if resolved == Path.home().resolve() and not allow_home_root:
        raise UnsafePhenixPathError(
            f"{name} must not be the home-directory root without --allow-home-root"
        )
    return resolved


def _versioned_prefix(request: InstallRequest) -> Path:
    prefix = _validate_absolute_directory(
        request.installation_prefix,
        name="installation prefix",
        allow_home_root=request.allow_home_root,
    )
    expected_component = request.expected_build or request.expected_release
    allowed_prefixes = (
        f"phenix-{expected_component}",
        f"phenix_v{expected_component}",
    )
    if not prefix.name.startswith(allowed_prefixes):
        raise UnsafePhenixPathError(
            "installation prefix must be versioned and begin with one of "
            f"{allowed_prefixes!r}"
        )
    return prefix


def _validate_platform() -> None:
    system = platform.system()
    architecture = platform.machine().lower()
    if system == "Linux":
        if architecture not in {"x86_64", "amd64"}:
            raise UnsupportedPhenixPlatformError(
                f"unsupported Linux architecture for Phenix: {architecture}"
            )
        libc_name, libc_version = platform.libc_ver()
        if libc_name != "glibc" or not libc_version:
            raise UnsupportedPhenixPlatformError(
                "Linux Phenix bootstrap requires a detectable glibc runtime"
            )
        major, minor, *_ = (int(part) for part in libc_version.split("."))
        if (major, minor) < (2, 17):
            raise UnsupportedPhenixPlatformError(
                f"Phenix requires glibc 2.17 or newer; detected {libc_version}"
            )
        return
    if system == "Darwin" and architecture in {"x86_64", "arm64", "aarch64"}:
        version = platform.mac_ver()[0]
        if not version:
            raise UnsupportedPhenixPlatformError("macOS version could not be detected")
        major, minor, *_ = (int(part) for part in version.split("."))
        minimum = (11, 0) if architecture in {"arm64", "aarch64"} else (10, 13)
        if (major, minor) < minimum:
            required = ".".join(str(part) for part in minimum)
            raise UnsupportedPhenixPlatformError(
                f"Phenix on {architecture} requires macOS {required} or newer"
            )
        return
    raise UnsupportedPhenixPlatformError(
        f"unsupported Phenix platform: {system} {architecture}"
    )


def _check_storage(path: Path, required_bytes: int, *, purpose: str) -> None:
    if required_bytes < 0:
        raise ValueError("minimum free-space requirements must not be negative")
    free_bytes = shutil.disk_usage(path).free
    if free_bytes < required_bytes:
        raise UnsafePhenixPathError(
            f"insufficient free space for {purpose}: require {required_bytes} bytes, "
            f"found {free_bytes} bytes at {path}"
        )


def _check_executable_temporary_directory(path: Path) -> None:
    """Confirm that the chosen temporary filesystem permits direct execution."""

    descriptor, probe_name = tempfile.mkstemp(prefix="phenix-exec-probe-", dir=path)
    probe = Path(probe_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("#!/usr/bin/env sh\nexit 0\n")
        probe.chmod(0o700)
        completed = subprocess.run(
            [probe],
            check=False,
            capture_output=True,
            timeout=10,
        )
        if completed.returncode != 0:
            raise UnsafePhenixPathError(
                f"temporary directory does not permit executable files: {path}"
            )
    except OSError as error:
        raise UnsafePhenixPathError(
            f"temporary directory does not permit executable files: {path}: {error}"
        ) from error
    finally:
        probe.unlink(missing_ok=True)


def _default_command_records(prefix: Path) -> tuple[PhenixCommandRecord, ...]:
    return tuple(
        PhenixCommandRecord(
            name=name,
            path=str(prefix / "bin" / name),
            smoke_test_status=SmokeTestStatus.NOT_RUN,
            version_text=None,
        )
        for name in REQUIRED_COMMANDS
    )


def _manifest(
    request: InstallRequest,
    prefix: Path,
    installer_digest: str,
    *,
    status: str,
    detected_version: str,
    commands: tuple[PhenixCommandRecord, ...],
    install_log: Path,
    verification_log: Path,
    warnings: tuple[str, ...] = (),
) -> PhenixInstallManifest:
    environment_file = prefix / "phenix_env.sh"
    environment_digest = (
        sha256_file(environment_file) if environment_file.is_file() else None
    )
    return PhenixInstallManifest.model_validate(
        {
            "schema_version": "1.0",
            "status": status,
            "requested_release": request.expected_release,
            "requested_build": request.expected_build,
            "phenix_version": detected_version,
            "installation_prefix": str(prefix),
            "phenix_env_sh": str(environment_file),
            "phenix_env_sha256": environment_digest,
            "installer_basename": request.installer.name,
            "installer_sha256": installer_digest,
            "platform": platform_record().model_dump(mode="json"),
            "installed_at": utc_now(),
            "required_commands": [
                command.model_dump(mode="json") for command in commands
            ],
            "install_log": str(install_log),
            "verification_log": str(verification_log),
            "current_symlink": (
                str(request.current_symlink.absolute())
                if request.current_symlink is not None
                else None
            ),
            "operator_notes": list(request.operator_notes),
            "warnings": list(warnings),
        }
    )


def _write_manifest(path: Path, manifest: PhenixInstallManifest) -> None:
    atomic_write_json(path, manifest.model_dump(mode="json"))
    _LOGGER.info(
        "wrote Phenix installation manifest",
        extra={"manifest": str(path), "status": manifest.status},
    )


def _run_installer(
    request: InstallRequest, prefix: Path, staging_directory: Path, log_path: Path
) -> int:
    bash = shutil.which("bash")
    if bash is None:
        raise UnsupportedPhenixPlatformError("bash is required by the Phenix installer")
    command = [bash, str(request.installer), "-b", "-p", str(prefix)]
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "TMPDIR": str(staging_directory),
    }
    for name in ("HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM"):
        value = os.environ.get(name)
        if value is not None:
            environment[name] = value
    _LOGGER.info(
        "starting official Phenix batch installer",
        extra={
            "command": command,
            "install_log": str(log_path),
            "temporary_directory": str(staging_directory),
        },
    )
    with log_path.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=environment,
            text=True,
        )
        if process.stdout is None:
            raise AssertionError("installer stdout pipe was not created")
        with tqdm(
            total=1,
            desc="Installing Phenix",
            unit="installation",
            disable=not request.progress,
        ) as progress_bar:
            for line in process.stdout:
                log_handle.write(line)
                log_handle.flush()
                _LOGGER.debug(
                    "Phenix installer output", extra={"line": line.rstrip("\n")}
                )
            returncode = process.wait()
            if returncode == 0:
                progress_bar.update(1)
    _LOGGER.info("Phenix installer finished", extra={"exit_status": returncode})
    return returncode


def _preserve_failed_target(prefix: Path) -> Path | None:
    if not prefix.exists():
        return None
    failed_path = prefix.parent / f".{prefix.name}.failed-{uuid.uuid4().hex}"
    os.replace(prefix, failed_path)
    _LOGGER.warning(
        "preserved failed Phenix installation",
        extra={"failed_installation": str(failed_path)},
    )
    return failed_path


def _validate_current_symlink(path: Path | None, *, allow_home_root: bool) -> None:
    if path is None:
        return
    resolved_parent = _validate_absolute_directory(
        path.parent,
        name="current symlink parent",
        allow_home_root=allow_home_root,
    )
    if not resolved_parent.is_dir() or not os.access(resolved_parent, os.W_OK):
        raise UnsafePhenixPathError(
            f"current symlink parent is not a writable directory: {resolved_parent}"
        )
    if path.exists() and not path.is_symlink():
        raise PhenixInstallationExistsError(
            f"refusing to replace non-symlink current path: {path}"
        )


def _update_current_symlink(path: Path, prefix: Path) -> None:
    temporary_link = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        os.symlink(prefix, temporary_link, target_is_directory=True)
        os.replace(temporary_link, path)
    finally:
        temporary_link.unlink(missing_ok=True)
    _LOGGER.info(
        "updated current Phenix symlink",
        extra={"current_symlink": str(path), "target": str(prefix)},
    )


def install_phenix(request: InstallRequest) -> PhenixInstallManifest:
    """Install, verify, and record one new external Phenix runtime.

    The official batch command is ``bash INSTALLER -b -p PREFIX``. The installer
    file digest is the input identity. Existing installations are never removed or
    overwritten; failed new targets are renamed for forensic inspection.
    """

    installer = request.installer.resolve()
    if not installer.is_file() or not os.access(installer, os.R_OK):
        raise FileNotFoundError(f"Phenix installer is not a readable file: {installer}")
    expected_digest = _validate_sha256(request.installer_sha256)
    _LOGGER.info(
        "checksumming user-supplied Phenix installer",
        extra={
            "installer_basename": installer.name,
            "size_bytes": installer.stat().st_size,
        },
    )
    actual_digest = sha256_file(
        installer,
        progress=request.progress,
        description="Checksumming Phenix installer",
        logger=_LOGGER,
    )
    if actual_digest != expected_digest:
        raise PhenixInstallerChecksumError(
            "installer SHA-256 mismatch: "
            f"expected {expected_digest}, found {actual_digest}"
        )

    prefix = _versioned_prefix(request)
    temporary_directory = _validate_absolute_directory(
        request.temporary_directory,
        name="temporary directory",
        allow_home_root=request.allow_home_root,
    )
    _validate_platform()
    if prefix.exists() or prefix.is_symlink():
        raise PhenixInstallationExistsError(
            f"versioned Phenix installation already exists: {prefix}"
        )
    if request.manifest_path.exists():
        raise PhenixInstallationExistsError(
            f"refusing to replace existing Phenix manifest: {request.manifest_path}"
        )
    if not prefix.parent.is_dir() or not os.access(prefix.parent, os.W_OK):
        raise UnsafePhenixPathError(
            f"installation parent is not a writable directory: {prefix.parent}"
        )
    if not temporary_directory.is_dir() or not os.access(
        temporary_directory, os.W_OK | os.X_OK
    ):
        raise UnsafePhenixPathError(
            f"temporary directory is not writable/searchable: {temporary_directory}"
        )
    _check_executable_temporary_directory(temporary_directory)
    _check_storage(
        prefix.parent,
        request.minimum_install_free_bytes,
        purpose="Phenix installation",
    )
    _check_storage(
        temporary_directory,
        request.minimum_temporary_free_bytes,
        purpose="Phenix temporary extraction",
    )
    _validate_current_symlink(
        request.current_symlink, allow_home_root=request.allow_home_root
    )

    request.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    install_log = request.manifest_path.with_suffix(".install.log")
    verification_log = request.manifest_path.with_suffix(".verify.log")
    existing_logs = [path for path in (install_log, verification_log) if path.exists()]
    if existing_logs:
        raise PhenixInstallationExistsError(
            "refusing to replace existing Phenix logs: "
            + ", ".join(str(path) for path in existing_logs)
        )
    staging_directory = Path(
        tempfile.mkdtemp(prefix="phenix-install-", dir=temporary_directory)
    )
    _LOGGER.info(
        "created private Phenix installer staging directory",
        extra={"staging_directory": str(staging_directory)},
    )
    try:
        returncode = _run_installer(request, prefix, staging_directory, install_log)
        if returncode != 0:
            error = PhenixInstallCommandError(returncode, str(install_log))
            failed_path = _preserve_failed_target(prefix)
            warning = str(error)
            if failed_path is not None:
                warning = f"{warning}; partial target preserved at {failed_path}"
            manifest = _manifest(
                request,
                prefix,
                actual_digest,
                status="failed",
                detected_version="undetected",
                commands=_default_command_records(prefix),
                install_log=install_log,
                verification_log=verification_log,
                warnings=(warning,),
            )
            _write_manifest(request.manifest_path, manifest)
            raise error

        inspection: RuntimeInspection
        try:
            inspection = inspect_runtime(
                prefix,
                expected_release=request.expected_release,
                expected_build=request.expected_build,
                progress=request.progress,
                timeout_seconds=request.command_timeout_seconds,
                verification_log=verification_log,
            )
        except PhenixRuntimeVerificationError as error:
            commands = error.commands or _default_command_records(prefix)
            detected_version = error.detected_version or "undetected"
            manifest = _manifest(
                request,
                prefix,
                actual_digest,
                status="failed",
                detected_version=detected_version,
                commands=commands,
                install_log=install_log,
                verification_log=verification_log,
                warnings=(str(error),),
            )
            _write_manifest(request.manifest_path, manifest)
            _preserve_failed_target(prefix)
            raise

        manifest = _manifest(
            request,
            prefix,
            actual_digest,
            status="verified",
            detected_version=inspection.phenix_version,
            commands=inspection.commands,
            install_log=install_log,
            verification_log=verification_log,
        )
        _write_manifest(request.manifest_path, manifest)
        if request.current_symlink is not None:
            _update_current_symlink(request.current_symlink, prefix)
        return manifest
    finally:
        shutil.rmtree(staging_directory, ignore_errors=True)
