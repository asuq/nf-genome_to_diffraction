"""Tests for first-copy Phaser execution, parsing, and credibility gates."""

import hashlib
import json
import shutil
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from genome_to_diffraction.cli import main
from genome_to_diffraction.diffraction.selection import (
    bind_phase3_hypothesis,
    build_diffraction_selection,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.model_registry import (
    ValidatedProcessedModelInput,
    build_all_eligible_model_registry,
)
from genome_to_diffraction.mr import (
    PhaserInputError,
    PhaserParseError,
    PhaserRunRequest,
    parse_phaser_log,
    read_phaser_solution_metrics,
    run_first_copy_phaser,
)
from genome_to_diffraction.mr_resources import build_mr_resource_plan
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    CrystalEntry,
    PhenixInstallManifest,
    PrototypeProfile,
)
from genome_to_diffraction.schemas.results import (
    CoordinateSourceRecord,
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    MtzObservationCandidateRecord,
    MtzPreflightRecord,
    ProcessedModelRecord,
    SequenceGroupRecord,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
PHASER_FIXTURES = REPOSITORY / "tests/fixtures/phaser"
SEQUENCE_GROUP_ID = (
    "seq_f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e"
)
MODEL_ID = "model_" + "a" * 64
HYPOTHESIS_ID = "mrhyp_" + "d" * 64
POSITIVE_LOG = (PHASER_FIXTURES / "phenix_2_1_positive.log").read_text(encoding="utf-8")
NO_SOLUTION_LOG = (PHASER_FIXTURES / "phenix_2_1_no_solution.log").read_text(
    encoding="utf-8"
)
PACKING_NO_SOLUTION_LOG = (
    PHASER_FIXTURES / "phenix_2_1_no_solution_packing.log"
).read_text(encoding="utf-8")


def _inputs(tmp_path: Path) -> PhaserRunRequest:
    tmp_path.mkdir(parents=True, exist_ok=True)
    model_preparation = tmp_path / "model preparation with spaces"
    shutil.copytree(STUBS / "predicted_model_preparation", model_preparation)
    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=HYPOTHESIS_ID,
        crystal_id="test_crystal_01",
        sequence_group_id=SEQUENCE_GROUP_ID,
        model_id=MODEL_ID,
        copy_count_expected=2,
        copy_number_to_search=1,
        fixed_solution_id=None,
        space_group="P 21 21 21",
        obs_labels="I,SIGI",
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.PILOT,
        priority_features={"exact_sequence_mapping": True},
        status=MrHypothesisStatus.QUEUED,
    )
    hypotheses = tmp_path / "MR hypotheses.jsonl"
    hypotheses.write_text(f"{canonical_json_text(hypothesis)}\n", encoding="utf-8")
    mtz = tmp_path / "input data.mtz"
    mtz.write_bytes(b"synthetic MTZ boundary fixture")
    stub_preflight = MtzPreflightRecord.model_validate_json(
        (STUBS / "mtz_preflight.jsonl").read_text(encoding="utf-8")
    )
    preflight = stub_preflight.model_copy(
        update={
            "mtz_sha256": hashlib.sha256(mtz.read_bytes()).hexdigest(),
            "selected_observation_dataset_id": 1,
            "observation_candidate_identities": (
                MtzObservationCandidateRecord(
                    dataset_id=1,
                    labels=("I", "SIGI"),
                    observation_type="intensity",
                ),
            ),
        }
    )
    preflights = tmp_path / "MTZ preflight.jsonl"
    preflights.write_text(f"{canonical_json_text(preflight)}\n", encoding="utf-8")
    return PhaserRunRequest(
        hypotheses_jsonl=hypotheses,
        hypothesis_id=HYPOTHESIS_ID,
        sequence_groups_jsonl=STUBS / "sequence_groups.jsonl",
        processed_models_jsonl=model_preparation / "processed_models.jsonl",
        model_preparation_manifest=(
            model_preparation / "model_preparation_manifest.json"
        ),
        preflight_jsonl=preflights,
        mtz=mtz,
        phenix_manifest=STUBS / "phenix_install_manifest.json",
        output_directory=tmp_path / "Phaser output with spaces",
        threads=4,
        progress=False,
    )


