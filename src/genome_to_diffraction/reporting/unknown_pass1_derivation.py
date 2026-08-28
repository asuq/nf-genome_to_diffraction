"""Derive one unknown-pass-1 assessment from owned workflow evidence.

The builder accepts no scientific status, copy count, score, or final metric.
It resolves review packages from completed owned registries, authenticates the
independent decision files, parses the retained scientific records, copies the
exact evidence into one portable directory, and derives the schema-v2 terminal
assessment.  Zero-model, shortlist-only, held, and failed runs remain typed
non-claim outcomes.  A credible solution requires all four review checkpoints
and the complete Phaser/copy/refinement/sequence asset set.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.reporting.unknown_pass1 import (
    PHASE3_UNKNOWN_CRYSTAL_IDS,
    UnknownPass1AssessmentSource,
    UnknownPass1CollectionRequest,
    UnknownPass1EvidenceSource,
    collect_unknown_pass1_panel,
)
from genome_to_diffraction.review.owned_run import (
    PhaseIIIOwnedRunError,
    ResolvedOwnedPhaseIIIReviewPackage,
    resolve_phase3_owned_review_package,
    validate_phase3_owned_run_registry,
)
from genome_to_diffraction.schemas.base import ContractModel
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.schemas.results import (
    AdditionalCopyResult,
    BriefRefinementResult,
    CopyCountAssessment,
    NormalisedMrResult,
    SequenceMapResult,
)
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
    PhaseIIIReviewPackageManifest,
    UnknownPass1CollectedFileKind,
    UnknownPass1CrossChecksumManifest,
    UnknownPass1CrystalAssessment,
    UnknownPass1FinalMetricsEvidence,
    UnknownPass1ResidualContentState,
    UnknownPass1ReviewEvidence,
    UnknownPass1SolutionEvidence,
    UnknownPass1TerminalEvidence,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError


class UnknownPass1DerivationError(InputContractError):
    """Owned pass-1 evidence cannot form one honest terminal assessment."""


@dataclass(frozen=True, slots=True)
class UnknownPass1AssessmentDerivationRequest:
    """Exact evidence paths for one crystal's terminal derivation."""

    crystal_id: str
    execution_identity: Path
    run_manifest: Path
    job_result: Path
    crystallographic_registry: Path
    crystallographic_decision: Path
    screen_registry: Path
    a_seed_decision: Path | None
    single_component_registry: Path | None
    sequence_decision: Path | None
    composition_decision: Path | None
    copy_assessment: Path | None
    packing_result: Path | None
    combined_coordinate: Path | None
    refinement_result: Path | None
    sequence_result: Path | None
    refined_coordinate: Path | None
    refined_mtz: Path | None
    review_map: Path | None
    output_directory: Path


@dataclass(frozen=True, slots=True)
class UnknownPass1AssessmentDerivationOutput:
    assessment: Path
    evidence_manifest: Path
    scientific_status: str


_DERIVATION_SPEC_FIELDS = frozenset(
    {
        "schema_version",
        "crystal_id",
        "execution_identity",
        "run_manifest",
        "job_result",
        "crystallographic_registry",
        "crystallographic_decision",
        "screen_registry",
        "a_seed_decision",
        "single_component_registry",
        "sequence_decision",
        "composition_decision",
        "copy_assessment",
        "packing_result",
        "combined_coordinate",
        "refinement_result",
        "sequence_result",
        "refined_coordinate",
        "refined_mtz",
        "review_map",
    }
)


def _spec_path(value: object, label: str, *, optional: bool = False) -> Path | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value.startswith("/"):
        raise UnknownPass1DerivationError(f"{label} must be an absolute path")
    return Path(value)


