"""Reference cohort parity on synthetic models and the real production funnel."""

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.matthews.enumerate import enumerate_group
from genome_to_diffraction.ranking import (
    DiverseFirstCopyFunnelRequest,
    build_diverse_first_copy_funnel,
)
from genome_to_diffraction.ranking.funnel import FunnelInputError
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import CrystalEntry, PipelineConfig
from genome_to_diffraction.schemas.results import (
    MtzPreflightRecord,
    SequenceGroupRecord,
)
from tests.fixtures.ranking_four_arm_admission import reference_admission_plan
from tests.unit.test_m6_admission import _prepared_case
from tests.unit.test_ranking_funnel import _diverse_request


def _fixed_inputs(
    request: DiverseFirstCopyFunnelRequest,
) -> DiverseFirstCopyFunnelRequest:
    """Re-enumerate the synthetic fixture under the unchanged native M6 budgets."""

    config = yaml.safe_load(request.pipeline_config.read_text())
    config["prototype"]["profile"] = "pilot"
    config["matthews"]["max_hypotheses_per_candidate"] = 4
    config["search_limits"]["max_first_copy_jobs"] = 25
    config["search_limits"]["max_structural_hypotheses"] = 100
    request.pipeline_config.write_text(json.dumps(config))
    typed_config = load_contract(request.pipeline_config, "pipeline-config")
    assert isinstance(typed_config, PipelineConfig)
    preflight = MtzPreflightRecord.model_validate_json(
        request.mtz_preflight_jsonl.read_bytes()
    )
    crystal = CrystalEntry(
        crystal_id=preflight.crystal_id, mtz="fixture.mtz", catalogue_id="synthetic"
    )
    groups = tuple(
        SequenceGroupRecord.model_validate_json(line)
        for line in request.sequence_groups_jsonl.read_text().splitlines()
    )
    rows = tuple(
        row
        for group in groups
        for row in enumerate_group(group, crystal, preflight, typed_config)
    )
    request.matthews_hypotheses_jsonl.write_text(
        "".join(f"{canonical_json_text(row)}\n" for row in rows)
    )
    return replace(request, maximum_first_copy_jobs=25)


def _small_request(tmp_path: Path) -> DiverseFirstCopyFunnelRequest:
    return _fixed_inputs(_diverse_request(tmp_path))


def test_reference_preserves_four_retained_but_three_per_model(tmp_path: Path) -> None:
    request = _small_request(tmp_path)
    before = request.matthews_hypotheses_jsonl.read_bytes()
    baseline = reference_admission_plan(request, admission_prior="copy_weighted")
    density = reference_admission_plan(request, admission_prior="solvent_density")
    production = build_diverse_first_copy_funnel(request)
    assert tuple(row.hypothesis for row in baseline.selected) == production.hypotheses
    assert baseline.configured_matthews_retention == 4
    assert baseline.per_model_copy_cap == 3
    assert baseline.task_cap == 25
    for plan in (baseline, density):
        assert len(plan.selected) == 6
        assert set(
            Counter(row.hypothesis.model_id for row in plan.selected).values()
        ) == {3}
        assert any(row.matthews.retained for row in plan.deferred_copy)
        assert all(not row.within_model_cap for row in plan.deferred_copy)
        assert all(row.hypothesis.copy_number_to_search == 1 for row in plan.inventory)
        assert len(plan.inventory) == (
            len(plan.selected) + len(plan.deferred_copy) + len(plan.deferred_task)
        )
    assert request.matthews_hypotheses_jsonl.read_bytes() == before
    assert {row.hypothesis.hypothesis_id for row in density.inventory} == {
        row.hypothesis.hypothesis_id for row in baseline.inventory
    }
    # This fixture is not required to change the cohort: parity and the actual
    # two-stage cap are independent of whether its solvent ranks differ.


def _large_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> DiverseFirstCopyFunnelRequest:
    case = _prepared_case(tmp_path, monkeypatch)
    return _fixed_inputs(
        DiverseFirstCopyFunnelRequest(
            coordinate_sources_jsonl=(
                tmp_path / "coordinate_stage/registration/coordinate_sources.jsonl",
            ),
            processed_models_jsonl=(case / "model-preparation/processed_models.jsonl",),
            model_preparation_manifests=(
                case / "model-preparation/model_preparation_manifest.json",
            ),
            coordinate_hit_mappings_jsonl=tmp_path
            / "coordinate_stage/registration/coordinate_hit_mappings.jsonl",
            sequence_groups_jsonl=case / "eligible-candidates/sequence_groups.jsonl",
            matthews_hypotheses_jsonl=next((case / "matthews").glob("*.jsonl")),
            mtz_preflight_jsonl=tmp_path / "preflight/preflight/mtz_preflight.jsonl",
            pipeline_config=tmp_path / "case_task/analysis_config.json",
            output_directory=tmp_path / "reference_production_funnel",
            crystal_ids=("test_crystal_01",),
            maximum_first_copy_jobs=25,
            progress=False,
        )
    )


