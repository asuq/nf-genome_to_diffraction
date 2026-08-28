"""Single-task scientific boundaries for the Nextflow-owned M6 graph.

Inputs are the opaque runner, frozen database/Phenix manifests, software lock,
execution policy, and one typed catalogue, case, hypothesis group, seed, or
finalist record. Outputs are checksum-bound task bundles and the legacy-
compatible aggregate filenames consumed by truth-side collection. MMseqs2,
Foldseek/ProstT5, and Phenix are invoked only through the existing pinned
adapters; this module contains no scheduler or concurrency primitive.

Scientific no-hit, no-model, ambiguity, and abstention states are normal typed
outputs. Missing inputs, changed checksums, malformed joins, child-count loss,
or partial bundles fail loudly. Shared import/search keys bind content,
database, parameters, Pixi lock, execution policy, and adapter versions; all
policy and case work remains track-specific. Unit tests cover planning,
batch/cache invalidation, empty branches, retention, aggregation compatibility,
and legacy/new collection, while DSL2 stub tests cover the complete graph.
"""

import csv
import gzip
import json
import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from genome_to_diffraction.benchmarks.control_matrix_run import (
    _supported_first_copy_count,
)
from genome_to_diffraction.benchmarks.control_slice_run import _review_seed
from genome_to_diffraction.benchmarks.m6_edge import (
    M6EdgeObservation,
    edge_stimulus,
    observe_case_edge,
    observe_isolated_missing_phenix,
    verify_edge_observations,
    write_missing_model_stimulus,
)
from genome_to_diffraction.benchmarks.m6_execution import load_m6_execution_policy
from genome_to_diffraction.benchmarks.m6_identity import (
    M6IdentityDecision,
    derive_m6_identity_decision,
    verify_m6_identity_decision_evidence,
)
from genome_to_diffraction.benchmarks.m6_model_policy import (
    M6_ACCEPTED_HIT_CAP_PER_QUERY_ROUTE,
    M6_RAW_DISCOVERY_HIT_CAP_PER_QUERY_ROUTE,
    M6ModelPolicyRequest,
    apply_m6_model_policy,
)
from genome_to_diffraction.benchmarks.m6_scientific import (
    M6ScientificTrack,
    m6_track_case_ids,
    verify_m6_scientific_output,
)
from genome_to_diffraction.benchmarks.m6_verification import (
    M6RunnerCaseSpec,
    M6RunnerInventorySpec,
    M6RunnerObjectSpec,
    M6RunnerVerificationRequest,
    verify_m6_runner_bundle,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.catalogue import CatalogueImportRequest, import_catalogues
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.diffraction.preflight import (
    MtzPreflightError,
    PreflightRequest,
    preflight_crystals,
)
from genome_to_diffraction.ids import canonical_digest, canonical_json_text
from genome_to_diffraction.matthews import MatthewsRequest, enumerate_matthews
from genome_to_diffraction.model_registry.experimental import (
    ExperimentalModelPreparationRequest,
    prepare_experimental_models,
)
from genome_to_diffraction.mr.add_copy import (
    AddCopyRunRequest,
    run_additional_copy_series,
)
from genome_to_diffraction.mr.phaser import PhaserRunOutput
from genome_to_diffraction.ranking import (
    DiverseFirstCopyFunnelRequest,
    build_diverse_first_copy_funnel,
)
from genome_to_diffraction.refinement.brief import T12RunRequest, run_t12_candidate
from genome_to_diffraction.schemas.base import (
    ContractModel,
    PositiveInt,
    Sha256Hex,
)
from genome_to_diffraction.schemas.io import (
    ContractLoadError,
    load_json_document,
    parse_json_document,
)
from genome_to_diffraction.schemas.results import (
    AdditionalCopyResult,
    BriefRefinementResult,
    MrHypothesis,
    MtzPreflightRecord,
    NormalisedMrResult,
    SequenceGroupRecord,
    SequenceMapResult,
    SourceProteinRecord,
    StructuralSearchHit,
    StructuralSearchResult,
)
from genome_to_diffraction.structure_search import (
    PdbCoordinateRegistrationRequest,
    PdbSequenceSearchRequest,
    ProstT5FoldseekSearchRequest,
    register_pdb_coordinates,
    search_pdb_sequences,
    search_prostt5_foldseek,
)
from genome_to_diffraction.structure_search.provider_plan import (
    FrozenM6RawProviderAuthorisation,
)

_PLAN_ADAPTER = "m6-nextflow-plan-v1"
_CATALOGUE_ADAPTER = "m6-nextflow-catalogue-v1"
_QUERY_BATCH_ADAPTER = "m6-nextflow-query-batch-v2"
_PDB_ADAPTER = "m6-nextflow-pdb-search-v2"
_FOLDSEEK_ADAPTER = "m6-nextflow-foldseek-search-v2"
_MODEL_POLICY_ADAPTER = "m6-nextflow-model-policy-v2"
_PREFLIGHT_ADAPTER = "m6-nextflow-preflight-v1"
_COORDINATE_STAGE_ADAPTER = "m6-coordinate-stage-v1"
_CASE_ADAPTER = "m6-nextflow-case-v2"
_SEED_ADAPTER = "m6-nextflow-seeds-v2"
_CASE_EVIDENCE_ADAPTER = "m6-nextflow-case-evidence-v2"
_M6_SEED_CAP = 5
_RUN_ADAPTER = "m6-nextflow-run-v2"
_MATERIALISED_SUFFIX = {
    "application/json": ".json",
    "application/x-mtz": ".mtz",
    "text/plain": ".txt",
    "text/x-fasta": ".faa",
}
NonNegativeInt = Annotated[int, Field(ge=0)]


class M6CatalogueTask(ContractModel):
    """One truthless unique catalogue/configuration discovery unit."""

    schema_version: Literal["1.0"]
    catalogue_key: Sha256Hex
    catalogue_sha256: Sha256Hex
    analysis_config_sha256: Sha256Hex
    software_lock_sha256: Sha256Hex
    import_cache_key: Sha256Hex


class M6SearchBatchTask(ContractModel):
    """One deterministic multi-catalogue query batch for one search provider."""

    schema_version: Literal["1.0"]
    batch_id: Sha256Hex
    provider: Literal["pdb_sequence", "prostt5_foldseek"]
    sequence_count: PositiveInt
    residue_count: PositiveInt
    threads: PositiveInt
    database_manifest_sha256: Sha256Hex
    software_lock_sha256: Sha256Hex
    execution_policy_sha256: Sha256Hex
    search_cache_key: Sha256Hex


class M6CaseTask(ContractModel):
    """One opaque M6 case linked to its truthless catalogue task."""

    schema_version: Literal["1.0"]
    case_id: str
    track: M6ScientificTrack
    catalogue_key: Sha256Hex
    reflections_sha256: Sha256Hex
    analysis_config_sha256: Sha256Hex
    model_policy_sha256: Sha256Hex
    fault_control_sha256: Sha256Hex | None = None


class M6BundleManifest(ContractModel):
    """Common identity and checksum record for a single Nextflow task output."""

    schema_version: Literal["1.0"]
    adapter_version: str
    task_kind: str
    task_id: str
    input_sha256: dict[str, Sha256Hex]
    output_sha256: dict[str, Sha256Hex]
    early_outcome: str | None = None
    hypothesis_count: int | None = None


class M6SeedTask(ContractModel):
    """One retained first-copy parent eligible for an independent copy chain."""

    schema_version: Literal["1.0"]
    case_id: str
    seed_solution_id: str
    hypothesis_id: str
    sequence_group_id: str
    model_id: str
    expected_copy_count: int
    first_copy_placed_count: int
    search_model_sha256: Sha256Hex


class M6FinalistTask(ContractModel):
    """One best retained parent eligible for independent T12 assessment."""

    schema_version: Literal["1.0"]
    case_id: str
    seed_solution_id: str
    sequence_group_id: str
    input_copy_count: int
    parent_coordinate_sha256: Sha256Hex
    parent_mtz_sha256: Sha256Hex
    observation_labels: str
    resolution: float


class M6HypothesisGroupTask(ContractModel):
    """One case-local dynamically sized hypothesis group for Nextflow."""

    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-nextflow-case-v2"]
    case_id: str
    catalogue_key: Sha256Hex
    early_outcome: str | None = None
    hypothesis_count: NonNegativeInt
    hypothesis_ids: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_hypothesis_group(self) -> Self:
        if self.hypothesis_count != len(self.hypothesis_ids):
            raise ValueError("M6 hypothesis-group count changed")
        if self.hypothesis_count and self.early_outcome is not None:
            raise ValueError("runnable M6 hypothesis group has an early outcome")
        if not self.hypothesis_count and self.early_outcome is None:
            raise ValueError("empty M6 hypothesis group lacks a typed outcome")
        return self


class M6CaseEvidence(ContractModel):
    """One complete retain-all case record assembled from child tasks."""

    schema_version: Literal["2.0"]
    adapter_version: Literal["m6-nextflow-case-evidence-v2"]
    case_id: str
    execution_status: Literal["completed", "failed"]
    scientific_status: str
    typed_outcome: str
    failure_class: str | None = None
    candidate_count: NonNegativeInt
    retained_candidate_count: NonNegativeInt
    all_candidates_retained: Literal[True]
    candidate_ranking_path: str | None = None
    model_policy_report_path: str | None = None
    first_copy_attempt_count: NonNegativeInt
    additional_copy_attempt_count: NonNegativeInt
    refinement_attempt_count: NonNegativeInt
    sequence_assessment_count: NonNegativeInt
    identity_decision: M6IdentityDecision
    edge_observations: tuple[M6EdgeObservation, ...]
    first_copy_results: tuple[dict[str, object], ...]
    selected_seed_results: tuple[dict[str, object], ...]
    additional_copy_results: tuple[dict[str, object], ...]
    refinement_results: tuple[dict[str, object], ...]
    sequence_summaries: tuple[dict[str, object], ...]

    @model_validator(mode="after")
    def _validate_retention_and_counts(self) -> Self:
        if self.identity_decision.case_id != self.case_id:
            raise ValueError("M6 identity decision belongs to another case")
        verify_m6_identity_decision_evidence(
            self.identity_decision,
            self.selected_seed_results,
        )
        if verify_edge_observations(self.case_id, self.edge_observations) != (
            self.edge_observations
        ):
            raise ValueError("M6 edge observations are not canonical")
        if self.retained_candidate_count != self.candidate_count:
            raise ValueError("M6 case evidence lost a candidate")
        expected = (
            (self.first_copy_attempt_count, len(self.first_copy_results)),
            (
                self.additional_copy_attempt_count,
                len(self.additional_copy_results),
            ),
            (self.refinement_attempt_count, len(self.refinement_results)),
            (self.sequence_assessment_count, len(self.sequence_summaries)),
        )
        if any(declared != observed for declared, observed in expected):
            raise ValueError("M6 case evidence child count changed")
        return self


@dataclass(frozen=True, slots=True)
class M6TrackPlanRequest:
    """Inputs for one truthless operational or leakage task plan."""

    runner_root: Path
    database_manifest: Path
    software_lock: Path
    track: M6ScientificTrack
    output_directory: Path


@dataclass(frozen=True, slots=True)
class M6TrackPlanOutput:
    """Materialised task directories and deterministic channel manifests."""

    plan_directory: Path
    catalogue_tasks_tsv: Path
    case_tasks_tsv: Path
    plan_manifest: Path
    catalogue_task_count: int
    case_task_count: int


def _json_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = load_json_document(path)
    except ContractLoadError as error:
        raise PublicControlError(f"invalid M6 {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise PublicControlError(f"M6 {label} is not an object: {path}")
    return cast(dict[str, object], value)


def _jsonl_dicts(path: Path, *, required: bool = False) -> list[dict[str, object]]:
    if not path.is_file():
        if required:
            raise PublicControlError(f"required M6 JSONL is missing: {path}")
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise PublicControlError(f"cannot read M6 JSONL: {path}") from error
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        try:
            value = parse_json_document(line, label=f"{path}:{line_number}")
        except ContractLoadError as error:
            raise PublicControlError(
                f"invalid M6 JSONL line {line_number}: {error}"
            ) from error
        if not isinstance(value, dict):
            raise PublicControlError(
                f"M6 JSONL row is not an object at {path}:{line_number}"
            )
        rows.append(cast(dict[str, object], value))
    return rows


def _json_integer(
    document: Mapping[str, object],
    key: str,
    label: str,
    *,
    minimum: int = 0,
) -> int:
    value = document.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise PublicControlError(f"M6 {label} {key} is not an integer")
    if value < minimum:
        raise PublicControlError(
            f"M6 {label} {key} is below the minimum {minimum}: {value}"
        )
    return value


def _load_inventory(root: Path) -> M6RunnerInventorySpec:
    try:
        return M6RunnerInventorySpec.model_validate_json(
            (root / "runner_manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        raise PublicControlError(f"invalid M6 runner inventory: {error}") from error


def _copy_verified(source: Path, destination: Path, expected: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if sha256_file(destination) != expected:
        raise PublicControlError(f"M6 materialised object changed: {source.name}")


def _object_by_role(
    root: Path, case: M6RunnerCaseSpec
) -> dict[str, tuple[Path, M6RunnerObjectSpec]]:
    records: dict[str, tuple[Path, M6RunnerObjectSpec]] = {}
    for spec in case.objects:
        records[spec.role] = (root / "objects" / spec.object, spec)
    return records


def plan_m6_nextflow_track(request: M6TrackPlanRequest) -> M6TrackPlanOutput:
    """Verify and materialise one complete track into independent task bundles."""

    runner = request.runner_root.resolve(strict=True)
    database = request.database_manifest.resolve(strict=True)
    software_lock = request.software_lock.resolve(strict=True)
    software_lock_sha256 = sha256_file(software_lock)
    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise PublicControlError(f"M6 Nextflow plan output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    verify_m6_runner_bundle(
        M6RunnerVerificationRequest(
            runner_root=runner,
            output=output / "runner_input_qualification.json",
        )
    )
    inventory = _load_inventory(runner)
    cases_by_id = {case.case_id: case for case in inventory.cases}
    catalogue_tasks: dict[str, M6CatalogueTask] = {}
    case_tasks: list[M6CaseTask] = []
    for case in inventory.cases:
        roles = _object_by_role(runner, case)
        catalogue_spec = roles["catalogue"][1]
        config_spec = roles["analysis_config"][1]
        catalogue_key = canonical_digest(
            {
                "adapter_version": _PLAN_ADAPTER,
                "catalogue_sha256": catalogue_spec.sha256,
                "analysis_config_sha256": config_spec.sha256,
            }
        )
        if catalogue_key not in catalogue_tasks:
            import_key = canonical_digest(
                {
                    "adapter_version": _CATALOGUE_ADAPTER,
                    "catalogue_key": catalogue_key,
                    "software_lock_sha256": software_lock_sha256,
                }
            )
            task = M6CatalogueTask(
                schema_version="1.0",
                catalogue_key=catalogue_key,
                catalogue_sha256=catalogue_spec.sha256,
                analysis_config_sha256=config_spec.sha256,
                software_lock_sha256=software_lock_sha256,
                import_cache_key=import_key,
            )
            task_root = output / "catalogue_tasks" / catalogue_key
            task_root.mkdir(parents=True)
            _copy_verified(
                roles["catalogue"][0],
                task_root / "catalogue.faa",
                task.catalogue_sha256,
            )
            _copy_verified(
                roles["analysis_config"][0],
                task_root / "analysis_config.json",
                task.analysis_config_sha256,
            )
            atomic_write_json(task_root / "task.json", task.model_dump(mode="json"))
            catalogue_tasks[catalogue_key] = task

    for case_id in m6_track_case_ids(request.track):
        case = cases_by_id[case_id]
        roles = _object_by_role(runner, case)
        catalogue_spec = roles["catalogue"][1]
        config_spec = roles["analysis_config"][1]
        catalogue_key = canonical_digest(
            {
                "adapter_version": _PLAN_ADAPTER,
                "catalogue_sha256": catalogue_spec.sha256,
                "analysis_config_sha256": config_spec.sha256,
            }
        )

        model_spec = roles["model_policy"][1]
        reflection_spec = roles["reflections"][1]
        fault = roles.get("fault_control")
        fault_sha = None if fault is None else fault[1].sha256
        case_task = M6CaseTask(
            schema_version="1.0",
            case_id=case_id,
            track=request.track,
            catalogue_key=catalogue_key,
            reflections_sha256=reflection_spec.sha256,
            analysis_config_sha256=config_spec.sha256,
            model_policy_sha256=model_spec.sha256,
            fault_control_sha256=fault_sha,
        )
        case_root = output / "case_tasks" / case_id
        case_root.mkdir(parents=True)
        _copy_verified(
            roles["reflections"][0],
            case_root / "reflections.mtz",
            reflection_spec.sha256,
        )
        _copy_verified(
            roles["analysis_config"][0],
            case_root / "analysis_config.json",
            config_spec.sha256,
        )
        _copy_verified(
            roles["model_policy"][0], case_root / "model_policy.json", model_spec.sha256
        )
        if fault is not None and fault_sha is not None:
            _copy_verified(fault[0], case_root / "fault_control.json", fault_sha)
        atomic_write_json(case_root / "task.json", case_task.model_dump(mode="json"))
        case_tasks.append(case_task)

    catalogue_tsv = output / "catalogue_tasks.tsv"
    with catalogue_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "catalogue_key",
                "import_cache_key",
                "task_directory",
            )
        )
        for key, task in sorted(catalogue_tasks.items()):
            writer.writerow(
                (
                    key,
                    task.import_cache_key,
                    f"catalogue_tasks/{key}",
                )
            )
    case_tsv = output / "case_tasks.tsv"
    with case_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("case_id", "catalogue_key", "task_directory"))
        for task in case_tasks:
            writer.writerow(
                (task.case_id, task.catalogue_key, f"case_tasks/{task.case_id}")
            )
    plan_manifest = output / "track_plan.json"
    atomic_write_json(
        plan_manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _PLAN_ADAPTER,
            "track": request.track,
            "case_ids": list(m6_track_case_ids(request.track)),
            "case_task_count": len(case_tasks),
            "catalogue_task_count": len(catalogue_tasks),
            "input_sha256": {
                "runner_manifest": sha256_file(runner / "runner_manifest.json"),
                "database_manifest": sha256_file(database),
                "software_lock": software_lock_sha256,
            },
            "outputs": {
                "catalogue_tasks": sha256_file(catalogue_tsv),
                "case_tasks": sha256_file(case_tsv),
            },
        },
    )
    return M6TrackPlanOutput(
        plan_directory=output,
        catalogue_tasks_tsv=catalogue_tsv,
        case_tasks_tsv=case_tsv,
        plan_manifest=plan_manifest,
        catalogue_task_count=len(catalogue_tasks),
        case_task_count=len(case_tasks),
    )


def _load_catalogue_task(task_directory: Path) -> tuple[Path, M6CatalogueTask]:
    root = task_directory.resolve(strict=True)
    task = M6CatalogueTask.model_validate_json(
        (root / "task.json").read_text(encoding="utf-8")
    )
    if (
        sha256_file(root / "catalogue.faa") != task.catalogue_sha256
        or sha256_file(root / "analysis_config.json") != task.analysis_config_sha256
    ):
        raise PublicControlError("M6 catalogue task checksum changed")
    return root, task


def _load_case_task(task_directory: Path) -> tuple[Path, M6CaseTask]:
    root = task_directory.resolve(strict=True)
    task = M6CaseTask.model_validate_json(
        (root / "task.json").read_text(encoding="utf-8")
    )
    checks = {
        "reflections.mtz": task.reflections_sha256,
        "analysis_config.json": task.analysis_config_sha256,
        "model_policy.json": task.model_policy_sha256,
    }
    if task.fault_control_sha256 is not None:
        checks["fault_control.json"] = task.fault_control_sha256
    if any(sha256_file(root / name) != digest for name, digest in checks.items()):
        raise PublicControlError(f"M6 case task checksum changed: {task.case_id}")
    return root, task


def _write_bundle_manifest(
    output: Path,
    *,
    adapter: str,
    kind: str,
    task_id: str,
    inputs: dict[str, Path],
    outputs: dict[str, Path],
    early_outcome: str | None = None,
    hypothesis_count: int | None = None,
) -> Path:
    manifest = M6BundleManifest(
        schema_version="1.0",
        adapter_version=adapter,
        task_kind=kind,
        task_id=task_id,
        input_sha256={name: sha256_file(path) for name, path in inputs.items()},
        output_sha256={name: sha256_file(path) for name, path in outputs.items()},
        early_outcome=early_outcome,
        hypothesis_count=hypothesis_count,
    )
    path = output / "bundle_manifest.json"
    atomic_write_json(path, manifest.model_dump(mode="json"))
    return path


def run_m6_catalogue_task(
    task_directory: Path,
    software_lock: Path,
    output_directory: Path,
) -> Path:
    """Import exactly one unique truthless catalogue task."""

    task_root, task = _load_catalogue_task(task_directory)
    lock_path = software_lock.resolve(strict=True)
    if sha256_file(lock_path) != task.software_lock_sha256:
        raise PublicControlError("M6 catalogue task software lock changed")
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    catalogue_manifest = output / "catalogue_manifest.json"
    _write_catalogue_manifest(catalogue_manifest, task_root / "catalogue.faa")
    imported = output / "catalogue"
    import_catalogues(
        CatalogueImportRequest(
            catalogue_manifest=catalogue_manifest,
            pipeline_config=task_root / "analysis_config.json",
            output_directory=imported,
            progress=False,
        )
    )
    shutil.copy2(task_root / "task.json", output / "catalogue_task.json")
    _write_bundle_manifest(
        output,
        adapter=_CATALOGUE_ADAPTER,
        kind="catalogue_import",
        task_id=task.catalogue_key,
        inputs={
            "task": task_root / "task.json",
            "catalogue": task_root / "catalogue.faa",
            "analysis_config": task_root / "analysis_config.json",
            "software_lock": lock_path,
        },
        outputs={
            "sequence_groups": imported / "sequence_groups.jsonl",
            "source_records": imported / "source_records.jsonl",
            "import_manifest": imported / "catalogue_import_manifest.json",
        },
    )
    return output


def _load_catalogue_bundle(bundle: Path) -> tuple[Path, M6CatalogueTask]:
    root = bundle.resolve(strict=True)
    manifest = M6BundleManifest.model_validate_json(
        (root / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    task = M6CatalogueTask.model_validate_json(
        (root / "catalogue_task.json").read_text(encoding="utf-8")
    )
    if manifest.task_id != task.catalogue_key:
        raise PublicControlError("M6 catalogue bundle identity changed")
    for name, relative in (
        ("sequence_groups", "catalogue/sequence_groups.jsonl"),
        ("source_records", "catalogue/source_records.jsonl"),
        ("import_manifest", "catalogue/catalogue_import_manifest.json"),
    ):
        if sha256_file(root / relative) != manifest.output_sha256[name]:
            raise PublicControlError(f"M6 catalogue bundle output changed: {name}")
    return root, task


def _batch_groups(
    groups: tuple[SequenceGroupRecord, ...],
    *,
    maximum_sequences: int,
    maximum_residues: int,
) -> tuple[tuple[SequenceGroupRecord, ...], ...]:
    batches: list[tuple[SequenceGroupRecord, ...]] = []
    current: list[SequenceGroupRecord] = []
    residues = 0
    for group in sorted(groups, key=lambda item: item.sequence_group_id):
        if current and (
            len(current) >= maximum_sequences
            or residues + group.length_aa > maximum_residues
        ):
            batches.append(tuple(current))
            current = []
            residues = 0
        current.append(group)
        residues += group.length_aa
    if current:
        batches.append(tuple(current))
    return tuple(batches)


def build_m6_search_batches(
    catalogue_bundles: tuple[Path, ...],
    database_manifest: Path,
    execution_policy: Path,
    software_lock: Path,
    output_directory: Path,
) -> Path:
    """Deduplicate all runner catalogues and emit bounded provider batches."""

    if not catalogue_bundles:
        raise PublicControlError("M6 search batching received no catalogues")
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    database = database_manifest.resolve(strict=True)
    policy_path = execution_policy.resolve(strict=True)
    lock_path = software_lock.resolve(strict=True)
    policy = load_m6_execution_policy(policy_path)
    by_group: dict[str, SequenceGroupRecord] = {}
    memberships: dict[str, tuple[str, ...]] = {}
    bundle_manifests: dict[str, Path] = {}
    for bundle in catalogue_bundles:
        root, task = _load_catalogue_bundle(bundle)
        groups = _jsonl(root / "catalogue/sequence_groups.jsonl", SequenceGroupRecord)
        memberships[task.catalogue_key] = tuple(
            sorted(group.sequence_group_id for group in groups)
        )
        bundle_manifests[task.catalogue_key] = root / "bundle_manifest.json"
        for group in groups:
            current = by_group.get(group.sequence_group_id)
            if current is not None and (
                current.sha256 != group.sha256
                or current.sequence != group.sequence
                or current.length_aa != group.length_aa
                or current.quality_flags != group.quality_flags
            ):
                raise PublicControlError(
                    f"M6 shared sequence group differs across catalogues: "
                    f"{group.sequence_group_id}"
                )
            by_group.setdefault(group.sequence_group_id, group)
    unique_groups = tuple(by_group.values())
    membership_root = output / "catalogue_membership"
    membership_root.mkdir()
    for catalogue_key, group_ids in sorted(memberships.items()):
        atomic_write_json(
            membership_root / f"{catalogue_key}.json",
            {
                "schema_version": "1.0",
                "catalogue_key": catalogue_key,
                "sequence_group_ids": list(group_ids),
            },
        )
    provider_batches = {
        "pdb_sequence": _batch_groups(
            unique_groups,
            maximum_sequences=policy.search_batching.mmseqs2.maximum_unique_sequences,
            maximum_residues=policy.search_batching.mmseqs2.maximum_residues,
        ),
        "prostt5_foldseek": _batch_groups(
            unique_groups,
            maximum_sequences=policy.search_batching.foldseek.maximum_unique_sequences,
            maximum_residues=policy.search_batching.foldseek.maximum_residues,
        ),
    }
    database_sha256 = sha256_file(database)
    execution_policy_sha256 = sha256_file(policy_path)
    software_lock_sha256 = sha256_file(lock_path)
    task_rows: dict[str, list[M6SearchBatchTask]] = {
        "pdb_sequence": [],
        "prostt5_foldseek": [],
    }
    for provider, batches in provider_batches.items():
        for groups in batches:
            batch_id = canonical_digest(
                {
                    "adapter_version": _QUERY_BATCH_ADAPTER,
                    "provider": provider,
                    "sequences": [
                        {
                            "sequence_group_id": group.sequence_group_id,
                            "sha256": group.sha256,
                        }
                        for group in groups
                    ],
                }
            )
            threads = (
                policy.search_batching.mmseqs2.cpus
                if provider == "pdb_sequence"
                else policy.search_batching.foldseek.cpus
            )
            parameters = (
                {
                    "threads": threads,
                    "maximum_hits_per_query": (
                        M6_RAW_DISCOVERY_HIT_CAP_PER_QUERY_ROUTE
                    ),
                    "maximum_evalue": 1.0e-5,
                    "minimum_query_coverage": 0.5,
                    "maximum_query_length": 10_000,
                }
                if provider == "pdb_sequence"
                else {
                    "threads": threads,
                    "maximum_hits_per_query": (
                        M6_RAW_DISCOVERY_HIT_CAP_PER_QUERY_ROUTE
                    ),
                    "maximum_evalue": 1.0e-3,
                    "minimum_query_coverage": 0.5,
                    "maximum_query_length": 10_000,
                    "maximum_queries": 0,
                    "retain_unmapped_targets": True,
                }
            )
            search_key = canonical_digest(
                {
                    "adapter_version": (
                        _PDB_ADAPTER
                        if provider == "pdb_sequence"
                        else _FOLDSEEK_ADAPTER
                    ),
                    "batch_id": batch_id,
                    "database_manifest_sha256": database_sha256,
                    "software_lock_sha256": software_lock_sha256,
                    "execution_policy_sha256": execution_policy_sha256,
                    "parameters": parameters,
                }
            )
            task = M6SearchBatchTask(
                schema_version="1.0",
                batch_id=batch_id,
                provider=cast(Literal["pdb_sequence", "prostt5_foldseek"], provider),
                sequence_count=len(groups),
                residue_count=sum(group.length_aa for group in groups),
                threads=threads,
                database_manifest_sha256=database_sha256,
                software_lock_sha256=software_lock_sha256,
                execution_policy_sha256=execution_policy_sha256,
                search_cache_key=search_key,
            )
            task_root = output / f"{provider}_batches" / batch_id
            task_root.mkdir(parents=True)
            atomic_write_json(task_root / "task.json", task.model_dump(mode="json"))
            atomic_write_text(
                task_root / "sequence_groups.jsonl",
                "".join(f"{canonical_json_text(group)}\n" for group in groups),
            )
            task_rows[provider].append(task)
    for provider, rows in task_rows.items():
        path = output / f"{provider}_batches.tsv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(("batch_id", "search_cache_key", "task_directory"))
            for task in rows:
                writer.writerow(
                    (
                        task.batch_id,
                        task.search_cache_key,
                        f"{provider}_batches/{task.batch_id}",
                    )
                )
    atomic_write_json(
        output / "batch_plan.json",
        {
            "schema_version": "1.0",
            "adapter_version": _QUERY_BATCH_ADAPTER,
            "catalogue_count": len(memberships),
            "catalogue_record_count": sum(len(ids) for ids in memberships.values()),
            "unique_sequence_count": len(unique_groups),
            "unique_residue_count": sum(group.length_aa for group in unique_groups),
            "pdb_batch_count": len(task_rows["pdb_sequence"]),
            "foldseek_batch_count": len(task_rows["prostt5_foldseek"]),
            "pdb_threads": policy.search_batching.mmseqs2.cpus,
            "pdb_maximum_sequences": (
                policy.search_batching.mmseqs2.maximum_unique_sequences
            ),
            "pdb_maximum_residues": policy.search_batching.mmseqs2.maximum_residues,
            "foldseek_threads": policy.search_batching.foldseek.cpus,
            "foldseek_maximum_sequences": (
                policy.search_batching.foldseek.maximum_unique_sequences
            ),
            "foldseek_maximum_residues": (
                policy.search_batching.foldseek.maximum_residues
            ),
            "raw_discovery_hit_cap_per_query_route": (
                M6_RAW_DISCOVERY_HIT_CAP_PER_QUERY_ROUTE
            ),
            "accepted_model_hit_cap_per_query_route": (
                M6_ACCEPTED_HIT_CAP_PER_QUERY_ROUTE
            ),
            "database_manifest_sha256": database_sha256,
            "execution_policy_sha256": execution_policy_sha256,
            "software_lock_sha256": software_lock_sha256,
            "catalogue_bundle_sha256": {
                key: sha256_file(path) for key, path in sorted(bundle_manifests.items())
            },
        },
    )
    return output


def _load_search_batch(task_directory: Path) -> tuple[Path, M6SearchBatchTask]:
    root = task_directory.resolve(strict=True)
    task = M6SearchBatchTask.model_validate_json(
        (root / "task.json").read_text(encoding="utf-8")
    )
    groups = _jsonl(root / "sequence_groups.jsonl", SequenceGroupRecord)
    if (
        len(groups) != task.sequence_count
        or sum(group.length_aa for group in groups) != task.residue_count
    ):
        raise PublicControlError(f"M6 search batch changed: {task.batch_id}")
    return root, task


def run_m6_pdb_search_task(
    batch_task: Path,
    database_manifest: Path,
    execution_policy: Path,
    software_lock: Path,
    output_directory: Path,
    *,
    threads: int,
) -> Path:
    """Run one bounded multi-catalogue PDB-sequence query batch."""

    batch, task = _load_search_batch(batch_task)
    if task.provider != "pdb_sequence":
        raise PublicControlError("M6 PDB search received another batch provider")
    if threads != task.threads:
        raise PublicControlError("M6 PDB search thread allocation changed")
    database = database_manifest.resolve(strict=True)
    policy_path = execution_policy.resolve(strict=True)
    lock_path = software_lock.resolve(strict=True)
    if (
        sha256_file(database) != task.database_manifest_sha256
        or sha256_file(policy_path) != task.execution_policy_sha256
        or sha256_file(lock_path) != task.software_lock_sha256
    ):
        raise PublicControlError("M6 PDB search provenance changed")
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = search_pdb_sequences(
        PdbSequenceSearchRequest(
            sequence_groups_jsonl=batch / "sequence_groups.jsonl",
            database_manifest=database,
            output_directory=output / "search",
            frozen_m6_raw_authorisation=FrozenM6RawProviderAuthorisation(
                batch_task_json=batch / "task.json",
                execution_policy=policy_path,
                software_lock=lock_path,
            ),
            threads=threads,
            maximum_hits_per_query=M6_RAW_DISCOVERY_HIT_CAP_PER_QUERY_ROUTE,
            maximum_evalue=1.0e-5,
            minimum_query_coverage=0.5,
            maximum_query_length=10_000,
            progress=False,
        )
    )
    shutil.copy2(batch / "task.json", output / "batch_task.json")
    _write_bundle_manifest(
        output,
        adapter=_PDB_ADAPTER,
        kind="pdb_sequence_search",
        task_id=task.search_cache_key,
        inputs={
            "batch_task": batch / "task.json",
            "sequence_groups": batch / "sequence_groups.jsonl",
            "database_manifest": database,
            "execution_policy": policy_path,
            "software_lock": lock_path,
        },
        outputs={
            "search_results": result.results_jsonl,
            "structural_hits": result.hits_jsonl,
            "search_manifest": result.search_manifest,
        },
    )
    return output


def run_m6_foldseek_search_task(
    batch_task: Path,
    database_manifest: Path,
    execution_policy: Path,
    software_lock: Path,
    output_directory: Path,
    *,
    threads: int,
) -> Path:
    """Run one bounded multi-catalogue ProstT5/Foldseek query batch."""

    batch, task = _load_search_batch(batch_task)
    if task.provider != "prostt5_foldseek":
        raise PublicControlError("M6 Foldseek search received another batch provider")
    if threads != task.threads:
        raise PublicControlError("M6 Foldseek search thread allocation changed")
    database = database_manifest.resolve(strict=True)
    policy_path = execution_policy.resolve(strict=True)
    lock_path = software_lock.resolve(strict=True)
    if (
        sha256_file(database) != task.database_manifest_sha256
        or sha256_file(policy_path) != task.execution_policy_sha256
        or sha256_file(lock_path) != task.software_lock_sha256
    ):
        raise PublicControlError("M6 Foldseek search provenance changed")
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = search_prostt5_foldseek(
        ProstT5FoldseekSearchRequest(
            sequence_groups_jsonl=batch / "sequence_groups.jsonl",
            database_manifest=database,
            output_directory=output / "search",
            frozen_m6_raw_authorisation=FrozenM6RawProviderAuthorisation(
                batch_task_json=batch / "task.json",
                execution_policy=policy_path,
                software_lock=lock_path,
            ),
            threads=threads,
            maximum_hits_per_query=M6_RAW_DISCOVERY_HIT_CAP_PER_QUERY_ROUTE,
            maximum_evalue=1.0e-3,
            minimum_query_coverage=0.5,
            maximum_query_length=10_000,
            maximum_queries=0,
            retain_unmapped_targets=True,
            gpu=False,
            progress=False,
        )
    )
    shutil.copy2(batch / "task.json", output / "batch_task.json")
    _write_bundle_manifest(
        output,
        adapter=_FOLDSEEK_ADAPTER,
        kind="prostt5_foldseek_search",
        task_id=task.search_cache_key,
        inputs={
            "batch_task": batch / "task.json",
            "sequence_groups": batch / "sequence_groups.jsonl",
            "database_manifest": database,
            "execution_policy": policy_path,
            "software_lock": lock_path,
        },
        outputs={
            "search_results": result.results_jsonl,
            "structural_hits": result.hits_jsonl,
            "search_manifest": result.search_manifest,
        },
    )
    return output


def _iter_typed_jsonl[T](path: Path, model: type[T]) -> Iterator[T]:
    """Parse one typed JSONL stream without materialising the whole file."""

    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    yield model.model_validate_json(line)  # ty: ignore[unresolved-attribute]
                except ValueError as error:
                    raise PublicControlError(
                        f"invalid M6 JSONL line {line_number}: {path}"
                    ) from error
    except (OSError, UnicodeError) as error:
        raise PublicControlError(f"cannot read M6 JSONL: {path}") from error


def _batch_search_records(
    bundles: tuple[Path, ...],
    provider: str,
    selected_group_ids: frozenset[str],
) -> tuple[
    tuple[StructuralSearchResult, ...], tuple[StructuralSearchHit, ...], dict[str, str]
]:
    results: list[StructuralSearchResult] = []
    hits: list[StructuralSearchHit] = []
    manifests: dict[str, str] = {}
    result_ids: set[str] = set()
    hit_ids: set[str] = set()
    loaded: list[tuple[M6SearchBatchTask, Path]] = []
    for directory in bundles:
        root = directory.resolve(strict=True)
        task = M6SearchBatchTask.model_validate_json(
            (root / "batch_task.json").read_text(encoding="utf-8")
        )
        if task.provider != provider:
            raise PublicControlError("M6 batch search provider changed")
        loaded.append((task, root))
    batch_ids = [task.batch_id for task, _ in loaded]
    if len(batch_ids) != len(set(batch_ids)):
        raise PublicControlError(f"M6 {provider} search batch is duplicated")
    for task, root in sorted(loaded, key=lambda item: item[0].batch_id):
        for record in _iter_typed_jsonl(
            root / "search/search_results.jsonl", StructuralSearchResult
        ):
            if record.search_id in result_ids:
                raise PublicControlError(
                    f"M6 {provider} search records are duplicated"
                )
            result_ids.add(record.search_id)
            if record.sequence_group_id in selected_group_ids:
                results.append(record)
        for hit in _iter_typed_jsonl(
            root / "search/structural_hits.jsonl", StructuralSearchHit
        ):
            if hit.hit_id in hit_ids:
                raise PublicControlError(
                    f"M6 {provider} search records are duplicated"
                )
            hit_ids.add(hit.hit_id)
            if hit.sequence_group_id in selected_group_ids:
                hits.append(hit)
        manifests[task.batch_id] = sha256_file(root / "bundle_manifest.json")
    results.sort(
        key=lambda item: (item.sequence_group_id, item.provider, item.search_id)
    )
    hits.sort(
        key=lambda item: (
            item.sequence_group_id,
            item.provider,
            item.provider_rank,
            item.hit_id,
        )
    )
    return tuple(results), tuple(hits), dict(sorted(manifests.items()))


def partition_m6_discovery_task(
    catalogue_bundle: Path,
    batch_plan: Path,
    pdb_results: tuple[Path, ...],
    foldseek_results: tuple[Path, ...],
    output_directory: Path,
) -> Path:
    """Partition global query batches back into one truthless catalogue bundle."""

    catalogue, task = _load_catalogue_bundle(catalogue_bundle)
    plan = batch_plan.resolve(strict=True)
    membership = _json_object(
        plan / "catalogue_membership" / f"{task.catalogue_key}.json",
        "catalogue membership",
    )
    group_ids = frozenset(cast(list[str], membership["sequence_group_ids"]))
    pdb_search, pdb_hits, pdb_manifests = _batch_search_records(
        pdb_results, "pdb_sequence", group_ids
    )
    fold_search, fold_hits, fold_manifests = _batch_search_records(
        foldseek_results, "prostt5_foldseek", group_ids
    )
    if {record.sequence_group_id for record in pdb_search} != group_ids or {
        record.sequence_group_id for record in fold_search
    } != group_ids:
        raise PublicControlError(
            f"M6 batched discovery lost catalogue candidates: {task.catalogue_key}"
        )
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(catalogue / "catalogue_task.json", output / "catalogue_task.json")
    for label, records, hits, manifests in (
        ("pdb_bundle", pdb_search, pdb_hits, pdb_manifests),
        ("foldseek_bundle", fold_search, fold_hits, fold_manifests),
    ):
        root = output / label
        search = root / "search"
        search.mkdir(parents=True)
        atomic_write_text(
            search / "search_results.jsonl",
            "".join(f"{canonical_json_text(record)}\n" for record in records),
        )
        atomic_write_text(
            search / "structural_hits.jsonl",
            "".join(f"{canonical_json_text(hit)}\n" for hit in hits),
        )
        atomic_write_json(
            search / "search_manifest.json",
            {
                "schema_version": "1.0",
                "adapter_version": "m6-nextflow-discovery-partition-v1",
                "catalogue_key": task.catalogue_key,
                "provider": label,
                "query_count": len(records),
                "hit_count": len(hits),
                "source_batch_manifest_sha256": dict(sorted(manifests.items())),
            },
        )
        _write_bundle_manifest(
            root,
            adapter="m6-nextflow-discovery-partition-v1",
            kind=label,
            task_id=task.catalogue_key,
            inputs={
                "catalogue_bundle": catalogue / "bundle_manifest.json",
                "batch_plan": plan / "batch_plan.json",
            },
            outputs={
                "search_results": search / "search_results.jsonl",
                "structural_hits": search / "structural_hits.jsonl",
                "search_manifest": search / "search_manifest.json",
            },
        )
    atomic_write_json(
        output / "discovery_partition.json",
        {
            "schema_version": "1.0",
            "catalogue_key": task.catalogue_key,
            "candidate_count": len(group_ids),
            "all_candidates_retained": True,
        },
    )
    return output


def _fault(case_root: Path, task: M6CaseTask) -> dict[str, object]:
    if task.fault_control_sha256 is None:
        return {}
    return _json_object(
        case_root / "fault_control.json", f"fault control for {task.case_id}"
    )


def _write_catalogue_manifest(path: Path, catalogue: Path) -> None:
    atomic_write_json(
        path,
        {
            "schema_version": "1.0",
            "catalogues": [
                {
                    "catalogue_id": "m6_opaque_catalogue",
                    "proteome_faa": str(catalogue.resolve(strict=True)),
                    "annotation_provider": "M6 opaque RefSeq catalogue",
                    "annotation_version": "checksum-frozen",
                    "assembly_accession": None,
                    "assembly_version": None,
                    "genome_fasta": None,
                    "annotation_gff": None,
                    "annotation_gbff": None,
                    "protein_locus_map": None,
                    "translation_table": None,
                    "source_pipeline": None,
                    "source_pipeline_version": None,
                    "is_contaminant_catalogue": False,
                    "notes": "truth-isolated M6 catalogue",
                }
            ],
        },
    )


def _write_crystal_manifest(
    path: Path,
    *,
    case_id: str,
    reflections: Path,
    policy: dict[str, object],
    allow_remote_sequence_submission: bool,
) -> None:
    raw_masses = policy.get("sds_page_mass_kda", [])
    if not isinstance(raw_masses, list) or any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in raw_masses
    ):
        raise PublicControlError("M6 model policy has invalid SDS-PAGE masses")
    masses = [float(value) for value in raw_masses]
    atomic_write_json(
        path,
        {
            "schema_version": "1.0",
            "crystals": [
                {
                    "crystal_id": case_id,
                    "mtz": str(reflections.resolve(strict=True)),
                    "catalogue_id": "m6_opaque_catalogue",
                    "obs_labels": None,
                    "free_flag_labels": None,
                    "space_group_override": None,
                    "high_resolution_override": None,
                    "low_resolution_override": None,
                    "sds_page_mass_kda": masses,
                    "sds_page_condition": "unknown" if masses else None,
                    "sds_page_band_roles": ["uncertain" for _ in masses],
                    "sds_page_tolerance_fraction": 0.3,
                    "allow_remote_sequence_submission": (
                        allow_remote_sequence_submission
                    ),
                    "notes": "truth-isolated M6 diffraction case",
                }
            ],
        },
    )


def _early_outcome(preflight: MtzPreflightRecord) -> str | None:
    """Classify unusable observations from the preflight record alone."""

    warnings = set(preflight.warning_codes)
    if (
        preflight.selected_observation_labels is None
        and not preflight.observation_candidates
        and "no_observed_data" in warnings
    ):
        return "completed_map_only_mtz"
    if (
        preflight.selected_observation_labels is None
        and len(preflight.observation_candidates) >= 2
        and "ambiguous_observation_arrays" in warnings
    ):
        return "ambiguous_columns_conflicting"
    if "no_observed_data" in warnings or "ambiguous_observation_arrays" in warnings:
        return "unusable_observations"
    return None


def run_m6_preflight_task(
    case_task_directory: Path,
    phenix_manifest: Path,
    output_directory: Path,
) -> Path:
    """Preflight exactly one opaque M6 diffraction case."""

    case_root, task = _load_case_task(case_task_directory)
    phenix = phenix_manifest.resolve(strict=True)
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    policy = _json_object(
        case_root / "model_policy.json", f"model policy for {task.case_id}"
    )
    fault = _fault(case_root, task)
    stimulus = edge_stimulus(fault)
    crystal_manifest = output / "crystal_manifest.json"
    _write_crystal_manifest(
        crystal_manifest,
        case_id=task.case_id,
        reflections=case_root / "reflections.mtz",
        policy=policy,
        allow_remote_sequence_submission=stimulus == "remote_rate_limited",
    )
    try:
        result = preflight_crystals(
            PreflightRequest(
                crystal_manifest=crystal_manifest,
                output_directory=output / "preflight",
                phenix_manifest=phenix,
                skip_xtriage=True,
                progress=False,
                xtriage_timeout_seconds=None,
            )
        )
        records = result.records
        preflight_jsonl = result.jsonl_path
    except MtzPreflightError:
        if stimulus not in {
            "map_only_mtz",
            "ambiguous_columns_conflicting",
        }:
            raise
        preflight_jsonl = output / "preflight/mtz_preflight.jsonl"
        records = _jsonl(preflight_jsonl, MtzPreflightRecord)
    if len(records) != 1:
        raise PublicControlError("M6 case preflight did not return one record")
    shutil.copy2(case_root / "task.json", output / "case_task.json")
    early = _early_outcome(records[0])
    phenix_observation: M6EdgeObservation | None = None
    if stimulus == "missing_phenix":
        phenix_observation = observe_isolated_missing_phenix(
            case_id=task.case_id,
            supplied_manifest=phenix,
            isolated_manifest=output / "isolated_missing_phenix_manifest.json",
        )
        atomic_write_json(
            output / "phenix_edge_observation.json",
            phenix_observation.model_dump(mode="json"),
        )
        early = (
            "missing_phenix"
            if phenix_observation.measurement_status == "measured"
            else "edge_observation_contradicted"
        )
    outputs = {
        "crystal_manifest": crystal_manifest,
        "preflight": preflight_jsonl,
    }
    if phenix_observation is not None:
        outputs["phenix_edge_observation"] = output / "phenix_edge_observation.json"
        outputs["isolated_phenix_manifest"] = (
            output / "isolated_missing_phenix_manifest.json"
        )
    _write_bundle_manifest(
        output,
        adapter=_PREFLIGHT_ADAPTER,
        kind="case_preflight",
        task_id=task.case_id,
        inputs={
            "case_task": case_root / "task.json",
            "reflections": case_root / "reflections.mtz",
            "phenix_manifest": phenix,
        },
        outputs=outputs,
        early_outcome=early,
    )
    return output


def run_m6_model_policy_task(
    case_task_directory: Path,
    catalogue_bundle: Path,
    pdb_search_bundle: Path,
    foldseek_search_bundle: Path,
    protocol: Path,
    database_manifest: Path,
    output_directory: Path,
) -> Path:
    """Apply the isolated trusted model policy to exactly one case."""

    case_root, case_task = _load_case_task(case_task_directory)
    catalogue, catalogue_task = _load_catalogue_bundle(catalogue_bundle)
    if catalogue_task.catalogue_key != case_task.catalogue_key:
        raise PublicControlError("M6 case/catalogue task join changed")
    pdb = pdb_search_bundle.resolve(strict=True)
    foldseek = foldseek_search_bundle.resolve(strict=True)
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = apply_m6_model_policy(
        M6ModelPolicyRequest(
            protocol=protocol.resolve(strict=True),
            case_id=case_task.case_id,
            model_policy=case_root / "model_policy.json",
            database_manifest=database_manifest.resolve(strict=True),
            sequence_groups_jsonl=catalogue / "catalogue/sequence_groups.jsonl",
            source_records_jsonl=catalogue / "catalogue/source_records.jsonl",
            pdb_hits_jsonl=pdb / "search/structural_hits.jsonl",
            prostt5_hits_jsonl=foldseek / "search/structural_hits.jsonl",
            output_directory=output / "policy",
        )
    )
    shutil.copy2(case_root / "task.json", output / "case_task.json")
    _write_bundle_manifest(
        output,
        adapter=_MODEL_POLICY_ADAPTER,
        kind="trusted_model_policy",
        task_id=case_task.case_id,
        inputs={
            "case_task": case_root / "task.json",
            "catalogue_bundle": catalogue / "bundle_manifest.json",
            "pdb_bundle": pdb / "bundle_manifest.json",
            "foldseek_bundle": foldseek / "bundle_manifest.json",
            "protocol": protocol.resolve(strict=True),
            "database_manifest": database_manifest.resolve(strict=True),
        },
        outputs={
            "accepted_hits": result.accepted_hits_jsonl,
            "rejected_models": result.rejected_models_jsonl,
            "candidate_ranking": result.candidate_ranking_jsonl,
            "report": result.report_json,
        },
    )
    return output


def _jsonl[T](path: Path, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(line)  # ty: ignore[unresolved-attribute]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    )


def _write_selected_inputs(
    catalogue: Path,
    policy: Path,
    output: Path,
) -> tuple[Path, Path, Path]:
    ranking = _jsonl_dicts(policy / "policy/candidate_ranking.jsonl", required=True)
    selected_ids = {cast(str, row["sequence_group_id"]) for row in ranking[:25]}
    groups = _jsonl(catalogue / "catalogue/sequence_groups.jsonl", SequenceGroupRecord)
    sources = _jsonl(catalogue / "catalogue/source_records.jsonl", SourceProteinRecord)
    hits = _jsonl(policy / "policy/accepted_structural_hits.jsonl", StructuralSearchHit)
    selected = output / "selected-candidates"
    selected.mkdir()
    groups_path = selected / "sequence_groups.jsonl"
    sources_path = selected / "source_records.jsonl"
    hits_path = selected / "accepted_structural_hits.jsonl"
    atomic_write_text(
        groups_path,
        "".join(
            f"{canonical_json_text(item)}\n"
            for item in groups
            if item.sequence_group_id in selected_ids
        ),
    )
    atomic_write_text(
        sources_path,
        "".join(
            f"{canonical_json_text(item)}\n"
            for item in sources
            if item.sequence_group_id in selected_ids
        ),
    )
    atomic_write_text(
        hits_path,
        "".join(
            f"{canonical_json_text(item)}\n"
            for item in hits
            if item.sequence_group_id in selected_ids
        ),
    )
    return groups_path, sources_path, hits_path


def _coordinate_stage_outcome(stimulus: str | None, hits: Path) -> str | None:
    if stimulus == "missing_pdb_model" or not hits.read_text(encoding="utf-8").strip():
        return "completed_no_model"
    return None


def run_m6_coordinate_stage_task(
    case_task_directory: Path,
    catalogue_bundle: Path,
    policy_bundle: Path,
    database_manifest: Path,
    output_directory: Path,
) -> Path:
    """Resolve one bounded hit set before offline M6 case preparation."""

    case_root, task = _load_case_task(case_task_directory)
    catalogue, catalogue_task = _load_catalogue_bundle(catalogue_bundle)
    if catalogue_task.catalogue_key != task.catalogue_key:
        raise PublicControlError("M6 coordinate stage catalogue join changed")
    policy = policy_bundle.resolve(strict=True)
    policy_manifest = M6BundleManifest.model_validate_json(
        (policy / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    if policy_manifest.task_id != task.case_id:
        raise PublicControlError("M6 coordinate stage policy join changed")
    database = database_manifest.resolve(strict=True)
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    groups, sources, hits = _write_selected_inputs(catalogue, policy, output)
    registration_root = output / "registration"
    stimulus = edge_stimulus(_fault(case_root, task))
    stage_outcome = _coordinate_stage_outcome(stimulus, hits)
    if stage_outcome is not None:
        registration_root.mkdir()
        atomic_write_text(registration_root / "coordinate_sources.jsonl", "")
        atomic_write_text(registration_root / "coordinate_hit_mappings.jsonl", "")
        atomic_write_json(
            registration_root / "registration_manifest.json",
            {"schema_version": "1.0", "status": "completed_no_model"},
        )
    else:
        register_pdb_coordinates(
            PdbCoordinateRegistrationRequest(
                structural_hits_jsonl=hits,
                sequence_groups_jsonl=groups,
                database_manifest=database,
                output_directory=registration_root,
                maximum_hits_per_sequence_group=3,
                maximum_mappings=25,
                materialise_coordinate_objects=True,
                allow_network_acquisition=False,
                progress=False,
            )
        )
    _write_bundle_manifest(
        output,
        adapter=_COORDINATE_STAGE_ADAPTER,
        kind="coordinate_stage",
        task_id=task.case_id,
        inputs={
            "case_task": case_root / "task.json",
            "catalogue": catalogue / "bundle_manifest.json",
            "policy": policy / "bundle_manifest.json",
            "database_manifest": database,
            "selected_sequence_groups": groups,
            "selected_source_records": sources,
            "selected_structural_hits": hits,
        },
        outputs={
            "coordinate_sources": registration_root / "coordinate_sources.jsonl",
            "coordinate_hit_mappings": (
                registration_root / "coordinate_hit_mappings.jsonl"
            ),
            "registration": registration_root / "registration_manifest.json",
        },
        early_outcome=stage_outcome,
    )
    return output


def run_m6_prepare_case_task(
    case_task_directory: Path,
    preflight_bundle: Path,
    catalogue_bundle: Path,
    policy_bundle: Path | None,
    coordinate_stage_bundle: Path | None,
    output_directory: Path,
) -> Path:
    """Prepare one blind case and emit zero or more first-copy hypotheses."""

    case_root, task = _load_case_task(case_task_directory)
    preflight = preflight_bundle.resolve(strict=True)
    catalogue, catalogue_task = _load_catalogue_bundle(catalogue_bundle)
    if catalogue_task.catalogue_key != task.catalogue_key:
        raise PublicControlError("M6 case preparation catalogue join changed")
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(case_root / "task.json", output / "case_task.json")
    for name in ("reflections.mtz", "analysis_config.json", "model_policy.json"):
        shutil.copy2(case_root / name, output / name)
    if (case_root / "fault_control.json").is_file():
        shutil.copy2(case_root / "fault_control.json", output / "fault_control.json")
    shutil.copytree(preflight, output / "preflight_bundle")
    early_manifest = M6BundleManifest.model_validate_json(
        (preflight / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    shutil.copy2(
        catalogue / "catalogue/sequence_groups.jsonl",
        output / "all_sequence_groups.jsonl",
    )
    shutil.copy2(
        catalogue / "catalogue/source_records.jsonl",
        output / "all_source_records.jsonl",
    )
    if early_manifest.early_outcome is not None:
        case_plan = M6HypothesisGroupTask(
            schema_version="1.0",
            adapter_version=_CASE_ADAPTER,
            case_id=task.case_id,
            catalogue_key=task.catalogue_key,
            early_outcome=early_manifest.early_outcome,
            hypothesis_count=0,
            hypothesis_ids=(),
        )
        atomic_write_json(
            output / "case_plan.json",
            case_plan.model_dump(mode="json"),
        )
        _write_bundle_manifest(
            output,
            adapter=_CASE_ADAPTER,
            kind="case_preparation",
            task_id=task.case_id,
            inputs={
                "case_task": case_root / "task.json",
                "preflight": preflight / "bundle_manifest.json",
                "catalogue": catalogue / "bundle_manifest.json",
            },
            outputs={
                "case_plan": output / "case_plan.json",
                "sequence_groups": output / "all_sequence_groups.jsonl",
                "source_records": output / "all_source_records.jsonl",
            },
            early_outcome=early_manifest.early_outcome,
            hypothesis_count=0,
        )
        return output
    if policy_bundle is None:
        raise PublicControlError("active M6 case lacks a trusted policy bundle")
    policy = policy_bundle.resolve(strict=True)
    groups_path, sources_path, hits_path = _write_selected_inputs(
        catalogue, policy, output
    )
    fault = _fault(case_root, task)
    stimulus = edge_stimulus(fault)
    stage_root: Path | None = None
    stage_manifest: M6BundleManifest | None = None
    stage_sources: Path | None = None
    stage_mappings: Path | None = None
    if coordinate_stage_bundle is not None:
        stage_root = coordinate_stage_bundle.resolve(strict=True)
        stage_manifest = M6BundleManifest.model_validate_json(
            (stage_root / "bundle_manifest.json").read_text(encoding="utf-8")
        )
        if (
            stage_manifest.adapter_version != _COORDINATE_STAGE_ADAPTER
            or stage_manifest.task_id != task.case_id
        ):
            raise PublicControlError("M6 coordinate stage identity changed")
        for name, selected in (
            ("selected_sequence_groups", groups_path),
            ("selected_source_records", sources_path),
            ("selected_structural_hits", hits_path),
        ):
            if stage_manifest.input_sha256.get(name) != sha256_file(selected):
                raise PublicControlError("M6 coordinate stage selected inputs changed")
        stage_sources = stage_root / "registration/coordinate_sources.jsonl"
        stage_mappings = stage_root / "registration/coordinate_hit_mappings.jsonl"
        stage_registration = stage_root / "registration/registration_manifest.json"
        if (
            sha256_file(stage_sources)
            != stage_manifest.output_sha256.get("coordinate_sources")
            or sha256_file(stage_mappings)
            != stage_manifest.output_sha256.get("coordinate_hit_mappings")
            or sha256_file(stage_registration)
            != stage_manifest.output_sha256.get("registration")
        ):
            raise PublicControlError("M6 coordinate stage outputs changed")
        shutil.copy2(
            stage_root / "bundle_manifest.json",
            output / "coordinate_stage_manifest.json",
        )
    typed_outcome: str | None = None
    hypothesis_count = 0
    hypothesis_ids: tuple[str, ...] = ()
    if stimulus == "missing_pdb_model":
        if stage_manifest is not None and stage_manifest.early_outcome is None:
            raise PublicControlError(
                "M6 missing-model case has an inconsistent coordinate stage"
            )
        write_missing_model_stimulus(
            accepted_hits=hits_path,
            output_directory=output / "missing-model-stimulus",
        )
        typed_outcome = "completed_no_model"
    elif not hits_path.read_text(encoding="utf-8").strip():
        if stage_manifest is not None and stage_manifest.early_outcome is None:
            raise PublicControlError(
                "M6 no-hit case has an inconsistent coordinate stage"
            )
        typed_outcome = "completed_no_model"
    else:
        if (
            stage_manifest is None
            or stage_sources is None
            or stage_mappings is None
            or stage_manifest.early_outcome is not None
        ):
            raise PublicControlError(
                "active M6 case lacks a ready trusted coordinate stage"
            )
        models = prepare_experimental_models(
            ExperimentalModelPreparationRequest(
                coordinate_sources_jsonl=stage_sources,
                coordinate_hit_mappings_jsonl=stage_mappings,
                sequence_groups_jsonl=groups_path,
                output_directory=output / "model-preparation",
                progress=False,
            )
        )
        matthews = enumerate_matthews(
            MatthewsRequest(
                crystal_manifest=preflight / "crystal_manifest.json",
                pipeline_config=case_root / "analysis_config.json",
                preflight_jsonl=preflight / "preflight/mtz_preflight.jsonl",
                sequence_groups_jsonl=groups_path,
                source_records_jsonl=sources_path,
                output_directory=output / "matthews",
                progress=False,
            )
        )
        funnel = build_diverse_first_copy_funnel(
            DiverseFirstCopyFunnelRequest(
                coordinate_sources_jsonl=(stage_sources,),
                processed_models_jsonl=(models.records_jsonl,),
                model_preparation_manifests=(models.manifest_json,),
                coordinate_hit_mappings_jsonl=stage_mappings,
                sequence_groups_jsonl=groups_path,
                matthews_hypotheses_jsonl=matthews.jsonl_path,
                mtz_preflight_jsonl=preflight / "preflight/mtz_preflight.jsonl",
                pipeline_config=case_root / "analysis_config.json",
                output_directory=output / "first-copy-funnel",
                crystal_ids=(task.case_id,),
                maximum_first_copy_jobs=25,
                progress=False,
            )
        )
        hypothesis_count = len(funnel.hypotheses)
        hypothesis_ids = tuple(item.hypothesis_id for item in funnel.hypotheses)
        if hypothesis_count == 0:
            typed_outcome = "completed_no_model"
    case_plan = M6HypothesisGroupTask(
        schema_version="1.0",
        adapter_version=_CASE_ADAPTER,
        case_id=task.case_id,
        catalogue_key=task.catalogue_key,
        early_outcome=typed_outcome,
        hypothesis_count=hypothesis_count,
        hypothesis_ids=hypothesis_ids,
    )
    atomic_write_json(
        output / "case_plan.json",
        case_plan.model_dump(mode="json"),
    )
    shutil.copytree(policy, output / "policy_bundle")
    outputs = {
        "case_plan": output / "case_plan.json",
        "sequence_groups": output / "all_sequence_groups.jsonl",
        "source_records": output / "all_source_records.jsonl",
    }
    if hypothesis_count:
        outputs["funnel_manifest"] = output / "first-copy-funnel/funnel_manifest.json"
    if stimulus == "missing_pdb_model":
        outputs["missing_model_route"] = (
            output / "missing-model-stimulus/model_route_manifest.json"
        )
    bundle_inputs = {
        "case_task": case_root / "task.json",
        "preflight": preflight / "bundle_manifest.json",
        "catalogue": catalogue / "bundle_manifest.json",
        "policy": policy / "bundle_manifest.json",
    }
    if stage_root is not None:
        bundle_inputs["coordinate_stage"] = stage_root / "bundle_manifest.json"
        outputs["coordinate_stage"] = output / "coordinate_stage_manifest.json"
    _write_bundle_manifest(
        output,
        adapter=_CASE_ADAPTER,
        kind="case_preparation",
        task_id=task.case_id,
        inputs=bundle_inputs,
        outputs=outputs,
        early_outcome=typed_outcome,
        hypothesis_count=hypothesis_count,
    )
    return output


def _phaser_output(directory: Path) -> PhaserRunOutput:
    root = directory.resolve(strict=True)
    result_json = root / "normalised_mr_result.json"
    result_jsonl = root / "normalised_mr_result.jsonl"
    command = root / "phaser_command.json"
    return PhaserRunOutput(
        result=NormalisedMrResult.model_validate_json(
            result_json.read_text(encoding="utf-8")
        ),
        result_json=result_json,
        result_jsonl=result_jsonl,
        command_json=command,
    )


def _hypotheses(case_bundle: Path) -> dict[str, MrHypothesis]:
    root = case_bundle / "first-copy-funnel/hypotheses"
    records: dict[str, MrHypothesis] = {}
    if not root.is_dir():
        return records
    for path in sorted(root.glob("*.jsonl")):
        hypothesis = MrHypothesis.model_validate_json(
            path.read_text(encoding="utf-8").strip()
        )
        records[hypothesis.hypothesis_id] = hypothesis
    return records


def _case_plan(case_bundle: Path) -> M6HypothesisGroupTask:
    return M6HypothesisGroupTask.model_validate_json(
        (case_bundle / "case_plan.json").read_text(encoding="utf-8")
    )


def _first_rank(
    attempt: PhaserRunOutput,
    hypothesis: MrHypothesis,
    candidate_rank: Mapping[str, int],
) -> tuple[object, ...]:
    result = attempt.result
    return (
        -(result.llg if result.llg is not None else float("-inf")),
        -(result.tfz if result.tfz is not None else float("-inf")),
        candidate_rank.get(hypothesis.sequence_group_id, 10**9),
        hypothesis.hypothesis_id,
    )


def _m6_seed_advancement_rows(
    case_id: str,
    eligible: tuple[tuple[PhaserRunOutput, MrHypothesis], ...],
    selected_hypothesis_ids: set[str],
    candidate_rank: Mapping[str, int],
) -> tuple[dict[str, object], ...]:
    """Retain the disposition and ranking evidence for every eligible seed."""

    return tuple(
        {
            "schema_version": "1.0",
            "case_id": case_id,
            "hypothesis_id": hypothesis.hypothesis_id,
            "sequence_group_id": hypothesis.sequence_group_id,
            "model_id": hypothesis.model_id,
            "expected_copy_count": hypothesis.copy_count_expected,
            "llg": attempt.result.llg,
            "tfz": attempt.result.tfz,
            "candidate_rank": candidate_rank.get(hypothesis.sequence_group_id),
            "advancement_rank": rank,
            "advancement_disposition": (
                "selected"
                if hypothesis.hypothesis_id in selected_hypothesis_ids
                else "deferred_seed_cap"
            ),
            "eligible_hypothesis_retained": True,
        }
        for rank, (attempt, hypothesis) in enumerate(eligible, start=1)
    )


def _rank_m6_seed_candidates(
    packed: tuple[tuple[PhaserRunOutput, MrHypothesis], ...],
    candidate_rank: Mapping[str, int],
) -> tuple[tuple[PhaserRunOutput, MrHypothesis], ...]:
    """Order every eligible copy hypothesis without a copy-count preference."""

    return tuple(
        sorted(
            packed,
            key=lambda item: _first_rank(item[0], item[1], candidate_rank),
        )
    )


def _select_m6_seed_candidates(
    packed: tuple[tuple[PhaserRunOutput, MrHypothesis], ...],
    candidate_rank: Mapping[str, int],
) -> tuple[
    tuple[tuple[PhaserRunOutput, MrHypothesis], ...],
    tuple[tuple[PhaserRunOutput, MrHypothesis], ...],
]:
    """Return every eligible hypothesis and the unchanged five-seed slice."""

    eligible = _rank_m6_seed_candidates(packed, candidate_rank)
    return eligible, eligible[:_M6_SEED_CAP]


def run_m6_select_seeds_task(
    case_bundle: Path,
    first_copy_results: tuple[Path, ...],
    output_directory: Path,
) -> Path:
    """Select up to five retained advancement seeds for exactly one case."""

    case = case_bundle.resolve(strict=True)
    plan = _case_plan(case)
    case_id = plan.case_id
    expected = plan.hypothesis_count
    attempts = tuple(
        sorted(
            (_phaser_output(path) for path in first_copy_results),
            key=lambda attempt: attempt.result.hypothesis_id,
        )
    )
    if len(attempts) != expected:
        raise PublicControlError(
            f"M6 first-copy result count changed for {case_id}: "
            f"{len(attempts)} != {expected}"
        )
    hypotheses = _hypotheses(case)
    ranking_path = case / "policy_bundle/policy/candidate_ranking.jsonl"
    candidate_rank = (
        {}
        if not ranking_path.is_file()
        else {
            cast(str, row["sequence_group_id"]): _json_integer(
                row, "rank", "candidate ranking", minimum=1
            )
            for row in _jsonl_dicts(ranking_path, required=True)
        }
    )
    packed: list[tuple[PhaserRunOutput, MrHypothesis]] = []
    for attempt in attempts:
        hypothesis = hypotheses[attempt.result.hypothesis_id]
        if _supported_first_copy_count(
            attempt, expected_copy_count=hypothesis.copy_count_expected
        ):
            packed.append((attempt, hypothesis))
    eligible, selected = _select_m6_seed_candidates(tuple(packed), candidate_rank)
    selected_hypothesis_ids = {hypothesis.hypothesis_id for _, hypothesis in selected}
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    all_results = output / "first-copy-results"
    all_results.mkdir()
    for attempt in attempts:
        shutil.copytree(
            attempt.result_json.parent,
            all_results / attempt.result.hypothesis_id,
        )
    rows: list[dict[str, object]] = []
    for attempt, hypothesis in selected:
        solution_id, validation, review_manifest, coordinate = _review_seed(
            output, attempt
        )
        placed = _supported_first_copy_count(
            attempt, expected_copy_count=hypothesis.copy_count_expected
        )
        task = M6SeedTask(
            schema_version="1.0",
            case_id=case_id,
            seed_solution_id=solution_id,
            hypothesis_id=hypothesis.hypothesis_id,
            sequence_group_id=hypothesis.sequence_group_id,
            model_id=hypothesis.model_id,
            expected_copy_count=hypothesis.copy_count_expected,
            first_copy_placed_count=placed,
            search_model_sha256=sha256_file(coordinate),
        )
        task_root = output / "seed_tasks" / solution_id
        task_root.mkdir(parents=True)
        atomic_write_json(task_root / "task.json", task.model_dump(mode="json"))
        rows.append(
            {
                **task.model_dump(mode="json"),
                "validation": str(validation.relative_to(output)),
                "review_manifest": str(review_manifest.relative_to(output)),
                "search_model": str(coordinate.relative_to(output)),
            }
        )
    seeds_jsonl = output / "seed_tasks.jsonl"
    atomic_write_text(
        seeds_jsonl,
        "".join(f"{json.dumps(row, sort_keys=True)}\n" for row in rows),
    )
    advancement_path = output / "seed_advancement.jsonl"
    advancement_rows = _m6_seed_advancement_rows(
        case_id,
        eligible,
        selected_hypothesis_ids,
        candidate_rank,
    )
    atomic_write_text(
        advancement_path,
        "".join(f"{canonical_json_text(row)}\n" for row in advancement_rows),
    )
    atomic_write_json(
        output / "seed_plan.json",
        {
            "schema_version": "1.0",
            "adapter_version": _SEED_ADAPTER,
            "case_id": case_id,
            "first_copy_attempt_count": len(attempts),
            "advancement_eligible_count": len(eligible),
            "advancement_deferred_count": len(eligible) - len(selected),
            "selected_seed_count": len(selected),
            "typed_outcome": (None if selected else "completed_no_credible_seed"),
            "all_first_copy_attempts_retained": True,
            "all_advancement_eligible_hypotheses_retained": True,
            "copy_count_advancement_preference": "none",
        },
    )
    _write_bundle_manifest(
        output,
        adapter=_SEED_ADAPTER,
        kind="seed_selection",
        task_id=case_id,
        inputs={
            "case_plan": case / "case_plan.json",
            **{
                f"first_copy_{index}": attempt.result_json
                for index, attempt in enumerate(attempts)
            },
        },
        outputs={
            "seed_plan": output / "seed_plan.json",
            "seed_tasks": seeds_jsonl,
            "seed_advancement": advancement_path,
        },
    )
    return output


def run_m6_empty_seeds_task(case_bundle: Path, output_directory: Path) -> Path:
    """Emit the explicit zero-hypothesis/early-outcome seed bundle."""

    case = case_bundle.resolve(strict=True)
    plan = _case_plan(case)
    if plan.hypothesis_count != 0:
        raise PublicControlError("M6 empty-seed branch received a runnable case")
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "first-copy-results").mkdir()
    (output / "seed_tasks").mkdir()
    atomic_write_text(output / "seed_tasks.jsonl", "")
    atomic_write_text(output / "seed_advancement.jsonl", "")
    atomic_write_json(
        output / "seed_plan.json",
        {
            "schema_version": "1.0",
            "adapter_version": _SEED_ADAPTER,
            "case_id": plan.case_id,
            "first_copy_attempt_count": 0,
            "advancement_eligible_count": 0,
            "advancement_deferred_count": 0,
            "selected_seed_count": 0,
            "typed_outcome": plan.early_outcome or "completed_no_credible_seed",
            "all_first_copy_attempts_retained": True,
            "all_advancement_eligible_hypotheses_retained": True,
            "copy_count_advancement_preference": "none",
        },
    )
    _write_bundle_manifest(
        output,
        adapter=_SEED_ADAPTER,
        kind="seed_selection",
        task_id=plan.case_id,
        inputs={"case_plan": case / "case_plan.json"},
        outputs={
            "seed_plan": output / "seed_plan.json",
            "seed_tasks": output / "seed_tasks.jsonl",
            "seed_advancement": output / "seed_advancement.jsonl",
        },
    )
    return output


def _seed_task(seed_bundle: Path, seed_solution_id: str) -> M6SeedTask:
    return M6SeedTask.model_validate_json(
        (seed_bundle / "seed_tasks" / seed_solution_id / "task.json").read_text(
            encoding="utf-8"
        )
    )


def run_m6_add_copy_task(
    case_bundle: Path,
    seed_bundle: Path,
    seed_solution_id: str,
    phenix_manifest: Path,
    output_directory: Path,
    *,
    threads: int,
) -> Path:
    """Run one scientifically sequential copy chain for one independent seed."""

    case = case_bundle.resolve(strict=True)
    seeds = seed_bundle.resolve(strict=True)
    task = _seed_task(seeds, seed_solution_id)
    review = seeds / "review" / seed_solution_id
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    best_parent = output / "best_parent.pdb"
    best_copy_count = task.first_copy_placed_count
    if task.first_copy_placed_count >= task.expected_copy_count:
        atomic_write_text(output / "additional_copy_series_results.jsonl", "")
        atomic_write_json(
            output / "additional_copy_series_summary.json",
            {
                "schema_version": "1.0",
                "seed_solution_id": seed_solution_id,
                "expected_copy_count": task.expected_copy_count,
                "attempt_count": 0,
                "best_supported_copy_count": best_copy_count,
                "reached_expected_copy_count": True,
                "stop_reason": "first_copy_already_reached_expected_count",
                "parent_retained": True,
            },
        )
        shutil.copy2(review / "assets/solution.pdb", best_parent)
    else:
        series = run_additional_copy_series(
            AddCopyRunRequest(
                review_validation_json=review / "mr_seed_approval.json",
                review_package_manifest=review / "mr_seed_review_manifest.json",
                seed_solution_id=seed_solution_id,
                hypotheses_jsonl=case / "first-copy-funnel/mr_hypotheses.jsonl",
                sequence_groups_jsonl=case
                / "selected-candidates/sequence_groups.jsonl",
                preflight_jsonl=case / "preflight_bundle/preflight/mtz_preflight.jsonl",
                mtz=case / "reflections.mtz",
                search_model=review / "assets/solution.pdb",
                expected_search_model_sha256=task.search_model_sha256,
                phenix_manifest=phenix_manifest.resolve(strict=True),
                output_directory=output / "series",
                threads=threads,
                timeout_seconds=None,
                progress=False,
            )
        )
        shutil.copy2(
            series.results_jsonl, output / "additional_copy_series_results.jsonl"
        )
        shutil.copy2(
            series.summary_json, output / "additional_copy_series_summary.json"
        )
        coordinate = review / "assets/solution.pdb"
        for attempt in series.attempts:
            if attempt.result.additional_copy_supported:
                best_copy_count = max(
                    best_copy_count, attempt.result.best_supported_copy_count
                )
                if attempt.result.output_coordinate_path is not None:
                    coordinate = (
                        attempt.result_json.parent
                        / attempt.result.output_coordinate_path
                    )
        shutil.copy2(coordinate, best_parent)
    shutil.copy2(
        seeds / "seed_tasks" / seed_solution_id / "task.json",
        output / "seed_task.json",
    )
    atomic_write_json(
        output / "best_parent.json",
        {
            "schema_version": "1.0",
            "case_id": task.case_id,
            "seed_solution_id": seed_solution_id,
            "sequence_group_id": task.sequence_group_id,
            "best_supported_copy_count": best_copy_count,
            "parent_coordinate_sha256": sha256_file(best_parent),
            "parent_retained": True,
        },
    )
    return output


def run_m6_select_finalists_task(
    case_bundle: Path,
    seed_bundle: Path,
    add_copy_results: tuple[Path, ...],
    output_directory: Path,
) -> Path:
    """Publish one best retained refinement parent for every selected seed."""

    case = case_bundle.resolve(strict=True)
    seeds = seed_bundle.resolve(strict=True)
    seed_plan = _json_object(seeds / "seed_plan.json", "seed plan")
    expected = _json_integer(seed_plan, "selected_seed_count", "seed plan")
    if len(add_copy_results) != expected:
        raise PublicControlError("M6 additional-copy result count changed")
    by_seed: dict[str, Path] = {}
    for path in add_copy_results:
        root = path.resolve(strict=True)
        parent = _json_object(root / "best_parent.json", "best-parent record")
        seed_id = cast(str, parent["seed_solution_id"])
        if seed_id in by_seed:
            raise PublicControlError(f"duplicate M6 add-copy result: {seed_id}")
        by_seed[seed_id] = root
    expected_seed_ids = {
        cast(str, row["seed_solution_id"])
        for row in _jsonl_dicts(seeds / "seed_tasks.jsonl")
    }
    if set(by_seed) != expected_seed_ids:
        raise PublicControlError("M6 additional-copy result partition changed")
    preflight = MtzPreflightRecord.model_validate_json(
        (case / "preflight_bundle/preflight/mtz_preflight.jsonl")
        .read_text(encoding="utf-8")
        .strip()
    )
    if preflight.selected_observation_labels is None:
        raise PublicControlError("M6 finalist lacks selected observations")
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(seeds, output / "seed_bundle")
    shutil.copytree(case, output / "case_bundle")
    rows: list[dict[str, object]] = []
    for seed_id, add in sorted(by_seed.items()):
        seed = _seed_task(seeds, seed_id)
        parent = _json_object(add / "best_parent.json", "best-parent record")
        task = M6FinalistTask(
            schema_version="1.0",
            case_id=seed.case_id,
            seed_solution_id=seed_id,
            sequence_group_id=seed.sequence_group_id,
            input_copy_count=_json_integer(
                parent,
                "best_supported_copy_count",
                "best-parent record",
                minimum=1,
            ),
            parent_coordinate_sha256=cast(str, parent["parent_coordinate_sha256"]),
            parent_mtz_sha256=sha256_file(case / "reflections.mtz"),
            observation_labels=preflight.selected_observation_labels,
            resolution=preflight.resolution_high_a,
        )
        task_root = output / "finalist_tasks" / seed_id
        task_root.mkdir(parents=True)
        atomic_write_json(task_root / "task.json", task.model_dump(mode="json"))
        shutil.copy2(add / "best_parent.pdb", task_root / "parent_coordinate.pdb")
        shutil.copy2(case / "reflections.mtz", task_root / "parent.mtz")
        shutil.copytree(add, output / "add-copy-results" / seed_id)
        rows.append(task.model_dump(mode="json"))
    finalists = output / "finalist_tasks.jsonl"
    atomic_write_text(
        finalists,
        "".join(f"{json.dumps(row, sort_keys=True)}\n" for row in rows),
    )
    atomic_write_json(
        output / "finalist_plan.json",
        {
            "schema_version": "1.0",
            "adapter_version": "m6-nextflow-finalists-v1",
            "case_id": seed_plan["case_id"],
            "finalist_count": len(rows),
            "all_seed_parents_retained": True,
        },
    )
    return output


def run_m6_empty_finalists_task(
    case_bundle: Path, seed_bundle: Path, output_directory: Path
) -> Path:
    """Emit the explicit zero-seed finalist bundle."""

    case = case_bundle.resolve(strict=True)
    seeds = seed_bundle.resolve(strict=True)
    seed_plan = _json_object(seeds / "seed_plan.json", "seed plan")
    if _json_integer(seed_plan, "selected_seed_count", "seed plan") != 0:
        raise PublicControlError("M6 empty-finalist branch received selected seeds")
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "finalist_tasks").mkdir()
    (output / "add-copy-results").mkdir()
    shutil.copytree(seeds, output / "seed_bundle")
    shutil.copytree(case, output / "case_bundle")
    atomic_write_text(output / "finalist_tasks.jsonl", "")
    atomic_write_json(
        output / "finalist_plan.json",
        {
            "schema_version": "1.0",
            "adapter_version": "m6-nextflow-finalists-v1",
            "case_id": seed_plan["case_id"],
            "finalist_count": 0,
            "all_seed_parents_retained": True,
        },
    )
    return output


def run_m6_refinement_task(
    finalist_bundle: Path,
    seed_solution_id: str,
    phenix_manifest: Path,
    output_directory: Path,
    *,
    threads: int,
) -> Path:
    """Run one independent finalist refinement and sequence assessment."""

    bundle = finalist_bundle.resolve(strict=True)
    task_root = bundle / "finalist_tasks" / seed_solution_id
    task = M6FinalistTask.model_validate_json(
        (task_root / "task.json").read_text(encoding="utf-8")
    )
    case = bundle / "case_bundle"
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = run_t12_candidate(
        T12RunRequest(
            seed_solution_id=seed_solution_id,
            sequence_group_id=task.sequence_group_id,
            input_copy_count=task.input_copy_count,
            parent_coordinate=task_root / "parent_coordinate.pdb",
            parent_coordinate_sha256=task.parent_coordinate_sha256,
            parent_mtz=task_root / "parent.mtz",
            parent_mtz_sha256=task.parent_mtz_sha256,
            observation_labels=task.observation_labels,
            sequence_groups_jsonl=case / "all_sequence_groups.jsonl",
            source_records_jsonl=case / "all_source_records.jsonl",
            resolution=task.resolution,
            phenix_manifest=phenix_manifest.resolve(strict=True),
            output_directory=output / "t12",
            threads=threads,
            timeout_seconds=None,
            progress=False,
        )
    )
    shutil.copy2(task_root / "task.json", output / "finalist_task.json")
    atomic_write_json(
        output / "refinement_bundle.json",
        {
            "schema_version": "1.0",
            "case_id": task.case_id,
            "seed_solution_id": seed_solution_id,
            "refinement_sha256": sha256_file(result.refinement_json),
            "sequence_sha256": sha256_file(result.sequence_json),
        },
    )
    return output


def _duplicate_locus_outcome(
    fault: dict[str, object], sources: tuple[SourceProteinRecord, ...]
) -> tuple[str, str] | None:
    if fault.get("duplicate_locus") is True:
        counts = Counter(source.sequence_group_id for source in sources)
        if max(counts.values(), default=0) < 2:
            raise PublicControlError("M6 duplicate-locus control lost its ambiguity")
        return "ambiguous_multiple_loci", "duplicate_loci_retained"
    return None


def run_m6_assemble_case_task(
    case_bundle: Path,
    finalist_bundle: Path,
    refinement_results: tuple[Path, ...],
    output_directory: Path,
) -> Path:
    """Assemble one complete retained case record from completed child tasks."""

    case = case_bundle.resolve(strict=True)
    finalists = finalist_bundle.resolve(strict=True)
    case_plan = _case_plan(case)
    finalist_plan = _json_object(finalists / "finalist_plan.json", "case/finalist plan")
    case_id = case_plan.case_id
    expected_refinements = _json_integer(
        finalist_plan, "finalist_count", "case/finalist plan"
    )
    if len(refinement_results) != expected_refinements:
        raise PublicControlError("M6 refinement result count changed")
    groups = _jsonl(case / "all_sequence_groups.jsonl", SequenceGroupRecord)
    sources = _jsonl(case / "all_source_records.jsonl", SourceProteinRecord)
    task = M6CaseTask.model_validate_json(
        (case / "case_task.json").read_text(encoding="utf-8")
    )
    if task.case_id != case_id:
        raise PublicControlError("M6 case-evidence identity changed")
    fault = (
        {}
        if not (case / "fault_control.json").is_file()
        else _json_object(case / "fault_control.json", "fault control")
    )
    hypotheses = _hypotheses(case)
    seed_bundle = finalists / "seed_bundle"
    first_rows: list[dict[str, object]] = []
    first_results: list[NormalisedMrResult] = []
    first_root = seed_bundle / "first-copy-results"
    if first_root.is_dir():
        for directory in sorted(path for path in first_root.iterdir() if path.is_dir()):
            attempt = _phaser_output(directory)
            first_results.append(attempt.result)
            first_rows.append(
                {
                    "hypothesis": hypotheses[attempt.result.hypothesis_id].model_dump(
                        mode="json"
                    ),
                    "result": attempt.result.model_dump(mode="json"),
                }
            )
    copy_rows: list[AdditionalCopyResult] = []
    add_root = finalists / "add-copy-results"
    if add_root.is_dir():
        for path in sorted(add_root.glob("*/additional_copy_series_results.jsonl")):
            copy_rows.extend(_jsonl(path, AdditionalCopyResult))
    refinement_children: list[
        tuple[M6FinalistTask, BriefRefinementResult, SequenceMapResult, Path]
    ] = []
    for directory in refinement_results:
        root = directory.resolve(strict=True)
        task_record = M6FinalistTask.model_validate_json(
            (root / "finalist_task.json").read_text(encoding="utf-8")
        )
        refinement = BriefRefinementResult.model_validate_json(
            (root / "t12/brief_refinement_result.json").read_text(encoding="utf-8")
        )
        sequence = SequenceMapResult.model_validate_json(
            (root / "t12/sequence_map_result.json").read_text(encoding="utf-8")
        )
        refinement_children.append((task_record, refinement, sequence, root))
    seed_ids = [item[0].seed_solution_id for item in refinement_children]
    if len(seed_ids) != len(set(seed_ids)):
        raise PublicControlError("duplicate M6 refinement result")
    refinement_children.sort(key=lambda item: item[0].seed_solution_id)
    refinements = [item[1] for item in refinement_children]
    sequences = [item[2] for item in refinement_children]
    refinement_by_seed = {
        task_record.seed_solution_id: root
        for task_record, _, _, root in refinement_children
    }
    seed_rows = _jsonl_dicts(seed_bundle / "seed_tasks.jsonl")
    selected_rows: list[dict[str, object]] = []
    first_by_hypothesis = {row.hypothesis_id: row for row in first_results}
    copy_best: dict[str, int] = {}
    for result in copy_rows:
        copy_best[result.seed_solution_id] = max(
            copy_best.get(result.seed_solution_id, 0),
            result.best_supported_copy_count,
        )
    for row in seed_rows:
        hypothesis_id = cast(str, row["hypothesis_id"])
        seed_id = cast(str, row["seed_solution_id"])
        first = first_by_hypothesis[hypothesis_id]
        selected_rows.append(
            {
                "seed_solution_id": seed_id,
                "hypothesis_id": hypothesis_id,
                "sequence_group_id": row["sequence_group_id"],
                "model_id": row["model_id"],
                "expected_copy_count": row["expected_copy_count"],
                "first_copy_execution_status": first.execution_status.value,
                "first_copy_placed_count": first.placed_copy_count,
                "llg": first.llg,
                "tfz": first.tfz,
                "best_supported_copy_count": max(
                    cast(int, row["first_copy_placed_count"]),
                    copy_best.get(seed_id, 0),
                ),
                "parent_retained": True,
            }
        )
    identity_decision = derive_m6_identity_decision(
        case_id=case_id,
        selected_seed_results=selected_rows,
        sequence_groups=groups,
    )
    edge_observations = observe_case_edge(
        case_id=case_id,
        case_bundle=case,
        fault_control=fault,
        sequence_groups=groups,
        hypothesis_count=case_plan.hypothesis_count,
    )
    sequence_summaries = [
        {
            "case_id": case_id,
            "sequence_assessment_id": item.sequence_assessment_id,
            "seed_solution_id": item.seed_solution_id,
            "execution_status": item.execution_status.value,
            "complete_catalogue_group_count": item.complete_catalogue_group_count,
            "scored_group_count": item.scored_group_count,
            "best_score": item.best_score,
            "best_score_z": item.best_score_z,
            "top_candidates": [
                candidate.model_dump(mode="json") for candidate in item.candidates[:5]
            ],
            "warnings": list(item.warnings),
        }
        for item in sequences
    ]
    seed_plan = _json_object(seed_bundle / "seed_plan.json", "seed plan")
    typed_outcome = cast(str | None, seed_plan.get("typed_outcome"))
    scientific_status = "abstained"
    execution_status = "completed"
    failure_class = None
    if refinements:
        scientific_status = "candidate_evidence"
        typed_outcome = typed_outcome or "completed_candidate_evidence"
    if typed_outcome == "missing_phenix":
        execution_status = "failed"
        scientific_status = "not_assessed"
        failure_class = "missing_phenix"
    elif typed_outcome == "completed_map_only_mtz":
        scientific_status = "typed_control_outcome"
    elif typed_outcome == "ambiguous_columns_conflicting":
        scientific_status = "abstained"
    duplicate_outcome = _duplicate_locus_outcome(fault, sources)
    if duplicate_outcome is not None:
        scientific_status, typed_outcome = duplicate_outcome
    policy = case / "policy_bundle/policy"
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    ranking_path = output / "candidate_ranking.jsonl"
    policy_path = output / "model_policy_report.json"
    if policy.is_dir():
        shutil.copy2(policy / "candidate_ranking.jsonl", ranking_path)
        shutil.copy2(policy / "model_policy_report.json", policy_path)
    else:
        atomic_write_text(ranking_path, "")
        atomic_write_json(
            policy_path,
            {
                "schema_version": "1.0",
                "case_id": case_id,
                "early_outcome": True,
            },
        )
    case_record = M6CaseEvidence(
        schema_version="2.0",
        adapter_version=_CASE_EVIDENCE_ADAPTER,
        case_id=case_id,
        execution_status=execution_status,
        scientific_status=scientific_status,
        typed_outcome=typed_outcome or "completed_no_credible_seed",
        failure_class=failure_class,
        candidate_count=len(groups),
        retained_candidate_count=len(groups),
        all_candidates_retained=True,
        candidate_ranking_path=(
            None
            if not ranking_path.read_text(encoding="utf-8").strip()
            else ranking_path.name
        ),
        model_policy_report_path=(None if not policy.is_dir() else policy_path.name),
        first_copy_attempt_count=len(first_rows),
        additional_copy_attempt_count=len(copy_rows),
        refinement_attempt_count=len(refinements),
        sequence_assessment_count=len(sequences),
        identity_decision=identity_decision,
        edge_observations=edge_observations,
        first_copy_results=tuple(first_rows),
        selected_seed_results=tuple(selected_rows),
        additional_copy_results=tuple(
            item.model_dump(mode="json") for item in copy_rows
        ),
        refinement_results=tuple(item.model_dump(mode="json") for item in refinements),
        sequence_summaries=tuple(sequence_summaries),
    )
    atomic_write_json(
        output / "identity_decision.json",
        identity_decision.model_dump(mode="json"),
    )
    atomic_write_text(
        output / "edge_observations.jsonl",
        "".join(
            f"{canonical_json_text(observation)}\n" for observation in edge_observations
        ),
    )
    atomic_write_json(output / "case_record.json", case_record.model_dump(mode="json"))
    atomic_write_text(
        output / "first_copy_results.jsonl",
        "".join(f"{canonical_json_text(item)}\n" for item in first_results),
    )
    atomic_write_text(
        output / "additional_copy_results.jsonl",
        "".join(f"{canonical_json_text(item)}\n" for item in copy_rows),
    )
    atomic_write_text(
        output / "refinement_results.jsonl",
        "".join(f"{canonical_json_text(item)}\n" for item in refinements),
    )
    atomic_write_text(
        output / "sequence_results.jsonl",
        "".join(f"{canonical_json_text(item)}\n" for item in sequences),
    )
    atomic_write_text(
        output / "sequence_summary.jsonl",
        "".join(f"{json.dumps(item, sort_keys=True)}\n" for item in sequence_summaries),
    )
    shutil.copytree(case, output / "raw/case")
    shutil.copytree(finalists, output / "raw/finalists")
    for seed_id, root in sorted(refinement_by_seed.items()):
        shutil.copytree(root, output / "raw/refinements" / seed_id)
    atomic_write_json(
        output / "case_evidence_manifest.json",
        {
            "schema_version": "2.0",
            "adapter_version": _CASE_EVIDENCE_ADAPTER,
            "case_id": case_id,
            "case_record_sha256": sha256_file(output / "case_record.json"),
            "identity_decision_sha256": sha256_file(output / "identity_decision.json"),
            "edge_observations_sha256": sha256_file(output / "edge_observations.jsonl"),
            "all_candidates_retained": True,
            "all_child_attempts_retained": True,
        },
    )
    return output


def _atomic_concatenate_jsonl(destination: Path, sources: tuple[Path, ...]) -> None:
    """Concatenate canonical JSONL sources with bounded memory and atomic publish."""

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            for source in sources:
                with source.open("rb") as stream:
                    for line in stream:
                        text = line.decode("utf-8").rstrip("\r\n")
                        if text:
                            output.write(text.encode("utf-8") + b"\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _atomic_gzip(source: Path, destination: Path) -> None:
    """Write one deterministic gzip stream without loading its source into memory."""

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as raw:
            temporary = Path(raw.name)
            with gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=raw,
                mtime=0,
            ) as compressed, source.open("rb") as stream:
                shutil.copyfileobj(stream, compressed, length=1024 * 1024)
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(temporary, destination)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def run_m6_aggregate_track_task(
    case_evidence: tuple[Path, ...],
    runner_root: Path,
    protocol: Path,
    database_manifest: Path,
    phenix_manifest: Path,
    track: M6ScientificTrack,
    output_directory: Path,
) -> Path:
    """Deterministically aggregate one complete Nextflow M6 track."""

    expected_ids = m6_track_case_ids(track)
    by_id: dict[str, Path] = {}
    records_by_id: dict[str, dict[str, object]] = {}
    for directory in case_evidence:
        root = directory.resolve(strict=True)
        typed_record = M6CaseEvidence.model_validate_json(
            (root / "case_record.json").read_text(encoding="utf-8")
        )
        record = cast(dict[str, object], typed_record.model_dump(mode="json"))
        case_id = typed_record.case_id
        if case_id in by_id:
            raise PublicControlError(f"duplicate M6 case evidence: {case_id}")
        by_id[case_id] = root
        records_by_id[case_id] = record
    if tuple(sorted(by_id)) != tuple(sorted(expected_ids)):
        raise PublicControlError("M6 Nextflow case evidence partition changed")
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    records = tuple(records_by_id[case_id] for case_id in expected_ids)
    case_results = output / "m6_case_results.jsonl"
    rankings = output / "m6_candidate_rankings.jsonl"
    policies = output / "m6_model_policy_results.jsonl"
    first_copy = output / "m6_first_copy_results.jsonl"
    additional = output / "m6_additional_copy_results.jsonl"
    refinements = output / "m6_refinement_results.jsonl"
    sequences = output / "m6_sequence_results.jsonl"
    sequence_summary = output / "m6_sequence_summary.jsonl"
    atomic_write_text(
        case_results,
        "".join(f"{json.dumps(row, sort_keys=True)}\n" for row in records),
    )
    _atomic_concatenate_jsonl(
        rankings,
        tuple(by_id[case_id] / "candidate_ranking.jsonl" for case_id in expected_ids),
    )
    rankings_gzip = output / "m6_candidate_rankings.jsonl.gz"
    _atomic_gzip(rankings, rankings_gzip)
    atomic_write_text(
        policies,
        "".join(
            json.dumps(
                _json_object(
                    by_id[case_id] / "model_policy_report.json",
                    "model policy report",
                ),
                sort_keys=True,
            )
            + "\n"
            for case_id in expected_ids
            if records_by_id[case_id]["model_policy_report_path"] is not None
        ),
    )
    for destination, source_name in (
        (first_copy, "first_copy_results.jsonl"),
        (additional, "additional_copy_results.jsonl"),
        (refinements, "refinement_results.jsonl"),
        (sequences, "sequence_results.jsonl"),
        (sequence_summary, "sequence_summary.jsonl"),
    ):
        _atomic_concatenate_jsonl(
            destination,
            tuple(by_id[case_id] / source_name for case_id in expected_ids),
        )
    for case_id in expected_ids:
        shutil.copytree(by_id[case_id], output / "cases" / case_id)
    runner = runner_root.resolve(strict=True)
    protocol_path = protocol.resolve(strict=True)
    database = database_manifest.resolve(strict=True)
    phenix = phenix_manifest.resolve(strict=True)
    phenix_document = _json_object(phenix, "Phenix manifest")
    phenix_release = phenix_document.get("phenix_version")
    if not isinstance(phenix_release, str) or not phenix_release:
        raise PublicControlError("M6 Phenix manifest lacks its release identifier")
    outputs = {
        "case_results": sha256_file(case_results),
        "candidate_rankings": sha256_file(rankings),
        "candidate_rankings_gzip": sha256_file(rankings_gzip),
        "model_policy_results": sha256_file(policies),
        "first_copy_results": sha256_file(first_copy),
        "additional_copy_results": sha256_file(additional),
        "refinement_results": sha256_file(refinements),
        "sequence_results": sha256_file(sequences),
        "sequence_summary": sha256_file(sequence_summary),
    }
    input_sha256 = {
        "runner_manifest": sha256_file(runner / "runner_manifest.json"),
        "protocol": sha256_file(protocol_path),
        "database_manifest": sha256_file(database),
        "phenix_manifest": sha256_file(phenix),
    }
    summary = output / "m6_scientific_summary.json"
    atomic_write_json(
        summary,
        {
            "schema_version": "2.0",
            "adapter_version": _RUN_ADAPTER,
            "execution_model": "nextflow_dsl2_slurm_fanout",
            "protocol_id": "m6_independent_prokaryote_homomer_v1",
            "track": track,
            "case_count": len(records),
            "case_ids": list(expected_ids),
            "candidate_count": sum(
                cast(int, row["candidate_count"]) for row in records
            ),
            "retained_candidate_count": sum(
                cast(int, row["retained_candidate_count"]) for row in records
            ),
            "all_candidates_retained": all(
                bool(row["all_candidates_retained"]) for row in records
            ),
            "first_copy_attempt_count": sum(
                cast(int, row["first_copy_attempt_count"]) for row in records
            ),
            "additional_copy_attempt_count": sum(
                cast(int, row["additional_copy_attempt_count"]) for row in records
            ),
            "refinement_attempt_count": sum(
                cast(int, row["refinement_attempt_count"]) for row in records
            ),
            "sequence_assessment_count": sum(
                cast(int, row["sequence_assessment_count"]) for row in records
            ),
            "score_policy": "LLG/TFZ_are_ranking_annotations_only",
            "generalisation_claim": False,
            "phenix_release": phenix_release,
            "case_evidence_digest": canonical_digest(records),
            "scientific_output_digest": canonical_digest(outputs),
            "input_sha256": input_sha256,
            "cache_key": canonical_digest(
                {
                    "adapter_version": _RUN_ADAPTER,
                    "track": track,
                    "input_sha256": input_sha256,
                }
            ),
            "outputs": outputs,
        },
    )
    verify_m6_scientific_output(output, track)
    return output
