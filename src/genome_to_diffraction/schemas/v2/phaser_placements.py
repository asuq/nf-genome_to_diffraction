"""Exact Phaser component-coordinate derivation for Phase III controls.

The installed Phenix wrapper emits ``PHASER.sol`` and a combined PDB but does
not honour its advertised per-ensemble output switch.  Components are therefore
assigned by exact source-model polymer identity, never PDB chain order, and
their full atom partition is verified against the combined solution.
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
    """One exact ``SOLU 6DIM`` entry and its derived component PDB."""

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
        expected = f"component_{self.component_label}.pdb"
        if self.coordinate_path != expected:
            raise ValueError("placement coordinate does not match its component")
        return self


class PhaserPlacementComponentGroup(_ContentAddressedContract):
    """Complete exact-model chain group for one component ensemble."""

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
    observed_copy_count: PositiveInt = Field(le=4)
    placement_ordinals: tuple[PositiveInt, ...] = Field(min_length=1, max_length=4)
    combined_chain_ids: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=4)
    source_model_sha256: Sha256Hex
    source_model_polymer_sha256: Sha256Hex
    coordinate_path: NonEmptyString
    coordinate_sha256: Sha256Hex
    atom_count: PositiveInt

    @model_validator(mode="after")
    def _validate_ordinals(self) -> Self:
        if self.placement_ordinals != tuple(sorted(set(self.placement_ordinals))):
            raise ValueError("component placement ordinals must be unique and sorted")
        if self.observed_copy_count != self.expected_copy_count:
            raise ValueError("component copy count differs from expectation")
        if self.combined_chain_ids != tuple(sorted(set(self.combined_chain_ids))):
            raise ValueError("component chain IDs must be unique and sorted")
        if len(self.combined_chain_ids) != self.observed_copy_count:
            raise ValueError("component chains do not match observed copy count")
        _portable_basename(self.coordinate_path, suffix=".pdb")
        if self.coordinate_path != f"component_{self.component_label}.pdb":
            raise ValueError("component coordinate name does not match its label")
        return self


class PhaserPerPlacementInventory(_ContentAddressedContract):
    """Complete exact solution/chain mapping and verified atom partition."""

    _identity_field: ClassVar[str] = "inventory_id"
    _identity_prefix: ClassVar[str] = "phaserplacements_"

    schema_version: Literal["2.0"]
    inventory_id: PhaserPlacementInventoryIdentifier
    adapter_version: Literal["phaser-component-coordinate-inventory-v2"]
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
    combined_atom_count: PositiveInt
    recombined_atom_count: PositiveInt
    recombined_atom_sha256: Sha256Hex
    ordinal_mapping_status: Literal["verified_exact_sol_to_model_bound_chains"]
    recombination_status: Literal["verified_exact_combined_atom_partition"]
    can_create_fixed_component_evidence: Literal[True] = True

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
        all_chain_ids = tuple(
            chain_id
            for group in self.component_groups
            for chain_id in group.combined_chain_ids
        )
        if len(set(all_chain_ids)) != len(all_chain_ids):
            raise ValueError("one combined chain cannot belong to several components")
        if (
            self.combined_atom_count != self.recombined_atom_count
            or sum(group.atom_count for group in self.component_groups)
            != self.combined_atom_count
        ):
            raise ValueError("component atoms do not reconstruct the combined model")
        observed: dict[str, list[int]] = {}
        for placement in self.placements:
            group = group_by_ensemble.get(placement.ensemble_id)
            if group is None or group.component_label != placement.component_label:
                raise ValueError("placement is not covered by its component group")
            if (
                placement.coordinate_path != group.coordinate_path
                or placement.coordinate_sha256 != group.coordinate_sha256
            ):
                raise ValueError("placement coordinate differs from its component")
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
