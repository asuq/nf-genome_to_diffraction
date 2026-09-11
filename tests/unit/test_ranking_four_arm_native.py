"""Original scientific joins with simulated external tools, not native acceptance."""

import json
import subprocess
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.hpc.rf_reference_evidence import command_record_expectations
from tests.fixtures.ranking_four_arm_aggregate import build_reference_run
from tests.fixtures.ranking_four_arm_context import (
    ReferenceFinalistContext,
    ReferenceIdentityContext,
    ReferencePlanContext,
    ReferencePreparedContext,
    ReferenceReviewContext,
)
from tests.fixtures.ranking_four_arm_continuation import (
    ReferenceContinuationInputs,
    ReferencePreparedCopyRequest,
    reference_copy_tasks,
    run_prepared_reference_copy_task,
)
from tests.fixtures.ranking_four_arm_finalists import (
    ReferenceFinalists,
    build_reference_finalists,
)
from tests.fixtures.ranking_four_arm_first_copy import (
    ReferenceFirstCopyRequest,
    build_prepared_reference_reviews,
    run_reference_first_copy_task,
)
from tests.fixtures.ranking_four_arm_identity import (
    ReferenceIdentityInputs,
    build_reference_case_identity,
)
from tests.fixtures.ranking_four_arm_native import (
    _input_copies,
    _native_commands,
    _science,
)
from tests.fixtures.ranking_four_arm_prepared import bind_reference_prepared_case
from tests.fixtures.ranking_four_arm_refinement import (
    ReferenceRefinementRequest,
    run_reference_refinement_task,
)
from tests.unit.test_add_copy_phaser import (
    NO_SOLUTION_LOG as COPY_NO_SOLUTION_LOG,
)
from tests.unit.test_add_copy_phaser import _fake_runtime as copy_runtime
from tests.unit.test_brief_refinement import _install_phase3_runtime
from tests.unit.test_phaser_adapter import NO_SOLUTION_LOG, POSITIVE_LOG, _fake_runtime
from tests.unit.test_ranking_four_arm_aggregate import _original_contexts
from tests.unit.test_ranking_four_arm_prepared import _inputs


def _work(run: Path, number: int) -> Path:
    digest = f"{number:032x}"
    path = run / "cache/rf-reference/work" / digest[:2] / digest[2:]
    path.mkdir(parents=True)
    return path


def test_native_input_copies_are_create_only_and_resume_requires_original_bytes(
    tmp_path: Path,
) -> None:
    from genome_to_diffraction.hpc.rf_reference_evidence import REFERENCE_INPUT_COPIES

    run = tmp_path / "runs/reference"
    (run / "artifacts/qualification").mkdir(parents=True)
    originals = tmp_path / "original-inputs"
    originals.mkdir()
    paths = {}
    for role, filename in REFERENCE_INPUT_COPIES.items():
        path = originals / filename
        path.write_text(f"synthetic original input {role}\n")
        paths[role] = path
    inventory = _input_copies(run, paths, phase="first")
    assert _input_copies(run, paths, phase="resume") == inventory
    with pytest.raises(ValueError, match="must not already exist"):
        _input_copies(run, paths, phase="first")
    paths["runner_manifest"].write_text("changed original\n")
    with pytest.raises(ValueError, match="unchanged original"):
        _input_copies(run, paths, phase="resume")


