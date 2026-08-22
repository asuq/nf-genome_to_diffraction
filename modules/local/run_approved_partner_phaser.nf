nextflow.enable.types = true

// Cross the existing MR-seed checkpoint, then search the fixed 6RTZ B model.
// The Python bridge revalidates the approved stage and review-owned A evidence.
process RUN_APPROVED_PARTNER_PHASER {
    tag 'approved-partner:6RTZ'
    label 'process_mr'
    errorStrategy 'finish'
    publishDir params.outdir, mode: 'copy', overwrite: true
    stageInMode 'copy'

    input:
    approved_stage: Path
    review_package: Path
    control_preparation: Path
    sequence_groups: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path

    output:
    result: Path = file('approved_partner_search')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        mr approved-partner \
        --approved-stage '${approved_stage}' \
        --review-package '${review_package}' \
        --control-preparation '${control_preparation}/preparation_manifest.json' \
        --sequence-groups '${sequence_groups}' \
        --preflight '${preflight}' \
        --mtz '${mtz}' \
        --phenix-manifest '${phenix_manifest}' \
        --threads '${task.cpus}' \
        --outdir approved_partner_search
    """

    stub:
    """
    cp -R \
        '${projectDir}/tests/fixtures/stubs/approved_partner_search' \
        approved_partner_search
    """
}
