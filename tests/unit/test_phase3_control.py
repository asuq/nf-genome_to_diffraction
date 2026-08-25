import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import gemmi
import numpy as np
import pytest

from genome_to_diffraction.benchmarks import phase3_control as control
from genome_to_diffraction.benchmarks.heteromer_control import (
    HeteromerControlPreparationRequest,
)
from genome_to_diffraction.schemas.results import MrHypothesis

PROTOCOL = Path("benchmarks/m6/protocol.yaml")


def _synthetic_mtz(output: Path) -> gemmi.Mtz:
    mtz = gemmi.Mtz(with_base=True)
    space_group = gemmi.find_spacegroup_by_name("P 21 21 21")
    assert space_group is not None
    mtz.spacegroup = space_group
    mtz.set_cell_for_all(gemmi.UnitCell(100, 110, 120, 90, 90, 90))
    dataset = mtz.add_dataset("9ECN-test")
    for label, kind in (
        ("FreeR_flag", "I"),
        ("F", "F"),
        ("SIGF", "Q"),
    ):
        mtz.add_column(label, kind, dataset.id)
    mtz.set_data(
        np.asarray(
            [
                [0, 0, 1, 0, 100, 10],
                [0, 1, 0, 1, 80, 8],
            ],
            dtype=np.float32,
        )
    )
    mtz.update_reso()
    output.parent.mkdir(parents=True, exist_ok=True)
    mtz.write_to_file(str(output))
    return mtz


def test_protocol_freezes_9ecn_three_component_identity() -> None:
    specification = control._control_spec(PROTOCOL)

    assert specification.source.pdb_id == "9ECN"
    assert specification.source.pdb_entity_ids == (1, 2, 3)
    assert specification.asu_distinct_protein_species == 3
    assert specification.asu_protein_copy_count == 6
    assert tuple(protein.protein_id for protein in specification.proteins) == (
        "WP_011024419.1",
        "WP_011024423.1",
        "WP_011024420.1",
    )


def test_sequence_evidence_requires_exact_tag_alignment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_sequences = {1: "ACD", 2: "EFG", 3: "XXHI"}
    catalogue_sequences = {1: "ACD", 2: "EFG", 3: "HI"}
    coordinates = tmp_path / "synthetic.cif"
    coordinates.write_text(
        """data_synthetic
loop_
_entity_poly.entity_id
_entity_poly.pdbx_seq_one_letter_code_can
1 ACD
2 EFG
3 XXHI
loop_
_struct_asym.id
_struct_asym.entity_id
A 1
B 1
C 2
D 2
E 3
F 3
loop_
_struct_ref.entity_id
_struct_ref.pdbx_db_accession
_struct_ref.pdbx_seq_one_letter_code
1 REF_A ACD
2 REF_B EFG
3 REF_C HI
loop_
_struct_ref_seq.pdbx_strand_id
_struct_ref_seq.seq_align_beg
_struct_ref_seq.seq_align_end
_struct_ref_seq.db_align_beg
_struct_ref_seq.db_align_end
A 1 3 1 3
B 1 3 1 3
C 1 3 1 3
D 1 3 1 3
E 3 4 1 2
F 3 4 1 2
""",
        encoding="ascii",
    )
    monkeypatch.setattr(
        control,
        "_COMPONENTS",
        (
            ("A", 1, ("A", "B"), "A", "P1", 3),
            ("B", 2, ("C", "D"), "C", "P2", 3),
            ("C", 3, ("E", "F"), "E", "P3", 2),
        ),
    )
    monkeypatch.setattr(
        control,
        "_ALIGNMENTS",
        {
            "A": (1, 3, 1, 3),
            "B": (1, 3, 1, 3),
            "C": (1, 3, 1, 3),
            "D": (1, 3, 1, 3),
            "E": (3, 4, 1, 2),
            "F": (3, 4, 1, 2),
        },
    )
    monkeypatch.setattr(
        control,
        "_SOURCE_ENTITY_3_SHA256",
        hashlib.sha256(source_sequences[3].encode("ascii")).hexdigest(),
    )
    monkeypatch.setattr(control, "_SOURCE_ENTITY_3_LENGTH", len(source_sequences[3]))
    fake_control = SimpleNamespace(
        proteins=tuple(
            SimpleNamespace(
                sequence_length=len(catalogue_sequences[index]),
                sequence_sha256=hashlib.sha256(
                    catalogue_sequences[index].encode("ascii")
                ).hexdigest(),
            )
            for index in (1, 2, 3)
        )
    )

    typed_control = cast(control.M6AssumptionControlSpec, fake_control)
    evidence = control._sequences(coordinates, typed_control)
    assert evidence.source_sequences == source_sequences
    assert evidence.catalogue_sequences == catalogue_sequences

    coordinates.write_text(
        coordinates.read_text(encoding="ascii").replace("E 3 4 1 2", "E 2 4 1 2"),
        encoding="ascii",
    )
    with pytest.raises(
        control.HeteromerControlPreparationError,
        match="alignment changed",
    ):
        control._sequences(coordinates, typed_control)


