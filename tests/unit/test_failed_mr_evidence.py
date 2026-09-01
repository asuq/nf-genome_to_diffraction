"""Tests for bounded failed-screen MR child evidence retention."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.hpc.mr_failure_evidence import (
    MrFailureEvidenceError,
    build_failed_mr_evidence,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.mr_resources import build_mr_resource_plan
from genome_to_diffraction.schemas.results import MrHypothesis, NormalisedMrResult
from genome_to_diffraction.status import ExecutionStatus

RUN_ID = "gtd-unknown-screen-20260901T000000Z-0123456789ab-1234abcd"


def _hypothesis(identifier: str, *, copies: int) -> MrHypothesis:
    fixture = Path("tests/fixtures/stubs/exact_predicted_funnel/mr_hypotheses.jsonl")
    base = MrHypothesis.model_validate_json(fixture.read_text(encoding="utf-8"))
    return base.model_copy(
        update={
            "hypothesis_id": identifier,
            "crystal_id": "crystal_test",
            "copy_count_expected": copies,
            "copy_number_to_search": 1,
        }
    )


def _case(tmp_path: Path) -> tuple[Path, Path, tuple[MrHypothesis, ...]]:
    work = tmp_path / "work"
    funnel = work / "aa" / "funnelhash" / "diverse_first_copy_funnel"
    funnel.mkdir(parents=True)
    hypotheses = tuple(
        _hypothesis(f"mrhyp_{character * 64}", copies=copies)
        for character, copies in (("a", 7), ("b", 12), ("c", 4))
    )
    (funnel / "mr_hypotheses.jsonl").write_text(
        "".join(f"{canonical_json_text(item)}\n" for item in hypotheses),
        encoding="utf-8",
    )
    plans = funnel / "resource_plans"
    plans.mkdir()
    for hypothesis in hypotheses:
        plan = build_mr_resource_plan(
            owner_kind="mr_hypothesis",
            owner_id=hypothesis.hypothesis_id,
            reflection_count=10_000,
            moving_atom_count=1_000,
            searched_copy_count=1,
            fixed_atom_count=0,
            symmetry_multiplicity=4,
        )
        (plans / f"{hypothesis.hypothesis_id}.json").write_text(
            f"{canonical_json_text(plan)}\n",
            encoding="utf-8",
        )

    first_work = work / "11" / "firsthash"
    second_work = work / "22" / "secondhash"
    first_work.mkdir(parents=True)
    second_work.mkdir(parents=True)
    for name in (".command.sh", ".command.log", ".command.trace", ".exitcode"):
        (first_work / name).write_text(f"first {name}\n", encoding="utf-8")
    (first_work / ".command.run").write_text(
        "#!/bin/bash\n#SBATCH -c 8\n#SBATCH -t 1-00:00:00\n#SBATCH --mem 32G\n",
        encoding="utf-8",
    )
    (second_work / ".command.log").write_text("second running\n", encoding="utf-8")
    result = (
        first_work / f"phase3_first_copy_crystal_test_{hypotheses[0].hypothesis_id}"
    )
    result.mkdir()
    normalised = NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=hypotheses[0].hypothesis_id,
        tool_version="Phaser test",
        execution_status=ExecutionStatus.COMPLETED_NO_HIT,
        placed_copy_count=0,
        packing_summary={"top_solution_packed": False},
        raw_log_pointer="PHASER.log",
    )
    (result / "normalised_mr_result.json").write_text(
        f"{canonical_json_text(normalised)}\n",
        encoding="utf-8",
    )
    (result / "PHASER.log").write_text("NO SOLUTION\n", encoding="utf-8")

    log = tmp_path / "nextflow.log"
    log.write_text(
        "\n".join(
            (
                "Aug-31 04:02:11.575 [Task submitter] DEBUG "
                "nextflow.executor.GridTaskHandler - [SLURM] submitted process "
                "WORKFLOW:RUN_PHASE3_FIRST_COPY_PHASER "
                f"(phase3-first-copy:crystal_test:{hypotheses[0].hypothesis_id}) "
                f"> jobId: 101; workDir: {first_work}",
                "Aug-31 04:02:11.675 [Task submitter] DEBUG "
                "nextflow.executor.GridTaskHandler - [SLURM] submitted process "
                "WORKFLOW:RUN_PHASE3_FIRST_COPY_PHASER "
                f"(phase3-first-copy:crystal_test:{hypotheses[1].hypothesis_id}) "
                f"> jobId: 102; workDir: {second_work}",
                "Aug-31 05:00:00.000 [Task monitor] DEBUG monitor - Task completed > "
                "TaskHandler[jobId: 101; id: 1; name: "
                "WORKFLOW:RUN_PHASE3_FIRST_COPY_PHASER "
                f"(phase3-first-copy:crystal_test:{hypotheses[0].hypothesis_id}); "
                "status: COMPLETED; exit: 0; error: -; workDir: unused "
                "started: 1788141761501; exited: 2026-08-31T05:00:00Z; ]",
                "WARN: Killing running tasks (1)",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return work, log, hypotheses


def test_failed_mr_evidence_conserves_completed_running_and_unsubmitted(
    tmp_path: Path,
) -> None:
    work, log, hypotheses = _case(tmp_path)
    output = tmp_path / "failed-evidence"

    manifest_path = build_failed_mr_evidence(
        run_id=RUN_ID,
        nextflow_log=log,
        work_root=work,
        output_directory=output,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["scientific_evidence_accepted"] is False
    assert manifest["cache_reusable"] is False
    assert manifest["funnel_hypothesis_count"] == 3
    assert manifest["submitted_attempt_count"] == 2
    assert manifest["completed_attempt_count"] == 1
    assert manifest["unfinished_attempt_count"] == 1
    assert manifest["unsubmitted_hypothesis_count"] == 1
    assert {item["hypothesis_id"]: item["state"] for item in manifest["children"]} == {
        hypotheses[0].hypothesis_id: "completed",
        hypotheses[1].hypothesis_id: "unfinished_at_controller_abort",
        hypotheses[2].hypothesis_id: "unsubmitted",
    }
    first_attempt = manifest["children"][0]["attempts"][0]
    assert first_attempt["allocated_resources"] == {
        "cpus": 8,
        "time_limit": "1-00:00:00",
        "memory_limit": "32G",
    }
    assert first_attempt["normalised_result"] == {
        "state": "valid",
        "execution_status": "completed_no_hit",
    }
    assert (
        output
        / "children"
        / hypotheses[0].hypothesis_id
        / "attempt-01"
        / "result"
        / "PHASER.log"
    ).read_text(encoding="utf-8") == "NO SOLUTION\n"
    assert (
        output / "hypotheses" / hypotheses[0].hypothesis_id / "mr_resource_plan.json"
    ).is_file()

    checksum_rows = tuple(
        line.split("  ", 1)
        for line in (output / "checksums.sha256").read_text().splitlines()
        if line
    )
    assert len(checksum_rows) == int((output / "file-count").read_text())
    for digest, relative in checksum_rows:
        assert sha256_file(output / relative, progress=False) == digest


def test_failed_mr_evidence_rejects_cross_funnel_submission(tmp_path: Path) -> None:
    work, log, _ = _case(tmp_path)
    text = log.read_text(encoding="utf-8").replace(
        "mrhyp_" + "b" * 64, "mrhyp_" + "d" * 64
    )
    log.write_text(text, encoding="utf-8")

    with pytest.raises(MrFailureEvidenceError, match="absent from the funnel"):
        build_failed_mr_evidence(
            run_id=RUN_ID,
            nextflow_log=log,
            work_root=work,
            output_directory=tmp_path / "rejected",
        )


def test_failed_mr_evidence_rejects_orphan_completion(tmp_path: Path) -> None:
    work, log, _ = _case(tmp_path)
    text = log.read_text(encoding="utf-8").replace(
        "TaskHandler[jobId: 101;", "TaskHandler[jobId: 999;"
    )
    log.write_text(text, encoding="utf-8")

    with pytest.raises(MrFailureEvidenceError, match="absent from the submission"):
        build_failed_mr_evidence(
            run_id=RUN_ID,
            nextflow_log=log,
            work_root=work,
            output_directory=tmp_path / "rejected",
        )
