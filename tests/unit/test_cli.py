"""Unit tests for command-line behaviour."""

from pathlib import Path

import pytest

from genome_to_diffraction.cli import main


def test_version_flag_exits_successfully(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--version"])
    assert error.value.code == 0
    assert capsys.readouterr().out.strip() == "0.1.0.dev0"


def test_schema_check_reports_missing_schema_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["schema-check", "--repository", str(tmp_path)]) == 1
    assert "schema directory not found" in capsys.readouterr().err
