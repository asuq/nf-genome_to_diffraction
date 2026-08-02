"""Tests for checksum-bound recovery of installer-preserved Phenix trees."""

import hashlib
import json
import shlex
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.phenix.errors import (
    PhenixRecoveryError,
    PhenixRuntimeVerificationError,
    UnsafePhenixPathError,
)
from genome_to_diffraction.phenix.recovery import (
    RecoveryRequest,
    recover_failed_install,
)
from genome_to_diffraction.phenix.runtime import (
    REQUIRED_COMMANDS,
    platform_record,
    validate_manifest_environment,
)
from genome_to_diffraction.schemas.manifests import (
    PhenixCommandRecord,
    PhenixInstallManifest,
    SmokeTestStatus,
)
from genome_to_diffraction.time import utc_now


def _command_script(command: str, *, broken: bool = False) -> str:
    if broken:
        body = (
            "printf 'Traceback (most recent call last):\\n' >&2\n"
            "printf 'ImportError: broken runtime\\n' >&2\n"
            "exit 1"
        )
    elif command == "phenix.xtriage":
        body = (
            "printf 'Usage:\\n'\n"
            "printf 'phenix.xtriage [options] reflection_file parameters [...]\\n'\n"
            "exit 1"
        )
    elif command == "phenix.phaser":
        body = (
            "printf 'Usage:\\n'\n"
            "printf 'phenix.phaser is a multi-function command:\\n'\n"
            "exit 1"
        )
    elif command == "phenix.maps":
        body = (
            "printf 'phenix.maps: a command line tool to compute various maps'\n"
            "printf ' and save them.\\n'\n"
            "exit 1"
        )
    else:
        body = f"printf 'usage: {command} [options]\\n'\nexit 0"
    return f"#!/usr/bin/env bash\nset -euo pipefail\n{body}\n"


def _recovery_fixture(
    tmp_path: Path,
    *,
    broken_command: str | None = None,
) -> tuple[RecoveryRequest, Path]:
    parent = tmp_path / "Phenix installations"
    parent.mkdir()
    prefix = parent / "phenix-2.1-9999"
    failed_prefix = parent / f".{prefix.name}.failed-{'a' * 32}"
    binary_directory = failed_prefix / "bin"
    binary_directory.mkdir(parents=True)
    environment = failed_prefix / "phenix_env.sh"
    quoted_prefix = shlex.quote(str(prefix))
    quoted_binary_directory = shlex.quote(str(prefix / "bin"))
    environment.write_text(
        f"export PHENIX={quoted_prefix}\n"
        f"export PHENIX_PREFIX={quoted_prefix}\n"
        "export PHENIX_VERSION=2.1-9999\n"
        f"export PATH={quoted_binary_directory}:$PATH\n",
        encoding="utf-8",
    )
    for command in REQUIRED_COMMANDS:
        executable = binary_directory / command
        executable.write_text(
            _command_script(command, broken=command == broken_command),
            encoding="utf-8",
        )
        executable.chmod(0o755)

    failed_manifest = tmp_path / "phenix failed.json"
    model = PhenixInstallManifest(
        schema_version="1.0",
        status="failed",
        requested_release="2.1",
        requested_build="2.1-9999",
        phenix_version="2.1-9999",
        installation_prefix=str(prefix),
        phenix_env_sh=str(prefix / "phenix_env.sh"),
        phenix_env_sha256=hashlib.sha256(environment.read_bytes()).hexdigest(),
        installer_basename="Phenix-test.sh",
        installer_sha256="1" * 64,
        platform=platform_record(),
        installed_at=utc_now(),
        required_commands=tuple(
            PhenixCommandRecord(
                name=command,
                path=str(prefix / "bin" / command),
                smoke_test_status=SmokeTestStatus.FAILED,
                version_text="2.1-9999",
            )
            for command in REQUIRED_COMMANDS
        ),
        warnings=("prior verifier rejected the runtime",),
    )
    failed_manifest.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    failed_digest = hashlib.sha256(failed_manifest.read_bytes()).hexdigest()
    request = RecoveryRequest(
        failed_prefix=failed_prefix,
        installation_prefix=prefix,
        failed_manifest=failed_manifest,
        failed_manifest_sha256=failed_digest,
        recovered_manifest=tmp_path / "phenix verified.json",
        expected_release="2.1",
        expected_build="2.1-9999",
        tool_revision="f" * 40,
        current_symlink=parent / "phenix-current",
        progress=False,
        command_timeout_seconds=10,
    )
    return request, failed_manifest


def test_recover_failed_install_preserves_provenance_and_publishes(
    tmp_path: Path,
) -> None:
    request, failed_manifest = _recovery_fixture(tmp_path)
    original_failed_bytes = failed_manifest.read_bytes()

    recovered = recover_failed_install(request)

    assert recovered.status == "verified"
    assert request.installation_prefix.is_dir()
    assert not request.failed_prefix.exists()
    assert request.current_symlink.is_symlink()
    assert request.current_symlink.resolve() == request.installation_prefix.resolve()
    assert failed_manifest.read_bytes() == original_failed_bytes
    assert all(
        command.smoke_test_status is SmokeTestStatus.PASSED
        for command in recovered.required_commands
    )
    loaded = validate_manifest_environment(request.recovered_manifest)
    assert loaded.installer_sha256 == "1" * 64
    assert request.recovered_manifest.with_suffix(".verify.log").is_file()
    assert not (
        request.installation_prefix.parent / ".phenix-2.1-9999.recover.lock"
    ).exists()


def test_recovery_rejects_changed_failed_manifest_before_move(tmp_path: Path) -> None:
    request, failed_manifest = _recovery_fixture(tmp_path)
    failed_manifest.write_text(
        failed_manifest.read_text(encoding="utf-8") + " ", encoding="utf-8"
    )

    with pytest.raises(PhenixRecoveryError, match="SHA-256 mismatch"):
        recover_failed_install(request)

    assert request.failed_prefix.is_dir()
    assert not request.installation_prefix.exists()


def test_recovery_rejects_non_installer_quarantine_name(tmp_path: Path) -> None:
    request, _ = _recovery_fixture(tmp_path)
    unsafe_prefix = request.failed_prefix.with_name("arbitrary-runtime")
    request.failed_prefix.rename(unsafe_prefix)
    unsafe_request = replace(request, failed_prefix=unsafe_prefix)

    with pytest.raises(UnsafePhenixPathError, match="quarantine naming policy"):
        recover_failed_install(unsafe_request)

    assert unsafe_prefix.is_dir()
    assert not request.installation_prefix.exists()


def test_recovery_rolls_back_when_runtime_still_fails(tmp_path: Path) -> None:
    request, _ = _recovery_fixture(tmp_path, broken_command="phenix.xtriage")

    with pytest.raises(
        PhenixRuntimeVerificationError,
        match=r"required Phenix commands failed verification: phenix\.xtriage",
    ):
        recover_failed_install(request)

    assert request.failed_prefix.is_dir()
    assert not request.installation_prefix.exists()
    assert not request.recovered_manifest.exists()
    assert not request.current_symlink.exists()
    assert not (
        request.installation_prefix.parent / ".phenix-2.1-9999.recover.lock"
    ).exists()
