#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include {
    BUILD_PHASE3_OWNED_A_REVIEW_PACKAGE
} from '../../../../modules/local/phase3_multicrystal_first_copy_tasks'

params {
    review_manifest: Path
    execution_identity: Path
    owned_parent_run_id: String
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    reviews = channel.value(params.review_manifest).flatMap { Path manifest ->
        def records = new groovy.json.JsonSlurper().parse(manifest.toFile())
        (records.crystals as List).collect { item ->
            tuple(
                item.crystal_id as String,
                file(item.review_package as String, checkIfExists: true),
                file(item.hypotheses as String, checkIfExists: true),
                params.execution_identity,
                params.owned_parent_run_id
            )
        }
    }
    BUILD_PHASE3_OWNED_A_REVIEW_PACKAGE(reviews)
}
