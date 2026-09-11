"""Real cohort/model materialisation from synthetic production-prepared inputs."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.model_registry import load_all_eligible_model_registry
from genome_to_diffraction.ranking import (
    DiverseFirstCopyFunnelRequest,
    build_diverse_first_copy_funnel,
)
from genome_to_diffraction.review.mr_seed import _funnel_entries
from genome_to_diffraction.schemas.results import MrHypothesis
from tests.fixtures.ranking_four_arm_admission import reference_admission_plan
from tests.fixtures.ranking_four_arm_materialisation import (
    materialise_reference_cohorts,
    validate_reference_materialisation,
)
from tests.unit.test_ranking_four_arm_admission import (
    _fixed_inputs,
    _large_request,
    _small_request,
)


def _known_request(
    request: DiverseFirstCopyFunnelRequest, *, asu_volume: float | None = None
) -> DiverseFirstCopyFunnelRequest:
    preflight = json.loads(request.mtz_preflight_jsonl.read_text())
    preflight["crystal_id"] = "M6C001"
    if asu_volume is not None:
        preflight.update(
            asu_volume_a3=asu_volume,
            cell_volume_a3=4 * asu_volume,
            unit_cell=[1.0, 1.0, 4 * asu_volume, 90.0, 90.0, 90.0],
        )
    request.mtz_preflight_jsonl.write_text(canonical_json_text(preflight) + "\n")
    return _fixed_inputs(replace(request, crystal_ids=("M6C001",)))


def test_paired_materialisation_preserves_full_models_and_production_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _known_request(_large_request(tmp_path, monkeypatch))
    raw_matthews = request.matthews_hypotheses_jsonl.read_bytes()
    production = build_diverse_first_copy_funnel(request)
    path = materialise_reference_cohorts(request, tmp_path / "reference")
    manifest = validate_reference_materialisation(path, request)
    assert not manifest.mr_executed
    assert not manifest.human_approval_granted
    assert manifest.cohorts[0].hypotheses == production.hypotheses
    assert all(len(cohort.hypotheses) == 25 for cohort in manifest.cohorts)
    assert len(manifest.tasks) <= 50
    assert len(manifest.tasks) == len(
        {
            hypothesis.hypothesis_id
            for cohort in manifest.cohorts
            for hypothesis in cohort.hypotheses
        }
    )
    for cohort in manifest.cohorts:
        directory = path.parent / cohort.admission_prior
        registry_path = directory / "model_registry/all_model_registry.json"
        registry = load_all_eligible_model_registry(registry_path)
        assert registry.manifest.model_count == 93
        assert registry.manifest.sequence_group_count == 31
        assert sha256_file(registry_path) == sha256_file(
            production.model_registry_directory / "all_model_registry.json"
        )
        plan = reference_admission_plan(request, admission_prior=cohort.admission_prior)
        assert cohort.hypotheses == tuple(row.hypothesis for row in plan.selected)
        assert (
            cohort.physical_hypothesis_count
            == len(cohort.hypotheses)
            + cohort.deferred_copy_count
            + cohort.deferred_task_count
        )
        funnel = json.loads((directory / "funnel_manifest.json").read_text())
        assert funnel["execution_authority_kind"] == "truth_blind_rf_reference"
        assert len(_funnel_entries(funnel, cohort.hypotheses)[1]) == 25
    for task in manifest.tasks:
        hypothesis = MrHypothesis.model_validate_json(
            (path.parent / task.hypothesis_path).read_text()
        )
        assert hypothesis == task.hypothesis
        assert hypothesis.copy_number_to_search == 1
    assert request.matthews_hypotheses_jsonl.read_bytes() == raw_matthews
    assert not tuple(path.parent.rglob("normalised_mr_result.json"))
    assert not tuple(path.parent.rglob("benchmark_advancement.json"))
    assert not tuple(path.parent.rglob("mr_seed_approval.json"))


def test_materialisation_emits_genuine_reference_only_physical_hypotheses(
    tmp_path: Path,
) -> None:
    request = _known_request(_small_request(tmp_path), asu_volume=25_000.0)
    path = materialise_reference_cohorts(request, tmp_path / "reference")
    manifest = validate_reference_materialisation(path, request)
    baseline, density = manifest.cohorts
    baseline_ids = {row.hypothesis_id for row in baseline.hypotheses}
    promoted = [
        row for row in density.hypotheses if row.hypothesis_id not in baseline_ids
    ]
    assert promoted
    assert len(manifest.tasks) > len(baseline.hypotheses)
    assert {row.hypothesis_id for row in promoted} <= {
        task.hypothesis.hypothesis_id for task in manifest.tasks
    }
    plan = reference_admission_plan(request, admission_prior="solvent_density")
    by_id = {row.hypothesis.hypothesis_id: row for row in plan.selected}
    for hypothesis in promoted:
        original = by_id[hypothesis.hypothesis_id].matthews.original
        assert hypothesis.priority_features["matthews_prior"] == original.matthews_prior
        assert hypothesis.copy_number_to_search == 1


@pytest.mark.parametrize(
    "corruption", ("hypothesis", "model", "physical", "task", "missing", "foreign")
)
def test_materialisation_rejects_changed_or_missing_output_evidence(
    tmp_path: Path, corruption: str
) -> None:
    request = _known_request(_small_request(tmp_path))
    path = materialise_reference_cohorts(request, tmp_path / "reference")
    if corruption == "hypothesis":
        target = path.parent / "copy_weighted/mr_hypotheses.jsonl"
    elif corruption == "model":
        registry = load_all_eligible_model_registry(
            path.parent / "copy_weighted/model_registry/all_model_registry.json"
        )
        model = next(
            model
            for group in registry.manifest.sequence_groups
            for model in group.models
        )
        target = registry.root / model.model_path
    elif corruption == "physical":
        target = path.parent / "solvent_density/physical_inventory.json"
    elif corruption == "task":
        target = path.parent / "reference_first_copy_tasks.tsv"
    elif corruption == "missing":
        (path.parent / "copy_weighted/funnel_manifest.json").unlink()
        target = None
    else:
        target = path.parent / "unrecorded.txt"
    if target is not None:
        target.write_text("changed synthetic output\n")
    with pytest.raises(ValueError, match="reference materialisation identity"):
        validate_reference_materialisation(path, request)


def test_materialisation_rejects_foreign_case_before_writing(tmp_path: Path) -> None:
    request = _small_request(tmp_path)
    output = tmp_path / "reference"
    with pytest.raises(ValueError, match="fixed known case"):
        materialise_reference_cohorts(request, output)
    assert not output.exists()


def test_materialisation_keeps_empty_admission_separate_from_mr_success(
    tmp_path: Path,
) -> None:
    request = _known_request(_small_request(tmp_path), asu_volume=1.0)
    path = materialise_reference_cohorts(request, tmp_path / "reference")
    manifest = validate_reference_materialisation(path, request)
    assert not manifest.tasks
    assert all(
        cohort.admission_status == "completed_no_model" for cohort in manifest.cohorts
    )
    assert not manifest.mr_executed
    assert not manifest.human_approval_granted
