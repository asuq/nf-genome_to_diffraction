"""Focused tests for the Phase III complete composition-attempt inventory."""

import json

import pytest
from pydantic import ValidationError

from genome_to_diffraction.execution import (
    CompositionAttemptInventoryError,
    build_composition_attempt_inventory,
    load_composition_attempt_inventory,
    write_composition_attempt_inventory,
)
from genome_to_diffraction.ranking.composition import (
    ComponentExpansionInput,
    CompositionExpansionOutput,
    CompositionExpansionRequest,
    ParentExpansionInput,
    build_composition_expansion_plan,
)
from genome_to_diffraction.schemas.v2 import (
    ComponentExpansionExecutionInput,
    ComponentIdentitySupport,
    ComponentPlacement,
    ComponentSpec,
    CompositionAttemptInventory,
    CompositionAttemptInventoryStatus,
    CompositionState,
    CompositionSupportState,
    DiffractionSelection,
    DiffractionValueSource,
    ExpansionDisposition,
    FreeRConventionStatus,
    FreeRDistributionSummary,
    FreeRFlagCount,
    FreeRIdentity,
    ModelUnavailableReason,
    RegistryModelResolution,
    RegistryModelResolutionScope,
    diffraction_dataset_id,
)
from genome_to_diffraction.schemas.v2.component_execution_input import (
    FixedComponentExecutionEvidence,
)
from genome_to_diffraction.status import ExecutionStatus

CRYSTAL_ID = "composition_fanout_crystal"
MTZ_SHA256 = f"{501:064x}"
DIFFRACTION_DATASET_ID = diffraction_dataset_id(
    crystal_id=CRYSTAL_ID,
    mtz_sha256=MTZ_SHA256,
)
MODEL_REGISTRY_ID = f"allmodelreg_{502:064x}"
EXECUTION_IDENTITY_ID = f"phase3exec_{503:064x}"


def _sha(index: int) -> str:
    return f"{index:064x}"


def _component_specs(
    *,
    label: str,
    sequence_index: int,
    model_index: int,
) -> tuple[ComponentSpec, ...]:
    sequence_sha256 = _sha(sequence_index)
    return tuple(
        ComponentSpec.from_content(
            label=label,
            sequence_group_id=f"seq_{sequence_sha256}",
            sequence_sha256=sequence_sha256,
            model_id=f"model_{model_index}",
            model_sha256=_sha(model_index),
            requested_copy_count=copy_count,
            sequence_mass_da=20_000.0 + sequence_index,
            mass_evidence_sha256=_sha(600 + sequence_index),
            model_evidence_sha256=_sha(700 + model_index),
        )
        for copy_count in range(1, 5)
    )


def _available_resolution(
    *,
    scope: RegistryModelResolutionScope,
    parent_state_id: str,
    parent_rank: int,
    component: ComponentSpec,
    candidate_rank: int | None = None,
) -> RegistryModelResolution:
    return RegistryModelResolution.from_content(
        model_registry_id=MODEL_REGISTRY_ID,
        scope=scope,
        parent_state_id=parent_state_id,
        parent_rank=parent_rank,
        candidate_rank=candidate_rank,
        component_spec_id=component.component_spec_id,
        requested_copy_count=component.requested_copy_count,
        sequence_group_id=component.sequence_group_id,
        sequence_sha256=component.sequence_sha256,
        model_id=component.model_id,
        model_sha256=component.model_sha256,
        registry_entry_sha256=_sha(800 + parent_rank + (candidate_rank or 0)),
        resolved_provider="synthetic",
        resolved_variant_type="processed",
    )


def _parent(rank: int) -> ParentExpansionInput:
    component = _component_specs(
        label="A",
        sequence_index=1,
        model_index=10 + rank,
    )[rank - 1]
    placement = ComponentPlacement.from_content(
        component_spec_id=component.component_spec_id,
        component_label=component.label,
        sequence_group_id=component.sequence_group_id,
        model_id=component.model_id,
        model_sha256=component.model_sha256,
        requested_copy_count=component.requested_copy_count,
        observed_copy_count=component.requested_copy_count,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        component_tfz=10.0 + rank,
        incremental_llg=100.0 + rank,
        packing_passed=True,
        coordinate_sha256=_sha(900 + rank),
        identity_support=ComponentIdentitySupport.SEQUENCE_EQUIVALENCE_GROUP,
    )
    state = CompositionState.from_content(
        crystal_id=CRYSTAL_ID,
        diffraction_dataset_id=DIFFRACTION_DATASET_ID,
        diffraction_sha256=MTZ_SHA256,
        parent_state_id=None,
        depth=1,
        components=(component,),
        placements=(placement,),
        combined_coordinate_sha256=_sha(900 + rank),
        physical_mass_lower_da=10_000.0,
        physical_mass_upper_da=100_000.0,
        support_state=CompositionSupportState.PACKED,
    )
    resolution = _available_resolution(
        scope=RegistryModelResolutionScope.PARENT_COMPONENT,
        parent_state_id=state.state_id,
        parent_rank=rank,
        component=component,
    )
    return ParentExpansionInput(
        parent_rank=rank,
        state=state,
        model_resolutions=(resolution,),
    )


