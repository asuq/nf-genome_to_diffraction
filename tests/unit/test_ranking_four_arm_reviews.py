"""Exact first-copy result union to genuine review format and reference authority."""

import json
import shutil
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.ranking import DiverseFirstCopyFunnelRequest
from genome_to_diffraction.schemas.results import NormalisedMrResult
from genome_to_diffraction.status import ExecutionStatus
from tests.fixtures.ranking_four_arm_advancement import validate_reference_advancement
from tests.fixtures.ranking_four_arm_materialisation import (
    materialise_reference_cohorts,
    validate_reference_materialisation,
)
from tests.fixtures.ranking_four_arm_reviews import (
    build_reference_reviews,
    validate_reference_reviews,
)
from tests.unit.test_m6_seed_selection import _attempts
from tests.unit.test_ranking_four_arm_admission import _large_request, _small_request
from tests.unit.test_ranking_four_arm_materialisation import _known_request


def _materialised_attempts(
    request: DiverseFirstCopyFunnelRequest, tmp_path: Path
) -> tuple[Path, tuple[Path, ...]]:
    path = materialise_reference_cohorts(request, tmp_path / "materialised")
    manifest = validate_reference_materialisation(path, request)
    case = tmp_path / "synthetic-union"
    funnel = case / "first-copy-funnel"
    funnel.mkdir(parents=True)
    shutil.copytree(
        path.parent / "copy_weighted/model_registry", funnel / "model_registry"
    )
    (funnel / "mr_hypotheses.jsonl").write_text(
        "".join(canonical_json_text(task.hypothesis) + "\n" for task in manifest.tasks)
    )
    return path, _attempts(case, tmp_path / "synthetic-attempts")


def test_reference_reviews_partition_actual_union_and_write_no_production_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _known_request(_large_request(tmp_path, monkeypatch))
    materialised, attempts = _materialised_attempts(request, tmp_path)
    originals = {
        path: sha256_file(path / "normalised_mr_result.json") for path in attempts
    }
    sources = request.sequence_groups_jsonl.parent / "source_records.jsonl"
    path = build_reference_reviews(
        materialised,
        request,
        source_records_jsonl=sources,
        first_copy_results=tuple(reversed(attempts)),
        output=tmp_path / "reviews",
    )
    manifest = validate_reference_reviews(
        path, materialised, request, source_records_jsonl=sources
    )
    materialisation = validate_reference_materialisation(materialised, request)
    assert len(manifest.first_copy_result_sha256) == len(materialisation.tasks)
    for record, cohort in zip(manifest.cohorts, materialisation.cohorts, strict=True):
        assert record.advancement_manifest is not None
        hypotheses = (
            materialised.parent / cohort.admission_prior / "mr_hypotheses.jsonl"
        )
        authority = validate_reference_advancement(
            path.parent / record.advancement_manifest,
            request,
            hypotheses_jsonl=hypotheses,
        ).manifest
        assert {row.original.hypothesis_id for row in authority.arms[0].rows} == {
            hypothesis.hypothesis_id for hypothesis in cohort.hypotheses
        }
        assert all(
            len(arm.rows) == 25 and len(arm.recommended) <= 5 for arm in authority.arms
        )
        assert not authority.human_approval_granted
        assert len(authority.recommended) <= 10
    assert originals == {
        root: sha256_file(root / "normalised_mr_result.json") for root in attempts
    }
    assert not tuple(path.parent.rglob("benchmark_advancement.json"))
    assert not tuple(path.parent.rglob("mr_seed_approval.json"))
    assert not tuple(path.parent.rglob("additional_copy_series_results.jsonl"))


