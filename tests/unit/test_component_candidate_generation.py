"""Complete deterministic evidence joins for schema-v2 expansion candidates."""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

import pytest
from pydantic import ValidationError

from genome_to_diffraction.ids import canonical_digest, sequence_digest
from genome_to_diffraction.localisation import (
    ActiveWaveCompletion,
    ActiveWaveGroupResult,
    ActiveWaveResultStatus,
    CatalogueLocalisationWavePolicy,
    DeepTMHMMBlockedResult,
    DeepTMHMMInvocationPlan,
    FirstWaveDisposition,
    LocalisationGroupEvidence,
    LocalisationOutcome,
    LocalisationReopenPlan,
    LocalisationReopenStatus,
    LocalisationTaskInventory,
    LocalisationTaskItem,
    OfflineExecutionProvenance,
)
from genome_to_diffraction.localisation.contracts import LocalisationResult
from genome_to_diffraction.model_registry import (
    ValidatedProcessedModelInput,
    build_all_eligible_model_registry,
)
from genome_to_diffraction.ranking.candidate_generation import (
    CandidateGenerationError,
    ComponentExpansionInputInventory,
    ParentMatthewsContext,
    ParentModelRankingEvidence,
    build_component_expansion_inputs,
)
from genome_to_diffraction.ranking.composition import (
    ExpansionEvidenceLevel,
    ParentExpansionInput,
    build_registry_bound_composition_expansion_plan,
)
from genome_to_diffraction.schemas.manifests import (
    GelEvidenceManifest,
    GelEvidenceObservation,
    GelMethod,
    SdsBandRole,
)
from genome_to_diffraction.schemas.results import (
    CoordinateSourceRecord,
    ProcessedModelRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.schemas.v2 import (
    ComponentIdentitySupport,
    ComponentPlacement,
    ComponentSpec,
    CompositionState,
    CompositionSupportState,
    ExpansionDisposition,
)
from genome_to_diffraction.status import ExecutionStatus

REPOSITORY = Path(__file__).resolve().parents[2]
MODEL_FIXTURE = REPOSITORY / "tests/fixtures/stubs/predicted_model_preparation"
STUB_MODEL = MODEL_FIXTURE / "models/stub.pdb"


class _GenerationCase(TypedDict):
    groups: tuple[SequenceGroupRecord, ...]
    policy: CatalogueLocalisationWavePolicy
    pending_completion: ActiveWaveCompletion
    pending_reopen: LocalisationReopenPlan
    registry_json: Path
    models: dict[str, tuple[ProcessedModelRecord, ...]]
    parents: tuple[ParentExpansionInput, ...]
    contexts: tuple[ParentMatthewsContext, ...]
    ranking: tuple[ParentModelRankingEvidence, ...]


def _sha(index: int) -> str:
    return f"{index:064x}"


def _group(
    residue: str,
    *,
    mass_da: float | None,
) -> SequenceGroupRecord:
    sequence = residue * 20
    digest = sequence_digest(sequence)
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=mass_da,
        mass_method="synthetic candidate-generation mass",
        residue_policy=(
            "standard_exact" if mass_da is not None else "mass_unavailable"
        ),
        source_record_count=1,
        quality_flags=(() if mass_da is not None else ("mass_unavailable",)),
    )


def _blocked_deeptmhmm(group: SequenceGroupRecord) -> DeepTMHMMBlockedResult:
    provenance = OfflineExecutionProvenance()
    runtime_sha256 = _sha(200)
    image_sha256 = _sha(201)
    input_sha256 = _sha(202)
    payload = {
        "image_sha256": image_sha256,
        "input_fasta_sha256": input_sha256,
        "invocation_status": "blocked_unverified_cli",
        "provenance": provenance,
        "raw_output_retention_required": True,
        "runtime_identity_sha256": runtime_sha256,
        "sequence_group_id": group.sequence_group_id,
        "sequence_sha256": group.sha256,
        "tool": "deeptmhmm",
        "tool_version": "1.0",
    }
    plan = DeepTMHMMInvocationPlan(
        runtime_identity_sha256=runtime_sha256,
        image_sha256=image_sha256,
        sequence_group_id=group.sequence_group_id,
        sequence_sha256=group.sha256,
        input_fasta_path=f"{group.sequence_group_id}.faa",
        input_fasta_sha256=input_sha256,
        block_reason="synthetic verified blocked invocation",
        invocation_identity_sha256=canonical_digest(payload),
        provenance=provenance,
    )
    return DeepTMHMMBlockedResult.from_plan(plan)


