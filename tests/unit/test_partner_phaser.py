"""Tests for the fixed-A/joint-B Phaser adapter."""

import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.cli import main
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.mr import (
    PartnerSearchRequest,
    PhaserInputError,
    run_partner_search,
)
from genome_to_diffraction.mr.partner import _score_cohort
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import PhenixInstallManifest
from genome_to_diffraction.schemas.results import (
    MtzPreflightRecord,
    PartnerSearchResult,
    SequenceGroupRecord,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
PHASER_FIXTURES = REPOSITORY / "tests/fixtures/phaser"
POSITIVE_LOG = (PHASER_FIXTURES / "phenix_2_1_positive.log").read_text(encoding="utf-8")
NO_EXTENSION_LOG = (
    "PHENIX: Phaser 2.8.4\n"
    "Top LLG (packs) = 1200.0\n"
    "** Sorry - No solution with all components\n"
    "** Search did not extend input solution with new components\n"
    "EXIT STATUS: SUCCESS\n"
)


def _group(sequence: str) -> SequenceGroupRecord:
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        mass_method="synthetic fixed-A/one-B test sequence",
        residue_policy="standard_exact",
        source_record_count=1,
    )


def _manifest() -> PhenixInstallManifest:
    model = load_contract(
        STUBS / "phenix_install_manifest.json",
        "phenix-install-manifest",
        progress=False,
    )
    assert isinstance(model, PhenixInstallManifest)
    return model


def _request(tmp_path: Path) -> PartnerSearchRequest:
    parent_group = _group("ACDE")
    partner_group = _group("FGHI")
    groups = tmp_path / "sequence_groups.jsonl"
    groups.write_text(
        f"{canonical_json_text(parent_group)}\n{canonical_json_text(partner_group)}\n",
        encoding="utf-8",
    )
    parent = tmp_path / "fixed_A.pdb"
    parent.write_text(
        "REMARK fixed A control\n"
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  "
        "1.00 20.00           C\n",
        encoding="utf-8",
    )
    partner_model = tmp_path / "search_B.pdb"
    partner_model.write_text(
        "ATOM      1  CA  GLY B   1       1.000   1.000   1.000  "
        "1.00 20.00           C\n",
        encoding="utf-8",
    )
    mtz = tmp_path / "control.mtz"
    mtz.write_bytes(b"synthetic heteromer MTZ")
    stub_preflight = MtzPreflightRecord.model_validate_json(
        (STUBS / "mtz_preflight.jsonl").read_text(encoding="utf-8")
    )
    preflight = stub_preflight.model_copy(update={"mtz_sha256": sha256_file(mtz)})
    preflights = tmp_path / "preflight.jsonl"
    preflights.write_text(f"{canonical_json_text(preflight)}\n", encoding="utf-8")
    return PartnerSearchRequest(
        crystal_id=preflight.crystal_id,
        parent_solution_id="parent_" + "a" * 64,
        parent_sequence_group_id=parent_group.sequence_group_id,
        partner_sequence_group_id=partner_group.sequence_group_id,
        sequence_groups_jsonl=groups,
        parent_coordinate=parent,
        expected_parent_coordinate_sha256=sha256_file(parent),
        parent_llg=1200.0,
        parent_model_identity_fraction=0.35,
        parent_model_uncertainty_source="registered PDB homologue identity",
        partner_model=partner_model,
        expected_partner_model_sha256=sha256_file(partner_model),
        partner_model_identity_fraction=0.42,
        preflight_jsonl=preflights,
        mtz=mtz,
        phenix_manifest=STUBS / "phenix_install_manifest.json",
        output_directory=tmp_path / "partner_output",
        threads=8,
        progress=False,
    )


