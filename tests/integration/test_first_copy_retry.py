"""Actual first-copy CLI failures reach the existing Nextflow retry/resume rule."""

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from genome_to_diffraction.checksums import sha256_file

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURE = REPOSITORY / "tests/fixtures/stubs/first_copy_retry/main.nf"


def _run(
    root: Path, scenario: str, *, resume: bool = False
) -> tuple[subprocess.CompletedProcess[str], tuple[dict[str, str], ...]]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "cache").mkdir(exist_ok=True)
    environment = dict(os.environ)
    environment.update(
        NXF_AGENT_MODE="true",
        NXF_ANSI_LOG="false",
        NXF_DISABLE_CHECK_LATEST="true",
        NXF_HOME=str(root / "nxf-home"),
        NXF_SYNTAX_PARSER="v2",
        NXF_JVM_ARGS="-Xms256m -Xmx2g -XX:ActiveProcessorCount=1",
        POLARS_MAX_THREADS="1",
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    command = [
        "nextflow",
        "-C",
        str(REPOSITORY / "conf/base.config"),
        "run",
        str(FIXTURE),
        "--scenario",
        scenario,
        "--repository",
        str(REPOSITORY),
        "--python",
        sys.executable,
        "--outdir",
        str(root / "results"),
        "--cache_root",
        str(root / "cache"),
    ]
    if resume:
        command.append("-resume")
    result = subprocess.run(
        command,
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    trace = root / "results/pipeline_info/trace.tsv"
    assert trace.is_file(), f"{result.stdout}\n{result.stderr}"
    with trace.open(encoding="utf-8", newline="") as stream:
        rows = tuple(csv.DictReader(stream, delimiter="\t"))
    for row in rows:
        work = Path(row["workdir"])
        observed = json.loads((work / "attempt-result.json").read_text())
        assert observed["mocked_native_execution"] is True
        assert observed["result_sha256"] == sha256_file(
            work / "native-output/normalised_mr_result.json"
        )
        assert observed["cli_exit"] == int(row["exit"])
    return result, rows


def test_native_75_retries_once_then_reuses_the_successful_attempt(
    tmp_path: Path,
) -> None:
    root = tmp_path / "recover"
    result, rows = _run(root, "recover")
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert tuple(row["attempt"] for row in rows) == ("1", "2")
    assert tuple(row["exit"] for row in rows) == ("75", "0")
    first, second = (Path(row["workdir"]) for row in rows)
    assert first != second
    first_receipt = json.loads((first / "attempt-result.json").read_text())
    second_receipt = json.loads((second / "attempt-result.json").read_text())
    assert first_receipt["native_exit"] == 75
    assert second_receipt["native_exit"] == 0
    for key in ("hypothesis_id", "requested_threads", "scientific_input_sha256"):
        assert first_receipt[key] == second_receipt[key]
    before = {
        str(path.relative_to(second)): sha256_file(path)
        for path in (second / "native-output").rglob("*")
        if path.is_file()
    }
    resumed, cached = _run(root, "recover", resume=True)
    assert resumed.returncode == 0, f"{resumed.stdout}\n{resumed.stderr}"
    assert len(cached) == 1 and cached[0]["status"] == "CACHED"
    assert Path(cached[0]["workdir"]) == second
    assert before == {
        str(path.relative_to(second)): sha256_file(path)
        for path in (second / "native-output").rglob("*")
        if path.is_file()
    }


def test_exhausted_native_75_stays_failed_with_both_attempts_retained(
    tmp_path: Path,
) -> None:
    result, rows = _run(tmp_path / "exhausted", "exhausted")
    assert result.returncode != 0
    assert tuple(row["attempt"] for row in rows) == ("1", "2")
    assert tuple(row["exit"] for row in rows) == ("75", "75")
    assert all(row["status"] == "FAILED" for row in rows)


def test_no_hit_and_deterministic_tool_failure_do_not_gain_a_retry(
    tmp_path: Path,
) -> None:
    for scenario in ("no_hit", "tool_failure"):
        result, rows = _run(tmp_path / scenario, scenario)
        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
        assert len(rows) == 1
        assert rows[0]["attempt"] == "1" and rows[0]["exit"] == "0"
