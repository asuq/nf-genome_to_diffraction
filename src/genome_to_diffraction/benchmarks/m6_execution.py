"""Validate M6 execution policy and child Slurm resource evidence.

The input policy fixes driver/per-job limits, batching, concurrency semantics,
and shared-cache eligibility. The fixed Viper and Marmic policies use distinct
policy identities because their scheduler queue and submission-rate controls
differ. A completed Nextflow trace is normalised into a
checksum-bound inventory of native job IDs, requested resources, observed CPU
and peak RSS, and aggregate concurrency. Missing trace fields, unparsable
values, changed counts, or policy violations fail loudly. The policy checksum
is the cache/provenance identity; unit and fake-Viper tests cover parsing,
per-job gates, and collection compatibility.
"""

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Self, cast

from pydantic import ValidationError, model_validator

from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    PositiveFloat,
    PositiveInt,
    Sha256Hex,
)
from genome_to_diffraction.schemas.io import load_json_document, load_yaml_document

_MEMORY = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*([KMGT]B)$", re.I)


class M6DriverPolicy(ContractModel):
    maximum_cpus: PositiveInt
    maximum_memory_gb: PositiveFloat
    maximum_scheduler_hours: PositiveFloat


class M6PerJobPolicy(ContractModel):
    maximum_cpus: PositiveInt
    maximum_memory_gb: PositiveFloat
    maximum_scheduler_hours: PositiveFloat


class M6ConcurrencyPolicy(ContractModel):
    aggregate_policy: Literal["scheduler_managed"]
    phenix_policy: Literal["scheduler_managed"]
    queue_size: PositiveInt
    submit_rate_limit: str


class M6SearchProviderPolicy(ContractModel):
    cpus: PositiveInt
    maximum_unique_sequences: PositiveInt
    maximum_residues: PositiveInt


class M6SearchBatchingPolicy(ContractModel):
    global_exact_sequence_deduplication: Literal[True]
    mmseqs2: M6SearchProviderPolicy
    foldseek: M6SearchProviderPolicy


class M6SharedCachePolicy(ContractModel):
    eligible_stages: tuple[
        Literal[
            "catalogue_import",
            "pdb_sequence_search",
            "prostt5_foldseek_search",
        ],
        ...,
    ]
    truthless_only: Literal[True]
    require_content_addressed_key: Literal[True]
    require_complete_checksum_manifest: Literal[True]


class M6ExecutionPolicy(ContractModel):
    schema_version: Literal["1.0"]
    policy_id: Literal[
        "m6_nextflow_slurm_v1",
        "m6_nextflow_slurm_marmic_v1",
    ]
    site_id: Literal["marmic", "viper-cpu"]
    orchestrator: Literal["nextflow_dsl2"]
    executor: Literal["slurm"]
    driver: M6DriverPolicy
    per_job: M6PerJobPolicy
    concurrency: M6ConcurrencyPolicy
    search_batching: M6SearchBatchingPolicy
    tool_runtime_timeouts: Literal[False]
    shared_cache: M6SharedCachePolicy

    @model_validator(mode="after")
    def _validate_resource_hierarchy(self) -> Self:
        expected_site = {
            "m6_nextflow_slurm_v1": "viper-cpu",
            "m6_nextflow_slurm_marmic_v1": "marmic",
        }[self.policy_id]
        if self.site_id != expected_site:
            raise ValueError("M6 execution policy ID and site ID disagree")
        search_cpus = (
            self.search_batching.mmseqs2.cpus,
            self.search_batching.foldseek.cpus,
        )
        if any(cpus > self.per_job.maximum_cpus for cpus in search_cpus):
            raise ValueError("M6 search CPUs exceed the per-job execution limit")
        if self.driver.maximum_cpus > self.per_job.maximum_cpus:
            raise ValueError("M6 driver CPUs exceed the per-job execution limit")
        return self


class M6ChildJobRecord(ContractModel):
    process: NonEmptyString
    tag: str | None = None
    status: str
    native_job_id: NonEmptyString
    requested_cpus: PositiveInt
    requested_memory_gb: PositiveFloat
    requested_time_hours: PositiveFloat
    start: datetime | None = None
    complete: datetime | None = None
    peak_rss_gb: float | None = None
    observed_cpu_percent: float | None = None
    phenix_job: bool


