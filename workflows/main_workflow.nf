nextflow.enable.types = true

include { ENUMERATE_MATTHEWS } from '../modules/local/enumerate_matthews'
include { IMPORT_CATALOGUES } from '../modules/local/import_catalogues'
include { MTZ_PREFLIGHT } from '../modules/local/mtz_preflight'
include { PREPARE_EXPERIMENTAL_MODELS } from '../modules/local/prepare_experimental_models'
include { PREPARE_PREDICTED_MODELS } from '../modules/local/prepare_predicted_models'
include { REGISTER_PDB_COORDINATES } from '../modules/local/register_pdb_coordinates'
include { VALIDATE_TASK05_INPUTS } from '../modules/local/validate_task05_inputs'
include { PDB_SEQUENCE_DISCOVERY } from './pdb_sequence_discovery_workflow'

workflow MAIN_WORKFLOW {
    take:
    catalogues: Path
    crystals: Path
    pipeline_config: Path
    database_manifest: Path
    phenix_manifest: Path
    cache_root: String
    review_mode: String
    profile_mode: String
    analysis_stage: String
    skip_xtriage: Boolean
    maximum_hits_per_query: Integer
    maximum_evalue: Float
    minimum_query_coverage: Float
    maximum_query_length: Integer
    prostt5_maximum_hits_per_query: Integer
    prostt5_maximum_evalue: Float
    prostt5_minimum_query_coverage: Float
    prostt5_maximum_query_length: Integer
    prostt5_maximum_queries: Integer
    prostt5_gpu: Boolean
    afdb_accession_map: Path?
    afdb_request_timeout_seconds: Float
    afdb_retry_count: Integer
    maximum_pdb_hits_per_sequence_group: Integer
    maximum_pdb_mappings: Integer

    main:
    validation_scope = VALIDATE_TASK05_INPUTS(
        catalogues,
        crystals,
        pipeline_config,
        database_manifest,
        phenix_manifest,
        cache_root,
        review_mode,
        profile_mode,
        analysis_stage
    )
    catalogue_bundle = IMPORT_CATALOGUES(
        catalogues,
        pipeline_config,
        validation_scope
    )
    preflight_bundle = MTZ_PREFLIGHT(
        crystals,
        phenix_manifest,
        skip_xtriage,
        validation_scope
    )
    matthews_bundle = ENUMERATE_MATTHEWS(
        crystals,
        pipeline_config,
        preflight_bundle,
        catalogue_bundle
    )

    if (analysis_stage == 'discovery') {
        sequence_groups = catalogue_bundle.map { Path bundle ->
            bundle.resolve('sequence_groups.jsonl')
        }
        source_records = catalogue_bundle.map { Path bundle ->
            bundle.resolve('source_records.jsonl')
        }
        discovery = PDB_SEQUENCE_DISCOVERY(
            sequence_groups,
            source_records,
            database_manifest,
            maximum_hits_per_query,
            maximum_evalue,
            minimum_query_coverage,
            maximum_query_length,
            prostt5_maximum_hits_per_query,
            prostt5_maximum_evalue,
            prostt5_minimum_query_coverage,
            prostt5_maximum_query_length,
            prostt5_maximum_queries,
            prostt5_gpu,
            afdb_accession_map,
            afdb_request_timeout_seconds,
            afdb_retry_count
        )
        direct_pdb_hits = discovery.pdb_sequence_search.map { Path bundle ->
            bundle.resolve('structural_hits.jsonl')
        }
        pdb_registration = REGISTER_PDB_COORDINATES(
            direct_pdb_hits,
            sequence_groups,
            database_manifest,
            maximum_pdb_hits_per_sequence_group,
            maximum_pdb_mappings
        )
        predicted_coordinate_sources = discovery.afdb_exact_search.map {
            Path bundle -> bundle.resolve('coordinate_sources.jsonl')
        }
        PREPARE_PREDICTED_MODELS(
            predicted_coordinate_sources,
            sequence_groups,
            phenix_manifest
        )
        pdb_coordinate_sources = pdb_registration.map { Path bundle ->
            bundle.resolve('coordinate_sources.jsonl')
        }
        coordinate_hit_mappings = pdb_registration.map { Path bundle ->
            bundle.resolve('coordinate_hit_mappings.jsonl')
        }
        PREPARE_EXPERIMENTAL_MODELS(
            pdb_coordinate_sources,
            coordinate_hit_mappings,
            sequence_groups
        )
    }

    emit:
    scope: Path = validation_scope
    catalogue: Path = catalogue_bundle
    preflight: Path = preflight_bundle
    matthews: Path = matthews_bundle
}
