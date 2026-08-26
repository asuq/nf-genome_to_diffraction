nextflow.enable.types = true

include { IMPORT_CATALOGUES } from '../modules/local/import_catalogues'
include { MTZ_PREFLIGHT } from '../modules/local/mtz_preflight'
include { ENUMERATE_MATTHEWS } from '../modules/local/enumerate_matthews'
include { PREPARE_EXPERIMENTAL_MODELS } from '../modules/local/prepare_experimental_models'
include { PREPARE_PREDICTED_MODELS } from '../modules/local/prepare_predicted_models'
include { REGISTER_PDB_COORDINATES } from '../modules/local/register_pdb_coordinates'
include { VALIDATE_TASK05_INPUTS } from '../modules/local/validate_task05_inputs'
include { CRYSTAL_FANOUT_WORKFLOW } from './crystal_fanout_workflow'
include { PDB_SEQUENCE_DISCOVERY } from './pdb_sequence_discovery_workflow'
include {
    PHASE3_MULTICRYSTAL_FIRST_COPY_WORKFLOW
} from './phase3_multicrystal_first_copy_workflow'
include {
    PHASE3_REVIEWED_SINGLE_COMPONENT_WORKFLOW
} from './phase3_reviewed_single_component_workflow'
include {
    VALIDATE_PHASE3_CRYSTALLOGRAPHIC_REVIEWS as VALIDATE_PHASE3_PROVIDER_DISCOVERY_REVIEWS
} from '../modules/local/phase3_multicrystal_first_copy_tasks'
include {
    PACKAGE_PHASE3_PROVIDER_DISCOVERY
} from '../modules/local/package_phase3_provider_discovery'


// Provider discovery is a separate offline compute checkpoint. It validates
// the exact three-crystal review authority, imports the catalogue once, and
// runs only local PDB/MMseqs2 plus ProstT5/Foldseek searches. AFDB retrieval and
// PDB coordinate acquisition remain absent until bounded login-side staging.
workflow PHASE3_PROVIDER_DISCOVERY_APPLICATION_WORKFLOW {
    take:
    catalogues: Path
    crystals: Path
    pipeline_config: Path
    database_manifest: Path
    phenix_manifest: Path
    cache_root: String
    review_mode: String
    profile_mode: String
    maximum_evalue: Float
    minimum_query_coverage: Float
    maximum_query_length: Integer
    prostt5_maximum_evalue: Float
    prostt5_minimum_query_coverage: Float
    prostt5_maximum_query_length: Integer
    prostt5_maximum_queries: Integer
    prostt5_gpu: Boolean
    afdb_accession_map: Path
    afdb_request_timeout_seconds: Float
    afdb_retry_count: Integer
    crystallographic_review_stage: Path
    execution_identity: Path
    owned_run_id: String

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
        'discovery'
    )
    review_bundle = VALIDATE_PHASE3_PROVIDER_DISCOVERY_REVIEWS(
        crystallographic_review_stage,
        execution_identity,
        crystals
    )
    reviewed_scope = validation_scope
        .combine(review_bundle)
        .map { Path scope, Path _reviews -> scope }
    catalogue_bundle = IMPORT_CATALOGUES(
        catalogues,
        pipeline_config,
        reviewed_scope
    )
    sequence_groups = catalogue_bundle.map { Path bundle ->
        bundle.resolve('sequence_groups.jsonl')
    }
    source_records = catalogue_bundle.map { Path bundle ->
        bundle.resolve('source_records.jsonl')
    }
    discovery = PDB_SEQUENCE_DISCOVERY(
        sequence_groups,
        source_records,
        pipeline_config,
        database_manifest,
        maximum_evalue,
        minimum_query_coverage,
        maximum_query_length,
        prostt5_maximum_evalue,
        prostt5_minimum_query_coverage,
        prostt5_maximum_query_length,
        prostt5_maximum_queries,
        prostt5_gpu,
        afdb_accession_map,
        afdb_request_timeout_seconds,
        afdb_retry_count,
        true,
        false
    )
    discovery_package = PACKAGE_PHASE3_PROVIDER_DISCOVERY(
        owned_run_id,
        execution_identity,
        pipeline_config,
        database_manifest,
        review_bundle,
        catalogue_bundle,
        discovery.provider_plan,
        discovery.pdb_sequence_search,
        discovery.prostt5_foldseek_search,
        discovery.pdb_provider_hits,
        afdb_accession_map
    )

    emit:
    scope: Path = validation_scope
    reviews: Path = review_bundle
    catalogue: Path = catalogue_bundle
    provider_plan: Path = discovery.provider_plan
    pdb_sequence_search: Path = discovery.pdb_sequence_search
    prostt5_foldseek_search: Path = discovery.prostt5_foldseek_search
    pdb_provider_hits: Path = discovery.pdb_provider_hits
    checkpoint: Path = discovery_package
}


