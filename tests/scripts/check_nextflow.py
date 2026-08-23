"""Parse and exercise the implemented Nextflow entry points."""

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import gemmi
import numpy as np

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.localisation import (
    ActiveWaveCompletion,
    ActiveWaveGroupResult,
    ActiveWaveResultStatus,
    DeepTMHMMRuntimeContract,
    LocalisationOutcome,
    PSortbRuntimeContract,
)
from genome_to_diffraction.schemas.results import SequenceGroupRecord

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


def _write_p6_empty_partner_stub_bundle(root: Path) -> Path:
    """Create the complete 1,845-row missing-B plan used by the P6 stub."""

    bundle = root / "p6-empty-partner-stub"
    plan_directory = bundle / "partner_search_plan"
    plan_directory.mkdir(parents=True)
    (bundle / "p6_empty_partner.stub").write_text("p6-missing-b\n", encoding="utf-8")

    candidates: list[dict[str, object]] = []
    for rank in range(1, 1846):
        candidate_digest = hashlib.sha256(
            f"p6-missing-b-candidate-{rank}".encode()
        ).hexdigest()
        sequence_digest = hashlib.sha256(
            f"p6-missing-b-sequence-{rank}".encode()
        ).hexdigest()
        candidates.append(
            {
                "schema_version": "1.0",
                "candidate_id": f"partnercand_{candidate_digest}",
                "rank": rank,
                "sequence_group_id": f"seq_{sequence_digest}",
                "selection_status": "unsearchable_no_model",
                "sds_page_prior_label": "unavailable",
                "native_page_prior_label": "unavailable",
                "ordering_reasons": [
                    "sds_page:unavailable",
                    "native_page:unavailable_neutral",
                    "selection:unsearchable_no_model",
                ],
            }
        )

    plan_id = "partnerplan_" + hashlib.sha256(b"p6-missing-b-plan").hexdigest()
    plan = {
        "schema_version": "1.0",
        "plan_id": plan_id,
        "adapter_version": "catalogue-partner-plan-v1",
        "crystal_id": "6RTZ",
        "parent_sequence_group_id": "seq_"
        + hashlib.sha256(b"p6-missing-b-parent").hexdigest(),
        "parent_state_sha256": hashlib.sha256(b"p6-missing-b-parent-state").hexdigest(),
        "parent_copy_count": 1,
        "partner_copy_count": 1,
        "candidate_count": 1845,
        "searchable_candidate_count": 0,
        "selected_attempt_count": 0,
        "deferred_cap_count": 0,
        "unsearchable_candidate_count": 1845,
        "selection_cap": 25,
        "cap_reason": "prototype_first_wave_25",
        "candidates": candidates,
    }
    plan_path = plan_directory / "partner_search_plan.json"
    plan_path.write_text(
        json.dumps(plan, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (plan_directory / "partner_candidates.jsonl").write_text(
        "".join(
            json.dumps(candidate, sort_keys=True, separators=(",", ":")) + "\n"
            for candidate in candidates
        ),
        encoding="utf-8",
    )
    (plan_directory / "selected_partner_candidate_ids.txt").write_text(
        "", encoding="utf-8"
    )

    summary = {
        "schema_version": "1.0",
        "summary_id": "partnersummary_"
        + hashlib.sha256(b"p6-missing-b-summary").hexdigest(),
        "plan_id": plan_id,
        "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "candidate_count": 1845,
        "selected_attempt_count": 0,
        "result_count": 0,
        "completed_hit_count": 0,
        "completed_no_hit_count": 0,
        "failed_tool_execution_count": 0,
        "failed_parse_count": 0,
        "deferred_cap_count": 0,
        "unsearchable_candidate_count": 1845,
        "selected_candidate_ids": [],
        "result_candidate_ids": [],
        "result_search_ids": [],
        "all_selected_attempts_retained": True,
        "failed_search_proves_partner_absence": False,
    }
    (plan_directory / "partner_attempt_summary.stub.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return bundle


def _p6_empty_partner_command(
    *, output: Path, cache: Path, stub_bundle: Path
) -> list[str]:
    """Build the fixed command for the real empty-selected workflow stub."""

    stub_root = REPOSITORY / "tests/fixtures/stubs"
    return [
        "nextflow",
        "-C",
        "tests/fixtures/stubs/p6_empty_partner/nextflow.config",
        "run",
        "tests/fixtures/stubs/p6_empty_partner/main.nf",
        "-stub-run",
        "--approved_stage",
        str(stub_root / "approved_mr_seed_stage"),
        "--review_package",
        str(stub_root / "mr_seed_review"),
        "--sequence_groups",
        str(stub_root / "sequence_groups.jsonl"),
        "--matthews",
        str(stub_root / "mtz_preflight.jsonl"),
        "--preflight",
        str(stub_root / "mtz_preflight.jsonl"),
        "--pipeline_config",
        str(REPOSITORY / "examples/config.yaml"),
        "--model_registry",
        str(stub_bundle),
        "--mtz",
        str(stub_root / "mtz_preflight.jsonl"),
        "--phenix_manifest",
        str(stub_root / "phenix_install_manifest.json"),
        "--outdir",
        str(output),
        "--cache_root",
        str(cache),
    ]


def _read_trace(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8", newline="") as handle:
        return tuple(csv.DictReader(handle, delimiter="\t"))


def check_p6_empty_partner_stub() -> None:
    """Exercise the P6 zero-selection branch through the real workflow graph."""

    with tempfile.TemporaryDirectory(
        prefix="nf-genome-to-diffraction-p6-empty-", dir="/tmp"
    ) as temporary:
        temporary_root = Path(temporary)
        environment = _environment(temporary_root / "nxf-home")
        output = temporary_root / "results"
        stub_bundle = _write_p6_empty_partner_stub_bundle(temporary_root)
        command = _p6_empty_partner_command(
            output=output,
            cache=temporary_root / "cache",
            stub_bundle=stub_bundle,
        )
        _run(command, environment=environment)

        trace_path = output / "pipeline_info/trace.tsv"
        first_rows = _read_trace(trace_path)
        first_counts = Counter(row["process"].split(":")[-1] for row in first_rows)
        expected_counts = Counter(
            {
                "BUILD_PARTNER_PLAN": 1,
                "SUMMARIZE_PARTNER_ATTEMPTS": 1,
            }
        )
        if first_counts != expected_counts:
            raise RuntimeError(
                "P6 empty-selected stub scheduled the wrong process set: "
                f"{dict(sorted(first_counts.items()))}"
            )
        if {row["status"] for row in first_rows} != {"COMPLETED"}:
            raise RuntimeError("P6 empty-selected stub did not complete both tasks")

        plan_paths = tuple(output.rglob("partner_search_plan.json"))
        candidate_paths = tuple(output.rglob("partner_candidates.jsonl"))
        selected_paths = tuple(output.rglob("selected_partner_candidate_ids.txt"))
        summary_paths = tuple(output.rglob("partner_attempt_summary.json"))
        if not all(
            len(paths) == 1
            for paths in (plan_paths, candidate_paths, selected_paths, summary_paths)
        ):
            raise RuntimeError(
                "P6 empty-selected outputs were not published exactly once"
            )

        plan_path = plan_paths[0]
        candidate_path = candidate_paths[0]
        selected_path = selected_paths[0]
        summary_path = summary_paths[0]
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        candidate_rows = tuple(
            json.loads(line)
            for line in candidate_path.read_text(encoding="utf-8").splitlines()
            if line
        )
        if (
            plan.get("candidate_count") != 1845
            or plan.get("selected_attempt_count") != 0
            or plan.get("unsearchable_candidate_count") != 1845
            or len(plan.get("candidates", [])) != 1845
            or len(candidate_rows) != 1845
            or selected_path.read_text(encoding="utf-8") != ""
        ):
            raise RuntimeError(
                "P6 empty-selected plan lost its 1,845-candidate inventory"
            )
        if any(
            row.get("selection_status") != "unsearchable_no_model"
            for row in candidate_rows
        ):
            raise RuntimeError("P6 missing-B candidates did not remain unsearchable")

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if (
            summary.get("plan_id") != plan.get("plan_id")
            or summary.get("plan_sha256")
            != hashlib.sha256(plan_path.read_bytes()).hexdigest()
            or summary.get("candidate_count") != 1845
            or summary.get("unsearchable_candidate_count") != 1845
            or summary.get("selected_attempt_count") != 0
            or summary.get("result_count") != 0
            or summary.get("selected_candidate_ids") != []
            or summary.get("result_candidate_ids") != []
            or summary.get("result_search_ids") != []
            or summary.get("all_selected_attempts_retained") is not True
        ):
            raise RuntimeError(
                "P6 empty-selected summary is incomplete or inconsistent"
            )

        retained_paths = (plan_path, candidate_path, selected_path, summary_path)
        before_resume = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in retained_paths
        }
        _run([*command, "-resume"], environment=environment)
        resumed_rows = _read_trace(trace_path)
        resumed_counts = Counter(row["process"].split(":")[-1] for row in resumed_rows)
        if resumed_counts != expected_counts or {
            row["status"] for row in resumed_rows
        } != {"CACHED"}:
            raise RuntimeError(
                "P6 empty-selected stub did not cache both tasks on resume"
            )
        after_resume = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in retained_paths
        }
        if before_resume != after_resume:
            raise RuntimeError("P6 empty-selected resume changed retained outputs")


def _localisation_group(
    residue: str,
    outcome: LocalisationOutcome,
) -> SequenceGroupRecord:
    sequence = residue * 20
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=None,
        mass_method="not_calculated",
        residue_policy="standard_amino_acids",
        source_record_count=1,
        quality_flags=(f"stub_localisation:{outcome.value}",),
    )


def _write_localisation_stub_inputs(root: Path, *, empty: bool) -> dict[str, Path]:
    """Create checksum-valid offline runtimes, groups, and completion evidence."""

    input_root = root / "localisation-inputs"
    input_root.mkdir()
    executable = input_root / "psort"
    executable.write_text(
        "#!/usr/bin/env bash\nprintf 'PSORTb version 3.0.6\\n'\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    psortb_runtime = PSortbRuntimeContract.from_executable(executable)
    psortb_runtime_json = input_root / "psortb-runtime.json"
    atomic_write_json(
        psortb_runtime_json,
        psortb_runtime.model_dump(mode="json"),
    )
    image = input_root / "deeptmhmm-1.0.sif"
    image.write_bytes(b"synthetic user-provided image")
    deeptmhmm_runtime = DeepTMHMMRuntimeContract.from_user_image(image)
    deeptmhmm_runtime_json = input_root / "deeptmhmm-runtime.json"
    atomic_write_json(
        deeptmhmm_runtime_json,
        deeptmhmm_runtime.model_dump(mode="json"),
    )
    groups = (
        ()
        if empty
        else (
            _localisation_group("A", LocalisationOutcome.SOLUBLE),
            _localisation_group("C", LocalisationOutcome.MEMBRANE),
            _localisation_group("D", LocalisationOutcome.UNKNOWN),
            _localisation_group("E", LocalisationOutcome.FAILED),
            _localisation_group("F", LocalisationOutcome.EXTRACELLULAR),
        )
    )
    sequence_groups = input_root / "sequence-groups.jsonl"
    sequence_groups.write_text(
        "".join(f"{canonical_json_text(group)}\n" for group in reversed(groups)),
        encoding="utf-8",
    )
    active = tuple(
        sorted(
            group.sequence_group_id
            for group in groups
            if group.quality_flags == ("stub_localisation:soluble",)
        )
    )
    neutral = tuple(
        sorted(
            group.sequence_group_id
            for group in groups
            if group.quality_flags
            in {
                ("stub_localisation:unknown",),
                ("stub_localisation:failed",),
            }
        )
    )
    first_wave_groups = active + neutral
    completion = ActiveWaveCompletion.from_results(
        first_wave_groups,
        tuple(
            ActiveWaveGroupResult(
                sequence_group_id=group_id,
                status=ActiveWaveResultStatus.COMPLETED_NO_PACKED_RESULT,
                source_result_sha256=hashlib.sha256(
                    f"stub-active-wave:{group_id}".encode("ascii")
                ).hexdigest(),
            )
            for group_id in first_wave_groups
        ),
    )
    completion_json = input_root / "active-wave-completion.json"
    atomic_write_json(completion_json, completion.model_dump(mode="json"))
    return {
        "sequence_groups": sequence_groups,
        "psortb_runtime": psortb_runtime_json,
        "deeptmhmm_runtime": deeptmhmm_runtime_json,
        "active_wave_completion": completion_json,
    }


def _localisation_wave_command(
    *,
    inputs: dict[str, Path],
    output: Path,
    cache: Path,
) -> list[str]:
    command = [
        "nextflow",
        "-C",
        "tests/fixtures/stubs/localisation_wave/nextflow.config",
        "run",
        "tests/fixtures/stubs/localisation_wave/main.nf",
        "-stub-run",
    ]
    for name in (
        "sequence_groups",
        "psortb_runtime",
        "deeptmhmm_runtime",
        "active_wave_completion",
    ):
        command.extend((f"--{name}", str(inputs[name])))
    command.extend(("--outdir", str(output), "--cache_root", str(cache)))
    return command


def _assert_localisation_trace(
    rows: Sequence[dict[str, str]],
    *,
    task_count: int,
    expected_status: str,
) -> None:
    counts = Counter(row["process"].split(":")[-1] for row in rows)
    expected = Counter(
        {
            "BUILD_CATALOGUE_LOCALISATION_TASKS": 1,
            "BUILD_CATALOGUE_LOCALISATION_WAVE_POLICY": 1,
            "PLAN_LOCALISATION_REOPEN": 1,
        }
    )
    if task_count:
        expected["RUN_OFFLINE_LOCALISATION_TASK"] = task_count
    if counts != expected or {row["status"] for row in rows} != {expected_status}:
        raise RuntimeError(
            "localisation stub process set/status mismatch: "
            f"counts={dict(sorted(counts.items()))}, "
            f"statuses={sorted({row['status'] for row in rows})}"
        )


def _check_localisation_case(root: Path, *, empty: bool) -> None:
    inputs = _write_localisation_stub_inputs(root, empty=empty)
    output = root / "results"
    command = _localisation_wave_command(
        inputs=inputs,
        output=output,
        cache=root / "cache",
    )
    environment = _environment(root / "nxf-home")
    _run(command, environment=environment)
    trace = output / "pipeline_info/trace.tsv"
    task_count = 0 if empty else 5
    _assert_localisation_trace(
        _read_trace(trace),
        task_count=task_count,
        expected_status="COMPLETED",
    )
    policy_paths = tuple(output.rglob("first_wave_policy.json"))
    reopen_paths = tuple(output.rglob("localisation_reopen_plan.json"))
    inventory_paths = tuple(output.rglob("localisation_task_inventory.json"))
    if not all(
        len(paths) == 1 for paths in (policy_paths, reopen_paths, inventory_paths)
    ):
        raise RuntimeError(
            "localisation stub did not publish one policy/reopen/inventory"
        )
    policy = json.loads(policy_paths[0].read_text(encoding="utf-8"))
    reopen = json.loads(reopen_paths[0].read_text(encoding="utf-8"))
    inventory = json.loads(inventory_paths[0].read_text(encoding="utf-8"))
    if empty:
        if (
            inventory.get("task_count") != 0
            or policy.get("sequence_group_count") != 0
            or policy.get("result_count") != 0
            or reopen.get("status") != "not_required_no_excluded_groups"
            or reopen.get("reopened_count") != 0
        ):
            raise RuntimeError("empty localisation branch did not remain complete")
    else:
        result_paths = tuple(output.rglob("psortb/localisation-result.json"))
        blocked_paths = tuple(output.rglob("deeptmhmm-blocked-result.json"))
        evidence_paths = tuple(output.rglob("group-localisation-evidence.json"))
        if not (
            len(result_paths) == 5
            and len(blocked_paths) == 5
            and len(evidence_paths) == 5
        ):
            raise RuntimeError("localisation task fan-out lost a per-group result")
        statuses = Counter(
            json.loads(path.read_text(encoding="utf-8"))["execution_status"]
            for path in result_paths
        )
        if statuses != Counter({"completed_success": 4, "failed_tool_execution": 1}):
            raise RuntimeError(
                "failed PSORTb branch was not retained as typed evidence"
            )
        if any(
            json.loads(path.read_text(encoding="utf-8"))["outcome"] is not None
            for path in blocked_paths
        ):
            raise RuntimeError("blocked DeepTMHMM result fabricated an outcome")
        expected_counts = {
            "sequence_group_count": 5,
            "result_count": 5,
            "psortb_completed_count": 4,
            "psortb_failed_count": 1,
            "deeptmhmm_blocked_count": 5,
            "active_count": 1,
            "excluded_count": 2,
            "neutral_count": 2,
            "first_wave_eligible_count": 3,
        }
        if any(policy.get(name) != count for name, count in expected_counts.items()):
            raise RuntimeError("localisation wave policy count mismatch")
        if (
            len(policy.get("retained_excluded_group_ids", [])) != 2
            or reopen.get("status") != "activated_no_packed_result"
            or reopen.get("retained_excluded_count") != 2
            or reopen.get("reopened_count") != 2
            or reopen.get("reopened_group_ids")
            != policy.get("retained_excluded_group_ids")
        ):
            raise RuntimeError("zero-pack reopen did not retain/activate exclusions")
    retained_paths = (
        inventory_paths[0],
        policy_paths[0],
        reopen_paths[0],
    )
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in retained_paths
    }
    _run([*command, "-resume"], environment=environment)
    _assert_localisation_trace(
        _read_trace(trace),
        task_count=task_count,
        expected_status="CACHED",
    )
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in retained_paths
    }
    if before != after:
        raise RuntimeError("cached localisation resume changed retained outputs")


