nextflow.enable.types = true

include { BUILD_MR_SEED_REVIEW } from '../modules/local/build_mr_seed_review'
include { ENUMERATE_MATTHEWS } from '../modules/local/enumerate_matthews'
include { IMPORT_CATALOGUES } from '../modules/local/import_catalogues'
include { MTZ_PREFLIGHT } from '../modules/local/mtz_preflight'
include { PREPARE_EXPERIMENTAL_MODELS } from '../modules/local/prepare_experimental_models'
include { PREPARE_PREDICTED_MODELS } from '../modules/local/prepare_predicted_models'
include { REGISTER_PDB_COORDINATES } from '../modules/local/register_pdb_coordinates'
include { SELECT_SINGLE_CRYSTAL } from '../modules/local/select_single_crystal'
include { STAGE_APPROVED_MR_SEEDS } from '../modules/local/stage_approved_mr_seeds'
include { STAGE_LIVE_T12 } from '../modules/local/stage_live_t12'
include { VALIDATE_TASK05_INPUTS } from '../modules/local/validate_task05_inputs'
include { ADDITIONAL_COPY_WORKFLOW } from './additional_copy_workflow'
include { BRIEF_REFINEMENT_WORKFLOW } from './brief_refinement_workflow'
include { DIVERSE_FIRST_COPY_MR_WORKFLOW } from './diverse_first_copy_mr_workflow'
include { PDB_SEQUENCE_DISCOVERY } from './pdb_sequence_discovery_workflow'

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
    analysis_stage: String
    approved_mr_seeds: Path?
    skip_xtriage: Boolean
    maximum_hits_per_query: Integer
    maximum_evalue: Float
    minimum_query_coverage: Float
    maximum_query_length: Integer
    prostt5_maximum_hits_per_query: Integer
    prostt5_maximum_evalue: Float
    prostt5_minimum_query_coverage: Float
    prostt5_maximum_query_length: Integer
    prostt5_maximum_queries: Integer
    prostt5_gpu: Boolean
    afdb_accession_map: Path?
    afdb_request_timeout_seconds: Float
    afdb_retry_count: Integer
    maximum_pdb_hits_per_sequence_group: Integer
    maximum_pdb_mappings: Integer
    maximum_first_copy_jobs: Integer

    main:
    validation_scope = VALIDATE_TASK05_INPUTS(
        catalogues,
        crystals,
        pipeline_config,
        database_manifest,
        phenix_manifest,
        cache_root,
        review_mode,
        profile_mode,
        analysis_stage
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

    if (analysis_stage in ['discovery', 'first_copy', 'additional_copy', 't12']) {
        sequence_groups = catalogue_bundle.map { Path bundle ->
            bundle.resolve('sequence_groups.jsonl')
        }
        source_records = catalogue_bundle.map { Path bundle ->
            bundle.resolve('source_records.jsonl')
        }
        discovery = PDB_SEQUENCE_DISCOVERY(
            sequence_groups,
            source_records,
            database_manifest,
            maximum_hits_per_query,
            maximum_evalue,
            minimum_query_coverage,
            maximum_query_length,
            prostt5_maximum_hits_per_query,
            prostt5_maximum_evalue,
            prostt5_minimum_query_coverage,
            prostt5_maximum_query_length,
            prostt5_maximum_queries,
            prostt5_gpu,
            afdb_accession_map,
            afdb_request_timeout_seconds,
            afdb_retry_count
        )
        direct_pdb_hits = discovery.pdb_sequence_search.map { Path bundle ->
            bundle.resolve('structural_hits.jsonl')
        }
        pdb_registration = REGISTER_PDB_COORDINATES(
            direct_pdb_hits,
            sequence_groups,
            database_manifest,
            maximum_pdb_hits_per_sequence_group,
            maximum_pdb_mappings
        )
        predicted_coordinate_sources = discovery.afdb_exact_search.map {
            Path bundle -> bundle.resolve('coordinate_sources.jsonl')
        }
        predicted_models = PREPARE_PREDICTED_MODELS(
            predicted_coordinate_sources,
            sequence_groups,
            phenix_manifest
        )
        pdb_coordinate_sources = pdb_registration.map { Path bundle ->
            bundle.resolve('coordinate_sources.jsonl')
        }
        coordinate_hit_mappings = pdb_registration.map { Path bundle ->
            bundle.resolve('coordinate_hit_mappings.jsonl')
        }
        experimental_models = PREPARE_EXPERIMENTAL_MODELS(
            pdb_coordinate_sources,
            coordinate_hit_mappings,
            sequence_groups
        )

        if (analysis_stage in ['first_copy', 'additional_copy', 't12']) {
            crystal_dispatch = SELECT_SINGLE_CRYSTAL(crystals, preflight_bundle)
            crystal_id = crystal_dispatch.map { Path bundle ->
                bundle.resolve('crystal_id.txt').toFile().text.trim()
            }
            selected_mtz = crystal_dispatch.map { Path bundle ->
                bundle.resolve('input.mtz')
            }
            matthews_jsonl = matthews_bundle.map { Path bundle ->
                bundle.resolve('matthews_hypotheses.jsonl')
            }
            preflight_jsonl = preflight_bundle.map { Path bundle ->
                bundle.resolve('mtz_preflight.jsonl')
            }
            first_copy = DIVERSE_FIRST_COPY_MR_WORKFLOW(
                predicted_coordinate_sources,
                predicted_models,
                pdb_coordinate_sources,
                coordinate_hit_mappings,
                experimental_models,
                sequence_groups,
                matthews_jsonl,
                preflight_jsonl,
                pipeline_config,
                crystal_id,
                maximum_first_copy_jobs,
                selected_mtz,
                phenix_manifest
            )
            mr_seed_review = BUILD_MR_SEED_REVIEW(
                first_copy.funnel,
                first_copy.results.collect(),
                sequence_groups,
                source_records,
                matthews_jsonl,
                pipeline_config
            )
            if (analysis_stage in ['additional_copy', 't12']) {
                if (approved_mr_seeds == null) {
                    error "${analysis_stage} stage requires approved MR seeds"
                }
                first_copy_hypotheses = first_copy.funnel.map { Path bundle ->
                    bundle.resolve('mr_hypotheses.jsonl')
                }
                approved_stage = STAGE_APPROVED_MR_SEEDS(
                    mr_seed_review,
                    approved_mr_seeds,
                    first_copy_hypotheses
                )
                additional_seeds = approved_stage.map { Path bundle ->
                    bundle.resolve('additional_copy_seeds.tsv')
                }
                review_validation = approved_stage.map { Path bundle ->
                    bundle.resolve('validated_mr_seed_decisions.json')
                }
                review_manifest = mr_seed_review.map { Path bundle ->
                    bundle.resolve('mr_seed_review_manifest.json')
                }
                additional_copy = ADDITIONAL_COPY_WORKFLOW(
                    additional_seeds,
                    review_validation,
                    review_manifest,
                    first_copy_hypotheses,
                    sequence_groups,
                    preflight_jsonl,
                    selected_mtz,
                    phenix_manifest
                )
                if (analysis_stage == 't12') {
                    copy_results = additional_copy
                        .collect()
                        .ifEmpty([])
                    live_t12_stage = STAGE_LIVE_T12(
                        approved_stage,
                        mr_seed_review,
                        copy_results,
                        first_copy_hypotheses,
                        sequence_groups,
                        source_records,
                        preflight_jsonl,
                        selected_mtz,
                        phenix_manifest
                    )
                    t12_finalists = live_t12_stage.map { Path bundle ->
                        bundle.resolve('finalists.tsv')
                    }
                    t12_sequence_groups = live_t12_stage.map { Path bundle ->
                        bundle.resolve('inputs/sequence_groups.jsonl')
                    }
                    t12_source_records = live_t12_stage.map { Path bundle ->
                        bundle.resolve('inputs/source_records.jsonl')
                    }
                    t12_phenix_manifest = live_t12_stage.map { Path bundle ->
                        bundle.resolve('inputs/phenix_manifest.json')
                    }
                    BRIEF_REFINEMENT_WORKFLOW(
                        t12_finalists,
                        t12_sequence_groups,
                        t12_source_records,
                        t12_phenix_manifest
                    )
                }
            }
        }
    }

    emit:
    scope: Path = validation_scope
    catalogue: Path = catalogue_bundle
    preflight: Path = preflight_bundle
    matthews: Path = matthews_bundle
}
