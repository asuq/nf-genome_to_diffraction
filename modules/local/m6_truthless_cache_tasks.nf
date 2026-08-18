/*
 * Truthless M6 catalogue/import search boundaries.
 *
 * Inputs are validated content IDs plus explicitly staged task, database,
 * policy, and software-lock paths. Outputs are checksum-bearing directory
 * bundles. Adapter or contract failures terminate the task; scientific no-hit
 * records remain normal outputs. `cache 'deep'` binds reuse to staged content
 * rather than track-plan work paths. Focused stub tests require two catalogue,
 * two PDB, and two Foldseek tasks to be the only cross-track cache hits.
 *
 * This module intentionally uses tuple path qualifiers because the preview
 * typed-process syntax treats paths nested in a generic Tuple as values and
 * therefore hashes their track-specific producer paths.
 */

process M6_IMPORT_CATALOGUE {
    tag "m6-import:${catalogue_key}"
    label 'm6_small'
    cache 'deep'

    input:
    tuple val(catalogue_key), val(import_cache_key), path('catalogue_task/task.json'), path('catalogue_task/catalogue.faa'), path('catalogue_task/analysis_config.json'), path('software_lock')

    output:
    tuple val(catalogue_key), path('m6_catalogue_bundle'), emit: result

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark run-m6-catalogue-task \
        --task catalogue_task \
        --software-lock software_lock \
        --outdir m6_catalogue_bundle
    """

    stub:
    """
    /bin/bash '${projectDir}/tests/scripts/copy_stub_fixture.sh' \
        '${projectDir}/tests/fixtures/stubs/m6_nextflow/catalogue_bundle' m6_catalogue_bundle
    """
}

process M6_SEARCH_PDB {
    tag "m6-pdb:${batch_id}"
    label 'm6_pdb_search'
    cache 'deep'

    input:
    tuple val(batch_id), val(search_cache_key), path('batch_task/task.json'), path('batch_task/sequence_groups.jsonl'), path('database_manifest.json'), path('execution_policy.yaml'), path('software_lock')

    output:
    tuple val(batch_id), path('m6_pdb_bundle'), emit: result

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark run-m6-pdb-task \
        --batch-task batch_task \
        --database-manifest database_manifest.json \
        --execution-policy execution_policy.yaml \
        --software-lock software_lock \
        --threads '${task.cpus}' \
        --outdir m6_pdb_bundle
    """

    stub:
    """
    if [[ '${batch_id}' == b* ]]; then
        sleep 4
    else
        sleep 1
    fi
    /bin/bash '${projectDir}/tests/scripts/copy_stub_fixture.sh' \
        '${projectDir}/tests/fixtures/stubs/m6_nextflow/pdb_bundle' m6_pdb_bundle
    """
}

process M6_SEARCH_FOLDSEEK {
    tag "m6-foldseek:${batch_id}"
    label 'm6_foldseek_search'
    cache 'deep'

    input:
    tuple val(batch_id), val(search_cache_key), path('batch_task/task.json'), path('batch_task/sequence_groups.jsonl'), path('database_manifest.json'), path('execution_policy.yaml'), path('software_lock')

    output:
    tuple val(batch_id), path('m6_foldseek_bundle'), emit: result

    script:
    """
    genome-to-diffraction --no-progress --log-format json \
        benchmark run-m6-foldseek-task \
        --batch-task batch_task \
        --database-manifest database_manifest.json \
        --execution-policy execution_policy.yaml \
        --software-lock software_lock \
        --threads '${task.cpus}' \
        --outdir m6_foldseek_bundle
    """

    stub:
    """
    if [[ '${batch_id}' == d* ]]; then
        sleep 4
    else
        sleep 1
    fi
    /bin/bash '${projectDir}/tests/scripts/copy_stub_fixture.sh' \
        '${projectDir}/tests/fixtures/stubs/m6_nextflow/foldseek_bundle' m6_foldseek_bundle
    """
}
