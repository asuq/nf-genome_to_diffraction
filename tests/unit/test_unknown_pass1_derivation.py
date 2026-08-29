"""Tests for evidence-derived unknown-pass-1 terminal records."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.reporting import (
    UnknownPass1AssessmentDerivationRequest,
    derive_unknown_pass1_assessment,
)
from genome_to_diffraction.reporting.unknown_pass1 import (
    UnknownPass1EvidenceSource,
    _validate_review_sources,
    _validate_scientific_sources,
)
from genome_to_diffraction.review import (
    OwnedPhaseIIIParentRun,
    OwnedPhaseIIIReviewPackageSource,
    PhaseIIIReviewEvidenceSource,
    PhaseIIIReviewPackageRequest,
    build_owned_phase3_composition_review_package,
    build_owned_phase3_sequence_review_package,
    build_phase3_review_package,
    register_phase3_owned_run,
)
from genome_to_diffraction.review.sequence_checkpoint import (
    build_live_sequence_checkpoint,
)
from genome_to_diffraction.schemas.results import NormalisedMrResult
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecision,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
    UnknownPass1CollectedFileKind,
    UnknownPass1CrystalAssessment,
)
from genome_to_diffraction.status import ExecutionStatus
from tests.support.unknown_pass1_fixture import (
    materialise_unknown_pass1_public_fixture,
)
from tests.unit.test_sequence_checkpoint import (
    _phase3_live_request,
    _phase3_sequence_execution,
)


def test_zero_model_screen_derives_no_supported_candidate(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(fixture_root)
    crystal_id = fixture.crystals[0].crystal_id
    screen_run = "gtd-unknown-screen-20260828T000000Z-aaaaaaaaaaaa-bbbbbbbb"
    single_run = "gtd-unknown-single-component-20260828T000100Z-aaaaaaaaaaaa-cccccccc"
    evidence_root = tmp_path / "a-evidence"
    evidence_root.mkdir()
    (evidence_root / "mr_seed_review_manifest.json").write_text(
        '{"schema_version":"1.0","review_package_kind":"mr_seed",'
        '"checkpoint":"mr_seed","candidate_count":0,'
        '"inspectable_solution_count":0,"items":[],'
        '"execution_status":"completed_success"}\n',
        encoding="ascii",
    )
    package_root = tmp_path / "a-package"
    package_root.mkdir()
    a_package = build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            owned_parent_run_id=screen_run,
            parent_profile="unknown-screen",
            parent_phase="phase3-pass1",
            execution_identity_id=(
                fixture.inventory.execution_identity.execution_identity_id
            ),
            crystal_id=crystal_id,
            target_item_ids=(),
            created_at=datetime(2026, 8, 28, tzinfo=UTC),
            input_root=evidence_root,
            evidence_sources=(
                PhaseIIIReviewEvidenceSource(
                    role="mr_seed_review_manifest",
                    relative_path="mr_seed_review_manifest.json",
                ),
            ),
            output_directory=package_root,
        )
    )
    screen_registry = tmp_path / "screen-registry"
    screen_registry.mkdir()
    register_phase3_owned_run(
        parent=OwnedPhaseIIIParentRun(
            screen_run,
            "unknown-screen",
            "phase3-pass1",
        ),
        completed_at=datetime(2026, 8, 28, 1, tzinfo=UTC),
        execution_identity=fixture.execution_identity,
        packages=(
            OwnedPhaseIIIReviewPackageSource(
                crystal_id=crystal_id,
                checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
                package_directory=a_package.manifest.parent,
            ),
        ),
        output_directory=screen_registry,
    )
    sibling_crystal = fixture.crystals[1].crystal_id
    sibling_package = _generic_package(
        tmp_path,
        name="sibling-sequence-package",
        checkpoint=PhaseIIIReviewCheckpoint.SEQUENCE,
        parent_run=single_run,
        parent_profile="unknown-single-component",
        execution_identity_id=fixture.inventory.execution_identity.execution_identity_id,
        crystal_id=sibling_crystal,
        item_id=f"seq_{'1' * 64}",
    )
    single_registry = tmp_path / "single-registry"
    single_registry.mkdir()
    register_phase3_owned_run(
        parent=OwnedPhaseIIIParentRun(
            single_run,
            "unknown-single-component",
            "phase3-pass1",
        ),
        completed_at=datetime(2026, 8, 28, 2, tzinfo=UTC),
        execution_identity=fixture.execution_identity,
        packages=(
            OwnedPhaseIIIReviewPackageSource(
                crystal_id=sibling_crystal,
                checkpoint=PhaseIIIReviewCheckpoint.SEQUENCE,
                package_directory=sibling_package.manifest.parent,
            ),
        ),
        output_directory=single_registry,
    )
    job_result = tmp_path / "job-result.json"
    atomic_write_json(
        job_result,
        {
            "run_id": single_run,
            "profile": "unknown-single-component",
            "scheduler_state": "COMPLETED",
            "failure_class": "success",
            "exit_code": 0,
        },
    )
    run_manifest = _run_manifest(
        tmp_path / "run-manifest.json",
        run_id=single_run,
        profile="unknown-single-component",
        execution_identity=fixture.execution_identity,
    )
    decision = (
        fixture.review_stage / "stages" / crystal_id / "phase3_review_decision.json"
    )

    output = derive_unknown_pass1_assessment(
        UnknownPass1AssessmentDerivationRequest(
            crystal_id=crystal_id,
            execution_identity=fixture.execution_identity,
            run_manifest=run_manifest,
            job_result=job_result,
            crystallographic_registry=fixture.owned_run_registry,
            crystallographic_decision=decision,
            screen_registry=screen_registry,
            a_seed_decision=None,
            single_component_registry=single_registry,
            sequence_decision=None,
            composition_decision=None,
            copy_assessment=None,
            packing_result=None,
            combined_coordinate=None,
            refinement_result=None,
            sequence_result=None,
            refined_coordinate=None,
            refined_mtz=None,
            review_map=None,
            output_directory=tmp_path / "derived",
        )
    )

    assessment = UnknownPass1CrystalAssessment.model_validate_json(
        output.assessment.read_bytes()
    )
    assert assessment.scientific_status.value == "no_supported_catalogue_candidate"
    assert assessment.candidate_shortlist_present is False
    assert assessment.solution_evidence is None
    assert assessment.owned_parent_run_id == single_run


def _run_manifest(
    path: Path,
    *,
    run_id: str,
    profile: str,
    execution_identity: Path,
) -> Path:
    identity = json.loads(execution_identity.read_text(encoding="utf-8"))
    atomic_write_json(
        path,
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "site_id": "marmic",
            "profile": profile,
            "commit": identity["source_commit"],
            "nf_helper_commit": identity["nf_helper_commit"],
            "pixi_lock_sha256": identity["pixi_lock_sha256"],
            "source_snapshot_status": "immutable",
        },
    )
    return path


def _decision_file(
    path: Path,
    *,
    package,
    checkpoint: PhaseIIIReviewCheckpoint,
    parent_run: str,
    crystal_id: str,
    item_id: str,
    decision: PhaseIIIReviewDecisionValue,
) -> Path:
    record = PhaseIIIReviewDecisionFile.from_content(
        checkpoint=checkpoint,
        owned_parent_run_id=parent_run,
        review_package_id=package.review_package_id,
        review_package_manifest_sha256=sha256_file(package.manifest),
        decisions=(
            PhaseIIIReviewDecision(
                crystal_id=crystal_id,
                item_id=item_id,
                decision=decision,
                reviewer="reviewer",
                reviewed_at=datetime.now(UTC),
                reason="owned evidence inspected",
            ),
        ),
    )
    atomic_write_json(path, record.model_dump(mode="json", exclude_none=False))
    return path


def _generic_package(
    root: Path,
    *,
    name: str,
    checkpoint: PhaseIIIReviewCheckpoint,
    parent_run: str,
    parent_profile: str,
    execution_identity_id: str,
    crystal_id: str,
    item_id: str,
    extra_sources: tuple[Path, ...] = (),
):
    evidence = root / f"{name}-evidence"
    evidence.mkdir()
    (evidence / "evidence.json").write_text(
        '{"status":"review_required"}\n',
        encoding="ascii",
    )
    evidence_sources = [
        PhaseIIIReviewEvidenceSource(
            role="review_evidence",
            relative_path="evidence.json",
        )
    ]
    for index, source in enumerate(extra_sources, start=1):
        destination = evidence / f"scientific_{index:02d}{source.suffix}"
        destination.write_bytes(source.read_bytes())
        evidence_sources.append(
            PhaseIIIReviewEvidenceSource(
                role=f"scientific_evidence_{index:02d}",
                relative_path=destination.name,
            )
        )
    output = root / name
    output.mkdir()
    return build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=checkpoint,
            owned_parent_run_id=parent_run,
            parent_profile=parent_profile,
            parent_phase="phase3-pass1",
            execution_identity_id=execution_identity_id,
            crystal_id=crystal_id,
            target_item_ids=(item_id,),
            created_at=datetime(2026, 8, 28, 1, tzinfo=UTC),
            input_root=evidence,
            evidence_sources=tuple(evidence_sources),
            output_directory=output,
        )
    )


def test_credible_solution_is_derived_from_owned_scientific_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint_request = _phase3_live_request(tmp_path)
    checkpoint = build_live_sequence_checkpoint(checkpoint_request)
    execution_identity = _phase3_sequence_execution(tmp_path, checkpoint_request)
    identity = json.loads(execution_identity.read_text(encoding="utf-8"))
    execution_identity_id = str(identity["execution_identity_id"])
    crystal_id = str(checkpoint_request.crystal_id)
    result_root = checkpoint_request.candidate_result_directories[0]
    refinement = json.loads(
        (result_root / "brief_refinement_result.json").read_text(encoding="utf-8")
    )
    sequence = json.loads(
        (result_root / "sequence_map_result.json").read_text(encoding="utf-8")
    )
    state_id = str(refinement["seed_solution_id"])
    sequence_group_id = str(sequence["candidates"][0]["sequence_group_id"])
    assessments = tuple(
        line
        for line in (checkpoint_request.stage_bundle / "copy_count_assessments.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if json.loads(line)["seed_solution_id"] == state_id
    )
    assert len(assessments) == 1
    copy_record = json.loads(assessments[0])
    assert copy_record["seed_solution_id"] == state_id
    assert copy_record["best_supported_copy_count"] == refinement["input_copy_count"]
    copy_assessment = checkpoint_request.stage_bundle / "copy_count_assessments.jsonl"
    combined = checkpoint_request.stage_bundle / f"parents/{state_id}/parent.pdb"
    packing = NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=str(copy_record["hypothesis_id"]),
        tool_version="fixture",
        execution_status=ExecutionStatus.COMPLETED_HIT,
        llg=100,
        tfz=10,
        placed_copy_count=int(refinement["input_copy_count"]),
        packing_summary={
            "top_solution_packed": True,
            "packed_solution_count": 1,
        },
        solution_coordinate_path=combined.name,
        solution_coordinate_sha256=sha256_file(combined),
        raw_log_pointer="PHASER.log",
    )
    packing_path = tmp_path / "packing.json"
    packing_path.write_text(
        f"{canonical_json_text(packing)}\n",
        encoding="utf-8",
    )
    screen_run = "gtd-unknown-screen-20260828T000000Z-aaaaaaaaaaaa-bbbbbbbb"
    single_run = "gtd-unknown-single-component-20260828T000100Z-aaaaaaaaaaaa-cccccccc"
    crystal_run = "phase3-crystallographic-review-test"

    crystal_package = _generic_package(
        tmp_path,
        name="crystal-package",
        checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        parent_run=crystal_run,
        parent_profile="unknown-crystallographic-review",
        execution_identity_id=execution_identity_id,
        crystal_id=crystal_id,
        item_id=f"{crystal_id}_review",
    )
    crystal_registry = tmp_path / "crystal-registry"
    crystal_registry.mkdir()
    register_phase3_owned_run(
        parent=OwnedPhaseIIIParentRun(
            crystal_run,
            "unknown-crystallographic-review",
            "phase3-pass1",
        ),
        completed_at=datetime(2026, 8, 28, tzinfo=UTC),
        execution_identity=execution_identity,
        packages=(
            OwnedPhaseIIIReviewPackageSource(
                crystal_id=crystal_id,
                checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
                package_directory=crystal_package.manifest.parent,
            ),
        ),
        output_directory=crystal_registry,
    )
    crystal_decision = _decision_file(
        tmp_path / "crystal-decision.json",
        package=crystal_package,
        checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        parent_run=crystal_run,
        crystal_id=crystal_id,
        item_id=f"{crystal_id}_review",
        decision=PhaseIIIReviewDecisionValue.PROCEED,
    )

    a_package = _generic_package(
        tmp_path,
        name="a-package",
        checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
        parent_run=screen_run,
        parent_profile="unknown-screen",
        execution_identity_id=execution_identity_id,
        crystal_id=crystal_id,
        item_id=state_id,
        extra_sources=(packing_path, combined),
    )
    screen_registry = tmp_path / "screen-registry"
    screen_registry.mkdir()
    register_phase3_owned_run(
        parent=OwnedPhaseIIIParentRun(screen_run, "unknown-screen", "phase3-pass1"),
        completed_at=datetime(2026, 8, 28, 2, tzinfo=UTC),
        execution_identity=execution_identity,
        packages=(
            OwnedPhaseIIIReviewPackageSource(
                crystal_id=crystal_id,
                checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
                package_directory=a_package.manifest.parent,
            ),
        ),
        output_directory=screen_registry,
    )
    a_decision = _decision_file(
        tmp_path / "a-decision.json",
        package=a_package,
        checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
        parent_run=screen_run,
        crystal_id=crystal_id,
        item_id=state_id,
        decision=PhaseIIIReviewDecisionValue.APPROVE,
    )

    sequence_package = build_owned_phase3_sequence_review_package(
        sequence_checkpoint=checkpoint.manifest_json.parent,
        execution_identity=execution_identity,
        owned_parent_run_id=single_run,
        crystal_id=crystal_id,
        output_directory=tmp_path / "sequence-package",
    )
    composition_package = build_owned_phase3_composition_review_package(
        sequence_checkpoint=checkpoint.manifest_json.parent,
        execution_identity=execution_identity,
        owned_parent_run_id=single_run,
        crystal_id=crystal_id,
        output_directory=tmp_path / "composition-package",
    )
    single_registry = tmp_path / "single-registry"
    single_registry.mkdir()
    register_phase3_owned_run(
        parent=OwnedPhaseIIIParentRun(
            single_run,
            "unknown-single-component",
            "phase3-pass1",
        ),
        completed_at=datetime(2026, 8, 28, 4, tzinfo=UTC),
        execution_identity=execution_identity,
        packages=(
            OwnedPhaseIIIReviewPackageSource(
                crystal_id=crystal_id,
                checkpoint=PhaseIIIReviewCheckpoint.SEQUENCE,
                package_directory=sequence_package.manifest.parent,
            ),
            OwnedPhaseIIIReviewPackageSource(
                crystal_id=crystal_id,
                checkpoint=PhaseIIIReviewCheckpoint.COMPOSITION,
                package_directory=composition_package.manifest.parent,
            ),
        ),
        output_directory=single_registry,
    )
    sequence_decision = _decision_file(
        tmp_path / "sequence-decision.json",
        package=sequence_package,
        checkpoint=PhaseIIIReviewCheckpoint.SEQUENCE,
        parent_run=single_run,
        crystal_id=crystal_id,
        item_id=sequence_group_id,
        decision=PhaseIIIReviewDecisionValue.APPROVE,
    )
    composition_decision = _decision_file(
        tmp_path / "composition-decision.json",
        package=composition_package,
        checkpoint=PhaseIIIReviewCheckpoint.COMPOSITION,
        parent_run=single_run,
        crystal_id=crystal_id,
        item_id=state_id,
        decision=PhaseIIIReviewDecisionValue.APPROVE,
    )

    job_result = tmp_path / "single-job-result.json"
    atomic_write_json(
        job_result,
        {
            "run_id": single_run,
            "profile": "unknown-single-component",
            "scheduler_state": "COMPLETED",
            "failure_class": "success",
            "exit_code": 0,
        },
    )
    run_manifest = _run_manifest(
        tmp_path / "single-run-manifest.json",
        run_id=single_run,
        profile="unknown-single-component",
        execution_identity=execution_identity,
    )

    output = derive_unknown_pass1_assessment(
        UnknownPass1AssessmentDerivationRequest(
            crystal_id=crystal_id,
            execution_identity=execution_identity,
            run_manifest=run_manifest,
            job_result=job_result,
            crystallographic_registry=crystal_registry,
            crystallographic_decision=crystal_decision,
            screen_registry=screen_registry,
            a_seed_decision=a_decision,
            single_component_registry=single_registry,
            sequence_decision=sequence_decision,
            composition_decision=composition_decision,
            copy_assessment=copy_assessment,
            packing_result=packing_path,
            combined_coordinate=combined,
            refinement_result=result_root / "brief_refinement_result.json",
            sequence_result=result_root / "sequence_map_result.json",
            refined_coordinate=result_root / str(refinement["refined_model_path"]),
            refined_mtz=result_root / str(refinement["refined_mtz_path"]),
            review_map=result_root / str(refinement["map_path"]),
            output_directory=tmp_path / "credible-derived",
        )
    )

    assessment = UnknownPass1CrystalAssessment.model_validate_json(
        output.assessment.read_bytes()
    )
    assert assessment.scientific_status.value == "credible_single_component_solution"
    assert assessment.solution_evidence is not None
    derivation = json.loads(output.evidence_manifest.read_text(encoding="utf-8"))
    sources = [
        (
            UnknownPass1EvidenceSource(
                crystal_id=crystal_id,
                kind=UnknownPass1CollectedFileKind(item["kind"]),
                role=item["role"],
                relative_path=item["relative_path"],
                sha256=item["sha256"],
                size_bytes=item["size_bytes"],
            ),
            output.evidence_manifest.parent / item["relative_path"],
        )
        for item in derivation["evidence"]
    ]
    package_digests = _validate_review_sources(assessment, sources)
    solution = assessment.solution_evidence
    assert solution is not None
    packaged = set().union(*package_digests.values())
    expected = {
        solution.copy_support_evidence_sha256,
        solution.packing_evidence_sha256,
        solution.combined_coordinate_sha256,
        solution.refined_coordinate_sha256,
        solution.refined_mtz_sha256,
        solution.review_map_sha256,
        solution.refinement_evidence_sha256,
        solution.sequence_evidence_sha256,
    }
    assert expected <= packaged, expected - packaged
    # This fixture exercises owned provenance and typed record joins. The
    # collector's independent Gemmi asset validation has dedicated real-file
    # coverage in test_unknown_pass1_collection.py.
    monkeypatch.setattr(
        "genome_to_diffraction.reporting.unknown_pass1._validate_scientific_assets",
        lambda **_: None,
    )
    _validate_scientific_sources(assessment, sources, package_digests)
