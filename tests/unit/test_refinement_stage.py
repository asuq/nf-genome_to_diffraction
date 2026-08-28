"""Tests for fixed and normal-workflow retained-parent T12 boundaries."""

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.mr.stage_add_copy import PhaseIIISeedStageEvidence
from genome_to_diffraction.refinement.stage import (
    LiveT12StageRequest,
    T12StageError,
    T12StageRequest,
    stage_live_t12_inputs,
    stage_t12_inputs,
)
from genome_to_diffraction.schemas.manifests import PrototypeProfile
from genome_to_diffraction.schemas.results import (
    AdditionalCopyResult,
    CopyCountAssessment,
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    NormalisedMrResult,
)
from genome_to_diffraction.status import ExecutionStatus

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
SEED_ID = "sol_" + "c" * 64
HYPOTHESIS_ID = "mrhyp_" + "d" * 64
GROUP_ID = "seq_f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e"
REVIEW_ID = "rev_" + "b" * 64


def _write_seed_table(path: Path, expected_copy_count: int, model: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "seed_solution_id",
                "search_model",
                "search_model_sha256",
                "expected_copy_count",
                "requires_additional_copy",
            )
        )
        if path.name == "approved_seeds.tsv" or expected_copy_count > 1:
            writer.writerow(
                (
                    SEED_ID,
                    str(model),
                    sha256_file(model),
                    expected_copy_count,
                    str(expected_copy_count > 1).lower(),
                )
            )


def _write_copy_series(
    root: Path,
    *,
    expected_copy_count: int,
    outcome: str,
) -> Path:
    root.mkdir()
    attempts: list[tuple[AdditionalCopyResult, Path]] = []
    parent_id = SEED_ID
    parent_count = 1

    def add_attempt(*, supported: bool, status: ExecutionStatus) -> None:
        nonlocal parent_id, parent_count
        attempted = parent_count + 1
        attempt_root = root if attempted == 2 else root / f"copy_{attempted:02d}"
        attempt_root.mkdir(exist_ok=True)
        coordinate_sha = mtz_sha = child_id = None
        coordinate_path = mtz_path = None
        if supported:
            coordinate = attempt_root / "PHASER.1.pdb"
            coordinate.write_text(
                f"REMARK supported copy {attempted}\n", encoding="ascii"
            )
            result_mtz = attempt_root / "PHASER.1.mtz"
            result_mtz.write_bytes(f"solution mtz {attempted}".encode("ascii"))
            coordinate_path = coordinate.name
            mtz_path = result_mtz.name
            coordinate_sha = sha256_file(coordinate)
            mtz_sha = sha256_file(result_mtz)
            child_id = f"copystate_{attempted}"
        (attempt_root / "PHASER.log").write_text(
            f"attempt {attempted}\n", encoding="ascii"
        )
        (attempt_root / "phaser_command.json").write_text(
            json.dumps({"attempted_copy_number": attempted}) + "\n",
            encoding="ascii",
        )
        result = AdditionalCopyResult(
            schema_version="1.0",
            attempt_id=f"addcopy_{attempted}",
            review_id=REVIEW_ID,
            seed_solution_id=SEED_ID,
            parent_solution_id=parent_id,
            child_solution_id=child_id,
            hypothesis_id=HYPOTHESIS_ID,
            sequence_group_id=GROUP_ID,
            parent_copy_count=parent_count,
            attempted_copy_number=attempted,
            expected_copy_count=expected_copy_count,
            execution_status=status,
            llg=80.0 if supported else None,
            llg_delta_from_parent=40.0 if supported else None,
            tfz=7.0 if supported else None,
            phaser_placement_count=attempted if supported else 0,
            top_solution_packed=supported,
            additional_copy_supported=supported,
            best_supported_copy_count=attempted if supported else parent_count,
            output_coordinate_path=coordinate_path,
            output_coordinate_sha256=coordinate_sha,
            output_mtz_path=mtz_path,
            output_mtz_sha256=mtz_sha,
            raw_log_pointer="PHASER.log",
            command_pointer="phaser_command.json",
            rejection_reason=None if supported else "typed_addition_not_supported",
        )
        result_path = attempt_root / "additional_copy_result.jsonl"
        result_path.write_text(f"{canonical_json_text(result)}\n", encoding="utf-8")
        attempts.append((result, result_path))
        if supported:
            parent_id = str(child_id)
            parent_count = attempted

    if outcome == "supported":
        add_attempt(supported=True, status=ExecutionStatus.COMPLETED_HIT)
    elif outcome == "unsupported_after_supported":
        add_attempt(supported=True, status=ExecutionStatus.COMPLETED_HIT)
        add_attempt(supported=False, status=ExecutionStatus.COMPLETED_NO_HIT)
    elif outcome == "failed":
        add_attempt(supported=False, status=ExecutionStatus.FAILED_TOOL_EXECUTION)
    else:
        raise AssertionError(f"unknown series outcome: {outcome}")

    aggregate = root / "additional_copy_series_results.jsonl"
    aggregate.write_text(
        "".join(f"{canonical_json_text(result)}\n" for result, _ in attempts),
        encoding="utf-8",
    )
    final = attempts[-1][0]
    stop_reason = (
        "expected_copy_count_reached"
        if final.additional_copy_supported
        else "additional_copy_not_supported"
    )
    (root / "additional_copy_series_summary.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "series_id": "copyseries_test",
                "adapter_version": "phenix-add-copy-mr-v1",
                "seed_solution_id": SEED_ID,
                "attempt_ids": [result.attempt_id for result, _ in attempts],
                "expected_copy_count": expected_copy_count,
                "attempt_count": len(attempts),
                "attempted_copy_numbers": [
                    result.attempted_copy_number for result, _ in attempts
                ],
                "best_supported_copy_count": final.best_supported_copy_count,
                "reached_expected_copy_count": (
                    final.best_supported_copy_count == expected_copy_count
                ),
                "stop_reason": stop_reason,
                "parent_retained": True,
                "failed_addition_proves_absence": False,
                "result_paths": [
                    path.relative_to(root).as_posix() for _, path in attempts
                ],
                "result_sha256": [sha256_file(path) for _, path in attempts],
            }
        ),
        encoding="utf-8",
    )
    return root


