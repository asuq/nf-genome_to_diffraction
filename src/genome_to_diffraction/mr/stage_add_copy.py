"""Prepare checksum-bound inputs for comparative additional-copy screening.

The fixed-site interface authenticates a retained successful P2-diverse run and
resolves each original processed model.  The normal-workflow interface consumes
the live review package and uses each approved rigid-body-derived solution
coordinate as its next search model.  Both revalidate the human decision file,
copy only approved review assets, and write a bounded seed table.  Neither
performs molecular replacement or makes a scientific selection.
"""

import csv
import io
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.review.mr_seed import (
    MrSeedApprovalOutput,
    MrSeedApprovalRequest,
    MrSeedReviewError,
    validate_mr_seed_approvals,
    validate_mr_seed_review_evidence,
)
from genome_to_diffraction.review.owned_run import (
    PhaseIIIOwnedRunError,
    resolve_phase3_owned_review_package,
)
from genome_to_diffraction.review.phase3_package import (
    PhaseIIIReviewPackageError,
    validate_phase3_review_package,
)
from genome_to_diffraction.review.phase3_stage import PhaseIIIReviewStageManifest
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.schemas.results import MrHypothesis
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
    PhaseIIIReviewPackageManifest,
)
from genome_to_diffraction.status import ExecutionStatus
from genome_to_diffraction.time import utc_now_iso

_LOGGER = logging.getLogger("genome_to_diffraction.mr.stage_add_copy")


@dataclass(frozen=True, slots=True)
class AddCopyStageRequest:
    """Fixed retained-run inputs for one M4 comparative screen."""

    parent_run: Path
    decisions: Path
    expected_review_manifest_sha256: str
    mtz: Path
    phenix_manifest: Path
    output_directory: Path
    expected_seed_count: int = 11
    progress: bool = True
    use_solution_coordinates_as_models: bool = False
    source_site_id: str | None = None


@dataclass(frozen=True, slots=True)
class AddCopyStageOutput:
    """Prepared seed table and its complete provenance manifest."""

    seeds_tsv: Path
    validation_json: Path
    stage_manifest: Path
    seed_count: int


@dataclass(frozen=True, slots=True)
class LiveAddCopyStageRequest:
    """Normal-workflow MR checkpoint and its immutable scientific inputs."""

    review_package: Path
    decisions: Path
    hypotheses_jsonl: Path
    output_directory: Path
    progress: bool = True
    phase3_review_stage: Path | None = None
    phase3_review_package_manifest: Path | None = None
    phase3_owned_run_registry: Path | None = None
    phase3_execution_identity: Path | None = None
    phase3_owned_parent_run_id: str | None = None


@dataclass(frozen=True, slots=True)
class LiveAddCopyStageOutput:
    """Approved-seed bundle for normal sequential-copy execution."""

    approved_seeds_tsv: Path
    additional_copy_seeds_tsv: Path
    validation_json: Path
    stage_manifest: Path
    approved_seed_count: int
    additional_copy_seed_count: int


@dataclass(frozen=True, slots=True)
class _PhaseIIISeedApproval:
    stage: PhaseIIIReviewStageManifest
    decisions: PhaseIIIReviewDecisionFile
    package: PhaseIIIReviewPackageManifest
    stage_manifest_path: Path
    canonical_decisions_path: Path
    package_manifest_path: Path
    owned_run_registry_id: str | None = None


def _load_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = load_json_document(path)
    except ContractLoadError as error:
        raise ValueError(f"cannot load {label}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _regular_file(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    return resolved


def _copy_file(source: Path, destination: Path, label: str) -> Path:
    resolved = _regular_file(source, label)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(resolved, destination)
    return destination


def _owned_review_asset(root: Path, relative: object, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label} path is absent")
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"{label} path is unsafe")
    candidate = root / relative_path
    resolved = _regular_file(candidate, label)
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError(f"{label} escapes the review package")
    return resolved


