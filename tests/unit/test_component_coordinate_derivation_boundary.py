"""Fail-closed tests for missing native Phaser component-coordinate evidence."""

import json

import pytest
from pydantic import ValidationError

from genome_to_diffraction.schemas.v2 import (
    ComponentCoordinateDerivationBoundary,
    ComponentCoordinateDerivationGap,
)


def _sha(index: int) -> str:
    return f"{index:064x}"


def _boundary() -> ComponentCoordinateDerivationBoundary:
    return ComponentCoordinateDerivationBoundary.from_content(
        crystal_id="3U7Q",
        source_commit="68d216fad6dc83ca4a66de1f0bd9a37d365f2b80",
        combined_coordinate_sha256=_sha(1),
        result_record_sha256=_sha(2),
        command_record_sha256=_sha(3),
        raw_log_sha256=_sha(4),
        retained_artifact_inventory_sha256=_sha(5),
        phaser_tool_version="Phenix 2.1-6048; Phaser 2.8.4",
        parent_component_labels=("A", "B"),
        observed_copy_counts=(2, 2),
    )


def _content(
    boundary: ComponentCoordinateDerivationBoundary,
    **changes: object,
) -> dict[str, object]:
    values = boundary.model_dump(
        mode="python",
        exclude={"derivation_boundary_id"},
    )
    values.update(changes)
    return values


def test_boundary_cannot_be_used_as_component_coordinate_evidence() -> None:
    boundary = _boundary()

    assert boundary.derivation_status.startswith("blocked_")
    assert boundary.exact_solution_file_sha256 is None
    assert boundary.per_placement_coordinate_sha256s == ()
    assert boundary.derived_component_coordinate_sha256s == ()
    assert not boundary.chain_to_ensemble_assignment_verified
    assert not boundary.full_precision_transforms_verified
    assert not boundary.recombination_verified
    assert not boundary.can_create_fixed_component_evidence
    assert boundary.derivation_command == ()
    assert boundary.missing_evidence == tuple(ComponentCoordinateDerivationGap)
    assert boundary.future_adapter_requirement.endswith("checksum_group_and_recombine")


def test_boundary_identity_binds_every_retained_evidence_checksum() -> None:
    boundary = _boundary()
    changed = ComponentCoordinateDerivationBoundary.from_content(
        **_content(boundary, raw_log_sha256=_sha(6))
    )

    assert changed.derivation_boundary_id != boundary.derivation_boundary_id

    stale = json.loads(boundary.model_dump_json())
    stale["raw_log_sha256"] = _sha(6)
    with pytest.raises(ValidationError, match="derivation_boundary_id"):
        ComponentCoordinateDerivationBoundary.model_validate(stale)


def test_boundary_requires_exact_component_coverage_and_all_evidence_gaps() -> None:
    boundary = _boundary()

    with pytest.raises(ValidationError, match="ordered A--F prefix"):
        ComponentCoordinateDerivationBoundary.from_content(
            **_content(boundary, parent_component_labels=("A", "C"))
        )
    with pytest.raises(ValidationError, match="cover every parent component"):
        ComponentCoordinateDerivationBoundary.from_content(
            **_content(boundary, observed_copy_counts=(2, 2, 1))
        )
    with pytest.raises(ValidationError, match="every evidence gap"):
        ComponentCoordinateDerivationBoundary.from_content(
            **_content(
                boundary,
                missing_evidence=(
                    ComponentCoordinateDerivationGap.EXACT_SOLUTION_FILE,
                ),
            )
        )


def test_boundary_rejects_guessed_coordinates_or_derivation_command() -> None:
    boundary = _boundary()

    with pytest.raises(ValidationError, match="guessed outputs or command"):
        ComponentCoordinateDerivationBoundary.from_content(
            **_content(
                boundary,
                per_placement_coordinate_sha256s=(_sha(7),),
            )
        )
    with pytest.raises(ValidationError, match="guessed outputs or command"):
        ComponentCoordinateDerivationBoundary.from_content(
            **_content(boundary, derivation_command=("phenix.phaser",))
        )
