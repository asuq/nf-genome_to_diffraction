"""Tests for the fixed public 6RTZ input preparation."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import gemmi
import numpy as np
import pytest

from genome_to_diffraction.benchmarks import (
    HeteromerControlPreparationRequest,
    HeteromerControlReviewRequest,
    build_6rtz_control_review,
    prepare_3u7q_heteromer_control,
    prepare_6rtz_heteromer_control,
)
from genome_to_diffraction.benchmarks import heteromer_control as control
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    NormalisedMrResult,
    ProcessedModelRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import ExecutionStatus

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

    parent_root = tmp_path / "parent-results"
    parent_result = parent_root / f"first_copy_phaser_{hypothesis.hypothesis_id}"
    parent_result.mkdir(parents=True)
    solution = parent_result / "PHASER.1.pdb"
    solution.write_text("REMARK ENSEMBLE parent\nATOM\n", encoding="ascii")
    output_mtz = parent_result / "PHASER.1.mtz"
    output_mtz.write_bytes(b"parent result MTZ")
    normalised = NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=hypothesis.hypothesis_id,
        tool_version="Phenix 2.1-6048; Phaser 2.8.4",
        execution_status=ExecutionStatus.COMPLETED_HIT,
        llg=1000.0,
        tfz=30.0,
        placed_copy_count=1,
        packing_summary={
            "top_solution_packed": True,
            "score_gate_passed": True,
            "score_gate_llg_strictly_greater_than": 50.0,
            "score_gate_tfz_strictly_greater_than": 5.0,
            "score_gate_operator": "or",
        },
        solution_coordinate_path=solution.name,
        solution_coordinate_sha256=sha256_file(solution),
        output_mtz_path=output_mtz.name,
        output_mtz_sha256=sha256_file(output_mtz),
        raw_log_pointer="PHASER.log",
    )
    (parent_result / "normalised_mr_result.jsonl").write_text(
        f"{canonical_json_text(normalised)}\n", encoding="utf-8"
    )
    (parent_result / "phaser_command.json").write_text(
        json.dumps(
            {
                "model_sha256": model.model_sha256,
                "model_identity_percent": 100.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (parent_result / "PHASER.log").write_text("fake log\n", encoding="ascii")

    reviewed = build_6rtz_control_review(
        HeteromerControlReviewRequest(
            preparation_manifest=result.preparation_manifest,
            parent_result_directory=parent_result,
            output_directory=tmp_path / "reviewed",
            progress=False,
        )
    )

    assert reviewed.review_package.is_dir()
    assert reviewed.decisions_tsv.is_file()
    assert reviewed.approved_stage.is_dir()
    approved_rows = (reviewed.approved_stage / "approved_seeds.tsv").read_text(
        encoding="utf-8"
    )
    assert "\t1\tfalse\n" in approved_rows


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


def test_3u7q_protocol_declares_two_a_and_two_b() -> None:
    specification = control._control_spec(PROTOCOL, control._CONTROL_3U7Q)

    assert specification.source.pdb_id == "3U7Q"
    assert specification.source.pdb_entity_ids == (1, 2)
    assert specification.asu_protein_copy_count == 4


def test_multicopy_preparer_requests_two_a_jointly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinates = tmp_path / "3U7Q.cif"
    structure_factors = tmp_path / "3U7Q-sf.cif"
    coordinates.write_text("synthetic coordinates\n", encoding="ascii")
    structure_factors.write_text("synthetic reflections\n", encoding="ascii")
    resource = SimpleNamespace(sha256="a" * 64, size_bytes=1)
    fake_control = SimpleNamespace(
        source=SimpleNamespace(coordinates=resource, structure_factors=resource),
        proteins=tuple(
            SimpleNamespace(
                protein_id=protein_id,
                sequence_length=len(sequence),
                sequence_sha256=hashlib.sha256(sequence.encode("ascii")).hexdigest(),
            )
            for protein_id, sequence in (
                ("parent", PARENT_SEQUENCE),
                ("partner", PARTNER_SEQUENCE),
            )
        ),
        catalogue_id="synthetic-multicopy",
    )
    monkeypatch.setattr(
        control,
        "_CONTROL_3U7Q",
        replace(control._CONTROL_3U7Q, source_sequence_sha256=None),
    )
    monkeypatch.setattr(control, "_control_spec", lambda *_: fake_control)
    monkeypatch.setattr(
        control, "_verify_source", lambda path, **_: path.resolve(strict=True)
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

    result = prepare_3u7q_heteromer_control(
        HeteromerControlPreparationRequest(
            protocol=PROTOCOL,
            coordinates=coordinates,
            structure_factors=structure_factors,
            output_directory=tmp_path / "prepared-3u7q",
            progress=False,
        )
    )

    hypothesis = MrHypothesis.model_validate_json(
        result.hypotheses_jsonl.read_text(encoding="utf-8")
    )
    manifest = json.loads(result.preparation_manifest.read_text(encoding="utf-8"))
    assert hypothesis.copy_count_expected == 2
    assert hypothesis.copy_number_to_search == 2
    assert manifest["composition"] == {"A": 2, "B": 2}
