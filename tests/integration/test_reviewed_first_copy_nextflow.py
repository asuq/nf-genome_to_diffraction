"""Real authority gate, stubbed MR, and the existing file-based A checkpoint."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

from tests.scripts.check_nextflow import _environment
from tests.unit.test_reviewed_first_copy_selection import _case, _execution_request

REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("valid_confirmation", (True, False))
def test_reviewed_first_copy_nextflow_gates_native_task_fanout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    valid_confirmation: bool,
) -> None:
    request = _execution_request(_case(tmp_path, monkeypatch))
    output = tmp_path / "nextflow_results"
    values = {
        "funnel": request.funnel_directory,
        "confirmed_funnel_sha256": request.confirmed_funnel_sha256
        if valid_confirmation
        else "0" * 64,
        "sequence_groups": request.sequence_groups,
        "source_records": request.source_records,
        "matthews": request.matthews_hypotheses,
        "preflight": request.mtz_preflight,
        "pipeline_config": request.pipeline_config,
        "crystal_directory": request.crystal_directory,
        "execution_identity": request.execution_identity,
        "phenix_manifest": request.phenix_manifest,
        "owned_run_id": "gtd-reviewed-nextflow-fixture",
        "outdir": output,
    }
    command = [
        "nextflow",
        "-C",
        str(REPOSITORY / "tests/fixtures/stubs/p6_empty_partner/nextflow.config"),
        "run",
        str(REPOSITORY / "reviewed_first_copy.nf"),
        "-stub-run",
        "-ansi-log",
        "false",
        "-w",
        str(tmp_path / "work"),
    ]
    for name, value in values.items():
        command.extend((f"--{name}", str(value)))
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=_environment(tmp_path / "nxf-home"),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert (result.returncode == 0) is valid_confirmation, result.stdout + result.stderr
    trace_path = output / "pipeline_info/trace.tsv"
    with trace_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == (4 if valid_confirmation else 1)
    assert {row["process"] for row in rows} == (
        {
            "VALIDATE_REVIEWED_FIRST_COPY_EXECUTION",
            "RUN_PHASE3_FIRST_COPY_PHASER",
            "BUILD_PHASE3_MR_SEED_REVIEW",
            "BUILD_PHASE3_OWNED_A_REVIEW_PACKAGE",
        }
        if valid_confirmation
        else {"VALIDATE_REVIEWED_FIRST_COPY_EXECUTION"}
    )
    if valid_confirmation:
        assert all(row["status"] == "COMPLETED" for row in rows)
        dispatch = json.loads(
            (output / "reviewed_first_copy_dispatch.json").read_text()
        )
        assert dispatch["selected_count"] == 1
        assert dispatch["a_seed_approval_granted"] is False
        markers = tuple(output.rglob("phase3_owned_a_review.stub"))
        assert len(markers) == 1
    else:
        assert rows[0]["status"] == "FAILED"
        assert not (output / "reviewed_first_copy_dispatch.json").exists()
