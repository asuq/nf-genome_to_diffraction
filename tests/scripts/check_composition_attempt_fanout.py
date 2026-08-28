"""Exercise the Phase III complete-item composition stub and cached resume."""

import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from genome_to_diffraction.execution import (
    build_composition_attempt_inventory,
    write_composition_attempt_inventory,
)
from genome_to_diffraction.ranking.composition import (
    ComponentExpansionInput,
    CompositionExpansionOutput,
    CompositionExpansionRequest,
    ParentExpansionInput,
    build_composition_expansion_plan,
)
from genome_to_diffraction.schemas.v2 import (
    ComponentExpansionExecutionInput,
    ComponentIdentitySupport,
    ComponentPlacement,
    ComponentSpec,
    CompositionAttemptInventory,
    CompositionAttemptInventoryStatus,
    CompositionState,
    CompositionSupportState,
    DiffractionSelection,
    DiffractionValueSource,
    FreeRConventionStatus,
    FreeRDistributionSummary,
    FreeRFlagCount,
    FreeRIdentity,
    ModelUnavailableReason,
    RegistryModelResolution,
    RegistryModelResolutionScope,
    diffraction_dataset_id,
)
from genome_to_diffraction.schemas.v2.component_execution_input import (
    FixedComponentExecutionEvidence,
)
from genome_to_diffraction.status import ExecutionStatus

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURE = REPOSITORY / "tests/fixtures/stubs/composition_attempt_fanout"
CRYSTAL_ID = "composition_fanout_crystal"


def _sha(index: int) -> str:
    return f"{index:064x}"


MTZ_SHA256 = _sha(501)
DIFFRACTION_DATASET_ID = diffraction_dataset_id(
    crystal_id=CRYSTAL_ID,
    mtz_sha256=MTZ_SHA256,
)
MODEL_REGISTRY_ID = f"allmodelreg_{_sha(502)}"
EXECUTION_IDENTITY_ID = f"phase3exec_{_sha(503)}"


def _component_specs(
    *,
    label: str,
    sequence_index: int,
    model_index: int,
) -> tuple[ComponentSpec, ...]:
    sequence_sha256 = _sha(sequence_index)
    return tuple(
        ComponentSpec.from_content(
            label=label,
            sequence_group_id=f"seq_{sequence_sha256}",
            sequence_sha256=sequence_sha256,
            model_id=f"model_{model_index}",
            model_sha256=_sha(model_index),
            requested_copy_count=copy_count,
            sequence_mass_da=20_000.0 + sequence_index,
            mass_evidence_sha256=_sha(600 + sequence_index),
            model_evidence_sha256=_sha(700 + model_index),
        )
        for copy_count in range(1, 5)
    )


def _available_resolution(
    *,
    scope: RegistryModelResolutionScope,
    parent_state_id: str,
    parent_rank: int,
    component: ComponentSpec,
    candidate_rank: int | None = None,
) -> RegistryModelResolution:
    return RegistryModelResolution.from_content(
        model_registry_id=MODEL_REGISTRY_ID,
        scope=scope,
        parent_state_id=parent_state_id,
        parent_rank=parent_rank,
        candidate_rank=candidate_rank,
        component_spec_id=component.component_spec_id,
        requested_copy_count=component.requested_copy_count,
        sequence_group_id=component.sequence_group_id,
        sequence_sha256=component.sequence_sha256,
        model_id=component.model_id,
        model_sha256=component.model_sha256,
        registry_entry_sha256=_sha(800 + parent_rank + (candidate_rank or 0)),
        resolved_provider="synthetic",
        resolved_variant_type="processed",
    )