def test_native_science_rederives_original_five_cases_before_accepting_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One simulated preparation workspace is sufficient to test the read-only
    # scientific verifier. It is not an executor or scheduler qualification.
    work = _work(tmp_path, 1)
    original = _original_contexts(work, monkeypatch)
    plan = ReferencePlanContext.model_validate_json(original.plan_context.read_bytes())
    prepared = ReferencePreparedContext.model_validate_json(
        original.prepared_contexts[0].read_bytes()
    )
    path = build_reference_run(
        original,
        tmp_path / "artifacts/rf-reference-results/reference_run/bundle",
    )
    paths = {
        "runner_manifest": plan.runner_root / "runner_manifest.json",
        "database_manifest": plan.database_manifest,
        "software_lock": plan.software_lock,
        "phenix_manifest": prepared.phenix_manifest,
    }
    tasks = ({"workdir": str(work)},)
    with pytest.raises(ValueError, match="untraced original"):
        _science(tmp_path, paths, ())
    manifest, identities = _science(tmp_path, paths, tasks)
    assert len(manifest.cases) == 5 and len(identities) == 1
    assert not manifest.native_acceptance_claim and not manifest.truth_compared
    assert manifest.cases[0].preparation_status == "materialised"
    assert all(
        row.preparation_status == "completed_no_model" for row in manifest.cases[1:]
    )
    assert identities[0].finalists.review.first_copy_receipts

    native_receipt = identities[0].finalists.review.first_copy_receipts[0]
    native_receipt.write_bytes(native_receipt.read_bytes() + b"\n")
    # Published files have not changed; original scientific provenance has.
    with pytest.raises(ValueError):
        _science(tmp_path, paths, tasks)
    assert path.is_file()


def _first_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, no_hit: bool
) -> tuple[ReferenceContinuationInputs, tuple[dict[str, str], ...]]:
    prepared_work = _work(tmp_path, 1)
    inputs = _inputs(prepared_work, monkeypatch, small=True)
    prepared_path = bind_reference_prepared_case(inputs, prepared_work / "reference")
    hypotheses = json.loads(
        (prepared_path.parent / "cohorts/reference_cohorts.json").read_bytes()
    )["tasks"]
    _fake_runtime(
        monkeypatch,
        log_text=NO_SOLUTION_LOG if no_hit else POSITIVE_LOG,
        write_solution=not no_hit,
    )
    receipts = []
    tasks = []
    for index, hypothesis in enumerate(hypotheses, start=2):
        work = _work(tmp_path, index)
        hypothesis_id = hypothesis["hypothesis"]["hypothesis_id"]
        receipt = run_reference_first_copy_task(
            ReferenceFirstCopyRequest(
                prepared_path=prepared_path,
                prepared_inputs=inputs,
                hypothesis_id=hypothesis_id,
                threads=2,
                output_directory=work / "reference_first/bundle",
            )
        )
        receipts.append(receipt)
        _log_commands(work, (receipt.parent / "phaser_command.json",), exit_code=0)
        tasks.append(
            {
                "process": "RF_REFERENCE_WORKFLOW:RF_FIRST_COPY",
                "workdir": str(work),
                "tag": f"rf-first:{inputs.case_id}:{hypothesis_id}",
                "cpus": "2",
                "task_id": str(index),
                "native_id": str(30150000 + index),
                "hash": work.relative_to(
                    tmp_path / "cache/rf-reference/work"
                ).as_posix(),
            }
        )
    reviews = build_prepared_reference_reviews(
        prepared_path,
        inputs,
        first_copy_receipts=tuple(receipts),
        output=prepared_work / "reviews",
    )
    continuation = ReferenceContinuationInputs(
        prepared_path, inputs, reviews, tuple(receipts)
    )
    return continuation, tuple(tasks)


def _log_commands(work: Path, paths: tuple[Path, ...], *, exit_code: int) -> None:
    events = []
    for path in paths:
        for command in command_record_expectations(path, work_directory=work):
            events.extend(
                (
                    {
                        "logger": "genome_to_diffraction.phenix",
                        "message": "executing captured Phenix command",
                        "command": command.arguments[0],
                        "arguments": list(command.arguments[1:]),
                        "working_directory": str(command.working_directory),
                    },
                    {
                        "logger": "genome_to_diffraction.phenix",
                        "message": "captured Phenix command finished",
                        "command": command.arguments[0],
                        "exit_status": exit_code,
                    },
                )
            )
    (work / ".command.err").write_text("\n".join(json.dumps(row) for row in events))


