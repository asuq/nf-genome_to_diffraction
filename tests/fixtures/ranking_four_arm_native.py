"""Read-only native verification for the fixed original-client RF reference run.

The sole runtime input is the owned Raven run, plus its first-verification SHA
on resume. Original controller, immutable source, runner, database, policy,
Phenix executable and task identities are checked before scientific validation.
The existing aggregate validator rederives every original case and receipt;
actual Phenix command/exit pairs must match the complete executed receipt union.
No truth labels, expected answers or scientific settings enter this interface.

Nextflow alone executes science. This verifier reads metadata and hashes files;
its only subprocess is read-only Git provenance. It writes fixed, create-only
qualification records and byte-identical input-manifest copies, never native
task/results. Complete batching and partition metadata are rederived in a
temporary directory and compared with original bytes, without external tools.
Both passes revalidate science. Resume additionally requires the
externally frozen first receipt, all cached tasks and unchanged native bytes.
The output records native observations, not M6 acceptance or human approval.
Missing, foreign, changed, oversized or incompletely cached evidence fails.
Python 3.14, the original immutable checkout and its pinned HPC runtime are
required. Unit tests cover path/log safety; graph and native tests cover joins.
"""

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from tests.fixtures.ranking_four_arm_advancement import REFERENCE_CASE_IDS
from tests.fixtures.ranking_four_arm_aggregate import (
    ReferenceRun,
    ReferenceRunInputs,
    validate_reference_run,
)
from tests.fixtures.ranking_four_arm_cli import validate_module_origins
from tests.fixtures.ranking_four_arm_context import (
    ReferenceIdentityContext,
    ReferencePlanContext,
    ReferencePreparedContext,
)
from tests.fixtures.ranking_four_arm_continuation import ReferencePreparedCopyReceipt
from tests.fixtures.ranking_four_arm_execution import (
    ReferenceChildOutputRequest,
    collect_reference_child_outputs,
)
from tests.fixtures.ranking_four_arm_first_copy import ReferenceFirstCopyReceipt
from tests.fixtures.ranking_four_arm_native_discovery import verify_reference_discovery
from tests.fixtures.ranking_four_arm_refinement import ReferenceRefinementReceipt

