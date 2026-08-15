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
        integrated_out = temporary_root / "integrated-first-copy-results"
        post_checkpoint_out = temporary_root / "integrated-additional-copy-results"
        integrated_t12_out = temporary_root / "integrated-t12-results"
        database_out = temporary_root / "database-results"
        discovery_out = temporary_root / "discovery-results"
        coordinate_out = temporary_root / "coordinate-results"
        pdb_model_out = temporary_root / "pdb-model-results"
        model_out = temporary_root / "model-results"
        first_copy_out = temporary_root / "first-copy-results"
        diverse_first_copy_out = temporary_root / "diverse-first-copy-results"
        control_first_copy_out = temporary_root / "control-first-copy-results"
        additional_copy_out = temporary_root / "additional-copy-results"
        refinement_out = temporary_root / "refinement-results"
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

        integrated_cache_root = temporary_root / "integrated-cache"
        integrated_command = [
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
            "--outdir",
            str(integrated_out),
            "--cache_root",
            str(integrated_cache_root),
        ]
        _run(integrated_command, environment=environment)
        _assert_files(
            integrated_out,
            {
                "pipeline_scope.json",
                "sequence_groups.jsonl",
                "source_records.jsonl",
                "mtz_preflight.jsonl",
                "matthews_hypotheses.jsonl",
                "search_results.jsonl",
                "structural_hits.jsonl",
                "search_manifest.json",
                "coordinate_sources.jsonl",
                "coordinate_hit_mappings.jsonl",
                "registration_manifest.json",
                "processed_models.jsonl",
                "model_preparation_manifest.json",
                "crystal_dispatch.json",
                "crystal_id.txt",
                "input.mtz",
                "funnel_manifest.json",
                "mr_hypotheses.jsonl",
                "normalised_mr_result.json",
                "normalised_mr_result.jsonl",
                "phaser_command.json",
                "PHASER.log",
                "mr_seed_review_manifest.json",
                "mr_seed_candidates.tsv",
                "mr_seed_candidates.html",
                "mr_seed_approval_candidates.tsv",
                "approved_mr_seeds.tsv",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        integrated_scope = json.loads(
            (integrated_out / "scope" / "pipeline_scope.json").read_text(
                encoding="utf-8"
            )
        )
        if integrated_scope.get("analysis_stage") != "first_copy":
            raise RuntimeError("integrated main workflow lost its stage identity")
        approval_template = integrated_out / "mr_seed_review/approved_mr_seeds.tsv"
        if len(approval_template.read_text(encoding="utf-8").splitlines()) != 1:
            raise RuntimeError(
                "integrated first-copy workflow fabricated an MR-seed decision"
            )
        integrated_resumed = _run(
            [*integrated_command, "-resume"], environment=environment
        )
        integrated_resumed_output = (
            f"{integrated_resumed.stdout}\n{integrated_resumed.stderr}".lower()
        )
        if "cached" not in integrated_resumed_output:
            raise RuntimeError(
                "resumed integrated first-copy stub did not report cached work:\n"
                + integrated_resumed_output
            )

        post_checkpoint_command = [
            "nextflow",
            "run",
            "main.nf",
            "-profile",
            "test",
            "-stub-run",
            "-params-file",
            "tests/fixtures/stubs/main_params.yaml",
            "--analysis_stage",
            "additional_copy",
            "--approved_mr_seeds",
            "examples/approvals/approved_mr_seeds.tsv",
            "--outdir",
            str(post_checkpoint_out),
            "--cache_root",
            str(temporary_root / "post-checkpoint-cache"),
        ]
        _run(post_checkpoint_command, environment=environment)
        _assert_files(
            post_checkpoint_out,
            {
                "mr_seed_review_manifest.json",
                "approved_mr_seeds.tsv",
                "approved_seeds.tsv",
                "additional_copy_seeds.tsv",
                "validated_mr_seed_decisions.json",
                "live_m4_stage_manifest.json",
                "additional_copy_result.json",
                "additional_copy_result.jsonl",
                "additional_copy_series_results.jsonl",
                "additional_copy_series_summary.json",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        post_scope = json.loads(
            (post_checkpoint_out / "scope" / "pipeline_scope.json").read_text(
                encoding="utf-8"
            )
        )
        if post_scope.get("analysis_stage") != "additional_copy":
            raise RuntimeError("post-checkpoint workflow lost its stage identity")
        post_stage = json.loads(
            (
                post_checkpoint_out
                / "approved_mr_seed_stage/live_m4_stage_manifest.json"
            ).read_text(encoding="utf-8")
        )
        if (
            post_stage.get("all_approved_seeds_retained") is not True
            or post_stage.get("numeric_score_filter_applied") is not False
        ):
            raise RuntimeError("post-checkpoint stage filtered an approved seed")
        post_resumed = _run(
            [*post_checkpoint_command, "-resume"], environment=environment
        )
        if "cached" not in (f"{post_resumed.stdout}\n{post_resumed.stderr}".lower()):
            raise RuntimeError(
                "resumed post-checkpoint workflow did not report cached work"
            )

        integrated_t12_command = [
            "nextflow",
            "run",
            "main.nf",
            "-profile",
            "test",
            "-stub-run",
            "-params-file",
            "tests/fixtures/stubs/main_params.yaml",
            "--analysis_stage",
            "t12",
            "--approved_mr_seeds",
            "examples/approvals/approved_mr_seeds.tsv",
            "--outdir",
            str(integrated_t12_out),
            "--cache_root",
            str(temporary_root / "integrated-t12-cache"),
        ]
        _run(integrated_t12_command, environment=environment)
        _assert_files(
            integrated_t12_out,
            {
                "live_m4_stage_manifest.json",
                "additional_copy_series_summary.json",
                "t12_stage_manifest.json",
                "finalists.tsv",
                "copy_count_report.tsv",
                "copy_count_report.md",
                "brief_refinement_result.json",
                "sequence_map_result.json",
                "t12_command.json",
                "sequence_checkpoint_manifest.json",
                "sequence_candidates_top10.tsv",
                "sequence_candidates_top25.tsv",
                "sequence_candidates_full.tsv",
                "sequence_candidates.html",
                "sequence_approval_candidates.tsv",
                "approved_sequence_groups.tsv",
                "sequence_gene_annotations.tsv",
                "sequence_matthews_context.tsv",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        t12_scope = json.loads(
            (integrated_t12_out / "scope" / "pipeline_scope.json").read_text(
                encoding="utf-8"
            )
        )
        if t12_scope.get("analysis_stage") != "t12":
            raise RuntimeError("integrated T12 workflow lost its stage identity")
        t12_stage = json.loads(
            (integrated_t12_out / "live_t12_stage/t12_stage_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        if (
            t12_stage.get("all_approved_seeds_retained") is not True
            or t12_stage.get("numeric_score_filter_applied") is not False
            or t12_stage.get("failed_addition_proves_absence") is not False
        ):
            raise RuntimeError("integrated T12 stage lost retain-all semantics")
        t12_checkpoint = json.loads(
            (
                integrated_t12_out
                / "t12_sequence_checkpoint/sequence_checkpoint_manifest.json"
            ).read_text(encoding="utf-8")
        )
        if (
            t12_checkpoint.get("execution_mode") != "normal_workflow"
            or t12_checkpoint.get("all_finalists_retained") is not True
            or t12_checkpoint.get("automatic_approval") is not False
            or t12_checkpoint.get("retained_finalist_count") != 1
        ):
            raise RuntimeError("integrated T12.5 lost retain-all checkpoint semantics")
        with (
            integrated_t12_out / "t12_sequence_checkpoint/approved_sequence_groups.tsv"
        ).open(encoding="utf-8", newline="") as handle:
            if len(handle.readlines()) != 1:
                raise RuntimeError("integrated T12.5 fabricated a sequence decision")
        integrated_t12_resumed = _run(
            [*integrated_t12_command, "-resume"], environment=environment
        )
        if "cached" not in (
            f"{integrated_t12_resumed.stdout}\n{integrated_t12_resumed.stderr}".lower()
        ):
            raise RuntimeError("resumed integrated T12 did not report cached work")

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

        coordinate_command = [
            "nextflow",
            "run",
            "register_coordinates.nf",
            "-profile",
            "test",
            "-stub-run",
            "--structural_hits",
            "tests/fixtures/stubs/structure_search/structural_hits.jsonl",
            "--sequence_groups",
            "tests/fixtures/stubs/sequence_groups.jsonl",
            "--database_manifest",
            "tests/fixtures/stubs/database_manifest.json",
            "--outdir",
            str(coordinate_out),
            "--cache_root",
            str(cache_root / "coordinate-registration"),
        ]
        _run(coordinate_command, environment=environment)
        _assert_files(
            coordinate_out,
            {
                "coordinate_sources.jsonl",
                "coordinate_hit_mappings.jsonl",
                "registration_manifest.json",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        coordinate_resumed = _run(
            [*coordinate_command, "-resume"], environment=environment
        )
        if "cached" not in (
            f"{coordinate_resumed.stdout}\n{coordinate_resumed.stderr}".lower()
        ):
            raise RuntimeError(
                "resumed PDB coordinate-registration stub did not report cached work"
            )

        pdb_model_command = [
            "nextflow",
            "run",
            "prepare_pdb_models.nf",
            "-profile",
            "test",
            "-stub-run",
            "--coordinate_sources",
            "tests/fixtures/stubs/pdb_coordinate_registration/coordinate_sources.jsonl",
            "--coordinate_hit_mappings",
            "tests/fixtures/stubs/pdb_coordinate_registration/coordinate_hit_mappings.jsonl",
            "--sequence_groups",
            "tests/fixtures/stubs/sequence_groups.jsonl",
            "--outdir",
            str(pdb_model_out),
            "--cache_root",
            str(cache_root / "pdb-model-preparation"),
        ]
        _run(pdb_model_command, environment=environment)
        _assert_files(
            pdb_model_out,
            {
                "processed_models.jsonl",
                "model_preparation_manifest.json",
                "stub.pdb",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        pdb_model_resumed = _run(
            [*pdb_model_command, "-resume"], environment=environment
        )
        if "cached" not in (
            f"{pdb_model_resumed.stdout}\n{pdb_model_resumed.stderr}".lower()
        ):
            raise RuntimeError(
                "resumed experimental-model stub did not report cached work"
            )

        model_command = [
            "nextflow",
            "run",
            "prepare_models.nf",
            "-profile",
            "test",
            "-stub-run",
            "--coordinate_sources",
            "tests/fixtures/stubs/afdb_exact_search/coordinate_sources.jsonl",
            "--sequence_groups",
            "tests/fixtures/stubs/sequence_groups.jsonl",
            "--phenix_manifest",
            "tests/fixtures/stubs/phenix_install_manifest.json",
            "--outdir",
            str(model_out),
            "--cache_root",
            str(cache_root / "model-preparation"),
        ]
        _run(model_command, environment=environment)
        _assert_files(
            model_out,
            {
                "processed_models.jsonl",
                "model_preparation_manifest.json",
                "stub.pdb",
                "phenix.process_predicted_model.log",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        model_resumed = _run([*model_command, "-resume"], environment=environment)
        if "cached" not in f"{model_resumed.stdout}\n{model_resumed.stderr}".lower():
            raise RuntimeError(
                "resumed predicted-model stub did not report cached work"
            )

        first_copy_command = [
            "nextflow",
            "run",
            "screen_first_copy.nf",
            "-profile",
            "test",
            "-stub-run",
            "--coordinate_sources",
            "tests/fixtures/stubs/afdb_exact_search/coordinate_sources.jsonl",
            "--prepared_models",
            "tests/fixtures/stubs/predicted_model_preparation",
            "--sequence_groups",
            "tests/fixtures/stubs/sequence_groups.jsonl",
            "--matthews",
            "tests/fixtures/stubs/mtz_preflight.jsonl",
            "--preflight",
            "tests/fixtures/stubs/mtz_preflight.jsonl",
            "--config",
            "examples/config.yaml",
            "--crystal_id",
            "test_crystal_01",
            "--mtz",
            "tests/fixtures/stubs/predicted_model_preparation/models/stub.pdb",
            "--phenix_manifest",
            "tests/fixtures/stubs/phenix_install_manifest.json",
            "--outdir",
            str(first_copy_out),
            "--cache_root",
            str(cache_root / "first-copy"),
        ]
        _run(first_copy_command, environment=environment)
        _assert_files(
            first_copy_out,
            {
                "funnel_manifest.json",
                "mr_hypotheses.jsonl",
                "mr_hypotheses.tsv",
                "normalised_mr_result.json",
                "normalised_mr_result.jsonl",
                "phaser_command.json",
                "PHASER.log",
                "phenix.phaser.capture.log",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        first_copy_resumed = _run(
            [*first_copy_command, "-resume"], environment=environment
        )
        if "cached" not in (
            f"{first_copy_resumed.stdout}\n{first_copy_resumed.stderr}".lower()
        ):
            raise RuntimeError("resumed first-copy stub did not report cached work")

        diverse_first_copy_command = [
            "nextflow",
            "run",
            "screen_diverse_first_copy.nf",
            "-profile",
            "test",
            "-stub-run",
            "--predicted_coordinate_sources",
            "tests/fixtures/stubs/afdb_exact_search/coordinate_sources.jsonl",
            "--predicted_prepared_models",
            "tests/fixtures/stubs/predicted_model_preparation",
            "--pdb_coordinate_sources",
            "tests/fixtures/stubs/pdb_coordinate_registration/coordinate_sources.jsonl",
            "--coordinate_hit_mappings",
            "tests/fixtures/stubs/pdb_coordinate_registration/coordinate_hit_mappings.jsonl",
            "--experimental_prepared_models",
            "tests/fixtures/stubs/experimental_model_preparation",
            "--sequence_groups",
            "tests/fixtures/stubs/sequence_groups.jsonl",
            "--matthews",
            "tests/fixtures/stubs/mtz_preflight.jsonl",
            "--preflight",
            "tests/fixtures/stubs/mtz_preflight.jsonl",
            "--config",
            "examples/config.yaml",
            "--crystal_id",
            "test_crystal_01",
            "--mtz",
            "tests/fixtures/stubs/predicted_model_preparation/models/stub.pdb",
            "--phenix_manifest",
            "tests/fixtures/stubs/phenix_install_manifest.json",
            "--outdir",
            str(diverse_first_copy_out),
            "--cache_root",
            str(cache_root / "diverse-first-copy"),
        ]
        _run(diverse_first_copy_command, environment=environment)
        _assert_files(
            diverse_first_copy_out,
            {
                "funnel_manifest.json",
                "mr_hypotheses.jsonl",
                "mr_hypotheses.tsv",
                "processed_models.jsonl",
                "model_preparation_manifest.json",
                "normalised_mr_result.json",
                "normalised_mr_result.jsonl",
                "phaser_command.json",
                "PHASER.log",
                "phenix.phaser.capture.log",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        diverse_first_copy_resumed = _run(
            [*diverse_first_copy_command, "-resume"], environment=environment
        )
        if (
            "cached"
            not in (
                f"{diverse_first_copy_resumed.stdout}\n"
                f"{diverse_first_copy_resumed.stderr}"
            ).lower()
        ):
            raise RuntimeError(
                "resumed diverse first-copy stub did not report cached work"
            )

        control_first_copy_command = [
            "nextflow",
            "run",
            "screen_first_copy_controls.nf",
            "-profile",
            "test",
            "-stub-run",
            "--control_bundle",
            "tests/fixtures/stubs/first_copy_controls",
            "--sequence_groups",
            "tests/fixtures/stubs/sequence_groups.jsonl",
            "--preflight",
            "tests/fixtures/stubs/mtz_preflight.jsonl",
            "--mtz",
            "tests/fixtures/stubs/predicted_model_preparation/models/stub.pdb",
            "--phenix_manifest",
            "tests/fixtures/stubs/phenix_install_manifest.json",
            "--outdir",
            str(control_first_copy_out),
            "--cache_root",
            str(cache_root / "control-first-copy"),
        ]
        _run(control_first_copy_command, environment=environment)
        _assert_files(
            control_first_copy_out,
            {
                "normalised_mr_result.json",
                "normalised_mr_result.jsonl",
                "phaser_command.json",
                "PHASER.log",
                "phenix.phaser.capture.log",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        control_trace = control_first_copy_out / "pipeline_info/trace.tsv"
        control_trace_rows = control_trace.read_text(encoding="utf-8").splitlines()
        if len(control_trace_rows) != 3:
            raise RuntimeError(
                "control first-copy stub did not execute both fixed hypotheses"
            )
        control_trace_text = "\n".join(control_trace_rows)
        for hypothesis_token in ("mrhyp_aaaaaaaa", "mrhyp_bbbbbbbb"):
            if hypothesis_token not in control_trace_text:
                raise RuntimeError(
                    "control first-copy trace omitted fixed hypothesis "
                    f"{hypothesis_token}"
                )
        control_first_copy_resumed = _run(
            [*control_first_copy_command, "-resume"], environment=environment
        )
        if (
            "cached"
            not in (
                f"{control_first_copy_resumed.stdout}\n"
                f"{control_first_copy_resumed.stderr}"
            ).lower()
        ):
            raise RuntimeError(
                "resumed control first-copy stub did not report cached work"
            )

        additional_seeds = temporary_root / "additional-seeds.tsv"
        stub_search_model = (
            REPOSITORY
            / "tests/fixtures/stubs/predicted_model_preparation/models/stub.pdb"
        )
        additional_seeds.write_text(
            "seed_solution_id\tsearch_model\tsearch_model_sha256\n"
            "sol_cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\t"
            f"{stub_search_model}\t"
            f"{hashlib.sha256(stub_search_model.read_bytes()).hexdigest()}\n",
            encoding="utf-8",
        )
        additional_copy_command = [
            "nextflow",
            "run",
            "screen_additional_copies.nf",
            "-profile",
            "test",
            "-stub-run",
            "--seeds",
            str(additional_seeds),
            "--review_validation",
            "tests/fixtures/stubs/additional_copy_result.json",
            "--review_package",
            "tests/fixtures/stubs/additional_copy_result.json",
            "--hypotheses",
            "tests/fixtures/stubs/mr_hypothesis.json",
            "--sequence_groups",
            "tests/fixtures/stubs/sequence_groups.jsonl",
            "--preflight",
            "tests/fixtures/stubs/mtz_preflight.jsonl",
            "--mtz",
            "tests/fixtures/stubs/predicted_model_preparation/models/stub.pdb",
            "--phenix_manifest",
            "tests/fixtures/stubs/phenix_install_manifest.json",
            "--outdir",
            str(additional_copy_out),
            "--cache_root",
            str(cache_root / "additional-copy"),
        ]
        _run(additional_copy_command, environment=environment)
        _assert_files(
            additional_copy_out,
            {
                "additional_copy_result.json",
                "additional_copy_result.jsonl",
                "additional_copy_series_results.jsonl",
                "additional_copy_series_summary.json",
                "phaser_command.json",
                "add_copy.eff",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        additional_copy_resumed = _run(
            [*additional_copy_command, "-resume"], environment=environment
        )
        if "cached" not in (
            f"{additional_copy_resumed.stdout}\n{additional_copy_resumed.stderr}".lower()
        ):
            raise RuntimeError(
                "resumed additional-copy stub did not report cached work"
            )

        refinement_finalists = temporary_root / "refinement-finalists.tsv"
        parent_digest = hashlib.sha256(stub_search_model.read_bytes()).hexdigest()
        refinement_finalists.write_text(
            "seed_solution_id\tsequence_group_id\tinput_copy_count\t"
            "parent_coordinate\tparent_coordinate_sha256\tparent_mtz\t"
            "parent_mtz_sha256\tresolution\tobservation_labels\n"
            "sol_stub\t"
            "seq_2cdbeb9e27633f6c402934df4721e2733a2eb0609549ff23035550640d9f6255\t"
            f"2\t{stub_search_model}\t{parent_digest}\t{stub_search_model}\t"
            f"{parent_digest}\t2.5\tI,SIGI\n",
            encoding="utf-8",
        )
        refinement_command = [
            "nextflow",
            "run",
            "refine_finalists.nf",
            "-profile",
            "test",
            "-stub-run",
            "--finalists",
            str(refinement_finalists),
            "--sequence_groups",
            "tests/fixtures/stubs/sequence_groups.jsonl",
            "--source_records",
            "tests/fixtures/stubs/source_records.jsonl",
            "--phenix_manifest",
            "tests/fixtures/stubs/phenix_install_manifest.json",
            "--outdir",
            str(refinement_out),
            "--cache_root",
            str(cache_root / "refinement"),
        ]
        _run(refinement_command, environment=environment)
        _assert_files(
            refinement_out,
            {
                "brief_refinement_result.json",
                "sequence_map_result.json",
                "t12_command.json",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        refinement_resumed = _run(
            [*refinement_command, "-resume"], environment=environment
        )
        if "cached" not in (
            f"{refinement_resumed.stdout}\n{refinement_resumed.stderr}".lower()
        ):
            raise RuntimeError("resumed refinement stub did not report cached work")

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
