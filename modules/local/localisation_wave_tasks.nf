/*
 * Phase III catalogue-wide offline localisation and wave policy.
 *
 * BUILD emits one immutable item per exact sequence group. RUN invokes only the
 * verified local PSORTb adapter; its stub materialises typed synthetic records
 * and never invokes PSORTb or DeepTMHMM. BUILD_WAVE_POLICY requires exact
 * one-result-per-group coverage. PLAN_REOPEN consumes a complete-wave record and
 * can activate retained excluded groups only when no first-wave result packed.
 * Runtime identities, task identities, raw checksums, merged evidence, and all
 * excluded groups remain published. Candidate-local PSORTb failures are normal
 * outputs; malformed contracts fail the corresponding process. Deep cache mode
 * binds resume to complete staged task/runtime/result content.
 */

nextflow.enable.types = true

process BUILD_CATALOGUE_LOCALISATION_TASKS {
    tag 'catalogue-localisation-tasks'
    label 'process_low'
    cache 'deep'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    sequence_groups: Path
    psortb_runtime: Path
    deeptmhmm_runtime: Path

    output:
    tasks: Path = file('localisation_tasks')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        localisation build-tasks \
        --sequence-groups '${sequence_groups}' \
        --psortb-runtime '${psortb_runtime}' \
        --deeptmhmm-runtime '${deeptmhmm_runtime}' \
        --outdir localisation_tasks
    """

    stub:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        localisation build-tasks \
        --sequence-groups '${sequence_groups}' \
        --psortb-runtime '${psortb_runtime}' \
        --deeptmhmm-runtime '${deeptmhmm_runtime}' \
        --outdir localisation_tasks
    """
}

process BUILD_CATALOGUE_LOCALISATION_WAVE_POLICY {
    tag 'catalogue-localisation-wave-policy'
    label 'process_low'
    cache 'deep'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    task_inventory: Path
    localisation_results: List<Path>

    output:
    policy: Path = file('localisation_wave_policy')

    script:
    def resultArguments = localisation_results
        .collect { Path result -> "--result-directory '${result}'" }
        .join(' ')
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        localisation build-wave-policy \
        --task-inventory '${task_inventory}' \
        ${resultArguments} \
        --outdir localisation_wave_policy
    """

    stub:
    def resultArguments = localisation_results
        .collect { Path result -> "--result-directory '${result}'" }
        .join(' ')
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        localisation build-wave-policy \
        --task-inventory '${task_inventory}' \
        ${resultArguments} \
        --outdir localisation_wave_policy
    """
}

process PLAN_LOCALISATION_REOPEN {
    tag 'localisation-reopen-plan'
    label 'process_low'
    cache 'deep'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    wave_policy: Path
    active_wave_completion: Path

    output:
    reopen: Path = file('localisation_reopen_plan')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        localisation plan-reopen \
        --wave-policy '${wave_policy}/first_wave_policy.json' \
        --active-wave-completion '${active_wave_completion}' \
        --outdir localisation_reopen_plan
    """

    stub:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        localisation plan-reopen \
        --wave-policy '${wave_policy}/first_wave_policy.json' \
        --active-wave-completion '${active_wave_completion}' \
        --outdir localisation_reopen_plan
    """
}
