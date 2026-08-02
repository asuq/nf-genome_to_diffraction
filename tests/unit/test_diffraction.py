"""Tests for independent MTZ preflight and candidate-specific Matthews values."""

import hashlib
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import gemmi
import numpy as np
import polars as pl
import pytest

from genome_to_diffraction.cli import main
from genome_to_diffraction.diffraction import free_r as free_r_module
from genome_to_diffraction.diffraction import preflight as preflight_module
from genome_to_diffraction.diffraction.free_r import (
    FreeRGenerationError,
    FreeRGenerationRequest,
    generate_free_r,
)
from genome_to_diffraction.diffraction.preflight import (
    inspect_crystal,
    parse_xtriage_output,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.matthews import assess_sds, enumerate_group
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    CrystalEntry,
    PipelineConfig,
)
from genome_to_diffraction.schemas.results import (
    AssessmentStatus,
    MtzPreflightRecord,
    PreflightDecision,
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.status import ExecutionStatus

REPOSITORY = Path(__file__).resolve().parents[2]


def _write_mtz(
    path: Path,
    columns: tuple[tuple[str, str], ...],
    *,
    space_group: str = "P 21 21 21",
    cell: tuple[float, float, float, float, float, float] = (
        100,
        100,
        100,
        90,
        90,
        90,
    ),
) -> None:
    mtz = gemmi.Mtz(with_base=True)
    mtz.spacegroup = gemmi.find_spacegroup_by_name(space_group)
    mtz.set_cell_for_all(gemmi.UnitCell(*cell))
    mtz.add_dataset("synthetic")
    for label, type_code in columns:
        mtz.add_column(label, type_code)
    rows: list[list[float]] = []
    for index in range(1, 11):
        values = [float(index * 100 + offset + 1) for offset in range(len(columns))]
        rows.append([float(index), 1.0, 1.0, *values])
    mtz.set_data(np.asarray(rows, dtype=np.float32))
    mtz.update_reso()
    mtz.write_to_file(str(path))


def _crystal(path: Path, **updates: object) -> CrystalEntry:
    document: dict[str, object] = {
        "crystal_id": "crystal_a",
        "mtz": str(path),
        "catalogue_id": "catalogue_a",
        "allow_remote_sequence_submission": False,
    }
    document.update(updates)
    return CrystalEntry.model_validate(document)


@pytest.mark.parametrize(
    ("columns", "expected_labels", "expected_type"),
    (
        (
            (("I", "J"), ("SIGI", "Q"), ("FreeR_flag", "I")),
            "I,SIGI",
            "intensity",
        ),
        ((("FP", "F"), ("SIGFP", "Q")), "FP,SIGFP", "amplitude"),
    ),
)
def test_gemmi_preflight_selects_observations_and_asu_volume(
    tmp_path: Path,
    columns: tuple[tuple[str, str], ...],
    expected_labels: str,
    expected_type: str,
) -> None:
    mtz_path = tmp_path / "input data.mtz"
    _write_mtz(mtz_path, columns)
    record = inspect_crystal(
        _crystal(mtz_path),
        manifest_path=tmp_path / "crystals.json",
        output_directory=tmp_path / "output",
        phenix_manifest=None,
        skip_xtriage=True,
        progress=False,
        xtriage_timeout_seconds=30,
    )
    assert record.selected_observation_labels == expected_labels
    assert record.selected_observation_type == expected_type
    assert record.general_position_multiplicity == 4
    assert record.cell_volume_a3 == pytest.approx(1_000_000)
    assert record.asu_volume_a3 == pytest.approx(250_000)
    assert record.decision is PreflightDecision.PASS_WITH_REVIEW
    assert "xtriage_not_run" in record.warning_codes


def test_map_coefficients_never_become_observations(tmp_path: Path) -> None:
    mtz_path = tmp_path / "map-only.mtz"
    _write_mtz(mtz_path, (("FWT", "F"), ("PHWT", "P")))
    record = inspect_crystal(
        _crystal(mtz_path),
        manifest_path=tmp_path / "crystals.json",
        output_directory=tmp_path / "output",
        phenix_manifest=None,
        skip_xtriage=True,
        progress=False,
        xtriage_timeout_seconds=30,
    )
    assert record.decision is PreflightDecision.FAIL
    assert record.selected_observation_labels is None
    assert "no_observed_data" in record.warning_codes
    assert record.execution_status is ExecutionStatus.FAILED_INPUT_CONTRACT


def test_equal_priority_observation_arrays_fail_as_ambiguous(tmp_path: Path) -> None:
    mtz_path = tmp_path / "ambiguous.mtz"
    _write_mtz(
        mtz_path,
        (("I1", "J"), ("SIGI1", "Q"), ("I2", "J"), ("SIGI2", "Q")),
    )
    record = inspect_crystal(
        _crystal(mtz_path),
        manifest_path=tmp_path / "crystals.json",
        output_directory=tmp_path / "output",
        phenix_manifest=None,
        skip_xtriage=True,
        progress=False,
        xtriage_timeout_seconds=30,
    )
    assert record.decision is PreflightDecision.FAIL
    assert "ambiguous_observation_arrays" in record.warning_codes


def test_explicit_observation_override_resolves_ambiguity(tmp_path: Path) -> None:
    mtz_path = tmp_path / "explicit.mtz"
    _write_mtz(
        mtz_path,
        (("I1", "J"), ("SIGI1", "Q"), ("I2", "J"), ("SIGI2", "Q")),
    )
    record = inspect_crystal(
        _crystal(mtz_path, obs_labels="I2,SIGI2"),
        manifest_path=tmp_path / "crystals.json",
        output_directory=tmp_path / "output",
        phenix_manifest=None,
        skip_xtriage=True,
        progress=False,
        xtriage_timeout_seconds=30,
    )
    assert record.selected_observation_labels == "I2,SIGI2"
    assert "ambiguous_observation_arrays" not in record.warning_codes


def test_xtriage_parser_normalises_warnings_and_metrics() -> None:
    report = (
        REPOSITORY / "tests/fixtures/xtriage/phenix_2_1_positive_summary.log"
    ).read_text(encoding="utf-8")
    parsed = parse_xtriage_output(report)
    assert parsed.version == "2.1-6048"
    assert parsed.completeness is None
    assert parsed.mean_i_over_sigma is None
    assert parsed.anisotropy_status is AssessmentStatus.SUSPECTED
    assert parsed.tncs_status is AssessmentStatus.SUSPECTED
    assert parsed.twinning_status is AssessmentStatus.SUSPECTED
    assert parsed.symmetry_status is AssessmentStatus.SUSPECTED
    assert set(parsed.warning_codes) == {
        "xtriage_anisotropy",
        "xtriage_tncs",
        "xtriage_twinning",
        "xtriage_symmetry",
    }


def test_xtriage_parser_uses_real_final_verdict_not_explanatory_text() -> None:
    report = (
        REPOSITORY / "tests/fixtures/xtriage/phenix_2_1_negative_summary.log"
    ).read_text(encoding="utf-8")
    parsed = parse_xtriage_output(report)
    assert parsed.completeness == pytest.approx(0.837033)
    assert parsed.mean_i_over_sigma == pytest.approx(7.9)
    assert parsed.summary["xtriage_resolution_low_a"] == pytest.approx(107.352)
    assert parsed.summary["xtriage_resolution_high_a"] == pytest.approx(1.42454)
    assert parsed.summary["xtriage_reflection_count"] == 532346
    assert parsed.summary["patterson_off_origin_peak_fraction"] == pytest.approx(
        0.02435
    )
    assert parsed.summary["patterson_peak_p_value"] == pytest.approx(1.0)
    assert parsed.summary["l_test_multivariate_z"] == pytest.approx(0.785)
    assert parsed.summary["anisotropy_noise_z_least_affected"] == pytest.approx(0.09)
    assert parsed.summary["anisotropy_noise_z_most_affected"] == pytest.approx(0.28)
    assert parsed.anisotropy_status is AssessmentStatus.NOT_ASSESSED
    assert parsed.tncs_status is AssessmentStatus.NOT_DETECTED
    assert parsed.twinning_status is AssessmentStatus.NOT_DETECTED
    assert parsed.symmetry_status is AssessmentStatus.NOT_DETECTED
    assert set(parsed.warning_codes) == {
        "xtriage_completeness_below_90_percent",
        "xtriage_direction_dependent_resolution",
    }


def test_xtriage_parser_treats_equivalent_centered_settings_as_same_point_group() -> (
    None
):
    report = """
The point group of data as dictated by the space group is I 1 2 1
The likely point group of the data is: C 1 2 1 (x+y,z,2*x)
I 1 2 1 (input space group): no absences found
"""
    parsed = parse_xtriage_output(report)
    assert parsed.symmetry_status is AssessmentStatus.NOT_DETECTED
    assert parsed.summary["point_group_equivalent"] is True


def test_xtriage_parser_requires_absence_evidence_for_equivalent_point_group() -> None:
    report = """
The point group of data as dictated by the space group is I 1 2 1
The likely point group of the data is: C 1 2 1 (x+y,z,2*x)
"""
    parsed = parse_xtriage_output(report)
    assert parsed.symmetry_status is AssessmentStatus.NOT_ASSESSED
    assert parsed.summary["point_group_equivalent"] is True
    assert parsed.summary["input_space_group_absences_consistent"] is None


def test_xtriage_parser_does_not_classify_explanatory_text() -> None:
    report = (
        REPOSITORY / "tests/fixtures/xtriage/phenix_2_1_explanatory_only.log"
    ).read_text(encoding="utf-8")
    parsed = parse_xtriage_output(report)
    assert parsed.anisotropy_status is AssessmentStatus.NOT_ASSESSED
    assert parsed.tncs_status is AssessmentStatus.NOT_ASSESSED
    assert parsed.twinning_status is AssessmentStatus.NOT_ASSESSED
    assert parsed.symmetry_status is AssessmentStatus.NOT_ASSESSED
    assert parsed.warning_codes == ()


def test_xtriage_positive_symmetry_verdict_does_not_invent_group_equivalence() -> None:
    report = """
----------Final verdict----------
The symmetry of the intensities suggest that the assumed space group is too low.
----------Statistics independent of twin laws----------
"""
    parsed = parse_xtriage_output(report)
    assert parsed.symmetry_status is AssessmentStatus.SUSPECTED
    assert parsed.summary["point_group_equivalent"] is None


def test_xtriage_weak_patterson_signal_is_review_not_tncs_detection() -> None:
    report = """
p_value(height) : 1.151e-02
----------Final verdict----------
No significant pseudotranslation is detected.
No twinning is suspected.
----------Statistics independent of twin laws----------
"""
    parsed = parse_xtriage_output(report)
    assert parsed.tncs_status is AssessmentStatus.NOT_DETECTED
    assert parsed.summary["patterson_peak_p_value"] == pytest.approx(0.01151)
    assert parsed.warning_codes == ("xtriage_patterson_peak_review",)


@pytest.mark.parametrize(
    "fixture",
    [
        "phenix_2_1_negative_summary.log",
        "phenix_2_1_positive_summary.log",
        "phenix_2_1_explanatory_only.log",
    ],
)
def test_xtriage_real_format_fixtures_are_sanitised(fixture: str) -> None:
    text = (REPOSITORY / "tests/fixtures/xtriage" / fixture).read_text(encoding="utf-8")
    assert "/Users/" not in text
    assert "AD4QS1P4G2_18" not in text
    assert "CD4QS2P2G1_15" not in text
    assert "CD6QS2P2G1_5" not in text


def test_xtriage_parser_flags_a_genuinely_different_likely_point_group() -> None:
    report = """
The point group of data as dictated by the space group is P 2 2 2
The likely point group of the data is: P 4 2 2
"""
    parsed = parse_xtriage_output(report)
    assert parsed.symmetry_status is AssessmentStatus.SUSPECTED
    assert parsed.summary["point_group_equivalent"] is False
    assert parsed.warning_codes == ("xtriage_symmetry",)


def test_preflight_runs_xtriage_through_captured_phenix_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mtz_path = tmp_path / "xtriage.mtz"
    _write_mtz(mtz_path, (("I", "J"), ("SIGI", "Q"), ("FreeR_flag", "I")))
    phenix_document = json.loads(
        (REPOSITORY / "tests/fixtures/stubs/phenix_install_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    phenix_document["phenix_version"] = "2.1-7000"
    phenix_manifest = tmp_path / "phenix.json"
    phenix_manifest.write_text(json.dumps(phenix_document), encoding="utf-8")

    def fake_capture(
        manifest_path: Path,
        arguments: Sequence[str],
        *,
        working_directory: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[bytes]:
        del manifest_path, working_directory, timeout_seconds
        assert arguments[0] == "phenix.xtriage"
        assert any("obs_labels=I,SIGI" in item for item in arguments)
        report = (
            b"PHENIX.xtriage version 2.1-7000\n"
            b"Completeness overall: 99.0 %\n"
            b"Resolution: 50.000 - 1.500\n"
            b"Number of reflections: 900\n"
            b"The data are not significantly anisotropic.\n"
            b"The quarter of Intensities *least* affected by the anisotropy "
            b"correction show\n"
            b"Fraction of I/sigI > 3 : 2.00e-01 ( Z = 0.10 )\n"
            b"The quarter of Intensities *most* affected by the anisotropy "
            b"correction show\n"
            b"Fraction of I/sigI > 3 : 1.00e-01 ( Z = 1.20 )\n"
            b"Height relative to origin : 2.500 %\n"
            b"p_value(height) : 1.250e-01\n"
            b"----------Final verdict----------\n"
            b"No significant pseudotranslation is detected.\n"
            b"No twinning is suspected.\n"
            b"----------Statistics independent of twin laws----------\n"
            b"Multivariate Z score L-test: 0.750\n"
        )
        return subprocess.CompletedProcess(arguments, 0, report, b"")

    monkeypatch.setattr(preflight_module, "capture_from_manifest", fake_capture)
    record = inspect_crystal(
        _crystal(mtz_path),
        manifest_path=tmp_path / "crystals.json",
        output_directory=tmp_path / "output",
        phenix_manifest=phenix_manifest,
        skip_xtriage=False,
        progress=False,
        xtriage_timeout_seconds=30,
    )
    assert record.decision is PreflightDecision.PASS
    assert record.xtriage_version == "2.1-7000"
    assert record.completeness == pytest.approx(0.99)
    assert record.xtriage_log == "xtriage/crystal_a.log"
    assert (tmp_path / "output/xtriage/crystal_a.log").is_file()
    preflight_module._write_preflight_outputs(tmp_path / "output", (record,))
    report_text = (tmp_path / "output/preflight_report.md").read_text(encoding="utf-8")
    assert "Xtriage version: `2.1-7000`" in report_text
    assert "Completeness: `99.00%`" in report_text
    assert "Xtriage selected-data resolution: `50.000-1.500 A`" in report_text
    assert "Xtriage selected reflection count: `900`" in report_text
    assert "tncs=not_detected" in report_text
    assert "twinning=not_detected" in report_text
    assert "Patterson off-origin peak: `2.50%`" in report_text
    assert "Patterson peak p-value: `1.250e-01`" in report_text
    assert "Multivariate L-test Z: `0.750`" in report_text
    assert "Anisotropy-noise Z (least/most affected quarters): `0.10 / 1.20`" in (
        report_text
    )


def _sequence_group(
    *,
    exact_mass: float | None = 50_000,
    lower_mass: float | None = None,
    upper_mass: float | None = None,
) -> SequenceGroupRecord:
    sequence = "A" * 100
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=exact_mass,
        molecular_mass_lower_da=lower_mass,
        molecular_mass_upper_da=upper_mass,
        mass_method="synthetic fixed mass",
        residue_policy="test",
        source_record_count=1,
    )


def _preflight() -> MtzPreflightRecord:
    return MtzPreflightRecord(
        schema_version="1.0",
        preflight_id="preflight_test",
        crystal_id="crystal_a",
        mtz_sha256="0" * 64,
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


def _config() -> PipelineConfig:
    model = load_contract(
        REPOSITORY / "examples/config.yaml", "pipeline-config", progress=False
    )
    assert isinstance(model, PipelineConfig)
    return model


def test_matthews_known_cell_mass_and_copy_example() -> None:
    rows = enumerate_group(
        _sequence_group(),
        _crystal(
            Path("input.mtz"),
            sds_page_mass_kda=[50.0],
            sds_page_condition="reducing",
            sds_page_band_roles=["dominant"],
        ),
        _preflight(),
        _config(),
    )
    copy_two = next(row for row in rows if row.copy_count == 2)
    assert copy_two.total_mass_da == pytest.approx(100_000)
    assert copy_two.matthews_coefficient == pytest.approx(2.5)
    assert copy_two.solvent_fraction == pytest.approx(0.508)
    assert copy_two.sds_page_prior_label == "strong"
    assert sum(row.retained for row in rows) == 3


def test_python_matthews_matches_preserved_xtriage_reference_fixture() -> None:
    fixture = (REPOSITORY / "tests/fixtures/xtriage/synthetic_matthews.log").read_text(
        encoding="utf-8"
    )
    reference = parse_xtriage_output(fixture).matthews_rows[0]
    rows = enumerate_group(
        _sequence_group(),
        _crystal(Path("input.mtz")),
        _preflight(),
        _config(),
    )
    calculated = next(row for row in rows if row.copy_count == reference.copy_count)
    assert calculated.matthews_coefficient == pytest.approx(
        reference.matthews_coefficient
    )
    assert calculated.solvent_fraction == pytest.approx(reference.solvent_fraction)


def test_bounded_mass_produces_bounded_matthews_values() -> None:
    rows = enumerate_group(
        _sequence_group(exact_mass=None, lower_mass=48_000, upper_mass=52_000),
        _crystal(Path("input.mtz")),
        _preflight(),
        _config(),
    )
    copy_two = next(row for row in rows if row.copy_count == 2)
    assert copy_two.matthews_coefficient is None
    assert copy_two.matthews_coefficient_lower == pytest.approx(250_000 / 104_000)
    assert copy_two.matthews_coefficient_upper == pytest.approx(250_000 / 96_000)
    assert "matthews_uses_sequence_mass_bounds" in copy_two.warnings


def test_sds_multiple_bands_is_soft_and_missing_is_unavailable() -> None:
    group = _sequence_group()
    multiple = assess_sds(
        group,
        _crystal(
            Path("input.mtz"),
            sds_page_mass_kda=[20.0, 52.0],
            sds_page_condition="nonreducing",
            sds_page_band_roles=["minor", "dominant"],
        ),
    )
    assert multiple.nearest_band_kda == 52.0
    assert multiple.label == "compatible"
    assert "sds_condition_reduces_prior_strength" in multiple.warnings
    missing = assess_sds(group, _crystal(Path("input.mtz")))
    assert missing.label == "unavailable"


def test_free_r_generation_is_separate_deterministic_and_preserves_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mtz"
    _write_mtz(source, (("I", "J"), ("SIGI", "Q")))
    source_before = source.read_bytes()
    phenix_manifest = tmp_path / "phenix.json"
    phenix_manifest.write_text("{}\n", encoding="utf-8")
    captured_arguments: list[str] = []

    def fake_capture(
        manifest_path: Path,
        arguments: Sequence[str],
        *,
        working_directory: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[bytes]:
        del manifest_path, working_directory, timeout_seconds
        captured_arguments.extend(arguments)
        destination = Path(
            next(item for item in arguments if item.startswith("--mtz=")).split("=", 1)[
                1
            ]
        )
        mtz = gemmi.read_mtz_file(str(source))
        old_data = np.array(mtz.array, copy=True)
        mtz.add_column("FreeR_flag", "I")
        flags = np.asarray(
            [[1.0 if index == 0 else 0.0] for index in range(len(old_data))]
        )
        mtz.set_data(np.hstack((old_data, flags)).astype(np.float32))
        mtz.write_to_file(str(destination))
        return subprocess.CompletedProcess(
            arguments, 0, b"generated Free-R flags\n", b""
        )

    monkeypatch.setattr(free_r_module, "capture_from_manifest", fake_capture)
    output = tmp_path / "derived/free-r.mtz"
    record = generate_free_r(
        FreeRGenerationRequest(
            source_mtz=source,
            output_mtz=output,
            phenix_manifest=phenix_manifest,
            command_log=tmp_path / "logs/free-r.log",
            record_path=tmp_path / "records/free-r.json",
            progress=False,
        )
    )
    assert source.read_bytes() == source_before
    assert gemmi.read_mtz_file(str(output)).rfree_column().label == "FreeR_flag"
    assert "--generate-r-free-flags" in captured_arguments
    assert "--use-lattice-symmetry-in-r-free-flag-generation" in captured_arguments
    assert "--random-seed=20260801" in captured_arguments
    assert record.source_mtz_sha256 != record.output_mtz_sha256
    assert record.flag_convention == "cns"


def test_free_r_generation_refuses_existing_flags(tmp_path: Path) -> None:
    source = tmp_path / "already-free.mtz"
    _write_mtz(source, (("I", "J"), ("SIGI", "Q"), ("FREE", "I")))
    manifest = tmp_path / "phenix.json"
    manifest.write_text("{}\n", encoding="utf-8")
    with pytest.raises(FreeRGenerationError, match="already contains Free-R"):
        generate_free_r(
            FreeRGenerationRequest(
                source_mtz=source,
                output_mtz=tmp_path / "output.mtz",
                phenix_manifest=manifest,
                command_log=tmp_path / "command.log",
                record_path=tmp_path / "record.json",
                progress=False,
            )
        )


def test_cli_preflight_to_matthews_outputs_all_copy_counts(tmp_path: Path) -> None:
    mtz = tmp_path / "input.mtz"
    _write_mtz(mtz, (("I", "J"), ("SIGI", "Q"), ("FREE", "I")))
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
    config = tmp_path / "config.yaml"
    config.write_text(
        (REPOSITORY / "examples/config.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    group = _sequence_group()
    source = SourceProteinRecord(
        schema_version="1.0",
        source_record_id="source_a",
        catalogue_id="catalogue_a",
        original_protein_id="protein_a",
        original_header="protein_a",
        sequence_group_id=group.sequence_group_id,
        source_annotation_provider="synthetic",
    )
    sequence_groups = tmp_path / "sequence_groups.jsonl"
    source_records = tmp_path / "source_records.jsonl"
    sequence_groups.write_text(canonical_json_text(group) + "\n", encoding="utf-8")
    source_records.write_text(canonical_json_text(source) + "\n", encoding="utf-8")
    preflight_output = tmp_path / "preflight"
    assert (
        main(
            [
                "--no-progress",
                "diffraction",
                "preflight",
                "--crystals",
                str(crystals),
                "--outdir",
                str(preflight_output),
                "--skip-xtriage",
            ]
        )
        == 0
    )
    matthews_output = tmp_path / "matthews"
    assert (
        main(
            [
                "--no-progress",
                "matthews",
                "enumerate",
                "--crystals",
                str(crystals),
                "--config",
                str(config),
                "--preflight",
                str(preflight_output / "mtz_preflight.jsonl"),
                "--sequence-groups",
                str(sequence_groups),
                "--source-records",
                str(source_records),
                "--outdir",
                str(matthews_output),
            ]
        )
        == 0
    )
    table = pl.read_parquet(matthews_output / "matthews_hypotheses.parquet")
    assert table.height == 16
    assert table.filter(pl.col("retained")).height == 3
