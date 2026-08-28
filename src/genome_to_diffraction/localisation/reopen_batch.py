"""Plan the retained localisation-excluded A wave after complete zero packing.

This adapter consumes one Phase III first-wave funnel, all of its terminal MR
result directories, and the exact portable localisation bundle. It never runs
Phaser. It reopens retained excluded model/copy hypotheses only when every
scheduled active hypothesis has a completed scientific result and none packed.
Any missing, duplicated, failed, or nonterminal result blocks reopening.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal, Self

from pydantic import Field, ValidationError, model_validator

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.localisation.batch import (
    validate_catalogue_localisation_batch,
)
from genome_to_diffraction.schemas.base import NonEmptyString, Sha256Hex
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    NormalisedMrResult,
)
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_ADAPTER_VERSION = "phase3-localisation-zero-pack-reopen-v1"


class BatchLocalisationReopenStatus(StrEnum):
    """Typed terminal planning outcome without scientific promotion."""

    READY = "ready_reopened_after_complete_zero_pack"
    NOT_REQUIRED_PACKED = "not_required_packed_first_wave"
    EMPTY_NO_EXCLUDED = "empty_no_excluded_hypotheses"
    BLOCKED_INCOMPLETE = "blocked_incomplete_or_failed_first_wave"


class BatchLocalisationReopenPlan(_ContentAddressedContract):
    """Complete zero-pack decision and bounded reopened hypothesis inventory."""

    _identity_field: ClassVar[str] = "plan_id"
    _identity_prefix: ClassVar[str] = "localreopen_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["phase3-localisation-zero-pack-reopen-v1"] = (
        _ADAPTER_VERSION
    )
    plan_id: NonEmptyString
    localisation_policy_id: NonEmptyString
    funnel_manifest_sha256: Sha256Hex
    active_hypotheses_sha256: Sha256Hex
    deferred_hypotheses_sha256: Sha256Hex
    terminal_results_sha256: Sha256Hex
    active_hypothesis_count: int = Field(ge=0, le=25)
    terminal_result_count: int = Field(ge=0, le=25)
    failed_or_incomplete_count: int = Field(ge=0, le=25)
    packed_result_count: int = Field(ge=0, le=25)
    deferred_hypothesis_count: int = Field(ge=0)
    maximum_reopened_attempts: int = Field(ge=1, le=175)
    reopened_hypothesis_count: int = Field(ge=0, le=175)
    remaining_deferred_count: int = Field(ge=0)
    status: BatchLocalisationReopenStatus
    source_hypothesis_ids: tuple[NonEmptyString, ...]
    reopened_hypothesis_ids: tuple[NonEmptyString, ...]

    @model_validator(mode="after")
    def _validate_decision(self) -> Self:
        if self.terminal_result_count + self.failed_or_incomplete_count != (
            self.active_hypothesis_count
        ):
            raise ValueError("reopen result counts do not cover the active wave")
        if self.reopened_hypothesis_count != len(self.reopened_hypothesis_ids):
            raise ValueError("reopened hypothesis count differs")
        if self.reopened_hypothesis_count != len(self.source_hypothesis_ids):
            raise ValueError("reopened source-hypothesis count differs")
        if self.deferred_hypothesis_count != (
            self.reopened_hypothesis_count + self.remaining_deferred_count
        ):
            raise ValueError("reopen inventory does not conserve exclusions")
        expected = (
            BatchLocalisationReopenStatus.BLOCKED_INCOMPLETE
            if self.failed_or_incomplete_count
            else BatchLocalisationReopenStatus.NOT_REQUIRED_PACKED
            if self.packed_result_count
            else BatchLocalisationReopenStatus.EMPTY_NO_EXCLUDED
            if not self.deferred_hypothesis_count
            else BatchLocalisationReopenStatus.READY
        )
        if self.status is not expected:
            raise ValueError("reopen status differs from terminal evidence")
        if (self.status is BatchLocalisationReopenStatus.READY) != bool(
            self.reopened_hypothesis_count
        ):
            raise ValueError("only a ready reopen plan may schedule hypotheses")
        return self


class BatchLocalisationReopenError(InputContractError):
    """First-wave evidence cannot form one safe reopen decision."""


@dataclass(frozen=True, slots=True)
class BatchLocalisationReopenRequest:
    """One first-wave funnel, results, and exact policy."""

    funnel_directory: Path
    result_directories: tuple[Path, ...]
    localisation_bundle: Path
    maximum_reopened_attempts: int
    output_directory: Path


@dataclass(frozen=True, slots=True)
class BatchLocalisationReopenOutput:
    """Published decision and optional reopened hypotheses."""

    plan: BatchLocalisationReopenPlan
    plan_json: Path
    hypotheses_jsonl: Path


def _hypotheses(path: Path, *, label: str) -> tuple[MrHypothesis, ...]:
    try:
        lines = path.resolve(strict=True).read_text(encoding="utf-8").splitlines()
        records = tuple(
            MrHypothesis.model_validate_json(line) for line in lines if line.strip()
        )
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise BatchLocalisationReopenError(f"invalid {label}") from error
    if len({item.hypothesis_id for item in records}) != len(records):
        raise BatchLocalisationReopenError(f"duplicate {label}")
    return records


def _result(directory: Path) -> NormalisedMrResult:
    path = directory / "normalised_mr_result.json"
    try:
        return NormalisedMrResult.model_validate_json(
            path.resolve(strict=True).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise BatchLocalisationReopenError("invalid first-wave result") from error


def plan_batch_localisation_reopen(
    request: BatchLocalisationReopenRequest,
) -> BatchLocalisationReopenOutput:
    """Require complete zero packing before reopening retained exclusions."""

    if not 1 <= request.maximum_reopened_attempts <= 175:
        raise ValueError("maximum reopened attempts must be in 1..175")
    try:
        root = request.funnel_directory.resolve(strict=True)
        manifest_path = root / "diverse_first_copy_funnel_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BatchLocalisationReopenError("first-wave funnel is invalid") from error
    policy = validate_catalogue_localisation_batch(request.localisation_bundle)
    if (
        not isinstance(manifest, dict)
        or manifest.get("adapter_version")
        != "multi-source-first-copy-funnel-v3-phase3-evidence"
        or manifest.get("localisation_policy_id") != policy.policy_id
    ):
        raise BatchLocalisationReopenError(
            "first-wave funnel uses a different localisation policy"
        )
    active_path = root / "mr_hypotheses.jsonl"
    deferred_path = root / "deferred_localisation_hypotheses.jsonl"
    active = _hypotheses(active_path, label="active first-wave hypotheses")
    deferred = _hypotheses(deferred_path, label="deferred localisation hypotheses")
    if len(active) > 25 or any(
        item.status is not MrHypothesisStatus.QUEUED
        or item.sequence_group_id in policy.retained_excluded_group_ids
        for item in active
    ):
        raise BatchLocalisationReopenError("active first-wave inventory differs")
    if any(
        item.status is not MrHypothesisStatus.SKIPPED
        or item.priority_features.get("localisation_wave_disposition") != "excluded"
        or item.sequence_group_id not in policy.retained_excluded_group_ids
        for item in deferred
    ):
        raise BatchLocalisationReopenError("deferred localisation inventory differs")
    results = tuple(_result(path) for path in request.result_directories)
    by_hypothesis = {result.hypothesis_id: result for result in results}
    if len(by_hypothesis) != len(results) or set(by_hypothesis) != {
        item.hypothesis_id for item in active
    }:
        raise BatchLocalisationReopenError(
            "first-wave results do not exactly cover active hypotheses"
        )
    terminal_statuses = {
        ExecutionStatus.COMPLETED_HIT,
        ExecutionStatus.COMPLETED_NO_HIT,
    }
    incomplete = sum(
        result.execution_status not in terminal_statuses for result in results
    )
    packed = sum(
        result.execution_status is ExecutionStatus.COMPLETED_HIT
        and result.packing_summary.get("top_solution_packed") is True
        for result in results
    )
    result_lines = "".join(
        f"{canonical_json_text(result)}\n"
        for result in sorted(results, key=lambda item: item.hypothesis_id)
    )
    result_sha256 = hashlib.sha256(result_lines.encode("utf-8")).hexdigest()
    reopen_ready = not incomplete and not packed and bool(deferred)
    selected = deferred[: request.maximum_reopened_attempts] if reopen_ready else ()
    plan_values = {
        "localisation_policy_id": policy.policy_id,
        "funnel_manifest_sha256": sha256_file(manifest_path),
        "active_hypotheses_sha256": sha256_file(active_path),
        "deferred_hypotheses_sha256": sha256_file(deferred_path),
        "terminal_results_sha256": result_sha256,
        "active_hypothesis_count": len(active),
        "terminal_result_count": len(active) - incomplete,
        "failed_or_incomplete_count": incomplete,
        "packed_result_count": packed,
        "deferred_hypothesis_count": len(deferred),
        "maximum_reopened_attempts": request.maximum_reopened_attempts,
        "reopened_hypothesis_count": len(selected),
        "remaining_deferred_count": len(deferred) - len(selected),
        "status": (
            BatchLocalisationReopenStatus.BLOCKED_INCOMPLETE
            if incomplete
            else BatchLocalisationReopenStatus.NOT_REQUIRED_PACKED
            if packed
            else BatchLocalisationReopenStatus.EMPTY_NO_EXCLUDED
            if not deferred
            else BatchLocalisationReopenStatus.READY
        ),
        "source_hypothesis_ids": tuple(item.hypothesis_id for item in selected),
    }
    reopen_evidence_id = content_id(
        "localreopenevidence_",
        {
            "localisation_policy_id": policy.policy_id,
            "deferred_hypotheses_sha256": plan_values["deferred_hypotheses_sha256"],
            "terminal_results_sha256": result_sha256,
        },
    )
    reopened = tuple(
        item.model_copy(
            update={
                "hypothesis_id": content_id(
                    "mrhyp_",
                    {
                        "source_hypothesis_id": item.hypothesis_id,
                        "reopen_evidence_id": reopen_evidence_id,
                    },
                ),
                "priority_features": {
                    **item.priority_features,
                    "source_hypothesis_id": item.hypothesis_id,
                    "localisation_reopen_evidence_id": reopen_evidence_id,
                    "localisation_reopened_after_zero_pack": True,
                },
                "status": MrHypothesisStatus.QUEUED,
            }
        )
        for item in selected
    )
    plan = BatchLocalisationReopenPlan.from_content(
        **plan_values,
        reopened_hypothesis_ids=tuple(item.hypothesis_id for item in reopened),
    )
    output = request.output_directory.absolute()
    if output.exists() or output.is_symlink():
        raise BatchLocalisationReopenError("reopen output already exists")
    output.mkdir(parents=True)
    hypotheses_jsonl = output / "reopened_hypotheses.jsonl"
    atomic_write_text(
        hypotheses_jsonl,
        "".join(f"{canonical_json_text(item)}\n" for item in reopened),
    )
    plan_json = output / "localisation_reopen_plan.json"
    atomic_write_json(plan_json, plan.model_dump(mode="json"))
    return BatchLocalisationReopenOutput(plan, plan_json, hypotheses_jsonl)


__all__ = [
    "BatchLocalisationReopenError",
    "BatchLocalisationReopenOutput",
    "BatchLocalisationReopenPlan",
    "BatchLocalisationReopenRequest",
    "BatchLocalisationReopenStatus",
    "plan_batch_localisation_reopen",
]
