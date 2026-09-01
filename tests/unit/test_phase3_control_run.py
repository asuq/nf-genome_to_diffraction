import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from genome_to_diffraction.benchmarks import phase3_control_run as control_run
from genome_to_diffraction.diffraction import PreflightRequest
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.mr import (
    PartnerSearchRequest,
    PhaserPerPlacementRequest,
    PhaserRunRequest,
)
from genome_to_diffraction.schemas.results import SequenceGroupRecord
from genome_to_diffraction.schemas.v2 import (
    DiffractionSelection,
    DiffractionValueSource,
    diffraction_dataset_id,
)
from genome_to_diffraction.status import ExecutionStatus


def _write(path: Path, text: str) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="ascii")
    payload = path.read_bytes()
    return {
        "path": path.name if path.parent.name != "models" else f"models/{path.name}",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def _group(label: str) -> SequenceGroupRecord:
    sequence = {"A": "MPEPTIDEA", "B": "MPEPTIDEB", "C": "MPEPTIDEC", "D": "MPEPTIDED"}[
        label
    ]
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        mass_method="synthetic exact sequence mass",
        residue_policy="standard_exact",
        source_record_count=1,
        molecular_mass_da=1000.0 + len(sequence),
    )


def _prepared_9ecn(root: Path) -> Path:
    groups = {label: _group(label) for label in ("A", "B", "C")}
    files = {
        "crystal_manifest": _write(root / "crystals.json", "{}\n"),
        "sequence_groups": _write(
            root / "sequence_groups.jsonl",
            "".join(
                f"{canonical_json_text(groups[label])}\n" for label in ("A", "B", "C")
            ),
        ),
        "processed_models": _write(root / "processed_models.jsonl", "{}\n"),
        "model_preparation_manifest": _write(
            root / "model_preparation_manifest.json", "{}\n"
        ),
        "hypotheses": _write(root / "mr_hypotheses.jsonl", "{}\n"),
        "mtz": _write(root / "9ECN.mtz", "MTZ\n"),
    }
    components = []
    for label in ("A", "B", "C"):
        record = _write(root / "models" / f"component_{label}.pdb", f"ATOM {label}\n")
        files[f"component_{label}_model"] = record
        components.append(
            {
                "label": label,
                "requested_copy_count": 2,
                "sequence_group_id": groups[label].sequence_group_id,
                "catalogue_sequence_sha256": groups[label].sha256,
                "model_id": f"model_{label}",
                "model_sha256": record["sha256"],
            }
        )
    (root / "preparation_manifest.json").write_text(
        json.dumps(
            {
                "adapter_version": "9ecn-fixed-two-a-two-b-two-c-inputs-v1",
                "crystal_id": "9ECN",
                "composition": {"A": 2, "B": 2, "C": 2},
                "parent_hypothesis_id": "parent_A_two_copies",
                "components": components,
                "files": files,
            }
        )
        + "\n",
        encoding="ascii",
    )
    return root


def _wrong_control_manifest(
    root: Path,
    *,
    group: SequenceGroupRecord,
    groups: Path,
    model: Path,
) -> Path:
    model_sha256 = hashlib.sha256(model.read_bytes()).hexdigest()
    manifest = root / "wrong-control.json"
    manifest.write_text(
        json.dumps(
            {
                "adapter_version": "heteromer-p6-control-slice-v2",
                "wrong_partner": {
                    "partner_sequence_group_id": group.sequence_group_id,
                    "partner_model_sha256": model_sha256,
                },
                "positive_controls": {
                    "3U7Q": {
                        "partner_sequence_group_id": group.sequence_group_id,
                        "partner_model_sha256": model_sha256,
                    }
                },
                "files": {
                    "wrong_partner_model": {
                        "path": model.name,
                        "sha256": model_sha256,
                        "size_bytes": model.stat().st_size,
                    },
                    "wrong_sequence_groups": {
                        "path": groups.name,
                        "sha256": hashlib.sha256(groups.read_bytes()).hexdigest(),
                        "size_bytes": groups.stat().st_size,
                    },
                },
            }
        )
        + "\n",
        encoding="ascii",
    )
    return manifest


