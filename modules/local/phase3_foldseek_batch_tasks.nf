nextflow.enable.types = true

// Plan once per complete catalogue. Provider-plan and entry bytes remain task
// inputs so a route/database mutation invalidates the complete batching graph.
process PLAN_PHASE3_FOLDSEEK_BATCHES {
    tag 'phase3-complete-catalogue-foldseek-batches'
    label 'process_low'

    input:
    sequence_groups: Path
    provider_plan: Path
    provider_entry: Path

    output:
    plan: Path = file('phase3_foldseek_batches')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search plan-phase3-foldseek-batches \
        --sequence-groups '${sequence_groups}' \
        --outdir phase3_foldseek_batches
    """

    stub:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search plan-phase3-foldseek-batches \
        --sequence-groups '${sequence_groups}' \
        --outdir phase3_foldseek_batches
    """
}


// Each independent Foldseek database invocation receives at most 128 sorted
// sequence groups. maxForks=1 reserves only one large-memory node at a time.
process SEARCH_PHASE3_FOLDSEEK_BATCH {
    tag "phase3-prostt5-foldseek:${batch[0]}"
    label 'process_prostt5_search'
    maxForks 1

    input:
    batch: Tuple
    database_manifest: Path
    provider_plan: Path
    provider_entry: Path
    maximum_evalue: Float
    minimum_query_coverage: Float
    maximum_query_length: Integer
    gpu: Boolean

    output:
    result: Tuple = tuple(batch[0], file("phase3_foldseek_batch_${batch[0]}"))

    script:
    def outputName = "phase3_foldseek_batch_${batch[0]}"
    """
    mkdir -p '${outputName}'
    cp '${batch[1]}/batch.json' '${outputName}/batch.json'
    args=(
        --sequence-groups '${batch[1]}/sequence_groups.jsonl'
        --database-manifest '${database_manifest}'
        --provider-plan '${provider_plan}'
        --provider-entry '${provider_entry}'
        --outdir '${outputName}/search'
        --threads '${task.cpus}'
        --maximum-evalue '${maximum_evalue}'
        --minimum-query-coverage '${minimum_query_coverage}'
        --maximum-query-length '${maximum_query_length}'
        --maximum-queries '0'
        --retain-unmapped-targets
    )
    [[ '${gpu}' == 'true' ]] && args+=(--gpu)
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search prostt5-foldseek \
        "\${args[@]}"
    """

    stub:
    def outputName = "phase3_foldseek_batch_${batch[0]}"
    """
    mkdir -p '${outputName}'
    cp '${batch[1]}/batch.json' '${outputName}/batch.json'
    python '${moduleDir}/../../tests/scripts/write_phase3_foldseek_batch_stub.py' \
        '${batch[1]}' \
        '${outputName}/search'
    """
}


// Independently verify complete typed query/hit coverage and preserve every
// per-batch raw log/result before exposing the historical provider bundle.
process MERGE_PHASE3_FOLDSEEK_BATCHES {
    tag 'phase3-complete-catalogue-foldseek-results'
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    sequence_groups: Path
    batch_plan: Path
    batches: List<Path>

    output:
    search: Path = file('prostt5_foldseek_search')

    script:
    def batchArguments = batches
        .sort { left, right -> left.name <=> right.name }
        .collect { bundle -> "--batch '${bundle}'" }
        .join(' ')
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search merge-phase3-foldseek-batches \
        --sequence-groups '${sequence_groups}' \
        --batch-plan '${batch_plan}' \
        ${batchArguments} \
        --outdir prostt5_foldseek_search
    """

    stub:
    def batchArguments = batches
        .sort { left, right -> left.name <=> right.name }
        .collect { bundle -> "--batch '${bundle}'" }
        .join(' ')
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search merge-phase3-foldseek-batches \
        --sequence-groups '${sequence_groups}' \
        --batch-plan '${batch_plan}' \
        ${batchArguments} \
        --outdir prostt5_foldseek_search
    """
}
