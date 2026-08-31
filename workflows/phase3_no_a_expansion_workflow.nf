nextflow.enable.types = true

include {
    RUN_PHASE3_NO_A_FIRST_COPY;
    BUILD_PHASE3_NO_A_REVIEW;
    BUILD_PHASE3_NO_A_OWNED_REVIEW
} from '../modules/local/phase3_no_a_tasks'

workflow PHASE3_NO_A_EXPANSION_WORKFLOW {
    take:
    no_a_inputs: Tuple
    owned_parent_run_id: String

    main:
    attempts = no_a_inputs.flatMap { item ->
        def rows = item[2].resolve('reopened_hypotheses.jsonl')
            .toFile().readLines().findAll { line -> line.trim() }
        def key = groupKey(item[0] as String, rows.size())
        rows.collect { line ->
            def hypothesis = new groovy.json.JsonSlurper().parseText(line)
            Path resourcePlan = item[2].resolve('resource_plans').resolve(
                "${hypothesis.hypothesis_id}.json"
            )
            if (!resourcePlan.toFile().isFile()) {
                error "No-A hypothesis lacks its MR resource plan: ${hypothesis.hypothesis_id}"
            }
            def resourcePlanDocument = new groovy.json.JsonSlurper().parse(
                resourcePlan.toFile()
            )
            tuple(
                item[0], hypothesis.hypothesis_id as String,
                item[2], item[3], item[4], item[5], item[6], item[7],
                item[8], item[9], key, item,
                file(resourcePlan, checkIfExists: true), resourcePlanDocument
            )
        }
    }
    results = RUN_PHASE3_NO_A_FIRST_COPY(attempts)
    grouped = results.groupTuple().map {
        key, crystalIds, plans, sourceItems, resultPaths ->
        tuple(
            key.groupTarget as String,
            plans[0] as Path,
            resultPaths as List<Path>,
            sourceItems[0][3] as Path,
            sourceItems[0][10] as Path,
            sourceItems[0][11] as Path,
            sourceItems[0][12] as Path
        )
    }
    reviews = BUILD_PHASE3_NO_A_REVIEW(grouped)
    owned_inputs = reviews.join(no_a_inputs.map { item ->
        tuple(item[0], item[2], item[9])
    }, by: 0, failOnDuplicate: true, failOnMismatch: true).map {
        crystalId, review, plan, executionIdentity ->
        tuple(
            crystalId,
            review,
            file(plan.resolve('mr_hypotheses.jsonl'), checkIfExists: true),
            executionIdentity,
            owned_parent_run_id
        )
    }
    owned = BUILD_PHASE3_NO_A_OWNED_REVIEW(owned_inputs)

    emit:
    first_copy_results: Tuple = results
    reviews: Tuple = reviews
    owned_reviews: Tuple = owned
}
