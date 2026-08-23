nextflow.enable.types = true

include { DISPATCH_CRYSTAL_ITEM } from '../modules/local/dispatch_crystal_item'

// Expand a validated crystal manifest into complete per-crystal items. Chained
// `combine` operators deliberately form a Cartesian product with each singleton
// shared preparation. This broadcasts those immutable bundles to every crystal
// instead of consuming them alongside only the first crystal queue item.
workflow CRYSTAL_FANOUT_WORKFLOW {
    take:
    crystals: Path
    preflight: Path
    catalogue_bundle: Path
    provider_bundle: Path

    main:
    crystal_ids = crystals
        .splitJson(path: 'crystals')
        .map { entry -> tuple(entry.crystal_id as String) }
    complete_items = crystal_ids
        .combine(crystals)
        .combine(preflight)
        .combine(catalogue_bundle)
        .combine(provider_bundle)
    dispatched = DISPATCH_CRYSTAL_ITEM(complete_items)

    emit:
    items: Tuple = dispatched
}
