"""Offline localisation contracts for one exact sequence-equivalence group.

The records bind sequence, executable or user-image checksum, tool version, raw
output, and the explicit prohibition on public sequence submission.  They do not
rank candidates or schedule work.  PSORTb failures are typed results; DeepTMHMM
remains a blocked invocation plan until its user-provided image exposes a verified
local command and output contract.
"""

from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    Sha256Hex,
)
from genome_to_diffraction.status import ExecutionStatus

_PSORTB_ADAPTER_VERSION = "psortb-archaea-v1"
_DEEPTMHMM_ADAPTER_VERSION = "deeptmhmm-runtime-contract-v1"


class LocalisationOutcome(StrEnum):
    """Normalised localisation evidence without candidate-ranking semantics."""

    MEMBRANE = "membrane"
    SURFACE = "surface"
    EXTRACELLULAR = "extracellular"
    TRANSMEMBRANE = "transmembrane"
    SOLUBLE = "soluble"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"
    FAILED = "failed"


class OfflineExecutionProvenance(ContractModel):
    """Evidence that no catalogue sequence was sent to a public service."""

    execution_mode: Literal["local_offline"] = "local_offline"
    network_access_used: Literal[False] = False
    public_sequence_submission: Literal[False] = False
    runtime_redistributed: Literal[False] = False


class PSortbRuntimeContract(ContractModel):
    """Checksum-bound standalone PSORTb 3.0.6 archaeal runtime."""

    schema_version: Literal["1.0"] = "1.0"
    tool: Literal["psortb"] = "psortb"
    tool_version: Literal["3.0.6"] = "3.0.6"
    executable_path: NonEmptyString
    executable_sha256: Sha256Hex
    organism_model: Literal["archaea"] = "archaea"
    output_format: Literal["terse"] = "terse"
    adapter_version: Literal["psortb-archaea-v1"] = _PSORTB_ADAPTER_VERSION
    runtime_identity_sha256: Sha256Hex
    provenance: OfflineExecutionProvenance = Field(
        default_factory=OfflineExecutionProvenance
    )

    @classmethod
    def from_executable(cls, executable: Path) -> Self:
        """Create a contract from an existing local executable without running it."""

        resolved = executable.resolve(strict=True)
        digest = sha256_file(resolved)
        identity = canonical_digest(
            {
                "adapter_version": _PSORTB_ADAPTER_VERSION,
                "executable_sha256": digest,
                "organism_model": "archaea",
                "output_format": "terse",
                "tool": "psortb",
                "tool_version": "3.0.6",
            }
        )
        return cls(
            executable_path=str(resolved),
            executable_sha256=digest,
            runtime_identity_sha256=identity,
        )

    @model_validator(mode="after")
    def _validate_runtime_identity(self) -> Self:
        if not Path(self.executable_path).is_absolute():
            raise ValueError("PSORTb executable path must be absolute")
        expected = canonical_digest(
            {
                "adapter_version": self.adapter_version,
                "executable_sha256": self.executable_sha256,
                "organism_model": self.organism_model,
                "output_format": self.output_format,
                "tool": self.tool,
                "tool_version": self.tool_version,
            }
        )
        if self.runtime_identity_sha256 != expected:
            raise ValueError("PSORTb runtime identity does not match its content")
        return self


