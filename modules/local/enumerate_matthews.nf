nextflow.enable.types = true

process ENUMERATE_MATTHEWS {
    tag 'candidate-copy-hypotheses'
    label 'process_low'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    crystals: Path
    pipeline_config: Path
    preflight: Path
    catalogue: Path

    output:
    matthews: Path = file('matthews')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        matthews enumerate \
        --crystals '${crystals}' \
        --config '${pipeline_config}' \
        --preflight '${preflight}/mtz_preflight.jsonl' \
        --sequence-groups '${catalogue}/sequence_groups.jsonl' \
        --source-records '${catalogue}/source_records.jsonl' \
        --outdir matthews
    """

    stub:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        matthews enumerate \
        --crystals '${crystals}' \
        --config '${pipeline_config}' \
        --preflight '${preflight}/mtz_preflight.jsonl' \
        --sequence-groups '${catalogue}/sequence_groups.jsonl' \
        --source-records '${catalogue}/source_records.jsonl' \
        --outdir matthews
    """
}
