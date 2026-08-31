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
from genome_to_diffraction.schemas.results import MrHypothesis, NormalisedMrResult
from genome_to_diffraction.schemas.v2 import (
    MrResourcePlan,
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
class PhaseIIISeedStageRequest:
    """Canonical owned Phase III A-review inputs for one crystal."""

    review_stage: Path
    review_package_manifest: Path
    hypotheses_jsonl: Path
    owned_run_registry: Path
    execution_identity: Path
    owned_parent_run_id: str
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True, slots=True)
class PhaseIIISeedStageOutput:
    """Schema-v2 A-seed stage with no translated legacy approval records."""

    approved_seeds_tsv: Path
    additional_copy_seeds_tsv: Path
    stage_manifest: Path
    review_package: Path
    review_stage: Path
    approved_seed_count: int
    additional_copy_seed_count: int


@dataclass(frozen=True, slots=True)
class PhaseIIISeedStageEvidence:
    """Revalidated canonical authority and scientific evidence for one stage."""

    stage_id: str
    review_id: str
    approved_solution_ids: tuple[str, ...]
    root: Path
    review_root: Path
    review_manifest: Path
    review_document: dict[str, object]
    model_sources: dict[str, dict[str, object]]


@dataclass(frozen=True, slots=True)
class _PhaseIIISeedApproval:
    stage: PhaseIIIReviewStageManifest
    decisions: PhaseIIIReviewDecisionFile
    package: PhaseIIIReviewPackageManifest
    stage_manifest_path: Path
    canonical_decisions_path: Path
    package_manifest_path: Path
    owned_run_registry_id: str


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


def _load_seed_rows(path: Path, label: str) -> dict[str, dict[str, str]]:
    required = (
        "seed_solution_id",
        "search_model",
        "search_model_sha256",
        "expected_copy_count",
        "requires_additional_copy",
    )
    try:
        with _regular_file(path, label).open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if tuple(reader.fieldnames or ()) != required:
                raise ValueError(f"{label} has an invalid header")
            rows = tuple(dict(row) for row in reader)
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise ValueError(f"cannot read {label}: {error}") from error
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        seed_id = row.get("seed_solution_id", "")
        if not seed_id or seed_id in indexed:
            raise ValueError(f"{label} has an invalid or duplicate seed ID")
        indexed[seed_id] = row
    return indexed


