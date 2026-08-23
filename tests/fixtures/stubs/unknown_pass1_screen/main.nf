#!/usr/bin/env nextflow

nextflow.enable.dsl = 2
nextflow.enable.types = true

include {
    UNKNOWN_PASS1_SCREEN_WORKFLOW
} from '../../../../workflows/unknown_pass1_screen_workflow'

process PREPARE_SHARED_UNKNOWN_CATALOGUE_FIXTURE {
    tag 'unknown-pass1-shared-catalogue'

    input:
    seed: Path

    output:
    bundle: Path = file('shared_unknown_catalogue')

    script:
    """
    mkdir -p shared_unknown_catalogue
    cp '${seed}' shared_unknown_catalogue/catalogue_preparation.json
    """

    stub:
    """
    mkdir -p shared_unknown_catalogue
    cp '${seed}' shared_unknown_catalogue/catalogue_preparation.json
    """
}


process PREPARE_SHARED_UNKNOWN_PROVIDER_FIXTURE {
    tag 'unknown-pass1-shared-provider'

    input:
    seed: Path

    output:
    bundle: Path = file('shared_unknown_provider')

    script:
    """
    mkdir -p shared_unknown_provider
    cp '${seed}' shared_unknown_provider/provider_preparation.json
    """

    stub:
    """
    mkdir -p shared_unknown_provider
    cp '${seed}' shared_unknown_provider/provider_preparation.json
    """
}


process PREPARE_SHARED_UNKNOWN_LOCALISATION_FIXTURE {
    tag 'unknown-pass1-shared-localisation'

    input:
    seed: Path

    output:
    bundle: Path = file('shared_unknown_localisation')

    script:
    """
    mkdir -p shared_unknown_localisation
    cp '${seed}' shared_unknown_localisation/localisation_preparation.json
    """

    stub:
    """
    mkdir -p shared_unknown_localisation
    cp '${seed}' shared_unknown_localisation/localisation_preparation.json
    """
}


process PREPARE_CRYSTALLOGRAPHIC_REVIEW_STAGE_FIXTURE {
    tag 'unknown-pass1-crystallographic-review-stage'

    input:
    seed: Path

    output:
    stage: Path = file('crystallographic_review_stage')

    script:
    """
    cp -R '${seed}' crystallographic_review_stage
    """

    stub:
    """
    cp -R '${seed}' crystallographic_review_stage
    """
}


workflow {
    main:
    inputRoot = file("${launchDir}/inputs")
    catalogue = PREPARE_SHARED_UNKNOWN_CATALOGUE_FIXTURE(
        channel.value(file("${inputRoot}/catalogue_preparation.json"))
    )
    provider = PREPARE_SHARED_UNKNOWN_PROVIDER_FIXTURE(
        channel.value(file("${inputRoot}/provider_preparation.json"))
    )
    localisation = PREPARE_SHARED_UNKNOWN_LOCALISATION_FIXTURE(
        channel.value(file("${inputRoot}/localisation_preparation.json"))
    )
    review = PREPARE_CRYSTALLOGRAPHIC_REVIEW_STAGE_FIXTURE(
        channel.value(file("${inputRoot}/review_stage"))
    )
    crystalRecordItems = channel
        .fromPath("${inputRoot}/crystal_items/*.json", checkIfExists: true)
        .map { record ->
            def parts = record.baseName.tokenize('--')
            tuple(parts[0], parts[1], record)
        }
    hypothesisRecordItems = channel
        .fromPath("${inputRoot}/hypothesis_tasks/*.json", checkIfExists: true)
        .map { record ->
            def parts = record.baseName.tokenize('--')
            tuple(parts[0], parts[1], parts[2] as Integer, record)
        }
    mtzItems = channel
        .fromPath("${inputRoot}/crystal_mtz/*.mtz", checkIfExists: true)
        .map { mtz -> tuple(mtz.baseName, mtz) }
    modelItems = channel
        .fromPath("${inputRoot}/models/*.pdb", checkIfExists: true)
        .map { model -> tuple(model.baseName, model) }
    UNKNOWN_PASS1_SCREEN_WORKFLOW(
        channel.value(file("${inputRoot}/unknown_pass1_screen_inventory.json")),
        channel.value(file("${inputRoot}/phase3_execution_identity.json")),
        review,
        catalogue,
        provider,
        localisation,
        crystalRecordItems,
        hypothesisRecordItems,
        mtzItems,
        modelItems
    )
}
