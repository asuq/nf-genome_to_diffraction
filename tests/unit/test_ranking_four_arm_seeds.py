"""Paired reference recommendations with real review validation, synthetic MR."""

import json
import shutil
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.m6_advancement import validate_m6_advancement
from genome_to_diffraction.benchmarks.m6_nextflow import (
    M6HypothesisGroupTask,
    run_m6_select_seeds_task,
)
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.model_registry import load_all_eligible_model_registry
from genome_to_diffraction.ranking import (
    DiverseFirstCopyFunnelRequest,
    build_diverse_first_copy_funnel,
)
from genome_to_diffraction.ranking.funnel import FunnelInputError
from genome_to_diffraction.review.mr_seed import MrSeedReviewError
from genome_to_diffraction.schemas.results import (
    NormalisedMrResult,
    SelectedMrSolutionEvidence,
)
from genome_to_diffraction.status import ExecutionStatus
from tests.fixtures.ranking_four_arm_admission import reference_admission_plan
from tests.fixtures.ranking_four_arm_reference import AdmissionPrior
from tests.fixtures.ranking_four_arm_seeds import reference_seed_recommendations
from tests.unit.test_m6_seed_selection import _attempts
from tests.unit.test_ranking_four_arm_admission import _large_request


def _review_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prior: AdmissionPrior,
    *,
    no_hits: bool = False,
) -> tuple[DiverseFirstCopyFunnelRequest, Path, Path]:
    request = _large_request(tmp_path, monkeypatch)
    production = build_diverse_first_copy_funnel(request)
    plan = reference_admission_plan(request, admission_prior=prior)
    # Keep the original production output intact. This separate test bundle is
    # explicitly reference-labelled and uses only verified original model bytes.
    case = tmp_path / "reference_case"
    funnel = case / "first-copy-funnel"
    funnel.mkdir(parents=True)
    shutil.copytree(production.model_registry_directory, funnel / "model_registry")
    registry = load_all_eligible_model_registry(
        funnel / "model_registry/all_model_registry.json"
    )
    hypotheses = tuple(row.hypothesis for row in plan.selected)
    hypothesis_path = funnel / "mr_hypotheses.jsonl"
    hypothesis_path.write_text(
        "".join(f"{canonical_json_text(row)}\n" for row in hypotheses)
    )
    (funnel / "hypotheses").mkdir()
    entries: list[dict[str, object]] = []
    for hypothesis in hypotheses:
        (funnel / "hypotheses" / f"{hypothesis.hypothesis_id}.jsonl").write_text(
            canonical_json_text(hypothesis) + "\n"
        )
        model = next(
            row
            for row in registry.lookup(hypothesis.sequence_group_id).models
            if row.model_id == hypothesis.model_id
        )
        entries.append(
            {
                "hypothesis_id": hypothesis.hypothesis_id,
                "model_id": model.model_id,
                "model_path": f"model_registry/{model.model_path}",
                "model_sha256": model.model_sha256,
                "coordinate_id": model.coordinate_id,
                "coordinate_provider": model.provider,
                "matthews_hypothesis_id": hypothesis.priority_features[
                    "matthews_hypothesis_id"
                ],
            }
        )
    identity = {"prior": prior, "hypotheses": entries, "inputs": plan.input_sha256}
    atomic_write_json(
        funnel / "funnel_manifest.json",
        {
            "schema_version": "1.0",
            "adapter_version": "synthetic-rf-reference-admission-fixture",
            "funnel_id": content_id("rffixture_", identity),
            "selected_hypothesis_count": len(hypotheses),
            "hypotheses": entries,
            "execution_status": "completed_success",
        },
    )
    (case / "matthews").mkdir()
    shutil.copy2(
        request.matthews_hypotheses_jsonl, case / "matthews/matthews_hypotheses.jsonl"
    )
    shutil.copy2(request.pipeline_config, case / "analysis_config.json")
    shutil.copytree(request.sequence_groups_jsonl.parent, case / "eligible-candidates")
    task = M6HypothesisGroupTask(
        schema_version="1.0",
        adapter_version="m6-nextflow-case-v3-eligible-inventory",
        case_id=request.crystal_ids[0],
        catalogue_key="a" * 64,
        hypothesis_count=len(hypotheses),
        hypothesis_ids=tuple(row.hypothesis_id for row in hypotheses),
    )
    atomic_write_json(case / "case_plan.json", task.model_dump(mode="json"))
    attempts = _attempts(case, tmp_path / "reference_attempts")
    # Explicit anti-prior synthetic score assignment makes the comparison probe
    # change top-five membership. This never modifies native MR or known truth.
    prior_order = sorted(
        plan.selected, key=lambda row: (row.order_key, row.hypothesis.hypothesis_id)
    )
    scores = {
        row.hypothesis.hypothesis_id: 100.0 + index
        for index, row in enumerate(prior_order)
    }
    for root in attempts:
        old = NormalisedMrResult.model_validate_json(
            (root / "normalised_mr_result.json").read_bytes()
        )
        result = old.model_copy(
            update={
                "execution_status": ExecutionStatus.COMPLETED_NO_HIT
                if no_hits
                else ExecutionStatus.COMPLETED_HIT,
                "llg": scores[old.hypothesis_id],
                "placed_copy_count": 1,
                "selected_solution": SelectedMrSolutionEvidence(
                    coordinate_sha256=sha256_file(root / "PHASER.1.pdb"),
                    placed_copy_count=1,
                    annotation="synthetic paired-reference fixture",
                    packing_clash_count=0,
                    tncs_annotation_present=False,
                ),
            }
        )
        result = NormalisedMrResult.model_validate(result.model_dump())
        atomic_write_json(
            root / "normalised_mr_result.json", result.model_dump(mode="json")
        )
        (root / "normalised_mr_result.jsonl").write_text(
            canonical_json_text(result) + "\n"
        )
    seeds = run_m6_select_seeds_task(case, attempts, tmp_path / "reference_seeds")
    return request, hypothesis_path, seeds


