nextflow.enable.types = true

include {
    BUILD_PHASE3_DIVERSE_FIRST_COPY_FUNNEL
} from '../modules/local/build_phase3_diverse_first_copy_funnel'
include {
    BUILD_PHASE3_OWNED_A_REVIEW_PACKAGE;
    BUILD_PHASE3_MR_SEED_REVIEW;
    RETAIN_PHASE3_CRYSTALLOGRAPHIC_HOLD;
    RUN_PHASE3_FIRST_COPY_PHASER;
    VALIDATE_PHASE3_CRYSTALLOGRAPHIC_REVIEWS
} from '../modules/local/phase3_multicrystal_first_copy_tasks'
include {
    PLAN_PHASE3_LOCALISATION_REOPEN
} from '../modules/local/plan_phase3_localisation_reopen'
include { CRYSTAL_FANOUT_WORKFLOW } from './crystal_fanout_workflow'

// Phase III runs one manifest-owned branch per crystal while retaining one
// catalogue/provider preparation. Complete immutable items carry their exact
// MTZ/model/review inputs; groupKey prevents one crystal from consuming or
// invalidating its siblings. The historical single-crystal path is untouched.
workflow PHASE3_MULTICRYSTAL_FIRST_COPY_WORKFLOW {
    take:
    crystals: Path
    preflight: Path
    catalogue_bundle: Path
    provider_bundle: Path
    predicted_coordinate_sources: Path
    predicted_prepared_models: Path
    pdb_coordinate_sources: Path
    coordinate_hit_mappings: Path
    experimental_prepared_models: Path
    matthews: Path
    pipeline_config: Path
    localisation_bundle: Path
    maximum_first_copy_jobs: Integer
    phenix_manifest: Path
    crystallographic_review_stage: Path?
    execution_identity: Path?
    owned_parent_run_id: String?

    main:
    dispatched = CRYSTAL_FANOUT_WORKFLOW(
        crystals,
        preflight,
        catalogue_bundle,
        provider_bundle
    )
    if (crystallographic_review_stage != null) {
        if (execution_identity == null) {
            error 'Phase III crystallographic reviews lack their execution identity'
        }
        review_bundle = VALIDATE_PHASE3_CRYSTALLOGRAPHIC_REVIEWS(
            crystallographic_review_stage,
            execution_identity,
            crystals.first()
        )
        review_routes = review_bundle.flatMap { root ->
            root.list().sort().collect { String name ->
                Path stage = root.resolve(name)
                def route = new groovy.json.JsonSlurper().parse(
                    stage.resolve('crystallographic_review_routing.json').toFile()
                )
                tuple(route.crystal_id as String, route.decision as String, stage)
            }
        }
        reviewed_dispatch = dispatched.join(review_routes, by: 0)
        held = reviewed_dispatch
            .filter { crystalId, dispatch, catalogue, provider, decision, stage ->
                decision == 'hold'
            }
            .map { crystalId, dispatch, catalogue, provider, decision, stage ->
                tuple(crystalId, stage)
            }
        holds = RETAIN_PHASE3_CRYSTALLOGRAPHIC_HOLD(held)
        active_dispatch = reviewed_dispatch
            .filter { crystalId, dispatch, catalogue, provider, decision, stage ->
                decision == 'proceed'
            }
            .map { crystalId, dispatch, catalogue, provider, decision, stage ->
                tuple(crystalId, dispatch, catalogue, provider, stage)
            }
    } else {
        if (owned_parent_run_id != null) {
            error 'Owned Phase III A packages require reviewed crystallographic stages'
        }
        if (execution_identity != null) {
            error 'Phase III execution identity lacks reviewed crystallographic stages'
        }
        active_dispatch = dispatched.map {
            crystalId, dispatch, catalogue, provider ->
            tuple(crystalId, dispatch, catalogue, provider, dispatch)
        }
        holds = channel.empty()
    }
    crystal_ids = active_dispatch.map {
        crystalId, dispatch, catalogue, provider, reviewStage -> crystalId as String
    }
    sequence_groups = catalogue_bundle.map { bundle ->
        bundle.resolve('sequence_groups.jsonl')
    }
    source_records = catalogue_bundle.map { bundle ->
        bundle.resolve('source_records.jsonl')
    }
    funnel_items = BUILD_PHASE3_DIVERSE_FIRST_COPY_FUNNEL(
        predicted_coordinate_sources.first(),
        predicted_prepared_models.first(),
        pdb_coordinate_sources.first(),
        coordinate_hit_mappings.first(),
        experimental_prepared_models.first(),
        sequence_groups.first(),
        source_records.first(),
        matthews.first(),
        preflight.first(),
        pipeline_config.first(),
        localisation_bundle.first(),
        crystal_ids,
        maximum_first_copy_jobs
    )
    complete_funnels = funnel_items
        .join(active_dispatch, by: 0)
        .combine(sequence_groups.first())
        .combine(source_records.first())
        .combine(matthews.first())
        .combine(preflight.first())
        .combine(pipeline_config.first())
        .combine(phenix_manifest.first())
        .map {
            crystal,
            sequences,
            sources,
            matthewsRecords,
            preflightRecords,
            config,
            phenix ->
            String crystalId = crystal[0] as String
            Path funnel = crystal[1] as Path
            Path dispatch = crystal[2] as Path
            Path catalogue = crystal[3] as Path
            Path provider = crystal[4] as Path
            Path reviewStage = crystal[5] as Path
            Path hypotheses = funnel.resolve('hypotheses')
            def records = hypotheses.list().sort().collect { String name ->
                hypotheses.resolve(name)
            }
            tuple(
                crystalId,
                funnel,
                dispatch,
                catalogue,
                provider,
                sequences,
                sources,
                matthewsRecords,
                preflightRecords,
                config,
                phenix,
                reviewStage,
                records
            )
        }
    runnable = complete_funnels.filter {
        crystalId,
        funnel,
        dispatch,
        catalogue,
        provider,
        sequences,
        sources,
        matthewsRecords,
        preflightRecords,
        config,
        phenix,
        reviewStage,
        records -> !records.isEmpty()
    }
    empty = complete_funnels.filter {
        crystalId,
        funnel,
        dispatch,
        catalogue,
        provider,
        sequences,
        sources,
        matthewsRecords,
        preflightRecords,
        config,
        phenix,
        reviewStage,
        records -> records.isEmpty()
    }
    hypotheses = runnable.flatMap {
        crystalId,
        funnel,
        dispatch,
        catalogue,
        provider,
        sequences,
        sources,
        matthewsRecords,
        preflightRecords,
        config,
        phenix,
        reviewStage,
        records ->
        if (records.size() > maximum_first_copy_jobs) {
            error "Phase III A-search cap changed for ${crystalId}"
        }
        records.collect { Path hypothesis ->
            tuple(
                groupKey(crystalId, records.size()),
                crystalId,
                funnel,
                dispatch,
                catalogue,
                provider,
                sequences,
                sources,
                matthewsRecords,
                preflightRecords,
                config,
                phenix,
                reviewStage,
                hypothesis
            )
        }
    }
    first_copy = RUN_PHASE3_FIRST_COPY_PHASER(hypotheses)
    active_reviews = first_copy
        .groupTuple()
        .map {
            key,
            crystalIds,
            funnels,
            dispatches,
            catalogues,
            providers,
            sequenceRecords,
            sourceRecords,
            matthewsRecords,
            preflightRecords,
            configs,
            phenixManifests,
            reviewStages,
            results ->
            def orderedResults = (results as List<Path>).sort { left, right ->
                left.name <=> right.name
            }
            tuple(
                key.groupTarget as String,
                funnels[0] as Path,
                orderedResults,
                sequenceRecords[0] as Path,
                sourceRecords[0] as Path,
                matthewsRecords[0] as Path,
                configs[0] as Path,
                dispatches[0] as Path,
                catalogues[0] as Path,
                providers[0] as Path,
                reviewStages[0] as Path
            )
        }
    empty_reviews = empty.map {
        crystalId,
        funnel,
        dispatch,
        catalogue,
        provider,
        sequences,
        sources,
        matthewsRecords,
        preflightRecords,
        config,
        phenix,
        reviewStage,
        records ->
        tuple(
            crystalId,
            funnel,
            [],
            sequences,
            sources,
            matthewsRecords,
            config,
            dispatch,
            catalogue,
            provider,
            reviewStage
        )
    }
    reviews = BUILD_PHASE3_MR_SEED_REVIEW(active_reviews.mix(empty_reviews))
    reopen_inputs = active_reviews
        .mix(empty_reviews)
        .map {
            crystalId,
            funnel,
            results,
            sequences,
            sources,
            matthewsRecords,
            config,
            dispatch,
            catalogue,
            provider,
            reviewStage -> tuple(crystalId, funnel, results)
        }
    reopen = PLAN_PHASE3_LOCALISATION_REOPEN(
        reopen_inputs,
        localisation_bundle.first()
    )
    if (owned_parent_run_id != null) {
        owned_inputs = reviews
            .join(funnel_items, by: 0)
            .map { crystalId, review, funnel ->
                tuple(
                    crystalId,
                    review,
                    funnel.resolve('mr_hypotheses.jsonl'),
                    execution_identity,
                    owned_parent_run_id
                )
            }
        owned_reviews = BUILD_PHASE3_OWNED_A_REVIEW_PACKAGE(owned_inputs)
    } else {
        owned_reviews = channel.empty()
    }

    emit:
    funnel: Tuple = funnel_items
    results: Tuple = first_copy
    review: Tuple = reviews
    owned_review: Tuple = owned_reviews
    localisation_reopen: Tuple = reopen
    hold: Tuple = holds
}
