"""Authenticated RF copy-to-finalist joins; all native responses are synthetic."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import tests.fixtures.ranking_four_arm_finalists as finalists_module
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.mr.add_copy import AddCopyRunRequest
from genome_to_diffraction.ranking import DiverseFirstCopyFunnelRequest
from tests.fixtures.ranking_four_arm_continuation import (
    ReferenceCopyTask,
    ReferencePreparedCopyReceipt,
    ReferencePreparedCopyRequest,
    reference_copy_tasks,
    run_prepared_reference_copy_task,
)
from tests.fixtures.ranking_four_arm_finalists import (
    build_reference_finalists,
    validate_reference_finalists,
)
from tests.unit.test_add_copy_phaser import NO_SOLUTION_LOG, _fake_runtime
from tests.unit.test_ranking_four_arm_continuation import _inputs


def test_reference_finalists_require_actual_complete_prior_bound_copy_union(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path, monkeypatch)
    tasks = reference_copy_tasks(inputs)
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)
    # This test loops over a simulator; the native graph must fan out these items.
    receipts = tuple(
        run_prepared_reference_copy_task(
            ReferencePreparedCopyRequest(
                inputs=inputs,
                admission_prior=task.admission_prior,
                seed_solution_id=task.seed_solution_id,
                threads=16,
                output_directory=tmp_path / f"simulated-copy-{index}",
            )
        )
        for index, task in enumerate(tasks)
    )
    upstream_checks = Mock(wraps=finalists_module._context)
    monkeypatch.setattr(finalists_module, "_context", upstream_checks)
    path = build_reference_finalists(
        inputs, copy_receipts=receipts, output=tmp_path / "finalists"
    )
    manifest = validate_reference_finalists(path, inputs, copy_receipts=receipts)
    # Construction, its final check and explicit replay each authenticate the
    # whole original context at entry and exit, independent of the receipt count.
    assert upstream_checks.call_count == 6
    assert len(manifest.tasks) == len(tasks)
    assert not manifest.refinement_executed
    assert not manifest.human_approval_granted
    assert len(manifest.stages) == 2
    assert {arm.arm for stage in manifest.stages for arm in stage.arms} == {
        "A",
        "B",
        "C",
        "D",
    }
    original = inputs.prepared_inputs.prepared_case
    for row in manifest.tasks:
        bundle = path.parent / row.bundle_directory
        root = bundle / "finalist_tasks" / row.task.seed_solution_id
        assert row.task.input_copy_count == 1
        assert sha256_file(root / "parent.mtz") == sha256_file(
            original / "reflections.mtz"
        )
        for name in ("all_sequence_groups.jsonl", "all_source_records.jsonl"):
            assert sha256_file(bundle / "case_bundle" / name) == sha256_file(
                original / name
            )
    assert not tuple(path.parent.rglob("benchmark_advancement.json"))
    for label, incomplete in (
        ("missing", receipts[:-1]),
        ("duplicate", (*receipts[:-1], receipts[0])),
    ):
        with pytest.raises(ValueError, match="exact unique copy receipt union"):
            build_reference_finalists(
                inputs, copy_receipts=incomplete, output=tmp_path / label
            )
        assert not (tmp_path / label).exists()
    # Even a self-consistently rehashed output cannot replace an original parent.
    first = manifest.tasks[0]
    relative = (
        f"{first.bundle_directory}/finalist_tasks/"
        f"{first.task.seed_solution_id}/parent_coordinate.pdb"
    )
    (path.parent / relative).write_text("changed synthetic parent\n")
    document = json.loads(path.read_text())
    document["output_sha256"][relative] = sha256_file(path.parent / relative)
    document["finalists_id"] = content_id(
        "rffinalists_",
        {key: value for key, value in document.items() if key != "finalists_id"},
    )
    atomic_write_json(path, document)
    with pytest.raises(ValueError, match="tasks, stages or frozen inputs changed"):
        validate_reference_finalists(path, inputs, copy_receipts=receipts)


@pytest.mark.parametrize("mutation", ("original_first_copy_log", "review_bytes"))
def test_reference_finalists_reauthenticate_upstream_after_last_copy_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    inputs = _inputs(tmp_path, monkeypatch)
    tasks = reference_copy_tasks(inputs)
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)
    receipts = tuple(
        run_prepared_reference_copy_task(
            ReferencePreparedCopyRequest(
                inputs=inputs,
                admission_prior=task.admission_prior,
                seed_solution_id=task.seed_solution_id,
                threads=16,
                output_directory=tmp_path / f"simulated-copy-{index}",
            )
        )
        for index, task in enumerate(tasks)
    )
    original_validate = finalists_module._validate_prepared_reference_copy_outputs
    upstream_checks = Mock(wraps=finalists_module._context)
    monkeypatch.setattr(finalists_module, "_context", upstream_checks)
    copy_checks = 0

    def mutate_after_copy(
        path: Path,
        request: ReferencePreparedCopyRequest,
        *,
        task: ReferenceCopyTask,
        native: AddCopyRunRequest,
        admission: DiverseFirstCopyFunnelRequest,
        authority: Path,
    ) -> ReferencePreparedCopyReceipt:
        nonlocal copy_checks
        result = original_validate(
            path,
            request,
            task=task,
            native=native,
            admission=admission,
            authority=authority,
        )
        copy_checks += 1
        if copy_checks == len(receipts):
            target = (
                inputs.first_copy_receipts[0].parent / "PHASER.log"
                if mutation == "original_first_copy_log"
                else inputs.reviews_path
            )
            # A newline leaves the parsed review manifest identical, but its
            # original bytes must still be bound across the entire assembly.
            target.write_bytes(target.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(
        finalists_module, "_validate_prepared_reference_copy_outputs", mutate_after_copy
    )
    output = tmp_path / "changed-during-assembly"
    message = (
        "receipt, original inputs or outputs changed"
        if mutation == "original_first_copy_log"
        else "upstream context changed during assembly"
    )
    with pytest.raises(ValueError, match=message):
        build_reference_finalists(inputs, copy_receipts=receipts, output=output)
    assert copy_checks == len(receipts)
    assert upstream_checks.call_count == 2
    assert not output.exists()


def test_reference_no_hit_finalists_preserve_four_empty_advanced_inventories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path, monkeypatch, no_hit=True)
    path = build_reference_finalists(
        inputs, copy_receipts=(), output=tmp_path / "no-hit-finalists"
    )
    manifest = validate_reference_finalists(path, inputs, copy_receipts=())
    assert manifest.tasks == ()
    assert manifest.empty_admission_priors == ()
    assert len(manifest.stages) == 2
    assert all(
        arm.stages.advanced.hypothesis_tasks == 0
        for stage in manifest.stages
        for arm in stage.arms
    )
    assert not tuple(path.parent.rglob("parent_coordinate.pdb"))
