"""Path-free contracts for the fixed Phase III unknown-pass-1 screen stub.

Scientific purpose
------------------
These records define the scheduling boundary after crystallographic review and
before any first-copy molecular-replacement execution.  They retain three
complete crystal items, every ranked A hypothesis, typed hold and scientific
no-work branches, and the exact selected task inventory.  They do not execute
Phaser or promote a sequence, placement, or composition claim.

Inputs and outputs
------------------
The inventory embeds one :class:`PhaseIIIExecutionIdentity`, one checksum-bound
crystallographic review binding and decision file, one shared
catalogue/provider/localisation preparation, exactly three crystal items, and
zero to 75 selected A tasks.  Machine paths and operator-configurable crystal
selectors or thresholds are absent from all records.

No external command or version is introduced here.  Contract, identity,
coverage, ordering, cap, or review inconsistencies fail validation.  ``hold``,
``empty_no_model``, and ``empty_no_hypotheses`` are successful typed scheduling
outcomes.  Content identifiers are the cache keys.  Focused builder, mutation,
branch, task-coverage, and cached-Nextflow-resume tests live in
``tests/unit/test_unknown_pass1_screen.py`` and
``tests/scripts/check_unknown_pass1_screen.py``.
"""

from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.schemas.base import (
    NonEmptyString,
    OperatorIdentifier,
    PositiveInt,
    Sha256Hex,
)
from genome_to_diffraction.schemas.v2.composition import (
    ModelUnavailableReason,
    SequenceGroupIdentifier,
    _ContentAddressedContract,
)
from genome_to_diffraction.schemas.v2.execution import (
    ExecutionIdentityIdentifier,
    PhaseIIIExecutionIdentity,
)
from genome_to_diffraction.schemas.v2.review import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
)

UnknownPass1SharedPreparationIdentifier = Annotated[
    str,
    Field(pattern=r"^unknownshared_[a-f0-9]{64}$"),
]
UnknownPass1ReviewBindingIdentifier = Annotated[
    str,
    Field(pattern=r"^unknownreview_[a-f0-9]{64}$"),
]
UnknownPass1AHypothesisIdentifier = Annotated[
    str,
    Field(pattern=r"^unknownahyp_[a-f0-9]{64}$"),
]
UnknownPass1CrystalItemIdentifier = Annotated[
    str,
    Field(pattern=r"^unknowncrystal_[a-f0-9]{64}$"),
]
UnknownPass1ATaskIdentifier = Annotated[
    str,
    Field(pattern=r"^unknownatask_[a-f0-9]{64}$"),
]
UnknownPass1ScreenInventoryIdentifier = Annotated[
    str,
    Field(pattern=r"^unknownscreen_[a-f0-9]{64}$"),
]


class UnknownPass1AHypothesisDisposition(StrEnum):
    """Complete first-copy scheduling disposition for one ranked hypothesis."""

    SELECTED = "selected"
    DEFERRED_CAP = "deferred_cap"
    UNSEARCHABLE_NO_MODEL = "unsearchable_no_model"


class UnknownPass1CrystalBranch(StrEnum):
    """Typed post-review scheduling branch for one complete crystal item."""

    READY = "ready"
    HELD = "held"
    EMPTY_NO_MODEL = "empty_no_model"
    EMPTY_NO_HYPOTHESES = "empty_no_hypotheses"


class UnknownPass1SharedPreparation(_ContentAddressedContract):
    """One reusable local preparation shared by all three crystal items."""

    _identity_field: ClassVar[str] = "preparation_id"
    _identity_prefix: ClassVar[str] = "unknownshared_"

    schema_version: Literal["2.0"]
    preparation_id: UnknownPass1SharedPreparationIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    catalogue_preparation_id: NonEmptyString
    catalogue_preparation_sha256: Sha256Hex
    provider_preparation_id: NonEmptyString
    provider_preparation_sha256: Sha256Hex
    localisation_preparation_id: NonEmptyString
    localisation_preparation_sha256: Sha256Hex
    provider_remote_sequence_submission: Literal[False] = False
    localisation_execution_mode: Literal["local_offline"] = "local_offline"


class UnknownPass1ReviewBinding(_ContentAddressedContract):
    """Verified file-stage provenance retained without machine paths."""

    _identity_field: ClassVar[str] = "review_binding_id"
    _identity_prefix: ClassVar[str] = "unknownreview_"

    schema_version: Literal["2.0"]
    review_binding_id: UnknownPass1ReviewBindingIdentifier
    checkpoint: Literal[PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC]
    stage_id: NonEmptyString
    stage_manifest_sha256: Sha256Hex
    decision_file_id: NonEmptyString
    canonical_decision_sha256: Sha256Hex
    owned_parent_run_id: NonEmptyString
    parent_profile: NonEmptyString
    parent_phase: NonEmptyString