def check_localisation_wave_stub() -> None:
    """Exercise mixed/failure and zero-task catalogue branches with resume."""

    with tempfile.TemporaryDirectory(
        prefix="nf-genome-to-diffraction-localisation-mixed-", dir="/tmp"
    ) as mixed:
        _check_localisation_case(Path(mixed), empty=False)
    with tempfile.TemporaryDirectory(
        prefix="nf-genome-to-diffraction-localisation-empty-", dir="/tmp"
    ) as empty:
        _check_localisation_case(Path(empty), empty=True)


def _assert_m6_fanout_trace(
    trace_rows: Sequence[dict[str, str]], *, require_cached: bool
) -> dict[str, tuple[dict[str, str], ...]]:
    """Require the complete multi-catalogue M6 stub fan-out."""

    catalogue_keys = {
        "a" * 64,
        "e" * 64,
    }
    expected_tags = {
        "M6_IMPORT_CATALOGUE": {
            f"m6-import:{catalogue_key}" for catalogue_key in catalogue_keys
        },
        "M6_SEARCH_PDB": {f"m6-pdb:{batch_id}" for batch_id in ("b" * 64, "c" * 64)},
        "M6_SEARCH_FOLDSEEK": {
            f"m6-foldseek:{batch_id}" for batch_id in ("d" * 64, "e" * 64)
        },
        "M6_PARTITION_DISCOVERY": {
            f"m6-partition:{catalogue_key}" for catalogue_key in catalogue_keys
        },
        "M6_PREFLIGHT_CASE": {
            "m6-preflight:M6C001",
            "m6-preflight:M6C057",
        },
        "M6_PREPARE_ACTIVE_CASE": {"m6-case:M6C001"},
        "M6_PREPARE_EARLY_CASE": {"m6-early-case:M6C057"},
    }
    rows_by_process: dict[str, tuple[dict[str, str], ...]] = {}
    for process, expected in expected_tags.items():
        process_rows = tuple(
            row for row in trace_rows if row["process"].split(":")[-1] == process
        )
        actual = {row["tag"] for row in process_rows}
        if len(process_rows) != len(expected) or actual != expected:
            raise RuntimeError(
                f"M6 stub {process} fan-out mismatch: "
                f"expected={sorted(expected)}, actual={sorted(actual)}, "
                f"count={len(process_rows)}"
            )
        if require_cached and {row["status"] for row in process_rows} != {"CACHED"}:
            raise RuntimeError(
                f"resumed M6 stub did not cache every {process} task: "
                f"{sorted(row['status'] for row in process_rows)}"
            )
        rows_by_process[process] = process_rows
    return rows_by_process