def _localisation_policy(
    groups: Sequence[SequenceGroupRecord],
    outcomes: dict[str, LocalisationOutcome],
) -> CatalogueLocalisationWavePolicy:
    runtime_sha256 = _sha(210)
    tasks = tuple(
        LocalisationTaskItem.from_group(
            group,
            input_fasta_sha256=_sha(211),
            psortb_runtime_identity_sha256=runtime_sha256,
            deeptmhmm_runtime_identity_sha256=_sha(212),
        )
        for group in groups
    )
    inventory = LocalisationTaskInventory.from_tasks(
        tasks,
        source_sequence_groups_sha256=_sha(213),
        psortb_runtime_contract_sha256=_sha(214),
        deeptmhmm_runtime_contract_sha256=_sha(215),
        psortb_runtime_identity_sha256=runtime_sha256,
        deeptmhmm_runtime_identity_sha256=_sha(212),
    )
    task_by_group = {task.sequence_group_id: task for task in inventory.tasks}
    evidence: list[LocalisationGroupEvidence] = []
    for group in groups:
        outcome = outcomes[group.sequence_group_id]
        failed = outcome is LocalisationOutcome.FAILED
        psortb = LocalisationResult(
            tool="psortb",
            tool_version="3.0.6",
            runtime_identity_sha256=runtime_sha256,
            sequence_group_id=group.sequence_group_id,
            sequence_sha256=group.sha256,
            execution_status=(
                ExecutionStatus.FAILED_TOOL_EXECUTION
                if failed
                else ExecutionStatus.COMPLETED_SUCCESS
            ),
            outcome=outcome,
            raw_label=None if failed else outcome.value,
            score=None if failed else 9.0,
            raw_output_path=f"raw/{group.sha256}.out",
            raw_output_sha256=_sha(216),
            raw_stderr_path=f"raw/{group.sha256}.err",
            raw_stderr_sha256=_sha(217),
            command_identity_sha256=_sha(218),
        )
        evidence.append(
            LocalisationGroupEvidence.from_results(
                task_by_group[group.sequence_group_id],
                psortb,
                _blocked_deeptmhmm(group),
            )
        )
    return CatalogueLocalisationWavePolicy.from_evidence(inventory, evidence)


def _completion(
    policy: CatalogueLocalisationWavePolicy,
    *,
    complete_zero_pack: bool,
) -> ActiveWaveCompletion:
    results = (
        tuple(
            ActiveWaveGroupResult(
                sequence_group_id=group_id,
                status=ActiveWaveResultStatus.COMPLETED_NO_PACKED_RESULT,
                source_result_sha256=_sha(220 + index),
            )
            for index, group_id in enumerate(policy.first_wave_group_ids)
        )
        if complete_zero_pack
        else ()
    )
    return ActiveWaveCompletion.from_results(policy.first_wave_group_ids, results)


def _template_model() -> ProcessedModelRecord:
    return ProcessedModelRecord.model_validate_json(
        (MODEL_FIXTURE / "processed_models.jsonl").read_text(encoding="utf-8")
    )


def _registry(
    root: Path,
    groups: Sequence[SequenceGroupRecord],
    model_counts: dict[str, int],
) -> tuple[Path, dict[str, tuple[ProcessedModelRecord, ...]]]:
    template = _template_model()
    inputs: list[ValidatedProcessedModelInput] = []
    by_group: dict[str, tuple[ProcessedModelRecord, ...]] = {}
    model_index = 1
    for group in groups:
        coordinate = CoordinateSourceRecord(
            schema_version="1.0",
            coordinate_id=f"coord_{group.sha256}",
            provider="afdb",
            provider_accession=f"AF-{group.sha256[:12]}-F1",
            retrieval_date=datetime(2026, 8, 23, tzinfo=UTC),
            source_release="v6",
            coordinate_path=f"coordinates/{group.sha256}.cif",
            coordinate_sha256=group.sha256,
            source_sequence_sha256=group.sha256,
            confidence_summary={"mean_plddt": 90.0},
            license_or_provenance="synthetic candidate-generation fixture",
        )
        models: list[ProcessedModelRecord] = []
        for _ in range(model_counts[group.sequence_group_id]):
            model = template.model_copy(
                update={
                    "model_id": f"model_{model_index:064x}",
                    "coordinate_id": coordinate.coordinate_id,
                    "full_candidate_sequence_group_id": group.sequence_group_id,
                }
            )
            inputs.append(
                ValidatedProcessedModelInput(
                    model=model,
                    coordinate=coordinate,
                    sequence_group=group,
                    model_path=STUB_MODEL,
                    retained_fraction=1.0,
                )
            )
            models.append(model)
            model_index += 1
        by_group[group.sequence_group_id] = tuple(models)
    output = build_all_eligible_model_registry(
        models=inputs,
        sequence_groups=groups,
        output_directory=root,
    )
    return output.registry_json, by_group


