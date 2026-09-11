"""Materialise paired RF admission cohorts before any first-copy MR executes.

Inputs are one fixed known case's original production-validated funnel request.
The complete prepared model registry is published by the shared production
writer, then copied unchanged to both reference-labelled cohorts. Every physical
alternative and cap disposition is retained. Raw Matthews/hypothesis factors
are never rewritten. A deterministic channel table emits the exact hypothesis
union, at most 50 tasks per case and still at most 25 per arm; only identical
full hypotheses sharing the same authenticated inputs may reuse a first-copy
result. No external command or review authority is generated. Empty admission
is recorded separately and cannot be interpreted as MR success. Missing, stale,
foreign or changed assets fail. Source/input/output digests bind the cache
identity. Tests compare the real production registry and selection using
synthetic prepared inputs, not native acceptance evidence.
"""

import csv
import io
import shutil
from pathlib import Path
from typing import Literal

from pydantic import Field
from tests.fixtures.ranking_four_arm_admission import (
    ReferenceAdmissionPlan,
    reference_admission_plan,
)
from tests.fixtures.ranking_four_arm_advancement import (
    REFERENCE_CASE_IDS,
    _source_sha256,
)
from tests.fixtures.ranking_four_arm_plan import _inventory
from tests.fixtures.ranking_four_arm_reference import AdmissionPrior

from genome_to_diffraction.benchmarks.m6_advancement import _object, _owned, _records
from genome_to_diffraction.checksums import atomic_write_json, atomic_write_text
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.model_registry import load_all_eligible_model_registry
from genome_to_diffraction.ranking.funnel import (
    DiverseFirstCopyFunnelRequest,
    _diverse_model_paths,
    _load_diverse_inputs,
    _publish_all_eligible_models,
)
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.results import MrHypothesis, ProcessedModelRecord

_MANIFEST = "reference_cohorts.json"
_PRIORS: tuple[AdmissionPrior, AdmissionPrior] = ("copy_weighted", "solvent_density")


class ReferenceAdmissionCohort(ContractModel):
    """An ordered capped cohort, not a recommendation or executed result."""

    admission_prior: AdmissionPrior
    admission_status: Literal["completed_hypotheses", "completed_no_model"]
    hypotheses: tuple[MrHypothesis, ...] = Field(max_length=25)
    physical_hypothesis_count: int = Field(ge=0)
    deferred_copy_count: int = Field(ge=0)
    deferred_task_count: int = Field(ge=0)
    registry_id: str


class ReferenceFirstCopyTask(ContractModel):
    """One exact shared hypothesis and an owned canonical cohort asset path."""

    hypothesis: MrHypothesis
    admission_prior: AdmissionPrior
    hypothesis_path: str
    model_registry_path: str


