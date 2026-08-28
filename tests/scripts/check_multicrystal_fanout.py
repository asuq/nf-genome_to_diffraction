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

from genome_to_diffraction.checksums import atomic_write_json
from tests.support.unknown_pass1_fixture import (
    PUBLIC_STUB_CRYSTAL_IDS,
    materialise_neutral_localisation_fixture,
    materialise_phase3_provider_login_stub,
    materialise_unknown_pass1_public_fixture,
)

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
    localisation_root = root / "localisation-input"
    localisation_root.mkdir()
    gel_evidence = localisation_root / "gel-evidence.json"
    gel_evidence.write_text(
        '{"schema_version":"2.0","observations":[]}\n',
        encoding="ascii",
    )
    localisation_bundle = materialise_neutral_localisation_fixture(
        localisation_root,
        gel_evidence=gel_evidence,
        sequence_groups_jsonl=stubs / "sequence_groups.jsonl",
        source_records_jsonl=stubs / "source_records.jsonl",
    )
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
        "--localisation_bundle",
        str(localisation_bundle),
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
            "BUILD_PHASE3_DIVERSE_FIRST_COPY_FUNNEL": 3,
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

    review_root = root / "reviewed-inputs"
    review_root.mkdir()
    reviewed = materialise_unknown_pass1_public_fixture(review_root)
    reviewed_manifest = reviewed.input_root / "reviewed_crystals.json"
    atomic_write_json(
        reviewed_manifest,
        {
            "schema_version": "1.0",
            "crystals": [
                {
                    "crystal_id": crystal.crystal_id,
                    "mtz": str(crystal.mtz),
                    "catalogue_id": "example_archaeon_refseq",
                    "sds_page_mass_kda": [],
                    "allow_remote_sequence_submission": False,
                }
                for crystal in reviewed.crystals
            ],
        },
    )
    reviewed_output = root / "reviewed-first-copy-results"
    reviewed_command = list(command)
    reviewed_command[reviewed_command.index("--crystals") + 1] = str(reviewed_manifest)
    reviewed_command[reviewed_command.index("--outdir") + 1] = str(reviewed_output)
    reviewed_command[reviewed_command.index("--cache_root") + 1] = str(
        root / "reviewed-first-copy-cache"
    )
    reviewed_command.extend(
        [
            "--phase3_crystallographic_review_stage",
            str(reviewed.review_stage),
            "--phase3_execution_identity",
            str(reviewed.execution_identity),
        ]
    )
    _run(reviewed_command, environment)
    reviewed_trace = reviewed_output / "pipeline_info/trace.tsv"
    reviewed_rows = _read_trace(reviewed_trace)
    expected_reviewed = Counter(
        {
            "PREPARE_PHASE3_SHARED_CATALOGUE_FIXTURE": 1,
            "PREPARE_PHASE3_SHARED_PROVIDER_FIXTURE": 1,
            "DISPATCH_CRYSTAL_ITEM": 3,
            "VALIDATE_PHASE3_CRYSTALLOGRAPHIC_REVIEWS": 1,
            "RETAIN_PHASE3_CRYSTALLOGRAPHIC_HOLD": 1,
            "BUILD_PHASE3_DIVERSE_FIRST_COPY_FUNNEL": 2,
            "RUN_PHASE3_FIRST_COPY_PHASER": 2,
            "BUILD_PHASE3_MR_SEED_REVIEW": 2,
        }
    )
    if Counter(_process_name(row) for row in reviewed_rows) != expected_reviewed:
        raise RuntimeError(
            "reviewed crystal application ignored proceed/hold decisions"
        )
    held_id = PUBLIC_STUB_CRYSTAL_IDS[1]
    held_route = reviewed_output / f"phase3_crystallographic_hold_{held_id}"
    if not (held_route / "crystallographic_review_routing.json").is_file():
        raise RuntimeError("held crystal lost its independently retained review")
    if (reviewed_output / f"phase3_mr_seed_review_{held_id}").exists():
        raise RuntimeError("held crystal unexpectedly reached molecular replacement")
    for crystal_id in (PUBLIC_STUB_CRYSTAL_IDS[0], PUBLIC_STUB_CRYSTAL_IDS[2]):
        if not (
            reviewed_output
            / f"phase3_mr_seed_review_{crystal_id}"
            / "mr_seed_review_manifest.json"
        ).is_file():
            raise RuntimeError(f"proceeding crystal lost its own review: {crystal_id}")
    reviewed_before = _output_digests(reviewed_output)
    _run([*reviewed_command, "-resume"], environment)
    reviewed_resumed = _read_trace(reviewed_trace)
    if (
        Counter(_process_name(row) for row in reviewed_resumed) != expected_reviewed
        or {row["status"] for row in reviewed_resumed} != {"CACHED"}
        or {row["hash"] for row in reviewed_resumed}
        != {row["hash"] for row in reviewed_rows}
        or _output_digests(reviewed_output) != reviewed_before
    ):
        raise RuntimeError("reviewed proceed/hold application changed on cached resume")

    discovery_output = root / "provider-discovery-results"
    discovery_command = [
        "nextflow",
        "run",
        "phase3_application.nf",
        "-profile",
        "test",
        "-stub-run",
        "-params-file",
        "tests/fixtures/stubs/phase3_application_params.yaml",
        "--phase3_operation",
        "provider_discovery",
        "--crystals",
        str(reviewed_manifest),
        "--phase3_crystallographic_review_stage",
        str(reviewed.review_stage),
        "--phase3_execution_identity",
        str(reviewed.execution_identity),
        "--afdb_accession_map",
        "tests/fixtures/stubs/empty_afdb_accession_map.tsv",
        "--phase3_owned_parent_run_id",
        "gtd-unknown-discovery-production-fixture",
        "--phase3_localisation_bundle",
        str(localisation_bundle),
        "--outdir",
        str(discovery_output),
        "--cache_root",
        str(root / "provider-discovery-cache"),
    ]
    _run(discovery_command, environment)
    discovery_trace = discovery_output / "pipeline_info/trace.tsv"
    discovery_rows = _read_trace(discovery_trace)
    discovery = Counter(_process_name(row) for row in discovery_rows)
    if (
        discovery["VALIDATE_PHASE3_PROVIDER_DISCOVERY_REVIEWS"] != 1
        or discovery["VALIDATE_PHASE3_LOCALISATION_BUNDLE"] != 1
        or discovery["SEARCH_PDB_SEQUENCES"] != 1
        or discovery["PLAN_PHASE3_FOLDSEEK_BATCHES"] != 1
        or discovery["SEARCH_PHASE3_FOLDSEEK_BATCH"] < 1
        or discovery["MERGE_PHASE3_FOLDSEEK_BATCHES"] != 1
        or discovery["PACKAGE_PHASE3_PROVIDER_DISCOVERY"] != 1
        or discovery["RETRIEVE_AFDB_EXACT"] != 0
        or discovery["REGISTER_PDB_COORDINATES"] != 0
        or discovery["PREPARE_PREDICTED_MODELS"] != 0
        or discovery["PREPARE_EXPERIMENTAL_MODELS"] != 0
        or discovery["RUN_PHASE3_FIRST_COPY_PHASER"] != 0
    ):
        raise RuntimeError(
            "Phase III provider discovery crossed its offline compute boundary"
        )
    package_manifest = (
        discovery_output
        / "phase3_provider_discovery"
        / "phase3_provider_discovery_manifest.json"
    )
    if not package_manifest.is_file():
        raise RuntimeError("Phase III provider discovery lost its owned package")
    before_discovery = _output_digests(discovery_output)
    _run([*discovery_command, "-resume"], environment)
    resumed_discovery = _read_trace(discovery_trace)
    if (
        {row["status"] for row in resumed_discovery} != {"CACHED"}
        or {row["hash"] for row in resumed_discovery}
        != {row["hash"] for row in discovery_rows}
        or _output_digests(discovery_output) != before_discovery
    ):
        raise RuntimeError("Phase III provider discovery changed on cached resume")
    provider_stage = materialise_phase3_provider_login_stub(
        package_manifest.parent,
        root / "provider-login-stage",
    )
    application_output = root / "main-application-results"
    application_command = [
        "nextflow",
        "run",
        "phase3_application.nf",
        "-profile",
        "test",
        "-stub-run",
        "-params-file",
        "tests/fixtures/stubs/phase3_application_params.yaml",
        "--phase3_operation",
        "first_copy",
        "--crystals",
        str(reviewed_manifest),
        "--phase3_crystallographic_review_stage",
        str(reviewed.review_stage),
        "--phase3_execution_identity",
        str(reviewed.execution_identity),
        "--phase3_owned_parent_run_id",
        "gtd-unknown-screen-production-fixture",
        "--phase3_provider_discovery",
        str(package_manifest.parent),
        "--phase3_provider_preparation",
        str(provider_stage),
        "--phase3_localisation_bundle",
        str(localisation_bundle),
        "--outdir",
        str(application_output),
        "--cache_root",
        str(root / "main-application-cache"),
    ]
    _run(application_command, environment)
    application = Counter(
        _process_name(row)
        for row in _read_trace(application_output / "pipeline_info/trace.tsv")
    )
    if (
        application["VALIDATE_PHASE3_OFFLINE_PROVIDER_INPUT"] != 1
        or application["VALIDATE_PHASE3_LOCALISATION_BUNDLE"] != 1
        or application["DISPATCH_CRYSTAL_ITEM"] != 3
        or application["RUN_PHASE3_FIRST_COPY_PHASER"] != 2
        or application["BUILD_PHASE3_MR_SEED_REVIEW"] != 2
        or application["PDB_SEQUENCE_DISCOVERY"] != 0
        or application["RETRIEVE_AFDB_EXACT"] != 0
        or application["REGISTER_PDB_COORDINATES"] != 0
        or application["SELECT_SINGLE_CRYSTAL"] != 0
    ):
        raise RuntimeError("Phase III application crossed its offline provider path")
    application_before = _output_digests(application_output)
    _run([*application_command, "-resume"], environment)
    application_resumed = _read_trace(application_output / "pipeline_info/trace.tsv")
    if (
        {row["status"] for row in application_resumed} != {"CACHED"}
        or Counter(_process_name(row) for row in application_resumed) != application
        or _output_digests(application_output) != application_before
    ):
        raise RuntimeError("Phase III offline application changed on cached resume")


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
