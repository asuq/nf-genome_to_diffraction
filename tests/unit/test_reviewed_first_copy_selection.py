"""Reviewed alternatives reach the real adapters with a synthetic Phenix runtime."""

import json
import shutil
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.diffraction.selection import build_diffraction_selection
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.matthews.enumerate import enumerate_group
from genome_to_diffraction.mr import PhaserRunRequest, run_first_copy_phaser
from genome_to_diffraction.ranking.funnel import (
    DiverseFirstCopyFunnelOutput,
    DiverseFirstCopyFunnelRequest,
    FunnelInputError,
    build_diverse_first_copy_funnel,
)
from genome_to_diffraction.review import (
    MrSeedReviewRequest,
    OwnedPhaseIIIParentRun,
    OwnedPhaseIIIReviewPackageSource,
    build_mr_seed_review,
    build_owned_phase3_a_seed_review_package,
    register_phase3_owned_run,
)
from genome_to_diffraction.review.reconsideration import (
    FirstCopySelectionError,
    FirstCopySelectionRequest,
    ReviewedFirstCopyExecutionRequest,
    validate_reviewed_first_copy_execution,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import CrystalEntry, PipelineConfig
from genome_to_diffraction.schemas.mr_resources import MrResourcePlan
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MrHypothesis,
    MtzObservationCandidateRecord,
    MtzPreflightRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.schemas.v2 import (
    ExecutionArtifactIdentity,
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecision,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
    PhaseIIIReviewPackageManifest,
)
from genome_to_diffraction.schemas.v2.reconsideration import (
    FirstCopySelectionTarget,
    ReviewedFirstCopySelection,
)
from tests.unit.test_phase3_owned_run_registry import _execution_identity
from tests.unit.test_phaser_adapter import (
    NO_SOLUTION_LOG,
    POSITIVE_LOG,
    STUBS,
    _fake_runtime,
)
from tests.unit.test_ranking_funnel import (
    _diverse_request,
    _phase3_localisation_bundle,
)


@dataclass(frozen=True)
class SelectionCase:
    request: DiverseFirstCopyFunnelRequest
    selection: ReviewedFirstCopySelection
    parent: DiverseFirstCopyFunnelOutput
    mtz: Path
    diffraction_selection: Path
    execution_identity: Path


def _run(
    request: DiverseFirstCopyFunnelRequest,
    funnel: DiverseFirstCopyFunnelOutput,
    mtz: Path,
    diffraction_selection: Path,
    output_root: Path,
) -> Path:
    assert len(funnel.hypotheses) == 1
    hypothesis = funnel.hypotheses[0]
    resource_path = (
        funnel.manifest_json.parent
        / "resource_plans"
        / f"{hypothesis.hypothesis_id}.json"
    )
    resources = MrResourcePlan.model_validate_json(resource_path.read_bytes())
    result = run_first_copy_phaser(
        PhaserRunRequest(
            hypotheses_jsonl=funnel.hypotheses_jsonl,
            hypothesis_id=hypothesis.hypothesis_id,
            sequence_groups_jsonl=request.sequence_groups_jsonl,
            processed_models_jsonl=funnel.model_registry_directory
            / "processed_models.jsonl",
            model_preparation_manifest=None,
            all_model_registry_json=funnel.model_registry_directory
            / "all_model_registry.json",
            preflight_jsonl=request.mtz_preflight_jsonl,
            mtz=mtz,
            diffraction_selection_json=diffraction_selection,
            derive_phase3_hypothesis_id=True,
            resource_plan_json=resource_path,
            phenix_manifest=STUBS / "phenix_install_manifest.json",
            output_directory=output_root
            / f"first_copy_phaser_{hypothesis.hypothesis_id}",
            threads=resources.base_cpus,
            progress=False,
        )
    )
    return result.result_jsonl


def _execution_request(case: SelectionCase) -> ReviewedFirstCopyExecutionRequest:
    """Use declared fake runtime metadata; no native Phenix claim is made."""
    funnel = build_diverse_first_copy_funnel(case.request)
    root = case.request.output_directory.parent
    crystal = root / "execution_crystal"
    crystal.mkdir()
    shutil.copy2(case.mtz, crystal / "input.mtz")
    shutil.copy2(
        case.diffraction_selection, crystal / "phase3_diffraction_selection.json"
    )
    identity = PhaseIIIExecutionIdentity.model_validate_json(
        case.execution_identity.read_bytes()
    )
    phenix_data = json.loads((STUBS / "phenix_install_manifest.json").read_text())
    phenix_data.update(
        status="verified",
        required_commands=[
            {
                "name": tool.name,
                "path": f"/nonexistent/phenix/{tool.name}",
                "smoke_test_status": "passed",
                "version_text": tool.version,
                "executable_sha256": tool.executable_sha256,
            }
            for tool in identity.tools
            if tool.name.startswith("phenix.")
        ],
    )
    phenix = root / "synthetic_phenix_manifest.json"
    atomic_write_json(phenix, phenix_data)
    assert case.request.source_records_jsonl is not None
    return ReviewedFirstCopyExecutionRequest(
        funnel_directory=funnel.manifest_json.parent,
        confirmed_funnel_sha256=sha256_file(funnel.manifest_json),
        sequence_groups=case.request.sequence_groups_jsonl,
        source_records=case.request.source_records_jsonl,
        matthews_hypotheses=case.request.matthews_hypotheses_jsonl,
        mtz_preflight=case.request.mtz_preflight_jsonl,
        pipeline_config=case.request.pipeline_config,
        crystal_directory=crystal,
        execution_identity=case.execution_identity,
        phenix_manifest=phenix,
        output_json=root / "dispatch.json",
    )


def test_reviewed_execution_gate_preserves_exact_selected_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch)
    request = _execution_request(case)
    result = validate_reviewed_first_copy_execution(request)
    assert result["selected_count"] == 1
    assert result["selection_id"] == case.selection.selection_id
    assert result["a_seed_approval_granted"] is False
    assert json.loads(request.output_json.read_text()) == result