def test_reference_global_cap_and_complete_model_join(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _large_request(tmp_path, monkeypatch)
    baseline = reference_admission_plan(request, admission_prior="copy_weighted")
    density = reference_admission_plan(request, admission_prior="solvent_density")
    assert not request.output_directory.exists()
    production = build_diverse_first_copy_funnel(request)
    assert tuple(row.hypothesis for row in baseline.selected) == production.hypotheses
    for plan in (baseline, density):
        assert len(plan.selected) == 25
        assert len({row.hypothesis.model_id for row in plan.inventory}) == 93
        assert len({row.hypothesis.sequence_group_id for row in plan.inventory}) == 31
        assert plan.deferred_task
        assert len({row.diversity_bucket for row in plan.selected}) == 25
        assert len(plan.inventory) == len(plan.selected) + len(
            plan.deferred_copy
        ) + len(plan.deferred_task)
    assert baseline.input_sha256 == density.input_sha256
    for path in (
        request.sequence_groups_jsonl,
        request.matthews_hypotheses_jsonl,
        *request.processed_models_jsonl,
        *request.coordinate_sources_jsonl,
    ):
        path.write_text("\n".join(reversed(path.read_text().splitlines())) + "\n")
    permuted = reference_admission_plan(request, admission_prior="solvent_density")
    assert permuted.selected == density.selected
    assert permuted.inventory == density.inventory


def test_solvent_reference_admits_previously_omitted_physical_copies(
    tmp_path: Path,
) -> None:
    request = _diverse_request(tmp_path)
    preflight = json.loads(request.mtz_preflight_jsonl.read_text())
    # Explicit high-copy synthetic mass/volume probe, unrelated to native inputs.
    preflight.update(
        asu_volume_a3=25_000.0,
        cell_volume_a3=100_000.0,
        unit_cell=[20.0, 50.0, 100.0, 90.0, 90.0, 90.0],
    )
    request.mtz_preflight_jsonl.write_text(json.dumps(preflight))
    request = _fixed_inputs(request)
    density = reference_admission_plan(request, admission_prior="solvent_density")
    baseline = reference_admission_plan(request, admission_prior="copy_weighted")
    promoted = [row for row in density.selected if not row.matthews.original.retained]
    assert promoted
    baseline_ids = {row.hypothesis.hypothesis_id for row in baseline.selected}
    assert all(row.hypothesis.hypothesis_id not in baseline_ids for row in promoted)
    assert all(row.hypothesis.copy_number_to_search == 1 for row in promoted)
    assert all(row.matthews.rank <= 3 for row in promoted)
    assert all(
        row.hypothesis.priority_features["matthews_prior"]
        == row.matthews.original.matthews_prior
        for row in promoted
    )


@pytest.mark.parametrize(
    "corruption", ("scope", "budget", "missing_group", "stale_factor", "model_bytes")
)
def test_reference_admission_fails_closed(tmp_path: Path, corruption: str) -> None:
    request = _small_request(tmp_path)
    if corruption == "scope":
        request = replace(request, crystal_ids=())
    elif corruption == "budget":
        config = json.loads(request.pipeline_config.read_text())
        config["search_limits"]["max_first_copy_jobs"] = 24
        request.pipeline_config.write_text(json.dumps(config))
    elif corruption in {"missing_group", "stale_factor"}:
        path = request.matthews_hypotheses_jsonl
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        if corruption == "missing_group":
            rows = []
        else:
            rows[0]["prior_reference_sha256"] = "a" * 64
        path.write_text("".join(f"{json.dumps(row)}\n" for row in rows))
    else:
        manifest_path = request.model_preparation_manifests[0]
        manifest = json.loads(manifest_path.read_text())
        model = manifest_path.parent / manifest["entries"][0]["model_path"]
        model.write_text("changed model bytes\n")
    expected_error = (
        ValueError if corruption in {"scope", "budget"} else FunnelInputError
    )
    with pytest.raises(expected_error):
        reference_admission_plan(request, admission_prior="solvent_density")
    assert not request.output_directory.exists()
