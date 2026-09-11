"""Run the existing CI check groups concurrently with isolated test state.

The CI workflow defines the required checks; Pixi defines their commands. This
local runner changes scheduling only, retaining sequential checks within each
group and every test's execution/resume pairing. It requires the locked Python
3.14/Pixi environment. Per-check logs and a JSON result retain timings, resource
settings and explicit failed/skipped states; a partial gate never succeeds.
Nextflow history/cache/logs and pytest temporary roots are run-owned. No scientific
workflow, input, acceptance threshold, task retry or source cache is changed.
Unit tests cover plan validation, overlap, isolation, failure and cancellation.
"""

import argparse
import asyncio
import json
import os
import re
import signal
import sys
import tempfile
import time
import tomllib
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from genome_to_diffraction.checksums import atomic_write_json, sha256_file

REPOSITORY = Path(__file__).resolve().parents[2]
# Start the observed longest group first; the remaining independent groups fill
# free slots. These are the existing CI groups, not a second test inventory.
LANE_ORDER = (
    "nextflow-core",
    "unit",
    "integration",
    "quality",
    "scientific-stubs-a",
    "scientific-stubs-b",
)
PYTEST_TASKS = frozenset({"test-unit", "test-contract", "test-integration"})
_TASK_COMMAND = re.compile(r"pixi run --locked ([a-z][a-z0-9-]*)")


@dataclass(frozen=True)
class CheckLane:
    """One existing CI group and its ordered concrete Pixi checks."""

    name: str
    tasks: tuple[str, ...]


@dataclass(frozen=True)
class CheckBudget:
    """Resolved group and nested-worker limits for one local check."""

    cpu_budget: int
    parallel_lanes: int
    workers_per_lane: int


def load_check_lanes(repository: Path) -> tuple[CheckLane, ...]:
    """Read the actual CI commands and reject unsupported or incomplete plans."""

    workflow = yaml.safe_load((repository / ".github/workflows/ci.yml").read_text())
    with (repository / "pixi.toml").open("rb") as handle:
        tasks = tomllib.load(handle)["tasks"]
    if not isinstance(workflow, dict) or not isinstance(workflow.get("jobs"), dict):
        raise ValueError("CI workflow has no job mapping")
    jobs = workflow["jobs"]
    if set(jobs) != set(LANE_ORDER):
        raise ValueError("CI groups differ from the reviewed local check groups")
    lanes: list[CheckLane] = []
    observed: set[str] = set()
    for name in LANE_ORDER:
        job = jobs[name]
        if not isinstance(job, dict) or "needs" in job or "strategy" in job:
            raise ValueError(f"CI group {name} is not an independent fixed group")
        steps = job.get("steps")
        if not isinstance(steps, list):
            raise ValueError(f"CI group {name} has no steps")
        names: list[str] = []
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError(f"CI group {name} contains an invalid step")
            if "run" not in step:
                continue
            command = step["run"]
            match = (
                _TASK_COMMAND.fullmatch(command) if isinstance(command, str) else None
            )
            if match is None or "if" in step or "continue-on-error" in step:
                raise ValueError(f"CI group {name} contains an unsupported check")
            task = match[1]
            if task == "check" or not isinstance(tasks.get(task), str):
                raise ValueError(f"CI check {task} is not one concrete Pixi task")
            if task in observed:
                raise ValueError(f"CI check occurs more than once: {task}")
            observed.add(task)
            names.append(task)
        if not names:
            raise ValueError(f"CI group {name} contains no checks")
        lanes.append(CheckLane(name, tuple(names)))
    return tuple(lanes)


