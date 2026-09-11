"""Bind one RF copy chain to original preparation and authenticated MR reviews.

Inputs retain the exact prepared case, complete first-copy receipt union and
paired reviews. Metadata planning emits separate prior/seed items; Nextflow
owns their scheduling. Execution reuses the shared reference copy adapter with
the original full-registry model, sequence, MTZ/preflight and Phenix manifest.
No human or production M6 authority is manufactured. Cross-prior chains remain
separate because their authenticated review authority differs.

The receipt binds source, upstream manifests, allocated threads, every native
file and the shared parent/child validator. Native parameters are reconstructed
at their original task paths, including successive retained parents. Empty
recommendation sets emit no tasks; complete roots retain zero actual attempts;
tool/parse/unsupported outcomes are never relabelled. Changed, foreign or
missing evidence fails. Tests simulate external Phenix responses; native runtime,
scheduler, resource and resume qualification remain separate acceptance gates.
"""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from pydantic import Field, PositiveInt
from tests.fixtures.ranking_four_arm_advancement import (
    _source_sha256,
    validate_reference_advancement,
)
from tests.fixtures.ranking_four_arm_copy import (
    _reference_authority,
    run_reference_copy_task,
    validate_reference_copy_receipt,
)
from tests.fixtures.ranking_four_arm_first_copy import (
    validate_prepared_reference_reviews,
)
from tests.fixtures.ranking_four_arm_plan import _inventory
from tests.fixtures.ranking_four_arm_prepared import (
    ReferencePreparedInputs,
    validate_reference_prepared_case,
)
from tests.fixtures.ranking_four_arm_reference import AdmissionPrior
from tests.fixtures.ranking_four_arm_reviews import ReferenceReviews

from genome_to_diffraction.benchmarks.m6_advancement import _object, _owned
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.model_registry import load_all_eligible_model_registry
from genome_to_diffraction.mr.add_copy import (
    AddCopyRunRequest,
    _parameters,
    _resolve_review_seed,
)
from genome_to_diffraction.ranking import DiverseFirstCopyFunnelRequest
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.results import AdditionalCopyResult

_MANIFEST = "reference_copy.json"


@dataclass(frozen=True)
class ReferenceContinuationInputs:
    """Original case and the complete authenticated first-copy review join."""

    prepared_path: Path
    prepared_inputs: ReferencePreparedInputs
    reviews_path: Path
    first_copy_receipts: tuple[Path, ...]


class ReferenceCopyTask(ContractModel):
    """One explicit prior-bound selected seed, shared only within its paired arms."""

    admission_prior: AdmissionPrior
    seed_solution_id: str
    hypothesis_id: str
    sequence_group_id: str
    model_id: str
    expected_copy_count: PositiveInt
    first_copy_placed_count: PositiveInt
    advancement_manifest_sha256: Sha256Hex


@dataclass(frozen=True)
class ReferencePreparedCopyRequest:
    """One Nextflow item with no configurable scientific-input overrides."""

    inputs: ReferenceContinuationInputs
    admission_prior: AdmissionPrior
    seed_solution_id: str
    threads: int
    output_directory: Path


