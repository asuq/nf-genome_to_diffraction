#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { BRIEF_REFINEMENT_WORKFLOW } from './workflows/brief_refinement_workflow'

params {
    finalists: Path
    sequence_groups: Path
    source_records: Path
    phenix_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    finalists_channel = channel.of(params.finalists)
    BRIEF_REFINEMENT_WORKFLOW(
        finalists_channel,
        params.sequence_groups,
        params.source_records,
        params.phenix_manifest
    )
}
