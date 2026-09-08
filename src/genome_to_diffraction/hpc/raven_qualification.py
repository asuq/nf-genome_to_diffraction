"""Fixed Raven qualification routes through the existing Nextflow workflows.

The private launch binds exact source/CI, a completed migration smoke, licensed
runtime and a regular-file input inventory. No arbitrary command or workflow is
accepted. Python validates and retains evidence; Nextflow schedules every
independent scientific task. A changed binding, incomplete smoke, escaped path,
failed replay or missing resource trace fails the controller. Native candidate
failure remains in its original typed record, never a scientific no-hit.

The input content ID and source/tool bindings are the launch identity; the
existing adapters still own scientific cache keys. Tests exercise fixed command
construction, stale authority, path confinement, resources and failed evidence
without claiming installed-runtime or Raven qualification.
"""

import csv
import json
import os
import re
import shutil
from pathlib import Path

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.execution.finding_closure import (
    PhaseIIIExactSourceCIEvidence,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.raven import (
    RavenQualificationLaunch,
)

_PARAMETERS = {
    "control-first-copy": (
        "control_bundle",
        "sequence_groups",
        "preflight",
        "mtz",
    ),
    "control-additional-copy": (
        "seeds",
        "review_validation",
        "review_package",
        "hypotheses",
        "sequence_groups",
        "preflight",
        "mtz",
    ),
    "control-refinement": ("finalists", "sequence_groups", "source_records"),
    "control-composition-attempts": (
        "attempt_inventory",
        "fixed_coordinate_root",
        "model_registry",
        "sequence_groups",
        "preflight",
        "mtz",
        "execution_identity",
    ),
    "control-reopening": ("known_control_inputs",),
    "m6-operational": ("runner_root", "database_manifest"),
    "m6-leakage": ("runner_root", "database_manifest"),
    "m6-comparison-initial": ("comparison_root",),
    "m6-comparison-continuation": ("comparison_root",),
    "unknown-single-component": (
        "catalogues",
        "crystals",
        "config",
        "database_manifest",
        "phase3_execution_identity",
        "phase3_reviewed_crystal_manifest",
        "phase3_owned_run_registry",
    ),
    "unknown-pass2": ("phase3_pass2_input_manifest",),
}
INPUT_DOCUMENT = "raven-qualification-inputs.json"
_SAFE_RELATIVE = re.compile(r"[A-Za-z0-9_. /-]+")
_DIRECTORIES = {
    "control_bundle",
    "review_package",
    "fixed_coordinate_root",
    "model_registry",
    "runner_root",
    "comparison_root",
    "phase3_owned_run_registry",
}
_KNOWN_CONTROLS = frozenset({"7L6G", "3U7Q", "9ECN"})


def _regular(path: Path) -> Path:
    if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
        raise ValueError(f"qualification file is absent or unsafe: {path}")
    return path


def confined(path: Path, root: Path) -> Path:
    """Require an existing owned path within the approved project namespace."""

    if (
        not path.is_absolute()
        or path.is_symlink()
        or not path.resolve(strict=True).is_relative_to(root.resolve(strict=True))
        or path.stat().st_uid != os.getuid()
        or any(p.is_symlink() for p in path.parents if p.is_relative_to(root))
    ):
        raise ValueError("Raven qualification path escapes the owned /ptmp project")
    return path


def input_identity(root: Path) -> str:
    """Hash the complete staged input tree, including its parameter document."""

    if root.is_symlink() or not root.is_dir():
        raise ValueError("Raven qualification input root is absent or unsafe")
    files = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Raven qualification inputs contain a symlink")
        if path.is_dir():
            continue
        _regular(path)
        size = path.stat().st_size
        total += size
        if len(files) >= 100000 or size > 4 * 1024**3 or total > 200 * 1024**3:
            raise ValueError("Raven qualification input inventory exceeds its bound")
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": size,
                "sha256": sha256_file(path),
            }
        )
    if not files or not (root / INPUT_DOCUMENT).is_file():
        raise ValueError("Raven qualification inputs lack their fixed document")
    return content_id("ravenqualificationinputs_", {"files": files})


