nextflow.enable.types = true

// Cross the first human checkpoint only through an explicit decision file.
// The Python adapter revalidates the exact review manifest and assets, then
// stages every approved solution coordinate without applying a score filter.
process STAGE_APPROVED_MR_SEEDS {
    tag 'approved-mr-seeds'
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true
    stageInMode 'copy'

    input:
    review_package: Path
    decisions: Path
    hypotheses: Path

    output:
    stage: Path = file('approved_mr_seed_stage')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        mr stage-approved-seeds \
        --review-package '${review_package}' \
        --decisions '${decisions}' \
        --hypotheses '${hypotheses}' \
        --outdir approved_mr_seed_stage
    """

    stub:
    """
    cp -R \
        '${projectDir}/tests/fixtures/stubs/approved_mr_seed_stage' \
        approved_mr_seed_stage
    printf 'seed_solution_id\tsearch_model\tsearch_model_sha256\texpected_copy_count\trequires_additional_copy\nsol_cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\t%s\te38fba8177fbb677bd5efb444debe1f1e99a26da2f3c93ae4fb06347f00fb378\t3\ttrue\n' \
        "\$PWD/approved_mr_seed_stage/models/stub.pdb" \
        > approved_mr_seed_stage/approved_seeds.tsv
    cp \
        approved_mr_seed_stage/approved_seeds.tsv \
        approved_mr_seed_stage/additional_copy_seeds.tsv
    """
}
