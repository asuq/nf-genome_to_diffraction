"""Run and normalise one first-copy Phaser MR hypothesis.

The adapter accepts one immutable ``MrHypothesis``, verifies its sequence,
processed model, MTZ, preflight, and Phenix runtime, then executes
``phenix.phaser`` in a hypothesis-owned directory. Total composition comes from
the full candidate sequence and expected copy count; exactly one copy is
searched. The exact-predicted vertical slice passes factual 100% sequence
identity explicitly, while Phenix-processed model B values retain predicted
coordinate uncertainty.

Tool failure, malformed output, scientific no-hit, and a preliminary hit remain
distinct. The user-defined provisional score gate is strict: LLG > 100 and
TFZ > 10. Final packing and placed-copy checks are independent requirements and
all raw metrics and advisories are preserved.
"""

import json
import logging
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.phenix.runtime import (
    capture_from_manifest,
    validate_manifest_environment,
)
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    MtzPreflightRecord,
    NormalisedMrResult,
    PreflightDecision,
    ProcessedModelRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import (
    ExecutionStatus,
    InputContractError,
    ResultParseError,
)
from genome_to_diffraction.time import utc_now_iso

_LOGGER = logging.getLogger("genome_to_diffraction.mr.phaser")
_ADAPTER_VERSION = "phenix-first-copy-mr-v1"
_ROOT = "PHASER"
_LLG_GATE = 100.0
_TFZ_GATE = 10.0
_VERSION = re.compile(r"PHENIX:\s+Phaser\s+([0-9]+(?:\.[0-9]+){2})", re.I)
_TOP_LLG = re.compile(r"Top LLG \(packs\)\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)")
_REFINED_TFZ = re.compile(
    r"Refined TF/TFZ equivalent\s*=\s*-?[0-9]+(?:\.[0-9]+)?/\s*"
    r"(-?[0-9]+(?:\.[0-9]+)?)"
)
_LLGI = re.compile(r"\bLLGI\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)")
_SOLUTION_COUNT = re.compile(r"\*\* There (?:were|was)\s+(\d+) solutions?", re.I)
_NO_SOLUTION = re.compile(r"^\s*(?:\*\*\s+)?Sorry\s+-\s+No solutions?\s*$", re.I | re.M)
_PACKING = re.compile(
    r"(\d+) accepted of (\d+) solutions\s+(\d+) pack of (\d+) accepted solutions"
)
_PDB_LLG = re.compile(r"^REMARK Log-Likelihood Gain:\s*(-?[0-9]+(?:\.[0-9]+)?)", re.M)
_PDB_TFZ = re.compile(r"\bTFZ==(-?[0-9]+(?:\.[0-9]+)?)")
_PDB_PAK = re.compile(r"\bPAK=(-?[0-9]+(?:\.[0-9]+)?)")
_PDB_PLACEMENT = re.compile(r"^REMARK ENSEMBLE\s+", re.M)


class PhaserInputError(InputContractError):
    """An MR hypothesis cannot be executed without changing its identity."""


class PhaserParseError(ResultParseError):
    """A completed Phaser log or output set is internally inconsistent."""


@dataclass(frozen=True)
class PhaserRunRequest:
    """Immutable inputs and resource controls for one first-copy search."""

    hypotheses_jsonl: Path
    hypothesis_id: str
    sequence_groups_jsonl: Path
    processed_models_jsonl: Path
    model_preparation_manifest: Path
    preflight_jsonl: Path
    mtz: Path
    phenix_manifest: Path
    output_directory: Path
    threads: int = 1
    timeout_seconds: float | None = None
    progress: bool = True


@dataclass(frozen=True)
class PhaserRunOutput:
    """Normalised record and retained files from one MR attempt."""

    result: NormalisedMrResult
    result_json: Path
    result_jsonl: Path
    command_json: Path


@dataclass(frozen=True)
class ParsedPhaserLog:
    """Versioned raw Phaser metrics before hypothesis-specific classification."""

    phaser_version: str | None
    solution_count: int
    llg: float | None
    llgi: float | None
    tfz: float | None
    accepted_solution_count: int
    packed_solution_count: int
    parser_warnings: tuple[str, ...]


