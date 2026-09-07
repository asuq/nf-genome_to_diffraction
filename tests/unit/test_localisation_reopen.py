"""Tests for zero-pack-only reopening of retained localisation exclusions."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_digest, canonical_json_text
from genome_to_diffraction.localisation import (
    BatchLocalisationReopenRequest,
    BatchLocalisationReopenStatus,
    import_catalogue_localisation_batch,
    plan_batch_localisation_reopen,
)
from genome_to_diffraction.mr_resources import build_mr_resource_plan
from genome_to_diffraction.review.phase3_package import (
    PhaseIIIReviewEvidenceSource,
    PhaseIIIReviewPackageRequest,
    build_phase3_review_package,
)
from genome_to_diffraction.review.phase3_stage import (
    OwnedPhaseIIIParentRun,
    PhaseIIIReviewStageError,
    PhaseIIIReviewStageRequest,
    stage_phase3_review_decisions,
)
from genome_to_diffraction.schemas.manifests import PrototypeProfile
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    NormalisedMrResult,
)
from genome_to_diffraction.schemas.v2.review import (
    PhaseIIIReopenRequest,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecision,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
)
from genome_to_diffraction.status import ExecutionStatus
from tests.unit.test_localisation_batch import _inputs


def _case(
    tmp_path: Path,
    *,
    status: ExecutionStatus,
    packed: bool,
    crystal_id: str = "crystal_reopen",
) -> tuple[BatchLocalisationReopenRequest, str]:
    policy_root = tmp_path / "policy"
    policy_root.mkdir()
    imported = import_catalogue_localisation_batch(_inputs(policy_root))
    policy = imported.policy
    active_group = next(
        row.sequence_group_id
        for row in policy.group_evidence
        if row.first_wave_disposition.value == "active"
    )
    excluded_group = policy.retained_excluded_group_ids[0]
    funnel = tmp_path / "funnel"
    funnel.mkdir()
    active = MrHypothesis(
        schema_version="1.0",
        hypothesis_id="mrhyp_active",
        crystal_id=crystal_id,
        sequence_group_id=active_group,
        model_id="model_active",
        copy_count_expected=1,
        copy_number_to_search=1,
        space_group="P 1",
        obs_labels="F,SIGF",
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.SMOKE,
        priority_features={
            "localisation_wave_disposition": "active",
            "initial_admission_eligible": True,
            "matthews_physical_status": "plausible",
        },
        status=MrHypothesisStatus.QUEUED,
    )
    deferred = active.model_copy(
        update={
            "hypothesis_id": "mrhyp_deferred",
            "sequence_group_id": excluded_group,
            "model_id": "model_deferred",
            "priority_features": {
                "initial_admission_eligible": True,
                "matthews_physical_status": "review",
                "localisation_wave_disposition": "excluded",
                "localisation_first_wave_reason": (
                    "retained_excluded_requires_reopening_authority"
                ),
            },
            "status": MrHypothesisStatus.SKIPPED,
        }
    )
    active_path = funnel / "mr_hypotheses.jsonl"
    (funnel / "deferred_cap_hypotheses.jsonl").write_text("", encoding="utf-8")
    deferred_path = funnel / "deferred_localisation_hypotheses.jsonl"
    active_path.write_text(f"{canonical_json_text(active)}\n", encoding="utf-8")
    deferred_path.write_text(
        f"{canonical_json_text(deferred)}\n",
        encoding="utf-8",
    )
    complete_path = funnel / "complete_acquired_hypotheses.jsonl"
    complete_path.write_text(active_path.read_text() + deferred_path.read_text())
    resource_plan_path = funnel / "mr_resource_plans.jsonl"
    resource_plan_path.write_text(
        "".join(
            canonical_json_text(
                {
                    "hypothesis_id": hypothesis.hypothesis_id,
                    "resource_plan": build_mr_resource_plan(
                        owner_kind="mr_hypothesis",
                        owner_id=hypothesis.hypothesis_id,
                        reflection_count=1_000,
                        moving_atom_count=100,
                        searched_copy_count=1,
                        fixed_atom_count=0,
                        symmetry_multiplicity=1,
                    ).model_dump(mode="json"),
                }
            )
            + "\n"
            for hypothesis in (active, deferred)
        ),
        encoding="utf-8",
    )
    (funnel / "funnel_manifest.json").write_text(
        json.dumps(
            {
                "adapter_version": (
                    "multi-source-first-copy-funnel-v8-reviewed-alternatives"
                ),
                "localisation_policy_id": policy.policy_id,
                "mr_resource_plan_adapter": (
                    "phase3-mr-resource-allocation-v2-overprovisioned"
                ),
                "mr_resource_plan_count": 2,
                "mr_resource_plans_sha256": sha256_file(resource_plan_path),
                "complete_acquired_hypothesis_count": 2,
                "complete_acquired_hypotheses_sha256": sha256_file(complete_path),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result_directory = tmp_path / "result"
    result_directory.mkdir()
    result = NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=active.hypothesis_id,
        tool_version="Phaser test",
        execution_status=status,
        placed_copy_count=1 if status is ExecutionStatus.COMPLETED_HIT else 0,
        packing_summary={"top_solution_packed": packed},
        solution_coordinate_path="PHASER.1.pdb"
        if status is ExecutionStatus.COMPLETED_HIT
        else None,
        solution_coordinate_sha256="a" * 64
        if status is ExecutionStatus.COMPLETED_HIT
        else None,
        raw_log_pointer="PHASER.log",
    )
    (result_directory / "normalised_mr_result.json").write_text(
        f"{canonical_json_text(result)}\n",
        encoding="utf-8",
    )
    return (
        BatchLocalisationReopenRequest(
            funnel_directory=funnel,
            result_directories=(result_directory,),
            localisation_bundle=imported.output_directory,
            maximum_reopened_attempts=175,
            output_directory=tmp_path / "reopen",
        ),
        deferred.hypothesis_id,
    )


def test_complete_zero_pack_reopens_retained_exclusion(tmp_path: Path) -> None:
    request, source_id = _case(
        tmp_path,
        status=ExecutionStatus.COMPLETED_NO_HIT,
        packed=False,
    )

    output = plan_batch_localisation_reopen(request)

    assert output.plan.status is BatchLocalisationReopenStatus.READY
    assert output.plan.source_hypothesis_ids == (source_id,)
    reopened = MrHypothesis.model_validate_json(
        output.hypotheses_jsonl.read_text(encoding="utf-8")
    )
    assert reopened.status is MrHypothesisStatus.QUEUED
    assert reopened.hypothesis_id != source_id
    assert reopened.priority_features["localisation_reopened_after_zero_pack"] is True


def test_no_a_expansion_prioritises_initial_cap_before_localisation_exclusion(
    tmp_path: Path,
) -> None:
    request, excluded_source_id = _case(
        tmp_path,
        status=ExecutionStatus.COMPLETED_NO_HIT,
        packed=False,
    )
    active = MrHypothesis.model_validate_json(
        (request.funnel_directory / "mr_hypotheses.jsonl").read_text()
    )
    cap_deferred = active.model_copy(
        update={
            "hypothesis_id": "mrhyp_cap_deferred",
            "priority_features": {
                **active.priority_features,
                "first_copy_execution_disposition": (
                    "deferred_initial_25_cap_requires_reopening_authority"
                ),
            },
            "status": MrHypothesisStatus.SKIPPED,
        }
    )
    (request.funnel_directory / "deferred_cap_hypotheses.jsonl").write_text(
        f"{canonical_json_text(cap_deferred)}\n",
        encoding="utf-8",
    )
    resource_path = request.funnel_directory / "mr_resource_plans.jsonl"
    resource_path.write_text(
        resource_path.read_text()
        + canonical_json_text(
            {
                "hypothesis_id": cap_deferred.hypothesis_id,
                "resource_plan": build_mr_resource_plan(
                    owner_kind="mr_hypothesis",
                    owner_id=cap_deferred.hypothesis_id,
                    reflection_count=1_000,
                    moving_atom_count=100,
                    searched_copy_count=1,
                    fixed_atom_count=0,
                    symmetry_multiplicity=1,
                ).model_dump(mode="json"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = request.funnel_directory / "funnel_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["mr_resource_plan_count"] = 3
    manifest["mr_resource_plans_sha256"] = sha256_file(resource_path)
    complete_path = request.funnel_directory / "complete_acquired_hypotheses.jsonl"
    complete_path.write_text(
        complete_path.read_text() + canonical_json_text(cap_deferred) + "\n"
    )
    manifest["complete_acquired_hypothesis_count"] = 3
    manifest["complete_acquired_hypotheses_sha256"] = sha256_file(complete_path)
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    output = plan_batch_localisation_reopen(request)
    reopened = tuple(
        MrHypothesis.model_validate_json(line)
        for line in output.hypotheses_jsonl.read_text().splitlines()
        if line
    )

    assert output.plan.source_hypothesis_ids == (
        cap_deferred.hypothesis_id,
        excluded_source_id,
    )
    assert [item.priority_features["source_deferred_wave"] for item in reopened] == [
        "initial_25_cap",
        "localisation_excluded",
    ]


@pytest.mark.parametrize(
    ("status", "packed", "expected"),
    (
        (
            ExecutionStatus.COMPLETED_HIT,
            True,
            BatchLocalisationReopenStatus.NOT_REQUIRED_PACKED,
        ),
        (
            ExecutionStatus.FAILED_PARSE,
            False,
            BatchLocalisationReopenStatus.BLOCKED_INCOMPLETE,
        ),
    ),
)
def test_packed_or_failed_first_wave_does_not_reopen(
    tmp_path: Path,
    status: ExecutionStatus,
    packed: bool,
    expected: BatchLocalisationReopenStatus,
) -> None:
    request, _ = _case(tmp_path, status=status, packed=packed)

    output = plan_batch_localisation_reopen(request)

    assert output.plan.status is expected
    assert output.plan.reopened_hypothesis_count == 0
    assert output.hypotheses_jsonl.read_bytes() == b""


def _reviewed_request(
    request: BatchLocalisationReopenRequest,
    selected_ids: tuple[str, ...],
    *,
    parent_run_id: str = "test_parent",
    execution_identity_id: str = "phase3exec_" + "a" * 64,
    parent_profile: str = "known-control",
) -> BatchLocalisationReopenRequest:
    created = datetime(2026, 9, 7, tzinfo=UTC)
    crystal_id = MrHypothesis.model_validate_json(
        (request.funnel_directory / "mr_hypotheses.jsonl").read_text()
    ).crystal_id
    (request.output_directory.parent / "owned_review").mkdir()
    native_sources = []
    review_items = []
    for index, result_directory in enumerate(request.result_directories):
        result = NormalisedMrResult.model_validate_json(
            (result_directory / "normalised_mr_result.json").read_text()
        )
        result_name = f"normalised_mr_result_{index}.json"
        (request.funnel_directory / result_name).write_text(result.model_dump_json())
        native_sources.append(
            PhaseIIIReviewEvidenceSource(f"mr_result_{index}", result_name)
        )
        review_items.append(
            {
                "hypothesis_id": result.hypothesis_id,
                "solution_identity": {"result_sha256": canonical_digest(result)},
                "copied_assets": {"normalised_result": result_name},
            }
        )
    (request.funnel_directory / "mr_seed_review_manifest.json").write_text(
        json.dumps({"items": review_items})
    )
    package = build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            owned_parent_run_id=parent_run_id,
            parent_profile=parent_profile,
            parent_phase="phase3-pass1",
            execution_identity_id=execution_identity_id,
            crystal_id=crystal_id,
            target_item_ids=("solution_active",),
            created_at=created,
            input_root=request.funnel_directory,
            evidence_sources=(
                PhaseIIIReviewEvidenceSource(
                    "complete_acquired_hypotheses", "complete_acquired_hypotheses.jsonl"
                ),
                PhaseIIIReviewEvidenceSource(
                    "source_funnel_manifest", "funnel_manifest.json"
                ),
                PhaseIIIReviewEvidenceSource(
                    "mr_seed_review_manifest", "mr_seed_review_manifest.json"
                ),
                *native_sources,
            ),
            output_directory=request.output_directory.parent / "owned_review",
        )
    )
    decisions = PhaseIIIReviewDecisionFile.from_content(
        checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
        owned_parent_run_id=parent_run_id,
        review_package_id=package.review_package_id,
        review_package_manifest_sha256=sha256_file(package.manifest),
        decisions=(
            PhaseIIIReviewDecision(
                crystal_id=crystal_id,
                item_id="solution_active",
                decision=PhaseIIIReviewDecisionValue.REJECT,
                reviewer="reviewer",
                reviewed_at=created + timedelta(minutes=5),
                reason="Reject this A placement and inspect alternative copy states.",
            ),
        ),
        reopen_request=PhaseIIIReopenRequest(
            selected_hypothesis_ids=selected_ids, maximum_reopened_attempts=1
        ),
    )
    decision_path = request.output_directory.parent / "decisions.json"
    decision_path.write_text(decisions.model_dump_json())
    stage = stage_phase3_review_decisions(
        PhaseIIIReviewStageRequest(
            parent=OwnedPhaseIIIParentRun(
                parent_run_id, parent_profile, "phase3-pass1"
            ),
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            review_package_manifest=package.manifest,
            decisions=decision_path,
            confirmed_decisions_sha256=sha256_file(decision_path),
            output_directory=request.output_directory.parent / "stage",
        )
    )
    return replace(
        request,
        review_package_manifest=package.manifest,
        review_decisions=stage.canonical_decision,
        maximum_reopened_attempts=1,
    )


@pytest.mark.parametrize("failed", (False, True))
def test_reviewed_zero_prior_alternative_can_reopen_after_rejection(
    tmp_path: Path,
    failed: bool,
) -> None:
    request, source_id = _case(
        tmp_path,
        status=ExecutionStatus.FAILED_TOOL_EXECUTION
        if failed
        else ExecutionStatus.COMPLETED_HIT,
        packed=not failed,
    )
    deferred_path = request.funnel_directory / "deferred_localisation_hypotheses.jsonl"
    deferred = MrHypothesis.model_validate_json(deferred_path.read_text())
    deferred = deferred.model_copy(
        update={
            "copy_count_expected": 11,
            "priority_features": {
                **deferred.priority_features,
                "initial_admission_eligible": False,
                "matthews_prior": 0.0,
                "solvent_fraction": 0.01,
            },
        }
    )
    deferred_path.write_text(canonical_json_text(deferred) + "\n")
    complete_path = request.funnel_directory / "complete_acquired_hypotheses.jsonl"
    complete_path.write_text(
        (request.funnel_directory / "mr_hypotheses.jsonl").read_text()
        + deferred_path.read_text()
    )
    manifest_path = request.funnel_directory / "funnel_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["complete_acquired_hypotheses_sha256"] = sha256_file(complete_path)
    manifest_path.write_text(json.dumps(manifest))
    reviewed = _reviewed_request(request, (source_id,))
    output = plan_batch_localisation_reopen(reviewed)
    if failed:
        assert output.plan.status is BatchLocalisationReopenStatus.BLOCKED_INCOMPLETE
        assert output.hypotheses_jsonl.read_text() == ""
    else:
        assert output.plan.status is BatchLocalisationReopenStatus.READY_REVIEWED
        reopened = MrHypothesis.model_validate_json(output.hypotheses_jsonl.read_text())
        assert reopened.priority_features["matthews_prior"] == 0.0
        assert (
            reopened.copy_count_expected == 11 and reopened.copy_number_to_search == 1
        )
        assert output.plan.source_hypothesis_ids == (source_id,)
        assert (
            output.plan_json.parent / "review_stage" / "phase3_review_decision.json"
        ).is_file()


@pytest.mark.parametrize("selected_id", ("absent_hypothesis", "mrhyp_active"))
def test_reviewed_reopen_rejects_absent_or_already_executed_selection(
    tmp_path: Path,
    selected_id: str,
) -> None:
    request, _ = _case(tmp_path, status=ExecutionStatus.COMPLETED_HIT, packed=True)
    with pytest.raises(PhaseIIIReviewStageError, match="absent, already executed"):
        _reviewed_request(request, (selected_id,))


def test_reviewed_reopen_rejects_stale_funnel_and_attempt_limit(tmp_path: Path) -> None:
    request, source_id = _case(
        tmp_path, status=ExecutionStatus.COMPLETED_HIT, packed=True
    )
    reviewed = _reviewed_request(request, (source_id,))
    with pytest.raises(ValueError, match="explicit attempt limit"):
        PhaseIIIReopenRequest(
            selected_hypothesis_ids=("a", "b"), maximum_reopened_attempts=1
        )
    from genome_to_diffraction.localisation.reopen_batch import (
        BatchLocalisationReopenError,
    )

    with pytest.raises(BatchLocalisationReopenError, match="attempt limit differs"):
        plan_batch_localisation_reopen(replace(reviewed, maximum_reopened_attempts=2))
    manifest_path = request.funnel_directory / "funnel_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["unreviewed_change"] = True
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(PhaseIIIReviewStageError, match="source funnel differs"):
        plan_batch_localisation_reopen(reviewed)


def test_reviewed_reopen_refuses_substituted_native_results(tmp_path: Path) -> None:
    request, source_id = _case(
        tmp_path, status=ExecutionStatus.COMPLETED_HIT, packed=True
    )
    reviewed = _reviewed_request(request, (source_id,))
    result_path = request.result_directories[0] / "normalised_mr_result.json"
    result = NormalisedMrResult.model_validate_json(result_path.read_text())
    result_path.write_text(result.model_copy(update={"llg": 122.0}).model_dump_json())
    with pytest.raises(
        PhaseIIIReviewStageError, match="native terminal results differ"
    ):
        plan_batch_localisation_reopen(reviewed)
