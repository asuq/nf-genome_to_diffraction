"""Validation and mutation tests for the blocked B--F execution input."""

import json

import pytest
from pydantic import BaseModel, ValidationError

from genome_to_diffraction.schemas.v2 import (
    ComponentExpansionExecutionInput,
    ComponentExpansionScoreEvidence,
    ComponentIdentitySupport,
    ComponentPlacement,
    ComponentSpec,
    CompositionCandidateHypothesis,
    CompositionExpansionDepthCandidate,
    CompositionExpansionDepthParent,
    CompositionExpansionDepthPlan,
    CompositionState,
    CompositionSupportState,
    DiffractionSelection,
    DiffractionValueSource,
    ExpansionDisposition,
    FreeRConventionStatus,
    FreeRDistributionSummary,
    FreeRFlagCount,
    FreeRIdentity,
    PhaserPerPlacementInventory,
    PhaserPlacementArtifact,
    PhaserPlacementComponentGroup,
    RegistryModelResolution,
    RegistryModelResolutionScope,
    diffraction_dataset_id,
)
from genome_to_diffraction.schemas.v2.component_execution_input import (
    FixedComponentExecutionEvidence,
)
from genome_to_diffraction.status import ExecutionStatus


def _sha(index: int) -> str:
    return f"{index:064x}"


def _component(label: str, index: int, *, copies: int = 1) -> ComponentSpec:
    sequence_sha256 = _sha(index)
    return ComponentSpec.from_content(
        label=label,
        sequence_group_id=f"seq_{sequence_sha256}",
        sequence_sha256=sequence_sha256,
        model_id=f"model_{label.lower()}",
        model_sha256=_sha(10 + index),
        requested_copy_count=copies,
        sequence_mass_da=20_000.0 + index,
        mass_evidence_sha256=_sha(20 + index),
        model_evidence_sha256=_sha(30 + index),
    )


def _placement(component: ComponentSpec, index: int) -> ComponentPlacement:
    return ComponentPlacement.from_content(
        component_spec_id=component.component_spec_id,
        component_label=component.label,
        sequence_group_id=component.sequence_group_id,
        model_id=component.model_id,
        model_sha256=component.model_sha256,
        requested_copy_count=component.requested_copy_count,
        observed_copy_count=component.requested_copy_count,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        component_tfz=10.0 + index,
        incremental_llg=100.0 + index,
        packing_passed=True,
        coordinate_sha256=_sha(40 + index),
        identity_support=ComponentIdentitySupport.UNRESOLVED,
    )


def _resolution(
    *,
    registry_id: str,
    parent_state: CompositionState,
    component: ComponentSpec,
    scope: RegistryModelResolutionScope,
    candidate_rank: int | None,
    index: int,
) -> RegistryModelResolution:
    return RegistryModelResolution.from_content(
        model_registry_id=registry_id,
        scope=scope,
        parent_state_id=parent_state.state_id,
        parent_rank=1,
        candidate_rank=candidate_rank,
        component_spec_id=component.component_spec_id,
        requested_copy_count=component.requested_copy_count,
        sequence_group_id=component.sequence_group_id,
        sequence_sha256=component.sequence_sha256,
        model_id=component.model_id,
        model_sha256=component.model_sha256,
        requested_provider=("pdb" if candidate_rank is not None else None),
        requested_variant_type=(
            "experimental_cleaned_source_chain" if candidate_rank is not None else None
        ),
        registry_entry_sha256=_sha(70 + index),
        resolved_provider="pdb",
        resolved_variant_type="experimental_cleaned_source_chain",
    )


def _resolution_sort_key(
    resolution: RegistryModelResolution,
) -> tuple[int, int, int, str]:
    scope_rank = (
        0 if resolution.scope is RegistryModelResolutionScope.PARENT_COMPONENT else 1
    )
    return (
        resolution.parent_rank,
        scope_rank,
        resolution.candidate_rank or 0,
        resolution.component_spec_id,
    )


