"""Bind one RF finalist to the unchanged M6 refinement/sequence implementation.

The original authenticated finalist union, explicit prior/seed, Phenix manifest
and scheduler CPU allocation own the inputs. One invocation runs exactly one
finalist through run_m6_refinement_task, preserving schema-1/v6 T12 settings,
complete catalogue, parent MTZ, labels and supported copy count. This is not the
optional Phase III Free-R output-membership contract or an identity decision.

The reference receipt binds source, upstream inputs, commands, typed JSON/JSONL
results and the complete native output inventory. Validation rederives command
identity, parameters, catalogue, metrics and sequence crosswalk. Native failure,
parse failure and skipped sequence assessment remain distinct. Numeric process
exit codes are not present in T12 JSON: retain the original runtime task logs;
never infer them from status. Nextflow owns independent scheduling and resume.
Tests simulate only external Phenix responses; native qualification is separate.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import PositiveInt
from tests.fixtures.ranking_four_arm_advancement import _source_sha256
from tests.fixtures.ranking_four_arm_continuation import ReferenceContinuationInputs
from tests.fixtures.ranking_four_arm_finalists import (
    ReferenceFinalist,
    validate_reference_finalists,
)
from tests.fixtures.ranking_four_arm_plan import _inventory
from tests.fixtures.ranking_four_arm_reference import AdmissionPrior

from genome_to_diffraction.benchmarks.m6_advancement import _object, _owned
from genome_to_diffraction.benchmarks.m6_nextflow import run_m6_refinement_task
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.refinement.brief import (
    _PROTOCOL_VERSION,
    _classify_sequence_output,
    _has_required_map_coefficients,
    _observation_label_argument,
    _read_jsonl,
    _refine_parameters,
    _refinement_metrics,
    _refinement_output_paths,
    _source_crosswalk,
)
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.manifests import PhenixInstallManifest
from genome_to_diffraction.schemas.results import (
    BriefRefinementResult,
    SequenceGroupRecord,
    SequenceMapResult,
    SourceProteinRecord,
)
from genome_to_diffraction.status import ExecutionStatus

_MANIFEST = "reference_refinement.json"


@dataclass(frozen=True)
class ReferenceRefinementRequest:
    """One original prior-bound finalist, never a loop over independent seeds."""

    inputs: ReferenceContinuationInputs
    copy_receipts: tuple[Path, ...]
    finalists_path: Path
    admission_prior: AdmissionPrior
    seed_solution_id: str
    threads: int
    output_directory: Path


class ReferenceRefinementReceipt(ContractModel):
    """Frozen native outputs, not scientific acceptance or human approval."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["rf-shared-refinement-v1"] = "rf-shared-refinement-v1"
    execution_authority_kind: Literal["truth_blind_rf_reference"] = (
        "truth_blind_rf_reference"
    )
    human_approval_granted: Literal[False] = False
    receipt_id: str
    task_key: str
    finalists_id: str
    task: ReferenceFinalist
    threads: PositiveInt
    source_sha256: dict[str, Sha256Hex]
    input_sha256: dict[str, Sha256Hex]
    output_sha256: dict[str, Sha256Hex]
    refinement: BriefRefinementResult
    sequence: SequenceMapResult


def _request(
    request: ReferenceRefinementRequest,
) -> tuple[str, ReferenceFinalist, Path]:
    if type(request.threads) is not int or not 1 <= request.threads <= 64:
        raise ValueError("reference refinement threads must be an integer in 1..64")
    finalists = validate_reference_finalists(
        request.finalists_path, request.inputs, copy_receipts=request.copy_receipts
    )
    matching = tuple(
        row
        for row in finalists.tasks
        if row.admission_prior == request.admission_prior
        and row.task.seed_solution_id == request.seed_solution_id
    )
    if len(matching) != 1:
        raise ValueError("reference refinement requires exactly one emitted finalist")
    row = matching[0]
    return (
        finalists.finalists_id,
        row,
        _finalist_bundle(request.finalists_path, row),
    )


