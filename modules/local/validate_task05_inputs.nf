nextflow.enable.types = true

process VALIDATE_TASK05_INPUTS {
    tag 'task05-input-contracts'
    label 'process_single'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    catalogues: Path
    crystals: Path
    pipeline_config: Path
    database_manifest: Path
    phenix_manifest: Path
    cache_root: String
    review_mode: String
    profile_mode: String
    analysis_stage: String

    output:
    scope: Path = file('scope')

    script:
    def scopeStatus = (
        analysis_stage == 'task05'
            ? 'task05_preflight_complete_downstream_deferred'
            : 'discovery_and_model_preparation_requested'
    )
    """
    genome-to-diffraction --no-progress contract validate catalogue-manifest '${catalogues}'
    genome-to-diffraction --no-progress contract validate crystal-manifest '${crystals}'
    genome-to-diffraction --no-progress contract validate pipeline-config '${pipeline_config}'
    genome-to-diffraction --no-progress contract validate database-manifest '${database_manifest}'
    genome-to-diffraction --no-progress contract validate phenix-install-manifest '${phenix_manifest}'

    mkdir -p scope
    cp '${catalogues}' scope/catalogue_manifest.json
    cp '${crystals}' scope/crystal_manifest.json
    cp '${pipeline_config}' scope/pipeline_config.yaml
    cp '${database_manifest}' scope/database_manifest.json
    cp '${phenix_manifest}' scope/phenix_install_manifest.json
    printf '%s\n' '{"schema_version":"1.0","status":"${scopeStatus}","cache_root":"${cache_root}","review_mode":"${review_mode}","profile_mode":"${profile_mode}","analysis_stage":"${analysis_stage}"}' > scope/pipeline_scope.json
    """

    stub:
    """
    mkdir -p scope
    cp '${catalogues}' scope/catalogue_manifest.json
    cp '${crystals}' scope/crystal_manifest.json
    cp '${pipeline_config}' scope/pipeline_config.yaml
    cp '${database_manifest}' scope/database_manifest.json
    cp '${phenix_manifest}' scope/phenix_install_manifest.json
    printf '%s\n' '{"schema_version":"1.0","status":"stub_input_contracts_validated","analysis_stage":"${analysis_stage}"}' > scope/pipeline_scope.json
    """
}
