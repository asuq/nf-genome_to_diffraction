"""Protect retirement of the direct control-matrix scheduler."""

from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.control_matrix_run import (
    ControlMatrixRunError,
    ControlMatrixRunRequest,
    run_control_matrix,
)


def test_control_matrix_fails_before_reading_inputs_with_nextflow_migration(
    tmp_path: Path,
) -> None:
    request = ControlMatrixRunRequest(
        import_root=tmp_path / "inputs",
        phenix_manifest=tmp_path / "phenix.json",
        output_directory=tmp_path / "output",
    )

    with pytest.raises(ControlMatrixRunError, match="Nextflow channel item"):
        run_control_matrix(request)

    assert not request.output_directory.exists()
