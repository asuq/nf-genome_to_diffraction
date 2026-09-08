"""Exact AFDB binding, shared confidence processing and failure evidence."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import gemmi
import pytest

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.hpc import identification_run
from genome_to_diffraction.hpc.identification_inputs import (
    IdentificationInputError,
    build_identification_input_bundle,
    validate_plan,
)
from genome_to_diffraction.model_registry import predicted
from tests.support.identification_fixture import materialise_afdb_identification_fixture


def test_predicted_source_provenance_changes_input_content_identity(
    tmp_path: Path,
) -> None:
    root, plan = materialise_afdb_identification_fixture(tmp_path)
    first = build_identification_input_bundle(
        repository=tmp_path, archive_path=tmp_path / "first.tar", source_commit="a" * 40
    )
    raw = plan.model_dump(mode="json")
    raw["cases"][0]["coordinate_source"]["retrieval_date"] = "2026-09-09T00:00:00Z"
    atomic_write_json(root / "plan.json", raw)
    second = build_identification_input_bundle(
        repository=tmp_path,
        archive_path=tmp_path / "second.tar",
        source_commit="a" * 40,
    )
    assert first.input_id != second.input_id
    assert first.archive_sha256 != second.archive_sha256


def test_predicted_stub_cannot_be_used_for_real_mr(tmp_path: Path) -> None:
    root, plan = materialise_afdb_identification_fixture(tmp_path)
    case = plan.cases[0]
    out = tmp_path / "stub"
    manifest = tmp_path / "unavailable-runtime"
    identification_run.prepare_case(root, case.case_id, out, manifest, stub=True)
    assert (
        json.loads((out / "preparation.json").read_text())["status"]
        == "stub_not_scientific"
    )
    with pytest.raises(IdentificationInputError, match="prepared model identity"):
        identification_run.run_case(
            root, case.case_id, out, manifest, 8, 1, tmp_path / "not_run", 24
        )
    assert not (tmp_path / "not_run").exists()


@pytest.mark.parametrize(
    "mutation", ["sequence", "coordinate", "provider", "identity", "release"]
)
def test_exact_predicted_source_cannot_be_guessed(
    tmp_path: Path, mutation: str
) -> None:
    root, plan = materialise_afdb_identification_fixture(tmp_path)
    raw = plan.model_dump(mode="json")
    case = raw["cases"][0]
    if mutation == "sequence":
        case["coordinate_source"]["source_sequence_sha256"] = "c" * 64
    elif mutation == "coordinate":
        case["coordinate_source"]["coordinate_sha256"] = "c" * 64
    elif mutation == "provider":
        case["hit"]["provider"] = "pdb_sequence_mmseqs"
    elif mutation == "identity":
        case["hit"]["sequence_identity"] = 0.99
    else:
        case["coordinate_source"]["source_release"] = "model-version-5"
    atomic_write_json(root / "plan.json", raw)
    with pytest.raises(IdentificationInputError, match="source is inconsistent"):
        validate_plan(root, allowed_mtz_root=tmp_path)


@pytest.mark.parametrize("outcome", ["success", "native_failure", "empty_output"])
def test_shared_predicted_preparation_and_phaser_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    root, plan = materialise_afdb_identification_fixture(tmp_path)
    assert plan.adapter_version == "identification-screen-v2"
    manifest = tmp_path / "phenix-manifest.json"
    manifest.write_text("{}\n")
    monkeypatch.setattr(
        predicted,
        "validate_manifest_environment",
        lambda _path: SimpleNamespace(phenix_version="2.1-test"),
    )
    calls = []

    def capture(_manifest, command, *, working_directory, timeout_seconds):
        calls.append(command)
        assert command[0] == "phenix.process_predicted_model"
        assert "process_predicted_model.b_value_field_is=plddt" in command
        assert "process_predicted_model.input_plddt_is_fractional=False" in command
        assert "process_predicted_model.split_model_by_compact_regions=False" in command
        assert timeout_seconds is None
        if outcome == "success":
            structure = gemmi.read_structure(command[1])
            del structure[0][0][3]
            del structure[0][0][2]
            for residue in structure[0][0]:
                for atom in residue:
                    atom.b_iso = 12.0
            prefix = next(
                v.split("=", 1)[1]
                for v in command
                if v.startswith("output_files.processed_model_prefix=")
            )
            Path(prefix + "_model.pdb").write_text(structure.make_pdb_string())
        return subprocess.CompletedProcess(
            command,
            1 if outcome == "native_failure" else 0,
            b"native confidence processing\n",
            b"",
        )

    monkeypatch.setattr(predicted, "capture_from_manifest", capture)
    out = tmp_path / "prepared"
    case = plan.cases[0]
    identification_run.prepare_case(root, case.case_id, out, manifest)
    record = json.loads((out / "preparation.json").read_text())
    assert len(calls) == 1
    logs = list((out / "predicted/raw").rglob("*.log"))
    assert len(logs) == 1 and "native confidence" in logs[0].read_text()
    if outcome != "success":
        assert record["status"] == "model_preparation_failed"
        assert not (out / "model.pdb").exists()
        assert not (out / "resource_plan.json").exists()
        return
    assert record["status"] == "prepared"
    assert record["structural_source_class"] == "predicted"
    assert record["processed_model"]["residue_ranges"] == ["A:1-2"]
    assert record["source_confidence_summary"]["value"] == 90.0
    model = gemmi.read_structure(str(out / "model.pdb"))
    assert [a.b_iso for residue in model[0][0] for a in residue] == [12.0, 12.0]
    assert (out / "candidate.fasta").read_text().endswith("ACDQ\n")
    command = identification_run.phaser_command(plan, case, out, 8)
    assert "phaser.model_identity=100" in command
    assert "phaser.search_copies=1" in command
    assert f"phaser.component_copies={case.component_copies}" in command
    manifest.write_text('{"changed":true}\n')
    with pytest.raises(IdentificationInputError, match="preparation/runtime"):
        identification_run.run_case(
            root, case.case_id, out, manifest, 8, 1, tmp_path / "not_run", 24
        )
    assert not (tmp_path / "not_run").exists()
