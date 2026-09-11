#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

// A repository-root entry preserves original projectDir/runtime source paths.
// This fixed reference route is not an M6 track or an operational parent.
include { RF_REFERENCE_WORKFLOW } from './tests/fixtures/ranking_four_arm_workflow'

params {
    runner_root: Path
    protocol: Path = file('benchmarks/m6/protocol.yaml')
    execution_policy: Path = file('benchmarks/m6/execution-nextflow-v1.yaml')
    software_lock: Path = file('pixi.lock')
    database_manifest: Path
    phenix_manifest: Path
    outdir: Path = file('results/rf-reference')
    cache_root: Path = file('.cache/m6')
}

workflow {
    main:
    RF_REFERENCE_WORKFLOW(
        params.runner_root,
        params.protocol,
        params.execution_policy,
        params.software_lock,
        params.database_manifest,
        params.phenix_manifest
    )
}
