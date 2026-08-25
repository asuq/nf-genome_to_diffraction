"""Focused contracts for the fixed T12 refinement/sequence adapter."""

import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import gemmi
import numpy as np
import pytest

import genome_to_diffraction.refinement.brief as brief_module
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.diffraction.free_r_identity import build_free_r_identity
from genome_to_diffraction.diffraction.selection import (
    build_diffraction_selection,
    load_diffraction_selection,
)
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
from genome_to_diffraction.schemas.v2.diffraction import (
    DiffractionSelection,
    FreeRConventionStatus,
)
from genome_to_diffraction.status import ExecutionStatus

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
_HKL = (
    (1, 0, 0),
    (0, 1, 0),
    (0, 0, 1),
    (1, 1, 0),
    (1, 0, 1),
    (0, 1, 1),
)
_FREE_R_FLAGS = (0, 1, 0, 0, 1, 0)


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


def test_phase3_nextflow_refinement_passes_every_bound_diffraction_input() -> None:
    process = (REPOSITORY / "modules/local/run_brief_refinement.nf").read_text(
        encoding="ascii"
    )
    workflow = (REPOSITORY / "workflows/main_workflow.nf").read_text(encoding="ascii")
    dispatch = (REPOSITORY / "modules/local/select_single_crystal.nf").read_text(
        encoding="ascii"
    )

    assert "process RUN_PHASE3_BRIEF_REFINEMENT" in process
    assert "cache 'deep'" in process
    assert 'tag "phase3-t12:${item[4]}:${item[0][0]}"' in process
    assert 'file("phase3_t12_${item[4]}_${item[0][0]}")' in process
    for argument in (
        "--crystal-id '${item[4]}'",
        "--diffraction-selection '${item[5]}'",
        "--source-mtz '${item[6]}'",
        "--preflight '${item[7]}'",
        "--free-r-identity '${item[8]}'",
    ):
        assert argument in process
    assert "SELECT_PHASE3_SINGLE_CRYSTAL" in workflow
    assert "PHASE3_BRIEF_REFINEMENT_WORKFLOW" in workflow
    assert "--phase3-diffraction" in dispatch


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


def _write_phase3_mtz(
    path: Path,
    *,
    hkl: tuple[tuple[int, int, int], ...] = _HKL,
    free_r_flags: tuple[int, ...] = _FREE_R_FLAGS,
    include_free_r: bool = True,
    include_map_coefficients: bool = False,
    observation_labels: tuple[str, str] = ("I", "SIGI"),
    observation_offset: float = 0.0,
    sigma_offset: float = 0.0,
) -> None:
    if len(hkl) != len(free_r_flags):
        raise ValueError("test HKL and Free-R arrays must have equal length")
    mtz = gemmi.Mtz(with_base=True)
    mtz.spacegroup = gemmi.find_spacegroup_by_name("P 21 21 21")
    mtz.set_cell_for_all(gemmi.UnitCell(100, 100, 100, 90, 90, 90))
    observations = mtz.add_dataset("observations")
    assert observations.id == 1
    mtz.add_column(observation_labels[0], "J", observations.id)
    mtz.add_column(observation_labels[1], "Q", observations.id)
    if include_free_r:
        mtz.add_column("FreeR_flag", "I", observations.id)
    if include_map_coefficients:
        mtz.add_column("2FOFCWT", "F", observations.id)
        mtz.add_column("PH2FOFCWT", "P", observations.id)
        mtz.add_column("FOFCWT", "F", observations.id)
        mtz.add_column("PHFOFCWT", "P", observations.id)
    rows: list[tuple[float, ...]] = []
    for row_index, indices in enumerate(hkl):
        observation_index = _HKL.index(indices) if indices in _HKL else row_index
        values: list[float] = [
            float(indices[0]),
            float(indices[1]),
            float(indices[2]),
            float(100 + observation_index) + observation_offset,
            float(10 + observation_index) + sigma_offset,
        ]
        if include_free_r:
            values.append(float(free_r_flags[row_index]))
        if include_map_coefficients:
            values.extend((20.0, 30.0, 5.0, 40.0))
        rows.append(tuple(values))
    mtz.set_data(np.asarray(rows, dtype=np.float32))
    mtz.update_reso()
    mtz.write_to_file(str(path))