class M6ResourceEvidence(ContractModel):
    schema_version: Literal["1.0"]
    execution_policy_id: str
    execution_policy_sha256: str
    child_job_count: int
    maximum_cpu_per_job: int
    maximum_memory_gb_per_job: float
    maximum_scheduler_hours_per_job: float
    maximum_peak_rss_gb: float
    maximum_observed_cpu_percent: float
    peak_running_jobs: int
    peak_aggregate_cpus: int
    peak_aggregate_memory_gb: float
    peak_concurrent_phenix_jobs: int
    per_job_bounds_passed: bool
    jobs: tuple[M6ChildJobRecord, ...]
    controller_stages: tuple[M6ChildJobRecord, ...] = ()

    @model_validator(mode="after")
    def _validate_job_inventory(self) -> Self:
        if self.child_job_count != len(self.jobs):
            raise ValueError("M6 child-job count changed")
        if any(
            job.process.rsplit(":", maxsplit=1)[-1] != "M6_STAGE_COORDINATES"
            or job.status != "COMPLETED"
            or job.phenix_job
            for job in self.controller_stages
        ):
            raise ValueError("M6 controller-stage inventory changed")
        if any(
            job.process.rsplit(":", maxsplit=1)[-1] == "M6_STAGE_COORDINATES"
            for job in self.jobs
        ):
            raise ValueError("M6 controller stage was classified as a Slurm child")
        derived_cpu = max((job.requested_cpus for job in self.jobs), default=0)
        derived_memory = max(
            (job.requested_memory_gb for job in self.jobs), default=0.0
        )
        derived_time = max((job.requested_time_hours for job in self.jobs), default=0.0)
        if (
            self.maximum_cpu_per_job != derived_cpu
            or self.maximum_memory_gb_per_job != derived_memory
            or self.maximum_scheduler_hours_per_job != derived_time
        ):
            raise ValueError("M6 child-job resource maxima changed")
        return self


@dataclass(frozen=True, slots=True)
class M6ResourceEvidenceRequest:
    policy: Path
    trace: Path
    output: Path


class M6ChildOutputFile(ContractModel):
    """One path-free checksum within a completed scientific task directory."""

    relative_path: NonEmptyString
    sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_relative_path(self) -> Self:
        path = Path(self.relative_path)
        if path.is_absolute() or ".." in path.parts or str(path) != self.relative_path:
            raise ValueError("M6 child output path is not a safe relative path")
        return self


class M6ChildOutputTask(ContractModel):
    """One exact Nextflow task and its complete non-staged child outputs."""

    process: NonEmptyString
    tag: NonEmptyString
    task_hash: NonEmptyString
    status: Literal["COMPLETED", "CACHED"]
    outputs: tuple[M6ChildOutputFile, ...]

    @model_validator(mode="after")
    def _validate_outputs(self) -> Self:
        paths = tuple(item.relative_path for item in self.outputs)
        if not paths or paths != tuple(sorted(set(paths))):
            raise ValueError("M6 child output inventory is empty or not canonical")
        return self


class M6ChildOutputEvidence(ContractModel):
    """First-pass or checksum-bound resume inventory for every scientific task."""

    schema_version: Literal["1.0"]
    phase: Literal["first", "resume"]
    trace_sha256: Sha256Hex
    baseline_sha256: Sha256Hex | None = None
    task_count: PositiveInt
    tasks: tuple[M6ChildOutputTask, ...]

    @model_validator(mode="after")
    def _validate_tasks(self) -> Self:
        identities = tuple((task.process, task.tag) for task in self.tasks)
        expected_status = "COMPLETED" if self.phase == "first" else "CACHED"
        if (
            self.task_count != len(self.tasks)
            or identities != tuple(sorted(set(identities)))
            or any(task.status != expected_status for task in self.tasks)
            or (self.baseline_sha256 is None) != (self.phase == "first")
        ):
            raise ValueError("M6 child output task inventory is incomplete")
        return self


@dataclass(frozen=True, slots=True)
class M6ChildOutputEvidenceRequest:
    """Collect first outputs or compare one cached resume to that exact baseline."""

    trace: Path
    output: Path
    baseline: Path | None = None


def load_m6_execution_policy(path: Path) -> M6ExecutionPolicy:
    """Load the separately approved resource and orchestration policy."""

    try:
        payload = load_yaml_document(path.resolve(strict=True))
        return M6ExecutionPolicy.model_validate(payload)
    except (OSError, ValueError) as error:
        raise PublicControlError(f"invalid M6 execution policy: {error}") from error


def _memory_gb(value: str) -> float:
    text = value.strip()
    if text == "0":
        return 0.0
    match = _MEMORY.fullmatch(text)
    if match is None:
        raise PublicControlError(f"cannot parse Nextflow trace memory: {value}")
    amount = float(match.group(1))
    factor = {"KB": 1e-6, "MB": 1e-3, "GB": 1.0, "TB": 1e3}[match.group(2).upper()]
    return amount * factor


