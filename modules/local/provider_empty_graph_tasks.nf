nextflow.enable.types = true

// The enabled branch is deliberately stub-only. A normal run fails before any
// provider executable or network route can be reached.
process STUB_LOCAL_PROVIDER_NO_HIT {
    tag 'provider-empty:pdb_sequence:enabled-no-hit'
    label 'process_local'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    provider_plan: Path
    provider_entry: Path
    database_manifest: Path
    sequence_groups: Path
    stub_helper: Path

    output:
    bundle: Path = file('pdb_sequence_search')

    script:
    """
    printf '%s\n' 'provider-empty enabled route is stub-only' >&2
    exit 64
    """

    stub:
    """
    python '${stub_helper}' \
        --provider-plan '${provider_plan}' \
        --provider-entry '${provider_entry}' \
        --database-manifest '${database_manifest}' \
        --sequence-groups '${sequence_groups}' \
        --outdir pdb_sequence_search
    """
}


process COMPLETE_PROVIDER_EMPTY_GRAPH {
    tag 'provider-empty:completed-no-model'
    label 'process_local'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    pipeline_config: Path
    provider_plan: Path
    sequence_groups: Path
    bundles: Tuple

    output:
    completion: Path = file('provider_empty_graph_completion')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search complete-provider-empty-graph \
        --config '${pipeline_config}' \
        --provider-plan '${provider_plan}' \
        --sequence-groups '${sequence_groups}' \
        --bundle '${bundles[0]}' \
        --bundle '${bundles[1]}' \
        --bundle '${bundles[2]}' \
        --bundle '${bundles[3]}' \
        --outdir provider_empty_graph_completion
    """

    stub:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search complete-provider-empty-graph \
        --config '${pipeline_config}' \
        --provider-plan '${provider_plan}' \
        --sequence-groups '${sequence_groups}' \
        --bundle '${bundles[0]}' \
        --bundle '${bundles[1]}' \
        --bundle '${bundles[2]}' \
        --bundle '${bundles[3]}' \
        --outdir provider_empty_graph_completion
    """
}
