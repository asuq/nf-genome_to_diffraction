"""Focused tests for the fixed P6 heteromer control slice."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from genome_to_diffraction.benchmarks import (
    HeteromerSliceAssessmentRequest,
    HeteromerSlicePreparationRequest,
    assess_heteromer_control_slice,
    prepare_heteromer_control_slice,
)
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.cli import main
from genome_to_diffraction.schemas.results import (
    NormalisedMrResult,
    PartnerAttemptSummary,
    PartnerSearchPlan,
    PartnerSearchResult,
    SequenceGroupRecord,
)

REPOSITORY = Path(__file__).resolve().parents[2]


def _group(sequence: str) -> SequenceGroupRecord:
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=20000.0,
        mass_method="synthetic P6 control",
        residue_policy="standard_exact",
        source_record_count=1,
    )


def _preparation(
    root: Path,
    *,
    crystal_id: str,
    parent: SequenceGroupRecord,
    partner: SequenceGroupRecord,
) -> Path:
    root.mkdir()
    groups = root / "sequence_groups.jsonl"
    groups.write_text(
        f"{parent.model_dump_json()}\n{partner.model_dump_json()}\n",
        encoding="utf-8",
    )
    parent_model = root / "parent.pdb"
    partner_model = root / "partner.pdb"
    parent_model.write_text("REMARK parent\nATOM\n", encoding="ascii")
    partner_model.write_text("REMARK partner\nATOM\n", encoding="ascii")
    files = {
        "sequence_groups": groups,
        "parent_model": parent_model,
        "partner_model": partner_model,
    }
    manifest = root / "preparation_manifest.json"
    atomic_write_json(
        manifest,
        {
            "schema_version": "1.0",
            "crystal_id": crystal_id,
            "parent_sequence_group_id": parent.sequence_group_id,
            "partner_sequence_group_id": partner.sequence_group_id,
            "partner_model_identity_fraction": 1.0,
            "files": {
                role: {
                    "path": path.name,
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
                for role, path in files.items()
            },
        },
    )
    return manifest


def _prepare(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    hisf = _group("M" + "A" * 30)
    hish = _group("M" + "B" * 30)
    nifd = _group("M" + "C" * 30)
    nifk = _group("M" + "D" * 30)
    prep6 = _preparation(tmp_path / "six", crystal_id="6RTZ", parent=hisf, partner=hish)
    prep3 = _preparation(
        tmp_path / "three", crystal_id="3U7Q", parent=nifd, partner=nifk
    )
    result = prepare_heteromer_control_slice(
        HeteromerSlicePreparationRequest(
            protocol=REPOSITORY / "benchmarks/m6/protocol.yaml",
            control_6rtz_preparation=prep6,
            control_3u7q_preparation=prep3,
            output_directory=tmp_path / "p6",
        )
    )
    document = json.loads(result.preparation_manifest.read_text())
    return result.preparation_manifest, document


def _partner_result(
    *,
    crystal_id: str,
    parent_id: str,
    partner_id: str,
    copies: int,
    hit: bool,
) -> PartnerSearchResult:
    common = {
        "schema_version": "1.0",
        "search_id": "partner_" + hashlib.sha256(crystal_id.encode()).hexdigest(),
        "crystal_id": crystal_id,
        "tool_version": "synthetic",
        "parent_solution_id": "sol_" + "a" * 64,
        "parent_sequence_group_id": parent_id,
        "parent_copy_count": copies,
        "partner_sequence_group_id": partner_id,
        "requested_partner_copy_count": copies,
        "execution_status": "completed_hit" if hit else "completed_no_hit",
        "parent_llg": 1000.0,
        "combined_llg": 1200.0 if hit else None,
        "incremental_llg": 200.0 if hit else None,
        "partner_tfz": 12.0 if hit else None,
        "solution_count": 1 if hit else 0,
        "top_solution_packed": hit,
        "fixed_parent_placement_observed": hit,
        "partner_placement_count": copies if hit else 0,
        "partner_placement_observed": hit,
        "score_cohort": "primary" if hit else None,
        "combined_solution_id": "composition_" + "b" * 64 if hit else None,
        "combined_coordinate_path": "PHASER.1.pdb" if hit else None,
        "combined_coordinate_sha256": "c" * 64 if hit else None,
        "output_mtz_path": "PHASER.1.mtz" if hit else None,
        "output_mtz_sha256": "d" * 64 if hit else None,
        "parent_coordinate_sha256": "e" * 64,
        "partner_model_sha256": "f" * 64,
        "mtz_sha256": "0" * 64,
        "raw_log_pointer": "PHASER.log",
        "command_pointer": "phaser_command.json",
        "parameters_pointer": "partner_search.eff",
        "rejection_reason": None if hit else "no_partner_solution",
    }
    return PartnerSearchResult.model_validate(common)


def _write(path: Path, model: BaseModel) -> Path:
    atomic_write_json(path, model.model_dump(mode="json"))
    return path


def test_p6_preparation_and_assessment_keep_negative_controls_non_claiming(
    tmp_path: Path,
) -> None:
    preparation, document = _prepare(tmp_path)
    wrong_definition = document["wrong_partner"]
    assert isinstance(wrong_definition, dict)
    parent_id = wrong_definition["parent_sequence_group_id"]
    wrong_id = wrong_definition["partner_sequence_group_id"]
    assert isinstance(parent_id, str)
    assert isinstance(wrong_id, str)
    positive_6 = _write(
        tmp_path / "positive6.json",
        _partner_result(
            crystal_id="6RTZ",
            parent_id=parent_id,
            partner_id="seq_" + "1" * 64,
            copies=1,
            hit=True,
        ),
    )
    positive_3 = _write(
        tmp_path / "positive3.json",
        _partner_result(
            crystal_id="3U7Q",
            parent_id="seq_" + "2" * 64,
            partner_id="seq_" + "3" * 64,
            copies=2,
            hit=True,
        ),
    )
    missing_plan = PartnerSearchPlan(
        schema_version="1.0",
        plan_id="partnerplan_" + "4" * 64,
        adapter_version="test",
        crystal_id="6RTZ",
        parent_sequence_group_id=parent_id,
        parent_copy_count=1,
        partner_copy_count=1,
        candidate_count=0,
        searchable_candidate_count=0,
        selected_attempt_count=0,
        deferred_cap_count=0,
        unsearchable_candidate_count=0,
        candidates=(),
    )
    missing_plan_path = _write(tmp_path / "missing-plan.json", missing_plan)
    missing_summary = PartnerAttemptSummary(
        schema_version="1.0",
        summary_id="partnersummary_" + "5" * 64,
        plan_id=missing_plan.plan_id,
        plan_sha256=sha256_file(missing_plan_path),
        candidate_count=0,
        selected_attempt_count=0,
        result_count=0,
        completed_hit_count=0,
        completed_no_hit_count=0,
        failed_tool_execution_count=0,
        failed_parse_count=0,
        deferred_cap_count=0,
        unsearchable_candidate_count=0,
        selected_candidate_ids=(),
        result_candidate_ids=(),
        result_search_ids=(),
    )
    wrong = _write(
        tmp_path / "wrong.json",
        _partner_result(
            crystal_id="6RTZ",
            parent_id=parent_id,
            partner_id=wrong_id,
            copies=1,
            hit=False,
        ),
    )
    homomer = NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id="mrhyp_" + "6" * 64,
        tool_version="synthetic",
        execution_status="completed_hit",
        llg=100.0,
        tfz=12.0,
        placed_copy_count=1,
        packing_summary={"top_solution_packed": True},
        raw_log_pointer="PHASER.log",
    )
    assessed = assess_heteromer_control_slice(
        HeteromerSliceAssessmentRequest(
            preparation_manifest=preparation,
            positive_6rtz_result=positive_6,
            positive_3u7q_result=positive_3,
            missing_partner_plan=missing_plan_path,
            missing_partner_summary=_write(
                tmp_path / "missing-summary.json", missing_summary
            ),
            wrong_partner_result=wrong,
            homomer_result=_write(tmp_path / "homomer.json", homomer),
            output_json=tmp_path / "report.json",
        )
    )

    assert assessed.gate_passed is True
    report = json.loads(assessed.report_json.read_text())
    assert report["cases"]["missing_B"]["complete_composition_claimed"] is False
    assert report["cases"]["wrong_B"]["complete_composition_claimed"] is False
    unsupported = report["cases"]["9ECN_three_component_boundary"]
    assert unsupported["status"] == "unsupported_component_count"
    assert unsupported["retain_partial_a_b_evidence"] is True


def test_p6_cli_surfaces_are_fixed() -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["benchmark", "prepare-heteromer-control-slice", "--help"])
    with pytest.raises(SystemExit, match="0"):
        main(["benchmark", "assess-heteromer-control-slice", "--help"])
