"""Derive the T13.1 per-crystal status from accepted T12 evidence.

Execution success is deliberately independent from scientific interpretation.
An empty sequence-decision file therefore yields ``completed_success`` and
``insufficient_evidence`` rather than promoting a ranked candidate.
"""

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.schemas.results import (
    BriefRefinementResult,
    PrototypeAssumptionStatus,
    ReviewDecision,
    ReviewDecisionManifest,
    ScientificStatusRecord,
)
from genome_to_diffraction.status import (
    ExecutionStatus,
    InputContractError,
    ScientificStatus,
)


class StatusEngineError(InputContractError):
    """Accepted T12 evidence or human decisions are inconsistent."""


class _T12Summary(BaseModel):
    schema_version: str
    run_id: str
    candidate_count: int
    completed_refinement_count: int
    failed_refinement_count: int
    completed_sequence_count: int
    failed_sequence_count: int
    all_candidates_retained: bool


class _JobResult(BaseModel):
    schema_version: str
    run_id: str
    completed_at: datetime
    scheduler_state: str
    exit_code: int
    failure_class: str


class _CheckpointManifest(BaseModel):
    schema_version: str
    run_id: str
    finalist_count: int
    outputs: dict[str, str]


@dataclass(frozen=True)
class StatusRequest:
    """Inputs for one deterministic T13.1 status record."""

    crystal_id: str
    t12_summary_json: Path
    job_result_json: Path
    refinement_results_jsonl: Path
    checkpoint_manifest_json: Path
    approval_candidates_tsv: Path
    decisions_tsv: Path
    output_json: Path
    prototype_assumption_status: PrototypeAssumptionStatus = (
        PrototypeAssumptionStatus.UNKNOWN
    )
    residual_content_suspected: bool = False


def _load_model[T: BaseModel](path: Path, model: type[T], label: str) -> T:
    if path.is_symlink() or not path.is_file():
        raise StatusEngineError(f"{label} is absent or unsafe")
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise StatusEngineError(f"invalid {label}: {exc}") from exc


def _read_refinements(path: Path) -> tuple[BriefRefinementResult, ...]:
    if path.is_symlink() or not path.is_file():
        raise StatusEngineError("refinement results are absent or unsafe")
    records: list[BriefRefinementResult] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(BriefRefinementResult.model_validate_json(line))
                except (ValidationError, ValueError) as exc:
                    raise StatusEngineError(
                        f"invalid refinement results at line {line_number}: {exc}"
                    ) from exc
    except OSError as exc:
        raise StatusEngineError(f"cannot read refinement results: {exc}") from exc
    return tuple(records)


def _read_candidate_ids(path: Path) -> set[str]:
    if path.is_symlink() or not path.is_file():
        raise StatusEngineError("approval candidates are absent or unsafe")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if (
                reader.fieldnames is None
                or "sequence_group_id" not in reader.fieldnames
            ):
                raise StatusEngineError("approval candidates lack sequence_group_id")
            return {row["sequence_group_id"] for row in reader}
    except OSError as exc:
        raise StatusEngineError(f"cannot read approval candidates: {exc}") from exc


def _read_decisions(path: Path, candidate_ids: set[str]) -> ReviewDecisionManifest:
    if path.is_symlink() or not path.is_file():
        raise StatusEngineError("sequence decisions are absent or unsafe")
    decisions: list[ReviewDecision] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            expected = {
                "checkpoint",
                "item_id",
                "decision",
                "reviewer",
                "reviewed_at",
                "comment",
                "override_reason",
            }
            if reader.fieldnames is None or set(reader.fieldnames) != expected:
                raise StatusEngineError(
                    "sequence decision columns do not match contract"
                )
            for row in reader:
                if row["checkpoint"] != "sequence_candidate":
                    raise StatusEngineError(
                        "only sequence_candidate decisions are allowed"
                    )
                if row["item_id"] not in candidate_ids:
                    raise StatusEngineError(
                        f"decision references unknown sequence group {row['item_id']}"
                    )
                payload = {
                    key: (value if value != "" else None) for key, value in row.items()
                }
                decisions.append(ReviewDecision.model_validate(payload))
        return ReviewDecisionManifest(schema_version="1.0", decisions=tuple(decisions))
    except (OSError, ValidationError, ValueError) as exc:
        if isinstance(exc, StatusEngineError):
            raise
        raise StatusEngineError(f"invalid sequence decisions: {exc}") from exc


