"""Focused contracts for the fixed T12 refinement/sequence adapter."""

from pathlib import Path

import pytest

from genome_to_diffraction.ids import sequence_digest
from genome_to_diffraction.refinement.brief import (
    T12InputError,
    _refine_parameters,
    _refinement_metrics,
    _sequence_candidates,
    _verified_file,
)
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    SourceProteinRecord,
)


def _group(sequence: str) -> SequenceGroupRecord:
    digest = sequence_digest(sequence)
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=1000.0,
        mass_method="test",
        residue_policy="canonical",
        source_record_count=1,
    )


def _source(group: SequenceGroupRecord) -> SourceProteinRecord:
    return SourceProteinRecord(
        schema_version="1.0",
        source_record_id="src_" + "a" * 64,
        catalogue_id="catalogue",
        original_protein_id="protein-1",
        original_header="protein-1",
        sequence_group_id=group.sequence_group_id,
        locus_tag="LOCUS_1",
        source_annotation_provider="test",
    )


def test_fixed_refinement_parameters_are_conservative_and_stable() -> None:
    text = _refine_parameters(threads=4, map_name="stable.ccp4")

    assert "number_of_macro_cycles = 1" in text
    assert "nproc = 4" in text
    assert "strategy = individual_sites individual_adp" in text
    assert "simulated_annealing = False" in text
    assert "ordered_solvent = False" in text
    assert "map_type = 2mFo-DFc" in text
    assert "file_name = stable.ccp4" in text
    assert "fill_missing_f_obs = False" in text
    assert "scale = sigma" in text
    assert "region = cell" in text


def test_refinement_parser_preserves_initial_and_final_r_values() -> None:
    text = """
Start r_work = 0.4120 r_free = 0.4560
RMS bonds = 0.014
Final R-work = 0.3110 R-free = 0.3680
RMS angles = 1.72
"""

    assert _refinement_metrics(text) == (
        0.412,
        0.456,
        0.311,
        0.368,
        0.014,
        1.72,
    )


def test_sequence_parser_ranks_all_scored_exact_groups() -> None:
    first = _group("ACDE")
    second = _group("FGHIK")
    source_first = _source(first)
    source_second = _source(second).model_copy(
        update={
            "source_record_id": "src_" + "b" * 64,
            "sequence_group_id": second.sequence_group_id,
            "locus_tag": "LOCUS_2",
        }
    )
    text = f"""
Score for sequence 1 (4 residues):  7.00 (>{first.sequence_group_id})
Score for sequence 2 (5 residues):  11.00 (>{second.sequence_group_id})
Overall best Z-score: 1.00  Mean and SD of scores: 9.00 +/- 2.00 .
"""

    candidates, best, mean, sd, best_z = _sequence_candidates(
        text,
        refinement_id="refine_" + "c" * 64,
        groups={first.sequence_group_id: first, second.sequence_group_id: second},
        crosswalk={
            first.sequence_group_id: (
                (source_first.source_record_id,),
                ("LOCUS_1",),
            ),
            second.sequence_group_id: (
                (source_second.source_record_id,),
                ("LOCUS_2",),
            ),
        },
    )

    assert [item.sequence_group_id for item in candidates] == [
        second.sequence_group_id,
        first.sequence_group_id,
    ]
    assert [item.rank for item in candidates] == [1, 2]
    assert [item.score_z for item in candidates] == [1.0, -1.0]
    assert (best, mean, sd, best_z) == (11.0, 9.0, 2.0, 1.0)


def test_checksum_mismatch_fails_before_external_execution(tmp_path: Path) -> None:
    path = tmp_path / "parent.pdb"
    path.write_text("MODEL\nEND\n", encoding="ascii")

    with pytest.raises(T12InputError, match="checksum mismatch"):
        _verified_file(
            path,
            "0" * 64,
            label="parent coordinate",
            progress=False,
        )
