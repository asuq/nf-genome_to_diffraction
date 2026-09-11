"""Execute one authenticated RF first-copy item through the production adapter.

Exactly one emitted hypothesis, its complete production-written model registry,
original prepared case and Phenix manifest determine the task. Nextflow owns
independent task scheduling and the supplied positive CPU allocation. This
adapter does not alter Phaser settings, expected composition, initial searched
copy count, score annotation, parser or failure semantics. A separate reference
receipt binds the unchanged native command and all output bytes; it grants no
review approval or M6 acceptance.

The content key binds reference preparation, hypothesis, source and threads.
Validation rederives admission and command construction, checks the two typed
result encodings and selected native assets, and rejects changed/foreign inputs
or outputs. Tool/parse/no-hit outcomes retain their original types. Native runtime
and scheduler/resume qualification remain separate from tests, which simulate
only the external Phenix response using frozen representative output.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import PositiveInt
from tests.fixtures.ranking_four_arm_advancement import _source_sha256
from tests.fixtures.ranking_four_arm_materialisation import (
    ReferenceFirstCopyTask,
    validate_reference_materialisation,
)
from tests.fixtures.ranking_four_arm_plan import _inventory
from tests.fixtures.ranking_four_arm_prepared import (
    ReferencePreparedInputs,
    validate_reference_prepared_case,
)
from tests.fixtures.ranking_four_arm_reviews import (
    ReferenceReviews,
    build_reference_reviews,
    validate_reference_reviews,
)

from genome_to_diffraction.benchmarks.m6_advancement import _object, _owned
from genome_to_diffraction.benchmarks.m6_nextflow import _phaser_output
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.mr.phaser import (
    _ADAPTER_VERSION,
    PhaserRunRequest,
    _command,
    _resolve_inputs,
    read_selected_solution_evidence,
    run_first_copy_phaser,
)
from genome_to_diffraction.ranking import DiverseFirstCopyFunnelRequest
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.results import NormalisedMrResult

_MANIFEST = "reference_first_copy.json"
_ADAPTER = "rf-shared-first-copy-v1"


@dataclass(frozen=True)
class ReferenceFirstCopyRequest:
    """One scheduler-owned hypothesis; original preparation owns all science inputs."""

    prepared_path: Path
    prepared_inputs: ReferencePreparedInputs
    hypothesis_id: str
    threads: int
    output_directory: Path


class ReferenceFirstCopyReceipt(ContractModel):
    """Exact native result binding, not a success claim or a review decision."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["rf-shared-first-copy-v1"] = _ADAPTER
    execution_authority_kind: Literal["truth_blind_rf_reference"] = (
        "truth_blind_rf_reference"
    )
    human_approval_granted: Literal[False] = False
    receipt_id: str
    task_key: str
    prepared_id: str
    task: ReferenceFirstCopyTask
    threads: PositiveInt
    source_sha256: dict[str, Sha256Hex]
    input_sha256: dict[str, Sha256Hex]
    output_sha256: dict[str, Sha256Hex]
    result: NormalisedMrResult


def _request(
    request: ReferenceFirstCopyRequest,
) -> tuple[str, ReferenceFirstCopyTask, PhaserRunRequest]:
    if type(request.threads) is not int or request.threads < 1:
        raise ValueError("reference first-copy threads must be a positive integer")
    prepared, admission = validate_reference_prepared_case(
        request.prepared_path, request.prepared_inputs
    )
    if admission is None or prepared.materialisation_path is None:
        raise ValueError("reference first-copy requires genuine materialised admission")
    materialisation_path = _owned(
        request.prepared_path.resolve(strict=True).parent, prepared.materialisation_path
    )
    materialisation = validate_reference_materialisation(
        materialisation_path, admission
    )
    matching = [
        task
        for task in materialisation.tasks
        if task.hypothesis.hypothesis_id == request.hypothesis_id
    ]
    if len(matching) != 1:
        raise ValueError(
            "reference first-copy hypothesis is outside the exact emitted union"
        )
    task = matching[0]
    if (
        task.hypothesis.copy_number_to_search != 1
        or task.hypothesis.crystal_id != prepared.task.case_id
    ):
        raise ValueError("reference first-copy changed its case or initial copy count")
    registry = _owned(materialisation_path.parent, task.model_registry_path)
    return (
        prepared.prepared_id,
        task,
        PhaserRunRequest(
            hypotheses_jsonl=_owned(materialisation_path.parent, task.hypothesis_path),
            hypothesis_id=request.hypothesis_id,
            sequence_groups_jsonl=admission.sequence_groups_jsonl,
            processed_models_jsonl=registry.parent / "processed_models.jsonl",
            model_preparation_manifest=None,
            all_model_registry_json=registry,
            preflight_jsonl=admission.mtz_preflight_jsonl,
            mtz=request.prepared_inputs.prepared_case / "reflections.mtz",
            phenix_manifest=request.prepared_inputs.phenix_manifest,
            output_directory=request.output_directory,
            threads=request.threads,
            progress=False,
        ),
    )


