#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include {
    PHASE3_MULTICRYSTAL_FIRST_COPY_WORKFLOW
} from '../../../../workflows/phase3_multicrystal_first_copy_workflow'

params {
    crystals: Path
    preflight: Path
    sequence_groups: Path
    source_records: Path
    predicted_coordinate_sources: Path
    predicted_prepared_models: Path
    pdb_coordinate_sources: Path
    coordinate_hit_mappings: Path
    experimental_prepared_models: Path
    matthews: Path
    pipeline_config: Path
    phenix_manifest: Path
    phase3_crystallographic_review_stage: Path? = null
    phase3_execution_identity: Path? = null
    phase3_owned_parent_run_id: String? = null
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}


process PREPARE_PHASE3_SHARED_CATALOGUE_FIXTURE {
    tag 'phase3-shared-catalogue'

    input:
    sequence_groups: Path
    source_records: Path

    output:
    bundle: Path = file('phase3_shared_catalogue')

    script:
    """
    mkdir -p phase3_shared_catalogue
    cp '${sequence_groups}' phase3_shared_catalogue/sequence_groups.jsonl
    cp '${source_records}' phase3_shared_catalogue/source_records.jsonl
    """

    stub:
    """
    mkdir -p phase3_shared_catalogue
    cp '${sequence_groups}' phase3_shared_catalogue/sequence_groups.jsonl
    cp '${source_records}' phase3_shared_catalogue/source_records.jsonl
    """
}


process PREPARE_PHASE3_SHARED_PROVIDER_FIXTURE {
    tag 'phase3-shared-provider'

    input:
    coordinate_sources: Path

    output:
    bundle: Path = file('phase3_shared_provider')

    script:
    """
    mkdir -p phase3_shared_provider
    cp '${coordinate_sources}' phase3_shared_provider/coordinate_sources.jsonl
    """

    stub:
    """
    mkdir -p phase3_shared_provider
    cp '${coordinate_sources}' phase3_shared_provider/coordinate_sources.jsonl
    """
}


workflow {
    main:
    catalogue = PREPARE_PHASE3_SHARED_CATALOGUE_FIXTURE(
        channel.value(params.sequence_groups),
        channel.value(params.source_records)
    )
    provider = PREPARE_PHASE3_SHARED_PROVIDER_FIXTURE(
        channel.value(params.pdb_coordinate_sources)
    )
    PHASE3_MULTICRYSTAL_FIRST_COPY_WORKFLOW(
        channel.value(params.crystals),
        channel.value(params.preflight),
        catalogue,
        provider,
        channel.value(params.predicted_coordinate_sources),
        channel.value(params.predicted_prepared_models),
        channel.value(params.pdb_coordinate_sources),
        channel.value(params.coordinate_hit_mappings),
        channel.value(params.experimental_prepared_models),
        channel.value(params.matthews),
        channel.value(params.pipeline_config),
        25,
        channel.value(params.phenix_manifest),
        params.phase3_crystallographic_review_stage,
        params.phase3_execution_identity,
        params.phase3_owned_parent_run_id
    )
}
