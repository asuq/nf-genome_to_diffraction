"""Tests for the file-based first-copy MR checkpoint."""

import csv
import json
import os
import subprocess
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.cli import main
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.mr.stage_add_copy import (
    LiveAddCopyStageRequest,
    prepare_live_add_copy_stage,
)
from genome_to_diffraction.review import (
    MrSeedApprovalRequest,
    MrSeedReviewError,
    MrSeedReviewRequest,
    OwnedPhaseIIIParentRun,
    PhaseIIIReviewEvidenceSource,
    PhaseIIIReviewPackageRequest,
    PhaseIIIReviewStageRequest,
    build_mr_seed_review,
    build_phase3_review_package,
    stage_phase3_review_decisions,
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
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecision,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
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


def _phase3_a_seed_stage(
    tmp_path: Path,
    *,
    review_manifest: Path,
    solution_id: str,
    decision: PhaseIIIReviewDecisionValue,
) -> tuple[Path, Path]:
    package_directory = tmp_path / "phase3 A review package"
    package_directory.mkdir()
    package = build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            owned_parent_run_id="gtd-unknown-screen-fixture",
            parent_profile="unknown-screen",
            parent_phase="phase3-pass1",
            execution_identity_id=f"phase3exec_{'a' * 64}",
            crystal_id="test_crystal_01",
            target_item_ids=(solution_id,),
            created_at=datetime.now(UTC),
            input_root=review_manifest.parent,
            evidence_sources=(
                PhaseIIIReviewEvidenceSource(
                    role="mr_seed_review_manifest",
                    relative_path=review_manifest.name,
                ),
            ),
            output_directory=package_directory,
        )
    )
    source = tmp_path / "phase3-a-decisions.json"
    record = PhaseIIIReviewDecisionFile.from_content(
        checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
        owned_parent_run_id="gtd-unknown-screen-fixture",
        review_package_id=package.review_package_id,
        review_package_manifest_sha256=sha256_file(package.manifest),
        decisions=(
            PhaseIIIReviewDecision(
                crystal_id="test_crystal_01",
                item_id=solution_id,
                decision=decision,
                reviewer="phase3-reviewer",
                reviewed_at=datetime(2099, 1, 1, tzinfo=UTC),
                reason="Coot evidence inspected",
                comment="original human decision retained",
            ),
        ),
    )
    atomic_write_json(source, record.model_dump(mode="json", exclude_none=False))
    output = stage_phase3_review_decisions(
        PhaseIIIReviewStageRequest(
            parent=OwnedPhaseIIIParentRun(
                "gtd-unknown-screen-fixture",
                "unknown-screen",
                "phase3-pass1",
            ),
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            review_package_manifest=package.manifest,
            decisions=source,
            confirmed_decisions_sha256=sha256_file(source),
            output_directory=tmp_path / "phase3 A staged decisions",
            progress=False,
        )
    )
    return output.stage_manifest.parent, package.manifest


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


def test_no_model_funnel_emits_an_honest_empty_mr_seed_review(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    request.hypotheses_jsonl.write_text("", encoding="utf-8")
    request.results_jsonl.write_text("", encoding="utf-8")
    funnel = json.loads(request.funnel_manifest.read_text(encoding="utf-8"))
    funnel["selected_hypothesis_count"] = 0
    funnel["hypotheses"] = []
    request.funnel_manifest.write_text(json.dumps(funnel), encoding="utf-8")

    output = build_mr_seed_review(request)

    assert output.candidate_count == 0
    rows = tuple(
        csv.DictReader(output.review_tsv.open(encoding="utf-8"), delimiter="\t")
    )
    assert rows == ()
    manifest = json.loads(output.manifest_json.read_text(encoding="utf-8"))
    assert manifest["candidate_count"] == 0
    assert manifest["inspectable_solution_count"] == 0
    assert manifest["items"] == []
    assert manifest["approval_requires_explicit_human_decision"] is True

    phase3_root = tmp_path / "phase3-empty-a-review"
    phase3_root.mkdir()
    phase3_package = build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            owned_parent_run_id="gtd-unknown-screen-fixture",
            parent_profile="unknown-screen",
            parent_phase="phase3-pass1",
            execution_identity_id=f"phase3exec_{'a' * 64}",
            crystal_id="test_crystal_01",
            target_item_ids=(),
            created_at=datetime.now(UTC),
            input_root=output.manifest_json.parent,
            evidence_sources=(
                PhaseIIIReviewEvidenceSource(
                    role="mr_seed_review_manifest",
                    relative_path=output.manifest_json.name,
                ),
            ),
            output_directory=phase3_root,
        )
    )
    package = json.loads(phase3_package.manifest.read_text(encoding="ascii"))
    assert package["adapter_version"] == "phase3-review-package-v2"
    assert package["permitted_targets"] == []
    assert package["review_tables"][0]["row_count"] == 0


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


