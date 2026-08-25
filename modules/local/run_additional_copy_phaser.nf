nextflow.enable.types = true

process RUN_ADDITIONAL_COPY_PHASER {
    tag "add-copy:${seed[0]}"
    label 'process_mr'
    errorStrategy { task.exitStatus == 75 ? 'retry' : 'finish' }
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
        --expected-search-model-sha256 '${seed[2]}' \
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


// A reviewed Phase III seed carries its complete crystal-bound inputs in one
// scheduler item. Deep hashing preserves independent resume/cache behaviour.
process RUN_PHASE3_ADDITIONAL_COPY_PHASER {
    tag "phase3-add-copy:${item[0]}:${item[1]}"
    label 'process_mr'
    cache 'deep'
    errorStrategy { task.exitStatus == 75 ? 'retry' : 'finish' }
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    item: Tuple

    output:
    result: Tuple = tuple(
        item[0],
        item[1],
        file("phase3_additional_copy_${item[0]}_${item[1]}")
    )

    script:
    def outputName = "phase3_additional_copy_${item[0]}_${item[1]}"
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        mr add-copy \
        --review-validation '${item[4]}' \
        --review-package-manifest '${item[5]}' \
        --seed-solution-id '${item[1]}' \
        --hypotheses '${item[6]}' \
        --sequence-groups '${item[7]}' \
        --preflight '${item[8]}' \
        --mtz '${item[9]}' \
        --search-model '${item[2]}' \
        --expected-search-model-sha256 '${item[3]}' \
        --phenix-manifest '${item[10]}' \
        --diffraction-selection '${item[11]}' \
        --threads '${task.cpus}' \
        --until-expected \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "phase3_additional_copy_${item[0]}_${item[1]}"
    """
    mkdir -p '${outputName}'
    cp \
        '${projectDir}/tests/fixtures/stubs/additional_copy_result.jsonl' \
        '${outputName}/additional_copy_result.jsonl'
    cp \
        '${projectDir}/tests/fixtures/stubs/additional_copy_result.json' \
        '${outputName}/additional_copy_result.json'
    cp \
        '${projectDir}/tests/fixtures/stubs/phaser_command.json' \
        '${outputName}/phaser_command.json'
    cp '${projectDir}/tests/fixtures/stubs/add_copy.eff' '${outputName}/add_copy.eff'
    cp \
        '${projectDir}/tests/fixtures/stubs/additional_copy_series_results.jsonl' \
        '${outputName}/additional_copy_series_results.jsonl'
    cp \
        '${projectDir}/tests/fixtures/stubs/additional_copy_series_summary.json' \
        '${outputName}/additional_copy_series_summary.json'
    cp '${item[11]}' '${outputName}/phase3_diffraction_selection.json'
    printf '%s\n' '${item[0]}' > '${outputName}/phase3_crystal_id.txt'
    """
}
