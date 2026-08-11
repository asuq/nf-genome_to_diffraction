#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { REGISTER_PDB_COORDINATES } from './modules/local/register_pdb_coordinates'

params {
    structural_hits: Path
    sequence_groups: Path
    database_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
    maximum_hits_per_sequence_group: Integer = 3
    maximum_mappings: Integer = 25
}

workflow {
    main:
    REGISTER_PDB_COORDINATES(
        params.structural_hits,
        params.sequence_groups,
        params.database_manifest,
        params.maximum_hits_per_sequence_group,
        params.maximum_mappings
    )
}
