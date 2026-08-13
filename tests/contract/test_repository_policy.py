"""Contract tests for the intentionally narrow foundation repository."""

import hashlib
import json
from pathlib import Path

import gemmi
import yaml

from genome_to_diffraction.schemas.results import ProcessedModelRecord

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


def test_pilot_afdb_mapping_is_explicit_and_narrow() -> None:
    mapping = (
        REPOSITORY / "benchmarks" / "public-controls" / "afdb_accessions.tsv"
    ).read_text(encoding="ascii")
    assert mapping.splitlines() == [
        "source_record_id\tuniprot_accession",
        "src_e7a42a60baf486a4d28372148586124f0edeb57692f74918f2e89ae8cd8bf4ab"
        "\tA0A832VZP6",
    ]


def test_predicted_model_stub_is_schema_valid_and_checksum_bound() -> None:
    root = REPOSITORY / "tests/fixtures/stubs/predicted_model_preparation"
    records = (root / "processed_models.jsonl").read_text(encoding="ascii").splitlines()
    assert len(records) == 1
    record = ProcessedModelRecord.model_validate_json(records[0])
    manifest = json.loads(
        (root / "model_preparation_manifest.json").read_text(encoding="ascii")
    )
    assert manifest["processed_model_count"] == 1
    assert manifest["entries"][0]["model_id"] == record.model_id
    model = root / manifest["entries"][0]["model_path"]
    assert hashlib.sha256(model.read_bytes()).hexdigest() == record.model_sha256
    structure = gemmi.read_structure(str(model))
    structure.setup_entities()
    assert len(structure) == 1
    assert structure[0]["A"].get_polymer().make_one_letter_sequence() == "ACDE"


def test_remote_sequence_submission_defaults_off() -> None:
    crystal = (REPOSITORY / "examples" / "crystal_manifest.json").read_text(
        encoding="utf-8"
    )
    assert '"allow_remote_sequence_submission": false' in crystal


def test_pilot_retention_cap_preserves_the_qualified_8oox_copy_rank() -> None:
    config = yaml.safe_load(
        (REPOSITORY / "examples" / "config.yaml").read_text(encoding="utf-8")
    )

    assert config["matthews"]["max_hypotheses_per_candidate"] == 4


def test_diverse_funnel_stages_coordinate_sources_under_unique_names() -> None:
    module = (
        REPOSITORY / "modules" / "local" / "build_diverse_first_copy_funnel.nf"
    ).read_text(encoding="utf-8")

    assert (
        "stageAs predicted_coordinate_sources, "
        "'predicted_coordinate_sources.jsonl'" in module
    )
    assert "stageAs pdb_coordinate_sources, 'pdb_coordinate_sources.jsonl'" in module
    assert "--coordinate-sources '${predicted_coordinate_sources}'" in module
    assert "--coordinate-sources '${pdb_coordinate_sources}'" in module


def test_nf_helper_submodule_exposes_marmic_history_and_active_viper_profile() -> None:
    gitmodules = (REPOSITORY / ".gitmodules").read_text(encoding="utf-8")
    assert "path = external/nf-helper" in gitmodules
    assert "url = https://github.com/asuq/nf-helper.git" in gitmodules
    assert "branch = main" in gitmodules

    wrapper = (REPOSITORY / "conf" / "marmic.config").read_text(encoding="utf-8")
    assert "external/nf-helper/conf/sites/marmic.config" in wrapper
    assert "beforeScript" in wrapper
    assert ".pixi/envs/hpc/bin" in wrapper
    mr_block = wrapper.split("withLabel: process_mr", maxsplit=1)[1].split(
        "withLabel: process_prostt5_search", maxsplit=1
    )[0]
    assert "cpus = 4" in mr_block
    assert "memory = '8 GB'" in mr_block
    assert "25-job prototype fanout" in wrapper
    assert "withLabel: process_database_download" in wrapper
    assert "cpus = 100" in wrapper
    assert "memory = '2000 GB'" in wrapper
    assert "time = '48 hours'" in wrapper
    assert "withLabel: process_prostt5_search" in wrapper
    assert "time = '1000 hours'" in wrapper

    nextflow_config = (REPOSITORY / "nextflow.config").read_text(encoding="utf-8")
    assert "includeConfig 'conf/marmic.config'" in nextflow_config
    assert "includeConfig 'conf/viper-cpu.config'" in nextflow_config

    site_profile = (
        REPOSITORY / "external" / "nf-helper" / "conf" / "sites" / "marmic.config"
    ).read_text(encoding="utf-8")
    assert "marmic {" in site_profile
    assert "executor = 'slurm'" in site_profile
    assert "clusterOptions = '--export=ALL'" in site_profile
    assert "scratch = \"/scratch/${System.getenv('USER')}\"" in site_profile

    viper_wrapper = (REPOSITORY / "conf" / "viper-cpu.config").read_text(
        encoding="utf-8"
    )
    assert "external/nf-helper/conf/sites/viper-cpu.config" in viper_wrapper
    assert "max_cpus = 64" in viper_wrapper
    assert "max_memory = 192000.MB" in viper_wrapper
    assert "cpus: 64" in viper_wrapper
    assert "memory: 192000.MB" in viper_wrapper
    assert "maxForks = 7" in viper_wrapper
    assert "--partition=datatransfer" not in viper_wrapper
    assert "workDir = \"/ptmp/${System.getenv('USER')}" in viper_wrapper

    database_job = (REPOSITORY / "bootstrap" / "nf-gtd-hpc-smoke-job").read_text(
        encoding="utf-8"
    )
    assert "scratch_parent_source=job_owned_ptmp" in database_job
    assert "/dev/shm" not in database_job

    phaser_module = (
        REPOSITORY / "modules" / "local" / "run_first_copy_phaser.nf"
    ).read_text(encoding="utf-8")
    assert "--threads '${task.cpus}'" in phaser_module


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
        '"wait", "logs", "collect", "review-collect", "cancel"]'
    )
    assert approved_operations in runbook
    job = smoke_job.read_text(encoding="utf-8")
    assert "--prostt5_maximum_queries 128" in job
    assert "phase=database_revalidate_bounded profile=p0" in job
    p0_body, database_body = job.split("run_database()", maxsplit=1)
    assert "--full-verify" not in p0_body
    assert "--full-verify" in database_body
    assert "SLURM_TMPDIR" not in database_body
    assert "scratch_parent_source=job_owned_ptmp" in job
    assert "/dev/shm" not in job
    assert "scratch_parent_source=job_owned_ptmp" in database_body
    assert "phase=pixi_verify_offline profile=database" in database_body
    assert "--offline" in database_body
    assert "database resource build uses compute scratch" in (
        REPOSITORY / "src" / "genome_to_diffraction" / "databases" / "prepare.py"
    ).read_text(encoding="utf-8")
    dispatcher_text = dispatcher.read_text(encoding="utf-8")
    assert "--cpus-per-task=64" in dispatcher_text
    assert "--mem=192G" in dispatcher_text
    assert "stage_hpc_environment_ready" in dispatcher_text
    assert "databases stage-sources" in dispatcher_text
    assert "database-source-stage.log" in dispatcher_text
    assert "database-source-bundle-sha256" in dispatcher_text
    assert "--source-bundle" in database_body
    assert (REPOSITORY / "conf" / "hpc-database.paths.example").is_file()
    database_module = (
        REPOSITORY / "modules" / "local" / "prepare_database_resources.nf"
    ).read_text(encoding="utf-8")
    assert "--threads '${task.cpus}'" in database_module
    assert "threads: Integer" not in database_module
    assert "database administration" in runbook.lower()
