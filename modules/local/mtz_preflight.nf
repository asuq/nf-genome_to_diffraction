nextflow.enable.types = true

process MTZ_PREFLIGHT {
    tag 'mtz-preflight'
    label 'process_phenix'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    crystals: Path
    phenix_manifest: Path
    skip_xtriage: Boolean
    validation_scope: Path

    output:
    preflight: Path = file('preflight')

    script:
    def skipArgument = skip_xtriage ? '--skip-xtriage' : ''
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        diffraction preflight \
        --crystals '${crystals}' \
        --phenix-manifest '${phenix_manifest}' \
        --outdir preflight \
        ${skipArgument}
    """

    stub:
    """
    mkdir -p preflight
    cp '${projectDir}/tests/fixtures/stubs/mtz_preflight.jsonl' preflight/mtz_preflight.jsonl
    printf '%s\n' '# Stub MTZ preflight' > preflight/preflight_report.md
    """
}
