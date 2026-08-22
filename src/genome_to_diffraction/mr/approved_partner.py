"""Run the accepted partner adapter from one approved component-workflow seed.

This P3 bridge consumes the existing normal-workflow MR review package and its
``stage-approved-seeds`` output. It requires exactly one explicitly approved,
packed, one-copy A state, verifies the copied coordinate and parent LLG, binds
the checksum-frozen 6RTZ B model from the control preparation manifest, and
delegates execution to :func:`run_partner_search`.

The bridge adds no candidate ranking, general composition graph, or scheduler.
Input/checkpoint inconsistencies fail as contracts; hit/no-hit/tool/parse
statuses remain those of ``PartnerSearchResult``. Its identity and cache key are
therefore the accepted partner adapter identity plus the validated review,
parent, model, sequence, MTZ, and Phenix inputs. Focused tests cover the approved
happy path and rejection of absent approval or changed parent evidence.
"""

import csv
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from pydantic import ValidationError

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.mr.partner import (
    PartnerSearchOutput,
    PartnerSearchRequest,
    run_partner_search,
)
from genome_to_diffraction.mr.phaser import PhaserInputError
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.schemas.results import (
    NormalisedMrResult,
    PartnerCandidateSelectionStatus,
    PartnerSearchPlan,
)
from genome_to_diffraction.status import ExecutionStatus


@dataclass(frozen=True)
class ApprovedPartnerSearchRequest:
    """Inputs for one explicitly approved A-to-B transition."""

    approved_stage: Path
    review_package: Path
    control_preparation_manifest: Path
    sequence_groups_jsonl: Path
    preflight_jsonl: Path
    mtz: Path
    phenix_manifest: Path
    output_directory: Path
    threads: int = 1
    timeout_seconds: float | None = None
    progress: bool = True


@dataclass(frozen=True)
class PlannedPartnerSearchRequest:
    """Inputs for one selected catalogue B attempt from an approved A state."""

    approved_stage: Path
    review_package: Path
    partner_plan_json: Path
    partner_candidate_id: str
    sequence_groups_jsonl: Path
    model_registry_directory: Path
    preflight_jsonl: Path
    mtz: Path
    phenix_manifest: Path
    output_directory: Path
    threads: int = 1
    timeout_seconds: float | None = None
    progress: bool = True


@dataclass(frozen=True)
class _ApprovedParent:
    solution_id: str
    sequence_group_id: str
    coordinate: Path
    coordinate_sha256: str
    llg: float
    copy_count: int


def _object(path: Path, *, label: str) -> tuple[Path, dict[str, object]]:
    resolved = path.resolve(strict=True)
    try:
        document = load_json_document(resolved)
    except ContractLoadError as error:
        raise PhaserInputError(f"cannot read {label}: {error}") from error
    if not isinstance(document, dict):
        raise PhaserInputError(f"{label} must be a JSON object")
    return resolved, cast(dict[str, object], document)


