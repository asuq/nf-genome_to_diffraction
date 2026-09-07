"""Publish terminal Phase III pass-2 composition and sequence review packages.

Terminal summaries, every input parent and every observed child remain
reviewable independently of the three-state continuing beam. Packing and MR
scores remain search evidence. The sequence package
offers catalogue sequence groups only as review targets; without later map-
supported approval, ``no_assignment`` remains the scientifically valid result.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.execution.composition import (
    load_composition_attempt_inventory,
)
from genome_to_diffraction.execution.composition_beam import (
    CompositionBeamDepthResult,
    CompositionBeamDepthStatus,
)
from genome_to_diffraction.review.phase3_package import (
    PhaseIIIReviewEvidenceSource,
    PhaseIIIReviewPackageOutput,
    PhaseIIIReviewPackageRequest,
    build_phase3_review_package,
)
from genome_to_diffraction.schemas.v2 import (
    CompositionState,
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
)
from genome_to_diffraction.status import InputContractError


class Pass2ReviewPackageError(InputContractError):
    """Terminal beam evidence cannot form its mandatory human handoff."""


@dataclass(frozen=True, slots=True)
class Pass2ReviewPackageOutput:
    """Owned composition and sequence packages for one terminal crystal."""

    composition: PhaseIIIReviewPackageOutput
    sequence: PhaseIIIReviewPackageOutput


def _root(path: Path) -> Path:
    if path.is_symlink():
        raise Pass2ReviewPackageError("terminal beam root must not be a symlink")
    try:
        root = path.resolve(strict=True)
    except OSError as error:
        raise Pass2ReviewPackageError("terminal beam root is absent") from error
    if not root.is_dir():
        raise Pass2ReviewPackageError("terminal beam root must be a directory")
    return root


def _verify_checksums(root: Path) -> None:
    manifest = root / "composition_beam_depth_checksums.sha256"
    if manifest.is_symlink():
        raise Pass2ReviewPackageError("terminal beam checksums must not be a symlink")
    try:
        lines = manifest.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as error:
        raise Pass2ReviewPackageError("terminal beam checksums are absent") from error
    declared: set[Path] = set()
    for line in lines:
        fields = line.split("  ", maxsplit=1)
        if len(fields) != 2:
            raise Pass2ReviewPackageError("terminal beam checksum row is malformed")
        digest, relative_text = fields
        relative = PurePosixPath(relative_text)
        path = root.joinpath(*relative.parts)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or path in declared
            or path.is_symlink()
            or not path.is_file()
            or sha256_file(path) != digest
        ):
            raise Pass2ReviewPackageError("terminal beam checksum evidence differs")
        declared.add(path)
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise Pass2ReviewPackageError("terminal beam contains a symlink")
        if path.is_file() and path != manifest:
            actual.add(path)
    if actual != declared:
        raise Pass2ReviewPackageError("terminal beam checksum inventory is incomplete")


def _states(root: Path) -> tuple[CompositionState, ...]:
    path = root / "terminal_review_states.jsonl"
    try:
        states = tuple(
            CompositionState.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise Pass2ReviewPackageError("terminal review states are invalid") from error
    if not 1 <= len(states) <= 28 or len({state.state_id for state in states}) != len(
        states
    ):
        raise Pass2ReviewPackageError(
            "terminal review requires unique bounded parent/child states"
        )
    return states


def build_pass2_review_packages(
    *,
    beam_directory: Path,
    execution_identity: Path,
    owned_parent_run_id: str,
    crystal_id: str,
    output_directory: Path,
) -> Pass2ReviewPackageOutput:
    """Build independent composition and sequence handoffs for one beam stop."""

    root = _root(beam_directory)
    _verify_checksums(root)
    try:
        result = CompositionBeamDepthResult.model_validate_json(
            (root / "composition_beam_depth_result.json").read_bytes()
        )
        identity = PhaseIIIExecutionIdentity.model_validate_json(
            execution_identity.read_bytes()
        )
    except (OSError, ValidationError, ValueError) as error:
        raise Pass2ReviewPackageError("terminal beam identity is invalid") from error
    states = _states(root)
    inventory_path = root / "composition_attempt_inventory.json"
    inventory = load_composition_attempt_inventory(inventory_path)
    expected_state_ids = {
        *(state.state_id for state in inventory.parent_states),
        *(
            item.child_state_id
            for item in result.attempts
            if item.child_state_id is not None
        ),
    }
    if (
        result.status is not CompositionBeamDepthStatus.TERMINAL
        or result.crystal_id != crystal_id
        or any(state.crystal_id != crystal_id for state in states)
        or not owned_parent_run_id.startswith("gtd-unknown-pass2-")
        or sha256_file(inventory_path) != result.inventory_sha256
        or {state.state_id for state in states} != expected_state_ids
    ):
        raise Pass2ReviewPackageError("terminal beam belongs to another authority")
    summary_names = {
        "composition_beam_depth_result.json",
        "attempt_evidence.jsonl",
        "retained_parent_states.jsonl",
        "terminal_review_states.jsonl",
        "component_scope_decisions.jsonl",
        "composition_assessments.jsonl",
        "composition_beam_depth_checksums.sha256",
        "composition_attempt_inventory.json",
        "parent_extension_outcomes.jsonl",
    }
    evidence_paths = {path for name in summary_names if (path := root / name).is_file()}
    state_ids = {state.state_id for state in states}
    for directory_name in ("attempts", "parent_evidence", "task_diagnostics"):
        evidence_paths.update(
            path for path in (root / directory_name).rglob("*") if path.is_file()
        )
    sources = tuple(
        PhaseIIIReviewEvidenceSource(
            role=f"pass2_terminal_evidence_{index:05d}",
            relative_path=path.relative_to(root).as_posix(),
        )
        for index, path in enumerate(
            sorted(evidence_paths, key=lambda item: item.relative_to(root).as_posix()),
            start=1,
        )
    )
    composition_targets = tuple(sorted(state_ids))
    sequence_targets = tuple(
        sorted(
            {
                component.sequence_group_id
                for state in states
                for component in state.components
            }
        )
    )
    output = output_directory.resolve()
    if output.exists() or output.is_symlink():
        raise Pass2ReviewPackageError("pass-2 review output must be absent")
    output.mkdir(parents=True)
    composition_output = output / "composition"
    sequence_output = output / "sequence"
    composition_output.mkdir()
    sequence_output.mkdir()
    common = {
        "owned_parent_run_id": owned_parent_run_id,
        "parent_profile": "unknown-pass2",
        "parent_phase": "phase3-pass2",
        "execution_identity_id": identity.execution_identity_id,
        "crystal_id": crystal_id,
        "created_at": datetime.now(UTC),
        "input_root": root,
        "evidence_sources": sources,
    }
    composition = build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=PhaseIIIReviewCheckpoint.COMPOSITION,
            target_item_ids=composition_targets,
            output_directory=composition_output,
            **common,
        )
    )
    sequence = build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=PhaseIIIReviewCheckpoint.SEQUENCE,
            target_item_ids=sequence_targets,
            output_directory=sequence_output,
            **common,
        )
    )
    return Pass2ReviewPackageOutput(composition=composition, sequence=sequence)


__all__ = [
    "Pass2ReviewPackageError",
    "Pass2ReviewPackageOutput",
    "build_pass2_review_packages",
]
