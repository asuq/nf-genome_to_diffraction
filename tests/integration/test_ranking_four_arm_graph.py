"""Actual fixed RF Nextflow scheduling with explicitly simulated scientific stages."""

import csv
import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.hpc.rf_reference_evidence import (
    reference_native_file_inventory,
    reference_staged_search_inputs,
)
from tests.fixtures.ranking_four_arm_advancement import REFERENCE_CASE_IDS
from tests.fixtures.ranking_four_arm_execution import (
    ReferenceChildOutputRequest,
    collect_reference_child_outputs,
)
from tests.scripts.check_nextflow import _environment
from tests.unit.test_ranking_four_arm_plan import _inputs

ROOT = Path(__file__).resolve().parents[2]


def test_reference_graph_keeps_all_cases_fans_out_and_resumes(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.mkdir()
    inputs = _inputs(original)
    published = tmp_path / "published"
    cache = tmp_path / "cache"
    published.mkdir()
    cache.mkdir()
    command = [
        "nextflow",
        "-C",
        str(ROOT / "nextflow.config"),
        "run",
        str(ROOT / "rf_reference.nf"),
        "-profile",
        "test",
        "-stub-run",
        "-ansi-log",
        "false",
        "-w",
        str(tmp_path / "cache/rf-reference/work"),
        "--runner_root",
        str(inputs.runner_root),
        "--protocol",
        str(ROOT / "benchmarks/m6/protocol.yaml"),
        "--execution_policy",
        str(ROOT / "benchmarks/m6/execution-nextflow-v1.yaml"),
        "--software_lock",
        str(inputs.software_lock),
        "--database_manifest",
        str(inputs.database_manifest),
        "--phenix_manifest",
        str(ROOT / "tests/fixtures/stubs/phenix_install_manifest.json"),
        "--outdir",
        str(published),
        "--cache_root",
        str(cache),
    ]
    environment = _environment(tmp_path / "nxf-home")
    environment["PYTHONPATH"] = f"{ROOT / 'src'}:{ROOT}"
    environment["NXF_OPTS"] = "-Xmx2g"

    def run(label: str, *, resume: bool) -> list[dict[str, str]]:
        result = subprocess.run(
            [*command, *(["-resume"] if resume else [])],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        (tmp_path / f"{label}.log").write_text(
            result.stdout + result.stderr, encoding="utf-8"
        )
        assert result.returncode == 0, result.stdout + result.stderr
        trace = published / "pipeline_info/trace.tsv"
        (tmp_path / f"{label}.trace.tsv").write_bytes(trace.read_bytes())
        with trace.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))

    first = run("first", resume=False)
    assert {row["status"] for row in first} == {"COMPLETED"}
    # Actual Nextflow staging/filesystem proof with explicitly simulated science;
    # numeric local executor IDs are not native Raven/Phenix acceptance.
    original_inputs = reference_staged_search_inputs(tmp_path, tuple(first))
    original_files = reference_native_file_inventory(tmp_path, tuple(first))
    assert len(original_inputs) == 15
    assert not (set(original_files) & set(original_inputs))
    counts = Counter(row["process"].split(":")[-1] for row in first)
    assert counts == Counter(
        {
            "RF_PLAN": 1,
            "M6_IMPORT_CATALOGUE": 1,
            "M6_BUILD_SEARCH_BATCHES": 1,
            "M6_SEARCH_PDB": 2,
            "M6_SEARCH_FOLDSEEK": 2,
            "M6_PARTITION_DISCOVERY": 1,
            "M6_PREFLIGHT_CASE": 5,
            "M6_APPLY_POLICY": 4,
            "M6_STAGE_COORDINATES": 4,
            "M6_PREPARE_ACTIVE_CASE": 4,
            "M6_PREPARE_EARLY_CASE": 1,
            "RF_PREPARE": 5,
            "RF_FIRST_COPY": 4,
            "RF_REVIEWS": 3,
            "RF_COPY": 2,
            "RF_FINALISTS": 3,
            "RF_REFINE": 2,
            "RF_IDENTITY": 3,
            "RF_AGGREGATE": 1,
        }
    )
    result_path = published / "reference_run/bundle/reference_run.json"
    summary = json.loads(result_path.read_bytes())
    assert summary["record_kind"] == "rf_nextflow_scheduling_stub"
    assert summary["simulation_only"]
    assert summary["case_ids"] == sorted(REFERENCE_CASE_IDS)
    assert summary["identity_case_ids"] == ["M6C001", "M6C010", "M6C055"]
    assert not summary["native_acceptance_claim"]
    assert not summary["benchmark_acceptance_claim"]
    assert not summary["human_approval_granted"]
    before = sha256_file(result_path)
    checkpoint = tmp_path / "first-outputs.json"
    frozen = collect_reference_child_outputs(
        ReferenceChildOutputRequest(
            result_path, tmp_path / "first.trace.tsv", checkpoint
        )
    )
    assert frozen.task_count == len(first)
    assert len(frozen.task_logs) == len(first)
    assert not frozen.native_acceptance_claim
    baseline_sha = sha256_file(checkpoint)
    resumed = run("resume", resume=True)
    assert len(resumed) == len(first)
    assert {row["status"] for row in resumed} == {"CACHED"}
    assert reference_staged_search_inputs(tmp_path, tuple(resumed)) == original_inputs
    assert reference_native_file_inventory(tmp_path, tuple(resumed)) == original_files
    assert {(row["process"], row["hash"]) for row in resumed} == {
        (row["process"], row["hash"]) for row in first
    }
    assert sha256_file(result_path) == before
    replay = collect_reference_child_outputs(
        ReferenceChildOutputRequest(
            result_path,
            tmp_path / "resume.trace.tsv",
            tmp_path / "resume-outputs.json",
            checkpoint,
            baseline_sha,
        )
    )
    assert replay.phase == "resume"
    assert replay.baseline_sha256 == baseline_sha
    assert replay.task_logs == frozen.task_logs
    assert replay.source_sha256 == frozen.source_sha256

    def held(output: str, message: str) -> None:
        with pytest.raises((ValueError, PublicControlError), match=message):
            collect_reference_child_outputs(
                ReferenceChildOutputRequest(
                    result_path,
                    tmp_path / "resume.trace.tsv",
                    tmp_path / output,
                    checkpoint,
                    baseline_sha,
                )
            )
        assert not (tmp_path / output).exists()

    child = next(row for row in first if row["process"].endswith(":RF_FIRST_COPY"))
    original_work = Path(child["workdir"])
    receipt = original_work / "reference_first/bundle/reference_first_copy.json"
    original_bytes = receipt.read_bytes()
    receipt.write_bytes(original_bytes + b"\n")
    mutated = run("cached-mutation", resume=True)
    assert len(mutated) == len(first)
    assert {row["status"] for row in mutated} == {"CACHED"}
    assert sha256_file(result_path) == before
    held(
        "changed-child.json",
        "cached source, result, child outputs or task logs changed",
    )
    receipt.unlink()
    held("missing-child.json", "missing or changed child outputs")
    receipt.write_bytes(original_bytes)

    command_log = original_work / ".command.err"
    original_log = command_log.read_bytes()
    command_log.write_bytes(original_log + b"changed task log\n")
    held(
        "changed-log.json", "cached source, result, child outputs or task logs changed"
    )
    command_log.unlink()
    held("missing-log.json", "original task log is missing or substituted")
    command_log.write_bytes(original_log)
    checkpoint.write_bytes(checkpoint.read_bytes() + b"\n")
    held("changed-baseline.json", "first-pass checkpoint checksum changed")
