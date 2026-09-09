"""Selected-solution evidence invariants in the shared production/M6 policy."""

from dataclasses import replace

import pytest
from pydantic import ValidationError

from genome_to_diffraction.matthews.probability import PRIOR_BACKEND
from genome_to_diffraction.review.priority import (
    FirstCopyReviewEvidence,
    mr_evidence_key,
    review_priority_key,
)
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MrHypothesis,
    NormalisedMrResult,
    SelectedMrSolutionEvidence,
)


def _evidence(
    *,
    marker: str = "a",
    copies: int = 1,
    tncs: bool = False,
    clashes: int | None = 0,
    llg: float | None = 120.0,
    tfz: float | None = 12.0,
) -> FirstCopyReviewEvidence:
    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=f"mrhyp_{marker * 64}",
        crystal_id="crystal",
        sequence_group_id="seq_a",
        model_id="model_a",
        copy_count_expected=2,
        copy_number_to_search=1,
        space_group="P 1",
        search_stage="first_copy",
        resource_profile="smoke",
        status="queued",
    )
    selected = SelectedMrSolutionEvidence(
        coordinate_sha256="a" * 64,
        placed_copy_count=copies,
        annotation="PAK=0 +TNCS" if tncs else "PAK=0",
        packing_clash_count=clashes,
        tncs_annotation_present=tncs,
    )
    result = NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=hypothesis.hypothesis_id,
        tool_version="synthetic policy fixture",
        execution_status="completed_hit",
        llg=llg,
        tfz=tfz,
        placed_copy_count=copies,
        selected_solution=selected,
        solution_coordinate_path="PHASER.1.pdb",
        solution_coordinate_sha256="a" * 64,
        raw_log_pointer="PHASER.log",
    )
    matthews = MatthewsHypothesis(
        schema_version="1.0",
        hypothesis_id="matthews_a",
        crystal_id="crystal",
        sequence_group_id="seq_a",
        copy_count=2,
        sequence_mass_da=50_000,
        total_mass_da=100_000,
        v_asu_a3=250_000,
        matthews_coefficient=2.5,
        solvent_fraction=0.508,
        matthews_prior=0.2,
        prior_backend=PRIOR_BACKEND,
        rank_within_candidate=1,
        retained=True,
        physical_status="plausible",
        sds_page_prior_label="unavailable",
    )
    return FirstCopyReviewEvidence(hypothesis, result, matthews, True)


@pytest.mark.parametrize(
    ("copies", "tncs", "expected"),
    (
        (1, False, "literal"),
        (2, True, "tncs_coupled_pair"),
        (2, False, "unexplained"),
        (3, True, "unexplained"),
    ),
)
def test_copy_state_requires_selected_tncs_annotation(
    copies: int,
    tncs: bool,
    expected: str,
) -> None:
    evidence = _evidence(copies=copies, tncs=tncs)
    assert evidence.copy_state == expected
    reference = _evidence()
    if expected in {"literal", "tncs_coupled_pair"}:
        assert mr_evidence_key(evidence) == mr_evidence_key(reference)
    else:
        assert mr_evidence_key(evidence) > mr_evidence_key(reference)


def test_packing_precedes_score_gate_and_missing_is_not_zero() -> None:
    packed = _evidence(llg=20, tfz=3)
    missing = _evidence(clashes=None, llg=500, tfz=40)
    positive_clashes = _evidence(clashes=3, llg=500, tfz=40)
    assert packed.packing_state == "zero_clashes"
    assert missing.packing_state == "unavailable"
    assert positive_clashes.packing_state == "clashes_present"
    assert review_priority_key(packed) < review_priority_key(missing)
    assert review_priority_key(packed) < review_priority_key(positive_clashes)


def test_aggregate_packing_alone_cannot_promote_a_selected_solution() -> None:
    reference = _evidence()
    unbound = replace(
        reference,
        result=reference.result.model_copy(
            update={
                "selected_solution": None,
                "packing_summary": {"top_solution_packed": True},
            }
        ),
    )
    assert unbound.packing_state == "unavailable"
    assert unbound.copy_state == "unavailable"
    assert review_priority_key(reference) < review_priority_key(unbound)


def test_matthews_only_breaks_mr_ties_then_ids_break_complete_ties() -> None:
    first, second = _evidence(marker="a"), _evidence(marker="b")
    assert review_priority_key(first) < review_priority_key(second)
    higher_prior = replace(
        second,
        matthews=second.matthews.model_copy(
            update={"matthews_prior": 0.9},
        ),
    )
    assert review_priority_key(higher_prior) < review_priority_key(first)
    weaker_mr = replace(
        higher_prior,
        result=higher_prior.result.model_copy(
            update={"llg": 110.0},
        ),
    )
    assert review_priority_key(first) < review_priority_key(weaker_mr)


def test_missing_score_is_not_zero_and_invalid_execution_is_not_inspectable() -> None:
    missing = _evidence(llg=None, tfz=12)
    zero = _evidence(llg=0, tfz=12)
    assert review_priority_key(zero) < review_priority_key(missing)
    failed = replace(
        zero,
        result=zero.result.model_copy(
            update={"execution_status": "failed_parse"},
        ),
    )
    assert review_priority_key(missing) < review_priority_key(failed)


@pytest.mark.parametrize("field", ("coordinate_sha256", "placed_copy_count"))
def test_selected_result_binding_rejects_drift(field: str) -> None:
    document = _evidence().result.model_dump(mode="json")
    document["selected_solution"][field] = "b" * 64 if field.endswith("sha256") else 2
    with pytest.raises(ValidationError, match="does not bind"):
        NormalisedMrResult.model_validate(document)
