"""Exercise all fixed provider-empty branches in one cached Nextflow stub."""

import csv
import hashlib
import json
import os
import subprocess
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
STUB = REPOSITORY / "tests/fixtures/stubs/provider_empty_graph"


def _run(
    command: Sequence[str],
    *,
    root: Path,
    environment: dict[str, str],
    success: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if success != (result.returncode == 0):
        raise RuntimeError(
            f"provider-empty command returned {result.returncode}: "
            f"{' '.join(command)}\n{result.stdout}\n{result.stderr}"
        )
    return result


def _trace(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8", newline="") as handle:
        return tuple(csv.DictReader(handle, delimiter="\t"))


def _name(row: dict[str, str]) -> str:
    return row["process"].split(":")[-1]


def _digests(output: Path) -> dict[str, str]:
    return {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file() and "pipeline_info" not in path.parts
    }


def _assert_completion(output: Path) -> None:
    completion = json.loads(
        (
            output
            / "provider_empty_graph_completion/provider_empty_graph_completion.json"
        ).read_text(encoding="utf-8")
    )
    if (
        completion.get("terminal_status") != "completed_no_model"
        or completion.get("network_request_count") != 0
        or completion.get("query_count") != 1
    ):
        raise RuntimeError("provider-empty terminal record is not a typed no-model")
    outcomes = {
        branch["provider"]: branch["outcome"]
        for branch in completion.get("branches", [])
    }
    if outcomes != {
        "afdb_exact": "disabled",
        "esm_atlas": "provider_unavailable",
        "foldseek_prostt5_pdb": "disabled",
        "pdb_sequence": "enabled_no_hit",
    }:
        raise RuntimeError(f"provider-empty branch outcomes changed: {outcomes}")
    registry = json.loads(
        (
            output
            / "provider_empty_graph_completion"
            / "all_model_registry/all_model_registry.json"
        ).read_text(encoding="utf-8")
    )
    inventories = registry.get("sequence_groups", [])
    if (
        registry.get("model_count") != 0
        or registry.get("unavailable_sequence_group_count") != 1
        or len(inventories) != 1
        or inventories[0].get("unavailable_reason") != "no_eligible_model"
    ):
        raise RuntimeError("empty provider graph lost its typed no-model inventory")
    for name in (
        "afdb_exact_search",
        "esm_atlas_search",
        "prostt5_foldseek_search",
        "pdb_sequence_search",
    ):
        rows = tuple(
            json.loads(line)
            for line in (output / name / "search_results.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        if len(rows) != 1 or rows[0].get("hit_count") != 0:
            raise RuntimeError(f"provider branch is not a complete empty item: {name}")


def main() -> int:
    """Run first pass, byte-identical resume, and non-stub refusal."""

    with tempfile.TemporaryDirectory(prefix="provider-empty-graph-") as temporary:
        root = Path(temporary)
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
        output = root / "results"
        cache = root / "cache"
        command = [
            "nextflow",
            "run",
            str(STUB / "main.nf"),
            "-c",
            str(STUB / "nextflow.config"),
            "-stub-run",
            "--sequence_groups",
            str(REPOSITORY / "tests/fixtures/stubs/sequence_groups.jsonl"),
            "--config",
            str(STUB / "config.yaml"),
            "--database_manifest",
            str(
                REPOSITORY / "tests/fixtures/stubs/provider_plan_database_manifest.json"
            ),
            "--stub_helper",
            str(REPOSITORY / "tests/scripts/materialise_provider_no_hit.py"),
            "--outdir",
            str(output),
            "--cache_root",
            str(cache),
        ]
        _run(command, root=root, environment=environment)
        rows = _trace(output / "pipeline_info/trace.tsv")
        counts = Counter(_name(row) for row in rows)
        expected = Counter(
            {
                "RESOLVE_PROVIDER_PLAN": 1,
                "STUB_LOCAL_PROVIDER_NO_HIT": 1,
                "EMIT_DISABLED_AFDB": 1,
                "EMIT_DISABLED_ESM": 1,
                "EMIT_DISABLED_FOLDSEEK": 1,
                "COMPLETE_PROVIDER_EMPTY_GRAPH": 1,
            }
        )
        if counts != expected or {row["status"] for row in rows} != {"COMPLETED"}:
            raise RuntimeError(f"provider-empty task inventory changed: {dict(counts)}")
        _assert_completion(output)
        before = _digests(output)
        _run([*command, "-resume"], root=root, environment=environment)
        resumed = _trace(output / "pipeline_info/trace.tsv")
        if len(resumed) != 6 or {row["status"] for row in resumed} != {"CACHED"}:
            raise RuntimeError("provider-empty resume did not cache all six tasks")
        if before != _digests(output):
            raise RuntimeError("provider-empty outputs changed across cached resume")

        live_output = root / "live-results"
        live_cache = root / "live-cache"
        live_command = [item for item in command if item != "-stub-run"]
        live_command[live_command.index(str(output))] = str(live_output)
        live_command[live_command.index(str(cache))] = str(live_cache)
        failure = _run(
            live_command,
            root=root,
            environment=environment,
            success=False,
        )
        text = f"{failure.stdout}\n{failure.stderr}"
        if "provider-empty enabled route is stub-only" not in text:
            raise RuntimeError("provider-empty non-stub did not fail at its boundary")
        if (live_output / "provider_empty_graph_completion").exists():
            raise RuntimeError("provider-empty live refusal published a terminal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
