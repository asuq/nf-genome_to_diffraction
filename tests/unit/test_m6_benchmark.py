"""Focused contracts for the approved truth-isolated M6 benchmark."""

import json
from pathlib import Path

import pytest
import yaml

from genome_to_diffraction.benchmarks.m6_evaluation import (
    M6CaseAssessment,
    M6CollectedEvidence,
    M6EvaluationRequest,
    M6SoftwareProvenance,
    evaluate_m6,
)
from genome_to_diffraction.benchmarks.m6_protocol import (
    M6BenchmarkProtocol,
    load_m6_protocol,
)
from genome_to_diffraction.benchmarks.m6_runner import (
    M6RunnerBundleRequest,
    build_m6_runner_bundle,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import sha256_file

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
    assert (
        len({target.rcsb_30_cluster_line_sha256 for target in protocol.positives}) == 12
    )
    assert not {
        target.rcsb_30_cluster_line_sha256 for target in protocol.positives
    } & set(protocol.leakage_policy.m5_positive_30_cluster_line_sha256)
    assert (
        sum(target.correct_family_model_eligible for target in protocol.positives) == 11
    )


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


def _prepared_manifest(tmp_path: Path, protocol: M6BenchmarkProtocol) -> Path:
    catalogue = tmp_path / "catalogue.fa"
    reflections = tmp_path / "reflections.mtz"
    config = tmp_path / "config.json"
    catalogue.write_text(">seq_opaque\nACDEFGHIK\n", encoding="ascii")
    reflections.write_bytes(b"MTZ synthetic opaque fixture\n")
    config.write_text('{"mode":"analysis"}\n', encoding="ascii")
    objects = []
    for role, path, media_type in (
        ("catalogue", catalogue, "text/x-fasta"),
        ("reflections", reflections, "application/x-mtz"),
        ("analysis_config", config, "application/json"),
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
    assert first.object_count == 3
    assert first.archive_sha256 == second.archive_sha256
    manifest_text = first.runner_manifest.read_text(encoding="utf-8")
    assert "8GKV" not in manifest_text
    assert "NP_414916.1" not in manifest_text
    assert "expected_asu_copy_count" not in manifest_text


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