def _owned(root: Path, relative: object, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise PhaserInputError(f"{label} path is invalid")
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts:
        raise PhaserInputError(f"{label} path escapes its package")
    resolved = (root / Path(*path.parts)).resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(root.resolve(strict=True)):
        raise PhaserInputError(f"{label} is absent or outside its package")
    return resolved


def _approved_parent(approved_stage: Path, review_package: Path) -> _ApprovedParent:
    stage = approved_stage.resolve(strict=True)
    review = review_package.resolve(strict=True)
    if not stage.is_dir() or not review.is_dir():
        raise PhaserInputError("approved stage and review package must be directories")
    _, stage_manifest = _object(
        stage / "live_m4_stage_manifest.json", label="approved-stage manifest"
    )
    approved_tsv = stage / "approved_seeds.tsv"
    validation = stage / "validated_mr_seed_decisions.json"
    if (
        stage_manifest.get("execution_status")
        != ExecutionStatus.COMPLETED_SUCCESS.value
        or stage_manifest.get("approved_seed_count") != 1
        or stage_manifest.get("approved_seeds_sha256") != sha256_file(approved_tsv)
        or stage_manifest.get("validation_sha256") != sha256_file(validation)
    ):
        raise PhaserInputError("approved A stage is incomplete or changed")
    with approved_tsv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    required = {
        "seed_solution_id",
        "search_model",
        "search_model_sha256",
        "expected_copy_count",
        "requires_additional_copy",
    }
    if len(rows) != 1 or set(rows[0]) != required:
        raise PhaserInputError("approved A table must contain exactly one fixed row")
    row = rows[0]
    try:
        expected_copy_count = int(row["expected_copy_count"])
    except ValueError as error:
        raise PhaserInputError("approved A state has an invalid copy count") from error
    if expected_copy_count < 1 or row["requires_additional_copy"] != "false":
        raise PhaserInputError("approved A state is not a complete retained parent")
    solution_id = row["seed_solution_id"]
    coordinate_sha256 = row["search_model_sha256"]
    if not solution_id or re.fullmatch(r"[a-f0-9]{64}", coordinate_sha256) is None:
        raise PhaserInputError("approved A table contains invalid identities")
    coordinate = Path(row["search_model"]).resolve(strict=True)
    if not coordinate.is_file() or sha256_file(coordinate) != coordinate_sha256:
        raise PhaserInputError("approved A coordinate checksum differs")

    _, review_manifest = _object(
        review / "mr_seed_review_manifest.json", label="MR review manifest"
    )
    items = review_manifest.get("items")
    matches = (
        [
            cast(dict[str, object], item)
            for item in items
            if isinstance(item, dict) and item.get("solution_id") == solution_id
        ]
        if isinstance(items, list)
        else []
    )
    if len(matches) != 1:
        raise PhaserInputError("approved A solution is not unique in review package")
    item = matches[0]
    copied = item.get("copied_assets")
    copied_sha = item.get("copied_asset_sha256")
    sequence_group_id = item.get("sequence_group_id")
    if (
        not isinstance(copied, dict)
        or not isinstance(copied_sha, dict)
        or not isinstance(sequence_group_id, str)
    ):
        raise PhaserInputError("approved A review item lacks typed assets")
    review_coordinate = _owned(
        review, copied.get("solution_coordinate"), label="review A coordinate"
    )
    if (
        sha256_file(review_coordinate) != copied_sha.get("solution_coordinate")
        or sha256_file(review_coordinate) != coordinate_sha256
    ):
        raise PhaserInputError("approved and reviewed A coordinates differ")
    parent_result_path = _owned(
        review, copied.get("normalised_result"), label="review A result"
    )
    if sha256_file(parent_result_path) != copied_sha.get("normalised_result"):
        raise PhaserInputError("review A result checksum differs")
    try:
        result = NormalisedMrResult.model_validate_json(
            parent_result_path.read_text(encoding="utf-8").strip()
        )
    except (OSError, ValidationError) as error:
        raise PhaserInputError("review A result is invalid") from error
    if (
        result.execution_status is not ExecutionStatus.COMPLETED_HIT
        or result.placed_copy_count != expected_copy_count
        or result.packing_summary.get("top_solution_packed") is not True
        or result.llg is None
    ):
        raise PhaserInputError("approved A result does not match its packed copy count")
    return _ApprovedParent(
        solution_id=solution_id,
        sequence_group_id=sequence_group_id,
        coordinate=coordinate,
        coordinate_sha256=coordinate_sha256,
        llg=result.llg,
        copy_count=expected_copy_count,
    )


def run_approved_partner_search(
    request: ApprovedPartnerSearchRequest,
) -> PartnerSearchOutput:
    """Search fixed 6RTZ B from one explicitly approved normal-workflow A seed."""

    parent = _approved_parent(request.approved_stage, request.review_package)
    preparation_path, preparation = _object(
        request.control_preparation_manifest, label="6RTZ control preparation"
    )
    if (
        preparation.get("adapter_version") != "6rtz-fixed-a-one-b-inputs-v1"
        or preparation.get("crystal_id") != "6RTZ"
        or preparation.get("composition") != {"A": 1, "B": 1}
        or preparation.get("parent_sequence_group_id") != parent.sequence_group_id
        or parent.copy_count != 1
    ):
        raise PhaserInputError("approved A does not match fixed 6RTZ composition")
    partner_group = preparation.get("partner_sequence_group_id")
    identity = preparation.get("partner_model_identity_fraction")
    files = preparation.get("files")
    partner_entry = files.get("partner_model") if isinstance(files, dict) else None
    if (
        not isinstance(partner_group, str)
        or isinstance(identity, bool)
        or not isinstance(identity, int | float)
        or not isinstance(partner_entry, dict)
    ):
        raise PhaserInputError("fixed 6RTZ partner specification is incomplete")
    partner_model = _owned(
        preparation_path.parent,
        partner_entry.get("path"),
        label="fixed B model",
    )
    partner_sha256 = partner_entry.get("sha256")
    if (
        not isinstance(partner_sha256, str)
        or sha256_file(partner_model) != partner_sha256
    ):
        raise PhaserInputError("fixed B model checksum differs")
    return run_partner_search(
        PartnerSearchRequest(
            crystal_id="6RTZ",
            parent_solution_id=parent.solution_id,
            parent_sequence_group_id=parent.sequence_group_id,
            partner_sequence_group_id=partner_group,
            sequence_groups_jsonl=request.sequence_groups_jsonl,
            parent_coordinate=parent.coordinate,
            expected_parent_coordinate_sha256=parent.coordinate_sha256,
            parent_llg=parent.llg,
            parent_copy_count=parent.copy_count,
            partner_model=partner_model,
            expected_partner_model_sha256=partner_sha256,
            partner_model_identity_fraction=float(identity),
            preflight_jsonl=request.preflight_jsonl,
            mtz=request.mtz,
            phenix_manifest=request.phenix_manifest,
            output_directory=request.output_directory,
            threads=request.threads,
            timeout_seconds=request.timeout_seconds,
            progress=request.progress,
        )
    )


def run_planned_partner_search(
    request: PlannedPartnerSearchRequest,
) -> PartnerSearchOutput:
    """Run one plan-selected B model from one approved retained A state."""

    parent = _approved_parent(request.approved_stage, request.review_package)
    plan_path = request.partner_plan_json.resolve(strict=True)
    try:
        plan = PartnerSearchPlan.model_validate_json(
            plan_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise PhaserInputError("partner search plan is invalid") from error
    matches = [
        item
        for item in plan.candidates
        if item.candidate_id == request.partner_candidate_id
    ]
    if len(matches) != 1:
        raise PhaserInputError("partner candidate is not unique in its plan")
    candidate = matches[0]
    if candidate.selection_status is not PartnerCandidateSelectionStatus.SELECTED:
        raise PhaserInputError("partner candidate was not selected for execution")
    if (
        plan.parent_sequence_group_id != parent.sequence_group_id
        or plan.parent_copy_count != parent.copy_count
        or plan.parent_state_sha256
        != sha256_file(
            request.approved_stage.resolve(strict=True) / "live_m4_stage_manifest.json"
        )
    ):
        raise PhaserInputError("partner plan parent differs from approved A state")
    if (
        candidate.model_path is None
        or candidate.model_sha256 is None
        or candidate.model_sequence_identity is None
        or candidate.model_sequence_identity <= 0
    ):
        raise PhaserInputError(
            "selected partner candidate lacks executable model evidence"
        )
    registry = request.model_registry_directory.resolve(strict=True)
    partner_model = _owned(
        registry,
        candidate.model_path,
        label="planned B model",
    )
    if sha256_file(partner_model) != candidate.model_sha256:
        raise PhaserInputError("planned B model checksum differs")
    plan_sha256 = sha256_file(plan_path)
    return run_partner_search(
        PartnerSearchRequest(
            crystal_id=plan.crystal_id,
            parent_solution_id=parent.solution_id,
            parent_sequence_group_id=parent.sequence_group_id,
            partner_sequence_group_id=candidate.sequence_group_id,
            sequence_groups_jsonl=request.sequence_groups_jsonl,
            parent_coordinate=parent.coordinate,
            expected_parent_coordinate_sha256=parent.coordinate_sha256,
            parent_llg=parent.llg,
            parent_copy_count=parent.copy_count,
            partner_model=partner_model,
            expected_partner_model_sha256=candidate.model_sha256,
            partner_model_identity_fraction=candidate.model_sequence_identity,
            partner_copy_count=plan.partner_copy_count,
            preflight_jsonl=request.preflight_jsonl,
            mtz=request.mtz,
            phenix_manifest=request.phenix_manifest,
            output_directory=request.output_directory,
            selection_plan_id=plan.plan_id,
            selection_plan_sha256=plan_sha256,
            partner_candidate_id=candidate.candidate_id,
            threads=request.threads,
            timeout_seconds=request.timeout_seconds,
            progress=request.progress,
        )
    )
