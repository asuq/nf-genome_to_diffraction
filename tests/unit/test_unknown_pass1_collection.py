"""Focused tests for the checksum-closed unknown-pass terminal collector."""

import hashlib
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import gemmi
import numpy as np
import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_bytes
from genome_to_diffraction.reporting.unknown_pass1 import (
    PHASE3_UNKNOWN_CRYSTAL_IDS,
    UnknownPass1AssessmentSource,
    UnknownPass1CollectionError,
    UnknownPass1CollectionRequest,
    UnknownPass1EvidenceSource,
    collect_unknown_pass1_panel,
)
from genome_to_diffraction.review import (
    PhaseIIIReviewEvidenceSource,
    PhaseIIIReviewPackageRequest,
    build_phase3_review_package,
)
from genome_to_diffraction.schemas.base import ContractModel
from genome_to_diffraction.schemas.results import (
    BriefRefinementResult,
    CopyCountAssessment,
    NormalisedMrResult,
    SequenceMapCandidate,
    SequenceMapResult,
)
from genome_to_diffraction.schemas.v2 import (
    UnknownPass1CollectedFileKind,
    UnknownPass1CrystalAssessment,
    UnknownPass1CrystalChecksumManifest,
    UnknownPass1FinalMetricsEvidence,
    UnknownPass1PanelSummary,
    UnknownPass1ResidualContentState,
    UnknownPass1ReviewEvidence,
    UnknownPass1ScientificStatus,
    UnknownPass1SolutionEvidence,
    UnknownPass1TerminalEvidence,
)
from genome_to_diffraction.schemas.v2.review import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecision,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
)
from genome_to_diffraction.status import ExecutionStatus

