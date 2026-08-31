"""Build one executable Phase III composition-search depth from owned evidence.

The adapter joins a retained one-to-three-state beam to the complete catalogue,
offline localisation/gel policy, total-composition Matthews evidence, canonical
all-model registry, selected diffraction/Free-R identities, and run-owned
component coordinates. It emits one complete 0--25-attempt inventory. It runs
no external scientific tool and never promotes identity or composition support.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.execution.composition import (
    build_composition_attempt_inventory,
    write_composition_attempt_inventory,
)
from genome_to_diffraction.execution.finding_closure import (
    PhaseIIIFindingClosureEvidenceFiles,
    validate_phase3_finding_closure,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.localisation import (
    ActiveWaveCompletion,
    CatalogueLocalisationWavePolicy,
    LocalisationReopenPlan,
)
from genome_to_diffraction.model_registry.all_eligible import (
    AllEligibleModelEntry,
    AllEligibleModelRegistry,
    AllEligibleModelRegistryError,
    load_all_eligible_model_registry,
)
from genome_to_diffraction.mr.fixed_components import (
    FixedComponentEvidenceError,
    FixedComponentEvidenceRequest,
    FixedComponentUncertainty,
    build_fixed_component_execution_evidence,
)
from genome_to_diffraction.mr_resources import (
    build_mr_resource_plan,
    count_polymer_atoms,
)
from genome_to_diffraction.ranking import (
    CompositionExpansionRequest,
    ParentExpansionInput,
    ParentMatthewsContext,
    ParentModelRankingEvidence,
    build_component_expansion_inputs,
    build_registry_bound_composition_expansion_plan,
)
from genome_to_diffraction.schemas.manifests import GelEvidenceManifest
from genome_to_diffraction.schemas.results import (
    MtzPreflightRecord,
    NormalisedMrResult,
    SequenceGroupRecord,
)
from genome_to_diffraction.schemas.v2 import (
    ComponentExpansionExecutionInput,
    ComponentExpansionScoreEvidence,
    CompositionState,
    DiffractionSelection,
    FreeRIdentity,
    MrResourcePlan,
    PhaseIIIExecutionIdentity,
    PhaserPerPlacementInventory,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_ADAPTER_VERSION = "phase3-composition-depth-input-v1"


class CompositionDepthInputError(InputContractError):
    """Owned inputs cannot form one executable composition depth."""


@dataclass(frozen=True, slots=True)
class CompositionDepthInputRequest:
    """Complete local files used to build one B--F attempt inventory."""

    parent_states_jsonl: Path
    sequence_groups_jsonl: Path
    localisation_policy: Path
    active_wave_completion: Path
    localisation_reopen_plan: Path
    gel_evidence: Path
    preflight_jsonl: Path
    model_registry: Path
    model_ranking_evidence_jsonl: Path
    diffraction_selection: Path
    free_r_identity: Path
    fixed_coordinate_root: Path
    execution_identity: Path
    finding_closure: Path
    finding_ledger: Path
    adverse_review_evidence: Path
    integration_gate_evidence: Path
    known_control_evidence: Path
    m6_evidence: Path
    unknown_pass1_evidence: Path
    exact_source_ci_evidence: Path
    output_directory: Path
    global_attempts_used_before: int = 0
    per_depth_attempt_budget: int = 25


@dataclass(frozen=True, slots=True)
class CompositionDepthInputOutput:
    """Published candidate, plan, execution, and checksum artifacts."""

    attempt_inventory: Path
    candidate_inventory: Path
    depth_plan: Path
    checksums: Path
    attempt_count: int


def _typed_json(path: Path, model, label: str):
    if path.is_symlink() or not path.is_file():
        raise CompositionDepthInputError(f"{label} must be a regular file")
    try:
        return model.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise CompositionDepthInputError(f"{label} violates its contract") from error


def _typed_jsonl(path: Path, model, label: str) -> tuple:
    if path.is_symlink() or not path.is_file():
        raise CompositionDepthInputError(f"{label} must be a regular file")
    records = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(model.model_validate_json(line))
                except (ValidationError, ValueError) as error:
                    raise CompositionDepthInputError(
                        f"{label} line {line_number} violates its contract"
                    ) from error
    except (OSError, UnicodeError) as error:
        raise CompositionDepthInputError(f"{label} is unreadable") from error
    return tuple(records)


def _registry_entry(
    registry: AllEligibleModelRegistry,
    *,
    sequence_group_id: str,
    model_id: str,
    model_sha256: str,
) -> AllEligibleModelEntry:
    matches = tuple(
        entry
        for group in registry.manifest.sequence_groups
        for entry in group.models
        if entry.sequence_group_id == sequence_group_id
        and entry.model_id == model_id
        and entry.model_sha256 == model_sha256
    )
    if len(matches) != 1:
        raise CompositionDepthInputError(
            "all-model registry lacks one exact component model"
        )
    return matches[0]


def _find_component_inventory(root: Path, state: CompositionState) -> Path:
    matches: dict[str, Path] = {}
    for path in root.rglob("phaser_per_placement_inventory.json"):
        if path.is_symlink() or not path.is_file():
            raise CompositionDepthInputError("component evidence contains a symlink")
        try:
            inventory = PhaserPerPlacementInventory.model_validate_json(
                path.read_bytes()
            )
        except OSError, ValidationError, ValueError:
            continue
        if (
            inventory.crystal_id == state.crystal_id
            and inventory.combined_coordinate_sha256 == state.combined_coordinate_sha256
        ):
            matches.setdefault(sha256_file(path), path)
    if len(matches) != 1:
        raise CompositionDepthInputError(
            "parent lacks one exact component-coordinate inventory"
        )
    return next(iter(matches.values()))


def _parent_score(
    root: Path,
    state: CompositionState,
) -> tuple[float, str]:
    matches: dict[str, tuple[float, Path]] = {}
    if state.depth == 1:
        for path in root.rglob("normalised_mr_result.json"):
            try:
                result = NormalisedMrResult.model_validate_json(path.read_bytes())
            except OSError, ValidationError, ValueError:
                continue
            if (
                result.execution_status is ExecutionStatus.COMPLETED_HIT
                and result.solution_coordinate_sha256
                == state.combined_coordinate_sha256
                and result.llg is not None
            ):
                matches.setdefault(sha256_file(path), (result.llg, path))
    else:
        for path in root.rglob("component_score_evidence.json"):
            try:
                score = ComponentExpansionScoreEvidence.model_validate_json(
                    path.read_bytes()
                )
            except OSError, ValidationError, ValueError:
                continue
            if (
                score.execution_input.parent_state.state_id == state.parent_state_id
                and score.placement == state.placements[-1]
                and score.placement.coordinate_sha256
                == state.placements[-1].coordinate_sha256
            ):
                matches.setdefault(sha256_file(path), (score.combined_llg, path))
    if len(matches) != 1:
        raise CompositionDepthInputError("parent lacks one exact score record")
    digest, (combined_llg, _) = next(iter(matches.items()))
    return combined_llg, digest


def _execution_inputs(
    *,
    parents: tuple[ParentExpansionInput, ...],
    depth_plan,
    selected_attempts,
    registry: AllEligibleModelRegistry,
    registry_root: Path,
    fixed_root: Path,
    selection: DiffractionSelection,
    free_r: FreeRIdentity,
    preflight: MtzPreflightRecord,
) -> tuple[
    tuple[ComponentExpansionExecutionInput, ...],
    tuple[MrResourcePlan, ...],
]:
    parent_by_id = {parent.state.state_id: parent for parent in parents}
    candidates = {
        candidate.depth_candidate_id: candidate for candidate in depth_plan.candidates
    }
    resolutions = {
        (item.parent_state_id, item.component_spec_id): item
        for item in depth_plan.model_resolutions
    }
    fixed_by_parent = {}
    fixed_atom_counts: dict[str, int] = {}
    score_by_parent = {}
    for parent in parents:
        state = parent.state
        inventory_path = _find_component_inventory(fixed_root, state)
        uncertainties = tuple(
            FixedComponentUncertainty(
                component_label=component.label,
                phaser_identity_fraction=_registry_entry(
                    registry,
                    sequence_group_id=component.sequence_group_id,
                    model_id=component.model_id,
                    model_sha256=component.model_sha256,
                ).model_sequence_identity,
                model_uncertainty_source=_registry_entry(
                    registry,
                    sequence_group_id=component.sequence_group_id,
                    model_id=component.model_id,
                    model_sha256=component.model_sha256,
                ).model_uncertainty_source,
                model_uncertainty_evidence_sha256=(component.model_evidence_sha256),
            )
            for component in state.components
        )
        try:
            placement_inventory = PhaserPerPlacementInventory.model_validate_json(
                inventory_path.read_bytes()
            )
            fixed = build_fixed_component_execution_evidence(
                FixedComponentEvidenceRequest(
                    parent_state=state,
                    inventory_json=inventory_path,
                    uncertainties=uncertainties,
                )
            )
        except (OSError, ValidationError, FixedComponentEvidenceError) as error:
            raise CompositionDepthInputError(
                "parent fixed-component evidence is invalid"
            ) from error
        fixed_by_parent[state.state_id] = fixed.evidence
        fixed_atom_counts[state.state_id] = placement_inventory.combined_atom_count
        score_by_parent[state.state_id] = _parent_score(fixed_root, state)

    outputs: list[ComponentExpansionExecutionInput] = []
    resource_plans: list[MrResourcePlan] = []
    for attempt in selected_attempts:
        parent = parent_by_id[attempt.parent_state_id]
        candidate = candidates[attempt.depth_candidate_id]
        component = candidate.hypothesis.component
        entry = _registry_entry(
            registry,
            sequence_group_id=component.sequence_group_id,
            model_id=component.model_id,
            model_sha256=component.model_sha256,
        )
        if entry.model_sequence_identity <= 0:
            raise CompositionDepthInputError(
                "selected candidate has no usable model identity"
            )
        resolution = resolutions[(parent.state.state_id, component.component_spec_id)]
        parent_llg, parent_score_sha = score_by_parent[parent.state.state_id]
        candidate_path = (registry_root / entry.model_path).resolve(strict=True)
        if not candidate_path.is_relative_to(registry_root):
            raise CompositionDepthInputError("candidate model escapes its registry")
        execution_input = ComponentExpansionExecutionInput.from_content(
            depth_plan_id=depth_plan.depth_plan_id,
            selected_candidate=candidate,
            parent_state=parent.state,
            fixed_components=fixed_by_parent[parent.state.state_id],
            candidate_model_resolution=resolution,
            candidate_phaser_identity_fraction=entry.model_sequence_identity,
            candidate_model_uncertainty_source=entry.model_uncertainty_source,
            candidate_model_uncertainty_evidence_sha256=(
                component.model_evidence_sha256
            ),
            diffraction_selection=selection,
            free_r_identity=free_r,
            parent_combined_llg=parent_llg,
            parent_score_evidence_sha256=parent_score_sha,
        )
        outputs.append(execution_input)
        resource_plans.append(
            build_mr_resource_plan(
                owner_kind="component_execution_input",
                owner_id=execution_input.execution_input_id,
                reflection_count=preflight.reflection_count,
                moving_atom_count=count_polymer_atoms(candidate_path),
                searched_copy_count=component.requested_copy_count,
                fixed_atom_count=fixed_atom_counts[parent.state.state_id],
                symmetry_multiplicity=preflight.general_position_multiplicity,
            )
        )
    return tuple(outputs), tuple(resource_plans)


def build_composition_depth_inputs(
    request: CompositionDepthInputRequest,
) -> CompositionDepthInputOutput:
    """Build and publish one complete executable B--F depth inventory."""

    if not 0 <= request.global_attempts_used_before <= 100:
        raise ValueError("global attempts used must be between zero and 100")
    if not 1 <= request.per_depth_attempt_budget <= 25:
        raise ValueError("per-depth attempt budget must be between one and 25")
    parents = _typed_jsonl(
        request.parent_states_jsonl, CompositionState, "parent states"
    )
    if not 1 <= len(parents) <= 3:
        raise CompositionDepthInputError("parent beam must contain one to three states")
    parent_inputs = tuple(
        ParentExpansionInput(parent_rank=index, state=state)
        for index, state in enumerate(parents, start=1)
    )
    identity = _typed_json(
        request.execution_identity,
        PhaseIIIExecutionIdentity,
        "execution identity",
    )
    adapters = dict(identity.adapter_versions)
    required_adapters = {
        "phase3_all_model_registry": "all-eligible-model-registry-v3",
        "phase3_component_coordinates": ("phaser-component-coordinate-inventory-v2"),
        "phase3_composition_attempt": (
            "phase3-composition-attempt-execution-v2-resource-plan"
        ),
        "phase3_mr_resources": "phase3-mr-resource-allocation-v1",
        "phase3_composition_beam": "phase3-composition-beam-depth-v1",
        "phase3_composition_depth": _ADAPTER_VERSION,
    }
    if any(
        adapters.get(name) != version for name, version in required_adapters.items()
    ):
        raise CompositionDepthInputError(
            "execution identity lacks current composition-depth adapters"
        )
    closure = validate_phase3_finding_closure(
        request.finding_closure,
        request.finding_ledger,
        expected_source_commit=identity.source_commit,
        expected_source_tree=identity.source_tree,
        evidence_files=PhaseIIIFindingClosureEvidenceFiles(
            adverse_review=request.adverse_review_evidence,
            integration_gate=request.integration_gate_evidence,
            known_control_evidence=request.known_control_evidence,
            m6_evidence=request.m6_evidence,
            unknown_pass1_evidence=request.unknown_pass1_evidence,
            exact_source_ci_evidence=request.exact_source_ci_evidence,
        ),
    )
    groups = _typed_jsonl(
        request.sequence_groups_jsonl, SequenceGroupRecord, "sequence groups"
    )
    policy = _typed_json(
        request.localisation_policy,
        CatalogueLocalisationWavePolicy,
        "localisation policy",
    )
    completion = _typed_json(
        request.active_wave_completion,
        ActiveWaveCompletion,
        "active-wave completion",
    )
    reopen = _typed_json(
        request.localisation_reopen_plan,
        LocalisationReopenPlan,
        "localisation reopen plan",
    )
    gel = _typed_json(request.gel_evidence, GelEvidenceManifest, "gel evidence")
    preflights = _typed_jsonl(
        request.preflight_jsonl, MtzPreflightRecord, "MTZ preflight"
    )
    crystal_id = parents[0].crystal_id
    matching_preflight = tuple(
        item for item in preflights if item.crystal_id == crystal_id
    )
    if len(matching_preflight) != 1:
        raise CompositionDepthInputError("parent crystal lacks one MTZ preflight")
    contexts = tuple(
        ParentMatthewsContext(
            parent_state_id=state.state_id,
            asu_volume_a3=matching_preflight[0].asu_volume_a3,
            minimum_solvent_fraction=0.45,
            maximum_solvent_fraction=0.75,
            source_evidence_sha256=sha256_file(request.preflight_jsonl),
        )
        for state in parents
    )
    model_evidence = _typed_jsonl(
        request.model_ranking_evidence_jsonl,
        ParentModelRankingEvidence,
        "model-ranking evidence",
    )
    generation = build_component_expansion_inputs(
        parents=parent_inputs,
        sequence_groups=groups,
        localisation_policy=policy,
        active_wave_completion=completion,
        localisation_reopen_plan=reopen,
        gel_evidence=gel,
        matthews_contexts=contexts,
        model_registry_json=request.model_registry,
        model_ranking_evidence=model_evidence,
    )
    unbound = generation.as_request().model_copy(
        update={
            "per_depth_attempt_budget": request.per_depth_attempt_budget,
            "global_attempts_used_before": request.global_attempts_used_before,
        }
    )
    planned = build_registry_bound_composition_expansion_plan(
        CompositionExpansionRequest.model_validate(unbound),
        model_registry_json=request.model_registry,
    )
    try:
        registry_path = request.model_registry.resolve(strict=True)
        registry = load_all_eligible_model_registry(registry_path)
    except (AllEligibleModelRegistryError, OSError) as error:
        raise CompositionDepthInputError("all-model registry is invalid") from error
    selection = _typed_json(
        request.diffraction_selection,
        DiffractionSelection,
        "diffraction selection",
    )
    free_r = _typed_json(request.free_r_identity, FreeRIdentity, "Free-R identity")
    fixed_root = request.fixed_coordinate_root.resolve(strict=True)
    if request.fixed_coordinate_root.is_symlink() or not fixed_root.is_dir():
        raise CompositionDepthInputError("fixed-coordinate root is invalid")
    execution_inputs, resource_plans = _execution_inputs(
        parents=parent_inputs,
        depth_plan=planned.depth_plan,
        selected_attempts=planned.selected_attempts,
        registry=registry,
        registry_root=registry_path.parent,
        fixed_root=fixed_root,
        selection=selection,
        free_r=free_r,
        preflight=matching_preflight[0],
    )
    inventory = build_composition_attempt_inventory(
        depth_plan=planned.depth_plan,
        planned_attempts=planned.selected_attempts,
        parent_states=parents,
        diffraction_selection=selection,
        free_r_identity=free_r,
        execution_identity_id=identity.execution_identity_id,
        execution_inputs=execution_inputs,
        resource_plans=resource_plans,
    )
    output = request.output_directory.resolve()
    if output.exists() or output.is_symlink():
        raise CompositionDepthInputError("composition-depth output must be absent")
    output.mkdir(parents=True)
    candidate_path = output / "component_candidate_inventory.json"
    atomic_write_json(candidate_path, generation.inventory.model_dump(mode="json"))
    depth_plan_path = output / "composition_depth_plan.json"
    atomic_write_json(depth_plan_path, planned.depth_plan.model_dump(mode="json"))
    parent_path = output / "parent_states.jsonl"
    atomic_write_text(
        parent_path,
        "".join(f"{canonical_json_text(state)}\n" for state in parents),
    )
    attempt_path = write_composition_attempt_inventory(
        inventory,
        output / "composition_attempt_inventory.json",
    )
    manifest = output / "composition_depth_input_manifest.json"
    atomic_write_json(
        manifest,
        {
            "schema_version": "2.0",
            "adapter_version": _ADAPTER_VERSION,
            "crystal_id": crystal_id,
            "parent_depth": parents[0].depth,
            "target_depth": parents[0].depth + 1,
            "candidate_inventory_id": generation.inventory.inventory_id,
            "depth_plan_id": planned.depth_plan.depth_plan_id,
            "attempt_inventory_id": inventory.inventory_id,
            "finding_closure_id": closure.closure_id,
            "attempt_count": inventory.attempt_count,
            "global_attempts_used_before": request.global_attempts_used_before,
            "per_depth_attempt_budget": request.per_depth_attempt_budget,
        },
    )
    checksums = output / "composition_depth_input_checksums.sha256"
    files = (candidate_path, depth_plan_path, parent_path, attempt_path, manifest)
    atomic_write_text(
        checksums,
        "".join(
            f"{sha256_file(path)}  {path.relative_to(output).as_posix()}\n"
            for path in files
        ),
    )
    return CompositionDepthInputOutput(
        attempt_inventory=attempt_path,
        candidate_inventory=candidate_path,
        depth_plan=depth_plan_path,
        checksums=checksums,
        attempt_count=inventory.attempt_count,
    )


__all__ = [
    "CompositionDepthInputError",
    "CompositionDepthInputOutput",
    "CompositionDepthInputRequest",
    "build_composition_depth_inputs",
]
