"""Collect one bounded Phase III composition-search depth.

The collector verifies exactly one run-owned output directory for every selected
attempt in a :class:`CompositionAttemptInventory`. It rehashes each attempt's
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
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_ADAPTER_VERSION = "phase3-composition-beam-depth-v1"


class CompositionBeamError(InputContractError):
    """Attempt outputs cannot form one complete deterministic beam depth."""


class CompositionBeamDepthStatus(StrEnum):
    """Whether another component depth may be planned."""

    READY_NEXT_DEPTH = "ready_next_depth"
    TERMINAL = "terminal"


class CompositionBeamAttemptEvidence(_ContentAddressedContract):
    """One rehashed attempt and optional packed child-state evidence."""

    _identity_field: ClassVar[str] = "attempt_evidence_id"
    _identity_prefix: ClassVar[str] = "compbeamattempt_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["phase3-composition-beam-depth-v1"] = _ADAPTER_VERSION
    attempt_evidence_id: NonEmptyString
    attempt_id: CompositionAttemptIdentifier
    allocation_rank: int = Field(ge=1, le=25)
    result_id: NonEmptyString
    result_sha256: Sha256Hex
    checksums_sha256: Sha256Hex
    execution_status: ExecutionStatus
    child_state_id: NonEmptyString | None = None
    child_state_sha256: Sha256Hex | None = None
    child_support_state: CompositionSupportState | None = None
    score_evidence_id: NonEmptyString | None = None
    score_evidence_sha256: Sha256Hex | None = None
    combined_llg: float | None = None
    component_tfz: float | None = None

    @model_validator(mode="after")
    def _validate_child_evidence(self) -> Self:
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
    adapter_version: Literal["phase3-composition-beam-depth-v1"] = _ADAPTER_VERSION
    beam_result_id: NonEmptyString
    inventory_id: CompositionAttemptInventoryIdentifier
    inventory_sha256: Sha256Hex
    crystal_id: NonEmptyString
    parent_depth: int = Field(ge=1, le=5)
    target_depth: int = Field(ge=2, le=6)
    attempt_count: int = Field(ge=0, le=25)
    completed_hit_count: int = Field(ge=0, le=25)
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
        if self.global_attempts_used_after != (
            self.global_attempts_used_before + self.attempt_count
        ):
            raise ValueError("beam global attempt count is not conserved")
        if self.completed_hit_count != sum(
            item.execution_status is ExecutionStatus.COMPLETED_HIT
            for item in self.attempts
        ):
            raise ValueError("beam hit count differs from attempt evidence")
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
    beam_width: int = 3


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
    attempt_id: str,
    allocation_rank: int,
) -> tuple[CompositionBeamAttemptEvidence, CompositionState | None]:
    checksums = _verify_attempt_checksums(root)
    result_path = root / "composition_attempt_execution.json"
    try:
        result = CompositionAttemptExecutionResult.model_validate_json(
            result_path.read_bytes()
        )
    except (OSError, ValidationError, ValueError) as error:
        raise CompositionBeamError("attempt result violates its contract") from error
    if result.attempt_id != attempt_id:
        raise CompositionBeamError("attempt result belongs to another task")
    if result.execution_status is not ExecutionStatus.COMPLETED_HIT:
        return (
            CompositionBeamAttemptEvidence.from_content(
                attempt_id=attempt_id,
                allocation_rank=allocation_rank,
                result_id=result.attempt_result_id,
                result_sha256=sha256_file(result_path),
                checksums_sha256=sha256_file(checksums),
                execution_status=result.execution_status,
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
    selected_component = (
        score.execution_input.selected_candidate.hypothesis.component
    )
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
        attempt_id=attempt_id,
        allocation_rank=allocation_rank,
        result_id=result.attempt_result_id,
        result_sha256=sha256_file(result_path),
        checksums_sha256=sha256_file(checksums),
        execution_status=result.execution_status,
        child_state_id=state.state_id,
        child_state_sha256=sha256_file(state_path),
        child_support_state=state.support_state,
        score_evidence_id=score.score_evidence_id,
        score_evidence_sha256=sha256_file(score_path),
        combined_llg=score.combined_llg,
        component_tfz=score.component_tfz,
    )
    return evidence, state


def _stop_reason(
    *,
    target_depth: int,
    attempt_count: int,
    physical_hypothesis_count: int,
    global_attempts_used_after: int,
    retained_count: int,
) -> CompositionStopReason | None:
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
    if len(request.attempt_result_directories) != inventory.attempt_count:
        raise CompositionBeamError("attempt output count differs from the inventory")
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
    if set(by_attempt) != expected:
        raise CompositionBeamError("attempt output identities are incomplete")

    evidence_rows: list[CompositionBeamAttemptEvidence] = []
    packed: list[tuple[CompositionBeamAttemptEvidence, CompositionState, Path]] = []
    for task in inventory.attempts:
        evidence, state = _attempt_evidence(
            by_attempt[task.attempt_id],
            attempt_id=task.attempt_id,
            allocation_rank=task.allocation_rank,
        )
        evidence_rows.append(evidence)
        if state is not None and state.support_state is CompositionSupportState.PACKED:
            packed.append((evidence, state, by_attempt[task.attempt_id]))
    packed.sort(
        key=lambda item: (
            -(item[0].combined_llg or float("-inf")),
            -(item[0].component_tfz or float("-inf")),
            item[0].allocation_rank,
            item[1].state_id,
        )
    )
    retained = tuple(packed[: request.beam_width])
    plan = inventory.depth_plan
    used_after = plan.global_attempts_used_before + inventory.attempt_count
    stop_reason = _stop_reason(
        target_depth=plan.target_depth,
        attempt_count=inventory.attempt_count,
        physical_hypothesis_count=plan.physical_hypothesis_count,
        global_attempts_used_after=used_after,
        retained_count=len(retained),
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
        completed_hit_count=sum(
            item.execution_status is ExecutionStatus.COMPLETED_HIT
            for item in evidence_rows
        ),
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
    for task in inventory.attempts:
        shutil.copytree(
            by_attempt[task.attempt_id],
            output / "attempts" / task.attempt_id,
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
        scope_states = (
            tuple(state for _, state, _ in retained)
            if retained
            else (inventory.parent_states[0],)
        )
        terminal_review_states = scope_states
        remaining_physical = sum(
            candidate.hypothesis.physical_possible
            and candidate.hypothesis.disposition.value != "selected"
            for candidate in plan.candidates
        )
        for state in scope_states:
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
            elif stop_reason in {
                CompositionStopReason.GLOBAL_ATTEMPT_BUDGET_REACHED,
                CompositionStopReason.INFRASTRUCTURE_OR_CONTRACT_FAILURE,
                CompositionStopReason.REVIEWER_HOLD,
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
                stop_reason=stop_reason,
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
            assessment = CompositionAssessment.from_content(
                crystal_id=state.crystal_id,
                state_id=state.state_id,
                scope_decision=scope,
                execution_status=(
                    ExecutionStatus.COMPLETED_HIT
                    if retained
                    else ExecutionStatus.COMPLETED_NO_HIT
                ),
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
        "".join(
            f"{canonical_json_text(item)}\n" for item in terminal_review_states
        ),
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
