"""Per-arm conservation over real receipt validation and simulated Phenix."""

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.m6_advancement import validate_m6_advancement
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.status import ExecutionStatus
from tests.fixtures.ranking_four_arm_copy import run_reference_copy_task
from tests.fixtures.ranking_four_arm_reference import AdmissionPrior
from tests.fixtures.ranking_four_arm_stages import (
    ReferenceCopyEvidence,
    ReferencePairedStages,
    build_reference_stage_inventory,
)
from tests.unit.test_add_copy_phaser import NO_SOLUTION_LOG, _fake_runtime
from tests.unit.test_ranking_four_arm_advancement import (
    _copy_request,
    _inputs,
    _unexpected_phenix,
)


@pytest.mark.parametrize("prior", ("copy_weighted", "solvent_density"))
def test_reference_stages_conserve_individual_caps_and_authenticated_union(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prior: AdmissionPrior
) -> None:
    admission, hypotheses, path, manifest = _inputs(tmp_path, monkeypatch, prior)
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)
    evidence: list[ReferenceCopyEvidence] = []
    for seed in manifest.recommended:
        request = replace(
            _copy_request(
                tmp_path,
                admission,
                hypotheses,
                manifest,
                seed_solution_id=seed.solution_id,
            ),
            output_directory=tmp_path / "copies" / seed.solution_id,
        )
        root = run_reference_copy_task(request, admission, advancement_manifest=path)
        evidence.append(ReferenceCopyEvidence(request, root))
    stages = build_reference_stage_inventory(
        admission,
        hypotheses_jsonl=hypotheses,
        advancement_manifest=path,
        copy_evidence=tuple(evidence),
    )
    assert ReferencePairedStages.model_validate_json(stages.model_dump_json()) == stages
    assert stages.advancement_manifest_sha256 == sha256_file(path)
    assert len(stages.receipts) == len(manifest.recommended) > 5
    receipt_by_id = {row.seed_solution_id: row for row in stages.receipts}
    for arm, planned in zip(stages.arms, manifest.arms, strict=True):
        assert arm.arm == planned.arm
        assert arm.stages.scheduled.hypothesis_tasks == 25
        assert arm.stages.recommended == arm.stages.advanced
        assert arm.stages.advanced.hypothesis_tasks == 5
        chosen = {row.solution_id for row in planned.recommended}
        assert {row.solution_id for row in arm.stages.rows if row.recommended} == chosen
        for row in arm.stages.rows:
            if row.solution_id in chosen:
                receipt = receipt_by_id[row.solution_id]
                assert row.continuation_receipt_sha256 == receipt.receipt_sha256
                assert row.additional_copy_attempt_count == len(receipt.attempts)
                assert row.advanced_rank == row.recommendation_rank
            else:
                assert row.advanced_rank is None
                assert row.continuation_receipt_sha256 is None
                assert row.additional_copy_attempt_count == 0
        advanced = [row for row in arm.stages.rows if row.recommended]
        assert arm.stages.advanced.unique_proteins == len(
            {row.sequence_group_id for row in advanced}
        )
        assert arm.stages.advanced.unique_models == len(
            {row.model_id for row in advanced}
        )
        assert arm.stages.advanced.expected_copy_states == len(
            {(row.sequence_group_id, row.expected_copy_count) for row in advanced}
        )
    if prior == "copy_weighted":
        production = validate_m6_advancement(
            path.parent / "benchmark_advancement.json", hypotheses_jsonl=hypotheses
        )
        actual = {row.hypothesis_id: row for row in production.manifest.rows}
        for row in stages.arms[1].stages.rows:
            original = actual[row.hypothesis_id]
            assert row.review_priority_rank == original.review_priority_rank
            assert row.recommendation_rank == original.recommendation_rank
            assert row.recommended == (
                original.advancement_disposition == "recommended"
            )
    assert (
        build_reference_stage_inventory(
            admission,
            hypotheses_jsonl=hypotheses,
            advancement_manifest=path,
            copy_evidence=tuple(reversed(evidence)),
        )
        == stages
    )
    # The saved digest detects later changes even to a log without its own
    # standalone input binding; re-accounting cannot authenticate the old record.
    native = next(
        item for item in evidence if (item.root / "series/PHASER.log").exists()
    )
    (native.root / "series/PHASER.log").write_text("changed synthetic log\n")
    changed = build_reference_stage_inventory(
        admission,
        hypotheses_jsonl=hypotheses,
        advancement_manifest=path,
        copy_evidence=tuple(evidence),
    )
    assert changed != stages


