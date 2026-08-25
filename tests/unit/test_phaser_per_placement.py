"""Focused exact-model Phaser component-coordinate derivation tests."""

from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.cli import main
from genome_to_diffraction.mr.per_placement import (
    ExpectedPhaserComponent,
    PhaserPerPlacementError,
    PhaserPerPlacementRequest,
    collect_phaser_per_placement_outputs,
)

_A_RESIDUES = ("ALA", "GLY", "SER", "THR")
_B_RESIDUES = ("LYS", "GLU", "ASP", "VAL")


def _pdb(chains: tuple[tuple[str, tuple[str, ...]], ...]) -> str:
    lines = ["CRYST1   40.000   50.000   60.000  90.00  90.00  90.00 P 1           1\n"]
    serial = 1
    for chain_id, residues in chains:
        for residue_number, residue_name in enumerate(residues, start=1):
            lines.append(
                f"ATOM  {serial:5d}  CA  {residue_name:>3} {chain_id}"
                f"{residue_number:4d}    {float(serial + 9):8.3f}"
                f"{0.0:8.3f}{0.0:8.3f}{1.0:6.2f}{20.0:6.2f}           C\n"
            )
            serial += 1
        lines.append("TER\n")
    lines.append("END\n")
    return "".join(lines)


def _request(
    tmp_path: Path,
    *,
    copies_a: int = 2,
    copies_b: int = 2,
) -> PhaserPerPlacementRequest:
    output = tmp_path / "phaser"
    output.mkdir()
    models = tmp_path / "models"
    models.mkdir()
    source_a = models / "source_A.pdb"
    source_b = models / "source_B.pdb"
    source_a.write_text(_pdb((("M", _A_RESIDUES),)), encoding="ascii")
    source_b.write_text(_pdb((("N", _B_RESIDUES),)), encoding="ascii")
    combined_chains: list[tuple[str, tuple[str, ...]]] = []
    next_chain = 0
    for copy_index in range(max(copies_a, copies_b)):
        if copy_index < copies_b:
            combined_chains.append((chr(ord("A") + next_chain), _B_RESIDUES))
            next_chain += 1
        if copy_index < copies_a:
            combined_chains.append((chr(ord("A") + next_chain), _A_RESIDUES))
            next_chain += 1
    (output / "PHASER.1.pdb").write_text(_pdb(tuple(combined_chains)), encoding="ascii")
    entries = ["fixed_parent", *("search_partner" for _ in range(copies_b))]
    lines = ["SOLU SET LLG=100\n"]
    lines.extend(
        f"SOLU 6DIM ENSE {ensemble} EULER {index} 0 0 FRAC 0 0 0 BFAC 0\n"
        for index, ensemble in enumerate(entries, start=1)
    )
    (output / "PHASER.sol").write_text("".join(lines), encoding="ascii")
    command = output / "phaser_command.json"
    command.write_text('{"command":"phenix.phaser"}\n', encoding="ascii")
    result = output / "partner_search_result.json"
    result.write_text('{"execution_status":"completed_hit"}\n', encoding="ascii")
    return PhaserPerPlacementRequest(
        crystal_id="3U7Q",
        search_id="partner_test",
        phaser_version="2.8.3",
        output_directory=output,
        command_record=command,
        result_record=result,
        expected_components=(
            ExpectedPhaserComponent("A", "fixed_parent", copies_a),
            ExpectedPhaserComponent("B", "search_partner", copies_b),
        ),
        component_models=(("A", source_a), ("B", source_b)),
    )


def test_maps_exact_model_sequences_and_recombines_all_atoms(tmp_path: Path) -> None:
    request = _request(tmp_path)

    first = collect_phaser_per_placement_outputs(request)
    first_bytes = first.inventory_json.read_bytes()
    second = collect_phaser_per_placement_outputs(request)

    assert second.inventory_json.read_bytes() == first_bytes
    assert second.inventory.inventory_id == first.inventory.inventory_id
    assert tuple(item.ensemble_id for item in first.inventory.placements) == (
        "fixed_parent",
        "search_partner",
        "search_partner",
    )
    assert tuple(
        group.component_label for group in first.inventory.component_groups
    ) == ("A", "B")
    assert first.inventory.component_groups[0].placement_ordinals == (1,)
    assert first.inventory.component_groups[0].combined_chain_ids == ("B", "D")
    assert first.inventory.component_groups[0].observed_copy_count == 2
    assert first.inventory.component_groups[1].placement_ordinals == (2, 3)
    assert first.inventory.component_groups[1].combined_chain_ids == ("A", "C")
    assert first.inventory.ordinal_mapping_status == (
        "verified_exact_sol_to_model_bound_chains"
    )
    assert first.inventory.recombination_status == (
        "verified_exact_combined_atom_partition"
    )
    assert first.inventory.can_create_fixed_component_evidence is True
    assert first.inventory.combined_atom_count == 16
    assert first.inventory.recombined_atom_count == 16
    assert (request.output_directory / "component_A.pdb").is_file()
    assert (request.output_directory / "component_B.pdb").is_file()