PARENT_RUN = "phase3_unknown_pass1_owned"
EXECUTION_ID = f"phase3exec_{hashlib.sha256(b'execution').hexdigest()}"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _write_artifact(
    root: Path,
    *,
    crystal_id: str,
    role: str,
    kind: UnknownPass1CollectedFileKind,
    payload: bytes | None = None,
    extension: str = "txt",
) -> UnknownPass1EvidenceSource:
    relative_path = f"evidence/{crystal_id}/{role}.{extension}"
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        payload if payload is not None else f"{crystal_id}|{role}\n".encode("ascii")
    )
    return UnknownPass1EvidenceSource(
        crystal_id=crystal_id,
        kind=kind,
        role=role,
        relative_path=relative_path,
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def _updated_source(
    root: Path,
    source: UnknownPass1EvidenceSource,
) -> UnknownPass1EvidenceSource:
    path = root / source.relative_path
    return replace(source, sha256=sha256_file(path), size_bytes=path.stat().st_size)


def _result_record(
    root: Path,
    *,
    crystal_id: str,
    role: str,
    record: ContractModel,
) -> UnknownPass1EvidenceSource:
    return _write_artifact(
        root,
        crystal_id=crystal_id,
        role=role,
        kind=UnknownPass1CollectedFileKind.RESULT,
        payload=canonical_json_bytes(record) + b"\n",
        extension="json",
    )


def _coordinate(
    root: Path,
    *,
    crystal_id: str,
    role: str,
) -> UnknownPass1EvidenceSource:
    model = Path(
        "tests/fixtures/stubs/predicted_model_preparation/models/stub.pdb"
    ).read_bytes()
    return _write_artifact(
        root,
        crystal_id=crystal_id,
        role=role,
        kind=UnknownPass1CollectedFileKind.RESULT,
        payload=f"REMARK {crystal_id} {role}\n".encode("ascii") + model,
        extension="pdb",
    )


def _refined_mtz(root: Path, *, crystal_id: str) -> UnknownPass1EvidenceSource:
    source = _write_artifact(
        root,
        crystal_id=crystal_id,
        role="refined_mtz",
        kind=UnknownPass1CollectedFileKind.RESULT,
        payload=b"",
        extension="mtz",
    )
    mtz = gemmi.Mtz(with_base=True)
    mtz.spacegroup = gemmi.find_spacegroup_by_name("P 1")
    mtz.set_cell_for_all(gemmi.UnitCell(40, 50, 60, 90, 90, 90))
    dataset = mtz.add_dataset(crystal_id)
    for label, kind in (
        ("F", "F"),
        ("SIGF", "Q"),
        ("FreeR_flag", "I"),
        ("2FOFCWT", "F"),
        ("PH2FOFCWT", "P"),
        ("FOFCWT", "F"),
        ("PHFOFCWT", "P"),
    ):
        mtz.add_column(label, kind, dataset.id)
    mtz.set_data(
        np.asarray(
            (
                (1, 0, 0, 100, 10, 0, 95, 15, 12, 35),
                (0, 1, 0, 80, 8, 1, 77, 20, 9, 40),
            ),
            dtype=np.float32,
        )
    )
    mtz.update_reso()
    mtz.write_to_file(str(root / source.relative_path))
    return _updated_source(root, source)


def _review_map(root: Path, *, crystal_id: str) -> UnknownPass1EvidenceSource:
    source = _write_artifact(
        root,
        crystal_id=crystal_id,
        role="review_map",
        kind=UnknownPass1CollectedFileKind.RESULT,
        payload=b"",
        extension="ccp4",
    )
    grid = gemmi.FloatGrid(4, 4, 4)
    grid.spacegroup = gemmi.find_spacegroup_by_name("P 1")
    grid.unit_cell = gemmi.UnitCell(40, 50, 60, 90, 90, 90)
    grid.fill(float(len(crystal_id)))
    review_map = gemmi.Ccp4Map()
    review_map.grid = grid
    review_map.update_ccp4_header(2, True)
    review_map.write_ccp4_map(str(root / source.relative_path))
    return _updated_source(root, source)


def _review(
    root: Path,
    evidence: list[UnknownPass1EvidenceSource],
    *,
    crystal_id: str,
    checkpoint: PhaseIIIReviewCheckpoint,
    item_id: str,
    decision: PhaseIIIReviewDecisionValue,
    package_sources: tuple[UnknownPass1EvidenceSource, ...] = (),
) -> UnknownPass1ReviewEvidence:
    prefix = f"{checkpoint.value}_{item_id}"
    review_root = root / "reviews" / crystal_id / prefix
    source_root = review_root / "source"
    source_root.mkdir(parents=True)
    source_path = source_root / "review-input.txt"
    source_path.write_text(
        f"synthetic-owned-review|{crystal_id}|{checkpoint.value}|{item_id}\n",
        encoding="ascii",
    )
    package_evidence = [
        PhaseIIIReviewEvidenceSource(
            role="owned_review_context",
            relative_path=source_path.name,
        )
    ]
    for index, declared in enumerate(package_sources, start=1):
        source = root / declared.relative_path
        copied = source_root / f"scientific_{index:02d}_{source.name}"
        shutil.copy2(source, copied)
        package_evidence.append(
            PhaseIIIReviewEvidenceSource(
                role=f"owned_scientific_{index:02d}",
                relative_path=copied.name,
            )
        )
    package_root = review_root / "package"
    package_root.mkdir()
    final_checkpoint = checkpoint in {
        PhaseIIIReviewCheckpoint.SEQUENCE,
        PhaseIIIReviewCheckpoint.COMPOSITION,
    }
    if final_checkpoint:
        parent_run = PARENT_RUN
        parent_profile = "unknown-single-component"
    elif checkpoint is PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC:
        parent_run = f"{PARENT_RUN}_crystallographic"
        parent_profile = "unknown-crystallographic-review"
    else:
        parent_run = f"{PARENT_RUN}_screen"
        parent_profile = "unknown-screen"
    package = build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=checkpoint,
            owned_parent_run_id=parent_run,
            parent_profile=parent_profile,
            parent_phase="phase3-pass1",
            execution_identity_id=EXECUTION_ID,
            crystal_id=crystal_id,
            target_item_ids=(item_id,),
            created_at=datetime(2026, 8, 25, tzinfo=UTC),
            input_root=source_root,
            evidence_sources=tuple(package_evidence),
            output_directory=package_root,
        )
    )
    manifest_sha = sha256_file(package.manifest)
    decision_file = PhaseIIIReviewDecisionFile.from_content(
        checkpoint=checkpoint,
        owned_parent_run_id=parent_run,
        review_package_id=package.review_package_id,
        review_package_manifest_sha256=manifest_sha,
        decisions=(
            PhaseIIIReviewDecision(
                crystal_id=crystal_id,
                item_id=item_id,
                decision=decision,
                reviewer="independent-reviewer",
                reviewed_at=datetime(2026, 8, 25, 1, tzinfo=UTC),
                reason="synthetic public-fixture review evidence inspected",
            ),
        ),
    )
    decision_path = review_root / "decision.json"
    decision_path.write_bytes(canonical_json_bytes(decision_file) + b"\n")
    for index, path in enumerate(sorted(package_root.rglob("*")), start=1):
        if not path.is_file():
            continue
        if path == package.manifest:
            role = f"{prefix}_package"
        elif path.name == "review_targets.tsv":
            role = f"{prefix}_targets"
        else:
            role = f"{prefix}_source_{index:04d}"
        evidence.append(
            UnknownPass1EvidenceSource(
                crystal_id=crystal_id,
                kind=UnknownPass1CollectedFileKind.EVIDENCE,
                role=role,
                relative_path=path.relative_to(root).as_posix(),
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
            )
        )
    evidence.append(
        UnknownPass1EvidenceSource(
            crystal_id=crystal_id,
            kind=UnknownPass1CollectedFileKind.EVIDENCE,
            role=f"{prefix}_decision",
            relative_path=decision_path.relative_to(root).as_posix(),
            sha256=sha256_file(decision_path),
            size_bytes=decision_path.stat().st_size,
        )
    )
    return UnknownPass1ReviewEvidence(
        checkpoint=checkpoint,
        package_crystal_id=crystal_id,
        package_item_id=item_id,
        review_package_id=package.review_package_id,
        review_package_manifest_sha256=manifest_sha,
        decision_crystal_id=crystal_id,
        decision_item_id=item_id,
        decision_file_id=decision_file.decision_file_id,
        decision_file_sha256=sha256_file(decision_path),
        decision=decision,
    )


