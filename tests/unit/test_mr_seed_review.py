"""Tests for the file-based first-copy MR checkpoint."""

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.mr.stage_add_copy import (
    LiveAddCopyStageRequest,
    prepare_live_add_copy_stage,
)
from genome_to_diffraction.review import (
    MrSeedApprovalRequest,
    MrSeedReviewError,
    MrSeedReviewRequest,
    build_mr_seed_review,
    validate_mr_seed_approvals,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import PrototypeProfile
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    NormalisedMrResult,
    PhysicalStatus,
    ReviewDecisionManifest,
)
from genome_to_diffraction.status import ExecutionStatus

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
GROUP_ID = "seq_f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e"
HYPOTHESIS_ID = "mrhyp_" + "d" * 64


def _hypothesis() -> MrHypothesis:
    return MrHypothesis(
        schema_version="1.0",
        hypothesis_id=HYPOTHESIS_ID,
        crystal_id="test_crystal_01",
        sequence_group_id=GROUP_ID,
        model_id="model_" + "a" * 64,
        copy_count_expected=1,
        copy_number_to_search=1,
        fixed_solution_id=None,
        space_group="P 21 21 21",
        obs_labels="I,SIGI",
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.PILOT,
        priority_features={
            "matthews_hypothesis_id": "matthews_stub",
            "structural_source_class": "predicted",
            "coordinate_provider_accession": "AF-STUB-F1",
            "exact_sequence_mapping": True,
        },
        status=MrHypothesisStatus.QUEUED,
    )


def _matthews() -> MatthewsHypothesis:
    return MatthewsHypothesis(
        schema_version="1.0",
        hypothesis_id="matthews_stub",
        crystal_id="test_crystal_01",
        sequence_group_id=GROUP_ID,
        copy_count=1,
        sequence_mass_da=436.4375,
        total_mass_da=436.4375,
        v_asu_a3=250_000,
        matthews_coefficient=2.4,
        solvent_fraction=0.49,
        matthews_prior=0.75,
        prior_backend="test-prior",
        rank_within_candidate=1,
        retained=True,
        physical_status=PhysicalStatus.PLAUSIBLE,
        sds_page_prior_label="compatible",
        sds_page_fractional_difference=0.1,
    )


def _result(*, hit: bool = True, raw_log: str = "PHASER.log") -> NormalisedMrResult:
    return NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=HYPOTHESIS_ID,
        tool_version="2.8.3",
        execution_status=(
            ExecutionStatus.COMPLETED_HIT if hit else ExecutionStatus.COMPLETED_NO_HIT
        ),
        llg=111.0 if hit else 49.0,
        tfz=11.0 if hit else 5.0,
        placed_copy_count=1 if hit else 0,
        packing_summary={
            "score_gate_passed": hit,
            "score_gate_llg_strictly_greater_than": 50.0,
            "score_gate_tfz_strictly_greater_than": 5.0,
            "score_gate_operator": "or",
            "top_solution_packed": hit,
        },
        solution_coordinate_path="PHASER.1.pdb" if hit else None,
        solution_coordinate_sha256=None,
        output_mtz_path="PHASER.1.mtz" if hit else None,
        output_mtz_sha256=None,
        parser_warnings=(),
        raw_log_pointer=raw_log,
        preliminary_credibility_class=(
            "passes_strict_provisional_score_gate"
            if hit
            else "does_not_pass_strict_provisional_score_gate"
        ),
        rejection_reason=None if hit else "strict_llg_or_tfz_gate_not_met",
    )