from genome_to_diffraction.benchmarks.m6_execution import (
    M6ResourceEvidenceRequest,
    collect_m6_resource_evidence,
    load_m6_execution_policy,
)
from genome_to_diffraction.benchmarks.m6_verification import M6RunnerInventorySpec
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.login_process import (
    _context,
    _identity,
    _process_identity,
    _text,
)
from genome_to_diffraction.hpc.rf_reference_evidence import (
    REFERENCE_INPUT_COPIES,
    ReferenceNativeCommand,
    _owned_path,
    command_record_expectations,
    read_reference_native_task_log,
    reference_native_file_inventory,
    reference_owned_regular_file,
    reference_staged_search_inputs,
    reference_trace_tasks,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.phenix.runtime import validate_manifest_environment
from genome_to_diffraction.schemas.base import ContractModel
from genome_to_diffraction.schemas.io import load_json_document

_PROFILE = "rf-reference"
_SCOPE = "rf-fixed-five-v1"
_POLICY = "benchmarks/m6/execution-nextflow-raven-v2.yaml"
_NATIVE_RECEIPTS = {
    "RF_FIRST_COPY": "reference_first/bundle/reference_first_copy.json",
    "RF_COPY": "reference_copy/bundle/reference_copy.json",
    "RF_REFINE": "reference_refinement/bundle/reference_refinement.json",
}


def _object(path: Path) -> dict[str, object]:
    value = load_json_document(path)
    if not isinstance(value, dict):
        raise ValueError("reference native evidence must be a JSON object")
    return value


def _git(source: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(source), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    ).stdout.strip()


def _bind_run(run: Path) -> tuple[dict[str, object], dict[str, Path]]:
    source = run / "source"
    validate_module_origins(source)
    if Path(__file__).resolve() != (
        source / "tests/fixtures/ranking_four_arm_native.py"
    ).resolve(strict=True):
        raise ValueError("native verifier is not the original source")
    context = _context(run, _text(run / "state/owner-id"))
    identity = _identity(context)
    process = identity["process"]
    if not isinstance(process, Mapping) or _process_identity(process["pid"]) != process:
        raise ValueError("reference native verifier lost its original live controller")
    if context.profile != _PROFILE or _text(run / "state/rf-reference-scope") != _SCOPE:
        raise ValueError("reference native profile/scope differs")
    for name in (
        "m6-track",
        "m6-execution-purpose",
        "m6-operational-parent-run-id",
        "m6-operational-precheck-sha256",
        "m6-shared-cache-dir",
        "job-id",
    ):
        path = run / "state" / name
        if path.exists() or path.is_symlink():
            raise ValueError("reference native run carries foreign M6/Slurm state")
    manifest = _object(reference_owned_regular_file(run, run / "manifest.json"))
    if (
        _git(source, "rev-parse", "HEAD") != context.commit
        or _git(source, "status", "--porcelain", "--untracked-files=no")
        or _git(source / "external/nf-helper", "rev-parse", "HEAD")
        != manifest["nf_helper_commit"]
        or _git(
            source / "external/nf-helper",
            "status",
            "--porcelain",
            "--untracked-files=no",
        )
    ):
        raise ValueError("reference native source or nf-helper changed")
    paths = {
        "runner_manifest": run / "artifacts/m6-runner-inputs/runner_manifest.json",
        "database_manifest": Path(_text(run / "state/database-manifest")),
        "phenix_manifest": Path(_text(run / "state/phenix-manifest")),
        "software_lock": source / "pixi.lock",
        "execution_policy": source / _POLICY,
        "protocol": source / "benchmarks/m6/protocol.yaml",
        "controller_identity": run / "state/controller.json",
        "run_manifest": run / "manifest.json",
        "phenix_verification_log": run
        / "artifacts/qualification/rf-reference-phenix-verification.log",
    }
    state_names = {
        "runner_manifest": "m6-runner-manifest-sha256",
        "database_manifest": "database-manifest-sha256",
        "phenix_manifest": "phenix-manifest-sha256",
        "software_lock": "pixi-lock-sha256",
        "execution_policy": "execution-policy-sha256",
    }
    inputs = {}
    for role, path in paths.items():
        reference_owned_regular_file(context.root, path)
        digest = sha256_file(path)
        if role in state_names and digest != _text(run / "state" / state_names[role]):
            raise ValueError(f"reference native original input changed: {role}")
        inputs[role] = digest
    policy = load_m6_execution_policy(paths["execution_policy"])
    if (
        _text(run / "state/nextflow-profile") != "raven"
        or _text(run / "state/execution-policy-relative") != _POLICY
        or _text(run / "state/execution-policy-id") != policy.policy_id
        or policy.policy_id != "m6_nextflow_slurm_raven_v2"
        or manifest["pixi_lock_sha256"] != inputs["software_lock"]
    ):
        raise ValueError("reference native fixed resource/runtime binding differs")
    archive_sha = _text(run / "state/m6-runner-archive-sha256")
    if re.fullmatch(r"[0-9a-f]{64}", archive_sha) is None:
        raise ValueError("reference native runner archive binding is invalid")
    runner = M6RunnerInventorySpec.model_validate_json(
        paths["runner_manifest"].read_bytes()
    )
    if _text(run / "state/m6-runner-case-count") != "63" or str(
        runner.object_count
    ) != _text(run / "state/m6-runner-object-count"):
        raise ValueError("reference native complete runner inventory differs")
    phenix = validate_manifest_environment(paths["phenix_manifest"])
    return {
        "run_id": run.name,
        "profile": _PROFILE,
        "reference_scope": _SCOPE,
        "source_commit": context.commit,
        "nf_helper_commit": manifest["nf_helper_commit"],
        "controller_identity": identity,
        "input_sha256": inputs,
        "runner_archive_sha256": archive_sha,
        "phenix_runtime": phenix.model_dump(mode="json"),
    }, paths


def _context_paths(
    run: Path, value: object, *, external: set[Path], task_roots: tuple[Path, ...]
) -> None:
    if isinstance(value, Path):
        if value.resolve(strict=True) in external:
            return
        if not any(
            value.resolve(strict=True).is_relative_to(root) for root in task_roots
        ):
            raise ValueError(
                "reference scientific context names an untraced original task path"
            )
        _owned_path(run, value, directory=value.is_dir())
        if value.is_file():
            reference_owned_regular_file(run, value)
    elif isinstance(value, Mapping):
        for nested in value.values():
            _context_paths(run, nested, external=external, task_roots=task_roots)
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _context_paths(run, nested, external=external, task_roots=task_roots)


def _read_context[T: ContractModel](run: Path, path: Path, model: type[T]) -> T:
    return model.model_validate_json(
        reference_owned_regular_file(run, path).read_bytes()
    )


def _science(
    run: Path, paths: dict[str, Path], tasks: tuple[dict[str, str], ...]
) -> tuple[ReferenceRun, tuple[ReferenceIdentityContext, ...]]:
    result = (
        run / "artifacts/rf-reference-results/reference_run/bundle/reference_run.json"
    )
    root = result.parent
    plan_path = root / "plan/context.json"
    plan = _read_context(run, plan_path, ReferencePlanContext)
    runner_root = paths["runner_manifest"].parent
    if (
        plan.runner_root.resolve(strict=True) != runner_root.resolve(strict=True)
        or plan.database_manifest.resolve(strict=True)
        != paths["database_manifest"].resolve(strict=True)
        or plan.software_lock.resolve(strict=True)
        != paths["software_lock"].resolve(strict=True)
    ):
        raise ValueError("reference plan does not use the original staged inputs")
    external = {
        path.resolve(strict=True)
        for path in (
            runner_root,
            paths["database_manifest"],
            paths["software_lock"],
            paths["phenix_manifest"],
        )
    }
    task_roots = tuple(Path(row["workdir"]).resolve(strict=True) for row in tasks)
    _context_paths(run, plan.model_dump(), external=external, task_roots=task_roots)
    prepared_paths = []
    identity_paths = []
    identities = []
    for case_id in REFERENCE_CASE_IDS:
        prepared_path = root / "cases" / case_id / "prepared_context.json"
        prepared = _read_context(run, prepared_path, ReferencePreparedContext)
        if prepared.phenix_manifest.resolve(strict=True) != paths[
            "phenix_manifest"
        ].resolve(strict=True):
            raise ValueError("reference case changed its original Phenix manifest")
        _context_paths(
            run, prepared.model_dump(), external=external, task_roots=task_roots
        )
        prepared_paths.append(prepared_path)
        identity_path = prepared_path.with_name("identity_context.json")
        if identity_path.exists() or identity_path.is_symlink():
            identity = _read_context(run, identity_path, ReferenceIdentityContext)
            _context_paths(
                run, identity.model_dump(), external=external, task_roots=task_roots
            )
            identity_paths.append(identity_path)
            identities.append(identity)
    validated = validate_reference_run(
        reference_owned_regular_file(run, result),
        ReferenceRunInputs(plan_path, tuple(prepared_paths), tuple(identity_paths)),
    )
    return validated, tuple(identities)


def _native_commands(
    run: Path,
    tasks: tuple[dict[str, str], ...],
    identities: tuple[ReferenceIdentityContext, ...],
) -> list[dict[str, object]]:
    receipts: dict[Path, tuple[str, str]] = {}
    for identity in identities:
        finalists = identity.finalists
        case_id = finalists.review.prepared.case_id
        for process, paths in (
            ("RF_FIRST_COPY", finalists.review.first_copy_receipts),
            ("RF_COPY", finalists.copy_receipts),
            ("RF_REFINE", identity.refinement_receipts),
        ):
            for path in paths:
                original = path.resolve(strict=True)
                if original in receipts:
                    raise ValueError("reference native receipt is duplicated")
                receipts[original] = (process, case_id)
    observations: list[dict[str, object]] = []
    seen: set[Path] = set()
    for task in tasks:
        process = task["process"].rsplit(":", 1)[-1]
        if process not in _NATIVE_RECEIPTS:
            continue
        work = Path(task["workdir"])
        receipt_path = reference_owned_regular_file(
            run, work / _NATIVE_RECEIPTS[process]
        )
        receipt_key = receipt_path.resolve(strict=True)
        if receipt_key not in receipts or receipts[receipt_key][0] != process:
            raise ValueError(
                "reference native trace has an extra or foreign scientific task"
            )
        seen.add(receipt_key)
        case_id = receipts[receipt_key][1]
        root = receipt_path.parent
        expected: tuple[ReferenceNativeCommand, ...]
        if process == "RF_FIRST_COPY":
            first = ReferenceFirstCopyReceipt.model_validate_json(
                receipt_path.read_bytes()
            )
            tag = f"rf-first:{case_id}:{first.task.hypothesis.hypothesis_id}"
            threads = first.threads
            expected = command_record_expectations(
                root / "phaser_command.json", work_directory=work
            )
        elif process == "RF_COPY":
            copy = ReferencePreparedCopyReceipt.model_validate_json(
                receipt_path.read_bytes()
            )
            tag = (
                f"rf-copy:{case_id}:{copy.task.admission_prior}:"
                f"{copy.task.seed_solution_id}"
            )
            threads = copy.threads
            summary = _object(root / "additional_copy_series_summary.json")
            # The original already-complete summary deliberately omits paths;
            # the authenticated receipt, not missing data, proves zero attempts.
            result_paths = summary.get(
                "result_paths", [] if copy.native_attempt_count == 0 else None
            )
            if (
                not isinstance(result_paths, list)
                or len(result_paths) != copy.native_attempt_count
                or any(type(relative) is not str for relative in result_paths)
            ):
                raise ValueError("reference native copy attempt count differs")
            expected = tuple(
                command
                for relative in result_paths
                for command in command_record_expectations(
                    reference_owned_regular_file(run, root / "series" / relative).parent
                    / "phaser_command.json",
                    work_directory=work,
                )
            )
        else:
            refine = ReferenceRefinementReceipt.model_validate_json(
                receipt_path.read_bytes()
            )
            tag = (
                f"rf-refine:{case_id}:{refine.task.admission_prior}:"
                f"{refine.task.task.seed_solution_id}"
            )
            threads = refine.threads
            expected = command_record_expectations(
                root / "t12/t12_command.json", work_directory=work
            )
        if task["tag"] != tag or task["cpus"] != str(threads):
            raise ValueError(
                "reference native task tag or allocated CPU binding differs"
            )
        log = read_reference_native_task_log(
            work / ".command.err", work_directory=work, expected=expected
        )
        observations.append(
            {
                "process": task["process"],
                "tag": tag,
                "task_hash": task["hash"],
                "native_id": task["native_id"],
                "workdir": str(work),
                "receipt_sha256": sha256_file(receipt_path),
                "stderr_sha256": log.log_sha256,
                "other_stderr_lines": log.other_stderr_lines,
                "invocations": [
                    {
                        "arguments": list(row.command.arguments),
                        "working_directory": str(row.command.working_directory),
                        "exit_status": row.exit_status,
                        "start_line": row.start_line,
                        "finish_line": row.finish_line,
                    }
                    for row in log.invocations
                ],
            }
        )
    if seen != set(receipts):
        raise ValueError(
            "reference native trace omits an authenticated scientific receipt"
        )
    return sorted(observations, key=lambda row: (str(row["process"]), str(row["tag"])))


def _input_copies(
    run: Path, paths: dict[str, Path], *, phase: Literal["first", "resume"]
) -> dict[str, dict[str, str | int]]:
    root = run / "artifacts/qualification/rf-reference-inputs"
    if phase == "first":
        if root.exists() or root.is_symlink():
            raise ValueError("reference input copies must not already exist")
        root.mkdir()
    _owned_path(run, root, directory=True)
    if set(paths) != set(REFERENCE_INPUT_COPIES):
        raise ValueError("reference input-copy roles differ from the fixed interface")
    inventory = {}
    for role, filename in REFERENCE_INPUT_COPIES.items():
        original = reference_owned_regular_file(run.parent.parent, paths[role])
        payload = original.read_bytes()
        destination = root / filename
        if phase == "first":
            with destination.open("xb") as handle:
                handle.write(payload)
        reference_owned_regular_file(run, destination)
        if destination.read_bytes() != payload:
            raise ValueError("reference input copy differs from its unchanged original")
        inventory[destination.relative_to(run).as_posix()] = {
            "sha256": sha256_file(destination),
            "size_bytes": len(payload),
        }
    if {path.name for path in root.iterdir()} != set(REFERENCE_INPUT_COPIES.values()):
        raise ValueError("reference input copies contain a foreign file")
    return inventory


def _published_files(
    run: Path, result: ReferenceRun
) -> dict[str, dict[str, str | int]]:
    root = run / "artifacts/rf-reference-results/reference_run/bundle"
    paths = {
        "reference_run.json": sha256_file(root / "reference_run.json"),
        **result.output_sha256,
    }
    inventory = {}
    for relative, digest in paths.items():
        path = reference_owned_regular_file(run, root / relative)
        if sha256_file(path) != digest:
            raise ValueError("reference published bytes changed after validation")
        inventory[path.relative_to(run).as_posix()] = {
            "sha256": digest,
            "size_bytes": path.stat().st_size,
        }
    return inventory


def verify_native_reference(
    run: Path, *, phase: Literal["first", "resume"], first_sha256: str | None
) -> Path:
    """Revalidate original science/native bytes and write one fixed phase receipt."""

    qualification = run / "artifacts/qualification"
    output = qualification / f"rf-reference-{phase}-verification.json"
    if output.exists() or output.is_symlink():
        raise ValueError("reference native verification output must be absent")
    baseline = None
    if phase == "resume":
        first_path = reference_owned_regular_file(
            run, qualification / "rf-reference-first-verification.json"
        )
        if first_sha256 is None or sha256_file(first_path) != first_sha256:
            raise ValueError(
                "reference resume requires its externally frozen first receipt"
            )
        baseline = _object(first_path)
        if baseline.get("phase") != "first":
            raise ValueError("reference native baseline is not a first-pass receipt")
    elif first_sha256 is not None:
        raise ValueError("reference first pass cannot take a baseline")
    binding, paths = _bind_run(run)
    trace = qualification / f"rf-reference-{phase}-pipeline-info/trace.tsv"
    tasks = reference_trace_tasks(run, trace)
    staged_inputs = reference_staged_search_inputs(run, tasks)
    native_files = reference_native_file_inventory(run, tasks)
    result, identities = _science(run, paths, tasks)
    commands = _native_commands(run, tasks, identities)
    published_root = run / "artifacts/rf-reference-results/reference_run/bundle"
    discovery = verify_reference_discovery(
        run,
        paths,
        tasks,
        _read_context(run, published_root / "plan/context.json", ReferencePlanContext),
        tuple(
            _read_context(
                run,
                published_root / "cases" / case_id / "prepared_context.json",
                ReferencePreparedContext,
            )
            for case_id in REFERENCE_CASE_IDS
        ),
        identities,
    )
    input_copies = _input_copies(run, paths, phase=phase)
    published_files = _published_files(run, result)
    first_trace = qualification / "rf-reference-first-pipeline-info/trace.tsv"
    reference_owned_regular_file(run, first_trace)
    resources_path = qualification / f"rf-reference-{phase}-resource-evidence.json"
    if resources_path.exists() or resources_path.is_symlink():
        raise ValueError("reference resource evidence output must be absent")
    resources = collect_m6_resource_evidence(
        M6ResourceEvidenceRequest(
            policy=paths["execution_policy"],
            trace=first_trace,
            output=resources_path,
        )
    )
    if not resources.per_job_bounds_passed:
        raise ValueError("reference native children exceeded the fixed site policy")
    checkpoint_path = qualification / f"rf-reference-{phase}-child-outputs.json"
    checkpoint = collect_reference_child_outputs(
        ReferenceChildOutputRequest(
            result=run
            / "artifacts/rf-reference-results/reference_run/bundle/reference_run.json",
            trace=trace,
            output=checkpoint_path,
            baseline=qualification / "rf-reference-first-child-outputs.json"
            if baseline
            else None,
            expected_baseline_sha256=str(baseline["child_checkpoint_sha256"])
            if baseline
            else None,
        )
    )
    invariant = {
        **binding,
        "reference_run_id": result.reference_run_id,
        "reference_result_sha256": checkpoint.reference_result_sha256,
        "source_sha256": checkpoint.source_sha256,
        "first_trace_sha256": sha256_file(first_trace),
        "native_files": native_files,
        "staged_search_inputs": staged_inputs,
        "input_copies": input_copies,
        "published_files": published_files,
        "native_commands": commands,
        "discovery_provenance": discovery,
        "resource_evidence": resources.model_dump(mode="json"),
    }
    if baseline is not None and baseline["invariant"] != invariant:
        raise ValueError(
            "reference cached original inputs, science or native provenance changed"
        )
    if (
        _bind_run(run)[0] != binding
        or reference_staged_search_inputs(run, tasks) != staged_inputs
        or reference_native_file_inventory(run, tasks) != native_files
    ):
        raise ValueError(
            "reference original inputs or native files changed during verification"
        )
    record = {
        "schema_version": "1.0",
        "adapter_version": "rf-native-verification-v1",
        "phase": phase,
        "first_verification_sha256": first_sha256,
        "native_acceptance_claim": False,
        "benchmark_acceptance_claim": False,
        "human_approval_granted": False,
        "truth_compared": False,
        "invariant": invariant,
        "trace_sha256": sha256_file(trace),
        "child_checkpoint_sha256": sha256_file(checkpoint_path),
        "resource_evidence_sha256": sha256_file(resources_path),
    }
    record["verification_id"] = content_id("rfnative_", record)
    atomic_write_json(output, record)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--phase", choices=("first", "resume"), required=True)
    parser.add_argument("--first-verification-sha256")
    args = parser.parse_args()
    verify_native_reference(
        args.run_root, phase=args.phase, first_sha256=args.first_verification_sha256
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
