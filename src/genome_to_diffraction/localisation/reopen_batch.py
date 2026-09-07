"""Plan bounded no-A expansion from complete execution and review authority.

This adapter consumes one Phase III first-wave funnel, all of its terminal MR
result directories, and the exact portable localisation bundle. It never runs
Phaser. Automatic complete-zero-pack planning retains admitted cap-deferred and
localisation-excluded hypotheses. A staged JSON A decision can explicitly select
any retained mathematical alternative after all realised targets were rejected
or deferred, including a weak packed first wave. Missing, failed or nonterminal
execution blocks both routes. Every reopened hypothesis searches one copy.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
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
from genome_to_diffraction.mr_resources import build_mr_resource_plan
from genome_to_diffraction.schemas.base import NonEmptyString, Sha256Hex
from genome_to_diffraction.schemas.mr_resources import (
    MR_RESOURCE_ADAPTER_VERSION,
    MrResourcePlan,
)
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    NormalisedMrResult,
)
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_ADAPTER_VERSION = "phase3-no-a-expansion-v3-reviewed-selection"


def _reopen_evidence_id(values: Mapping[str, object]) -> str:
    names = (
        "localisation_policy_id",
        "deferred_hypotheses_sha256",
        "terminal_results_sha256",
        "source_hypothesis_ids",
        "maximum_reopened_attempts",
    )
    review_names = (
        "review_package_id",
        "review_package_manifest_sha256",
        "review_decision_file_id",
        "source_review_decisions_sha256",
    )
    payload = {name: values[name] for name in names}
    if values.get("review_decision_file_id") is not None:
        payload.update({name: values[name] for name in review_names})
    return content_id("localreopenevidence_", payload)


class BatchLocalisationReopenStatus(StrEnum):
    """Typed terminal planning outcome without scientific promotion."""

    READY = "ready_reopened_after_complete_zero_pack"
    READY_REVIEWED = "ready_reopened_after_human_review"
    NOT_REQUIRED_PACKED = "not_required_packed_first_wave"
    EMPTY_NO_AUTOMATIC_ALTERNATIVES = "empty_no_automatic_alternatives"
    BLOCKED_INCOMPLETE = "blocked_incomplete_or_failed_first_wave"


class BatchLocalisationReopenPlan(_ContentAddressedContract):
    """Complete execution, optional human authority and bounded alternatives."""

    _identity_field: ClassVar[str] = "plan_id"
    _identity_prefix: ClassVar[str] = "localreopen_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["phase3-no-a-expansion-v3-reviewed-selection"] = (
        _ADAPTER_VERSION
    )
    plan_id: NonEmptyString
    localisation_policy_id: NonEmptyString
    funnel_manifest_sha256: Sha256Hex
    active_hypotheses_sha256: Sha256Hex
    deferred_cap_hypotheses_sha256: Sha256Hex
    deferred_localisation_hypotheses_sha256: Sha256Hex
    deferred_hypotheses_sha256: Sha256Hex
    complete_acquired_hypotheses_sha256: Sha256Hex
    terminal_results_sha256: Sha256Hex
    active_hypothesis_count: int = Field(ge=0, le=25)
    terminal_result_count: int = Field(ge=0, le=25)
    failed_or_incomplete_count: int = Field(ge=0, le=25)
    packed_result_count: int = Field(ge=0, le=25)
    cap_deferred_hypothesis_count: int = Field(ge=0)
    localisation_deferred_hypothesis_count: int = Field(ge=0)
    deferred_hypothesis_count: int = Field(ge=0)
    automatic_eligible_hypothesis_count: int = Field(ge=0)
    maximum_reopened_attempts: int = Field(ge=1, le=175)
    reopened_hypothesis_count: int = Field(ge=0, le=175)
    remaining_deferred_count: int = Field(ge=0)
    status: BatchLocalisationReopenStatus
    source_hypothesis_ids: tuple[NonEmptyString, ...]
    reopened_hypothesis_ids: tuple[NonEmptyString, ...]
    review_package_id: NonEmptyString | None = None
    review_package_manifest_sha256: Sha256Hex | None = None
    review_decision_file_id: NonEmptyString | None = None
    source_review_decisions_sha256: Sha256Hex | None = None

    @property
    def reopen_evidence_id(self) -> str:
        """Bind the selected native searches to their reopening authority."""

        return _reopen_evidence_id(self.model_dump(mode="python"))

    @model_validator(mode="after")
    def _validate_decision(self) -> Self:
        if len(set(self.source_hypothesis_ids)) != len(
            self.source_hypothesis_ids
        ) or len(set(self.reopened_hypothesis_ids)) != len(
            self.reopened_hypothesis_ids
        ):
            raise ValueError("reopened source and task hypothesis IDs must be unique")
        review_bindings = (
            self.review_package_id,
            self.review_package_manifest_sha256,
            self.review_decision_file_id,
            self.source_review_decisions_sha256,
        )
        if any(value is not None for value in review_bindings) and not all(
            value is not None for value in review_bindings
        ):
            raise ValueError(
                "reviewed reopening requires every package/decision binding"
            )
        if self.reopened_hypothesis_count > self.maximum_reopened_attempts:
            raise ValueError("reopened selection exceeds the declared attempt limit")
        if self.automatic_eligible_hypothesis_count > self.deferred_hypothesis_count:
            raise ValueError(
                "automatic reopen eligibility exceeds the complete inventory"
            )
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
            raise ValueError("reopen inventory does not conserve deferred hypotheses")
        if self.deferred_hypothesis_count != (
            self.cap_deferred_hypothesis_count
            + self.localisation_deferred_hypothesis_count
        ):
            raise ValueError("reopen inventory does not conserve both deferred waves")
        expected = (
            BatchLocalisationReopenStatus.BLOCKED_INCOMPLETE
            if self.failed_or_incomplete_count
            else BatchLocalisationReopenStatus.READY_REVIEWED
            if self.review_decision_file_id is not None
            else BatchLocalisationReopenStatus.NOT_REQUIRED_PACKED
            if self.packed_result_count
            else BatchLocalisationReopenStatus.EMPTY_NO_AUTOMATIC_ALTERNATIVES
            if not self.automatic_eligible_hypothesis_count
            else BatchLocalisationReopenStatus.READY
        )
        if self.status is not expected:
            raise ValueError("reopen status differs from terminal evidence")
        if (
            self.status
            in {
                BatchLocalisationReopenStatus.READY,
                BatchLocalisationReopenStatus.READY_REVIEWED,
            }
        ) != bool(self.reopened_hypothesis_count):
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
    review_package_manifest: Path | None = None
    review_decisions: Path | None = None


@dataclass(frozen=True, slots=True)
class BatchLocalisationReopenOutput:
    """Published decision and optional reopened hypotheses."""

    plan: BatchLocalisationReopenPlan
    plan_json: Path
    hypotheses_jsonl: Path
    funnel_manifest_json: Path


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
    """Require complete execution plus zero packing or explicit human selection."""

    from genome_to_diffraction.review.phase3_stage import (
        load_staged_phase3_reopen_decisions,
        validate_phase3_reopen_decision,
    )

    if not 1 <= request.maximum_reopened_attempts <= 175:
        raise ValueError("maximum reopened attempts must be in 1..175")
    try:
        root = request.funnel_directory.resolve(strict=True)
        manifest_path = root / "funnel_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BatchLocalisationReopenError("first-wave funnel is invalid") from error
    policy = validate_catalogue_localisation_batch(request.localisation_bundle)
    if (
        not isinstance(manifest, dict)
        or manifest.get("adapter_version")
        != "multi-source-first-copy-funnel-v8-reviewed-alternatives"
        or manifest.get("localisation_policy_id") != policy.policy_id
    ):
        raise BatchLocalisationReopenError(
            "first-wave funnel uses a different localisation policy"
        )
    active_path = root / "mr_hypotheses.jsonl"
    complete_path = root / "complete_acquired_hypotheses.jsonl"
    deferred_cap_path = root / "deferred_cap_hypotheses.jsonl"
    deferred_localisation_path = root / "deferred_localisation_hypotheses.jsonl"
    active = _hypotheses(active_path, label="active first-wave hypotheses")
    complete = _hypotheses(complete_path, label="complete acquired-model hypotheses")
    deferred_cap = _hypotheses(
        deferred_cap_path,
        label="cap-deferred active hypotheses",
    )
    deferred_localisation = _hypotheses(
        deferred_localisation_path,
        label="deferred localisation hypotheses",
    )
    resource_plan_path = root / "mr_resource_plans.jsonl"
    resource_plans: dict[str, MrResourcePlan] = {}
    try:
        for _line_number, line in enumerate(
            resource_plan_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            document = json.loads(line)
            if not isinstance(document, dict) or set(document) != {
                "hypothesis_id",
                "resource_plan",
            }:
                raise ValueError("resource-plan mapping shape differs")
            hypothesis_id = document["hypothesis_id"]
            if not isinstance(hypothesis_id, str) or hypothesis_id in resource_plans:
                raise ValueError("resource-plan hypothesis is invalid or duplicated")
            resource_plan = MrResourcePlan.model_validate(document["resource_plan"])
            if (
                resource_plan.owner_kind != "mr_hypothesis"
                or resource_plan.owner_id != hypothesis_id
            ):
                raise ValueError("resource plan owns another hypothesis")
            resource_plans[hypothesis_id] = resource_plan
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as error:
        raise BatchLocalisationReopenError(
            f"first-wave MR resource plans are invalid: {error}"
        ) from error
    if len(active) > 25 or any(
        item.status is not MrHypothesisStatus.QUEUED
        or item.sequence_group_id in policy.retained_excluded_group_ids
        for item in active
    ):
        raise BatchLocalisationReopenError("active first-wave inventory differs")
    if any(
        item.status is not MrHypothesisStatus.SKIPPED
        or item.priority_features.get("first_copy_execution_disposition")
        not in {
            "deferred_initial_25_cap_requires_reopening_authority",
            "deferred_expected_copy_state_requires_reviewed_selection",
        }
        or item.sequence_group_id in policy.retained_excluded_group_ids
        for item in deferred_cap
    ):
        raise BatchLocalisationReopenError("cap-deferred hypothesis inventory differs")
    if any(
        item.status is not MrHypothesisStatus.SKIPPED
        or item.priority_features.get("localisation_wave_disposition") != "excluded"
        or item.sequence_group_id not in policy.retained_excluded_group_ids
        for item in deferred_localisation
    ):
        raise BatchLocalisationReopenError("deferred localisation inventory differs")
    deferred = (*deferred_cap, *deferred_localisation)
    combined = {item.hypothesis_id: item for item in (*active, *deferred)}
    if (
        len(combined) != len(active) + len(deferred)
        or {item.hypothesis_id: item for item in complete} != combined
        or manifest.get("complete_acquired_hypothesis_count") != len(complete)
        or manifest.get("complete_acquired_hypotheses_sha256")
        != sha256_file(complete_path)
        or any(item.copy_number_to_search != 1 for item in complete)
    ):
        raise BatchLocalisationReopenError(
            "complete acquired-model inventory differs from funnel"
        )
    automatic_deferred = tuple(
        item
        for item in deferred
        if item.priority_features.get("initial_admission_eligible") is True
    )
    complete_hypothesis_ids = {item.hypothesis_id for item in (*active, *deferred)}
    if (
        set(resource_plans) != complete_hypothesis_ids
        or manifest.get("mr_resource_plan_count") != len(resource_plans)
        or manifest.get("mr_resource_plan_adapter") != MR_RESOURCE_ADAPTER_VERSION
        or manifest.get("mr_resource_plans_sha256") != sha256_file(resource_plan_path)
    ):
        raise BatchLocalisationReopenError(
            "first-wave MR resource-plan inventory differs"
        )
    deferred_ids = tuple(item.hypothesis_id for item in deferred)
    if len(deferred_ids) != len(set(deferred_ids)) or set(deferred_ids) & {
        item.hypothesis_id for item in active
    }:
        raise BatchLocalisationReopenError("deferred hypotheses are duplicated")
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
    review_bindings: dict[str, str] = {}
    if (request.review_package_manifest is None) != (request.review_decisions is None):
        raise BatchLocalisationReopenError(
            "reviewed reopening requires both package and JSON decisions"
        )
    if request.review_decisions is not None:
        assert request.review_package_manifest is not None
        if request.review_decisions.suffix.lower() != ".json":
            raise BatchLocalisationReopenError(
                "reviewed reopening requires JSON decisions"
            )
        decisions = load_staged_phase3_reopen_decisions(
            decision_path=request.review_decisions,
            package_manifest=request.review_package_manifest,
        )
        assert decisions.reopen_request is not None
        if (
            decisions.reopen_request.maximum_reopened_attempts
            != request.maximum_reopened_attempts
        ):
            raise BatchLocalisationReopenError(
                "reopen attempt limit differs from the human decision"
            )
        reviewed_selection = validate_phase3_reopen_decision(
            package_manifest=request.review_package_manifest,
            decisions=decisions,
            source_funnel_directory=root,
            terminal_results_sha256=result_sha256,
        )
        if any(
            item.hypothesis_id not in {row.hypothesis_id for row in deferred}
            for item in reviewed_selection
        ):
            raise BatchLocalisationReopenError(
                "reviewed selection is outside the deferred source wave"
            )
        selected = reviewed_selection if not incomplete else ()
        review_bindings = {
            "review_package_id": decisions.review_package_id,
            "review_package_manifest_sha256": decisions.review_package_manifest_sha256,
            "review_decision_file_id": decisions.decision_file_id,
            "source_review_decisions_sha256": sha256_file(request.review_decisions),
        }
    else:
        reopen_ready = not incomplete and not packed and bool(automatic_deferred)
        selected = (
            automatic_deferred[: request.maximum_reopened_attempts]
            if reopen_ready
            else ()
        )
    plan_values = {
        "localisation_policy_id": policy.policy_id,
        "funnel_manifest_sha256": sha256_file(manifest_path),
        "active_hypotheses_sha256": sha256_file(active_path),
        "deferred_cap_hypotheses_sha256": sha256_file(deferred_cap_path),
        "deferred_localisation_hypotheses_sha256": sha256_file(
            deferred_localisation_path
        ),
        "deferred_hypotheses_sha256": hashlib.sha256(
            "".join(f"{canonical_json_text(item)}\n" for item in deferred).encode(
                "utf-8"
            )
        ).hexdigest(),
        "complete_acquired_hypotheses_sha256": sha256_file(complete_path),
        "terminal_results_sha256": result_sha256,
        "active_hypothesis_count": len(active),
        "terminal_result_count": len(active) - incomplete,
        "failed_or_incomplete_count": incomplete,
        "packed_result_count": packed,
        "cap_deferred_hypothesis_count": len(deferred_cap),
        "localisation_deferred_hypothesis_count": len(deferred_localisation),
        "deferred_hypothesis_count": len(deferred),
        "automatic_eligible_hypothesis_count": len(automatic_deferred),
        "maximum_reopened_attempts": request.maximum_reopened_attempts,
        "reopened_hypothesis_count": len(selected),
        "remaining_deferred_count": len(deferred) - len(selected),
        "status": (
            BatchLocalisationReopenStatus.BLOCKED_INCOMPLETE
            if incomplete
            else BatchLocalisationReopenStatus.READY_REVIEWED
            if review_bindings
            else BatchLocalisationReopenStatus.NOT_REQUIRED_PACKED
            if packed
            else BatchLocalisationReopenStatus.EMPTY_NO_AUTOMATIC_ALTERNATIVES
            if not automatic_deferred
            else BatchLocalisationReopenStatus.READY
        ),
        "source_hypothesis_ids": tuple(item.hypothesis_id for item in selected),
        **review_bindings,
    }
    reopen_evidence_id = _reopen_evidence_id(plan_values)
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
                    "no_a_expansion_after_zero_pack": not bool(review_bindings),
                    "no_a_expansion_after_human_review": bool(review_bindings),
                    "source_deferred_wave": (
                        item.priority_features.get(
                            "source_deferred_wave", "initial_25_cap"
                        )
                        if item in deferred_cap
                        else "localisation_excluded"
                    ),
                    "localisation_reopened_after_zero_pack": (
                        item in deferred_localisation and not review_bindings
                    ),
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
    if review_bindings:
        assert (
            request.review_package_manifest is not None
            and request.review_decisions is not None
        )
        shutil.copytree(
            request.review_package_manifest.parent, output / "review_package"
        )
        review_stage = output / "review_stage"
        review_stage.mkdir()
        for name in (
            "phase3_review_decision.json",
            "phase3_review_stage_manifest.json",
        ):
            shutil.copyfile(request.review_decisions.parent / name, review_stage / name)
        # Recheck the copied authority so portable pass-2 inputs retain its exact bytes.
        copied_decisions = load_staged_phase3_reopen_decisions(
            decision_path=review_stage / "phase3_review_decision.json",
            package_manifest=output
            / "review_package"
            / "phase3_review_package_manifest.json",
        )
        validate_phase3_reopen_decision(
            package_manifest=output
            / "review_package"
            / "phase3_review_package_manifest.json",
            decisions=copied_decisions,
            terminal_results_sha256=result_sha256,
        )
    hypotheses_jsonl = output / "reopened_hypotheses.jsonl"
    atomic_write_text(
        hypotheses_jsonl,
        "".join(f"{canonical_json_text(item)}\n" for item in reopened),
    )
    atomic_write_text(
        output / "mr_hypotheses.jsonl",
        hypotheses_jsonl.read_text(encoding="utf-8"),
    )
    reopened_resource_rows = tuple(
        (
            reopened_item.hypothesis_id,
            build_mr_resource_plan(
                owner_kind="mr_hypothesis",
                owner_id=reopened_item.hypothesis_id,
                reflection_count=resource_plans[source.hypothesis_id].reflection_count,
                moving_atom_count=resource_plans[
                    source.hypothesis_id
                ].moving_atom_count,
                searched_copy_count=resource_plans[
                    source.hypothesis_id
                ].searched_copy_count,
                fixed_atom_count=resource_plans[source.hypothesis_id].fixed_atom_count,
                symmetry_multiplicity=resource_plans[
                    source.hypothesis_id
                ].symmetry_multiplicity,
            ),
        )
        for source, reopened_item in zip(selected, reopened, strict=True)
    )
    resource_output = output / "resource_plans"
    resource_output.mkdir()
    reopened_resource_plans = output / "mr_resource_plans.jsonl"
    atomic_write_text(
        reopened_resource_plans,
        "".join(
            canonical_json_text(
                {
                    "hypothesis_id": hypothesis_id,
                    "resource_plan": resource_plan.model_dump(mode="json"),
                }
            )
            + "\n"
            for hypothesis_id, resource_plan in reopened_resource_rows
        ),
    )
    for hypothesis_id, resource_plan in reopened_resource_rows:
        atomic_write_json(
            resource_output / f"{hypothesis_id}.json",
            resource_plan.model_dump(mode="json"),
        )
    plan_json = output / "localisation_reopen_plan.json"
    atomic_write_json(plan_json, plan.model_dump(mode="json"))
    funnel_manifest = output / "reopened_funnel_manifest.json"
    funnel_identity = {
        "adapter_version": _ADAPTER_VERSION,
        "plan_id": plan.plan_id,
        "hypothesis_ids": list(plan.reopened_hypothesis_ids),
        "mr_resource_plans_sha256": sha256_file(reopened_resource_plans),
    }
    atomic_write_json(
        funnel_manifest,
        {
            "schema_version": "1.0",
            "funnel_id": content_id("funnel_", funnel_identity),
            "adapter_version": _ADAPTER_VERSION,
            "selected_hypothesis_count": len(reopened),
            "mr_resource_plan_adapter": MR_RESOURCE_ADAPTER_VERSION,
            "mr_resource_plan_count": len(reopened_resource_rows),
            "mr_resource_plans_sha256": sha256_file(reopened_resource_plans),
            "hypotheses": [{"hypothesis_id": item.hypothesis_id} for item in reopened],
            "execution_status": ExecutionStatus.COMPLETED_SUCCESS.value,
        },
    )
    atomic_write_text(
        output / "funnel_manifest.json",
        funnel_manifest.read_text(encoding="utf-8"),
    )
    return BatchLocalisationReopenOutput(
        plan,
        plan_json,
        hypotheses_jsonl,
        funnel_manifest,
    )


__all__ = [
    "BatchLocalisationReopenError",
    "BatchLocalisationReopenOutput",
    "BatchLocalisationReopenPlan",
    "BatchLocalisationReopenRequest",
    "BatchLocalisationReopenStatus",
    "plan_batch_localisation_reopen",
]