@pytest.mark.parametrize(
    "changed",
    ("confirmation", "source", "aggregate", "hypothesis", "resource", "runtime", "mtz"),
)
def test_reviewed_execution_gate_rejects_dispatch_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    request = _execution_request(_case(tmp_path, monkeypatch))
    if changed == "confirmation":
        request = replace(request, confirmed_funnel_sha256="0" * 64)
    elif changed == "source":
        request.sequence_groups.write_text(request.sequence_groups.read_text() + "\n")
    elif changed == "aggregate":
        path = request.funnel_directory / "mr_hypotheses.jsonl"
        path.write_text(path.read_text() + "\n")
    elif changed == "hypothesis":
        path = next((request.funnel_directory / "hypotheses").glob("*.jsonl"))
        document = json.loads(path.read_text())
        document["priority_features"]["expected_copy_count"] = 1
        atomic_write_json(path, document)
    elif changed == "resource":
        path = next((request.funnel_directory / "resource_plans").glob("*.json"))
        document = json.loads(path.read_text())
        document["base_cpus"] += 1
        atomic_write_json(path, document)
    elif changed == "runtime":
        document = json.loads(request.phenix_manifest.read_text())
        document["required_commands"][0]["executable_sha256"] = "0" * 64
        atomic_write_json(request.phenix_manifest, document)
    else:
        (request.crystal_directory / "input.mtz").write_bytes(b"changed MTZ")
    with pytest.raises(FirstCopySelectionError):
        validate_reviewed_first_copy_execution(request)
    assert not request.output_json.exists()


def _review(
    request: DiverseFirstCopyFunnelRequest,
    funnel: DiverseFirstCopyFunnelOutput,
    results: Path,
    output: Path,
) -> Path:
    assert request.source_records_jsonl is not None
    return build_mr_seed_review(
        MrSeedReviewRequest(
            hypotheses_jsonl=funnel.hypotheses_jsonl,
            results_jsonl=results,
            result_root=results.parent.parent,
            funnel_manifest=funnel.manifest_json,
            sequence_groups_jsonl=request.sequence_groups_jsonl,
            source_records_jsonl=request.source_records_jsonl,
            matthews_hypotheses_jsonl=request.matthews_hypotheses_jsonl,
            pipeline_config=request.pipeline_config,
            output_directory=output,
            progress=False,
        )
    ).manifest_json