def _reviews(
    *items: UnknownPass1ReviewEvidence,
) -> tuple[UnknownPass1ReviewEvidence, ...]:
    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.checkpoint.value,
                item.package_crystal_id,
                item.package_item_id,
                item.decision_crystal_id,
                item.decision_item_id,
                item.review_package_id,
                item.decision_file_id,
            ),
        )
    )


def _assessment(
    root: Path,
    *,
    crystal_id: str,
    mode: str,
) -> tuple[UnknownPass1CrystalAssessment, tuple[UnknownPass1EvidenceSource, ...]]:
    evidence = [
        _write_artifact(
            root,
            crystal_id=crystal_id,
            role="command",
            kind=UnknownPass1CollectedFileKind.COMMAND,
        ),
    ]
    crystallographic_item = f"{crystal_id}_mtz_review"
    solution = None
    shortlist = False
    status = ExecutionStatus.COMPLETED_NO_HIT
    reviews: tuple[UnknownPass1ReviewEvidence, ...] = ()

    if mode != "failure" and mode != "insufficient":
        decision = (
            PhaseIIIReviewDecisionValue.HOLD
            if mode == "hold"
            else PhaseIIIReviewDecisionValue.PROCEED
        )
        crystallographic = _review(
            root,
            evidence,
            crystal_id=crystal_id,
            checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            item_id=crystallographic_item,
            decision=decision,
        )
        reviews = _reviews(crystallographic)

    if mode == "credible":
        state_id = f"{crystal_id}_state_A"
        sequence_group_id = f"seq_{_digest(f'{crystal_id}:sequence-group')}"
        hypothesis_id = f"{crystal_id}_hypothesis_A"
        refinement_id = f"{crystal_id}_refinement_A"
        combined = _coordinate(
            root,
            crystal_id=crystal_id,
            role="combined_coordinate",
        )
        refined = _coordinate(
            root,
            crystal_id=crystal_id,
            role="refined_coordinate",
        )
        refined_mtz = _refined_mtz(root, crystal_id=crystal_id)
        review_map = _review_map(root, crystal_id=crystal_id)
        copies = _result_record(
            root,
            crystal_id=crystal_id,
            role="copy_support",
            record=CopyCountAssessment(
                schema_version="1.0",
                assessment_id=f"{crystal_id}_copy_assessment",
                review_id=f"{crystal_id}_review_A",
                seed_solution_id=state_id,
                hypothesis_id=hypothesis_id,
                sequence_group_id=sequence_group_id,
                expected_copy_count=2,
                best_supported_copy_count=2,
                attempted_transition_count=1,
                reached_expected_copy_count=True,
                final_execution_status=ExecutionStatus.COMPLETED_HIT,
                final_top_solution_packed=True,
                final_placement_count=2,
                terminal_reason="expected_copy_count_reached",
            ),
        )
        packing = _result_record(
            root,
            crystal_id=crystal_id,
            role="packing",
            record=NormalisedMrResult(
                schema_version="1.0",
                hypothesis_id=hypothesis_id,
                tool_version="synthetic-public-fixture",
                execution_status=ExecutionStatus.COMPLETED_HIT,
                llg=100,
                tfz=10,
                placed_copy_count=2,
                packing_summary={
                    "solution_count": 1,
                    "accepted_solution_count": 1,
                    "packed_solution_count": 1,
                    "top_solution_packed": True,
                    "top_solution_pak": 0,
                },
                solution_coordinate_path="combined_coordinate.pdb",
                solution_coordinate_sha256=combined.sha256,
                raw_log_pointer="synthetic-phaser.log",
            ),
        )
        refinement = _result_record(
            root,
            crystal_id=crystal_id,
            role="refinement",
            record=BriefRefinementResult(
                schema_version="1.0",
                refinement_id=refinement_id,
                seed_solution_id=state_id,
                sequence_group_id=sequence_group_id,
                input_copy_count=2,
                tool_version="synthetic-public-fixture",
                execution_status=ExecutionStatus.COMPLETED_SUCCESS,
                final_r_work=0.22,
                final_r_free=0.27,
                refined_model_path="refined_coordinate.pdb",
                refined_model_sha256=refined.sha256,
                refined_mtz_path="refined_mtz.mtz",
                refined_mtz_sha256=refined_mtz.sha256,
                map_path="review_map.ccp4",
                map_sha256=review_map.sha256,
                command_pointer="synthetic-refinement-command.json",
                raw_log_pointer="synthetic-refinement.log",
            ),
        )
        sequence = _result_record(
            root,
            crystal_id=crystal_id,
            role="sequence_map",
            record=SequenceMapResult(
                schema_version="1.0",
                sequence_assessment_id=f"{crystal_id}_sequence_assessment",
                refinement_id=refinement_id,
                seed_solution_id=state_id,
                execution_status=ExecutionStatus.COMPLETED_HIT,
                tool_version="synthetic-public-fixture",
                complete_catalogue_group_count=1,
                scored_group_count=1,
                candidates=(
                    SequenceMapCandidate(
                        schema_version="1.0",
                        refinement_id=refinement_id,
                        rank=1,
                        sequence_group_id=sequence_group_id,
                        sequence_length=4,
                        raw_score=10,
                        source_record_ids=(f"{crystal_id}_protein",),
                    ),
                ),
                command_pointer="synthetic-sequence-command.json",
                raw_log_pointer="synthetic-sequence.log",
            ),
        )
        metrics = _result_record(
            root,
            crystal_id=crystal_id,
            role="final_metrics",
            record=UnknownPass1FinalMetricsEvidence(
                schema_version="2.0",
                owned_parent_run_id=PARENT_RUN,
                execution_identity_id=EXECUTION_ID,
                crystal_id=crystal_id,
                state_id=state_id,
                sequence_group_id=sequence_group_id,
                refinement_id=refinement_id,
                final_r_work=0.22,
                final_r_free=0.27,
                residual_content_state=UnknownPass1ResidualContentState.NONE_DETECTED,
            ),
        )
        evidence.extend(
            (
                combined,
                refined,
                refined_mtz,
                review_map,
                copies,
                packing,
                refinement,
                sequence,
                metrics,
            )
        )
        solution = UnknownPass1SolutionEvidence(
            crystal_id=crystal_id,
            state_id=state_id,
            search_sequence_group_id=sequence_group_id,
            sequence_group_id=sequence_group_id,
            requested_copy_count=2,
            observed_copy_count=2,
            copy_counts_supported=True,
            copy_support_evidence_sha256=copies.sha256,
            packing_passed=True,
            packing_evidence_sha256=packing.sha256,
            refinement_completed=True,
            combined_coordinate_sha256=combined.sha256,
            refined_coordinate_sha256=refined.sha256,
            refined_mtz_sha256=refined_mtz.sha256,
            review_map_sha256=review_map.sha256,
            refinement_evidence_sha256=refinement.sha256,
            sequence_evidence_sha256=sequence.sha256,
            final_r_work=0.22,
            final_r_free=0.27,
            parsed_final_metrics_evidence_sha256=metrics.sha256,
            residual_content_state=UnknownPass1ResidualContentState.NONE_DETECTED,
        )
        seed_review = _review(
            root,
            evidence,
            crystal_id=crystal_id,
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            item_id=state_id,
            decision=PhaseIIIReviewDecisionValue.APPROVE,
            package_sources=(packing, combined),
        )
        composition_review = _review(
            root,
            evidence,
            crystal_id=crystal_id,
            checkpoint=PhaseIIIReviewCheckpoint.COMPOSITION,
            item_id=state_id,
            decision=PhaseIIIReviewDecisionValue.APPROVE,
            package_sources=(
                copies,
                combined,
                refined,
                refined_mtz,
                review_map,
                refinement,
                sequence,
            ),
        )
        sequence_review = _review(
            root,
            evidence,
            crystal_id=crystal_id,
            checkpoint=PhaseIIIReviewCheckpoint.SEQUENCE,
            item_id=sequence_group_id,
            decision=PhaseIIIReviewDecisionValue.APPROVE,
            package_sources=(
                copies,
                combined,
                refined,
                refined_mtz,
                review_map,
                refinement,
                sequence,
            ),
        )
        reviews = _reviews(reviews[0], seed_review, composition_review, sequence_review)
        shortlist = True
        status = ExecutionStatus.COMPLETED_HIT
    elif mode == "failure":
        status = ExecutionStatus.FAILED_PARSE
    elif mode == "shortlist":
        shortlist = True
        status = ExecutionStatus.COMPLETED_SUCCESS
    elif mode in {"hold", "insufficient"}:
        status = ExecutionStatus.SKIPPED_POLICY

    terminal = _result_record(
        root,
        crystal_id=crystal_id,
        role="terminal_result",
        record=UnknownPass1TerminalEvidence(
            schema_version="2.0",
            owned_parent_run_id=PARENT_RUN,
            execution_identity_id=EXECUTION_ID,
            crystal_id=crystal_id,
            execution_status=status,
            candidate_shortlist_present=shortlist,
            state_id=solution.state_id if solution is not None else None,
            sequence_group_id=(
                solution.sequence_group_id if solution is not None else None
            ),
        ),
    )
    evidence.append(terminal)

    item = UnknownPass1CrystalAssessment.from_evidence(
        adapter_version="unknown-pass1-terminal-assessment-v2",
        owned_parent_run_id=PARENT_RUN,
        execution_identity_id=EXECUTION_ID,
        crystal_id=crystal_id,
        crystallographic_review_item_id=crystallographic_item,
        execution_status=status,
        terminal_evidence_sha256=terminal.sha256,
        candidate_shortlist_present=shortlist,
        solution_evidence=solution,
        review_evidence=reviews,
    )
    return item, tuple(evidence)


