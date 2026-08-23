/*
 * One offline localisation task per exact sequence-equivalence group.
 *
 * This process intentionally uses legacy tuple path qualifiers: preview typed
 * process syntax treats paths nested in a generic Tuple as values and would not
 * content-hash or stage the task directory. PSORTb tool/parse failure is emitted
 * as a typed result; contract/runtime failure terminates the process. Deep cache
 * mode binds resume to the complete task and runtime-contract file contents.
 */

process RUN_OFFLINE_LOCALISATION_TASK {
    tag "offline-localisation:${sequence_group_id}"
    label 'process_low'
    cache 'deep'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    tuple val(task_id), val(sequence_group_id), path('localisation_task')
    path psortb_runtime
    path deeptmhmm_runtime

    output:
    tuple val(sequence_group_id), path("localisation_result_${task_id}"), emit: result

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        localisation run-task \
        --task-directory localisation_task \
        --psortb-runtime '${psortb_runtime}' \
        --deeptmhmm-runtime '${deeptmhmm_runtime}' \
        --outdir 'localisation_result_${task_id}'
    """

    stub:
    """
    python '${moduleDir}/../../tests/scripts/materialise_localisation_stub.py' \
        --task-directory localisation_task \
        --psortb-runtime '${psortb_runtime}' \
        --deeptmhmm-runtime '${deeptmhmm_runtime}' \
        --outdir 'localisation_result_${task_id}'
    """
}