def _phase3_inputs(
    tmp_path: Path,
    *,
    resolution_high_a: float = 2.0,
) -> PhaserRunRequest:
    request = _inputs(tmp_path)
    preflight = MtzPreflightRecord.model_validate_json(
        request.preflight_jsonl.read_text(encoding="utf-8")
    )
    payload = preflight.model_dump(mode="python")
    payload["resolution_high_a"] = resolution_high_a
    preflight = MtzPreflightRecord.model_validate(payload)
    request.preflight_jsonl.write_text(
        f"{canonical_json_text(preflight)}\n",
        encoding="utf-8",
    )
    crystal = CrystalEntry(
        crystal_id=preflight.crystal_id,
        mtz=str(request.mtz),
        catalogue_id="catalogue_test",
    )
    selection = build_diffraction_selection(
        crystal=crystal,
        preflight=preflight,
        crystal_manifest_sha256="e" * 64,
    )
    selection_path = tmp_path / "diffraction_selection.json"
    selection_path.write_text(canonical_json_text(selection), encoding="utf-8")
    resource_plan = build_mr_resource_plan(
        owner_kind="mr_hypothesis",
        owner_id=HYPOTHESIS_ID,
        reflection_count=1_000,
        moving_atom_count=4,
        searched_copy_count=1,
        fixed_atom_count=0,
        symmetry_multiplicity=4,
    )
    resource_plan_path = tmp_path / "mr_resource_plan.json"
    resource_plan_path.write_text(
        canonical_json_text(resource_plan),
        encoding="utf-8",
    )
    hypothesis = MrHypothesis.model_validate_json(
        request.hypotheses_jsonl.read_text(encoding="utf-8")
    )
    bound = bind_phase3_hypothesis(hypothesis, selection)
    model = ProcessedModelRecord.model_validate_json(
        request.processed_models_jsonl.read_text(encoding="utf-8")
    )
    group = SequenceGroupRecord.model_validate_json(
        request.sequence_groups_jsonl.read_text(encoding="utf-8")
    )
    coordinate = CoordinateSourceRecord(
        schema_version="1.0",
        coordinate_id=model.coordinate_id,
        provider="afdb",
        provider_accession="AF-STUB-F1",
        retrieval_date=datetime(2026, 8, 23, tzinfo=UTC),
        source_release="v6",
        coordinate_path="coordinates/stub.cif",
        coordinate_sha256="b" * 64,
        source_sequence_sha256=group.sha256,
        confidence_summary={"mean_plddt": 93.8},
        license_or_provenance="Phase III first-copy registry fixture",
    )
    assert request.model_preparation_manifest is not None
    registry = build_all_eligible_model_registry(
        models=(
            ValidatedProcessedModelInput(
                model=model,
                coordinate=coordinate,
                sequence_group=group,
                model_path=(
                    request.model_preparation_manifest.parent / "models/stub.pdb"
                ),
                retained_fraction=1.0,
            ),
        ),
        sequence_groups=(group,),
        output_directory=tmp_path / "canonical phase3 registry",
    )
    return replace(
        request,
        processed_models_jsonl=registry.processed_models_jsonl,
        model_preparation_manifest=None,
        all_model_registry_json=registry.registry_json,
        diffraction_selection_json=selection_path,
        resource_plan_json=resource_plan_path,
        phase3_hypothesis_id=bound.hypothesis_id,
    )


def _experimental_inputs(tmp_path: Path) -> PhaserRunRequest:
    request = _inputs(tmp_path)
    assert request.model_preparation_manifest is not None
    preparation = request.model_preparation_manifest.parent
    shutil.rmtree(preparation)
    shutil.copytree(STUBS / "experimental_model_preparation", preparation)
    model = ProcessedModelRecord.model_validate_json(
        request.processed_models_jsonl.read_text(encoding="utf-8")
    )
    parameters = dict(model.processing_parameters)
    parameters["sequence_identity"] = 0.625
    model = model.model_copy(update={"processing_parameters": parameters})
    request.processed_models_jsonl.write_text(
        f"{canonical_json_text(model)}\n", encoding="utf-8"
    )
    hypothesis = MrHypothesis.model_validate_json(
        request.hypotheses_jsonl.read_text(encoding="utf-8")
    ).model_copy(
        update={
            "model_id": model.model_id,
            "priority_features": {
                "exact_sequence_mapping": False,
                "structural_source_class": "experimental",
                "coordinate_mapping_id": parameters["mapping_id"],
                "candidate_source_sequence_identity": 0.625,
            },
        }
    )
    request.hypotheses_jsonl.write_text(
        f"{canonical_json_text(hypothesis)}\n", encoding="utf-8"
    )
    return request


def _unrelated_control_inputs(tmp_path: Path) -> PhaserRunRequest:
    request = _experimental_inputs(tmp_path)
    model = ProcessedModelRecord.model_validate_json(
        request.processed_models_jsonl.read_text(encoding="utf-8")
    )
    parameters = dict(model.processing_parameters)
    parameters.pop("mapping_id")
    parameters.pop("sequence_identity")
    parameters.update(
        {
            "control_role": "deliberate_unrelated_negative",
            "phaser_identity_percent": 1.0,
            "relationship_to_target": "deliberately_unrelated",
            "identity_interpretation": "error_model_input_not_sequence_homology",
        }
    )
    model = model.model_copy(
        update={
            "variant_type": "control_unrelated_cleaned_source_chain",
            "processing_parameters": parameters,
        }
    )
    request.processed_models_jsonl.write_text(
        f"{canonical_json_text(model)}\n", encoding="utf-8"
    )
    hypothesis = MrHypothesis.model_validate_json(
        request.hypotheses_jsonl.read_text(encoding="utf-8")
    ).model_copy(
        update={
            "model_id": model.model_id,
            "priority_features": {
                "control_role": "deliberate_unrelated_negative",
                "exact_sequence_mapping": False,
                "structural_source_class": "deliberate_unrelated_control",
                "phaser_identity_percent": 1.0,
                "identity_interpretation": ("error_model_input_not_sequence_homology"),
            },
        }
    )
    request.hypotheses_jsonl.write_text(
        f"{canonical_json_text(hypothesis)}\n", encoding="utf-8"
    )
    return request


