"""Regressions for complete, bounded parallel local check execution."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import BinaryIO, TypedDict, Unpack

import pytest
import yaml

from tests.scripts import run_check


class SpawnOptions(TypedDict):
    cwd: Path
    env: dict[str, str]
    stdout: BinaryIO
    stderr: int
    start_new_session: bool


def _repository(root: Path) -> Path:
    (root / ".github/workflows").mkdir(parents=True)
    jobs = {
        name: {"steps": [{"run": f"pixi run --locked task-{number}"}]}
        for number, name in enumerate(run_check.LANE_ORDER)
    }
    (root / ".github/workflows/ci.yml").write_text(yaml.safe_dump({"jobs": jobs}))
    (root / "pixi.toml").write_text(
        "[tasks]\n" + "\n".join(f'task-{i} = "true"' for i in range(len(jobs)))
    )
    return root


def test_plan_reuses_every_ci_group_exactly_once(tmp_path: Path) -> None:
    lanes = run_check.load_check_lanes(_repository(tmp_path / "repo"))
    assert tuple(lane.name for lane in lanes) == run_check.LANE_ORDER
    assert [lane.tasks for lane in lanes] == [
        (f"task-{i}",) for i in range(len(run_check.LANE_ORDER))
    ]


@pytest.mark.parametrize(
    "mutation", ("duplicate", "shell", "needs", "missing", "alias")
)
def test_plan_rejects_unsafe_or_changed_inventory(
    tmp_path: Path, mutation: str
) -> None:
    repository = _repository(tmp_path / "repo")
    path = repository / ".github/workflows/ci.yml"
    workflow = yaml.safe_load(path.read_text())
    job = workflow["jobs"]["unit"]
    if mutation == "duplicate":
        job["steps"] = [{"run": "pixi run --locked task-0"}]
    elif mutation == "shell":
        job["steps"] = [{"run": "pixi run --locked task-1; true"}]
    elif mutation == "needs":
        job["needs"] = "quality"
    elif mutation == "missing":
        del workflow["jobs"]["quality"]
    else:
        (repository / "pixi.toml").write_text(
            '[tasks]\ntask-0 = { depends-on = ["check"] }\n'
        )
    path.write_text(yaml.safe_dump(workflow))
    with pytest.raises(ValueError):
        run_check.load_check_lanes(repository)


def test_budget_is_bounded_and_divides_nested_workers() -> None:
    assert run_check.check_budget(8, None, 6) == run_check.CheckBudget(8, 3, 2)
    assert run_check.check_budget(2, None, 6) == run_check.CheckBudget(2, 1, 2)
    assert run_check.check_budget(8, 1, 6) == run_check.CheckBudget(8, 1, 8)
    for cpus, jobs in ((0, None), (2, 3), (8, 0), (8, 7)):
        with pytest.raises(ValueError):
            run_check.check_budget(cpus, jobs, 6)


def test_environment_has_no_shared_nextflow_history_or_logs(tmp_path: Path) -> None:
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    budget = run_check.CheckBudget(8, 3, 2)
    environments = [run_check.check_environment(root, budget) for root in (left, right)]
    for name in ("NXF_HOME", "NXF_CACHE_DIR", "NXF_LOG_FILE", "NXF_TEMP", "NXF_WORK"):
        assert environments[0][name] != environments[1][name]
    assert environments[0]["PYTEST_XDIST_AUTO_NUM_WORKERS"] == "2"
    assert environments[0]["POLARS_MAX_THREADS"] == "1"
    assert "-Xmx2g" in environments[0]["NXF_JVM_ARGS"]
    assert "-XX:ActiveProcessorCount=2" in environments[0]["NXF_JVM_ARGS"]


def test_pytest_has_case_owned_nextflow_state(tmp_path: Path) -> None:
    root = Path(os.environ["NXF_CACHE_DIR"]).parent
    assert root.name.startswith("nextflow-state") and root.parent == tmp_path.parent
    assert Path(os.environ["NXF_LOG_FILE"]).parent == root
    assert not tuple(tmp_path.iterdir())


def test_groups_overlap_but_checks_in_one_group_keep_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = 0
    peak = 0
    events: list[str] = []
    budgets: list[str] = []

    class Process:
        async def wait(self) -> int:
            nonlocal active
            await asyncio.sleep(0.03)
            active -= 1
            return 0

    async def spawn(*command: str, **kwargs: Unpack[SpawnOptions]) -> Process:
        nonlocal active, peak
        task = command[4]
        events.append(task)
        active += 1
        peak = max(peak, active)
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        budgets.append(environment["PYTEST_XDIST_AUTO_NUM_WORKERS"])
        return Process()

    monkeypatch.setattr(run_check.asyncio, "create_subprocess_exec", spawn)
    lanes = (
        run_check.CheckLane("a", ("first-a", "second-a")),
        run_check.CheckLane("b", ("first-b", "second-b")),
        run_check.CheckLane("c", ("first-c",)),
    )
    results = asyncio.run(
        run_check.run_checks(
            lanes, tmp_path, tmp_path / "output", run_check.CheckBudget(4, 2, 2)
        )
    )
    assert peak == 2
    assert events[:2] == ["first-a", "first-b"]
    assert events.index("first-c") > events.index("second-a")
    assert len(results) == 5 and all(row["status"] == "passed" for row in results)
    assert budgets == ["2"] * 5


def test_failure_is_retained_and_only_its_group_remainder_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual_spawn = asyncio.create_subprocess_exec

    async def spawn(
        *command: str, **kwargs: Unpack[SpawnOptions]
    ) -> asyncio.subprocess.Process:
        return await actual_spawn(
            sys.executable,
            "-c",
            "import sys; print('retained failure'); sys.exit(7)"
            if command[4] == "bad"
            else "print('passed')",
            **kwargs,
        )

    monkeypatch.setattr(run_check.asyncio, "create_subprocess_exec", spawn)
    output = tmp_path / "output"
    lanes = (
        run_check.CheckLane("a", ("bad", "later")),
        run_check.CheckLane("b", ("good",)),
    )
    results = asyncio.run(
        run_check.run_checks(lanes, tmp_path, output, run_check.CheckBudget(2, 2, 1))
    )
    assert [row["status"] for row in results] == ["failed", "skipped", "passed"]
    assert results[0]["exit_code"] == 7
    assert results[1]["exit_code"] is None and results[1]["log"] is None
    assert "retained failure" in (output / "a/bad/check.log").read_text()
    assert json.loads((output / "b/good/result.json").read_text())["status"] == "passed"


def test_cancellation_stops_only_the_started_test_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual_spawn = asyncio.create_subprocess_exec
    children: list[asyncio.subprocess.Process] = []

    async def spawn(
        *command: str, **kwargs: Unpack[SpawnOptions]
    ) -> asyncio.subprocess.Process:
        process = await actual_spawn(
            sys.executable, "-c", "import time; time.sleep(60)", **kwargs
        )
        children.append(process)
        return process

    async def execute() -> None:
        task = asyncio.create_task(
            run_check.run_checks(
                (run_check.CheckLane("a", ("slow",)),),
                tmp_path,
                tmp_path / "output",
                run_check.CheckBudget(1, 1, 1),
            )
        )
        while not children:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    monkeypatch.setattr(run_check.asyncio, "create_subprocess_exec", spawn)
    asyncio.run(execute())
    assert len(children) == 1 and children[0].returncode is not None
    record = json.loads((tmp_path / "output/a/slow/result.json").read_text())
    assert record["status"] == "cancelled" and record["exit_code"] is None