def _finalist_bundle(path: Path, row: ReferenceFinalist) -> Path:
    task_path = _owned(
        path.resolve(strict=True).parent,
        f"{row.bundle_directory}/finalist_tasks/{row.task.seed_solution_id}/task.json",
    )
    return task_path.parents[2]


def _input_digests(request: ReferenceRefinementRequest) -> dict[str, str]:
    return {
        "reference_finalists": sha256_file(request.finalists_path),
        "phenix_manifest": sha256_file(request.inputs.prepared_inputs.phenix_manifest),
    }


def _task_key(
    task: ReferenceFinalist,
    threads: int,
    inputs: dict[str, str],
    source: dict[str, str],
) -> str:
    return content_id(
        "rfrefinetask_",
        {
            "adapter": "rf-shared-refinement-v1",
            "task": task.model_dump(mode="json"),
            "threads": threads,
            "input_sha256": inputs,
            "source_sha256": source,
        },
    )


def _identity(receipt: ReferenceRefinementReceipt) -> str:
    return content_id(
        "rfrefine_", receipt.model_dump(mode="json", exclude={"receipt_id"})
    )


def _results(
    request: ReferenceRefinementRequest, finalist: ReferenceFinalist, bundle: Path
) -> tuple[BriefRefinementResult, SequenceMapResult]:
    output = request.output_directory.resolve(strict=True)
    root = output / "t12"
    task = finalist.task
    refinement_path = root / "brief_refinement_result.json"
    sequence_path = root / "sequence_map_result.json"
    refinement = BriefRefinementResult.model_validate_json(refinement_path.read_bytes())
    sequence = SequenceMapResult.model_validate_json(sequence_path.read_bytes())
    if (
        refinement
        != BriefRefinementResult.model_validate_json(
            refinement_path.with_suffix(".jsonl").read_bytes()
        )
        or sequence
        != SequenceMapResult.model_validate_json(
            sequence_path.with_suffix(".jsonl").read_bytes()
        )
        or _object(output / "finalist_task.json") != task.model_dump(mode="json")
        or _object(output / "refinement_bundle.json")
        != {
            "schema_version": "1.0",
            "case_id": task.case_id,
            "seed_solution_id": task.seed_solution_id,
            "refinement_sha256": sha256_file(refinement_path),
            "sequence_sha256": sha256_file(sequence_path),
        }
    ):
        raise ValueError("reference refinement native result encodings or task changed")
    case = bundle / "case_bundle"
    groups_path = case / "all_sequence_groups.jsonl"
    sources_path = case / "all_source_records.jsonl"
    groups = _read_jsonl(groups_path, SequenceGroupRecord, label="sequence group")
    sources = _read_jsonl(sources_path, SourceProteinRecord, label="source record")
    group_by_id = {group.sequence_group_id: group for group in groups}
    crosswalk = _source_crosswalk(sources)
    if len(group_by_id) != len(groups) or set(group_by_id) != set(crosswalk):
        raise ValueError("reference refinement complete catalogue crosswalk changed")
    fasta = root / "exact_sequence_catalogue.fasta"
    lines: list[str] = []
    for group in groups:
        lines.append(f">{group.sequence_group_id}")
        lines.extend(
            group.sequence[i : i + 80] for i in range(0, len(group.sequence), 80)
        )
    if fasta.read_text() != "\n".join(lines) + "\n":
        raise ValueError("reference refinement full catalogue FASTA changed")
    phenix_path = request.inputs.prepared_inputs.phenix_manifest
    phenix = PhenixInstallManifest.model_validate_json(phenix_path.read_bytes())
    refine_id = content_id(
        "refine_",
        {
            "protocol": _PROTOCOL_VERSION,
            "seed_solution_id": task.seed_solution_id,
            "sequence_group_id": task.sequence_group_id,
            "input_copy_count": task.input_copy_count,
            "parent_coordinate_sha256": task.parent_coordinate_sha256,
            "parent_mtz_sha256": task.parent_mtz_sha256,
            "observation_labels": task.observation_labels,
            "catalogue_sha256": sha256_file(groups_path),
            "source_records_sha256": sha256_file(sources_path),
            "phenix_manifest_sha256": sha256_file(phenix_path),
            "resolution": task.resolution,
            "threads": request.threads,
        },
    )
    success = refinement.execution_status in {
        ExecutionStatus.COMPLETED_SUCCESS,
        ExecutionStatus.COMPLETED_WARNING,
    }
    model, mtz, map_path, difference = _refinement_output_paths(root)
    params = root / "brief_refine.eff"
    parent = bundle / "finalist_tasks" / task.seed_solution_id
    expected_command = {
        "schema_version": "1.0",
        "protocol_version": _PROTOCOL_VERSION,
        "refinement_id": refine_id,
        "refine_arguments": [
            "phenix.refine",
            str(parent / "parent_coordinate.pdb"),
            str(parent / "parent.mtz"),
            str(params),
            _observation_label_argument(task.observation_labels),
        ],
        "sequence_arguments": [
            "phenix.sequence_from_map",
            f"input_files.map_file={map_path}",
            f"input_files.model_file={model}",
            f"input_files.multiple_seq_file={fasta}",
            f"crystal_info.resolution={task.resolution:g}",
            "output_files.pdb_out=sequence_from_map.pdb",
            "control.verbose=True",
        ]
        if success
        else None,
        "inputs": {
            "parent_coordinate_sha256": task.parent_coordinate_sha256,
            "parent_mtz_sha256": task.parent_mtz_sha256,
            "observation_labels": task.observation_labels,
            "catalogue_fasta_sha256": sha256_file(fasta),
            "phenix_manifest_sha256": sha256_file(phenix_path),
        },
    }
    if (
        _object(root / "t12_command.json") != expected_command
        or params.read_text()
        != _refine_parameters(
            threads=request.threads,
            map_name=map_path.name,
            difference_map_name=difference.name,
        )
        or refinement.refinement_id != refine_id
        or refinement.seed_solution_id != task.seed_solution_id
        or refinement.sequence_group_id != task.sequence_group_id
        or refinement.input_copy_count != task.input_copy_count
        or refinement.tool_version != phenix.phenix_version
        or refinement.command_pointer != "t12_command.json"
        or refinement.raw_log_pointer != "phenix.refine.log"
        or sequence.refinement_id != refine_id
        or sequence.sequence_assessment_id
        != content_id(
            "seqmap_", {"refinement_id": refine_id, "protocol": _PROTOCOL_VERSION}
        )
        or sequence.seed_solution_id != task.seed_solution_id
        or sequence.tool_version != phenix.phenix_version
        or sequence.complete_catalogue_group_count != len(groups)
        or sequence.command_pointer != "t12_command.json"
        or sequence.raw_log_pointer != "phenix.sequence_from_map.log"
    ):
        raise ValueError(
            "reference refinement command, identity or native settings changed"
        )
    metrics = (
        refinement.initial_r_work,
        refinement.initial_r_free,
        refinement.final_r_work,
        refinement.final_r_free,
        refinement.rms_bonds,
        refinement.rms_angles,
    )
    if metrics != _refinement_metrics((root / refinement.raw_log_pointer).read_text()):
        raise ValueError("reference refinement metrics differ from native log")
    if not success and refinement.execution_status not in {
        ExecutionStatus.FAILED_TOOL_EXECUTION,
        ExecutionStatus.FAILED_PARSE,
    }:
        raise ValueError("reference refinement has an unsupported native status")
    for prefix, asset in (
        ("refined_model", model),
        ("refined_mtz", mtz),
        ("map", map_path),
        ("difference_map", difference),
    ):
        if getattr(refinement, f"{prefix}_path") != (
            asset.name if success else None
        ) or getattr(refinement, f"{prefix}_sha256") != (
            sha256_file(asset) if success else None
        ):
            raise ValueError("reference refinement native asset changed")
    if success and not _has_required_map_coefficients(mtz):
        raise ValueError("reference refinement required map coefficients changed")
    sequence_text = (root / sequence.raw_log_pointer).read_text()
    parsed = (
        sequence.execution_status,
        sequence.candidates,
        sequence.best_score,
        sequence.mean_score,
        sequence.score_sd,
        sequence.best_score_z,
        sequence.warnings,
    )
    if not success:
        expected = (ExecutionStatus.SKIPPED_INELIGIBLE, (), None, None, None, None, ())
        if sequence_text != "sequence-from-map skipped: refinement failed\n":
            raise ValueError("reference refinement skipped sequence log changed")
    elif sequence.execution_status == ExecutionStatus.FAILED_TOOL_EXECUTION:
        expected = (
            ExecutionStatus.FAILED_TOOL_EXECUTION,
            (),
            None,
            None,
            None,
            None,
            (),
        )
    else:
        expected = _classify_sequence_output(
            sequence_text,
            refinement_id=refine_id,
            groups=group_by_id,
            crosswalk=crosswalk,
        )
    sequence_model = root / "sequence_from_map.pdb"
    if (
        parsed != expected
        or sequence.output_model_path
        != (sequence_model.name if sequence_model.is_file() else None)
        or sequence.output_model_sha256
        != (sha256_file(sequence_model) if sequence_model.is_file() else None)
    ):
        raise ValueError(
            "reference refinement sequence evidence or full crosswalk changed"
        )
    return refinement, sequence


