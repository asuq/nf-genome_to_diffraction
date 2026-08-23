nextflow.enable.types = true

// Phase III per-crystal dispatch boundary. Each input tuple is complete:
// crystal ID, full manifest, completed preflight evidence, shared catalogue
// preparation, and shared provider preparation. The two shared bundles are
// deliberately carried through the output so downstream stages never pair an
// independent crystal stream with consumable singleton channels.
//
// The Python adapter verifies the selected manifest/preflight/MTZ identity and
// fails on contract, checksum, or preflight ineligibility. The Nextflow task
// hash is the cache key and includes every tuple member. Unit adapter coverage
// and the focused three-crystal cached-resume stub protect this boundary.
process DISPATCH_CRYSTAL_ITEM {
    tag "crystal-dispatch:${item[0]}"
    label 'process_single'

    input:
    item: Tuple

    output:
    result: Tuple = tuple(
        item[0],
        file("crystal_dispatch_${item[0]}"),
        item[3],
        item[4]
    )

    script:
    def outputName = "crystal_dispatch_${item[0]}"
    """
    genome-to-diffraction \
        --no-progress \
        --log-format json \
        diffraction select-single \
        --crystals '${item[1]}' \
        --preflight '${item[2]}' \
        --crystal-id '${item[0]}' \
        --outdir '${outputName}'
    """

    stub:
    def outputName = "crystal_dispatch_${item[0]}"
    """
    mkdir -p '${outputName}'
    printf '%s\n' 'stub-mtz' > '${outputName}/input.mtz'
    printf '%s\n' '${item[0]}' > '${outputName}/crystal_id.txt'
    printf '%s\n' \
        '{"schema_version":"1.0","dispatch_id":"crdispatch_${item[0]}","crystal_id":"${item[0]}","catalogue_id":"stub_catalogue","crystal_manifest_sha256":"0000000000000000000000000000000000000000000000000000000000000000","preflight_jsonl_sha256":"0000000000000000000000000000000000000000000000000000000000000000","preflight_id":"preflight_${item[0]}","mtz_sha256":"0000000000000000000000000000000000000000000000000000000000000000","staged_mtz":"input.mtz","stub":true}' \
        > '${outputName}/crystal_dispatch.json'
    """
}
