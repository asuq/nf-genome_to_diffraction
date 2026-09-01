#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { PDB_SEQUENCE_DISCOVERY } from './workflows/pdb_sequence_discovery_workflow'
include { REGISTER_PDB_COORDINATES } from './modules/local/register_pdb_coordinates'
include { PREPARE_PREDICTED_MODELS } from './modules/local/prepare_predicted_models'
include { PREPARE_EXPERIMENTAL_MODELS } from './modules/local/prepare_experimental_models'
include { FIRST_COPY_MR_WORKFLOW } from './workflows/first_copy_mr_workflow'
include { DIVERSE_FIRST_COPY_MR_WORKFLOW } from './workflows/diverse_first_copy_mr_workflow'
include { CONTROL_FIRST_COPY_MR_WORKFLOW } from './workflows/control_first_copy_mr_workflow'
include { ADDITIONAL_COPY_WORKFLOW } from './workflows/additional_copy_workflow'
include { BRIEF_REFINEMENT_WORKFLOW } from './workflows/brief_refinement_workflow'
include { PHASE3_NETWORK_PROBE_WORKFLOW } from './workflows/qualification/phase3_network_probe'

params {
    qualification_stage: String
    sequence_groups: Path? = null
    source_records: Path? = null
    config: Path? = null
    database_manifest: Path? = null
    structural_hits: Path? = null
    pdb_search_results: Path? = null
    foldseek_search_results: Path? = null
    coordinate_sources: Path? = null
    provider_search_results: Path? = null
    coordinate_hit_mappings: Path? = null
    registration_manifest: Path? = null
    prepared_models: Path? = null
    predicted_coordinate_sources: Path? = null
    predicted_prepared_models: Path? = null
    pdb_coordinate_sources: Path? = null
    experimental_prepared_models: Path? = null
    matthews: Path? = null
    preflight: Path? = null
    control_bundle: Path? = null
    seeds: Path? = null
    review_validation: Path? = null
    review_package: Path? = null
    hypotheses: Path? = null
    finalists: Path? = null
    mtz: Path? = null
    phenix_manifest: Path? = null
    crystal_id: String? = null
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
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
    maximum_hits_per_sequence_group: Integer = 3
    maximum_mappings: Integer = 25
    maximum_first_copy_jobs: Integer = 25
    outer_job_id: String? = null
    outer_network_namespace: String? = null
}

