"""Authenticate reviewer-selected alternatives without automatic reopening.

Inputs are one independently checksum-confirmed selection, its owned A-review
registry, original funnel and exact parent decisions. The validator reuses the
review ownership, package, decision and model-registry boundaries. It returns
validated target authority to the production funnel; it never executes MR or
approves a seed. Missing, stale, foreign, duplicated or altered evidence fails
with ``FirstCopySelectionError`` before output publication. Failed parent tasks
remain incomplete evidence and cannot trigger this route as scientific negatives.

The selection content ID and its byte checksum bind the output/cache identity.
No external command is required. Focused coverage is in
``tests/unit/test_reviewed_first_copy_selection.py``.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.model_registry.all_eligible import (
    AllEligibleModelRegistry,
    load_all_eligible_model_registry,
)
from genome_to_diffraction.review.mr_seed import validate_mr_seed_review_evidence
from genome_to_diffraction.review.owned_run import (
    resolve_phase3_owned_review_package,
    validate_phase3_owned_run_registry,
)
from genome_to_diffraction.review.phase3_package import validate_phase3_review_package
from genome_to_diffraction.review.phase3_stage import (
    validate_phase3_review_decision_binding,
)
from genome_to_diffraction.schemas.io import load_contract, load_json_document
from genome_to_diffraction.schemas.manifests import PhenixInstallManifest
from genome_to_diffraction.schemas.mr_resources import MrResourcePlan
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MtzPreflightRecord,
    NormalisedMrResult,
)
from genome_to_diffraction.schemas.v2 import (
    DiffractionSelection,
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
)
from genome_to_diffraction.schemas.v2.reconsideration import ReviewedFirstCopySelection
from genome_to_diffraction.schemas.v2.review import validate_phase3_review_relative_path
from genome_to_diffraction.status import ExecutionStatus, InputContractError


class FirstCopySelectionError(InputContractError):
    """Explicit deferred-hypothesis authority could not be authenticated."""


@dataclass(frozen=True, slots=True)
class FirstCopySelectionRequest:
    """Exact files required by the reviewer-triggered production funnel."""

    selection_json: Path
    confirmed_selection_sha256: str
    owned_run_registry: Path
    parent_funnel_directory: Path
    parent_decisions: Path


@dataclass(frozen=True, slots=True)
class ValidatedFirstCopySelection:
    """Authenticated target authority and unchanged parent evidence inventory."""

    selection: ReviewedFirstCopySelection
    selection_sha256: str
    model_registry: AllEligibleModelRegistry
    parent_hypotheses: tuple[MrHypothesis, ...]
    previous_hypothesis_ids: tuple[str, ...]
    parent_execution_identity_id: str
    parent_completed_count: int
    parent_incomplete_count: int
    parent_selected_packed_count: int


def _object(path: Path) -> dict[str, Any]:
    value = load_json_document(path)
    if not isinstance(value, dict):
        raise FirstCopySelectionError(f"expected a JSON object: {path.name}")
    return value


def _package_path(root: Path, relative: object) -> Path:
    if not isinstance(relative, str):
        raise FirstCopySelectionError("package evidence path is absent")
    validate_phase3_review_relative_path(relative)
    result = root / relative
    if result.is_symlink() or not result.resolve(strict=True).is_relative_to(
        root.resolve(strict=True)
    ):
        raise FirstCopySelectionError("package evidence path escapes its root")
    return result


def validate_first_copy_selection(
    request: FirstCopySelectionRequest,
    *,
    source_input_sha256: dict[str, str],
    preflights: tuple[MtzPreflightRecord, ...],
) -> ValidatedFirstCopySelection:
    """Bind selected alternatives to their owned source, inputs and A review."""

    try:
        return _validate(request, source_input_sha256, preflights)
    except FirstCopySelectionError:
        raise
    except (OSError, ValidationError, ValueError, InputContractError) as error:
        raise FirstCopySelectionError(
            f"reviewed first-copy selection is invalid: {error}"
        ) from error


def _validate(
    request: FirstCopySelectionRequest,
    source_input_sha256: dict[str, str],
    preflights: tuple[MtzPreflightRecord, ...],
) -> ValidatedFirstCopySelection:
    for path in (request.selection_json, request.parent_decisions):
        if path.is_symlink() or not path.is_file():
            raise FirstCopySelectionError("selection inputs must be regular files")
    selection_sha256 = sha256_file(request.selection_json, progress=False)
    if selection_sha256 != request.confirmed_selection_sha256:
        raise FirstCopySelectionError("selection checksum differs from confirmation")
    selection = ReviewedFirstCopySelection.model_validate_json(
        request.selection_json.read_bytes()
    )
    registry = validate_phase3_owned_run_registry(request.owned_run_registry)
    if (
        selection.owned_run_registry_id != registry.owned_run_registry_id
        or selection.source_commit != registry.source_commit
        or selection.source_tree != registry.source_tree
    ):
        raise FirstCopySelectionError("selection source or owned registry differs")
    resolved = resolve_phase3_owned_review_package(
        request.owned_run_registry,
        run_id=selection.owned_parent_run_id,
        crystal_id=selection.crystal_id,
        checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
    )
    if (
        selection.review_package_id != resolved.review_package_id
        or selection.review_package_manifest_sha256
        != resolved.review_package_manifest_sha256
    ):
        raise FirstCopySelectionError("selection names a stale review package")
    package = validate_phase3_review_package(resolved.package_directory)
    decisions_sha256 = sha256_file(request.parent_decisions, progress=False)
    if decisions_sha256 != selection.parent_decisions_sha256:
        raise FirstCopySelectionError("parent decisions checksum differs")
    decisions = load_contract(
        request.parent_decisions, "phase3-review-decisions", progress=False
    )
    if not isinstance(decisions, PhaseIIIReviewDecisionFile):
        raise FirstCopySelectionError("parent decisions use the wrong contract")
    validate_phase3_review_decision_binding(
        parent=resolved.parent,
        checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
        package=package,
        package_sha256=resolved.review_package_manifest_sha256,
        decisions=decisions,
    )
    decisions_by_id = {row.item_id: row for row in decisions.decisions}
    for solution_id in selection.trigger_solution_ids:
        decision = decisions_by_id.get(solution_id)
        if decision is None or decision.decision not in {
            PhaseIIIReviewDecisionValue.REJECT,
            PhaseIIIReviewDecisionValue.DEFER,
        }:
            raise FirstCopySelectionError(
                "selection requires rejected or deferred A review"
            )
        if selection.reviewed_at < decision.reviewed_at:
            raise FirstCopySelectionError("selection predates its triggering review")

    parent_root = request.parent_funnel_directory.resolve(strict=True)
    parent_manifest_path = _package_path(parent_root, "funnel_manifest.json")
    if sha256_file(parent_manifest_path) != selection.parent_funnel_manifest_sha256:
        raise FirstCopySelectionError("parent funnel checksum differs")
    parent_manifest = _object(parent_manifest_path)
    if parent_manifest.get("adapter_version") not in {
        "multi-source-first-copy-funnel-v9-prior-factors",
        "reviewed-first-copy-funnel-v1",
    }:
        raise FirstCopySelectionError("parent funnel is not a current Phase III funnel")
    parent_source_inputs = parent_manifest.get(
        "source_input_sha256", parent_manifest.get("input_sha256")
    )
    if parent_source_inputs != source_input_sha256:
        raise FirstCopySelectionError("selection inputs differ from the parent funnel")
    review_artifact = next(
        (
            row
            for row in package.evidence_inventory
            if row.role == "mr_seed_review_manifest"
        ),
        None,
    )
    if review_artifact is None:
        raise FirstCopySelectionError("owned package lacks its MR-review evidence")
    review_manifest_path = _package_path(
        resolved.package_directory, review_artifact.relative_path
    )
    parent_hypotheses_path = _package_path(parent_root, "mr_hypotheses.jsonl")
    validate_mr_seed_review_evidence(
        package_manifest=review_manifest_path,
        hypotheses_jsonl=parent_hypotheses_path,
        crystal_id=selection.crystal_id,
    )
    review = _object(review_manifest_path)
    reviewed_inputs = review["package_identity"]["input_sha256"]
    if (
        reviewed_inputs.get("funnel_manifest")
        != selection.parent_funnel_manifest_sha256
    ):
        raise FirstCopySelectionError("owned review belongs to another funnel")
    for name in (
        "sequence_groups",
        "source_records",
        "matthews_hypotheses",
        "pipeline_config",
    ):
        if reviewed_inputs.get(name) != source_input_sha256.get(name):
            raise FirstCopySelectionError("owned review source inputs differ")
    parent_hypotheses = tuple(
        MrHypothesis.model_validate_json(line)
        for line in parent_hypotheses_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    earlier_ids = parent_manifest.get("reviewed_previous_hypothesis_ids", [])
    if (
        not isinstance(earlier_ids, list)
        or any(not isinstance(value, str) for value in earlier_ids)
        or earlier_ids != sorted(set(earlier_ids))
    ):
        raise FirstCopySelectionError("previous scheduled inventory is malformed")
    current_ids = {row.hypothesis_id for row in parent_hypotheses}
    if current_ids.intersection(earlier_ids):
        raise FirstCopySelectionError("parent rescheduled an earlier hypothesis")
    previous_ids = tuple(sorted(current_ids.union(earlier_ids)))
    model_info = parent_manifest.get("model_registry")
    if not isinstance(model_info, dict):
        raise FirstCopySelectionError("parent funnel lacks its all-model registry")
    model_root = _package_path(parent_root, model_info.get("path"))
    model_manifest_path = _package_path(model_root, "all_model_registry.json")
    if sha256_file(model_manifest_path) != model_info.get("registry_manifest_sha256"):
        raise FirstCopySelectionError("parent model registry checksum differs")
    models = load_all_eligible_model_registry(model_manifest_path)
    if models.manifest.registry_id != model_info.get("registry_id"):
        raise FirstCopySelectionError("parent model registry identity differs")
    for target in selection.targets:
        if target.model_id not in {
            row.model_id for row in models.lookup(target.sequence_group_id).models
        }:
            raise FirstCopySelectionError("selected target has no owned eligible model")

    identity = PhaseIIIExecutionIdentity.model_validate_json(
        (request.owned_run_registry / "phase3_execution_identity.json").read_bytes()
    )
    mtz = next(
        (
            row
            for row in identity.crystal_artifacts
            if row.owner_id == selection.crystal_id and row.role == "mtz"
        ),
        None,
    )
    selected_preflights = tuple(
        row for row in preflights if row.crystal_id == selection.crystal_id
    )
    if (
        len(selected_preflights) != 1
        or mtz is None
        or mtz.sha256 != selected_preflights[0].mtz_sha256
    ):
        raise FirstCopySelectionError("selected crystal MTZ differs from the owned run")
    completed = packed = 0
    for item in review["items"]:
        result_path = _package_path(
            review_manifest_path.parent, item["copied_assets"]["normalised_result"]
        )
        lines = tuple(
            line
            for line in result_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if len(lines) != 1:
            raise FirstCopySelectionError(
                "parent result must contain exactly one record"
            )
        result = NormalisedMrResult.model_validate_json(lines[0])
        if result.hypothesis_id != item["hypothesis_id"]:
            raise FirstCopySelectionError("parent result hypothesis differs")
        terminal = result.execution_status in {
            ExecutionStatus.COMPLETED_HIT,
            ExecutionStatus.COMPLETED_NO_HIT,
        }
        if item["solution_id"] in selection.trigger_solution_ids and not terminal:
            raise FirstCopySelectionError(
                "failed or incomplete execution is not negative evidence"
            )
        completed += terminal
        packed += bool(
            terminal
            and result.selected_solution is not None
            and result.selected_solution.packing_clash_count == 0
        )
    if (
        sha256_file(request.selection_json) != selection_sha256
        or sha256_file(request.parent_decisions) != decisions_sha256
    ):
        raise FirstCopySelectionError("review authority changed during validation")
    return ValidatedFirstCopySelection(
        selection,
        selection_sha256,
        models,
        parent_hypotheses,
        previous_ids,
        resolved.execution_identity_id,
        completed,
        len(parent_hypotheses) - completed,
        packed,
    )


@dataclass(frozen=True, slots=True)
class ReviewedFirstCopyExecutionRequest:
    """Independently confirmed selection output and its exact execution inputs."""

    funnel_directory: Path
    confirmed_funnel_sha256: str
    sequence_groups: Path
    source_records: Path
    matthews_hypotheses: Path
    mtz_preflight: Path
    pipeline_config: Path
    crystal_directory: Path
    execution_identity: Path
    phenix_manifest: Path
    output_json: Path


def validate_reviewed_first_copy_execution(
    request: ReviewedFirstCopyExecutionRequest,
) -> dict[str, Any]:
    """Gate the shared Nextflow executor on a confirmed, exact-source funnel.

    This read/validate boundary publishes only a checksum-bound dispatch record.
    It does not change the selection, launch Phaser or grant A approval.
    """

    try:
        return _validate_execution(request)
    except FirstCopySelectionError:
        raise
    except (OSError, ValidationError, ValueError, InputContractError) as error:
        raise FirstCopySelectionError(
            f"reviewed first-copy execution is invalid: {error}"
        ) from error


def _validate_execution(
    request: ReviewedFirstCopyExecutionRequest,
) -> dict[str, Any]:
    root = request.funnel_directory.resolve(strict=True)
    manifest_path = _package_path(root, "funnel_manifest.json")
    manifest_sha256 = sha256_file(manifest_path)
    if manifest_sha256 != request.confirmed_funnel_sha256:
        raise FirstCopySelectionError(
            "execution funnel checksum differs from confirmation"
        )
    manifest = _object(manifest_path)
    if manifest.get("adapter_version") != "reviewed-first-copy-funnel-v1":
        raise FirstCopySelectionError("execution requires a reviewed first-copy funnel")
    selection = ReviewedFirstCopySelection.model_validate(
        manifest.get("review_selection")
    )
    identity = PhaseIIIExecutionIdentity.model_validate_json(
        request.execution_identity.read_bytes()
    )
    if identity.execution_identity_id != manifest.get("parent_execution_identity_id"):
        raise FirstCopySelectionError(
            "execution source, tools or inputs differ from the parent"
        )
    phenix = PhenixInstallManifest.model_validate_json(
        request.phenix_manifest.read_bytes()
    )
    execution_tools = {tool.name: tool for tool in identity.tools}
    commands = {command.name: command for command in phenix.required_commands}
    expected_commands = {name for name in execution_tools if name.startswith("phenix.")}
    if (
        phenix.status != "verified"
        or set(commands) != expected_commands
        or any(
            command.executable_sha256 is None
            or command.executable_sha256 != execution_tools[name].executable_sha256
            or (command.version_text or phenix.phenix_version)
            != execution_tools[name].version
            for name, command in commands.items()
        )
    ):
        raise FirstCopySelectionError(
            "execution Phenix runtime differs from the parent"
        )
    source_paths = {
        "sequence_groups": request.sequence_groups,
        "source_records": request.source_records,
        "matthews_hypotheses": request.matthews_hypotheses,
        "mtz_preflight": request.mtz_preflight,
        "pipeline_config": request.pipeline_config,
    }
    source_digests = manifest.get("source_input_sha256")
    if not isinstance(source_digests, dict) or any(
        sha256_file(path) != source_digests.get(name)
        for name, path in source_paths.items()
    ):
        raise FirstCopySelectionError("reviewed execution input checksums differ")
    diffraction = DiffractionSelection.model_validate_json(
        (request.crystal_directory / "phase3_diffraction_selection.json").read_bytes()
    )
    preflights = tuple(
        MtzPreflightRecord.model_validate_json(line)
        for line in request.mtz_preflight.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    selected = tuple(
        row for row in preflights if row.crystal_id == selection.crystal_id
    )
    if (
        len(selected) != 1
        or diffraction.crystal_id != selection.crystal_id
        or diffraction.preflight_id != selected[0].preflight_id
        or diffraction.mtz_sha256 != selected[0].mtz_sha256
        or sha256_file(request.crystal_directory / "input.mtz")
        != diffraction.mtz_sha256
    ):
        raise FirstCopySelectionError("reviewed execution diffraction binding differs")
    model_info = manifest.get("model_registry")
    if not isinstance(model_info, dict):
        raise FirstCopySelectionError("execution model registry is absent")
    registry_path = _package_path(
        _package_path(root, model_info.get("path")), "all_model_registry.json"
    )
    if sha256_file(registry_path) != model_info.get("registry_manifest_sha256"):
        raise FirstCopySelectionError("execution model registry checksum differs")
    models = load_all_eligible_model_registry(registry_path)
    if models.manifest.registry_id != model_info.get("registry_id"):
        raise FirstCopySelectionError("execution model registry identity differs")
    hypothesis_inventory = _package_path(root, "mr_hypotheses.jsonl")
    resource_inventory = _package_path(root, "mr_resource_plans.jsonl")
    if sha256_file(hypothesis_inventory) != manifest.get(
        "mr_hypotheses_sha256"
    ) or sha256_file(resource_inventory) != manifest.get("mr_resource_plans_sha256"):
        raise FirstCopySelectionError(
            "execution hypothesis or resource inventory checksum differs"
        )
    resource_rows = tuple(
        json.loads(line)
        for line in resource_inventory.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if any(
        not isinstance(row, dict)
        or set(row) != {"hypothesis_id", "resource_plan"}
        or not isinstance(row["hypothesis_id"], str)
        for row in resource_rows
    ):
        raise FirstCopySelectionError("execution resource inventory is malformed")
    resources = {
        row["hypothesis_id"]: MrResourcePlan.model_validate(row["resource_plan"])
        for row in resource_rows
    }
    if len(resources) != len(resource_rows):
        raise FirstCopySelectionError(
            "execution resource inventory contains duplicates"
        )
    hypotheses = tuple(
        MrHypothesis.model_validate_json(line)
        for line in hypothesis_inventory.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    expected_targets = {
        (row.sequence_group_id, row.model_id, row.matthews_hypothesis_id)
        for row in selection.targets
    }
    observed_targets: set[tuple[str, str, str]] = set()
    for row in hypotheses:
        matthews_id = row.priority_features.get("matthews_hypothesis_id")
        if (
            not isinstance(matthews_id, str)
            or row.crystal_id != selection.crystal_id
            or row.copy_number_to_search != 1
            or row.fixed_solution_id is not None
            or row.priority_features.get("review_selection_id")
            != selection.selection_id
        ):
            raise FirstCopySelectionError(
                "execution hypothesis differs from the explicit selection"
            )
        observed_targets.add((row.sequence_group_id, row.model_id, matthews_id))
        record = _package_path(root, f"hypotheses/{row.hypothesis_id}.jsonl")
        if MrHypothesis.model_validate_json(record.read_bytes()) != row:
            raise FirstCopySelectionError(
                "dispatched hypothesis differs from aggregate inventory"
            )
        plan_path = _package_path(root, f"resource_plans/{row.hypothesis_id}.json")
        plan = MrResourcePlan.model_validate_json(plan_path.read_bytes())
        if plan != resources.get(row.hypothesis_id):
            raise FirstCopySelectionError(
                "dispatched resource plan differs from aggregate inventory"
            )
    if observed_targets != expected_targets or len(hypotheses) != len(expected_targets):
        raise FirstCopySelectionError(
            "execution does not exactly cover selected targets"
        )
    if set(resources) != {row.hypothesis_id for row in hypotheses}:
        raise FirstCopySelectionError(
            "execution resource coverage differs from selected targets"
        )
    output = {
        "adapter_version": "reviewed-first-copy-execution-gate-v1",
        "funnel_id": manifest["funnel_id"],
        "funnel_manifest_sha256": manifest_sha256,
        "selection_id": selection.selection_id,
        "owned_parent_run_id": selection.owned_parent_run_id,
        "execution_identity_id": identity.execution_identity_id,
        "crystal_id": selection.crystal_id,
        "hypothesis_ids": sorted(row.hypothesis_id for row in hypotheses),
        "selected_count": len(hypotheses),
        "phenix_manifest_sha256": sha256_file(request.phenix_manifest),
        "a_seed_approval_granted": False,
    }
    if request.output_json.exists() or request.output_json.is_symlink():
        raise FirstCopySelectionError("execution-gate output already exists")
    atomic_write_json(request.output_json, output)
    return output


__all__ = [
    "FirstCopySelectionError",
    "FirstCopySelectionRequest",
    "ReviewedFirstCopyExecutionRequest",
    "ValidatedFirstCopySelection",
    "validate_first_copy_selection",
    "validate_reviewed_first_copy_execution",
]
