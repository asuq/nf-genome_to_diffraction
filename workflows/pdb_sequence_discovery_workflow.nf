nextflow.enable.types = true

include { SEARCH_PDB_SEQUENCES } from '../modules/local/search_pdb_sequences'

workflow PDB_SEQUENCE_DISCOVERY {
    take:
    sequence_groups: Path
    database_manifest: Path
    maximum_hits_per_query: Integer
    maximum_evalue: Float
    minimum_query_coverage: Float
    maximum_query_length: Integer

    main:
    search_bundle = SEARCH_PDB_SEQUENCES(
        sequence_groups,
        database_manifest,
        maximum_hits_per_query,
        maximum_evalue,
        minimum_query_coverage,
        maximum_query_length
    )

    emit:
    pdb_sequence_search: Path = search_bundle
}
