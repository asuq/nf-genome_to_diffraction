"""Tests for machine-readable HPC CLI failure output."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.hpc.cli import _build_parser, main


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


def test_database_start_commands_are_distinct_from_routine_profiles() -> None:
    parser = _build_parser()

    staged = parser.parse_args(["database-stage", "--revision", "HEAD"])
    submitted = parser.parse_args(["database-submit", "--run-id", "RUN_ID"])
    readiness = parser.parse_args(["database-readiness"])
    archived = parser.parse_args(
        ["database-archive-failed", "--run-id", "RUN_ID", "--confirm", "RUN_ID"]
    )
    configured = parser.parse_args(
        [
            "p0-configure",
            "--paths-file",
            "p0.paths",
            "--confirm-sha256",
            "0" * 64,
        ]
    )
    input_stage = parser.parse_args(
        ["p0-inputs-stage", "--confirm-spec-sha256", "0" * 64]
    )

    assert staged.operation == "database-stage"
    assert submitted.operation == "database-submit"
    assert readiness.operation == "database-readiness"
    assert archived.operation == "database-archive-failed"
    assert configured.operation == "p0-configure"
    assert input_stage.operation == "p0-inputs-stage"
    with pytest.raises(SystemExit):
        parser.parse_args(["stage", "database", "--revision", "HEAD"])
    with pytest.raises(SystemExit):
        parser.parse_args(["submit", "database", "--run-id", "RUN_ID"])


@pytest.mark.parametrize("profile", ["p1", "p2", "p2-diverse", "p2-control"])
def test_scientific_profile_uses_only_the_fixed_routine_interface(
    profile: str,
) -> None:
    parser = _build_parser()

    readiness = parser.parse_args(["readiness", profile])
    staged = parser.parse_args(["stage", profile, "--revision", "HEAD"])
    submitted = parser.parse_args(["submit", profile, "--run-id", "RUN_ID"])

    assert readiness.profile == profile
    assert staged.profile == profile
    assert submitted.profile == profile


def test_review_collection_accepts_only_an_owned_run_identifier() -> None:
    parser = _build_parser()

    review = parser.parse_args(["review-collect", "--run-id", "RUN_ID"])

    assert review.operation == "review-collect"
    assert review.run_id == "RUN_ID"


def test_m4_copy_uses_explicit_checksum_gated_stage() -> None:
    parser = _build_parser()

    staged = parser.parse_args(
        [
            "m4-copy-stage",
            "--revision",
            "HEAD",
            "--parent-run",
            "PARENT",
            "--decisions",
            "decisions.tsv",
            "--confirm-decisions-sha256",
            "0" * 64,
        ]
    )
    submitted = parser.parse_args(["submit", "m4-copy", "--run-id", "RUN_ID"])

    assert staged.operation == "m4-copy-stage"
    assert staged.parent_run == "PARENT"
    assert submitted.profile == "m4-copy"
    with pytest.raises(SystemExit):
        parser.parse_args(["stage", "m4-copy", "--revision", "HEAD"])
