"""Derive exact component coordinates from real Phaser combined output.

The installed Phenix wrapper ignores its advertised per-ensemble PDB flag, so
native ``PHASER.1.<ordinal>.pdb`` files cannot be assumed.  This boundary maps
each combined-coordinate chain to exactly one checksum-bound source-model
polymer sequence, binds the exact top-solution ``SOLU 6DIM`` records, writes
one multi-copy PDB per component, and verifies the complete atom partition.
No chain order, rounded transform, or scientific identity is guessed.
"""

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import gemmi
from pydantic import ValidationError

from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.v2 import (
    PhaserPerPlacementInventory,
    PhaserPlacementArtifact,
    PhaserPlacementComponentGroup,
)
from genome_to_diffraction.status import InputContractError

_ROOT = "PHASER"
_SOLUTION_SET = re.compile(rb"^\s*SOLU(?:TION)?\s+SET(?:\s|$)", re.I)
_PLACEMENT = re.compile(
    rb"^\s*SOLU(?:TION)?\s+6DIM\s+ENSE(?:MBLE)?\s+(\S+)(?:\s|$)",
    re.I,
)
_OUTPUT_BINDING = (
    "phaser.keywords.general.xyzout=True;"
    "phaser.keywords.general.xyzout_ensemble=True;"
    "phaser.keywords.general.keywords=True"
)


class PhaserPerPlacementError(InputContractError):
    """Native Phaser output cannot be mapped without guessing."""


@dataclass(frozen=True, slots=True)
class ExpectedPhaserComponent:
    """One known component-to-ensemble mapping and expected copy count."""

    component_label: str
    ensemble_id: str
    expected_copy_count: int


@dataclass(frozen=True, slots=True)
class PhaserPerPlacementRequest:
    """Exact retained files and expected known-control component mapping."""

    crystal_id: str
    search_id: str
    phaser_version: str
    output_directory: Path
    command_record: Path
    result_record: Path
    expected_components: tuple[ExpectedPhaserComponent, ...]
    component_models: tuple[tuple[str, Path], ...] = ()


@dataclass(frozen=True, slots=True)
class PhaserPerPlacementOutput:
    """Validated inventory and its canonical JSON path."""

    inventory: PhaserPerPlacementInventory
    inventory_json: Path


def _regular_file(path: Path, *, label: str) -> Path:
    try:
        if path.is_symlink():
            raise PhaserPerPlacementError(f"{label} must not be a symlink")
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise PhaserPerPlacementError(f"{label} is absent or unreadable") from error
    if not resolved.is_file():
        raise PhaserPerPlacementError(f"{label} must be a regular file")
    return resolved


def _top_solution_entries(solution_file: Path) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    solution_number = 0
    for raw_line in solution_file.read_bytes().splitlines(keepends=True):
        if _SOLUTION_SET.search(raw_line):
            solution_number += 1
            if solution_number > 1:
                break
            continue
        if solution_number != 1:
            continue
        match = _PLACEMENT.search(raw_line)
        if match is None:
            continue
        try:
            ensemble_id = match.group(1).decode("ascii")
        except UnicodeDecodeError as error:
            raise PhaserPerPlacementError(
                "Phaser solution contains a non-ASCII ensemble ID"
            ) from error
        entries.append((ensemble_id, hashlib.sha256(raw_line).hexdigest()))
    if solution_number == 0:
        raise PhaserPerPlacementError("Phaser .sol lacks a SOLU SET block")
    if not entries:
        raise PhaserPerPlacementError("top Phaser solution lacks SOLU 6DIM entries")
    return tuple(entries)


def _expected_components(
    values: tuple[ExpectedPhaserComponent, ...],
) -> tuple[ExpectedPhaserComponent, ...]:
    if len(values) < 2:
        raise PhaserPerPlacementError("per-placement control requires two components")
    ordered = tuple(
        sorted(values, key=lambda item: (item.component_label, item.ensemble_id))
    )
    if len({item.component_label for item in ordered}) != len(ordered):
        raise PhaserPerPlacementError("component labels must be unique")
    if len({item.ensemble_id for item in ordered}) != len(ordered):
        raise PhaserPerPlacementError("ensemble IDs must be unique")
    for item in ordered:
        if (
            not item.component_label
            or not item.ensemble_id
            or item.expected_copy_count < 1
            or item.expected_copy_count > 4
        ):
            raise PhaserPerPlacementError("expected component mapping is invalid")
    return ordered


