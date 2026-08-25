nextflow.enable.types = true

process REGISTER_PDB_COORDINATES {
    tag 'bounded-direct-pdb-coordinate-registration'
    label 'process_network'
    label 'needs_internet'
    label 'run_local'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    structural_hits: Path
    sequence_groups: Path
    database_manifest: Path
    maximum_hits_per_sequence_group: Integer
    maximum_mappings: Integer

    output:
    registration: Path = file('pdb_coordinate_registration')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search register-pdb-coordinates \
        --structural-hits '${structural_hits}' \
        --sequence-groups '${sequence_groups}' \
        --database-manifest '${database_manifest}' \
        --maximum-hits-per-sequence-group ${maximum_hits_per_sequence_group} \
        --maximum-mappings ${maximum_mappings} \
        --outdir pdb_coordinate_registration
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/pdb_coordinate_registration' \
        pdb_coordinate_registration
    """
}
