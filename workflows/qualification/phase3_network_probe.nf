nextflow.enable.dsl = 2

params.outer_job_id = null
params.outer_network_namespace = null
params.outdir = null

process PHASE3_NETWORK_PROBE_CHILD {
    tag 'child_slurm'
    label 'phase3_network_probe_child'
    cpus 1
    memory '1 GB'
    time '10 minutes'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    tuple val(python_executable), val(outer_job_id), val(outer_network_namespace)

    output:
    path 'phase3-network-probe-child.json', emit: report

    script:
    """
    "${python_executable}" \
        -m genome_to_diffraction.execution.network_probe \
        probe \
        --role child_slurm \
        --outer-job-id '${outer_job_id}' \
        --outer-network-namespace '${outer_network_namespace}' \
        --output phase3-network-probe-child.json
    """
}

process PHASE3_NETWORK_PROBE_CONTROLLER {
    tag 'controller_local'
    label 'phase3_network_probe_controller'
    label 'run_local'
    cpus 1
    memory '1 GB'
    time '10 minutes'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    tuple val(python_executable), val(outer_job_id), val(outer_network_namespace)

    output:
    path 'phase3-network-probe-controller.json', emit: report

    script:
    """
    "${python_executable}" \
        -m genome_to_diffraction.execution.network_probe \
        probe \
        --role controller_local \
        --outer-job-id '${outer_job_id}' \
        --outer-network-namespace '${outer_network_namespace}' \
        --output phase3-network-probe-controller.json
    """
}

workflow {
    if (!params.outer_job_id || !(params.outer_job_id as String).matches(/[0-9]+/)) {
        error 'phase3 network probe requires the fixed numeric outer job ID'
    }
    if (!params.outer_network_namespace ||
        !(params.outer_network_namespace as String).matches(/net:\[[0-9]+\]/)) {
        error 'phase3 network probe requires the fixed outer network namespace'
    }
    if (!params.outdir) {
        error 'phase3 network probe requires its owned output directory'
    }

    probe_input = channel.value(
        tuple(
            "${projectDir}/.pixi/envs/hpc/bin/python" as String,
            params.outer_job_id as String,
            params.outer_network_namespace as String,
        )
    )
    PHASE3_NETWORK_PROBE_CHILD(probe_input)
    PHASE3_NETWORK_PROBE_CONTROLLER(probe_input)
}