// Current Phase III A screening has one authority: reviewed joint multi-crystal
// execution. It never accepts a legacy approval TSV or a single-crystal switch.
workflow PHASE3_FIRST_COPY_APPLICATION_WORKFLOW {
    take:
    catalogues: Path
    crystals: Path
    pipeline_config: Path
    database_manifest: Path
    phenix_manifest: Path
    cache_root: String
    review_mode: String
    profile_mode: String
    skip_xtriage: Boolean
    maximum_evalue: Float
    minimum_query_coverage: Float
    maximum_query_length: Integer
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
    maximum_first_copy_jobs: Integer
    crystallographic_review_stage: Path
    execution_identity: Path
    owned_parent_run_id: String

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
        'first_copy'
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
    sequence_groups = catalogue_bundle.map { Path bundle ->
        bundle.resolve('sequence_groups.jsonl')
    }
    source_records = catalogue_bundle.map { Path bundle ->
        bundle.resolve('source_records.jsonl')
    }
    discovery = PDB_SEQUENCE_DISCOVERY(
        sequence_groups,
        source_records,
        pipeline_config,
        database_manifest,
        maximum_evalue,
        minimum_query_coverage,
        maximum_query_length,
        prostt5_maximum_evalue,
        prostt5_minimum_query_coverage,
        prostt5_maximum_query_length,
        prostt5_maximum_queries,
        prostt5_gpu,
        afdb_accession_map,
        afdb_request_timeout_seconds,
        afdb_retry_count,
        true,
        true
    )
    direct_pdb_hits = discovery.pdb_provider_hits.map { Path bundle ->
        bundle.resolve('structural_hits.jsonl')
    }
    pdb_search_results = discovery.pdb_sequence_search.map { Path bundle ->
        bundle.resolve('search_results.jsonl')
    }
    foldseek_search_results = discovery.prostt5_foldseek_search.map {
        Path bundle -> bundle.resolve('search_results.jsonl')
    }
    pdb_registration = REGISTER_PDB_COORDINATES(
        direct_pdb_hits,
        pdb_search_results,
        foldseek_search_results,
        sequence_groups,
        database_manifest,
        maximum_pdb_hits_per_sequence_group,
        maximum_pdb_mappings
    )
    predicted_coordinate_sources = discovery.afdb_exact_search.map {
        Path bundle -> bundle.resolve('coordinate_sources.jsonl')
    }
    predicted_search_results = discovery.afdb_exact_search.map {
        Path bundle -> bundle.resolve('search_results.jsonl')
    }
    predicted_models = PREPARE_PREDICTED_MODELS(
        predicted_coordinate_sources,
        predicted_search_results,
        sequence_groups,
        phenix_manifest
    )
    pdb_coordinate_sources = pdb_registration.map { Path bundle ->
        bundle.resolve('coordinate_sources.jsonl')
    }
    coordinate_hit_mappings = pdb_registration.map { Path bundle ->
        bundle.resolve('coordinate_hit_mappings.jsonl')
    }
    registration_manifest = pdb_registration.map { Path bundle ->
        bundle.resolve('registration_manifest.json')
    }
    experimental_models = PREPARE_EXPERIMENTAL_MODELS(
        pdb_coordinate_sources,
        coordinate_hit_mappings,
        registration_manifest,
        sequence_groups
    )
    matthews_jsonl = matthews_bundle.map { Path bundle ->
        bundle.resolve('matthews_hypotheses.jsonl')
    }
    preflight_jsonl = preflight_bundle.map { Path bundle ->
        bundle.resolve('mtz_preflight.jsonl')
    }
    PHASE3_MULTICRYSTAL_FIRST_COPY_WORKFLOW(
        channel.value(crystals),
        preflight_jsonl,
        catalogue_bundle,
        pdb_registration,
        predicted_coordinate_sources,
        predicted_models,
        pdb_coordinate_sources,
        coordinate_hit_mappings,
        experimental_models,
        matthews_jsonl,
        channel.value(pipeline_config.toAbsolutePath()),
        maximum_first_copy_jobs,
        channel.value(phenix_manifest.toAbsolutePath()),
        crystallographic_review_stage,
        execution_identity,
        owned_parent_run_id
    )

    emit:
    scope: Path = validation_scope
    catalogue: Path = catalogue_bundle
    preflight: Path = preflight_bundle
    matthews: Path = matthews_bundle
}


