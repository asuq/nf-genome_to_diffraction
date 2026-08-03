"""Tests for the fixed Phenix Matthews method-reference qualification."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from genome_to_diffraction.cli import main
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.matthews import reference as reference_module
from genome_to_diffraction.matthews.enumerate import enumerate_group
from genome_to_diffraction.matthews.reference import (
    MatthewsReferenceExecutionError,
    MatthewsReferenceInputError,
    MatthewsReferenceParseError,
    MatthewsReferenceRequest,
    parse_phenix_matthews_output,
    qualify_matthews_reference,
)
from genome_to_diffraction.phenix.runtime import MatthewsReferenceExecution
from genome_to_diffraction.schemas.manifests import CrystalEntry, PipelineConfig
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MtzPreflightRecord,
    PreflightDecision,
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.status import ExecutionStatus

REPOSITORY = Path(__file__).resolve().parents[2]
REFERENCE_TEXT = (REPOSITORY / "tests/fixtures/phenix/matthews_table.log").read_text(
    encoding="utf-8"
)


def _group(*, molecular_mass_da: float = 50_000) -> SequenceGroupRecord:
    sequence = "A" * 100
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=molecular_mass_da,
        mass_method="synthetic exact-composition fixture",
        residue_policy="test",
        source_record_count=1,
    )


def _inputs(
    tmp_path: Path,
    *,
    molecular_mass_da: float = 50_000,
) -> tuple[MatthewsReferenceRequest, Path]:
    mtz = tmp_path / "input data.mtz"
    mtz.write_bytes(b"synthetic MTZ fixture")
    mtz_digest = hashlib.sha256(mtz.read_bytes()).hexdigest()
    crystals = tmp_path / "crystals.json"
    crystals.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "crystals": [
                    {
                        "crystal_id": "crystal_a",
                        "mtz": str(mtz),
                        "catalogue_id": "catalogue_a",
                        "allow_remote_sequence_submission": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    preflight = MtzPreflightRecord(
        schema_version="1.0",
        preflight_id="preflight_reference",
        crystal_id="crystal_a",
        mtz_sha256=mtz_digest,
        selected_observation_labels="I,SIGI",
        selected_observation_type="intensity",
        free_flag_labels="FreeR_flag",
        free_flag_status="present",
        unit_cell=(100, 100, 100, 90, 90, 90),
        space_group="P 21 21 21",
        general_position_multiplicity=4,
        cell_volume_a3=1_000_000,
        asu_volume_a3=250_000,
        resolution_low_a=20,
        resolution_high_a=2,
        reflection_count=1000,
        decision=PreflightDecision.PASS,
        execution_status=ExecutionStatus.COMPLETED_SUCCESS,
    )
    preflight_path = tmp_path / "preflight.jsonl"
    preflight_path.write_text(canonical_json_text(preflight) + "\n", encoding="utf-8")
    group = _group(molecular_mass_da=molecular_mass_da)
    groups = tmp_path / "sequence groups.jsonl"
    groups.write_text(canonical_json_text(group) + "\n", encoding="utf-8")
    source = SourceProteinRecord(
        schema_version="1.0",
        source_record_id="source_reference",
        catalogue_id="catalogue_a",
        original_protein_id="protein_reference",
        original_header="protein_reference",
        sequence_group_id=group.sequence_group_id,
        source_annotation_provider="synthetic",
    )
    sources = tmp_path / "source records.jsonl"
    sources.write_text(canonical_json_text(source) + "\n", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(
        (REPOSITORY / "examples/config.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest = tmp_path / "phenix manifest.json"
    manifest.write_text('{"fixture":true}\n', encoding="utf-8")
    executable = tmp_path / "mmtbx.matthews"
    executable.write_text("fixture\n", encoding="utf-8")
    request = MatthewsReferenceRequest(
        crystal_manifest=crystals,
        pipeline_config=config,
        preflight_jsonl=preflight_path,
        sequence_groups_jsonl=groups,
        source_records_jsonl=sources,
        phenix_manifest=manifest,
        crystal_id="crystal_a",
        sequence_group_id=group.sequence_group_id,
        output_directory=tmp_path / "reference output",
        progress=False,
    )
    return request, executable


def _fake_execution(executable: Path) -> MatthewsReferenceExecution:
    return MatthewsReferenceExecution(
        completed=subprocess.CompletedProcess(
            [str(executable)], 0, REFERENCE_TEXT.encode(), b""
        ),
        executable=executable,
        executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        phenix_version="2.1-6048",
    )


def test_parser_reads_table_and_enforces_best_probability() -> None:
    parsed = parse_phenix_matthews_output(REFERENCE_TEXT)
    assert [row.copy_count for row in parsed.rows] == [1, 2, 3]
    assert parsed.rows[1].matthews_coefficient == pytest.approx(2.5)
    assert parsed.rows[1].solvent_fraction == pytest.approx(0.508)
    assert parsed.best_guess_copy_count == 2

    inconsistent = REFERENCE_TEXT.replace(
        "Best guess : 2 copies", "Best guess : 1 copy"
    )
    with pytest.raises(MatthewsReferenceParseError, match="probability ordering"):
        parse_phenix_matthews_output(inconsistent)

    printed_tie = REFERENCE_TEXT.replace(
        "| 3      | 0.262           | 1.67            | 0.300",
        "| 3      | 0.262           | 1.67            | 0.900",
    ).replace("Best guess : 2 copies", "Best guess : 3 copies")
    assert parse_phenix_matthews_output(printed_tie).best_guess_copy_count == 3


@pytest.mark.parametrize(
    "bad_text",
    (
        "Best guess : 1 copy in the ASU\n",
        REFERENCE_TEXT.replace("| 3      |", "| 2      |"),
        REFERENCE_TEXT.replace("0.754", "1.754"),
        REFERENCE_TEXT.replace("0.754", "0.600"),
    ),
)
def test_parser_fails_loudly_on_malformed_tables(bad_text: str) -> None:
    with pytest.raises(MatthewsReferenceParseError):
        parse_phenix_matthews_output(bad_text)


def test_reference_qualification_reports_method_only_and_cli_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, executable = _inputs(tmp_path)

    def fake_capture(*args: object, **kwargs: object) -> MatthewsReferenceExecution:
        del args, kwargs
        return _fake_execution(executable)

    monkeypatch.setattr(
        reference_module, "capture_matthews_reference_from_manifest", fake_capture
    )
    result = qualify_matthews_reference(request)
    report = json.loads(result.json_path.read_text(encoding="utf-8"))

    assert result.status == "passed"
    assert report["scope"] == "method_reference_only"
    assert report["positive_control_status"] == "not_established"
    assert report["checks"] == {
        "mass_models_within_compatibility_bound": True,
        "phenix_best_guess_in_configured_copy_range": True,
        "pipeline_formula_consistent": True,
        "plausible_copy_sets_match": True,
        "probability_prior_order_matches": True,
        "reference_formula_consistent_with_printed_rounding": True,
    }
    assert report["pipeline_plausible_copy_counts"] == [1, 2, 3]
    assert "not asserted" in report["selection_note"]
    assert result.phenix_log_path.read_text(encoding="utf-8") == REFERENCE_TEXT

    cli_output = tmp_path / "cli output"
    assert (
        main(
            [
                "--no-progress",
                "matthews",
                "reference-check",
                "--crystals",
                str(request.crystal_manifest),
                "--config",
                str(request.pipeline_config),
                "--preflight",
                str(request.preflight_jsonl),
                "--sequence-groups",
                str(request.sequence_groups_jsonl),
                "--source-records",
                str(request.source_records_jsonl),
                "--phenix-manifest",
                str(request.phenix_manifest),
                "--crystal-id",
                request.crystal_id,
                "--sequence-group-id",
                request.sequence_group_id,
                "--outdir",
                str(cli_output),
            ]
        )
        == 0
    )


def test_reference_qualification_fails_compatibility_without_claiming_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, executable = _inputs(tmp_path, molecular_mass_da=80_000)
    monkeypatch.setattr(
        reference_module,
        "capture_matthews_reference_from_manifest",
        lambda *args, **kwargs: _fake_execution(executable),
    )

    result = qualify_matthews_reference(request)
    report = json.loads(result.json_path.read_text(encoding="utf-8"))

    assert result.status == "passed_with_review"
    assert report["positive_control_status"] == "not_established"
    assert not report["checks"]["mass_models_within_compatibility_bound"]
    assert report["review_reasons"]


def test_reference_qualification_fails_pipeline_formula_inconsistency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, executable = _inputs(tmp_path)

    def inconsistent_enumerate(
        group: SequenceGroupRecord,
        crystal: CrystalEntry,
        preflight: MtzPreflightRecord,
        config: PipelineConfig,
    ) -> tuple[MatthewsHypothesis, ...]:
        rows = enumerate_group(group, crystal, preflight, config)
        first = rows[0]
        assert first.matthews_coefficient is not None
        inconsistent = first.model_copy(
            update={"matthews_coefficient": first.matthews_coefficient * 1.01}
        )
        return (inconsistent, *rows[1:])

    monkeypatch.setattr(
        "genome_to_diffraction.matthews.reference.enumerate_group",
        inconsistent_enumerate,
    )
    monkeypatch.setattr(
        reference_module,
        "capture_matthews_reference_from_manifest",
        lambda *args, **kwargs: _fake_execution(executable),
    )

    result = qualify_matthews_reference(request)
    report = json.loads(result.json_path.read_text(encoding="utf-8"))

    assert result.status == "failed"
    assert not report["checks"]["pipeline_formula_consistent"]


def test_reference_qualification_requires_crystal_catalogue_membership(
    tmp_path: Path,
) -> None:
    request, _ = _inputs(tmp_path)
    source_text = request.source_records_jsonl.read_text(encoding="utf-8")
    request.source_records_jsonl.write_text(
        source_text.replace("catalogue_a", "different_catalogue"),
        encoding="utf-8",
    )

    with pytest.raises(MatthewsReferenceInputError, match="not linked to catalogue"):
        qualify_matthews_reference(request)


def test_reference_qualification_preserves_failed_tool_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, executable = _inputs(tmp_path)
    failed = MatthewsReferenceExecution(
        completed=subprocess.CompletedProcess(
            [str(executable)], 23, b"partial reference output\n", b"tool failed\n"
        ),
        executable=executable,
        executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        phenix_version="2.1-6048",
    )
    monkeypatch.setattr(
        reference_module,
        "capture_matthews_reference_from_manifest",
        lambda *args, **kwargs: failed,
    )

    with pytest.raises(MatthewsReferenceExecutionError, match="exit status 23"):
        qualify_matthews_reference(request)

    assert (request.output_directory / "phenix_matthews.log").read_text(
        encoding="utf-8"
    ) == "partial reference output\ntool failed\n"