def _parent(
    rank: int,
    *,
    group: SequenceGroupRecord,
    model: ProcessedModelRecord,
) -> ParentExpansionInput:
    copies = rank
    component = ComponentSpec.from_content(
        label="A",
        sequence_group_id=group.sequence_group_id,
        sequence_sha256=group.sha256,
        model_id=model.model_id,
        model_sha256=model.model_sha256,
        requested_copy_count=copies,
        sequence_mass_da=group.molecular_mass_da,
        mass_evidence_sha256=canonical_digest(group),
        model_evidence_sha256=canonical_digest(model),
    )
    placement = ComponentPlacement.from_content(
        component_spec_id=component.component_spec_id,
        component_label="A",
        sequence_group_id=group.sequence_group_id,
        model_id=model.model_id,
        model_sha256=model.model_sha256,
        requested_copy_count=copies,
        observed_copy_count=copies,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        component_tfz=12.0,
        incremental_llg=120.0,
        packing_passed=True,
        coordinate_sha256=_sha(300 + rank),
        identity_support=ComponentIdentitySupport.UNRESOLVED,
    )
    mass = group.molecular_mass_da
    assert mass is not None
    state = CompositionState.from_content(
        crystal_id="crystal_candidates",
        diffraction_dataset_id="diffraction_candidates",
        diffraction_sha256=_sha(310),
        parent_state_id=None,
        depth=1,
        components=(component,),
        placements=(placement,),
        combined_coordinate_sha256=_sha(300 + rank),
        physical_mass_lower_da=mass * copies,
        physical_mass_upper_da=mass * copies,
        support_state=CompositionSupportState.PACKED,
    )
    return ParentExpansionInput(parent_rank=rank, state=state)


def _gel() -> GelEvidenceManifest:
    return GelEvidenceManifest(
        schema_version="2.0",
        observations=(
            GelEvidenceObservation(
                observation_id="sds-20",
                crystal_id="crystal_candidates",
                method=GelMethod.SDS_PAGE,
                apparent_mass_kda=20.0,
                absolute_uncertainty_kda=1.0,
                condition="reducing",
                band_role=SdsBandRole.DOMINANT,
                replicate_id="rep-1",
                source="synthetic gel fixture",
            ),
            GelEvidenceObservation(
                observation_id="native-60",
                crystal_id="crystal_candidates",
                method=GelMethod.NATIVE_PAGE,
                apparent_mass_kda=60.0,
                absolute_uncertainty_kda=1.0,
                condition="native",
                band_role=SdsBandRole.DOMINANT,
                replicate_id="rep-1",
                source="synthetic gel fixture",
            ),
        ),
    )


