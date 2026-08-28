nextflow.enable.types = true

// One selected B--F attempt per complete Nextflow item. The Python adapter
// independently revalidates the full inventory, execution identity, model
// registry, fixed coordinates, sequence groups, MTZ/Free-R membership, and
// Phenix runtime before constructing the 9ECN-qualified multi-fixed command.
process RUN_PHASE3_COMPOSITION_ATTEMPT {
    tag "composition-attempt:${item[0]}"
    label 'process_single'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    item: Tuple
    fixed_coordinate_root: Path
    model_registry: Path
    sequence_groups: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path
    execution_identity: Path

    stage:
    stageAs fixed_coordinate_root, 'fixed_coordinate_root'
    stageAs model_registry, 'model_registry'
    stageAs sequence_groups, 'sequence_groups.jsonl'
    stageAs preflight, 'preflight.jsonl'
    stageAs mtz, 'diffraction.mtz'
    stageAs phenix_manifest, 'phenix_manifest.json'
    stageAs execution_identity, 'phase3_execution_identity.json'

    output:
    result: Tuple = tuple(
        item[0],
        file("composition_attempt_${item[0]}")
    )

    script:
    def outputName = "composition_attempt_${item[0]}"
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        composition run-attempt \
        --attempt-inventory '${item[11]}' \
        --attempt-id '${item[0]}' \
        --fixed-coordinate-root '${fixed_coordinate_root}' \
        --model-registry '${model_registry}' \
        --sequence-groups '${sequence_groups}' \
        --preflight '${preflight}' \
        --mtz '${mtz}' \
        --phenix-manifest '${phenix_manifest}' \
        --execution-identity '${execution_identity}' \
        --threads '${task.cpus}' \
        --outdir '${outputName}'
    """

    stub:
    def attempt = item[1]
    def executionInput = item[2]
    def outputName = "composition_attempt_${item[0]}"
    """
    mkdir -p '${outputName}'
    cp '${item[11]}' '${outputName}/composition_attempt_inventory.json'
    printf '%s\n' \
        '{"schema_version":"2.0","adapter_version":"phase3-composition-attempt-execution-v1","attempt_id":"${attempt.attempt_id}","execution_input_id":"${executionInput.execution_input_id}","component_execution_input_id":"${executionInput.execution_input_id}","allocation_rank":${attempt.allocation_rank},"depth_plan_id":"${attempt.depth_plan_id}","parent_state_id":"${attempt.parent_state_id}","depth_candidate_id":"${attempt.depth_candidate_id}","component_spec_id":"${attempt.component_spec_id}","candidate_model_resolution_id":"${attempt.candidate_model_resolution_id}","diffraction_selection_id":"${attempt.diffraction_selection_id}","free_r_identity_id":"${attempt.free_r_identity_id}","model_registry_id":"${attempt.model_registry_id}","execution_identity_bound_in_inventory":true,"execution_status":"stub_not_executed","scientific_status":"search_evidence_only","exact_identity_claimed":false,"complete_composition_claimed":false}' \
        > '${outputName}/composition_attempt_stub.json'
    """
}
