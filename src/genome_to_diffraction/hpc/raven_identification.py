"""Owned Raven login controller for the existing identification Nextflow graph.

Only orchestration runs on the login node. Independent preparations and MR remain
Slurm tasks. All managed files are confined to the user's /ptmp project root.
"""

import argparse
import fcntl
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import traceback
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.client import SubprocessGitRepository
from genome_to_diffraction.hpc.identification_inputs import (
    execution_cases,
    validate_bound_input_root,
)
from genome_to_diffraction.hpc.identification_run import summarise, timestamp
from genome_to_diffraction.hpc.raven_qualification import (
    QUALIFICATION_RUN_PATTERN,
    RavenQualificationLaunch,
    retain_evidence,
    validate_launch,
)
from genome_to_diffraction.hpc.raven_qualification import (
    cache_root as qualification_cache_root,
)
from genome_to_diffraction.hpc.raven_qualification import (
    nextflow_command as qualification_command,
)

IDENTIFICATION_RUN_PATTERN = (
    r"gtd-identification-screen-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}-[a-f0-9]{8}"
)
RUN_PATTERN = f"(?:{IDENTIFICATION_RUN_PATTERN}|{QUALIFICATION_RUN_PATTERN})"
MAX_COLLECT_BYTES = 12 * 1024**3