def load_parameters(spec: RavenQualificationLaunch) -> dict[str, Path]:
    """Resolve only the parameters admitted by this fixed stage."""

    document = json.loads(_regular(spec.input_root / INPUT_DOCUMENT).read_text())
    allowed = {"schema_version", "source_commit", "parameters", "control_id"}
    if (
        not isinstance(document, dict)
        or set(document) != allowed
        or document["schema_version"] != "1.0"
        or document["source_commit"] != spec.source_commit
        or not isinstance(document["parameters"], dict)
        or set(document["parameters"]) != set(_PARAMETERS[spec.stage])
    ):
        raise ValueError("Raven qualification parameter contract differs")
    control = spec.stage.startswith("control-")
    if (control and document["control_id"] not in _KNOWN_CONTROLS) or (
        not control and document["control_id"] is not None
    ):
        raise ValueError("Raven known-control scope is absent or unexpected")
    parameters = {}
    for name, value in document["parameters"].items():
        if not isinstance(value, str) or _SAFE_RELATIVE.fullmatch(value) is None:
            raise ValueError("qualification parameter is not a safe relative path")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts or str(relative) != value:
            raise ValueError("qualification parameter escapes its input bundle")
        path = confined(spec.input_root / relative, spec.input_root)
        if (name in _DIRECTORIES and not path.is_dir()) or (
            name not in _DIRECTORIES and not path.is_file()
        ):
            raise ValueError(f"qualification parameter has the wrong type: {name}")
        parameters[name] = path
    if control and "preflight" in parameters:
        rows = [
            json.loads(line)
            for line in parameters["preflight"].read_text().splitlines()
            if line.strip()
        ]
        if len(rows) != 1 or rows[0].get("crystal_id") != document["control_id"]:
            raise ValueError("known-control preflight belongs to another crystal")
    return parameters


def _migration_ready(spec: RavenQualificationLaunch, root: Path) -> None:
    # Imported here to keep the shared controller independent of scientific
    # qualification and to preserve its active identification launch contract.
    from genome_to_diffraction.benchmarks.m6_execution import _hours, _memory_gb
    from genome_to_diffraction.hpc.raven_identification import RavenLaunch, _status

    migration = confined(spec.migration_run, root)
    paths = {
        "launch.json": spec.migration_launch_sha256,
        "state.json": spec.migration_state_sha256,
        "collected/assessment.json": spec.migration_assessment_sha256,
    }
    for name, expected in paths.items():
        if sha256_file(_regular(migration / name)) != expected:
            raise ValueError("Raven migration evidence changed")
    launch = RavenLaunch.model_validate_json((migration / "launch.json").read_text())
    if (
        migration.parent != root / "runs"
        or launch.run_id != migration.name
        or launch.run_mode != "smoke"
        or launch.account != spec.account
        or launch.phenix_manifest_sha256 != spec.phenix_manifest_sha256
        or _status(migration, launch).get("state") != "COMPLETED"
    ):
        raise ValueError("Raven migration lacks a completed bound smoke")
    assessment = json.loads((migration / "collected/assessment.json").read_text())
    selected = [
        row for row in assessment["cases"] if row["selected_for_this_run"] is True
    ]
    tasks = assessment["tasks"]
    status = _status(migration, launch)
    if (
        not selected
        or status.get("execution_case_count") != len(selected)
        or not tasks
        or any(
            row["execution_state"] not in {"completed_hit", "completed_no_hit"}
            for row in selected
        )
        or any(
            row["status"] != "COMPLETED"
            or re.fullmatch(r"[0-9]+", row["native_id"]) is None
            for row in tasks
        )
    ):
        raise ValueError("Raven migration smoke has incomplete native evidence")
    artifacts = {item["path"]: item for item in assessment["artifacts"]}
    if len(artifacts) != len(assessment["artifacts"]):
        raise ValueError("Raven smoke repeats a native artifact")
    for row in selected:
        case_id = row["case"]["case_id"]
        if re.fullmatch(r"identcase_[a-f0-9]{64}", case_id) is None:
            raise ValueError("Raven smoke native case ID is malformed")
        relative = f"mr/{case_id}/run.json"
        native_path = confined(migration / "results" / relative, migration)
        record = json.loads(_regular(native_path).read_text())
        task_rows = [
            task for task in tasks if task["tag"] == f"identification-mr:{case_id}"
        ]
        if (
            len(task_rows) != 1
            or record.get("case_id") != case_id
            or record.get("status") != row["execution_state"]
            or record.get("exit_code") != 0
            or sha256_file(native_path) != artifacts[relative]["sha256"]
        ):
            raise ValueError("Raven smoke native outcome differs from its assessment")
        task = task_rows[0]
        resources = record["resources"]
        if (
            resources["cpus"] != int(task["cpus"])
            or resources["memory_gb"] != _memory_gb(task["memory"])
            or resources["time_hours"] != _hours(task["time"])
            or not 0 < resources["time_hours"] <= 24
        ):
            raise ValueError("Raven smoke resolved allocation differs from its trace")


