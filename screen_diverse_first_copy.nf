#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { DIVERSE_FIRST_COPY_MR_WORKFLOW } from './workflows/diverse_first_copy_mr_workflow'

params {
    predicted_coordinate_sources: Path
    predicted_prepared_models: Path
    pdb_coordinate_sources: Path
    coordinate_hit_mappings: Path
    experimental_prepared_models: Path
    sequence_groups: Path
    matthews: Path
    preflight: Path
    config: Path
    crystal_id: String
    maximum_first_copy_jobs: Integer = 25
    mtz: Path
    phenix_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    DIVERSE_FIRST_COPY_MR_WORKFLOW(
        params.predicted_coordinate_sources,
        params.predicted_prepared_models,
        params.pdb_coordinate_sources,
        params.coordinate_hit_mappings,
        params.experimental_prepared_models,
        params.sequence_groups,
        params.matthews,
        params.preflight,
        params.config,
        params.crystal_id,
        params.maximum_first_copy_jobs,
        params.mtz,
        params.phenix_manifest
    )
}