def _request(
    tmp_path: Path,
    modes: tuple[str, str, str],
    *,
    output_name: str = "output",
) -> UnknownPass1CollectionRequest:
    root = tmp_path / "input"
    root.mkdir(parents=True)
    assessment_sources = []
    evidence_sources = []
    for crystal_id, mode in zip(PHASE3_UNKNOWN_CRYSTAL_IDS, modes, strict=True):
        item, evidence = _assessment(root, crystal_id=crystal_id, mode=mode)
        relative_path = f"assessments/{crystal_id}.json"
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(item) + b"\n")
        assessment_sources.append(
            UnknownPass1AssessmentSource(
                crystal_id=crystal_id,
                relative_path=relative_path,
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
            )
        )
        evidence_sources.extend(evidence)
    output = tmp_path / output_name
    output.mkdir()
    return UnknownPass1CollectionRequest(
        input_root=root,
        assessment_sources=tuple(assessment_sources),
        evidence_allow_list=tuple(evidence_sources),
        output_directory=output,
    )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _replace_scientific_evidence(
    request: UnknownPass1CollectionRequest,
    *,
    crystal_id: str,
    role: str,
    payload: bytes,
) -> UnknownPass1CollectionRequest:
    source = next(
        item
        for item in request.evidence_allow_list
        if item.crystal_id == crystal_id and item.role == role
    )
    source_path = request.input_root / source.relative_path
    source_path.write_bytes(payload)
    replacement_source = _updated_source(request.input_root, source)
    assessment_source = next(
        item for item in request.assessment_sources if item.crystal_id == crystal_id
    )
    assessment_path = request.input_root / assessment_source.relative_path
    assessment = UnknownPass1CrystalAssessment.model_validate_json(
        assessment_path.read_bytes()
    )
    solution = assessment.solution_evidence
    terminal_digest = assessment.terminal_evidence_sha256
    fields = {
        "copy_support": "copy_support_evidence_sha256",
        "packing": "packing_evidence_sha256",
        "combined_coordinate": "combined_coordinate_sha256",
        "refined_coordinate": "refined_coordinate_sha256",
        "refined_mtz": "refined_mtz_sha256",
        "review_map": "review_map_sha256",
        "refinement": "refinement_evidence_sha256",
        "sequence_map": "sequence_evidence_sha256",
        "final_metrics": "parsed_final_metrics_evidence_sha256",
    }
    if role == "terminal_result":
        terminal_digest = replacement_source.sha256
    elif solution is not None:
        solution = solution.model_copy(update={fields[role]: replacement_source.sha256})

    replacement_assessment = UnknownPass1CrystalAssessment.from_evidence(
        adapter_version=assessment.adapter_version,
        owned_parent_run_id=assessment.owned_parent_run_id,
        execution_identity_id=assessment.execution_identity_id,
        crystal_id=assessment.crystal_id,
        crystallographic_review_item_id=assessment.crystallographic_review_item_id,
        execution_status=assessment.execution_status,
        terminal_evidence_sha256=terminal_digest,
        candidate_shortlist_present=assessment.candidate_shortlist_present,
        solution_evidence=solution,
        review_evidence=assessment.review_evidence,
    )
    assessment_path.write_bytes(canonical_json_bytes(replacement_assessment) + b"\n")
    replacement_assessment_source = replace(
        assessment_source,
        sha256=sha256_file(assessment_path),
        size_bytes=assessment_path.stat().st_size,
    )
    return replace(
        request,
        assessment_sources=tuple(
            replacement_assessment_source if item is assessment_source else item
            for item in request.assessment_sources
        ),
        evidence_allow_list=tuple(
            replacement_source if item is source else item
            for item in request.evidence_allow_list
        ),
    )


