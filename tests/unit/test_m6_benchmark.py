"""Focused contracts for the approved truth-isolated M6 benchmark."""

import gzip
import hashlib
import json
from pathlib import Path
from typing import cast

import gemmi
import numpy as np
import pytest
import yaml
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from genome_to_diffraction.benchmarks import m6_model_policy as m6_model_policy_module
from genome_to_diffraction.benchmarks.m6_collection import (
    M6CollectionRequest,
    _M6PrivateCaseTruth,
    _M6PrivateFamily,
    collect_m6_evidence,
)
from genome_to_diffraction.benchmarks.m6_collection import (
    _assessment as _truth_assessment,
)
from genome_to_diffraction.benchmarks.m6_edge import (
    M6EdgeObservation,
    M6HttpRateLimitEvidence,
    M6MatthewsCandidateEvidence,
    M6MatthewsEdgeEvidence,
    M6ModelExhaustionEvidence,
    M6MtzEdgeEvidence,
    M6PhenixValidationEvidence,
    M6RemoteGuardEvidence,
    M6RetainedMatthewsFact,
    make_edge_observation,
)
from genome_to_diffraction.benchmarks.m6_evaluation import (
    M6CaseAssessment,
    M6CollectedEvidence,
    M6EvaluationRequest,
    M6FamilyModelEvidence,
    M6SoftwareProvenance,
    evaluate_m6,
)
from genome_to_diffraction.benchmarks.m6_execution import (
    M6ResourceEvidenceRequest,
    collect_m6_resource_evidence,
    load_m6_execution_policy,
)
from genome_to_diffraction.benchmarks.m6_identity import (
    M6IdentityCandidate,
    M6IdentityDecision,
    M6IdentityEvidencePointer,
    derive_m6_identity_decision,
)
from genome_to_diffraction.benchmarks.m6_model_policy import (
    M6ModelPolicyRequest,
    apply_m6_model_policy,
)
from genome_to_diffraction.benchmarks.m6_nextflow import (
    M6CaseEvidence,
    M6CatalogueTask,
    M6HypothesisGroupTask,
    M6TrackPlanRequest,
    build_m6_search_batches,
    plan_m6_nextflow_track,
    run_m6_assemble_case_task,
    run_m6_catalogue_task,
    run_m6_empty_finalists_task,
    run_m6_empty_seeds_task,
    run_m6_preflight_task,
    run_m6_prepare_case_task,
)
from genome_to_diffraction.benchmarks.m6_prepare import (
    M6MtzVariation,
    _write_opaque_catalogue,
    anonymise_m6_catalogue,
    write_m6_mtz_variant,
)
from genome_to_diffraction.benchmarks.m6_protocol import (
    M6BenchmarkProtocol,
    load_m6_protocol,
)
from genome_to_diffraction.benchmarks.m6_runner import (
    M6RunnerBundleRequest,
    build_m6_runner_bundle,
)
from genome_to_diffraction.benchmarks.m6_scientific import (
    M6ScientificTrack,
    m6_track_case_ids,
    verify_m6_scientific_output,
)
from genome_to_diffraction.benchmarks.m6_verification import (
    M6RunnerVerificationRequest,
    verify_m6_runner_bundle,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.diffraction.preflight import select_observations
from genome_to_diffraction.ids import (
    canonical_digest,
    canonical_json_text,
    content_id,
    sequence_digest,
)
from genome_to_diffraction.schemas.results import (
    EligibilityStatus,
    SequenceGroupRecord,
    SourceProteinRecord,
    StructuralSearchHit,
)

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "benchmarks" / "m6" / "protocol.yaml"
EXECUTION_POLICY = ROOT / "benchmarks" / "m6" / "execution-nextflow-v1.yaml"
HASH = "a" * 64


def _identity_decision(case_id: str, digest: str | None = None) -> M6IdentityDecision:
    """Build one valid runner decision for truth-side unit fixtures."""

    if digest is None:
        return derive_m6_identity_decision(
            case_id=case_id,
            selected_seed_results=(),
            sequence_groups=(),
        )
    selected_row = {
        "seed_solution_id": f"seed_{case_id}",
        "sequence_group_id": f"seq_{digest}",
    }
    pointer_payload = {
        "role": "selected_seed",
        "seed_solution_id": selected_row["seed_solution_id"],
        "record_sha256": canonical_digest(selected_row),
    }
    pointer = M6IdentityEvidencePointer(
        role="selected_seed",
        record_id=content_id("m6idevidence_", pointer_payload),
        seed_solution_id=selected_row["seed_solution_id"],
        record_sha256=pointer_payload["record_sha256"],
    )
    candidate = M6IdentityCandidate(
        sequence_group_id=f"seq_{digest}",
        sequence_sha256=digest,
        evidence_pointers=(pointer,),
    )
    payload = {
        "schema_version": "1.0",
        "adapter_version": "m6-identity-decision-v1",
        "case_id": case_id,
        "decision": "reported",
        "candidates": [candidate.model_dump(mode="json")],
    }
    return M6IdentityDecision(
        schema_version="1.0",
        adapter_version="m6-identity-decision-v1",
        identity_decision_id=content_id("m6identity_", payload),
        case_id=case_id,
        decision="reported",
        candidates=(candidate,),
    )


def _assessment(
    protocol: M6BenchmarkProtocol,
    case_id: str,
) -> M6CaseAssessment:
    case = next(item for item in protocol.cases if item.case_id == case_id)
    target = next(
        (item for item in protocol.positives if item.target_key == case.target_key),
        None,
    )
    common: dict[str, object] = {
        "case_id": case.case_id,
        "execution_status": "completed",
        "scientific_status": "typed_control_outcome",
        "typed_outcome": "completed",
        "failure_class": None,
        "candidate_count": 3,
        "retained_candidate_count": 3,
        "all_candidates_retained": True,
        "runner_identity_decision": _identity_decision(case.case_id),
        "exact_identity_sequence_sha256": None,
    }
    edge_kinds = {
        "missing_pdb_model",
        "wrong_sds_mass",
        "non_top_matthews",
        "map_only_mtz",
        "ambiguous_columns_equivalent",
        "ambiguous_columns_conflicting",
        "remote_disabled",
        "remote_rate_limited",
        "missing_phenix",
    }
    if case.case_kind in edge_kinds:
        common.update(
            edge_observations=(_measured_edge_observation(protocol, case.case_id),),
            edge_outcome_verified=True,
        )
    if case.case_kind in {"operational_positive", "leakage_positive"}:
        assert target is not None
        common.update(
            scientific_status="candidate_evidence",
            typed_outcome="target_evidence_retained",
            target_sequence_rank=1,
            correct_family_model_retained=True,
            family_model_evidence=(
                M6FamilyModelEvidence(
                    hypothesis_id=f"hyp_{case.case_id}",
                    model_id=f"model_{case.case_id}",
                    pdb_id="1ABC",
                    pdb_entity_id=1,
                    classification="verified_family",
                ),
            ),
            credible_seed_recovered=True,
            supported_copy_count=target.expected_asu_copy_count,
            runner_identity_decision=_identity_decision(
                case.case_id, target.target_sequence_sha256
            ),
            exact_identity_sequence_sha256=target.target_sequence_sha256,
        )
    elif case.case_kind in {"target_absent", "wrong_related_catalogue"}:
        common.update(
            scientific_status="no_exact_assignment",
            typed_outcome="completed_no_exact_assignment",
        )
    elif case.case_kind == "assumption_violation":
        common.update(
            scientific_status="assumption_violation",
            typed_outcome="assumption_violation",
            candidate_count=0,
            retained_candidate_count=0,
        )
    elif case.case_kind == "duplicate_locus":
        common.update(
            scientific_status="ambiguous_multiple_loci",
            typed_outcome="duplicate_loci_retained",
        )
    else:
        expected = {
            "missing_pdb_model": "completed_no_pdb_model",
            "wrong_sds_mass": "completed_wrong_mass_prior_retained",
            "non_top_matthews": "completed_non_top_matthews_retained",
            "map_only_mtz": "completed_map_only_mtz",
            "ambiguous_columns_equivalent": (
                "completed_equivalent_columns_deterministic"
            ),
            "ambiguous_columns_conflicting": "ambiguous_columns_conflicting",
            "remote_disabled": "completed_remote_disabled",
            "remote_rate_limited": "completed_remote_rate_limited",
            "missing_phenix": "missing_phenix",
        }[case.case_kind]
        common["typed_outcome"] = expected
        if case.case_kind == "ambiguous_columns_conflicting":
            common["scientific_status"] = "abstained"
        if case.case_kind == "missing_phenix":
            common.update(
                execution_status="failed",
                scientific_status="not_assessed",
                failure_class="missing_phenix",
                candidate_count=0,
                retained_candidate_count=0,
            )
    return M6CaseAssessment.model_validate(common)


def _evidence(protocol: M6BenchmarkProtocol) -> M6CollectedEvidence:
    return M6CollectedEvidence(
        schema_version="1.1",
        protocol_id=protocol.protocol_id,
        protocol_sha256=sha256_file(PROTOCOL),
        private_truth_map_sha256=HASH,
        run_ids=("m6-operational-run", "m6-leakage-run"),
        provenance=M6SoftwareProvenance(
            source_commit="a" * 40,
            nf_helper_commit="b" * 40,
            pixi_version="0.76.2",
            pixi_lock_sha256=HASH,
            phenix_release="2.1-6048",
            phenix_manifest_sha256=HASH,
            database_manifest_sha256=HASH,
            runner_archive_sha256=HASH,
            runner_manifest_sha256=HASH,
        ),
        maximum_cpu_count=8,
        maximum_memory_gb=16.0,
        maximum_concurrent_phenix_attempts=4,
        scheduler_ceiling_hours=24.0,
        deterministic_replay_equivalent=True,
        resume_equivalent=True,
        cache_invalidation_verified=True,
        no_silent_partial_output=True,
        bounded_interface_verified=True,
        assessments=tuple(
            _assessment(protocol, case.case_id) for case in protocol.cases
        ),
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _private_truth_file(
    tmp_path: Path, protocol_path: Path, protocol: M6BenchmarkProtocol
) -> Path:
    positives = {item.target_key: item for item in protocol.positives}
    assumptions = {item.target_key: item for item in protocol.assumption_controls}
    cases: list[dict[str, object]] = []
    for case in protocol.cases:
        target = positives.get(case.target_key)
        if target is not None:
            digests = (target.target_sequence_sha256,)
            source_pdb_id = target.source.pdb_id
            expected_copy_count = target.expected_asu_copy_count
        else:
            assumption = assumptions[case.target_key]
            digests = tuple(item.sequence_sha256 for item in assumption.proteins)
            source_pdb_id = assumption.source.pdb_id
            expected_copy_count = None
        cases.append(
            {
                "case_id": case.case_id,
                "case_kind": case.case_kind,
                "target_key": case.target_key,
                "source_pdb_id": source_pdb_id,
                "target_sequence_sha256": list(digests),
                "target_opaque_loci": {
                    digest: [f"opaque_{index}"]
                    for index, digest in enumerate(digests, start=1)
                },
                "expected_asu_copy_count": expected_copy_count,
            }
        )
    path = tmp_path / "private_truth_map.json"
    _write_json(
        path,
        {
            "schema_version": "1.1",
            "protocol_id": protocol.protocol_id,
            "protocol_sha256": sha256_file(protocol_path),
            "cluster_snapshots": [
                {
                    "identity_threshold_percent": threshold,
                    "file_name": Path(
                        (
                            protocol.leakage_policy.rcsb_30_snapshot
                            if threshold == 30
                            else protocol.leakage_policy.rcsb_70_snapshot
                        ).url
                    ).name,
                    "source_url": (
                        protocol.leakage_policy.rcsb_30_snapshot
                        if threshold == 30
                        else protocol.leakage_policy.rcsb_70_snapshot
                    ).url,
                    "sha256": (
                        protocol.leakage_policy.rcsb_30_snapshot
                        if threshold == 30
                        else protocol.leakage_policy.rcsb_70_snapshot
                    ).sha256,
                    "size_bytes": (
                        protocol.leakage_policy.rcsb_30_snapshot
                        if threshold == 30
                        else protocol.leakage_policy.rcsb_70_snapshot
                    ).size_bytes,
                    "target_line_count": 12,
                }
                for threshold in (30, 70)
            ],
            "verified_families": [
                _private_family(protocol, target.target_key).model_dump(mode="json")
                for target in protocol.positives
            ],
            "cases": cases,
        },
    )
    return path


def test_m6_protocol_fixes_the_approved_case_balance() -> None:
    protocol = load_m6_protocol(PROTOCOL)

    assert len(protocol.cases) == 63
    assert len(protocol.positives) == 12
    assert len(protocol.assumption_controls) == 4
    assert {target.expected_asu_copy_count for target in protocol.positives} == {
        1,
        2,
        3,
        4,
        6,
    }


def test_m6_scientific_tracks_partition_all_opaque_cases() -> None:
    protocol = load_m6_protocol(PROTOCOL)
    operational = m6_track_case_ids("operational")
    leakage = m6_track_case_ids("leakage")

    assert len(operational) == 36
    assert len(leakage) == 27
    assert set(operational).isdisjoint(leakage)
    assert set(operational) | set(leakage) == {
        f"M6C{index:03d}" for index in range(1, 64)
    }
    assert (
        len({target.rcsb_30_cluster_line_sha256 for target in protocol.positives}) == 12
    )
    assert not {
        target.rcsb_30_cluster_line_sha256 for target in protocol.positives
    } & set(protocol.leakage_policy.m5_positive_30_cluster_line_sha256)
    assert (
        sum(target.correct_family_model_eligible for target in protocol.positives) == 11
    )


def _raw_m6_case(case_id: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "execution_status": "completed",
        "scientific_status": "candidate_evidence",
        "typed_outcome": "completed_candidate_evidence",
        "failure_class": None,
        "candidate_count": 1,
        "retained_candidate_count": 1,
        "all_candidates_retained": True,
        "selected_seed_results": [],
        "first_copy_results": [],
        "identity_decision": _identity_decision(case_id).model_dump(mode="json"),
        "edge_observations": [],
    }


def _private_family(protocol: M6BenchmarkProtocol, target_key: str) -> _M6PrivateFamily:
    target = next(item for item in protocol.positives if item.target_key == target_key)
    source = target.source_pdb_entity_id
    safe = [
        f"AF_SYNTHETIC_{target_key}_{index}"
        for index in range(1, target.allowed_30_to_70_model_count + 1)
    ]
    if target_key == "T02" and safe:
        safe[0] = "3G14_1"
    close = ("2GPJ_1",) if target_key == "T03" else ()
    cluster_30 = tuple(sorted((source, *close, *safe)))
    cluster_70 = tuple(sorted((source, *close)))
    line_30 = " ".join(cluster_30)
    line_70 = " ".join(cluster_70)
    operational = tuple(sorted(set(cluster_30) - {source}))
    leakage_safe = tuple(sorted(set(cluster_30) - set(cluster_70)))
    return _M6PrivateFamily(
        target_key=target_key,
        source_pdb_entity_id=source,
        cluster_30_line=line_30,
        cluster_70_line=line_70,
        cluster_30_line_sha256=target.rcsb_30_cluster_line_sha256,
        cluster_70_line_sha256=target.rcsb_70_cluster_line_sha256,
        cluster_30_entities=cluster_30,
        cluster_70_entities=cluster_70,
        operational_family_entities=operational,
        leakage_safe_family_entities=leakage_safe,
        frozen_allowed_30_to_70_model_count=target.allowed_30_to_70_model_count,
        observed_allowed_30_to_70_model_count=target.allowed_30_to_70_model_count,
    )


def _synthetic_collection_protocol(tmp_path: Path) -> Path:
    """Create truth-side-only cluster lines and matching frozen checksums."""

    base = load_m6_protocol(PROTOCOL)
    payload = base.model_dump(mode="json")
    lines_by_threshold: dict[int, list[str]] = {30: [], 70: []}
    for raw_target in payload["positives"]:
        target_key = raw_target["target_key"]
        family = _private_family(base, target_key)
        lines_by_threshold[30].append(family.cluster_30_line)
        lines_by_threshold[70].append(family.cluster_70_line)
        raw_target["rcsb_30_cluster_line_sha256"] = hashlib.sha256(
            f"{family.cluster_30_line}\n".encode("ascii")
        ).hexdigest()
        raw_target["rcsb_70_cluster_line_sha256"] = hashlib.sha256(
            f"{family.cluster_70_line}\n".encode("ascii")
        ).hexdigest()
    for threshold in (30, 70):
        snapshot_bytes = (
            "".join(f"{line}\n" for line in lines_by_threshold[threshold])
        ).encode("ascii")
        resource = payload["leakage_policy"][f"rcsb_{threshold}_snapshot"]
        resource["sha256"] = hashlib.sha256(snapshot_bytes).hexdigest()
        resource["size_bytes"] = len(snapshot_bytes)
    path = tmp_path / "synthetic-m6-protocol.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    (tmp_path / "execution-nextflow-v1.yaml").write_bytes(EXECUTION_POLICY.read_bytes())
    load_m6_protocol(path)
    return path


def _private_case(protocol: M6BenchmarkProtocol, case_id: str) -> _M6PrivateCaseTruth:
    case = next(item for item in protocol.cases if item.case_id == case_id)
    positive = next(
        (item for item in protocol.positives if item.target_key == case.target_key),
        None,
    )
    if positive is not None:
        digests = (positive.target_sequence_sha256,)
        source_pdb_id = positive.source.pdb_id
        expected_copy_count = positive.expected_asu_copy_count
    else:
        assumption = next(
            item
            for item in protocol.assumption_controls
            if item.target_key == case.target_key
        )
        digests = tuple(item.sequence_sha256 for item in assumption.proteins)
        source_pdb_id = assumption.source.pdb_id
        expected_copy_count = None
    return _M6PrivateCaseTruth(
        case_id=case.case_id,
        case_kind=case.case_kind,
        target_key=case.target_key,
        source_pdb_id=source_pdb_id,
        target_sequence_sha256=digests,
        target_opaque_loci={
            digest: (f"opaque_{index}",)
            for index, digest in enumerate(digests, start=1)
        },
        expected_asu_copy_count=expected_copy_count,
    )


def _measured_edge_observation(
    protocol: M6BenchmarkProtocol, case_id: str
) -> M6EdgeObservation:
    case = next(item for item in protocol.cases if item.case_id == case_id)
    kind = case.case_kind
    if kind == "missing_pdb_model":
        evidence = M6ModelExhaustionEvidence(
            evidence_kind="model_exhaustion",
            route_manifest_sha256=HASH,
            stimulus_source_hits_sha256=HASH,
            accepted_hits_sha256=HASH,
            coordinate_sources_sha256=HASH,
            processed_models_sha256=HASH,
            accepted_hit_count=0,
            coordinate_source_count=0,
            processed_model_count=0,
            hypothesis_count=0,
            route_completed=True,
        )
    elif kind in {"wrong_sds_mass", "non_top_matthews"}:
        target = next(
            item for item in protocol.positives if item.target_key == case.target_key
        )
        evidence = M6MatthewsEdgeEvidence(
            evidence_kind="matthews",
            matthews_jsonl_sha256=HASH,
            candidate_summaries=(
                M6MatthewsCandidateEvidence(
                    sequence_group_id=f"seq_{target.target_sequence_sha256}",
                    sequence_sha256=target.target_sequence_sha256,
                    sds_page_nearest_band_kda=1.0,
                    sds_page_absolute_difference_kda=100.0,
                    sds_page_fractional_difference=1.0,
                    sds_page_prior_label=(
                        "weak" if kind == "wrong_sds_mass" else "compatible"
                    ),
                    retained_hypotheses=(
                        M6RetainedMatthewsFact(
                            hypothesis_id=f"mhyp_{case.case_id}",
                            copy_count=target.expected_asu_copy_count,
                            rank_within_candidate=2,
                            physical_status="plausible",
                            matthews_prior=0.5,
                        ),
                    ),
                ),
            ),
        )
    elif kind in {
        "map_only_mtz",
        "ambiguous_columns_equivalent",
        "ambiguous_columns_conflicting",
    }:
        if kind == "map_only_mtz":
            candidates: tuple[str, ...] = ()
            selected = None
            warnings = ("no_observed_data",)
            decision = "fail"
        elif kind == "ambiguous_columns_equivalent":
            candidates = ("I,SIGI", "IMEAN,SIGIMEAN")
            selected = "I,SIGI"
            warnings = (
                "equivalent_observation_arrays",
                "observation_selection_deterministic",
            )
            decision = "pass_with_review"
        else:
            candidates = ("I,SIGI", "IMEAN,SIGIMEAN")
            selected = None
            warnings = ("ambiguous_observation_arrays",)
            decision = "fail"
        evidence = M6MtzEdgeEvidence(
            evidence_kind="mtz_preflight",
            preflight_jsonl_sha256=HASH,
            preflight_record_sha256=HASH,
            preflight_id=f"preflight_{case.case_id}",
            mtz_sha256=HASH,
            observation_candidates=candidates,
            selected_observation_labels=selected,
            warning_codes=warnings,
            decision=decision,
            available_columns=(),
        )
    elif kind == "remote_disabled":
        evidence = M6RemoteGuardEvidence(
            evidence_kind="remote_guard",
            analysis_config_sha256=HASH,
            crystal_manifest_sha256=HASH,
            provider_enabled=False,
            consent_allowed=False,
            authorisation_denied=True,
            authorisation_failure_code="run_remote_disabled",
            request_count=0,
        )
    elif kind == "remote_rate_limited":
        evidence = M6HttpRateLimitEvidence(
            evidence_kind="http_rate_limit",
            analysis_config_sha256=HASH,
            crystal_manifest_sha256=HASH,
            fault_control_sha256=HASH,
            fixture_sha256=HASH,
            provider_enabled=True,
            consent_allowed=True,
            request_count=1,
            http_status_code=429,
            retry_after_seconds=60,
        )
    elif kind == "missing_phenix":
        evidence = M6PhenixValidationEvidence(
            evidence_kind="phenix_validation",
            supplied_manifest_sha256=HASH,
            isolated_manifest_sha256=HASH,
            validation_succeeded=False,
            failure_code="environment_file_missing",
        )
    else:
        raise AssertionError(f"not an edge case: {case_id}")
    return make_edge_observation(
        case_id=case.case_id,
        edge_kind=kind,
        evidence=evidence,
    )


def test_m6_truth_join_uses_retained_rank_and_copy_evidence() -> None:
    protocol = load_m6_protocol(PROTOCOL)
    case = next(item for item in protocol.cases if item.case_id == "M6C002")
    target = next(item for item in protocol.positives if item.target_key == "T02")
    raw = _raw_m6_case(case.case_id)
    raw["selected_seed_results"] = [
        {
            "sequence_group_id": "seq_target",
            "best_supported_copy_count": target.expected_asu_copy_count,
        }
    ]
    raw["first_copy_results"] = [
        {
            "hypothesis": {
                "hypothesis_id": "mrhyp_family",
                "sequence_group_id": "seq_target",
                "model_id": "model_family",
                "priority_features": {"pdb_id": "3G14", "pdb_entity_id": 1},
            },
            "result": {},
        }
    ]
    rankings: tuple[dict[str, object], ...] = (
        {
            "case_id": case.case_id,
            "sequence_sha256": target.target_sequence_sha256,
            "sequence_group_id": "seq_target",
            "rank": 4,
            "accepted_model_hit_count": 1,
        },
    )

    assessment = _truth_assessment(
        protocol,
        case,
        raw,
        rankings,
        {target.target_key: _private_family(protocol, target.target_key)},
        {case.case_id: _private_case(protocol, case.case_id)},
    )

    assert assessment.target_sequence_rank == 4
    assert assessment.correct_family_model_retained is True
    assert assessment.credible_seed_recovered is True
    assert assessment.supported_copy_count == 2
    assert assessment.exact_identity_sequence_sha256 is None


def test_m6_truth_join_does_not_count_an_off_family_accepted_hit() -> None:
    protocol = load_m6_protocol(PROTOCOL)
    case = next(item for item in protocol.cases if item.case_id == "M6C002")
    target = next(item for item in protocol.positives if item.target_key == "T02")
    raw = _raw_m6_case(case.case_id)
    raw["first_copy_results"] = [
        {
            "hypothesis": {
                "hypothesis_id": "mrhyp_off_family",
                "sequence_group_id": "seq_target",
                "model_id": "model_off_family",
                "priority_features": {"pdb_id": "9ZZZ", "pdb_entity_id": 1},
            },
            "result": {},
        }
    ]
    rankings: tuple[dict[str, object], ...] = (
        {
            "case_id": case.case_id,
            "sequence_sha256": target.target_sequence_sha256,
            "sequence_group_id": "seq_target",
            "rank": 1,
            "accepted_model_hit_count": 99,
        },
    )

    assessment = _truth_assessment(
        protocol,
        case,
        raw,
        rankings,
        {target.target_key: _private_family(protocol, target.target_key)},
        {case.case_id: _private_case(protocol, case.case_id)},
    )

    assert assessment.correct_family_model_retained is False
    assert [item.classification for item in assessment.family_model_evidence] == [
        "off_family"
    ]


def test_m6_leakage_truth_excludes_a_close_70_percent_cluster_model() -> None:
    protocol = load_m6_protocol(PROTOCOL)
    case = next(item for item in protocol.cases if item.case_id == "M6C015")
    target = next(item for item in protocol.positives if item.target_key == "T03")
    family = _private_family(protocol, target.target_key)
    raw = _raw_m6_case(case.case_id)
    raw["first_copy_results"] = [
        {
            "hypothesis": {
                "hypothesis_id": "mrhyp_close",
                "sequence_group_id": "seq_target",
                "model_id": "model_close",
                "priority_features": {"pdb_id": "2GPJ", "pdb_entity_id": 1},
            },
            "result": {},
        }
    ]
    rankings: tuple[dict[str, object], ...] = (
        {
            "case_id": case.case_id,
            "sequence_sha256": target.target_sequence_sha256,
            "sequence_group_id": "seq_target",
            "rank": 1,
            "accepted_model_hit_count": 1,
        },
    )

    assessment = _truth_assessment(
        protocol,
        case,
        raw,
        rankings,
        {target.target_key: family},
        {case.case_id: _private_case(protocol, case.case_id)},
    )

    assert assessment.correct_family_model_retained is False
    assert [item.classification for item in assessment.family_model_evidence] == [
        "excluded_close_family"
    ]


def test_m6_truth_join_does_not_auto_accept_an_assumption_violation() -> None:
    protocol = load_m6_protocol(PROTOCOL)
    case = next(item for item in protocol.cases if item.case_id == "M6C045")
    raw = _raw_m6_case(case.case_id)
    raw["selected_seed_results"] = [
        {
            "seed_solution_id": f"seed_{case.case_id}",
            "sequence_group_id": f"seq_{HASH}",
            "best_supported_copy_count": 1,
        }
    ]
    raw["identity_decision"] = _identity_decision(case.case_id, HASH).model_dump(
        mode="json"
    )

    assessment = _truth_assessment(
        protocol,
        case,
        raw,
        (),
        {},
        {case.case_id: _private_case(protocol, case.case_id)},
    )

    assert assessment.scientific_status == "candidate_evidence"
    assert assessment.typed_outcome == "single_component_seed_on_assumption_violation"


def _synthetic_scientific_output(
    tmp_path: Path,
    *,
    adapter_version: str = "m6-scientific-run-v3",
    track: M6ScientificTrack = "operational",
    reported_identity_by_case: dict[str, str] | None = None,
    edge_observation_by_case: dict[str, M6EdgeObservation] | None = None,
    protocol_path: Path = PROTOCOL,
) -> Path:
    output = tmp_path / f"{adapter_version}-{track}"
    output.mkdir()
    case_ids = m6_track_case_ids(track)
    case_rows: list[dict[str, object]] = []
    for case_id in case_ids:
        row: dict[str, object] = {
            **_raw_m6_case(case_id),
            "candidate_ranking_path": "model-policy/candidate_ranking.jsonl",
            "model_policy_report_path": "model-policy/model_policy_report.json",
            "first_copy_attempt_count": 0,
            "additional_copy_attempt_count": 0,
            "refinement_attempt_count": 0,
            "sequence_assessment_count": 0,
            "first_copy_results": [],
            "additional_copy_results": [],
            "refinement_results": [],
            "sequence_summaries": [],
        }
        if adapter_version == "m6-nextflow-run-v2":
            row.update(
                schema_version="2.0",
                adapter_version="m6-nextflow-case-evidence-v2",
            )
            reported_digest = (reported_identity_by_case or {}).get(case_id)
            if reported_digest is not None:
                selected = {
                    "seed_solution_id": f"seed_{case_id}",
                    "sequence_group_id": f"seq_{reported_digest}",
                }
                row["selected_seed_results"] = [selected]
                row["identity_decision"] = _identity_decision(
                    case_id, reported_digest
                ).model_dump(mode="json")
            edge_observation = (edge_observation_by_case or {}).get(case_id)
            if edge_observation is not None:
                row["edge_observations"] = [edge_observation.model_dump(mode="json")]
        else:
            row.pop("identity_decision", None)
            row.pop("first_copy_results", None)
            row["first_copy_results"] = []
        case_rows.append(row)
    cases = tuple(case_rows)
    rankings = tuple(
        {
            "schema_version": (
                "2.0" if adapter_version == "m6-nextflow-run-v2" else "1.0"
            ),
            "case_id": case_id,
            "rank": 1,
            "sequence_group_id": f"seq_{case_id}",
            "sequence_sha256": HASH,
            "source_record_count": 1,
            "accepted_model_hit_count": 0,
            "rejected_model_hit_count": 0,
            "all_candidate_records_retained": True,
        }
        for case_id in case_ids
    )
    files: dict[str, str] = {
        "case_results": "m6_case_results.jsonl",
        "candidate_rankings": "m6_candidate_rankings.jsonl",
        "candidate_rankings_gzip": "m6_candidate_rankings.jsonl.gz",
        "model_policy_results": "m6_model_policy_results.jsonl",
        "first_copy_results": "m6_first_copy_results.jsonl",
        "additional_copy_results": "m6_additional_copy_results.jsonl",
        "refinement_results": "m6_refinement_results.jsonl",
        "sequence_results": "m6_sequence_results.jsonl",
        "sequence_summary": "m6_sequence_summary.jsonl",
    }
    (output / files["case_results"]).write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in cases),
        encoding="utf-8",
    )
    ranking_bytes = "".join(
        json.dumps(row, sort_keys=True) + "\n" for row in rankings
    ).encode()
    (output / files["candidate_rankings"]).write_bytes(ranking_bytes)
    (output / files["candidate_rankings_gzip"]).write_bytes(
        gzip.compress(ranking_bytes, compresslevel=9, mtime=0)
    )
    for key in (
        "model_policy_results",
        "first_copy_results",
        "additional_copy_results",
        "refinement_results",
        "sequence_results",
        "sequence_summary",
    ):
        (output / files[key]).write_text("", encoding="utf-8")
    output_sha256 = {key: sha256_file(output / value) for key, value in files.items()}
    input_sha256 = {
        "runner_manifest": "1" * 64,
        "protocol": sha256_file(protocol_path),
        "database_manifest": "3" * 64,
        "phenix_manifest": "4" * 64,
    }
    _write_json(
        output / "m6_scientific_summary.json",
        {
            "schema_version": (
                "2.0" if adapter_version == "m6-nextflow-run-v2" else "1.0"
            ),
            "adapter_version": adapter_version,
            "track": track,
            "case_ids": list(case_ids),
            "case_evidence_digest": canonical_digest(cases),
            "scientific_output_digest": canonical_digest(output_sha256),
            "input_sha256": input_sha256,
            "cache_key": canonical_digest(
                {
                    "adapter_version": adapter_version,
                    "track": track,
                    "input_sha256": input_sha256,
                }
            ),
            "outputs": output_sha256,
            "threads": 8,
            "maximum_concurrent_phenix_attempts": 4,
            "execution_model": (
                "nextflow_dsl2_slurm_fanout"
                if adapter_version in {"m6-nextflow-run-v1", "m6-nextflow-run-v2"}
                else None
            ),
            "phenix_release": "Phenix 2.1-6048",
            "first_copy_attempt_count": 0,
            "additional_copy_attempt_count": 0,
            "refinement_attempt_count": 0,
            "sequence_assessment_count": 0,
        },
    )
    return output


