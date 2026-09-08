nextflow.enable.types = true

include {
    M6_FIRST_COPY;
    M6_ADDITIONAL_COPY;
    M6_SELECT_FINALISTS;
    M6_EMPTY_FINALISTS;
    M6_REFINEMENT;
    M6_ASSEMBLE_CASE;
    M6_ASSEMBLE_EMPTY_CASE
} from '../../modules/local/m6_nextflow_tasks'

process M6_VALIDATE_COMPARISON {
    tag "m6-comparison-validate:${stage}"
    label 'm6_small'

    input:
    root: Path
    stage: String
    software_lock: Path
    phenix_manifest: Path

    output:
    validated: Path = file('comparison_execution.json')

    script:
    """
    genome-to-diffraction --no-progress benchmark validate-m6-comparison \
        --root '${root}' --stage '${stage}' \
        --software-lock '${software_lock}' --phenix-manifest '${phenix_manifest}' \
        --output comparison_execution.json
    """
}

process M6_COMPARISON_SELECT {
    tag "m6-comparison-review:${item[0]}:${item[3]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    selected: Tuple = tuple(item[0], item[3], file('comparison_seeds'))

    script:
    def resultArgs = item[2].collect { Path result -> "--first-copy-result '${result}'" }.join(' ')
    """
    genome-to-diffraction --no-progress benchmark select-m6-comparison-seeds \
        --case-bundle '${item[1]}' --arm '${item[3]}' \
        ${resultArgs} --outdir comparison_seeds
    """
}

process M6_COMPARISON_FREEZE {
    tag 'm6-comparison-freeze'
    label 'm6_small'
    publishDir "${params.outdir}", mode: 'copy'

    input:
    root: Path
    seed_bundles: List<Path>

    stage:
    stageAs seed_bundles, 'seeds??/*'

    output:
    frozen: Path = file('comparison_advancement')

    script:
    def seedArgs = seed_bundles.collect { Path seed -> "--seed-bundle '${seed}'" }.join(' ')
    """
    genome-to-diffraction --no-progress benchmark freeze-m6-comparison \
        --root '${root}' ${seedArgs} --outdir comparison_advancement
    """
}

process M6_COMPARISON_COLLECT {
    tag 'm6-comparison-collect'
    label 'm6_small'
    publishDir "${params.outdir}", mode: 'copy'

    input:
    root: Path
    case_bundles: List<Path>
    software_lock: Path
    phenix_manifest: Path

    stage:
    stageAs case_bundles, 'cases??/*'

    output:
    result: Path = file('comparison_results')

    script:
    def caseArgs = case_bundles.collect { Path evidence -> "--case-evidence '${evidence}'" }.join(' ')
    """
    genome-to-diffraction --no-progress benchmark collect-m6-comparison \
        --root '${root}' ${caseArgs} --software-lock '${software_lock}' \
        --phenix-manifest '${phenix_manifest}' --outdir comparison_results
    """
}

workflow M6_COMPARISON_INITIAL_WORKFLOW {
    take:
    root: Path
    software_lock: Path
    phenix_manifest: Path

    main:
    validation = M6_VALIDATE_COMPARISON(root, 'initial', software_lock, phenix_manifest)
    cohorts = validation.flatMap { Path path ->
        def plan = new groovy.json.JsonSlurper().parse(path.toFile()).validated
        plan.cohorts.collect { entry ->
            tuple(entry.cohort.cohort_id as String,
                file(root.resolve(entry.case_path as String), checkIfExists: true),
                entry.cohort.scheduled_hypothesis_ids as List,
                entry.cohort.admission_prior as String,
                plan.plan_id as String)
        }
    }
    runnable = cohorts.filter { id, bundle, ids, prior, planId -> ids.size() > 0 }
    empty = cohorts.filter { id, bundle, ids, prior, planId -> ids.size() == 0 }
    first_tasks = runnable.flatMap { id, bundle, ids, prior, planId ->
        ids.collect { Object rawId ->
            tuple(groupKey(id, ids.size()), id, bundle,
                bundle.resolve("first-copy-funnel/hypotheses/${rawId}.jsonl"),
                phenix_manifest, planId)
        }
    }
    first = M6_FIRST_COPY(first_tasks)
    grouped = first.groupTuple().map { key, ids, bundles, results ->
        tuple(key.groupTarget as String, bundles[0] as Path, results as List<Path>)
    }
    // Each native cohort is shared by both review orders; no Phaser task is
    // created per review arm. Empty cohorts follow the same accounting path.
    completed = grouped.mix(empty.map { id, bundle, ids, prior, planId ->
        tuple(id, bundle, [] as List<Path>)
    })
    reviews = completed.flatMap { id, bundle, results ->
        def cohort = new groovy.json.JsonSlurper().parse(
            bundle.resolve('comparison_cohort.json').toFile())
        def arms = cohort.admission_prior == 'solvent_density' ? ['A', 'C'] : ['B', 'D']
        arms.collect { String arm -> tuple(id, bundle, results, arm) }
    }
    selected = M6_COMPARISON_SELECT(reviews)
    selected_bundles = selected.collect().map { rows ->
        rows.sort { left, right -> "${left[0]}:${left[1]}" <=> "${right[0]}:${right[1]}" }
            .collect { row -> row[2] as Path }
    }
    result = M6_COMPARISON_FREEZE(root, selected_bundles)

    emit:
    frozen_workload: Path = result
}