def _identity_context(
    continuation: ReferenceContinuationInputs,
    copy_receipts: tuple[Path, ...],
    finalists: Path,
    refinement_receipts: tuple[Path, ...],
) -> ReferenceIdentityContext:
    inputs = continuation.prepared_inputs
    identity = build_reference_case_identity(
        ReferenceIdentityInputs(
            continuation, copy_receipts, finalists, refinement_receipts
        ),
        continuation.prepared_path.parent.parent / "identity",
    )
    return ReferenceIdentityContext(
        finalists=ReferenceFinalistContext(
            review=ReferenceReviewContext(
                prepared=ReferencePreparedContext(
                    plan=ReferencePlanContext(
                        runner_root=inputs.plan_inputs.runner_root,
                        database_manifest=inputs.plan_inputs.database_manifest,
                        software_lock=inputs.plan_inputs.software_lock,
                        plan_path=inputs.plan_path,
                    ),
                    case_id=inputs.case_id,
                    catalogue_bundle=inputs.catalogue_bundle,
                    prepared_case=inputs.prepared_case,
                    coordinate_stage=inputs.coordinate_stage,
                    phenix_manifest=inputs.phenix_manifest,
                    prepared_path=continuation.prepared_path,
                ),
                first_copy_receipts=continuation.first_copy_receipts,
                reviews_path=continuation.reviews_path,
            ),
            copy_receipts=copy_receipts,
            finalists_path=finalists,
        ),
        refinement_receipts=refinement_receipts,
        identity_path=identity,
    )


def test_native_command_join_requires_every_original_receipt_and_numeric_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    continuation, tasks = _first_control(tmp_path, monkeypatch, no_hit=True)
    receipts = continuation.first_copy_receipts
    finalists = build_reference_finalists(
        continuation,
        copy_receipts=(),
        output=continuation.prepared_path.parent.parent / "finalists",
    )
    context = _identity_context(continuation, (), finalists, ())
    observed = _native_commands(tmp_path, tuple(tasks), (context,))
    assert len(observed) == len(receipts) > 1
    for row in observed:
        invocations = row["invocations"]
        assert isinstance(invocations, list)
        assert invocations[0]["exit_status"] == 0
    assert all("task_hash" in row for row in observed)
    with pytest.raises(ValueError, match="omits"):
        _native_commands(tmp_path, tuple(tasks[:-1]), (context,))
    with pytest.raises(ValueError, match="CPU"):
        _native_commands(
            tmp_path, tuple([{**tasks[0], "cpus": "1"}, *tasks[1:]]), (context,)
        )
    receipt = receipts[0]
    command_path = receipt.parent / "phaser_command.json"
    command = json.loads(command_path.read_bytes())
    command["arguments"] = [*command["arguments"], "invented_argument"]
    atomic_write_json(command_path, command)
    with pytest.raises(ValueError, match="commands are incomplete or differ"):
        _native_commands(tmp_path, tuple(tasks), (context,))


