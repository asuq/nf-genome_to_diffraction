#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { PREPARE_EXPERIMENTAL_MODELS } from './modules/local/prepare_experimental_models'

params {
    coordinate_sources: Path
    coordinate_hit_mappings: Path
    sequence_groups: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    PREPARE_EXPERIMENTAL_MODELS(
        params.coordinate_sources,
        params.coordinate_hit_mappings,
        params.sequence_groups
    )
}
