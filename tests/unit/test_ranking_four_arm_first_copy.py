"""Actual shared first-copy execution with simulated, explicitly non-native Phenix."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.fixtures.ranking_four_arm_first_copy import (
    ReferenceFirstCopyRequest,
    build_prepared_reference_reviews,
    run_reference_first_copy_task,
    validate_prepared_reference_reviews,
    validate_reference_first_copy_task,
)
from tests.fixtures.ranking_four_arm_prepared import bind_reference_prepared_case
from tests.unit.test_phaser_adapter import NO_SOLUTION_LOG, POSITIVE_LOG, _fake_runtime
from tests.unit.test_ranking_four_arm_prepared import _inputs


def _request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ReferenceFirstCopyRequest:
    inputs = _inputs(tmp_path, monkeypatch)
    prepared = bind_reference_prepared_case(inputs, tmp_path / "reference-prepared")
    materialisation = json.loads(
        (prepared.parent / "cohorts/reference_cohorts.json").read_text()
    )
    return ReferenceFirstCopyRequest(
        prepared_path=prepared,
        prepared_inputs=inputs,
        hypothesis_id=materialisation["tasks"][0]["hypothesis"]["hypothesis_id"],
        threads=4,
        output_directory=tmp_path / "first-copy",
    )


@pytest.mark.parametrize("outcome", ("hit", "no_hit", "tool_failure", "parse_failure"))
def test_reference_first_copy_preserves_shared_commands_and_typed_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    request = _request(tmp_path, monkeypatch)
    commands = _fake_runtime(
        monkeypatch,
        log_text=POSITIVE_LOG
        if outcome == "hit"
        else NO_SOLUTION_LOG
        if outcome == "no_hit"
        else "explicit failed synthetic response\n",
        write_solution=outcome == "hit",
        returncode=3 if outcome == "tool_failure" else 0,
    )
    path = run_reference_first_copy_task(request)
    receipt = validate_reference_first_copy_task(path, request)
    assert len(commands) == 1
    assert "phaser.search_copies=1" in commands[0]
    assert (
        f"phaser.component_copies={receipt.task.hypothesis.copy_count_expected}"
        in commands[0]
    )
    assert "phaser.keywords.general.jobs=4" in commands[0]
    assert (
        receipt.result.execution_status
        == {
            "hit": "completed_hit",
            "no_hit": "completed_no_hit",
            "tool_failure": "failed_tool_execution",
            "parse_failure": "failed_parse",
        }[outcome]
    )
    assert receipt.execution_authority_kind == "truth_blind_rf_reference"
    assert not receipt.human_approval_granted
    if outcome == "hit":
        assert receipt.result.llg == pytest.approx(1622.879)
        assert receipt.result.tfz == pytest.approx(49.7)
        assert receipt.result.placed_copy_count == 1
        assert receipt.result.selected_solution is not None
    assert not tuple(path.parent.rglob("benchmark_advancement.json"))


@pytest.mark.parametrize("corruption", ("log", "command", "result", "foreign_file"))
def test_reference_first_copy_rejects_changed_native_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    request = _request(tmp_path, monkeypatch)
    _fake_runtime(monkeypatch, log_text=POSITIVE_LOG, write_solution=True)
    path = run_reference_first_copy_task(request)
    target = (
        path.parent
        / {
            "log": "PHASER.log",
            "command": "phaser_command.json",
            "result": "normalised_mr_result.json",
            "foreign_file": "unrecorded.txt",
        }[corruption]
    )
    target.write_text((target.read_text() if target.is_file() else "") + "\n")
    with pytest.raises(ValueError, match="receipt, original inputs or outputs changed"):
        validate_reference_first_copy_task(path, request)


@pytest.mark.parametrize("corruption", ("hypothesis", "threads", "prepared_input"))
def test_reference_first_copy_rejects_unplanned_tasks_before_native_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    request = _request(tmp_path, monkeypatch)
    commands = _fake_runtime(monkeypatch, log_text=POSITIVE_LOG, write_solution=True)
    if corruption == "hypothesis":
        request = replace(request, hypothesis_id="mrhyp_unplanned")
    elif corruption == "threads":
        request = replace(request, threads=0)
    else:
        (request.prepared_inputs.prepared_case / "reflections.mtz").write_bytes(
            b"changed"
        )
    with pytest.raises(ValueError):
        run_reference_first_copy_task(request)
    assert commands == []
    assert not request.output_directory.exists()


def test_reference_reviews_require_complete_authenticated_first_copy_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path, monkeypatch, small=True)
    prepared = bind_reference_prepared_case(inputs, tmp_path / "reference-prepared")
    tasks = json.loads(
        (prepared.parent / "cohorts/reference_cohorts.json").read_text()
    )["tasks"]
    assert 1 < len(tasks) <= 6
    commands = _fake_runtime(monkeypatch, log_text=POSITIVE_LOG, write_solution=True)
    # Unit-test simulation only. The native graph must emit independent tasks;
    # this loop invokes no external Phenix or scheduler.
    receipts = tuple(
        run_reference_first_copy_task(
            ReferenceFirstCopyRequest(
                prepared_path=prepared,
                prepared_inputs=inputs,
                hypothesis_id=task["hypothesis"]["hypothesis_id"],
                threads=4,
                output_directory=tmp_path / f"simulated-first-copy-{index}",
            )
        )
        for index, task in enumerate(tasks)
    )
    assert len(commands) == len(tasks)
    reviewed_path = build_prepared_reference_reviews(
        prepared, inputs, first_copy_receipts=receipts, output=tmp_path / "reviews"
    )
    reviewed = validate_prepared_reference_reviews(
        reviewed_path, prepared, inputs, first_copy_receipts=receipts
    )
    assert len(reviewed.first_copy_result_sha256) == len(tasks)
    assert all(
        "reference_first_copy.json" in inventory
        for inventory in reviewed.first_copy_result_sha256.values()
    )
    for label, incomplete in (
        ("missing", receipts[:-1]),
        ("duplicate", (*receipts[:-1], receipts[0])),
    ):
        with pytest.raises(ValueError, match="exact unique first-copy receipt union"):
            build_prepared_reference_reviews(
                prepared,
                inputs,
                first_copy_receipts=incomplete,
                output=tmp_path / label,
            )
        assert not (tmp_path / label).exists()
    native_log = receipts[0].parent / "PHASER.log"
    native_log.write_text(native_log.read_text() + "\n")
    with pytest.raises(ValueError, match="receipt, original inputs or outputs changed"):
        validate_prepared_reference_reviews(
            reviewed_path, prepared, inputs, first_copy_receipts=receipts
        )