def test_collects_mixed_panel_without_sibling_promotion(tmp_path: Path) -> None:
    request = _request(tmp_path, ("credible", "no_hit", "failure"))
    cross = collect_unknown_pass1_panel(request)
    panel = UnknownPass1PanelSummary.model_validate_json(
        (request.output_directory / "unknown-pass1-panel-summary.json").read_bytes()
    )
    statuses = {item.crystal_id: item.scientific_status for item in panel.assessments}

    assert statuses == {
        "AD4QS1P4G2_18": (
            UnknownPass1ScientificStatus.CREDIBLE_SINGLE_COMPONENT_SOLUTION
        ),
        "CD4QS2P2G1_15": UnknownPass1ScientificStatus.NO_SUPPORTED_CATALOGUE_CANDIDATE,
        "CD6QS2P2G1_5": UnknownPass1ScientificStatus.EXECUTION_FAILURE,
    }
    assert cross.panel_id == panel.panel_id
    assert len(cross.crystal_manifest_ids) == 3
    html_report = (request.output_directory / "unknown-pass1-report.html").read_text()
    assert "Exploratory application; not validation." in html_report
    assert "makes no additional identity or composition claim" in html_report
    assert "<script" not in html_report
    for crystal_id in PHASE3_UNKNOWN_CRYSTAL_IDS:
        manifest = UnknownPass1CrystalChecksumManifest.model_validate_json(
            (
                request.output_directory
                / "crystals"
                / crystal_id
                / "checksum-manifest.json"
            ).read_bytes()
        )
        assert manifest.crystal_id == crystal_id
        for entry in manifest.files:
            assert (
                sha256_file(request.output_directory / entry.relative_path)
                == entry.sha256
            )


