nextflow.enable.types = true

process RUN_BRIEF_REFINEMENT {
    tag "t12:${finalist[0]}"
    label 'process_refine'
    errorStrategy 'finish'
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
