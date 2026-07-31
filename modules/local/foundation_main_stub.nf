nextflow.enable.types = true

process FOUNDATION_MAIN_STUB {
    tag 'foundation-contract-wiring'
    label 'process_single'
    publishDir "${params.outdir}/foundation", mode: 'copy'

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
    bundle: Path = file('foundation')

    script:
    """
    printf '%s\n' 'foundation_only_not_implemented: scientific execution begins in later milestones' >&2
    exit 64
    """

    stub:
    """
    mkdir -p foundation
    cp '${catalogues}' foundation/catalogue_manifest.json
    cp '${crystals}' foundation/crystal_manifest.json
    cp '${pipeline_config}' foundation/pipeline_config.yaml
    cp '${database_manifest}' foundation/database_manifest.json
    cp '${phenix_manifest}' foundation/phenix_install_manifest.json
    """
}
