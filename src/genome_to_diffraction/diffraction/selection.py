"""Build and verify Phase III diffraction-selection records.

The builder consumes one version-1 crystal entry and its completed preflight,
then creates an opt-in schema-v2 selection.  It rejects rendered observation
labels that occur in more than one MTZ dataset because the currently qualified
Phenix adapters pass labels but have no dataset-qualified label parameter.
Scientific overrides remain explicit provenance rather than being inferred from
warnings.  Tool adapters call :func:`verify_diffraction_selection` again before
execution so stale selections fail before any licensed command is launched.

The selection itself retains no inferred Free-R convention.  Phase III Free-R
label, distribution, and raw HKL-to-flag identities are validated in the
separate :mod:`genome_to_diffraction.diffraction.free_r_identity` foundation.
The brief-refinement command binding requires that exact identity while stating
that an explicit Phenix Free-R parameter still awaits real-runtime
qualification; this builder remains independent of MTZ file access.
"""

import math
from pathlib import Path

from pydantic import ValidationError

from genome_to_diffraction.diffraction.free_r_identity import (
    verify_free_r_identity_selection,
)
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.schemas.manifests import CrystalEntry
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MtzPreflightRecord,
    PreflightDecision,
)
from genome_to_diffraction.schemas.v2.diffraction import (
    DiffractionBoundHypothesis,
    DiffractionCommandBinding,
    DiffractionCommandConsumer,
    DiffractionSelection,
    DiffractionValueSource,
    FreeRIdentity,
    diffraction_dataset_id,
)
from genome_to_diffraction.status import InputContractError


class DiffractionSelectionError(InputContractError):
    """A Phase III diffraction selection is ambiguous or stale."""


def _labels(value: str) -> tuple[str, ...]:
    labels = tuple(item.strip() for item in value.split(",") if item.strip())
    if len(labels) not in {2, 4}:
        raise DiffractionSelectionError(
            "selected observations must be one value/sigma pair or anomalous quartet"
        )
    return labels


def _normalise_space_group(value: str) -> str:
    return " ".join(value.split()).upper()


def _same_float(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-9)


def verify_diffraction_selection(
    selection: DiffractionSelection,
    preflight: MtzPreflightRecord,
) -> None:
    """Verify one selection against the exact complete preflight record."""

    if selection.crystal_id != preflight.crystal_id:
        raise DiffractionSelectionError(
            "diffraction selection crystal differs from preflight"
        )
    if selection.preflight_id != preflight.preflight_id:
        raise DiffractionSelectionError(
            "diffraction selection preflight identity differs"
        )
    if selection.preflight_record_sha256 != canonical_digest(preflight):
        raise DiffractionSelectionError(
            "diffraction selection preflight record digest differs"
        )
    if selection.mtz_sha256 != preflight.mtz_sha256:
        raise DiffractionSelectionError("diffraction selection MTZ digest differs")
    if preflight.selected_observation_labels is None:
        raise DiffractionSelectionError("preflight has no selected observations")
    if selection.observation_labels != _labels(preflight.selected_observation_labels):
        raise DiffractionSelectionError(
            "diffraction selection observation labels differ from preflight"
        )
    if selection.observation_dataset_id != preflight.selected_observation_dataset_id:
        raise DiffractionSelectionError(
            "diffraction selection observation dataset differs from preflight"
        )
    if selection.observation_type != preflight.selected_observation_type:
        raise DiffractionSelectionError(
            "diffraction selection observation type differs from preflight"
        )
    matching_candidates = tuple(
        candidate
        for candidate in preflight.observation_candidate_identities
        if candidate.rendered_labels == preflight.selected_observation_labels
    )
    if len(matching_candidates) != 1:
        raise DiffractionSelectionError(
            "selected rendered observation labels must identify exactly one MTZ dataset"
        )
    candidate = matching_candidates[0]
    if (
        candidate.dataset_id != selection.observation_dataset_id
        or candidate.observation_type != selection.observation_type
    ):
        raise DiffractionSelectionError(
            "selected observation candidate identity differs from selection"
        )
    if _normalise_space_group(selection.selected_space_group) != (
        _normalise_space_group(preflight.space_group)
    ):
        raise DiffractionSelectionError(
            "diffraction selection space group differs from preflight"
        )
    if not _same_float(selection.resolution_low_a, preflight.resolution_low_a):
        raise DiffractionSelectionError(
            "diffraction selection low-resolution limit differs from preflight"
        )
    if not _same_float(selection.resolution_high_a, preflight.resolution_high_a):
        raise DiffractionSelectionError(
            "diffraction selection high-resolution limit differs from preflight"
        )


