"""Focused credible-pass-1 to executable A-state bridge test."""

from pathlib import Path

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.execution import Pass2SeedRequest, build_pass2_a_seed
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.model_registry import (
    build_all_eligible_model_registry,
    load_all_eligible_model_registry,
)
from genome_to_diffraction.schemas.manifests import PrototypeProfile
from genome_to_diffraction.schemas.results import (
    CopyCountAssessment,
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    NormalisedMrResult,
)
from genome_to_diffraction.schemas.v2 import (
    ComponentIdentitySupport,
    ExecutionArtifactIdentity,
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecisionValue,
    UnknownPass1CrystalAssessment,
    UnknownPass1ResidualContentState,
    UnknownPass1ReviewEvidence,
    UnknownPass1SolutionEvidence,
)
from genome_to_diffraction.status import ExecutionStatus
from tests.support.unknown_pass1_fixture import (
    materialise_unknown_pass1_public_fixture,
)
from tests.unit.test_all_eligible_model_registry import _two_group_inputs

CRYSTAL = "AD4QS1P4G2_18"


def _review(
    checkpoint: PhaseIIIReviewCheckpoint,
    item_id: str,
    decision: PhaseIIIReviewDecisionValue,
    index: int,
) -> UnknownPass1ReviewEvidence:
    return UnknownPass1ReviewEvidence(
        checkpoint=checkpoint,
        package_crystal_id=CRYSTAL,
        package_item_id=item_id,
        review_package_id=f"phase3reviewpkg_{index:064x}",
        review_package_manifest_sha256=f"{index + 10:064x}",
        decision_crystal_id=CRYSTAL,
        decision_item_id=item_id,
        decision_file_id=f"phase3review_{index + 20:064x}",
        decision_file_sha256=f"{index + 30:064x}",
        decision=decision,
    )


