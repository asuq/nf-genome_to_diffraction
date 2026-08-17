#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { M6_VALIDATION_WORKFLOW } from './workflows/m6_validation_workflow'

params {
    runner_root: Path
    protocol: Path = file('benchmarks/m6/protocol.yaml')
    execution_policy: Path = file('benchmarks/m6/execution-nextflow-v1.yaml')
    software_lock: Path = file('pixi.lock')
    database_manifest: Path
    phenix_manifest: Path
    track: String
    outdir: Path = file('results/m6')
    cache_root: Path = file('.cache/m6')
    m6_discovery_store: Path = file('.cache/m6-discovery')
}

workflow {
    main:
    if (!(params.track in ['operational', 'leakage'])) {
        error "M6 track must be operational or leakage"
    }
    M6_VALIDATION_WORKFLOW(
        params.runner_root,
        params.protocol,
        params.execution_policy,
        params.software_lock,
        params.database_manifest,
        params.phenix_manifest,
        params.track
    )
}
