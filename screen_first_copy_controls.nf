#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { CONTROL_FIRST_COPY_MR_WORKFLOW } from './workflows/control_first_copy_mr_workflow'

params {
    control_bundle: Path
    sequence_groups: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    control_bundle_channel = channel.of(params.control_bundle)
    CONTROL_FIRST_COPY_MR_WORKFLOW(
        control_bundle_channel,
        params.sequence_groups,
        params.preflight,
        params.mtz,
        params.phenix_manifest
    )
}