def _request(
    tmp_path: Path,
    *,
    hit: bool = True,
    raw_log: str = "PHASER.log",
    keep_solution_assets: bool | None = None,
) -> MrSeedReviewRequest:
    hypothesis = _hypothesis()
    result = _result(hit=hit, raw_log=raw_log)
    hypotheses = tmp_path / "hypotheses.jsonl"
    hypotheses.write_text(f"{canonical_json_text(hypothesis)}\n", encoding="utf-8")
    results = tmp_path / "results.jsonl"
    results.write_text(f"{canonical_json_text(result)}\n", encoding="utf-8")
    matthews = tmp_path / "matthews.jsonl"
    matthews.write_text(f"{canonical_json_text(_matthews())}\n", encoding="utf-8")
    funnel = tmp_path / "funnel_manifest.json"
    funnel.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "funnel_id": "funnel_stub_review",
                "selected_hypothesis_count": 1,
                "execution_status": "completed_success",
                "hypotheses": [
                    {
                        "hypothesis_id": HYPOTHESIS_ID,
                        "model_id": hypothesis.model_id,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result_root = tmp_path / "published results"
    bundle = result_root / f"first_copy_phaser_{HYPOTHESIS_ID}"
    bundle.mkdir(parents=True)
    (bundle / "normalised_mr_result.jsonl").write_text(
        f"{canonical_json_text(result)}\n", encoding="utf-8"
    )
    (bundle / "phaser_command.json").write_text(
        json.dumps(
            {
                "arguments": ["phenix.phaser"],
                "model_sha256": "a" * 64,
                "model_identity_percent": 85.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    if raw_log == "PHASER.log":
        (bundle / raw_log).write_text("PHASER test log\n", encoding="utf-8")
    if keep_solution_assets is None:
        keep_solution_assets = hit
    if keep_solution_assets:
        coordinate = bundle / "PHASER.1.pdb"
        coordinate.write_text("MODEL        1\nEND\n", encoding="utf-8")
        mtz = bundle / "PHASER.1.mtz"
        mtz.write_bytes(b"MTZ test bytes")
        result = result.model_copy(
            update={
                "solution_coordinate_path": coordinate.name,
                "solution_coordinate_sha256": sha256_file(coordinate),
                "output_mtz_path": mtz.name,
                "output_mtz_sha256": sha256_file(mtz),
            }
        )
        results.write_text(f"{canonical_json_text(result)}\n", encoding="utf-8")
        (bundle / "normalised_mr_result.jsonl").write_text(
            f"{canonical_json_text(result)}\n", encoding="utf-8"
        )
    return MrSeedReviewRequest(
        hypotheses_jsonl=hypotheses,
        results_jsonl=results,
        result_root=result_root,
        funnel_manifest=funnel,
        sequence_groups_jsonl=STUBS / "sequence_groups.jsonl",
        source_records_jsonl=STUBS / "source_records.jsonl",
        matthews_hypotheses_jsonl=matthews,
        pipeline_config=REPOSITORY / "examples/config.yaml",
        output_directory=tmp_path / "review package",
        progress=False,
    )


def _decision(path: Path, solution_id: str, *, override: str = "") -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "checkpoint",
                "item_id",
                "decision",
                "reviewer",
                "reviewed_at",
                "comment",
                "override_reason",
            )
        )
        writer.writerow(
            (
                "mr_seed",
                solution_id,
                "approve",
                "test-reviewer",
                "2099-01-01T00:00:00Z",
                "map and packing inspected",
                override,
            )
        )


def test_builds_content_bound_review_and_schema_valid_empty_template(
    tmp_path: Path,
) -> None:
    output = build_mr_seed_review(_request(tmp_path))

    assert output.package_id.startswith("reviewpkg_")
    assert output.candidate_count == 1
    rows = list(
        csv.DictReader(output.review_tsv.open(encoding="utf-8"), delimiter="\t")
    )
    assert rows[0]["solution_id"].startswith("sol_")
    assert rows[0]["inspectable_solution"] == "True"
    assert rows[0]["llg"] == "111.0"
    assert rows[0]["tfz"] == "11.0"
    assert rows[0]["source_loci"] == "example_archaeon_refseq:stub_protein"
    assert (output.manifest_json.parent / rows[0]["solution_coordinate"]).is_file()
    assert "not a calibrated probability" in output.review_html.read_text(
        encoding="utf-8"
    )
    manifest = json.loads(output.manifest_json.read_text(encoding="utf-8"))
    assert manifest["score_gate"] == {
        "policy_id": "strict_llg_gt_50_or_tfz_gt_5",
        "llg_strictly_greater_than": 50.0,
        "tfz_strictly_greater_than": 5.0,
        "operator": "or",
    }
    assert manifest["numeric_screen_excludes_candidates"] is False
    assert manifest["approval_requires_explicit_human_decision"] is True
    assert manifest["inspectable_solution_count"] == 1
    template = load_contract(
        output.approval_template_tsv,
        "review-decisions",
        progress=False,
    )
    assert isinstance(template, ReviewDecisionManifest)
    assert template.decisions == ()


def test_validates_explicit_approval_and_rejects_stale_identifier(
    tmp_path: Path,
) -> None:
    package = build_mr_seed_review(_request(tmp_path))
    manifest = json.loads(package.manifest_json.read_text(encoding="utf-8"))
    solution_id = manifest["items"][0]["solution_id"]
    decisions = tmp_path / "approved.tsv"
    _decision(decisions, solution_id)

    validated = validate_mr_seed_approvals(
        MrSeedApprovalRequest(
            package_manifest=package.manifest_json,
            decisions=decisions,
            output_json=tmp_path / "validated.json",
            progress=False,
        )
    )
    assert validated.review_id.startswith("rev_")
    assert validated.approved_solution_ids == (solution_id,)

    _decision(decisions, "sol_" + "0" * 64)
    with pytest.raises(MrSeedReviewError, match="stale or unknown"):
        validate_mr_seed_approvals(
            replace(
                MrSeedApprovalRequest(
                    package_manifest=package.manifest_json,
                    decisions=decisions,
                    output_json=tmp_path / "stale.json",
                    progress=False,
                )
            )
        )


def test_stages_approved_solution_coordinate_for_live_additional_copy(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    hypothesis = _hypothesis().model_copy(update={"copy_count_expected": 3})
    request.hypotheses_jsonl.write_text(
        f"{canonical_json_text(hypothesis)}\n", encoding="utf-8"
    )
    matthews = _matthews().model_copy(
        update={"copy_count": 3, "total_mass_da": 3 * 436.4375}
    )
    request.matthews_hypotheses_jsonl.write_text(
        f"{canonical_json_text(matthews)}\n", encoding="utf-8"
    )
    package = build_mr_seed_review(request)
    manifest = json.loads(package.manifest_json.read_text(encoding="utf-8"))
    solution_id = manifest["items"][0]["solution_id"]
    decisions = tmp_path / "approved-live.tsv"
    _decision(decisions, solution_id)

    staged = prepare_live_add_copy_stage(
        LiveAddCopyStageRequest(
            review_package=package.manifest_json.parent,
            decisions=decisions,
            hypotheses_jsonl=request.hypotheses_jsonl,
            output_directory=tmp_path / "live M4 stage",
            progress=False,
        )
    )

    assert staged.approved_seed_count == 1
    assert staged.additional_copy_seed_count == 1
    rows = list(
        csv.DictReader(
            staged.additional_copy_seeds_tsv.open(encoding="utf-8"),
            delimiter="\t",
        )
    )
    assert rows == [
        {
            "seed_solution_id": solution_id,
            "search_model": rows[0]["search_model"],
            "search_model_sha256": rows[0]["search_model_sha256"],
            "expected_copy_count": "3",
            "requires_additional_copy": "true",
        }
    ]
    staged_model = staged.additional_copy_seeds_tsv.parent / rows[0]["search_model"]
    assert staged_model.is_file()
    assert sha256_file(staged_model) == rows[0]["search_model_sha256"]
    stage_manifest = json.loads(staged.stage_manifest.read_text(encoding="utf-8"))
    source = stage_manifest["model_sources"][solution_id]
    assert source["derivation"] == ("first_copy_solution_coordinate_rigid_body_derived")
    assert source["original_first_copy_model_sha256"] == "a" * 64
    assert source["staged_search_model_sha256"] == rows[0]["search_model_sha256"]
    assert stage_manifest["numeric_score_filter_applied"] is False


def test_live_stage_retains_approved_one_copy_seed_without_phaser_dispatch(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    package = build_mr_seed_review(request)
    manifest = json.loads(package.manifest_json.read_text(encoding="utf-8"))
    solution_id = manifest["items"][0]["solution_id"]
    decisions = tmp_path / "approved-one-copy.tsv"
    _decision(decisions, solution_id)

    staged = prepare_live_add_copy_stage(
        LiveAddCopyStageRequest(
            review_package=package.manifest_json.parent,
            decisions=decisions,
            hypotheses_jsonl=request.hypotheses_jsonl,
            output_directory=tmp_path / "one copy M4 stage",
            progress=False,
        )
    )

    approved_rows = list(
        csv.DictReader(staged.approved_seeds_tsv.open(encoding="utf-8"), delimiter="\t")
    )
    additional_rows = list(
        csv.DictReader(
            staged.additional_copy_seeds_tsv.open(encoding="utf-8"),
            delimiter="\t",
        )
    )
    assert approved_rows[0]["seed_solution_id"] == solution_id
    assert approved_rows[0]["requires_additional_copy"] == "false"
    assert additional_rows == []
    stage_manifest = json.loads(staged.stage_manifest.read_text(encoding="utf-8"))
    assert stage_manifest["approved_seed_count"] == 1
    assert stage_manifest["additional_copy_seed_count"] == 0
    assert stage_manifest["already_at_expected_copy_count"] == 1
    assert stage_manifest["all_approved_seeds_retained"] is True


def test_approval_without_inspectable_assets_requires_explicit_override(
    tmp_path: Path,
) -> None:
    package = build_mr_seed_review(_request(tmp_path, hit=False))
    manifest = json.loads(package.manifest_json.read_text(encoding="utf-8"))
    solution_id = manifest["items"][0]["solution_id"]
    decisions = tmp_path / "approved.tsv"
    request = MrSeedApprovalRequest(
        package_manifest=package.manifest_json,
        decisions=decisions,
        output_json=tmp_path / "validated.json",
        progress=False,
    )
    _decision(decisions, solution_id)
    with pytest.raises(MrSeedReviewError, match="override reason"):
        validate_mr_seed_approvals(request)

    _decision(decisions, solution_id, override="expert map evidence")
    assert validate_mr_seed_approvals(request).approved_solution_ids == (solution_id,)


def test_below_screen_solution_assets_are_retained_for_coot_and_approval(
    tmp_path: Path,
) -> None:
    package = build_mr_seed_review(
        _request(tmp_path, hit=False, keep_solution_assets=True)
    )
    rows = list(
        csv.DictReader(package.review_tsv.open(encoding="utf-8"), delimiter="\t")
    )
    assert rows[0]["score_gate_passed"] == "False"
    assert rows[0]["inspectable_solution"] == "True"
    assert (package.manifest_json.parent / rows[0]["solution_coordinate"]).is_file()
    assert (package.manifest_json.parent / rows[0]["output_mtz"]).is_file()

    manifest = json.loads(package.manifest_json.read_text(encoding="utf-8"))
    solution_id = manifest["items"][0]["solution_id"]
    decisions = tmp_path / "approved-below-screen.tsv"
    _decision(decisions, solution_id)
    validated = validate_mr_seed_approvals(
        MrSeedApprovalRequest(
            package_manifest=package.manifest_json,
            decisions=decisions,
            output_json=tmp_path / "validated-below-screen.json",
            progress=False,
        )
    )
    assert validated.approved_solution_ids == (solution_id,)


def test_legacy_review_item_with_pdb_and_mtz_is_inspectable_for_approval(
    tmp_path: Path,
) -> None:
    package = build_mr_seed_review(
        _request(tmp_path, hit=False, keep_solution_assets=True)
    )
    manifest = json.loads(package.manifest_json.read_text(encoding="utf-8"))
    item = manifest["items"][0]
    solution_id = item["solution_id"]
    item.pop("inspectable_solution")
    package.manifest_json.write_text(
        json.dumps(manifest) + "\n",
        encoding="utf-8",
    )
    decisions = tmp_path / "approved-legacy.tsv"
    _decision(decisions, solution_id)

    validated = validate_mr_seed_approvals(
        MrSeedApprovalRequest(
            package_manifest=package.manifest_json,
            decisions=decisions,
            output_json=tmp_path / "validated-legacy.json",
            progress=False,
        )
    )

    assert validated.approved_solution_ids == (solution_id,)


def test_approval_validates_only_assets_for_explicitly_decided_items(
    tmp_path: Path,
) -> None:
    package = build_mr_seed_review(_request(tmp_path))
    manifest = json.loads(package.manifest_json.read_text(encoding="utf-8"))
    approved_solution_id = manifest["items"][0]["solution_id"]
    missing_identity = {"test_fixture": "unselected transported solution"}
    missing_solution_id = content_id("sol_", missing_identity)
    missing_item = json.loads(json.dumps(manifest["items"][0]))
    missing_item.update(
        {
            "solution_id": missing_solution_id,
            "solution_identity": missing_identity,
            "inspectable_solution": False,
            "copied_assets": {
                "command": f"assets/{missing_solution_id}/missing-command.json"
            },
            "copied_asset_sha256": {"command": "0" * 64},
        }
    )
    manifest["items"].append(missing_item)
    manifest["package_identity"]["solution_ids"].append(missing_solution_id)
    manifest["package_id"] = content_id("reviewpkg_", manifest["package_identity"])
    package.manifest_json.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    decisions = tmp_path / "approved-transported-subset.tsv"
    _decision(decisions, approved_solution_id)

    validated = validate_mr_seed_approvals(
        MrSeedApprovalRequest(
            package_manifest=package.manifest_json,
            decisions=decisions,
            output_json=tmp_path / "validated-transported-subset.json",
            progress=False,
        )
    )

    assert validated.approved_solution_ids == (approved_solution_id,)


def test_review_recomputes_missing_gate_for_no_solution(tmp_path: Path) -> None:
    request = _request(tmp_path, hit=False)
    result = _result(hit=False).model_copy(
        update={
            "llg": None,
            "tfz": None,
            "packing_summary": {
                "accepted_solution_count": 0,
                "packed_solution_count": 0,
                "solution_count": 0,
                "top_solution_packed": False,
            },
            "preliminary_credibility_class": "no_solution",
            "rejection_reason": "phaser_reported_no_solution",
        }
    )
    result_text = f"{canonical_json_text(result)}\n"
    request.results_jsonl.write_text(result_text, encoding="utf-8")
    bundle = request.result_root / f"first_copy_phaser_{HYPOTHESIS_ID}"
    (bundle / "normalised_mr_result.jsonl").write_text(result_text, encoding="utf-8")

    package = build_mr_seed_review(request)
    rows = list(
        csv.DictReader(package.review_tsv.open(encoding="utf-8"), delimiter="\t")
    )
    assert rows[0]["score_gate_passed"] == "False"
    assert rows[0]["inspectable_solution"] == "False"


def test_review_rejects_explicit_score_gate_disagreement(tmp_path: Path) -> None:
    request = _request(tmp_path, hit=False)
    result = _result(hit=False).model_copy(
        update={"packing_summary": {"score_gate_passed": True}}
    )
    result_text = f"{canonical_json_text(result)}\n"
    request.results_jsonl.write_text(result_text, encoding="utf-8")
    bundle = request.result_root / f"first_copy_phaser_{HYPOTHESIS_ID}"
    (bundle / "normalised_mr_result.jsonl").write_text(result_text, encoding="utf-8")

    with pytest.raises(MrSeedReviewError, match="stored and recomputed"):
        build_mr_seed_review(request)


def test_review_reclassifies_legacy_gate_from_preserved_raw_scores(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    result = _result().model_copy(
        update={
            "execution_status": ExecutionStatus.COMPLETED_NO_HIT,
            "llg": 19.726,
            "tfz": 5.5,
            "packing_summary": {
                "score_gate_passed": False,
                "score_gate_llg_strictly_greater_than": 100.0,
                "score_gate_tfz_strictly_greater_than": 10.0,
                "top_solution_packed": True,
            },
            "preliminary_credibility_class": (
                "does_not_pass_strict_provisional_score_gate"
            ),
            "rejection_reason": "strict_llg_tfz_gate_not_met",
        }
    )
    result_text = f"{canonical_json_text(result)}\n"
    request.results_jsonl.write_text(result_text, encoding="utf-8")
    bundle = request.result_root / f"first_copy_phaser_{HYPOTHESIS_ID}"
    (bundle / "normalised_mr_result.jsonl").write_text(result_text, encoding="utf-8")

    package = build_mr_seed_review(request)
    rows = list(
        csv.DictReader(package.review_tsv.open(encoding="utf-8"), delimiter="\t")
    )
    assert rows[0]["score_gate_passed"] == "True"
    assert rows[0]["inspectable_solution"] == "True"


def test_rejects_result_bundle_path_traversal(tmp_path: Path) -> None:
    request = _request(tmp_path, hit=False, raw_log="../outside.log")
    (request.result_root / "outside.log").write_text("unsafe\n", encoding="utf-8")

    with pytest.raises(MrSeedReviewError, match="unsafe Phaser raw log path"):
        build_mr_seed_review(request)


def test_approval_validation_detects_edited_review_table(tmp_path: Path) -> None:
    package = build_mr_seed_review(_request(tmp_path))
    manifest = json.loads(package.manifest_json.read_text(encoding="utf-8"))
    solution_id = manifest["items"][0]["solution_id"]
    decisions = tmp_path / "approved.tsv"
    _decision(decisions, solution_id)
    package.review_tsv.write_text("edited\n", encoding="utf-8")

    with pytest.raises(MrSeedReviewError, match="output checksum differs"):
        validate_mr_seed_approvals(
            MrSeedApprovalRequest(
                package_manifest=package.manifest_json,
                decisions=decisions,
                output_json=tmp_path / "validated.json",
                progress=False,
            )
        )
