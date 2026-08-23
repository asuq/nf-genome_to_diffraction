"""Phase III attempt contracts for one bounded composition fan-out.

These records are an execution boundary, not a molecular-replacement result.
They bind the authoritative shared-depth plan and its selected attempt inventory
to every immutable identity needed by a later executor.  No Phaser parameter,
score, placement, or scientific support is introduced here.

``CompositionAttemptInventory`` retains the complete parent beam, diffraction
selection, Free-R identity, all-model-registry identity, and an opaque global
execution identity.  Each compact ``CompositionAttemptTask`` is content-
addressed over the exact selected candidate and model-resolution identities.
The inventory validator reconstructs those references from the embedded plan,
so a selected row cannot be silently omitted, duplicated, or rebound.
"""

from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.schemas.base import PositiveInt
from genome_to_diffraction.schemas.v2.component_execution_input import (
    ComponentExpansionExecutionInput,
    ComponentExpansionExecutionInputIdentifier,
)
from genome_to_diffraction.schemas.v2.composition import (
    AllModelRegistryIdentifier,
    ComponentSpecIdentifier,
    CompositionExpansionDepthCandidate,
    CompositionExpansionDepthPlan,
    CompositionState,
    CompositionStateIdentifier,
    ExpansionDepthCandidateIdentifier,
    ExpansionDepthPlanIdentifier,
    ExpansionDisposition,
    RegistryModelResolution,
    RegistryModelResolutionIdentifier,
    RegistryModelResolutionScope,
    _ContentAddressedContract,
)
from genome_to_diffraction.schemas.v2.diffraction import (
    DiffractionSelection,
    DiffractionSelectionIdentifier,
    FreeRIdentity,
    FreeRIdentityIdentifier,
)
from genome_to_diffraction.schemas.v2.execution import ExecutionIdentityIdentifier

CompositionAttemptIdentifier = Annotated[
    str,
    Field(pattern=r"^compattempt_[a-f0-9]{64}$"),
]
CompositionAttemptInventoryIdentifier = Annotated[
    str,
    Field(pattern=r"^compattemptinventory_[a-f0-9]{64}$"),
]


class CompositionAttemptInventoryStatus(StrEnum):
    """Typed scheduling state before any external execution."""

    READY = "ready"
    EMPTY_NO_MODEL = "empty_no_model"
    EMPTY_NO_SELECTED_ATTEMPTS = "empty_no_selected_attempts"


class CompositionAttemptTask(_ContentAddressedContract):
    """One immutable selected attempt and all of its content identities."""

    _identity_field: ClassVar[str] = "attempt_id"
    _identity_prefix: ClassVar[str] = "compattempt_"

    schema_version: Literal["2.0"]
    attempt_id: CompositionAttemptIdentifier
    allocation_rank: PositiveInt = Field(le=25)
    depth_plan_id: ExpansionDepthPlanIdentifier
    parent_state_id: CompositionStateIdentifier
    depth_candidate_id: ExpansionDepthCandidateIdentifier
    component_spec_id: ComponentSpecIdentifier
    parent_model_resolution_ids: tuple[RegistryModelResolutionIdentifier, ...] = Field(
        min_length=1, max_length=5
    )
    candidate_model_resolution_id: RegistryModelResolutionIdentifier
    diffraction_selection_id: DiffractionSelectionIdentifier
    free_r_identity_id: FreeRIdentityIdentifier
    model_registry_id: AllModelRegistryIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    component_execution_input_id: ComponentExpansionExecutionInputIdentifier

    @model_validator(mode="after")
    def _validate_task_identity_set(self) -> Self:
        if len(set(self.parent_model_resolution_ids)) != len(
            self.parent_model_resolution_ids
        ):
            raise ValueError("parent model resolution identities must be unique")
        return self


