#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include {
    PHASE3_FIRST_COPY_APPLICATION_WORKFLOW;
    PHASE3_REVIEWED_SINGLE_COMPONENT_APPLICATION_WORKFLOW
} from './workflows/phase3_application_workflow'

params {
    catalogues: Path
    crystals: Path
    config: Path
    database_manifest: Path
    phenix_manifest: Path
    phase3_operation: String
    phase3_execution_identity: Path
    phase3_owned_parent_run_id: String
    phase3_crystallographic_review_stage: Path? = null
    phase3_reviewed_crystal_manifest: Path? = null
    phase3_owned_run_registry: Path? = null
    phase3_owned_sequence_parent_run_id: String? = null
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
    review_mode: String = 'prepare'
    profile_mode: String = 'smoke'
    skip_xtriage: Boolean = false
    maximum_evalue: Float = 1.0e-5
    minimum_query_coverage: Float = 0.5
    maximum_query_length: Integer = 10000
    prostt5_maximum_evalue: Float = 1.0e-3
    prostt5_minimum_query_coverage: Float = 0.5
    prostt5_maximum_query_length: Integer = 10000
    prostt5_maximum_queries: Integer = 0
    prostt5_gpu: Boolean = false
    afdb_accession_map: Path? = null
    afdb_request_timeout_seconds: Float = 60.0
    afdb_retry_count: Integer = 3
    maximum_pdb_hits_per_sequence_group: Integer = 3
    maximum_pdb_mappings: Integer = 25
    maximum_first_copy_jobs: Integer = 25
}

workflow {
    main:
    if (!(params.phase3_operation in [
        'first_copy',
        'reviewed_single_component'
    ])) {
        error "Unsupported phase3_operation: ${params.phase3_operation}"
    }
    if (params.phase3_operation == 'first_copy') {
        if (
            params.phase3_crystallographic_review_stage == null ||
            params.phase3_reviewed_crystal_manifest != null ||
            params.phase3_owned_run_registry != null ||
            params.phase3_owned_sequence_parent_run_id != null
        ) {
            error 'Phase III first-copy requires only its crystallographic review authority'
        }
        PHASE3_FIRST_COPY_APPLICATION_WORKFLOW(
            params.catalogues,
            params.crystals,
            params.config,
            params.database_manifest,
            params.phenix_manifest,
            params.cache_root.toString(),
            params.review_mode,
            params.profile_mode,
            params.skip_xtriage,
            params.maximum_evalue.toFloat(),
            params.minimum_query_coverage.toFloat(),
            params.maximum_query_length,
            params.prostt5_maximum_evalue.toFloat(),
            params.prostt5_minimum_query_coverage.toFloat(),
            params.prostt5_maximum_query_length,
            params.prostt5_maximum_queries,
            params.prostt5_gpu,
            params.afdb_accession_map,
            params.afdb_request_timeout_seconds.toFloat(),
            params.afdb_retry_count,
            params.maximum_pdb_hits_per_sequence_group,
            params.maximum_pdb_mappings,
            params.maximum_first_copy_jobs,
            params.phase3_crystallographic_review_stage,
            params.phase3_execution_identity,
            params.phase3_owned_parent_run_id
        )
    } else {
        if (
            params.phase3_crystallographic_review_stage != null ||
            params.phase3_reviewed_crystal_manifest == null ||
            params.phase3_owned_run_registry == null ||
            params.phase3_owned_sequence_parent_run_id == null ||
            params.phase3_owned_sequence_parent_run_id ==
            params.phase3_owned_parent_run_id
        ) {
            error 'Phase III reviewed continuation requires its owned screen and distinct single-component parent'
        }
        PHASE3_REVIEWED_SINGLE_COMPONENT_APPLICATION_WORKFLOW(
            params.catalogues,
            params.crystals,
            params.config,
            params.database_manifest,
            params.phenix_manifest,
            params.cache_root.toString(),
            params.review_mode,
            params.profile_mode,
            params.skip_xtriage,
            params.phase3_reviewed_crystal_manifest,
            params.phase3_owned_run_registry,
            params.phase3_execution_identity,
            params.phase3_owned_parent_run_id,
            params.phase3_owned_sequence_parent_run_id
        )
    }
}
