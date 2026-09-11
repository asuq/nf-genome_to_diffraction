"""Original RF finalist-to-T12 boundary; only external Phenix is simulated."""

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import genome_to_diffraction.refinement.brief as brief_module
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.status import ExecutionStatus
from tests.fixtures.ranking_four_arm_continuation import (
    ReferencePreparedCopyRequest,
    reference_copy_tasks,
    run_prepared_reference_copy_task,
)
from tests.fixtures.ranking_four_arm_finalists import (
    ReferenceFinalists,
    build_reference_finalists,
)
from tests.fixtures.ranking_four_arm_identity import (
    ReferenceIdentityInputs,
    build_reference_case_identity,
    validate_reference_case_identity,
)
from tests.fixtures.ranking_four_arm_refinement import (
    ReferenceRefinementReceipt,
    ReferenceRefinementRequest,
    run_reference_refinement_task,
    validate_reference_refinement_task,
)
from tests.unit.test_add_copy_phaser import NO_SOLUTION_LOG, _fake_runtime
from tests.unit.test_brief_refinement import _install_phase3_runtime
from tests.unit.test_ranking_four_arm_continuation import _inputs


def _request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ReferenceRefinementRequest:
    inputs = _inputs(tmp_path, monkeypatch)
    tasks = reference_copy_tasks(inputs)
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)
    # Simulator only: native independent chains must fan out through Nextflow.
    receipts = tuple(
        run_prepared_reference_copy_task(
            ReferencePreparedCopyRequest(
                inputs=inputs,
                admission_prior=task.admission_prior,
                seed_solution_id=task.seed_solution_id,
                threads=16,
                output_directory=tmp_path / f"simulated-copy-{index}",
            )
        )
        for index, task in enumerate(tasks)
    )
    path = build_reference_finalists(
        inputs, copy_receipts=receipts, output=tmp_path / "finalists"
    )
    manifest = ReferenceFinalists.model_validate_json(path.read_bytes())
    task = manifest.tasks[0]
    return ReferenceRefinementRequest(
        inputs=inputs,
        copy_receipts=receipts,
        finalists_path=path,
        admission_prior=task.admission_prior,
        seed_solution_id=task.task.seed_solution_id,
        threads=16,
        output_directory=tmp_path / "refinement",
    )


def _rehash(path: Path) -> None:
    document = json.loads(path.read_text())
    for relative in document["output_sha256"]:
        document["output_sha256"][relative] = sha256_file(path.parent / relative)
    document["receipt_id"] = content_id(
        "rfrefine_",
        {key: value for key, value in document.items() if key != "receipt_id"},
    )
    atomic_write_json(path, document)


