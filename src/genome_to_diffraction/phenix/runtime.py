"""Verify and execute an external Phenix runtime in an isolated child shell.

Inputs are a versioned installation prefix or a schema-valid installation
manifest. Outputs are command-resolution records and optional verification logs.
Failures are infrastructure errors; scientific no-hit states are not produced
here. The cache/provenance key is the manifest plus ``phenix_env.sh`` checksum.
"""

import json
import logging
import os
import platform
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_text, sha256_file
from genome_to_diffraction.phenix.errors import PhenixRuntimeVerificationError
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    PhenixCommandRecord,
    PhenixInstallManifest,
    PlatformRecord,
    SmokeTestStatus,
)

_LOGGER = logging.getLogger("genome_to_diffraction.phenix")

REQUIRED_COMMANDS = (
    "phenix.xtriage",
    "phenix.phaser",
    "phenix.process_predicted_model",
    "phenix.refine",
    "phenix.sequence_from_map",
    "phenix.maps",
    "phenix.reflection_file_converter",
)


@dataclass(frozen=True)
class _CommandProbe:
    """One side-effect-free command probe and its accepted help convention."""

    arguments: tuple[str, ...] = ("--help",)
    accepted_nonzero_exit: int | None = None
    required_nonzero_markers: tuple[str, ...] = ()


_DEFAULT_COMMAND_PROBE = _CommandProbe()
_COMMAND_PROBES = {
    "phenix.xtriage": _CommandProbe(
        accepted_nonzero_exit=1,
        required_nonzero_markers=(
            "Usage:",
            "phenix.xtriage [options] reflection_file parameters",
        ),
    ),
    "phenix.phaser": _CommandProbe(
        accepted_nonzero_exit=1,
        required_nonzero_markers=(
            "Usage:",
            "phenix.phaser is a multi-function command:",
        ),
    ),
    "phenix.maps": _CommandProbe(
        accepted_nonzero_exit=1,
        required_nonzero_markers=(
            "phenix.maps: a command line tool to compute various maps",
        ),
    ),
}
_FORBIDDEN_PROBE_MARKERS = (
    "Traceback (most recent call last)",
    "ModuleNotFoundError",
    "ImportError",
    "dyld:",
    "dyld[",
    "Library not loaded:",
    "Symbol not found:",
    "error while loading shared libraries:",
    "cannot open shared object file:",
)


@dataclass(frozen=True)
class RuntimeInspection:
    """Detected environment and smoke-test results for one Phenix runtime."""

    phenix_version: str
    phenix_path: Path
    phenix_prefix: Path
    commands: tuple[PhenixCommandRecord, ...]


def _evaluate_command_probe(
    probe: _CommandProbe,
    *,
    returncode: int,
    output: str,
) -> tuple[bool, str]:
    """Validate one probe without treating arbitrary non-zero output as help."""

    forbidden = next(
        (marker for marker in _FORBIDDEN_PROBE_MARKERS if marker in output), None
    )
    if forbidden is not None:
        return False, f"forbidden failure marker present: {forbidden}"
    if returncode == 0:
        return True, "probe exited successfully"
    if returncode != probe.accepted_nonzero_exit:
        return False, f"unexpected probe exit status: {returncode}"
    missing_markers = tuple(
        marker for marker in probe.required_nonzero_markers if marker not in output
    )
    if missing_markers:
        return False, "accepted non-zero help signature missing: " + ", ".join(
            repr(marker) for marker in missing_markers
        )
    return True, "accepted command-specific non-zero help convention"


def platform_record() -> PlatformRecord:
    """Return reproducible platform metadata without importing Phenix Python."""

    system = platform.system()
    architecture = platform.machine()
    libc_name, libc_version = platform.libc_ver()
    glibc = libc_version if system == "Linux" and libc_name == "glibc" else None
    os_version = platform.mac_ver()[0] if system == "Darwin" else platform.release()
    return PlatformRecord(
        os=system,
        architecture=architecture,
        glibc=glibc,
        os_version=os_version or None,
    )


def _clean_child_environment() -> dict[str, str]:
    """Build a minimal inherited environment for an isolated Phenix shell."""

    environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    for name in ("HOME", "USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL", "TERM"):
        value = os.environ.get(name)
        if value is not None:
            environment[name] = value
    return environment