def _phase3_request(
    tmp_path: Path,
    *,
    test_flag_value: int | None = None,
) -> T12RunRequest:
    tmp_path.mkdir(parents=True, exist_ok=True)
    parent_coordinate = tmp_path / "parent.pdb"
    parent_coordinate.write_text("MODEL\nEND\n", encoding="ascii")
    source_mtz = tmp_path / "raw.mtz"
    _write_phase3_mtz(source_mtz)
    parent_mtz = tmp_path / "parent.mtz"
    _write_phase3_mtz(parent_mtz)
    base_preflight = MtzPreflightRecord.model_validate_json(
        (STUBS / "mtz_preflight.jsonl").read_text(encoding="utf-8")
    )
    candidate = MtzObservationCandidateRecord(
        dataset_id=1,
        labels=("I", "SIGI"),
        observation_type="intensity",
    )
    payload = base_preflight.model_dump(mode="python")
    payload.update(
        {
            "mtz_sha256": sha256_file(source_mtz, progress=False),
            "selected_observation_dataset_id": 1,
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
    free_r_identity = build_free_r_identity(
        selection=selection,
        mtz_path=source_mtz,
        free_r_dataset_id=1,
        free_r_label="FreeR_flag",
        test_flag_value=test_flag_value,
    )
    free_r_identity_path = tmp_path / "free_r_identity.json"
    free_r_identity_path.write_text(
        canonical_json_text(free_r_identity),
        encoding="utf-8",
    )
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
        source_mtz=source_mtz,
        diffraction_selection_json=selection_path,
        preflight_jsonl=preflight_path,
        free_r_identity_json=free_r_identity_path,
        progress=False,
    )


def _install_phase3_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    derived_hkl: tuple[tuple[int, int, int], ...] = _HKL,
    derived_free_r_flags: tuple[int, ...] = _FREE_R_FLAGS,
    include_free_r: bool = True,
) -> list[list[str]]:
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
            _write_phase3_mtz(
                working_directory / "brief_refine_001.mtz",
                hkl=derived_hkl,
                free_r_flags=derived_free_r_flags,
                include_free_r=include_free_r,
                include_map_coefficients=True,
            )
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
    return commands


def test_version_1_refinement_path_does_not_require_free_r_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = replace(
        _phase3_request(tmp_path),
        crystal_id=None,
        source_mtz=None,
        diffraction_selection_json=None,
        preflight_jsonl=None,
        free_r_identity_json=None,
    )
    _install_phase3_runtime(monkeypatch)

    output = run_t12_candidate(request)

    record = json.loads(output.command_json.read_text(encoding="utf-8"))
    assert output.refinement.execution_status is ExecutionStatus.COMPLETED_SUCCESS
    assert output.free_r_comparison is None
    assert record["schema_version"] == "1.0"
    assert record["protocol_version"] == "phenix-t12-brief-v5"
    assert "free_r_identity" not in record


def test_phase3_refinement_requires_free_r_identity(tmp_path: Path) -> None:
    request = replace(
        _phase3_request(tmp_path),
        free_r_identity_json=None,
    )

    with pytest.raises(T12InputError, match="Free-R identity"):
        run_t12_candidate(request)


def test_phase3_refinement_requires_exact_raw_source_mtz(tmp_path: Path) -> None:
    request = replace(_phase3_request(tmp_path), source_mtz=None)

    with pytest.raises(T12InputError, match="source MTZ"):
        run_t12_candidate(request)


def test_phase3_refinement_rejects_content_id_mutated_free_r_identity(
    tmp_path: Path,
) -> None:
    request = _phase3_request(tmp_path)
    assert request.free_r_identity_json is not None
    record = json.loads(request.free_r_identity_json.read_text(encoding="utf-8"))
    record["free_r_label"] = "mutated_without_recomputing_identity"
    request.free_r_identity_json.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(T12InputError, match="invalid Free-R identity"):
        run_t12_candidate(request)


