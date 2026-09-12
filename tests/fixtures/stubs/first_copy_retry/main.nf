#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

params {
    scenario: String
    repository: Path
    python: String
    outdir: Path
    cache_root: Path
}

process FIRST_COPY_RETRY_PROBE {
    tag scenario
    label 'process_local'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    scenario: String

    output:
    native_result: Path = file('native-output')
    receipt: Path = file('attempt-result.json')

    script:
    """
    PYTHONPATH='${params.repository}/src:${params.repository}' \
        '${params.python}' -P '${projectDir}/run_probe.py' \
        --scenario '${scenario}' --attempt '${task.attempt}'
    """
}

workflow {
    main:
    FIRST_COPY_RETRY_PROBE(channel.of(params.scenario))
}
