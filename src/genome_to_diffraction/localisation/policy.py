"""Catalogue-wide offline localisation and conservative wave policy.

The module materialises one content-addressed PSORTb task per exact sequence
group, executes no public service, and retains a typed blocked DeepTMHMM result
until the user image CLI is verified.  It then validates exact catalogue/result
coverage and derives an inspectable first-wave decision for every group.

Soluble evidence is active.  Explicit membrane, surface, extracellular, or
transmembrane evidence is excluded from the first wave but never discarded.
Unknown, conflicting, and failed evidence is neutral and remains first-wave
eligible.  Excluded groups reopen only after every eligible active-wave group
has a non-failed terminal result and none packed.  An incomplete or failed wave
therefore remains pending rather than silently triggering a fallback search.

Inputs are sequence-group JSONL plus checksum-bound PSORTb and DeepTMHMM runtime
contracts.  Outputs are task bundles, per-group retained evidence, one complete
wave policy, and one reopen plan.  External execution is limited to the existing
PSORTb 3.0.6 adapter; DeepTMHMM has no command.  Candidate-local tool/parse
failures are normal typed results, while malformed coverage or checksum state
raises :class:`InputContractError`.  Task, evidence, policy, completion, and
reopen identities are the cache keys.  Focused Python and Nextflow-stub tests
cover ordering, exact coverage, failed/empty branches, retention, activation,
and cached resume.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import (
    canonical_digest,
    canonical_json_text,
    content_id,
    identity_view,
)
from genome_to_diffraction.localisation.adapters import (
    plan_deeptmhmm_invocation,
    run_psortb,
)
from genome_to_diffraction.localisation.contracts import (
    DeepTMHMMInvocationPlan,
    DeepTMHMMRuntimeContract,
    LocalisationOutcome,
    LocalisationResult,
    OfflineExecutionProvenance,
    PSortbCommandRecord,
    PSortbRuntimeContract,
    resolve_localisation_outcome,
)
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    Sha256Hex,
)
from genome_to_diffraction.schemas.results import SequenceGroupRecord
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_TASK_ADAPTER_VERSION = "catalogue-localisation-task-v1"
_POLICY_VERSION = "phase3-localisation-wave-v1"
_REOPEN_POLICY_VERSION = "phase3-localisation-reopen-v1"

_EXCLUDED_OUTCOMES = frozenset(
    {
        LocalisationOutcome.MEMBRANE,
        LocalisationOutcome.SURFACE,
        LocalisationOutcome.EXTRACELLULAR,
        LocalisationOutcome.TRANSMEMBRANE,
    }
)


def _task_payload(
    *,
    sequence_group: SequenceGroupRecord,
    input_fasta_sha256: str,
    psortb_runtime_identity_sha256: str,
    deeptmhmm_runtime_identity_sha256: str,
) -> dict[str, object]:
    return {
        "adapter_version": _TASK_ADAPTER_VERSION,
        "deeptmhmm_runtime_identity_sha256": (deeptmhmm_runtime_identity_sha256),
        "input_fasta_sha256": input_fasta_sha256,
        "psortb_runtime_identity_sha256": psortb_runtime_identity_sha256,
        "sequence_group": sequence_group,
    }


class LocalisationTaskItem(ContractModel):
    """One deterministic external-tool item for one exact sequence group."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["catalogue-localisation-task-v1"] = _TASK_ADAPTER_VERSION
    task_id: NonEmptyString
    sequence_group: SequenceGroupRecord
    input_fasta_sha256: Sha256Hex
    psortb_runtime_identity_sha256: Sha256Hex
    deeptmhmm_runtime_identity_sha256: Sha256Hex

    @classmethod
    def from_group(
        cls,
        sequence_group: SequenceGroupRecord,
        *,
        input_fasta_sha256: str,
        psortb_runtime_identity_sha256: str,
        deeptmhmm_runtime_identity_sha256: str,
    ) -> Self:
        """Build a content-addressed task without depending on catalogue order."""

        payload = _task_payload(
            sequence_group=sequence_group,
            input_fasta_sha256=input_fasta_sha256,
            psortb_runtime_identity_sha256=psortb_runtime_identity_sha256,
            deeptmhmm_runtime_identity_sha256=(deeptmhmm_runtime_identity_sha256),
        )
        return cls(
            task_id=content_id("localisationtask_", payload),
            sequence_group=sequence_group,
            input_fasta_sha256=input_fasta_sha256,
            psortb_runtime_identity_sha256=psortb_runtime_identity_sha256,
            deeptmhmm_runtime_identity_sha256=(deeptmhmm_runtime_identity_sha256),
        )

    @model_validator(mode="after")
    def _validate_task_identity(self) -> Self:
        expected = content_id(
            "localisationtask_",
            _task_payload(
                sequence_group=self.sequence_group,
                input_fasta_sha256=self.input_fasta_sha256,
                psortb_runtime_identity_sha256=(self.psortb_runtime_identity_sha256),
                deeptmhmm_runtime_identity_sha256=(
                    self.deeptmhmm_runtime_identity_sha256
                ),
            ),
        )
        if self.task_id != expected:
            raise ValueError("localisation task identity does not match its content")
        return self

    @property
    def sequence_group_id(self) -> str:
        """Return the immutable sequence-equivalence group identifier."""

        return self.sequence_group.sequence_group_id


