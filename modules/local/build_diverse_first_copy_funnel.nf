nextflow.enable.types = true

process BUILD_DIVERSE_FIRST_COPY_FUNNEL {
    tag "diverse-first-copy-funnel:${crystal_id}"
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    predicted_coordinate_sources: Path
    predicted_prepared_models: Path
    pdb_coordinate_sources: Path
    coordinate_hit_mappings: Path
    experimental_prepared_models: Path
    sequence_groups: Path
    matthews: Path
    preflight: Path
    pipeline_config: Path
    crystal_id: String
    maximum_first_copy_jobs: Integer
    joint_copy_search: Boolean

    stage:
    stageAs predicted_coordinate_sources, 'predicted_coordinate_sources.jsonl'
    stageAs pdb_coordinate_sources, 'pdb_coordinate_sources.jsonl'

    output:
    funnel: Path = file('diverse_first_copy_funnel')

    script:
    def jointCopyArgument = joint_copy_search ? '--joint-copy-search' : ''
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        ranking diverse-first-copy-funnel \
        --coordinate-sources '${predicted_coordinate_sources}' \
        --coordinate-sources '${pdb_coordinate_sources}' \
        --processed-models '${predicted_prepared_models}/processed_models.jsonl' \
        --processed-models '${experimental_prepared_models}/processed_models.jsonl' \
        --model-preparation-manifest '${predicted_prepared_models}/model_preparation_manifest.json' \
        --model-preparation-manifest '${experimental_prepared_models}/model_preparation_manifest.json' \
        --coordinate-hit-mappings '${coordinate_hit_mappings}' \
        --sequence-groups '${sequence_groups}' \
        --matthews '${matthews}' \
        --preflight '${preflight}' \
        --config '${pipeline_config}' \
        --crystal-id '${crystal_id}' \
        --maximum-first-copy-jobs ${maximum_first_copy_jobs} \
        ${jointCopyArgument} \
        --outdir diverse_first_copy_funnel
    """

    stub:
    """
    cp -R \
        '${projectDir}/tests/fixtures/stubs/exact_predicted_funnel' \
        diverse_first_copy_funnel
    cp -R \
        '${projectDir}/tests/fixtures/stubs/predicted_model_preparation' \
        diverse_first_copy_funnel/model_registry
    """
}
