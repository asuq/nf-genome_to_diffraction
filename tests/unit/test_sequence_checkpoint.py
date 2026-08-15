import csv
import json
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.review.sequence_checkpoint import (
    SequenceCheckpointError,
    SequenceCheckpointRequest,
    build_sequence_checkpoint,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _request(tmp_path: Path) -> SequenceCheckpointRequest:
    run_id = "gtd-t12-20260815T014459Z-f50e02fe1b1a-4eff44ad"
    asset_root = tmp_path / "assets"
    refinement_records: list[dict[str, object]] = []
    sequence_records: list[dict[str, object]] = []
    for seed_index in range(2):
        seed = f"sol_{seed_index:064x}"
        directory = asset_root / "artifacts" / "t12" / f"t12_{seed}"
        directory.mkdir(parents=True)
        contents = {
            "brief_refine_001.pdb": f"PDB {seed}\n",
            "brief_refine_001.mtz": f"MTZ {seed}\n",
            "brief_refine_2mFo-DFc.ccp4": f"MAP {seed}\n",
            "sequence_from_map.pdb": f"SEQ {seed}\n",
        }
        for name, content in contents.items():
            (directory / name).write_text(content, encoding="ascii")
        refinement_id = f"refine_{seed_index:064x}"
        refinement_records.append(
            {
                "schema_version": "1.0",
                "refinement_id": refinement_id,
                "seed_solution_id": seed,
                "sequence_group_id": f"seq_{seed_index:064x}",
                "input_copy_count": 2,
                "tool_version": "2.1-6048",
                "execution_status": "completed_success",
                "initial_r_work": 0.6,
                "initial_r_free": 0.61,
                "final_r_work": 0.54,
                "final_r_free": 0.55,
                "rms_bonds": 0.01,
                "rms_angles": 1.0,
                "refined_model_path": "brief_refine_001.pdb",
                "refined_model_sha256": sha256_file(directory / "brief_refine_001.pdb"),
                "refined_mtz_path": "brief_refine_001.mtz",
                "refined_mtz_sha256": sha256_file(directory / "brief_refine_001.mtz"),
                "map_path": "brief_refine_2mFo-DFc.ccp4",
                "map_sha256": sha256_file(directory / "brief_refine_2mFo-DFc.ccp4"),
                "map_type": "2mFo-DFc",
                "map_scale": "sigma",
                "map_region": "cell",
                "command_pointer": "t12_command.json",
                "raw_log_pointer": "phenix.refine.log",
                "warnings": [],
            }
        )
        candidates = [
            {
                "schema_version": "1.0",
                "refinement_id": refinement_id,
                "rank": rank,
                "sequence_group_id": f"seq_{rank:064x}",
                "sequence_length": 50 + rank,
                "raw_score": 100.0 - rank,
                "score_z": 10.0 - rank / 10,
                "source_record_ids": [f"src_{rank:064x}"],
                "source_loci": [f"locus_{rank}"],
                "segment_ranges": [],
                "coverage": None,
                "warnings": [],
            }
            for rank in range(1, 31)
        ]
        sequence_records.append(
            {
                "schema_version": "1.0",
                "sequence_assessment_id": f"seqassess_{seed_index:064x}",
                "refinement_id": refinement_id,
                "seed_solution_id": seed,
                "execution_status": "completed_hit",
                "tool_version": "2.1-6048",
                "complete_catalogue_group_count": 40,
                "scored_group_count": 30,
                "candidates": candidates,
                "best_score": 99.0,
                "mean_score": 20.0,
                "score_sd": 8.0,
                "best_score_z": 9.9,
                "command_pointer": "t12_command.json",
                "raw_log_pointer": "phenix.sequence_from_map.log",
                "output_model_path": "sequence_from_map.pdb",
                "output_model_sha256": sha256_file(directory / "sequence_from_map.pdb"),
                "warnings": [],
            }
        )

    refinement = tmp_path / "refinement.jsonl"
    sequence = tmp_path / "sequence.jsonl"
    stage = tmp_path / "stage.json"
    job = tmp_path / "job.json"
    _write_jsonl(refinement, refinement_records)
    _write_jsonl(sequence, sequence_records)
    stage.write_text(
        json.dumps({"seed_count": 2, "parent_run_id": "gtd-m4-copy-parent"}),
        encoding="utf-8",
    )
    job.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile": "t12",
                "scheduler_state": "COMPLETED",
                "failure_class": "success",
                "exit_code": 0,
            }
        ),
        encoding="utf-8",
    )
    return SequenceCheckpointRequest(
        run_id=run_id,
        refinement_results_jsonl=refinement,
        sequence_results_jsonl=sequence,
        stage_manifest_json=stage,
        job_result_json=job,
        asset_root=asset_root,
        output_directory=tmp_path / "checkpoint",
        progress=False,
    )


def test_sequence_checkpoint_publishes_bounded_and_full_views(tmp_path: Path) -> None:
    output = build_sequence_checkpoint(_request(tmp_path))

    assert output.package_id.startswith("seqreview_")
    assert output.finalist_count == 2
    assert len(output.top10_tsv.read_text(encoding="utf-8").splitlines()) == 21
    assert len(output.top25_tsv.read_text(encoding="utf-8").splitlines()) == 51
    assert len(output.full_tsv.read_text(encoding="utf-8").splitlines()) == 61
    with output.approval_template_tsv.open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle, delimiter="\t")) == []
    manifest = json.loads(output.manifest_json.read_text(encoding="utf-8"))
    assert (
        manifest["selection_policy"] == "retain_all_finalists_and_all_scored_sequences"
    )
    assert manifest["automatic_approval"] is False
    assert manifest["top10_row_count"] == 20
    assert manifest["top25_row_count"] == 50
    assert manifest["full_scored_row_count"] == 60


def test_sequence_checkpoint_rejects_tampered_finalist_asset(tmp_path: Path) -> None:
    request = _request(tmp_path)
    asset = next(request.asset_root.rglob("brief_refine_001.pdb"))
    asset.write_text("tampered\n", encoding="ascii")

    with pytest.raises(SequenceCheckpointError, match="checksum differs"):
        build_sequence_checkpoint(request)
