"""Native Phaser per-placement output inventory for Phase III controls.

This schema records the exact ``.sol`` entry-to-PDB ordinal mapping produced by
the installed Phaser ``XYZOUT ON ENSEMBLE ON`` interface.  It intentionally
does not claim that independently written placement coordinates recombine to
the combined solution; that scientific/coordinate check requires a retained
real control output and remains a separate gate.
"""

from pathlib import PurePosixPath
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.schemas.base import NonEmptyString, PositiveInt, Sha256Hex
from genome_to_diffraction.schemas.v2.composition import (
    ComponentLabel,
    _ContentAddressedContract,
)

PhaserPlacementInventoryIdentifier = Annotated[
    str,
    Field(pattern=r"^phaserplacements_[a-f0-9]{64}$"),
]


def _portable_basename(value: str, *, suffix: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or len(path.parts) != 1
        or path.name != value
        or not value.endswith(suffix)
    ):
        raise ValueError(f"output path must be one portable {suffix} basename")


class PhaserPlacementArtifact(_ContentAddressedContract):
    """One exact ``SOLU 6DIM`` entry and its native placement PDB."""

    _identity_field: ClassVar[str] = "placement_artifact_id"
    _identity_prefix: ClassVar[str] = "phaserplacement_"

    schema_version: Literal["2.0"]
    placement_artifact_id: Annotated[
        str,
        Field(pattern=r"^phaserplacement_[a-f0-9]{64}$"),
    ]
    solution_number: PositiveInt
    placement_ordinal: PositiveInt
    ensemble_id: NonEmptyString
    component_label: ComponentLabel
    solu_6dim_line_sha256: Sha256Hex
    coordinate_path: NonEmptyString
    coordinate_sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_coordinate_name(self) -> Self:
        _portable_basename(self.coordinate_path, suffix=".pdb")
        expected = f"PHASER.{self.solution_number}.{self.placement_ordinal}.pdb"
        if self.coordinate_path != expected:
            raise ValueError("placement coordinate name does not match its ordinal")
        return self


class PhaserPlacementComponentGroup(_ContentAddressedContract):
    """Expected and observed native placements for one component ensemble."""

    _identity_field: ClassVar[str] = "component_group_id"
    _identity_prefix: ClassVar[str] = "phasercompgroup_"

    schema_version: Literal["2.0"]
    component_group_id: Annotated[
        str,
        Field(pattern=r"^phasercompgroup_[a-f0-9]{64}$"),
    ]
    component_label: ComponentLabel
    ensemble_id: NonEmptyString
    expected_copy_count: PositiveInt = Field(le=4)
    placement_ordinals: tuple[PositiveInt, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def _validate_ordinals(self) -> Self:
        if self.placement_ordinals != tuple(sorted(set(self.placement_ordinals))):
            raise ValueError("component placement ordinals must be unique and sorted")
        if len(self.placement_ordinals) != self.expected_copy_count:
            raise ValueError("component placement count differs from expectation")
        return self


class PhaserPerPlacementInventory(_ContentAddressedContract):
    """Complete exact mapping for the top native Phaser solution."""

    _identity_field: ClassVar[str] = "inventory_id"
    _identity_prefix: ClassVar[str] = "phaserplacements_"

    schema_version: Literal["2.0"]
    inventory_id: PhaserPlacementInventoryIdentifier
    adapter_version: Literal["phaser-per-placement-inventory-v1"]
    crystal_id: NonEmptyString
    search_id: NonEmptyString
    phaser_version: NonEmptyString
    solution_number: Literal[1]
    command_record_sha256: Sha256Hex
    result_record_sha256: Sha256Hex
    solution_file_path: Literal["PHASER.sol"]
    solution_file_sha256: Sha256Hex
    combined_coordinate_path: Literal["PHASER.1.pdb"]
    combined_coordinate_sha256: Sha256Hex
    output_command_binding: Literal[
        "phaser.keywords.general.xyzout=True;"
        "phaser.keywords.general.xyzout_ensemble=True;"
        "phaser.keywords.general.keywords=True"
    ]
    placements: tuple[PhaserPlacementArtifact, ...] = Field(min_length=2)
    component_groups: tuple[PhaserPlacementComponentGroup, ...] = Field(min_length=2)
    ordinal_mapping_status: Literal["verified_exact_sol_to_native_pdb"]
    recombination_status: Literal["not_assessed_pending_real_control"]
    can_create_fixed_component_evidence: Literal[False] = False

    @model_validator(mode="after")
    def _validate_complete_mapping(self) -> Self:
        ordinals = tuple(item.placement_ordinal for item in self.placements)
        if ordinals != tuple(range(1, len(self.placements) + 1)):
            raise ValueError("placement ordinals must form one complete sequence")
        if any(
            item.solution_number != self.solution_number for item in self.placements
        ):
            raise ValueError("placement belongs to another Phaser solution")
        group_keys = tuple(
            (group.component_label, group.ensemble_id)
            for group in self.component_groups
        )
        if group_keys != tuple(sorted(set(group_keys))):
            raise ValueError("component groups must be unique and sorted")
        group_by_ensemble = {
            group.ensemble_id: group for group in self.component_groups
        }
        if len(group_by_ensemble) != len(self.component_groups):
            raise ValueError("one ensemble cannot map to several components")
        observed: dict[str, list[int]] = {}
        for placement in self.placements:
            group = group_by_ensemble.get(placement.ensemble_id)
            if group is None or group.component_label != placement.component_label:
                raise ValueError("placement is not covered by its component group")
            observed.setdefault(placement.ensemble_id, []).append(
                placement.placement_ordinal
            )
        if set(observed) != set(group_by_ensemble):
            raise ValueError("component groups and placement ensembles differ")
        for ensemble_id, observed_ordinals in observed.items():
            if (
                tuple(observed_ordinals)
                != group_by_ensemble[ensemble_id].placement_ordinals
            ):
                raise ValueError("component group ordinals differ from placements")
        return self


__all__ = [
    "PhaserPerPlacementInventory",
    "PhaserPlacementArtifact",
    "PhaserPlacementComponentGroup",
    "PhaserPlacementInventoryIdentifier",
]
