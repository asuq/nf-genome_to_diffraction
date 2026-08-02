"""Contract tests for the intentionally narrow foundation repository."""

from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]


def test_operational_documentation_is_tracked_separately_from_handoff() -> None:
    assert (REPOSITORY / "docs" / "README.md").is_file()
    assert (REPOSITORY / "docs" / "marmic-prototype-runbook.md").is_file()
    assert (REPOSITORY / "docs" / "prototype-test-report-2026-08-02.md").is_file()
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

    nextflow_config = (REPOSITORY / "nextflow.config").read_text(encoding="utf-8")
    assert "includeConfig 'conf/marmic.config'" in nextflow_config

    site_profile = (
        REPOSITORY / "external" / "nf-helper" / "conf" / "sites" / "marmic.config"
    ).read_text(encoding="utf-8")
    assert "marmic {" in site_profile
    assert "executor = 'slurm'" in site_profile
    assert "clusterOptions = '--export=ALL'" in site_profile