def _selection_and_free_r(
    *,
    crystal_id: str,
    mtz_sha256: str,
) -> tuple[DiffractionSelection, FreeRIdentity]:
    dataset_id = diffraction_dataset_id(
        crystal_id=crystal_id,
        mtz_sha256=mtz_sha256,
    )
    selection = DiffractionSelection.from_content(
        crystal_id=crystal_id,
        diffraction_dataset_id=dataset_id,
        mtz_sha256=mtz_sha256,
        preflight_id=f"preflight_{_sha(90)}",
        preflight_record_sha256=_sha(91),
        crystal_manifest_sha256=_sha(92),
        observation_dataset_id=1,
        observation_labels=("I", "SIGI"),
        observation_type="intensity",
        selected_space_group="P 1",
        resolution_low_a=50.0,
        resolution_high_a=2.0,
        observation_source=DiffractionValueSource.MTZ_PREFLIGHT_AUTOMATIC,
        space_group_source=DiffractionValueSource.MTZ_HEADER,
        resolution_low_source=DiffractionValueSource.MTZ_RESOLUTION_RANGE,
        resolution_high_source=DiffractionValueSource.MTZ_RESOLUTION_RANGE,
    )
    distribution = FreeRDistributionSummary(
        reflection_count=10,
        distinct_flag_values=2,
        flag_counts=(
            FreeRFlagCount(flag_value=0, reflection_count=9),
            FreeRFlagCount(flag_value=1, reflection_count=1),
        ),
    )
    free_r = FreeRIdentity.from_content(
        diffraction_selection_id=selection.diffraction_selection_id,
        diffraction_dataset_id=dataset_id,
        crystal_id=crystal_id,
        mtz_sha256=mtz_sha256,
        observation_dataset_id=1,
        free_r_dataset_id=1,
        free_r_label="FreeR_flag",
        distribution=distribution,
        hkl_set_sha256=_sha(93),
        hkl_to_flag_membership_sha256=_sha(94),
        convention_status=FreeRConventionStatus.UNRESOLVED,
    )
    return selection, free_r


