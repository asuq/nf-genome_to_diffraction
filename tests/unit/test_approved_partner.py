"""Tests for the approved component-seed to partner-search bridge."""

import json
from pathlib import Path
from typing import cast

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.mr.approved_partner import (
    ApprovedPartnerSearchRequest,
    run_approved_partner_search,
)
from genome_to_diffraction.mr.partner import PartnerSearchOutput, PartnerSearchRequest
from genome_to_diffraction.mr.phaser import PhaserInputError
from genome_to_diffraction.schemas.results import NormalisedMrResult
from genome_to_diffraction.status import ExecutionStatus


def _request(tmp_path: Path) -> ApprovedPartnerSearchRequest:
    solution_id = "sol_" + "a" * 64
    parent_group = "seq_" + "b" * 64
    partner_group = "seq_" + "c" * 64
    review = tmp_path / "review"
    assets = review / "assets" / solution_id
    assets.mkdir(parents=True)
    coordinate = assets / "solution.pdb"
    coordinate.write_text("REMARK parent\nATOM\n", encoding="ascii")
    result = NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id="mrhyp_" + "d" * 64,
        tool_version="Phenix 2.1-6048; Phaser 2.8.4",
        execution_status=ExecutionStatus.COMPLETED_HIT,
        llg=321.5,
        tfz=18.0,
        placed_copy_count=1,
        packing_summary={"top_solution_packed": True},
        solution_coordinate_path="PHASER.1.pdb",
        solution_coordinate_sha256=sha256_file(coordinate),
        output_mtz_path="PHASER.1.mtz",
        output_mtz_sha256="e" * 64,
        raw_log_pointer="PHASER.log",
    )
    result_path = assets / "normalised_mr_result.jsonl"
    result_path.write_text(f"{canonical_json_text(result)}\n", encoding="utf-8")
    review_manifest = review / "mr_seed_review_manifest.json"
    review_manifest.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "solution_id": solution_id,
                        "sequence_group_id": parent_group,
                        "copied_assets": {
                            "solution_coordinate": (
                                f"assets/{solution_id}/solution.pdb"
                            ),
                            "normalised_result": (
                                f"assets/{solution_id}/normalised_mr_result.jsonl"
                            ),
                        },
                        "copied_asset_sha256": {
                            "solution_coordinate": sha256_file(coordinate),
                            "normalised_result": sha256_file(result_path),
                        },
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    stage = tmp_path / "approved-stage"
    models = stage / "models"
    models.mkdir(parents=True)
    staged_parent = models / "parent.pdb"
    staged_parent.write_bytes(coordinate.read_bytes())
    approved = stage / "approved_seeds.tsv"
    approved.write_text(
        "seed_solution_id\tsearch_model\tsearch_model_sha256\t"
        "expected_copy_count\trequires_additional_copy\n"
        f"{solution_id}\t{staged_parent.resolve()}\t{sha256_file(staged_parent)}\t"
        "1\tfalse\n",
        encoding="utf-8",
    )
    validation = stage / "validated_mr_seed_decisions.json"
    validation.write_text('{"execution_status":"completed_success"}\n')
    (stage / "live_m4_stage_manifest.json").write_text(
        json.dumps(
            {
                "execution_status": "completed_success",
                "approved_seed_count": 1,
                "approved_seeds_sha256": sha256_file(approved),
                "validation_sha256": sha256_file(validation),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    control = tmp_path / "control"
    control_models = control / "models"
    control_models.mkdir(parents=True)
    partner_model = control_models / "component_B.pdb"
    partner_model.write_text("ATOM\n", encoding="ascii")
    preparation = control / "preparation_manifest.json"
    preparation.write_text(
        json.dumps(
            {
                "adapter_version": "6rtz-fixed-a-one-b-inputs-v1",
                "crystal_id": "6RTZ",
                "composition": {"A": 1, "B": 1},
                "parent_sequence_group_id": parent_group,
                "partner_sequence_group_id": partner_group,
                "partner_model_identity_fraction": 1.0,
                "files": {
                    "partner_model": {
                        "path": "models/component_B.pdb",
                        "sha256": sha256_file(partner_model),
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for name in ("sequence_groups.jsonl", "preflight.jsonl", "data.mtz", "phenix.json"):
        (tmp_path / name).write_text("placeholder\n", encoding="ascii")
    return ApprovedPartnerSearchRequest(
        approved_stage=stage,
        review_package=review,
        control_preparation_manifest=preparation,
        sequence_groups_jsonl=tmp_path / "sequence_groups.jsonl",
        preflight_jsonl=tmp_path / "preflight.jsonl",
        mtz=tmp_path / "data.mtz",
        phenix_manifest=tmp_path / "phenix.json",
        output_directory=tmp_path / "output",
        threads=8,
        progress=False,
    )


def test_approved_seed_binds_parent_llg_and_fixed_partner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    captured: list[PartnerSearchRequest] = []
    sentinel = cast(PartnerSearchOutput, object())

    def fake_run(partner_request: PartnerSearchRequest) -> PartnerSearchOutput:
        captured.append(partner_request)
        return sentinel

    monkeypatch.setattr(
        "genome_to_diffraction.mr.approved_partner.run_partner_search", fake_run
    )

    output = run_approved_partner_search(request)

    assert output is sentinel
    assert len(captured) == 1
    partner_request = captured[0]
    assert partner_request.crystal_id == "6RTZ"
    assert partner_request.parent_llg == 321.5
    assert partner_request.parent_sequence_group_id == "seq_" + "b" * 64
    assert partner_request.partner_sequence_group_id == "seq_" + "c" * 64
    assert partner_request.partner_model.name == "component_B.pdb"
    assert partner_request.threads == 8


def test_bridge_rejects_changed_review_result(tmp_path: Path) -> None:
    request = _request(tmp_path)
    manifest = json.loads(
        (request.review_package / "mr_seed_review_manifest.json").read_text()
    )
    relative = manifest["items"][0]["copied_assets"]["normalised_result"]
    (request.review_package / relative).write_text("{}\n", encoding="utf-8")

    with pytest.raises(PhaserInputError, match="result checksum differs"):
        run_approved_partner_search(request)
