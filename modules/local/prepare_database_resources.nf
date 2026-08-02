nextflow.enable.types = true

process PREPARE_DATABASE_RESOURCES {
    tag 'shared-reference-databases'
    label 'process_database_download'
    publishDir "${params.outdir}/provenance", mode: 'copy', overwrite: true

    input:
    database_root: String
    prepare_pdb_foldseek: Boolean
    prepare_pdb_sequences: Boolean
    prepare_prostt5: Boolean
    initialise_coordinate_cache: Boolean
    verify_esm_atlas_connectivity: Boolean
    verify_only: Boolean
    force_rebuild: Boolean
    full_verify: Boolean
    expected_manifest: String
    expected_manifest_sha256: String
    storage_limit_bytes: String
    minimum_free_bytes: String
    threads: Integer
    database_fixture: Path

    stage:
    stageAs database_fixture, 'database_manifest.fixture.json'

    output:
    manifest: Path = file('database_manifest.json')

    script:
    """
    args=(
        --database-root '${database_root}'
        --manifest database_manifest.json
        --storage-limit-bytes '${storage_limit_bytes}'
        --minimum-free-bytes '${minimum_free_bytes}'
        --threads '${threads}'
    )
    [[ '${prepare_pdb_foldseek}' == 'true' ]] && args+=(--prepare-pdb-foldseek)
    [[ '${prepare_pdb_sequences}' == 'true' ]] && args+=(--prepare-pdb-sequences)
    [[ '${prepare_prostt5}' == 'true' ]] && args+=(--prepare-prostt5)
    [[ '${initialise_coordinate_cache}' == 'true' ]] && args+=(--initialise-coordinate-cache)
    [[ '${verify_esm_atlas_connectivity}' == 'true' ]] && args+=(--verify-esm-atlas-connectivity)
    [[ '${verify_only}' == 'true' ]] && args+=(--verify-only)
    [[ '${force_rebuild}' == 'true' ]] && args+=(--force-rebuild)
    [[ '${full_verify}' == 'true' ]] && args+=(--full-verify)
    if [[ -n '${expected_manifest}' ]]; then
        args+=(--expected-manifest '${expected_manifest}')
    fi
    if [[ -n '${expected_manifest_sha256}' ]]; then
        args+=(--expected-manifest-sha256 '${expected_manifest_sha256}')
    fi

    genome-to-diffraction --no-progress databases prepare "\${args[@]}"
    """

    stub:
    """
    cp '${database_fixture}' database_manifest.json
    """
}