@pytest.mark.parametrize(
    "corruption", ("missing", "duplicate", "foreign", "raw_log", "result")
)
def test_reference_reviews_reject_incomplete_or_changed_result_evidence(
    tmp_path: Path, corruption: str
) -> None:
    request = _known_request(_small_request(tmp_path), asu_volume=25_000.0)
    materialised, attempts = _materialised_attempts(request, tmp_path)
    sources = request.sequence_groups_jsonl.parent / "source_records.jsonl"
    if corruption == "missing":
        attempts = attempts[1:]
    elif corruption == "duplicate":
        attempts = (*attempts, attempts[0])
    elif corruption == "foreign":
        result = json.loads((attempts[0] / "normalised_mr_result.json").read_text())
        result["hypothesis_id"] = "mrhyp_" + "f" * 64
        atomic_write_json(attempts[0] / "normalised_mr_result.json", result)
    if corruption in {"missing", "duplicate", "foreign"}:
        with pytest.raises(ValueError, match="reference MR result union"):
            build_reference_reviews(
                materialised,
                request,
                source_records_jsonl=sources,
                first_copy_results=attempts,
                output=tmp_path / "reviews",
            )
        assert not (tmp_path / "reviews").exists()
        return
    path = build_reference_reviews(
        materialised,
        request,
        source_records_jsonl=sources,
        first_copy_results=attempts,
        output=tmp_path / "reviews",
    )
    if corruption == "raw_log":
        target = next((path.parent / "first-copy-results").glob("*/PHASER.log"))
    else:
        target = next(
            (path.parent / "first-copy-results").glob("*/normalised_mr_result.jsonl")
        )
    target.write_text("changed frozen synthetic evidence\n")
    with pytest.raises(ValueError, match="reference reviews identity"):
        validate_reference_reviews(
            path, materialised, request, source_records_jsonl=sources
        )


def test_reference_reviews_no_hit_results_do_not_fabricate_recommendations(
    tmp_path: Path,
) -> None:
    request = _known_request(_small_request(tmp_path))
    materialised, attempts = _materialised_attempts(request, tmp_path)
    sources = request.sequence_groups_jsonl.parent / "source_records.jsonl"
    for root in attempts:
        result = NormalisedMrResult.model_validate_json(
            (root / "normalised_mr_result.json").read_bytes()
        ).model_copy(update={"execution_status": ExecutionStatus.COMPLETED_NO_HIT})
        atomic_write_json(
            root / "normalised_mr_result.json", result.model_dump(mode="json")
        )
        (root / "normalised_mr_result.jsonl").write_text(
            canonical_json_text(result) + "\n"
        )
    path = build_reference_reviews(
        materialised,
        request,
        source_records_jsonl=sources,
        first_copy_results=attempts,
        output=tmp_path / "reviews",
    )
    manifest = validate_reference_reviews(
        path, materialised, request, source_records_jsonl=sources
    )
    for cohort in manifest.cohorts:
        assert cohort.advancement_manifest is not None
        authority = validate_reference_advancement(
            path.parent / cohort.advancement_manifest,
            request,
            hypotheses_jsonl=materialised.parent
            / cohort.admission_prior
            / "mr_hypotheses.jsonl",
        ).manifest
        assert all(not arm.recommended for arm in authority.arms)


def test_reference_empty_admission_does_not_create_review_or_authority(
    tmp_path: Path,
) -> None:
    request = _known_request(_small_request(tmp_path), asu_volume=1.0)
    materialised, attempts = _materialised_attempts(request, tmp_path)
    assert not attempts
    sources = request.sequence_groups_jsonl.parent / "source_records.jsonl"
    path = build_reference_reviews(
        materialised,
        request,
        source_records_jsonl=sources,
        first_copy_results=(),
        output=tmp_path / "reviews",
    )
    manifest = validate_reference_reviews(
        path, materialised, request, source_records_jsonl=sources
    )
    assert not manifest.first_copy_result_sha256
    assert all(
        row.status == "no_scheduled_hypotheses"
        and row.review_manifest is None
        and row.advancement_manifest is None
        for row in manifest.cohorts
    )
    assert not tuple(path.parent.rglob("reference_advancement.json"))