def derivation_request_from_spec(
    *,
    spec_path: Path,
    output_directory: Path,
) -> UnknownPass1AssessmentDerivationRequest:
    """Load one fixed path-bearing local spec; paths never enter output identity."""

    try:
        spec = load_json_document(_file(spec_path, "derivation spec"))
    except ContractLoadError as error:
        raise UnknownPass1DerivationError("derivation spec is malformed") from error
    if (
        not isinstance(spec, dict)
        or set(spec) != _DERIVATION_SPEC_FIELDS
        or spec.get("schema_version") != "1.0"
        or not isinstance(spec.get("crystal_id"), str)
    ):
        raise UnknownPass1DerivationError(
            "derivation spec differs from its fixed fields"
        )
    required = {
        name: cast(Path, _spec_path(spec[name], name))
        for name in (
            "execution_identity",
            "run_manifest",
            "job_result",
            "crystallographic_registry",
            "crystallographic_decision",
            "screen_registry",
        )
    }
    optional = {
        name: _spec_path(spec[name], name, optional=True)
        for name in _DERIVATION_SPEC_FIELDS
        if name
        not in {
            "schema_version",
            "crystal_id",
            *required,
        }
    }
    return UnknownPass1AssessmentDerivationRequest(
        crystal_id=str(spec["crystal_id"]),
        execution_identity=required["execution_identity"],
        run_manifest=required["run_manifest"],
        job_result=required["job_result"],
        crystallographic_registry=required["crystallographic_registry"],
        crystallographic_decision=required["crystallographic_decision"],
        screen_registry=required["screen_registry"],
        a_seed_decision=optional["a_seed_decision"],
        single_component_registry=optional["single_component_registry"],
        sequence_decision=optional["sequence_decision"],
        composition_decision=optional["composition_decision"],
        copy_assessment=optional["copy_assessment"],
        packing_result=optional["packing_result"],
        combined_coordinate=optional["combined_coordinate"],
        refinement_result=optional["refinement_result"],
        sequence_result=optional["sequence_result"],
        refined_coordinate=optional["refined_coordinate"],
        refined_mtz=optional["refined_mtz"],
        review_map=optional["review_map"],
        output_directory=output_directory,
    )


