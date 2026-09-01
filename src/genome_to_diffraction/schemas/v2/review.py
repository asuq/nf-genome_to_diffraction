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
``PhaseIIIReviewPackageManifest`` content-binds one parent run, execution identity,
checkpoint, crystal, permitted-target set, explicit evidence inventory, and
generated target-review table. ``PhaseIIIReviewDecision`` contains the crystal/item
target, decision, reviewer, UTC-normalised review time, reason, and optional comment.
One ``PhaseIIIReviewDecisionFile`` contains decisions for exactly one checkpoint and
review package. JSON may carry the typed record directly; the operator-facing TSV
adapter is registered as ``phase3-review-decisions`` in
:mod:`genome_to_diffraction.schemas.io`.

No external command or tool version is required.  Invalid decision values,
duplicate or contradictory targets, mixed checkpoint semantics, and retained-state
limits fail contract validation.  Scientific hold, rejection, deferral, retained
partial/alternative, and no-assignment outcomes are valid decisions rather than
execution failures.

The cache/content keys are ``review_package_id`` and ``decision_file_id``: full
SHA-256 identifiers over their RFC-8785 canonical records excluding only their own
identifier. They intentionally differ from byte checksums of the manifest and
source TSV; the local stager retains and verifies those transport checksums
separately. Focused package validation lives in
``tests/unit/test_phase3_review_package.py``. Decision mutation, duplicate, limit,
JSON/TSV, and v1-preservation coverage lives in
``tests/unit/test_phase3_review_contracts.py``.
"""

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    OperatorIdentifier,
    PositiveInt,
    Sha256Hex,
    UtcTimestamp,
)
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract
from genome_to_diffraction.schemas.v2.execution import ExecutionIdentityIdentifier

PhaseIIIReviewDecisionFileIdentifier = Annotated[
    str,
    Field(pattern=r"^phase3review_[a-f0-9]{64}$"),
]
PhaseIIIReviewPackageIdentifier = Annotated[
    str,
    Field(pattern=r"^phase3reviewpkg_[a-f0-9]{64}$"),
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

    crystal_id: OperatorIdentifier
    item_id: OperatorIdentifier


def validate_phase3_review_relative_path(
    value: str,
    *,
    required_prefix: str | None = None,
) -> None:
    """Reject absolute, platform-dependent, or non-canonical package paths."""

    if not value or "\\" in value or "\x00" in value:
        raise ValueError("package path must be a non-empty portable POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise ValueError("package path must be canonical and relative")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("package path cannot contain empty, dot, or parent segments")
    if any(
        not part
        or not part[0].isalnum()
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in part
        )
        for part in path.parts
    ):
        raise ValueError("package path contains a non-portable segment")
    if required_prefix is not None and path.parts[0] != required_prefix:
        raise ValueError(f"package path must be below {required_prefix}/")


class PhaseIIIReviewEvidenceArtifact(ContractModel):
    """One allow-listed evidence file copied into an immutable review package."""

    role: OperatorIdentifier
    relative_path: NonEmptyString
    sha256: Sha256Hex
    size_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_evidence_path(self) -> Self:
        validate_phase3_review_relative_path(
            self.relative_path,
            required_prefix="evidence",
        )
        return self


class PhaseIIIReviewTableArtifact(ContractModel):
    """Generated target-review table bound to every permitted item."""

    role: Literal["review_targets"]
    relative_path: Literal["review_targets.tsv"]
    sha256: Sha256Hex
    size_bytes: PositiveInt
    row_count: int = Field(ge=0)
    target_item_ids: tuple[OperatorIdentifier, ...]

    @model_validator(mode="after")
    def _validate_table_targets(self) -> Self:
        if self.target_item_ids != tuple(sorted(set(self.target_item_ids))):
            raise ValueError("review table target IDs must be unique and sorted")
        return self


def phase3_review_package_content_sha256(
    *,
    evidence_inventory: tuple[PhaseIIIReviewEvidenceArtifact, ...],
    review_tables: tuple[PhaseIIIReviewTableArtifact, ...],
) -> str:
    """Hash the complete allow-listed package payload without self-reference."""

    return canonical_digest(
        {
            "evidence_inventory": evidence_inventory,
            "review_tables": review_tables,
        }
    )


class PhaseIIIReviewPackageManifest(_ContentAddressedContract):
    """Path-free content manifest for one checkpoint and one crystal."""

    _identity_field: ClassVar[str] = "review_package_id"
    _identity_prefix: ClassVar[str] = "phase3reviewpkg_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["phase3-review-package-v1", "phase3-review-package-v2"]
    review_package_id: PhaseIIIReviewPackageIdentifier
    checkpoint: PhaseIIIReviewCheckpoint
    owned_parent_run_id: OperatorIdentifier
    parent_profile: OperatorIdentifier
    parent_phase: OperatorIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    crystal_id: OperatorIdentifier
    created_at: UtcTimestamp
    permitted_targets: tuple[PhaseIIIReviewPackageTarget, ...]
    evidence_inventory: tuple[PhaseIIIReviewEvidenceArtifact, ...] = Field(min_length=1)
    review_tables: tuple[PhaseIIIReviewTableArtifact, ...] = Field(min_length=1)
    package_content_sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_package_metadata(self) -> Self:
        if (
            self.adapter_version == "phase3-review-package-v1"
            and self.checkpoint
            not in {
                PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
                PhaseIIIReviewCheckpoint.A_SEED,
            }
        ):
            raise ValueError(
                "review-package-v1 supports crystallographic and A-seed review only"
            )
        target_keys = tuple(
            (target.crystal_id, target.item_id) for target in self.permitted_targets
        )
        if not target_keys and (
            self.adapter_version != "phase3-review-package-v2"
            or self.checkpoint is not PhaseIIIReviewCheckpoint.A_SEED
        ):
            raise ValueError(
                "only a v2 A-seed review package may retain zero review targets"
            )
        if target_keys != tuple(sorted(set(target_keys))):
            raise ValueError("review package targets must be unique and sorted")
        if any(crystal_id != self.crystal_id for crystal_id, _ in target_keys):
            raise ValueError("review package must contain exactly one crystal")

        evidence_keys = tuple(
            (artifact.role, artifact.relative_path)
            for artifact in self.evidence_inventory
        )
        if evidence_keys != tuple(sorted(evidence_keys)):
            raise ValueError("review evidence must be canonically sorted")
        roles = tuple(role for role, _ in evidence_keys)
        paths = tuple(path for _, path in evidence_keys)
        if len(roles) != len(set(roles)):
            raise ValueError("review evidence roles must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("review evidence paths must be unique")
        if not target_keys and "mr_seed_review_manifest" not in roles:
            raise ValueError(
                "empty A-seed review requires its completed MR-seed manifest"
            )

        if len(self.review_tables) != 1:
            raise ValueError("review-package-v1 requires exactly one review table")
        table = self.review_tables[0]
        target_item_ids = tuple(item_id for _, item_id in target_keys)
        if table.row_count != len(target_item_ids):
            raise ValueError("review table row count does not cover every target")
        if table.target_item_ids != target_item_ids:
            raise ValueError("review table target IDs do not cover every target")
        if table.relative_path in paths:
            raise ValueError("review table and evidence paths must be distinct")

        expected_content_sha256 = phase3_review_package_content_sha256(
            evidence_inventory=self.evidence_inventory,
            review_tables=self.review_tables,
        )
        if self.package_content_sha256 != expected_content_sha256:
            raise ValueError(
                "package_content_sha256 does not match the allow-listed files"
            )
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
    "PhaseIIIReviewEvidenceArtifact",
    "PhaseIIIReviewPackageManifest",
    "PhaseIIIReviewPackageTarget",
    "PhaseIIIReviewTableArtifact",
    "phase3_review_package_content_sha256",
    "validate_phase3_review_relative_path",
]
