"""Tests for manifest-derived single-crystal MR dispatch."""

import json
from pathlib import Path

import gemmi
import numpy as np
import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.cli import main
from genome_to_diffraction.diffraction.dispatch import (
    CrystalDispatchError,
    CrystalDispatchRequest,
    prepare_crystal_dispatch,
)
from genome_to_diffraction.schemas.v2 import (
    DiffractionSelection,
    FreeRConventionStatus,
    FreeRIdentity,
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


def _phase3_inputs(
    tmp_path: Path,
    *,
    free_dataset_id: int = 1,
    flags: tuple[int, ...] = (0, 1, 0, 0, 1, 0),
) -> tuple[Path, Path, Path]:
    crystals, preflight, path = _inputs(tmp_path)
    crystal_document = json.loads(crystals.read_text(encoding="utf-8"))
    crystal_document["crystals"][0]["free_r_test_value"] = 0
    crystals.write_text(json.dumps(crystal_document), encoding="utf-8")
    mtz = gemmi.Mtz(with_base=True)
    mtz.spacegroup = gemmi.find_spacegroup_by_name("P 21 21 21")
    mtz.set_cell_for_all(gemmi.UnitCell(100, 100, 100, 90, 90, 90))
    observations = mtz.add_dataset("observations")
    observation_dataset_id = observations.id
    other = mtz.add_dataset("other")
    assert observation_dataset_id == 1
    assert other.id == 2
    mtz.add_column("I", "J", observation_dataset_id)
    mtz.add_column("SIGI", "Q", observation_dataset_id)
    mtz.add_column("FreeR_flag", "I", free_dataset_id)
    indices = ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1))
    mtz.set_data(
        np.asarray(
            [
                (*hkl, float(100 + index), float(10 + index), float(flags[index]))
                for index, hkl in enumerate(indices)
            ],
            dtype=np.float32,
        )
    )
    mtz.update_reso()
    mtz.write_to_file(str(path))
    record = json.loads(preflight.read_text(encoding="utf-8"))
    record.update(
        {
            "mtz_sha256": sha256_file(path, progress=False),
            "selected_observation_dataset_id": observation_dataset_id,
            "observation_candidate_identities": [
                {
                    "dataset_id": observation_dataset_id,
                    "labels": ["I", "SIGI"],
                    "observation_type": "intensity",
                }
            ],
        }
    )
    preflight.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return crystals, preflight, path


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
    assert first.diffraction_selection is None
    assert first.free_r_identity is None


def test_phase3_dispatch_binds_selected_dataset_and_exact_free_r_membership(
    tmp_path: Path,
) -> None:
    crystals, preflight, mtz = _phase3_inputs(tmp_path, free_dataset_id=2)

    output = prepare_crystal_dispatch(
        CrystalDispatchRequest(
            crystal_manifest=crystals,
            preflight_jsonl=preflight,
            output_directory=tmp_path / "phase3-dispatch",
            progress=False,
            phase3_diffraction=True,
        )
    )

    assert output.diffraction_selection is not None
    assert output.free_r_identity is not None
    selection = DiffractionSelection.model_validate_json(
        output.diffraction_selection.read_bytes()
    )
    identity = FreeRIdentity.model_validate_json(output.free_r_identity.read_bytes())
    assert selection.crystal_id == "crystal_01"
    assert selection.mtz_sha256 == sha256_file(mtz, progress=False)
    assert selection.observation_dataset_id == 1
    assert selection.observation_labels == ("I", "SIGI")
    assert identity.diffraction_selection_id == selection.diffraction_selection_id
    assert identity.free_r_dataset_id == 2
    assert identity.free_r_label == "FreeR_flag"
    assert identity.distribution.reflection_count == 6
    assert identity.convention_status is FreeRConventionStatus.EXPLICIT_TEST_VALUE
    assert identity.test_flag_value == 0