def _candidate(
    *,
    parent: ParentExpansionInput,
    rank: int,
    sequence_index: int,
    eligible: tuple[int, ...] = (1, 2, 3, 4),
    model_available: bool = True,
) -> ComponentExpansionInput:
    components = _component_specs(
        label="B",
        sequence_index=sequence_index,
        model_index=100 + sequence_index,
    )
    resolutions = tuple(
        _available_resolution(
            scope=RegistryModelResolutionScope.CANDIDATE_COPY,
            parent_state_id=parent.state.state_id,
            parent_rank=parent.parent_rank,
            candidate_rank=rank,
            component=component,
        )
        if model_available
        else RegistryModelResolution.from_content(
            model_registry_id=MODEL_REGISTRY_ID,
            scope=RegistryModelResolutionScope.CANDIDATE_COPY,
            parent_state_id=parent.state.state_id,
            parent_rank=parent.parent_rank,
            candidate_rank=rank,
            component_spec_id=component.component_spec_id,
            requested_copy_count=component.requested_copy_count,
            sequence_group_id=component.sequence_group_id,
            sequence_sha256=component.sequence_sha256,
            model_id=component.model_id,
            model_sha256=component.model_sha256,
            unavailable_reason=ModelUnavailableReason.NO_ELIGIBLE_MODEL,
        )
        for component in components
    )
    return ComponentExpansionInput(
        parent_state_id=parent.state.state_id,
        candidate_rank=rank,
        component_specs=components,
        physically_eligible_copy_counts=eligible,
        model_available=model_available,
        model_resolutions=resolutions,
    )


def _diffraction_selection() -> DiffractionSelection:
    return DiffractionSelection.from_content(
        crystal_id=CRYSTAL_ID,
        diffraction_dataset_id=DIFFRACTION_DATASET_ID,
        mtz_sha256=MTZ_SHA256,
        preflight_id="preflight_composition_fanout",
        preflight_record_sha256=_sha(1001),
        crystal_manifest_sha256=_sha(1002),
        observation_dataset_id=1,
        observation_labels=("F", "SIGF"),
        observation_type="amplitude",
        selected_space_group="P 21 21 21",
        resolution_low_a=50.0,
        resolution_high_a=2.0,
        observation_source=DiffractionValueSource.MTZ_PREFLIGHT_AUTOMATIC,
        space_group_source=DiffractionValueSource.MTZ_HEADER,
        resolution_low_source=DiffractionValueSource.MTZ_RESOLUTION_RANGE,
        resolution_high_source=DiffractionValueSource.MTZ_RESOLUTION_RANGE,
    )


def _free_r_identity(selection: DiffractionSelection) -> FreeRIdentity:
    return FreeRIdentity.from_content(
        diffraction_selection_id=selection.diffraction_selection_id,
        diffraction_dataset_id=selection.diffraction_dataset_id,
        crystal_id=selection.crystal_id,
        mtz_sha256=selection.mtz_sha256,
        observation_dataset_id=selection.observation_dataset_id,
        free_r_dataset_id=selection.observation_dataset_id,
        free_r_label="FreeR_flag",
        distribution=FreeRDistributionSummary(
            reflection_count=100,
            distinct_flag_values=2,
            flag_counts=(
                FreeRFlagCount(flag_value=0, reflection_count=95),
                FreeRFlagCount(flag_value=1, reflection_count=5),
            ),
        ),
        hkl_set_sha256=_sha(1003),
        hkl_to_flag_membership_sha256=_sha(1004),
        convention_status=FreeRConventionStatus.UNRESOLVED,
    )