@dataclass(frozen=True)
class _ResolvedInput:
    """Integrity-checked files and records used to construct the command."""

    hypothesis: MrHypothesis
    group: SequenceGroupRecord
    model: ProcessedModelRecord
    model_path: Path
    preflight: MtzPreflightRecord
    mtz_path: Path


def _read_jsonl[T: BaseModel](
    path: Path, model: type[T], *, label: str
) -> tuple[T, ...]:
    resolved = path.resolve(strict=True)
    records: list[T] = []
    with resolved.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(model.model_validate_json(line))
            except ValidationError as error:
                raise PhaserInputError(
                    f"invalid {label} record at line {line_number}: {resolved}"
                ) from error
    if not records:
        raise PhaserInputError(f"{label} input is empty: {resolved}")
    return tuple(records)


def _one_by_id[T](
    records: tuple[T, ...],
    *,
    identifier: str,
    key: Callable[[T], str],
    label: str,
) -> T:
    matches = [record for record in records if key(record) == identifier]
    if len(matches) != 1:
        raise PhaserInputError(
            f"expected exactly one {label} {identifier!r}; observed {len(matches)}"
        )
    return matches[0]


def _load_manifest(path: Path) -> tuple[Path, dict[str, object]]:
    resolved = path.resolve(strict=True)
    try:
        document: object = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PhaserInputError(
            f"cannot load model-preparation manifest: {resolved}"
        ) from error
    if not isinstance(document, dict):
        raise PhaserInputError("model-preparation manifest must be a JSON object")
    return resolved, cast(dict[str, object], document)


def _resolve_model_path(
    manifest_path: Path, model: ProcessedModelRecord, *, progress: bool
) -> Path:
    resolved, document = _load_manifest(manifest_path)
    entries = document.get("entries")
    if document.get("schema_version") != "1.0" or not isinstance(entries, list):
        raise PhaserInputError("model-preparation manifest structure is invalid")
    matches = [
        cast(dict[str, object], entry)
        for entry in entries
        if isinstance(entry, dict) and entry.get("model_id") == model.model_id
    ]
    if len(matches) != 1:
        raise PhaserInputError(
            f"model-preparation manifest does not uniquely map {model.model_id}"
        )
    entry = matches[0]
    relative_text = entry.get("model_path")
    digest = entry.get("model_sha256")
    if not isinstance(relative_text, str) or digest != model.model_sha256:
        raise PhaserInputError("model-preparation entry does not match model record")
    relative = PurePosixPath(relative_text)
    if relative.is_absolute() or ".." in relative.parts or relative_text == "":
        raise PhaserInputError(f"unsafe processed-model path: {relative_text!r}")
    root = resolved.parent.resolve()
    model_path = (root / Path(*relative.parts)).resolve(strict=True)
    if not model_path.is_file() or not model_path.is_relative_to(root):
        raise PhaserInputError("processed model escaped its preparation root")
    actual = sha256_file(
        model_path,
        progress=progress,
        description="Verify MR model",
        logger=_LOGGER,
    )
    if actual != model.model_sha256:
        raise PhaserInputError("processed-model checksum mismatch")
    return model_path


def _normalise_space_group(value: str) -> str:
    return " ".join(value.split()).upper()


