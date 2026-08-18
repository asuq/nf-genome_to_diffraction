nextflow.enable.types = true

include {
    M6_PLAN_TRACK;
    M6_BUILD_SEARCH_BATCHES;
    M6_PARTITION_DISCOVERY;
    M6_PREFLIGHT_CASE;
    M6_APPLY_POLICY;
    M6_PREPARE_ACTIVE_CASE;
    M6_PREPARE_EARLY_CASE;
    M6_FIRST_COPY;
    M6_SELECT_SEEDS;
    M6_EMPTY_SEEDS;
    M6_ADDITIONAL_COPY;
    M6_SELECT_FINALISTS;
    M6_EMPTY_FINALISTS;
    M6_REFINEMENT;
    M6_ASSEMBLE_CASE;
    M6_ASSEMBLE_EMPTY_CASE;
    M6_AGGREGATE_TRACK
} from '../modules/local/m6_nextflow_tasks'

include {
    M6_IMPORT_CATALOGUE;
    M6_SEARCH_PDB;
    M6_SEARCH_FOLDSEEK
} from '../modules/local/m6_truthless_cache_tasks'

workflow M6_VALIDATION_WORKFLOW {
    take:
    runner_root: Path
    protocol: Path
    execution_policy: Path
    software_lock: Path
    database_manifest: Path
    phenix_manifest: Path
    track: String

    main:
    plan = M6_PLAN_TRACK(runner_root, database_manifest, software_lock, track)

    catalogue_tasks = plan.flatMap { Path bundle ->
        bundle.resolve('catalogue_tasks.tsv').toFile().readLines().drop(1)
            .findAll { String line -> line.trim() }
            .collect { String line ->
                def fields = line.split('\t', -1)
                def taskRoot = bundle.resolve(fields[2])
                tuple(
                    fields[0] as String,
                    fields[1] as String,
                    file(taskRoot.resolve('task.json'), checkIfExists: true),
                    file(taskRoot.resolve('catalogue.faa'), checkIfExists: true),
                    file(taskRoot.resolve('analysis_config.json'), checkIfExists: true),
                    software_lock
                )
            }
    }
    case_tasks = plan.flatMap { Path bundle ->
        bundle.resolve('case_tasks.tsv').toFile().readLines().drop(1)
            .findAll { String line -> line.trim() }
            .collect { String line ->
                def fields = line.split('\t', -1)
                tuple(
                    fields[0] as String,
                    fields[1] as String,
                    file(bundle.resolve(fields[2]), checkIfExists: true)
                )
            }
    }

    imported = M6_IMPORT_CATALOGUE(catalogue_tasks)
    imported_bundles = imported
        .map { catalogueKey, bundle -> bundle }
        .collect()
    // Track salts batch-plan construction so only the three approved
    // content-addressed import/search processes can reuse cross-track work.
    batch_input = imported_bundles.map { bundles ->
        tuple(bundles, database_manifest, execution_policy, software_lock, track)
    }
    batch_plan = M6_BUILD_SEARCH_BATCHES(batch_input)
    batch_plan_value = batch_plan.first()
    pdb_batch_tasks = batch_plan_value.flatMap { Path bundle ->
        bundle.resolve('pdb_sequence_batches.tsv').toFile().readLines().drop(1)
            .findAll { String line -> line.trim() }
            .collect { String line ->
                def fields = line.split('\t', -1)
                def taskRoot = bundle.resolve(fields[2])
                tuple(
                    fields[0] as String,
                    fields[1] as String,
                    file(taskRoot.resolve('task.json'), checkIfExists: true),
                    file(taskRoot.resolve('sequence_groups.jsonl'), checkIfExists: true),
                    database_manifest,
                    execution_policy,
                    software_lock
                )
            }
    }
    foldseek_batch_tasks = batch_plan_value.flatMap { Path bundle ->
        bundle.resolve('prostt5_foldseek_batches.tsv').toFile().readLines().drop(1)
            .findAll { String line -> line.trim() }
            .collect { String line ->
                def fields = line.split('\t', -1)
                def taskRoot = bundle.resolve(fields[2])
                tuple(
                    fields[0] as String,
                    fields[1] as String,
                    file(taskRoot.resolve('task.json'), checkIfExists: true),
                    file(taskRoot.resolve('sequence_groups.jsonl'), checkIfExists: true),
                    database_manifest,
                    execution_policy,
                    software_lock
                )
            }
    }
    pdb = M6_SEARCH_PDB(pdb_batch_tasks)
    foldseek = M6_SEARCH_FOLDSEEK(foldseek_batch_tasks)
    pdb_bundles_value = pdb
        .map { batchId, bundle -> bundle }
        .collect()
        .map { values -> values as List<Path> }
    foldseek_bundles_value = foldseek
        .map { batchId, bundle -> bundle }
        .collect()
        .map { values -> values as List<Path> }
    discovery = M6_PARTITION_DISCOVERY(
        imported,
        batch_plan_value,
        pdb_bundles_value,
        foldseek_bundles_value
    )

    preflight_inputs = case_tasks.map { caseId, catalogueKey, task ->
        tuple(caseId, catalogueKey, task, phenix_manifest)
    }
    preflight = M6_PREFLIGHT_CASE(preflight_inputs)
    preflight_active = preflight.filter { caseId, catalogueKey, task, bundle ->
            def record = new groovy.json.JsonSlurper().parseText(
                bundle.resolve('bundle_manifest.json').toFile().text
            )
            record.early_outcome == null
    }
    preflight_early = preflight.filter { caseId, catalogueKey, task, bundle ->
            def record = new groovy.json.JsonSlurper().parseText(
                bundle.resolve('bundle_manifest.json').toFile().text
            )
            record.early_outcome != null
    }

    active_joined = preflight_active
        .map { caseId, catalogueKey, task, preflightBundle ->
            tuple(catalogueKey, caseId, task, preflightBundle)
        }
        .join(discovery, by: 0)
    policy_inputs = active_joined.map {
        catalogueKey, caseId, task, preflightBundle, catalogueBundle, pdbBundle, foldseekBundle ->
        tuple(
            caseId,
            task,
            catalogueBundle,
            pdbBundle,
            foldseekBundle,
            protocol,
            database_manifest,
            preflightBundle
        )
    }
    policies = M6_APPLY_POLICY(policy_inputs)
    active_case_inputs = policies.map {
        caseId, task, catalogueBundle, preflightBundle, policyBundle ->
        tuple(
            caseId,
            task,
            catalogueBundle,
            preflightBundle,
            policyBundle,
            database_manifest
        )
    }
    active_cases = M6_PREPARE_ACTIVE_CASE(active_case_inputs)

    early_joined = preflight_early
        .map { caseId, catalogueKey, task, preflightBundle ->
            tuple(catalogueKey, caseId, task, preflightBundle)
        }
        .join(imported, by: 0)
    early_case_inputs = early_joined.map {
        catalogueKey, caseId, task, preflightBundle, catalogueBundle ->
        tuple(caseId, task, catalogueBundle, preflightBundle, database_manifest)
    }
    early_cases = M6_PREPARE_EARLY_CASE(early_case_inputs)
    cases = active_cases.mix(early_cases)

    planned_cases = cases.map { caseId, bundle ->
        def record = new groovy.json.JsonSlurper().parseText(
            bundle.resolve('case_plan.json').toFile().text
        )
        tuple(caseId, bundle, record.hypothesis_count as Integer)
    }
    runnable_cases = planned_cases.filter { caseId, bundle, count -> count > 0 }
    empty_cases = planned_cases.filter { caseId, bundle, count -> count == 0 }
    hypothesis_tasks = runnable_cases.flatMap { caseId, bundle, count ->
        def planRecord = new groovy.json.JsonSlurper().parseText(
            bundle.resolve('case_plan.json').toFile().text
        )
        def hypothesisIds = planRecord.hypothesis_ids as List
        if (hypothesisIds.size() != count) {
            error "M6 hypothesis-group count changed for ${caseId}"
        }
        Path records = bundle.resolve('first-copy-funnel/hypotheses')
        hypothesisIds.collect { Object rawId ->
            String hypothesisId = rawId as String
            tuple(
                groupKey(caseId, count),
                caseId,
                bundle,
                records.resolve("${hypothesisId}.jsonl"),
                phenix_manifest
            )
        }
    }
    first_copy = M6_FIRST_COPY(hypothesis_tasks)
    grouped_first = first_copy
        .groupTuple()
        .map { key, caseIds, bundles, results ->
            tuple(key.groupTarget as String, bundles[0] as Path, results as List<Path>)
        }
    selected_seeds = M6_SELECT_SEEDS(grouped_first)
    empty_seed_inputs = empty_cases.map { caseId, bundle, count ->
        tuple(caseId, bundle)
    }
    empty_seeds = M6_EMPTY_SEEDS(empty_seed_inputs)
    seeds = selected_seeds.mix(empty_seeds)

    planned_seeds = seeds.map { caseId, caseBundle, seedBundle ->
        def record = new groovy.json.JsonSlurper().parseText(
            seedBundle.resolve('seed_plan.json').toFile().text
        )
        tuple(caseId, caseBundle, seedBundle, record.selected_seed_count as Integer)
    }
    runnable_seeds = planned_seeds.filter {
        caseId, caseBundle, seedBundle, count -> count > 0
    }
    empty_seed_plans = planned_seeds.filter {
        caseId, caseBundle, seedBundle, count -> count == 0
    }
    copy_tasks = runnable_seeds.flatMap {
        caseId, caseBundle, seedBundle, count ->
        def rows = seedBundle.resolve('seed_tasks.jsonl').toFile().readLines()
            .findAll { String line -> line.trim() }
        if (rows.size() != count) {
            error "M6 seed-group count changed for ${caseId}"
        }
        rows.collect { String line ->
                def row = new groovy.json.JsonSlurper().parseText(line)
                tuple(
                    groupKey(caseId, count),
                    caseId,
                    row.seed_solution_id as String,
                    caseBundle,
                    seedBundle,
                    phenix_manifest
                )
            }
    }
    copy_results = M6_ADDITIONAL_COPY(copy_tasks)
    grouped_copy = copy_results
        .groupTuple()
        .map { key, caseIds, caseBundles, seedBundles, results ->
            tuple(
                key.groupTarget as String,
                caseBundles[0] as Path,
                seedBundles[0] as Path,
                results as List<Path>
            )
        }
    finalists = M6_SELECT_FINALISTS(grouped_copy)
    empty_finalist_inputs = empty_seed_plans.map {
        caseId, caseBundle, seedBundle, count -> tuple(caseId, caseBundle, seedBundle)
    }
    empty_finalists = M6_EMPTY_FINALISTS(empty_finalist_inputs)
    finalist_bundles = finalists.mix(empty_finalists)

    planned_finalists = finalist_bundles.map { caseId, caseBundle, finalistBundle ->
        def record = new groovy.json.JsonSlurper().parseText(
            finalistBundle.resolve('finalist_plan.json').toFile().text
        )
        tuple(caseId, caseBundle, finalistBundle, record.finalist_count as Integer)
    }
    runnable_finalists = planned_finalists.filter {
        caseId, caseBundle, finalistBundle, count -> count > 0
    }
    empty_finalist_plans = planned_finalists.filter {
        caseId, caseBundle, finalistBundle, count -> count == 0
    }
    refinement_tasks = runnable_finalists.flatMap {
        caseId, caseBundle, finalistBundle, count ->
        def rows = finalistBundle.resolve('finalist_tasks.jsonl').toFile().readLines()
            .findAll { String line -> line.trim() }
        if (rows.size() != count) {
            error "M6 finalist-group count changed for ${caseId}"
        }
        rows.collect { String line ->
                def row = new groovy.json.JsonSlurper().parseText(line)
                tuple(
                    groupKey(caseId, count),
                    caseId,
                    row.seed_solution_id as String,
                    caseBundle,
                    finalistBundle,
                    phenix_manifest
                )
            }
    }
    refinement = M6_REFINEMENT(refinement_tasks)
    grouped_refinement = refinement
        .groupTuple()
        .map { key, caseIds, caseBundles, finalistBundles, results ->
            tuple(
                key.groupTarget as String,
                caseBundles[0] as Path,
                finalistBundles[0] as Path,
                results as List<Path>
            )
        }
    assembled = M6_ASSEMBLE_CASE(grouped_refinement)
    empty_assembly_inputs = empty_finalist_plans.map {
        caseId, caseBundle, finalistBundle, count ->
        tuple(caseId, caseBundle, finalistBundle)
    }
    assembled_empty = M6_ASSEMBLE_EMPTY_CASE(empty_assembly_inputs)
    case_evidence = assembled.mix(assembled_empty)
    collected_cases = case_evidence
        .collect()
        .map { rows ->
            rows.sort { left, right -> left[0] <=> right[0] }
                .collect { row -> row[1] as Path }
        }
    result = M6_AGGREGATE_TRACK(
        collected_cases,
        runner_root,
        protocol,
        database_manifest,
        phenix_manifest,
        track
    )

    emit:
    plan_bundle: Path = plan
    scientific_result: Path = result
}