def _case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision_value: PhaseIIIReviewDecisionValue = PhaseIIIReviewDecisionValue.REJECT,
    *,
    copy_count: int | None = 67,
    parent_failed: bool = False,
) -> SelectionCase:
    base = _diverse_request(tmp_path)
    groups_path = tmp_path / "sequence_groups.jsonl"
    shutil.copy2(base.sequence_groups_jsonl, groups_path)
    base = replace(base, sequence_groups_jsonl=groups_path)
    mtz = tmp_path / "input.mtz"
    mtz.write_bytes(b"synthetic MTZ boundary fixture")
    preflight = MtzPreflightRecord.model_validate_json(
        base.mtz_preflight_jsonl.read_bytes()
    )
    preflight = preflight.model_copy(
        update={
            "asu_volume_a3": 60_000.0,
            "cell_volume_a3": 240_000.0,
            "unit_cell": (20.0, 30.0, 400.0, 90.0, 90.0, 90.0),
            "mtz_sha256": sha256_file(mtz),
            "selected_observation_dataset_id": 1,
            "observation_candidate_identities": (
                MtzObservationCandidateRecord(
                    dataset_id=1, labels=("I", "SIGI"), observation_type="intensity"
                ),
            ),
        }
    )
    base.mtz_preflight_jsonl.write_text(
        canonical_json_text(preflight) + "\n", encoding="ascii"
    )
    group = SequenceGroupRecord.model_validate_json(
        base.sequence_groups_jsonl.read_bytes()
    )
    config = load_contract(base.pipeline_config, "pipeline-config", progress=False)
    assert isinstance(config, PipelineConfig)
    crystal = CrystalEntry(
        crystal_id=preflight.crystal_id, mtz=str(mtz), catalogue_id="catalogue_test"
    )
    rows = enumerate_group(group, crystal, preflight, config)
    base.matthews_hypotheses_jsonl.write_text(
        "".join(canonical_json_text(row) + "\n" for row in rows), encoding="ascii"
    )
    diffraction = build_diffraction_selection(
        crystal=crystal, preflight=preflight, crystal_manifest_sha256="e" * 64
    )
    diffraction_path = tmp_path / "diffraction.json"
    atomic_write_json(diffraction_path, diffraction.model_dump(mode="json"))
    assert base.source_records_jsonl is not None
    localisation = _phase3_localisation_bundle(
        tmp_path,
        sequence_groups_jsonl=base.sequence_groups_jsonl,
        source_records_jsonl=base.source_records_jsonl,
    )
    base = replace(
        base,
        require_localisation_policy=True,
        localisation_bundle=localisation,
        maximum_first_copy_jobs=1,
    )
    parent = build_diverse_first_copy_funnel(base)
    _fake_runtime(
        monkeypatch,
        log_text=POSITIVE_LOG,
        write_solution=True,
        returncode=1 if parent_failed else 0,
    )
    execution_path = tmp_path / "identity.json"
    result = _run(base, parent, mtz, diffraction_path, tmp_path / "parent_results")
    completed_at = datetime.now(UTC)
    review_manifest = _review(base, parent, result, tmp_path / "parent_review")
    identity_data = _execution_identity().model_dump(
        mode="python", exclude={"execution_identity_id"}
    )
    identity_data["crystal_artifacts"] = (
        ExecutionArtifactIdentity.from_content(
            scope="crystal",
            owner_id=preflight.crystal_id,
            role="mtz",
            sha256=sha256_file(mtz),
            size_bytes=mtz.stat().st_size,
        ),
    )
    identity = PhaseIIIExecutionIdentity.from_content(**identity_data)
    atomic_write_json(execution_path, identity.model_dump(mode="json"))
    owned = build_owned_phase3_a_seed_review_package(
        review_package=review_manifest.parent,
        hypotheses_jsonl=parent.hypotheses_jsonl,
        execution_identity=execution_path,
        owned_parent_run_id="gtd-reviewed-alternatives-fixture",
        crystal_id=preflight.crystal_id,
        output_directory=tmp_path / "owned_package",
    )
    registry_root = tmp_path / "owned_registry"
    registry_root.mkdir()
    registry = register_phase3_owned_run(
        parent=OwnedPhaseIIIParentRun(
            "gtd-reviewed-alternatives-fixture", "unknown-screen", "phase3-pass1"
        ),
        completed_at=completed_at,
        execution_identity=execution_path,
        packages=(
            OwnedPhaseIIIReviewPackageSource(
                preflight.crystal_id,
                PhaseIIIReviewCheckpoint.A_SEED,
                owned.manifest.parent,
            ),
        ),
        output_directory=registry_root,
    )
    solution = json.loads(review_manifest.read_text())["items"][0]["solution_id"]
    package = PhaseIIIReviewPackageManifest.model_validate_json(
        owned.manifest.read_bytes()
    )
    decisions = PhaseIIIReviewDecisionFile.from_content(
        checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
        owned_parent_run_id=registry.run_id,
        review_package_id=owned.review_package_id,
        review_package_manifest_sha256=sha256_file(owned.manifest),
        decisions=(
            PhaseIIIReviewDecision(
                crystal_id=preflight.crystal_id,
                item_id=solution,
                decision=decision_value,
                reviewer="test-reviewer",
                reviewed_at=package.created_at + timedelta(seconds=1),
                reason="Synthetic gate test; not a biological conclusion",
            ),
        ),
    )
    decisions_path = tmp_path / "parent_decisions.json"
    atomic_write_json(decisions_path, decisions.model_dump(mode="json"))
    if copy_count is None:
        deferred = MrHypothesis.model_validate_json(
            parent.deferred_cap_hypotheses_jsonl.read_text().splitlines()[0]
        )
        target = next(
            row
            for row in rows
            if row.hypothesis_id == deferred.priority_features["matthews_hypothesis_id"]
        )
        model_id = deferred.model_id
    else:
        target = next(row for row in rows if row.copy_count == copy_count)
        model_id = "model_" + "a" * 64
    selection = ReviewedFirstCopySelection.from_content(
        adapter_version="reviewed-first-copy-selection-v1",
        owned_parent_run_id=registry.run_id,
        owned_run_registry_id=registry.owned_run_registry_id,
        source_commit=registry.source_commit,
        source_tree=registry.source_tree,
        crystal_id=preflight.crystal_id,
        review_package_id=owned.review_package_id,
        review_package_manifest_sha256=sha256_file(owned.manifest),
        parent_decisions_sha256=sha256_file(decisions_path),
        parent_funnel_manifest_sha256=sha256_file(parent.manifest_json),
        trigger_solution_ids=(solution,),
        targets=(
            FirstCopySelectionTarget(
                sequence_group_id=group.sequence_group_id,
                model_id=model_id,
                matthews_hypothesis_id=target.hypothesis_id,
            ),
        ),
        maximum_attempts=1,
        reviewer="test-reviewer",
        reviewed_at=package.created_at + timedelta(seconds=2),
        reason="Synthetic copy alternative; unchanged initial one-copy search",
    )
    selection_path = tmp_path / "selection.json"
    atomic_write_json(selection_path, selection.model_dump(mode="json"))
    authority = FirstCopySelectionRequest(
        selection_path,
        sha256_file(selection_path),
        registry_root,
        parent.manifest_json.parent,
        decisions_path,
    )
    return SelectionCase(
        request=replace(
            base,
            output_directory=tmp_path / "selected_funnel",
            review_selection=authority,
        ),
        selection=selection,
        parent=parent,
        mtz=mtz,
        diffraction_selection=diffraction_path,
        execution_identity=execution_path,
    )


