"""Prepare checksum-bound inputs for comparative additional-copy screening.

This module is used by the fixed Marmic dispatcher after it has authenticated a
retained successful P2-diverse run.  It revalidates the human decision file,
copies only approved review assets, resolves each original processed model by
the SHA-256 recorded in the first-copy command, and writes a bounded seed table.
It performs no molecular replacement and makes no scientific selection.
"""

import csv
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.review.mr_seed import (
    MrSeedApprovalRequest,
    validate_mr_seed_approvals,
)

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

    anchor = output if cross_site_import else parent
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
