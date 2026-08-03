nextflow.enable.types = true

include { PREPARE_DATABASE_RESOURCES } from '../modules/local/prepare_database_resources'

workflow DATABASE_PREP_WORKFLOW {
    take:
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
    scratch_root: String
    storage_limit_bytes: String
    minimum_free_bytes: String
    minimum_scratch_free_bytes: String
    database_fixture: Path

    main:
    database_manifest = PREPARE_DATABASE_RESOURCES(
        database_root,
        prepare_pdb_foldseek,
        prepare_pdb_sequences,
        prepare_prostt5,
        initialise_coordinate_cache,
        verify_esm_atlas_connectivity,
        verify_only,
        force_rebuild,
        full_verify,
        expected_manifest,
        expected_manifest_sha256,
        scratch_root,
        storage_limit_bytes,
        minimum_free_bytes,
        minimum_scratch_free_bytes,
        database_fixture
    )

    emit:
    manifest: Path = database_manifest
}
