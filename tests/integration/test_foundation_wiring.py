"""Lightweight integration checks for typed workflow source wiring."""

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
def test_nextflow_task05_processes_are_typed_and_have_stubs() -> None:
    for name in (
        "validate_task05_inputs.nf",
        "import_catalogues.nf",
        "mtz_preflight.nf",
        "enumerate_matthews.nf",
    ):
        source = (REPOSITORY / "modules/local" / name).read_text(encoding="utf-8")
        assert "nextflow.enable.types = true" in source
        assert "stub:" in source
    database_source = (
        REPOSITORY / "modules/local/prepare_database_resources.nf"
    ).read_text(encoding="utf-8")
    assert "genome-to-diffraction --no-progress databases prepare" in database_source
    assert "stub:" in database_source
    assert "nextflow.enable.types = true" in database_source


@pytest.mark.integration
def test_project_layout_preparation_is_idempotent_and_space_safe(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "pilot project"
    command = [
        str(REPOSITORY / "bootstrap" / "prepare_project_layout.sh"),
        "--root",
        str(project_root),
    ]

    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    for relative_path in (
        "input/genome",
        "input/diffraction",
        "manifests",
        "software/manifests",
        "databases",
        "cache/nextflow-home",
        "cache/work",
        "logs",
        "results",
    ):
        assert (project_root / relative_path).is_dir()
    assert f"[prepare] project root: {project_root}" in first.stdout
    assert f"[prepare] project root: {project_root}" in second.stdout


@pytest.mark.integration
def test_project_layout_dry_run_does_not_write(tmp_path: Path) -> None:
    project_root = tmp_path / "dry run"
    result = subprocess.run(
        [
            str(REPOSITORY / "bootstrap" / "prepare_project_layout.sh"),
            "--root",
            str(project_root),
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "[prepare:dry-run]" in result.stdout
    assert not project_root.exists()


@pytest.mark.integration
def test_project_layout_rejects_relative_root() -> None:
    result = subprocess.run(
        [
            str(REPOSITORY / "bootstrap" / "prepare_project_layout.sh"),
            "--root",
            "relative/path",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "--root must be an absolute path" in result.stderr
