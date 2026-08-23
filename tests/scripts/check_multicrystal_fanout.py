"""Exercise the Phase III complete per-crystal Nextflow fan-out boundary."""

import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURE = REPOSITORY / "tests/fixtures/stubs/multi_crystal_fanout"
CRYSTAL_IDS = (
    "fanout_crystal_01",
    "fanout_crystal_02",
    "fanout_crystal_03",
)


def _environment(nxf_home: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "NXF_AGENT_MODE": "true",
            "NXF_ANSI_LOG": "false",
            "NXF_DISABLE_CHECK_LATEST": "true",
            "NXF_HOME": str(nxf_home),
            "NXF_SYNTAX_PARSER": "v2",
        }
    )
    return environment


def _run(
    command: Sequence[str], environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if result.returncode != 0:
        combined = f"{result.stdout}\n{result.stderr}"
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{combined}"
        )
    return result


def _read_trace(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8", newline="") as handle:
        return tuple(csv.DictReader(handle, delimiter="\t"))


def _process_name(row: dict[str, str]) -> str:
    return row["process"].split(":")[-1]


def _task_hashes(rows: Sequence[dict[str, str]], process: str) -> dict[str, str]:
    selected = tuple(row for row in rows if _process_name(row) == process)
    return {row["tag"]: row["hash"] for row in selected}


def _output_digests(output: Path) -> dict[str, str]:
    return {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file() and "pipeline_info" not in path.parts
    }


def main() -> int:
    """Require three complete items and byte-identical cached resume."""

    with tempfile.TemporaryDirectory(
        prefix="nf-genome-to-diffraction-multicrystal-", dir="/tmp"
    ) as temporary:
        root = Path(temporary)
        output = root / "results"
        environment = _environment(root / "nxf-home")
        command = [
            "nextflow",
            "-C",
            "tests/fixtures/stubs/multi_crystal_fanout/nextflow.config",
            "run",
            "tests/fixtures/stubs/multi_crystal_fanout/main.nf",
            "-stub-run",
            "--crystals",
            str(FIXTURE / "crystals.json"),
            "--preflight",
            str(REPOSITORY / "tests/fixtures/stubs/mtz_preflight.jsonl"),
            "--catalogue_seed",
            str(FIXTURE / "catalogue.marker"),
            "--provider_seed",
            str(FIXTURE / "provider.marker"),
            "--outdir",
            str(output),
            "--cache_root",
            str(root / "cache"),
        ]
        _run(command, environment)

        trace_path = output / "pipeline_info/trace.tsv"
        first_rows = _read_trace(trace_path)
        expected_counts = Counter(
            {
                "PREPARE_SHARED_CATALOGUE_FIXTURE": 1,
                "PREPARE_SHARED_PROVIDER_FIXTURE": 1,
                "DISPATCH_CRYSTAL_ITEM": 3,
                "RECORD_COMPLETE_CRYSTAL_ITEM_FIXTURE": 3,
            }
        )
        actual_counts = Counter(_process_name(row) for row in first_rows)
        if actual_counts != expected_counts:
            raise RuntimeError(
                "multi-crystal stub scheduled the wrong task counts: "
                f"{dict(sorted(actual_counts.items()))}"
            )
        if {row["status"] for row in first_rows} != {"COMPLETED"}:
            raise RuntimeError("multi-crystal stub did not complete every task")
        first_identities = {
            (row["process"], row["tag"]): row["hash"] for row in first_rows
        }

        dispatch_hashes = _task_hashes(first_rows, "DISPATCH_CRYSTAL_ITEM")
        expected_dispatch_tags = {
            f"crystal-dispatch:{crystal_id}" for crystal_id in CRYSTAL_IDS
        }
        if set(dispatch_hashes) != expected_dispatch_tags:
            raise RuntimeError("per-crystal dispatch task identities are incomplete")
        if len(set(dispatch_hashes.values())) != len(CRYSTAL_IDS):
            raise RuntimeError("per-crystal dispatch tasks do not have distinct hashes")

        for crystal_id in CRYSTAL_IDS:
            bundle = output / f"complete_crystal_{crystal_id}"
            if (bundle / "crystal_id.txt").read_text(encoding="utf-8") != (
                f"{crystal_id}\n"
            ):
                raise RuntimeError(f"crystal identity changed for {crystal_id}")
            dispatch = json.loads(
                (bundle / "crystal_dispatch.json").read_text(encoding="utf-8")
            )
            if dispatch.get("crystal_id") != crystal_id:
                raise RuntimeError(f"dispatch evidence changed for {crystal_id}")
            if (bundle / "catalogue.marker").read_text(encoding="utf-8") != (
                "catalogue-prepared-once\n"
            ):
                raise RuntimeError(f"shared catalogue was unavailable to {crystal_id}")
            if (bundle / "provider.marker").read_text(encoding="utf-8") != (
                "provider-prepared-once\n"
            ):
                raise RuntimeError(f"shared provider was unavailable to {crystal_id}")

        before_resume = _output_digests(output)
        resume_command = [*command[:5], "-resume", *command[5:]]
        _run(resume_command, environment)
        resumed_rows = _read_trace(trace_path)
        resumed_counts = Counter(_process_name(row) for row in resumed_rows)
        if resumed_counts != expected_counts:
            raise RuntimeError("cached resume changed multi-crystal task counts")
        if {row["status"] for row in resumed_rows} != {"CACHED"}:
            resumed_statuses = Counter(row["status"] for row in resumed_rows)
            raise RuntimeError(
                "cached resume did not cache every fan-out task: "
                f"{dict(sorted(resumed_statuses.items()))}"
            )
        resumed_identities = {
            (row["process"], row["tag"]): row["hash"] for row in resumed_rows
        }
        if resumed_identities != first_identities:
            raise RuntimeError("cached resume changed exact task identities")
        resumed_dispatch_hashes = _task_hashes(resumed_rows, "DISPATCH_CRYSTAL_ITEM")
        if resumed_dispatch_hashes != dispatch_hashes:
            raise RuntimeError("cached resume changed per-crystal task identities")
        if _output_digests(output) != before_resume:
            raise RuntimeError("cached resume changed retained crystal evidence")

    print("Three-crystal complete-item fan-out and cached resume passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