def _execution_input() -> ComponentExpansionExecutionInput:
    crystal_id = "9ECN_contract"
    mtz_sha256 = _sha(1)
    selection, free_r = _selection_and_free_r(
        crystal_id=crystal_id,
        mtz_sha256=mtz_sha256,
    )
    component_a = _component("A", 2, copies=2)
    component_b = _component("B", 3, copies=2)
    component_c = _component("C", 4, copies=2)
    placement_a = _placement(component_a, 2)
    placement_b = _placement(component_b, 3)
    parent_state = CompositionState.from_content(
        crystal_id=crystal_id,
        diffraction_dataset_id=selection.diffraction_dataset_id,
        diffraction_sha256=mtz_sha256,
        parent_state_id=f"compstate_{_sha(5)}",
        depth=2,
        components=(component_a, component_b),
        placements=(placement_a, placement_b),
        combined_coordinate_sha256=_sha(50),
        physical_mass_lower_da=100_000.0,
        physical_mass_upper_da=130_000.0,
        support_state=CompositionSupportState.PACKED,
    )
    candidate_hypothesis = CompositionCandidateHypothesis.from_content(
        component=component_c,
        rank=1,
        disposition=ExpansionDisposition.SELECTED,
        disposition_reason="highest deterministic rank within shared depth budget",
        physical_assessed=True,
        physical_possible=True,
        model_available=True,
    )
    selected_candidate = CompositionExpansionDepthCandidate.from_content(
        parent_state_id=parent_state.state_id,
        parent_rank=1,
        hypothesis=candidate_hypothesis,
        allocation_rank=1,
    )
    registry_id = f"allmodelreg_{_sha(60)}"
    resolution_a = _resolution(
        registry_id=registry_id,
        parent_state=parent_state,
        component=component_a,
        scope=RegistryModelResolutionScope.PARENT_COMPONENT,
        candidate_rank=None,
        index=1,
    )
    resolution_b = _resolution(
        registry_id=registry_id,
        parent_state=parent_state,
        component=component_b,
        scope=RegistryModelResolutionScope.PARENT_COMPONENT,
        candidate_rank=None,
        index=2,
    )
    resolution_c = _resolution(
        registry_id=registry_id,
        parent_state=parent_state,
        component=component_c,
        scope=RegistryModelResolutionScope.CANDIDATE_COPY,
        candidate_rank=1,
        index=3,
    )
    resolutions = tuple(
        sorted(
            (resolution_a, resolution_b, resolution_c),
            key=_resolution_sort_key,
        )
    )
    depth_parent = CompositionExpansionDepthParent.from_content(
        parent_state_id=parent_state.state_id,
        parent_rank=1,
        parent_component_labels=("A", "B"),
        parent_sequence_group_ids=(
            component_a.sequence_group_id,
            component_b.sequence_group_id,
        ),
    )
    depth_plan = CompositionExpansionDepthPlan.from_content(
        crystal_id=crystal_id,
        diffraction_dataset_id=selection.diffraction_dataset_id,
        parent_depth=2,
        target_depth=3,
        parents=(depth_parent,),
        maximum_component_depth=6,
        beam_width=3,
        per_depth_attempt_budget=25,
        global_attempt_budget=100,
        global_attempts_used_before=8,
        ranking_policy_version="phase3-round-robin-v1",
        model_registry_id=registry_id,
        model_resolutions=resolutions,
        candidate_count=1,
        physical_hypothesis_count=1,
        selected_attempt_count=1,
        deferred_candidate_count=0,
        unsearchable_candidate_count=0,
        candidates=(selected_candidate,),
    )

    fixed_a = FixedComponentExecutionEvidence.from_content(
        parent_state_id=parent_state.state_id,
        component_spec_id=component_a.component_spec_id,
        placement_id=placement_a.placement_id,
        source_parent_combined_coordinate_sha256=(
            parent_state.combined_coordinate_sha256
        ),
        fixed_coordinate_sha256=_sha(80),
        coordinate_derivation_evidence_sha256=_sha(81),
        phaser_identity_fraction=0.35,
        model_uncertainty_source="registered homologue sequence identity",
        model_uncertainty_evidence_sha256=component_a.model_evidence_sha256,
    )
    fixed_b = FixedComponentExecutionEvidence.from_content(
        parent_state_id=parent_state.state_id,
        component_spec_id=component_b.component_spec_id,
        placement_id=placement_b.placement_id,
        source_parent_combined_coordinate_sha256=(
            parent_state.combined_coordinate_sha256
        ),
        fixed_coordinate_sha256=_sha(82),
        coordinate_derivation_evidence_sha256=_sha(83),
        phaser_identity_fraction=0.82,
        model_uncertainty_source="exact predicted-model identity",
        model_uncertainty_evidence_sha256=component_b.model_evidence_sha256,
    )
    return ComponentExpansionExecutionInput.from_content(
        depth_plan_id=depth_plan.depth_plan_id,
        selected_candidate=selected_candidate,
        parent_state=parent_state,
        fixed_components=(fixed_a, fixed_b),
        candidate_model_resolution=resolution_c,
        candidate_phaser_identity_fraction=0.71,
        candidate_model_uncertainty_source=("registered homologue sequence identity"),
        candidate_model_uncertainty_evidence_sha256=(component_c.model_evidence_sha256),
        diffraction_selection=selection,
        free_r_identity=free_r,
        parent_combined_llg=420.5,
        parent_score_evidence_sha256=_sha(95),
    )


def _replace_content(
    model: BaseModel,
    identity_field: str,
    **changes: object,
) -> dict[str, object]:
    values = model.model_dump(mode="python", exclude={identity_field})
    values.update(changes)
    return values


