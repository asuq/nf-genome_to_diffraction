"""Tests for deterministic predicted-coordinate model preparation."""

import hashlib
import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import gemmi
import pytest

from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.model_registry import (
    PredictedModelInputError,
    PredictedModelPreparationRequest,
    PredictedModelToolError,
    prepare_predicted_models,
)
from genome_to_diffraction.model_registry import predicted as predicted_module
from genome_to_diffraction.schemas.results import (
    CoordinateSourceRecord,
    SearchScientificStatus,
    SequenceGroupRecord,
    StructuralSearchResult,
)
from genome_to_diffraction.status import ExecutionStatus


def _pdb(sequence: str, positions: Sequence[int] | None = None) -> bytes:
    residue_names = {
        "A": "ALA",
        "C": "CYS",
        "D": "ASP",
        "E": "GLU",
        "F": "PHE",
        "G": "GLY",
        "H": "HIS",
        "I": "ILE",
    }
    selected = positions if positions is not None else range(1, len(sequence) + 1)
    atoms = "".join(
        f"ATOM  {atom_index:5d}  CA  {residue_names[sequence[position - 1]]} "
        f"A{position:4d}    {float(position):8.3f}{0.0:8.3f}{0.0:8.3f}  "
        "1.00 90.00           C\n"
        for atom_index, position in enumerate(selected, start=1)
    )
    return f"{atoms}END\n".encode("ascii")


def _mmcif(sequence: str, positions: Sequence[int] | None = None) -> bytes:
    structure = gemmi.read_pdb_string(_pdb(sequence, positions).decode("ascii"))
    structure.name = "predicted-model-test"
    structure.setup_entities()
    return str(structure.make_mmcif_document().as_string()).encode("ascii")


def _inputs(
    tmp_path: Path, *, sequence: str = "ACDEFGHI"
) -> tuple[Path, Path, Path, CoordinateSourceRecord, SequenceGroupRecord]:
    root = tmp_path / "input with spaces"
    root.mkdir()
    coordinate = root / "AFDB source model.cif"
    coordinate.write_bytes(_mmcif(sequence))
    sequence_sha256 = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    coordinate_sha256 = hashlib.sha256(coordinate.read_bytes()).hexdigest()
    group = SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{sequence_sha256}",
        sha256=sequence_sha256,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=900.0,
        mass_method="test mass",
        residue_policy="standard_exact",
        source_record_count=1,
    )
    source = CoordinateSourceRecord(
        schema_version="1.0",
        coordinate_id=f"coord_{coordinate_sha256}",
        provider="afdb",
        provider_accession="A0TEST",
        retrieval_date=datetime(2026, 8, 10, tzinfo=UTC),
        source_release="model-version-6",
        coordinate_path=str(coordinate),
        coordinate_sha256=coordinate_sha256,
        source_sequence_sha256=sequence_sha256,
        confidence_summary={"metric": "mean_plddt", "value": 95.0},
        license_or_provenance="AlphaFold DB CC-BY-4.0",
    )
    sources = root / "coordinate sources.jsonl"
    sources.write_text(f"{canonical_json_text(source)}\n", encoding="utf-8")
    groups = root / "sequence groups.jsonl"
    groups.write_text(f"{canonical_json_text(group)}\n", encoding="utf-8")
    manifest = root / "phenix manifest.json"
    manifest.write_text('{"test":"manifest"}\n', encoding="utf-8")
    return sources, groups, manifest, source, group


