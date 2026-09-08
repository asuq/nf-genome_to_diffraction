"""Frozen, truth-blind scope for the approved M6 ranking comparison.

Only the twelve approved cases and four fixed arms are representable. The
checked-in recipe and unchanged M6 protocol are checksum-bound before planning.
This module validates metadata only; it runs no scientific tools or scheduler.
Changed recipes, cross-cohort arms and invalid content identities fail closed.
The comparison tests cover recipe mutation, arm isolation and workload bounds.
"""

from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex

M6_COMPARISON_ID = "m6_ranking_four_arm_v1"
M6_COMPARISON_SHA256 = (
    "24e665c108eabf88614461a5f68347654ddde29b5b8a806401480c7f2d811199"
)
M6_COMPARISON_CASES = (
    "M6C001",
    "M6C009",
    "M6C010",
    "M6C012",
    "M6C013",
    "M6C022",
    "M6C025",
    "M6C034",
    "M6C037",
    "M6C042",
    "M6C055",
    "M6C056",
)
type M6ComparisonArm = Literal["A", "B", "C", "D"]
type M6AdmissionPrior = Literal["solvent_density", "copy_weighted"]
M6_COMPARISON_ARMS: dict[M6ComparisonArm, tuple[M6AdmissionPrior, str]] = {
    "A": ("solvent_density", "prior_first_reference"),
    "B": ("copy_weighted", "prior_first_reference"),
    "C": ("solvent_density", "production_mr_led"),
    "D": ("copy_weighted", "production_mr_led"),
}


def validate_comparison_recipe(recipe: Path) -> None:
    """Require the exact user-approved recipe, with no mutable threshold options."""

    if sha256_file(recipe) != M6_COMPARISON_SHA256:
        raise ValueError("M6 comparison recipe differs from the frozen approval")


def comparison_case_digest(root: Path, *, allow_empty: bool = False) -> str:
    """Bind all retained inputs while excluding only the cohort's own metadata."""

    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ValueError("M6 comparison case contains a non-owned symlink")
        if path.is_file() and relative != "comparison_cohort.json":
            files[relative] = sha256_file(path)
    if not files and not allow_empty:
        raise ValueError("M6 comparison case is empty")
    return canonical_digest(files)


class M6ComparisonCohort(ContractModel):
    """One admission cohort consumed by exactly two alternative review orders."""

    schema_version: Literal["1.0"]
    comparison_id: Literal["m6_ranking_four_arm_v1"]
    comparison_spec_sha256: Sha256Hex
    cohort_id: str
    case_id: str
    admission_prior: M6AdmissionPrior
    source_case_sha256: Sha256Hex
    case_sha256: Sha256Hex
    scheduled_hypothesis_ids: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_frozen_scope(self) -> Self:
        if self.case_id not in M6_COMPARISON_CASES:
            raise ValueError("M6 comparison case is outside the frozen twelve")
        if self.comparison_spec_sha256 != M6_COMPARISON_SHA256:
            raise ValueError("M6 comparison scope uses another recipe")
        if len(self.scheduled_hypothesis_ids) > 25 or len(
            set(self.scheduled_hypothesis_ids)
        ) != len(self.scheduled_hypothesis_ids):
            raise ValueError("M6 comparison initial cohort exceeds its unique budget")
        if self.cohort_id != content_id(
            "m6cohort_", self.model_dump(mode="json", exclude={"cohort_id"})
        ):
            raise ValueError("M6 comparison cohort identity differs")
        return self


class M6ComparisonArmContext(ContractModel):
    """A fixed arm over one retained cohort; never a human review authority."""

    schema_version: Literal["1.0"]
    arm: M6ComparisonArm
    cohort: M6ComparisonCohort

    @model_validator(mode="after")
    def _validate_shared_cohort(self) -> Self:
        if M6_COMPARISON_ARMS[self.arm][0] != self.cohort.admission_prior:
            raise ValueError("M6 comparison arm belongs to another admission cohort")
        return self

    @property
    def review_order(self) -> str:
        """Return the frozen review order, not a caller-provided override."""

        return M6_COMPARISON_ARMS[self.arm][1]


def load_comparison_cohort(case_bundle: Path) -> M6ComparisonCohort:
    """Authenticate the exact native-execution input bundle for either review arm."""

    cohort = M6ComparisonCohort.model_validate_json(
        (case_bundle / "comparison_cohort.json").read_bytes()
    )
    if comparison_case_digest(case_bundle) != cohort.case_sha256:
        raise ValueError("M6 comparison case inputs changed after cohort freeze")
    return cohort
