"""Focused Phase III diffraction-selection and identity regressions."""

from pathlib import Path

import pytest

from genome_to_diffraction.diffraction.selection import (
    DiffractionSelectionError,
    bind_phase3_hypothesis,
    build_diffraction_command_binding,
    build_diffraction_selection,
)
from genome_to_diffraction.schemas.manifests import CrystalEntry, PrototypeProfile
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    MtzObservationCandidateRecord,
    MtzPreflightRecord,
)
from genome_to_diffraction.schemas.v2.diffraction import (
    DiffractionCommandConsumer,
    DiffractionValueSource,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
_MANIFEST_SHA256 = "a" * 64


def _preflight(
    *,
    selected_dataset_id: int = 7,
    candidate_dataset_ids: tuple[int, ...] = (7,),
    resolution_high_a: float = 2.0,
    resolution_low_a: float = 20.0,
) -> MtzPreflightRecord:
    base = MtzPreflightRecord.model_validate_json(
        (STUBS / "mtz_preflight.jsonl").read_text(encoding="utf-8")
    )
    candidates = tuple(
        MtzObservationCandidateRecord(
            dataset_id=dataset_id,
            labels=("I", "SIGI"),
            observation_type="intensity",
        )
        for dataset_id in candidate_dataset_ids
    )
    payload = base.model_dump(mode="python")
    payload.update(
        {
            "selected_observation_dataset_id": selected_dataset_id,
            "observation_candidates": tuple(
                candidate.rendered_labels for candidate in candidates
            ),
            "observation_candidate_identities": candidates,
            "resolution_high_a": resolution_high_a,
            "resolution_low_a": resolution_low_a,
        }
    )
    return MtzPreflightRecord.model_validate(payload)


def _crystal(
    *,
    obs_labels: str | None = None,
    space_group_override: str | None = None,
    high_resolution_override: float | None = None,
    low_resolution_override: float | None = None,
) -> CrystalEntry:
    return CrystalEntry(
        crystal_id="test_crystal_01",
        mtz="input.mtz",
        catalogue_id="catalogue_test",
        obs_labels=obs_labels,
        space_group_override=space_group_override,
        high_resolution_override=high_resolution_override,
        low_resolution_override=low_resolution_override,
    )


def _hypothesis() -> MrHypothesis:
    return MrHypothesis(
        schema_version="1.0",
        hypothesis_id="mrhyp_" + "b" * 64,
        crystal_id="test_crystal_01",
        sequence_group_id="seq_" + "c" * 64,
        model_id="model_" + "d" * 64,
        copy_count_expected=2,
        copy_number_to_search=1,
        fixed_solution_id=None,
        space_group="P 21 21 21",
        obs_labels="I,SIGI",
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.PILOT,
        priority_features={"exact_sequence_mapping": True},
        status=MrHypothesisStatus.QUEUED,
    )


def test_selection_records_dataset_and_every_override_source() -> None:
    preflight = _preflight(resolution_high_a=1.8, resolution_low_a=18.0)
    crystal = _crystal(
        obs_labels="I,SIGI",
        space_group_override="P 21 21 21",
        high_resolution_override=1.8,
        low_resolution_override=18.0,
    )

    selection = build_diffraction_selection(
        crystal=crystal,
        preflight=preflight,
        crystal_manifest_sha256=_MANIFEST_SHA256,
    )

    assert selection.crystal_id == crystal.crystal_id
    assert selection.mtz_sha256 == preflight.mtz_sha256
    assert selection.observation_dataset_id == 7
    assert selection.observation_labels == ("I", "SIGI")
    assert selection.observation_type == "intensity"
    assert selection.selected_space_group == "P 21 21 21"
    assert selection.resolution_low_a == 18.0
    assert selection.resolution_high_a == 1.8
    assert (
        selection.observation_source is DiffractionValueSource.CRYSTAL_MANIFEST_OVERRIDE
    )
    assert (
        selection.space_group_source is DiffractionValueSource.CRYSTAL_MANIFEST_OVERRIDE
    )
    assert (
        selection.resolution_low_source
        is DiffractionValueSource.CRYSTAL_MANIFEST_OVERRIDE
    )
    assert (
        selection.resolution_high_source
        is DiffractionValueSource.CRYSTAL_MANIFEST_OVERRIDE
    )
    assert selection.free_r_membership_boundary.endswith("validation_pending")


def test_duplicate_rendered_labels_across_datasets_fail_closed() -> None:
    preflight = _preflight(candidate_dataset_ids=(7, 8))

    with pytest.raises(
        DiffractionSelectionError,
        match="exactly one MTZ dataset",
    ):
        build_diffraction_selection(
            crystal=_crystal(),
            preflight=preflight,
            crystal_manifest_sha256=_MANIFEST_SHA256,
        )


def test_selected_dataset_mismatch_fails_closed() -> None:
    preflight = _preflight(selected_dataset_id=7, candidate_dataset_ids=(8,))

    with pytest.raises(
        DiffractionSelectionError,
        match="candidate identity differs",
    ):
        build_diffraction_selection(
            crystal=_crystal(),
            preflight=preflight,
            crystal_manifest_sha256=_MANIFEST_SHA256,
        )


def test_override_value_must_match_preflight_selection() -> None:
    with pytest.raises(
        DiffractionSelectionError,
        match="high-resolution override differs",
    ):
        build_diffraction_selection(
            crystal=_crystal(high_resolution_override=1.9),
            preflight=_preflight(resolution_high_a=2.0),
            crystal_manifest_sha256=_MANIFEST_SHA256,
        )


def test_selection_mutation_changes_hypothesis_and_command_identities() -> None:
    first = build_diffraction_selection(
        crystal=_crystal(),
        preflight=_preflight(resolution_high_a=2.0),
        crystal_manifest_sha256=_MANIFEST_SHA256,
    )
    second = build_diffraction_selection(
        crystal=_crystal(),
        preflight=_preflight(resolution_high_a=1.8),
        crystal_manifest_sha256=_MANIFEST_SHA256,
    )
    hypothesis = _hypothesis()
    bound_first = bind_phase3_hypothesis(hypothesis, first)
    bound_second = bind_phase3_hypothesis(hypothesis, second)
    command_first = build_diffraction_command_binding(
        consumer=DiffractionCommandConsumer.FIRST_COPY_PHASER,
        command_owner_id=bound_first.hypothesis_id,
        selection=first,
    )
    command_second = build_diffraction_command_binding(
        consumer=DiffractionCommandConsumer.FIRST_COPY_PHASER,
        command_owner_id=bound_second.hypothesis_id,
        selection=second,
    )

    assert first.diffraction_selection_id != second.diffraction_selection_id
    assert bound_first.hypothesis_id != bound_second.hypothesis_id
    assert command_first.binding_id != command_second.binding_id
    assert command_first.observation_command_binding.startswith("explicit_parameter")
    assert command_first.space_group_command_binding == (
        "explicit_phaser_crystal_symmetry_parameter"
    )
    assert command_first.resolution_command_binding == (
        "explicit_phaser_resolution_low_high_parameters"
    )
