nextflow.enable.types = true

include { PHASE3_NO_A_EXPANSION_WORKFLOW } from '../phase3_no_a_expansion_workflow'

process VALIDATE_KNOWN_CONTROL_REOPENING {
    label 'process_low'

    input:
    input_bundle: Path
    manifest_name: String
    source_commit: String
    phenix_manifest: Path

    stage:
    stageAs input_bundle, 'input_bundle'

    output:
    dispatch: Path = file('known_control_dispatch.json')

    script:
    """
    python -m genome_to_diffraction.hpc.raven_controls \
        --manifest 'input_bundle/${manifest_name}' --source-commit '${source_commit}' \
        --phenix-manifest '${phenix_manifest}' \
        --output known_control_dispatch.json
    """
}

workflow KNOWN_CONTROL_REOPENING_WORKFLOW {
    take:
    manifest: Path
    source_commit: String
    phenix_manifest: Path

    main:
    checked = VALIDATE_KNOWN_CONTROL_REOPENING(
        manifest.parent, manifest.name, source_commit, phenix_manifest
    )
    def parent = new groovy.json.JsonSlurper().parse(manifest.toFile()).parent_run_id as String
    items = checked.map { path ->
        def item = new groovy.json.JsonSlurper().parse(path.toFile())
        if (item.parent_run_id != parent) {
            error 'Known-control parent changed during input validation'
        }
        def p = item.paths
        tuple(
            item.crystal_id as String,
            file(p.pass1_assessment as String, checkIfExists: true),
            file(p.no_a_expansion_plan as String, checkIfExists: true),
            file(p.sequence_groups as String, checkIfExists: true),
            file(p.model_registry as String, checkIfExists: true),
            file(p.preflight as String, checkIfExists: true),
            file(p.mtz as String, checkIfExists: true),
            file(p.diffraction_selection as String, checkIfExists: true),
            file(p.phenix_manifest as String, checkIfExists: true),
            file(p.execution_identity as String, checkIfExists: true),
            file(p.source_records as String, checkIfExists: true),
            file(p.matthews as String, checkIfExists: true),
            file(p.pipeline_config as String, checkIfExists: true)
        )
    }
    PHASE3_NO_A_EXPANSION_WORKFLOW(items, parent)
}
