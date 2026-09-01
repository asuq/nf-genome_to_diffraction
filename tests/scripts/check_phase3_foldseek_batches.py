"""Exercise every complete-catalogue Phase III Foldseek Nextflow batch."""

import csv
import hashlib
import json
import os
import subprocess
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from tests.scripts.write_phase3_foldseek_batch_stub import (
    write_phase3_foldseek_stub_sequence_groups,
)

REPOSITORY = Path(__file__).resolve().parents[2]


def _run(command: Sequence[str], environment: dict[str, str]) -> None:
    result = subprocess.run(
        command,
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if result.returncode:
        raise RuntimeError(
            f"Foldseek batch stub failed: {' '.join(command)}\n"
            f"{result.stdout}\n{result.stderr}"
        )


def _trace(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8", newline="") as handle:
        return tuple(csv.DictReader(handle, delimiter="\t"))


def _digests(output: Path) -> dict[str, str]:
    return {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file() and "pipeline_info" not in path.parts
    }


def _assert_results(output: Path, expected_ids: set[str]) -> None:
    root = output / "prostt5_foldseek_search"
    manifest = json.loads((root / "search_manifest.json").read_bytes())
    if (
        manifest.get("query_count") != 1621
        or manifest.get("batch_count") != 13
        or manifest.get("maximum_queries_per_batch") != 128
        or manifest.get("deferred_query_count") != 0
    ):
        raise RuntimeError("Foldseek catalogue lost a query or bounded batch")
    results = tuple(
        json.loads(line)
        for line in (root / "search_results.jsonl")
        .read_text(encoding="ascii")
        .splitlines()
    )
    if (
        len(results) != 1621
        or {result["sequence_group_id"] for result in results} != expected_ids
        or any(result["execution_status"] != "completed_no_hit" for result in results)
    ):
        raise RuntimeError("Foldseek catalogue did not retain every typed query")
    if any(
        not (root / result["raw_result_pointer"]).is_file()
        or not (root / result["command_log_pointer"]).is_file()
        for result in results
    ):
        raise RuntimeError("Foldseek catalogue lost a batch raw result or command log")


def main() -> int:
    """Require exactly 13 one-at-a-time tasks and a byte-identical cached run."""

    with tempfile.TemporaryDirectory(prefix="phase3-foldseek-batches-") as temporary:
        root = Path(temporary)
        groups = write_phase3_foldseek_stub_sequence_groups(
            output=root / "sequence_groups.jsonl", count=1621
        )
        expected_ids = {
            json.loads(line)["sequence_group_id"]
            for line in groups.read_text(encoding="ascii").splitlines()
        }
        output = root / "results"
        environment = dict(os.environ)
        environment.update(
            {
                "NXF_AGENT_MODE": "true",
                "NXF_ANSI_LOG": "false",
                "NXF_DISABLE_CHECK_LATEST": "true",
                "NXF_HOME": str(root / "nxf-home"),
                "NXF_SYNTAX_PARSER": "v2",
            }
        )
        command = [
            "nextflow",
            "-C",
            "tests/fixtures/stubs/p6_empty_partner/nextflow.config",
            "run",
            "tests/fixtures/stubs/phase3_foldseek_batches/main.nf",
            "-stub-run",
            "--sequence_groups",
            str(groups),
            "--config",
            "examples/config.yaml",
            "--database_manifest",
            "tests/fixtures/stubs/provider_plan_database_manifest.json",
            "--outdir",
            str(output),
            "--cache_root",
            str(root / "cache"),
        ]
        _run(command, environment)
        trace = output / "pipeline_info/trace.tsv"
        first = _trace(trace)
        expected = Counter(
            {
                "RESOLVE_PROVIDER_PLAN": 1,
                "PLAN_PHASE3_FOLDSEEK_BATCHES": 1,
                "SEARCH_PHASE3_FOLDSEEK_BATCH": 13,
                "MERGE_PHASE3_FOLDSEEK_BATCHES": 1,
            }
        )
        observed = Counter(row["process"].split(":")[-1] for row in first)
        if observed != expected or {row["status"] for row in first} != {"COMPLETED"}:
            raise RuntimeError(f"unexpected Phase III Foldseek tasks: {dict(observed)}")
        search_tags = {
            row["tag"]
            for row in first
            if row["process"].endswith("SEARCH_PHASE3_FOLDSEEK_BATCH")
        }
        if len(search_tags) != 13:
            raise RuntimeError("Foldseek batches lost an immutable task identity")
        _assert_results(output, expected_ids)
        before = _digests(output)
        _run([*command, "-resume"], environment)
        resumed = _trace(trace)
        if (
            len(resumed) != len(first)
            or {row["status"] for row in resumed} != {"CACHED"}
            or {row["hash"] for row in resumed} != {row["hash"] for row in first}
            or _digests(output) != before
        ):
            raise RuntimeError("complete Foldseek batches changed on cached resume")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