class PSortbCommandRecord(ContractModel):
    """Resolved PSORTb command and all cache-relevant identities."""

    schema_version: Literal["1.0"] = "1.0"
    tool: Literal["psortb"] = "psortb"
    tool_version: Literal["3.0.6"] = "3.0.6"
    adapter_version: Literal["psortb-archaea-v1"] = _PSORTB_ADAPTER_VERSION
    runtime_identity_sha256: Sha256Hex
    sequence_group_id: NonEmptyString
    sequence_sha256: Sha256Hex
    input_fasta_path: NonEmptyString
    input_fasta_sha256: Sha256Hex
    command: tuple[NonEmptyString, ...] = Field(min_length=5)
    command_identity_sha256: Sha256Hex
    provenance: OfflineExecutionProvenance = Field(
        default_factory=OfflineExecutionProvenance
    )

    @model_validator(mode="after")
    def _validate_command_identity(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError("sequence_group_id does not match sequence_sha256")
        if self.command[1:-1] != ("-a", "-o", "terse"):
            raise ValueError("PSORTb command does not use archaeal terse semantics")
        if self.command[-1] != self.input_fasta_path:
            raise ValueError("PSORTb command input does not match input_fasta_path")
        expected = canonical_digest(
            {
                "adapter_version": self.adapter_version,
                "arguments": self.command[1:-1],
                "input_fasta_sha256": self.input_fasta_sha256,
                "runtime_identity_sha256": self.runtime_identity_sha256,
                "sequence_group_id": self.sequence_group_id,
                "sequence_sha256": self.sequence_sha256,
                "tool_version": self.tool_version,
            }
        )
        if self.command_identity_sha256 != expected:
            raise ValueError("PSORTb command identity does not match its content")
        return self


class LocalisationResult(ContractModel):
    """One terminal adapter result with retained raw-output checksums."""

    schema_version: Literal["1.0"] = "1.0"
    tool: Literal["psortb", "deeptmhmm"]
    tool_version: NonEmptyString
    runtime_identity_sha256: Sha256Hex
    sequence_group_id: NonEmptyString
    sequence_sha256: Sha256Hex
    execution_status: ExecutionStatus
    outcome: LocalisationOutcome
    raw_label: str | None = None
    score: float | None = Field(default=None, ge=0)
    raw_output_path: NonEmptyString
    raw_output_sha256: Sha256Hex
    raw_stderr_path: NonEmptyString
    raw_stderr_sha256: Sha256Hex
    command_identity_sha256: Sha256Hex
    warnings: tuple[str, ...] = ()
    provenance: OfflineExecutionProvenance = Field(
        default_factory=OfflineExecutionProvenance
    )

    @model_validator(mode="after")
    def _validate_terminal_state(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError("sequence_group_id does not match sequence_sha256")
        if self.execution_status is ExecutionStatus.COMPLETED_SUCCESS:
            if self.outcome is LocalisationOutcome.FAILED:
                raise ValueError("completed localisation cannot have failed outcome")
            if self.raw_label is None or self.score is None:
                raise ValueError("completed PSORTb result requires label and score")
        elif self.execution_status in {
            ExecutionStatus.FAILED_TOOL_EXECUTION,
            ExecutionStatus.FAILED_PARSE,
        }:
            if self.outcome is not LocalisationOutcome.FAILED:
                raise ValueError("failed execution requires failed outcome")
            if self.raw_label is not None or self.score is not None:
                raise ValueError("failed execution cannot retain parsed evidence")
        else:
            raise ValueError("localisation result requires a supported terminal status")
        return self


class DeepTMHMMRuntimeContract(ContractModel):
    """Checksum-bound user image for DeepTMHMM 1.0.

    This contract intentionally does not state an image entrypoint or arguments.
    The official DTU page does not publish a stable local CLI or output wire format.
    """

    schema_version: Literal["1.0"] = "1.0"
    tool: Literal["deeptmhmm"] = "deeptmhmm"
    tool_version: Literal["1.0"] = "1.0"
    image_path: NonEmptyString
    image_sha256: Sha256Hex
    image_supplied_by_user: Literal[True] = True
    redistribute_image: Literal[False] = False
    usage_context: Literal["academic"] = "academic"
    adapter_version: Literal["deeptmhmm-runtime-contract-v1"] = (
        _DEEPTMHMM_ADAPTER_VERSION
    )
    runtime_identity_sha256: Sha256Hex
    provenance: OfflineExecutionProvenance = Field(
        default_factory=OfflineExecutionProvenance
    )

    @classmethod
    def from_user_image(cls, image: Path) -> Self:
        """Create a contract for a locally supplied image without inspecting it."""

        resolved = image.resolve(strict=True)
        digest = sha256_file(resolved)
        identity = canonical_digest(
            {
                "adapter_version": _DEEPTMHMM_ADAPTER_VERSION,
                "image_sha256": digest,
                "tool": "deeptmhmm",
                "tool_version": "1.0",
                "usage_context": "academic",
            }
        )
        return cls(
            image_path=str(resolved),
            image_sha256=digest,
            runtime_identity_sha256=identity,
        )

    @model_validator(mode="after")
    def _validate_runtime_identity(self) -> Self:
        if not Path(self.image_path).is_absolute():
            raise ValueError("DeepTMHMM image path must be absolute")
        expected = canonical_digest(
            {
                "adapter_version": self.adapter_version,
                "image_sha256": self.image_sha256,
                "tool": self.tool,
                "tool_version": self.tool_version,
                "usage_context": self.usage_context,
            }
        )
        if self.runtime_identity_sha256 != expected:
            raise ValueError("DeepTMHMM runtime identity does not match its content")
        return self


class DeepTMHMMInvocationPlan(ContractModel):
    """Verified input/runtime plan whose executable invocation remains blocked."""

    schema_version: Literal["1.0"] = "1.0"
    tool: Literal["deeptmhmm"] = "deeptmhmm"
    tool_version: Literal["1.0"] = "1.0"
    runtime_identity_sha256: Sha256Hex
    image_sha256: Sha256Hex
    sequence_group_id: NonEmptyString
    sequence_sha256: Sha256Hex
    input_fasta_path: NonEmptyString
    input_fasta_sha256: Sha256Hex
    invocation_status: Literal["blocked_unverified_cli"] = "blocked_unverified_cli"
    command: tuple[str, ...] = ()
    block_reason: NonEmptyString
    raw_output_retention_required: Literal[True] = True
    provenance: OfflineExecutionProvenance = Field(
        default_factory=OfflineExecutionProvenance
    )

    @model_validator(mode="after")
    def _validate_blocked_plan(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError("sequence_group_id does not match sequence_sha256")
        if self.command:
            raise ValueError("blocked DeepTMHMM plan cannot contain a guessed command")
        return self


def resolve_localisation_outcome(
    outcomes: tuple[LocalisationOutcome, ...],
) -> LocalisationOutcome:
    """Resolve multiple tool outcomes without turning disagreement into exclusion."""

    informative = {
        outcome
        for outcome in outcomes
        if outcome not in {LocalisationOutcome.UNKNOWN, LocalisationOutcome.FAILED}
    }
    if not informative:
        if LocalisationOutcome.UNKNOWN in outcomes:
            return LocalisationOutcome.UNKNOWN
        return LocalisationOutcome.FAILED
    if informative <= {
        LocalisationOutcome.MEMBRANE,
        LocalisationOutcome.TRANSMEMBRANE,
    }:
        return (
            LocalisationOutcome.TRANSMEMBRANE
            if LocalisationOutcome.TRANSMEMBRANE in informative
            else LocalisationOutcome.MEMBRANE
        )
    if len(informative) == 1:
        return next(iter(informative))
    return LocalisationOutcome.CONFLICTING
