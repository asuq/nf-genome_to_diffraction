nextflow.enable.types = true

include {
    PHASE3_COMPOSITION_DEPTH_WORKFLOW as PHASE3_COMPOSITION_DEPTH_B
} from './phase3_composition_beam_workflow'
include {
    PHASE3_COMPOSITION_DEPTH_WORKFLOW as PHASE3_COMPOSITION_DEPTH_C
} from './phase3_composition_beam_workflow'
include {
    PHASE3_COMPOSITION_DEPTH_WORKFLOW as PHASE3_COMPOSITION_DEPTH_D
} from './phase3_composition_beam_workflow'
include {
    PHASE3_COMPOSITION_DEPTH_WORKFLOW as PHASE3_COMPOSITION_DEPTH_E
} from './phase3_composition_beam_workflow'
include {
    PHASE3_COMPOSITION_DEPTH_WORKFLOW as PHASE3_COMPOSITION_DEPTH_F
} from './phase3_composition_beam_workflow'
include {
    BUILD_PHASE3_PASS2_REVIEW_PACKAGES
} from '../modules/local/phase3_composition_beam_tasks'

workflow PHASE3_FULL_COMPOSITION_BEAM_WORKFLOW {
    take:
    initial_depth_inputs: Tuple
    owned_parent_run_id: String

    main:
    depthB = PHASE3_COMPOSITION_DEPTH_B(initial_depth_inputs)
    terminalB = depthB.filter { crystalId, beam, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            beam.resolve('composition_beam_depth_result.json').toFile().text
        )
        record.status == 'terminal'
    }
    nextC = depthB.filter { crystalId, beam, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            beam.resolve('composition_beam_depth_result.json').toFile().text
        )
        record.status == 'ready_next_depth'
    }.map { crystalId, beam, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            beam.resolve('composition_beam_depth_result.json').toFile().text
        )
        tuple(
            crystalId,
            file(beam.resolve('retained_parent_states.jsonl')),
            sourceItem[2], sourceItem[3], sourceItem[4], sourceItem[5],
            sourceItem[6], sourceItem[7], sourceItem[8], sourceItem[9],
            sourceItem[10], sourceItem[11], beam, sourceItem[13],
            sourceItem[14], sourceItem[15],
            record.global_attempts_used_after as Integer, 25,
            sourceItem[18], sourceItem[19], sourceItem[20], sourceItem[21],
            sourceItem[22], sourceItem[23], sourceItem[24], sourceItem[25]
        )
    }

    depthC = PHASE3_COMPOSITION_DEPTH_C(nextC)
    terminalC = depthC.filter { crystalId, beam, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            beam.resolve('composition_beam_depth_result.json').toFile().text
        )
        record.status == 'terminal'
    }
    nextD = depthC.filter { crystalId, beam, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            beam.resolve('composition_beam_depth_result.json').toFile().text
        )
        record.status == 'ready_next_depth'
    }.map { crystalId, beam, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            beam.resolve('composition_beam_depth_result.json').toFile().text
        )
        tuple(
            crystalId,
            file(beam.resolve('retained_parent_states.jsonl')),
            sourceItem[2], sourceItem[3], sourceItem[4], sourceItem[5],
            sourceItem[6], sourceItem[7], sourceItem[8], sourceItem[9],
            sourceItem[10], sourceItem[11], beam, sourceItem[13],
            sourceItem[14], sourceItem[15],
            record.global_attempts_used_after as Integer, 25,
            sourceItem[18], sourceItem[19], sourceItem[20], sourceItem[21],
            sourceItem[22], sourceItem[23], sourceItem[24], sourceItem[25]
        )
    }

    depthD = PHASE3_COMPOSITION_DEPTH_D(nextD)
    terminalD = depthD.filter { crystalId, beam, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            beam.resolve('composition_beam_depth_result.json').toFile().text
        )
        record.status == 'terminal'
    }
    nextE = depthD.filter { crystalId, beam, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            beam.resolve('composition_beam_depth_result.json').toFile().text
        )
        record.status == 'ready_next_depth'
    }.map { crystalId, beam, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            beam.resolve('composition_beam_depth_result.json').toFile().text
        )
        tuple(
            crystalId,
            file(beam.resolve('retained_parent_states.jsonl')),
            sourceItem[2], sourceItem[3], sourceItem[4], sourceItem[5],
            sourceItem[6], sourceItem[7], sourceItem[8], sourceItem[9],
            sourceItem[10], sourceItem[11], beam, sourceItem[13],
            sourceItem[14], sourceItem[15],
            record.global_attempts_used_after as Integer, 25,
            sourceItem[18], sourceItem[19], sourceItem[20], sourceItem[21],
            sourceItem[22], sourceItem[23], sourceItem[24], sourceItem[25]
        )
    }

    depthE = PHASE3_COMPOSITION_DEPTH_E(nextE)
    terminalE = depthE.filter { crystalId, beam, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            beam.resolve('composition_beam_depth_result.json').toFile().text
        )
        record.status == 'terminal'
    }
    nextF = depthE.filter { crystalId, beam, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            beam.resolve('composition_beam_depth_result.json').toFile().text
        )
        record.status == 'ready_next_depth'
    }.map { crystalId, beam, sourceItem ->
        def record = new groovy.json.JsonSlurper().parseText(
            beam.resolve('composition_beam_depth_result.json').toFile().text
        )
        tuple(
            crystalId,
            file(beam.resolve('retained_parent_states.jsonl')),
            sourceItem[2], sourceItem[3], sourceItem[4], sourceItem[5],
            sourceItem[6], sourceItem[7], sourceItem[8], sourceItem[9],
            sourceItem[10], sourceItem[11], beam, sourceItem[13],
            sourceItem[14], sourceItem[15],
            record.global_attempts_used_after as Integer, 25,
            sourceItem[18], sourceItem[19], sourceItem[20], sourceItem[21],
            sourceItem[22], sourceItem[23], sourceItem[24], sourceItem[25]
        )
    }

    depthF = PHASE3_COMPOSITION_DEPTH_F(nextF)
    terminal = terminalB.mix(terminalC, terminalD, terminalE, depthF)
    review_packages = BUILD_PHASE3_PASS2_REVIEW_PACKAGES(
        terminal,
        owned_parent_run_id
    )

    emit:
    terminal_results: Tuple = terminal
    review_packages: Tuple = review_packages
}
