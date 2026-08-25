nextflow.enable.types = true

include {
    BUILD_DIVERSE_FIRST_COPY_FUNNEL
} from '../modules/local/build_diverse_first_copy_funnel'
include {
    BUILD_PHASE3_MR_SEED_REVIEW;
    RUN_PHASE3_FIRST_COPY_PHASER
} from '../modules/local/phase3_multicrystal_first_copy_tasks'
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
    maximum_first_copy_jobs: Integer
    phenix_manifest: Path

    main:
    dispatched = CRYSTAL_FANOUT_WORKFLOW(
        crystals,
        preflight,
        catalogue_bundle,
        provider_bundle
    )
    crystal_ids = dispatched.map { crystalId, dispatch, catalogue, provider ->
        crystalId as String
    }
    sequence_groups = catalogue_bundle.map { bundle ->
        bundle.resolve('sequence_groups.jsonl')
    }
    source_records = catalogue_bundle.map { bundle ->
        bundle.resolve('source_records.jsonl')
    }
    funnel_items = BUILD_DIVERSE_FIRST_COPY_FUNNEL(
        predicted_coordinate_sources.first(),
        predicted_prepared_models.first(),
        pdb_coordinate_sources.first(),
        coordinate_hit_mappings.first(),
        experimental_prepared_models.first(),
        sequence_groups.first(),
        matthews.first(),
        preflight.first(),
        pipeline_config.first(),
        crystal_ids,
        maximum_first_copy_jobs,
        true
    )
    complete_funnels = funnel_items
        .join(dispatched, by: 0)
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
                providers[0] as Path
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
            provider
        )
    }
    reviews = BUILD_PHASE3_MR_SEED_REVIEW(active_reviews.mix(empty_reviews))

    emit:
    funnel: Tuple = funnel_items
    results: Tuple = first_copy
    review: Tuple = reviews
}