@pytest.mark.parametrize(
    "decision", (PhaseIIIReviewDecisionValue.REJECT, PhaseIIIReviewDecisionValue.DEFER)
)
def test_unobserved_non_top_copy_reaches_execution_after_packed_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision: PhaseIIIReviewDecisionValue,
) -> None:
    case = _case(tmp_path, monkeypatch, decision)
    selected = build_diverse_first_copy_funnel(case.request)
    hypothesis = selected.hypotheses[0]
    assert hypothesis.copy_count_expected == 67
    assert hypothesis.copy_number_to_search == 1
    assert hypothesis.priority_features["empirical_copy_frequency"] == 0
    assert hypothesis.priority_features["copy_frequency_status"] == "unobserved"
    copy_rank = hypothesis.priority_features["matthews_rank_within_candidate"]
    assert isinstance(copy_rank, int) and copy_rank > 3
    assert hypothesis.priority_features["solvent_window_status"] == "outside"
    manifest = json.loads(selected.manifest_json.read_text())
    inventory = manifest["reconsideration_inventory"]
    assert inventory["parent_selected_packed_count"] == 1
    assert (
        inventory["available_deferred_count"]
        == inventory["selected_count"] + inventory["remaining_deferred_count"]
    )
    assert inventory["new_attempted_count"] == 0
    assert inventory["a_seed_approval_granted"] is False
    calls = _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG)
    result_path = _run(
        case.request,
        selected,
        case.mtz,
        case.diffraction_selection,
        tmp_path / "selected_results",
    )
    assert len(calls) == 1
    result = json.loads(result_path.read_text())
    assert result["execution_status"] == "completed_no_hit"
    review = _review(case.request, selected, result_path, tmp_path / "selected_review")
    assert json.loads(review.read_text())["candidate_count"] == 1
    outcomes = json.loads(review.read_text())["reviewed_selection_outcomes"]
    assert outcomes["selected_count"] == outcomes["attempted_adapter_count"] == 1
    assert outcomes["completed_mr_count"] == outcomes["no_hit_count"] == 1
    assert outcomes["incomplete_mr_count"] == 0
    assert (review.parent / "approved_mr_seeds.tsv").read_text().count("\n") == 1


