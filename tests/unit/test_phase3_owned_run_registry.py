"""Focused trust-boundary tests for the local Phase III owned-run registry."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.review import (
    OwnedPhaseIIIParentRun,
    OwnedPhaseIIIReviewPackageSource,
    PhaseIIIOwnedRunError,
    PhaseIIIReviewEvidenceSource,
    PhaseIIIReviewPackageRequest,
    build_phase3_review_package,
    register_phase3_owned_run,
    resolve_phase3_owned_review_package,
    validate_phase3_owned_run_registry,
)
from genome_to_diffraction.schemas.v2 import (
    ExecutionArtifactIdentity,
    ExecutionToolIdentity,
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
)

RUN_ID = "gtd-phase3-owned-run"
PROFILE = "unknown-screen"
PHASE = "phase3-pass1"
SOURCE_COMMIT = "1" * 40
SOURCE_TREE = "2" * 40
CRYSTAL_A = "AD4QS1P4G2_18"
CRYSTAL_B = "CD4QS2P2G1_15"
RUN_COMPLETED_AT = datetime(2026, 8, 23, 20, 0, tzinfo=UTC)
PACKAGE_CREATED_AT = RUN_COMPLETED_AT + timedelta(hours=1)
_PHENIX = (
    "phenix.maps",
    "phenix.phaser",
    "phenix.process_predicted_model",
    "phenix.refine",
    "phenix.reflection_file_converter",
    "phenix.sequence_from_map",
    "phenix.xtriage",
)


def _artifact(
    scope: str,
    owner_id: str,
    role: str,
    digest_character: str,
) -> ExecutionArtifactIdentity:
    return ExecutionArtifactIdentity.from_content(
        scope=scope,
        owner_id=owner_id,
        role=role,
        sha256=digest_character * 64,
        size_bytes=100,
        release_or_source="frozen-test-source",
    )


def _execution_identity() -> PhaseIIIExecutionIdentity:
    catalogue = tuple(
        sorted(
            (
                _artifact("catalogue", "catalogue_01", "annotation_gff", "a"),
                _artifact("catalogue", "catalogue_01", "proteome_faa", "b"),
            ),
            key=lambda item: (item.owner_id, item.role, item.artifact_id),
        )
    )
    crystals = tuple(
        sorted(
            (
                _artifact("crystal", CRYSTAL_A, "mtz", "c"),
                _artifact("crystal", CRYSTAL_B, "mtz", "d"),
            ),
            key=lambda item: (item.owner_id, item.role, item.artifact_id),
        )
    )
    tools = tuple(
        sorted(
            (
                ExecutionToolIdentity.from_content(
                    name=name,
                    version="2.1-6048",
                    executable_sha256=f"{index:x}" * 64,
                    adapter_version="phase3-test-v1",
                )
                for index, name in enumerate(_PHENIX, start=1)
            ),
            key=lambda item: (item.name, item.tool_identity_id),
        )
    )
    return PhaseIIIExecutionIdentity.from_content(
        source_commit=SOURCE_COMMIT,
        source_tree=SOURCE_TREE,
        nf_helper_commit="3" * 40,
        pixi_lock_sha256="4" * 64,
        execution_policy_sha256="5" * 64,
        catalogue_artifacts=catalogue,
        crystal_artifacts=crystals,
        database_artifacts=(
            _artifact("database", "pdb_2026_08", "database_manifest", "f"),
        ),
        tools=tools,
        adapter_versions=(("unknown_screen", "phase3-unknown-screen-v1"),),
    )


def _write_execution_identity(tmp_path: Path) -> tuple[Path, PhaseIIIExecutionIdentity]:
    identity = _execution_identity()
    path = tmp_path / "phase3_execution_identity.input.json"
    atomic_write_json(path, identity.model_dump(mode="json", exclude_none=False))
    return path, identity


def _build_package(
    tmp_path: Path,
    *,
    name: str,
    identity: PhaseIIIExecutionIdentity,
    crystal_id: str,
    checkpoint: PhaseIIIReviewCheckpoint,
    run_id: str = RUN_ID,
    profile: str = PROFILE,
    phase: str = PHASE,
    created_at: datetime = PACKAGE_CREATED_AT,
) -> Path:
    input_root = tmp_path / f"{name}-inputs"
    input_root.mkdir()
    (input_root / "evidence.json").write_text(
        '{"status":"review_required"}\n',
        encoding="ascii",
    )
    package = tmp_path / name
    package.mkdir()
    build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=checkpoint,
            owned_parent_run_id=run_id,
            parent_profile=profile,
            parent_phase=phase,
            execution_identity_id=identity.execution_identity_id,
            crystal_id=crystal_id,
            target_item_ids=(f"{crystal_id}_target",),
            created_at=created_at,
            input_root=input_root,
            evidence_sources=(
                PhaseIIIReviewEvidenceSource(
                    role="review_evidence",
                    relative_path="evidence.json",
                ),
            ),
            output_directory=package,
        )
    )
    return package


def _parent() -> OwnedPhaseIIIParentRun:
    return OwnedPhaseIIIParentRun(RUN_ID, PROFILE, PHASE)


def _sources(
    tmp_path: Path,
    identity: PhaseIIIExecutionIdentity,
) -> tuple[OwnedPhaseIIIReviewPackageSource, ...]:
    return (
        OwnedPhaseIIIReviewPackageSource(
            crystal_id=CRYSTAL_A,
            checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            package_directory=_build_package(
                tmp_path,
                name="crystal-a-review",
                identity=identity,
                crystal_id=CRYSTAL_A,
                checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            ),
        ),
        OwnedPhaseIIIReviewPackageSource(
            crystal_id=CRYSTAL_A,
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            package_directory=_build_package(
                tmp_path,
                name="crystal-a-seed",
                identity=identity,
                crystal_id=CRYSTAL_A,
                checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            ),
        ),
        OwnedPhaseIIIReviewPackageSource(
            crystal_id=CRYSTAL_B,
            checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            package_directory=_build_package(
                tmp_path,
                name="crystal-b-review",
                identity=identity,
                crystal_id=CRYSTAL_B,
                checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            ),
        ),
    )


def _register(
    tmp_path: Path,
) -> tuple[
    Path, PhaseIIIExecutionIdentity, tuple[OwnedPhaseIIIReviewPackageSource, ...]
]:
    execution_path, identity = _write_execution_identity(tmp_path)
    sources = _sources(tmp_path, identity)
    output = tmp_path / "local-owned-run-registry"
    output.mkdir()
    register_phase3_owned_run(
        parent=_parent(),
        completed_at=RUN_COMPLETED_AT,
        execution_identity=execution_path,
        packages=sources,
        output_directory=output,
    )
    return output, identity, sources


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_registers_path_free_records_and_resolves_exact_owned_package(
    tmp_path: Path,
) -> None:
    output, identity, _ = _register(tmp_path)

    registry = validate_phase3_owned_run_registry(output)
    resolved = resolve_phase3_owned_review_package(
        output,
        run_id=RUN_ID,
        crystal_id=CRYSTAL_A,
        checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
    )

    assert registry.execution_status == "completed_success"
    assert registry.execution_identity_id == identity.execution_identity_id
    assert len(registry.packages) == 3
    assert resolved.parent.run_id == RUN_ID
    assert resolved.crystal_id == CRYSTAL_A
    assert resolved.checkpoint is PhaseIIIReviewCheckpoint.A_SEED
    assert resolved.package_manifest.is_file()
    record_text = (output / "phase3_owned_run_registry.json").read_text(
        encoding="ascii"
    )
    identity_text = (output / "phase3_execution_identity.json").read_text(
        encoding="ascii"
    )
    assert str(tmp_path) not in record_text
    assert str(tmp_path) not in identity_text
    assert "package_directory" not in record_text


def test_package_order_does_not_change_registry_bytes(tmp_path: Path) -> None:
    execution_path, identity = _write_execution_identity(tmp_path)
    sources = _sources(tmp_path, identity)
    first = tmp_path / "registry-a"
    second = tmp_path / "registry-b"
    first.mkdir()
    second.mkdir()

    first_output = register_phase3_owned_run(
        parent=_parent(),
        completed_at=RUN_COMPLETED_AT,
        execution_identity=execution_path,
        packages=sources,
        output_directory=first,
    )
    second_output = register_phase3_owned_run(
        parent=_parent(),
        completed_at=RUN_COMPLETED_AT,
        execution_identity=execution_path,
        packages=tuple(reversed(sources)),
        output_directory=second,
    )

    assert first_output.owned_run_registry_id == second_output.owned_run_registry_id
    assert _tree_bytes(first) == _tree_bytes(second)


@pytest.mark.parametrize(
    (
        "package_run_id",
        "package_profile",
        "package_phase",
        "declared_crystal",
        "declared_checkpoint",
        "message",
    ),
    (
        (
            "another-run",
            PROFILE,
            PHASE,
            CRYSTAL_A,
            PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            "parent run differs",
        ),
        (
            RUN_ID,
            "another-profile",
            PHASE,
            CRYSTAL_A,
            PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            "profile differs",
        ),
        (
            RUN_ID,
            PROFILE,
            "another-phase",
            CRYSTAL_A,
            PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            "phase differs",
        ),
        (
            RUN_ID,
            PROFILE,
            PHASE,
            CRYSTAL_B,
            PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            "crystal differs",
        ),
        (
            RUN_ID,
            PROFILE,
            PHASE,
            CRYSTAL_A,
            PhaseIIIReviewCheckpoint.A_SEED,
            "checkpoint differs",
        ),
    ),
)
def test_rejects_stale_cross_run_cross_crystal_and_cross_checkpoint_packages(
    tmp_path: Path,
    package_run_id: str,
    package_profile: str,
    package_phase: str,
    declared_crystal: str,
    declared_checkpoint: PhaseIIIReviewCheckpoint,
    message: str,
) -> None:
    execution_path, identity = _write_execution_identity(tmp_path)
    package = _build_package(
        tmp_path,
        name="directory-name-does-not-prove-ownership",
        identity=identity,
        crystal_id=CRYSTAL_A,
        checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        run_id=package_run_id,
        profile=package_profile,
        phase=package_phase,
    )
    source = OwnedPhaseIIIReviewPackageSource(
        crystal_id=declared_crystal,
        checkpoint=declared_checkpoint,
        package_directory=package,
    )
    output = tmp_path / "registry"
    output.mkdir()

    with pytest.raises(PhaseIIIOwnedRunError, match=message):
        register_phase3_owned_run(
            parent=_parent(),
            completed_at=RUN_COMPLETED_AT,
            execution_identity=execution_path,
            packages=(source,),
            output_directory=output,
        )

    assert list(output.iterdir()) == []


def test_rejects_duplicate_crystal_checkpoint_registration(tmp_path: Path) -> None:
    execution_path, identity = _write_execution_identity(tmp_path)
    source = _sources(tmp_path, identity)[0]
    output = tmp_path / "registry"
    output.mkdir()

    with pytest.raises(PhaseIIIOwnedRunError, match="duplicate crystal"):
        register_phase3_owned_run(
            parent=_parent(),
            completed_at=RUN_COMPLETED_AT,
            execution_identity=execution_path,
            packages=(source, source),
            output_directory=output,
        )


@pytest.mark.parametrize("mutation", ("changed", "missing", "extra"))
def test_lookup_rejects_mutated_missing_or_extra_package_files(
    tmp_path: Path,
    mutation: str,
) -> None:
    output, _, _ = _register(tmp_path)
    registry = validate_phase3_owned_run_registry(output)
    package = next(
        item
        for item in registry.packages
        if item.crystal_id == CRYSTAL_A
        and item.checkpoint is PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC
    )
    package_root = output / "packages" / package.review_package_id
    evidence = next((package_root / "evidence").iterdir())
    if mutation == "changed":
        evidence.write_bytes(b"x" * evidence.stat().st_size)
    elif mutation == "missing":
        evidence.unlink()
    else:
        (package_root / "unexpected.txt").write_text("unexpected\n", encoding="ascii")

    with pytest.raises(PhaseIIIOwnedRunError):
        resolve_phase3_owned_review_package(
            output,
            run_id=RUN_ID,
            crystal_id=CRYSTAL_A,
            checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        )


def test_lookup_rejects_cross_run_and_missing_crystal_checkpoint(
    tmp_path: Path,
) -> None:
    output, _, _ = _register(tmp_path)

    with pytest.raises(PhaseIIIOwnedRunError, match="requested run differs"):
        resolve_phase3_owned_review_package(
            output,
            run_id="another-run",
            crystal_id=CRYSTAL_A,
            checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        )
    with pytest.raises(PhaseIIIOwnedRunError, match="package is missing"):
        resolve_phase3_owned_review_package(
            output,
            run_id=RUN_ID,
            crystal_id=CRYSTAL_B,
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
        )


def test_package_created_before_completed_run_is_rejected(tmp_path: Path) -> None:
    execution_path, identity = _write_execution_identity(tmp_path)
    package = _build_package(
        tmp_path,
        name="stale-package",
        identity=identity,
        crystal_id=CRYSTAL_A,
        checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        created_at=RUN_COMPLETED_AT - timedelta(seconds=1),
    )
    output = tmp_path / "registry"
    output.mkdir()

    with pytest.raises(PhaseIIIOwnedRunError, match="predates"):
        register_phase3_owned_run(
            parent=_parent(),
            completed_at=RUN_COMPLETED_AT,
            execution_identity=execution_path,
            packages=(
                OwnedPhaseIIIReviewPackageSource(
                    crystal_id=CRYSTAL_A,
                    checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
                    package_directory=package,
                ),
            ),
            output_directory=output,
        )
