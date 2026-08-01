"""Unit tests for safe Phenix installation and isolated execution."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from genome_to_diffraction.phenix.errors import (
    PhenixInstallationExistsError,
    PhenixInstallCommandError,
    PhenixInstallerChecksumError,
    PhenixRuntimeVerificationError,
    UnsafePhenixPathError,
)
from genome_to_diffraction.phenix.installer import InstallRequest, install_phenix
from genome_to_diffraction.phenix.runtime import (
    REQUIRED_COMMANDS,
    execute_from_manifest,
    validate_manifest_environment,
    verify_manifest,
)

REPOSITORY = Path(__file__).resolve().parents[2]


def _write_installer(path: Path, *, exit_status: int = 0) -> str:
    commands = " ".join(REQUIRED_COMMANDS)
    script = f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "${{1-}}" != "-b" || "${{2-}}" != "-p" ]]; then
  exit 64
fi
prefix="$3"
mkdir -p "$prefix/bin"
if [[ {exit_status} -ne 0 ]]; then
  exit {exit_status}
fi
printf 'export PHENIX=%q\n' "$prefix" > "$prefix/phenix_env.sh"
printf 'export PHENIX_PREFIX=%q\n' "$prefix" >> "$prefix/phenix_env.sh"
printf 'export PHENIX_VERSION=%q\n' '2.1-9999' >> "$prefix/phenix_env.sh"
printf 'export PATH=%q/bin:$PATH\n' "$prefix" >> "$prefix/phenix_env.sh"
for command in {commands}; do
  cat > "$prefix/bin/$command" <<'COMMAND'
#!/usr/bin/env bash
if [[ "${{1-}}" == "--help" ]]; then
  printf 'fake Phenix help\n'
  exit 0
fi
printf '%s\n' "$@"
COMMAND
  chmod 755 "$prefix/bin/$command"
done
"""
    path.write_text(script, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _request(
    tmp_path: Path,
    installer: Path,
    digest: str,
    *,
    prefix: Path | None = None,
    manifest: Path | None = None,
) -> InstallRequest:
    install_parent = tmp_path / "Phenix installations with spaces"
    install_parent.mkdir(exist_ok=True)
    temporary_directory = tmp_path / "temporary files"
    temporary_directory.mkdir(exist_ok=True)
    return InstallRequest(
        installer=installer,
        installer_sha256=digest,
        installation_prefix=prefix or install_parent / "phenix-2.1-9999",
        expected_release="2.1",
        expected_build="2.1-9999",
        temporary_directory=temporary_directory,
        manifest_path=manifest or tmp_path / "phenix manifest.json",
        current_symlink=install_parent / "current",
        minimum_install_free_bytes=0,
        minimum_temporary_free_bytes=0,
        progress=False,
        command_timeout_seconds=10,
    )


def test_installer_checksum_mismatch_fails_before_install(tmp_path: Path) -> None:
    installer = tmp_path / "phenix installer.sh"
    digest = _write_installer(installer)
    request = _request(tmp_path, installer, "0" * 64)
    with pytest.raises(PhenixInstallerChecksumError, match="mismatch"):
        install_phenix(request)
    assert digest != request.installer_sha256
    assert not request.installation_prefix.exists()


def test_unsafe_destination_is_rejected(tmp_path: Path) -> None:
    installer = tmp_path / "installer.sh"
    digest = _write_installer(installer)
    request = _request(tmp_path, installer, digest, prefix=Path("/"))
    with pytest.raises(UnsafePhenixPathError, match="filesystem root"):
        install_phenix(request)


def test_existing_installation_is_never_overwritten(tmp_path: Path) -> None:
    installer = tmp_path / "installer.sh"
    digest = _write_installer(installer)
    request = _request(tmp_path, installer, digest)
    request.installation_prefix.mkdir()
    marker = request.installation_prefix / "user-file"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises(PhenixInstallationExistsError, match="already exists"):
        install_phenix(request)
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_mocked_installer_writes_verified_schema_valid_manifest(
    tmp_path: Path,
) -> None:
    installer = tmp_path / "phenix installer.sh"
    digest = _write_installer(installer)
    request = _request(tmp_path, installer, digest)
    manifest = install_phenix(request)

    assert manifest.status == "verified"
    assert manifest.phenix_version == "2.1-9999"
    assert all(
        record.smoke_test_status == "passed" for record in manifest.required_commands
    )
    assert request.current_symlink is not None
    assert request.current_symlink.resolve() == request.installation_prefix.resolve()
    loaded = validate_manifest_environment(request.manifest_path)
    assert loaded.installer_sha256 == digest
    assert verify_manifest(request.manifest_path, progress=False).commands
    assert json.loads(request.manifest_path.read_text(encoding="utf-8"))["status"] == (
        "verified"
    )


def test_mocked_failed_installer_preserves_status_and_exact_exit(
    tmp_path: Path,
) -> None:
    installer = tmp_path / "failed installer.sh"
    digest = _write_installer(installer, exit_status=23)
    request = _request(tmp_path, installer, digest)
    with pytest.raises(PhenixInstallCommandError) as captured:
        install_phenix(request)
    assert getattr(captured.value, "returncode", None) == 23
    manifest = json.loads(request.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert "exit status 23" in manifest["warnings"][0]
    assert not request.installation_prefix.exists()
    assert list(request.installation_prefix.parent.glob(".phenix-2.1-9999.failed-*"))


def test_isolated_executor_preserves_parent_path_and_literal_arguments(
    tmp_path: Path,
) -> None:
    installer = tmp_path / "installer.sh"
    digest = _write_installer(installer)
    request = _request(tmp_path, installer, digest)
    install_phenix(request)
    marker = tmp_path / "must not be created"
    parent_path = os.environ.get("PATH")

    returncode = execute_from_manifest(
        request.manifest_path,
        ["phenix.xtriage", f"; touch {marker}"],
    )

    assert returncode == 0
    assert os.environ.get("PATH") == parent_path
    assert not marker.exists()


def test_shell_executor_preserves_external_exit_status(tmp_path: Path) -> None:
    installer = tmp_path / "installer.sh"
    digest = _write_installer(installer)
    request = _request(tmp_path, installer, digest)
    install_phenix(request)
    exit_command = request.installation_prefix / "bin" / "phenix.exit"
    exit_command.write_text("#!/usr/bin/env bash\nexit 23\n", encoding="utf-8")
    exit_command.chmod(0o755)

    completed = subprocess.run(
        [
            REPOSITORY / "bin" / "phenix_exec.sh",
            "--manifest",
            request.manifest_path,
            "--",
            "phenix.exit",
        ],
        check=False,
    )
    assert completed.returncode == 23


def test_manifest_environment_tampering_fails(tmp_path: Path) -> None:
    installer = tmp_path / "installer.sh"
    digest = _write_installer(installer)
    request = _request(tmp_path, installer, digest)
    install_phenix(request)
    environment_file = request.installation_prefix / "phenix_env.sh"
    environment_file.write_text(
        environment_file.read_text(encoding="utf-8") + "# changed\n",
        encoding="utf-8",
    )
    with pytest.raises(PhenixRuntimeVerificationError, match="checksum"):
        validate_manifest_environment(request.manifest_path)