def test_preparer_emits_three_models_and_joint_two_copy_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinates = tmp_path / "9ECN.cif"
    structure_factors = tmp_path / "9ECN-sf.cif"
    coordinates.write_text("synthetic coordinates\n", encoding="ascii")
    structure_factors.write_text("synthetic reflections\n", encoding="ascii")
    sequences = {1: "ACDE", 2: "FGHI", 3: "XXKLMN"}
    catalogue = {1: "ACDE", 2: "FGHI", 3: "KLMN"}
    resource = SimpleNamespace(sha256="a" * 64, size_bytes=1)
    fake_control = SimpleNamespace(
        source=SimpleNamespace(coordinates=resource, structure_factors=resource),
        catalogue_id="cat-macetivorans",
    )
    monkeypatch.setattr(control, "_control_spec", lambda _: fake_control)
    monkeypatch.setattr(
        control, "_verify_source", lambda path, **_: path.resolve(strict=True)
    )
    monkeypatch.setattr(
        control,
        "_sequences",
        lambda *_: control._SequenceEvidence(
            source_sequences=sequences,
            catalogue_sequences=catalogue,
            accessions={1: "A", 2: "B", 3: "C"},
        ),
    )

    def fake_extract(
        source: Path,
        output: Path,
        *,
        chain_name: str,
        catalogue_sequence: str,
    ) -> tuple[str, tuple[str, ...]]:
        del source
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"REMARK chain {chain_name}\nATOM\n", encoding="ascii")
        return catalogue_sequence, (f"{chain_name}:1-{len(catalogue_sequence)}",)

    monkeypatch.setattr(control, "_extract_component_chain", fake_extract)
    monkeypatch.setattr(
        control, "_convert_structure_factors", lambda _, output: _synthetic_mtz(output)
    )

    result = control.prepare_9ecn_phase3_control(
        HeteromerControlPreparationRequest(
            protocol=PROTOCOL,
            coordinates=coordinates,
            structure_factors=structure_factors,
            output_directory=tmp_path / "prepared",
            progress=False,
        )
    )

    manifest = json.loads(result.preparation_manifest.read_text(encoding="utf-8"))
    hypothesis = MrHypothesis.model_validate_json(
        result.hypotheses_jsonl.read_text(encoding="utf-8")
    )
    assert manifest["composition"] == {"A": 2, "B": 2, "C": 2}
    assert [row["label"] for row in manifest["components"]] == ["A", "B", "C"]
    assert (
        manifest["components"][2]["source_construct_sequence_sha256"]
        != (manifest["components"][2]["catalogue_sequence_sha256"])
    )
    assert manifest["claim_boundary"] == "known_control_input_only_no_scientific_result"
    assert len(result.component_models) == 3
    assert len(result.processed_models_jsonl.read_text().splitlines()) == 3
    assert hypothesis.copy_count_expected == 2
    assert hypothesis.copy_number_to_search == 2
