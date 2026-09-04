"""Checksum and provenance gates for local Phase III review staging."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import genome_to_diffraction.review.phase3_stage as phase3_stage
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.review import (
    OwnedPhaseIIIParentRun,
    PhaseIIIReviewStageError,
    PhaseIIIReviewStageManifest,
    PhaseIIIReviewStageRequest,
    stage_phase3_review_decisions,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecision,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
    PhaseIIIReviewEvidenceArtifact,
    PhaseIIIReviewPackageManifest,
    PhaseIIIReviewPackageTarget,
    PhaseIIIReviewTableArtifact,
)
from genome_to_diffraction.schemas.v2.review import (
    phase3_review_package_content_sha256,
)

PARENT = OwnedPhaseIIIParentRun(
    run_id="gtd-unknown-screen-owned-run",
    profile="unknown-screen",
    phase="phase3-pass1",
)
EXECUTION_ID = f"phase3exec_{'a' * 64}"
PACKAGE_CREATED = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
REVIEWED = PACKAGE_CREATED + timedelta(minutes=5)


def _write_package(
    path: Path,
    targets: tuple[tuple[str, str], ...],
    *,
    parent: OwnedPhaseIIIParentRun = PARENT,
    checkpoint: PhaseIIIReviewCheckpoint = PhaseIIIReviewCheckpoint.A_SEED,
) -> tuple[Path, str, str]:
    sorted_targets = tuple(sorted(targets))
    evidence = (
        PhaseIIIReviewEvidenceArtifact(
            role="review_evidence",
            relative_path="evidence/review.json",
            sha256="b" * 64,
            size_bytes=10,
        ),
    )
    table = (
        PhaseIIIReviewTableArtifact(
            role="review_targets",
            relative_path="review_targets.tsv",
            sha256="c" * 64,
            size_bytes=100,
            row_count=len(sorted_targets),
            target_item_ids=tuple(item_id for _, item_id in sorted_targets),
        ),
    )
    package = PhaseIIIReviewPackageManifest.from_content(
        adapter_version=(
            "phase3-review-package-v1"
            if checkpoint
            in {
                PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
                PhaseIIIReviewCheckpoint.A_SEED,
            }
            else "phase3-review-package-v2"
        ),
        checkpoint=checkpoint,
        owned_parent_run_id=parent.run_id,
        parent_profile=parent.profile,
        parent_phase=parent.phase,
        execution_identity_id=EXECUTION_ID,
        crystal_id=sorted_targets[0][0],
        created_at=PACKAGE_CREATED,
        permitted_targets=tuple(
            PhaseIIIReviewPackageTarget(crystal_id=crystal_id, item_id=item_id)
            for crystal_id, item_id in sorted_targets
        ),
        evidence_inventory=evidence,
        review_tables=table,
        package_content_sha256=phase3_review_package_content_sha256(
            evidence_inventory=evidence,
            review_tables=table,
        ),
    )
    atomic_write_json(path, package.model_dump(mode="json", exclude_none=False))
    return path, sha256_file(path, progress=False), package.review_package_id


def _decision(
    item_id: str,
    value: PhaseIIIReviewDecisionValue,
    *,
    crystal_id: str = "unknown_1",
    reviewed_at: datetime = REVIEWED,
) -> PhaseIIIReviewDecision:
    return PhaseIIIReviewDecision(
        crystal_id=crystal_id,
        item_id=item_id,
        decision=value,
        reviewer="reviewer_1",
        reviewed_at=reviewed_at,
        reason="reviewed against the exact checksum-bound package",
        comment="Coot and crystallographic evidence considered",
    )


def _write_decisions(
    path: Path,
    package_sha256: str,
    decisions: tuple[PhaseIIIReviewDecision, ...],
    *,
    parent_run_id: str = PARENT.run_id,
    checkpoint: PhaseIIIReviewCheckpoint = PhaseIIIReviewCheckpoint.A_SEED,
    package_id: str,
) -> PhaseIIIReviewDecisionFile:
    decision_file = PhaseIIIReviewDecisionFile.from_content(
        checkpoint=checkpoint,
        owned_parent_run_id=parent_run_id,
        review_package_id=package_id,
        review_package_manifest_sha256=package_sha256,
        decisions=decisions,
    )
    atomic_write_json(
        path,
        decision_file.model_dump(mode="json", exclude_none=False),
    )
    return decision_file


def _request(
    *,
    package: Path,
    decisions: Path,
    output: Path,
    parent: OwnedPhaseIIIParentRun = PARENT,
    confirmed_sha256: str | None = None,
    checkpoint: PhaseIIIReviewCheckpoint = PhaseIIIReviewCheckpoint.A_SEED,
) -> PhaseIIIReviewStageRequest:
    return PhaseIIIReviewStageRequest(
        parent=parent,
        checkpoint=checkpoint,
        review_package_manifest=package,
        decisions=decisions,
        confirmed_decisions_sha256=(
            confirmed_sha256
            if confirmed_sha256 is not None
            else sha256_file(decisions, progress=False)
        ),
        output_directory=output,
    )


def test_happy_path_publishes_only_canonical_decision_and_stage_manifest(
    tmp_path: Path,
) -> None:
    package, package_sha256, package_id = _write_package(
        tmp_path / "review-package.json",
        (("unknown_1", "state_1"), ("unknown_1", "state_2")),
    )
    decisions_path = tmp_path / "decisions.json"
    expected = _write_decisions(
        decisions_path,
        package_sha256,
        (
            _decision("state_1", PhaseIIIReviewDecisionValue.APPROVE),
            _decision("state_2", PhaseIIIReviewDecisionValue.REJECT),
        ),
        package_id=package_id,
    )
    output_directory = tmp_path / "staged"

    output = stage_phase3_review_decisions(
        _request(
            package=package,
            decisions=decisions_path,
            output=output_directory,
        )
    )

    assert {path.name for path in output_directory.iterdir()} == {
        "phase3_review_decision.json",
        "phase3_review_stage_manifest.json",
    }
    assert (
        load_contract(
            output.canonical_decision,
            "phase3-review-decisions",
            progress=False,
        )
        == expected
    )
    manifest = PhaseIIIReviewStageManifest.model_validate_json(
        output.stage_manifest.read_bytes()
    )
    assert manifest.stage_id == output.stage_id
    assert manifest.decision_file_id == expected.decision_file_id
    assert manifest.decision_count == 2
    assert manifest.review_package_manifest_sha256 == package_sha256
    assert manifest.source_decisions_sha256 == sha256_file(
        decisions_path, progress=False
    )
    assert manifest.canonical_decision_sha256 == sha256_file(
        output.canonical_decision, progress=False
    )
    assert manifest.output_allowlist == (
        "phase3_review_decision.json",
        "phase3_review_stage_manifest.json",
    )


@pytest.mark.parametrize(
    ("checkpoint", "decision"),
    (
        (
            PhaseIIIReviewCheckpoint.COMPOSITION,
            PhaseIIIReviewDecisionValue.RETAIN_PARTIAL,
        ),
        (
            PhaseIIIReviewCheckpoint.SEQUENCE,
            PhaseIIIReviewDecisionValue.RETAIN_ALTERNATIVE,
        ),
    ),
)
def test_stages_composition_and_sequence_reviews_without_promoting_claims(
    tmp_path: Path,
    checkpoint: PhaseIIIReviewCheckpoint,
    decision: PhaseIIIReviewDecisionValue,
) -> None:
    package, package_sha256, package_id = _write_package(
        tmp_path / "review-package.json",
        (("unknown_1", "state_1"),),
        checkpoint=checkpoint,
    )
    decisions_path = tmp_path / "decisions.json"
    expected = _write_decisions(
        decisions_path,
        package_sha256,
        (_decision("state_1", decision),),
        checkpoint=checkpoint,
        package_id=package_id,
    )

    output = stage_phase3_review_decisions(
        _request(
            package=package,
            decisions=decisions_path,
            output=tmp_path / "staged",
            checkpoint=checkpoint,
        )
    )

    observed = load_contract(
        output.canonical_decision,
        "phase3-review-decisions",
        progress=False,
    )
    assert isinstance(observed, PhaseIIIReviewDecisionFile)
    assert observed == expected
    assert observed.decisions[0].decision is decision


@pytest.mark.parametrize(
    ("package_parent", "current_parent", "message"),
    (
        (
            OwnedPhaseIIIParentRun(
                run_id="gtd-stale-run",
                profile=PARENT.profile,
                phase=PARENT.phase,
            ),
            PARENT,
            "stale or different parent run",
        ),
        (
            OwnedPhaseIIIParentRun(
                run_id=PARENT.run_id,
                profile="unknown-screen-old",
                phase=PARENT.phase,
            ),
            PARENT,
            "profile differs",
        ),
        (
            OwnedPhaseIIIParentRun(
                run_id=PARENT.run_id,
                profile=PARENT.profile,
                phase="phase3-foundation",
            ),
            PARENT,
            "phase differs",
        ),
    ),
)
def test_stale_parent_run_profile_or_phase_fails_closed(
    tmp_path: Path,
    package_parent: OwnedPhaseIIIParentRun,
    current_parent: OwnedPhaseIIIParentRun,
    message: str,
) -> None:
    package, package_sha256, package_id = _write_package(
        tmp_path / "review-package.json",
        (("unknown_1", "state_1"),),
        parent=package_parent,
    )
    decisions = tmp_path / "decisions.json"
    _write_decisions(
        decisions,
        package_sha256,
        (_decision("state_1", PhaseIIIReviewDecisionValue.APPROVE),),
        parent_run_id=package_parent.run_id,
        package_id=package_id,
    )

    with pytest.raises(PhaseIIIReviewStageError, match=message):
        stage_phase3_review_decisions(
            _request(
                package=package,
                decisions=decisions,
                output=tmp_path / "staged",
                parent=current_parent,
            )
        )


def test_decision_for_a_different_review_package_fails_closed(tmp_path: Path) -> None:
    package, package_sha256, _package_id = _write_package(
        tmp_path / "review-package.json",
        (("unknown_1", "state_1"),),
    )
    decisions = tmp_path / "decisions.json"
    _write_decisions(
        decisions,
        package_sha256,
        (_decision("state_1", PhaseIIIReviewDecisionValue.APPROVE),),
        package_id="reviewpkg_other",
    )

    with pytest.raises(PhaseIIIReviewStageError, match="different review package"):
        stage_phase3_review_decisions(
            _request(
                package=package,
                decisions=decisions,
                output=tmp_path / "staged",
            )
        )


def test_decision_for_an_unknown_package_target_fails_closed(tmp_path: Path) -> None:
    package, package_sha256, package_id = _write_package(
        tmp_path / "review-package.json",
        (("unknown_1", "state_allowed"),),
    )
    decisions = tmp_path / "decisions.json"
    _write_decisions(
        decisions,
        package_sha256,
        (_decision("state_unknown", PhaseIIIReviewDecisionValue.APPROVE),),
        package_id=package_id,
    )

    with pytest.raises(PhaseIIIReviewStageError, match="absent from the exact"):
        stage_phase3_review_decisions(
            _request(
                package=package,
                decisions=decisions,
                output=tmp_path / "staged",
            )
        )


def test_decision_before_package_creation_fails_closed(tmp_path: Path) -> None:
    package, package_sha256, package_id = _write_package(
        tmp_path / "review-package.json",
        (("unknown_1", "state_1"),),
    )
    decisions = tmp_path / "decisions.json"
    _write_decisions(
        decisions,
        package_sha256,
        (
            _decision(
                "state_1",
                PhaseIIIReviewDecisionValue.APPROVE,
                reviewed_at=PACKAGE_CREATED - timedelta(seconds=1),
            ),
        ),
        package_id=package_id,
    )

    with pytest.raises(PhaseIIIReviewStageError, match="predates"):
        stage_phase3_review_decisions(
            _request(
                package=package,
                decisions=decisions,
                output=tmp_path / "staged",
            )
        )


def test_wrong_manifest_or_transported_decision_checksum_fails_closed(
    tmp_path: Path,
) -> None:
    package, package_sha256, package_id = _write_package(
        tmp_path / "review-package.json",
        (("unknown_1", "state_1"),),
    )
    decisions = tmp_path / "decisions.json"
    _write_decisions(
        decisions,
        "f" * 64,
        (_decision("state_1", PhaseIIIReviewDecisionValue.APPROVE),),
        package_id=package_id,
    )
    with pytest.raises(PhaseIIIReviewStageError, match="manifest checksum"):
        stage_phase3_review_decisions(
            _request(
                package=package,
                decisions=decisions,
                output=tmp_path / "wrong-package-stage",
            )
        )

    _write_decisions(
        decisions,
        package_sha256,
        (_decision("state_1", PhaseIIIReviewDecisionValue.APPROVE),),
        package_id=package_id,
    )
    with pytest.raises(PhaseIIIReviewStageError, match="independent confirmation"):
        stage_phase3_review_decisions(
            _request(
                package=package,
                decisions=decisions,
                output=tmp_path / "wrong-decision-stage",
                confirmed_sha256="0" * 64,
            )
        )


def test_stale_decision_content_id_fails_even_with_current_byte_checksum(
    tmp_path: Path,
) -> None:
    package, package_sha256, package_id = _write_package(
        tmp_path / "review-package.json",
        (("unknown_1", "state_1"),),
    )
    decisions = tmp_path / "decisions.json"
    _write_decisions(
        decisions,
        package_sha256,
        (_decision("state_1", PhaseIIIReviewDecisionValue.APPROVE),),
        package_id=package_id,
    )
    document = json.loads(decisions.read_text(encoding="utf-8"))
    document["decisions"][0]["reason"] = "edited after identity derivation"
    decisions.write_text(json.dumps(document) + "\n", encoding="utf-8")

    with pytest.raises(PhaseIIIReviewStageError, match="decision_file_id"):
        stage_phase3_review_decisions(
            _request(
                package=package,
                decisions=decisions,
                output=tmp_path / "staged",
            )
        )


def test_decision_file_change_during_validation_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package, package_sha256, package_id = _write_package(
        tmp_path / "review-package.json",
        (("unknown_1", "state_1"),),
    )
    decisions = tmp_path / "decisions.json"
    _write_decisions(
        decisions,
        package_sha256,
        (_decision("state_1", PhaseIIIReviewDecisionValue.APPROVE),),
        package_id=package_id,
    )
    original_load = phase3_stage._load_decisions

    def _load_then_mutate(path: Path) -> PhaseIIIReviewDecisionFile:
        loaded = original_load(path)
        path.write_bytes(path.read_bytes() + b"\n")
        return loaded

    monkeypatch.setattr(phase3_stage, "_load_decisions", _load_then_mutate)

    with pytest.raises(PhaseIIIReviewStageError, match="changed during"):
        stage_phase3_review_decisions(
            _request(
                package=package,
                decisions=decisions,
                output=tmp_path / "staged",
            )
        )


@pytest.mark.parametrize(
    ("rows", "targets", "message"),
    (
        (
            (
                ("state_1", "approve"),
                ("state_1", "reject"),
            ),
            (("unknown_1", "state_1"),),
            "duplicate or conflict",
        ),
        (
            tuple((f"state_{index}", "approve") for index in range(1, 7)),
            tuple(("unknown_1", f"state_{index}") for index in range(1, 7)),
            "approved A states",
        ),
    ),
)
def test_duplicate_or_over_cap_decision_tsv_fails_the_typed_contract(
    tmp_path: Path,
    rows: tuple[tuple[str, str], ...],
    targets: tuple[tuple[str, str], ...],
    message: str,
) -> None:
    package, package_sha256, package_id = _write_package(
        tmp_path / "review-package.json",
        targets,
    )
    decisions = tmp_path / "decisions.tsv"
    header = (
        "checkpoint\towned_parent_run_id\treview_package_id\t"
        "review_package_manifest_sha256\tcrystal_id\titem_id\tdecision\t"
        "reviewer\treviewed_at\treason\n"
    )
    body = "".join(
        f"a_seed\t{PARENT.run_id}\t{package_id}\t{package_sha256}\t"
        f"unknown_1\t{item_id}\t{decision}\treviewer_1\t"
        "2026-08-23T16:05:00Z\tmap inspected\n"
        for item_id, decision in rows
    )
    decisions.write_text(header + body, encoding="utf-8")

    with pytest.raises(PhaseIIIReviewStageError, match=message):
        stage_phase3_review_decisions(
            _request(
                package=package,
                decisions=decisions,
                output=tmp_path / "staged",
            )
        )


def test_stage_refuses_even_an_empty_pre_existing_output_directory(
    tmp_path: Path,
) -> None:
    package, package_sha256, package_id = _write_package(
        tmp_path / "review-package.json",
        (("unknown_1", "state_1"),),
    )
    decisions = tmp_path / "decisions.json"
    _write_decisions(
        decisions,
        package_sha256,
        (_decision("state_1", PhaseIIIReviewDecisionValue.APPROVE),),
        package_id=package_id,
    )
    output = tmp_path / "staged"
    output.mkdir()

    with pytest.raises(PhaseIIIReviewStageError, match="new absent directory"):
        stage_phase3_review_decisions(
            _request(package=package, decisions=decisions, output=output)
        )
