"""Materialise typed offline-localisation stub evidence without running a tool."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.localisation import (
    DeepTMHMMBlockedResult,
    DeepTMHMMRuntimeContract,
    LocalisationGroupEvidence,
    LocalisationOutcome,
    LocalisationResult,
    LocalisationTaskItem,
    PSortbCommandRecord,
    PSortbRuntimeContract,
    plan_deeptmhmm_invocation,
)
from genome_to_diffraction.schemas.base import ContractModel
from genome_to_diffraction.status import ExecutionStatus


def _contract[T: ContractModel](path: Path, model: type[T]) -> T:
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def _scenario(task: LocalisationTaskItem) -> LocalisationOutcome:
    prefix = "stub_localisation:"
    values = tuple(
        flag.removeprefix(prefix)
        for flag in task.sequence_group.quality_flags
        if flag.startswith(prefix)
    )
    if len(values) != 1:
        raise ValueError("stub task requires exactly one localisation scenario flag")
    return LocalisationOutcome(values[0])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-directory", type=Path, required=True)
    parser.add_argument("--psortb-runtime", type=Path, required=True)
    parser.add_argument("--deeptmhmm-runtime", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Write one valid task result for the fixture-declared scenario."""

    args = _build_parser().parse_args(argv)
    task = _contract(args.task_directory / "task.json", LocalisationTaskItem)
    psortb_runtime = _contract(args.psortb_runtime, PSortbRuntimeContract)
    deeptmhmm_runtime = _contract(args.deeptmhmm_runtime, DeepTMHMMRuntimeContract)
    if (
        task.psortb_runtime_identity_sha256 != psortb_runtime.runtime_identity_sha256
        or task.deeptmhmm_runtime_identity_sha256
        != deeptmhmm_runtime.runtime_identity_sha256
    ):
        raise ValueError("stub task runtime identity mismatch")
    args.outdir.mkdir(parents=True, exist_ok=False)
    atomic_write_json(
        args.outdir / "localisation-task.json",
        task.model_dump(mode="json"),
    )

    psortb_root = args.outdir / "psortb"
    raw_root = psortb_root / "raw"
    raw_root.mkdir(parents=True)
    fasta = raw_root / "sequence.faa"
    atomic_write_text(
        fasta,
        f">{task.sequence_group_id}\n{task.sequence_group.sequence}\n",
        encoding="ascii",
    )
    raw_output = raw_root / "psortb-terse.tsv"
    raw_stderr = raw_root / "psortb.stderr.log"
    atomic_write_text(raw_root / "psortb-version.txt", "PSORTb version 3.0.6\n")
    command_values = (
        psortb_runtime.executable_path,
        "-a",
        "-o",
        "terse",
        str(fasta),
    )
    command_payload = {
        "adapter_version": psortb_runtime.adapter_version,
        "arguments": command_values[1:-1],
        "input_fasta_sha256": sha256_file(fasta),
        "runtime_identity_sha256": psortb_runtime.runtime_identity_sha256,
        "sequence_group_id": task.sequence_group_id,
        "sequence_sha256": task.sequence_group.sha256,
        "tool_version": psortb_runtime.tool_version,
    }
    command = PSortbCommandRecord(
        runtime_identity_sha256=psortb_runtime.runtime_identity_sha256,
        sequence_group_id=task.sequence_group_id,
        sequence_sha256=task.sequence_group.sha256,
        input_fasta_path=str(fasta),
        input_fasta_sha256=sha256_file(fasta),
        command=command_values,
        command_identity_sha256=canonical_digest(command_payload),
    )
    atomic_write_json(
        psortb_root / "psortb-command.json",
        command.model_dump(mode="json"),
    )
    scenario = _scenario(task)
    if scenario is LocalisationOutcome.FAILED:
        atomic_write_text(raw_output, "")
        atomic_write_text(raw_stderr, "synthetic PSORTb exit status 7\n")
        result = LocalisationResult(
            tool="psortb",
            tool_version="3.0.6",
            runtime_identity_sha256=psortb_runtime.runtime_identity_sha256,
            sequence_group_id=task.sequence_group_id,
            sequence_sha256=task.sequence_group.sha256,
            execution_status=ExecutionStatus.FAILED_TOOL_EXECUTION,
            outcome=LocalisationOutcome.FAILED,
            raw_output_path=str(raw_output),
            raw_output_sha256=sha256_file(raw_output),
            raw_stderr_path=str(raw_stderr),
            raw_stderr_sha256=sha256_file(raw_stderr),
            command_identity_sha256=command.command_identity_sha256,
            warnings=("PSORTb exited with status 7",),
        )
    else:
        raw_labels = {
            LocalisationOutcome.MEMBRANE: "CytoplasmicMembrane",
            LocalisationOutcome.SURFACE: "Cellwall",
            LocalisationOutcome.EXTRACELLULAR: "Extracellular",
            LocalisationOutcome.SOLUBLE: "Cytoplasmic",
            LocalisationOutcome.UNKNOWN: "Unknown",
        }
        raw_label = raw_labels[scenario]
        atomic_write_text(
            raw_output,
            f"{task.sequence_group_id}\t{raw_label}\t9.00\n",
        )
        atomic_write_text(raw_stderr, "")
        result = LocalisationResult(
            tool="psortb",
            tool_version="3.0.6",
            runtime_identity_sha256=psortb_runtime.runtime_identity_sha256,
            sequence_group_id=task.sequence_group_id,
            sequence_sha256=task.sequence_group.sha256,
            execution_status=ExecutionStatus.COMPLETED_SUCCESS,
            outcome=scenario,
            raw_label=raw_label,
            score=9.0,
            raw_output_path=str(raw_output),
            raw_output_sha256=sha256_file(raw_output),
            raw_stderr_path=str(raw_stderr),
            raw_stderr_sha256=sha256_file(raw_stderr),
            command_identity_sha256=command.command_identity_sha256,
        )
    atomic_write_json(
        psortb_root / "localisation-result.json",
        result.model_dump(mode="json"),
    )

    invocation = plan_deeptmhmm_invocation(
        deeptmhmm_runtime,
        task.sequence_group,
        args.task_directory / "sequence.faa",
    )
    blocked = DeepTMHMMBlockedResult.from_plan(invocation)
    evidence = LocalisationGroupEvidence.from_results(task, result, blocked)
    atomic_write_json(
        args.outdir / "deeptmhmm-invocation-plan.json",
        invocation.model_dump(mode="json"),
    )
    atomic_write_json(
        args.outdir / "deeptmhmm-blocked-result.json",
        blocked.model_dump(mode="json"),
    )
    atomic_write_json(
        args.outdir / "group-localisation-evidence.json",
        evidence.model_dump(mode="json"),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
