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

// Reviewed Phase III continuation still owns exactly one crystal at this
// boundary, but must retain its dataset-qualified observations and raw Free-R
// identity before any later same-component refinement can be scheduled.
process SELECT_PHASE3_SINGLE_CRYSTAL {
    tag 'phase3-single-crystal-mr-dispatch'
    label 'process_single'
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    crystals: Path
    preflight: Path

    output:
    dispatch: Path = file('selected_phase3_crystal')

    script:
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        diffraction select-single \
        --crystals '${crystals}' \
        --preflight '${preflight}/mtz_preflight.jsonl' \
        --phase3-diffraction \
        --outdir selected_phase3_crystal
    """

    stub:
    """
    mkdir -p selected_phase3_crystal
    cp \
        '${projectDir}/tests/fixtures/stubs/predicted_model_preparation/models/stub.pdb' \
        selected_phase3_crystal/input.mtz
    printf '%s\n' 'test_crystal_01' > selected_phase3_crystal/crystal_id.txt
    printf '%s\n' '{}' > selected_phase3_crystal/phase3_diffraction_selection.json
    printf '%s\n' '{}' > selected_phase3_crystal/phase3_free_r_identity.json
    printf '%s\n' \
        '{"schema_version":"1.0","dispatch_id":"crdispatch_stub","crystal_id":"test_crystal_01","catalogue_id":"example_archaeon_refseq","crystal_manifest_sha256":"0000000000000000000000000000000000000000000000000000000000000000","preflight_jsonl_sha256":"0000000000000000000000000000000000000000000000000000000000000000","preflight_id":"preflight_stub","mtz_sha256":"0000000000000000000000000000000000000000000000000000000000000000","staged_mtz":"input.mtz","stub":true}' \
        > selected_phase3_crystal/crystal_dispatch.json
    """
}