def test_phase3_refinement_rejects_free_r_selection_mismatch(tmp_path: Path) -> None:
    request = _phase3_request(tmp_path)
    assert request.diffraction_selection_json is not None
    assert request.free_r_identity_json is not None
    selection = load_diffraction_selection(request.diffraction_selection_json)
    selection_values = selection.model_dump(
        mode="python",
        exclude={"diffraction_selection_id"},
    )
    selection_values["crystal_manifest_sha256"] = "e" * 64
    other_selection = DiffractionSelection.from_content(**selection_values)
    other_identity = build_free_r_identity(
        selection=other_selection,
        mtz_path=request.parent_mtz,
        free_r_dataset_id=1,
        free_r_label="FreeR_flag",
    )
    request.free_r_identity_json.write_text(
        canonical_json_text(other_identity),
        encoding="utf-8",
    )

    with pytest.raises(T12InputError, match="differs from the diffraction selection"):
        run_t12_candidate(request)


def test_phase3_refinement_promotes_permuted_synthetic_mtz_after_free_r_comparison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _phase3_request(tmp_path)
    order = (5, 2, 0, 4, 1, 3)
    commands = _install_phase3_runtime(
        monkeypatch,
        derived_hkl=tuple(_HKL[index] for index in order),
        derived_free_r_flags=tuple(_FREE_R_FLAGS[index] for index in order),
    )

    output = run_t12_candidate(request)

    record = json.loads(output.command_json.read_text(encoding="utf-8"))
    binding = record["diffraction_command_binding"]
    assert output.refinement.execution_status is ExecutionStatus.COMPLETED_SUCCESS
    assert output.free_r_comparison is not None
    assert output.free_r_comparison_json is not None
    assert output.free_r_comparison_json.is_file()
    assert output.free_r_comparison.preservation_status.startswith("preserved_exact")
    assert record["schema_version"] == "2.0"
    assert record["phase3_refine_command_id"].startswith("refinecmd_")
    assert record["phase3_sequence_command_id"].startswith("seqmapcmd_")
    assert record["diffraction_selection"]["observation_dataset_id"] == 1
    assert record["free_r_identity"]["free_r_label"] == "FreeR_flag"
    assert record["free_r_identity"]["convention_status"] == (
        "unresolved_raw_flag_values_only"
    )
    assert record["free_r_identity"]["test_flag_value"] is None
    assert record["free_r_membership_comparison_status"] == "preserved_exact"
    assert record["free_r_membership_comparison"]["comparison_id"] == (
        output.free_r_comparison.comparison_id
    )
    assert binding["resolution_command_binding"] == (
        "refinement_low_high_and_sequence_map_high_explicit"
    )
    assert binding["space_group_command_binding"] == (
        "explicit_refinement_crystal_symmetry_parameter"
    )
    assert binding["command_mtz_binding"] == (
        "verified_parent_hkl_free_r_and_observation_dataset"
    )
    assert record["parent_free_r_membership_comparison"]["derived_mtz_sha256"] == (
        request.parent_mtz_sha256
    )
    assert (
        record["inputs"]["source_mtz_sha256"]
        == (record["diffraction_selection"]["mtz_sha256"])
    )
    assert len(record["inputs"]["parent_observation_membership_sha256"]) == 64
    assert binding["free_r_label"] == "FreeR_flag"
    assert binding["free_r_convention_status"] == ("unresolved_raw_flag_values_only")
    assert binding["free_r_test_flag_value"] is None
    assert binding["free_r_command_binding"] == (
        "selected_label_explicit_generation_disabled_test_value_automatic"
    )
    assert "data_manager.miller_array.labels.name=I,SIGI" in commands[0]
    assert "data_manager.miller_array.labels.name=FreeR_flag" in commands[0]
    assert "data_manager.fmodel.xray_data.r_free_flags.required=True" in commands[0]
    assert "data_manager.fmodel.xray_data.r_free_flags.generate=False" in commands[0]
    assert not any("test_flag_value" in argument for argument in commands[0])
    assert (
        f"refinement.crystal_symmetry.space_group={binding['selected_space_group']}"
        in commands[0]
    )
    assert any(
        argument.startswith("data_manager.fmodel.xray_data.low_resolution=")
        for argument in commands[0]
    )
    assert "data_manager.fmodel.xray_data.high_resolution=2" in commands[0]
    assert "crystal_info.resolution=2" in commands[1]


