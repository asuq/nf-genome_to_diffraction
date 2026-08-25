"""Unit tests for command-line behaviour."""

import json
from pathlib import Path

import pytest

import genome_to_diffraction.cli as cli_module
from genome_to_diffraction.cli import main
from genome_to_diffraction.status import (
    InfrastructureError,
    InputContractError,
    ResultParseError,
    TransientInfrastructureError,
)


@pytest.mark.parametrize(
    "action", ("run-control-slice", "run-control-matrix", "run-m6-scientific")
)
def test_retired_direct_benchmark_execution_aliases_are_not_registered(
    action: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        main(["benchmark", action])

    assert error.value.code == 2
    assert f"invalid choice: '{action}'" in capsys.readouterr().err


def test_version_flag_exits_successfully(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--version"])
    assert error.value.code == 0
    assert capsys.readouterr().out.strip() == "0.2.0"


@pytest.mark.parametrize("action", ("build-status", "build-report"))
def test_obsolete_scientific_claim_writers_are_not_registered(
    capsys: pytest.CaptureFixture[str], action: str
) -> None:
    with pytest.raises(SystemExit) as error:
        main(["review", action])

    assert error.value.code == 2
    assert f"invalid choice: '{action}'" in capsys.readouterr().err


def test_schema_check_reports_missing_schema_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["schema-check", "--repository", str(tmp_path)]) == 1
    assert "schema directory not found" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("error", "expected_status"),
    (
        (TransientInfrastructureError("temporary staging failure"), 75),
        (InfrastructureError("permanent infrastructure failure"), 1),
        (InputContractError("invalid scientific input"), 1),
        (ResultParseError("unparseable scientific result"), 1),
    ),
)
def test_only_classified_transient_failures_request_a_scheduler_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    def fail(_repository: Path) -> list[str]:
        raise error

    monkeypatch.setattr(cli_module, "validate_repository", fail)

    assert main(["schema-check", "--repository", str(tmp_path)]) == expected_status


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


def test_contract_schema_command_emits_authoritative_tracked_schema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = Path(__file__).resolve().parents[2]
    authoritative = json.loads(
        (repository / "schemas/pipeline_config.schema.json").read_text(encoding="utf-8")
    )

    assert main(["contract", "schema", "pipeline-config"]) == 0

    assert json.loads(capsys.readouterr().out) == authoritative
