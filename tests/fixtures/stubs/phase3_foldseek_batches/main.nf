#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { RESOLVE_PROVIDER_PLAN } from '../../../../modules/local/resolve_provider_plan'
include {
    PLAN_PHASE3_FOLDSEEK_BATCHES;
    SEARCH_PHASE3_FOLDSEEK_BATCH;
    MERGE_PHASE3_FOLDSEEK_BATCHES
} from '../../../../modules/local/phase3_foldseek_batch_tasks'

params {
    sequence_groups: Path
    config: Path
    database_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    provider = RESOLVE_PROVIDER_PLAN(
        channel.value(params.config),
        channel.value(params.database_manifest)
    )
    provider_plan = provider.map { Path bundle ->
        bundle.resolve('provider_plan.json')
    }.first()
    provider_entry = provider.map { Path bundle ->
        bundle.resolve('entries/foldseek_prostt5_pdb.json')
    }.first()
    plan = PLAN_PHASE3_FOLDSEEK_BATCHES(
        channel.value(params.sequence_groups),
        provider_plan,
        provider_entry
    )
    tasks = plan.first().flatMap { Path bundle ->
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
    results = SEARCH_PHASE3_FOLDSEEK_BATCH(
        tasks,
        channel.value(params.database_manifest),
        provider_plan,
        provider_entry,
        1.0e-3,
        0.5,
        10000,
        false
    )
    completed = results.collect().map { values ->
        values.sort { left, right ->
                (left[0] as String) <=> (right[0] as String)
            }
            .collect { row -> row[1] as Path }
    }
    MERGE_PHASE3_FOLDSEEK_BATCHES(
        channel.value(params.sequence_groups),
        plan.first(),
        completed
    )
}
