"""Tests for non-destructive legacy Phenix manifest refresh."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.phenix.errors import PhenixRuntimeVerificationError
from genome_to_diffraction.phenix.runtime import (
    REQUIRED_COMMANDS,
    RuntimeInspection,
    refresh_legacy_manifest,
)
from genome_to_diffraction.schemas.manifests import (
    PhenixCommandRecord,
    PhenixInstallManifest,
    SmokeTestStatus,
)


def _legacy_manifest(
    tmp_path: Path,
) -> tuple[Path, Path, tuple[PhenixCommandRecord, ...]]:
    prefix = tmp_path / "phenix-2.1-6048"
    binary = prefix / "bin"
    binary.mkdir(parents=True)
    environment = prefix / "phenix_env.sh"
    environment.write_text("export PHENIX_VERSION=2.1-6048\n", encoding="ascii")
    commands: list[PhenixCommandRecord] = []
    for name in REQUIRED_COMMANDS:
        executable = binary / name
        executable.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="ascii")
        executable.chmod(0o755)
        commands.append(
            PhenixCommandRecord(
                name=name,
                path=str(executable),
                executable_sha256=sha256_file(executable),
                smoke_test_status=SmokeTestStatus.PASSED,
                version_text="2.1-6048",
            )
        )
    manifest = tmp_path / "legacy.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "status": "verified",
                "phenix_version": "2.1-6048",
                "installation_prefix": str(prefix),
                "phenix_env_sh": str(environment),
                "phenix_env_sha256": sha256_file(environment),
                "installer_basename": "phenix-installer.bin",
                "installer_sha256": "a" * 64,
                "platform": {
                    "os": "Linux",
                    "architecture": "x86_64",
                    "glibc": "2.36",
                    "os_version": "test",
                },
                "installed_at": "2026-08-01T00:00:00Z",
                "required_commands": [
                    {
                        "name": command.name,
                        "path": command.path,
                        "smoke_test_status": "passed",
                        "version_text": "2.1-6048",
                    }
                    for command in commands
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest, prefix, tuple(commands)


def test_refresh_hashes_commands_without_modifying_legacy_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy, prefix, commands = _legacy_manifest(tmp_path)
    original = legacy.read_bytes()
    monkeypatch.setattr(
        "genome_to_diffraction.phenix.runtime.inspect_runtime",
        lambda *args, **kwargs: RuntimeInspection(
            phenix_version="2.1-6048",
            phenix_path=prefix,
            phenix_prefix=prefix,
            commands=commands,
        ),
    )
    output = tmp_path / "refreshed.json"

    refreshed = refresh_legacy_manifest(legacy, output, progress=False)

    assert legacy.read_bytes() == original
    assert output.is_file()
    assert refreshed.status == "verified"
    assert all(command.executable_sha256 for command in refreshed.required_commands)
    assert "legacy_manifest_refreshed_with_executable_sha256" in refreshed.warnings
    assert (
        PhenixInstallManifest.model_validate_json(output.read_text(encoding="utf-8"))
        == refreshed
    )


def test_refresh_rejects_changed_legacy_environment(tmp_path: Path) -> None:
    legacy, prefix, _ = _legacy_manifest(tmp_path)
    (prefix / "phenix_env.sh").write_text("changed\n", encoding="ascii")

    with pytest.raises(PhenixRuntimeVerificationError, match="checksum changed"):
        refresh_legacy_manifest(legacy, tmp_path / "refreshed.json", progress=False)
