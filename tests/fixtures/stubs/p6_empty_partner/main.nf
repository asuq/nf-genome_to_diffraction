#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { PARTNER_SEARCH_WORKFLOW } from '../../../../workflows/partner_search_workflow'

params {
    approved_stage: Path
    review_package: Path
    sequence_groups: Path
    matthews: Path
    preflight: Path
    pipeline_config: Path
    model_registry: Path
    mtz: Path
    phenix_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    PARTNER_SEARCH_WORKFLOW(
        channel.value(params.approved_stage),
        channel.value(params.review_package),
        channel.value(params.sequence_groups),
        channel.value(params.matthews),
        channel.value(params.preflight),
        channel.value(params.pipeline_config),
        channel.value(params.model_registry),
        'P6_MISSING_B_STUB',
        1,
        channel.value(params.mtz),
        channel.value(params.phenix_manifest)
    )
}