def _inventory(
    *,
    parents: tuple[ParentExpansionInput, ...],
    candidates: tuple[ComponentExpansionInput, ...],
) -> tuple[CompositionExpansionOutput, CompositionAttemptInventory]:
    output = build_composition_expansion_plan(
        CompositionExpansionRequest(
            parents=parents,
            candidates=candidates,
            model_registry_id=MODEL_REGISTRY_ID,
        )
    )
    selection = _diffraction_selection()
    free_r = _free_r_identity(selection)
    execution_inputs = _execution_inputs(
        output=output,
        parents=parents,
        selection=selection,
        free_r=free_r,
    )
    inventory = build_composition_attempt_inventory(
        depth_plan=output.depth_plan,
        planned_attempts=output.selected_attempts,
        parent_states=tuple(parent.state for parent in parents),
        diffraction_selection=selection,
        free_r_identity=free_r,
        execution_identity_id=EXECUTION_IDENTITY_ID,
        execution_inputs=execution_inputs,
    )
    return output, inventory


def _execution_inputs(
    *,
    output: CompositionExpansionOutput,
    parents: tuple[ParentExpansionInput, ...],
    selection: DiffractionSelection,
    free_r: FreeRIdentity,
) -> tuple[ComponentExpansionExecutionInput, ...]:
    state_by_id = {parent.state.state_id: parent.state for parent in parents}
    candidate_by_id = {
        candidate.depth_candidate_id: candidate
        for candidate in output.depth_plan.candidates
    }
    resolution_by_key = {
        (resolution.parent_state_id, resolution.component_spec_id): resolution
        for resolution in output.depth_plan.model_resolutions
    }
    inputs: list[ComponentExpansionExecutionInput] = []
    for attempt in output.selected_attempts:
        state = state_by_id[attempt.parent_state_id]
        candidate = candidate_by_id[attempt.depth_candidate_id]
        fixed = tuple(
            FixedComponentExecutionEvidence.from_content(
                parent_state_id=state.state_id,
                component_spec_id=component.component_spec_id,
                placement_id=placement.placement_id,
                fixed_coordinate_sha256=placement.coordinate_sha256,
                source_parent_combined_coordinate_sha256=(
                    state.combined_coordinate_sha256
                ),
                coordinate_derivation_evidence_sha256=_sha(1100 + index),
                phaser_identity_fraction=0.35 + index / 10,
                model_uncertainty_source="synthetic reviewed model identity",
                model_uncertainty_evidence_sha256=(component.model_evidence_sha256),
            )
            for index, (component, placement) in enumerate(
                zip(state.components, state.placements, strict=True)
            )
        )
        component = candidate.hypothesis.component
        resolution = resolution_by_key[(state.state_id, component.component_spec_id)]
        inputs.append(
            ComponentExpansionExecutionInput.from_content(
                depth_plan_id=output.depth_plan.depth_plan_id,
                selected_candidate=candidate,
                parent_state=state,
                fixed_components=fixed,
                candidate_model_resolution=resolution,
                candidate_phaser_identity_fraction=0.8,
                candidate_model_uncertainty_source=(
                    "synthetic candidate model identity"
                ),
                candidate_model_uncertainty_evidence_sha256=(
                    component.model_evidence_sha256
                ),
                diffraction_selection=selection,
                free_r_identity=free_r,
                parent_combined_llg=1000.0,
                parent_score_evidence_sha256=_sha(1200 + attempt.allocation_rank),
            )
        )
    return tuple(inputs)


def test_shared_25_attempt_budget_becomes_exact_complete_items() -> None:
    parents = tuple(_parent(rank) for rank in range(1, 4))
    candidates = tuple(
        _candidate(
            parent=parent,
            rank=rank,
            sequence_index=parent.parent_rank * 10 + rank,
        )
        for parent in parents
        for rank in range(1, 4)
    )

    output, inventory = _inventory(parents=parents, candidates=candidates)
    repeated = build_composition_attempt_inventory(
        depth_plan=output.depth_plan,
        planned_attempts=output.selected_attempts,
        parent_states=tuple(parent.state for parent in parents),
        diffraction_selection=inventory.diffraction_selection,
        free_r_identity=inventory.free_r_identity,
        execution_identity_id=EXECUTION_IDENTITY_ID,
        execution_inputs=inventory.execution_inputs,
    )

    assert inventory == repeated
    assert output.depth_plan.candidate_count == 36
    assert output.depth_plan.selected_attempt_count == 25
    assert inventory.status is CompositionAttemptInventoryStatus.READY
    assert inventory.attempt_count == 25
    assert tuple(task.allocation_rank for task in inventory.attempts) == tuple(
        range(1, 26)
    )
    assert len({task.attempt_id for task in inventory.attempts}) == 25
    assert len(inventory.execution_inputs) == 25
    assert {task.component_execution_input_id for task in inventory.attempts} == {
        item.execution_input_id for item in inventory.execution_inputs
    }
    assert {task.parent_state_id for task in inventory.attempts} == {
        parent.state.state_id for parent in parents
    }
    assert all(
        task.depth_plan_id == output.depth_plan.depth_plan_id
        and task.diffraction_selection_id
        == inventory.diffraction_selection.diffraction_selection_id
        and task.free_r_identity_id == inventory.free_r_identity.free_r_identity_id
        and task.model_registry_id == MODEL_REGISTRY_ID
        and task.execution_identity_id == EXECUTION_IDENTITY_ID
        for task in inventory.attempts
    )