def _manifest() -> PhenixInstallManifest:
    model = load_contract(
        STUBS / "phenix_install_manifest.json",
        "phenix-install-manifest",
        progress=False,
    )
    assert isinstance(model, PhenixInstallManifest)
    return model


def _fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    log_text: str,
    returncode: int = 0,
    write_solution: bool = False,
    pdb_llg: float = 1622.879,
    pdb_tfz: float = 49.7,
    pdb_pak: float | None = 0.0,
    placement_count: int = 1,
    corrupt_evidence: str | None = None,
    capture_bytes: bytes = b"capture\n",
    write_native_log: bool = True,
) -> list[list[str]]:
    commands: list[list[str]] = []

    def fake_validate(path: Path) -> PhenixInstallManifest:
        del path
        return _manifest()

    def fake_capture(
        manifest_path: Path,
        arguments: list[str],
        *,
        working_directory: Path,
        timeout_seconds: float | None,
    ) -> subprocess.CompletedProcess[bytes]:
        del manifest_path, timeout_seconds
        commands.append(arguments)
        working_directory.mkdir(parents=True, exist_ok=True)
        if write_native_log:
            (working_directory / "PHASER.log").write_text(log_text, encoding="utf-8")
        if write_solution:
            placements = "".join(
                "REMARK ENSEMBLE ense_1 EULER 1 2 3 FRAC 0.1 0.2 0.3\n"
                for _ in range(placement_count)
            )
            packing = "" if pdb_pak is None else f"PAK={pdb_pak:g} "
            (working_directory / "PHASER.1.pdb").write_text(
                "REMARK Log-Likelihood Gain: "
                f"{pdb_llg}\n"
                f"REMARK {packing}LLG={pdb_llg} TFZ=={pdb_tfz}\n"
                f"{placements}"
                "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  "
                "1.00 20.00           C\n",
                encoding="utf-8",
            )
            (working_directory / "PHASER.1.mtz").write_bytes(b"phaser MTZ")
        if corrupt_evidence is not None:
            evidence = working_directory / corrupt_evidence
            evidence.write_bytes(evidence.read_bytes() + b"\xff")
        return subprocess.CompletedProcess(arguments, returncode, capture_bytes, b"")

    monkeypatch.setattr(
        "genome_to_diffraction.mr.phaser.validate_manifest_environment",
        fake_validate,
    )
    monkeypatch.setattr(
        "genome_to_diffraction.mr.phaser.capture_from_manifest", fake_capture
    )
    return commands


def test_real_format_parser_uses_final_packing_and_retains_advisory() -> None:
    parsed = parse_phaser_log(POSITIVE_LOG)

    assert parsed.phaser_version == "2.8.4"
    assert parsed.solution_count == 2
    assert parsed.llg == pytest.approx(1622.91)
    assert parsed.tfz == pytest.approx(49.7)
    assert parsed.accepted_solution_count == 2
    assert parsed.packed_solution_count == 2
    assert parsed.parser_warnings == ("phaser_advisory_top_ftf_did_not_pack",)


@pytest.mark.parametrize("annotation", ("", "SOLU SET PAK=1\n"))
def test_parser_rejects_single_solution_without_explicit_packing(
    annotation: str,
) -> None:
    log = (
        POSITIVE_LOG.replace(
            "2 accepted of 2 solutions\n2 pack of 2 accepted solutions\n", ""
        )
        .replace("** There were 2 solutions", f"{annotation}** SINGLE solution")
        .replace("\nADVISORY\nThe top solution from a FTF did not pack\n", "")
    )

    with pytest.raises(PhaserParseError, match="final packing evidence"):
        parse_phaser_log(log)


def test_parser_accepts_phenix_single_solution_summary() -> None:
    log = (
        POSITIVE_LOG.replace(
            "2 accepted of 2 solutions\n2 pack of 2 accepted solutions\n", ""
        )
        .replace("** There were 2 solutions", "SOLU SET PAK=0\n** SINGLE solution")
        .replace("\nADVISORY\nThe top solution from a FTF did not pack\n", "")
    )

    parsed = parse_phaser_log(log)

    assert parsed.solution_count == 1
    assert parsed.accepted_solution_count == 1
    assert parsed.packed_solution_count == 1
    assert parsed.parser_warnings == ("single_solution_packing_verified_from_pak",)