def _resolve_inputs(request: PhaserRunRequest) -> _ResolvedInput:
    hypotheses = _read_jsonl(
        request.hypotheses_jsonl, MrHypothesis, label="MR hypotheses"
    )
    hypothesis = _one_by_id(
        hypotheses,
        identifier=request.hypothesis_id,
        key=lambda item: item.hypothesis_id,
        label="MR hypothesis",
    )
    if (
        hypothesis.search_stage is not MrSearchStage.FIRST_COPY
        or hypothesis.copy_number_to_search != 1
        or hypothesis.fixed_solution_id is not None
        or hypothesis.status is not MrHypothesisStatus.QUEUED
    ):
        raise PhaserInputError(
            "hypothesis is not a queued independent first-copy search"
        )
    if hypothesis.priority_features.get("exact_sequence_mapping") is not True:
        raise PhaserInputError("first exact-predicted adapter requires exact mapping")
    groups = _read_jsonl(
        request.sequence_groups_jsonl, SequenceGroupRecord, label="sequence groups"
    )
    group = _one_by_id(
        groups,
        identifier=hypothesis.sequence_group_id,
        key=lambda item: item.sequence_group_id,
        label="sequence group",
    )
    models = _read_jsonl(
        request.processed_models_jsonl, ProcessedModelRecord, label="processed models"
    )
    model = _one_by_id(
        models,
        identifier=hypothesis.model_id,
        key=lambda item: item.model_id,
        label="processed model",
    )
    if (
        model.full_candidate_sequence_group_id != group.sequence_group_id
        or model.variant_type != "predicted_confidence_pruned_full"
        or model.processing_tool != "phenix.process_predicted_model"
    ):
        raise PhaserInputError("processed model does not match exact-predicted policy")
    model_path = _resolve_model_path(
        request.model_preparation_manifest, model, progress=request.progress
    )
    preflights = _read_jsonl(
        request.preflight_jsonl, MtzPreflightRecord, label="MTZ preflights"
    )
    preflight = _one_by_id(
        preflights,
        identifier=hypothesis.crystal_id,
        key=lambda item: item.crystal_id,
        label="MTZ preflight",
    )
    if preflight.decision is PreflightDecision.FAIL:
        raise PhaserInputError("cannot run MR against a failed MTZ preflight")
    if preflight.selected_observation_labels is None or hypothesis.obs_labels is None:
        raise PhaserInputError("MR hypothesis lacks selected observation labels")
    if hypothesis.obs_labels != preflight.selected_observation_labels:
        raise PhaserInputError("hypothesis observation labels differ from preflight")
    if _normalise_space_group(hypothesis.space_group) != _normalise_space_group(
        preflight.space_group
    ):
        raise PhaserInputError("hypothesis space group differs from preflight")
    mtz_path = request.mtz.resolve(strict=True)
    if not mtz_path.is_file():
        raise PhaserInputError(f"MTZ is not a regular file: {mtz_path}")
    mtz_sha256 = sha256_file(
        mtz_path,
        progress=request.progress,
        description="Verify MR MTZ",
        logger=_LOGGER,
    )
    if mtz_sha256 != preflight.mtz_sha256:
        raise PhaserInputError("MTZ checksum differs from preflight")
    return _ResolvedInput(
        hypothesis=hypothesis,
        group=group,
        model=model,
        model_path=model_path,
        preflight=preflight,
        mtz_path=mtz_path,
    )


def _last_match_float(pattern: re.Pattern[str], text: str) -> float | None:
    values = [float(match) for match in pattern.findall(text)]
    return values[-1] if values else None


def parse_phaser_log(text: str) -> ParsedPhaserLog:
    """Parse final Phaser metrics without treating early advisories as terminal."""

    solution_matches = list(_SOLUTION_COUNT.finditer(text))
    no_solution_matches = list(_NO_SOLUTION.finditer(text))
    if no_solution_matches and (
        not solution_matches
        or no_solution_matches[-1].start() > solution_matches[-1].start()
    ):
        solution_count = 0
    elif solution_matches:
        solution_count = int(solution_matches[-1].group(1))
    else:
        raise PhaserParseError("Phaser log lacks a final solution count")
    packing_rows = [
        tuple(int(value) for value in row) for row in _PACKING.findall(text)
    ]
    accepted = packed = 0
    if packing_rows:
        accepted, total, packed, accepted_again = packing_rows[-1]
        if total < accepted or accepted_again != accepted or packed > accepted:
            raise PhaserParseError("Phaser final packing counts are inconsistent")
    elif solution_count > 0:
        raise PhaserParseError("Phaser solution lacks final packing evidence")
    warnings: list[str] = []
    if "The top solution from a FTF did not pack" in text:
        warnings.append("phaser_advisory_top_ftf_did_not_pack")
    if "EXIT STATUS: SUCCESS" not in text:
        warnings.append("phaser_success_marker_absent")
    llg_values = [float(value) for value in _TOP_LLG.findall(text)]
    tfz_values = [float(value) for value in _REFINED_TFZ.findall(text)]
    llg = max(llg_values) if llg_values else None
    tfz = max(tfz_values) if tfz_values else None
    llgi = _last_match_float(_LLGI, text)
    if solution_count > 0 and (llg is None or tfz is None):
        raise PhaserParseError("Phaser solution lacks final LLG or TFZ")
    version_match = _VERSION.search(text)
    return ParsedPhaserLog(
        phaser_version=version_match.group(1) if version_match else None,
        solution_count=solution_count,
        llg=llg,
        llgi=llgi,
        tfz=tfz,
        accepted_solution_count=accepted,
        packed_solution_count=packed,
        parser_warnings=tuple(warnings),
    )


