"""Tests for the fixed A-seed decision archive."""

import json
import shutil
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.unknown_single_inputs import (
    UNKNOWN_SINGLE_SPEC_RELATIVE,
    UnknownSingleComponentInputError,
    build_unknown_single_component_input_bundle,
    stage_unknown_single_component_handoff,
    validate_unknown_single_component_input_tree,
)
from genome_to_diffraction.review.phase3_package import (
    PhaseIIIReviewEvidenceSource,
    PhaseIIIReviewPackageRequest,
    build_phase3_review_package,
)
from genome_to_diffraction.schemas.v2 import PhaseIIIReviewCheckpoint
from tests.support.unknown_pass1_fixture import (
    PUBLIC_STUB_CRYSTAL_IDS,
    materialise_unknown_pass1_public_fixture,
)

PARENT = "gtd-unknown-screen-20260825T000000Z-aaaaaaaaaaaa-bbbbbbbb"
HEADER = (
    "checkpoint\towned_parent_run_id\treview_package_id\t"
    "review_package_manifest_sha256\tcrystal_id\titem_id\tdecision\t"
    "reviewer\treviewed_at\treason\n"
)


def _decision(
    path: Path,
    crystal_id: str,
    *,
    parent: str = PARENT,
    review_package_id: str = f"reviewpkg_{'1' * 64}",
    review_package_manifest_sha256: str = "2" * 64,
) -> None:
    path.write_text(
        HEADER + f"a_seed\t{parent}\t{review_package_id}\t"
        f"{review_package_manifest_sha256}\t"
        f"{crystal_id}\tsolution_1\tapprove\treviewer\t"
        "2026-08-25T00:00:00Z\tmap inspected\n",
        encoding="ascii",
    )


def _spec(root: Path, rows: tuple[tuple[str, Path], ...]) -> Path:
    path = root / UNKNOWN_SINGLE_SPEC_RELATIVE
    path.parent.mkdir(parents=True)
    atomic_write_json(
        path,
        {
            "schema_version": "1.0",
            "decisions": [
                {
                    "crystal_id": crystal_id,
                    "path": str(decision),
                    "sha256": sha256_file(decision, progress=False),
                }
                for crystal_id, decision in rows
            ],
        },
    )
    path.chmod(0o600)
    return path


def _real_handoff_fixture(
    tmp_path: Path,
    *,
    completion_field: str,
) -> tuple[Path, Path, Path, str]:
    public_root = tmp_path / "public"
    public_root.mkdir()
    public = materialise_unknown_pass1_public_fixture(public_root)
    crystal_id = PUBLIC_STUB_CRYSTAL_IDS[0]
    execution = json.loads(public.execution_identity.read_text(encoding="utf-8"))
    parent = tmp_path / PARENT
    child = tmp_path / "gtd-unknown-single-component-child"
    (parent / "state").mkdir(parents=True)
    inputs = parent / "artifacts/unknown-screen/inputs"
    results = parent / "artifacts/unknown-screen/results"
    inputs.mkdir(parents=True)
    results.mkdir(parents=True)
    child.mkdir()
    shutil.copy2(public.execution_identity, inputs / "phase3_execution_identity.json")

    evidence_root = tmp_path / "a-review-evidence"
    evidence_root.mkdir()
    (evidence_root / "review.json").write_text(
        '{"execution_status":"completed_success"}\n',
        encoding="ascii",
    )
    package_root = results / f"phase3_owned_a_review_{crystal_id}"
    package_root.mkdir()
    package = build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            owned_parent_run_id=PARENT,
            parent_profile="unknown-screen",
            parent_phase="phase3-pass1",
            execution_identity_id=str(execution["execution_identity_id"]),
            crystal_id=crystal_id,
            target_item_ids=("solution_1",),
            created_at=datetime(2026, 8, 25, tzinfo=UTC),
            input_root=evidence_root,
            evidence_sources=(
                PhaseIIIReviewEvidenceSource(
                    role="mr_seed_review_manifest",
                    relative_path="review.json",
                ),
            ),
            output_directory=package_root,
        )
    )
    hypotheses = results / f"phase3/{crystal_id}/diverse_first_copy_funnel"
    hypotheses.mkdir(parents=True)
    hypotheses.joinpath("mr_hypotheses.jsonl").write_text(
        f"{public.crystals[0].hypotheses[0].model_dump_json()}\n",
        encoding="utf-8",
    )
    terminal = {
        "schema_version": "1.0",
        "run_id": PARENT,
        "profile": "unknown-screen",
        "job_id": "123",
        "started_at": "2026-08-25T00:00:00Z",
        completion_field: "2026-08-25T01:00:00Z",
        "scheduler_state": "COMPLETED",
        "exit_code": 0,
        "failure_class": "success",
        "standard_output": "logs/slurm-123.out",
        "standard_error": "logs/slurm-123.out",
        "application_log": "logs/unknown-screen.log",
        "structured_test_reports": [],
        "retained_artifacts": ["artifacts/unknown-screen"],
    }
    atomic_write_json(parent / "state/job-result.json", terminal)

    decision = tmp_path / "decision.tsv"
    _decision(
        decision,
        crystal_id,
        review_package_id=package.review_package_id,
        review_package_manifest_sha256=sha256_file(package.manifest, progress=False),
    )
    _spec(tmp_path, ((crystal_id, decision),))
    bundle = build_unknown_single_component_input_bundle(
        repository=tmp_path,
        parent_run_id=PARENT,
        archive_path=tmp_path / "inputs.tar",
    )
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(bundle.archive_path, mode="r") as archive:
        archive.extractall(extracted, filter="data")
    return parent, child, extracted, bundle.input_id


