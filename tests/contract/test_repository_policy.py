"""Contract tests for the intentionally narrow foundation repository."""

import hashlib
import json
import re
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
    assert "withLabel: m6_pdb_search" in wrapper
    assert "withLabel: m6_foldseek_search" in wrapper
    assert wrapper.count("cpus = 32") >= 2

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
    assert "managed run root is a non-Viper noncanonical path" in database_job
    assert '"$(<"$RUN/state/site-id")" == viper-cpu' in database_job

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
        '"wait", "logs", "collect", "review-collect", '
        '"t12-review-collect", "cancel"]'
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
    assert "--cpus-per-task=4" in dispatcher_text
    assert "--mem=8G" in dispatcher_text
    assert "stage_hpc_environment_ready" in dispatcher_text
    assert "databases stage-sources" in dispatcher_text
    assert "database-source-stage.log" in dispatcher_text
    assert "logs/m4-import-stage.log" in dispatcher_text
    assert "logs/control-slice-stage.log" in dispatcher_text
    assert "control_slice_import_manifest.json" in dispatcher_text
    assert "control-slice-stage requires the fixed Viper site" in dispatcher_text
    m4_body = job.split("run_m4_copy() {", maxsplit=1)[1].split(
        "run_database() {", maxsplit=1
    )[0]
    assert "load_p0_config" not in m4_body
    assert "export NF_HELPER_VIPER_COMPUTE_CONTROLLER=managed-slurm" in m4_body
    assert "export NXF_APPTAINER_CACHEDIR=/ptmp/ashima/apptainer-cache" in m4_body
    additional_copy_workflow = (
        REPOSITORY / "workflows" / "additional_copy_workflow.nf"
    ).read_text(encoding="utf-8")
    additional_copy_module = (
        REPOSITORY / "modules" / "local" / "run_additional_copy_phaser.nf"
    ).read_text(encoding="utf-8")
    assert "row.search_model_sha256 as String" in additional_copy_workflow
    assert "--expected-search-model-sha256 '${seed[2]}'" in additional_copy_module
    assert "database-source-bundle-sha256" in dispatcher_text
    assert "--source-bundle" in database_body
    assert (REPOSITORY / "conf" / "hpc-database.paths.example").is_file()
    database_module = (
        REPOSITORY / "modules" / "local" / "prepare_database_resources.nf"
    ).read_text(encoding="utf-8")
    assert "--threads '${task.cpus}'" in database_module
    assert "threads: Integer" not in database_module
    assert "database administration" in runbook.lower()


def test_m6_scientific_stage_uses_viper_runtime_manifests() -> None:
    """Keep M6 independent of the legacy single-root P0 site contract."""

    dispatcher = (REPOSITORY / "bootstrap" / "nf-gtd-hpc-remote").read_text(
        encoding="utf-8"
    )
    stage_body = dispatcher.split("stage_run_common() {", maxsplit=1)[1].split(
        "stage_run() {", maxsplit=1
    )[0]
    m6_body = dispatcher.split("m6_runner_stage_common() {", maxsplit=1)[1].split(
        "m6_inputs_stage_run() {", maxsplit=1
    )[0]

    assert '"$profile" == m6-operational || "$profile" == m6-leakage' in stage_body
    assert "database_config_readiness runtime" in stage_body
    assert 'phenix_manifest="${startup_site_values[6]}"' in stage_body
    assert 'atomic_text "$run/state/database-manifest" "$DATABASE_MANIFEST"' in (
        stage_body
    )
    assert 'atomic_text "$run/state/phenix-manifest" "$phenix_manifest"' in (stage_body)
    assert "P0_CONFIG" not in m6_body
    assert 'database_manifest="$(<"$run/state/database-manifest")"' in m6_body
    assert 'phenix_manifest="$(<"$run/state/phenix-manifest")"' in m6_body


