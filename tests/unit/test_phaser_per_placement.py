"""Focused native Phaser placement-output mapping tests."""

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


def _request(tmp_path: Path, *, copies_a: int = 2, copies_b: int = 2):
    output = tmp_path / "phaser"
    output.mkdir()
    entries = ["fixed_parent"] * copies_a + ["search_partner"] * copies_b
    lines = ["SOLU SET LLG=100\n"]
    for index, ensemble in enumerate(entries, start=1):
        lines.append(f"SOLU 6DIM ENSE {ensemble} EULER {index} 0 0 FRAC 0 0 0 BFAC 0\n")
        (output / f"PHASER.1.{index}.pdb").write_text(
            f"REMARK ENSEMBLE {ensemble}\nEND\n",
            encoding="ascii",
        )
    (output / "PHASER.sol").write_text("".join(lines), encoding="ascii")
    (output / "PHASER.1.pdb").write_text("MODEL\nEND\n", encoding="ascii")
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
    )


def test_maps_exact_solu_ordinals_and_is_byte_stable(tmp_path: Path) -> None:
    request = _request(tmp_path)

    first = collect_phaser_per_placement_outputs(request)
    first_bytes = first.inventory_json.read_bytes()
    second = collect_phaser_per_placement_outputs(request)

    assert second.inventory_json.read_bytes() == first_bytes
    assert second.inventory.inventory_id == first.inventory.inventory_id
    assert tuple(item.ensemble_id for item in first.inventory.placements) == (
        "fixed_parent",
        "fixed_parent",
        "search_partner",
        "search_partner",
    )
    assert tuple(
        group.component_label for group in first.inventory.component_groups
    ) == (
        "A",
        "B",
    )
    assert first.inventory.component_groups[0].placement_ordinals == (1, 2)
    assert first.inventory.component_groups[1].placement_ordinals == (3, 4)
    assert first.inventory.ordinal_mapping_status == (
        "verified_exact_sol_to_native_pdb"
    )
    assert first.inventory.recombination_status == ("not_assessed_pending_real_control")
    assert first.inventory.can_create_fixed_component_evidence is False


def test_coordinate_mutation_changes_inventory_identity(tmp_path: Path) -> None:
    request = _request(tmp_path, copies_a=1, copies_b=1)
    first = collect_phaser_per_placement_outputs(request).inventory
    coordinate = request.output_directory / "PHASER.1.2.pdb"
    coordinate.write_bytes(coordinate.read_bytes() + b"REMARK changed\n")

    second = collect_phaser_per_placement_outputs(request).inventory

    assert second.inventory_id != first.inventory_id
    assert second.placements[1].coordinate_sha256 != (
        first.placements[1].coordinate_sha256
    )


def test_cli_writes_the_content_addressed_inventory(tmp_path: Path) -> None:
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
        ]
    )

    assert status == 0
    assert (request.output_directory / "phaser_per_placement_inventory.json").is_file()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("missing_sol", "solution file"),
        ("missing_placement", "placement coordinate 2"),
        ("extra_placement", "inventory differs"),
        ("wrong_expected_count", "placement count differs"),
        ("unexpected_ensemble", "unexpected ensemble"),
    ),
)
def test_refuses_incomplete_or_misbound_native_outputs(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    request = _request(tmp_path, copies_a=1, copies_b=1)
    if mutation == "missing_sol":
        (request.output_directory / "PHASER.sol").unlink()
    elif mutation == "missing_placement":
        (request.output_directory / "PHASER.1.2.pdb").unlink()
    elif mutation == "extra_placement":
        (request.output_directory / "PHASER.1.3.pdb").write_text(
            "END\n",
            encoding="ascii",
        )
    elif mutation == "wrong_expected_count":
        request = replace(
            request,
            expected_components=(
                ExpectedPhaserComponent("A", "fixed_parent", 1),
                ExpectedPhaserComponent("B", "search_partner", 2),
            ),
        )
    else:
        solution = request.output_directory / "PHASER.sol"
        solution.write_text(
            solution.read_text(encoding="ascii").replace(
                "search_partner",
                "unknown_component",
            ),
            encoding="ascii",
        )

    with pytest.raises(PhaserPerPlacementError, match=message):
        collect_phaser_per_placement_outputs(request)
