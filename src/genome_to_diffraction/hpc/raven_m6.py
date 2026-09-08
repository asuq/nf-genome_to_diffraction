"""Retain fixed Raven M6 first/resume evidence for the existing truth-side gate.

This module performs bounded file validation and report assembly only. The
existing M6 Nextflow graph, child-output verifier, resource collector and frozen
63-case scientific verifier provide the evidence. The original operational
launch is the sole leakage cache authority. A login controller is never
represented as a Slurm allocation. Missing, changed or incomplete records fail.
Tests exercise source/parent checks and the shared resource/collection contracts;
native M6 acceptance still requires two fresh Raven tracks and private truth.
"""

import csv
import json
import shutil
from pathlib import Path
from typing import Literal

from genome_to_diffraction.benchmarks.m6_execution import (
    M6_SHARED_TRUTHLESS_PROCESSES,
    M6ChildOutputEvidence,
    M6ChildOutputEvidenceRequest,
    M6ResourceEvidence,
    M6ResourceEvidenceRequest,
    collect_m6_child_output_evidence,
    collect_m6_resource_evidence,
    m6_process_name,
)
from genome_to_diffraction.benchmarks.m6_scientific import verify_m6_scientific_output
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.raven_qualification import (
    RavenQualificationLaunch,
    confined,
    load_parameters,
)
from genome_to_diffraction.ids import canonical_digest

_PRECHECK_PATHS = (
    "launch.json",
    "state.json",
    "qualification/m6-scientific-summary.json",
    "qualification/m6-scientific-checksums.sha256",
)
_OUTPUTS = {
    "m6_scientific_summary.json": "m6-scientific-summary.json",
    "m6_execution_verification.json": "m6-execution-verification.json",
    "m6_case_results.jsonl": "m6-case-results.jsonl",
    "m6_candidate_rankings.jsonl.gz": "m6-candidate-rankings.jsonl.gz",
    "m6_model_policy_results.jsonl": "m6-model-policy-results.jsonl",
    "m6_sequence_summary.jsonl": "m6-sequence-summary.jsonl",
}


def operational_precheck(root: Path) -> str:
    """Hash the completed login-run authority consumed by its leakage child."""

    files = {}
    for name in _PRECHECK_PATHS:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Raven M6 operational precheck is incomplete")
        files[name] = sha256_file(path)
    return canonical_digest(files)


def collection_manifest(root: Path) -> dict[str, object]:
    """Verify a terminal Raven record, then project its observed provenance."""

    from genome_to_diffraction.hpc.raven_identification import _status

    spec = RavenQualificationLaunch.model_validate_json(
        (root / "launch.json").read_text()
    )
    status = _status(root, spec)
    if spec.stage not in {"m6-operational", "m6-leakage"} or (
        status["state"] != "COMPLETED" or status.get("exit_code") != 0
    ):
        raise ValueError("Raven M6 collection lacks a completed owned controller")
    qualification = root / "qualification"
    declared = set()
    checksum_path = qualification / "m6-scientific-checksums.sha256"
    for line in checksum_path.read_text().splitlines():
        digest, relative = line.split("  ", 1)
        path = Path(relative)
        if (
            path.is_absolute()
            or ".." in path.parts
            or str(path) != relative
            or relative in declared
            or (qualification / path).is_symlink()
            or sha256_file(qualification / path) != digest
        ):
            raise ValueError("Raven M6 collected qualification checksum changed")
        declared.add(relative)
    actual = {
        p.relative_to(qualification).as_posix()
        for p in qualification.rglob("*")
        if p.is_file() and p != checksum_path
    }
    if not declared or actual != declared:
        raise ValueError("Raven M6 qualification snapshot is incomplete")
    parameters = json.loads(
        (root / "qualification/m6-input-provenance.json").read_text()
    )
    if (
        parameters.get("run_id") != spec.run_id
        or parameters.get("input_id") != spec.input_id
        or parameters.get("runner_archive_sha256") != spec.runner_archive_sha256
        or parameters.get("software_lock_sha256") != spec.pixi_lock_sha256
    ):
        raise ValueError("Raven M6 collected inputs differ from their launch")
    summary = json.loads((qualification / "m6-scientific-summary.json").read_text())
    inputs = summary.get("input_sha256")
    if not isinstance(inputs, dict) or any(
        inputs.get(key) != value
        for key, value in {
            "phenix_manifest": spec.phenix_manifest_sha256,
            "database_manifest": parameters["database_manifest_sha256"],
            "runner_manifest": parameters["runner_manifest_sha256"],
        }.items()
    ):
        raise ValueError("Raven M6 scientific inputs differ from their launch")
    return {
        "run_id": spec.run_id,
        "site_id": "raven",
        "profile": spec.stage,
        "controller_kind": "login_process",
        "commit": spec.source_commit,
        "nf_helper_commit": spec.nf_helper_commit,
        "pixi_version": spec.pixi_version,
        "pixi_lock_sha256": spec.pixi_lock_sha256,
        "database_manifest_sha256": parameters["database_manifest_sha256"],
        "runner_archive_sha256": spec.runner_archive_sha256,
        "runner_manifest_sha256": parameters["runner_manifest_sha256"],
        "operational_parent_run_id": (
            spec.operational_parent_run.name if spec.operational_parent_run else None
        ),
        "operational_precheck_sha256": spec.operational_precheck_sha256,
    }


