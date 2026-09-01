#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

params {
    scenario: String
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

process PHASE3_RETRY_PROBE {
    tag scenario
    publishDir params.outdir, mode: 'copy'

    input:
    scenario: String

    output:
    result: Path = file('result.txt')

    script:
    """
    if [[ '${scenario}' == 'transient' && '${task.attempt}' == '1' ]]; then
        exit 75
    fi
    if [[ '${scenario}' == 'contract' ]]; then
        exit 65
    fi
    printf '%s\\n' '${task.attempt}' > result.txt
    """
}

workflow {
    main:
    PHASE3_RETRY_PROBE(channel.of(params.scenario))
}