class UnknownPass1AHypothesis(_ContentAddressedContract):
    """One ranked A hypothesis, including deferred and unavailable rows."""

    _identity_field: ClassVar[str] = "hypothesis_id"
    _identity_prefix: ClassVar[str] = "unknownahyp_"

    schema_version: Literal["2.0"]
    hypothesis_id: UnknownPass1AHypothesisIdentifier
    crystal_id: OperatorIdentifier
    candidate_rank: PositiveInt
    allocation_rank: Annotated[int, Field(gt=0, le=25)] | None = None
    sequence_group_id: SequenceGroupIdentifier
    requested_copy_count: Annotated[int, Field(gt=0, le=4)]
    model_id: NonEmptyString | None = None
    model_sha256: Sha256Hex | None = None
    disposition: UnknownPass1AHypothesisDisposition
    no_model_reason: ModelUnavailableReason | None = None

    @model_validator(mode="after")
    def _validate_disposition(self) -> Self:
        model_available = self.model_id is not None and self.model_sha256 is not None
        if (self.model_id is None) != (self.model_sha256 is None):
            raise ValueError("model identifier and checksum must be present together")
        if self.disposition is UnknownPass1AHypothesisDisposition.SELECTED:
            if not model_available or self.allocation_rank is None:
                raise ValueError("selected A hypothesis requires model and allocation")
            if self.no_model_reason is not None:
                raise ValueError("selected A hypothesis cannot have no-model reason")
        elif self.disposition is UnknownPass1AHypothesisDisposition.DEFERRED_CAP:
            if not model_available or self.allocation_rank is not None:
                raise ValueError(
                    "cap-deferred A hypothesis requires an unallocated model"
                )
            if self.no_model_reason is not None:
                raise ValueError(
                    "cap-deferred A hypothesis cannot have no-model reason"
                )
        else:
            if model_available or self.allocation_rank is not None:
                raise ValueError("no-model A hypothesis cannot be executable")
            if self.no_model_reason is None:
                raise ValueError("no-model A hypothesis requires a typed reason")
        return self


class UnknownPass1CrystalItem(_ContentAddressedContract):
    """One path-free complete item for a reviewed crystal."""

    _identity_field: ClassVar[str] = "crystal_item_id"
    _identity_prefix: ClassVar[str] = "unknowncrystal_"

    schema_version: Literal["2.0"]
    crystal_item_id: UnknownPass1CrystalItemIdentifier
    crystal_id: OperatorIdentifier
    mtz_artifact_id: NonEmptyString
    mtz_sha256: Sha256Hex
    execution_identity_id: ExecutionIdentityIdentifier
    shared_preparation_id: UnknownPass1SharedPreparationIdentifier
    review_binding_id: UnknownPass1ReviewBindingIdentifier
    review_item_id: NonEmptyString
    review_decision: Literal[
        PhaseIIIReviewDecisionValue.PROCEED,
        PhaseIIIReviewDecisionValue.HOLD,
    ]
    branch: UnknownPass1CrystalBranch
    candidate_count: int = Field(ge=0)
    selected_hypothesis_count: int = Field(ge=0, le=25)
    deferred_cap_count: int = Field(ge=0)
    unsearchable_no_model_count: int = Field(ge=0)
    hypotheses: tuple[UnknownPass1AHypothesis, ...]

    @model_validator(mode="after")
    def _validate_branch_inventory(self) -> Self:
        ordered = tuple(sorted(self.hypotheses, key=lambda item: item.candidate_rank))
        if self.hypotheses != ordered:
            raise ValueError("A hypotheses must be ordered by candidate rank")
        if tuple(item.candidate_rank for item in self.hypotheses) != tuple(
            range(1, len(self.hypotheses) + 1)
        ):
            raise ValueError("A hypothesis candidate ranks must be contiguous")
        if any(item.crystal_id != self.crystal_id for item in self.hypotheses):
            raise ValueError("crystal item contains another crystal's A hypothesis")
        hypothesis_ids = tuple(item.hypothesis_id for item in self.hypotheses)
        if len(hypothesis_ids) != len(set(hypothesis_ids)):
            raise ValueError("A hypothesis identities must be unique per crystal")

        selected = tuple(
            item
            for item in self.hypotheses
            if item.disposition is UnknownPass1AHypothesisDisposition.SELECTED
        )
        deferred = sum(
            item.disposition is UnknownPass1AHypothesisDisposition.DEFERRED_CAP
            for item in self.hypotheses
        )
        no_model = sum(
            item.disposition is UnknownPass1AHypothesisDisposition.UNSEARCHABLE_NO_MODEL
            for item in self.hypotheses
        )
        if self.candidate_count != len(self.hypotheses):
            raise ValueError("candidate count does not match A hypothesis inventory")
        if self.selected_hypothesis_count != len(selected):
            raise ValueError("selected count does not match A hypothesis inventory")
        if self.deferred_cap_count != deferred:
            raise ValueError("deferred count does not match A hypothesis inventory")
        if self.unsearchable_no_model_count != no_model:
            raise ValueError("no-model count does not match A hypothesis inventory")
        if tuple(item.allocation_rank for item in selected) != tuple(
            range(1, len(selected) + 1)
        ):
            raise ValueError("selected A allocation ranks must be contiguous")

        if self.review_decision is PhaseIIIReviewDecisionValue.HOLD:
            if self.branch is not UnknownPass1CrystalBranch.HELD or self.hypotheses:
                raise ValueError("held crystal must schedule no A hypothesis")
            return self
        if self.branch is UnknownPass1CrystalBranch.READY:
            if not selected:
                raise ValueError("ready crystal requires selected A hypotheses")
        elif self.branch is UnknownPass1CrystalBranch.EMPTY_NO_MODEL:
            if selected or not self.hypotheses or no_model != len(self.hypotheses):
                raise ValueError(
                    "empty-no-model crystal must retain only no-model rows"
                )
        elif self.branch is UnknownPass1CrystalBranch.EMPTY_NO_HYPOTHESES:
            if self.hypotheses:
                raise ValueError("empty-hypothesis crystal cannot contain candidates")
        else:
            raise ValueError("proceed decision cannot enter the held branch")
        return self


