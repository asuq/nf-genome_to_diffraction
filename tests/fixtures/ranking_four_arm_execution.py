"""Reference-only complete child-byte and native task-log resume checkpoints.

Reuse the original production byte-inventory reader without assigning the mixed
five-case reference graph an M6 track. First-pass tasks must complete and resume
tasks must all cache with identical identities, output bytes and full task logs.
The original reference result file, trace and executor sources are bound too.
An explicit externally saved baseline checksum is mandatory for resume.

This is a file-integrity boundary, not scientific/native acceptance. The fixed
runner must separately authenticate the exact-case result against its original
contexts and validate native commands/resources before any truth comparison.
Task exit zero is not a claim that an underlying Phenix candidate succeeded.
No external command runs, and no native paths, IDs or scientific fields change.
Missing, foreign, duplicate, modified or incompletely cached evidence fails.
"""

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator
from tests.fixtures.ranking_four_arm_advancement import (
    REFERENCE_CASE_IDS,
    _source_sha256,
)

from genome_to_diffraction.benchmarks.m6_execution import (
    M6ChildOutputTask,
    collect_child_output_tasks,
)
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.base import ContractModel, PositiveInt, Sha256Hex

_PROCESSES = frozenset(
    {
        "RF_PLAN",
        "RF_PREPARE",
        "RF_FIRST_COPY",
        "RF_REVIEWS",
        "RF_COPY",
        "RF_FINALISTS",
        "RF_REFINE",
        "RF_IDENTITY",
        "RF_AGGREGATE",
        "M6_IMPORT_CATALOGUE",
        "M6_BUILD_SEARCH_BATCHES",
        "M6_SEARCH_PDB",
        "M6_SEARCH_FOLDSEEK",
        "M6_PARTITION_DISCOVERY",
        "M6_PREFLIGHT_CASE",
        "M6_APPLY_POLICY",
        "M6_STAGE_COORDINATES",
        "M6_PREPARE_ACTIVE_CASE",
        "M6_PREPARE_EARLY_CASE",
    }
)
_LOGS = (
    ".command.sh",
    ".command.run",
    ".command.out",
    ".command.err",
    ".command.log",
    ".command.trace",
    ".exitcode",
)


@dataclass(frozen=True)
class ReferenceChildOutputRequest:
    """Original result/trace and, for resume, an independently frozen first receipt."""

    result: Path
    trace: Path
    output: Path
    baseline: Path | None = None
    expected_baseline_sha256: str | None = None


class ReferenceTaskLogs(ContractModel):
    """Exact task script/runtime log bytes, including genuine numeric exit evidence."""

    process: str
    tag: str
    task_hash: str
    files: dict[str, Sha256Hex]