def _assert_m6_cross_track_cache(
    first_rows: Sequence[dict[str, str]], leakage_rows: Sequence[dict[str, str]]
) -> None:
    """Require only the six truthless tasks to cache across M6 tracks."""

    expected_cached = {
        "M6_IMPORT_CATALOGUE": 2,
        "M6_SEARCH_PDB": 2,
        "M6_SEARCH_FOLDSEEK": 2,
    }
    cached = tuple(row for row in leakage_rows if row["status"] == "CACHED")
    completed = tuple(row for row in leakage_rows if row["status"] == "COMPLETED")
    cached_counts = Counter(row["process"].split(":")[-1] for row in cached)
    if len(leakage_rows) != 25 or cached_counts != expected_cached:
        raise RuntimeError(
            "M6 leakage resume did not cache exactly six truthless tasks: "
            f"{dict(sorted(cached_counts.items()))}"
        )
    if len(completed) != 19 or len(cached) + len(completed) != len(leakage_rows):
        raise RuntimeError("M6 leakage resume did not complete 19 track-specific tasks")
    for process in expected_cached:
        first_tags = sorted(
            row["tag"] for row in first_rows if row["process"].split(":")[-1] == process
        )
        cached_tags = sorted(
            row["tag"] for row in cached if row["process"].split(":")[-1] == process
        )
        if first_tags != cached_tags:
            raise RuntimeError(f"M6 cached task identity changed: {process}")


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

    check_p6_empty_partner_stub()
    check_localisation_wave_stub()
    with tempfile.TemporaryDirectory(
        prefix="nf-genome-to-diffraction-stub-", dir="/tmp"
    ) as temporary:
        temporary_root = Path(temporary)
        environment = _environment(temporary_root / "nxf-home")
        main_out = temporary_root / "main-results"
        integrated_out = temporary_root / "integrated-first-copy-results"
        post_checkpoint_out = temporary_root / "integrated-additional-copy-results"
        heteromer_out = temporary_root / "integrated-heteromer-results"
        integrated_t12_out = temporary_root / "integrated-t12-results"
        database_out = temporary_root / "database-results"
        discovery_out = temporary_root / "discovery-results"
        disabled_discovery_out = temporary_root / "disabled-discovery-results"
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

        heteromer_command = [
            "nextflow",
            "run",
            "main.nf",
            "-profile",
            "test",
            "-stub-run",
            "-params-file",
            "tests/fixtures/stubs/main_params.yaml",
            "--analysis_stage",
            "heteromer",
            "--approved_mr_seeds",
            "examples/approvals/approved_mr_seeds.tsv",
            "--heteromer_control_preparation",
            "tests/fixtures/stubs/approved_partner_search",
            "--outdir",
            str(heteromer_out),
            "--cache_root",
            str(temporary_root / "heteromer-cache"),
        ]
        _run(heteromer_command, environment=environment)
        _assert_files(
            heteromer_out,
            {
                "pipeline_scope.json",
                "mr_seed_review_manifest.json",
                "validated_mr_seed_decisions.json",
                "live_m4_stage_manifest.json",
                "partner_search_result.json",
                "partner_search_result.jsonl",
                "partner_search.eff",
                "phaser_command.json",
                "partner_search_plan.json",
                "partner_candidates.jsonl",
                "selected_partner_candidate_ids.txt",
                "partner_attempt_summary.json",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        heteromer_scope = json.loads(
            (heteromer_out / "scope/pipeline_scope.json").read_text(encoding="utf-8")
        )
        if heteromer_scope.get("analysis_stage") != "heteromer":
            raise RuntimeError("heteromer workflow lost its stage identity")
        planned_partner_dirs = sorted(heteromer_out.glob("planned_partner_*"))
        if (
            len(planned_partner_dirs) != 1
            or not (planned_partner_dirs[0] / "partner_search_result.json").is_file()
        ):
            raise RuntimeError("heteromer workflow did not fan out its selected B row")

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
            "--config",
            "examples/config.yaml",
            "--database_manifest",
            "tests/fixtures/stubs/provider_plan_database_manifest.json",
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
                "provider_plan.json",
                "esm_atlas.json",
                "disabled.log",
                "provider_hit_merge_manifest.json",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )
        discovery_trace = discovery_out / "pipeline_info" / "trace.tsv"
        with discovery_trace.open(encoding="utf-8", newline="") as handle:
            discovery_rows = tuple(csv.DictReader(handle, delimiter="\t"))
        discovery_process_counts = Counter(
            row["process"].split(":")[-1] for row in discovery_rows
        )
        expected_discovery_processes = {
            "RESOLVE_PROVIDER_PLAN": 1,
            "SEARCH_PDB_SEQUENCES": 1,
            "SEARCH_FOLDSEEK_PROSTT5": 1,
            "RETRIEVE_AFDB_EXACT": 1,
            "EMIT_DISABLED_ESM": 1,
            "MERGE_PDB_PROVIDER_HITS": 1,
        }
        if discovery_process_counts != expected_discovery_processes:
            raise RuntimeError(
                "structural-discovery provider routing changed: "
                f"{dict(sorted(discovery_process_counts.items()))}"
            )
        esm_results = tuple(
            json.loads(line)
            for line in (discovery_out / "esm_atlas_search/search_results.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        )
        if not esm_results or any(
            row.get("execution_status") != "skipped_policy"
            or row.get("scientific_status") != "not_interpretable"
            for row in esm_results
        ):
            raise RuntimeError("disabled ESM route did not emit typed skipped results")
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
        with discovery_trace.open(encoding="utf-8", newline="") as handle:
            discovery_resume_rows = tuple(csv.DictReader(handle, delimiter="\t"))
        if len(discovery_resume_rows) != 6 or {
            row["status"] for row in discovery_resume_rows
        } != {"CACHED"}:
            raise RuntimeError(
                "structural-discovery provider route was not fully cached"
            )

        disabled_discovery_command = list(discovery_command)
        disabled_discovery_command[disabled_discovery_command.index("--config") + 1] = (
            "tests/fixtures/stubs/config_all_providers_disabled.yaml"
        )
        disabled_discovery_command[disabled_discovery_command.index("--outdir") + 1] = (
            str(disabled_discovery_out)
        )
        disabled_discovery_command[
            disabled_discovery_command.index("--cache_root") + 1
        ] = str(cache_root / "disabled-discovery")
        _run(disabled_discovery_command, environment=environment)
        disabled_trace = disabled_discovery_out / "pipeline_info" / "trace.tsv"
        with disabled_trace.open(encoding="utf-8", newline="") as handle:
            disabled_rows = tuple(csv.DictReader(handle, delimiter="\t"))
        disabled_process_counts = Counter(
            row["process"].split(":")[-1] for row in disabled_rows
        )
        expected_disabled_processes = {
            "RESOLVE_PROVIDER_PLAN": 1,
            "EMIT_DISABLED_PDB": 1,
            "EMIT_DISABLED_FOLDSEEK": 1,
            "EMIT_DISABLED_AFDB": 1,
            "EMIT_DISABLED_ESM": 1,
            "MERGE_PDB_PROVIDER_HITS": 1,
        }
        if disabled_process_counts != expected_disabled_processes:
            raise RuntimeError(
                "all-disabled provider routing changed: "
                f"{dict(sorted(disabled_process_counts.items()))}"
            )
        for bundle_name in (
            "pdb_sequence_search",
            "prostt5_foldseek_search",
            "afdb_exact_search",
            "esm_atlas_search",
        ):
            rows = tuple(
                json.loads(line)
                for line in (
                    disabled_discovery_out / bundle_name / "search_results.jsonl"
                )
                .read_text(encoding="utf-8")
                .splitlines()
                if line
            )
            if not rows or any(
                row.get("execution_status") != "skipped_policy"
                or row.get("scientific_status") != "not_interpretable"
                for row in rows
            ):
                raise RuntimeError(
                    f"disabled provider bundle is not typed: {bundle_name}"
                )
        _run([*disabled_discovery_command, "-resume"], environment=environment)
        with disabled_trace.open(encoding="utf-8", newline="") as handle:
            disabled_resume_rows = tuple(csv.DictReader(handle, delimiter="\t"))
        if len(disabled_resume_rows) != 6 or {
            row["status"] for row in disabled_resume_rows
        } != {"CACHED"}:
            raise RuntimeError("all-disabled provider route was not fully cached")

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

        m6_out = temporary_root / "m6-nextflow-results"
        m6_cache = temporary_root / "m6-nextflow-cache"
        m6_command = [
            "nextflow",
            "run",
            "m6_validation.nf",
            "-profile",
            "test",
            "-stub-run",
            "-params-file",
            "tests/fixtures/stubs/m6_nextflow_params.yaml",
            "--outdir",
            str(m6_out),
            "--cache_root",
            str(m6_cache),
        ]
        _run(m6_command, environment=environment)
        _assert_files(
            m6_out,
            {
                "m6_scientific_summary.json",
                "m6_execution_verification.json",
                "m6_case_results.jsonl",
                "m6_candidate_rankings.jsonl",
                "m6_model_policy_results.jsonl",
                "m6_first_copy_results.jsonl",
                "m6_additional_copy_results.jsonl",
                "m6_refinement_results.jsonl",
                "m6_sequence_results.jsonl",
                "m6_sequence_summary.jsonl",
                "trace.tsv",
                "report.html",
                "timeline.html",
                "dag.html",
            },
        )
        trace_path = m6_out / "pipeline_info" / "trace.tsv"
        with trace_path.open(encoding="utf-8", newline="") as handle:
            trace_rows = tuple(csv.DictReader(handle, delimiter="\t"))
        if len(trace_rows) != 25 or {row["status"] for row in trace_rows} != {
            "COMPLETED"
        }:
            raise RuntimeError("M6 first stub run did not complete exactly 25 tasks")
        fanout_rows = _assert_m6_fanout_trace(trace_rows, require_cached=False)
        processes = {row["process"].split(":")[-1] for row in trace_rows}
        required_processes = {
            "M6_IMPORT_CATALOGUE",
            "M6_BUILD_SEARCH_BATCHES",
            "M6_SEARCH_PDB",
            "M6_SEARCH_FOLDSEEK",
            "M6_PARTITION_DISCOVERY",
            "M6_PREPARE_ACTIVE_CASE",
            "M6_PREPARE_EARLY_CASE",
            "M6_FIRST_COPY",
            "M6_EMPTY_SEEDS",
            "M6_ADDITIONAL_COPY",
            "M6_REFINEMENT",
            "M6_ASSEMBLE_CASE",
            "M6_ASSEMBLE_EMPTY_CASE",
            "M6_AGGREGATE_TRACK",
        }
        if not required_processes.issubset(processes):
            raise RuntimeError(
                "M6 stub did not exercise required fan-out branches: "
                f"{sorted(required_processes - processes)}"
            )
        search_intervals = {
            process: tuple(
                (
                    datetime.fromisoformat(row["start"]),
                    datetime.fromisoformat(row["complete"]),
                )
                for row in fanout_rows[process]
            )
            for process in ("M6_SEARCH_PDB", "M6_SEARCH_FOLDSEEK")
        }
        if not any(
            max(pdb_start, foldseek_start) <= min(pdb_complete, foldseek_complete)
            for pdb_start, pdb_complete in search_intervals["M6_SEARCH_PDB"]
            for foldseek_start, foldseek_complete in search_intervals[
                "M6_SEARCH_FOLDSEEK"
            ]
        ):
            raise RuntimeError("M6 MMseqs2 and Foldseek stub jobs did not overlap")
        summary_paths = tuple(m6_out.rglob("m6_scientific_summary.json"))
        if len(summary_paths) != 1:
            raise RuntimeError("M6 stub summary path is not unique")
        summary_path = summary_paths[0]
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if (
            summary.get("schema_version") != "2.0"
            or summary.get("adapter_version") != "m6-nextflow-run-v2"
        ):
            raise RuntimeError("M6 stub did not publish the v2 aggregate contract")
        case_records = tuple(
            json.loads(line)
            for line in (summary_path.parent / "m6_case_results.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        )
        if len(case_records) != 2 or any(
            record.get("schema_version") != "2.0"
            or record.get("adapter_version") != "m6-nextflow-case-evidence-v2"
            or not isinstance(record.get("identity_decision"), dict)
            or not isinstance(record.get("edge_observations"), list)
            for record in case_records
        ):
            raise RuntimeError("M6 stub did not retain v2 identity/edge evidence")
        m6_files = sorted(path for path in m6_out.rglob("*") if path.is_file())
        before_resume = {
            str(path.relative_to(m6_out)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in m6_files
            if "pipeline_info" not in path.parts
        }
        resumed_m6 = _run([*m6_command, "-resume"], environment=environment)
        resumed_m6_output = f"{resumed_m6.stdout}\n{resumed_m6.stderr}"
        if "cached" not in resumed_m6_output.lower():
            raise RuntimeError("resumed M6 stub did not report cached work")
        with trace_path.open(encoding="utf-8", newline="") as handle:
            resumed_trace_rows = tuple(csv.DictReader(handle, delimiter="\t"))
        if len(resumed_trace_rows) != 25 or {
            row["status"] for row in resumed_trace_rows
        } != {"CACHED"}:
            raise RuntimeError("resumed M6 stub did not cache all 25 tasks")
        _assert_m6_fanout_trace(resumed_trace_rows, require_cached=True)
        after_resume = {
            str(path.relative_to(m6_out)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in m6_out.rglob("*")
            if path.is_file() and "pipeline_info" not in path.parts
        }
        if before_resume != after_resume:
            raise RuntimeError("M6 stub resume changed scientific outputs")

        leakage_out = temporary_root / "m6-nextflow-leakage-results"
        _run(
            [
                *m6_command,
                "--track",
                "leakage",
                "--outdir",
                str(leakage_out),
                "-resume",
            ],
            environment=environment,
        )
        with (leakage_out / "pipeline_info/trace.tsv").open(
            encoding="utf-8", newline=""
        ) as handle:
            leakage_trace_rows = tuple(csv.DictReader(handle, delimiter="\t"))
        _assert_m6_fanout_trace(leakage_trace_rows, require_cached=False)
        _assert_m6_cross_track_cache(trace_rows, leakage_trace_rows)

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
    mode.add_argument("--p6-empty-partner-stub", action="store_true")
    mode.add_argument("--localisation-wave-stub", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested Nextflow foundation check."""

    args = _build_parser().parse_args(argv)
    try:
        if args.syntax:
            check_syntax()
        elif args.stub:
            check_stubs()
        elif args.p6_empty_partner_stub:
            check_p6_empty_partner_stub()
        else:
            check_localisation_wave_stub()
    except (OSError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 1
    print("Nextflow workflow check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
