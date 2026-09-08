"""Retain and truth-join the frozen four-arm M6 comparison.

The collector accepts exactly 48 case/arm outputs from the existing M6 native
graph, verifies their original frozen seed bundles and writes result checksums.
Only the separate evaluator then opens the private truth map and reuses the
existing M6 case assessment. Reference gains/losses are diagnostic; no new
acceptance threshold or alternative to the full 63-case M6 gate is introduced.
No external scientific tool or scheduler is invoked. Missing, changed or
substituted results fail. Tests cover arm partitions and truth-boundary mutation.
"""

import shutil
from pathlib import Path
from typing import cast

from genome_to_diffraction.benchmarks.m6_collection import (
    _assessment,
    _load_private_truth,
)
from genome_to_diffraction.benchmarks.m6_comparison import (
    validate_m6_comparison_advancement,
)
from genome_to_diffraction.benchmarks.m6_comparison_policy import (
    M6_COMPARISON_ARMS,
    M6_COMPARISON_CASES,
    comparison_case_digest,
)
from genome_to_diffraction.benchmarks.m6_evaluation import M6CaseAssessment
from genome_to_diffraction.benchmarks.m6_nextflow import M6CaseEvidence
from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.schemas.io import load_json_document, parse_json_document


def _object(path: Path) -> dict[str, object]:
    value = load_json_document(path)
    if not isinstance(value, dict):
        raise ValueError("M6 comparison result must be an object")
    return cast(dict[str, object], value)


def collect_m6_comparison_results(
    *,
    frozen_root: Path,
    case_evidence: tuple[Path, ...],
    software_lock: Path,
    phenix_manifest: Path,
    output: Path,
) -> Path:
    """Freeze all native case outcomes before any truth-side comparison."""

    frozen = validate_m6_comparison_advancement(
        frozen_root, software_lock=software_lock, phenix_manifest=phenix_manifest
    )
    expected = {
        (row["case_id"], row["arm"]): row
        for row in cast(list[dict[str, object]], frozen["arms"])
    }
    observed: dict[tuple[str, str], tuple[Path, M6CaseEvidence]] = {}
    for directory in case_evidence:
        root = directory.resolve(strict=True)
        case = M6CaseEvidence.model_validate_json(
            (root / "case_record.json").read_bytes()
        )
        context = case.decision_trace.comparison_context
        if context is None:
            raise ValueError("M6 comparison result lacks its explicit arm")
        key = (case.case_id, context.arm)
        if (
            key in observed
            or key not in expected
            or context.cohort.cohort_id != expected[key]["cohort_id"]
        ):
            raise ValueError("M6 comparison repeats or substitutes a case/arm result")
        if (
            comparison_case_digest(root / "raw/finalists/seed_bundle")
            != expected[key]["seed_bundle_sha256"]
        ):
            raise ValueError("M6 comparison execution changed its frozen seed evidence")
        if {row.solution_id for row in case.decision_trace.observed_advancement} != set(
            cast(list[str], expected[key]["selected_seed_ids"])
        ):
            raise ValueError("M6 comparison result omits a frozen advancement chain")
        observed[key] = (root, case)
    if set(observed) != set(expected):
        raise ValueError(
            "M6 comparison requires all forty-eight terminal case/arm outputs"
        )
    output.mkdir(parents=True, exist_ok=False)
    entries: list[dict[str, object]] = []
    for (case_id, arm), (root, case) in sorted(observed.items()):
        relative = f"cases/{case_id}/{arm}"
        shutil.copytree(root, output / relative)
        entries.append(
            {
                "case_id": case_id,
                "arm": arm,
                "path": relative,
                "case_record_sha256": sha256_file(root / "case_record.json"),
                "case_bundle_sha256": comparison_case_digest(root),
                "execution_status": case.execution_status,
            }
        )
    plan = _object(frozen_root / "initial_plan/comparison_plan.json")
    payload = {
        "schema_version": "1.0",
        "comparison_id": "m6_ranking_four_arm_v1",
        "source_commit": plan["source_commit"],
        "protocol_sha256": plan["protocol_sha256"],
        "comparison_spec_sha256": plan["comparison_spec_sha256"],
        "freeze_id": frozen["freeze_id"],
        "freeze_sha256": sha256_file(frozen_root / "comparison_advancement.json"),
        "initial_hypothesis_count": frozen["initial_hypothesis_count"],
        "continuation_chain_count": frozen["continuation_chain_count"],
        "additional_copy_attempt_budget": frozen["additional_copy_attempt_budget"],
        "all_case_arms_retained": True,
        "truth_join_permitted": True,
        "scientific_acceptance": "not_assessed",
        "full_63_case_m6_still_required": True,
        "cases": entries,
    }
    atomic_write_json(
        output / "comparison_results.json",
        {**payload, "results_id": content_id("m6comparisonresults_", payload)},
    )
    return output


