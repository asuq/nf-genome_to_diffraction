"""Per-arm RF native-receipt joins with explicitly simulated external Phenix."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

import tests.fixtures.ranking_four_arm_identity as identity_module
from genome_to_diffraction.benchmarks.m6_identity import derive_m6_identity_decision
from genome_to_diffraction.benchmarks.m6_stages import stage_counts
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.refinement.brief import _read_jsonl
from genome_to_diffraction.schemas.results import SequenceGroupRecord
from tests.fixtures.ranking_four_arm_continuation import ReferenceContinuationInputs
from tests.fixtures.ranking_four_arm_finalists import ReferenceFinalists
from tests.fixtures.ranking_four_arm_first_copy import ReferenceFirstCopyReceipt
from tests.fixtures.ranking_four_arm_identity import (
    ReferenceIdentityInputs,
    _arm_identity,
    build_reference_case_identity,
    validate_reference_case_identity,
)
from tests.fixtures.ranking_four_arm_refinement import (
    ReferenceRefinementReceipt,
    run_reference_refinement_task,
)
from tests.unit.test_brief_refinement import _install_phase3_runtime
from tests.unit.test_ranking_four_arm_refinement import _request


def test_reference_identity_requires_exact_union_and_counts_only_each_arms_seeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path, monkeypatch)
    finalists = ReferenceFinalists.model_validate_json(
        request.finalists_path.read_bytes()
    )
    _install_phase3_runtime(monkeypatch)
    # Independent calls to a simulator only; the native graph must use channel items.
    receipts = tuple(
        run_reference_refinement_task(
            replace(
                request,
                admission_prior=row.admission_prior,
                seed_solution_id=row.task.seed_solution_id,
                output_directory=tmp_path / f"refine-{index}",
            )
        )
        for index, row in enumerate(finalists.tasks)
    )
    inputs = ReferenceIdentityInputs(
        continuation=request.inputs,
        copy_receipts=request.copy_receipts,
        finalists_path=request.finalists_path,
        refinement_receipts=receipts,
    )
    original_validate = identity_module.validate_reference_finalists
    upstream_checks = 0

    def counted_validate(
        path: Path,
        continuation: ReferenceContinuationInputs,
        *,
        copy_receipts: tuple[Path, ...],
    ) -> ReferenceFinalists:
        nonlocal upstream_checks
        upstream_checks += 1
        return original_validate(path, continuation, copy_receipts=copy_receipts)

    monkeypatch.setattr(
        identity_module, "validate_reference_finalists", counted_validate
    )
    path = build_reference_case_identity(inputs, tmp_path / "identity")
    manifest = validate_reference_case_identity(path, inputs)
    # Construction, its final check and explicit replay each authenticate the
    # full upstream union twice, independently of the number of native receipts.
    assert upstream_checks == 6
    assert tuple(arm.arm for arm in manifest.arms) == ("A", "B", "C", "D")
    assert not manifest.human_approval_granted
    assert all(arm.identity_decision.decision == "reported" for arm in manifest.arms)
    groups = _read_jsonl(
        request.inputs.prepared_inputs.prepared_case / "all_sequence_groups.jsonl",
        SequenceGroupRecord,
        label="sequence group",
    )
    for arm in manifest.arms:
        assert arm.stages is not None
        assert len(arm.selected_seed_results) == arm.stages.advanced.hypothesis_tasks
        assert arm.identity_decision == derive_m6_identity_decision(
            case_id=manifest.case_id,
            selected_seed_results=arm.selected_seed_results,
            sequence_groups=groups,
        )
    parsed = tuple(
        ReferenceRefinementReceipt.model_validate_json(p.read_bytes()) for p in receipts
    )
    # All simulated sequence assessments have no scored hit. They must not become
    # an unapproved identity threshold replacing M6's selected-seed rule.
    assert all(not receipt.sequence.candidates for receipt in parsed)
    first = tuple(
        ReferenceFirstCopyReceipt.model_validate_json(p.read_bytes())
        for p in request.inputs.first_copy_receipts
    )
    by_key = {
        (receipt.task.admission_prior, receipt.task.task.seed_solution_id): receipt
        for receipt in parsed
    }
    digests = {key: sha256_file(p) for key, p in zip(by_key, receipts, strict=True)}
    stage = manifest.arms[0].stages
    assert stage is not None
    # A deliberately altered test-only arm has no advanced seeds, while the
    # complete paired-union map still contains the other arm's native receipts.
    rows = tuple(
        row.model_copy(
            update={
                "advanced_rank": None,
                "continuation_receipt_sha256": None,
                "additional_copy_attempt_count": 0,
            }
        )
        for row in stage.rows
    )
    isolated = _arm_identity(
        case_id=manifest.case_id,
        arm="A",
        prior="solvent_density",
        review="prior_first",
        stages=stage.model_copy(update={"rows": rows, "advanced": stage_counts([])}),
        groups=groups,
        first_results={row.result.hypothesis_id: row.result for row in first},
        refinements=by_key,
        receipt_digests=digests,
    )
    assert isolated.identity_decision.decision == "abstained"
    assert isolated.selected_seed_results == ()
    assert isolated.refinement_receipt_sha256 == {}
    for label, incomplete in (
        ("missing", receipts[:-1]),
        ("duplicate", (*receipts[:-1], receipts[0])),
    ):
        with pytest.raises(ValueError, match="exact unique refinement union"):
            build_reference_case_identity(
                replace(inputs, refinement_receipts=incomplete), tmp_path / label
            )
        assert not (tmp_path / label).exists()
    # A consistent replacement of identity evidence still fails reconstruction
    # against the original arm's authentic selected rows.
    changed = manifest.arms[0].model_copy(
        update={
            "selected_seed_results": (),
            "identity_decision": derive_m6_identity_decision(
                case_id=manifest.case_id,
                selected_seed_results=(),
                sequence_groups=groups,
            ),
        }
    )
    document = json.loads(path.read_text())
    document["arms"][0] = changed.model_dump(mode="json")
    document["case_identity_id"] = content_id(
        "rfcaseidentity_",
        {k: v for k, v in document.items() if k != "case_identity_id"},
    )
    atomic_write_json(path, document)
    with pytest.raises(ValueError, match="arms, original receipts or outputs changed"):
        validate_reference_case_identity(path, inputs)