@pytest.fixture
def generation_case(tmp_path: Path) -> _GenerationCase:
    groups = (
        _group("A", mass_da=20_000.0),
        _group("C", mass_da=20_000.0),
        _group("D", mass_da=30_000.0),
        _group("E", mass_da=25_000.0),
        _group("F", mass_da=22_000.0),
        _group("G", mass_da=24_000.0),
        _group("H", mass_da=None),
    )
    outcomes = {
        groups[0].sequence_group_id: LocalisationOutcome.SOLUBLE,
        groups[1].sequence_group_id: LocalisationOutcome.SOLUBLE,
        groups[2].sequence_group_id: LocalisationOutcome.MEMBRANE,
        groups[3].sequence_group_id: LocalisationOutcome.UNKNOWN,
        groups[4].sequence_group_id: LocalisationOutcome.FAILED,
        groups[5].sequence_group_id: LocalisationOutcome.CONFLICTING,
        groups[6].sequence_group_id: LocalisationOutcome.UNKNOWN,
    }
    policy = _localisation_policy(groups, outcomes)
    pending_completion = _completion(policy, complete_zero_pack=False)
    pending_reopen = LocalisationReopenPlan.from_policy(
        policy,
        pending_completion,
    )
    model_counts = {
        groups[0].sequence_group_id: 25,
        groups[1].sequence_group_id: 2,
        groups[2].sequence_group_id: 1,
        groups[3].sequence_group_id: 0,
        groups[4].sequence_group_id: 1,
        groups[5].sequence_group_id: 1,
        groups[6].sequence_group_id: 0,
    }
    registry_json, models = _registry(
        tmp_path / "registry",
        groups,
        model_counts,
    )
    parents = (
        _parent(1, group=groups[0], model=models[groups[0].sequence_group_id][0]),
        _parent(2, group=groups[0], model=models[groups[0].sequence_group_id][0]),
    )
    contexts = tuple(
        ParentMatthewsContext(
            parent_state_id=parent.state.state_id,
            asu_volume_a3=250_000.0,
            minimum_solvent_fraction=0.45,
            maximum_solvent_fraction=0.75,
            source_evidence_sha256=_sha(400 + parent.parent_rank),
        )
        for parent in parents
    )
    b_models = models[groups[1].sequence_group_id]
    ranking = tuple(
        ParentModelRankingEvidence(
            parent_state_id=parent.state.state_id,
            model_id=model.model_id,
            model_sha256=model.model_sha256,
            policy_version="synthetic-model-ranking-v1",
            model_quality_evidence=ExpansionEvidenceLevel.SUPPORTING,
            structural_diversity_evidence=(
                ExpansionEvidenceLevel.SUPPORTING
                if index == 2
                else ExpansionEvidenceLevel.NEUTRAL
            ),
            evidence_sha256=_sha(500 + parent.parent_rank * 10 + index),
        )
        for parent in parents
        for index, model in enumerate(b_models, start=1)
    )
    return {
        "groups": groups,
        "policy": policy,
        "pending_completion": pending_completion,
        "pending_reopen": pending_reopen,
        "registry_json": registry_json,
        "models": models,
        "parents": parents,
        "contexts": contexts,
        "ranking": ranking,
    }


def _generate(
    case: _GenerationCase,
    *,
    parents: Sequence[ParentExpansionInput] | None = None,
    sequence_groups: Sequence[SequenceGroupRecord] | None = None,
    localisation_policy: CatalogueLocalisationWavePolicy | None = None,
    active_wave_completion: ActiveWaveCompletion | None = None,
    localisation_reopen_plan: LocalisationReopenPlan | None = None,
    gel_evidence: GelEvidenceManifest | None = None,
    matthews_contexts: Sequence[ParentMatthewsContext] | None = None,
    model_ranking_evidence: Sequence[ParentModelRankingEvidence] | None = None,
):
    return build_component_expansion_inputs(
        parents=case["parents"] if parents is None else parents,
        sequence_groups=(
            case["groups"] if sequence_groups is None else sequence_groups
        ),
        localisation_policy=(
            case["policy"] if localisation_policy is None else localisation_policy
        ),
        active_wave_completion=(
            case["pending_completion"]
            if active_wave_completion is None
            else active_wave_completion
        ),
        localisation_reopen_plan=(
            case["pending_reopen"]
            if localisation_reopen_plan is None
            else localisation_reopen_plan
        ),
        gel_evidence=_gel() if gel_evidence is None else gel_evidence,
        matthews_contexts=(
            case["contexts"] if matthews_contexts is None else matthews_contexts
        ),
        model_registry_json=case["registry_json"],
        model_ranking_evidence=(
            case["ranking"]
            if model_ranking_evidence is None
            else model_ranking_evidence
        ),
    )


