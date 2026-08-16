"""Tests for checksum-frozen public crystallographic controls."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from genome_to_diffraction.benchmarks.panel import (
    PublicControlPanelSpec,
    PublicPanelPreparationRequest,
    load_homomer_workflow_suite,
    load_public_control_panel,
    prepare_public_control_panel,
)
from genome_to_diffraction.benchmarks.public_control import (
    PublicControlError,
    PublicControlSpec,
    load_public_control_spec,
)
from genome_to_diffraction.cli import main
from genome_to_diffraction.logging import configure_logging

REPOSITORY = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPOSITORY / "benchmarks/public-controls"


def _yaml_document(path: Path) -> dict[str, object]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise AssertionError(f"expected mapping in {path}")
    return document


def test_tracked_panel_has_twelve_diverse_entries_and_balanced_workflow_suite() -> None:
    panel = load_public_control_panel(CONTROL_ROOT / "panel.yaml")
    suite = load_homomer_workflow_suite(CONTROL_ROOT / panel.workflow_suite, panel)

    assert len(panel.entries) == 12
    assert {entry.metabolic_group for entry in panel.entries} == {
        "methanogen",
        "methanotroph",
        "other_prokaryote",
    }
    assert (
        sum(entry.qualification_status == "runnable_control" for entry in panel.entries)
        == 3
    )
    assert sum(case.case_kind == "positive" for case in suite.cases) == 11
    assert sum(case.case_kind == "wrong_model_negative" for case in suite.cases) == 7
    assert {case.case_kind for case in suite.cases} == {
        "positive",
        "wrong_model_negative",
        "target_absent_negative",
        "wrong_catalogue_negative",
        "assumption_violation",
    }
    violation = next(entry for entry in panel.entries if entry.pdb_id == "6CXH")
    assert violation.expected_prototype_outcome == "assumption_violation"
    assert violation.asu_distinct_protein_species == 3
    assert violation.reflection_block_count == 2
    assert violation.derived_mtz is None


@pytest.mark.parametrize("pdb_id", ("8OOX", "7P50", "6P1F"))
def test_runnable_control_construct_mapping_matches_panel(pdb_id: str) -> None:
    panel = load_public_control_panel(CONTROL_ROOT / "panel.yaml")
    entry = next(item for item in panel.entries if item.pdb_id == pdb_id)
    assert entry.active_control_specification is not None
    control = load_public_control_spec(
        CONTROL_ROOT / entry.active_control_specification
    )

    assert control.target_protein_id == entry.catalogue_targets[0].protein_id
    assert control.target_construct == entry.catalogue_targets[0].construct_mapping
    assert control.score_gate.llg_greater_than == 50
    assert control.score_gate.tfz_greater_than == 5
    assert control.score_gate.combination == "or"


def test_8oox_control_binds_qualified_p0_catalogue() -> None:
    control = load_public_control_spec(CONTROL_ROOT / "pdb_8oox.yaml")

    assert (
        control.catalogue_id
        == "methermicoccus_shengliensis_gcf_000711905_1_refseq_2025_11_20"
    )
    assert control.assembly_accession == "GCF_000711905.1"


def test_construct_mapping_rejects_off_by_one_span() -> None:
    document = _yaml_document(CONTROL_ROOT / "pdb_6p1f.yaml")
    construct = document["target_construct"]
    if not isinstance(construct, dict):
        raise AssertionError("target_construct must be a mapping")
    construct["coordinate_match_end"] = 130

    with pytest.raises(ValidationError, match="spans differ"):
        PublicControlSpec.model_validate(document)


def test_panel_rejects_heteromer_mislabeled_as_positive() -> None:
    document = _yaml_document(CONTROL_ROOT / "panel.yaml")
    entries = document["entries"]
    if not isinstance(entries, list):
        raise AssertionError("entries must be a list")
    violation = next(entry for entry in entries if entry["pdb_id"] == "6CXH")
    violation["expected_prototype_outcome"] = "positive"
    violation["qualification_status"] = "source_qualified"

    with pytest.raises(ValidationError, match="must have one species"):
        PublicControlPanelSpec.model_validate(document)


def test_panel_rejects_unsafe_active_specification_path() -> None:
    document = _yaml_document(CONTROL_ROOT / "panel.yaml")
    entries = document["entries"]
    if not isinstance(entries, list):
        raise AssertionError("entries must be a list")
    entries[0]["active_control_specification"] = "../../outside.yaml"

    with pytest.raises(ValidationError, match="active_control_specification"):
        PublicControlPanelSpec.model_validate(document)


def test_workflow_suite_rejects_missing_positive_case(tmp_path: Path) -> None:
    panel = PublicControlPanelSpec.model_validate(
        _yaml_document(CONTROL_ROOT / "panel.yaml")
    )
    document = _yaml_document(CONTROL_ROOT / "homomer_workflow_cases.yaml")
    cases = document["cases"]
    if not isinstance(cases, list):
        raise AssertionError("cases must be a list")
    document["cases"] = [case for case in cases if case["case_id"] != "POS_3W45"]
    path = tmp_path / "suite.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(PublicControlError, match="one positive case"):
        load_homomer_workflow_suite(path, panel)


def test_workflow_suite_rejects_duplicate_positive_case(tmp_path: Path) -> None:
    panel = PublicControlPanelSpec.model_validate(
        _yaml_document(CONTROL_ROOT / "panel.yaml")
    )
    document = _yaml_document(CONTROL_ROOT / "homomer_workflow_cases.yaml")
    cases = document["cases"]
    if not isinstance(cases, list):
        raise AssertionError("cases must be a list")
    duplicate = dict(next(case for case in cases if case["case_id"] == "POS_3W45"))
    duplicate["case_id"] = "POS_3W45_DUPLICATE"
    cases.append(duplicate)
    path = tmp_path / "suite.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(PublicControlError, match="one positive case"):
        load_homomer_workflow_suite(path, panel)


def test_workflow_suite_rejects_size_mismatched_wrong_model(tmp_path: Path) -> None:
    panel = PublicControlPanelSpec.model_validate(
        _yaml_document(CONTROL_ROOT / "panel.yaml")
    )
    document = _yaml_document(CONTROL_ROOT / "homomer_workflow_cases.yaml")
    cases = document["cases"]
    if not isinstance(cases, list):
        raise AssertionError("cases must be a list")
    case = next(item for item in cases if item["case_id"] == "NEG_MODEL_8OOX_8JPV")
    case["model_control_id"] = "PDB_7P50"
    path = tmp_path / "suite.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(PublicControlError, match="not size matched"):
        load_homomer_workflow_suite(path, panel)


def test_offline_panel_preparation_fails_loudly_and_logs_context(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(log_format="human")
    with pytest.raises(PublicControlError, match="downloads are disabled"):
        prepare_public_control_panel(
            PublicPanelPreparationRequest(
                specification=CONTROL_ROOT / "panel.yaml",
                output_directory=tmp_path / "panel output",
                download_missing=False,
                progress=False,
                minimum_free_bytes=0,
            )
        )

    assert "preparing public control panel" in capsys.readouterr().err
    assert not (tmp_path / "panel output/preparation.json").exists()


def test_cli_checks_panel_successfully(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "--no-progress",
                "benchmark",
                "check-public-panel",
                "--panel",
                str(CONTROL_ROOT / "panel.yaml"),
            ]
        )
        == 0
    )
    assert "12 entries" in capsys.readouterr().out
