#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { COMPOSITION_ATTEMPT_WORKFLOW } from '../../../../workflows/composition_attempt_workflow'

params {
    attempt_inventory: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    COMPOSITION_ATTEMPT_WORKFLOW(channel.value(params.attempt_inventory))
}
