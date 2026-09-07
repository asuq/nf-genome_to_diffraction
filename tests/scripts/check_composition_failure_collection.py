"""Exercise the production beam graph after exhausted native task failures.

Only the scientific CLI is replaced by a file-producing fixture. The actual
Nextflow planner/attempt/collector graph and retry policy execute unchanged.
Python collector contracts are covered separately by unit tests.
"""

import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_FAKE_CLI = """
import csv
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
action = args[args.index("composition") + 1]
def value(flag):
    return args[args.index(flag) + 1]
output = Path(value("--outdir"))
if action == "plan-depth":
    output.mkdir()
    (output / "composition_depth_input_manifest.json").write_text(json.dumps({
        "parent_depth": 1, "target_depth": 2, "attempt_count": 2,
    }))
    (output / "composition_attempt_inventory.json").write_text(json.dumps({
        "attempts": [{
            "attempt_id": f"compattempt_{index:064x}",
            "resource_plan": {
                "base_cpus": 1, "base_memory_gb": 1, "base_time_hours": 1,
            },
        } for index in (1, 2)],
    }))
elif action == "run-attempt":
    if value("--attempt-id").endswith("1") or os.environ["BEAM_FIXTURE_MODE"] == "all":
        print("deliberate scheduler failure", file=sys.stderr)
        sys.exit(137)
    output.mkdir()
    (output / "native.fixture").write_text("observed native output\\n")
elif action == "collect-depth":
    observed = [args[index + 1] for index, token in enumerate(args)
                if token == "--attempt-result"]
    expected_count = 0 if os.environ["BEAM_FIXTURE_MODE"] == "all" else 1
    assert len(observed) == expected_count, observed
    assert all(Path(path, "native.fixture").is_file() for path in observed)
    with Path(value("--scheduler-trace")).open() as stream:
        tasks = [row for row in csv.DictReader(stream, delimiter="\\t")
                 if row["process"].endswith(":RUN_PHASE3_BEAM_ATTEMPT")]
    failures = [row for row in tasks if row["tag"].endswith("1")]
    assert sorted(row["attempt"] for row in failures) == ["1", "2"], failures
    assert all(row["status"] == "FAILED" and row["exit"] == "137" for row in failures)
    assert value("--workflow-run-id")
    assert Path(value("--task-work-root")).is_dir()
    output.mkdir()
    (output / "composition_beam_depth_result.json").write_text(json.dumps({
        "status": "terminal", "stop_reason": "composition_depth_incomplete",
        "attempt_count": 2, "native_output_count": expected_count,
        "depth_complete": False,
    }))
else:
    raise AssertionError(action)
"""


def check_failure_collection(repository: Path) -> None:
    """Require collector dispatch with partial and absent native results."""

    for mode in ("mixed", "all"):
        _check_failure_case(repository, mode)


def _check_failure_case(repository: Path, mode: str) -> None:

    with tempfile.TemporaryDirectory(
        prefix="nf-gtd-beam-failure-", dir="/tmp"
    ) as temporary:
        root = Path(temporary)
        binary = root / "bin"
        binary.mkdir()
        cli = binary / "genome-to-diffraction"
        cli.write_text(f"#!{sys.executable}\n{_FAKE_CLI}", encoding="ascii")
        cli.chmod(0o755)
        placeholder = root / "fixture-input"
        placeholder.write_text("synthetic fixture\n", encoding="ascii")
        config = root / "nextflow.config"
        config.write_text(
            f"includeConfig '{repository / 'conf/base.config'}'\n"
            "cleanup = false\n"
            "process.executor = 'local'\n",
            encoding="ascii",
        )
        workflow = root / "main.nf"
        imported_workflow = repository / "workflows/phase3_composition_beam_workflow"
        fields = ", ".join(
            "0" if index == 16 else "25" if index == 17 else f"file('{placeholder}')"
            for index in range(1, 26)
        )
        workflow.write_text(
            "nextflow.enable.types = true\n"
            "include { PHASE3_COMPOSITION_DEPTH_WORKFLOW } "
            f"from '{imported_workflow}'\n"
            "params {\n outdir: Path\n cache_root: Path\n}\n"
            "workflow {\n"
            f" items = channel.of(tuple('failure_case', {fields}))\n"
            " PHASE3_COMPOSITION_DEPTH_WORKFLOW(items)\n}\n",
            encoding="ascii",
        )
        output = root / "results"
        environment = dict(os.environ)
        environment["PATH"] = f"{binary}{os.pathsep}{environment['PATH']}"
        environment["NXF_HOME"] = str(root / "nxf-home")
        environment["BEAM_FIXTURE_MODE"] = mode
        completed = subprocess.run(
            [
                "nextflow",
                "-C",
                str(config),
                "run",
                str(workflow),
                "--outdir",
                str(output),
                "--cache_root",
                str(root / "cache"),
            ],
            cwd=repository,
            env=environment,
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode:
            raise RuntimeError(
                "beam failure collection failed:\n"
                f"{completed.stdout}\n{completed.stderr}"
            )
        result = (
            output
            / "composition_beam_failure_case_depth2"
            / "composition_beam_depth_result.json"
        )
        if not result.is_file():
            raise RuntimeError("missing native result suppressed the depth collector")
        with (output / "pipeline_info/trace.tsv").open(
            encoding="utf-8", newline=""
        ) as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        if (
            sum(
                row["process"].endswith(":COLLECT_PHASE3_COMPOSITION_DEPTH")
                for row in rows
            )
            != 1
        ):
            raise RuntimeError("partial depth did not schedule exactly one collector")


if __name__ == "__main__":
    check_failure_collection(Path(__file__).resolve().parents[2])
    print("Composition missing-output collection and single retry passed.")