def test_complete_join_is_deterministic_and_uses_all_model_registry(
    generation_case: _GenerationCase,
) -> None:
    first = _generate(generation_case)
    repeated = _generate(
        generation_case,
        parents=tuple(reversed(generation_case["parents"])),
        sequence_groups=tuple(reversed(generation_case["groups"])),
        gel_evidence=GelEvidenceManifest(
            schema_version="2.0",
            observations=tuple(reversed(_gel().observations)),
        ),
        matthews_contexts=tuple(reversed(generation_case["contexts"])),
        model_ranking_evidence=tuple(reversed(generation_case["ranking"])),
    )

    assert first == repeated
    inventory = first.inventory
    assert inventory.catalogue_group_count == 7
    assert inventory.parent_count == 2
    assert inventory.represented_group_occurrence_count == 2
    assert inventory.expected_candidate_row_count == 12
    assert inventory.candidate_row_count == 12
    assert inventory.total_composition_copy_evidence_count == 48
    assert inventory.assessed_copy_evidence_count == 40
    assert inventory.unassessed_copy_evidence_count == 8
    assert inventory.retained_first_wave_excluded_row_count == 2
    assert inventory.first_wave_eligible_row_count == 10
    assert inventory.reopened_row_count == 0
    assert inventory.wave_eligible_row_count == 10
    assert inventory.model_unavailable_row_count == 4
    assert (
        len({(row.parent_state_id, row.sequence_group_id) for row in inventory.rows})
        == 12
    )
    assert inventory.catalogue_sequence_group_ids == tuple(
        sorted(group.sequence_group_id for group in generation_case["groups"])
    )
    assert all(
        set(coverage.represented_sequence_group_ids)
        | set(coverage.candidate_sequence_group_ids)
        == set(inventory.catalogue_sequence_group_ids)
        for coverage in inventory.parent_coverages
    )

    incomplete_coverage = inventory.parent_coverages[0].model_copy(
        update={
            "candidate_sequence_group_ids": (
                inventory.parent_coverages[0].candidate_sequence_group_ids[:-1]
            )
        }
    )
    payload = inventory.model_dump(mode="python", exclude={"inventory_id"})
    payload["parent_coverages"] = (
        incomplete_coverage,
        *inventory.parent_coverages[1:],
    )
    with pytest.raises(ValidationError, match="candidate rows differ"):
        ComponentExpansionInputInventory.from_rows(**payload)

    groups = generation_case["groups"]
    models = generation_case["models"]
    parents = generation_case["parents"]
    a_shortlist = {model.model_id for model in models[groups[0].sequence_group_id]}
    selected_b = models[groups[1].sequence_group_id][1]
    b_rows = tuple(
        row
        for row in inventory.rows
        if row.sequence_group_id == groups[1].sequence_group_id
    )
    assert len(a_shortlist) == 25
    assert selected_b.model_id not in a_shortlist
    assert all(
        row.component_input.component_specs[0].model_id == selected_b.model_id
        and row.component_input.model_quality_evidence
        is ExpansionEvidenceLevel.SUPPORTING
        and row.component_input.structural_diversity_evidence
        is ExpansionEvidenceLevel.SUPPORTING
        and row.component_input.candidate_rank == 1
        for row in b_rows
    )
    assert {row.parent_state_id for row in b_rows} == {
        parent.state.state_id for parent in parents
    }


def test_parent_specific_total_composition_copies_and_missing_mass_are_retained(
    generation_case: _GenerationCase,
) -> None:
    output = _generate(generation_case)
    groups = generation_case["groups"]
    parents = generation_case["parents"]
    b_rows = {
        row.parent_state_id: row
        for row in output.inventory.rows
        if row.sequence_group_id == groups[1].sequence_group_id
    }

    assert b_rows[
        parents[0].state.state_id
    ].component_input.physically_eligible_copy_counts == (2, 3, 4)
    assert b_rows[
        parents[1].state.state_id
    ].component_input.physically_eligible_copy_counts == (1, 2, 3)
    assert all(
        row.component_input.sds_page_evidence is ExpansionEvidenceLevel.SUPPORTING
        and row.component_input.native_page_evidence
        is ExpansionEvidenceLevel.SUPPORTING
        for row in b_rows.values()
    )

    unavailable_mass_rows = tuple(
        row
        for row in output.inventory.rows
        if row.sequence_group_id == groups[6].sequence_group_id
    )
    assert len(unavailable_mass_rows) == 2
    assert all(
        row.component_input.physically_eligible_copy_counts == ()
        and row.component_input.physically_assessed_copy_counts == ()
        and row.component_input.matthews_evidence is ExpansionEvidenceLevel.NEUTRAL
        and all(
            component.sequence_mass_da is None
            and component.sequence_mass_lower_da is None
            and component.sequence_mass_upper_da is None
            and "sequence_mass_unavailable" in component.warnings
            for component in row.component_input.component_specs
        )
        and all(item.physical_status is None for item in row.total_composition_evidence)
        for row in unavailable_mass_rows
    )


def test_uncertain_failed_localisation_and_missing_gel_are_neutral(
    generation_case: _GenerationCase,
) -> None:
    output = _generate(
        generation_case,
        gel_evidence=GelEvidenceManifest(schema_version="2.0"),
    )
    neutral_outcomes = {
        LocalisationOutcome.UNKNOWN,
        LocalisationOutcome.CONFLICTING,
        LocalisationOutcome.FAILED,
    }
    rows = tuple(
        row
        for row in output.inventory.rows
        if row.localisation_outcome in neutral_outcomes
    )

    assert rows
    assert all(
        row.first_wave_disposition is FirstWaveDisposition.NEUTRAL
        and row.first_wave_eligible
        and row.wave_eligible
        and row.component_input.localisation_evidence is ExpansionEvidenceLevel.NEUTRAL
        and row.component_input.sds_page_evidence is ExpansionEvidenceLevel.NEUTRAL
        and row.component_input.native_page_evidence is ExpansionEvidenceLevel.NEUTRAL
        for row in rows
    )