def _placement_inventory(
    execution_input: ComponentExpansionExecutionInput,
) -> PhaserPerPlacementInventory:
    components = (
        *execution_input.parent_state.components,
        execution_input.selected_candidate.hypothesis.component,
    )
    groups: list[PhaserPlacementComponentGroup] = []
    placements: list[PhaserPlacementArtifact] = []
    next_chain = 0
    for ordinal, component in enumerate(components, start=1):
        chains = tuple(
            chr(ord("A") + next_chain + index)
            for index in range(component.requested_copy_count)
        )
        next_chain += component.requested_copy_count
        group = PhaserPlacementComponentGroup.from_content(
            component_label=component.label,
            ensemble_id=f"ensemble_{component.label}",
            expected_copy_count=component.requested_copy_count,
            observed_copy_count=component.requested_copy_count,
            placement_ordinals=(ordinal,),
            combined_chain_ids=chains,
            source_model_sha256=component.model_sha256,
            source_model_polymer_sha256=_sha(500 + ordinal),
            coordinate_path=f"component_{component.label}.pdb",
            coordinate_sha256=_sha(510 + ordinal),
            atom_count=component.requested_copy_count * 10,
        )
        groups.append(group)
        placements.append(
            PhaserPlacementArtifact.from_content(
                solution_number=1,
                placement_ordinal=ordinal,
                ensemble_id=group.ensemble_id,
                component_label=group.component_label,
                solu_6dim_line_sha256=_sha(520 + ordinal),
                coordinate_path=group.coordinate_path,
                coordinate_sha256=group.coordinate_sha256,
            )
        )
    atom_count = sum(group.atom_count for group in groups)
    return PhaserPerPlacementInventory.from_content(
        adapter_version="phaser-component-coordinate-inventory-v2",
        crystal_id=execution_input.parent_state.crystal_id,
        search_id="candidate_component_search",
        phaser_version="2.8.3",
        solution_number=1,
        command_record_sha256=_sha(530),
        result_record_sha256=_sha(531),
        solution_file_path="PHASER.sol",
        solution_file_sha256=_sha(532),
        combined_coordinate_path="PHASER.1.pdb",
        combined_coordinate_sha256=_sha(533),
        output_command_binding=(
            "phaser.keywords.general.xyzout=True;"
            "phaser.keywords.general.xyzout_ensemble=True;"
            "phaser.keywords.general.keywords=True"
        ),
        placements=tuple(placements),
        component_groups=tuple(groups),
        combined_atom_count=atom_count,
        recombined_atom_count=atom_count,
        recombined_atom_sha256=_sha(534),
        ordinal_mapping_status="verified_exact_sol_to_model_bound_chains",
        recombination_status="verified_exact_combined_atom_partition",
    )


def test_expansion_scores_keep_candidate_tfz_and_incremental_llg_separate() -> None:
    execution_input = _execution_input()
    inventory = _placement_inventory(execution_input)

    evidence = ComponentExpansionScoreEvidence.from_observed(
        execution_input=execution_input,
        placement_inventory=inventory,
        score_ensemble_id="ensemble_C",
        combined_llg=747.549,
        component_tfz=5.1,
        packing_passed=True,
    )

    assert evidence.parent_combined_llg == pytest.approx(420.5)
    assert evidence.combined_llg == pytest.approx(747.549)
    assert evidence.incremental_llg == pytest.approx(327.049)
    assert evidence.component_tfz == pytest.approx(5.1)
    assert evidence.placement.component_label == "C"
    assert evidence.placement.incremental_llg == pytest.approx(327.049)
    assert evidence.placement.component_tfz == pytest.approx(5.1)
    assert evidence.placement.identity_support is ComponentIdentitySupport.UNRESOLVED


def test_expansion_scores_reject_parent_ensemble_and_combined_llg_substitution() -> (
    None
):
    execution_input = _execution_input()
    inventory = _placement_inventory(execution_input)

    with pytest.raises(ValidationError, match="candidate ensemble"):
        ComponentExpansionScoreEvidence.from_observed(
            execution_input=execution_input,
            placement_inventory=inventory,
            score_ensemble_id="ensemble_B",
            combined_llg=747.549,
            component_tfz=5.1,
            packing_passed=True,
        )

    evidence = ComponentExpansionScoreEvidence.from_observed(
        execution_input=execution_input,
        placement_inventory=inventory,
        score_ensemble_id="ensemble_C",
        combined_llg=747.549,
        component_tfz=5.1,
        packing_passed=True,
    )
    with pytest.raises(ValidationError, match="combined minus parent"):
        ComponentExpansionScoreEvidence.from_content(
            **_replace_content(
                evidence,
                "score_evidence_id",
                incremental_llg=evidence.combined_llg,
            )
        )
    with pytest.raises(ValidationError, match="fixed parent LLG"):
        ComponentExpansionScoreEvidence.from_content(
            **_replace_content(
                evidence,
                "score_evidence_id",
                parent_combined_llg=evidence.parent_combined_llg + 1,
            )
        )


