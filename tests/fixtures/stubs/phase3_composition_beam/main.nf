#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include {
    PHASE3_FULL_COMPOSITION_BEAM_WORKFLOW
} from '../../../../workflows/phase3_full_composition_beam_workflow'
include {
    PHASE3_NO_A_EXPANSION_WORKFLOW
} from '../../../../workflows/phase3_no_a_expansion_workflow'

params {
    fixture_root: Path
    outdir: Path = file('results')
    cache_root: Path = file('.cache')
}

workflow {
    def fixture = file(params.fixture_root)
    inputs = channel.of(
        tuple(
            'stub_crystal',
            file(fixture.resolve('parents.jsonl')),
            file(fixture.resolve('sequence_groups.jsonl')),
            file(fixture.resolve('localisation_policy.json')),
            file(fixture.resolve('active_wave_completion.json')),
            file(fixture.resolve('localisation_reopen_plan.json')),
            file(fixture.resolve('gel_evidence.json')),
            file(fixture.resolve('preflight.jsonl')),
            file(fixture.resolve('registry/all_model_registry.json')),
            file(fixture.resolve('model_ranking_evidence.jsonl')),
            file(fixture.resolve('diffraction_selection.json')),
            file(fixture.resolve('free_r_identity.json')),
            file(fixture.resolve('fixed')),
            file(fixture.resolve('execution_identity.json')),
            file(fixture.resolve('input.mtz')),
            file(fixture.resolve('phenix_manifest.json')),
            0,
            25,
            file(fixture.resolve('finding_closure.json')),
            file(fixture.resolve('finding_ledger.md')),
            file(fixture.resolve('adverse_review.json')),
            file(fixture.resolve('integration_gate.json')),
            file(fixture.resolve('known_controls.json')),
            file(fixture.resolve('m6.json')),
            file(fixture.resolve('unknown_pass1.json')),
            file(fixture.resolve('ci.json'))
        )
    )
    PHASE3_FULL_COMPOSITION_BEAM_WORKFLOW(
        inputs,
        'gtd-unknown-pass2-20260828T000000Z-aaaaaaaaaaaa-bbbbbbbb'
    )
    noA = channel.of(
        tuple(
            'stub_no_a_crystal',
            file(fixture.resolve('unknown_pass1.json')),
            file(fixture.resolve('no_a')),
            file(fixture.resolve('sequence_groups.jsonl')),
            file(fixture.resolve('registry/all_model_registry.json')),
            file(fixture.resolve('preflight.jsonl')),
            file(fixture.resolve('input.mtz')),
            file(fixture.resolve('diffraction_selection.json')),
            file(fixture.resolve('phenix_manifest.json')),
            file(fixture.resolve('execution_identity.json')),
            file(fixture.resolve('source_records.jsonl')),
            file(fixture.resolve('matthews.jsonl')),
            file(fixture.resolve('pipeline_config.yaml'))
        )
    )
    PHASE3_NO_A_EXPANSION_WORKFLOW(
        noA,
        'gtd-unknown-pass2-20260828T000000Z-aaaaaaaaaaaa-bbbbbbbb'
    )
}
