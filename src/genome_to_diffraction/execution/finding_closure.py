"""Fail-closed Phase III finding-closure record verification.

The pass-2 scheduler gate consumes one immutable record whose source commit,
source tree, exact ledger bytes, integration evidence, and complete finding
inventory agree.  This module performs no scheduling and writes no output.
Missing, duplicate, stale, locally qualified, or otherwise non-final findings
raise :class:`PhaseIIIFindingClosureError`.
"""

import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, ValidationError, model_validator

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.schemas.base import ContractModel, NonEmptyString, Sha256Hex
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract
from genome_to_diffraction.status import InputContractError

FindingIdentifier = Annotated[
    str,
    Field(pattern=r"^(PIPE|DEV|PH3|FCB)-P[0-3]-[0-9]{2}$"),
]
GitObjectHex = Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
ClosureIdentifier = Annotated[
    str,
    Field(pattern=r"^phase3closure_[a-f0-9]{64}$"),
]

_LEDGER_ROW = re.compile(
    r"^\|\s*`(?P<finding>(?:PIPE|DEV|PH3|FCB)-P[0-3]-[0-9]{2})`"
    r"[^|]*\|\s*(?P<status>[^|]+?)\s*\|"
)
_FINAL_LEDGER_STATUS = frozenset({"Fixed", "Superseded", "Deleted"})


class PhaseIIIFindingClosureError(InputContractError):
    """The Phase III pass-2 finding-closure authority is not complete."""


class FindingDisposition(StrEnum):
    """Permitted final dispositions at the Phase III pass-2 gate."""

    FIXED = "fixed"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class PhaseIIIFindingClosureEntry(ContractModel):
    """One final finding disposition and its exact regression/evidence IDs."""

    finding_id: FindingIdentifier
    disposition: FindingDisposition
    regression_ids: tuple[NonEmptyString, ...] = Field(min_length=1)
    evidence_ids: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_sorted_evidence(self) -> Self:
        for label, values in (
            ("regression_ids", self.regression_ids),
            ("evidence_ids", self.evidence_ids),
        ):
            if values != tuple(sorted(values)) or len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique and sorted")
        return self


class PhaseIIIFindingClosureRecord(_ContentAddressedContract):
    """Exact-source authority required before an unknown pass-2 submission."""

    _identity_field: ClassVar[str] = "closure_id"
    _identity_prefix: ClassVar[str] = "phase3closure_"

    schema_version: Literal["2.0"]
    closure_id: ClosureIdentifier
    source_commit: GitObjectHex
    source_tree: GitObjectHex
    ledger_sha256: Sha256Hex
    adverse_review_sha256: Sha256Hex
    integration_gate_sha256: Sha256Hex
    known_control_evidence_sha256: Sha256Hex
    m6_evidence_sha256: Sha256Hex
    unknown_pass1_evidence_sha256: Sha256Hex
    exact_source_ci_run_id: int = Field(gt=0)
    exact_source_ci_job_id: int = Field(gt=0)
    exact_source_ci_status: Literal["success"]
    entries: tuple[PhaseIIIFindingClosureEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_complete_inventory(self) -> Self:
        finding_ids = tuple(entry.finding_id for entry in self.entries)
        if finding_ids != tuple(sorted(finding_ids)):
            raise ValueError("finding closure entries must be sorted")
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("finding closure entries must be unique")
        return self


def _regular_file(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise PhaseIIIFindingClosureError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise PhaseIIIFindingClosureError(f"{label} is absent or unreadable") from error
    if not resolved.is_file():
        raise PhaseIIIFindingClosureError(f"{label} must be a regular file")
    return resolved


def _ledger_dispositions(ledger: Path) -> dict[str, FindingDisposition]:
    try:
        text = ledger.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise PhaseIIIFindingClosureError(
            "Phase III finding ledger is not strict UTF-8 text"
        ) from error

    dispositions: dict[str, FindingDisposition] = {}
    non_final: list[str] = []
    for line in text.splitlines():
        match = _LEDGER_ROW.match(line)
        if match is None:
            continue
        finding_id = match.group("finding")
        if finding_id in dispositions:
            raise PhaseIIIFindingClosureError(
                f"Phase III finding ledger repeats {finding_id}"
            )
        status = match.group("status")
        if status not in _FINAL_LEDGER_STATUS:
            non_final.append(f"{finding_id}={status}")
            continue
        dispositions[finding_id] = FindingDisposition(status.lower())

    if non_final:
        raise PhaseIIIFindingClosureError(
            "Phase III finding ledger contains non-final dispositions: "
            + ", ".join(non_final)
        )
    if not dispositions:
        raise PhaseIIIFindingClosureError(
            "Phase III finding ledger contains no final finding rows"
        )
    return dispositions


def validate_phase3_finding_closure(
    closure_path: Path,
    ledger_path: Path,
    *,
    expected_source_commit: str,
    expected_source_tree: str,
) -> PhaseIIIFindingClosureRecord:
    """Authenticate one complete finding-closure record against exact source."""

    closure = _regular_file(closure_path, label="Phase III finding closure")
    ledger = _regular_file(ledger_path, label="Phase III finding ledger")
    try:
        document = load_json_document(closure)
        record = PhaseIIIFindingClosureRecord.model_validate(document)
    except (ContractLoadError, ValidationError, ValueError) as error:
        raise PhaseIIIFindingClosureError(
            f"Phase III finding closure violates its contract: {error}"
        ) from error

    if record.source_commit != expected_source_commit:
        raise PhaseIIIFindingClosureError(
            "Phase III finding closure belongs to another source commit"
        )
    if record.source_tree != expected_source_tree:
        raise PhaseIIIFindingClosureError(
            "Phase III finding closure belongs to another source tree"
        )
    if record.ledger_sha256 != sha256_file(ledger, progress=False):
        raise PhaseIIIFindingClosureError(
            "Phase III finding ledger differs from the closure record"
        )

    ledger_dispositions = _ledger_dispositions(ledger)
    record_dispositions = {
        entry.finding_id: entry.disposition for entry in record.entries
    }
    if record_dispositions != ledger_dispositions:
        missing = sorted(set(ledger_dispositions) - set(record_dispositions))
        unexpected = sorted(set(record_dispositions) - set(ledger_dispositions))
        changed = sorted(
            finding_id
            for finding_id in set(record_dispositions) & set(ledger_dispositions)
            if record_dispositions[finding_id] != ledger_dispositions[finding_id]
        )
        raise PhaseIIIFindingClosureError(
            "Phase III finding closure inventory differs from the ledger: "
            f"missing={missing}, unexpected={unexpected}, changed={changed}"
        )
    return record


__all__ = [
    "FindingDisposition",
    "PhaseIIIFindingClosureEntry",
    "PhaseIIIFindingClosureError",
    "PhaseIIIFindingClosureRecord",
    "validate_phase3_finding_closure",
]
