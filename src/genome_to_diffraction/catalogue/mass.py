"""Average neutral polypeptide-mass calculations for catalogue sequences."""

from dataclasses import dataclass
from typing import cast

from Bio import __version__ as BIOPYTHON_VERSION
from Bio.SeqUtils import molecular_weight

STANDARD_RESIDUES = frozenset("ACDEFGHIKLMNPQRSTVWY")
DEFINED_NONSTANDARD_RESIDUES = frozenset("UO")
AMBIGUOUS_RESIDUES: dict[str, frozenset[str]] = {
    "B": frozenset("DN"),
    "Z": frozenset("EQ"),
    "J": frozenset("IL"),
    "X": STANDARD_RESIDUES,
}
VALID_RESIDUES = (
    STANDARD_RESIDUES | DEFINED_NONSTANDARD_RESIDUES | frozenset(AMBIGUOUS_RESIDUES)
)
MASS_METHOD = (
    "Biopython Bio.SeqUtils.molecular_weight average neutral protein mass "
    f"{BIOPYTHON_VERSION}, including terminal water"
)


@dataclass(frozen=True)
class MassAssessment:
    """Exact mass or defensible bounds plus machine-readable review flags."""

    exact_da: float | None
    lower_da: float | None
    upper_da: float | None
    residue_policy: str
    quality_flags: tuple[str, ...]


def invalid_residues(sequence: str) -> frozenset[str]:
    """Return symbols for which no protein interpretation is permitted."""

    return frozenset(sequence) - VALID_RESIDUES - {"*"}


def _residue_contribution(residue: str) -> float:
    water = cast(
        float,
        molecular_weight("", seq_type="protein"),  # type: ignore[no-untyped-call]
    )
    residue_mass = cast(
        float,
        molecular_weight(residue, seq_type="protein"),  # type: ignore[no-untyped-call]
    )
    return residue_mass - water


def assess_mass(sequence: str) -> MassAssessment:
    """Calculate an exact average mass or bounds without guessing residues.

    ``B/Z/J/X`` are expanded only to their IUPAC candidate sets and returned as
    bounds. ``U/O`` have defined chemical identities in Biopython and therefore
    retain exact masses, but are flagged because downstream tools may reject them.
    An internal stop makes mass unavailable; the caller must retain it for review.
    """

    invalid = invalid_residues(sequence)
    if invalid:
        rendered = ", ".join(sorted(invalid))
        raise ValueError(f"unsupported protein residue symbols: {rendered}")
    if "*" in sequence:
        return MassAssessment(
            exact_da=None,
            lower_da=None,
            upper_da=None,
            residue_policy="internal_stop_mass_unavailable",
            quality_flags=("internal_stop", "mass_unavailable"),
        )

    ambiguous = sorted(frozenset(sequence) & frozenset(AMBIGUOUS_RESIDUES))
    nonstandard = sorted(frozenset(sequence) & DEFINED_NONSTANDARD_RESIDUES)
    flags: list[str] = []
    if ambiguous:
        flags.extend(f"ambiguous_residue_{residue}" for residue in ambiguous)
    if nonstandard:
        flags.extend(
            f"defined_nonstandard_residue_{residue}" for residue in nonstandard
        )

    if not ambiguous:
        return MassAssessment(
            exact_da=cast(
                float,
                molecular_weight(  # type: ignore[no-untyped-call]
                    sequence, seq_type="protein"
                ),
            ),
            lower_da=None,
            upper_da=None,
            residue_policy=(
                "defined_nonstandard_exact_review" if nonstandard else "standard_exact"
            ),
            quality_flags=tuple(flags),
        )

    water = cast(
        float,
        molecular_weight("", seq_type="protein"),  # type: ignore[no-untyped-call]
    )
    lower = water
    upper = water
    for residue in sequence:
        choices = AMBIGUOUS_RESIDUES.get(residue, frozenset({residue}))
        contributions = [_residue_contribution(choice) for choice in choices]
        lower += min(contributions)
        upper += max(contributions)
    return MassAssessment(
        exact_da=None,
        lower_da=lower,
        upper_da=upper,
        residue_policy="iupac_ambiguity_bounds_review",
        quality_flags=tuple(flags),
    )