def _file(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise UnknownPass1DerivationError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise UnknownPass1DerivationError(f"{label} is absent") from error
    if not resolved.is_file():
        raise UnknownPass1DerivationError(f"{label} must be a regular file")
    return resolved


def _present(path: Path | None, label: str) -> Path:
    if path is None:
        raise UnknownPass1DerivationError(f"{label} is absent")
    return path


def _identity(path: Path) -> PhaseIIIExecutionIdentity:
    try:
        return PhaseIIIExecutionIdentity.model_validate_json(
            _file(path, "execution identity").read_bytes()
        )
    except (OSError, ValidationError, ValueError) as error:
        raise UnknownPass1DerivationError(
            "execution identity violates schema-v2"
        ) from error


def _job_result(path: Path) -> dict[str, object]:
    try:
        value = load_json_document(_file(path, "job result"))
    except ContractLoadError as error:
        raise UnknownPass1DerivationError("job result is malformed") from error
    if not isinstance(value, dict):
        raise UnknownPass1DerivationError("job result must be an object")
    return value


def _run_manifest(path: Path) -> dict[str, object]:
    try:
        value = load_json_document(_file(path, "owned run manifest"))
    except ContractLoadError as error:
        raise UnknownPass1DerivationError("owned run manifest is malformed") from error
    if not isinstance(value, dict):
        raise UnknownPass1DerivationError("owned run manifest must be an object")
    return value


def _decision(path: Path) -> PhaseIIIReviewDecisionFile:
    try:
        return PhaseIIIReviewDecisionFile.model_validate_json(
            _file(path, "review decision").read_bytes()
        )
    except (OSError, ValidationError, ValueError) as error:
        raise UnknownPass1DerivationError(
            "review decision violates schema-v2"
        ) from error


def _resolved_review(
    registry: Path,
    decision_path: Path,
    *,
    crystal_id: str,
    checkpoint: PhaseIIIReviewCheckpoint,
    item_id: str | None = None,
) -> tuple[
    ResolvedOwnedPhaseIIIReviewPackage,
    PhaseIIIReviewDecisionFile,
    tuple[UnknownPass1ReviewEvidence, ...],
]:
    try:
        owned = validate_phase3_owned_run_registry(registry)
        resolved = resolve_phase3_owned_review_package(
            registry,
            run_id=owned.run_id,
            crystal_id=crystal_id,
            checkpoint=checkpoint,
        )
    except (OSError, PhaseIIIOwnedRunError, ValueError) as error:
        raise UnknownPass1DerivationError(
            f"{checkpoint.value} package is not owned"
        ) from error
    decision = _decision(decision_path)
    try:
        package = PhaseIIIReviewPackageManifest.model_validate_json(
            resolved.package_manifest.read_bytes()
        )
    except (OSError, ValidationError, ValueError) as error:
        raise UnknownPass1DerivationError(
            f"{checkpoint.value} package manifest is invalid"
        ) from error
    permitted = {
        (target.crystal_id, target.item_id) for target in package.permitted_targets
    }
    rows = tuple(
        row
        for row in decision.decisions
        if row.crystal_id == crystal_id
        and (item_id is None or row.item_id == item_id)
    )
    if (
        not rows
        or decision.checkpoint is not checkpoint
        or decision.owned_parent_run_id != resolved.parent.run_id
        or decision.review_package_id != resolved.review_package_id
        or decision.review_package_manifest_sha256
        != resolved.review_package_manifest_sha256
        or any(row.crystal_id != crystal_id for row in decision.decisions)
        or any(
            (row.crystal_id, row.item_id) not in permitted
            or row.reviewed_at < package.created_at
            for row in decision.decisions
        )
    ):
        raise UnknownPass1DerivationError(
            f"{checkpoint.value} decision differs from its owned package"
        )
    decision_sha256 = sha256_file(_file(decision_path, "review decision"))
    evidence = tuple(
        UnknownPass1ReviewEvidence(
            checkpoint=checkpoint,
            package_crystal_id=crystal_id,
            package_item_id=row.item_id,
            review_package_id=resolved.review_package_id,
            review_package_manifest_sha256=(
                resolved.review_package_manifest_sha256
            ),
            decision_crystal_id=crystal_id,
            decision_item_id=row.item_id,
            decision_file_id=decision.decision_file_id,
            decision_file_sha256=decision_sha256,
            decision=row.decision,
        )
        for row in rows
    )
    return resolved, decision, evidence


def _single_record[Record: ContractModel](
    path: Path,
    schema: type[Record],
    label: str,
) -> Record:
    payload = _file(path, label).read_bytes()
    lines = payload.splitlines()
    if len(lines) != 1:
        raise UnknownPass1DerivationError(f"{label} must contain one record")
    try:
        return schema.model_validate_json(lines[0])
    except (ValidationError, ValueError) as error:
        raise UnknownPass1DerivationError(f"{label} is invalid") from error


def _copy_assessment(path: Path, *, state_id: str) -> CopyCountAssessment:
    """Load one selected state from a package-owned JSON or JSONL record set."""

    payload = _file(path, "copy assessment").read_bytes()
    try:
        try:
            records = (CopyCountAssessment.model_validate_json(payload),)
        except (ValidationError, ValueError):
            records = tuple(
                CopyCountAssessment.model_validate_json(line)
                for line in payload.splitlines()
                if line.strip()
            )
    except (ValidationError, ValueError) as error:
        raise UnknownPass1DerivationError("copy assessment is invalid") from error
    matches = tuple(item for item in records if item.seed_solution_id == state_id)
    if len(matches) != 1:
        raise UnknownPass1DerivationError(
            "copy assessment lacks one exact reviewed state"
        )
    return matches[0]


def _copy_file(
    source: Path,
    destination: Path,
    *,
    role: str,
    kind: str,
) -> dict[str, object]:
    resolved = _file(source, role)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(resolved, destination)
    return {
        "kind": kind,
        "role": role,
        "relative_path": destination.as_posix(),
        "sha256": sha256_file(destination),
        "size_bytes": destination.stat().st_size,
    }


def _copy_review(
    root: Path,
    resolved: ResolvedOwnedPhaseIIIReviewPackage,
    decision: Path,
    *,
    checkpoint: PhaseIIIReviewCheckpoint,
) -> list[dict[str, object]]:
    destination = root / "reviews" / checkpoint.value / "package"
    shutil.copytree(resolved.package_directory, destination)
    copied: list[dict[str, object]] = []
    for index, path in enumerate(sorted(destination.rglob("*")), start=1):
        if path.is_file():
            copied.append(
                {
                    "kind": "evidence",
                    "role": f"{checkpoint.value}_package_{index:04d}",
                    "relative_path": path.relative_to(root).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    decision_destination = root / "reviews" / checkpoint.value / "decision.json"
    copied.append(
        _copy_file(
            decision,
            decision_destination,
            role=f"{checkpoint.value}_decision",
            kind="evidence",
        )
    )
    copied[-1]["relative_path"] = decision_destination.relative_to(root).as_posix()
    return copied


def _failure_status(failure_class: object) -> ExecutionStatus:
    if failure_class in {
        "scheduler_rejection",
        "queue_timeout",
        "node_failure",
        "environment_failure",
        "filesystem_failure",
        "transfer_failure",
    }:
        return ExecutionStatus.FAILED_INFRASTRUCTURE
    return ExecutionStatus.FAILED_TOOL_EXECUTION


def derive_unknown_pass1_assessment(
    request: UnknownPass1AssessmentDerivationRequest,
) -> UnknownPass1AssessmentDerivationOutput:
    """Derive and publish one portable, collector-ready crystal assessment."""

    output = request.output_directory.absolute()
    if output.exists() or output.is_symlink():
        raise UnknownPass1DerivationError("derivation output must be absent")
    identity = _identity(request.execution_identity)
    run_manifest = _run_manifest(request.run_manifest)
    job = _job_result(request.job_result)
    if (
        run_manifest.get("schema_version") != "1.0"
        or run_manifest.get("run_id") != job.get("run_id")
        or run_manifest.get("profile") != job.get("profile")
        or run_manifest.get("commit") != identity.source_commit
        or run_manifest.get("nf_helper_commit") != identity.nf_helper_commit
        or run_manifest.get("pixi_lock_sha256") != identity.pixi_lock_sha256
        or run_manifest.get("source_snapshot_status") != "immutable"
        or run_manifest.get("site_id") not in {"marmic", "viper-cpu"}
    ):
        raise UnknownPass1DerivationError(
            "owned run manifest differs from its job or execution identity"
        )
    try:
        crystallographic_registry = validate_phase3_owned_run_registry(
            request.crystallographic_registry
        )
        screen_registry = validate_phase3_owned_run_registry(request.screen_registry)
    except (OSError, PhaseIIIOwnedRunError, ValueError) as error:
        raise UnknownPass1DerivationError(
            "required owned registry is invalid"
        ) from error
    if (
        crystallographic_registry.execution_identity_id
        != identity.execution_identity_id
        or screen_registry.execution_identity_id != identity.execution_identity_id
    ):
        raise UnknownPass1DerivationError("review registries use another execution")

    crystal_package, _, crystal_reviews = _resolved_review(
        request.crystallographic_registry,
        request.crystallographic_decision,
        crystal_id=request.crystal_id,
        checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
    )
    if len(crystal_reviews) != 1:
        raise UnknownPass1DerivationError(
            "crystallographic checkpoint requires one exact decision"
        )
    crystal_review = crystal_reviews[0]
    try:
        a_package = resolve_phase3_owned_review_package(
            request.screen_registry,
            run_id=screen_registry.run_id,
            crystal_id=request.crystal_id,
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
        )
    except (OSError, PhaseIIIOwnedRunError, ValueError) as error:
        raise UnknownPass1DerivationError("A-seed package is absent") from error
    try:
        a_manifest = PhaseIIIReviewPackageManifest.model_validate_json(
            a_package.package_manifest.read_bytes()
        )
    except (OSError, ValidationError, ValueError) as error:
        raise UnknownPass1DerivationError(
            "A-seed package manifest is invalid"
        ) from error
    candidate_shortlist = bool(a_manifest.permitted_targets)

    single_registry = None
    if request.single_component_registry is not None:
        try:
            single_registry = validate_phase3_owned_run_registry(
                request.single_component_registry
            )
        except (OSError, PhaseIIIOwnedRunError, ValueError) as error:
            raise UnknownPass1DerivationError(
                "single-component registry is invalid"
            ) from error
        if (
            single_registry.execution_identity_id != identity.execution_identity_id
            or single_registry.profile != "unknown-single-component"
            or single_registry.phase != "phase3-pass1"
        ):
            raise UnknownPass1DerivationError(
                "single-component registry uses another execution"
            )

    failure_class = job.get("failure_class")
    if failure_class == "success":
        if job.get("scheduler_state") != "COMPLETED" or job.get("exit_code") != 0:
            raise UnknownPass1DerivationError("successful job result is contradictory")
    elif not isinstance(failure_class, str):
        raise UnknownPass1DerivationError("job result lacks a failure class")

    review_pairs: list[
        tuple[
            ResolvedOwnedPhaseIIIReviewPackage,
            Path,
            PhaseIIIReviewCheckpoint,
        ]
    ] = [
        (
            crystal_package,
            request.crystallographic_decision,
            PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        )
    ]
    review_evidence = list(crystal_reviews)

    a_resolved: ResolvedOwnedPhaseIIIReviewPackage | None = None
    a_reviews: tuple[UnknownPass1ReviewEvidence, ...] = ()
    if request.a_seed_decision is not None:
        a_resolved, _, a_reviews = _resolved_review(
            request.screen_registry,
            request.a_seed_decision,
            crystal_id=request.crystal_id,
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
        )
        review_pairs.append(
            (
                a_resolved,
                request.a_seed_decision,
                PhaseIIIReviewCheckpoint.A_SEED,
            )
        )
        review_evidence.extend(a_reviews)
    elif candidate_shortlist:
        raise UnknownPass1DerivationError(
            "candidate shortlist lacks its mandatory A-seed decision"
        )
    solution: UnknownPass1SolutionEvidence | None = None
    final_metrics: UnknownPass1FinalMetricsEvidence | None = None
    science_paths = (
        request.copy_assessment,
        request.packing_result,
        request.combined_coordinate,
        request.refinement_result,
        request.sequence_result,
        request.refined_coordinate,
        request.refined_mtz,
        request.review_map,
    )
    has_solution_inputs = any(path is not None for path in science_paths)
    if has_solution_inputs and any(path is None for path in science_paths):
        raise UnknownPass1DerivationError(
            "solution derivation requires the complete scientific asset set"
        )

    if has_solution_inputs:
        if (
            request.a_seed_decision is None
            or request.single_component_registry is None
            or request.sequence_decision is None
            or request.composition_decision is None
        ):
            raise UnknownPass1DerivationError(
                "solution derivation requires all final owned reviews"
            )
        copy_assessment_path = _present(
            request.copy_assessment, "copy assessment"
        )
        packing_result_path = _present(request.packing_result, "packing result")
        combined_coordinate_path = _present(
            request.combined_coordinate, "combined coordinate"
        )
        refinement_result_path = _present(
            request.refinement_result, "refinement result"
        )
        sequence_result_path = _present(
            request.sequence_result, "sequence result"
        )
        refined_coordinate_path = _present(
            request.refined_coordinate, "refined coordinate"
        )
        refined_mtz_path = _present(request.refined_mtz, "refined MTZ")
        review_map_path = _present(request.review_map, "review map")
        single_component_registry = _present(
            request.single_component_registry,
            "single-component registry",
        )
        a_seed_decision = _present(request.a_seed_decision, "A-seed decision")
        sequence_decision = _present(
            request.sequence_decision,
            "sequence decision",
        )
        composition_decision = _present(
            request.composition_decision,
            "composition decision",
        )
        if single_registry is None:
            raise UnknownPass1DerivationError(
                "solution derivation lacks its single-component registry"
            )
        if a_resolved is None or request.a_seed_decision != a_seed_decision:
            raise UnknownPass1DerivationError(
                "solution derivation lacks its A-seed review"
            )
        sequence_resolved, _, sequence_reviews = _resolved_review(
            single_component_registry,
            sequence_decision,
            crystal_id=request.crystal_id,
            checkpoint=PhaseIIIReviewCheckpoint.SEQUENCE,
        )
        composition_resolved, _, composition_reviews = _resolved_review(
            single_component_registry,
            composition_decision,
            crystal_id=request.crystal_id,
            checkpoint=PhaseIIIReviewCheckpoint.COMPOSITION,
        )
        if len(a_reviews) != 1 or len(sequence_reviews) != 1 or len(
            composition_reviews
        ) != 1:
            raise UnknownPass1DerivationError(
                "solution derivation requires one selected item per final review"
            )
        a_review = a_reviews[0]
        sequence_review = sequence_reviews[0]
        composition_review = composition_reviews[0]
        if (
            a_review.decision is not PhaseIIIReviewDecisionValue.APPROVE
            or sequence_review.decision
            not in {
                PhaseIIIReviewDecisionValue.APPROVE,
                PhaseIIIReviewDecisionValue.RETAIN_ALTERNATIVE,
            }
            or composition_review.decision
            not in {
                PhaseIIIReviewDecisionValue.APPROVE,
                PhaseIIIReviewDecisionValue.RETAIN_PARTIAL,
            }
            or a_review.package_item_id != composition_review.package_item_id
        ):
            raise UnknownPass1DerivationError(
                "final review decisions do not support one state and sequence"
            )
        state_id = composition_review.package_item_id
        copies = _copy_assessment(copy_assessment_path, state_id=state_id)
        packing_path = _file(packing_result_path, "packing result")
        try:
            packing: NormalisedMrResult | AdditionalCopyResult = (
                NormalisedMrResult.model_validate_json(
                    packing_path.read_bytes().splitlines()[0]
                )
            )
        except (IndexError, ValidationError, ValueError):
            try:
                packing = AdditionalCopyResult.model_validate_json(
                    packing_path.read_bytes().splitlines()[0]
                )
            except (IndexError, ValidationError, ValueError) as error:
                raise UnknownPass1DerivationError(
                    "packing result is invalid"
                ) from error
        refinement = _single_record(
            refinement_result_path,
            BriefRefinementResult,
            "refinement result",
        )
        sequence = _single_record(
            sequence_result_path,
            SequenceMapResult,
            "sequence result",
        )
        sequence_group_id = sequence_review.package_item_id
        if isinstance(packing, NormalisedMrResult):
            packing_hypothesis_id = packing.hypothesis_id
            packing_copy_count = packing.placed_copy_count
            packing_status = packing.execution_status
            packing_passed = (
                packing.packing_summary.get("top_solution_packed") is True
            )
            packing_coordinate_sha256 = packing.solution_coordinate_sha256
        else:
            packing_hypothesis_id = packing.hypothesis_id
            packing_copy_count = packing.best_supported_copy_count
            packing_status = packing.execution_status
            packing_passed = packing.top_solution_packed
            packing_coordinate_sha256 = packing.output_coordinate_sha256
        combined_sha256 = sha256_file(
            _file(combined_coordinate_path, "combined coordinate")
        )
        refined_sha256 = sha256_file(
            _file(refined_coordinate_path, "refined coordinate")
        )
        refined_mtz_sha256 = sha256_file(_file(refined_mtz_path, "refined MTZ"))
        review_map_sha256 = sha256_file(_file(review_map_path, "review map"))
        if (
            copies.seed_solution_id != state_id
            or not copies.reached_expected_copy_count
            or copies.best_supported_copy_count != packing_copy_count
            or copies.hypothesis_id != packing_hypothesis_id
            or packing_status is not ExecutionStatus.COMPLETED_HIT
            or not packing_passed
            or packing_coordinate_sha256 != combined_sha256
            or refinement.seed_solution_id != state_id
            or refinement.sequence_group_id != copies.sequence_group_id
            or refinement.input_copy_count != copies.best_supported_copy_count
            or refinement.refined_model_sha256 != refined_sha256
            or refinement.refined_mtz_sha256 != refined_mtz_sha256
            or refinement.map_sha256 != review_map_sha256
            or refinement.final_r_work is None
            or refinement.final_r_free is None
            or sequence.seed_solution_id != state_id
            or sequence.refinement_id != refinement.refinement_id
            or not any(
                item.sequence_group_id == sequence_group_id
                for item in sequence.candidates
            )
        ):
            raise UnknownPass1DerivationError(
                "scientific records do not support the reviewed state"
            )
        residual = (
            UnknownPass1ResidualContentState.NONE_DETECTED
            if composition_review.decision is PhaseIIIReviewDecisionValue.APPROVE
            else UnknownPass1ResidualContentState.PRESENT_OR_SUSPECTED
        )
        final_metrics = UnknownPass1FinalMetricsEvidence(
            schema_version="2.0",
            owned_parent_run_id=single_registry.run_id,
            execution_identity_id=identity.execution_identity_id,
            crystal_id=request.crystal_id,
            state_id=state_id,
            sequence_group_id=sequence_group_id,
            refinement_id=refinement.refinement_id,
            final_r_work=refinement.final_r_work,
            final_r_free=refinement.final_r_free,
            residual_content_state=residual,
        )
        solution = UnknownPass1SolutionEvidence(
            crystal_id=request.crystal_id,
            state_id=state_id,
            search_sequence_group_id=copies.sequence_group_id,
            sequence_group_id=sequence_group_id,
            requested_copy_count=copies.expected_copy_count,
            observed_copy_count=copies.best_supported_copy_count,
            copy_counts_supported=True,
            copy_support_evidence_sha256=sha256_file(copy_assessment_path),
            packing_passed=True,
            packing_evidence_sha256=sha256_file(packing_path),
            refinement_completed=True,
            combined_coordinate_sha256=combined_sha256,
            refined_coordinate_sha256=refined_sha256,
            refined_mtz_sha256=refined_mtz_sha256,
            review_map_sha256=review_map_sha256,
            refinement_evidence_sha256=sha256_file(refinement_result_path),
            sequence_evidence_sha256=sha256_file(sequence_result_path),
            final_r_work=refinement.final_r_work,
            final_r_free=refinement.final_r_free,
            parsed_final_metrics_evidence_sha256="0" * 64,
            residual_content_state=residual,
        )
        review_pairs.extend(
            (
                (
                    sequence_resolved,
                    sequence_decision,
                    PhaseIIIReviewCheckpoint.SEQUENCE,
                ),
                (
                    composition_resolved,
                    composition_decision,
                    PhaseIIIReviewCheckpoint.COMPOSITION,
                ),
            )
        )
        review_evidence.extend((*sequence_reviews, *composition_reviews))
        parent_run_id = single_registry.run_id
        execution_status = ExecutionStatus.COMPLETED_HIT
    else:
        parent_run_id = (
            single_registry.run_id
            if single_registry is not None
            else screen_registry.run_id
        )
        if failure_class != "success":
            execution_status = _failure_status(failure_class)
        elif crystal_review.decision is PhaseIIIReviewDecisionValue.HOLD:
            execution_status = ExecutionStatus.SKIPPED_POLICY
        elif candidate_shortlist:
            execution_status = ExecutionStatus.COMPLETED_SUCCESS
        else:
            execution_status = ExecutionStatus.COMPLETED_NO_HIT

    expected_profile = (
        "unknown-single-component"
        if single_registry is not None
        else "unknown-screen"
    )
    if (
        job.get("run_id") != parent_run_id
        or job.get("profile") != expected_profile
    ):
        raise UnknownPass1DerivationError(
            "terminal job result belongs to another owned run"
        )

    output.mkdir(parents=True)
    evidence_rows: list[dict[str, object]] = []
    for resolved, decision_path, checkpoint in review_pairs:
        evidence_rows.extend(
            _copy_review(
                output,
                resolved,
                decision_path,
                checkpoint=checkpoint,
            )
        )

    if solution is not None:
        science_sources = (
            (copy_assessment_path, "copy_support"),
            (packing_result_path, "packing"),
            (combined_coordinate_path, "combined_coordinate"),
            (refined_coordinate_path, "refined_coordinate"),
            (refined_mtz_path, "refined_mtz"),
            (review_map_path, "review_map"),
            (refinement_result_path, "refinement"),
            (sequence_result_path, "sequence_map"),
        )
        for source, role in science_sources:
            suffix = "".join(source.suffixes) or ".bin"
            destination = output / "science" / f"{role}{suffix}"
            row = _copy_file(source, destination, role=role, kind="result")
            row["relative_path"] = destination.relative_to(output).as_posix()
            evidence_rows.append(row)
        assert final_metrics is not None
        final_metrics_path = output / "science/final_metrics.json"
        atomic_write_json(final_metrics_path, final_metrics.model_dump(mode="json"))
        evidence_rows.append(
            {
                "kind": "result",
                "role": "final_metrics",
                "relative_path": final_metrics_path.relative_to(output).as_posix(),
                "sha256": sha256_file(final_metrics_path),
                "size_bytes": final_metrics_path.stat().st_size,
            }
        )
        solution = solution.model_copy(
            update={
                "parsed_final_metrics_evidence_sha256": sha256_file(
                    final_metrics_path
                )
            }
        )

    execution_identity_path = _file(
        request.execution_identity,
        "execution identity",
    )
    run_manifest_path = _file(request.run_manifest, "owned run manifest")
    job_result_path = _file(request.job_result, "job result")
    for source, role in (
        (execution_identity_path, "execution_identity"),
        (run_manifest_path, "terminal_run_manifest"),
        (job_result_path, "terminal_job_result"),
    ):
        destination = output / "science" / f"{role}.json"
        row = _copy_file(source, destination, role=role, kind="result")
        row["relative_path"] = destination.relative_to(output).as_posix()
        evidence_rows.append(row)

    terminal = UnknownPass1TerminalEvidence(
        schema_version="3.0",
        owned_parent_run_id=parent_run_id,
        execution_identity_id=identity.execution_identity_id,
        crystal_id=request.crystal_id,
        execution_status=execution_status,
        candidate_shortlist_present=candidate_shortlist,
        state_id=solution.state_id if solution is not None else None,
        sequence_group_id=(
            solution.sequence_group_id if solution is not None else None
        ),
        parent_profile=expected_profile,
        execution_identity_sha256=sha256_file(execution_identity_path),
        run_manifest_sha256=sha256_file(run_manifest_path),
        job_result_sha256=sha256_file(job_result_path),
    )
    terminal_path = output / "science/terminal_result.json"
    atomic_write_json(terminal_path, terminal.model_dump(mode="json"))
    evidence_rows.append(
        {
            "kind": "result",
            "role": "terminal_result",
            "relative_path": terminal_path.relative_to(output).as_posix(),
            "sha256": sha256_file(terminal_path),
            "size_bytes": terminal_path.stat().st_size,
        }
    )
    assessment = UnknownPass1CrystalAssessment.from_evidence(
        owned_parent_run_id=parent_run_id,
        execution_identity_id=identity.execution_identity_id,
        crystal_id=request.crystal_id,
        crystallographic_review_item_id=crystal_review.package_item_id,
        execution_status=execution_status,
        terminal_evidence_sha256=sha256_file(terminal_path),
        candidate_shortlist_present=candidate_shortlist,
        solution_evidence=solution,
        review_evidence=tuple(
            sorted(
                review_evidence,
                key=lambda item: (
                    item.checkpoint.value,
                    item.package_crystal_id,
                    item.package_item_id,
                ),
            )
        ),
    )
    assessment_path = output / "assessment.json"
    atomic_write_json(assessment_path, assessment.model_dump(mode="json"))
    manifest_path = output / "derivation_manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "adapter_version": "unknown-pass1-owned-derivation-v1",
            "crystal_id": request.crystal_id,
            "assessment": {
                "relative_path": assessment_path.relative_to(output).as_posix(),
                "sha256": sha256_file(assessment_path),
                "size_bytes": assessment_path.stat().st_size,
            },
            "evidence": sorted(
                evidence_rows,
                key=lambda item: (str(item["kind"]), str(item["role"])),
            ),
        },
    )
    return UnknownPass1AssessmentDerivationOutput(
        assessment=assessment_path,
        evidence_manifest=manifest_path,
        scientific_status=assessment.scientific_status.value,
    )


def collect_derived_unknown_pass1_panel(
    *,
    input_root: Path,
    output_directory: Path,
) -> UnknownPass1CrossChecksumManifest:
    """Load exactly three derivation manifests and run the strict panel collector."""

    root = input_root.resolve(strict=True)
    assessments: list[UnknownPass1AssessmentSource] = []
    evidence: list[UnknownPass1EvidenceSource] = []
    for crystal_id in PHASE3_UNKNOWN_CRYSTAL_IDS:
        directory = root / crystal_id
        try:
            manifest = load_json_document(directory / "derivation_manifest.json")
        except ContractLoadError as error:
            raise UnknownPass1DerivationError(
                f"derivation manifest is invalid for {crystal_id}"
            ) from error
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != "1.0"
            or manifest.get("adapter_version")
            != "unknown-pass1-owned-derivation-v1"
            or manifest.get("crystal_id") != crystal_id
            or not isinstance(manifest.get("assessment"), dict)
            or not isinstance(manifest.get("evidence"), list)
        ):
            raise UnknownPass1DerivationError(
                f"derivation manifest fields differ for {crystal_id}"
            )
        assessment = manifest["assessment"]
        assessments.append(
            UnknownPass1AssessmentSource(
                crystal_id=crystal_id,
                relative_path=(
                    directory / str(assessment["relative_path"])
                ).relative_to(root).as_posix(),
                sha256=str(assessment["sha256"]),
                size_bytes=int(assessment["size_bytes"]),
            )
        )
        for item in manifest["evidence"]:
            if not isinstance(item, dict):
                raise UnknownPass1DerivationError(
                    f"derivation evidence is invalid for {crystal_id}"
                )
            evidence.append(
                UnknownPass1EvidenceSource(
                    crystal_id=crystal_id,
                    kind=UnknownPass1CollectedFileKind(str(item["kind"])),
                    role=str(item["role"]),
                    relative_path=(
                        directory / str(item["relative_path"])
                    ).relative_to(root).as_posix(),
                    sha256=str(item["sha256"]),
                    size_bytes=int(item["size_bytes"]),
                )
            )
    return collect_unknown_pass1_panel(
        UnknownPass1CollectionRequest(
            input_root=root,
            assessment_sources=tuple(assessments),
            evidence_allow_list=tuple(evidence),
            output_directory=output_directory,
        )
    )


__all__ = [
    "UnknownPass1AssessmentDerivationOutput",
    "UnknownPass1AssessmentDerivationRequest",
    "UnknownPass1DerivationError",
    "collect_derived_unknown_pass1_panel",
    "derivation_request_from_spec",
    "derive_unknown_pass1_assessment",
]
