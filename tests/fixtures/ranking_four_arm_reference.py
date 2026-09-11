"""RF-G4 reference-only priors and review orders, never production dispatch.

Inputs are the complete production-validated Matthews enumeration and joined
first-copy evidence. Outputs preserve the original records and separately expose
comparison ranks/retention; no score is overwritten, task executed, identity
truth read, or seed approved. Native input/asset verification belongs to the
qualification harness. Unit tests use the real enumerator and explicitly
synthetic MR; this fixture alone supplies no native acceptance evidence.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from genome_to_diffraction.matthews.enumerate import dynamic_copy_counts
from genome_to_diffraction.matthews.probability import (
    PRIOR_BACKEND,
    PRIOR_FACTOR_BACKEND,
    REFERENCE_RESOURCE_SHA256,
    SOLVENT_DENSITY_BACKEND,
)
from genome_to_diffraction.review.priority import (
    FirstCopyReviewEvidence,
    mr_evidence_key,
    review_priority_key,
)
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MrHypothesis,
    NormalisedMrResult,
    PhysicalStatus,
)

type AdmissionPrior = Literal["solvent_density", "copy_weighted"]
type ReviewOrder = Literal["prior_first", "mr_led"]


@dataclass(frozen=True)
class ReferencePriorRow:
    """A comparison annotation, not a modified production Matthews record."""

    original: MatthewsHypothesis
    prior: float
    rank: int
    retained: bool


def _physical_rank(row: MatthewsHypothesis) -> int:
    return {"plausible": 0, "review": 1, "impossible": 2}[row.physical_status.value]


def _validate_complete_group(rows: Sequence[MatthewsHypothesis]) -> None:
    first = rows[0]
    identity_fields = (
        "v_asu_a3",
        "sequence_mass_da",
        "sequence_mass_lower_da",
        "sequence_mass_upper_da",
        "configured_solvent_min",
        "configured_solvent_max",
        "solvent_density_reference_count",
        "copy_frequency_reference_count",
    )
    if any(
        getattr(row, field) != getattr(first, field)
        for row in rows
        for field in identity_fields
    ):
        raise ValueError("comparison Matthews group has inconsistent input bindings")
    lower = (
        first.sequence_mass_da
        if first.sequence_mass_da is not None
        else first.sequence_mass_lower_da
    )
    upper = (
        first.sequence_mass_da
        if first.sequence_mass_da is not None
        else first.sequence_mass_upper_da
    )
    if lower is None or upper is None:
        raise ValueError("comparison Matthews group lacks sequence mass")
    expected, _ = dynamic_copy_counts(
        v_asu_a3=first.v_asu_a3, mass_lower_da=lower, mass_upper_da=upper
    )
    if tuple(sorted(row.copy_count for row in rows)) != expected:
        raise ValueError("comparison requires the complete finite copy enumeration")


def reference_prior_inventory(
    rows: Sequence[MatthewsHypothesis],
    *,
    admission_prior: AdmissionPrior,
    maximum_hypotheses_per_candidate: int,
) -> tuple[ReferencePriorRow, ...]:
    """Re-rank all physical alternatives before applying the same retention cap."""

    if admission_prior not in {"solvent_density", "copy_weighted"}:
        raise ValueError("unknown comparison admission prior")
    if (
        type(maximum_hypotheses_per_candidate) is not int
        or maximum_hypotheses_per_candidate < 1
    ):
        raise ValueError("comparison retention cap must be a positive integer")
    if not rows or len({row.hypothesis_id for row in rows}) != len(rows):
        raise ValueError("comparison Matthews inventory is empty or duplicated")
    groups: dict[tuple[str, str], list[MatthewsHypothesis]] = {}
    for original in rows:
        row = MatthewsHypothesis.model_validate(original.model_dump())
        if (
            row.prior_backend != PRIOR_BACKEND
            or row.prior_factor_backend != PRIOR_FACTOR_BACKEND
            or row.solvent_density_backend != SOLVENT_DENSITY_BACKEND
            or row.prior_reference_sha256 != REFERENCE_RESOURCE_SHA256
            or row.relative_solvent_density is None
        ):
            raise ValueError("comparison requires complete current prior factors")
        groups.setdefault((row.crystal_id, row.sequence_group_id), []).append(row)
    output: list[ReferencePriorRow] = []
    for group_id in sorted(groups):
        group = groups[group_id]
        _validate_complete_group(group)
        weighted = sorted(
            group,
            key=lambda row: (_physical_rank(row), -row.matthews_prior, row.copy_count),
        )
        for rank, row in enumerate(weighted, 1):
            retained = (
                rank <= maximum_hypotheses_per_candidate
                and row.physical_status is not PhysicalStatus.IMPOSSIBLE
            )
            if row.rank_within_candidate != rank or row.retained != retained:
                raise ValueError("comparison input differs from production retention")

        def prior(row: MatthewsHypothesis) -> float:
            if admission_prior == "copy_weighted":
                return row.matthews_prior
            assert row.relative_solvent_density is not None
            return row.relative_solvent_density

        ordered = sorted(
            group, key=lambda row: (_physical_rank(row), -prior(row), row.copy_count)
        )
        output.extend(
            ReferencePriorRow(
                original=row,
                prior=prior(row),
                rank=rank,
                retained=rank <= maximum_hypotheses_per_candidate
                and row.physical_status is not PhysicalStatus.IMPOSSIBLE,
            )
            for rank, row in enumerate(ordered, 1)
        )
    return tuple(output)


def reference_review_order(
    evidence: Sequence[FirstCopyReviewEvidence],
    matthews: Sequence[MatthewsHypothesis],
    *,
    admission_prior: AdmissionPrior,
    review_order: ReviewOrder,
    maximum_hypotheses_per_candidate: int,
) -> tuple[FirstCopyReviewEvidence, ...]:
    """Pair review orders on identical MR without claiming recommendation/execution."""

    if review_order not in {"prior_first", "mr_led"}:
        raise ValueError("unknown comparison review order")
    priors = {
        row.original.hypothesis_id: row
        for row in reference_prior_inventory(
            matthews,
            admission_prior=admission_prior,
            maximum_hypotheses_per_candidate=maximum_hypotheses_per_candidate,
        )
    }
    if len({row.hypothesis.hypothesis_id for row in evidence}) != len(evidence):
        raise ValueError("comparison MR inventory contains duplicate hypotheses")
    for item in evidence:
        MrHypothesis.model_validate(item.hypothesis.model_dump())
        NormalisedMrResult.model_validate(item.result.model_dump())
        row = priors.get(item.matthews.hypothesis_id)
        if (
            row is None
            or row.original != item.matthews
            or not row.retained
            or item.result.hypothesis_id != item.hypothesis.hypothesis_id
            or item.hypothesis.crystal_id != item.matthews.crystal_id
            or item.hypothesis.sequence_group_id != item.matthews.sequence_group_id
            or item.hypothesis.copy_count_expected != item.matthews.copy_count
            or item.hypothesis.search_stage != "first_copy"
            or item.hypothesis.copy_number_to_search != 1
            or type(item.inspectable) is not bool
        ):
            raise ValueError("comparison MR evidence has a stale or foreign join")

    if admission_prior == "copy_weighted" and review_order == "mr_led":
        return tuple(sorted(evidence, key=review_priority_key))

    def key(item: FirstCopyReviewEvidence) -> tuple[object, ...]:
        reference = priors[item.matthews.hypothesis_id]
        prior_key = (_physical_rank(item.matthews), -reference.prior, reference.rank)
        mr = mr_evidence_key(item)
        if review_order == "prior_first":
            return (*mr[:2], *prior_key, *mr[2:], *item.stable_id)
        return (*mr, *prior_key, *item.stable_id)

    return tuple(sorted(evidence, key=key))
