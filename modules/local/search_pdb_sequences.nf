nextflow.enable.types = true

process SEARCH_PDB_SEQUENCES {
    tag 'catalogue-wide-pdb-sequence-search'
    label 'process_search'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    sequence_groups: Path
    database_manifest: Path
    maximum_hits_per_query: Integer
    maximum_evalue: Float
    minimum_query_coverage: Float
    maximum_query_length: Integer

    output:
    search: Path = file('pdb_sequence_search')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search pdb-sequence \
        --sequence-groups '${sequence_groups}' \
        --database-manifest '${database_manifest}' \
        --outdir pdb_sequence_search \
        --threads ${task.cpus} \
        --maximum-hits-per-query ${maximum_hits_per_query} \
        --maximum-evalue ${maximum_evalue} \
        --minimum-query-coverage ${minimum_query_coverage} \
        --maximum-query-length ${maximum_query_length}
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/structure_search' pdb_sequence_search
    """
}
