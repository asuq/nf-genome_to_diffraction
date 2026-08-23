"""Command-line entry point for contracts and foundation utilities."""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from genome_to_diffraction import __version__
from genome_to_diffraction.benchmarks import (
    HeteromerCatalogueControlRequest,
    HeteromerControlPreparationRequest,
    HeteromerControlReviewRequest,
    HeteromerSliceAssessmentRequest,
    HeteromerSlicePreparationRequest,
    M6CollectionRequest,
    M6EvaluationRequest,
    M6InputPreparationRequest,
    M6RunnerBundleRequest,
    M6RunnerVerificationRequest,
    MrControlBundleRequest,
    PublicControlPreparationRequest,
    PublicPanelPreparationRequest,
    assess_heteromer_control_slice,
    build_6rtz_control_review,
    build_m6_runner_bundle,
    build_mr_control_bundle,
    collect_m6_evidence,
    evaluate_m6,
    load_m6_protocol,
    load_public_control_panel,
    prepare_3u7q_heteromer_control,
    prepare_6rtz_heteromer_control,
    prepare_6rtz_partner_catalogue_control,
    prepare_heteromer_control_slice,
    prepare_m6_inputs,
    prepare_public_control,
    prepare_public_control_panel,
    verify_m6_runner_bundle,
)
from genome_to_diffraction.benchmarks.control_matrix_run import (
    ControlMatrixRunRequest,
    run_control_matrix,
)
from genome_to_diffraction.benchmarks.control_slice_run import (
    ControlSliceRunRequest,
    run_control_slice,
)
from genome_to_diffraction.benchmarks.m6_execution import (
    M6ResourceEvidenceRequest,
    collect_m6_resource_evidence,
)
from genome_to_diffraction.benchmarks.m6_nextflow import (
    M6TrackPlanRequest,
    build_m6_search_batches,
    partition_m6_discovery_task,
    plan_m6_nextflow_track,
    run_m6_add_copy_task,
    run_m6_aggregate_track_task,
    run_m6_assemble_case_task,
    run_m6_catalogue_task,
    run_m6_empty_finalists_task,
    run_m6_empty_seeds_task,
    run_m6_foldseek_search_task,
    run_m6_model_policy_task,
    run_m6_pdb_search_task,
    run_m6_preflight_task,
    run_m6_prepare_case_task,
    run_m6_refinement_task,
    run_m6_select_finalists_task,
    run_m6_select_seeds_task,
)
from genome_to_diffraction.catalogue import CatalogueImportRequest, import_catalogues
from genome_to_diffraction.checksums import atomic_write_text
from genome_to_diffraction.databases.preflight import (
    DatabasePreflightRequest,
    preflight_database_administration,
)
from genome_to_diffraction.databases.prepare import (
    DEFAULT_MINIMUM_FREE_BYTES,
    DEFAULT_STORAGE_LIMIT_BYTES,
    ESM_ATLAS_PROBE_URL,
    PDB_COORDINATE_URL_TEMPLATE,
    PDB_SEQUENCE_URL,
    DatabasePreparationRequest,
    prepare,
)
from genome_to_diffraction.databases.sources import (
    SourceBundleRequest,
    stage_source_bundle,
)
from genome_to_diffraction.diffraction import (
    CrystalDispatchRequest,
    FreeRGenerationRequest,
    PreflightRequest,
    generate_free_r,
    preflight_crystals,
    prepare_crystal_dispatch,
)
from genome_to_diffraction.execution import (
    ProviderEmptyGraphRequest,
    complete_provider_empty_graph,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.localisation import (
    build_catalogue_localisation_tasks,
    build_catalogue_localisation_wave_policy,
    plan_localisation_reopen,
    run_catalogue_localisation_task,
)
from genome_to_diffraction.logging import configure_logging, parse_log_level
from genome_to_diffraction.matthews import (
    MatthewsReferenceRequest,
    MatthewsRequest,
    enumerate_matthews,
    qualify_matthews_reference,
)
from genome_to_diffraction.model_registry import (
    ExperimentalModelPreparationRequest,
    PredictedModelPreparationRequest,
    prepare_experimental_models,
    prepare_predicted_models,
)
from genome_to_diffraction.mr import (
    AddCopyRunRequest,
    ApprovedPartnerSearchRequest,
    CopyCountReportRequest,
    PartnerSearchRequest,
    PartnerSummaryRequest,
    PhaserRunRequest,
    PlannedPartnerSearchRequest,
    build_copy_count_report,
    run_additional_copy_phaser,
    run_additional_copy_series,
    run_approved_partner_search,
    run_first_copy_phaser,
    run_partner_search,
    run_planned_partner_search,
    summarize_partner_attempts,
)
from genome_to_diffraction.mr.stage_add_copy import (
    AddCopyStageRequest,
    LiveAddCopyStageRequest,
    prepare_add_copy_stage,
    prepare_live_add_copy_stage,
)
from genome_to_diffraction.phenix.errors import PhenixInstallCommandError
from genome_to_diffraction.phenix.installer import InstallRequest, install_phenix
from genome_to_diffraction.phenix.interface_probe import (
    PhaserInterfaceProbeRequest,
    probe_phaser_interface,
)
from genome_to_diffraction.phenix.recovery import (
    RecoveryRequest,
    recover_failed_install,
)
from genome_to_diffraction.phenix.runtime import (
    execute_from_manifest,
    refresh_legacy_manifest,
    verify_manifest,
)
from genome_to_diffraction.ranking import (
    ApprovedPartnerPlanRequest,
    DiverseFirstCopyFunnelRequest,
    ExactPredictedFunnelRequest,
    PartnerPlanRequest,
    build_approved_partner_search_plan,
    build_diverse_first_copy_funnel,
    build_exact_predicted_funnel,
    build_partner_search_plan,
)
from genome_to_diffraction.refinement import (
    LiveT12StageRequest,
    T12RunRequest,
    T12StageRequest,
    run_t12_candidate,
    stage_live_t12_inputs,
    stage_t12_inputs,
)
from genome_to_diffraction.review import (
    CrystalReportRequest,
    LiveSequenceCheckpointRequest,
    MrSeedApprovalRequest,
    MrSeedReviewRequest,
    ResourceSummaryRequest,
    SequenceCheckpointRequest,
    StatusRequest,
    build_crystal_report,
    build_live_sequence_checkpoint,
    build_mr_seed_review,
    build_resource_summary,
    build_sequence_checkpoint,
    build_status_record,
    validate_mr_seed_approvals,
)
from genome_to_diffraction.schema_check import validate_repository
from genome_to_diffraction.schemas.io import (
    ContractError,
    InputFormat,
    contract_json_schema,
    contract_kinds,
    load_contract,
)
from genome_to_diffraction.status import GenomeToDiffractionError
from genome_to_diffraction.structure_search import (
    AfdbExactRequest,
    DisabledProviderBundleRequest,
    P1QualificationRequest,
    PdbCoordinateRegistrationRequest,
    PdbSequenceSearchRequest,
    ProstT5FoldseekSearchRequest,
    ProviderHitMergeRequest,
    ProviderPlanRequest,
    emit_disabled_provider_bundle,
    merge_pdb_provider_hits,
    qualify_p1_search,
    register_pdb_coordinates,
    resolve_provider_plan,
    search_afdb_exact,
    search_pdb_sequences,
    search_prostt5_foldseek,
)


def _add_contract_input(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("kind", choices=contract_kinds(), help="contract kind")
    parser.add_argument("input", type=Path, help="JSON, YAML, or supported TSV input")
    parser.add_argument(
        "--format",
        choices=("auto", "json", "yaml", "tsv"),
        default="auto",
        help="input format (default: infer from suffix)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="genome-to-diffraction")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="DEBUG, INFO, WARNING, ERROR, or CRITICAL",
    )
    parser.add_argument(
        "--log-format",
        choices=("human", "json"),
        default="human",
        help="diagnostic log rendering (default: human)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="disable tqdm progress bars",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    schema_parser = subparsers.add_parser(
        "schema-check", help="validate repository schemas and fixtures"
    )
    schema_parser.add_argument(
        "--repository",
        type=Path,
        default=Path.cwd(),
        help="repository root (default: current directory)",
    )

    contract_parser = subparsers.add_parser(
        "contract", help="validate or canonicalise a versioned contract"
    )
    contract_actions = contract_parser.add_subparsers(
        dest="contract_action", required=True
    )
    validate_parser = contract_actions.add_parser(
        "validate", help="validate a JSON, YAML, or supported TSV contract"
    )
    _add_contract_input(validate_parser)
    canonicalise_parser = contract_actions.add_parser(
        "canonicalise", help="write validated RFC 8785 canonical JSON"
    )
    _add_contract_input(canonicalise_parser)
    canonicalise_parser.add_argument(
        "--output",
        type=Path,
        help="output path (default: standard output)",
    )
    schema_output_parser = contract_actions.add_parser(
        "schema", help="write a Draft 2020-12 JSON Schema for a contract"
    )
    schema_output_parser.add_argument("kind", choices=contract_kinds())
    schema_output_parser.add_argument(
        "--output",
        type=Path,
        help="output path (default: standard output)",
    )

    phenix_parser = subparsers.add_parser(
        "phenix", help="install, verify, or execute the external Phenix runtime"
    )
    phenix_actions = phenix_parser.add_subparsers(dest="phenix_action", required=True)
    install_parser = phenix_actions.add_parser(
        "install", help="install a user-supplied Phenix command-line installer"
    )
    install_parser.add_argument(
        "--installer", type=Path, required=True, help="user-supplied installer file"
    )
    install_parser.add_argument(
        "--installer-sha256",
        required=True,
        help="expected full SHA-256 of the installer file",
    )
    install_parser.add_argument(
        "--prefix",
        type=Path,
        required=True,
        help="new absolute versioned prefix, such as /opt/phenix-2.1-XXXX",
    )
    install_parser.add_argument(
        "--expected-release",
        default="2.1",
        help="required PHENIX_VERSION release family (default: 2.1)",
    )
    install_parser.add_argument(
        "--expected-build", help="optional exact PHENIX_VERSION value"
    )
    install_parser.add_argument(
        "--temp-dir",
        type=Path,
        required=True,
        help="absolute executable temporary directory with at least 25 GiB free",
    )
    install_parser.add_argument(
        "--manifest", type=Path, required=True, help="new manifest output path"
    )
    install_parser.add_argument(
        "--current-link",
        type=Path,
        help="optional controlled symlink updated only after verification",
    )
    install_parser.add_argument(
        "--operator-note",
        action="append",
        default=[],
        help="repeatable provenance note stored in the manifest",
    )
    install_parser.add_argument(
        "--minimum-install-free-gb",
        type=float,
        default=15.0,
        help="minimum installation-filesystem free space (default: 15 GiB)",
    )
    install_parser.add_argument(
        "--minimum-temp-free-gb",
        type=float,
        default=25.0,
        help="minimum temporary-filesystem free space (default: 25 GiB)",
    )
    install_parser.add_argument(
        "--allow-home-root",
        action="store_true",
        help="allow the home root itself as an administrative target",
    )
    install_parser.add_argument(
        "--command-timeout-seconds",
        type=float,
        default=120.0,
        help="per-command smoke-test timeout (default: 120)",
    )

    verify_parser = phenix_actions.add_parser(
        "verify", help="revalidate a recorded Phenix installation manifest"
    )
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--verification-log", type=Path)
    verify_timeout = verify_parser.add_mutually_exclusive_group()
    verify_timeout.add_argument("--command-timeout-seconds", type=float)
    verify_timeout.add_argument(
        "--no-command-timeout",
        dest="command_timeout_seconds",
        action="store_const",
        const=None,
        help="allow runtime probes to complete without a per-command deadline",
    )
    verify_parser.set_defaults(command_timeout_seconds=120.0)

    refresh_parser = phenix_actions.add_parser(
        "refresh-manifest",
        help="write an executable-hashed successor for one verified legacy manifest",
    )
    refresh_parser.add_argument("--manifest", type=Path, required=True)
    refresh_parser.add_argument("--output", type=Path, required=True)
    refresh_parser.add_argument("--verification-log", type=Path)
    refresh_timeout = refresh_parser.add_mutually_exclusive_group()
    refresh_timeout.add_argument("--command-timeout-seconds", type=float)
    refresh_timeout.add_argument(
        "--no-command-timeout",
        dest="command_timeout_seconds",
        action="store_const",
        const=None,
    )
    refresh_parser.set_defaults(command_timeout_seconds=120.0)

    recover_parser = phenix_actions.add_parser(
        "recover-failed",
        help="requalify one exact installer-preserved failed Phenix tree",
    )
    recover_parser.add_argument("--failed-prefix", type=Path, required=True)
    recover_parser.add_argument("--prefix", type=Path, required=True)
    recover_parser.add_argument("--failed-manifest", type=Path, required=True)
    recover_parser.add_argument("--failed-manifest-sha256", required=True)
    recover_parser.add_argument("--manifest", type=Path, required=True)
    recover_parser.add_argument("--expected-release", default="2.1")
    recover_parser.add_argument("--expected-build", required=True)
    recover_parser.add_argument(
        "--tool-revision",
        required=True,
        help="full Git SHA of the reviewed recovery implementation",
    )
    recover_parser.add_argument("--current-link", type=Path, required=True)
    recover_parser.add_argument("--command-timeout-seconds", type=float, default=120.0)

    execute_parser = phenix_actions.add_parser(
        "exec", help="execute one command in an isolated verified Phenix shell"
    )
    execute_parser.add_argument("--manifest", type=Path, required=True)
    execute_parser.add_argument(
        "phenix_command",
        nargs=argparse.REMAINDER,
        help="exact command and arguments, conventionally after --",
    )

    interface_probe_parser = phenix_actions.add_parser(
        "probe-phaser-interface",
        help="capture the fixed installed phenix.phaser --show_defaults interface",
    )
    interface_probe_parser.add_argument("--manifest", type=Path, required=True)
    interface_probe_parser.add_argument("--outdir", type=Path, required=True)
    interface_probe_timeout = interface_probe_parser.add_mutually_exclusive_group()
    interface_probe_timeout.add_argument("--command-timeout-seconds", type=float)
    interface_probe_timeout.add_argument(
        "--no-command-timeout",
        dest="command_timeout_seconds",
        action="store_const",
        const=None,
    )
    interface_probe_parser.set_defaults(command_timeout_seconds=120.0)

    database_parser = subparsers.add_parser(
        "databases", help="prepare or verify shared reference databases"
    )
    database_actions = database_parser.add_subparsers(
        dest="database_action", required=True
    )
    source_parser = database_actions.add_parser(
        "stage-sources",
        help="download the fixed source bundle directly to durable storage",
    )
    source_parser.add_argument("--database-root", type=Path, required=True)
    source_parser.add_argument("--manifest", type=Path, required=True)
    source_parser.add_argument(
        "--storage-limit-bytes", type=int, default=DEFAULT_STORAGE_LIMIT_BYTES
    )
    source_parser.add_argument(
        "--minimum-free-bytes", type=int, default=DEFAULT_MINIMUM_FREE_BYTES
    )
    prepare_parser = database_actions.add_parser(
        "prepare", help="run explicit idempotent database preparation"
    )
    prepare_parser.add_argument("--database-root", type=Path, required=True)
    prepare_parser.add_argument("--manifest", type=Path, required=True)
    prepare_parser.add_argument("--prepare-pdb-foldseek", action="store_true")
    prepare_parser.add_argument("--prepare-pdb-sequences", action="store_true")
    prepare_parser.add_argument("--prepare-prostt5", action="store_true")
    prepare_parser.add_argument("--initialise-coordinate-cache", action="store_true")
    prepare_parser.add_argument("--verify-esm-atlas-connectivity", action="store_true")
    prepare_parser.add_argument("--verify-only", action="store_true")
    prepare_parser.add_argument("--force-rebuild", action="store_true")
    prepare_parser.add_argument("--full-verify", action="store_true")
    prepare_parser.add_argument(
        "--expected-manifest",
        type=Path,
        help="operator-frozen manifest required by verify-only",
    )
    prepare_parser.add_argument(
        "--expected-manifest-sha256",
        help="trusted SHA-256 of --expected-manifest",
    )
    prepare_parser.add_argument("--threads", type=int, default=4)
    prepare_parser.add_argument("--lock-timeout-seconds", type=float, default=30.0)
    prepare_parser.add_argument("--scratch-root", type=Path)
    prepare_parser.add_argument("--minimum-scratch-free-bytes", type=int, default=0)
    prepare_parser.add_argument(
        "--source-bundle",
        type=Path,
        help="verified durable source bundle for offline database preparation",
    )
    prepare_parser.add_argument(
        "--storage-limit-bytes", type=int, default=DEFAULT_STORAGE_LIMIT_BYTES
    )
    prepare_parser.add_argument(
        "--minimum-free-bytes", type=int, default=DEFAULT_MINIMUM_FREE_BYTES
    )
    prepare_parser.add_argument("--pdb-sequence-url", default=PDB_SEQUENCE_URL)
    prepare_parser.add_argument(
        "--pdb-coordinate-url-template", default=PDB_COORDINATE_URL_TEMPLATE
    )
    prepare_parser.add_argument("--esm-atlas-probe-url", default=ESM_ATLAS_PROBE_URL)
    preflight_parser = database_actions.add_parser(
        "preflight",
        help="validate compute-node capacity, scratch, tools, and fixed public routes",
    )
    preflight_parser.add_argument("--database-root", type=Path, required=True)
    preflight_parser.add_argument("--scratch-root", type=Path, required=True)
    preflight_parser.add_argument("--report", type=Path, required=True)
    preflight_parser.add_argument("--storage-limit-bytes", type=int, required=True)
    preflight_parser.add_argument("--minimum-free-bytes", type=int, required=True)
    preflight_parser.add_argument(
        "--required-database-capacity-bytes", type=int, required=True
    )
    preflight_parser.add_argument(
        "--minimum-scratch-free-bytes", type=int, required=True
    )
    preflight_parser.add_argument(
        "--source-bundle",
        type=Path,
        help="verified durable source bundle for a network-isolated compute node",
    )
    preflight_parser.add_argument("--probe-timeout-seconds", type=int, default=60)

    benchmark_parser = subparsers.add_parser(
        "benchmark", help="prepare checksum-frozen scientific controls"
    )
    benchmark_actions = benchmark_parser.add_subparsers(
        dest="benchmark_action", required=True
    )
    public_control_parser = benchmark_actions.add_parser(
        "prepare-public-control",
        help="prepare the tracked public MTZ positive control outside Git",
    )
    public_control_parser.add_argument("--specification", type=Path, required=True)
    public_control_input = public_control_parser.add_mutually_exclusive_group(
        required=True
    )
    public_control_input.add_argument("--proteome-faa", type=Path)
    public_control_input.add_argument(
        "--catalogue-manifest",
        type=Path,
        help="resolve the frozen proteome from one matching catalogue entry",
    )
    public_control_parser.add_argument("--outdir", type=Path, required=True)
    public_control_parser.add_argument(
        "--offline",
        action="store_true",
        help="verify existing source files without downloading missing files",
    )
    public_control_parser.add_argument("--storage-limit-mib", type=int, default=256)
    public_control_parser.add_argument("--minimum-free-mib", type=int, default=64)
    heteromer_control_parser = benchmark_actions.add_parser(
        "prepare-6rtz-heteromer-control",
        help="prepare the fixed public 6RTZ 1A+1B adapter-isolation inputs",
    )
    heteromer_control_parser.add_argument("--protocol", type=Path, required=True)
    heteromer_control_parser.add_argument("--coordinates", type=Path)
    heteromer_control_parser.add_argument("--structure-factors", type=Path)
    heteromer_control_parser.add_argument(
        "--download",
        action="store_true",
        help="download only the two protocol-frozen RCSB files",
    )
    heteromer_control_parser.add_argument("--outdir", type=Path, required=True)
    multicopy_control_parser = benchmark_actions.add_parser(
        "prepare-3u7q-heteromer-control",
        help="prepare the fixed public 3U7Q 2A+2B multi-copy inputs",
    )
    multicopy_control_parser.add_argument("--protocol", type=Path, required=True)
    multicopy_control_parser.add_argument("--coordinates", type=Path)
    multicopy_control_parser.add_argument("--structure-factors", type=Path)
    multicopy_control_parser.add_argument(
        "--download",
        action="store_true",
        help="download only the two protocol-frozen RCSB files",
    )
    multicopy_control_parser.add_argument("--outdir", type=Path, required=True)
    partner_catalogue_parser = benchmark_actions.add_parser(
        "prepare-6rtz-partner-catalogue",
        help="prepare the frozen full Thermotoga catalogue and HisH model registry",
    )
    partner_catalogue_parser.add_argument("--protocol", type=Path, required=True)
    partner_catalogue_parser.add_argument(
        "--control-preparation", type=Path, required=True
    )
    partner_catalogue_parser.add_argument("--proteome-faa", type=Path)
    partner_catalogue_parser.add_argument(
        "--download",
        action="store_true",
        help="download only the protocol-frozen NCBI catalogue bundle",
    )
    partner_catalogue_parser.add_argument("--outdir", type=Path, required=True)
    heteromer_review_parser = benchmark_actions.add_parser(
        "approve-6rtz-parent",
        help="build and approve the fixed HisF MR review checkpoint",
    )
    heteromer_review_parser.add_argument(
        "--preparation-manifest", type=Path, required=True
    )
    heteromer_review_parser.add_argument(
        "--parent-result-directory", type=Path, required=True
    )
    heteromer_review_parser.add_argument("--outdir", type=Path, required=True)
    heteromer_slice_prepare_parser = benchmark_actions.add_parser(
        "prepare-heteromer-control-slice",
        help="prepare the fixed missing-B, wrong-B, and 9ECN P6 controls",
    )
    heteromer_slice_prepare_parser.add_argument("--protocol", type=Path, required=True)
    heteromer_slice_prepare_parser.add_argument(
        "--control-6rtz-preparation", type=Path, required=True
    )
    heteromer_slice_prepare_parser.add_argument(
        "--control-3u7q-preparation", type=Path, required=True
    )
    heteromer_slice_prepare_parser.add_argument(
        "--catalogue-sequence-groups", type=Path, required=True
    )
    heteromer_slice_prepare_parser.add_argument("--outdir", type=Path, required=True)
    heteromer_slice_assess_parser = benchmark_actions.add_parser(
        "assess-heteromer-control-slice",
        help="assess the six fixed P6 controls",
    )
    heteromer_slice_assess_parser.add_argument(
        "--preparation-manifest", type=Path, required=True
    )
    heteromer_slice_assess_parser.add_argument(
        "--positive-6rtz-result", type=Path, required=True
    )
    heteromer_slice_assess_parser.add_argument(
        "--positive-3u7q-result", type=Path, required=True
    )
    heteromer_slice_assess_parser.add_argument(
        "--positive-3u7q-parent-result", type=Path, required=True
    )
    heteromer_slice_assess_parser.add_argument(
        "--catalogue-sequence-groups", type=Path, required=True
    )
    heteromer_slice_assess_parser.add_argument(
        "--missing-partner-plan", type=Path, required=True
    )
    heteromer_slice_assess_parser.add_argument(
        "--missing-partner-summary", type=Path, required=True
    )
    heteromer_slice_assess_parser.add_argument(
        "--wrong-partner-result", type=Path, required=True
    )
    heteromer_slice_assess_parser.add_argument(
        "--homomer-result", type=Path, required=True
    )
    heteromer_slice_assess_parser.add_argument("--output", type=Path, required=True)
    control_bundle_parser = benchmark_actions.add_parser(
        "build-first-copy-controls",
        help="build the fixed exact-positive and unrelated-negative MR bundle",
    )
    control_bundle_parser.add_argument("--specification", type=Path, required=True)
    control_bundle_parser.add_argument(
        "--public-control-preparation", type=Path, required=True
    )
    control_bundle_parser.add_argument("--database-manifest", type=Path, required=True)
    control_bundle_parser.add_argument("--sequence-groups", type=Path, required=True)
    control_bundle_parser.add_argument("--preflight", type=Path, required=True)
    control_bundle_parser.add_argument("--outdir", type=Path, required=True)
    control_slice_parser = benchmark_actions.add_parser(
        "run-control-slice",
        help="execute the fixed six-case Viper Phenix control slice",
    )
    control_slice_parser.add_argument("--import-root", type=Path, required=True)
    control_slice_parser.add_argument("--phenix-manifest", type=Path, required=True)
    control_slice_parser.add_argument("--outdir", type=Path, required=True)
    control_slice_parser.add_argument("--threads", type=int, default=8)
    control_matrix_parser = benchmark_actions.add_parser(
        "run-control-matrix",
        help="run the fixed 23-case prokaryotic homomer benchmark",
    )
    control_matrix_parser.add_argument("--import-root", type=Path, required=True)
    control_matrix_parser.add_argument("--phenix-manifest", type=Path, required=True)
    control_matrix_parser.add_argument("--outdir", type=Path, required=True)
    control_matrix_parser.add_argument("--threads", type=int, default=8)
    panel_check_parser = benchmark_actions.add_parser(
        "check-public-panel",
        help="validate the tracked public panel and active control mappings",
    )
    panel_check_parser.add_argument("--panel", type=Path, required=True)
    panel_prepare_parser = benchmark_actions.add_parser(
        "prepare-public-panel",
        help="download and verify public panel sources outside Git",
    )
    panel_prepare_parser.add_argument("--panel", type=Path, required=True)
    panel_prepare_parser.add_argument("--outdir", type=Path, required=True)
    panel_prepare_parser.add_argument(
        "--offline",
        action="store_true",
        help="verify existing panel sources without downloading missing files",
    )
    panel_prepare_parser.add_argument("--storage-limit-mib", type=int, default=1024)
    panel_prepare_parser.add_argument("--minimum-free-mib", type=int, default=128)
    m6_check_parser = benchmark_actions.add_parser(
        "check-m6-protocol",
        help="validate the approved truth-facing M6 protocol",
    )
    m6_check_parser.add_argument("--protocol", type=Path, required=True)
    m6_prepare_parser = benchmark_actions.add_parser(
        "prepare-m6-inputs",
        help="verify frozen sources and prepare sanitised M6 runner inputs",
    )
    m6_prepare_parser.add_argument("--protocol", type=Path, required=True)
    m6_prepare_parser.add_argument("--rcsb-root", type=Path, required=True)
    m6_prepare_parser.add_argument(
        "--catalogue-root",
        type=Path,
        action="append",
        required=True,
        help="repeatable NCBI Datasets extraction root",
    )
    m6_prepare_parser.add_argument("--outdir", type=Path, required=True)
    m6_runner_parser = benchmark_actions.add_parser(
        "build-m6-runner",
        help="build a deterministic truth-isolated M6 runner archive",
    )
    m6_runner_parser.add_argument("--protocol", type=Path, required=True)
    m6_runner_parser.add_argument("--preparation-manifest", type=Path, required=True)
    m6_runner_parser.add_argument("--outdir", type=Path, required=True)
    m6_runner_parser.add_argument("--archive", type=Path, required=True)
    m6_verify_parser = benchmark_actions.add_parser(
        "verify-m6-runner",
        help="verify an extracted truth-isolated M6 runner bundle",
    )
    m6_verify_parser.add_argument("--runner-root", type=Path, required=True)
    m6_verify_parser.add_argument("--report", type=Path, required=True)
    m6_scientific_parser = benchmark_actions.add_parser(
        "run-m6-scientific",
        help="reject legacy monolithic execution; retained for CLI compatibility",
    )
    m6_scientific_parser.add_argument("--runner-root", type=Path, required=True)
    m6_scientific_parser.add_argument("--protocol", type=Path, required=True)
    m6_scientific_parser.add_argument("--database-manifest", type=Path, required=True)
    m6_scientific_parser.add_argument("--phenix-manifest", type=Path, required=True)
    m6_scientific_parser.add_argument(
        "--track", choices=("operational", "leakage"), required=True
    )
    m6_scientific_parser.add_argument("--outdir", type=Path, required=True)
    m6_scientific_parser.add_argument("--threads", type=int, default=8)
    m6_scientific_parser.add_argument(
        "--maximum-concurrent-phenix-attempts", type=int, default=4
    )
    m6_scientific_parser.add_argument(
        "--resume",
        action="store_true",
        help="verify and reuse a complete checksum-matching track output",
    )
    m6_plan_nf = benchmark_actions.add_parser(
        "plan-m6-nextflow", help="materialise one truthless M6 Nextflow task graph"
    )
    m6_plan_nf.add_argument("--runner-root", type=Path, required=True)
    m6_plan_nf.add_argument("--database-manifest", type=Path, required=True)
    m6_plan_nf.add_argument("--software-lock", type=Path, required=True)
    m6_plan_nf.add_argument(
        "--track", choices=("operational", "leakage"), required=True
    )
    m6_plan_nf.add_argument("--outdir", type=Path, required=True)
    m6_import_task = benchmark_actions.add_parser(
        "run-m6-catalogue-task", help="import one M6 catalogue channel item"
    )
    m6_import_task.add_argument("--task", type=Path, required=True)
    m6_import_task.add_argument("--software-lock", type=Path, required=True)
    m6_import_task.add_argument("--outdir", type=Path, required=True)
    m6_batch_task = benchmark_actions.add_parser(
        "build-m6-search-batches",
        help="deduplicate imported catalogues into bounded search batches",
    )
    m6_batch_task.add_argument(
        "--catalogue-bundle", type=Path, action="append", required=True
    )
    m6_batch_task.add_argument("--database-manifest", type=Path, required=True)
    m6_batch_task.add_argument("--execution-policy", type=Path, required=True)
    m6_batch_task.add_argument("--software-lock", type=Path, required=True)
    m6_batch_task.add_argument("--outdir", type=Path, required=True)
    m6_pdb_task = benchmark_actions.add_parser(
        "run-m6-pdb-task", help="search one bounded M6 query batch with MMseqs2"
    )
    m6_pdb_task.add_argument("--batch-task", type=Path, required=True)
    m6_pdb_task.add_argument("--database-manifest", type=Path, required=True)
    m6_pdb_task.add_argument("--execution-policy", type=Path, required=True)
    m6_pdb_task.add_argument("--software-lock", type=Path, required=True)
    m6_pdb_task.add_argument("--threads", type=int, required=True)
    m6_pdb_task.add_argument("--outdir", type=Path, required=True)
    m6_foldseek_task = benchmark_actions.add_parser(
        "run-m6-foldseek-task", help="search one bounded M6 query batch with Foldseek"
    )
    m6_foldseek_task.add_argument("--batch-task", type=Path, required=True)
    m6_foldseek_task.add_argument("--database-manifest", type=Path, required=True)
    m6_foldseek_task.add_argument("--execution-policy", type=Path, required=True)
    m6_foldseek_task.add_argument("--software-lock", type=Path, required=True)
    m6_foldseek_task.add_argument("--threads", type=int, required=True)
    m6_foldseek_task.add_argument("--outdir", type=Path, required=True)
    m6_partition_task = benchmark_actions.add_parser(
        "partition-m6-discovery",
        help="partition global search batches back into one catalogue",
    )
    m6_partition_task.add_argument("--catalogue-bundle", type=Path, required=True)
    m6_partition_task.add_argument("--batch-plan", type=Path, required=True)
    m6_partition_task.add_argument(
        "--pdb-result", type=Path, action="append", required=True
    )
    m6_partition_task.add_argument(
        "--foldseek-result", type=Path, action="append", required=True
    )
    m6_partition_task.add_argument("--outdir", type=Path, required=True)
    m6_preflight_task = benchmark_actions.add_parser(
        "run-m6-preflight-task", help="preflight one opaque M6 case"
    )
    m6_preflight_task.add_argument("--task", type=Path, required=True)
    m6_preflight_task.add_argument("--phenix-manifest", type=Path, required=True)
    m6_preflight_task.add_argument("--outdir", type=Path, required=True)
    m6_policy_task = benchmark_actions.add_parser(
        "run-m6-policy-task", help="apply trusted model policy to one M6 case"
    )
    m6_policy_task.add_argument("--task", type=Path, required=True)
    m6_policy_task.add_argument("--catalogue-bundle", type=Path, required=True)
    m6_policy_task.add_argument("--pdb-bundle", type=Path, required=True)
    m6_policy_task.add_argument("--foldseek-bundle", type=Path, required=True)
    m6_policy_task.add_argument("--protocol", type=Path, required=True)
    m6_policy_task.add_argument("--database-manifest", type=Path, required=True)
    m6_policy_task.add_argument("--outdir", type=Path, required=True)
    m6_case_task = benchmark_actions.add_parser(
        "run-m6-case-task", help="prepare one blind M6 case and its hypotheses"
    )
    m6_case_task.add_argument("--task", type=Path, required=True)
    m6_case_task.add_argument("--preflight-bundle", type=Path, required=True)
    m6_case_task.add_argument("--catalogue-bundle", type=Path, required=True)
    m6_case_task.add_argument("--policy-bundle", type=Path)
    m6_case_task.add_argument("--database-manifest", type=Path, required=True)
    m6_case_task.add_argument("--outdir", type=Path, required=True)
    m6_seed_task = benchmark_actions.add_parser(
        "select-m6-seeds", help="select retained first-copy seeds for one M6 case"
    )
    m6_seed_task.add_argument("--case-bundle", type=Path, required=True)
    m6_seed_task.add_argument(
        "--first-copy-result", type=Path, action="append", default=[]
    )
    m6_seed_task.add_argument("--outdir", type=Path, required=True)
    m6_empty_seed_task = benchmark_actions.add_parser(
        "empty-m6-seeds", help="emit an explicit zero-hypothesis M6 seed bundle"
    )
    m6_empty_seed_task.add_argument("--case-bundle", type=Path, required=True)
    m6_empty_seed_task.add_argument("--outdir", type=Path, required=True)
    m6_copy_task = benchmark_actions.add_parser(
        "run-m6-add-copy-task", help="run one retained M6 copy chain"
    )
    m6_copy_task.add_argument("--case-bundle", type=Path, required=True)
    m6_copy_task.add_argument("--seed-bundle", type=Path, required=True)
    m6_copy_task.add_argument("--seed-solution-id", required=True)
    m6_copy_task.add_argument("--phenix-manifest", type=Path, required=True)
    m6_copy_task.add_argument("--threads", type=int, required=True)
    m6_copy_task.add_argument("--outdir", type=Path, required=True)
    m6_finalist_task = benchmark_actions.add_parser(
        "select-m6-finalists", help="select retained parents for one M6 case"
    )
    m6_finalist_task.add_argument("--case-bundle", type=Path, required=True)
    m6_finalist_task.add_argument("--seed-bundle", type=Path, required=True)
    m6_finalist_task.add_argument(
        "--add-copy-result", type=Path, action="append", default=[]
    )
    m6_finalist_task.add_argument("--outdir", type=Path, required=True)
    m6_empty_finalist = benchmark_actions.add_parser(
        "empty-m6-finalists", help="emit an explicit zero-seed M6 finalist bundle"
    )
    m6_empty_finalist.add_argument("--case-bundle", type=Path, required=True)
    m6_empty_finalist.add_argument("--seed-bundle", type=Path, required=True)
    m6_empty_finalist.add_argument("--outdir", type=Path, required=True)
    m6_refinement_task = benchmark_actions.add_parser(
        "run-m6-refinement-task", help="refine and sequence-assess one M6 finalist"
    )
    m6_refinement_task.add_argument("--finalist-bundle", type=Path, required=True)
    m6_refinement_task.add_argument("--seed-solution-id", required=True)
    m6_refinement_task.add_argument("--phenix-manifest", type=Path, required=True)
    m6_refinement_task.add_argument("--threads", type=int, required=True)
    m6_refinement_task.add_argument("--outdir", type=Path, required=True)
    m6_case_evidence = benchmark_actions.add_parser(
        "assemble-m6-case", help="assemble one complete M6 case evidence bundle"
    )
    m6_case_evidence.add_argument("--case-bundle", type=Path, required=True)
    m6_case_evidence.add_argument("--finalist-bundle", type=Path, required=True)
    m6_case_evidence.add_argument(
        "--refinement-result", type=Path, action="append", default=[]
    )
    m6_case_evidence.add_argument("--outdir", type=Path, required=True)
    m6_track_evidence = benchmark_actions.add_parser(
        "aggregate-m6-track", help="aggregate a complete Nextflow M6 track"
    )
    m6_track_evidence.add_argument(
        "--case-evidence", type=Path, action="append", required=True
    )
    m6_track_evidence.add_argument("--runner-root", type=Path, required=True)
    m6_track_evidence.add_argument("--protocol", type=Path, required=True)
    m6_track_evidence.add_argument("--database-manifest", type=Path, required=True)
    m6_track_evidence.add_argument("--phenix-manifest", type=Path, required=True)
    m6_track_evidence.add_argument(
        "--track", choices=("operational", "leakage"), required=True
    )
    m6_track_evidence.add_argument("--outdir", type=Path, required=True)
    m6_resources = benchmark_actions.add_parser(
        "collect-m6-resources", help="derive M6 child-job resource evidence"
    )
    m6_resources.add_argument("--execution-policy", type=Path, required=True)
    m6_resources.add_argument("--trace", type=Path, required=True)
    m6_resources.add_argument("--output", type=Path, required=True)
    m6_evaluate_parser = benchmark_actions.add_parser(
        "evaluate-m6",
        help="evaluate collected M6 evidence against the frozen gates",
    )
    m6_evaluate_parser.add_argument("--protocol", type=Path, required=True)
    m6_evaluate_parser.add_argument("--evidence", type=Path, required=True)
    m6_evaluate_parser.add_argument("--report", type=Path, required=True)
    m6_collect_parser = benchmark_actions.add_parser(
        "collect-m6-evidence",
        help="verify and truth-join two collected M6 scientific tracks",
    )
    m6_collect_parser.add_argument("--protocol", type=Path, required=True)
    m6_collect_parser.add_argument("--private-truth-map", type=Path, required=True)
    m6_collect_parser.add_argument("--operational-collection", type=Path, required=True)
    m6_collect_parser.add_argument("--leakage-collection", type=Path, required=True)
    m6_collect_parser.add_argument("--output", type=Path, required=True)

    catalogue_parser = subparsers.add_parser(
        "catalogue", help="normalise trusted protein catalogues"
    )
    catalogue_actions = catalogue_parser.add_subparsers(
        dest="catalogue_action", required=True
    )
    import_parser = catalogue_actions.add_parser(
        "import", help="import, deduplicate, and inventory trusted catalogues"
    )
    import_parser.add_argument(
        "--catalogues", type=Path, required=True, help="catalogue manifest"
    )
    import_parser.add_argument(
        "--config", type=Path, required=True, help="pipeline configuration"
    )
    import_parser.add_argument(
        "--outdir", type=Path, required=True, help="stable output directory"
    )

    localisation_parser = subparsers.add_parser(
        "localisation", help="run checksum-bound offline localisation policy"
    )
    localisation_actions = localisation_parser.add_subparsers(
        dest="localisation_action", required=True
    )
    localisation_tasks_parser = localisation_actions.add_parser(
        "build-tasks", help="emit one offline task per exact sequence group"
    )
    localisation_tasks_parser.add_argument(
        "--sequence-groups", type=Path, required=True
    )
    localisation_tasks_parser.add_argument("--psortb-runtime", type=Path, required=True)
    localisation_tasks_parser.add_argument(
        "--deeptmhmm-runtime", type=Path, required=True
    )
    localisation_tasks_parser.add_argument("--outdir", type=Path, required=True)
    localisation_run_parser = localisation_actions.add_parser(
        "run-task", help="run one PSORTb item and retain blocked DeepTMHMM"
    )
    localisation_run_parser.add_argument("--task-directory", type=Path, required=True)
    localisation_run_parser.add_argument("--psortb-runtime", type=Path, required=True)
    localisation_run_parser.add_argument(
        "--deeptmhmm-runtime", type=Path, required=True
    )
    localisation_run_parser.add_argument("--outdir", type=Path, required=True)
    localisation_policy_parser = localisation_actions.add_parser(
        "build-wave-policy",
        help="merge exact per-group results into first-wave decisions",
    )
    localisation_policy_parser.add_argument(
        "--task-inventory", type=Path, required=True
    )
    localisation_policy_parser.add_argument(
        "--result-directory", type=Path, action="append", default=[]
    )
    localisation_policy_parser.add_argument("--outdir", type=Path, required=True)
    localisation_reopen_parser = localisation_actions.add_parser(
        "plan-reopen", help="reopen excluded groups only after a zero-pack wave"
    )
    localisation_reopen_parser.add_argument("--wave-policy", type=Path, required=True)
    localisation_reopen_parser.add_argument(
        "--active-wave-completion", type=Path, required=True
    )
    localisation_reopen_parser.add_argument("--outdir", type=Path, required=True)

    diffraction_parser = subparsers.add_parser(
        "diffraction", help="inspect crystallographic diffraction inputs"
    )
    diffraction_actions = diffraction_parser.add_subparsers(
        dest="diffraction_action", required=True
    )
    preflight_parser = diffraction_actions.add_parser(
        "preflight", help="inspect MTZ files and optionally run Phenix Xtriage"
    )
    preflight_parser.add_argument("--crystals", type=Path, required=True)
    preflight_parser.add_argument("--phenix-manifest", type=Path)
    preflight_parser.add_argument("--outdir", type=Path, required=True)
    preflight_parser.add_argument(
        "--skip-xtriage",
        action="store_true",
        help="skip Xtriage and force pass-with-review (testing/preparation only)",
    )
    xtriage_timeout = preflight_parser.add_mutually_exclusive_group()
    xtriage_timeout.add_argument(
        "--xtriage-timeout-seconds", type=float, dest="xtriage_timeout_seconds"
    )
    xtriage_timeout.add_argument(
        "--no-xtriage-timeout",
        action="store_const",
        const=None,
        dest="xtriage_timeout_seconds",
        help="allow Xtriage to run without a command deadline",
    )
    preflight_parser.set_defaults(xtriage_timeout_seconds=3600.0)
    free_r_parser = diffraction_actions.add_parser(
        "generate-free-r",
        help="create one immutable Free-R derivative with verified Phenix",
    )
    free_r_parser.add_argument("--source-mtz", type=Path, required=True)
    free_r_parser.add_argument("--output-mtz", type=Path, required=True)
    free_r_parser.add_argument("--phenix-manifest", type=Path, required=True)
    free_r_parser.add_argument("--command-log", type=Path, required=True)
    free_r_parser.add_argument("--record", type=Path, required=True)
    free_r_parser.add_argument("--test-fraction", type=float, default=0.05)
    free_r_parser.add_argument("--maximum-free-reflections", type=int, default=2000)
    free_r_parser.add_argument("--random-seed", type=int, default=20260801)
    free_r_parser.add_argument("--timeout-seconds", type=float, default=3600.0)
    dispatch_parser = diffraction_actions.add_parser(
        "select-single",
        help="derive one checksum-verified MR input from a crystal manifest",
    )
    dispatch_parser.add_argument("--crystals", type=Path, required=True)
    dispatch_parser.add_argument("--preflight", type=Path, required=True)
    dispatch_parser.add_argument("--outdir", type=Path, required=True)
    dispatch_parser.add_argument(
        "--crystal-id",
        help=(
            "manifest-owned crystal to dispatch; required when the manifest "
            "contains more than one crystal"
        ),
    )

    matthews_parser = subparsers.add_parser(
        "matthews", help="enumerate candidate-specific ASU copy hypotheses"
    )
    matthews_actions = matthews_parser.add_subparsers(
        dest="matthews_action", required=True
    )
    enumerate_parser = matthews_actions.add_parser(
        "enumerate", help="calculate Matthews and soft SDS-PAGE priors"
    )
    enumerate_parser.add_argument("--crystals", type=Path, required=True)
    enumerate_parser.add_argument("--config", type=Path, required=True)
    enumerate_parser.add_argument("--preflight", type=Path, required=True)
    enumerate_parser.add_argument("--sequence-groups", type=Path, required=True)
    enumerate_parser.add_argument("--source-records", type=Path, required=True)
    enumerate_parser.add_argument("--outdir", type=Path, required=True)
    reference_parser = matthews_actions.add_parser(
        "reference-check",
        help="compare one exact-mass hypothesis with fixed local Phenix Matthews",
    )
    reference_parser.add_argument("--crystals", type=Path, required=True)
    reference_parser.add_argument("--config", type=Path, required=True)
    reference_parser.add_argument("--preflight", type=Path, required=True)
    reference_parser.add_argument("--sequence-groups", type=Path, required=True)
    reference_parser.add_argument("--source-records", type=Path, required=True)
    reference_parser.add_argument("--phenix-manifest", type=Path, required=True)
    reference_parser.add_argument("--crystal-id", required=True)
    reference_parser.add_argument("--sequence-group-id", required=True)
    reference_parser.add_argument("--outdir", type=Path, required=True)
    reference_parser.add_argument("--timeout-seconds", type=float, default=600.0)

    model_parser = subparsers.add_parser(
        "model", help="prepare integrity-checked molecular-replacement models"
    )
    model_actions = model_parser.add_subparsers(dest="model_action", required=True)
    predicted_parser = model_actions.add_parser(
        "prepare-predicted",
        help="confidence-process selected AFDB/Atlas coordinates with Phenix",
    )
    predicted_parser.add_argument("--coordinate-sources", type=Path, required=True)
    predicted_parser.add_argument("--sequence-groups", type=Path, required=True)
    predicted_parser.add_argument("--phenix-manifest", type=Path, required=True)
    predicted_parser.add_argument("--outdir", type=Path, required=True)
    predicted_parser.add_argument(
        "--coordinate-id",
        action="append",
        default=[],
        help="repeatable coordinate ID; by default process all predicted sources",
    )
    predicted_parser.add_argument(
        "--timeout-seconds",
        type=float,
        help="optional explicit Phenix deadline; by default no deadline is imposed",
    )
    experimental_parser = model_actions.add_parser(
        "prepare-experimental",
        help="prepare one cleaned PDB source-chain model per registered mapping",
    )
    experimental_parser.add_argument("--coordinate-sources", type=Path, required=True)
    experimental_parser.add_argument(
        "--coordinate-hit-mappings", type=Path, required=True
    )
    experimental_parser.add_argument("--sequence-groups", type=Path, required=True)
    experimental_parser.add_argument("--outdir", type=Path, required=True)
    experimental_parser.add_argument(
        "--mapping-id",
        action="append",
        default=[],
        help="repeatable mapping ID; by default process every registered mapping",
    )

    ranking_parser = subparsers.add_parser(
        "ranking", help="build inspectable, hard-capped candidate funnels"
    )
    ranking_actions = ranking_parser.add_subparsers(
        dest="ranking_action", required=True
    )
    exact_predicted_parser = ranking_actions.add_parser(
        "exact-predicted-funnel",
        help="join exact predicted models to physical copy hypotheses",
    )
    exact_predicted_parser.add_argument(
        "--coordinate-sources", type=Path, required=True
    )
    exact_predicted_parser.add_argument("--processed-models", type=Path, required=True)
    exact_predicted_parser.add_argument(
        "--model-preparation-manifest", type=Path, required=True
    )
    exact_predicted_parser.add_argument("--sequence-groups", type=Path, required=True)
    exact_predicted_parser.add_argument("--matthews", type=Path, required=True)
    exact_predicted_parser.add_argument("--preflight", type=Path, required=True)
    exact_predicted_parser.add_argument("--config", type=Path, required=True)
    exact_predicted_parser.add_argument("--outdir", type=Path, required=True)
    exact_predicted_parser.add_argument(
        "--crystal-id",
        action="append",
        default=[],
        help="repeatable crystal ID; by default use all supplied preflights",
    )
    diverse_parser = ranking_actions.add_parser(
        "diverse-first-copy-funnel",
        help="join predicted and experimental models under hard diversity caps",
    )
    diverse_parser.add_argument(
        "--coordinate-sources", type=Path, action="append", required=True
    )
    diverse_parser.add_argument(
        "--processed-models", type=Path, action="append", required=True
    )
    diverse_parser.add_argument(
        "--model-preparation-manifest", type=Path, action="append", required=True
    )
    diverse_parser.add_argument("--coordinate-hit-mappings", type=Path)
    diverse_parser.add_argument("--sequence-groups", type=Path, required=True)
    diverse_parser.add_argument("--matthews", type=Path, required=True)
    diverse_parser.add_argument("--preflight", type=Path, required=True)
    diverse_parser.add_argument("--config", type=Path, required=True)
    diverse_parser.add_argument("--outdir", type=Path, required=True)
    diverse_parser.add_argument(
        "--crystal-id",
        action="append",
        default=[],
        help="repeatable crystal ID; by default use all supplied preflights",
    )
    diverse_parser.add_argument(
        "--maximum-first-copy-jobs",
        type=int,
        help="optional additional hard cap applied after configured profile limits",
    )
    partner_plan_parser = ranking_actions.add_parser(
        "partner-plan",
        help="select the fixed first wave of at most 25 catalogue B candidates",
    )
    partner_plan_parser.add_argument("--crystal-id", required=True)
    partner_plan_parser.add_argument("--parent-sequence-group-id", required=True)
    partner_plan_parser.add_argument("--parent-copy-count", type=int, required=True)
    partner_plan_parser.add_argument("--partner-copy-count", type=int, required=True)
    partner_plan_parser.add_argument("--sequence-groups", type=Path, required=True)
    partner_plan_parser.add_argument("--matthews", type=Path, required=True)
    partner_plan_parser.add_argument("--preflight", type=Path, required=True)
    partner_plan_parser.add_argument("--config", type=Path, required=True)
    partner_plan_parser.add_argument("--model-registry", type=Path, required=True)
    partner_plan_parser.add_argument("--outdir", type=Path, required=True)
    approved_partner_plan_parser = ranking_actions.add_parser(
        "approved-partner-plan",
        help="select catalogue B candidates from one approved retained A state",
    )
    approved_partner_plan_parser.add_argument(
        "--approved-stage", type=Path, required=True
    )
    approved_partner_plan_parser.add_argument("--crystal-id", required=True)
    approved_partner_plan_parser.add_argument(
        "--partner-copy-count", type=int, required=True
    )
    approved_partner_plan_parser.add_argument(
        "--sequence-groups", type=Path, required=True
    )
    approved_partner_plan_parser.add_argument("--matthews", type=Path, required=True)
    approved_partner_plan_parser.add_argument("--preflight", type=Path, required=True)
    approved_partner_plan_parser.add_argument("--config", type=Path, required=True)
    approved_partner_plan_parser.add_argument(
        "--model-registry", type=Path, required=True
    )
    approved_partner_plan_parser.add_argument("--outdir", type=Path, required=True)

    mr_parser = subparsers.add_parser(
        "mr", help="execute bounded molecular-replacement hypotheses"
    )
    mr_actions = mr_parser.add_subparsers(dest="mr_action", required=True)
    first_copy_parser = mr_actions.add_parser(
        "first-copy",
        help="run one registered independent first-copy Phaser search",
    )
    first_copy_parser.add_argument("--hypotheses", type=Path, required=True)
    first_copy_parser.add_argument("--hypothesis-id", required=True)
    first_copy_parser.add_argument("--sequence-groups", type=Path, required=True)
    first_copy_parser.add_argument("--processed-models", type=Path, required=True)
    first_copy_parser.add_argument(
        "--model-preparation-manifest", type=Path, required=True
    )
    first_copy_parser.add_argument("--preflight", type=Path, required=True)
    first_copy_parser.add_argument("--mtz", type=Path, required=True)
    first_copy_parser.add_argument(
        "--diffraction-selection",
        type=Path,
        help="optional schema-v2 dataset-qualified diffraction selection",
    )
    first_copy_parser.add_argument(
        "--phase3-hypothesis-id",
        help="content identity binding the v1 hypothesis to --diffraction-selection",
    )
    first_copy_parser.add_argument("--phenix-manifest", type=Path, required=True)
    first_copy_parser.add_argument("--outdir", type=Path, required=True)
    first_copy_parser.add_argument("--threads", type=int, default=1)
    first_copy_parser.add_argument(
        "--timeout-seconds",
        type=float,
        help="optional explicit Phaser deadline; by default no deadline is imposed",
    )
    add_copy_parser = mr_actions.add_parser(
        "add-copy",
        help="fix one approved MR seed and search one additional same-component copy",
    )
    add_copy_parser.add_argument("--review-validation", type=Path, required=True)
    add_copy_parser.add_argument("--review-package-manifest", type=Path, required=True)
    add_copy_parser.add_argument("--seed-solution-id", required=True)
    add_copy_parser.add_argument("--hypotheses", type=Path, required=True)
    add_copy_parser.add_argument("--sequence-groups", type=Path, required=True)
    add_copy_parser.add_argument("--preflight", type=Path, required=True)
    add_copy_parser.add_argument("--mtz", type=Path, required=True)
    add_copy_parser.add_argument("--search-model", type=Path, required=True)
    add_copy_parser.add_argument("--expected-search-model-sha256")
    add_copy_parser.add_argument("--phenix-manifest", type=Path, required=True)
    add_copy_parser.add_argument("--outdir", type=Path, required=True)
    add_copy_parser.add_argument(
        "--parent-result",
        type=Path,
        help="supported prior additional-copy JSONL for copy 3..n",
    )
    add_copy_parser.add_argument(
        "--parent-coordinate",
        type=Path,
        help="checksum-matched coordinate from --parent-result",
    )
    add_copy_parser.add_argument(
        "--until-expected",
        action="store_true",
        help="advance one supported copy at a time to expected n or first stop",
    )
    add_copy_parser.add_argument("--threads", type=int, default=1)
    add_copy_parser.add_argument(
        "--timeout-seconds",
        type=float,
        help="optional explicit Phaser deadline; by default no deadline is imposed",
    )
    partner_parser = mr_actions.add_parser(
        "search-partner",
        help="fix one A solution and search exactly one B component",
    )
    partner_parser.add_argument("--crystal-id", required=True)
    partner_parser.add_argument("--parent-solution-id", required=True)
    partner_parser.add_argument("--parent-sequence-group-id", required=True)
    partner_parser.add_argument("--partner-sequence-group-id", required=True)
    partner_parser.add_argument("--sequence-groups", type=Path, required=True)
    partner_parser.add_argument("--parent-coordinate", type=Path, required=True)
    partner_parser.add_argument("--expected-parent-coordinate-sha256", required=True)
    partner_parser.add_argument("--parent-llg", type=float, required=True)
    partner_parser.add_argument(
        "--parent-model-identity-fraction", type=float, required=True
    )
    partner_parser.add_argument("--parent-model-uncertainty-source", required=True)
    partner_parser.add_argument("--parent-copy-count", type=int, default=1)
    partner_parser.add_argument("--partner-model", type=Path, required=True)
    partner_parser.add_argument("--expected-partner-model-sha256", required=True)
    partner_parser.add_argument(
        "--partner-model-identity-fraction", type=float, required=True
    )
    partner_parser.add_argument("--partner-copy-count", type=int, default=1)
    approved_partner_parser = mr_actions.add_parser(
        "approved-partner",
        help="search fixed 6RTZ B from one explicitly approved workflow A seed",
    )
    approved_partner_parser.add_argument("--approved-stage", type=Path, required=True)
    approved_partner_parser.add_argument("--review-package", type=Path, required=True)
    approved_partner_parser.add_argument(
        "--control-preparation", type=Path, required=True
    )
    approved_partner_parser.add_argument("--sequence-groups", type=Path, required=True)
    approved_partner_parser.add_argument("--preflight", type=Path, required=True)
    approved_partner_parser.add_argument("--mtz", type=Path, required=True)
    approved_partner_parser.add_argument("--phenix-manifest", type=Path, required=True)
    approved_partner_parser.add_argument("--outdir", type=Path, required=True)
    approved_partner_parser.add_argument("--threads", type=int, default=1)
    approved_partner_parser.add_argument("--timeout-seconds", type=float)
    planned_partner_parser = mr_actions.add_parser(
        "planned-partner",
        help="run one selected catalogue B candidate from an approved A state",
    )
    planned_partner_parser.add_argument("--approved-stage", type=Path, required=True)
    planned_partner_parser.add_argument("--review-package", type=Path, required=True)
    planned_partner_parser.add_argument("--partner-plan", type=Path, required=True)
    planned_partner_parser.add_argument("--partner-candidate-id", required=True)
    planned_partner_parser.add_argument("--sequence-groups", type=Path, required=True)
    planned_partner_parser.add_argument("--model-registry", type=Path, required=True)
    planned_partner_parser.add_argument("--preflight", type=Path, required=True)
    planned_partner_parser.add_argument("--mtz", type=Path, required=True)
    planned_partner_parser.add_argument("--phenix-manifest", type=Path, required=True)
    planned_partner_parser.add_argument("--outdir", type=Path, required=True)
    planned_partner_parser.add_argument("--threads", type=int, default=1)
    planned_partner_parser.add_argument("--timeout-seconds", type=float)
    partner_summary_parser = mr_actions.add_parser(
        "summarize-partners",
        help="require and count every terminal result from one partner plan",
    )
    partner_summary_parser.add_argument("--partner-plan", type=Path, required=True)
    partner_summary_parser.add_argument(
        "--result-directory", type=Path, action="append", default=[]
    )
    partner_summary_parser.add_argument("--output", type=Path, required=True)
    partner_parser.add_argument("--preflight", type=Path, required=True)
    partner_parser.add_argument("--mtz", type=Path, required=True)
    partner_parser.add_argument("--phenix-manifest", type=Path, required=True)
    partner_parser.add_argument("--outdir", type=Path, required=True)
    partner_parser.add_argument("--threads", type=int, default=1)
    partner_parser.add_argument(
        "--timeout-seconds",
        type=float,
        help="optional explicit Phaser deadline; by default no deadline is imposed",
    )
    stage_add_copy_parser = mr_actions.add_parser(
        "stage-add-copy",
        help="prepare checksum-bound comparative M4 inputs from a retained run",
    )
    stage_add_copy_parser.add_argument("--parent-run", type=Path, required=True)
    stage_add_copy_parser.add_argument("--decisions", type=Path, required=True)
    stage_add_copy_parser.add_argument("--review-manifest-sha256", required=True)
    stage_add_copy_parser.add_argument("--mtz", type=Path, required=True)
    stage_add_copy_parser.add_argument("--phenix-manifest", type=Path, required=True)
    stage_add_copy_parser.add_argument("--outdir", type=Path, required=True)
    stage_add_copy_parser.add_argument("--expected-seed-count", type=int, default=11)
    stage_add_copy_parser.add_argument(
        "--use-solution-coordinates-as-models",
        action="store_true",
        help=(
            "cross-site mode: derive search models from rigid-body transformed "
            "first-copy solution coordinates"
        ),
    )
    stage_add_copy_parser.add_argument("--source-site-id")
    live_stage_parser = mr_actions.add_parser(
        "stage-approved-seeds",
        help=("validate a normal-workflow MR checkpoint and stage every approved seed"),
    )
    live_stage_parser.add_argument("--review-package", type=Path, required=True)
    live_stage_parser.add_argument("--decisions", type=Path, required=True)
    live_stage_parser.add_argument("--hypotheses", type=Path, required=True)
    live_stage_parser.add_argument("--outdir", type=Path, required=True)
    copy_report_parser = mr_actions.add_parser(
        "copy-report",
        help="compare Matthews-intended and empirically supported copy counts",
    )
    copy_report_parser.add_argument("--results", type=Path, required=True)
    copy_report_parser.add_argument("--outdir", type=Path, required=True)

    refinement_parser = subparsers.add_parser(
        "refinement", help="run fixed finalist refinement and sequence assessment"
    )
    refinement_actions = refinement_parser.add_subparsers(
        dest="refinement_action", required=True
    )
    brief_parser = refinement_actions.add_parser(
        "brief", help="run the fixed T12 brief-refinement/map/sequence protocol"
    )
    brief_parser.add_argument("--seed-solution-id", required=True)
    brief_parser.add_argument("--sequence-group-id", required=True)
    brief_parser.add_argument("--input-copy-count", type=int, required=True)
    brief_parser.add_argument("--parent-coordinate", type=Path, required=True)
    brief_parser.add_argument("--parent-coordinate-sha256", required=True)
    brief_parser.add_argument("--parent-mtz", type=Path, required=True)
    brief_parser.add_argument("--parent-mtz-sha256", required=True)
    brief_parser.add_argument("--observation-labels", required=True)
    brief_parser.add_argument("--sequence-groups", type=Path, required=True)
    brief_parser.add_argument("--source-records", type=Path, required=True)
    brief_parser.add_argument("--resolution", type=float, required=True)
    brief_parser.add_argument(
        "--crystal-id",
        help="required with --diffraction-selection for Phase III refinement",
    )
    brief_parser.add_argument(
        "--diffraction-selection",
        type=Path,
        help="optional schema-v2 dataset-qualified diffraction selection",
    )
    brief_parser.add_argument(
        "--preflight",
        type=Path,
        help="required with --diffraction-selection for exact preflight verification",
    )
    brief_parser.add_argument(
        "--free-r-identity",
        type=Path,
        help=(
            "required with --diffraction-selection; content-addressed Free-R "
            "identity for exact post-refinement membership verification"
        ),
    )
    brief_parser.add_argument("--phenix-manifest", type=Path, required=True)
    brief_parser.add_argument("--outdir", type=Path, required=True)
    brief_parser.add_argument("--threads", type=int, default=4)
    brief_parser.add_argument(
        "--timeout-seconds",
        type=float,
        help="optional explicit deadline; by default no deadline is imposed",
    )
    stage_parser = refinement_actions.add_parser(
        "stage", help="derive the fixed all-candidate T12 boundary from retained M4"
    )
    stage_parser.add_argument("--parent-run", type=Path, required=True)
    stage_parser.add_argument("--source-records", type=Path, required=True)
    stage_parser.add_argument("--outdir", type=Path, required=True)
    stage_parser.add_argument("--expected-seed-count", type=int, default=11)
    live_stage_parser = refinement_actions.add_parser(
        "stage-live",
        help="retain every approved normal-workflow copy state for T12",
    )
    live_stage_parser.add_argument("--approved-stage", type=Path, required=True)
    live_stage_parser.add_argument("--review-package", type=Path, required=True)
    live_stage_parser.add_argument(
        "--additional-copy-result", type=Path, action="append", default=[]
    )
    live_stage_parser.add_argument("--hypotheses", type=Path, required=True)
    live_stage_parser.add_argument("--sequence-groups", type=Path, required=True)
    live_stage_parser.add_argument("--source-records", type=Path, required=True)
    live_stage_parser.add_argument("--preflight", type=Path, required=True)
    live_stage_parser.add_argument("--mtz", type=Path, required=True)
    live_stage_parser.add_argument("--phenix-manifest", type=Path, required=True)
    live_stage_parser.add_argument("--outdir", type=Path, required=True)

    review_parser = subparsers.add_parser(
        "review", help="build and validate file-based human checkpoints"
    )
    review_actions = review_parser.add_subparsers(dest="review_action", required=True)
    mr_seed_review_parser = review_actions.add_parser(
        "build-mr-seed",
        help="assemble a bounded first-copy MR review package",
    )
    mr_seed_review_parser.add_argument("--hypotheses", type=Path, required=True)
    mr_seed_review_parser.add_argument("--results", type=Path, required=True)
    mr_seed_review_parser.add_argument("--result-root", type=Path, required=True)
    mr_seed_review_parser.add_argument("--funnel-manifest", type=Path, required=True)
    mr_seed_review_parser.add_argument("--sequence-groups", type=Path, required=True)
    mr_seed_review_parser.add_argument("--source-records", type=Path, required=True)
    mr_seed_review_parser.add_argument("--matthews", type=Path, required=True)
    mr_seed_review_parser.add_argument("--config", type=Path, required=True)
    mr_seed_review_parser.add_argument("--outdir", type=Path, required=True)
    mr_seed_approval_parser = review_actions.add_parser(
        "validate-mr-seeds",
        help="validate explicit MR-seed decisions against a current package",
    )
    mr_seed_approval_parser.add_argument("--package-manifest", type=Path, required=True)
    mr_seed_approval_parser.add_argument("--decisions", type=Path, required=True)
    mr_seed_approval_parser.add_argument("--out", type=Path, required=True)
    sequence_checkpoint_parser = review_actions.add_parser(
        "build-sequence-checkpoint",
        help="publish the T12.5 top-10, top-25, full, and approval views",
    )
    sequence_checkpoint_parser.add_argument("--run-id", required=True)
    sequence_checkpoint_parser.add_argument(
        "--refinement-results", type=Path, required=True
    )
    sequence_checkpoint_parser.add_argument(
        "--sequence-results", type=Path, required=True
    )
    sequence_checkpoint_parser.add_argument(
        "--stage-manifest", type=Path, required=True
    )
    sequence_checkpoint_parser.add_argument("--job-result", type=Path, required=True)
    sequence_checkpoint_parser.add_argument(
        "--sequence-groups", type=Path, required=True
    )
    sequence_checkpoint_parser.add_argument(
        "--source-records", type=Path, required=True
    )
    sequence_checkpoint_parser.add_argument("--preflight", type=Path, required=True)
    sequence_checkpoint_parser.add_argument("--asset-root", type=Path, required=True)
    sequence_checkpoint_parser.add_argument("--outdir", type=Path, required=True)
    live_sequence_checkpoint_parser = review_actions.add_parser(
        "build-live-sequence-checkpoint",
        help="publish T12.5 directly from normal-workflow finalist outputs",
    )
    live_sequence_checkpoint_parser.add_argument(
        "--stage-bundle", type=Path, required=True
    )
    live_sequence_checkpoint_parser.add_argument(
        "--candidate-result", type=Path, action="append", default=[]
    )
    live_sequence_checkpoint_parser.add_argument("--outdir", type=Path, required=True)
    status_parser = review_actions.add_parser(
        "build-status",
        help="derive the T13.1 execution, scientific, and assumption status",
    )
    status_parser.add_argument("--crystal-id", required=True)
    status_parser.add_argument("--t12-summary", type=Path, required=True)
    status_parser.add_argument("--job-result", type=Path, required=True)
    status_parser.add_argument("--refinement-results", type=Path, required=True)
    status_parser.add_argument("--checkpoint-manifest", type=Path, required=True)
    status_parser.add_argument("--approval-candidates", type=Path, required=True)
    status_parser.add_argument("--decisions", type=Path, required=True)
    status_parser.add_argument(
        "--prototype-assumption-status",
        choices=("consistent", "possibly_violated", "violated", "unknown"),
        default="unknown",
    )
    status_parser.add_argument("--residual-content-suspected", action="store_true")
    status_parser.add_argument("--out", type=Path, required=True)
    report_parser = review_actions.add_parser(
        "build-report",
        help="add the T13.2 crystal report to a verified T12.5 package",
    )
    report_parser.add_argument("--status", type=Path, required=True)
    report_parser.add_argument("--checkpoint-dir", type=Path, required=True)
    resource_parser = review_actions.add_parser(
        "build-resource-summary",
        help="add the deterministic T13.3 resource record to a T12.5 package",
    )
    resource_parser.add_argument("--run-manifest", type=Path, required=True)
    resource_parser.add_argument("--job-result", type=Path, required=True)
    resource_parser.add_argument("--first-trace", type=Path, required=True)
    resource_parser.add_argument("--resume-trace", type=Path, required=True)
    resource_parser.add_argument("--first-report", type=Path, required=True)
    resource_parser.add_argument("--checkpoint-dir", type=Path, required=True)

    search_parser = subparsers.add_parser(
        "structure-search", help="search immutable structural-reference databases"
    )
    search_actions = search_parser.add_subparsers(
        dest="structure_search_action", required=True
    )
    provider_plan_parser = search_actions.add_parser(
        "resolve-provider-plan",
        help="resolve provider enablement, caps, adapters, and database identities",
    )
    provider_plan_parser.add_argument("--config", type=Path, required=True)
    provider_plan_parser.add_argument("--database-manifest", type=Path, required=True)
    provider_plan_parser.add_argument("--outdir", type=Path, required=True)
    disabled_provider_parser = search_actions.add_parser(
        "emit-disabled-provider",
        help="emit typed skipped-policy results for one disabled provider entry",
    )
    disabled_provider_parser.add_argument("--provider-entry", type=Path, required=True)
    disabled_provider_parser.add_argument("--sequence-groups", type=Path, required=True)
    disabled_provider_parser.add_argument("--outdir", type=Path, required=True)
    provider_empty_graph_parser = search_actions.add_parser(
        "complete-provider-empty-graph",
        help="close the fixed provider graph after complete empty branches",
    )
    provider_empty_graph_parser.add_argument("--config", type=Path, required=True)
    provider_empty_graph_parser.add_argument(
        "--provider-plan", type=Path, required=True
    )
    provider_empty_graph_parser.add_argument(
        "--sequence-groups", type=Path, required=True
    )
    provider_empty_graph_parser.add_argument(
        "--bundle", type=Path, action="append", required=True
    )
    provider_empty_graph_parser.add_argument("--outdir", type=Path, required=True)
    merge_provider_hits_parser = search_actions.add_parser(
        "merge-pdb-provider-hits",
        help="combine typed PDB-sequence and Foldseek hit evidence",
    )
    merge_provider_hits_parser.add_argument(
        "--pdb-sequence-hits", type=Path, required=True
    )
    merge_provider_hits_parser.add_argument("--foldseek-hits", type=Path, required=True)
    merge_provider_hits_parser.add_argument("--outdir", type=Path, required=True)
    pdb_sequence_parser = search_actions.add_parser(
        "pdb-sequence",
        help="search exact catalogue sequences against the local PDB SEQRES database",
    )
    pdb_sequence_parser.add_argument("--sequence-groups", type=Path, required=True)
    pdb_sequence_parser.add_argument("--database-manifest", type=Path, required=True)
    pdb_sequence_parser.add_argument("--provider-plan", type=Path)
    pdb_sequence_parser.add_argument("--provider-entry", type=Path)
    pdb_sequence_parser.add_argument("--outdir", type=Path, required=True)
    pdb_sequence_parser.add_argument("--threads", type=int, default=4)
    pdb_sequence_parser.add_argument("--maximum-hits-per-query", type=int, default=25)
    pdb_sequence_parser.add_argument("--maximum-evalue", type=float, default=1.0e-5)
    pdb_sequence_parser.add_argument(
        "--minimum-query-coverage", type=float, default=0.5
    )
    pdb_sequence_parser.add_argument("--maximum-query-length", type=int, default=10_000)
    pdb_coordinates_parser = search_actions.add_parser(
        "register-pdb-coordinates",
        help="cache and register a bounded, diversity-reserved set of direct-PDB hits",
    )
    pdb_coordinates_parser.add_argument("--structural-hits", type=Path, required=True)
    pdb_coordinates_parser.add_argument("--sequence-groups", type=Path, required=True)
    pdb_coordinates_parser.add_argument("--database-manifest", type=Path, required=True)
    pdb_coordinates_parser.add_argument("--outdir", type=Path, required=True)
    pdb_coordinates_parser.add_argument(
        "--maximum-hits-per-sequence-group", type=int, default=3
    )
    pdb_coordinates_parser.add_argument("--maximum-mappings", type=int, default=25)
    pdb_coordinates_parser.add_argument(
        "--hit-id",
        action="append",
        default=[],
        help=(
            "repeatable explicit direct-PDB hit ID; otherwise select deterministically"
        ),
    )
    pdb_coordinates_parser.add_argument(
        "--storage-limit-bytes", type=int, default=100_000_000_000
    )
    pdb_coordinates_parser.add_argument(
        "--minimum-free-bytes", type=int, default=1_000_000_000
    )
    prostt5_parser = search_actions.add_parser(
        "prostt5-foldseek",
        help="search exact sequences against local PDB using ProstT5 and Foldseek",
    )
    prostt5_parser.add_argument("--sequence-groups", type=Path, required=True)
    prostt5_parser.add_argument("--database-manifest", type=Path, required=True)
    prostt5_parser.add_argument("--provider-plan", type=Path)
    prostt5_parser.add_argument("--provider-entry", type=Path)
    prostt5_parser.add_argument("--outdir", type=Path, required=True)
    prostt5_parser.add_argument("--threads", type=int, default=4)
    prostt5_parser.add_argument("--maximum-hits-per-query", type=int, default=3)
    prostt5_parser.add_argument("--maximum-evalue", type=float, default=1.0e-3)
    prostt5_parser.add_argument("--minimum-query-coverage", type=float, default=0.5)
    prostt5_parser.add_argument("--maximum-query-length", type=int, default=10_000)
    prostt5_parser.add_argument(
        "--maximum-queries",
        type=int,
        default=0,
        help=(
            "deterministically search at most this many eligible queries; "
            "0 is unlimited"
        ),
    )
    prostt5_parser.add_argument(
        "--gpu",
        action="store_true",
        help="enable Foldseek/ProstT5 GPU execution (CPU is the default)",
    )
    afdb_parser = search_actions.add_parser(
        "afdb-exact",
        help="retrieve sequence-exact AlphaFold DB models for mapped accessions",
    )
    afdb_parser.add_argument("--sequence-groups", type=Path, required=True)
    afdb_parser.add_argument("--source-records", type=Path, required=True)
    afdb_parser.add_argument("--database-manifest", type=Path, required=True)
    afdb_parser.add_argument("--provider-plan", type=Path)
    afdb_parser.add_argument("--provider-entry", type=Path)
    afdb_parser.add_argument("--outdir", type=Path, required=True)
    afdb_parser.add_argument(
        "--accession-map",
        type=Path,
        help=(
            "optional TSV with source_record_id and uniprot_accession columns; "
            "strict UniProt identifiers are otherwise read from original_protein_id"
        ),
    )
    afdb_parser.add_argument("--request-timeout-seconds", type=float, default=60.0)
    afdb_parser.add_argument("--retry-count", type=int, default=3)
    qualify_p1_parser = search_actions.add_parser(
        "qualify-p1",
        help="validate direct-PDB results, positive control, resources, and resume",
    )
    qualify_p1_parser.add_argument("--sequence-groups", type=Path, required=True)
    qualify_p1_parser.add_argument("--search-directory", type=Path, required=True)
    qualify_p1_parser.add_argument("--control-specification", type=Path, required=True)
    qualify_p1_parser.add_argument("--first-trace", type=Path, required=True)
    qualify_p1_parser.add_argument("--resume-trace", type=Path, required=True)
    qualify_p1_parser.add_argument("--output", type=Path, required=True)
    return parser


def _run_contract(args: argparse.Namespace, logger: logging.Logger) -> int:
    if args.contract_action == "schema":
        payload = f"{canonical_json_text(contract_json_schema(args.kind))}\n"
        if args.output is None:
            sys.stdout.write(payload)
        else:
            atomic_write_text(args.output, payload)
            logger.info(
                "wrote contract schema",
                extra={"contract_kind": args.kind, "output": str(args.output)},
            )
        return 0

    model = load_contract(
        args.input,
        args.kind,
        input_format=cast(InputFormat, args.format),
        progress=not args.no_progress,
    )
    if args.contract_action == "validate":
        print(f"Valid {args.kind}: {args.input}")
        return 0

    payload = f"{canonical_json_text(model)}\n"
    if args.output is None:
        sys.stdout.write(payload)
    else:
        atomic_write_text(args.output, payload)
        logger.info(
            "wrote canonical contract",
            extra={"contract_kind": args.kind, "output": str(args.output)},
        )
    return 0


def _run_phenix(args: argparse.Namespace, logger: logging.Logger) -> int:
    gib = 1024**3
    if args.phenix_action == "install":
        request = InstallRequest(
            installer=args.installer,
            installer_sha256=args.installer_sha256,
            installation_prefix=args.prefix,
            expected_release=args.expected_release,
            expected_build=args.expected_build,
            temporary_directory=args.temp_dir,
            manifest_path=args.manifest,
            current_symlink=args.current_link,
            operator_notes=tuple(args.operator_note),
            minimum_install_free_bytes=int(args.minimum_install_free_gb * gib),
            minimum_temporary_free_bytes=int(args.minimum_temp_free_gb * gib),
            allow_home_root=args.allow_home_root,
            progress=not args.no_progress,
            command_timeout_seconds=args.command_timeout_seconds,
        )
        manifest = install_phenix(request)
        print(f"Verified Phenix {manifest.phenix_version}: {args.manifest}")
        return 0
    if args.phenix_action == "verify":
        inspection = verify_manifest(
            args.manifest,
            progress=not args.no_progress,
            timeout_seconds=args.command_timeout_seconds,
            verification_log=args.verification_log,
        )
        print(
            f"Verified Phenix {inspection.phenix_version}: {inspection.phenix_prefix}"
        )
        return 0
    if args.phenix_action == "refresh-manifest":
        manifest = refresh_legacy_manifest(
            args.manifest,
            args.output,
            progress=not args.no_progress,
            timeout_seconds=args.command_timeout_seconds,
            verification_log=args.verification_log,
        )
        print(f"Refreshed Phenix {manifest.phenix_version}: {args.output}")
        return 0
    if args.phenix_action == "recover-failed":
        manifest = recover_failed_install(
            RecoveryRequest(
                failed_prefix=args.failed_prefix,
                installation_prefix=args.prefix,
                failed_manifest=args.failed_manifest,
                failed_manifest_sha256=args.failed_manifest_sha256,
                recovered_manifest=args.manifest,
                expected_release=args.expected_release,
                expected_build=args.expected_build,
                tool_revision=args.tool_revision,
                current_symlink=args.current_link,
                progress=not args.no_progress,
                command_timeout_seconds=args.command_timeout_seconds,
            )
        )
        print(f"Recovered Phenix {manifest.phenix_version}: {args.manifest}")
        return 0
    if args.phenix_action == "exec":
        command = list(args.phenix_command)
        if command and command[0] == "--":
            command = command[1:]
        return execute_from_manifest(args.manifest, command)
    if args.phenix_action == "probe-phaser-interface":
        output = probe_phaser_interface(
            PhaserInterfaceProbeRequest(
                phenix_manifest=args.manifest,
                output_directory=args.outdir,
                timeout_seconds=args.command_timeout_seconds,
            )
        )
        print(f"Captured Phaser interface {output.probe_id}: {output.report_json}")
        return 0
    raise AssertionError(f"unhandled Phenix action: {args.phenix_action}")


def _run_databases(args: argparse.Namespace) -> int:
    if args.database_action == "stage-sources":
        bundle = stage_source_bundle(
            SourceBundleRequest(
                database_root=args.database_root,
                manifest_path=args.manifest,
                storage_limit_bytes=args.storage_limit_bytes,
                minimum_free_bytes=args.minimum_free_bytes,
                progress=not args.no_progress,
            )
        )
        print(
            f"Staged {len(bundle.resources)} durable database sources: {args.manifest}"
        )
        return 0
    if args.database_action == "preflight":
        result = preflight_database_administration(
            DatabasePreflightRequest(
                database_root=args.database_root,
                scratch_root=args.scratch_root,
                report_path=args.report,
                storage_limit_bytes=args.storage_limit_bytes,
                minimum_free_bytes=args.minimum_free_bytes,
                required_database_capacity_bytes=(
                    args.required_database_capacity_bytes
                ),
                minimum_scratch_free_bytes=args.minimum_scratch_free_bytes,
                source_bundle_path=args.source_bundle,
                probe_timeout_seconds=args.probe_timeout_seconds,
                progress=not args.no_progress,
            )
        )
        print(f"Database administration preflight {result['status']}: {args.report}")
        return 0
    if args.database_action != "prepare":
        raise AssertionError(f"unhandled database action: {args.database_action}")
    manifest = prepare(
        DatabasePreparationRequest(
            database_root=args.database_root,
            manifest_path=args.manifest,
            prepare_pdb_foldseek=args.prepare_pdb_foldseek,
            prepare_pdb_sequences=args.prepare_pdb_sequences,
            prepare_prostt5=args.prepare_prostt5,
            initialise_coordinate_cache=args.initialise_coordinate_cache,
            verify_esm_atlas_connectivity=args.verify_esm_atlas_connectivity,
            verify_only=args.verify_only,
            force_rebuild=args.force_rebuild,
            full_verify=args.full_verify,
            expected_manifest_path=args.expected_manifest,
            expected_manifest_sha256=args.expected_manifest_sha256,
            storage_limit_bytes=args.storage_limit_bytes,
            minimum_free_bytes=args.minimum_free_bytes,
            threads=args.threads,
            lock_timeout_seconds=args.lock_timeout_seconds,
            scratch_root=args.scratch_root,
            minimum_scratch_free_bytes=args.minimum_scratch_free_bytes,
            source_bundle_path=args.source_bundle,
            progress=not args.no_progress,
            pdb_sequence_url=args.pdb_sequence_url,
            pdb_coordinate_url_template=args.pdb_coordinate_url_template,
            esm_atlas_probe_url=args.esm_atlas_probe_url,
        )
    )
    print(f"Prepared {len(manifest.resources)} database resources: {args.manifest}")
    return 0


def _run_catalogue(args: argparse.Namespace) -> int:
    if args.catalogue_action != "import":
        raise AssertionError(f"unhandled catalogue action: {args.catalogue_action}")
    result = import_catalogues(
        CatalogueImportRequest(
            catalogue_manifest=args.catalogues,
            pipeline_config=args.config,
            output_directory=args.outdir,
            progress=not args.no_progress,
        )
    )
    print(
        f"Imported {result.manifest.source_record_count} source proteins into "
        f"{result.manifest.sequence_group_count} exact sequence groups: {args.outdir}"
    )
    return 0


def _run_localisation(args: argparse.Namespace) -> int:
    if args.localisation_action == "build-tasks":
        result = build_catalogue_localisation_tasks(
            args.sequence_groups,
            args.psortb_runtime,
            args.deeptmhmm_runtime,
            args.outdir,
        )
        print(
            f"Built {result.inventory.task_count} localisation task(s): "
            f"{result.inventory_json}"
        )
        return 0
    if args.localisation_action == "run-task":
        result = run_catalogue_localisation_task(
            args.task_directory,
            args.psortb_runtime,
            args.deeptmhmm_runtime,
            args.outdir,
        )
        print(
            f"Localisation {result.task.sequence_group_id}: "
            f"{result.group_evidence.merged_outcome.value}"
        )
        return 0
    if args.localisation_action == "build-wave-policy":
        result = build_catalogue_localisation_wave_policy(
            args.task_inventory,
            tuple(args.result_directory),
            args.outdir,
        )
        print(
            f"Built localisation wave policy for "
            f"{result.policy.sequence_group_count} group(s): {result.policy_json}"
        )
        return 0
    if args.localisation_action == "plan-reopen":
        result = plan_localisation_reopen(
            args.wave_policy,
            args.active_wave_completion,
            args.outdir,
        )
        print(f"Localisation reopen {result.plan.status.value}: {result.plan_json}")
        return 0
    raise AssertionError(f"unhandled localisation action: {args.localisation_action}")


def _run_benchmark(args: argparse.Namespace) -> int:
    mib = 1024 * 1024
    if args.benchmark_action == "prepare-public-control":
        control_result = prepare_public_control(
            PublicControlPreparationRequest(
                specification=args.specification,
                output_directory=args.outdir,
                proteome_faa=args.proteome_faa,
                catalogue_manifest=args.catalogue_manifest,
                download_missing=not args.offline,
                progress=not args.no_progress,
                storage_limit_bytes=args.storage_limit_mib * mib,
                minimum_free_bytes=args.minimum_free_mib * mib,
            )
        )
        print(
            f"Prepared public control {control_result.control_id}: "
            f"{control_result.preparation_manifest}"
        )
        return 0
    if args.benchmark_action == "prepare-6rtz-heteromer-control":
        prepared = prepare_6rtz_heteromer_control(
            HeteromerControlPreparationRequest(
                protocol=args.protocol,
                coordinates=args.coordinates,
                structure_factors=args.structure_factors,
                output_directory=args.outdir,
                download_missing=args.download,
                progress=not args.no_progress,
            )
        )
        print(f"Prepared fixed 6RTZ 1A+1B inputs: {prepared.preparation_manifest}")
        return 0
    if args.benchmark_action == "prepare-3u7q-heteromer-control":
        prepared = prepare_3u7q_heteromer_control(
            HeteromerControlPreparationRequest(
                protocol=args.protocol,
                coordinates=args.coordinates,
                structure_factors=args.structure_factors,
                output_directory=args.outdir,
                download_missing=args.download,
                progress=not args.no_progress,
            )
        )
        print(f"Prepared fixed 3U7Q 2A+2B inputs: {prepared.preparation_manifest}")
        return 0
    if args.benchmark_action == "prepare-heteromer-control-slice":
        prepared = prepare_heteromer_control_slice(
            HeteromerSlicePreparationRequest(
                protocol=args.protocol,
                control_6rtz_preparation=args.control_6rtz_preparation,
                control_3u7q_preparation=args.control_3u7q_preparation,
                catalogue_sequence_groups=args.catalogue_sequence_groups,
                output_directory=args.outdir,
            )
        )
        print(f"Prepared fixed P6 control slice: {prepared.preparation_manifest}")
        return 0
    if args.benchmark_action == "assess-heteromer-control-slice":
        assessed = assess_heteromer_control_slice(
            HeteromerSliceAssessmentRequest(
                preparation_manifest=args.preparation_manifest,
                catalogue_sequence_groups=args.catalogue_sequence_groups,
                positive_6rtz_result=args.positive_6rtz_result,
                positive_3u7q_result=args.positive_3u7q_result,
                positive_3u7q_parent_result=args.positive_3u7q_parent_result,
                missing_partner_plan=args.missing_partner_plan,
                missing_partner_summary=args.missing_partner_summary,
                wrong_partner_result=args.wrong_partner_result,
                homomer_result=args.homomer_result,
                output_json=args.output,
            )
        )
        print(f"Assessed fixed P6 control slice: {assessed.report_json}")
        return 0 if assessed.gate_passed else 4
    if args.benchmark_action == "prepare-6rtz-partner-catalogue":
        prepared = prepare_6rtz_partner_catalogue_control(
            HeteromerCatalogueControlRequest(
                protocol=args.protocol,
                control_preparation_manifest=args.control_preparation,
                output_directory=args.outdir,
                proteome_faa=args.proteome_faa,
                download_missing=args.download,
            )
        )
        print(
            f"Prepared {prepared.protein_record_count}-protein 6RTZ catalogue "
            f"control: {prepared.preparation_manifest}"
        )
        return 0
    if args.benchmark_action == "build-first-copy-controls":
        control_bundle = build_mr_control_bundle(
            MrControlBundleRequest(
                specification=args.specification,
                public_control_preparation=args.public_control_preparation,
                database_manifest=args.database_manifest,
                sequence_groups_jsonl=args.sequence_groups,
                preflight_jsonl=args.preflight,
                output_directory=args.outdir,
                progress=not args.no_progress,
            )
        )
        print(
            f"Prepared first-copy controls {control_bundle.control_pair_id}: "
            f"{control_bundle.manifest_json}"
        )
        return 0
    if args.benchmark_action == "approve-6rtz-parent":
        reviewed = build_6rtz_control_review(
            HeteromerControlReviewRequest(
                preparation_manifest=args.preparation_manifest,
                parent_result_directory=args.parent_result_directory,
                output_directory=args.outdir,
                progress=not args.no_progress,
            )
        )
        print(f"Approved fixed 6RTZ HisF parent: {reviewed.approved_stage}")
        return 0
    if args.benchmark_action == "run-control-slice":
        result = run_control_slice(
            ControlSliceRunRequest(
                import_root=args.import_root,
                phenix_manifest=args.phenix_manifest,
                output_directory=args.outdir,
                threads=args.threads,
                progress=not args.no_progress,
            )
        )
        print(
            f"Executed six-case control slice with "
            f"{result.first_copy_attempt_count} first-copy attempts: "
            f"{result.summary_json}"
        )
        return 0
    if args.benchmark_action == "run-control-matrix":
        result = run_control_matrix(
            ControlMatrixRunRequest(
                import_root=args.import_root,
                phenix_manifest=args.phenix_manifest,
                output_directory=args.outdir,
                threads=args.threads,
                progress=not args.no_progress,
            )
        )
        print(
            "Completed fixed 23-case homomer matrix: "
            f"{result.first_copy_attempt_count} first-copy, "
            f"{result.additional_copy_attempt_count} additional-copy, "
            f"{result.refinement_attempt_count} refinement attempts"
        )
        return 0
    if args.benchmark_action == "check-public-panel":
        panel = load_public_control_panel(args.panel)
        print(f"Public panel {panel.panel_id} is valid: {len(panel.entries)} entries")
        return 0
    if args.benchmark_action == "prepare-public-panel":
        panel_result = prepare_public_control_panel(
            PublicPanelPreparationRequest(
                specification=args.panel,
                output_directory=args.outdir,
                download_missing=not args.offline,
                progress=not args.no_progress,
                storage_limit_bytes=args.storage_limit_mib * mib,
                minimum_free_bytes=args.minimum_free_mib * mib,
            )
        )
        print(
            f"Prepared public panel {panel_result.panel_id} "
            f"({panel_result.entry_count} entries): "
            f"{panel_result.preparation_manifest}"
        )
        return 0
    if args.benchmark_action == "check-m6-protocol":
        protocol = load_m6_protocol(args.protocol)
        print(
            f"M6 protocol {protocol.protocol_id} is valid: {len(protocol.cases)} cases"
        )
        return 0
    if args.benchmark_action == "prepare-m6-inputs":
        result = prepare_m6_inputs(
            M6InputPreparationRequest(
                protocol=args.protocol,
                rcsb_directory=args.rcsb_root,
                catalogue_directories=tuple(args.catalogue_root),
                output_directory=args.outdir,
            )
        )
        print(
            f"Prepared {result.case_count} sanitised M6 inputs: "
            f"{result.preparation_manifest}"
        )
        return 0
    if args.benchmark_action == "build-m6-runner":
        result = build_m6_runner_bundle(
            M6RunnerBundleRequest(
                protocol=args.protocol,
                preparation_manifest=args.preparation_manifest,
                output_directory=args.outdir,
                archive=args.archive,
            )
        )
        print(
            f"Built truth-isolated M6 runner with {result.case_count} cases and "
            f"{result.object_count} objects: {result.archive} "
            f"({result.archive_sha256})"
        )
        return 0
    if args.benchmark_action == "verify-m6-runner":
        result = verify_m6_runner_bundle(
            M6RunnerVerificationRequest(
                runner_root=args.runner_root,
                output=args.report,
            )
        )
        print(
            f"Verified truth-isolated M6 runner with {result.case_count} cases "
            f"and {result.object_count} objects: {result.qualification}"
        )
        return 0
    if args.benchmark_action == "run-m6-scientific":
        raise GenomeToDiffractionError(
            "run-m6-scientific is a legacy verifier-only boundary; "
            "execute M6 through m6_validation.nf"
        )
    if args.benchmark_action == "plan-m6-nextflow":
        result = plan_m6_nextflow_track(
            M6TrackPlanRequest(
                runner_root=args.runner_root,
                database_manifest=args.database_manifest,
                software_lock=args.software_lock,
                track=args.track,
                output_directory=args.outdir,
            )
        )
        print(
            f"Planned M6 {args.track}: {result.case_task_count} cases, "
            f"{result.catalogue_task_count} catalogues"
        )
        return 0
    if args.benchmark_action == "run-m6-catalogue-task":
        result = run_m6_catalogue_task(args.task, args.software_lock, args.outdir)
        print(f"Completed M6 catalogue task: {result}")
        return 0
    if args.benchmark_action == "build-m6-search-batches":
        result = build_m6_search_batches(
            tuple(args.catalogue_bundle),
            args.database_manifest,
            args.execution_policy,
            args.software_lock,
            args.outdir,
        )
        print(f"Built M6 search batches: {result}")
        return 0
    if args.benchmark_action == "run-m6-pdb-task":
        result = run_m6_pdb_search_task(
            args.batch_task,
            args.database_manifest,
            args.execution_policy,
            args.software_lock,
            args.outdir,
            threads=args.threads,
        )
        print(f"Completed M6 PDB task: {result}")
        return 0
    if args.benchmark_action == "run-m6-foldseek-task":
        result = run_m6_foldseek_search_task(
            args.batch_task,
            args.database_manifest,
            args.execution_policy,
            args.software_lock,
            args.outdir,
            threads=args.threads,
        )
        print(f"Completed M6 Foldseek task: {result}")
        return 0
    if args.benchmark_action == "partition-m6-discovery":
        result = partition_m6_discovery_task(
            args.catalogue_bundle,
            args.batch_plan,
            tuple(args.pdb_result),
            tuple(args.foldseek_result),
            args.outdir,
        )
        print(f"Partitioned M6 discovery: {result}")
        return 0
    if args.benchmark_action == "run-m6-preflight-task":
        result = run_m6_preflight_task(args.task, args.phenix_manifest, args.outdir)
        print(f"Completed M6 preflight task: {result}")
        return 0
    if args.benchmark_action == "run-m6-policy-task":
        result = run_m6_model_policy_task(
            args.task,
            args.catalogue_bundle,
            args.pdb_bundle,
            args.foldseek_bundle,
            args.protocol,
            args.database_manifest,
            args.outdir,
        )
        print(f"Completed M6 policy task: {result}")
        return 0
    if args.benchmark_action == "run-m6-case-task":
        result = run_m6_prepare_case_task(
            args.task,
            args.preflight_bundle,
            args.catalogue_bundle,
            args.policy_bundle,
            args.database_manifest,
            args.outdir,
        )
        print(f"Completed M6 case task: {result}")
        return 0
    if args.benchmark_action == "select-m6-seeds":
        result = run_m6_select_seeds_task(
            args.case_bundle, tuple(args.first_copy_result), args.outdir
        )
        print(f"Selected M6 seeds: {result}")
        return 0
    if args.benchmark_action == "empty-m6-seeds":
        result = run_m6_empty_seeds_task(args.case_bundle, args.outdir)
        print(f"Published empty M6 seed bundle: {result}")
        return 0
    if args.benchmark_action == "run-m6-add-copy-task":
        result = run_m6_add_copy_task(
            args.case_bundle,
            args.seed_bundle,
            args.seed_solution_id,
            args.phenix_manifest,
            args.outdir,
            threads=args.threads,
        )
        print(f"Completed M6 copy task: {result}")
        return 0
    if args.benchmark_action == "select-m6-finalists":
        result = run_m6_select_finalists_task(
            args.case_bundle,
            args.seed_bundle,
            tuple(args.add_copy_result),
            args.outdir,
        )
        print(f"Selected M6 finalists: {result}")
        return 0
    if args.benchmark_action == "empty-m6-finalists":
        result = run_m6_empty_finalists_task(
            args.case_bundle, args.seed_bundle, args.outdir
        )
        print(f"Published empty M6 finalist bundle: {result}")
        return 0
    if args.benchmark_action == "run-m6-refinement-task":
        result = run_m6_refinement_task(
            args.finalist_bundle,
            args.seed_solution_id,
            args.phenix_manifest,
            args.outdir,
            threads=args.threads,
        )
        print(f"Completed M6 refinement task: {result}")
        return 0
    if args.benchmark_action == "assemble-m6-case":
        result = run_m6_assemble_case_task(
            args.case_bundle,
            args.finalist_bundle,
            tuple(args.refinement_result),
            args.outdir,
        )
        print(f"Assembled M6 case evidence: {result}")
        return 0
    if args.benchmark_action == "aggregate-m6-track":
        result = run_m6_aggregate_track_task(
            tuple(args.case_evidence),
            args.runner_root,
            args.protocol,
            args.database_manifest,
            args.phenix_manifest,
            args.track,
            args.outdir,
        )
        print(f"Aggregated M6 {args.track} track: {result}")
        return 0
    if args.benchmark_action == "collect-m6-resources":
        result = collect_m6_resource_evidence(
            M6ResourceEvidenceRequest(
                policy=args.execution_policy,
                trace=args.trace,
                output=args.output,
            )
        )
        print(f"Collected {result.child_job_count} M6 child jobs: {args.output}")
        return 0
    if args.benchmark_action == "evaluate-m6":
        result = evaluate_m6(
            M6EvaluationRequest(
                protocol=args.protocol,
                evidence=args.evidence,
                report=args.report,
            )
        )
        print(
            f"M6 release decision: {'accept' if result.accepted else 'hold'}; "
            f"report: {result.report_path}"
        )
        return 0
    if args.benchmark_action == "collect-m6-evidence":
        result = collect_m6_evidence(
            M6CollectionRequest(
                protocol=args.protocol,
                private_truth_map=args.private_truth_map,
                operational_collection=args.operational_collection,
                leakage_collection=args.leakage_collection,
                output=args.output,
            )
        )
        print(f"Collected M6 evidence: {result.output} ({result.sha256})")
        return 0
    raise AssertionError(f"unhandled benchmark action: {args.benchmark_action}")


def _run_diffraction(args: argparse.Namespace) -> int:
    if args.diffraction_action == "select-single":
        dispatch = prepare_crystal_dispatch(
            CrystalDispatchRequest(
                crystal_manifest=args.crystals,
                preflight_jsonl=args.preflight,
                output_directory=args.outdir,
                progress=not args.no_progress,
                crystal_id=args.crystal_id,
            )
        )
        print(
            f"Prepared crystal dispatch {dispatch.record.dispatch_id}: "
            f"{dispatch.dispatch_json}"
        )
        return 0
    if args.diffraction_action == "generate-free-r":
        record = generate_free_r(
            FreeRGenerationRequest(
                source_mtz=args.source_mtz,
                output_mtz=args.output_mtz,
                phenix_manifest=args.phenix_manifest,
                command_log=args.command_log,
                record_path=args.record,
                test_fraction=args.test_fraction,
                maximum_free_reflections=args.maximum_free_reflections,
                random_seed=args.random_seed,
                timeout_seconds=args.timeout_seconds,
                progress=not args.no_progress,
            )
        )
        print(
            f"Generated immutable Free-R MTZ {record.generation_id}: {args.output_mtz}"
        )
        return 0
    if args.diffraction_action != "preflight":
        raise AssertionError(f"unhandled diffraction action: {args.diffraction_action}")
    result = preflight_crystals(
        PreflightRequest(
            crystal_manifest=args.crystals,
            output_directory=args.outdir,
            phenix_manifest=args.phenix_manifest,
            skip_xtriage=args.skip_xtriage,
            progress=not args.no_progress,
            xtriage_timeout_seconds=args.xtriage_timeout_seconds,
        )
    )
    print(f"Preflighted {len(result.records)} MTZ file(s): {args.outdir}")
    return 0


def _run_matthews(args: argparse.Namespace) -> int:
    if args.matthews_action == "reference-check":
        reference_result = qualify_matthews_reference(
            MatthewsReferenceRequest(
                crystal_manifest=args.crystals,
                pipeline_config=args.config,
                preflight_jsonl=args.preflight,
                sequence_groups_jsonl=args.sequence_groups,
                source_records_jsonl=args.source_records,
                phenix_manifest=args.phenix_manifest,
                crystal_id=args.crystal_id,
                sequence_group_id=args.sequence_group_id,
                output_directory=args.outdir,
                timeout_seconds=args.timeout_seconds,
                progress=not args.no_progress,
            )
        )
        print(
            f"Matthews method-reference qualification {reference_result.status}: "
            f"{reference_result.json_path}"
        )
        return 0 if reference_result.status != "failed" else 1
    if args.matthews_action != "enumerate":
        raise AssertionError(f"unhandled Matthews action: {args.matthews_action}")
    result = enumerate_matthews(
        MatthewsRequest(
            crystal_manifest=args.crystals,
            pipeline_config=args.config,
            preflight_jsonl=args.preflight,
            sequence_groups_jsonl=args.sequence_groups,
            source_records_jsonl=args.source_records,
            output_directory=args.outdir,
            progress=not args.no_progress,
        )
    )
    print(f"Enumerated {len(result.hypotheses)} Matthews hypotheses: {args.outdir}")
    return 0


def _run_structure_search(args: argparse.Namespace) -> int:
    if args.structure_search_action == "resolve-provider-plan":
        provider_plan = resolve_provider_plan(
            ProviderPlanRequest(
                pipeline_config=args.config,
                database_manifest=args.database_manifest,
                output_directory=args.outdir,
            )
        )
        print(
            f"Resolved provider plan {provider_plan.plan.plan_id}: "
            f"{provider_plan.plan_json}"
        )
        return 0
    if args.structure_search_action == "emit-disabled-provider":
        disabled = emit_disabled_provider_bundle(
            DisabledProviderBundleRequest(
                provider_entry_json=args.provider_entry,
                sequence_groups_jsonl=args.sequence_groups,
                output_directory=args.outdir,
            )
        )
        print(
            f"Emitted {len(disabled.results)} disabled-provider results: "
            f"{disabled.search_manifest}"
        )
        return 0
    if args.structure_search_action == "complete-provider-empty-graph":
        completion = complete_provider_empty_graph(
            ProviderEmptyGraphRequest(
                pipeline_config=args.config,
                provider_plan_json=args.provider_plan,
                sequence_groups_jsonl=args.sequence_groups,
                provider_bundle_directories=tuple(args.bundle),
                output_directory=args.outdir,
            )
        )
        print(
            f"Completed empty provider graph {completion.completion.completion_id}: "
            f"{completion.completion_json}"
        )
        return 0
    if args.structure_search_action == "merge-pdb-provider-hits":
        merged = merge_pdb_provider_hits(
            ProviderHitMergeRequest(
                pdb_sequence_hits_jsonl=args.pdb_sequence_hits,
                foldseek_hits_jsonl=args.foldseek_hits,
                output_directory=args.outdir,
            )
        )
        print(f"Merged {len(merged.hits)} PDB provider hits: {merged.manifest_json}")
        return 0
    if args.structure_search_action == "qualify-p1":
        report = qualify_p1_search(
            P1QualificationRequest(
                sequence_groups_jsonl=args.sequence_groups,
                search_directory=args.search_directory,
                control_specification=args.control_specification,
                first_trace_tsv=args.first_trace,
                resume_trace_tsv=args.resume_trace,
                output_json=args.output,
                progress=not args.no_progress,
            )
        )
        print(f"P1 direct-PDB search qualified: {report}")
        return 0
    if args.structure_search_action == "afdb-exact":
        afdb_result = search_afdb_exact(
            AfdbExactRequest(
                sequence_groups_jsonl=args.sequence_groups,
                source_records_jsonl=args.source_records,
                database_manifest=args.database_manifest,
                output_directory=args.outdir,
                provider_plan_json=args.provider_plan,
                provider_entry_json=args.provider_entry,
                accession_map_tsv=args.accession_map,
                request_timeout_seconds=args.request_timeout_seconds,
                retry_count=args.retry_count,
                progress=not args.no_progress,
            )
        )
        print(
            f"Checked {len(afdb_result.results)} exact sequence groups and cached "
            f"{len(afdb_result.coordinate_sources)} exact AFDB models: "
            f"{afdb_result.search_manifest}"
        )
        return 0
    if args.structure_search_action == "prostt5-foldseek":
        foldseek_result = search_prostt5_foldseek(
            ProstT5FoldseekSearchRequest(
                sequence_groups_jsonl=args.sequence_groups,
                database_manifest=args.database_manifest,
                output_directory=args.outdir,
                provider_plan_json=args.provider_plan,
                provider_entry_json=args.provider_entry,
                threads=args.threads,
                maximum_hits_per_query=args.maximum_hits_per_query,
                maximum_evalue=args.maximum_evalue,
                minimum_query_coverage=args.minimum_query_coverage,
                maximum_query_length=args.maximum_query_length,
                maximum_queries=args.maximum_queries,
                gpu=args.gpu,
                progress=not args.no_progress,
            )
        )
        hit_count = sum(item.hit_count for item in foldseek_result.results)
        print(
            f"Searched {len(foldseek_result.results)} exact sequence groups and "
            f"retained {hit_count} ProstT5/Foldseek PDB hits: "
            f"{foldseek_result.search_manifest}"
        )
        return 0
    if args.structure_search_action == "register-pdb-coordinates":
        registration = register_pdb_coordinates(
            PdbCoordinateRegistrationRequest(
                structural_hits_jsonl=args.structural_hits,
                sequence_groups_jsonl=args.sequence_groups,
                database_manifest=args.database_manifest,
                output_directory=args.outdir,
                maximum_hits_per_sequence_group=(args.maximum_hits_per_sequence_group),
                maximum_mappings=args.maximum_mappings,
                hit_ids=tuple(args.hit_id),
                storage_limit_bytes=args.storage_limit_bytes,
                minimum_free_bytes=args.minimum_free_bytes,
                progress=not args.no_progress,
            )
        )
        print(
            f"Registered {len(registration.mappings)} direct-PDB mapping(s) from "
            f"{len(registration.coordinate_sources)} coordinate source(s): "
            f"{registration.manifest_json}"
        )
        return 0
    if args.structure_search_action != "pdb-sequence":
        raise AssertionError(
            f"unhandled structure-search action: {args.structure_search_action}"
        )
    result = search_pdb_sequences(
        PdbSequenceSearchRequest(
            sequence_groups_jsonl=args.sequence_groups,
            database_manifest=args.database_manifest,
            output_directory=args.outdir,
            provider_plan_json=args.provider_plan,
            provider_entry_json=args.provider_entry,
            threads=args.threads,
            maximum_hits_per_query=args.maximum_hits_per_query,
            maximum_evalue=args.maximum_evalue,
            minimum_query_coverage=args.minimum_query_coverage,
            maximum_query_length=args.maximum_query_length,
            progress=not args.no_progress,
        )
    )
    hit_count = sum(item.hit_count for item in result.results)
    print(
        f"Searched {len(result.results)} exact sequence groups and retained "
        f"{hit_count} PDB sequence hits: {result.search_manifest}"
    )
    return 0


def _run_model(args: argparse.Namespace) -> int:
    if args.model_action == "prepare-experimental":
        experimental_result = prepare_experimental_models(
            ExperimentalModelPreparationRequest(
                coordinate_sources_jsonl=args.coordinate_sources,
                coordinate_hit_mappings_jsonl=args.coordinate_hit_mappings,
                sequence_groups_jsonl=args.sequence_groups,
                output_directory=args.outdir,
                mapping_ids=tuple(args.mapping_id),
                progress=not args.no_progress,
            )
        )
        print(
            f"Prepared {len(experimental_result.records)} experimental MR model(s): "
            f"{experimental_result.manifest_json}"
        )
        return 0
    if args.model_action != "prepare-predicted":
        raise AssertionError(f"unhandled model action: {args.model_action}")
    predicted_result = prepare_predicted_models(
        PredictedModelPreparationRequest(
            coordinate_sources_jsonl=args.coordinate_sources,
            sequence_groups_jsonl=args.sequence_groups,
            phenix_manifest=args.phenix_manifest,
            output_directory=args.outdir,
            coordinate_ids=tuple(args.coordinate_id),
            timeout_seconds=args.timeout_seconds,
            progress=not args.no_progress,
        )
    )
    print(
        f"Prepared {len(predicted_result.records)} predicted MR model(s): "
        f"{predicted_result.manifest_json}"
    )
    return 0


def _run_ranking(args: argparse.Namespace) -> int:
    if args.ranking_action == "approved-partner-plan":
        partner_plan = build_approved_partner_search_plan(
            ApprovedPartnerPlanRequest(
                approved_stage=args.approved_stage,
                crystal_id=args.crystal_id,
                partner_copy_count=args.partner_copy_count,
                sequence_groups_jsonl=args.sequence_groups,
                matthews_hypotheses_jsonl=args.matthews,
                mtz_preflight_jsonl=args.preflight,
                pipeline_config=args.config,
                model_registry_directory=args.model_registry,
                output_directory=args.outdir,
                progress=not args.no_progress,
            )
        )
        print(
            f"Selected {partner_plan.plan.selected_attempt_count} approved-parent "
            f"B candidate(s): {partner_plan.plan_json}"
        )
        return 0
    if args.ranking_action == "partner-plan":
        partner_plan = build_partner_search_plan(
            PartnerPlanRequest(
                crystal_id=args.crystal_id,
                parent_sequence_group_id=args.parent_sequence_group_id,
                parent_copy_count=args.parent_copy_count,
                partner_copy_count=args.partner_copy_count,
                sequence_groups_jsonl=args.sequence_groups,
                matthews_hypotheses_jsonl=args.matthews,
                mtz_preflight_jsonl=args.preflight,
                pipeline_config=args.config,
                model_registry_directory=args.model_registry,
                output_directory=args.outdir,
                progress=not args.no_progress,
            )
        )
        print(
            f"Selected {partner_plan.plan.selected_attempt_count} of "
            f"{partner_plan.plan.candidate_count} catalogue B candidate(s): "
            f"{partner_plan.plan_json}"
        )
        return 0
    if args.ranking_action == "diverse-first-copy-funnel":
        diverse_result = build_diverse_first_copy_funnel(
            DiverseFirstCopyFunnelRequest(
                coordinate_sources_jsonl=tuple(args.coordinate_sources),
                processed_models_jsonl=tuple(args.processed_models),
                model_preparation_manifests=tuple(args.model_preparation_manifest),
                coordinate_hit_mappings_jsonl=args.coordinate_hit_mappings,
                sequence_groups_jsonl=args.sequence_groups,
                matthews_hypotheses_jsonl=args.matthews,
                mtz_preflight_jsonl=args.preflight,
                pipeline_config=args.config,
                output_directory=args.outdir,
                crystal_ids=tuple(args.crystal_id),
                maximum_first_copy_jobs=args.maximum_first_copy_jobs,
                progress=not args.no_progress,
            )
        )
        print(
            f"Selected {len(diverse_result.hypotheses)} multi-source first-copy "
            f"hypothesis(es): {diverse_result.manifest_json}"
        )
        return 0
    if args.ranking_action != "exact-predicted-funnel":
        raise AssertionError(f"unhandled ranking action: {args.ranking_action}")
    result = build_exact_predicted_funnel(
        ExactPredictedFunnelRequest(
            coordinate_sources_jsonl=args.coordinate_sources,
            processed_models_jsonl=args.processed_models,
            model_preparation_manifest=args.model_preparation_manifest,
            sequence_groups_jsonl=args.sequence_groups,
            matthews_hypotheses_jsonl=args.matthews,
            mtz_preflight_jsonl=args.preflight,
            pipeline_config=args.config,
            output_directory=args.outdir,
            crystal_ids=tuple(args.crystal_id),
            progress=not args.no_progress,
        )
    )
    print(
        f"Selected {len(result.hypotheses)} exact-predicted MR hypothesis(es): "
        f"{result.manifest_json}"
    )
    return 0


def _run_mr(args: argparse.Namespace) -> int:
    if args.mr_action == "copy-report":
        report = build_copy_count_report(
            CopyCountReportRequest(
                results_jsonl=args.results,
                output_directory=args.outdir,
                progress=not args.no_progress,
            )
        )
        print(
            f"Built copy-count report for {len(report.assessments)} candidate(s): "
            f"{report.manifest_json}"
        )
        return 0
    if args.mr_action == "stage-add-copy":
        staged = prepare_add_copy_stage(
            AddCopyStageRequest(
                parent_run=args.parent_run,
                decisions=args.decisions,
                expected_review_manifest_sha256=args.review_manifest_sha256,
                mtz=args.mtz,
                phenix_manifest=args.phenix_manifest,
                output_directory=args.outdir,
                expected_seed_count=args.expected_seed_count,
                progress=not args.no_progress,
                use_solution_coordinates_as_models=(
                    args.use_solution_coordinates_as_models
                ),
                source_site_id=args.source_site_id,
            )
        )
        print(
            f"Prepared {staged.seed_count} comparative M4 seed(s): "
            f"{staged.stage_manifest}"
        )
        return 0
    if args.mr_action == "stage-approved-seeds":
        live_staged = prepare_live_add_copy_stage(
            LiveAddCopyStageRequest(
                review_package=args.review_package,
                decisions=args.decisions,
                hypotheses_jsonl=args.hypotheses,
                output_directory=args.outdir,
                progress=not args.no_progress,
            )
        )
        print(
            f"Staged {live_staged.approved_seed_count} approved MR seed(s); "
            f"{live_staged.additional_copy_seed_count} require additional-copy "
            f"search: {live_staged.stage_manifest}"
        )
        return 0
    if args.mr_action == "add-copy":
        request = AddCopyRunRequest(
            review_validation_json=args.review_validation,
            review_package_manifest=args.review_package_manifest,
            seed_solution_id=args.seed_solution_id,
            hypotheses_jsonl=args.hypotheses,
            sequence_groups_jsonl=args.sequence_groups,
            preflight_jsonl=args.preflight,
            mtz=args.mtz,
            search_model=args.search_model,
            expected_search_model_sha256=args.expected_search_model_sha256,
            phenix_manifest=args.phenix_manifest,
            output_directory=args.outdir,
            parent_result_jsonl=args.parent_result,
            parent_coordinate=args.parent_coordinate,
            threads=args.threads,
            timeout_seconds=args.timeout_seconds,
            progress=not args.no_progress,
        )
        if args.until_expected:
            series = run_additional_copy_series(request)
            print(
                f"Additional-copy MR series retained {len(series.attempts)} "
                f"attempt(s): {series.summary_json}"
            )
            return 0
        add_copy_output = run_additional_copy_phaser(request)
        print(
            "Additional-copy MR "
            f"{add_copy_output.result.execution_status.value}: "
            f"{add_copy_output.result_json}"
        )
        return 0
    if args.mr_action == "search-partner":
        partner_output = run_partner_search(
            PartnerSearchRequest(
                crystal_id=args.crystal_id,
                parent_solution_id=args.parent_solution_id,
                parent_sequence_group_id=args.parent_sequence_group_id,
                partner_sequence_group_id=args.partner_sequence_group_id,
                sequence_groups_jsonl=args.sequence_groups,
                parent_coordinate=args.parent_coordinate,
                expected_parent_coordinate_sha256=(
                    args.expected_parent_coordinate_sha256
                ),
                parent_llg=args.parent_llg,
                parent_model_identity_fraction=(args.parent_model_identity_fraction),
                parent_model_uncertainty_source=(args.parent_model_uncertainty_source),
                parent_copy_count=args.parent_copy_count,
                partner_model=args.partner_model,
                expected_partner_model_sha256=args.expected_partner_model_sha256,
                partner_model_identity_fraction=(args.partner_model_identity_fraction),
                partner_copy_count=args.partner_copy_count,
                preflight_jsonl=args.preflight,
                mtz=args.mtz,
                phenix_manifest=args.phenix_manifest,
                output_directory=args.outdir,
                threads=args.threads,
                timeout_seconds=args.timeout_seconds,
                progress=not args.no_progress,
            )
        )
        print(
            "Partner MR "
            f"{partner_output.result.execution_status.value}: "
            f"{partner_output.result_json}"
        )
        return 0
    if args.mr_action == "approved-partner":
        partner_output = run_approved_partner_search(
            ApprovedPartnerSearchRequest(
                approved_stage=args.approved_stage,
                review_package=args.review_package,
                control_preparation_manifest=args.control_preparation,
                sequence_groups_jsonl=args.sequence_groups,
                preflight_jsonl=args.preflight,
                mtz=args.mtz,
                phenix_manifest=args.phenix_manifest,
                output_directory=args.outdir,
                threads=args.threads,
                timeout_seconds=args.timeout_seconds,
                progress=not args.no_progress,
            )
        )
        print(
            "Approved partner MR "
            f"{partner_output.result.execution_status.value}: "
            f"{partner_output.result_json}"
        )
        return 0
    if args.mr_action == "planned-partner":
        partner_output = run_planned_partner_search(
            PlannedPartnerSearchRequest(
                approved_stage=args.approved_stage,
                review_package=args.review_package,
                partner_plan_json=args.partner_plan,
                partner_candidate_id=args.partner_candidate_id,
                sequence_groups_jsonl=args.sequence_groups,
                model_registry_directory=args.model_registry,
                preflight_jsonl=args.preflight,
                mtz=args.mtz,
                phenix_manifest=args.phenix_manifest,
                output_directory=args.outdir,
                threads=args.threads,
                timeout_seconds=args.timeout_seconds,
                progress=not args.no_progress,
            )
        )
        print(
            "Planned partner MR "
            f"{partner_output.result.execution_status.value}: "
            f"{partner_output.result_json}"
        )
        return 0
    if args.mr_action == "summarize-partners":
        summary = summarize_partner_attempts(
            PartnerSummaryRequest(
                partner_plan_json=args.partner_plan,
                result_directories=tuple(args.result_directory),
                output_json=args.output,
            )
        )
        print(
            f"Retained {summary.result_count} of "
            f"{summary.selected_attempt_count} selected partner result(s): "
            f"{args.output}"
        )
        return 0
    if args.mr_action != "first-copy":
        raise AssertionError(f"unhandled MR action: {args.mr_action}")
    output = run_first_copy_phaser(
        PhaserRunRequest(
            hypotheses_jsonl=args.hypotheses,
            hypothesis_id=args.hypothesis_id,
            sequence_groups_jsonl=args.sequence_groups,
            processed_models_jsonl=args.processed_models,
            model_preparation_manifest=args.model_preparation_manifest,
            preflight_jsonl=args.preflight,
            mtz=args.mtz,
            phenix_manifest=args.phenix_manifest,
            output_directory=args.outdir,
            diffraction_selection_json=args.diffraction_selection,
            phase3_hypothesis_id=args.phase3_hypothesis_id,
            threads=args.threads,
            timeout_seconds=args.timeout_seconds,
            progress=not args.no_progress,
        )
    )
    print(f"First-copy MR {output.result.execution_status.value}: {output.result_json}")
    return 0


def _run_review(args: argparse.Namespace) -> int:
    if args.review_action == "build-resource-summary":
        resources = build_resource_summary(
            ResourceSummaryRequest(
                run_manifest_json=args.run_manifest,
                job_result_json=args.job_result,
                first_trace_tsv=args.first_trace,
                resume_trace_tsv=args.resume_trace,
                first_report_html=args.first_report,
                checkpoint_directory=args.checkpoint_dir,
                progress=not args.no_progress,
            )
        )
        print(
            f"Built T13.3 resource summary {resources.summary_id}: "
            f"{resources.summary_json}"
        )
        return 0
    if args.review_action == "build-report":
        report = build_crystal_report(
            CrystalReportRequest(
                status_json=args.status,
                checkpoint_directory=args.checkpoint_dir,
            )
        )
        print(f"Built T13.2 crystal report {report.report_id}: {report.report_html}")
        return 0
    if args.review_action == "build-mr-seed":
        output = build_mr_seed_review(
            MrSeedReviewRequest(
                hypotheses_jsonl=args.hypotheses,
                results_jsonl=args.results,
                result_root=args.result_root,
                funnel_manifest=args.funnel_manifest,
                sequence_groups_jsonl=args.sequence_groups,
                source_records_jsonl=args.source_records,
                matthews_hypotheses_jsonl=args.matthews,
                pipeline_config=args.config,
                output_directory=args.outdir,
                progress=not args.no_progress,
            )
        )
        print(
            f"Built MR seed review package with {output.candidate_count} "
            f"candidate(s): {output.manifest_json}"
        )
        return 0
    if args.review_action == "build-live-sequence-checkpoint":
        sequence_output = build_live_sequence_checkpoint(
            LiveSequenceCheckpointRequest(
                stage_bundle=args.stage_bundle,
                candidate_result_directories=tuple(args.candidate_result),
                output_directory=args.outdir,
                progress=not args.no_progress,
            )
        )
        print(
            f"Built normal-workflow T12.5 checkpoint for "
            f"{sequence_output.finalist_count} finalist(s): "
            f"{sequence_output.manifest_json}"
        )
        return 0
    if args.review_action == "build-sequence-checkpoint":
        sequence_output = build_sequence_checkpoint(
            SequenceCheckpointRequest(
                run_id=args.run_id,
                refinement_results_jsonl=args.refinement_results,
                sequence_results_jsonl=args.sequence_results,
                stage_manifest_json=args.stage_manifest,
                job_result_json=args.job_result,
                sequence_groups_jsonl=args.sequence_groups,
                source_records_jsonl=args.source_records,
                preflight_jsonl=args.preflight,
                asset_root=args.asset_root,
                output_directory=args.outdir,
                progress=not args.no_progress,
            )
        )
        print(
            f"Built T12.5 sequence checkpoint for {sequence_output.finalist_count} "
            f"finalist(s): {sequence_output.manifest_json}"
        )
        return 0
    if args.review_action == "build-status":
        from genome_to_diffraction.schemas.results import PrototypeAssumptionStatus

        status = build_status_record(
            StatusRequest(
                crystal_id=args.crystal_id,
                t12_summary_json=args.t12_summary,
                job_result_json=args.job_result,
                refinement_results_jsonl=args.refinement_results,
                checkpoint_manifest_json=args.checkpoint_manifest,
                approval_candidates_tsv=args.approval_candidates,
                decisions_tsv=args.decisions,
                output_json=args.out,
                prototype_assumption_status=PrototypeAssumptionStatus(
                    args.prototype_assumption_status
                ),
                residual_content_suspected=args.residual_content_suspected,
            )
        )
        print(
            f"Built T13.1 status {status.execution_status.value}/"
            f"{status.scientific_status.value}: {args.out}"
        )
        return 0
    if args.review_action != "validate-mr-seeds":
        raise AssertionError(f"unhandled review action: {args.review_action}")
    approval = validate_mr_seed_approvals(
        MrSeedApprovalRequest(
            package_manifest=args.package_manifest,
            decisions=args.decisions,
            output_json=args.out,
            progress=not args.no_progress,
        )
    )
    print(
        f"Validated {len(approval.approved_solution_ids)} approved MR seed(s): "
        f"{approval.output_json}"
    )
    return 0


def _run_refinement(args: argparse.Namespace) -> int:
    if args.refinement_action == "stage-live":
        live_stage_output = stage_live_t12_inputs(
            LiveT12StageRequest(
                approved_stage=args.approved_stage,
                review_package=args.review_package,
                additional_copy_results=tuple(args.additional_copy_result),
                hypotheses_jsonl=args.hypotheses,
                sequence_groups_jsonl=args.sequence_groups,
                source_records_jsonl=args.source_records,
                preflight_jsonl=args.preflight,
                diffraction_mtz=args.mtz,
                phenix_manifest=args.phenix_manifest,
                output_directory=args.outdir,
                progress=not args.no_progress,
            )
        )
        print(
            f"Staged {live_stage_output.seed_count} live T12 finalists: "
            f"{live_stage_output.manifest}"
        )
        return 0
    if args.refinement_action == "stage":
        fixed_stage_output = stage_t12_inputs(
            T12StageRequest(
                parent_run=args.parent_run,
                source_records_jsonl=args.source_records,
                output_directory=args.outdir,
                expected_seed_count=args.expected_seed_count,
                progress=not args.no_progress,
            )
        )
        print(
            f"Staged {fixed_stage_output.seed_count} T12 finalists: "
            f"{fixed_stage_output.manifest}"
        )
        return 0
    if args.refinement_action != "brief":
        raise AssertionError(f"unhandled refinement action: {args.refinement_action}")
    run_output = run_t12_candidate(
        T12RunRequest(
            seed_solution_id=args.seed_solution_id,
            sequence_group_id=args.sequence_group_id,
            input_copy_count=args.input_copy_count,
            parent_coordinate=args.parent_coordinate,
            parent_coordinate_sha256=args.parent_coordinate_sha256,
            parent_mtz=args.parent_mtz,
            parent_mtz_sha256=args.parent_mtz_sha256,
            observation_labels=args.observation_labels,
            sequence_groups_jsonl=args.sequence_groups,
            source_records_jsonl=args.source_records,
            resolution=args.resolution,
            phenix_manifest=args.phenix_manifest,
            output_directory=args.outdir,
            crystal_id=args.crystal_id,
            diffraction_selection_json=args.diffraction_selection,
            preflight_jsonl=args.preflight,
            free_r_identity_json=args.free_r_identity,
            threads=args.threads,
            timeout_seconds=args.timeout_seconds,
            progress=not args.no_progress,
        )
    )
    print(
        f"T12 refinement {run_output.refinement.execution_status.value}; "
        f"sequence assessment {run_output.sequence.execution_status.value}: "
        f"{run_output.sequence_json}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        level = parse_log_level(args.log_level)
    except ValueError as level_error:
        parser.error(str(level_error))
    logger = configure_logging(level=level, log_format=args.log_format)

    try:
        if args.command == "schema-check":
            errors = validate_repository(args.repository)
            if errors:
                for schema_error in errors:
                    logger.error(
                        "schema validation failed", extra={"error": schema_error}
                    )
                return 1
            print("All schemas, fixtures, and review TSV contracts are valid.")
            return 0
        if args.command == "contract":
            return _run_contract(args, logger)
        if args.command == "phenix":
            return _run_phenix(args, logger)
        if args.command == "databases":
            return _run_databases(args)
        if args.command == "benchmark":
            return _run_benchmark(args)
        if args.command == "catalogue":
            return _run_catalogue(args)
        if args.command == "localisation":
            return _run_localisation(args)
        if args.command == "diffraction":
            return _run_diffraction(args)
        if args.command == "matthews":
            return _run_matthews(args)
        if args.command == "model":
            return _run_model(args)
        if args.command == "ranking":
            return _run_ranking(args)
        if args.command == "mr":
            return _run_mr(args)
        if args.command == "refinement":
            return _run_refinement(args)
        if args.command == "review":
            return _run_review(args)
        if args.command == "structure-search":
            return _run_structure_search(args)
    except PhenixInstallCommandError as error:
        logger.error(
            "Phenix installer command failed",
            extra={"error": str(error), "exit_status": error.returncode},
        )
        return error.returncode
    except (
        ContractError,
        GenomeToDiffractionError,
        OSError,
        ValueError,
    ) as error:
        logger.error("command failed", extra={"error": str(error)})
        return 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
