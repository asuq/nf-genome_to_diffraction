"""Derive component identity solely from an owned, map-supported human review."""

from dataclasses import dataclass
from pathlib import Path

import gemmi
from pydantic import ValidationError

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.review.phase3_package import (
    PhaseIIIReviewPackageError,
    validate_phase3_review_package,
)
from genome_to_diffraction.schemas.v2.composition import (
    ComponentSequenceReviewEvidence,
    ComponentSpec,
    CompositionDecisionReviewEvidence,
)
from genome_to_diffraction.schemas.v2.review import PhaseIIIReviewCheckpoint
from genome_to_diffraction.status import InputContractError


class ComponentIdentityReviewError(InputContractError):
    """Component identity lacks independently owned, approved map evidence."""


@dataclass(frozen=True, slots=True)
class ComponentIdentityReviewRequest:
    """The exact files a reviewer inspected for one placed component."""

    component: ComponentSpec
    crystal_id: str
    owned_parent_run_id: str
    execution_identity_id: str
    reviewed_state_id: str
    review_package_directory: Path
    decision_file: Path
    sequence_map_result: Path
    refinement_result: Path
    review_map: Path


@dataclass(frozen=True, slots=True)
class CompositionDecisionReviewRequest:
    """The exact component, coordinate, map, and composition decision files."""

    components: tuple[ComponentSpec, ...]
    crystal_id: str
    owned_parent_run_id: str
    execution_identity_id: str
    reviewed_state_id: str
    review_package_directory: Path
    decision_file: Path
    combined_coordinates: Path
    refinement_result: Path
    review_map: Path


def _file(path: Path, *, root: Path | None = None, label: str) -> Path:
    if path.is_symlink():
        raise ComponentIdentityReviewError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ComponentIdentityReviewError(f"{label} is missing") from error
    if not resolved.is_file() or (
        root is not None and not resolved.is_relative_to(root)
    ):
        raise ComponentIdentityReviewError(f"{label} is unowned or unsafe")
    return resolved


def build_component_sequence_review_evidence(
    request: ComponentIdentityReviewRequest,
) -> ComponentSequenceReviewEvidence:
    """Read and cross-bind the exact owned review, approval, map, and results."""

    root = request.review_package_directory
    if root.is_symlink():
        raise ComponentIdentityReviewError("sequence review package is unsafe")
    try:
        root = root.resolve(strict=True)
        package = validate_phase3_review_package(root)
    except (OSError, PhaseIIIReviewPackageError) as error:
        raise ComponentIdentityReviewError(
            "sequence review package is absent or invalid"
        ) from error
    if (
        package.checkpoint is not PhaseIIIReviewCheckpoint.SEQUENCE
        or package.owned_parent_run_id != request.owned_parent_run_id
        or package.execution_identity_id != request.execution_identity_id
        or package.crystal_id != request.crystal_id
    ):
        raise ComponentIdentityReviewError(
            "sequence review package owner, execution, or crystal differs"
        )

    manifest = _file(
        root / "phase3_review_package_manifest.json",
        root=root,
        label="sequence review manifest",
    )
    decision = _file(request.decision_file, label="human sequence decision")
    sequence = _file(
        request.sequence_map_result,
        root=root,
        label="sequence-map result",
    )
    refinement = _file(
        request.refinement_result,
        root=root,
        label="refinement result",
    )
    review_map = _file(request.review_map, root=root, label="review map")
    try:
        observed_map = gemmi.read_ccp4_map(str(review_map))
        if min(observed_map.grid.nu, observed_map.grid.nv, observed_map.grid.nw) < 1:
            raise ValueError("review map has no density grid")
        return ComponentSequenceReviewEvidence(
            owned_parent_run_id=request.owned_parent_run_id,
            execution_identity_id=request.execution_identity_id,
            crystal_id=request.crystal_id,
            reviewed_state_id=request.reviewed_state_id,
            reviewed_item_id=request.component.sequence_group_id,
            component_spec_id=request.component.component_spec_id,
            component_label=request.component.label,
            sequence_group_id=request.component.sequence_group_id,
            model_id=request.component.model_id,
            model_sha256=request.component.model_sha256,
            requested_copy_count=request.component.requested_copy_count,
            review_package_json=manifest.read_text(encoding="utf-8"),
            review_package_manifest_sha256=sha256_file(manifest),
            decision_file_json=decision.read_text(encoding="utf-8"),
            decision_file_sha256=sha256_file(decision),
            sequence_map_result_json=sequence.read_text(encoding="utf-8"),
            sequence_map_result_sha256=sha256_file(sequence),
            refinement_result_json=refinement.read_text(encoding="utf-8"),
            refinement_result_sha256=sha256_file(refinement),
            review_map_sha256=sha256_file(review_map),
        )
    except (OSError, RuntimeError, ValidationError, ValueError) as error:
        raise ComponentIdentityReviewError(
            f"owned map-supported sequence review is invalid: {error}"
        ) from error


