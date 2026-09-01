"""Validate and locally stage one Phase III human-review decision file.

Scientific purpose
------------------
This boundary prevents a decision for a stale run, review package, checkpoint, or
target from entering the unknown-crystal workflow.  It validates the existing
schema-v2 decision semantics, including checkpoint-specific retained-state caps,
without interpreting a human decision as scientific evidence by itself.

Inputs and outputs
------------------
The input is one trusted local parent reference, one checksum-bound Phase III
review-package manifest, one JSON or TSV decision file, and the independently
confirmed SHA-256 of that decision file.  A successful call creates a previously
absent output directory containing exactly ``phase3_review_decision.json`` and
``phase3_review_stage_manifest.json``.  The first is a deterministic canonical
typed JSON rendering; the second records every verified provenance binding and
both source/canonical checksums.

No external command or tool version is required.  Every input, chronology,
membership, or publication-contract failure raises ``PhaseIIIReviewStageError``;
no partial scientific status is emitted.  The deterministic cache key is
``stage_id``, derived from adapter version, parent/checkpoint metadata, exact
package and decision identities/checksums, package creation time, and decision
count.  Focused failure and happy-path coverage lives in
``tests/unit/test_phase3_review_stage.py``.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, model_validator

from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    sha256_file,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    PositiveInt,
    Sha256Hex,
    UtcTimestamp,
)
from genome_to_diffraction.schemas.io import ContractError, load_contract
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewPackageManifest,
)
from genome_to_diffraction.status import InputContractError
from genome_to_diffraction.time import utc_now

_ADAPTER_VERSION = "phase3-review-stage-v1"
_CANONICAL_DECISION_NAME = "phase3_review_decision.json"
_STAGE_MANIFEST_NAME = "phase3_review_stage_manifest.json"
_OUTPUT_ALLOWLIST = (_CANONICAL_DECISION_NAME, _STAGE_MANIFEST_NAME)
_SHA256 = re.compile(r"^[a-f0-9]{64}$")

PhaseIIIReviewStageIdentifier = Annotated[
    str,
    Field(pattern=r"^phase3reviewstage_[a-f0-9]{64}$"),
]
PhaseIIIReviewDecisionIdentifier = Annotated[
    str,
    Field(pattern=r"^phase3review_[a-f0-9]{64}$"),
]


class PhaseIIIReviewStageError(InputContractError):
    """Phase III review inputs cannot be safely published for consumption."""


@dataclass(frozen=True, slots=True)
class OwnedPhaseIIIParentRun:
    """Caller-verified local ownership metadata for the parent analysis run."""

    run_id: str
    profile: str
    phase: str


@dataclass(frozen=True, slots=True)
class PhaseIIIReviewStageRequest:
    """Exact local inputs for one checkpoint staging operation."""

    parent: OwnedPhaseIIIParentRun
    checkpoint: PhaseIIIReviewCheckpoint
    review_package_manifest: Path
    decisions: Path
    confirmed_decisions_sha256: str
    output_directory: Path
    progress: bool = False


@dataclass(frozen=True, slots=True)
class PhaseIIIReviewStageOutput:
    """The only two allow-listed files published by a successful stage."""

    stage_id: str
    decision_file_id: str
    decision_count: int
    canonical_decision: Path
    stage_manifest: Path


class PhaseIIIReviewStageManifest(ContractModel):
    """Typed local publication record for one validated decision file."""

    schema_version: Literal["2.0"]
    adapter_version: Literal["phase3-review-stage-v1"]
    stage_id: PhaseIIIReviewStageIdentifier
    staged_at: UtcTimestamp
    checkpoint: PhaseIIIReviewCheckpoint
    owned_parent_run_id: NonEmptyString
    parent_profile: NonEmptyString
    parent_phase: NonEmptyString
    review_package_id: NonEmptyString
    review_package_created_at: UtcTimestamp
    review_package_manifest_sha256: Sha256Hex
    source_decisions_sha256: Sha256Hex
    decision_file_id: PhaseIIIReviewDecisionIdentifier
    decision_count: PositiveInt
    canonical_decision_path: Literal["phase3_review_decision.json"]
    canonical_decision_sha256: Sha256Hex
    output_allowlist: tuple[
        Literal["phase3_review_decision.json"],
        Literal["phase3_review_stage_manifest.json"],
    ]
    execution_status: Literal["completed_success"]

    @model_validator(mode="after")
    def _validate_stage_identity(self) -> Self:
        expected = _stage_id(
            checkpoint=self.checkpoint,
            parent=OwnedPhaseIIIParentRun(
                run_id=self.owned_parent_run_id,
                profile=self.parent_profile,
                phase=self.parent_phase,
            ),
            package_id=self.review_package_id,
            package_created_at=self.review_package_created_at,
            package_sha256=self.review_package_manifest_sha256,
            source_decisions_sha256=self.source_decisions_sha256,
            decision_file_id=self.decision_file_id,
            decision_count=self.decision_count,
            canonical_decision_sha256=self.canonical_decision_sha256,
        )
        if self.stage_id != expected:
            raise ValueError("stage_id does not match the validated stage inputs")
        return self


def _stage_id(
    *,
    checkpoint: PhaseIIIReviewCheckpoint,
    parent: OwnedPhaseIIIParentRun,
    package_id: str,
    package_created_at: datetime,
    package_sha256: str,
    source_decisions_sha256: str,
    decision_file_id: str,
    decision_count: int,
    canonical_decision_sha256: str,
) -> str:
    return content_id(
        "phase3reviewstage_",
        {
            "adapter_version": _ADAPTER_VERSION,
            "checkpoint": checkpoint,
            "owned_parent_run_id": parent.run_id,
            "parent_profile": parent.profile,
            "parent_phase": parent.phase,
            "review_package_id": package_id,
            "review_package_created_at": package_created_at,
            "review_package_manifest_sha256": package_sha256,
            "source_decisions_sha256": source_decisions_sha256,
            "decision_file_id": decision_file_id,
            "decision_count": decision_count,
            "canonical_decision_sha256": canonical_decision_sha256,
        },
    )


def _regular_file(path: Path, *, label: str) -> Path:
    try:
        if path.is_symlink():
            raise PhaseIIIReviewStageError(
                f"{label} must be a regular non-symlink file"
            )
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise PhaseIIIReviewStageError(f"{label} is absent or unreadable") from error
    if not resolved.is_file():
        raise PhaseIIIReviewStageError(f"{label} must be a regular non-symlink file")
    return resolved


def _new_output_directory(path: Path) -> Path:
    if path.is_symlink() or path.exists():
        raise PhaseIIIReviewStageError(
            "Phase III review stage output must be a new absent directory"
        )
    absolute = path.absolute()
    try:
        parent = absolute.parent.resolve(strict=True)
    except OSError as error:
        raise PhaseIIIReviewStageError(
            "Phase III review stage output parent is absent or unreadable"
        ) from error
    if not parent.is_dir():
        raise PhaseIIIReviewStageError(
            "Phase III review stage output parent must be a directory"
        )
    return parent / absolute.name


def _validated_checkpoint(value: object) -> PhaseIIIReviewCheckpoint:
    try:
        return PhaseIIIReviewCheckpoint(value)
    except (TypeError, ValueError) as error:
        raise PhaseIIIReviewStageError(
            "requested Phase III review checkpoint is invalid"
        ) from error


def _validate_parent(parent: OwnedPhaseIIIParentRun) -> None:
    for label, value in (
        ("owned parent run ID", parent.run_id),
        ("owned parent profile", parent.profile),
        ("owned parent phase", parent.phase),
    ):
        if not isinstance(value, str) or not value.strip():
            raise PhaseIIIReviewStageError(f"{label} must be non-empty")


def _load_package(path: Path) -> PhaseIIIReviewPackageManifest:
    try:
        return PhaseIIIReviewPackageManifest.model_validate_json(path.read_bytes())
    except (ContractError, OSError, ValidationError, ValueError) as error:
        raise PhaseIIIReviewStageError(
            f"review package manifest violates its typed contract: {error}"
        ) from error


def _load_decisions(path: Path) -> PhaseIIIReviewDecisionFile:
    try:
        decision_file = load_contract(
            path,
            "phase3-review-decisions",
            progress=False,
        )
    except ContractError as error:
        raise PhaseIIIReviewStageError(
            f"decision file violates its typed contract: {error}"
        ) from error
    if not isinstance(decision_file, PhaseIIIReviewDecisionFile):
        raise PhaseIIIReviewStageError("decision loader returned an unexpected type")
    return decision_file


def _sha256(path: Path, *, label: str, progress: bool) -> str:
    try:
        return sha256_file(
            path,
            progress=progress,
            description=f"Checksumming {label}",
        )
    except OSError as error:
        raise PhaseIIIReviewStageError(
            f"{label} became unreadable during checksum verification"
        ) from error


def _canonical_json_bytes(decisions: PhaseIIIReviewDecisionFile) -> bytes:
    document = decisions.model_dump(mode="json", exclude_none=False)
    payload = json.dumps(
        document,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    return f"{payload}\n".encode()


def stage_phase3_review_decisions(
    request: PhaseIIIReviewStageRequest,
) -> PhaseIIIReviewStageOutput:
    """Validate and publish one exact Phase III checkpoint decision file."""

    checkpoint = _validated_checkpoint(request.checkpoint)
    _validate_parent(request.parent)
    if _SHA256.fullmatch(request.confirmed_decisions_sha256) is None:
        raise PhaseIIIReviewStageError(
            "confirmed decision-file checksum must be lowercase SHA-256"
        )
    output = _new_output_directory(request.output_directory)
    package_path = _regular_file(
        request.review_package_manifest,
        label="review package manifest",
    )
    decision_path = _regular_file(request.decisions, label="decision file")

    package_sha256 = _sha256(
        package_path,
        label="Phase III review package manifest",
        progress=request.progress,
    )
    source_decisions_sha256 = _sha256(
        decision_path,
        label="Phase III decision file",
        progress=request.progress,
    )
    if source_decisions_sha256 != request.confirmed_decisions_sha256:
        raise PhaseIIIReviewStageError(
            "decision-file checksum differs from the independent confirmation"
        )

    package = _load_package(package_path)
    decisions = _load_decisions(decision_path)
    if package.owned_parent_run_id != request.parent.run_id:
        raise PhaseIIIReviewStageError(
            "review package belongs to a stale or different parent run"
        )
    if package.parent_profile != request.parent.profile:
        raise PhaseIIIReviewStageError(
            "review package profile differs from the owned parent profile"
        )
    if package.parent_phase != request.parent.phase:
        raise PhaseIIIReviewStageError(
            "review package phase differs from the owned parent phase"
        )
    if package.checkpoint is not checkpoint:
        raise PhaseIIIReviewStageError(
            "review package checkpoint differs from the requested checkpoint"
        )
    if decisions.owned_parent_run_id != request.parent.run_id:
        raise PhaseIIIReviewStageError(
            "decision file belongs to a stale or different parent run"
        )
    if decisions.checkpoint is not checkpoint:
        raise PhaseIIIReviewStageError(
            "decision file checkpoint differs from the requested checkpoint"
        )
    if decisions.review_package_id != package.review_package_id:
        raise PhaseIIIReviewStageError("decision file names a different review package")
    if decisions.review_package_manifest_sha256 != package_sha256:
        raise PhaseIIIReviewStageError(
            "decision file names a different review-package manifest checksum"
        )

    permitted = {
        (target.crystal_id, target.item_id) for target in package.permitted_targets
    }
    for decision in decisions.decisions:
        target = (decision.crystal_id, decision.item_id)
        if target not in permitted:
            raise PhaseIIIReviewStageError(
                "decision file contains a target absent from the exact review "
                f"package: {decision.crystal_id}/{decision.item_id}"
            )
        if decision.reviewed_at < package.created_at:
            raise PhaseIIIReviewStageError(
                "decision predates the exact review package: "
                f"{decision.crystal_id}/{decision.item_id}"
            )

    if (
        _sha256(
            package_path,
            label="Phase III review package manifest",
            progress=False,
        )
        != package_sha256
    ):
        raise PhaseIIIReviewStageError(
            "review package manifest changed during stage validation"
        )
    if (
        _sha256(
            decision_path,
            label="Phase III decision file",
            progress=False,
        )
        != source_decisions_sha256
    ):
        raise PhaseIIIReviewStageError("decision file changed during stage validation")

    canonical_bytes = _canonical_json_bytes(decisions)
    canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
    stage_id = _stage_id(
        checkpoint=checkpoint,
        parent=request.parent,
        package_id=package.review_package_id,
        package_created_at=package.created_at,
        package_sha256=package_sha256,
        source_decisions_sha256=source_decisions_sha256,
        decision_file_id=decisions.decision_file_id,
        decision_count=len(decisions.decisions),
        canonical_decision_sha256=canonical_sha256,
    )
    stage_manifest = PhaseIIIReviewStageManifest(
        schema_version="2.0",
        adapter_version=_ADAPTER_VERSION,
        stage_id=stage_id,
        staged_at=utc_now(),
        checkpoint=checkpoint,
        owned_parent_run_id=request.parent.run_id,
        parent_profile=request.parent.profile,
        parent_phase=request.parent.phase,
        review_package_id=package.review_package_id,
        review_package_created_at=package.created_at,
        review_package_manifest_sha256=package_sha256,
        source_decisions_sha256=source_decisions_sha256,
        decision_file_id=decisions.decision_file_id,
        decision_count=len(decisions.decisions),
        canonical_decision_path=_CANONICAL_DECISION_NAME,
        canonical_decision_sha256=canonical_sha256,
        output_allowlist=_OUTPUT_ALLOWLIST,
        execution_status="completed_success",
    )

    canonical_path = output / _CANONICAL_DECISION_NAME
    manifest_path = output / _STAGE_MANIFEST_NAME
    try:
        output.mkdir(mode=0o700)
        atomic_write_bytes(canonical_path, canonical_bytes)
        atomic_write_json(
            manifest_path,
            stage_manifest.model_dump(mode="json", exclude_none=False),
        )
        if tuple(sorted(path.name for path in output.iterdir())) != tuple(
            sorted(_OUTPUT_ALLOWLIST)
        ):
            raise PhaseIIIReviewStageError(
                "Phase III review stage output violates its two-file allow-list"
            )
    except OSError as error:
        raise PhaseIIIReviewStageError(
            "Phase III review stage output could not be published"
        ) from error
    return PhaseIIIReviewStageOutput(
        stage_id=stage_id,
        decision_file_id=decisions.decision_file_id,
        decision_count=len(decisions.decisions),
        canonical_decision=canonical_path,
        stage_manifest=manifest_path,
    )


__all__ = [
    "OwnedPhaseIIIParentRun",
    "PhaseIIIReviewStageError",
    "PhaseIIIReviewStageManifest",
    "PhaseIIIReviewStageOutput",
    "PhaseIIIReviewStageRequest",
    "stage_phase3_review_decisions",
]
