"""Pure first-copy review ordering shared by production and known-control M6.

Inputs are joined hypotheses, normalised selected-solution evidence, Matthews
rows and independently verified asset availability. Outputs are deterministic
lexicographic keys and explicit evidence states; no external tool is invoked.
Malformed scores fail, missing packing is not acceptance, and ranking never
grants review approval. REVIEW_PRIORITY_POLICY versions report/cache identities.
Unit regressions cover prior dominance, missing evidence, tNCS and stable ties.
"""

import math
from dataclasses import dataclass
from typing import Literal

from genome_to_diffraction.mr.policy import passes_provisional_score_gate
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MrHypothesis,
    NormalisedMrResult,
)
from genome_to_diffraction.status import ExecutionStatus

REVIEW_PRIORITY_POLICY = "selected-packing-copy-mr-matthews-v1"
type MrEvidenceKey = tuple[int, int, int, int, int, float, float]
type MatthewsEvidenceKey = tuple[int, float, int]
type PackingState = Literal["zero_clashes", "clashes_present", "unavailable"]
type CopyState = Literal["literal", "tncs_coupled_pair", "unexplained", "unavailable"]


@dataclass(frozen=True)
class FirstCopyReviewEvidence:
    """Joined evidence without filesystem or benchmark-truth dependencies."""

    hypothesis: MrHypothesis
    result: NormalisedMrResult
    matthews: MatthewsHypothesis
    inspectable: bool

    @property
    def packing_state(self) -> PackingState:
        selected = self.result.selected_solution
        if selected is None or selected.packing_clash_count is None:
            return "unavailable"
        return (
            "zero_clashes" if selected.packing_clash_count == 0 else "clashes_present"
        )

    @property
    def copy_state(self) -> CopyState:
        selected = self.result.selected_solution
        if selected is None:
            return "unavailable"
        if selected.placed_copy_count == self.hypothesis.copy_number_to_search:
            return "literal"
        if (
            self.hypothesis.copy_number_to_search == 1
            and self.hypothesis.copy_count_expected >= 2
            and selected.placed_copy_count == 2
            and selected.tncs_annotation_present
        ):
            return "tncs_coupled_pair"
        return "unexplained"

    @property
    def stable_id(self) -> tuple[str, str, str]:
        return (
            self.hypothesis.sequence_group_id,
            self.hypothesis.model_id,
            self.hypothesis.hypothesis_id,
        )


def _descending(value: float | None) -> float:
    if value is None:
        return math.inf
    if not math.isfinite(value):
        raise ValueError("review ranking score must be finite or explicitly missing")
    return -value


def mr_evidence_key(evidence: FirstCopyReviewEvidence) -> MrEvidenceKey:
    """Order inspectability, selected packing/copy interpretation, then raw MR."""

    result = evidence.result
    completed = result.execution_status in {
        ExecutionStatus.COMPLETED_HIT,
        ExecutionStatus.COMPLETED_NO_HIT,
    }
    return (
        0 if completed and evidence.inspectable else 1,
        0 if completed else 1,
        0 if evidence.packing_state == "zero_clashes" else 1,
        0 if evidence.copy_state in {"literal", "tncs_coupled_pair"} else 1,
        0 if passes_provisional_score_gate(llg=result.llg, tfz=result.tfz) else 1,
        _descending(result.llg),
        _descending(result.tfz),
    )


def matthews_evidence_key(evidence: FirstCopyReviewEvidence) -> MatthewsEvidenceKey:
    """Retain the independent Matthews ordering, without an MR feedback loop."""

    row = evidence.matthews
    return (
        {"plausible": 0, "review": 1, "impossible": 2}[row.physical_status.value],
        _descending(row.matthews_prior),
        row.rank_within_candidate,
    )


def review_priority_key(
    evidence: FirstCopyReviewEvidence,
) -> tuple[MrEvidenceKey, MatthewsEvidenceKey, tuple[str, str, str]]:
    """Use Matthews only after selected-solution MR evidence is tied."""

    return (
        mr_evidence_key(evidence),
        matthews_evidence_key(evidence),
        evidence.stable_id,
    )
