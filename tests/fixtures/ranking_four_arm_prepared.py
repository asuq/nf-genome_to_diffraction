"""Bind original M6 preparation to one explicitly labelled RF admission bundle.

Inputs are the fixed reference plan, original full catalogue import, prepared
case, original coordinate stage and unchanged runtime manifests. Original task,
track, MTZ, catalogue, preflight, policy and registration joins are checked before
the shared admission loaders are used. Both reference cohorts are materialised
without changing the production preparation or generating M6/human authority.
Preflight termination and an empty coordinate inventory emit no invented funnel
or MR result. A production-empty funnel still receives reference assessment when
the original complete Matthews/model inputs exist.

No external tool runs here. Source, plan, every original bundle file, runtime
and all outputs form the content identity; native staging must anchor the saved
manifest digest independently. Missing, foreign, changed or symlinked assets and
inconsistent typed outcomes fail. Tests use production producers and explicitly
synthetic external responses, not native qualification.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tests.fixtures.ranking_four_arm_admission import reference_admission_plan
from tests.fixtures.ranking_four_arm_advancement import _SOURCE_ROOT, _source_sha256
from tests.fixtures.ranking_four_arm_materialisation import (
    materialise_reference_cohorts,
    validate_reference_materialisation,
)
from tests.fixtures.ranking_four_arm_plan import (
    ReferencePlanInputs,
    _inventory,
    validate_reference_plan,
)

from genome_to_diffraction.benchmarks.m6_advancement import _owned
from genome_to_diffraction.benchmarks.m6_nextflow import (
    _CASE_ADAPTER,
    _CATALOGUE_ADAPTER,
    _COORDINATE_STAGE_ADAPTER,
    _MODEL_POLICY_ADAPTER,
    _PREFLIGHT_ADAPTER,
    M6BundleManifest,
    M6CaseTask,
    M6CatalogueTask,
    _case_plan,
    _early_outcome,
    _jsonl,
)
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.ranking import DiverseFirstCopyFunnelRequest
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.results import MrHypothesis, MtzPreflightRecord

_MANIFEST = "reference_prepared_case.json"
type PreparedStatus = Literal["materialised", "completed_no_model", "preflight_blocked"]


@dataclass(frozen=True)
class ReferencePreparedInputs:
    """Original, externally anchored outputs from unchanged production tasks."""

    plan_path: Path
    plan_inputs: ReferencePlanInputs
    case_id: str
    catalogue_bundle: Path
    prepared_case: Path
    coordinate_stage: Path | None
    phenix_manifest: Path


class ReferencePreparedCase(ContractModel):
    """A prepared reference case, never an M6 completion or review decision."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["rf-original-preparation-v1"] = (
        "rf-original-preparation-v1"
    )
    execution_authority_kind: Literal["truth_blind_rf_reference"] = (
        "truth_blind_rf_reference"
    )
    human_approval_granted: Literal[False] = False
    mr_executed: Literal[False] = False
    prepared_id: str
    plan_id: str
    task: M6CaseTask
    status: PreparedStatus
    production_early_outcome: str | None
    materialisation_path: str | None
    materialisation_sha256: Sha256Hex | None
    source_sha256: dict[str, Sha256Hex]
    input_sha256: dict[str, Sha256Hex]
    original_bundle_sha256: dict[str, dict[str, Sha256Hex]]
    output_sha256: dict[str, Sha256Hex]


def _bundle(
    root: Path,
    *,
    adapter: str,
    kind: str,
    task_id: str,
    inputs: dict[str, Path],
    outputs: dict[str, Path],
) -> M6BundleManifest:
    manifest = M6BundleManifest.model_validate_json(
        _owned(root, "bundle_manifest.json").read_bytes()
    )
    if (
        manifest.adapter_version != adapter
        or manifest.task_kind != kind
        or manifest.task_id != task_id
        or any(
            manifest.input_sha256.get(key) != sha256_file(path)
            for key, path in inputs.items()
        )
        or manifest.output_sha256
        != {key: sha256_file(path) for key, path in outputs.items()}
    ):
        raise ValueError(f"reference original {kind} identity or checksum changed")
    return manifest


def _original_inventory(inputs: ReferencePreparedInputs) -> dict[str, dict[str, str]]:
    roots = {
        "catalogue": inputs.catalogue_bundle,
        "prepared_case": inputs.prepared_case,
    }
    if inputs.coordinate_stage is not None:
        roots["coordinate_stage"] = inputs.coordinate_stage
    return {
        name: _inventory(root.resolve(strict=True), None)
        for name, root in roots.items()
    }


