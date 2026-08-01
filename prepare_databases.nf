#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { DATABASE_PREP_WORKFLOW } from './workflows/database_prep_workflow'

params {
    database_root: String
    outdir: Path = file('results')
    prepare_pdb_foldseek: Boolean = false
    prepare_pdb_sequences: Boolean = false
    prepare_prostt5: Boolean = false
    initialise_coordinate_cache: Boolean = false
    verify_esm_atlas_connectivity: Boolean = false
    verify_only: Boolean = false
    force_rebuild: Boolean = false
    full_verify: Boolean = false
    storage_limit_bytes: String = '1800000000000'
    minimum_free_bytes: String = '200000000000'
    threads: Integer = 4
}

workflow {
    main:
    DATABASE_PREP_WORKFLOW(
        params.database_root.toString(),
        params.prepare_pdb_foldseek,
        params.prepare_pdb_sequences,
        params.prepare_prostt5,
        params.initialise_coordinate_cache,
        params.verify_esm_atlas_connectivity,
        params.verify_only,
        params.force_rebuild,
        params.full_verify,
        params.storage_limit_bytes,
        params.minimum_free_bytes,
        params.threads,
        file("${projectDir}/tests/fixtures/stubs/database_manifest.json")
    )
}