def test_native_copy_refinement_keep_attempts_and_unexecuted_sequence_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import genome_to_diffraction.refinement.brief as brief

    continuation, first_tasks = _first_control(tmp_path, monkeypatch, no_hit=False)
    tasks = list(first_tasks)
    copy_runtime(monkeypatch, log_text=COPY_NO_SOLUTION_LOG, write_solution=False)
    copies = []
    for index, copy in enumerate(reference_copy_tasks(continuation), start=20):
        work = _work(tmp_path, index)
        receipt = run_prepared_reference_copy_task(
            ReferencePreparedCopyRequest(
                inputs=continuation,
                admission_prior=copy.admission_prior,
                seed_solution_id=copy.seed_solution_id,
                # The shared copy simulator asserts 16 allocated threads. This
                # unit join does not exercise or change Raven's fixed allocation.
                threads=16,
                output_directory=work / "reference_copy/bundle",
            )
        )
        copies.append(receipt)
        summary = json.loads(
            (receipt.parent / "additional_copy_series_summary.json").read_bytes()
        )
        paths = tuple(
            (receipt.parent / "series" / relative).parent / "phaser_command.json"
            for relative in (
                summary["result_paths"] if summary["attempt_count"] else []
            )
        )
        _log_commands(work, paths, exit_code=0)
        tasks.append(
            {
                "process": "RF_REFERENCE_WORKFLOW:RF_COPY",
                "workdir": str(work),
                "tag": (
                    f"rf-copy:{continuation.prepared_inputs.case_id}:"
                    f"{copy.admission_prior}:{copy.seed_solution_id}"
                ),
                "cpus": "16",
                "task_id": str(index),
                "native_id": str(30150000 + index),
                "hash": work.relative_to(
                    tmp_path / "cache/rf-reference/work"
                ).as_posix(),
            }
        )
    finalists = build_reference_finalists(
        continuation,
        copy_receipts=tuple(copies),
        output=continuation.prepared_path.parent.parent / "finalists",
    )
    manifest = ReferenceFinalists.model_validate_json(finalists.read_bytes())
    _install_phase3_runtime(monkeypatch)

    def simulated_refine_failure(
        manifest_path: Path,
        arguments: list[str],
        *,
        working_directory: Path,
        timeout_seconds: float | None,
    ) -> subprocess.CompletedProcess[bytes]:
        assert arguments[0] == "phenix.refine" and timeout_seconds is None
        return subprocess.CompletedProcess(
            arguments, 17, b"simulated native failure\n", b""
        )

    monkeypatch.setattr(brief, "capture_from_manifest", simulated_refine_failure)
    refinements = []
    for index, finalist in enumerate(manifest.tasks, start=40):
        work = _work(tmp_path, index)
        receipt = run_reference_refinement_task(
            ReferenceRefinementRequest(
                inputs=continuation,
                copy_receipts=tuple(copies),
                finalists_path=finalists,
                admission_prior=finalist.admission_prior,
                seed_solution_id=finalist.task.seed_solution_id,
                threads=4,
                output_directory=work / "reference_refinement/bundle",
            )
        )
        refinements.append(receipt)
        _log_commands(work, (receipt.parent / "t12/t12_command.json",), exit_code=17)
        tasks.append(
            {
                "process": "RF_REFERENCE_WORKFLOW:RF_REFINE",
                "workdir": str(work),
                "tag": (
                    f"rf-refine:{continuation.prepared_inputs.case_id}:"
                    f"{finalist.admission_prior}:{finalist.task.seed_solution_id}"
                ),
                "cpus": "4",
                "task_id": str(index),
                "native_id": str(30150000 + index),
                "hash": work.relative_to(
                    tmp_path / "cache/rf-reference/work"
                ).as_posix(),
            }
        )
    context = _identity_context(
        continuation, tuple(copies), finalists, tuple(refinements)
    )
    observed = _native_commands(tmp_path, tuple(tasks), (context,))
    assert copies and refinements
    assert len(observed) == len(first_tasks) + len(copies) + len(refinements)
    copy_observations = [
        row for row in observed if row["process"] == "RF_REFERENCE_WORKFLOW:RF_COPY"
    ]
    assert any(row["invocations"] == [] for row in copy_observations)
    assert any(row["invocations"] != [] for row in copy_observations)
    for row in observed:
        invocations = row["invocations"]
        assert isinstance(invocations, list)
        if row["process"] == "RF_REFERENCE_WORKFLOW:RF_REFINE":
            assert len(invocations) == 1
            assert invocations[0]["arguments"][0] == "phenix.refine"
            assert invocations[0]["exit_status"] == 17
    with pytest.raises(ValueError, match="omits"):
        _native_commands(tmp_path, tuple(tasks[:-1]), (context,))
