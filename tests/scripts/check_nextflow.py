"""Parse and exercise the implemented Nextflow entry points."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

import gemmi
import numpy as np

REPOSITORY = Path(__file__).resolve().parents[2]


def _run(
    command: Sequence[str],
    *,
    environment: dict[str, str],
    expected_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    if expected_success and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{combined}"
        )
    if not expected_success and result.returncode == 0:
        raise RuntimeError(f"command unexpectedly succeeded: {' '.join(command)}")
    return result


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


def check_syntax() -> None:
    """Run the Nextflow parser/linter over all workflow sources."""

    with tempfile.TemporaryDirectory(
        prefix="nf-genome-to-diffraction-lint-", dir="/tmp"
    ) as temporary:
        environment = _environment(Path(temporary) / "nxf-home")
        _run(["nextflow", "lint", "."], environment=environment)


def _assert_files(root: Path, names: set[str]) -> None:
    actual = {path.name for path in root.rglob("*") if path.is_file()}
    missing = names - actual
    if missing:
        raise RuntimeError(f"missing outputs under {root}: {sorted(missing)}")


def _write_real_inputs(root: Path) -> Path:
    """Create tiny local contracts and MTZ for real Task 05 workflow acceptance."""

    inputs = root / "real-inputs"
    inputs.mkdir()
    fasta = inputs / "trusted proteins.faa"
    fasta.write_text(f">protein_a\n{'A' * 50}\n", encoding="utf-8")
    catalogue_manifest = inputs / "catalogues.json"
    catalogue_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "catalogues": [
                    {
                        "catalogue_id": "test_catalogue",
                        "proteome_faa": str(fasta),
                        "annotation_provider": "synthetic trusted fixture",
                        "annotation_version": "1",
                        "is_contaminant_catalogue": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    mtz_path = inputs / "integrated intensities.mtz"
    mtz = gemmi.Mtz(with_base=True)
    mtz.spacegroup = gemmi.find_spacegroup_by_name("P 21 21 21")
    mtz.set_cell_for_all(gemmi.UnitCell(50, 50, 50, 90, 90, 90))
    mtz.add_dataset("synthetic")
    mtz.add_column("I", "J")
    mtz.add_column("SIGI", "Q")
    mtz.add_column("FREE", "I")
    data = np.asarray(
        [
            [index, 1, 1, 1000 + index, 10 + index, 1 if index == 1 else 0]
            for index in range(1, 11)
        ],
        dtype=np.float32,
    )
    mtz.set_data(data)
    mtz.update_reso()
    mtz.write_to_file(str(mtz_path))
    crystal_manifest = inputs / "crystals.json"
    crystal_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "crystals": [
                    {
                        "crystal_id": "test_crystal",
                        "mtz": str(mtz_path),
                        "catalogue_id": "test_catalogue",
                        "sds_page_mass_kda": [],
                        "allow_remote_sequence_submission": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    params = inputs / "params.json"
    params.write_text(
        json.dumps(
            {
                "catalogues": str(catalogue_manifest),
                "crystals": str(crystal_manifest),
                "config": str(REPOSITORY / "examples/config.yaml"),
                "database_manifest": str(
                    REPOSITORY / "tests/fixtures/stubs/database_manifest.json"
                ),
                "phenix_manifest": str(
                    REPOSITORY / "tests/fixtures/stubs/phenix_install_manifest.json"
                ),
                "review_mode": "prepare",
                "profile_mode": "smoke",
                "skip_xtriage": True,
            }
        ),
        encoding="utf-8",
    )
    return params


def check_stubs() -> None:
    """Run all stubs and real Task 05, verify outputs, and exercise resume."""

    with tempfile.TemporaryDirectory(
        prefix="nf-genome-to-diffraction-stub-", dir="/tmp"
    ) as temporary:
        temporary_root = Path(temporary)
        environment = _environment(temporary_root / "nxf-home")
        main_out = temporary_root / "main-results"
        database_out = temporary_root / "database-results"
        discovery_out = temporary_root / "discovery-results"
        cache_root = temporary_root / "cache"

        main_command = [
            "nextflow",
            "run",
            "main.nf",
            "-profile",
            "test",
            "-stub-run",
            "-params-file",
            "tests/fixtures/stubs/main_params.yaml",
            "--outdir",
            str(main_out),
            "--cache_root",
            str(cache_root),
        ]
        _run(main_command, environment=environment)
        _assert_files(
            main_out,
            {
                "catalogue_manifest.json",
                "crystal_manifest.json",
                "pipeline_config.yaml",
                "database_manifest.json",
                "phenix_install_manifest.json",
                "pipeline_scope.json",
                "sequence_groups.jsonl",
                "source_records.jsonl",
                "mtz_preflight.jsonl",
                "matthews_hypotheses.jsonl",
                "matthews_hypotheses.parquet",
                "matthews_report.md",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )

        resumed = _run([*main_command, "-resume"], environment=environment)
        resumed_output = f"{resumed.stdout}\n{resumed.stderr}".lower()
        if "cached" not in resumed_output:
            raise RuntimeError(
                "resumed stub run did not report cached work:\n" + resumed_output
            )

        discovery_command = [
            "nextflow",
            "run",
            "discover_structures.nf",
            "-profile",
            "test",
            "-stub-run",
            "--sequence_groups",
            "tests/fixtures/stubs/sequence_groups.jsonl",
            "--source_records",
            "tests/fixtures/stubs/source_records.jsonl",
            "--database_manifest",
            "tests/fixtures/stubs/database_manifest.json",
            "--outdir",
            str(discovery_out),
            "--cache_root",
            str(cache_root),
        ]
        _run(discovery_command, environment=environment)
        _assert_files(
            discovery_out,
            {
                "search_results.jsonl",
                "structural_hits.jsonl",
                "search_manifest.json",
                "mmseqs-results.tsv",
                "mmseqs.log",
                "foldseek-results.tsv",
                "foldseek.log",
                "coordinate_sources.jsonl",
                "http.log",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        discovery_resumed = _run(
            [*discovery_command, "-resume"], environment=environment
        )
        discovery_resumed_output = (
            f"{discovery_resumed.stdout}\n{discovery_resumed.stderr}".lower()
        )
        if "cached" not in discovery_resumed_output:
            raise RuntimeError(
                "resumed structural-discovery stub did not report cached work:\n"
                + discovery_resumed_output
            )

        database_command = [
            "nextflow",
            "run",
            "prepare_databases.nf",
            "-profile",
            "test",
            "-stub-run",
            "-params-file",
            "tests/fixtures/stubs/database_params.yaml",
            "--outdir",
            str(database_out),
            "--database_root",
            str(temporary_root / "database-root"),
        ]
        _run(database_command, environment=environment)
        _assert_files(
            database_out,
            {
                "database_manifest.json",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )

        real_main_out = temporary_root / "main-real-results"
        real_main_cache = temporary_root / "main-real-cache"
        real_params = _write_real_inputs(temporary_root)
        real_main_command = [
            "nextflow",
            "run",
            "main.nf",
            "-profile",
            "test",
            "-params-file",
            str(real_params),
            "--outdir",
            str(real_main_out),
            "--cache_root",
            str(real_main_cache),
        ]
        _run(real_main_command, environment=environment)
        _assert_files(
            real_main_out,
            {
                "catalogue_import_manifest.json",
                "mtz_preflight.jsonl",
                "preflight_report.md",
                "matthews_hypotheses.jsonl",
                "matthews_hypotheses.tsv",
                "matthews_hypotheses.parquet",
                "matthews_report.md",
                "pipeline_scope.json",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        real_resumed = _run([*real_main_command, "-resume"], environment=environment)
        if "cached" not in f"{real_resumed.stdout}\n{real_resumed.stderr}".lower():
            raise RuntimeError("resumed real Task 05 run did not report cached work")

        real_database_command = [
            part for part in database_command if part != "-stub-run"
        ]
        real_database_command.extend(
            [
                "--verify_only",
                "false",
                "--minimum_free_bytes",
                "0",
                "--storage_limit_bytes",
                "100000000",
            ]
        )
        _run(real_database_command, environment=environment)
        _assert_files(database_out, {"database_manifest.json"})
        expected_database_manifest = (
            database_out / "provenance" / "database_manifest.json"
        )
        expected_database_sha256 = hashlib.sha256(
            expected_database_manifest.read_bytes()
        ).hexdigest()
        verified_database_command = [
            *real_database_command,
            "--verify_only",
            "true",
            "--expected_manifest",
            str(expected_database_manifest),
            "--expected_manifest_sha256",
            expected_database_sha256,
        ]
        _run(verified_database_command, environment=environment)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--syntax", action="store_true")
    mode.add_argument("--stub", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested Nextflow foundation check."""

    args = _build_parser().parse_args(argv)
    try:
        if args.syntax:
            check_syntax()
        else:
            check_stubs()
    except (OSError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 1
    print("Nextflow workflow check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
