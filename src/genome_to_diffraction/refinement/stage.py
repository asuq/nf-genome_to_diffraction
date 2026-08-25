"""Build checksum-bound input boundaries for T12 refinement.

The retained-run stage derives exactly one supported two-copy parent per Viper
M4 seed.  The normal-workflow stage instead follows every explicitly approved
seed through its bounded copy series and retains the last checksum-authenticated
supported state.  Neither stage re-ranks or drops candidates.  Refinement uses
the original diffraction MTZ so FreeR flags are preserved; Phaser solution MTZ
files remain copied provenance rather than refinement observations.
"""

import csv
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError as PydanticValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.schemas.results import (
    AdditionalCopyResult,
    MrHypothesis,
    MtzPreflightRecord,
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

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


@dataclass(frozen=True, slots=True)
class LiveT12StageRequest:
    """Normal-workflow inputs after explicit MR-seed approval and copy search."""

    approved_stage: Path
    review_package: Path | None
    additional_copy_results: tuple[Path, ...]
    hypotheses_jsonl: Path
    sequence_groups_jsonl: Path
    source_records_jsonl: Path
    preflight_jsonl: Path
    diffraction_mtz: Path
    phenix_manifest: Path
    output_directory: Path
    progress: bool = True
    phase3_seed_stage_manifest: Path | None = None


@dataclass(frozen=True, slots=True)
class LiveT12StageOutput:
    """Normal-workflow T12 finalists and copy-state report."""

    manifest: Path
    finalists: Path
    copy_report_tsv: Path
    copy_report_markdown: Path
    seed_count: int


@dataclass(frozen=True, slots=True)
class _SupportedState:
    """One checksum-authenticated state that can safely enter T12."""

    solution_id: str
    copy_count: int
    coordinate: Path
    coordinate_sha256: str
    solution_mtz: Path
    solution_mtz_sha256: str
    source_kind: str


@dataclass(frozen=True, slots=True)
class _CopySeries:
    """Validated typed copy-series evidence for one approved seed."""

    root: Path
    results: tuple[AdditionalCopyResult, ...]
    result_paths: tuple[Path, ...]
    summary: Path
    aggregate: Path
    stop_reason: str
    retained_state: _SupportedState | None


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = load_json_document(path)
    except ContractLoadError as error:
        raise T12StageError(f"cannot read {label}: {error}") from error
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
                records.append(
                    model.model_validate_json(line)  # ty: ignore[unresolved-attribute]
                )
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


def _directory(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise T12StageError(f"required {label} is absent: {path}") from error
    if path.is_symlink() or not resolved.is_dir():
        raise T12StageError(f"{label} must be a regular non-symlink directory")
    return resolved


def _owned_regular(root: Path, relative: object, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise T12StageError(f"{label} path is absent")
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise T12StageError(f"{label} path is unsafe")
    resolved = _regular(root / relative_path, label)
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise T12StageError(f"{label} escapes its owning bundle")
    return resolved


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise T12StageError(f"{label} is absent or invalid")
    return value


def _sha256_value(value: object, label: str) -> str:
    digest = _required_string(value, label)
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise T12StageError(f"{label} is not a SHA-256 digest")
    return digest


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise T12StageError(f"{label} must be a non-empty list")
    strings = tuple(_required_string(item, label) for item in value)
    if len(set(strings)) != len(strings):
        raise T12StageError(f"{label} contains duplicates")
    return strings


def _read_approved_seed_rows(
    path: Path, *, allow_empty: bool = False
) -> dict[str, dict[str, str]]:
    required = {
        "seed_solution_id",
        "search_model",
        "search_model_sha256",
        "expected_copy_count",
        "requires_additional_copy",
    }
    try:
        with _regular(path, "approved seed table").open(
            encoding="utf-8", newline=""
        ) as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise T12StageError("approved seed table has an invalid header")
            rows = [dict(row) for row in reader]
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise T12StageError(f"cannot read approved seed table: {path}") from error
    if not rows and not allow_empty:
        raise T12StageError("approved seed table is empty")
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        seed = row.get("seed_solution_id", "")
        if not seed or seed in indexed:
            raise T12StageError("approved seed table has an invalid or duplicate ID")
        indexed[seed] = row
    return indexed


def _result_assets(
    result_path: Path,
    result: AdditionalCopyResult,
) -> tuple[Path, str, Path, str] | None:
    values = (
        result.output_coordinate_path,
        result.output_coordinate_sha256,
        result.output_mtz_path,
        result.output_mtz_sha256,
    )
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise T12StageError(
            f"additional-copy result has a partial asset inventory: {result.attempt_id}"
        )
    coordinate = _owned_regular(
        result_path.parent,
        cast(str, result.output_coordinate_path),
        "additional-copy coordinate",
    )
    result_mtz = _owned_regular(
        result_path.parent,
        cast(str, result.output_mtz_path),
        "additional-copy MTZ",
    )
    coordinate_sha = cast(str, result.output_coordinate_sha256)
    result_mtz_sha = cast(str, result.output_mtz_sha256)
    if (
        sha256_file(coordinate) != coordinate_sha
        or sha256_file(result_mtz) != result_mtz_sha
    ):
        raise T12StageError(
            f"additional-copy asset checksum mismatch: {result.attempt_id}"
        )
    return coordinate, coordinate_sha, result_mtz, result_mtz_sha


def _load_copy_series(
    root_path: Path,
    *,
    seed_solution_id: str,
    review_id: str,
    hypothesis: MrHypothesis,
) -> _CopySeries:
    root = _directory(root_path, "additional-copy result bundle")
    summary_path = _regular(
        root / "additional_copy_series_summary.json", "copy-series summary"
    )
    aggregate_path = _regular(
        root / "additional_copy_series_results.jsonl", "copy-series aggregate"
    )
    summary = _load_object(summary_path, "copy-series summary")
    raw_paths = summary.get("result_paths")
    raw_sha256 = summary.get("result_sha256")
    if (
        not isinstance(raw_paths, list)
        or not raw_paths
        or not isinstance(raw_sha256, list)
        or len(raw_paths) != len(raw_sha256)
    ):
        raise T12StageError("copy-series summary has an invalid result inventory")

    result_paths: list[Path] = []
    results: list[AdditionalCopyResult] = []
    for index, (relative, expected_sha) in enumerate(
        zip(raw_paths, raw_sha256, strict=True), start=1
    ):
        result_path = _owned_regular(root, relative, "copy-series result")
        if sha256_file(result_path) != _sha256_value(
            expected_sha, "copy-series result checksum"
        ):
            raise T12StageError(f"copy-series result checksum mismatch at item {index}")
        records = _read_jsonl(
            result_path, AdditionalCopyResult, "additional-copy result"
        )
        if len(records) != 1:
            raise T12StageError("each copy-series result file must contain one record")
        result_paths.append(result_path)
        results.append(records[0])

    aggregate = _read_jsonl(
        aggregate_path, AdditionalCopyResult, "copy-series aggregate"
    )
    if aggregate != tuple(results):
        raise T12StageError("copy-series aggregate differs from its result inventory")

    retained_state: _SupportedState | None = None
    previous: AdditionalCopyResult | None = None
    for index, (result, result_path) in enumerate(
        zip(results, result_paths, strict=True)
    ):
        if (
            result.review_id != review_id
            or result.seed_solution_id != seed_solution_id
            or result.hypothesis_id != hypothesis.hypothesis_id
            or result.sequence_group_id != hypothesis.sequence_group_id
            or result.expected_copy_count != hypothesis.copy_count_expected
            or result.attempted_copy_number > hypothesis.copy_count_expected
        ):
            raise T12StageError(
                f"copy-series identity differs from approved seed: {seed_solution_id}"
            )
        _owned_regular(
            result_path.parent, result.raw_log_pointer, "additional-copy log"
        )
        _owned_regular(
            result_path.parent, result.command_pointer, "additional-copy command"
        )
        expected_parent_id = (
            seed_solution_id if previous is None else previous.child_solution_id
        )
        expected_parent_count = (
            1 if previous is None else previous.attempted_copy_number
        )
        if (
            expected_parent_id is None
            or result.parent_solution_id != expected_parent_id
            or result.parent_copy_count != expected_parent_count
            or (previous is not None and not previous.additional_copy_supported)
        ):
            raise T12StageError(
                f"copy-series parent-child lineage is invalid: {seed_solution_id}"
            )
        assets = _result_assets(result_path, result)
        if result.additional_copy_supported:
            if (
                result.execution_status is not ExecutionStatus.COMPLETED_HIT
                or assets is None
            ):
                raise T12StageError(
                    "supported addition lacks completed child evidence: "
                    f"{result.attempt_id}"
                )
            coordinate, coordinate_sha, result_mtz, result_mtz_sha = assets
            retained_state = _SupportedState(
                solution_id=cast(str, result.child_solution_id),
                copy_count=result.best_supported_copy_count,
                coordinate=coordinate,
                coordinate_sha256=coordinate_sha,
                solution_mtz=result_mtz,
                solution_mtz_sha256=result_mtz_sha,
                source_kind="supported_additional_copy",
            )
        elif index != len(results) - 1:
            raise T12StageError(
                "an unsupported addition must terminate its copy series"
            )
        previous = result

    final = results[-1]
    stop_reason = _required_string(
        summary.get("stop_reason"), "copy-series stop reason"
    )
    reached_expected = final.best_supported_copy_count == final.expected_copy_count
    expected_stop = (
        "expected_copy_count_reached"
        if final.additional_copy_supported and reached_expected
        else "additional_copy_not_supported"
    )
    if (
        stop_reason != expected_stop
        or summary.get("seed_solution_id") != seed_solution_id
        or summary.get("attempt_count") != len(results)
        or summary.get("attempt_ids") != [item.attempt_id for item in results]
        or summary.get("attempted_copy_numbers")
        != [item.attempted_copy_number for item in results]
        or summary.get("expected_copy_count") != hypothesis.copy_count_expected
        or summary.get("best_supported_copy_count") != final.best_supported_copy_count
        or summary.get("reached_expected_copy_count") is not reached_expected
        or summary.get("parent_retained") is not True
        or summary.get("failed_addition_proves_absence") is not False
    ):
        raise T12StageError(f"copy-series summary is inconsistent: {seed_solution_id}")
    return _CopySeries(
        root=root,
        results=tuple(results),
        result_paths=tuple(result_paths),
        summary=summary_path,
        aggregate=aggregate_path,
        stop_reason=stop_reason,
        retained_state=retained_state,
    )


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
        "parent_mtz_sha256\tresolution\tobservation_labels"
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
                    str(selected_preflight.selected_observation_labels),
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


def stage_live_t12_inputs(request: LiveT12StageRequest) -> LiveT12StageOutput:
    """Retain every approved seed's best supported state and stage live T12.

    Typed tool or parse failures end only their candidate's copy series.  The
    last supported parent remains a finalist, and the stage explicitly records
    that a failed addition does not prove absence.  Missing result bundles are
    infrastructure failures and therefore fail the boundary instead of being
    converted into a scientific no-addition outcome.
    """

    approved_root = _directory(request.approved_stage, "approved M4 stage")
    output_path = request.output_directory
    if output_path.is_symlink() or output_path.exists():
        raise T12StageError(f"live T12 stage output already exists: {output_path}")
    output = output_path.absolute()
    output.mkdir(parents=True)

    validation_path: Path | None = None
    decisions_path: Path | None = None
    if request.phase3_seed_stage_manifest is None:
        if request.review_package is None:
            raise T12StageError("legacy live T12 requires its MR review package")
        review_root = _directory(request.review_package, "MR review package")
        approved_manifest_path = _regular(
            approved_root / "live_m4_stage_manifest.json", "live M4 stage manifest"
        )
        approved_manifest = _load_object(
            approved_manifest_path, "live M4 stage manifest"
        )
        if (
            approved_manifest.get("stage_kind") != "normal_workflow_post_mr_seed"
            or approved_manifest.get("all_approved_seeds_retained") is not True
            or approved_manifest.get("numeric_score_filter_applied") is not False
            or approved_manifest.get("execution_status")
            != ExecutionStatus.COMPLETED_SUCCESS.value
        ):
            raise T12StageError("live M4 stage is not accepted retain-all evidence")
        approved_ids = _string_list(
            approved_manifest.get("approved_solution_ids"), "approved solution IDs"
        )
        approved_seeds_path = _regular(
            approved_root / "approved_seeds.tsv", "approved seed table"
        )
        additional_seeds_path = _regular(
            approved_root / "additional_copy_seeds.tsv", "additional-copy seed table"
        )
        validation_path = _regular(
            approved_root / "validated_mr_seed_decisions.json",
            "MR decision validation",
        )
        decisions_path = _regular(
            approved_root / "approved_mr_seeds.tsv", "MR seed decisions"
        )
        if (
            sha256_file(approved_seeds_path)
            != approved_manifest.get("approved_seeds_sha256")
            or sha256_file(additional_seeds_path)
            != approved_manifest.get("additional_copy_seeds_sha256")
            or sha256_file(validation_path)
            != approved_manifest.get("validation_sha256")
            or sha256_file(decisions_path)
            != approved_manifest.get("decisions_sha256")
        ):
            raise T12StageError(
                "live M4 stage file checksum differs from its manifest"
            )
        validation = _load_object(validation_path, "MR decision validation")
        review_id = _required_string(validation.get("review_id"), "MR review ID")
        if (
            validation.get("execution_status")
            != ExecutionStatus.COMPLETED_SUCCESS.value
            or validation.get("checkpoint") != "mr_seed"
            or validation.get("approved_solution_ids") != list(approved_ids)
            or approved_manifest.get("review_id") != review_id
        ):
            raise T12StageError(
                "MR decision validation differs from the live M4 stage"
            )
        review_manifest_path = _regular(
            review_root / "mr_seed_review_manifest.json", "MR review manifest"
        )
        review_manifest_sha = sha256_file(review_manifest_path)
        review_manifest = _load_object(review_manifest_path, "MR review manifest")
        if (
            review_manifest_sha != approved_manifest.get("review_manifest_sha256")
            or review_manifest_sha != validation.get("package_manifest_sha256")
            or review_manifest.get("package_id")
            != approved_manifest.get("review_package_id")
            or review_manifest.get("package_id") != validation.get("package_id")
        ):
            raise T12StageError(
                "MR review package differs from the approved live stage"
            )
    else:
        from genome_to_diffraction.mr.stage_add_copy import (
            validate_phase3_seed_stage,
        )

        if request.review_package is not None:
            raise T12StageError("Phase III live T12 rejects a legacy review package")
        try:
            phase3 = validate_phase3_seed_stage(
                request.phase3_seed_stage_manifest,
                hypotheses_jsonl=request.hypotheses_jsonl,
            )
        except (OSError, ValueError) as error:
            raise T12StageError(f"Phase III seed stage is invalid: {error}") from error
        if phase3.root != approved_root:
            raise T12StageError("Phase III seed-stage manifest belongs to another root")
        approved_manifest_path = request.phase3_seed_stage_manifest.resolve(strict=True)
        approved_manifest = _load_object(
            approved_manifest_path, "Phase III seed-stage manifest"
        )
        approved_ids = phase3.approved_solution_ids
        if not approved_ids:
            raise T12StageError("Phase III live T12 has no approved A seed")
        approved_seeds_path = _regular(
            approved_root / "approved_seeds.tsv", "approved seed table"
        )
        additional_seeds_path = _regular(
            approved_root / "additional_copy_seeds.tsv", "additional-copy seed table"
        )
        review_root = phase3.review_root
        review_manifest_path = phase3.review_manifest
        review_manifest_sha = sha256_file(review_manifest_path)
        review_manifest = phase3.review_document
        review_id = phase3.review_id

    if approved_manifest.get("approved_seed_count") != len(approved_ids):
        raise T12StageError("live M4 approved seed count is inconsistent")
    approved_rows = _read_approved_seed_rows(approved_seeds_path)
    additional_rows = _read_approved_seed_rows(additional_seeds_path, allow_empty=True)
    if set(approved_rows) != set(approved_ids):
        raise T12StageError("approved seed table identities differ from the stage")
    raw_items = review_manifest.get("items")
    if not isinstance(raw_items, list):
        raise T12StageError("MR review manifest has no item inventory")
    review_items: dict[str, dict[str, object]] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        solution_id = raw_item.get("solution_id")
        if isinstance(solution_id, str):
            if solution_id in review_items:
                raise T12StageError("MR review manifest contains duplicate solutions")
            review_items[solution_id] = cast(dict[str, object], raw_item)

    hypotheses_path = _regular(request.hypotheses_jsonl, "MR hypotheses")
    if sha256_file(hypotheses_path) != approved_manifest.get("hypotheses_sha256"):
        raise T12StageError("MR hypotheses differ from the approved live stage")
    hypotheses_records = _read_jsonl(hypotheses_path, MrHypothesis, "MR hypothesis")
    hypotheses = {item.hypothesis_id: item for item in hypotheses_records}
    if len(hypotheses) != len(hypotheses_records):
        raise T12StageError("MR hypotheses contain duplicate identities")
    raw_model_sources = approved_manifest.get("model_sources")
    if not isinstance(raw_model_sources, dict) or set(raw_model_sources) != set(
        approved_ids
    ):
        raise T12StageError("live M4 model-source identities are inconsistent")

    seed_inputs: dict[str, tuple[MrHypothesis, _SupportedState, dict[str, object]]] = {}
    required_additional_ids: set[str] = set()
    for seed_id in approved_ids:
        raw_source = raw_model_sources.get(seed_id)
        item = review_items.get(seed_id)
        row = approved_rows[seed_id]
        if not isinstance(raw_source, dict) or item is None:
            raise T12StageError(f"approved seed provenance is absent: {seed_id}")
        source = cast(dict[str, object], raw_source)
        hypothesis_id = _required_string(
            source.get("hypothesis_id"), "approved hypothesis ID"
        )
        hypothesis = hypotheses.get(hypothesis_id)
        if hypothesis is None:
            raise T12StageError(f"approved hypothesis is absent: {hypothesis_id}")
        expected_count = source.get("expected_copy_count")
        requires_additional = source.get("requires_additional_copy")
        if (
            item.get("hypothesis_id") != hypothesis.hypothesis_id
            or item.get("sequence_group_id") != hypothesis.sequence_group_id
            or source.get("sequence_group_id") != hypothesis.sequence_group_id
            or expected_count != hypothesis.copy_count_expected
            or requires_additional is not (hypothesis.copy_count_expected > 1)
            or row.get("expected_copy_count") != str(hypothesis.copy_count_expected)
            or row.get("requires_additional_copy")
            != str(hypothesis.copy_count_expected > 1).lower()
        ):
            raise T12StageError(f"approved seed metadata is inconsistent: {seed_id}")
        staged_model_sha = _sha256_value(
            source.get("staged_search_model_sha256"), "staged search-model checksum"
        )
        staged_model = _owned_regular(
            approved_root, source.get("staged_search_model"), "staged search model"
        )
        if (
            sha256_file(staged_model) != staged_model_sha
            or row.get("search_model_sha256") != staged_model_sha
        ):
            raise T12StageError(f"staged search-model checksum mismatch: {seed_id}")
        _sha256_value(
            source.get("original_first_copy_model_sha256"),
            "original first-copy model checksum",
        )
        copied = item.get("copied_assets")
        copied_sha = item.get("copied_asset_sha256")
        if not isinstance(copied, dict) or not isinstance(copied_sha, dict):
            raise T12StageError(f"approved review assets are absent: {seed_id}")
        coordinate = _owned_regular(
            review_root,
            copied.get("solution_coordinate"),
            "first-copy solution coordinate",
        )
        solution_mtz = _owned_regular(
            review_root, copied.get("output_mtz"), "first-copy solution MTZ"
        )
        coordinate_sha = _sha256_value(
            copied_sha.get("solution_coordinate"),
            "first-copy solution-coordinate checksum",
        )
        solution_mtz_sha = _sha256_value(
            copied_sha.get("output_mtz"), "first-copy solution-MTZ checksum"
        )
        if (
            source.get("source_solution_coordinate")
            != copied.get("solution_coordinate")
            or coordinate_sha != staged_model_sha
            or sha256_file(coordinate) != coordinate_sha
            or sha256_file(solution_mtz) != solution_mtz_sha
        ):
            raise T12StageError(f"first-copy review asset checksum mismatch: {seed_id}")
        root_state = _SupportedState(
            solution_id=seed_id,
            copy_count=1,
            coordinate=coordinate,
            coordinate_sha256=coordinate_sha,
            solution_mtz=solution_mtz,
            solution_mtz_sha256=solution_mtz_sha,
            source_kind="first_copy_review_solution",
        )
        seed_inputs[seed_id] = (hypothesis, root_state, source)
        if hypothesis.copy_count_expected > 1:
            required_additional_ids.add(seed_id)

    if set(additional_rows) != required_additional_ids:
        raise T12StageError(
            "additional-copy seed identities differ from approved expected counts"
        )
    if approved_manifest.get("additional_copy_seed_count") != len(
        required_additional_ids
    ):
        raise T12StageError("live M4 additional-copy seed count is inconsistent")

    result_roots: dict[str, Path] = {}
    for raw_root in request.additional_copy_results:
        root = _directory(raw_root, "additional-copy result bundle")
        summary = _load_object(
            _regular(
                root / "additional_copy_series_summary.json", "copy-series summary"
            ),
            "copy-series summary",
        )
        seed_id = _required_string(
            summary.get("seed_solution_id"), "copy-series seed solution ID"
        )
        if seed_id in result_roots:
            raise T12StageError(f"duplicate additional-copy result: {seed_id}")
        result_roots[seed_id] = root
    if set(result_roots) != required_additional_ids:
        raise T12StageError(
            "typed additional-copy result bundles do not cover every required seed"
        )

    sequence_groups_source = _regular(request.sequence_groups_jsonl, "sequence groups")
    source_records_source = _regular(
        request.source_records_jsonl, "catalogue source-record crosswalk"
    )
    preflight_source = _regular(request.preflight_jsonl, "MTZ preflight")
    phenix_source = _regular(request.phenix_manifest, "Phenix manifest")
    diffraction_source = _regular(request.diffraction_mtz, "diffraction MTZ")
    groups = _read_jsonl(sequence_groups_source, SequenceGroupRecord, "sequence group")
    sources = _read_jsonl(source_records_source, SourceProteinRecord, "source record")
    preflights = _read_jsonl(preflight_source, MtzPreflightRecord, "MTZ preflight")
    group_ids = {group.sequence_group_id for group in groups}
    source_group_ids = {source.sequence_group_id for source in sources}
    candidate_group_ids = {
        hypothesis.sequence_group_id for hypothesis, _, _ in seed_inputs.values()
    }
    if source_group_ids != group_ids or not candidate_group_ids.issubset(group_ids):
        raise T12StageError(
            "source-record crosswalk, sequence groups, and finalists differ"
        )
    diffraction_sha = sha256_file(diffraction_source)
    matching_preflights = tuple(
        record for record in preflights if record.mtz_sha256 == diffraction_sha
    )
    if len(matching_preflights) != 1:
        raise T12StageError(
            "live T12 requires exactly one preflight matching the diffraction MTZ"
        )
    selected_preflight = matching_preflights[0]
    if (
        selected_preflight.free_flag_status == "missing"
        or selected_preflight.selected_observation_labels is None
    ):
        raise T12StageError("live T12 refinement requires labelled FreeR observations")
    for hypothesis, _, _ in seed_inputs.values():
        if (
            hypothesis.crystal_id != selected_preflight.crystal_id
            or hypothesis.obs_labels != selected_preflight.selected_observation_labels
        ):
            raise T12StageError("approved hypothesis differs from the MTZ preflight")

    inputs = output / "inputs"
    _atomic_copy(sequence_groups_source, inputs / "sequence_groups.jsonl")
    _atomic_copy(source_records_source, inputs / "source_records.jsonl")
    _atomic_copy(preflight_source, inputs / "preflight.jsonl")
    _atomic_copy(phenix_source, inputs / "phenix_manifest.json")
    diffraction_mtz = inputs / "diffraction.mtz"
    _atomic_copy(diffraction_source, diffraction_mtz)

    finalist_rows = [
        "seed_solution_id\tsequence_group_id\tinput_copy_count\t"
        "parent_coordinate\tparent_coordinate_sha256\tparent_mtz\t"
        "parent_mtz_sha256\tresolution\tobservation_labels"
    ]
    report_rows = [
        "seed_solution_id\thypothesis_id\tsequence_group_id\t"
        "expected_copy_count\tattempted_transition_count\t"
        "attempted_copy_numbers\tbest_supported_copy_count\t"
        "reached_expected_copy_count\tterminal_reason\t"
        "final_addition_execution_status\tfinal_llg\tfinal_tfz\t"
        "final_llg_delta_from_parent\tfinal_top_solution_packed\t"
        "final_placement_count\tparent_retained\t"
        "failed_addition_proves_absence"
    ]
    report_markdown_rows = [
        "| Seed | Expected | Attempts | Best supported | Terminal reason |",
        "|---|---:|---:|---:|---|",
    ]
    candidate_documents: list[dict[str, object]] = []
    iterator = tqdm(
        approved_ids,
        desc="Stage live T12 parents",
        unit="candidate",
        disable=not request.progress,
    )
    for seed_id in iterator:
        hypothesis, root_state, model_source = seed_inputs[seed_id]
        series: _CopySeries | None = None
        retained = root_state
        if hypothesis.copy_count_expected > 1:
            series = _load_copy_series(
                result_roots[seed_id],
                seed_solution_id=seed_id,
                review_id=review_id,
                hypothesis=hypothesis,
            )
            if series.retained_state is not None:
                retained = series.retained_state

        candidate_out = output / "parents" / seed_id
        coordinate_out = candidate_out / "parent.pdb"
        solution_mtz_out = candidate_out / "phaser_solution.mtz"
        _atomic_copy(retained.coordinate, coordinate_out)
        _atomic_copy(retained.solution_mtz, solution_mtz_out)
        if (
            sha256_file(coordinate_out) != retained.coordinate_sha256
            or sha256_file(solution_mtz_out) != retained.solution_mtz_sha256
        ):
            raise T12StageError(f"staged retained-parent checksum failed: {seed_id}")

        final_result = series.results[-1] if series is not None else None
        if final_result is None:
            terminal_reason = "already_at_expected_copy_count"
            attempted_numbers: list[int] = []
            reached_expected = True
        else:
            if series is None:
                raise AssertionError("final copy result lacks its series")
            terminal_reason = series.stop_reason
            attempted_numbers = [
                result.attempted_copy_number for result in series.results
            ]
            reached_expected = retained.copy_count == hypothesis.copy_count_expected
            if retained.copy_count != final_result.best_supported_copy_count:
                raise T12StageError(
                    f"retained state differs from typed copy result: {seed_id}"
                )

        finalist_rows.append(
            "\t".join(
                (
                    seed_id,
                    hypothesis.sequence_group_id,
                    str(retained.copy_count),
                    str(coordinate_out),
                    retained.coordinate_sha256,
                    str(diffraction_mtz),
                    diffraction_sha,
                    str(selected_preflight.resolution_high_a),
                    selected_preflight.selected_observation_labels,
                )
            )
        )
        report_rows.append(
            "\t".join(
                (
                    seed_id,
                    hypothesis.hypothesis_id,
                    hypothesis.sequence_group_id,
                    str(hypothesis.copy_count_expected),
                    str(len(attempted_numbers)),
                    ",".join(str(number) for number in attempted_numbers),
                    str(retained.copy_count),
                    str(reached_expected).lower(),
                    terminal_reason,
                    (
                        final_result.execution_status.value
                        if final_result is not None
                        else "not_attempted"
                    ),
                    (
                        str(final_result.llg)
                        if final_result is not None and final_result.llg is not None
                        else ""
                    ),
                    (
                        str(final_result.tfz)
                        if final_result is not None and final_result.tfz is not None
                        else ""
                    ),
                    str(
                        final_result.llg_delta_from_parent
                        if final_result is not None
                        and final_result.llg_delta_from_parent is not None
                        else ""
                    ),
                    str(
                        final_result.top_solution_packed
                        if final_result is not None
                        else ""
                    ).lower(),
                    str(
                        final_result.phaser_placement_count
                        if final_result is not None
                        else ""
                    ),
                    "true",
                    "false",
                )
            )
        )
        report_markdown_rows.append(
            f"| `{seed_id}` | {hypothesis.copy_count_expected} | "
            f"{len(attempted_numbers)} | {retained.copy_count} | "
            f"{terminal_reason} |"
        )

        attempt_documents: list[dict[str, object]] = []
        if series is not None:
            for result, result_path in zip(
                series.results, series.result_paths, strict=True
            ):
                raw_log = _owned_regular(
                    result_path.parent,
                    result.raw_log_pointer,
                    "additional-copy log",
                )
                command = _owned_regular(
                    result_path.parent,
                    result.command_pointer,
                    "additional-copy command",
                )
                attempt_documents.append(
                    {
                        **result.model_dump(mode="json"),
                        "result_record": result_path.relative_to(
                            series.root
                        ).as_posix(),
                        "result_record_sha256": sha256_file(result_path),
                        "raw_log_sha256": sha256_file(raw_log),
                        "command_sha256": sha256_file(command),
                    }
                )
        if retained.source_kind == "first_copy_review_solution":
            source_coordinate = retained.coordinate.relative_to(review_root).as_posix()
            source_solution_mtz = retained.solution_mtz.relative_to(
                review_root
            ).as_posix()
            source_bundle = "mr_seed_review"
        else:
            if series is None:
                raise AssertionError("additional-copy state lacks its series")
            source_coordinate = retained.coordinate.relative_to(series.root).as_posix()
            source_solution_mtz = retained.solution_mtz.relative_to(
                series.root
            ).as_posix()
            source_bundle = series.root.name
        candidate_documents.append(
            {
                "seed_solution_id": seed_id,
                "hypothesis_id": hypothesis.hypothesis_id,
                "sequence_group_id": hypothesis.sequence_group_id,
                "expected_copy_count": hypothesis.copy_count_expected,
                "attempted_transition_count": len(attempted_numbers),
                "attempted_copy_numbers": attempted_numbers,
                "best_supported_copy_count": retained.copy_count,
                "reached_expected_copy_count": reached_expected,
                "terminal_reason": terminal_reason,
                "final_addition_execution_status": (
                    final_result.execution_status.value
                    if final_result is not None
                    else None
                ),
                "retained_solution_id": retained.solution_id,
                "retained_state_source": retained.source_kind,
                "source_bundle": source_bundle,
                "source_coordinate": source_coordinate,
                "source_coordinate_sha256": retained.coordinate_sha256,
                "source_solution_mtz": source_solution_mtz,
                "source_solution_mtz_sha256": retained.solution_mtz_sha256,
                "staged_parent_coordinate": coordinate_out.relative_to(
                    output
                ).as_posix(),
                "staged_solution_mtz": solution_mtz_out.relative_to(output).as_posix(),
                "refinement_mtz": diffraction_mtz.relative_to(output).as_posix(),
                "refinement_mtz_sha256": diffraction_sha,
                "parent_retained": True,
                "failed_addition_proves_absence": False,
                "original_first_copy_model_sha256": model_source[
                    "original_first_copy_model_sha256"
                ],
                "staged_search_model_sha256": model_source[
                    "staged_search_model_sha256"
                ],
                "copy_series_summary_sha256": (
                    sha256_file(series.summary) if series is not None else None
                ),
                "copy_series_aggregate_sha256": (
                    sha256_file(series.aggregate) if series is not None else None
                ),
                "attempts": attempt_documents,
            }
        )

    finalists = output / "finalists.tsv"
    copy_report_tsv = output / "copy_count_report.tsv"
    copy_report_markdown = output / "copy_count_report.md"
    atomic_write_text(finalists, "\n".join(finalist_rows) + "\n")
    atomic_write_text(copy_report_tsv, "\n".join(report_rows) + "\n")
    atomic_write_text(
        copy_report_markdown,
        "# Same-component copy-count report\n\n"
        "Every explicitly approved seed is retained. A failed or unsupported "
        "addition does not prove that the copy is absent.\n\n"
        + "\n".join(report_markdown_rows)
        + "\n",
    )

    stage_identity = {
        "approved_stage_manifest_sha256": sha256_file(approved_manifest_path),
        "review_manifest_sha256": review_manifest_sha,
        "hypotheses_sha256": sha256_file(hypotheses_path),
        "sequence_groups_sha256": sha256_file(sequence_groups_source),
        "source_records_sha256": sha256_file(source_records_source),
        "preflight_sha256": sha256_file(preflight_source),
        "phenix_manifest_sha256": sha256_file(phenix_source),
        "diffraction_mtz_sha256": diffraction_sha,
        "retained_states": [
            {
                "seed_solution_id": item["seed_solution_id"],
                "best_supported_copy_count": item["best_supported_copy_count"],
                "source_coordinate_sha256": item["source_coordinate_sha256"],
                "source_solution_mtz_sha256": item["source_solution_mtz_sha256"],
                "copy_series_summary_sha256": item["copy_series_summary_sha256"],
                "copy_series_aggregate_sha256": item["copy_series_aggregate_sha256"],
            }
            for item in candidate_documents
        ],
    }
    if request.phase3_seed_stage_manifest is None:
        assert decisions_path is not None
        assert validation_path is not None
        approval_identity = {
            "approved_decisions_sha256": sha256_file(decisions_path),
            "approved_validation_sha256": sha256_file(validation_path),
        }
        schema_version = "1.0"
        profile = "normal_workflow"
    else:
        approval_identity = {
            "phase3_seed_stage_id": approved_manifest.get("stage_id"),
            "phase3_decision_file_id": review_id,
        }
        schema_version = "2.0"
        profile = "phase3_reviewed_single_component"
    manifest = output / "t12_stage_manifest.json"
    atomic_write_json(
        manifest,
        {
            "schema_version": schema_version,
            "stage_id": content_id("t12stage_", stage_identity),
            "profile": profile,
            "selection_policy": "retain_all_best_checksum_authenticated_copy_states",
            "review_id": review_id,
            "seed_count": len(candidate_documents),
            "all_approved_seeds_retained": True,
            "numeric_score_filter_applied": False,
            "failed_addition_proves_absence": False,
            **stage_identity,
            **approval_identity,
            "diffraction_mtz_free_flag_status": selected_preflight.free_flag_status,
            "observation_labels": selected_preflight.selected_observation_labels,
            "resolution_high_a": selected_preflight.resolution_high_a,
            "finalists_sha256": sha256_file(finalists),
            "copy_report_tsv_sha256": sha256_file(copy_report_tsv),
            "copy_report_markdown_sha256": sha256_file(copy_report_markdown),
            "candidates": candidate_documents,
            "execution_status": ExecutionStatus.COMPLETED_SUCCESS.value,
        },
    )
    _LOGGER.info(
        "normal-workflow T12 inputs staged",
        extra={
            "review_id": review_id,
            "seed_count": len(candidate_documents),
            "manifest": str(manifest),
        },
    )
    return LiveT12StageOutput(
        manifest=manifest,
        finalists=finalists,
        copy_report_tsv=copy_report_tsv,
        copy_report_markdown=copy_report_markdown,
        seed_count=len(candidate_documents),
    )
