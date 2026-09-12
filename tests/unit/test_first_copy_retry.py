"""An observed inner 75 reaches existing retry dispatch after evidence is saved."""

from pathlib import Path

import pytest

from genome_to_diffraction.cli import main
from genome_to_diffraction.mr.phaser import PhaserRunRequest, run_first_copy_phaser
from genome_to_diffraction.schemas.results import NormalisedMrResult
from genome_to_diffraction.status import ExecutionStatus, TransientInfrastructureError
from tests.fixtures import ranking_four_arm_cli as reference_cli
from tests.fixtures.ranking_four_arm_first_copy import (
    run_reference_first_copy_task,
    validate_reference_first_copy_task,
)
from tests.unit.test_phaser_adapter import (
    NO_SOLUTION_LOG,
    _fake_runtime,
    _phase3_inputs,
)
from tests.unit.test_ranking_four_arm_context import _context
from tests.unit.test_ranking_four_arm_first_copy import _request

REPOSITORY = Path(__file__).resolve().parents[2]
FIRST_COPY_PROCESSES = {
    "modules/local/run_first_copy_phaser.nf": "RUN_FIRST_COPY_PHASER",
    "modules/local/phase3_multicrystal_first_copy_tasks.nf": (
        "RUN_PHASE3_FIRST_COPY_PHASER"
    ),
    "modules/local/phase3_no_a_tasks.nf": "RUN_PHASE3_NO_A_FIRST_COPY",
    "modules/local/m6_nextflow_tasks.nf": "M6_FIRST_COPY",
    "tests/fixtures/ranking_four_arm_tasks.nf": "RF_FIRST_COPY",
}


def first_copy_arguments(request: PhaserRunRequest) -> list[str]:
    """Use the real public Phase III entry point and unchanged fixture inputs."""

    fields = (
        ("--hypotheses", request.hypotheses_jsonl),
        ("--hypothesis-id", request.hypothesis_id),
        ("--sequence-groups", request.sequence_groups_jsonl),
        ("--processed-models", request.processed_models_jsonl),
        ("--all-model-registry", request.all_model_registry_json),
        ("--preflight", request.preflight_jsonl),
        ("--mtz", request.mtz),
        ("--phenix-manifest", request.phenix_manifest),
        ("--diffraction-selection", request.diffraction_selection_json),
        ("--resource-plan", request.resource_plan_json),
        ("--phase3-hypothesis-id", request.phase3_hypothesis_id),
        ("--outdir", request.output_directory),
        ("--threads", request.threads),
    )
    return [
        "--no-progress",
        "mr",
        "first-copy",
        *(value for option, argument in fields for value in (option, str(argument))),
    ]


@pytest.mark.parametrize(
    ("native_exit", "expected_exit", "expected_status"),
    (
        (75, 75, ExecutionStatus.FAILED_TOOL_EXECUTION),
        (2, 0, ExecutionStatus.FAILED_TOOL_EXECUTION),
        (0, 0, ExecutionStatus.COMPLETED_NO_HIT),
    ),
)
def test_actual_first_copy_cli_keeps_evidence_and_existing_retry_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    native_exit: int,
    expected_exit: int,
    expected_status: ExecutionStatus,
) -> None:
    request = _phase3_inputs(tmp_path)
    log = NO_SOLUTION_LOG if native_exit == 0 else "controlled native failure\n"
    calls = _fake_runtime(
        monkeypatch, log_text=log, returncode=native_exit, capture_bytes=log.encode()
    )

    status = main(first_copy_arguments(request))

    result = NormalisedMrResult.model_validate_json(
        (request.output_directory / "normalised_mr_result.json").read_bytes()
    )
    assert len(calls) == 1
    assert result.execution_status is expected_status
    if native_exit:
        assert result.rejection_reason == f"phenix.phaser_exit_{native_exit}"
    assert (request.output_directory / "phenix.phaser.capture.log").read_text() == log
    assert (request.output_directory / "normalised_mr_result.jsonl").is_file()
    assert (request.output_directory / "phaser_command.json").is_file()
    assert status == expected_exit


def test_library_retry_signal_is_raised_only_after_complete_native_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _phase3_inputs(tmp_path)
    _fake_runtime(monkeypatch, log_text="retained transient detail\n", returncode=75)

    with pytest.raises(TransientInfrastructureError):
        run_first_copy_phaser(request)

    result = NormalisedMrResult.model_validate_json(
        (request.output_directory / "normalised_mr_result.json").read_bytes()
    )
    assert result.execution_status is ExecutionStatus.FAILED_TOOL_EXECUTION
    assert result.rejection_reason == "phenix.phaser_exit_75"


def test_reference_retry_signal_preserves_its_authenticated_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path, monkeypatch)
    _fake_runtime(monkeypatch, log_text="retained RF transient detail\n", returncode=75)

    with pytest.raises(TransientInfrastructureError):
        run_reference_first_copy_task(request)

    receipt_path = request.output_directory / "reference_first_copy.json"
    receipt = validate_reference_first_copy_task(receipt_path, request)
    assert receipt.result.execution_status is ExecutionStatus.FAILED_TOOL_EXECUTION
    assert receipt.result.rejection_reason == "phenix.phaser_exit_75"
    assert "phenix.phaser.capture.log" in receipt.output_sha256


def test_reference_cli_propagates_explicit_retry_without_inventing_a_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _context(tmp_path).review.prepared
    context = tmp_path / "context.json"
    context.write_text(prepared.model_dump_json(), encoding="ascii")

    def fail(_request: object) -> Path:
        raise TransientInfrastructureError("controlled already-classified transient")

    monkeypatch.setattr(reference_cli, "run_reference_first_copy_task", fail)
    output = tmp_path / "output"
    assert (
        reference_cli.main(
            [
                "--source-root",
                str(REPOSITORY),
                "first-copy",
                "--prepared-context",
                str(context),
                "--hypothesis-id",
                "hyp-one",
                "--threads",
                "1",
                "--output",
                str(output),
            ]
        )
        == 75
    )
    assert not output.exists()


@pytest.mark.parametrize(("relative", "process"), FIRST_COPY_PROCESSES.items())
def test_first_copy_script_invalidates_former_failed_as_success_caches(
    relative: str, process: str
) -> None:
    source = (REPOSITORY / relative).read_text(encoding="utf-8")
    body = source.split(f"process {process} {{", 1)[1].split("\nprocess ", 1)[0]
    script = body.split("script:", 1)[1].split('"""', 2)[1]
    assert script.count("# Operational exit contract: first-copy-transient-75-v1") == 1
