nextflow.enable.types = true

// Publish, but never execute, the zero-pack-only localisation reopen decision.
// Reopened hypotheses are retained for the separately authorised no-A pass-2
// expansion and cannot enlarge the 25-attempt pass-1 screen.
process PLAN_PHASE3_LOCALISATION_REOPEN {
    tag "phase3-localisation-reopen:${item[0]}"
    label 'process_low'
    stageInMode 'copy'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    item: Tuple
    localisation_bundle: Path

    output:
    plan: Tuple = tuple(
        item[0],
        file("phase3_localisation_reopen_${item[0]}")
    )

    script:
    def resultArguments = (item[2] as List<Path>)
        .sort { left, right -> left.name <=> right.name }
        .collect { result -> "--result-directory '${result}'" }
        .join(' ')
    def outputName = "phase3_localisation_reopen_${item[0]}"
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        localisation plan-batch-reopen \
        --funnel '${item[1]}' \
        ${resultArguments} \
        --localisation-bundle '${localisation_bundle}' \
        --maximum-reopened-attempts 175 \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "phase3_localisation_reopen_${item[0]}"
    """
    mkdir -p '${outputName}'
    printf '%s\n' \
        '{"schema_version":"2.0","adapter_version":"phase3-localisation-zero-pack-reopen-v1","crystal_id":"${item[0]}","status":"stub_not_executed","reopened_hypothesis_count":0}' \
        > '${outputName}/localisation_reopen_plan.json'
    : > '${outputName}/reopened_hypotheses.jsonl'
    """
}