def test_excluded_groups_reopen_only_from_the_exact_complete_zero_pack_trigger(
    generation_case: _GenerationCase,
) -> None:
    pending = _generate(generation_case)
    policy = generation_case["policy"]
    completed = _completion(policy, complete_zero_pack=True)
    activated_plan = LocalisationReopenPlan.from_policy(policy, completed)
    activated = _generate(
        generation_case,
        active_wave_completion=completed,
        localisation_reopen_plan=activated_plan,
    )
    assert activated_plan.status is LocalisationReopenStatus.ACTIVATED_NO_PACKED_RESULT

    excluded_group = generation_case["groups"][2].sequence_group_id
    pending_rows = {
        row.parent_state_id: row
        for row in pending.inventory.rows
        if row.sequence_group_id == excluded_group
    }
    activated_rows = {
        row.parent_state_id: row
        for row in activated.inventory.rows
        if row.sequence_group_id == excluded_group
    }
    assert all(
        not row.reopened
        and not row.wave_eligible
        and not row.component_input.localisation_wave_eligible
        and row.component_input.reviewer_allowed
        and row.component_input.localisation_evidence
        is ExpansionEvidenceLevel.CONFLICTING
        for row in pending_rows.values()
    )
    assert all(
        row.reopened
        and row.wave_eligible
        and row.component_input.localisation_wave_eligible
        and row.component_input.reviewer_allowed
        and row.component_input.localisation_evidence
        is ExpansionEvidenceLevel.CONFLICTING
        for row in activated_rows.values()
    )
    with pytest.raises(CandidateGenerationError, match="not derived"):
        _generate(
            generation_case,
            active_wave_completion=generation_case["pending_completion"],
            localisation_reopen_plan=activated_plan,
        )


def test_generated_rows_plan_without_support_promotion(
    generation_case: _GenerationCase,
) -> None:
    output = _generate(generation_case)
    plan = build_registry_bound_composition_expansion_plan(
        output.as_request(),
        model_registry_json=generation_case["registry_json"],
    )
    excluded_group = generation_case["groups"][2].sequence_group_id
    excluded = tuple(
        item
        for item in plan.depth_plan.candidates
        if item.hypothesis.component.sequence_group_id == excluded_group
    )
    mass_unavailable_group = generation_case["groups"][6].sequence_group_id
    mass_unavailable = tuple(
        item
        for item in plan.depth_plan.candidates
        if item.hypothesis.component.sequence_group_id == mass_unavailable_group
    )

    assert excluded
    assert {item.hypothesis.disposition for item in excluded} == {
        ExpansionDisposition.DEFERRED_LOCALISATION_WAVE,
        ExpansionDisposition.EXCLUDED_PHYSICAL_IMPOSSIBLE,
    }
    assert mass_unavailable
    assert {item.hypothesis.disposition for item in mass_unavailable} == {
        ExpansionDisposition.UNSEARCHABLE_PHYSICAL_EVIDENCE
    }
    assert all(not item.hypothesis.physical_assessed for item in mass_unavailable)
    assert all(
        parent.state.support_state is CompositionSupportState.PACKED
        for parent in output.parents
    )
    assert all(
        item.hypothesis.disposition is not ExpansionDisposition.SELECTED
        or "selection is not scientific support" in item.hypothesis.disposition_reason
        for item in plan.depth_plan.candidates
    )


def test_incomplete_catalogue_localisation_coverage_fails(
    generation_case: _GenerationCase,
) -> None:
    groups = generation_case["groups"]
    incomplete = _localisation_policy(
        groups[:-1],
        {group.sequence_group_id: LocalisationOutcome.UNKNOWN for group in groups[:-1]},
    )
    completion = _completion(incomplete, complete_zero_pack=False)
    reopen = LocalisationReopenPlan.from_policy(incomplete, completion)

    with pytest.raises(CandidateGenerationError, match="complete catalogue"):
        _generate(
            generation_case,
            localisation_policy=incomplete,
            active_wave_completion=completion,
            localisation_reopen_plan=reopen,
        )
