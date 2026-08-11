#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { FIRST_COPY_MR_WORKFLOW } from './workflows/first_copy_mr_workflow'

params {
    coordinate_sources: Path
    prepared_models: Path
    sequence_groups: Path
    matthews: Path
    preflight: Path
    config: Path
    crystal_id: String
    mtz: Path
    phenix_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    FIRST_COPY_MR_WORKFLOW(
        params.coordinate_sources,
        params.prepared_models,
        params.sequence_groups,
        params.matthews,
        params.preflight,
        params.config,
        params.crystal_id,
        params.mtz,
        params.phenix_manifest
    )
}