@pytest.mark.parametrize("mutation", ("crystal", "model", "result", "identity"))
def test_expansion_scores_reject_cross_bound_or_promoted_candidate_evidence(
    mutation: str,
) -> None:
    execution_input = _execution_input()
    inventory = _placement_inventory(execution_input)
    evidence = ComponentExpansionScoreEvidence.from_observed(
        execution_input=execution_input,
        placement_inventory=inventory,
        score_ensemble_id="ensemble_C",
        combined_llg=747.549,
        component_tfz=5.1,
        packing_passed=True,
    )
    if mutation == "crystal":
        changed_inventory = PhaserPerPlacementInventory.from_content(
            **_replace_content(inventory, "inventory_id", crystal_id="another_crystal")
        )
        changes: dict[str, object] = {"placement_inventory": changed_inventory}
        error = "another crystal"
    elif mutation == "model":
        changed_group = PhaserPlacementComponentGroup.from_content(
            **_replace_content(
                inventory.component_groups[-1],
                "component_group_id",
                source_model_sha256=_sha(999),
            )
        )
        changed_inventory = PhaserPerPlacementInventory.from_content(
            **_replace_content(
                inventory,
                "inventory_id",
                component_groups=(*inventory.component_groups[:-1], changed_group),
            )
        )
        changes = {"placement_inventory": changed_inventory}
        error = "component model or copies"
    elif mutation == "result":
        changes = {"result_record_sha256": _sha(999)}
        error = "result record checksum"
    else:
        with pytest.raises(
            ValidationError,
            match="owned map-supported sequence review",
        ):
            ComponentPlacement.from_content(
                **_replace_content(
                    evidence.placement,
                    "placement_id",
                    identity_support=ComponentIdentitySupport.EXACT_SEQUENCE,
                )
            )
        return

    with pytest.raises(ValidationError, match=error):
        ComponentExpansionScoreEvidence.from_content(
            **_replace_content(evidence, "score_evidence_id", **changes)
        )


def test_expansion_score_identity_changes_with_the_component_metrics() -> None:
    execution_input = _execution_input()
    inventory = _placement_inventory(execution_input)
    baseline = ComponentExpansionScoreEvidence.from_observed(
        execution_input=execution_input,
        placement_inventory=inventory,
        score_ensemble_id="ensemble_C",
        combined_llg=747.549,
        component_tfz=5.1,
        packing_passed=True,
    )
    changed = ComponentExpansionScoreEvidence.from_observed(
        execution_input=execution_input,
        placement_inventory=inventory,
        score_ensemble_id="ensemble_C",
        combined_llg=748.549,
        component_tfz=5.2,
        packing_passed=True,
    )

    assert baseline.score_evidence_id != changed.score_evidence_id
    assert changed.incremental_llg == pytest.approx(328.049)


def test_execution_input_preserves_distinct_parent_uncertainties_and_all_ids() -> None:
    execution_input = _execution_input()

    assert execution_input.parent_state.depth == 2
    assert execution_input.selected_candidate.hypothesis.component.label == "C"
    assert (
        execution_input.selected_candidate.hypothesis.component.requested_copy_count
        == 2
    )
    assert tuple(
        item.phaser_identity_fraction for item in execution_input.fixed_components
    ) == (0.35, 0.82)
    assert execution_input.candidate_phaser_identity_fraction == 0.71
    assert (
        execution_input.free_r_identity.diffraction_selection_id
        == execution_input.diffraction_selection.diffraction_selection_id
    )
    assert execution_input.command_boundary.endswith("syntax_not_qualified")


def test_execution_input_content_id_changes_with_parent_uncertainty_or_llg() -> None:
    execution_input = _execution_input()
    fixed_a, fixed_b = execution_input.fixed_components
    changed_fixed_a = FixedComponentExecutionEvidence.from_content(
        **_replace_content(
            fixed_a,
            "fixed_component_evidence_id",
            phaser_identity_fraction=0.36,
        )
    )
    changed_uncertainty = ComponentExpansionExecutionInput.from_content(
        **_replace_content(
            execution_input,
            "execution_input_id",
            fixed_components=(changed_fixed_a, fixed_b),
        )
    )
    changed_llg = ComponentExpansionExecutionInput.from_content(
        **_replace_content(
            execution_input,
            "execution_input_id",
            parent_combined_llg=421.5,
        )
    )

    assert changed_uncertainty.execution_input_id != execution_input.execution_input_id
    assert changed_llg.execution_input_id != execution_input.execution_input_id

    stale = json.loads(execution_input.model_dump_json())
    stale["parent_combined_llg"] = 421.5
    with pytest.raises(ValidationError, match="execution_input_id"):
        ComponentExpansionExecutionInput.model_validate(stale)


