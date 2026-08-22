"""Tests for deterministic capped catalogue B selection."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.cli import main
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.ranking import (
    ApprovedPartnerPlanRequest,
    PartnerPlanInputError,
    PartnerPlanRequest,
    build_approved_partner_search_plan,
    build_partner_search_plan,
)
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MtzPreflightRecord,
    ProcessedModelRecord,
    SequenceGroupRecord,
)

REPOSITORY = Path(__file__).resolve().parents[2]


def _group(sequence: str, mass_da: float) -> SequenceGroupRecord:
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=mass_da,
        mass_method="synthetic partner-plan test",
        residue_policy="standard_exact",
        source_record_count=1,
    )


def _matthews(
    group: SequenceGroupRecord,
    *,
    label: str,
    index: int,
) -> MatthewsHypothesis:
    mass = group.molecular_mass_da
    assert mass is not None
    coefficient = 250000.0 / mass
    solvent = 1.0 - 1.23 / coefficient
    return MatthewsHypothesis.model_validate(
        {
            "schema_version": "1.0",
            "hypothesis_id": f"matthews_{index:064x}",
            "crystal_id": "test_crystal_01",
            "sequence_group_id": group.sequence_group_id,
            "copy_count": 1,
            "sequence_mass_da": mass,
            "total_mass_da": mass,
            "v_asu_a3": 250000.0,
            "matthews_coefficient": coefficient,
            "solvent_fraction": solvent,
            "matthews_prior": 0.5,
            "prior_backend": "synthetic",
            "rank_within_candidate": 1,
            "retained": True,
            "physical_status": "review",
            "sds_page_nearest_band_kda": 20.0 if label != "unavailable" else None,
            "sds_page_absolute_difference_kda": (
                0.5 if label != "unavailable" else None
            ),
            "sds_page_fractional_difference": (
                0.025 if label != "unavailable" else None
            ),
            "sds_page_prior_label": label,
        }
    )


def _request(
    tmp_path: Path,
) -> tuple[PartnerPlanRequest, dict[str, SequenceGroupRecord]]:
    parent = _group("M" + "G" * 30, 20000.0)
    partners = [
        _group("M" + "A" * index + "C" * (30 - index), 20000.0) for index in range(28)
    ]
    partners[-2] = partners[-2].model_copy(update={"molecular_mass_da": 300000.0})
    groups = (parent, *partners)
    sequence_groups = tmp_path / "sequence_groups.jsonl"
    sequence_groups.write_text(
        "".join(f"{canonical_json_text(group)}\n" for group in groups),
        encoding="utf-8",
    )
    labels = ["weak"] * len(partners)
    labels[10] = "strong"
    labels[11] = "compatible"
    labels[12] = "unavailable"
    matthews_rows = [
        _matthews(group, label=labels[index], index=index + 1)
        for index, group in enumerate(partners)
    ]
    matthews = tmp_path / "matthews.jsonl"
    matthews.write_text(
        "".join(f"{canonical_json_text(row)}\n" for row in matthews_rows),
        encoding="utf-8",
    )
    preflight = MtzPreflightRecord.model_validate_json(
        (REPOSITORY / "tests/fixtures/stubs/mtz_preflight.jsonl").read_text(
            encoding="utf-8"
        )
    )
    preflights = tmp_path / "preflight.jsonl"
    preflights.write_text(f"{canonical_json_text(preflight)}\n", encoding="utf-8")
    registry = tmp_path / "model_registry"
    model_root = registry / "models"
    model_root.mkdir(parents=True)
    models: list[ProcessedModelRecord] = []
    entries: list[dict[str, object]] = []
    for index, group in enumerate(partners[:-1]):
        model_path = model_root / f"model-{index:02d}.pdb"
        model_path.write_text(f"REMARK model {index}\nATOM\n", encoding="ascii")
        digest = sha256_file(model_path)
        model = ProcessedModelRecord(
            schema_version="1.0",
            model_id=f"model_{index:064x}",
            coordinate_id=f"coord_{index:064x}",
            variant_type=(
                "predicted_confidence_pruned_full"
                if index % 2 == 0
                else "experimental_cleaned_source_chain"
            ),
            residue_ranges=("A:1-30",),
            processing_tool="synthetic",
            processing_version="1",
            processing_parameters={"sequence_identity": 0.9},
            estimated_coordinate_error=1.0,
            model_mass_da=18000.0,
            full_candidate_sequence_group_id=group.sequence_group_id,
            model_sha256=digest,
        )
        models.append(model)
        entries.append(
            {
                "model_id": model.model_id,
                "model_path": model_path.relative_to(registry).as_posix(),
                "model_sha256": digest,
                "retained_fraction": 0.9,
            }
        )
    (registry / "processed_models.jsonl").write_text(
        "".join(f"{canonical_json_text(model)}\n" for model in models),
        encoding="utf-8",
    )
    (registry / "model_preparation_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "processed_model_count": len(models),
                "entries": entries,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    request = PartnerPlanRequest(
        crystal_id="test_crystal_01",
        parent_sequence_group_id=parent.sequence_group_id,
        parent_copy_count=1,
        partner_copy_count=1,
        sequence_groups_jsonl=sequence_groups,
        matthews_hypotheses_jsonl=matthews,
        mtz_preflight_jsonl=preflights,
        pipeline_config=REPOSITORY / "examples/config.yaml",
        model_registry_directory=registry,
        output_directory=tmp_path / "partner_plan",
        progress=False,
    )
    return request, {
        "strong": partners[10],
        "compatible": partners[11],
        "unavailable": partners[12],
        "no_model": partners[-1],
        "impossible": partners[-2],
    }


def test_partner_plan_caps_first_wave_and_retains_every_reason(tmp_path: Path) -> None:
    request, named = _request(tmp_path)

    output = build_partner_search_plan(request)

    plan = output.plan
    assert plan.candidate_count == 28
    assert plan.searchable_candidate_count == 26
    assert plan.selected_attempt_count == 25
    assert plan.deferred_cap_count == 1
    assert plan.unsearchable_candidate_count == 2
    assert plan.candidates[0].sequence_group_id == named["strong"].sequence_group_id
    assert plan.candidates[1].sequence_group_id == named["compatible"].sequence_group_id
    unavailable = next(
        item
        for item in plan.candidates
        if item.sequence_group_id == named["unavailable"].sequence_group_id
    )
    first_weak_rank = min(
        item.rank
        for item in plan.candidates
        if item.sds_page_prior_label == "weak"
        and item.selection_status in {"selected", "deferred_cap"}
    )
    assert unavailable.native_page_prior_label == "unavailable"
    assert unavailable.rank < first_weak_rank
    no_model = next(
        item
        for item in plan.candidates
        if item.sequence_group_id == named["no_model"].sequence_group_id
    )
    impossible = next(
        item
        for item in plan.candidates
        if item.sequence_group_id == named["impossible"].sequence_group_id
    )
    assert no_model.selection_status == "unsearchable_no_model"
    assert impossible.selection_status == "excluded_physical_impossible"
    assert output.candidates_jsonl.read_text(encoding="utf-8").count("\n") == 28
    assert output.selected_candidate_ids.read_text(encoding="utf-8").count("\n") == 25

    repeated = build_partner_search_plan(
        replace(request, output_directory=tmp_path / "repeated")
    )
    assert output.plan_json.read_bytes() == repeated.plan_json.read_bytes()
    assert (
        output.candidates_jsonl.read_bytes() == repeated.candidates_jsonl.read_bytes()
    )
    assert (
        output.selected_candidate_ids.read_bytes()
        == repeated.selected_candidate_ids.read_bytes()
    )


def test_partner_plan_rejects_changed_model(tmp_path: Path) -> None:
    request, _ = _request(tmp_path)
    model = next((request.model_registry_directory / "models").glob("*.pdb"))
    model.write_text("changed\n", encoding="ascii")

    with pytest.raises(PartnerPlanInputError, match="checksum"):
        build_partner_search_plan(request)


def test_partner_plan_cli_keeps_the_cap_fixed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request, _ = _request(tmp_path)

    exit_status = main(
        [
            "--no-progress",
            "ranking",
            "partner-plan",
            "--crystal-id",
            request.crystal_id,
            "--parent-sequence-group-id",
            request.parent_sequence_group_id,
            "--parent-copy-count",
            str(request.parent_copy_count),
            "--partner-copy-count",
            str(request.partner_copy_count),
            "--sequence-groups",
            str(request.sequence_groups_jsonl),
            "--matthews",
            str(request.matthews_hypotheses_jsonl),
            "--preflight",
            str(request.mtz_preflight_jsonl),
            "--config",
            str(request.pipeline_config),
            "--model-registry",
            str(request.model_registry_directory),
            "--outdir",
            str(request.output_directory),
        ]
    )

    assert exit_status == 0
    assert "Selected 25 of 28 catalogue B candidate(s)" in capsys.readouterr().out


def test_approved_partner_plan_derives_parent_state(tmp_path: Path) -> None:
    request, _ = _request(tmp_path)
    stage = tmp_path / "approved-stage"
    stage.mkdir()
    stage_manifest = stage / "live_m4_stage_manifest.json"
    stage_manifest.write_text(
        json.dumps(
            {
                "execution_status": "completed_success",
                "approved_seed_count": 1,
                "approved_solution_ids": ["sol_test"],
                "model_sources": {
                    "sol_test": {
                        "sequence_group_id": request.parent_sequence_group_id,
                        "expected_copy_count": 1,
                        "requires_additional_copy": False,
                    }
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    output = build_approved_partner_search_plan(
        ApprovedPartnerPlanRequest(
            approved_stage=stage,
            crystal_id=request.crystal_id,
            partner_copy_count=1,
            sequence_groups_jsonl=request.sequence_groups_jsonl,
            matthews_hypotheses_jsonl=request.matthews_hypotheses_jsonl,
            mtz_preflight_jsonl=request.mtz_preflight_jsonl,
            pipeline_config=request.pipeline_config,
            model_registry_directory=request.model_registry_directory,
            output_directory=tmp_path / "approved-plan",
            progress=False,
        )
    )

    assert output.plan.parent_sequence_group_id == request.parent_sequence_group_id
    assert output.plan.parent_copy_count == 1
    assert output.plan.parent_state_sha256 == sha256_file(stage_manifest)
