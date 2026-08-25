#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include {
    PHASE3_REVIEWED_SINGLE_COMPONENT_WORKFLOW
} from '../../../../workflows/phase3_reviewed_single_component_workflow'

params {
    reviewed_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    reviewed = channel.value(params.reviewed_manifest).flatMap { Path manifest ->
        def records = new groovy.json.JsonSlurper().parse(manifest.toFile())
        (records.crystals as List).collect { item ->
            tuple(
                item.crystal_id as String,
                file(item.review_package as String, checkIfExists: true),
                file(item.review_stage as String, checkIfExists: true),
                file(item.phase3_package as String, checkIfExists: true),
                file(item.hypotheses as String, checkIfExists: true),
                file(item.sequence_groups as String, checkIfExists: true),
                file(item.source_records as String, checkIfExists: true),
                file(item.preflight as String, checkIfExists: true),
                file(item.mtz as String, checkIfExists: true),
                file(item.phenix_manifest as String, checkIfExists: true),
                file(item.dispatch as String, checkIfExists: true)
            )
        }
    }
    PHASE3_REVIEWED_SINGLE_COMPONENT_WORKFLOW(reviewed)
}
