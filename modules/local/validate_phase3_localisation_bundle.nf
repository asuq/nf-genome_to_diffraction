nextflow.enable.types = true

/* Validate complete local localisation/gel evidence without changing bytes. */

process VALIDATE_PHASE3_LOCALISATION_BUNDLE {
    tag 'phase3-localisation-bundle'
    label 'process_low'
    stageInMode 'copy'

    input:
    localisation_bundle: Path

    output:
    bundle: Path = file('phase3_localisation_bundle')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        localisation stage-batch \
        --bundle '${localisation_bundle}' \
        --outdir phase3_localisation_bundle
    """

    stub:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        localisation stage-batch \
        --bundle '${localisation_bundle}' \
        --outdir phase3_localisation_bundle
    """
}
