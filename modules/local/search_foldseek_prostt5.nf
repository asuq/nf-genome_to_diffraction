nextflow.enable.types = true

process SEARCH_FOLDSEEK_PROSTT5 {
    tag 'catalogue-wide-prostt5-foldseek-pdb-search'
    label 'process_prostt5_search'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    sequence_groups: Path
    database_manifest: Path
    maximum_hits_per_query: Integer
    maximum_evalue: Float
    minimum_query_coverage: Float
    maximum_query_length: Integer
    maximum_queries: Integer
    gpu: Boolean

    output:
    search: Path = file('prostt5_foldseek_search')

    script:
    """
    args=(
        --sequence-groups '${sequence_groups}'
        --database-manifest '${database_manifest}'
        --outdir prostt5_foldseek_search
        --threads '${task.cpus}'
        --maximum-hits-per-query '${maximum_hits_per_query}'
        --maximum-evalue '${maximum_evalue}'
        --minimum-query-coverage '${minimum_query_coverage}'
        --maximum-query-length '${maximum_query_length}'
        --maximum-queries '${maximum_queries}'
    )
    [[ '${gpu}' == 'true' ]] && args+=(--gpu)

    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search prostt5-foldseek \
        "\${args[@]}"
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/prostt5_foldseek_search' prostt5_foldseek_search
    """
}