class UnknownPass1AHypothesisTask(_ContentAddressedContract):
    """One selected A hypothesis with all shared and crystal identities."""

    _identity_field: ClassVar[str] = "task_id"
    _identity_prefix: ClassVar[str] = "unknownatask_"

    schema_version: Literal["2.0"]
    task_id: UnknownPass1ATaskIdentifier
    crystal_id: OperatorIdentifier
    crystal_item_id: UnknownPass1CrystalItemIdentifier
    hypothesis_id: UnknownPass1AHypothesisIdentifier
    allocation_rank: Annotated[int, Field(gt=0, le=25)]
    model_id: NonEmptyString
    model_sha256: Sha256Hex
    mtz_sha256: Sha256Hex
    execution_identity_id: ExecutionIdentityIdentifier
    shared_preparation_id: UnknownPass1SharedPreparationIdentifier
    review_binding_id: UnknownPass1ReviewBindingIdentifier


class UnknownPass1ScreenInventory(_ContentAddressedContract):
    """Exact three-crystal complete-item and selected-task inventory."""

    _identity_field: ClassVar[str] = "inventory_id"
    _identity_prefix: ClassVar[str] = "unknownscreen_"

    schema_version: Literal["2.0"]
    inventory_id: UnknownPass1ScreenInventoryIdentifier
    execution_identity: PhaseIIIExecutionIdentity
    shared_preparation: UnknownPass1SharedPreparation
    review_binding: UnknownPass1ReviewBinding
    review_decisions: PhaseIIIReviewDecisionFile
    crystal_count: Literal[3]
    ready_count: int = Field(ge=0, le=3)
    held_count: int = Field(ge=0, le=3)
    empty_no_model_count: int = Field(ge=0, le=3)
    empty_no_hypotheses_count: int = Field(ge=0, le=3)
    hypothesis_task_count: int = Field(ge=0, le=75)
    crystals: tuple[UnknownPass1CrystalItem, ...] = Field(
        min_length=3,
        max_length=3,
    )
    hypothesis_tasks: tuple[UnknownPass1AHypothesisTask, ...]

    @model_validator(mode="after")
    def _validate_complete_screen(self) -> Self:
        execution_id = self.execution_identity.execution_identity_id
        if self.shared_preparation.execution_identity_id != execution_id:
            raise ValueError("shared preparation uses another execution identity")
        if (
            self.review_binding.checkpoint
            is not PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC
        ):
            raise ValueError("unknown pass 1 requires crystallographic review")
        decisions = self.review_decisions
        if (
            decisions.checkpoint is not PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC
            or decisions.decision_file_id != self.review_binding.decision_file_id
            or decisions.owned_parent_run_id != self.review_binding.owned_parent_run_id
        ):
            raise ValueError("review decisions do not match the staged review binding")

        crystal_ids = tuple(item.crystal_id for item in self.crystals)
        if crystal_ids != tuple(sorted(crystal_ids)):
            raise ValueError("unknown-screen crystal items must be sorted")
        if len(set(crystal_ids)) != 3:
            raise ValueError("unknown screen requires three distinct crystals")
        decision_by_target = {
            (item.crystal_id, item.item_id): item for item in decisions.decisions
        }
        if len(decision_by_target) != 3:
            raise ValueError("unknown screen requires one review decision per crystal")

        mtz_by_crystal = {
            artifact.owner_id: artifact
            for artifact in self.execution_identity.crystal_artifacts
            if artifact.role == "mtz"
        }
        if set(mtz_by_crystal) != set(crystal_ids):
            raise ValueError("execution identity MTZ inventory differs from crystals")
        for item in self.crystals:
            decision = decision_by_target.get((item.crystal_id, item.review_item_id))
            artifact = mtz_by_crystal[item.crystal_id]
            if decision is None or decision.decision is not item.review_decision:
                raise ValueError("crystal item differs from its review decision")
            if (
                item.mtz_artifact_id != artifact.artifact_id
                or item.mtz_sha256 != artifact.sha256
                or item.execution_identity_id != execution_id
                or item.shared_preparation_id != self.shared_preparation.preparation_id
                or item.review_binding_id != self.review_binding.review_binding_id
            ):
                raise ValueError("crystal item lacks an exact complete identity")

        branch_counts = {
            branch: sum(item.branch is branch for item in self.crystals)
            for branch in UnknownPass1CrystalBranch
        }
        if (
            self.ready_count != branch_counts[UnknownPass1CrystalBranch.READY]
            or self.held_count != branch_counts[UnknownPass1CrystalBranch.HELD]
            or self.empty_no_model_count
            != branch_counts[UnknownPass1CrystalBranch.EMPTY_NO_MODEL]
            or self.empty_no_hypotheses_count
            != branch_counts[UnknownPass1CrystalBranch.EMPTY_NO_HYPOTHESES]
        ):
            raise ValueError("screen branch counts do not match crystal items")

        selected_rows = tuple(
            (item, hypothesis)
            for item in self.crystals
            for hypothesis in item.hypotheses
            if hypothesis.disposition is UnknownPass1AHypothesisDisposition.SELECTED
        )
        tasks = self.hypothesis_tasks
        if tasks != tuple(
            sorted(tasks, key=lambda item: (item.crystal_id, item.allocation_rank))
        ):
            raise ValueError("A tasks must be sorted by crystal and allocation")
        if self.hypothesis_task_count != len(tasks) or len(tasks) != len(selected_rows):
            raise ValueError("A task inventory does not cover every selected row")
        if len({task.task_id for task in tasks}) != len(tasks):
            raise ValueError("A task identities must be unique")
        tasks_by_hypothesis = {task.hypothesis_id: task for task in tasks}
        if len(tasks_by_hypothesis) != len(tasks):
            raise ValueError("selected A hypothesis appears in multiple tasks")
        for item, hypothesis in selected_rows:
            task = tasks_by_hypothesis.get(hypothesis.hypothesis_id)
            if task is None or hypothesis.allocation_rank is None:
                raise ValueError("selected A hypothesis lacks its exact task")
            if (
                task.crystal_id != item.crystal_id
                or task.crystal_item_id != item.crystal_item_id
                or task.allocation_rank != hypothesis.allocation_rank
                or task.model_id != hypothesis.model_id
                or task.model_sha256 != hypothesis.model_sha256
                or task.mtz_sha256 != item.mtz_sha256
                or task.execution_identity_id != execution_id
                or task.shared_preparation_id != self.shared_preparation.preparation_id
                or task.review_binding_id != self.review_binding.review_binding_id
            ):
                raise ValueError("A task differs from its complete selected row")
        return self


__all__ = [
    "UnknownPass1AHypothesis",
    "UnknownPass1AHypothesisDisposition",
    "UnknownPass1AHypothesisTask",
    "UnknownPass1CrystalBranch",
    "UnknownPass1CrystalItem",
    "UnknownPass1ReviewBinding",
    "UnknownPass1ScreenInventory",
    "UnknownPass1SharedPreparation",
]