def validate_operational_parent(root: Path, spec: RavenQualificationLaunch) -> None:
    """Permit leakage to reuse only its exact completed operational cache."""

    from genome_to_diffraction.hpc.raven_identification import _status

    if spec.operational_parent_run is None:
        raise ValueError("Raven leakage lacks its operational parent")
    parent = confined(spec.operational_parent_run, root)
    launch = RavenQualificationLaunch.model_validate_json(
        (parent / "launch.json").read_text()
    )
    if (
        parent.parent != root / "runs"
        or parent.name != launch.run_id
        or launch.stage != "m6-operational"
        or launch.source_commit != spec.source_commit
        or launch.source_tree != spec.source_tree
        or launch.input_id != spec.input_id
        or launch.input_root != spec.input_root
        or launch.phenix_manifest_sha256 != spec.phenix_manifest_sha256
        or launch.runner_archive_sha256 != spec.runner_archive_sha256
        or _status(parent, launch).get("state") != "COMPLETED"
        or operational_precheck(parent) != spec.operational_precheck_sha256
    ):
        raise ValueError(
            "Raven leakage operational source/input/terminal binding differs"
        )
    collection_manifest(parent)
    expected_outputs = json.loads(
        (parent / "qualification/m6-first-output-inventory.json").read_text()
    )
    if _output_inventory(parent / "results/m6_scientific") != expected_outputs:
        raise ValueError("Raven operational scientific outputs changed")
    baseline = M6ChildOutputEvidence.model_validate_json(
        (parent / "qualification/m6-first-child-outputs.json").read_text()
    )
    with (parent / "qualification/m6-first-pipeline-info/trace.tsv").open(
        newline=""
    ) as stream:
        work_by_task = {
            (row["process"], row["tag"]): Path(row["workdir"])
            for row in csv.DictReader(stream, delimiter="\t")
        }
    for task in baseline.tasks:
        if m6_process_name(task.process) not in M6_SHARED_TRUTHLESS_PROCESSES:
            continue
        work = confined(
            work_by_task[(task.process, task.tag)], parent / "cache/qualification/work"
        )
        for item in task.outputs:
            path = confined(work / item.relative_path, work)
            if sha256_file(path) != item.sha256:
                raise ValueError("Raven operational truthless cache changed")


def _output_inventory(root: Path) -> dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Raven M6 output contains a symlink")
        if path.is_file():
            if len(files) >= 100000:
                raise ValueError("Raven M6 output inventory exceeds its bound")
            files[path.relative_to(root).as_posix()] = sha256_file(path)
    if not files:
        raise ValueError("Raven M6 produced no scientific outputs")
    return files


