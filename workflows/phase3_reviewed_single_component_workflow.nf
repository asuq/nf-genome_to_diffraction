nextflow.enable.types = true

include {
    STAGE_PHASE3_CRYSTAL_T12
} from '../modules/local/stage_live_t12'
include {
    BUILD_PHASE3_CRYSTAL_SEQUENCE_CHECKPOINT;
    BUILD_PHASE3_OWNED_COMPOSITION_REVIEW_PACKAGE;
    BUILD_PHASE3_OWNED_SEQUENCE_REVIEW_PACKAGE
} from '../modules/local/build_live_sequence_checkpoint'
include {
    PHASE3_REVIEWED_ADDITIONAL_COPY_WORKFLOW
} from './additional_copy_workflow'
include {
    PHASE3_MULTICRYSTAL_BRIEF_REFINEMENT_WORKFLOW
} from './brief_refinement_workflow'


// Complete crystal-owned A reviews, placement results, selected diffraction,
// Free-R identity, catalogue, and runtime stay keyed through final refinement.
workflow PHASE3_REVIEWED_SINGLE_COMPONENT_WORKFLOW {
    take:
    reviewed_crystals: Tuple
    owned_run_registry: Path
    execution_identity: Path
    owned_parent_run_id: String
    owned_sequence_parent_run_id: String

    main:
    if (
        owned_run_registry == null ||
        execution_identity == null ||
        owned_parent_run_id == null ||
        owned_sequence_parent_run_id == null ||
        owned_sequence_parent_run_id == owned_parent_run_id
    ) {
        error 'Owned Phase III final reviews require a distinct single-component run'
    }
    placement_inputs = reviewed_crystals.map { item ->
        tuple(
            item[0],
            item[1],
            item[2],
            item[3],
            item[4],
            item[6],
            item[7],
            item[8],
            file(
                item[9].resolve('phase3_diffraction_selection.json'),
                checkIfExists: true
            )
        )
    }
    placements = PHASE3_REVIEWED_ADDITIONAL_COPY_WORKFLOW(
        placement_inputs,
        owned_run_registry,
        execution_identity,
        owned_parent_run_id
    )
    active_stages = placements.stage.filter { crystalId, stage ->
        def manifest = new groovy.json.JsonSlurper().parse(
            stage.resolve('phase3_seed_stage_manifest.json').toFile()
        )
        (manifest.approved_seed_count as Integer) > 0
    }
    needs_placement = active_stages.filter { crystalId, stage ->
        def manifest = new groovy.json.JsonSlurper().parse(
            stage.resolve('phase3_seed_stage_manifest.json').toFile()
        )
        (manifest.additional_copy_seed_count as Integer) > 0
    }
    already_complete = active_stages
        .filter { crystalId, stage ->
            def manifest = new groovy.json.JsonSlurper().parse(
                stage.resolve('phase3_seed_stage_manifest.json').toFile()
            )
            (manifest.additional_copy_seed_count as Integer) == 0
        }
        .map { crystalId, stage -> tuple(crystalId, stage, [], []) }
    grouped_placements = placements.results.groupTuple(by: 0)
    approved_inputs = needs_placement
        .join(grouped_placements, by: 0, failOnMismatch: true)
        .mix(already_complete)
    staged_inputs = approved_inputs
        .join(reviewed_crystals, by: 0, failOnDuplicate: true, failOnMismatch: false)
        .map {
            crystalId,
            approved,
            seedIds,
            results,
            decision,
            phase3Package,
            hypotheses,
            sequences,
            sources,
            preflight,
            mtz,
            phenix,
            dispatch ->
            tuple(
                crystalId,
                approved,
                results,
                hypotheses,
                sequences,
                sources,
                preflight,
                mtz,
                phenix,
                dispatch
            )
        }
    finalist_stages = STAGE_PHASE3_CRYSTAL_T12(staged_inputs)
    refinements = PHASE3_MULTICRYSTAL_BRIEF_REFINEMENT_WORKFLOW(finalist_stages)
    grouped_refinements = refinements.groupTuple(by: 0)
    checkpoint_inputs = finalist_stages
        .join(grouped_refinements, by: 0, failOnDuplicate: true, failOnMismatch: true)
        .map { crystalId, stage, dispatch, seedIds, results ->
            tuple(crystalId, stage, results)
        }
    checkpoints = BUILD_PHASE3_CRYSTAL_SEQUENCE_CHECKPOINT(checkpoint_inputs)
    final_review_inputs = checkpoints.map { crystalId, checkpoint ->
        tuple(
            crystalId,
            checkpoint,
            execution_identity,
            owned_sequence_parent_run_id
        )
    }
    sequence_review_inputs = final_review_inputs.filter {
        crystalId, checkpoint, identity, parentRun ->
        def manifest = new groovy.json.JsonSlurper().parse(
            checkpoint.resolve('sequence_checkpoint_manifest.json').toFile()
        )
        (manifest.approval_candidate_count as Integer) > 0
    }
    composition_review_inputs = final_review_inputs.filter {
        crystalId, checkpoint, identity, parentRun ->
        def manifest = new groovy.json.JsonSlurper().parse(
            checkpoint.resolve('sequence_checkpoint_manifest.json').toFile()
        )
        (manifest.candidate_outcomes as List).any { outcome ->
            outcome.refinement_execution_status in [
                'completed_success',
                'completed_warning'
            ]
        }
    }
    owned_sequence_reviews = BUILD_PHASE3_OWNED_SEQUENCE_REVIEW_PACKAGE(
        sequence_review_inputs
    )
    owned_composition_reviews = BUILD_PHASE3_OWNED_COMPOSITION_REVIEW_PACKAGE(
        composition_review_inputs
    )

    emit:
    approval_stage: Tuple = placements.stage
    placement: Tuple = placements.results
    finalist_stage: Tuple = finalist_stages
    refinement: Tuple = refinements
    sequence_checkpoint: Tuple = checkpoints
    owned_sequence_review: Tuple = owned_sequence_reviews
    owned_composition_review: Tuple = owned_composition_reviews
}
