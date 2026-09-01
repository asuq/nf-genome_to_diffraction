"""Integration tests for all-model-registry-backed composition planning."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from genome_to_diffraction.ids import sequence_digest
from genome_to_diffraction.model_registry import (
    ValidatedProcessedModelInput,
    build_all_eligible_model_registry,
)
from genome_to_diffraction.ranking.composition import (
    ComponentExpansionInput,
    CompositionExpansionRequest,
    CompositionPlanningError,
    ParentExpansionInput,
    build_registry_bound_composition_expansion_plan,
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
    CompositionExpansionDepthPlan,
    CompositionState,
    CompositionSupportState,
    ExpansionDisposition,
    ModelUnavailableReason,
    RegistryModelResolutionScope,
)
from genome_to_diffraction.status import ExecutionStatus

REPOSITORY = Path(__file__).resolve().parents[2]
STUB_PREPARATION = REPOSITORY / "tests/fixtures/stubs/predicted_model_preparation"
STUB_MODEL = STUB_PREPARATION / "models/stub.pdb"


def _sha(index: int) -> str:
    return f"{index:064x}"


def _group(sequence: str) -> SequenceGroupRecord:
    digest = sequence_digest(sequence)
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=436.4375,
        mass_method="synthetic registry-planner test mass",
        residue_policy="standard_exact",
        source_record_count=1,
    )


def _coordinate(
    group: SequenceGroupRecord,
    *,
    source_release: str,
) -> CoordinateSourceRecord:
    return CoordinateSourceRecord(
        schema_version="1.0",
        coordinate_id=f"coord_{group.sha256}",
        provider="afdb",
        provider_accession=f"AF-{group.sha256[:12]}-F1",
        retrieval_date=datetime(2026, 8, 23, tzinfo=UTC),
        source_release=source_release,
        coordinate_path=f"coordinates/{group.sha256}.cif",
        coordinate_sha256=group.sha256,
        source_sequence_sha256=group.sha256,
        confidence_summary={"mean_plddt": 90.0},
        license_or_provenance="synthetic registry-planner fixture",
    )


def _template_model() -> ProcessedModelRecord:
    return ProcessedModelRecord.model_validate_json(
        (STUB_PREPARATION / "processed_models.jsonl").read_text(encoding="utf-8")
    )


def _build_registry(
    tmp_path: Path,
    *,
    group_model_counts: tuple[tuple[SequenceGroupRecord, int], ...],
    source_release: str = "v6",
) -> tuple[Path, dict[str, tuple[ProcessedModelRecord, ...]]]:
    template = _template_model()
    inputs: list[ValidatedProcessedModelInput] = []
    models_by_group: dict[str, tuple[ProcessedModelRecord, ...]] = {}
    model_index = 1
    for group, count in group_model_counts:
        coordinate = _coordinate(group, source_release=source_release)
        group_models: list[ProcessedModelRecord] = []
        for _ in range(count):
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
            group_models.append(model)
            model_index += 1
        models_by_group[group.sequence_group_id] = tuple(group_models)
    output = build_all_eligible_model_registry(
        models=tuple(inputs),
        sequence_groups=tuple(group for group, _ in group_model_counts),
        output_directory=tmp_path,
    )
    return output.registry_json, models_by_group


def _component_specs(
    *,
    label: str,
    group: SequenceGroupRecord,
    model_id: str,
    model_sha256: str,
) -> tuple[ComponentSpec, ...]:
    return tuple(
        ComponentSpec.from_content(
            label=label,
            sequence_group_id=group.sequence_group_id,
            sequence_sha256=group.sha256,
            model_id=model_id,
            model_sha256=model_sha256,
            requested_copy_count=copy_count,
            sequence_mass_da=group.molecular_mass_da,
            mass_evidence_sha256=_sha(800),
            model_evidence_sha256=_sha(900),
        )
        for copy_count in range(1, 5)
    )


def _parent(
    *,
    group: SequenceGroupRecord,
    model_id: str,
    model_sha256: str,
) -> ParentExpansionInput:
    component = _component_specs(
        label="A",
        group=group,
        model_id=model_id,
        model_sha256=model_sha256,
    )[0]
    placement = ComponentPlacement.from_content(
        component_spec_id=component.component_spec_id,
        component_label=component.label,
        sequence_group_id=component.sequence_group_id,
        model_id=component.model_id,
        model_sha256=component.model_sha256,
        requested_copy_count=component.requested_copy_count,
        observed_copy_count=1,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        component_tfz=12.0,
        incremental_llg=120.0,
        packing_passed=True,
        coordinate_sha256=_sha(700),
        identity_support=ComponentIdentitySupport.UNRESOLVED,
    )
    state = CompositionState.from_content(
        crystal_id="crystal_registry_planner",
        diffraction_dataset_id="diffraction_registry_planner",
        diffraction_sha256=_sha(701),
        parent_state_id=None,
        depth=1,
        components=(component,),
        placements=(placement,),
        combined_coordinate_sha256=_sha(700),
        physical_mass_lower_da=100.0,
        physical_mass_upper_da=100_000.0,
        support_state=CompositionSupportState.PACKED,
    )
    return ParentExpansionInput(parent_rank=1, state=state)


def _candidate(
    *,
    parent: ParentExpansionInput,
    rank: int,
    group: SequenceGroupRecord,
    model_id: str,
    model_sha256: str,
    provider: str | None = None,
    variant_type: str | None = None,
) -> ComponentExpansionInput:
    return ComponentExpansionInput(
        parent_state_id=parent.state.state_id,
        candidate_rank=rank,
        component_specs=_component_specs(
            label="B",
            group=group,
            model_id=model_id,
            model_sha256=model_sha256,
        ),
        physically_eligible_copy_counts=(1, 2, 3, 4),
        model_provider=provider,
        model_variant_type=variant_type,
    )


def test_model_outside_a_shortlist_is_schedulable_for_b_to_f(
    tmp_path: Path,
) -> None:
    group_a = _group("ACDE")
    group_b = _group("FGHI")
    registry_json, models = _build_registry(
        tmp_path / "registry",
        group_model_counts=((group_a, 25), (group_b, 1)),
    )
    a_shortlist = tuple(model.model_id for model in models[group_a.sequence_group_id])
    parent_model = models[group_a.sequence_group_id][0]
    b_model = models[group_b.sequence_group_id][0]
    parent = _parent(
        group=group_a,
        model_id=parent_model.model_id,
        model_sha256=parent_model.model_sha256,
    )
    candidate = _candidate(
        parent=parent,
        rank=1,
        group=group_b,
        model_id=b_model.model_id,
        model_sha256=b_model.model_sha256,
    )

    output = build_registry_bound_composition_expansion_plan(
        CompositionExpansionRequest(parents=(parent,), candidates=(candidate,)),
        model_registry_json=registry_json,
    )

    assert len(a_shortlist) == 25
    assert b_model.model_id not in a_shortlist
    assert output.depth_plan.selected_attempt_count == 4
    assert len(output.depth_plan.model_resolutions) == 5
    assert all(
        resolution.available for resolution in output.depth_plan.model_resolutions
    )
    assert all(
        candidate.hypothesis.disposition is ExpansionDisposition.SELECTED
        for candidate in output.depth_plan.candidates
    )
    assert all(
        "selection is not scientific support" in candidate.hypothesis.disposition_reason
        for candidate in output.depth_plan.candidates
    )
    assert parent.state.support_state is CompositionSupportState.PACKED


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    (
        ("no_model", ModelUnavailableReason.NO_ELIGIBLE_MODEL),
        ("unknown_group", ModelUnavailableReason.SEQUENCE_GROUP_NOT_REGISTERED),
        ("provider", ModelUnavailableReason.PROVIDER_UNAVAILABLE),
        ("variant", ModelUnavailableReason.VARIANT_UNAVAILABLE),
        ("exact_model", ModelUnavailableReason.MODEL_NOT_REGISTERED),
    ),
)
def test_unavailable_registry_queries_remain_typed_and_unsearchable(
    tmp_path: Path,
    case: str,
    expected_reason: ModelUnavailableReason,
) -> None:
    group_a = _group("ACDE")
    group_b = _group("FGHI")
    group_without_model = _group("KLMN")
    unknown_group = _group("PQRS")
    registry_json, models = _build_registry(
        tmp_path / "registry",
        group_model_counts=((group_a, 1), (group_b, 1), (group_without_model, 0)),
    )
    parent_model = models[group_a.sequence_group_id][0]
    b_model = models[group_b.sequence_group_id][0]
    parent = _parent(
        group=group_a,
        model_id=parent_model.model_id,
        model_sha256=parent_model.model_sha256,
    )
    group = group_b
    model_id = b_model.model_id
    model_sha256 = b_model.model_sha256
    provider = variant_type = None
    if case == "no_model":
        group = group_without_model
        model_id = "model_missing"
        model_sha256 = _sha(1001)
    elif case == "unknown_group":
        group = unknown_group
        model_id = "model_unknown_group"
        model_sha256 = _sha(1002)
    elif case == "provider":
        provider = "pdb"
    elif case == "variant":
        variant_type = "experimental_full"
    else:
        model_id = "model_not_registered"
    candidate = _candidate(
        parent=parent,
        rank=1,
        group=group,
        model_id=model_id,
        model_sha256=model_sha256,
        provider=provider,
        variant_type=variant_type,
    )

    output = build_registry_bound_composition_expansion_plan(
        CompositionExpansionRequest(parents=(parent,), candidates=(candidate,)),
        model_registry_json=registry_json,
    )

    candidate_resolutions = tuple(
        resolution
        for resolution in output.depth_plan.model_resolutions
        if resolution.scope is RegistryModelResolutionScope.CANDIDATE_COPY
    )
    assert len(candidate_resolutions) == 4
    assert {item.unavailable_reason for item in candidate_resolutions} == {
        expected_reason
    }
    assert output.depth_plan.candidate_count == 4
    assert output.depth_plan.selected_attempt_count == 0
    assert {item.hypothesis.disposition for item in output.depth_plan.candidates} == {
        ExpansionDisposition.UNSEARCHABLE_NO_MODEL
    }
    assert all(
        expected_reason.value in item.hypothesis.disposition_reason
        for item in output.depth_plan.candidates
    )

    mutated = output.depth_plan.model_dump(mode="python")
    mutated["model_resolutions"][1]["unavailable_reason"] = (
        ModelUnavailableReason.MODEL_NOT_REGISTERED
        if expected_reason is not ModelUnavailableReason.MODEL_NOT_REGISTERED
        else ModelUnavailableReason.NO_ELIGIBLE_MODEL
    )
    with pytest.raises(ValidationError, match="resolution_id"):
        CompositionExpansionDepthPlan.model_validate(mutated)


def test_unavailable_parent_model_blocks_but_retains_candidate_copies(
    tmp_path: Path,
) -> None:
    group_a = _group("ACDE")
    group_b = _group("FGHI")
    registry_json, models = _build_registry(
        tmp_path / "registry",
        group_model_counts=((group_a, 1), (group_b, 1)),
    )
    actual_a = models[group_a.sequence_group_id][0]
    b_model = models[group_b.sequence_group_id][0]
    parent = _parent(
        group=group_a,
        model_id="model_unregistered_parent",
        model_sha256=actual_a.model_sha256,
    )
    candidate = _candidate(
        parent=parent,
        rank=1,
        group=group_b,
        model_id=b_model.model_id,
        model_sha256=b_model.model_sha256,
    )

    output = build_registry_bound_composition_expansion_plan(
        CompositionExpansionRequest(parents=(parent,), candidates=(candidate,)),
        model_registry_json=registry_json,
    )

    parent_resolutions = tuple(
        resolution
        for resolution in output.depth_plan.model_resolutions
        if resolution.scope is RegistryModelResolutionScope.PARENT_COMPONENT
    )
    assert [item.unavailable_reason for item in parent_resolutions] == [
        ModelUnavailableReason.MODEL_NOT_REGISTERED
    ]
    assert output.depth_plan.candidate_count == 4
    assert output.selected_attempts == ()
    assert all(
        item.hypothesis.disposition is ExpansionDisposition.UNSEARCHABLE_NO_MODEL
        and not item.hypothesis.model_available
        and "parent:" in item.hypothesis.disposition_reason
        for item in output.depth_plan.candidates
    )


def test_registry_binding_preserves_order_neutral_evidence_and_budgets(
    tmp_path: Path,
) -> None:
    groups = tuple(
        _group(sequence)
        for sequence in (
            "ACDE",
            "FGHI",
            "KLMN",
            "PQRS",
            "TVWY",
            "AAAA",
            "CCCC",
            "DDDD",
        )
    )
    registry_json, models = _build_registry(
        tmp_path / "registry",
        group_model_counts=tuple((group, 1) for group in groups),
    )
    parent_model = models[groups[0].sequence_group_id][0]
    parent = _parent(
        group=groups[0],
        model_id=parent_model.model_id,
        model_sha256=parent_model.model_sha256,
    )
    candidates = tuple(
        _candidate(
            parent=parent,
            rank=rank,
            group=group,
            model_id=models[group.sequence_group_id][0].model_id,
            model_sha256=models[group.sequence_group_id][0].model_sha256,
        )
        for rank, group in enumerate(groups[1:], start=1)
    )
    first = build_registry_bound_composition_expansion_plan(
        CompositionExpansionRequest(parents=(parent,), candidates=candidates),
        model_registry_json=registry_json,
    )
    repeated = build_registry_bound_composition_expansion_plan(
        CompositionExpansionRequest(
            parents=(parent,),
            candidates=tuple(reversed(candidates)),
        ),
        model_registry_json=registry_json,
    )
    global_limited = build_registry_bound_composition_expansion_plan(
        CompositionExpansionRequest(
            parents=(parent,),
            candidates=candidates,
            global_attempts_used_before=99,
        ),
        model_registry_json=registry_json,
    )

    assert first == repeated
    assert first.depth_plan.selected_attempt_count == 25
    assert first.depth_plan.candidate_count == 28
    assert first.remaining_global_attempt_budget == 75
    assert all(
        "sds_page:neutral" in item.hypothesis.disposition_reason
        for item in first.depth_plan.candidates
    )
    assert global_limited.depth_plan.selected_attempt_count == 1
    assert global_limited.remaining_global_attempt_budget == 0
    assert {
        item.hypothesis.disposition for item in global_limited.depth_plan.candidates[1:]
    } == {ExpansionDisposition.DEFERRED_GLOBAL_BUDGET}


def test_registry_source_mutation_changes_plan_identity_without_promoting_support(
    tmp_path: Path,
) -> None:
    group_a = _group("ACDE")
    group_b = _group("FGHI")
    first_registry, first_models = _build_registry(
        tmp_path / "first",
        group_model_counts=((group_a, 1), (group_b, 1)),
        source_release="v6",
    )
    second_registry, second_models = _build_registry(
        tmp_path / "second",
        group_model_counts=((group_a, 1), (group_b, 1)),
        source_release="v7",
    )
    parent_model = first_models[group_a.sequence_group_id][0]
    candidate_model = first_models[group_b.sequence_group_id][0]
    assert parent_model == second_models[group_a.sequence_group_id][0]
    assert candidate_model == second_models[group_b.sequence_group_id][0]
    parent = _parent(
        group=group_a,
        model_id=parent_model.model_id,
        model_sha256=parent_model.model_sha256,
    )
    candidate = _candidate(
        parent=parent,
        rank=1,
        group=group_b,
        model_id=candidate_model.model_id,
        model_sha256=candidate_model.model_sha256,
    )
    request = CompositionExpansionRequest(parents=(parent,), candidates=(candidate,))

    first = build_registry_bound_composition_expansion_plan(
        request,
        model_registry_json=first_registry,
    )
    second = build_registry_bound_composition_expansion_plan(
        request,
        model_registry_json=second_registry,
    )

    assert first.depth_plan.model_registry_id != second.depth_plan.model_registry_id
    assert first.depth_plan.depth_plan_id != second.depth_plan.depth_plan_id
    assert first.depth_plan.selected_attempt_count == 4
    assert second.depth_plan.selected_attempt_count == 4
    assert parent.state.support_state is CompositionSupportState.PACKED


def test_candidate_checksum_mismatch_fails_before_planning(tmp_path: Path) -> None:
    group_a = _group("ACDE")
    group_b = _group("FGHI")
    registry_json, models = _build_registry(
        tmp_path / "registry",
        group_model_counts=((group_a, 1), (group_b, 1)),
    )
    parent_model = models[group_a.sequence_group_id][0]
    b_model = models[group_b.sequence_group_id][0]
    parent = _parent(
        group=group_a,
        model_id=parent_model.model_id,
        model_sha256=parent_model.model_sha256,
    )
    candidate = _candidate(
        parent=parent,
        rank=1,
        group=group_b,
        model_id=b_model.model_id,
        model_sha256=_sha(2026),
    )

    with pytest.raises(CompositionPlanningError, match="identity disagrees"):
        build_registry_bound_composition_expansion_plan(
            CompositionExpansionRequest(parents=(parent,), candidates=(candidate,)),
            model_registry_json=registry_json,
        )


def test_tampered_registry_model_fails_before_planning(tmp_path: Path) -> None:
    group_a = _group("ACDE")
    group_b = _group("FGHI")
    registry_json, models = _build_registry(
        tmp_path / "registry",
        group_model_counts=((group_a, 1), (group_b, 1)),
    )
    parent_model = models[group_a.sequence_group_id][0]
    b_model = models[group_b.sequence_group_id][0]
    parent = _parent(
        group=group_a,
        model_id=parent_model.model_id,
        model_sha256=parent_model.model_sha256,
    )
    candidate = _candidate(
        parent=parent,
        rank=1,
        group=group_b,
        model_id=b_model.model_id,
        model_sha256=b_model.model_sha256,
    )
    registry_document = json.loads(registry_json.read_text(encoding="utf-8"))
    model_path = (
        registry_json.parent
        / registry_document["sequence_groups"][0]["models"][0]["model_path"]
    )
    model_path.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(CompositionPlanningError, match="checksum verified"):
        build_registry_bound_composition_expansion_plan(
            CompositionExpansionRequest(parents=(parent,), candidates=(candidate,)),
            model_registry_json=registry_json,
        )
