import csv
import json
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.review.sequence_checkpoint import (
    LiveSequenceCheckpointRequest,
    SequenceCheckpointError,
    SequenceCheckpointRequest,
    build_live_sequence_checkpoint,
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


def _live_request(
    tmp_path: Path, *, failed_seed_index: int | None = None
) -> LiveSequenceCheckpointRequest:
    source = _request(tmp_path / "source")
    refinement_records = [
        json.loads(line)
        for line in source.refinement_results_jsonl.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    sequence_records = [
        json.loads(line)
        for line in source.sequence_results_jsonl.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    stage = tmp_path / "live_t12_stage"
    (stage / "inputs").mkdir(parents=True)
    diffraction = stage / "inputs/diffraction.mtz"
    diffraction.write_text("DIFFRACTION\n", encoding="ascii")
    diffraction_sha = sha256_file(diffraction)
    result_directories: list[Path] = []
    stage_candidates: list[dict[str, object]] = []
    finalist_rows = ["seed_solution_id"]
    for seed_index, (refinement, sequence) in enumerate(
        zip(refinement_records, sequence_records, strict=True)
    ):
        seed = str(refinement["seed_solution_id"])
        finalist_rows.append(seed)
        result_directory = tmp_path / "results" / f"t12_{seed}"
        result_directory.mkdir(parents=True)
        source_directory = source.asset_root / "artifacts" / "t12" / f"t12_{seed}"
        if failed_seed_index == seed_index:
            refinement.update(
                {
                    "execution_status": "failed_tool_execution",
                    "initial_r_work": None,
                    "initial_r_free": None,
                    "final_r_work": None,
                    "final_r_free": None,
                    "rms_bonds": None,
                    "rms_angles": None,
                    "refined_model_path": None,
                    "refined_model_sha256": None,
                    "refined_mtz_path": None,
                    "refined_mtz_sha256": None,
                    "map_path": None,
                    "map_sha256": None,
                }
            )
            sequence.update(
                {
                    "execution_status": "skipped_ineligible",
                    "scored_group_count": 0,
                    "candidates": [],
                    "best_score": None,
                    "mean_score": None,
                    "score_sd": None,
                    "best_score_z": None,
                    "output_model_path": None,
                    "output_model_sha256": None,
                }
            )
        else:
            for asset in source_directory.iterdir():
                (result_directory / asset.name).write_bytes(asset.read_bytes())
        for basename, record in (
            ("brief_refinement_result", refinement),
            ("sequence_map_result", sequence),
        ):
            (result_directory / f"{basename}.json").write_text(
                json.dumps(record, sort_keys=True), encoding="utf-8"
            )
            _write_jsonl(result_directory / f"{basename}.jsonl", [record])
        (result_directory / "t12_command.json").write_text(
            json.dumps({"schema_version": "1.0", "seed_solution_id": seed}),
            encoding="utf-8",
        )
        (result_directory / "phenix.refine.log").write_text(
            f"refinement {seed}\n", encoding="ascii"
        )
        (result_directory / "phenix.sequence_from_map.log").write_text(
            f"sequence {seed}\n", encoding="ascii"
        )
        result_directories.append(result_directory)

        parent_directory = stage / "parents" / seed
        parent_directory.mkdir(parents=True)
        parent = parent_directory / "parent.pdb"
        solution = parent_directory / "phaser_solution.mtz"
        parent.write_text(f"PARENT {seed}\n", encoding="ascii")
        solution.write_text(f"PHASER {seed}\n", encoding="ascii")
        stage_candidates.append(
            {
                "seed_solution_id": seed,
                "sequence_group_id": refinement["sequence_group_id"],
                "best_supported_copy_count": refinement["input_copy_count"],
                "staged_parent_coordinate": parent.relative_to(stage).as_posix(),
                "source_coordinate_sha256": sha256_file(parent),
                "staged_solution_mtz": solution.relative_to(stage).as_posix(),
                "source_solution_mtz_sha256": sha256_file(solution),
                "refinement_mtz": diffraction.relative_to(stage).as_posix(),
                "refinement_mtz_sha256": diffraction_sha,
            }
        )
    finalists = stage / "finalists.tsv"
    finalists.write_text("\n".join(finalist_rows) + "\n", encoding="utf-8")
    copy_tsv = stage / "copy_count_report.tsv"
    copy_md = stage / "copy_count_report.md"
    copy_tsv.write_text("seed_solution_id\n", encoding="utf-8")
    copy_md.write_text("# Copy report\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "stage_id": "t12stage_live_unit",
        "profile": "normal_workflow",
        "execution_status": "completed_success",
        "seed_count": len(stage_candidates),
        "all_approved_seeds_retained": True,
        "numeric_score_filter_applied": False,
        "failed_addition_proves_absence": False,
        "finalists_sha256": sha256_file(finalists),
        "copy_report_tsv_sha256": sha256_file(copy_tsv),
        "copy_report_markdown_sha256": sha256_file(copy_md),
        "candidates": stage_candidates,
    }
    (stage / "t12_stage_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )
    return LiveSequenceCheckpointRequest(
        stage_bundle=stage,
        candidate_result_directories=tuple(result_directories),
        output_directory=tmp_path / "live_checkpoint",
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


def test_live_sequence_checkpoint_packages_normal_workflow_results(
    tmp_path: Path,
) -> None:
    output = build_live_sequence_checkpoint(_live_request(tmp_path))

    manifest = json.loads(output.manifest_json.read_text(encoding="utf-8"))
    assert output.finalist_count == 2
    assert manifest["execution_mode"] == "normal_workflow"
    assert manifest["retained_finalist_count"] == 2
    assert manifest["reviewable_finalist_count"] == 2
    assert manifest["all_finalists_retained"] is True
    assert manifest["automatic_approval"] is False
    assert len(manifest["candidate_outcomes"]) == 2
    with output.approval_template_tsv.open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle, delimiter="\t")) == []
    first_seed = manifest["candidate_outcomes"][0]["seed_solution_id"]
    assert (output.manifest_json.parent / "assets/shared/diffraction.mtz").is_file()
    assert (
        output.manifest_json.parent / f"evidence/{first_seed}/t12_command.json"
    ).is_file()
    assert (
        output.manifest_json.parent / f"assets/{first_seed}/staged_parent.pdb"
    ).is_file()


def test_live_sequence_checkpoint_retains_typed_candidate_failure(
    tmp_path: Path,
) -> None:
    output = build_live_sequence_checkpoint(
        _live_request(tmp_path, failed_seed_index=1)
    )

    manifest = json.loads(output.manifest_json.read_text(encoding="utf-8"))
    failed = next(
        candidate
        for candidate in manifest["candidate_outcomes"]
        if candidate["refinement_execution_status"] == "failed_tool_execution"
    )
    assert manifest["retained_finalist_count"] == 2
    assert manifest["reviewable_finalist_count"] == 1
    assert failed["sequence_execution_status"] == "skipped_ineligible"
    assert failed["retained"] is True
    assert len(output.full_tsv.read_text(encoding="utf-8").splitlines()) == 31
    failed_seed = failed["seed_solution_id"]
    assert (
        output.manifest_json.parent
        / f"evidence/{failed_seed}/brief_refinement_result.json"
    ).is_file()
    assert (
        output.manifest_json.parent / f"assets/{failed_seed}/staged_parent.pdb"
    ).is_file()


def test_live_sequence_checkpoint_rejects_changed_stage_parent(
    tmp_path: Path,
) -> None:
    request = _live_request(tmp_path)
    parent = next((request.stage_bundle / "parents").rglob("parent.pdb"))
    parent.write_text("changed\n", encoding="ascii")

    with pytest.raises(SequenceCheckpointError, match="checksum differs"):
        build_live_sequence_checkpoint(request)
