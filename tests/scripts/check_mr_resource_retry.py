"""Prove one scaled retry is reused by the canonical Nextflow resume."""

import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURE = REPOSITORY / "tests/fixtures/stubs/mr_resource_retry"


def _run(command: list[str], environment: dict[str, str]) -> None:
    result = subprocess.run(
        command,
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode:
        raise RuntimeError(f"retry fixture failed:\n{result.stdout}\n{result.stderr}")


def _trace(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8", newline="") as stream:
        return tuple(csv.DictReader(stream, delimiter="\t"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nf-gtd-mr-resource-retry-") as raw:
        root = Path(raw)
        output = root / "results"
        work = root / "work"
        sentinel = root / "first-attempt-failed"
        command = [
            "nextflow",
            "-C",
            str(FIXTURE / "nextflow.config"),
            "run",
            str(FIXTURE / "main.nf"),
            "-work-dir",
            str(work),
            "--outdir",
            str(output),
            "--sentinel",
            str(sentinel),
        ]
        environment = dict(os.environ)
        environment.update(
            {
                "NXF_AGENT_MODE": "true",
                "NXF_ANSI_LOG": "false",
                "NXF_DISABLE_CHECK_LATEST": "true",
                "NXF_HOME": str(root / "nxf-home"),
            }
        )
        _run(command, environment)
        first = _trace(output / "trace.tsv")
        completed = tuple(row for row in first if row["status"] == "COMPLETED")
        if len(completed) != 1 or completed[0]["attempt"] != "2":
            raise RuntimeError("first run did not complete exactly one scaled retry")
        if (output / "result.txt").read_text(encoding="utf-8").strip() != (
            "same-scientific-task|2|2"
        ):
            raise RuntimeError("scaled retry did not receive attempt-two CPUs")

        _run([*command, "-resume"], environment)
        resumed = _trace(output / "trace.tsv")
        if len(resumed) != 1 or resumed[0]["status"] != "CACHED":
            raise RuntimeError("successful scaled retry was not cached on resume")
        if (output / "result.txt").read_text(encoding="utf-8").strip() != (
            "same-scientific-task|2|2"
        ):
            raise RuntimeError("resume replaced the successful retry output")
    print("MR resource retry multiplication and cached resume passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
