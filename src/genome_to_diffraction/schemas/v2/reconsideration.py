"""Explicit, source-bound selection of deferred first-copy alternatives.

This is authority to schedule the named hypotheses, not approval of an A seed.
The existing A checkpoint still follows MR. The selection binds one owned parent
and review package, exact human decisions, model/copy targets and a finite budget.
No tool is executed by this contract. Invalid IDs, duplicate targets, blank human
text and budget excess fail validation; the content key is ``selection_id``.
The local validator also authenticates the referenced evidence and model universe.
"""

from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    OperatorIdentifier,
    Sha256Hex,
    UtcTimestamp,
)
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract
from genome_to_diffraction.schemas.v2.execution import GitObjectHex
from genome_to_diffraction.schemas.v2.owned_run import OwnedRunRegistryIdentifier
from genome_to_diffraction.schemas.v2.review import PhaseIIIReviewPackageIdentifier


class FirstCopySelectionTarget(ContractModel):
    """One exact catalogue model and a member of the full Matthews inventory."""

    sequence_group_id: Annotated[str, Field(pattern=r"^seq_[a-f0-9]{64}$")]
    model_id: OperatorIdentifier
    matthews_hypothesis_id: Annotated[str, Field(pattern=r"^matthews_[a-f0-9]{64}$")]


class ReviewedFirstCopySelection(_ContentAddressedContract):
    """Human-selected alternatives after rejected or unresolved A review."""

    _identity_field: ClassVar[str] = "selection_id"
    _identity_prefix: ClassVar[str] = "firstcopyselect_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["reviewed-first-copy-selection-v1"]
    selection_id: Annotated[str, Field(pattern=r"^firstcopyselect_[a-f0-9]{64}$")]
    owned_parent_run_id: OperatorIdentifier
    owned_run_registry_id: OwnedRunRegistryIdentifier
    source_commit: GitObjectHex
    source_tree: GitObjectHex
    crystal_id: OperatorIdentifier
    review_package_id: PhaseIIIReviewPackageIdentifier
    review_package_manifest_sha256: Sha256Hex
    parent_decisions_sha256: Sha256Hex
    parent_funnel_manifest_sha256: Sha256Hex
    trigger_solution_ids: tuple[OperatorIdentifier, ...] = Field(min_length=1)
    targets: tuple[FirstCopySelectionTarget, ...] = Field(min_length=1, max_length=25)
    maximum_attempts: int = Field(ge=1, le=25)
    reviewer: NonEmptyString
    reviewed_at: UtcTimestamp
    reason: NonEmptyString

    @model_validator(mode="after")
    def _validate_explicit_selection(self) -> Self:
        if len(self.targets) > self.maximum_attempts:
            raise ValueError("selected hypotheses exceed the explicit attempt budget")
        keys = tuple(
            (row.sequence_group_id, row.model_id, row.matthews_hypothesis_id)
            for row in self.targets
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("selected targets must be unique and canonically sorted")
        if self.trigger_solution_ids != tuple(sorted(set(self.trigger_solution_ids))):
            raise ValueError("trigger solution IDs must be unique and sorted")
        if not self.reviewer.strip() or not self.reason.strip():
            raise ValueError("selection reviewer and reason must not be blank")
        return self


__all__ = ["FirstCopySelectionTarget", "ReviewedFirstCopySelection"]
