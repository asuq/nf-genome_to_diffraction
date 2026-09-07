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
    // A plan contributes a sentinel even when every task lacks an output.
    // Wait for channel completion: expected-size grouping would drop partial
    // and zero-output groups after exhausted scheduler failures.
    expected = planned.map { crystalId, bundle, sourceItem ->
        tuple(crystalId, bundle, sourceItem, null)
    }
    attempts = planned.flatMap { crystalId, bundle, sourceItem ->
        def inventory = new groovy.json.JsonSlurper().parseText(
            bundle.resolve('composition_attempt_inventory.json').toFile().text
        )
        def rows = inventory.attempts as List
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
                bundle as Path,
                sourceItem,
                row
            )
        }
    }
    executed = RUN_PHASE3_BEAM_ATTEMPT(attempts)
    grouped = executed.mix(expected).groupTuple().map {
        crystalId, bundles, sourceItems, results ->
        def bundlePaths = (bundles as List<Path>).toSet()
        if (bundlePaths.size() != 1) {
            error 'composition depth attempt group changed crystal or plan'
        }
        tuple(
            crystalId as String,
            bundles[0] as Path,
            sourceItems[0],
            results.findAll { it != null } as List<Path>,
            file("${params.outdir}/pipeline_info/trace.tsv").toString(),
            workflow.sessionId.toString(),
            workflow.workDir.toString()
        )
    }
    collected = COLLECT_PHASE3_COMPOSITION_DEPTH(grouped)

    emit:
    results: Tuple = collected
}