def _fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int = 0,
    stdout: bytes = b"processed model\n",
) -> list[str]:
    captured_arguments: list[str] = []
    monkeypatch.setattr(
        predicted_module,
        "validate_manifest_environment",
        lambda _path: SimpleNamespace(phenix_version="2.1-6048"),
    )

    def fake_capture(
        manifest_path: Path,
        arguments: Sequence[str],
        *,
        working_directory: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[bytes]:
        del manifest_path, working_directory, timeout_seconds
        captured_arguments.extend(arguments)
        if returncode == 0:
            prefix = Path(
                next(
                    item.split("=", 1)[1]
                    for item in arguments
                    if item.startswith("output_files.processed_model_prefix=")
                )
            )
            prefix.with_name(f"{prefix.name}_A_1.pdb").write_bytes(
                _pdb("ACDEFGHI", positions=(2, 3, 5, 6, 7, 8))
            )
        return subprocess.CompletedProcess(arguments, returncode, stdout, b"")

    monkeypatch.setattr(predicted_module, "capture_from_manifest", fake_capture)
    return captured_arguments


def test_predicted_model_preparation_is_mapped_content_addressed_and_space_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, groups, manifest, source, group = _inputs(tmp_path)
    arguments = _fake_runtime(monkeypatch)
    output = tmp_path / "output with spaces"
    result = prepare_predicted_models(
        PredictedModelPreparationRequest(
            coordinate_sources_jsonl=sources,
            sequence_groups_jsonl=groups,
            phenix_manifest=manifest,
            output_directory=output,
            coordinate_ids=(source.coordinate_id,),
            progress=False,
        )
    )

    assert len(result.records) == 1
    record = result.records[0]
    assert record.coordinate_id == source.coordinate_id
    assert record.full_candidate_sequence_group_id == group.sequence_group_id
    assert record.variant_type == "predicted_confidence_pruned_full"
    assert record.residue_ranges == ("A:2-3", "A:5-8")
    assert record.processing_tool == "phenix.process_predicted_model"
    assert record.processing_version == "2.1-6048"
    assert "low_confidence_residues_removed" in record.quality_flags
    assert "process_predicted_model.split_model_by_compact_regions=False" in arguments
    assert "process_predicted_model.remove_low_confidence_residues=True" in arguments
    assert "output_files.target_output_format=pdb" in arguments

    preparation = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    entry = preparation["entries"][0]
    model_path = output / entry["model_path"]
    assert model_path.is_file()
    assert model_path.suffix == ".pdb"
    assert model_path.read_text(encoding="ascii").startswith("ATOM")
    assert hashlib.sha256(model_path.read_bytes()).hexdigest() == record.model_sha256
    assert entry["source_residue_count"] == 8
    assert entry["retained_residue_count"] == 6
    assert entry["removed_residue_count"] == 2
    assert entry["execution_status"] == "completed_success"
    assert (output / entry["command_log"]).read_text(encoding="utf-8") == (
        "processed model\n"
    )
    parsed = [
        json.loads(line)
        for line in result.records_jsonl.read_text(encoding="utf-8").splitlines()
    ]
    assert parsed[0]["model_id"] == record.model_id


def test_predicted_model_preparation_rejects_coordinate_checksum_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, groups, manifest, source, _group = _inputs(tmp_path)
    _fake_runtime(monkeypatch)
    Path(source.coordinate_path).write_bytes(b"tampered\n")

    with pytest.raises(PredictedModelInputError, match="coordinate checksum mismatch"):
        prepare_predicted_models(
            PredictedModelPreparationRequest(
                coordinate_sources_jsonl=sources,
                sequence_groups_jsonl=groups,
                phenix_manifest=manifest,
                output_directory=tmp_path / "output",
                progress=False,
            )
        )


def test_disabled_predicted_provider_completes_without_invoking_phenix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, groups, manifest, _, group = _inputs(tmp_path)
    sources.write_text("", encoding="utf-8")
    provider_results = tmp_path / "disabled AFDB results.jsonl"
    result = StructuralSearchResult(
        schema_version="1.0",
        search_id="search_disabled_afdb",
        sequence_group_id=group.sequence_group_id,
        provider="afdb_exact",
        database_id="disabled_afdb_exact",
        tool="provider-plan",
        tool_version="1.0",
        adapter_version="provider-disabled-v1",
        cache_key="a" * 64,
        execution_status=ExecutionStatus.SKIPPED_POLICY,
        scientific_status=SearchScientificStatus.NOT_INTERPRETABLE,
        hit_count=0,
        raw_result_pointer="raw/disabled.jsonl",
        raw_result_sha256="b" * 64,
        command_log_pointer="raw/disabled.log",
        command_log_sha256="c" * 64,
    )
    provider_results.write_text(f"{canonical_json_text(result)}\n", encoding="utf-8")
    arguments = _fake_runtime(monkeypatch)

    output = prepare_predicted_models(
        PredictedModelPreparationRequest(
            coordinate_sources_jsonl=sources,
            provider_search_results_jsonl=provider_results,
            sequence_groups_jsonl=groups,
            phenix_manifest=manifest,
            output_directory=tmp_path / "empty predicted models",
            progress=False,
        )
    )

    assert arguments == []
    assert output.records == ()
    assert output.records_jsonl.read_bytes() == b""
    preparation = json.loads(output.manifest_json.read_text(encoding="utf-8"))
    assert preparation["coordinate_source_count"] == 0
    assert preparation["processed_model_count"] == 0
    assert (
        preparation["provider_search_results_sha256"]
        == hashlib.sha256(provider_results.read_bytes()).hexdigest()
    )


def test_empty_predicted_sources_without_typed_provider_evidence_remain_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, groups, manifest, _, _ = _inputs(tmp_path)
    sources.write_text("", encoding="utf-8")
    _fake_runtime(monkeypatch)

    with pytest.raises(PredictedModelInputError, match="typed provider search results"):
        prepare_predicted_models(
            PredictedModelPreparationRequest(
                coordinate_sources_jsonl=sources,
                sequence_groups_jsonl=groups,
                phenix_manifest=manifest,
                output_directory=tmp_path / "empty predicted models",
                progress=False,
            )
        )


def test_predicted_model_failure_preserves_bounded_native_log_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, groups, manifest, source, _group = _inputs(tmp_path)
    lines = (
        ["early marker"]
        + [f"diagnostic {index}" for index in range(50)]
        + ["final native marker"]
    )
    _fake_runtime(
        monkeypatch,
        returncode=1,
        stdout=("\n".join(lines) + "\n").encode("utf-8"),
    )
    output = tmp_path / "failed output"

    with pytest.raises(PredictedModelToolError) as error:
        prepare_predicted_models(
            PredictedModelPreparationRequest(
                coordinate_sources_jsonl=sources,
                sequence_groups_jsonl=groups,
                phenix_manifest=manifest,
                output_directory=output,
                coordinate_ids=(source.coordinate_id,),
                progress=False,
            )
        )
    assert "final native marker" in str(error.value)
    assert "early marker" not in str(error.value)
    raw_log = (
        output / "raw" / source.coordinate_id / "phenix.process_predicted_model.log"
    )
    assert "early marker" in raw_log.read_text(encoding="utf-8")