def test_fixed_9ecn_chain_retains_claim_free_depth_three_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _prepared_9ecn(tmp_path / "prepared")
    phenix_manifest = tmp_path / "phenix.json"
    phenix_manifest.write_text("{}\n", encoding="ascii")
    wrong_group = _group("D")
    wrong_groups = tmp_path / "wrong-sequence-groups.jsonl"
    wrong_groups.write_text(
        f"{canonical_json_text(wrong_group)}\n",
        encoding="ascii",
    )
    wrong_model = tmp_path / "wrong-C.pdb"
    wrong_model.write_text("ATOM WRONG C\n", encoding="ascii")
    wrong_model_sha256 = hashlib.sha256(wrong_model.read_bytes()).hexdigest()
    wrong_control = _wrong_control_manifest(
        tmp_path,
        group=wrong_group,
        groups=wrong_groups,
        model=wrong_model,
    )

    def fake_preflight(request: PreflightRequest) -> SimpleNamespace:
        output = request.output_directory
        output.mkdir(parents=True)
        path = output / "mtz_preflight.jsonl"
        path.write_text("{}\n", encoding="ascii")
        return SimpleNamespace(jsonl_path=path)

    def fake_parent(request: PhaserRunRequest) -> SimpleNamespace:
        output = request.output_directory
        output.mkdir(parents=True)
        coordinate = output / "PHASER.1.pdb"
        output_mtz = output / "PHASER.1.mtz"
        coordinate.write_text("REMARK ENSEMBLE parent\n", encoding="ascii")
        output_mtz.write_text("MTZ parent\n", encoding="ascii")
        digest = hashlib.sha256(coordinate.read_bytes()).hexdigest()
        result = output / "normalised_mr_result.json"
        result.write_text(
            json.dumps(
                {
                    "execution_status": "completed_hit",
                    "placed_copy_count": 2,
                    "llg": 100.0,
                    "tfz": 18.0,
                    "solution_coordinate_path": coordinate.name,
                    "solution_coordinate_sha256": digest,
                    "output_mtz_sha256": hashlib.sha256(
                        output_mtz.read_bytes()
                    ).hexdigest(),
                }
            )
            + "\n",
            encoding="ascii",
        )
        command = output / "phaser_command.json"
        command.write_text(
            json.dumps(
                {
                    "model_identity_percent": 100.0,
                    "model_uncertainty_source": "known control identity",
                }
            )
            + "\n",
            encoding="ascii",
        )
        return SimpleNamespace(result_json=result, command_json=command)

    def fake_partner(request: PartnerSearchRequest) -> SimpleNamespace:
        output = request.output_directory
        output.mkdir(parents=True)
        result = output / "partner_search_result.json"
        result.write_text("{}\n", encoding="ascii")
        command = output / "phaser_command.json"
        command.write_text(
            '{"partner_model_identity_fraction":1.0}\n', encoding="ascii"
        )
        combined = output / "PHASER.1.pdb"
        output_mtz = output / "PHASER.1.mtz"
        combined.write_text("ATOM COMBINED A B\n", encoding="ascii")
        output_mtz.write_text("MTZ combined A B\n", encoding="ascii")
        return SimpleNamespace(
            result=SimpleNamespace(
                execution_status=ExecutionStatus.COMPLETED_HIT,
                combined_solution_id="solution_AB",
                combined_llg=250.0,
                search_id="search_B",
                tool_version="Phaser test",
                partner_tfz=12.0,
                incremental_llg=150.0,
                top_solution_packed=True,
                combined_coordinate_sha256=hashlib.sha256(
                    combined.read_bytes()
                ).hexdigest(),
                output_mtz_sha256=hashlib.sha256(output_mtz.read_bytes()).hexdigest(),
            ),
            result_json=result,
            command_json=command,
        )

    def fake_multi_fixed(
        *,
        manifest_path: Path,
        sequence_groups_jsonl: Path,
        preflight_jsonl: Path,
        mtz_path: Path,
        phenix_manifest: Path,
        output_directory: Path,
        threads: int = 1,
        timeout_seconds: float | None = None,
    ) -> SimpleNamespace:
        del (
            sequence_groups_jsonl,
            preflight_jsonl,
            mtz_path,
            phenix_manifest,
            threads,
            timeout_seconds,
        )
        manifest = json.loads(manifest_path.read_text())
        assert [row["label"] for row in manifest["fixed_components"]] == ["A", "B"]
        assert manifest["candidate"]["label"] == "C"
        is_wrong = output_directory.name == "wrong_C"
        assert (
            manifest["candidate"]["sequence_group_id"] == wrong_group.sequence_group_id
        ) is is_wrong
        output = output_directory
        output.mkdir(parents=True)
        (output / "component_search_result.json").write_text("{}\n", encoding="ascii")
        (output / "phaser_command.json").write_text("{}\n", encoding="ascii")
        combined = output / "PHASER.1.pdb"
        output_mtz = output / "PHASER.1.mtz"
        combined.write_text("ATOM COMBINED\n", encoding="ascii")
        output_mtz.write_text("MTZ combined\n", encoding="ascii")
        return SimpleNamespace(
            execution_status=ExecutionStatus.COMPLETED_HIT,
            search_id="search_C",
            tool_version="Phaser test",
            top_solution_packed=True,
            fixed_components_observed=True,
            candidate_placement_observed=True,
            scientific_status="search_evidence_only",
            exact_identity_claimed=False,
            complete_composition_claimed=False,
            candidate_tfz=12.0,
            incremental_llg=150.0,
            combined_coordinate_sha256=hashlib.sha256(
                combined.read_bytes()
            ).hexdigest(),
            output_mtz_sha256=hashlib.sha256(output_mtz.read_bytes()).hexdigest(),
        )

    def fake_inventory(request: PhaserPerPlacementRequest) -> SimpleNamespace:
        output = request.output_directory
        labels = ("A", "B") if output.name == "partner_B" else ("A", "B", "C")
        groups = []
        for label in labels:
            coordinate = output / f"component_{label}.pdb"
            coordinate.write_text(f"ATOM {label}\n", encoding="ascii")
            groups.append(
                {
                    "component_label": label,
                    "expected_copy_count": 2,
                    "observed_copy_count": 2,
                    "coordinate_path": coordinate.name,
                    "coordinate_sha256": hashlib.sha256(
                        coordinate.read_bytes()
                    ).hexdigest(),
                }
            )
        inventory = output / "phaser_per_placement_inventory.json"
        inventory.write_text(
            json.dumps(
                {
                    "component_groups": groups,
                    "recombination_status": "verified_exact_combined_atom_partition",
                    "combined_atom_count": 60,
                    "recombined_atom_count": 60,
                }
            )
            + "\n",
            encoding="ascii",
        )
        return SimpleNamespace(inventory_json=inventory)

    monkeypatch.setattr(control_run, "preflight_crystals", fake_preflight)
    selection_sha = "9" * 64
    monkeypatch.setattr(
        control_run,
        "_diffraction_selection",
        lambda _manifest, _preflight: DiffractionSelection.from_content(
            crystal_id="9ECN",
            diffraction_dataset_id=diffraction_dataset_id(
                crystal_id="9ECN",
                mtz_sha256=selection_sha,
            ),
            mtz_sha256=selection_sha,
            preflight_id="preflight_test",
            preflight_record_sha256="8" * 64,
            crystal_manifest_sha256="7" * 64,
            observation_dataset_id=1,
            observation_labels=("F", "SIGF"),
            observation_type="amplitude",
            selected_space_group="P 21 21 21",
            resolution_low_a=50.0,
            resolution_high_a=2.0,
            observation_source=DiffractionValueSource.MTZ_PREFLIGHT_AUTOMATIC,
            space_group_source=DiffractionValueSource.MTZ_HEADER,
            resolution_low_source=DiffractionValueSource.MTZ_RESOLUTION_RANGE,
            resolution_high_source=DiffractionValueSource.MTZ_RESOLUTION_RANGE,
        ),
    )
    monkeypatch.setattr(control_run, "run_first_copy_phaser", fake_parent)
    monkeypatch.setattr(control_run, "run_partner_search", fake_partner)
    monkeypatch.setattr(control_run, "run_multi_fixed_search", fake_multi_fixed)
    monkeypatch.setattr(
        control_run, "collect_phaser_per_placement_outputs", fake_inventory
    )

    result = control_run.run_9ecn_phase3_control(
        control_run.Phase3ControlExecutionRequest(
            preparation_directory=prepared,
            phenix_manifest=phenix_manifest,
            wrong_c_sequence_groups_jsonl=wrong_groups,
            wrong_c_sequence_group_id=wrong_group.sequence_group_id,
            wrong_c_model=wrong_model,
            wrong_c_control_manifest=wrong_control,
            expected_wrong_c_model_sha256=wrong_model_sha256,
            wrong_c_model_identity_fraction=1.0,
            output_directory=tmp_path / "output",
            progress=False,
        )
    )

    report = json.loads(result.report.read_text(encoding="utf-8"))
    assert report["adapter_version"] == (
        "9ecn-phase3-depth-three-control-v3-wrong-c-assessment"
    )
    assert report["gate_passed"] is True
    assert report["component_copy_counts"] == {"A": 2, "B": 2, "C": 2}
    assert report["generic_scientific_status"] == "search_evidence_only"
    assert report["exact_identity_claimed_by_search"] is False
    assert report["complete_composition_claimed_by_search"] is False
    assert report["wrong_c_claim_boundary_passed"] is True
    assert report["wrong_c_execution_status"] == "completed_hit"
    assert report["wrong_c_top_solution_packed"] is True
    assert report["wrong_c_exact_identity_claimed"] is False
    assert report["wrong_c_complete_composition_claimed"] is False
    assert report["wrong_c_scientific_status"] == "search_evidence_only"
    assert report["wrong_c_assessment_claim_eligible"] is False
    assert report["wrong_c_assessment_claimed"] is False
    assert report["wrong_c_assessment_id"].startswith("compassess_")
    checksum_rows = [
        line.split(maxsplit=1) for line in result.checksums.read_text().splitlines()
    ]
    assert len(checksum_rows) >= 15
    for digest, relative in checksum_rows:
        assert (
            hashlib.sha256((result.report.parent / relative).read_bytes()).hexdigest()
            == digest
        )