def _parent(rank: int) -> ParentExpansionInput:
    component = _component_specs(
        label="A",
        sequence_index=1,
        model_index=10 + rank,
    )[rank - 1]
    placement = ComponentPlacement.from_content(
        component_spec_id=component.component_spec_id,
        component_label=component.label,
        sequence_group_id=component.sequence_group_id,
        model_id=component.model_id,
        model_sha256=component.model_sha256,
        requested_copy_count=component.requested_copy_count,
        observed_copy_count=component.requested_copy_count,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        component_tfz=10.0 + rank,
        incremental_llg=100.0 + rank,
        packing_passed=True,
        coordinate_sha256=_sha(900 + rank),
        identity_support=ComponentIdentitySupport.UNRESOLVED,
    )
    state = CompositionState.from_content(
        crystal_id=CRYSTAL_ID,
        diffraction_dataset_id=DIFFRACTION_DATASET_ID,
        diffraction_sha256=MTZ_SHA256,
        parent_state_id=None,
        depth=1,
        components=(component,),
        placements=(placement,),
        combined_coordinate_sha256=_sha(900 + rank),
        physical_mass_lower_da=10_000.0,
        physical_mass_upper_da=100_000.0,
        support_state=CompositionSupportState.PACKED,
    )
    return ParentExpansionInput(
        parent_rank=rank,
        state=state,
        model_resolutions=(
            _available_resolution(
                scope=RegistryModelResolutionScope.PARENT_COMPONENT,
                parent_state_id=state.state_id,
                parent_rank=rank,
                component=component,
            ),
        ),
    )


def _candidate(
    *,
    parent: ParentExpansionInput,
    rank: int,
    sequence_index: int,
    model_available: bool = True,
) -> ComponentExpansionInput:
    components = _component_specs(
        label="B",
        sequence_index=sequence_index,
        model_index=100 + sequence_index,
    )
    resolutions = tuple(
        _available_resolution(
            scope=RegistryModelResolutionScope.CANDIDATE_COPY,
            parent_state_id=parent.state.state_id,
            parent_rank=parent.parent_rank,
            candidate_rank=rank,
            component=component,
        )
        if model_available
        else RegistryModelResolution.from_content(
            model_registry_id=MODEL_REGISTRY_ID,
            scope=RegistryModelResolutionScope.CANDIDATE_COPY,
            parent_state_id=parent.state.state_id,
            parent_rank=parent.parent_rank,
            candidate_rank=rank,
            component_spec_id=component.component_spec_id,
            requested_copy_count=component.requested_copy_count,
            sequence_group_id=component.sequence_group_id,
            sequence_sha256=component.sequence_sha256,
            model_id=component.model_id,
            model_sha256=component.model_sha256,
            unavailable_reason=ModelUnavailableReason.NO_ELIGIBLE_MODEL,
        )
        for component in components
    )
    return ComponentExpansionInput(
        parent_state_id=parent.state.state_id,
        candidate_rank=rank,
        component_specs=components,
        physically_eligible_copy_counts=(1, 2, 3, 4),
        model_available=model_available,
        model_resolutions=resolutions,
    )


def _selection() -> DiffractionSelection:
    return DiffractionSelection.from_content(
        crystal_id=CRYSTAL_ID,
        diffraction_dataset_id=DIFFRACTION_DATASET_ID,
        mtz_sha256=MTZ_SHA256,
        preflight_id="preflight_composition_fanout",
        preflight_record_sha256=_sha(1001),
        crystal_manifest_sha256=_sha(1002),
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
    )


def _free_r(selection: DiffractionSelection) -> FreeRIdentity:
    return FreeRIdentity.from_content(
        diffraction_selection_id=selection.diffraction_selection_id,
        diffraction_dataset_id=selection.diffraction_dataset_id,
        crystal_id=selection.crystal_id,
        mtz_sha256=selection.mtz_sha256,
        observation_dataset_id=selection.observation_dataset_id,
        free_r_dataset_id=selection.observation_dataset_id,
        free_r_label="FreeR_flag",
        distribution=FreeRDistributionSummary(
            reflection_count=100,
            distinct_flag_values=2,
            flag_counts=(
                FreeRFlagCount(flag_value=0, reflection_count=95),
                FreeRFlagCount(flag_value=1, reflection_count=5),
            ),
        ),
        hkl_set_sha256=_sha(1003),
        hkl_to_flag_membership_sha256=_sha(1004),
        convention_status=FreeRConventionStatus.UNRESOLVED,
    )


