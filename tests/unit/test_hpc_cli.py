"""Tests for machine-readable HPC CLI failure output."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.hpc.cli import main


def test_missing_configuration_returns_json_and_diagnostic_log(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = main(
        [
            "--config",
            str(tmp_path / "missing.json"),
            "--no-progress",
            "status",
            "--run-id",
            "gtd-smoke-20260802T120000Z-0123456789ab-01234567",
        ]
    )

    assert result == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["failure_class"] == "wrapper_failure"
    assert "configuration not found" in payload["message"]
    assert "HPC operation failed" in captured.err
