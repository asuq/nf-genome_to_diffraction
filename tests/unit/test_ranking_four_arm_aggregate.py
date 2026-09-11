"""Actual exact-case joins with original preparation and simulated external tools."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.m6_nextflow import (
    run_m6_coordinate_stage_task,
    run_m6_model_policy_task,
    run_m6_preflight_task,
    run_m6_prepare_case_task,
)
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from tests.fixtures.ranking_four_arm_advancement import REFERENCE_CASE_IDS
from tests.fixtures.ranking_four_arm_aggregate import (
    ReferenceRunInputs,
    build_reference_run,
    validate_reference_run,
)
from tests.fixtures.ranking_four_arm_context import (
    ReferenceFinalistContext,
    ReferenceIdentityContext,
    ReferencePlanContext,
    ReferencePreparedContext,
    ReferenceReviewContext,
)
from tests.fixtures.ranking_four_arm_finalists import build_reference_finalists
from tests.fixtures.ranking_four_arm_identity import (
    ReferenceIdentityInputs,
    build_reference_case_identity,
)
from tests.fixtures.ranking_four_arm_plan import validate_reference_plan
from tests.fixtures.ranking_four_arm_prepared import bind_reference_prepared_case
from tests.unit.test_ranking_four_arm_continuation import _inputs


def _original_contexts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ReferenceRunInputs:
    # Only Phenix/search responses are simulated; all scientific joins below
    # use the original validators and complete five-case runner plan.
    continuation = _inputs(tmp_path, monkeypatch, no_hit=True)
    first = continuation.prepared_inputs
    plan = validate_reference_plan(first.plan_path, first.plan_inputs)
    plan_context = ReferencePlanContext(
        runner_root=first.plan_inputs.runner_root,
        database_manifest=first.plan_inputs.database_manifest,
        software_lock=first.plan_inputs.software_lock,
        plan_path=first.plan_path,
    )
    context_root = tmp_path / "contexts"
    context_root.mkdir()
    plan_context_path = context_root / "plan.json"
    atomic_write_json(plan_context_path, plan_context.model_dump(mode="json"))
    prepared_paths = []
    identity_paths = []
    for row in plan.cases:
        case_id = row.task.case_id
        if case_id == first.case_id:
            inputs, prepared_path = first, continuation.prepared_path
        else:
            task = first.plan_path.parent / row.task_directory
            preflight = run_m6_preflight_task(
                task, first.phenix_manifest, tmp_path / f"preflight-{case_id}"
            )
            # Both provider inputs are explicitly empty simulated responses.
            empty_search = tmp_path / "synthetic-foldseek-search"
            policy = run_m6_model_policy_task(
                task,
                first.catalogue_bundle,
                empty_search,
                empty_search,
                Path(__file__).resolve().parents[2] / "benchmarks/m6/protocol.yaml",
                first.plan_inputs.database_manifest,
                tmp_path / f"policy-{case_id}",
            )
            stage = run_m6_coordinate_stage_task(
                task,
                first.catalogue_bundle,
                policy,
                first.plan_inputs.database_manifest,
                tmp_path / f"coordinates-{case_id}",
            )
            original_case = run_m6_prepare_case_task(
                task,
                preflight,
                first.catalogue_bundle,
                policy,
                stage,
                tmp_path / f"prepared-{case_id}",
            )
            inputs = replace(
                first,
                case_id=case_id,
                prepared_case=original_case,
                coordinate_stage=stage,
            )
            prepared_path = bind_reference_prepared_case(
                inputs, tmp_path / f"reference-{case_id}"
            )
        prepared_context = ReferencePreparedContext(
            plan=plan_context,
            case_id=case_id,
            catalogue_bundle=inputs.catalogue_bundle,
            prepared_case=inputs.prepared_case,
            coordinate_stage=inputs.coordinate_stage,
            phenix_manifest=inputs.phenix_manifest,
            prepared_path=prepared_path,
        )
        prepared_context_path = context_root / f"prepared-{case_id}.json"
        atomic_write_json(
            prepared_context_path, prepared_context.model_dump(mode="json")
        )
        prepared_paths.append(prepared_context_path)
        if case_id != first.case_id:
            continue
        finalists = build_reference_finalists(
            continuation, copy_receipts=(), output=tmp_path / "finalists"
        )
        identity = build_reference_case_identity(
            ReferenceIdentityInputs(continuation, (), finalists, ()),
            tmp_path / "identity",
        )
        identity_context = ReferenceIdentityContext(
            finalists=ReferenceFinalistContext(
                review=ReferenceReviewContext(
                    prepared=prepared_context,
                    first_copy_receipts=continuation.first_copy_receipts,
                    reviews_path=continuation.reviews_path,
                ),
                copy_receipts=(),
                finalists_path=finalists,
            ),
            refinement_receipts=(),
            identity_path=identity,
        )
        identity_context_path = context_root / f"identity-{case_id}.json"
        atomic_write_json(
            identity_context_path, identity_context.model_dump(mode="json")
        )
        identity_paths.append(identity_context_path)
    return ReferenceRunInputs(
        plan_context_path, tuple(prepared_paths), tuple(identity_paths)
    )


def test_reference_aggregate_requires_all_original_cases_and_preserves_early_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _original_contexts(tmp_path, monkeypatch)
    path = build_reference_run(inputs, tmp_path / "complete")
    manifest = validate_reference_run(path, inputs)
    assert tuple(row.case_id for row in manifest.cases) == REFERENCE_CASE_IDS
    assert not manifest.native_acceptance_claim
    assert not manifest.benchmark_acceptance_claim
    assert not manifest.human_approval_granted
    assert not manifest.truth_compared
    assert manifest.cases[0].preparation_status == "materialised"
    assert manifest.cases[0].case_identity_id is not None
    assert all(
        row.preparation_status == "completed_no_model" for row in manifest.cases[1:]
    )
    assert all(row.case_identity_id is None for row in manifest.cases[1:])
    assert (
        path.parent / "cases/M6C001/identity/reference_case_identity.json"
    ).is_file()
    assert not (path.parent / "cases/M6C025/identity").exists()

    for label, altered, match in (
        (
            "missing-case",
            replace(inputs, prepared_contexts=inputs.prepared_contexts[:-1]),
            "all five exact",
        ),
        (
            "duplicate-case",
            replace(
                inputs,
                prepared_contexts=(
                    *inputs.prepared_contexts[:-1],
                    inputs.prepared_contexts[0],
                ),
            ),
            "repeats an original context",
        ),
        (
            "missing-identity",
            replace(inputs, identity_contexts=()),
            "missing or invented identity",
        ),
        (
            "duplicate-identity",
            replace(inputs, identity_contexts=inputs.identity_contexts * 2),
            "repeats an original context",
        ),
    ):
        with pytest.raises(ValueError, match=match):
            build_reference_run(altered, tmp_path / label)
        assert not (tmp_path / label).exists()

    # An edited transport file cannot change an original authenticated case.
    foreign = json.loads(inputs.prepared_contexts[0].read_bytes())
    foreign["case_id"] = "M6C002"
    foreign_path = tmp_path / "foreign-context.json"
    atomic_write_json(foreign_path, foreign)
    with pytest.raises(ValueError, match="all five exact"):
        build_reference_run(
            replace(
                inputs, prepared_contexts=(foreign_path, *inputs.prepared_contexts[1:])
            ),
            tmp_path / "foreign-case",
        )

    relative = "cases/M6C001/identity/reference_case_identity.json"
    copied = path.parent / relative
    copied.write_bytes(copied.read_bytes() + b"\n")
    document = json.loads(path.read_bytes())
    document["output_sha256"][relative] = sha256_file(copied)
    document["reference_run_id"] = content_id(
        "rfrun_",
        {key: value for key, value in document.items() if key != "reference_run_id"},
    )
    atomic_write_json(path, document)
    with pytest.raises(ValueError, match="source, inputs or outputs changed"):
        validate_reference_run(path, inputs)
