"""Unit tests for the public package boundary, metadata and time helpers."""

import subprocess
import sys
from datetime import datetime

from genome_to_diffraction import __version__
from genome_to_diffraction.time import utc_now, utc_now_iso


def test_version_is_v0_2_release() -> None:
    assert __version__ == "0.2.0"


def test_public_cli_does_not_require_internal_hpc_package() -> None:
    """Catch source imports of the intentionally wheel-excluded controller."""

    probe = """
import importlib.abc
import sys

class ExcludeInternalHpc(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "genome_to_diffraction.hpc" or fullname.startswith(
            "genome_to_diffraction.hpc."
        ):
            raise ModuleNotFoundError("internal HPC package is not distributed")
        return None

sys.meta_path.insert(0, ExcludeInternalHpc())
sys.argv = ["genome-to-diffraction", "--help"]
from genome_to_diffraction.cli import main
main()
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_utc_now_is_timezone_aware() -> None:
    value = utc_now()
    offset = value.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0


def test_utc_now_iso_is_parseable_and_uses_z_suffix() -> None:
    value = utc_now_iso()
    assert value.endswith("Z")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.utcoffset() is not None
