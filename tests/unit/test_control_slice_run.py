"""Scientific acceptance tests for the fixed six-case runtime."""

from pathlib import Path

from genome_to_diffraction.benchmarks.control_slice_run import (
    _pdb_sequence,
    _positive_control_retained,
)
from genome_to_diffraction.schemas.results import NormalisedMrResult
from genome_to_diffraction.status import ExecutionStatus


def _packed_result(hypothesis_id: str) -> NormalisedMrResult:
    return NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=hypothesis_id,
        tool_version="test",
        execution_status=ExecutionStatus.COMPLETED_HIT,
        placed_copy_count=1,
        packing_summary={"top_solution_packed": True},
        raw_log_pointer="phaser.log",
    )


def test_one_copy_positive_accepts_packed_first_copy() -> None:
    assert _positive_control_retained(
        expected_copy_count=1,
        related=[_packed_result("one")],
        supported_copy_two_hypotheses=set(),
    )


def test_two_copy_positive_requires_supported_second_copy() -> None:
    result = _packed_result("two")
    assert not _positive_control_retained(
        expected_copy_count=2,
        related=[result],
        supported_copy_two_hypotheses=set(),
    )
    assert _positive_control_retained(
        expected_copy_count=2,
        related=[result],
        supported_copy_two_hypotheses={"two"},
    )


def test_modified_amino_acid_model_sequence_is_mass_compatible(
    tmp_path: Path,
) -> None:
    model = tmp_path / "mse.pdb"
    model.write_text(
        "HETATM    1  N   MSE A   1       0.000   0.000   0.000  1.00 20.00"
        "           N  \n"
        "HETATM    2  CA  MSE A   1       1.000   0.000   0.000  1.00 20.00"
        "           C  \n"
        "HETATM    3  C   MSE A   1       1.000   1.000   0.000  1.00 20.00"
        "           C  \n"
        "END\n",
        encoding="ascii",
    )

    sequence, _, atom_count = _pdb_sequence(model)

    assert sequence == "M"
    assert atom_count == 3


def test_kynurenine_model_residue_is_retained_as_tryptophan(tmp_path: Path) -> None:
    model = tmp_path / "kyn.pdb"
    model.write_text(
        "HETATM    1  N   KYN A   1       0.000   0.000   0.000  1.00 20.00"
        "           N  \n"
        "HETATM    2  CA  KYN A   1       1.000   0.000   0.000  1.00 20.00"
        "           C  \n"
        "HETATM    3  C   KYN A   1       1.000   1.000   0.000  1.00 20.00"
        "           C  \n"
        "END\n",
        encoding="ascii",
    )

    sequence, _, atom_count = _pdb_sequence(model)

    assert sequence == "W"
    assert atom_count == 3
