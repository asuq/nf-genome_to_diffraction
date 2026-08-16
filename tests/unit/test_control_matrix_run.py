"""Scientific contract tests for the fixed 23-case matrix runtime."""

import hashlib
from pathlib import Path

from genome_to_diffraction.benchmarks.control_matrix_run import (
    _supported_first_copy_count,
    _write_runtime_inputs,
)
from genome_to_diffraction.mr.phaser import (
    PhaserRunOutput,
    _experimental_model_identity,
)
from genome_to_diffraction.schemas.results import (
    MtzPreflightRecord,
    NormalisedMrResult,
    PreflightDecision,
    ProcessedModelRecord,
)
from genome_to_diffraction.status import ExecutionStatus


def _preflight(crystal_id: str) -> MtzPreflightRecord:
    return MtzPreflightRecord(
        schema_version="1.0",
        preflight_id="preflight_test",
        crystal_id=crystal_id,
        mtz_sha256="0" * 64,
        selected_observation_labels="I,SIGI",
        selected_observation_type="intensity",
        free_flag_labels="FreeR_flag",
        free_flag_status="present",
        unit_cell=(100, 100, 100, 90, 90, 90),
        space_group="P 21 21 21",
        general_position_multiplicity=4,
        cell_volume_a3=1_000_000,
        asu_volume_a3=250_000,
        resolution_low_a=20,
        resolution_high_a=2,
        reflection_count=1_000,
        decision=PreflightDecision.PASS,
        execution_status=ExecutionStatus.COMPLETED_SUCCESS,
    )


def test_packed_tncs_first_solution_preserves_three_copy_parent(
    tmp_path: Path,
) -> None:
    result = NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id="mrhyp_" + "a" * 64,
        tool_version="Phenix 2.1-6048; Phaser 2.8.4",
        execution_status=ExecutionStatus.COMPLETED_HIT,
        llg=1601.02,
        tfz=14.2,
        placed_copy_count=3,
        packing_summary={"top_solution_packed": True},
        solution_coordinate_path="PHASER.1.pdb",
        raw_log_pointer="PHASER.log",
    )
    attempt = PhaserRunOutput(
        result=result,
        result_json=tmp_path / "result.json",
        result_jsonl=tmp_path / "result.jsonl",
        command_json=tmp_path / "command.json",
    )

    assert _supported_first_copy_count(attempt, expected_copy_count=6) == 3
    assert _supported_first_copy_count(attempt, expected_copy_count=2) == 0


def test_positive_hypothesis_retains_its_experimental_mapping_id(
    tmp_path: Path,
) -> None:
    root = tmp_path / "inputs"
    control_id = "PDB_TEST"
    sequence = "A"
    sequence_sha256 = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    proteome = root / "controls" / control_id / "proteome.faa"
    proteome.parent.mkdir(parents=True)
    proteome.write_text(">protein_a\nA\n", encoding="ascii")
    model_payload = (
        "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 20.00"
        "           N  \n"
        "ATOM      2  CA  ALA A   1       1.000   0.000   0.000  1.00 20.00"
        "           C  \n"
        "ATOM      3  C   ALA A   1       1.000   1.000   0.000  1.00 20.00"
        "           C  \n"
        "END\n"
    ).encode("ascii")
    model_path = root / "models" / "known.pdb"
    model_path.parent.mkdir()
    model_path.write_bytes(model_payload)
    manifest: dict[str, object] = {
        "positive_controls": {
            control_id: {
                "target_sequence_sha256": sequence_sha256,
                "target_protein_id": "protein_a",
                "catalogue_id": "catalogue_test",
                "annotation_provider": "test",
                "expected_asu_copy_count": 1,
                "model": {
                    "model_id": "known_model",
                    "archive_path": "models/known.pdb",
                    "sha256": hashlib.sha256(model_payload).hexdigest(),
                    "observed_sequence_sha256": sequence_sha256,
                },
            }
        },
        "wrong_model_controls": {},
    }

    runtime = _write_runtime_inputs(
        root,
        manifest,
        (_preflight(control_id),),
        tmp_path / "runtime",
    )
    model = ProcessedModelRecord.model_validate_json(
        runtime.models.read_text(encoding="utf-8")
    )

    assert _experimental_model_identity(runtime.hypotheses[0], model) == 100.0
