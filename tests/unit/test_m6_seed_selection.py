"""Real production review/admission parity with explicitly synthetic MR assets."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.m6_advancement import (
    M6AdvancementManifest,
    validate_m6_advancement,
)
from genome_to_diffraction.benchmarks.m6_nextflow import (
    run_m6_add_copy_task,
    run_m6_select_seeds_task,
)
from genome_to_diffraction.benchmarks.m6_stages import build_m6_stage_inventory
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.model_registry import load_all_eligible_model_registry
from genome_to_diffraction.mr.add_copy import (
    AddCopyRunRequest,
    run_additional_copy_phaser,
)
from genome_to_diffraction.mr.phaser import PhaserInputError
from genome_to_diffraction.review.mr_seed import (
    MrSeedReviewRequest,
    build_mr_seed_review,
)
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    NormalisedMrResult,
    SelectedMrSolutionEvidence,
)
from genome_to_diffraction.status import ExecutionStatus
from tests.unit.test_add_copy_phaser import NO_SOLUTION_LOG, STUBS, _fake_runtime
from tests.unit.test_m6_admission import _prepared_case


def _attempts(case: Path, output: Path) -> tuple[Path, ...]:
    hypotheses = tuple(
        MrHypothesis.model_validate_json(line)
        for line in (case / "first-copy-funnel/mr_hypotheses.jsonl")
        .read_text()
        .splitlines()
    )
    registry = load_all_eligible_model_registry(
        case / "first-copy-funnel/model_registry/all_model_registry.json"
    )
    paths: list[Path] = []
    for index, hypothesis in enumerate(hypotheses):
        root = output / hypothesis.hypothesis_id
        root.mkdir(parents=True)
        coordinate = root / "PHASER.1.pdb"
        coordinate.write_text(f"REMARK synthetic MR fixture {index}\nEND\n")
        (root / "PHASER.1.mtz").write_bytes(b"synthetic MR MTZ")
        (root / "PHASER.log").write_text("synthetic first-copy result\n")
        count = 2 if index in {8, 9} else 1
        clashes = 1 if index == 7 else 0
        selected = (
            None
            if index == 6
            else SelectedMrSolutionEvidence(
                coordinate_sha256=sha256_file(coordinate),
                placed_copy_count=count,
                annotation="synthetic fixture",
                packing_clash_count=clashes,
                tncs_annotation_present=index == 9,
            )
        )
        result = NormalisedMrResult(
            schema_version="1.0",
            hypothesis_id=hypothesis.hypothesis_id,
            tool_version="synthetic-test-not-native",
            execution_status=ExecutionStatus.COMPLETED_HIT
            if index < 10
            else ExecutionStatus.COMPLETED_NO_HIT,
            llg=200.0 - index if index < 6 else 500.0 + index,
            tfz=12.0,
            placed_copy_count=count,
            packing_summary={"top_solution_packed": True},
            selected_solution=selected,
            solution_coordinate_path=coordinate.name,
            solution_coordinate_sha256=sha256_file(coordinate),
            output_mtz_path="PHASER.1.mtz",
            output_mtz_sha256=sha256_file(root / "PHASER.1.mtz"),
            raw_log_pointer="PHASER.log",
        )
        atomic_write_json(
            root / "normalised_mr_result.json", result.model_dump(mode="json")
        )
        (root / "normalised_mr_result.jsonl").write_text(
            canonical_json_text(result) + "\n"
        )
        model = next(
            row
            for row in registry.lookup(hypothesis.sequence_group_id).models
            if row.model_id == hypothesis.model_id
        )
        atomic_write_json(
            root / "phaser_command.json",
            {
                "model_sha256": model.model_sha256,
                "model_identity_percent": 100.0,
            },
        )
        paths.append(root)
    return tuple(paths)


@pytest.fixture
def seed_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, tuple[Path, ...]]:
    case = _prepared_case(tmp_path, monkeypatch)
    return case, _attempts(case, tmp_path / "attempts")


def test_m6_uses_production_review_order_and_original_single_model(
    tmp_path: Path,
    seed_inputs: tuple[Path, tuple[Path, ...]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, attempts = seed_inputs
    seeds = run_m6_select_seeds_task(case, attempts, tmp_path / "seeds")
    validated = validate_m6_advancement(
        seeds / "benchmark_advancement.json",
        hypotheses_jsonl=case / "first-copy-funnel/mr_hypotheses.jsonl",
    )
    manifest = validated.manifest
    assert len(manifest.rows) == 25
    assert len(manifest.recommended) == 5
    assert sum(row.recommendation_rank is not None for row in manifest.rows) == 7
    assert manifest.recommended[0].copy_state == "tncs_coupled_pair"
    assert manifest.human_approval_granted is False
    assert not tuple(seeds.rglob("mr_seed_approval.json"))
    assert (seeds / "review/approved_mr_seeds.tsv").read_text().count("\n") == 1
    by_id = {row.hypothesis_id: row for row in manifest.rows}
    for index in (6, 7, 8, 10):
        assert by_id[attempts[index].name].advancement_disposition == "ineligible"
    production = build_mr_seed_review(
        MrSeedReviewRequest(
            hypotheses_jsonl=case / "first-copy-funnel/mr_hypotheses.jsonl",
            results_jsonl=seeds / "first_copy_results.jsonl",
            result_root=seeds / "first-copy-results",
            funnel_manifest=case / "first-copy-funnel/funnel_manifest.json",
            sequence_groups_jsonl=case / "eligible-candidates/sequence_groups.jsonl",
            source_records_jsonl=case / "eligible-candidates/source_records.jsonl",
            matthews_hypotheses_jsonl=case / "matthews/matthews_hypotheses.jsonl",
            pipeline_config=case / "analysis_config.json",
            output_directory=tmp_path / "production_review",
            progress=False,
        )
    )
    review = json.loads(production.manifest_json.read_text())
    assert [row.solution_id for row in manifest.rows] == [
        row["solution_id"] for row in review["items"]
    ]
    reversed_seeds = run_m6_select_seeds_task(
        case, tuple(reversed(attempts)), tmp_path / "reversed"
    )
    reversed_manifest = M6AdvancementManifest.model_validate_json(
        (reversed_seeds / "benchmark_advancement.json").read_bytes()
    )
    assert reversed_manifest.rows == manifest.rows
    # Run the real continuation adapter; simulate only the external Phenix call.
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)
    seed = manifest.recommended[0]
    child = run_m6_add_copy_task(
        case,
        seeds,
        seed.solution_id,
        STUBS / "phenix_install_manifest.json",
        tmp_path / "child",
        threads=16,
    )
    summary = json.loads((child / "additional_copy_series_summary.json").read_text())
    command = json.loads((child / "series/phaser_command.json").read_text())
    assert summary["attempt_count"] == 1
    assert summary["best_supported_copy_count"] == 2
    assert summary["human_approval_granted"] is False
    assert command["adapter_version"] == "phenix-add-copy-mr-v9-m6-truth-blind"
    assert command["benchmark_advancement_id"] == manifest.advancement_id
    assert command["search_model_sha256"] == command["original_first_copy_model_sha256"]
    assert command["search_model_sha256"] != command["parent_coordinate_sha256"]
    assert command["parent_copy_count"] == 2


def test_m6_duplicate_result_partition_fails_before_selection(
    tmp_path: Path, seed_inputs: tuple[Path, tuple[Path, ...]]
) -> None:
    case, attempts = seed_inputs
    with pytest.raises(PublicControlError, match="partitions differ"):
        run_m6_select_seeds_task(case, (*attempts[:-1], attempts[0]), tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_stage_inventory_authenticates_executed_children(
    tmp_path: Path,
    seed_inputs: tuple[Path, tuple[Path, ...]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, attempts = seed_inputs
    seeds = run_m6_select_seeds_task(case, attempts, tmp_path / "seeds")
    authority = validate_m6_advancement(
        seeds / "benchmark_advancement.json",
        hypotheses_jsonl=case / "first-copy-funnel/mr_hypotheses.jsonl",
    )
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)
    children = tuple(
        run_m6_add_copy_task(
            case,
            seeds,
            row.solution_id,
            STUBS / "phenix_install_manifest.json",
            tmp_path / f"child_{index}",
            threads=16,
        )
        for index, row in enumerate(authority.manifest.recommended)
    )
    inventory = build_m6_stage_inventory(case, seeds, children)
    assert inventory.scheduled.hypothesis_tasks == 25
    assert (
        inventory.recommended.hypothesis_tasks
        == inventory.advanced.hypothesis_tasks
        == 5
    )
    assert [row.scheduled_rank for row in inventory.rows] == list(range(1, 26))
    hypotheses = [
        json.loads(line)
        for line in (case / "first-copy-funnel/mr_hypotheses.jsonl")
        .read_text()
        .splitlines()
    ]
    assert [row.hypothesis_id for row in inventory.rows] == [
        row["hypothesis_id"] for row in hypotheses
    ]
    assert inventory.scheduled.unique_proteins == len(
        {row["sequence_group_id"] for row in hypotheses}
    )
    assert inventory.scheduled.unique_models == len(
        {row["model_id"] for row in hypotheses}
    )
    assert inventory.scheduled.expected_copy_states == len(
        {(row["sequence_group_id"], row["copy_count_expected"]) for row in hypotheses}
    )
    assert build_m6_stage_inventory(case, seeds, tuple(reversed(children))) == inventory
    with pytest.raises(ValueError, match="missing or foreign continuation"):
        build_m6_stage_inventory(case, seeds, children[:-1])
    with pytest.raises(ValueError, match="duplicate continuation"):
        build_m6_stage_inventory(case, seeds, (*children[:-1], children[0]))
    parent_path = children[0] / "best_parent.json"
    parent = json.loads(parent_path.read_text())
    parent["best_supported_copy_count"] += 1
    atomic_write_json(parent_path, parent)
    with pytest.raises(ValueError, match="retained parent or terminal state"):
        build_m6_stage_inventory(case, seeds, children)


def test_m6_no_credible_seed_retains_all_review_evidence(
    tmp_path: Path, seed_inputs: tuple[Path, tuple[Path, ...]]
) -> None:
    case, attempts = seed_inputs
    for attempt in attempts:
        result = NormalisedMrResult.model_validate_json(
            (attempt / "normalised_mr_result.json").read_bytes()
        ).model_copy(update={"execution_status": ExecutionStatus.COMPLETED_NO_HIT})
        atomic_write_json(
            attempt / "normalised_mr_result.json", result.model_dump(mode="json")
        )
        (attempt / "normalised_mr_result.jsonl").write_text(
            canonical_json_text(result) + "\n"
        )
    seeds = run_m6_select_seeds_task(case, attempts, tmp_path / "seeds")
    authority = validate_m6_advancement(
        seeds / "benchmark_advancement.json",
        hypotheses_jsonl=case / "first-copy-funnel/mr_hypotheses.jsonl",
    )
    assert len(authority.manifest.rows) == 25
    assert not authority.manifest.recommended
    assert (seeds / "seed_tasks.jsonl").read_text() == ""
    assert json.loads((seeds / "seed_plan.json").read_text())["typed_outcome"] == (
        "completed_no_credible_seed"
    )


@pytest.mark.parametrize(
    "mutation", ["stale_checksum", "fabricated_selection", "cap", "human_approval"]
)
def test_benchmark_authority_rejects_tampering(
    tmp_path: Path, seed_inputs: tuple[Path, tuple[Path, ...]], mutation: str
) -> None:
    case, attempts = seed_inputs
    seeds = run_m6_select_seeds_task(case, attempts, tmp_path / "seeds")
    path = seeds / "benchmark_advancement.json"
    document = json.loads(path.read_text())
    if mutation == "stale_checksum":
        document["review_manifest_sha256"] = "0" * 64
    elif mutation == "fabricated_selection":
        document["rows"][-1]["advancement_disposition"] = "recommended"
    elif mutation == "cap":
        document["seed_cap"] = 6
    else:
        document["human_approval_granted"] = True
    document["advancement_id"] = content_id(
        "m6advance_",
        {key: value for key, value in document.items() if key != "advancement_id"},
    )
    atomic_write_json(path, document)
    with pytest.raises(ValueError):
        validate_m6_advancement(
            path, hypotheses_jsonl=case / "first-copy-funnel/mr_hypotheses.jsonl"
        )


def test_benchmark_does_not_bypass_default_human_gate_or_accept_model_override(
    tmp_path: Path, seed_inputs: tuple[Path, tuple[Path, ...]]
) -> None:
    case, attempts = seed_inputs
    seeds = run_m6_select_seeds_task(case, attempts, tmp_path / "seeds")
    document = M6AdvancementManifest.model_validate_json(
        (seeds / "benchmark_advancement.json").read_bytes()
    )
    seed = document.recommended[0]
    request = AddCopyRunRequest(
        review_validation_json=None,
        review_package_manifest=None,
        seed_solution_id=seed.solution_id,
        hypotheses_jsonl=case / "first-copy-funnel/mr_hypotheses.jsonl",
        sequence_groups_jsonl=case / "eligible-candidates/sequence_groups.jsonl",
        preflight_jsonl=case / "preflight_bundle/preflight/mtz_preflight.jsonl",
        mtz=case / "reflections.mtz",
        search_model=seeds / "seed_tasks" / seed.solution_id / "search_model.pdb",
        phenix_manifest=STUBS / "phenix_install_manifest.json",
        output_directory=tmp_path / "blocked",
        progress=False,
    )
    with pytest.raises(PhaserInputError, match="requires its approval pair"):
        run_additional_copy_phaser(request)
    with pytest.raises(PhaserInputError, match="rejects human/staged-model overrides"):
        run_additional_copy_phaser(
            replace(
                request,
                benchmark_advancement_manifest=seeds / "benchmark_advancement.json",
                expected_search_model_sha256="0" * 64,
            )
        )