def _load_phase3_seed_approval(
    request: PhaseIIISeedStageRequest,
    *,
    review_manifest: Path,
    hypotheses: dict[str, MrHypothesis],
) -> _PhaseIIISeedApproval:
    stage_root = request.review_stage
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
    package_path = _regular_file(
        request.review_package_manifest,
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
    try:
        identity = PhaseIIIExecutionIdentity.model_validate_json(
            _regular_file(
                request.execution_identity, "Phase III execution identity"
            ).read_bytes()
        )
        owned = resolve_phase3_owned_review_package(
            request.owned_run_registry,
            run_id=request.owned_parent_run_id,
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
            f"Phase III A-seed evidence is not owned by the completed screen: {error}"
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
    return _PhaseIIISeedApproval(
        stage=stage,
        decisions=decisions,
        package=package,
        stage_manifest_path=stage_path,
        canonical_decisions_path=decision_path,
        package_manifest_path=package_path,
        owned_run_registry_id=owned.owned_run_registry_id,
    )


def _phase3_approval_provenance(approval: _PhaseIIISeedApproval) -> dict[str, object]:
    return {
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
        "owned_run_registry_id": approval.owned_run_registry_id,
    }


def _copy_owned_directory(source: Path, destination: Path, label: str) -> Path:
    if source.is_symlink() or not source.resolve(strict=True).is_dir():
        raise ValueError(f"{label} must be a regular non-symlink directory")
    root = source.resolve(strict=True)
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError(f"{label} must not contain symlinks")
    shutil.copytree(root, destination)
    return destination


def _stage_approved_seed_models(
    *,
    approved_solution_ids: tuple[str, ...],
    items: dict[str, dict[str, object]],
    hypotheses: dict[str, MrHypothesis],
    review_root: Path,
    output: Path,
    derive_placed_copy_count: bool = False,
) -> tuple[
    list[tuple[str, str, str, int, str]],
    list[tuple[str, str, str, int, str]],
    dict[str, dict[str, object]],
]:
    """Copy exact approved coordinates and retain their complete provenance."""

    models = output / "models"
    models.mkdir()
    approved_rows: list[tuple[str, str, str, int, str]] = []
    additional_rows: list[tuple[str, str, str, int, str]] = []
    model_sources: dict[str, dict[str, object]] = {}
    for solution_id in approved_solution_ids:
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
            review_root, coordinate_relative, "first-copy solution coordinate"
        )
        coordinate_sha = sha256_file(coordinate)
        if coordinate_sha != copied_sha.get("solution_coordinate"):
            raise ValueError(f"first-copy solution checksum differs: {solution_id}")
        command_relative = copied.get("command")
        command = _load_object(
            _owned_review_asset(review_root, command_relative, "first-copy command"),
            "first-copy command",
        )
        resource_plan: MrResourcePlan | None = None
        if derive_placed_copy_count:
            try:
                resource_plan = MrResourcePlan.model_validate(
                    command.get("resource_plan")
                )
                if (
                    resource_plan.owner_kind != "mr_hypothesis"
                    or resource_plan.owner_id != hypothesis.hypothesis_id
                ):
                    raise ValueError("resource plan owns another hypothesis")
            except (ValidationError, ValueError) as error:
                raise ValueError(
                    f"Phase III command lacks its MR resource plan: {solution_id}"
                ) from error
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
        placed_copy_count = 1
        normalised_result_relative: str | None = None
        normalised_result_sha256: str | None = None
        if derive_placed_copy_count:
            normalised_result_relative = copied.get("normalised_result")
            normalised_result = _owned_review_asset(
                review_root,
                normalised_result_relative,
                "first-copy normalised result",
            )
            normalised_result_sha256 = sha256_file(normalised_result)
            if normalised_result_sha256 != copied_sha.get("normalised_result"):
                raise ValueError(f"first-copy result checksum differs: {solution_id}")
            try:
                result_lines = normalised_result.read_bytes().splitlines()
                if len(result_lines) != 1:
                    raise ValueError("expected exactly one JSONL record")
                parsed_result = NormalisedMrResult.model_validate_json(result_lines[0])
            except (OSError, ValidationError, ValueError) as error:
                raise ValueError(
                    f"first-copy result is invalid: {solution_id}: {error}"
                ) from error
            if (
                parsed_result.hypothesis_id != hypothesis.hypothesis_id
                or parsed_result.execution_status is not ExecutionStatus.COMPLETED_HIT
                or parsed_result.placed_copy_count < 1
                or parsed_result.placed_copy_count > hypothesis.copy_count_expected
                or parsed_result.solution_coordinate_sha256 != coordinate_sha
            ):
                raise ValueError(
                    f"first-copy placed-copy evidence differs: {solution_id}"
                )
            placed_copy_count = parsed_result.placed_copy_count
            normalised_result_relative = normalised_result.relative_to(
                output
            ).as_posix()
        requires_additional = placed_copy_count < hypothesis.copy_count_expected
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
            "placed_copy_count": placed_copy_count,
            "requires_additional_copy": requires_additional,
            "derivation": "first_copy_solution_coordinate_rigid_body_derived",
            "source_solution_coordinate": str(coordinate_relative),
            "original_first_copy_model_sha256": original_model_sha,
            "staged_search_model": model_relative.as_posix(),
            "staged_search_model_sha256": coordinate_sha,
            "resource_plan": (
                resource_plan.model_dump(mode="json")
                if resource_plan is not None
                else None
            ),
        }
        if derive_placed_copy_count:
            model_sources[solution_id].update(
                {
                    "normalised_result": normalised_result_relative,
                    "normalised_result_sha256": normalised_result_sha256,
                }
            )
    return approved_rows, additional_rows, model_sources