class ReferencePreparedCopyReceipt(ContractModel):
    """Original-input and complete native-output binding, not an acceptance claim."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["rf-prepared-copy-v1"] = "rf-prepared-copy-v1"
    execution_authority_kind: Literal["truth_blind_rf_reference"] = (
        "truth_blind_rf_reference"
    )
    human_approval_granted: Literal[False] = False
    receipt_id: str
    task_key: str
    task: ReferenceCopyTask
    threads: PositiveInt
    source_sha256: dict[str, Sha256Hex]
    input_sha256: dict[str, Sha256Hex]
    output_sha256: dict[str, Sha256Hex]
    native_receipt_sha256: Sha256Hex
    native_attempt_count: int = Field(ge=0)


def _context(
    inputs: ReferenceContinuationInputs,
) -> tuple[Path, DiverseFirstCopyFunnelRequest, ReferenceReviews]:
    reviews = validate_prepared_reference_reviews(
        inputs.reviews_path,
        inputs.prepared_path,
        inputs.prepared_inputs,
        first_copy_receipts=inputs.first_copy_receipts,
    )
    prepared, admission = validate_reference_prepared_case(
        inputs.prepared_path, inputs.prepared_inputs
    )
    if admission is None or prepared.materialisation_path is None:
        raise ValueError("reference continuation requires materialised admission")
    return (
        _owned(inputs.prepared_path.parent, prepared.materialisation_path),
        admission,
        reviews,
    )


def reference_copy_tasks(
    inputs: ReferenceContinuationInputs,
) -> tuple[ReferenceCopyTask, ...]:
    """Emit the exact paired-authority union without executing independent seeds."""

    materialisation, admission, reviews = _context(inputs)
    return _tasks(inputs, materialisation, admission, reviews)


def _tasks(
    inputs: ReferenceContinuationInputs,
    materialisation: Path,
    admission: DiverseFirstCopyFunnelRequest,
    reviews: ReferenceReviews,
) -> tuple[ReferenceCopyTask, ...]:
    """Derive task metadata from a context already authenticated within this call."""

    tasks: list[ReferenceCopyTask] = []
    for cohort in reviews.cohorts:
        if cohort.advancement_manifest is None:
            if cohort.status != "no_scheduled_hypotheses":
                raise ValueError("reference reviewed cohort lacks its authority")
            continue
        authority_path = _owned(inputs.reviews_path.parent, cohort.advancement_manifest)
        authority = validate_reference_advancement(
            authority_path,
            admission,
            hypotheses_jsonl=materialisation.parent
            / cohort.admission_prior
            / "mr_hypotheses.jsonl",
        )
        tasks.extend(
            ReferenceCopyTask(
                admission_prior=cohort.admission_prior,
                seed_solution_id=row.solution_id,
                hypothesis_id=row.hypothesis_id,
                sequence_group_id=row.sequence_group_id,
                model_id=row.model_id,
                expected_copy_count=row.expected_copy_count,
                first_copy_placed_count=row.first_copy_placed_count,
                advancement_manifest_sha256=sha256_file(authority_path),
            )
            for row in authority.manifest.recommended
        )
    if len(tasks) > 20:
        raise ValueError("reference copy union exceeds its paired-arm budgets")
    return tuple(tasks)


def _request(
    request: ReferencePreparedCopyRequest,
) -> tuple[ReferenceCopyTask, AddCopyRunRequest, DiverseFirstCopyFunnelRequest, Path]:
    if type(request.threads) is not int or request.threads < 1:
        raise ValueError("reference copy threads must be a positive integer")
    materialisation, admission, reviews = _context(request.inputs)
    matches = tuple(
        task
        for task in _tasks(request.inputs, materialisation, admission, reviews)
        if task.admission_prior == request.admission_prior
        and task.seed_solution_id == request.seed_solution_id
    )
    if len(matches) != 1:
        raise ValueError("reference copy seed is outside its exact prior-bound union")
    task = matches[0]
    cohort = next(
        row for row in reviews.cohorts if row.admission_prior == request.admission_prior
    )
    if cohort.advancement_manifest is None:
        raise ValueError("reference copy seed lacks its original authority")
    authority = _owned(request.inputs.reviews_path.parent, cohort.advancement_manifest)
    cohort_root = materialisation.parent / request.admission_prior
    registry = load_all_eligible_model_registry(
        cohort_root / "model_registry/all_model_registry.json"
    )
    models = tuple(
        row
        for row in registry.lookup(task.sequence_group_id).models
        if row.model_id == task.model_id
    )
    if len(models) != 1:
        raise ValueError("reference selected seed lacks its unique registered model")
    return (
        task,
        AddCopyRunRequest(
            review_validation_json=None,
            review_package_manifest=None,
            seed_solution_id=task.seed_solution_id,
            hypotheses_jsonl=cohort_root / "mr_hypotheses.jsonl",
            sequence_groups_jsonl=admission.sequence_groups_jsonl,
            preflight_jsonl=admission.mtz_preflight_jsonl,
            mtz=request.inputs.prepared_inputs.prepared_case / "reflections.mtz",
            search_model=_owned(registry.root, models[0].model_path),
            phenix_manifest=request.inputs.prepared_inputs.phenix_manifest,
            output_directory=request.output_directory,
            threads=request.threads,
            progress=False,
        ),
        admission,
        authority,
    )


def _input_digests(inputs: ReferenceContinuationInputs) -> dict[str, str]:
    return {
        "reference_prepared_case": sha256_file(inputs.prepared_path),
        "reference_reviews": sha256_file(inputs.reviews_path),
        "phenix_manifest": sha256_file(inputs.prepared_inputs.phenix_manifest),
    }


def _native_binding(
    request: AddCopyRunRequest,
    admission: DiverseFirstCopyFunnelRequest,
    authority: Path,
) -> tuple[str, int]:
    root = request.output_directory.resolve(strict=True)
    receipt = validate_reference_copy_receipt(
        root, request, admission, advancement_manifest=authority
    )
    summary = _object(root / "additional_copy_series_summary.json")
    paths = summary.get("result_paths", [])
    if not isinstance(paths, list) or len(paths) != receipt[1]:
        raise ValueError("reference copy native result paths changed")
    current = request
    for relative in paths:
        result_path = _owned(root / "series", relative)
        attempt_root = result_path.parent
        current = replace(current, output_directory=attempt_root)
        resolved = _resolve_review_seed(
            current, _reference_authority(current, admission, authority)
        )
        command = _object(attempt_root / "phaser_command.json")
        if (
            command.get("threads") != request.threads
            or command.get("timeout_seconds") is not None
            or command.get("phenix_manifest_sha256")
            != sha256_file(request.phenix_manifest)
            or command.get("arguments")
            != ["phenix.phaser", str(attempt_root / "add_copy.eff")]
            or (attempt_root / "composition.fasta").read_text()
            != f">{resolved.group.sequence_group_id}\n{resolved.group.sequence}\n"
            or (attempt_root / "add_copy.eff").read_text()
            != _parameters(
                resolved, attempt_root / "composition.fasta", request.threads
            )
        ):
            raise ValueError(
                "reference copy native settings differ from original inputs"
            )
        result = AdditionalCopyResult.model_validate_json(result_path.read_text())
        if result.additional_copy_supported:
            current = replace(
                current,
                parent_result_jsonl=result_path,
                parent_coordinate=_owned(attempt_root, result.output_coordinate_path),
            )
    return receipt


def _identity(receipt: ReferencePreparedCopyReceipt) -> str:
    return content_id(
        "rfcopyreceipt_", receipt.model_dump(mode="json", exclude={"receipt_id"})
    )


def _task_key(
    task: ReferenceCopyTask,
    threads: int,
    inputs: dict[str, str],
    source: dict[str, str],
) -> str:
    return content_id(
        "rfcopy_",
        {
            "adapter_version": "rf-prepared-copy-v1",
            "task": task,
            "threads": threads,
            "input_sha256": inputs,
            "source_sha256": source,
        },
    )


def run_prepared_reference_copy_task(request: ReferencePreparedCopyRequest) -> Path:
    """Execute one authenticated dependent chain and bind every resulting byte."""

    if request.output_directory.exists() or request.output_directory.is_symlink():
        raise ValueError("reference prepared-copy output must not already exist")
    before = _input_digests(request.inputs)
    source = _source_sha256()
    task, native, admission, authority = _request(request)
    run_reference_copy_task(native, admission, advancement_manifest=authority)
    native_digest, count = _native_binding(native, admission, authority)
    if before != _input_digests(request.inputs) or source != _source_sha256():
        raise ValueError("reference copy original inputs changed during execution")
    receipt = ReferencePreparedCopyReceipt(
        receipt_id="pending",
        task_key=_task_key(task, request.threads, before, source),
        task=task,
        threads=request.threads,
        source_sha256=source,
        input_sha256=before,
        output_sha256=_inventory(request.output_directory, _MANIFEST),
        native_receipt_sha256=native_digest,
        native_attempt_count=count,
    )
    receipt = receipt.model_copy(update={"receipt_id": _identity(receipt)})
    path = request.output_directory / _MANIFEST
    atomic_write_json(path, receipt.model_dump(mode="json"))
    validate_prepared_reference_copy_task(path, request)
    return path


def validate_prepared_reference_copy_task(
    path: Path, request: ReferencePreparedCopyRequest
) -> ReferencePreparedCopyReceipt:
    """Rederive the prior-bound task and validate its original native chain."""

    if (
        path.is_symlink()
        or path.name != _MANIFEST
        or path.resolve(strict=True).parent
        != request.output_directory.resolve(strict=True)
    ):
        raise ValueError("reference copy requires its owned canonical receipt")
    receipt = ReferencePreparedCopyReceipt.model_validate_json(path.read_bytes())
    task, native, admission, authority = _request(request)
    native_digest, count = _native_binding(native, admission, authority)
    inputs = _input_digests(request.inputs)
    source = _source_sha256()
    if (
        receipt.receipt_id != _identity(receipt)
        or receipt.task_key != _task_key(task, request.threads, inputs, source)
        or receipt.task != task
        or receipt.threads != request.threads
        or receipt.source_sha256 != source
        or receipt.input_sha256 != inputs
        or receipt.output_sha256 != _inventory(path.parent, _MANIFEST)
        or receipt.native_receipt_sha256 != native_digest
        or receipt.native_attempt_count != count
    ):
        raise ValueError("reference prepared-copy receipt, inputs or outputs changed")
    return receipt
