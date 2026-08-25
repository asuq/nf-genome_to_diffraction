nextflow.enable.types = true

include {
    RUN_ADDITIONAL_COPY_PHASER;
    RUN_PHASE3_ADDITIONAL_COPY_PHASER
} from '../modules/local/run_additional_copy_phaser'
include {
    STAGE_PHASE3_CRYSTAL_APPROVED_MR_SEEDS
} from '../modules/local/stage_phase3_approved_mr_seeds'

workflow ADDITIONAL_COPY_WORKFLOW {
    take:
    seeds: Path
    review_validation: Path
    review_package: Path
    hypotheses: Path
    sequence_groups: Path
    preflight: Path
    mtz: Path
    phenix_manifest: Path

    main:
    seed_rows = seeds
        .splitCsv(header: true, sep: '\t')
        .map { row ->
            tuple(
                row.seed_solution_id as String,
                file(row.search_model as String, checkIfExists: true),
                row.search_model_sha256 as String
            )
        }
    additional_copy_results = RUN_ADDITIONAL_COPY_PHASER(
        seed_rows,
        review_validation.first(),
        review_package.first(),
        hypotheses.first(),
        sequence_groups.first(),
        preflight.first(),
        mtz.first(),
        phenix_manifest.first()
    )

    emit:
    results: Path = additional_copy_results
}


// Each channel item owns one reviewed crystal and all its selected A evidence;
// no shared queue can be consumed by another crystal or approved seed.
workflow PHASE3_ADDITIONAL_COPY_WORKFLOW {
    take:
    reviewed_crystals: Tuple

    main:
    complete_seeds = reviewed_crystals.flatMap { item ->
        String crystalId = item[0] as String
        Path approved = item[1] as Path
        Path seeds = approved.resolve('additional_copy_seeds.tsv')
        def lines = seeds.toFile().readLines()
        if (lines.isEmpty()) {
            error "Phase III approved seed table is empty for ${crystalId}"
        }
        def header = lines[0].split('\t', -1).toList()
        def required = ['seed_solution_id', 'search_model', 'search_model_sha256']
        if (header.size() < 3 || header.take(3) != required) {
            error "Phase III approved seed headers differ for ${crystalId}"
        }
        def stageManifest = new groovy.json.JsonSlurper().parse(
            approved.resolve('live_m4_stage_manifest.json').toFile()
        )
        if (stageManifest.phase3_approval_provenance?.crystal_id != crystalId) {
            error "Phase III approved seeds belong to another crystal: ${crystalId}"
        }
        lines.drop(1).findAll { String line -> !line.isEmpty() }.collect {
            String line ->
            def columns = line.split('\t', -1)
            if (columns.size() < 3) {
                error "Phase III approved seed row is incomplete for ${crystalId}"
            }
            tuple(
                crystalId,
                columns[0],
                file(columns[1], checkIfExists: true),
                columns[2],
                file(
                    approved.resolve('validated_mr_seed_decisions.json'),
                    checkIfExists: true
                ),
                file(item[2], checkIfExists: true),
                file(item[3], checkIfExists: true),
                file(item[4], checkIfExists: true),
                file(item[5], checkIfExists: true),
                file(item[6], checkIfExists: true),
                file(item[7], checkIfExists: true),
                file(item[8], checkIfExists: true)
            )
        }
    }
    additional_copy_results = RUN_PHASE3_ADDITIONAL_COPY_PHASER(complete_seeds)

    emit:
    results: Tuple = additional_copy_results
}


// Revalidate each owned A checkpoint separately, retain rejected/deferred
// stages, and join placement inputs only by their exact crystal identity.
workflow PHASE3_REVIEWED_ADDITIONAL_COPY_WORKFLOW {
    take:
    reviewed_crystals: Tuple
    owned_run_registry: Path?
    execution_identity: Path?
    owned_parent_run_id: String?

    main:
    stage_items = reviewed_crystals.map { item ->
        if (owned_run_registry != null) {
            tuple(
                item[0],
                item[1],
                item[2],
                item[3],
                item[4],
                owned_run_registry,
                execution_identity,
                owned_parent_run_id
            )
        } else {
            tuple(item[0], item[1], item[2], item[3], item[4])
        }
    }
    staged = STAGE_PHASE3_CRYSTAL_APPROVED_MR_SEEDS(stage_items)
    complete_crystals = staged
        .join(reviewed_crystals, by: 0, failOnDuplicate: true, failOnMismatch: true)
        .map {
            crystalId,
            approved,
            legacyReview,
            reviewedDecision,
            phase3Package,
            hypotheses,
            sequences,
            preflight,
            mtz,
            phenix,
            selection ->
            tuple(
                crystalId,
                approved,
                file(
                    legacyReview.resolve('mr_seed_review_manifest.json'),
                    checkIfExists: true
                ),
                hypotheses,
                sequences,
                preflight,
                mtz,
                phenix,
                selection
            )
        }
    placements = PHASE3_ADDITIONAL_COPY_WORKFLOW(complete_crystals)

    emit:
    stage: Tuple = staged
    results: Tuple = placements
}
