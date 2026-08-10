nextflow.enable.types = true

include { SEARCH_PDB_SEQUENCES } from '../modules/local/search_pdb_sequences'
include { SEARCH_FOLDSEEK_PROSTT5 } from '../modules/local/search_foldseek_prostt5'
include { RETRIEVE_AFDB_EXACT } from '../modules/local/retrieve_afdb_exact'

workflow PDB_SEQUENCE_DISCOVERY {
    take:
    sequence_groups: Path
    source_records: Path
    database_manifest: Path
    maximum_hits_per_query: Integer
    maximum_evalue: Float
    minimum_query_coverage: Float
    maximum_query_length: Integer
    prostt5_maximum_hits_per_query: Integer
    prostt5_maximum_evalue: Float
    prostt5_minimum_query_coverage: Float
    prostt5_maximum_query_length: Integer
    prostt5_maximum_queries: Integer
    prostt5_gpu: Boolean
    afdb_accession_map: Path?
    afdb_request_timeout_seconds: Float
    afdb_retry_count: Integer

    main:
    search_bundle = SEARCH_PDB_SEQUENCES(
        sequence_groups,
        database_manifest,
        maximum_hits_per_query,
        maximum_evalue,
        minimum_query_coverage,
        maximum_query_length
    )
    prostt5_bundle = SEARCH_FOLDSEEK_PROSTT5(
        sequence_groups,
        database_manifest,
        prostt5_maximum_hits_per_query,
        prostt5_maximum_evalue,
        prostt5_minimum_query_coverage,
        prostt5_maximum_query_length,
        prostt5_maximum_queries,
        prostt5_gpu
    )
    afdb_bundle = RETRIEVE_AFDB_EXACT(
        sequence_groups,
        source_records,
        database_manifest,
        afdb_accession_map,
        afdb_request_timeout_seconds,
        afdb_retry_count
    )

    emit:
    pdb_sequence_search: Path = search_bundle
    prostt5_foldseek_search: Path = prostt5_bundle
    afdb_exact_search: Path = afdb_bundle
}
