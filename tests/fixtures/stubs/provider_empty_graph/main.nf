#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { PROVIDER_EMPTY_GRAPH_WORKFLOW } from '../../../../workflows/provider_empty_graph_workflow'

params {
    sequence_groups: Path
    config: Path
    database_manifest: Path
    stub_helper: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    PROVIDER_EMPTY_GRAPH_WORKFLOW(
        channel.value(params.sequence_groups),
        channel.value(params.config),
        channel.value(params.database_manifest),
        channel.value(params.stub_helper)
    )
}
