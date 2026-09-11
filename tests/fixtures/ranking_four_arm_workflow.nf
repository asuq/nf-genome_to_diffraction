nextflow.enable.types = true

include {
    M6_BUILD_SEARCH_BATCHES;
    M6_PARTITION_DISCOVERY;
    M6_PREFLIGHT_CASE;
    M6_APPLY_POLICY;
    M6_STAGE_COORDINATES;
    M6_PREPARE_ACTIVE_CASE;
    M6_PREPARE_EARLY_CASE
} from '../../modules/local/m6_nextflow_tasks'

include {
    M6_IMPORT_CATALOGUE;
    M6_SEARCH_PDB;
    M6_SEARCH_FOLDSEEK
} from '../../modules/local/m6_truthless_cache_tasks'

include {
    RF_PLAN; RF_PREPARE; RF_FIRST_COPY; RF_REVIEWS; RF_COPY;
    RF_FINALISTS; RF_REFINE; RF_IDENTITY; RF_AGGREGATE
} from './ranking_four_arm_tasks'

workflow RF_REFERENCE_WORKFLOW {
    take:
    runner_root: Path
    protocol: Path
    execution_policy: Path
    software_lock: Path
    database_manifest: Path
    phenix_manifest: Path

    main:
    plan = RF_PLAN(runner_root, database_manifest, software_lock)
    plan_bundles = plan.map { Path root -> root.resolve('bundle') }
    plan_context = plan.first().map { Path root -> root.resolve('context.json') }

    catalogue_tasks = plan_bundles.flatMap { Path bundle ->
        bundle.resolve('reference_catalogue_tasks.tsv').toFile().readLines().drop(1)
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
    case_tasks = plan_bundles.flatMap { Path bundle ->
        bundle.resolve('reference_case_tasks.tsv').toFile().readLines().drop(1)
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
        .collect()
        .map { values ->
            values.sort { left, right ->
                    (left[0] as String) <=> (right[0] as String)
                }
                .collect { row -> row[1] as Path }
        }
    // Reference salt keeps batch-plan scheduling separate; only the three approved
    // content-addressed import/search processes can reuse cross-track work.
    batch_input = imported_bundles.map { bundles ->
        tuple(bundles, database_manifest, execution_policy, software_lock, 'rf-fixed-five-v1')
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
        .collect()
        .map { values ->
            values.sort { left, right ->
                    (left[0] as String) <=> (right[0] as String)
                }
                .collect { row -> row[1] as Path }
        }
    foldseek_bundles_value = foldseek
        .collect()
        .map { values ->
            values.sort { left, right ->
                    (left[0] as String) <=> (right[0] as String)
                }
                .collect { row -> row[1] as Path }
        }
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
        // Several cases consume each uniquely planned catalogue result.
        .combine(discovery, by: 0)
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
    coordinate_stage_inputs = policies.map {
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
    coordinate_stages = M6_STAGE_COORDINATES(coordinate_stage_inputs)
    active_cases = M6_PREPARE_ACTIVE_CASE(coordinate_stages)

    early_joined = preflight_early
        .map { caseId, catalogueKey, task, preflightBundle ->
            tuple(catalogueKey, caseId, task, preflightBundle)
        }
        .combine(imported, by: 0)
    early_case_inputs = early_joined.map {
        catalogueKey, caseId, task, preflightBundle, catalogueBundle ->
        tuple(caseId, task, catalogueBundle, preflightBundle)
    }
    early_cases = M6_PREPARE_EARLY_CASE(early_case_inputs)

    // Case-ID joins are one-to-one; catalogue broadcasts above remain many-to-one.
    active_contexts = coordinate_stages
        .map { caseId, task, catalogueBundle, preflightBundle, policyBundle, stage ->
            tuple(caseId, catalogueBundle, stage)
        }
        .join(active_cases, by: 0, failOnDuplicate: true, failOnMismatch: true)
        .map { caseId, catalogueBundle, stage, preparedBundle ->
            tuple(caseId, catalogueBundle, preparedBundle, [stage])
        }
    early_contexts = early_case_inputs
        .map { caseId, task, catalogueBundle, preflightBundle ->
            tuple(caseId, catalogueBundle)
        }
        .join(early_cases, by: 0, failOnDuplicate: true, failOnMismatch: true)
        .map { caseId, catalogueBundle, preparedBundle ->
            tuple(caseId, catalogueBundle, preparedBundle, [])
        }
    prepared = RF_PREPARE(active_contexts.mix(early_contexts), plan_context, phenix_manifest)
    prepared_plans = prepared.map { caseId, root ->
        def manifest = new groovy.json.JsonSlurper().parseText(
            root.resolve('bundle/reference_prepared_case.json').toFile().text
        )
        if (!(manifest.status in ['materialised', 'completed_no_model', 'preflight_blocked'])) {
            error "Unknown reference preparation status for ${caseId}"
        }
        def tasks = manifest.status == 'materialised'
            ? new groovy.json.JsonSlurper().parseText(
                root.resolve('bundle/cohorts/reference_cohorts.json').toFile().text
            ).tasks as List
            : []
        if (tasks.size() > 50) {
            error "Reference first-copy union exceeds its budget for ${caseId}"
        }
        tuple(caseId, root, manifest.status as String, tasks)
    }
    materialised = prepared_plans.filter { caseId, root, status, tasks ->
        status == 'materialised'
    }
    // Genuine early preparation goes directly to the exact-case aggregate.
    // Materialised empty admission still has a real review/identity boundary.
    first_tasks = materialised.flatMap { caseId, root, status, tasks ->
        tasks.collect { row ->
            tuple(
                groupKey(caseId, tasks.size()), caseId, root,
                row.hypothesis.hypothesis_id as String
            )
        }
    }
    first_results = RF_FIRST_COPY(first_tasks)
    first_groups = first_results.groupTuple().map { key, caseIds, roots, results ->
        def ordered = (results as List).sort { left, right -> left.toString() <=> right.toString() }
        tuple(key.groupTarget as String, roots[0] as Path, ordered)
    }
    empty_first = materialised
        .filter { caseId, root, status, tasks -> tasks.isEmpty() }
        .map { caseId, root, status, tasks -> tuple(caseId, root, []) }
    reviews = RF_REVIEWS(first_groups.mix(empty_first))
    review_plans = reviews.map { caseId, root ->
        def tasks = new groovy.json.JsonSlurper().parseText(
            root.resolve('copy_tasks.json').toFile().text
        ).tasks as List
        if (tasks.size() > 20) {
            error "Reference copy union exceeds its paired budgets for ${caseId}"
        }
        tuple(caseId, root, tasks)
    }
    copy_tasks = review_plans.flatMap { caseId, root, tasks ->
        tasks.collect { row ->
            tuple(
                groupKey(caseId, tasks.size()), caseId, root,
                row.admission_prior as String, row.seed_solution_id as String
            )
        }
    }
    copy_results = RF_COPY(copy_tasks)
    copy_groups = copy_results.groupTuple().map { key, caseIds, roots, results ->
        def ordered = (results as List).sort { left, right -> left.toString() <=> right.toString() }
        tuple(key.groupTarget as String, roots[0] as Path, ordered)
    }
    empty_copy = review_plans
        .filter { caseId, root, tasks -> tasks.isEmpty() }
        .map { caseId, root, tasks -> tuple(caseId, root, []) }
    finalists = RF_FINALISTS(copy_groups.mix(empty_copy))
    finalist_plans = finalists.map { caseId, root ->
        def tasks = new groovy.json.JsonSlurper().parseText(
            root.resolve('bundle/reference_finalists.json').toFile().text
        ).tasks as List
        if (tasks.size() > 20) {
            error "Reference finalist union exceeds its paired budgets for ${caseId}"
        }
        tuple(caseId, root, tasks)
    }
    refine_tasks = finalist_plans.flatMap { caseId, root, tasks ->
        tasks.collect { row ->
            tuple(
                groupKey(caseId, tasks.size()), caseId, root,
                row.admission_prior as String, row.task.seed_solution_id as String
            )
        }
    }
    refine_results = RF_REFINE(refine_tasks)
    refine_groups = refine_results.groupTuple().map { key, caseIds, roots, results ->
        def ordered = (results as List).sort { left, right -> left.toString() <=> right.toString() }
        tuple(key.groupTarget as String, roots[0] as Path, ordered)
    }
    empty_refine = finalist_plans
        .filter { caseId, root, tasks -> tasks.isEmpty() }
        .map { caseId, root, tasks -> tuple(caseId, root, []) }
    identities = RF_IDENTITY(refine_groups.mix(empty_refine))
    all_prepared = prepared.toList().map { rows ->
        rows.sort { left, right -> left[0] <=> right[0] }
            .collect { row -> (row[1] as Path).resolve('context.json') }
    }
    // toList emits an explicit empty value when all cases terminated early.
    all_identities = identities.toList().map { rows ->
        rows.sort { left, right -> left[0] <=> right[0] }
            .collect { row -> (row[1] as Path).resolve('context.json') }
    }
    result = RF_AGGREGATE(plan_context, all_prepared, all_identities)

    emit:
    plan_bundle: Path = plan
    reference_result: Path = result
}
