"""T13.3 reports measured resources without inventing unavailable metrics."""

import csv
import json
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.review.crystal_report import (
    CrystalReportRequest,
    build_crystal_report,
)
from genome_to_diffraction.review.resource_summary import (
    ResourceSummaryError,
    ResourceSummaryRequest,
    build_resource_summary,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.results import ResourceSummaryRecord

_TRACE_FIELDS = (
    "task_id",
    "hash",
    "native_id",
    "name",
    "status",
    "exit",
    "submit",
    "duration",
    "realtime",
    "%cpu",
    "peak_rss",
    "peak_vmem",
    "rchar",
    "wchar",
)


def _write_checkpoint(root: Path) -> None:
    seed_id = "sol_test"
    asset_dir = root / "assets" / seed_id
    asset_dir.mkdir(parents=True)
    assets: dict[str, str] = {}
    for name in (
        "brief_refine_001.pdb",
        "brief_refine_001.mtz",
        "brief_refine_2mFo-DFc.ccp4",
        "sequence_from_map.pdb",
    ):
        path = asset_dir / name
        path.write_text(name, encoding="utf-8")
        assets[path.relative_to(root).as_posix()] = sha256_file(path)
    outputs: dict[str, str] = {}
    for name in (
        "sequence_candidates.html",
        "sequence_candidates_top10.tsv",
        "sequence_candidates_top25.tsv",
        "sequence_candidates_full.tsv",
        "sequence_approval_candidates.tsv",
        "approved_sequence_groups.tsv",
    ):
        path = root / name
        path.write_text(name, encoding="utf-8")
        outputs[name] = sha256_file(path)
    (root / "sequence_checkpoint_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "gtd-t12-test",
                "package_id": "seqreview_test",
                "finalist_count": 1,
                "outputs": outputs,
                "identity": {"assets": assets},
            }
        ),
        encoding="utf-8",
    )
    status = root.parent / "status.json"
    status.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "crystal_id": "crystal_test",
                "execution_status": "completed_success",
                "scientific_status": "insufficient_evidence",
                "prototype_assumption_status": "unknown",
                "credible_seed_count": 1,
                "approved_seed_count": 1,
                "primary_sequence_groups": [],
                "extended_sequence_groups": [],
                "best_supported_copy_counts": {seed_id: 2},
                "residual_content_suspected": False,
                "warnings": ["human_sequence_approval_pending"],
                "completed_at": "2026-08-15T00:00:10Z",
                "provenance_pointers": ["t12-summary.json"],
            }
        ),
        encoding="utf-8",
    )
    build_crystal_report(
        CrystalReportRequest(status_json=status, checkpoint_directory=root)
    )


def _write_trace(path: Path, status: str, *, native_id: str = "101") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_TRACE_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerow(
            {
                "task_id": "1",
                "hash": "aa/bbbbbb",
                "native_id": native_id,
                "name": "WORKFLOW:RUN (t12:sol_test)",
                "status": status,
                "exit": "0",
                "submit": "2026-08-15 00:00:00",
                "duration": "4s",
                "realtime": "4s",
                "%cpu": "50.0%",
                "peak_rss": "1 KB",
                "peak_vmem": "2 KB",
                "rchar": "100 B",
                "wchar": "40 B",
            }
        )


def _write_report(path: Path) -> None:
    task = {
        "task_id": "1",
        "hash": "aa/bbbbbb",
        "native_id": "101",
        "name": "WORKFLOW:RUN (t12:sol_test)",
        "status": "COMPLETED",
        "exit": "0",
        "start": "1000",
        "complete": "5000",
        "realtime": "4000",
        "%cpu": "50.0",
        "peak_rss": "1024",
        "rchar": "100",
        "wchar": "40",
        "read_bytes": "10",
        "write_bytes": "20",
        "attempt": "1",
        "cpus": "4",
        "memory": "17179869184",
        "time": "86400000",
        "script": "tool --model 'model.pdb'",
    }
    payload = json.dumps({"trace": [task], "summary": []}).replace("'", "\\'")
    path.write_text(
        "<html><script>\nwindow.data = " + payload + ";\n</script></html>\n",
        encoding="utf-8",
    )


def _request(root: Path) -> ResourceSummaryRequest:
    checkpoint = root / "checkpoint"
    _write_checkpoint(checkpoint)
    run_manifest = root / "run-manifest.json"
    run_manifest.write_text(
        json.dumps(
            {
                "run_id": "gtd-t12-test",
                "site_id": "viper-cpu",
                "profile": "t12",
                "commit": "a" * 40,
            }
        ),
        encoding="utf-8",
    )
    job_result = root / "job-result.json"
    job_result.write_text(
        json.dumps(
            {
                "run_id": "gtd-t12-test",
                "profile": "t12",
                "job_id": "100",
                "started_at": "2026-08-15T00:00:00Z",
                "completed_at": "2026-08-15T00:00:10Z",
                "scheduler_state": "COMPLETED",
                "exit_code": 0,
                "failure_class": "success",
            }
        ),
        encoding="utf-8",
    )
    first_trace = root / "first-trace.tsv"
    resume_trace = root / "resume-trace.tsv"
    report = root / "first-report.html"
    _write_trace(first_trace, "COMPLETED")
    _write_trace(resume_trace, "CACHED")
    _write_report(report)
    return ResourceSummaryRequest(
        run_manifest_json=run_manifest,
        job_result_json=job_result,
        first_trace_tsv=first_trace,
        resume_trace_tsv=resume_trace,
        first_report_html=report,
        checkpoint_directory=checkpoint,
        progress=False,
    )


def test_resource_summary_separates_measured_and_missing_values(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)

    first = build_resource_summary(request)
    second = build_resource_summary(request)

    assert first.summary_id == second.summary_id
    assert first.record.first_execution.process_count == 1
    assert first.record.first_execution.estimated_cpu_hours == pytest.approx(0.000556)
    assert first.record.first_execution.allocated_cpu_hours == pytest.approx(0.004444)
    assert first.record.first_execution.peak_rss_bytes == 1024
    assert first.record.first_execution.observed_max_concurrent_allocated_cpus == 4
    assert first.record.resume_execution.cached_process_count == 1
    assert first.record.resume_execution.estimated_cpu_hours is None
    assert first.record.outer_job.elapsed_seconds == 10
    assert first.record.outer_job.allocated_cpus is None
    assert first.record.database_io_bytes is None
    assert first.record.database_io_status == "not_measured"
    assert first.record.remote_request_count == 0
    assert first.record.package_inventory.file_count_excluding_summary > 0
    loaded = load_contract(first.summary_json, "resource-summary", progress=False)
    assert isinstance(loaded, ResourceSummaryRecord)


def test_resource_summary_rejects_nonmatching_resume_identity(tmp_path: Path) -> None:
    request = _request(tmp_path)
    _write_trace(request.resume_trace_tsv, "CACHED", native_id="different")

    with pytest.raises(ResourceSummaryError, match="task identities differ"):
        build_resource_summary(request)


def test_resource_summary_rejects_package_symlink(tmp_path: Path) -> None:
    request = _request(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (request.checkpoint_directory / "unsafe-link").symlink_to(outside)

    with pytest.raises(ResourceSummaryError, match="contains a symlink"):
        build_resource_summary(request)
