nextflow.enable.types = true

/*
 * Phase III first-copy funnel with mandatory localisation/gel authority.
 */

process BUILD_PHASE3_DIVERSE_FIRST_COPY_FUNNEL {
    tag "phase3-diverse-first-copy-funnel:${crystal_id}"
    label 'process_low'
    publishDir params.outdir,
        mode: 'copy',
        overwrite: true,
        saveAs: { name -> "phase3/${crystal_id}/${name}" }

    input:
    predicted_coordinate_sources: Path
    predicted_prepared_models: Path
    pdb_coordinate_sources: Path
    coordinate_hit_mappings: Path
    experimental_prepared_models: Path
    sequence_groups: Path
    source_records: Path
    matthews: Path
    preflight: Path
    pipeline_config: Path
    localisation_bundle: Path
    crystal_id: String
    maximum_first_copy_jobs: Integer

    stage:
    stageAs predicted_coordinate_sources, 'predicted_coordinate_sources.jsonl'
    stageAs pdb_coordinate_sources, 'pdb_coordinate_sources.jsonl'

    output:
    funnel: Tuple = tuple(crystal_id, file('diverse_first_copy_funnel'))

    script:
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
        --source-records '${source_records}' \
        --matthews '${matthews}' \
        --preflight '${preflight}' \
        --config '${pipeline_config}' \
        --localisation-bundle '${localisation_bundle}' \
        --require-localisation-policy \
        --crystal-id '${crystal_id}' \
        --maximum-first-copy-jobs ${maximum_first_copy_jobs} \
        --joint-copy-search \
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
