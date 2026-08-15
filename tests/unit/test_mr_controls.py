"""Tests for the fixed same-MTZ first-copy MR calibration controls."""

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from Bio.SeqUtils import seq3

from genome_to_diffraction.benchmarks.mr_controls import (
    MrControlBundleRequest,
    MrControlInputError,
    build_mr_control_bundle,
)
from genome_to_diffraction.catalogue.mass import assess_mass
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MtzPreflightRecord,
    PreflightDecision,
    ProcessedModelRecord,
    SequenceGroupRecord,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
UBIQUITIN = (
    "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"
)


def _pdb(sequence: str) -> bytes:
    lines = []
    three_letter = seq3(sequence).upper()
    for index in range(len(sequence)):
        residue = three_letter[index * 3 : index * 3 + 3]
        lines.append(
            f"ATOM  {index + 1:5d}  CA  {residue:>3s} A{index + 1:4d}    "
            f"{float(index):8.3f}{0.0:8.3f}{0.0:8.3f}  1.00 20.00           C"
        )
    return ("\n".join(lines) + "\nTER\nEND\n").encode("ascii")


def _bundle_inputs(tmp_path: Path) -> MrControlBundleRequest:
    specification_root = tmp_path / "specifications"
    preparation_root = tmp_path / "prepared public control"
    database_root = tmp_path / "database coordinate cache"
    specification_root.mkdir()
    (preparation_root / "manifests").mkdir(parents=True)
    (preparation_root / "models").mkdir()
    object_root = database_root / "pdb/objects/aa"
    object_root.mkdir(parents=True)

    target_sequence = "AAAA"
    target_sha = hashlib.sha256(target_sequence.encode("ascii")).hexdigest()
    positive_model = preparation_root / "models/positive.pdb"
    positive_model.write_bytes(_pdb(target_sequence))
    positive_sha = sha256_file(positive_model)
    negative_coordinate = object_root / "negative.pdb"
    negative_coordinate.write_bytes(_pdb(UBIQUITIN))
    negative_sha = sha256_file(negative_coordinate)
    negative_sequence_sha = hashlib.sha256(UBIQUITIN.encode("ascii")).hexdigest()

    positive_spec = {
        "schema_version": "1.0",
        "control_id": "CONTROL_CRYSTAL",
        "benchmark_class": "operational_public_positive_control",
        "organism": "Synthetic unit-test organism",
        "assembly_accession": "GCF_000000001.1",
        "assembly_version": "test",
        "annotation_provider": "test",
        "annotation_version": "test",
        "expected_proteome_sha256": "a" * 64,
        "catalogue_id": "control_catalogue",
        "target_protein_id": "target_a",
        "target_sequence_length": 4,
        "target_sequence_sha256": target_sha,
        "expected_exact_catalogue_records": ["target_a"],
        "target_pdb_id": "1AAA",
        "target_pdb_version": "1.0",
        "expected_asu_copy_count": 2,
        "biological_assembly_copy_count": 2,
        "asu_model": "single_protein_species_multi_copy",
        "target_construct": {
            "coordinate_sequence_length": 4,
            "coordinate_sequence_sha256": target_sha,
            "catalogue_start": 1,
            "catalogue_end": 4,
            "coordinate_match_start": 1,
            "coordinate_match_end": 4,
        },
        "processing_software": ["test"],
        "sds_page_evidence": "not_available",
        "resources": [
            {
                "role": role,
                "pdb_id": pdb_id,
                "url": f"https://files.rcsb.org/download/{pdb_id}.cif",
                "filename": f"{pdb_id}.cif",
                "sha256": character * 64,
                "size_bytes": 1,
            }
            for role, pdb_id, character in (
                ("target_coordinates", "1AAA", "1"),
                ("target_structure_factors", "1AAA", "2"),
                ("exact_mr_coordinates", "1AAB", "3"),
                ("homolog_mr_coordinates", "1AAC", "4"),
            )
        ],
        "derived_mtz": {
            "filename": "control.mtz",
            "gemmi_version": "0.7.5",
            "sha256": "5" * 64,
            "reflection_count": 1,
            "space_group": "P 1",
            "unit_cell": [10, 10, 10, 90, 90, 90],
            "observation_labels": "I,SIGI",
            "free_flag_labels": "FREE",
        },
        "mr_models": [
            {
                "model_id": "positive_exact",
                "source_role": "exact_mr_coordinates",
                "chain_id": "A",
                "filename": "positive.pdb",
                "source_sequence_sha256": target_sha,
                "expected_model_sha256": positive_sha,
                "relationship_to_target": "exact test model",
                "leakage_class": "operational_exact",
                "target_fragment_start_in_source": 1,
                "target_fragment_end_in_source": 4,
            },
            {
                "model_id": "homolog_challenge",
                "source_role": "homolog_mr_coordinates",
                "chain_id": "A",
                "filename": "homolog.pdb",
                "source_sequence_sha256": "6" * 64,
                "expected_model_sha256": "7" * 64,
                "relationship_to_target": "unused unit-test homologue",
                "leakage_class": "homolog_challenge",
            },
        ],
        "score_gate": {
            "llg_greater_than": 50,
            "tfz_greater_than": 5,
            "combination": "or",
        },
        "database_exclusions_for_homolog_challenge": [],
        "limitations": ["unit-test control"],
    }
    positive_spec_path = specification_root / "positive.yaml"
    positive_spec_path.write_text(yaml.safe_dump(positive_spec), encoding="utf-8")
    pair_spec = {
        "schema_version": "1.0",
        "control_pair_id": "CONTROL_PAIR",
        "positive_control_specification": "positive.yaml",
        "positive_model_id": "positive_exact",
        "positive_expected_outcome": "retained_top_ranked",
        "negative_control": {
            "pdb_id": "1UBQ",
            "seqres_token": "A",
            "entity_id": "1",
            "coordinate_sha256": negative_sha,
            "source_sequence_sha256": negative_sequence_sha,
            "source_sequence_length": len(UBIQUITIN),
            "phaser_identity_percent": 1.0,
            "expected_outcome": "retained_below_positive",
            "relationship_to_target": (
                "deliberately unrelated ubiquitin negative control"
            ),
        },
        "score_gate": {
            "llg_greater_than": 50,
            "tfz_greater_than": 5,
            "combination": "or",
        },
        "limitations": ["unit-test pair"],
    }
    pair_path = specification_root / "pair.yaml"
    pair_path.write_text(yaml.safe_dump(pair_spec), encoding="utf-8")
    preparation_manifest = preparation_root / "manifests/preparation.json"
    preparation_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "control_id": "CONTROL_CRYSTAL",
                "derived": {
                    "exact_mr_model": {
                        "path": str(positive_model),
                        "sha256": positive_sha,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    database_manifest = tmp_path / "database manifest.json"
    database_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "manifest_id": "database_test",
                "created_at": "2026-08-12T00:00:00Z",
                "resources": [
                    {
                        "database_id": "coordinate_cache",
                        "name": "coordinate_cache",
                        "source": "test cache",
                        "release_or_snapshot": "test",
                        "root_path": str(database_root),
                        "prepared_with": {"tool": "test", "version": "1"},
                        "parameters": {
                            "qualification": {
                                "provider": "pdb",
                                "source_id": "1ubq",
                                "object_relative_path": ("pdb/objects/aa/negative.pdb"),
                                "object_sha256": negative_sha,
                            }
                        },
                        "prepared_at": "2026-08-12T00:00:00Z",
                        "manifest_sha256": "8" * 64,
                        "status": "ready",
                    },
                    {
                        "database_id": "pdb_foldseek",
                        "name": "pdb_foldseek",
                        "source": "test database",
                        "release_or_snapshot": "test",
                        "root_path": str(tmp_path / "unused"),
                        "prepared_with": {"tool": "test", "version": "1"},
                        "parameters": {
                            "qualification": {
                                "coordinate_mapping": {
                                    "entry_id": "1UBQ",
                                    "seqres_token": "A",
                                    "entity_id": "1",
                                    "sequence_length": len(UBIQUITIN),
                                    "sequence_sha256": negative_sequence_sha,
                                }
                            }
                        },
                        "prepared_at": "2026-08-12T00:00:00Z",
                        "manifest_sha256": "9" * 64,
                        "status": "ready",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    mass = assess_mass(target_sequence)
    assert mass.exact_da is not None
    sequence_group = SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{target_sha}",
        sha256=target_sha,
        sequence=target_sequence,
        length_aa=4,
        molecular_mass_da=mass.exact_da,
        mass_method="unit test",
        residue_policy="standard_exact",
        source_record_count=1,
    )
    sequence_groups = tmp_path / "sequence groups.jsonl"
    sequence_groups.write_text(
        f"{canonical_json_text(sequence_group)}\n", encoding="utf-8"
    )
    stub_preflight = MtzPreflightRecord.model_validate_json(
        (STUBS / "mtz_preflight.jsonl").read_text(encoding="utf-8")
    )
    preflight = stub_preflight.model_copy(
        update={
            "crystal_id": "CONTROL_CRYSTAL",
            "decision": PreflightDecision.PASS,
        }
    )
    preflights = tmp_path / "preflight.jsonl"
    preflights.write_text(f"{canonical_json_text(preflight)}\n", encoding="utf-8")
    return MrControlBundleRequest(
        specification=pair_path,
        public_control_preparation=preparation_manifest,
        database_manifest=database_manifest,
        sequence_groups_jsonl=sequence_groups,
        preflight_jsonl=preflights,
        output_directory=tmp_path / "control bundle",
        progress=False,
    )


def test_build_control_bundle_emits_exact_positive_and_unrelated_negative(
    tmp_path: Path,
) -> None:
    request = _bundle_inputs(tmp_path)

    output = build_mr_control_bundle(request)

    models = [
        ProcessedModelRecord.model_validate_json(line)
        for line in output.processed_models_jsonl.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    hypotheses = [
        MrHypothesis.model_validate_json(line)
        for line in output.hypotheses_jsonl.read_text(encoding="utf-8").splitlines()
    ]
    assert len(models) == len(hypotheses) == 2
    assert {item.processing_parameters["control_role"] for item in models} == {
        "known_positive",
        "deliberate_unrelated_negative",
    }
    negative = next(
        item
        for item in models
        if item.processing_parameters["control_role"] == "deliberate_unrelated_negative"
    )
    assert negative.variant_type == "control_unrelated_cleaned_source_chain"
    assert negative.processing_parameters["phaser_identity_percent"] == 1.0
    assert negative.full_candidate_sequence_group_id == hypotheses[0].sequence_group_id
    assert len(tuple(output.hypothesis_directory.glob("mrhyp_*.jsonl"))) == 2
    manifest = json.loads(output.manifest_json.read_text(encoding="utf-8"))
    assert manifest["expected_outcomes"] == {
        hypotheses[0].hypothesis_id: "retained_top_ranked",
        hypotheses[1].hypothesis_id: "retained_below_positive",
    }


def test_control_bundle_rejects_changed_negative_coordinate(tmp_path: Path) -> None:
    request = _bundle_inputs(tmp_path)
    database = json.loads(request.database_manifest.read_text(encoding="utf-8"))
    root = Path(database["resources"][0]["root_path"])
    (root / "pdb/objects/aa/negative.pdb").write_bytes(b"changed")

    with pytest.raises(MrControlInputError, match="checksum differs"):
        build_mr_control_bundle(request)


def test_control_bundle_rejects_unsafe_database_object_path(tmp_path: Path) -> None:
    request = _bundle_inputs(tmp_path)
    database = json.loads(request.database_manifest.read_text(encoding="utf-8"))
    database["resources"][0]["parameters"]["qualification"]["object_relative_path"] = (
        "../outside.pdb"
    )
    request.database_manifest.write_text(json.dumps(database), encoding="utf-8")

    with pytest.raises(MrControlInputError, match="object path is unsafe"):
        build_mr_control_bundle(request)
