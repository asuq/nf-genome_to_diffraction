"""Freeze genuine RF continuation parents for the unchanged refinement adapter.

Inputs are the original prepared/review binding and the exact prior/seed union
of authenticated prepared-copy receipts. No independent scientific task is run
here. Each arm's stage inventory is rederived separately before materialising
the complete union of retained parents. Original MTZ, observation labels,
resolution, supported copy count and full catalogue/locus crosswalk are retained.
The production finalist task is reused solely as scientific input data, never
as M6 execution authority. Nextflow must fan out the emitted finalists.

The manifest binds source, upstream receipts, stage accounting and every frozen
file. Validation reconstructs both metadata and copied-byte inventories from the
original receipts, so rehashing an altered parent cannot authenticate it. Empty
admission and empty recommendations remain explicit; no refinement, sequence
identity or native success is invented. Tests use simulated copy evidence;
native refinement and fixed-route/resume qualification remain outstanding.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field
from tests.fixtures.ranking_four_arm_advancement import _source_sha256
from tests.fixtures.ranking_four_arm_continuation import (
    ReferenceContinuationInputs,
    ReferencePreparedCopyReceipt,
    ReferencePreparedCopyRequest,
    _context,
    _input_digests,
    _request,
    _tasks,
    validate_prepared_reference_copy_task,
)
from tests.fixtures.ranking_four_arm_plan import _inventory
from tests.fixtures.ranking_four_arm_reference import AdmissionPrior
from tests.fixtures.ranking_four_arm_stages import (
    ReferenceCopyEvidence,
    ReferencePairedStages,
    build_reference_stage_inventory,
)

from genome_to_diffraction.benchmarks.m6_advancement import _object, _owned
from genome_to_diffraction.benchmarks.m6_nextflow import M6FinalistTask
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.results import MtzPreflightRecord

_MANIFEST = "reference_finalists.json"


class ReferenceFinalist(ContractModel):
    """One prior-bound retained parent with unchanged production scientific inputs."""

    admission_prior: AdmissionPrior
    bundle_directory: str
    task: M6FinalistTask


class ReferenceFinalists(ContractModel):
    """Exact retained-parent union and per-arm stages, not a completed M6 case."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["rf-retained-finalists-v1"] = "rf-retained-finalists-v1"
    execution_authority_kind: Literal["truth_blind_rf_reference"] = (
        "truth_blind_rf_reference"
    )
    human_approval_granted: Literal[False] = False
    refinement_executed: Literal[False] = False
    finalists_id: str
    case_id: str
    source_sha256: dict[str, Sha256Hex]
    input_sha256: dict[str, Sha256Hex]
    output_sha256: dict[str, Sha256Hex]
    empty_admission_priors: tuple[AdmissionPrior, ...] = Field(max_length=2)
    stages: tuple[ReferencePairedStages, ...] = Field(max_length=2)
    tasks: tuple[ReferenceFinalist, ...] = Field(max_length=20)


@dataclass(frozen=True)
class _DerivedFinalists:
    case_id: str
    tasks: tuple[ReferenceFinalist, ...]
    stages: tuple[ReferencePairedStages, ...]
    empty_admission_priors: tuple[AdmissionPrior, ...]
    inputs: dict[str, str]
    files: dict[str, Path]
    documents: dict[str, dict[str, object]]


