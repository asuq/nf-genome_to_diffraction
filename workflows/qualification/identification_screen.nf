nextflow.enable.types = true

// The wrapper validates the complete immutable input tree once before launch.
// Include its content ID in every task hash; each adapter rechecks its own model.
process PREPARE_IDENTIFICATION_MODEL {
    tag "identification-prepare:${item[0]}"
    label 'process_low'
    errorStrategy 'finish'
    publishDir "${params.outdir}/prepared", mode: 'copy'

    input:
    item: Tuple

    output:
    prepared: Tuple = tuple(item[0], file("${item[0]}"), item[1])

    script:
    """
    python -m genome_to_diffraction.hpc.identification_run prepare \
        --inputs '${params.identification_inputs}' \
        --case-id '${item[0]}' --outdir '${item[0]}'
    """

    stub:
    """
    python -m genome_to_diffraction.hpc.identification_run prepare \
        --inputs '${params.identification_inputs}' \
        --case-id '${item[0]}' --outdir '${item[0]}'
    """
}

process RUN_IDENTIFICATION_PHASER {
    tag "identification-mr:${item[0]}"
    label 'process_mr'
    publishDir "${params.outdir}/mr", mode: 'copy'
    cpus { (item[3].base_cpus as int) * task.attempt }
    memory { "${(item[3].base_memory_gb as int) * task.attempt} GB" }
    time { "${(item[3].base_time_hours as int) * task.attempt} hours" }

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file("${item[0]}"))

    script:
    """
    python -m genome_to_diffraction.hpc.identification_run run \
        --inputs '${params.identification_inputs}' \
        --case-id '${item[0]}' --prepared '${item[1]}' \
        --phenix-manifest '${params.phenix_manifest}' \
        --threads '${task.cpus}' --attempt '${task.attempt}' \
        --outdir '${item[0]}'
    """

    stub:
    """
    mkdir '${item[0]}'
    printf '%s\n' '{"case_id":"${item[0]}","status":"stub_not_scientific","identity_accepted":false}' > '${item[0]}/run.json'
    """
}

workflow IDENTIFICATION_SCREEN_WORKFLOW {
    main:
    selected = new groovy.json.JsonSlurper().parse((params.identification_cases as Path).toFile())
    cases = channel.fromList(selected).map { row -> tuple(row.case_id, params.identification_input_id) }
    PREPARE_IDENTIFICATION_MODEL(cases)
    ready = PREPARE_IDENTIFICATION_MODEL.out.prepared
        .map { item ->
            def record = new groovy.json.JsonSlurper().parse(item[1].resolve('preparation.json').toFile())
            tuple(item[0], item[1], item[2], record)
        }
        .filter { item -> item[3].status == 'prepared' }
        .map { item -> tuple(item[0], item[1], item[2], item[3].resource_plan) }
    RUN_IDENTIFICATION_PHASER(ready)
}
