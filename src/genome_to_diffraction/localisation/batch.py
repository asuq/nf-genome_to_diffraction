"""Import one offline, catalogue-wide PSORTb/DeepTMHMM batch.

The Phase III prototype runs each database/model-heavy localisation tool once
for the complete frozen catalogue.  This importer never executes a container
and never sends a sequence to a service.  It validates complete source-record
coverage, collapses exact duplicate sequences only when their predictions are
identical, binds the pinned image manifests and raw bytes, and emits one typed
record per sequence-equivalence group.  Its runtime contract accepts only
Docker network mode ``none``; bridge-network diagnostic output is not run
authority.

PSORTb uses the official Brinkman Lab command-line image containing PSORTb
3.0.6.  DeepTMHMM uses the project image at one immutable manifest digest.
DeepTMHMM ``TM``, ``SP+TM``, and ``BETA`` calls are transmembrane evidence;
``GLOB`` is soluble; ``SP`` alone is neutral because a signal peptide is not a
compartment call.  Conflicting tools remain neutral.  An empty gel manifest is
retained as neutral evidence.  Missing, duplicate, malformed, or changed
coverage fails closed.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self, cast

from pydantic import Field, model_validator

from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.localisation.container_execution import (
    DEEPTMHMM_IMAGE_MANIFEST_SHA256,
    DEEPTMHMM_IMAGE_REFERENCE,
    LOCALISATION_BATCH_ADAPTER_VERSION,
    PSORTB_IMAGE_MANIFEST_SHA256,
    PSORTB_IMAGE_REFERENCE,
    LocalisationContainerToolExecution,
    validate_localisation_container_execution,
)
from genome_to_diffraction.localisation.contracts import (
    LocalisationOutcome,
    OfflineExecutionProvenance,
    resolve_localisation_outcome,
)
from genome_to_diffraction.localisation.policy import (
    FirstWaveDisposition,
    first_wave_disposition,
)
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    Sha256Hex,
)
from genome_to_diffraction.schemas.manifests import GelEvidenceManifest
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.status import InputContractError, ResultParseError

_ADAPTER_VERSION = LOCALISATION_BATCH_ADAPTER_VERSION
_DEEPTMHMM_TYPE = re.compile(r"^>(\S+) \| (TM|SP\+TM|SP|GLOB|BETA)$")
type DeepTMHMMType = Literal["TM", "SP+TM", "SP", "GLOB", "BETA"]


class LocalisationBatchImportError(InputContractError):
    """A frozen raw localisation batch is incomplete or inconsistent."""


class ContainerRuntimeEvidence(ContractModel):
    """Immutable local container identity used to create raw evidence."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["container-localisation-batch-v3-inspected"] = (
        _ADAPTER_VERSION
    )
    runtime_id: NonEmptyString
    container_execution_id: NonEmptyString
    container_id: Sha256Hex
    tool: Literal["psortb", "deeptmhmm"]
    tool_version: NonEmptyString
    image_reference: NonEmptyString
    image_manifest_sha256: Sha256Hex
    image_id: NonEmptyString
    platform: Literal["linux/amd64"] = "linux/amd64"
    execution_backend: Literal["docker_local_offline"] = "docker_local_offline"
    network_mode: Literal["none"] = "none"
    container_engine_version: NonEmptyString
    container_inspect_sha256: Sha256Hex
    image_inspect_sha256: Sha256Hex
    log_sha256: Sha256Hex
    command: tuple[NonEmptyString, ...] = Field(min_length=3)
    license_or_usage: NonEmptyString
    provenance: OfflineExecutionProvenance = Field(
        default_factory=OfflineExecutionProvenance
    )

    @classmethod
    def from_execution(
        cls,
        *,
        execution: LocalisationContainerToolExecution,
    ) -> Self:
        """Bind one independently validated Docker execution."""

        if execution.tool == "psortb":
            version = "3.0.6"
            reference = PSORTB_IMAGE_REFERENCE
            digest = PSORTB_IMAGE_MANIFEST_SHA256
            usage = "GNU GPL v3; Brinkman Lab PSORTb command-line image"
        else:
            version = "1.0"
            reference = DEEPTMHMM_IMAGE_REFERENCE
            digest = DEEPTMHMM_IMAGE_MANIFEST_SHA256
            usage = "academic local use; image is checksum-bound and not redistributed"
        payload = {
            "adapter_version": _ADAPTER_VERSION,
            "command": execution.effective_command,
            "container_engine_version": execution.docker_engine_version,
            "container_execution_id": execution.execution_id,
            "container_id": execution.container_id,
            "container_inspect_sha256": execution.container_inspect_sha256,
            "execution_backend": "docker_local_offline",
            "image_manifest_sha256": digest,
            "image_reference": reference,
            "image_id": execution.image_id,
            "image_inspect_sha256": execution.image_inspect_sha256,
            "license_or_usage": usage,
            "log_sha256": execution.log_sha256,
            "network_mode": "none",
            "platform": "linux/amd64",
            "tool": execution.tool,
            "tool_version": version,
        }
        return cls(
            runtime_id=content_id("localruntime_", payload),
            container_execution_id=execution.execution_id,
            container_id=execution.container_id,
            tool=execution.tool,
            tool_version=version,
            image_reference=reference,
            image_manifest_sha256=digest,
            image_id=execution.image_id,
            container_engine_version=execution.docker_engine_version,
            container_inspect_sha256=execution.container_inspect_sha256,
            image_inspect_sha256=execution.image_inspect_sha256,
            log_sha256=execution.log_sha256,
            command=execution.effective_command,
            license_or_usage=usage,
            network_mode="none",
        )

    @model_validator(mode="after")
    def _validate_runtime(self) -> Self:
        if self.tool == "psortb":
            expected_version = "3.0.6"
            expected_reference = PSORTB_IMAGE_REFERENCE
            expected_digest = PSORTB_IMAGE_MANIFEST_SHA256
            expected_usage = "GNU GPL v3; Brinkman Lab PSORTb command-line image"
        else:
            expected_version = "1.0"
            expected_reference = DEEPTMHMM_IMAGE_REFERENCE
            expected_digest = DEEPTMHMM_IMAGE_MANIFEST_SHA256
            expected_usage = (
                "academic local use; image is checksum-bound and not redistributed"
            )
        payload = {
            "adapter_version": self.adapter_version,
            "command": self.command,
            "container_engine_version": self.container_engine_version,
            "container_execution_id": self.container_execution_id,
            "container_id": self.container_id,
            "container_inspect_sha256": self.container_inspect_sha256,
            "execution_backend": self.execution_backend,
            "image_manifest_sha256": self.image_manifest_sha256,
            "image_reference": self.image_reference,
            "image_id": self.image_id,
            "image_inspect_sha256": self.image_inspect_sha256,
            "license_or_usage": self.license_or_usage,
            "log_sha256": self.log_sha256,
            "network_mode": self.network_mode,
            "platform": self.platform,
            "tool": self.tool,
            "tool_version": self.tool_version,
        }
        if (
            self.tool_version != expected_version
            or self.image_reference != expected_reference
            or self.image_manifest_sha256 != expected_digest
            or self.license_or_usage != expected_usage
            or self.runtime_id != content_id("localruntime_", payload)
        ):
            raise ValueError("localisation runtime differs from the fixed image")
        return self


