"""Build the deterministic T13.3 resource summary from retained T12 evidence."""

import csv
import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.review.historical_checkpoint import (
    verify_historical_checkpoint,
)
from genome_to_diffraction.schemas.results import (
    OuterJobResourceSummary,
    PackageResourceInventory,
    ProcessResourceSummary,
    ResourceSummaryRecord,
)
from genome_to_diffraction.status import InputContractError

_LOGGER = logging.getLogger("genome_to_diffraction.review.resource_summary")
_REPORT_MARKER = "window.data = "
_SUMMARY_BASENAME = "resource_summary.json"
_TRACE_FIELDS = frozenset(
    {
        "task_id",
        "hash",
        "native_id",
        "name",
        "status",
        "exit",
        "duration",
        "realtime",
        "%cpu",
        "peak_rss",
        "peak_vmem",
        "rchar",
        "wchar",
    }
)


class ResourceSummaryError(InputContractError):
    """Retained execution or package evidence cannot support T13.3."""


class _RunManifest(BaseModel):
    run_id: str
    site_id: str
    profile: str
    commit: str = Field(pattern=r"^[a-f0-9]{40}$")


class _JobResult(BaseModel):
    run_id: str
    profile: str
    job_id: str
    started_at: datetime
    completed_at: datetime
    scheduler_state: str
    exit_code: int
    failure_class: str


class _ReportTask(BaseModel):
    task_id: str
    hash: str
    native_id: str
    name: str
    status: str
    exit: str
    start: str
    complete: str
    realtime: str
    cpu_percent: str = Field(alias="%cpu")
    peak_rss: str
    rchar: str
    wchar: str
    read_bytes: str
    write_bytes: str
    attempt: str
    cpus: str
    memory: str
    time: str


class _ReportData(BaseModel):
    trace: list[_ReportTask]


class _CrystalReportIdentity(BaseModel):
    checkpoint_package_id: str
    checkpoint_manifest_sha256: str
    scientific_status_sha256: str
    report_html_sha256: str


class _CrystalReportManifest(BaseModel):
    report_id: str
    identity: _CrystalReportIdentity
    outputs: dict[str, str]


@dataclass(frozen=True)
class ResourceSummaryRequest:
    """Fixed retained inputs for one T13.3 summary."""

    run_manifest_json: Path
    job_result_json: Path
    first_trace_tsv: Path
    resume_trace_tsv: Path
    first_report_html: Path
    checkpoint_directory: Path
    progress: bool = True


@dataclass(frozen=True)
class ResourceSummaryOutput:
    """The stable resource record added to the review package."""

    summary_id: str
    summary_json: Path
    record: ResourceSummaryRecord


def _regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ResourceSummaryError(f"{label} is absent or unsafe: {path}")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise ResourceSummaryError(f"cannot resolve {label}: {path}") from exc


