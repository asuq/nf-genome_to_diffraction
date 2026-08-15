nextflow.enable.types = true

// Package every typed T12 outcome for the second file-based checkpoint.
// Top-10 and top-25 tables are review views only; the approval file stays empty.
process BUILD_LIVE_SEQUENCE_CHECKPOINT {
    tag 'normal-workflow-t12.5-checkpoint'
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true
    stageInMode 'copy'

    input:
    stage: Path
    candidate_results: List<Path>

    output:
    checkpoint: Path = file('t12_sequence_checkpoint')

    script:
    def resultFlags = candidate_results
        .sort { left, right -> left.name <=> right.name }
        .collect { result -> "--candidate-result '${result}'" }
        .join(' ')
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        review build-live-sequence-checkpoint \
        --stage-bundle '${stage}' \
        ${resultFlags} \
        --outdir t12_sequence_checkpoint
    """

    stub:
    """
    mkdir -p t12_sequence_checkpoint
    printf '%s\n' \
        'seed_solution_id\trefinement_id\tcandidate_rank\tsequence_group_id\tsource_record_ids\tsource_loci\tsequence_length\traw_score\tscore_z\tcoverage\tsegment_ranges\tfinal_r_work\tfinal_r_free\trms_bonds\trms_angles\trefined_model\trefined_mtz\tmap_2mfo_dfc\tsequence_model\twarnings' \
        > t12_sequence_checkpoint/sequence_candidates_top10.tsv
    cp \
        t12_sequence_checkpoint/sequence_candidates_top10.tsv \
        t12_sequence_checkpoint/sequence_candidates_top25.tsv
    cp \
        t12_sequence_checkpoint/sequence_candidates_top10.tsv \
        t12_sequence_checkpoint/sequence_candidates_full.tsv
    printf '%s\n' \
        'sequence_group_id\tbest_candidate_rank\tbest_raw_score\tbest_score_z\tsupporting_finalist_count\tsource_record_ids\tsource_loci' \
        > t12_sequence_checkpoint/sequence_approval_candidates.tsv
    printf '%s\n' \
        'checkpoint\titem_id\tdecision\treviewer\treviewed_at\tcomment\toverride_reason' \
        > t12_sequence_checkpoint/approved_sequence_groups.tsv
    printf '%s\n' \
        '<!doctype html><html><body><h1>T12.5 stub checkpoint</h1></body></html>' \
        > t12_sequence_checkpoint/sequence_candidates.html
    printf '%s\n' \
        '{"schema_version":"1.0","adapter_version":"live-sequence-checkpoint-v1","package_id":"seqreview_stub","run_id":"t12stage_stub","execution_mode":"normal_workflow","finalist_count":1,"retained_finalist_count":1,"reviewable_finalist_count":0,"top10_row_count":0,"top25_row_count":0,"full_scored_row_count":0,"approval_candidate_count":0,"selection_policy":"retain_all_finalists_and_all_scored_sequences","automatic_approval":false,"all_finalists_retained":true,"typed_failures_are_evidence":true,"candidate_outcomes":[{"seed_solution_id":"sol_stub","refinement_execution_status":"failed_tool_execution","sequence_execution_status":"skipped_ineligible","scored_group_count":0,"review_row_count":0,"retained":true}],"identity":{},"outputs":{}}' \
        > t12_sequence_checkpoint/sequence_checkpoint_manifest.json
    """
}