def _evidence_payload(
    *,
    sequence_group_id: str,
    sequence_sha256: str,
    source_record_ids: tuple[str, ...],
    psortb_raw_label: str | None,
    psortb_score: float | None,
    psortb_outcome: LocalisationOutcome,
    deeptmhmm_type: str | None,
    deeptmhmm_topology_sha256: str | None,
    deeptmhmm_tmr_count: int | None,
    deeptmhmm_outcome: LocalisationOutcome,
    merged_outcome: LocalisationOutcome,
    disposition: FirstWaveDisposition,
    eligible: bool,
    warnings: tuple[str, ...],
) -> dict[str, object]:
    return {
        "adapter_version": _ADAPTER_VERSION,
        "deeptmhmm_outcome": deeptmhmm_outcome,
        "deeptmhmm_tmr_count": deeptmhmm_tmr_count,
        "deeptmhmm_topology_sha256": deeptmhmm_topology_sha256,
        "deeptmhmm_type": deeptmhmm_type,
        "first_wave_disposition": disposition,
        "first_wave_eligible": eligible,
        "merged_outcome": merged_outcome,
        "psortb_outcome": psortb_outcome,
        "psortb_raw_label": psortb_raw_label,
        "psortb_score": psortb_score,
        "sequence_group_id": sequence_group_id,
        "sequence_sha256": sequence_sha256,
        "source_record_ids": source_record_ids,
        "warnings": warnings,
    }