def prepare_phase3_seed_stage(
    request: PhaseIIISeedStageRequest,
) -> PhaseIIISeedStageOutput:
    """Stage one owned Phase III A checkpoint without legacy translations."""

    package_path = _regular_file(
        request.review_package_manifest,
        "Phase III A-seed review-package manifest",
    )
    package_root = package_path.parent
    try:
        package = validate_phase3_review_package(package_root)
    except PhaseIIIReviewPackageError as error:
        raise ValueError(
            f"Phase III A-seed review package is invalid: {error}"
        ) from error
    review_artifacts = tuple(
        artifact
        for artifact in package.evidence_inventory
        if artifact.role == "mr_seed_review_manifest"
    )
    if len(review_artifacts) != 1:
        raise ValueError("Phase III A-seed package must contain one MR review manifest")
    review_manifest = _owned_review_asset(
        package_root,
        review_artifacts[0].relative_path,
        "owned MR review manifest",
    )
    hypotheses = _load_hypotheses(request.hypotheses_jsonl)
    approval = _load_phase3_seed_approval(
        request,
        review_manifest=review_manifest,
        hypotheses=hypotheses,
    )

    output_path = request.output_directory
    if output_path.is_symlink() or output_path.exists():
        raise ValueError(f"Phase III seed-stage output already exists: {output_path}")
    output = output_path.absolute()
    output.mkdir(parents=True)

    copied_package = _copy_owned_directory(
        package_root,
        output / "review_package",
        "Phase III A-seed review package",
    )
    copied_review_stage = _copy_owned_directory(
        request.review_stage,
        output / "review_stage",
        "Phase III A-seed review stage",
    )
    copied_package_manifest = _regular_file(
        copied_package / "phase3_review_package_manifest.json",
        "copied Phase III A-seed review-package manifest",
    )
    copied_stage_manifest = _regular_file(
        copied_review_stage / "phase3_review_stage_manifest.json",
        "copied Phase III A-seed stage manifest",
    )
    copied_decisions = _regular_file(
        copied_review_stage / "phase3_review_decision.json",
        "copied Phase III A-seed decisions",
    )
    copied_package_contract = validate_phase3_review_package(copied_package)
    if (
        copied_package_contract != approval.package
        or sha256_file(copied_package_manifest) != sha256_file(package_path)
        or sha256_file(copied_stage_manifest)
        != sha256_file(approval.stage_manifest_path)
        or sha256_file(copied_decisions)
        != sha256_file(approval.canonical_decisions_path)
    ):
        raise ValueError("copied Phase III A-seed authority differs from its source")

    copied_review_manifest = _owned_review_asset(
        copied_package,
        review_artifacts[0].relative_path,
        "copied owned MR review manifest",
    )
    legacy_manifest = _load_object(copied_review_manifest, "owned MR review manifest")
    items = _review_item_inventory(legacy_manifest)
    approved_ids = tuple(
        decision.item_id
        for decision in approval.decisions.decisions
        if decision.decision is PhaseIIIReviewDecisionValue.APPROVE
    )
    approved_rows, additional_rows, model_sources = _stage_approved_seed_models(
        approved_solution_ids=approved_ids,
        items=items,
        hypotheses=hypotheses,
        review_root=copied_review_manifest.parent,
        output=output,
        derive_placed_copy_count=True,
    )
    approved_seeds = output / "approved_seeds.tsv"
    additional_seeds = output / "additional_copy_seeds.tsv"
    atomic_write_text(approved_seeds, _seed_table(approved_rows))
    atomic_write_text(additional_seeds, _seed_table(additional_rows))

    provenance = _phase3_approval_provenance(approval)
    stage_identity: dict[str, object] = {
        "adapter_version": "phase3-owned-a-seed-stage-v4",
        "stage_kind": "phase3_owned_a_seed",
        "approval_provenance": provenance,
        "review_package_path": "review_package",
        "review_package_manifest_path": (
            "review_package/phase3_review_package_manifest.json"
        ),
        "review_package_manifest_sha256": sha256_file(copied_package_manifest),
        "review_stage_path": "review_stage",
        "review_stage_manifest_path": (
            "review_stage/phase3_review_stage_manifest.json"
        ),
        "review_stage_manifest_sha256": sha256_file(copied_stage_manifest),
        "canonical_decision_path": "review_stage/phase3_review_decision.json",
        "canonical_decision_sha256": sha256_file(copied_decisions),
        "mr_review_manifest_path": (
            copied_review_manifest.relative_to(output).as_posix()
        ),
        "mr_review_manifest_sha256": sha256_file(copied_review_manifest),
        "hypotheses_sha256": sha256_file(request.hypotheses_jsonl),
        "approved_solution_ids": list(approved_ids),
        "model_sources": model_sources,
        "approved_seed_count": len(approved_rows),
        "additional_copy_seed_count": len(additional_rows),
        "already_at_expected_copy_count": len(approved_rows) - len(additional_rows),
        "all_approved_seeds_retained": True,
        "numeric_score_filter_applied": False,
        "approved_seeds_sha256": sha256_file(approved_seeds),
        "additional_copy_seeds_sha256": sha256_file(additional_seeds),
        "output_allowlist": [
            "additional_copy_seeds.tsv",
            "approved_seeds.tsv",
            "models",
            "phase3_seed_stage_manifest.json",
            "review_package",
            "review_stage",
        ],
        "execution_status": ExecutionStatus.COMPLETED_SUCCESS.value,
    }
    stage_manifest = output / "phase3_seed_stage_manifest.json"
    atomic_write_json(
        stage_manifest,
        {
            "schema_version": "2.0",
            "stage_id": content_id("phase3seedstage_", stage_identity),
            "staged_at": utc_now_iso(),
            **stage_identity,
        },
    )
    validated = validate_phase3_seed_stage(
        stage_manifest,
        hypotheses_jsonl=request.hypotheses_jsonl,
    )
    if validated.approved_solution_ids != approved_ids:
        raise ValueError("published Phase III A-seed stage changed during validation")
    _LOGGER.info(
        "prepared owned Phase III A-seed stage",
        extra={
            "stage_manifest": str(stage_manifest),
            "approved_seed_count": len(approved_rows),
            "additional_copy_seed_count": len(additional_rows),
        },
    )
    return PhaseIIISeedStageOutput(
        approved_seeds_tsv=approved_seeds,
        additional_copy_seeds_tsv=additional_seeds,
        stage_manifest=stage_manifest,
        review_package=copied_package,
        review_stage=copied_review_stage,
        approved_seed_count=len(approved_rows),
        additional_copy_seed_count=len(additional_rows),
    )


