#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { COMPOSITION_ATTEMPT_WORKFLOW } from '../../../../workflows/composition_attempt_workflow'

params {
    attempt_inventory: Path
    fixed_coordinate_root: Path
    model_registry: Path
    sequence_groups: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path
    execution_identity: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    COMPOSITION_ATTEMPT_WORKFLOW(
        channel.value(params.attempt_inventory),
        channel.value(params.fixed_coordinate_root),
        channel.value(params.model_registry),
        channel.value(params.sequence_groups),
        channel.value(params.preflight),
        channel.value(params.mtz),
        channel.value(params.phenix_manifest),
        channel.value(params.execution_identity)
    )
}
