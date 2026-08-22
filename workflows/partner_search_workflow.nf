nextflow.enable.types = true

include { BUILD_PARTNER_PLAN } from '../modules/local/build_partner_plan'
include { RUN_PLANNED_PARTNER_PHASER } from '../modules/local/run_planned_partner_phaser'
include { SUMMARIZE_PARTNER_ATTEMPTS } from '../modules/local/summarize_partner_attempts'

workflow PARTNER_SEARCH_WORKFLOW {
    take:
    approved_stage: Path
    review_package: Path
    sequence_groups: Path
    matthews: Path
    preflight: Path
    pipeline_config: Path
    model_registry: Path
    crystal_id: String
    partner_copy_count: Integer
    mtz: Path
    phenix_manifest: Path

    main:
    partner_plan = BUILD_PARTNER_PLAN(
        approved_stage,
        sequence_groups,
        matthews,
        preflight,
        pipeline_config,
        model_registry,
        crystal_id,
        partner_copy_count
    )
    selected_candidates = partner_plan
        .map { Path bundle -> bundle.resolve('selected_partner_candidate_ids.txt') }
        .splitText()
        .map { String candidate_id -> candidate_id.trim() }
        .filter { String candidate_id -> !candidate_id.isEmpty() }
    planned_results = RUN_PLANNED_PARTNER_PHASER(
        selected_candidates,
        approved_stage.first(),
        review_package.first(),
        partner_plan.first(),
        sequence_groups.first(),
        model_registry.first(),
        preflight.first(),
        mtz.first(),
        phenix_manifest.first()
    )
    partner_result_list = planned_results
        .collect()
        .map { results -> results as List<Path> }
    attempt_summary = SUMMARIZE_PARTNER_ATTEMPTS(
        partner_plan.first(),
        partner_result_list
    )

    emit:
    plan: Path = partner_plan
    results: Path = planned_results
    summary: Path = attempt_summary
}
