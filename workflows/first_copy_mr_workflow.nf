nextflow.enable.types = true

include { BUILD_EXACT_PREDICTED_FUNNEL } from '../modules/local/build_exact_predicted_funnel'
include { RUN_FIRST_COPY_PHASER } from '../modules/local/run_first_copy_phaser'

workflow FIRST_COPY_MR_WORKFLOW {
    take:
    coordinate_sources: Path
    prepared_models: Path
    sequence_groups: Path
    matthews: Path
    preflight: Path
    pipeline_config: Path
    crystal_id: String
    mtz: Path
    phenix_manifest: Path

    main:
    funnel_bundle = BUILD_EXACT_PREDICTED_FUNNEL(
        coordinate_sources,
        prepared_models,
        sequence_groups,
        matthews,
        preflight,
        pipeline_config,
        crystal_id
    )
    hypothesis_records = funnel_bundle
        .flatMap { Path bundle ->
            Path records = bundle.resolve('hypotheses')
            records.list().sort().collect { String name -> records.resolve(name) }
        }
    first_copy_results = RUN_FIRST_COPY_PHASER(
        hypothesis_records,
        sequence_groups.first(),
        prepared_models.first(),
        preflight.first(),
        mtz.first(),
        phenix_manifest.first(),
        false
    )

    emit:
    funnel: Path = funnel_bundle
    results: Path = first_copy_results
}