def test_credible_collection_rejects_checksum_matched_fake_review_package(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path, ("credible", "no_hit", "failure"))
    crystal_id = PHASE3_UNKNOWN_CRYSTAL_IDS[0]
    assessment_source = next(
        item for item in request.assessment_sources if item.crystal_id == crystal_id
    )
    assessment_path = request.input_root / assessment_source.relative_path
    assessment = UnknownPass1CrystalAssessment.model_validate_json(
        assessment_path.read_bytes()
    )
    review = next(
        item
        for item in assessment.review_evidence
        if item.checkpoint is PhaseIIIReviewCheckpoint.SEQUENCE
    )
    package_source = next(
        item
        for item in request.evidence_allow_list
        if item.sha256 == review.review_package_manifest_sha256
    )
    package_path = request.input_root / package_source.relative_path
    package_path.write_text(
        "fabricated but checksum-matched review\n", encoding="ascii"
    )
    package_digest = sha256_file(package_path)
    replacement_review = review.model_copy(
        update={"review_package_manifest_sha256": package_digest}
    )
    replacements = _reviews(
        *(
            replacement_review if item is review else item
            for item in assessment.review_evidence
        )
    )
    updated_assessment = UnknownPass1CrystalAssessment.from_evidence(
        adapter_version=assessment.adapter_version,
        owned_parent_run_id=assessment.owned_parent_run_id,
        execution_identity_id=assessment.execution_identity_id,
        crystal_id=assessment.crystal_id,
        crystallographic_review_item_id=assessment.crystallographic_review_item_id,
        execution_status=assessment.execution_status,
        terminal_evidence_sha256=assessment.terminal_evidence_sha256,
        candidate_shortlist_present=assessment.candidate_shortlist_present,
        solution_evidence=assessment.solution_evidence,
        review_evidence=replacements,
    )
    assessment_path.write_bytes(canonical_json_bytes(updated_assessment) + b"\n")
    altered = replace(
        request,
        assessment_sources=tuple(
            replace(
                item,
                sha256=sha256_file(assessment_path),
                size_bytes=assessment_path.stat().st_size,
            )
            if item is assessment_source
            else item
            for item in request.assessment_sources
        ),
        evidence_allow_list=tuple(
            replace(
                item,
                sha256=package_digest,
                size_bytes=package_path.stat().st_size,
            )
            if item is package_source
            else item
            for item in request.evidence_allow_list
        ),
    )

    with pytest.raises(UnknownPass1CollectionError, match="review package"):
        collect_unknown_pass1_panel(altered)


def test_credible_collection_rejects_untyped_scientific_artifacts(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path, ("credible", "no_hit", "failure"))
    altered = _replace_scientific_evidence(
        request,
        crystal_id=PHASE3_UNKNOWN_CRYSTAL_IDS[0],
        role="copy_support",
        payload=b"checksum-matched but fabricated scientific evidence\n",
    )

    with pytest.raises(UnknownPass1CollectionError, match="scientific"):
        collect_unknown_pass1_panel(altered)


