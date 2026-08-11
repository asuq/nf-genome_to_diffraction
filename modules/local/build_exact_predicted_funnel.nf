nextflow.enable.types = true

process BUILD_EXACT_PREDICTED_FUNNEL {
    tag "exact-predicted-funnel:${crystal_id}"
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    coordinate_sources: Path
    prepared_models: Path
    sequence_groups: Path
    matthews: Path
    preflight: Path
    pipeline_config: Path
    crystal_id: String

    output:
    funnel: Path = file('exact_predicted_funnel')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        ranking exact-predicted-funnel \
        --coordinate-sources '${coordinate_sources}' \
        --processed-models '${prepared_models}/processed_models.jsonl' \
        --model-preparation-manifest '${prepared_models}/model_preparation_manifest.json' \
        --sequence-groups '${sequence_groups}' \
        --matthews '${matthews}' \
        --preflight '${preflight}' \
        --config '${pipeline_config}' \
        --crystal-id '${crystal_id}' \
        --outdir exact_predicted_funnel
    """

    stub:
    """
    cp -R \
        '${projectDir}/tests/fixtures/stubs/exact_predicted_funnel' \
        exact_predicted_funnel
    """
}