def test_cli_phase3_dispatch_publishes_both_crystal_owned_diffraction_records(
    tmp_path: Path,
) -> None:
    crystals, preflight, _ = _phase3_inputs(tmp_path)
    output = tmp_path / "phase3-cli-dispatch"

    result = main(
        [
            "--no-progress",
            "diffraction",
            "select-single",
            "--crystals",
            str(crystals),
            "--preflight",
            str(preflight),
            "--phase3-diffraction",
            "--outdir",
            str(output),
        ]
    )

    assert result == 0
    assert (output / "phase3_diffraction_selection.json").is_file()
    assert (output / "phase3_free_r_identity.json").is_file()


@pytest.mark.parametrize("failure", ("missing", "missing_test_value", "constant"))
def test_phase3_dispatch_refuses_missing_or_invalid_free_r_before_publication(
    tmp_path: Path,
    failure: str,
) -> None:
    crystals, preflight, _ = _phase3_inputs(
        tmp_path,
        free_dataset_id=1,
        flags=(0, 0, 0, 0, 0, 0) if failure == "constant" else (0, 1, 0, 0, 1, 0),
    )
    if failure == "missing":
        record = json.loads(preflight.read_text(encoding="utf-8"))
        record.update({"free_flag_labels": None, "free_flag_status": "missing"})
        preflight.write_text(json.dumps(record) + "\n", encoding="utf-8")
    elif failure == "missing_test_value":
        manifest = json.loads(crystals.read_text(encoding="utf-8"))
        manifest["crystals"][0]["free_r_test_value"] = None
        crystals.write_text(json.dumps(manifest), encoding="utf-8")
    destination = tmp_path / "invalid-phase3-dispatch"

    with pytest.raises(CrystalDispatchError, match=r"Free-R|diffraction selection"):
        prepare_crystal_dispatch(
            CrystalDispatchRequest(
                crystal_manifest=crystals,
                preflight_jsonl=preflight,
                output_directory=destination,
                progress=False,
                phase3_diffraction=True,
            )
        )

    assert not destination.exists()


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


def test_dispatch_selects_each_manifest_owned_crystal_from_multi_manifest(
    tmp_path: Path,
) -> None:
    crystals, preflight, first_mtz = _inputs(tmp_path)
    document = json.loads(crystals.read_text(encoding="utf-8"))
    preflight_template = json.loads(preflight.read_text(encoding="utf-8"))
    preflight_records = [preflight_template]
    expected_mtz = {"crystal_01": first_mtz}

    for index in (2, 3):
        crystal_id = f"crystal_{index:02d}"
        mtz = first_mtz.parent / f"input diffraction {index}.mtz"
        mtz.write_bytes(f"checksum-bound MTZ fixture {index}\n".encode())
        entry = dict(document["crystals"][0])
        entry.update(
            {
                "crystal_id": crystal_id,
                "mtz": f"../data/{mtz.name}",
            }
        )
        document["crystals"].append(entry)
        record = dict(preflight_template)
        record.update(
            {
                "crystal_id": crystal_id,
                "preflight_id": f"preflight_{crystal_id}",
                "mtz_sha256": sha256_file(mtz),
            }
        )
        preflight_records.append(record)
        expected_mtz[crystal_id] = mtz

    crystals.write_text(json.dumps(document), encoding="utf-8")
    preflight.write_text(
        "".join(f"{json.dumps(record)}\n" for record in preflight_records),
        encoding="utf-8",
    )

    dispatched = {
        crystal_id: prepare_crystal_dispatch(
            CrystalDispatchRequest(
                crystals,
                preflight,
                tmp_path / f"dispatch-{crystal_id}",
                False,
                crystal_id,
            )
        )
        for crystal_id in expected_mtz
    }

    assert set(dispatched) == {"crystal_01", "crystal_02", "crystal_03"}
    assert len({item.record.dispatch_id for item in dispatched.values()}) == 3
    for crystal_id, item in dispatched.items():
        assert item.record.crystal_id == crystal_id
        assert item.mtz.read_bytes() == expected_mtz[crystal_id].read_bytes()


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