def _live_request(
    tmp_path: Path,
    *,
    expected_copy_count: int,
    outcome: str | None,
    placed_copy_count: int = 1,
) -> LiveT12StageRequest:
    review = tmp_path / "review"
    assets = review / "assets" / SEED_ID
    assets.mkdir(parents=True)
    root_coordinate = assets / "PHASER.1.pdb"
    root_coordinate.write_text("REMARK first copy\n", encoding="ascii")
    root_solution_mtz = assets / "PHASER.1.mtz"
    root_solution_mtz.write_bytes(b"first-copy solution mtz")
    normalised_result = assets / "normalised_mr_result.jsonl"
    first_result = NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=HYPOTHESIS_ID,
        tool_version="2.1-6048",
        execution_status=ExecutionStatus.COMPLETED_HIT,
        llg=100.0,
        tfz=10.0,
        placed_copy_count=placed_copy_count,
        packing_summary={
            "top_solution_packed": True,
            "packed_solution_count": 1,
        },
        solution_coordinate_path="PHASER.1.pdb",
        solution_coordinate_sha256=sha256_file(root_coordinate),
        output_mtz_path="PHASER.1.mtz",
        output_mtz_sha256=sha256_file(root_solution_mtz),
        raw_log_pointer="PHASER.log",
    )
    normalised_result.write_text(
        f"{canonical_json_text(first_result)}\n",
        encoding="utf-8",
    )
    package_id = "reviewpkg_" + "a" * 64
    review_manifest = review / "mr_seed_review_manifest.json"
    review_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "package_id": package_id,
                "items": [
                    {
                        "solution_id": SEED_ID,
                        "hypothesis_id": HYPOTHESIS_ID,
                        "sequence_group_id": GROUP_ID,
                        "copied_assets": {
                            "solution_coordinate": (
                                root_coordinate.relative_to(review).as_posix()
                            ),
                            "output_mtz": root_solution_mtz.relative_to(
                                review
                            ).as_posix(),
                            "normalised_result": normalised_result.relative_to(
                                review
                            ).as_posix(),
                        },
                        "copied_asset_sha256": {
                            "solution_coordinate": sha256_file(root_coordinate),
                            "output_mtz": sha256_file(root_solution_mtz),
                            "normalised_result": sha256_file(normalised_result),
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=HYPOTHESIS_ID,
        crystal_id="test_crystal_01",
        sequence_group_id=GROUP_ID,
        model_id="model_" + "a" * 64,
        copy_count_expected=expected_copy_count,
        copy_number_to_search=placed_copy_count,
        fixed_solution_id=None,
        space_group="P 21 21 21",
        obs_labels="I,SIGI",
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.PILOT,
        priority_features={},
        status=MrHypothesisStatus.QUEUED,
    )
    hypotheses = tmp_path / "hypotheses.jsonl"
    hypotheses.write_text(f"{canonical_json_text(hypothesis)}\n", encoding="utf-8")

    approved = tmp_path / "approved-stage"
    models = approved / "models"
    models.mkdir(parents=True)
    staged_model = models / "model.pdb"
    staged_model.write_bytes(root_coordinate.read_bytes())
    approved_seeds = approved / "approved_seeds.tsv"
    additional_seeds = approved / "additional_copy_seeds.tsv"
    _write_seed_table(approved_seeds, expected_copy_count, staged_model)
    _write_seed_table(additional_seeds, expected_copy_count, staged_model)
    decisions = approved / "approved_mr_seeds.tsv"
    decisions.write_text("explicit decisions\n", encoding="ascii")
    validation = approved / "validated_mr_seed_decisions.json"
    validation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "review_id": REVIEW_ID,
                "checkpoint": "mr_seed",
                "package_id": package_id,
                "package_manifest_sha256": sha256_file(review_manifest),
                "decisions_sha256": sha256_file(decisions),
                "approved_solution_ids": [SEED_ID],
                "execution_status": "completed_success",
            }
        ),
        encoding="utf-8",
    )
    (approved / "live_m4_stage_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "stage_id": "m4stage_test",
                "stage_kind": "normal_workflow_post_mr_seed",
                "review_id": REVIEW_ID,
                "review_package_id": package_id,
                "review_manifest_sha256": sha256_file(review_manifest),
                "decisions_sha256": sha256_file(decisions),
                "hypotheses_sha256": sha256_file(hypotheses),
                "approved_solution_ids": [SEED_ID],
                "model_sources": {
                    SEED_ID: {
                        "hypothesis_id": HYPOTHESIS_ID,
                        "sequence_group_id": GROUP_ID,
                        "expected_copy_count": expected_copy_count,
                        "requires_additional_copy": expected_copy_count > 1,
                        "source_solution_coordinate": root_coordinate.relative_to(
                            review
                        ).as_posix(),
                        "original_first_copy_model_sha256": "a" * 64,
                        "staged_search_model": staged_model.relative_to(
                            approved
                        ).as_posix(),
                        "staged_search_model_sha256": sha256_file(staged_model),
                    }
                },
                "approved_seed_count": 1,
                "additional_copy_seed_count": int(expected_copy_count > 1),
                "all_approved_seeds_retained": True,
                "numeric_score_filter_applied": False,
                "approved_seeds_sha256": sha256_file(approved_seeds),
                "additional_copy_seeds_sha256": sha256_file(additional_seeds),
                "validation_sha256": sha256_file(validation),
                "execution_status": "completed_success",
            }
        ),
        encoding="utf-8",
    )

    diffraction_mtz = tmp_path / "diffraction.mtz"
    diffraction_mtz.write_bytes(b"original FreeR-bearing diffraction MTZ")
    preflight = json.loads((STUBS / "mtz_preflight.jsonl").read_text(encoding="utf-8"))
    preflight["mtz_sha256"] = sha256_file(diffraction_mtz)
    preflights = tmp_path / "preflight.jsonl"
    preflights.write_text(json.dumps(preflight) + "\n", encoding="utf-8")
    phenix = tmp_path / "phenix.json"
    phenix.write_text("{}\n", encoding="ascii")
    result_directories = (
        (
            _write_copy_series(
                tmp_path / "additional-copy-results",
                expected_copy_count=expected_copy_count,
                outcome=outcome,
            ),
        )
        if outcome is not None
        else ()
    )
    return LiveT12StageRequest(
        approved_stage=approved,
        review_package=review,
        additional_copy_results=result_directories,
        hypotheses_jsonl=hypotheses,
        sequence_groups_jsonl=STUBS / "sequence_groups.jsonl",
        source_records_jsonl=STUBS / "source_records.jsonl",
        preflight_jsonl=preflights,
        diffraction_mtz=diffraction_mtz,
        phenix_manifest=phenix,
        output_directory=tmp_path / "live-t12",
        progress=False,
    )


