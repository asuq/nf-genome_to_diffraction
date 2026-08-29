nextflow.enable.types = true

include {
    PLAN_PHASE3_COMPOSITION_DEPTH;
    RUN_PHASE3_BEAM_ATTEMPT;
    COLLECT_PHASE3_COMPOSITION_DEPTH
} from '../modules/local/phase3_composition_beam_tasks'

// One complete crystal item contains the retained parents plus every immutable
// scientific/runtime authority needed by planning and execution. Independent
// attempts fan out through Nextflow; only the cross-depth dependency is serial.
workflow PHASE3_COMPOSITION_DEPTH_WORKFLOW {
    take:
    depth_inputs: Tuple

    main:
    planned = PLAN_PHASE3_COMPOSITION_DEPTH(depth_inputs)
    runnable = planned.filter { crystalId, bundle, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            bundle.resolve('composition_depth_input_manifest.json').toFile().text
        )
        (record.attempt_count as Integer) > 0
    }
    empty = planned.filter { crystalId, bundle, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            bundle.resolve('composition_depth_input_manifest.json').toFile().text
        )
        (record.attempt_count as Integer) == 0
    }.map { crystalId, bundle, sourceItem ->
        tuple(crystalId, bundle, sourceItem, [] as List<Path>)
    }
    attempts = runnable.flatMap { crystalId, bundle, sourceItem ->
        def inventory = new groovy.json.JsonSlurper().parseText(
            bundle.resolve('composition_attempt_inventory.json').toFile().text
        )
        def rows = inventory.attempts as List
        def key = groupKey(crystalId as String, rows.size())
        rows.collect { row ->
            tuple(
                crystalId as String,
                row.attempt_id as String,
                file(bundle.resolve('composition_attempt_inventory.json')),
                sourceItem[12] as Path,
                sourceItem[8] as Path,
                sourceItem[2] as Path,
                sourceItem[7] as Path,
                sourceItem[14] as Path,
                sourceItem[15] as Path,
                sourceItem[13] as Path,
                key,
                bundle as Path,
                sourceItem
            )
        }
    }
    executed = RUN_PHASE3_BEAM_ATTEMPT(attempts)
    grouped = executed.groupTuple().map {
        key, crystalIds, bundles, sourceItems, results ->
        def crystals = (crystalIds as List<String>).toSet()
        def bundlePaths = (bundles as List<Path>).toSet()
        if (crystals.size() != 1 || bundlePaths.size() != 1) {
            error 'composition depth attempt group changed crystal or plan'
        }
        tuple(
            key.groupTarget as String,
            bundles[0] as Path,
            sourceItems[0],
            results as List<Path>
        )
    }
    collected = COLLECT_PHASE3_COMPOSITION_DEPTH(grouped.mix(empty))

    emit:
    results: Tuple = collected
}