def test_solution_pdb_llg_accepts_scientific_notation(tmp_path: Path) -> None:
    coordinate = tmp_path / "PHASER.1.pdb"
    coordinate.write_text(
        "REMARK Log-Likelihood Gain: 2.47e+05\n"
        "REMARK PAK=0 LLG=246594 TFZ==371.4\n"
        "REMARK ENSEMBLE fixed_parent EULER 0 0 0 FRAC 0 0 0\n"
        "REMARK ENSEMBLE search_partner EULER 1 2 3 FRAC 0.1 0.2 0.3\n",
        encoding="ascii",
    )

    llg, tfz, placed_count, pak = read_phaser_solution_metrics(
        parse_phaser_log(POSITIVE_LOG), coordinate
    )

    assert llg == pytest.approx(247000.0)
    assert tfz == pytest.approx(371.4)
    assert placed_count == 2
    assert pak == pytest.approx(0.0)


def test_solution_pdb_rejects_non_utf8_scientific_evidence(tmp_path: Path) -> None:
    coordinate = tmp_path / "PHASER.1.pdb"
    coordinate.write_bytes(
        b"REMARK Log-Likelihood Gain: 247000\n"
        b"REMARK PAK=0 LLG=246594 TFZ==371.4\n"
        b"REMARK ENSEMBLE search_partner EULER 1 2 3 FRAC 0.1 0.2 0.3\n"
        b"\xff"
    )

    with pytest.raises(PhaserParseError, match="not valid UTF-8"):
        read_phaser_solution_metrics(parse_phaser_log(POSITIVE_LOG), coordinate)


@pytest.mark.parametrize(
    "annotation_header",
    ("Solution #1 annotation (history):", "Solution annotation (history):"),
)
def test_parser_retains_top_solution_tfz_when_tncs_omits_refined_value(
    annotation_header: str,
) -> None:
    parsed = parse_phaser_log(
        "PHENIX: Phaser 2.8.4\n"
        "Top LLG (packs) = 1601.02\n"
        "7 accepted of 7 solutions\n"
        "7 pack of 7 accepted solutions\n"
        "** There were 7 solutions\n"
        f"{annotation_header}\n"
        "SOLU SET RFZ=10.8 TFZ=14.2 +TNCS PAK=0 LLG=1601\n"
        "EXIT STATUS: SUCCESS\n"
    )

    assert parsed.llg == pytest.approx(1601.02)
    assert parsed.tfz == pytest.approx(14.2)
    assert parsed.parser_warnings == ("tfz_from_top_solution_annotation",)


def test_parser_uses_final_singular_packing_summary() -> None:
    parsed = parse_phaser_log(
        "PHENIX: Phaser 2.8.4\n"
        "13 accepted of 13 solutions\n"
        "13 pack of 13 accepted solutions\n"
        "Top LLG (packs) = 3507.7\n"
        "1 accepted of 1 solutions\n"
        "1 packs of 1 accepted solution\n"
        "** SINGLE solution\n"
        "Solution annotation (history):\n"
        "SOLU SET RFZ=20.8 TFZ=19.3 +TNCS PAK=3 LLG=3508 PAK=0\n"
        "EXIT STATUS: SUCCESS\n"
    )

    assert parsed.solution_count == 1
    assert parsed.llg == pytest.approx(3507.7)
    assert parsed.tfz == pytest.approx(19.3)
    assert parsed.accepted_solution_count == 1
    assert parsed.packed_solution_count == 1


def test_parser_rejects_solution_without_final_packing() -> None:
    with pytest.raises(PhaserParseError, match="final packing evidence"):
        parse_phaser_log(
            POSITIVE_LOG.replace(
                "2 accepted of 2 solutions\n2 pack of 2 accepted solutions\n", ""
            )
        )


def test_real_no_solution_format_uses_terminal_marker_and_packing() -> None:
    parsed = parse_phaser_log(PACKING_NO_SOLUTION_LOG)

    assert parsed.phaser_version == "2.8.4"
    assert parsed.solution_count == 0
    assert parsed.accepted_solution_count == 0
    assert parsed.packed_solution_count == 0
    assert parsed.llg is None
    assert parsed.tfz is None
    assert parsed.parser_warnings == ()


def test_partial_solution_phrase_is_not_zero_solution_evidence() -> None:
    with pytest.raises(PhaserParseError, match="final packing evidence"):
        parse_phaser_log(
            "** There was 1 solution\n"
            "** Sorry - No solution with all components\n"
            "EXIT STATUS: SUCCESS\n"
        )


def test_adapter_runs_exact_composition_and_emits_credible_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _inputs(tmp_path)
    commands = _fake_runtime(monkeypatch, log_text=POSITIVE_LOG, write_solution=True)

    output = run_first_copy_phaser(request)

    assert output.result.execution_status == "completed_hit"
    assert output.result.llg == pytest.approx(1622.879)
    assert output.result.tfz == pytest.approx(49.7)
    assert output.result.placed_copy_count == 1
    assert output.result.packing_summary["score_gate_passed"] is True
    assert output.result.packing_summary["score_gate_operator"] == "or"
    assert output.result.packing_summary["score_gate_llg_strictly_greater_than"] == 50.0
    assert output.result.packing_summary["score_gate_tfz_strictly_greater_than"] == 5.0
    assert output.result.parser_warnings == ("phaser_advisory_top_ftf_did_not_pack",)
    command = commands[0]
    assert "phaser.model_identity=100" in command
    assert "phaser.component_copies=2" in command
    assert "phaser.search_copies=1" in command
    assert "phaser.keywords.general.jobs=4" in command
    assert "phaser.keywords.sgalternative.select=none" in command
    record = json.loads(output.command_json.read_text(encoding="utf-8"))
    assert record["adapter_version"] == "phenix-first-copy-mr-v8"
    assert record["model_uncertainty_source"].startswith("phenix.process")