@pytest.mark.parametrize(
    (
        "expected_copy_count",
        "outcome",
        "expected_best_count",
        "expected_terminal_reason",
        "expected_source_kind",
        "expected_final_status",
    ),
    [
        (
            1,
            None,
            1,
            "already_at_expected_copy_count",
            "first_copy_review_solution",
            None,
        ),
        (
            2,
            "supported",
            2,
            "expected_copy_count_reached",
            "supported_additional_copy",
            "completed_hit",
        ),
        (
            3,
            "unsupported_after_supported",
            2,
            "additional_copy_not_supported",
            "supported_additional_copy",
            "completed_no_hit",
        ),
        (
            2,
            "failed",
            1,
            "additional_copy_not_supported",
            "first_copy_review_solution",
            "failed_tool_execution",
        ),
    ],
)
def test_live_stage_retains_best_supported_parent_for_every_typed_outcome(
    tmp_path: Path,
    expected_copy_count: int,
    outcome: str | None,
    expected_best_count: int,
    expected_terminal_reason: str,
    expected_source_kind: str,
    expected_final_status: str | None,
) -> None:
    request = _live_request(
        tmp_path,
        expected_copy_count=expected_copy_count,
        outcome=outcome,
    )

    output = stage_live_t12_inputs(request)

    assert output.seed_count == 1
    manifest = json.loads(output.manifest.read_text(encoding="utf-8"))
    assert manifest["all_approved_seeds_retained"] is True
    assert manifest["numeric_score_filter_applied"] is False
    assert manifest["failed_addition_proves_absence"] is False
    candidate = manifest["candidates"][0]
    assert candidate["best_supported_copy_count"] == expected_best_count
    assert candidate["terminal_reason"] == expected_terminal_reason
    assert candidate["retained_state_source"] == expected_source_kind
    assert candidate["final_addition_execution_status"] == expected_final_status
    assert candidate["parent_retained"] is True
    assert candidate["failed_addition_proves_absence"] is False

    finalist = output.finalists.read_text(encoding="utf-8").splitlines()[1].split("\t")
    assert finalist[2] == str(expected_best_count)
    assert Path(finalist[5]).read_bytes() == b"original FreeR-bearing diffraction MTZ"
    assert finalist[6] == sha256_file(request.diffraction_mtz)
    retained_coordinate = Path(finalist[3]).read_text(encoding="ascii")
    if expected_source_kind == "supported_additional_copy":
        assert retained_coordinate == "REMARK supported copy 2\n"
    else:
        assert retained_coordinate == "REMARK first copy\n"
    assert "does not prove that the copy is absent" in (
        output.copy_report_markdown.read_text(encoding="utf-8")
    )


