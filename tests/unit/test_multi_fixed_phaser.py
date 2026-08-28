"""Tests for the Phase III multi-fixed-component Phaser adapter."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import canonical_digest, canonical_json_text
from genome_to_diffraction.mr import (
    CandidateSearchComponent,
    FixedSearchComponent,
    MultiFixedSearchManifest,
    PhaserInputError,
    run_multi_fixed_search,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import PhenixInstallManifest
from genome_to_diffraction.schemas.results import (
    MtzPreflightRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.schemas.v2 import (
    DiffractionSelection,
    DiffractionValueSource,
    diffraction_dataset_id,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
POSITIVE_LOG = (REPOSITORY / "tests/fixtures/phaser/phenix_2_1_positive.log").read_text(
    encoding="utf-8"
)
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
        mass_method="synthetic multi-fixed test sequence",
        residue_policy="standard_exact",
        source_record_count=1,
    )


def _manifest_model() -> PhenixInstallManifest:
    model = load_contract(
        STUBS / "phenix_install_manifest.json",
        "phenix-install-manifest",
        progress=False,
    )
    assert isinstance(model, PhenixInstallManifest)
    return model


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    groups = (_group("ACDE"), _group("FGHI"), _group("KLMN"))
    sequence_groups = tmp_path / "sequence_groups.jsonl"
    sequence_groups.write_text(
        "".join(f"{canonical_json_text(item)}\n" for item in groups),
        encoding="utf-8",
    )
    coordinates = []
    for label in ("A", "B", "C"):
        path = tmp_path / f"component_{label}.pdb"
        path.write_text(
            f"ATOM      1  CA  ALA {label}   1       0.000   0.000   0.000  "
            "1.00 20.00           C\n",
            encoding="utf-8",
        )
        coordinates.append(path)
    fixed = tuple(
        FixedSearchComponent(
            schema_version="2.0",
            label=label,
            sequence_group_id=groups[index].sequence_group_id,
            model_id=f"model_{label.lower()}",
            model_sha256=sha256_file(coordinates[index]),
            coordinate_path=coordinates[index].name,
            coordinate_sha256=sha256_file(coordinates[index]),
            requested_copy_count=2,
            observed_copy_count=2,
            phaser_identity_fraction=0.8 - index * 0.1,
            model_uncertainty_source=f"fixed {label} control identity",
            model_uncertainty_evidence_sha256=hashlib.sha256(
                f"uncertainty:{label}".encode("ascii")
            ).hexdigest(),
        )
        for index, label in enumerate(("A", "B"))
    )
    candidate = CandidateSearchComponent(
        schema_version="2.0",
        label="C",
        sequence_group_id=groups[2].sequence_group_id,
        model_id="model_c",
        model_sha256=sha256_file(coordinates[2]),
        model_path=coordinates[2].name,
        requested_copy_count=2,
        phaser_identity_fraction=0.6,
        model_uncertainty_source="candidate C control identity",
        model_uncertainty_evidence_sha256=hashlib.sha256(b"uncertainty:C").hexdigest(),
    )
    mtz = tmp_path / "control.mtz"
    mtz.write_bytes(b"synthetic multi-fixed MTZ")
    stub = MtzPreflightRecord.model_validate_json(
        (STUBS / "mtz_preflight.jsonl").read_text(encoding="utf-8")
    )
    preflight_record = stub.model_copy(
        update={
            "crystal_id": "9ECN",
            "mtz_sha256": sha256_file(mtz),
            "selected_observation_dataset_id": 1,
            "selected_observation_labels": "F,SIGF",
            "selected_observation_type": "amplitude",
        }
    )
    preflight = tmp_path / "preflight.jsonl"
    preflight.write_text(
        f"{canonical_json_text(preflight_record)}\n",
        encoding="utf-8",
    )
    assert preflight_record.selected_observation_dataset_id is not None
    assert preflight_record.selected_observation_labels is not None
    assert preflight_record.selected_observation_type is not None
    selection = DiffractionSelection.from_content(
        crystal_id="9ECN",
        diffraction_dataset_id=diffraction_dataset_id(
            crystal_id="9ECN",
            mtz_sha256=sha256_file(mtz),
        ),
        mtz_sha256=sha256_file(mtz),
        preflight_id=preflight_record.preflight_id,
        preflight_record_sha256=canonical_digest(preflight_record),
        crystal_manifest_sha256="d" * 64,
        observation_dataset_id=preflight_record.selected_observation_dataset_id,
        observation_labels=tuple(
            value.strip()
            for value in preflight_record.selected_observation_labels.split(",")
        ),
        observation_type=preflight_record.selected_observation_type,
        selected_space_group=preflight_record.space_group,
        resolution_low_a=preflight_record.resolution_low_a,
        resolution_high_a=preflight_record.resolution_high_a,
        observation_source=DiffractionValueSource.MTZ_PREFLIGHT_AUTOMATIC,
        space_group_source=DiffractionValueSource.MTZ_HEADER,
        resolution_low_source=DiffractionValueSource.MTZ_RESOLUTION_RANGE,
        resolution_high_source=DiffractionValueSource.MTZ_RESOLUTION_RANGE,
    )
    manifest = tmp_path / "multi_fixed.json"
    atomic_write_json(
        manifest,
        MultiFixedSearchManifest(
            schema_version="2.0",
            adapter_version="multi-fixed-component-search-input-v2",
            crystal_id="9ECN",
            diffraction_selection=selection,
            parent_solution_id="parent_ab",
            parent_combined_llg=1200.0,
            fixed_components=fixed,
            candidate=candidate,
        ).model_dump(mode="json"),
    )
    return manifest, sequence_groups, preflight, mtz


def _fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    log_text: str,
    returncode: int = 0,
    write_solution: bool = False,
    include_fixed_b: bool = True,
) -> list[str]:
    parameters: list[str] = []

    def fake_validate(path: Path) -> PhenixInstallManifest:
        del path
        return _manifest_model()

    def fake_capture(
        manifest_path: Path,
        arguments: list[str],
        *,
        working_directory: Path,
        timeout_seconds: float | None,
    ) -> subprocess.CompletedProcess[bytes]:
        del manifest_path, timeout_seconds
        parameters.append(Path(arguments[1]).read_text(encoding="utf-8"))
        (working_directory / "PHASER.log").write_text(log_text, encoding="utf-8")
        if write_solution:
            fixed_b = (
                "REMARK ENSEMBLE fixed_B EULER 0 0 0 FRAC 0 0 0\n"
                if include_fixed_b
                else ""
            )
            (working_directory / "PHASER.1.pdb").write_text(
                "REMARK Log-Likelihood Gain: 1700.0\n"
                "REMARK PAK=0 LLG=1700.0 TFZ==25.0\n"
                "REMARK ENSEMBLE fixed_A EULER 0 0 0 FRAC 0 0 0\n"
                f"{fixed_b}"
                "REMARK ENSEMBLE search_C EULER 1 2 3 FRAC 0.1 0.2 0.3\n"
                "REMARK ENSEMBLE search_C EULER 4 5 6 FRAC 0.4 0.5 0.6\n"
                "ATOM\n",
                encoding="utf-8",
            )
            (working_directory / "PHASER.1.mtz").write_bytes(b"combined MTZ")
        return subprocess.CompletedProcess(arguments, returncode, b"capture\n", b"")

    monkeypatch.setattr(
        "genome_to_diffraction.mr.multi_fixed.validate_manifest_environment",
        fake_validate,
    )
    monkeypatch.setattr(
        "genome_to_diffraction.mr.multi_fixed.capture_from_manifest",
        fake_capture,
    )
    return parameters


def test_multi_fixed_manifest_rejects_unqualified_one_fixed_a_route(
    tmp_path: Path,
) -> None:
    manifest_path, _, _, _ = _inputs(tmp_path)
    source = MultiFixedSearchManifest.model_validate_json(manifest_path.read_bytes())
    component_b = source.fixed_components[1]

    with pytest.raises(ValueError, match="at least 2"):
        MultiFixedSearchManifest(
            schema_version="2.0",
            adapter_version="multi-fixed-component-search-input-v2",
            crystal_id=source.crystal_id,
            diffraction_selection=source.diffraction_selection,
            parent_solution_id="parent_a",
            parent_combined_llg=500.0,
            fixed_components=(source.fixed_components[0],),
            candidate=CandidateSearchComponent(
                schema_version="2.0",
                label="B",
                sequence_group_id=component_b.sequence_group_id,
                model_id=component_b.model_id,
                model_sha256=component_b.model_sha256,
                model_path=component_b.coordinate_path,
                requested_copy_count=component_b.requested_copy_count,
                phaser_identity_fraction=component_b.phaser_identity_fraction,
                model_uncertainty_source=component_b.model_uncertainty_source,
                model_uncertainty_evidence_sha256=(
                    component_b.model_uncertainty_evidence_sha256
                ),
            ),
        )


def test_multi_fixed_a_b_searches_two_c_without_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, groups, preflight, mtz = _inputs(tmp_path)
    parameters = _fake_runtime(
        monkeypatch,
        log_text=POSITIVE_LOG,
        write_solution=True,
    )

    result = run_multi_fixed_search(
        manifest_path=manifest,
        sequence_groups_jsonl=groups,
        preflight_jsonl=preflight,
        mtz_path=mtz,
        phenix_manifest=STUBS / "phenix_install_manifest.json",
        output_directory=tmp_path / "output",
        threads=8,
    )

    command = json.loads(
        (tmp_path / "output/phaser_command.json").read_text(encoding="utf-8")
    )
    assert command["adapter_version"] == (
        "phenix-multi-fixed-joint-component-v2-diffraction"
    )
    assert command["diffraction_selection_id"].startswith("diffsel_")
    assert command["parameters_sha256"]
    assert result.execution_status == "completed_hit"
    assert result.fixed_component_labels == ("A", "B")
    assert result.candidate_component_label == "C"
    assert result.fixed_components_observed is True
    assert result.candidate_placement_count == 2
    assert result.candidate_placement_observed is True
    assert result.incremental_llg == pytest.approx(500.0)
    assert result.candidate_tfz == pytest.approx(25.0)
    assert result.top_solution_packed is True
    assert result.scientific_status == "search_evidence_only"
    assert result.exact_identity_claimed is False
    assert result.complete_composition_claimed is False
    text = parameters[0]
    assert text.count("solution_at_origin = True") == 2
    assert "model_id = fixed_A" in text
    assert "model_id = fixed_B" in text
    assert "model_id = search_C" in text
    assert "ensembles = search_C" in text
    assert "copies = 2" in text
    assert text.count("num = 2") == 3
    assert "crystal_symmetry {" in text
    assert "space_group =" in text
    assert "resolution {" in text
    assert "low = 20" in text
    assert "high = 2" in text


@pytest.mark.parametrize(
    ("selection_field", "preflight_field", "changed_value", "rendered"),
    (
        ("selected_space_group", "space_group", "P 21 21 2", "P 21 21 2"),
        ("resolution_low_a", "resolution_low_a", 25.0, "low = 25"),
        ("resolution_high_a", "resolution_high_a", 2.5, "high = 2.5"),
    ),
)
def test_multi_fixed_diffraction_change_changes_command_and_search_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selection_field: str,
    preflight_field: str,
    changed_value: str | float,
    rendered: str,
) -> None:
    manifest_path, groups, preflight_path, mtz = _inputs(tmp_path)
    parameters = _fake_runtime(monkeypatch, log_text=NO_EXTENSION_LOG)
    first = run_multi_fixed_search(
        manifest_path=manifest_path,
        sequence_groups_jsonl=groups,
        preflight_jsonl=preflight_path,
        mtz_path=mtz,
        phenix_manifest=STUBS / "phenix_install_manifest.json",
        output_directory=tmp_path / "first",
    )
    manifest = MultiFixedSearchManifest.model_validate_json(manifest_path.read_bytes())
    preflight = MtzPreflightRecord.model_validate_json(preflight_path.read_bytes())
    changed_preflight = preflight.model_copy(update={preflight_field: changed_value})
    changed_preflight_path = tmp_path / "changed-preflight.jsonl"
    changed_preflight_path.write_text(
        f"{canonical_json_text(changed_preflight)}\n",
        encoding="utf-8",
    )
    selection_values = manifest.diffraction_selection.model_dump(mode="python")
    selection_values.pop("diffraction_selection_id")
    selection_values[selection_field] = changed_value
    selection_values["preflight_record_sha256"] = canonical_digest(changed_preflight)
    changed_selection = DiffractionSelection.from_content(**selection_values)
    changed_manifest = tmp_path / "changed-manifest.json"
    atomic_write_json(
        changed_manifest,
        MultiFixedSearchManifest(
            schema_version="2.0",
            adapter_version="multi-fixed-component-search-input-v2",
            crystal_id=manifest.crystal_id,
            diffraction_selection=changed_selection,
            parent_solution_id=manifest.parent_solution_id,
            parent_combined_llg=manifest.parent_combined_llg,
            fixed_components=manifest.fixed_components,
            candidate=manifest.candidate,
        ).model_dump(mode="json"),
    )
    second = run_multi_fixed_search(
        manifest_path=changed_manifest,
        sequence_groups_jsonl=groups,
        preflight_jsonl=changed_preflight_path,
        mtz_path=mtz,
        phenix_manifest=STUBS / "phenix_install_manifest.json",
        output_directory=tmp_path / "second",
    )

    assert first.search_id != second.search_id
    assert parameters[0] != parameters[1]
    assert rendered in parameters[1]


def test_multi_fixed_missing_fixed_marker_remains_unpromoted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, groups, preflight, mtz = _inputs(tmp_path)
    _fake_runtime(
        monkeypatch,
        log_text=POSITIVE_LOG,
        write_solution=True,
        include_fixed_b=False,
    )

    result = run_multi_fixed_search(
        manifest_path=manifest,
        sequence_groups_jsonl=groups,
        preflight_jsonl=preflight,
        mtz_path=mtz,
        phenix_manifest=STUBS / "phenix_install_manifest.json",
        output_directory=tmp_path / "output",
    )

    assert result.execution_status == "completed_hit"
    assert result.fixed_components_observed is False
    assert result.candidate_placement_observed is False
    assert "combined_solution_lacks_fixed_component_markers" in result.warnings
    assert result.scientific_status == "search_evidence_only"


def test_multi_fixed_no_extension_is_scientific_no_hit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, groups, preflight, mtz = _inputs(tmp_path)
    _fake_runtime(monkeypatch, log_text=NO_EXTENSION_LOG)

    result = run_multi_fixed_search(
        manifest_path=manifest,
        sequence_groups_jsonl=groups,
        preflight_jsonl=preflight,
        mtz_path=mtz,
        phenix_manifest=STUBS / "phenix_install_manifest.json",
        output_directory=tmp_path / "output",
    )

    assert result.execution_status == "completed_no_hit"
    assert result.combined_coordinate_path is None
    assert result.exact_identity_claimed is False
    assert result.complete_composition_claimed is False
    assert result.rejection_reason == "phaser_reported_no_component_extension"


def test_changed_fixed_coordinate_fails_before_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, groups, preflight, mtz = _inputs(tmp_path)
    (tmp_path / "component_A.pdb").write_text("changed\n", encoding="utf-8")
    parameters = _fake_runtime(monkeypatch, log_text=NO_EXTENSION_LOG)

    with pytest.raises(PhaserInputError, match="fixed component A checksum differs"):
        run_multi_fixed_search(
            manifest_path=manifest,
            sequence_groups_jsonl=groups,
            preflight_jsonl=preflight,
            mtz_path=mtz,
            phenix_manifest=STUBS / "phenix_install_manifest.json",
            output_directory=tmp_path / "output",
        )

    assert parameters == []