def build_diffraction_selection(
    *,
    crystal: CrystalEntry,
    preflight: MtzPreflightRecord,
    crystal_manifest_sha256: str,
) -> DiffractionSelection:
    """Create one content-addressed selection from an exact crystal/preflight pair."""

    if preflight.decision is PreflightDecision.FAIL:
        raise DiffractionSelectionError(
            "cannot select diffraction data from a failed preflight"
        )
    if crystal.crystal_id != preflight.crystal_id:
        raise DiffractionSelectionError("crystal entry and preflight identities differ")
    if (
        preflight.selected_observation_labels is None
        or preflight.selected_observation_dataset_id is None
        or preflight.selected_observation_type is None
    ):
        raise DiffractionSelectionError(
            "preflight lacks a dataset-qualified observation selection"
        )

    selected_labels = _labels(preflight.selected_observation_labels)
    if (
        crystal.obs_labels is not None
        and _labels(crystal.obs_labels) != selected_labels
    ):
        raise DiffractionSelectionError(
            "crystal observation override differs from selected preflight labels"
        )
    if crystal.space_group_override is not None and _normalise_space_group(
        crystal.space_group_override
    ) != _normalise_space_group(preflight.space_group):
        raise DiffractionSelectionError(
            "crystal space-group override differs from selected preflight group"
        )
    if crystal.low_resolution_override is not None and not _same_float(
        crystal.low_resolution_override,
        preflight.resolution_low_a,
    ):
        raise DiffractionSelectionError(
            "crystal low-resolution override differs from selected preflight limit"
        )
    if crystal.high_resolution_override is not None and not _same_float(
        crystal.high_resolution_override,
        preflight.resolution_high_a,
    ):
        raise DiffractionSelectionError(
            "crystal high-resolution override differs from selected preflight limit"
        )

    selection = DiffractionSelection.from_content(
        crystal_id=crystal.crystal_id,
        diffraction_dataset_id=diffraction_dataset_id(
            crystal_id=crystal.crystal_id,
            mtz_sha256=preflight.mtz_sha256,
        ),
        mtz_sha256=preflight.mtz_sha256,
        preflight_id=preflight.preflight_id,
        preflight_record_sha256=canonical_digest(preflight),
        crystal_manifest_sha256=crystal_manifest_sha256,
        observation_dataset_id=preflight.selected_observation_dataset_id,
        observation_labels=selected_labels,
        observation_type=preflight.selected_observation_type,
        selected_space_group=preflight.space_group,
        resolution_low_a=preflight.resolution_low_a,
        resolution_high_a=preflight.resolution_high_a,
        observation_source=(
            DiffractionValueSource.CRYSTAL_MANIFEST_OVERRIDE
            if crystal.obs_labels is not None
            else DiffractionValueSource.MTZ_PREFLIGHT_AUTOMATIC
        ),
        space_group_source=(
            DiffractionValueSource.CRYSTAL_MANIFEST_OVERRIDE
            if crystal.space_group_override is not None
            else DiffractionValueSource.MTZ_HEADER
        ),
        resolution_low_source=(
            DiffractionValueSource.CRYSTAL_MANIFEST_OVERRIDE
            if crystal.low_resolution_override is not None
            else DiffractionValueSource.MTZ_RESOLUTION_RANGE
        ),
        resolution_high_source=(
            DiffractionValueSource.CRYSTAL_MANIFEST_OVERRIDE
            if crystal.high_resolution_override is not None
            else DiffractionValueSource.MTZ_RESOLUTION_RANGE
        ),
    )
    verify_diffraction_selection(selection, preflight)
    return selection


