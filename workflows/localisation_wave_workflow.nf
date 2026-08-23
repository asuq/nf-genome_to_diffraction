nextflow.enable.types = true

include {
    BUILD_CATALOGUE_LOCALISATION_TASKS;
    BUILD_CATALOGUE_LOCALISATION_WAVE_POLICY;
    PLAN_LOCALISATION_REOPEN
} from '../modules/local/localisation_wave_tasks'
include { RUN_OFFLINE_LOCALISATION_TASK } from '../modules/local/run_offline_localisation_task'

workflow LOCALISATION_WAVE_WORKFLOW {
    take:
    sequence_groups: Path
    psortb_runtime: Path
    deeptmhmm_runtime: Path
    active_wave_completion: Path

    main:
    task_inventory = BUILD_CATALOGUE_LOCALISATION_TASKS(
        sequence_groups,
        psortb_runtime,
        deeptmhmm_runtime
    )
    task_items = task_inventory.flatMap { Path bundle ->
        bundle.resolve('localisation_tasks.tsv').toFile().readLines().drop(1)
            .findAll { String line -> line.trim() }
            .collect { String line ->
                def fields = line.split('\t', -1)
                tuple(
                    fields[0] as String,
                    fields[1] as String,
                    file(bundle.resolve(fields[2]), checkIfExists: true)
                )
            }
    }
    localisation_results = RUN_OFFLINE_LOCALISATION_TASK(
        task_items,
        psortb_runtime.first(),
        deeptmhmm_runtime.first()
    )
    result_list = localisation_results
        .collect()
        .ifEmpty { [] }
        .map { values ->
            values.sort { left, right ->
                    (left[0] as String) <=> (right[0] as String)
                }
                .collect { row -> row[1] as Path }
        }
    wave_policy = BUILD_CATALOGUE_LOCALISATION_WAVE_POLICY(
        task_inventory.first(),
        result_list
    )
    reopen_plan = PLAN_LOCALISATION_REOPEN(
        wave_policy.first(),
        active_wave_completion
    )

    emit:
    tasks: Path = task_inventory
    results = localisation_results
    policy: Path = wave_policy
    reopen: Path = reopen_plan
}
