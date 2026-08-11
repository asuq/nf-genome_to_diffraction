nextflow.enable.types = true

process PREPARE_PREDICTED_MODELS {
    tag 'confidence-process-exact-predicted-models'
    label 'process_phenix'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    coordinate_sources: Path
    sequence_groups: Path
    phenix_manifest: Path

    output:
    prepared_models: Path = file('predicted_model_preparation')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        model prepare-predicted \
        --coordinate-sources '${coordinate_sources}' \
        --sequence-groups '${sequence_groups}' \
        --phenix-manifest '${phenix_manifest}' \
        --outdir predicted_model_preparation
    """

    stub:
    """
    cp -R \
        '${projectDir}/tests/fixtures/stubs/predicted_model_preparation' \
        predicted_model_preparation
    """
}
