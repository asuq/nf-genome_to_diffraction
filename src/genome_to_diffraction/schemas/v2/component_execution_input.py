"""Blocked execution input for one Phase III B--F component expansion.

The contract binds the minimum evidence needed to construct one fixed-partial
Phaser search without flattening a multi-component parent into one perfect
ensemble.  It does not construct or execute a command: retained repository
evidence qualifies one ``solution_at_origin = True`` ensemble, not several
independently uncertain fixed ensembles.  ``command_boundary`` keeps that
limitation machine-readable until exact official syntax and the installed
runtime are qualified.

Inputs are one selected depth candidate, its packed parent state, a
component-only fixed coordinate and original Phaser identity/error evidence for
each existing component, one available registry model resolution, the exact
diffraction and Free-R selections, and the parent LLG needed for an incremental
LLG.  Missing, collapsed, reordered, or cross-dataset evidence fails validation.
``execution_input_id`` covers the complete canonical payload and is the cache
identity.  Focused tests live in
``tests/unit/test_component_expansion_execution_input.py``.

``ComponentCoordinateDerivationBoundary`` separately checksum-binds retained
combined-coordinate evidence that lacks the exact Phaser ``.sol`` and native
per-placement PDBs.  It emits no coordinates or command and records the exact
future output-adapter requirement.  Its regressions live in
``tests/unit/test_component_coordinate_derivation_boundary.py``.

``ComponentExpansionScoreEvidence`` binds a verified component inventory to
one explicit candidate-ensemble TFZ, the fixed parent's retained combined LLG,
the new combined LLG, and their independently validated incremental delta.
Packing remains search evidence and never establishes component identity.
"""

import math
from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.schemas.base import NonEmptyString, PositiveInt, Sha256Hex
from genome_to_diffraction.schemas.v2.composition import (
    ComponentIdentitySupport,
    ComponentLabel,
    ComponentPlacement,
    ComponentPlacementIdentifier,
    ComponentSpecIdentifier,
    CompositionExpansionDepthCandidate,
    CompositionState,
    CompositionStateIdentifier,
    CompositionSupportState,
    ExpansionDepthPlanIdentifier,
    ExpansionDisposition,
    RegistryModelResolution,
    RegistryModelResolutionScope,
    _ContentAddressedContract,
)
from genome_to_diffraction.schemas.v2.diffraction import (
    DiffractionSelection,
    FreeRIdentity,
)
from genome_to_diffraction.schemas.v2.phaser_placements import (
    PhaserPerPlacementInventory,
)
from genome_to_diffraction.status import ExecutionStatus

FixedComponentExecutionEvidenceIdentifier = Annotated[
    str,
    Field(pattern=r"^fixedcompevidence_[a-f0-9]{64}$"),
]
ComponentExpansionExecutionInputIdentifier = Annotated[
    str,
    Field(pattern=r"^compexecinput_[a-f0-9]{64}$"),
]
ComponentCoordinateDerivationBoundaryIdentifier = Annotated[
    str,
    Field(pattern=r"^compcoordboundary_[a-f0-9]{64}$"),
]
ComponentExpansionScoreEvidenceIdentifier = Annotated[
    str,
    Field(pattern=r"^compscore_[a-f0-9]{64}$"),
]

_ORDERED_COMPONENT_LABELS = ("A", "B", "C", "D", "E", "F")
_EXECUTABLE_PARENT_STATES = {
    CompositionSupportState.PACKED,
    CompositionSupportState.REFINED,
    CompositionSupportState.REVIEW_SUPPORTED,
    CompositionSupportState.COMPOSITION_SUPPORTED,
}


class ComponentCoordinateDerivationGap(StrEnum):
    """Missing evidence that forbids component-coordinate derivation."""

    EXACT_SOLUTION_FILE = "exact_solution_file_not_retained"
    PER_PLACEMENT_COORDINATES = "per_solu_6dim_coordinates_not_retained"
    CHAIN_ENSEMBLE_ASSIGNMENT = "chain_to_ensemble_assignment_not_proven"
    FULL_PRECISION_TRANSFORMS = "full_precision_transforms_not_reconstructible"
    RECOMBINATION = "component_recombination_not_verifiable"


