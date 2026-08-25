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
from shutil import copytree

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURE = REPOSITORY / "tests/fixtures/stubs/multi_crystal_fanout"
CRYSTAL_IDS = (
    "fanout_crystal_01",
    "fanout_crystal_02",
    "fanout_crystal_03",
)


def _check_first_copy_application(root: Path, environment: dict[str, str]) -> None:
    """Require one shared preparation and three independent real workflow branches."""

    output = root / "first-copy-results"
    stubs = REPOSITORY / "tests/fixtures/stubs"
    project = root / "first-copy-project"
    project.mkdir()
    fixture_main = stubs / "phase3_multicrystal_first_copy/main.nf"
    (project / "main.nf").write_text(
        fixture_main.read_text(encoding="ascii").replace(
            "'../../../../workflows/",
            f"'{REPOSITORY}/workflows/",
        ),
        encoding="ascii",
    )
    project_stubs = project / "tests/fixtures/stubs"
    project_stubs.mkdir(parents=True)
    for name in (
        "exact_predicted_funnel",
        "predicted_model_preparation",
        "first_copy_phaser",
        "mr_seed_review",
    ):
        copytree(stubs / name, project_stubs / name)
    command = [
        "nextflow",
        "-C",
        "tests/fixtures/stubs/p6_empty_partner/nextflow.config",
        "run",
        str(project / "main.nf"),
        "-stub-run",
        "--crystals",
        str(FIXTURE / "crystals.json"),
        "--preflight",
        str(stubs / "mtz_preflight.jsonl"),
        "--sequence_groups",
        str(stubs / "sequence_groups.jsonl"),
        "--source_records",
        str(stubs / "source_records.jsonl"),
        "--predicted_coordinate_sources",
        str(stubs / "afdb_exact_search/coordinate_sources.jsonl"),
        "--predicted_prepared_models",
        str(stubs / "predicted_model_preparation"),
        "--pdb_coordinate_sources",
        str(stubs / "pdb_coordinate_registration/coordinate_sources.jsonl"),
        "--coordinate_hit_mappings",
        str(stubs / "pdb_coordinate_registration/coordinate_hit_mappings.jsonl"),
        "--experimental_prepared_models",
        str(stubs / "experimental_model_preparation"),
        "--matthews",
        str(stubs / "mtz_preflight.jsonl"),
        "--pipeline_config",
        str(REPOSITORY / "examples/config.yaml"),
        "--phenix_manifest",
        str(stubs / "phenix_install_manifest.json"),
        "--outdir",
        str(output),
        "--cache_root",
        str(root / "first-copy-cache"),
    ]
    _run(command, environment)
    trace = output / "pipeline_info/trace.tsv"
    first = _read_trace(trace)
    expected = Counter(
        {
            "PREPARE_PHASE3_SHARED_CATALOGUE_FIXTURE": 1,
            "PREPARE_PHASE3_SHARED_PROVIDER_FIXTURE": 1,
            "DISPATCH_CRYSTAL_ITEM": 3,
            "BUILD_DIVERSE_FIRST_COPY_FUNNEL": 3,
            "RUN_PHASE3_FIRST_COPY_PHASER": 3,
            "BUILD_PHASE3_MR_SEED_REVIEW": 3,
        }
    )
    if Counter(_process_name(row) for row in first) != expected:
        raise RuntimeError("Phase III multi-crystal application dropped a branch")
    if {row["status"] for row in first} != {"COMPLETED"}:
        raise RuntimeError("Phase III multi-crystal application did not complete")
    for crystal_id in CRYSTAL_IDS:
        package = output / f"phase3_mr_seed_review_{crystal_id}"
        if not (package / "mr_seed_review_manifest.json").is_file():
            raise RuntimeError(f"missing independent MR review for {crystal_id}")
        approvals = (package / "approved_mr_seeds.tsv").read_text(encoding="utf-8")
        if len(approvals.splitlines()) != 1:
            raise RuntimeError(f"fabricated MR review approval for {crystal_id}")
    before = _output_digests(output)
    _run([*command, "-resume"], environment)
    resumed = _read_trace(trace)
    if len(resumed) != len(first) or {row["status"] for row in resumed} != {"CACHED"}:
        raise RuntimeError("Phase III multi-crystal application did not fully resume")
    if {row["hash"] for row in resumed} != {row["hash"] for row in first}:
        raise RuntimeError("Phase III multi-crystal resume changed task identities")
    if _output_digests(output) != before:
        raise RuntimeError("Phase III multi-crystal resume changed published outputs")

    application_output = root / "main-application-results"
    _run(
        [
            "nextflow",
            "run",
            "main.nf",
            "-profile",
            "test",
            "-stub-run",
            "-params-file",
            "tests/fixtures/stubs/main_params.yaml",
            "--analysis_stage",
            "first_copy",
            "--phase3_joint_first_copy",
            "true",
            "--outdir",
            str(application_output),
            "--cache_root",
            str(root / "main-application-cache"),
        ],
        environment,
    )
    application = Counter(
        _process_name(row)
        for row in _read_trace(application_output / "pipeline_info/trace.tsv")
    )
    if (
        application["DISPATCH_CRYSTAL_ITEM"] != 1
        or application["RUN_PHASE3_FIRST_COPY_PHASER"] != 1
        or application["BUILD_PHASE3_MR_SEED_REVIEW"] != 1
        or application["SELECT_SINGLE_CRYSTAL"] != 0
    ):
        raise RuntimeError("main application did not select the Phase III crystal path")


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
        _check_first_copy_application(root, environment)

    print("Three-crystal dispatch, first-copy review, and cached resume passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