@pytest.mark.parametrize(
    "decision",
    (
        PhaseIIIReviewDecisionValue.APPROVE,
        PhaseIIIReviewDecisionValue.REJECT,
        PhaseIIIReviewDecisionValue.DEFER,
    ),
)
def test_phase3_a_decisions_feed_only_approved_existing_copy_workflow(
    tmp_path: Path,
    decision: PhaseIIIReviewDecisionValue,
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
    legacy = build_mr_seed_review(request)
    legacy_document = json.loads(legacy.manifest_json.read_text(encoding="utf-8"))
    solution_id = legacy_document["items"][0]["solution_id"]
    stage, phase3_manifest = _phase3_a_seed_stage(
        tmp_path,
        review_manifest=legacy.manifest_json,
        solution_id=solution_id,
        decision=decision,
    )

    output = prepare_live_add_copy_stage(
        LiveAddCopyStageRequest(
            review_package=legacy.manifest_json.parent,
            decisions=stage / "phase3_review_decision.json",
            hypotheses_jsonl=request.hypotheses_jsonl,
            output_directory=tmp_path / "phase3 approved A state",
            progress=False,
            phase3_review_stage=stage,
            phase3_review_package_manifest=phase3_manifest,
        )
    )

    expected_count = int(decision is PhaseIIIReviewDecisionValue.APPROVE)
    assert output.approved_seed_count == expected_count
    assert output.additional_copy_seed_count == expected_count
    rows = tuple(
        csv.DictReader(
            output.additional_copy_seeds_tsv.open(encoding="ascii"),
            delimiter="\t",
        )
    )
    assert tuple(row["seed_solution_id"] for row in rows) == (
        (solution_id,) if expected_count else ()
    )
    validation = json.loads(output.validation_json.read_text(encoding="utf-8"))
    provenance = validation["phase3_approval_provenance"]
    assert provenance["crystal_id"] == "test_crystal_01"
    assert provenance["parent_profile"] == "unknown-screen"
    assert provenance["approved_solution_ids"] == (
        [solution_id] if expected_count else []
    )
    disposition_field = {
        PhaseIIIReviewDecisionValue.APPROVE: "approved_solution_ids",
        PhaseIIIReviewDecisionValue.REJECT: "rejected_solution_ids",
        PhaseIIIReviewDecisionValue.DEFER: "deferred_solution_ids",
    }[decision]
    assert provenance[disposition_field] == [solution_id]
    assert validation["execution_status"] == "completed_success"
    manifest = json.loads(output.stage_manifest.read_text(encoding="utf-8"))
    assert manifest["phase3_approval_provenance"] == provenance
    for name in (
        "phase3_review_decision.json",
        "phase3_review_stage_manifest.json",
        "phase3_review_package_manifest.json",
    ):
        assert (output.stage_manifest.parent / name).is_file()


@pytest.mark.parametrize("failure", ("canonical", "legacy", "stage", "package"))
def test_phase3_a_seed_bridge_rejects_cross_evidence_before_publication(
    tmp_path: Path,
    failure: str,
) -> None:
    request = _request(tmp_path)
    legacy = build_mr_seed_review(request)
    document = json.loads(legacy.manifest_json.read_text(encoding="utf-8"))
    solution_id = document["items"][0]["solution_id"]
    stage, phase3_manifest = _phase3_a_seed_stage(
        tmp_path,
        review_manifest=legacy.manifest_json,
        solution_id=solution_id,
        decision=PhaseIIIReviewDecisionValue.APPROVE,
    )
    decision_path = stage / "phase3_review_decision.json"
    if failure == "canonical":
        decision_path = tmp_path / "another-decision.json"
        decision_path.write_bytes((stage / "phase3_review_decision.json").read_bytes())
    elif failure == "legacy":
        legacy.manifest_json.write_text(
            legacy.manifest_json.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
    elif failure == "stage":
        (stage / "unexpected.json").write_text("{}\n", encoding="utf-8")
    else:
        evidence = next((phase3_manifest.parent / "evidence").rglob("*.json"))
        evidence.write_text("{}\n", encoding="utf-8")
    destination = tmp_path / "must-not-publish-a-state"

    with pytest.raises(ValueError):
        prepare_live_add_copy_stage(
            LiveAddCopyStageRequest(
                review_package=legacy.manifest_json.parent,
                decisions=decision_path,
                hypotheses_jsonl=request.hypotheses_jsonl,
                output_directory=destination,
                progress=False,
                phase3_review_stage=stage,
                phase3_review_package_manifest=phase3_manifest,
            )
        )

    assert not destination.exists()


def test_cli_passes_canonical_phase3_a_approval_to_same_component_stage(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    package = build_mr_seed_review(request)
    manifest = json.loads(package.manifest_json.read_text(encoding="utf-8"))
    solution_id = manifest["items"][0]["solution_id"]
    stage, phase3_package_manifest = _phase3_a_seed_stage(
        tmp_path,
        review_manifest=package.manifest_json,
        solution_id=solution_id,
        decision=PhaseIIIReviewDecisionValue.APPROVE,
    )
    destination = tmp_path / "cli reviewed phase3 seed"

    exit_code = main(
        [
            "--no-progress",
            "mr",
            "stage-approved-seeds",
            "--review-package",
            str(package.manifest_json.parent),
            "--decisions",
            str(stage / "phase3_review_decision.json"),
            "--hypotheses",
            str(request.hypotheses_jsonl),
            "--phase3-review-stage",
            str(stage),
            "--phase3-review-package-manifest",
            str(phase3_package_manifest),
            "--outdir",
            str(destination),
        ]
    )

    assert exit_code == 0
    result = json.loads(
        (destination / "live_m4_stage_manifest.json").read_text(encoding="utf-8")
    )
    assert result["phase3_approval_provenance"]["approved_solution_ids"] == [
        solution_id
    ]


@pytest.mark.parametrize(
    "decision",
    (
        PhaseIIIReviewDecisionValue.APPROVE,
        PhaseIIIReviewDecisionValue.REJECT,
        PhaseIIIReviewDecisionValue.DEFER,
    ),
)
def test_phase3_a_decision_controls_the_actual_same_component_process(
    tmp_path: Path,
    decision: PhaseIIIReviewDecisionValue,
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
    stage, phase3_package_manifest = _phase3_a_seed_stage(
        tmp_path,
        review_manifest=package.manifest_json,
        solution_id=solution_id,
        decision=decision,
    )
    project = tmp_path / "nextflow-project"
    project.mkdir()
    source = STUBS / "phase3_reviewed_seed_fanout/main.nf"
    (project / "main.nf").write_text(
        source.read_text(encoding="ascii")
        .replace("'../../../../modules/", f"'{REPOSITORY}/modules/")
        .replace("'../../../../workflows/", f"'{REPOSITORY}/workflows/"),
        encoding="ascii",
    )
    local_stubs = project / "tests/fixtures/stubs"
    local_stubs.mkdir(parents=True)
    for name in (
        "additional_copy_result.jsonl",
        "additional_copy_result.json",
        "phaser_command.json",
        "add_copy.eff",
        "additional_copy_series_results.jsonl",
        "additional_copy_series_summary.json",
    ):
        copy2(STUBS / name, local_stubs / name)
    output = tmp_path / "reviewed-copy-results"
    command = [
        "nextflow",
        "-C",
        "tests/fixtures/stubs/p6_empty_partner/nextflow.config",
        "run",
        str(project / "main.nf"),
        "-stub-run",
        "--review_package",
        str(package.manifest_json.parent),
        "--review_stage",
        str(stage),
        "--phase3_package",
        str(phase3_package_manifest.parent),
        "--hypotheses",
        str(request.hypotheses_jsonl),
        "--sequence_groups",
        str(STUBS / "sequence_groups.jsonl"),
        "--preflight",
        str(STUBS / "mtz_preflight.jsonl"),
        "--mtz",
        str(STUBS / "predicted_model_preparation/models/stub.pdb"),
        "--phenix_manifest",
        str(STUBS / "phenix_install_manifest.json"),
        "--outdir",
        str(output),
        "--cache_root",
        str(tmp_path / "nextflow-cache"),
    ]
    environment = dict(os.environ)
    environment.update(
        {
            "NXF_AGENT_MODE": "true",
            "NXF_ANSI_LOG": "false",
            "NXF_DISABLE_CHECK_LATEST": "true",
            "NXF_HOME": str(tmp_path / "nxf-home"),
            "NXF_SYNTAX_PARSER": "v2",
        }
    )
    result = subprocess.run(
        command,
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    trace = output / "pipeline_info/trace.tsv"
    with trace.open(encoding="utf-8", newline="") as stream:
        first = tuple(csv.DictReader(stream, delimiter="\t"))
    expected_processes = {
        "STAGE_PHASE3_APPROVED_MR_SEEDS": 1,
    }
    if decision is PhaseIIIReviewDecisionValue.APPROVE:
        expected_processes["RUN_ADDITIONAL_COPY_PHASER"] = 1
    assert Counter(row["process"].split(":")[-1] for row in first) == expected_processes
    assert {row["status"] for row in first} == {"COMPLETED"}
    staged = json.loads(
        (output / "approved_mr_seed_stage/live_m4_stage_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert staged["phase3_approval_provenance"]["approved_solution_ids"] == (
        [solution_id] if decision is PhaseIIIReviewDecisionValue.APPROVE else []
    )

    resumed = subprocess.run(
        [*command, "-resume"],
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert resumed.returncode == 0, f"{resumed.stdout}\n{resumed.stderr}"
    with trace.open(encoding="utf-8", newline="") as stream:
        cached = tuple(csv.DictReader(stream, delimiter="\t"))
    assert {row["status"] for row in cached} == {"CACHED"}
    assert {row["hash"] for row in cached} == {row["hash"] for row in first}


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