workflow {
    main:
    def supported = [
        'discovery',
        'register_coordinates',
        'prepare_predicted_models',
        'prepare_experimental_models',
        'first_copy',
        'diverse_first_copy',
        'first_copy_controls',
        'additional_copy',
        'refine_finalists',
        'phase3_network_probe'
    ]
    if (!(params.qualification_stage in supported)) {
        error "Unsupported qualification_stage: ${params.qualification_stage}"
    }

    if (params.qualification_stage == 'discovery') {
        if (
            params.sequence_groups == null ||
            params.source_records == null ||
            params.config == null ||
            params.database_manifest == null
        ) {
            error 'discovery qualification requires sequence, source, configuration, and database inputs'
        }
        PDB_SEQUENCE_DISCOVERY(
            params.sequence_groups as Path,
            params.source_records as Path,
            params.config as Path,
            params.database_manifest as Path,
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
            false,
            true
        )
    } else if (params.qualification_stage == 'register_coordinates') {
        if (
            params.structural_hits == null ||
            params.sequence_groups == null ||
            params.database_manifest == null
        ) {
            error 'coordinate qualification requires hits, sequence, and database inputs'
        }
        REGISTER_PDB_COORDINATES(
            params.structural_hits as Path,
            params.pdb_search_results,
            params.foldseek_search_results,
            params.sequence_groups as Path,
            params.database_manifest as Path,
            params.maximum_hits_per_sequence_group,
            params.maximum_mappings
        )
    } else if (params.qualification_stage == 'prepare_predicted_models') {
        if (
            params.coordinate_sources == null ||
            params.sequence_groups == null ||
            params.phenix_manifest == null
        ) {
            error 'predicted-model qualification requires coordinate, sequence, and Phenix inputs'
        }
        PREPARE_PREDICTED_MODELS(
            params.coordinate_sources as Path,
            params.provider_search_results,
            params.sequence_groups as Path,
            params.phenix_manifest as Path
        )
    } else if (params.qualification_stage == 'prepare_experimental_models') {
        if (
            params.coordinate_sources == null ||
            params.coordinate_hit_mappings == null ||
            params.sequence_groups == null
        ) {
            error 'experimental-model qualification requires coordinates, mappings, and sequences'
        }
        PREPARE_EXPERIMENTAL_MODELS(
            params.coordinate_sources as Path,
            params.coordinate_hit_mappings as Path,
            params.registration_manifest,
            params.sequence_groups as Path
        )
    } else if (params.qualification_stage == 'first_copy') {
        if (
            params.coordinate_sources == null ||
            params.prepared_models == null ||
            params.sequence_groups == null ||
            params.matthews == null ||
            params.preflight == null ||
            params.config == null ||
            params.crystal_id == null ||
            params.mtz == null ||
            params.phenix_manifest == null
        ) {
            error 'first-copy qualification requires its complete crystal/model authority'
        }
        FIRST_COPY_MR_WORKFLOW(
            params.coordinate_sources as Path,
            params.prepared_models as Path,
            params.sequence_groups as Path,
            params.matthews as Path,
            params.preflight as Path,
            params.config as Path,
            params.crystal_id as String,
            params.mtz as Path,
            params.phenix_manifest as Path
        )
    } else if (params.qualification_stage == 'diverse_first_copy') {
        if (
            params.predicted_coordinate_sources == null ||
            params.predicted_prepared_models == null ||
            params.pdb_coordinate_sources == null ||
            params.coordinate_hit_mappings == null ||
            params.experimental_prepared_models == null ||
            params.sequence_groups == null ||
            params.matthews == null ||
            params.preflight == null ||
            params.config == null ||
            params.crystal_id == null ||
            params.mtz == null ||
            params.phenix_manifest == null
        ) {
            error 'diverse first-copy qualification requires its complete crystal/model authority'
        }
        DIVERSE_FIRST_COPY_MR_WORKFLOW(
            params.predicted_coordinate_sources as Path,
            params.predicted_prepared_models as Path,
            params.pdb_coordinate_sources as Path,
            params.coordinate_hit_mappings as Path,
            params.experimental_prepared_models as Path,
            params.sequence_groups as Path,
            params.matthews as Path,
            params.preflight as Path,
            params.config as Path,
            params.crystal_id as String,
            params.maximum_first_copy_jobs,
            params.mtz as Path,
            params.phenix_manifest as Path
        )
    } else if (params.qualification_stage == 'first_copy_controls') {
        if (
            params.control_bundle == null ||
            params.sequence_groups == null ||
            params.preflight == null ||
            params.mtz == null ||
            params.phenix_manifest == null
        ) {
            error 'first-copy controls require their complete fixed authority'
        }
        CONTROL_FIRST_COPY_MR_WORKFLOW(
            channel.of(params.control_bundle as Path),
            params.sequence_groups as Path,
            params.preflight as Path,
            params.mtz as Path,
            params.phenix_manifest as Path
        )
    } else if (params.qualification_stage == 'additional_copy') {
        if (
            params.seeds == null ||
            params.review_validation == null ||
            params.review_package == null ||
            params.hypotheses == null ||
            params.sequence_groups == null ||
            params.preflight == null ||
            params.mtz == null ||
            params.phenix_manifest == null
        ) {
            error 'additional-copy qualification requires its complete reviewed authority'
        }
        ADDITIONAL_COPY_WORKFLOW(
            channel.of(params.seeds as Path),
            params.review_validation as Path,
            params.review_package as Path,
            params.hypotheses as Path,
            params.sequence_groups as Path,
            params.preflight as Path,
            params.mtz as Path,
            params.phenix_manifest as Path
        )
    } else if (params.qualification_stage == 'refine_finalists') {
        if (
            params.finalists == null ||
            params.sequence_groups == null ||
            params.source_records == null ||
            params.phenix_manifest == null
        ) {
            error 'refinement qualification requires finalist, sequence, source, and Phenix inputs'
        }
        BRIEF_REFINEMENT_WORKFLOW(
            channel.of(params.finalists as Path),
            params.sequence_groups as Path,
            params.source_records as Path,
            params.phenix_manifest as Path
        )
    } else {
        if (
            params.outer_job_id == null ||
            params.outer_network_namespace == null
        ) {
            error 'Phase III network probe requires its fixed outer scheduler and namespace identities'
        }
        PHASE3_NETWORK_PROBE_WORKFLOW()
    }
}