def check_budget(cpus: int, jobs: int | None, lane_count: int) -> CheckBudget:
    """Bound local group concurrency and subdivide the available CPU budget."""

    if cpus < 1 or lane_count < 1:
        raise ValueError("CPU budget and check-group count must be positive")
    resolved = min(3, max(1, cpus // 2), lane_count) if jobs is None else jobs
    if not 1 <= resolved <= min(cpus, lane_count):
        raise ValueError("parallel groups must be within the CPU and group counts")
    return CheckBudget(cpus, resolved, max(1, cpus // resolved))


def check_environment(root: Path, budget: CheckBudget) -> dict[str, str]:
    """Isolate Nextflow state and prevent nested numerical/pytest oversubscription."""

    environment = dict(os.environ)
    for name in ("nxf-home", "nxf-cache", "nxf-temp"):
        (root / name).mkdir()
    environment.update(
        {
            "NXF_HOME": str(root / "nxf-home"),
            "NXF_CACHE_DIR": str(root / "nxf-cache"),
            "NXF_LOG_FILE": str(root / "nextflow.log"),
            "NXF_TEMP": str(root / "nxf-temp"),
            "NXF_WORK": str(root / "work"),
            "NXF_OPTS": "",
            "NXF_JVM_ARGS": (
                f"-Xms256m -Xmx2g -XX:ActiveProcessorCount={budget.workers_per_lane}"
            ),
            "PYTEST_XDIST_AUTO_NUM_WORKERS": str(budget.workers_per_lane),
            "POLARS_MAX_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }
    )
    return environment


async def _stop_child(process: asyncio.subprocess.Process) -> None:
    """Stop only this runner's local process group when the runner is interrupted."""

    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        await process.wait()
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        # The owned child may exit between the grace-period timeout and signal.
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()


async def run_lane(
    lane: CheckLane,
    *,
    repository: Path,
    output: Path,
    budget: CheckBudget,
    semaphore: asyncio.Semaphore,
) -> list[dict[str, object]]:
    """Keep one CI group's check order and preserve every completion or omission."""

    results: list[dict[str, object]] = []
    async with semaphore:
        failed = False
        for task in lane.tasks:
            root = output / lane.name / task
            root.mkdir(parents=True)
            log = root / "check.log"
            command = ["pixi", "run", "--locked", "--skip-deps", task]
            if task in PYTEST_TASKS:
                command.extend(("--basetemp", str(root / "pytest")))
            record: dict[str, object] = {
                "lane": lane.name,
                "task": task,
                "command": command,
                "log": str(log.relative_to(output)),
                "status": "skipped",
                "exit_code": None,
                "elapsed_seconds": 0.0,
            }
            if failed:
                record["log"] = None
                record["reason"] = "earlier check in this group failed"
                results.append(record)
                atomic_write_json(root / "result.json", record)
                continue
            environment = check_environment(root, budget)
            print(f"[{lane.name}] START {task}", flush=True)
            started = time.monotonic()
            record["started_at"] = datetime.now(UTC).isoformat()
            try:
                with log.open("xb") as stream:
                    process = await asyncio.create_subprocess_exec(
                        *command,
                        cwd=repository,
                        env=environment,
                        stdout=stream,
                        stderr=asyncio.subprocess.STDOUT,
                        start_new_session=True,
                    )
                    try:
                        code = await process.wait()
                    except asyncio.CancelledError:
                        await _stop_child(process)
                        record["status"] = "cancelled"
                        raise
                record["exit_code"] = code
                record["status"] = "passed" if code == 0 else "failed"
            except OSError as error:
                record["status"] = "failed"
                record["launch_error"] = str(error)
            finally:
                record["elapsed_seconds"] = round(time.monotonic() - started, 3)
                record["completed_at"] = datetime.now(UTC).isoformat()
                record["log_sha256"] = sha256_file(log) if log.is_file() else None
                atomic_write_json(root / "result.json", record)
            results.append(record)
            failed = record["status"] != "passed"
            print(
                f"[{lane.name}] {str(record['status']).upper()} {task} "
                f"({record['elapsed_seconds']}s) log={log}",
                flush=True,
            )
    return results


async def run_checks(
    lanes: tuple[CheckLane, ...], repository: Path, output: Path, budget: CheckBudget
) -> list[dict[str, object]]:
    """Run independent groups concurrently; failure never becomes a passed gate."""

    semaphore = asyncio.Semaphore(budget.parallel_lanes)
    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(
                run_lane(
                    lane,
                    repository=repository,
                    output=output,
                    budget=budget,
                    semaphore=semaphore,
                )
            )
            for lane in lanes
        ]
    return [record for task in tasks for record in task.result()]


def main() -> int:
    """Run the complete local check using the CI-defined inventory."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, help="maximum concurrent CI groups")
    parser.add_argument("--cpus", type=int, help="total local CPU/worker budget")
    parser.add_argument("--output-dir", type=Path, help="new directory for check logs")
    args = parser.parse_args()
    available = os.process_cpu_count()
    cpus = args.cpus if args.cpus is not None else available
    if cpus is None or (available is not None and cpus > available):
        parser.error("CPU budget is unavailable or exceeds available CPUs")
    try:
        lanes = load_check_lanes(REPOSITORY)
        budget = check_budget(cpus, args.jobs, len(lanes))
    except ValueError as error:
        parser.error(str(error))
    if args.output_dir is None:
        output = Path(tempfile.mkdtemp(prefix="nf-gtd-check-", dir="/tmp"))
    else:
        output = args.output_dir.absolute()
        output.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "runner": "ci-groups-parallel-v1",
        "budget": asdict(budget),
        "nextflow_heap_gb": 2,
        "numerical_threads_per_process": 1,
        "lanes": [asdict(lane) for lane in lanes],
        "inputs_sha256": {
            name: sha256_file(REPOSITORY / name)
            for name in (
                "pixi.toml",
                "pixi.lock",
                ".github/workflows/ci.yml",
                "tests/scripts/run_check.py",
                "tests/conftest.py",
            )
        },
        "started_at": datetime.now(UTC).isoformat(),
        "passed": False,
    }
    atomic_write_json(output / "summary.json", manifest)
    print(f"Check logs: {output}\nBudget: {json.dumps(asdict(budget))}", flush=True)
    start = time.monotonic()
    try:
        records = asyncio.run(run_checks(lanes, REPOSITORY, output, budget))
    except KeyboardInterrupt:
        manifest["interrupted"] = True
        records = []
    expected = {task for lane in lanes for task in lane.tasks}
    passed = (
        len(records) == len(expected)
        and {record["task"] for record in records} == expected
        and all(record["status"] == "passed" for record in records)
    )
    manifest.update(
        {
            "results": records,
            "passed": passed,
            "elapsed_seconds": round(time.monotonic() - start, 3),
            "completed_at": datetime.now(UTC).isoformat(),
        }
    )
    atomic_write_json(output / "summary.json", manifest)
    print(
        f"Complete check: {'PASSED' if passed else 'FAILED'} "
        f"({manifest['elapsed_seconds']}s); summary={output / 'summary.json'}",
        flush=True,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