def test_cap_deferred_target_is_explicitly_reachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch, copy_count=None)
    selected = build_diverse_first_copy_funnel(case.request)
    row = selected.hypotheses[0]
    copy_rank = row.priority_features["matthews_rank_within_candidate"]
    assert isinstance(copy_rank, int) and copy_rank <= 3
    assert row.hypothesis_id not in {
        item.hypothesis_id for item in case.parent.hypotheses
    }


def test_failed_execution_cannot_trigger_scientific_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch, parent_failed=True)
    with pytest.raises(FirstCopySelectionError, match="not negative evidence"):
        build_diverse_first_copy_funnel(case.request)


def test_failed_selected_attempt_stays_incomplete_in_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch)
    selected = build_diverse_first_copy_funnel(case.request)
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, returncode=1)
    result = _run(
        case.request,
        selected,
        case.mtz,
        case.diffraction_selection,
        tmp_path / "failed_results",
    )
    review = _review(case.request, selected, result, tmp_path / "failed_review")
    outcomes = json.loads(review.read_text())["reviewed_selection_outcomes"]
    assert outcomes["attempted_adapter_count"] == outcomes["incomplete_mr_count"] == 1
    assert outcomes["completed_mr_count"] == outcomes["no_hit_count"] == 0


def test_already_scheduled_hypothesis_cannot_be_implicitly_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch)
    assert case.request.review_selection is not None
    authority = case.request.review_selection
    parent = case.parent.hypotheses[0]
    matthews_id = parent.priority_features["matthews_hypothesis_id"]
    assert isinstance(matthews_id, str)
    target = FirstCopySelectionTarget(
        sequence_group_id=parent.sequence_group_id,
        model_id=parent.model_id,
        matthews_hypothesis_id=matthews_id,
    )
    document = case.selection.model_dump(mode="python", exclude={"selection_id"})
    altered = ReviewedFirstCopySelection.from_content(
        **{**document, "targets": (target,)}
    )
    atomic_write_json(authority.selection_json, altered.model_dump(mode="json"))
    authority = replace(
        authority, confirmed_selection_sha256=sha256_file(authority.selection_json)
    )
    with pytest.raises(FunnelInputError, match="already scheduled"):
        build_diverse_first_copy_funnel(
            replace(case.request, review_selection=authority)
        )