def load_diffraction_selection(path: Path) -> DiffractionSelection:
    """Load one strict schema-v2 selection JSON document."""

    resolved = path.resolve(strict=True)
    try:
        return DiffractionSelection.model_validate_json(
            resolved.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise DiffractionSelectionError(
            f"invalid diffraction selection: {resolved}"
        ) from error


def bind_phase3_hypothesis(
    hypothesis: MrHypothesis,
    selection: DiffractionSelection,
) -> DiffractionBoundHypothesis:
    """Bind a complete immutable v1 hypothesis payload to one Phase III selection."""

    if hypothesis.crystal_id != selection.crystal_id:
        raise DiffractionSelectionError(
            "hypothesis crystal differs from diffraction selection"
        )
    if hypothesis.obs_labels is None or _labels(hypothesis.obs_labels) != (
        selection.observation_labels
    ):
        raise DiffractionSelectionError(
            "hypothesis observations differ from diffraction selection"
        )
    if _normalise_space_group(hypothesis.space_group) != _normalise_space_group(
        selection.selected_space_group
    ):
        raise DiffractionSelectionError(
            "hypothesis space group differs from diffraction selection"
        )
    return DiffractionBoundHypothesis.from_content(
        legacy_hypothesis_id=hypothesis.hypothesis_id,
        legacy_hypothesis_sha256=canonical_digest(hypothesis),
        crystal_id=hypothesis.crystal_id,
        diffraction_selection_id=selection.diffraction_selection_id,
        diffraction_dataset_id=selection.diffraction_dataset_id,
        mtz_sha256=selection.mtz_sha256,
    )


def build_diffraction_command_binding(
    *,
    consumer: DiffractionCommandConsumer,
    command_owner_id: str,
    selection: DiffractionSelection,
    free_r_identity: FreeRIdentity | None = None,
) -> DiffractionCommandBinding:
    """Create the typed external-command propagation boundary for one selection."""

    if consumer is DiffractionCommandConsumer.BRIEF_REFINEMENT:
        if free_r_identity is None:
            raise DiffractionSelectionError(
                "Phase III brief refinement requires a Free-R identity"
            )
        verify_free_r_identity_selection(free_r_identity, selection)
    elif free_r_identity is not None:
        raise DiffractionSelectionError(
            "first-copy Phaser cannot consume a brief-refinement Free-R identity"
        )

    resolution_binding = (
        "verified_by_mtz_preflight_explicit_refinement_limits_pending"
        if consumer is DiffractionCommandConsumer.FIRST_COPY_PHASER
        else "sequence_from_map_high_resolution_explicit_refinement_limits_pending"
    )
    command_mtz_binding = (
        "exact_selected_mtz"
        if consumer is DiffractionCommandConsumer.FIRST_COPY_PHASER
        else "derived_parent_mtz_recorded_derivation_verification_pending"
    )
    return DiffractionCommandBinding.from_content(
        command_owner_id=command_owner_id,
        consumer=consumer,
        diffraction_selection_id=selection.diffraction_selection_id,
        diffraction_dataset_id=selection.diffraction_dataset_id,
        mtz_sha256=selection.mtz_sha256,
        command_mtz_binding=command_mtz_binding,
        observation_dataset_id=selection.observation_dataset_id,
        observation_labels=selection.observation_labels,
        observation_type=selection.observation_type,
        selected_space_group=selection.selected_space_group,
        resolution_low_a=selection.resolution_low_a,
        resolution_high_a=selection.resolution_high_a,
        resolution_command_binding=resolution_binding,
        free_r_identity_id=(
            free_r_identity.free_r_identity_id if free_r_identity is not None else None
        ),
        free_r_dataset_id=(
            free_r_identity.free_r_dataset_id if free_r_identity is not None else None
        ),
        free_r_label=(
            free_r_identity.free_r_label if free_r_identity is not None else None
        ),
        free_r_convention_status=(
            free_r_identity.convention_status if free_r_identity is not None else None
        ),
        free_r_test_flag_value=(
            free_r_identity.test_flag_value if free_r_identity is not None else None
        ),
        free_r_command_binding=(
            "selected_identity_recorded_explicit_phenix_parameter_not_qualified"
            if free_r_identity is not None
            else "not_applicable_first_copy_phaser"
        ),
        free_r_membership_binding=(
            "validated_source_identity_post_refinement_exact_comparison_required"
            if free_r_identity is not None
            else "identity_placeholder_only_membership_validation_pending"
        ),
    )


__all__ = [
    "DiffractionSelectionError",
    "bind_phase3_hypothesis",
    "build_diffraction_command_binding",
    "build_diffraction_selection",
    "load_diffraction_selection",
    "verify_diffraction_selection",
]