def run_reference_refinement_task(request: ReferenceRefinementRequest) -> Path:
    """Run one original M6 task, then freeze every output and recheck upstreams."""

    if request.output_directory.exists() or request.output_directory.is_symlink():
        raise ValueError("reference refinement output must not already exist")
    output = request.output_directory.resolve()
    finalists_id, task, bundle = _request(request)
    inputs, source = _input_digests(request), _source_sha256()
    run_m6_refinement_task(
        bundle,
        request.seed_solution_id,
        request.inputs.prepared_inputs.phenix_manifest,
        output,
        threads=request.threads,
    )
    refinement, sequence = _results(request, task, bundle)
    receipt = ReferenceRefinementReceipt(
        receipt_id="pending",
        task_key=_task_key(task, request.threads, inputs, source),
        finalists_id=finalists_id,
        task=task,
        threads=request.threads,
        source_sha256=source,
        input_sha256=inputs,
        output_sha256=_inventory(output, _MANIFEST),
        refinement=refinement,
        sequence=sequence,
    )
    receipt = receipt.model_copy(update={"receipt_id": _identity(receipt)})
    path = output / _MANIFEST
    atomic_write_json(path, receipt.model_dump(mode="json"))
    validate_reference_refinement_task(path, request)
    return path


def _validate_reference_refinement_outputs(
    path: Path,
    request: ReferenceRefinementRequest,
    *,
    finalists_id: str,
    task: ReferenceFinalist,
    bundle: Path,
) -> ReferenceRefinementReceipt:
    """Check one output against the caller's already-authenticated finalist union."""

    if type(request.threads) is not int or not 1 <= request.threads <= 64:
        raise ValueError("reference refinement threads must be an integer in 1..64")
    if (
        path.is_symlink()
        or path.name != _MANIFEST
        or path.resolve(strict=True).parent
        != request.output_directory.resolve(strict=True)
    ):
        raise ValueError("reference refinement requires its owned canonical receipt")
    path = path.resolve(strict=True)
    receipt = ReferenceRefinementReceipt.model_validate_json(path.read_bytes())
    inputs, source = _input_digests(request), _source_sha256()
    if (
        receipt.receipt_id != _identity(receipt)
        or receipt.task_key != _task_key(task, request.threads, inputs, source)
        or receipt.finalists_id != finalists_id
        or receipt.task != task
        or receipt.threads != request.threads
        or receipt.source_sha256 != source
        or receipt.input_sha256 != inputs
        or receipt.output_sha256 != _inventory(path.parent, _MANIFEST)
        or (receipt.refinement, receipt.sequence) != _results(request, task, bundle)
    ):
        raise ValueError(
            "reference refinement receipt, original inputs or outputs changed"
        )
    return receipt


def validate_reference_refinement_task(
    path: Path, request: ReferenceRefinementRequest
) -> ReferenceRefinementReceipt:
    """Authenticate original finalist inputs and native outputs without rerunning."""

    finalists_id, task, bundle = _request(request)
    return _validate_reference_refinement_outputs(
        path, request, finalists_id=finalists_id, task=task, bundle=bundle
    )
