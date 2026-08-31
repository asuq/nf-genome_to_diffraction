nextflow.enable.dsl = 2
nextflow.enable.types = true

params {
    outdir: Path
    sentinel: String
}

process MR_RESOURCE_RETRY {
    tag 'mr-resource-retry'
    errorStrategy { task.exitStatus == 75 ? 'retry' : 'finish' }
    maxRetries 1
    cpus { task.attempt }
    memory { "${task.attempt} GB" }
    time { "${task.attempt} min" }
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    token: String

    output:
    result: Path = file('result.txt')

    script:
    """
    if [[ '${task.attempt}' == 1 && ! -f '${params.sentinel}' ]]; then
        touch '${params.sentinel}'
        exit 75
    fi
    printf '%s\n' '${token}|${task.attempt}|${task.cpus}' > result.txt
    """
}

workflow {
    MR_RESOURCE_RETRY(channel.of('same-scientific-task'))
}