def test_phase3_refinement_accepts_proven_derived_parent_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _phase3_request(tmp_path)
    _write_phase3_mtz(original.parent_mtz, include_map_coefficients=True)
    request = replace(
        original,
        parent_mtz_sha256=sha256_file(original.parent_mtz, progress=False),
    )
    commands = _install_phase3_runtime(monkeypatch)

    output = run_t12_candidate(request)

    record = json.loads(output.command_json.read_text(encoding="utf-8"))
    parent_proof = record["parent_free_r_membership_comparison"]
    assert len(commands) == 2
    assert output.refinement.execution_status is ExecutionStatus.COMPLETED_SUCCESS
    assert parent_proof["source_mtz_sha256"] != parent_proof["derived_mtz_sha256"]
    assert parent_proof["derived_mtz_sha256"] == request.parent_mtz_sha256


@pytest.mark.parametrize(
    ("observation_offset", "sigma_offset", "label"),
    ((1.0, 0.0, "I"), (0.0, 1.0, "SIGI")),
)
def test_phase3_refinement_rejects_changed_observations_before_phenix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_offset: float,
    sigma_offset: float,
    label: str,
) -> None:
    original = _phase3_request(tmp_path)
    _write_phase3_mtz(
        original.parent_mtz,
        observation_offset=observation_offset,
        sigma_offset=sigma_offset,
    )
    request = replace(
        original,
        parent_mtz_sha256=sha256_file(original.parent_mtz, progress=False),
    )
    commands = _install_phase3_runtime(monkeypatch)

    with pytest.raises(T12InputError, match=f"parent MTZ.*observation values.*{label}"):
        run_t12_candidate(request)

    assert commands == []


def test_phase3_refinement_accepts_permuted_parent_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _phase3_request(tmp_path)
    order = (5, 2, 0, 4, 1, 3)
    _write_phase3_mtz(
        original.parent_mtz,
        hkl=tuple(_HKL[index] for index in order),
        free_r_flags=tuple(_FREE_R_FLAGS[index] for index in order),
        include_map_coefficients=True,
    )
    request = replace(
        original,
        parent_mtz_sha256=sha256_file(original.parent_mtz, progress=False),
    )
    commands = _install_phase3_runtime(monkeypatch)

    output = run_t12_candidate(request)

    assert output.refinement.execution_status is ExecutionStatus.COMPLETED_SUCCESS
    assert len(commands) == 2


def test_phase3_refinement_rejects_changed_raw_source_before_phenix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _phase3_request(tmp_path)
    assert request.source_mtz is not None
    _write_phase3_mtz(request.source_mtz, observation_offset=1.0)
    commands = _install_phase3_runtime(monkeypatch)

    with pytest.raises(T12InputError, match="source MTZ checksum mismatch"):
        run_t12_candidate(request)

    assert commands == []


@pytest.mark.parametrize(
    ("flags", "observation_labels", "message"),
    (
        (
            (1, 1, 0, 0, 1, 0),
            ("I", "SIGI"),
            "parent MTZ.*changed the exact HKL-to-Free-R",
        ),
        (
            _FREE_R_FLAGS,
            ("OTHER", "SIGOTHER"),
            "parent MTZ lacks the selected observation dataset",
        ),
    ),
)
def test_phase3_refinement_rejects_unproven_parent_before_phenix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flags: tuple[int, ...],
    observation_labels: tuple[str, str],
    message: str,
) -> None:
    original = _phase3_request(tmp_path)
    _write_phase3_mtz(
        original.parent_mtz,
        free_r_flags=flags,
        observation_labels=observation_labels,
    )
    request = replace(
        original,
        parent_mtz_sha256=sha256_file(original.parent_mtz, progress=False),
    )
    commands = _install_phase3_runtime(monkeypatch)

    with pytest.raises(T12InputError, match=message):
        run_t12_candidate(request)

    assert commands == []


