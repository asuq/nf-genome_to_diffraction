#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include {
    RUN_PHASE3_FIRST_COPY_PHASER;
    BUILD_PHASE3_MR_SEED_REVIEW;
    BUILD_PHASE3_OWNED_A_REVIEW_PACKAGE
} from './modules/local/phase3_multicrystal_first_copy_tasks'

params {
    funnel: Path
    confirmed_funnel_sha256: String
    sequence_groups: Path
    source_records: Path
    matthews: Path
    preflight: Path
    pipeline_config: Path
    crystal_directory: Path
    execution_identity: Path
    phenix_manifest: Path
    owned_run_id: String
    outdir: Path = file('results')
}

// This gate also runs in stub mode. It authenticates the independently confirmed
// funnel, selected one-copy records, resource plans, model bytes and parent
// runtime before any independent MR item is emitted. No human decision is made.
process VALIDATE_REVIEWED_FIRST_COPY_EXECUTION {
    tag 'reviewed-first-copy-authority'
    label 'process_low'
    cache 'deep'
    stageInMode 'copy'
    publishDir params.outdir, mode: 'copy', overwrite: false

    input:
    funnel: Path
    confirmed_sha256: String
    sequence_groups: Path
    source_records: Path
    matthews: Path
    preflight: Path
    pipeline_config: Path
    crystal_directory: Path
    execution_identity: Path
    phenix_manifest: Path

    output:
    dispatch: Path = file('reviewed_first_copy_dispatch.json')

    script:
    """
    # Authority contract: reviewed-first-copy-execution-gate-v1
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        review validate-reviewed-execution \
        --funnel-directory '${funnel.toString()}' \
        --confirmed-funnel-sha256 '${confirmed_sha256}' \
        --sequence-groups '${sequence_groups.toString()}' \
        --source-records '${source_records.toString()}' \
        --matthews-hypotheses '${matthews.toString()}' \
        --mtz-preflight '${preflight.toString()}' \
        --pipeline-config '${pipeline_config.toString()}' \
        --crystal-directory '${crystal_directory.toString()}' \
        --execution-identity '${execution_identity.toString()}' \
        --phenix-manifest '${phenix_manifest.toString()}' \
        --output-json reviewed_first_copy_dispatch.json
    """
}

workflow {
    main:
    if (!(params.confirmed_funnel_sha256 ==~ /[a-f0-9]{64}/)) {
        error 'Reviewed first-copy requires an independently confirmed SHA-256'
    }
    if (!(params.owned_run_id ==~ /[A-Za-z0-9][A-Za-z0-9._-]{0,127}/)) {
        error 'Reviewed first-copy requires a portable, distinct owned run ID'
    }
    dispatch = VALIDATE_REVIEWED_FIRST_COPY_EXECUTION(
        params.funnel,
        params.confirmed_funnel_sha256,
        params.sequence_groups,
        params.source_records,
        params.matthews,
        params.preflight,
        params.pipeline_config,
        params.crystal_directory,
        params.execution_identity,
        params.phenix_manifest
    )
    selected = dispatch.flatMap { Path authority ->
        def document = new groovy.json.JsonSlurper().parse(authority.toFile())
        if (params.owned_run_id == document.owned_parent_run_id) {
            error 'Reviewed first-copy must not reuse the parent owned run ID'
        }
        String crystalId = document.crystal_id as String
        def ids = document.hypothesis_ids as List<String>
        ids.collect { String hypothesisId ->
            Path hypothesis = params.funnel.resolve('hypotheses').resolve(
                "${hypothesisId}.jsonl"
            )
            Path resourcePlan = params.funnel.resolve('resource_plans').resolve(
                "${hypothesisId}.json"
            )
            def resources = new groovy.json.JsonSlurper().parse(resourcePlan.toFile())
            tuple(
                groupKey(crystalId, ids.size()),
                crystalId,
                params.funnel,
                params.crystal_directory,
                params.sequence_groups,
                params.source_records,
                params.sequence_groups,
                params.source_records,
                params.matthews,
                params.preflight,
                params.pipeline_config,
                params.phenix_manifest,
                authority,
                file(hypothesis, checkIfExists: true),
                file(resourcePlan, checkIfExists: true),
                resources
            )
        }
    }
    results = RUN_PHASE3_FIRST_COPY_PHASER(selected)
    reviewInputs = results.groupTuple().map { item ->
        tuple(
            item[0].groupTarget as String,
            item[2][0] as Path,
            item[13] as List<Path>,
            item[6][0] as Path,
            item[7][0] as Path,
            item[8][0] as Path,
            item[10][0] as Path
        )
    }
    reviews = BUILD_PHASE3_MR_SEED_REVIEW(reviewInputs)
    ownedInputs = reviews.map { crystalId, review ->
        tuple(
            crystalId,
            review,
            params.funnel.resolve('mr_hypotheses.jsonl'),
            params.execution_identity,
            params.owned_run_id,
            'unknown-screen',
            'phase3-pass1'
        )
    }
    BUILD_PHASE3_OWNED_A_REVIEW_PACKAGE(ownedInputs)
}