class CompositionAttemptInventory(_ContentAddressedContract):
    """Validated complete-item source for one shared composition depth.

    ``attempts`` is empty for valid scientific no-work states.  The status
    distinguishes complete no-model absence from other zero-selection paths.
    A ready inventory contains exactly one task for every selected depth
    candidate, in allocation order, never more than the shared 25-attempt cap.
    """

    _identity_field: ClassVar[str] = "inventory_id"
    _identity_prefix: ClassVar[str] = "compattemptinventory_"

    schema_version: Literal["2.0"]
    inventory_id: CompositionAttemptInventoryIdentifier
    status: CompositionAttemptInventoryStatus
    depth_plan: CompositionExpansionDepthPlan
    parent_states: tuple[CompositionState, ...] = Field(min_length=1, max_length=3)
    diffraction_selection: DiffractionSelection
    free_r_identity: FreeRIdentity
    model_registry_id: AllModelRegistryIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    execution_inputs: tuple[ComponentExpansionExecutionInput, ...]
    attempt_count: int = Field(ge=0, le=25)
    unsearchable_no_model_count: int = Field(ge=0)
    attempts: tuple[CompositionAttemptTask, ...]

    @model_validator(mode="after")
    def _validate_complete_inventory(self) -> Self:
        plan = self.depth_plan
        if plan.model_registry_id is None:
            raise ValueError("execution inventory requires a registry-bound plan")
        if self.model_registry_id != plan.model_registry_id:
            raise ValueError("execution inventory uses a different model registry")

        plan_parents = tuple(parent.parent_state_id for parent in plan.parents)
        state_ids = tuple(state.state_id for state in self.parent_states)
        if state_ids != plan_parents:
            raise ValueError("parent states do not match the ordered depth-plan beam")
        parent_by_id = {state.state_id: state for state in self.parent_states}
        for plan_parent, state in zip(
            plan.parents,
            self.parent_states,
            strict=True,
        ):
            if (
                state.crystal_id != plan.crystal_id
                or state.diffraction_dataset_id != plan.diffraction_dataset_id
                or state.depth != plan.parent_depth
                or tuple(component.label for component in state.components)
                != plan_parent.parent_component_labels
                or tuple(component.sequence_group_id for component in state.components)
                != plan_parent.parent_sequence_group_ids
            ):
                raise ValueError("parent state content disagrees with the depth plan")

        selection = self.diffraction_selection
        if (
            selection.crystal_id != plan.crystal_id
            or selection.diffraction_dataset_id != plan.diffraction_dataset_id
            or any(
                state.diffraction_sha256 != selection.mtz_sha256
                for state in self.parent_states
            )
        ):
            raise ValueError("diffraction selection does not match the parent beam")
        free_r = self.free_r_identity
        if (
            free_r.diffraction_selection_id != selection.diffraction_selection_id
            or free_r.diffraction_dataset_id != selection.diffraction_dataset_id
            or free_r.crystal_id != selection.crystal_id
            or free_r.mtz_sha256 != selection.mtz_sha256
            or free_r.observation_dataset_id != selection.observation_dataset_id
        ):
            raise ValueError("Free-R identity does not match diffraction selection")

        no_model_count = sum(
            candidate.hypothesis.disposition
            is ExpansionDisposition.UNSEARCHABLE_NO_MODEL
            for candidate in plan.candidates
        )
        if self.unsearchable_no_model_count != no_model_count:
            raise ValueError("no-model count does not match the depth plan")
        if (
            self.attempt_count != len(self.attempts)
            or self.attempt_count != plan.selected_attempt_count
        ):
            raise ValueError("attempt count does not match selected depth candidates")
        if len(self.execution_inputs) != self.attempt_count:
            raise ValueError("execution-input count does not match selected attempts")
        if len({attempt.attempt_id for attempt in self.attempts}) != len(self.attempts):
            raise ValueError("composition attempt identities must be unique")
        execution_inputs_by_id = {
            item.execution_input_id: item for item in self.execution_inputs
        }
        if len(execution_inputs_by_id) != len(self.execution_inputs):
            raise ValueError("component execution-input identities must be unique")

        selected = tuple(
            sorted(
                (
                    candidate
                    for candidate in plan.candidates
                    if candidate.hypothesis.disposition is ExpansionDisposition.SELECTED
                ),
                key=_selected_candidate_allocation_rank,
            )
        )
        if len(selected) != len(self.attempts):
            raise ValueError("selected candidate inventory is incomplete")
        resolutions_by_id = {
            resolution.resolution_id: resolution
            for resolution in plan.model_resolutions
        }
        resolutions_by_parent_and_spec = {
            (resolution.parent_state_id, resolution.component_spec_id): resolution
            for resolution in plan.model_resolutions
        }
        for task, candidate in zip(self.attempts, selected, strict=True):
            state = parent_by_id[candidate.parent_state_id]
            execution_input = execution_inputs_by_id.get(
                task.component_execution_input_id
            )
            if execution_input is None:
                raise ValueError("attempt lacks its exact component execution input")
            parent_resolution_ids = tuple(
                _required_parent_resolution(
                    resolutions_by_parent_and_spec,
                    state,
                    component.component_spec_id,
                ).resolution_id
                for component in state.components
            )
            candidate_resolution = _required_candidate_resolution(
                resolutions_by_parent_and_spec,
                candidate,
            )
            if (
                task.allocation_rank != candidate.allocation_rank
                or task.depth_plan_id != plan.depth_plan_id
                or task.parent_state_id != state.state_id
                or task.depth_candidate_id != candidate.depth_candidate_id
                or task.component_spec_id
                != candidate.hypothesis.component.component_spec_id
                or task.parent_model_resolution_ids != parent_resolution_ids
                or task.candidate_model_resolution_id
                != candidate_resolution.resolution_id
                or task.diffraction_selection_id != selection.diffraction_selection_id
                or task.free_r_identity_id != free_r.free_r_identity_id
                or task.model_registry_id != self.model_registry_id
                or task.execution_identity_id != self.execution_identity_id
                or execution_input.depth_plan_id != plan.depth_plan_id
                or execution_input.selected_candidate.depth_candidate_id
                != candidate.depth_candidate_id
                or execution_input.parent_state.state_id != state.state_id
                or execution_input.candidate_model_resolution.resolution_id
                != candidate_resolution.resolution_id
                or execution_input.diffraction_selection.diffraction_selection_id
                != selection.diffraction_selection_id
                or execution_input.free_r_identity.free_r_identity_id
                != free_r.free_r_identity_id
            ):
                raise ValueError("attempt task does not match its selected candidate")
            bound_resolutions = (
                *(
                    resolutions_by_id[resolution_id]
                    for resolution_id in task.parent_model_resolution_ids
                ),
                resolutions_by_id[task.candidate_model_resolution_id],
            )
            if any(not resolution.available for resolution in bound_resolutions):
                raise ValueError("selected attempt contains an unavailable model")

        expected_status = _expected_status(plan)
        if self.status is not expected_status:
            raise ValueError("attempt inventory status does not match plan contents")
        return self


