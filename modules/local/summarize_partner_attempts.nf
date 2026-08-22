nextflow.enable.types = true

process SUMMARIZE_PARTNER_ATTEMPTS {
    tag 'partner-attempt-summary'
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    partner_plan: Path
    partner_results: List<Path>

    output:
    summary: Path = file('partner_attempt_summary.json')

    script:
    def resultArguments = partner_results
        .collect { Path result -> "--result-directory '${result}'" }
        .join(' \\\n        ')
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        mr summarize-partners \
        --partner-plan '${partner_plan}/partner_search_plan.json' \
        ${resultArguments} \
        --output partner_attempt_summary.json
    """

    stub:
    """
    cp \
        '${projectDir}/tests/fixtures/stubs/partner_attempt_summary.json' \
        partner_attempt_summary.json
    """
}
