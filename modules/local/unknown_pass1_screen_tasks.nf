nextflow.enable.types = true

// Stub-only Phase III unknown-pass-1 execution boundaries. Every tuple is
// path-closed: the path-free crystal/task record is accompanied by the exact
// MTZ or model bytes, global execution identity, staged crystallographic
// review, and the same three shared preparations. The full panel inventory is
// retained separately, so an unrelated crystal cannot invalidate this item.
// These processes emit scheduling evidence only and never invoke Phaser or
// make a scientific claim.
process MATERIALISE_UNKNOWN_PASS1_CRYSTAL_ITEM {
    tag "unknown-pass1-crystal:${item[0]}:${item[1]}"
    label 'process_single'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(
        item[0],
        file("unknown_pass1_crystal_${item[0]}")
    )

    script:
    def outputName = "unknown_pass1_crystal_${item[0]}"
    """
    printf '%s\n' 'unknown pass 1 crystal fan-out is stub-only' >&2
    exit 64
    """

    stub:
    def outputName = "unknown_pass1_crystal_${item[0]}"
    """
    mkdir -p '${outputName}'
    cp '${item[2]}' '${outputName}/crystal_item.json'
    cp '${item[3]}' '${outputName}/input.mtz'
    cp '${item[4]}' '${outputName}/phase3_execution_identity.json'
    cp -R '${item[5]}' '${outputName}/crystallographic_review_stage'
    cp -R '${item[6]}' '${outputName}/shared_catalogue'
    cp -R '${item[7]}' '${outputName}/shared_provider'
    cp -R '${item[8]}' '${outputName}/shared_localisation'
    """
}


process STUB_UNKNOWN_PASS1_A_HYPOTHESIS {
    tag "unknown-pass1-a:${item[0]}:${item[1]}"
    label 'process_single'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(
        item[0],
        item[1],
        file("unknown_pass1_a_${item[0]}_${item[1]}")
    )

    script:
    def outputName = "unknown_pass1_a_${item[0]}_${item[1]}"
    """
    printf '%s\n' 'unknown pass 1 A execution is stub-only' >&2
    exit 64
    """

    stub:
    def outputName = "unknown_pass1_a_${item[0]}_${item[1]}"
    """
    mkdir -p '${outputName}'
    cp '${item[2]}' '${outputName}/a_hypothesis_task.json'
    cp '${item[4]}' '${outputName}/crystal_item.json'
    cp '${item[3]}' '${outputName}/model.pdb'
    cp '${item[5]}' '${outputName}/input.mtz'
    cp '${item[6]}' '${outputName}/phase3_execution_identity.json'
    cp -R '${item[7]}' '${outputName}/crystallographic_review_stage'
    cp -R '${item[8]}' '${outputName}/shared_catalogue'
    cp -R '${item[9]}' '${outputName}/shared_provider'
    cp -R '${item[10]}' '${outputName}/shared_localisation'
    printf '%s\n' 'stub_only_no_scientific_result' > '${outputName}/execution_status.txt'
    """
}