def _hours(value: str) -> float:
    text = value.strip()
    if text.endswith("d"):
        return float(text[:-1]) * 24.0
    if text.endswith("h"):
        return float(text[:-1])
    if text.endswith("m"):
        return float(text[:-1]) / 60.0
    if text.endswith("s"):
        return float(text[:-1]) / 3600.0
    parts = text.split(":")
    if len(parts) == 3:
        return int(parts[0]) + int(parts[1]) / 60.0 + float(parts[2]) / 3600.0
    raise PublicControlError(f"cannot parse Nextflow trace time: {value}")


def _timestamp(value: str) -> datetime | None:
    if not value.strip() or value.strip() == "-":
        return None
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def _cpu_percent(value: str) -> float | None:
    text = value.strip()
    if not text or text == "-":
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        parsed = float(text)
    except ValueError as error:
        raise PublicControlError(
            f"cannot parse Nextflow trace CPU percentage: {value}"
        ) from error
    if parsed < 0:
        raise PublicControlError("Nextflow trace CPU percentage is negative")
    return parsed


def _peak(records: tuple[M6ChildJobRecord, ...]) -> tuple[int, int, float, int]:
    events: list[tuple[datetime, int, M6ChildJobRecord]] = []
    for record in records:
        if record.start is None or record.complete is None:
            continue
        events.append((record.start, 1, record))
        events.append((record.complete, -1, record))
    running: set[str] = set()
    by_id = {record.native_job_id: record for record in records}
    peak_jobs = peak_cpu = peak_phenix = 0
    peak_memory = 0.0
    for _, direction, record in sorted(events, key=lambda item: (item[0], item[1])):
        if direction < 0:
            running.discard(record.native_job_id)
        else:
            running.add(record.native_job_id)
        current = [by_id[job_id] for job_id in running]
        peak_jobs = max(peak_jobs, len(current))
        peak_cpu = max(peak_cpu, sum(item.requested_cpus for item in current))
        peak_memory = max(
            peak_memory, sum(item.requested_memory_gb for item in current)
        )
        peak_phenix = max(peak_phenix, sum(item.phenix_job for item in current))
    return peak_jobs, peak_cpu, peak_memory, peak_phenix


