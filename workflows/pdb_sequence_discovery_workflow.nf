nextflow.enable.types = true

include { EMIT_DISABLED_PROVIDER_BUNDLE as EMIT_DISABLED_AFDB } from '../modules/local/emit_disabled_provider_bundle'
include { EMIT_DISABLED_PROVIDER_BUNDLE as EMIT_DISABLED_ESM } from '../modules/local/emit_disabled_provider_bundle'
include { EMIT_DISABLED_PROVIDER_BUNDLE as EMIT_DISABLED_FOLDSEEK } from '../modules/local/emit_disabled_provider_bundle'
include { EMIT_DISABLED_PROVIDER_BUNDLE as EMIT_DISABLED_PDB } from '../modules/local/emit_disabled_provider_bundle'
include { MERGE_PDB_PROVIDER_HITS } from '../modules/local/merge_pdb_provider_hits'
include {
    PLAN_PHASE3_FOLDSEEK_BATCHES;
    SEARCH_PHASE3_FOLDSEEK_BATCH;
    MERGE_PHASE3_FOLDSEEK_BATCHES
} from '../modules/local/phase3_foldseek_batch_tasks'
include { RESOLVE_PROVIDER_PLAN } from '../modules/local/resolve_provider_plan'
include { RETRIEVE_AFDB_EXACT } from '../modules/local/retrieve_afdb_exact'
include { SEARCH_FOLDSEEK_PROSTT5 } from '../modules/local/search_foldseek_prostt5'
include { SEARCH_PDB_SEQUENCES } from '../modules/local/search_pdb_sequences'

