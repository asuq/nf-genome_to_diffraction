nextflow.enable.types = true

// Aggregate every first-copy result and invoke the existing checksum-gated
// retain-all review builder. The generated approval file is empty: downstream
// copy placement still requires an explicit, separately validated human edit.
process BUILD_MR_SEED_REVIEW {
    tag 'first-copy-mr-seed-review'
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true
    stageInMode 'copy'

    input:
    funnel: Path
    first_copy_results: List<Path>
    sequence_groups: Path
    source_records: Path
    matthews: Path
    pipeline_config: Path

    output:
    review: Path = file('mr_seed_review')

    script:
    def resultJsonl = first_copy_results
        .sort { left, right -> left.name <=> right.name }
        .collect { result -> "'${result}/normalised_mr_result.jsonl'" }
        .join(' ')
    def resultCommand = first_copy_results.isEmpty()
        ? 'touch normalised_mr_results.jsonl'
        : "cat ${resultJsonl} > normalised_mr_results.jsonl"
    """
    ${resultCommand}
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        review build-mr-seed \
        --hypotheses '${funnel}/mr_hypotheses.jsonl' \
        --results normalised_mr_results.jsonl \
        --result-root . \
        --funnel-manifest '${funnel}/funnel_manifest.json' \
        --sequence-groups '${sequence_groups}' \
        --source-records '${source_records}' \
        --matthews '${matthews}' \
        --config '${pipeline_config}' \
        --outdir mr_seed_review
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/mr_seed_review' mr_seed_review
    """
}