workflow M6_COMPARISON_CONTINUATION_WORKFLOW {
    take:
    root: Path
    software_lock: Path
    phenix_manifest: Path

    main:
    validation = M6_VALIDATE_COMPARISON(root, 'continuation', software_lock, phenix_manifest)
    arms = validation.flatMap { Path path ->
        def frozen = new groovy.json.JsonSlurper().parse(path.toFile()).validated
        frozen.arms.collect { row ->
            tuple("${row.case_id}:${row.arm}" as String,
                file(root.resolve(row.case_path as String), checkIfExists: true),
                file(root.resolve(row.seed_path as String), checkIfExists: true),
                row.selected_seed_ids as List,
                frozen.freeze_id as String)
        }
    }
    active = arms.filter { key, caseBundle, seeds, ids, freezeId -> ids.size() > 0 }
    empty = arms.filter { key, caseBundle, seeds, ids, freezeId -> ids.size() == 0 }
    copy_tasks = active.flatMap { key, caseBundle, seeds, ids, freezeId ->
        ids.collect { Object seed ->
            tuple(groupKey(key, ids.size()), key, seed as String,
                caseBundle, seeds, phenix_manifest, freezeId)
        }
    }
    copies = M6_ADDITIONAL_COPY(copy_tasks)
    grouped_copies = copies.groupTuple().map { key, keys, cases, seeds, results ->
        tuple(key.groupTarget as String, cases[0] as Path,
            seeds[0] as Path, results as List<Path>)
    }
    active_finalists = M6_SELECT_FINALISTS(grouped_copies)
    empty_finalists = M6_EMPTY_FINALISTS(empty.map { key, caseBundle, seeds, ids, freezeId ->
        tuple(key, caseBundle, seeds)
    })
    finalists = active_finalists.mix(empty_finalists).map { key, caseBundle, bundle ->
        def plan = new groovy.json.JsonSlurper().parse(
            bundle.resolve('finalist_plan.json').toFile())
        tuple(key, caseBundle, bundle, plan.finalist_count as Integer)
    }
    active_parents = finalists.filter { key, caseBundle, bundle, count -> count > 0 }
    empty_parents = finalists.filter { key, caseBundle, bundle, count -> count == 0 }
    refinement_tasks = active_parents.flatMap { key, caseBundle, bundle, count ->
        def rows = bundle.resolve('finalist_tasks.jsonl').toFile().readLines()
            .findAll { String line -> line.trim() }
        if (rows.size() != count) {
            error "M6 comparison finalist count changed for ${key}"
        }
        rows.collect { String line ->
            def row = new groovy.json.JsonSlurper().parseText(line)
            tuple(groupKey(key, count), key, row.seed_solution_id as String,
                caseBundle, bundle, phenix_manifest)
        }
    }
    refinements = M6_REFINEMENT(refinement_tasks)
    grouped_refinements = refinements.groupTuple().map { key, keys, cases, bundles, results ->
        tuple(key.groupTarget as String, cases[0] as Path,
            bundles[0] as Path, results as List<Path>)
    }
    active_evidence = M6_ASSEMBLE_CASE(grouped_refinements)
    empty_evidence = M6_ASSEMBLE_EMPTY_CASE(empty_parents.map { key, caseBundle, bundle, count ->
        tuple(key, caseBundle, bundle)
    })
    cases = active_evidence.mix(empty_evidence).collect().map { rows ->
        rows.sort { left, right -> left[0] <=> right[0] }.collect { row -> row[1] as Path }
    }
    result = M6_COMPARISON_COLLECT(root, cases, software_lock, phenix_manifest)

    emit:
    comparison_result: Path = result
}
