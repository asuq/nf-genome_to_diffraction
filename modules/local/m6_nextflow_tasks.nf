nextflow.enable.types = true

process M6_PLAN_TRACK {
    tag "m6-plan:${track}"
    label 'm6_small'

    input:
    runner_root: Path
    database_manifest: Path
    software_lock: Path
    track: String

    output:
    plan: Path = file('m6_track_plan')

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark plan-m6-nextflow \
        --runner-root '${runner_root}' \
        --database-manifest '${database_manifest}' \
        --software-lock '${software_lock}' \
        --track '${track}' \
        --outdir m6_track_plan
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/track_plan' m6_track_plan
    """
}

process M6_IMPORT_CATALOGUE {
    tag "m6-import:${item[0]}"
    label 'm6_small'
    storeDir { "${params.m6_discovery_store}/catalogue/${item[1]}" }

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file('m6_catalogue_bundle'))

    script:
    """
        genome-to-diffraction --no-progress --log-format json \
        benchmark run-m6-catalogue-task \
        --task '${item[2]}' \
        --software-lock '${item[3]}' \
        --outdir m6_catalogue_bundle
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/catalogue_bundle' m6_catalogue_bundle
    """
}

process M6_BUILD_SEARCH_BATCHES {
    tag 'm6-build-search-batches'
    label 'm6_small'

    input:
    item: Tuple

    output:
    batches: Path = file('m6_batch_plan')

    script:
    def catalogueArgs = item[0].collect { Path bundle -> "--catalogue-bundle '${bundle}'" }.join(' ')
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark build-m6-search-batches \
        ${catalogueArgs} \
        --database-manifest '${item[1]}' \
        --execution-policy '${item[2]}' \
        --software-lock '${item[3]}' \
        --outdir m6_batch_plan
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/batch_plan' m6_batch_plan
    """
}

process M6_SEARCH_PDB {
    tag "m6-pdb:${item[0]}"
    label 'm6_pdb_search'
    storeDir { "${params.m6_discovery_store}/pdb/${item[1]}" }

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file('m6_pdb_bundle'))

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark run-m6-pdb-task \
        --batch-task '${item[2]}' \
        --database-manifest '${item[3]}' \
        --execution-policy '${item[4]}' \
        --software-lock '${item[5]}' \
        --threads '${task.cpus}' \
        --outdir m6_pdb_bundle
    """

    stub:
    """
    if [[ '${item[0]}' == b* ]]; then
        sleep 4
    else
        sleep 1
    fi
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/pdb_bundle' m6_pdb_bundle
    """
}

process M6_SEARCH_FOLDSEEK {
    tag "m6-foldseek:${item[0]}"
    label 'm6_foldseek_search'
    storeDir { "${params.m6_discovery_store}/foldseek/${item[1]}" }

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file('m6_foldseek_bundle'))

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark run-m6-foldseek-task \
        --batch-task '${item[2]}' \
        --database-manifest '${item[3]}' \
        --execution-policy '${item[4]}' \
        --software-lock '${item[5]}' \
        --threads '${task.cpus}' \
        --outdir m6_foldseek_bundle
    """

    stub:
    """
    if [[ '${item[0]}' == d* ]]; then
        sleep 4
    else
        sleep 1
    fi
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/foldseek_bundle' m6_foldseek_bundle
    """
}

