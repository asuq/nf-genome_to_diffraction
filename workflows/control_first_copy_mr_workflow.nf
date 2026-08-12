nextflow.enable.types = true

include { RUN_FIRST_COPY_PHASER } from '../modules/local/run_first_copy_phaser'

workflow CONTROL_FIRST_COPY_MR_WORKFLOW {
    take:
    control_bundle: Path
    sequence_groups: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path

    main:
    hypothesis_records = control_bundle
        .flatMap { Path bundle ->
            Path records = bundle.resolve('hypotheses')
            records.list().sort().collect { String name -> records.resolve(name) }
        }
    prepared_models = control_bundle
        .map { Path bundle -> bundle }
        .first()
    first_copy_results = RUN_FIRST_COPY_PHASER(
        hypothesis_records,
        sequence_groups,
        prepared_models,
        preflight,
        mtz,
        phenix_manifest
    )

    emit:
    results: Path = first_copy_results
}