_REQUIRED_DERIVATION_GAPS = (
    ComponentCoordinateDerivationGap.EXACT_SOLUTION_FILE,
    ComponentCoordinateDerivationGap.PER_PLACEMENT_COORDINATES,
    ComponentCoordinateDerivationGap.CHAIN_ENSEMBLE_ASSIGNMENT,
    ComponentCoordinateDerivationGap.FULL_PRECISION_TRANSFORMS,
    ComponentCoordinateDerivationGap.RECOMBINATION,
)


class ComponentCoordinateDerivationBoundary(_ContentAddressedContract):
    """Checksum-bound refusal to derive component coordinates from combined PDBs.

    This record is emitted when retained Phaser evidence contains a combined parent
    PDB and summary/log evidence but lacks the exact ``.sol`` file and Phaser's
    documented per-``SOLU 6DIM`` coordinate outputs.  It carries no command and no
    derived coordinate checksum.  Therefore it cannot be supplied as
    :class:`FixedComponentExecutionEvidence`.

    A future real-runtime adapter must retain the exact ``.sol`` plus the files
    produced by ``XYZOUT ON ENSEMBLE ON``, bind each file ordinal to its documented
    ``SOLU 6DIM`` entry, checksum-group placements by component, and verify exact
    recombination against the combined parent before this boundary can be replaced.
    """

    _identity_field: ClassVar[str] = "derivation_boundary_id"
    _identity_prefix: ClassVar[str] = "compcoordboundary_"

    schema_version: Literal["2.0"]
    derivation_boundary_id: ComponentCoordinateDerivationBoundaryIdentifier
    crystal_id: NonEmptyString
    source_commit: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    combined_coordinate_sha256: Sha256Hex
    result_record_sha256: Sha256Hex
    command_record_sha256: Sha256Hex
    raw_log_sha256: Sha256Hex
    retained_artifact_inventory_sha256: Sha256Hex
    phaser_tool_version: NonEmptyString
    parent_component_labels: tuple[ComponentLabel, ...] = Field(
        min_length=2,
        max_length=5,
    )
    observed_copy_counts: tuple[PositiveInt, ...] = Field(
        min_length=2,
        max_length=5,
    )
    derivation_status: Literal[
        "blocked_missing_exact_sol_and_per_placement_coordinates"
    ] = "blocked_missing_exact_sol_and_per_placement_coordinates"
    exact_solution_file_sha256: None = None
    per_placement_coordinate_sha256s: tuple[Sha256Hex, ...] = ()
    derived_component_coordinate_sha256s: tuple[Sha256Hex, ...] = ()
    chain_to_ensemble_assignment_verified: Literal[False] = False
    full_precision_transforms_verified: Literal[False] = False
    recombination_verified: Literal[False] = False
    can_create_fixed_component_evidence: Literal[False] = False
    derivation_command: tuple[str, ...] = ()
    missing_evidence: tuple[ComponentCoordinateDerivationGap, ...] = (
        _REQUIRED_DERIVATION_GAPS
    )
    future_adapter_requirement: Literal[
        "retain_exact_sol_and_xyzout_ensemble_per_solu_6dim_pdbs_then_"
        "checksum_group_and_recombine"
    ] = (
        "retain_exact_sol_and_xyzout_ensemble_per_solu_6dim_pdbs_then_"
        "checksum_group_and_recombine"
    )

    @model_validator(mode="after")
    def _validate_blocked_derivation(self) -> Self:
        labels = self.parent_component_labels
        if labels != _ORDERED_COMPONENT_LABELS[: len(labels)]:
            raise ValueError("parent components are not the ordered A--F prefix")
        if len(self.observed_copy_counts) != len(labels):
            raise ValueError("copy counts do not cover every parent component")
        if any(count > 4 for count in self.observed_copy_counts):
            raise ValueError("parent component copy count exceeds four")
        if self.missing_evidence != _REQUIRED_DERIVATION_GAPS:
            raise ValueError("blocked derivation does not retain every evidence gap")
        if (
            self.per_placement_coordinate_sha256s
            or self.derived_component_coordinate_sha256s
            or self.derivation_command
        ):
            raise ValueError(
                "blocked derivation cannot carry guessed outputs or command"
            )
        return self