def test_planned_attempt_inventory_cannot_be_omitted_or_reordered() -> None:
    parent = _parent(1)
    output = build_composition_expansion_plan(
        CompositionExpansionRequest(
            parents=(parent,),
            candidates=(_candidate(parent=parent, rank=1, sequence_index=2),),
            model_registry_id=MODEL_REGISTRY_ID,
        )
    )
    selection = _diffraction_selection()
    common = {
        "depth_plan": output.depth_plan,
        "parent_states": (parent.state,),
        "diffraction_selection": selection,
        "free_r_identity": _free_r_identity(selection),
        "execution_identity_id": EXECUTION_IDENTITY_ID,
        "execution_inputs": _execution_inputs(
            output=output,
            parents=(parent,),
            selection=selection,
            free_r=_free_r_identity(selection),
        ),
    }

    with pytest.raises(CompositionAttemptInventoryError, match="exactly match"):
        build_composition_attempt_inventory(
            planned_attempts=output.selected_attempts[:-1],
            **common,
        )
    with pytest.raises(CompositionAttemptInventoryError, match="exactly match"):
        build_composition_attempt_inventory(
            planned_attempts=tuple(reversed(output.selected_attempts)),
            **common,
        )


def test_no_model_and_other_empty_paths_remain_typed() -> None:
    parent = _parent(1)
    no_model_output, no_model = _inventory(
        parents=(parent,),
        candidates=(
            _candidate(
                parent=parent,
                rank=1,
                sequence_index=2,
                model_available=False,
            ),
        ),
    )
    impossible_output, impossible = _inventory(
        parents=(parent,),
        candidates=(
            _candidate(
                parent=parent,
                rank=1,
                sequence_index=3,
                eligible=(),
            ),
        ),
    )

    assert no_model_output.selected_attempts == ()
    assert no_model.status is CompositionAttemptInventoryStatus.EMPTY_NO_MODEL
    assert no_model.attempt_count == 0
    assert no_model.unsearchable_no_model_count == 4
    assert no_model.attempts == ()
    assert {
        candidate.hypothesis.disposition for candidate in no_model.depth_plan.candidates
    } == {ExpansionDisposition.UNSEARCHABLE_NO_MODEL}
    assert impossible_output.selected_attempts == ()
    assert (
        impossible.status
        is CompositionAttemptInventoryStatus.EMPTY_NO_SELECTED_ATTEMPTS
    )
    assert impossible.unsearchable_no_model_count == 0
    assert impossible.attempts == ()


def test_attempt_and_inventory_content_mutation_fails_closed(tmp_path) -> None:
    parent = _parent(1)
    _, inventory = _inventory(
        parents=(parent,),
        candidates=(_candidate(parent=parent, rank=1, sequence_index=2),),
    )
    path = write_composition_attempt_inventory(
        inventory,
        tmp_path / "composition_attempt_inventory.json",
    )

    assert load_composition_attempt_inventory(path) == inventory
    first_bytes = path.read_bytes()
    write_composition_attempt_inventory(inventory, path)
    assert path.read_bytes() == first_bytes

    mutated = json.loads(path.read_text(encoding="utf-8"))
    mutated["attempts"][0]["execution_identity_id"] = f"phase3exec_{999:064x}"
    with pytest.raises(ValidationError, match="attempt_id"):
        CompositionAttemptInventory.model_validate(mutated)
    path.write_text(json.dumps(mutated), encoding="utf-8")
    with pytest.raises(CompositionAttemptInventoryError, match="invalid"):
        load_composition_attempt_inventory(path)
