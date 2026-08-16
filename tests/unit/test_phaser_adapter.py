"""Tests for first-copy Phaser execution, parsing, and credibility gates."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from genome_to_diffraction.cli import main
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.mr import (
    PhaserInputError,
    PhaserParseError,
    PhaserRunRequest,
    parse_phaser_log,
    run_first_copy_phaser,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    PhenixInstallManifest,
    PrototypeProfile,
)
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    MtzPreflightRecord,
    ProcessedModelRecord,
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
        update={"mtz_sha256": hashlib.sha256(mtz.read_bytes()).hexdigest()}
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


def _experimental_inputs(tmp_path: Path) -> PhaserRunRequest:
    request = _inputs(tmp_path)
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
        (working_directory / "PHASER.log").write_text(log_text, encoding="utf-8")
        if write_solution:
            (working_directory / "PHASER.1.pdb").write_text(
                "REMARK Log-Likelihood Gain: "
                f"{pdb_llg}\n"
                f"REMARK PAK=0 LLG={pdb_llg} TFZ=={pdb_tfz}\n"
                "REMARK ENSEMBLE ense_1 EULER 1 2 3 FRAC 0.1 0.2 0.3\n"
                "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  "
                "1.00 20.00           C\n",
                encoding="utf-8",
            )
            (working_directory / "PHASER.1.mtz").write_bytes(b"phaser MTZ")
        return subprocess.CompletedProcess(arguments, returncode, b"capture\n", b"")

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
    assert record["model_uncertainty_source"].startswith("phenix.process")


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
        "solution_count_inferred_from_output_files",
    )


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
