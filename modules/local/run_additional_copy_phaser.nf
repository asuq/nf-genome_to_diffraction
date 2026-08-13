nextflow.enable.types = true

process RUN_ADDITIONAL_COPY_PHASER {
    tag "add-copy:${seed[0]}"
    label 'process_mr'
    errorStrategy 'finish'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    seed: Tuple
    review_validation: Path
    review_package: Path
    hypotheses: Path
    sequence_groups: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path

    output:
    result: Path = file("additional_copy_${seed[0]}")

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        mr add-copy \
        --review-validation '${review_validation}' \
        --review-package-manifest '${review_package}' \
        --seed-solution-id '${seed[0]}' \
        --hypotheses '${hypotheses}' \
        --sequence-groups '${sequence_groups}' \
        --preflight '${preflight}' \
        --mtz '${mtz}' \
        --search-model '${seed[1]}' \
        --phenix-manifest '${phenix_manifest}' \
        --threads '${task.cpus}' \
        --until-expected \
        --outdir 'additional_copy_${seed[0]}'
    """

    stub:
    """
    mkdir -p 'additional_copy_${seed[0]}'
    cp \
        '${projectDir}/tests/fixtures/stubs/additional_copy_result.jsonl' \
        'additional_copy_${seed[0]}/additional_copy_result.jsonl'
    cp \
        '${projectDir}/tests/fixtures/stubs/additional_copy_result.json' \
        'additional_copy_${seed[0]}/additional_copy_result.json'
    cp \
        '${projectDir}/tests/fixtures/stubs/phaser_command.json' \
        'additional_copy_${seed[0]}/phaser_command.json'
    cp \
        '${projectDir}/tests/fixtures/stubs/add_copy.eff' \
        'additional_copy_${seed[0]}/add_copy.eff'
    cp \
        '${projectDir}/tests/fixtures/stubs/additional_copy_series_results.jsonl' \
        'additional_copy_${seed[0]}/additional_copy_series_results.jsonl'
    cp \
        '${projectDir}/tests/fixtures/stubs/additional_copy_series_summary.json' \
        'additional_copy_${seed[0]}/additional_copy_series_summary.json'
    """
}
