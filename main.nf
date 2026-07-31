#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { MAIN_WORKFLOW } from './workflows/main_workflow'

params {
    catalogues: Path
    crystals: Path
    config: Path
    database_manifest: Path
    phenix_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
    review_mode: String = 'prepare'
    approved_mr_seeds: Path? = null
    approved_sequence_groups: Path? = null
    profile_mode: String = 'smoke'
}

workflow {
    main:
    MAIN_WORKFLOW(
        params.catalogues,
        params.crystals,
        params.config,
        params.database_manifest,
        params.phenix_manifest,
        params.cache_root.toString(),
        params.review_mode,
        params.profile_mode
    )
}
