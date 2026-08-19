nextflow.enable.types = true

process RESOLVE_PROVIDER_PLAN {
    tag 'resolve-provider-plan'
    label 'process_local'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    pipeline_config: Path
    database_manifest: Path

    output:
    plan: Path = file('provider_plan')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search resolve-provider-plan \
        --config '${pipeline_config}' \
        --database-manifest '${database_manifest}' \
        --outdir provider_plan
    """

    stub:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search resolve-provider-plan \
        --config '${pipeline_config}' \
        --database-manifest '${database_manifest}' \
        --outdir provider_plan
    """
}