def test_phase3_adapter_verifies_and_records_dataset_qualified_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _phase3_inputs(tmp_path)
    commands = _fake_runtime(monkeypatch, log_text=PACKING_NO_SOLUTION_LOG)

    output = run_first_copy_phaser(request)

    record = json.loads(output.command_json.read_text(encoding="utf-8"))
    binding = record["diffraction_command_binding"]
    selection = record["diffraction_selection"]
    assert record["schema_version"] == "2.0"
    assert record["adapter_version"] == "phenix-first-copy-mr-v12-resource-plan"
    assert record["phase3_hypothesis_id"] == request.phase3_hypothesis_id
    assert record["phase3_command_id"].startswith("phasercmd_")
    command_identity = {
        "adapter_version": record["adapter_version"],
        "phase3_hypothesis_id": record["phase3_hypothesis_id"],
        "diffraction_selection_id": selection["diffraction_selection_id"],
        "diffraction_command_binding_id": binding["binding_id"],
        "arguments": record["arguments"],
        "threads": record["threads"],
        "resource_attempt": record["resource_attempt"],
        "resource_plan_id": record["resource_plan"]["resource_plan_id"],
        "timeout_seconds": record["timeout_seconds"],
        "mtz_sha256": record["mtz_sha256"],
        "model_sha256": record["model_sha256"],
        "sequence_sha256": record["sequence_sha256"],
        "phenix_manifest_sha256": record["phenix_manifest_sha256"],
        "all_model_registry_id": record["all_model_registry_id"],
        "all_model_registry_sha256": record["all_model_registry_sha256"],
    }
    assert content_id("phasercmd_", command_identity) == record["phase3_command_id"]
    previous_identity = {
        **command_identity,
        "adapter_version": "phenix-first-copy-mr-v9-phase3-diffraction",
    }
    assert content_id("phasercmd_", previous_identity) != record["phase3_command_id"]
    assert selection["observation_dataset_id"] == 1
    assert selection["observation_labels"] == ["I", "SIGI"]
    assert binding["observation_command_binding"].startswith("explicit_parameter")
    assert binding["space_group_command_binding"] == (
        "explicit_phaser_crystal_symmetry_parameter"
    )
    assert binding["resolution_command_binding"] == (
        "explicit_phaser_resolution_low_high_parameters"
    )
    assert binding["command_mtz_binding"] == "exact_selected_mtz"
    assert "phaser.labin=I,SIGI" in commands[0]
    assert "phaser.crystal_symmetry.space_group=P 21 21 21" in commands[0]
    assert (
        f"phaser.keywords.resolution.low={selection['resolution_low_a']:.12g}"
        in commands[0]
    )
    assert (
        f"phaser.keywords.resolution.high={selection['resolution_high_a']:.12g}"
        in commands[0]
    )


def test_phase3_adapter_derives_bound_hypothesis_from_complete_task_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit = _phase3_inputs(tmp_path)
    request = replace(
        explicit,
        phase3_hypothesis_id=None,
        derive_phase3_hypothesis_id=True,
    )
    commands = _fake_runtime(monkeypatch, log_text=PACKING_NO_SOLUTION_LOG)

    output = run_first_copy_phaser(request)

    record = json.loads(output.command_json.read_text(encoding="utf-8"))
    assert record["phase3_hypothesis_id"] == explicit.phase3_hypothesis_id
    assert record["all_model_registry_id"].startswith("allmodelreg_")
    assert record["diffraction_selection"]["observation_dataset_id"] == 1
    assert "phaser.crystal_symmetry.space_group=P 21 21 21" in commands[0]


def test_phase3_adapter_requires_matching_resource_plan_and_threads(
    tmp_path: Path,
) -> None:
    missing = _phase3_inputs(tmp_path / "missing")
    missing = replace(missing, resource_plan_json=None)
    with pytest.raises(PhaserInputError, match="must be paired"):
        run_first_copy_phaser(missing)

    mismatched = replace(_phase3_inputs(tmp_path / "mismatched"), threads=6)
    with pytest.raises(PhaserInputError, match="threads differ"):
        run_first_copy_phaser(mismatched)

    swapped = _phase3_inputs(tmp_path / "swapped")
    assert swapped.resource_plan_json is not None
    swapped.resource_plan_json.write_text(
        canonical_json_text(
            build_mr_resource_plan(
                owner_kind="mr_hypothesis",
                owner_id="mrhyp_another_hypothesis",
                reflection_count=1_000,
                moving_atom_count=4,
                searched_copy_count=1,
                fixed_atom_count=0,
                symmetry_multiplicity=4,
            )
        ),
        encoding="utf-8",
    )
    with pytest.raises(PhaserInputError, match="resource plan is invalid"):
        run_first_copy_phaser(swapped)