process M6_PARTITION_DISCOVERY {
    tag "m6-partition:${catalogue[0]}"
    label 'm6_small'

    input:
    catalogue: List
    batch_plan: Path
    pdb_results: List<Path>
    foldseek_results: List<Path>

    output:
    result: Tuple = tuple(
        catalogue[0],
        catalogue[1],
        file('m6_discovery_partition/pdb_bundle'),
        file('m6_discovery_partition/foldseek_bundle')
    )

    script:
    def pdbArgs = pdb_results.collect { Path bundle -> "--pdb-result '${bundle}'" }.join(' ')
    def foldseekArgs = foldseek_results.collect { Path bundle -> "--foldseek-result '${bundle}'" }.join(' ')
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark partition-m6-discovery \
        --catalogue-bundle '${catalogue[1]}' \
        --batch-plan '${batch_plan}' \
        ${pdbArgs} \
        ${foldseekArgs} \
        --outdir m6_discovery_partition
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/discovery_partition' m6_discovery_partition
    """
}

process M6_PREFLIGHT_CASE {
    tag "m6-preflight:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], item[1], item[2], file('m6_preflight_bundle'))

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark run-m6-preflight-task \
        --task '${item[2]}' \
        --phenix-manifest '${item[3]}' \
        --outdir m6_preflight_bundle
    """

    stub:
    """
    if [[ '${item[0]}' == M6C057 ]]; then
        cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/early_preflight_bundle' m6_preflight_bundle
    else
        cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/preflight_bundle' m6_preflight_bundle
    fi
    """
}

process M6_APPLY_POLICY {
    tag "m6-policy:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], item[1], item[2], item[7], file('m6_policy_bundle'))

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark run-m6-policy-task \
        --task '${item[1]}' \
        --catalogue-bundle '${item[2]}' \
        --pdb-bundle '${item[3]}' \
        --foldseek-bundle '${item[4]}' \
        --protocol '${item[5]}' \
        --database-manifest '${item[6]}' \
        --outdir m6_policy_bundle
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/policy_bundle' m6_policy_bundle
    """
}

process M6_PREPARE_ACTIVE_CASE {
    tag "m6-case:${item[0]}"
    label 'm6_case_prepare'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file('m6_case_bundle'))

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark run-m6-case-task \
        --task '${item[1]}' \
        --preflight-bundle '${item[3]}' \
        --catalogue-bundle '${item[2]}' \
        --policy-bundle '${item[4]}' \
        --database-manifest '${item[5]}' \
        --outdir m6_case_bundle
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/case_bundle' m6_case_bundle
    """
}

process M6_PREPARE_EARLY_CASE {
    tag "m6-early-case:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file('m6_case_bundle'))

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark run-m6-case-task \
        --task '${item[1]}' \
        --preflight-bundle '${item[3]}' \
        --catalogue-bundle '${item[2]}' \
        --database-manifest '${item[4]}' \
        --outdir m6_case_bundle
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/empty_case_bundle' m6_case_bundle
    """
}

process M6_FIRST_COPY {
    tag "m6-first:${item[1]}:${item[3].baseName}"
    label 'm6_first_copy'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], item[1], item[2], file('m6_first_copy_result'))

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        mr first-copy \
        --hypotheses '${item[3]}' \
        --hypothesis-id '${item[3].baseName}' \
        --sequence-groups '${item[2]}/selected-candidates/sequence_groups.jsonl' \
        --processed-models '${item[2]}/first-copy-funnel/model_registry/processed_models.jsonl' \
        --model-preparation-manifest '${item[2]}/first-copy-funnel/model_registry/model_preparation_manifest.json' \
        --preflight '${item[2]}/preflight_bundle/preflight/mtz_preflight.jsonl' \
        --mtz '${item[2]}/reflections.mtz' \
        --phenix-manifest '${item[4]}' \
        --threads '${task.cpus}' \
        --outdir m6_first_copy_result
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/first_copy_phaser' m6_first_copy_result
    """
}

process M6_SELECT_SEEDS {
    tag "m6-seeds:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], item[1], file('m6_seed_bundle'))

    script:
    def resultArgs = item[2].collect { Path result -> "--first-copy-result '${result}'" }.join(' ')
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark select-m6-seeds \
        --case-bundle '${item[1]}' \
        ${resultArgs} \
        --outdir m6_seed_bundle
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/seed_bundle' m6_seed_bundle
    """
}

process M6_EMPTY_SEEDS {
    tag "m6-empty-seeds:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], item[1], file('m6_seed_bundle'))

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark empty-m6-seeds \
        --case-bundle '${item[1]}' \
        --outdir m6_seed_bundle
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/empty_seed_bundle' m6_seed_bundle
    """
}

