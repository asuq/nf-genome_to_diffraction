"""Immutable file-based human decisions for the Phase III unknown workflow.

Scientific purpose
------------------
These records preserve explicit human decisions at the crystallographic,
first-component (A-seed), composition, and sequence checkpoints.  A decision
file binds every row to one owned parent-run identifier and one checksum-qualified
review package.  The package manifest exposes the exact parent profile/phase and
the permitted crystal/item targets; the local staging boundary verifies those
facts before consuming a decision.

Inputs and outputs
------------------
``PhaseIIIReviewPackageManifest`` identifies one immutable review package and its
permitted targets.  ``PhaseIIIReviewDecision`` contains the crystal/item target,
decision, reviewer, UTC-normalised review time, reason, and optional comment.  One
``PhaseIIIReviewDecisionFile`` contains decisions for exactly one checkpoint and
review package.  JSON may carry the typed record directly; the operator-facing TSV
adapter is registered as ``phase3-review-decisions`` in
:mod:`genome_to_diffraction.schemas.io`.

No external command or tool version is required.  Invalid decision values,
duplicate or contradictory targets, mixed checkpoint semantics, and retained-state
limits fail contract validation.  Scientific hold, rejection, deferral, retained
partial/alternative, and no-assignment outcomes are valid decisions rather than
execution failures.

The cache/content key is ``decision_file_id``: a full SHA-256 identifier over the
RFC-8785 canonical record excluding only that identifier.  It intentionally differs
from a byte checksum of the source TSV; the local stager retains and verifies that
transport checksum separately.  Focused validation, mutation, duplicate, limit,
JSON/TSV, and v1-preservation coverage lives in
``tests/unit/test_phase3_review_contracts.py``.
"""

from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    Sha256Hex,
    UtcTimestamp,
)
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract

PhaseIIIReviewDecisionFileIdentifier = Annotated[
    str,
    Field(pattern=r"^phase3review_[a-f0-9]{64}$"),
]


class PhaseIIIReviewCheckpoint(StrEnum):
    """Human checkpoints required by the approved unknown workflow."""

    CRYSTALLOGRAPHIC = "crystallographic"
    A_SEED = "a_seed"
    COMPOSITION = "composition"
    SEQUENCE = "sequence"


class PhaseIIIReviewDecisionValue(StrEnum):
    """Union of checkpoint-specific operator decisions."""

    PROCEED = "proceed"
    HOLD = "hold"
    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"
    RETAIN_PARTIAL = "retain_partial"
    RETAIN_ALTERNATIVE = "retain_alternative"
    NO_ASSIGNMENT = "no_assignment"


class PhaseIIIReviewPackageTarget(ContractModel):
    """One crystal/item pair that the exact review package permits deciding."""

    crystal_id: NonEmptyString
    item_id: NonEmptyString


