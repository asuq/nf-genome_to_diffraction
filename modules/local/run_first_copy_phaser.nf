nextflow.enable.types = true

process RUN_FIRST_COPY_PHASER {
    tag "first-copy-phaser:${hypothesis.baseName}"
    label 'process_mr'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    hypothesis: Path
    sequence_groups: Path
    prepared_models: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path

    output:
    result: Path = file("first_copy_phaser_${hypothesis.baseName}")

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        mr first-copy \
        --hypotheses '${hypothesis}' \
        --hypothesis-id '${hypothesis.baseName}' \
        --sequence-groups '${sequence_groups}' \
        --processed-models '${prepared_models}/processed_models.jsonl' \
        --model-preparation-manifest '${prepared_models}/model_preparation_manifest.json' \
        --preflight '${preflight}' \
        --mtz '${mtz}' \
        --phenix-manifest '${phenix_manifest}' \
        --threads '${task.cpus}' \
        --outdir 'first_copy_phaser_${hypothesis.baseName}'
    """

    stub:
    """
    cp -R \
        '${projectDir}/tests/fixtures/stubs/first_copy_phaser' \
        'first_copy_phaser_${hypothesis.baseName}'
    """
}
