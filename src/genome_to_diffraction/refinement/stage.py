"""Build the fixed checksum-bound input boundary for Viper T12.

The stage derives exactly one supported two-copy PDB/MTZ parent per retained
M4 seed.  It never re-ranks or drops seeds and copies only evidence already
inside the immutable parent run plus the fixed catalogue source crosswalk.
"""

import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.schemas.results import (
    AdditionalCopyResult,
    MtzPreflightRecord,
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.status import InputContractError

_LOGGER = logging.getLogger("genome_to_diffraction.refinement.stage")


class T12StageError(InputContractError):
    """The retained M4 parent cannot provide the fixed T12 boundary."""


@dataclass(frozen=True, slots=True)
class T12StageRequest:
    """Fixed inputs for one all-candidate T12 stage."""

    parent_run: Path
    source_records_jsonl: Path
    output_directory: Path
    expected_seed_count: int = 11
    progress: bool = True


@dataclass(frozen=True, slots=True)
class T12StageOutput:
    """Stable T12 stage products."""

    manifest: Path
    finalists: Path
    seed_count: int
    source_records_sha256: str


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise T12StageError(f"cannot read {label}: {path}") from error
    if not isinstance(value, dict):
        raise T12StageError(f"{label} must be a JSON object")
    return value


def _regular(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise T12StageError(f"required {label} is absent: {path}") from error
    if path.is_symlink() or not resolved.is_file():
        raise T12StageError(f"{label} must be a regular non-symlink file")
    return resolved


def _read_jsonl[T](path: Path, model: type[T], label: str) -> tuple[T, ...]:
    records: list[T] = []
    with _regular(path, label).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(model.model_validate_json(line))  # type: ignore[attr-defined]
            except PydanticValidationError as error:
                raise T12StageError(
                    f"invalid {label} at line {line_number}: {path}"
                ) from error
    if not records:
        raise T12StageError(f"{label} is empty: {path}")
    return tuple(records)


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            with source.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, handle, length=1024 * 1024)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def stage_t12_inputs(request: T12StageRequest) -> T12StageOutput:
    """Create an immutable all-11 T12 boundary from one accepted M4 run."""

    if request.expected_seed_count < 1:
        raise ValueError("expected_seed_count must be positive")
    parent = request.parent_run.resolve(strict=True)
    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise T12StageError(f"T12 stage directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    qualification = parent / "artifacts/qualification"
    summary_path = _regular(qualification / "m4-copy-summary.json", "M4 summary")
    resume_path = _regular(
        qualification / "m4-copy-resume-check.json", "M4 resume record"
    )
    summary = _load_object(summary_path, "M4 summary")
    resume = _load_object(resume_path, "M4 resume record")
    parent_stage_manifest_path = _regular(
        parent / "artifacts/m4-copy-inputs/m4_copy_stage_manifest.json",
        "M4 stage manifest",
    )
    parent_stage_manifest = _load_object(
        parent_stage_manifest_path, "M4 stage manifest"
    )
    raw_inputs = parent_stage_manifest.get("inputs")
    raw_mtz = raw_inputs.get("mtz") if isinstance(raw_inputs, dict) else None
    parent_mtz_sha256 = raw_mtz.get("sha256") if isinstance(raw_mtz, dict) else None
    if not isinstance(parent_mtz_sha256, str):
        raise T12StageError("M4 stage manifest omits the parent MTZ checksum")
    if (
        summary.get("attempted_seed_count") != request.expected_seed_count
        or summary.get("all_parents_retained") is not True
        or summary.get("all_resume_processes_cached") is not True
        or resume.get("all_candidate_series_cached") is not True
    ):
        raise T12StageError("M4 parent is not accepted retain-all cached evidence")

    results = _read_jsonl(
        qualification / "m4-copy-results.jsonl",
        AdditionalCopyResult,
        "M4 result",
    )
    selected: dict[str, AdditionalCopyResult] = {}
    for result in results:
        if result.attempted_copy_number != 2 or not result.additional_copy_supported:
            continue
        if result.seed_solution_id in selected:
            raise T12StageError(
                "M4 parent contains duplicate supported copy-two results"
            )
        selected[result.seed_solution_id] = result
    if len(selected) != request.expected_seed_count:
        raise T12StageError(
            "M4 parent does not contain exactly the expected supported copy-two parents"
        )

    common = parent / "artifacts/m4-copy-inputs/inputs"
    sequence_groups_source = _regular(
        common / "sequence_groups.jsonl", "sequence groups"
    )
    preflight_source = _regular(common / "preflight.jsonl", "MTZ preflight")
    phenix_source = _regular(common / "phenix_manifest.json", "Phenix manifest")
    groups = _read_jsonl(sequence_groups_source, SequenceGroupRecord, "sequence group")
    preflights = _read_jsonl(preflight_source, MtzPreflightRecord, "MTZ preflight")
    matching_preflights = tuple(
        record for record in preflights if record.mtz_sha256 == parent_mtz_sha256
    )
    if len(matching_preflights) != 1:
        raise T12StageError(
            "T12 requires exactly one preflight record matching the parent MTZ"
        )
    selected_preflight = matching_preflights[0]
    if selected_preflight.free_flag_status == "missing":
        raise T12StageError("T12 refinement requires FreeR flags in the parent MTZ")
    diffraction_mtz_source = _regular(common / "mtz.mtz", "parent diffraction MTZ")
    if sha256_file(diffraction_mtz_source) != parent_mtz_sha256:
        raise T12StageError("parent diffraction MTZ checksum mismatch")
    source_records_source = _regular(
        request.source_records_jsonl, "catalogue source-record crosswalk"
    )
    source_records = _read_jsonl(
        source_records_source, SourceProteinRecord, "source record"
    )
    group_ids = {group.sequence_group_id for group in groups}
    source_group_ids = {record.sequence_group_id for record in source_records}
    if source_group_ids != group_ids:
        raise T12StageError(
            "source-record crosswalk and sequence-group catalogue identities differ"
        )

    inputs = output / "inputs"
    _atomic_copy(sequence_groups_source, inputs / "sequence_groups.jsonl")
    _atomic_copy(preflight_source, inputs / "preflight.jsonl")
    _atomic_copy(phenix_source, inputs / "phenix_manifest.json")
    _atomic_copy(source_records_source, inputs / "source_records.jsonl")
    diffraction_mtz = inputs / "diffraction.mtz"
    _atomic_copy(diffraction_mtz_source, diffraction_mtz)

    rows = [
        "seed_solution_id\tsequence_group_id\tinput_copy_count\t"
        "parent_coordinate\tparent_coordinate_sha256\tparent_mtz\t"
        "parent_mtz_sha256\tresolution"
    ]
    candidate_manifest: list[dict[str, object]] = []
    iterator = tqdm(
        sorted(selected.items()),
        desc="Stage T12 parents",
        unit="candidate",
        disable=not request.progress,
    )
    for seed_id, result in iterator:
        candidate_root = (
            parent / "artifacts/m4-copy/copy-two" / f"additional_copy_{seed_id}"
        )
        coordinate = _regular(candidate_root / "PHASER.1.pdb", "copy-two PDB")
        mtz = _regular(candidate_root / "PHASER.1.mtz", "copy-two MTZ")
        coordinate_sha = sha256_file(coordinate)
        mtz_sha = sha256_file(mtz)
        if (
            coordinate_sha != result.output_coordinate_sha256
            or mtz_sha != result.output_mtz_sha256
        ):
            raise T12StageError(f"copy-two asset checksum mismatch for {seed_id}")
        candidate_out = output / "parents" / seed_id
        coordinate_out = candidate_out / "parent.pdb"
        mtz_out = candidate_out / "phaser_solution.mtz"
        _atomic_copy(coordinate, coordinate_out)
        _atomic_copy(mtz, mtz_out)
        rows.append(
            "\t".join(
                (
                    seed_id,
                    result.sequence_group_id,
                    "2",
                    str(coordinate_out),
                    coordinate_sha,
                    str(diffraction_mtz),
                    parent_mtz_sha256,
                    str(selected_preflight.resolution_high_a),
                )
            )
        )
        candidate_manifest.append(
            {
                "seed_solution_id": seed_id,
                "sequence_group_id": result.sequence_group_id,
                "copy_count": 2,
                "child_solution_id": result.child_solution_id,
                "source_coordinate": str(coordinate.relative_to(parent)),
                "source_coordinate_sha256": coordinate_sha,
                "source_mtz": str(mtz.relative_to(parent)),
                "source_mtz_sha256": mtz_sha,
                "staged_solution_mtz": str(mtz_out.relative_to(output)),
            }
        )

    finalists = output / "finalists.tsv"
    atomic_write_text(finalists, "\n".join(rows) + "\n")
    manifest = output / "t12_stage_manifest.json"
    source_sha = sha256_file(inputs / "source_records.jsonl")
    atomic_write_json(
        manifest,
        {
            "schema_version": "1.0",
            "profile": "t12",
            "selection_policy": "retain_all_supported_copy_two_parents",
            "parent_run_id": parent.name,
            "seed_count": len(candidate_manifest),
            "parent_summary_sha256": sha256_file(summary_path),
            "parent_resume_sha256": sha256_file(resume_path),
            "parent_results_sha256": sha256_file(
                qualification / "m4-copy-results.jsonl"
            ),
            "parent_stage_manifest_sha256": sha256_file(parent_stage_manifest_path),
            "parent_mtz_sha256": parent_mtz_sha256,
            "parent_mtz_free_flag_status": selected_preflight.free_flag_status,
            "sequence_groups_sha256": sha256_file(inputs / "sequence_groups.jsonl"),
            "source_records_sha256": source_sha,
            "preflight_sha256": sha256_file(inputs / "preflight.jsonl"),
            "phenix_manifest_sha256": sha256_file(inputs / "phenix_manifest.json"),
            "finalists_sha256": sha256_file(finalists),
            "candidates": candidate_manifest,
        },
    )
    _LOGGER.info(
        "fixed T12 inputs staged",
        extra={
            "parent_run_id": parent.name,
            "seed_count": len(candidate_manifest),
            "manifest": str(manifest),
        },
    )
    return T12StageOutput(manifest, finalists, len(candidate_manifest), source_sha)