def test_m6_scientific_verifier_replays_complete_bounded_outputs(
    tmp_path: Path,
) -> None:
    output = _synthetic_scientific_output(tmp_path)

    report_path = verify_m6_scientific_output(output, "operational")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["deterministic_assembly_verified"] is True
    assert report["resume_load_verified"] is True
    assert report["cache_invalidation_verified"] is True
    assert report["candidate_retention_verified"] is True


def test_m6_scientific_verifier_accepts_nextflow_aggregate(tmp_path: Path) -> None:
    output = _synthetic_scientific_output(
        tmp_path, adapter_version="m6-nextflow-run-v1"
    )

    report_path = verify_m6_scientific_output(output, "operational")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["adapter_version"] == "m6-nextflow-run-v1"
    assert report["bounded_interface_verified"] is True

    with (output / "m6_case_results.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    with pytest.raises(PublicControlError, match="checksum changed"):
        verify_m6_scientific_output(output, "operational")


def _synthetic_collection(
    tmp_path: Path,
    *,
    track: M6ScientificTrack,
    adapter_version: str,
    commit: str,
    reported_identity_by_case: dict[str, str] | None = None,
    edge_observation_by_case: dict[str, M6EdgeObservation] | None = None,
    protocol_path: Path = PROTOCOL,
) -> Path:
    scientific = _synthetic_scientific_output(
        tmp_path,
        adapter_version=adapter_version,
        track=track,
        reported_identity_by_case=reported_identity_by_case,
        edge_observation_by_case=edge_observation_by_case,
        protocol_path=protocol_path,
    )
    verification = verify_m6_scientific_output(scientific, track)
    root = tmp_path / f"collection-{track}"
    qualification = root / "artifacts/qualification"
    state = root / "state"
    qualification.mkdir(parents=True)
    state.mkdir()
    for source, destination in (
        (scientific / "m6_scientific_summary.json", "m6-scientific-summary.json"),
        (verification, "m6-execution-verification.json"),
        (scientific / "m6_case_results.jsonl", "m6-case-results.jsonl"),
        (
            scientific / "m6_candidate_rankings.jsonl.gz",
            "m6-candidate-rankings.jsonl.gz",
        ),
    ):
        (qualification / destination).write_bytes(source.read_bytes())
    profile = f"m6-{track}"
    run_id = f"gtd-{profile}-20260817T000000Z-{commit[:12]}-01234567"
    _write_json(
        qualification / "m6-resume-check.json",
        {
            "deterministic_replay_equivalent": True,
            "resume_equivalent": True,
        },
    )
    nextflow = adapter_version in {"m6-nextflow-run-v1", "m6-nextflow-run-v2"}
    runtime = {
        "schema_version": "1.1" if nextflow else "1.0",
        "profile": profile,
        "track": track,
        "maximum_cpu_count": 32 if nextflow else 8,
        "maximum_memory_gb": 16.0,
        "maximum_concurrent_phenix_attempts": 3 if nextflow else 4,
        "scheduler_ceiling_hours": 24.0,
        "tool_runtime_timeouts": False,
    }
    if nextflow:
        runtime.update(
            execution_model="nextflow_dsl2_slurm_fanout",
            execution_policy="m6_nextflow_slurm_v1",
            child_job_count=1,
            peak_running_jobs=1,
            peak_aggregate_cpu_count=32,
            peak_aggregate_memory_gb=16.0,
            maximum_concurrent_phenix_attempts=0,
        )
        _write_json(
            qualification / "m6-child-resource-evidence.json",
            {
                "schema_version": "1.0",
                "execution_policy_id": "m6_nextflow_slurm_v1",
                "execution_policy_sha256": sha256_file(EXECUTION_POLICY),
                "child_job_count": 1,
                "maximum_cpu_per_job": 32,
                "maximum_memory_gb_per_job": 16.0,
                "maximum_scheduler_hours_per_job": 24.0,
                "maximum_peak_rss_gb": 8.0,
                "maximum_observed_cpu_percent": 3100.0,
                "peak_running_jobs": 1,
                "peak_aggregate_cpus": 32,
                "peak_aggregate_memory_gb": 16.0,
                "peak_concurrent_phenix_jobs": 0,
                "per_job_bounds_passed": True,
                "jobs": [
                    {
                        "process": "M6_SEARCH_FOLDSEEK",
                        "tag": "batch",
                        "status": "COMPLETED",
                        "native_job_id": "101",
                        "requested_cpus": 32,
                        "requested_memory_gb": 16.0,
                        "requested_time_hours": 24.0,
                        "start": "2026-08-17T00:00:00Z",
                        "complete": "2026-08-17T01:00:00Z",
                        "peak_rss_gb": 8.0,
                        "observed_cpu_percent": 3100.0,
                        "phenix_job": False,
                    }
                ],
            },
        )
        _write_json(
            qualification / "m6-shared-store-evidence.json",
            {
                "schema_version": "1.0",
                "eligible_processes": [
                    "M6_IMPORT_CATALOGUE",
                    "M6_SEARCH_FOLDSEEK",
                    "M6_SEARCH_PDB",
                ],
                "first_run_reuse": {},
                "resume_reuse": {
                    "M6_IMPORT_CATALOGUE": 1,
                    "M6_SEARCH_FOLDSEEK": 1,
                    "M6_SEARCH_PDB": 1,
                },
                "truthless_only": True,
                "track_specific_reuse": False,
            },
        )
    _write_json(qualification / "m6-runtime-provenance.json", runtime)
    _write_json(
        root / "manifest.json",
        {
            "run_id": run_id,
            "site_id": "viper-cpu",
            "profile": profile,
            "commit": commit,
            "nf_helper_commit": "c" * 40,
            "pixi_version": "pixi 0.76.2",
            "pixi_lock_sha256": "d" * 64,
            "database_manifest_sha256": "3" * 64,
        },
    )
    _write_json(
        state / "job-result.json",
        {
            "scheduler_state": "COMPLETED",
            "exit_code": 0,
            "failure_class": "success",
        },
    )
    (state / "failure-class").write_text("success\n", encoding="ascii")
    (state / "exit-code").write_text("0\n", encoding="ascii")
    (state / "m6-runner-archive-sha256").write_text("5" * 64, encoding="ascii")
    (state / "m6-runner-manifest-sha256").write_text("1" * 64, encoding="ascii")
    return root


def test_m6_collection_rejects_legacy_tracks_for_corrected_acceptance(
    tmp_path: Path,
) -> None:
    protocol_path = _synthetic_collection_protocol(tmp_path)
    protocol = load_m6_protocol(protocol_path)
    operational = _synthetic_collection(
        tmp_path,
        track="operational",
        adapter_version="m6-scientific-run-v3",
        commit="a" * 40,
        protocol_path=protocol_path,
    )
    leakage = _synthetic_collection(
        tmp_path,
        track="leakage",
        adapter_version="m6-nextflow-run-v1",
        commit="b" * 40,
        protocol_path=protocol_path,
    )

    with pytest.raises(PublicControlError, match="identity-bearing v2 tracks"):
        collect_m6_evidence(
            M6CollectionRequest(
                protocol=protocol_path,
                private_truth_map=_private_truth_file(
                    tmp_path, protocol_path, protocol
                ),
                operational_collection=operational,
                leakage_collection=leakage,
                output=tmp_path / "collected-evidence.json",
            )
        )


def test_m6_collection_rejects_private_truth_from_another_protocol(
    tmp_path: Path,
) -> None:
    protocol_path = _synthetic_collection_protocol(tmp_path)
    protocol = load_m6_protocol(protocol_path)
    truth = _private_truth_file(tmp_path, protocol_path, protocol)
    payload = json.loads(truth.read_text(encoding="utf-8"))
    payload["protocol_sha256"] = "f" * 64
    _write_json(truth, payload)

    with pytest.raises(PublicControlError, match="uses another protocol"):
        collect_m6_evidence(
            M6CollectionRequest(
                protocol=protocol_path,
                private_truth_map=truth,
                operational_collection=tmp_path / "not-read-operational",
                leakage_collection=tmp_path / "not-read-leakage",
                output=tmp_path / "not-written.json",
            )
        )


def test_m6_collection_rehashes_private_cluster_lines(tmp_path: Path) -> None:
    protocol_path = _synthetic_collection_protocol(tmp_path)
    protocol = load_m6_protocol(protocol_path)
    truth = _private_truth_file(tmp_path, protocol_path, protocol)
    payload = json.loads(truth.read_text(encoding="utf-8"))
    family = payload["verified_families"][0]
    family["cluster_30_line"] = " ".join(reversed(family["cluster_30_line"].split()))
    _write_json(truth, payload)

    with pytest.raises(PublicControlError, match="private family truth changed"):
        collect_m6_evidence(
            M6CollectionRequest(
                protocol=protocol_path,
                private_truth_map=truth,
                operational_collection=tmp_path / "not-read-operational",
                leakage_collection=tmp_path / "not-read-leakage",
                output=tmp_path / "not-written.json",
            )
        )


def test_m6_collection_accepts_two_identity_bearing_tracks(tmp_path: Path) -> None:
    protocol_path = _synthetic_collection_protocol(tmp_path)
    protocol = load_m6_protocol(protocol_path)
    operational = _synthetic_collection(
        tmp_path,
        track="operational",
        adapter_version="m6-nextflow-run-v2",
        commit="a" * 40,
        protocol_path=protocol_path,
    )
    leakage = _synthetic_collection(
        tmp_path,
        track="leakage",
        adapter_version="m6-nextflow-run-v2",
        commit="b" * 40,
        protocol_path=protocol_path,
    )
    truth = _private_truth_file(tmp_path, protocol_path, protocol)

    result = collect_m6_evidence(
        M6CollectionRequest(
            protocol=protocol_path,
            private_truth_map=truth,
            operational_collection=operational,
            leakage_collection=leakage,
            output=tmp_path / "collected-evidence.json",
        )
    )

    assert result.evidence.execution_policy_id == "m6_nextflow_slurm_v1"
    assert result.evidence.maximum_cpu_count == 32
    assert result.evidence.child_job_count == 2
    assert result.evidence.execution_policy_sha256 == sha256_file(EXECUTION_POLICY)
    assert result.evidence.private_truth_map_sha256 == sha256_file(truth)
    assert result.evidence.provenance.track_source_commits == {
        "operational": "a" * 40,
        "leakage": "b" * 40,
    }


def test_collect_then_evaluate_holds_on_reported_wrong_open_set_identity(
    tmp_path: Path,
) -> None:
    protocol_path = _synthetic_collection_protocol(tmp_path)
    protocol = load_m6_protocol(protocol_path)
    operational = _synthetic_collection(
        tmp_path,
        track="operational",
        adapter_version="m6-nextflow-run-v2",
        commit="a" * 40,
        reported_identity_by_case={"M6C025": HASH},
        protocol_path=protocol_path,
    )
    leakage = _synthetic_collection(
        tmp_path,
        track="leakage",
        adapter_version="m6-nextflow-run-v2",
        commit="b" * 40,
        protocol_path=protocol_path,
    )
    evidence_path = tmp_path / "collected-evidence.json"
    collect_m6_evidence(
        M6CollectionRequest(
            protocol=protocol_path,
            private_truth_map=_private_truth_file(tmp_path, protocol_path, protocol),
            operational_collection=operational,
            leakage_collection=leakage,
            output=evidence_path,
        )
    )

    result = evaluate_m6(
        M6EvaluationRequest(protocol=protocol_path, evidence=evidence_path)
    )

    assert result.accepted is False
    assert "exact_false_assignments" in result.failed_gates
    assert result.report["reported_open_set_identities"] == [
        {"case_id": "M6C025", "sequence_sha256": HASH}
    ]


def test_collect_then_evaluate_holds_when_edge_descriptor_lacks_matching_evidence(
    tmp_path: Path,
) -> None:
    protocol_path = _synthetic_collection_protocol(tmp_path)
    protocol = load_m6_protocol(protocol_path)
    case = next(item for item in protocol.cases if item.case_id == "M6C053")
    target = next(
        item for item in protocol.positives if item.target_key == case.target_key
    )
    contradictory = make_edge_observation(
        case_id=case.case_id,
        edge_kind="wrong_sds_mass",
        evidence=M6MatthewsEdgeEvidence(
            evidence_kind="matthews",
            matthews_jsonl_sha256=HASH,
            candidate_summaries=(
                M6MatthewsCandidateEvidence(
                    sequence_group_id=f"seq_{target.target_sequence_sha256}",
                    sequence_sha256=target.target_sequence_sha256,
                    sds_page_nearest_band_kda=50.0,
                    sds_page_absolute_difference_kda=1.0,
                    sds_page_fractional_difference=0.02,
                    sds_page_prior_label="compatible",
                    retained_hypotheses=(
                        M6RetainedMatthewsFact(
                            hypothesis_id="mhyp_contradictory",
                            copy_count=target.expected_asu_copy_count,
                            rank_within_candidate=1,
                            physical_status="plausible",
                            matthews_prior=0.5,
                        ),
                    ),
                ),
            ),
        ),
    )
    operational = _synthetic_collection(
        tmp_path,
        track="operational",
        adapter_version="m6-nextflow-run-v2",
        commit="a" * 40,
        protocol_path=protocol_path,
    )
    leakage = _synthetic_collection(
        tmp_path,
        track="leakage",
        adapter_version="m6-nextflow-run-v2",
        commit="b" * 40,
        edge_observation_by_case={case.case_id: contradictory},
        protocol_path=protocol_path,
    )
    evidence_path = tmp_path / "edge-evidence.json"
    collect_m6_evidence(
        M6CollectionRequest(
            protocol=protocol_path,
            private_truth_map=_private_truth_file(tmp_path, protocol_path, protocol),
            operational_collection=operational,
            leakage_collection=leakage,
            output=evidence_path,
        )
    )

    result = evaluate_m6(
        M6EvaluationRequest(protocol=protocol_path, evidence=evidence_path)
    )

    assert result.accepted is False
    assert "typed_edge_outcomes" in result.failed_gates


def test_m6_protocol_rejects_a_relabelled_case() -> None:
    payload = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    payload["cases"][0]["case_kind"] = "target_absent"
    payload["cases"][0]["expected_outcome"] = "no_exact_assignment"

    with pytest.raises(ValueError, match="63-case balance"):
        M6BenchmarkProtocol.model_validate(payload)


def test_m6_evaluator_accepts_only_complete_predeclared_evidence(
    tmp_path: Path,
) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    evidence = _evidence(protocol)
    evidence_path = tmp_path / "evidence.json"
    report_path = tmp_path / "report.json"
    _write_json(evidence_path, evidence.model_dump(mode="json"))

    result = evaluate_m6(
        M6EvaluationRequest(
            protocol=PROTOCOL,
            evidence=evidence_path,
            report=report_path,
        )
    )

    assert result.accepted is True
    assert result.failed_gates == ()
    assert result.report["release_decision"] == "accept"
    assert result.report["candidate_retention_fraction"] == 1.0
    assert result.report["exact_false_assignment_count"] == 0
    operational_metrics = cast(dict[str, object], result.report["operational_metrics"])
    leakage_metrics = cast(
        dict[str, object], result.report["leakage_controlled_metrics"]
    )
    assert operational_metrics["correct_family_denominator"] == 12
    assert leakage_metrics["correct_family_denominator"] == 11
    assert report_path.is_file()


def test_m6_evaluator_holds_on_false_assignment_and_candidate_loss(
    tmp_path: Path,
) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    payload = _evidence(protocol).model_dump(mode="json")
    absent = next(
        item for item in payload["assessments"] if item["case_id"] == "M6C025"
    )
    absent["runner_identity_decision"] = _identity_decision("M6C025", HASH).model_dump(
        mode="json"
    )
    absent["exact_identity_sequence_sha256"] = HASH
    absent["retained_candidate_count"] = 2
    absent["all_candidates_retained"] = False
    evidence_path = tmp_path / "evidence.json"
    _write_json(evidence_path, payload)

    result = evaluate_m6(M6EvaluationRequest(protocol=PROTOCOL, evidence=evidence_path))

    assert result.accepted is False
    assert "candidate_retention" in result.failed_gates
    assert "exact_false_assignments" in result.failed_gates
    assert result.report["reported_open_set_identities"] == [
        {"case_id": "M6C025", "sequence_sha256": HASH}
    ]


def test_m6_evaluator_holds_on_an_unexpected_execution_failure(
    tmp_path: Path,
) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    payload = _evidence(protocol).model_dump(mode="json")
    failed = next(
        item for item in payload["assessments"] if item["case_id"] == "M6C025"
    )
    failed["execution_status"] = "failed"
    failed["failure_class"] = "candidate_adapter_failure"
    evidence_path = tmp_path / "evidence.json"
    _write_json(evidence_path, payload)

    result = evaluate_m6(M6EvaluationRequest(protocol=PROTOCOL, evidence=evidence_path))

    assert result.accepted is False
    assert "unexpected_execution_failures" in result.failed_gates


def test_m6_evaluator_binds_the_nextflow_execution_policy(tmp_path: Path) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    payload = _evidence(protocol).model_dump(mode="json")
    payload.update(
        maximum_cpu_count=32,
        execution_policy_id="m6_nextflow_slurm_v1",
        execution_policy_sha256=sha256_file(EXECUTION_POLICY),
        child_job_count=1,
    )
    evidence_path = tmp_path / "evidence.json"
    _write_json(evidence_path, payload)
    accepted = evaluate_m6(
        M6EvaluationRequest(protocol=PROTOCOL, evidence=evidence_path)
    )
    assert accepted.accepted is True

    payload["execution_policy_sha256"] = "0" * 64
    _write_json(evidence_path, payload)
    held = evaluate_m6(M6EvaluationRequest(protocol=PROTOCOL, evidence=evidence_path))
    assert held.accepted is False
    assert "execution_policy_verified" in held.failed_gates


def test_m6_evaluator_holds_on_forbidden_family_attempts(tmp_path: Path) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    payload = _evidence(protocol).model_dump(mode="json")
    operational = next(
        item for item in payload["assessments"] if item["case_id"] == "M6C001"
    )
    leakage = next(
        item for item in payload["assessments"] if item["case_id"] == "M6C013"
    )
    operational["correct_family_model_retained"] = False
    operational["family_model_evidence"] = [
        {
            "hypothesis_id": "hyp_exact",
            "model_id": "model_exact",
            "pdb_id": "8GKV",
            "pdb_entity_id": 1,
            "classification": "exact_deposition",
        }
    ]
    leakage["correct_family_model_retained"] = False
    leakage["family_model_evidence"] = [
        {
            "hypothesis_id": "hyp_close",
            "model_id": "model_close",
            "pdb_id": "2GPJ",
            "pdb_entity_id": 1,
            "classification": "excluded_close_family",
        }
    ]
    evidence_path = tmp_path / "forbidden-family-evidence.json"
    _write_json(evidence_path, payload)

    result = evaluate_m6(M6EvaluationRequest(protocol=PROTOCOL, evidence=evidence_path))

    assert "no_exact_deposition_models_attempted" in result.failed_gates
    assert "no_leakage_close_models_attempted" in result.failed_gates


def _prepared_manifest(
    tmp_path: Path,
    protocol: M6BenchmarkProtocol,
    *,
    candidate_policy: str = "retain_all",
) -> Path:
    catalogue = tmp_path / "catalogue.fa"
    reflections = tmp_path / "reflections.mtz"
    config = tmp_path / "config.json"
    policy = tmp_path / "policy.json"
    catalogue.write_text(f">loc_{'a' * 64}\nACDEFGHIK\n", encoding="ascii")
    write_m6_mtz_variant(
        _m6_source_mtz(),
        reflections,
        opaque_id="M6C001",
        variation="ordinary",
    )
    _write_json(
        config,
        {
            "schema_version": "1.0",
            "prototype": {
                "asu_model": "single_protein_species_multi_copy",
                "profile": "pilot",
            },
            "catalogue": {
                "min_length_aa": 30,
                "ambiguous_residue_policy": "warn",
                "remove_terminal_stop": True,
            },
            "providers": {
                "pdb_sequence": {"enabled": True, "max_hits": 3},
                "foldseek_prostt5_pdb": {"enabled": True, "max_hits": 3},
                "esm_atlas": {
                    "enabled": False,
                    "max_hits": 2,
                    "requests_per_minute": 10,
                    "max_sequence_length": 1500,
                },
                "afdb_exact": {"enabled": False, "max_hits": 1},
            },
            "matthews": {
                "min_copy_count": 1,
                "max_copy_count": 16,
                "max_hypotheses_per_candidate": 4,
                "min_solvent_fraction": 0.1,
                "max_solvent_fraction": 0.9,
                "reference_backend": "phenix_xtriage",
            },
            "search_limits": {
                "max_structural_hypotheses": 100,
                "max_first_copy_jobs": 25,
                "max_refinement_finalists": 10,
                "max_sequence_map_finalists": 5,
                "max_concurrent_mr_jobs": 4,
            },
            "review": {
                "primary_shortlist_size": 10,
                "extended_shortlist_size": 25,
                "require_mr_seed_checkpoint": True,
                "require_sequence_checkpoint": True,
            },
            "retention": {
                "max_full_artifact_finalists": 25,
                "retain_all_logs": True,
                "retain_all_normalised_results": True,
            },
        },
    )
    _write_json(
        policy,
        {
            "mode": "operational",
            "candidate_policy": candidate_policy,
            "score_policy": "llg_tfz_annotations_only",
        },
    )
    objects = []
    for role, path, media_type in (
        ("catalogue", catalogue, "text/x-fasta"),
        ("reflections", reflections, "application/x-mtz"),
        ("analysis_config", config, "application/json"),
        ("model_policy", policy, "application/json"),
    ):
        objects.append(
            {
                "role": role,
                "path": str(path),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
                "media_type": media_type,
            }
        )
    manifest = tmp_path / "preparation.json"
    _write_json(
        manifest,
        {
            "schema_version": "1.0",
            "protocol_id": protocol.protocol_id,
            "protocol_sha256": sha256_file(PROTOCOL),
            "cases": [
                {"case_id": case.case_id, "objects": objects} for case in protocol.cases
            ],
        },
    )
    return manifest


def test_m6_runner_bundle_is_truth_isolated_and_deterministic(
    tmp_path: Path,
) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    preparation = _prepared_manifest(tmp_path, protocol)

    first = build_m6_runner_bundle(
        M6RunnerBundleRequest(
            protocol=PROTOCOL,
            preparation_manifest=preparation,
            output_directory=tmp_path / "runner-one",
            archive=tmp_path / "runner-one.tar",
        )
    )
    second = build_m6_runner_bundle(
        M6RunnerBundleRequest(
            protocol=PROTOCOL,
            preparation_manifest=preparation,
            output_directory=tmp_path / "runner-two",
            archive=tmp_path / "runner-two.tar",
        )
    )

    assert first.case_count == 63
    assert first.object_count == 4
    assert first.archive_sha256 == second.archive_sha256
    manifest_text = first.runner_manifest.read_text(encoding="utf-8")
    assert "8GKV" not in manifest_text
    assert "NP_414916.1" not in manifest_text
    assert "expected_asu_copy_count" not in manifest_text


def test_m6_nextflow_plan_emits_case_and_unique_catalogue_tasks(
    tmp_path: Path,
) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    preparation = _prepared_manifest(tmp_path, protocol)
    bundle = build_m6_runner_bundle(
        M6RunnerBundleRequest(
            protocol=PROTOCOL,
            preparation_manifest=preparation,
            output_directory=tmp_path / "runner",
            archive=tmp_path / "runner.tar",
        )
    )

    plan = plan_m6_nextflow_track(
        M6TrackPlanRequest(
            runner_root=bundle.runner_manifest.parent,
            database_manifest=ROOT / "tests/fixtures/stubs/database_manifest.json",
            software_lock=ROOT / "pixi.lock",
            track="operational",
            output_directory=tmp_path / "plan",
        )
    )

    assert plan.case_task_count == 36
    assert plan.catalogue_task_count == 1
    assert len(plan.case_tasks_tsv.read_text(encoding="utf-8").splitlines()) == 37
    assert (plan.plan_directory / "case_tasks/M6C001/reflections.mtz").is_file()


def _nextflow_catalogue_task(
    tmp_path: Path,
    name: str,
    sequences: tuple[str, ...],
) -> Path:
    task_root = tmp_path / name
    task_root.mkdir()
    catalogue = task_root / "catalogue.faa"
    catalogue.write_text(
        "".join(
            f">loc_{index:064x}\n{sequence}\n"
            for index, sequence in enumerate(sequences, start=1)
        ),
        encoding="ascii",
    )
    config = task_root / "analysis_config.json"
    config.write_text(
        json.dumps(
            yaml.safe_load((ROOT / "examples/config.yaml").read_text(encoding="utf-8"))
        ),
        encoding="utf-8",
    )
    catalogue_key = canonical_digest(
        {
            "catalogue": sha256_file(catalogue),
            "config": sha256_file(config),
        }
    )
    task = M6CatalogueTask(
        schema_version="1.0",
        catalogue_key=catalogue_key,
        catalogue_sha256=sha256_file(catalogue),
        analysis_config_sha256=sha256_file(config),
        software_lock_sha256=sha256_file(ROOT / "pixi.lock"),
        import_cache_key=canonical_digest({"catalogue_key": catalogue_key}),
    )
    _write_json(task_root / "task.json", task.model_dump(mode="json"))
    return task_root


def test_m6_search_batching_deduplicates_across_catalogues(tmp_path: Path) -> None:
    first_task = _nextflow_catalogue_task(
        tmp_path,
        "first-task",
        ("A" * 50, "C" * 50),
    )
    second_task = _nextflow_catalogue_task(
        tmp_path,
        "second-task",
        ("A" * 50, "D" * 50),
    )
    first = run_m6_catalogue_task(
        first_task, ROOT / "pixi.lock", tmp_path / "first-bundle"
    )
    second = run_m6_catalogue_task(
        second_task, ROOT / "pixi.lock", tmp_path / "second-bundle"
    )

    output = build_m6_search_batches(
        (first, second),
        ROOT / "tests/fixtures/stubs/database_manifest.json",
        EXECUTION_POLICY,
        ROOT / "pixi.lock",
        tmp_path / "batches",
    )
    manifest = json.loads((output / "batch_plan.json").read_text(encoding="utf-8"))

    assert manifest["catalogue_count"] == 2
    assert manifest["catalogue_record_count"] == 4
    assert manifest["unique_sequence_count"] == 3
    assert manifest["unique_residue_count"] == 150
    assert manifest["pdb_batch_count"] == 1
    assert manifest["foldseek_batch_count"] == 1
    assert manifest["pdb_threads"] == 32
    assert manifest["foldseek_threads"] == 32
    first_batch_task = next((output / "prostt5_foldseek_batches").glob("*/task.json"))
    first_batch = json.loads(first_batch_task.read_text(encoding="utf-8"))
    changed_database = tmp_path / "changed-database.json"
    database_payload = json.loads(
        (ROOT / "tests/fixtures/stubs/database_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    database_payload["manifest_id"] = "dbm_changed"
    _write_json(changed_database, database_payload)
    changed = build_m6_search_batches(
        (first, second),
        changed_database,
        EXECUTION_POLICY,
        ROOT / "pixi.lock",
        tmp_path / "changed-batches",
    )
    changed_batch = json.loads(
        next((changed / "prostt5_foldseek_batches").glob("*/task.json")).read_text(
            encoding="utf-8"
        )
    )
    assert changed_batch["batch_id"] == first_batch["batch_id"]
    assert changed_batch["search_cache_key"] != first_batch["search_cache_key"]

    changed_lock = tmp_path / "pixi.lock"
    changed_lock.write_bytes((ROOT / "pixi.lock").read_bytes() + b"\n")
    changed_software = build_m6_search_batches(
        (first, second),
        ROOT / "tests/fixtures/stubs/database_manifest.json",
        EXECUTION_POLICY,
        changed_lock,
        tmp_path / "changed-software-batches",
    )
    changed_software_batch = json.loads(
        next(
            (changed_software / "prostt5_foldseek_batches").glob("*/task.json")
        ).read_text(encoding="utf-8")
    )
    assert changed_software_batch["batch_id"] == first_batch["batch_id"]
    assert changed_software_batch["search_cache_key"] != first_batch["search_cache_key"]


def test_m6_execution_policy_and_trace_use_per_job_bounds(tmp_path: Path) -> None:
    policy = load_m6_execution_policy(EXECUTION_POLICY)
    trace = tmp_path / "trace.tsv"
    trace.write_text(
        "process\ttag\tstatus\tnative_id\tcpus\tmemory\ttime\tstart\tcomplete\tpeak_rss\t%cpu\n"
        "M6_SEARCH_FOLDSEEK\tb1\tCOMPLETED\t101\t32\t16 GB\t1d\t"
        "2026-08-17T00:00:00+00:00\t2026-08-17T01:00:00+00:00\t8 GB\t3100%\n"
        "M6_FIRST_COPY\th1\tCOMPLETED\t102\t2\t4 GB\t24h\t"
        "2026-08-17T00:30:00+00:00\t2026-08-17T00:45:00+00:00\t0\t190%\n",
        encoding="utf-8",
    )

    evidence = collect_m6_resource_evidence(
        M6ResourceEvidenceRequest(
            policy=EXECUTION_POLICY,
            trace=trace,
            output=tmp_path / "resource-evidence.json",
        )
    )

    assert policy.per_job.maximum_cpus == 32
    assert policy.search_batching.mmseqs2.cpus == 32
    assert policy.search_batching.foldseek.cpus == 32
    assert evidence.per_job_bounds_passed is True
    assert evidence.child_job_count == 2
    assert evidence.peak_running_jobs == 2
    assert evidence.peak_aggregate_cpus == 34
    assert evidence.peak_concurrent_phenix_jobs == 1
    assert evidence.maximum_scheduler_hours_per_job == 24.0
    assert evidence.maximum_peak_rss_gb == 8.0
    assert evidence.jobs[1].peak_rss_gb == 0.0
    assert evidence.maximum_observed_cpu_percent == 3100.0


def test_m6_runner_verifier_checks_opaque_media_and_policy(tmp_path: Path) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    preparation = _prepared_manifest(tmp_path, protocol)
    bundle = build_m6_runner_bundle(
        M6RunnerBundleRequest(
            protocol=PROTOCOL,
            preparation_manifest=preparation,
            output_directory=tmp_path / "runner",
            archive=tmp_path / "runner.tar",
        )
    )

    result = verify_m6_runner_bundle(
        M6RunnerVerificationRequest(
            runner_root=bundle.runner_manifest.parent,
            output=tmp_path / "qualification.json",
        )
    )

    report = json.loads(result.qualification.read_text(encoding="utf-8"))
    assert result.case_count == 63
    assert result.object_count == 4
    assert report["all_candidates_retained"] is True
    assert report["case_records"][0]["selected_observation_labels"] == "FP,SIGFP"


def test_m6_scientific_runner_materialises_typed_opaque_objects(
    tmp_path: Path,
) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    preparation = _prepared_manifest(tmp_path, protocol)
    bundle = build_m6_runner_bundle(
        M6RunnerBundleRequest(
            protocol=PROTOCOL,
            preparation_manifest=preparation,
            output_directory=tmp_path / "runner",
            archive=tmp_path / "runner.tar",
        )
    )
    plan = plan_m6_nextflow_track(
        M6TrackPlanRequest(
            runner_root=bundle.runner_manifest.parent,
            database_manifest=ROOT / "tests/fixtures/stubs/database_manifest.json",
            software_lock=ROOT / "pixi.lock",
            track="operational",
            output_directory=tmp_path / "materialised-inputs",
        )
    )

    case_root = plan.plan_directory / "case_tasks/M6C001"
    catalogue_root = next(
        path for path in (plan.plan_directory / "catalogue_tasks").iterdir()
    )
    assert (case_root / "analysis_config.json").is_file()
    assert (case_root / "model_policy.json").is_file()
    assert (case_root / "reflections.mtz").is_file()
    assert (catalogue_root / "catalogue.faa").is_file()


def test_m6_nextflow_early_case_retains_catalogue_and_assembles(
    tmp_path: Path,
) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    preparation = _prepared_manifest(tmp_path, protocol)
    bundle = build_m6_runner_bundle(
        M6RunnerBundleRequest(
            protocol=PROTOCOL,
            preparation_manifest=preparation,
            output_directory=tmp_path / "runner",
            archive=tmp_path / "runner.tar",
        )
    )
    plan = plan_m6_nextflow_track(
        M6TrackPlanRequest(
            runner_root=bundle.runner_manifest.parent,
            database_manifest=ROOT / "tests/fixtures/stubs/database_manifest.json",
            software_lock=ROOT / "pixi.lock",
            track="leakage",
            output_directory=tmp_path / "plan",
        )
    )
    catalogue_task = next(
        path for path in (plan.plan_directory / "catalogue_tasks").iterdir()
    )
    catalogue = run_m6_catalogue_task(
        catalogue_task,
        ROOT / "pixi.lock",
        tmp_path / "catalogue",
    )
    case_task = plan.plan_directory / "case_tasks/M6C057"
    reflections = case_task / "reflections.mtz"
    write_m6_mtz_variant(
        _m6_source_mtz(),
        reflections,
        opaque_id="M6C057",
        variation="map_only",
    )
    fault = case_task / "fault_control.json"
    _write_json(
        fault,
        {"edge_stimulus": "map_only_mtz", "reflection_mode": "map_only"},
    )
    task_record = json.loads((case_task / "task.json").read_text(encoding="utf-8"))
    task_record["fault_control_sha256"] = sha256_file(fault)
    task_record["reflections_sha256"] = sha256_file(reflections)
    _write_json(case_task / "task.json", task_record)
    preflight = run_m6_preflight_task(
        case_task,
        ROOT / "tests/fixtures/stubs/phenix_install_manifest.json",
        tmp_path / "preflight",
    )
    case = run_m6_prepare_case_task(
        case_task,
        preflight,
        catalogue,
        None,
        ROOT / "tests/fixtures/stubs/database_manifest.json",
        tmp_path / "case",
    )
    assert (case / "all_sequence_groups.jsonl").is_file()
    assert (case / "all_source_records.jsonl").is_file()
    group = M6HypothesisGroupTask.model_validate_json(
        (case / "case_plan.json").read_text(encoding="utf-8")
    )
    assert group.early_outcome == "completed_map_only_mtz"
    assert group.hypothesis_count == 0

    seeds = run_m6_empty_seeds_task(case, tmp_path / "seeds")
    finalists = run_m6_empty_finalists_task(case, seeds, tmp_path / "finalists")
    evidence = run_m6_assemble_case_task(
        case,
        finalists,
        (),
        tmp_path / "evidence",
    )
    record = M6CaseEvidence.model_validate_json(
        (evidence / "case_record.json").read_text(encoding="utf-8")
    )
    assert record.typed_outcome == "completed_map_only_mtz"
    assert record.candidate_count == record.retained_candidate_count
    assert record.candidate_count > 0


def test_m6_runner_verifier_rejects_changed_object(tmp_path: Path) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    preparation = _prepared_manifest(tmp_path, protocol)
    bundle = build_m6_runner_bundle(
        M6RunnerBundleRequest(
            protocol=PROTOCOL,
            preparation_manifest=preparation,
            output_directory=tmp_path / "runner",
            archive=tmp_path / "runner.tar",
        )
    )
    manifest = json.loads(bundle.runner_manifest.read_text(encoding="utf-8"))
    object_path = (
        bundle.runner_manifest.parent / "objects" / next(iter(manifest["objects"]))
    )
    object_path.chmod(0o644)
    object_path.write_bytes(object_path.read_bytes() + b"changed")

    with pytest.raises(PublicControlError, match="size changed"):
        verify_m6_runner_bundle(
            M6RunnerVerificationRequest(
                runner_root=bundle.runner_manifest.parent,
                output=tmp_path / "qualification.json",
            )
        )


def test_m6_runner_verifier_rejects_candidate_deletion_policy(
    tmp_path: Path,
) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    preparation = _prepared_manifest(
        tmp_path,
        protocol,
        candidate_policy="delete_low_score",
    )
    bundle = build_m6_runner_bundle(
        M6RunnerBundleRequest(
            protocol=PROTOCOL,
            preparation_manifest=preparation,
            output_directory=tmp_path / "runner",
            archive=tmp_path / "runner.tar",
        )
    )

    with pytest.raises(PublicControlError, match="retain every candidate"):
        verify_m6_runner_bundle(
            M6RunnerVerificationRequest(
                runner_root=bundle.runner_manifest.parent,
                output=tmp_path / "qualification.json",
            )
        )


def test_m6_runner_bundle_rejects_truth_bearing_input(tmp_path: Path) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    preparation = _prepared_manifest(tmp_path, protocol)
    payload = json.loads(preparation.read_text(encoding="utf-8"))
    truth_config = tmp_path / "truth-config.json"
    truth_config.write_text('{"target":"8GKV"}\n', encoding="ascii")
    replacement = {
        "role": "analysis_config",
        "path": str(truth_config),
        "sha256": sha256_file(truth_config),
        "size_bytes": truth_config.stat().st_size,
        "media_type": "application/json",
    }
    for case in payload["cases"]:
        case["objects"] = [
            replacement if item["role"] == "analysis_config" else item
            for item in case["objects"]
        ]
    _write_json(preparation, payload)

    with pytest.raises(PublicControlError, match="truth-isolation failure"):
        build_m6_runner_bundle(
            M6RunnerBundleRequest(
                protocol=PROTOCOL,
                preparation_manifest=preparation,
                output_directory=tmp_path / "runner",
                archive=tmp_path / "runner.tar",
            )
        )


def test_m6_catalogue_anonymisation_removes_and_duplicates_exact_sequence(
    tmp_path: Path,
) -> None:
    target_sequence = "ACDEFGHIK"
    target_digest = sequence_digest(target_sequence)
    records = (
        SeqRecord(
            Seq(target_sequence),
            id="NP_414916.1",
            description="NP_414916.1 truth-bearing source header",
        ),
        SeqRecord(Seq("LMNPQRSTV"), id="WP_000000001.1", description="other"),
    )

    absent, _ = anonymise_m6_catalogue(records, remove_sequence_sha256=target_digest)
    duplicated, _ = anonymise_m6_catalogue(
        records,
        duplicate_sequence_sha256=target_digest,
        duplicate_case_id="M6C049",
    )
    output = tmp_path / "catalogue.faa"
    _write_opaque_catalogue(output, duplicated)

    assert all(record.sequence_sha256 != target_digest for record in absent)
    assert sum(record.sequence_sha256 == target_digest for record in duplicated) == 2
    assert "NP_414916.1" not in output.read_text(encoding="ascii")
    assert all(record.opaque_id.startswith("loc_") for record in duplicated)


def _policy_group(sequence: str) -> SequenceGroupRecord:
    digest = sequence_digest(sequence)
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=500.0,
        mass_method="test",
        residue_policy="test",
        source_record_count=1,
    )


def _policy_hit(
    group: SequenceGroupRecord,
    *,
    hit_id: str,
    provider: str,
    pdb_id: str,
    target_sha256: str,
    identity: float,
    coverage: float,
) -> StructuralSearchHit:
    return StructuralSearchHit(
        schema_version="1.0",
        hit_id=hit_id,
        sequence_group_id=group.sequence_group_id,
        provider=provider,
        provider_rank=1,
        target_id=f"{pdb_id.lower()}_A",
        model_key=f"pdb:{pdb_id}:legacy_seqres_suffix:A",
        target_chain_or_entity="A",
        pdb_id=pdb_id,
        identifier_namespace="legacy_seqres_suffix",
        query_start=1,
        query_end=len(group.sequence),
        target_start=1,
        target_end=len(group.sequence),
        aligned_length=len(group.sequence),
        query_coverage=coverage,
        target_coverage=coverage,
        sequence_identity=identity,
        evalue=1.0e-10,
        bits=50.0,
        database_id=(
            "db_pdb_sequences"
            if provider == "pdb_sequence_mmseqs"
            else "db_pdb_foldseek"
        ),
        raw_result_pointer="raw/results.tsv",
        raw_metrics={
            "target_sequence_length": len(group.sequence),
            "target_sequence_sha256": target_sha256,
        },
        eligibility_status=EligibilityStatus.SELECTED,
        eligibility_reason="test proposal",
    )


def test_m6_model_policy_filters_every_route_and_retains_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _policy_group("ACDE")
    second = _policy_group("FGHI")
    groups = tmp_path / "groups.jsonl"
    groups.write_text(
        "".join(f"{canonical_json_text(item)}\n" for item in (first, second)),
        encoding="utf-8",
    )
    sources = tmp_path / "sources.jsonl"
    sources.write_text(
        "".join(
            f"{canonical_json_text(item)}\n"
            for item in (
                SourceProteinRecord(
                    schema_version="1.0",
                    source_record_id="src_first",
                    catalogue_id="opaque",
                    original_protein_id="loc_first",
                    original_header="loc_first",
                    sequence_group_id=first.sequence_group_id,
                    source_annotation_provider="test",
                ),
                SourceProteinRecord(
                    schema_version="1.0",
                    source_record_id="src_second",
                    catalogue_id="opaque",
                    original_protein_id="loc_second",
                    original_header="loc_second",
                    sequence_group_id=second.sequence_group_id,
                    source_annotation_provider="test",
                ),
            )
        ),
        encoding="utf-8",
    )
    safe_source_sha256 = "b" * 64
    direct_hits = (
        _policy_hit(
            first,
            hit_id="hit_exact_deposition",
            provider="pdb_sequence_mmseqs",
            pdb_id="8GKV",
            target_sha256=first.sha256,
            identity=1.0,
            coverage=1.0,
        ),
        _policy_hit(
            first,
            hit_id="hit_leaking_model",
            provider="pdb_sequence_mmseqs",
            pdb_id="2ABC",
            target_sha256="c" * 64,
            identity=0.8,
            coverage=0.9,
        ),
        _policy_hit(
            first,
            hit_id="hit_safe_model",
            provider="pdb_sequence_mmseqs",
            pdb_id="1ABC",
            target_sha256=safe_source_sha256,
            identity=0.5,
            coverage=1.0,
        ),
    )
    foldseek_hits = (
        _policy_hit(
            first,
            hit_id="hit_foldseek_qualified",
            provider="foldseek_prostt5_pdb",
            pdb_id="3ABC",
            target_sha256=safe_source_sha256,
            identity=0.2,
            coverage=0.7,
        ),
        _policy_hit(
            second,
            hit_id="hit_foldseek_unqualified",
            provider="foldseek_prostt5_pdb",
            pdb_id="4ABC",
            target_sha256="d" * 64,
            identity=0.2,
            coverage=0.7,
        ),
        _policy_hit(
            second,
            hit_id="hit_foldseek_unmapped",
            provider="foldseek_prostt5_pdb",
            pdb_id="5ABC",
            target_sha256="e" * 64,
            identity=0.2,
            coverage=0.7,
        ).model_copy(
            update={
                "raw_metrics": {"coordinate_mapping_status": "unavailable"},
                "eligibility_status": EligibilityStatus.DEFERRED,
                "eligibility_reason": "retained unmapped test proposal",
            }
        ),
    )
    pdb_hits = tmp_path / "pdb.jsonl"
    pdb_hits.write_text(
        "".join(f"{canonical_json_text(item)}\n" for item in direct_hits),
        encoding="utf-8",
    )
    foldseek_path = tmp_path / "foldseek.jsonl"
    foldseek_path.write_text(
        "".join(f"{canonical_json_text(item)}\n" for item in foldseek_hits),
        encoding="utf-8",
    )
    policy = tmp_path / "policy.json"
    _write_json(
        policy,
        {
            "schema_version": "1.0",
            "mode": "query_relative_leakage",
            "maximum_model_identity_fraction": 0.7,
            "minimum_exclusion_coverage_fraction": 0.8,
            "exact_deposition_removed_by_trusted_transition": True,
            "applies_to_all_model_routes": True,
            "retain_rejected_model_annotations": True,
            "candidate_policy": "retain_all",
            "score_policy": "llg_tfz_annotations_only",
        },
    )
    database = tmp_path / "database.json"
    database.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        m6_model_policy_module,
        "_mmseqs_version",
        lambda _path: ("18.8cc5c", "db_pdb_sequences"),
    )

    output = apply_m6_model_policy(
        M6ModelPolicyRequest(
            protocol=PROTOCOL,
            case_id="M6C013",
            model_policy=policy,
            database_manifest=database,
            sequence_groups_jsonl=groups,
            source_records_jsonl=sources,
            pdb_hits_jsonl=pdb_hits,
            prostt5_hits_jsonl=foldseek_path,
            output_directory=tmp_path / "output",
        )
    )

    assert {hit.hit_id for hit in output.accepted_hits} == {
        "hit_safe_model",
        "hit_foldseek_qualified",
    }
    foldseek = next(
        hit for hit in output.accepted_hits if hit.hit_id == "hit_foldseek_qualified"
    )
    assert foldseek.sequence_identity == pytest.approx(0.5)
    report = json.loads(output.report_json.read_text(encoding="utf-8"))
    assert report["candidate_count"] == 2
    assert report["retained_candidate_count"] == 2
    assert report["all_candidates_retained"] is True
    assert report["rejection_reason_counts"] == {
        "amino_acid_alignment_unavailable": 1,
        "coordinate_mapping_unavailable": 1,
        "exact_deposited_coordinates": 1,
        "query_relative_leakage": 1,
    }
    ranking = [
        json.loads(line)
        for line in output.candidate_ranking_jsonl.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert [row["sequence_group_id"] for row in ranking] == [
        first.sequence_group_id,
        second.sequence_group_id,
    ]


def _m6_source_mtz() -> gemmi.Mtz:
    mtz = gemmi.Mtz(with_base=True)
    mtz.spacegroup = gemmi.find_spacegroup_by_name("P 21 21 21")
    mtz.set_cell_for_all(gemmi.UnitCell(50, 60, 70, 90, 90, 90))
    mtz.add_dataset("8GKV truth-bearing dataset")
    for label, column_type in (
        ("FreeR_flag", "I"),
        ("FP", "F"),
        ("SIGFP", "Q"),
        ("FWT", "F"),
        ("PHWT", "P"),
    ):
        mtz.add_column(label, column_type)
    rows = np.asarray(
        [
            [index, 1, 1, 0, index * 10, index, index * 8, index * 5]
            for index in range(1, 11)
        ],
        dtype=np.float32,
    )
    mtz.set_data(rows)
    mtz.update_reso()
    return mtz


@pytest.mark.parametrize(
    ("variation", "expected_labels", "warning"),
    (
        ("ordinary", "FP,SIGFP", None),
        ("map_only", None, "no_observed_data"),
        (
            "equivalent_observation_arrays",
            "FX,SIGFX",
            "equivalent_observation_arrays",
        ),
        (
            "conflicting_observation_arrays",
            None,
            "ambiguous_observation_arrays",
        ),
    ),
)
def test_m6_mtz_variants_are_sanitised_and_typed(
    tmp_path: Path,
    variation: M6MtzVariation,
    expected_labels: str | None,
    warning: str | None,
) -> None:
    output = tmp_path / f"{variation}.mtz"
    write_m6_mtz_variant(
        _m6_source_mtz(),
        output,
        opaque_id="M6C057",
        variation=variation,
    )

    mtz = gemmi.read_mtz_file(str(output))
    selected, _, warnings = select_observations(mtz, None)
    assert (None if selected is None else selected.rendered) == expected_labels
    assert warning is None or warning in warnings
    assert "8GKV" not in mtz.title
    assert all("8GKV" not in item.dataset_name for item in mtz.datasets)
