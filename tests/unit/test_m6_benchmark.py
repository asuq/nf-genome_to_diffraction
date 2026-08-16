"""Focused contracts for the approved truth-isolated M6 benchmark."""

import json
from pathlib import Path

import gemmi
import numpy as np
import pytest
import yaml
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from genome_to_diffraction.benchmarks.m6_evaluation import (
    M6CaseAssessment,
    M6CollectedEvidence,
    M6EvaluationRequest,
    M6SoftwareProvenance,
    evaluate_m6,
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
from genome_to_diffraction.benchmarks.m6_verification import (
    M6RunnerVerificationRequest,
    verify_m6_runner_bundle,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.diffraction.preflight import select_observations
from genome_to_diffraction.ids import sequence_digest

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