def test_combined_coordinate_mutation_changes_inventory_identity(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path, copies_a=1, copies_b=1)
    first = collect_phaser_per_placement_outputs(request).inventory
    combined = request.output_directory / "PHASER.1.pdb"
    payload = combined.read_bytes()
    assert b"  10.000" in payload
    combined.write_bytes(payload.replace(b"  10.000", b"  11.000", 1))

    second = collect_phaser_per_placement_outputs(request).inventory

    assert second.inventory_id != first.inventory_id
    assert second.recombined_atom_sha256 != first.recombined_atom_sha256


def test_cli_writes_the_verified_component_inventory(tmp_path: Path) -> None:
    request = _request(tmp_path, copies_a=1, copies_b=1)

    status = main(
        [
            "--no-progress",
            "mr",
            "collect-per-placement",
            "--crystal-id",
            request.crystal_id,
            "--search-id",
            request.search_id,
            "--phaser-version",
            request.phaser_version,
            "--output-directory",
            str(request.output_directory),
            "--command-record",
            str(request.command_record),
            "--result-record",
            str(request.result_record),
            "--expected-component",
            "A:fixed_parent:1",
            "--expected-component",
            "B:search_partner:1",
            "--component-model",
            f"A:{request.component_models[0][1]}",
            "--component-model",
            f"B:{request.component_models[1][1]}",
        ]
    )

    assert status == 0
    assert (request.output_directory / "phaser_per_placement_inventory.json").is_file()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("missing_sol", "solution file"),
        ("missing_model", "source model"),
        ("wrong_expected_count", "placement count differs"),
        ("unexpected_ensemble", "unexpected ensemble"),
        ("unmatched_chain", "matches no component"),
        ("indistinguishable_models", "indistinguishable"),
        ("duplicate_fixed_solution", "ambiguous"),
    ),
)
def test_refuses_incomplete_ambiguous_or_misbound_components(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    request = _request(tmp_path, copies_a=1, copies_b=1)
    if mutation == "missing_sol":
        (request.output_directory / "PHASER.sol").unlink()
    elif mutation == "missing_model":
        request.component_models[1][1].unlink()
    elif mutation == "wrong_expected_count":
        request = replace(
            request,
            expected_components=(
                ExpectedPhaserComponent("A", "fixed_parent", 1),
                ExpectedPhaserComponent("B", "search_partner", 2),
            ),
        )
    elif mutation == "unexpected_ensemble":
        solution = request.output_directory / "PHASER.sol"
        solution.write_text(
            solution.read_text(encoding="ascii").replace(
                "search_partner",
                "unknown_component",
            ),
            encoding="ascii",
        )
    elif mutation == "unmatched_chain":
        combined = request.output_directory / "PHASER.1.pdb"
        combined.write_text(
            combined.read_text(encoding="ascii").replace("LYS", "TYR", 1),
            encoding="ascii",
        )
    elif mutation == "indistinguishable_models":
        request = replace(
            request,
            component_models=(
                request.component_models[0],
                ("B", request.component_models[0][1]),
            ),
        )
    else:
        solution = request.output_directory / "PHASER.sol"
        solution.write_text(
            solution.read_text(encoding="ascii").replace(
                "SOLU 6DIM ENSE search_partner",
                "SOLU 6DIM ENSE fixed_parent EULER 0 0 0 FRAC 0 0 0 BFAC 0\n"
                "SOLU 6DIM ENSE search_partner",
            ),
            encoding="ascii",
        )

    with pytest.raises(PhaserPerPlacementError, match=message):
        collect_phaser_per_placement_outputs(request)
