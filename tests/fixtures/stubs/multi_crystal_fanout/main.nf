#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include { CRYSTAL_FANOUT_WORKFLOW } from '../../../../workflows/crystal_fanout_workflow'

params {
    crystals: Path
    preflight: Path
    catalogue_seed: Path
    provider_seed: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

process PREPARE_SHARED_CATALOGUE_FIXTURE {
    tag 'shared-catalogue'

    input:
    seed: Path

    output:
    bundle: Path = file('shared_catalogue')

    script:
    """
    mkdir -p shared_catalogue
    cp '${seed}' shared_catalogue/catalogue.marker
    """

    stub:
    """
    mkdir -p shared_catalogue
    cp '${seed}' shared_catalogue/catalogue.marker
    """
}

process PREPARE_SHARED_PROVIDER_FIXTURE {
    tag 'shared-provider'

    input:
    seed: Path

    output:
    bundle: Path = file('shared_provider')

    script:
    """
    mkdir -p shared_provider
    cp '${seed}' shared_provider/provider.marker
    """

    stub:
    """
    mkdir -p shared_provider
    cp '${seed}' shared_provider/provider.marker
    """
}

process RECORD_COMPLETE_CRYSTAL_ITEM_FIXTURE {
    tag "complete-crystal:${item[0]}"
    publishDir params.outdir, mode: 'copy', overwrite: true

    input:
    item: Tuple

    output:
    evidence: Path = file("complete_crystal_${item[0]}")

    script:
    def outputName = "complete_crystal_${item[0]}"
    """
    mkdir -p '${outputName}'
    cp '${item[1]}/crystal_dispatch.json' '${outputName}/crystal_dispatch.json'
    cp '${item[1]}/crystal_id.txt' '${outputName}/crystal_id.txt'
    cp '${item[2]}/catalogue.marker' '${outputName}/catalogue.marker'
    cp '${item[3]}/provider.marker' '${outputName}/provider.marker'
    """

    stub:
    def outputName = "complete_crystal_${item[0]}"
    """
    mkdir -p '${outputName}'
    cp '${item[1]}/crystal_dispatch.json' '${outputName}/crystal_dispatch.json'
    cp '${item[1]}/crystal_id.txt' '${outputName}/crystal_id.txt'
    cp '${item[2]}/catalogue.marker' '${outputName}/catalogue.marker'
    cp '${item[3]}/provider.marker' '${outputName}/provider.marker'
    """
}

workflow {
    main:
    catalogue = PREPARE_SHARED_CATALOGUE_FIXTURE(
        channel.value(params.catalogue_seed)
    )
    provider = PREPARE_SHARED_PROVIDER_FIXTURE(
        channel.value(params.provider_seed)
    )
    fanout = CRYSTAL_FANOUT_WORKFLOW(
        channel.value(params.crystals),
        channel.value(params.preflight),
        catalogue,
        provider
    )
    RECORD_COMPLETE_CRYSTAL_ITEM_FIXTURE(fanout)
}