def cache_root(run: Path, spec: RavenQualificationLaunch) -> Path:
    """Reuse the completed operational cache only for its bound leakage child."""

    owner = spec.operational_parent_run or run
    return owner / "cache/qualification"


def validate_launch(
    run: Path, root: Path, spec: RavenQualificationLaunch
) -> dict[str, Path]:
    """Recheck source, CI, migration and every input before native dispatch."""

    from genome_to_diffraction.hpc.client import SubprocessGitRepository

    for path in (spec.source_root, spec.input_root, spec.phenix_manifest):
        confined(path, root)
    if spec.source_root != root / "sources" / spec.source_commit:
        raise ValueError("Raven qualification source is not its immutable snapshot")
    git = SubprocessGitRepository(spec.source_root)
    git.ensure_clean()
    if (
        git.resolve_commit("HEAD") != spec.source_commit
        or git.resolve_commit("HEAD^{tree}") != spec.source_tree
    ):
        raise ValueError("Raven qualification source tree changed")
    helper = SubprocessGitRepository(spec.source_root / "external/nf-helper")
    if helper.resolve_commit("HEAD") != spec.nf_helper_commit:
        raise ValueError("Raven qualification helper changed")
    helper.ensure_clean()
    if sha256_file(spec.source_root / "pixi.lock") != spec.pixi_lock_sha256:
        raise ValueError("Raven qualification lock changed")
    if input_identity(spec.input_root) != spec.input_id:
        raise ValueError("Raven qualification input identity changed")
    ci_path = _regular(spec.input_root / "exact-source-ci.json")
    ci = PhaseIIIExactSourceCIEvidence.model_validate_json(ci_path.read_text())
    if (
        ci.head_sha != spec.source_commit
        or sha256_file(ci_path) != spec.ci_evidence_sha256
    ):
        raise ValueError("Raven qualification requires successful exact-source CI")
    _migration_ready(spec, root)
    parameters = load_parameters(spec)
    if spec.runner_archive is not None:
        confined(spec.runner_archive, root)
        if sha256_file(_regular(spec.runner_archive)) != spec.runner_archive_sha256:
            raise ValueError("M6 runner archive changed")
    if spec.stage == "control-reopening":
        from genome_to_diffraction.hpc.raven_controls import (
            validate_known_control_reopening,
        )

        validate_known_control_reopening(
            parameters["known_control_inputs"],
            source_commit=spec.source_commit,
            phenix_manifest=spec.phenix_manifest,
        )
    if spec.stage == "m6-leakage":
        from genome_to_diffraction.hpc.raven_m6 import validate_operational_parent

        validate_operational_parent(root, spec)
    if spec.stage == "unknown-pass2":
        from genome_to_diffraction.hpc.unknown_pass2_inputs import (
            PASS2_INPUT_MANIFEST,
            validate_unknown_pass2_input_tree,
        )

        manifest = parameters["phase3_pass2_input_manifest"]
        if manifest.name != PASS2_INPUT_MANIFEST:
            raise ValueError("unknown pass 2 lacks its canonical RG7 authority")
        payload = json.loads(manifest.read_text())
        validate_unknown_pass2_input_tree(
            manifest.parent,
            expected_input_id=payload["input_id"],
            expected_source_commit=spec.source_commit,
            expected_source_tree=spec.source_tree,
            expected_parent_run_id=str(spec.parent_run_id),
            expected_finding_ledger_sha256=sha256_file(
                spec.source_root / "docs/phase-iii-finding-ledger.md"
            ),
        )
    if spec.stage == "unknown-single-component":
        from genome_to_diffraction.hpc.unknown_single_inputs import (
            validate_unknown_single_component_handoff,
        )
        from genome_to_diffraction.schemas.v2.execution import PhaseIIIExecutionIdentity

        assert spec.screen_parent_run is not None
        assert spec.continuation_handoff_root is not None
        parent = confined(spec.screen_parent_run, root)
        handoff = confined(spec.continuation_handoff_root, spec.input_root)
        if parent.name != spec.parent_run_id or handoff.name != spec.run_id:
            raise ValueError("single-component handoff belongs to another run")
        validate_unknown_single_component_handoff(
            parent_run_root=parent,
            child_run_root=handoff,
        )
        frozen = handoff / "artifacts/unknown-single-component/phase3_crystals.json"
        identity = PhaseIIIExecutionIdentity.model_validate_json(
            parameters["phase3_execution_identity"].read_text()
        )
        if (
            sha256_file(parameters["crystals"]) != sha256_file(frozen)
            or identity.source_commit != spec.source_commit
            or identity.source_tree != spec.source_tree
        ):
            raise ValueError("single-component diffraction/source authority changed")
    return parameters