def _derive(
    inputs: ReferenceContinuationInputs, copy_receipts: tuple[Path, ...]
) -> _DerivedFinalists:
    materialisation, admission, reviews = _context(inputs)
    expected_tasks = _tasks(inputs, materialisation, admission, reviews)
    expected = {
        (task.admission_prior, task.seed_solution_id) for task in expected_tasks
    }
    parsed = tuple(
        ReferencePreparedCopyReceipt.model_validate_json(path.read_bytes())
        for path in copy_receipts
    )
    keys = tuple(
        (receipt.task.admission_prior, receipt.task.seed_solution_id)
        for receipt in parsed
    )
    if (
        len(keys) != len(expected)
        or set(keys) != expected
        or len({path.resolve(strict=True) for path in copy_receipts}) != len(expected)
    ):
        raise ValueError(
            "reference finalists require the exact unique copy receipt union"
        )
    preflight = MtzPreflightRecord.model_validate_json(
        admission.mtz_preflight_jsonl.read_text()
    )
    if preflight.selected_observation_labels is None:
        raise ValueError("reference finalists require original selected observations")
    evidence: dict[AdmissionPrior, list[ReferenceCopyEvidence]] = {
        row.admission_prior: [] for row in reviews.cohorts
    }
    digests = _input_digests(inputs)
    files: dict[str, Path] = {}
    documents: dict[str, dict[str, object]] = {}
    tasks: list[ReferenceFinalist] = []
    for path, receipt in sorted(
        zip(copy_receipts, parsed, strict=True),
        key=lambda item: (
            item[1].task.admission_prior,
            item[1].task.seed_solution_id,
        ),
    ):
        prior, seed_id = receipt.task.admission_prior, receipt.task.seed_solution_id
        request = ReferencePreparedCopyRequest(
            inputs=inputs,
            admission_prior=prior,
            seed_solution_id=seed_id,
            threads=receipt.threads,
            output_directory=path.parent,
        )
        validate_prepared_reference_copy_task(path, request)
        _, native, _, _ = _request(request)
        evidence[prior].append(ReferenceCopyEvidence(native, path.parent))
        digests[f"copy_receipt/{prior}/{seed_id}"] = sha256_file(path)
        parent = _object(path.parent / "best_parent.json")
        copy_count = parent.get("best_supported_copy_count")
        if type(copy_count) is not int or copy_count < 1:
            raise ValueError(
                "reference finalist requires an actual positive copy count"
            )
        task = M6FinalistTask(
            schema_version="1.0",
            case_id=preflight.crystal_id,
            seed_solution_id=seed_id,
            sequence_group_id=receipt.task.sequence_group_id,
            input_copy_count=copy_count,
            parent_coordinate_sha256=sha256_file(path.parent / "best_parent.pdb"),
            parent_mtz_sha256=sha256_file(
                inputs.prepared_inputs.prepared_case / "reflections.mtz"
            ),
            observation_labels=preflight.selected_observation_labels,
            resolution=preflight.resolution_high_a,
        )
        tasks.append(
            ReferenceFinalist(admission_prior=prior, bundle_directory=prior, task=task)
        )
        prefix = f"{prior}/finalist_tasks/{seed_id}"
        documents[f"{prefix}/task.json"] = task.model_dump(mode="json")
        files[f"{prefix}/parent_coordinate.pdb"] = path.parent / "best_parent.pdb"
        files[f"{prefix}/parent.mtz"] = (
            inputs.prepared_inputs.prepared_case / "reflections.mtz"
        )
        for relative in _inventory(path.parent, None):
            files[f"{prior}/copy_receipts/{seed_id}/{relative}"] = _owned(
                path.parent, relative
            )
    stages: list[ReferencePairedStages] = []
    empty: list[AdmissionPrior] = []
    for cohort in reviews.cohorts:
        prior = cohort.admission_prior
        for name in ("all_sequence_groups.jsonl", "all_source_records.jsonl"):
            files[f"{prior}/case_bundle/{name}"] = (
                inputs.prepared_inputs.prepared_case / name
            )
        if cohort.advancement_manifest is None:
            if evidence[prior] or cohort.status != "no_scheduled_hypotheses":
                raise ValueError("reference empty cohort has unauthorised continuation")
            empty.append(prior)
            continue
        stages.append(
            build_reference_stage_inventory(
                admission,
                hypotheses_jsonl=materialisation.parent / prior / "mr_hypotheses.jsonl",
                advancement_manifest=_owned(
                    inputs.reviews_path.parent, cohort.advancement_manifest
                ),
                copy_evidence=tuple(evidence[prior]),
            )
        )
    return _DerivedFinalists(
        preflight.crystal_id,
        tuple(tasks),
        tuple(stages),
        tuple(empty),
        digests,
        files,
        documents,
    )


def _identity(manifest: ReferenceFinalists) -> str:
    return content_id(
        "rffinalists_", manifest.model_dump(mode="json", exclude={"finalists_id"})
    )


def build_reference_finalists(
    inputs: ReferenceContinuationInputs,
    *,
    copy_receipts: tuple[Path, ...],
    output: Path,
) -> Path:
    """Freeze each authentic best parent and complete catalogue without running T12."""

    if output.exists() or output.is_symlink():
        raise ValueError("reference finalist output must not already exist")
    source = _source_sha256()
    derived = _derive(inputs, copy_receipts)
    output.mkdir(parents=True, exist_ok=False)
    for relative, original in derived.files.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
    for relative, document in derived.documents.items():
        atomic_write_json(output / relative, document)
    manifest = ReferenceFinalists(
        finalists_id="pending",
        case_id=derived.case_id,
        source_sha256=source,
        input_sha256=derived.inputs,
        output_sha256=_inventory(output, _MANIFEST),
        empty_admission_priors=derived.empty_admission_priors,
        stages=derived.stages,
        tasks=derived.tasks,
    )
    manifest = manifest.model_copy(update={"finalists_id": _identity(manifest)})
    path = output / _MANIFEST
    atomic_write_json(path, manifest.model_dump(mode="json"))
    validate_reference_finalists(path, inputs, copy_receipts=copy_receipts)
    return path


def validate_reference_finalists(
    path: Path,
    inputs: ReferenceContinuationInputs,
    *,
    copy_receipts: tuple[Path, ...],
) -> ReferenceFinalists:
    """Reconstruct tasks, stages and copied assets from the original receipts."""

    if path.is_symlink() or path.name != _MANIFEST:
        raise ValueError("reference finalists require their owned canonical manifest")
    manifest = ReferenceFinalists.model_validate_json(path.read_bytes())
    derived = _derive(inputs, copy_receipts)
    actual = _inventory(path.parent, _MANIFEST)
    if (
        manifest.finalists_id != _identity(manifest)
        or manifest.source_sha256 != _source_sha256()
        or manifest.case_id != derived.case_id
        or manifest.input_sha256 != derived.inputs
        or manifest.tasks != derived.tasks
        or manifest.stages != derived.stages
        or manifest.empty_admission_priors != derived.empty_admission_priors
        or manifest.output_sha256 != actual
        or set(actual) != set(derived.files) | set(derived.documents)
        or any(
            actual[relative] != sha256_file(original)
            for relative, original in derived.files.items()
        )
        or any(
            _object(_owned(path.parent, relative)) != document
            for relative, document in derived.documents.items()
        )
    ):
        raise ValueError("reference finalist tasks, stages or frozen inputs changed")
    return manifest