def _input_digests(request: ReferenceFirstCopyRequest) -> dict[str, str]:
    return {
        "reference_prepared_case": sha256_file(request.prepared_path),
        "phenix_manifest": sha256_file(request.prepared_inputs.phenix_manifest),
    }


def _task_key(
    task: ReferenceFirstCopyTask,
    threads: int,
    inputs: dict[str, str],
    source: dict[str, str],
) -> str:
    return content_id(
        "rffirst_",
        {
            "adapter_version": _ADAPTER,
            "task": task,
            "threads": threads,
            "input_sha256": inputs,
            "source_sha256": source,
        },
    )


def _result(request: PhaserRunRequest) -> NormalisedMrResult:
    root = request.output_directory.resolve(strict=True)
    resolved = _resolve_inputs(request)
    command = _object(_owned(root, "phaser_command.json"))
    expected = {
        "schema_version": "1.0",
        "adapter_version": _ADAPTER_VERSION,
        "hypothesis_id": request.hypothesis_id,
        "arguments": _command(resolved, root / "composition.fasta", request.threads),
        "threads": request.threads,
        "timeout_seconds": None,
        "model_identity_percent": resolved.model_identity_percent,
        "model_uncertainty_source": resolved.model_uncertainty_source,
        "mtz_sha256": resolved.preflight.mtz_sha256,
        "model_sha256": resolved.model.model_sha256,
        "sequence_sha256": resolved.group.sha256,
        "phenix_manifest_sha256": sha256_file(request.phenix_manifest),
        "all_model_registry_id": resolved.all_model_registry_id,
        "all_model_registry_sha256": resolved.all_model_registry_sha256,
    }
    if set(command) != {*expected, "created_at"} or any(
        command.get(key) != value for key, value in expected.items()
    ):
        raise ValueError(
            "reference first-copy native command differs from original inputs"
        )
    if (
        _owned(root, "composition.fasta").read_text()
        != f">{resolved.group.sequence_group_id}\n{resolved.group.sequence}\n"
    ):
        raise ValueError("reference first-copy full composition sequence changed")
    result = _phaser_output(root).result
    jsonl = _owned(root, "normalised_mr_result.jsonl").read_text().splitlines()
    if (
        len(jsonl) != 1
        or NormalisedMrResult.model_validate_json(jsonl[0]) != result
        or result.hypothesis_id != request.hypothesis_id
    ):
        raise ValueError("reference first-copy result identity or encodings disagree")
    _owned(root, result.raw_log_pointer)
    for relative, digest in (
        (result.solution_coordinate_path, result.solution_coordinate_sha256),
        (result.output_mtz_path, result.output_mtz_sha256),
    ):
        if (relative is None) != (digest is None):
            raise ValueError("reference first-copy native asset binding is incomplete")
        if relative is not None and sha256_file(_owned(root, relative)) != digest:
            raise ValueError("reference first-copy native asset checksum changed")
    for relative in (result.solution_file_path, result.rotation_file_path):
        if relative is not None:
            _owned(root, relative)
    if result.selected_solution is not None and (
        result.solution_coordinate_path is None
        or read_selected_solution_evidence(
            _owned(root, result.solution_coordinate_path)
        )
        != result.selected_solution
    ):
        raise ValueError("reference first-copy selected native evidence changed")
    return result


def _identity(receipt: ReferenceFirstCopyReceipt) -> str:
    return content_id(
        "rffirstreceipt_", receipt.model_dump(mode="json", exclude={"receipt_id"})
    )


def run_reference_first_copy_task(request: ReferenceFirstCopyRequest) -> Path:
    """Run one actual production first-copy adapter and retain its reference receipt."""

    output = request.output_directory
    if output.exists() or output.is_symlink():
        raise ValueError("reference first-copy output must not already exist")
    before = _input_digests(request)
    source = _source_sha256()
    prepared_id, task, native_request = _request(request)
    native = run_first_copy_phaser(native_request)
    result = _result(native_request)
    if (
        result != native.result
        or _request(request)[:2] != (prepared_id, task)
        or before != _input_digests(request)
        or source != _source_sha256()
    ):
        raise ValueError(
            "reference first-copy inputs or result changed during execution"
        )
    receipt = ReferenceFirstCopyReceipt(
        receipt_id="pending",
        task_key=_task_key(task, request.threads, before, source),
        prepared_id=prepared_id,
        task=task,
        threads=request.threads,
        source_sha256=source,
        input_sha256=before,
        output_sha256=_inventory(output, _MANIFEST),
        result=result,
    )
    receipt = receipt.model_copy(update={"receipt_id": _identity(receipt)})
    path = output / _MANIFEST
    atomic_write_json(path, receipt.model_dump(mode="json"))
    validate_reference_first_copy_task(path, request)
    return path


