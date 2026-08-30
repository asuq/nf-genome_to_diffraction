nextflow.enable.types = true

process RUN_BRIEF_REFINEMENT {
    tag "t12:${finalist[0]}"
    label 'process_refine'
    errorStrategy { task.exitStatus == 75 ? 'retry' : 'finish' }
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    finalist: Tuple
    sequence_groups: Path
    source_records: Path
    phenix_manifest: Path

    output:
    result: Path = file("t12_${finalist[0]}")

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        refinement brief \
        --seed-solution-id '${finalist[0]}' \
        --sequence-group-id '${finalist[1]}' \
        --input-copy-count '${finalist[2]}' \
        --parent-coordinate '${finalist[3]}' \
        --parent-coordinate-sha256 '${finalist[4]}' \
        --parent-mtz '${finalist[5]}' \
        --parent-mtz-sha256 '${finalist[6]}' \
        --resolution '${finalist[7]}' \
        --observation-labels '${finalist[8]}' \
        --sequence-groups '${sequence_groups}' \
        --source-records '${source_records}' \
        --phenix-manifest '${phenix_manifest}' \
        --threads '${task.cpus}' \
        --outdir 't12_${finalist[0]}'
    """

    stub:
    """
    mkdir -p 't12_${finalist[0]}'
    cp \
        '${projectDir}/tests/fixtures/stubs/brief_refinement_result.json' \
        't12_${finalist[0]}/brief_refinement_result.json'
    cp \
        '${projectDir}/tests/fixtures/stubs/sequence_map_result.json' \
        't12_${finalist[0]}/sequence_map_result.json'
    cp \
        '${projectDir}/tests/fixtures/stubs/t12_command.json' \
        't12_${finalist[0]}/t12_command.json'
    """
}

// Every reviewed Phase III finalist carries its own complete crystal-bound
// diffraction evidence. Deep content hashing makes source, selected dataset,
// Free-R flags, preflight, and licensed-runtime changes visible to resume.
process RUN_PHASE3_BRIEF_REFINEMENT {
    tag "phase3-t12:${item[4]}:${item[0][0]}"
    label 'process_refine'
    cache 'deep'
    errorStrategy { task.exitStatus == 75 ? 'retry' : 'finish' }
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    item: Tuple

    output:
    result: Tuple = tuple(
        item[4],
        item[0][0],
        file("phase3_t12_${item[4]}_${item[0][0]}")
    )

    script:
    def finalist = item[0]
    def outputName = "phase3_t12_${item[4]}_${finalist[0]}"
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        refinement brief \
        --seed-solution-id '${finalist[0]}' \
        --sequence-group-id '${finalist[1]}' \
        --input-copy-count '${finalist[2]}' \
        --parent-coordinate '${finalist[3]}' \
        --parent-coordinate-sha256 '${finalist[4]}' \
        --parent-mtz '${finalist[5]}' \
        --parent-mtz-sha256 '${finalist[6]}' \
        --resolution '${finalist[7]}' \
        --observation-labels '${finalist[8]}' \
        --sequence-groups '${item[1]}' \
        --source-records '${item[2]}' \
        --phenix-manifest '${item[3]}' \
        --crystal-id '${item[4]}' \
        --diffraction-selection '${item[5]}' \
        --source-mtz '${item[6]}' \
        --preflight '${item[7]}' \
        --free-r-identity '${item[8]}' \
        --threads '${task.cpus}' \
        --outdir '${outputName}'
    """

    stub:
    def finalist = item[0]
    def outputName = "phase3_t12_${item[4]}_${finalist[0]}"
    """
    mkdir -p '${outputName}'
    cp \
        '${projectDir}/tests/fixtures/stubs/brief_refinement_result.json' \
        '${outputName}/brief_refinement_result.json'
    cp \
        '${projectDir}/tests/fixtures/stubs/sequence_map_result.json' \
        '${outputName}/sequence_map_result.json'
    cp \
        '${projectDir}/tests/fixtures/stubs/t12_command.json' \
        '${outputName}/t12_command.json'
    cp '${item[5]}' '${outputName}/phase3_diffraction_selection.json'
    cp '${item[8]}' '${outputName}/phase3_free_r_identity.json'
    printf '%s\n' '${item[4]}' > '${outputName}/phase3_crystal_id.txt'
    """
}