def test_execution_input_rejects_missing_reordered_or_collapsed_fixed_evidence() -> (
    None
):
    execution_input = _execution_input()
    fixed_a, fixed_b = execution_input.fixed_components

    with pytest.raises(ValidationError, match="cover every parent component"):
        ComponentExpansionExecutionInput.from_content(
            **_replace_content(
                execution_input,
                "execution_input_id",
                fixed_components=(fixed_a,),
            )
        )
    with pytest.raises(ValidationError, match="differs from its parent component"):
        ComponentExpansionExecutionInput.from_content(
            **_replace_content(
                execution_input,
                "execution_input_id",
                fixed_components=(fixed_b, fixed_a),
            )
        )

    collapsed_b = FixedComponentExecutionEvidence.from_content(
        **_replace_content(
            fixed_b,
            "fixed_component_evidence_id",
            fixed_coordinate_sha256=fixed_a.fixed_coordinate_sha256,
        )
    )
    with pytest.raises(ValidationError, match="collapsed coordinate"):
        ComponentExpansionExecutionInput.from_content(
            **_replace_content(
                execution_input,
                "execution_input_id",
                fixed_components=(fixed_a, collapsed_b),
            )
        )

    combined_b = FixedComponentExecutionEvidence.from_content(
        **_replace_content(
            fixed_b,
            "fixed_component_evidence_id",
            fixed_coordinate_sha256=(
                execution_input.parent_state.combined_coordinate_sha256
            ),
        )
    )
    with pytest.raises(ValidationError, match="reuse combined coordinates"):
        ComponentExpansionExecutionInput.from_content(
            **_replace_content(
                execution_input,
                "execution_input_id",
                fixed_components=(fixed_a, combined_b),
            )
        )


def test_execution_input_rejects_non_candidate_or_mutated_model_resolution() -> None:
    execution_input = _execution_input()
    candidate = execution_input.selected_candidate.hypothesis.component
    parent_resolution = RegistryModelResolution.from_content(
        model_registry_id=execution_input.candidate_model_resolution.model_registry_id,
        scope=RegistryModelResolutionScope.PARENT_COMPONENT,
        parent_state_id=execution_input.parent_state.state_id,
        parent_rank=1,
        candidate_rank=None,
        component_spec_id=candidate.component_spec_id,
        requested_copy_count=candidate.requested_copy_count,
        sequence_group_id=candidate.sequence_group_id,
        sequence_sha256=candidate.sequence_sha256,
        model_id=candidate.model_id,
        model_sha256=candidate.model_sha256,
        registry_entry_sha256=_sha(75),
        resolved_provider="pdb",
        resolved_variant_type="experimental_cleaned_source_chain",
    )
    with pytest.raises(ValidationError, match="differs from selected copy"):
        ComponentExpansionExecutionInput.from_content(
            **_replace_content(
                execution_input,
                "execution_input_id",
                candidate_model_resolution=parent_resolution,
            )
        )

    mutated_resolution = RegistryModelResolution.from_content(
        **_replace_content(
            execution_input.candidate_model_resolution,
            "resolution_id",
            model_sha256=_sha(99),
        )
    )
    with pytest.raises(ValidationError, match="differs from selected copy"):
        ComponentExpansionExecutionInput.from_content(
            **_replace_content(
                execution_input,
                "execution_input_id",
                candidate_model_resolution=mutated_resolution,
            )
        )


def test_execution_input_rejects_free_r_selection_mismatch() -> None:
    execution_input = _execution_input()
    free_r = execution_input.free_r_identity
    mismatched_free_r = FreeRIdentity.from_content(
        **_replace_content(
            free_r,
            "free_r_identity_id",
            diffraction_selection_id=f"diffsel_{_sha(100)}",
        )
    )

    with pytest.raises(ValidationError, match="Free-R identity differs"):
        ComponentExpansionExecutionInput.from_content(
            **_replace_content(
                execution_input,
                "execution_input_id",
                free_r_identity=mismatched_free_r,
            )
        )
