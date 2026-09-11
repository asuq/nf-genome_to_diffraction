"""Real-enumerator RF-G4 reference checks; MR evidence is explicitly synthetic."""

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.matthews.enumerate import enumerate_group
from genome_to_diffraction.review.priority import (
    FirstCopyReviewEvidence,
    review_priority_key,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import CrystalEntry, PipelineConfig
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MtzPreflightRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import ExecutionStatus
from tests.fixtures.ranking_four_arm_reference import (
    AdmissionPrior,
    ReviewOrder,
    reference_prior_inventory,
    reference_review_order,
)
from tests.unit.test_review_priority import _evidence

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"


def _enumeration(
    mass_da: float, marker: str, *, retention_cap: int = 4
) -> tuple[MatthewsHypothesis, ...]:
    config = load_contract(REPOSITORY / "examples/config.yaml", "pipeline-config")
    assert isinstance(config, PipelineConfig)
    config = config.model_copy(
        update={
            "matthews": config.matthews.model_copy(
                update={"max_hypotheses_per_candidate": retention_cap}
            )
        }
    )
    sequence = marker * 100
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    group = SequenceGroupRecord.model_validate_json(
        (STUBS / "sequence_groups.jsonl").read_text().splitlines()[0]
    ).model_copy(
        update={
            "sequence_group_id": f"seq_{digest}",
            "sha256": digest,
            "sequence": sequence,
            "length_aa": len(sequence),
            "molecular_mass_da": mass_da,
            "mass_method": "synthetic_declared_test_mass",
        }
    )
    preflight = MtzPreflightRecord.model_validate_json(
        (STUBS / "mtz_preflight.jsonl").read_bytes()
    ).model_copy(update={"asu_volume_a3": 250_000.0, "resolution_high_a": 2.0})
    crystal = CrystalEntry(
        crystal_id=preflight.crystal_id, mtz="fixture.mtz", catalogue_id="fixture"
    )
    return enumerate_group(group, crystal, preflight, config)


def _joined(
    row: MatthewsHypothesis, marker: str, *, strong: bool = True
) -> FirstCopyReviewEvidence:
    base = _evidence(
        marker=marker,
        llg=120.0 if strong else 20.0,
        tfz=12.0 if strong else 3.0,
        clashes=0 if strong else 3,
    )
    return replace(
        base,
        hypothesis=base.hypothesis.model_copy(
            update={
                "crystal_id": row.crystal_id,
                "sequence_group_id": row.sequence_group_id,
                "copy_count_expected": row.copy_count,
            }
        ),
        matthews=row,
    )


def test_weighted_reference_exactly_preserves_production_enumeration() -> None:
    rows = _enumeration(5_000, "A")
    before = tuple(row.model_dump_json() for row in rows)
    reference = reference_prior_inventory(
        rows, admission_prior="copy_weighted", maximum_hypotheses_per_candidate=4
    )
    assert len(reference) == 40
    assert {item.original.hypothesis_id for item in reference} == {
        row.hypothesis_id for row in rows
    }
    assert all(
        item.rank == item.original.rank_within_candidate
        and item.prior == item.original.matthews_prior
        and item.retained == item.original.retained
        for item in reference
    )
    assert tuple(row.model_dump_json() for row in rows) == before
    assert reference == reference_prior_inventory(
        tuple(reversed(rows)),
        admission_prior="copy_weighted",
        maximum_hypotheses_per_candidate=4,
    )


def test_solvent_reference_recomputes_retention_without_rewriting() -> None:
    rows = _enumeration(5_000, "A")
    before = tuple(row.model_dump_json() for row in rows)
    reference = reference_prior_inventory(
        rows, admission_prior="solvent_density", maximum_hypotheses_per_candidate=4
    )
    promoted = [
        item for item in reference if item.retained and not item.original.retained
    ]
    assert promoted
    assert sum(item.retained for item in reference) == 4
    assert all(
        item.prior == item.original.relative_solvent_density for item in reference
    )
    assert any(item.prior != item.original.matthews_prior for item in promoted)
    assert tuple(row.model_dump_json() for row in rows) == before


@pytest.mark.parametrize("prior", ("solvent_density", "copy_weighted"))
def test_impossible_diagnostic_is_never_retained(prior: AdmissionPrior) -> None:
    rows = _enumeration(500_000, "A")
    reference = reference_prior_inventory(
        rows, admission_prior=prior, maximum_hypotheses_per_candidate=4
    )
    assert len(reference) == 1
    assert reference[0].original.physical_status == "impossible"
    assert reference[0].retained is False


@pytest.mark.parametrize(
    "corruption",
    ("truncated", "duplicate", "stale_reference", "changed_rank", "changed_input"),
)
def test_reference_rejects_incomplete_or_changed_production_inputs(
    corruption: str,
) -> None:
    rows = _enumeration(5_000, "A")
    if corruption == "truncated":
        rows = rows[:-1]
    elif corruption == "duplicate":
        rows = (*rows, rows[0])
    else:
        update = {
            "stale_reference": {"prior_reference_sha256": "b" * 64},
            "changed_rank": {"rank_within_candidate": 999},
            "changed_input": {"configured_solvent_min": 0.11},
        }[corruption]
        rows = (rows[0].model_copy(update=update), *rows[1:])
    with pytest.raises(ValueError):
        reference_prior_inventory(
            rows, admission_prior="solvent_density", maximum_hypotheses_per_candidate=4
        )


@pytest.mark.parametrize(
    ("prior", "order", "strong_first"),
    (
        ("solvent_density", "prior_first", False),
        ("copy_weighted", "prior_first", False),
        ("solvent_density", "mr_led", True),
        ("copy_weighted", "mr_led", True),
    ),
)
def test_four_arms_reuse_identical_synthetic_mr_and_keep_production_baseline(
    prior: AdmissionPrior, order: ReviewOrder, strong_first: bool
) -> None:
    # Retain all copy rows only for this two-result mathematical ordering probe.
    # Native comparison must instead use its unchanged per-model/25-task budgets.
    rows = (
        *_enumeration(50_000, "A", retention_cap=40),
        *_enumeration(5_000, "C", retention_cap=40),
    )
    two = next(
        row for row in rows if row.sequence_mass_da == 50_000 and row.copy_count == 2
    )
    twenty = next(
        row for row in rows if row.sequence_mass_da == 5_000 and row.copy_count == 20
    )
    assert two.solvent_fraction == twenty.solvent_fraction == pytest.approx(0.508)
    assert two.matthews_prior > twenty.matthews_prior
    weak, strong = _joined(two, "a", strong=False), _joined(twenty, "b")
    evidence = (weak, strong)
    before = tuple(item.result.model_dump_json() for item in evidence)
    ordered = reference_review_order(
        evidence,
        rows,
        admission_prior=prior,
        review_order=order,
        maximum_hypotheses_per_candidate=40,
    )
    assert ordered[0] == (strong if strong_first else weak)
    assert len(ordered) == 2
    assert tuple(item.result.model_dump_json() for item in evidence) == before
    if prior == "copy_weighted" and order == "mr_led":
        assert ordered == tuple(sorted(evidence, key=review_priority_key))
    assert ordered == reference_review_order(
        tuple(reversed(evidence)),
        tuple(reversed(rows)),
        admission_prior=prior,
        review_order=order,
        maximum_hypotheses_per_candidate=40,
    )


@pytest.mark.parametrize("order", ("prior_first", "mr_led"))
def test_failed_or_uninspectable_mr_cannot_gain_priority_from_reference_prior(
    order: ReviewOrder,
) -> None:
    rows = _enumeration(50_000, "A")
    ranked = sorted(rows, key=lambda row: row.rank_within_candidate)
    high = _joined(ranked[0], "a")
    lower = _joined(ranked[1], "b", strong=False)
    for failed_high in (
        replace(high, inspectable=False),
        replace(
            high,
            result=high.result.model_copy(
                update={"execution_status": ExecutionStatus.FAILED_PARSE}
            ),
        ),
    ):
        ordered = reference_review_order(
            (failed_high, lower),
            rows,
            admission_prior="copy_weighted",
            review_order=order,
            maximum_hypotheses_per_candidate=4,
        )
        assert ordered == (lower, failed_high)


@pytest.mark.parametrize(
    "corruption", ("foreign_sequence", "foreign_result", "duplicate", "unretained")
)
def test_reference_review_rejects_broken_joins_and_out_of_cohort_rows(
    corruption: str,
) -> None:
    rows = _enumeration(5_000, "A")
    target = next(row for row in rows if row.retained)
    if corruption == "unretained":
        target = next(row for row in rows if not row.retained)
    item = _joined(target, "a")
    if corruption == "foreign_sequence":
        item = replace(
            item,
            hypothesis=item.hypothesis.model_copy(
                update={"sequence_group_id": "seq_foreign"}
            ),
        )
    if corruption == "foreign_result":
        item = replace(
            item,
            result=item.result.model_copy(
                update={"hypothesis_id": "mrhyp_" + "b" * 64}
            ),
        )
    evidence = (item, item) if corruption == "duplicate" else (item,)
    with pytest.raises(ValueError):
        reference_review_order(
            evidence,
            rows,
            admission_prior="copy_weighted",
            review_order="prior_first",
            maximum_hypotheses_per_candidate=4,
        )


def test_empty_mr_is_not_fabricated_as_a_result() -> None:
    assert (
        reference_review_order(
            (),
            _enumeration(50_000, "A"),
            admission_prior="copy_weighted",
            review_order="mr_led",
            maximum_hypotheses_per_candidate=4,
        )
        == ()
    )
