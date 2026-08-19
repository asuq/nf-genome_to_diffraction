nextflow.enable.types = true

process MERGE_PDB_PROVIDER_HITS {
    tag 'merge-pdb-provider-hits'
    label 'process_local'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    pdb_sequence_hits: Path
    foldseek_hits: Path

    stage:
    stageAs pdb_sequence_hits, 'pdb_sequence_hits.jsonl'
    stageAs foldseek_hits, 'foldseek_hits.jsonl'

    output:
    bundle: Path = file('pdb_provider_hits')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search merge-pdb-provider-hits \
        --pdb-sequence-hits '${pdb_sequence_hits}' \
        --foldseek-hits '${foldseek_hits}' \
        --outdir pdb_provider_hits
    """

    stub:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        structure-search merge-pdb-provider-hits \
        --pdb-sequence-hits '${pdb_sequence_hits}' \
        --foldseek-hits '${foldseek_hits}' \
        --outdir pdb_provider_hits
    """
}
