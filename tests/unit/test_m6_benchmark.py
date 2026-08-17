"""Focused contracts for the approved truth-isolated M6 benchmark."""

import gzip
import json
from pathlib import Path

import gemmi
import numpy as np
import pytest
import yaml
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from genome_to_diffraction.benchmarks import m6_model_policy as m6_model_policy_module
from genome_to_diffraction.benchmarks.m6_collection import (
    _assessment as _truth_assessment,
)
from genome_to_diffraction.benchmarks.m6_evaluation import (
    M6CaseAssessment,
    M6CollectedEvidence,
    M6EvaluationRequest,
    M6SoftwareProvenance,
    evaluate_m6,
)
from genome_to_diffraction.benchmarks.m6_model_policy import (
    M6ModelPolicyRequest,
    apply_m6_model_policy,
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
HASH = "a" * 64


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
    }
    if case.case_kind in {"operational_positive", "leakage_positive"}:
        assert target is not None
        common.update(
            scientific_status="candidate_evidence",
            typed_outcome="target_evidence_retained",
            target_sequence_rank=1,
            correct_family_model_retained=True,
            credible_seed_recovered=True,
            supported_copy_count=target.expected_asu_copy_count,
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
        schema_version="1.0",
        protocol_id=protocol.protocol_id,
        protocol_sha256=sha256_file(PROTOCOL),
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
    }


def test_m6_truth_join_uses_retained_rank_and_copy_evidence() -> None:
    protocol = load_m6_protocol(PROTOCOL)
    case = next(item for item in protocol.cases if item.case_id == "M6C001")
    target = next(item for item in protocol.positives if item.target_key == "T01")
    raw = _raw_m6_case(case.case_id)
    raw["selected_seed_results"] = [
        {
            "sequence_group_id": "seq_target",
            "best_supported_copy_count": target.expected_asu_copy_count,
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

    assessment = _truth_assessment(protocol, case, raw, rankings)

    assert assessment.target_sequence_rank == 4
    assert assessment.correct_family_model_retained is True
    assert assessment.credible_seed_recovered is True
    assert assessment.supported_copy_count == 2
    assert assessment.exact_identity_sequence_sha256 is None


def test_m6_truth_join_does_not_auto_accept_an_assumption_violation() -> None:
    protocol = load_m6_protocol(PROTOCOL)
    case = next(item for item in protocol.cases if item.case_id == "M6C045")
    raw = _raw_m6_case(case.case_id)
    raw["selected_seed_results"] = [
        {"sequence_group_id": "seq_component", "best_supported_copy_count": 1}
    ]

    assessment = _truth_assessment(protocol, case, raw, ())

    assert assessment.scientific_status == "candidate_evidence"
    assert assessment.typed_outcome == "single_component_seed_on_assumption_violation"


def _synthetic_scientific_output(tmp_path: Path) -> Path:
    output = tmp_path / "scientific-output"
    output.mkdir()
    case_ids = m6_track_case_ids("operational")
    cases = tuple(
        {
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
        for case_id in case_ids
    )
    rankings = tuple(
        {
            "schema_version": "1.0",
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
        "protocol": "2" * 64,
        "database_manifest": "3" * 64,
        "phenix_manifest": "4" * 64,
    }
    _write_json(
        output / "m6_scientific_summary.json",
        {
            "schema_version": "1.0",
            "adapter_version": "m6-scientific-run-v1",
            "track": "operational",
            "case_ids": list(case_ids),
            "case_evidence_digest": canonical_digest(cases),
            "scientific_output_digest": canonical_digest(output_sha256),
            "input_sha256": input_sha256,
            "cache_key": canonical_digest(
                {
                    "adapter_version": "m6-scientific-run-v1",
                    "track": "operational",
                    "input_sha256": input_sha256,
                }
            ),
            "outputs": output_sha256,
            "threads": 8,
            "maximum_concurrent_phenix_attempts": 4,
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

    with (output / "m6_case_results.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    with pytest.raises(PublicControlError, match="checksum changed"):
        verify_m6_scientific_output(output, "operational")


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
    assert report_path.is_file()


def test_m6_evaluator_holds_on_false_assignment_and_candidate_loss(
    tmp_path: Path,
) -> None:
    protocol = load_m6_protocol(PROTOCOL)
    payload = _evidence(protocol).model_dump(mode="json")
    absent = next(
        item for item in payload["assessments"] if item["case_id"] == "M6C025"
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
