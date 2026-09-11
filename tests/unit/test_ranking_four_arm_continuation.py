"""Original prepared/reference copy joins with explicitly simulated Phenix only."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.fixtures.ranking_four_arm_continuation import (
    ReferenceContinuationInputs,
    ReferencePreparedCopyRequest,
    reference_copy_tasks,
    run_prepared_reference_copy_task,
    validate_prepared_reference_copy_task,
)
from tests.fixtures.ranking_four_arm_first_copy import (
    ReferenceFirstCopyRequest,
    build_prepared_reference_reviews,
    run_reference_first_copy_task,
)
from tests.fixtures.ranking_four_arm_prepared import bind_reference_prepared_case
from tests.unit.test_add_copy_phaser import (
    NO_SOLUTION_LOG as COPY_NO_SOLUTION,
)
from tests.unit.test_add_copy_phaser import (
    POSITIVE_LOG as COPY_POSITIVE,
)
from tests.unit.test_add_copy_phaser import (
    _fake_runtime as copy_runtime,
)
from tests.unit.test_phaser_adapter import NO_SOLUTION_LOG, POSITIVE_LOG, _fake_runtime
from tests.unit.test_ranking_four_arm_prepared import _inputs as prepared_inputs


def _inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, no_hit: bool = False
) -> ReferenceContinuationInputs:
    original = prepared_inputs(tmp_path, monkeypatch, small=True)
    prepared = bind_reference_prepared_case(original, tmp_path / "reference-prepared")
    tasks = json.loads(
        (prepared.parent / "cohorts/reference_cohorts.json").read_text()
    )["tasks"]
    _fake_runtime(
        monkeypatch,
        log_text=NO_SOLUTION_LOG if no_hit else POSITIVE_LOG,
        write_solution=not no_hit,
    )
    # Only a unit-test simulator. Native independent items must fan out in Nextflow.
    receipts = tuple(
        run_reference_first_copy_task(
            ReferenceFirstCopyRequest(
                prepared_path=prepared,
                prepared_inputs=original,
                hypothesis_id=task["hypothesis"]["hypothesis_id"],
                threads=2,
                output_directory=tmp_path / f"simulated-first-copy-{index}",
            )
        )
        for index, task in enumerate(tasks)
    )
    reviews = build_prepared_reference_reviews(
        prepared,
        original,
        first_copy_receipts=receipts,
        output=tmp_path / "reference-reviews",
    )
    return ReferenceContinuationInputs(prepared, original, reviews, receipts)


def _request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ReferencePreparedCopyRequest:
    inputs = _inputs(tmp_path, monkeypatch)
    tasks = reference_copy_tasks(inputs)
    assert 1 < len(tasks) <= 12
    task = next(task for task in tasks if task.expected_copy_count > 1)
    return ReferencePreparedCopyRequest(
        inputs=inputs,
        admission_prior=task.admission_prior,
        seed_solution_id=task.seed_solution_id,
        threads=16,
        output_directory=tmp_path / "reference-copy",
    )


@pytest.mark.parametrize("supported", (False, True))
def test_prepared_copy_preserves_original_native_inputs_and_prior_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, supported: bool
) -> None:
    request = _request(tmp_path, monkeypatch)
    copy_runtime(
        monkeypatch,
        log_text=COPY_POSITIVE if supported else COPY_NO_SOLUTION,
        write_solution=supported,
        placement_count=(2, 2),
    )
    path = run_prepared_reference_copy_task(request)
    receipt = validate_prepared_reference_copy_task(path, request)
    assert receipt.native_attempt_count >= 1
    assert not receipt.human_approval_granted
    command = json.loads((path.parent / "series/phaser_command.json").read_text())
    assert command["threads"] == 16
    assert command["timeout_seconds"] is None
    assert command["execution_authority_kind"] == "truth_blind_rf_reference"
    assert command["benchmark_advancement_manifest_sha256"] == (
        receipt.task.advancement_manifest_sha256
    )
    assert command["search_model_sha256"] == command["original_first_copy_model_sha256"]
    assert not tuple(path.parent.rglob("benchmark_advancement.json"))


@pytest.mark.parametrize("corruption", ("seed", "threads", "missing_first_copy"))
def test_prepared_copy_rejects_unplanned_inputs_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    request = _request(tmp_path, monkeypatch)
    if corruption == "seed":
        request = replace(request, seed_solution_id="mrsol_unplanned")
    elif corruption == "threads":
        request = replace(request, threads=True)
    else:
        request = replace(
            request,
            inputs=replace(
                request.inputs,
                first_copy_receipts=request.inputs.first_copy_receipts[:-1],
            ),
        )
    with pytest.raises(ValueError):
        run_prepared_reference_copy_task(request)
    assert not request.output_directory.exists()


@pytest.mark.parametrize("corruption", ("native_log", "phenix", "command_threads"))
def test_prepared_copy_rejects_changed_runtime_or_native_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    request = _request(tmp_path, monkeypatch)
    copy_runtime(monkeypatch, log_text=COPY_NO_SOLUTION, write_solution=False)
    path = run_prepared_reference_copy_task(request)
    if corruption == "native_log":
        log = path.parent / "series/PHASER.log"
        log.write_text(log.read_text() + "\nchanged synthetic log\n")
    elif corruption == "phenix":
        other = tmp_path / "different-phenix.json"
        other.write_bytes(
            request.inputs.prepared_inputs.phenix_manifest.read_bytes() + b"\n"
        )
        request = replace(
            request,
            inputs=replace(
                request.inputs,
                prepared_inputs=replace(
                    request.inputs.prepared_inputs, phenix_manifest=other
                ),
            ),
        )
    else:
        target = path.parent / "series/phaser_command.json"
        command = json.loads(target.read_text())
        command["threads"] = 3
        target.write_text(json.dumps(command))
    with pytest.raises(ValueError):
        validate_prepared_reference_copy_task(path, request)


def test_prepared_no_hit_reviews_emit_no_copy_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path, monkeypatch, no_hit=True)
    assert reference_copy_tasks(inputs) == ()
    assert not tuple(tmp_path.rglob("reference_copy.json"))
