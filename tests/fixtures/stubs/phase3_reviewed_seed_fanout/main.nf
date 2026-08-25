#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include {
    STAGE_PHASE3_APPROVED_MR_SEEDS
} from '../../../../modules/local/stage_phase3_approved_mr_seeds'
include {
    PHASE3_ADDITIONAL_COPY_WORKFLOW
} from '../../../../workflows/additional_copy_workflow'

params {
    review_package: Path
    review_stage: Path
    phase3_package: Path
    hypotheses: Path
    sequence_groups: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path
    diffraction_selection: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    main:
    approved = STAGE_PHASE3_APPROVED_MR_SEEDS(
        channel.value(params.review_package),
        channel.value(params.review_stage),
        channel.value(params.phase3_package),
        channel.value(params.hypotheses)
    )
    reviewed = approved.map { Path bundle ->
        tuple(
            'test_crystal_01',
            bundle,
            params.review_package.resolve('mr_seed_review_manifest.json'),
            params.hypotheses,
            params.sequence_groups,
            params.preflight,
            params.mtz,
            params.phenix_manifest,
            params.diffraction_selection
        )
    }
    PHASE3_ADDITIONAL_COPY_WORKFLOW(reviewed)
}
