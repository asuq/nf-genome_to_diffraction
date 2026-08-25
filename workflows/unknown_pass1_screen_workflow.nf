nextflow.enable.types = true

include {
    MATERIALISE_UNKNOWN_PASS1_CRYSTAL_ITEM;
    STUB_UNKNOWN_PASS1_A_HYPOTHESIS
} from '../modules/local/unknown_pass1_screen_tasks'

// Fixed pass-1 stub fan-out. The inventory has already revalidated the global
// execution identity, exact MTZ/model bytes, one staged crystallographic
// proceed|hold decision per crystal, shared preparation checksums, three-item
// coverage, and the 25-A cap. Each item carries only its own complete record;
// the independently retained panel inventory is not a child-task cache input.
workflow UNKNOWN_PASS1_SCREEN_WORKFLOW {
    take:
    execution_identity: Path
    crystallographic_review_stages: Channel<Tuple>
    shared_catalogue: Path
    shared_provider: Path
    shared_localisation: Path
    crystal_record_items: Channel<Tuple>
    hypothesis_record_items: Channel<Tuple>
    mtz_items: Channel<Tuple>
    model_items: Channel<Tuple>

    main:
    crystal_bundles = crystal_record_items
        .join(mtz_items, by: 0)
        .join(crystallographic_review_stages, by: 0)
    crystal_inputs = crystal_bundles
        .combine(execution_identity)
        .combine(shared_catalogue)
        .combine(shared_provider)
        .combine(shared_localisation)
        .map {
            crystal,
            executionIdentity,
            catalogue,
            provider,
            localisation ->
            tuple(
                crystal[0],
                crystal[1],
                crystal[2],
                crystal[3],
                executionIdentity,
                crystal[4],
                catalogue,
                provider,
                localisation
            )
        }
    crystal_results = MATERIALISE_UNKNOWN_PASS1_CRYSTAL_ITEM(crystal_inputs)

    hypotheses_with_models = hypothesis_record_items
        .combine(model_items, by: 0)
        .map { modelId, crystalId, allocationRank, task, model ->
            tuple(crystalId, allocationRank, task, model)
        }
    hypothesis_inputs = hypotheses_with_models
        .combine(crystal_inputs, by: 0)
        .map {
            crystalId,
            allocationRank,
            task,
            model,
            branch,
            crystalRecord,
            mtz,
            executionIdentity,
            reviewStage,
            catalogue,
            provider,
            localisation ->
            tuple(
                crystalId,
                allocationRank,
                task,
                model,
                crystalRecord,
                mtz,
                executionIdentity,
                reviewStage,
                catalogue,
                provider,
                localisation
            )
        }
    hypothesis_results = STUB_UNKNOWN_PASS1_A_HYPOTHESIS(hypothesis_inputs)

    emit:
    crystal_items: Tuple = crystal_results
    hypothesis_tasks: Tuple = hypothesis_results
}