def _fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    log_text: str,
    returncode: int = 0,
    write_solution: bool = False,
    include_component_markers: bool = True,
    partner_marker_count: int = 1,
    pdb_llg: float = 1622.91,
    pdb_tfz: float = 49.7,
    corrupt_evidence: str | None = None,
) -> list[str]:
    captured_parameters: list[str] = []

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
        assert arguments[0] == "phenix.phaser"
        parameters = Path(arguments[1]).read_text(encoding="utf-8")
        captured_parameters.append(parameters)
        (working_directory / "PHASER.log").write_text(log_text, encoding="utf-8")
        if write_solution:
            markers = (
                "REMARK ENSEMBLE fixed_parent EULER 0 0 0 FRAC 0 0 0\n"
                + "REMARK ENSEMBLE search_partner EULER 1 2 3 FRAC 0.1 0.2 0.3\n"
                * partner_marker_count
                if include_component_markers
                else "REMARK ENSEMBLE unknown EULER 0 0 0 FRAC 0 0 0\n"
            )
            (working_directory / "PHASER.1.pdb").write_text(
                f"REMARK Log-Likelihood Gain: {pdb_llg}\n"
                f"REMARK PAK=0 LLG={pdb_llg} TFZ=={pdb_tfz}\n"
                f"{markers}"
                "ATOM\n",
                encoding="utf-8",
            )
            (working_directory / "PHASER.1.mtz").write_bytes(b"combined MTZ")
        if corrupt_evidence is not None:
            evidence = working_directory / corrupt_evidence
            evidence.write_bytes(evidence.read_bytes() + b"\xff")
        return subprocess.CompletedProcess(arguments, returncode, b"capture\n", b"")

    monkeypatch.setattr(
        "genome_to_diffraction.mr.partner.validate_manifest_environment",
        fake_validate,
    )
    monkeypatch.setattr(
        "genome_to_diffraction.mr.partner.capture_from_manifest", fake_capture
    )
    return captured_parameters


def test_fixed_a_one_b_command_and_primary_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    parameters = _fake_runtime(monkeypatch, log_text=POSITIVE_LOG, write_solution=True)

    output = run_partner_search(request)

    result = output.result
    command = json.loads(output.command_json.read_text(encoding="utf-8"))
    assert command["adapter_version"] == "phenix-fixed-a-joint-b-v6-native-placements"
    assert result.execution_status == "completed_hit"
    assert result.partner_tfz == pytest.approx(49.7)
    assert result.combined_llg == pytest.approx(1622.91)
    assert result.incremental_llg == pytest.approx(422.91)
    assert result.parent_model_identity_fraction == pytest.approx(0.35)
    assert result.parent_model_uncertainty_source == "registered PDB homologue identity"
    assert result.score_cohort == "primary"
    assert result.fixed_parent_placement_observed is True
    assert result.partner_placement_count == 1
    assert result.partner_placement_observed is True
    assert result.top_solution_packed is True
    assert result.combined_coordinate_sha256 == sha256_file(
        request.output_directory / "PHASER.1.pdb"
    )
    assert result.output_mtz_sha256 == sha256_file(
        request.output_directory / "PHASER.1.mtz"
    )
    text = parameters[0]
    assert text.count("chain {") == 2
    assert text.count("num = 1") == 2
    assert "solution_at_origin = True" in text
    assert "model_id = fixed_parent" in text
    assert "model_id = search_partner" in text
    assert "ensembles = search_partner" in text
    assert "copies = 1" in text
    assert "identity = 0.35" in text
    assert "identity = 0.42" in text
    assert "jobs = 8" in text
    assert "xyzout = True" in text
    assert "xyzout_ensemble = True" in text
    assert "keywords = True" in text


def test_fixed_two_a_searches_two_b_jointly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    request = replace(
        request,
        parent_copy_count=2,
        partner_copy_count=2,
    )
    parameters = _fake_runtime(
        monkeypatch,
        log_text=POSITIVE_LOG,
        write_solution=True,
        partner_marker_count=2,
    )

    result = run_partner_search(request).result

    assert result.parent_copy_count == 2
    assert result.requested_partner_copy_count == 2
    assert result.partner_placement_count == 2
    assert result.partner_placement_observed is True
    text = parameters[0]
    assert text.count("num = 2") == 2
    assert "copies = 2" in text


def test_partner_scores_use_strict_fallback_cohort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    fallback_log = (
        "PHENIX: Phaser 2.8.4\n"
        "Top LLG (packs) = 1275.0\n"
        "Refined TF/TFZ equivalent = 1275.0/ 7.0\n"
        "1 accepted of 1 solutions\n"
        "1 pack of 1 accepted solutions\n"
        "** There was 1 solution\n"
        "EXIT STATUS: SUCCESS\n"
    )
    _fake_runtime(
        monkeypatch,
        log_text=fallback_log,
        write_solution=True,
        pdb_llg=1275.0,
        pdb_tfz=7.0,
    )

    result = run_partner_search(request).result

    assert result.combined_llg == pytest.approx(1275.0)
    assert result.incremental_llg == pytest.approx(75.0)
    assert result.partner_tfz == pytest.approx(7.0)
    assert result.score_cohort == "fallback"


def test_partner_score_thresholds_are_strict() -> None:
    assert _score_cohort(100.0, 10.0) == "fallback"
    assert _score_cohort(50.0, 5.0) == "below_threshold"


