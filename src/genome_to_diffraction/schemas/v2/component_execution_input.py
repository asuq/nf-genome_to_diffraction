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
"""

from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.schemas.base import NonEmptyString, Sha256Hex
from genome_to_diffraction.schemas.v2.composition import (
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

FixedComponentExecutionEvidenceIdentifier = Annotated[
    str,
    Field(pattern=r"^fixedcompevidence_[a-f0-9]{64}$"),
]
ComponentExpansionExecutionInputIdentifier = Annotated[
    str,
    Field(pattern=r"^compexecinput_[a-f0-9]{64}$"),
]

_ORDERED_COMPONENT_LABELS = ("A", "B", "C", "D", "E", "F")
_EXECUTABLE_PARENT_STATES = {
    CompositionSupportState.PACKED,
    CompositionSupportState.REFINED,
    CompositionSupportState.REVIEW_SUPPORTED,
    CompositionSupportState.COMPOSITION_SUPPORTED,
}


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


__all__ = [
    "ComponentExpansionExecutionInput",
    "FixedComponentExecutionEvidence",
]