class FixedComponentExecutionEvidence(_ContentAddressedContract):
    """One component-only fixed coordinate and its original Phaser error model."""

    _identity_field: ClassVar[str] = "fixed_component_evidence_id"
    _identity_prefix: ClassVar[str] = "fixedcompevidence_"

    schema_version: Literal["2.0"]
    fixed_component_evidence_id: FixedComponentExecutionEvidenceIdentifier
    parent_state_id: CompositionStateIdentifier
    component_spec_id: ComponentSpecIdentifier
    placement_id: ComponentPlacementIdentifier
    fixed_coordinate_sha256: Sha256Hex
    source_parent_combined_coordinate_sha256: Sha256Hex
    coordinate_derivation_evidence_sha256: Sha256Hex
    coordinate_scope: Literal["component_only_all_observed_copies_in_parent_frame"] = (
        "component_only_all_observed_copies_in_parent_frame"
    )
    coordinate_format: Literal["pdb"] = "pdb"
    phaser_uncertainty_parameter: Literal["identity"] = "identity"
    phaser_identity_fraction: float = Field(gt=0, le=1)
    model_uncertainty_source: NonEmptyString
    model_uncertainty_evidence_sha256: Sha256Hex


class ComponentExpansionExecutionInput(_ContentAddressedContract):
    """Complete non-executable input for one selected B--F expansion attempt."""

    _identity_field: ClassVar[str] = "execution_input_id"
    _identity_prefix: ClassVar[str] = "compexecinput_"

    schema_version: Literal["2.0"]
    execution_input_id: ComponentExpansionExecutionInputIdentifier
    command_boundary: Literal[
        "input_complete_multi_fixed_partial_phaser_syntax_not_qualified"
    ] = "input_complete_multi_fixed_partial_phaser_syntax_not_qualified"
    depth_plan_id: ExpansionDepthPlanIdentifier
    selected_candidate: CompositionExpansionDepthCandidate
    parent_state: CompositionState
    fixed_components: tuple[FixedComponentExecutionEvidence, ...] = Field(
        min_length=1,
        max_length=5,
    )
    candidate_model_resolution: RegistryModelResolution
    candidate_coordinate_format: Literal["pdb"] = "pdb"
    candidate_phaser_uncertainty_parameter: Literal["identity"] = "identity"
    candidate_phaser_identity_fraction: float = Field(gt=0, le=1)
    candidate_model_uncertainty_source: NonEmptyString
    candidate_model_uncertainty_evidence_sha256: Sha256Hex
    diffraction_selection: DiffractionSelection
    free_r_identity: FreeRIdentity
    parent_combined_llg: float
    parent_score_evidence_sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_complete_input(self) -> Self:
        parent = self.parent_state
        if parent.depth > 5:
            raise ValueError("a depth-six parent cannot be expanded further")
        if parent.support_state not in _EXECUTABLE_PARENT_STATES:
            raise ValueError("component expansion requires a retained packed parent")
        if parent.combined_coordinate_sha256 is None:
            raise ValueError("component expansion parent lacks combined coordinates")
        parent_labels = tuple(item.label for item in parent.components)
        if parent_labels != _ORDERED_COMPONENT_LABELS[: parent.depth]:
            raise ValueError("parent components are not the ordered A--F prefix")

        selected = self.selected_candidate
        candidate = selected.hypothesis.component
        if (
            selected.parent_state_id != parent.state_id
            or selected.hypothesis.disposition is not ExpansionDisposition.SELECTED
        ):
            raise ValueError("candidate is not selected for the supplied parent")
        if candidate.label != _ORDERED_COMPONENT_LABELS[parent.depth]:
            raise ValueError("candidate is not the next ordered B--F component")
        if candidate.sequence_group_id in {
            item.sequence_group_id for item in parent.components
        }:
            raise ValueError("candidate repeats a parent sequence group")
        if candidate.requested_copy_count > 4:
            raise ValueError("candidate copy count exceeds four")

        if len(self.fixed_components) != parent.depth:
            raise ValueError("fixed evidence does not cover every parent component")
        fixed_digests: list[str] = []
        for component, placement, evidence in zip(
            parent.components,
            parent.placements,
            self.fixed_components,
            strict=True,
        ):
            if (
                evidence.parent_state_id != parent.state_id
                or evidence.component_spec_id != component.component_spec_id
                or evidence.placement_id != placement.placement_id
                or evidence.source_parent_combined_coordinate_sha256
                != parent.combined_coordinate_sha256
                or evidence.model_uncertainty_evidence_sha256
                != component.model_evidence_sha256
            ):
                raise ValueError("fixed evidence differs from its parent component")
            fixed_digests.append(evidence.fixed_coordinate_sha256)
        if parent.depth > 1 and parent.combined_coordinate_sha256 in fixed_digests:
            raise ValueError(
                "multi-component parent cannot reuse combined coordinates as one "
                "fixed component"
            )
        if len(set(fixed_digests)) != len(fixed_digests):
            raise ValueError("fixed components cannot share one collapsed coordinate")

        resolution = self.candidate_model_resolution
        if (
            not resolution.available
            or resolution.scope is not RegistryModelResolutionScope.CANDIDATE_COPY
            or resolution.parent_state_id != parent.state_id
            or resolution.parent_rank != selected.parent_rank
            or resolution.component_spec_id != candidate.component_spec_id
            or resolution.sequence_group_id != candidate.sequence_group_id
            or resolution.sequence_sha256 != candidate.sequence_sha256
            or resolution.model_id != candidate.model_id
            or resolution.model_sha256 != candidate.model_sha256
            or resolution.requested_copy_count != candidate.requested_copy_count
        ):
            raise ValueError("candidate model resolution differs from selected copy")
        if (
            self.candidate_model_uncertainty_evidence_sha256
            != candidate.model_evidence_sha256
        ):
            raise ValueError("candidate uncertainty evidence differs from its model")

        selection = self.diffraction_selection
        if (
            selection.crystal_id != parent.crystal_id
            or selection.diffraction_dataset_id != parent.diffraction_dataset_id
            or selection.mtz_sha256 != parent.diffraction_sha256
        ):
            raise ValueError("diffraction selection differs from parent state")
        free_r = self.free_r_identity
        if (
            free_r.diffraction_selection_id != selection.diffraction_selection_id
            or free_r.diffraction_dataset_id != selection.diffraction_dataset_id
            or free_r.crystal_id != selection.crystal_id
            or free_r.mtz_sha256 != selection.mtz_sha256
            or free_r.observation_dataset_id != selection.observation_dataset_id
        ):
            raise ValueError("Free-R identity differs from diffraction selection")
        return self