def test_m6_scientific_fanout_remains_nextflow_owned() -> None:
    """Prevent a return to one multi-sample Python/Slurm allocation."""

    agents = (REPOSITORY / "AGENTS.md").read_text(encoding="utf-8")
    architecture = (REPOSITORY / "docs/execution-architecture.md").read_text(
        encoding="utf-8"
    )
    job = (REPOSITORY / "bootstrap/nf-gtd-hpc-smoke-job").read_text(encoding="utf-8")
    m6_body = job.split("run_m6_scientific() {", maxsplit=1)[1].split(
        "run_m4_copy_nextflow() {", maxsplit=1
    )[0]
    workflow = (REPOSITORY / "workflows/m6_validation_workflow.nf").read_text(
        encoding="utf-8"
    )
    modules = (REPOSITORY / "modules/local/m6_nextflow_tasks.nf").read_text(
        encoding="utf-8"
    )
    viper = (REPOSITORY / "conf/viper-cpu.config").read_text(encoding="utf-8")
    legacy = (
        REPOSITORY / "src/genome_to_diffraction/benchmarks/m6_scientific.py"
    ).read_text(encoding="utf-8")
    task_boundaries = (
        REPOSITORY / "src/genome_to_diffraction/benchmarks/m6_nextflow.py"
    ).read_text(encoding="utf-8")
    policy = yaml.safe_load(
        (REPOSITORY / "benchmarks/m6/execution-nextflow-v1.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert "Independent catalogues, samples, candidates, hypotheses" in agents
    assert "efficient batch" in agents
    assert "shared-store task's inputs" in agents
    assert "Nextflow owns scientific fan-out" in architecture
    assert "run_m6_nextflow first" in m6_body
    assert "benchmark run-m6-scientific" not in m6_body
    assert "m6_validation.nf" in job
    assert '--software_lock "$RUN/source/pixi.lock"' in job
    assert '"artifacts/m6-nextflow-results"' in job
    assert "groupKey(" in workflow
    assert "M6_FIRST_COPY(hypothesis_tasks)" in workflow
    assert "M6_ADDITIONAL_COPY(copy_tasks)" in workflow
    assert "M6_BUILD_SEARCH_BATCHES" in workflow
    assert "M6_SEARCH_PDB" in modules and "M6_SEARCH_FOLDSEEK" in modules
    assert "ThreadPoolExecutor" not in legacy
    assert "ThreadPoolExecutor" not in task_boundaries
    assert "ProcessPoolExecutor" not in task_boundaries
    assert "multiprocessing" not in task_boundaries
    assert policy["per_job"]["maximum_cpus"] == 32
    assert policy["search_batching"]["mmseqs2"]["cpus"] == 32
    assert policy["search_batching"]["foldseek"]["cpus"] == 32
    assert policy["search_batching"]["global_exact_sequence_deduplication"] is True
    assert policy["concurrency"]["phenix_policy"] == "scheduler_managed"
    assert "withLabel: m6_pdb_search" in viper
    assert "withLabel: m6_foldseek_search" in viper
    assert viper.count("cpus = 32") >= 2


def test_marmic_store_dir_tasks_bypass_node_scratch() -> None:
    """Keep permanent shared-store writes out of Marmic scratch copy-back."""

    module = (REPOSITORY / "modules/local/m6_nextflow_tasks.nf").read_text(
        encoding="utf-8"
    )
    marmic = (REPOSITORY / "conf/marmic.config").read_text(encoding="utf-8")
    process_bodies = {
        match.group("name"): match.group("body")
        for match in re.finditer(
            r"^process (?P<name>[A-Z0-9_]+) \{(?P<body>.*?)(?=^process |\Z)",
            module,
            flags=re.MULTILINE | re.DOTALL,
        )
    }
    stored_processes = {
        name for name, body in process_bodies.items() if "storeDir" in body
    }

    assert stored_processes == {
        "M6_IMPORT_CATALOGUE",
        "M6_SEARCH_PDB",
        "M6_SEARCH_FOLDSEEK",
    }
    for process_name in sorted(stored_processes):
        selector = marmic.split(f"withName: {process_name} {{", maxsplit=1)
        assert len(selector) == 2, f"missing Marmic selector for {process_name}"
        assert "scratch = false" in selector[1].split("}", maxsplit=1)[0]


def test_m6_smoke_uses_only_fixed_site_bound_profiles_and_policies() -> None:
    """Keep Marmic migration closed over staged immutable run state."""

    dispatcher = (REPOSITORY / "bootstrap/nf-gtd-hpc-remote").read_text(
        encoding="utf-8"
    )
    job = (REPOSITORY / "bootstrap/nf-gtd-hpc-smoke-job").read_text(encoding="utf-8")
    smoke_body = job.split("load_m6_smoke_site_contract() {", maxsplit=1)[1].split(
        "run_m6_nextflow() {", maxsplit=1
    )[0]
    viper_policy = yaml.safe_load(
        (REPOSITORY / "benchmarks/m6/execution-nextflow-v1.yaml").read_text()
    )
    marmic_policy = yaml.safe_load(
        (REPOSITORY / "benchmarks/m6/execution-nextflow-marmic-v1.yaml").read_text()
    )
    marmic_site = (
        REPOSITORY / "external/nf-helper/conf/sites/marmic.config"
    ).read_text()

    assert "SITE_ID=marmic" in dispatcher
    assert "SITE_ID=viper-cpu" in dispatcher
    assert "unsupported HPC site configuration" in dispatcher
    assert "stage_m6_site_policy_bound" in dispatcher
    assert "validate_m6_smoke_site_state" in dispatcher
    assert "execution-nextflow-marmic-v1.yaml" in dispatcher
    assert "execution-nextflow-v1.yaml" in dispatcher
    assert '-profile "$M6_NEXTFLOW_PROFILE"' in smoke_body
    assert "--execution_policy" in smoke_body
    assert '"$M6_EXECUTION_POLICY"' in smoke_body
    assert '--execution-policy "$M6_EXECUTION_POLICY"' in smoke_body
    assert '--apptainer_cache_dir "$M6_APPTAINER_CACHE"' in smoke_body
    assert 'export NXF_APPTAINER_CACHEDIR="$M6_APPTAINER_CACHE"' in smoke_body
    assert 'if [[ "$M6_SITE_ID" == viper-cpu ]]' in smoke_body
    assert "unset NF_HELPER_VIPER_COMPUTE_CONTROLLER" in smoke_body
    assert "/ptmp/ashima/apptainer-cache" not in smoke_body
    assert viper_policy["site_id"] == "viper-cpu"
    assert viper_policy["policy_id"] == "m6_nextflow_slurm_v1"
    assert viper_policy["concurrency"] == {
        "aggregate_policy": "scheduler_managed",
        "phenix_policy": "scheduler_managed",
        "queue_size": 250,
        "submit_rate_limit": "5/1s",
    }
    assert marmic_policy["site_id"] == "marmic"
    assert marmic_policy["policy_id"] == "m6_nextflow_slurm_marmic_v1"
    assert marmic_policy["concurrency"] == {
        "aggregate_policy": "scheduler_managed",
        "phenix_policy": "scheduler_managed",
        "queue_size": 30,
        "submit_rate_limit": "10/1s",
    }
    assert "executor_queue_size = 30" in marmic_site
    assert "executor_submit_rate_limit = '10/1s'" in marmic_site
