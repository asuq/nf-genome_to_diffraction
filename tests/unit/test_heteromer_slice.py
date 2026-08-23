"""Focused tests for the fixed P6 heteromer control slice."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from genome_to_diffraction.benchmarks import (
    HeteromerSliceAssessmentRequest,
    HeteromerSlicePreparationRequest,
    assess_heteromer_control_slice,
    prepare_heteromer_control_slice,
)
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.cli import main
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.results import (
    CompositionAssessment,
    MrHypothesis,
    NormalisedMrResult,
    PartnerAttemptSummary,
    PartnerCandidateRanking,
    PartnerSearchPlan,
    PartnerSearchResult,
    ProcessedModelRecord,
    SequenceGroupRecord,
)

REPOSITORY = Path(__file__).resolve().parents[2]
MISSING_CANDIDATE_COUNT = 1845
AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"
CONTROL_METADATA = {
    "6RTZ": {
        "control_key": "A01",
        "adapter_version": "6rtz-fixed-a-one-b-inputs-v1",
        "composition": {"A": 1, "B": 1},
        "source": {
            "coordinates_sha256": (
                "af2f388b5dee3bb5ad9046c7950ff134f509f9143733b66103ac8169146dfba2"
            ),
            "structure_factors_sha256": (
                "474930b7efa0a9024d12d4efd1f74da0de979dd334b9f097a97086e453eb2d7d"
            ),
        },
        "protein_ids": ("WP_004080486.1", "WP_004080484.1"),
        "catalogue_sha256": (
            "c194a0417837fabca3ac1762889ba85d734aa929a0072585298dbc7bdcaa3a50",
            "259f42c3e05e57e373d144c10a31d137368f61964f7e9b9c0b96fc25a7b5439f",
        ),
    },
    "3U7Q": {
        "control_key": "A03",
        "adapter_version": "3u7q-fixed-two-a-two-b-inputs-v1",
        "composition": {"A": 2, "B": 2},
        "source": {
            "coordinates_sha256": (
                "4021acb1765da9070528f0013f09d598d962c025d6d0b96ec8aa62143ea8bfb2"
            ),
            "structure_factors_sha256": (
                "b25518663a98bbe7491c9a899def648c952ab63c8b6ef491b19410f7b23ecc5c"
            ),
        },
        "protein_ids": ("WP_012698832.1", "WP_012698833.1"),
        "catalogue_sha256": (
            "672912f544981102c24919f58c516f16bb5041af15d5d933a9be9618dd57939b",
            "90d14f01041688fc46b92288b9762c0ede104bcf2ea9d941449a64cff1ac80df",
        ),
    },
}


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


def _catalogue_sequence_groups(
    path: Path,
    *,
    parent: SequenceGroupRecord,
    partner: SequenceGroupRecord,
) -> Path:
    groups = [parent, partner]
    observed = {parent.sequence_group_id, partner.sequence_group_id}
    index = 0
    while len(groups) < 1846:
        value = index
        encoded: list[str] = []
        for _ in range(5):
            encoded.append(AMINO_ACIDS[value % len(AMINO_ACIDS)])
            value //= len(AMINO_ACIDS)
        candidate = _group("M" + "".join(reversed(encoded)) + "A" * 25)
        if candidate.sequence_group_id not in observed:
            groups.append(candidate)
            observed.add(candidate.sequence_group_id)
        index += 1
    path.write_text(
        "".join(f"{group.model_dump_json()}\n" for group in groups),
        encoding="utf-8",
    )
    return path


def _preparation(
    root: Path,
    *,
    crystal_id: str,
    parent: SequenceGroupRecord,
    partner: SequenceGroupRecord,
) -> Path:
    metadata = CONTROL_METADATA[crystal_id]
    composition = metadata["composition"]
    assert isinstance(composition, dict)
    root.mkdir()
    models = root / "models"
    models.mkdir()
    derived = root / "derived"
    derived.mkdir()
    groups = root / "sequence_groups.jsonl"
    groups.write_text(
        f"{parent.model_dump_json()}\n{partner.model_dump_json()}\n",
        encoding="utf-8",
    )
    parent_model = models / "component_A.pdb"
    partner_model = models / "component_B.pdb"
    parent_model.write_text(f"REMARK {crystal_id} parent\nATOM\n", encoding="ascii")
    partner_model.write_text(f"REMARK {crystal_id} partner\nATOM\n", encoding="ascii")
    mtz = derived / f"{crystal_id}.mtz"
    mtz.write_bytes(f"synthetic {crystal_id} MTZ".encode("ascii"))
    mapping_id = "coordmap_" + "1" * 64
    coordinate_id = "coord_" + "2" * 64
    model_id = "model_" + hashlib.sha256(crystal_id.encode()).hexdigest()
    model = ProcessedModelRecord(
        schema_version="1.0",
        model_id=model_id,
        coordinate_id=coordinate_id,
        variant_type="experimental_cleaned_source_chain",
        residue_ranges=("A:polymer",),
        processing_tool="gemmi",
        processing_version="synthetic",
        processing_parameters={
            "adapter_version": metadata["adapter_version"],
            "mapping_id": mapping_id,
            "sequence_identity": 1.0,
            "source_pdb_id": crystal_id,
            "source_chain": "A",
        },
        model_mass_da=20000.0,
        full_candidate_sequence_group_id=parent.sequence_group_id,
        model_sha256=sha256_file(parent_model),
    )
    processed_models = root / "processed_models.jsonl"
    processed_models.write_text(f"{model.model_dump_json()}\n", encoding="utf-8")
    model_manifest = root / "model_preparation_manifest.json"
    atomic_write_json(
        model_manifest,
        {
            "schema_version": "1.0",
            "adapter_version": metadata["adapter_version"],
            "entries": [
                {
                    "model_id": model.model_id,
                    "model_path": "models/component_A.pdb",
                    "model_sha256": model.model_sha256,
                    "mapping_id": mapping_id,
                }
            ],
        },
    )
    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id="mrhyp_" + hashlib.sha256(f"{crystal_id}-A".encode()).hexdigest(),
        crystal_id=crystal_id,
        sequence_group_id=parent.sequence_group_id,
        model_id=model.model_id,
        copy_count_expected=composition["A"],
        copy_number_to_search=composition["A"],
        fixed_solution_id=None,
        space_group="P 1",
        obs_labels="F,SIGF",
        search_stage="first_copy",
        resource_profile="pilot",
        priority_features={},
        status="queued",
    )
    hypotheses = root / "mr_hypotheses.jsonl"
    hypotheses.write_text(f"{hypothesis.model_dump_json()}\n", encoding="utf-8")
    crystal_manifest = root / "crystals.json"
    atomic_write_json(crystal_manifest, {"schema_version": "1.0", "crystals": []})
    files = {
        "crystal_manifest": crystal_manifest,
        "sequence_groups": groups,
        "processed_models": processed_models,
        "model_preparation_manifest": model_manifest,
        "hypotheses": hypotheses,
        "mtz": mtz,
        "parent_model": parent_model,
        "partner_model": partner_model,
    }
    source = metadata["source"]
    protein_ids = metadata["protein_ids"]
    catalogue_sha256 = metadata["catalogue_sha256"]
    assert isinstance(source, dict)
    assert isinstance(protein_ids, tuple)
    assert isinstance(catalogue_sha256, tuple)
    preparation_id = content_id(
        "heteromerprep_",
        {
            "adapter_version": metadata["adapter_version"],
            "source_coordinates_sha256": source["coordinates_sha256"],
            "source_structure_factors_sha256": source["structure_factors_sha256"],
            "files": {role: sha256_file(path) for role, path in files.items()},
        },
    )
    manifest = root / "preparation_manifest.json"
    atomic_write_json(
        manifest,
        {
            "schema_version": "1.0",
            "adapter_version": metadata["adapter_version"],
            "preparation_id": preparation_id,
            "control_key": metadata["control_key"],
            "crystal_id": crystal_id,
            "composition": composition,
            "parent_sequence_group_id": parent.sequence_group_id,
            "partner_sequence_group_id": partner.sequence_group_id,
            "parent_hypothesis_id": hypothesis.hypothesis_id,
            "partner_model_identity_fraction": 1.0,
            "sequence_relationships": [
                {
                    "entity_id": entity_id,
                    "source_construct_sequence_sha256": group.sha256,
                    "catalogue_protein_id": protein_ids[entity_id - 1],
                    "catalogue_sequence_sha256": catalogue_sha256[entity_id - 1],
                    "exact_catalogue_sequence": (
                        group.sha256 == catalogue_sha256[entity_id - 1]
                    ),
                }
                for entity_id, group in enumerate((parent, partner), start=1)
            ],
            "source": source,
            "files": {
                role: {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
                for role, path in files.items()
            },
        },
    )
    return manifest


def _prepare(tmp_path: Path) -> tuple[Path, dict[str, Any], Path]:
    hisf = _group("M" + "A" * 30)
    hish = _group("M" + "B" * 30)
    nifd = _group("M" + "C" * 30)
    nifk = _group("M" + "D" * 30)
    prep6 = _preparation(tmp_path / "six", crystal_id="6RTZ", parent=hisf, partner=hish)
    prep3 = _preparation(
        tmp_path / "three", crystal_id="3U7Q", parent=nifd, partner=nifk
    )
    catalogue = _catalogue_sequence_groups(
        tmp_path / "catalogue-sequence-groups.jsonl",
        parent=hisf,
        partner=hish,
    )
    result = prepare_heteromer_control_slice(
        HeteromerSlicePreparationRequest(
            protocol=REPOSITORY / "benchmarks/m6/protocol.yaml",
            control_6rtz_preparation=prep6,
            control_3u7q_preparation=prep3,
            catalogue_sequence_groups=catalogue,
            output_directory=tmp_path / "p6",
        )
    )
    document = json.loads(result.preparation_manifest.read_text())
    return result.preparation_manifest, document, catalogue


def _partner_result(
    *,
    crystal_id: str,
    parent_id: str,
    partner_id: str,
    copies: int,
    partner_model_sha256: str,
    mtz_sha256: str,
    hit: bool,
    parent_llg: float = 1000.0,
    parent_coordinate_sha256: str = "e" * 64,
) -> PartnerSearchResult:
    return PartnerSearchResult.model_validate(
        {
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
            "parent_llg": parent_llg,
            "combined_llg": parent_llg + 200.0 if hit else None,
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
            "parent_coordinate_sha256": parent_coordinate_sha256,
            "partner_model_sha256": partner_model_sha256,
            "mtz_sha256": mtz_sha256,
            "raw_log_pointer": "PHASER.log",
            "command_pointer": "phaser_command.json",
            "parameters_pointer": "partner_search.eff",
            "rejection_reason": None if hit else "no_partner_solution",
        }
    )


def _write(path: Path, model: BaseModel) -> Path:
    atomic_write_json(path, model.model_dump(mode="json"))
    return path


def _parent_result(
    *,
    hypothesis_id: str,
    copies: int,
    llg: float,
    coordinate_sha256: str,
) -> NormalisedMrResult:
    return NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=hypothesis_id,
        tool_version="synthetic",
        execution_status="completed_hit",
        llg=llg,
        tfz=12.0,
        placed_copy_count=copies,
        packing_summary={"top_solution_packed": True},
        solution_coordinate_path="PHASER.1.pdb",
        solution_coordinate_sha256=coordinate_sha256,
        raw_log_pointer="PHASER.log",
    )


def _missing_plan(
    *,
    parent_sequence_group_id: str,
    candidate_sequence_group_ids: list[str],
) -> PartnerSearchPlan:
    parent_state_sha256 = "1" * 64
    candidates = tuple(
        PartnerCandidateRanking(
            schema_version="1.0",
            candidate_id=content_id(
                "partnercand_",
                {
                    "adapter_version": "catalogue-partner-plan-v1",
                    "crystal_id": "6RTZ",
                    "parent_sequence_group_id": parent_sequence_group_id,
                    "parent_copy_count": 1,
                    "partner_sequence_group_id": sequence_group_id,
                    "partner_copy_count": 1,
                    "parent_state_sha256": parent_state_sha256,
                    "model_id": None,
                },
            ),
            rank=index,
            sequence_group_id=sequence_group_id,
            selection_status="unsearchable_no_model",
            sds_page_prior_label="unavailable",
            ordering_reasons=("no_model",),
        )
        for index, sequence_group_id in enumerate(candidate_sequence_group_ids, start=1)
    )
    candidate_count = len(candidates)
    return PartnerSearchPlan(
        schema_version="1.0",
        plan_id="partnerplan_" + "4" * 64,
        adapter_version="catalogue-partner-plan-v1",
        crystal_id="6RTZ",
        parent_sequence_group_id=parent_sequence_group_id,
        parent_state_sha256=parent_state_sha256,
        parent_copy_count=1,
        partner_copy_count=1,
        candidate_count=candidate_count,
        searchable_candidate_count=0,
        selected_attempt_count=0,
        deferred_cap_count=0,
        unsearchable_candidate_count=candidate_count,
        candidates=candidates,
    )


def _assessment_request(
    tmp_path: Path,
    *,
    candidate_mutation: str | None = None,
    wrong_parent_llg: float = 1000.0,
    wrong_parent_sha256: str = "e" * 64,
    positive_3_parent_sha256: str = "7" * 64,
    mismatched_summary_sha256: bool = False,
) -> tuple[HeteromerSliceAssessmentRequest, dict[str, Any]]:
    preparation, document, catalogue = _prepare(tmp_path)
    controls = document["positive_controls"]
    control_6 = controls["6RTZ"]
    control_3 = controls["3U7Q"]
    positive_6 = _write(
        tmp_path / "positive6.json",
        _partner_result(
            crystal_id="6RTZ",
            parent_id=control_6["parent_sequence_group_id"],
            partner_id=control_6["partner_sequence_group_id"],
            copies=1,
            partner_model_sha256=control_6["partner_model_sha256"],
            mtz_sha256=control_6["mtz_sha256"],
            hit=True,
            parent_llg=1000.0,
            parent_coordinate_sha256="e" * 64,
        ),
    )
    positive_3 = _write(
        tmp_path / "positive3.json",
        _partner_result(
            crystal_id="3U7Q",
            parent_id=control_3["parent_sequence_group_id"],
            partner_id=control_3["partner_sequence_group_id"],
            copies=2,
            partner_model_sha256=control_3["partner_model_sha256"],
            mtz_sha256=control_3["mtz_sha256"],
            hit=True,
            parent_llg=2000.0,
            parent_coordinate_sha256="7" * 64,
        ),
    )
    catalogue_ids = {
        SequenceGroupRecord.model_validate_json(line).sequence_group_id
        for line in catalogue.read_text(encoding="utf-8").splitlines()
        if line
    }
    candidate_sequence_group_ids = sorted(
        catalogue_ids - {control_6["parent_sequence_group_id"]}
    )
    if candidate_mutation == "truncated_catalogue":
        candidate_sequence_group_ids.pop()
    elif candidate_mutation == "invented_1845":
        candidate_sequence_group_ids[-1] = "seq_" + "9" * 64
        candidate_sequence_group_ids.sort()
    missing_plan = _missing_plan(
        parent_sequence_group_id=control_6["parent_sequence_group_id"],
        candidate_sequence_group_ids=candidate_sequence_group_ids,
    )
    count = missing_plan.candidate_count
    missing_plan_path = _write(tmp_path / "missing-plan.json", missing_plan)
    missing_summary = PartnerAttemptSummary(
        schema_version="1.0",
        summary_id="partnersummary_" + "5" * 64,
        plan_id=missing_plan.plan_id,
        plan_sha256=(
            "9" * 64 if mismatched_summary_sha256 else sha256_file(missing_plan_path)
        ),
        candidate_count=count,
        selected_attempt_count=0,
        result_count=0,
        completed_hit_count=0,
        completed_no_hit_count=0,
        failed_tool_execution_count=0,
        failed_parse_count=0,
        deferred_cap_count=0,
        unsearchable_candidate_count=count,
        selected_candidate_ids=(),
        result_candidate_ids=(),
        result_search_ids=(),
    )
    wrong = _write(
        tmp_path / "wrong.json",
        _partner_result(
            crystal_id="6RTZ",
            parent_id=control_6["parent_sequence_group_id"],
            partner_id=document["wrong_partner"]["partner_sequence_group_id"],
            copies=1,
            partner_model_sha256=document["wrong_partner"]["partner_model_sha256"],
            mtz_sha256=control_6["mtz_sha256"],
            hit=True,
            parent_llg=wrong_parent_llg,
            parent_coordinate_sha256=wrong_parent_sha256,
        ),
    )
    homomer = _parent_result(
        hypothesis_id=document["homomer_non_regression"]["parent_hypothesis_id"],
        copies=1,
        llg=1000.0,
        coordinate_sha256="e" * 64,
    )
    positive_3_parent = _parent_result(
        hypothesis_id=control_3["parent_hypothesis_id"],
        copies=2,
        llg=2000.0,
        coordinate_sha256=positive_3_parent_sha256,
    )
    request = HeteromerSliceAssessmentRequest(
        preparation_manifest=preparation,
        catalogue_sequence_groups=catalogue,
        positive_6rtz_result=positive_6,
        positive_3u7q_result=positive_3,
        positive_3u7q_parent_result=_write(
            tmp_path / "positive3-parent.json", positive_3_parent
        ),
        missing_partner_plan=missing_plan_path,
        missing_partner_summary=_write(
            tmp_path / "missing-summary.json", missing_summary
        ),
        wrong_partner_result=wrong,
        homomer_result=_write(tmp_path / "homomer.json", homomer),
        output_json=tmp_path / "report.json",
    )
    return request, document


def test_p6_gate_binds_controls_and_keeps_wrong_hit_non_claiming(
    tmp_path: Path,
) -> None:
    request, preparation = _assessment_request(tmp_path)
    assessed = assess_heteromer_control_slice(request)

    assert assessed.gate_passed is True
    assert preparation["adapter_version"] == "heteromer-p6-control-slice-v2"
    assert preparation["missing_partner"]["expected_candidate_count"] == 1845
    assert set(preparation["source_preparations"]) == {"6RTZ", "3U7Q"}
    report = json.loads(assessed.report_json.read_text())
    assert report["cases"]["missing_B"]["candidate_count"] == 1845
    wrong = report["cases"]["wrong_B"]["assessment"]
    assert wrong["execution_status"] == "completed_hit"
    assert wrong["placement_observed"] is True
    assert wrong["scientific_status"] == "search_evidence_only"
    assert wrong["complete_composition_claim_eligible"] is False
    assert wrong["complete_composition_claimed"] is False
    unsupported = report["cases"]["9ECN_three_component_boundary"]
    assert unsupported["status"] == "unsupported_component_count"
    assert unsupported["retain_partial_a_b_evidence"] is True
    rows = [
        CompositionAssessment.model_validate_json(line)
        for line in assessed.composition_assessments_jsonl.read_text().splitlines()
    ]
    assert len(rows) == 6
    assert report["composition_assessments"]["record_count"] == 6

    invalid_wrong = wrong | {"complete_composition_claim_eligible": True}
    with pytest.raises(ValidationError, match="claim eligibility"):
        CompositionAssessment.model_validate(invalid_wrong)


def test_p6_gate_rejects_swapped_positive_results(tmp_path: Path) -> None:
    request, _ = _assessment_request(tmp_path)
    swapped = HeteromerSliceAssessmentRequest(
        **{
            **request.__dict__,
            "positive_6rtz_result": request.positive_3u7q_result,
            "positive_3u7q_result": request.positive_6rtz_result,
        }
    )
    assessed = assess_heteromer_control_slice(swapped)
    assert assessed.gate_passed is False
    report = json.loads(assessed.report_json.read_text())
    assert report["cases"]["6RTZ_positive_1A_1B"]["gate_passed"] is False
    assert report["cases"]["3U7Q_positive_2A_2B"]["gate_passed"] is False


def test_p6_gate_rejects_swapped_positive_parent_results(tmp_path: Path) -> None:
    request, _ = _assessment_request(tmp_path)
    swapped = HeteromerSliceAssessmentRequest(
        **{
            **request.__dict__,
            "homomer_result": request.positive_3u7q_parent_result,
            "positive_3u7q_parent_result": request.homomer_result,
        }
    )
    assessed = assess_heteromer_control_slice(swapped)
    report = json.loads(assessed.report_json.read_text())
    assert assessed.gate_passed is False
    assert report["cases"]["6RTZ_positive_1A_1B"]["gate_passed"] is False
    assert report["cases"]["3U7Q_positive_2A_2B"]["gate_passed"] is False
    assert report["cases"]["homomer_non_regression"]["gate_passed"] is False


def test_p6_gate_rejects_positive_parent_coordinate_mutation(tmp_path: Path) -> None:
    request, _ = _assessment_request(
        tmp_path,
        positive_3_parent_sha256="8" * 64,
    )
    assessed = assess_heteromer_control_slice(request)
    report = json.loads(assessed.report_json.read_text())
    assert assessed.gate_passed is False
    assert report["cases"]["3U7Q_positive_2A_2B"]["gate_passed"] is False


@pytest.mark.parametrize(
    ("wrong_parent_llg", "wrong_parent_sha256"),
    [(1001.0, "e" * 64), (1000.0, "8" * 64)],
)
def test_p6_gate_rejects_wrong_b_parent_evidence_mutation(
    tmp_path: Path,
    wrong_parent_llg: float,
    wrong_parent_sha256: str,
) -> None:
    request, _ = _assessment_request(
        tmp_path,
        wrong_parent_llg=wrong_parent_llg,
        wrong_parent_sha256=wrong_parent_sha256,
    )
    assessed = assess_heteromer_control_slice(request)
    report = json.loads(assessed.report_json.read_text())
    assert assessed.gate_passed is False
    assert report["cases"]["wrong_B"]["gate_passed"] is False
    assert report["cases"]["wrong_B"]["complete_composition_claim_eligible"] is False


@pytest.mark.parametrize(
    "assessment_option",
    ["truncated_catalogue", "invented_1845", "mismatched_summary_sha256"],
)
def test_p6_gate_rejects_incomplete_or_unbound_missing_b_inventory(
    tmp_path: Path,
    assessment_option: str,
) -> None:
    request, _ = _assessment_request(
        tmp_path,
        candidate_mutation=(
            assessment_option
            if assessment_option in {"truncated_catalogue", "invented_1845"}
            else None
        ),
        mismatched_summary_sha256=(assessment_option == "mismatched_summary_sha256"),
    )
    assessed = assess_heteromer_control_slice(request)
    report = json.loads(assessed.report_json.read_text())
    assert assessed.gate_passed is False
    assert report["cases"]["missing_B"]["gate_passed"] is False


def test_p6_preparation_rejects_mutated_source_model(tmp_path: Path) -> None:
    hisf = _group("M" + "A" * 30)
    hish = _group("M" + "B" * 30)
    nifd = _group("M" + "C" * 30)
    nifk = _group("M" + "D" * 30)
    prep6 = _preparation(tmp_path / "six", crystal_id="6RTZ", parent=hisf, partner=hish)
    prep3 = _preparation(
        tmp_path / "three", crystal_id="3U7Q", parent=nifd, partner=nifk
    )
    catalogue = _catalogue_sequence_groups(
        tmp_path / "catalogue-sequence-groups.jsonl",
        parent=hisf,
        partner=hish,
    )
    (prep3.parent / "models/component_B.pdb").write_text(
        "mutated wrong model\n", encoding="ascii"
    )
    with pytest.raises(ValueError, match="checksum differs"):
        prepare_heteromer_control_slice(
            HeteromerSlicePreparationRequest(
                protocol=REPOSITORY / "benchmarks/m6/protocol.yaml",
                control_6rtz_preparation=prep6,
                control_3u7q_preparation=prep3,
                catalogue_sequence_groups=catalogue,
                output_directory=tmp_path / "p6",
            )
        )


def test_p6_cli_surfaces_are_fixed(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["benchmark", "prepare-heteromer-control-slice", "--help"])
    assert "--catalogue-sequence-groups" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="0"):
        main(["benchmark", "assess-heteromer-control-slice", "--help"])
    assessment_help = capsys.readouterr().out
    assert "--catalogue-sequence-groups" in assessment_help
    assert "--positive-3u7q-parent-result" in assessment_help