def _load_model[T: BaseModel](path: Path, model: type[T], label: str) -> T:
    resolved = _regular_file(path, label)
    try:
        return model.model_validate_json(resolved.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise ResourceSummaryError(f"invalid {label}: {exc}") from exc


def _read_trace(path: Path, expected_status: str) -> list[dict[str, str]]:
    resolved = _regular_file(path, f"{expected_status} trace")
    try:
        with resolved.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames is None or not _TRACE_FIELDS.issubset(
                reader.fieldnames
            ):
                raise ResourceSummaryError(
                    f"Nextflow trace has incomplete headers: {resolved}"
                )
            rows = [
                {key: value or "" for key, value in row.items() if key is not None}
                for row in reader
            ]
    except OSError as exc:
        raise ResourceSummaryError(f"cannot read Nextflow trace: {resolved}") from exc
    if not rows:
        raise ResourceSummaryError(f"Nextflow trace contains no rows: {resolved}")
    if any(row["status"] != expected_status or row["exit"] != "0" for row in rows):
        raise ResourceSummaryError(
            f"Nextflow trace is not entirely {expected_status}/exit 0: {resolved}"
        )
    return rows


def _load_report(path: Path) -> tuple[list[_ReportTask], Path]:
    resolved = _regular_file(path, "first Nextflow report")
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise ResourceSummaryError(f"cannot read Nextflow report: {resolved}") from exc
    marker_index = text.find(_REPORT_MARKER)
    if marker_index < 0:
        raise ResourceSummaryError("Nextflow report lacks its data payload")
    payload = text[marker_index + len(_REPORT_MARKER) :].lstrip()
    # Nextflow emits a JavaScript object, not strict JSON: shell single quotes in
    # the recorded command are escaped as \' even though the string uses double
    # quotes. Removing that JavaScript-only escape preserves the command text.
    payload = payload.replace("\\'", "'")
    try:
        decoded, _ = json.JSONDecoder().raw_decode(payload)
        report = _ReportData.model_validate(decoded)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ResourceSummaryError(f"invalid Nextflow report data: {exc}") from exc
    if not report.trace:
        raise ResourceSummaryError("Nextflow report contains no task records")
    return report.trace, resolved


def _task_key(row: dict[str, str] | _ReportTask) -> tuple[str, str, str, str]:
    if isinstance(row, _ReportTask):
        return row.task_id, row.hash, row.native_id, row.name
    return row["task_id"], row["hash"], row["native_id"], row["name"]


def _unique_task_keys(
    rows: list[dict[str, str]] | list[_ReportTask], label: str
) -> set[tuple[str, str, str, str]]:
    keys = [_task_key(row) for row in rows]
    if any(not all(key) for key in keys) or len(keys) != len(set(keys)):
        raise ResourceSummaryError(
            f"{label} contains empty or duplicate task identities"
        )
    return set(keys)


def _integer(value: str, label: str, *, positive: bool = False) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ResourceSummaryError(f"invalid integer {label}: {value!r}") from exc
    if parsed < (1 if positive else 0):
        raise ResourceSummaryError(f"invalid integer {label}: {value!r}")
    return parsed


def _percentage(value: str) -> float:
    try:
        parsed = float(value.removesuffix("%"))
    except ValueError as exc:
        raise ResourceSummaryError(f"invalid CPU percentage: {value!r}") from exc
    if parsed < 0:
        raise ResourceSummaryError(f"invalid CPU percentage: {value!r}")
    return parsed


def _concurrency(tasks: list[tuple[int, int, int, int]]) -> tuple[int, int, int]:
    events: list[tuple[int, int, int, int, int]] = []
    for start, complete, cpus, memory in tasks:
        events.append((start, 1, 1, cpus, memory))
        events.append((complete, 0, -1, -cpus, -memory))
    active = active_cpus = active_memory = 0
    maximum = maximum_cpus = maximum_memory = 0
    for _, _, count_delta, cpu_delta, memory_delta in sorted(events):
        active += count_delta
        active_cpus += cpu_delta
        active_memory += memory_delta
        if active < 0 or active_cpus < 0 or active_memory < 0:
            raise ResourceSummaryError(
                "Nextflow report has inconsistent task intervals"
            )
        maximum = max(maximum, active)
        maximum_cpus = max(maximum_cpus, active_cpus)
        maximum_memory = max(maximum_memory, active_memory)
    return maximum, maximum_cpus, maximum_memory


def _summarise_first(tasks: list[_ReportTask]) -> ProcessResourceSummary:
    intervals: list[tuple[int, int, int, int]] = []
    starts: list[int] = []
    completes: list[int] = []
    realtimes: list[int] = []
    cpu_percentages: list[float] = []
    attempts: list[int] = []
    cpus: list[int] = []
    memories: list[int] = []
    time_limits: list[int] = []
    peak_rss: list[int] = []
    rchar: list[int] = []
    wchar: list[int] = []
    read_bytes: list[int] = []
    write_bytes: list[int] = []
    statuses: Counter[str] = Counter()
    for task in tasks:
        if task.status != "COMPLETED" or task.exit != "0":
            raise ResourceSummaryError(
                "first Nextflow report is not entirely COMPLETED/exit 0"
            )
        start = _integer(task.start, "task start")
        complete = _integer(task.complete, "task completion", positive=True)
        realtime = _integer(task.realtime, "task realtime")
        task_cpus = _integer(task.cpus, "allocated CPUs", positive=True)
        memory = _integer(task.memory, "allocated memory", positive=True)
        if complete <= start:
            raise ResourceSummaryError("Nextflow task timing is inconsistent")
        starts.append(start)
        completes.append(complete)
        realtimes.append(realtime)
        cpu_percentages.append(_percentage(task.cpu_percent))
        attempts.append(_integer(task.attempt, "attempt", positive=True))
        cpus.append(task_cpus)
        memories.append(memory)
        time_limits.append(_integer(task.time, "time limit", positive=True))
        peak_rss.append(_integer(task.peak_rss, "peak RSS"))
        rchar.append(_integer(task.rchar, "rchar"))
        wchar.append(_integer(task.wchar, "wchar"))
        read_bytes.append(_integer(task.read_bytes, "read_bytes"))
        write_bytes.append(_integer(task.write_bytes, "write_bytes"))
        intervals.append((start, complete, task_cpus, memory))
        statuses[task.status] += 1
    maximum, maximum_cpus, maximum_memory = _concurrency(intervals)
    estimated_cpu_hours = sum(
        realtime / 3_600_000 * cpu_percent / 100
        for realtime, cpu_percent in zip(realtimes, cpu_percentages, strict=True)
    )
    allocated_cpu_hours = sum(
        realtime / 3_600_000 * task_cpus
        for realtime, task_cpus in zip(realtimes, cpus, strict=True)
    )
    return ProcessResourceSummary(
        process_count=len(tasks),
        executed_process_count=len(tasks),
        cached_process_count=0,
        retry_count=sum(attempt - 1 for attempt in attempts),
        status_counts=dict(sorted(statuses.items())),
        wall_span_seconds=(max(completes) - min(starts)) / 1000,
        process_realtime_seconds_sum=sum(realtimes) / 1000,
        estimated_cpu_hours=round(estimated_cpu_hours, 6),
        allocated_cpu_hours=round(allocated_cpu_hours, 6),
        peak_rss_bytes=max(peak_rss),
        total_rchar_bytes=sum(rchar),
        total_wchar_bytes=sum(wchar),
        total_read_bytes=sum(read_bytes),
        total_write_bytes=sum(write_bytes),
        allocated_cpus_per_process_min=min(cpus),
        allocated_cpus_per_process_max=max(cpus),
        allocated_memory_bytes_per_process_min=min(memories),
        allocated_memory_bytes_per_process_max=max(memories),
        allocated_time_limit_seconds_per_process_min=min(time_limits) / 1000,
        allocated_time_limit_seconds_per_process_max=max(time_limits) / 1000,
        observed_max_concurrent_processes=maximum,
        observed_max_concurrent_allocated_cpus=maximum_cpus,
        observed_max_concurrent_allocated_memory_bytes=maximum_memory,
        measurement_note=(
            "Exact allocation and byte counters come from the retained Nextflow "
            "report; CPU-hours are trace estimates from realtime and %cpu."
        ),
    )


def _summarise_resume(rows: list[dict[str, str]]) -> ProcessResourceSummary:
    statuses = Counter(row["status"] for row in rows)
    return ProcessResourceSummary(
        process_count=len(rows),
        executed_process_count=0,
        cached_process_count=len(rows),
        retry_count=0,
        status_counts=dict(sorted(statuses.items())),
        measurement_note=(
            "All rows are CACHED; inherited first-run metrics are deliberately not "
            "counted as new execution resources."
        ),
    )


def _verify_crystal_report(
    root: Path, checkpoint_package_id: str, checkpoint_manifest_sha256: str
) -> Path:
    manifest_path = _regular_file(
        root / "crystal_report_manifest.json", "crystal report manifest"
    )
    manifest = _load_model(
        manifest_path, _CrystalReportManifest, "crystal report manifest"
    )
    if (
        manifest.identity.checkpoint_package_id != checkpoint_package_id
        or manifest.identity.checkpoint_manifest_sha256 != checkpoint_manifest_sha256
    ):
        raise ResourceSummaryError("crystal report and checkpoint identities differ")
    required = {"crystal_report.html", "scientific_status.json"}
    if not required.issubset(manifest.outputs):
        raise ResourceSummaryError("crystal report output inventory is incomplete")
    for relative, expected in manifest.outputs.items():
        path = root / relative
        try:
            path.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as exc:
            raise ResourceSummaryError(
                f"crystal report output escapes the package: {relative}"
            ) from exc
        if path.is_symlink() or not path.is_file() or sha256_file(path) != expected:
            raise ResourceSummaryError(
                f"crystal report output failed verification: {relative}"
            )
    if (
        manifest.outputs["crystal_report.html"] != manifest.identity.report_html_sha256
        or manifest.outputs["scientific_status.json"]
        != manifest.identity.scientific_status_sha256
    ):
        raise ResourceSummaryError("crystal report identity checksums are inconsistent")
    return manifest_path


def _inventory(root: Path, output: Path, *, progress: bool) -> PackageResourceInventory:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ResourceSummaryError(f"review package contains a symlink: {path}")
        if path.is_file() and path != output:
            files.append(path)
    entries: list[dict[str, str | int]] = []
    total_bytes = 0
    for path in tqdm(
        sorted(files),
        desc="Inventory review package",
        unit="file",
        disable=not progress,
    ):
        size = path.stat().st_size
        total_bytes += size
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": size,
                "sha256": sha256_file(path),
            }
        )
    return PackageResourceInventory(
        file_count_excluding_summary=len(entries),
        total_bytes_excluding_summary=total_bytes,
        inventory_id=content_id("inventory_", entries),
        measurement_note=(
            "Logical regular-file bytes in the self-contained T12.5/T13.2 package; "
            "the resource summary itself is excluded for deterministic rebuilds."
        ),
    )