def _command(resolved: _ResolvedInput, sequence_fasta: Path, threads: int) -> list[str]:
    hypothesis = resolved.hypothesis
    return [
        "phenix.phaser",
        "phaser.mode=MR_AUTO",
        f"phaser.hklin={resolved.mtz_path}",
        f"phaser.labin={hypothesis.obs_labels}",
        f"phaser.model={resolved.model_path}",
        f"phaser.seq_file={sequence_fasta}",
        "phaser.model_identity=100",
        f"phaser.component_copies={hypothesis.copy_count_expected}",
        "phaser.search_copies=1",
        f"phaser.keywords.general.root={_ROOT}",
        f"phaser.keywords.general.jobs={threads}",
        "phaser.keywords.sgalternative.select=none",
    ]


def _write_result(
    output: Path,
    result: NormalisedMrResult,
    command_json: Path,
) -> PhaserRunOutput:
    result_json = output / "normalised_mr_result.json"
    atomic_write_json(result_json, result.model_dump(mode="json"))
    result_jsonl = output / "normalised_mr_result.jsonl"
    atomic_write_text(result_jsonl, f"{canonical_json_text(result)}\n")
    return PhaserRunOutput(result, result_json, result_jsonl, command_json)


def _failure_result(
    *,
    hypothesis: MrHypothesis,
    tool_version: str,
    status: ExecutionStatus,
    raw_log: Path,
    reason: str,
    warnings: tuple[str, ...] = (),
) -> NormalisedMrResult:
    return NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=hypothesis.hypothesis_id,
        tool_version=tool_version,
        execution_status=status,
        llg=None,
        llgi=None,
        tfz=None,
        placed_copy_count=0,
        packing_summary={},
        parser_warnings=warnings,
        raw_log_pointer=raw_log.name,
        preliminary_credibility_class=None,
        rejection_reason=reason,
    )


def _read_solution_metrics(
    parsed: ParsedPhaserLog,
    coordinate_path: Path,
) -> tuple[float | None, float | None, int, float | None]:
    if not coordinate_path.is_file():
        return parsed.llg, parsed.tfz, 0, None
    text = coordinate_path.read_text(encoding="utf-8", errors="replace")
    pdb_llg = _last_match_float(_PDB_LLG, text)
    llg = pdb_llg if pdb_llg is not None else parsed.llg
    tfz_values = [float(value) for value in _PDB_TFZ.findall(text)]
    tfz = tfz_values[-1] if tfz_values else parsed.tfz
    placed_count = len(_PDB_PLACEMENT.findall(text))
    pak_values = [float(value) for value in _PDB_PAK.findall(text)]
    pak = pak_values[-1] if pak_values else None
    return llg, tfz, placed_count, pak