def _read_structure(path: Path, *, label: str) -> gemmi.Structure:
    try:
        structure = gemmi.read_structure(str(path))
        structure.setup_entities()
    except (OSError, RuntimeError, ValueError) as error:
        raise PhaserPerPlacementError(f"cannot parse {label} coordinates") from error
    if len(structure) != 1:
        raise PhaserPerPlacementError(f"{label} must contain exactly one model")
    return structure


def _polymer_signature(chain: gemmi.Chain, *, label: str) -> str:
    residues = tuple(residue.name for residue in chain.get_polymer())
    if not residues:
        raise PhaserPerPlacementError(f"{label} chain {chain.name} has no polymer")
    return hashlib.sha256(canonical_json_text(residues).encode("ascii")).hexdigest()


def _atom_records(structure: gemmi.Structure) -> tuple[tuple[str, ...], ...]:
    records: list[tuple[str, ...]] = []
    for chain in structure[0]:
        polymer = list(chain.get_polymer())
        if len(polymer) != len(list(chain)):
            raise PhaserPerPlacementError(
                f"combined chain {chain.name} contains unassigned non-polymer residues"
            )
        for residue in polymer:
            for atom in residue:
                records.append(
                    (
                        chain.name,
                        residue.name,
                        str(residue.seqid),
                        atom.name,
                        str(atom.altloc),
                        str(atom.element.name),
                        f"{atom.pos.x + 0.0:.3f}",
                        f"{atom.pos.y + 0.0:.3f}",
                        f"{atom.pos.z + 0.0:.3f}",
                        f"{atom.occ:.2f}",
                        f"{atom.b_iso:.2f}",
                    )
                )
    if not records:
        raise PhaserPerPlacementError("combined Phaser coordinate contains no atoms")
    return tuple(records)


def _component_model_signatures(
    request: PhaserPerPlacementRequest,
    expected: tuple[ExpectedPhaserComponent, ...],
) -> dict[str, tuple[Path, str]]:
    models: dict[str, tuple[Path, str]] = {}
    for label, model_path in request.component_models:
        if label in models:
            raise PhaserPerPlacementError("component model labels must be unique")
        model = _regular_file(model_path, label=f"component {label} source model")
        structure = _read_structure(model, label=f"component {label} source model")
        chains = [chain for chain in structure[0] if list(chain.get_polymer())]
        if len(chains) != 1:
            raise PhaserPerPlacementError(
                f"component {label} source model must contain one polymer chain"
            )
        models[label] = (
            model,
            _polymer_signature(chains[0], label=f"component {label} source model"),
        )
    if set(models) != {component.component_label for component in expected}:
        raise PhaserPerPlacementError("source models do not cover every component")
    if len({signature for _, signature in models.values()}) != len(models):
        raise PhaserPerPlacementError(
            "component source-model sequences are indistinguishable"
        )
    return models