process M6_ADDITIONAL_COPY {
    tag "m6-copy:${item[1]}:${item[2]}"
    label 'm6_add_copy'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], item[1], item[3], item[4], file('m6_add_copy_result'))

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark run-m6-add-copy-task \
        --case-bundle '${item[3]}' \
        --seed-bundle '${item[4]}' \
        --seed-solution-id '${item[2]}' \
        --phenix-manifest '${item[5]}' \
        --threads '${task.cpus}' \
        --outdir m6_add_copy_result
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/add_copy_bundle' m6_add_copy_result
    """
}

process M6_SELECT_FINALISTS {
    tag "m6-finalists:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], item[1], file('m6_finalist_bundle'))

    script:
    def resultArgs = item[3].collect { Path result -> "--add-copy-result '${result}'" }.join(' ')
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark select-m6-finalists \
        --case-bundle '${item[1]}' \
        --seed-bundle '${item[2]}' \
        ${resultArgs} \
        --outdir m6_finalist_bundle
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/finalist_bundle' m6_finalist_bundle
    """
}

process M6_EMPTY_FINALISTS {
    tag "m6-empty-finalists:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], item[1], file('m6_finalist_bundle'))

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark empty-m6-finalists \
        --case-bundle '${item[1]}' \
        --seed-bundle '${item[2]}' \
        --outdir m6_finalist_bundle
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/empty_finalist_bundle' m6_finalist_bundle
    """
}

process M6_REFINEMENT {
    tag "m6-refine:${item[1]}:${item[2]}"
    label 'm6_refinement'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], item[1], item[3], item[4], file('m6_refinement_result'))

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark run-m6-refinement-task \
        --finalist-bundle '${item[4]}' \
        --seed-solution-id '${item[2]}' \
        --phenix-manifest '${item[5]}' \
        --threads '${task.cpus}' \
        --outdir m6_refinement_result
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/refinement_bundle' m6_refinement_result
    """
}

process M6_ASSEMBLE_CASE {
    tag "m6-evidence:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file('m6_case_evidence'))

    script:
    def resultArgs = item[3].collect { Path result -> "--refinement-result '${result}'" }.join(' ')
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark assemble-m6-case \
        --case-bundle '${item[1]}' \
        --finalist-bundle '${item[2]}' \
        ${resultArgs} \
        --outdir m6_case_evidence
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/case_evidence' m6_case_evidence
    """
}

process M6_ASSEMBLE_EMPTY_CASE {
    tag "m6-empty-evidence:${item[0]}"
    label 'm6_small'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(item[0], file('m6_case_evidence'))

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark assemble-m6-case \
        --case-bundle '${item[1]}' \
        --finalist-bundle '${item[2]}' \
        --outdir m6_case_evidence
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/case_evidence' m6_case_evidence
    """
}

process M6_AGGREGATE_TRACK {
    tag "m6-aggregate:${track}"
    label 'm6_small'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    case_evidence: List<Path>
    runner_root: Path
    protocol: Path
    database_manifest: Path
    phenix_manifest: Path
    track: String

    output:
    result: Path = file('m6_scientific')

    script:
    def caseArgs = case_evidence.collect { Path result -> "--case-evidence '${result}'" }.join(' ')
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark aggregate-m6-track \
        ${caseArgs} \
        --runner-root '${runner_root}' \
        --protocol '${protocol}' \
        --database-manifest '${database_manifest}' \
        --phenix-manifest '${phenix_manifest}' \
        --track '${track}' \
        --outdir m6_scientific
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/m6_nextflow/track_output' m6_scientific
    """
}
