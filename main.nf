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
    heteromer_control_preparation: Path? = null
    partner_copy_count: Integer = 1
    profile_mode: String = 'smoke'
    analysis_stage: String = 'task05'
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
    phase3_joint_first_copy: Boolean = false
    phase3_crystallographic_review_stage: Path? = null
    phase3_execution_identity: Path? = null
    phase3_owned_parent_run_id: String? = null
    phase3_a_seed_review_stage: Path? = null
    phase3_a_seed_review_package: Path? = null
    phase3_reviewed_crystal_manifest: Path? = null
    phase3_owned_run_registry: Path? = null
    phase3_owned_sequence_parent_run_id: String? = null
}

workflow {
    main:
    if (!(params.analysis_stage in [
        'task05',
        'discovery',
        'first_copy',
        'additional_copy',
        'heteromer',
        't12'
    ])) {
        error "Unsupported analysis_stage: ${params.analysis_stage}"
    }
    if (
        params.analysis_stage in ['additional_copy', 'heteromer', 't12'] &&
        params.approved_mr_seeds == null &&
        params.phase3_a_seed_review_stage == null &&
        params.phase3_reviewed_crystal_manifest == null
    ) {
        error "analysis_stage=${params.analysis_stage} requires --approved_mr_seeds"
    }
    def phase3SeedInputs = [
        params.phase3_a_seed_review_stage,
        params.phase3_a_seed_review_package
    ]
    if (phase3SeedInputs.any { item -> item != null }) {
        if (phase3SeedInputs.any { item -> item == null }) {
            error 'Phase III A-seed execution requires its stage and owned package'
        }
        if (!(params.analysis_stage in ['additional_copy', 't12'])) {
            error 'Phase III A-seed decisions permit only same-component or refinement execution'
        }
        if (
            params.approved_mr_seeds != null ||
            !params.phase3_joint_first_copy ||
            params.phase3_owned_run_registry == null ||
            params.phase3_execution_identity == null ||
            params.phase3_owned_parent_run_id == null
        ) {
            error 'Phase III A-seed execution requires joint hypotheses and no legacy decision override'
        }
    }
    if (params.phase3_reviewed_crystal_manifest != null) {
        if (
            params.analysis_stage != 't12' ||
            !params.phase3_joint_first_copy ||
            params.phase3_owned_run_registry == null ||
            params.phase3_execution_identity == null ||
            params.phase3_owned_parent_run_id == null ||
            params.phase3_crystallographic_review_stage != null ||
            params.approved_mr_seeds != null ||
            phase3SeedInputs.any { item -> item != null }
        ) {
            error 'Reviewed Phase III continuation requires its exact owned screen, execution identity, and T12 stage'
        }
        if (
            params.phase3_owned_sequence_parent_run_id == null ||
            params.phase3_owned_sequence_parent_run_id ==
            params.phase3_owned_parent_run_id
        ) {
            error 'Owned Phase III final reviews require a distinct single-component run'
        }
    } else if (params.phase3_owned_run_registry != null) {
        error 'A Phase III owned-run registry requires reviewed multi-crystal continuation'
    }
    if (
        params.phase3_owned_sequence_parent_run_id != null &&
        params.phase3_reviewed_crystal_manifest == null
    ) {
        error 'Owned Phase III sequence packages require their separate reviewed single-component run'
    }
    if (params.analysis_stage == 'heteromer' && params.partner_copy_count < 1) {
        error 'analysis_stage=heteromer requires a positive --partner_copy_count'
    }
    if (
        params.phase3_reviewed_crystal_manifest == null &&
        (
            (params.phase3_crystallographic_review_stage == null) !=
            (params.phase3_execution_identity == null)
        )
    ) {
        error 'Phase III crystallographic reviews require both staged decisions and execution identity'
    }
    if (
        params.phase3_crystallographic_review_stage != null &&
        (params.analysis_stage != 'first_copy' || !params.phase3_joint_first_copy)
    ) {
        error 'Phase III crystallographic reviews require explicit joint first-copy mode'
    }
    if (
        params.phase3_owned_parent_run_id != null &&
        params.phase3_reviewed_crystal_manifest == null &&
        (
            params.analysis_stage != 'first_copy' ||
            !params.phase3_joint_first_copy ||
            params.phase3_crystallographic_review_stage == null ||
            params.phase3_execution_identity == null
        )
    ) {
        error 'Owned Phase III A packages require reviewed joint first-copy execution'
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
        params.heteromer_control_preparation,
        params.partner_copy_count,
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
        params.phase3_joint_first_copy,
        params.phase3_crystallographic_review_stage,
        params.phase3_execution_identity,
        params.phase3_owned_parent_run_id,
        params.phase3_a_seed_review_stage,
        params.phase3_a_seed_review_package,
        params.phase3_reviewed_crystal_manifest,
        params.phase3_owned_run_registry,
        params.phase3_owned_sequence_parent_run_id
    )
}