def _inventory(*, no_model: bool = False) -> CompositionAttemptInventory:
    parents = tuple(_parent(rank) for rank in range(1, 4))
    candidates = (
        (
            _candidate(
                parent=parents[0],
                rank=1,
                sequence_index=11,
                model_available=False,
            ),
        )
        if no_model
        else tuple(
            _candidate(
                parent=parent,
                rank=rank,
                sequence_index=parent.parent_rank * 10 + rank,
            )
            for parent in parents
            for rank in range(1, 4)
        )
    )
    active_parents = (parents[0],) if no_model else parents
    output = build_composition_expansion_plan(
        CompositionExpansionRequest(
            parents=active_parents,
            candidates=candidates,
            model_registry_id=MODEL_REGISTRY_ID,
        )
    )
    selection = _selection()
    free_r = _free_r(selection)
    execution_inputs = _execution_inputs(
        output=output,
        parents=active_parents,
        selection=selection,
        free_r=free_r,
    )
    return build_composition_attempt_inventory(
        depth_plan=output.depth_plan,
        planned_attempts=output.selected_attempts,
        parent_states=tuple(parent.state for parent in active_parents),
        diffraction_selection=selection,
        free_r_identity=free_r,
        execution_identity_id=EXECUTION_IDENTITY_ID,
        execution_inputs=execution_inputs,
    )


def _execution_inputs(
    *,
    output: CompositionExpansionOutput,
    parents: tuple[ParentExpansionInput, ...],
    selection: DiffractionSelection,
    free_r: FreeRIdentity,
) -> tuple[ComponentExpansionExecutionInput, ...]:
    depth_plan = output.depth_plan
    state_by_id = {parent.state.state_id: parent.state for parent in parents}
    candidate_by_id = {
        candidate.depth_candidate_id: candidate for candidate in depth_plan.candidates
    }
    resolution_by_key = {
        (resolution.parent_state_id, resolution.component_spec_id): resolution
        for resolution in depth_plan.model_resolutions
    }
    inputs: list[ComponentExpansionExecutionInput] = []
    for attempt in output.selected_attempts:
        state = state_by_id[attempt.parent_state_id]
        candidate = candidate_by_id[attempt.depth_candidate_id]
        fixed = tuple(
            FixedComponentExecutionEvidence.from_content(
                parent_state_id=state.state_id,
                component_spec_id=component.component_spec_id,
                placement_id=placement.placement_id,
                fixed_coordinate_sha256=placement.coordinate_sha256,
                source_parent_combined_coordinate_sha256=(
                    state.combined_coordinate_sha256
                ),
                coordinate_derivation_evidence_sha256=_sha(1100 + index),
                phaser_identity_fraction=0.35 + index / 10,
                model_uncertainty_source="synthetic reviewed model identity",
                model_uncertainty_evidence_sha256=(component.model_evidence_sha256),
            )
            for index, (component, placement) in enumerate(
                zip(state.components, state.placements, strict=True)
            )
        )
        component = candidate.hypothesis.component
        inputs.append(
            ComponentExpansionExecutionInput.from_content(
                depth_plan_id=depth_plan.depth_plan_id,
                selected_candidate=candidate,
                parent_state=state,
                fixed_components=fixed,
                candidate_model_resolution=resolution_by_key[
                    (state.state_id, component.component_spec_id)
                ],
                candidate_phaser_identity_fraction=0.8,
                candidate_model_uncertainty_source=(
                    "synthetic candidate model identity"
                ),
                candidate_model_uncertainty_evidence_sha256=(
                    component.model_evidence_sha256
                ),
                diffraction_selection=selection,
                free_r_identity=free_r,
                parent_combined_llg=1000.0,
                parent_score_evidence_sha256=_sha(1200 + attempt.allocation_rank),
            )
        )
    return tuple(inputs)


def _environment(nxf_home: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "NXF_AGENT_MODE": "true",
            "NXF_ANSI_LOG": "false",
            "NXF_DISABLE_CHECK_LATEST": "true",
            "NXF_HOME": str(nxf_home),
            "NXF_SYNTAX_PARSER": "v2",
        }
    )
    return environment


