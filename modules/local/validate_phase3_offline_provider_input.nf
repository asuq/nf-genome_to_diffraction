nextflow.enable.types = true

// Re-authenticate the discovery package, bounded login preparation, and exact
// execution identity before any offline model preparation or Phaser task.
process VALIDATE_PHASE3_OFFLINE_PROVIDER_INPUT {
    tag 'phase3-offline-provider-input'
    label 'process_low'
    stageInMode 'copy'

    input:
    discovery_package: Path
    provider_preparation: Path
    execution_identity: Path

    output:
    authority: Path = file('phase3_offline_provider_input')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search validate-phase3-offline-provider-input \
        --discovery-package '${discovery_package}' \
        --provider-preparation '${provider_preparation}' \
        --execution-identity '${execution_identity}' \
        --outdir phase3_offline_provider_input
    """

    stub:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search validate-phase3-offline-provider-input \
        --discovery-package '${discovery_package}' \
        --provider-preparation '${provider_preparation}' \
        --execution-identity '${execution_identity}' \
        --outdir phase3_offline_provider_input
    """
}
