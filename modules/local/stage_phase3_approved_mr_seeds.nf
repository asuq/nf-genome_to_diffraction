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


// Independent reviewed crystals must never publish into the same stage or
// consume another crystal's authenticated package, decisions, or hypotheses.
process STAGE_PHASE3_CRYSTAL_APPROVED_MR_SEEDS {
    tag "phase3-approved-mr-seeds:${item[0]}"
    label 'process_low'
    cache 'deep'
    publishDir params.outdir, mode: 'copy', overwrite: true
    stageInMode 'copy'

    input:
    item: Tuple

    output:
    stage: Tuple = tuple(
        item[0],
        file("phase3_approved_mr_seed_${item[0]}")
    )

    script:
    def outputName = "phase3_approved_mr_seed_${item[0]}"
    def ownershipArguments = item.size() == 8
        ? "--phase3-owned-run-registry '${item[5]}' " +
            "--phase3-execution-identity '${item[6]}' " +
            "--phase3-owned-parent-run '${item[7]}'"
        : ''
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        mr stage-approved-seeds \
        --review-package '${item[1]}' \
        --decisions '${item[2]}/phase3_review_decision.json' \
        --phase3-review-stage '${item[2]}' \
        --phase3-review-package-manifest '${item[3]}/phase3_review_package_manifest.json' \
        --hypotheses '${item[4]}' \
        ${ownershipArguments} \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "phase3_approved_mr_seed_${item[0]}"
    def ownershipArguments = item.size() == 8
        ? "--phase3-owned-run-registry '${item[5]}' " +
            "--phase3-execution-identity '${item[6]}' " +
            "--phase3-owned-parent-run '${item[7]}'"
        : ''
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        mr stage-approved-seeds \
        --review-package '${item[1]}' \
        --decisions '${item[2]}/phase3_review_decision.json' \
        --phase3-review-stage '${item[2]}' \
        --phase3-review-package-manifest '${item[3]}/phase3_review_package_manifest.json' \
        --hypotheses '${item[4]}' \
        ${ownershipArguments} \
        --outdir '${outputName}'
    """
}
