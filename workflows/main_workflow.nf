nextflow.enable.types = true

include { FOUNDATION_MAIN_STUB } from '../modules/local/foundation_main_stub'

workflow MAIN_WORKFLOW {
    take:
    catalogues: Path
    crystals: Path
    pipeline_config: Path
    database_manifest: Path
    phenix_manifest: Path
    cache_root: String
    review_mode: String
    profile_mode: String

    main:
    foundation_bundle = FOUNDATION_MAIN_STUB(
        catalogues,
        crystals,
        pipeline_config,
        database_manifest,
        phenix_manifest,
        cache_root,
        review_mode,
        profile_mode
    )

    emit:
    bundle: Path = foundation_bundle
}
