#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { DATABASE_PREP_WORKFLOW } from './workflows/database_prep_workflow'

params {
    database_root: Path
    outdir: Path = file('results')
    prepare_pdb_foldseek: Boolean = false
    prepare_pdb_sequences: Boolean = false
    prepare_prostt5: Boolean = false
    initialise_coordinate_cache: Boolean = false
    verify_only: Boolean = false
}

workflow {
    main:
    DATABASE_PREP_WORKFLOW(
        params.database_root.toString(),
        params.prepare_pdb_foldseek,
        params.prepare_pdb_sequences,
        params.prepare_prostt5,
        params.initialise_coordinate_cache,
        params.verify_only,
        file("${projectDir}/tests/fixtures/stubs/database_manifest.json")
    )
}