workflow PDB_SEQUENCE_DISCOVERY {
    take:
    sequence_groups: Path
    source_records: Path
    pipeline_config: Path
    database_manifest: Path
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
    phase3_full_catalogue_batches: Boolean

    main:
    plan_bundle = RESOLVE_PROVIDER_PLAN(pipeline_config, database_manifest)
    provider_routes = plan_bundle.flatMap { Path bundle ->
        ['afdb_exact', 'esm_atlas', 'foldseek_prostt5_pdb', 'pdb_sequence']
            .collect { String providerKey ->
                Path plan = bundle.resolve('provider_plan.json')
                Path entry = bundle.resolve("entries/${providerKey}.json")
                def document = new groovy.json.JsonSlurper().parse(entry.toFile())
                tuple(providerKey, document.enabled as Boolean, plan, entry)
            }
    }

    pdb_enabled_plan = provider_routes
        .filter { key, enabled, plan, entry -> key == 'pdb_sequence' && enabled }
        .map { key, enabled, plan, entry -> plan as Path }
    pdb_enabled_entry = provider_routes
        .filter { key, enabled, plan, entry -> key == 'pdb_sequence' && enabled }
        .map { key, enabled, plan, entry -> entry as Path }
    pdb_disabled_entry = provider_routes
        .filter { key, enabled, plan, entry -> key == 'pdb_sequence' && !enabled }
        .map { key, enabled, plan, entry -> entry as Path }
    pdb_enabled_bundle = SEARCH_PDB_SEQUENCES(
        sequence_groups,
        database_manifest,
        pdb_enabled_plan,
        pdb_enabled_entry,
        maximum_evalue,
        minimum_query_coverage,
        maximum_query_length
    )
    pdb_disabled_bundle = EMIT_DISABLED_PDB(
        'pdb_sequence',
        'pdb_sequence_search',
        sequence_groups,
        pdb_disabled_entry
    )
    search_bundle = pdb_enabled_bundle.mix(pdb_disabled_bundle).first()

    foldseek_enabled_plan = provider_routes
        .filter { key, enabled, plan, entry ->
            key == 'foldseek_prostt5_pdb' && enabled
        }
        .map { key, enabled, plan, entry -> plan as Path }
    foldseek_enabled_entry = provider_routes
        .filter { key, enabled, plan, entry ->
            key == 'foldseek_prostt5_pdb' && enabled
        }
        .map { key, enabled, plan, entry -> entry as Path }
    foldseek_disabled_entry = provider_routes
        .filter { key, enabled, plan, entry ->
            key == 'foldseek_prostt5_pdb' && !enabled
        }
        .map { key, enabled, plan, entry -> entry as Path }
    if (phase3_full_catalogue_batches) {
        foldseek_batch_plan = PLAN_PHASE3_FOLDSEEK_BATCHES(
            sequence_groups,
            foldseek_enabled_plan,
            foldseek_enabled_entry
        )
        foldseek_batch_tasks = foldseek_batch_plan.first().flatMap { Path bundle ->
            def document = new groovy.json.JsonSlurper().parse(
                bundle.resolve('batch_plan.json').toFile()
            )
            document.batches.collect { batch ->
                tuple(
                    batch.batch_id as String,
                    file(bundle.resolve("batches/${batch.batch_id}"), checkIfExists: true)
                )
            }
        }
        foldseek_batch_results = SEARCH_PHASE3_FOLDSEEK_BATCH(
            foldseek_batch_tasks,
            channel.value(database_manifest),
            foldseek_enabled_plan.first(),
            foldseek_enabled_entry.first(),
            prostt5_maximum_evalue,
            prostt5_minimum_query_coverage,
            prostt5_maximum_query_length,
            prostt5_gpu
        )
        complete_foldseek_batches = foldseek_batch_results
            .collect()
            .map { values ->
                values.sort { left, right ->
                        (left[0] as String) <=> (right[0] as String)
                    }
                    .collect { row -> row[1] as Path }
            }
        prostt5_enabled_bundle = MERGE_PHASE3_FOLDSEEK_BATCHES(
            sequence_groups,
            foldseek_batch_plan.first(),
            complete_foldseek_batches
        )
    } else {
        prostt5_enabled_bundle = SEARCH_FOLDSEEK_PROSTT5(
            sequence_groups,
            database_manifest,
            foldseek_enabled_plan,
            foldseek_enabled_entry,
            prostt5_maximum_evalue,
            prostt5_minimum_query_coverage,
            prostt5_maximum_query_length,
            prostt5_maximum_queries,
            prostt5_gpu
        )
    }
    prostt5_disabled_bundle = EMIT_DISABLED_FOLDSEEK(
        'foldseek_prostt5_pdb',
        'prostt5_foldseek_search',
        sequence_groups,
        foldseek_disabled_entry
    )
    prostt5_bundle = prostt5_enabled_bundle.mix(prostt5_disabled_bundle).first()

    afdb_enabled_plan = provider_routes
        .filter { key, enabled, plan, entry -> key == 'afdb_exact' && enabled }
        .map { key, enabled, plan, entry -> plan as Path }
    afdb_enabled_entry = provider_routes
        .filter { key, enabled, plan, entry -> key == 'afdb_exact' && enabled }
        .map { key, enabled, plan, entry -> entry as Path }
    afdb_disabled_entry = provider_routes
        .filter { key, enabled, plan, entry -> key == 'afdb_exact' && !enabled }
        .map { key, enabled, plan, entry -> entry as Path }
    afdb_enabled_bundle = RETRIEVE_AFDB_EXACT(
        sequence_groups,
        source_records,
        database_manifest,
        afdb_enabled_plan,
        afdb_enabled_entry,
        afdb_accession_map,
        afdb_request_timeout_seconds,
        afdb_retry_count
    )
    afdb_disabled_bundle = EMIT_DISABLED_AFDB(
        'afdb_exact',
        'afdb_exact_search',
        sequence_groups,
        afdb_disabled_entry
    )
    afdb_bundle = afdb_enabled_bundle.mix(afdb_disabled_bundle).first()

    esm_disabled_entry = provider_routes
        .filter { key, enabled, plan, entry -> key == 'esm_atlas' && !enabled }
        .map { key, enabled, plan, entry -> entry as Path }
    esm_bundle = EMIT_DISABLED_ESM(
        'esm_atlas',
        'esm_atlas_search',
        sequence_groups,
        esm_disabled_entry
    )
    pdb_hits = search_bundle.map { Path bundle ->
        bundle.resolve('structural_hits.jsonl')
    }
    foldseek_hits = prostt5_bundle.map { Path bundle ->
        bundle.resolve('structural_hits.jsonl')
    }
    merged_pdb_hits = MERGE_PDB_PROVIDER_HITS(pdb_hits, foldseek_hits)

    emit:
    provider_plan: Path = plan_bundle
    pdb_sequence_search: Path = search_bundle
    prostt5_foldseek_search: Path = prostt5_bundle
    afdb_exact_search: Path = afdb_bundle
    esm_atlas_search: Path = esm_bundle
    pdb_provider_hits: Path = merged_pdb_hits
}
