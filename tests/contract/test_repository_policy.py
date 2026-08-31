"""Contract tests for the intentionally narrow foundation repository."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

import gemmi
import pytest
import yaml

from genome_to_diffraction.schemas.results import ProcessedModelRecord

REPOSITORY = Path(__file__).resolve().parents[2]


def test_root_nextflow_surface_has_only_intentional_owners() -> None:
    assert {path.name for path in REPOSITORY.glob("*.nf")} == {
        "m6_validation.nf",
        "main.nf",
        "phase3_application.nf",
        "prepare_databases.nf",
        "qualification.nf",
    }


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


def test_network_acquisition_processes_use_both_reviewed_controller_labels() -> None:
    modules = {
        "REGISTER_PDB_COORDINATES": "modules/local/register_pdb_coordinates.nf",
        "RETRIEVE_AFDB_EXACT": "modules/local/retrieve_afdb_exact.nf",
    }
    for process_name, relative_path in modules.items():
        source = (REPOSITORY / relative_path).read_text(encoding="utf-8")
        process = source.split(f"process {process_name}", maxsplit=1)[1].split(
            "input:",
            maxsplit=1,
        )[0]
        assert "label 'process_network'" in process
        assert "label 'needs_internet'" in process
        assert "label 'run_local'" in process

    m6_source = (REPOSITORY / "modules/local/m6_nextflow_tasks.nf").read_text(
        encoding="utf-8"
    )
    m6_materialisation = m6_source.split("process M6_STAGE_COORDINATES", maxsplit=1)[
        1
    ].split("input:", maxsplit=1)[0]
    assert "label 'run_local'" in m6_materialisation
    assert "label 'process_network'" not in m6_materialisation
    assert "label 'needs_internet'" not in m6_materialisation

    login_labelled = {
        path.relative_to(REPOSITORY).as_posix()
        for path in (REPOSITORY / "modules").rglob("*.nf")
        if any(
            label in path.read_text(encoding="utf-8")
            for label in ("label 'needs_internet'", "label 'run_local'")
        )
    }
    assert login_labelled == {
        *modules.values(),
        "modules/local/m6_nextflow_tasks.nf",
    }

    sites = REPOSITORY / "external/nf-helper/conf/sites"
    marmic = (sites / "marmic.config").read_text(encoding="utf-8")
    viper = (sites / "viper-cpu.config").read_text(encoding="utf-8")
    assert (
        "executor = 'local'"
        in marmic.split(
            "withLabel: run_local",
            maxsplit=1,
        )[1].split("}", maxsplit=1)[0]
    )
    assert (
        "executor = 'local'"
        in viper.split(
            "withLabel: needs_internet",
            maxsplit=1,
        )[1].split("}", maxsplit=1)[0]
    )


def test_hpc_tasks_enforce_network_namespace_without_in_job_exception() -> None:
    wrapper_path = REPOSITORY / "bootstrap" / "nf-gtd-worker-offline-shell"
    wrapper = wrapper_path.read_text(encoding="utf-8")
    assert '[[ ! "${SLURM_JOB_ID:-}" =~ ^[0-9]+$ ]]' in wrapper
    assert "GTD_COMPUTE_NETWORK_ACCESS=false" in wrapper
    assert (
        'exec /usr/bin/unshare --user --map-current-user --net -- /bin/bash "$@"'
        in wrapper
    )
    outside_slurm = subprocess.run(
        ["/bin/bash", str(wrapper_path), "-c", "exit 0"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert outside_slurm.returncode == 78
    assert "requires a numeric Slurm job context" in outside_slurm.stderr

    sites = ("conf/marmic.config", "conf/viper-cpu.config")
    for relative_path in sites:
        config = (REPOSITORY / relative_path).read_text(encoding="utf-8")
        assert '"${projectDir}/bootstrap/nf-gtd-worker-offline-shell"' in config
        assert "shell = ['/bin/bash', '-ue']" not in config

    production_sources = (
        tuple(REPOSITORY.glob("*.nf"))
        + tuple((REPOSITORY / "modules").rglob("*.nf"))
        + tuple((REPOSITORY / "workflows").rglob("*.nf"))
    )
    for path in production_sources:
        source = path.read_text(encoding="utf-8")
        assert re.search(r"(?m)^\s*shell\s+['\"]", source) is None


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


def test_phase3_funnel_copies_validated_localisation_bundle() -> None:
    module = (
        REPOSITORY / "modules" / "local" / "build_phase3_diverse_first_copy_funnel.nf"
    ).read_text(encoding="utf-8")

    assert "stageInMode 'copy'" in module
    assert "--localisation-bundle '${localisation_bundle}'" in module


def test_provider_local_processes_have_complete_scheduler_resources() -> None:
    base = (REPOSITORY / "conf/base.config").read_text(encoding="utf-8")
    block = base.split("withLabel: process_local", maxsplit=1)[1].split(
        "withLabel: process_single",
        maxsplit=1,
    )[0]

    assert "cpus = 1" in block
    assert "memory = '1 GB'" in block
    assert "time = '10 min'" in block
    for relative in (
        "modules/local/resolve_provider_plan.nf",
        "modules/local/emit_disabled_provider_bundle.nf",
        "modules/local/provider_empty_graph_tasks.nf",
        "modules/local/merge_pdb_provider_hits.nf",
    ):
        module = (REPOSITORY / relative).read_text(encoding="utf-8")
        assert "label 'process_local'" in module


def test_phase3_foldseek_batches_retain_unmapped_database_targets() -> None:
    module = (
        REPOSITORY / "modules" / "local" / "phase3_foldseek_batch_tasks.nf"
    ).read_text(encoding="utf-8")

    assert "--retain-unmapped-targets" in module
    process = module.split(
        "process SEARCH_PHASE3_FOLDSEEK_BATCH",
        maxsplit=1,
    )[1].split("input:", maxsplit=1)[0]
    assert "maxForks" not in process


def test_phase3_scientific_concurrency_is_scheduler_managed() -> None:
    first_copy = (
        REPOSITORY / "modules/local/phase3_multicrystal_first_copy_tasks.nf"
    ).read_text(encoding="utf-8")
    first_copy_process = first_copy.split(
        "process RUN_PHASE3_FIRST_COPY_PHASER",
        maxsplit=1,
    )[1].split("input:", maxsplit=1)[0]
    refinement = (REPOSITORY / "modules/local/run_brief_refinement.nf").read_text(
        encoding="utf-8"
    )
    refinement_process = refinement.split(
        "process RUN_PHASE3_BRIEF_REFINEMENT",
        maxsplit=1,
    )[1].split("input:", maxsplit=1)[0]
    no_a = (REPOSITORY / "modules/local/phase3_no_a_tasks.nf").read_text(
        encoding="utf-8"
    )
    no_a_process = no_a.split(
        "process RUN_PHASE3_NO_A_FIRST_COPY",
        maxsplit=1,
    )[1].split("input:", maxsplit=1)[0]
    beam = (REPOSITORY / "modules/local/phase3_composition_beam_tasks.nf").read_text(
        encoding="utf-8"
    )
    beam_process = beam.split(
        "process RUN_PHASE3_BEAM_ATTEMPT",
        maxsplit=1,
    )[1].split("input:", maxsplit=1)[0]
    additional = (REPOSITORY / "modules/local/run_additional_copy_phaser.nf").read_text(
        encoding="utf-8"
    )
    additional_process = additional.split(
        "process RUN_PHASE3_ADDITIONAL_COPY_PHASER",
        maxsplit=1,
    )[1].split("input:", maxsplit=1)[0]
    composition = (
        REPOSITORY / "modules/local/run_phase3_composition_attempt.nf"
    ).read_text(encoding="utf-8")
    composition_process = composition.split(
        "process RUN_PHASE3_COMPOSITION_ATTEMPT",
        maxsplit=1,
    )[1].split("input:", maxsplit=1)[0]
    marmic = (REPOSITORY / "conf/marmic.config").read_text(encoding="utf-8")

    assert "maxForks" not in first_copy_process
    assert "maxForks" not in refinement_process
    assert "maxForks" not in no_a_process
    assert "maxForks" not in beam_process
    for process in (
        first_copy_process,
        additional_process,
        no_a_process,
        beam_process,
        composition_process,
    ):
        assert "base_cpus" in process
        assert "base_memory_gb" in process
        assert "base_time_hours" in process
        assert "task.attempt" in process
    assert "queueSize = 0" in marmic


def test_phase3_mr_review_stages_canonical_result_bundles() -> None:
    module = (
        REPOSITORY / "modules/local/phase3_multicrystal_first_copy_tasks.nf"
    ).read_text(encoding="utf-8")
    review_process = module.split(
        "process BUILD_PHASE3_MR_SEED_REVIEW",
        maxsplit=1,
    )[1].split("stub:", maxsplit=1)[0]

    assert 'def resultPrefix = "phase3_first_copy_${item[0]}_"' in review_process
    assert "result.name.startsWith(resultPrefix)" in review_process
    assert "first_copy_phaser_${hypothesisId}" in review_process
    assert "--result-root ." in review_process


def test_phase3_mr_retry_policy_is_bounded_and_resource_only() -> None:
    base = (REPOSITORY / "conf/base.config").read_text(encoding="utf-8")
    block = base.split("withLabel: process_mr", maxsplit=1)[1].split(
        "withLabel: process_refine",
        maxsplit=1,
    )[0]

    assert "task.exitStatus == 75" in block
    assert "task.exitStatus == 104" in block
    assert "task.exitStatus in (130..145)" in block
    assert "task.exitStatus in (175..177)" in block
    assert "maxRetries = 1" in block
    assert "maxErrors = '-1'" in block
    assert "cpus: 16" in block
    assert "memory: 64.GB" in block
    assert "time: 48.h" in block
    assert "'retry' : 'finish'" in block


def test_portable_stub_profiles_fit_two_cpu_ci_runners() -> None:
    stub_root = REPOSITORY / "tests/fixtures/stubs"
    portable = (
        "p6_empty_partner",
        "composition_attempt_fanout",
        "phase3_composition_beam",
        "unknown_pass1_screen",
        "multi_crystal_fanout",
        "provider_empty_graph",
        "localisation_wave",
    )
    for name in portable:
        config = (stub_root / name / "nextflow.config").read_text(encoding="utf-8")
        block = config.split("withLabel: process_mr", maxsplit=1)[1]
        assert "cpus = 1" in block, name
        assert "memory = '1 GB'" in block, name
    retry = (stub_root / "mr_resource_retry/nextflow.config").read_text(
        encoding="utf-8"
    )
    assert "withLabel: process_mr" not in retry


def test_nextflow_process_scripts_avoid_parameterised_runtime_casts() -> None:
    """Reject the cast form that failed live script construction on Marmic."""

    for module_path in sorted((REPOSITORY / "modules/local").glob("*.nf")):
        module = module_path.read_text(encoding="utf-8")
        assert " as List<" not in module, module_path.relative_to(REPOSITORY)


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
    assert "resourceLimits" in mr_block
    assert "cpus: 16" in mr_block
    assert "memory: 64.GB" in mr_block
    assert "time: 48.h" in mr_block
    assert "Slurm owns aggregate" in wrapper
    database_block = wrapper.split("withLabel: process_database_download", maxsplit=1)[
        1
    ].split("withLabel: process_search", maxsplit=1)[0]
    assert "cpus = 100" in database_block
    assert "memory = '2000 GB'" in database_block
    assert "time = '48 hours'" in database_block
    prostt5_block = wrapper.split("withLabel: process_prostt5_search", maxsplit=1)[
        1
    ].split("withName: SEARCH_PHASE3_FOLDSEEK_BATCH", maxsplit=1)[0]
    assert "cpus = 64" in prostt5_block
    assert "memory = '192 GB'" in prostt5_block
    assert "time = '24 hours'" in prostt5_block
    phase3_batch_block = wrapper.split(
        "withName: SEARCH_PHASE3_FOLDSEEK_BATCH", maxsplit=1
    )[1].split("withLabel: m6_small", maxsplit=1)[0]
    assert "cpus = 32" in phase3_batch_block
    assert "memory = '192 GB'" in phase3_batch_block
    assert "time = '4 hours'" in phase3_batch_block
    assert "withLabel: m6_pdb_search" in wrapper
    assert "withLabel: m6_foldseek_search" in wrapper
    assert wrapper.count("cpus = 32") >= 3

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
    assert "maxForks = 7" not in viper_wrapper
    assert "cpus: 16" in viper_wrapper
    assert "memory: 64.GB" in viper_wrapper
    assert "time: 48.h" in viper_wrapper
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
    assert 'export NXF_APPTAINER_CACHEDIR="$RUN/cache/apptainer"' in m4_body
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


@pytest.mark.parametrize(
    ("function_name", "next_function_name"),
    (
        ("run_m6_scientific", "run_m4_copy_nextflow"),
        ("run_m4_copy", "run_t12_nextflow"),
        ("run_t12", "run_database"),
    ),
)
def test_scientific_profiles_use_run_owned_apptainer_caches(
    function_name: str,
    next_function_name: str,
) -> None:
    """Legacy scientific profiles must never share an account-owned cache."""

    job = (REPOSITORY / "bootstrap/nf-gtd-hpc-smoke-job").read_text(encoding="utf-8")
    body = job.split(f"{function_name}() {{", maxsplit=1)[1].split(
        f"{next_function_name}() {{", maxsplit=1
    )[0]

    assert '"$RUN/cache/apptainer"' in body
    if function_name == "run_m6_scientific":
        assert "load_m6_smoke_site_contract || return 2" in body
        assert 'export NXF_APPTAINER_CACHEDIR="$M6_APPTAINER_CACHE"' in body
        site_contract = job.split(
            "load_m6_smoke_site_contract() {",
            maxsplit=1,
        )[1].split("run_m6_stub_nextflow() {", maxsplit=1)[0]
        assert '[[ "$M6_APPTAINER_CACHE" == "$RUN/cache/apptainer" &&' in (
            site_contract
        )
    else:
        assert 'export NXF_APPTAINER_CACHEDIR="$RUN/cache/apptainer"' in body
    assert "/ptmp/ashima/apptainer-cache" not in body


def test_only_explicit_transient_failures_receive_one_nextflow_retry() -> None:
    """Retain scientific finish semantics without retrying deterministic failures."""

    base = (REPOSITORY / "conf/base.config").read_text(encoding="utf-8")
    assert "errorStrategy = { task.exitStatus == 75 ? 'retry' : 'terminate' }" in base
    assert "maxRetries = 1" in base
    for relative_path in (
        "modules/local/run_additional_copy_phaser.nf",
        "modules/local/run_approved_partner_phaser.nf",
        "modules/local/run_planned_partner_phaser.nf",
        "modules/local/run_brief_refinement.nf",
    ):
        process = (REPOSITORY / relative_path).read_text(encoding="utf-8")
        assert "errorStrategy { task.exitStatus == 75 ? 'retry' : 'finish' }" in (
            process
        )


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
    modules = "\n".join(
        (REPOSITORY / relative).read_text(encoding="utf-8")
        for relative in (
            "modules/local/m6_nextflow_tasks.nf",
            "modules/local/m6_truthless_cache_tasks.nf",
        )
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
    assert "M6_STAGE_COORDINATES" in workflow
    assert "M6_SEARCH_PDB" in modules and "M6_SEARCH_FOLDSEEK" in modules
    coordinate_materialisation = modules.split("process M6_STAGE_COORDINATES", 1)[
        1
    ].split("process M6_PREPARE_ACTIVE_CASE", 1)[0]
    assert "label 'run_local'" in coordinate_materialisation
    assert "process_network" not in coordinate_materialisation
    assert "needs_internet" not in coordinate_materialisation
    case_process = modules.split("process M6_PREPARE_ACTIVE_CASE", 1)[1].split(
        "process M6_PREPARE_EARLY_CASE", 1
    )[0]
    case_task = task_boundaries.split("def run_m6_prepare_case_task", 1)[1].split(
        "def _phaser_output", 1
    )[0]
    assert "--coordinate-stage" in case_process
    assert "--database-manifest" not in case_process
    assert "register_pdb_coordinates" not in case_task
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


def test_control_helpers_expose_no_direct_or_nested_python_schedulers() -> None:
    """Retain preparation helpers without resurrecting direct scientific drivers."""

    relative_drivers = (
        "src/genome_to_diffraction/benchmarks/control_slice_run.py",
        "src/genome_to_diffraction/benchmarks/control_matrix_run.py",
    )
    forbidden = (
        "ThreadPoolExecutor",
        "ProcessPoolExecutor",
        "concurrent.futures",
        "multiprocessing",
    )

    for relative in relative_drivers:
        source = (REPOSITORY / relative).read_text(encoding="utf-8")
        assert all(token not in source for token in forbidden)
        assert "RunRequest" not in source
        assert "def run_control_" not in source

    cli = (REPOSITORY / "src/genome_to_diffraction/cli.py").read_text(encoding="utf-8")
    assert '"run-control-slice"' not in cli
    assert '"run-control-matrix"' not in cli
    assert '"run-m6-scientific"' not in cli


def test_m6_uses_standard_nextflow_resume_cache_without_store_dir() -> None:
    """Keep M6 reuse inside one standard Nextflow work/cache boundary."""

    module = (REPOSITORY / "modules/local/m6_truthless_cache_tasks.nf").read_text(
        encoding="utf-8"
    )
    marmic = (REPOSITORY / "conf/marmic.config").read_text(encoding="utf-8")
    entrypoint = (REPOSITORY / "m6_validation.nf").read_text(encoding="utf-8")
    params = (REPOSITORY / "tests/fixtures/stubs/m6_nextflow_params.yaml").read_text(
        encoding="utf-8"
    )
    workflow = (REPOSITORY / "workflows/m6_validation_workflow.nf").read_text(
        encoding="utf-8"
    )
    job = (REPOSITORY / "bootstrap/nf-gtd-hpc-smoke-job").read_text(encoding="utf-8")
    former_store_processes = {
        "M6_IMPORT_CATALOGUE",
        "M6_SEARCH_PDB",
        "M6_SEARCH_FOLDSEEK",
    }

    assert "storeDir" not in module
    assert "m6_discovery_store" not in entrypoint
    assert "m6_discovery_store" not in params
    assert "m6_discovery_store" not in job
    assert 'M6_SMOKE_CACHE="$RUN/cache/m6-nextflow-smoke"' in job
    assert 'M6_SMOKE_EXECUTION="$RUN/execution/m6-nextflow-smoke"' in job
    assert "m6-nextflow-smoke-cache-evidence.json" in job
    assert (
        "Stored process"
        not in job.split("run_m6_nextflow_smoke() {", maxsplit=1)[1].split(
            "run_m6_nextflow() {", maxsplit=1
        )[0]
    )
    cache_directives = [
        line for line in module.splitlines() if line.strip() == "cache 'deep'"
    ]
    assert len(cache_directives) == 3
    assert (
        "tuple(bundles, database_manifest, execution_policy, software_lock, track)"
        in workflow
    )
    assert workflow.count(".sort { left, right ->") == 7
    assert workflow.count("(left[0] as String) <=> (right[0] as String)") == 3
    for process_name in sorted(former_store_processes):
        assert f"withName: {process_name} {{" not in marmic
        process_body = module.split(f"process {process_name} {{", maxsplit=1)[1].split(
            "\n}\n", maxsplit=1
        )[0]
        assert "cache 'deep'" in process_body


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
