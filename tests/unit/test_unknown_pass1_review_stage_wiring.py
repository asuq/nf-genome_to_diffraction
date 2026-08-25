"""Focused tests for registry-owned unknown-pass-1 review staging."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.execution.unknown_screen import (
    UnknownPass1ReviewDecisionInput,
    UnknownPass1ReviewStageIndexOutput,
    UnknownPass1ScreenError,
    publish_unknown_pass1_crystallographic_review_routes,
    stage_unknown_pass1_crystallographic_reviews,
)

from ..support.unknown_pass1_fixture import (
    PUBLIC_STUB_CRYSTAL_IDS,
    UnknownPass1PublicFixture,
    materialise_unknown_pass1_public_fixture,
)


def _stage(
    fixture: UnknownPass1PublicFixture,
    output: Path,
    *,
    decisions: tuple[UnknownPass1ReviewDecisionInput, ...] | None = None,
    run_id: str | None = None,
) -> UnknownPass1ReviewStageIndexOutput:
    return stage_unknown_pass1_crystallographic_reviews(
        owned_run_registry=fixture.owned_run_registry,
        owned_run_id=run_id or "public-unknown-pass1-stub-parent",
        decisions=decisions or fixture.review_decisions,
        output_directory=output,
    )


def test_stages_registry_packages_in_deterministic_crystal_order(
    tmp_path: Path,
) -> None:
    fixture = materialise_unknown_pass1_public_fixture(tmp_path)
    output = _stage(
        fixture,
        tmp_path / "restaged-reversed",
        decisions=tuple(reversed(fixture.review_decisions)),
    )

    assert tuple(item.crystal_id for item in output.index.review_bindings) == (
        PUBLIC_STUB_CRYSTAL_IDS
    )
    assert output.index.execution_identity_id == (
        fixture.inventory.execution_identity.execution_identity_id
    )
    assert output.index.owned_parent_run_id == "public-unknown-pass1-stub-parent"
    assert {item.name for item in output.stage_directory.iterdir()} == set(
        PUBLIC_STUB_CRYSTAL_IDS
    )
    assert str(tmp_path) not in output.index_path.read_text(encoding="ascii")


def test_cross_run_and_cross_crystal_decisions_fail_before_publication(
    tmp_path: Path,
) -> None:
    fixture = materialise_unknown_pass1_public_fixture(tmp_path)
    with pytest.raises(UnknownPass1ScreenError, match="requested run differs"):
        _stage(
            fixture,
            tmp_path / "cross-run",
            run_id="another-owned-run",
        )

    inputs = list(fixture.review_decisions)
    inputs[0] = replace(
        inputs[0],
        decisions=inputs[1].decisions,
        confirmed_decisions_sha256=inputs[1].confirmed_decisions_sha256,
    )
    with pytest.raises(UnknownPass1ScreenError, match="different review package"):
        _stage(
            fixture,
            tmp_path / "cross-crystal",
            decisions=tuple(inputs),
        )

    assert not (tmp_path / "cross-run").exists()
    assert not (tmp_path / "cross-crystal").exists()


@pytest.mark.parametrize("mutation", ("changed", "missing", "duplicate"))
def test_mutated_missing_or_duplicate_owned_package_fails_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    fixture = materialise_unknown_pass1_public_fixture(tmp_path)
    registry_path = fixture.owned_run_registry / "phase3_owned_run_registry.json"
    payload = json.loads(registry_path.read_text(encoding="ascii"))
    first = payload["packages"][0]
    package_root = fixture.owned_run_registry / "packages" / first["review_package_id"]
    if mutation == "changed":
        evidence = next(
            item for item in (package_root / "evidence").rglob("*") if item.is_file()
        )
        evidence.write_bytes(b"x" * evidence.stat().st_size)
    elif mutation == "missing":
        shutil.rmtree(package_root)
    else:
        payload["packages"][1] = first
        registry_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="ascii",
        )

    with pytest.raises(UnknownPass1ScreenError, match="package resolution failed"):
        _stage(fixture, tmp_path / f"package-{mutation}")

    assert not (tmp_path / f"package-{mutation}").exists()


def test_wrong_decision_confirmation_and_duplicate_crystal_fail_closed(
    tmp_path: Path,
) -> None:
    fixture = materialise_unknown_pass1_public_fixture(tmp_path)
    wrong_hash = list(fixture.review_decisions)
    wrong_hash[0] = replace(
        wrong_hash[0],
        confirmed_decisions_sha256="0" * 64,
    )
    with pytest.raises(UnknownPass1ScreenError, match="checksum differs"):
        _stage(
            fixture,
            tmp_path / "wrong-hash",
            decisions=tuple(wrong_hash),
        )

    duplicate = (
        fixture.review_decisions[0],
        fixture.review_decisions[0],
        fixture.review_decisions[2],
    )
    with pytest.raises(UnknownPass1ScreenError, match="distinct crystal"):
        _stage(
            fixture,
            tmp_path / "duplicate-crystal",
            decisions=duplicate,
        )

    assert not (tmp_path / "wrong-hash").exists()
    assert not (tmp_path / "duplicate-crystal").exists()


def _crystal_manifest(fixture: UnknownPass1PublicFixture, path: Path) -> Path:
    atomic_write_json(
        path,
        {
            "schema_version": "1.0",
            "crystals": [
                {
                    "crystal_id": crystal.crystal_id,
                    "mtz": str(crystal.mtz),
                    "catalogue_id": "public_stub_catalogue",
                    "sds_page_mass_kda": [],
                    "allow_remote_sequence_submission": False,
                }
                for crystal in fixture.crystals
            ],
        },
    )
    return path


def test_review_routes_preserve_exact_owned_proceed_and_hold_stages(
    tmp_path: Path,
) -> None:
    fixture = materialise_unknown_pass1_public_fixture(tmp_path)
    output = publish_unknown_pass1_crystallographic_review_routes(
        review_stage_index=fixture.review_stage_index,
        execution_identity=fixture.execution_identity,
        crystal_manifest=_crystal_manifest(fixture, tmp_path / "crystals.json"),
        output_directory=tmp_path / "review-routes",
    )

    assert (
        tuple(sorted(path.name for path in output.iterdir())) == PUBLIC_STUB_CRYSTAL_IDS
    )
    routes = {
        crystal_id: json.loads(
            (output / crystal_id / "crystallographic_review_routing.json").read_bytes()
        )
        for crystal_id in PUBLIC_STUB_CRYSTAL_IDS
    }
    assert tuple(route["decision"] for route in routes.values()) == (
        "proceed",
        "hold",
        "proceed",
    )
    assert {route["execution_identity_id"] for route in routes.values()} == {
        fixture.inventory.execution_identity.execution_identity_id
    }
    for crystal_id in PUBLIC_STUB_CRYSTAL_IDS:
        stage = output / crystal_id / "crystallographic_review_stage"
        assert {item.name for item in stage.iterdir()} == {
            "phase3_review_decision.json",
            "phase3_review_stage_manifest.json",
        }


@pytest.mark.parametrize(
    "mutation", ("missing-crystal", "changed-mtz", "changed-stage")
)
def test_review_routes_reject_unbound_crystals_mtz_or_decisions(
    tmp_path: Path,
    mutation: str,
) -> None:
    fixture = materialise_unknown_pass1_public_fixture(tmp_path)
    manifest = _crystal_manifest(fixture, tmp_path / "crystals.json")
    if mutation == "missing-crystal":
        document = json.loads(manifest.read_bytes())
        document["crystals"].pop()
        atomic_write_json(manifest, document)
    elif mutation == "changed-mtz":
        fixture.crystals[0].mtz.write_bytes(b"changed-public-stub-mtz")
    else:
        decision = (
            fixture.review_stage
            / "stages"
            / PUBLIC_STUB_CRYSTAL_IDS[0]
            / "phase3_review_decision.json"
        )
        decision.write_text("{}\n", encoding="ascii")

    with pytest.raises(UnknownPass1ScreenError):
        publish_unknown_pass1_crystallographic_review_routes(
            review_stage_index=fixture.review_stage_index,
            execution_identity=fixture.execution_identity,
            crystal_manifest=manifest,
            output_directory=tmp_path / "review-routes",
        )
    assert not (tmp_path / "review-routes").exists()
