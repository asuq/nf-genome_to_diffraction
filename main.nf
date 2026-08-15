#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { MAIN_WORKFLOW } from './workflows/main_workflow'

params {
    catalogues: Path
    crystals: Path
    config: Path
    database_manifest: Path
    phenix_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
    review_mode: String = 'prepare'
    approved_mr_seeds: Path? = null
    approved_sequence_groups: Path? = null
    profile_mode: String = 'smoke'
    analysis_stage: String = 'task05'
    skip_xtriage: Boolean = false
    maximum_hits_per_query: Integer = 25
    maximum_evalue: Float = 1.0e-5
    minimum_query_coverage: Float = 0.5
    maximum_query_length: Integer = 10000
    prostt5_maximum_hits_per_query: Integer = 3
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
    if (!(params.analysis_stage in [
        'task05',
        'discovery',
        'first_copy',
        'additional_copy'
    ])) {
        error "Unsupported analysis_stage: ${params.analysis_stage}"
    }
    if (
        params.analysis_stage == 'additional_copy' &&
        params.approved_mr_seeds == null
    ) {
        error "analysis_stage=additional_copy requires --approved_mr_seeds"
    }
    MAIN_WORKFLOW(
        params.catalogues,
        params.crystals,
        params.config,
        params.database_manifest,
        params.phenix_manifest,
        params.cache_root.toString(),
        params.review_mode,
        params.profile_mode,
        params.analysis_stage,
        params.approved_mr_seeds,
        params.skip_xtriage,
        params.maximum_hits_per_query,
        params.maximum_evalue.toFloat(),
        params.minimum_query_coverage.toFloat(),
        params.maximum_query_length,
        params.prostt5_maximum_hits_per_query,
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
        params.maximum_first_copy_jobs
    )
}
