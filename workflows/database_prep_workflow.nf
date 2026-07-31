nextflow.enable.types = true

include { FOUNDATION_DATABASE_STUB } from '../modules/local/foundation_database_stub'

workflow DATABASE_PREP_WORKFLOW {
    take:
    database_root: String
    prepare_pdb_foldseek: Boolean
    prepare_pdb_sequences: Boolean
    prepare_prostt5: Boolean
    initialise_coordinate_cache: Boolean
    verify_only: Boolean
    database_fixture: Path

    main:
    database_manifest = FOUNDATION_DATABASE_STUB(
        database_root,
        prepare_pdb_foldseek,
        prepare_pdb_sequences,
        prepare_prostt5,
        initialise_coordinate_cache,
        verify_only,
        database_fixture
    )

    emit:
    manifest: Path = database_manifest
}