def test_fixed_9ecn_chain_rejects_changed_wrong_c_model(tmp_path: Path) -> None:
    prepared = _prepared_9ecn(tmp_path / "prepared")
    phenix_manifest = tmp_path / "phenix.json"
    phenix_manifest.write_text("{}\n", encoding="ascii")
    wrong_group = _group("D")
    wrong_groups = tmp_path / "wrong-sequence-groups.jsonl"
    wrong_groups.write_text(
        f"{canonical_json_text(wrong_group)}\n",
        encoding="ascii",
    )
    wrong_model = tmp_path / "wrong-C.pdb"
    wrong_model.write_text("ATOM WRONG C\n", encoding="ascii")
    wrong_control = _wrong_control_manifest(
        tmp_path,
        group=wrong_group,
        groups=wrong_groups,
        model=wrong_model,
    )
    output = tmp_path / "output"

    with pytest.raises(
        control_run.Phase3ControlExecutionError,
        match="wrong-C model identity differs",
    ):
        control_run.run_9ecn_phase3_control(
            control_run.Phase3ControlExecutionRequest(
                preparation_directory=prepared,
                phenix_manifest=phenix_manifest,
                wrong_c_sequence_groups_jsonl=wrong_groups,
                wrong_c_sequence_group_id=wrong_group.sequence_group_id,
                wrong_c_model=wrong_model,
                wrong_c_control_manifest=wrong_control,
                expected_wrong_c_model_sha256="0" * 64,
                wrong_c_model_identity_fraction=1.0,
                output_directory=output,
                progress=False,
            )
        )
    assert not output.exists()
