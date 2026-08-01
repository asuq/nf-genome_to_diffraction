"""Lightweight integration-scaffold tests that do not execute scientific work."""

import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_module_cli_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "genome_to_diffraction.cli", "--version"],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "0.1.0.dev0"


@pytest.mark.integration
def test_nextflow_processes_are_fail_loud_and_have_stubs() -> None:
    main_source = (REPOSITORY / "modules/local/foundation_main_stub.nf").read_text(
        encoding="utf-8"
    )
    assert "foundation_only_not_implemented" in main_source
    assert "stub:" in main_source
    database_source = (
        REPOSITORY / "modules/local/prepare_database_resources.nf"
    ).read_text(encoding="utf-8")
    assert "genome-to-diffraction --no-progress databases prepare" in database_source
    assert "stub:" in database_source
    assert "nextflow.enable.types = true" in database_source
