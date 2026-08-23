nextflow.enable.types = true

include { EMIT_DISABLED_PROVIDER_BUNDLE as EMIT_DISABLED_AFDB } from '../modules/local/emit_disabled_provider_bundle'
include { EMIT_DISABLED_PROVIDER_BUNDLE as EMIT_DISABLED_ESM } from '../modules/local/emit_disabled_provider_bundle'
include { EMIT_DISABLED_PROVIDER_BUNDLE as EMIT_DISABLED_FOLDSEEK } from '../modules/local/emit_disabled_provider_bundle'
include { RESOLVE_PROVIDER_PLAN } from '../modules/local/resolve_provider_plan'
include { COMPLETE_PROVIDER_EMPTY_GRAPH; STUB_LOCAL_PROVIDER_NO_HIT } from '../modules/local/provider_empty_graph_tasks'

workflow PROVIDER_EMPTY_GRAPH_WORKFLOW {
    take:
    sequence_groups: Path
    pipeline_config: Path
    database_manifest: Path
    stub_helper: Path

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

    pdb_plan = provider_routes
        .filter { key, enabled, plan, entry -> key == 'pdb_sequence' && enabled }
        .map { key, enabled, plan, entry -> plan as Path }
    pdb_entry = provider_routes
        .filter { key, enabled, plan, entry -> key == 'pdb_sequence' && enabled }
        .map { key, enabled, plan, entry -> entry as Path }
    pdb_bundle = STUB_LOCAL_PROVIDER_NO_HIT(
        pdb_plan,
        pdb_entry,
        database_manifest,
        sequence_groups,
        stub_helper
    )

    afdb_entry = provider_routes
        .filter { key, enabled, plan, entry -> key == 'afdb_exact' && !enabled }
        .map { key, enabled, plan, entry -> entry as Path }
    afdb_bundle = EMIT_DISABLED_AFDB(
        'afdb_exact',
        'afdb_exact_search',
        sequence_groups,
        afdb_entry
    )
    esm_entry = provider_routes
        .filter { key, enabled, plan, entry -> key == 'esm_atlas' && !enabled }
        .map { key, enabled, plan, entry -> entry as Path }
    esm_bundle = EMIT_DISABLED_ESM(
        'esm_atlas',
        'esm_atlas_search',
        sequence_groups,
        esm_entry
    )
    foldseek_entry = provider_routes
        .filter { key, enabled, plan, entry ->
            key == 'foldseek_prostt5_pdb' && !enabled
        }
        .map { key, enabled, plan, entry -> entry as Path }
    foldseek_bundle = EMIT_DISABLED_FOLDSEEK(
        'foldseek_prostt5_pdb',
        'prostt5_foldseek_search',
        sequence_groups,
        foldseek_entry
    )

    bundles = pdb_bundle
        .mix(afdb_bundle, esm_bundle, foldseek_bundle)
        .collect()
        .map { values ->
            def ordered = values.sort { left, right -> left.name <=> right.name }
            tuple(ordered[0], ordered[1], ordered[2], ordered[3])
        }
    provider_plan = plan_bundle.map { Path bundle ->
        bundle.resolve('provider_plan.json')
    }
    completion = COMPLETE_PROVIDER_EMPTY_GRAPH(
        pipeline_config,
        provider_plan,
        sequence_groups,
        bundles
    )

    emit:
    provider_plan: Path = plan_bundle
    completed_no_model: Path = completion
}