def _bash() -> str:
    executable = shutil.which("bash")
    if executable is None:
        raise PhenixRuntimeVerificationError("bash is required to source phenix_env.sh")
    return executable


def _child_shell(
    environment_file: Path,
    arguments: Sequence[str],
    *,
    timeout_seconds: float | None,
    capture_output: bool,
    working_directory: Path | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Source exactly one environment file and execute one argument array."""

    script = 'set -eo pipefail\nsource "$1"\nshift\nexec "$@"'
    return subprocess.run(
        [
            _bash(),
            "--noprofile",
            "--norc",
            "-c",
            script,
            "genome-to-diffraction-phenix-child",
            str(environment_file),
            *arguments,
        ],
        check=False,
        capture_output=capture_output,
        cwd=working_directory,
        env=_clean_child_environment(),
        timeout=timeout_seconds,
    )


def _read_environment(
    environment_file: Path, timeout_seconds: float
) -> tuple[str, ...]:
    script = (
        'source "$1" 1>&2 || exit $?\n'
        'printf "%s\\0%s\\0%s\\0" "${PHENIX-}" "${PHENIX_PREFIX-}" '
        '"${PHENIX_VERSION-}"'
    )
    completed = subprocess.run(
        [
            _bash(),
            "--noprofile",
            "--norc",
            "-c",
            script,
            "genome-to-diffraction-phenix-environment",
            str(environment_file),
        ],
        check=False,
        capture_output=True,
        env=_clean_child_environment(),
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        diagnostic = completed.stderr.decode("utf-8", errors="replace").strip()
        raise PhenixRuntimeVerificationError(
            "phenix_env.sh could not be sourced in an isolated child shell"
            + (f": {diagnostic}" if diagnostic else "")
        )
    values = tuple(item.decode("utf-8") for item in completed.stdout.split(b"\0")[:-1])
    if len(values) != 3 or any(not value for value in values):
        raise PhenixRuntimeVerificationError(
            "phenix_env.sh must define PHENIX, PHENIX_PREFIX, and PHENIX_VERSION"
        )
    return values


def _version_matches(detected: str, release: str, exact_build: str | None) -> bool:
    if exact_build is not None:
        return detected == exact_build
    return detected == release or detected.startswith((f"{release}-", f"{release}."))


def inspect_runtime(
    installation_prefix: Path,
    *,
    expected_release: str,
    expected_build: str | None = None,
    progress: bool = True,
    timeout_seconds: float = 120.0,
    verification_log: Path | None = None,
) -> RuntimeInspection:
    """Resolve and smoke-test required Phenix commands using ``--help``.

    The external command requirement is Phenix release 2.1 (or the explicitly
    supplied build). A failure in any command fails the runtime as infrastructure.
    All help output is retained in ``verification_log`` when provided.
    """

    prefix = installation_prefix.resolve()
    environment_file = prefix / "phenix_env.sh"
    if not environment_file.is_file() or not os.access(environment_file, os.R_OK):
        raise PhenixRuntimeVerificationError(
            f"readable phenix_env.sh not found at {environment_file}"
        )
    detected_phenix, detected_prefix, detected_version = _read_environment(
        environment_file, timeout_seconds
    )
    if Path(detected_phenix).resolve() != prefix:
        raise PhenixRuntimeVerificationError(
            f"PHENIX resolves to {detected_phenix}, expected {prefix}",
            detected_version=detected_version,
        )
    if Path(detected_prefix).resolve() != prefix:
        raise PhenixRuntimeVerificationError(
            f"PHENIX_PREFIX resolves to {detected_prefix}, expected {prefix}",
            detected_version=detected_version,
        )
    if not _version_matches(detected_version, expected_release, expected_build):
        expectation = expected_build or f"release family {expected_release}"
        raise PhenixRuntimeVerificationError(
            f"detected PHENIX_VERSION {detected_version!r}, expected {expectation}",
            detected_version=detected_version,
        )

    _LOGGER.info(
        "verifying Phenix commands",
        extra={
            "command_count": len(REQUIRED_COMMANDS),
            "phenix_version": detected_version,
            "prefix": str(prefix),
        },
    )
    records: list[PhenixCommandRecord] = []
    log_sections: list[str] = []
    for command in tqdm(
        REQUIRED_COMMANDS,
        desc="Verifying Phenix",
        unit="command",
        disable=not progress,
    ):
        probe = _COMMAND_PROBES.get(command, _DEFAULT_COMMAND_PROBE)
        probe_arguments = list(probe.arguments)
        resolve_script = 'source "$1" 1>&2 || exit $?\ncommand -v -- "$2"'
        resolution = subprocess.run(
            [
                _bash(),
                "--noprofile",
                "--norc",
                "-c",
                resolve_script,
                "genome-to-diffraction-phenix-resolve",
                str(environment_file),
                command,
            ],
            check=False,
            capture_output=True,
            env=_clean_child_environment(),
            timeout=timeout_seconds,
        )
        resolved_text = resolution.stdout.decode("utf-8", errors="replace").strip()
        resolved_path = Path(resolved_text).resolve() if resolved_text else None
        if (
            resolution.returncode != 0
            or resolved_path is None
            or not resolved_path.is_file()
            or not resolved_path.is_relative_to(prefix)
        ):
            records.append(
                PhenixCommandRecord(
                    name=command,
                    path=resolved_text,
                    smoke_test_status=SmokeTestStatus.FAILED,
                    version_text=detected_version,
                )
            )
            log_sections.append(
                f"## {command}\nprobe_args={json.dumps(probe_arguments)}\n"
                "exit=not_run\n"
                "result=failed\n"
                "reason=resolution failed or escaped installation prefix\n"
            )
            continue
        completed = _child_shell(
            environment_file,
            [str(resolved_path), *probe.arguments],
            timeout_seconds=timeout_seconds,
            capture_output=True,
        )
        output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
        passed, reason = _evaluate_command_probe(
            probe,
            returncode=completed.returncode,
            output=output,
        )
        log_sections.append(
            f"## {command}\npath={resolved_path}\n"
            f"probe_args={json.dumps(probe_arguments)}\n"
            f"exit={completed.returncode}\n"
            f"result={'passed' if passed else 'failed'}\n"
            f"reason={reason}\n{output}\n"
        )
        status = SmokeTestStatus.PASSED if passed else SmokeTestStatus.FAILED
        records.append(
            PhenixCommandRecord(
                name=command,
                path=str(resolved_path),
                smoke_test_status=status,
                version_text=detected_version,
            )
        )
        _LOGGER.info(
            "Phenix command smoke test finished",
            extra={
                "command": command,
                "probe_arguments": probe_arguments,
                "exit_status": completed.returncode,
                "probe_passed": passed,
                "probe_reason": reason,
            },
        )

    if verification_log is not None:
        atomic_write_text(verification_log, "\n".join(log_sections))
    failed = [
        record.name
        for record in records
        if record.smoke_test_status is not SmokeTestStatus.PASSED
    ]
    if failed:
        raise PhenixRuntimeVerificationError(
            "required Phenix commands failed verification: " + ", ".join(failed),
            commands=records,
            detected_version=detected_version,
        )
    return RuntimeInspection(
        phenix_version=detected_version,
        phenix_path=Path(detected_phenix).resolve(),
        phenix_prefix=Path(detected_prefix).resolve(),
        commands=tuple(records),
    )


def validate_manifest_environment(manifest_path: Path) -> PhenixInstallManifest:
    """Validate a verified manifest and its immutable environment checksum."""

    model = load_contract(manifest_path, "phenix-install-manifest", progress=False)
    if not isinstance(model, PhenixInstallManifest):
        raise AssertionError("phenix manifest registry returned the wrong model")
    if model.status != "verified":
        raise PhenixRuntimeVerificationError(
            f"Phenix manifest status is {model.status!r}, not 'verified'"
        )
    prefix = Path(model.installation_prefix)
    environment_file = Path(model.phenix_env_sh)
    if not prefix.is_absolute() or not environment_file.is_absolute():
        raise PhenixRuntimeVerificationError(
            "installation_prefix and phenix_env_sh must be absolute paths"
        )
    resolved_prefix = prefix.resolve()
    resolved_environment = environment_file.resolve()
    if not resolved_environment.is_relative_to(resolved_prefix):
        raise PhenixRuntimeVerificationError(
            "phenix_env.sh escapes the manifest installation prefix"
        )
    if not resolved_environment.is_file():
        raise PhenixRuntimeVerificationError(
            f"manifest environment file is missing: {resolved_environment}"
        )
    if model.phenix_env_sha256 is None:
        raise PhenixRuntimeVerificationError(
            "verified manifest does not record phenix_env_sha256"
        )
    actual_digest = sha256_file(resolved_environment)
    if actual_digest != model.phenix_env_sha256:
        raise PhenixRuntimeVerificationError(
            "phenix_env.sh checksum does not match the installation manifest"
        )
    return model


def verify_manifest(
    manifest_path: Path,
    *,
    progress: bool = True,
    timeout_seconds: float = 120.0,
    verification_log: Path | None = None,
) -> RuntimeInspection:
    """Revalidate a recorded runtime without modifying its installation."""

    manifest = validate_manifest_environment(manifest_path)
    expected_release = manifest.requested_release or manifest.phenix_version
    expected_build = manifest.requested_build
    return inspect_runtime(
        Path(manifest.installation_prefix),
        expected_release=expected_release,
        expected_build=expected_build,
        progress=progress,
        timeout_seconds=timeout_seconds,
        verification_log=verification_log,
    )


def execute_from_manifest(
    manifest_path: Path,
    arguments: Sequence[str],
    *,
    environment_overrides: Mapping[str, str] | None = None,
) -> int:
    """Execute one exact argument array and return the Phenix command exit status."""

    if not arguments:
        raise ValueError("a Phenix command and optional arguments are required")
    if environment_overrides:
        raise ValueError("environment overrides are not supported at this boundary")
    manifest = validate_manifest_environment(manifest_path)
    environment_file = Path(manifest.phenix_env_sh).resolve()
    _LOGGER.info(
        "executing isolated Phenix command",
        extra={"command": arguments[0], "manifest": str(manifest_path)},
    )
    completed = _child_shell(
        environment_file,
        list(arguments),
        timeout_seconds=None,
        capture_output=False,
    )
    _LOGGER.info(
        "isolated Phenix command finished",
        extra={"command": arguments[0], "exit_status": completed.returncode},
    )
    return completed.returncode


def capture_from_manifest(
    manifest_path: Path,
    arguments: Sequence[str],
    *,
    working_directory: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[bytes]:
    """Run a verified recorded Phenix command and capture its byte streams.

    The executable is replaced with the absolute, previously verified path from
    the manifest. This boundary is used by parsers that must preserve and inspect
    external-tool logs without modifying the parent Pixi environment.
    """

    if not arguments:
        raise ValueError("a Phenix command and optional arguments are required")
    manifest = validate_manifest_environment(manifest_path)
    requested = arguments[0]
    command = next(
        (record for record in manifest.required_commands if record.name == requested),
        None,
    )
    if command is None or command.smoke_test_status is not SmokeTestStatus.PASSED:
        raise PhenixRuntimeVerificationError(
            f"Phenix command is not verified in the manifest: {requested}"
        )
    executable = Path(command.path).resolve(strict=True)
    prefix = Path(manifest.installation_prefix).resolve(strict=True)
    if not executable.is_file() or not executable.is_relative_to(prefix):
        raise PhenixRuntimeVerificationError(
            f"verified Phenix command escapes installation prefix: {requested}"
        )
    working_directory.mkdir(parents=True, exist_ok=True)
    resolved_arguments = [str(executable), *arguments[1:]]
    _LOGGER.info(
        "executing captured Phenix command",
        extra={
            "command": requested,
            "arguments": list(arguments[1:]),
            "working_directory": str(working_directory),
        },
    )
    completed = _child_shell(
        Path(manifest.phenix_env_sh).resolve(strict=True),
        resolved_arguments,
        timeout_seconds=timeout_seconds,
        capture_output=True,
        working_directory=working_directory,
    )
    _LOGGER.info(
        "captured Phenix command finished",
        extra={"command": requested, "exit_status": completed.returncode},
    )
    return completed