def test_explicit_no_extension_is_scientific_no_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    _fake_runtime(monkeypatch, log_text=NO_EXTENSION_LOG)

    result = run_partner_search(request).result

    assert result.execution_status == "completed_no_hit"
    assert result.combined_llg is None
    assert result.partner_tfz is None
    assert result.combined_solution_id is None
    assert result.failed_search_proves_partner_absence is False
    assert result.rejection_reason == "phaser_reported_no_partner_solution"


@pytest.mark.parametrize("corrupt_evidence", ("PHASER.log", "PHASER.1.pdb"))
def test_partner_rejects_non_utf8_scientific_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corrupt_evidence: str,
) -> None:
    request = _request(tmp_path)
    _fake_runtime(
        monkeypatch,
        log_text=POSITIVE_LOG,
        write_solution=True,
        corrupt_evidence=corrupt_evidence,
    )

    result = run_partner_search(request).result

    assert result.execution_status == "failed_parse"
    assert "not valid UTF-8" in (result.rejection_reason or "")
    assert result.top_solution_packed is False
    assert result.combined_coordinate_path is None


@pytest.mark.parametrize(
    ("returncode", "log_text", "expected_status", "reason"),
    [
        (2, "fatal\n", "failed_tool_execution", "phenix.phaser_exit_2"),
        (0, "EXIT STATUS: SUCCESS\n", "failed_parse", "solution count"),
    ],
)
def test_tool_and_parse_failures_remain_distinct(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    log_text: str,
    expected_status: str,
    reason: str,
) -> None:
    request = _request(tmp_path)
    _fake_runtime(monkeypatch, log_text=log_text, returncode=returncode)

    result = run_partner_search(request).result

    assert result.execution_status == expected_status
    assert reason in (result.rejection_reason or "")
    assert result.combined_coordinate_path is None


def test_changed_partner_model_fails_before_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    request.partner_model.write_text("changed\n", encoding="utf-8")
    parameters = _fake_runtime(monkeypatch, log_text=NO_EXTENSION_LOG)

    with pytest.raises(PhaserInputError, match="B search model checksum differs"):
        run_partner_search(request)

    assert parameters == []


def test_partner_result_rejects_incorrect_incremental_llg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    _fake_runtime(monkeypatch, log_text=POSITIVE_LOG, write_solution=True)
    document = run_partner_search(request).result.model_dump(mode="json")
    document["incremental_llg"] = 1.0

    with pytest.raises(ValidationError, match="incremental LLG"):
        PartnerSearchResult.model_validate(document)


def test_partner_result_requires_paired_parent_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    _fake_runtime(monkeypatch, log_text=POSITIVE_LOG, write_solution=True)
    document = run_partner_search(request).result.model_dump(mode="json")
    document["parent_model_uncertainty_source"] = None

    with pytest.raises(ValidationError, match="parent model identity"):
        PartnerSearchResult.model_validate(document)


def test_partner_cli_exposes_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _request(tmp_path)
    _fake_runtime(monkeypatch, log_text=NO_EXTENSION_LOG)

    exit_status = main(
        [
            "--no-progress",
            "mr",
            "search-partner",
            "--crystal-id",
            request.crystal_id,
            "--parent-solution-id",
            request.parent_solution_id,
            "--parent-sequence-group-id",
            request.parent_sequence_group_id,
            "--partner-sequence-group-id",
            request.partner_sequence_group_id,
            "--sequence-groups",
            str(request.sequence_groups_jsonl),
            "--parent-coordinate",
            str(request.parent_coordinate),
            "--expected-parent-coordinate-sha256",
            request.expected_parent_coordinate_sha256,
            "--parent-llg",
            str(request.parent_llg),
            "--parent-model-identity-fraction",
            str(request.parent_model_identity_fraction),
            "--parent-model-uncertainty-source",
            request.parent_model_uncertainty_source,
            "--partner-model",
            str(request.partner_model),
            "--expected-partner-model-sha256",
            request.expected_partner_model_sha256,
            "--partner-model-identity-fraction",
            str(request.partner_model_identity_fraction),
            "--preflight",
            str(request.preflight_jsonl),
            "--mtz",
            str(request.mtz),
            "--phenix-manifest",
            str(request.phenix_manifest),
            "--outdir",
            str(request.output_directory),
            "--threads",
            str(request.threads),
        ]
    )

    assert exit_status == 0
    assert "Partner MR completed_no_hit" in capsys.readouterr().out
