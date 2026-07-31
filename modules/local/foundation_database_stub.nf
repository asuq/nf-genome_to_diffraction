nextflow.enable.types = true

process FOUNDATION_DATABASE_STUB {
    tag 'foundation-database-contract-wiring'
    label 'process_single'
    publishDir "${params.outdir}/provenance", mode: 'copy'

    input:
    database_root: String
    prepare_pdb_foldseek: Boolean
    prepare_pdb_sequences: Boolean
    prepare_prostt5: Boolean
    initialise_coordinate_cache: Boolean
    verify_only: Boolean
    database_fixture: Path

    stage:
    stageAs database_fixture, 'database_manifest.fixture.json'

    output:
    manifest: Path = file('database_manifest.json')

    script:
    """
    printf '%s\n' 'foundation_only_not_implemented: database preparation begins in Epic 3' >&2
    exit 64
    """

    stub:
    """
    cp '${database_fixture}' database_manifest.json
    """
}
