"""Tests for zero-pack-only reopening of retained localisation exclusions."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.localisation import (
    BatchLocalisationReopenRequest,
    BatchLocalisationReopenStatus,
    import_catalogue_localisation_batch,
    plan_batch_localisation_reopen,
)
from genome_to_diffraction.schemas.manifests import PrototypeProfile
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    NormalisedMrResult,
)
from genome_to_diffraction.status import ExecutionStatus
from tests.unit.test_localisation_batch import _inputs


def _case(
    tmp_path: Path,
    *,
    status: ExecutionStatus,
    packed: bool,
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
        crystal_id="crystal_reopen",
        sequence_group_id=active_group,
        model_id="model_active",
        copy_count_expected=1,
        copy_number_to_search=1,
        space_group="P 1",
        obs_labels="F,SIGF",
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.SMOKE,
        priority_features={"localisation_wave_disposition": "active"},
        status=MrHypothesisStatus.QUEUED,
    )
    deferred = active.model_copy(
        update={
            "hypothesis_id": "mrhyp_deferred",
            "sequence_group_id": excluded_group,
            "model_id": "model_deferred",
            "priority_features": {
                "localisation_wave_disposition": "excluded",
                "localisation_first_wave_reason": (
                    "retained_excluded_reopen_only_after_complete_zero_pack"
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
    (funnel / "diverse_first_copy_funnel_manifest.json").write_text(
        json.dumps(
            {
                "adapter_version": (
                    "multi-source-first-copy-funnel-v4-phase3-evidence"
                ),
                "localisation_policy_id": policy.policy_id,
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
                    "deferred_initial_25_cap_reopen_only_after_complete_zero_pack"
                ),
            },
            "status": MrHypothesisStatus.SKIPPED,
        }
    )
    (request.funnel_directory / "deferred_cap_hypotheses.jsonl").write_text(
        f"{canonical_json_text(cap_deferred)}\n",
        encoding="utf-8",
    )

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
