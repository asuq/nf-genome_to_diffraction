"""Truthless, checksum-bound reportable-identity decisions for M6.

The runner derives one decision from the unique exact-sequence groups represented
by its selected MR seeds.  Zero, one, or multiple groups yield ``abstained``,
``reported``, or ``ambiguous`` respectively.  This is workflow evidence, not a
claim of biological identity; truth-side collection and evaluation decide whether
a reported digest is correct.

Inputs are selected-seed rows and the complete case catalogue.  The output is an
immutable ``M6IdentityDecision`` whose candidates and evidence pointers are unique
and canonically sorted.  Missing catalogue groups, malformed seed evidence,
conflicting pointers, or changed content identifiers fail loudly.  The adapter has
no external command, scheduler, or network dependency; ``identity_decision_id``
is its cache/content key over the case, state, candidates, and complete seed-row
digests.  Focused unit tests cover all three states, deduplication, canonical
replay, and tamper rejection.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Literal, Self

from pydantic import model_validator

from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.schemas.base import ContractModel, NonEmptyString, Sha256Hex
from genome_to_diffraction.schemas.results import SequenceGroupRecord

_IDENTITY_ADAPTER = "m6-identity-decision-v1"


class M6IdentityEvidencePointer(ContractModel):
    """Content-addressed pointer to one complete selected-seed row."""

    role: Literal["selected_seed"]
    record_id: NonEmptyString
    seed_solution_id: NonEmptyString
    record_sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_content_id(self) -> Self:
        if self.record_id != content_id("m6idevidence_", self.identity_payload()):
            raise ValueError("identity evidence record identifier changed")
        return self

    def identity_payload(self) -> dict[str, str]:
        """Return the explicit pointer identity, excluding only its record ID."""

        return {
            "role": self.role,
            "seed_solution_id": self.seed_solution_id,
            "record_sha256": self.record_sha256,
        }


class M6IdentityCandidate(ContractModel):
    """One exact-sequence candidate and the selected seeds supporting it."""

    sequence_group_id: NonEmptyString
    sequence_sha256: Sha256Hex
    evidence_pointers: tuple[M6IdentityEvidencePointer, ...]

    @model_validator(mode="after")
    def _validate_identity_and_order(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError("identity candidate group and sequence digest differ")
        if not self.evidence_pointers:
            raise ValueError("identity candidate lacks selected-seed evidence")
        pointer_keys = tuple(
            _pointer_key(pointer) for pointer in self.evidence_pointers
        )
        if tuple(sorted(set(pointer_keys))) != pointer_keys:
            raise ValueError("identity evidence pointers must be unique and sorted")
        return self


class M6IdentityDecision(ContractModel):
    """One content-addressed runner decision carried unchanged to truth side."""

    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-identity-decision-v1"]
    identity_decision_id: NonEmptyString
    case_id: NonEmptyString
    decision: Literal["reported", "ambiguous", "abstained"]
    candidates: tuple[M6IdentityCandidate, ...]

    @model_validator(mode="after")
    def _validate_state_order_and_content_id(self) -> Self:
        expected_state = (
            "abstained"
            if not self.candidates
            else "reported"
            if len(self.candidates) == 1
            else "ambiguous"
        )
        if self.decision != expected_state:
            raise ValueError("identity decision does not match its candidate count")
        candidate_keys = tuple(
            (candidate.sequence_sha256, candidate.sequence_group_id)
            for candidate in self.candidates
        )
        if tuple(sorted(set(candidate_keys))) != candidate_keys:
            raise ValueError("identity candidates must be unique and sorted")
        if self.identity_decision_id != content_id(
            "m6identity_", self.identity_payload()
        ):
            raise ValueError("identity decision content identifier changed")
        return self

    def identity_payload(self) -> dict[str, object]:
        """Return the explicit content-identity view, excluding only its ID."""

        return {
            "schema_version": self.schema_version,
            "adapter_version": self.adapter_version,
            "case_id": self.case_id,
            "decision": self.decision,
            "candidates": [
                candidate.model_dump(mode="json") for candidate in self.candidates
            ],
        }


def _pointer_key(pointer: M6IdentityEvidencePointer) -> tuple[str, str, str]:
    return (
        pointer.seed_solution_id,
        pointer.record_sha256,
        pointer.record_id,
    )


def _selected_seed_pointer(
    raw_row: Mapping[str, object],
) -> tuple[str, M6IdentityEvidencePointer]:
    group_id = raw_row.get("sequence_group_id")
    seed_id = raw_row.get("seed_solution_id")
    if not isinstance(group_id, str) or not group_id:
        raise ValueError("selected seed lacks a sequence-group identifier")
    if not isinstance(seed_id, str) or not seed_id:
        raise ValueError("selected seed lacks a solution identifier")
    row_sha256 = canonical_digest(raw_row)
    payload = {
        "role": "selected_seed",
        "seed_solution_id": seed_id,
        "record_sha256": row_sha256,
    }
    return group_id, M6IdentityEvidencePointer(
        role="selected_seed",
        record_id=content_id("m6idevidence_", payload),
        seed_solution_id=seed_id,
        record_sha256=row_sha256,
    )


def _evidence_by_group(
    selected_seed_results: Iterable[Mapping[str, object]],
) -> dict[str, tuple[M6IdentityEvidencePointer, ...]]:
    evidence: defaultdict[str, dict[str, M6IdentityEvidencePointer]] = defaultdict(dict)
    seed_owner: dict[str, tuple[str, str]] = {}
    for raw_row in selected_seed_results:
        group_id, pointer = _selected_seed_pointer(raw_row)
        observed = (group_id, pointer.record_sha256)
        previous = seed_owner.setdefault(pointer.seed_solution_id, observed)
        if previous != observed:
            raise ValueError(
                "selected-seed evidence pointer has conflicting identities"
            )
        evidence[group_id][pointer.record_id] = pointer
    return {
        group_id: tuple(sorted(pointers.values(), key=_pointer_key))
        for group_id, pointers in evidence.items()
    }


def verify_m6_identity_decision_evidence(
    decision: M6IdentityDecision,
    selected_seed_results: Iterable[Mapping[str, object]],
) -> None:
    """Verify that a decision is bound to the complete selected-seed rows."""

    expected = _evidence_by_group(selected_seed_results)
    observed = {
        candidate.sequence_group_id: candidate.evidence_pointers
        for candidate in decision.candidates
    }
    if observed != expected:
        raise ValueError("identity decision does not match selected-seed evidence")


def derive_m6_identity_decision(
    *,
    case_id: str,
    selected_seed_results: Iterable[Mapping[str, object]],
    sequence_groups: Iterable[SequenceGroupRecord],
) -> M6IdentityDecision:
    """Derive the minimal truthless decision from unique selected seed groups."""

    group_index: dict[str, SequenceGroupRecord] = {}
    for group in sequence_groups:
        if group.sequence_group_id in group_index:
            raise ValueError(
                f"duplicate sequence group in identity catalogue: "
                f"{group.sequence_group_id}"
            )
        group_index[group.sequence_group_id] = group

    evidence_by_group = _evidence_by_group(selected_seed_results)
    for group_id in evidence_by_group:
        if group_id not in group_index:
            raise ValueError(
                f"selected seed references unknown sequence group: {group_id}"
            )

    candidates = tuple(
        sorted(
            (
                M6IdentityCandidate(
                    sequence_group_id=group_id,
                    sequence_sha256=group_index[group_id].sha256,
                    evidence_pointers=pointers,
                )
                for group_id, pointers in evidence_by_group.items()
            ),
            key=lambda candidate: (
                candidate.sequence_sha256,
                candidate.sequence_group_id,
            ),
        )
    )
    decision: Literal["reported", "ambiguous", "abstained"]
    if not candidates:
        decision = "abstained"
    elif len(candidates) == 1:
        decision = "reported"
    else:
        decision = "ambiguous"
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "adapter_version": _IDENTITY_ADAPTER,
        "case_id": case_id,
        "decision": decision,
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
    }
    return M6IdentityDecision(
        schema_version="1.0",
        adapter_version=_IDENTITY_ADAPTER,
        identity_decision_id=content_id("m6identity_", payload),
        case_id=case_id,
        decision=decision,
        candidates=candidates,
    )
