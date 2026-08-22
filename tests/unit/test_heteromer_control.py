"""Tests for the fixed public 6RTZ input preparation."""

import json
from pathlib import Path

import gemmi
import numpy as np
import pytest

from genome_to_diffraction.benchmarks import (
    HeteromerControlPreparationRequest,
    prepare_6rtz_heteromer_control,
)
from genome_to_diffraction.benchmarks import heteromer_control as control
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    ProcessedModelRecord,
    SequenceGroupRecord,
)

REPOSITORY = Path(__file__).resolve().parents[2]
PROTOCOL = REPOSITORY / "benchmarks/m6/protocol.yaml"
PARENT_SEQUENCE = (
    "MLAKRIIACLDVKDGRVVKGTNFENLRDSGDPVELGKFYSEIGIDELVFLDITASVEKRKTMLELVEKVA"
    "EQIDIPFTVGGGIHDFETASELILRGADKVSINTAAVENPSLITQIAQTFGSQAVVVAIDAKRVDGEFM"
    "VFTYSGKKNTGILLRDWVVEVEKRGAGEILLTSIDRDGTKSGYDTEMIRFVRPLTTLPIIASGGAGKMEH"
    "FLEAFLAGADAALAASVFHFREIDVRELKEYLKKHGVNVRLEGL"
)
PARTNER_SEQUENCE = (
    "MRIGIISVGPGNIMNLYRGVKRASENFEDVSIELVESPRNDLYDLLFIPGVGHFGEGMRRLRENDLIDFV"
    "RKHVEDERYVVGVCLGMQLLFEESEEAPGVKGLSLIEGNVVKLRSRRLPHMGWNEVIFKDTFPNGYYYF"
    "VHTYRAVCEEEHVLGTTEYDGEIFPSAVRKGRILGFQFHPEKSSKIGRKLLEKVIECSLSRR"
)


def _synthetic_mtz(output: Path) -> gemmi.Mtz:
    mtz = gemmi.Mtz(with_base=True)
    space_group = gemmi.find_spacegroup_by_name("P 32 2 1")
    assert space_group is not None
    mtz.spacegroup = space_group
    mtz.set_cell_for_all(gemmi.UnitCell(80, 80, 120, 90, 90, 120))
    dataset = mtz.add_dataset("6RTZ-test")
    for label, kind in (
        ("FreeR_flag", "I"),
        ("F(+)", "G"),
        ("SIGF(+)", "L"),
        ("F(-)", "G"),
        ("SIGF(-)", "L"),
    ):
        mtz.add_column(label, kind, dataset.id)
    mtz.set_data(
        np.asarray(
            [
                [0, 0, 1, 0, 100, 10, 90, 9],
                [0, 1, 0, 1, 80, 8, 70, 7],
            ],
            dtype=np.float32,
        )
    )
    mtz.update_reso()
    output.parent.mkdir(parents=True, exist_ok=True)
    mtz.write_to_file(str(output))
    return mtz


def test_preparer_writes_minimal_a_then_b_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinates = tmp_path / "6RTZ.cif"
    structure_factors = tmp_path / "6RTZ-sf.cif"
    coordinates.write_text("synthetic coordinates\n", encoding="ascii")
    structure_factors.write_text("synthetic reflections\n", encoding="ascii")

    monkeypatch.setattr(
        control,
        "_verify_source",
        lambda path, **_: path.resolve(strict=True),
    )
    monkeypatch.setattr(
        control,
        "_entity_sequences",
        lambda _: {1: PARENT_SEQUENCE, 2: PARTNER_SEQUENCE},
    )

    def fake_extract(
        source: Path,
        output: Path,
        *,
        chain_name: str,
        full_sequence: str,
    ) -> tuple[str, tuple[str, ...]]:
        del source
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"REMARK chain {chain_name}\nATOM\n", encoding="ascii")
        return full_sequence[:-1], (f"{chain_name}:1-{len(full_sequence) - 1}",)

    monkeypatch.setattr(control, "_extract_polymer_chain", fake_extract)
    monkeypatch.setattr(
        control, "_convert_structure_factors", lambda _, output: _synthetic_mtz(output)
    )

    result = prepare_6rtz_heteromer_control(
        HeteromerControlPreparationRequest(
            protocol=PROTOCOL,
            coordinates=coordinates,
            structure_factors=structure_factors,
            output_directory=tmp_path / "prepared",
            progress=False,
        )
    )

    groups = [
        SequenceGroupRecord.model_validate_json(line)
        for line in result.sequence_groups_jsonl.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert [group.sequence for group in groups] == [
        PARENT_SEQUENCE,
        PARTNER_SEQUENCE,
    ]
    model = ProcessedModelRecord.model_validate_json(
        result.processed_models_jsonl.read_text(encoding="utf-8")
    )
    hypothesis = MrHypothesis.model_validate_json(
        result.hypotheses_jsonl.read_text(encoding="utf-8")
    )
    assert model.full_candidate_sequence_group_id == groups[0].sequence_group_id
    assert model.processing_parameters["sequence_identity"] == 1.0
    assert hypothesis.sequence_group_id == groups[0].sequence_group_id
    assert hypothesis.copy_count_expected == 1
    assert hypothesis.obs_labels == "F(+),SIGF(+),F(-),SIGF(-)"
    assert result.partner_sequence_group_id == groups[1].sequence_group_id
    manifest = json.loads(result.preparation_manifest.read_text(encoding="utf-8"))
    assert manifest["composition"] == {"A": 1, "B": 1}
    assert manifest["files"]["partner_model"]["sha256"] == sha256_file(
        result.partner_model
    )


def test_preparer_rejects_changed_frozen_source(tmp_path: Path) -> None:
    changed = tmp_path / "6RTZ.cif"
    changed.write_text("changed\n", encoding="ascii")

    with pytest.raises(
        control.HeteromerControlPreparationError,
        match="does not match the frozen",
    ):
        control._verify_source(
            changed,
            sha256="0" * 64,
            size=changed.stat().st_size,
            label="6RTZ coordinates",
        )
