"""Resolve the maintained Raven profile against the actual offline M6 stage."""

import csv
import json
import subprocess
import sys
from pathlib import Path

from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
from genome_to_diffraction.benchmarks.m6_runner import (
    M6RunnerBundleRequest,
    build_m6_runner_bundle,
)
from tests.scripts.check_nextflow import _environment
from tests.unit.test_m6_benchmark import PROTOCOL, _prepared_manifest

REPOSITORY = Path(__file__).resolve().parents[2]


def test_raven_coordinate_stage_runs_locally_with_bounded_resources(
    tmp_path: Path,
) -> None:
    (tmp_path / "external").symlink_to(
        REPOSITORY / "external", target_is_directory=True
    )
    (tmp_path / "tests").symlink_to(REPOSITORY / "tests", target_is_directory=True)
    entrypoint = tmp_path / "main.nf"
    entrypoint.write_text(
        "nextflow.enable.types = true\n"
        "include { M6_STAGE_COORDINATES } from "
        f"'{REPOSITORY}/modules/local/m6_nextflow_tasks'\n"
        "workflow {\n"
        "    M6_STAGE_COORDINATES(channel.of(\n"
        "        tuple('M6C001', 'task', 'catalogue', 'preflight', 'policy', 'db')\n"
        "    ))\n"
        "}\n",
        encoding="ascii",
    )
    config = tmp_path / "nextflow.config"
    config.write_text(
        f"includeConfig '{REPOSITORY}/conf/raven.config'\n"
        # Only remove the unavailable site module command; routing and resources
        # remain the actual maintained Raven configuration.
        "profiles { raven { process {\n"
        "    withName: M6_STAGE_COORDINATES { beforeScript = '' }\n"
        "} } }\n"
        "trace.enabled = true\n"
        "trace.file = 'trace.tsv'\n"
        "trace.fields = 'process,status,cpus,memory,time,workdir'\n",
        encoding="ascii",
    )
    environment = _environment(tmp_path / "nxf-home")
    environment["HOSTNAME"] = "raven03"
    environment["NXF_APPTAINER_CACHEDIR"] = "/ptmp/test/apptainer-cache"
    result = subprocess.run(
        [
            "nextflow",
            "-C",
            str(config),
            "run",
            str(entrypoint),
            "-stub-run",
            "-ansi-log",
            "false",
            "-profile",
            "raven",
            "-w",
            str(tmp_path / "work"),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    log = Path(environment["NXF_LOG_FILE"]).read_text()
    assert "executor: local" in log
    assert "executor: slurm" not in log
    with (tmp_path / "trace.tsv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == 1
    row = rows[0]
    assert row["process"] == "M6_STAGE_COORDINATES"
    assert row["status"] == "COMPLETED"
    assert row["cpus"] == "1"
    assert row["memory"] == "4 GB"
    assert row["time"] == "1d"
    assert (Path(row["workdir"]) / "m6_coordinate_stage").is_dir()


def test_raven_real_planner_uses_run_source_with_a_reused_older_runtime(
    tmp_path: Path,
) -> None:
    """Exercise the real CLI/module, not its stub, with stale inherited source."""

    for name in ("external", "src"):
        (tmp_path / name).symlink_to(REPOSITORY / name, target_is_directory=True)
    preparation = _prepared_manifest(tmp_path, load_m6_protocol(PROTOCOL))
    bundle = build_m6_runner_bundle(
        M6RunnerBundleRequest(
            protocol=PROTOCOL,
            preparation_manifest=preparation,
            output_directory=tmp_path / "runner",
            archive=tmp_path / "runner.tar",
        )
    )

    # Model a reusable environment whose installed application predates the
    # new flag. Dependencies/interpreter remain the actual locked environment.
    stale = tmp_path / "older-runtime-package"
    package = stale / "genome_to_diffraction"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="ascii")
    (package / "cli.py").write_text(
        "import argparse\n"
        "def main():\n"
        "    parser = argparse.ArgumentParser()\n"
        "    parser.parse_args()\n",
        encoding="ascii",
    )
    runtime_bin = tmp_path / ".pixi/envs/hpc/bin"
    runtime_bin.mkdir(parents=True)
    launcher = runtime_bin / "genome-to-diffraction"
    launcher.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "from genome_to_diffraction import cli\n"
        "pathlib.Path('source-binding.json').write_text(json.dumps({\n"
        "    'cli': str(pathlib.Path(cli.__file__).resolve()),\n"
        "    'pythonpath': os.environ.get('PYTHONPATH'),\n"
        "    'bytecode': os.environ.get('PYTHONDONTWRITEBYTECODE'),\n"
        "}))\n"
        "sys.exit(cli.main())\n",
        encoding="ascii",
    )
    launcher.chmod(0o755)
    module_bin = tmp_path / "module-bin"
    module_bin.mkdir()
    module = module_bin / "module"
    module.write_text(
        "#!/bin/bash\n[[ $# == 2 && $1 == load && $2 == apptainer/1.4.3 ]]\n",
        encoding="ascii",
    )
    module.chmod(0o755)
    environment = _environment(tmp_path / "nxf-home")
    environment["PYTHONPATH"] = str(stale)
    environment["PATH"] = f"{module_bin}:{environment['PATH']}"
    environment["HOSTNAME"] = "raven03"
    environment["NXF_APPTAINER_CACHEDIR"] = "/ptmp/test/apptainer-cache"
    old = subprocess.run(
        [str(launcher), "--execution-purpose", "native_control"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert old.returncode == 2
    assert "unrecognized arguments: --execution-purpose native_control" in old.stderr
    assert json.loads((tmp_path / "source-binding.json").read_text())["cli"] == str(
        package / "cli.py"
    )

    entrypoint = tmp_path / "main.nf"
    entrypoint.write_text(
        "nextflow.enable.types = true\n"
        "include { M6_PLAN_TRACK } from "
        f"'{REPOSITORY}/modules/local/m6_nextflow_tasks'\n"
        "workflow {\n"
        f"    M6_PLAN_TRACK(file('{bundle.runner_manifest.parent}'),\n"
        f"        file('{REPOSITORY}/tests/fixtures/stubs/database_manifest.json'),\n"
        f"        file('{REPOSITORY}/pixi.lock'),\n"
        "        'operational', 'native_control')\n"
        "}\n",
        encoding="ascii",
    )
    config = tmp_path / "nextflow.config"
    config.write_text(
        f"includeConfig '{REPOSITORY}/conf/raven.config'\n"
        # Only scheduler execution is localised. The real Raven beforeScript,
        # module command and application entry point must all execute unchanged.
        "profiles { raven { process {\n"
        "    withName: M6_PLAN_TRACK { executor = 'local' }\n"
        "} } }\n"
        "trace.enabled = true\n"
        "trace.file = 'trace.tsv'\n"
        "trace.fields = 'process,status,workdir'\n",
        encoding="ascii",
    )
    result = subprocess.run(
        [
            "nextflow",
            "-C",
            str(config),
            "run",
            str(entrypoint),
            "-ansi-log",
            "false",
            "-profile",
            "raven",
            "-w",
            str(tmp_path / "work"),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with (tmp_path / "trace.tsv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == 1
    assert rows[0]["process"] == "M6_PLAN_TRACK"
    assert rows[0]["status"] == "COMPLETED"
    work = Path(rows[0]["workdir"])
    binding = json.loads((work / "source-binding.json").read_text())
    assert binding == {
        "cli": str(REPOSITORY / "src/genome_to_diffraction/cli.py"),
        "pythonpath": str(tmp_path / "src"),
        "bytecode": "1",
    }
    plan = json.loads((work / "m6_track_plan/track_plan.json").read_text())
    assert plan["case_ids"] == ["M6C001", "M6C025"]
    assert plan["execution_purpose"] == "native_control"
    assert plan["benchmark_acceptance_claim"] is False
