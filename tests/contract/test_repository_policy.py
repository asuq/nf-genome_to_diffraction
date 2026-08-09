"""Contract tests for the intentionally narrow foundation repository."""

from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]


def test_operational_documentation_is_tracked_separately_from_handoff() -> None:
    assert (REPOSITORY / "docs" / "README.md").is_file()
    assert (REPOSITORY / "docs" / "marmic-prototype-runbook.md").is_file()
    assert (REPOSITORY / "docs" / "prototype-test-report-2026-08-02.md").is_file()
    assert (REPOSITORY / "docs" / "hpc-feedback-loop.md").is_file()
    assert not (REPOSITORY / "prompts").exists()
    assert not (REPOSITORY / "scaffold").exists()
    assert not (REPOSITORY / "CODEX_START_HERE.md").exists()


def test_packaging_only_handoff_files_are_absent() -> None:
    for name in (
        "DEVELOPER_SPECIFICATION.md",
        "FILE_INDEX.txt",
        "PACKAGE_MANIFEST.json",
        "SHA256SUMS",
    ):
        assert not (REPOSITORY / name).exists()


def test_remote_sequence_submission_defaults_off() -> None:
    crystal = (REPOSITORY / "examples" / "crystal_manifest.json").read_text(
        encoding="utf-8"
    )
    assert '"allow_remote_sequence_submission": false' in crystal


def test_nf_helper_submodule_exposes_marmic_profile() -> None:
    gitmodules = (REPOSITORY / ".gitmodules").read_text(encoding="utf-8")
    assert "path = external/nf-helper" in gitmodules
    assert "url = https://github.com/asuq/nf-helper.git" in gitmodules
    assert "branch = main" in gitmodules

    wrapper = (REPOSITORY / "conf" / "marmic.config").read_text(encoding="utf-8")
    assert "external/nf-helper/conf/sites/marmic.config" in wrapper
    assert "beforeScript" in wrapper
    assert ".pixi/envs/hpc/bin" in wrapper
    assert "withLabel: process_database_download" in wrapper
    assert "cpus = 8" in wrapper
    assert "memory = '64 GB'" in wrapper
    assert "time = '48 hours'" in wrapper

    nextflow_config = (REPOSITORY / "nextflow.config").read_text(encoding="utf-8")
    assert "includeConfig 'conf/marmic.config'" in nextflow_config

    site_profile = (
        REPOSITORY / "external" / "nf-helper" / "conf" / "sites" / "marmic.config"
    ).read_text(encoding="utf-8")
    assert "marmic {" in site_profile
    assert "executor = 'slurm'" in site_profile
    assert "clusterOptions = '--export=ALL'" in site_profile
    assert "scratch = \"/scratch/${System.getenv('USER')}\"" in site_profile

    database_job = (REPOSITORY / "bootstrap" / "nf-gtd-hpc-smoke-job").read_text(
        encoding="utf-8"
    )
    assert "DATABASE_SCRATCH_ROOT='/scratch'" in database_job


def test_hpc_smoke_interface_keeps_cleanup_outside_automatic_operations() -> None:
    dispatcher = REPOSITORY / "bootstrap" / "nf-gtd-hpc-remote"
    smoke_job = REPOSITORY / "bootstrap" / "nf-gtd-hpc-smoke-job"
    assert dispatcher.is_file()
    assert smoke_job.is_file()
    assert dispatcher.stat().st_mode & 0o111
    assert smoke_job.stat().st_mode & 0o111

    runbook = (REPOSITORY / "docs" / "hpc-feedback-loop.md").read_text(encoding="utf-8")
    assert "Never\ninclude `clean` in a persistent Codex allow rule" in runbook
    assert "Raw SSH" in runbook
    assert "2 CPUs" in runbook
    assert "8 GB" in runbook
    assert "45-minute" in runbook
    assert "nf-gtd-hpc-test deploy-tools --revision HEAD" in runbook
    approved_operations = (
        '["deploy-tools", "readiness", "stage", "submit", "status", '
        '"wait", "logs", "collect", "cancel"]'
    )
    assert approved_operations in runbook
    job = smoke_job.read_text(encoding="utf-8")
    assert "phase=database_revalidate_bounded profile=p0" in job
    p0_body, database_body = job.split("run_database()", maxsplit=1)
    assert "--full-verify" not in p0_body
    assert "--full-verify" in database_body
    assert "SLURM_TMPDIR" in database_body
    assert "DATABASE_SCRATCH_ROOT='/scratch'" in job
    assert "scratch_parent_source=job_owned_scratch" in database_body
    assert "database payload scratch must not use /dev/shm" in database_body
    assert (REPOSITORY / "conf" / "hpc-database.paths.example").is_file()
    database_module = (
        REPOSITORY / "modules" / "local" / "prepare_database_resources.nf"
    ).read_text(encoding="utf-8")
    assert "--threads '${task.cpus}'" in database_module
    assert "threads: Integer" not in database_module
    assert "database administration" in runbook.lower()
