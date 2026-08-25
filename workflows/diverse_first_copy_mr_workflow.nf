nextflow.enable.types = true

include { BUILD_DIVERSE_FIRST_COPY_FUNNEL } from '../modules/local/build_diverse_first_copy_funnel'
include { RUN_FIRST_COPY_PHASER } from '../modules/local/run_first_copy_phaser'

workflow DIVERSE_FIRST_COPY_MR_WORKFLOW {
    take:
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
    mtz: Path
    phenix_manifest: Path

    main:
    funnel_bundle = BUILD_DIVERSE_FIRST_COPY_FUNNEL(
        predicted_coordinate_sources,
        predicted_prepared_models,
        pdb_coordinate_sources,
        coordinate_hit_mappings,
        experimental_prepared_models,
        sequence_groups,
        matthews,
        preflight,
        pipeline_config,
        crystal_id,
        maximum_first_copy_jobs,
        joint_copy_search
    )
    hypothesis_records = funnel_bundle
        .flatMap { Path bundle ->
            Path records = bundle.resolve('hypotheses')
            records.list().sort().collect { String name -> records.resolve(name) }
        }
    aggregate_model_registry = funnel_bundle
        .map { Path bundle -> bundle.resolve('model_registry') }
        .first()
    first_copy_results = RUN_FIRST_COPY_PHASER(
        hypothesis_records,
        sequence_groups.first(),
        aggregate_model_registry,
        preflight.first(),
        mtz.first(),
        phenix_manifest.first()
    )

    emit:
    funnel: Path = funnel_bundle
    results: Path = first_copy_results
}
