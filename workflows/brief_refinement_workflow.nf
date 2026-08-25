nextflow.enable.types = true

include {
    RUN_BRIEF_REFINEMENT;
    RUN_PHASE3_BRIEF_REFINEMENT
} from '../modules/local/run_brief_refinement'

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
                row.resolution as Double,
                row.observation_labels as String
            )
        }
    refinement_results = RUN_BRIEF_REFINEMENT(
        finalist_rows,
        sequence_groups.first(),
        source_records.first(),
        phenix_manifest.first()
    )

    emit:
    results: Path = refinement_results
}

workflow PHASE3_BRIEF_REFINEMENT_WORKFLOW {
    take:
    finalists: Path
    sequence_groups: Path
    source_records: Path
    phenix_manifest: Path
    crystal_dispatch: Path
    preflight: Path

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
                row.resolution as Double,
                row.observation_labels as String
            )
        }
    complete_items = finalist_rows
        .combine(sequence_groups.first())
        .combine(source_records.first())
        .combine(phenix_manifest.first())
        .combine(crystal_dispatch.first())
        .combine(preflight.first())
        .map {
            seedId,
            sequenceId,
            copyCount,
            parentCoordinate,
            parentCoordinateSha,
            parentMtz,
            parentMtzSha,
            resolution,
            observationLabels,
            sequences,
            sources,
            phenix,
            dispatch,
            preflightRecords ->
            tuple(
                tuple(
                    seedId,
                    sequenceId,
                    copyCount,
                    parentCoordinate,
                    parentCoordinateSha,
                    parentMtz,
                    parentMtzSha,
                    resolution,
                    observationLabels
                ),
                sequences,
                sources,
                phenix,
                dispatch.resolve('crystal_id.txt').toFile().text.trim(),
                file(
                    dispatch.resolve('phase3_diffraction_selection.json'),
                    checkIfExists: true
                ),
                file(dispatch.resolve('input.mtz'), checkIfExists: true),
                preflightRecords,
                file(
                    dispatch.resolve('phase3_free_r_identity.json'),
                    checkIfExists: true
                )
            )
        }
    refinement_results = RUN_PHASE3_BRIEF_REFINEMENT(complete_items)

    emit:
    results: Path = refinement_results
}
