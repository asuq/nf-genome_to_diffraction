#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include {
    STAGE_PHASE3_APPROVED_MR_SEEDS
} from '../../../../modules/local/stage_phase3_approved_mr_seeds'
include {
    ADDITIONAL_COPY_WORKFLOW
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
    ADDITIONAL_COPY_WORKFLOW(
        approved.map { Path bundle -> bundle.resolve('additional_copy_seeds.tsv') },
        approved.map { Path bundle ->
            bundle.resolve('validated_mr_seed_decisions.json')
        },
        channel.value(params.review_package.resolve('mr_seed_review_manifest.json')),
        channel.value(params.hypotheses),
        channel.value(params.sequence_groups),
        channel.value(params.preflight),
        channel.value(params.mtz),
        channel.value(params.phenix_manifest)
    )
}
