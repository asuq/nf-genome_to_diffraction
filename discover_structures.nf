#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { PDB_SEQUENCE_DISCOVERY } from './workflows/pdb_sequence_discovery_workflow'

params {
    sequence_groups: Path
    source_records: Path
    config: Path
    database_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
    maximum_evalue: Float = 1.0e-5
    minimum_query_coverage: Float = 0.5
    maximum_query_length: Integer = 10000
    prostt5_maximum_evalue: Float = 1.0e-3
    prostt5_minimum_query_coverage: Float = 0.5
    prostt5_maximum_query_length: Integer = 10000
    prostt5_maximum_queries: Integer = 0
    prostt5_gpu: Boolean = false
    afdb_accession_map: Path? = null
    afdb_request_timeout_seconds: Float = 60.0
    afdb_retry_count: Integer = 3
}

workflow {
    main:
    PDB_SEQUENCE_DISCOVERY(
        params.sequence_groups,
        params.source_records,
        params.config,
        params.database_manifest,
        params.maximum_evalue.toFloat(),
        params.minimum_query_coverage.toFloat(),
        params.maximum_query_length,
        params.prostt5_maximum_evalue.toFloat(),
        params.prostt5_minimum_query_coverage.toFloat(),
        params.prostt5_maximum_query_length,
        params.prostt5_maximum_queries,
        params.prostt5_gpu,
        params.afdb_accession_map,
        params.afdb_request_timeout_seconds.toFloat(),
        params.afdb_retry_count,
        false
    )
}
