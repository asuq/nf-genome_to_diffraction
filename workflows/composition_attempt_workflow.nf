nextflow.enable.types = true

include { STUB_PLANNED_COMPOSITION_ATTEMPT } from '../modules/local/stub_planned_composition_attempt'

// Expand only the selected rows in one Python-validated composition-attempt
// inventory. `combine` forms a Cartesian product with the immutable inventory
// path, so every row carries the complete parent/selection/Free-R/registry
// context. The singleton is never consumed by only the first queue item.
workflow COMPOSITION_ATTEMPT_WORKFLOW {
    take:
    attempt_inventory: Path

    main:
    selected_rows = attempt_inventory.flatMap { Path inventory ->
        def document = new groovy.json.JsonSlurper().parse(inventory.toFile())
        document.attempts.collect { attempt ->
            def parentState = document.parent_states.find { state ->
                state.state_id == attempt.parent_state_id
            }
            def depthCandidate = document.depth_plan.candidates.find { candidate ->
                candidate.depth_candidate_id == attempt.depth_candidate_id
            }
            def parentResolutions = attempt.parent_model_resolution_ids.collect { resolutionId ->
                document.depth_plan.model_resolutions.find { resolution ->
                    resolution.resolution_id == resolutionId
                }
            }
            def candidateResolution = document.depth_plan.model_resolutions.find { resolution ->
                resolution.resolution_id == attempt.candidate_model_resolution_id
            }
            def executionInput = document.execution_inputs.find { input ->
                input.execution_input_id == attempt.component_execution_input_id
            }
            tuple(
                attempt.attempt_id as String,
                attempt,
                executionInput,
                parentState,
                depthCandidate,
                parentResolutions,
                candidateResolution,
                document.diffraction_selection,
                document.free_r_identity,
                document.model_registry_id as String,
                document.execution_identity_id as String
            )
        }
    }
    complete_items = selected_rows.combine(attempt_inventory)
    executed = STUB_PLANNED_COMPOSITION_ATTEMPT(complete_items)

    emit:
    results: Tuple = executed
}
