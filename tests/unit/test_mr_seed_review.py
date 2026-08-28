"""Tests for the file-based first-copy MR checkpoint."""

import csv
import json
import os
import subprocess
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.cli import main
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.mr.stage_add_copy import (
    LiveAddCopyStageRequest,
    PhaseIIISeedStageRequest,
    prepare_live_add_copy_stage,
    prepare_phase3_seed_stage,
)
from genome_to_diffraction.review import (
    MrSeedApprovalRequest,
    MrSeedReviewError,
    MrSeedReviewRequest,
    OwnedPhaseIIIParentRun,
    OwnedPhaseIIIReviewPackageSource,
    PhaseIIIReviewEvidenceSource,
    PhaseIIIReviewPackageError,
    PhaseIIIReviewPackageRequest,
    PhaseIIIReviewStageRequest,
    build_mr_seed_review,
    build_owned_phase3_a_seed_review_package,
    build_phase3_review_package,
    register_phase3_owned_run,
    stage_phase3_review_decisions,
    validate_mr_seed_approvals,
    validate_phase3_review_package,
)
from genome_to_diffraction.review.mr_seed import validate_mr_seed_review_evidence
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
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecision,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
)
from genome_to_diffraction.status import ExecutionStatus
from tests.support.unknown_pass1_fixture import (
    PUBLIC_STUB_CRYSTAL_IDS,
    materialise_unknown_pass1_public_fixture,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
GROUP_ID = "seq_f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e"
HYPOTHESIS_ID = "mrhyp_" + "d" * 64


def _hypothesis(
    *,
    crystal_id: str = "test_crystal_01",
    hypothesis_id: str = HYPOTHESIS_ID,
) -> MrHypothesis:
    return MrHypothesis(
        schema_version="1.0",
        hypothesis_id=hypothesis_id,
        crystal_id=crystal_id,
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


def _matthews(*, crystal_id: str = "test_crystal_01") -> MatthewsHypothesis:
    return MatthewsHypothesis(
        schema_version="1.0",
        hypothesis_id="matthews_stub",
        crystal_id=crystal_id,
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


def _result(
    *,
    hit: bool = True,
    raw_log: str = "PHASER.log",
    hypothesis_id: str = HYPOTHESIS_ID,
) -> NormalisedMrResult:
    return NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=hypothesis_id,
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
    crystal_id: str = "test_crystal_01",
    hypothesis_id: str = HYPOTHESIS_ID,
) -> MrSeedReviewRequest:
    hypothesis = _hypothesis(crystal_id=crystal_id, hypothesis_id=hypothesis_id)
    result = _result(hit=hit, raw_log=raw_log, hypothesis_id=hypothesis_id)
    hypotheses = tmp_path / "hypotheses.jsonl"
    hypotheses.write_text(f"{canonical_json_text(hypothesis)}\n", encoding="utf-8")
    results = tmp_path / "results.jsonl"
    results.write_text(f"{canonical_json_text(result)}\n", encoding="utf-8")
    matthews = tmp_path / "matthews.jsonl"
    matthews.write_text(
        f"{canonical_json_text(_matthews(crystal_id=crystal_id))}\n",
        encoding="utf-8",
    )
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
                        "hypothesis_id": hypothesis_id,
                        "model_id": hypothesis.model_id,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result_root = tmp_path / "published results"
    bundle = result_root / f"first_copy_phaser_{hypothesis_id}"
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
    crystal_id: str = "test_crystal_01",
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
            crystal_id=crystal_id,
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
                crystal_id=crystal_id,
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


def _owned_phase3_a_seed_inputs(
    root: Path,
    *,
    crystal_id: str,
    execution_identity: Path,
    owned_parent_run_id: str,
    decision: PhaseIIIReviewDecisionValue,
    expected_copies: int = 1,
    placed_copies: int = 1,
) -> tuple[MrSeedReviewRequest, Path, Path, Path, str]:
    request = _request(root, crystal_id=crystal_id)
    hypothesis = _hypothesis(crystal_id=crystal_id).model_copy(
        update={"copy_count_expected": expected_copies}
    )
    request.hypotheses_jsonl.write_text(
        f"{canonical_json_text(hypothesis)}\n", encoding="utf-8"
    )
    matthews = _matthews(crystal_id=crystal_id).model_copy(
        update={
            "copy_count": expected_copies,
            "total_mass_da": expected_copies * 436.4375,
        }
    )
    request.matthews_hypotheses_jsonl.write_text(
        f"{canonical_json_text(matthews)}\n", encoding="utf-8"
    )
    result = NormalisedMrResult.model_validate_json(
        request.results_jsonl.read_text(encoding="utf-8")
    ).model_copy(update={"placed_copy_count": placed_copies})
    result_text = f"{canonical_json_text(result)}\n"
    request.results_jsonl.write_text(result_text, encoding="utf-8")
    result_bundles = tuple(request.result_root.iterdir())
    assert len(result_bundles) == 1
    (result_bundles[0] / "normalised_mr_result.jsonl").write_text(
        result_text,
        encoding="utf-8",
    )
    review = build_mr_seed_review(request)
    legacy = json.loads(review.manifest_json.read_text(encoding="utf-8"))
    solution_id = str(legacy["items"][0]["solution_id"])
    package = build_owned_phase3_a_seed_review_package(
        review_package=review.manifest_json.parent,
        hypotheses_jsonl=request.hypotheses_jsonl,
        execution_identity=execution_identity,
        owned_parent_run_id=owned_parent_run_id,
        crystal_id=crystal_id,
        output_directory=root / "owned-a-package",
    )
    record = PhaseIIIReviewDecisionFile.from_content(
        checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
        owned_parent_run_id=owned_parent_run_id,
        review_package_id=package.review_package_id,
        review_package_manifest_sha256=sha256_file(package.manifest),
        decisions=(
            PhaseIIIReviewDecision(
                crystal_id=crystal_id,
                item_id=solution_id,
                decision=decision,
                reviewer="phase3-reviewer",
                reviewed_at=datetime(2099, 1, 1, tzinfo=UTC),
                reason="Coot evidence inspected",
            ),
        ),
    )
    decisions = root / "a-decisions.json"
    atomic_write_json(decisions, record.model_dump(mode="json", exclude_none=False))
    stage = stage_phase3_review_decisions(
        PhaseIIIReviewStageRequest(
            parent=OwnedPhaseIIIParentRun(
                owned_parent_run_id,
                "unknown-screen",
                "phase3-pass1",
            ),
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            review_package_manifest=package.manifest,
            decisions=decisions,
            confirmed_decisions_sha256=sha256_file(decisions),
            output_directory=root / "owned-a-stage",
            progress=False,
        )
    )
    return (
        request,
        review.manifest_json.parent,
        package.manifest.parent,
        stage.stage_manifest.parent,
        solution_id,
    )


@dataclass(frozen=True)
class _OwnedPhase3SeedFixture:
    request: MrSeedReviewRequest
    legacy_review: Path
    package: Path
    review_stage: Path
    solution_id: str
    execution_identity: Path
    owned_registry: Path
    parent_run: str
    owned_registry_id: str

    def stage_request(self, output: Path) -> PhaseIIISeedStageRequest:
        return PhaseIIISeedStageRequest(
            review_stage=self.review_stage,
            review_package_manifest=(
                self.package / "phase3_review_package_manifest.json"
            ),
            hypotheses_jsonl=self.request.hypotheses_jsonl,
            owned_run_registry=self.owned_registry,
            execution_identity=self.execution_identity,
            owned_parent_run_id=self.parent_run,
            output_directory=output,
            progress=False,
        )


def _registered_phase3_a_seed_fixture(
    tmp_path: Path,
    *,
    decision: PhaseIIIReviewDecisionValue,
    expected_copies: int = 3,
    placed_copies: int = 1,
) -> _OwnedPhase3SeedFixture:
    public_root = tmp_path / "public-fixture"
    public_root.mkdir()
    public = materialise_unknown_pass1_public_fixture(public_root)
    parent_run = "gtd-unknown-screen-owned-fixture"
    crystal_id = PUBLIC_STUB_CRYSTAL_IDS[0]
    crystal_root = tmp_path / crystal_id
    crystal_root.mkdir()
    request, legacy, package, stage, solution_id = _owned_phase3_a_seed_inputs(
        crystal_root,
        crystal_id=crystal_id,
        execution_identity=public.execution_identity,
        owned_parent_run_id=parent_run,
        decision=decision,
        expected_copies=expected_copies,
        placed_copies=placed_copies,
    )
    registry = tmp_path / "completed-screen-registry"
    registry.mkdir()
    record = register_phase3_owned_run(
        parent=OwnedPhaseIIIParentRun(parent_run, "unknown-screen", "phase3-pass1"),
        completed_at=datetime.now(UTC),
        execution_identity=public.execution_identity,
        packages=(
            OwnedPhaseIIIReviewPackageSource(
                crystal_id=crystal_id,
                checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
                package_directory=package,
            ),
        ),
        output_directory=registry,
    )
    return _OwnedPhase3SeedFixture(
        request=request,
        legacy_review=legacy,
        package=package,
        review_stage=stage,
        solution_id=solution_id,
        execution_identity=public.execution_identity,
        owned_registry=registry,
        parent_run=parent_run,
        owned_registry_id=record.owned_run_registry_id,
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


@pytest.mark.parametrize("empty", (False, True), ids=("complete", "no-model"))
def test_owned_phase3_a_package_binds_real_crystal_review_evidence(
    tmp_path: Path, *, empty: bool
) -> None:
    fixture_root = tmp_path / "public execution"
    fixture_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(fixture_root)
    crystal_id = PUBLIC_STUB_CRYSTAL_IDS[0]
    review_root = tmp_path / "first-copy evidence"
    review_root.mkdir()
    request = _request(review_root, crystal_id=crystal_id)
    if empty:
        request.hypotheses_jsonl.write_text("", encoding="utf-8")
        request.results_jsonl.write_text("", encoding="utf-8")
        funnel = json.loads(request.funnel_manifest.read_text(encoding="utf-8"))
        funnel["selected_hypothesis_count"] = 0
        funnel["hypotheses"] = []
        atomic_write_json(request.funnel_manifest, funnel)
    review = build_mr_seed_review(request)

    output = build_owned_phase3_a_seed_review_package(
        review_package=review.manifest_json.parent,
        hypotheses_jsonl=request.hypotheses_jsonl,
        execution_identity=fixture.execution_identity,
        owned_parent_run_id="gtd-unknown-screen-owned-fixture",
        crystal_id=crystal_id,
        output_directory=tmp_path / "owned A package",
    )

    package = validate_phase3_review_package(output.manifest.parent)
    execution = PhaseIIIExecutionIdentity.model_validate_json(
        fixture.execution_identity.read_bytes()
    )
    legacy = json.loads(review.manifest_json.read_text(encoding="utf-8"))
    assert package.owned_parent_run_id == "gtd-unknown-screen-owned-fixture"
    assert package.parent_profile == "unknown-screen"
    assert package.parent_phase == "phase3-pass1"
    assert package.crystal_id == crystal_id
    assert package.execution_identity_id == execution.execution_identity_id
    assert tuple(item.item_id for item in package.permitted_targets) == tuple(
        sorted(item["solution_id"] for item in legacy["items"])
    )
    assert package.review_tables[0].row_count == (0 if empty else 1)
    evidence = next(
        item
        for item in package.evidence_inventory
        if item.role == "mr_seed_review_manifest"
    )
    assert evidence.sha256 == sha256_file(review.manifest_json, progress=False)
    assert validate_mr_seed_review_evidence(
        package_manifest=output.manifest.parent / evidence.relative_path,
        hypotheses_jsonl=request.hypotheses_jsonl,
        crystal_id=crystal_id,
    ) == tuple(item.item_id for item in package.permitted_targets)


@pytest.mark.parametrize(
    "mutation", ("crystal", "output", "hypotheses", "count", "failure")
)
def test_owned_phase3_a_package_rejects_inconsistent_review_before_publication(
    tmp_path: Path, mutation: str
) -> None:
    fixture_root = tmp_path / "public execution"
    fixture_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(fixture_root)
    crystal_id = PUBLIC_STUB_CRYSTAL_IDS[0]
    review_root = tmp_path / "first-copy evidence"
    review_root.mkdir()
    request = _request(review_root, crystal_id=crystal_id)
    review = build_mr_seed_review(request)
    if mutation == "crystal":
        crystal_id = PUBLIC_STUB_CRYSTAL_IDS[1]
    elif mutation == "output":
        review.review_tsv.write_text("mutated review\n", encoding="utf-8")
    elif mutation == "hypotheses":
        request.hypotheses_jsonl.write_text("", encoding="utf-8")
    else:
        document = json.loads(review.manifest_json.read_text(encoding="utf-8"))
        if mutation == "count":
            document["candidate_count"] = 2
        else:
            document["execution_status"] = "execution_failure"
        atomic_write_json(review.manifest_json, document)
    destination = tmp_path / "must not publish"

    with pytest.raises(PhaseIIIReviewPackageError):
        build_owned_phase3_a_seed_review_package(
            review_package=review.manifest_json.parent,
            hypotheses_jsonl=request.hypotheses_jsonl,
            execution_identity=fixture.execution_identity,
            owned_parent_run_id="gtd-unknown-screen-owned-fixture",
            crystal_id=crystal_id,
            output_directory=destination,
        )

    assert not destination.exists()


def test_cli_builds_owned_phase3_a_review_from_exact_execution_evidence(
    tmp_path: Path,
) -> None:
    fixture_root = tmp_path / "public execution"
    fixture_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(fixture_root)
    review_root = tmp_path / "first-copy evidence"
    review_root.mkdir()
    crystal_id = PUBLIC_STUB_CRYSTAL_IDS[0]
    request = _request(review_root, crystal_id=crystal_id)
    review = build_mr_seed_review(request)
    destination = tmp_path / "cli owned A package"

    assert (
        main(
            [
                "--no-progress",
                "review",
                "build-owned-a-package",
                "--review-package",
                str(review.manifest_json.parent),
                "--hypotheses",
                str(request.hypotheses_jsonl),
                "--execution-identity",
                str(fixture.execution_identity),
                "--owned-parent-run",
                "gtd-unknown-screen-owned-fixture",
                "--crystal-id",
                crystal_id,
                "--outdir",
                str(destination),
            ]
        )
        == 0
    )

    assert validate_phase3_review_package(destination).crystal_id == crystal_id


def test_owned_a_review_tasks_keep_crystals_and_no_model_outcomes_independent(
    tmp_path: Path,
) -> None:
    fixture_root = tmp_path / "public execution"
    fixture_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(fixture_root)
    records: list[dict[str, str]] = []
    review_manifests: dict[str, Path] = {}
    for index, crystal_id in enumerate(PUBLIC_STUB_CRYSTAL_IDS):
        root = tmp_path / crystal_id
        root.mkdir()
        request = _request(
            root,
            crystal_id=crystal_id,
            hypothesis_id=f"mrhyp_{format(index + 1, 'x') * 64}",
        )
        if index == 2:
            request.hypotheses_jsonl.write_text("", encoding="utf-8")
            request.results_jsonl.write_text("", encoding="utf-8")
            funnel = json.loads(request.funnel_manifest.read_text(encoding="utf-8"))
            funnel["selected_hypothesis_count"] = 0
            funnel["hypotheses"] = []
            atomic_write_json(request.funnel_manifest, funnel)
        review = build_mr_seed_review(request)
        review_manifests[crystal_id] = review.manifest_json
        records.append(
            {
                "crystal_id": crystal_id,
                "review_package": str(review.manifest_json.parent),
                "hypotheses": str(request.hypotheses_jsonl),
            }
        )
    input_manifest = tmp_path / "complete crystal reviews.json"
    atomic_write_json(input_manifest, {"crystals": records})
    output = tmp_path / "owned A packages"
    command = [
        "nextflow",
        "-C",
        "tests/fixtures/stubs/p6_empty_partner/nextflow.config",
        "run",
        str(STUBS / "phase3_owned_a_review/main.nf"),
        "--review_manifest",
        str(input_manifest),
        "--execution_identity",
        str(fixture.execution_identity),
        "--owned_parent_run_id",
        "gtd-unknown-screen-owned-fixture",
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

    first = subprocess.run(
        command,
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert first.returncode == 0, f"{first.stdout}\n{first.stderr}"
    trace = output / "pipeline_info/trace.tsv"
    with trace.open(encoding="utf-8", newline="") as stream:
        first_rows = tuple(csv.DictReader(stream, delimiter="\t"))
    assert len(first_rows) == 3
    assert {row["status"] for row in first_rows} == {"COMPLETED"}
    for index, crystal_id in enumerate(PUBLIC_STUB_CRYSTAL_IDS):
        package = validate_phase3_review_package(
            output / f"phase3_owned_a_review_{crystal_id}"
        )
        assert package.crystal_id == crystal_id
        assert len(package.permitted_targets) == (0 if index == 2 else 1)

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
    assert {row["hash"] for row in cached} == {row["hash"] for row in first_rows}

    changed_crystal = PUBLIC_STUB_CRYSTAL_IDS[0]
    changed_manifest = review_manifests[changed_crystal]
    changed_document = json.loads(changed_manifest.read_text(encoding="utf-8"))
    changed_html = (
        changed_manifest.parent / changed_document["outputs"]["review_html"]["path"]
    )
    changed_html.write_text(
        changed_html.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    changed_document["outputs"]["review_html"]["sha256"] = sha256_file(
        changed_html,
        progress=False,
    )
    atomic_write_json(changed_manifest, changed_document)

    mutated = subprocess.run(
        [*command, "-resume"],
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert mutated.returncode == 0, f"{mutated.stdout}\n{mutated.stderr}"
    with trace.open(encoding="utf-8", newline="") as stream:
        rerun = tuple(csv.DictReader(stream, delimiter="\t"))
    assert Counter(row["status"] for row in rerun) == {
        "COMPLETED": 1,
        "CACHED": 2,
    }
    changed = next(row for row in rerun if row["status"] == "COMPLETED")
    assert changed_crystal in changed["tag"]


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
    fixture = _registered_phase3_a_seed_fixture(tmp_path, decision=decision)
    output = prepare_phase3_seed_stage(
        fixture.stage_request(tmp_path / "phase3 approved A state")
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
        (fixture.solution_id,) if expected_count else ()
    )
    manifest = json.loads(output.stage_manifest.read_text(encoding="utf-8"))
    provenance = manifest["approval_provenance"]
    assert provenance["crystal_id"] == PUBLIC_STUB_CRYSTAL_IDS[0]
    assert provenance["parent_profile"] == "unknown-screen"
    assert provenance["approved_solution_ids"] == (
        [fixture.solution_id] if expected_count else []
    )
    disposition_field = {
        PhaseIIIReviewDecisionValue.APPROVE: "approved_solution_ids",
        PhaseIIIReviewDecisionValue.REJECT: "rejected_solution_ids",
        PhaseIIIReviewDecisionValue.DEFER: "deferred_solution_ids",
    }[decision]
    assert provenance[disposition_field] == [fixture.solution_id]
    assert provenance["owned_run_registry_id"] == fixture.owned_registry_id
    assert manifest["schema_version"] == "2.0"
    assert manifest["execution_status"] == "completed_success"
    assert set(path.name for path in output.stage_manifest.parent.iterdir()) == set(
        manifest["output_allowlist"]
    )
    for forbidden in (
        "approved_mr_seeds.tsv",
        "validated_mr_seed_decisions.json",
        "live_m4_stage_manifest.json",
    ):
        assert not (output.stage_manifest.parent / forbidden).exists()


def test_phase3_joint_copy_solution_skips_redundant_addition(
    tmp_path: Path,
) -> None:
    fixture = _registered_phase3_a_seed_fixture(
        tmp_path,
        decision=PhaseIIIReviewDecisionValue.APPROVE,
        expected_copies=2,
        placed_copies=2,
    )

    output = prepare_phase3_seed_stage(
        fixture.stage_request(tmp_path / "phase3 joint complete A state")
    )

    assert output.approved_seed_count == 1
    assert output.additional_copy_seed_count == 0
    manifest = json.loads(output.stage_manifest.read_text(encoding="utf-8"))
    source = manifest["model_sources"][fixture.solution_id]
    assert source["expected_copy_count"] == 2
    assert source["placed_copy_count"] == 2
    assert source["requires_additional_copy"] is False


@pytest.mark.parametrize("mutation", ("non-object", "missing-id", "duplicate"))
def test_phase3_a_stage_rejects_tampered_owned_review_inventory(
    tmp_path: Path, mutation: str
) -> None:
    fixture = _registered_phase3_a_seed_fixture(
        tmp_path, decision=PhaseIIIReviewDecisionValue.DEFER
    )
    embedded = fixture.package / "evidence/mr_seed_review_manifest.json"
    document = json.loads(embedded.read_text(encoding="utf-8"))
    if mutation == "non-object":
        document["items"].append(None)
    elif mutation == "missing-id":
        document["items"].append({"hypothesis_id": HYPOTHESIS_ID})
    else:
        document["items"].append(dict(document["items"][0]))
    embedded.write_text(json.dumps(document), encoding="utf-8")
    destination = tmp_path / "nonconserving-a-stage"

    with pytest.raises(ValueError):
        prepare_phase3_seed_stage(fixture.stage_request(destination))

    assert not destination.exists()


@pytest.mark.parametrize("mutation", ("none", "parent", "identity", "registry"))
def test_phase3_a_seed_stage_authenticates_completed_owned_screen(
    tmp_path: Path,
    mutation: str,
) -> None:
    public_root = tmp_path / "public-fixture"
    public_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(public_root)
    parent_run = "gtd-unknown-screen-owned-fixture"
    crystal_id = PUBLIC_STUB_CRYSTAL_IDS[0]
    crystal_root = tmp_path / crystal_id
    crystal_root.mkdir()
    request, _legacy, package, stage, solution_id = _owned_phase3_a_seed_inputs(
        crystal_root,
        crystal_id=crystal_id,
        execution_identity=fixture.execution_identity,
        owned_parent_run_id=parent_run,
        decision=PhaseIIIReviewDecisionValue.APPROVE,
    )
    registry = tmp_path / "completed-screen-registry"
    registry.mkdir()
    record = register_phase3_owned_run(
        parent=OwnedPhaseIIIParentRun(parent_run, "unknown-screen", "phase3-pass1"),
        completed_at=datetime.now(UTC),
        execution_identity=fixture.execution_identity,
        packages=(
            OwnedPhaseIIIReviewPackageSource(
                crystal_id=crystal_id,
                checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
                package_directory=package,
            ),
        ),
        output_directory=registry,
    )
    execution_identity = fixture.execution_identity
    if mutation == "parent":
        parent_run = "gtd-unknown-screen-another-fixture"
    elif mutation == "identity":
        execution_identity = tmp_path / "invalid-execution-identity.json"
        execution_identity.write_text('{"invalid":true}\n', encoding="ascii")
    elif mutation == "registry":
        registry = fixture.owned_run_registry
    output_root = tmp_path / "owned-reviewed-stage"
    stage_request = PhaseIIISeedStageRequest(
        review_stage=stage,
        review_package_manifest=package / "phase3_review_package_manifest.json",
        hypotheses_jsonl=request.hypotheses_jsonl,
        owned_run_registry=registry,
        execution_identity=execution_identity,
        owned_parent_run_id=parent_run,
        output_directory=output_root,
        progress=False,
    )
    if mutation != "none":
        with pytest.raises(ValueError, match=r"owned|ownership"):
            prepare_phase3_seed_stage(stage_request)
        assert not output_root.exists()
        return

    output = prepare_phase3_seed_stage(stage_request)
    provenance = json.loads(output.stage_manifest.read_text(encoding="utf-8"))[
        "approval_provenance"
    ]
    assert provenance["owned_run_registry_id"] == record.owned_run_registry_id
    assert provenance["owned_parent_run_id"] == parent_run
    assert provenance["approved_solution_ids"] == [solution_id]


@pytest.mark.parametrize("failure", ("canonical", "legacy", "stage", "package"))
def test_phase3_a_seed_stage_rejects_cross_evidence_before_publication(
    tmp_path: Path,
    failure: str,
) -> None:
    fixture = _registered_phase3_a_seed_fixture(
        tmp_path, decision=PhaseIIIReviewDecisionValue.APPROVE
    )
    if failure == "canonical":
        decision_path = fixture.review_stage / "phase3_review_decision.json"
        decision_path.write_bytes(decision_path.read_bytes() + b"\n")
    elif failure == "legacy":
        legacy_manifest = fixture.package / "evidence/mr_seed_review_manifest.json"
        legacy_manifest.write_text(
            legacy_manifest.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
    elif failure == "stage":
        (fixture.review_stage / "unexpected.json").write_text("{}\n", encoding="utf-8")
    else:
        evidence = next((fixture.package / "evidence").rglob("*.json"))
        evidence.write_text("{}\n", encoding="utf-8")
    destination = tmp_path / "must-not-publish-a-state"

    with pytest.raises(ValueError):
        prepare_phase3_seed_stage(fixture.stage_request(destination))

    assert not destination.exists()


def test_cli_passes_canonical_phase3_a_approval_to_same_component_stage(
    tmp_path: Path,
) -> None:
    fixture = _registered_phase3_a_seed_fixture(
        tmp_path, decision=PhaseIIIReviewDecisionValue.APPROVE
    )
    destination = tmp_path / "cli reviewed phase3 seed"

    exit_code = main(
        [
            "--no-progress",
            "mr",
            "stage-phase3-seeds",
            "--review-stage",
            str(fixture.review_stage),
            "--review-package-manifest",
            str(fixture.package / "phase3_review_package_manifest.json"),
            "--hypotheses",
            str(fixture.request.hypotheses_jsonl),
            "--owned-run-registry",
            str(fixture.owned_registry),
            "--execution-identity",
            str(fixture.execution_identity),
            "--owned-parent-run",
            fixture.parent_run,
            "--outdir",
            str(destination),
        ]
    )

    assert exit_code == 0
    result = json.loads(
        (destination / "phase3_seed_stage_manifest.json").read_text(encoding="utf-8")
    )
    assert result["approval_provenance"]["approved_solution_ids"] == [
        fixture.solution_id
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
    fixture = _registered_phase3_a_seed_fixture(
        tmp_path,
        decision=decision,
        expected_copies=3,
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
    selection = tmp_path / "selected diffraction.json"
    selection.write_text('{"selection":"reviewed-crystal"}\n', encoding="ascii")
    output = tmp_path / "reviewed-copy-results"
    command = [
        "nextflow",
        "-C",
        "tests/fixtures/stubs/p6_empty_partner/nextflow.config",
        "run",
        str(project / "main.nf"),
        "-stub-run",
        "--review_stage",
        str(fixture.review_stage),
        "--phase3_package",
        str(fixture.package),
        "--hypotheses",
        str(fixture.request.hypotheses_jsonl),
        "--owned_run_registry",
        str(fixture.owned_registry),
        "--execution_identity",
        str(fixture.execution_identity),
        "--owned_parent_run_id",
        fixture.parent_run,
        "--crystal_id",
        PUBLIC_STUB_CRYSTAL_IDS[0],
        "--sequence_groups",
        str(STUBS / "sequence_groups.jsonl"),
        "--preflight",
        str(STUBS / "mtz_preflight.jsonl"),
        "--mtz",
        str(STUBS / "predicted_model_preparation/models/stub.pdb"),
        "--phenix_manifest",
        str(STUBS / "phenix_install_manifest.json"),
        "--diffraction_selection",
        str(selection),
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
        expected_processes["RUN_PHASE3_ADDITIONAL_COPY_PHASER"] = 1
    assert Counter(row["process"].split(":")[-1] for row in first) == expected_processes
    assert {row["status"] for row in first} == {"COMPLETED"}
    staged = json.loads(
        (output / "phase3_seed_stage/phase3_seed_stage_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert staged["approval_provenance"]["approved_solution_ids"] == (
        [fixture.solution_id] if decision is PhaseIIIReviewDecisionValue.APPROVE else []
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


def test_reviewed_crystals_stage_and_resume_without_cross_consuming_decisions(
    tmp_path: Path,
) -> None:
    fixture_root = tmp_path / "public-fixture"
    fixture_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(fixture_root)
    parent_run = "gtd-unknown-screen-owned-fanout"
    single_component_run = "gtd-unknown-single-component-owned-fanout"
    records: list[dict[str, str]] = []
    sources: list[OwnedPhaseIIIReviewPackageSource] = []
    approved_ids: dict[str, str] = {}
    selection_paths: dict[str, Path] = {}
    decisions = (
        (PUBLIC_STUB_CRYSTAL_IDS[0], PhaseIIIReviewDecisionValue.APPROVE, 3),
        (PUBLIC_STUB_CRYSTAL_IDS[1], PhaseIIIReviewDecisionValue.APPROVE, 1),
        (PUBLIC_STUB_CRYSTAL_IDS[2], PhaseIIIReviewDecisionValue.DEFER, 3),
    )
    for crystal_id, decision, expected_copies in decisions:
        root = tmp_path / crystal_id
        root.mkdir()
        request, _legacy, package, stage, solution_id = _owned_phase3_a_seed_inputs(
            root,
            crystal_id=crystal_id,
            execution_identity=fixture.execution_identity,
            owned_parent_run_id=parent_run,
            decision=decision,
            expected_copies=expected_copies,
        )
        sources.append(
            OwnedPhaseIIIReviewPackageSource(
                crystal_id=crystal_id,
                checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
                package_directory=package,
            )
        )
        dispatch = root / "crystal-dispatch"
        dispatch.mkdir()
        (dispatch / "crystal_id.txt").write_text(f"{crystal_id}\n", encoding="ascii")
        copy2(
            STUBS / "predicted_model_preparation/models/stub.pdb",
            dispatch / "input.mtz",
        )
        selection = dispatch / "phase3_diffraction_selection.json"
        selection.write_text(f'{{"crystal":"{crystal_id}"}}\n', encoding="ascii")
        (dispatch / "phase3_free_r_identity.json").write_text(
            f'{{"crystal":"{crystal_id}","free_r":"fixture"}}\n',
            encoding="ascii",
        )
        selection_paths[crystal_id] = selection
        if decision is PhaseIIIReviewDecisionValue.APPROVE:
            approved_ids[crystal_id] = solution_id
        records.append(
            {
                "crystal_id": crystal_id,
                "review_stage": str(stage),
                "phase3_package": str(package),
                "hypotheses": str(request.hypotheses_jsonl),
                "sequence_groups": str(STUBS / "sequence_groups.jsonl"),
                "source_records": str(STUBS / "source_records.jsonl"),
                "preflight": str(STUBS / "mtz_preflight.jsonl"),
                "mtz": str(STUBS / "predicted_model_preparation/models/stub.pdb"),
                "phenix_manifest": str(STUBS / "phenix_install_manifest.json"),
                "dispatch": str(dispatch),
            }
        )

    registry = tmp_path / "owned-screen-registry"
    registry.mkdir()
    register_phase3_owned_run(
        parent=OwnedPhaseIIIParentRun(parent_run, "unknown-screen", "phase3-pass1"),
        completed_at=datetime.now(UTC),
        execution_identity=fixture.execution_identity,
        packages=tuple(sources),
        output_directory=registry,
    )
    input_manifest = tmp_path / "reviewed-crystals.json"
    input_manifest.write_text(json.dumps({"crystals": records}), encoding="ascii")
    project = tmp_path / "nextflow-project"
    project.mkdir()
    source = STUBS / "phase3_multicrystal_reviewed_seed_fanout/main.nf"
    (project / "main.nf").write_text(
        source.read_text(encoding="ascii").replace(
            "'../../../../workflows/",
            f"'{REPOSITORY}/workflows/",
        ),
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
        "brief_refinement_result.json",
        "sequence_map_result.json",
        "t12_command.json",
    ):
        copy2(STUBS / name, local_stubs / name)
    model_root = local_stubs / "predicted_model_preparation/models"
    model_root.mkdir(parents=True)
    copy2(
        STUBS / "predicted_model_preparation/models/stub.pdb", model_root / "stub.pdb"
    )
    scripts = project / "tests/scripts"
    scripts.mkdir()
    copy2(
        REPOSITORY / "tests/scripts/build_phase3_owned_sequence_stub.py",
        scripts / "build_phase3_owned_sequence_stub.py",
    )
    output = tmp_path / "reviewed-crystal-results"
    command = [
        "nextflow",
        "-C",
        "tests/fixtures/stubs/p6_empty_partner/nextflow.config",
        "run",
        str(project / "main.nf"),
        "-stub-run",
        "--reviewed_manifest",
        str(input_manifest),
        "--owned_run_registry",
        str(registry),
        "--execution_identity",
        str(fixture.execution_identity),
        "--owned_parent_run_id",
        parent_run,
        "--owned_sequence_parent_run_id",
        single_component_run,
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

    def run(*, resume: bool = False) -> tuple[dict[str, str], ...]:
        invocation = [*command, *(["-resume"] if resume else [])]
        result = subprocess.run(
            invocation,
            cwd=REPOSITORY,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
        trace = output / "pipeline_info/trace.tsv"
        with trace.open(encoding="utf-8", newline="") as stream:
            return tuple(csv.DictReader(stream, delimiter="\t"))

    first = run()
    assert Counter(row["process"].split(":")[-1] for row in first) == {
        "STAGE_PHASE3_CRYSTAL_APPROVED_MR_SEEDS": 3,
        "RUN_PHASE3_ADDITIONAL_COPY_PHASER": 1,
        "STAGE_PHASE3_CRYSTAL_T12": 2,
        "RUN_PHASE3_BRIEF_REFINEMENT": 2,
        "BUILD_PHASE3_CRYSTAL_SEQUENCE_CHECKPOINT": 2,
        "BUILD_PHASE3_OWNED_COMPOSITION_REVIEW_PACKAGE": 2,
        "BUILD_PHASE3_OWNED_SEQUENCE_REVIEW_PACKAGE": 2,
    }
    assert {row["status"] for row in first} == {"COMPLETED"}
    for crystal_id, decision, expected_copies in decisions:
        stage_manifest = output / (
            f"phase3_seed_stage_{crystal_id}/phase3_seed_stage_manifest.json"
        )
        stage = json.loads(stage_manifest.read_text(encoding="utf-8"))
        assert stage["approval_provenance"]["crystal_id"] == crystal_id
        assert stage["approval_provenance"]["approved_solution_ids"] == (
            [approved_ids[crystal_id]]
            if decision is PhaseIIIReviewDecisionValue.APPROVE
            else []
        )
        assert stage["additional_copy_seed_count"] == (
            1
            if decision is PhaseIIIReviewDecisionValue.APPROVE and expected_copies > 1
            else 0
        )
    untouched_crystal = PUBLIC_STUB_CRYSTAL_IDS[1]
    first_selection = output / (
        f"phase3_t12_{untouched_crystal}_{approved_ids[untouched_crystal]}"
        "/phase3_diffraction_selection.json"
    )
    first_digest = sha256_file(first_selection)
    for crystal_id, solution_id in approved_ids.items():
        refinement = output / f"phase3_t12_{crystal_id}_{solution_id}"
        assert (refinement / "phase3_crystal_id.txt").read_text(encoding="ascii") == (
            f"{crystal_id}\n"
        )
        assert (refinement / "phase3_free_r_identity.json").read_bytes() == (
            (
                selection_paths[crystal_id].parent / "phase3_free_r_identity.json"
            ).read_bytes()
        )
        checkpoint = output / f"phase3_sequence_checkpoint_{crystal_id}"
        manifest = json.loads(
            (checkpoint / "sequence_checkpoint_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        assert manifest["crystal_context"]["crystal_id"] == crystal_id
        assert manifest["finalist_count"] == 1
        assert manifest["automatic_approval"] is False
        assert (checkpoint / "provenance/sequence_groups.jsonl").is_file()
        assert (checkpoint / "provenance/source_records.jsonl").is_file()
        for review_name, checkpoint_type in (
            ("sequence", PhaseIIIReviewCheckpoint.SEQUENCE),
            ("composition", PhaseIIIReviewCheckpoint.COMPOSITION),
        ):
            owned_review = validate_phase3_review_package(
                output / f"phase3_owned_{review_name}_review_{crystal_id}"
            )
            assert owned_review.checkpoint is checkpoint_type
            assert owned_review.owned_parent_run_id == single_component_run
    deferred_crystal = PUBLIC_STUB_CRYSTAL_IDS[2]
    assert not (output / f"phase3_sequence_checkpoint_{deferred_crystal}").exists()
    assert not (output / f"phase3_owned_sequence_review_{deferred_crystal}").exists()
    assert not (output / f"phase3_owned_composition_review_{deferred_crystal}").exists()

    cached = run(resume=True)
    assert {row["status"] for row in cached} == {"CACHED"}
    assert {row["hash"] for row in cached} == {row["hash"] for row in first}

    changed_crystal = PUBLIC_STUB_CRYSTAL_IDS[0]
    selection_paths[changed_crystal].write_text(
        f'{{"crystal":"{changed_crystal}","revision":2}}\n',
        encoding="ascii",
    )
    changed = run(resume=True)
    assert Counter(row["status"] for row in changed) == {"CACHED": 8, "COMPLETED": 6}
    rerun = tuple(row for row in changed if row["status"] == "COMPLETED")
    assert {row["process"].split(":")[-1] for row in rerun} == {
        "RUN_PHASE3_ADDITIONAL_COPY_PHASER",
        "STAGE_PHASE3_CRYSTAL_T12",
        "RUN_PHASE3_BRIEF_REFINEMENT",
        "BUILD_PHASE3_CRYSTAL_SEQUENCE_CHECKPOINT",
        "BUILD_PHASE3_OWNED_COMPOSITION_REVIEW_PACKAGE",
        "BUILD_PHASE3_OWNED_SEQUENCE_REVIEW_PACKAGE",
    }
    assert all(changed_crystal in row["tag"] for row in rerun)
    assert sha256_file(first_selection) == first_digest


@pytest.mark.parametrize("single_component_parent", (None, "gtd-owned-screen"))
def test_phase3_application_requires_distinct_owned_final_review_parent(
    tmp_path: Path,
    single_component_parent: str | None,
) -> None:
    reviewed = tmp_path / "reviewed-crystals.json"
    atomic_write_json(reviewed, {"crystals": []})
    registry = tmp_path / "owned-screen-registry"
    registry.mkdir()
    identity = tmp_path / "execution-identity.json"
    identity.write_text("{}\n", encoding="ascii")
    output = tmp_path / "refused-reviewed-output"
    command = [
        "nextflow",
        "run",
        "phase3_application.nf",
        "-profile",
        "test",
        "-stub-run",
        "-params-file",
        "tests/fixtures/stubs/phase3_application_params.yaml",
        "--phase3_operation",
        "reviewed_single_component",
        "--phase3_reviewed_crystal_manifest",
        str(reviewed),
        "--phase3_owned_run_registry",
        str(registry),
        "--phase3_execution_identity",
        str(identity),
        "--phase3_owned_parent_run_id",
        "gtd-owned-screen",
        "--outdir",
        str(output),
        "--cache_root",
        str(tmp_path / "refused-cache"),
    ]
    if single_component_parent is not None:
        command.extend(
            ("--phase3_owned_sequence_parent_run_id", single_component_parent)
        )
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
        timeout=60,
    )

    assert result.returncode != 0
    assert (
        "Phase III reviewed continuation requires its owned screen and distinct "
        "single-component parent" in f"{result.stdout}\n{result.stderr}"
    )
    assert not tuple(output.glob("phase3_*"))
    trace = output / "pipeline_info/trace.tsv"
    if trace.is_file():
        with trace.open(encoding="utf-8", newline="") as stream:
            assert tuple(csv.DictReader(stream, delimiter="\t")) == ()


def test_application_roots_reject_cross_authority_parameters(tmp_path: Path) -> None:
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
    invocations = (
        (
            [
                "nextflow",
                "run",
                "main.nf",
                "-profile",
                "test",
                "-stub-run",
                "-params-file",
                "tests/fixtures/stubs/main_params.yaml",
                "--analysis_stage",
                "task05",
                "--phase3_operation",
                "first_copy",
                "--outdir",
                str(tmp_path / "legacy-output"),
                "--cache_root",
                str(tmp_path / "legacy-cache"),
            ],
            "Parameter `phase3_operation` was specified",
            tmp_path / "legacy-output",
        ),
        (
            [
                "nextflow",
                "run",
                "phase3_application.nf",
                "-profile",
                "test",
                "-stub-run",
                "-params-file",
                "tests/fixtures/stubs/phase3_application_params.yaml",
                "--phase3_operation",
                "first_copy",
                "--phase3_execution_identity",
                "tests/fixtures/stubs/phenix_install_manifest.json",
                "--phase3_owned_parent_run_id",
                "gtd-test-parent",
                "--phase3_crystallographic_review_stage",
                "tests/fixtures/stubs",
                "--approved_mr_seeds",
                "examples/approvals/approved_mr_seeds.tsv",
                "--outdir",
                str(tmp_path / "phase3-output"),
                "--cache_root",
                str(tmp_path / "phase3-cache"),
            ],
            "Parameter `approved_mr_seeds` was specified",
            tmp_path / "phase3-output",
        ),
    )
    for command, expected_error, output in invocations:
        result = subprocess.run(
            command,
            cwd=REPOSITORY,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert result.returncode != 0
        assert expected_error in f"{result.stdout}\n{result.stderr}"
        trace = output / "pipeline_info/trace.tsv"
        if trace.is_file():
            with trace.open(encoding="utf-8", newline="") as stream:
                assert tuple(csv.DictReader(stream, delimiter="\t")) == ()


@pytest.mark.parametrize("operation", ("provider_discovery", "first_copy"))
def test_phase3_application_refuses_missing_localisation_authority(
    tmp_path: Path,
    operation: str,
) -> None:
    output = tmp_path / f"missing-localisation-{operation}"
    command = [
        "nextflow",
        "run",
        "phase3_application.nf",
        "-profile",
        "test",
        "-stub-run",
        "-params-file",
        "tests/fixtures/stubs/phase3_application_params.yaml",
        "--phase3_operation",
        operation,
        "--phase3_crystallographic_review_stage",
        "tests/fixtures/stubs",
        "--phase3_execution_identity",
        "tests/fixtures/stubs/phenix_install_manifest.json",
        "--phase3_owned_parent_run_id",
        "gtd-missing-localisation-authority",
        "--outdir",
        str(output),
        "--cache_root",
        str(tmp_path / f"missing-localisation-cache-{operation}"),
    ]
    if operation == "provider_discovery":
        command.extend(
            (
                "--afdb_accession_map",
                "tests/fixtures/stubs/empty_afdb_accession_map.tsv",
            )
        )
    else:
        command.extend(
            (
                "--phase3_provider_discovery",
                "tests/fixtures/stubs",
                "--phase3_provider_preparation",
                "tests/fixtures/stubs",
            )
        )
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
        timeout=60,
    )

    assert result.returncode != 0
    expected = {
        "provider_discovery": (
            "Phase III provider discovery requires its crystallographic review, "
            "AFDB policy, and localisation/gel authorities only"
        ),
        "first_copy": (
            "Phase III first-copy requires its crystallographic review, owned "
            "provider, and localisation/gel authorities only"
        ),
    }
    assert expected[operation] in f"{result.stdout}\n{result.stderr}"
    trace = output / "pipeline_info/trace.tsv"
    if trace.is_file():
        with trace.open(encoding="utf-8", newline="") as stream:
            assert tuple(csv.DictReader(stream, delimiter="\t")) == ()


def test_phase3_application_continues_owned_reviewed_crystals_independently(
    tmp_path: Path,
) -> None:
    fixture_root = tmp_path / "public-fixture"
    fixture_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(fixture_root)
    parent_run = "gtd-unknown-screen-production-fixture"
    single_component_run = "gtd-unknown-single-component-production-fixture"
    routes: list[dict[str, str]] = []
    sources: list[OwnedPhaseIIIReviewPackageSource] = []
    stages: dict[str, tuple[Path, Path]] = {}
    dispositions = (
        (PhaseIIIReviewDecisionValue.APPROVE, 3),
        (PhaseIIIReviewDecisionValue.APPROVE, 1),
        (PhaseIIIReviewDecisionValue.DEFER, 3),
    )
    for crystal_id, (decision, expected_copies) in zip(
        PUBLIC_STUB_CRYSTAL_IDS, dispositions, strict=True
    ):
        root = tmp_path / crystal_id
        root.mkdir()
        request, _legacy, package, stage, _ = _owned_phase3_a_seed_inputs(
            root,
            crystal_id=crystal_id,
            execution_identity=fixture.execution_identity,
            owned_parent_run_id=parent_run,
            decision=decision,
            expected_copies=expected_copies,
        )
        routes.append(
            {
                "crystal_id": crystal_id,
                "review_stage": str(stage),
                "hypotheses": str(request.hypotheses_jsonl),
            }
        )
        sources.append(
            OwnedPhaseIIIReviewPackageSource(
                crystal_id=crystal_id,
                checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
                package_directory=package,
            )
        )
        stages[crystal_id] = (stage, package)

    registry = tmp_path / "completed-screen-registry"
    registry.mkdir()
    record = register_phase3_owned_run(
        parent=OwnedPhaseIIIParentRun(parent_run, "unknown-screen", "phase3-pass1"),
        completed_at=datetime.now(UTC),
        execution_identity=fixture.execution_identity,
        packages=tuple(sources),
        output_directory=registry,
    )
    manifest = tmp_path / "reviewed-crystals.json"
    atomic_write_json(manifest, {"crystals": routes})
    template = json.loads(
        (REPOSITORY / "examples/crystal_manifest.json").read_text(encoding="utf-8")
    )["crystals"][0]
    crystals = tmp_path / "three-crystals.json"
    atomic_write_json(
        crystals,
        {
            "schema_version": "1.0",
            "crystals": [
                {**template, "crystal_id": item.crystal_id, "mtz": str(item.mtz)}
                for item in fixture.crystals
            ],
        },
    )
    output = tmp_path / "production-reviewed-results"
    command = [
        "nextflow",
        "run",
        "phase3_application.nf",
        "-profile",
        "test",
        "-stub-run",
        "-params-file",
        "tests/fixtures/stubs/phase3_application_params.yaml",
        "--phase3_operation",
        "reviewed_single_component",
        "--crystals",
        str(crystals),
        "--phase3_reviewed_crystal_manifest",
        str(manifest),
        "--phase3_owned_run_registry",
        str(registry),
        "--phase3_execution_identity",
        str(fixture.execution_identity),
        "--phase3_owned_parent_run_id",
        parent_run,
        "--phase3_owned_sequence_parent_run_id",
        single_component_run,
        "--outdir",
        str(output),
        "--cache_root",
        str(tmp_path / "production-cache"),
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

    def run(*, resume: bool = False) -> tuple[dict[str, str], ...]:
        invocation = [*command, *(["-resume"] if resume else [])]
        result = subprocess.run(
            invocation,
            cwd=REPOSITORY,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=240,
        )
        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
        with (output / "pipeline_info/trace.tsv").open(
            encoding="utf-8", newline=""
        ) as stream:
            return tuple(csv.DictReader(stream, delimiter="\t"))

    first = run()
    assert Counter(row["process"].split(":")[-1] for row in first) == {
        "VALIDATE_TASK05_INPUTS": 1,
        "IMPORT_CATALOGUES": 1,
        "MTZ_PREFLIGHT": 1,
        "DISPATCH_CRYSTAL_ITEM": 3,
        "STAGE_PHASE3_CRYSTAL_APPROVED_MR_SEEDS": 3,
        "RUN_PHASE3_ADDITIONAL_COPY_PHASER": 1,
        "STAGE_PHASE3_CRYSTAL_T12": 2,
        "RUN_PHASE3_BRIEF_REFINEMENT": 2,
        "BUILD_PHASE3_CRYSTAL_SEQUENCE_CHECKPOINT": 2,
        "BUILD_PHASE3_OWNED_COMPOSITION_REVIEW_PACKAGE": 2,
        "BUILD_PHASE3_OWNED_SEQUENCE_REVIEW_PACKAGE": 2,
    }
    assert {row["status"] for row in first} == {"COMPLETED"}
    for crystal_id in PUBLIC_STUB_CRYSTAL_IDS:
        approved = json.loads(
            (
                output
                / f"phase3_seed_stage_{crystal_id}/phase3_seed_stage_manifest.json"
            ).read_text(encoding="utf-8")
        )
        assert approved["approval_provenance"]["owned_run_registry_id"] == (
            record.owned_run_registry_id
        )
    for crystal_id in PUBLIC_STUB_CRYSTAL_IDS[:2]:
        checkpoint = output / f"phase3_sequence_checkpoint_{crystal_id}"
        document = json.loads(
            (checkpoint / "sequence_checkpoint_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        assert document["crystal_context"]["crystal_id"] == crystal_id
        assert document["finalist_count"] == 1
        assert document["automatic_approval"] is False
        assert (checkpoint / "provenance/sequence_groups.jsonl").is_file()
        owned_review = validate_phase3_review_package(
            output / f"phase3_owned_sequence_review_{crystal_id}"
        )
        assert owned_review.checkpoint is PhaseIIIReviewCheckpoint.SEQUENCE
        assert owned_review.crystal_id == crystal_id
        assert owned_review.owned_parent_run_id == single_component_run
        assert owned_review.parent_profile == "unknown-single-component"
        assert len(owned_review.permitted_targets) == 1
        composition_review = validate_phase3_review_package(
            output / f"phase3_owned_composition_review_{crystal_id}"
        )
        assert composition_review.checkpoint is PhaseIIIReviewCheckpoint.COMPOSITION
        assert composition_review.crystal_id == crystal_id
        assert composition_review.owned_parent_run_id == single_component_run
        assert composition_review.parent_profile == "unknown-single-component"
        assert len(composition_review.permitted_targets) == 1
    assert not (
        output / f"phase3_sequence_checkpoint_{PUBLIC_STUB_CRYSTAL_IDS[2]}"
    ).exists()
    assert not (
        output / f"phase3_owned_sequence_review_{PUBLIC_STUB_CRYSTAL_IDS[2]}"
    ).exists()
    assert not (
        output / f"phase3_owned_composition_review_{PUBLIC_STUB_CRYSTAL_IDS[2]}"
    ).exists()
    cached = run(resume=True)
    assert {row["status"] for row in cached} == {"CACHED"}
    assert {row["hash"] for row in cached} == {row["hash"] for row in first}

    crystal_id = PUBLIC_STUB_CRYSTAL_IDS[0]
    original_stage, package = stages[crystal_id]
    original = PhaseIIIReviewDecisionFile.model_validate_json(
        (original_stage / "phase3_review_decision.json").read_bytes()
    )
    revised = PhaseIIIReviewDecisionFile.from_content(
        checkpoint=original.checkpoint,
        owned_parent_run_id=original.owned_parent_run_id,
        review_package_id=original.review_package_id,
        review_package_manifest_sha256=original.review_package_manifest_sha256,
        decisions=(
            original.decisions[0].model_copy(
                update={"comment": "reviewed once more by the supervisor"}
            ),
        ),
    )
    revised_source = tmp_path / "revised-a-decisions.json"
    atomic_write_json(
        revised_source, revised.model_dump(mode="json", exclude_none=False)
    )
    revised_stage = stage_phase3_review_decisions(
        PhaseIIIReviewStageRequest(
            parent=OwnedPhaseIIIParentRun(parent_run, "unknown-screen", "phase3-pass1"),
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            review_package_manifest=package / "phase3_review_package_manifest.json",
            decisions=revised_source,
            confirmed_decisions_sha256=sha256_file(revised_source),
            output_directory=tmp_path / "revised-a-stage",
            progress=False,
        )
    )
    routes[0]["review_stage"] = str(revised_stage.stage_manifest.parent)
    atomic_write_json(manifest, {"crystals": routes})
    changed = run(resume=True)
    rerun = tuple(row for row in changed if row["status"] == "COMPLETED")
    assert Counter(row["process"].split(":")[-1] for row in rerun) == {
        "STAGE_PHASE3_CRYSTAL_APPROVED_MR_SEEDS": 1,
        "RUN_PHASE3_ADDITIONAL_COPY_PHASER": 1,
        "STAGE_PHASE3_CRYSTAL_T12": 1,
        "BUILD_PHASE3_CRYSTAL_SEQUENCE_CHECKPOINT": 1,
        "BUILD_PHASE3_OWNED_COMPOSITION_REVIEW_PACKAGE": 1,
        "BUILD_PHASE3_OWNED_SEQUENCE_REVIEW_PACKAGE": 1,
    }
    assert all(crystal_id in row["tag"] for row in rerun)


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
