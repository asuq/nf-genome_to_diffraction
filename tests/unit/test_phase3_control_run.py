import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from genome_to_diffraction.benchmarks import phase3_control_run as control_run
from genome_to_diffraction.diffraction import PreflightRequest
from genome_to_diffraction.mr import (
    PartnerSearchRequest,
    PhaserPerPlacementRequest,
    PhaserRunRequest,
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


def _prepared_9ecn(root: Path) -> Path:
    files = {
        "crystal_manifest": _write(root / "crystals.json", "{}\n"),
        "sequence_groups": _write(root / "sequence_groups.jsonl", "{}\n"),
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
                "sequence_group_id": f"seq_{label}",
                "catalogue_sequence_sha256": hashlib.sha256(
                    f"sequence_{label}".encode("ascii")
                ).hexdigest(),
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


def test_fixed_9ecn_chain_retains_claim_free_depth_three_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _prepared_9ecn(tmp_path / "prepared")
    phenix_manifest = tmp_path / "phenix.json"
    phenix_manifest.write_text("{}\n", encoding="ascii")

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
        coordinate.write_text("REMARK ENSEMBLE parent\n", encoding="ascii")
        digest = hashlib.sha256(coordinate.read_bytes()).hexdigest()
        result = output / "normalised_mr_result.json"
        result.write_text(
            json.dumps(
                {
                    "execution_status": "completed_hit",
                    "placed_copy_count": 2,
                    "llg": 100.0,
                    "solution_coordinate_path": coordinate.name,
                    "solution_coordinate_sha256": digest,
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
        return SimpleNamespace(
            result=SimpleNamespace(
                execution_status=ExecutionStatus.COMPLETED_HIT,
                combined_solution_id="solution_AB",
                combined_llg=250.0,
                search_id="search_B",
                tool_version="Phaser test",
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
        output = output_directory
        output.mkdir(parents=True)
        (output / "component_search_result.json").write_text("{}\n", encoding="ascii")
        (output / "phaser_command.json").write_text("{}\n", encoding="ascii")
        return SimpleNamespace(
            execution_status=ExecutionStatus.COMPLETED_HIT,
            search_id="search_C",
            tool_version="Phaser test",
            top_solution_packed=True,
            fixed_components_observed=True,
            candidate_placement_observed=True,
            scientific_status="search_evidence_only",
            candidate_tfz=12.0,
            incremental_llg=150.0,
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
            output_directory=tmp_path / "output",
            progress=False,
        )
    )

    report = json.loads(result.report.read_text(encoding="utf-8"))
    assert report["gate_passed"] is True
    assert report["component_copy_counts"] == {"A": 2, "B": 2, "C": 2}
    assert report["generic_scientific_status"] == "search_evidence_only"
    assert report["exact_identity_claimed_by_search"] is False
    assert report["complete_composition_claimed_by_search"] is False
    checksum_rows = [
        line.split(maxsplit=1) for line in result.checksums.read_text().splitlines()
    ]
    assert len(checksum_rows) >= 15
    for digest, relative in checksum_rows:
        assert (
            hashlib.sha256((result.report.parent / relative).read_bytes()).hexdigest()
            == digest
        )
