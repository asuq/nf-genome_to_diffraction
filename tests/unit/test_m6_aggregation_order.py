"""Completion-order regressions for the active M6 case aggregation boundary."""

import json
from pathlib import Path

from genome_to_diffraction.benchmarks.m6_nextflow import run_m6_assemble_case_task
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import sequence_digest

HASH = "a" * 64


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{json.dumps(row, sort_keys=True)}\n" for row in rows),
        encoding="utf-8",
    )


def _sequence_group(sequence: str) -> dict[str, object]:
    digest = sequence_digest(sequence)
    return {
        "schema_version": "1.0",
        "sequence_group_id": f"seq_{digest}",
        "sha256": digest,
        "sequence": sequence,
        "length_aa": len(sequence),
        "molecular_mass_da": 3500.0,
        "molecular_mass_lower_da": None,
        "molecular_mass_upper_da": None,
        "mass_method": "test",
        "residue_policy": "test",
        "source_record_count": 1,
        "quality_flags": [],
    }


def _write_case_bundle(root: Path) -> tuple[Path, tuple[dict[str, object], ...]]:
    groups = (_sequence_group("A" * 50), _sequence_group("C" * 50))
    hypotheses: list[dict[str, object]] = []
    seed_rows: list[dict[str, object]] = []
    for suffix, group in zip(("a", "b"), groups, strict=True):
        hypothesis_id = f"hyp_{suffix}"
        seed_id = f"sol_{suffix}"
        group_id = str(group["sequence_group_id"])
        hypotheses.append(
            {
                "schema_version": "1.0",
                "hypothesis_id": hypothesis_id,
                "crystal_id": "M6C001",
                "sequence_group_id": group_id,
                "model_id": f"model_{suffix}",
                "copy_count_expected": 1,
                "copy_number_to_search": 1,
                "fixed_solution_id": None,
                "space_group": "P 1",
                "obs_labels": "F,SIGF",
                "search_stage": "first_copy",
                "resource_profile": "smoke",
                "priority_features": {},
                "status": "completed_hit",
            }
        )
        seed_rows.append(
            {
                "schema_version": "1.0",
                "case_id": "M6C001",
                "seed_solution_id": seed_id,
                "hypothesis_id": hypothesis_id,
                "sequence_group_id": group_id,
                "model_id": f"model_{suffix}",
                "expected_copy_count": 1,
                "first_copy_placed_count": 1,
                "search_model_sha256": HASH,
            }
        )
    _write_json(
        root / "case_plan.json",
        {
            "schema_version": "1.0",
            "adapter_version": "m6-nextflow-case-v2",
            "case_id": "M6C001",
            "catalogue_key": HASH,
            "early_outcome": None,
            "hypothesis_count": 2,
            "hypothesis_ids": ["hyp_a", "hyp_b"],
        },
    )
    _write_json(
        root / "case_task.json",
        {
            "schema_version": "1.0",
            "case_id": "M6C001",
            "track": "operational",
            "catalogue_key": HASH,
            "reflections_sha256": HASH,
            "analysis_config_sha256": HASH,
            "model_policy_sha256": HASH,
            "fault_control_sha256": None,
        },
    )
    _write_jsonl(root / "all_sequence_groups.jsonl", list(groups))
    _write_jsonl(
        root / "all_source_records.jsonl",
        [
            {
                "schema_version": "1.0",
                "source_record_id": f"src_{index}",
                "catalogue_id": "stub",
                "original_protein_id": f"protein_{index}",
                "original_header": f"protein_{index}",
                "sequence_group_id": group["sequence_group_id"],
                "source_annotation_provider": "stub",
            }
            for index, group in enumerate(groups, start=1)
        ],
    )
    for hypothesis in hypotheses:
        _write_jsonl(
            root
            / "first-copy-funnel/hypotheses"
            / f"{hypothesis['hypothesis_id']}.jsonl",
            [hypothesis],
        )
    return root, tuple(seed_rows)


def _write_finalist_bundle(
    root: Path, seed_rows: tuple[dict[str, object], ...]
) -> Path:
    _write_json(
        root / "finalist_plan.json",
        {
            "schema_version": "1.0",
            "adapter_version": "m6-nextflow-finalists-v1",
            "case_id": "M6C001",
            "finalist_count": 2,
            "all_seed_parents_retained": True,
        },
    )
    _write_jsonl(root / "seed_bundle/seed_tasks.jsonl", list(seed_rows))
    _write_json(
        root / "seed_bundle/seed_plan.json",
        {
            "schema_version": "1.0",
            "adapter_version": "m6-nextflow-seeds-v2",
            "case_id": "M6C001",
            "selected_seed_count": 2,
            "typed_outcome": None,
        },
    )
    (root / "add-copy-results").mkdir(parents=True)
    for seed in seed_rows:
        hypothesis_id = str(seed["hypothesis_id"])
        _write_json(
            root
            / "seed_bundle/first-copy-results"
            / hypothesis_id
            / "normalised_mr_result.json",
            {
                "schema_version": "1.0",
                "hypothesis_id": hypothesis_id,
                "tool_version": "test",
                "execution_status": "completed_hit",
                "llg": 100.0,
                "tfz": 10.0,
                "placed_copy_count": 1,
                "packing_summary": {"top_solution_packed": True},
                "raw_log_pointer": f"{hypothesis_id}.log",
            },
        )
    return root


def _write_refinement(root: Path, seed: dict[str, object]) -> Path:
    seed_id = str(seed["seed_solution_id"])
    group_id = str(seed["sequence_group_id"])
    refinement_id = f"refine_{seed_id}"
    _write_json(
        root / "finalist_task.json",
        {
            "schema_version": "1.0",
            "case_id": "M6C001",
            "seed_solution_id": seed_id,
            "sequence_group_id": group_id,
            "input_copy_count": 1,
            "parent_coordinate_sha256": HASH,
            "parent_mtz_sha256": HASH,
            "observation_labels": "F,SIGF",
            "resolution": 2.0,
        },
    )
    _write_json(
        root / "t12/brief_refinement_result.json",
        {
            "schema_version": "1.0",
            "refinement_id": refinement_id,
            "seed_solution_id": seed_id,
            "sequence_group_id": group_id,
            "input_copy_count": 1,
            "tool_version": "test",
            "execution_status": "failed_tool_execution",
            "command_pointer": "refine.command.json",
            "raw_log_pointer": "refine.log",
        },
    )
    _write_json(
        root / "t12/sequence_map_result.json",
        {
            "schema_version": "1.0",
            "sequence_assessment_id": f"seqmap_{seed_id}",
            "refinement_id": refinement_id,
            "seed_solution_id": seed_id,
            "execution_status": "skipped_ineligible",
            "tool_version": "test",
            "complete_catalogue_group_count": 2,
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
    tmp_path: Path,
) -> None:
    case, seed_rows = _write_case_bundle(tmp_path / "case")
    finalists = _write_finalist_bundle(tmp_path / "finalists", seed_rows)
    first = _write_refinement(tmp_path / "refinement-b", seed_rows[1])
    second = _write_refinement(tmp_path / "refinement-a", seed_rows[0])

    forward = run_m6_assemble_case_task(
        case,
        finalists,
        (first, second),
        tmp_path / "forward",
    )
    reverse = run_m6_assemble_case_task(
        case,
        finalists,
        (second, first),
        tmp_path / "reverse",
    )

    assert _tree_digest(forward) == _tree_digest(reverse)
    refinements = (forward / "refinement_results.jsonl").read_text(encoding="utf-8")
    assert refinements.index("sol_a") < refinements.index("sol_b")
