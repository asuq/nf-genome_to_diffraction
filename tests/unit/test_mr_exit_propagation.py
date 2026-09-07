"""CLI regressions for native retry evidence and terminal candidate failures."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import genome_to_diffraction.cli as cli
from genome_to_diffraction.schemas.results import PhaserExecutionFailure
from genome_to_diffraction.status import ExecutionStatus


def _arguments(action: str, resource_attempt: int) -> list[str]:
    cli_action = "add-copy" if action == "add-series" else action
    command = "composition" if action == "run-attempt" else "mr"
    flags = {
        "first-copy": (
            "hypotheses",
            "hypothesis-id",
            "sequence-groups",
            "processed-models",
            "model-preparation-manifest",
            "preflight",
            "mtz",
            "phenix-manifest",
        ),
        "add-copy": (
            "seed-solution-id",
            "hypotheses",
            "sequence-groups",
            "preflight",
            "mtz",
            "search-model",
            "phenix-manifest",
        ),
        "run-attempt": (
            "attempt-inventory",
            "attempt-id",
            "fixed-coordinate-root",
            "model-registry",
            "sequence-groups",
            "preflight",
            "mtz",
            "phenix-manifest",
            "execution-identity",
        ),
        "search-component": (
            "manifest",
            "sequence-groups",
            "preflight",
            "mtz",
            "phenix-manifest",
        ),
    }[cli_action]
    arguments = [command, cli_action]
    for flag in (*flags, "outdir"):
        arguments.extend((f"--{flag}", "synthetic"))
    arguments.extend(("--resource-attempt", str(resource_attempt)))
    if action == "add-series":
        arguments.append("--until-expected")
    return arguments


def _replace_adapter(monkeypatch, action, status, failure):
    result = SimpleNamespace(
        execution_status=status,
        execution_failure=failure,
        attempt_id="one-logical-search",
    )
    output = SimpleNamespace(result=result, result_json=Path("retained-result.json"))
    returned = (
        SimpleNamespace(attempts=(output,), summary_json=Path("series.json"))
        if action == "add-series"
        else result
        if action == "search-component"
        else output
    )
    function = {
        "first-copy": "run_first_copy_phaser",
        "add-copy": "run_additional_copy_phaser",
        "add-series": "run_additional_copy_series",
        "run-attempt": "execute_composition_attempt",
        "search-component": "run_multi_fixed_search",
    }[action]
    monkeypatch.setattr(cli, function, lambda *args, **kwargs: returned)


@pytest.mark.parametrize(
    "action",
    ("first-copy", "add-copy", "add-series", "run-attempt", "search-component"),
)
@pytest.mark.parametrize(("resource_attempt", "expected_exit"), ((1, 75), (2, 0)))
def test_retryable_first_failure_reaches_nextflow_once(
    monkeypatch, action, resource_attempt, expected_exit
):
    failure = PhaserExecutionFailure.from_native(returncode=137, timed_out=False)
    _replace_adapter(
        monkeypatch, action, ExecutionStatus.FAILED_TOOL_EXECUTION, failure
    )
    assert cli.main(_arguments(action, resource_attempt)) == expected_exit


@pytest.mark.parametrize(
    ("status", "failure", "expected_exit"),
    (
        (ExecutionStatus.COMPLETED_NO_HIT, None, 0),
        (ExecutionStatus.FAILED_PARSE, None, 0),
        (ExecutionStatus.FAILED_TOOL_EXECUTION, None, 0),
        (
            ExecutionStatus.FAILED_TOOL_EXECUTION,
            PhaserExecutionFailure.from_native(returncode=1, timed_out=False),
            0,
        ),
        (
            ExecutionStatus.FAILED_TOOL_EXECUTION,
            PhaserExecutionFailure.from_native(returncode=124, timed_out=False),
            0,
        ),
        (
            ExecutionStatus.FAILED_TOOL_EXECUTION,
            PhaserExecutionFailure.from_native(returncode=-9, timed_out=True),
            75,
        ),
        (ExecutionStatus.FAILED_INFRASTRUCTURE, None, 1),
        (ExecutionStatus.FAILED_INPUT_CONTRACT, None, 1),
    ),
)
def test_only_explicit_candidate_failure_evidence_grants_retry(
    monkeypatch, status, failure, expected_exit
):
    _replace_adapter(monkeypatch, "first-copy", status, failure)
    assert cli.main(_arguments("first-copy", 1)) == expected_exit