def build_composition_decision_review_evidence(
    request: CompositionDecisionReviewRequest,
) -> CompositionDecisionReviewEvidence:
    """Read a distinct human composition approval and its exact physical evidence."""

    root = request.review_package_directory
    if root.is_symlink():
        raise ComponentIdentityReviewError("composition review package is unsafe")
    try:
        root = root.resolve(strict=True)
        package = validate_phase3_review_package(root)
    except (OSError, PhaseIIIReviewPackageError) as error:
        raise ComponentIdentityReviewError(
            "composition review package is absent or invalid"
        ) from error
    if (
        package.checkpoint is not PhaseIIIReviewCheckpoint.COMPOSITION
        or package.owned_parent_run_id != request.owned_parent_run_id
        or package.execution_identity_id != request.execution_identity_id
        or package.crystal_id != request.crystal_id
        or not request.components
    ):
        raise ComponentIdentityReviewError(
            "composition review owner, execution, crystal, or components differ"
        )

    manifest = _file(
        root / "phase3_review_package_manifest.json",
        root=root,
        label="composition review manifest",
    )
    decision = _file(request.decision_file, label="human composition decision")
    combined = _file(
        request.combined_coordinates,
        root=root,
        label="combined component coordinates",
    )
    refinement = _file(
        request.refinement_result,
        root=root,
        label="composition refinement result",
    )
    review_map = _file(request.review_map, root=root, label="composition review map")
    try:
        structure = gemmi.read_structure(str(combined))
        atom_count = sum(
            len(residue) for model in structure for chain in model for residue in chain
        )
        density = gemmi.read_ccp4_map(str(review_map))
        if atom_count < 1 or min(density.grid.nu, density.grid.nv, density.grid.nw) < 1:
            raise ValueError("composition coordinates or map contain no observations")
        return CompositionDecisionReviewEvidence(
            owned_parent_run_id=request.owned_parent_run_id,
            execution_identity_id=request.execution_identity_id,
            crystal_id=request.crystal_id,
            reviewed_state_id=request.reviewed_state_id,
            reviewed_item_id=request.reviewed_state_id,
            review_package_json=manifest.read_text(encoding="utf-8"),
            review_package_manifest_sha256=sha256_file(manifest),
            decision_file_json=decision.read_text(encoding="utf-8"),
            decision_file_sha256=sha256_file(decision),
            component_spec_ids=tuple(
                component.component_spec_id for component in request.components
            ),
            component_labels=tuple(component.label for component in request.components),
            sequence_group_ids=tuple(
                component.sequence_group_id for component in request.components
            ),
            model_sha256s=tuple(
                component.model_sha256 for component in request.components
            ),
            requested_copy_counts=tuple(
                component.requested_copy_count for component in request.components
            ),
            combined_coordinate_sha256=sha256_file(combined),
            refinement_result_json=refinement.read_text(encoding="utf-8"),
            refinement_result_sha256=sha256_file(refinement),
            review_map_sha256=sha256_file(review_map),
        )
    except (OSError, RuntimeError, ValidationError, ValueError) as error:
        raise ComponentIdentityReviewError(
            f"owned map-supported composition review is invalid: {error}"
        ) from error
