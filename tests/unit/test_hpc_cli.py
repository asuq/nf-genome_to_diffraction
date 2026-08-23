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

    t12_review = parser.parse_args(["t12-review-collect", "--run-id", "RUN_ID"])
    assert t12_review.operation == "t12-review-collect"
    assert t12_review.run_id == "RUN_ID"


def test_heteromer_smoke_has_only_fixed_stage_and_submit_arguments() -> None:
    parser = _build_parser()

    staged = parser.parse_args(["stage", "heteromer-smoke", "--revision", "HEAD"])
    submitted = parser.parse_args(["submit", "heteromer-smoke", "--run-id", "RUN_ID"])

    assert staged.profile == "heteromer-smoke"
    assert vars(staged)["revision"] == "HEAD"
    assert not {"case", "path", "command", "coordinates"} & vars(staged).keys()
    assert submitted.profile == "heteromer-smoke"


def test_phase3_phenix_probe_exposes_no_runtime_command_or_path() -> None:
    parser = _build_parser()

    deployment = parser.parse_args(
        ["deploy-tools", "--revision", "HEAD", "--source-branch", "dev/phase3"]
    )
    staged = parser.parse_args(["stage", "phase3-phenix-probe", "--revision", "HEAD"])
    submitted = parser.parse_args(
        ["submit", "phase3-phenix-probe", "--run-id", "RUN_ID"]
    )

    assert deployment.source_branch == "dev/phase3"
    assert staged.profile == "phase3-phenix-probe"
    assert vars(staged)["revision"] == "HEAD"
    assert not {"path", "command", "manifest", "arguments"} & vars(staged).keys()
    assert submitted.profile == "phase3-phenix-probe"


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


def test_m4_import_has_no_caller_supplied_paths() -> None:
    parser = _build_parser()

    staged = parser.parse_args(["m4-import-stage", "--revision", "HEAD"])

    assert staged.operation == "m4-import-stage"
    assert vars(staged)["revision"] == "HEAD"
    assert not {"source", "destination", "parent_run"} & vars(staged).keys()


def test_control_slice_stage_has_no_caller_supplied_cases_or_paths() -> None:
    parser = _build_parser()

    staged = parser.parse_args(["control-slice-stage", "--revision", "HEAD"])
    assert staged.operation == "control-slice-stage"
    assert vars(staged)["revision"] == "HEAD"
    assert not {"cases", "source", "destination", "evidence_root"} & vars(staged).keys()
    submitted = parser.parse_args(["submit", "control-slice", "--run-id", "RUN_ID"])
    assert submitted.profile == "control-slice"


def test_control_matrix_stage_has_no_caller_supplied_cases_or_paths() -> None:
    parser = _build_parser()

    staged = parser.parse_args(["control-matrix-stage", "--revision", "HEAD"])
    assert staged.operation == "control-matrix-stage"
    assert vars(staged)["revision"] == "HEAD"
    assert not {"cases", "source", "destination", "evidence_root"} & vars(staged).keys()
    submitted = parser.parse_args(["submit", "control-matrix", "--run-id", "RUN_ID"])
    assert submitted.profile == "control-matrix"


@pytest.mark.parametrize("track", ["operational", "leakage"])
def test_m6_scientific_stage_accepts_only_a_confirmed_archive_and_track(
    track: str,
) -> None:
    parser = _build_parser()

    staged = parser.parse_args(
        [
            "m6-scientific-stage",
            "--revision",
            "HEAD",
            "--archive",
            ".untracked/m6-runner.tar",
            "--confirm-archive-sha256",
            "a" * 64,
            "--track",
            track,
        ]
    )
    submitted = parser.parse_args(["submit", f"m6-{track}", "--run-id", "RUN_ID"])

    assert staged.operation == "m6-scientific-stage"
    assert staged.track == track
    assert submitted.profile == f"m6-{track}"


def test_t12_stage_accepts_only_revision_and_owned_parent() -> None:
    parser = _build_parser()

    staged = parser.parse_args(
        ["t12-stage", "--revision", "HEAD", "--parent-run", "PARENT"]
    )
    submitted = parser.parse_args(["submit", "t12", "--run-id", "RUN_ID"])

    assert staged.operation == "t12-stage"
    assert staged.parent_run == "PARENT"
    assert not {"source", "destination", "source_records"} & vars(staged).keys()
    assert submitted.profile == "t12"


def test_t12_remote_stage_installs_the_locked_hpc_runtime() -> None:
    dispatcher = (
        Path(__file__).resolve().parents[2] / "bootstrap/nf-gtd-hpc-remote"
    ).read_text(encoding="utf-8")

    assert dispatcher.count('"$profile" == t12') >= 2
    assert dispatcher.count('"$profile" == control-slice') >= 2


def test_control_slice_remote_stage_validates_before_exposing_staged() -> None:
    dispatcher = (
        Path(__file__).resolve().parents[2] / "bootstrap/nf-gtd-hpc-remote"
    ).read_text(encoding="utf-8")
    function = dispatcher.split("control_slice_stage_run() {", 1)[1].split(
        "\nm4_import_stage_run() {", 1
    )[0]

    assert '"$case_count" -eq 6' in function
    assert "expected_cases = [" in function
    assert 'manifest.get("all_candidates_retained") is not True' in function
    import_phase = function.index(
        'atomic_text "$run/state/phase" control_slice_importing'
    )
    manifest_checksum = function.index(
        'atomic_text "$run/state/control-slice-manifest-sha256"'
    )
    final_staged = function.index('atomic_text "$run/state/phase" staged')
    assert import_phase < manifest_checksum < final_staged


def test_control_matrix_remote_stage_validates_fixed_scope_before_staged() -> None:
    dispatcher = (
        Path(__file__).resolve().parents[2] / "bootstrap/nf-gtd-hpc-remote"
    ).read_text(encoding="utf-8")
    function = dispatcher.split("control_matrix_stage_run() {", 1)[1].split(
        "\nm4_import_stage_run() {", 1
    )[0]

    assert '"$case_count" -eq 23' in function
    assert '"positive": 11' in function
    assert '"wrong_model_negative": 7' in function
    assert 'manifest.get("positive_copy_counts") != [1, 2, 3, 4, 6]' in function
    assert 'manifest.get("all_candidates_retained") is not True' in function
    assert 'manifest.get("score_policy")' in function


def test_m4_copy_remote_stage_exposes_staged_only_after_inputs_are_bound() -> None:
    dispatcher = (
        Path(__file__).resolve().parents[2] / "bootstrap/nf-gtd-hpc-remote"
    ).read_text(encoding="utf-8")
    function = dispatcher.split("m4_copy_stage_run() {", 1)[1].split(
        "\ndatabase_stage_run() {", 1
    )[0]

    input_staging = function.index('atomic_text "$run/state/phase" m4_input_staging')
    manifest_checksum = function.index(
        'atomic_text "$run/state/m4-stage-manifest-sha256"'
    )
    final_staged = function.index('atomic_text "$run/state/phase" staged')

    assert input_staging < manifest_checksum < final_staged


def test_m4_job_builds_and_collects_copy_count_report() -> None:
    repository = Path(__file__).resolve().parents[2]
    job = (repository / "bootstrap/nf-gtd-hpc-smoke-job").read_text(encoding="utf-8")
    dispatcher = (repository / "bootstrap/nf-gtd-hpc-remote").read_text(
        encoding="utf-8"
    )

    assert "mr copy-report" in job
    assert "m4-copy-count-report/copy_count_report_manifest.json" in job
    assert "m4-copy-count-report/copy_count_report_manifest.json" in dispatcher