@pytest.mark.parametrize("prior", ("copy_weighted", "solvent_density"))
def test_paired_reference_recommendations_use_identical_validated_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prior: AdmissionPrior
) -> None:
    request, hypotheses, seeds = _review_case(tmp_path, monkeypatch, prior)
    review = seeds / "review/mr_seed_review_manifest.json"
    mr_led = reference_seed_recommendations(
        request,
        hypotheses_jsonl=hypotheses,
        review_manifest=review,
        admission_prior=prior,
        review_order="mr_led",
    )
    prior_first = reference_seed_recommendations(
        request,
        hypotheses_jsonl=hypotheses,
        review_manifest=review,
        admission_prior=prior,
        review_order="prior_first",
    )
    assert len(mr_led.rows) == len(prior_first.rows) == 25
    assert len(mr_led.recommended) == len(prior_first.recommended) == 5
    assert mr_led.input_sha256 == prior_first.input_sha256
    assert {row.original.hypothesis_id for row in mr_led.rows} == {
        row.original.hypothesis_id for row in prior_first.rows
    }
    assert {row.original.hypothesis_id for row in mr_led.recommended} != {
        row.original.hypothesis_id for row in prior_first.recommended
    }
    assert all(row.original.recommendation_rank is not None for row in mr_led.rows)
    validated = validate_m6_advancement(
        seeds / "benchmark_advancement.json", hypotheses_jsonl=hypotheses
    )
    if prior == "copy_weighted":
        assert tuple(row.original for row in mr_led.rows) == validated.manifest.rows
        assert (
            tuple(row.original for row in mr_led.recommended)
            == validated.manifest.recommended
        )
    assert not tuple(tmp_path.rglob("additional_copy_series_results.jsonl"))
    assert not tuple(tmp_path.rglob("mr_seed_approval.json"))


def test_reference_no_hit_review_does_not_fabricate_recommendations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, hypotheses, seeds = _review_case(
        tmp_path, monkeypatch, "copy_weighted", no_hits=True
    )
    result = reference_seed_recommendations(
        request,
        hypotheses_jsonl=hypotheses,
        review_manifest=seeds / "review/mr_seed_review_manifest.json",
        admission_prior="copy_weighted",
        review_order="prior_first",
    )
    assert len(result.rows) == 25
    assert not result.recommended
    assert all(row.recommendation_rank is None for row in result.rows)


@pytest.mark.parametrize("corruption", ("cohort", "result", "model", "manifest"))
def test_reference_recommendations_reject_foreign_or_changed_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    request, hypotheses, seeds = _review_case(tmp_path, monkeypatch, "copy_weighted")
    review = seeds / "review/mr_seed_review_manifest.json"
    if corruption == "cohort":
        hypotheses.write_text("\n".join(hypotheses.read_text().splitlines()[1:]) + "\n")
    elif corruption == "result":
        document = json.loads(review.read_text())
        result = (
            review.parent / document["items"][0]["copied_assets"]["normalised_result"]
        )
        result.write_text("changed synthetic result\n")
    elif corruption == "model":
        path = request.model_preparation_manifests[0]
        manifest = json.loads(path.read_text())
        (path.parent / manifest["entries"][0]["model_path"]).write_text(
            "changed synthetic model\n"
        )
    else:
        document = json.loads(review.read_text())
        document["items"][0]["inspectable_solution"] = False
        atomic_write_json(review, document)
    with pytest.raises((ValueError, FunnelInputError, MrSeedReviewError)):
        reference_seed_recommendations(
            request,
            hypotheses_jsonl=hypotheses,
            review_manifest=review,
            admission_prior="copy_weighted",
            review_order="prior_first",
        )
