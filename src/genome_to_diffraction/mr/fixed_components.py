"""Bind verified Phaser component coordinates to their original uncertainty.

The adapter consumes a checksum-validated component inventory and a packed
schema-v2 composition state.  It produces the already-existing fixed-component
execution records without constructing a Phaser command or relaxing copy,
model, crystal, combined-coordinate, or original uncertainty identity.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.schemas.v2 import (
    CompositionState,
    CompositionSupportState,
    PhaserPerPlacementInventory,
)
from genome_to_diffraction.schemas.v2.component_execution_input import (
    FixedComponentExecutionEvidence,
)
from genome_to_diffraction.status import InputContractError


class FixedComponentEvidenceError(InputContractError):
    """Verified coordinates cannot be bound to their exact parent state."""


@dataclass(frozen=True, slots=True)
class FixedComponentUncertainty:
    """Original component-specific Phaser identity and evidence record."""

    component_label: str
    phaser_identity_fraction: float
    model_uncertainty_source: str
    model_uncertainty_evidence_sha256: str


@dataclass(frozen=True, slots=True)
class FixedComponentEvidenceRequest:
    """One packed parent, verified component inventory, and original errors."""

    parent_state: CompositionState
    inventory_json: Path
    uncertainties: tuple[FixedComponentUncertainty, ...]


@dataclass(frozen=True, slots=True)
class FixedComponentEvidenceOutput:
    """Ordered fixed evidence and independently verified component paths."""

    evidence: tuple[FixedComponentExecutionEvidence, ...]
    coordinate_paths: tuple[Path, ...]
    inventory_sha256: str


def _regular_file(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise FixedComponentEvidenceError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise FixedComponentEvidenceError(f"{label} is absent or unreadable") from error
    if not resolved.is_file():
        raise FixedComponentEvidenceError(f"{label} must be a regular file")
    return resolved


def build_fixed_component_execution_evidence(
    request: FixedComponentEvidenceRequest,
) -> FixedComponentEvidenceOutput:
    """Recover every original component coordinate/error without collapsing it."""

    inventory_path = _regular_file(request.inventory_json, label="component inventory")
    inventory_bytes = inventory_path.read_bytes()
    try:
        inventory = PhaserPerPlacementInventory.model_validate_json(inventory_bytes)
    except ValidationError as error:
        raise FixedComponentEvidenceError("component inventory is invalid") from error

    parent = request.parent_state
    if parent.support_state not in {
        CompositionSupportState.PACKED,
        CompositionSupportState.REFINED,
        CompositionSupportState.REVIEW_SUPPORTED,
        CompositionSupportState.COMPOSITION_SUPPORTED,
    }:
        raise FixedComponentEvidenceError("parent state has not passed packing")
    if (
        parent.crystal_id != inventory.crystal_id
        or parent.combined_coordinate_sha256 != inventory.combined_coordinate_sha256
    ):
        raise FixedComponentEvidenceError(
            "inventory differs from parent crystal or coordinates"
        )

    combined = _regular_file(
        inventory_path.parent / inventory.combined_coordinate_path,
        label="combined parent coordinate",
    )
    if sha256_file(combined) != inventory.combined_coordinate_sha256:
        raise FixedComponentEvidenceError("combined parent coordinate checksum differs")

    groups = {group.component_label: group for group in inventory.component_groups}
    uncertainties = {item.component_label: item for item in request.uncertainties}
    parent_labels = tuple(component.label for component in parent.components)
    if (
        len(uncertainties) != len(request.uncertainties)
        or set(groups) != set(parent_labels)
        or set(uncertainties) != set(parent_labels)
    ):
        raise FixedComponentEvidenceError(
            "component inventory or uncertainty coverage differs"
        )

    inventory_sha256 = hashlib.sha256(inventory_bytes).hexdigest()
    records: list[FixedComponentExecutionEvidence] = []
    paths: list[Path] = []
    for component, placement in zip(parent.components, parent.placements, strict=True):
        group = groups[component.label]
        uncertainty = uncertainties[component.label]
        if (
            group.source_model_sha256 != component.model_sha256
            or group.expected_copy_count != component.requested_copy_count
            or group.observed_copy_count != placement.observed_copy_count
            or uncertainty.model_uncertainty_evidence_sha256
            != component.model_evidence_sha256
        ):
            raise FixedComponentEvidenceError(
                f"component {component.label} model, copies, "
                "or original uncertainty differ"
            )
        coordinate = _regular_file(
            inventory_path.parent / group.coordinate_path,
            label=f"component {component.label} coordinate",
        )
        if sha256_file(coordinate) != group.coordinate_sha256:
            raise FixedComponentEvidenceError(
                f"component {component.label} coordinate checksum differs"
            )
        try:
            record = FixedComponentExecutionEvidence.from_content(
                parent_state_id=parent.state_id,
                component_spec_id=component.component_spec_id,
                placement_id=placement.placement_id,
                fixed_coordinate_sha256=group.coordinate_sha256,
                source_parent_combined_coordinate_sha256=(
                    inventory.combined_coordinate_sha256
                ),
                coordinate_derivation_evidence_sha256=inventory_sha256,
                phaser_identity_fraction=uncertainty.phaser_identity_fraction,
                model_uncertainty_source=uncertainty.model_uncertainty_source,
                model_uncertainty_evidence_sha256=(
                    uncertainty.model_uncertainty_evidence_sha256
                ),
            )
        except ValidationError as error:
            raise FixedComponentEvidenceError(
                f"component {component.label} original uncertainty is invalid"
            ) from error
        records.append(record)
        paths.append(coordinate)

    if len({record.fixed_coordinate_sha256 for record in records}) != len(records):
        raise FixedComponentEvidenceError(
            "component coordinates collapse into one model"
        )
    return FixedComponentEvidenceOutput(
        evidence=tuple(records),
        coordinate_paths=tuple(paths),
        inventory_sha256=inventory_sha256,
    )
