#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { PREPARE_PREDICTED_MODELS } from './modules/local/prepare_predicted_models'

params {
    coordinate_sources: Path
    provider_search_results: Path? = null
    sequence_groups: Path
    phenix_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    PREPARE_PREDICTED_MODELS(
        params.coordinate_sources,
        params.provider_search_results,
        params.sequence_groups,
        params.phenix_manifest
    )
}
