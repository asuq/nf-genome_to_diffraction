nextflow.enable.types = true

// Publish one path-closed discovery checkpoint for bounded login staging. The
// Python adapter independently verifies complete catalogue/query coverage and
// inventories every copied byte; this process performs no network operation.
process PACKAGE_PHASE3_PROVIDER_DISCOVERY {
    tag "phase3-provider-discovery:${owned_run_id}"
    label 'process_low'
    stageInMode 'copy'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    owned_run_id: String
    execution_identity: Path
    pipeline_config: Path
    database_manifest: Path
    review_routes: Path
    catalogue_bundle: Path
    provider_plan_bundle: Path
    pdb_sequence_search: Path
    prostt5_foldseek_search: Path
    pdb_provider_hits: Path
    afdb_accession_map: Path

    output:
    checkpoint: Path = file('phase3_provider_discovery')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search package-phase3-provider-discovery \
        --owned-run-id '${owned_run_id}' \
        --execution-identity '${execution_identity}' \
        --config '${pipeline_config}' \
        --database-manifest '${database_manifest}' \
        --crystallographic-review-routes '${review_routes}' \
        --catalogue-bundle '${catalogue_bundle}' \
        --provider-plan-bundle '${provider_plan_bundle}' \
        --pdb-sequence-search '${pdb_sequence_search}' \
        --prostt5-foldseek-search '${prostt5_foldseek_search}' \
        --pdb-provider-hits '${pdb_provider_hits}' \
        --afdb-accession-map '${afdb_accession_map}' \
        --outdir phase3_provider_discovery
    """

    stub:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search package-phase3-provider-discovery \
        --owned-run-id '${owned_run_id}' \
        --execution-identity '${execution_identity}' \
        --config '${pipeline_config}' \
        --database-manifest '${database_manifest}' \
        --crystallographic-review-routes '${review_routes}' \
        --catalogue-bundle '${catalogue_bundle}' \
        --provider-plan-bundle '${provider_plan_bundle}' \
        --pdb-sequence-search '${pdb_sequence_search}' \
        --prostt5-foldseek-search '${prostt5_foldseek_search}' \
        --pdb-provider-hits '${pdb_provider_hits}' \
        --afdb-accession-map '${afdb_accession_map}' \
        --outdir phase3_provider_discovery
    """
}