def test_reference_refinement_binds_native_command_catalogue_results_and_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path, monkeypatch)
    commands = _install_phase3_runtime(monkeypatch)
    native_capture = brief_module.capture_from_manifest
    groups = tuple(
        json.loads(line)
        for line in (
            request.inputs.prepared_inputs.prepared_case / "all_sequence_groups.jsonl"
        )
        .read_text()
        .splitlines()
    )
    assert len(groups) > 1
    mode = "success"

    def simulated_capture(
        manifest_path: Path,
        arguments: list[str],
        *,
        working_directory: Path,
        timeout_seconds: float | None,
    ) -> subprocess.CompletedProcess[bytes]:
        assert manifest_path == request.inputs.prepared_inputs.phenix_manifest.resolve()
        assert timeout_seconds is None
        is_refine = arguments[0] == "phenix.refine"
        if is_refine and mode in {"refine_tool_failure", "refine_parse_failure"}:
            commands.append(arguments)
            return subprocess.CompletedProcess(
                arguments,
                17 if mode == "refine_tool_failure" else 0,
                b"simulated refinement without required assets\n",
                b"",
            )
        result = native_capture(
            manifest_path,
            arguments,
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
        )
        if is_refine:
            return result
        if mode == "sequence_tool_failure":
            return subprocess.CompletedProcess(
                arguments, 23, b"simulated failure\n", b""
            )
        if mode == "sequence_parse_failure":
            return subprocess.CompletedProcess(arguments, 0, b"malformed score\n", b"")
        rows = "".join(
            f"Score for sequence {index} ({group['length_aa']} residues): "
            f"{index:.2f} (>{group['sequence_group_id']})\n"
            for index, group in enumerate(groups, start=1)
        )
        return subprocess.CompletedProcess(
            arguments,
            0,
            (
                rows + "Overall best Z-score: 1.0 Mean and SD of scores: 1.5 +/- 0.5\n"
            ).encode(),
            b"",
        )

    monkeypatch.setattr(brief_module, "capture_from_manifest", simulated_capture)
    path = run_reference_refinement_task(request)
    receipt = validate_reference_refinement_task(path, request)
    assert receipt.refinement.execution_status == ExecutionStatus.COMPLETED_SUCCESS
    assert receipt.sequence.execution_status == ExecutionStatus.COMPLETED_HIT
    assert receipt.sequence.scored_group_count == len(groups)
    sources = tuple(
        json.loads(line)
        for line in (
            request.inputs.prepared_inputs.prepared_case / "all_source_records.jsonl"
        )
        .read_text()
        .splitlines()
    )
    for candidate in receipt.sequence.candidates:
        matching = tuple(
            row
            for row in sources
            if row["sequence_group_id"] == candidate.sequence_group_id
        )
        assert candidate.source_record_ids == tuple(
            sorted(row["source_record_id"] for row in matching)
        )
        assert candidate.source_loci == tuple(
            sorted(
                {
                    value
                    for row in matching
                    for value in (row["locus_tag"], row["gene_name"])
                    if value
                }
            )
        )
    assert all(not candidate.source_loci for candidate in receipt.sequence.candidates)
    assert not receipt.human_approval_granted
    assert len(commands) == 2
    command = json.loads((path.parent / "t12/t12_command.json").read_text())
    assert command["refine_arguments"] == commands[0]
    assert command["sequence_arguments"] == commands[1]
    assert command["schema_version"] == "1.0"
    assert command["protocol_version"] == "phenix-t12-brief-v6"
    assert "free_r_identity" not in command
    assert "exit_status" not in command
    params = (path.parent / "t12/brief_refine.eff").read_text()
    assert "nproc = 16" in params
    assert "number_of_macro_cycles = 1" in params
    assert "strategy = individual_sites individual_adp" in params
    original_receipt = path.read_bytes()

    # Rehashing altered command/parameters/catalogue cannot authenticate changes.
    for relative in (
        "t12/t12_command.json",
        "t12/brief_refine.eff",
        "t12/exact_sequence_catalogue.fasta",
    ):
        target = path.parent / relative
        original = target.read_bytes()
        if relative.endswith(".json"):
            document = json.loads(original)
            document["refine_arguments"][-1] = "changed.observation.labels"
            atomic_write_json(target, document)
        else:
            target.write_bytes(original + b"changed\n")
        _rehash(path)
        with pytest.raises(ValueError, match="changed"):
            validate_reference_refinement_task(path, request)
        target.write_bytes(original)
        path.write_bytes(original_receipt)

    # Preserve each actual typed native failure; no guessed numeric exit codes.
    for mode, refine_status, sequence_status in (
        (
            "refine_tool_failure",
            ExecutionStatus.FAILED_TOOL_EXECUTION,
            ExecutionStatus.SKIPPED_INELIGIBLE,
        ),
        (
            "refine_parse_failure",
            ExecutionStatus.FAILED_PARSE,
            ExecutionStatus.SKIPPED_INELIGIBLE,
        ),
        (
            "sequence_tool_failure",
            ExecutionStatus.COMPLETED_SUCCESS,
            ExecutionStatus.FAILED_TOOL_EXECUTION,
        ),
        (
            "sequence_parse_failure",
            ExecutionStatus.COMPLETED_SUCCESS,
            ExecutionStatus.FAILED_PARSE,
        ),
    ):
        failed_request = replace(request, output_directory=tmp_path / mode)
        failed = run_reference_refinement_task(failed_request)
        result = ReferenceRefinementReceipt.model_validate_json(failed.read_bytes())
        assert result.refinement.execution_status == refine_status
        assert result.sequence.execution_status == sequence_status
        assert not result.sequence.candidates
    monkeypatch.chdir(tmp_path)
    relative_request = replace(request, output_directory=Path("relative-refinement"))
    relative_receipt = run_reference_refinement_task(relative_request)
    assert relative_receipt.is_absolute()
    validate_reference_refinement_task(relative_receipt, relative_request)
    before = len(commands)
    for invalid in (
        replace(request, threads=True, output_directory=tmp_path / "bad-threads"),
        replace(
            request,
            seed_solution_id="not-emitted",
            output_directory=tmp_path / "bad-seed",
        ),
        replace(
            request,
            copy_receipts=request.copy_receipts[:-1],
            output_directory=tmp_path / "missing-copy",
        ),
    ):
        with pytest.raises(ValueError):
            run_reference_refinement_task(invalid)
        assert not invalid.output_directory.exists()
    assert len(commands) == before


def test_reference_refinement_rejects_empty_finalist_union_without_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path, monkeypatch, no_hit=True)
    finalists = build_reference_finalists(
        inputs, copy_receipts=(), output=tmp_path / "finalists"
    )
    commands = _install_phase3_runtime(monkeypatch)
    request = ReferenceRefinementRequest(
        inputs=inputs,
        copy_receipts=(),
        finalists_path=finalists,
        admission_prior="solvent_density",
        seed_solution_id="not-emitted",
        threads=2,
        output_directory=tmp_path / "refinement",
    )
    with pytest.raises(ValueError, match="exactly one emitted finalist"):
        run_reference_refinement_task(request)
    assert not commands
    assert not request.output_directory.exists()
    identity_inputs = ReferenceIdentityInputs(inputs, (), finalists, ())
    identity = build_reference_case_identity(identity_inputs, tmp_path / "identity")
    result = validate_reference_case_identity(identity, identity_inputs)
    assert all(arm.identity_decision.decision == "abstained" for arm in result.arms)
    assert all(arm.stages is not None for arm in result.arms)
    assert all(arm.admission_status == "materialised" for arm in result.arms)
    assert not commands
