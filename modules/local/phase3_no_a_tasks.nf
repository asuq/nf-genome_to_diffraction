nextflow.enable.types = true

process RUN_PHASE3_NO_A_FIRST_COPY {
    tag "phase3-no-a:${item[0]}:${item[1]}"
    label 'process_mr'
    publishDir params.outdir, mode: 'copy', overwrite: false

    input:
    item: Tuple

    output:
    result: Tuple = tuple(
        item[10], item[0], item[2], item[11],
        file("first_copy_phaser_${item[1]}")
    )

    script:
    def outputName = "first_copy_phaser_${item[1]}"
    def registryRoot = item[4].parent
    """
    genome-to-diffraction --no-progress --log-format json \
        mr first-copy \
        --hypotheses '${item[2]}/mr_hypotheses.jsonl' \
        --hypothesis-id '${item[1]}' \
        --sequence-groups '${item[3]}' \
        --processed-models '${registryRoot}/processed_models.jsonl' \
        --all-model-registry '${item[4]}' \
        --preflight '${item[5]}' \
        --mtz '${item[6]}' \
        --diffraction-selection '${item[7]}' \
        --derive-phase3-hypothesis-id \
        --phenix-manifest '${item[8]}' \
        --threads '${task.cpus}' \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "first_copy_phaser_${item[1]}"
    """
    mkdir -p '${outputName}'
    printf '%s\n' '{"execution_status":"stub_not_executed"}' \
        > '${outputName}/normalised_mr_result.jsonl'
    """
}

process BUILD_PHASE3_NO_A_REVIEW {
    tag "phase3-no-a-review:${item[0]}"
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: false
    stageInMode 'copy'

    input:
    item: Tuple

    output:
    review: Tuple = tuple(item[0], file("phase3_no_a_review_${item[0]}"))

    script:
    def outputName = "phase3_no_a_review_${item[0]}"
    def results = item[2]
    def resultJsonl = results.sort { left, right -> left.name <=> right.name }
        .collect { result -> "'${result}/normalised_mr_result.jsonl'" }
        .join(' ')
    """
    cat ${resultJsonl} > normalised_mr_results.jsonl
    genome-to-diffraction --no-progress --log-format json \
        review build-mr-seed \
        --hypotheses '${item[1]}/mr_hypotheses.jsonl' \
        --results normalised_mr_results.jsonl \
        --result-root . \
        --funnel-manifest '${item[1]}/funnel_manifest.json' \
        --sequence-groups '${item[3]}' \
        --source-records '${item[4]}' \
        --matthews '${item[5]}' \
        --config '${item[6]}' \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "phase3_no_a_review_${item[0]}"
    """
    mkdir -p '${outputName}'
    printf '%s\n' '{"schema_version":"1.0","stub":true}' \
        > '${outputName}/mr_seed_review_manifest.json'
    """
}

process BUILD_PHASE3_NO_A_OWNED_REVIEW {
    tag "phase3-no-a-owned-review:${item[0]}"
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: false
    stageInMode 'copy'

    input:
    item: Tuple

    output:
    owned_review: Tuple = tuple(
        item[0], file("phase3_owned_a_review_${item[0]}")
    )

    script:
    def outputName = "phase3_owned_a_review_${item[0]}"
    """
    genome-to-diffraction --no-progress --log-format json \
        review build-owned-a-package \
        --review-package '${item[1]}' \
        --hypotheses '${item[2]}' \
        --execution-identity '${item[3]}' \
        --owned-parent-run '${item[4]}' \
        --parent-profile unknown-pass2 \
        --parent-phase phase3-pass2 \
        --crystal-id '${item[0]}' \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "phase3_owned_a_review_${item[0]}"
    """
    mkdir -p '${outputName}'
    printf '%s\n' 'scientific execution not performed in stub mode' \
        > '${outputName}/phase3_owned_a_review.stub'
    """
}