def _normalised_success(
    *,
    resolved: _ResolvedInput,
    parsed: ParsedPhaserLog,
    tool_version: str,
    raw_log: Path,
    output: Path,
) -> NormalisedMrResult:
    coordinate = output / f"{_ROOT}.1.pdb"
    output_mtz = output / f"{_ROOT}.1.mtz"
    if parsed.solution_count == 0:
        if coordinate.exists() or output_mtz.exists():
            raise PhaserParseError(
                "zero-solution log produced unexpected solution files"
            )
        return NormalisedMrResult(
            schema_version="1.0",
            hypothesis_id=resolved.hypothesis.hypothesis_id,
            tool_version=tool_version,
            execution_status=ExecutionStatus.COMPLETED_NO_HIT,
            llg=None,
            llgi=parsed.llgi,
            tfz=None,
            placed_copy_count=0,
            packing_summary={
                "solution_count": 0,
                "accepted_solution_count": 0,
                "packed_solution_count": 0,
                "top_solution_packed": False,
            },
            parser_warnings=parsed.parser_warnings,
            raw_log_pointer=raw_log.name,
            preliminary_credibility_class="no_solution",
            rejection_reason="phaser_reported_no_solution",
        )
    if not coordinate.is_file() or not output_mtz.is_file():
        raise PhaserParseError("Phaser solution is missing PDB or MTZ output")
    llg, tfz, placed_count, pak = _read_solution_metrics(parsed, coordinate)
    if llg is None or tfz is None or placed_count < 1:
        raise PhaserParseError("Phaser solution files lack final placement metrics")
    score_gate = llg > _LLG_GATE and tfz > _TFZ_GATE
    top_packed = parsed.packed_solution_count > 0
    placed_expected = placed_count == resolved.hypothesis.copy_number_to_search
    credible = score_gate and top_packed and placed_expected
    rejection_reasons: list[str] = []
    if not score_gate:
        rejection_reasons.append("strict_llg_tfz_gate_not_met")
    if not top_packed:
        rejection_reasons.append("final_packing_not_accepted")
    if not placed_expected:
        rejection_reasons.append("placed_copy_count_mismatch")
    coordinate_sha256 = sha256_file(coordinate)
    output_mtz_sha256 = sha256_file(output_mtz)
    return NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=resolved.hypothesis.hypothesis_id,
        tool_version=tool_version,
        execution_status=(
            ExecutionStatus.COMPLETED_HIT
            if credible
            else ExecutionStatus.COMPLETED_NO_HIT
        ),
        llg=llg,
        llgi=parsed.llgi,
        tfz=tfz,
        placed_copy_count=placed_count,
        packing_summary={
            "solution_count": parsed.solution_count,
            "accepted_solution_count": parsed.accepted_solution_count,
            "packed_solution_count": parsed.packed_solution_count,
            "top_solution_packed": top_packed,
            "top_solution_pak": pak,
            "score_gate_llg_strictly_greater_than": _LLG_GATE,
            "score_gate_tfz_strictly_greater_than": _TFZ_GATE,
            "score_gate_passed": score_gate,
        },
        solution_coordinate_path=coordinate.name,
        solution_coordinate_sha256=coordinate_sha256,
        output_mtz_path=output_mtz.name,
        output_mtz_sha256=output_mtz_sha256,
        parser_warnings=parsed.parser_warnings,
        raw_log_pointer=raw_log.name,
        preliminary_credibility_class=(
            "passes_strict_provisional_score_gate"
            if score_gate
            else "does_not_pass_strict_provisional_score_gate"
        ),
        rejection_reason=(";".join(rejection_reasons) or None),
    )