def test_unknown_single_decision_archive_round_trips(tmp_path: Path) -> None:
    first_decision = tmp_path / "first.tsv"
    second_decision = tmp_path / "second.tsv"
    _decision(first_decision, "crystal_a")
    _decision(second_decision, "crystal_b")
    _spec(
        tmp_path,
        (("crystal_b", second_decision), ("crystal_a", first_decision)),
    )

    first = build_unknown_single_component_input_bundle(
        repository=tmp_path,
        parent_run_id=PARENT,
        archive_path=tmp_path / "first.tar",
    )
    second = build_unknown_single_component_input_bundle(
        repository=tmp_path,
        parent_run_id=PARENT,
        archive_path=tmp_path / "second.tar",
    )

    assert first.archive_sha256 == second.archive_sha256
    assert first.crystal_ids == ("crystal_a", "crystal_b")
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(first.archive_path, mode="r") as archive:
        archive.extractall(extracted, filter="data")
    assert (
        validate_unknown_single_component_input_tree(
            extracted,
            expected_input_id=first.input_id,
            expected_parent_run_id=PARENT,
        )
        == first.crystal_ids
    )


def test_cross_parent_decision_fails(tmp_path: Path) -> None:
    decision = tmp_path / "decision.tsv"
    _decision(decision, "crystal_a", parent="gtd-unknown-screen-other")
    _spec(tmp_path, (("crystal_a", decision),))

    with pytest.raises(UnknownSingleComponentInputError, match="another authority"):
        build_unknown_single_component_input_bundle(
            repository=tmp_path,
            parent_run_id=PARENT,
            archive_path=tmp_path / "inputs.tar",
        )


def test_checksum_confirmation_is_required(tmp_path: Path) -> None:
    decision = tmp_path / "decision.tsv"
    _decision(decision, "crystal_a")
    spec = _spec(tmp_path, (("crystal_a", decision),))
    document = {
        "schema_version": "1.0",
        "decisions": [
            {
                "crystal_id": "crystal_a",
                "path": str(decision),
                "sha256": "0" * 64,
            }
        ],
    }
    atomic_write_json(spec, document)
    spec.chmod(0o600)

    with pytest.raises(UnknownSingleComponentInputError, match="checksum differs"):
        build_unknown_single_component_input_bundle(
            repository=tmp_path,
            parent_run_id=PARENT,
            archive_path=tmp_path / "inputs.tar",
        )


def test_changed_extracted_decision_fails(tmp_path: Path) -> None:
    decision = tmp_path / "decision.tsv"
    _decision(decision, "crystal_a")
    _spec(tmp_path, (("crystal_a", decision),))
    bundle = build_unknown_single_component_input_bundle(
        repository=tmp_path,
        parent_run_id=PARENT,
        archive_path=tmp_path / "inputs.tar",
    )
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(bundle.archive_path, mode="r") as archive:
        archive.extractall(extracted, filter="data")
    staged = extracted / "decisions/crystal_a.tsv"
    staged.write_bytes(staged.read_bytes() + b"\n")

    with pytest.raises(UnknownSingleComponentInputError, match="changed"):
        validate_unknown_single_component_input_tree(
            extracted,
            expected_input_id=bundle.input_id,
            expected_parent_run_id=PARENT,
        )


def test_handoff_refuses_missing_parent_terminal_evidence(tmp_path: Path) -> None:
    decision = tmp_path / "decision.tsv"
    _decision(decision, "crystal_a")
    _spec(tmp_path, (("crystal_a", decision),))
    bundle = build_unknown_single_component_input_bundle(
        repository=tmp_path,
        parent_run_id=PARENT,
        archive_path=tmp_path / "inputs.tar",
    )
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(bundle.archive_path, mode="r") as archive:
        archive.extractall(extracted, filter="data")
    parent = tmp_path / PARENT
    child = tmp_path / "gtd-unknown-single-component-child"
    parent.mkdir()
    child.mkdir()

    with pytest.raises(UnknownSingleComponentInputError, match="terminal result"):
        stage_unknown_single_component_handoff(
            parent_run_root=parent,
            child_run_root=child,
            input_root=extracted,
            child_run_id=child.name,
            expected_input_id=bundle.input_id,
        )


def test_handoff_accepts_wrapper_completed_at_and_creates_registry(
    tmp_path: Path,
) -> None:
    parent, child, extracted, input_id = _real_handoff_fixture(
        tmp_path,
        completion_field="completed_at",
    )

    output = stage_unknown_single_component_handoff(
        parent_run_root=parent,
        child_run_root=child,
        input_root=extracted,
        child_run_id=child.name,
        expected_input_id=input_id,
    )

    assert (output / "owned_run_registry/phase3_owned_run_registry.json").is_file()
    assert (output / "a_seed_stages" / PUBLIC_STUB_CRYSTAL_IDS[0]).is_dir()
    assert json.loads((output / "reviewed_crystals.json").read_text())["crystals"] == [
        {
            "crystal_id": PUBLIC_STUB_CRYSTAL_IDS[0],
            "hypotheses": f"hypotheses/{PUBLIC_STUB_CRYSTAL_IDS[0]}.jsonl",
            "review_stage": f"a_seed_stages/{PUBLIC_STUB_CRYSTAL_IDS[0]}",
        }
    ]


def test_handoff_rejects_noncanonical_finished_at_alias(tmp_path: Path) -> None:
    parent, child, extracted, input_id = _real_handoff_fixture(
        tmp_path,
        completion_field="finished_at",
    )

    with pytest.raises(
        UnknownSingleComponentInputError,
        match="lacks successful terminal evidence",
    ):
        stage_unknown_single_component_handoff(
            parent_run_root=parent,
            child_run_root=child,
            input_root=extracted,
            child_run_id=child.name,
            expected_input_id=input_id,
        )