def build_resource_summary(request: ResourceSummaryRequest) -> ResourceSummaryOutput:
    """Verify retained evidence and atomically add the T13.3 resource record."""

    run = _load_model(request.run_manifest_json, _RunManifest, "run manifest")
    job = _load_model(request.job_result_json, _JobResult, "outer job result")
    if (
        run.run_id != job.run_id
        or run.profile != "t12"
        or job.profile != "t12"
        or job.scheduler_state != "COMPLETED"
        or job.exit_code != 0
        or job.failure_class != "success"
    ):
        raise ResourceSummaryError("resource summary requires accepted T12 execution")

    root = request.checkpoint_directory.resolve(strict=True)
    if request.checkpoint_directory.is_symlink() or not root.is_dir():
        raise ResourceSummaryError("checkpoint directory is absent or unsafe")
    checkpoint, checkpoint_manifest_path = verify_historical_checkpoint(root)
    checkpoint_manifest_sha256 = sha256_file(checkpoint_manifest_path)
    if checkpoint.run_id != run.run_id:
        raise ResourceSummaryError("checkpoint and execution run IDs differ")
    crystal_report_manifest_path = _verify_crystal_report(
        root, checkpoint.package_id, checkpoint_manifest_sha256
    )

    first_rows = _read_trace(request.first_trace_tsv, "COMPLETED")
    resume_rows = _read_trace(request.resume_trace_tsv, "CACHED")
    report_tasks, report_path = _load_report(request.first_report_html)
    first_keys = _unique_task_keys(first_rows, "first trace")
    resume_keys = _unique_task_keys(resume_rows, "resume trace")
    report_keys = _unique_task_keys(report_tasks, "first report")
    if first_keys != resume_keys or first_keys != report_keys:
        raise ResourceSummaryError(
            "first trace, resume trace, and report task identities differ"
        )
    if len(first_rows) != checkpoint.finalist_count:
        raise ResourceSummaryError("process and checkpoint finalist counts differ")

    output = root / _SUMMARY_BASENAME
    if output.is_symlink():
        raise ResourceSummaryError("resource summary output must not be a symlink")
    package_inventory = _inventory(root, output, progress=request.progress)
    first_execution = _summarise_first(report_tasks)
    resume_execution = _summarise_resume(resume_rows)
    elapsed_seconds = (job.completed_at - job.started_at).total_seconds()
    outer_job = OuterJobResourceSummary(
        job_id=job.job_id,
        scheduler_state=job.scheduler_state,
        started_at=job.started_at,
        completed_at=job.completed_at,
        elapsed_seconds=elapsed_seconds,
        allocated_cpus=None,
        allocated_memory_bytes=None,
        peak_rss_bytes=None,
        measurement_note=(
            "Elapsed time is measured by the outer job result; that contract does "
            "not record outer allocation or MaxRSS, so those fields remain null."
        ),
    )
    evidence_sha256 = {
        "checkpoint_manifest": checkpoint_manifest_sha256,
        "crystal_report_manifest": sha256_file(crystal_report_manifest_path),
        "first_nextflow_report": sha256_file(report_path),
        "first_nextflow_trace": sha256_file(request.first_trace_tsv),
        "outer_job_result": sha256_file(request.job_result_json),
        "resume_nextflow_trace": sha256_file(request.resume_trace_tsv),
        "run_manifest": sha256_file(request.run_manifest_json),
    }
    io_measurement_semantics = (
        "Nextflow rchar/wchar and read_bytes/write_bytes describe process-level "
        "I/O counters, not physical database-device traffic. T12 uses only staged "
        "inputs and performs no remote requests."
    )
    identity = {
        "run_id": run.run_id,
        "site_id": run.site_id,
        "profile": run.profile,
        "source_commit": run.commit,
        "checkpoint_package_id": checkpoint.package_id,
        "outer_job": outer_job.model_dump(mode="json"),
        "first_execution": first_execution.model_dump(mode="json"),
        "resume_execution": resume_execution.model_dump(mode="json"),
        "package_inventory": package_inventory.model_dump(mode="json"),
        "database_io_bytes": None,
        "database_io_status": "not_measured",
        "remote_request_count": 0,
        "remote_request_status": "not_applicable",
        "io_measurement_semantics": io_measurement_semantics,
        "evidence_sha256": evidence_sha256,
    }
    summary_id = content_id("resources_", identity)
    record = ResourceSummaryRecord(
        schema_version="1.0",
        summary_id=summary_id,
        run_id=run.run_id,
        site_id=run.site_id,
        profile=run.profile,
        source_commit=run.commit,
        checkpoint_package_id=checkpoint.package_id,
        outer_job=outer_job,
        first_execution=first_execution,
        resume_execution=resume_execution,
        package_inventory=package_inventory,
        database_io_bytes=None,
        database_io_status="not_measured",
        remote_request_count=0,
        remote_request_status="not_applicable",
        io_measurement_semantics=io_measurement_semantics,
        evidence_sha256=evidence_sha256,
    )
    atomic_write_json(output, record.model_dump(mode="json"))
    _LOGGER.info(
        "T13.3 resource summary built",
        extra={
            "run_id": run.run_id,
            "summary_id": summary_id,
            "process_count": first_execution.process_count,
            "cached_process_count": resume_execution.cached_process_count,
            "package_bytes": package_inventory.total_bytes_excluding_summary,
        },
    )
    return ResourceSummaryOutput(summary_id, output, record)
