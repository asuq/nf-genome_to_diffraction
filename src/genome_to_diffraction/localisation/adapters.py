"""Minimal offline PSORTb adapter and blocked DeepTMHMM runtime plan.

PSORTb receives exactly one canonical sequence group in FASTA format and runs the
official standalone archaeal terse command.  Stdout, stderr, version probe, command,
and terminal result are retained.  Tool and parser failures become typed records.

DeepTMHMM execution is deliberately absent: the official DTU documentation names a
downloadable user image and FASTA input but does not define its local entrypoint,
arguments, or raw output format.  The adapter verifies the image and one-sequence
input checksums and returns a blocked plan instead of guessing.
"""

import math
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.localisation.contracts import (
    DeepTMHMMInvocationPlan,
    DeepTMHMMRuntimeContract,
    LocalisationOutcome,
    LocalisationResult,
    PSortbCommandRecord,
    PSortbRuntimeContract,
)
from genome_to_diffraction.schemas.results import SequenceGroupRecord
from genome_to_diffraction.status import (
    ExecutionStatus,
    InputContractError,
    ResultParseError,
)

_PSORTB_VERSION = re.compile(r"(?<![0-9.])3\.0\.6(?![0-9.])")
_DEEPTMHMM_AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
_DEEPTMHMM_BLOCK_REASON = (
    "official DeepTMHMM 1.0 documentation does not specify the local user-image "
    "entrypoint, arguments, or raw output wire format; inspect and approve the "
    "supplied image contract before enabling execution"
)


@dataclass(frozen=True)
class PSortbOutput:
    """Files published by one terminal standalone PSORTb attempt."""

    result: LocalisationResult
    result_json: Path
    command_json: Path
    version_log: Path


@dataclass(frozen=True)
class _ParsedPSortb:
    raw_label: str
    score: float
    outcome: LocalisationOutcome


def write_sequence_group_fasta(path: Path, record: SequenceGroupRecord) -> None:
    """Write exactly one immutable sequence-equivalence group in FASTA format."""

    atomic_write_text(
        path,
        f">{record.sequence_group_id}\n{record.sequence}\n",
        encoding="ascii",
    )


def build_psortb_command(
    runtime: PSortbRuntimeContract, input_fasta: Path
) -> tuple[str, ...]:
    """Build the official PSORTb archaeal terse command as an argument array."""

    return (
        runtime.executable_path,
        "-a",
        "-o",
        "terse",
        str(input_fasta),
    )


def _verify_file(path_value: str, expected_sha256: str, *, label: str) -> Path:
    path = Path(path_value)
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise InputContractError(f"{label} is missing or unreadable: {path}") from error
    if not resolved.is_file():
        raise InputContractError(f"{label} is not a regular file: {resolved}")
    try:
        actual = sha256_file(resolved)
    except OSError as error:
        raise InputContractError(f"cannot checksum {label}: {resolved}") from error
    if actual != expected_sha256:
        raise InputContractError(f"{label} checksum does not match its contract")
    return resolved


