"""Focused tests for the checksum-closed unknown-pass terminal collector."""

import hashlib
from dataclasses import replace
from pathlib import Path

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
from genome_to_diffraction.schemas.v2 import (
    UnknownPass1CollectedFileKind,
    UnknownPass1CrystalAssessment,
    UnknownPass1CrystalChecksumManifest,
    UnknownPass1PanelSummary,
    UnknownPass1ResidualContentState,
    UnknownPass1ReviewEvidence,
    UnknownPass1ScientificStatus,
    UnknownPass1SolutionEvidence,
)
from genome_to_diffraction.schemas.v2.review import (
    PhaseIIIReviewCheckpoint,
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
) -> UnknownPass1EvidenceSource:
    relative_path = f"evidence/{crystal_id}/{role}.txt"
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{crystal_id}|{role}\n", encoding="ascii")
    return UnknownPass1EvidenceSource(
        crystal_id=crystal_id,
        kind=kind,
        role=role,
        relative_path=relative_path,
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def _review(
    root: Path,
    evidence: list[UnknownPass1EvidenceSource],
    *,
    crystal_id: str,
    checkpoint: PhaseIIIReviewCheckpoint,
    item_id: str,
    decision: PhaseIIIReviewDecisionValue,
) -> UnknownPass1ReviewEvidence:
    prefix = f"{checkpoint.value}_{item_id}"
    package = _write_artifact(
        root,
        crystal_id=crystal_id,
        role=f"{prefix}_package",
        kind=UnknownPass1CollectedFileKind.EVIDENCE,
    )
    decision_file = _write_artifact(
        root,
        crystal_id=crystal_id,
        role=f"{prefix}_decision",
        kind=UnknownPass1CollectedFileKind.EVIDENCE,
    )
    evidence.extend((package, decision_file))
    return UnknownPass1ReviewEvidence(
        checkpoint=checkpoint,
        package_crystal_id=crystal_id,
        package_item_id=item_id,
        review_package_id=f"phase3reviewpkg_{_digest(f'{prefix}:package-id')}",
        review_package_manifest_sha256=package.sha256,
        decision_crystal_id=crystal_id,
        decision_item_id=item_id,
        decision_file_id=f"phase3review_{_digest(f'{prefix}:decision-id')}",
        decision_file_sha256=decision_file.sha256,
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
        _write_artifact(
            root,
            crystal_id=crystal_id,
            role="terminal_result",
            kind=UnknownPass1CollectedFileKind.RESULT,
        ),
    ]
    terminal_sha = evidence[-1].sha256
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
        solution_roles = (
            "copy_support",
            "packing",
            "combined_coordinate",
            "refined_mtz",
            "refinement",
            "final_metrics",
        )
        solution_files = {
            role: _write_artifact(
                root,
                crystal_id=crystal_id,
                role=role,
                kind=UnknownPass1CollectedFileKind.RESULT,
            )
            for role in solution_roles
        }
        evidence.extend(solution_files.values())
        solution = UnknownPass1SolutionEvidence(
            crystal_id=crystal_id,
            state_id=state_id,
            requested_copy_count=2,
            observed_copy_count=2,
            copy_counts_supported=True,
            copy_support_evidence_sha256=solution_files["copy_support"].sha256,
            packing_passed=True,
            packing_evidence_sha256=solution_files["packing"].sha256,
            refinement_completed=True,
            combined_coordinate_sha256=solution_files["combined_coordinate"].sha256,
            refined_mtz_sha256=solution_files["refined_mtz"].sha256,
            refinement_evidence_sha256=solution_files["refinement"].sha256,
            final_r_work=0.22,
            final_r_free=0.27,
            parsed_final_metrics_evidence_sha256=solution_files["final_metrics"].sha256,
            residual_content_state=UnknownPass1ResidualContentState.NONE_DETECTED,
        )
        seed_review = _review(
            root,
            evidence,
            crystal_id=crystal_id,
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            item_id=state_id,
            decision=PhaseIIIReviewDecisionValue.APPROVE,
        )
        composition_review = _review(
            root,
            evidence,
            crystal_id=crystal_id,
            checkpoint=PhaseIIIReviewCheckpoint.COMPOSITION,
            item_id=state_id,
            decision=PhaseIIIReviewDecisionValue.APPROVE,
        )
        reviews = _reviews(reviews[0], seed_review, composition_review)
        shortlist = True
        status = ExecutionStatus.COMPLETED_HIT
    elif mode == "failure":
        status = ExecutionStatus.FAILED_PARSE
    elif mode == "shortlist":
        shortlist = True
        status = ExecutionStatus.COMPLETED_SUCCESS
    elif mode in {"hold", "insufficient"}:
        status = ExecutionStatus.SKIPPED_POLICY

    item = UnknownPass1CrystalAssessment.from_evidence(
        owned_parent_run_id=PARENT_RUN,
        execution_identity_id=EXECUTION_ID,
        crystal_id=crystal_id,
        crystallographic_review_item_id=crystallographic_item,
        execution_status=status,
        terminal_evidence_sha256=terminal_sha,
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
    with pytest.raises(UnknownPass1CollectionError, match="cross-crystal evidence"):
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
