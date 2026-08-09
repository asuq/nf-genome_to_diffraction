#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { PDB_SEQUENCE_DISCOVERY } from './workflows/pdb_sequence_discovery_workflow'

params {
    sequence_groups: Path
    database_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
    maximum_hits_per_query: Integer = 25
    maximum_evalue: Float = 1.0e-5
    minimum_query_coverage: Float = 0.5
    maximum_query_length: Integer = 10000
}

workflow {
    main:
    PDB_SEQUENCE_DISCOVERY(
        params.sequence_groups,
        params.database_manifest,
        params.maximum_hits_per_query,
        params.maximum_evalue.toFloat(),
        params.minimum_query_coverage.toFloat(),
        params.maximum_query_length
    )
}
