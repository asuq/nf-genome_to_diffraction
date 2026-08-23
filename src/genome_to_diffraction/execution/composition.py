"""Build the Phase III complete-item composition execution inventory.

Scientific purpose
------------------
This adapter turns one authoritative
:class:`~genome_to_diffraction.schemas.v2.CompositionExpansionDepthPlan` and
its ordered selected
:class:`~genome_to_diffraction.ranking.composition.PlannedCompositionAttempt`
rows into immutable execution task identities. It performs no Phaser,
refinement, model selection, result parsing, or scientific promotion.

Inputs are the complete retained parent-state beam, dataset-qualified
diffraction selection, exact Free-R identity, and an opaque global Phase III
execution identity.  The registry-bound depth plan supplies every parent and
candidate model resolution.  Outputs are one deterministic JSON inventory and
zero to 25 compact task rows.  Scientific no-work states remain successful,
typed empty inventories; malformed, missing, reordered, or unavailable
selected inputs raise :class:`CompositionAttemptInventoryError`.

The inventory content ID is the adapter cache key.  Each attempt ID separately
binds the plan, parent, selected candidate, model resolutions, diffraction,
Free-R, all-model registry, and global execution identities.  Focused unit and
Nextflow cached-resume coverage lives in
``tests/unit/test_composition_attempt_inventory.py`` and
``tests/scripts/check_composition_attempt_fanout.py``.
"""

from pathlib import Path

from pydantic import ValidationError

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.ranking.composition import PlannedCompositionAttempt
from genome_to_diffraction.schemas.v2 import (
    ComponentExpansionExecutionInput,
    CompositionExpansionDepthPlan,
    CompositionState,
    DiffractionSelection,
    FreeRIdentity,
)
from genome_to_diffraction.schemas.v2.composition import (
    CompositionExpansionDepthCandidate,
    ExpansionDisposition,
    RegistryModelResolution,
    RegistryModelResolutionScope,
)
from genome_to_diffraction.schemas.v2.composition_attempts import (
    CompositionAttemptInventory,
    CompositionAttemptInventoryStatus,
    CompositionAttemptTask,
)
from genome_to_diffraction.status import InputContractError


class CompositionAttemptInventoryError(InputContractError):
    """A selected composition attempt cannot form one complete task item."""


def _selected_candidates(
    plan: CompositionExpansionDepthPlan,
) -> tuple[CompositionExpansionDepthCandidate, ...]:
    selected = tuple(
        candidate
        for candidate in plan.candidates
        if candidate.hypothesis.disposition is ExpansionDisposition.SELECTED
    )
    if any(candidate.allocation_rank is None for candidate in selected):
        raise CompositionAttemptInventoryError(
            "selected composition candidate lacks an allocation rank"
        )
    return tuple(
        sorted(
            selected,
            key=lambda candidate: candidate.allocation_rank or 0,
        )
    )


def _verify_planned_attempts(
    *,
    plan: CompositionExpansionDepthPlan,
    planned_attempts: tuple[PlannedCompositionAttempt, ...],
) -> tuple[CompositionExpansionDepthCandidate, ...]:
    selected = _selected_candidates(plan)
    expected = tuple(
        (
            candidate.allocation_rank,
            candidate.parent_state_id,
            candidate.depth_candidate_id,
            candidate.hypothesis.component.component_spec_id,
        )
        for candidate in selected
    )
    observed = tuple(
        (
            attempt.allocation_rank,
            attempt.parent_state_id,
            attempt.depth_candidate_id,
            attempt.component_spec_id,
        )
        for attempt in planned_attempts
    )
    if observed != expected:
        raise CompositionAttemptInventoryError(
            "planned attempt inventory does not exactly match selected depth rows"
        )
    return selected


def _parent_resolution_ids(
    *,
    plan: CompositionExpansionDepthPlan,
    state: CompositionState,
) -> tuple[str, ...]:
    resolutions = {
        (resolution.parent_state_id, resolution.component_spec_id): resolution
        for resolution in plan.model_resolutions
    }
    selected: list[str] = []
    for component in state.components:
        resolution = resolutions.get((state.state_id, component.component_spec_id))
        if (
            resolution is None
            or resolution.scope is not RegistryModelResolutionScope.PARENT_COMPONENT
            or not resolution.available
        ):
            raise CompositionAttemptInventoryError(
                "selected attempt parent lacks an available exact model resolution"
            )
        selected.append(resolution.resolution_id)
    return tuple(selected)


def _candidate_resolution(
    *,
    plan: CompositionExpansionDepthPlan,
    candidate: CompositionExpansionDepthCandidate,
) -> RegistryModelResolution:
    component = candidate.hypothesis.component
    resolution = next(
        (
            item
            for item in plan.model_resolutions
            if item.parent_state_id == candidate.parent_state_id
            and item.component_spec_id == component.component_spec_id
        ),
        None,
    )
    if (
        resolution is None
        or resolution.scope is not RegistryModelResolutionScope.CANDIDATE_COPY
        or not resolution.available
    ):
        raise CompositionAttemptInventoryError(
            "selected candidate lacks an available exact model resolution"
        )
    return resolution


