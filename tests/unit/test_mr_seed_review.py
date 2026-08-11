"""Tests for the file-based first-copy MR checkpoint."""

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_text
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
        llg=111.0 if hit else 99.0,
        tfz=11.0,
        placed_copy_count=1 if hit else 0,
        packing_summary={
            "score_gate_passed": hit,
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
        rejection_reason=None if hit else "strict_llg_tfz_gate_not_met",
    )


def _request(
    tmp_path: Path, *, hit: bool = True, raw_log: str = "PHASER.log"
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
        '{"arguments":["phenix.phaser"]}\n', encoding="utf-8"
    )
    if raw_log == "PHASER.log":
        (bundle / raw_log).write_text("PHASER test log\n", encoding="utf-8")
    if hit:
        coordinate = bundle / "PHASER.1.pdb"
        coordinate.write_text("MODEL        1\nEND\n", encoding="utf-8")
        mtz = bundle / "PHASER.1.mtz"
        mtz.write_bytes(b"MTZ test bytes")
        result = result.model_copy(
            update={
                "solution_coordinate_sha256": sha256_file(coordinate),
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
    assert rows[0]["automatic_eligibility"] == "True"
    assert rows[0]["llg"] == "111.0"
    assert rows[0]["tfz"] == "11.0"
    assert rows[0]["source_loci"] == "example_archaeon_refseq:stub_protein"
    assert (output.manifest_json.parent / rows[0]["solution_coordinate"]).is_file()
    assert "not a calibrated probability" in output.review_html.read_text(
        encoding="utf-8"
    )
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


def test_ineligible_approval_requires_explicit_override(tmp_path: Path) -> None:
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