def _input_digests(inputs: ReferencePreparedInputs) -> dict[str, str]:
    return {
        "reference_plan": sha256_file(inputs.plan_path),
        "phenix_manifest": sha256_file(inputs.phenix_manifest),
        **inputs.plan_inputs.checksums(),
    }


def _admission(
    inputs: ReferencePreparedInputs, output: Path
) -> tuple[str, M6CaseTask, PreparedStatus, DiverseFirstCopyFunnelRequest | None]:
    plan = validate_reference_plan(inputs.plan_path, inputs.plan_inputs)
    rows = [row for row in plan.cases if row.task.case_id == inputs.case_id]
    if len(rows) != 1:
        raise ValueError("reference prepared case is outside the fixed plan")
    row = rows[0]
    task = row.task
    plan_root = inputs.plan_path.resolve(strict=True).parent
    task_root = _owned(plan_root, f"{row.task_directory}/task.json").parent
    case = inputs.prepared_case.resolve(strict=True)
    catalogue = inputs.catalogue_bundle.resolve(strict=True)
    catalogue_row = next(
        item
        for item in plan.catalogues
        if item.task.catalogue_key == task.catalogue_key
    )
    catalogue_task_root = _owned(
        plan_root, f"{catalogue_row.task_directory}/task.json"
    ).parent
    if (
        M6CaseTask.model_validate_json(_owned(case, "case_task.json").read_bytes())
        != task
        or M6CatalogueTask.model_validate_json(
            _owned(catalogue, "catalogue_task.json").read_bytes()
        )
        != catalogue_row.task
    ):
        raise ValueError("reference prepared task differs from the original plan")
    for name in ("reflections.mtz", "analysis_config.json", "model_policy.json"):
        if sha256_file(_owned(case, name)) != sha256_file(task_root / name):
            raise ValueError("reference prepared case changed an original task input")
    if task.fault_control_sha256 is not None:
        if sha256_file(_owned(case, "fault_control.json")) != task.fault_control_sha256:
            raise ValueError("reference prepared fault input changed")
    elif (case / "fault_control.json").exists():
        raise ValueError("reference prepared case introduced a fault input")
    _bundle(
        catalogue,
        adapter=_CATALOGUE_ADAPTER,
        kind="catalogue_import",
        task_id=task.catalogue_key,
        inputs={
            "task": catalogue_task_root / "task.json",
            "catalogue": catalogue_task_root / "catalogue.faa",
            "analysis_config": catalogue_task_root / "analysis_config.json",
            "software_lock": inputs.plan_inputs.software_lock,
        },
        outputs={
            "sequence_groups": catalogue / "catalogue/sequence_groups.jsonl",
            "source_records": catalogue / "catalogue/source_records.jsonl",
            "import_manifest": catalogue / "catalogue/catalogue_import_manifest.json",
        },
    )
    for name in ("sequence_groups", "source_records"):
        if sha256_file(case / f"all_{name}.jsonl") != sha256_file(
            catalogue / f"catalogue/{name}.jsonl"
        ):
            raise ValueError("reference prepared case changed its full catalogue")
    preflight = case / "preflight_bundle"
    if sha256_file(_owned(preflight, "case_task.json")) != sha256_file(
        task_root / "task.json"
    ):
        raise ValueError("reference preflight copied task changed")
    preflight_manifest = _bundle(
        preflight,
        adapter=_PREFLIGHT_ADAPTER,
        kind="case_preflight",
        task_id=task.case_id,
        inputs={
            "case_task": task_root / "task.json",
            "reflections": task_root / "reflections.mtz",
            "phenix_manifest": inputs.phenix_manifest,
        },
        outputs={
            "crystal_manifest": preflight / "crystal_manifest.json",
            "preflight": preflight / "preflight/mtz_preflight.jsonl",
        },
    )
    records = _jsonl(preflight / "preflight/mtz_preflight.jsonl", MtzPreflightRecord)
    if (
        len(records) != 1
        or records[0].crystal_id != task.case_id
        or records[0].mtz_sha256 != task.reflections_sha256
        or _early_outcome(records[0]) != preflight_manifest.early_outcome
    ):
        raise ValueError("reference original preflight record or outcome changed")
    production = _case_plan(case)
    if (
        production.case_id != task.case_id
        or production.catalogue_key != task.catalogue_key
    ):
        raise ValueError("reference original preparation plan changed its case")
    bundle_inputs = {
        "case_task": task_root / "task.json",
        "catalogue": catalogue / "bundle_manifest.json",
        "preflight": preflight / "bundle_manifest.json",
    }
    bundle_outputs = {
        "case_plan": case / "case_plan.json",
        "sequence_groups": case / "all_sequence_groups.jsonl",
        "source_records": case / "all_source_records.jsonl",
    }
    admission: DiverseFirstCopyFunnelRequest | None = None
    status: PreparedStatus
    if preflight_manifest.early_outcome is not None:
        if (
            inputs.coordinate_stage is not None
            or production.early_outcome != preflight_manifest.early_outcome
        ):
            raise ValueError("reference early preparation contradicts its preflight")
        status = "preflight_blocked"
    else:
        if inputs.coordinate_stage is None:
            raise ValueError(
                "reference active preparation lacks its original coordinate stage"
            )
        stage = inputs.coordinate_stage.resolve(strict=True)
        policy = case / "policy_bundle"
        if sha256_file(_owned(policy, "case_task.json")) != sha256_file(
            task_root / "task.json"
        ):
            raise ValueError("reference policy copied task changed")
        _bundle(
            policy,
            adapter=_MODEL_POLICY_ADAPTER,
            kind="trusted_model_policy",
            task_id=task.case_id,
            inputs={
                "case_task": task_root / "task.json",
                "catalogue_bundle": catalogue / "bundle_manifest.json",
                "database_manifest": inputs.plan_inputs.database_manifest,
                "protocol": _SOURCE_ROOT / "benchmarks/m6/protocol.yaml",
            },
            outputs={
                "accepted_hits": policy / "policy/accepted_structural_hits.jsonl",
                "rejected_models": policy / "policy/rejected_model_annotations.jsonl",
                "candidate_ranking": policy / "policy/candidate_ranking.jsonl",
                "report": policy / "policy/model_policy_report.json",
            },
        )
        stage_manifest = _bundle(
            stage,
            adapter=_COORDINATE_STAGE_ADAPTER,
            kind="coordinate_stage",
            task_id=task.case_id,
            inputs={
                "case_task": task_root / "task.json",
                "catalogue": catalogue / "bundle_manifest.json",
                "policy": policy / "bundle_manifest.json",
                "database_manifest": inputs.plan_inputs.database_manifest,
                "eligible_sequence_groups": case
                / "eligible-candidates/sequence_groups.jsonl",
                "eligible_source_records": case
                / "eligible-candidates/source_records.jsonl",
                "eligible_structural_hits": case
                / "eligible-candidates/accepted_structural_hits.jsonl",
            },
            outputs={
                "coordinate_sources": stage / "registration/coordinate_sources.jsonl",
                "coordinate_hit_mappings": stage
                / "registration/coordinate_hit_mappings.jsonl",
                "registration": stage / "registration/registration_manifest.json",
            },
        )
        if sha256_file(stage / "bundle_manifest.json") != sha256_file(
            case / "coordinate_stage_manifest.json"
        ):
            raise ValueError("reference original coordinate-stage manifest changed")
        bundle_inputs.update(
            policy=policy / "bundle_manifest.json",
            coordinate_stage=stage / "bundle_manifest.json",
        )
        bundle_outputs["coordinate_stage"] = case / "coordinate_stage_manifest.json"
        if stage_manifest.early_outcome is not None:
            if (
                stage_manifest.early_outcome != "completed_no_model"
                or production.early_outcome != "completed_no_model"
                or (case / "eligible-candidates/accepted_structural_hits.jsonl")
                .read_text()
                .strip()
                or (stage / "registration/coordinate_sources.jsonl").read_text().strip()
                or (stage / "registration/coordinate_hit_mappings.jsonl")
                .read_text()
                .strip()
                or (case / "matthews").exists()
                or (case / "first-copy-funnel").exists()
            ):
                raise ValueError(
                    "reference empty coordinate stage contradicts its preparation"
                )
            status = "completed_no_model"
        else:
            admission = DiverseFirstCopyFunnelRequest(
                coordinate_sources_jsonl=(
                    stage / "registration/coordinate_sources.jsonl",
                ),
                processed_models_jsonl=(
                    case / "model-preparation/processed_models.jsonl",
                ),
                model_preparation_manifests=(
                    case / "model-preparation/model_preparation_manifest.json",
                ),
                sequence_groups_jsonl=case
                / "eligible-candidates/sequence_groups.jsonl",
                matthews_hypotheses_jsonl=case / "matthews/matthews_hypotheses.jsonl",
                mtz_preflight_jsonl=preflight / "preflight/mtz_preflight.jsonl",
                pipeline_config=case / "analysis_config.json",
                coordinate_hit_mappings_jsonl=stage
                / "registration/coordinate_hit_mappings.jsonl",
                crystal_ids=(task.case_id,),
                maximum_first_copy_jobs=25,
                output_directory=output / "cohorts",
                progress=False,
            )
            baseline = reference_admission_plan(
                admission, admission_prior="copy_weighted"
            )
            expected = tuple(item.hypothesis for item in baseline.selected)
            observed = _jsonl(
                case / "first-copy-funnel/mr_hypotheses.jsonl", MrHypothesis
            )
            if (
                observed != expected
                or tuple(item.hypothesis_id for item in observed)
                != production.hypothesis_ids
                or production.early_outcome
                != (None if observed else "completed_no_model")
            ):
                raise ValueError(
                    "reference inputs do not reproduce original production admission"
                )
            if production.hypothesis_count:
                bundle_outputs["funnel_manifest"] = (
                    case / "first-copy-funnel/funnel_manifest.json"
                )
            status = "materialised"
    manifest = _bundle(
        case,
        adapter=_CASE_ADAPTER,
        kind="case_preparation",
        task_id=task.case_id,
        inputs=bundle_inputs,
        outputs=bundle_outputs,
    )
    if (
        manifest.early_outcome != production.early_outcome
        or manifest.hypothesis_count != production.hypothesis_count
    ):
        raise ValueError("reference original preparation outcome changed")
    return plan.plan_id, task, status, admission


