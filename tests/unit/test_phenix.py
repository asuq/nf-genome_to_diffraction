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
    capture_matthews_reference_from_manifest,
    execute_from_manifest,
    validate_manifest_environment,
    verify_manifest,
)

REPOSITORY = Path(__file__).resolve().parents[2]


def _write_installer(
    path: Path,
    *,
    exit_status: int = 0,
    xtriage_probe: str = "valid",
) -> str:
    xtriage_probe_body = {
        "valid": (
            "      printf 'Usage:\\n'\n"
            "      printf 'phenix.xtriage [options] reflection_file "
            "parameters [...]\\n'\n"
            "      exit 1"
        ),
        "missing_signature": (
            "      printf 'generic help without a command signature\\n'\n      exit 1"
        ),
        "traceback": (
            "      printf 'Usage:\\n'\n"
            "      printf 'phenix.xtriage [options] reflection_file "
            "parameters [...]\\n'\n"
            "      printf 'Traceback (most recent call last):\\n' >&2\n"
            "      printf 'ImportError: broken runtime\\n' >&2\n"
            "      exit 1"
        ),
    }[xtriage_probe]
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
  case "${{0##*/}}" in
    phenix.xtriage)
{xtriage_probe_body}
      ;;
    phenix.phaser)
      printf 'Usage:\n'
      printf 'phenix.phaser is a multi-function command:\n'
      printf 'it can launch either mode.\n'
      exit 1
      ;;
    phenix.maps)
      printf 'phenix.maps: a command line tool to compute various maps and save them.\n'
      exit 1
      ;;
    *)
      printf 'fake Phenix help\n'
      exit 0
      ;;
  esac
fi
printf '%s\n' "$@"
COMMAND
  chmod 755 "$prefix/bin/$command"
done
cat > "$prefix/bin/mmtbx.matthews" <<'COMMAND'
#!/usr/bin/env bash
if [[ "${{1-}}" == "--help" ]]; then
  printf 'Calculate a Matthews coefficient with n_residues\n'
  exit 0
fi
printf 'argument_1=%s\n' "$1"
printf 'argument_2=%s\n' "$2"
printf '| Copies | Solvent content | Matthews coeff. | P(solvent content) |\n'
printf '| 1 | 0.754 | 5.00 | 0.200 |\n'
printf '| 2 | 0.508 | 2.50 | 0.900 |\n'
printf '| 3 | 0.262 | 1.67 | 0.300 |\n'
printf 'Best guess : 2 copies in the ASU\n'
COMMAND
chmod 755 "$prefix/bin/mmtbx.matthews"
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
    verification_log = request.manifest_path.with_suffix(".verify.log").read_text(
        encoding="utf-8"
    )
    assert verification_log.count('probe_args=["--help"]') == len(REQUIRED_COMMANDS)
    assert verification_log.count("exit=1") == 3
    assert (
        verification_log.count(
            "reason=accepted command-specific non-zero help convention"
        )
        == 3
    )


def test_runtime_probe_timeout_is_actionable_and_retained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer = tmp_path / "phenix installer.sh"
    digest = _write_installer(installer)
    request = _request(tmp_path, installer, digest)
    install_phenix(request)
    verification_log = tmp_path / "timeout verification.log"

    def timeout_probe(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise subprocess.TimeoutExpired(["phenix.xtriage", "--help"], 3)

    monkeypatch.setattr(
        "genome_to_diffraction.phenix.runtime._child_shell", timeout_probe
    )

    with pytest.raises(
        PhenixRuntimeVerificationError,
        match=r"command probe timed out after 3 seconds: phenix\.xtriage",
    ):
        verify_manifest(
            request.manifest_path,
            progress=False,
            timeout_seconds=3,
            verification_log=verification_log,
        )

    retained = verification_log.read_text(encoding="utf-8")
    assert "## phenix.xtriage" in retained
    assert "exit=timeout" in retained
    assert "reason=probe timed out after 3 seconds" in retained


@pytest.mark.parametrize("xtriage_probe", ["missing_signature", "traceback"])
def test_nonzero_probe_requires_valid_help_without_runtime_failures(
    tmp_path: Path,
    xtriage_probe: str,
) -> None:
    installer = tmp_path / "phenix installer.sh"
    digest = _write_installer(installer, xtriage_probe=xtriage_probe)
    request = _request(tmp_path, installer, digest)

    with pytest.raises(
        PhenixRuntimeVerificationError,
        match=r"required Phenix commands failed verification: phenix\.xtriage",
    ):
        install_phenix(request)

    manifest = json.loads(request.manifest_path.read_text(encoding="utf-8"))
    xtriage_record = next(
        record
        for record in manifest["required_commands"]
        if record["name"] == "phenix.xtriage"
    )
    assert xtriage_record["smoke_test_status"] == "failed"
    verification_log = request.manifest_path.with_suffix(".verify.log").read_text(
        encoding="utf-8"
    )
    assert 'probe_args=["--help"]' in verification_log
    assert "exit=1" in verification_log
    assert "result=failed" in verification_log


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


def test_fixed_matthews_reference_is_captured_with_provenance(tmp_path: Path) -> None:
    installer = tmp_path / "installer.sh"
    digest = _write_installer(installer)
    request = _request(tmp_path, installer, digest)
    install_phenix(request)
    mtz = tmp_path / "input data.mtz"
    mtz.write_bytes(b"synthetic fixture")

    execution = capture_matthews_reference_from_manifest(
        request.manifest_path,
        mtz_path=mtz,
        residue_count=100,
        working_directory=tmp_path / "working directory",
        timeout_seconds=10,
    )

    assert execution.completed.returncode == 0
    assert b"Best guess : 2 copies" in execution.completed.stdout
    assert f"argument_1={mtz.resolve()}".encode() in execution.completed.stdout
    assert b"argument_2=n_residues=100" in execution.completed.stdout
    assert execution.executable.is_relative_to(request.installation_prefix)
    assert len(execution.executable_sha256) == 64
    assert execution.phenix_version == "2.1-9999"


def test_fixed_matthews_reference_rejects_executable_escape(tmp_path: Path) -> None:
    installer = tmp_path / "installer.sh"
    digest = _write_installer(installer)
    request = _request(tmp_path, installer, digest)
    install_phenix(request)
    auxiliary = request.installation_prefix / "bin/mmtbx.matthews"
    auxiliary.unlink()
    auxiliary.symlink_to(Path("/bin/echo"))
    mtz = tmp_path / "input.mtz"
    mtz.write_bytes(b"synthetic fixture")

    with pytest.raises(PhenixRuntimeVerificationError, match="not found inside"):
        capture_matthews_reference_from_manifest(
            request.manifest_path,
            mtz_path=mtz,
            residue_count=100,
            working_directory=tmp_path / "work",
            timeout_seconds=10,
        )