def collect_phaser_per_placement_outputs(
    request: PhaserPerPlacementRequest,
) -> PhaserPerPlacementOutput:
    """Checksum exact solution entries and verified component-only coordinates."""

    output = request.output_directory.resolve(strict=True)
    if not output.is_dir() or output.is_symlink():
        raise PhaserPerPlacementError("Phaser output must be a regular directory")
    command = _regular_file(request.command_record, label="Phaser command record")
    result = _regular_file(request.result_record, label="Phaser result record")
    solution = _regular_file(output / f"{_ROOT}.sol", label="Phaser solution file")
    combined = _regular_file(
        output / f"{_ROOT}.1.pdb",
        label="combined Phaser coordinate",
    )
    expected = _expected_components(request.expected_components)
    expected_by_ensemble = {item.ensemble_id: item for item in expected}
    entries = _top_solution_entries(solution)
    models = _component_model_signatures(request, expected)
    combined_structure = _read_structure(combined, label="combined Phaser")
    combined_records = _atom_records(combined_structure)
    expected_signatures = {signature: label for label, (_, signature) in models.items()}
    chains_by_component: dict[str, list[str]] = {}
    for chain in combined_structure[0]:
        signature = _polymer_signature(chain, label="combined Phaser")
        component_label = expected_signatures.get(signature)
        if component_label is None:
            raise PhaserPerPlacementError(
                f"combined chain {chain.name} matches no component source model"
            )
        chains_by_component.setdefault(component_label, []).append(chain.name)

    observed_by_ensemble: dict[str, list[int]] = {}
    for ordinal, (ensemble_id, _) in enumerate(entries, start=1):
        if ensemble_id not in expected_by_ensemble:
            raise PhaserPerPlacementError(
                f"top Phaser solution contains an unexpected ensemble: {ensemble_id}"
            )
        observed_by_ensemble.setdefault(ensemble_id, []).append(ordinal)
    if set(observed_by_ensemble) != set(expected_by_ensemble):
        raise PhaserPerPlacementError("top Phaser solution omits a component ensemble")

    derived_records: list[tuple[str, ...]] = []
    component_groups: list[PhaserPlacementComponentGroup] = []
    for component in expected:
        ordinals = tuple(observed_by_ensemble.get(component.ensemble_id, ()))
        chain_ids = tuple(
            sorted(chains_by_component.get(component.component_label, ()))
        )
        if len(chain_ids) != component.expected_copy_count:
            raise PhaserPerPlacementError(
                f"component {component.component_label} placement count differs"
            )
        if component == expected[-1] and len(ordinals) != component.expected_copy_count:
            raise PhaserPerPlacementError(
                f"component {component.component_label} solution count differs"
            )
        if component != expected[-1] and len(ordinals) != 1:
            raise PhaserPerPlacementError(
                f"fixed component {component.component_label} solution is ambiguous"
            )
        selection = gemmi.Selection(
            f"/1/{','.join(chain_ids)};polymer"
        ).copy_structure_selection(combined_structure)
        coordinate_name = f"component_{component.component_label}.pdb"
        coordinate = output / coordinate_name
        if coordinate.is_symlink():
            raise PhaserPerPlacementError(
                "derived component output must not be a symlink"
            )
        atomic_write_bytes(coordinate, selection.make_pdb_string().encode("ascii"))
        derived = _read_structure(
            coordinate, label=f"component {component.component_label}"
        )
        component_records = _atom_records(derived)
        derived_records.extend(component_records)
        source_model, source_signature = models[component.component_label]
        component_groups.append(
            PhaserPlacementComponentGroup.from_content(
                component_label=component.component_label,
                ensemble_id=component.ensemble_id,
                expected_copy_count=component.expected_copy_count,
                observed_copy_count=len(chain_ids),
                placement_ordinals=ordinals,
                combined_chain_ids=chain_ids,
                source_model_sha256=sha256_file(source_model),
                source_model_polymer_sha256=source_signature,
                coordinate_path=coordinate_name,
                coordinate_sha256=sha256_file(coordinate),
                atom_count=len(component_records),
            )
        )
    if Counter(derived_records) != Counter(combined_records):
        raise PhaserPerPlacementError(
            "derived component atoms do not reconstruct the combined model"
        )
    groups_by_ensemble = {group.ensemble_id: group for group in component_groups}
    placements = tuple(
        PhaserPlacementArtifact.from_content(
            solution_number=1,
            placement_ordinal=ordinal,
            ensemble_id=ensemble_id,
            component_label=groups_by_ensemble[ensemble_id].component_label,
            solu_6dim_line_sha256=line_sha256,
            coordinate_path=groups_by_ensemble[ensemble_id].coordinate_path,
            coordinate_sha256=groups_by_ensemble[ensemble_id].coordinate_sha256,
        )
        for ordinal, (ensemble_id, line_sha256) in enumerate(entries, start=1)
    )
    try:
        inventory = PhaserPerPlacementInventory.from_content(
            adapter_version="phaser-component-coordinate-inventory-v2",
            crystal_id=request.crystal_id,
            search_id=request.search_id,
            phaser_version=request.phaser_version,
            solution_number=1,
            command_record_sha256=sha256_file(command),
            result_record_sha256=sha256_file(result),
            solution_file_path="PHASER.sol",
            solution_file_sha256=sha256_file(solution),
            combined_coordinate_path="PHASER.1.pdb",
            combined_coordinate_sha256=sha256_file(combined),
            output_command_binding=_OUTPUT_BINDING,
            placements=placements,
            component_groups=tuple(component_groups),
            combined_atom_count=len(combined_records),
            recombined_atom_count=len(derived_records),
            recombined_atom_sha256=hashlib.sha256(
                canonical_json_text(tuple(sorted(derived_records))).encode("ascii")
            ).hexdigest(),
            ordinal_mapping_status="verified_exact_sol_to_model_bound_chains",
            recombination_status="verified_exact_combined_atom_partition",
        )
    except ValidationError as error:
        raise PhaserPerPlacementError(
            "native placement inventory violates its content contract"
        ) from error
    inventory_path = output / "phaser_per_placement_inventory.json"
    atomic_write_json(inventory_path, inventory.model_dump(mode="json"))
    return PhaserPerPlacementOutput(inventory, inventory_path)


__all__ = [
    "ExpectedPhaserComponent",
    "PhaserPerPlacementError",
    "PhaserPerPlacementOutput",
    "PhaserPerPlacementRequest",
    "collect_phaser_per_placement_outputs",
]
