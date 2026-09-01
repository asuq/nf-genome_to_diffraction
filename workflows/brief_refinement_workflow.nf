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
    refinement_results = RUN_PHASE3_BRIEF_REFINEMENT(complete_items).map {
        crystalId, seedId, result -> result
    }

    emit:
    results: Path = refinement_results
}


// Every finalist table and all immutable inputs belong to one reviewed crystal;
// no shared singleton, selected observation, or Free-R array can cross keys.
workflow PHASE3_MULTICRYSTAL_BRIEF_REFINEMENT_WORKFLOW {
    take:
    staged_crystals: Tuple

    main:
    complete_items = staged_crystals.flatMap { crystalId, stage, dispatch ->
        String expectedCrystal = crystalId as String
        if (
            dispatch.resolve('crystal_id.txt').toFile().text.trim() !=
            expectedCrystal
        ) {
            error "Phase III refinement dispatch belongs to another crystal: ${crystalId}"
        }
        Path finalists = stage.resolve('finalists.tsv')
        def rows = finalists.toFile().readLines()
        if (rows.isEmpty()) {
            error "Phase III refinement finalist table is empty for ${crystalId}"
        }
        def required = [
            'seed_solution_id',
            'sequence_group_id',
            'input_copy_count',
            'parent_coordinate',
            'parent_coordinate_sha256',
            'parent_mtz',
            'parent_mtz_sha256',
            'resolution',
            'observation_labels'
        ]
        if (rows[0].split('\t', -1).toList() != required) {
            error "Phase III refinement finalist headers differ for ${crystalId}"
        }
        rows.drop(1).findAll { String line -> !line.isEmpty() }.collect {
            String line ->
            def columns = line.split('\t', -1)
            if (columns.size() != required.size()) {
                error "Phase III refinement finalist is incomplete for ${crystalId}"
            }
            tuple(
                tuple(
                    columns[0],
                    columns[1],
                    columns[2] as Integer,
                    file(stage.resolve(columns[3]), checkIfExists: true),
                    columns[4],
                    file(stage.resolve(columns[5]), checkIfExists: true),
                    columns[6],
                    columns[7] as Double,
                    columns[8]
                ),
                file(stage.resolve('inputs/sequence_groups.jsonl'), checkIfExists: true),
                file(stage.resolve('inputs/source_records.jsonl'), checkIfExists: true),
                file(stage.resolve('inputs/phenix_manifest.json'), checkIfExists: true),
                expectedCrystal,
                file(
                    dispatch.resolve('phase3_diffraction_selection.json'),
                    checkIfExists: true
                ),
                file(dispatch.resolve('input.mtz'), checkIfExists: true),
                file(stage.resolve('inputs/preflight.jsonl'), checkIfExists: true),
                file(
                    dispatch.resolve('phase3_free_r_identity.json'),
                    checkIfExists: true
                )
            )
        }
    }
    refinement_results = RUN_PHASE3_BRIEF_REFINEMENT(complete_items)

    emit:
    results: Tuple = refinement_results
}
