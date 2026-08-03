"""Tests for the reproducible immutable HPC controller build."""

import hashlib
import json
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
BUILDER = REPOSITORY / "bootstrap" / "build_hpc_test_app.py"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _build(output: Path) -> dict[str, str]:
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--output", str(output)],
        cwd=REPOSITORY,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return {str(key): str(value) for key, value in payload.items()}


def test_hpc_controller_build_is_byte_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first-controller"
    second = tmp_path / "second-controller"

    first_provenance = _build(first)
    second_provenance = _build(second)

    assert first.read_bytes() == second.read_bytes()
    digest = hashlib.sha256(first.read_bytes()).hexdigest()
    assert first_provenance["sha256"] == digest
    assert second_provenance["sha256"] == digest
    assert stat.S_IMODE(first.stat().st_mode) == 0o555

    with zipfile.ZipFile(first) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        assert names == sorted(names)
        assert names[0] == "__main__.py"
        assert all(member.date_time == FIXED_ZIP_TIMESTAMP for member in members)
        assert all(member.compress_type == zipfile.ZIP_DEFLATED for member in members)
        assert all(
            stat.S_IMODE(member.external_attr >> 16) == 0o644 for member in members
        )
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)

    help_result = subprocess.run(
        [str(first), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "readiness" in help_result.stdout