def _identity(manifest: ReferencePreparedCase) -> str:
    return content_id(
        "rfprepared_", manifest.model_dump(mode="json", exclude={"prepared_id"})
    )


def bind_reference_prepared_case(inputs: ReferencePreparedInputs, output: Path) -> Path:
    """Validate original preparation, then materialise only its reference inputs."""

    if output.exists() or output.is_symlink():
        raise ValueError("reference prepared output must not already exist")
    before = _original_inventory(inputs)
    digests = _input_digests(inputs)
    source = _source_sha256()
    plan_id, task, status, admission = _admission(inputs, output)
    output.mkdir(parents=True)
    materialisation = (
        None
        if admission is None
        else materialise_reference_cohorts(admission, output / "cohorts")
    )
    manifest = ReferencePreparedCase(
        prepared_id="pending",
        plan_id=plan_id,
        task=task,
        status=status,
        production_early_outcome=_case_plan(inputs.prepared_case).early_outcome,
        materialisation_path=None
        if materialisation is None
        else "cohorts/reference_cohorts.json",
        materialisation_sha256=None
        if materialisation is None
        else sha256_file(materialisation),
        source_sha256=source,
        input_sha256=digests,
        original_bundle_sha256=before,
        output_sha256=_inventory(output, _MANIFEST),
    )
    if (
        before != _original_inventory(inputs)
        or digests != _input_digests(inputs)
        or source != _source_sha256()
    ):
        raise ValueError(
            "reference original preparation changed during materialisation"
        )
    manifest = manifest.model_copy(update={"prepared_id": _identity(manifest)})
    path = output / _MANIFEST
    atomic_write_json(path, manifest.model_dump(mode="json"))
    validate_reference_prepared_case(path, inputs)
    return path


