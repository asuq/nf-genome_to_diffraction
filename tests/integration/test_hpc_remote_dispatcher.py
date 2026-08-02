"""Exercise the fixed remote scripts with real Git and fake Slurm commands."""

import base64
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tarfile
from collections.abc import Iterator
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
RUN_ID = "gtd-smoke-20260802T120000Z-0123456789ab-01234567"
SECOND_RUN_ID = "gtd-smoke-20260802T120001Z-0123456789ab-01234568"
P0_RUN_ID = "gtd-p0-20260802T120000Z-0123456789ab-01234567"
OWNER_ID = "1" * 32


@pytest.fixture(autouse=True)
def _restore_test_tree_permissions(tmp_path: Path) -> Iterator[None]:
    """Make immutable fake checkouts removable after each integration test."""

    yield
    for directory, subdirectories, files in os.walk(tmp_path):
        directory_path = Path(directory)
        if not directory_path.is_symlink():
            directory_path.chmod(0o700)
        for name in (*subdirectories, *files):
            path = directory_path / name
            if not path.is_symlink():
                path.chmod(0o700)


def _run(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
    success: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
    )
    if success and result.returncode != 0:
        pytest.fail(
            f"command failed ({result.returncode}): {command}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
    if not success and result.returncode == 0:
        pytest.fail(f"command unexpectedly succeeded: {command}")
    return result


def _git(repository: Path, *arguments: str) -> str:
    return _run(["git", *arguments], cwd=repository).stdout.decode().strip()


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _decode_protocol(payload: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in payload.splitlines():
        key, encoded = line.split(b"\t", maxsplit=1)
        result[key.decode()] = base64.b64decode(encoded).decode()
    return result


def _prepare_git_repositories(root: Path) -> tuple[Path, str]:
    helper = root / "helper"
    helper.mkdir()
    _git(helper, "init", "-q")
    _git(helper, "config", "user.name", "Test")
    _git(helper, "config", "user.email", "test@example.invalid")
    (helper / "README.md").write_text("helper\n", encoding="utf-8")
    _git(helper, "add", "README.md")
    _git(helper, "commit", "-q", "-m", "helper")

    source = root / "source-origin"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "branch", "-M", "main")
    _git(source, "config", "user.name", "Test")
    _git(source, "config", "user.email", "test@example.invalid")
    (source / "pixi.lock").write_text("locked test environment\n", encoding="utf-8")
    bootstrap = source / "bootstrap"
    bootstrap.mkdir()
    for name in ("nf-gtd-hpc-remote", "nf-gtd-hpc-smoke-job"):
        shutil.copy2(REPOSITORY / "bootstrap" / name, bootstrap / name)
        (bootstrap / name).chmod(0o755)
    _git(source, "add", "pixi.lock", "bootstrap")
    _git(
        source,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(helper),
        "external/nf-helper",
    )
    _git(source, "commit", "-q", "-m", "source")
    return source, _git(source, "rev-parse", "HEAD")


def _prepare_remote_layout(tmp_path: Path) -> tuple[Path, Path, dict[str, str], str]:
    root = tmp_path / "remote-root"
    tooling = root / "_tooling"
    mirror_parent = root / "_cache" / "git"
    tooling.mkdir(parents=True)
    mirror_parent.mkdir(parents=True)
    (root / "_locks").mkdir()
    (root / "runs").mkdir()

    dispatcher = tooling / "nf-gtd-hpc-remote"
    smoke_job = tooling / "nf-gtd-hpc-smoke-job"
    shutil.copy2(REPOSITORY / "bootstrap" / dispatcher.name, dispatcher)
    shutil.copy2(REPOSITORY / "bootstrap" / smoke_job.name, smoke_job)
    dispatcher.chmod(0o755)
    smoke_job.chmod(0o755)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    pixi = fake_bin / "pixi"
    _write_executable(
        pixi,
        "#!/usr/bin/env bash\n"
        'case "${1-}" in\n'
        "  --version) echo 'pixi 0.74.0' ;;\n"
        '  install) [[ "${FAKE_PIXI_INSTALL_FAIL:-0}" != 1 ]] || exit 4 ;;\n'
        "  run)\n"
        '    [[ "${FAKE_PIXI_RUN_FAIL:-0}" != 1 ]] || exit 5\n'
        '    if [[ "${FAKE_PIXI_READONLY_TMP:-0}" == 1 ]]; then\n'
        '      mkdir -p "$TMPDIR/readonly/nested"\n'
        '      touch "$TMPDIR/readonly/nested/fixture"\n'
        '      chmod -R a-w "$TMPDIR/readonly"\n'
        "    fi\n"
        '    if [[ "${FAKE_PIXI_TERM_PARENT:-0}" == 1 ]]; then\n'
        '      kill -TERM "$PPID"\n'
        "      sleep 0.1\n"
        "    fi\n"
        "    ;;\n"
        "esac\n"
        "exit 0\n",
    )
    _write_executable(
        fake_bin / "sbatch",
        "#!/usr/bin/env bash\n"
        '[[ "${FAKE_SBATCH_REJECT:-0}" != 1 ]] || exit 1\n'
        f'printf "%s\\n" "$@" > '
        f"{shlex.quote(str(tmp_path / 'sbatch-args'))}\n"
        "echo 123\n",
    )
    _write_executable(
        fake_bin / "squeue",
        "#!/usr/bin/env bash\n"
        '[[ "${FAKE_SQUEUE_FAIL:-0}" != 1 ]] || exit 1\n'
        '[[ -z "${FAKE_SQUEUE_STATE:-}" ]] || echo "$FAKE_SQUEUE_STATE"\n',
    )
    _write_executable(fake_bin / "flock", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        fake_bin / "sacct",
        "#!/usr/bin/env bash\n"
        '[[ "${FAKE_SACCT_FAIL:-0}" != 1 ]] || exit 1\n'
        'echo "${FAKE_SACCT_STATE:-COMPLETED}|${FAKE_SACCT_EXIT:-0}:0"\n',
    )
    _write_executable(
        fake_bin / "scancel",
        f'#!/usr/bin/env bash\necho "$1" > {tmp_path / "cancelled-job"}\n',
    )
    (tooling / "pixi.path").write_text(f"{pixi}\n", encoding="utf-8")

    source, commit = _prepare_git_repositories(tmp_path)
    mirror = mirror_parent / "nf-genome_to_diffraction.git"
    _run(["git", "clone", "-q", "--mirror", str(source), str(mirror)], cwd=tmp_path)
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["GIT_ALLOW_PROTOCOL"] = "file"
    return dispatcher, smoke_job, environment, commit


def test_remote_dispatcher_full_fake_scheduler_lifecycle(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    source_bootstrap = tmp_path / "source-origin" / "bootstrap"
    dispatcher_digest = hashlib.sha256(
        (source_bootstrap / dispatcher.name).read_bytes()
    ).hexdigest()
    smoke_job_digest = hashlib.sha256(
        (source_bootstrap / smoke_job.name).read_bytes()
    ).hexdigest()
    smoke_job.write_text(
        smoke_job.read_text(encoding="utf-8") + "# stale installed copy\n",
        encoding="utf-8",
    )

    deployed = _run(
        [
            str(dispatcher),
            "deploy-tools",
            commit,
            dispatcher_digest,
            smoke_job_digest,
        ],
        cwd=tmp_path,
        environment=environment,
    )
    deployed_fields = _decode_protocol(deployed.stdout)
    assert deployed_fields["deployed"] == "true"
    assert deployed_fields["commit"] == commit
    assert hashlib.sha256(dispatcher.read_bytes()).hexdigest() == dispatcher_digest
    assert hashlib.sha256(smoke_job.read_bytes()).hexdigest() == smoke_job_digest
    deployment_record = json.loads(
        (dispatcher.parent / "deployed-tools.json").read_text(encoding="utf-8")
    )
    assert deployment_record["dispatcher_sha256"] == dispatcher_digest
    assert deployment_record["smoke_job_sha256"] == smoke_job_digest

    lock_checksum = subprocess.run(
        ["sha256sum", tmp_path / "source-origin" / "pixi.lock"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[0]

    staged = _run(
        [
            str(dispatcher),
            "stage",
            RUN_ID,
            commit,
            lock_checksum,
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(staged.stdout)["phase"] == "staged"

    submitted = _run(
        [str(dispatcher), "submit", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(submitted.stdout)["job_id"] == "123"
    submitted_arguments = (
        (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    )
    remote_root = smoke_job.parent.parent
    assert submitted_arguments[-4:] == [
        str(smoke_job),
        RUN_ID,
        str(remote_root),
        "smoke",
    ]

    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "123"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    job_environment["FAKE_PIXI_READONLY_TMP"] = "1"
    spool_directory = tmp_path / "slurm-spool"
    spool_directory.mkdir()
    spooled_job = spool_directory / "slurm_script"
    shutil.copy2(smoke_job, spooled_job)
    _run(
        [str(spooled_job), RUN_ID, str(remote_root), "smoke"],
        cwd=tmp_path,
        environment=job_environment,
    )
    scratch = job_environment["SLURM_TMPDIR"] + f"/nf-gtd-123-{RUN_ID}"
    assert not Path(scratch).exists()

    status = _run(
        [str(dispatcher), "status", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )
    status_fields = _decode_protocol(status.stdout)
    assert status_fields["scheduler_state"] == "COMPLETED"
    assert status_fields["failure_class"] == "success"
    assert status_fields["terminal"] == "true"

    cancelled_environment = dict(environment)
    cancelled_environment["FAKE_SACCT_STATE"] = "CANCELLED"
    cancelled_status = _run(
        [str(dispatcher), "status", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=cancelled_environment,
    )
    cancelled_fields = _decode_protocol(cancelled_status.stdout)
    assert cancelled_fields["failure_class"] == "unknown_failure"
    assert cancelled_fields["terminal"] == "true"

    logs = _run(
        [str(dispatcher), "logs", RUN_ID, OWNER_ID, "200"],
        cwd=tmp_path,
        environment=environment,
    )
    log_fields = _decode_protocol(logs.stdout)
    assert (
        "smoke_status=success"
        in base64.b64decode(log_fields["content_base64"]).decode()
    )

    archive_path = tmp_path / "collected.tar.gz"
    archive_path.write_bytes(
        _run(
            [str(dispatcher), "collect", RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    with tarfile.open(archive_path, "r:gz") as archive:
        assert "manifest.json" in archive.getnames()
        assert "state/job-result.json" in archive.getnames()

    _run(
        [str(dispatcher), "cancel", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )
    assert (tmp_path / "cancelled-job").read_text(encoding="utf-8").strip() == "123"

    rejected = _run(
        [str(dispatcher), "clean", RUN_ID, OWNER_ID, "wrong"],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(rejected.stdout)["failure_class"] == "wrapper_failure"
    assert (tmp_path / "remote-root" / "runs" / RUN_ID).is_dir()

    _run(
        [str(dispatcher), "clean", RUN_ID, OWNER_ID, RUN_ID],
        cwd=tmp_path,
        environment=environment,
    )
    assert not (tmp_path / "remote-root" / "runs" / RUN_ID).exists()


def test_remote_dispatcher_rejects_command_injection_before_side_effects(
    tmp_path: Path,
) -> None:
    dispatcher, _, environment, _ = _prepare_remote_layout(tmp_path)
    result = _run(
        [str(dispatcher), "status", "../../bad;touch", OWNER_ID],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(result.stdout)["failure_class"] == "wrapper_failure"
    assert not (tmp_path / "bad").exists()

    original_dispatcher = hashlib.sha256(dispatcher.read_bytes()).hexdigest()
    rejected_deployment = _run(
        [str(dispatcher), "deploy-tools", "1" * 39 + ";", "0" * 64, "0" * 64],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(rejected_deployment.stdout)["failure_class"] == (
        "wrapper_failure"
    )
    assert hashlib.sha256(dispatcher.read_bytes()).hexdigest() == original_dispatcher


def test_remote_dispatcher_rejects_deployment_checksum_mismatch(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    original_dispatcher = hashlib.sha256(dispatcher.read_bytes()).hexdigest()
    original_smoke_job = hashlib.sha256(smoke_job.read_bytes()).hexdigest()

    rejected = _run(
        [str(dispatcher), "deploy-tools", commit, "0" * 64, "0" * 64],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )

    assert _decode_protocol(rejected.stdout)["failure_class"] == "transfer_failure"
    assert hashlib.sha256(dispatcher.read_bytes()).hexdigest() == original_dispatcher
    assert hashlib.sha256(smoke_job.read_bytes()).hexdigest() == original_smoke_job
    assert not (dispatcher.parent / "deployed-tools.json").exists()


def _lock_checksum(tmp_path: Path) -> str:
    return subprocess.run(
        ["sha256sum", tmp_path / "source-origin" / "pixi.lock"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[0]


def _write_p0_paths(root: Path, *, unsafe: bool = False) -> Path:
    allowed = root / "p0-inputs"
    allowed.mkdir()
    database_root = allowed / "databases"
    database_root.mkdir()
    inputs = []
    for name in ("catalogues.json", "crystals.json", "config.yaml", "phenix.json"):
        path = allowed / name
        path.write_text("{}\n", encoding="utf-8")
        inputs.append(path)
    p0_config = root / "_config" / "p0.paths"
    p0_config.parent.mkdir()
    crystal_path = str(inputs[1])
    if unsafe:
        crystal_path += ";touch-bad"
    p0_config.write_text(
        "\n".join(
            (
                str(allowed),
                str(inputs[0]),
                crystal_path,
                str(inputs[2]),
                str(database_root),
                str(inputs[3]),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    p0_config.chmod(0o600)
    return p0_config


def test_p0_stage_fingerprints_fixed_config_and_rejects_unsafe_paths_at_run(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    p0_config = _write_p0_paths(remote_root, unsafe=True)

    staged = _run(
        [
            str(dispatcher),
            "stage",
            P0_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "p0",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    staged_fields = _decode_protocol(staged.stdout)
    assert staged_fields["profile"] == "p0"
    manifest = json.loads(
        (remote_root / "runs" / P0_RUN_ID / "manifest.json").read_text(encoding="utf-8")
    )
    assert (
        manifest["p0_config_sha256"]
        == hashlib.sha256(p0_config.read_bytes()).hexdigest()
    )

    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "321"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    failed = _run(
        [str(smoke_job), P0_RUN_ID, str(remote_root), "p0"],
        cwd=tmp_path,
        environment=job_environment,
        success=False,
    )
    assert failed.returncode != 0
    failure = (remote_root / "runs" / P0_RUN_ID / "state" / "failure-class").read_text(
        encoding="utf-8"
    )
    assert failure.strip() == "environment_failure"
    assert not (tmp_path / "bad").exists()


def _install_fake_p0_runtime(run: Path, *, all_cached: bool = True) -> None:
    bin_directory = run / "source" / ".pixi" / "envs" / "hpc" / "bin"
    bin_directory.mkdir(parents=True)
    _write_executable(
        bin_directory / "genome-to-diffraction",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mode=\n"
        "previous=\n"
        'for argument in "$@"; do\n'
        '  [[ "$argument" != databases ]] || mode=databases\n'
        '  if [[ "$previous" == --verification-log ]]; then\n'
        "    printf 'verified\\n' > \"$argument\"\n"
        '  elif [[ "$mode" == databases && "$previous" == --manifest ]]; then\n'
        "    printf '{}\\n' > \"$argument\"\n"
        "  fi\n"
        '  previous="$argument"\n'
        "done\n",
    )
    status = "CACHED" if all_cached else "COMPLETED"
    _write_executable(
        bin_directory / "nextflow",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "outdir=\n"
        "previous=\n"
        'for argument in "$@"; do\n'
        '  if [[ "$previous" == --outdir ]]; then outdir="$argument"; fi\n'
        '  previous="$argument"\n'
        "done\n"
        '[[ -n "$outdir" ]]\n'
        'mkdir -p "$outdir/pipeline_info" "$outdir/scope" '
        '"$outdir/catalogue" "$outdir/preflight" "$outdir/matthews"\n'
        "printf 'task_id\\tstatus\\n' > \"$outdir/pipeline_info/trace.tsv\"\n"
        f"for task in 1 2 3 4; do printf '%s\\t{status}\\n' \"$task\"; done "
        '>> "$outdir/pipeline_info/trace.tsv"\n'
        "for name in report.html timeline.html dag.html; do "
        "printf '<html></html>\\n' > \"$outdir/pipeline_info/$name\"; done\n"
        'printf \'{"status":"task05_preflight_complete_downstream_deferred"}\\n\' '
        '> "$outdir/scope/pipeline_scope.json"\n'
        "printf '{}\\n' > \"$outdir/catalogue/catalogue_import_manifest.json\"\n"
        "printf '{}\\n' > \"$outdir/preflight/mtz_preflight.jsonl\"\n"
        "printf 'header\\n' > \"$outdir/preflight/mtz_preflight.tsv\"\n"
        "printf '# preflight\\n' > \"$outdir/preflight/preflight_report.md\"\n"
        "printf '# matthews\\n' > \"$outdir/matthews/matthews_report.md\"\n",
    )


@pytest.mark.parametrize(
    ("all_cached", "success", "failure_class"),
    [(True, True, "success"), (False, False, "test_failure")],
)
def test_p0_job_enforces_the_cached_resume_gate(
    tmp_path: Path,
    all_cached: bool,
    success: bool,
    failure_class: str,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_p0_paths(remote_root)
    _run(
        [
            str(dispatcher),
            "stage",
            P0_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "p0",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    run = remote_root / "runs" / P0_RUN_ID
    _install_fake_p0_runtime(run, all_cached=all_cached)
    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "654"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")

    _run(
        [str(smoke_job), P0_RUN_ID, str(remote_root), "p0"],
        cwd=tmp_path,
        environment=job_environment,
        success=success,
    )

    result = json.loads((run / "state" / "job-result.json").read_text(encoding="utf-8"))
    assert result["failure_class"] == failure_class
    if all_cached:
        resume = json.loads(
            (run / "artifacts" / "qualification" / "resume-check.json").read_text(
                encoding="utf-8"
            )
        )
        assert resume["cached_process_count"] == 4
        assert resume["all_deterministic_processes_cached"] is True


def test_remote_dispatcher_classifies_scheduler_rejection_and_concurrency(
    tmp_path: Path,
) -> None:
    dispatcher, _, environment, commit = _prepare_remote_layout(tmp_path)
    lock_checksum = _lock_checksum(tmp_path)
    for run_id in (RUN_ID, SECOND_RUN_ID):
        _run(
            [
                str(dispatcher),
                "stage",
                run_id,
                commit,
                lock_checksum,
                OWNER_ID,
                "1",
                "smoke",
            ],
            cwd=tmp_path,
            environment=environment,
        )

    rejected_environment = dict(environment)
    rejected_environment["FAKE_SBATCH_REJECT"] = "1"
    rejected = _run(
        [str(dispatcher), "submit", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=rejected_environment,
        success=False,
    )
    assert _decode_protocol(rejected.stdout)["failure_class"] == ("scheduler_rejection")

    _run(
        [str(dispatcher), "submit", SECOND_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )
    third_run = "gtd-smoke-20260802T120002Z-0123456789ab-01234569"
    _run(
        [
            str(dispatcher),
            "stage",
            third_run,
            commit,
            lock_checksum,
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    active_environment = dict(environment)
    active_environment["FAKE_SQUEUE_STATE"] = "RUNNING"
    concurrent = _run(
        [str(dispatcher), "submit", third_run, OWNER_ID],
        cwd=tmp_path,
        environment=active_environment,
        success=False,
    )
    assert _decode_protocol(concurrent.stdout)["failure_class"] == (
        "scheduler_rejection"
    )

    fourth_run = "gtd-smoke-20260802T120003Z-0123456789ab-0123456a"
    _run(
        [
            str(dispatcher),
            "stage",
            fourth_run,
            commit,
            lock_checksum,
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    stale_lock_environment = dict(environment)
    stale_lock_environment["FAKE_SQUEUE_FAIL"] = "1"
    recovered = _run(
        [str(dispatcher), "submit", fourth_run, OWNER_ID],
        cwd=tmp_path,
        environment=stale_lock_environment,
    )
    assert _decode_protocol(recovered.stdout)["job_id"] == "123"


def test_remote_dispatcher_classifies_node_failure_and_oversized_collection(
    tmp_path: Path,
) -> None:
    dispatcher, _, environment, commit = _prepare_remote_layout(tmp_path)
    lock_checksum = _lock_checksum(tmp_path)
    _run(
        [
            str(dispatcher),
            "stage",
            RUN_ID,
            commit,
            lock_checksum,
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    _run(
        [str(dispatcher), "submit", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )

    node_environment = dict(environment)
    node_environment["FAKE_SACCT_STATE"] = "NODE_FAIL"
    node_status = _run(
        [str(dispatcher), "status", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=node_environment,
    )
    assert _decode_protocol(node_status.stdout)["failure_class"] == "node_failure"

    unavailable_environment = dict(environment)
    unavailable_environment["FAKE_SQUEUE_FAIL"] = "1"
    unavailable_environment["FAKE_SACCT_FAIL"] = "1"
    unavailable_status = _run(
        [str(dispatcher), "status", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=unavailable_environment,
    )
    unavailable_fields = _decode_protocol(unavailable_status.stdout)
    assert unavailable_fields["scheduler_state"] == "UNKNOWN"
    assert unavailable_fields["terminal"] == "false"

    smoke_log = tmp_path / "remote-root" / "runs" / RUN_ID / "logs" / "smoke.log"
    smoke_log.touch()
    os.truncate(smoke_log, 20 * 1024 * 1024 + 1)
    oversized = _run(
        [str(dispatcher), "collect", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(oversized.stdout)["failure_class"] == "transfer_failure"


@pytest.mark.parametrize(
    ("environment_key", "expected_class"),
    [
        ("FAKE_PIXI_INSTALL_FAIL", "environment_failure"),
        ("FAKE_PIXI_RUN_FAIL", "test_failure"),
    ],
)
def test_smoke_job_distinguishes_environment_and_test_failures(
    tmp_path: Path, environment_key: str, expected_class: str
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    _run(
        [
            str(dispatcher),
            "stage",
            RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "456"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    job_environment[environment_key] = "1"
    _run(
        [str(smoke_job), RUN_ID, str(smoke_job.parent.parent), "smoke"],
        cwd=tmp_path,
        environment=job_environment,
        success=False,
    )
    failure = (
        tmp_path / "remote-root" / "runs" / RUN_ID / "state" / "failure-class"
    ).read_text(encoding="utf-8")
    assert failure.strip() == expected_class


def test_smoke_job_records_term_signal_as_cancellation(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    _run(
        [
            str(dispatcher),
            "stage",
            RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "789"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    job_environment["FAKE_PIXI_TERM_PARENT"] = "1"
    terminated = _run(
        [str(smoke_job), RUN_ID, str(smoke_job.parent.parent), "smoke"],
        cwd=tmp_path,
        environment=job_environment,
        success=False,
    )
    assert terminated.returncode == 143
    result_path = (
        tmp_path / "remote-root" / "runs" / RUN_ID / "state" / "job-result.json"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["scheduler_state"] == "CANCELLED"
    assert result["failure_class"] == "unknown_failure"
    assert result["exit_code"] == 143
    scratch = job_environment["SLURM_TMPDIR"] + f"/nf-gtd-789-{RUN_ID}"
    assert not Path(scratch).exists()
