"""Place one additional same-component copy while retaining the fixed parent.

The adapter consumes an explicitly approved first-copy review seed, its original
typed hypothesis and exact catalogue sequence, the checksum-matched search model,
MTZ preflight, and a verified Phenix manifest. It writes a PHIL parameter file,
runs ``phenix.phaser`` with the approved coordinates fixed at the origin, and
searches exactly one additional copy. A parsed but unpacked or absent addition
retains the parent as best state and never proves that another copy is absent.

The cache identity is the review/seed identity plus parent, model, sequence, MTZ,
Phenix-manifest, and command-policy checksums. Unit tests cover command assembly,
packed/no-solution semantics, and checksum failures; real-runtime qualification is
required before this operation may be called integrated.
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from pydantic import ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.mr.phaser import (
    PhaserInputError,
    PhaserParseError,
    parse_phaser_log,
)
from genome_to_diffraction.phenix.runtime import (
    capture_from_manifest,
    validate_manifest_environment,
)
from genome_to_diffraction.schemas.results import (
    AdditionalCopyResult,
    MrHypothesis,
    MtzPreflightRecord,
    NormalisedMrResult,
    PreflightDecision,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import ExecutionStatus
from genome_to_diffraction.time import utc_now_iso

_LOGGER = logging.getLogger("genome_to_diffraction.mr.add_copy")
_ADAPTER_VERSION = "phenix-add-copy-mr-v1"
_ROOT = "PHASER"
_PLACEMENT = re.compile(r"^REMARK ENSEMBLE\s+", re.M)


@dataclass(frozen=True)
class AddCopyRunRequest:
    """Immutable inputs for one approved fixed-parent additional-copy search."""

    review_validation_json: Path
    review_package_manifest: Path
    seed_solution_id: str
    hypotheses_jsonl: Path
    sequence_groups_jsonl: Path
    preflight_jsonl: Path
    mtz: Path
    search_model: Path
    phenix_manifest: Path
    output_directory: Path
    expected_search_model_sha256: str | None = None
    parent_result_jsonl: Path | None = None
    parent_coordinate: Path | None = None
    threads: int = 1
    timeout_seconds: float | None = None
    progress: bool = True


@dataclass(frozen=True)
class AddCopyRunOutput:
    """Typed result and retained files from one additional-copy attempt."""

    result: AdditionalCopyResult
    result_json: Path
    result_jsonl: Path
    command_json: Path
    parameters_file: Path


@dataclass(frozen=True)
class AddCopySeriesOutput:
    """Retained one-copy-at-a-time attempts for one approved seed."""

    attempts: tuple[AddCopyRunOutput, ...]
    results_jsonl: Path
    summary_json: Path


@dataclass(frozen=True)
class _Resolved:
    review_id: str
    hypothesis: MrHypothesis
    group: SequenceGroupRecord
    parent_coordinate: Path
    parent_coordinate_sha256: str
    parent_solution_id: str
    parent_copy_count: int
    parent_result_sha256: str
    parent_llg: float | None
    search_model: Path
    search_model_sha256: str
    original_first_copy_model_sha256: str
    model_identity_fraction: float
    mtz: Path
    mtz_sha256: str


def _json_object(path: Path, *, label: str) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    try:
        document: object = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PhaserInputError(f"cannot load {label}: {resolved}") from error
    if not isinstance(document, dict):
        raise PhaserInputError(f"{label} must be a JSON object")
    return cast(dict[str, object], document)


def _jsonl_records[T](path: Path, model: type[T], *, label: str) -> tuple[T, ...]:
    records: list[T] = []
    resolved = path.resolve(strict=True)
    with resolved.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(model.model_validate_json(line))  # type: ignore[attr-defined]
            except ValidationError as error:
                raise PhaserInputError(
                    f"invalid {label} record at line {line_number}: {resolved}"
                ) from error
    if not records:
        raise PhaserInputError(f"{label} input is empty: {resolved}")
    return tuple(records)


def _one[T](records: tuple[T, ...], identifier: str, attribute: str, label: str) -> T:
    matches = [item for item in records if getattr(item, attribute) == identifier]
    if len(matches) != 1:
        raise PhaserInputError(
            f"expected exactly one {label} {identifier!r}; observed {len(matches)}"
        )
    return matches[0]


def _owned(root: Path, relative: object, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise PhaserInputError(f"invalid {label} path")
    candidate = root.joinpath(relative)
    if candidate.is_symlink():
        raise PhaserInputError(f"{label} must not be a symlink")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(root.resolve(strict=True)):
        raise PhaserInputError(f"{label} escapes the review package")
    return resolved


def _resolve(request: AddCopyRunRequest) -> _Resolved:
    validation = _json_object(request.review_validation_json, label="MR approval")
    manifest_path = request.review_package_manifest.resolve(strict=True)
    manifest = _json_object(manifest_path, label="MR review manifest")
    if (
        validation.get("execution_status") != ExecutionStatus.COMPLETED_SUCCESS.value
        or validation.get("checkpoint") != "mr_seed"
        or validation.get("package_id") != manifest.get("package_id")
        or validation.get("package_manifest_sha256") != sha256_file(manifest_path)
    ):
        raise PhaserInputError("MR approval does not match the review package")
    approved = validation.get("approved_solution_ids")
    review_id = validation.get("review_id")
    if (
        not isinstance(approved, list)
        or request.seed_solution_id not in approved
        or not isinstance(review_id, str)
    ):
        raise PhaserInputError("seed is not explicitly approved for M4")
    raw_items = manifest.get("items")
    if not isinstance(raw_items, list):
        raise PhaserInputError("MR review manifest has no items")
    matches = [
        cast(dict[str, object], item)
        for item in raw_items
        if isinstance(item, dict)
        and item.get("solution_id") == request.seed_solution_id
    ]
    if len(matches) != 1:
        raise PhaserInputError("approved seed is not unique in the review package")
    item = matches[0]
    copied = item.get("copied_assets")
    copied_sha = item.get("copied_asset_sha256")
    if not isinstance(copied, dict) or not isinstance(copied_sha, dict):
        raise PhaserInputError("approved seed lacks an asset inventory")
    root = manifest_path.parent
    root_parent = _owned(
        root, copied.get("solution_coordinate"), label="root parent coordinate"
    )
    root_parent_sha = sha256_file(
        root_parent, progress=request.progress, logger=_LOGGER
    )
    if root_parent_sha != copied_sha.get("solution_coordinate"):
        raise PhaserInputError(
            "root parent coordinate checksum differs from review package"
        )
    root_result_path = _owned(
        root, copied.get("normalised_result"), label="parent normalised result"
    )
    if sha256_file(root_result_path) != copied_sha.get("normalised_result"):
        raise PhaserInputError(
            "root parent result checksum differs from review package"
        )
    root_results = _jsonl_records(
        root_result_path, NormalisedMrResult, label="root parent result"
    )
    if len(root_results) != 1:
        raise PhaserInputError("M4 root seed must have exactly one parent result")
    root_result = root_results[0]
    if root_result.execution_status not in {
        ExecutionStatus.COMPLETED_HIT,
        ExecutionStatus.COMPLETED_NO_HIT,
    }:
        raise PhaserInputError("M4 root seed must be a successfully parsed parent")
    if (
        root_result.placed_copy_count != 1
        or root_result.packing_summary.get("top_solution_packed") is not True
    ):
        raise PhaserInputError(
            "M4 root seed must contain exactly one packed placed copy"
        )
    parent = root_parent
    parent_sha = root_parent_sha
    parent_solution_id = request.seed_solution_id
    parent_copy_count = 1
    parent_result_sha = sha256_file(root_result_path)
    parent_llg = root_result.llg
    hypothesis_id = item.get("hypothesis_id")
    if not isinstance(hypothesis_id, str):
        raise PhaserInputError("review item lacks a hypothesis ID")
    hypotheses = _jsonl_records(
        request.hypotheses_jsonl, MrHypothesis, label="MR hypotheses"
    )
    hypothesis = _one(hypotheses, hypothesis_id, "hypothesis_id", "hypothesis")
    if (request.parent_result_jsonl is None) != (request.parent_coordinate is None):
        raise PhaserInputError(
            "sequential parent result and coordinate must be supplied together"
        )
    if request.parent_result_jsonl is not None:
        if request.parent_result_jsonl.is_symlink():
            raise PhaserInputError(
                "sequential parent result must be a regular non-symlink file"
            )
        sequential_result_path = request.parent_result_jsonl.resolve(strict=True)
        if not sequential_result_path.is_file():
            raise PhaserInputError(
                "sequential parent result must be a regular non-symlink file"
            )
        sequential_results = _jsonl_records(
            sequential_result_path,
            AdditionalCopyResult,
            label="sequential parent result",
        )
        if len(sequential_results) != 1:
            raise PhaserInputError(
                "sequential parent must have exactly one additional-copy result"
            )
        sequential = sequential_results[0]
        sequential_coordinate = cast(Path, request.parent_coordinate)
        parent = sequential_coordinate.resolve(strict=True)
        if sequential_coordinate.is_symlink() or not parent.is_file():
            raise PhaserInputError(
                "sequential parent coordinate must be a regular non-symlink file"
            )
        parent_sha = sha256_file(parent, progress=request.progress, logger=_LOGGER)
        if (
            not sequential.additional_copy_supported
            or sequential.execution_status is not ExecutionStatus.COMPLETED_HIT
            or sequential.review_id != review_id
            or sequential.seed_solution_id != request.seed_solution_id
            or sequential.hypothesis_id != hypothesis.hypothesis_id
            or sequential.sequence_group_id != hypothesis.sequence_group_id
            or sequential.expected_copy_count != hypothesis.copy_count_expected
            or sequential.child_solution_id is None
            or sequential.output_coordinate_sha256 != parent_sha
            or sequential.phaser_placement_count != sequential.attempted_copy_number
            or sequential.best_supported_copy_count != sequential.attempted_copy_number
        ):
            raise PhaserInputError(
                "sequential parent is not a supported child of the approved seed"
            )
        parent_solution_id = sequential.child_solution_id
        parent_copy_count = sequential.best_supported_copy_count
        parent_result_sha = sha256_file(sequential_result_path)
        parent_llg = sequential.llg
    if hypothesis.copy_count_expected <= parent_copy_count:
        raise PhaserInputError("approved seed has no expected additional copy")
    groups = _jsonl_records(
        request.sequence_groups_jsonl, SequenceGroupRecord, label="sequence groups"
    )
    group = _one(
        groups, hypothesis.sequence_group_id, "sequence_group_id", "sequence group"
    )
    preflights = _jsonl_records(
        request.preflight_jsonl, MtzPreflightRecord, label="MTZ preflights"
    )
    preflight = _one(preflights, hypothesis.crystal_id, "crystal_id", "preflight")
    if (
        preflight.decision is PreflightDecision.FAIL
        or hypothesis.obs_labels is None
        or preflight.selected_observation_labels != hypothesis.obs_labels
    ):
        raise PhaserInputError("approved seed does not match a usable MTZ preflight")
    mtz = request.mtz.resolve(strict=True)
    mtz_sha = sha256_file(mtz, progress=request.progress, logger=_LOGGER)
    if mtz_sha != preflight.mtz_sha256:
        raise PhaserInputError("MTZ checksum differs from preflight")
    command_path = _owned(root, copied.get("command"), label="parent command")
    if sha256_file(command_path) != copied_sha.get("command"):
        raise PhaserInputError("parent command checksum differs from review package")
    command = _json_object(command_path, label="parent command")
    expected_model_sha = command.get("model_sha256")
    identity_percent = command.get("model_identity_percent")
    if (
        not isinstance(expected_model_sha, str)
        or isinstance(identity_percent, bool)
        or not isinstance(identity_percent, (int, float))
        or not 0 < float(identity_percent) <= 100
    ):
        raise PhaserInputError("parent command lacks model provenance")
    search_model = request.search_model.resolve(strict=True)
    search_model_sha = sha256_file(
        search_model, progress=request.progress, logger=_LOGGER
    )
    staged_model_sha = request.expected_search_model_sha256 or expected_model_sha
    if not re.fullmatch(r"[0-9a-f]{64}", staged_model_sha):
        raise PhaserInputError("expected search model checksum is invalid")
    if search_model_sha != staged_model_sha:
        raise PhaserInputError("search model checksum differs from staged seed")
    return _Resolved(
        review_id=review_id,
        hypothesis=hypothesis,
        group=group,
        parent_coordinate=parent,
        parent_coordinate_sha256=parent_sha,
        parent_solution_id=parent_solution_id,
        parent_copy_count=parent_copy_count,
        parent_result_sha256=parent_result_sha,
        parent_llg=parent_llg,
        search_model=search_model,
        search_model_sha256=search_model_sha,
        original_first_copy_model_sha256=expected_model_sha,
        model_identity_fraction=float(identity_percent) / 100.0,
        mtz=mtz,
        mtz_sha256=mtz_sha,
    )


def _parameters(resolved: _Resolved, sequence_fasta: Path, threads: int) -> str:
    labels = resolved.hypothesis.obs_labels
    mtz = json.dumps(str(resolved.mtz))
    sequence = json.dumps(str(sequence_fasta))
    parent = json.dumps(str(resolved.parent_coordinate))
    model = json.dumps(str(resolved.search_model))
    return f"""phaser {{
  mode = MR_AUTO
  hklin = {mtz}
  labin = {labels}
  composition {{
    chain {{
      chain_type = protein
      comp_type = sequence_file
      sequence_file = {sequence}
      num = {resolved.hypothesis.copy_count_expected}
    }}
  }}
  ensemble {{
    model_id = fixed_parent
    solution_at_origin = True
    coordinates {{
      pdb = {parent}
      identity = 1.0
    }}
  }}
  ensemble {{
    model_id = search_copy
    coordinates {{
      pdb = {model}
      identity = {resolved.model_identity_fraction:.12g}
    }}
  }}
  search {{
    ensembles = search_copy
    copies = 1
  }}
  keywords {{
    general {{
      root = {_ROOT}
      jobs = {threads}
    }}
    sgalternative {{ select = none }}
  }}
}}
"""


def _write_output(
    output: Path,
    result: AdditionalCopyResult,
    command: Path,
    parameters: Path,
) -> AddCopyRunOutput:
    result_json = output / "additional_copy_result.json"
    result_jsonl = output / "additional_copy_result.jsonl"
    atomic_write_json(result_json, result.model_dump(mode="json"))
    atomic_write_text(result_jsonl, f"{canonical_json_text(result)}\n")
    return AddCopyRunOutput(result, result_json, result_jsonl, command, parameters)


def run_additional_copy_phaser(request: AddCopyRunRequest) -> AddCopyRunOutput:
    """Run one approved fixed-parent search for exactly one additional copy."""

    if request.threads < 1:
        raise ValueError("threads must be positive")
    if request.timeout_seconds is not None and request.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive when supplied")
    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise PhaserInputError(f"Phaser output directory is not empty: {output}")
    resolved = _resolve(request)
    validate_manifest_environment(request.phenix_manifest.resolve(strict=True))
    output.mkdir(parents=True, exist_ok=True)
    sequence_fasta = output / "composition.fasta"
    atomic_write_text(
        sequence_fasta,
        f">{resolved.group.sequence_group_id}\n{resolved.group.sequence}\n",
    )
    parameters = output / "add_copy.eff"
    atomic_write_text(
        parameters, _parameters(resolved, sequence_fasta, request.threads)
    )
    attempt_identity = {
        "adapter_version": _ADAPTER_VERSION,
        "review_id": resolved.review_id,
        "seed_solution_id": request.seed_solution_id,
        "parent_solution_id": resolved.parent_solution_id,
        "parent_copy_count": resolved.parent_copy_count,
        "parent_result_sha256": resolved.parent_result_sha256,
        "parent_coordinate_sha256": resolved.parent_coordinate_sha256,
        "search_model_sha256": resolved.search_model_sha256,
        "original_first_copy_model_sha256": (resolved.original_first_copy_model_sha256),
        "sequence_sha256": resolved.group.sha256,
        "mtz_sha256": resolved.mtz_sha256,
        "phenix_manifest_sha256": sha256_file(
            request.phenix_manifest.resolve(strict=True)
        ),
        "parameters_sha256": sha256_file(parameters),
    }
    attempt_id = content_id("addcopy_", attempt_identity)
    arguments = ["phenix.phaser", str(parameters)]
    command_json = output / "phaser_command.json"
    atomic_write_json(
        command_json,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "created_at": utc_now_iso(),
            "attempt_id": attempt_id,
            "arguments": arguments,
            "threads": request.threads,
            "timeout_seconds": request.timeout_seconds,
            **attempt_identity,
        },
    )
    _LOGGER.info(
        "additional-copy Phaser search started",
        extra={
            "attempt_id": attempt_id,
            "seed_solution_id": request.seed_solution_id,
            "attempted_copy_number": resolved.parent_copy_count + 1,
            "expected_copy_count": resolved.hypothesis.copy_count_expected,
            "threads": request.threads,
        },
    )
    with tqdm(
        total=1,
        desc="Run additional-copy Phaser",
        unit="seed",
        disable=not request.progress,
    ) as bar:
        try:
            completed = capture_from_manifest(
                request.phenix_manifest,
                arguments,
                working_directory=output,
                timeout_seconds=request.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            completed = subprocess.CompletedProcess(arguments, 124, b"", b"timed out")
        bar.update(1)
    capture_log = output / "phenix.phaser.capture.log"
    atomic_write_text(
        capture_log,
        (completed.stdout + completed.stderr).decode("utf-8", errors="replace"),
    )
    native_log = output / f"{_ROOT}.log"
    raw_log = native_log if native_log.is_file() else capture_log
    status = ExecutionStatus.FAILED_TOOL_EXECUTION
    llg = tfz = None
    placements = 0
    packed = supported = False
    coordinate_path = mtz_path = None
    coordinate_sha = mtz_sha = child_id = None
    warnings: list[str] = []
    rejection_reason: str | None = None
    if completed.returncode != 0:
        rejection_reason = (
            "phenix.phaser_timeout"
            if completed.returncode == 124
            else f"phenix.phaser_exit_{completed.returncode}"
        )
    else:
        try:
            parsed = parse_phaser_log(
                raw_log.read_text(encoding="utf-8", errors="replace")
            )
            llg, tfz = parsed.llg, parsed.tfz
            packed = parsed.packed_solution_count > 0
            warnings.extend(parsed.parser_warnings)
            if parsed.solution_count == 0:
                status = ExecutionStatus.COMPLETED_NO_HIT
                rejection_reason = "phaser_reported_no_additional_solution"
            else:
                coordinate = output / f"{_ROOT}.1.pdb"
                result_mtz = output / f"{_ROOT}.1.mtz"
                if not coordinate.is_file() or not result_mtz.is_file():
                    raise PhaserParseError("additional-copy solution lacks PDB or MTZ")
                coordinate_text = coordinate.read_text(
                    encoding="utf-8", errors="replace"
                )
                placements = len(_PLACEMENT.findall(coordinate_text))
                coordinate_path = coordinate.name
                mtz_path = result_mtz.name
                coordinate_sha = sha256_file(coordinate)
                mtz_sha = sha256_file(result_mtz)
                child_id = content_id(
                    "copystate_",
                    {
                        "attempt_id": attempt_id,
                        "coordinate_sha256": coordinate_sha,
                        "mtz_sha256": mtz_sha,
                    },
                )
                status = ExecutionStatus.COMPLETED_HIT
                supported = packed and placements == resolved.parent_copy_count + 1
                if not packed:
                    warnings.append("additional_copy_not_packing_supported")
                    rejection_reason = "parsed_additional_solution_did_not_pack"
                elif placements != resolved.parent_copy_count + 1:
                    warnings.append("additional_copy_placement_count_not_observed")
                    rejection_reason = "parsed_solution_lacks_expected_copy_evidence"
        except PhaserParseError as error:
            status = ExecutionStatus.FAILED_PARSE
            rejection_reason = str(error)
    result = AdditionalCopyResult(
        schema_version="1.0",
        attempt_id=attempt_id,
        review_id=resolved.review_id,
        seed_solution_id=request.seed_solution_id,
        parent_solution_id=resolved.parent_solution_id,
        child_solution_id=child_id,
        hypothesis_id=resolved.hypothesis.hypothesis_id,
        sequence_group_id=resolved.group.sequence_group_id,
        parent_copy_count=resolved.parent_copy_count,
        attempted_copy_number=resolved.parent_copy_count + 1,
        expected_copy_count=resolved.hypothesis.copy_count_expected,
        execution_status=status,
        llg=llg,
        llg_delta_from_parent=(
            llg - resolved.parent_llg
            if llg is not None and resolved.parent_llg is not None
            else None
        ),
        tfz=tfz,
        phaser_placement_count=placements,
        top_solution_packed=packed,
        additional_copy_supported=supported,
        best_supported_copy_count=(
            resolved.parent_copy_count + 1 if supported else resolved.parent_copy_count
        ),
        output_coordinate_path=coordinate_path,
        output_coordinate_sha256=coordinate_sha,
        output_mtz_path=mtz_path,
        output_mtz_sha256=mtz_sha,
        raw_log_pointer=raw_log.name,
        command_pointer=command_json.name,
        warnings=tuple(warnings),
        rejection_reason=rejection_reason,
    )
    _LOGGER.info(
        "additional-copy Phaser search finished",
        extra={
            "attempt_id": attempt_id,
            "execution_status": status.value,
            "additional_copy_supported": supported,
            "best_supported_copy_count": result.best_supported_copy_count,
        },
    )
    return _write_output(output, result, command_json, parameters)


def run_additional_copy_series(request: AddCopyRunRequest) -> AddCopySeriesOutput:
    """Advance one seed sequentially until expected count or unsupported addition.

    Every attempt fixes the immediately preceding checksum-authenticated child,
    searches exactly one further copy, and remains in its own directory. An
    unsupported attempt ends this candidate's series while retaining all parent
    states and without claiming that the additional copy is absent.
    """

    root = request.output_directory.resolve()
    attempts: list[AddCopyRunOutput] = []
    current_request = request
    while True:
        output = run_additional_copy_phaser(current_request)
        attempts.append(output)
        result = output.result
        if not result.additional_copy_supported:
            stop_reason = "additional_copy_not_supported"
            break
        if result.best_supported_copy_count >= result.expected_copy_count:
            stop_reason = "expected_copy_count_reached"
            break
        if result.output_coordinate_path is None:
            raise PhaserInputError(
                "supported additional-copy child lacks its coordinate path"
            )
        next_copy = result.best_supported_copy_count + 1
        _LOGGER.info(
            "advancing supported additional-copy child",
            extra={
                "seed_solution_id": request.seed_solution_id,
                "parent_solution_id": result.child_solution_id,
                "parent_copy_count": result.best_supported_copy_count,
                "attempted_copy_number": next_copy,
                "expected_copy_count": result.expected_copy_count,
            },
        )
        current_request = replace(
            request,
            output_directory=root / f"copy_{next_copy:02d}",
            parent_result_jsonl=output.result_jsonl,
            parent_coordinate=output.result_json.parent / result.output_coordinate_path,
        )

    aggregate = root / "additional_copy_series_results.jsonl"
    atomic_write_text(
        aggregate,
        "".join(f"{canonical_json_text(item.result)}\n" for item in attempts),
    )
    summary = root / "additional_copy_series_summary.json"
    series_identity = {
        "adapter_version": _ADAPTER_VERSION,
        "seed_solution_id": request.seed_solution_id,
        "attempt_ids": [item.result.attempt_id for item in attempts],
    }
    final = attempts[-1].result
    atomic_write_json(
        summary,
        {
            "schema_version": "1.0",
            "series_id": content_id("copyseries_", series_identity),
            **series_identity,
            "expected_copy_count": final.expected_copy_count,
            "attempt_count": len(attempts),
            "attempted_copy_numbers": [
                item.result.attempted_copy_number for item in attempts
            ],
            "best_supported_copy_count": final.best_supported_copy_count,
            "reached_expected_copy_count": (
                final.best_supported_copy_count == final.expected_copy_count
            ),
            "stop_reason": stop_reason,
            "parent_retained": True,
            "failed_addition_proves_absence": False,
            "result_paths": [
                item.result_jsonl.relative_to(root).as_posix() for item in attempts
            ],
            "result_sha256": [sha256_file(item.result_jsonl) for item in attempts],
        },
    )
    _LOGGER.info(
        "additional-copy series finished",
        extra={
            "seed_solution_id": request.seed_solution_id,
            "attempt_count": len(attempts),
            "best_supported_copy_count": final.best_supported_copy_count,
            "expected_copy_count": final.expected_copy_count,
            "stop_reason": stop_reason,
        },
    )
    return AddCopySeriesOutput(tuple(attempts), aggregate, summary)
