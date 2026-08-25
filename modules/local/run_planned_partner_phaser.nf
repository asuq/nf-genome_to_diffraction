nextflow.enable.types = true

process RUN_PLANNED_PARTNER_PHASER {
    tag "planned-partner:${candidate_id}"
    label 'process_mr'
    errorStrategy { task.exitStatus == 75 ? 'retry' : 'finish' }
    publishDir params.outdir, mode: 'copy', overwrite: true
    stageInMode 'copy'

    input:
    candidate_id: String
    approved_stage: Path
    review_package: Path
    partner_plan: Path
    sequence_groups: Path
    model_registry: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path

    output:
    result: Path = file("planned_partner_${candidate_id}")

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        mr planned-partner \
        --approved-stage '${approved_stage}' \
        --review-package '${review_package}' \
        --partner-plan '${partner_plan}/partner_search_plan.json' \
        --partner-candidate-id '${candidate_id}' \
        --sequence-groups '${sequence_groups}' \
        --model-registry '${model_registry}' \
        --preflight '${preflight}' \
        --mtz '${mtz}' \
        --phenix-manifest '${phenix_manifest}' \
        --threads '${task.cpus}' \
        --outdir 'planned_partner_${candidate_id}'
    """

    stub:
    """
    cp -R \
        '${projectDir}/tests/fixtures/stubs/approved_partner_search' \
        'planned_partner_${candidate_id}'
    """
}