class LocalisationTaskInventory(ContractModel):
    """Complete, duplicate-free catalogue-to-task materialisation."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["catalogue-localisation-task-v1"] = _TASK_ADAPTER_VERSION
    inventory_id: NonEmptyString
    source_sequence_groups_sha256: Sha256Hex
    psortb_runtime_contract_sha256: Sha256Hex
    deeptmhmm_runtime_contract_sha256: Sha256Hex
    psortb_runtime_identity_sha256: Sha256Hex
    deeptmhmm_runtime_identity_sha256: Sha256Hex
    task_count: int = Field(ge=0)
    tasks: tuple[LocalisationTaskItem, ...]

    @classmethod
    def from_tasks(
        cls,
        tasks: Sequence[LocalisationTaskItem],
        *,
        source_sequence_groups_sha256: str,
        psortb_runtime_contract_sha256: str,
        deeptmhmm_runtime_contract_sha256: str,
        psortb_runtime_identity_sha256: str,
        deeptmhmm_runtime_identity_sha256: str,
    ) -> Self:
        """Build an order-invariant inventory while retaining source checksums."""

        ordered = tuple(sorted(tasks, key=lambda item: item.sequence_group_id))
        payload = {
            "adapter_version": _TASK_ADAPTER_VERSION,
            "deeptmhmm_runtime_identity_sha256": (deeptmhmm_runtime_identity_sha256),
            "psortb_runtime_identity_sha256": psortb_runtime_identity_sha256,
            "tasks": ordered,
        }
        return cls(
            inventory_id=content_id("localisationinventory_", payload),
            source_sequence_groups_sha256=source_sequence_groups_sha256,
            psortb_runtime_contract_sha256=psortb_runtime_contract_sha256,
            deeptmhmm_runtime_contract_sha256=(deeptmhmm_runtime_contract_sha256),
            psortb_runtime_identity_sha256=psortb_runtime_identity_sha256,
            deeptmhmm_runtime_identity_sha256=(deeptmhmm_runtime_identity_sha256),
            task_count=len(ordered),
            tasks=ordered,
        )

    @model_validator(mode="after")
    def _validate_inventory(self) -> Self:
        ordered = tuple(sorted(self.tasks, key=lambda item: item.sequence_group_id))
        if self.tasks != ordered:
            raise ValueError("localisation tasks must be ordered by sequence group")
        if self.task_count != len(self.tasks):
            raise ValueError("localisation task count does not match its inventory")
        group_ids = tuple(item.sequence_group_id for item in self.tasks)
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("duplicate sequence group in localisation inventory")
        if any(
            task.psortb_runtime_identity_sha256 != self.psortb_runtime_identity_sha256
            or task.deeptmhmm_runtime_identity_sha256
            != self.deeptmhmm_runtime_identity_sha256
            for task in self.tasks
        ):
            raise ValueError("localisation task uses a different runtime identity")
        expected = content_id(
            "localisationinventory_",
            {
                "adapter_version": self.adapter_version,
                "deeptmhmm_runtime_identity_sha256": (
                    self.deeptmhmm_runtime_identity_sha256
                ),
                "psortb_runtime_identity_sha256": (self.psortb_runtime_identity_sha256),
                "tasks": self.tasks,
            },
        )
        if self.inventory_id != expected:
            raise ValueError(
                "localisation inventory identity does not match its content"
            )
        return self


def _blocked_result_payload(
    *,
    block_reason: str,
    invocation_identity_sha256: str,
    provenance: OfflineExecutionProvenance,
    runtime_identity_sha256: str,
    sequence_group_id: str,
    sequence_sha256: str,
) -> dict[str, object]:
    return {
        "block_reason": block_reason,
        "execution_status": "skipped_policy",
        "invocation_identity_sha256": invocation_identity_sha256,
        "provenance": provenance,
        "runtime_identity_sha256": runtime_identity_sha256,
        "sequence_group_id": sequence_group_id,
        "sequence_sha256": sequence_sha256,
        "tool": "deeptmhmm",
        "tool_version": "1.0",
    }


class DeepTMHMMBlockedResult(ContractModel):
    """One typed non-execution result; it is not a scientific prediction."""

    schema_version: Literal["1.0"] = "1.0"
    blocked_result_id: NonEmptyString
    tool: Literal["deeptmhmm"] = "deeptmhmm"
    tool_version: Literal["1.0"] = "1.0"
    runtime_identity_sha256: Sha256Hex
    sequence_group_id: NonEmptyString
    sequence_sha256: Sha256Hex
    invocation_identity_sha256: Sha256Hex
    execution_status: Literal["skipped_policy"] = "skipped_policy"
    invocation_status: Literal["blocked_unverified_cli"] = "blocked_unverified_cli"
    outcome: None = None
    command: tuple[str, ...] = ()
    block_reason: NonEmptyString
    provenance: OfflineExecutionProvenance = Field(
        default_factory=OfflineExecutionProvenance
    )

    @classmethod
    def from_plan(cls, plan: DeepTMHMMInvocationPlan) -> Self:
        """Convert a verified blocked invocation plan into a typed result."""

        payload = _blocked_result_payload(
            block_reason=plan.block_reason,
            invocation_identity_sha256=plan.invocation_identity_sha256,
            provenance=plan.provenance,
            runtime_identity_sha256=plan.runtime_identity_sha256,
            sequence_group_id=plan.sequence_group_id,
            sequence_sha256=plan.sequence_sha256,
        )
        return cls(
            blocked_result_id=content_id("deeptmhmmblocked_", payload),
            runtime_identity_sha256=plan.runtime_identity_sha256,
            sequence_group_id=plan.sequence_group_id,
            sequence_sha256=plan.sequence_sha256,
            invocation_identity_sha256=plan.invocation_identity_sha256,
            block_reason=plan.block_reason,
            provenance=plan.provenance,
        )

    @model_validator(mode="after")
    def _validate_blocked_result(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError("blocked result sequence identity is inconsistent")
        if self.command or self.outcome is not None:
            raise ValueError("blocked DeepTMHMM result cannot fabricate an outcome")
        payload = _blocked_result_payload(
            block_reason=self.block_reason,
            invocation_identity_sha256=self.invocation_identity_sha256,
            provenance=self.provenance,
            runtime_identity_sha256=self.runtime_identity_sha256,
            sequence_group_id=self.sequence_group_id,
            sequence_sha256=self.sequence_sha256,
        )
        expected = content_id(
            "deeptmhmmblocked_",
            payload,
        )
        if self.blocked_result_id != expected:
            raise ValueError("blocked result identity does not match its content")
        return self


class FirstWaveDisposition(StrEnum):
    """Localisation-only disposition before other ranking evidence is applied."""

    ACTIVE = "active"
    EXCLUDED = "excluded"
    NEUTRAL = "neutral"


def first_wave_disposition(
    outcome: LocalisationOutcome,
) -> FirstWaveDisposition:
    """Map an outcome without treating uncertainty or failure as exclusion."""

    if outcome is LocalisationOutcome.SOLUBLE:
        return FirstWaveDisposition.ACTIVE
    if outcome in _EXCLUDED_OUTCOMES:
        return FirstWaveDisposition.EXCLUDED
    return FirstWaveDisposition.NEUTRAL


def localisation_result_identity(result: LocalisationResult) -> str:
    """Return a path-independent identity for one retained adapter result."""

    return canonical_digest(
        identity_view(
            result,
            exclude_fields=frozenset({"raw_output_path", "raw_stderr_path"}),
        )
    )


def _group_evidence_payload(
    *,
    task_id: str,
    sequence_group_id: str,
    sequence_sha256: str,
    psortb_execution_status: ExecutionStatus,
    psortb_outcome: LocalisationOutcome,
    psortb_result_identity_sha256: str,
    deeptmhmm_blocked_result_id: str,
    merged_outcome: LocalisationOutcome,
    disposition: FirstWaveDisposition,
    first_wave_eligible: bool,
) -> dict[str, object]:
    return {
        "deeptmhmm_blocked_result_id": deeptmhmm_blocked_result_id,
        "first_wave_disposition": disposition,
        "first_wave_eligible": first_wave_eligible,
        "merged_outcome": merged_outcome,
        "policy_version": _POLICY_VERSION,
        "psortb_execution_status": psortb_execution_status,
        "psortb_outcome": psortb_outcome,
        "psortb_result_identity_sha256": psortb_result_identity_sha256,
        "sequence_group_id": sequence_group_id,
        "sequence_sha256": sequence_sha256,
        "task_id": task_id,
    }


class LocalisationGroupEvidence(ContractModel):
    """Merged evidence and first-wave decision for one exact sequence group."""

    schema_version: Literal["1.0"] = "1.0"
    policy_version: Literal["phase3-localisation-wave-v1"] = _POLICY_VERSION
    evidence_id: NonEmptyString
    task_id: NonEmptyString
    sequence_group_id: NonEmptyString
    sequence_sha256: Sha256Hex
    psortb_execution_status: ExecutionStatus
    psortb_outcome: LocalisationOutcome
    psortb_result_identity_sha256: Sha256Hex
    deeptmhmm_blocked_result_id: NonEmptyString
    merged_outcome: LocalisationOutcome
    first_wave_disposition: FirstWaveDisposition
    first_wave_eligible: bool

    @classmethod
    def from_results(
        cls,
        task: LocalisationTaskItem,
        psortb_result: LocalisationResult,
        deeptmhmm_result: DeepTMHMMBlockedResult,
    ) -> Self:
        """Merge one executed PSORTb result with one blocked DeepTMHMM result."""

        merged = resolve_localisation_outcome((psortb_result.outcome,))
        disposition = first_wave_disposition(merged)
        eligible = disposition is not FirstWaveDisposition.EXCLUDED
        result_identity = localisation_result_identity(psortb_result)
        payload = _group_evidence_payload(
            task_id=task.task_id,
            sequence_group_id=task.sequence_group_id,
            sequence_sha256=task.sequence_group.sha256,
            psortb_execution_status=psortb_result.execution_status,
            psortb_outcome=psortb_result.outcome,
            psortb_result_identity_sha256=result_identity,
            deeptmhmm_blocked_result_id=(deeptmhmm_result.blocked_result_id),
            merged_outcome=merged,
            disposition=disposition,
            first_wave_eligible=eligible,
        )
        return cls(
            evidence_id=content_id("localevidence_", payload),
            task_id=task.task_id,
            sequence_group_id=task.sequence_group_id,
            sequence_sha256=task.sequence_group.sha256,
            psortb_execution_status=psortb_result.execution_status,
            psortb_outcome=psortb_result.outcome,
            psortb_result_identity_sha256=result_identity,
            deeptmhmm_blocked_result_id=(deeptmhmm_result.blocked_result_id),
            merged_outcome=merged,
            first_wave_disposition=disposition,
            first_wave_eligible=eligible,
        )

    @model_validator(mode="after")
    def _validate_evidence(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError("group evidence sequence identity is inconsistent")
        expected_merged = resolve_localisation_outcome((self.psortb_outcome,))
        if self.merged_outcome is not expected_merged:
            raise ValueError("merged outcome does not match executed tool evidence")
        failed_statuses = {
            ExecutionStatus.FAILED_TOOL_EXECUTION,
            ExecutionStatus.FAILED_PARSE,
        }
        if (self.psortb_execution_status in failed_statuses) != (
            self.psortb_outcome is LocalisationOutcome.FAILED
        ):
            raise ValueError("PSORTb status and outcome are inconsistent")
        expected_disposition = first_wave_disposition(self.merged_outcome)
        if self.first_wave_disposition is not expected_disposition:
            raise ValueError("first-wave disposition does not match merged outcome")
        if self.first_wave_eligible != (
            expected_disposition is not FirstWaveDisposition.EXCLUDED
        ):
            raise ValueError("first-wave eligibility does not match disposition")
        expected = content_id(
            "localevidence_",
            _group_evidence_payload(
                task_id=self.task_id,
                sequence_group_id=self.sequence_group_id,
                sequence_sha256=self.sequence_sha256,
                psortb_execution_status=self.psortb_execution_status,
                psortb_outcome=self.psortb_outcome,
                psortb_result_identity_sha256=(self.psortb_result_identity_sha256),
                deeptmhmm_blocked_result_id=(self.deeptmhmm_blocked_result_id),
                merged_outcome=self.merged_outcome,
                disposition=self.first_wave_disposition,
                first_wave_eligible=self.first_wave_eligible,
            ),
        )
        if self.evidence_id != expected:
            raise ValueError("group evidence identity does not match its content")
        return self


def _policy_payload(
    inventory_id: str,
    group_evidence: tuple[LocalisationGroupEvidence, ...],
) -> dict[str, object]:
    return {
        "group_evidence": group_evidence,
        "policy_version": _POLICY_VERSION,
        "task_inventory_id": inventory_id,
    }


class CatalogueLocalisationWavePolicy(ContractModel):
    """Complete catalogue disposition with no dropped excluded group."""

    schema_version: Literal["1.0"] = "1.0"
    policy_version: Literal["phase3-localisation-wave-v1"] = _POLICY_VERSION
    policy_id: NonEmptyString
    task_inventory_id: NonEmptyString
    sequence_group_count: int = Field(ge=0)
    result_count: int = Field(ge=0)
    psortb_completed_count: int = Field(ge=0)
    psortb_failed_count: int = Field(ge=0)
    deeptmhmm_blocked_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    neutral_count: int = Field(ge=0)
    first_wave_eligible_count: int = Field(ge=0)
    first_wave_group_ids: tuple[NonEmptyString, ...]
    retained_excluded_group_ids: tuple[NonEmptyString, ...]
    group_evidence: tuple[LocalisationGroupEvidence, ...]

    @classmethod
    def from_evidence(
        cls,
        inventory: LocalisationTaskInventory,
        evidence: Sequence[LocalisationGroupEvidence],
    ) -> Self:
        """Build a deterministic policy after exact result coverage is verified."""

        ordered = tuple(sorted(evidence, key=lambda item: item.sequence_group_id))
        active = tuple(
            item.sequence_group_id
            for item in ordered
            if item.first_wave_disposition is FirstWaveDisposition.ACTIVE
        )
        excluded = tuple(
            item.sequence_group_id
            for item in ordered
            if item.first_wave_disposition is FirstWaveDisposition.EXCLUDED
        )
        neutral = tuple(
            item.sequence_group_id
            for item in ordered
            if item.first_wave_disposition is FirstWaveDisposition.NEUTRAL
        )
        failed_count = sum(
            item.psortb_execution_status
            in {
                ExecutionStatus.FAILED_TOOL_EXECUTION,
                ExecutionStatus.FAILED_PARSE,
            }
            for item in ordered
        )
        return cls(
            policy_id=content_id(
                "localisationpolicy_",
                _policy_payload(inventory.inventory_id, ordered),
            ),
            task_inventory_id=inventory.inventory_id,
            sequence_group_count=inventory.task_count,
            result_count=len(ordered),
            psortb_completed_count=len(ordered) - failed_count,
            psortb_failed_count=failed_count,
            deeptmhmm_blocked_count=len(ordered),
            active_count=len(active),
            excluded_count=len(excluded),
            neutral_count=len(neutral),
            first_wave_eligible_count=len(active) + len(neutral),
            first_wave_group_ids=active + neutral,
            retained_excluded_group_ids=excluded,
            group_evidence=ordered,
        )

    @model_validator(mode="after")
    def _validate_policy(self) -> Self:
        ordered = tuple(
            sorted(self.group_evidence, key=lambda item: item.sequence_group_id)
        )
        if self.group_evidence != ordered:
            raise ValueError("group evidence must be ordered by sequence group")
        group_ids = tuple(item.sequence_group_id for item in ordered)
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("duplicate group evidence in localisation policy")
        active = tuple(
            item.sequence_group_id
            for item in ordered
            if item.first_wave_disposition is FirstWaveDisposition.ACTIVE
        )
        excluded = tuple(
            item.sequence_group_id
            for item in ordered
            if item.first_wave_disposition is FirstWaveDisposition.EXCLUDED
        )
        neutral = tuple(
            item.sequence_group_id
            for item in ordered
            if item.first_wave_disposition is FirstWaveDisposition.NEUTRAL
        )
        failed_count = sum(
            item.psortb_execution_status
            in {
                ExecutionStatus.FAILED_TOOL_EXECUTION,
                ExecutionStatus.FAILED_PARSE,
            }
            for item in ordered
        )
        expected_counts = (
            len(ordered),
            len(ordered),
            len(ordered) - failed_count,
            failed_count,
            len(ordered),
            len(active),
            len(excluded),
            len(neutral),
            len(active) + len(neutral),
        )
        actual_counts = (
            self.sequence_group_count,
            self.result_count,
            self.psortb_completed_count,
            self.psortb_failed_count,
            self.deeptmhmm_blocked_count,
            self.active_count,
            self.excluded_count,
            self.neutral_count,
            self.first_wave_eligible_count,
        )
        if actual_counts != expected_counts:
            raise ValueError("localisation policy counts do not match its evidence")
        if self.first_wave_group_ids != active + neutral:
            raise ValueError("first-wave group inventory is incomplete or reordered")
        if self.retained_excluded_group_ids != excluded:
            raise ValueError("excluded sequence group was not retained")
        expected = content_id(
            "localisationpolicy_",
            _policy_payload(self.task_inventory_id, self.group_evidence),
        )
        if self.policy_id != expected:
            raise ValueError("localisation policy identity does not match its content")
        return self


class ActiveWaveResultStatus(StrEnum):
    """Outcome needed only to decide whether excluded groups may reopen."""

    PACKED = "packed"
    COMPLETED_NO_PACKED_RESULT = "completed_no_packed_result"
    FAILED = "failed"


class ActiveWaveGroupResult(ContractModel):
    """One first-wave group result with an immutable upstream result checksum."""

    sequence_group_id: NonEmptyString
    status: ActiveWaveResultStatus
    source_result_sha256: Sha256Hex


def _completion_payload(
    first_wave_group_ids: tuple[str, ...],
    results: tuple[ActiveWaveGroupResult, ...],
) -> dict[str, object]:
    return {
        "first_wave_group_ids": first_wave_group_ids,
        "results": results,
    }


class ActiveWaveCompletion(ContractModel):
    """Exact active-wave accounting; failed or missing results are incomplete."""

    schema_version: Literal["1.0"] = "1.0"
    completion_id: NonEmptyString
    first_wave_group_ids: tuple[NonEmptyString, ...]
    results: tuple[ActiveWaveGroupResult, ...]
    expected_result_count: int = Field(ge=0)
    observed_result_count: int = Field(ge=0)
    terminal_result_count: int = Field(ge=0)
    packed_group_ids: tuple[NonEmptyString, ...]
    failed_group_ids: tuple[NonEmptyString, ...]
    missing_group_ids: tuple[NonEmptyString, ...]
    active_wave_complete: bool

    @classmethod
    def from_results(
        cls,
        first_wave_group_ids: Sequence[str],
        results: Sequence[ActiveWaveGroupResult],
    ) -> Self:
        """Normalise result order and derive fail-closed completion state."""

        expected_groups = tuple(first_wave_group_ids)
        positions = {group_id: index for index, group_id in enumerate(expected_groups)}
        if len(positions) != len(expected_groups):
            raise ValueError("duplicate first-wave sequence group")
        result_by_group = {result.sequence_group_id: result for result in results}
        if len(result_by_group) != len(results):
            raise ValueError("duplicate active-wave group result")
        unknown = set(result_by_group) - set(expected_groups)
        if unknown:
            raise ValueError("active-wave result refers to an unknown group")
        ordered = tuple(
            sorted(results, key=lambda item: positions[item.sequence_group_id])
        )
        packed = tuple(
            group_id
            for group_id in expected_groups
            if group_id in result_by_group
            and result_by_group[group_id].status is ActiveWaveResultStatus.PACKED
        )
        failed = tuple(
            group_id
            for group_id in expected_groups
            if group_id in result_by_group
            and result_by_group[group_id].status is ActiveWaveResultStatus.FAILED
        )
        missing = tuple(
            group_id for group_id in expected_groups if group_id not in result_by_group
        )
        terminal_count = len(ordered) - len(failed)
        complete = not failed and not missing
        payload = _completion_payload(expected_groups, ordered)
        return cls(
            completion_id=content_id("activewavecompletion_", payload),
            first_wave_group_ids=expected_groups,
            results=ordered,
            expected_result_count=len(expected_groups),
            observed_result_count=len(ordered),
            terminal_result_count=terminal_count,
            packed_group_ids=packed,
            failed_group_ids=failed,
            missing_group_ids=missing,
            active_wave_complete=complete,
        )

    @model_validator(mode="after")
    def _validate_completion(self) -> Self:
        group_ids = self.first_wave_group_ids
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("duplicate first-wave sequence group")
        positions = {group_id: index for index, group_id in enumerate(group_ids)}
        result_by_group = {result.sequence_group_id: result for result in self.results}
        if len(result_by_group) != len(self.results):
            raise ValueError("duplicate active-wave group result")
        if set(result_by_group) - set(group_ids):
            raise ValueError("active-wave result refers to an unknown group")
        ordered = tuple(
            sorted(self.results, key=lambda item: positions[item.sequence_group_id])
        )
        if self.results != ordered:
            raise ValueError(
                "active-wave group results are not deterministically ordered"
            )
        packed = tuple(
            group_id
            for group_id in group_ids
            if group_id in result_by_group
            and result_by_group[group_id].status is ActiveWaveResultStatus.PACKED
        )
        failed = tuple(
            group_id
            for group_id in group_ids
            if group_id in result_by_group
            and result_by_group[group_id].status is ActiveWaveResultStatus.FAILED
        )
        missing = tuple(
            group_id for group_id in group_ids if group_id not in result_by_group
        )
        expected_values = (
            len(group_ids),
            len(self.results),
            len(self.results) - len(failed),
            packed,
            failed,
            missing,
            not failed and not missing,
        )
        actual_values = (
            self.expected_result_count,
            self.observed_result_count,
            self.terminal_result_count,
            self.packed_group_ids,
            self.failed_group_ids,
            self.missing_group_ids,
            self.active_wave_complete,
        )
        if actual_values != expected_values:
            raise ValueError("active-wave completion does not match its results")
        expected_id = content_id(
            "activewavecompletion_",
            _completion_payload(group_ids, self.results),
        )
        if self.completion_id != expected_id:
            raise ValueError("active-wave completion identity does not match")
        return self


class LocalisationReopenStatus(StrEnum):
    """Deterministic state of the excluded-group fallback wave."""

    ACTIVATED_NO_PACKED_RESULT = "activated_no_packed_result"
    NOT_ACTIVATED_PACKED_RESULT = "not_activated_packed_result"
    PENDING_ACTIVE_WAVE = "pending_active_wave"
    NOT_REQUIRED_NO_EXCLUDED_GROUPS = "not_required_no_excluded_groups"


def _reopen_payload(
    *,
    policy_id: str,
    completion_id: str,
    status: LocalisationReopenStatus,
    retained_excluded_group_ids: tuple[str, ...],
    reopened_group_ids: tuple[str, ...],
) -> dict[str, object]:
    return {
        "active_wave_completion_id": completion_id,
        "policy_id": policy_id,
        "policy_version": _REOPEN_POLICY_VERSION,
        "reopened_group_ids": reopened_group_ids,
        "retained_excluded_group_ids": retained_excluded_group_ids,
        "status": status,
    }


class LocalisationReopenPlan(ContractModel):
    """Retained excluded groups and the fail-closed decision to reopen them."""

    schema_version: Literal["1.0"] = "1.0"
    policy_version: Literal["phase3-localisation-reopen-v1"] = _REOPEN_POLICY_VERSION
    reopen_plan_id: NonEmptyString
    policy_id: NonEmptyString
    active_wave_completion_id: NonEmptyString
    status: LocalisationReopenStatus
    active_wave_complete: bool
    active_wave_packed_group_ids: tuple[NonEmptyString, ...]
    retained_excluded_count: int = Field(ge=0)
    retained_excluded_group_ids: tuple[NonEmptyString, ...]
    reopened_count: int = Field(ge=0)
    reopened_group_ids: tuple[NonEmptyString, ...]
    all_excluded_groups_retained: Literal[True] = True

    @classmethod
    def from_policy(
        cls,
        policy: CatalogueLocalisationWavePolicy,
        completion: ActiveWaveCompletion,
    ) -> Self:
        """Activate only after a complete wave has zero packed results."""

        excluded = policy.retained_excluded_group_ids
        if not excluded:
            status = LocalisationReopenStatus.NOT_REQUIRED_NO_EXCLUDED_GROUPS
            reopened: tuple[str, ...] = ()
        elif not completion.active_wave_complete:
            status = LocalisationReopenStatus.PENDING_ACTIVE_WAVE
            reopened = ()
        elif completion.packed_group_ids:
            status = LocalisationReopenStatus.NOT_ACTIVATED_PACKED_RESULT
            reopened = ()
        else:
            status = LocalisationReopenStatus.ACTIVATED_NO_PACKED_RESULT
            reopened = excluded
        payload = _reopen_payload(
            policy_id=policy.policy_id,
            completion_id=completion.completion_id,
            status=status,
            retained_excluded_group_ids=excluded,
            reopened_group_ids=reopened,
        )
        return cls(
            reopen_plan_id=content_id("localisationreopen_", payload),
            policy_id=policy.policy_id,
            active_wave_completion_id=completion.completion_id,
            status=status,
            active_wave_complete=completion.active_wave_complete,
            active_wave_packed_group_ids=completion.packed_group_ids,
            retained_excluded_count=len(excluded),
            retained_excluded_group_ids=excluded,
            reopened_count=len(reopened),
            reopened_group_ids=reopened,
        )

    @model_validator(mode="after")
    def _validate_reopen_plan(self) -> Self:
        if self.retained_excluded_count != len(self.retained_excluded_group_ids):
            raise ValueError("retained excluded count is inconsistent")
        if self.reopened_count != len(self.reopened_group_ids):
            raise ValueError("reopened count is inconsistent")
        if any(
            group_id not in self.retained_excluded_group_ids
            for group_id in self.reopened_group_ids
        ):
            raise ValueError("reopen plan contains a non-excluded group")
        if self.status is LocalisationReopenStatus.ACTIVATED_NO_PACKED_RESULT:
            if (
                not self.active_wave_complete
                or self.active_wave_packed_group_ids
                or self.reopened_group_ids != self.retained_excluded_group_ids
            ):
                raise ValueError("activated reopen plan violates its trigger")
        elif self.status is LocalisationReopenStatus.NOT_ACTIVATED_PACKED_RESULT:
            if (
                not self.active_wave_complete
                or not self.active_wave_packed_group_ids
                or not self.retained_excluded_group_ids
                or self.reopened_group_ids
            ):
                raise ValueError("packed-result reopen plan violates its trigger")
        elif self.status is LocalisationReopenStatus.PENDING_ACTIVE_WAVE:
            if (
                self.active_wave_complete
                or not self.retained_excluded_group_ids
                or self.reopened_group_ids
            ):
                raise ValueError("pending reopen plan violates its trigger")
        elif self.retained_excluded_group_ids or self.reopened_group_ids:
            raise ValueError("no-exclusion reopen plan contains excluded groups")
        expected = content_id(
            "localisationreopen_",
            _reopen_payload(
                policy_id=self.policy_id,
                completion_id=self.active_wave_completion_id,
                status=self.status,
                retained_excluded_group_ids=(self.retained_excluded_group_ids),
                reopened_group_ids=self.reopened_group_ids,
            ),
        )
        if self.reopen_plan_id != expected:
            raise ValueError("reopen plan identity does not match its content")
        return self


@dataclass(frozen=True)
class LocalisationTaskBuildOutput:
    """Published catalogue task inventory paths."""

    inventory: LocalisationTaskInventory
    inventory_json: Path
    task_index_tsv: Path


@dataclass(frozen=True)
class LocalisationTaskRunOutput:
    """Published files for one terminal sequence-group task."""

    task: LocalisationTaskItem
    psortb_result: LocalisationResult
    deeptmhmm_result: DeepTMHMMBlockedResult
    group_evidence: LocalisationGroupEvidence
    output_directory: Path


@dataclass(frozen=True)
class LocalisationWavePolicyOutput:
    """Published complete catalogue policy paths."""

    policy: CatalogueLocalisationWavePolicy
    policy_json: Path
    evidence_jsonl: Path
    excluded_jsonl: Path


@dataclass(frozen=True)
class LocalisationReopenOutput:
    """Published deterministic fallback plan paths."""

    plan: LocalisationReopenPlan
    plan_json: Path
    retained_excluded_jsonl: Path
    reopened_group_ids: Path


def _read_contract[T: ContractModel](
    path: Path,
    model: type[T],
    *,
    label: str,
) -> T:
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise OSError("not a regular file")
        return model.model_validate_json(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise InputContractError(f"cannot load {label}: {path}: {error}") from error


def _read_sequence_groups(path: Path) -> tuple[SequenceGroupRecord, ...]:
    try:
        resolved = path.resolve(strict=True)
        lines = resolved.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise InputContractError(f"cannot read sequence-group JSONL: {path}") from error
    records: list[SequenceGroupRecord] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(SequenceGroupRecord.model_validate_json(line))
        except ValueError as error:
            raise InputContractError(
                f"invalid sequence group at line {line_number}: {error}"
            ) from error
    ordered = tuple(sorted(records, key=lambda item: item.sequence_group_id))
    group_ids = tuple(item.sequence_group_id for item in ordered)
    if len(set(group_ids)) != len(group_ids):
        raise InputContractError("duplicate sequence group in localisation input")
    return ordered


def _new_directory(path: Path, *, label: str) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise InputContractError(f"{label} already exists: {path}") from error
    return path


def _fasta_text(group: SequenceGroupRecord) -> str:
    return f">{group.sequence_group_id}\n{group.sequence}\n"


def build_catalogue_localisation_tasks(
    sequence_groups_jsonl: Path,
    psortb_runtime_json: Path,
    deeptmhmm_runtime_json: Path,
    output_directory: Path,
) -> LocalisationTaskBuildOutput:
    """Materialise exactly one deterministic task for each supplied group."""

    groups = _read_sequence_groups(sequence_groups_jsonl)
    psortb_runtime = _read_contract(
        psortb_runtime_json,
        PSortbRuntimeContract,
        label="PSORTb runtime contract",
    )
    deeptmhmm_runtime = _read_contract(
        deeptmhmm_runtime_json,
        DeepTMHMMRuntimeContract,
        label="DeepTMHMM runtime contract",
    )
    output = _new_directory(output_directory, label="localisation task output")
    tasks_root = output / "tasks"
    tasks_root.mkdir()
    tasks: list[LocalisationTaskItem] = []
    for group in groups:
        fasta_text = _fasta_text(group)
        fasta_sha256 = hashlib.sha256(fasta_text.encode("ascii")).hexdigest()
        task = LocalisationTaskItem.from_group(
            group,
            input_fasta_sha256=fasta_sha256,
            psortb_runtime_identity_sha256=(psortb_runtime.runtime_identity_sha256),
            deeptmhmm_runtime_identity_sha256=(
                deeptmhmm_runtime.runtime_identity_sha256
            ),
        )
        task_root = tasks_root / task.task_id
        task_root.mkdir()
        atomic_write_json(task_root / "task.json", task.model_dump(mode="json"))
        atomic_write_json(
            task_root / "sequence-group.json",
            group.model_dump(mode="json"),
        )
        atomic_write_text(
            task_root / "sequence.faa",
            fasta_text,
            encoding="ascii",
        )
        tasks.append(task)
    inventory = LocalisationTaskInventory.from_tasks(
        tasks,
        source_sequence_groups_sha256=sha256_file(sequence_groups_jsonl),
        psortb_runtime_contract_sha256=sha256_file(psortb_runtime_json),
        deeptmhmm_runtime_contract_sha256=sha256_file(deeptmhmm_runtime_json),
        psortb_runtime_identity_sha256=psortb_runtime.runtime_identity_sha256,
        deeptmhmm_runtime_identity_sha256=(deeptmhmm_runtime.runtime_identity_sha256),
    )
    inventory_json = output / "localisation_task_inventory.json"
    atomic_write_json(inventory_json, inventory.model_dump(mode="json"))
    task_index = output / "localisation_tasks.tsv"
    index_lines = ["task_id\tsequence_group_id\ttask_path"]
    index_lines.extend(
        f"{task.task_id}\t{task.sequence_group_id}\ttasks/{task.task_id}"
        for task in inventory.tasks
    )
    atomic_write_text(task_index, "\n".join(index_lines) + "\n")
    return LocalisationTaskBuildOutput(
        inventory=inventory,
        inventory_json=inventory_json,
        task_index_tsv=task_index,
    )


def _load_task_directory(path: Path) -> LocalisationTaskItem:
    task = _read_contract(path / "task.json", LocalisationTaskItem, label="task")
    group = _read_contract(
        path / "sequence-group.json",
        SequenceGroupRecord,
        label="task sequence group",
    )
    if group != task.sequence_group:
        raise InputContractError("task sequence-group file changed")
    fasta = path / "sequence.faa"
    try:
        fasta_text = fasta.read_text(encoding="ascii")
    except (OSError, UnicodeError) as error:
        raise InputContractError(f"cannot read task FASTA: {fasta}") from error
    if (
        fasta_text != _fasta_text(group)
        or sha256_file(fasta) != task.input_fasta_sha256
    ):
        raise InputContractError("task FASTA does not match its sequence group")
    return task


def run_catalogue_localisation_task(
    task_directory: Path,
    psortb_runtime_json: Path,
    deeptmhmm_runtime_json: Path,
    output_directory: Path,
) -> LocalisationTaskRunOutput:
    """Run PSORTb once and retain one blocked DeepTMHMM result for one task."""

    task = _load_task_directory(task_directory)
    psortb_runtime = _read_contract(
        psortb_runtime_json,
        PSortbRuntimeContract,
        label="PSORTb runtime contract",
    )
    deeptmhmm_runtime = _read_contract(
        deeptmhmm_runtime_json,
        DeepTMHMMRuntimeContract,
        label="DeepTMHMM runtime contract",
    )
    if (
        task.psortb_runtime_identity_sha256 != psortb_runtime.runtime_identity_sha256
        or task.deeptmhmm_runtime_identity_sha256
        != deeptmhmm_runtime.runtime_identity_sha256
    ):
        raise InputContractError("localisation task runtime identity changed")
    output = _new_directory(output_directory, label="localisation task result")
    atomic_write_json(output / "localisation-task.json", task.model_dump(mode="json"))
    psortb = run_psortb(psortb_runtime, task.sequence_group, output / "psortb")
    invocation = plan_deeptmhmm_invocation(
        deeptmhmm_runtime,
        task.sequence_group,
        task_directory / "sequence.faa",
    )
    blocked = DeepTMHMMBlockedResult.from_plan(invocation)
    evidence = LocalisationGroupEvidence.from_results(
        task,
        psortb.result,
        blocked,
    )
    atomic_write_json(
        output / "deeptmhmm-invocation-plan.json",
        invocation.model_dump(mode="json"),
    )
    atomic_write_json(
        output / "deeptmhmm-blocked-result.json",
        blocked.model_dump(mode="json"),
    )
    atomic_write_json(
        output / "group-localisation-evidence.json",
        evidence.model_dump(mode="json"),
    )
    return LocalisationTaskRunOutput(
        task=task,
        psortb_result=psortb.result,
        deeptmhmm_result=blocked,
        group_evidence=evidence,
        output_directory=output,
    )


def _load_task_inventory(path: Path) -> LocalisationTaskInventory:
    inventory = _read_contract(
        path / "localisation_task_inventory.json",
        LocalisationTaskInventory,
        label="localisation task inventory",
    )
    expected_rows = ["task_id\tsequence_group_id\ttask_path"]
    for task in inventory.tasks:
        task_root = path / "tasks" / task.task_id
        loaded = _load_task_directory(task_root)
        if loaded != task:
            raise InputContractError("task inventory does not match its task file")
        expected_rows.append(
            f"{task.task_id}\t{task.sequence_group_id}\ttasks/{task.task_id}"
        )
    try:
        actual_index = (path / "localisation_tasks.tsv").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise InputContractError("cannot read localisation task index") from error
    if actual_index != "\n".join(expected_rows) + "\n":
        raise InputContractError("localisation task index does not match inventory")
    return inventory


def _load_result_directory(
    path: Path,
) -> tuple[LocalisationTaskItem, LocalisationGroupEvidence]:
    task = _read_contract(
        path / "localisation-task.json",
        LocalisationTaskItem,
        label="result task",
    )
    psortb_result = _read_contract(
        path / "psortb/localisation-result.json",
        LocalisationResult,
        label="PSORTb result",
    )
    command = _read_contract(
        path / "psortb/psortb-command.json",
        PSortbCommandRecord,
        label="PSORTb command",
    )
    invocation = _read_contract(
        path / "deeptmhmm-invocation-plan.json",
        DeepTMHMMInvocationPlan,
        label="DeepTMHMM invocation plan",
    )
    blocked = _read_contract(
        path / "deeptmhmm-blocked-result.json",
        DeepTMHMMBlockedResult,
        label="blocked DeepTMHMM result",
    )
    evidence = _read_contract(
        path / "group-localisation-evidence.json",
        LocalisationGroupEvidence,
        label="group localisation evidence",
    )
    if (
        psortb_result.sequence_group_id != task.sequence_group_id
        or psortb_result.sequence_sha256 != task.sequence_group.sha256
        or psortb_result.runtime_identity_sha256 != task.psortb_runtime_identity_sha256
        or command.command_identity_sha256 != psortb_result.command_identity_sha256
        or command.sequence_group_id != task.sequence_group_id
        or command.input_fasta_sha256 != task.input_fasta_sha256
        or invocation.sequence_group_id != task.sequence_group_id
        or invocation.runtime_identity_sha256 != task.deeptmhmm_runtime_identity_sha256
        or invocation.input_fasta_sha256 != task.input_fasta_sha256
        or blocked.invocation_identity_sha256 != invocation.invocation_identity_sha256
    ):
        raise InputContractError("localisation result does not match its task")
    expected_raw = path / "psortb/raw/psortb-terse.tsv"
    expected_stderr = path / "psortb/raw/psortb.stderr.log"
    expected_fasta = path / "psortb/raw/sequence.faa"
    try:
        raw_sha256 = sha256_file(expected_raw)
        stderr_sha256 = sha256_file(expected_stderr)
        fasta_sha256 = sha256_file(expected_fasta)
    except OSError as error:
        raise InputContractError(
            "retained PSORTb raw evidence is missing or unreadable"
        ) from error
    if (
        raw_sha256 != psortb_result.raw_output_sha256
        or stderr_sha256 != psortb_result.raw_stderr_sha256
        or fasta_sha256 != task.input_fasta_sha256
    ):
        raise InputContractError("retained PSORTb raw evidence checksum changed")
    expected_evidence = LocalisationGroupEvidence.from_results(
        task,
        psortb_result,
        blocked,
    )
    if evidence != expected_evidence:
        raise InputContractError("merged localisation evidence changed")
    return task, evidence


def build_catalogue_localisation_wave_policy(
    task_inventory_directory: Path,
    result_directories: Sequence[Path],
    output_directory: Path,
) -> LocalisationWavePolicyOutput:
    """Require exactly one result per task and retain every group disposition."""

    inventory = _load_task_inventory(task_inventory_directory)
    evidence_by_group: dict[str, LocalisationGroupEvidence] = {}
    task_by_group = {task.sequence_group_id: task for task in inventory.tasks}
    for result_directory in result_directories:
        task, evidence = _load_result_directory(result_directory)
        expected_task = task_by_group.get(task.sequence_group_id)
        if expected_task is None or expected_task != task:
            raise InputContractError("localisation result refers to an unknown task")
        if task.sequence_group_id in evidence_by_group:
            raise InputContractError("duplicate localisation result for sequence group")
        evidence_by_group[task.sequence_group_id] = evidence
    missing = set(task_by_group) - set(evidence_by_group)
    if missing:
        raise InputContractError(
            "missing localisation result for sequence group: " + sorted(missing)[0]
        )
    policy = CatalogueLocalisationWavePolicy.from_evidence(
        inventory,
        tuple(evidence_by_group.values()),
    )
    output = _new_directory(output_directory, label="localisation wave policy output")
    policy_json = output / "first_wave_policy.json"
    evidence_jsonl = output / "group_localisation_evidence.jsonl"
    excluded_jsonl = output / "retained_excluded_groups.jsonl"
    atomic_write_json(policy_json, policy.model_dump(mode="json"))
    atomic_write_text(
        evidence_jsonl,
        "".join(f"{canonical_json_text(item)}\n" for item in policy.group_evidence),
    )
    excluded = tuple(
        item
        for item in policy.group_evidence
        if item.first_wave_disposition is FirstWaveDisposition.EXCLUDED
    )
    atomic_write_text(
        excluded_jsonl,
        "".join(f"{canonical_json_text(item)}\n" for item in excluded),
    )
    atomic_write_text(
        output / "first_wave_sequence_group_ids.txt",
        "".join(f"{group_id}\n" for group_id in policy.first_wave_group_ids),
    )
    atomic_write_text(
        output / "excluded_sequence_group_ids.txt",
        "".join(f"{group_id}\n" for group_id in policy.retained_excluded_group_ids),
    )
    return LocalisationWavePolicyOutput(
        policy=policy,
        policy_json=policy_json,
        evidence_jsonl=evidence_jsonl,
        excluded_jsonl=excluded_jsonl,
    )


def plan_localisation_reopen(
    wave_policy_json: Path,
    active_wave_completion_json: Path,
    output_directory: Path,
) -> LocalisationReopenOutput:
    """Retain excluded groups and open them only after a complete zero-pack wave."""

    policy = _read_contract(
        wave_policy_json,
        CatalogueLocalisationWavePolicy,
        label="localisation wave policy",
    )
    completion = _read_contract(
        active_wave_completion_json,
        ActiveWaveCompletion,
        label="active-wave completion",
    )
    if completion.first_wave_group_ids != policy.first_wave_group_ids:
        raise InputContractError(
            "active-wave completion does not match the first-wave inventory"
        )
    plan = LocalisationReopenPlan.from_policy(policy, completion)
    output = _new_directory(output_directory, label="localisation reopen output")
    plan_json = output / "localisation_reopen_plan.json"
    retained_jsonl = output / "retained_excluded_groups.jsonl"
    reopened_ids = output / "reopened_sequence_group_ids.txt"
    atomic_write_json(plan_json, plan.model_dump(mode="json"))
    excluded = {
        item.sequence_group_id: item
        for item in policy.group_evidence
        if item.first_wave_disposition is FirstWaveDisposition.EXCLUDED
    }
    atomic_write_text(
        retained_jsonl,
        "".join(
            f"{canonical_json_text(excluded[group_id])}\n"
            for group_id in plan.retained_excluded_group_ids
        ),
    )
    atomic_write_text(
        reopened_ids,
        "".join(f"{group_id}\n" for group_id in plan.reopened_group_ids),
    )
    return LocalisationReopenOutput(
        plan=plan,
        plan_json=plan_json,
        retained_excluded_jsonl=retained_jsonl,
        reopened_group_ids=reopened_ids,
    )
