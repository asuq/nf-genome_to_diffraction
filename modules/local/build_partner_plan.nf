nextflow.enable.types = true

process BUILD_PARTNER_PLAN {
    tag "partner-plan:${crystal_id}"
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    approved_stage: Path
    sequence_groups: Path
    matthews: Path
    preflight: Path
    pipeline_config: Path
    model_registry: Path
    crystal_id: String
    partner_copy_count: Integer

    output:
    plan: Path = file('partner_search_plan')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        ranking approved-partner-plan \
        --approved-stage '${approved_stage}' \
        --crystal-id '${crystal_id}' \
        --partner-copy-count '${partner_copy_count}' \
        --sequence-groups '${sequence_groups}' \
        --matthews '${matthews}' \
        --preflight '${preflight}' \
        --config '${pipeline_config}' \
        --model-registry '${model_registry}' \
        --outdir partner_search_plan
    """

    stub:
    """
    if [ -f '${model_registry}/p6_empty_partner.stub' ]; then
        cp -R \
            '${model_registry}/partner_search_plan' \
            partner_search_plan
    else
        cp -R \
            '${projectDir}/tests/fixtures/stubs/partner_search_plan' \
            partner_search_plan
    fi
    """
}
