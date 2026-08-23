"""Focused tests for the fixed Phase III unknown-pass-1 screen boundary."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.execution.unknown_screen import (
    UnknownPass1ModelInput,
    UnknownPass1ScreenError,
    build_unknown_pass1_screen_inventory,
    load_unknown_pass1_screen_inventory,
    write_unknown_pass1_screen_inventory,
)
from genome_to_diffraction.schemas.v2 import (
    UnknownPass1AHypothesis,
    UnknownPass1AHypothesisDisposition,
    UnknownPass1CrystalBranch,
    UnknownPass1ReviewBinding,
    UnknownPass1ReviewStageIndex,
    UnknownPass1ScreenInventory,
)

from ..support.unknown_pass1_fixture import (
    PUBLIC_STUB_CRYSTAL_IDS,
    UnknownPass1PublicFixture,
    materialise_unknown_pass1_public_fixture,
    public_stub_hypothesis,
    public_stub_model_bytes,
)


def _build(fixture: UnknownPass1PublicFixture):
    return build_unknown_pass1_screen_inventory(
        execution_identity_path=fixture.execution_identity,
        review_stage_index_path=fixture.review_stage_index,
        shared_preparation_input=fixture.shared_preparation,
        crystals=fixture.crystals,
    )


def test_builds_exact_three_crystal_and_25_task_inventory(tmp_path: Path) -> None:
    inventory = _build(materialise_unknown_pass1_public_fixture(tmp_path))

    assert inventory.crystal_count == 3
    assert tuple(binding.crystal_id for binding in inventory.review_bindings) == (
        PUBLIC_STUB_CRYSTAL_IDS
    )
    assert len(inventory.review_decisions) == 3
    assert inventory.ready_count == 1
    assert inventory.held_count == 1
    assert inventory.empty_no_model_count == 1
    assert inventory.empty_no_hypotheses_count == 0
    assert inventory.hypothesis_task_count == 25
    assert tuple(item.branch for item in inventory.crystals) == (
        UnknownPass1CrystalBranch.READY,
        UnknownPass1CrystalBranch.HELD,
        UnknownPass1CrystalBranch.EMPTY_NO_MODEL,
    )
    assert inventory.crystals[0].candidate_count == 27
    assert inventory.crystals[0].deferred_cap_count == 1
    assert inventory.crystals[0].unsearchable_no_model_count == 1
    assert inventory.crystals[2].selected_hypothesis_count == 0
    assert inventory.crystals[2].unsearchable_no_model_count == 2
    assert {task.crystal_id for task in inventory.hypothesis_tasks} == {
        PUBLIC_STUB_CRYSTAL_IDS[0]
    }
    assert tuple(task.allocation_rank for task in inventory.hypothesis_tasks) == tuple(
        range(1, 26)
    )
    assert len({task.model_id for task in inventory.hypothesis_tasks}) == 7
    assert len({task.model_id for task in inventory.hypothesis_tasks[:4]}) == 1


def test_inventory_write_and_reload_are_byte_stable(tmp_path: Path) -> None:
    inventory = _build(materialise_unknown_pass1_public_fixture(tmp_path))
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_unknown_pass1_screen_inventory(inventory, first)
    loaded = load_unknown_pass1_screen_inventory(first)
    write_unknown_pass1_screen_inventory(loaded, second)

    assert first.read_bytes() == second.read_bytes()
    assert loaded.inventory_id == inventory.inventory_id


def test_proceeding_crystal_can_emit_typed_empty_hypothesis_branch(
    tmp_path: Path,
) -> None:
    fixture = materialise_unknown_pass1_public_fixture(tmp_path)
    crystals = list(fixture.crystals)
    crystals[2] = replace(crystals[2], hypotheses=())

    inventory = _build(replace(fixture, crystals=tuple(crystals)))

    assert inventory.crystals[2].branch is UnknownPass1CrystalBranch.EMPTY_NO_HYPOTHESES
    assert inventory.empty_no_hypotheses_count == 1
    assert inventory.empty_no_model_count == 0
    assert inventory.hypothesis_task_count == 25


def test_mtz_model_or_review_stage_mutation_fails_closed(tmp_path: Path) -> None:
    fixture = materialise_unknown_pass1_public_fixture(tmp_path)
    fixture.crystals[0].mtz.write_text("changed\n", encoding="ascii")
    with pytest.raises(UnknownPass1ScreenError, match="MTZ bytes differ"):
        _build(fixture)

    model_root = tmp_path / "model-mutation"
    model_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(model_root)
    fixture.crystals[0].models[0].model.write_text("changed\n", encoding="ascii")
    with pytest.raises(UnknownPass1ScreenError, match="model bytes differ"):
        _build(fixture)

    model_identity_root = tmp_path / "model-identity-mutation"
    model_identity_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(model_identity_root)
    crystals = list(fixture.crystals)
    hypotheses = list(crystals[0].hypotheses)
    payload = hypotheses[1].model_dump(mode="python", exclude={"hypothesis_id"})
    payload["model_sha256"] = "0" * 64
    hypotheses[1] = UnknownPass1AHypothesis.from_content(**payload)
    crystals[0] = replace(crystals[0], hypotheses=tuple(hypotheses))
    with pytest.raises(UnknownPass1ScreenError, match="conflicting checksums"):
        _build(replace(fixture, crystals=tuple(crystals)))

    review_root = tmp_path / "review-mutation"
    review_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(review_root)
    decision = (
        fixture.review_stage
        / "stages"
        / PUBLIC_STUB_CRYSTAL_IDS[0]
        / "phase3_review_decision.json"
    )
    decision.write_bytes(decision.read_bytes() + b" \n")
    with pytest.raises(UnknownPass1ScreenError, match="exact crystallographic"):
        _build(fixture)


def test_shared_provider_and_localisation_modes_fail_closed(tmp_path: Path) -> None:
    fixture = materialise_unknown_pass1_public_fixture(tmp_path)
    fixture.shared_preparation.provider_preparation.write_text(
        '{"preparation_id":"public-provider-prepared-once",'
        '"remote_sequence_submission":true}\n',
        encoding="ascii",
    )
    with pytest.raises(UnknownPass1ScreenError, match="prohibit remote"):
        _build(fixture)

    localisation_root = tmp_path / "localisation-mode"
    localisation_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(localisation_root)
    fixture.shared_preparation.localisation_preparation.write_text(
        '{"execution_mode":"remote",'
        '"preparation_id":"public-localisation-prepared-once"}\n',
        encoding="ascii",
    )
    with pytest.raises(UnknownPass1ScreenError, match="local_offline"):
        _build(fixture)


def test_hold_cannot_hide_prepared_hypotheses(tmp_path: Path) -> None:
    fixture = materialise_unknown_pass1_public_fixture(tmp_path)
    crystals = list(fixture.crystals)
    held_hypothesis = public_stub_hypothesis(
        PUBLIC_STUB_CRYSTAL_IDS[1],
        1,
        UnknownPass1AHypothesisDisposition.SELECTED,
        allocation_rank=1,
    )
    held_model = tmp_path / "held-model.pdb"
    held_model.write_bytes(public_stub_model_bytes(PUBLIC_STUB_CRYSTAL_IDS[1], 1))
    crystals[1] = replace(
        crystals[1],
        hypotheses=(held_hypothesis,),
        models=(UnknownPass1ModelInput(held_hypothesis.model_id or "", held_model),),
    )

    with pytest.raises(UnknownPass1ScreenError, match="complete-item contract"):
        _build(replace(fixture, crystals=tuple(crystals)))


def test_26th_selected_allocation_is_rejected() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 25"):
        public_stub_hypothesis(
            PUBLIC_STUB_CRYSTAL_IDS[0],
            26,
            UnknownPass1AHypothesisDisposition.SELECTED,
            allocation_rank=26,
        )


def test_content_mutation_cannot_reuse_inventory_identity(tmp_path: Path) -> None:
    inventory = _build(materialise_unknown_pass1_public_fixture(tmp_path))
    path = tmp_path / "inventory.json"
    write_unknown_pass1_screen_inventory(inventory, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["held_count"] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(UnknownPass1ScreenError, match="typed contract"):
        load_unknown_pass1_screen_inventory(path)


def test_review_bindings_cannot_mix_owned_parent_runs(tmp_path: Path) -> None:
    inventory = _build(materialise_unknown_pass1_public_fixture(tmp_path))
    binding_payload = inventory.review_bindings[0].model_dump(
        mode="python",
        exclude={"review_binding_id"},
    )
    binding_payload["owned_parent_run_id"] = "another-owned-parent"
    changed = UnknownPass1ReviewBinding.from_content(**binding_payload)
    inventory_payload = inventory.model_dump(
        mode="python",
        exclude={"inventory_id"},
    )
    inventory_payload["review_bindings"] = (
        changed,
        *inventory.review_bindings[1:],
    )

    with pytest.raises(ValidationError, match="share one owned parent"):
        UnknownPass1ScreenInventory.from_content(**inventory_payload)


def test_review_stage_index_cannot_cross_execution_identity(tmp_path: Path) -> None:
    fixture = materialise_unknown_pass1_public_fixture(tmp_path)
    payload = fixture.inventory.model_dump(mode="python")
    index_payload = json.loads(fixture.review_stage_index.read_text(encoding="ascii"))
    index_payload.pop("stage_index_id")
    index_payload["execution_identity_id"] = f"phase3exec_{'f' * 64}"
    changed = UnknownPass1ReviewStageIndex.from_content(**index_payload)
    atomic_write_json(
        fixture.review_stage_index,
        changed.model_dump(mode="json", exclude_none=False),
    )

    with pytest.raises(UnknownPass1ScreenError, match="another execution identity"):
        _build(fixture)

    assert payload["execution_identity"]["execution_identity_id"] != (
        changed.execution_identity_id
    )