def _scientific_status(
    primary_groups: tuple[str, ...],
    assumption_status: PrototypeAssumptionStatus,
    residual_content_suspected: bool,
) -> ScientificStatus:
    if not primary_groups or assumption_status is PrototypeAssumptionStatus.UNKNOWN:
        return ScientificStatus.INSUFFICIENT_EVIDENCE
    if assumption_status in {
        PrototypeAssumptionStatus.POSSIBLY_VIOLATED,
        PrototypeAssumptionStatus.VIOLATED,
    }:
        return ScientificStatus.SUSPECTED_MULTI_COMPONENT
    if residual_content_suspected:
        return ScientificStatus.CREDIBLE_PARTIAL_SOLUTION
    return ScientificStatus.CREDIBLE_SINGLE_COMPONENT_SOLUTION


def build_status_record(request: StatusRequest) -> ScientificStatusRecord:
    """Validate accepted evidence and atomically write one status record."""

    summary = _load_model(request.t12_summary_json, _T12Summary, "T12 summary")
    job = _load_model(request.job_result_json, _JobResult, "job result")
    checkpoint = _load_model(
        request.checkpoint_manifest_json,
        _CheckpointManifest,
        "sequence checkpoint manifest",
    )
    if len({summary.run_id, job.run_id, checkpoint.run_id}) != 1:
        raise StatusEngineError("T12 run IDs do not agree")
    if (
        job.scheduler_state != "COMPLETED"
        or job.exit_code != 0
        or job.failure_class != "success"
    ):
        raise StatusEngineError("T13.1 currently requires accepted T12 execution")
    if (
        summary.candidate_count <= 0
        or summary.completed_refinement_count != summary.candidate_count
        or summary.completed_sequence_count != summary.candidate_count
        or summary.failed_refinement_count != 0
        or summary.failed_sequence_count != 0
        or not summary.all_candidates_retained
        or checkpoint.finalist_count != summary.candidate_count
    ):
        raise StatusEngineError("T12 evidence is incomplete or candidates were removed")

    expected_candidates_sha = checkpoint.outputs.get(
        request.approval_candidates_tsv.name
    )
    if (
        expected_candidates_sha is None
        or sha256_file(request.approval_candidates_tsv) != expected_candidates_sha
    ):
        raise StatusEngineError("approval-candidate checksum does not match checkpoint")

    refinements = _read_refinements(request.refinement_results_jsonl)
    if len(refinements) != summary.candidate_count:
        raise StatusEngineError("refinement result count does not match T12 summary")
    if any(
        result.execution_status is not ExecutionStatus.COMPLETED_SUCCESS
        for result in refinements
    ):
        raise StatusEngineError("not every refinement completed successfully")

    candidate_ids = _read_candidate_ids(request.approval_candidates_tsv)
    decisions = _read_decisions(request.decisions_tsv, candidate_ids)
    primary_groups = tuple(
        sorted(
            decision.item_id
            for decision in decisions.decisions
            if decision.decision == "approve"
        )
    )
    extended_groups = tuple(
        sorted(
            decision.item_id
            for decision in decisions.decisions
            if decision.decision == "retain_alternative"
        )
    )
    completed_at = max(
        [job.completed_at, *(decision.reviewed_at for decision in decisions.decisions)]
    )
    warnings: list[str] = []
    if not primary_groups:
        warnings.append("human_sequence_approval_pending")
    if request.prototype_assumption_status is PrototypeAssumptionStatus.UNKNOWN:
        warnings.append("prototype_assumption_not_assessed")

    record = ScientificStatusRecord(
        schema_version="1.0",
        crystal_id=request.crystal_id,
        execution_status=ExecutionStatus.COMPLETED_SUCCESS,
        scientific_status=_scientific_status(
            primary_groups,
            request.prototype_assumption_status,
            request.residual_content_suspected,
        ),
        prototype_assumption_status=request.prototype_assumption_status,
        credible_seed_count=summary.candidate_count,
        approved_seed_count=summary.candidate_count,
        primary_sequence_groups=primary_groups,
        extended_sequence_groups=extended_groups,
        best_supported_copy_counts={
            result.seed_solution_id: result.input_copy_count for result in refinements
        },
        residual_content_suspected=request.residual_content_suspected,
        warnings=tuple(warnings),
        completed_at=completed_at,
        provenance_pointers=(
            request.t12_summary_json.name,
            request.job_result_json.name,
            request.refinement_results_jsonl.name,
            request.checkpoint_manifest_json.name,
            request.approval_candidates_tsv.name,
            request.decisions_tsv.name,
        ),
    )
    atomic_write_json(request.output_json, record.model_dump(mode="json"))
    return record
