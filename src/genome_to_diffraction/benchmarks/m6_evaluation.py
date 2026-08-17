"""Truth-side evaluation of collected M6 benchmark evidence.

The runner never imports this module.  After a runner result archive has been
checksum-fixed and collected, a separate evaluator joins its opaque case IDs to
the frozen protocol and records the predeclared inclusion, abstention,
open-set, retention, and provenance gates.

LLG and TFZ remain annotations in the underlying evidence.  They are not
candidate-deletion gates here or in the runner.  A failed gate produces an
explicit hold; it is never rounded, relabelled, or silently excluded.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.benchmarks.m6_edge import (
    M6EdgeObservation,
    verify_edge_observations,
)
from genome_to_diffraction.benchmarks.m6_identity import M6IdentityDecision
from genome_to_diffraction.benchmarks.m6_protocol import (
    M6BenchmarkProtocol,
    M6CaseSpec,
    M6TrackCriteria,
    load_m6_protocol,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    OperatorIdentifier,
    PositiveFloat,
    PositiveInt,
    Sha256Hex,
)

NonNegativeInt = Annotated[int, Field(ge=0)]


class M6FamilyModelEvidence(ContractModel):
    """Truth-side family classification for one attempted structural model."""

    hypothesis_id: NonEmptyString
    model_id: NonEmptyString
    pdb_id: NonEmptyString
    pdb_entity_id: PositiveInt
    classification: Literal[
        "verified_family",
        "excluded_close_family",
        "exact_deposition",
        "off_family",
    ]


class M6SoftwareProvenance(ContractModel):
    """Immutable software, lock, database, and runner identifiers."""

    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    nf_helper_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    pixi_version: NonEmptyString
    pixi_lock_sha256: Sha256Hex
    phenix_release: NonEmptyString
    phenix_manifest_sha256: Sha256Hex
    database_manifest_sha256: Sha256Hex
    runner_archive_sha256: Sha256Hex
    runner_manifest_sha256: Sha256Hex
    track_source_commits: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_track_commits(self) -> Self:
        if self.track_source_commits and set(self.track_source_commits) != {
            "operational",
            "leakage",
        }:
            raise ValueError("M6 track source commits must cover both tracks")
        if any(
            re.fullmatch(r"[a-f0-9]{40}", value) is None
            for value in self.track_source_commits.values()
        ):
            raise ValueError("M6 track source commit is invalid")
        return self


class M6CaseAssessment(ContractModel):
    """Truth-side assessment derived from one opaque runner case result."""

    case_id: str = Field(pattern=r"^M6C[0-9]{3}$")
    execution_status: Literal["completed", "failed"]
    scientific_status: Literal[
        "candidate_evidence",
        "no_exact_assignment",
        "assumption_violation",
        "abstained",
        "ambiguous_multiple_loci",
        "typed_control_outcome",
        "not_assessed",
    ]
    typed_outcome: NonEmptyString
    failure_class: str | None = None
    candidate_count: NonNegativeInt
    retained_candidate_count: NonNegativeInt
    all_candidates_retained: bool
    target_sequence_rank: PositiveInt | None = None
    correct_family_model_retained: bool | None = None
    credible_seed_recovered: bool | None = None
    supported_copy_count: PositiveInt | None = None
    runner_identity_decision: M6IdentityDecision
    family_model_evidence: tuple[M6FamilyModelEvidence, ...] = ()
    edge_observations: tuple[M6EdgeObservation, ...] = ()
    edge_outcome_verified: bool | None = None
    exact_identity_sequence_sha256: Sha256Hex | None = None

    @model_validator(mode="after")
    def _validate_counts_and_failure(self) -> Self:
        if self.retained_candidate_count > self.candidate_count:
            raise ValueError("retained candidate count exceeds the candidate count")
        if self.all_candidates_retained != (
            self.retained_candidate_count == self.candidate_count
        ):
            raise ValueError("candidate-retention flag disagrees with the counts")
        if self.execution_status == "failed" and self.failure_class is None:
            raise ValueError("failed M6 assessment lacks a failure class")
        if self.execution_status == "completed" and self.failure_class is not None:
            raise ValueError("completed M6 assessment cannot have a failure class")
        expected_identity = (
            self.runner_identity_decision.candidates[0].sequence_sha256
            if self.runner_identity_decision.decision == "reported"
            else None
        )
        if self.exact_identity_sequence_sha256 != expected_identity:
            raise ValueError(
                "exact identity digest disagrees with the runner identity decision"
            )
        if verify_edge_observations(self.case_id, self.edge_observations) != (
            self.edge_observations
        ):
            raise ValueError("M6 edge observations are not canonical")
        verified_family = any(
            item.classification == "verified_family"
            for item in self.family_model_evidence
        )
        if (
            self.correct_family_model_retained is not None
            and self.correct_family_model_retained != verified_family
        ):
            raise ValueError(
                "correct-family flag disagrees with classified model evidence"
            )
        if self.edge_outcome_verified is True and (
            len(self.edge_observations) != 1
            or self.edge_observations[0].measurement_status != "measured"
        ):
            raise ValueError("verified edge outcome lacks measured edge evidence")
        return self


class M6CollectedEvidence(ContractModel):
    """Complete separately collected evidence for all 63 frozen cases."""

    schema_version: Literal["1.1"]
    protocol_id: OperatorIdentifier
    protocol_sha256: Sha256Hex
    private_truth_map_sha256: Sha256Hex
    run_ids: tuple[OperatorIdentifier, ...] = Field(min_length=2, max_length=2)
    provenance: M6SoftwareProvenance
    maximum_cpu_count: PositiveInt
    maximum_memory_gb: PositiveFloat
    maximum_concurrent_phenix_attempts: NonNegativeInt
    scheduler_ceiling_hours: PositiveFloat
    execution_policy_id: str | None = None
    execution_policy_sha256: Sha256Hex | None = None
    child_job_count: NonNegativeInt = 1
    peak_running_jobs: NonNegativeInt = 1
    peak_aggregate_cpu_count: NonNegativeInt = 0
    peak_aggregate_memory_gb: float = Field(default=0.0, ge=0)
    deterministic_replay_equivalent: bool
    resume_equivalent: bool
    cache_invalidation_verified: bool
    no_silent_partial_output: bool
    bounded_interface_verified: bool
    assessments: tuple[M6CaseAssessment, ...] = Field(min_length=63, max_length=63)

    @model_validator(mode="after")
    def _validate_case_ids(self) -> Self:
        case_ids = [assessment.case_id for assessment in self.assessments]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("collected M6 case IDs must be unique")
        return self


@dataclass(frozen=True)
class M6EvaluationRequest:
    """One truth-side evaluation request."""

    protocol: Path
    evidence: Path
    report: Path | None = None


@dataclass(frozen=True)
class M6EvaluationResult:
    """Stable M6 release-gate outcome."""

    accepted: bool
    failed_gates: tuple[str, ...]
    report: dict[str, object]
    report_path: Path | None


def load_m6_evidence(path: Path) -> M6CollectedEvidence:
    """Load the checksum-fixed truth-side evidence contract."""

    resolved = path.resolve(strict=True)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        return M6CollectedEvidence.model_validate(payload)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise PublicControlError(f"invalid M6 evidence {resolved}: {error}") from error


def _positive_metrics(
    protocol: M6BenchmarkProtocol,
    cases: dict[str, M6CaseSpec],
    assessments: dict[str, M6CaseAssessment],
    *,
    kind: Literal["operational_positive", "leakage_positive"],
) -> dict[str, int]:
    selected = [case for case in protocol.cases if case.case_kind == kind]
    truth = {target.target_key: target for target in protocol.positives}
    top_25 = 0
    top_10 = 0
    top_5 = 0
    correct_family = 0
    correct_family_denominator = 0
    credible_seed = 0
    true_copy = 0
    for case in selected:
        assessment = assessments[case.case_id]
        rank = assessment.target_sequence_rank
        top_25 += rank is not None and rank <= 25
        top_10 += rank is not None and rank <= 10
        top_5 += rank is not None and rank <= 5
        family_eligible = (
            kind == "operational_positive"
            or truth[case.target_key].correct_family_model_eligible
        )
        if family_eligible:
            correct_family_denominator += 1
            correct_family += assessment.correct_family_model_retained is True
        credible_seed += assessment.credible_seed_recovered is True
        true_copy += assessment.supported_copy_count == (
            truth[case.target_key].expected_asu_copy_count
        )
    return {
        "positive_case_count": len(selected),
        "top_25": top_25,
        "top_10": top_10,
        "top_5": top_5,
        "correct_family_model": correct_family,
        "correct_family_denominator": correct_family_denominator,
        "credible_seed": credible_seed,
        "true_copy": true_copy,
    }


def _track_gates(
    prefix: str,
    metrics: dict[str, int],
    criteria: M6TrackCriteria,
) -> dict[str, bool]:
    return {
        f"{prefix}_positive_case_count": metrics["positive_case_count"]
        == criteria.positive_case_count,
        f"{prefix}_top_25": metrics["top_25"] >= criteria.minimum_top_25,
        f"{prefix}_top_10": metrics["top_10"] >= criteria.minimum_top_10,
        f"{prefix}_top_5": metrics["top_5"] >= criteria.minimum_top_5,
        f"{prefix}_correct_family_model": metrics["correct_family_model"]
        >= criteria.minimum_correct_family_model,
        f"{prefix}_correct_family_denominator": metrics["correct_family_denominator"]
        == criteria.correct_family_denominator,
        f"{prefix}_credible_seed": metrics["credible_seed"]
        >= criteria.minimum_credible_seed,
        f"{prefix}_true_copy": metrics["true_copy"] >= criteria.minimum_true_copy,
    }


def _typed_edge_outcome(case: M6CaseSpec, assessment: M6CaseAssessment) -> bool:
    del case
    return assessment.edge_outcome_verified is True


def evaluate_m6(request: M6EvaluationRequest) -> M6EvaluationResult:
    """Evaluate all frozen gates and optionally write the deterministic report."""

    protocol_path = request.protocol.resolve(strict=True)
    protocol = load_m6_protocol(protocol_path)
    execution_policy_path = protocol_path.with_name("execution-nextflow-v1.yaml")
    expected_execution_policy_sha256 = (
        sha256_file(execution_policy_path) if execution_policy_path.is_file() else None
    )
    evidence = load_m6_evidence(request.evidence)
    if evidence.protocol_id != protocol.protocol_id:
        raise PublicControlError("M6 evidence and protocol IDs disagree")
    if evidence.protocol_sha256 != sha256_file(protocol_path):
        raise PublicControlError("M6 evidence was evaluated against another protocol")
    cases = {case.case_id: case for case in protocol.cases}
    assessments = {
        assessment.case_id: assessment for assessment in evidence.assessments
    }
    if set(assessments) != set(cases):
        raise PublicControlError("M6 evidence does not cover the frozen case matrix")

    total_candidates = sum(item.candidate_count for item in assessments.values())
    retained_candidates = sum(
        item.retained_candidate_count for item in assessments.values()
    )
    retention_fraction = (
        1.0 if total_candidates == 0 else retained_candidates / total_candidates
    )
    open_set = [
        case
        for case in protocol.cases
        if case.case_kind in {"target_absent", "wrong_related_catalogue"}
    ]
    reported_open_set = [
        (
            case.case_id,
            assessments[case.case_id]
            .runner_identity_decision.candidates[0]
            .sequence_sha256,
        )
        for case in open_set
        if assessments[case.case_id].runner_identity_decision.decision == "reported"
    ]
    false_assignments = len(reported_open_set)
    assumptions = [
        assessments[case.case_id]
        for case in protocol.cases
        if case.case_kind == "assumption_violation"
    ]
    assumption_abstentions = sum(
        item.scientific_status in {"assumption_violation", "abstained"}
        for item in assumptions
    )
    duplicate_cases = [
        assessments[case.case_id]
        for case in protocol.cases
        if case.case_kind == "duplicate_locus"
    ]
    duplicate_ambiguities = sum(
        item.scientific_status == "ambiguous_multiple_loci"
        and item.typed_outcome == "duplicate_loci_retained"
        for item in duplicate_cases
    )
    positive_identity_checks = []
    truth = {target.target_key: target for target in protocol.positives}
    for case in protocol.cases:
        if case.case_kind not in {"operational_positive", "leakage_positive"}:
            continue
        decision = assessments[case.case_id].runner_identity_decision
        called = (
            decision.candidates[0].sequence_sha256
            if decision.decision == "reported"
            else None
        )
        positive_identity_checks.append(
            called is None or called == truth[case.target_key].target_sequence_sha256
        )
    edge_cases = [
        case
        for case in protocol.cases
        if case.case_kind
        not in {
            "operational_positive",
            "leakage_positive",
            "target_absent",
            "wrong_related_catalogue",
            "assumption_violation",
            "duplicate_locus",
        }
    ]
    typed_edge_count = sum(
        _typed_edge_outcome(case, assessments[case.case_id]) for case in edge_cases
    )
    unexpected_execution_failures = sum(
        assessment.execution_status == "failed" and case.case_kind != "missing_phenix"
        for case in protocol.cases
        for assessment in (assessments[case.case_id],)
    )
    exact_deposition_attempts = [
        {"case_id": assessment.case_id, "hypothesis_id": item.hypothesis_id}
        for assessment in assessments.values()
        for item in assessment.family_model_evidence
        if item.classification == "exact_deposition"
    ]
    leakage_close_attempts = [
        {"case_id": assessment.case_id, "hypothesis_id": item.hypothesis_id}
        for case_id, assessment in assessments.items()
        if cases[case_id].case_kind == "leakage_positive"
        for item in assessment.family_model_evidence
        if item.classification == "excluded_close_family"
    ]

    operational_metrics = _positive_metrics(
        protocol, cases, assessments, kind="operational_positive"
    )
    leakage_metrics = _positive_metrics(
        protocol, cases, assessments, kind="leakage_positive"
    )
    gates: dict[str, bool] = {
        "case_count": len(assessments) == 63,
        "runner_identity_decisions_complete": all(
            assessment.runner_identity_decision.case_id == assessment.case_id
            for assessment in assessments.values()
        ),
        "candidate_retention": retention_fraction
        == protocol.criteria.candidate_retention_fraction
        and all(item.all_candidates_retained for item in assessments.values()),
        "open_set_case_count": len(open_set) == protocol.criteria.open_set_case_count,
        "exact_false_assignments": false_assignments
        <= protocol.criteria.maximum_exact_false_assignments,
        "positive_exact_assignments_not_wrong": all(positive_identity_checks),
        "assumption_abstentions": assumption_abstentions
        >= protocol.criteria.required_assumption_abstentions,
        "duplicate_locus_ambiguities": duplicate_ambiguities
        >= protocol.criteria.required_duplicate_locus_ambiguities,
        "typed_edge_outcomes": typed_edge_count == len(edge_cases),
        "unexpected_execution_failures": unexpected_execution_failures == 0,
        "no_exact_deposition_models_attempted": not exact_deposition_attempts,
        "no_leakage_close_models_attempted": not leakage_close_attempts,
        "deterministic_replay_equivalent": evidence.deterministic_replay_equivalent,
        "resume_equivalent": evidence.resume_equivalent,
        "cache_invalidation_verified": evidence.cache_invalidation_verified,
        "no_silent_partial_output": evidence.no_silent_partial_output,
        "bounded_interface_verified": evidence.bounded_interface_verified,
        "execution_policy_verified": (
            (
                evidence.execution_policy_id is None
                and evidence.execution_policy_sha256 is None
                and evidence.maximum_cpu_count <= 8
            )
            or (
                evidence.execution_policy_id == "m6_nextflow_slurm_v1"
                and evidence.execution_policy_sha256 == expected_execution_policy_sha256
                and evidence.child_job_count > 0
            )
        ),
        "bounded_cpu_per_job": evidence.maximum_cpu_count <= 32,
        "bounded_memory": evidence.maximum_memory_gb <= 16.0,
        "phenix_concurrency_recorded": evidence.maximum_concurrent_phenix_attempts >= 0,
        "bounded_scheduler_ceiling": evidence.scheduler_ceiling_hours <= 24.0,
    }
    gates.update(
        _track_gates("operational", operational_metrics, protocol.criteria.operational)
    )
    gates.update(
        _track_gates(
            "leakage",
            leakage_metrics,
            protocol.criteria.leakage_controlled,
        )
    )
    failed_gates = tuple(name for name, passed in gates.items() if not passed)
    report: dict[str, object] = {
        "schema_version": "1.1",
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": evidence.protocol_sha256,
        "release_decision": "accept" if not failed_gates else "hold",
        "generalisation_claim": False,
        "case_count": len(assessments),
        "candidate_count": total_candidates,
        "retained_candidate_count": retained_candidates,
        "candidate_retention_fraction": retention_fraction,
        "open_set_case_count": len(open_set),
        "exact_false_assignment_count": false_assignments,
        "reported_open_set_identities": [
            {"case_id": case_id, "sequence_sha256": digest}
            for case_id, digest in reported_open_set
        ],
        "assumption_abstention_count": assumption_abstentions,
        "duplicate_locus_ambiguity_count": duplicate_ambiguities,
        "typed_edge_outcome_count": typed_edge_count,
        "unexpected_execution_failure_count": unexpected_execution_failures,
        "exact_deposition_attempts": exact_deposition_attempts,
        "leakage_close_family_attempts": leakage_close_attempts,
        "operational_metrics": operational_metrics,
        "leakage_controlled_metrics": leakage_metrics,
        "gates": gates,
        "failed_gates": list(failed_gates),
        "provenance": evidence.provenance.model_dump(mode="json"),
        "limitations": [
            "This is an internal engineering benchmark, not a population-level "
            "sensitivity or specificity estimate.",
            "The pipeline narrows catalogue candidates and does not guarantee an "
            "exact sequence, locus, physiological assembly, or publication-quality "
            "final structure.",
            "LLG and TFZ are retained ranking annotations and never "
            "candidate-deletion gates.",
        ],
    }
    report_path: Path | None = None
    if request.report is not None:
        atomic_write_json(request.report, report)
        report_path = request.report.resolve(strict=True)
    return M6EvaluationResult(
        accepted=not failed_gates,
        failed_gates=failed_gates,
        report=report,
        report_path=report_path,
    )