def _selected_candidate_allocation_rank(
    candidate: CompositionExpansionDepthCandidate,
) -> int:
    if candidate.allocation_rank is None:  # pragma: no cover - schema guard
        raise ValueError("selected depth candidate lacks an allocation rank")
    return candidate.allocation_rank


def _required_parent_resolution(
    resolutions: dict[tuple[str, str], RegistryModelResolution],
    state: CompositionState,
    component_spec_id: str,
) -> RegistryModelResolution:
    resolution = resolutions.get((state.state_id, component_spec_id))
    if (
        resolution is None
        or resolution.scope is not RegistryModelResolutionScope.PARENT_COMPONENT
    ):
        raise ValueError("parent component lacks its exact model resolution")
    return resolution


def _required_candidate_resolution(
    resolutions: dict[tuple[str, str], RegistryModelResolution],
    candidate: CompositionExpansionDepthCandidate,
) -> RegistryModelResolution:
    component_spec_id = candidate.hypothesis.component.component_spec_id
    resolution = resolutions.get((candidate.parent_state_id, component_spec_id))
    if (
        resolution is None
        or resolution.scope is not RegistryModelResolutionScope.CANDIDATE_COPY
    ):
        raise ValueError("selected candidate lacks its exact model resolution")
    return resolution


def _expected_status(
    plan: CompositionExpansionDepthPlan,
) -> CompositionAttemptInventoryStatus:
    if plan.selected_attempt_count:
        return CompositionAttemptInventoryStatus.READY
    dispositions = {candidate.hypothesis.disposition for candidate in plan.candidates}
    if ExpansionDisposition.UNSEARCHABLE_NO_MODEL in dispositions and dispositions <= {
        ExpansionDisposition.UNSEARCHABLE_NO_MODEL,
        ExpansionDisposition.EXCLUDED_PHYSICAL_IMPOSSIBLE,
    }:
        return CompositionAttemptInventoryStatus.EMPTY_NO_MODEL
    return CompositionAttemptInventoryStatus.EMPTY_NO_SELECTED_ATTEMPTS


__all__ = [
    "CompositionAttemptInventory",
    "CompositionAttemptInventoryStatus",
    "CompositionAttemptTask",
]
