"""RF context transport is lossless metadata, never input authentication."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.fixtures.ranking_four_arm_context import (
    ReferenceFinalistContext,
    ReferencePlanContext,
    ReferencePreparedContext,
    ReferenceReviewContext,
)


def _context(root: Path) -> ReferenceFinalistContext:
    plan = ReferencePlanContext(
        runner_root=root / "runner",
        database_manifest=root / "database.json",
        software_lock=root / "pixi.lock",
        plan_path=root / "reference_plan/reference_plan.json",
    )
    prepared = ReferencePreparedContext(
        plan=plan,
        case_id="M6C001",
        catalogue_bundle=root / "original/catalogue",
        prepared_case=root / "original/prepared",
        coordinate_stage=None,
        phenix_manifest=root / "phenix.json",
        prepared_path=root / "reference_prepared/reference_prepared_case.json",
    )
    review = ReferenceReviewContext(
        prepared=prepared,
        first_copy_receipts=(root / "first-one/reference_first_copy.json",),
        reviews_path=root / "reviews/reference_reviews.json",
    )
    return ReferenceFinalistContext(
        review=review,
        copy_receipts=(root / "copy-one/reference_copy.json",),
        finalists_path=root / "finalists/reference_finalists.json",
    )


def test_reference_context_roundtrip_preserves_original_request_paths(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    restored = ReferenceFinalistContext.model_validate_json(context.model_dump_json())
    assert restored == context
    request = restored.review.inputs()
    assert request.prepared_path == context.review.prepared.prepared_path
    assert request.prepared_inputs == context.review.prepared.inputs()
    assert request.first_copy_receipts == context.review.first_copy_receipts
    assert request.reviews_path == context.review.reviews_path
    assert request.prepared_inputs.plan_inputs == context.review.prepared.plan.inputs()
    assert request.prepared_inputs.coordinate_stage is None
    # Structural transport does not read files or claim they are authenticated.
    assert not (tmp_path / "runner").exists()


@pytest.mark.parametrize("mutation", ("relative", "traversal", "unknown", "authority"))
def test_reference_context_rejects_ambiguous_paths_and_extra_fields(
    tmp_path: Path, mutation: str
) -> None:
    document = json.loads(_context(tmp_path).model_dump_json())
    if mutation == "relative":
        document["copy_receipts"] = ["reference_copy.json"]
    elif mutation == "traversal":
        document["review"]["prepared"]["plan"]["runner_root"] = str(
            tmp_path / "../runner"
        )
    elif mutation == "unknown":
        document["review"]["prepared"]["plan"]["track"] = "leakage"
    else:
        document["human_approval_granted"] = True
    expected = {
        "relative": "absolute original path",
        "traversal": "parent traversal",
        "unknown": "Extra inputs are not permitted",
        "authority": "Extra inputs are not permitted",
    }
    with pytest.raises(ValidationError, match=expected[mutation]):
        ReferenceFinalistContext.model_validate_json(json.dumps(document))
