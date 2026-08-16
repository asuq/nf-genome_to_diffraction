"""Protect the measured crowded-cluster control-matrix resource boundary."""

from pathlib import Path

from genome_to_diffraction.benchmarks.control_matrix_run import (
    ControlMatrixRunRequest,
    _bounded_worker_count,
)


def test_control_matrix_defaults_to_four_workers_with_eight_threads(
    tmp_path: Path,
) -> None:
    request = ControlMatrixRunRequest(
        import_root=tmp_path / "inputs",
        phenix_manifest=tmp_path / "phenix.json",
        output_directory=tmp_path / "output",
    )

    assert request.threads == 8
    assert _bounded_worker_count(18) == 4
    assert _bounded_worker_count(4) == 4
    assert _bounded_worker_count(1) == 1
    assert _bounded_worker_count(0) == 1
