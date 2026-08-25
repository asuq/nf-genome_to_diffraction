"""Phase III contracts for bounded multi-component composition search.

The records in this module describe scientific state; they do not execute Phaser,
refinement, map calculation, or any other external command.  Inputs and outputs are
strict immutable JSON-compatible records.  Invalid state transitions fail Pydantic
validation, while scientific no-hit and unresolved-identity outcomes remain typed
records rather than execution failures.

Every top-level record and expansion candidate is content-addressed over its complete
canonical payload except for its own identifier.  Therefore any change to identity,
ordering, evidence, status, or warning changes the identifier and invalidates a cache
key.  Focused validation and mutation coverage lives in
``tests/unit/test_composition_contracts_v2.py`` and
``tests/unit/test_composition_registry_planner.py``.  Registry model resolutions run
no external command: they serialise a checksum-verified match or one typed absence
for each parent component and candidate-copy input.

Version-1 contracts remain in :mod:`genome_to_diffraction.schemas.results`.  They are
not widened or reinterpreted here; callers opt into these records through the
``genome_to_diffraction.schemas.v2`` namespace.
"""

import hashlib
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import Field, ValidationError, ValidationInfo, model_validator

from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    OperatorIdentifier,
    PositiveFloat,
    PositiveInt,
    Sha256Hex,
)
from genome_to_diffraction.status import ExecutionStatus

ComponentLabel = Annotated[
    str,
    Field(pattern=r"^[A-Z][A-Z0-9_]*$", min_length=1),
]
SequenceGroupIdentifier = Annotated[
    str,
    Field(pattern=r"^seq_[a-f0-9]{64}$"),
]
ComponentSpecIdentifier = Annotated[
    str,
    Field(pattern=r"^compspec_[a-f0-9]{64}$"),
]
ComponentPlacementIdentifier = Annotated[
    str,
    Field(pattern=r"^compplace_[a-f0-9]{64}$"),
]
CompositionStateIdentifier = Annotated[
    str,
    Field(pattern=r"^compstate_[a-f0-9]{64}$"),
]
ExpansionCandidateIdentifier = Annotated[
    str,
    Field(pattern=r"^compexpandcand_[a-f0-9]{64}$"),
]
ExpansionPlanIdentifier = Annotated[
    str,
    Field(pattern=r"^compexpand_[a-f0-9]{64}$"),
]
ExpansionDepthParentIdentifier = Annotated[
    str,
    Field(pattern=r"^compexpanddepthparent_[a-f0-9]{64}$"),
]
ExpansionDepthCandidateIdentifier = Annotated[
    str,
    Field(pattern=r"^compexpanddepthcand_[a-f0-9]{64}$"),
]
ExpansionDepthPlanIdentifier = Annotated[
    str,
    Field(pattern=r"^compexpanddepth_[a-f0-9]{64}$"),
]
RegistryModelResolutionIdentifier = Annotated[
    str,
    Field(pattern=r"^modelresolution_[a-f0-9]{64}$"),
]
AllModelRegistryIdentifier = Annotated[
    str,
    Field(pattern=r"^allmodelreg_[a-f0-9]{64}$"),
]
ScopeDecisionIdentifier = Annotated[
    str,
    Field(pattern=r"^compscope_[a-f0-9]{64}$"),
]
CompositionAssessmentIdentifier = Annotated[
    str,
    Field(pattern=r"^compassess_[a-f0-9]{64}$"),
]

_CONTENT_BUILD_TOKEN = object()


class _ContentAddressedContract(ContractModel):
    """Validate a full RFC-8785 content identifier for a frozen record."""

    _identity_field: ClassVar[str]
    _identity_prefix: ClassVar[str]

    @classmethod
    def from_content(cls, **values: Any) -> Self:
        """Validate content, derive its identifier, then validate the final record."""

        raw = dict(values)
        raw.setdefault("schema_version", "2.0")
        raw[cls._identity_field] = f"{cls._identity_prefix}{'0' * 64}"
        provisional = cls.model_validate(
            raw,
            context={
                "content_build_token": _CONTENT_BUILD_TOKEN,
                "content_build_type": cls,
            },
        )
        complete = provisional.model_dump(mode="python")
        payload = {
            key: value for key, value in complete.items() if key != cls._identity_field
        }
        complete[cls._identity_field] = content_id(cls._identity_prefix, payload)
        return cls.model_validate(complete)

    @model_validator(mode="after")
    def _validate_content_identity(self, info: ValidationInfo) -> Self:
        if (
            info.context is not None
            and info.context.get("content_build_token") is _CONTENT_BUILD_TOKEN
            and info.context.get("content_build_type") is type(self)
        ):
            return self
        payload = self.model_dump(
            mode="python",
            exclude={self._identity_field},
        )
        expected = content_id(self._identity_prefix, payload)
        if getattr(self, self._identity_field) != expected:
            raise ValueError(
                f"{self._identity_field} does not match canonical record content"
            )
        return self


class ModelUnavailableReason(StrEnum):
    """Typed reason an exact registry-backed model cannot be scheduled."""

    NO_ELIGIBLE_MODEL = "no_eligible_model"
    SEQUENCE_GROUP_NOT_REGISTERED = "sequence_group_not_registered"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    VARIANT_UNAVAILABLE = "variant_unavailable"
    MODEL_NOT_REGISTERED = "model_not_registered"


class RegistryModelResolutionScope(StrEnum):
    """Location of one exact model reference in an expansion request."""

    PARENT_COMPONENT = "parent_component"
    CANDIDATE_COPY = "candidate_copy"