class RavenLaunch(BaseModel):
    """Exact source, input and licensed-runtime authority for one Raven run."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    run_id: str = Field(pattern=f"^{IDENTIFICATION_RUN_PATTERN}$")
    owner_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    site_id: Literal["raven"]
    account: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    source_root: Path
    input_root: Path
    input_id: str = Field(pattern=r"^identificationinputs_[a-f0-9]{64}$")
    phenix_manifest: Path
    phenix_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mtz_root: Path
    run_mode: Literal["smoke", "screen"]


type RavenLaunchSpec = RavenLaunch | RavenQualificationLaunch


def parse_launch(payload: str | bytes) -> RavenLaunchSpec:
    """Preserve active identification records and admit only fixed qualification."""

    document = json.loads(payload)
    if not isinstance(document, dict):
        raise ValueError("Raven launch must be an object")
    if document.get("schema_version") == "1.0":
        return RavenLaunch.model_validate(document)
    return RavenQualificationLaunch.model_validate(document)


def launch_profile(spec: RavenLaunchSpec) -> str:
    """Return the exact operation carried by the authenticated launch."""

    return (
        spec.stage
        if isinstance(spec, RavenQualificationLaunch)
        else "identification-screen"
    )


def _owned_json(path: Path) -> dict:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_uid != os.getuid()
        or path.stat().st_size > 65536
    ):
        raise ValueError(f"absent, unsafe or oversized controller record: {path}")
    result = json.loads(path.read_text())
    if not isinstance(result, dict):
        raise ValueError("controller record must be an object")
    return result


def _load(run: Path, owner: str) -> tuple[Path, RavenLaunchSpec]:
    host = socket.gethostname().split(".")[0]
    if host not in {
        f"raven{i:02d}{suffix}" for i in range(1, 5) for suffix in ("", "i")
    }:
        raise ValueError("Raven orchestration requires an explicit Raven login node")
    root = Path("/ptmp") / os.environ["USER"] / "nf-genome_to_diffraction"
    if (
        run.parent != root / "runs"
        or re.fullmatch(RUN_PATTERN, run.name) is None
        or run.is_symlink()
        or not run.is_dir()
        or run.stat().st_uid != os.getuid()
    ):
        raise ValueError("run is outside the owned /ptmp run namespace")
    spec = parse_launch(json.dumps(_owned_json(run / "launch.json")))
    if spec.owner_id != owner or spec.run_id != run.name:
        raise ValueError("Raven run ownership differs")
    if spec.source_commit[:12] != run.name.split("-")[-2]:
        raise ValueError("run name and source commit differ")
    for path in (
        spec.source_root,
        spec.input_root,
        spec.phenix_manifest,
        *((spec.mtz_root,) if isinstance(spec, RavenLaunch) else (spec.migration_run,)),
    ):
        if not path.is_absolute() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Raven source/input/runtime path escapes /ptmp project")
    return root, spec


def _process_identity(pid: int) -> dict | None:
    proc = Path("/proc") / str(pid)
    try:
        fields = (proc / "stat").read_text().rsplit(") ", 1)[1].split()
        if proc.stat().st_uid != os.getuid() or fields[0] == "Z":
            return None
        return {
            "pid": pid,
            "start_ticks": fields[19],
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        }
    except FileNotFoundError:
        return None


def _status(run: Path, spec: RavenLaunchSpec) -> dict:
    record = _owned_json(run / "controller.json")
    if record.get("owner_id") != spec.owner_id or record.get("run_id") != spec.run_id:
        raise ValueError("controller ownership differs")
    state_path = run / "state.json"
    state = _owned_json(state_path) if state_path.exists() else {"state": "STARTING"}
    if state_path.exists():
        for key, expected in {
            "run_id": spec.run_id,
            "owner_id": spec.owner_id,
            "source_commit": spec.source_commit,
            "input_id": spec.input_id,
        }.items():
            if state.get(key) != expected:
                raise ValueError(
                    "Raven controller state belongs to another source/input/owner"
                )
    if state.get("state") not in {
        "STARTING",
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }:
        raise ValueError("unknown Raven controller state")
    if (
        state.get("state") not in {"COMPLETED", "FAILED", "CANCELLED"}
        and _process_identity(record["process"]["pid"]) != record["process"]
    ):
        state = {
            "state": "FAILED",
            "reason": "controller exited without terminal evidence",
        }
    return {
        "run_id": spec.run_id,
        "owner_id": spec.owner_id,
        "site_id": "raven",
        "profile": launch_profile(spec),
        "controller_kind": "login_process",
        "controller_pid": record["process"]["pid"],
        "source_commit": spec.source_commit,
        "input_id": spec.input_id,
        "terminal": state["state"] in {"COMPLETED", "FAILED", "CANCELLED"},
        **state,
    }


def _start(run: Path, spec: RavenLaunchSpec) -> dict:
    if (run / "start.lock").is_symlink():
        raise ValueError("Raven start lock is unsafe")
    with (run / "start.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (run / "controller.json").exists() or (run / "state.json").exists():
            raise ValueError("this Raven run has already been started")
        with (run / "controller.log").open("xb") as log:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "genome_to_diffraction.hpc.raven_identification",
                    "run",
                    "--run-dir",
                    str(run),
                    "--owner",
                    spec.owner_id,
                ],
                cwd=run,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        identity = _process_identity(child.pid)
        if identity is None:
            raise RuntimeError(
                "Raven controller exited during launch; inspect its retained log"
            )
        atomic_write_json(
            run / "controller.json",
            {
                "run_id": spec.run_id,
                "owner_id": spec.owner_id,
                "process": identity,
                "started_at": timestamp(),
            },
        )
    return _status(run, spec)


def nextflow_command(run: Path, spec: RavenLaunch) -> list[str]:
    """Use the shared graph with a run-owned work directory and Raven admission."""

    return [
        str(spec.source_root / ".pixi/envs/hpc/bin/nextflow"),
        "-log",
        str(run / "logs/nextflow.log"),
        "-c",
        str(run / "raven-account.config"),
        "run",
        str(spec.source_root / "qualification.nf"),
        "-profile",
        "raven",
        "-work-dir",
        str(run / "cache/identification/work"),
        "--qualification_stage",
        "identification_screen",
        "--identification_inputs",
        str(spec.input_root),
        "--identification_input_id",
        spec.input_id,
        "--identification_cases",
        str(run / "selected/execution_cases.json"),
        "--phenix_manifest",
        str(run / "qualification/phenix-install-manifest.json"),
        "--outdir",
        str(run / "results"),
        "--cache_root",
        str(run / "cache/identification"),
    ]


def _run(run: Path, root: Path, spec: RavenLaunchSpec) -> int:
    state = {
        "state": "RUNNING",
        "started_at": timestamp(),
        "identity_accepted": False,
        "run_id": spec.run_id,
        "owner_id": spec.owner_id,
        "source_commit": spec.source_commit,
        "input_id": spec.input_id,
    }
    atomic_write_json(run / "state.json", state)
    child = None
    cancelled = False

    def stop(signum, frame):
        nonlocal cancelled
        cancelled = True
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGINT)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    result_code = 1
    try:
        git = SubprocessGitRepository(spec.source_root)
        if git.resolve_commit("HEAD") != spec.source_commit:
            raise ValueError("Raven source checkout changed")
        git.ensure_clean()
        if sha256_file(spec.phenix_manifest) != spec.phenix_manifest_sha256:
            raise ValueError("Raven Phenix binding changed")
        for name in (
            "logs",
            "qualification",
            "selected",
            "results",
            "execution",
            "cache",
            "tmp",
        ):
            (run / name).mkdir(exist_ok=True)
        bound_manifest = run / "qualification/phenix-install-manifest.json"
        shutil.copyfile(spec.phenix_manifest, bound_manifest)
        if sha256_file(bound_manifest) != spec.phenix_manifest_sha256:
            raise ValueError("Raven Phenix manifest changed during snapshot")
        environment = os.environ.copy()
        binary = spec.source_root / ".pixi/envs/hpc/bin"
        environment.update(
            {
                "PATH": f"{binary}:{environment.get('PATH', os.defpath)}",
                "JAVA_CMD": str(spec.source_root / ".pixi/envs/hpc/lib/jvm/bin/java"),
                "NXF_HOME": str(run / "cache/nextflow-home"),
                "NXF_TEMP": str(run / "tmp"),
                "NXF_OPTS": f"-Xms256m -Xmx4g -Djava.io.tmpdir={run / 'tmp'}",
                "NXF_APPTAINER_CACHEDIR": str(root / "cache/apptainer"),
                "APPTAINER_CACHEDIR": str(root / "cache/apptainer"),
                "APPTAINER_TMPDIR": str(run / "tmp"),
                "TMPDIR": str(run / "tmp"),
                "XDG_CACHE_HOME": str(root / "cache"),
                "MPLCONFIGDIR": str(root / "cache/matplotlib"),
                "XDG_CONFIG_HOME": str(root / "cache/config"),
                "CONDA_REGISTER_ENVS": "false",
                "CONDA_PKGS_DIRS": str(root / "cache/conda"),
                "PIXI_CACHE_DIR": str(root / "cache/pixi"),
                "RATTLER_CACHE_DIR": str(root / "cache/rattler"),
                "UV_CACHE_DIR": str(root / "cache/uv"),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        if isinstance(spec, RavenQualificationLaunch):
            validate_launch(run, root, spec)
        subprocess.run(
            [
                str(binary / "genome-to-diffraction"),
                "--no-progress",
                "phenix",
                "verify",
                "--manifest",
                str(bound_manifest),
                "--no-command-timeout",
                "--verification-log",
                str(run / "qualification/phenix-verification.log"),
            ],
            cwd=run,
            env=environment,
            check=True,
        )
        if isinstance(spec, RavenQualificationLaunch):
            environment["NXF_CACHE_DIR"] = str(
                qualification_cache_root(run, spec) / "nextflow"
            )
            (run / "raven-account.config").write_text(
                f"executor.account = '{spec.account}'\n"
            )
            commands = {
                "argv": qualification_command(run, spec),
                "resume_argv": qualification_command(run, spec, resume=True),
                "environment": {
                    key: environment[key]
                    for key in (
                        "NXF_HOME",
                        "NXF_CACHE_DIR",
                        "NXF_TEMP",
                        "NXF_APPTAINER_CACHEDIR",
                        "TMPDIR",
                    )
                },
            }
            atomic_write_json(run / "nextflow-command.json", commands)
            # Two explicit qualification phases of one graph. Independent
            # scientific work remains channel items scheduled by Nextflow.
            for phase in ("first", "resume"):
                if cancelled:
                    raise RuntimeError("controller cancelled before Nextflow launch")
                if phase == "resume":
                    validate_launch(run, root, spec)
                command = qualification_command(run, spec, resume=phase == "resume")
                child = subprocess.Popen(
                    command, cwd=run / "execution", env=environment
                )
                state.update(phase=phase, nextflow_process=_process_identity(child.pid))
                atomic_write_json(run / "state.json", state)
                result_code = child.wait()
                pipeline_info = run / "results/pipeline_info"
                if pipeline_info.is_dir():
                    trace_label = (
                        f"m6-{phase}"
                        if spec.stage in {"m6-operational", "m6-leakage"}
                        else phase
                    )
                    shutil.copytree(
                        pipeline_info,
                        run / f"qualification/{trace_label}-pipeline-info",
                    )
                if result_code != 0:
                    break
                if spec.stage in {"m6-operational", "m6-leakage"}:
                    from genome_to_diffraction.hpc.raven_m6 import finish_phase

                    finish_phase(run, spec, phase=phase)
        else:
            plan = validate_bound_input_root(
                spec.input_root,
                expected_input_id=spec.input_id,
                source_commit=spec.source_commit,
                allowed_mtz_root=spec.mtz_root,
            )
            if plan.run_mode != spec.run_mode:
                raise ValueError("Raven execution mode differs from its input plan")
            selected = execution_cases(plan)
            atomic_write_json(
                run / "selected/execution_cases.json",
                [c.model_dump(mode="json") for c in selected],
            )
            state.update(execution_case_count=len(selected), run_mode=plan.run_mode)
            atomic_write_json(run / "state.json", state)
            (run / "raven-account.config").write_text(
                f"executor.account = '{spec.account}'\n"
            )
            command = nextflow_command(run, spec)
            atomic_write_json(
                run / "nextflow-command.json",
                {
                    "argv": command,
                    "environment": {
                        k: environment[k]
                        for k in (
                            "NXF_HOME",
                            "NXF_TEMP",
                            "NXF_APPTAINER_CACHEDIR",
                            "TMPDIR",
                        )
                    },
                },
            )
            if cancelled:
                raise RuntimeError("controller cancelled before Nextflow launch")
            child = subprocess.Popen(command, cwd=run / "execution", env=environment)
            state["nextflow_process"] = _process_identity(child.pid)
            atomic_write_json(run / "state.json", state)
            result_code = child.wait()
            summarise(
                spec.input_root,
                run / "results",
                run / "cache/identification/work",
                run / "collected",
            )
    except Exception as error:
        traceback.print_exc()
        state["reason"] = str(error)
        result_code = 1
    finally:
        if isinstance(spec, RavenQualificationLaunch):
            try:
                retain_evidence(run, spec)
            except (OSError, ValueError, KeyError) as error:
                traceback.print_exc()
                state["retention_error"] = str(error)
                result_code = 1
        state.update(
            state="CANCELLED"
            if cancelled
            else ("COMPLETED" if result_code == 0 else "FAILED"),
            completed_at=timestamp(),
            exit_code=result_code,
        )
        atomic_write_json(run / "state.json", state)
    return result_code


def _collect(run: Path, spec: RavenLaunchSpec) -> None:
    if not _status(run, spec)["terminal"]:
        raise ValueError("collect requires a terminal Raven controller")
    files = [
        run / name
        for name in (
            "launch.json",
            "controller.json",
            "state.json",
            "controller.log",
            "nextflow-command.json",
            "raven-account.config",
        )
    ]
    for directory in ("collected", "logs", "qualification"):
        files.extend(p for p in (run / directory).rglob("*") if p.is_file())
    files = sorted({p for p in files if p.exists()})
    if len(files) > 30000 or any(
        p.is_symlink()
        or not p.resolve().is_relative_to(run.resolve())
        or p.stat().st_uid != os.getuid()
        or p.stat().st_size > 128 * 1024**2
        for p in files
    ):
        raise ValueError("Raven collection contains unsafe or oversized files")
    if sum(p.stat().st_size for p in files) > MAX_COLLECT_BYTES:
        raise ValueError("Raven collection exceeds its bound")
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as archive:
        for path in files:
            archive.add(path, arcname=str(path.relative_to(run)), recursive=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=("start", "run", "status", "logs", "collect", "cancel")
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--tail", type=int, default=200)
    args = parser.parse_args()
    root, spec = _load(args.run_dir, args.owner)
    if args.operation == "run":
        return _run(args.run_dir, root, spec)
    if args.operation == "start":
        result = _start(args.run_dir, spec)
    elif args.operation == "status":
        result = _status(args.run_dir, spec)
    elif args.operation == "logs":
        if not 1 <= args.tail <= 2000:
            raise ValueError("tail must be within 1..2000")
        path = args.run_dir / "controller.log"
        if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
            raise ValueError("Raven controller log is absent or unsafe")
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - 2 * 1024**2))
            log = b"\n".join(handle.read().splitlines()[-args.tail :]).decode(
                errors="replace"
            )
        result = {
            "run_id": spec.run_id,
            "site_id": "raven",
            "profile": launch_profile(spec),
            "owner_id": spec.owner_id,
            "source_commit": spec.source_commit,
            "input_id": spec.input_id,
            "log": log,
        }
    elif args.operation == "collect":
        _collect(args.run_dir, spec)
        return 0
    else:
        result = _status(args.run_dir, spec)
        if not result["terminal"]:
            pid = result["controller_pid"]
            if sys.platform == "linux":
                descriptor = os.pidfd_open(pid)
                try:
                    recorded = _owned_json(args.run_dir / "controller.json")["process"]
                    if _process_identity(pid) != recorded:
                        raise ValueError(
                            "controller process identity changed before cancellation"
                        )
                    signal.pidfd_send_signal(descriptor, signal.SIGTERM)
                finally:
                    os.close(descriptor)
            else:
                raise RuntimeError("Raven cancellation requires Linux pidfd support")
            result["cancel_requested"] = True
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