def _run(
    command: Sequence[str],
    environment: dict[str, str],
    *,
    retry_nextflow_concurrent_modification: bool = False,
) -> subprocess.CompletedProcess[str]:
    for attempt in range(2):
        result = subprocess.run(
            command,
            cwd=REPOSITORY,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if result.returncode == 0:
            return result
        combined = f"{result.stdout}\n{result.stderr}"
        if (
            attempt == 0
            and retry_nextflow_concurrent_modification
            and "java.util.ConcurrentModificationException" in combined
        ):
            continue
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{combined}"
        )
    raise AssertionError("bounded Nextflow retry loop did not return")


def _read_trace(path: Path) -> tuple[dict[str, str], ...]:
    if not path.is_file():
        return ()
    with path.open(encoding="utf-8", newline="") as handle:
        return tuple(csv.DictReader(handle, delimiter="\t"))


def _output_digests(output: Path) -> dict[str, str]:
    return {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file() and "pipeline_info" not in path.parts
    }


def _runtime_stubs(root: Path) -> Path:
    artifacts = root / "runtime-artifacts"
    (artifacts / "fixed-coordinates").mkdir(parents=True)
    (artifacts / "model-registry").mkdir()
    for name in (
        "sequence_groups.jsonl",
        "preflight.jsonl",
        "input.mtz",
        "phenix.json",
        "execution_identity.json",
    ):
        (artifacts / name).write_text(f"stub:{name}\n", encoding="ascii")
    return artifacts


def _command(
    *,
    inventory: Path,
    output: Path,
    cache: Path,
    artifacts: Path,
) -> list[str]:
    return [
        "nextflow",
        "-C",
        "tests/fixtures/stubs/composition_attempt_fanout/nextflow.config",
        "run",
        "tests/fixtures/stubs/composition_attempt_fanout/main.nf",
        "-stub-run",
        "--attempt_inventory",
        str(inventory),
        "--fixed_coordinate_root",
        str(artifacts / "fixed-coordinates"),
        "--model_registry",
        str(artifacts / "model-registry"),
        "--sequence_groups",
        str(artifacts / "sequence_groups.jsonl"),
        "--preflight",
        str(artifacts / "preflight.jsonl"),
        "--mtz",
        str(artifacts / "input.mtz"),
        "--phenix_manifest",
        str(artifacts / "phenix.json"),
        "--execution_identity",
        str(artifacts / "execution_identity.json"),
        "--outdir",
        str(output),
        "--cache_root",
        str(cache),
    ]