def nextflow_command(
    run: Path, spec: RavenQualificationLaunch, *, resume: bool = False
) -> list[str]:
    """Build one fixed workflow invocation; never accept extra CLI arguments."""

    parameters = load_parameters(spec)
    stage = spec.stage
    entrypoint = (
        "m6_validation.nf"
        if stage in {"m6-operational", "m6-leakage"}
        else "phase3_application.nf"
        if stage.startswith("unknown-")
        else "qualification.nf"
    )
    command = [
        str(spec.source_root / ".pixi/envs/hpc/bin/nextflow"),
        "-log",
        str(run / f"logs/nextflow-{'resume' if resume else 'first'}.log"),
        "-c",
        str(run / "raven-account.config"),
        "run",
        str(spec.source_root / entrypoint),
        "-profile",
        "raven",
        "-work-dir",
        str(cache_root(run, spec) / "work"),
    ]
    if resume or stage == "m6-leakage":
        command.append("-resume")
    if entrypoint == "m6_validation.nf":
        command.extend(
            (
                "--track",
                stage.removeprefix("m6-"),
                "--protocol",
                str(spec.source_root / "benchmarks/m6/protocol.yaml"),
                "--execution_policy",
                str(
                    spec.source_root / "benchmarks/m6/execution-nextflow-raven-v1.yaml"
                ),
            )
        )
    elif entrypoint == "phase3_application.nf":
        command.extend(
            (
                "--phase3_operation",
                "composition_beam"
                if stage == "unknown-pass2"
                else "reviewed_single_component",
                "--phase3_owned_parent_run_id",
                str(spec.parent_run_id),
            )
        )
        if stage == "unknown-single-component":
            command.extend(
                (
                    "--phase3_owned_sequence_parent_run_id",
                    str(spec.sequence_parent_run_id),
                    "--review_mode",
                    "require",
                    "--profile_mode",
                    "full",
                )
            )
    else:
        qualification = {
            "control-first-copy": "first_copy_controls",
            "control-additional-copy": "additional_copy",
            "control-refinement": "refine_finalists",
            "control-composition-attempts": "composition_attempts",
            "control-reopening": "known_control_reopening",
            "m6-comparison-initial": "m6_comparison_initial",
            "m6-comparison-continuation": "m6_comparison_continuation",
        }[stage]
        command.extend(("--qualification_stage", qualification))
        if stage == "control-reopening":
            command.extend(("--source_commit", spec.source_commit))
    for name, path in sorted(parameters.items()):
        command.extend((f"--{name}", str(path)))
    if stage != "unknown-pass2":
        command.extend(
            (
                "--phenix_manifest",
                str(run / "qualification/phenix-install-manifest.json"),
            )
        )
    if stage.startswith("m6-"):
        command.extend(("--software_lock", str(spec.source_root / "pixi.lock")))
    command.extend(
        (
            "--outdir",
            str(run / "results"),
            "--cache_root",
            str(cache_root(run, spec)),
        )
    )
    return command