def test_phase3_live_stage_uses_only_canonical_seed_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = _live_request(tmp_path, expected_copy_count=2, outcome="supported")
    assert legacy.review_package is not None
    review_root = legacy.review_package
    review_manifest = review_root / "mr_seed_review_manifest.json"
    review_document = json.loads(review_manifest.read_text(encoding="utf-8"))
    approved_root = legacy.approved_stage
    legacy_stage = json.loads(
        (approved_root / "live_m4_stage_manifest.json").read_text(encoding="utf-8")
    )
    phase3_model_sources = json.loads(json.dumps(legacy_stage["model_sources"]))
    phase3_model_sources[SEED_ID]["placed_copy_count"] = 1
    phase3_model_sources[SEED_ID]["requires_additional_copy"] = True
    stage_manifest = approved_root / "phase3_seed_stage_manifest.json"
    stage_manifest.write_text(
        json.dumps(
            {
                "stage_id": "phase3seedstage_" + "1" * 64,
                "approved_seed_count": 1,
                "additional_copy_seed_count": 1,
                "hypotheses_sha256": sha256_file(legacy.hypotheses_jsonl),
                "model_sources": phase3_model_sources,
            }
        ),
        encoding="utf-8",
    )
    evidence = PhaseIIISeedStageEvidence(
        stage_id="phase3seedstage_" + "1" * 64,
        review_id=REVIEW_ID,
        approved_solution_ids=(SEED_ID,),
        root=approved_root,
        review_root=review_root,
        review_manifest=review_manifest,
        review_document=review_document,
        model_sources=phase3_model_sources,
    )
    monkeypatch.setattr(
        "genome_to_diffraction.mr.stage_add_copy.validate_phase3_seed_stage",
        lambda *args, **kwargs: evidence,
    )
    request = replace(
        legacy,
        review_package=None,
        phase3_seed_stage_manifest=stage_manifest,
    )

    output = stage_live_t12_inputs(request)

    manifest = json.loads(output.manifest.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "2.0"
    assert manifest["profile"] == "phase3_reviewed_single_component"
    assert manifest["phase3_seed_stage_id"] == evidence.stage_id
    assert "approved_decisions_sha256" not in manifest
    assert "approved_validation_sha256" not in manifest


def test_phase3_joint_copy_parent_reaches_refinement_without_addition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _live_request(
        tmp_path,
        expected_copy_count=2,
        outcome="supported",
        placed_copy_count=2,
    )
    assert legacy.review_package is not None
    review_root = legacy.review_package
    review_manifest = review_root / "mr_seed_review_manifest.json"
    review_document = json.loads(review_manifest.read_text(encoding="utf-8"))
    approved_root = legacy.approved_stage
    legacy_stage = json.loads(
        (approved_root / "live_m4_stage_manifest.json").read_text(encoding="utf-8")
    )
    model_sources = json.loads(json.dumps(legacy_stage["model_sources"]))
    model_sources[SEED_ID]["placed_copy_count"] = 2
    model_sources[SEED_ID]["requires_additional_copy"] = False
    model = approved_root / str(model_sources[SEED_ID]["staged_search_model"])
    with (approved_root / "approved_seeds.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "seed_solution_id",
                "search_model",
                "search_model_sha256",
                "expected_copy_count",
                "requires_additional_copy",
            )
        )
        writer.writerow((SEED_ID, model, sha256_file(model), 2, "false"))
    with (approved_root / "additional_copy_seeds.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "seed_solution_id",
                "search_model",
                "search_model_sha256",
                "expected_copy_count",
                "requires_additional_copy",
            )
        )
    stage_manifest = approved_root / "phase3_seed_stage_manifest.json"
    stage_manifest.write_text(
        json.dumps(
            {
                "stage_id": "phase3seedstage_" + "1" * 64,
                "approved_seed_count": 1,
                "additional_copy_seed_count": 0,
                "hypotheses_sha256": sha256_file(legacy.hypotheses_jsonl),
                "model_sources": model_sources,
            }
        ),
        encoding="utf-8",
    )
    evidence = PhaseIIISeedStageEvidence(
        stage_id="phase3seedstage_" + "1" * 64,
        review_id=REVIEW_ID,
        approved_solution_ids=(SEED_ID,),
        root=approved_root,
        review_root=review_root,
        review_manifest=review_manifest,
        review_document=review_document,
        model_sources=model_sources,
    )
    monkeypatch.setattr(
        "genome_to_diffraction.mr.stage_add_copy.validate_phase3_seed_stage",
        lambda *args, **kwargs: evidence,
    )
    request = replace(
        legacy,
        review_package=None,
        phase3_seed_stage_manifest=stage_manifest,
        additional_copy_results=(),
    )

    output = stage_live_t12_inputs(request)

    finalist = output.finalists.read_text(encoding="utf-8").splitlines()[1]
    assert finalist.split("\t")[2] == "2"
    manifest = json.loads(output.manifest.read_text(encoding="utf-8"))
    candidate = manifest["candidates"][0]
    assert candidate["attempted_transition_count"] == 0
    assert candidate["best_supported_copy_count"] == 2
    assert candidate["reached_expected_copy_count"] is True
    assert output.copy_assessments_jsonl is not None
    assessment = CopyCountAssessment.model_validate_json(
        output.copy_assessments_jsonl.read_bytes().splitlines()[0]
    )
    assert assessment.attempted_transition_count == 0
    assert assessment.best_supported_copy_count == 2
    assert assessment.reached_expected_copy_count is True


def test_phase3_live_stage_rejects_dual_review_authority(tmp_path: Path) -> None:
    request = replace(
        _live_request(tmp_path, expected_copy_count=2, outcome="supported"),
        phase3_seed_stage_manifest=tmp_path / "phase3_seed_stage_manifest.json",
    )

    with pytest.raises(T12StageError, match="rejects a legacy review package"):
        stage_live_t12_inputs(request)


def test_live_stage_rejects_changed_supported_child_asset(tmp_path: Path) -> None:
    request = _live_request(tmp_path, expected_copy_count=2, outcome="supported")
    coordinate = request.additional_copy_results[0] / "PHASER.1.pdb"
    coordinate.write_text("changed after result publication\n", encoding="ascii")

    with pytest.raises(T12StageError, match="asset checksum mismatch"):
        stage_live_t12_inputs(request)


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
