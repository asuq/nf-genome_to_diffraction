nextflow.enable.types = true

include { RUN_ADDITIONAL_COPY_PHASER } from '../modules/local/run_additional_copy_phaser'

workflow ADDITIONAL_COPY_WORKFLOW {
    take:
    seeds: Path
    review_validation: Path
    review_package: Path
    hypotheses: Path
    sequence_groups: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path

    main:
    seed_rows = seeds
        .splitCsv(header: true, sep: '\t')
        .map { row ->
            tuple(
                row.seed_solution_id as String,
                file(row.search_model as String, checkIfExists: true),
                row.search_model_sha256 as String
            )
        }
    additional_copy_results = RUN_ADDITIONAL_COPY_PHASER(
        seed_rows,
        review_validation,
        review_package,
        hypotheses,
        sequence_groups,
        preflight,
        mtz,
        phenix_manifest
    )

    emit:
    results: Path = additional_copy_results
}