def test_credible_pass1_builds_claim_free_refined_a_parent(tmp_path: Path) -> None:
    inputs, groups = _two_group_inputs()
    registry_output = build_all_eligible_model_registry(
        models=(inputs[0],),
        sequence_groups=groups,
        output_directory=tmp_path / "registry",
    )
    registry = load_all_eligible_model_registry(registry_output.registry_json)
    group = groups[0]
    entry = next(
        item.models[0]
        for item in registry.manifest.sequence_groups
        if item.sequence_group_id == group.sequence_group_id
    )
    model = registry.root / entry.model_path
    source_mtz = tmp_path / "input.mtz"
    source_mtz.write_bytes(b"source diffraction\n")
    output_mtz = tmp_path / "PHASER.1.mtz"
    output_mtz.write_bytes(b"derived diffraction\n")
    combined = tmp_path / "PHASER.1.pdb"
    combined.write_bytes(model.read_bytes())
    solution_file = tmp_path / "PHASER.sol"
    solution_file.write_text(
        "SOLU SET LLG=100\nSOLU 6DIM ENSE search_A EULER 1 0 0 FRAC 0 0 0 BFAC 0\n",
        encoding="ascii",
    )
    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=f"mrhyp_{'1' * 64}",
        crystal_id=CRYSTAL,
        sequence_group_id=group.sequence_group_id,
        model_id=entry.model_id,
        copy_count_expected=1,
        copy_number_to_search=1,
        space_group="P 1",
        obs_labels="F,SIGF",
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.SMOKE,
        priority_features={"copy_search_mode": "joint_declared_copies"},
        status=MrHypothesisStatus.QUEUED,
    )
    hypotheses = tmp_path / "hypotheses.jsonl"
    hypotheses.write_text(f"{canonical_json_text(hypothesis)}\n", encoding="utf-8")
    state_id = "reviewed_A_state"
    copy = CopyCountAssessment(
        schema_version="1.0",
        assessment_id="copy_assessment",
        review_id="review_A",
        seed_solution_id=state_id,
        hypothesis_id=hypothesis.hypothesis_id,
        sequence_group_id=group.sequence_group_id,
        expected_copy_count=1,
        best_supported_copy_count=1,
        attempted_transition_count=0,
        reached_expected_copy_count=True,
        final_execution_status=ExecutionStatus.COMPLETED_HIT,
        final_llg=100.0,
        final_tfz=12.0,
        final_llg_delta_from_parent=None,
        final_top_solution_packed=True,
        final_placement_count=1,
        terminal_reason="expected_copy_count_reached",
        review_flags=(),
    )
    copies = tmp_path / "copy_assessments.jsonl"
    copies.write_text(f"{canonical_json_text(copy)}\n", encoding="utf-8")
    packing = NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=hypothesis.hypothesis_id,
        tool_version="Phaser test",
        execution_status=ExecutionStatus.COMPLETED_HIT,
        llg=100.0,
        tfz=12.0,
        placed_copy_count=1,
        packing_summary={"top_solution_packed": True, "packed_solution_count": 1},
        solution_coordinate_path=combined.name,
        solution_coordinate_sha256=sha256_file(combined),
        solution_file_path=solution_file.name,
        output_mtz_path=output_mtz.name,
        output_mtz_sha256=sha256_file(output_mtz),
        raw_log_pointer="PHASER.log",
    )
    packing_path = tmp_path / "normalised_mr_result.json"
    atomic_write_json(packing_path, packing.model_dump(mode="json"))
    solution = UnknownPass1SolutionEvidence(
        crystal_id=CRYSTAL,
        state_id=state_id,
        search_sequence_group_id=group.sequence_group_id,
        sequence_group_id=group.sequence_group_id,
        requested_copy_count=1,
        observed_copy_count=1,
        copy_counts_supported=True,
        copy_support_evidence_sha256=sha256_file(copies),
        packing_passed=True,
        packing_evidence_sha256=sha256_file(packing_path),
        refinement_completed=True,
        combined_coordinate_sha256=sha256_file(combined),
        refined_coordinate_sha256="2" * 64,
        refined_mtz_sha256="3" * 64,
        review_map_sha256="4" * 64,
        refinement_evidence_sha256="5" * 64,
        sequence_evidence_sha256="6" * 64,
        final_r_work=0.22,
        final_r_free=0.27,
        parsed_final_metrics_evidence_sha256="7" * 64,
        residual_content_state=UnknownPass1ResidualContentState.NONE_DETECTED,
    )
    reviews = tuple(
        sorted(
            (
                _review(
                    PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
                    f"{CRYSTAL}_review",
                    PhaseIIIReviewDecisionValue.PROCEED,
                    1,
                ),
                _review(
                    PhaseIIIReviewCheckpoint.A_SEED,
                    state_id,
                    PhaseIIIReviewDecisionValue.APPROVE,
                    2,
                ),
                _review(
                    PhaseIIIReviewCheckpoint.COMPOSITION,
                    state_id,
                    PhaseIIIReviewDecisionValue.APPROVE,
                    3,
                ),
                _review(
                    PhaseIIIReviewCheckpoint.SEQUENCE,
                    group.sequence_group_id,
                    PhaseIIIReviewDecisionValue.APPROVE,
                    4,
                ),
            ),
            key=lambda item: (
                item.checkpoint.value,
                item.package_crystal_id,
                item.package_item_id,
                item.decision_crystal_id,
                item.decision_item_id,
                item.review_package_id,
                item.decision_file_id,
            ),
        )
    )
    base_root = tmp_path / "base"
    base_root.mkdir()
    base = PhaseIIIExecutionIdentity.model_validate_json(
        materialise_unknown_pass1_public_fixture(
            base_root
        ).execution_identity.read_bytes()
    )
    identity_values = base.model_dump(mode="python")
    identity_values.pop("execution_identity_id")
    identity_values["crystal_artifacts"] = (
        ExecutionArtifactIdentity.from_content(
            scope="crystal",
            owner_id=CRYSTAL,
            role="mtz",
            sha256=sha256_file(source_mtz),
            size_bytes=source_mtz.stat().st_size,
            release_or_source="pass-2 seed test",
        ),
    )
    identity = PhaseIIIExecutionIdentity.from_content(**identity_values)
    identity_path = tmp_path / "execution_identity.json"
    atomic_write_json(identity_path, identity.model_dump(mode="json"))
    assessment = UnknownPass1CrystalAssessment.from_evidence(
        owned_parent_run_id="gtd-unknown-single-component-parent",
        execution_identity_id=identity.execution_identity_id,
        crystal_id=CRYSTAL,
        crystallographic_review_item_id=f"{CRYSTAL}_review",
        execution_status=ExecutionStatus.COMPLETED_HIT,
        terminal_evidence_sha256="8" * 64,
        candidate_shortlist_present=True,
        solution_evidence=solution,
        review_evidence=reviews,
    )
    assessment_path = tmp_path / "assessment.json"
    atomic_write_json(assessment_path, assessment.model_dump(mode="json"))
    command = tmp_path / "phaser_command.json"
    atomic_write_json(
        command,
        {
            "schema_version": "2.0",
            "phase3_hypothesis_id": hypothesis.hypothesis_id,
            "model_sha256": entry.model_sha256,
            "sequence_sha256": group.sha256,
            "model_identity_percent": 100.0,
            "mtz_sha256": sha256_file(source_mtz),
            "diffraction_selection": {
                "diffraction_dataset_id": "diffraction_pass2_seed"
            },
        },
    )
    sequence_groups = tmp_path / "sequence_groups.jsonl"
    sequence_groups.write_text(
        "".join(f"{canonical_json_text(item)}\n" for item in groups),
        encoding="utf-8",
    )

    output = build_pass2_a_seed(
        Pass2SeedRequest(
            assessment=assessment_path,
            hypothesis_jsonl=hypotheses,
            copy_assessments_jsonl=copies,
            packing_result=packing_path,
            phaser_command=command,
            solution_file=solution_file,
            combined_coordinate=combined,
            source_mtz=source_mtz,
            output_mtz=output_mtz,
            sequence_groups_jsonl=sequence_groups,
            model_registry=registry_output.registry_json,
            execution_identity=identity_path,
            output_directory=tmp_path / "pass2_seed",
        )
    )

    assert output.state.depth == 1
    assert output.state.support_state.value == "refined"
    assert output.state.placements[0].identity_support is (
        ComponentIdentitySupport.UNRESOLVED
    )
    assert output.component_inventory.is_file()