def test_production_phase3_nextflow_requires_bound_crystal_diffraction_inputs() -> None:
    dispatch = (REPOSITORY / "modules/local/dispatch_crystal_item.nf").read_text(
        encoding="ascii"
    )
    phaser = (
        REPOSITORY / "modules/local/phase3_multicrystal_first_copy_tasks.nf"
    ).read_text(encoding="ascii")

    assert "--phase3-diffraction" in dispatch
    assert "--diffraction-selection '${item[3]}/phase3_diffraction_selection.json'" in (
        phaser
    )
    assert "--derive-phase3-hypothesis-id" in phaser
    assert (
        "--all-model-registry "
        "'${item[2]}/model_registry/all_model_registry.json'" in phaser
    )
    assert "--model-preparation-manifest" not in phaser


@pytest.mark.parametrize("invalid", ("legacy", "both", "foreign_records", "tampered"))
def test_phase3_adapter_rejects_noncanonical_model_authority_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid: str,
) -> None:
    request = _phase3_inputs(tmp_path)
    assert request.all_model_registry_json is not None
    legacy = tmp_path / "model preparation with spaces/model_preparation_manifest.json"
    if invalid == "legacy":
        request = replace(
            request,
            model_preparation_manifest=legacy,
            all_model_registry_json=None,
        )
        expected = "canonical all-model registry"
    elif invalid == "both":
        request = replace(request, model_preparation_manifest=legacy)
        expected = "exactly one model authority"
    elif invalid == "foreign_records":
        foreign = tmp_path / "foreign processed models.jsonl"
        foreign.write_bytes(request.processed_models_jsonl.read_bytes())
        request = replace(request, processed_models_jsonl=foreign)
        expected = "processed-model records differ"
    else:
        model = next((request.all_model_registry_json.parent / "models").rglob("*.pdb"))
        model.write_bytes(b"tampered coordinate evidence")
        expected = "invalid all-model registry authority"
    commands = _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG)

    with pytest.raises(PhaserInputError, match=expected):
        run_first_copy_phaser(request)

    assert commands == []
    assert not request.output_directory.exists()


@pytest.mark.parametrize("ambiguous", ("missing", "both", "selection_missing"))
def test_phase3_adapter_rejects_ambiguous_hypothesis_identity_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ambiguous: str,
) -> None:
    request = _phase3_inputs(tmp_path)
    if ambiguous == "missing":
        request = replace(request, phase3_hypothesis_id=None)
    elif ambiguous == "both":
        request = replace(request, derive_phase3_hypothesis_id=True)
    else:
        request = replace(
            request,
            diffraction_selection_json=None,
            resource_plan_json=None,
            phase3_hypothesis_id=None,
            derive_phase3_hypothesis_id=True,
        )
    commands = _fake_runtime(monkeypatch, log_text=PACKING_NO_SOLUTION_LOG)

    with pytest.raises(PhaserInputError, match="hypothesis identity"):
        run_first_copy_phaser(request)

    assert commands == []


def test_phase3_adapter_rejects_bound_hypothesis_mismatch_before_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = replace(
        _phase3_inputs(tmp_path),
        phase3_hypothesis_id="mrhyp2_" + "0" * 64,
    )
    commands = _fake_runtime(monkeypatch, log_text=PACKING_NO_SOLUTION_LOG)

    with pytest.raises(PhaserInputError, match="bound hypothesis identity differs"):
        run_first_copy_phaser(request)

    assert commands == []


def test_phase3_command_record_identity_changes_with_resolution_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_request = _phase3_inputs(tmp_path / "first", resolution_high_a=2.0)
    second_request = _phase3_inputs(tmp_path / "second", resolution_high_a=1.8)
    _fake_runtime(monkeypatch, log_text=PACKING_NO_SOLUTION_LOG)

    first = json.loads(
        run_first_copy_phaser(first_request).command_json.read_text(encoding="utf-8")
    )
    second = json.loads(
        run_first_copy_phaser(second_request).command_json.read_text(encoding="utf-8")
    )

    assert first["phase3_hypothesis_id"] != second["phase3_hypothesis_id"]
    assert first["phase3_command_id"] != second["phase3_command_id"]


def test_adapter_can_search_declared_copies_jointly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _inputs(tmp_path)
    hypothesis = MrHypothesis.model_validate_json(
        request.hypotheses_jsonl.read_text(encoding="utf-8")
    ).model_copy(update={"copy_number_to_search": 2})
    request.hypotheses_jsonl.write_text(
        f"{canonical_json_text(hypothesis)}\n", encoding="utf-8"
    )
    commands = _fake_runtime(
        monkeypatch,
        log_text=POSITIVE_LOG,
        write_solution=True,
        placement_count=2,
    )
    log_extras: list[dict[str, object]] = []

    def capture_info(message: str, *, extra: dict[str, object]) -> None:
        if message == "first-copy Phaser search started":
            log_extras.append(extra)

    monkeypatch.setattr("genome_to_diffraction.mr.phaser._LOGGER.info", capture_info)

    output = run_first_copy_phaser(request)

    assert output.result.placed_copy_count == 2
    assert "phaser.component_copies=2" in commands[0]
    assert "phaser.search_copies=2" in commands[0]
    assert log_extras == [
        {
            "hypothesis_id": hypothesis.hypothesis_id,
            "copy_count_expected": 2,
            "copy_number_to_search": 2,
            "model_identity_percent": 100.0,
            "threads": 4,
            "output_directory": str(request.output_directory.absolute()),
        }
    ]