def validate_reference_first_copy_task(
    path: Path, request: ReferenceFirstCopyRequest
) -> ReferenceFirstCopyReceipt:
    """Authenticate one receipt at its original task paths, including native bytes."""

    if (
        path.is_symlink()
        or path.name != _MANIFEST
        or path.resolve(strict=True).parent
        != request.output_directory.resolve(strict=True)
    ):
        raise ValueError("reference first-copy requires its owned canonical receipt")
    receipt = ReferenceFirstCopyReceipt.model_validate_json(path.read_bytes())
    prepared_id, task, native_request = _request(request)
    inputs = _input_digests(request)
    source = _source_sha256()
    if (
        receipt.receipt_id != _identity(receipt)
        or receipt.task_key != _task_key(task, request.threads, inputs, source)
        or receipt.prepared_id != prepared_id
        or receipt.task != task
        or receipt.threads != request.threads
        or receipt.source_sha256 != source
        or receipt.input_sha256 != inputs
        or receipt.output_sha256 != _inventory(path.parent, _MANIFEST)
        or receipt.result != _result(native_request)
    ):
        raise ValueError(
            "reference first-copy receipt, original inputs or outputs changed"
        )
    return receipt


def _review_inputs(
    prepared_path: Path,
    prepared_inputs: ReferencePreparedInputs,
    receipts: tuple[Path, ...],
) -> tuple[Path, DiverseFirstCopyFunnelRequest, dict[str, Path]]:
    prepared, admission = validate_reference_prepared_case(
        prepared_path, prepared_inputs
    )
    if admission is None or prepared.materialisation_path is None:
        raise ValueError("reference case has no materialised cohort to review")
    materialisation_path = _owned(
        prepared_path.resolve(strict=True).parent, prepared.materialisation_path
    )
    materialisation = validate_reference_materialisation(
        materialisation_path, admission
    )
    parsed = tuple(
        ReferenceFirstCopyReceipt.model_validate_json(path.read_bytes())
        for path in receipts
    )
    expected = {task.hypothesis.hypothesis_id for task in materialisation.tasks}
    if (
        len(receipts) != len(expected)
        or {receipt.task.hypothesis.hypothesis_id for receipt in parsed} != expected
        or len({path.resolve(strict=True) for path in receipts}) != len(expected)
    ):
        raise ValueError(
            "reference review requires the exact unique first-copy receipt union"
        )
    roots: dict[str, Path] = {}
    for path, receipt in zip(receipts, parsed, strict=True):
        root = path.resolve(strict=True).parent
        hypothesis_id = receipt.task.hypothesis.hypothesis_id
        validate_reference_first_copy_task(
            path,
            ReferenceFirstCopyRequest(
                prepared_path=prepared_path,
                prepared_inputs=prepared_inputs,
                hypothesis_id=hypothesis_id,
                threads=receipt.threads,
                output_directory=root,
            ),
        )
        roots[hypothesis_id] = root
    return materialisation_path, admission, roots


def build_prepared_reference_reviews(
    prepared_path: Path,
    prepared_inputs: ReferencePreparedInputs,
    *,
    first_copy_receipts: tuple[Path, ...],
    output: Path,
) -> Path:
    """Authenticate every scheduled receipt before freezing and reviewing the union."""

    materialisation, admission, roots = _review_inputs(
        prepared_path, prepared_inputs, first_copy_receipts
    )
    return build_reference_reviews(
        materialisation,
        admission,
        source_records_jsonl=prepared_inputs.prepared_case
        / "eligible-candidates/source_records.jsonl",
        first_copy_results=tuple(roots[key] for key in sorted(roots)),
        output=output,
    )


def validate_prepared_reference_reviews(
    path: Path,
    prepared_path: Path,
    prepared_inputs: ReferencePreparedInputs,
    *,
    first_copy_receipts: tuple[Path, ...],
) -> ReferenceReviews:
    """Require frozen reviews to retain exactly their authenticated native receipts."""

    materialisation, admission, roots = _review_inputs(
        prepared_path, prepared_inputs, first_copy_receipts
    )
    reviewed = validate_reference_reviews(
        path,
        materialisation,
        admission,
        source_records_jsonl=prepared_inputs.prepared_case
        / "eligible-candidates/source_records.jsonl",
    )
    if reviewed.first_copy_result_sha256 != {
        key: _inventory(root, None) for key, root in roots.items()
    }:
        raise ValueError(
            "reference frozen review differs from its original native receipts"
        )
    return reviewed
