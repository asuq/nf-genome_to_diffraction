"""Exercise the fixed path-closed Phase III unknown-pass-1 Nextflow stub."""

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

from tests.support.unknown_pass1_fixture import (
    PUBLIC_STUB_CRYSTAL_IDS,
    materialise_unknown_pass1_public_fixture,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STUB_ROOT = REPOSITORY / "tests/fixtures/stubs/unknown_pass1_screen"


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
    command: Sequence[str],
    *,
    launch_root: Path,
    environment: dict[str, str],
    expected_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=launch_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if expected_success and result.returncode != 0:
        combined = f"{result.stdout}\n{result.stderr}"
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{combined}"
        )
    if not expected_success and result.returncode == 0:
        raise RuntimeError(f"command unexpectedly succeeded: {' '.join(command)}")
    return result


def _read_trace(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8", newline="") as handle:
        return tuple(csv.DictReader(handle, delimiter="\t"))


def _process_name(row: dict[str, str]) -> str:
    return row["process"].split(":")[-1]


def _output_digests(output: Path) -> dict[str, str]:
    return {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file() and "pipeline_info" not in path.parts
    }


def _assert_first_run(
    *,
    launch_root: Path,
    rows: tuple[dict[str, str], ...],
) -> tuple[Counter[str], dict[tuple[str, str], str]]:
    expected_counts: Counter[str] = Counter(
        {
            "PREPARE_SHARED_UNKNOWN_CATALOGUE_FIXTURE": 1,
            "PREPARE_SHARED_UNKNOWN_PROVIDER_FIXTURE": 1,
            "PREPARE_SHARED_UNKNOWN_LOCALISATION_FIXTURE": 1,
            "PREPARE_CRYSTALLOGRAPHIC_REVIEW_STAGE_FIXTURE": 3,
            "MATERIALISE_UNKNOWN_PASS1_CRYSTAL_ITEM": 3,
            "STUB_UNKNOWN_PASS1_A_HYPOTHESIS": 25,
        }
    )
    actual_counts = Counter(_process_name(row) for row in rows)
    if actual_counts != expected_counts:
        raise RuntimeError(
            "unknown-pass-1 stub scheduled the wrong exact task inventory: "
            f"{dict(sorted(actual_counts.items()))}"
        )
    if {row["status"] for row in rows} != {"COMPLETED"}:
        raise RuntimeError("unknown-pass-1 stub did not complete every task")

    crystal_rows = tuple(
        row
        for row in rows
        if _process_name(row) == "MATERIALISE_UNKNOWN_PASS1_CRYSTAL_ITEM"
    )
    expected_crystal_tags = {
        f"unknown-pass1-crystal:{PUBLIC_STUB_CRYSTAL_IDS[0]}:ready",
        f"unknown-pass1-crystal:{PUBLIC_STUB_CRYSTAL_IDS[1]}:held",
        f"unknown-pass1-crystal:{PUBLIC_STUB_CRYSTAL_IDS[2]}:empty_no_model",
    }
    if {row["tag"] for row in crystal_rows} != expected_crystal_tags:
        raise RuntimeError("three complete crystal branches were not retained exactly")
    if len({row["hash"] for row in crystal_rows}) != 3:
        raise RuntimeError("complete crystal items do not have distinct cache hashes")

    hypothesis_rows = tuple(
        row for row in rows if _process_name(row) == "STUB_UNKNOWN_PASS1_A_HYPOTHESIS"
    )
    expected_hypothesis_tags = {
        f"unknown-pass1-a:{PUBLIC_STUB_CRYSTAL_IDS[0]}:{rank}" for rank in range(1, 26)
    }
    if {row["tag"] for row in hypothesis_rows} != expected_hypothesis_tags:
        raise RuntimeError("A task fan-out differs from the exact 25-row inventory")
    if len({row["hash"] for row in hypothesis_rows}) != 25:
        raise RuntimeError("selected A tasks do not have distinct cache hashes")

    output = launch_root / "results"
    inventory_path = launch_root / "inputs/unknown_pass1_screen_inventory.json"
    inventory_bytes = inventory_path.read_bytes()
    inventory = json.loads(inventory_bytes)
    crystal_by_id = {item["crystal_id"]: item for item in inventory.get("crystals", [])}
    for crystal_id in PUBLIC_STUB_CRYSTAL_IDS:
        bundle = output / "crystals" / f"unknown_pass1_crystal_{crystal_id}"
        item = json.loads((bundle / "crystal_item.json").read_text(encoding="utf-8"))
        if item != crystal_by_id[crystal_id]:
            raise RuntimeError(f"complete crystal record changed for {crystal_id}")
        if (
            bundle / "unknown_pass1_screen_inventory.json"
        ).read_bytes() != inventory_bytes:
            raise RuntimeError(f"inventory bytes changed for {crystal_id}")
        if (
            hashlib.sha256((bundle / "input.mtz").read_bytes()).hexdigest()
            != item["mtz_sha256"]
        ):
            raise RuntimeError(f"MTZ bytes changed for {crystal_id}")
        for shared_file in (
            "shared_catalogue/catalogue_preparation.json",
            "shared_provider/provider_preparation.json",
            "shared_localisation/localisation_preparation.json",
            "crystallographic_review_stage/phase3_review_decision.json",
            "crystallographic_review_stage/phase3_review_stage_manifest.json",
            "phase3_execution_identity.json",
        ):
            if not (bundle / shared_file).is_file():
                raise RuntimeError(
                    f"complete crystal item lacks {shared_file}: {crystal_id}"
                )

    expected_task_ids = {
        task["task_id"] for task in inventory.get("hypothesis_tasks", [])
    }
    observed_task_ids: set[str] = set()
    for bundle in sorted((output / "hypotheses").glob("unknown_pass1_a_*")):
        task = json.loads(
            (bundle / "a_hypothesis_task.json").read_text(encoding="utf-8")
        )
        observed_task_ids.add(task["task_id"])
        if (bundle / "execution_status.txt").read_text(encoding="utf-8") != (
            "stub_only_no_scientific_result\n"
        ):
            raise RuntimeError("A stub fabricated or lost its execution status")
        if (
            hashlib.sha256((bundle / "model.pdb").read_bytes()).hexdigest()
            != task["model_sha256"]
        ):
            raise RuntimeError("A task model bytes differ from its exact identity")
        if (
            hashlib.sha256((bundle / "input.mtz").read_bytes()).hexdigest()
            != task["mtz_sha256"]
        ):
            raise RuntimeError("A task MTZ bytes differ from its exact identity")
        if (
            bundle / "unknown_pass1_screen_inventory.json"
        ).read_bytes() != inventory_bytes:
            raise RuntimeError("A task inventory bytes changed during fan-out")
    if observed_task_ids != expected_task_ids or len(observed_task_ids) != 25:
        raise RuntimeError("retained A task outputs do not match the inventory")

    identities = {(row["process"], row["tag"]): row["hash"] for row in rows}
    return expected_counts, identities


def main() -> int:
    """Require exact branches, complete items, and byte-identical cached resume."""

    with tempfile.TemporaryDirectory(
        prefix="nf-genome-to-diffraction-unknown-pass1-",
        dir="/tmp",
    ) as temporary:
        launch_root = Path(temporary)
        fixture = materialise_unknown_pass1_public_fixture(launch_root)
        inventory = fixture.inventory
        if (
            inventory.crystal_count != 3
            or inventory.hypothesis_task_count != 25
            or inventory.held_count != 1
            or inventory.empty_no_model_count != 1
        ):
            raise RuntimeError("synthetic public screen fixture is not exact")

        environment = _environment(launch_root / "nxf-home")
        command = [
            "nextflow",
            "-C",
            str(STUB_ROOT / "nextflow.config"),
            "run",
            str(STUB_ROOT / "main.nf"),
            "-stub-run",
        ]
        _run(command, launch_root=launch_root, environment=environment)
        trace = launch_root / "results/pipeline_info/trace.tsv"
        first_rows = _read_trace(trace)
        expected_counts, first_identities = _assert_first_run(
            launch_root=launch_root,
            rows=first_rows,
        )
        before_resume = _output_digests(launch_root / "results")

        resume_command = [*command[:5], "-resume", *command[5:]]
        _run(resume_command, launch_root=launch_root, environment=environment)
        resumed_rows = _read_trace(trace)
        if Counter(_process_name(row) for row in resumed_rows) != expected_counts:
            raise RuntimeError("cached resume changed the exact task inventory")
        if {row["status"] for row in resumed_rows} != {"CACHED"}:
            statuses = Counter(row["status"] for row in resumed_rows)
            raise RuntimeError(
                "cached resume did not cache every unknown-screen task: "
                f"{dict(sorted(statuses.items()))}"
            )
        resumed_identities = {
            (row["process"], row["tag"]): row["hash"] for row in resumed_rows
        }
        if resumed_identities != first_identities:
            raise RuntimeError("cached resume changed exact task identities")
        if _output_digests(launch_root / "results") != before_resume:
            raise RuntimeError("cached resume changed retained screen evidence")

        live_result = _run(
            [*command[:5], "-resume"],
            launch_root=launch_root,
            environment=environment,
            expected_success=False,
        )
        live_output = f"{live_result.stdout}\n{live_result.stderr}"
        if "unknown pass 1 crystal fan-out is stub-only" not in live_output:
            raise RuntimeError("non-stub unknown screen did not fail at its boundary")

    print("Unknown-pass-1 three-crystal path-closed cached stub passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