def test_adapter_uses_complete_solution_files_when_log_omits_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _inputs(tmp_path)
    _fake_runtime(
        monkeypatch,
        log_text="PHENIX: Phaser 2.8.4\nEXIT STATUS: SUCCESS\n",
        write_solution=True,
    )

    output = run_first_copy_phaser(request)

    assert output.result.execution_status == "completed_hit"
    assert output.result.packing_summary["solution_count"] == 1
    assert output.result.packing_summary["top_solution_packed"] is True
    assert output.result.parser_warnings == (
        "solution_count_verified_from_output_files",
        "packing_verified_from_solution_pak",
    )


@pytest.mark.parametrize("pdb_pak", (None, 1.0))
def test_adapter_rejects_output_only_solution_without_explicit_packing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pdb_pak: float | None,
) -> None:
    request = _inputs(tmp_path)
    _fake_runtime(
        monkeypatch,
        log_text="PHENIX: Phaser 2.8.4\nEXIT STATUS: SUCCESS\n",
        write_solution=True,
        pdb_pak=pdb_pak,
    )

    output = run_first_copy_phaser(request)

    assert output.result.execution_status == "failed_parse"
    assert (
        output.result.rejection_reason == "Phaser solution lacks final packing evidence"
    )


@pytest.mark.parametrize("corrupt_evidence", ("PHASER.log", "PHASER.1.pdb"))
def test_adapter_rejects_non_utf8_native_scientific_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corrupt_evidence: str,
) -> None:
    request = _inputs(tmp_path)
    _fake_runtime(
        monkeypatch,
        log_text=POSITIVE_LOG,
        write_solution=True,
        corrupt_evidence=corrupt_evidence,
    )

    result = run_first_copy_phaser(request).result

    assert result.execution_status == "failed_parse"
    assert "not valid UTF-8" in (result.rejection_reason or "")
    assert result.solution_coordinate_path is None


@pytest.mark.parametrize("write_native_log", (False, True))
def test_capture_bytes_are_preserved_and_parsed_only_when_authoritative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_native_log: bool,
) -> None:
    request = _inputs(tmp_path)
    capture = POSITIVE_LOG.encode("utf-8") + b"\xff"
    _fake_runtime(
        monkeypatch,
        log_text=POSITIVE_LOG,
        write_solution=True,
        capture_bytes=capture,
        write_native_log=write_native_log,
    )

    result = run_first_copy_phaser(request).result

    assert (request.output_directory / "phenix.phaser.capture.log").read_bytes() == (
        capture
    )
    if write_native_log:
        assert result.execution_status == "completed_hit"
        assert result.raw_log_pointer == "PHASER.log"
    else:
        assert result.execution_status == "failed_parse"
        assert result.raw_log_pointer == "phenix.phaser.capture.log"


def test_adapter_does_not_infer_no_hit_from_marker_free_empty_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _inputs(tmp_path)
    _fake_runtime(
        monkeypatch,
        log_text="PHENIX: Phaser 2.8.4\nEXIT STATUS: SUCCESS\n",
    )

    output = run_first_copy_phaser(request)

    assert output.result.execution_status == "failed_parse"
    assert output.result.rejection_reason == "Phaser log lacks a final solution count"


def test_adapter_uses_registered_experimental_sequence_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _experimental_inputs(tmp_path)
    commands = _fake_runtime(monkeypatch, log_text=PACKING_NO_SOLUTION_LOG)

    output = run_first_copy_phaser(request)

    assert output.result.execution_status == "completed_no_hit"
    assert "phaser.model_identity=62.5" in commands[0]
    record = json.loads(output.command_json.read_text(encoding="utf-8"))
    assert record["model_identity_percent"] == pytest.approx(62.5)
    assert record["model_uncertainty_source"].startswith("registered PDB")


def test_adapter_rejects_experimental_identity_drift(tmp_path: Path) -> None:
    request = _experimental_inputs(tmp_path)
    hypothesis = MrHypothesis.model_validate_json(
        request.hypotheses_jsonl.read_text(encoding="utf-8")
    )
    features = dict(hypothesis.priority_features)
    features["candidate_source_sequence_identity"] = 0.5
    changed = hypothesis.model_copy(update={"priority_features": features})
    request.hypotheses_jsonl.write_text(
        f"{canonical_json_text(changed)}\n",
        encoding="utf-8",
    )

    with pytest.raises(PhaserInputError, match="sequence identities differ"):
        run_first_copy_phaser(request)