def finish_phase(
    run: Path,
    spec: RavenQualificationLaunch,
    *,
    phase: Literal["first", "resume"],
) -> None:
    """Authenticate first outputs, then require cache-identical complete replay."""

    track: Literal["operational", "leakage"]
    if spec.stage == "m6-operational":
        track = "operational"
    elif spec.stage == "m6-leakage":
        track = "leakage"
    else:
        raise ValueError("Raven M6 phase received another profile")
    qualification = run / "qualification"
    scientific = run / "results/m6_scientific"
    verify_m6_scientific_output(scientific, track)
    trace = qualification / f"m6-{phase}-pipeline-info/trace.tsv"
    output_inventory = _output_inventory(scientific)
    first_inventory_path = qualification / "m6-first-output-inventory.json"
    if phase == "first":
        atomic_write_json(first_inventory_path, output_inventory)
        evidence = collect_m6_resource_evidence(
            M6ResourceEvidenceRequest(
                policy=spec.source_root
                / "benchmarks/m6/execution-nextflow-raven-v1.yaml",
                trace=trace,
                output=qualification / "m6-child-resource-evidence.json",
            )
        )
        if not evidence.per_job_bounds_passed or evidence.child_job_count < 1:
            raise ValueError("Raven M6 resolved allocations violate the frozen policy")
        collect_m6_child_output_evidence(
            M6ChildOutputEvidenceRequest(
                track=track,
                trace=trace,
                output=qualification / "m6-first-child-outputs.json",
            )
        )
        parameters = load_parameters(spec)
        atomic_write_json(
            qualification / "m6-input-provenance.json",
            {
                "run_id": spec.run_id,
                "input_id": spec.input_id,
                "software_lock_sha256": sha256_file(spec.source_root / "pixi.lock"),
                "database_manifest_sha256": sha256_file(
                    parameters["database_manifest"]
                ),
                "runner_manifest_sha256": sha256_file(
                    parameters["runner_root"] / "runner_manifest.json"
                ),
                "runner_archive_sha256": spec.runner_archive_sha256,
            },
        )
        return
    if json.loads(first_inventory_path.read_text()) != output_inventory:
        raise ValueError("Raven M6 cached resume changed scientific output bytes")
    resumed = collect_m6_child_output_evidence(
        M6ChildOutputEvidenceRequest(
            track=track,
            trace=trace,
            output=qualification / "m6-resume-child-outputs.json",
            baseline=qualification / "m6-first-child-outputs.json",
        )
    )
    with trace.open(newline="") as stream:
        rows = tuple(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != resumed.task_count or any(
        row["status"] != "CACHED" for row in rows
    ):
        raise ValueError("Raven M6 resume did not reuse every completed task")
    replay = {
        "schema_version": "1.0",
        "track": track,
        "deterministic_replay_equivalent": True,
        "resume_equivalent": True,
        "first_task_count": resumed.task_count,
        "cached_resume_task_count": len(rows),
        "output_inventory_sha256": sha256_file(first_inventory_path),
    }
    atomic_write_json(qualification / "m6-resume-check.json", replay)
    atomic_write_json(
        qualification / "m6-resume-cache-evidence.json",
        {
            "schema_version": "1.0",
            "cache_mechanism": "nextflow_resume",
            "fully_cached_resume": True,
            "first_task_count": resumed.task_count,
            "cached_resume_task_count": len(rows),
            "first_child_output_sha256": sha256_file(
                qualification / "m6-first-child-outputs.json"
            ),
            "resume_child_output_sha256": sha256_file(
                qualification / "m6-resume-child-outputs.json"
            ),
        },
    )
    evidence = M6ResourceEvidence.model_validate_json(
        (qualification / "m6-child-resource-evidence.json").read_text()
    )
    atomic_write_json(
        qualification / "m6-runtime-provenance.json",
        {
            "schema_version": "1.1",
            "profile": spec.stage,
            "track": track,
            "execution_model": "nextflow_dsl2_slurm_fanout",
            "controller_kind": "login_process",
            "maximum_cpu_count": 32,
            "maximum_memory_gb": 16.0,
            "scheduler_ceiling_hours": 24.0,
            "tool_runtime_timeouts": False,
            "maximum_concurrent_phenix_attempts": evidence.peak_concurrent_phenix_jobs,
            "child_job_count": evidence.child_job_count,
            "peak_running_jobs": evidence.peak_running_jobs,
            "peak_aggregate_cpu_count": evidence.peak_aggregate_cpus,
            "peak_aggregate_memory_gb": evidence.peak_aggregate_memory_gb,
            "execution_policy": evidence.execution_policy_id,
        },
    )
    for source, target in _OUTPUTS.items():
        shutil.copyfile(scientific / source, qualification / target)
    checksums = qualification / "m6-scientific-checksums.sha256"
    checksums.write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(qualification).as_posix()}\n"
            for path in sorted(qualification.rglob("*"))
            if path.is_file() and path != checksums
        )
    )