def collect_m6_resource_evidence(
    request: M6ResourceEvidenceRequest,
) -> M6ResourceEvidence:
    """Parse a fixed Nextflow trace into auditable Slurm resource evidence."""

    policy_path = request.policy.resolve(strict=True)
    trace = request.trace.resolve(strict=True)
    policy = load_m6_execution_policy(policy_path)
    records: list[M6ChildJobRecord] = []
    controller_stages: list[M6ChildJobRecord] = []
    with trace.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {
            "process",
            "tag",
            "status",
            "native_id",
            "cpus",
            "memory",
            "time",
            "start",
            "complete",
            "peak_rss",
            "%cpu",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise PublicControlError("M6 Nextflow trace lacks required resource fields")
        for row in reader:
            process = row["process"]
            peak_rss = row["peak_rss"].strip()
            record = M6ChildJobRecord(
                process=process,
                tag=row["tag"] or None,
                status=row["status"],
                native_job_id=row["native_id"],
                requested_cpus=int(row["cpus"]),
                requested_memory_gb=_memory_gb(row["memory"]),
                requested_time_hours=_hours(row["time"]),
                start=_timestamp(row["start"]),
                complete=_timestamp(row["complete"]),
                peak_rss_gb=(
                    None if not peak_rss or peak_rss == "-" else _memory_gb(peak_rss)
                ),
                observed_cpu_percent=_cpu_percent(row["%cpu"]),
                phenix_job=any(
                    token in process
                    for token in ("FIRST_COPY", "ADDITIONAL_COPY", "REFINEMENT")
                ),
            )
            if process.rsplit(":", maxsplit=1)[-1] == "M6_STAGE_COORDINATES":
                if (
                    record.requested_cpus > policy.driver.maximum_cpus
                    or record.requested_memory_gb > policy.driver.maximum_memory_gb
                    or record.requested_time_hours
                    > policy.driver.maximum_scheduler_hours
                ):
                    raise PublicControlError(
                        "M6 controller stage exceeds driver bounds"
                    )
                controller_stages.append(record)
            else:
                records.append(record)
    jobs = tuple(records)
    peak_jobs, peak_cpu, peak_memory, peak_phenix = _peak(jobs)
    max_cpu = max((job.requested_cpus for job in jobs), default=0)
    max_memory = max((job.requested_memory_gb for job in jobs), default=0.0)
    max_time = max((job.requested_time_hours for job in jobs), default=0.0)
    max_peak_rss = max(
        (job.peak_rss_gb for job in jobs if job.peak_rss_gb is not None),
        default=0.0,
    )
    max_observed_cpu = max(
        (
            job.observed_cpu_percent
            for job in jobs
            if job.observed_cpu_percent is not None
        ),
        default=0.0,
    )
    evidence = M6ResourceEvidence(
        schema_version="1.0",
        execution_policy_id=policy.policy_id,
        execution_policy_sha256=sha256_file(policy_path),
        child_job_count=len(jobs),
        maximum_cpu_per_job=max_cpu,
        maximum_memory_gb_per_job=max_memory,
        maximum_scheduler_hours_per_job=max_time,
        maximum_peak_rss_gb=max_peak_rss,
        maximum_observed_cpu_percent=max_observed_cpu,
        peak_running_jobs=peak_jobs,
        peak_aggregate_cpus=peak_cpu,
        peak_aggregate_memory_gb=peak_memory,
        peak_concurrent_phenix_jobs=peak_phenix,
        per_job_bounds_passed=(
            max_cpu <= policy.per_job.maximum_cpus
            and max_memory <= policy.per_job.maximum_memory_gb
            and max_time <= policy.per_job.maximum_scheduler_hours
        ),
        jobs=jobs,
        controller_stages=tuple(controller_stages),
    )
    request.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(request.output, evidence.model_dump(mode="json"))
    return evidence


def collect_m6_child_output_evidence(
    request: M6ChildOutputEvidenceRequest,
) -> M6ChildOutputEvidence:
    """Snapshot every first-pass child and refuse changed cached-resume children."""

    trace = request.trace.resolve(strict=True)
    baseline: M6ChildOutputEvidence | None = None
    baseline_sha256: str | None = None
    if request.baseline is not None:
        baseline_path = request.baseline.resolve(strict=True)
        try:
            baseline = M6ChildOutputEvidence.model_validate(
                load_json_document(baseline_path)
            )
        except (OSError, ValueError) as error:
            raise PublicControlError(
                f"M6 first-pass child output evidence is invalid: {error}"
            ) from error
        if baseline.phase != "first":
            raise PublicControlError("M6 child output baseline is not a first pass")
        baseline_sha256 = sha256_file(baseline_path)

    records: list[M6ChildOutputTask] = []
    with trace.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"process", "tag", "status", "hash", "workdir"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise PublicControlError("M6 child output trace lacks required fields")
        for row in reader:
            try:
                if row["status"] not in {"COMPLETED", "CACHED"}:
                    raise ValueError("M6 child task did not complete or cache")
                status = cast(Literal["COMPLETED", "CACHED"], row["status"])
                work = Path(row["workdir"]).resolve(strict=True)
                files = tuple(
                    M6ChildOutputFile(
                        relative_path=str(path.relative_to(work)),
                        sha256=sha256_file(path),
                    )
                    for path in sorted(
                        work.rglob("*"), key=lambda item: str(item.relative_to(work))
                    )
                    if path.is_file()
                    and not path.is_symlink()
                    and not path.relative_to(work).parts[0].startswith(".")
                )
                records.append(
                    M6ChildOutputTask(
                        process=row["process"],
                        tag=row["tag"],
                        task_hash=row["hash"],
                        status=status,
                        outputs=files,
                    )
                )
            except (OSError, ValueError) as error:
                raise PublicControlError(
                    f"M6 task has missing or changed child outputs: {row['tag']}"
                ) from error

    try:
        ordered_records = tuple(
            sorted(records, key=lambda item: (item.process, item.tag))
        )
        evidence = M6ChildOutputEvidence(
            schema_version="1.0",
            phase="first" if baseline is None else "resume",
            trace_sha256=sha256_file(trace),
            baseline_sha256=baseline_sha256,
            task_count=len(records),
            tasks=ordered_records,
        )
    except ValidationError as error:
        raise PublicControlError(
            f"M6 child output evidence is invalid: {error}"
        ) from error
    if baseline is not None:
        if evidence.task_count != baseline.task_count:
            raise PublicControlError("M6 cached child output task inventory changed")
        for expected, observed in zip(baseline.tasks, evidence.tasks, strict=True):
            if (
                expected.process != observed.process
                or expected.tag != observed.tag
                or expected.task_hash != observed.task_hash
                or expected.outputs != observed.outputs
            ):
                raise PublicControlError(
                    "M6 cached task has missing or changed child outputs: "
                    f"{expected.tag}"
                )

    atomic_write_json(request.output, evidence.model_dump(mode="json"))
    return evidence
