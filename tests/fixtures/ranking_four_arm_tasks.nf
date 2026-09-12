nextflow.enable.types = true

// Context paths nested in generic tuples are original producer values, not
// same-basename List<Path> staging aliases. The CLI authenticates originals.
// The original m6_* labels retain the fixed site's allocations and ceiling.

process RF_PLAN {
    tag 'rf-plan:fixed-five'
    label 'm6_small'

    input:
    runner_root: Path
    database_manifest: Path
    software_lock: Path

    output:
    result: Path = file('reference_plan')

    script:
    """
    PYTHONPATH='${projectDir}/src:${projectDir}' \
        python -P -m tests.fixtures.ranking_four_arm_cli \
        --source-root '${projectDir}' plan \
        --runner-root '${runner_root}' \
        --database-manifest '${database_manifest}' \
        --software-lock '${software_lock}' --output reference_plan
    """
}

process RF_PREPARE {
    tag "rf-prepare:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple
    plan_context: Path
    phenix_manifest: Path

    output:
    result: Tuple = tuple(item[0], file('reference_prepared'))

    script:
    def coordinateArg = item[3].collect { Path path -> "--coordinate-stage '${path}'" }.join(' ')
    """
    PYTHONPATH='${projectDir}/src:${projectDir}' \
        python -P -m tests.fixtures.ranking_four_arm_cli \
        --source-root '${projectDir}' prepare \
        --plan-context '${plan_context}' --case-id '${item[0]}' \
        --catalogue-bundle '${item[1]}' --prepared-case '${item[2]}' \
        ${coordinateArg} --phenix-manifest '${phenix_manifest}' \
        --output reference_prepared
    """

    stub:
    """
    python -P '${projectDir}/tests/fixtures/ranking_four_arm_stub.py' \
        prepare --case-id '${item[0]}' --output reference_prepared
    """
}

process RF_FIRST_COPY {
    tag "rf-first:${item[1]}:${item[3]}"
    label 'm6_first_copy'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], item[1], item[2], file('reference_first'))

    script:
    """
    # Operational exit contract: first-copy-transient-75-v1
    PYTHONPATH='${projectDir}/src:${projectDir}' \
        python -P -m tests.fixtures.ranking_four_arm_cli \
        --source-root '${projectDir}' first-copy \
        --prepared-context '${item[2]}/context.json' \
        --hypothesis-id '${item[3]}' --threads ${task.cpus} \
        --output reference_first
    """

    stub:
    """
    python -P '${projectDir}/tests/fixtures/ranking_four_arm_stub.py' \
        first --case-id '${item[1]}' --upstream '${item[2]}' --hypothesis-id '${item[3]}' --output reference_first
    """
}

process RF_REVIEWS {
    tag "rf-reviews:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file('reference_reviews'))

    script:
    def receiptArgs = item[2].collect { Path root -> "--first-copy-receipt '${root}/bundle/reference_first_copy.json'" }.join(' ')
    """
    PYTHONPATH='${projectDir}/src:${projectDir}' \
        python -P -m tests.fixtures.ranking_four_arm_cli \
        --source-root '${projectDir}' reviews \
        --prepared-context '${item[1]}/context.json' ${receiptArgs} \
        --output reference_reviews
    """

    stub:
    def receiptArgs = item[2].collect { Path root -> "--receipt '${root}'" }.join(' ')
    """
    python -P '${projectDir}/tests/fixtures/ranking_four_arm_stub.py' \
        reviews --case-id '${item[0]}' --upstream '${item[1]}' ${receiptArgs} --output reference_reviews
    """
}

process RF_COPY {
    tag "rf-copy:${item[1]}:${item[3]}:${item[4]}"
    label 'm6_add_copy'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], item[1], item[2], file('reference_copy'))

    script:
    """
    PYTHONPATH='${projectDir}/src:${projectDir}' \
        python -P -m tests.fixtures.ranking_four_arm_cli \
        --source-root '${projectDir}' copy \
        --review-context '${item[2]}/context.json' \
        --admission-prior '${item[3]}' --seed-solution-id '${item[4]}' \
        --threads ${task.cpus} --output reference_copy
    """

    stub:
    """
    python -P '${projectDir}/tests/fixtures/ranking_four_arm_stub.py' \
        copy --case-id '${item[1]}' --upstream '${item[2]}' --admission-prior '${item[3]}' --seed-id '${item[4]}' --output reference_copy
    """
}