class BatchLocalisationGroupEvidence(ContractModel):
    """One exact-sequence result collapsed from complete source records."""

    schema_version: Literal["2.0"] = "2.0"
    adapter_version: Literal["container-localisation-batch-v3-inspected"] = (
        _ADAPTER_VERSION
    )
    evidence_id: NonEmptyString
    sequence_group_id: NonEmptyString
    sequence_sha256: Sha256Hex
    source_record_ids: tuple[NonEmptyString, ...] = Field(min_length=1)
    psortb_raw_label: NonEmptyString | None = None
    psortb_score: float | None = Field(default=None, ge=0)
    psortb_outcome: LocalisationOutcome
    deeptmhmm_type: DeepTMHMMType | None = None
    deeptmhmm_topology_sha256: Sha256Hex | None = None
    deeptmhmm_tmr_count: int | None = Field(default=None, ge=0)
    deeptmhmm_outcome: LocalisationOutcome
    merged_outcome: LocalisationOutcome
    first_wave_disposition: FirstWaveDisposition
    first_wave_eligible: bool
    warnings: tuple[str, ...] = ()

    @classmethod
    def from_predictions(
        cls,
        *,
        group: SequenceGroupRecord,
        source_record_ids: Sequence[str],
        psortb_raw_label: str | None,
        psortb_score: float | None,
        psortb_outcome: LocalisationOutcome,
        deeptmhmm_type: DeepTMHMMType | None,
        topology: str | None,
    ) -> Self:
        """Derive conservative merged evidence from two parsed tool calls."""

        deep_outcomes = {
            "TM": LocalisationOutcome.TRANSMEMBRANE,
            "SP+TM": LocalisationOutcome.TRANSMEMBRANE,
            "BETA": LocalisationOutcome.TRANSMEMBRANE,
            "GLOB": LocalisationOutcome.SOLUBLE,
            "SP": LocalisationOutcome.UNKNOWN,
        }
        deep_outcome = (
            LocalisationOutcome.FAILED
            if deeptmhmm_type is None
            else deep_outcomes[deeptmhmm_type]
        )
        merged = resolve_localisation_outcome((psortb_outcome, deep_outcome))
        disposition = first_wave_disposition(merged)
        eligible = disposition is not FirstWaveDisposition.EXCLUDED
        warnings = tuple(
            warning
            for warning, present in (
                (
                    "deeptmhmm_signal_peptide_is_not_a_compartment_call",
                    deeptmhmm_type == "SP",
                ),
                (
                    "psortb_replaced_selenocysteine_with_x",
                    "U" in group.sequence,
                ),
                (
                    "psortb_sequence_local_failure",
                    psortb_outcome is LocalisationOutcome.FAILED,
                ),
                (
                    "deeptmhmm_sequence_local_failure",
                    deep_outcome is LocalisationOutcome.FAILED,
                ),
            )
            if present
        )
        ordered_sources = tuple(sorted(source_record_ids))
        topology_sha256 = (
            hashlib.sha256(topology.encode("ascii")).hexdigest()
            if topology is not None
            else None
        )
        tmr_count = _tmr_count(topology) if topology is not None else None
        payload = _evidence_payload(
            sequence_group_id=group.sequence_group_id,
            sequence_sha256=group.sha256,
            source_record_ids=ordered_sources,
            psortb_raw_label=psortb_raw_label,
            psortb_score=psortb_score,
            psortb_outcome=psortb_outcome,
            deeptmhmm_type=deeptmhmm_type,
            deeptmhmm_topology_sha256=topology_sha256,
            deeptmhmm_tmr_count=tmr_count,
            deeptmhmm_outcome=deep_outcome,
            merged_outcome=merged,
            disposition=disposition,
            eligible=eligible,
            warnings=warnings,
        )
        return cls(
            evidence_id=content_id("batchlocalevidence_", payload),
            sequence_group_id=group.sequence_group_id,
            sequence_sha256=group.sha256,
            source_record_ids=ordered_sources,
            psortb_raw_label=psortb_raw_label,
            psortb_score=psortb_score,
            psortb_outcome=psortb_outcome,
            deeptmhmm_type=deeptmhmm_type,
            deeptmhmm_topology_sha256=topology_sha256,
            deeptmhmm_tmr_count=tmr_count,
            deeptmhmm_outcome=deep_outcome,
            merged_outcome=merged,
            first_wave_disposition=disposition,
            first_wave_eligible=eligible,
            warnings=warnings,
        )

    @model_validator(mode="after")
    def _validate_evidence(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError("batch localisation sequence identity differs")
        if self.source_record_ids != tuple(sorted(self.source_record_ids)) or len(
            set(self.source_record_ids)
        ) != len(self.source_record_ids):
            raise ValueError("batch localisation source IDs are not canonical")
        if (self.psortb_outcome is LocalisationOutcome.FAILED) != (
            self.psortb_raw_label is None and self.psortb_score is None
        ):
            raise ValueError("PSORTb failure fields are inconsistent")
        if (self.deeptmhmm_outcome is LocalisationOutcome.FAILED) != (
            self.deeptmhmm_type is None
            and self.deeptmhmm_topology_sha256 is None
            and self.deeptmhmm_tmr_count is None
        ):
            raise ValueError("DeepTMHMM failure fields are inconsistent")
        expected_merged = resolve_localisation_outcome(
            (self.psortb_outcome, self.deeptmhmm_outcome)
        )
        if self.merged_outcome is not expected_merged:
            raise ValueError("batch localisation merged outcome differs")
        expected_disposition = first_wave_disposition(expected_merged)
        if self.first_wave_disposition is not expected_disposition or (
            self.first_wave_eligible
            != (expected_disposition is not FirstWaveDisposition.EXCLUDED)
        ):
            raise ValueError("batch localisation wave disposition differs")
        expected = content_id(
            "batchlocalevidence_",
            _evidence_payload(
                sequence_group_id=self.sequence_group_id,
                sequence_sha256=self.sequence_sha256,
                source_record_ids=self.source_record_ids,
                psortb_raw_label=self.psortb_raw_label,
                psortb_score=self.psortb_score,
                psortb_outcome=self.psortb_outcome,
                deeptmhmm_type=self.deeptmhmm_type,
                deeptmhmm_topology_sha256=self.deeptmhmm_topology_sha256,
                deeptmhmm_tmr_count=self.deeptmhmm_tmr_count,
                deeptmhmm_outcome=self.deeptmhmm_outcome,
                merged_outcome=self.merged_outcome,
                disposition=self.first_wave_disposition,
                eligible=self.first_wave_eligible,
                warnings=self.warnings,
            ),
        )
        if self.evidence_id != expected:
            raise ValueError("batch localisation evidence identity differs")
        return self


class BatchLocalisationPolicy(ContractModel):
    """Complete Phase III first-wave policy from two local batch tools."""

    schema_version: Literal["2.0"] = "2.0"
    adapter_version: Literal["container-localisation-batch-v3-inspected"] = (
        _ADAPTER_VERSION
    )
    policy_id: NonEmptyString
    psortb_runtime: ContainerRuntimeEvidence
    deeptmhmm_runtime: ContainerRuntimeEvidence
    sequence_groups_sha256: Sha256Hex
    source_records_sha256: Sha256Hex
    psortb_raw_sha256: Sha256Hex
    deeptmhmm_raw_sha256: Sha256Hex
    source_fasta_sha256: Sha256Hex
    container_execution_manifest_id: NonEmptyString
    container_execution_manifest_sha256: Sha256Hex
    gel_evidence_sha256: Sha256Hex
    gel_observation_count: int = Field(ge=0)
    sequence_group_count: int = Field(ge=0)
    source_record_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    neutral_count: int = Field(ge=0)
    conflicting_count: int = Field(ge=0)
    first_wave_group_ids: tuple[NonEmptyString, ...]
    retained_excluded_group_ids: tuple[NonEmptyString, ...]
    group_evidence: tuple[BatchLocalisationGroupEvidence, ...]
    provenance: OfflineExecutionProvenance = Field(
        default_factory=OfflineExecutionProvenance
    )

    @model_validator(mode="after")
    def _validate_policy(self) -> Self:
        ordered = tuple(
            sorted(self.group_evidence, key=lambda row: row.sequence_group_id)
        )
        if self.group_evidence != ordered:
            raise ValueError("batch localisation evidence is not ordered")
        active = tuple(
            row.sequence_group_id
            for row in ordered
            if row.first_wave_disposition is FirstWaveDisposition.ACTIVE
        )
        excluded = tuple(
            row.sequence_group_id
            for row in ordered
            if row.first_wave_disposition is FirstWaveDisposition.EXCLUDED
        )
        neutral = tuple(
            row.sequence_group_id
            for row in ordered
            if row.first_wave_disposition is FirstWaveDisposition.NEUTRAL
        )
        conflicting = sum(
            row.merged_outcome is LocalisationOutcome.CONFLICTING for row in ordered
        )
        if (
            self.sequence_group_count != len(ordered)
            or self.active_count != len(active)
            or self.excluded_count != len(excluded)
            or self.neutral_count != len(neutral)
            or self.conflicting_count != conflicting
            or self.first_wave_group_ids != active + neutral
            or self.retained_excluded_group_ids != excluded
        ):
            raise ValueError("batch localisation policy counts differ")
        payload = self.model_dump(
            mode="json",
            exclude={"policy_id"},
        )
        if self.policy_id != content_id("batchlocalpolicy_", payload):
            raise ValueError("batch localisation policy identity differs")
        return self


@dataclass(frozen=True, slots=True)
class BatchLocalisationImportRequest:
    """Frozen raw bytes and catalogue identities for one import."""

    sequence_groups_jsonl: Path
    source_records_jsonl: Path
    catalogue_fasta: Path
    psortb_terse: Path
    deeptmhmm_topologies: Path
    gel_evidence: Path
    container_execution_bundle: Path
    output_directory: Path


@dataclass(frozen=True, slots=True)
class BatchLocalisationImportOutput:
    """Published policy, evidence, runtime records, and raw manifest."""

    policy: BatchLocalisationPolicy
    policy_json: Path
    evidence_jsonl: Path
    manifest_json: Path
    output_directory: Path


_BUNDLE_FILES = frozenset(
    {
        "excluded_sequence_group_ids.txt",
        "first_wave_policy.json",
        "first_wave_sequence_group_ids.txt",
        "gel-evidence.json",
        "group_localisation_evidence.jsonl",
        "localisation_batch_manifest.json",
        "container_execution/deeptmhmm-container.log",
        "container_execution/localisation_container_execution.json",
        "container_execution/psortb-container.log",
        "raw/deeptmhmm-topologies.3line",
        "raw/psortb-terse.tsv",
    }
)


def _read_jsonl[T: ContractModel](
    path: Path, model: type[T], *, label: str
) -> tuple[T, ...]:
    try:
        lines = path.resolve(strict=True).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise LocalisationBatchImportError(f"cannot read {label}") from error
    records: list[T] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(model.model_validate_json(line))
        except ValueError as error:
            raise LocalisationBatchImportError(
                f"invalid {label} at line {line_number}"
            ) from error
    if not records:
        raise LocalisationBatchImportError(f"{label} is empty")
    return tuple(records)


def _psortb_outcome(raw_label: str) -> LocalisationOutcome:
    normalised = re.sub(r"[ _-]", "", raw_label).lower()
    outcomes = {
        "cytoplasmicmembrane": LocalisationOutcome.MEMBRANE,
        "cellwall": LocalisationOutcome.SURFACE,
        "extracellular": LocalisationOutcome.EXTRACELLULAR,
        "cytoplasmic": LocalisationOutcome.SOLUBLE,
        "unknown": LocalisationOutcome.UNKNOWN,
    }
    try:
        return outcomes[normalised]
    except KeyError as error:
        raise ResultParseError(
            f"unsupported PSORTb archaeal localisation label: {raw_label!r}"
        ) from error


def _parse_psortb(path: Path) -> dict[str, tuple[str, float, LocalisationOutcome]]:
    try:
        lines = path.resolve(strict=True).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise LocalisationBatchImportError("cannot read PSORTb batch") from error
    if not lines or lines[0] != "SeqID\tLocalization\tScore":
        raise LocalisationBatchImportError("PSORTb batch header differs")
    results: dict[str, tuple[str, float, LocalisationOutcome]] = {}
    for line_number, line in enumerate(lines[1:], start=2):
        fields = line.split("\t")
        if len(fields) != 3:
            raise LocalisationBatchImportError(
                f"PSORTb row {line_number} does not have three fields"
            )
        source_id = fields[0].strip()
        raw_label = fields[1].strip()
        try:
            score = float(fields[2])
        except ValueError as error:
            raise LocalisationBatchImportError(
                f"PSORTb row {line_number} score is not numeric"
            ) from error
        if (
            not source_id
            or source_id in results
            or not math.isfinite(score)
            or score < 0
        ):
            raise LocalisationBatchImportError(
                f"PSORTb row {line_number} is invalid or duplicated"
            )
        results[source_id] = (raw_label, score, _psortb_outcome(raw_label))
    return results


def _parse_deeptmhmm(path: Path) -> dict[str, tuple[DeepTMHMMType, str, str]]:
    try:
        lines = path.resolve(strict=True).read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as error:
        raise LocalisationBatchImportError("cannot read DeepTMHMM batch") from error
    if not lines or len(lines) % 3 != 0:
        raise LocalisationBatchImportError("DeepTMHMM 3-line batch is truncated")
    results: dict[str, tuple[DeepTMHMMType, str, str]] = {}
    for index in range(0, len(lines), 3):
        match = _DEEPTMHMM_TYPE.fullmatch(lines[index])
        sequence = lines[index + 1]
        topology = lines[index + 2]
        if (
            match is None
            or match.group(1) in results
            or not sequence
            or sequence != sequence.upper()
            or len(topology) != len(sequence)
            or not topology.isalpha()
            or not set(topology) <= {"I", "O", "M", "S", "B"}
        ):
            raise LocalisationBatchImportError(
                f"DeepTMHMM record {index // 3 + 1} is invalid"
            )
        results[match.group(1)] = (
            cast(DeepTMHMMType, match.group(2)),
            sequence,
            topology,
        )
    return results


def _tmr_count(topology: str) -> int:
    count = 0
    in_region = False
    for label in topology:
        current = label in {"M", "B"}
        if current and not in_region:
            count += 1
        in_region = current
    return count


def import_catalogue_localisation_batch(
    request: BatchLocalisationImportRequest,
) -> BatchLocalisationImportOutput:
    """Validate two complete raw batches and publish a portable policy."""

    groups = _read_jsonl(
        request.sequence_groups_jsonl,
        SequenceGroupRecord,
        label="sequence-group input",
    )
    sources = _read_jsonl(
        request.source_records_jsonl,
        SourceProteinRecord,
        label="source-record input",
    )
    try:
        execution = validate_localisation_container_execution(
            request.container_execution_bundle
        )
    except InputContractError as error:
        raise LocalisationBatchImportError(
            f"container execution evidence is invalid: {error}"
        ) from error
    if (
        sha256_file(request.catalogue_fasta) != execution.source_fasta_sha256
        or request.catalogue_fasta.stat().st_size != execution.source_fasta_size_bytes
        or sha256_file(request.psortb_terse) != execution.psortb.raw_output_sha256
        or request.psortb_terse.stat().st_size != execution.psortb.raw_output_size_bytes
        or sha256_file(request.deeptmhmm_topologies)
        != execution.deeptmhmm.raw_output_sha256
        or request.deeptmhmm_topologies.stat().st_size
        != execution.deeptmhmm.raw_output_size_bytes
    ):
        raise LocalisationBatchImportError(
            "container execution inputs or outputs differ"
        )
    group_by_id = {group.sequence_group_id: group for group in groups}
    if len(group_by_id) != len(groups):
        raise LocalisationBatchImportError("duplicate sequence-group ID")
    source_by_protein: dict[str, list[SourceProteinRecord]] = {}
    source_by_header: dict[str, list[SourceProteinRecord]] = {}
    for source in sources:
        source_by_protein.setdefault(source.original_protein_id, []).append(source)
        source_by_header.setdefault(source.original_header, []).append(source)
    if any(
        len({row.original_header for row in rows}) != 1
        or len({row.sequence_group_id for row in rows}) != 1
        for rows in source_by_protein.values()
    ):
        raise LocalisationBatchImportError(
            "one original protein ID maps to different FASTA content"
        )
    if any(
        len({row.original_protein_id for row in rows}) != 1
        or len({row.sequence_group_id for row in rows}) != 1
        for rows in source_by_header.values()
    ):
        raise LocalisationBatchImportError(
            "one original FASTA header maps to different source content"
        )
    source_groups: dict[str, list[SourceProteinRecord]] = {}
    for source in sources:
        if source.sequence_group_id not in group_by_id:
            raise LocalisationBatchImportError("source record maps to unknown group")
        source_groups.setdefault(source.sequence_group_id, []).append(source)
    if set(source_groups) != set(group_by_id) or any(
        len(source_groups[group.sequence_group_id]) != group.source_record_count
        for group in groups
    ):
        raise LocalisationBatchImportError("source/group coverage differs")
    psortb = _parse_psortb(request.psortb_terse)
    deeptmhmm = _parse_deeptmhmm(request.deeptmhmm_topologies)
    psortb_failed = set(execution.psortb.explicit_failed_source_ids)
    deeptmhmm_failed = set(execution.deeptmhmm.explicit_failed_source_ids)
    expected_protein_ids = set(source_by_protein)
    if (
        not psortb_failed <= expected_protein_ids
        or not deeptmhmm_failed <= expected_protein_ids
    ):
        raise LocalisationBatchImportError(
            "localisation failure status contains an unknown source"
        )
    expected_psortb_headers = {
        rows[0].original_header
        for protein_id, rows in source_by_protein.items()
        if protein_id not in psortb_failed
    }
    if set(psortb) != expected_psortb_headers or set(deeptmhmm) != (
        expected_protein_ids - deeptmhmm_failed
    ):
        raise LocalisationBatchImportError("localisation source coverage differs")
    evidence: list[BatchLocalisationGroupEvidence] = []
    for group in sorted(groups, key=lambda row: row.sequence_group_id):
        group_sources = sorted(
            source_groups[group.sequence_group_id],
            key=lambda row: row.source_record_id,
        )
        protein_ids = tuple(row.original_protein_id for row in group_sources)
        psortb_rows = {
            None
            if row.original_protein_id in psortb_failed
            else psortb[row.original_header]
            for row in group_sources
        }
        deep_rows = {
            None if protein_id in deeptmhmm_failed else deeptmhmm[protein_id]
            for protein_id in protein_ids
        }
        if len(psortb_rows) != 1 or len(deep_rows) != 1:
            raise LocalisationBatchImportError(
                "duplicate exact sequences received different predictions"
            )
        psortb_row = next(iter(psortb_rows))
        deep_row = next(iter(deep_rows))
        psortb_label, psortb_score, psortb_outcome = (
            (None, None, LocalisationOutcome.FAILED)
            if psortb_row is None
            else psortb_row
        )
        deep_type, deep_sequence, topology = (
            (None, None, None) if deep_row is None else deep_row
        )
        if deep_sequence is not None and deep_sequence != group.sequence:
            raise LocalisationBatchImportError(
                "DeepTMHMM sequence differs from catalogue group"
            )
        evidence.append(
            BatchLocalisationGroupEvidence.from_predictions(
                group=group,
                source_record_ids=tuple(row.source_record_id for row in group_sources),
                psortb_raw_label=psortb_label,
                psortb_score=psortb_score,
                psortb_outcome=psortb_outcome,
                deeptmhmm_type=deep_type,
                topology=topology,
            )
        )
    try:
        gel = GelEvidenceManifest.model_validate_json(
            request.gel_evidence.resolve(strict=True).read_bytes()
        )
    except (OSError, ValueError) as error:
        raise LocalisationBatchImportError("gel evidence is invalid") from error
    psortb_runtime = ContainerRuntimeEvidence.from_execution(
        execution=execution.psortb,
    )
    deep_runtime = ContainerRuntimeEvidence.from_execution(
        execution=execution.deeptmhmm,
    )
    ordered = tuple(evidence)
    active = tuple(
        row.sequence_group_id
        for row in ordered
        if row.first_wave_disposition is FirstWaveDisposition.ACTIVE
    )
    excluded = tuple(
        row.sequence_group_id
        for row in ordered
        if row.first_wave_disposition is FirstWaveDisposition.EXCLUDED
    )
    neutral = tuple(
        row.sequence_group_id
        for row in ordered
        if row.first_wave_disposition is FirstWaveDisposition.NEUTRAL
    )
    policy_values: dict[str, object] = {
        "schema_version": "2.0",
        "adapter_version": _ADAPTER_VERSION,
        "psortb_runtime": psortb_runtime,
        "deeptmhmm_runtime": deep_runtime,
        "sequence_groups_sha256": sha256_file(request.sequence_groups_jsonl),
        "source_records_sha256": sha256_file(request.source_records_jsonl),
        "psortb_raw_sha256": sha256_file(request.psortb_terse),
        "deeptmhmm_raw_sha256": sha256_file(request.deeptmhmm_topologies),
        "source_fasta_sha256": execution.source_fasta_sha256,
        "container_execution_manifest_id": execution.manifest_id,
        "container_execution_manifest_sha256": sha256_file(
            request.container_execution_bundle / "localisation_container_execution.json"
        ),
        "gel_evidence_sha256": sha256_file(request.gel_evidence),
        "gel_observation_count": len(gel.observations),
        "sequence_group_count": len(ordered),
        "source_record_count": len(sources),
        "active_count": len(active),
        "excluded_count": len(excluded),
        "neutral_count": len(neutral),
        "conflicting_count": sum(
            row.merged_outcome is LocalisationOutcome.CONFLICTING for row in ordered
        ),
        "first_wave_group_ids": active + neutral,
        "retained_excluded_group_ids": excluded,
        "group_evidence": ordered,
        "provenance": OfflineExecutionProvenance(),
    }
    policy = BatchLocalisationPolicy.model_validate(
        {
            **policy_values,
            "policy_id": content_id("batchlocalpolicy_", policy_values),
        }
    )
    output = request.output_directory.absolute()
    if output.exists() or output.is_symlink():
        raise LocalisationBatchImportError("localisation batch output already exists")
    output.mkdir(parents=True)
    raw = output / "raw"
    raw.mkdir()
    shutil.copytree(
        request.container_execution_bundle.resolve(strict=True),
        output / "container_execution",
    )
    atomic_write_bytes(raw / "psortb-terse.tsv", request.psortb_terse.read_bytes())
    atomic_write_bytes(
        raw / "deeptmhmm-topologies.3line",
        request.deeptmhmm_topologies.read_bytes(),
    )
    atomic_write_bytes(output / "gel-evidence.json", request.gel_evidence.read_bytes())
    policy_json = output / "first_wave_policy.json"
    evidence_jsonl = output / "group_localisation_evidence.jsonl"
    atomic_write_json(policy_json, policy.model_dump(mode="json"))
    atomic_write_text(
        evidence_jsonl,
        "".join(f"{canonical_json_text(row)}\n" for row in ordered),
    )
    atomic_write_text(
        output / "first_wave_sequence_group_ids.txt",
        "".join(f"{group_id}\n" for group_id in policy.first_wave_group_ids),
    )
    atomic_write_text(
        output / "excluded_sequence_group_ids.txt",
        "".join(f"{group_id}\n" for group_id in policy.retained_excluded_group_ids),
    )
    manifest_values = {
        "schema_version": "1.0",
        "adapter_version": _ADAPTER_VERSION,
        "policy_id": policy.policy_id,
        "policy_sha256": sha256_file(policy_json),
        "evidence_sha256": sha256_file(evidence_jsonl),
        "psortb_raw_sha256": policy.psortb_raw_sha256,
        "deeptmhmm_raw_sha256": policy.deeptmhmm_raw_sha256,
        "source_fasta_sha256": policy.source_fasta_sha256,
        "container_execution_manifest_id": policy.container_execution_manifest_id,
        "container_execution_manifest_sha256": (
            policy.container_execution_manifest_sha256
        ),
        "gel_evidence_sha256": policy.gel_evidence_sha256,
        "sequence_group_count": policy.sequence_group_count,
        "source_record_count": policy.source_record_count,
        "psortb_runtime_id": psortb_runtime.runtime_id,
        "deeptmhmm_runtime_id": deep_runtime.runtime_id,
    }
    manifest_json = output / "localisation_batch_manifest.json"
    atomic_write_json(
        manifest_json,
        {
            **manifest_values,
            "manifest_id": content_id("localbatchmanifest_", manifest_values),
        },
    )
    return BatchLocalisationImportOutput(
        policy=policy,
        policy_json=policy_json,
        evidence_jsonl=evidence_jsonl,
        manifest_json=manifest_json,
        output_directory=output,
    )


def validate_catalogue_localisation_batch(
    bundle_directory: Path,
) -> BatchLocalisationPolicy:
    """Revalidate a portable batch without trusting its manifest claims."""

    if bundle_directory.is_symlink():
        raise LocalisationBatchImportError("localisation bundle is unsafe")
    try:
        root = bundle_directory.resolve(strict=True)
    except OSError as error:
        raise LocalisationBatchImportError("localisation bundle is absent") from error
    if root.is_symlink() or not root.is_dir():
        raise LocalisationBatchImportError("localisation bundle is unsafe")
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.is_symlink() or not path.is_file():
            raise LocalisationBatchImportError(
                "localisation bundle contains an unsafe member"
            )
        files[path.relative_to(root).as_posix()] = path
    if frozenset(files) != _BUNDLE_FILES:
        raise LocalisationBatchImportError("localisation bundle layout differs")
    try:
        policy = BatchLocalisationPolicy.model_validate_json(
            files["first_wave_policy.json"].read_bytes()
        )
        evidence = tuple(
            BatchLocalisationGroupEvidence.model_validate_json(line)
            for line in files["group_localisation_evidence.jsonl"]
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
        gel = GelEvidenceManifest.model_validate_json(
            files["gel-evidence.json"].read_bytes()
        )
        manifest = json.loads(
            files["localisation_batch_manifest.json"].read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise LocalisationBatchImportError(
            "localisation bundle contract is invalid"
        ) from error
    try:
        execution = validate_localisation_container_execution(
            root / "container_execution"
        )
    except InputContractError as error:
        raise LocalisationBatchImportError(
            "localisation container execution changed"
        ) from error
    if evidence != policy.group_evidence:
        raise LocalisationBatchImportError("localisation evidence differs from policy")
    expected_first = "".join(f"{value}\n" for value in policy.first_wave_group_ids)
    expected_excluded = "".join(
        f"{value}\n" for value in policy.retained_excluded_group_ids
    )
    if (
        files["first_wave_sequence_group_ids.txt"].read_text(encoding="ascii")
        != expected_first
        or files["excluded_sequence_group_ids.txt"].read_text(encoding="ascii")
        != expected_excluded
        or sha256_file(files["raw/psortb-terse.tsv"]) != policy.psortb_raw_sha256
        or sha256_file(files["raw/deeptmhmm-topologies.3line"])
        != policy.deeptmhmm_raw_sha256
        or sha256_file(files["gel-evidence.json"]) != policy.gel_evidence_sha256
        or len(gel.observations) != policy.gel_observation_count
        or execution.manifest_id != policy.container_execution_manifest_id
        or sha256_file(
            files["container_execution/localisation_container_execution.json"]
        )
        != policy.container_execution_manifest_sha256
        or execution.psortb.raw_output_sha256 != policy.psortb_raw_sha256
        or execution.deeptmhmm.raw_output_sha256 != policy.deeptmhmm_raw_sha256
        or ContainerRuntimeEvidence.from_execution(execution=execution.psortb)
        != policy.psortb_runtime
        or ContainerRuntimeEvidence.from_execution(execution=execution.deeptmhmm)
        != policy.deeptmhmm_runtime
    ):
        raise LocalisationBatchImportError("localisation bundle evidence changed")
    manifest_values = {
        "schema_version": "1.0",
        "adapter_version": _ADAPTER_VERSION,
        "policy_id": policy.policy_id,
        "policy_sha256": sha256_file(files["first_wave_policy.json"]),
        "evidence_sha256": sha256_file(files["group_localisation_evidence.jsonl"]),
        "psortb_raw_sha256": policy.psortb_raw_sha256,
        "deeptmhmm_raw_sha256": policy.deeptmhmm_raw_sha256,
        "source_fasta_sha256": policy.source_fasta_sha256,
        "container_execution_manifest_id": policy.container_execution_manifest_id,
        "container_execution_manifest_sha256": (
            policy.container_execution_manifest_sha256
        ),
        "gel_evidence_sha256": policy.gel_evidence_sha256,
        "sequence_group_count": policy.sequence_group_count,
        "source_record_count": policy.source_record_count,
        "psortb_runtime_id": policy.psortb_runtime.runtime_id,
        "deeptmhmm_runtime_id": policy.deeptmhmm_runtime.runtime_id,
    }
    if manifest != {
        **manifest_values,
        "manifest_id": content_id("localbatchmanifest_", manifest_values),
    }:
        raise LocalisationBatchImportError("localisation batch manifest differs")
    return policy


def stage_catalogue_localisation_batch(
    bundle_directory: Path,
    output_directory: Path,
) -> BatchLocalisationPolicy:
    """Validate, copy, and independently revalidate one portable bundle."""

    policy = validate_catalogue_localisation_batch(bundle_directory)
    output = output_directory.absolute()
    if output.exists() or output.is_symlink():
        raise LocalisationBatchImportError("staged localisation output exists")
    try:
        shutil.copytree(bundle_directory.resolve(strict=True), output)
    except OSError as error:
        raise LocalisationBatchImportError(
            "cannot stage localisation bundle"
        ) from error
    staged = validate_catalogue_localisation_batch(output)
    if staged != policy:
        raise LocalisationBatchImportError("staged localisation policy differs")
    return staged


__all__ = [
    "DEEPTMHMM_IMAGE_MANIFEST_SHA256",
    "DEEPTMHMM_IMAGE_REFERENCE",
    "LOCALISATION_BATCH_ADAPTER_VERSION",
    "PSORTB_IMAGE_MANIFEST_SHA256",
    "PSORTB_IMAGE_REFERENCE",
    "BatchLocalisationGroupEvidence",
    "BatchLocalisationImportOutput",
    "BatchLocalisationImportRequest",
    "BatchLocalisationPolicy",
    "ContainerRuntimeEvidence",
    "LocalisationBatchImportError",
    "import_catalogue_localisation_batch",
    "stage_catalogue_localisation_batch",
    "validate_catalogue_localisation_batch",
]