def test_configured_cap_rejects_instead_of_truncating_explicit_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch)
    assert case.request.review_selection is not None
    authority = case.request.review_selection
    rows = tuple(
        MatthewsHypothesis.model_validate_json(line)
        for line in case.request.matthews_hypotheses_jsonl.read_text().splitlines()
    )
    copy68 = next(row for row in rows if row.copy_count == 68)
    other = FirstCopySelectionTarget(
        sequence_group_id=copy68.sequence_group_id,
        model_id=case.selection.targets[0].model_id,
        matthews_hypothesis_id=copy68.hypothesis_id,
    )
    targets = tuple(
        sorted(
            (*case.selection.targets, other),
            key=lambda row: (
                row.sequence_group_id,
                row.model_id,
                row.matthews_hypothesis_id,
            ),
        )
    )
    document = case.selection.model_dump(mode="python", exclude={"selection_id"})
    altered = ReviewedFirstCopySelection.from_content(
        **{**document, "targets": targets, "maximum_attempts": 2}
    )
    atomic_write_json(authority.selection_json, altered.model_dump(mode="json"))
    authority = replace(
        authority, confirmed_selection_sha256=sha256_file(authority.selection_json)
    )
    with pytest.raises(FunnelInputError, match="no truncation"):
        build_diverse_first_copy_funnel(
            replace(case.request, review_selection=authority)
        )
    assert not case.request.output_directory.exists()


@pytest.mark.parametrize(
    "mutation",
    ("source", "checksum", "crystal", "unmodelled", "stale_package", "foreign_copy"),
)
def test_reconsideration_rejects_unbound_selections_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    case = _case(tmp_path, monkeypatch)
    request = case.request
    assert request.review_selection is not None
    authority = request.review_selection
    document = case.selection.model_dump(mode="python", exclude={"selection_id"})
    if mutation == "checksum":
        authority = replace(authority, confirmed_selection_sha256="0" * 64)
    else:
        if mutation == "source":
            document["source_commit"] = "9" * 40
        elif mutation == "crystal":
            document["crystal_id"] = "foreign_crystal"
        elif mutation == "stale_package":
            document["review_package_id"] = "phase3reviewpkg_" + "9" * 64
        else:
            target = case.selection.targets[0].model_dump()
            target[
                "model_id" if mutation == "unmodelled" else "matthews_hypothesis_id"
            ] = ("model_" if mutation == "unmodelled" else "matthews_") + "9" * 64
            document["targets"] = (FirstCopySelectionTarget.model_validate(target),)
        altered = ReviewedFirstCopySelection.from_content(**document)
        atomic_write_json(authority.selection_json, altered.model_dump(mode="json"))
        authority = replace(
            authority, confirmed_selection_sha256=sha256_file(authority.selection_json)
        )
    with pytest.raises((FirstCopySelectionError, FunnelInputError)):
        build_diverse_first_copy_funnel(replace(request, review_selection=authority))
    assert not request.output_directory.exists()


def test_approved_parent_cannot_trigger_reconsideration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch, PhaseIIIReviewDecisionValue.APPROVE)
    with pytest.raises(FirstCopySelectionError, match="rejected or deferred"):
        build_diverse_first_copy_funnel(case.request)


def test_selection_contract_rejects_duplicate_targets_and_budget_excess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch)
    document = case.selection.model_dump(mode="python", exclude={"selection_id"})
    with pytest.raises(ValueError, match="unique"):
        ReviewedFirstCopySelection.from_content(
            **{**document, "maximum_attempts": 2, "targets": case.selection.targets * 2}
        )
    with pytest.raises(ValueError, match="budget"):
        ReviewedFirstCopySelection.from_content(
            **{**document, "targets": case.selection.targets * 2}
        )
