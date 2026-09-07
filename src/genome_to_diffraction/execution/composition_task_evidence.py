"""Retain terminal Nextflow evidence for a bounded composition depth.

The existing Nextflow trace supplies scheduler observations, never Phaser
scores. Each selected row is bound to the workflow session, logical attempt,
resource attempt, native task ID and owned work directory. The task command's
inventory checksum authenticates the join. Missing rows remain missing;
neither a native result nor an exit code is manufactured. This offline reader
does not submit, poll or retry work. Tests cover stale inventory/task evidence
and the distinction between missing output and a terminal scheduler failure.
"""

from __future__ import annotations

import csv
import io
import shlex
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import Field

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.schemas.base import NonEmptyString, Sha256Hex
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract
from genome_to_diffraction.schemas.v2.composition_attempts import (
    CompositionAttemptInventory,
)
from genome_to_diffraction.status import InputContractError


class CompositionTaskEvidenceError(InputContractError):
    """The scheduler trace cannot be authenticated against selected attempts."""


class CompositionTerminalTaskEvidence(_ContentAddressedContract):
    """One terminal scheduler observation, separate from any native result."""

    _identity_field: ClassVar[str] = "task_evidence_id"
    _identity_prefix: ClassVar[str] = "comptask_"

    schema_version: Literal["2.0"]
    task_evidence_id: NonEmptyString
    workflow_run_id: NonEmptyString
    inventory_sha256: Sha256Hex
    attempt_id: NonEmptyString
    resource_attempt: int = Field(ge=1, le=2)
    task_id: NonEmptyString
    native_task_id: NonEmptyString | None
    work_directory: NonEmptyString
    terminal_status: Literal["COMPLETED", "CACHED", "FAILED", "ABORTED"]
    exit_code: int | None
    trace_row_sha256: Sha256Hex
    command_sha256: Sha256Hex


def read_composition_terminal_tasks(
    *,
    trace_path: Path,
    workflow_run_id: str,
    task_work_root: Path,
    inventory_path: Path,
    inventory: CompositionAttemptInventory,
) -> tuple[CompositionTerminalTaskEvidence, ...]:
    """Read one trace snapshot and rehash every matching task's authority."""

    try:
        trace_text = trace_path.read_text(encoding="utf-8")
        work_root = task_work_root.resolve(strict=True)
    except (OSError, UnicodeError) as error:
        raise CompositionTaskEvidenceError("owned task trace/root is absent") from error
    reader = csv.DictReader(io.StringIO(trace_text), delimiter="\t")
    required = {
        "task_id",
        "native_id",
        "process",
        "tag",
        "status",
        "exit",
        "attempt",
        "workdir",
    }
    if not required <= set(reader.fieldnames or ()):
        raise CompositionTaskEvidenceError("task trace lacks required columns")
    expected = {task.attempt_id for task in inventory.attempts}
    inventory_sha256 = sha256_file(inventory_path)
    records: list[CompositionTerminalTaskEvidence] = []
    seen: set[tuple[str, int]] = set()
    for row in reader:
        if not row["process"].endswith(":RUN_PHASE3_BEAM_ATTEMPT") and (
            row["process"] != "RUN_PHASE3_BEAM_ATTEMPT"
        ):
            continue
        prefix = "composition-beam-attempt:"
        if not row["tag"].startswith(prefix):
            raise CompositionTaskEvidenceError("composition task tag is malformed")
        attempt_id = row["tag"][len(prefix) :]
        if attempt_id not in expected:
            continue  # Other depths/crystals share the run's trace.
        try:
            resource_attempt = int(row["attempt"])
            exit_code = None if row["exit"] == "-" else int(row["exit"])
            workdir = Path(row["workdir"]).resolve(strict=True)
            command = workdir / ".command.sh"
            tokens = shlex.split(command.read_text(encoding="utf-8"), comments=True)
            selected_id = tokens[tokens.index("--attempt-id") + 1]
            selected_inventory = Path(tokens[tokens.index("--attempt-inventory") + 1])
            if not selected_inventory.is_absolute():
                selected_inventory = workdir / selected_inventory
        except (OSError, UnicodeError, ValueError, IndexError) as error:
            raise CompositionTaskEvidenceError(
                "composition task authority is invalid"
            ) from error
        key = (attempt_id, resource_attempt)
        if (
            key in seen
            or work_root not in workdir.parents
            or selected_id != attempt_id
            or sha256_file(selected_inventory) != inventory_sha256
            or row["status"] not in {"COMPLETED", "CACHED", "FAILED", "ABORTED"}
            or (row["status"] in {"COMPLETED", "CACHED"} and exit_code != 0)
        ):
            raise CompositionTaskEvidenceError("composition task evidence differs")
        seen.add(key)
        records.append(
            CompositionTerminalTaskEvidence.from_content(
                workflow_run_id=workflow_run_id,
                inventory_sha256=inventory_sha256,
                attempt_id=attempt_id,
                resource_attempt=resource_attempt,
                task_id=row["task_id"],
                native_task_id=None if row["native_id"] == "-" else row["native_id"],
                work_directory=str(workdir),
                terminal_status=row["status"],
                exit_code=exit_code,
                trace_row_sha256=canonical_digest(row),
                command_sha256=sha256_file(command),
            )
        )
    return tuple(
        sorted(records, key=lambda item: (item.attempt_id, item.resource_attempt))
    )
