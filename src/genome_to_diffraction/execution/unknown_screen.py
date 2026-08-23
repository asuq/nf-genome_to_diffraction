"""Build the fixed, path-closed Phase III unknown-pass-1 screen inventory.

Scientific purpose
------------------
This local adapter binds a complete global execution identity, three exact
checksum-verified single-crystal crystallographic review stages, one shared
catalogue/provider/localisation preparation, and exactly three synthetic or
operator-owned crystal inputs before Nextflow scheduling.  It selects nothing
scientifically and executes no crystallographic software.

Inputs and outputs
------------------
Inputs are regular local files for the execution identity, three shared
preparation records, a root containing three canonical two-file review-stage
directories, and three
``UnknownPass1CrystalInput`` values containing MTZ paths plus complete ranked A
hypothesis inventories.  The output is one canonical JSON
``UnknownPass1ScreenInventory``.  Paths are resolved and checksummed locally but
never serialised into the inventory.

No external command or tool version is required.  Missing, symlinked, changed,
misbound, duplicate, over-cap, or incomplete inputs raise
``UnknownPass1ScreenError``.  Human holds and empty/no-model scientific branches
remain successful typed records.  The inventory and task content identifiers
are the cache keys.  Focused coverage lives in
``tests/unit/test_unknown_pass1_screen.py`` and the dedicated cached Nextflow
stub.
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.review.phase3_stage import PhaseIIIReviewStageManifest
from genome_to_diffraction.schemas.io import ContractLoadError, parse_json_document
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
)
from genome_to_diffraction.schemas.v2.unknown_screen import (
    UnknownPass1AHypothesis,
    UnknownPass1AHypothesisDisposition,
    UnknownPass1AHypothesisTask,
    UnknownPass1CrystalBranch,
    UnknownPass1CrystalItem,
    UnknownPass1ReviewBinding,
    UnknownPass1ScreenInventory,
    UnknownPass1SharedPreparation,
)
from genome_to_diffraction.status import InputContractError

_CANONICAL_DECISION_NAME = "phase3_review_decision.json"
_STAGE_MANIFEST_NAME = "phase3_review_stage_manifest.json"
_STAGE_FILES = frozenset({_CANONICAL_DECISION_NAME, _STAGE_MANIFEST_NAME})


class UnknownPass1ScreenError(InputContractError):
    """Unknown-pass-1 inputs cannot form a safe complete-item inventory."""


@dataclass(frozen=True, slots=True)
class UnknownPass1ModelInput:
    """Local model bytes for one model-backed ranked A hypothesis."""

    model_id: str
    model: Path


@dataclass(frozen=True, slots=True)
class UnknownPass1CrystalInput:
    """Local MTZ plus the complete ranked A universe for one crystal."""

    crystal_id: str
    mtz: Path
    hypotheses: tuple[UnknownPass1AHypothesis, ...]
    models: tuple[UnknownPass1ModelInput, ...] = ()


@dataclass(frozen=True, slots=True)
class UnknownPass1SharedPreparationInput:
    """One local file and path-free identifier for each shared preparation."""

    catalogue_preparation_id: str
    catalogue_preparation: Path
    provider_preparation_id: str
    provider_preparation: Path
    localisation_preparation_id: str
    localisation_preparation: Path


def _regular_file(path: Path, *, label: str) -> Path:
    try:
        if path.is_symlink():
            raise UnknownPass1ScreenError(f"{label} must not be a symlink")
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise UnknownPass1ScreenError(f"{label} is absent or unreadable") from error
    if not resolved.is_file():
        raise UnknownPass1ScreenError(f"{label} must be a regular file")
    return resolved


def _load_execution_identity(path: Path) -> PhaseIIIExecutionIdentity:
    resolved = _regular_file(path, label="Phase III execution identity")
    try:
        return PhaseIIIExecutionIdentity.model_validate_json(resolved.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise UnknownPass1ScreenError(
            "Phase III execution identity violates its content contract"
        ) from error


def _load_review_stage(
    directory: Path,
) -> tuple[
    PhaseIIIReviewStageManifest,
    PhaseIIIReviewDecisionFile,
    str,
]:
    try:
        if directory.is_symlink():
            raise UnknownPass1ScreenError("review stage must not be a symlink")
        resolved = directory.resolve(strict=True)
    except OSError as error:
        raise UnknownPass1ScreenError("review stage is absent or unreadable") from error
    if not resolved.is_dir():
        raise UnknownPass1ScreenError("review stage must be a directory")
    try:
        member_names = frozenset(path.name for path in resolved.iterdir())
    except OSError as error:
        raise UnknownPass1ScreenError("review stage cannot be enumerated") from error
    if member_names != _STAGE_FILES:
        raise UnknownPass1ScreenError(
            "review stage must contain exactly its canonical two-file allow-list"
        )

    manifest_path = _regular_file(
        resolved / _STAGE_MANIFEST_NAME,
        label="Phase III review stage manifest",
    )
    decision_path = _regular_file(
        resolved / _CANONICAL_DECISION_NAME,
        label="canonical Phase III review decisions",
    )
    try:
        manifest = PhaseIIIReviewStageManifest.model_validate_json(
            manifest_path.read_bytes()
        )
        decisions = PhaseIIIReviewDecisionFile.model_validate_json(
            decision_path.read_bytes()
        )
    except (OSError, ValidationError, ValueError) as error:
        raise UnknownPass1ScreenError(
            "review stage violates its typed content contracts"
        ) from error
    canonical_sha256 = sha256_file(decision_path, progress=False)
    if (
        manifest.checkpoint is not PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC
        or decisions.checkpoint is not PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC
        or manifest.canonical_decision_path != _CANONICAL_DECISION_NAME
        or manifest.canonical_decision_sha256 != canonical_sha256
        or manifest.decision_file_id != decisions.decision_file_id
        or manifest.decision_count != len(decisions.decisions)
        or manifest.owned_parent_run_id != decisions.owned_parent_run_id
    ):
        raise UnknownPass1ScreenError(
            "review stage does not bind the exact crystallographic decisions"
        )
    return manifest, decisions, sha256_file(manifest_path, progress=False)


def _load_review_stages(
    directory: Path,
) -> tuple[
    tuple[PhaseIIIReviewStageManifest, PhaseIIIReviewDecisionFile, str],
    ...,
]:
    """Load exactly three single-crystal crystallographic review stages."""

    try:
        if directory.is_symlink():
            raise UnknownPass1ScreenError("review-stage root must not be a symlink")
        resolved = directory.resolve(strict=True)
    except OSError as error:
        raise UnknownPass1ScreenError(
            "review-stage root is absent or unreadable"
        ) from error
    if not resolved.is_dir():
        raise UnknownPass1ScreenError("review-stage root must be a directory")
    try:
        children = tuple(resolved.iterdir())
    except OSError as error:
        raise UnknownPass1ScreenError(
            "review-stage root cannot be enumerated"
        ) from error
    if len(children) != 3 or any(
        child.is_symlink() or not child.is_dir() for child in children
    ):
        raise UnknownPass1ScreenError(
            "review-stage root must contain exactly three stage directories"
        )
    loaded = tuple(_load_review_stage(child) for child in children)
    if any(len(decisions.decisions) != 1 for _, decisions, _ in loaded):
        raise UnknownPass1ScreenError(
            "each crystallographic review stage must contain one crystal decision"
        )
    ordered = tuple(sorted(loaded, key=lambda item: item[1].decisions[0].crystal_id))
    crystal_ids = tuple(item[1].decisions[0].crystal_id for item in ordered)
    if len(set(crystal_ids)) != 3:
        raise UnknownPass1ScreenError(
            "review stages must cover three distinct crystals"
        )
    return ordered


def _shared_preparation(
    execution_identity_id: str,
    request: UnknownPass1SharedPreparationInput,
) -> UnknownPass1SharedPreparation:
    catalogue = _regular_file(
        request.catalogue_preparation,
        label="shared catalogue preparation",
    )
    provider = _regular_file(
        request.provider_preparation,
        label="shared provider preparation",
    )
    localisation = _regular_file(
        request.localisation_preparation,
        label="shared localisation preparation",
    )
    documents: list[tuple[str, Path, str]] = [
        ("catalogue", catalogue, request.catalogue_preparation_id),
        ("provider", provider, request.provider_preparation_id),
        ("localisation", localisation, request.localisation_preparation_id),
    ]
    parsed: dict[str, dict[str, object]] = {}
    for label, path, expected_id in documents:
        try:
            document = parse_json_document(
                path.read_text(encoding="utf-8"),
                label=f"shared {label} preparation",
            )
        except (ContractLoadError, OSError, UnicodeError) as error:
            raise UnknownPass1ScreenError(
                f"shared {label} preparation is not unambiguous JSON"
            ) from error
        if (
            not isinstance(document, dict)
            or document.get("preparation_id") != expected_id
        ):
            raise UnknownPass1ScreenError(
                f"shared {label} preparation identity does not match its file"
            )
        parsed[label] = document
    if parsed["provider"].get("remote_sequence_submission") is not False:
        raise UnknownPass1ScreenError(
            "shared provider preparation must prohibit remote sequence submission"
        )
    if parsed["localisation"].get("execution_mode") != "local_offline":
        raise UnknownPass1ScreenError(
            "shared localisation preparation must be explicitly local_offline"
        )
    try:
        return UnknownPass1SharedPreparation.from_content(
            execution_identity_id=execution_identity_id,
            catalogue_preparation_id=request.catalogue_preparation_id,
            catalogue_preparation_sha256=sha256_file(catalogue, progress=False),
            provider_preparation_id=request.provider_preparation_id,
            provider_preparation_sha256=sha256_file(provider, progress=False),
            localisation_preparation_id=request.localisation_preparation_id,
            localisation_preparation_sha256=sha256_file(localisation, progress=False),
        )
    except ValidationError as error:
        raise UnknownPass1ScreenError(
            "shared preparations violate their path-free content contract"
        ) from error


def _review_binding(
    manifest: PhaseIIIReviewStageManifest,
    decisions: PhaseIIIReviewDecisionFile,
    stage_manifest_sha256: str,
) -> UnknownPass1ReviewBinding:
    decision = decisions.decisions[0]
    return UnknownPass1ReviewBinding.from_content(
        checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        crystal_id=decision.crystal_id,
        stage_id=manifest.stage_id,
        stage_manifest_sha256=stage_manifest_sha256,
        review_package_id=manifest.review_package_id,
        review_package_manifest_sha256=manifest.review_package_manifest_sha256,
        decision_file_id=manifest.decision_file_id,
        canonical_decision_sha256=manifest.canonical_decision_sha256,
        owned_parent_run_id=manifest.owned_parent_run_id,
        parent_profile=manifest.parent_profile,
        parent_phase=manifest.parent_phase,
    )


def _crystal_branch(
    decision: PhaseIIIReviewDecisionValue,
    hypotheses: tuple[UnknownPass1AHypothesis, ...],
) -> UnknownPass1CrystalBranch:
    if decision is PhaseIIIReviewDecisionValue.HOLD:
        return UnknownPass1CrystalBranch.HELD
    if any(
        item.disposition is UnknownPass1AHypothesisDisposition.SELECTED
        for item in hypotheses
    ):
        return UnknownPass1CrystalBranch.READY
    if hypotheses and all(
        item.disposition is UnknownPass1AHypothesisDisposition.UNSEARCHABLE_NO_MODEL
        for item in hypotheses
    ):
        return UnknownPass1CrystalBranch.EMPTY_NO_MODEL
    return UnknownPass1CrystalBranch.EMPTY_NO_HYPOTHESES


def build_unknown_pass1_screen_inventory(
    *,
    execution_identity_path: Path,
    review_stage_directory: Path,
    shared_preparation_input: UnknownPass1SharedPreparationInput,
    crystals: tuple[UnknownPass1CrystalInput, ...],
) -> UnknownPass1ScreenInventory:
    """Validate exact local bytes and build the three-crystal task inventory."""

    execution = _load_execution_identity(execution_identity_path)
    review_stages = _load_review_stages(review_stage_directory)
    shared = _shared_preparation(
        execution.execution_identity_id,
        shared_preparation_input,
    )
    review_bindings = tuple(
        _review_binding(stage, decisions, stage_sha256)
        for stage, decisions, stage_sha256 in review_stages
    )
    review_decisions = tuple(decisions for _, decisions, _ in review_stages)

    if len(crystals) != 3:
        raise UnknownPass1ScreenError("unknown pass 1 requires exactly three crystals")
    crystal_by_id = {item.crystal_id: item for item in crystals}
    if len(crystal_by_id) != 3:
        raise UnknownPass1ScreenError("unknown pass 1 crystal IDs must be unique")
    decision_by_crystal = {
        decisions.decisions[0].crystal_id: decisions.decisions[0]
        for decisions in review_decisions
    }
    binding_by_crystal = {binding.crystal_id: binding for binding in review_bindings}
    if len(decision_by_crystal) != 3 or set(decision_by_crystal) != set(crystal_by_id):
        raise UnknownPass1ScreenError(
            "crystallographic review must contain exactly one decision per crystal"
        )
    mtz_artifacts = {
        artifact.owner_id: artifact
        for artifact in execution.crystal_artifacts
        if artifact.role == "mtz"
    }
    if set(mtz_artifacts) != set(crystal_by_id):
        raise UnknownPass1ScreenError(
            "execution identity must contain exactly one MTZ for each crystal"
        )

    crystal_items: list[UnknownPass1CrystalItem] = []
    tasks: list[UnknownPass1AHypothesisTask] = []
    try:
        for crystal_id in sorted(crystal_by_id):
            source = crystal_by_id[crystal_id]
            decision = decision_by_crystal[crystal_id]
            review_binding = binding_by_crystal[crystal_id]
            mtz = _regular_file(source.mtz, label=f"{crystal_id} MTZ")
            artifact = mtz_artifacts[crystal_id]
            if (
                sha256_file(mtz, progress=False) != artifact.sha256
                or mtz.stat().st_size != artifact.size_bytes
            ):
                raise UnknownPass1ScreenError(
                    f"{crystal_id} MTZ bytes differ from the execution identity"
                )
            hypotheses = tuple(
                sorted(source.hypotheses, key=lambda item: item.candidate_rank)
            )
            model_by_id = {model.model_id: model for model in source.models}
            if len(model_by_id) != len(source.models):
                raise UnknownPass1ScreenError(
                    f"{crystal_id} contains duplicate local model identities"
                )
            expected_models: dict[str, str] = {}
            for hypothesis in hypotheses:
                if hypothesis.model_id is None or hypothesis.model_sha256 is None:
                    continue
                existing_sha256 = expected_models.get(hypothesis.model_id)
                if (
                    existing_sha256 is not None
                    and existing_sha256 != hypothesis.model_sha256
                ):
                    raise UnknownPass1ScreenError(
                        f"{crystal_id} reuses one model ID with conflicting checksums"
                    )
                expected_models[hypothesis.model_id] = hypothesis.model_sha256
            if set(model_by_id) != set(expected_models):
                raise UnknownPass1ScreenError(
                    f"{crystal_id} local model inventory is not path-closed"
                )
            for model_id, expected_sha256 in expected_models.items():
                local_model = _regular_file(
                    model_by_id[model_id].model,
                    label=f"{crystal_id} model {model_id}",
                )
                if sha256_file(local_model, progress=False) != expected_sha256:
                    raise UnknownPass1ScreenError(
                        f"{crystal_id} model bytes differ from hypothesis identity"
                    )
            selected_count = sum(
                item.disposition is UnknownPass1AHypothesisDisposition.SELECTED
                for item in hypotheses
            )
            deferred_count = sum(
                item.disposition is UnknownPass1AHypothesisDisposition.DEFERRED_CAP
                for item in hypotheses
            )
            no_model_count = sum(
                item.disposition
                is UnknownPass1AHypothesisDisposition.UNSEARCHABLE_NO_MODEL
                for item in hypotheses
            )
            item = UnknownPass1CrystalItem.from_content(
                crystal_id=crystal_id,
                mtz_artifact_id=artifact.artifact_id,
                mtz_sha256=artifact.sha256,
                execution_identity_id=execution.execution_identity_id,
                shared_preparation_id=shared.preparation_id,
                review_binding_id=review_binding.review_binding_id,
                review_item_id=decision.item_id,
                review_decision=decision.decision,
                branch=_crystal_branch(decision.decision, hypotheses),
                candidate_count=len(hypotheses),
                selected_hypothesis_count=selected_count,
                deferred_cap_count=deferred_count,
                unsearchable_no_model_count=no_model_count,
                hypotheses=hypotheses,
            )
            crystal_items.append(item)
            for hypothesis in hypotheses:
                if (
                    hypothesis.disposition
                    is not UnknownPass1AHypothesisDisposition.SELECTED
                ):
                    continue
                if (
                    hypothesis.allocation_rank is None
                    or hypothesis.model_id is None
                    or hypothesis.model_sha256 is None
                ):  # pragma: no cover - hypothesis schema guard
                    raise AssertionError("selected hypothesis lacks execution fields")
                tasks.append(
                    UnknownPass1AHypothesisTask.from_content(
                        crystal_id=crystal_id,
                        crystal_item_id=item.crystal_item_id,
                        hypothesis_id=hypothesis.hypothesis_id,
                        allocation_rank=hypothesis.allocation_rank,
                        model_id=hypothesis.model_id,
                        model_sha256=hypothesis.model_sha256,
                        mtz_sha256=item.mtz_sha256,
                        execution_identity_id=execution.execution_identity_id,
                        shared_preparation_id=shared.preparation_id,
                        review_binding_id=review_binding.review_binding_id,
                    )
                )
        ordered_items = tuple(crystal_items)
        ordered_tasks = tuple(
            sorted(tasks, key=lambda item: (item.crystal_id, item.allocation_rank))
        )
        return UnknownPass1ScreenInventory.from_content(
            execution_identity=execution,
            shared_preparation=shared,
            review_bindings=review_bindings,
            review_decisions=review_decisions,
            crystal_count=3,
            ready_count=sum(
                item.branch is UnknownPass1CrystalBranch.READY for item in ordered_items
            ),
            held_count=sum(
                item.branch is UnknownPass1CrystalBranch.HELD for item in ordered_items
            ),
            empty_no_model_count=sum(
                item.branch is UnknownPass1CrystalBranch.EMPTY_NO_MODEL
                for item in ordered_items
            ),
            empty_no_hypotheses_count=sum(
                item.branch is UnknownPass1CrystalBranch.EMPTY_NO_HYPOTHESES
                for item in ordered_items
            ),
            hypothesis_task_count=len(ordered_tasks),
            crystals=ordered_items,
            hypothesis_tasks=ordered_tasks,
        )
    except ValidationError as error:
        raise UnknownPass1ScreenError(
            "unknown-pass-1 screen inventory violates its complete-item contract"
        ) from error


def load_unknown_pass1_screen_inventory(path: Path) -> UnknownPass1ScreenInventory:
    """Load and revalidate one strict content-addressed screen inventory."""

    resolved = _regular_file(path, label="unknown-pass-1 screen inventory")
    try:
        return UnknownPass1ScreenInventory.model_validate_json(resolved.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise UnknownPass1ScreenError(
            "unknown-pass-1 screen inventory violates its typed contract"
        ) from error


def write_unknown_pass1_screen_inventory(
    inventory: UnknownPass1ScreenInventory,
    path: Path,
) -> Path:
    """Write one deterministic JSON inventory for the Nextflow fan-out."""

    atomic_write_json(path, inventory.model_dump(mode="json", exclude_none=False))
    return path


__all__ = [
    "UnknownPass1CrystalInput",
    "UnknownPass1ModelInput",
    "UnknownPass1ScreenError",
    "UnknownPass1SharedPreparationInput",
    "build_unknown_pass1_screen_inventory",
    "load_unknown_pass1_screen_inventory",
    "write_unknown_pass1_screen_inventory",
]
