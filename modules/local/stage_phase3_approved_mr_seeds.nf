nextflow.enable.types = true

// Cross the Phase III A checkpoint only through its canonical owned-run stage.
// The existing Python adapter independently binds the legacy review asset
// manifest to the schema-v2 evidence and retains rejected/deferred outcomes.
process STAGE_PHASE3_APPROVED_MR_SEEDS {
    tag 'phase3-approved-mr-seeds'
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true
    stageInMode 'copy'

    input:
    review_package: Path
    review_stage: Path
    phase3_package: Path
    hypotheses: Path

    output:
    stage: Path = file('approved_mr_seed_stage')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        mr stage-approved-seeds \
        --review-package ${review_package} \
        --decisions ${review_stage}/phase3_review_decision.json \
        --phase3-review-stage ${review_stage} \
        --phase3-review-package-manifest ${phase3_package}/phase3_review_package_manifest.json \
        --hypotheses ${hypotheses} \
        --outdir approved_mr_seed_stage
    """

    stub:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        mr stage-approved-seeds \
        --review-package ${review_package} \
        --decisions ${review_stage}/phase3_review_decision.json \
        --phase3-review-stage ${review_stage} \
        --phase3-review-package-manifest ${phase3_package}/phase3_review_package_manifest.json \
        --hypotheses ${hypotheses} \
        --outdir approved_mr_seed_stage
    """
}