def validate_phase3_seed_stage(
    stage_manifest: Path,
    *,
    hypotheses_jsonl: Path | None = None,
) -> PhaseIIISeedStageEvidence:
    """Revalidate one complete schema-v2 seed stage before scientific use."""

    manifest_path = _regular_file(stage_manifest, "Phase III seed-stage manifest")
    root = manifest_path.parent
    if manifest_path != root / "phase3_seed_stage_manifest.json":
        raise ValueError("Phase III seed-stage manifest has a non-canonical path")
    document = _load_object(manifest_path, "Phase III seed-stage manifest")
    allowlist = document.get("output_allowlist")
    if (
        document.get("schema_version") != "2.0"
        or document.get("adapter_version") != "phase3-owned-a-seed-stage-v4"
        or document.get("stage_kind") != "phase3_owned_a_seed"
        or document.get("execution_status") != ExecutionStatus.COMPLETED_SUCCESS.value
        or not isinstance(allowlist, list)
        or any(not isinstance(item, str) for item in allowlist)
        or len(set(allowlist)) != len(allowlist)
        or {path.name for path in root.iterdir()} != set(allowlist)
    ):
        raise ValueError("Phase III seed stage violates its output contract")
    identity = {
        key: value
        for key, value in document.items()
        if key not in {"schema_version", "stage_id", "staged_at"}
    }
    stage_id = document.get("stage_id")
    if not isinstance(stage_id, str) or stage_id != content_id(
        "phase3seedstage_", identity
    ):
        raise ValueError("Phase III seed-stage identity differs from its content")

    fixed_paths = {
        "review_package_manifest_path": (
            "review_package/phase3_review_package_manifest.json"
        ),
        "review_stage_manifest_path": (
            "review_stage/phase3_review_stage_manifest.json"
        ),
        "canonical_decision_path": "review_stage/phase3_review_decision.json",
    }
    if any(document.get(key) != value for key, value in fixed_paths.items()):
        raise ValueError("Phase III seed stage uses a non-canonical authority path")
    package_manifest = _owned_review_asset(
        root,
        document.get("review_package_manifest_path"),
        "Phase III review-package manifest",
    )
    review_stage_manifest = _owned_review_asset(
        root,
        document.get("review_stage_manifest_path"),
        "Phase III review-stage manifest",
    )
    canonical_decision = _owned_review_asset(
        root,
        document.get("canonical_decision_path"),
        "Phase III canonical decision",
    )
    review_manifest = _owned_review_asset(
        root,
        document.get("mr_review_manifest_path"),
        "owned MR review manifest",
    )
    checksum_pairs = (
        (package_manifest, "review_package_manifest_sha256"),
        (review_stage_manifest, "review_stage_manifest_sha256"),
        (canonical_decision, "canonical_decision_sha256"),
        (review_manifest, "mr_review_manifest_sha256"),
    )
    if any(sha256_file(path) != document.get(key) for path, key in checksum_pairs):
        raise ValueError("Phase III seed-stage authority checksum differs")
    try:
        package = validate_phase3_review_package(package_manifest.parent)
        review_stage = PhaseIIIReviewStageManifest.model_validate_json(
            review_stage_manifest.read_bytes()
        )
        decisions = PhaseIIIReviewDecisionFile.model_validate_json(
            canonical_decision.read_bytes()
        )
    except (OSError, ValidationError, PhaseIIIReviewPackageError) as error:
        raise ValueError(
            f"Phase III seed-stage authority is invalid: {error}"
        ) from error
    provenance = document.get("approval_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("Phase III seed-stage approval provenance is absent")
    owned_run_registry_id = provenance.get("owned_run_registry_id")
    if not isinstance(owned_run_registry_id, str) or not owned_run_registry_id:
        raise ValueError("Phase III seed-stage owned-run identity is absent")
    approval = _PhaseIIISeedApproval(
        stage=review_stage,
        decisions=decisions,
        package=package,
        stage_manifest_path=review_stage_manifest,
        canonical_decisions_path=canonical_decision,
        package_manifest_path=package_manifest,
        owned_run_registry_id=owned_run_registry_id,
    )
    if provenance != _phase3_approval_provenance(approval):
        raise ValueError("Phase III seed-stage provenance differs from its authority")
    approved_ids = tuple(
        decision.item_id
        for decision in decisions.decisions
        if decision.decision is PhaseIIIReviewDecisionValue.APPROVE
    )
    if document.get("approved_solution_ids") != list(approved_ids):
        raise ValueError("Phase III seed-stage approved identities differ")
    hypotheses: dict[str, MrHypothesis] | None = None
    if hypotheses_jsonl is not None:
        hypotheses_path = _regular_file(hypotheses_jsonl, "MR hypotheses")
        if sha256_file(hypotheses_path) != document.get("hypotheses_sha256"):
            raise ValueError("Phase III seed-stage hypotheses differ")
        hypotheses = _load_hypotheses(hypotheses_path)

    approved_seeds = _regular_file(root / "approved_seeds.tsv", "approved seeds")
    additional_seeds = _regular_file(
        root / "additional_copy_seeds.tsv", "additional-copy seeds"
    )
    if sha256_file(approved_seeds) != document.get(
        "approved_seeds_sha256"
    ) or sha256_file(additional_seeds) != document.get("additional_copy_seeds_sha256"):
        raise ValueError("Phase III seed-stage seed-table checksum differs")
    approved_rows = _load_seed_rows(approved_seeds, "approved seeds")
    additional_rows = _load_seed_rows(additional_seeds, "additional-copy seeds")
    if tuple(approved_rows) != approved_ids:
        raise ValueError("Phase III seed-stage approved seed order differs")
    expected_additional = tuple(
        seed_id
        for seed_id, row in approved_rows.items()
        if row.get("requires_additional_copy") == "true"
    )
    if tuple(additional_rows) != expected_additional:
        raise ValueError("Phase III seed-stage additional-copy identities differ")
    if (
        document.get("approved_seed_count") != len(approved_rows)
        or document.get("additional_copy_seed_count") != len(additional_rows)
        or document.get("already_at_expected_copy_count")
        != len(approved_rows) - len(additional_rows)
        or document.get("all_approved_seeds_retained") is not True
        or document.get("numeric_score_filter_applied") is not False
    ):
        raise ValueError("Phase III seed-stage counts or retention policy differ")
    raw_sources = document.get("model_sources")
    if not isinstance(raw_sources, dict) or set(raw_sources) != set(approved_ids):
        raise ValueError("Phase III seed-stage model-source inventory differs")
    model_sources: dict[str, dict[str, object]] = {}
    for seed_id in approved_ids:
        raw_source = raw_sources.get(seed_id)
        if not isinstance(raw_source, dict):
            raise ValueError(f"Phase III model source is invalid: {seed_id}")
        source = cast(dict[str, object], raw_source)
        try:
            resource_plan = MrResourcePlan.model_validate(source.get("resource_plan"))
        except ValidationError as error:
            raise ValueError(
                f"Phase III MR resource plan is invalid: {seed_id}"
            ) from error
        hypothesis_id = source.get("hypothesis_id")
        if (
            resource_plan.owner_kind != "mr_hypothesis"
            or resource_plan.owner_id != hypothesis_id
            or (
                hypotheses is not None
                and (
                    not isinstance(hypothesis_id, str)
                    or hypothesis_id not in hypotheses
                )
            )
        ):
            raise ValueError(f"Phase III MR resource plan owner differs: {seed_id}")
        model = _owned_review_asset(
            root, source.get("staged_search_model"), "staged search model"
        )
        model_sha = source.get("staged_search_model_sha256")
        placed_copy_count = source.get("placed_copy_count")
        expected_copy_count = source.get("expected_copy_count")
        requires_additional = source.get("requires_additional_copy")
        row = approved_rows[seed_id]
        if (
            not isinstance(model_sha, str)
            or isinstance(placed_copy_count, bool)
            or not isinstance(placed_copy_count, int)
            or isinstance(expected_copy_count, bool)
            or not isinstance(expected_copy_count, int)
            or not 1 <= placed_copy_count <= expected_copy_count
            or requires_additional is not (placed_copy_count < expected_copy_count)
            or sha256_file(model) != model_sha
            or row.get("search_model_sha256") != model_sha
            or row.get("expected_copy_count") != str(expected_copy_count)
            or row.get("requires_additional_copy") != str(requires_additional).lower()
        ):
            raise ValueError(f"Phase III staged model differs: {seed_id}")
        normalised_result = _owned_review_asset(
            root,
            source.get("normalised_result"),
            "Phase III first-copy normalised result",
        )
        if sha256_file(normalised_result) != source.get("normalised_result_sha256"):
            raise ValueError(f"Phase III first-copy result differs: {seed_id}")
        model_sources[seed_id] = source
    review_document = _load_object(review_manifest, "owned MR review manifest")
    return PhaseIIISeedStageEvidence(
        stage_id=stage_id,
        review_id=decisions.decision_file_id,
        approved_solution_ids=approved_ids,
        root=root,
        review_root=review_manifest.parent,
        review_manifest=review_manifest,
        review_document=review_document,
        model_sources=model_sources,
    )


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
    output_path = request.output_directory
    if output_path.is_symlink() or output_path.exists():
        raise ValueError(f"live M4 stage output already exists: {output_path}")
    output = output_path.absolute()
    output.mkdir(parents=True)

    decisions = output / "approved_mr_seeds.tsv"
    decisions = _copy_file(request.decisions, decisions, "MR seed decisions")
    validation_json = output / "validated_mr_seed_decisions.json"
    approval = validate_mr_seed_approvals(
        MrSeedApprovalRequest(
            package_manifest=review_manifest,
            decisions=decisions,
            output_json=validation_json,
            progress=request.progress,
        )
    )
    manifest = _load_object(review_manifest, "MR review manifest")
    items = _review_item_inventory(manifest)

    approved_rows, additional_rows, model_sources = _stage_approved_seed_models(
        approved_solution_ids=approval.approved_solution_ids,
        items=items,
        hypotheses=hypotheses,
        review_root=review,
        output=output,
    )

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
