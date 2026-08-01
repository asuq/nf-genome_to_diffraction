nextflow.enable.types = true

include { ENUMERATE_MATTHEWS } from '../modules/local/enumerate_matthews'
include { IMPORT_CATALOGUES } from '../modules/local/import_catalogues'
include { MTZ_PREFLIGHT } from '../modules/local/mtz_preflight'
include { VALIDATE_TASK05_INPUTS } from '../modules/local/validate_task05_inputs'

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
    skip_xtriage: Boolean

    main:
    validation_scope = VALIDATE_TASK05_INPUTS(
        catalogues,
        crystals,
        pipeline_config,
        database_manifest,
        phenix_manifest,
        cache_root,
        review_mode,
        profile_mode
    )
    catalogue_bundle = IMPORT_CATALOGUES(
        catalogues,
        pipeline_config,
        validation_scope
    )
    preflight_bundle = MTZ_PREFLIGHT(
        crystals,
        phenix_manifest,
        skip_xtriage,
        validation_scope
    )
    matthews_bundle = ENUMERATE_MATTHEWS(
        crystals,
        pipeline_config,
        preflight_bundle,
        catalogue_bundle
    )

    emit:
    scope: Path = validation_scope
    catalogue: Path = catalogue_bundle
    preflight: Path = preflight_bundle
    matthews: Path = matthews_bundle
}
