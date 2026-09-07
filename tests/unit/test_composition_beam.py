"""Focused tests for deterministic Phase III depth collection."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.execution import (
    CompositionBeamCollectionRequest,
    CompositionBeamDepthStatus,
    collect_composition_beam_depth,
    write_composition_attempt_inventory,
)
from genome_to_diffraction.execution.composition_beam import CompositionBeamError
from genome_to_diffraction.execution.composition_runtime import (
    CompositionAttemptExecutionResult,
)
from genome_to_diffraction.execution.composition_task_evidence import (
    CompositionTaskEvidenceError,
)
from genome_to_diffraction.review import build_pass2_review_packages
from genome_to_diffraction.schemas.v2 import (
    ComponentExpansionScoreEvidence,
    CompositionState,
    CompositionStopReason,
    CompositionSupportState,
    PhaserPerPlacementInventory,
    PhaserPlacementArtifact,
    PhaserPlacementComponentGroup,
)
from genome_to_diffraction.status import ExecutionStatus
from tests.unit import test_composition_attempt_inventory as inventory_fixture
from tests.unit.test_composition_runtime import _request


def _write_attempt_checksums(root: Path) -> Path:
    path = root / "composition_attempt_checksums.sha256"
    files = tuple(
        sorted(
            (item for item in root.rglob("*") if item.is_file() and item != path),
            key=lambda item: item.relative_to(root).as_posix(),
        )
    )
    atomic_write_text(
        path,
        "".join(
            f"{sha256_file(item)}  {item.relative_to(root).as_posix()}\n"
            for item in files
        ),
    )
    return path


def _packed_attempt(
    root: Path, inventory, *, index: int = 0, llg: float = 1150.0, tfz: float = 14.0
) -> Path:
    task = inventory.attempts[index]
    execution_input = next(
        item
        for item in inventory.execution_inputs
        if item.execution_input_id == task.component_execution_input_id
    )
    parent = execution_input.parent_state
    candidate = execution_input.selected_candidate.hypothesis.component
    root.mkdir()
    search = root / "search"
    search.mkdir()
    result_record = search / "component_search_result.json"
    atomic_write_json(result_record, {"execution_status": "completed_hit"})
    command = search / "phaser_command.json"
    atomic_write_json(command, {"schema_version": "2.0"})
    solution = search / "PHASER.sol"
    solution.write_text("SOLU SET\n", encoding="ascii")
    combined = search / "PHASER.1.pdb"
    combined.write_text("ATOM COMBINED\n", encoding="ascii")
    combined_sha = sha256_file(combined)

    placements = []
    groups = []
    ordinal = 1
    for component in (*parent.components, candidate):
        coordinate = search / f"component_{component.label}.pdb"
        coordinate.write_text(f"ATOM COMPONENT {component.label}\n", encoding="ascii")
        coordinate_sha = sha256_file(coordinate)
        ordinals = tuple(range(ordinal, ordinal + component.requested_copy_count))
        placements.extend(
            PhaserPlacementArtifact.from_content(
                solution_number=1,
                placement_ordinal=value,
                ensemble_id=f"ensemble_{component.label}",
                component_label=component.label,
                solu_6dim_line_sha256=f"{1000 + value:064x}",
                coordinate_path=coordinate.name,
                coordinate_sha256=coordinate_sha,
            )
            for value in ordinals
        )
        groups.append(
            PhaserPlacementComponentGroup.from_content(
                component_label=component.label,
                ensemble_id=f"ensemble_{component.label}",
                expected_copy_count=component.requested_copy_count,
                observed_copy_count=component.requested_copy_count,
                placement_ordinals=ordinals,
                combined_chain_ids=tuple(
                    f"{component.label}{index}"
                    for index in range(1, component.requested_copy_count + 1)
                ),
                source_model_sha256=component.model_sha256,
                source_model_polymer_sha256=f"{2000 + ordinal:064x}",
                coordinate_path=coordinate.name,
                coordinate_sha256=coordinate_sha,
                atom_count=component.requested_copy_count,
            )
        )
        ordinal += component.requested_copy_count
    placement_inventory = PhaserPerPlacementInventory.from_content(
        adapter_version="phaser-component-coordinate-inventory-v2",
        crystal_id=parent.crystal_id,
        search_id="beam_search",
        phaser_version="test",
        solution_number=1,
        command_record_sha256=sha256_file(command),
        result_record_sha256=sha256_file(result_record),
        solution_file_path="PHASER.sol",
        solution_file_sha256=sha256_file(solution),
        combined_coordinate_path="PHASER.1.pdb",
        combined_coordinate_sha256=combined_sha,
        output_command_binding=(
            "phaser.keywords.general.xyzout=True;"
            "phaser.keywords.general.xyzout_ensemble=True;"
            "phaser.keywords.general.keywords=True"
        ),
        placements=tuple(placements),
        component_groups=tuple(groups),
        combined_atom_count=len(placements),
        recombined_atom_count=len(placements),
        recombined_atom_sha256="3" * 64,
        ordinal_mapping_status="verified_exact_sol_to_model_bound_chains",
        recombination_status="verified_exact_combined_atom_partition",
        can_create_fixed_component_evidence=True,
    )
    placement_path = search / "phaser_per_placement_inventory.json"
    atomic_write_json(placement_path, placement_inventory.model_dump(mode="json"))
    score = ComponentExpansionScoreEvidence.from_observed(
        execution_input=execution_input,
        placement_inventory=placement_inventory,
        score_ensemble_id=f"ensemble_{candidate.label}",
        combined_llg=llg,
        component_tfz=tfz,
        packing_passed=True,
    )
    score_path = root / "component_score_evidence.json"
    atomic_write_json(score_path, score.model_dump(mode="json"))
    output_mtz = search / "PHASER.1.mtz"
    output_mtz.write_bytes(b"derived MTZ\n")
    candidate_mass = float(candidate.sequence_mass_da or 0) * (
        candidate.requested_copy_count
    )
    child = CompositionState.from_content(
        crystal_id=parent.crystal_id,
        diffraction_dataset_id=parent.diffraction_dataset_id,
        diffraction_sha256=parent.diffraction_sha256,
        parent_state_id=parent.state_id,
        depth=2,
        components=(*parent.components, candidate),
        placements=(*parent.placements, score.placement),
        combined_coordinate_sha256=combined_sha,
        combined_mtz_sha256=sha256_file(output_mtz),
        physical_mass_lower_da=parent.physical_mass_lower_da + candidate_mass,
        physical_mass_upper_da=parent.physical_mass_upper_da + candidate_mass,
        support_state=CompositionSupportState.PACKED,
    )
    child_path = root / "composition_state.json"
    atomic_write_json(child_path, child.model_dump(mode="json"))
    free_r = root / "free_r_membership.json"
    atomic_write_json(free_r, {"comparison_id": "freercompare_test"})
    result = CompositionAttemptExecutionResult.from_content(
        attempt_id=task.attempt_id,
        resource_plan_id=task.resource_plan.resource_plan_id,
        resource_attempt=1,
        execution_input_id=execution_input.execution_input_id,
        crystal_id=parent.crystal_id,
        parent_state_id=parent.state_id,
        candidate_component_spec_id=candidate.component_spec_id,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        search_result_sha256=sha256_file(result_record),
        placement_inventory_sha256=sha256_file(placement_path),
        score_evidence_id=score.score_evidence_id,
        score_evidence_sha256=sha256_file(score_path),
        child_state_id=child.state_id,
        child_state_sha256=sha256_file(child_path),
        free_r_comparison_id="freercompare_test",
        free_r_comparison_sha256=sha256_file(free_r),
        child_support_state=child.support_state,
    )
    atomic_write_json(
        root / "composition_attempt_execution.json",
        result.model_dump(mode="json"),
    )
    _write_attempt_checksums(root)
    return root


def _no_hit_attempt(
    root: Path,
    inventory,
    task,
    *,
    status: ExecutionStatus = ExecutionStatus.COMPLETED_NO_HIT,
) -> Path:
    execution_input = next(
        item
        for item in inventory.execution_inputs
        if item.execution_input_id == task.component_execution_input_id
    )
    root.mkdir()
    search = root / "component_search_result.json"
    atomic_write_json(search, {"execution_status": status.value})
    result = CompositionAttemptExecutionResult.from_content(
        attempt_id=task.attempt_id,
        resource_plan_id=task.resource_plan.resource_plan_id,
        resource_attempt=1,
        execution_input_id=execution_input.execution_input_id,
        crystal_id=execution_input.parent_state.crystal_id,
        parent_state_id=execution_input.parent_state.state_id,
        candidate_component_spec_id=(
            execution_input.selected_candidate.hypothesis.component.component_spec_id
        ),
        execution_status=status,
        search_result_sha256=sha256_file(search),
    )
    atomic_write_json(
        root / "composition_attempt_execution.json",
        result.model_dump(mode="json"),
    )
    _write_attempt_checksums(root)
    return root


def test_no_hit_depth_retains_attempt_and_stops_without_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_request, inventory = _request(
        tmp_path,
        monkeypatch,
        status=ExecutionStatus.COMPLETED_NO_HIT,
    )
    attempts = tuple(
        _no_hit_attempt(tmp_path / f"attempt-{index}", inventory, task)
        for index, task in enumerate(inventory.attempts, start=1)
    )

    output = collect_composition_beam_depth(
        CompositionBeamCollectionRequest(
            attempt_inventory=runtime_request.attempt_inventory,
            attempt_result_directories=attempts,
            output_directory=tmp_path / "beam",
            fixed_coordinate_root=runtime_request.fixed_coordinate_root,
        )
    )

    assert output.result.status is CompositionBeamDepthStatus.TERMINAL
    assert output.result.stop_reason is CompositionStopReason.NO_RETAINED_PACKED_STATE
    assert output.result.retained_parent_count == 0
    assert output.result.attempt_count == inventory.attempt_count
    assert output.retained_states_jsonl.read_text() == ""
    scope = output.scope_decisions_jsonl.read_text()
    assessment = output.assessments_jsonl.read_text()
    assert '"stop_reason":"no_retained_packed_state"' in scope
    assert '"scientific_status":"search_evidence_only"' in assessment
    assert '"complete_composition_claimed":false' in assessment
    packages = build_pass2_review_packages(
        beam_directory=output.result_json.parent,
        execution_identity=runtime_request.execution_identity,
        owned_parent_run_id=(
            "gtd-unknown-pass2-20260828T000000Z-aaaaaaaaaaaa-bbbbbbbb"
        ),
        crystal_id=inventory.depth_plan.crystal_id,
        output_directory=tmp_path / "review-packages",
    )
    assert packages.composition.manifest.is_file()
    assert packages.sequence.manifest.is_file()


def test_packed_depth_publishes_one_claim_free_next_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_request, inventory = _request(
        tmp_path,
        monkeypatch,
        status=ExecutionStatus.COMPLETED_NO_HIT,
    )
    attempt_root = _packed_attempt(tmp_path / "packed-attempt", inventory)
    attempts = (
        attempt_root,
        *(
            _no_hit_attempt(tmp_path / f"no-hit-{index}", inventory, task)
            for index, task in enumerate(inventory.attempts[1:], start=1)
        ),
    )

    output = collect_composition_beam_depth(
        CompositionBeamCollectionRequest(
            attempt_inventory=runtime_request.attempt_inventory,
            attempt_result_directories=attempts,
            output_directory=tmp_path / "beam",
            fixed_coordinate_root=runtime_request.fixed_coordinate_root,
        )
    )

    assert output.result.status is CompositionBeamDepthStatus.READY_NEXT_DEPTH
    assert output.result.stop_reason is None
    assert output.result.retained_parent_count == 1
    assert output.result.global_attempts_used_after == inventory.attempt_count
    assert "composition_supported" not in output.retained_states_jsonl.read_text()


@pytest.mark.parametrize(
    "status", [ExecutionStatus.FAILED_TOOL_EXECUTION, ExecutionStatus.FAILED_PARSE]
)
def test_all_failures_are_incomplete_and_preserve_parent_assets(
    tmp_path, monkeypatch, status
):
    request, inventory = _request(
        tmp_path, monkeypatch, status=ExecutionStatus.COMPLETED_NO_HIT
    )
    attempts = tuple(
        _no_hit_attempt(tmp_path / f"failure-{index}", inventory, task, status=status)
        for index, task in enumerate(inventory.attempts)
    )
    output = collect_composition_beam_depth(
        CompositionBeamCollectionRequest(
            attempt_inventory=request.attempt_inventory,
            attempt_result_directories=attempts,
            output_directory=tmp_path / "beam",
            fixed_coordinate_root=request.fixed_coordinate_root,
        )
    )
    assert output.result.failed_count == inventory.attempt_count
    assert output.result.completed_no_hit_count == 0
    assert not output.result.depth_complete
    assert (
        output.result.stop_reason is CompositionStopReason.COMPOSITION_DEPTH_INCOMPLETE
    )
    assessment = json.loads(output.assessments_jsonl.read_text())
    assert assessment["execution_status"] == status.value
    assert assessment["scientific_status"] == "execution_failure"
    parent = inventory.parent_states[0]
    assert (
        sha256_file(
            output.result_json.parent
            / "parent_evidence"
            / parent.state_id
            / "combined.pdb"
        )
        == parent.combined_coordinate_sha256
    )


def test_partial_native_inventory_retains_child_but_blocks_advancement(
    tmp_path, monkeypatch
):
    request, inventory = _request(
        tmp_path, monkeypatch, status=ExecutionStatus.COMPLETED_NO_HIT
    )
    hit = _packed_attempt(tmp_path / "hit", inventory)
    output = collect_composition_beam_depth(
        CompositionBeamCollectionRequest(
            attempt_inventory=request.attempt_inventory,
            attempt_result_directories=(hit,),
            output_directory=tmp_path / "beam",
            fixed_coordinate_root=request.fixed_coordinate_root,
        )
    )
    assert output.result.completed_hit_count == 1
    assert output.result.missing_output_count == inventory.attempt_count - 1
    assert output.result.retained_parent_count == 1
    assert output.result.status is CompositionBeamDepthStatus.TERMINAL
    assert not output.result.depth_complete
    states = [
        json.loads(line)
        for line in (output.result_json.parent / "terminal_review_states.jsonl")
        .read_text()
        .splitlines()
    ]
    assert len(states) == 2
    assert {row["state_id"] for row in states} >= {inventory.parent_states[0].state_id}
    missing = output.result.attempts[1]
    assert missing.execution_status is None
    assert missing.result_sha256 is None


def test_zero_scores_rank_above_negative_scores(tmp_path, monkeypatch):
    request, inventory = _request(
        tmp_path, monkeypatch, status=ExecutionStatus.COMPLETED_NO_HIT
    )
    attempts = (
        _packed_attempt(tmp_path / "negative", inventory, index=0, llg=-1.0, tfz=1.0),
        _packed_attempt(tmp_path / "zero", inventory, index=1, llg=0.0, tfz=0.0),
        *(
            _no_hit_attempt(tmp_path / f"no-hit-{index}", inventory, task)
            for index, task in enumerate(inventory.attempts[2:])
        ),
    )
    output = collect_composition_beam_depth(
        CompositionBeamCollectionRequest(
            attempt_inventory=request.attempt_inventory,
            attempt_result_directories=attempts,
            output_directory=tmp_path / "beam",
            fixed_coordinate_root=request.fixed_coordinate_root,
            beam_width=1,
        )
    )
    assert output.result.retained_state_ids == (
        json.loads((attempts[1] / "composition_state.json").read_text())["state_id"],
    )
    assert output.result.depth_complete


def _task_trace(tmp_path, request, task, rows):
    work_root = tmp_path / "work"
    work_root.mkdir()
    trace = tmp_path / "trace.tsv"
    lines = ["task_id\tnative_id\tprocess\ttag\tstatus\texit\tattempt\tworkdir\n"]
    for resource_attempt, status, exit_code in rows:
        workdir = work_root / f"attempt-{resource_attempt}"
        workdir.mkdir()
        (workdir / ".command.sh").write_text(
            "genome-to-diffraction composition run-attempt "
            f"--attempt-id '{task.attempt_id}' "
            f"--attempt-inventory '{request.attempt_inventory}'\n"
        )
        (workdir / ".command.err").write_text(f"resource attempt {resource_attempt}\n")
        lines.append(
            f"{resource_attempt}\t{resource_attempt + 100}\t"
            f"WF:RUN_PHASE3_BEAM_ATTEMPT\tcomposition-beam-attempt:{task.attempt_id}\t"
            f"{status}\t{exit_code}\t{resource_attempt}\t{workdir}\n"
        )
    trace.write_text("".join(lines))
    return trace, work_root


def test_exhausted_scheduler_retries_are_one_failed_search(tmp_path, monkeypatch):
    request, inventory = _request(
        tmp_path, monkeypatch, status=ExecutionStatus.COMPLETED_NO_HIT
    )
    task = inventory.attempts[0]
    trace, work_root = _task_trace(
        tmp_path, request, task, ((1, "FAILED", 137), (2, "FAILED", 137))
    )
    output = collect_composition_beam_depth(
        CompositionBeamCollectionRequest(
            attempt_inventory=request.attempt_inventory,
            attempt_result_directories=(),
            output_directory=tmp_path / "beam",
            fixed_coordinate_root=request.fixed_coordinate_root,
            scheduler_trace=trace,
            task_work_root=work_root,
            workflow_run_id="session-test",
        )
    )
    assert output.result.attempt_count == inventory.attempt_count
    assert output.result.failed_count == 1
    assert output.result.missing_output_count == inventory.attempt_count - 1
    evidence = output.result.attempts[0]
    assert evidence.execution_status is None
    assert len(evidence.terminal_tasks) == 2
    assert (
        output.result_json.parent
        / "task_diagnostics"
        / task.attempt_id
        / "attempt-1"
        / ".command.err"
    ).read_text() == "resource attempt 1\n"


def test_stale_scheduler_inventory_is_rejected(tmp_path, monkeypatch):
    request, inventory = _request(
        tmp_path, monkeypatch, status=ExecutionStatus.COMPLETED_NO_HIT
    )
    task = inventory.attempts[0]
    trace, work_root = _task_trace(tmp_path, request, task, ((1, "FAILED", 137),))
    stale = tmp_path / "stale.json"
    stale.write_text("{}\n")
    command = work_root / "attempt-1" / ".command.sh"
    command.write_text(
        command.read_text().replace(str(request.attempt_inventory), str(stale))
    )
    with pytest.raises(CompositionTaskEvidenceError, match="evidence differs"):
        collect_composition_beam_depth(
            CompositionBeamCollectionRequest(
                attempt_inventory=request.attempt_inventory,
                attempt_result_directories=(),
                output_directory=tmp_path / "beam",
                fixed_coordinate_root=request.fixed_coordinate_root,
                scheduler_trace=trace,
                task_work_root=work_root,
                workflow_run_id="session-test",
            )
        )


def test_duplicate_native_outputs_fail_closed(tmp_path, monkeypatch):
    request, inventory = _request(
        tmp_path, monkeypatch, status=ExecutionStatus.COMPLETED_NO_HIT
    )
    result = _no_hit_attempt(tmp_path / "result", inventory, inventory.attempts[0])
    with pytest.raises(CompositionBeamError, match="duplicated"):
        collect_composition_beam_depth(
            CompositionBeamCollectionRequest(
                attempt_inventory=request.attempt_inventory,
                attempt_result_directories=(result, result),
                output_directory=tmp_path / "beam",
                fixed_coordinate_root=request.fixed_coordinate_root,
            )
        )


def test_each_parent_retains_its_own_extension_outcome(tmp_path, monkeypatch):
    request, _ = _request(
        tmp_path, monkeypatch, status=ExecutionStatus.COMPLETED_NO_HIT
    )
    first = inventory_fixture._parent(
        1,
        coordinate_sha256=sha256_file(
            request.fixed_coordinate_root / "component_A.pdb"
        ),
    )
    second_coordinate = request.fixed_coordinate_root / "second_parent.pdb"
    second_coordinate.write_text("ATOM SECOND PARENT\n")
    second = inventory_fixture._parent(
        2, coordinate_sha256=sha256_file(second_coordinate)
    )
    _, inventory = inventory_fixture._inventory(
        parents=(first, second),
        candidates=tuple(
            inventory_fixture._candidate(parent=parent, rank=1, sequence_index=2)
            for parent in (first, second)
        ),
    )
    inventory_path = write_composition_attempt_inventory(
        inventory, tmp_path / "multiple-parents.json"
    )
    hit = _packed_attempt(tmp_path / "hit", inventory)
    attempts = (
        hit,
        *(
            _no_hit_attempt(
                tmp_path / f"attempt-{index}",
                inventory,
                task,
                status=ExecutionStatus.FAILED_PARSE
                if task.parent_state_id == second.state.state_id
                else ExecutionStatus.COMPLETED_NO_HIT,
            )
            for index, task in enumerate(inventory.attempts[1:])
        ),
    )
    output = collect_composition_beam_depth(
        CompositionBeamCollectionRequest(
            attempt_inventory=inventory_path,
            attempt_result_directories=attempts,
            output_directory=tmp_path / "beam",
            fixed_coordinate_root=request.fixed_coordinate_root,
        )
    )
    parent_rows = {
        row["parent_state_id"]: row
        for line in (output.result_json.parent / "parent_extension_outcomes.jsonl")
        .read_text()
        .splitlines()
        if (row := json.loads(line))
    }
    assert parent_rows[first.state.state_id]["extension_complete"]
    assert parent_rows[first.state.state_id]["outcome_counts"]["completed_hit"] == 1
    assert not parent_rows[second.state.state_id]["extension_complete"]
    assert parent_rows[second.state.state_id]["outcome_counts"]["failed"] > 0
    assessments = {
        row["state_id"]: row
        for line in output.assessments_jsonl.read_text().splitlines()
        if (row := json.loads(line))
    }
    assert assessments[first.state.state_id]["execution_status"] == "completed_hit"
    assert assessments[second.state.state_id]["execution_status"] == "failed_parse"
    assert len(assessments) == 3
    packages = build_pass2_review_packages(
        beam_directory=output.result_json.parent,
        execution_identity=request.execution_identity,
        owned_parent_run_id="gtd-unknown-pass2-20260828T000000Z-aaaaaaaaaaaa-bbbbbbbb",
        crystal_id=inventory.depth_plan.crystal_id,
        output_directory=tmp_path / "packages",
    )
    assert packages.composition.manifest.is_file()
