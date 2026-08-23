"""Materialise the synthetic public unknown-pass-1 integration fixture."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.execution.unknown_screen import (
    UnknownPass1CrystalInput,
    UnknownPass1ModelInput,
    UnknownPass1SharedPreparationInput,
    build_unknown_pass1_screen_inventory,
    write_unknown_pass1_screen_inventory,
)
from genome_to_diffraction.review.phase3_stage import (
    OwnedPhaseIIIParentRun,
    PhaseIIIReviewStageRequest,
    stage_phase3_review_decisions,
)
from genome_to_diffraction.schemas.v2 import (
    ExecutionArtifactIdentity,
    ExecutionToolIdentity,
    ModelUnavailableReason,
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecision,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
    PhaseIIIReviewPackageManifest,
    PhaseIIIReviewPackageTarget,
    UnknownPass1AHypothesis,
    UnknownPass1AHypothesisDisposition,
    UnknownPass1ScreenInventory,
)

PUBLIC_STUB_CRYSTAL_IDS = (
    "public_stub_01",
    "public_stub_02",
    "public_stub_03",
)
_PHENIX = (
    "phenix.maps",
    "phenix.phaser",
    "phenix.process_predicted_model",
    "phenix.refine",
    "phenix.reflection_file_converter",
    "phenix.sequence_from_map",
    "phenix.xtriage",
)


@dataclass(frozen=True, slots=True)
class UnknownPass1PublicFixture:
    """Materialised local inputs and their validated path-free inventory."""

    input_root: Path
    execution_identity: Path
    review_stage: Path
    shared_preparation: UnknownPass1SharedPreparationInput
    crystals: tuple[UnknownPass1CrystalInput, ...]
    inventory: UnknownPass1ScreenInventory


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _model_bytes(crystal_id: str, rank: int) -> bytes:
    model_group = ((rank - 1) // 4) + 1
    return f"synthetic-public-model:{crystal_id}:{model_group}\n".encode("ascii")


def public_stub_model_bytes(crystal_id: str, rank: int) -> bytes:
    """Return the exact deterministic bytes for one synthetic model."""

    return _model_bytes(crystal_id, rank)


def _artifact(
    scope: str,
    owner_id: str,
    role: str,
    path: Path,
) -> ExecutionArtifactIdentity:
    return ExecutionArtifactIdentity.from_content(
        scope=scope,
        owner_id=owner_id,
        role=role,
        sha256=sha256_file(path, progress=False),
        size_bytes=path.stat().st_size,
        release_or_source="synthetic-public-stub",
    )


def _hypothesis(
    crystal_id: str,
    rank: int,
    disposition: UnknownPass1AHypothesisDisposition,
    *,
    allocation_rank: int | None = None,
) -> UnknownPass1AHypothesis:
    model_available = (
        disposition is not UnknownPass1AHypothesisDisposition.UNSEARCHABLE_NO_MODEL
    )
    model_group = ((rank - 1) // 4) + 1
    sequence_key = (
        f"model-group:{model_group}" if model_available else f"no-model:{rank}"
    )
    return UnknownPass1AHypothesis.from_content(
        crystal_id=crystal_id,
        candidate_rank=rank,
        allocation_rank=allocation_rank,
        sequence_group_id=f"seq_{_digest(f'{crystal_id}:sequence:{sequence_key}')}",
        requested_copy_count=((rank - 1) % 4) + 1,
        model_id=f"model_{_digest(f'{crystal_id}:model:{model_group}')}"
        if model_available
        else None,
        model_sha256=hashlib.sha256(_model_bytes(crystal_id, rank)).hexdigest()
        if model_available
        else None,
        disposition=disposition,
        no_model_reason=ModelUnavailableReason.NO_ELIGIBLE_MODEL
        if not model_available
        else None,
    )


def public_stub_hypothesis(
    crystal_id: str,
    rank: int,
    disposition: UnknownPass1AHypothesisDisposition,
    *,
    allocation_rank: int | None = None,
) -> UnknownPass1AHypothesis:
    """Build one deterministic synthetic A hypothesis for focused mutations."""

    return _hypothesis(
        crystal_id,
        rank,
        disposition,
        allocation_rank=allocation_rank,
    )


def materialise_unknown_pass1_public_fixture(
    launch_root: Path,
) -> UnknownPass1PublicFixture:
    """Write fixed local inputs and return their validated screen inventory."""

    input_root = launch_root / "inputs"
    input_root.mkdir()
    catalogue_faa = input_root / "catalogue.faa"
    catalogue_faa.write_text(">stub_a\nMPEPTIDE\n", encoding="ascii")
    annotation = input_root / "annotation.gff"
    annotation.write_text("##gff-version 3\n", encoding="ascii")
    database = input_root / "database.json"
    database.write_text('{"database":"synthetic-public-stub"}\n', encoding="ascii")

    mtz_root = input_root / "crystal_mtz"
    mtz_root.mkdir()
    mtz_paths: dict[str, Path] = {}
    for crystal_id in PUBLIC_STUB_CRYSTAL_IDS:
        path = mtz_root / f"{crystal_id}.mtz"
        path.write_text(f"synthetic-public-mtz:{crystal_id}\n", encoding="ascii")
        mtz_paths[crystal_id] = path

    execution = PhaseIIIExecutionIdentity.from_content(
        source_commit="1" * 40,
        source_tree="2" * 40,
        nf_helper_commit="3" * 40,
        pixi_lock_sha256="4" * 64,
        execution_policy_sha256="5" * 64,
        catalogue_artifacts=tuple(
            sorted(
                (
                    _artifact(
                        "catalogue",
                        "public_catalogue",
                        "annotation_gff",
                        annotation,
                    ),
                    _artifact(
                        "catalogue",
                        "public_catalogue",
                        "proteome_faa",
                        catalogue_faa,
                    ),
                ),
                key=lambda item: (item.owner_id, item.role, item.artifact_id),
            )
        ),
        crystal_artifacts=tuple(
            sorted(
                (
                    _artifact("crystal", crystal_id, "mtz", mtz_paths[crystal_id])
                    for crystal_id in PUBLIC_STUB_CRYSTAL_IDS
                ),
                key=lambda item: (item.owner_id, item.role, item.artifact_id),
            )
        ),
        database_artifacts=(
            _artifact("database", "public_database", "database_manifest", database),
        ),
        tools=tuple(
            sorted(
                (
                    ExecutionToolIdentity.from_content(
                        name=name,
                        version="synthetic-stub-not-executed",
                        executable_sha256=_digest(f"tool:{name}"),
                        adapter_version="unknown-pass1-stub-v1",
                    )
                    for name in _PHENIX
                ),
                key=lambda item: (item.name, item.tool_identity_id),
            )
        ),
        adapter_versions=(
            ("unknown_pass1_inventory", "unknown-pass1-screen-v1"),
            ("unknown_pass1_stub", "unknown-pass1-nextflow-stub-v1"),
        ),
    )
    execution_path = input_root / "phase3_execution_identity.json"
    atomic_write_json(execution_path, execution.model_dump(mode="json"))

    created_at = datetime(2026, 8, 23, 18, 0, tzinfo=UTC)
    parent = OwnedPhaseIIIParentRun(
        run_id="public-unknown-pass1-stub-parent",
        profile="unknown-screen-local-stub",
        phase="unknown-pass1-crystallographic-review",
    )
    package = PhaseIIIReviewPackageManifest(
        schema_version="2.0",
        review_package_id="public-crystallographic-review-package",
        checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        owned_parent_run_id=parent.run_id,
        parent_profile=parent.profile,
        parent_phase=parent.phase,
        created_at=created_at,
        permitted_targets=tuple(
            PhaseIIIReviewPackageTarget(
                crystal_id=crystal_id,
                item_id="crystallographic-dataset",
            )
            for crystal_id in PUBLIC_STUB_CRYSTAL_IDS
        ),
    )
    package_path = input_root / "review_package.json"
    atomic_write_json(package_path, package.model_dump(mode="json"))
    decision_values = (
        PhaseIIIReviewDecisionValue.PROCEED,
        PhaseIIIReviewDecisionValue.HOLD,
        PhaseIIIReviewDecisionValue.PROCEED,
    )
    decisions = PhaseIIIReviewDecisionFile.from_content(
        checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        owned_parent_run_id=parent.run_id,
        review_package_id=package.review_package_id,
        review_package_manifest_sha256=sha256_file(package_path, progress=False),
        decisions=tuple(
            PhaseIIIReviewDecision(
                crystal_id=crystal_id,
                item_id="crystallographic-dataset",
                decision=decision,
                reviewer="synthetic-public-stub-reviewer",
                reviewed_at=created_at + timedelta(minutes=index),
                reason="exercise a typed public-fixture review branch",
            )
            for index, (crystal_id, decision) in enumerate(
                zip(PUBLIC_STUB_CRYSTAL_IDS, decision_values, strict=True),
                start=1,
            )
        ),
    )
    decisions_path = input_root / "review_decisions.json"
    atomic_write_json(decisions_path, decisions.model_dump(mode="json"))
    review_stage = input_root / "review_stage"
    stage_phase3_review_decisions(
        PhaseIIIReviewStageRequest(
            parent=parent,
            checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            review_package_manifest=package_path,
            decisions=decisions_path,
            confirmed_decisions_sha256=sha256_file(decisions_path, progress=False),
            output_directory=review_stage,
        )
    )

    catalogue_preparation = input_root / "catalogue_preparation.json"
    catalogue_preparation.write_text(
        '{"preparation_id":"public-catalogue-prepared-once"}\n',
        encoding="ascii",
    )
    provider_preparation = input_root / "provider_preparation.json"
    provider_preparation.write_text(
        '{"preparation_id":"public-provider-prepared-once",'
        '"remote_sequence_submission":false}\n',
        encoding="ascii",
    )
    localisation_preparation = input_root / "localisation_preparation.json"
    localisation_preparation.write_text(
        '{"execution_mode":"local_offline",'
        '"preparation_id":"public-localisation-prepared-once"}\n',
        encoding="ascii",
    )
    shared = UnknownPass1SharedPreparationInput(
        catalogue_preparation_id="public-catalogue-prepared-once",
        catalogue_preparation=catalogue_preparation,
        provider_preparation_id="public-provider-prepared-once",
        provider_preparation=provider_preparation,
        localisation_preparation_id="public-localisation-prepared-once",
        localisation_preparation=localisation_preparation,
    )

    first_hypotheses = (
        *(
            _hypothesis(
                PUBLIC_STUB_CRYSTAL_IDS[0],
                rank,
                UnknownPass1AHypothesisDisposition.SELECTED,
                allocation_rank=rank,
            )
            for rank in range(1, 26)
        ),
        _hypothesis(
            PUBLIC_STUB_CRYSTAL_IDS[0],
            26,
            UnknownPass1AHypothesisDisposition.DEFERRED_CAP,
        ),
        _hypothesis(
            PUBLIC_STUB_CRYSTAL_IDS[0],
            27,
            UnknownPass1AHypothesisDisposition.UNSEARCHABLE_NO_MODEL,
        ),
    )
    third_hypotheses = tuple(
        _hypothesis(
            PUBLIC_STUB_CRYSTAL_IDS[2],
            rank,
            UnknownPass1AHypothesisDisposition.UNSEARCHABLE_NO_MODEL,
        )
        for rank in range(1, 3)
    )
    model_root = input_root / "models"
    model_root.mkdir()
    model_inputs: list[UnknownPass1ModelInput] = []
    materialised_model_ids: set[str] = set()
    for hypothesis in first_hypotheses:
        if hypothesis.model_id is None or hypothesis.model_id in materialised_model_ids:
            continue
        model = model_root / f"{hypothesis.model_id}.pdb"
        model.write_bytes(
            _model_bytes(hypothesis.crystal_id, hypothesis.candidate_rank)
        )
        model_inputs.append(UnknownPass1ModelInput(hypothesis.model_id, model))
        materialised_model_ids.add(hypothesis.model_id)
    crystals = (
        UnknownPass1CrystalInput(
            PUBLIC_STUB_CRYSTAL_IDS[0],
            mtz_paths[PUBLIC_STUB_CRYSTAL_IDS[0]],
            first_hypotheses,
            tuple(model_inputs),
        ),
        UnknownPass1CrystalInput(
            PUBLIC_STUB_CRYSTAL_IDS[1],
            mtz_paths[PUBLIC_STUB_CRYSTAL_IDS[1]],
            (),
        ),
        UnknownPass1CrystalInput(
            PUBLIC_STUB_CRYSTAL_IDS[2],
            mtz_paths[PUBLIC_STUB_CRYSTAL_IDS[2]],
            third_hypotheses,
        ),
    )
    inventory = build_unknown_pass1_screen_inventory(
        execution_identity_path=execution_path,
        review_stage_directory=review_stage,
        shared_preparation_input=shared,
        crystals=crystals,
    )
    write_unknown_pass1_screen_inventory(
        inventory,
        input_root / "unknown_pass1_screen_inventory.json",
    )
    crystal_item_root = input_root / "crystal_items"
    crystal_item_root.mkdir()
    for item in inventory.crystals:
        atomic_write_json(
            crystal_item_root / f"{item.crystal_id}--{item.branch.value}.json",
            item.model_dump(mode="json", exclude_none=False),
        )
    hypothesis_task_root = input_root / "hypothesis_tasks"
    hypothesis_task_root.mkdir()
    for task in inventory.hypothesis_tasks:
        atomic_write_json(
            hypothesis_task_root
            / f"{task.model_id}--{task.crystal_id}--{task.allocation_rank}.json",
            task.model_dump(mode="json", exclude_none=False),
        )
    return UnknownPass1PublicFixture(
        input_root=input_root,
        execution_identity=execution_path,
        review_stage=review_stage,
        shared_preparation=shared,
        crystals=crystals,
        inventory=inventory,
    )


__all__ = [
    "PUBLIC_STUB_CRYSTAL_IDS",
    "UnknownPass1PublicFixture",
    "materialise_unknown_pass1_public_fixture",
    "public_stub_hypothesis",
    "public_stub_model_bytes",
]
