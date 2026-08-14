nextflow.enable.types = true

include { RUN_BRIEF_REFINEMENT } from '../modules/local/run_brief_refinement'

workflow BRIEF_REFINEMENT_WORKFLOW {
    take:
    finalists: Path
    sequence_groups: Path
    source_records: Path
    phenix_manifest: Path

    main:
    finalist_rows = finalists
        .splitCsv(header: true, sep: '\t')
        .map { row ->
            tuple(
                row.seed_solution_id as String,
                row.sequence_group_id as String,
                row.input_copy_count as Integer,
                file(row.parent_coordinate as String, checkIfExists: true),
                row.parent_coordinate_sha256 as String,
                file(row.parent_mtz as String, checkIfExists: true),
                row.parent_mtz_sha256 as String,
                row.resolution as Double
            )
        }
    refinement_results = RUN_BRIEF_REFINEMENT(
        finalist_rows,
        sequence_groups,
        source_records,
        phenix_manifest
    )

    emit:
    results: Path = refinement_results
}
