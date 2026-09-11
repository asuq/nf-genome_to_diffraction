"""Resolve the maintained Raven profile against the actual offline M6 stage."""

import csv
import subprocess
from pathlib import Path

from tests.scripts.check_nextflow import _environment

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
