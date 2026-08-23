nextflow.enable.types = true

// Stub-only Phase III composition execution boundary. Each input tuple carries
// the immutable attempt ID and row, parent state, selected depth candidate,
// authoritative component execution input, parent/candidate model resolutions,
// diffraction selection, Free-R identity, all-model-registry identity, opaque
// global execution identity, and the complete validated inventory file.
//
// No live Phaser command is defined. A non-stub invocation fails clearly before
// creating scientific output. Under `-stub-run`, the Nextflow task hash (the
// cache key) covers both the selected row and the complete inventory bytes.
process STUB_PLANNED_COMPOSITION_ATTEMPT {
    tag "composition-attempt:${item[0]}"
    label 'process_single'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    item: Tuple

    output:
    result: Tuple = tuple(
        item[0],
        file("composition_attempt_${item[0]}")
    )

    script:
    """
    printf '%s\n' \
        'Live Phase III composition execution is intentionally unavailable.' >&2
    exit 64
    """

    stub:
    def attempt = item[1]
    def executionInput = item[2]
    def outputName = "composition_attempt_${item[0]}"
    """
    mkdir -p '${outputName}'
    cp '${item[11]}' '${outputName}/composition_attempt_inventory.json'
    printf '%s\n' \
        '{"schema_version":"2.0","attempt_id":"${attempt.attempt_id}","allocation_rank":${attempt.allocation_rank},"depth_plan_id":"${attempt.depth_plan_id}","parent_state_id":"${attempt.parent_state_id}","depth_candidate_id":"${attempt.depth_candidate_id}","component_spec_id":"${attempt.component_spec_id}","component_execution_input_id":"${executionInput.execution_input_id}","candidate_model_resolution_id":"${attempt.candidate_model_resolution_id}","diffraction_selection_id":"${attempt.diffraction_selection_id}","free_r_identity_id":"${attempt.free_r_identity_id}","model_registry_id":"${attempt.model_registry_id}","execution_identity_bound_in_inventory":true,"execution_status":"stub_not_executed"}' \
        > '${outputName}/composition_attempt_stub.json'
    """
}