def retain_evidence(run: Path, spec: RavenQualificationLaunch) -> None:
    """Keep every terminal task's diagnostics and index all published assets."""

    from genome_to_diffraction.benchmarks.m6_execution import _hours, _memory_gb
    from genome_to_diffraction.benchmarks.public_control import PublicControlError

    destination = run / "collected"
    destination.mkdir(exist_ok=True)
    index = []
    total = 0

    def retain(source: Path, relative: Path) -> None:
        nonlocal total
        _regular(source)
        size = source.stat().st_size
        copied = source.suffix.lower() != ".mtz"
        index.append(
            {
                "path": relative.as_posix(),
                "sha256": sha256_file(source),
                "size_bytes": size,
                "collected": copied,
            }
        )
        if len(index) > 30000:
            raise ValueError("Raven qualification collection exceeds its file bound")
        if copied:
            total += size
            if size > 128 * 1024**2 or total > 10 * 1024**3:
                raise ValueError(
                    "Raven qualification collection exceeds its byte bound"
                )
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    for path in sorted((run / "results").rglob("*")):
        if path.is_symlink():
            raise ValueError("Raven qualification result contains a symlink")
        if path.is_file():
            retain(path, Path("results") / path.relative_to(run / "results"))
    # Preserve the first trace as well as the resume, which otherwise replaces it.
    traces = sorted((run / "qualification").glob("*-pipeline-info/trace.tsv"))
    final_trace = run / "results/pipeline_info/trace.tsv"
    if final_trace.is_file() and not traces:
        traces = [final_trace]
    resources = []
    problems = []
    seen_tasks = set()
    for trace in traces:
        with trace.open(newline="") as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                task_key = (
                    row["workdir"]
                    if row["workdir"] not in {"", "-"}
                    else row["task_id"],
                    row["attempt"],
                )
                if task_key in seen_tasks:
                    continue
                seen_tasks.add(task_key)
                resources.append(dict(row))
                task_id = row["task_id"]
                if re.fullmatch(r"[0-9]+", task_id) is None:
                    raise ValueError("Raven task ID is malformed")
                attempt = row["attempt"]
                if attempt not in {"1", "2"}:
                    raise ValueError("Raven task attempt exceeds the single retry")
                try:
                    hours = _hours(row["time"])
                    cpus = int(row["cpus"])
                    memory = _memory_gb(row["memory"])
                    if (
                        not 0 < hours <= 24
                        or not 0 < cpus <= 72
                        or not 0 < memory <= 2048
                    ):
                        raise ValueError("resolved allocation exceeds Raven limits")
                except (ValueError, PublicControlError) as error:
                    problems.append({"task_id": task_id, "reason": str(error)})
                work_path = Path(row["workdir"])
                if row["workdir"] in {"", "-"} or not work_path.exists():
                    problems.append(
                        {
                            "task_id": task_id,
                            "reason": "owned work directory unavailable",
                        }
                    )
                    continue
                work = confined(work_path, cache_root(run, spec) / "work")
                task_directory = Path("tasks") / f"{task_id}-attempt-{attempt}"
                for name in (
                    ".command.sh",
                    ".command.run",
                    ".command.log",
                    ".command.err",
                    ".exitcode",
                ):
                    source = work / name
                    if source.is_file() and not source.is_symlink():
                        retain(source, task_directory / name)
                if row["status"] not in {"COMPLETED", "CACHED"}:
                    for path in sorted(work.rglob("*")):
                        relative = path.relative_to(work)
                        if (
                            path.is_symlink()
                            or not path.is_file()
                            or relative.parts[0].startswith(".")
                            or any(
                                p.is_symlink()
                                for p in path.parents
                                if p.is_relative_to(work)
                            )
                        ):
                            continue
                        retain(path, task_directory / "native" / relative)
    atomic_write_json(
        destination / "resource-evidence.json",
        {
            "schema_version": "1.0",
            "run_id": spec.run_id,
            "stage": spec.stage,
            "source_commit": spec.source_commit,
            "input_id": spec.input_id,
            "controller_kind": "login_process",
            "task_limit_hours": 24,
            "site_submission_guard": 250,
            "tasks": resources,
            "all_resolved_allocations_verified": bool(resources) and not problems,
            "incomplete_evidence": problems,
        },
    )
    atomic_write_json(
        destination / "artifact-index.json",
        {
            "schema_version": "1.0",
            "run_id": spec.run_id,
            "files": index,
            "mtz_policy": "retained_on_Raven_with_checksum",
        },
    )
    if not resources or problems:
        raise ValueError("Raven qualification has incomplete resolved task evidence")