def validate_reference_prepared_case(
    path: Path, inputs: ReferencePreparedInputs
) -> tuple[ReferencePreparedCase, DiverseFirstCopyFunnelRequest | None]:
    """Revalidate the binding and return the authentic optional admission request."""

    if path.name != _MANIFEST or path.is_symlink():
        raise ValueError("reference prepared case requires its canonical manifest")
    root = path.resolve(strict=True).parent
    manifest = ReferencePreparedCase.model_validate_json(path.read_bytes())
    if (
        manifest.prepared_id != _identity(manifest)
        or manifest.source_sha256 != _source_sha256()
        or manifest.input_sha256 != _input_digests(inputs)
        or manifest.original_bundle_sha256 != _original_inventory(inputs)
        or manifest.output_sha256 != _inventory(root, _MANIFEST)
    ):
        raise ValueError(
            "reference prepared identity, original inputs or outputs changed"
        )
    plan_id, task, status, admission = _admission(inputs, root)
    if (
        manifest.plan_id != plan_id
        or manifest.task != task
        or manifest.status != status
        or manifest.production_early_outcome
        != _case_plan(inputs.prepared_case).early_outcome
    ):
        raise ValueError("reference prepared binding differs from original preparation")
    if admission is None:
        if (
            manifest.materialisation_path is not None
            or manifest.materialisation_sha256 is not None
            or manifest.output_sha256
        ):
            raise ValueError(
                "reference early case contains invented admission evidence"
            )
    else:
        if manifest.materialisation_path != "cohorts/reference_cohorts.json":
            raise ValueError("reference materialisation has a non-canonical path")
        materialisation = _owned(root, manifest.materialisation_path)
        if sha256_file(materialisation) != manifest.materialisation_sha256:
            raise ValueError("reference prepared materialisation checksum changed")
        validate_reference_materialisation(materialisation, admission)
    return manifest, admission
