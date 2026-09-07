"""Production review, explicit benchmark authority and actual M6 advancement."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from genome_to_diffraction.benchmarks.m6_advancement import (
    validate_m6_advancement_authority,
)
from genome_to_diffraction.benchmarks.m6_nextflow import (
    M6CaseTask,
    run_m6_add_copy_task,
    run_m6_select_seeds_task,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.matthews.probability import homooligomer_copy_probability
from genome_to_diffraction.mr.add_copy import run_additional_copy_series
from genome_to_diffraction.mr.phaser import PhaserInputError
from tests.unit.test_add_copy_phaser import POSITIVE_LOG, _fake_runtime
from tests.unit.test_add_copy_phaser import _request as _copy_request
from tests.unit.test_mr_seed_review import _request as _review_request


def _case(
    tmp_path: Path, *, hit: bool = True, expected_copies: int = 1
) -> tuple[Path, Path]:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    request = _review_request(inputs, hit=hit, crystal_id="M6C001")
    case = tmp_path / "case"
    funnel = case / "first-copy-funnel"
    (funnel / "hypotheses").mkdir(parents=True)
    for source, relative in (
        (request.hypotheses_jsonl, "first-copy-funnel/mr_hypotheses.jsonl"),
        (request.sequence_groups_jsonl, "all_sequence_groups.jsonl"),
        (request.source_records_jsonl, "all_source_records.jsonl"),
        (request.matthews_hypotheses_jsonl, "matthews/matthews_hypotheses.jsonl"),
    ):
        destination = case / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (case / "analysis_config.json").write_text(
        json.dumps(yaml.safe_load(request.pipeline_config.read_text())),
        encoding="utf-8",
    )
    hypothesis = json.loads(request.hypotheses_jsonl.read_text())
    hypothesis["copy_count_expected"] = expected_copies
    (funnel / "mr_hypotheses.jsonl").write_text(
        json.dumps(hypothesis) + "\n", encoding="utf-8"
    )
    matthews_path = case / "matthews/matthews_hypotheses.jsonl"
    matthews = json.loads(matthews_path.read_text())
    matthews["copy_count"] = expected_copies
    matthews["total_mass_da"] = matthews["sequence_mass_da"] * expected_copies
    matthews["v_asu_a3"] *= expected_copies
    matthews["copy_frequency_factor"] = homooligomer_copy_probability(expected_copies)
    matthews["matthews_prior"] = (
        matthews["solvent_density"] * matthews["copy_frequency_factor"]
    )
    matthews_path.write_text(json.dumps(matthews) + "\n", encoding="utf-8")
    identifier = hypothesis["hypothesis_id"]
    (funnel / "hypotheses" / f"{identifier}.jsonl").write_text(
        json.dumps(hypothesis) + "\n", encoding="utf-8"
    )
    model = funnel / "model.pdb"
    model.write_text("original one-copy moving model\n", encoding="utf-8")
    manifest = json.loads(request.funnel_manifest.read_text())
    manifest["hypotheses"][0].update(
        model_path="model.pdb", model_sha256=sha256_file(model)
    )
    (funnel / "funnel_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (case / "case_plan.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "adapter_version": "m6-nextflow-case-v3-production-admission",
                "case_id": "M6C001",
                "catalogue_key": "a" * 64,
                "hypothesis_count": 1,
                "hypothesis_ids": [identifier],
            }
        ),
        encoding="utf-8",
    )
    task = M6CaseTask(
        schema_version="1.0",
        case_id="M6C001",
        track="operational",
        catalogue_key="a" * 64,
        reflections_sha256="b" * 64,
        analysis_config_sha256=sha256_file(case / "analysis_config.json"),
        model_policy_sha256="c" * 64,
    )
    (case / "case_task.json").write_text(canonical_json_text(task), encoding="utf-8")
    result_root = request.result_root / f"first_copy_phaser_{identifier}"
    shutil.copy2(
        result_root / "normalised_mr_result.jsonl",
        result_root / "normalised_mr_result.json",
    )
    command = json.loads((result_root / "phaser_command.json").read_text())
    command["model_sha256"] = sha256_file(model)
    (result_root / "phaser_command.json").write_text(
        json.dumps(command), encoding="utf-8"
    )
    return case, result_root


def test_selection_uses_production_review_and_explicit_benchmark_authority(
    tmp_path: Path,
) -> None:
    case, result = _case(tmp_path)
    seeds = run_m6_select_seeds_task(case, (result,), tmp_path / "seeds")
    authority, review_manifest = validate_m6_advancement_authority(
        seeds / "benchmark_advancement_manifest.json",
        hypotheses_jsonl=case / "first-copy-funnel/mr_hypotheses.jsonl",
    )
    review = json.loads(review_manifest.read_text())
    assert authority.selected_solution_ids == (review["items"][0]["solution_id"],)
    assert authority.human_approval is False
    assert not list(seeds.rglob("mr_seed_approval.json"))
    row = json.loads((seeds / "seed_tasks.jsonl").read_text())
    assert (seeds / row["search_model"]).read_bytes() == (
        case / "first-copy-funnel/model.pdb"
    ).read_bytes()
    recommendation = json.loads((seeds / "seed_advancement.jsonl").read_text())
    assert recommendation["advancement_disposition"] == "recommended"
    assert recommendation["advancement_observed"] is False
    advanced = run_m6_add_copy_task(
        case,
        seeds,
        authority.selected_solution_ids[0],
        tmp_path / "unused-phenix",
        tmp_path / "advanced",
        threads=1,
    )
    parent = json.loads((advanced / "best_parent.json").read_text())
    assert parent["advancement_observed"] is True
    assert parent["advancement_authority_kind"] == "benchmark_policy"
    summary = json.loads((advanced / "additional_copy_series_summary.json").read_text())
    assert summary["attempt_count"] == 0
    assert summary["composition_completeness"] == "not_assessed"


def test_no_eligible_seed_keeps_recommendation_and_execution_distinct(
    tmp_path: Path,
) -> None:
    case, result = _case(tmp_path, hit=False)
    seeds = run_m6_select_seeds_task(case, (result,), tmp_path / "seeds")
    assert not (seeds / "benchmark_advancement_manifest.json").exists()
    assert (seeds / "seed_tasks.jsonl").read_text() == ""
    plan = json.loads((seeds / "seed_plan.json").read_text())
    assert plan["selected_seed_count"] == 0
    assert plan["actually_advanced_seed_count"] == 0


def test_benchmark_authority_rejects_changed_selected_evidence(tmp_path: Path) -> None:
    case, result = _case(tmp_path)
    seeds = run_m6_select_seeds_task(case, (result,), tmp_path / "seeds")
    (seeds / "production_review/mr_seed_candidates.tsv").write_text(
        "changed evidence\n"
    )
    with pytest.raises(ValueError, match="checksum"):
        validate_m6_advancement_authority(
            seeds / "benchmark_advancement_manifest.json",
            hypotheses_jsonl=case / "first-copy-funnel/mr_hypotheses.jsonl",
        )


def test_duplicate_first_copy_results_cannot_replace_a_scheduled_hypothesis(
    tmp_path: Path,
) -> None:
    case, result = _case(tmp_path)
    plan_path = case / "case_plan.json"
    plan = json.loads(plan_path.read_text())
    plan["hypothesis_ids"].append("mrhyp_" + "f" * 64)
    plan["hypothesis_count"] = 2
    plan_path.write_text(json.dumps(plan))
    with pytest.raises(PublicControlError, match="identities differ"):
        run_m6_select_seeds_task(case, (result, result), tmp_path / "seeds")


def test_shared_copy_execution_rejects_mixed_authority(tmp_path: Path) -> None:
    request = _copy_request(tmp_path)
    request = replace(
        request, benchmark_advancement_manifest=tmp_path / "benchmark.json"
    )
    with pytest.raises(PhaserInputError, match="mixed human/benchmark authority"):
        run_additional_copy_series(request)


def test_benchmark_authority_uses_shared_copy_execution_and_binds_command_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, result = _case(tmp_path, expected_copies=2)
    seeds = run_m6_select_seeds_task(case, (result,), tmp_path / "seeds")
    seed = json.loads((seeds / "seed_tasks.jsonl").read_text())
    copy_request = _copy_request(tmp_path / "copy-inputs", expected_copy_count=2)
    preflight = json.loads(copy_request.preflight_jsonl.read_text())
    preflight["crystal_id"] = "M6C001"
    copy_request.preflight_jsonl.write_text(json.dumps(preflight) + "\n")
    copy_request = replace(
        copy_request,
        review_validation_json=None,
        review_package_manifest=None,
        benchmark_advancement_manifest=seeds / "benchmark_advancement_manifest.json",
        seed_solution_id=seed["seed_solution_id"],
        hypotheses_jsonl=case / "first-copy-funnel/mr_hypotheses.jsonl",
        search_model=seeds / seed["search_model_path"],
        expected_search_model_sha256=seed["search_model_sha256"],
    )
    _fake_runtime(monkeypatch, log_text=POSITIVE_LOG, write_solution=True)
    series = run_additional_copy_series(copy_request)
    assert len(series.attempts) == 1
    command = json.loads(series.attempts[0].command_json.read_text())
    assert (
        command["benchmark_advancement_authority"]["authority_kind"]
        == "benchmark_policy"
    )
    assert command["search_model_sha256"] == seed["search_model_sha256"]
    assert command["parent_coordinate_sha256"] != command["search_model_sha256"]