class ComponentExpansionScoreEvidence(_ContentAddressedContract):
    """One candidate's own TFZ and LLG increment without an identity claim."""

    _identity_field: ClassVar[str] = "score_evidence_id"
    _identity_prefix: ClassVar[str] = "compscore_"

    schema_version: Literal["2.0"]
    score_evidence_id: ComponentExpansionScoreEvidenceIdentifier
    execution_input: ComponentExpansionExecutionInput
    placement_inventory: PhaserPerPlacementInventory
    result_record_sha256: Sha256Hex
    score_ensemble_id: NonEmptyString
    parent_combined_llg: float
    combined_llg: float
    incremental_llg: float
    component_tfz: float
    placement: ComponentPlacement

    @classmethod
    def from_observed(
        cls,
        *,
        execution_input: ComponentExpansionExecutionInput,
        placement_inventory: PhaserPerPlacementInventory,
        score_ensemble_id: str,
        combined_llg: float,
        component_tfz: float,
        packing_passed: bool,
        warnings: tuple[str, ...] = (),
    ) -> Self:
        """Derive candidate-only placement evidence from a verified inventory."""

        candidate = execution_input.selected_candidate.hypothesis.component
        groups = {
            group.component_label: group
            for group in placement_inventory.component_groups
        }
        group = groups.get(candidate.label)
        if group is None:
            raise ValueError(
                "candidate component is absent from the placement inventory"
            )
        incremental_llg = combined_llg - execution_input.parent_combined_llg
        placement = ComponentPlacement.from_content(
            component_spec_id=candidate.component_spec_id,
            component_label=candidate.label,
            sequence_group_id=candidate.sequence_group_id,
            model_id=candidate.model_id,
            model_sha256=candidate.model_sha256,
            requested_copy_count=candidate.requested_copy_count,
            observed_copy_count=group.observed_copy_count,
            execution_status=ExecutionStatus.COMPLETED_HIT,
            component_tfz=component_tfz,
            incremental_llg=incremental_llg,
            packing_passed=packing_passed,
            coordinate_sha256=group.coordinate_sha256,
            identity_support=ComponentIdentitySupport.UNRESOLVED,
            warnings=warnings,
        )
        return cls.from_content(
            execution_input=execution_input,
            placement_inventory=placement_inventory,
            result_record_sha256=placement_inventory.result_record_sha256,
            score_ensemble_id=score_ensemble_id,
            parent_combined_llg=execution_input.parent_combined_llg,
            combined_llg=combined_llg,
            incremental_llg=incremental_llg,
            component_tfz=component_tfz,
            placement=placement,
        )

    @model_validator(mode="after")
    def _validate_component_score(self) -> Self:
        execution = self.execution_input
        inventory = self.placement_inventory
        candidate = execution.selected_candidate.hypothesis.component
        if inventory.crystal_id != execution.parent_state.crystal_id:
            raise ValueError("component score inventory belongs to another crystal")
        if self.result_record_sha256 != inventory.result_record_sha256:
            raise ValueError("component score result record checksum differs")

        expected_components = (*execution.parent_state.components, candidate)
        expected_labels = tuple(item.label for item in expected_components)
        groups = {group.component_label: group for group in inventory.component_groups}
        if set(groups) != set(expected_labels):
            raise ValueError(
                "component score inventory does not cover parent and candidate"
            )
        for component in expected_components:
            group = groups[component.label]
            if (
                group.source_model_sha256 != component.model_sha256
                or group.expected_copy_count != component.requested_copy_count
            ):
                raise ValueError(
                    "component score inventory changed component model or copies"
                )

        candidate_group = groups[candidate.label]
        if self.score_ensemble_id != candidate_group.ensemble_id:
            raise ValueError("component TFZ does not belong to the candidate ensemble")
        if not math.isclose(
            self.parent_combined_llg,
            execution.parent_combined_llg,
            rel_tol=1e-10,
            abs_tol=1e-8,
        ):
            raise ValueError("component score changed the fixed parent LLG")
        if not math.isclose(
            self.incremental_llg,
            self.combined_llg - self.parent_combined_llg,
            rel_tol=1e-10,
            abs_tol=1e-8,
        ):
            raise ValueError("component incremental LLG is not combined minus parent")

        placement = self.placement
        if (
            placement.component_spec_id != candidate.component_spec_id
            or placement.component_label != candidate.label
            or placement.sequence_group_id != candidate.sequence_group_id
            or placement.model_id != candidate.model_id
            or placement.model_sha256 != candidate.model_sha256
            or placement.requested_copy_count != candidate.requested_copy_count
            or placement.observed_copy_count != candidate_group.observed_copy_count
            or placement.coordinate_sha256 != candidate_group.coordinate_sha256
        ):
            raise ValueError("component placement differs from the selected candidate")
        if (
            placement.execution_status is not ExecutionStatus.COMPLETED_HIT
            or placement.identity_support is not ComponentIdentitySupport.UNRESOLVED
        ):
            raise ValueError(
                "component search scores cannot establish sequence identity"
            )
        if not math.isclose(
            placement.component_tfz or 0,
            self.component_tfz,
            rel_tol=1e-10,
            abs_tol=1e-8,
        ) or not math.isclose(
            placement.incremental_llg or 0,
            self.incremental_llg,
            rel_tol=1e-10,
            abs_tol=1e-8,
        ):
            raise ValueError(
                "component placement scores differ from candidate evidence"
            )
        return self


__all__ = [
    "ComponentCoordinateDerivationBoundary",
    "ComponentCoordinateDerivationGap",
    "ComponentExpansionExecutionInput",
    "ComponentExpansionScoreEvidence",
    "FixedComponentExecutionEvidence",
]
