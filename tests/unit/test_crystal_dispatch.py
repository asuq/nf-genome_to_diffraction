"""Tests for manifest-derived single-crystal MR dispatch."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.diffraction.dispatch import (
    CrystalDispatchError,
    CrystalDispatchRequest,
    prepare_crystal_dispatch,
)

REPOSITORY = Path(__file__).resolve().parents[2]


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    data = tmp_path / "data"
    data.mkdir()
    mtz = data / "input diffraction.mtz"
    mtz.write_bytes(b"small checksum-bound MTZ fixture\n")

    manifests = tmp_path / "manifests"
    manifests.mkdir()
    crystals = manifests / "crystals.json"
    crystals.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "crystals": [
                    {
                        "crystal_id": "crystal_01",
                        "mtz": "../data/input diffraction.mtz",
                        "catalogue_id": "catalogue_01",
                        "sds_page_mass_kda": [],
                        "allow_remote_sequence_submission": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    record = json.loads(
        (REPOSITORY / "tests/fixtures/stubs/mtz_preflight.jsonl").read_text(
            encoding="utf-8"
        )
    )
    record.update(
        {
            "crystal_id": "crystal_01",
            "preflight_id": "preflight_crystal_01",
            "mtz_sha256": sha256_file(mtz),
        }
    )
    preflight = manifests / "preflight.jsonl"
    preflight.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return crystals, preflight, mtz


def test_dispatch_resolves_and_verifies_manifest_owned_mtz(tmp_path: Path) -> None:
    crystals, preflight, mtz = _inputs(tmp_path)

    first = prepare_crystal_dispatch(
        CrystalDispatchRequest(crystals, preflight, tmp_path / "dispatch-a", False)
    )
    second = prepare_crystal_dispatch(
        CrystalDispatchRequest(crystals, preflight, tmp_path / "dispatch-b", False)
    )

    assert first.record.dispatch_id == second.record.dispatch_id
    assert first.record.crystal_id == "crystal_01"
    assert first.record.catalogue_id == "catalogue_01"
    assert first.record.mtz_sha256 == sha256_file(mtz)
    assert first.mtz.read_bytes() == mtz.read_bytes()
    assert first.crystal_id_txt.read_text(encoding="utf-8") == "crystal_01\n"
    assert json.loads(first.dispatch_json.read_text(encoding="utf-8")) == (
        first.record.model_dump(mode="json")
    )


def test_dispatch_rejects_multi_crystal_manifest(tmp_path: Path) -> None:
    crystals, preflight, _ = _inputs(tmp_path)
    document = json.loads(crystals.read_text(encoding="utf-8"))
    duplicate = dict(document["crystals"][0])
    duplicate["crystal_id"] = "crystal_02"
    document["crystals"].append(duplicate)
    crystals.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CrystalDispatchError, match="one-crystal manifest"):
        prepare_crystal_dispatch(
            CrystalDispatchRequest(crystals, preflight, tmp_path / "dispatch", False)
        )


def test_dispatch_rejects_preflight_checksum_drift(tmp_path: Path) -> None:
    crystals, preflight, _ = _inputs(tmp_path)
    record = json.loads(preflight.read_text(encoding="utf-8"))
    record["mtz_sha256"] = "0" * 64
    preflight.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(CrystalDispatchError, match="checksum does not match"):
        prepare_crystal_dispatch(
            CrystalDispatchRequest(crystals, preflight, tmp_path / "dispatch", False)
        )


def test_dispatch_rejects_failed_preflight(tmp_path: Path) -> None:
    crystals, preflight, _ = _inputs(tmp_path)
    record = json.loads(preflight.read_text(encoding="utf-8"))
    record["decision"] = "fail"
    record["execution_status"] = "failed_input_contract"
    preflight.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(CrystalDispatchError, match="not eligible for MR"):
        prepare_crystal_dispatch(
            CrystalDispatchRequest(crystals, preflight, tmp_path / "dispatch", False)
        )


def test_dispatch_rejects_symlink_output(tmp_path: Path) -> None:
    crystals, preflight, _ = _inputs(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    output = tmp_path / "dispatch"
    output.symlink_to(target, target_is_directory=True)

    with pytest.raises(CrystalDispatchError, match="must not be a symlink"):
        prepare_crystal_dispatch(
            CrystalDispatchRequest(crystals, preflight, output, False)
        )