class ReferenceChildOutputs(ContractModel):
    """Path-free integrity evidence, deliberately not an M6 track or native verdict."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["rf-child-output-checkpoint-v1"] = (
        "rf-child-output-checkpoint-v1"
    )
    native_acceptance_claim: Literal[False] = False
    benchmark_acceptance_claim: Literal[False] = False
    human_approval_granted: Literal[False] = False
    checkpoint_id: str
    phase: Literal["first", "resume"]
    baseline_sha256: Sha256Hex | None
    source_sha256: dict[str, Sha256Hex]
    trace_sha256: Sha256Hex
    reference_result_sha256: Sha256Hex
    task_count: PositiveInt
    tasks: tuple[M6ChildOutputTask, ...]
    task_logs: tuple[ReferenceTaskLogs, ...]

    @model_validator(mode="after")
    def _validate_tasks(self) -> Self:
        keys = tuple((row.process, row.tag, row.task_hash) for row in self.tasks)
        logs = tuple((row.process, row.tag, row.task_hash) for row in self.task_logs)
        if (
            self.task_count != len(keys)
            or keys != tuple(sorted(set(keys)))
            or len({(row.process, row.tag) for row in self.tasks}) != len(keys)
            or logs != keys
            or any(set(row.files) != set(_LOGS) for row in self.task_logs)
            or (self.phase == "first") != (self.baseline_sha256 is None)
        ):
            raise ValueError(
                "reference child/log inventory is incomplete or duplicated"
            )
        expected_status = "COMPLETED" if self.phase == "first" else "CACHED"
        for task in self.tasks:
            prefix, separator, name = task.process.rpartition(":")
            if (
                not separator
                or prefix != "RF_REFERENCE_WORKFLOW"
                or name not in _PROCESSES
                or task.status != expected_status
            ):
                raise ValueError(
                    "reference child is foreign, failed or not fully cached"
                )
        counts = Counter(row.process.rsplit(":", 1)[-1] for row in self.tasks)
        if counts["RF_PLAN"] != 1 or counts["RF_AGGREGATE"] != 1:
            raise ValueError("reference trace lacks its unique fixed plan/aggregate")
        for process, tag in (
            ("RF_PREPARE", "rf-prepare:"),
            ("M6_PREFLIGHT_CASE", "m6-preflight:"),
        ):
            observed = {
                row.tag for row in self.tasks if row.process.endswith(f":{process}")
            }
            if observed != {f"{tag}{case_id}" for case_id in REFERENCE_CASE_IDS}:
                raise ValueError(
                    "reference trace lacks the complete five-case boundary"
                )
        return self


def _identity(manifest: ReferenceChildOutputs) -> str:
    return content_id(
        "rfoutputs_", manifest.model_dump(mode="json", exclude={"checkpoint_id"})
    )


def _logs(trace: Path, output: Path) -> tuple[ReferenceTaskLogs, ...]:
    records = []
    with trace.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            work = Path(row["workdir"]).resolve(strict=True)
            if output.resolve().is_relative_to(work):
                raise ValueError(
                    "reference checkpoint cannot modify a bound task directory"
                )
            files = {}
            for name in _LOGS:
                path = work / name
                if path.is_symlink() or not path.is_file():
                    raise ValueError(
                        f"reference original task log is missing or substituted: {name}"
                    )
                files[name] = sha256_file(path)
            if (work / ".exitcode").read_text(encoding="ascii").strip() != "0":
                raise ValueError("reference task process did not exit successfully")
            records.append(
                ReferenceTaskLogs(
                    process=row["process"],
                    tag=row["tag"],
                    task_hash=row["hash"],
                    files=files,
                )
            )
    return tuple(sorted(records, key=lambda row: (row.process, row.tag, row.task_hash)))


def collect_reference_child_outputs(
    request: ReferenceChildOutputRequest,
) -> ReferenceChildOutputs:
    """Freeze first bytes or require an identical fully cached resume."""

    if request.output.exists() or request.output.is_symlink():
        raise ValueError("reference child checkpoint output must not already exist")
    if request.output.resolve().is_relative_to(
        request.result.resolve(strict=True).parent
    ):
        raise ValueError(
            "reference checkpoint cannot modify its bound result directory"
        )
    source = _source_sha256()
    result_sha = sha256_file(request.result)
    trace_sha = sha256_file(request.trace)
    baseline = None
    if (request.baseline is None) != (request.expected_baseline_sha256 is None):
        raise ValueError(
            "reference resume requires its externally frozen baseline checksum"
        )
    if request.baseline is not None:
        if sha256_file(request.baseline) != request.expected_baseline_sha256:
            raise ValueError("reference first-pass checkpoint checksum changed")
        baseline = ReferenceChildOutputs.model_validate_json(
            request.baseline.read_bytes()
        )
        if baseline.phase != "first" or baseline.checkpoint_id != _identity(baseline):
            raise ValueError(
                "reference baseline is not an intact first-pass checkpoint"
            )
    tasks = collect_child_output_tasks(request.trace)
    logs = _logs(request.trace, request.output)
    manifest = ReferenceChildOutputs(
        checkpoint_id="pending",
        phase="first" if baseline is None else "resume",
        baseline_sha256=request.expected_baseline_sha256,
        source_sha256=source,
        trace_sha256=trace_sha,
        reference_result_sha256=result_sha,
        task_count=len(tasks),
        tasks=tasks,
        task_logs=logs,
    )
    if baseline is not None and (
        manifest.source_sha256 != baseline.source_sha256
        or manifest.reference_result_sha256 != baseline.reference_result_sha256
        or tuple(row.model_dump(exclude={"status"}) for row in manifest.tasks)
        != tuple(row.model_dump(exclude={"status"}) for row in baseline.tasks)
        or manifest.task_logs != baseline.task_logs
    ):
        raise ValueError(
            "reference cached source, result, child outputs or task logs changed"
        )
    if (
        source != _source_sha256()
        or result_sha != sha256_file(request.result)
        or trace_sha != sha256_file(request.trace)
    ):
        raise ValueError("reference checkpoint inputs changed during collection")
    manifest = manifest.model_copy(update={"checkpoint_id": _identity(manifest)})
    atomic_write_json(request.output, manifest.model_dump(mode="json"))
    return manifest
