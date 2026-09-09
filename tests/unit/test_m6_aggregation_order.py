"""Completion-order regression through real M6 review and receipt assembly."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.m6_nextflow import (
    run_m6_add_copy_task,
    run_m6_assemble_case_task,
    run_m6_select_finalists_task,
    run_m6_select_seeds_task,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from tests.unit.test_add_copy_phaser import NO_SOLUTION_LOG, STUBS, _fake_runtime
from tests.unit.test_m6_admission import _prepared_case
from tests.unit.test_m6_seed_selection import _attempts


def _write_refinement(root: Path, task: dict[str, object]) -> Path:
    """Synthetic terminal T12 child, not a native refinement qualification."""
    root.mkdir(parents=True)
    (root / "t12").mkdir()
    seed_id = str(task["seed_solution_id"])
    refinement_id = f"refine_{seed_id}"
    atomic_write_json(root / "finalist_task.json", task)
    atomic_write_json(
        root / "t12/brief_refinement_result.json",
        {
            "schema_version": "1.0",
            "refinement_id": refinement_id,
            "seed_solution_id": seed_id,
            "sequence_group_id": task["sequence_group_id"],
            "input_copy_count": task["input_copy_count"],
            "tool_version": "test",
            "execution_status": "failed_tool_execution",
            "command_pointer": "refine.command.json",
            "raw_log_pointer": "refine.log",
        },
    )
    atomic_write_json(
        root / "t12/sequence_map_result.json",
        {
            "schema_version": "1.0",
            "sequence_assessment_id": f"seqmap_{seed_id}",
            "refinement_id": refinement_id,
            "seed_solution_id": seed_id,
            "execution_status": "skipped_ineligible",
            "tool_version": "test",
            "complete_catalogue_group_count": 31,
            "scored_group_count": 0,
            "candidates": [],
            "command_pointer": "sequence.command.json",
            "raw_log_pointer": "sequence.log",
        },
    )
    return root


def _tree_digest(root: Path) -> tuple[tuple[str, str], ...]:
    return tuple(
        (path.relative_to(root).as_posix(), sha256_file(path))
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_case_assembly_is_byte_identical_under_refinement_completion_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _prepared_case(tmp_path, monkeypatch)
    atomic_write_json(
        case / "policy_bundle/policy/model_policy_report.json",
        {"schema_version": "1.0", "synthetic_fixture": True},
    )
    attempts = _attempts(case, tmp_path / "attempts")
    seeds = run_m6_select_seeds_task(case, attempts, tmp_path / "seeds")
    seed_rows = [
        json.loads(line)
        for line in (seeds / "seed_tasks.jsonl").read_text().splitlines()
    ]
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)
    children = tuple(
        run_m6_add_copy_task(
            case,
            seeds,
            seed["seed_solution_id"],
            STUBS / "phenix_install_manifest.json",
            tmp_path / f"copy_{index}",
            threads=16,
        )
        for index, seed in enumerate(seed_rows)
    )
    finalists = run_m6_select_finalists_task(
        case, seeds, children, tmp_path / "finalists"
    )
    tasks = [
        json.loads(line)
        for line in (finalists / "finalist_tasks.jsonl").read_text().splitlines()
    ]
    refinements = tuple(
        _write_refinement(tmp_path / f"refinement_{index}", task)
        for index, task in enumerate(tasks)
    )
    forward = run_m6_assemble_case_task(
        case, finalists, refinements, tmp_path / "forward"
    )
    reverse = run_m6_assemble_case_task(
        case, finalists, tuple(reversed(refinements)), tmp_path / "reverse"
    )
    assert _tree_digest(forward) == _tree_digest(reverse)
    records = [
        json.loads(line)
        for line in (forward / "refinement_results.jsonl").read_text().splitlines()
    ]
    assert [row["seed_solution_id"] for row in records] == sorted(
        task["seed_solution_id"] for task in tasks
    )
    case_record = json.loads((forward / "case_record.json").read_text())
    stages = case_record["stage_inventory"]
    assert stages["scheduled"]["hypothesis_tasks"] == 25
    assert stages["advanced"]["hypothesis_tasks"] == 5
    assert case_record["first_copy_attempt_count"] == 25
    assert case_record["additional_copy_attempt_count"] == sum(
        row["additional_copy_attempt_count"] for row in stages["rows"]
    )
    receipt = json.loads((forward / "case_evidence_manifest.json").read_text())
    assert receipt["stage_inventory_sha256"] == sha256_file(
        forward / "stage_inventory.json"
    )
    task_path = refinements[0] / "finalist_task.json"
    changed = json.loads(task_path.read_text())
    changed["input_copy_count"] += 1
    atomic_write_json(task_path, changed)
    with pytest.raises(PublicControlError, match="refinement task differs"):
        run_m6_assemble_case_task(case, finalists, refinements, tmp_path / "tampered")
