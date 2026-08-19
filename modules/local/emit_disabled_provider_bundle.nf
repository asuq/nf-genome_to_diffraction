nextflow.enable.types = true

process EMIT_DISABLED_PROVIDER_BUNDLE {
    tag "disabled-provider:${provider_key}"
    label 'process_local'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    provider_key: String
    bundle_name: String
    sequence_groups: Path
    provider_entry: Path

    output:
    search: Path = file("${bundle_name}")

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search emit-disabled-provider \
        --provider-entry '${provider_entry}' \
        --sequence-groups '${sequence_groups}' \
        --outdir '${bundle_name}'
    """

    stub:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search emit-disabled-provider \
        --provider-entry '${provider_entry}' \
        --sequence-groups '${sequence_groups}' \
        --outdir '${bundle_name}'
    """
}
