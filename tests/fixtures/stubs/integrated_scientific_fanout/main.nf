#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { CONTROL_FIRST_COPY_MR_WORKFLOW } from '../../../../workflows/control_first_copy_mr_workflow'
include {
    ADDITIONAL_COPY_WORKFLOW;
    PHASE3_ADDITIONAL_COPY_WORKFLOW
} from '../../../../workflows/additional_copy_workflow'
include {
    BRIEF_REFINEMENT_WORKFLOW;
    PHASE3_BRIEF_REFINEMENT_WORKFLOW
} from '../../../../workflows/brief_refinement_workflow'

params {
    control_bundle: Path
    seeds: Path
    review_validation: Path
    review_package: Path
    hypotheses: Path
    finalists: Path
    phase3_finalists: Path
    phase3_dispatch: Path
    phase3_seed_stage: Path
    sequence_groups: Path
    source_records: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    CONTROL_FIRST_COPY_MR_WORKFLOW(
        channel.of(params.control_bundle),
        channel.of(params.sequence_groups),
        channel.of(params.preflight),
        channel.of(params.mtz),
        channel.of(params.phenix_manifest)
    )
    ADDITIONAL_COPY_WORKFLOW(
        channel.of(params.seeds),
        channel.of(params.review_validation),
        channel.of(params.review_package),
        channel.of(params.hypotheses),
        channel.of(params.sequence_groups),
        channel.of(params.preflight),
        channel.of(params.mtz),
        channel.of(params.phenix_manifest)
    )
    PHASE3_ADDITIONAL_COPY_WORKFLOW(
        channel.of(
            tuple(
                'test_crystal_01',
                params.phase3_seed_stage,
                params.hypotheses,
                params.sequence_groups,
                params.preflight,
                params.mtz,
                params.phenix_manifest,
                params.phase3_dispatch.resolve('phase3_diffraction_selection.json')
            )
        )
    )
    BRIEF_REFINEMENT_WORKFLOW(
        channel.of(params.finalists),
        channel.of(params.sequence_groups),
        channel.of(params.source_records),
        channel.of(params.phenix_manifest)
    )
    PHASE3_BRIEF_REFINEMENT_WORKFLOW(
        channel.of(params.phase3_finalists),
        channel.of(params.sequence_groups),
        channel.of(params.source_records),
        channel.of(params.phenix_manifest),
        channel.of(params.phase3_dispatch),
        channel.of(params.preflight)
    )
}