class RegistryModelResolution(_ContentAddressedContract):
    """Checksum-verified registry match or typed absence for one model input."""

    _identity_field = "resolution_id"
    _identity_prefix = "modelresolution_"

    schema_version: Literal["2.0"]
    resolution_id: RegistryModelResolutionIdentifier
    model_registry_id: AllModelRegistryIdentifier
    scope: RegistryModelResolutionScope
    parent_state_id: CompositionStateIdentifier
    parent_rank: PositiveInt = Field(le=3)
    candidate_rank: PositiveInt | None = None
    component_spec_id: ComponentSpecIdentifier
    requested_copy_count: PositiveInt = Field(le=4)
    sequence_group_id: SequenceGroupIdentifier
    sequence_sha256: Sha256Hex
    model_id: NonEmptyString
    model_sha256: Sha256Hex
    requested_provider: NonEmptyString | None = None
    requested_variant_type: NonEmptyString | None = None
    registry_entry_sha256: Sha256Hex | None = None
    resolved_provider: NonEmptyString | None = None
    resolved_variant_type: NonEmptyString | None = None
    unavailable_reason: ModelUnavailableReason | None = None

    @model_validator(mode="after")
    def _validate_resolution(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError("resolution sequence group does not match its digest")
        if self.scope is RegistryModelResolutionScope.PARENT_COMPONENT:
            if self.candidate_rank is not None:
                raise ValueError("parent model resolution cannot carry candidate rank")
            if (
                self.requested_provider is not None
                or self.requested_variant_type is not None
            ):
                raise ValueError("parent model resolution cannot carry query filters")
        elif self.candidate_rank is None:
            raise ValueError("candidate-copy resolution requires candidate rank")

        available_fields = (
            self.registry_entry_sha256,
            self.resolved_provider,
            self.resolved_variant_type,
        )
        if self.unavailable_reason is None:
            if any(value is None for value in available_fields):
                raise ValueError("available model resolution lacks registry evidence")
        elif any(value is not None for value in available_fields):
            raise ValueError("unavailable model resolution retains registry evidence")
        return self

    @property
    def available(self) -> bool:
        """Return whether the exact requested model was checksum verified."""

        return self.unavailable_reason is None


class ComponentIdentitySupport(StrEnum):
    """Sequence-level interpretation of one placed component."""

    UNRESOLVED = "unresolved"
    SEQUENCE_EQUIVALENCE_GROUP = "sequence_equivalence_group_supported"
    EXACT_SEQUENCE = "exact_sequence_supported"


class ComponentSpec(_ContentAddressedContract):
    """One ordered composition component and its requested copy hypothesis."""

    _identity_field = "component_spec_id"
    _identity_prefix = "compspec_"

    schema_version: Literal["2.0"]
    component_spec_id: ComponentSpecIdentifier
    label: ComponentLabel
    sequence_group_id: SequenceGroupIdentifier
    sequence_sha256: Sha256Hex
    model_id: NonEmptyString
    model_sha256: Sha256Hex
    requested_copy_count: PositiveInt
    sequence_mass_da: PositiveFloat | None = None
    sequence_mass_lower_da: PositiveFloat | None = None
    sequence_mass_upper_da: PositiveFloat | None = None
    mass_evidence_sha256: Sha256Hex
    model_evidence_sha256: Sha256Hex
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_sequence_group_identity(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError(
                "sequence_group_id does not match the exact sequence digest"
            )
        exact = self.sequence_mass_da is not None
        bounded = (
            self.sequence_mass_lower_da is not None
            or self.sequence_mass_upper_da is not None
        )
        unavailable = not exact and not bounded
        if exact and bounded:
            raise ValueError("component mass cannot be both exact and bounded")
        if bounded and (
            self.sequence_mass_lower_da is None or self.sequence_mass_upper_da is None
        ):
            raise ValueError("component mass bounds must be supplied together")
        if (
            self.sequence_mass_lower_da is not None
            and self.sequence_mass_upper_da is not None
            and self.sequence_mass_lower_da > self.sequence_mass_upper_da
        ):
            raise ValueError("component mass lower bound exceeds upper bound")
        if unavailable and "sequence_mass_unavailable" not in self.warnings:
            raise ValueError(
                "unavailable component mass requires sequence_mass_unavailable"
            )
        return self


class OwnedComponentReviewEvidence(ContractModel):
    """Actual owned review-package and human-decision bytes, not opaque hashes."""

    checkpoint: Literal["sequence", "composition"]
    owned_parent_run_id: OperatorIdentifier
    execution_identity_id: Annotated[
        str,
        Field(pattern=r"^phase3exec_[a-f0-9]{64}$"),
    ]
    crystal_id: OperatorIdentifier
    reviewed_state_id: OperatorIdentifier
    reviewed_item_id: OperatorIdentifier
    review_package_json: NonEmptyString
    review_package_manifest_sha256: Sha256Hex
    decision_file_json: NonEmptyString
    decision_file_sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_owned_review_decision(self) -> Self:
        from genome_to_diffraction.schemas.v2.review import (
            PhaseIIIReviewDecisionFile,
            PhaseIIIReviewDecisionValue,
            PhaseIIIReviewPackageManifest,
        )

        if (
            hashlib.sha256(self.review_package_json.encode("utf-8")).hexdigest()
            != self.review_package_manifest_sha256
        ):
            raise ValueError("owned review-package bytes differ from their checksum")
        if (
            hashlib.sha256(self.decision_file_json.encode("utf-8")).hexdigest()
            != self.decision_file_sha256
        ):
            raise ValueError("owned review-decision bytes differ from their checksum")
        try:
            package = PhaseIIIReviewPackageManifest.model_validate_json(
                self.review_package_json
            )
            decisions = PhaseIIIReviewDecisionFile.model_validate_json(
                self.decision_file_json
            )
        except (ValidationError, ValueError) as error:
            raise ValueError("owned component review or decision is invalid") from error

        if (
            package.checkpoint.value != self.checkpoint
            or package.parent_profile != "unknown-single-component"
            or package.owned_parent_run_id != self.owned_parent_run_id
            or package.execution_identity_id != self.execution_identity_id
            or package.crystal_id != self.crystal_id
            or decisions.checkpoint is not package.checkpoint
            or decisions.owned_parent_run_id != package.owned_parent_run_id
            or decisions.review_package_id != package.review_package_id
            or decisions.review_package_manifest_sha256
            != self.review_package_manifest_sha256
        ):
            raise ValueError("owned component review package or decision differs")

        targets = tuple(
            target
            for target in package.permitted_targets
            if target.crystal_id == self.crystal_id
            and target.item_id == self.reviewed_item_id
        )
        approvals = tuple(
            decision
            for decision in decisions.decisions
            if decision.crystal_id == self.crystal_id
            and decision.item_id == self.reviewed_item_id
        )
        if (
            len(targets) != 1
            or len(approvals) != 1
            or approvals[0].decision is not PhaseIIIReviewDecisionValue.APPROVE
        ):
            raise ValueError("owned component review lacks its exact human approval")
        return self

    def package_artifact_digests(self) -> frozenset[str]:
        """Return the independently typed package's retained evidence inventory."""

        from genome_to_diffraction.schemas.v2.review import (
            PhaseIIIReviewPackageManifest,
        )

        package = PhaseIIIReviewPackageManifest.model_validate_json(
            self.review_package_json
        )
        return frozenset(item.sha256 for item in package.evidence_inventory)


class ComponentSequenceReviewEvidence(OwnedComponentReviewEvidence):
    """One human-approved component identity backed by an actual reviewed map."""

    checkpoint: Literal["sequence"] = "sequence"
    component_spec_id: ComponentSpecIdentifier
    component_label: ComponentLabel
    sequence_group_id: SequenceGroupIdentifier
    model_id: NonEmptyString
    model_sha256: Sha256Hex
    requested_copy_count: PositiveInt
    sequence_map_result_json: NonEmptyString
    sequence_map_result_sha256: Sha256Hex
    refinement_result_json: NonEmptyString
    refinement_result_sha256: Sha256Hex
    review_map_sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_map_supported_sequence_review(self) -> Self:
        from genome_to_diffraction.schemas.results import (
            BriefRefinementResult,
            SequenceMapResult,
        )

        if (
            hashlib.sha256(self.sequence_map_result_json.encode("utf-8")).hexdigest()
            != self.sequence_map_result_sha256
            or hashlib.sha256(self.refinement_result_json.encode("utf-8")).hexdigest()
            != self.refinement_result_sha256
        ):
            raise ValueError("owned component sequence-map evidence checksum differs")
        try:
            sequence = SequenceMapResult.model_validate_json(
                self.sequence_map_result_json
            )
            refinement = BriefRefinementResult.model_validate_json(
                self.refinement_result_json
            )
        except (ValidationError, ValueError) as error:
            raise ValueError(
                "owned component sequence-map evidence is invalid"
            ) from error

        matching = tuple(
            candidate
            for candidate in sequence.candidates
            if candidate.sequence_group_id == self.sequence_group_id
            and candidate.refinement_id == refinement.refinement_id
        )
        if (
            self.reviewed_item_id != self.sequence_group_id
            or sequence.execution_status is not ExecutionStatus.COMPLETED_HIT
            or refinement.execution_status
            not in {
                ExecutionStatus.COMPLETED_SUCCESS,
                ExecutionStatus.COMPLETED_WARNING,
            }
            or sequence.refinement_id != refinement.refinement_id
            or sequence.seed_solution_id != self.reviewed_state_id
            or refinement.seed_solution_id != self.reviewed_state_id
            or refinement.sequence_group_id != self.sequence_group_id
            or refinement.input_copy_count != self.requested_copy_count
            or refinement.map_sha256 != self.review_map_sha256
            or len(matching) != 1
        ):
            raise ValueError("owned component map, state, copies, or sequence differs")
        if not {
            self.model_sha256,
            self.sequence_map_result_sha256,
            self.refinement_result_sha256,
            self.review_map_sha256,
        }.issubset(self.package_artifact_digests()):
            raise ValueError("owned sequence review lacks its complete map evidence")
        return self

    @property
    def derived_identity_support(self) -> ComponentIdentitySupport:
        """Distinguish a unique reviewed locus from an equivalent-sequence group."""

        from genome_to_diffraction.schemas.results import SequenceMapResult

        sequence = SequenceMapResult.model_validate_json(self.sequence_map_result_json)
        matching = next(
            item
            for item in sequence.candidates
            if item.sequence_group_id == self.sequence_group_id
        )
        return (
            ComponentIdentitySupport.EXACT_SEQUENCE
            if len(matching.source_record_ids) == 1
            else ComponentIdentitySupport.SEQUENCE_EQUIVALENCE_GROUP
        )


class CompositionDecisionReviewEvidence(OwnedComponentReviewEvidence):
    """One separately human-approved, map-supported complete composition."""

    checkpoint: Literal["composition"] = "composition"
    component_spec_ids: tuple[ComponentSpecIdentifier, ...] = Field(min_length=1)
    component_labels: tuple[ComponentLabel, ...] = Field(min_length=1)
    sequence_group_ids: tuple[SequenceGroupIdentifier, ...] = Field(min_length=1)
    model_sha256s: tuple[Sha256Hex, ...] = Field(min_length=1)
    requested_copy_counts: tuple[PositiveInt, ...] = Field(min_length=1)
    combined_coordinate_sha256: Sha256Hex
    refinement_result_json: NonEmptyString
    refinement_result_sha256: Sha256Hex
    review_map_sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_composition_approval(self) -> Self:
        from genome_to_diffraction.schemas.results import BriefRefinementResult

        component_count = len(self.component_spec_ids)
        if any(
            len(values) != component_count
            for values in (
                self.component_labels,
                self.sequence_group_ids,
                self.model_sha256s,
                self.requested_copy_counts,
            )
        ):
            raise ValueError("composition approval component inventory is incomplete")
        if (
            len(set(self.component_spec_ids)) != component_count
            or len(set(self.sequence_group_ids)) != component_count
        ):
            raise ValueError("composition approval duplicates a component identity")
        if (
            hashlib.sha256(self.refinement_result_json.encode("utf-8")).hexdigest()
            != self.refinement_result_sha256
        ):
            raise ValueError("composition refinement evidence checksum differs")
        try:
            refinement = BriefRefinementResult.model_validate_json(
                self.refinement_result_json
            )
        except (ValidationError, ValueError) as error:
            raise ValueError("composition refinement evidence is invalid") from error
        if (
            self.reviewed_item_id != self.reviewed_state_id
            or refinement.seed_solution_id != self.reviewed_state_id
            or refinement.execution_status
            not in {
                ExecutionStatus.COMPLETED_SUCCESS,
                ExecutionStatus.COMPLETED_WARNING,
            }
            or refinement.map_sha256 != self.review_map_sha256
        ):
            raise ValueError("composition review state, map, or refinement differs")
        if not {
            self.combined_coordinate_sha256,
            self.refinement_result_sha256,
            self.review_map_sha256,
            *self.model_sha256s,
        }.issubset(self.package_artifact_digests()):
            raise ValueError("composition review lacks complete component evidence")
        return self


class ComponentPlacement(_ContentAddressedContract):
    """Terminal evidence for placing one component into a composition state."""

    _identity_field = "placement_id"
    _identity_prefix = "compplace_"

    schema_version: Literal["2.0"]
    placement_id: ComponentPlacementIdentifier
    component_spec_id: ComponentSpecIdentifier
    component_label: ComponentLabel
    sequence_group_id: SequenceGroupIdentifier
    model_id: NonEmptyString
    model_sha256: Sha256Hex
    requested_copy_count: PositiveInt
    observed_copy_count: int = Field(ge=0)
    execution_status: ExecutionStatus
    component_tfz: float | None = None
    incremental_llg: float | None = None
    packing_passed: bool
    coordinate_sha256: Sha256Hex | None = None
    identity_support: ComponentIdentitySupport
    sequence_review_evidence: ComponentSequenceReviewEvidence | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_terminal_placement(self) -> Self:
        if self.observed_copy_count > self.requested_copy_count:
            raise ValueError("observed copies cannot exceed requested copies")
        if (self.component_tfz is None) != (self.incremental_llg is None):
            raise ValueError("component TFZ and incremental LLG must be paired")

        metrics_present = self.component_tfz is not None
        if self.execution_status is ExecutionStatus.COMPLETED_HIT:
            if (
                self.observed_copy_count < 1
                or self.coordinate_sha256 is None
                or not metrics_present
            ):
                raise ValueError("completed placement lacks coordinates or metrics")
        elif self.execution_status in {
            ExecutionStatus.COMPLETED_NO_HIT,
            ExecutionStatus.FAILED_TOOL_EXECUTION,
            ExecutionStatus.FAILED_PARSE,
            ExecutionStatus.FAILED_INFRASTRUCTURE,
            ExecutionStatus.FAILED_INPUT_CONTRACT,
        }:
            if (
                self.observed_copy_count != 0
                or self.coordinate_sha256 is not None
                or metrics_present
                or self.packing_passed
                or self.identity_support is not ComponentIdentitySupport.UNRESOLVED
            ):
                raise ValueError("non-hit placement cannot retain placement evidence")
        else:
            raise ValueError("component placement requires a terminal search status")

        if self.packing_passed and (
            self.observed_copy_count != self.requested_copy_count
        ):
            raise ValueError("packing support requires every requested copy")
        if (
            self.identity_support is not ComponentIdentitySupport.UNRESOLVED
            and self.execution_status is not ExecutionStatus.COMPLETED_HIT
        ):
            raise ValueError("identity support requires a completed placement")
        if self.identity_support is ComponentIdentitySupport.UNRESOLVED:
            if self.sequence_review_evidence is not None:
                raise ValueError("unresolved placement cannot retain sequence approval")
        else:
            review = self.sequence_review_evidence
            if review is None:
                raise ValueError(
                    "identity support requires owned map-supported sequence review"
                )
            if (
                review.component_spec_id != self.component_spec_id
                or review.component_label != self.component_label
                or review.sequence_group_id != self.sequence_group_id
                or review.model_id != self.model_id
                or review.model_sha256 != self.model_sha256
                or review.requested_copy_count != self.requested_copy_count
                or review.derived_identity_support is not self.identity_support
            ):
                raise ValueError(
                    "owned component sequence approval differs from placement"
                )
        return self


class CompositionSupportState(StrEnum):
    """Ordered evidence promotions for one retained composition state."""

    NO_PLACEMENT = "no_placement"
    SEARCH_EVIDENCE_ONLY = "search_evidence_only"
    PLACED = "placed"
    PACKED = "packed"
    REFINED = "refined"
    REVIEW_SUPPORTED = "review_supported"
    COMPOSITION_SUPPORTED = "composition_supported"


class CompositionState(_ContentAddressedContract):
    """One ordered, immutable A+B+C+... state and its evidence chain."""

    _identity_field = "state_id"
    _identity_prefix = "compstate_"

    schema_version: Literal["2.0"]
    state_id: CompositionStateIdentifier
    crystal_id: NonEmptyString
    diffraction_dataset_id: NonEmptyString
    diffraction_sha256: Sha256Hex
    parent_state_id: CompositionStateIdentifier | None = None
    depth: PositiveInt
    components: tuple[ComponentSpec, ...] = Field(min_length=1)
    placements: tuple[ComponentPlacement, ...] = Field(min_length=1)
    combined_coordinate_sha256: Sha256Hex | None = None
    combined_mtz_sha256: Sha256Hex | None = None
    refinement_evidence_sha256: Sha256Hex | None = None
    map_evidence_sha256: Sha256Hex | None = None
    review_evidence_sha256: Sha256Hex | None = None
    composition_decision_sha256: Sha256Hex | None = None
    composition_review_evidence: CompositionDecisionReviewEvidence | None = None
    physical_mass_lower_da: PositiveFloat
    physical_mass_upper_da: PositiveFloat
    support_state: CompositionSupportState
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_ordered_state(self) -> Self:
        if self.depth != len(self.components) or self.depth != len(self.placements):
            raise ValueError("state depth must match components and placements")
        if (self.depth == 1) != (self.parent_state_id is None):
            raise ValueError("only a depth-one state may omit its parent state")
        if self.physical_mass_lower_da > self.physical_mass_upper_da:
            raise ValueError("physical mass lower bound exceeds upper bound")

        labels = tuple(component.label for component in self.components)
        sequence_groups = tuple(
            component.sequence_group_id for component in self.components
        )
        component_ids = tuple(
            component.component_spec_id for component in self.components
        )
        if len(set(labels)) != self.depth:
            raise ValueError("component labels must be unique within a state")
        if len(set(sequence_groups)) != self.depth:
            raise ValueError(
                "exact sequence-equivalence groups cannot repeat as components"
            )
        if len(set(component_ids)) != self.depth:
            raise ValueError("component specification identities must be unique")

        for component, placement in zip(
            self.components,
            self.placements,
            strict=True,
        ):
            if (
                placement.component_spec_id != component.component_spec_id
                or placement.component_label != component.label
                or placement.sequence_group_id != component.sequence_group_id
                or placement.model_id != component.model_id
                or placement.model_sha256 != component.model_sha256
                or placement.requested_copy_count != component.requested_copy_count
            ):
                raise ValueError(
                    "ordered placement identity does not match its component"
                )

        any_observed = any(
            placement.observed_copy_count > 0 for placement in self.placements
        )
        fully_placed = all(
            placement.execution_status is ExecutionStatus.COMPLETED_HIT
            and placement.observed_copy_count == component.requested_copy_count
            for component, placement in zip(
                self.components,
                self.placements,
                strict=True,
            )
        )
        fully_packed = fully_placed and all(
            placement.packing_passed for placement in self.placements
        )
        identities_supported = all(
            placement.identity_support is not ComponentIdentitySupport.UNRESOLVED
            for placement in self.placements
        )

        if self.support_state is CompositionSupportState.NO_PLACEMENT:
            if any_observed or self.combined_coordinate_sha256 is not None:
                raise ValueError("no-placement state contains placement evidence")
        elif self.support_state is CompositionSupportState.SEARCH_EVIDENCE_ONLY:
            if not any_observed or self.combined_coordinate_sha256 is None:
                raise ValueError(
                    "search-evidence state requires an observed coordinate result"
                )
        else:
            if not fully_placed or self.combined_coordinate_sha256 is None:
                raise ValueError("placed state lacks every requested component copy")

        if (
            self.support_state
            in {
                CompositionSupportState.PACKED,
                CompositionSupportState.REFINED,
                CompositionSupportState.REVIEW_SUPPORTED,
                CompositionSupportState.COMPOSITION_SUPPORTED,
            }
            and not fully_packed
        ):
            raise ValueError("packed-or-higher state lacks packing evidence")

        refined_or_higher = self.support_state in {
            CompositionSupportState.REFINED,
            CompositionSupportState.REVIEW_SUPPORTED,
            CompositionSupportState.COMPOSITION_SUPPORTED,
        }
        if refined_or_higher and (
            self.combined_mtz_sha256 is None or self.refinement_evidence_sha256 is None
        ):
            raise ValueError("refined-or-higher state lacks refinement evidence")

        review_or_higher = self.support_state in {
            CompositionSupportState.REVIEW_SUPPORTED,
            CompositionSupportState.COMPOSITION_SUPPORTED,
        }
        if review_or_higher and (
            self.map_evidence_sha256 is None
            or self.review_evidence_sha256 is None
            or not identities_supported
        ):
            raise ValueError("review-supported state lacks map, review, or identity")
        if review_or_higher:
            reviews = tuple(
                placement.sequence_review_evidence for placement in self.placements
            )
            if any(review is None for review in reviews):
                raise ValueError("review-supported state lacks owned sequence reviews")
            approved = tuple(review for review in reviews if review is not None)
            if any(
                review.crystal_id != self.crystal_id
                or review.review_map_sha256 != self.map_evidence_sha256
                for review in approved
            ):
                raise ValueError("component review differs from its composition state")
            package_digests = tuple(
                sorted({review.review_package_manifest_sha256 for review in approved})
            )
            expected_review_digest = (
                package_digests[0]
                if len(package_digests) == 1
                else canonical_digest(package_digests)
            )
            if self.review_evidence_sha256 != expected_review_digest:
                raise ValueError("component review-package evidence differs")
            owners = {
                (
                    review.owned_parent_run_id,
                    review.execution_identity_id,
                    review.reviewed_state_id,
                )
                for review in approved
            }
            if len(owners) != 1:
                raise ValueError("component sequence reviews have inconsistent owners")

        if self.support_state is CompositionSupportState.COMPOSITION_SUPPORTED:
            composition = self.composition_review_evidence
            if self.composition_decision_sha256 is None or composition is None:
                raise ValueError(
                    "composition-supported state lacks its owned review decision"
                )
            approved = tuple(
                review
                for placement in self.placements
                if (review := placement.sequence_review_evidence) is not None
            )
            if (
                composition.crystal_id != self.crystal_id
                or composition.component_spec_ids != component_ids
                or composition.component_labels != labels
                or composition.sequence_group_ids != sequence_groups
                or composition.model_sha256s
                != tuple(component.model_sha256 for component in self.components)
                or composition.requested_copy_counts
                != tuple(
                    component.requested_copy_count for component in self.components
                )
                or composition.combined_coordinate_sha256
                != self.combined_coordinate_sha256
                or composition.refinement_result_sha256
                != self.refinement_evidence_sha256
                or composition.review_map_sha256 != self.map_evidence_sha256
                or composition.decision_file_sha256 != self.composition_decision_sha256
                or any(
                    composition.owned_parent_run_id != review.owned_parent_run_id
                    or composition.execution_identity_id != review.execution_identity_id
                    or composition.reviewed_state_id != review.reviewed_state_id
                    for review in approved
                )
            ):
                raise ValueError("composition review differs from approved components")
        elif (
            self.composition_decision_sha256 is not None
            or self.composition_review_evidence is not None
        ):
            raise ValueError(
                "only a composition-supported state may bind a composition decision"
            )
        return self


class ExpansionDisposition(StrEnum):
    """Complete scheduling disposition for one expansion hypothesis."""

    SELECTED = "selected"
    DEFERRED_DEPTH_BUDGET = "deferred_depth_budget"
    DEFERRED_GLOBAL_BUDGET = "deferred_global_budget"
    DEFERRED_LOCALISATION_WAVE = "deferred_localisation_wave"
    DEFERRED_REVIEWER = "deferred_reviewer"
    UNSEARCHABLE_PHYSICAL_EVIDENCE = "unsearchable_physical_evidence"
    UNSEARCHABLE_NO_MODEL = "unsearchable_no_model"
    UNSEARCHABLE_MODEL_IDENTITY = "unsearchable_model_identity"
    EXCLUDED_PHYSICAL_IMPOSSIBLE = "excluded_physical_impossible"


class CompositionCandidateHypothesis(_ContentAddressedContract):
    """One ranked component/copy proposal in an expansion plan."""

    _identity_field = "candidate_hypothesis_id"
    _identity_prefix = "compexpandcand_"

    schema_version: Literal["2.0"]
    candidate_hypothesis_id: ExpansionCandidateIdentifier
    component: ComponentSpec
    rank: PositiveInt
    disposition: ExpansionDisposition
    disposition_reason: NonEmptyString
    physical_assessed: bool
    physical_possible: bool
    model_available: bool

    @model_validator(mode="after")
    def _validate_disposition(self) -> Self:
        mass_available = self.component.sequence_mass_da is not None or (
            self.component.sequence_mass_lower_da is not None
            and self.component.sequence_mass_upper_da is not None
        )
        if self.physical_assessed and not mass_available:
            raise ValueError("physical assessment requires component mass evidence")
        if self.disposition in {
            ExpansionDisposition.SELECTED,
            ExpansionDisposition.DEFERRED_DEPTH_BUDGET,
            ExpansionDisposition.DEFERRED_GLOBAL_BUDGET,
            ExpansionDisposition.DEFERRED_LOCALISATION_WAVE,
            ExpansionDisposition.DEFERRED_REVIEWER,
        } and not (
            self.physical_assessed and self.physical_possible and self.model_available
        ):
            raise ValueError("selected or deferred hypothesis is not searchable")
        if not self.physical_assessed and (
            self.physical_possible
            or self.disposition
            is not ExpansionDisposition.UNSEARCHABLE_PHYSICAL_EVIDENCE
        ):
            raise ValueError(
                "unassessed physical evidence requires its typed disposition"
            )
        if (
            self.physical_assessed
            and self.disposition is ExpansionDisposition.UNSEARCHABLE_PHYSICAL_EVIDENCE
        ):
            raise ValueError("unsearchable physical-evidence disposition was assessed")
        if (
            self.disposition is ExpansionDisposition.UNSEARCHABLE_NO_MODEL
            and self.model_available
        ):
            raise ValueError("no-model disposition contradicts model availability")
        if self.disposition is ExpansionDisposition.EXCLUDED_PHYSICAL_IMPOSSIBLE and (
            not self.physical_assessed or self.physical_possible
        ):
            raise ValueError("physically impossible disposition is contradictory")
        return self


class CompositionExpansionPlan(_ContentAddressedContract):
    """Deterministic bounded expansion from one retained parent state."""

    _identity_field = "plan_id"
    _identity_prefix = "compexpand_"

    schema_version: Literal["2.0"]
    plan_id: ExpansionPlanIdentifier
    crystal_id: NonEmptyString
    parent_state_id: CompositionStateIdentifier
    parent_depth: PositiveInt
    target_depth: PositiveInt
    parent_component_labels: tuple[ComponentLabel, ...] = Field(min_length=1)
    parent_sequence_group_ids: tuple[SequenceGroupIdentifier, ...] = Field(min_length=1)
    maximum_component_depth: PositiveInt = Field(le=6)
    beam_width: PositiveInt = Field(le=3)
    per_depth_attempt_budget: PositiveInt = Field(le=25)
    global_attempt_budget: PositiveInt = Field(le=100)
    global_attempts_used_before: int = Field(ge=0)
    ranking_policy_version: NonEmptyString
    candidate_count: int = Field(ge=0)
    selected_attempt_count: int = Field(ge=0)
    deferred_candidate_count: int = Field(ge=0)
    unsearchable_candidate_count: int = Field(ge=0)
    candidates: tuple[CompositionCandidateHypothesis, ...]

    @model_validator(mode="after")
    def _validate_plan_inventory(self) -> Self:
        if self.target_depth != self.parent_depth + 1:
            raise ValueError("target depth must immediately follow parent depth")
        if self.target_depth > self.maximum_component_depth:
            raise ValueError("target depth exceeds the configured search depth")
        if len(self.parent_component_labels) != self.parent_depth:
            raise ValueError("parent labels do not match parent depth")
        if len(self.parent_sequence_group_ids) != self.parent_depth:
            raise ValueError("parent sequence groups do not match parent depth")
        if len(set(self.parent_component_labels)) != self.parent_depth:
            raise ValueError("parent component labels must be unique")
        if len(set(self.parent_sequence_group_ids)) != self.parent_depth:
            raise ValueError("parent sequence groups must be unique")
        if self.global_attempts_used_before > self.global_attempt_budget:
            raise ValueError("used attempts exceed the global budget")
        if self.candidate_count != len(self.candidates):
            raise ValueError("candidate count does not match candidate inventory")
        if [candidate.rank for candidate in self.candidates] != list(
            range(1, self.candidate_count + 1)
        ):
            raise ValueError("candidate ranks must be contiguous and ordered")

        selected = sum(
            candidate.disposition is ExpansionDisposition.SELECTED
            for candidate in self.candidates
        )
        deferred = sum(
            candidate.disposition
            in {
                ExpansionDisposition.DEFERRED_DEPTH_BUDGET,
                ExpansionDisposition.DEFERRED_GLOBAL_BUDGET,
                ExpansionDisposition.DEFERRED_LOCALISATION_WAVE,
                ExpansionDisposition.DEFERRED_REVIEWER,
            }
            for candidate in self.candidates
        )
        unsearchable = self.candidate_count - selected - deferred
        if (
            selected != self.selected_attempt_count
            or deferred != self.deferred_candidate_count
            or unsearchable != self.unsearchable_candidate_count
        ):
            raise ValueError("plan counts do not match candidate dispositions")

        remaining_global = self.global_attempt_budget - self.global_attempts_used_before
        if selected > min(self.per_depth_attempt_budget, remaining_global):
            raise ValueError("selected attempts exceed a depth or global budget")

        parent_labels = set(self.parent_component_labels)
        parent_groups = set(self.parent_sequence_group_ids)
        candidate_ids: set[str] = set()
        for candidate in self.candidates:
            if candidate.candidate_hypothesis_id in candidate_ids:
                raise ValueError("candidate hypothesis identities must be unique")
            candidate_ids.add(candidate.candidate_hypothesis_id)
            if candidate.component.label in parent_labels:
                raise ValueError("candidate component label already exists in parent")
            if candidate.component.sequence_group_id in parent_groups:
                raise ValueError(
                    "candidate sequence-equivalence group already exists in parent"
                )
            if candidate.component.requested_copy_count > 4:
                raise ValueError("Phase III expansion copy count exceeds four")
        return self


class CompositionExpansionDepthParent(_ContentAddressedContract):
    """One parent identity retained in a globally budgeted depth batch."""

    _identity_field = "depth_parent_id"
    _identity_prefix = "compexpanddepthparent_"

    schema_version: Literal["2.0"]
    depth_parent_id: ExpansionDepthParentIdentifier
    parent_state_id: CompositionStateIdentifier
    parent_rank: PositiveInt = Field(le=3)
    parent_component_labels: tuple[ComponentLabel, ...] = Field(min_length=1)
    parent_sequence_group_ids: tuple[SequenceGroupIdentifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_parent_inventory(self) -> Self:
        if len(self.parent_component_labels) != len(self.parent_sequence_group_ids):
            raise ValueError("parent labels and sequence groups differ in length")
        if len(set(self.parent_component_labels)) != len(self.parent_component_labels):
            raise ValueError("parent component labels must be unique")
        if len(set(self.parent_sequence_group_ids)) != len(
            self.parent_sequence_group_ids
        ):
            raise ValueError("parent sequence groups must be unique")
        return self


class CompositionExpansionDepthCandidate(_ContentAddressedContract):
    """One parent-bound hypothesis in a globally budgeted depth batch."""

    _identity_field = "depth_candidate_id"
    _identity_prefix = "compexpanddepthcand_"

    schema_version: Literal["2.0"]
    depth_candidate_id: ExpansionDepthCandidateIdentifier
    parent_state_id: CompositionStateIdentifier
    parent_rank: PositiveInt = Field(le=3)
    hypothesis: CompositionCandidateHypothesis
    allocation_rank: PositiveInt | None = None

    @model_validator(mode="after")
    def _validate_allocation(self) -> Self:
        selected = self.hypothesis.disposition is ExpansionDisposition.SELECTED
        if selected != (self.allocation_rank is not None):
            raise ValueError(
                "only a selected depth candidate may carry an allocation rank"
            )
        return self


class CompositionExpansionDepthPlan(_ContentAddressedContract):
    """Authoritative one-depth budget shared across the retained parent beam.

    The older :class:`CompositionExpansionPlan` remains readable as a singular-
    parent record, but it cannot prove a shared beam budget.  Phase III
    scheduling uses this parent-bound depth plan so the 25-attempt cap is
    validated once across all retained parents.
    """

    _identity_field = "depth_plan_id"
    _identity_prefix = "compexpanddepth_"

    schema_version: Literal["2.0"]
    depth_plan_id: ExpansionDepthPlanIdentifier
    crystal_id: NonEmptyString
    diffraction_dataset_id: NonEmptyString
    parent_depth: PositiveInt
    target_depth: PositiveInt
    parents: tuple[CompositionExpansionDepthParent, ...] = Field(
        min_length=1,
        max_length=3,
    )
    maximum_component_depth: PositiveInt = Field(le=6)
    beam_width: PositiveInt = Field(le=3)
    per_depth_attempt_budget: PositiveInt = Field(le=25)
    global_attempt_budget: PositiveInt = Field(le=100)
    global_attempts_used_before: int = Field(ge=0)
    ranking_policy_version: NonEmptyString
    model_registry_id: AllModelRegistryIdentifier | None = None
    model_resolutions: tuple[RegistryModelResolution, ...] = ()
    candidate_count: int = Field(ge=0)
    physical_hypothesis_count: int = Field(ge=0)
    selected_attempt_count: int = Field(ge=0)
    deferred_candidate_count: int = Field(ge=0)
    unsearchable_candidate_count: int = Field(ge=0)
    candidates: tuple[CompositionExpansionDepthCandidate, ...]

    @model_validator(mode="after")
    def _validate_depth_batch(self) -> Self:
        if self.target_depth != self.parent_depth + 1:
            raise ValueError("target depth must immediately follow parent depth")
        if self.target_depth > self.maximum_component_depth:
            raise ValueError("target depth exceeds the configured search depth")
        if len(self.parents) > self.beam_width:
            raise ValueError("parent count exceeds the configured beam width")
        if [parent.parent_rank for parent in self.parents] != list(
            range(1, len(self.parents) + 1)
        ):
            raise ValueError("depth parent ranks must be contiguous and ordered")
        parent_by_id = {parent.parent_state_id: parent for parent in self.parents}
        if len(parent_by_id) != len(self.parents):
            raise ValueError("depth parent state identities must be unique")
        if self.global_attempts_used_before > self.global_attempt_budget:
            raise ValueError("used attempts exceed the global budget")
        if (self.model_registry_id is None) != (not self.model_resolutions):
            raise ValueError(
                "model registry identity and model resolutions must be paired"
            )
        if self.model_registry_id is not None:
            if any(
                resolution.model_registry_id != self.model_registry_id
                for resolution in self.model_resolutions
            ):
                raise ValueError("model resolution uses a different registry")
            resolution_ids = tuple(
                resolution.resolution_id for resolution in self.model_resolutions
            )
            if len(set(resolution_ids)) != len(resolution_ids):
                raise ValueError("duplicate model resolution identity")
            expected_order = tuple(
                sorted(self.model_resolutions, key=_model_resolution_sort_key)
            )
            if self.model_resolutions != expected_order:
                raise ValueError("model resolutions are not deterministic")
        if self.candidate_count != len(self.candidates):
            raise ValueError("candidate count does not match depth inventory")
        if len({candidate.depth_candidate_id for candidate in self.candidates}) != len(
            self.candidates
        ):
            raise ValueError("depth candidate identities must be unique")

        ranks_by_parent: dict[str, list[int]] = {
            parent.parent_state_id: [] for parent in self.parents
        }
        allocation_ranks: list[int] = []
        selected = deferred = physical = 0
        for candidate in self.candidates:
            parent = parent_by_id.get(candidate.parent_state_id)
            if parent is None or parent.parent_rank != candidate.parent_rank:
                raise ValueError("depth candidate refers to an unknown parent")
            ranks_by_parent[parent.parent_state_id].append(candidate.hypothesis.rank)
            physical += candidate.hypothesis.physical_possible
            if (
                candidate.hypothesis.component.label in parent.parent_component_labels
                or candidate.hypothesis.component.sequence_group_id
                in parent.parent_sequence_group_ids
            ):
                raise ValueError("depth candidate repeats a represented component")
            if candidate.hypothesis.disposition is ExpansionDisposition.SELECTED:
                selected += 1
                if candidate.allocation_rank is None:  # validated by child record
                    raise AssertionError("selected candidate lacks allocation rank")
                allocation_ranks.append(candidate.allocation_rank)
            elif candidate.hypothesis.disposition in {
                ExpansionDisposition.DEFERRED_DEPTH_BUDGET,
                ExpansionDisposition.DEFERRED_GLOBAL_BUDGET,
                ExpansionDisposition.DEFERRED_LOCALISATION_WAVE,
                ExpansionDisposition.DEFERRED_REVIEWER,
            }:
                deferred += 1

        if self.model_registry_id is not None:
            candidate_resolutions = tuple(
                resolution
                for resolution in self.model_resolutions
                if resolution.scope is RegistryModelResolutionScope.CANDIDATE_COPY
            )
            candidate_resolution_by_spec = {
                (resolution.parent_state_id, resolution.component_spec_id): resolution
                for resolution in candidate_resolutions
            }
            if len(candidate_resolution_by_spec) != len(candidate_resolutions):
                raise ValueError("duplicate parent-bound candidate model resolution")
            if len(candidate_resolution_by_spec) < self.candidate_count:
                raise ValueError(
                    "registry-bound plan requires one resolution per candidate copy"
                )
            parent_unavailable: set[str] = set()
            parent_groups_by_id: dict[str, set[str]] = {
                parent.parent_state_id: set() for parent in self.parents
            }
            for resolution in self.model_resolutions:
                parent = parent_by_id.get(resolution.parent_state_id)
                if parent is None or resolution.parent_rank != parent.parent_rank:
                    raise ValueError("model resolution refers to an unknown parent")
                if resolution.scope is RegistryModelResolutionScope.PARENT_COMPONENT:
                    parent_groups_by_id[parent.parent_state_id].add(
                        resolution.sequence_group_id
                    )
                    if not resolution.available:
                        parent_unavailable.add(parent.parent_state_id)
            for parent in self.parents:
                if parent_groups_by_id[parent.parent_state_id] != set(
                    parent.parent_sequence_group_ids
                ):
                    raise ValueError(
                        "parent model resolutions do not match parent components"
                    )
            for candidate in self.candidates:
                resolution = candidate_resolution_by_spec.get(
                    (
                        candidate.parent_state_id,
                        candidate.hypothesis.component.component_spec_id,
                    )
                )
                if resolution is None:
                    raise ValueError("candidate copy lacks a model resolution")
                component = candidate.hypothesis.component
                if (
                    resolution.parent_state_id != candidate.parent_state_id
                    or resolution.parent_rank != candidate.parent_rank
                    or resolution.sequence_group_id != component.sequence_group_id
                    or resolution.sequence_sha256 != component.sequence_sha256
                    or resolution.model_id != component.model_id
                    or resolution.model_sha256 != component.model_sha256
                    or resolution.requested_copy_count != component.requested_copy_count
                ):
                    raise ValueError(
                        "candidate model resolution does not match its component"
                    )
                expected_available = (
                    resolution.available
                    and candidate.parent_state_id not in parent_unavailable
                )
                if candidate.hypothesis.model_available != expected_available:
                    raise ValueError(
                        "candidate model availability disagrees with resolutions"
                    )

        for ranks in ranks_by_parent.values():
            if ranks != list(range(1, len(ranks) + 1)):
                raise ValueError(
                    "candidate ranks must be contiguous within each parent"
                )
        if sorted(allocation_ranks) != list(range(1, selected + 1)):
            raise ValueError("selected allocation ranks must be contiguous and unique")
        unsearchable = self.candidate_count - selected - deferred
        if (
            physical != self.physical_hypothesis_count
            or selected != self.selected_attempt_count
            or deferred != self.deferred_candidate_count
            or unsearchable != self.unsearchable_candidate_count
        ):
            raise ValueError("depth plan counts do not match candidate inventory")
        remaining_global = self.global_attempt_budget - self.global_attempts_used_before
        if selected > min(self.per_depth_attempt_budget, remaining_global):
            raise ValueError(
                "selected attempts exceed the shared depth or global budget"
            )
        return self


def _model_resolution_sort_key(
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


class CompositionStopReason(StrEnum):
    """First applicable reason that automatic component expansion stopped."""

    NO_PHYSICALLY_POSSIBLE_REMAINING_COMPONENT = (
        "no_physically_possible_remaining_component"
    )
    NO_RETAINED_PACKED_STATE = "no_retained_packed_state"
    MAXIMUM_COMPONENT_DEPTH_REACHED = "maximum_component_depth_reached"
    GLOBAL_ATTEMPT_BUDGET_REACHED = "global_attempt_budget_reached"
    INFRASTRUCTURE_OR_CONTRACT_FAILURE = "infrastructure_or_contract_failure"
    REVIEWER_HOLD = "reviewer_hold"


class ResidualContentState(StrEnum):
    """Review state of diffraction content not explained by the composition."""

    NOT_ASSESSED = "not_assessed"
    NONE_DETECTED = "none_detected"
    SUSPECTED = "suspected"
    UNRESOLVED = "unresolved"


class ComponentScopeStatus(StrEnum):
    """Claim scope at the reached component depth."""

    WITHIN_VALIDATED_COMPONENT_DEPTH = "within_validated_component_depth"
    PROVISIONAL_UNVALIDATED_COMPONENT_DEPTH = "provisional_unvalidated_component_depth"
    SEARCH_INCOMPLETE = "search_incomplete"


class CompositionClaimBoundary(StrEnum):
    """Maximum scientific claim allowed by scope and stop evidence."""

    COMPLETE_COMPOSITION_REVIEW_ELIGIBLE = "complete_composition_review_eligible"
    PARTIAL_OR_RESIDUAL_ONLY = "partial_or_residual_only"
    PROVISIONAL_UNVALIDATED_COMPONENT_DEPTH = "provisional_unvalidated_component_depth"
    SEARCH_INCOMPLETE = "search_incomplete"


class ComponentScopeDecision(_ContentAddressedContract):
    """Bound search depth, stop reason, residual state, and claim boundary."""

    _identity_field = "decision_id"
    _identity_prefix = "compscope_"

    schema_version: Literal["2.0"]
    decision_id: ScopeDecisionIdentifier
    crystal_id: NonEmptyString
    state_id: CompositionStateIdentifier
    search_depth_reached: PositiveInt
    maximum_search_depth: PositiveInt = Field(le=6)
    validated_component_depth: PositiveInt = Field(le=3)
    total_additional_attempt_budget: PositiveInt = Field(le=100)
    total_additional_attempts_used: int = Field(ge=0)
    remaining_physical_hypothesis_count: int = Field(ge=0)
    retained_packed_state_count: int = Field(ge=0)
    state_support_state: CompositionSupportState
    stop_reason: CompositionStopReason
    residual_content_state: ResidualContentState
    scope_status: ComponentScopeStatus
    claim_boundary: CompositionClaimBoundary
    complete_composition_claim_eligible: bool
    reviewer_hold_evidence_sha256: Sha256Hex | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _derive_scope_and_claim_boundary(self) -> Self:
        if self.search_depth_reached > self.maximum_search_depth:
            raise ValueError("reached depth exceeds the configured maximum")
        if self.validated_component_depth > self.maximum_search_depth:
            raise ValueError("validated depth exceeds maximum search depth")
        if self.total_additional_attempts_used > self.total_additional_attempt_budget:
            raise ValueError("used attempts exceed the global attempt budget")
        if (
            self.stop_reason
            is CompositionStopReason.NO_PHYSICALLY_POSSIBLE_REMAINING_COMPONENT
            and self.remaining_physical_hypothesis_count != 0
        ):
            raise ValueError("no-physical stop retains physical hypotheses")
        if (
            self.stop_reason is CompositionStopReason.NO_RETAINED_PACKED_STATE
            and self.retained_packed_state_count != 0
        ):
            raise ValueError("no-packed-state stop retains packed states")
        if (
            self.stop_reason is CompositionStopReason.MAXIMUM_COMPONENT_DEPTH_REACHED
            and self.search_depth_reached != self.maximum_search_depth
        ):
            raise ValueError("maximum-depth stop did not reach maximum depth")
        if (
            self.stop_reason is CompositionStopReason.GLOBAL_ATTEMPT_BUDGET_REACHED
            and self.total_additional_attempts_used
            != self.total_additional_attempt_budget
        ):
            raise ValueError("budget stop did not exhaust the global budget")
        if (self.stop_reason is CompositionStopReason.REVIEWER_HOLD) != (
            self.reviewer_hold_evidence_sha256 is not None
        ):
            raise ValueError("reviewer hold evidence must match the stop reason")

        incomplete_stop = self.stop_reason in {
            CompositionStopReason.GLOBAL_ATTEMPT_BUDGET_REACHED,
            CompositionStopReason.INFRASTRUCTURE_OR_CONTRACT_FAILURE,
            CompositionStopReason.REVIEWER_HOLD,
        }
        if self.search_depth_reached > self.validated_component_depth:
            expected_scope = (
                ComponentScopeStatus.PROVISIONAL_UNVALIDATED_COMPONENT_DEPTH
            )
            expected_boundary = (
                CompositionClaimBoundary.PROVISIONAL_UNVALIDATED_COMPONENT_DEPTH
            )
        elif incomplete_stop:
            expected_scope = ComponentScopeStatus.SEARCH_INCOMPLETE
            expected_boundary = CompositionClaimBoundary.SEARCH_INCOMPLETE
        else:
            expected_scope = ComponentScopeStatus.WITHIN_VALIDATED_COMPONENT_DEPTH
            eligible = (
                self.state_support_state
                is CompositionSupportState.COMPOSITION_SUPPORTED
                and self.residual_content_state is ResidualContentState.NONE_DETECTED
            )
            expected_boundary = (
                CompositionClaimBoundary.COMPLETE_COMPOSITION_REVIEW_ELIGIBLE
                if eligible
                else CompositionClaimBoundary.PARTIAL_OR_RESIDUAL_ONLY
            )

        expected_eligible = (
            expected_boundary
            is CompositionClaimBoundary.COMPLETE_COMPOSITION_REVIEW_ELIGIBLE
        )
        if self.scope_status is not expected_scope:
            raise ValueError("scope status disagrees with depth and stop evidence")
        if self.claim_boundary is not expected_boundary:
            raise ValueError("claim boundary disagrees with scope evidence")
        if self.complete_composition_claim_eligible != expected_eligible:
            raise ValueError("claim eligibility disagrees with claim boundary")
        return self


class CompositionScientificStatus(StrEnum):
    """Evidence-derived interpretation of one retained composition state."""

    COMPOSITION_SUPPORTED = "composition_supported"
    CREDIBLE_PARTIAL_OR_RESIDUAL = "credible_partial_or_residual"
    SEARCH_EVIDENCE_ONLY = "search_evidence_only"
    NO_SUPPORTED_COMPOSITION = "no_supported_composition"
    PROVISIONAL_UNVALIDATED_COMPONENT_DEPTH = "provisional_unvalidated_component_depth"
    EXECUTION_FAILURE = "execution_failure"


class CompositionAssessment(_ContentAddressedContract):
    """Scientific status and claim eligibility derived from one scope decision."""

    _identity_field = "assessment_id"
    _identity_prefix = "compassess_"

    schema_version: Literal["2.0"]
    assessment_id: CompositionAssessmentIdentifier
    crystal_id: NonEmptyString
    state_id: CompositionStateIdentifier
    scope_decision: ComponentScopeDecision
    execution_status: ExecutionStatus
    state_support_state: CompositionSupportState
    scientific_status: CompositionScientificStatus
    complete_composition_claim_eligible: bool
    complete_composition_claimed: bool
    final_review_decision_sha256: Sha256Hex | None = None
    composition_state_json: NonEmptyString | None = None
    evidence_sha256: dict[NonEmptyString, Sha256Hex] = Field(min_length=1)
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _derive_scientific_status(self) -> Self:
        if (
            self.scope_decision.crystal_id != self.crystal_id
            or self.scope_decision.state_id != self.state_id
            or self.scope_decision.state_support_state is not self.state_support_state
        ):
            raise ValueError("assessment identity disagrees with its scope decision")

        failure = self.execution_status in {
            ExecutionStatus.FAILED_INPUT_CONTRACT,
            ExecutionStatus.FAILED_TOOL_EXECUTION,
            ExecutionStatus.FAILED_PARSE,
            ExecutionStatus.FAILED_INFRASTRUCTURE,
        }
        if failure:
            expected_status = CompositionScientificStatus.EXECUTION_FAILURE
        elif (
            self.scope_decision.scope_status
            is ComponentScopeStatus.PROVISIONAL_UNVALIDATED_COMPONENT_DEPTH
        ):
            expected_status = (
                CompositionScientificStatus.PROVISIONAL_UNVALIDATED_COMPONENT_DEPTH
            )
        elif (
            self.state_support_state is CompositionSupportState.COMPOSITION_SUPPORTED
            and self.scope_decision.complete_composition_claim_eligible
        ):
            expected_status = CompositionScientificStatus.COMPOSITION_SUPPORTED
        elif self.state_support_state in {
            CompositionSupportState.REVIEW_SUPPORTED,
            CompositionSupportState.COMPOSITION_SUPPORTED,
        }:
            expected_status = CompositionScientificStatus.CREDIBLE_PARTIAL_OR_RESIDUAL
        elif self.state_support_state is CompositionSupportState.NO_PLACEMENT:
            expected_status = CompositionScientificStatus.NO_SUPPORTED_COMPOSITION
        else:
            expected_status = CompositionScientificStatus.SEARCH_EVIDENCE_ONLY

        expected_eligible = (
            not failure
            and self.scope_decision.complete_composition_claim_eligible
            and self.state_support_state
            is CompositionSupportState.COMPOSITION_SUPPORTED
        )
        if self.scientific_status is not expected_status:
            raise ValueError("scientific status disagrees with retained evidence")
        if self.complete_composition_claim_eligible != expected_eligible:
            raise ValueError("assessment claim eligibility disagrees with evidence")
        if self.complete_composition_claimed and (
            not expected_eligible or self.final_review_decision_sha256 is None
        ):
            raise ValueError(
                "complete composition claim requires eligibility and final review"
            )
        if (
            expected_status
            in {
                CompositionScientificStatus.COMPOSITION_SUPPORTED,
                CompositionScientificStatus.CREDIBLE_PARTIAL_OR_RESIDUAL,
            }
            or self.complete_composition_claimed
        ):
            if self.composition_state_json is None:
                raise ValueError(
                    "composition claim requires owned composition state and review"
                )
            state_digest = hashlib.sha256(
                self.composition_state_json.encode("utf-8")
            ).hexdigest()
            if self.evidence_sha256.get("composition_state") != state_digest:
                raise ValueError("owned composition state checksum differs")
            try:
                state = CompositionState.model_validate_json(
                    self.composition_state_json
                )
            except (ValidationError, ValueError) as error:
                raise ValueError("owned composition state is invalid") from error
            if (
                state.state_id != self.state_id
                or state.crystal_id != self.crystal_id
                or state.support_state is not self.state_support_state
            ):
                raise ValueError("owned composition state differs from assessment")
            if self.complete_composition_claimed and (
                state.composition_review_evidence is None
                or state.composition_review_evidence.decision_file_sha256
                != self.final_review_decision_sha256
            ):
                raise ValueError(
                    "composition claim differs from its owned final review"
                )
        return self