def _load_hypotheses(path: Path) -> dict[str, MrHypothesis]:
    hypotheses: dict[str, MrHypothesis] = {}
    with _regular_file(path, "MR hypotheses").open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                hypothesis = MrHypothesis.model_validate_json(line)
            except ValidationError as error:
                raise ValueError(
                    f"invalid MR hypothesis at line {line_number}: {path}"
                ) from error
            if hypothesis.hypothesis_id in hypotheses:
                raise ValueError(f"duplicate MR hypothesis: {hypothesis.hypothesis_id}")
            hypotheses[hypothesis.hypothesis_id] = hypothesis
    if not hypotheses:
        raise ValueError(f"MR hypotheses are empty: {path}")
    return hypotheses


def _review_item_inventory(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    raw_items = manifest.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("MR review item inventory is absent")
    items: dict[str, dict[str, object]] = {}
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise ValueError(
                f"MR review item inventory contains a non-object at row {index}"
            )
        item = cast(dict[str, object], raw_item)
        solution_id = item.get("solution_id")
        if not isinstance(solution_id, str) or not solution_id:
            raise ValueError(
                f"MR review item inventory has an invalid solution ID at row {index}"
            )
        if solution_id in items:
            raise ValueError(
                "MR review solution inventory contains a duplicate solution ID: "
                f"{solution_id}"
            )
        items[solution_id] = item
    return items


def _seed_table(rows: list[tuple[str, str, str, int, str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(
        (
            "seed_solution_id",
            "search_model",
            "search_model_sha256",
            "expected_copy_count",
            "requires_additional_copy",
        )
    )
    writer.writerows(rows)
    return buffer.getvalue()


def _load_phase3_seed_approval(
    request: LiveAddCopyStageRequest,
    *,
    review_manifest: Path,
    hypotheses: dict[str, MrHypothesis],
) -> _PhaseIIISeedApproval | None:
    if request.phase3_review_stage is None:
        if request.phase3_review_package_manifest is not None:
            raise ValueError("Phase III review package requires its canonical stage")
        return None
    if request.phase3_review_package_manifest is None:
        raise ValueError("Phase III A-seed stage requires its exact review package")
    stage_root = request.phase3_review_stage
    if stage_root.is_symlink() or not stage_root.resolve(strict=True).is_dir():
        raise ValueError("Phase III A-seed stage must be a regular directory")
    stage_root = stage_root.resolve(strict=True)
    expected_files = {
        "phase3_review_decision.json",
        "phase3_review_stage_manifest.json",
    }
    if {path.name for path in stage_root.iterdir()} != expected_files:
        raise ValueError("Phase III A-seed stage differs from its two-file allow-list")
    stage_path = _regular_file(
        stage_root / "phase3_review_stage_manifest.json",
        "Phase III A-seed stage manifest",
    )
    decision_path = _regular_file(
        stage_root / "phase3_review_decision.json",
        "Phase III canonical A-seed decisions",
    )
    supplied_decisions = _regular_file(request.decisions, "Phase III A-seed decisions")
    if supplied_decisions != decision_path:
        raise ValueError("Phase III A-seed decisions must be the canonical staged file")
    package_path = _regular_file(
        request.phase3_review_package_manifest,
        "Phase III A-seed review-package manifest",
    )
    try:
        stage = PhaseIIIReviewStageManifest.model_validate_json(stage_path.read_bytes())
        decisions = PhaseIIIReviewDecisionFile.model_validate_json(
            decision_path.read_bytes()
        )
        package = validate_phase3_review_package(package_path.parent)
    except (OSError, ValidationError, ValueError, PhaseIIIReviewPackageError) as error:
        raise ValueError(
            "Phase III A-seed evidence violates its typed contracts"
        ) from error
    if (
        stage.checkpoint is not PhaseIIIReviewCheckpoint.A_SEED
        or decisions.checkpoint is not PhaseIIIReviewCheckpoint.A_SEED
        or package.checkpoint is not PhaseIIIReviewCheckpoint.A_SEED
        or stage.parent_profile != "unknown-screen"
        or stage.owned_parent_run_id != package.owned_parent_run_id
        or stage.parent_profile != package.parent_profile
        or stage.parent_phase != package.parent_phase
        or stage.review_package_id != package.review_package_id
        or stage.review_package_created_at != package.created_at
        or stage.review_package_manifest_sha256 != sha256_file(package_path)
        or stage.decision_file_id != decisions.decision_file_id
        or stage.decision_count != len(decisions.decisions)
        or stage.canonical_decision_sha256 != sha256_file(decision_path)
        or decisions.owned_parent_run_id != package.owned_parent_run_id
        or decisions.review_package_id != package.review_package_id
        or decisions.review_package_manifest_sha256 != sha256_file(package_path)
    ):
        raise ValueError("Phase III A-seed stage differs from its owned review package")
    legacy_evidence = tuple(
        artifact
        for artifact in package.evidence_inventory
        if artifact.role == "mr_seed_review_manifest"
    )
    if len(legacy_evidence) != 1 or legacy_evidence[0].sha256 != sha256_file(
        review_manifest
    ):
        raise ValueError("Phase III A-seed package does not bind the exact MR review")
    legacy = _load_object(review_manifest, "MR review manifest")
    items = _review_item_inventory(legacy)
    permitted = {target.item_id for target in package.permitted_targets}
    if permitted != set(items):
        raise ValueError("Phase III A-seed package omits or adds MR review targets")
    for item in items.values():
        hypothesis_id = item.get("hypothesis_id")
        if (
            not isinstance(hypothesis_id, str)
            or hypothesis_id not in hypotheses
            or hypotheses[hypothesis_id].crystal_id != package.crystal_id
        ):
            raise ValueError("Phase III A-seed package mixes crystal-bound hypotheses")
    if any(
        decision.crystal_id != package.crystal_id
        or decision.item_id not in permitted
        or decision.reviewed_at < package.created_at
        for decision in decisions.decisions
    ):
        raise ValueError(
            "Phase III A-seed decisions are stale or target another crystal"
        )
    ownership = (
        request.phase3_owned_run_registry,
        request.phase3_execution_identity,
        request.phase3_owned_parent_run_id,
    )
    registry_id: str | None = None
    if any(value is not None for value in ownership):
        registry, identity_path, parent_run = ownership
        if registry is None or identity_path is None or parent_run is None:
            raise ValueError(
                "Phase III owned A execution requires complete run identity"
            )
        try:
            identity = PhaseIIIExecutionIdentity.model_validate_json(
                _regular_file(
                    identity_path, "Phase III execution identity"
                ).read_bytes()
            )
            owned = resolve_phase3_owned_review_package(
                registry,
                run_id=parent_run,
                crystal_id=package.crystal_id,
                checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            )
            validate_mr_seed_review_evidence(
                package_manifest=review_manifest,
                hypotheses_jsonl=request.hypotheses_jsonl,
                crystal_id=package.crystal_id,
                progress=False,
            )
        except (
            OSError,
            ValidationError,
            ValueError,
            PhaseIIIOwnedRunError,
            MrSeedReviewError,
        ) as error:
            raise ValueError(
                "Phase III A-seed evidence is not owned by the completed "
                f"screen: {error}"
            ) from error
        if (
            owned.parent.profile != "unknown-screen"
            or owned.parent.phase != "phase3-pass1"
            or owned.execution_identity_id != identity.execution_identity_id
            or package.execution_identity_id != identity.execution_identity_id
            or owned.review_package_id != package.review_package_id
            or owned.review_package_manifest_sha256 != sha256_file(package_path)
        ):
            raise ValueError("Phase III A-seed ownership or execution identity differs")
        registry_id = owned.owned_run_registry_id
    return _PhaseIIISeedApproval(
        stage=stage,
        decisions=decisions,
        package=package,
        stage_manifest_path=stage_path,
        canonical_decisions_path=decision_path,
        package_manifest_path=package_path,
        owned_run_registry_id=registry_id,
    )


def _phase3_legacy_decisions(approval: _PhaseIIISeedApproval) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
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
    for decision in approval.decisions.decisions:
        writer.writerow(
            (
                "mr_seed",
                decision.item_id,
                decision.decision.value,
                decision.reviewer,
                decision.reviewed_at.isoformat(),
                decision.comment or decision.reason,
                "",
            )
        )
    return buffer.getvalue()


def _phase3_approval_provenance(approval: _PhaseIIISeedApproval) -> dict[str, object]:
    provenance: dict[str, object] = {
        "schema_version": "2.0",
        "checkpoint": approval.stage.checkpoint.value,
        "owned_parent_run_id": approval.stage.owned_parent_run_id,
        "parent_profile": approval.stage.parent_profile,
        "parent_phase": approval.stage.parent_phase,
        "execution_identity_id": approval.package.execution_identity_id,
        "crystal_id": approval.package.crystal_id,
        "review_package_id": approval.package.review_package_id,
        "review_package_manifest_sha256": approval.stage.review_package_manifest_sha256,
        "review_stage_id": approval.stage.stage_id,
        "review_stage_manifest_sha256": sha256_file(approval.stage_manifest_path),
        "decision_file_id": approval.decisions.decision_file_id,
        "canonical_decision_sha256": approval.stage.canonical_decision_sha256,
        "source_decisions_sha256": approval.stage.source_decisions_sha256,
        "decision_count": len(approval.decisions.decisions),
        "approved_solution_ids": [
            decision.item_id
            for decision in approval.decisions.decisions
            if decision.decision is PhaseIIIReviewDecisionValue.APPROVE
        ],
        "rejected_solution_ids": [
            decision.item_id
            for decision in approval.decisions.decisions
            if decision.decision is PhaseIIIReviewDecisionValue.REJECT
        ],
        "deferred_solution_ids": [
            decision.item_id
            for decision in approval.decisions.decisions
            if decision.decision is PhaseIIIReviewDecisionValue.DEFER
        ],
    }
    if approval.owned_run_registry_id is not None:
        provenance["owned_run_registry_id"] = approval.owned_run_registry_id
    return provenance


def prepare_live_add_copy_stage(
    request: LiveAddCopyStageRequest,
) -> LiveAddCopyStageOutput:
    """Validate a live MR checkpoint and stage every approved inspectable seed.

    The first-copy solution coordinate is a rigid-body transformation of the
    original search model and is therefore suitable as the search model for the
    next same-component placement.  Both checksums are retained explicitly.
    Seeds whose Matthews hypothesis already expects one copy remain in the
    approved table but are not sent to the additional-copy adapter.
    """

    review = request.review_package
    if review.is_symlink() or not review.resolve(strict=True).is_dir():
        raise ValueError("MR review package must be a regular non-symlink directory")
    review = review.resolve(strict=True)
    review_manifest = _regular_file(
        review / "mr_seed_review_manifest.json", "MR review manifest"
    )
    hypotheses = _load_hypotheses(request.hypotheses_jsonl)
    phase3_approval = _load_phase3_seed_approval(
        request,
        review_manifest=review_manifest,
        hypotheses=hypotheses,
    )
    output_path = request.output_directory
    if output_path.is_symlink() or output_path.exists():
        raise ValueError(f"live M4 stage output already exists: {output_path}")
    output = output_path.absolute()
    output.mkdir(parents=True)

    decisions = output / "approved_mr_seeds.tsv"
    if phase3_approval is None:
        decisions = _copy_file(request.decisions, decisions, "MR seed decisions")
    else:
        atomic_write_text(decisions, _phase3_legacy_decisions(phase3_approval))
        _copy_file(
            phase3_approval.canonical_decisions_path,
            output / "phase3_review_decision.json",
            "canonical Phase III A-seed decisions",
        )
        _copy_file(
            phase3_approval.stage_manifest_path,
            output / "phase3_review_stage_manifest.json",
            "Phase III A-seed stage manifest",
        )
        _copy_file(
            phase3_approval.package_manifest_path,
            output / "phase3_review_package_manifest.json",
            "Phase III A-seed review-package manifest",
        )
    validation_json = output / "validated_mr_seed_decisions.json"
    phase3_provenance = (
        _phase3_approval_provenance(phase3_approval)
        if phase3_approval is not None
        else None
    )
    if phase3_provenance is not None and not phase3_provenance["approved_solution_ids"]:
        review_id = content_id(
            "rev_",
            {
                "adapter_version": "phase3-a-seed-validation-v1",
                "review_package_id": phase3_provenance["review_package_id"],
                "review_stage_id": phase3_provenance["review_stage_id"],
                "decision_file_id": phase3_provenance["decision_file_id"],
                "approved_solution_ids": [],
            },
        )
        legacy_manifest = _load_object(review_manifest, "MR review manifest")
        atomic_write_json(
            validation_json,
            {
                "schema_version": "1.0",
                "review_id": review_id,
                "checkpoint": "mr_seed",
                "package_id": legacy_manifest.get("package_id"),
                "package_manifest_sha256": sha256_file(review_manifest),
                "decisions_sha256": sha256_file(decisions),
                "validated_at": utc_now_iso(),
                "decision_count": phase3_provenance["decision_count"],
                "approved_solution_ids": [],
                "phase3_approval_provenance": phase3_provenance,
                "execution_status": ExecutionStatus.COMPLETED_SUCCESS.value,
            },
        )
        approval = MrSeedApprovalOutput(review_id, (), validation_json)
    else:
        approval = validate_mr_seed_approvals(
            MrSeedApprovalRequest(
                package_manifest=review_manifest,
                decisions=decisions,
                output_json=validation_json,
                progress=request.progress,
            )
        )
        if phase3_provenance is not None:
            validation = _load_object(validation_json, "validated MR decisions")
            validation["phase3_approval_provenance"] = phase3_provenance
            atomic_write_json(validation_json, validation)
    manifest = _load_object(review_manifest, "MR review manifest")
    items = _review_item_inventory(manifest)

    models = output / "models"
    models.mkdir()
    approved_rows: list[tuple[str, str, str, int, str]] = []
    additional_rows: list[tuple[str, str, str, int, str]] = []
    model_sources: dict[str, dict[str, object]] = {}
    for solution_id in approval.approved_solution_ids:
        item = items.get(solution_id)
        if item is None:
            raise ValueError(
                f"approved solution is absent from manifest: {solution_id}"
            )
        hypothesis_id = item.get("hypothesis_id")
        if not isinstance(hypothesis_id, str) or hypothesis_id not in hypotheses:
            raise ValueError(
                f"approved solution has no current hypothesis: {solution_id}"
            )
        hypothesis = hypotheses[hypothesis_id]
        copied = item.get("copied_assets")
        copied_sha = item.get("copied_asset_sha256")
        if not isinstance(copied, dict) or not isinstance(copied_sha, dict):
            raise ValueError(
                f"approved solution has no copied asset inventory: {solution_id}"
            )
        coordinate_relative = copied.get("solution_coordinate")
        coordinate = _owned_review_asset(
            review, coordinate_relative, "first-copy solution coordinate"
        )
        coordinate_sha = sha256_file(coordinate)
        if coordinate_sha != copied_sha.get("solution_coordinate"):
            raise ValueError(f"first-copy solution checksum differs: {solution_id}")
        command_relative = copied.get("command")
        command = _load_object(
            _owned_review_asset(review, command_relative, "first-copy command"),
            "first-copy command",
        )
        original_model_sha = command.get("model_sha256")
        identity_percent = command.get("model_identity_percent")
        if (
            not isinstance(original_model_sha, str)
            or re.fullmatch(r"[0-9a-f]{64}", original_model_sha) is None
            or isinstance(identity_percent, bool)
            or not isinstance(identity_percent, int | float)
            or not 0 < float(identity_percent) <= 100
        ):
            raise ValueError(
                f"first-copy command lacks model provenance: {solution_id}"
            )
        model_relative = Path("models") / f"{coordinate_sha}.pdb"
        model = output / model_relative
        if not model.exists():
            _copy_file(coordinate, model, "first-copy solution coordinate")
        if sha256_file(model) != coordinate_sha:
            raise ValueError(f"staged search model checksum failed: {solution_id}")
        requires_additional = hypothesis.copy_count_expected > 1
        row = (
            solution_id,
            str(model.resolve(strict=True)),
            coordinate_sha,
            hypothesis.copy_count_expected,
            str(requires_additional).lower(),
        )
        approved_rows.append(row)
        if requires_additional:
            additional_rows.append(row)
        model_sources[solution_id] = {
            "hypothesis_id": hypothesis.hypothesis_id,
            "sequence_group_id": hypothesis.sequence_group_id,
            "expected_copy_count": hypothesis.copy_count_expected,
            "requires_additional_copy": requires_additional,
            "derivation": "first_copy_solution_coordinate_rigid_body_derived",
            "source_solution_coordinate": str(coordinate_relative),
            "original_first_copy_model_sha256": original_model_sha,
            "staged_search_model": model_relative.as_posix(),
            "staged_search_model_sha256": coordinate_sha,
        }

    approved_seeds = output / "approved_seeds.tsv"
    additional_seeds = output / "additional_copy_seeds.tsv"
    atomic_write_text(approved_seeds, _seed_table(approved_rows))
    atomic_write_text(additional_seeds, _seed_table(additional_rows))
    review_manifest_sha = sha256_file(review_manifest)
    decisions_sha = sha256_file(decisions)
    hypotheses_sha = sha256_file(request.hypotheses_jsonl)
    stage_identity = {
        "review_id": approval.review_id,
        "review_package_id": manifest.get("package_id"),
        "review_manifest_sha256": review_manifest_sha,
        "decisions_sha256": decisions_sha,
        "hypotheses_sha256": hypotheses_sha,
        "approved_solution_ids": list(approval.approved_solution_ids),
        "model_sources": model_sources,
    }
    if phase3_provenance is not None:
        stage_identity["phase3_approval_provenance"] = phase3_provenance
    stage_manifest = output / "live_m4_stage_manifest.json"
    atomic_write_json(
        stage_manifest,
        {
            "schema_version": "1.0",
            "stage_id": content_id("m4stage_", stage_identity),
            "stage_kind": "normal_workflow_post_mr_seed",
            **stage_identity,
            "approved_seed_count": len(approved_rows),
            "additional_copy_seed_count": len(additional_rows),
            "already_at_expected_copy_count": (
                len(approved_rows) - len(additional_rows)
            ),
            "all_approved_seeds_retained": True,
            "numeric_score_filter_applied": False,
            "approved_seeds_sha256": sha256_file(approved_seeds),
            "additional_copy_seeds_sha256": sha256_file(additional_seeds),
            "validation_sha256": sha256_file(validation_json),
            "execution_status": ExecutionStatus.COMPLETED_SUCCESS.value,
        },
    )
    _LOGGER.info(
        "prepared normal-workflow M4 inputs",
        extra={
            "review_id": approval.review_id,
            "approved_seed_count": len(approved_rows),
            "additional_copy_seed_count": len(additional_rows),
        },
    )
    return LiveAddCopyStageOutput(
        approved_seeds_tsv=approved_seeds,
        additional_copy_seeds_tsv=additional_seeds,
        validation_json=validation_json,
        stage_manifest=stage_manifest,
        approved_seed_count=len(approved_rows),
        additional_copy_seed_count=len(additional_rows),
    )


def _copy_review_package(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.resolve(strict=True).is_dir():
        raise ValueError("retained review package is absent or unsafe")
    for candidate in source.rglob("*"):
        if candidate.is_symlink():
            raise ValueError("retained review package contains a symlink")
    manifest_path = source / "mr_seed_review_manifest.json"
    manifest = _load_object(manifest_path, "review manifest")
    raw_items = manifest.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("review manifest has no item inventory")
    required: set[Path] = {
        Path("mr_seed_review_manifest.json"),
        Path("approved_mr_seeds.tsv"),
        Path("mr_seed_candidates.tsv"),
        Path("mr_seed_candidates.html"),
        Path("mr_seed_approval_candidates.tsv"),
    }
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        copied = item.get("copied_assets")
        if not isinstance(copied, dict) or "solution_coordinate" not in copied:
            continue
        for relative in copied.values():
            if not isinstance(relative, str):
                raise ValueError("review manifest contains a non-string asset path")
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError("review manifest contains an unsafe asset path")
            required.add(candidate)
    destination.mkdir()
    for relative in sorted(required):
        source_file = source / relative
        if not source_file.exists():
            if relative.name in {
                "approved_mr_seeds.tsv",
                "mr_seed_candidates.tsv",
                "mr_seed_candidates.html",
                "mr_seed_approval_candidates.tsv",
            }:
                continue
            raise ValueError(f"retained review asset is absent: {relative}")
        _copy_file(source_file, destination / relative, "retained review asset")


def _find_model(parent: Path, expected_sha256: str) -> Path:
    roots = (
        parent
        / "artifacts/p2-diverse/first-copy/diverse_first_copy_funnel/model_registry",
        parent / "artifacts/p2-diverse/experimental-model-preparation",
        parent / "artifacts/p1/model-preparation",
    )
    matches: list[Path] = []
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        for candidate in sorted(root.rglob("*.pdb")):
            if (
                candidate.is_file()
                and not candidate.is_symlink()
                and sha256_file(candidate) == expected_sha256
            ):
                matches.append(candidate.resolve(strict=True))
    if not matches:
        raise ValueError(
            "original processed model "
            f"{expected_sha256} is absent from retained evidence"
        )
    return matches[0]


def _model_source_relative_path(
    source_model: Path,
    *,
    parent: Path,
    output: Path,
    cross_site_import: bool,
) -> str:
    """Return provenance relative to the tree that owns the staged source."""

    anchor = (output if cross_site_import else parent).resolve(strict=True)
    try:
        return str(source_model.relative_to(anchor))
    except ValueError as error:
        message = "staged model source is outside its provenance root"
        raise ValueError(message) from error


def prepare_add_copy_stage(request: AddCopyStageRequest) -> AddCopyStageOutput:
    """Create a self-contained M4 input bundle from immutable retained evidence."""

    parent = request.parent_run.resolve(strict=True)
    output = request.output_directory
    if output.exists():
        raise ValueError(f"M4 stage output already exists: {output}")
    output.mkdir(parents=True)

    source_review = (
        parent / "review_package"
        if request.use_solution_coordinates_as_models
        else parent / "artifacts/qualification/p2-diverse-review"
    )
    review = output / "review_package"
    _copy_review_package(source_review, review)
    review_manifest = review / "mr_seed_review_manifest.json"
    actual_manifest_sha = sha256_file(review_manifest)
    if actual_manifest_sha != request.expected_review_manifest_sha256:
        raise ValueError("retained review manifest differs from the local handoff")

    decisions = _copy_file(request.decisions, output / "decisions.tsv", "decisions")
    validation_json = output / "validated_mr_seed_decisions.json"
    approval = validate_mr_seed_approvals(
        MrSeedApprovalRequest(
            package_manifest=review_manifest,
            decisions=decisions,
            output_json=validation_json,
            progress=request.progress,
        )
    )
    if len(approval.approved_solution_ids) != request.expected_seed_count:
        raise ValueError(
            "comparative M4 stage requires exactly "
            f"{request.expected_seed_count} approved seeds; observed "
            f"{len(approval.approved_solution_ids)}"
        )

    manifest = _load_object(review_manifest, "review manifest")
    raw_items = manifest.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("review manifest has no item inventory")
    items = {
        str(item["solution_id"]): cast(dict[str, object], item)
        for item in raw_items
        if isinstance(item, dict) and isinstance(item.get("solution_id"), str)
    }

    model_directory = output / "models"
    model_directory.mkdir()
    rows: list[tuple[str, str, str]] = []
    model_sources: dict[str, dict[str, str]] = {}
    for solution_id in approval.approved_solution_ids:
        item = items.get(solution_id)
        if item is None:
            raise ValueError(
                f"approved solution is absent from manifest: {solution_id}"
            )
        copied = item.get("copied_assets")
        if not isinstance(copied, dict):
            raise ValueError(f"approved solution has no copied assets: {solution_id}")
        command_relative = copied.get("command")
        if not isinstance(command_relative, str):
            raise ValueError(f"approved solution has no command: {solution_id}")
        command = _load_object(review / command_relative, "first-copy command")
        model_sha = command.get("model_sha256")
        if not isinstance(model_sha, str) or len(model_sha) != 64:
            raise ValueError(f"first-copy command has no model checksum: {solution_id}")
        if request.use_solution_coordinates_as_models:
            coordinate_relative = copied.get("solution_coordinate")
            if not isinstance(coordinate_relative, str):
                raise ValueError(f"approved solution has no coordinate: {solution_id}")
            source_model = _regular_file(
                review / coordinate_relative, "first-copy solution coordinate"
            )
        else:
            source_model = _find_model(parent, model_sha)
        staged_sha = sha256_file(source_model)
        staged_model = model_directory / f"{staged_sha}.pdb"
        if not staged_model.exists():
            shutil.copyfile(source_model, staged_model)
        if sha256_file(staged_model) != staged_sha:
            raise ValueError(f"staged model checksum failed: {solution_id}")
        rows.append((solution_id, str(staged_model.resolve()), staged_sha))
        model_sources[solution_id] = {
            "derivation": (
                "first_copy_solution_coordinate_rigid_body_derived"
                if request.use_solution_coordinates_as_models
                else "original_processed_model"
            ),
            "original_first_copy_model_sha256": model_sha,
            "staged_search_model_sha256": staged_sha,
            "source": _model_source_relative_path(
                source_model,
                parent=parent,
                output=output,
                cross_site_import=request.use_solution_coordinates_as_models,
            ),
        }

    seeds_tsv = output / "seeds.tsv"
    with seeds_tsv.open("w", encoding="ascii", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("seed_solution_id", "search_model", "search_model_sha256"))
        writer.writerows(rows)

    if request.use_solution_coordinates_as_models:
        source_files = {
            "hypotheses": parent / "inputs/hypotheses.jsonl",
            "sequence_groups": parent / "inputs/sequence_groups.jsonl",
            "preflight": parent / "inputs/preflight.jsonl",
            "mtz": request.mtz,
            "phenix_manifest": request.phenix_manifest,
        }
    else:
        source_files = {
            "hypotheses": parent
            / "artifacts/p2-diverse/first-copy/diverse_first_copy_funnel"
            / "mr_hypotheses.jsonl",
            "sequence_groups": parent / "artifacts/p1/catalogue/sequence_groups.jsonl",
            "preflight": parent / "artifacts/p0/preflight/mtz_preflight.jsonl",
            "mtz": request.mtz,
            "phenix_manifest": request.phenix_manifest,
        }
    copied_files: dict[str, dict[str, str]] = {}
    for name, source in source_files.items():
        suffix = source.suffix or ".json"
        destination = _copy_file(source, output / "inputs" / f"{name}{suffix}", name)
        copied_files[name] = {
            "path": str(destination.resolve()),
            "sha256": sha256_file(destination),
        }

    stage_manifest = output / "m4_copy_stage_manifest.json"
    atomic_write_json(
        stage_manifest,
        {
            "schema_version": "1.0",
            "profile": "m4-copy",
            "parent_run_id": parent.name,
            "review_id": approval.review_id,
            "review_package_id": manifest.get("package_id"),
            "review_manifest_sha256": actual_manifest_sha,
            "decisions_sha256": sha256_file(decisions),
            "seed_count": len(rows),
            "seed_solution_ids": [row[0] for row in rows],
            "seeds_tsv_sha256": sha256_file(seeds_tsv),
            "model_sources": model_sources,
            "source_site_id": request.source_site_id,
            "cross_site_import": request.use_solution_coordinates_as_models,
            "inputs": copied_files,
        },
    )
    _LOGGER.info(
        "prepared comparative M4 inputs",
        extra={"parent_run_id": parent.name, "seed_count": len(rows)},
    )
    return AddCopyStageOutput(
        seeds_tsv=seeds_tsv,
        validation_json=validation_json,
        stage_manifest=stage_manifest,
        seed_count=len(rows),
    )