@pytest.mark.parametrize(
    ("role", "mutation"),
    (
        ("terminal_result", "parent"),
        ("terminal_result", "crystal"),
        ("terminal_result", "status"),
        ("copy_support", "state"),
        ("copy_support", "sequence"),
        ("packing", "hypothesis"),
        ("packing", "unpacked"),
        ("refinement", "state"),
        ("refinement", "rfree"),
        ("sequence_map", "sequence"),
        ("final_metrics", "rfree"),
        ("final_metrics", "residual"),
    ),
    ids=(
        "cross-run-terminal",
        "cross-crystal-terminal",
        "contradictory-terminal-status",
        "cross-state-copy-assessment",
        "cross-sequence-copy-assessment",
        "cross-hypothesis-packing",
        "unsupported-packing",
        "cross-state-refinement",
        "unobserved-rfree",
        "unapproved-map-sequence",
        "contradictory-final-rfree",
        "contradictory-residual",
    ),
)
def test_credible_collection_rejects_inconsistent_scientific_records(
    tmp_path: Path,
    role: str,
    mutation: str,
) -> None:
    request = _request(tmp_path, ("credible", "no_hit", "failure"))
    crystal_id = PHASE3_UNKNOWN_CRYSTAL_IDS[0]
    source = next(
        item
        for item in request.evidence_allow_list
        if item.crystal_id == crystal_id and item.role == role
    )
    schemas: dict[str, type[ContractModel]] = {
        "terminal_result": UnknownPass1TerminalEvidence,
        "copy_support": CopyCountAssessment,
        "packing": NormalisedMrResult,
        "refinement": BriefRefinementResult,
        "sequence_map": SequenceMapResult,
        "final_metrics": UnknownPass1FinalMetricsEvidence,
    }
    record = schemas[role].model_validate_json(
        (request.input_root / source.relative_path).read_bytes()
    )
    updates: dict[str, object]
    if mutation == "parent":
        updates = {"owned_parent_run_id": "another_owned_parent"}
    elif mutation == "crystal":
        updates = {"crystal_id": PHASE3_UNKNOWN_CRYSTAL_IDS[1]}
    elif mutation == "status":
        updates = {"execution_status": ExecutionStatus.COMPLETED_NO_HIT}
    elif mutation == "state":
        updates = {"seed_solution_id": "another_state"}
    elif mutation == "hypothesis":
        updates = {"hypothesis_id": "another_hypothesis"}
    elif mutation == "unpacked":
        assert isinstance(record, NormalisedMrResult)
        updates = {
            "packing_summary": {
                **record.packing_summary,
                "packed_solution_count": 0,
                "top_solution_packed": False,
            }
        }
    elif mutation == "rfree":
        updates = {"final_r_free": 0.31}
    elif mutation == "residual":
        updates = {
            "residual_content_state": (
                UnknownPass1ResidualContentState.PRESENT_OR_SUSPECTED
            )
        }
    elif role == "sequence_map":
        assert isinstance(record, SequenceMapResult)
        updates = {
            "candidates": (
                record.candidates[0].model_copy(
                    update={"sequence_group_id": f"seq_{_digest('another-group')}"}
                ),
            )
        }
    else:
        updates = {"sequence_group_id": f"seq_{_digest('another-group')}"}

    replacement = record.model_copy(update=updates)
    altered = _replace_scientific_evidence(
        request,
        crystal_id=crystal_id,
        role=role,
        payload=canonical_json_bytes(replacement) + b"\n",
    )

    with pytest.raises(UnknownPass1CollectionError, match="scientific"):
        collect_unknown_pass1_panel(altered)


@pytest.mark.parametrize(
    "role",
    ("combined_coordinate", "refined_coordinate", "refined_mtz", "review_map"),
)
def test_credible_collection_rejects_invalid_checksum_matched_scientific_assets(
    tmp_path: Path,
    role: str,
) -> None:
    request = _request(tmp_path, ("credible", "no_hit", "failure"))
    crystal_id = PHASE3_UNKNOWN_CRYSTAL_IDS[0]
    altered = _replace_scientific_evidence(
        request,
        crystal_id=crystal_id,
        role=role,
        payload=b"checksum-matched but scientifically invalid bytes\n",
    )
    replacement_asset = next(
        item
        for item in altered.evidence_allow_list
        if item.crystal_id == crystal_id and item.role == role
    )
    parent_role = "packing" if role == "combined_coordinate" else "refinement"
    parent_source = next(
        item
        for item in altered.evidence_allow_list
        if item.crystal_id == crystal_id and item.role == parent_role
    )
    schema = NormalisedMrResult if parent_role == "packing" else BriefRefinementResult
    parent = schema.model_validate_json(
        (altered.input_root / parent_source.relative_path).read_bytes()
    )
    fields = {
        "combined_coordinate": "solution_coordinate_sha256",
        "refined_coordinate": "refined_model_sha256",
        "refined_mtz": "refined_mtz_sha256",
        "review_map": "map_sha256",
    }
    replacement_parent = parent.model_copy(
        update={fields[role]: replacement_asset.sha256}
    )
    altered = _replace_scientific_evidence(
        altered,
        crystal_id=crystal_id,
        role=parent_role,
        payload=canonical_json_bytes(replacement_parent) + b"\n",
    )

    with pytest.raises(UnknownPass1CollectionError, match="scientific"):
        collect_unknown_pass1_panel(altered)


