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

    output:
    scope: Path = file('scope')

    script:
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
    printf '%s\n' '{"schema_version":"1.0","status":"task05_preflight_complete_downstream_deferred","cache_root":"${cache_root}","review_mode":"${review_mode}","profile_mode":"${profile_mode}"}' > scope/pipeline_scope.json
    """

    stub:
    """
    mkdir -p scope
    cp '${catalogues}' scope/catalogue_manifest.json
    cp '${crystals}' scope/crystal_manifest.json
    cp '${pipeline_config}' scope/pipeline_config.yaml
    cp '${database_manifest}' scope/database_manifest.json
    cp '${phenix_manifest}' scope/phenix_install_manifest.json
    printf '%s\n' '{"schema_version":"1.0","status":"stub_task05_preflight_only"}' > scope/pipeline_scope.json
    """
}
