"""Tests for the bounded cleaned experimental PDB source-chain variant."""

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import gemmi
import pytest

from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.model_registry import (
    ExperimentalModelInputError,
    ExperimentalModelPreparationRequest,
    prepare_experimental_models,
)
from genome_to_diffraction.schemas.results import (
    CoordinateHitMappingRecord,
    CoordinateSourceRecord,
    SequenceGroupRecord,
)


def _source_pdb() -> str:
    names = ("ALA", "CYS", "ASP", "GLU")
    lines: list[str] = []
    atom_id = 1
    for position, name in enumerate(names, start=1):
        lines.append(
            f"ATOM  {atom_id:5d}  CA  {name} B{position:4d}    "
            f"{float(position):8.3f}{0.0:8.3f}{0.0:8.3f}  1.00 20.00           C"
        )
        atom_id += 1
        lines.append(
            f"ATOM  {atom_id:5d}  H   {name} B{position:4d}    "
            f"{float(position):8.3f}{1.0:8.3f}{0.0:8.3f}  1.00 20.00           H"
        )
        atom_id += 1
    lines.append(
        f"HETATM{atom_id:5d}  O   HOH B{10:4d}    "
        f"{10.0:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00 20.00           O"
    )
    return "\n".join([*lines, "END", ""])


def _inputs(
    tmp_path: Path,
) -> tuple[Path, Path, Path, CoordinateSourceRecord, CoordinateHitMappingRecord]:
    input_root = tmp_path / "experimental inputs with spaces"
    input_root.mkdir()
    structure = gemmi.read_pdb_string(_source_pdb())
    structure.name = "1ABC"
    structure.setup_entities()
    coordinate = input_root / "1abc source.cif.gz"
    coordinate.write_bytes(
        gzip.compress(
            structure.make_mmcif_document().as_string().encode("ascii"), mtime=0
        )
    )
    source_sequence = "ACDE"
    candidate_sequence = "ACDQ"
    source_sha256 = hashlib.sha256(source_sequence.encode("ascii")).hexdigest()
    candidate_sha256 = hashlib.sha256(candidate_sequence.encode("ascii")).hexdigest()
    coordinate_sha256 = hashlib.sha256(coordinate.read_bytes()).hexdigest()
    coordinate_id = f"coord_{'c' * 64}"
    source = CoordinateSourceRecord(
        schema_version="1.0",
        coordinate_id=coordinate_id,
        provider="pdb",
        provider_accession="1ABC:1:B",
        retrieval_date=datetime(2026, 8, 11, tzinfo=UTC),
        source_release="retrieved-2026-08-11",
        coordinate_path=str(coordinate),
        coordinate_sha256=coordinate_sha256,
        source_sequence_sha256=source_sha256,
        confidence_summary={"coordinate_kind": "experimental"},
        license_or_provenance="wwPDB test provenance",
    )
    group = SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{candidate_sha256}",
        sha256=candidate_sha256,
        sequence=candidate_sequence,
        length_aa=4,
        molecular_mass_da=475.0,
        mass_method="test mass",
        residue_policy="standard_exact",
        source_record_count=1,
    )
    mapping = CoordinateHitMappingRecord(
        schema_version="1.0",
        mapping_id=f"coordmap_{'d' * 64}",
        hit_id="hit_test_experimental",
        coordinate_id=coordinate_id,
        sequence_group_id=group.sequence_group_id,
        candidate_sequence_sha256=candidate_sha256,
        pdb_id="1ABC",
        identifier_namespace="legacy_seqres_suffix",
        seqres_token="B",
        entity_id="1",
        label_asym_ids=("B",),
        source_sequence_sha256=source_sha256,
        source_sequence_length=4,
        query_start=1,
        query_end=4,
        target_start=1,
        target_end=4,
        aligned_length=4,
        query_coverage=1.0,
        target_coverage=1.0,
        sequence_identity=0.75,
        exact_sequence_match=False,
    )
    sources = input_root / "coordinate sources.jsonl"
    sources.write_text(f"{canonical_json_text(source)}\n", encoding="utf-8")
    mappings = input_root / "coordinate mappings.jsonl"
    mappings.write_text(f"{canonical_json_text(mapping)}\n", encoding="utf-8")
    groups = input_root / "sequence groups.jsonl"
    groups.write_text(f"{canonical_json_text(group)}\n", encoding="utf-8")
    return sources, mappings, groups, source, mapping


def _request(
    tmp_path: Path, sources: Path, mappings: Path, groups: Path
) -> ExperimentalModelPreparationRequest:
    return ExperimentalModelPreparationRequest(
        coordinate_sources_jsonl=sources,
        coordinate_hit_mappings_jsonl=mappings,
        sequence_groups_jsonl=groups,
        output_directory=tmp_path / "experimental models with spaces",
        progress=False,
    )


def test_experimental_model_is_cleaned_mapped_and_content_addressed(
    tmp_path: Path,
) -> None:
    sources, mappings, groups, source, mapping = _inputs(tmp_path)
    output = prepare_experimental_models(_request(tmp_path, sources, mappings, groups))

    assert len(output.records) == 1
    record = output.records[0]
    assert record.coordinate_id == source.coordinate_id
    assert record.full_candidate_sequence_group_id == mapping.sequence_group_id
    assert record.variant_type == "experimental_cleaned_source_chain"
    assert record.residue_ranges == ("B:1-4",)
    assert "experimental_homologue" in record.quality_flags
    manifest = json.loads(output.manifest_json.read_text(encoding="utf-8"))
    entry = manifest["entries"][0]
    model_path = output.manifest_json.parent / entry["model_path"]
    assert model_path.is_file()
    assert hashlib.sha256(model_path.read_bytes()).hexdigest() == record.model_sha256
    model_text = model_path.read_text(encoding="ascii")
    assert " HOH " not in model_text
    assert " H   " not in model_text
    parsed = gemmi.read_structure(str(model_path))
    assert [chain.name for chain in parsed[0]] == ["A"]
    assert len(list(parsed[0][0].get_polymer())) == 4
    parameters = record.processing_parameters
    assert parameters["source_author_chain"] == "B"
    assert parameters["output_chain"] == "A"
    assert parameters["sequence_adaptation"] is False
    assert parameters["side_chain_pruning"] is False
    assert manifest["scope"] == "experimental_cleaned_source_chain_only"


def test_experimental_model_rejects_coordinate_checksum_drift(tmp_path: Path) -> None:
    sources, mappings, groups, source, _ = _inputs(tmp_path)
    Path(source.coordinate_path).write_bytes(b"changed")

    with pytest.raises(ExperimentalModelInputError, match="checksum mismatch"):
        prepare_experimental_models(_request(tmp_path, sources, mappings, groups))
