nextflow.enable.types = true

process IMPORT_CATALOGUES {
    tag 'trusted-protein-catalogues'
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    catalogues: Path
    pipeline_config: Path
    validation_scope: Path

    output:
    catalogue: Path = file('catalogue')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        catalogue import \
        --catalogues '${catalogues}' \
        --config '${pipeline_config}' \
        --outdir catalogue
    """

    stub:
    """
    mkdir -p catalogue
    cp '${projectDir}/tests/fixtures/stubs/sequence_groups.jsonl' catalogue/sequence_groups.jsonl
    cp '${projectDir}/tests/fixtures/stubs/source_records.jsonl' catalogue/source_records.jsonl
    printf '%s\n' '>seq_f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e' 'ACDE' > catalogue/exact_sequences.faa
    """
}
