"""Prepare checksum-bound inputs for comparative additional-copy screening.

The fixed-site interface authenticates a retained successful P2-diverse run and
resolves each original processed model.  The normal-workflow interface consumes
the live review package and uses each approved rigid-body-derived solution
coordinate as its next search model.  Both revalidate the human decision file,
copy only approved review assets, and write a bounded seed table.  Neither
performs molecular replacement or makes a scientific selection.
"""

import csv
import json
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
    validate_mr_seed_approvals,
)
from genome_to_diffraction.schemas.results import MrHypothesis
from genome_to_diffraction.status import ExecutionStatus

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


def _load_object(path: Path, label: str) -> dict[str, object]:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load {label}: {path}") from error
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


def _seed_table(rows: list[tuple[str, str, str, int, str]]) -> str:
    from io import StringIO

    buffer = StringIO(newline="")
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
    output_path = request.output_directory
    if output_path.is_symlink() or output_path.exists():
        raise ValueError(f"live M4 stage output already exists: {output_path}")
    output = output_path.absolute()
    output.mkdir(parents=True)

    review_manifest = _regular_file(
        review / "mr_seed_review_manifest.json", "MR review manifest"
    )
    decisions = _copy_file(
        request.decisions,
        output / "approved_mr_seeds.tsv",
        "MR seed decisions",
    )
    validation_json = output / "validated_mr_seed_decisions.json"
    approval = validate_mr_seed_approvals(
        MrSeedApprovalRequest(
            package_manifest=review_manifest,
            decisions=decisions,
            output_json=validation_json,
            progress=request.progress,
        )
    )
    hypotheses = _load_hypotheses(request.hypotheses_jsonl)
    manifest = _load_object(review_manifest, "MR review manifest")
    raw_items = manifest.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("MR review manifest has no item inventory")
    items = {
        str(item["solution_id"]): cast(dict[str, object], item)
        for item in raw_items
        if isinstance(item, dict) and isinstance(item.get("solution_id"), str)
    }

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
