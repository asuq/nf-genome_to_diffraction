"""Collect one bounded Phase III composition-search depth.

The collector reconciles the complete expected inventory with observed native
outputs and terminal Nextflow evidence. It rehashes each attempt's
complete checksum inventory, retains every hit/no-hit/failure result, ranks only
fully packed child states, and publishes at most three parents for the next
depth. It performs no Phaser execution and makes no identity or complete-
composition claim. Depths four through six remain explicitly provisional.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import ClassVar, Literal, Self

from pydantic import Field, ValidationError, model_validator

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.execution.composition import (
    CompositionAttemptInventoryError,
    load_composition_attempt_inventory,
)
from genome_to_diffraction.execution.composition_runtime import (
    CompositionAttemptExecutionResult,
)
from genome_to_diffraction.execution.composition_task_evidence import (
    CompositionTerminalTaskEvidence,
    read_composition_terminal_tasks,
)
from genome_to_diffraction.ids import canonical_digest, canonical_json_text
from genome_to_diffraction.schemas.base import NonEmptyString, Sha256Hex
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.schemas.v2 import (
    ComponentExpansionScoreEvidence,
    ComponentScopeDecision,
    ComponentScopeStatus,
    CompositionAssessment,
    CompositionClaimBoundary,
    CompositionScientificStatus,
    CompositionState,
    CompositionStopReason,
    CompositionSupportState,
    ResidualContentState,
)
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract
from genome_to_diffraction.schemas.v2.composition_attempts import (
    CompositionAttemptIdentifier,
    CompositionAttemptInventoryIdentifier,
    CompositionAttemptTask,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_ADAPTER_VERSION = "phase3-composition-beam-depth-v2-complete-outcomes"


class CompositionBeamError(InputContractError):
    """Attempt outputs cannot form one complete deterministic beam depth."""


class CompositionBeamDepthStatus(StrEnum):
    """Whether another component depth may be planned."""

    READY_NEXT_DEPTH = "ready_next_depth"
    TERMINAL = "terminal"


class CompositionAttemptOutcome(StrEnum):
    """Observed native or scheduler outcome of one logical search."""

    COMPLETED_HIT = "completed_hit"
    COMPLETED_NO_HIT = "completed_no_hit"
    FAILED = "failed"
    MISSING_OUTPUT = "missing_output"
    UNEXECUTED = "unexecuted"


class CompositionBeamAttemptEvidence(_ContentAddressedContract):
    """One rehashed attempt and optional packed child-state evidence."""

    _identity_field: ClassVar[str] = "attempt_evidence_id"
    _identity_prefix: ClassVar[str] = "compbeamattempt_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["phase3-composition-beam-depth-v2-complete-outcomes"] = (
        _ADAPTER_VERSION
    )
    attempt_evidence_id: NonEmptyString
    attempt_id: CompositionAttemptIdentifier
    parent_state_id: NonEmptyString
    allocation_rank: int = Field(ge=1, le=25)
    outcome: CompositionAttemptOutcome
    result_id: NonEmptyString | None = None
    result_sha256: Sha256Hex | None = None
    checksums_sha256: Sha256Hex | None = None
    execution_status: ExecutionStatus | None = None
    resource_attempt: int | None = Field(default=None, ge=1, le=2)
    terminal_tasks: tuple[CompositionTerminalTaskEvidence, ...] = ()
    child_state_id: NonEmptyString | None = None
    child_state_sha256: Sha256Hex | None = None
    child_support_state: CompositionSupportState | None = None
    score_evidence_id: NonEmptyString | None = None
    score_evidence_sha256: Sha256Hex | None = None
    combined_llg: float | None = None
    component_tfz: float | None = None

    @model_validator(mode="after")
    def _validate_child_evidence(self) -> Self:
        native_fields = (
            self.result_id,
            self.result_sha256,
            self.checksums_sha256,
            self.execution_status,
            self.resource_attempt,
        )
        if any(value is not None for value in native_fields) != all(
            value is not None for value in native_fields
        ):
            raise ValueError("native result evidence must be complete or absent")
        if self.execution_status is not None:
            expected_outcome = _native_outcome(self.execution_status)
            if self.outcome is not expected_outcome:
                raise ValueError("attempt outcome differs from its native result")
        elif self.outcome in {
            CompositionAttemptOutcome.COMPLETED_HIT,
            CompositionAttemptOutcome.COMPLETED_NO_HIT,
        }:
            raise ValueError("scientific completion requires native evidence")
        if any(task.attempt_id != self.attempt_id for task in self.terminal_tasks):
            raise ValueError("terminal task belongs to another logical search")
        child_fields = (
            self.child_state_id,
            self.child_state_sha256,
            self.child_support_state,
            self.score_evidence_id,
            self.score_evidence_sha256,
            self.combined_llg,
            self.component_tfz,
        )
        if self.execution_status is ExecutionStatus.COMPLETED_HIT:
            if any(value is None for value in child_fields):
                raise ValueError("completed beam attempt lacks child evidence")
        elif any(value is not None for value in child_fields):
            raise ValueError("non-hit beam attempt contains child evidence")
        return self


class CompositionBeamDepthResult(_ContentAddressedContract):
    """Complete result for one parent depth and its selected attempt fan-out."""

    _identity_field: ClassVar[str] = "beam_result_id"
    _identity_prefix: ClassVar[str] = "compbeamdepth_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["phase3-composition-beam-depth-v2-complete-outcomes"] = (
        _ADAPTER_VERSION
    )
    beam_result_id: NonEmptyString
    inventory_id: CompositionAttemptInventoryIdentifier
    inventory_sha256: Sha256Hex
    crystal_id: NonEmptyString
    parent_depth: int = Field(ge=1, le=5)
    target_depth: int = Field(ge=2, le=6)
    attempt_count: int = Field(ge=0, le=25)
    completed_hit_count: int = Field(ge=0, le=25)
    completed_no_hit_count: int = Field(ge=0, le=25)
    failed_count: int = Field(ge=0, le=25)
    missing_output_count: int = Field(ge=0, le=25)
    unexecuted_count: int = Field(ge=0, le=25)
    depth_complete: bool
    retained_parent_count: int = Field(ge=0, le=3)
    global_attempts_used_before: int = Field(ge=0, le=100)
    global_attempts_used_after: int = Field(ge=0, le=100)
    status: CompositionBeamDepthStatus
    stop_reason: CompositionStopReason | None = None
    provisional_component_depth: bool
    retained_state_ids: tuple[NonEmptyString, ...]
    attempts: tuple[CompositionBeamAttemptEvidence, ...]

    @model_validator(mode="after")
    def _validate_depth_result(self) -> Self:
        if self.target_depth != self.parent_depth + 1:
            raise ValueError("beam target depth must follow its parent depth")
        if self.attempt_count != len(self.attempts):
            raise ValueError("beam attempt count differs from its evidence")
        if len({item.attempt_id for item in self.attempts}) != self.attempt_count or (
            tuple(item.allocation_rank for item in self.attempts)
            != tuple(range(1, self.attempt_count + 1))
        ):
            raise ValueError("beam attempts must retain their unique inventory order")
        if self.global_attempts_used_after != (
            self.global_attempts_used_before + self.attempt_count
        ):
            raise ValueError("beam global attempt count is not conserved")
        if self.completed_hit_count != sum(
            item.execution_status is ExecutionStatus.COMPLETED_HIT
            for item in self.attempts
        ):
            raise ValueError("beam hit count differs from attempt evidence")
        for name, outcome in (
            ("completed_no_hit_count", CompositionAttemptOutcome.COMPLETED_NO_HIT),
            ("failed_count", CompositionAttemptOutcome.FAILED),
            ("missing_output_count", CompositionAttemptOutcome.MISSING_OUTPUT),
            ("unexecuted_count", CompositionAttemptOutcome.UNEXECUTED),
        ):
            if getattr(self, name) != sum(
                item.outcome is outcome for item in self.attempts
            ):
                raise ValueError(f"beam {name} differs from attempt evidence")
        complete = (
            self.completed_hit_count + self.completed_no_hit_count == self.attempt_count
        )
        if self.depth_complete != complete:
            raise ValueError("beam completeness differs from attempt outcomes")
        if not complete and (
            self.status is not CompositionBeamDepthStatus.TERMINAL
            or self.stop_reason
            is not CompositionStopReason.COMPOSITION_DEPTH_INCOMPLETE
        ):
            raise ValueError("an incomplete depth must stop automatic advancement")
        if self.retained_parent_count != len(self.retained_state_ids):
            raise ValueError("beam retained-parent count differs")
        if len(set(self.retained_state_ids)) != len(self.retained_state_ids):
            raise ValueError("beam retained parent states are duplicated")
        if (self.status is CompositionBeamDepthStatus.TERMINAL) != (
            self.stop_reason is not None
        ):
            raise ValueError("beam terminal status and stop reason must be paired")
        if self.status is CompositionBeamDepthStatus.READY_NEXT_DEPTH and (
            self.retained_parent_count < 1
            or self.target_depth >= 6
            or self.global_attempts_used_after >= 100
        ):
            raise ValueError("beam cannot continue beyond its retained/budget bounds")
        if self.provisional_component_depth != (self.target_depth >= 4):
            raise ValueError("beam provisional-depth marker differs")
        return self


@dataclass(frozen=True, slots=True)
class CompositionBeamCollectionRequest:
    """One exact attempt inventory and all of its task output directories."""

    attempt_inventory: Path
    attempt_result_directories: tuple[Path, ...]
    output_directory: Path
    fixed_coordinate_root: Path
    beam_width: int = 3
    scheduler_trace: Path | None = None
    workflow_run_id: str | None = None
    task_work_root: Path | None = None


@dataclass(frozen=True, slots=True)
class CompositionBeamCollectionOutput:
    """Published depth result, retained parents, and complete checksums."""

    result: CompositionBeamDepthResult
    result_json: Path
    retained_states_jsonl: Path
    attempt_evidence_jsonl: Path
    scope_decisions_jsonl: Path
    assessments_jsonl: Path
    checksums: Path


def _regular_directory(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise CompositionBeamError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise CompositionBeamError(f"{label} is absent") from error
    if not resolved.is_dir():
        raise CompositionBeamError(f"{label} must be a directory")
    return resolved


def _verify_attempt_checksums(root: Path) -> Path:
    manifest = root / "composition_attempt_checksums.sha256"
    if manifest.is_symlink() or not manifest.is_file():
        raise CompositionBeamError("attempt checksum manifest is absent")
    declared: dict[str, str] = {}
    try:
        lines = manifest.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as error:
        raise CompositionBeamError("attempt checksum manifest is unreadable") from error
    for line in lines:
        fields = line.split("  ", maxsplit=1)
        if len(fields) != 2:
            raise CompositionBeamError("attempt checksum row is malformed")
        digest, relative_text = fields
        relative = PurePosixPath(relative_text)
        if (
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or relative.is_absolute()
            or ".." in relative.parts
            or relative_text in declared
        ):
            raise CompositionBeamError("attempt checksum row is unsafe")
        path = root.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file() or sha256_file(path) != digest:
            raise CompositionBeamError("attempt checksum evidence differs")
        declared[relative_text] = digest
    actual: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise CompositionBeamError("attempt output contains a symlink")
        if path.is_file() and path != manifest:
            actual.add(path.relative_to(root).as_posix())
    if actual != set(declared):
        raise CompositionBeamError("attempt checksum inventory is incomplete")
    return manifest


def _attempt_evidence(
    root: Path,
    *,
    task: CompositionAttemptTask,
    crystal_id: str,
    terminal_tasks: tuple[CompositionTerminalTaskEvidence, ...],
) -> tuple[CompositionBeamAttemptEvidence, CompositionState | None]:
    checksums = _verify_attempt_checksums(root)
    result_path = root / "composition_attempt_execution.json"
    try:
        result = CompositionAttemptExecutionResult.model_validate_json(
            result_path.read_bytes()
        )
    except (OSError, ValidationError, ValueError) as error:
        raise CompositionBeamError("attempt result violates its contract") from error
    if (
        result.attempt_id != task.attempt_id
        or result.parent_state_id != task.parent_state_id
        or result.execution_input_id != task.component_execution_input_id
        or result.resource_plan_id != task.resource_plan.resource_plan_id
        or result.candidate_component_spec_id != task.component_spec_id
        or result.crystal_id != crystal_id
    ):
        raise CompositionBeamError("attempt result belongs to another task")
    if terminal_tasks and (
        terminal_tasks[-1].resource_attempt != result.resource_attempt
        or terminal_tasks[-1].terminal_status not in {"COMPLETED", "CACHED"}
    ):
        raise CompositionBeamError("native result differs from final scheduler attempt")
    common = {
        "attempt_id": task.attempt_id,
        "parent_state_id": task.parent_state_id,
        "allocation_rank": task.allocation_rank,
        "outcome": _native_outcome(result.execution_status),
        "result_id": result.attempt_result_id,
        "result_sha256": sha256_file(result_path),
        "checksums_sha256": sha256_file(checksums),
        "execution_status": result.execution_status,
        "resource_attempt": result.resource_attempt,
        "terminal_tasks": terminal_tasks,
    }
    if result.execution_status is not ExecutionStatus.COMPLETED_HIT:
        return (
            CompositionBeamAttemptEvidence.from_content(
                **common,
            ),
            None,
        )
    state_path = root / "composition_state.json"
    score_path = root / "component_score_evidence.json"
    try:
        state = CompositionState.model_validate_json(state_path.read_bytes())
        score = ComponentExpansionScoreEvidence.model_validate_json(
            score_path.read_bytes()
        )
    except (OSError, ValidationError, ValueError) as error:
        raise CompositionBeamError(
            "attempt child evidence violates its contract"
        ) from error
    selected_component = score.execution_input.selected_candidate.hypothesis.component
    if (
        result.child_state_id != state.state_id
        or result.child_state_sha256 != sha256_file(state_path)
        or result.child_support_state is not state.support_state
        or result.score_evidence_id != score.score_evidence_id
        or result.score_evidence_sha256 != sha256_file(score_path)
        or score.execution_input.parent_state.state_id != result.parent_state_id
        or selected_component.component_spec_id != result.candidate_component_spec_id
        or score.combined_llg is None
        or score.component_tfz is None
    ):
        raise CompositionBeamError("attempt result and child evidence differ")
    evidence = CompositionBeamAttemptEvidence.from_content(
        **common,
        child_state_id=state.state_id,
        child_state_sha256=sha256_file(state_path),
        child_support_state=state.support_state,
        score_evidence_id=score.score_evidence_id,
        score_evidence_sha256=sha256_file(score_path),
        combined_llg=score.combined_llg,
        component_tfz=score.component_tfz,
    )
    return evidence, state


def _native_outcome(status: ExecutionStatus) -> CompositionAttemptOutcome:
    if status is ExecutionStatus.COMPLETED_HIT:
        return CompositionAttemptOutcome.COMPLETED_HIT
    if status is ExecutionStatus.COMPLETED_NO_HIT:
        return CompositionAttemptOutcome.COMPLETED_NO_HIT
    if status in {
        ExecutionStatus.FAILED_TOOL_EXECUTION,
        ExecutionStatus.FAILED_PARSE,
        ExecutionStatus.FAILED_INFRASTRUCTURE,
        ExecutionStatus.FAILED_INPUT_CONTRACT,
    }:
        return CompositionAttemptOutcome.FAILED
    raise ValueError("composition attempt status is not terminal")


def _stop_reason(
    *,
    target_depth: int,
    attempt_count: int,
    physical_hypothesis_count: int,
    global_attempts_used_after: int,
    retained_count: int,
    depth_complete: bool,
) -> CompositionStopReason | None:
    if not depth_complete:
        return CompositionStopReason.COMPOSITION_DEPTH_INCOMPLETE
    if physical_hypothesis_count == 0:
        return CompositionStopReason.NO_PHYSICALLY_POSSIBLE_REMAINING_COMPONENT
    if retained_count == 0:
        return CompositionStopReason.NO_RETAINED_PACKED_STATE
    if target_depth == 6:
        return CompositionStopReason.MAXIMUM_COMPONENT_DEPTH_REACHED
    if global_attempts_used_after == 100:
        return CompositionStopReason.GLOBAL_ATTEMPT_BUDGET_REACHED
    if attempt_count == 0:
        return CompositionStopReason.NO_RETAINED_PACKED_STATE
    return None


def _copy_parent_assets(
    root: Path,
    output: Path,
    states: tuple[CompositionState, ...],
) -> None:
    """Retain the exact combined and component assets for every input parent."""

    root = _regular_directory(root, label="fixed-coordinate root")
    assets: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() in {".pdb", ".mtz"} and path.is_file():
            if path.is_symlink():
                raise CompositionBeamError("parent asset must not be a symlink")
            assets.setdefault(sha256_file(path), path)
    for state in states:
        destination = output / "parent_evidence" / state.state_id
        destination.mkdir(parents=True)
        atomic_write_json(
            destination / "composition_state.json", state.model_dump(mode="json")
        )
        required = {
            "combined.pdb": state.combined_coordinate_sha256,
            "combined.mtz": state.combined_mtz_sha256,
            **{
                f"component_{item.component_label}.pdb": item.coordinate_sha256
                for item in state.placements
            },
        }
        for name, digest in required.items():
            if digest is None:
                continue
            source = assets.get(digest)
            if source is None:
                raise CompositionBeamError(
                    "input parent lacks its declared review asset"
                )
            shutil.copy2(source, destination / name)


def _retain_task_diagnostics(
    output: Path,
    tasks: tuple[CompositionTerminalTaskEvidence, ...],
    native_results: set[tuple[str, int | None]],
) -> None:
    """Keep both resource attempts without creating extra scientific searches."""

    for task in tasks:
        source = Path(task.work_directory)
        destination = (
            output
            / "task_diagnostics"
            / task.attempt_id
            / f"attempt-{task.resource_attempt}"
        )
        destination.mkdir(parents=True)
        atomic_write_json(
            destination / "terminal_task.json", task.model_dump(mode="json")
        )
        for name in (
            ".command.sh",
            ".command.out",
            ".command.err",
            ".command.log",
            ".exitcode",
        ):
            path = source / name
            if path.is_symlink():
                raise CompositionBeamError("task diagnostic must not be a symlink")
            if path.is_file():
                shutil.copy2(path, destination / name)
        native = source / f"composition_attempt_{task.attempt_id}"
        if (
            native.is_dir()
            and (task.attempt_id, task.resource_attempt) not in native_results
        ):
            if native.is_symlink() or any(
                path.is_symlink() for path in native.rglob("*")
            ):
                raise CompositionBeamError("task diagnostics contain a symlink")
            shutil.copytree(native, destination / "native_outputs")


def collect_composition_beam_depth(
    request: CompositionBeamCollectionRequest,
) -> CompositionBeamCollectionOutput:
    """Verify one complete depth and retain at most three packed child states."""

    if not 1 <= request.beam_width <= 3:
        raise ValueError("beam width must be between one and three")
    try:
        inventory = load_composition_attempt_inventory(request.attempt_inventory)
    except CompositionAttemptInventoryError as error:
        raise CompositionBeamError("attempt inventory is invalid") from error
    trace_fields = (
        request.scheduler_trace,
        request.workflow_run_id,
        request.task_work_root,
    )
    if any(value is not None for value in trace_fields) != all(
        value is not None for value in trace_fields
    ):
        raise CompositionBeamError(
            "scheduler trace, run identity and work root must be paired"
        )
    terminal_tasks = (
        read_composition_terminal_tasks(
            trace_path=request.scheduler_trace,
            workflow_run_id=request.workflow_run_id,
            task_work_root=request.task_work_root,
            inventory_path=request.attempt_inventory,
            inventory=inventory,
        )
        if request.scheduler_trace is not None
        and request.workflow_run_id is not None
        and request.task_work_root is not None
        else ()
    )
    by_attempt: dict[str, Path] = {}
    for directory in request.attempt_result_directories:
        root = _regular_directory(directory, label="attempt output")
        try:
            document = load_json_document(root / "composition_attempt_execution.json")
        except ContractLoadError as error:
            raise CompositionBeamError("attempt result is malformed") from error
        if not isinstance(document, dict) or not isinstance(
            document.get("attempt_id"), str
        ):
            raise CompositionBeamError("attempt result lacks its identity")
        attempt_id = str(document["attempt_id"])
        if attempt_id in by_attempt:
            raise CompositionBeamError("attempt output is duplicated")
        by_attempt[attempt_id] = root
    expected = {task.attempt_id for task in inventory.attempts}
    if set(by_attempt) - expected:
        raise CompositionBeamError("attempt output identity is outside the inventory")

    evidence_rows: list[CompositionBeamAttemptEvidence] = []
    observed_states: list[CompositionState] = []
    packed: list[tuple[CompositionBeamAttemptEvidence, CompositionState, Path]] = []
    for task in inventory.attempts:
        task_evidence = tuple(
            item for item in terminal_tasks if item.attempt_id == task.attempt_id
        )
        if task.attempt_id not in by_attempt:
            outcome = CompositionAttemptOutcome.MISSING_OUTPUT
            if task_evidence and task_evidence[-1].terminal_status in {
                "FAILED",
                "ABORTED",
            }:
                outcome = CompositionAttemptOutcome.FAILED
                final_task = task_evidence[-1]
                if (
                    final_task.terminal_status == "ABORTED"
                    and final_task.native_task_id is None
                    and final_task.exit_code is None
                ):
                    outcome = CompositionAttemptOutcome.UNEXECUTED
            evidence_rows.append(
                CompositionBeamAttemptEvidence.from_content(
                    attempt_id=task.attempt_id,
                    parent_state_id=task.parent_state_id,
                    allocation_rank=task.allocation_rank,
                    outcome=outcome,
                    terminal_tasks=task_evidence,
                )
            )
            continue
        evidence, state = _attempt_evidence(
            by_attempt[task.attempt_id],
            task=task,
            crystal_id=inventory.depth_plan.crystal_id,
            terminal_tasks=task_evidence,
        )
        evidence_rows.append(evidence)
        if state is not None:
            observed_states.append(state)
        if state is not None and state.support_state is CompositionSupportState.PACKED:
            packed.append((evidence, state, by_attempt[task.attempt_id]))
    packed.sort(
        key=lambda item: (
            -(
                item[0].combined_llg
                if item[0].combined_llg is not None
                else float("-inf")
            ),
            -(
                item[0].component_tfz
                if item[0].component_tfz is not None
                else float("-inf")
            ),
            item[0].allocation_rank,
            item[1].state_id,
        )
    )
    retained = tuple(packed[: request.beam_width])
    plan = inventory.depth_plan
    used_after = plan.global_attempts_used_before + inventory.attempt_count
    counts = {
        outcome: sum(item.outcome is outcome for item in evidence_rows)
        for outcome in CompositionAttemptOutcome
    }
    depth_complete = (
        counts[CompositionAttemptOutcome.COMPLETED_HIT]
        + counts[CompositionAttemptOutcome.COMPLETED_NO_HIT]
        == inventory.attempt_count
    )
    stop_reason = _stop_reason(
        target_depth=plan.target_depth,
        attempt_count=inventory.attempt_count,
        physical_hypothesis_count=plan.physical_hypothesis_count,
        global_attempts_used_after=used_after,
        retained_count=len(retained),
        depth_complete=depth_complete,
    )
    status = (
        CompositionBeamDepthStatus.TERMINAL
        if stop_reason is not None
        else CompositionBeamDepthStatus.READY_NEXT_DEPTH
    )
    result = CompositionBeamDepthResult.from_content(
        inventory_id=inventory.inventory_id,
        inventory_sha256=sha256_file(request.attempt_inventory),
        crystal_id=plan.crystal_id,
        parent_depth=plan.parent_depth,
        target_depth=plan.target_depth,
        attempt_count=inventory.attempt_count,
        completed_hit_count=counts[CompositionAttemptOutcome.COMPLETED_HIT],
        completed_no_hit_count=counts[CompositionAttemptOutcome.COMPLETED_NO_HIT],
        failed_count=counts[CompositionAttemptOutcome.FAILED],
        missing_output_count=counts[CompositionAttemptOutcome.MISSING_OUTPUT],
        unexecuted_count=counts[CompositionAttemptOutcome.UNEXECUTED],
        depth_complete=depth_complete,
        retained_parent_count=len(retained),
        global_attempts_used_before=plan.global_attempts_used_before,
        global_attempts_used_after=used_after,
        status=status,
        stop_reason=stop_reason,
        provisional_component_depth=plan.target_depth >= 4,
        retained_state_ids=tuple(state.state_id for _, state, _ in retained),
        attempts=tuple(evidence_rows),
    )

    output = request.output_directory.resolve()
    if output.exists() or output.is_symlink():
        raise CompositionBeamError("beam output must be absent")
    output.mkdir(parents=True)
    _copy_parent_assets(request.fixed_coordinate_root, output, inventory.parent_states)
    _retain_task_diagnostics(
        output,
        terminal_tasks,
        {
            (item.attempt_id, item.resource_attempt)
            for item in evidence_rows
            if item.result_id is not None
        },
    )
    shutil.copy2(
        request.attempt_inventory, output / "composition_attempt_inventory.json"
    )
    for attempt_id, root in by_attempt.items():
        shutil.copytree(
            root,
            output / "attempts" / attempt_id,
        )
    parent_outcomes = []
    for parent in inventory.parent_states:
        rows = tuple(
            item for item in evidence_rows if item.parent_state_id == parent.state_id
        )
        parent_outcomes.append(
            {
                "parent_state_id": parent.state_id,
                "attempt_ids": tuple(item.attempt_id for item in rows),
                "outcome_counts": {
                    outcome.value: sum(item.outcome is outcome for item in rows)
                    for outcome in CompositionAttemptOutcome
                },
                "extension_complete": all(
                    item.outcome
                    in {
                        CompositionAttemptOutcome.COMPLETED_HIT,
                        CompositionAttemptOutcome.COMPLETED_NO_HIT,
                    }
                    for item in rows
                ),
                "selected_child_state_ids": tuple(
                    state.state_id
                    for _, state, _ in retained
                    if state.parent_state_id == parent.state_id
                ),
                "observed_child_state_ids": tuple(
                    state.state_id
                    for state in observed_states
                    if state.parent_state_id == parent.state_id
                ),
            }
        )
    atomic_write_text(
        output / "parent_extension_outcomes.jsonl",
        "".join(f"{canonical_json_text(item)}\n" for item in parent_outcomes),
    )
    retained_states = output / "retained_parent_states.jsonl"
    atomic_write_text(
        retained_states,
        "".join(f"{canonical_json_text(state)}\n" for _, state, _ in retained),
    )
    attempt_evidence = output / "attempt_evidence.jsonl"
    atomic_write_text(
        attempt_evidence,
        "".join(f"{canonical_json_text(item)}\n" for item in evidence_rows),
    )
    result_json = output / "composition_beam_depth_result.json"
    atomic_write_json(result_json, result.model_dump(mode="json"))
    scope_decisions = output / "component_scope_decisions.jsonl"
    assessments = output / "composition_assessments.jsonl"
    scope_rows: list[ComponentScopeDecision] = []
    assessment_rows: list[CompositionAssessment] = []
    terminal_review_states: tuple[CompositionState, ...] = ()
    if stop_reason is not None:
        scope_states = (*inventory.parent_states, *observed_states)
        terminal_review_states = scope_states
        remaining_physical = sum(
            candidate.hypothesis.physical_possible
            and candidate.hypothesis.disposition.value != "selected"
            for candidate in plan.candidates
        )
        remaining_physical += (
            result.failed_count + result.missing_output_count + result.unexecuted_count
        )
        for state in scope_states:
            state_stop = stop_reason
            if (
                state.depth < plan.target_depth
                and stop_reason is CompositionStopReason.MAXIMUM_COMPONENT_DEPTH_REACHED
            ):
                state_stop = CompositionStopReason.EXTENSIONS_RETAINED_FOR_REVIEW
            if state.depth > 3:
                scope_status = (
                    ComponentScopeStatus.PROVISIONAL_UNVALIDATED_COMPONENT_DEPTH
                )
                claim_boundary = (
                    CompositionClaimBoundary.PROVISIONAL_UNVALIDATED_COMPONENT_DEPTH
                )
                scientific_status = (
                    CompositionScientificStatus.PROVISIONAL_UNVALIDATED_COMPONENT_DEPTH
                )
            elif state_stop in {
                CompositionStopReason.GLOBAL_ATTEMPT_BUDGET_REACHED,
                CompositionStopReason.INFRASTRUCTURE_OR_CONTRACT_FAILURE,
                CompositionStopReason.REVIEWER_HOLD,
                CompositionStopReason.COMPOSITION_DEPTH_INCOMPLETE,
            }:
                scope_status = ComponentScopeStatus.SEARCH_INCOMPLETE
                claim_boundary = CompositionClaimBoundary.SEARCH_INCOMPLETE
                scientific_status = CompositionScientificStatus.SEARCH_EVIDENCE_ONLY
            else:
                scope_status = ComponentScopeStatus.WITHIN_VALIDATED_COMPONENT_DEPTH
                claim_boundary = CompositionClaimBoundary.PARTIAL_OR_RESIDUAL_ONLY
                scientific_status = CompositionScientificStatus.SEARCH_EVIDENCE_ONLY
            scope = ComponentScopeDecision.from_content(
                crystal_id=state.crystal_id,
                state_id=state.state_id,
                search_depth_reached=state.depth,
                maximum_search_depth=6,
                validated_component_depth=3,
                total_additional_attempt_budget=100,
                total_additional_attempts_used=used_after,
                remaining_physical_hypothesis_count=remaining_physical,
                retained_packed_state_count=len(retained),
                state_support_state=state.support_state,
                stop_reason=state_stop,
                residual_content_state=ResidualContentState.NOT_ASSESSED,
                scope_status=scope_status,
                claim_boundary=claim_boundary,
                complete_composition_claim_eligible=False,
                warnings=(
                    ("provisional_unvalidated_component_depth",)
                    if state.depth > 3
                    else ()
                ),
            )
            # A parent's extension outcome is independent of sibling parents.
            # The parent's already placed coordinates remain review evidence.
            extensions = tuple(
                item for item in evidence_rows if item.parent_state_id == state.state_id
            )
            failed = tuple(
                item
                for item in extensions
                if item.outcome
                in {
                    CompositionAttemptOutcome.FAILED,
                    CompositionAttemptOutcome.MISSING_OUTPUT,
                    CompositionAttemptOutcome.UNEXECUTED,
                }
            )
            execution_status = ExecutionStatus.COMPLETED_HIT
            if failed:
                execution_status = next(
                    (
                        item.execution_status
                        for item in failed
                        if item.execution_status is not None
                    ),
                    ExecutionStatus.FAILED_INFRASTRUCTURE,
                )
                scientific_status = CompositionScientificStatus.EXECUTION_FAILURE
            elif extensions and not any(
                item.outcome is CompositionAttemptOutcome.COMPLETED_HIT
                for item in extensions
            ):
                execution_status = ExecutionStatus.COMPLETED_NO_HIT
            assessment = CompositionAssessment.from_content(
                crystal_id=state.crystal_id,
                state_id=state.state_id,
                scope_decision=scope,
                execution_status=execution_status,
                state_support_state=state.support_state,
                scientific_status=scientific_status,
                complete_composition_claim_eligible=False,
                complete_composition_claimed=False,
                evidence_sha256={
                    "beam_depth_result": sha256_file(result_json),
                    "composition_state": canonical_digest(state),
                },
                warnings=scope.warnings,
            )
            scope_rows.append(scope)
            assessment_rows.append(assessment)
    atomic_write_text(
        scope_decisions,
        "".join(f"{canonical_json_text(item)}\n" for item in scope_rows),
    )
    atomic_write_text(
        assessments,
        "".join(f"{canonical_json_text(item)}\n" for item in assessment_rows),
    )
    atomic_write_text(
        output / "terminal_review_states.jsonl",
        "".join(f"{canonical_json_text(item)}\n" for item in terminal_review_states),
    )
    checksums = output / "composition_beam_depth_checksums.sha256"
    retained_files = tuple(
        sorted(
            (
                path
                for path in output.rglob("*")
                if path.is_file() and path != checksums
            ),
            key=lambda path: path.relative_to(output).as_posix(),
        )
    )
    atomic_write_text(
        checksums,
        "".join(
            f"{sha256_file(path)}  {path.relative_to(output).as_posix()}\n"
            for path in retained_files
        ),
    )
    return CompositionBeamCollectionOutput(
        result=result,
        result_json=result_json,
        retained_states_jsonl=retained_states,
        attempt_evidence_jsonl=attempt_evidence,
        scope_decisions_jsonl=scope_decisions,
        assessments_jsonl=assessments,
        checksums=checksums,
    )


__all__ = [
    "CompositionBeamAttemptEvidence",
    "CompositionBeamCollectionOutput",
    "CompositionBeamCollectionRequest",
    "CompositionBeamDepthResult",
    "CompositionBeamDepthStatus",
    "CompositionBeamError",
    "collect_composition_beam_depth",
]
