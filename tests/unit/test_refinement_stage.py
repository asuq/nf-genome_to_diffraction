"""Tests for the fixed retained-parent T12 staging boundary."""

import json
from pathlib import Path

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.refinement.stage import T12StageRequest, stage_t12_inputs
from genome_to_diffraction.schemas.results import AdditionalCopyResult
from genome_to_diffraction.status import ExecutionStatus


def test_stage_t12_inputs_retains_supported_copy_two_parent(tmp_path: Path) -> None:
    parent = tmp_path / "gtd-m4-copy-test"
    qualification = parent / "artifacts/qualification"
    common = parent / "artifacts/m4-copy-inputs/inputs"
    qualification.mkdir(parents=True)
    common.mkdir(parents=True)
    seed = "sol_" + "a" * 64
    sequence_id = "seq_f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e"
    candidate = parent / "artifacts/m4-copy/copy-two" / f"additional_copy_{seed}"
    candidate.mkdir(parents=True)
    coordinate = candidate / "PHASER.1.pdb"
    mtz = candidate / "PHASER.1.mtz"
    coordinate.write_text("REMARK PHASER ENSEMBLE MODEL 1\n", encoding="ascii")
    mtz.write_bytes(b"test mtz")
    result = AdditionalCopyResult(
        schema_version="1.0",
        attempt_id="addcopy_test",
        review_id="review_test",
        seed_solution_id=seed,
        parent_solution_id=seed,
        child_solution_id="copystate_test",
        hypothesis_id="mrhyp_test",
        sequence_group_id=sequence_id,
        parent_copy_count=1,
        attempted_copy_number=2,
        expected_copy_count=6,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        llg=60.0,
        llg_delta_from_parent=20.0,
        tfz=7.0,
        phaser_placement_count=2,
        top_solution_packed=True,
        additional_copy_supported=True,
        best_supported_copy_count=2,
        output_coordinate_path="PHASER.1.pdb",
        output_coordinate_sha256=sha256_file(coordinate),
        output_mtz_path="PHASER.1.mtz",
        output_mtz_sha256=sha256_file(mtz),
        raw_log_pointer="PHASER.log",
        command_pointer="phaser_command.json",
    )
    (qualification / "m4-copy-results.jsonl").write_text(
        result.model_dump_json() + "\n", encoding="utf-8"
    )
    (qualification / "m4-copy-summary.json").write_text(
        json.dumps(
            {
                "attempted_seed_count": 1,
                "all_parents_retained": True,
                "all_resume_processes_cached": True,
            }
        ),
        encoding="utf-8",
    )
    (qualification / "m4-copy-resume-check.json").write_text(
        json.dumps({"all_candidate_series_cached": True}), encoding="utf-8"
    )
    (common / "mtz.mtz").write_bytes(b"original diffraction mtz")
    original_mtz_sha = sha256_file(common / "mtz.mtz")
    (parent / "artifacts/m4-copy-inputs/m4_copy_stage_manifest.json").write_text(
        json.dumps({"inputs": {"mtz": {"sha256": original_mtz_sha}}}),
        encoding="utf-8",
    )
    fixtures = Path(__file__).parents[1] / "fixtures/stubs"
    (common / "sequence_groups.jsonl").write_bytes(
        (fixtures / "sequence_groups.jsonl").read_bytes()
    )
    selected_preflight = json.loads(
        (fixtures / "mtz_preflight.jsonl").read_text(encoding="utf-8")
    )
    selected_preflight["mtz_sha256"] = original_mtz_sha
    other_preflight = {**selected_preflight, "preflight_id": "other_preflight"}
    other_preflight["mtz_sha256"] = "1" * 64
    (common / "preflight.jsonl").write_text(
        json.dumps(selected_preflight) + "\n" + json.dumps(other_preflight) + "\n",
        encoding="utf-8",
    )
    (common / "phenix_manifest.json").write_text("{}\n", encoding="ascii")

    output = stage_t12_inputs(
        T12StageRequest(
            parent_run=parent,
            source_records_jsonl=fixtures / "source_records.jsonl",
            output_directory=tmp_path / "stage",
            expected_seed_count=1,
            progress=False,
        )
    )

    assert output.seed_count == 1
    assert output.finalists.read_text(encoding="utf-8").count("\n") == 2
    manifest = json.loads(output.manifest.read_text(encoding="utf-8"))
    assert manifest["selection_policy"] == "retain_all_supported_copy_two_parents"
    assert manifest["candidates"][0]["source_coordinate_sha256"] == sha256_file(
        coordinate
    )
    fields = output.finalists.read_text(encoding="utf-8").splitlines()[1].split("\t")
    assert Path(fields[5]).read_bytes() == b"original diffraction mtz"
    assert fields[6] == original_mtz_sha
    assert fields[8] == selected_preflight["selected_observation_labels"]
    assert manifest["parent_mtz_free_flag_status"] == "present"
    assert manifest["candidates"][0]["source_mtz_sha256"] == sha256_file(mtz)