def run_first_copy_phaser(request: PhaserRunRequest) -> PhaserRunOutput:
    """Execute and normalise one exact-predicted independent first-copy search."""

    if request.threads < 1:
        raise ValueError("threads must be positive")
    if request.timeout_seconds is not None and request.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive when supplied")
    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise PhaserInputError(f"Phaser output directory is not empty: {output}")
    resolved = _resolve_inputs(request)
    phenix_manifest = validate_manifest_environment(
        request.phenix_manifest.resolve(strict=True)
    )
    output.mkdir(parents=True, exist_ok=True)
    sequence_fasta = output / "composition.fasta"
    atomic_write_text(
        sequence_fasta,
        f">{resolved.group.sequence_group_id}\n{resolved.group.sequence}\n",
    )
    arguments = _command(resolved, sequence_fasta, request.threads)
    command_json = output / "phaser_command.json"
    atomic_write_json(
        command_json,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "created_at": utc_now_iso(),
            "hypothesis_id": resolved.hypothesis.hypothesis_id,
            "arguments": arguments,
            "threads": request.threads,
            "timeout_seconds": request.timeout_seconds,
            "model_identity_percent": 100.0,
            "model_uncertainty_source": (
                "phenix.process_predicted_model converted B values"
            ),
            "mtz_sha256": resolved.preflight.mtz_sha256,
            "model_sha256": resolved.model.model_sha256,
            "sequence_sha256": resolved.group.sha256,
            "phenix_manifest_sha256": sha256_file(
                request.phenix_manifest.resolve(strict=True)
            ),
        },
    )
    _LOGGER.info(
        "first-copy Phaser search started",
        extra={
            "hypothesis_id": resolved.hypothesis.hypothesis_id,
            "copy_count_expected": resolved.hypothesis.copy_count_expected,
            "copy_number_to_search": 1,
            "threads": request.threads,
            "output_directory": str(output),
        },
    )
    with tqdm(
        total=1,
        desc="Run first-copy Phaser",
        unit="hypothesis",
        disable=not request.progress,
    ) as progress_bar:
        try:
            completed = capture_from_manifest(
                request.phenix_manifest,
                arguments,
                working_directory=output,
                timeout_seconds=request.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            capture_log = output / "phenix.phaser.capture.log"
            atomic_write_text(capture_log, "phenix.phaser timed out\n")
            result = _failure_result(
                hypothesis=resolved.hypothesis,
                tool_version=phenix_manifest.phenix_version,
                status=ExecutionStatus.FAILED_INFRASTRUCTURE,
                raw_log=capture_log,
                reason="phenix.phaser_timeout",
            )
            progress_bar.update(1)
            return _write_result(output, result, command_json)
        progress_bar.update(1)
    capture_log = output / "phenix.phaser.capture.log"
    atomic_write_text(
        capture_log,
        (completed.stdout + completed.stderr).decode("utf-8", errors="replace"),
    )
    native_log = output / f"{_ROOT}.log"
    raw_log = native_log if native_log.is_file() else capture_log
    if completed.returncode != 0:
        result = _failure_result(
            hypothesis=resolved.hypothesis,
            tool_version=phenix_manifest.phenix_version,
            status=ExecutionStatus.FAILED_TOOL_EXECUTION,
            raw_log=raw_log,
            reason=f"phenix.phaser_exit_{completed.returncode}",
        )
        _LOGGER.warning(
            "first-copy Phaser tool execution failed",
            extra={
                "hypothesis_id": resolved.hypothesis.hypothesis_id,
                "exit_status": completed.returncode,
            },
        )
        return _write_result(output, result, command_json)
    log_text = raw_log.read_text(encoding="utf-8", errors="replace")
    try:
        parsed = parse_phaser_log(log_text)
        tool_version = (
            f"Phenix {phenix_manifest.phenix_version}; Phaser {parsed.phaser_version}"
            if parsed.phaser_version is not None
            else f"Phenix {phenix_manifest.phenix_version}"
        )
        result = _normalised_success(
            resolved=resolved,
            parsed=parsed,
            tool_version=tool_version,
            raw_log=raw_log,
            output=output,
        )
    except PhaserParseError as error:
        result = _failure_result(
            hypothesis=resolved.hypothesis,
            tool_version=phenix_manifest.phenix_version,
            status=ExecutionStatus.FAILED_PARSE,
            raw_log=raw_log,
            reason=str(error),
        )
    _LOGGER.info(
        "first-copy Phaser search normalised",
        extra={
            "hypothesis_id": resolved.hypothesis.hypothesis_id,
            "execution_status": result.execution_status.value,
            "llg": result.llg,
            "tfz": result.tfz,
            "placed_copy_count": result.placed_copy_count,
            "rejection_reason": result.rejection_reason,
        },
    )
    return _write_result(output, result, command_json)