process RF_FINALISTS {
    tag "rf-finalists:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file('reference_finalists'))

    script:
    def receiptArgs = item[2].collect { Path root -> "--copy-receipt '${root}/bundle/reference_copy.json'" }.join(' ')
    """
    PYTHONPATH='${projectDir}/src:${projectDir}' \
        python -P -m tests.fixtures.ranking_four_arm_cli \
        --source-root '${projectDir}' finalists \
        --review-context '${item[1]}/context.json' ${receiptArgs} \
        --output reference_finalists
    """

    stub:
    def receiptArgs = item[2].collect { Path root -> "--receipt '${root}'" }.join(' ')
    """
    python -P '${projectDir}/tests/fixtures/ranking_four_arm_stub.py' \
        finalists --case-id '${item[0]}' --upstream '${item[1]}' ${receiptArgs} --output reference_finalists
    """
}

process RF_REFINE {
    tag "rf-refine:${item[1]}:${item[3]}:${item[4]}"
    label 'm6_refinement'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], item[1], item[2], file('reference_refinement'))

    script:
    """
    PYTHONPATH='${projectDir}/src:${projectDir}' \
        python -P -m tests.fixtures.ranking_four_arm_cli \
        --source-root '${projectDir}' refine \
        --finalist-context '${item[2]}/context.json' \
        --admission-prior '${item[3]}' --seed-solution-id '${item[4]}' \
        --threads ${task.cpus} --output reference_refinement
    """

    stub:
    """
    python -P '${projectDir}/tests/fixtures/ranking_four_arm_stub.py' \
        refine --case-id '${item[1]}' --upstream '${item[2]}' --admission-prior '${item[3]}' --seed-id '${item[4]}' --output reference_refinement
    """
}

process RF_IDENTITY {
    tag "rf-identity:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file('reference_identity'))

    script:
    def receiptArgs = item[2].collect { Path root -> "--refinement-receipt '${root}/bundle/reference_refinement.json'" }.join(' ')
    """
    PYTHONPATH='${projectDir}/src:${projectDir}' \
        python -P -m tests.fixtures.ranking_four_arm_cli \
        --source-root '${projectDir}' identity \
        --finalist-context '${item[1]}/context.json' ${receiptArgs} \
        --output reference_identity
    """

    stub:
    def receiptArgs = item[2].collect { Path root -> "--receipt '${root}'" }.join(' ')
    """
    python -P '${projectDir}/tests/fixtures/ranking_four_arm_stub.py' \
        identity --case-id '${item[0]}' --upstream '${item[1]}' ${receiptArgs} --output reference_identity
    """
}

process RF_AGGREGATE {
    tag 'rf-aggregate:fixed-five'
    label 'm6_small'
    publishDir "${params.outdir}", mode: 'copy', overwrite: true

    input:
    plan_context: Path
    prepared_contexts: List
    identity_contexts: List

    output:
    result: Path = file('reference_run')

    script:
    def preparedArgs = prepared_contexts.collect { Path path -> "--prepared-context '${path}'" }.join(' ')
    def identityArgs = identity_contexts.collect { Path path -> "--identity-context '${path}'" }.join(' ')
    """
    PYTHONPATH='${projectDir}/src:${projectDir}' \
        python -P -m tests.fixtures.ranking_four_arm_cli \
        --source-root '${projectDir}' aggregate \
        --plan-context '${plan_context}' ${preparedArgs} ${identityArgs} \
        --output reference_run
    """

    stub:
    def preparedArgs = prepared_contexts.collect { Path path -> "--prepared '${path}'" }.join(' ')
    def identityArgs = identity_contexts.collect { Path path -> "--identity '${path}'" }.join(' ')
    """
    python -P '${projectDir}/tests/fixtures/ranking_four_arm_stub.py' \
        aggregate ${preparedArgs} ${identityArgs} --output reference_run
    """
}
