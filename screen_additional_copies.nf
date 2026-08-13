#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { ADDITIONAL_COPY_WORKFLOW } from './workflows/additional_copy_workflow'

params {
    seeds: Path
    review_validation: Path
    review_package: Path
    hypotheses: Path
    sequence_groups: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    seeds_channel = channel.of(params.seeds)
    ADDITIONAL_COPY_WORKFLOW(
        seeds_channel,
        params.review_validation,
        params.review_package,
        params.hypotheses,
        params.sequence_groups,
        params.preflight,
        params.mtz,
        params.phenix_manifest
    )
}
