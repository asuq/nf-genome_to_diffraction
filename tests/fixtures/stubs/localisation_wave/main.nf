#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { LOCALISATION_WAVE_WORKFLOW } from '../../../../workflows/localisation_wave_workflow'

params {
    sequence_groups: Path
    psortb_runtime: Path
    deeptmhmm_runtime: Path
    active_wave_completion: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    LOCALISATION_WAVE_WORKFLOW(
        channel.value(params.sequence_groups),
        channel.value(params.psortb_runtime),
        channel.value(params.deeptmhmm_runtime),
        channel.value(params.active_wave_completion)
    )
}
