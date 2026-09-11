"""Truth-blind per-arm inventories from authenticated reference copy receipts.

Inputs are one fixed paired authority, its exact admission/hypotheses and the
complete union of independently executed seed bundles. No tools are invoked or
seeds scheduled here. Outputs reuse production's structural stage/count model,
not its execution authority: each arm retains its own 25-task/five-seed bounds.
Native attempt statuses remain separate from advancement, including failed
attempts and already-complete zero-attempt roots. Missing, duplicate, foreign,
stale or altered evidence fails. Receipt/source/input hashes bind the result;
freeze that inventory before any truth-side join or later reuse. Tests exercise
the shared adapter with simulated Phenix, not native scientific acceptance.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field
from tests.fixtures.ranking_four_arm_advancement import validate_reference_advancement
from tests.fixtures.ranking_four_arm_copy import validate_reference_copy_receipt
from tests.fixtures.ranking_four_arm_reference import AdmissionPrior, ReviewOrder

from genome_to_diffraction.benchmarks.m6_stages import (
    M6StageInventory,
    M6StageRow,
    _records,
    stage_counts,
)
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.mr.add_copy import AddCopyRunRequest
from genome_to_diffraction.ranking.funnel import DiverseFirstCopyFunnelRequest
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.results import (
    AdditionalCopyResult,
    MrHypothesis,
    SequenceGroupRecord,
)


@dataclass(frozen=True)
class ReferenceCopyEvidence:
    """An original seed request and its completed native receipt directory."""

    request: AddCopyRunRequest
    root: Path


class ReferenceContinuationReceipt(ContractModel):
    """One shared chain, retaining typed results rather than inferred success."""

    seed_solution_id: str
    receipt_sha256: Sha256Hex
    attempts: tuple[AdditionalCopyResult, ...]


class ReferenceArmStages(ContractModel):
    """One arm's structural M6 stage contract under explicit RF authority."""

    arm: Literal["A", "B", "C", "D"]
    review_order: ReviewOrder
    stages: M6StageInventory


class ReferencePairedStages(ContractModel):
    """Two independent stage inventories joined to a shared receipt union."""

    schema_version: Literal["1.0"] = "1.0"
    execution_authority_kind: Literal["truth_blind_rf_reference"] = (
        "truth_blind_rf_reference"
    )
    advancement_manifest_sha256: Sha256Hex
    admission_prior: AdmissionPrior
    arms: tuple[ReferenceArmStages, ReferenceArmStages]
    receipts: tuple[ReferenceContinuationReceipt, ...] = Field(max_length=10)


def build_reference_stage_inventory(
    admission: DiverseFirstCopyFunnelRequest,
    *,
    hypotheses_jsonl: Path,
    advancement_manifest: Path,
    copy_evidence: tuple[ReferenceCopyEvidence, ...],
) -> ReferencePairedStages:
    """Authenticate the exact receipt union, then count each arm independently."""

    validated = validate_reference_advancement(
        advancement_manifest, admission, hypotheses_jsonl=hypotheses_jsonl
    )
    manifest = validated.manifest
    authority_sha256 = sha256_file(advancement_manifest)
    hypotheses = _records(hypotheses_jsonl, MrHypothesis)
    groups = _records(admission.sequence_groups_jsonl, SequenceGroupRecord)
    by_group = {row.sequence_group_id: row for row in groups}
    scheduled_sha256 = sha256_file(hypotheses_jsonl)
    expected_seeds = {row.solution_id for row in manifest.recommended}
    supplied_seeds = [item.request.seed_solution_id for item in copy_evidence]
    roots = [item.root.resolve(strict=True) for item in copy_evidence]
    if len(set(supplied_seeds)) != len(supplied_seeds) or len(set(roots)) != len(roots):
        raise ValueError("reference stages contain duplicate continuation receipts")
    if set(supplied_seeds) != expected_seeds:
        raise ValueError(
            "reference stages have missing or foreign continuation receipts"
        )
    receipts: dict[str, ReferenceContinuationReceipt] = {}
    for item in copy_evidence:
        if item.root.is_symlink() or not item.root.is_dir():
            raise ValueError("reference stages require an owned receipt directory")
        if sha256_file(item.request.hypotheses_jsonl) != scheduled_sha256:
            raise ValueError("reference receipt differs from the scheduled cohort")
        receipt_sha256, count = validate_reference_copy_receipt(
            item.root,
            item.request,
            admission,
            advancement_manifest=advancement_manifest,
        )
        attempts = _records(
            item.root / "additional_copy_series_results.jsonl", AdditionalCopyResult
        )
        if len(attempts) != count:
            raise ValueError("reference native attempt inventory changed")
        receipts[item.request.seed_solution_id] = ReferenceContinuationReceipt(
            seed_solution_id=item.request.seed_solution_id,
            receipt_sha256=receipt_sha256,
            attempts=attempts,
        )
    arms: list[ReferenceArmStages] = []
    for arm in manifest.arms:
        by_hypothesis = {row.original.hypothesis_id: row for row in arm.rows}
        rows: list[M6StageRow] = []
        for rank, hypothesis in enumerate(hypotheses, 1):
            recommendation = by_hypothesis[hypothesis.hypothesis_id]
            original = recommendation.original
            # A receipt selected only by the other arm is not this arm's work.
            receipt = (
                receipts[original.solution_id] if recommendation.recommended else None
            )
            rows.append(
                M6StageRow(
                    hypothesis_id=hypothesis.hypothesis_id,
                    sequence_group_id=original.sequence_group_id,
                    sequence_sha256=by_group[original.sequence_group_id].sha256,
                    model_id=original.model_id,
                    expected_copy_count=original.expected_copy_count,
                    scheduled_rank=rank,
                    solution_id=original.solution_id,
                    review_priority_rank=recommendation.review_rank,
                    recommendation_rank=recommendation.recommendation_rank,
                    recommended=recommendation.recommended,
                    advanced_rank=recommendation.recommendation_rank
                    if receipt
                    else None,
                    continuation_receipt_sha256=receipt.receipt_sha256
                    if receipt
                    else None,
                    additional_copy_attempt_count=len(receipt.attempts)
                    if receipt
                    else 0,
                )
            )
        stages = M6StageInventory(
            case_id=manifest.crystal_id,
            hypotheses_sha256=scheduled_sha256,
            benchmark_advancement_sha256=authority_sha256,
            rows=tuple(rows),
            scheduled=stage_counts(rows),
            recommended=stage_counts([row for row in rows if row.recommended]),
            advanced=stage_counts(
                [row for row in rows if row.advanced_rank is not None]
            ),
        )
        arms.append(
            ReferenceArmStages(
                arm=arm.arm, review_order=arm.review_order, stages=stages
            )
        )
    if (
        sha256_file(advancement_manifest) != authority_sha256
        or validate_reference_advancement(
            advancement_manifest, admission, hypotheses_jsonl=hypotheses_jsonl
        ).manifest
        != manifest
    ):
        raise ValueError("reference authority changed during stage accounting")
    return ReferencePairedStages(
        advancement_manifest_sha256=authority_sha256,
        admission_prior=manifest.admission_prior,
        arms=(arms[0], arms[1]),
        receipts=tuple(receipts[row.solution_id] for row in manifest.recommended),
    )
