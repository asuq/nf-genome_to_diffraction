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
    review_stage: Path
    phase3_package: Path
    hypotheses: Path
    owned_run_registry: Path
    execution_identity: Path
    owned_parent_run_id: String
    crystal_id: String
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
        channel.value(params.review_stage),
        channel.value(params.phase3_package),
        channel.value(params.hypotheses),
        channel.value(params.owned_run_registry),
        channel.value(params.execution_identity),
        channel.value(params.owned_parent_run_id)
    )
    reviewed = approved.map { Path bundle ->
        tuple(
            params.crystal_id,
            bundle,
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
