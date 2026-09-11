"""Reference-only top-five annotations over a production-validated MR package.

Inputs are one fixed reference admission request, its complete scheduled
hypotheses and the actual production review package for that cohort. Existing
production validation authenticates assets and eligibility; this fixture changes
only the declared comparison order. Output rows keep production fields separate
from comparison ranks. No authority, human decision, execution or advancement
receipt is written. Native qualification must additionally freeze source, inputs
and outputs, and provide genuine execution/provenance evidence.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from tests.fixtures.ranking_four_arm_admission import reference_admission_plan
from tests.fixtures.ranking_four_arm_reference import (
    AdmissionPrior,
    ReviewOrder,
    reference_review_order,
)

from genome_to_diffraction.benchmarks.m6_advancement import (
    M6AdvancementRow,
    _object,
    _owned,
    _records,
    _review_rows,
)
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ranking.funnel import (
    DiverseFirstCopyFunnelRequest,
    _diverse_input_digests,
)
from genome_to_diffraction.review.priority import FirstCopyReviewEvidence
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MrHypothesis,
    NormalisedMrResult,
)


@dataclass(frozen=True)
class ReferenceSeedRow:
    """Comparison ranks, with the original validated production row unchanged."""

    original: M6AdvancementRow
    review_rank: int
    recommendation_rank: int | None
    recommended: bool


@dataclass(frozen=True)
class ReferenceSeedPlan:
    """Recommendations only, not a benchmark advancement authorisation."""

    admission_prior: AdmissionPrior
    review_order: ReviewOrder
    input_sha256: dict[str, str]
    rows: tuple[ReferenceSeedRow, ...]

    @property
    def recommended(self) -> tuple[ReferenceSeedRow, ...]:
        return tuple(row for row in self.rows if row.recommended)


def reference_seed_recommendations(
    request: DiverseFirstCopyFunnelRequest,
    *,
    hypotheses_jsonl: Path,
    review_manifest: Path,
    admission_prior: AdmissionPrior,
    review_order: ReviewOrder,
) -> ReferenceSeedPlan:
    """Rederive admission, authenticate the full review, and annotate paired ranks."""

    admission = reference_admission_plan(request, admission_prior=admission_prior)
    expected = tuple(row.hypothesis for row in admission.selected)
    if not expected:
        raise ValueError(
            "empty admission needs native early-outcome evidence, not MR review"
        )
    hypotheses = _records(hypotheses_jsonl, MrHypothesis)
    if hypotheses != expected:
        raise ValueError("reference review does not cover its exact admission cohort")
    input_sha256 = {
        **{f"admission_{key}": value for key, value in admission.input_sha256.items()},
        "scheduled_hypotheses": sha256_file(hypotheses_jsonl),
        "review_manifest": sha256_file(review_manifest),
    }
    baseline = _review_rows(
        review_manifest,
        hypotheses_jsonl,
        request.matthews_hypotheses_jsonl,
        request.crystal_ids[0],
    )
    by_hypothesis = {row.hypothesis_id: row for row in hypotheses}
    matthews = _records(request.matthews_hypotheses_jsonl, MatthewsHypothesis)
    by_matthews = {row.hypothesis_id: row for row in matthews}
    document = _object(review_manifest)
    evidence: list[FirstCopyReviewEvidence] = []
    for item in cast(list[dict[str, object]], document["items"]):
        hypothesis = by_hypothesis[cast(str, item["hypothesis_id"])]
        copied = cast(dict[str, object], item["copied_assets"])
        result_path = _owned(
            review_manifest.resolve().parent, copied["normalised_result"]
        )
        payload = result_path.read_bytes()
        checksums = cast(dict[str, object], item["copied_asset_sha256"])
        if hashlib.sha256(payload).hexdigest() != checksums["normalised_result"]:
            raise ValueError("reference review result changed after validation")
        result = NormalisedMrResult.model_validate_json(payload)
        evidence.append(
            FirstCopyReviewEvidence(
                hypothesis=hypothesis,
                result=result,
                matthews=by_matthews[
                    cast(str, hypothesis.priority_features["matthews_hypothesis_id"])
                ],
                inspectable=cast(bool, item["inspectable_solution"]),
            )
        )
    ordered = reference_review_order(
        evidence,
        matthews,
        admission_prior=admission_prior,
        review_order=review_order,
        maximum_hypotheses_per_candidate=4,
    )
    baseline_by_id = {row.hypothesis_id: row for row in baseline}
    rows: list[ReferenceSeedRow] = []
    eligible_count = 0
    for rank, evidence_row in enumerate(ordered, 1):
        original = baseline_by_id[evidence_row.hypothesis.hypothesis_id]
        # Eligibility comes from validated production evidence for every row,
        # including eligible states beyond the production top-five cutoff.
        eligible = original.recommendation_rank is not None
        if eligible:
            eligible_count += 1
        rows.append(
            ReferenceSeedRow(
                original=original,
                review_rank=rank,
                recommendation_rank=eligible_count if eligible else None,
                recommended=eligible and eligible_count <= 5,
            )
        )
    if (
        admission_prior == "copy_weighted"
        and review_order == "mr_led"
        and (
            tuple(row.original for row in rows) != baseline
            or any(
                row.review_rank != row.original.review_priority_rank
                or row.recommendation_rank != row.original.recommendation_rank
                or row.recommended
                != (row.original.advancement_disposition == "recommended")
                for row in rows
            )
        )
    ):
        raise ValueError("reference baseline differs from production recommendations")
    if (
        _diverse_input_digests(request) != admission.input_sha256
        or sha256_file(hypotheses_jsonl) != input_sha256["scheduled_hypotheses"]
        or sha256_file(review_manifest) != input_sha256["review_manifest"]
    ):
        raise ValueError("reference recommendation inputs changed while planning")
    return ReferenceSeedPlan(admission_prior, review_order, input_sha256, tuple(rows))
