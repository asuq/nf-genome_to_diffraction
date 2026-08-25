nextflow.enable.types = true

process PREPARE_EXPERIMENTAL_MODELS {
    tag 'bounded-cleaned-pdb-source-chain-models'
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    coordinate_sources: Path
    coordinate_hit_mappings: Path
    registration_manifest: Path?
    sequence_groups: Path

    output:
    preparation: Path = file('experimental_model_preparation')

    script:
    """
    args=(
        --coordinate-sources '${coordinate_sources}'
        --coordinate-hit-mappings '${coordinate_hit_mappings}'
        --sequence-groups '${sequence_groups}'
        --outdir experimental_model_preparation
    )
    if [[ -n '${registration_manifest ?: ''}' ]]; then
        args+=(--registration-manifest '${registration_manifest ?: ''}')
    fi

    genome-to-diffraction \
        --no-progress \
        --log-format json \
        model prepare-experimental \
        "\${args[@]}"
    """

    stub:
    """
    cp -R '${projectDir}/tests/fixtures/stubs/experimental_model_preparation' \
        experimental_model_preparation
    """
}
