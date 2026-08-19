nextflow.enable.types = true

process RETRIEVE_AFDB_EXACT {
    tag 'catalogue-wide-exact-afdb-retrieval'
    label 'process_network'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    sequence_groups: Path
    source_records: Path
    database_manifest: Path
    provider_plan: Path
    provider_entry: Path
    accession_map: Path?
    request_timeout_seconds: Float
    retry_count: Integer

    output:
    search: Path = file('afdb_exact_search')

    script:
    """
    args=(
        --sequence-groups '${sequence_groups}'
        --source-records '${source_records}'
        --database-manifest '${database_manifest}'
        --provider-plan '${provider_plan}'
        --provider-entry '${provider_entry}'
        --outdir afdb_exact_search
        --request-timeout-seconds '${request_timeout_seconds}'
        --retry-count '${retry_count}'
    )
    [[ -n '${accession_map ?: ''}' ]] && args+=(--accession-map '${accession_map ?: ''}')

    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search afdb-exact \
        "\${args[@]}"
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/afdb_exact_search' afdb_exact_search
    """
}