def test_reference_stages_keep_scheduled_no_hits_without_inferred_advancement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admission, hypotheses, path, _ = _inputs(tmp_path, monkeypatch, no_hits=True)
    stages = build_reference_stage_inventory(
        admission,
        hypotheses_jsonl=hypotheses,
        advancement_manifest=path,
        copy_evidence=(),
    )
    assert not stages.receipts
    for arm in stages.arms:
        assert arm.stages.scheduled.hypothesis_tasks == 25
        assert arm.stages.recommended.hypothesis_tasks == 0
        assert arm.stages.advanced.hypothesis_tasks == 0
    hypotheses.write_text(
        hypotheses.read_text() + hypotheses.read_text().splitlines()[0] + "\n"
    )
    with pytest.raises(ValueError, match="exact admission cohort"):
        build_reference_stage_inventory(
            admission,
            hypotheses_jsonl=hypotheses,
            advancement_manifest=path,
            copy_evidence=(),
        )


def test_reference_stages_reject_incomplete_duplicate_and_foreign_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admission, hypotheses, path, manifest = _inputs(tmp_path, monkeypatch)
    request = _copy_request(tmp_path, admission, hypotheses, manifest)
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)
    root = run_reference_copy_task(request, admission, advancement_manifest=path)
    item = ReferenceCopyEvidence(request, root)
    for supplied, message in (
        ((item,), "missing or foreign"),
        ((item, item), "duplicate"),
        (
            (
                ReferenceCopyEvidence(
                    replace(request, seed_solution_id="foreign"), root
                ),
            ),
            "missing or foreign",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            build_reference_stage_inventory(
                admission,
                hypotheses_jsonl=hypotheses,
                advancement_manifest=path,
                copy_evidence=supplied,
            )


@pytest.mark.parametrize("zero_attempts", (True, False))
def test_reference_stages_distinguish_complete_roots_and_execution_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, zero_attempts: bool
) -> None:
    admission, hypotheses, path, manifest = _inputs(
        tmp_path, monkeypatch, small_cell=zero_attempts
    )
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)
    monkeypatch.setattr(
        "genome_to_diffraction.mr.add_copy.capture_from_manifest",
        _unexpected_phenix
        if zero_attempts
        else (
            lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 1, b"", b"synthetic failure"
            )
        ),
    )
    evidence: list[ReferenceCopyEvidence] = []
    for seed in manifest.recommended:
        request = replace(
            _copy_request(
                tmp_path,
                admission,
                hypotheses,
                manifest,
                seed_solution_id=seed.solution_id,
            ),
            output_directory=tmp_path / "copies" / seed.solution_id,
        )
        root = run_reference_copy_task(request, admission, advancement_manifest=path)
        evidence.append(ReferenceCopyEvidence(request, root))
    stages = build_reference_stage_inventory(
        admission,
        hypotheses_jsonl=hypotheses,
        advancement_manifest=path,
        copy_evidence=tuple(evidence),
    )
    assert all(arm.stages.advanced.hypothesis_tasks == 5 for arm in stages.arms)
    attempts = [attempt for receipt in stages.receipts for attempt in receipt.attempts]
    if zero_attempts:
        assert not attempts
        assert all(
            row.additional_copy_attempt_count == 0
            for arm in stages.arms
            for row in arm.stages.rows
        )
    else:
        assert attempts
        assert all(
            row.execution_status is ExecutionStatus.FAILED_TOOL_EXECUTION
            for row in attempts
        )
        assert not any(row.additional_copy_supported for row in attempts)
