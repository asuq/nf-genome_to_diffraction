nextflow.enable.types = true

// Select the last checksum-authenticated supported copy state for every
// explicitly approved seed. The original diffraction MTZ is staged separately
// for FreeR-preserving refinement; Phaser MTZ files remain provenance only.
process STAGE_LIVE_T12 {
    tag 'normal-workflow-t12-stage'
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true
    stageInMode 'copy'

    input:
    approved_stage: Path
    review_package: Path
    additional_copy_results: List<Path>
    hypotheses: Path
    sequence_groups: Path
    source_records: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path

    output:
    stage: Path = file('live_t12_stage')

    script:
    def resultFlags = additional_copy_results
        .sort { left, right -> left.name <=> right.name }
        .collect { result -> "--additional-copy-result '${result}'" }
        .join(' ')
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        refinement stage-live \
        --approved-stage '${approved_stage}' \
        --review-package '${review_package}' \
        ${resultFlags} \
        --hypotheses '${hypotheses}' \
        --sequence-groups '${sequence_groups}' \
        --source-records '${source_records}' \
        --preflight '${preflight}' \
        --mtz '${mtz}' \
        --phenix-manifest '${phenix_manifest}' \
        --outdir live_t12_stage
    """

    stub:
    def seed = 'sol_cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'
    def group = 'seq_f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e'
    """
    mkdir -p 'live_t12_stage/inputs' 'live_t12_stage/parents/${seed}'
    cp '${sequence_groups}' 'live_t12_stage/inputs/sequence_groups.jsonl'
    cp '${source_records}' 'live_t12_stage/inputs/source_records.jsonl'
    cp '${preflight}' 'live_t12_stage/inputs/preflight.jsonl'
    cp '${phenix_manifest}' 'live_t12_stage/inputs/phenix_manifest.json'
    cp '${mtz}' 'live_t12_stage/inputs/diffraction.mtz'
    cp \
        '${projectDir}/tests/fixtures/stubs/predicted_model_preparation/models/stub.pdb' \
        'live_t12_stage/parents/${seed}/parent.pdb'
    cp '${mtz}' 'live_t12_stage/parents/${seed}/phaser_solution.mtz'
    printf '%s\n' \
        'seed_solution_id\tsequence_group_id\tinput_copy_count\tparent_coordinate\tparent_coordinate_sha256\tparent_mtz\tparent_mtz_sha256\tresolution\tobservation_labels' \
        '${seed}\t${group}\t2\t'"\${PWD}"'/live_t12_stage/parents/${seed}/parent.pdb\t1111111111111111111111111111111111111111111111111111111111111111\t'"\${PWD}"'/live_t12_stage/inputs/diffraction.mtz\t2222222222222222222222222222222222222222222222222222222222222222\t2.0\tI,SIGI' \
        > live_t12_stage/finalists.tsv
    printf '%s\n' \
        'seed_solution_id\texpected_copy_count\tbest_supported_copy_count\tparent_retained\tfailed_addition_proves_absence' \
        '${seed}\t3\t2\ttrue\tfalse' \
        > live_t12_stage/copy_count_report.tsv
    printf '%s\n' '# Stub copy-count report' \
        > live_t12_stage/copy_count_report.md
    printf '%s\n' \
        '{"schema_version":"1.0","stage_id":"t12stage_stub","profile":"normal_workflow","selection_policy":"retain_all_best_checksum_authenticated_copy_states","seed_count":1,"all_approved_seeds_retained":true,"numeric_score_filter_applied":false,"failed_addition_proves_absence":false,"execution_status":"completed_success"}' \
        > live_t12_stage/t12_stage_manifest.json
    """
}


// Preserve each reviewed crystal and its complete placement inventory in one
// independent T12 preparation; existing v1 single-crystal publication remains.
process STAGE_PHASE3_CRYSTAL_T12 {
    tag "phase3-t12-stage:${item[0]}"
    label 'process_low'
    cache 'deep'
    publishDir params.outdir, mode: 'copy', overwrite: true
    stageInMode 'copy'

    input:
    item: Tuple

    output:
    stage: Tuple = tuple(
        item[0],
        file("phase3_live_t12_${item[0]}"),
        item[10]
    )

    script:
    def outputName = "phase3_live_t12_${item[0]}"
    def resultFlags = (item[3] as List<Path>)
        .sort { left, right -> left.name <=> right.name }
        .collect { result -> "--additional-copy-result '${result}'" }
        .join(' ')
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        refinement stage-live \
        --approved-stage '${item[1]}' \
        --review-package '${item[2]}' \
        ${resultFlags} \
        --hypotheses '${item[4]}' \
        --sequence-groups '${item[5]}' \
        --source-records '${item[6]}' \
        --preflight '${item[7]}' \
        --mtz '${item[8]}' \
        --phenix-manifest '${item[9]}' \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "phase3_live_t12_${item[0]}"
    def approved = new groovy.json.JsonSlurper().parse(
        item[1].resolve('live_m4_stage_manifest.json').toFile()
    )
    def group = 'seq_f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e'
    def copies = (approved.approved_solution_ids as List).collect { seed ->
        """
        mkdir -p '${outputName}/parents/${seed}'
        cp \
            '${projectDir}/tests/fixtures/stubs/predicted_model_preparation/models/stub.pdb' \
            '${outputName}/parents/${seed}/parent.pdb'
        printf '%s\n' \
            '${seed}\t${group}\t2\t'"\${PWD}"'/${outputName}/parents/${seed}/parent.pdb\t1111111111111111111111111111111111111111111111111111111111111111\t'"\${PWD}"'/${outputName}/inputs/diffraction.mtz\t2222222222222222222222222222222222222222222222222222222222222222\t2.0\tI,SIGI' \
            >> '${outputName}/finalists.tsv'
        """
    }.join('\n')
    """
    mkdir -p '${outputName}/inputs'
    cp '${item[5]}' '${outputName}/inputs/sequence_groups.jsonl'
    cp '${item[6]}' '${outputName}/inputs/source_records.jsonl'
    cp '${item[7]}' '${outputName}/inputs/preflight.jsonl'
    cp '${item[9]}' '${outputName}/inputs/phenix_manifest.json'
    cp '${item[8]}' '${outputName}/inputs/diffraction.mtz'
    printf '%s\n' \
        'seed_solution_id\tsequence_group_id\tinput_copy_count\tparent_coordinate\tparent_coordinate_sha256\tparent_mtz\tparent_mtz_sha256\tresolution\tobservation_labels' \
        > '${outputName}/finalists.tsv'
    ${copies}
    printf '%s\n' \
        '{"schema_version":"1.0","seed_count":${approved.approved_solution_ids.size()},"execution_status":"completed_success"}' \
        > '${outputName}/t12_stage_manifest.json'
    """
}
