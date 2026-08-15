nextflow.enable.types = true

// Resolve one crystal and MTZ exclusively from the validated manifest. The
// Python adapter verifies the preflight identity/checksum and copies the MTZ
// into a deterministic dispatch bundle for downstream MR tasks.
process SELECT_SINGLE_CRYSTAL {
    tag 'single-crystal-mr-dispatch'
    label 'process_single'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    crystals: Path
    preflight: Path

    output:
    dispatch: Path = file('selected_crystal')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        diffraction select-single \
        --crystals '${crystals}' \
        --preflight '${preflight}/mtz_preflight.jsonl' \
        --outdir selected_crystal
    """

    stub:
    """
    mkdir -p selected_crystal
    cp \
        '${projectDir}/tests/fixtures/stubs/predicted_model_preparation/models/stub.pdb' \
        selected_crystal/input.mtz
    printf '%s\n' 'test_crystal_01' > selected_crystal/crystal_id.txt
    printf '%s\n' \
        '{"schema_version":"1.0","dispatch_id":"crdispatch_stub","crystal_id":"test_crystal_01","catalogue_id":"example_archaeon_refseq","crystal_manifest_sha256":"0000000000000000000000000000000000000000000000000000000000000000","preflight_jsonl_sha256":"0000000000000000000000000000000000000000000000000000000000000000","preflight_id":"preflight_stub","mtz_sha256":"0000000000000000000000000000000000000000000000000000000000000000","staged_mtz":"input.mtz","stub":true}' \
        > selected_crystal/crystal_dispatch.json
    """
}