def test_uncertain_endpoints_remain_distinct(tmp_path: Path) -> None:
    request = _request(tmp_path, ("shortlist", "hold", "insufficient"))
    collect_unknown_pass1_panel(request)
    panel = UnknownPass1PanelSummary.model_validate_json(
        (request.output_directory / "unknown-pass1-panel-summary.json").read_bytes()
    )

    assert tuple(item.scientific_status for item in panel.assessments) == (
        UnknownPass1ScientificStatus.CANDIDATE_SHORTLIST_NO_CREDIBLE_MR_SOLUTION,
        UnknownPass1ScientificStatus.MTZ_OR_SYMMETRY_REVIEW_REQUIRED,
        UnknownPass1ScientificStatus.INSUFFICIENT_EVIDENCE,
    )


def test_input_permutation_produces_byte_identical_panel(tmp_path: Path) -> None:
    first = _request(tmp_path, ("credible", "no_hit", "failure"), output_name="one")
    first_cross = collect_unknown_pass1_panel(first)
    second_output = tmp_path / "two"
    second_output.mkdir()
    second = replace(
        first,
        assessment_sources=tuple(reversed(first.assessment_sources)),
        evidence_allow_list=tuple(reversed(first.evidence_allow_list)),
        output_directory=second_output,
    )
    second_cross = collect_unknown_pass1_panel(second)

    assert first_cross.cross_manifest_id == second_cross.cross_manifest_id
    assert _tree_bytes(first.output_directory) == _tree_bytes(second.output_directory)


def test_checksum_mutation_and_missing_evidence_are_rejected(tmp_path: Path) -> None:
    request = _request(tmp_path, ("no_hit", "no_hit", "failure"))
    mutated = request.evidence_allow_list[0]
    (request.input_root / mutated.relative_path).write_text("mutated\n")
    with pytest.raises(UnknownPass1CollectionError, match="checksum declaration"):
        collect_unknown_pass1_panel(request)

    clean = _request(
        tmp_path / "missing",
        ("no_hit", "no_hit", "failure"),
    )
    terminal = next(
        item
        for item in clean.evidence_allow_list
        if item.crystal_id == PHASE3_UNKNOWN_CRYSTAL_IDS[0]
        and item.role == "terminal_result"
    )
    missing = replace(
        clean,
        evidence_allow_list=tuple(
            item for item in clean.evidence_allow_list if item is not terminal
        ),
    )
    with pytest.raises(UnknownPass1CollectionError, match="evidence is missing"):
        collect_unknown_pass1_panel(missing)


def test_cross_crystal_duplicate_unsafe_symlink_and_nonempty_output_fail(
    tmp_path: Path,
) -> None:
    duplicate = _request(
        tmp_path / "duplicate",
        ("no_hit", "no_hit", "failure"),
    )
    shared = duplicate.evidence_allow_list[0]
    cross_crystal = replace(shared, crystal_id=PHASE3_UNKNOWN_CRYSTAL_IDS[1])
    with pytest.raises(UnknownPass1CollectionError, match="path is duplicated"):
        collect_unknown_pass1_panel(
            replace(
                duplicate,
                evidence_allow_list=(*duplicate.evidence_allow_list, cross_crystal),
            )
        )

    unsafe = _request(tmp_path / "unsafe", ("no_hit", "no_hit", "failure"))
    unsafe_source = replace(
        unsafe.assessment_sources[0], relative_path="../escape.json"
    )
    with pytest.raises(UnknownPass1CollectionError, match="path is unsafe"):
        collect_unknown_pass1_panel(
            replace(
                unsafe,
                assessment_sources=(unsafe_source, *unsafe.assessment_sources[1:]),
            )
        )

    symlinked = _request(tmp_path / "symlink", ("no_hit", "no_hit", "failure"))
    source = symlinked.evidence_allow_list[0]
    path = symlinked.input_root / source.relative_path
    target = path.with_name("real.txt")
    path.rename(target)
    path.symlink_to(target.name)
    with pytest.raises(UnknownPass1CollectionError, match="contains a symlink"):
        collect_unknown_pass1_panel(symlinked)

    nonempty = _request(tmp_path / "nonempty", ("no_hit", "no_hit", "failure"))
    (nonempty.output_directory / "existing.txt").write_text("owned\n")
    with pytest.raises(UnknownPass1CollectionError, match="empty directory"):
        collect_unknown_pass1_panel(nonempty)
