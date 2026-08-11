"""Versioned provisional acceptance policy for first-copy Phaser results."""

from typing import Final, Literal

SCORE_GATE_LLG: Final = 50.0
SCORE_GATE_TFZ: Final = 5.0
SCORE_GATE_OPERATOR: Final[Literal["or"]] = "or"
SCORE_GATE_ID: Final = "strict_llg_gt_50_or_tfz_gt_5"

LEGACY_SCORE_GATE_LLG: Final = 100.0
LEGACY_SCORE_GATE_TFZ: Final = 10.0


def passes_provisional_score_gate(*, llg: float | None, tfz: float | None) -> bool:
    """Return whether either raw Phaser metric strictly exceeds its threshold."""

    return (llg is not None and llg > SCORE_GATE_LLG) or (
        tfz is not None and tfz > SCORE_GATE_TFZ
    )