class ReferenceMaterialisation(ContractModel):
    """Source-bound paired inputs and exact union, with no MR success claim."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["rf-paired-materialisation-v1"] = (
        "rf-paired-materialisation-v1"
    )
    execution_authority_kind: Literal["truth_blind_rf_reference"] = (
        "truth_blind_rf_reference"
    )
    human_approval_granted: Literal[False] = False
    mr_executed: Literal[False] = False
    materialisation_id: str
    crystal_id: str
    source_sha256: dict[str, Sha256Hex]
    input_sha256: dict[str, Sha256Hex]
    output_sha256: dict[str, Sha256Hex]
    cohorts: tuple[ReferenceAdmissionCohort, ReferenceAdmissionCohort]
    tasks: tuple[ReferenceFirstCopyTask, ...] = Field(max_length=50)


def _plans(
    request: DiverseFirstCopyFunnelRequest,
) -> tuple[ReferenceAdmissionPlan, ReferenceAdmissionPlan]:
    if (
        len(request.crystal_ids) != 1
        or request.crystal_ids[0] not in REFERENCE_CASE_IDS
    ):
        raise ValueError("reference materialisation requires a fixed known case")
    first, second = (
        reference_admission_plan(request, admission_prior=prior) for prior in _PRIORS
    )
    if first.input_sha256 != second.input_sha256:
        raise ValueError("reference paired admission inputs changed")
    return first, second


def _physical_inventory(plan: ReferenceAdmissionPlan) -> list[dict[str, object]]:
    selected = {row.hypothesis.hypothesis_id for row in plan.selected}
    return [
        {
            "hypothesis": row.hypothesis.model_dump(mode="json"),
            "original_matthews": row.matthews.original.model_dump(mode="json"),
            "reference_prior": row.matthews.prior,
            "reference_rank": row.matthews.rank,
            "reference_retained": row.matthews.retained,
            "diversity_bucket": list(row.diversity_bucket),
            "disposition": "scheduled"
            if row.hypothesis.hypothesis_id in selected
            else "deferred_copy"
            if not row.within_model_cap
            else "deferred_task",
        }
        for row in plan.inventory
    ]


def _cohort(plan: ReferenceAdmissionPlan, registry_id: str) -> ReferenceAdmissionCohort:
    return ReferenceAdmissionCohort(
        admission_prior=plan.admission_prior,
        admission_status="completed_hypotheses"
        if plan.selected
        else "completed_no_model",
        hypotheses=tuple(row.hypothesis for row in plan.selected),
        physical_hypothesis_count=len(plan.inventory),
        deferred_copy_count=len(plan.deferred_copy),
        deferred_task_count=len(plan.deferred_task),
        registry_id=registry_id,
    )


def _funnel(plan: ReferenceAdmissionPlan, root: Path) -> dict[str, object]:
    registry = load_all_eligible_model_registry(
        root / "model_registry/all_model_registry.json"
    )
    by_model = {
        model.model_id: model
        for group in registry.manifest.sequence_groups
        for model in group.models
    }
    entries: list[dict[str, object]] = []
    for row in plan.selected:
        hypothesis = row.hypothesis
        model = by_model[hypothesis.model_id]
        if model.sequence_group_id != hypothesis.sequence_group_id:
            raise ValueError("reference hypothesis changed its original model group")
        entries.append(
            {
                "hypothesis_id": hypothesis.hypothesis_id,
                "model_id": model.model_id,
                "model_path": f"model_registry/{model.model_path}",
                "model_sha256": model.model_sha256,
                "coordinate_id": model.coordinate_id,
                "coordinate_provider": model.provider,
                "matthews_hypothesis_id": hypothesis.priority_features[
                    "matthews_hypothesis_id"
                ],
            }
        )
    identity = {
        "admission_prior": plan.admission_prior,
        "input_sha256": plan.input_sha256,
        "registry_id": registry.manifest.registry_id,
        "hypotheses": entries,
    }
    return {
        "schema_version": "1.0",
        "adapter_version": "rf-paired-materialisation-v1",
        "execution_authority_kind": "truth_blind_rf_reference",
        "funnel_id": content_id("rffunnel_", identity),
        **identity,
        "selected_hypothesis_count": len(entries),
        "execution_status": "completed_success",
    }


def _tasks(
    cohorts: tuple[ReferenceAdmissionCohort, ReferenceAdmissionCohort],
) -> tuple[ReferenceFirstCopyTask, ...]:
    tasks: dict[str, ReferenceFirstCopyTask] = {}
    for cohort in cohorts:
        prior = cohort.admission_prior
        for hypothesis in cohort.hypotheses:
            old = tasks.get(hypothesis.hypothesis_id)
            if old is not None:
                if old.hypothesis != hypothesis:
                    raise ValueError("reference shared hypothesis identity differs")
                continue
            tasks[hypothesis.hypothesis_id] = ReferenceFirstCopyTask(
                hypothesis=hypothesis,
                admission_prior=prior,
                hypothesis_path=f"{prior}/hypotheses/{hypothesis.hypothesis_id}.jsonl",
                model_registry_path=f"{prior}/model_registry/all_model_registry.json",
            )
    return tuple(tasks[key] for key in sorted(tasks))


def _task_table(tasks: tuple[ReferenceFirstCopyTask, ...]) -> str:
    table = io.StringIO(newline="")
    writer = csv.writer(table, delimiter="\t", lineterminator="\n")
    writer.writerow(
        (
            "crystal_id",
            "hypothesis_id",
            "admission_prior",
            "hypothesis_path",
            "model_registry_path",
        )
    )
    writer.writerows(
        (
            task.hypothesis.crystal_id,
            task.hypothesis.hypothesis_id,
            task.admission_prior,
            task.hypothesis_path,
            task.model_registry_path,
        )
        for task in tasks
    )
    return table.getvalue()


def _identity(manifest: ReferenceMaterialisation) -> str:
    return content_id(
        "rfmaterial_", manifest.model_dump(mode="json", exclude={"materialisation_id"})
    )


def materialise_reference_cohorts(
    request: DiverseFirstCopyFunnelRequest, output: Path
) -> Path:
    """Write both cohorts and the deduplicated first-copy union before execution."""

    if output.exists() or output.is_symlink():
        raise ValueError("reference materialisation output must not already exist")
    source = _source_sha256()
    plans = _plans(request)
    _, coordinates, batches, mappings, groups, _, _ = _load_diverse_inputs(request)
    root = output.resolve()
    registry, _ = _publish_all_eligible_models(
        root / _PRIORS[0],
        models=tuple(row for batch in batches for row in batch),
        coordinates=coordinates,
        mappings=mappings,
        model_paths=_diverse_model_paths(request, batches),
        groups=groups,
    )
    shutil.copytree(registry.registry_directory, root / _PRIORS[1] / "model_registry")
    cohorts: list[ReferenceAdmissionCohort] = []
    for plan in plans:
        directory = root / plan.admission_prior
        hypotheses = tuple(row.hypothesis for row in plan.selected)
        atomic_write_text(
            directory / "mr_hypotheses.jsonl",
            "".join(f"{canonical_json_text(row)}\n" for row in hypotheses),
        )
        (directory / "hypotheses").mkdir()
        for row in hypotheses:
            atomic_write_text(
                directory / "hypotheses" / f"{row.hypothesis_id}.jsonl",
                canonical_json_text(row) + "\n",
            )
        atomic_write_json(directory / "funnel_manifest.json", _funnel(plan, directory))
        atomic_write_json(
            directory / "physical_inventory.json", {"rows": _physical_inventory(plan)}
        )
        cohorts.append(_cohort(plan, registry.registry.registry_id))
    paired = (cohorts[0], cohorts[1])
    tasks = _tasks(paired)
    atomic_write_text(root / "reference_first_copy_tasks.tsv", _task_table(tasks))
    manifest = ReferenceMaterialisation(
        materialisation_id="pending",
        crystal_id=request.crystal_ids[0],
        source_sha256=source,
        input_sha256=plans[0].input_sha256,
        output_sha256=_inventory(root, _MANIFEST),
        cohorts=paired,
        tasks=tasks,
    )
    if source != _source_sha256() or _plans(request) != plans:
        raise ValueError("reference materialisation inputs or source changed")
    manifest = manifest.model_copy(update={"materialisation_id": _identity(manifest)})
    path = root / _MANIFEST
    atomic_write_json(path, manifest.model_dump(mode="json"))
    validate_reference_materialisation(path, request)
    return path


def validate_reference_materialisation(
    path: Path, request: DiverseFirstCopyFunnelRequest
) -> ReferenceMaterialisation:
    """Rederive both cohorts and authenticate every original and emitted asset."""

    root = path.resolve(strict=True).parent
    if path.is_symlink() or path.name != _MANIFEST:
        raise ValueError(
            "reference materialisation requires its owned canonical manifest"
        )
    manifest = ReferenceMaterialisation.model_validate_json(path.read_bytes())
    plans = _plans(request)
    if (
        manifest.materialisation_id != _identity(manifest)
        or manifest.crystal_id != request.crystal_ids[0]
        or manifest.source_sha256 != _source_sha256()
        or manifest.input_sha256 != plans[0].input_sha256
        or manifest.output_sha256 != _inventory(root, _MANIFEST)
    ):
        raise ValueError(
            "reference materialisation identity, source, inputs or outputs changed"
        )
    _, _, batches, _, groups, _, _ = _load_diverse_inputs(request)
    original_models = {row.model_id: row for batch in batches for row in batch}
    original_groups = {row.sequence_group_id: row.sha256 for row in groups}
    registries = []
    for plan, cohort in zip(plans, manifest.cohorts, strict=True):
        directory = root / plan.admission_prior
        registry = load_all_eligible_model_registry(
            directory / "model_registry/all_model_registry.json"
        )
        registries.append(registry.manifest)
        if {
            row.model_id: row
            for row in _records(
                directory / "model_registry/processed_models.jsonl",
                ProcessedModelRecord,
            )
        } != original_models:
            raise ValueError(
                "reference registry changed the complete original model universe"
            )
        if {
            row.sequence_group_id: row.sequence_sha256
            for row in registry.manifest.sequence_groups
        } != original_groups:
            raise ValueError(
                "reference registry changed the original sequence universe"
            )
        if cohort != _cohort(plan, registry.manifest.registry_id):
            raise ValueError("reference cohort differs from exact rederived admission")
        if (
            _records(directory / "mr_hypotheses.jsonl", MrHypothesis)
            != cohort.hypotheses
        ):
            raise ValueError("reference cohort changed its original hypotheses")
        for hypothesis in cohort.hypotheses:
            if _records(
                directory / "hypotheses" / f"{hypothesis.hypothesis_id}.jsonl",
                MrHypothesis,
            ) != (hypothesis,):
                raise ValueError("reference individual hypothesis changed")
        if _object(directory / "funnel_manifest.json") != _funnel(plan, directory):
            raise ValueError(
                "reference funnel metadata differs from its original models"
            )
        if _object(directory / "physical_inventory.json") != {
            "rows": _physical_inventory(plan)
        }:
            raise ValueError("reference physical inventory or cap dispositions changed")
    if registries[0] != registries[1]:
        raise ValueError("reference cohorts do not share the complete model registry")
    if manifest.tasks != _tasks(manifest.cohorts) or _owned(
        root, "reference_first_copy_tasks.tsv"
    ).read_text(encoding="ascii") != _task_table(manifest.tasks):
        raise ValueError(
            "reference first-copy task union differs from its exact cohorts"
        )
    return manifest