// Current Phase III post-A execution has one authority: the completed owned
// screen registry plus its exact per-crystal decision routes.
workflow PHASE3_REVIEWED_SINGLE_COMPONENT_APPLICATION_WORKFLOW {
    take:
    catalogues: Path
    crystals: Path
    pipeline_config: Path
    database_manifest: Path
    phenix_manifest: Path
    cache_root: String
    review_mode: String
    profile_mode: String
    skip_xtriage: Boolean
    reviewed_crystal_manifest: Path
    owned_run_registry: Path
    execution_identity: Path
    owned_parent_run_id: String
    owned_sequence_parent_run_id: String

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
        't12'
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
    def source = new groovy.json.JsonSlurper().parse(
        reviewed_crystal_manifest.toFile()
    )
    def frozen = new groovy.json.JsonSlurper().parse(crystals.toFile())
    def registry = new groovy.json.JsonSlurper().parse(
        owned_run_registry.resolve('phase3_owned_run_registry.json').toFile()
    )
    if (
        registry.run_id != owned_parent_run_id ||
        registry.profile != 'unknown-screen' ||
        registry.phase != 'phase3-pass1'
    ) {
        error 'Reviewed Phase III continuation belongs to another completed screen'
    }
    if (!(source.crystals instanceof List)) {
        error 'Reviewed Phase III continuation requires a crystal route list'
    }
    def frozenIds = (frozen.crystals as List).collect { item ->
        item.crystal_id as String
    }
    def routeIds = (source.crystals as List).collect { item ->
        item.crystal_id as String
    }
    if (routeIds.size() != routeIds.unique(false).size()) {
        error 'Reviewed Phase III continuation repeats a crystal route'
    }
    if (!routeIds.every { String crystalId -> frozenIds.contains(crystalId) }) {
        error 'Reviewed Phase III continuation contains an unknown crystal'
    }
    review_routes = channel.value(reviewed_crystal_manifest)
        .flatMap { Path manifest ->
            def routes = new groovy.json.JsonSlurper().parse(manifest.toFile())
            (routes.crystals as List).collect { item ->
                def required = [
                    'crystal_id',
                    'review_stage',
                    'hypotheses'
                ] as Set
                if (item.keySet() != required) {
                    error 'Reviewed Phase III crystal route differs from its fixed inputs'
                }
                def matches = (registry.packages as List).findAll { owned ->
                    owned.crystal_id == item.crystal_id &&
                        owned.checkpoint == 'a_seed'
                }
                if (matches.size() != 1) {
                    error "Reviewed Phase III crystal lacks its owned A package: ${item.crystal_id}"
                }
                tuple(
                    item.crystal_id as String,
                    file(item.review_stage as String, checkIfExists: true),
                    file(
                        owned_run_registry.resolve(
                            "packages/${matches[0].review_package_id}"
                        ),
                        checkIfExists: true
                    ),
                    file(item.hypotheses as String, checkIfExists: true)
                )
            }
        }
    preflight_jsonl = preflight_bundle.map { Path bundle ->
        bundle.resolve('mtz_preflight.jsonl')
    }
    dispatched = CRYSTAL_FANOUT_WORKFLOW(
        channel.value(crystals),
        preflight_jsonl,
        catalogue_bundle,
        channel.value(owned_run_registry)
    )
    complete_reviews = review_routes
        .join(dispatched, by: 0, failOnDuplicate: true, failOnMismatch: false)
        .combine(preflight_jsonl.first())
        .combine(channel.value(phenix_manifest))
        .map { item, preflight, phenix ->
            Path dispatch = item[4] as Path
            Path catalogue = item[5] as Path
            tuple(
                item[0],
                item[1],
                item[2],
                item[3],
                file(catalogue.resolve('sequence_groups.jsonl'), checkIfExists: true),
                file(catalogue.resolve('source_records.jsonl'), checkIfExists: true),
                preflight,
                file(dispatch.resolve('input.mtz'), checkIfExists: true),
                file((phenix as Path).toAbsolutePath(), checkIfExists: true),
                dispatch
            )
        }
    PHASE3_REVIEWED_SINGLE_COMPONENT_WORKFLOW(
        complete_reviews,
        owned_run_registry,
        execution_identity,
        owned_parent_run_id,
        owned_sequence_parent_run_id
    )
    matthews_bundle = channel.empty()

    emit:
    scope: Path = validation_scope
    catalogue: Path = catalogue_bundle
    preflight: Path = preflight_bundle
    matthews: Path = matthews_bundle
}