@pytest.mark.parametrize(
    ("include_free_r", "derived_flags", "error_fragment"),
    (
        (True, (1, 1, 0, 0, 1, 0), "changed the exact HKL-to-Free-R"),
        (False, _FREE_R_FLAGS, "Free-R label is missing"),
    ),
    ids=("changed-flag", "missing-flag-column"),
)
def test_phase3_refinement_refuses_changed_or_missing_free_r_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    include_free_r: bool,
    derived_flags: tuple[int, ...],
    error_fragment: str,
) -> None:
    request = _phase3_request(tmp_path)
    commands = _install_phase3_runtime(
        monkeypatch,
        derived_free_r_flags=derived_flags,
        include_free_r=include_free_r,
    )

    output = run_t12_candidate(request)

    record = json.loads(output.command_json.read_text(encoding="utf-8"))
    assert output.refinement.execution_status is ExecutionStatus.FAILED_PARSE
    assert output.refinement.refined_mtz_path is None
    assert output.sequence.execution_status is ExecutionStatus.SKIPPED_INELIGIBLE
    assert output.free_r_comparison is None
    assert output.free_r_comparison_json is None
    assert output.refinement.warnings == (
        "refined_mtz_free_r_membership_comparison_failed",
    )
    assert record["free_r_membership_comparison_status"] == "failed_contract"
    assert error_fragment in record["free_r_membership_comparison_error"]
    assert len(commands) == 1


def test_phase3_refinement_command_identity_changes_with_free_r_convention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unresolved_request = _phase3_request(tmp_path)
    assert unresolved_request.diffraction_selection_json is not None
    selection = load_diffraction_selection(
        unresolved_request.diffraction_selection_json
    )
    explicit_identity = build_free_r_identity(
        selection=selection,
        mtz_path=unresolved_request.parent_mtz,
        free_r_dataset_id=1,
        free_r_label="FreeR_flag",
        test_flag_value=1,
    )
    explicit_identity_path = tmp_path / "free_r_identity_explicit.json"
    explicit_identity_path.write_text(
        canonical_json_text(explicit_identity),
        encoding="utf-8",
    )
    explicit_request = replace(
        unresolved_request,
        free_r_identity_json=explicit_identity_path,
        output_directory=tmp_path / "refinement_explicit",
    )
    commands = _install_phase3_runtime(monkeypatch)

    unresolved = run_t12_candidate(unresolved_request)
    explicit = run_t12_candidate(explicit_request)

    unresolved_record = json.loads(unresolved.command_json.read_text(encoding="utf-8"))
    explicit_record = json.loads(explicit.command_json.read_text(encoding="utf-8"))
    assert (
        unresolved_record["diffraction_selection"]["diffraction_selection_id"]
        == (explicit_record["diffraction_selection"]["diffraction_selection_id"])
    )
    assert (
        unresolved_record["phase3_refine_command_id"]
        != (explicit_record["phase3_refine_command_id"])
    )
    assert unresolved_record["free_r_identity"]["convention_status"] == (
        FreeRConventionStatus.UNRESOLVED.value
    )
    assert unresolved_record["free_r_identity"]["test_flag_value"] is None
    assert explicit_record["free_r_identity"]["convention_status"] == (
        FreeRConventionStatus.EXPLICIT_TEST_VALUE.value
    )
    assert explicit_record["free_r_identity"]["test_flag_value"] == 1
    assert (
        unresolved_record["diffraction_command_binding"]["free_r_command_binding"]
        == "selected_label_explicit_generation_disabled_test_value_automatic"
    )
    assert (
        explicit_record["diffraction_command_binding"]["free_r_command_binding"]
        == "selected_label_and_test_value_explicit_generation_disabled"
    )
    assert not any("test_flag_value" in argument for argument in commands[0])
    assert "data_manager.fmodel.xray_data.r_free_flags.test_flag_value=1" in commands[2]
