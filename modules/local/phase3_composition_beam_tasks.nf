nextflow.enable.types = true

process PLAN_PHASE3_COMPOSITION_DEPTH {
    tag "composition-depth-plan:${item[0]}"
    label 'process_local'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file("composition_depth_${item[0]}"), item)

    script:
    def outputName = "composition_depth_${item[0]}"
    """
    genome-to-diffraction --no-progress --log-format json \
        composition plan-depth \
        --parent-states '${item[1]}' \
        --sequence-groups '${item[2]}' \
        --localisation-policy '${item[3]}' \
        --active-wave-completion '${item[4]}' \
        --localisation-reopen-plan '${item[5]}' \
        --gel-evidence '${item[6]}' \
        --preflight '${item[7]}' \
        --model-registry '${item[8]}' \
        --model-ranking-evidence '${item[9]}' \
        --diffraction-selection '${item[10]}' \
        --free-r-identity '${item[11]}' \
        --fixed-coordinate-root '${item[12]}' \
        --execution-identity '${item[13]}' \
        --finding-closure '${item[18]}' \
        --finding-ledger '${item[19]}' \
        --adverse-review-evidence '${item[20]}' \
        --integration-gate-evidence '${item[21]}' \
        --known-control-evidence '${item[22]}' \
        --m6-evidence '${item[23]}' \
        --unknown-pass1-evidence '${item[24]}' \
        --exact-source-ci-evidence '${item[25]}' \
        --global-attempts-used-before '${item[16]}' \
        --per-depth-attempt-budget '${item[17]}' \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "composition_depth_${item[0]}"
    """
    mkdir -p '${outputName}'
    printf '%s\n' \
        '{"schema_version":"2.0","adapter_version":"phase3-composition-depth-input-v1","crystal_id":"${item[0]}","parent_depth":1,"target_depth":2,"attempt_count":0,"global_attempts_used_before":${item[16]},"per_depth_attempt_budget":${item[17]}}' \
        > '${outputName}/composition_depth_input_manifest.json'
    printf '%s\n' '{"attempts":[]}' \
        > '${outputName}/composition_attempt_inventory.json'
    : > '${outputName}/parent_states.jsonl'
    """
}

process RUN_PHASE3_BEAM_ATTEMPT {
    tag "composition-beam-attempt:${item[1]}"
    label 'process_mr'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(
        item[10], item[0], item[11], item[12],
        file("composition_attempt_${item[1]}")
    )

    script:
    def outputName = "composition_attempt_${item[1]}"
    """
    genome-to-diffraction --no-progress --log-format json \
        composition run-attempt \
        --attempt-inventory '${item[2]}' \
        --attempt-id '${item[1]}' \
        --fixed-coordinate-root '${item[3]}' \
        --model-registry '${item[4]}' \
        --sequence-groups '${item[5]}' \
        --preflight '${item[6]}' \
        --mtz '${item[7]}' \
        --phenix-manifest '${item[8]}' \
        --execution-identity '${item[9]}' \
        --threads '${task.cpus}' \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "composition_attempt_${item[1]}"
    """
    mkdir -p '${outputName}'
    printf '%s\n' '{"attempt_id":"${item[1]}","execution_status":"stub_not_executed"}' \
        > '${outputName}/composition_attempt_stub.json'
    """
}

process COLLECT_PHASE3_COMPOSITION_DEPTH {
    tag "composition-depth-collect:${item[0]}"
    label 'process_local'
    publishDir params.outdir, mode: 'copy', overwrite: false

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file("composition_beam_${item[0]}_*"), item[2])

    script:
    def plan = new groovy.json.JsonSlurper().parseText(
        item[1].resolve('composition_depth_input_manifest.json').toFile().text
    )
    def outputName = "composition_beam_${item[0]}_depth${plan.target_depth}"
    def resultArgs = (item[3] as List<Path>).collect { path ->
        "--attempt-result '${path}'"
    }.join(' ')
    """
    genome-to-diffraction --no-progress --log-format json \
        composition collect-depth \
        --attempt-inventory '${item[1]}/composition_attempt_inventory.json' \
        ${resultArgs} \
        --beam-width 3 \
        --outdir '${outputName}'
    """

    stub:
    def plan = new groovy.json.JsonSlurper().parseText(
        item[1].resolve('composition_depth_input_manifest.json').toFile().text
    )
    def outputName = "composition_beam_${item[0]}_depth${plan.target_depth}"
    """
    mkdir -p '${outputName}'
    : > '${outputName}/retained_parent_states.jsonl'
    : > '${outputName}/attempt_evidence.jsonl'
    printf '%s\n' \
        '{"schema_version":"2.0","adapter_version":"phase3-composition-beam-depth-v1","crystal_id":"${item[0]}","parent_depth":1,"target_depth":2,"attempt_count":0,"retained_parent_count":0,"global_attempts_used_after":${item[2][16]},"status":"terminal","stop_reason":"no_retained_packed_state","provisional_component_depth":false}' \
        > '${outputName}/composition_beam_depth_result.json'
    """
}

process BUILD_PHASE3_PASS2_REVIEW_PACKAGES {
    tag "phase3-pass2-review:${item[0]}"
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: false
    stageInMode 'copy'

    input:
    item: Tuple
    owned_parent_run_id: String

    output:
    packages: Tuple = tuple(
        item[0], file("phase3_pass2_review_${item[0]}")
    )

    script:
    def outputName = "phase3_pass2_review_${item[0]}"
    """
    genome-to-diffraction --no-progress --log-format json \
        review build-pass2-packages \
        --beam '${item[1]}' \
        --execution-identity '${item[2][13]}' \
        --owned-parent-run '${owned_parent_run_id}' \
        --crystal-id '${item[0]}' \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "phase3_pass2_review_${item[0]}"
    """
    mkdir -p '${outputName}/composition' '${outputName}/sequence'
    printf '%s\n' 'scientific execution not performed in stub mode' \
        > '${outputName}/phase3_pass2_review.stub'
    """
}
