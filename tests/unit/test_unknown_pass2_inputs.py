"""Focused tests for the fixed RG7-closed pass-2 archive."""

import hashlib
import tarfile
from pathlib import Path

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.execution.finding_closure import (
    FindingDisposition,
    PhaseIIIFindingClosureEntry,
    PhaseIIIFindingClosureRecord,
)
from genome_to_diffraction.hpc.unknown_pass2_inputs import (
    PASS2_SPEC_RELATIVE,
    BatchLocalisationReopenPlan,
    BatchLocalisationReopenStatus,
    build_unknown_pass2_input_bundle,
    validate_unknown_pass2_input_tree,
)
from genome_to_diffraction.schemas.manifests import PrototypeProfile
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
)
from genome_to_diffraction.schemas.v2 import (
    ExecutionArtifactIdentity,
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecisionValue,
    UnknownPass1CrystalAssessment,
    UnknownPass1ReviewEvidence,
)
from genome_to_diffraction.status import ExecutionStatus
from tests.support.unknown_pass1_fixture import (
    materialise_unknown_pass1_public_fixture,
)

CRYSTAL = "AD4QS1P4G2_18"


def _write(path: Path, payload: str = "{}\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


def _closure(root: Path, identity: PhaseIIIExecutionIdentity) -> dict[str, str]:
    ledger = _write(
        root / "finding_ledger.md",
        "| Finding | Disposition | Evidence |\n"
        "| --- | --- | --- |\n"
        "| `FCB-P0-01` | Fixed | test |\n",
    )
    evidence = {}
    for name in (
        "adverse_review",
        "integration_gate",
        "known_control",
        "m6",
        "unknown_pass1",
    ):
        evidence[name] = _write(root / f"{name}.json", f'{{"kind":"{name}"}}\n')
    ci = root / "ci.json"
    atomic_write_json(
        ci,
        {
            "schema_version": "1.0",
            "run_id": 123,
            "job_id": 456,
            "head_sha": identity.source_commit,
            "conclusion": "success",
        },
    )
    closure = PhaseIIIFindingClosureRecord.from_content(
        source_commit=identity.source_commit,
        source_tree=identity.source_tree,
        ledger_sha256=sha256_file(ledger),
        adverse_review_sha256=sha256_file(evidence["adverse_review"]),
        integration_gate_sha256=sha256_file(evidence["integration_gate"]),
        known_control_evidence_sha256=sha256_file(evidence["known_control"]),
        m6_evidence_sha256=sha256_file(evidence["m6"]),
        unknown_pass1_evidence_sha256=sha256_file(evidence["unknown_pass1"]),
        exact_source_ci_evidence_sha256=sha256_file(ci),
        exact_source_ci_run_id=123,
        exact_source_ci_job_id=456,
        exact_source_ci_status="success",
        entries=(
            PhaseIIIFindingClosureEntry(
                finding_id="FCB-P0-01",
                disposition=FindingDisposition.FIXED,
                regression_ids=("tests/unit/test_unknown_pass2_inputs.py",),
                evidence_ids=("synthetic-complete-gate",),
            ),
        ),
    )
    closure_path = root / "finding_closure.json"
    atomic_write_json(closure_path, closure.model_dump(mode="json"))
    return {
        "finding_closure": closure_path.name,
        "finding_ledger": ledger.name,
        "adverse_review_evidence": evidence["adverse_review"].name,
        "integration_gate_evidence": evidence["integration_gate"].name,
        "known_control_evidence": evidence["known_control"].name,
        "m6_evidence": evidence["m6"].name,
        "unknown_pass1_evidence": evidence["unknown_pass1"].name,
        "exact_source_ci_evidence": ci.name,
    }


def test_pass2_archive_round_trip_accepts_one_no_a_crystal(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    root = tmp_path / "authority"
    root.mkdir()
    base_root = tmp_path / "base"
    base_root.mkdir()
    base_fixture = materialise_unknown_pass1_public_fixture(base_root)
    base = PhaseIIIExecutionIdentity.model_validate_json(
        base_fixture.execution_identity.read_bytes()
    )
    mtz = _write(root / "input.mtz", "synthetic MTZ\n")
    mtz_sha = sha256_file(mtz)
    values = base.model_dump(mode="python")
    values.pop("execution_identity_id")
    values["crystal_artifacts"] = (
        ExecutionArtifactIdentity.from_content(
            scope="crystal",
            owner_id=CRYSTAL,
            role="mtz",
            sha256=mtz_sha,
            size_bytes=mtz.stat().st_size,
            release_or_source="synthetic pass-2 MTZ",
        ),
    )
    identity = PhaseIIIExecutionIdentity.from_content(**values)
    identity_path = root / "execution_identity.json"
    atomic_write_json(identity_path, identity.model_dump(mode="json"))
    review = UnknownPass1ReviewEvidence(
        checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        package_crystal_id=CRYSTAL,
        package_item_id=f"{CRYSTAL}_review",
        review_package_id=f"phase3reviewpkg_{'1' * 64}",
        review_package_manifest_sha256="2" * 64,
        decision_crystal_id=CRYSTAL,
        decision_item_id=f"{CRYSTAL}_review",
        decision_file_id=f"phase3review_{'3' * 64}",
        decision_file_sha256="4" * 64,
        decision=PhaseIIIReviewDecisionValue.PROCEED,
    )
    assessment = UnknownPass1CrystalAssessment.from_evidence(
        adapter_version="unknown-pass1-terminal-assessment-v2",
        owned_parent_run_id="gtd-unknown-single-component-parent",
        execution_identity_id=identity.execution_identity_id,
        crystal_id=CRYSTAL,
        crystallographic_review_item_id=f"{CRYSTAL}_review",
        execution_status=ExecutionStatus.COMPLETED_NO_HIT,
        terminal_evidence_sha256="5" * 64,
        candidate_shortlist_present=False,
        review_evidence=(review,),
    )
    assessment_path = root / "pass1_assessment.json"
    atomic_write_json(assessment_path, assessment.model_dump(mode="json"))
    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=f"mrhyp_{'6' * 64}",
        crystal_id=CRYSTAL,
        sequence_group_id=f"seq_{'7' * 64}",
        model_id="model_reopened",
        copy_count_expected=1,
        copy_number_to_search=1,
        space_group="P 1",
        obs_labels="F,SIGF",
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.SMOKE,
        priority_features={"no_a_expansion_after_zero_pack": True},
        status=MrHypothesisStatus.QUEUED,
    )
    plan_root = root / "no_a_plan"
    plan_root.mkdir()
    plan = BatchLocalisationReopenPlan.from_content(
        localisation_policy_id="localisation_policy",
        funnel_manifest_sha256="8" * 64,
        active_hypotheses_sha256="9" * 64,
        deferred_cap_hypotheses_sha256="a" * 64,
        deferred_localisation_hypotheses_sha256="b" * 64,
        deferred_hypotheses_sha256="c" * 64,
        terminal_results_sha256="d" * 64,
        active_hypothesis_count=25,
        terminal_result_count=25,
        failed_or_incomplete_count=0,
        packed_result_count=0,
        cap_deferred_hypothesis_count=1,
        localisation_deferred_hypothesis_count=0,
        deferred_hypothesis_count=1,
        maximum_reopened_attempts=175,
        reopened_hypothesis_count=1,
        remaining_deferred_count=0,
        status=BatchLocalisationReopenStatus.READY,
        source_hypothesis_ids=("source_hypothesis",),
        reopened_hypothesis_ids=(hypothesis.hypothesis_id,),
    )
    atomic_write_json(
        plan_root / "localisation_reopen_plan.json",
        plan.model_dump(mode="json"),
    )
    _write(
        plan_root / "reopened_hypotheses.jsonl",
        f"{hypothesis.model_dump_json()}\n",
    )
    _write(root / "parent_states.jsonl", "")
    fixed = root / "fixed"
    fixed.mkdir()
    _write(fixed / "retained.txt", "retained\n")
    item_files = {
        "sequence_groups": _write(root / "sequence_groups.jsonl"),
        "localisation_policy": _write(root / "localisation_policy.json"),
        "active_wave_completion": _write(root / "active_wave_completion.json"),
        "localisation_reopen_plan": _write(root / "localisation_reopen_plan.json"),
        "gel_evidence": _write(root / "gel_evidence.json"),
        "preflight": _write(root / "preflight.jsonl"),
        "model_registry": _write(root / "all_model_registry.json"),
        "model_ranking_evidence": _write(root / "model_ranking.jsonl", ""),
        "diffraction_selection": _write(root / "diffraction_selection.json"),
        "free_r_identity": _write(root / "free_r_identity.json"),
        "phenix_manifest": _write(root / "phenix_manifest.json"),
        "source_records": _write(root / "source_records.jsonl"),
        "matthews": _write(root / "matthews.jsonl"),
        "pipeline_config": _write(
            root / "pipeline_config.yaml",
            "schema_version: '1.0'\n",
        ),
    }
    source = {
        "schema_version": "1.0",
        **_closure(root, identity),
        "items": [
            {
                "crystal_id": CRYSTAL,
                "mode": "no_a_expansion",
                "pass1_assessment": assessment_path.name,
                "no_a_expansion_plan": plan_root.name,
                "parent_states": "parent_states.jsonl",
                **{name: path.name for name, path in item_files.items()},
                "fixed_coordinate_root": fixed.name,
                "execution_identity": identity_path.name,
                "mtz": mtz.name,
            }
        ],
    }
    source_path = root / "phase3_pass2_source.json"
    atomic_write_json(source_path, source)
    spec = repository / PASS2_SPEC_RELATIVE
    spec.parent.mkdir(parents=True)
    atomic_write_json(
        spec,
        {
            "schema_version": "1.0",
            "input_root": str(root),
            "source_manifest_sha256": sha256_file(source_path),
        },
    )
    spec.chmod(0o600)

    bundle = build_unknown_pass2_input_bundle(
        repository=repository,
        archive_path=tmp_path / "pass2.tar",
    )
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(bundle.archive_path, mode="r:") as archive:
        archive.extractall(extracted, filter="data")
    validated = validate_unknown_pass2_input_tree(
        extracted,
        expected_input_id=bundle.input_id,
    )

    assert validated.input_id == bundle.input_id
    assert validated.crystal_ids == (CRYSTAL,)
    assert validated.finding_closure_id == bundle.finding_closure_id
    assert (
        bundle.archive_sha256
        == hashlib.sha256(bundle.archive_path.read_bytes()).hexdigest()
    )
