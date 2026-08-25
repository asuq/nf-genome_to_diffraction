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
        'seed_solution_id\trefinement_id\tcandidate_rank\tsequence_group_id\tsource_record_ids\tsource_loci\toriginal_protein_ids\tlocus_tags\tgene_names\tproducts\tannotation_providers\tsequence_length\traw_score\tscore_z\tcoverage\tsegment_ranges\tfinal_r_work\tfinal_r_free\trms_bonds\trms_angles\trefined_copy_count\tmatthews_rank_at_refined_copy\tmatthews_status_at_refined_copy\tmatthews_coefficient_at_refined_copy\tsolvent_fraction_at_refined_copy\tmatthews_top_copy_counts\trefined_model\trefined_mtz\tmap_2mfo_dfc\tmap_mfo_dfc\tsequence_assignment_hypothesis\twarnings' \
        > t12_sequence_checkpoint/sequence_candidates_top10.tsv
    cp \
        t12_sequence_checkpoint/sequence_candidates_top10.tsv \
        t12_sequence_checkpoint/sequence_candidates_top25.tsv
    cp \
        t12_sequence_checkpoint/sequence_candidates_top10.tsv \
        t12_sequence_checkpoint/sequence_candidates_full.tsv
    printf '%s\n' \
        'sequence_group_id\tbest_candidate_rank\tbest_raw_score\tbest_score_z\tsupporting_finalist_count\tsource_record_ids\tsource_loci\toriginal_protein_ids\tlocus_tags\tgene_names\tproducts\tannotation_providers\trefined_copy_count\tmatthews_rank_at_refined_copy\tmatthews_status_at_refined_copy\tmatthews_coefficient_at_refined_copy\tsolvent_fraction_at_refined_copy\tmatthews_top_copy_counts' \
        > t12_sequence_checkpoint/sequence_approval_candidates.tsv
    printf '%s\n' \
        'sequence_group_id\tsource_record_id\tcatalogue_id\toriginal_protein_id\tlocus_tag\tgene_name\tproduct\tdescription\tcontig\tstart\tend\tstrand\tannotation_provider\tquality_flags' \
        > t12_sequence_checkpoint/sequence_gene_annotations.tsv
    printf '%s\n' \
        'crystal_id\tsequence_group_id\tcopy_count\tsequence_mass_da\tsequence_mass_lower_da\tsequence_mass_upper_da\tmatthews_coefficient\tmatthews_coefficient_lower\tmatthews_coefficient_upper\tsolvent_fraction\tsolvent_fraction_lower\tsolvent_fraction_upper\tmatthews_prior\tphysical_status\trank_within_candidate\tretained\tasu_volume_a3\tspace_group' \
        > t12_sequence_checkpoint/sequence_matthews_context.tsv
    printf '%s\n' \
        'checkpoint\titem_id\tdecision\treviewer\treviewed_at\tcomment\toverride_reason' \
        > t12_sequence_checkpoint/approved_sequence_groups.tsv
    printf '%s\n' \
        '<!doctype html><html><body><h1>T12.5 stub checkpoint</h1></body></html>' \
        > t12_sequence_checkpoint/sequence_candidates.html
    printf '%s\n' \
        '{"schema_version":"1.0","adapter_version":"live-sequence-checkpoint-v2","package_id":"seqreview_stub","run_id":"t12stage_stub","execution_mode":"normal_workflow","finalist_count":1,"retained_finalist_count":1,"reviewable_finalist_count":0,"top10_row_count":0,"top25_row_count":0,"full_scored_row_count":0,"approval_candidate_count":0,"selection_policy":"retain_all_finalists_and_all_scored_sequences","automatic_approval":false,"all_finalists_retained":true,"typed_failures_are_evidence":true,"candidate_outcomes":[{"seed_solution_id":"sol_stub","refinement_execution_status":"failed_tool_execution","sequence_execution_status":"skipped_ineligible","scored_group_count":0,"review_row_count":0,"retained":true}],"identity":{},"outputs":{}}' \
        > t12_sequence_checkpoint/sequence_checkpoint_manifest.json
    """
}


// Keep every reviewed crystal, complete finalist inventory, and full catalogue
// together until its independent file-based sequence checkpoint is published.
process BUILD_PHASE3_CRYSTAL_SEQUENCE_CHECKPOINT {
    tag "phase3-sequence-checkpoint:${item[0]}"
    label 'process_low'
    cache 'deep'
    publishDir params.outdir, mode: 'copy', overwrite: true
    stageInMode 'copy'

    input:
    item: Tuple

    output:
    checkpoint: Tuple = tuple(
        item[0],
        file("phase3_sequence_checkpoint_${item[0]}")
    )

    script:
    def outputName = "phase3_sequence_checkpoint_${item[0]}"
    def resultFlags = (item[2] as List)
        .sort { left, right -> left.name <=> right.name }
        .collect { result -> "--candidate-result '${result}'" }
        .join(' ')
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        review build-live-sequence-checkpoint \
        --crystal-id '${item[0]}' \
        --stage-bundle '${item[1]}' \
        ${resultFlags} \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "phase3_sequence_checkpoint_${item[0]}"
    def finalistCount = (item[2] as List).size()
    """
    mkdir -p '${outputName}/provenance'
    cp '${item[1]}/inputs/sequence_groups.jsonl' \
        '${outputName}/provenance/sequence_groups.jsonl'
    cp '${item[1]}/inputs/source_records.jsonl' \
        '${outputName}/provenance/source_records.jsonl'
    printf '%s\\n' 'seed_solution_id\\tsequence_group_id\\traw_score' \
        > '${outputName}/sequence_candidates_full.tsv'
    cp '${outputName}/sequence_candidates_full.tsv' \
        '${outputName}/sequence_candidates_top10.tsv'
    cp '${outputName}/sequence_candidates_full.tsv' \
        '${outputName}/sequence_candidates_top25.tsv'
    printf '%s\\n' 'checkpoint\\titem_id\\tdecision\\treviewer' \
        > '${outputName}/approved_sequence_groups.tsv'
    printf '%s\\n' \
        '{"schema_version":"1.0","adapter_version":"phase3-sequence-checkpoint-stub","execution_mode":"phase3_reviewed_single_component","crystal_context":{"crystal_id":"${item[0]}"},"finalist_count":${finalistCount},"all_finalists_retained":true,"automatic_approval":false,"typed_failures_are_evidence":true}' \
        > '${outputName}/sequence_checkpoint_manifest.json'
    """
}


// Publish every crystal-owned review target and complete Coot evidence under
// the current single-component scheduler run, never its preceding screen run.
process BUILD_PHASE3_OWNED_SEQUENCE_REVIEW_PACKAGE {
    tag "phase3-owned-sequence-review:${item[0]}"
    label 'process_low'
    cache 'deep'
    publishDir params.outdir, mode: 'copy', overwrite: true
    stageInMode 'copy'

    input:
    item: Tuple

    output:
    owned_review: Tuple = tuple(
        item[0],
        file("phase3_owned_sequence_review_${item[0]}")
    )

    script:
    def outputName = "phase3_owned_sequence_review_${item[0]}"
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        review build-owned-sequence-package \
        --sequence-checkpoint '${item[1]}' \
        --execution-identity '${item[2]}' \
        --owned-parent-run '${item[3]}' \
        --crystal-id '${item[0]}' \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "phase3_owned_sequence_review_${item[0]}"
    """
    python \
        '${projectDir}/tests/scripts/build_phase3_owned_sequence_stub.py' \
        --sequence-checkpoint '${item[1]}' \
        --execution-identity '${item[2]}' \
        --owned-parent-run '${item[3]}' \
        --crystal-id '${item[0]}' \
        --outdir '${outputName}'
    """
}
