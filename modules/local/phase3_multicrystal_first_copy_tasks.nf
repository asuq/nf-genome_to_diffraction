nextflow.enable.types = true

// Each Phase III hypothesis receives its own crystal, exact MTZ, immutable
// shared preparations, per-crystal funnel, and licensed Phenix binding. The
// existing first-copy adapter owns command construction and typed failure
// semantics; Nextflow owns one independent task per selected hypothesis.
process RUN_PHASE3_FIRST_COPY_PHASER {
    tag "phase3-first-copy:${item[1]}:${item[12].baseName}"
    label 'process_mr'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    item: Tuple

    output:
    result: Tuple = tuple(
        item[0],
        item[1],
        item[2],
        item[3],
        item[4],
        item[5],
        item[6],
        item[7],
        item[8],
        item[9],
        item[10],
        item[11],
        file("phase3_first_copy_${item[1]}_${item[12].baseName}")
    )

    script:
    def outputName = "phase3_first_copy_${item[1]}_${item[12].baseName}"
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        mr first-copy \
        --hypotheses '${item[12]}' \
        --hypothesis-id '${item[12].baseName}' \
        --sequence-groups '${item[6]}' \
        --processed-models '${item[2]}/model_registry/processed_models.jsonl' \
        --model-preparation-manifest '${item[2]}/model_registry/model_preparation_manifest.json' \
        --preflight '${item[9]}' \
        --mtz '${item[3]}/input.mtz' \
        --phenix-manifest '${item[11]}' \
        --threads '${task.cpus}' \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "phase3_first_copy_${item[1]}_${item[12].baseName}"
    """
    cp -R \
        '${projectDir}/tests/fixtures/stubs/first_copy_phaser' \
        '${outputName}'
    """
}


// Aggregate only this crystal's selected first-copy tasks. Empty scientific
// no-model branches still produce their own review package; approval templates
// remain empty until an explicit independently staged human decision exists.
process BUILD_PHASE3_MR_SEED_REVIEW {
    tag "phase3-mr-seed-review:${item[0]}"
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true
    stageInMode 'copy'

    input:
    item: Tuple

    output:
    review: Tuple = tuple(
        item[0],
        file("phase3_mr_seed_review_${item[0]}")
    )

    script:
    def outputName = "phase3_mr_seed_review_${item[0]}"
    def results = item[2] as List<Path>
    def resultJsonl = results
        .sort { left, right -> left.name <=> right.name }
        .collect { result -> "'${result}/normalised_mr_result.jsonl'" }
        .join(' ')
    def resultCommand = results.isEmpty()
        ? 'touch normalised_mr_results.jsonl'
        : "cat ${resultJsonl} > normalised_mr_results.jsonl"
    """
    ${resultCommand}
    genome-to-diffraction \
        --no-progress \
        --log-format json \
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
    def outputName = "phase3_mr_seed_review_${item[0]}"
    """
    cp -R \
        '${projectDir}/tests/fixtures/stubs/mr_seed_review' \
        '${outputName}'
    """
}
