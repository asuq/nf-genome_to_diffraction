"""Retain exact native Phaser placement files for one known control solution.

The installed Phenix 2.1 interface probe qualified
``phaser.keywords.general.xyzout_ensemble=True`` and exact ``.sol`` output.
This parser maps the top solution's ordered ``SOLU 6DIM`` entries to native
``PHASER.1.<ordinal>.pdb`` files and checksums every retained artefact.  It runs
no external command and makes no coordinate-recombination or composition claim.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
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


def collect_phaser_per_placement_outputs(
    request: PhaserPerPlacementRequest,
) -> PhaserPerPlacementOutput:
    """Checksum and map the top solution's exact native placement artefacts."""

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

    placements: list[PhaserPlacementArtifact] = []
    observed_by_ensemble: dict[str, list[int]] = {}
    expected_paths: set[str] = set()
    for ordinal, (ensemble_id, line_sha256) in enumerate(entries, start=1):
        component = expected_by_ensemble.get(ensemble_id)
        if component is None:
            raise PhaserPerPlacementError(
                f"top Phaser solution contains an unexpected ensemble: {ensemble_id}"
            )
        coordinate_name = f"{_ROOT}.1.{ordinal}.pdb"
        coordinate = _regular_file(
            output / coordinate_name,
            label=f"placement coordinate {ordinal}",
        )
        expected_paths.add(coordinate_name)
        observed_by_ensemble.setdefault(ensemble_id, []).append(ordinal)
        placements.append(
            PhaserPlacementArtifact.from_content(
                solution_number=1,
                placement_ordinal=ordinal,
                ensemble_id=ensemble_id,
                component_label=component.component_label,
                solu_6dim_line_sha256=line_sha256,
                coordinate_path=coordinate_name,
                coordinate_sha256=sha256_file(coordinate),
            )
        )
    actual_paths = {
        path.name
        for path in output.glob(f"{_ROOT}.1.*.pdb")
        if path.is_file() and not path.is_symlink()
    }
    if actual_paths != expected_paths:
        raise PhaserPerPlacementError(
            "native per-placement PDB inventory differs from SOLU 6DIM entries"
        )

    component_groups: list[PhaserPlacementComponentGroup] = []
    for component in expected:
        ordinals = tuple(observed_by_ensemble.get(component.ensemble_id, ()))
        if len(ordinals) != component.expected_copy_count:
            raise PhaserPerPlacementError(
                f"component {component.component_label} placement count differs"
            )
        component_groups.append(
            PhaserPlacementComponentGroup.from_content(
                component_label=component.component_label,
                ensemble_id=component.ensemble_id,
                expected_copy_count=component.expected_copy_count,
                placement_ordinals=ordinals,
            )
        )
    try:
        inventory = PhaserPerPlacementInventory.from_content(
            adapter_version="phaser-per-placement-inventory-v1",
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
            placements=tuple(placements),
            component_groups=tuple(component_groups),
            ordinal_mapping_status="verified_exact_sol_to_native_pdb",
            recombination_status="not_assessed_pending_real_control",
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
