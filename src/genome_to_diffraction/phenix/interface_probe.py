"""Collect the installed Phenix Phaser interface without running MR.

The Phase III component-coordinate adapter needs the exact Phenix PHIL mapping
for Phaser's documented ``XYZOUT ON ENSEMBLE ON`` keyword.  The public Phaser
manual defines the binary keyword, but the mapping exposed by a particular
installed Phenix build must be observed rather than guessed.

This narrow probe runs only ``phenix.phaser --show_defaults`` through the
checksum-verified Phenix manifest.  It records the complete byte output and a
path-free content-addressed report.  It accepts no caller-supplied executable,
argument, input structure, or reflection file and therefore performs no
scientific calculation.
"""

from dataclasses import dataclass
from pathlib import Path

from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    sha256_file,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.phenix.errors import PhenixRuntimeVerificationError
from genome_to_diffraction.phenix.runtime import (
    capture_from_manifest,
    validate_manifest_environment,
    verified_runtime_identity_sha256,
)

_ADAPTER_VERSION = "phenix-phaser-interface-probe-v1"
_COMMAND = ("phenix.phaser", "--show_defaults")


@dataclass(frozen=True)
class PhaserInterfaceProbeRequest:
    """Fixed manifest, output directory, and optional execution deadline."""

    phenix_manifest: Path
    output_directory: Path
    timeout_seconds: float | None = 120.0


@dataclass(frozen=True)
class PhaserInterfaceProbeOutput:
    """Content-addressed report and exact captured defaults bytes."""

    probe_id: str
    report_json: Path
    defaults_output: Path


def probe_phaser_interface(
    request: PhaserInterfaceProbeRequest,
) -> PhaserInterfaceProbeOutput:
    """Capture the exact installed ``phenix.phaser --show_defaults`` output."""

    if request.timeout_seconds is not None and request.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive when supplied")
    output = request.output_directory.absolute()
    if output.exists() and any(output.iterdir()):
        raise PhenixRuntimeVerificationError(
            f"Phaser interface-probe output directory is not empty: {output}"
        )

    manifest_path = request.phenix_manifest.resolve(strict=True)
    manifest = validate_manifest_environment(manifest_path)
    command = next(
        record for record in manifest.required_commands if record.name == _COMMAND[0]
    )
    if command.executable_sha256 is None:
        raise PhenixRuntimeVerificationError(
            "verified phenix.phaser command lacks an executable checksum"
        )

    output.mkdir(parents=True, exist_ok=True)
    completed = capture_from_manifest(
        manifest_path,
        _COMMAND,
        working_directory=output,
        timeout_seconds=request.timeout_seconds,
    )
    defaults_bytes = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise PhenixRuntimeVerificationError(
            "phenix.phaser --show_defaults failed with exit status "
            f"{completed.returncode}"
        )
    if not defaults_bytes.strip():
        raise PhenixRuntimeVerificationError(
            "phenix.phaser --show_defaults returned empty output"
        )

    defaults_path = output / "phenix-phaser-show-defaults.txt"
    atomic_write_bytes(defaults_path, defaults_bytes)
    defaults_sha256 = sha256_file(defaults_path)
    decoded = defaults_bytes.decode("utf-8", errors="replace")
    casefolded = decoded.casefold()
    payload = {
        "schema_version": "1.0",
        "adapter_version": _ADAPTER_VERSION,
        "phenix_version": manifest.phenix_version,
        "phenix_runtime_identity_sha256": verified_runtime_identity_sha256(
            manifest_path
        ),
        "phenix_phaser_executable_sha256": command.executable_sha256,
        "command": list(_COMMAND),
        "exit_status": completed.returncode,
        "defaults_output": defaults_path.name,
        "defaults_sha256": defaults_sha256,
        "defaults_size_bytes": len(defaults_bytes),
        "phaser_scope_observed": "phaser" in casefolded,
        "xyzout_token_observed": "xyzout" in casefolded,
        "ensemble_token_observed": "ensemble" in casefolded,
        "scientific_execution_performed": False,
    }
    probe_id = content_id("phaserinterface_", payload)
    report = {"probe_id": probe_id, **payload}
    report_path = output / "phaser-interface-probe.json"
    atomic_write_json(report_path, report)
    return PhaserInterfaceProbeOutput(
        probe_id=probe_id,
        report_json=report_path,
        defaults_output=defaults_path,
    )