def _verify_psortb(runtime: PSortbRuntimeContract, version_log: Path) -> Path:
    executable = _verify_file(
        runtime.executable_path,
        runtime.executable_sha256,
        label="PSORTb executable",
    )
    if not os.access(executable, os.X_OK):
        raise InputContractError(f"PSORTb executable is not executable: {executable}")
    try:
        completed = subprocess.run(
            (str(executable), "--version"),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise InputContractError(f"cannot probe PSORTb version: {error}") from error
    version_text = completed.stdout + completed.stderr
    atomic_write_text(version_log, version_text)
    if completed.returncode != 0 or _PSORTB_VERSION.search(version_text) is None:
        raise InputContractError(
            "PSORTb version probe did not verify required version 3.0.6"
        )
    return executable


def parse_psortb_terse(path: Path, *, expected_sequence_group_id: str) -> _ParsedPSortb:
    """Parse the official three-column terse output for exactly one sequence."""

    try:
        lines = tuple(
            line for line in path.read_text(encoding="utf-8").splitlines() if line
        )
    except (OSError, UnicodeError) as error:
        raise ResultParseError(f"cannot read PSORTb terse output: {path}") from error
    if len(lines) != 1:
        raise ResultParseError("PSORTb one-sequence output must contain one record")
    fields = lines[0].split("\t")
    if len(fields) != 3:
        raise ResultParseError("PSORTb terse output must contain three columns")
    sequence_id, raw_label, raw_score = fields
    if sequence_id != expected_sequence_group_id:
        raise ResultParseError("PSORTb output sequence ID does not match its input")
    try:
        score = float(raw_score)
    except ValueError as error:
        raise ResultParseError("PSORTb confidence score is not numeric") from error
    if not math.isfinite(score) or score < 0:
        raise ResultParseError(
            "PSORTb confidence score must be finite and non-negative"
        )
    normalised = re.sub(r"[ _-]", "", raw_label).lower()
    outcomes = {
        "cytoplasmicmembrane": LocalisationOutcome.MEMBRANE,
        "cellwall": LocalisationOutcome.SURFACE,
        "extracellular": LocalisationOutcome.EXTRACELLULAR,
        "cytoplasmic": LocalisationOutcome.SOLUBLE,
        "unknown": LocalisationOutcome.UNKNOWN,
    }
    try:
        outcome = outcomes[normalised]
    except KeyError as error:
        raise ResultParseError(
            f"unsupported PSORTb archaeal localisation label: {raw_label!r}"
        ) from error
    return _ParsedPSortb(raw_label=raw_label, score=score, outcome=outcome)


def _command_record(
    runtime: PSortbRuntimeContract,
    record: SequenceGroupRecord,
    input_fasta: Path,
    command: tuple[str, ...],
) -> PSortbCommandRecord:
    input_digest = sha256_file(input_fasta)
    payload = {
        "adapter_version": runtime.adapter_version,
        "arguments": command[1:-1],
        "input_fasta_sha256": input_digest,
        "runtime_identity_sha256": runtime.runtime_identity_sha256,
        "sequence_group_id": record.sequence_group_id,
        "sequence_sha256": record.sha256,
        "tool_version": runtime.tool_version,
    }
    return PSortbCommandRecord(
        runtime_identity_sha256=runtime.runtime_identity_sha256,
        sequence_group_id=record.sequence_group_id,
        sequence_sha256=record.sha256,
        input_fasta_path=str(input_fasta),
        input_fasta_sha256=input_digest,
        command=command,
        command_identity_sha256=canonical_digest(payload),
    )


def _result(
    *,
    runtime: PSortbRuntimeContract,
    record: SequenceGroupRecord,
    command: PSortbCommandRecord,
    status: ExecutionStatus,
    outcome: LocalisationOutcome,
    raw_output: Path,
    raw_stderr: Path,
    raw_label: str | None = None,
    score: float | None = None,
    warnings: tuple[str, ...] = (),
) -> LocalisationResult:
    return LocalisationResult(
        tool="psortb",
        tool_version=runtime.tool_version,
        runtime_identity_sha256=runtime.runtime_identity_sha256,
        sequence_group_id=record.sequence_group_id,
        sequence_sha256=record.sha256,
        execution_status=status,
        outcome=outcome,
        raw_label=raw_label,
        score=score,
        raw_output_path=str(raw_output),
        raw_output_sha256=sha256_file(raw_output),
        raw_stderr_path=str(raw_stderr),
        raw_stderr_sha256=sha256_file(raw_stderr),
        command_identity_sha256=command.command_identity_sha256,
        warnings=warnings,
    )


def run_psortb(
    runtime: PSortbRuntimeContract,
    record: SequenceGroupRecord,
    output_directory: Path,
) -> PSortbOutput:
    """Run one offline PSORTb 3.0.6 archaeal attempt and retain raw evidence."""

    try:
        output_directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise InputContractError(
            f"PSORTb output directory already exists: {output_directory}"
        ) from error
    raw_directory = output_directory / "raw"
    raw_directory.mkdir()
    input_fasta = raw_directory / "sequence.faa"
    raw_output = raw_directory / "psortb-terse.tsv"
    raw_stderr = raw_directory / "psortb.stderr.log"
    version_log = raw_directory / "psortb-version.txt"
    write_sequence_group_fasta(input_fasta, record)
    executable = _verify_psortb(runtime, version_log)
    command_values = build_psortb_command(runtime, input_fasta)
    command_values = (str(executable), *command_values[1:])
    command = _command_record(runtime, record, input_fasta, command_values)
    command_json = output_directory / "psortb-command.json"
    atomic_write_json(command_json, command.model_dump(mode="json"))
    try:
        with (
            raw_output.open("w", encoding="utf-8") as stdout,
            raw_stderr.open("w", encoding="utf-8") as stderr,
        ):
            completed = subprocess.run(
                command_values,
                check=False,
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
    except OSError as error:
        atomic_write_text(raw_output, "")
        atomic_write_text(raw_stderr, f"cannot execute PSORTb: {error}\n")
        completed_returncode = None
    else:
        completed_returncode = completed.returncode

    if completed_returncode != 0:
        warning = (
            "PSORTb could not be spawned"
            if completed_returncode is None
            else f"PSORTb exited with status {completed_returncode}"
        )
        result = _result(
            runtime=runtime,
            record=record,
            command=command,
            status=ExecutionStatus.FAILED_TOOL_EXECUTION,
            outcome=LocalisationOutcome.FAILED,
            raw_output=raw_output,
            raw_stderr=raw_stderr,
            warnings=(warning,),
        )
    else:
        try:
            parsed = parse_psortb_terse(
                raw_output,
                expected_sequence_group_id=record.sequence_group_id,
            )
        except ResultParseError as error:
            result = _result(
                runtime=runtime,
                record=record,
                command=command,
                status=ExecutionStatus.FAILED_PARSE,
                outcome=LocalisationOutcome.FAILED,
                raw_output=raw_output,
                raw_stderr=raw_stderr,
                warnings=(str(error),),
            )
        else:
            result = _result(
                runtime=runtime,
                record=record,
                command=command,
                status=ExecutionStatus.COMPLETED_SUCCESS,
                outcome=parsed.outcome,
                raw_output=raw_output,
                raw_stderr=raw_stderr,
                raw_label=parsed.raw_label,
                score=parsed.score,
            )
    result_json = output_directory / "localisation-result.json"
    atomic_write_json(result_json, result.model_dump(mode="json"))
    return PSortbOutput(
        result=result,
        result_json=result_json,
        command_json=command_json,
        version_log=version_log,
    )


def _read_single_sequence_fasta(path: Path) -> tuple[str, str]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as error:
        raise InputContractError(
            f"cannot read DeepTMHMM input FASTA: {path}"
        ) from error
    if not lines or not lines[0].startswith(">"):
        raise InputContractError("DeepTMHMM input must be FASTA")
    if any(line.startswith(">") for line in lines[1:]):
        raise InputContractError("DeepTMHMM contract accepts exactly one sequence")
    identifier = lines[0][1:]
    sequence = "".join(lines[1:])
    if not identifier or not sequence:
        raise InputContractError("DeepTMHMM FASTA requires identifier and sequence")
    return identifier, sequence


def plan_deeptmhmm_invocation(
    runtime: DeepTMHMMRuntimeContract,
    record: SequenceGroupRecord,
    input_fasta: Path,
) -> DeepTMHMMInvocationPlan:
    """Verify the image/input pair and return an explicitly blocked CLI plan."""

    _verify_file(
        runtime.image_path,
        runtime.image_sha256,
        label="DeepTMHMM user image",
    )
    try:
        resolved_input = input_fasta.resolve(strict=True)
    except OSError as error:
        raise InputContractError(
            f"DeepTMHMM input FASTA is missing: {input_fasta}"
        ) from error
    identifier, sequence = _read_single_sequence_fasta(resolved_input)
    if identifier != record.sequence_group_id or sequence != record.sequence:
        raise InputContractError(
            "DeepTMHMM input FASTA does not match its sequence-group contract"
        )
    unsupported = sorted(set(sequence) - _DEEPTMHMM_AMINO_ACIDS)
    if unsupported:
        raise InputContractError(
            "DeepTMHMM input contains unsupported residues: " + "".join(unsupported)
        )
    return DeepTMHMMInvocationPlan(
        runtime_identity_sha256=runtime.runtime_identity_sha256,
        image_sha256=runtime.image_sha256,
        sequence_group_id=record.sequence_group_id,
        sequence_sha256=record.sha256,
        input_fasta_path=str(resolved_input),
        input_fasta_sha256=sha256_file(resolved_input),
        block_reason=_DEEPTMHMM_BLOCK_REASON,
    )