def test_adapter_uses_fixed_unrelated_negative_control_error_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _unrelated_control_inputs(tmp_path)
    commands = _fake_runtime(monkeypatch, log_text=PACKING_NO_SOLUTION_LOG)

    output = run_first_copy_phaser(request)

    assert output.result.execution_status == "completed_no_hit"
    assert "phaser.model_identity=1" in commands[0]
    record = json.loads(output.command_json.read_text(encoding="utf-8"))
    assert record["model_identity_percent"] == 1.0
    assert "not sequence homology" in record["model_uncertainty_source"]


def test_adapter_rejects_unrelated_control_identity_drift(tmp_path: Path) -> None:
    request = _unrelated_control_inputs(tmp_path)
    model = ProcessedModelRecord.model_validate_json(
        request.processed_models_jsonl.read_text(encoding="utf-8")
    )
    parameters = dict(model.processing_parameters)
    parameters["phaser_identity_percent"] = 2.0
    changed = model.model_copy(update={"processing_parameters": parameters})
    request.processed_models_jsonl.write_text(
        f"{canonical_json_text(changed)}\n",
        encoding="utf-8",
    )

    with pytest.raises(PhaserInputError, match="negative-control policy"):
        run_first_copy_phaser(request)


@pytest.mark.parametrize(
    ("llg", "tfz", "expected_screen_priority"),
    (
        (50.0, 5.0, False),
        (50.0, 5.1, True),
        (50.1, 5.0, True),
        (49.9, 4.9, False),
    ),
)
def test_score_screen_ranks_without_discarding_parsed_solutions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    llg: float,
    tfz: float,
    expected_screen_priority: bool,
) -> None:
    request = _inputs(tmp_path)
    _fake_runtime(
        monkeypatch,
        log_text=POSITIVE_LOG,
        write_solution=True,
        pdb_llg=llg,
        pdb_tfz=tfz,
    )

    result = run_first_copy_phaser(request).result

    assert result.execution_status == "completed_hit"
    assert result.packing_summary["score_gate_passed"] is expected_screen_priority
    assert result.preliminary_credibility_class == (
        "screen_priority"
        if expected_screen_priority
        else "screen_retained_below_numeric_threshold"
    )
    assert result.rejection_reason is None
    assert result.packing_summary["review_advisories"] == (
        [] if expected_screen_priority else ["provisional_llg_or_tfz_screen_not_met"]
    )


def test_adapter_records_scientific_no_solution_without_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _inputs(tmp_path)
    _fake_runtime(monkeypatch, log_text=PACKING_NO_SOLUTION_LOG)

    result = run_first_copy_phaser(request).result

    assert result.execution_status == "completed_no_hit"
    assert result.preliminary_credibility_class == "no_solution"
    assert result.rejection_reason == "phaser_reported_no_solution"


def test_adapter_records_tool_and_parse_failures_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool_request = _inputs(tmp_path / "tool")
    _fake_runtime(monkeypatch, log_text="native failure\n", returncode=7)
    tool_result = run_first_copy_phaser(tool_request).result
    assert tool_result.execution_status == "failed_tool_execution"
    assert tool_result.rejection_reason == "phenix.phaser_exit_7"

    parse_request = _inputs(tmp_path / "parse")
    _fake_runtime(monkeypatch, log_text="EXIT STATUS: SUCCESS\n")
    parse_result = run_first_copy_phaser(parse_request).result
    assert parse_result.execution_status == "failed_parse"
    assert "solution count" in (parse_result.rejection_reason or "")


def test_adapter_rejects_changed_mtz_before_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _inputs(tmp_path)
    request.mtz.write_bytes(b"changed")
    commands = _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG)

    with pytest.raises(PhaserInputError, match="checksum differs"):
        run_first_copy_phaser(request)
    assert commands == []


def test_first_copy_cli_exposes_adapter_without_default_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _inputs(tmp_path)
    commands = _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG)

    exit_status = main(
        [
            "--no-progress",
            "mr",
            "first-copy",
            "--hypotheses",
            str(request.hypotheses_jsonl),
            "--hypothesis-id",
            request.hypothesis_id,
            "--sequence-groups",
            str(request.sequence_groups_jsonl),
            "--processed-models",
            str(request.processed_models_jsonl),
            "--model-preparation-manifest",
            str(request.model_preparation_manifest),
            "--preflight",
            str(request.preflight_jsonl),
            "--mtz",
            str(request.mtz),
            "--phenix-manifest",
            str(request.phenix_manifest),
            "--outdir",
            str(request.output_directory),
            "--threads",
            "4",
        ]
    )

    assert exit_status == 0
    assert "First-copy MR completed_no_hit" in capsys.readouterr().out
    assert commands[0][-2:] == [
        "phaser.keywords.general.jobs=4",
        "phaser.keywords.sgalternative.select=none",
    ]


def test_normalised_result_has_only_json_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _inputs(tmp_path)
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG)
    document: Any = json.loads(
        run_first_copy_phaser(request).result_json.read_text(encoding="utf-8")
    )
    assert document["hypothesis_id"] == HYPOTHESIS_ID