def evaluate_m6_comparison_results(
    *,
    results_root: Path,
    protocol_path: Path,
    private_truth_map: Path,
    output: Path,
) -> Path:
    """Apply existing M6 truth assessment after authenticating every frozen result."""

    manifest = _object(results_root / "comparison_results.json")
    identity = {key: value for key, value in manifest.items() if key != "results_id"}
    if (
        manifest.get("results_id") != content_id("m6comparisonresults_", identity)
        or manifest.get("truth_join_permitted") is not True
    ):
        raise ValueError("M6 comparison results have not been checksum-frozen")
    entries = cast(list[dict[str, object]], manifest["cases"])
    if len(entries) != 48 or {(row["case_id"], row["arm"]) for row in entries} != {
        (case_id, arm) for case_id in M6_COMPARISON_CASES for arm in M6_COMPARISON_ARMS
    }:
        raise ValueError("M6 comparison result arm partition differs")
    roots: dict[tuple[str, str], Path] = {}
    records: dict[tuple[str, str], M6CaseEvidence] = {}
    for entry in entries:
        case_id, arm = cast(str, entry["case_id"]), cast(str, entry["arm"])
        if entry["path"] != f"cases/{case_id}/{arm}":
            raise ValueError("M6 comparison result path leaves its fixed scope")
        root = results_root / cast(str, entry["path"])
        if (
            comparison_case_digest(root) != entry["case_bundle_sha256"]
            or sha256_file(root / "case_record.json") != entry["case_record_sha256"]
        ):
            raise ValueError("M6 comparison native result changed before truth joining")
        record = M6CaseEvidence.model_validate_json(
            (root / "case_record.json").read_bytes()
        )
        context = record.decision_trace.comparison_context
        if context is None or (record.case_id, context.arm) != (case_id, arm):
            raise ValueError("M6 comparison result ownership changed")
        roots[(case_id, arm)] = root
        records[(case_id, arm)] = record
    if sha256_file(protocol_path) != manifest["protocol_sha256"]:
        raise ValueError("M6 comparison truth uses another protocol")
    # The truth boundary is crossed only after the complete native checksum audit.
    protocol = load_m6_protocol(protocol_path)
    truth = _load_private_truth(
        private_truth_map, protocol=protocol, protocol_sha256=sha256_file(protocol_path)
    )
    families = {row.target_key: row for row in truth.verified_families}
    private_cases = {row.case_id: row for row in truth.cases}
    cases = {row.case_id: row for row in protocol.cases}
    assessments: dict[tuple[str, str], M6CaseAssessment] = {}
    for key, record in sorted(records.items()):
        ranking_path = roots[key] / "candidate_ranking.jsonl"
        rankings = tuple(
            cast(dict[str, object], parse_json_document(line, label=ranking_path))
            for line in ranking_path.read_text(encoding="utf-8").splitlines()
        )
        assessments[key] = _assessment(
            protocol,
            cases[key[0]],
            record.model_dump(mode="json"),
            rankings,
            families,
            private_cases,
        )
    metrics: dict[tuple[str, str], dict[str, bool | None]] = {}
    for (case_id, arm), assessment in assessments.items():
        rank = assessment.target_sequence_rank
        expected_copies = private_cases[case_id].expected_asu_copy_count
        metrics[(case_id, arm)] = {
            **{
                f"target_scheduled_top{cap}": rank is not None and rank <= cap
                for cap in (5, 10, 25)
            },
            "correct_family_model_retained": assessment.correct_family_model_retained,
            "target_seed_advanced": assessment.stage_metrics.target_advanced_seed_rank
            is not None,
            "true_copy_count_supported": None
            if expected_copies is None
            else assessment.supported_copy_count == expected_copies,
        }
        if assessment.execution_status == "failed":
            for metric in (
                "correct_family_model_retained",
                "target_seed_advanced",
                "true_copy_count_supported",
            ):
                metrics[(case_id, arm)][metric] = None
    differences = []
    for reference in ("A", "B", "C"):
        for metric in next(iter(metrics.values())):
            comparable = [
                case_id
                for case_id in M6_COMPARISON_CASES
                if metrics[(case_id, reference)][metric] is not None
                and metrics[(case_id, "D")][metric] is not None
            ]
            differences.append(
                {
                    "reference_arm": reference,
                    "production_arm": "D",
                    "metric": metric,
                    "gained_cases": [
                        case_id
                        for case_id in comparable
                        if metrics[(case_id, "D")][metric] is True
                        and metrics[(case_id, reference)][metric] is False
                    ],
                    "lost_cases": [
                        case_id
                        for case_id in comparable
                        if metrics[(case_id, "D")][metric] is False
                        and metrics[(case_id, reference)][metric] is True
                    ],
                    "unassessed_cases": [
                        case_id
                        for case_id in M6_COMPARISON_CASES
                        if case_id not in comparable
                    ],
                }
            )
    output.mkdir(parents=True, exist_ok=False)
    atomic_write_text(
        output / "comparison_case_assessments.jsonl",
        "".join(
            canonical_json_text(
                {"arm": arm, "assessment": assessment.model_dump(mode="json")}
            )
            + "\n"
            for (case_id, arm), assessment in sorted(assessments.items())
        ),
    )
    atomic_write_json(
        output / "comparison_evaluation.json",
        {
            "schema_version": "1.0",
            "comparison_id": "m6_ranking_four_arm_v1",
            "results_id": manifest["results_id"],
            "results_sha256": sha256_file(results_root / "comparison_results.json"),
            "private_truth_map_sha256": sha256_file(private_truth_map),
            "case_assessments_sha256": sha256_file(
                output / "comparison_case_assessments.jsonl"
            ),
            "reference_arm_acceptance": "diagnostic_no_new_recovery_cutoff",
            "production_acceptance": "unchanged_full_63_case_m6_criteria_required",
            "failed_case_arms": [
                {"case_id": case_id, "arm": arm}
                for (case_id, arm), assessment in assessments.items()
                if assessment.execution_status == "failed"
            ],
            "gains_and_losses": differences,
        },
    )
    return output