def _check_ready(root: Path, environment: dict[str, str]) -> None:
    inventory = _inventory()
    if (
        inventory.status is not CompositionAttemptInventoryStatus.READY
        or inventory.depth_plan.selected_attempt_count != 25
        or inventory.attempt_count != 25
        or len({task.parent_state_id for task in inventory.attempts}) != 3
    ):
        raise RuntimeError("synthetic shared-depth inventory is not exactly 25 tasks")
    inventory_path = write_composition_attempt_inventory(
        inventory,
        root / "ready/composition_attempt_inventory.json",
    )
    output = root / "ready-results"
    artifacts = _runtime_stubs(root)
    command = _command(
        inventory=inventory_path,
        output=output,
        cache=root / "ready-cache",
        artifacts=artifacts,
    )
    _run(command, environment)

    trace_path = output / "pipeline_info/trace.tsv"
    first_rows = _read_trace(trace_path)
    expected_process = "RUN_PHASE3_COMPOSITION_ATTEMPT"
    actual_processes = Counter(row["process"].split(":")[-1] for row in first_rows)
    if actual_processes != Counter({expected_process: 25}):
        raise RuntimeError(
            "composition stub scheduled the wrong exact task count: "
            f"{dict(actual_processes)}"
        )
    if {row["status"] for row in first_rows} != {"COMPLETED"}:
        raise RuntimeError("composition stub did not complete all 25 tasks")
    expected_tags = {
        f"composition-attempt:{task.attempt_id}" for task in inventory.attempts
    }
    task_rows = {
        row["tag"]: row["hash"]
        for row in first_rows
        if row["process"].split(":")[-1] == expected_process
    }
    if set(task_rows) != expected_tags or len(set(task_rows.values())) != 25:
        raise RuntimeError("composition stub task identities are incomplete")

    source_bytes = inventory_path.read_bytes()
    for task in inventory.attempts:
        bundle = output / f"composition_attempt_{task.attempt_id}"
        retained = bundle / "composition_attempt_inventory.json"
        stub = json.loads(
            (bundle / "composition_attempt_stub.json").read_text(encoding="utf-8")
        )
        if retained.read_bytes() != source_bytes:
            raise RuntimeError(f"complete inventory changed for {task.attempt_id}")
        if (
            stub.get("attempt_id") != task.attempt_id
            or stub.get("allocation_rank") != task.allocation_rank
            or stub.get("depth_plan_id") != task.depth_plan_id
            or stub.get("parent_state_id") != task.parent_state_id
            or stub.get("depth_candidate_id") != task.depth_candidate_id
            or stub.get("component_execution_input_id")
            != task.component_execution_input_id
            or stub.get("candidate_model_resolution_id")
            != task.candidate_model_resolution_id
            or stub.get("diffraction_selection_id") != task.diffraction_selection_id
            or stub.get("free_r_identity_id") != task.free_r_identity_id
            or stub.get("model_registry_id") != task.model_registry_id
            or stub.get("execution_status") != "stub_not_executed"
        ):
            raise RuntimeError(f"stub identity changed for {task.attempt_id}")

    before_resume = _output_digests(output)
    first_identities = {(row["process"], row["tag"]): row["hash"] for row in first_rows}
    resume_command = [*command[:5], "-resume", *command[5:]]
    _run(
        resume_command,
        environment,
        retry_nextflow_concurrent_modification=True,
    )
    resumed_rows = _read_trace(trace_path)
    if Counter(row["process"].split(":")[-1] for row in resumed_rows) != Counter(
        {expected_process: 25}
    ) or {row["status"] for row in resumed_rows} != {"CACHED"}:
        raise RuntimeError("cached resume did not reuse all 25 composition tasks")
    resumed_identities = {
        (row["process"], row["tag"]): row["hash"] for row in resumed_rows
    }
    if resumed_identities != first_identities:
        raise RuntimeError("cached resume changed exact composition task identities")
    if _output_digests(output) != before_resume:
        raise RuntimeError("cached resume changed retained composition evidence")


def _check_no_model(root: Path, environment: dict[str, str]) -> None:
    inventory = _inventory(no_model=True)
    if (
        inventory.status is not CompositionAttemptInventoryStatus.EMPTY_NO_MODEL
        or inventory.attempt_count != 0
        or inventory.unsearchable_no_model_count != 4
        or inventory.attempts
    ):
        raise RuntimeError("no-model inventory did not remain a typed empty path")
    inventory_path = write_composition_attempt_inventory(
        inventory,
        root / "no-model/composition_attempt_inventory.json",
    )
    output = root / "no-model-results"
    _run(
        _command(
            inventory=inventory_path,
            output=output,
            cache=root / "no-model-cache",
            artifacts=root / "runtime-artifacts",
        ),
        environment,
    )
    rows = _read_trace(output / "pipeline_info/trace.tsv")
    if rows or tuple(output.glob("composition_attempt_*")):
        raise RuntimeError("typed no-model inventory scheduled an execution task")


def main() -> int:
    """Require exact complete-item fan-out, typed empty, and cached resume."""

    with tempfile.TemporaryDirectory(
        prefix="nf-genome-to-diffraction-composition-fanout-",
        dir="/tmp",
    ) as temporary:
        root = Path(temporary)
        environment = _environment(root / "nxf-home")
        _check_ready(root, environment)
        _check_no_model(root, environment)
    print("Composition complete-item fan-out and cached resume passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