def _inventory_status(
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


def build_composition_attempt_inventory(
    *,
    depth_plan: CompositionExpansionDepthPlan,
    planned_attempts: tuple[PlannedCompositionAttempt, ...],
    parent_states: tuple[CompositionState, ...],
    diffraction_selection: DiffractionSelection,
    free_r_identity: FreeRIdentity,
    execution_identity_id: str,
    execution_inputs: tuple[ComponentExpansionExecutionInput, ...],
) -> CompositionAttemptInventory:
    """Bind one selected shared-depth plan to complete immutable task identities."""

    if depth_plan.model_registry_id is None:
        raise CompositionAttemptInventoryError(
            "composition execution requires a registry-bound depth plan"
        )
    selected = _verify_planned_attempts(
        plan=depth_plan,
        planned_attempts=planned_attempts,
    )
    state_by_id = {state.state_id: state for state in parent_states}
    if len(state_by_id) != len(parent_states):
        raise CompositionAttemptInventoryError("duplicate parent state identity")
    execution_input_by_candidate = {
        (
            item.parent_state.state_id,
            item.selected_candidate.depth_candidate_id,
        ): item
        for item in execution_inputs
    }
    if len(execution_input_by_candidate) != len(execution_inputs):
        raise CompositionAttemptInventoryError("duplicate component execution input")
    expected_execution_keys = {
        (candidate.parent_state_id, candidate.depth_candidate_id)
        for candidate in selected
    }
    if set(execution_input_by_candidate) != expected_execution_keys:
        raise CompositionAttemptInventoryError(
            "component execution inputs do not exactly match selected attempts"
        )

    tasks: list[CompositionAttemptTask] = []
    ordered_execution_inputs: list[ComponentExpansionExecutionInput] = []
    try:
        for candidate in selected:
            state = state_by_id.get(candidate.parent_state_id)
            if state is None:
                raise CompositionAttemptInventoryError(
                    "selected attempt refers to a missing parent state"
                )
            resolution = _candidate_resolution(
                plan=depth_plan,
                candidate=candidate,
            )
            if candidate.allocation_rank is None:  # pragma: no cover - schema guard
                raise AssertionError("selected candidate lacks allocation rank")
            execution_input = execution_input_by_candidate[
                (state.state_id, candidate.depth_candidate_id)
            ]
            ordered_execution_inputs.append(execution_input)
            tasks.append(
                CompositionAttemptTask.from_content(
                    allocation_rank=candidate.allocation_rank,
                    depth_plan_id=depth_plan.depth_plan_id,
                    parent_state_id=state.state_id,
                    depth_candidate_id=candidate.depth_candidate_id,
                    component_spec_id=(
                        candidate.hypothesis.component.component_spec_id
                    ),
                    parent_model_resolution_ids=_parent_resolution_ids(
                        plan=depth_plan,
                        state=state,
                    ),
                    candidate_model_resolution_id=resolution.resolution_id,
                    diffraction_selection_id=(
                        diffraction_selection.diffraction_selection_id
                    ),
                    free_r_identity_id=free_r_identity.free_r_identity_id,
                    model_registry_id=depth_plan.model_registry_id,
                    execution_identity_id=execution_identity_id,
                    component_execution_input_id=(execution_input.execution_input_id),
                )
            )
        no_model_count = sum(
            candidate.hypothesis.disposition
            is ExpansionDisposition.UNSEARCHABLE_NO_MODEL
            for candidate in depth_plan.candidates
        )
        return CompositionAttemptInventory.from_content(
            status=_inventory_status(depth_plan),
            depth_plan=depth_plan,
            parent_states=parent_states,
            diffraction_selection=diffraction_selection,
            free_r_identity=free_r_identity,
            model_registry_id=depth_plan.model_registry_id,
            execution_identity_id=execution_identity_id,
            execution_inputs=tuple(ordered_execution_inputs),
            attempt_count=len(tasks),
            unsearchable_no_model_count=no_model_count,
            attempts=tuple(tasks),
        )
    except ValidationError as error:
        raise CompositionAttemptInventoryError(
            "composition attempt inventory failed its complete-item contract"
        ) from error


def load_composition_attempt_inventory(path: Path) -> CompositionAttemptInventory:
    """Load and revalidate one strict content-addressed inventory document."""

    try:
        return CompositionAttemptInventory.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise CompositionAttemptInventoryError(
            f"invalid composition attempt inventory: {path}"
        ) from error


def write_composition_attempt_inventory(
    inventory: CompositionAttemptInventory,
    path: Path,
) -> Path:
    """Write one deterministic JSON inventory for Nextflow fan-out."""

    atomic_write_json(path, inventory.model_dump(mode="json"))
    return path


__all__ = [
    "CompositionAttemptInventoryError",
    "build_composition_attempt_inventory",
    "load_composition_attempt_inventory",
    "write_composition_attempt_inventory",
]