class PhaseIIIReviewPackageManifest(ContractModel):
    """Minimum immutable package metadata required by the local stager."""

    schema_version: Literal["2.0"]
    review_package_id: NonEmptyString
    checkpoint: PhaseIIIReviewCheckpoint
    owned_parent_run_id: NonEmptyString
    parent_profile: NonEmptyString
    parent_phase: NonEmptyString
    created_at: UtcTimestamp
    permitted_targets: tuple[PhaseIIIReviewPackageTarget, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_package_metadata(self) -> Self:
        for field_name in (
            "review_package_id",
            "owned_parent_run_id",
            "parent_profile",
            "parent_phase",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must contain non-whitespace text")
        target_keys = [
            (target.crystal_id, target.item_id) for target in self.permitted_targets
        ]
        if len(target_keys) != len(set(target_keys)):
            raise ValueError("review package contains duplicate permitted targets")
        return self


_ALLOWED_DECISIONS: dict[
    PhaseIIIReviewCheckpoint,
    frozenset[PhaseIIIReviewDecisionValue],
] = {
    PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC: frozenset(
        {
            PhaseIIIReviewDecisionValue.PROCEED,
            PhaseIIIReviewDecisionValue.HOLD,
        }
    ),
    PhaseIIIReviewCheckpoint.A_SEED: frozenset(
        {
            PhaseIIIReviewDecisionValue.APPROVE,
            PhaseIIIReviewDecisionValue.REJECT,
            PhaseIIIReviewDecisionValue.DEFER,
        }
    ),
    PhaseIIIReviewCheckpoint.COMPOSITION: frozenset(
        {
            PhaseIIIReviewDecisionValue.APPROVE,
            PhaseIIIReviewDecisionValue.REJECT,
            PhaseIIIReviewDecisionValue.DEFER,
            PhaseIIIReviewDecisionValue.RETAIN_PARTIAL,
        }
    ),
    PhaseIIIReviewCheckpoint.SEQUENCE: frozenset(
        {
            PhaseIIIReviewDecisionValue.APPROVE,
            PhaseIIIReviewDecisionValue.RETAIN_ALTERNATIVE,
            PhaseIIIReviewDecisionValue.NO_ASSIGNMENT,
        }
    ),
}


class PhaseIIIReviewDecision(ContractModel):
    """One explicit human decision for one crystal-bound review item."""

    crystal_id: NonEmptyString
    item_id: NonEmptyString
    decision: PhaseIIIReviewDecisionValue
    reviewer: NonEmptyString
    reviewed_at: UtcTimestamp
    reason: NonEmptyString
    comment: NonEmptyString | None = None

    @model_validator(mode="after")
    def _reject_blank_human_text(self) -> Self:
        for field_name in ("reviewer", "reason"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must contain non-whitespace text")
        if self.comment is not None and not self.comment.strip():
            raise ValueError("comment must be omitted rather than blank")
        return self


class PhaseIIIReviewDecisionFile(_ContentAddressedContract):
    """One checkpoint's decisions bound to an immutable parent review package."""

    _identity_field: ClassVar[str] = "decision_file_id"
    _identity_prefix: ClassVar[str] = "phase3review_"

    schema_version: Literal["2.0"]
    decision_file_id: PhaseIIIReviewDecisionFileIdentifier
    checkpoint: PhaseIIIReviewCheckpoint
    owned_parent_run_id: NonEmptyString
    review_package_id: NonEmptyString
    review_package_manifest_sha256: Sha256Hex
    decisions: tuple[PhaseIIIReviewDecision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_checkpoint_decisions(self) -> Self:
        allowed = _ALLOWED_DECISIONS[self.checkpoint]
        target_keys: set[tuple[str, str]] = set()
        decisions_by_crystal: dict[str, list[PhaseIIIReviewDecision]] = {}
        for decision in self.decisions:
            if decision.decision not in allowed:
                raise ValueError(
                    f"decision {decision.decision.value!r} is invalid for "
                    f"checkpoint {self.checkpoint.value!r}"
                )
            key = (decision.crystal_id, decision.item_id)
            if key in target_keys:
                raise ValueError(
                    "review decisions duplicate or conflict for a crystal/item "
                    f"target: {decision.crystal_id}/{decision.item_id}"
                )
            target_keys.add(key)
            decisions_by_crystal.setdefault(decision.crystal_id, []).append(decision)

        retained_values: frozenset[PhaseIIIReviewDecisionValue]
        limit_label: str
        if self.checkpoint is PhaseIIIReviewCheckpoint.A_SEED:
            retained_values = frozenset({PhaseIIIReviewDecisionValue.APPROVE})
            limit_label = "approved A states"
        elif self.checkpoint is PhaseIIIReviewCheckpoint.COMPOSITION:
            retained_values = frozenset(
                {
                    PhaseIIIReviewDecisionValue.APPROVE,
                    PhaseIIIReviewDecisionValue.RETAIN_PARTIAL,
                }
            )
            limit_label = "combined composition finalists"
        else:
            return self

        for crystal_id, items in decisions_by_crystal.items():
            retained_count = sum(item.decision in retained_values for item in items)
            if retained_count > 3:
                raise ValueError(
                    f"{limit_label} exceed the per-crystal limit of three: {crystal_id}"
                )
        return self


__all__ = [
    "PhaseIIIReviewCheckpoint",
    "PhaseIIIReviewDecision",
    "PhaseIIIReviewDecisionFile",
    "PhaseIIIReviewDecisionValue",
    "PhaseIIIReviewPackageManifest",
    "PhaseIIIReviewPackageTarget",
]
