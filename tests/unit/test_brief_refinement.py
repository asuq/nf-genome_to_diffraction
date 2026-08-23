"""Focused contracts for the fixed T12 refinement/sequence adapter."""

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import genome_to_diffraction.refinement.brief as brief_module
from genome_to_diffraction.diffraction.selection import build_diffraction_selection
from genome_to_diffraction.ids import canonical_json_text, sequence_digest
from genome_to_diffraction.refinement.brief import (
    T12InputError,
    T12RunRequest,
    _has_required_map_coefficients,
    _observation_label_argument,
    _refine_parameters,
    _refinement_metrics,
    _refinement_output_paths,
    _sequence_candidates,
    _verified_file,
    run_t12_candidate,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    CrystalEntry,
    PhenixInstallManifest,
)
from genome_to_diffraction.schemas.results import (
    MtzObservationCandidateRecord,
    MtzPreflightRecord,
    SequenceGroupRecord,
    SourceProteinRecord,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"


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
    text = _refine_parameters(
        threads=4,
        map_name="stable.ccp4",
        difference_map_name="difference.ccp4",
    )

    assert "number_of_macro_cycles = 1" in text
    assert "nproc = 4" in text
    assert "strategy = individual_sites individual_adp" in text
    assert "simulated_annealing = False" in text
    assert "ordered_solvent = False" in text
    assert "write_model_cif_file = False" in text
    assert "write_final_pdb_file = True" in text
    assert "map_coefficients {" in text
    assert "map_type = 2mFo-DFc" in text
    assert "mtz_label_amplitudes = 2FOFCWT" in text
    assert "mtz_label_phases = PH2FOFCWT" in text
    assert "map_type = mFo-DFc" in text
    assert "mtz_label_amplitudes = FOFCWT" in text
    assert "mtz_label_phases = PHFOFCWT" in text
    assert "file_name = stable.ccp4" in text
    assert "file_name = difference.ccp4" in text
    assert "fill_missing_f_obs = False" in text
    assert "scale = sigma" in text
    assert "region = cell" in text
    assert "serial = 0" in text


def test_observation_labels_are_passed_to_phenix_unambiguously() -> None:
    assert _observation_label_argument("IMEAN_CD6,SIGIMEAN_CD6") == (
        "data_manager.miller_array.labels.name=IMEAN_CD6,SIGIMEAN_CD6"
    )


def test_refinement_output_names_match_phenix_serial_convention(
    tmp_path: Path,
) -> None:
    model, mtz, map_path, difference_map = _refinement_output_paths(tmp_path)

    assert model.name == "brief_refine_001.pdb"
    assert mtz.name == "brief_refine_001.mtz"
    assert map_path.name == "brief_refine_2mFo-DFc.ccp4"
    assert difference_map.name == "brief_refine_mFo-DFc.ccp4"


def test_refined_mtz_requires_both_review_map_coefficient_pairs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "brief_refine_001.mtz"
    path.write_bytes(b"fixture")

    def columns(*pairs: tuple[str, str]) -> SimpleNamespace:
        return SimpleNamespace(
            columns=[
                SimpleNamespace(label=label, type=type_code)
                for label, type_code in pairs
            ]
        )

    monkeypatch.setattr(
        brief_module.gemmi,
        "read_mtz_file",
        lambda _path: columns(
            ("2FOFCWT", "F"),
            ("PH2FOFCWT", "P"),
            ("FOFCWT", "F"),
            ("PHFOFCWT", "P"),
        ),
    )
    assert _has_required_map_coefficients(path)

    monkeypatch.setattr(
        brief_module.gemmi,
        "read_mtz_file",
        lambda _path: columns(("2FOFCWT", "F"), ("PH2FOFCWT", "P")),
    )
    assert not _has_required_map_coefficients(path)


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


def _phase3_request(tmp_path: Path) -> T12RunRequest:
    tmp_path.mkdir(parents=True, exist_ok=True)
    parent_coordinate = tmp_path / "parent.pdb"
    parent_coordinate.write_text("MODEL\nEND\n", encoding="ascii")
    parent_mtz = tmp_path / "parent.mtz"
    parent_mtz.write_bytes(b"derived parent MTZ")
    base_preflight = MtzPreflightRecord.model_validate_json(
        (STUBS / "mtz_preflight.jsonl").read_text(encoding="utf-8")
    )
    candidate = MtzObservationCandidateRecord(
        dataset_id=3,
        labels=("I", "SIGI"),
        observation_type="intensity",
    )
    payload = base_preflight.model_dump(mode="python")
    payload.update(
        {
            "selected_observation_dataset_id": 3,
            "observation_candidate_identities": (candidate,),
        }
    )
    preflight = MtzPreflightRecord.model_validate(payload)
    preflight_path = tmp_path / "preflight.jsonl"
    preflight_path.write_text(
        f"{canonical_json_text(preflight)}\n",
        encoding="utf-8",
    )
    selection = build_diffraction_selection(
        crystal=CrystalEntry(
            crystal_id=preflight.crystal_id,
            mtz="raw.mtz",
            catalogue_id="catalogue_test",
        ),
        preflight=preflight,
        crystal_manifest_sha256="f" * 64,
    )
    selection_path = tmp_path / "diffraction_selection.json"
    selection_path.write_text(canonical_json_text(selection), encoding="utf-8")
    group = SequenceGroupRecord.model_validate_json(
        (STUBS / "sequence_groups.jsonl").read_text(encoding="utf-8")
    )
    return T12RunRequest(
        seed_solution_id="seed_test",
        sequence_group_id=group.sequence_group_id,
        input_copy_count=1,
        parent_coordinate=parent_coordinate,
        parent_coordinate_sha256=hashlib.sha256(
            parent_coordinate.read_bytes()
        ).hexdigest(),
        parent_mtz=parent_mtz,
        parent_mtz_sha256=hashlib.sha256(parent_mtz.read_bytes()).hexdigest(),
        observation_labels="I,SIGI",
        sequence_groups_jsonl=STUBS / "sequence_groups.jsonl",
        source_records_jsonl=STUBS / "source_records.jsonl",
        resolution=2.0,
        phenix_manifest=STUBS / "phenix_install_manifest.json",
        output_directory=tmp_path / "refinement",
        crystal_id=preflight.crystal_id,
        diffraction_selection_json=selection_path,
        preflight_jsonl=preflight_path,
        progress=False,
    )


def test_phase3_refinement_command_records_verified_diffraction_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _phase3_request(tmp_path)
    manifest = load_contract(
        STUBS / "phenix_install_manifest.json",
        "phenix-install-manifest",
        progress=False,
    )
    assert isinstance(manifest, PhenixInstallManifest)
    commands: list[list[str]] = []

    def fake_capture(
        manifest_path: Path,
        arguments: list[str],
        *,
        working_directory: Path,
        timeout_seconds: float | None,
    ) -> subprocess.CompletedProcess[bytes]:
        del manifest_path, timeout_seconds
        commands.append(arguments)
        if arguments[0] == "phenix.refine":
            (working_directory / "brief_refine_001.pdb").write_text(
                "MODEL\nEND\n",
                encoding="ascii",
            )
            (working_directory / "brief_refine_001.mtz").write_bytes(b"refined")
            (working_directory / "brief_refine_2mFo-DFc.ccp4").write_bytes(b"map")
            (working_directory / "brief_refine_mFo-DFc.ccp4").write_bytes(b"difference")
            output = (
                b"Start r_work = 0.40 r_free = 0.45\n"
                b"Final R-work = 0.30 R-free = 0.35\n"
            )
        else:
            output = b"Overall best Z-score: 0.0  Mean and SD of scores: 0.0 +/- 1.0\n"
        return subprocess.CompletedProcess(arguments, 0, output, b"")

    monkeypatch.setattr(
        brief_module,
        "validate_manifest_environment",
        lambda _path: manifest,
    )
    monkeypatch.setattr(brief_module, "capture_from_manifest", fake_capture)
    monkeypatch.setattr(
        brief_module,
        "_has_required_map_coefficients",
        lambda _path: True,
    )

    output = run_t12_candidate(request)

    record = json.loads(output.command_json.read_text(encoding="utf-8"))
    binding = record["diffraction_command_binding"]
    assert record["schema_version"] == "2.0"
    assert record["phase3_refine_command_id"].startswith("refinecmd_")
    assert record["phase3_sequence_command_id"].startswith("seqmapcmd_")
    assert record["diffraction_selection"]["observation_dataset_id"] == 3
    assert binding["resolution_command_binding"] == (
        "sequence_from_map_high_resolution_explicit_refinement_limits_pending"
    )
    assert binding["command_mtz_binding"].endswith("derivation_verification_pending")
    assert "data_manager.miller_array.labels.name=I,SIGI" in commands[0]
    assert not any("space_group" in argument for argument in commands[0])
    assert not any("resolution" in argument for argument in commands[0])
    assert "crystal_info.resolution=2" in commands[1]
