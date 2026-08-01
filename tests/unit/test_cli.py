"""Unit tests for command-line behaviour."""

import json
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


def test_contract_canonicalise_writes_stable_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = Path(__file__).resolve().parents[2]
    result = main(
        [
            "--no-progress",
            "contract",
            "canonicalise",
            "catalogue-manifest",
            str(repository / "examples/catalogue_manifest.json"),
        ]
    )
    assert result == 0
    output = capsys.readouterr().out
    assert json.loads(output)["schema_version"] == "1.0"
    assert "\n " not in output


def test_contract_schema_command_emits_draft_2020_12(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["contract", "schema", "sequence-group"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
