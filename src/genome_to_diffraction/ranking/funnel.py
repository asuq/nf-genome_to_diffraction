"""Build a bounded, inspectable exact-predicted-model MR funnel.

This first vertical slice joins immutable exact predicted coordinate sources,
confidence-processed models, candidate-specific Matthews hypotheses, and MTZ
preflight records. It verifies every selected model byte-for-byte, excludes
physically impossible copy counts, preserves each priority feature separately,
and applies both profile-specific and configured hard caps.

It intentionally does not combine evidence into a scalar score or implement the
broader experimental/model-diversity funnel.
"""

import csv
import io
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from pydantic import BaseModel, JsonValue, ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.model_registry.all_eligible import (
    AllEligibleModelRegistryError,
    AllEligibleModelRegistryOutput,
    ValidatedProcessedModelInput,
    build_all_eligible_model_registry,
)
from genome_to_diffraction.schemas.io import (
    ContractLoadError,
    load_contract,
    load_json_document,
)
from genome_to_diffraction.schemas.manifests import PipelineConfig, PrototypeProfile
from genome_to_diffraction.schemas.results import (
    CoordinateHitMappingRecord,
    CoordinateSourceRecord,
    MatthewsHypothesis,
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    MtzPreflightRecord,
    PhysicalStatus,
    PreflightDecision,
    ProcessedModelRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError
from genome_to_diffraction.time import utc_now_iso

_LOGGER = logging.getLogger("genome_to_diffraction.ranking.funnel")
_ADAPTER_VERSION = "exact-predicted-funnel-v1"
_DIVERSE_ADAPTER_VERSION = "multi-source-first-copy-funnel-v1"
_PHASE3_DIVERSE_ADAPTER_VERSION = "multi-source-first-copy-funnel-v2-phase3"
_PHASE3_MAXIMUM_COPY_COUNT = 4
_PHASE3_MAXIMUM_FIRST_COPY_JOBS = 25
_COPY_CAPS: dict[PrototypeProfile, int | None] = {
    PrototypeProfile.SMOKE: 1,
    PrototypeProfile.PILOT: 3,
    PrototypeProfile.EXTENDED: None,
}
_FIRST_COPY_PROFILE_CAPS: dict[PrototypeProfile, int] = {
    PrototypeProfile.SMOKE: 25,
    PrototypeProfile.PILOT: 200,
    PrototypeProfile.EXTENDED: 1000,
}


class FunnelInputError(InputContractError):
    """Funnel inputs cannot be joined without changing their meaning."""


@dataclass(frozen=True)
class ExactPredictedFunnelRequest:
    """Typed inputs for the bounded exact-predicted-model funnel."""

    coordinate_sources_jsonl: Path
    processed_models_jsonl: Path
    model_preparation_manifest: Path
    sequence_groups_jsonl: Path
    matthews_hypotheses_jsonl: Path
    mtz_preflight_jsonl: Path
    pipeline_config: Path
    output_directory: Path
    crystal_ids: tuple[str, ...] = ()
    progress: bool = True


@dataclass(frozen=True)
class ExactPredictedFunnelOutput:
    """Published hypotheses and their relocatable integrity manifest."""

    hypotheses: tuple[MrHypothesis, ...]
    hypotheses_jsonl: Path
    hypotheses_tsv: Path
    manifest_json: Path


@dataclass(frozen=True)
class DiverseFirstCopyFunnelRequest:
    """Multi-source model bundles for one diversity-aware first-copy funnel."""

    coordinate_sources_jsonl: tuple[Path, ...]
    processed_models_jsonl: tuple[Path, ...]
    model_preparation_manifests: tuple[Path, ...]
    sequence_groups_jsonl: Path
    matthews_hypotheses_jsonl: Path
    mtz_preflight_jsonl: Path
    pipeline_config: Path
    output_directory: Path
    coordinate_hit_mappings_jsonl: Path | None = None
    crystal_ids: tuple[str, ...] = ()
    maximum_first_copy_jobs: int | None = None
    joint_copy_search: bool = False
    progress: bool = True


@dataclass(frozen=True)
class DiverseFirstCopyFunnelOutput:
    """Selected A hypotheses plus the independent all-eligible model registry."""

    hypotheses: tuple[MrHypothesis, ...]
    hypotheses_jsonl: Path
    hypotheses_tsv: Path
    model_registry_directory: Path
    manifest_json: Path


@dataclass(frozen=True)
class _ModelPath:
    """Verified processed-model file resolved from its preparation manifest."""

    relative_path: str
    absolute_path: Path
    retained_fraction: float


@dataclass(frozen=True)
class _Candidate:
    """One fully joined candidate before global cap application."""

    hypothesis: MrHypothesis
    model_path: _ModelPath
    coordinate: CoordinateSourceRecord
    model: ProcessedModelRecord
    matthews: MatthewsHypothesis


def _read_jsonl[T: BaseModel](
    path: Path,
    model: type[T],
    *,
    label: str,
    progress: bool,
    allow_empty: bool = False,
) -> tuple[T, ...]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise FunnelInputError(f"{label} input is not a file: {resolved}")
    records: list[T] = []
    with resolved.open(encoding="utf-8") as handle:
        iterator = tqdm(
            handle,
            desc=f"Reading {label}",
            unit="record",
            disable=not progress,
        )
        for line_number, line in enumerate(iterator, start=1):
            if not line.strip():
                continue
            try:
                records.append(model.model_validate_json(line))
            except ValidationError as error:
                raise FunnelInputError(
                    f"invalid {label} record at line {line_number}: {resolved}"
                ) from error
    if not records and (not allow_empty or resolved.stat().st_size != 0):
        raise FunnelInputError(f"{label} input is empty: {resolved}")
    return tuple(records)


def _unique_index[T](
    records: Sequence[T], key: Callable[[T], str], *, label: str
) -> dict[str, T]:
    index: dict[str, T] = {}
    for record in records:
        identifier = key(record)
        if identifier in index:
            raise FunnelInputError(f"duplicate {label}: {identifier}")
        index[identifier] = record
    return index


def _load_object(path: Path, *, label: str) -> tuple[Path, dict[str, object]]:
    resolved = path.resolve(strict=True)
    try:
        document = load_json_document(resolved)
    except ContractLoadError as error:
        raise FunnelInputError(f"cannot load {label}: {error}") from error
    if not isinstance(document, dict):
        raise FunnelInputError(f"{label} must be a JSON object: {resolved}")
    return resolved, cast(dict[str, object], document)


def _manifest_model_paths(
    path: Path,
    models: Sequence[ProcessedModelRecord],
    *,
    progress: bool,
) -> dict[str, _ModelPath]:
    resolved, document = _load_object(path, label="model-preparation manifest")
    if document.get("schema_version") != "1.0":
        raise FunnelInputError("model-preparation manifest schema_version is not '1.0'")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise FunnelInputError("model-preparation manifest entries must be an array")
    model_index = _unique_index(models, lambda item: item.model_id, label="model ID")
    if document.get("processed_model_count") != len(models) or len(entries) != len(
        models
    ):
        raise FunnelInputError(
            "model-preparation manifest count does not match processed models"
        )
    root = resolved.parent.resolve()
    paths: dict[str, _ModelPath] = {}
    iterator = tqdm(
        entries,
        desc="Verifying processed models",
        unit="model",
        disable=not progress,
    )
    for raw_entry in iterator:
        if not isinstance(raw_entry, dict):
            raise FunnelInputError("model-preparation entry must be an object")
        entry = cast(dict[str, object], raw_entry)
        model_id = entry.get("model_id")
        relative_text = entry.get("model_path")
        digest = entry.get("model_sha256")
        retained_fraction = entry.get("retained_fraction")
        if (
            not isinstance(model_id, str)
            or not isinstance(relative_text, str)
            or not isinstance(digest, str)
            or not isinstance(retained_fraction, (int, float))
            or isinstance(retained_fraction, bool)
        ):
            raise FunnelInputError("model-preparation entry has invalid typed fields")
        if model_id in paths:
            raise FunnelInputError(f"duplicate model-preparation entry: {model_id}")
        model = model_index.get(model_id)
        if model is None or model.model_sha256 != digest:
            raise FunnelInputError(
                f"model-preparation entry does not match model record: {model_id}"
            )
        relative = PurePosixPath(relative_text)
        if relative.is_absolute() or ".." in relative.parts or relative_text == "":
            raise FunnelInputError(f"unsafe processed-model path: {relative_text!r}")
        absolute = (root / Path(*relative.parts)).resolve(strict=True)
        if not absolute.is_file() or not absolute.is_relative_to(root):
            raise FunnelInputError(
                f"processed model escaped preparation root: {model_id}"
            )
        actual = sha256_file(
            absolute,
            progress=progress,
            description=f"Verify {model_id[:18]}",
            logger=_LOGGER,
        )
        if actual != digest:
            raise FunnelInputError(f"processed-model checksum mismatch: {model_id}")
        fraction = float(retained_fraction)
        if not 0 < fraction <= 1:
            raise FunnelInputError(f"invalid retained fraction for model: {model_id}")
        paths[model_id] = _ModelPath(relative_text, absolute, fraction)
    if set(paths) != set(model_index):
        raise FunnelInputError("model-preparation entries do not cover every model")
    return paths


def _copy_cap(config: PipelineConfig) -> int:
    profile_cap = _COPY_CAPS[config.prototype.profile]
    if profile_cap is None:
        return config.matthews.max_hypotheses_per_candidate
    return min(profile_cap, config.matthews.max_hypotheses_per_candidate)


def _candidate_sort_key(candidate: _Candidate) -> tuple[object, ...]:
    status_rank = {
        PhysicalStatus.PLAUSIBLE: 0,
        PhysicalStatus.REVIEW: 1,
        PhysicalStatus.IMPOSSIBLE: 2,
    }
    return (
        candidate.hypothesis.crystal_id,
        status_rank[candidate.matthews.physical_status],
        -candidate.matthews.matthews_prior,
        candidate.matthews.rank_within_candidate,
        -candidate.model_path.retained_fraction,
        candidate.coordinate.provider,
        candidate.coordinate.provider_accession,
        candidate.model.model_id,
    )


def _priority_features(
    coordinate: CoordinateSourceRecord,
    model: ProcessedModelRecord,
    model_path: _ModelPath,
    group: SequenceGroupRecord,
    matthews: MatthewsHypothesis,
) -> dict[str, JsonValue]:
    sequence_mass = group.molecular_mass_da
    model_mass_fraction = (
        model.model_mass_da / sequence_mass if sequence_mass is not None else None
    )
    return {
        "funnel_adapter": _ADAPTER_VERSION,
        "funnel_scope": "exact_predicted_model_vertical_slice",
        "coordinate_provider": coordinate.provider,
        "coordinate_provider_accession": coordinate.provider_accession,
        "coordinate_source_release": coordinate.source_release,
        "coordinate_confidence_summary": coordinate.confidence_summary,
        "exact_sequence_mapping": True,
        "source_sequence_sha256": group.sha256,
        "model_variant_type": model.variant_type,
        "model_retained_fraction": model_path.retained_fraction,
        "model_mass_fraction_of_candidate": model_mass_fraction,
        "estimated_coordinate_error": model.estimated_coordinate_error,
        "matthews_hypothesis_id": matthews.hypothesis_id,
        "matthews_prior": matthews.matthews_prior,
        "matthews_rank_within_candidate": matthews.rank_within_candidate,
        "matthews_physical_status": matthews.physical_status.value,
        "sds_page_prior_label": matthews.sds_page_prior_label,
        "sds_page_fractional_difference": matthews.sds_page_fractional_difference,
    }


def _make_candidate(
    *,
    coordinate: CoordinateSourceRecord,
    model: ProcessedModelRecord,
    model_path: _ModelPath,
    group: SequenceGroupRecord,
    matthews: MatthewsHypothesis,
    preflight: MtzPreflightRecord,
    profile: PrototypeProfile,
) -> _Candidate:
    identity = {
        "crystal_id": preflight.crystal_id,
        "sequence_group_id": group.sequence_group_id,
        "model_id": model.model_id,
        "copy_count_expected": matthews.copy_count,
        "copy_number_to_search": 1,
        "space_group": preflight.space_group,
        "obs_labels": preflight.selected_observation_labels,
        "search_stage": MrSearchStage.FIRST_COPY.value,
        "resource_profile": profile.value,
    }
    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=content_id("mrhyp_", identity),
        crystal_id=preflight.crystal_id,
        sequence_group_id=group.sequence_group_id,
        model_id=model.model_id,
        copy_count_expected=matthews.copy_count,
        copy_number_to_search=1,
        fixed_solution_id=None,
        space_group=preflight.space_group,
        obs_labels=preflight.selected_observation_labels,
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=profile,
        priority_features=_priority_features(
            coordinate, model, model_path, group, matthews
        ),
        status=MrHypothesisStatus.QUEUED,
    )
    return _Candidate(hypothesis, model_path, coordinate, model, matthews)


def _write_tsv(path: Path, candidates: Sequence[_Candidate]) -> None:
    columns = (
        "hypothesis_id",
        "crystal_id",
        "sequence_group_id",
        "model_id",
        "coordinate_id",
        "coordinate_provider",
        "coordinate_provider_accession",
        "copy_count_expected",
        "matthews_hypothesis_id",
        "matthews_prior",
        "matthews_physical_status",
        "sds_page_prior_label",
        "model_retained_fraction",
        "model_path",
        "status",
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=columns, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    for candidate in candidates:
        writer.writerow(
            {
                "hypothesis_id": candidate.hypothesis.hypothesis_id,
                "crystal_id": candidate.hypothesis.crystal_id,
                "sequence_group_id": candidate.hypothesis.sequence_group_id,
                "model_id": candidate.model.model_id,
                "coordinate_id": candidate.coordinate.coordinate_id,
                "coordinate_provider": candidate.coordinate.provider,
                "coordinate_provider_accession": (
                    candidate.coordinate.provider_accession
                ),
                "copy_count_expected": candidate.matthews.copy_count,
                "matthews_hypothesis_id": candidate.matthews.hypothesis_id,
                "matthews_prior": candidate.matthews.matthews_prior,
                "matthews_physical_status": (candidate.matthews.physical_status.value),
                "sds_page_prior_label": candidate.matthews.sds_page_prior_label,
                "model_retained_fraction": candidate.model_path.retained_fraction,
                "model_path": candidate.model_path.relative_path,
                "status": candidate.hypothesis.status.value,
            }
        )
    atomic_write_text(path, stream.getvalue())


def _load_inputs(
    request: ExactPredictedFunnelRequest,
) -> tuple[
    PipelineConfig,
    tuple[CoordinateSourceRecord, ...],
    tuple[ProcessedModelRecord, ...],
    tuple[SequenceGroupRecord, ...],
    tuple[MatthewsHypothesis, ...],
    tuple[MtzPreflightRecord, ...],
]:
    config_model = load_contract(
        request.pipeline_config.resolve(strict=True),
        "pipeline-config",
        progress=request.progress,
    )
    if not isinstance(config_model, PipelineConfig):
        raise TypeError("pipeline-config registry returned an unexpected model")
    return (
        config_model,
        _read_jsonl(
            request.coordinate_sources_jsonl,
            CoordinateSourceRecord,
            label="coordinate sources",
            progress=request.progress,
        ),
        _read_jsonl(
            request.processed_models_jsonl,
            ProcessedModelRecord,
            label="processed models",
            progress=request.progress,
        ),
        _read_jsonl(
            request.sequence_groups_jsonl,
            SequenceGroupRecord,
            label="sequence groups",
            progress=request.progress,
        ),
        _read_jsonl(
            request.matthews_hypotheses_jsonl,
            MatthewsHypothesis,
            label="Matthews hypotheses",
            progress=request.progress,
        ),
        _read_jsonl(
            request.mtz_preflight_jsonl,
            MtzPreflightRecord,
            label="MTZ preflights",
            progress=request.progress,
        ),
    )


def _join_candidates(
    *,
    config: PipelineConfig,
    coordinates: Sequence[CoordinateSourceRecord],
    models: Sequence[ProcessedModelRecord],
    model_paths: dict[str, _ModelPath],
    groups: Sequence[SequenceGroupRecord],
    matthews_rows: Sequence[MatthewsHypothesis],
    preflights: Sequence[MtzPreflightRecord],
    crystal_ids: Sequence[str],
) -> list[_Candidate]:
    coordinate_index = _unique_index(
        coordinates, lambda item: item.coordinate_id, label="coordinate ID"
    )
    group_index = _unique_index(
        groups, lambda item: item.sequence_group_id, label="sequence-group ID"
    )
    preflight_index = _unique_index(
        preflights, lambda item: item.crystal_id, label="preflight crystal ID"
    )
    selected_crystals = set(crystal_ids) or set(preflight_index)
    unknown_crystals = selected_crystals - set(preflight_index)
    if unknown_crystals:
        raise FunnelInputError(
            "requested crystals lack MTZ preflight records: "
            + ", ".join(sorted(unknown_crystals))
        )
    per_model_copy_cap = _copy_cap(config)
    candidates: list[_Candidate] = []
    for model in models:
        coordinate = coordinate_index.get(model.coordinate_id)
        group = group_index.get(model.full_candidate_sequence_group_id)
        if coordinate is None or group is None:
            raise FunnelInputError(
                "processed model cannot be mapped to coordinate/group: "
                f"{model.model_id}"
            )
        if coordinate.source_sequence_sha256 != group.sha256:
            raise FunnelInputError(
                "coordinate does not map exactly to sequence group: "
                f"{model.coordinate_id}"
            )
        applicable = sorted(
            (
                row
                for row in matthews_rows
                if row.sequence_group_id == group.sequence_group_id
                and row.crystal_id in selected_crystals
                and row.retained
                and row.physical_status is not PhysicalStatus.IMPOSSIBLE
            ),
            key=lambda row: (
                row.crystal_id,
                row.rank_within_candidate,
                -row.matthews_prior,
                row.copy_count,
            ),
        )
        per_crystal_counts: dict[str, int] = {}
        for row in applicable:
            used = per_crystal_counts.get(row.crystal_id, 0)
            if used >= per_model_copy_cap:
                continue
            preflight = preflight_index[row.crystal_id]
            if preflight.decision is PreflightDecision.FAIL:
                continue
            if preflight.execution_status not in {
                ExecutionStatus.COMPLETED_SUCCESS,
                ExecutionStatus.COMPLETED_WARNING,
            }:
                continue
            if preflight.selected_observation_labels is None:
                raise FunnelInputError(
                    f"passing preflight lacks observation labels: {row.crystal_id}"
                )
            candidates.append(
                _make_candidate(
                    coordinate=coordinate,
                    model=model,
                    model_path=model_paths[model.model_id],
                    group=group,
                    matthews=row,
                    preflight=preflight,
                    profile=config.prototype.profile,
                )
            )
            per_crystal_counts[row.crystal_id] = used + 1
    candidates.sort(key=_candidate_sort_key)
    return candidates


def build_exact_predicted_funnel(
    request: ExactPredictedFunnelRequest,
) -> ExactPredictedFunnelOutput:
    """Join exact predicted models to physical copy priors and publish MR jobs."""

    config, coordinates, models, groups, matthews_rows, preflights = _load_inputs(
        request
    )
    model_paths = _manifest_model_paths(
        request.model_preparation_manifest, models, progress=request.progress
    )
    candidates = _join_candidates(
        config=config,
        coordinates=coordinates,
        models=models,
        model_paths=model_paths,
        groups=groups,
        matthews_rows=matthews_rows,
        preflights=preflights,
        crystal_ids=request.crystal_ids,
    )
    global_cap = min(
        config.search_limits.max_structural_hypotheses,
        config.search_limits.max_first_copy_jobs,
    )
    selected = tuple(candidates[:global_cap])
    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise FunnelInputError(f"funnel output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    hypotheses_jsonl = output / "mr_hypotheses.jsonl"
    atomic_write_text(
        hypotheses_jsonl,
        "".join(f"{canonical_json_text(item.hypothesis)}\n" for item in selected),
    )
    hypothesis_records = output / "hypotheses"
    hypothesis_records.mkdir()
    for item in selected:
        atomic_write_text(
            hypothesis_records / f"{item.hypothesis.hypothesis_id}.jsonl",
            f"{canonical_json_text(item.hypothesis)}\n",
        )
    hypotheses_tsv = output / "mr_hypotheses.tsv"
    _write_tsv(hypotheses_tsv, selected)
    input_paths = {
        "coordinate_sources_jsonl": request.coordinate_sources_jsonl,
        "processed_models_jsonl": request.processed_models_jsonl,
        "model_preparation_manifest": request.model_preparation_manifest,
        "sequence_groups_jsonl": request.sequence_groups_jsonl,
        "matthews_hypotheses_jsonl": request.matthews_hypotheses_jsonl,
        "mtz_preflight_jsonl": request.mtz_preflight_jsonl,
        "pipeline_config": request.pipeline_config,
    }
    input_digests = {
        name: sha256_file(path.resolve(strict=True))
        for name, path in input_paths.items()
    }
    per_model_copy_cap = _copy_cap(config)
    funnel_identity = {
        "adapter_version": _ADAPTER_VERSION,
        "input_sha256": input_digests,
        "hypothesis_ids": [item.hypothesis.hypothesis_id for item in selected],
        "global_cap": global_cap,
        "per_model_copy_cap": per_model_copy_cap,
    }
    manifest_json = output / "funnel_manifest.json"
    atomic_write_json(
        manifest_json,
        {
            "schema_version": "1.0",
            "funnel_id": content_id("funnel_", funnel_identity),
            "created_at": utc_now_iso(),
            "adapter_version": _ADAPTER_VERSION,
            "scope": "exact_predicted_model_vertical_slice",
            "resource_profile": config.prototype.profile.value,
            "input_sha256": input_digests,
            "candidate_count_before_global_cap": len(candidates),
            "selected_hypothesis_count": len(selected),
            "excluded_by_global_cap_count": len(candidates) - len(selected),
            "global_cap": global_cap,
            "per_model_copy_cap": per_model_copy_cap,
            "ordering_features": [
                "crystal_id",
                "matthews_physical_status",
                "matthews_prior",
                "matthews_rank_within_candidate",
                "model_retained_fraction",
                "coordinate_provider",
                "coordinate_provider_accession",
                "model_id",
            ],
            "hypotheses": [
                {
                    "hypothesis_id": item.hypothesis.hypothesis_id,
                    "model_id": item.model.model_id,
                    "model_path": item.model_path.relative_path,
                    "model_sha256": item.model.model_sha256,
                    "coordinate_id": item.coordinate.coordinate_id,
                    "matthews_hypothesis_id": item.matthews.hypothesis_id,
                }
                for item in selected
            ],
            "execution_status": ExecutionStatus.COMPLETED_SUCCESS.value,
        },
    )
    _LOGGER.info(
        "exact-predicted-model funnel complete",
        extra={
            "candidate_count_before_global_cap": len(candidates),
            "selected_hypothesis_count": len(selected),
            "global_cap": global_cap,
            "per_model_copy_cap": per_model_copy_cap,
            "manifest": str(manifest_json),
        },
    )
    return ExactPredictedFunnelOutput(
        hypotheses=tuple(item.hypothesis for item in selected),
        hypotheses_jsonl=hypotheses_jsonl,
        hypotheses_tsv=hypotheses_tsv,
        manifest_json=manifest_json,
    )


def _load_diverse_inputs(
    request: DiverseFirstCopyFunnelRequest,
) -> tuple[
    PipelineConfig,
    tuple[CoordinateSourceRecord, ...],
    tuple[tuple[ProcessedModelRecord, ...], ...],
    tuple[CoordinateHitMappingRecord, ...],
    tuple[SequenceGroupRecord, ...],
    tuple[MatthewsHypothesis, ...],
    tuple[MtzPreflightRecord, ...],
]:
    if not request.coordinate_sources_jsonl:
        raise FunnelInputError("at least one coordinate-source input is required")
    if not request.processed_models_jsonl:
        raise FunnelInputError("at least one processed-model input is required")
    if len(request.processed_models_jsonl) != len(request.model_preparation_manifests):
        raise FunnelInputError(
            "processed-model inputs and preparation manifests must be paired"
        )
    config = load_contract(
        request.pipeline_config.resolve(strict=True),
        "pipeline-config",
        progress=request.progress,
    )
    if not isinstance(config, PipelineConfig):
        raise TypeError("pipeline-config registry returned an unexpected model")
    coordinates = tuple(
        item
        for path in request.coordinate_sources_jsonl
        for item in _read_jsonl(
            path,
            CoordinateSourceRecord,
            label="coordinate sources",
            progress=request.progress,
            allow_empty=True,
        )
    )
    model_batches = tuple(
        _read_jsonl(
            path,
            ProcessedModelRecord,
            label="processed models",
            progress=request.progress,
            allow_empty=True,
        )
        for path in request.processed_models_jsonl
    )
    mappings = (
        _read_jsonl(
            request.coordinate_hit_mappings_jsonl,
            CoordinateHitMappingRecord,
            label="coordinate-hit mappings",
            progress=request.progress,
            allow_empty=True,
        )
        if request.coordinate_hit_mappings_jsonl is not None
        else ()
    )
    return (
        config,
        coordinates,
        model_batches,
        mappings,
        _read_jsonl(
            request.sequence_groups_jsonl,
            SequenceGroupRecord,
            label="sequence groups",
            progress=request.progress,
        ),
        _read_jsonl(
            request.matthews_hypotheses_jsonl,
            MatthewsHypothesis,
            label="Matthews hypotheses",
            progress=request.progress,
        ),
        _read_jsonl(
            request.mtz_preflight_jsonl,
            MtzPreflightRecord,
            label="MTZ preflights",
            progress=request.progress,
        ),
    )


def _diverse_model_paths(
    request: DiverseFirstCopyFunnelRequest,
    model_batches: Sequence[Sequence[ProcessedModelRecord]],
) -> dict[str, _ModelPath]:
    paths: dict[str, _ModelPath] = {}
    for manifest, models in zip(
        request.model_preparation_manifests, model_batches, strict=True
    ):
        batch_paths = _manifest_model_paths(manifest, models, progress=request.progress)
        duplicate = sorted(set(paths) & set(batch_paths))
        if duplicate:
            raise FunnelInputError(
                "model ID occurs in multiple preparation bundles: "
                + ", ".join(duplicate)
            )
        paths.update(batch_paths)
    return paths


def _diverse_priority_features(
    coordinate: CoordinateSourceRecord,
    model: ProcessedModelRecord,
    model_path: _ModelPath,
    group: SequenceGroupRecord,
    matthews: MatthewsHypothesis,
    mapping: CoordinateHitMappingRecord | None,
) -> dict[str, JsonValue]:
    features = _priority_features(coordinate, model, model_path, group, matthews)
    exact_mapping = (
        coordinate.source_sequence_sha256 == group.sha256
        if mapping is None
        else mapping.exact_sequence_match
    )
    features.update(
        {
            "funnel_adapter": _DIVERSE_ADAPTER_VERSION,
            "funnel_scope": "multi_source_first_copy",
            "structural_source_class": (
                "experimental" if coordinate.provider == "pdb" else "predicted"
            ),
            "exact_sequence_mapping": exact_mapping,
            "model_quality_flags": list(model.quality_flags),
        }
    )
    if mapping is not None:
        features.update(
            {
                "coordinate_mapping_id": mapping.mapping_id,
                "structural_hit_id": mapping.hit_id,
                "pdb_id": mapping.pdb_id,
                "pdb_entity_id": mapping.entity_id,
                "pdb_seqres_token": mapping.seqres_token,
                "candidate_query_coverage": mapping.query_coverage,
                "source_target_coverage": mapping.target_coverage,
                "candidate_source_sequence_identity": mapping.sequence_identity,
                "candidate_query_range": [mapping.query_start, mapping.query_end],
                "source_target_range": [mapping.target_start, mapping.target_end],
            }
        )
    return features


def _diverse_candidate_sort_key(candidate: _Candidate) -> tuple[object, ...]:
    """Reserve exact mappings before ordering the remaining evidence features."""

    exact_mapping = candidate.hypothesis.priority_features.get("exact_sequence_mapping")
    return (
        candidate.hypothesis.crystal_id,
        0 if exact_mapping is True else 1,
        *_candidate_sort_key(candidate)[1:],
    )


def _make_diverse_candidate(
    *,
    coordinate: CoordinateSourceRecord,
    model: ProcessedModelRecord,
    model_path: _ModelPath,
    group: SequenceGroupRecord,
    matthews: MatthewsHypothesis,
    preflight: MtzPreflightRecord,
    profile: PrototypeProfile,
    mapping: CoordinateHitMappingRecord | None,
    joint_copy_search: bool,
) -> _Candidate:
    copy_number_to_search = matthews.copy_count if joint_copy_search else 1
    identity = {
        "crystal_id": preflight.crystal_id,
        "sequence_group_id": group.sequence_group_id,
        "model_id": model.model_id,
        "copy_count_expected": matthews.copy_count,
        "copy_number_to_search": copy_number_to_search,
        "space_group": preflight.space_group,
        "obs_labels": preflight.selected_observation_labels,
        "search_stage": MrSearchStage.FIRST_COPY.value,
        "resource_profile": profile.value,
    }
    features = _diverse_priority_features(
        coordinate, model, model_path, group, matthews, mapping
    )
    if joint_copy_search:
        features.update(
            {
                "funnel_adapter": _PHASE3_DIVERSE_ADAPTER_VERSION,
                "copy_search_mode": "joint_declared_copies",
            }
        )
    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=content_id("mrhyp_", identity),
        crystal_id=preflight.crystal_id,
        sequence_group_id=group.sequence_group_id,
        model_id=model.model_id,
        copy_count_expected=matthews.copy_count,
        copy_number_to_search=copy_number_to_search,
        fixed_solution_id=None,
        space_group=preflight.space_group,
        obs_labels=preflight.selected_observation_labels,
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=profile,
        priority_features=features,
        status=MrHypothesisStatus.QUEUED,
    )
    return _Candidate(hypothesis, model_path, coordinate, model, matthews)


def _join_diverse_candidates(
    *,
    config: PipelineConfig,
    coordinates: Sequence[CoordinateSourceRecord],
    models: Sequence[ProcessedModelRecord],
    mappings: Sequence[CoordinateHitMappingRecord],
    model_paths: dict[str, _ModelPath],
    groups: Sequence[SequenceGroupRecord],
    matthews_rows: Sequence[MatthewsHypothesis],
    preflights: Sequence[MtzPreflightRecord],
    crystal_ids: Sequence[str],
    joint_copy_search: bool,
) -> list[_Candidate]:
    coordinate_index = _unique_index(
        coordinates, lambda item: item.coordinate_id, label="coordinate ID"
    )
    mapping_index = _unique_index(
        mappings, lambda item: item.mapping_id, label="coordinate mapping ID"
    )
    group_index = _unique_index(
        groups, lambda item: item.sequence_group_id, label="sequence-group ID"
    )
    preflight_index = _unique_index(
        preflights, lambda item: item.crystal_id, label="preflight crystal ID"
    )
    selected_crystals = set(crystal_ids) or set(preflight_index)
    unknown_crystals = selected_crystals - set(preflight_index)
    if unknown_crystals:
        raise FunnelInputError(
            "requested crystals lack MTZ preflight records: "
            + ", ".join(sorted(unknown_crystals))
        )
    per_model_copy_cap = (
        min(_PHASE3_MAXIMUM_COPY_COUNT, config.matthews.max_hypotheses_per_candidate)
        if joint_copy_search
        else _copy_cap(config)
    )
    candidates: list[_Candidate] = []
    for model in models:
        coordinate = coordinate_index.get(model.coordinate_id)
        group = group_index.get(model.full_candidate_sequence_group_id)
        if coordinate is None or group is None:
            raise FunnelInputError(
                "processed model cannot be mapped to coordinate/group: "
                f"{model.model_id}"
            )
        mapping: CoordinateHitMappingRecord | None = None
        if coordinate.provider == "pdb":
            mapping_id = model.processing_parameters.get("mapping_id")
            if not isinstance(mapping_id, str):
                raise FunnelInputError(
                    "experimental model lacks its coordinate mapping ID: "
                    f"{model.model_id}"
                )
            mapping = mapping_index.get(mapping_id)
            if (
                mapping is None
                or mapping.coordinate_id != coordinate.coordinate_id
                or mapping.sequence_group_id != group.sequence_group_id
                or mapping.source_sequence_sha256 != coordinate.source_sequence_sha256
                or mapping.candidate_sequence_sha256 != group.sha256
            ):
                raise FunnelInputError(
                    "experimental model mapping does not match its inputs: "
                    f"{model.model_id}"
                )
        elif coordinate.provider in {"afdb", "esm_atlas"}:
            if coordinate.source_sequence_sha256 != group.sha256:
                raise FunnelInputError(
                    "predicted coordinate does not map exactly to sequence group: "
                    f"{coordinate.coordinate_id}"
                )
        else:
            raise FunnelInputError(
                "unsupported coordinate provider in diverse funnel: "
                f"{coordinate.provider}"
            )
        applicable = sorted(
            (
                row
                for row in matthews_rows
                if row.sequence_group_id == group.sequence_group_id
                and row.crystal_id in selected_crystals
                and row.retained
                and row.physical_status is not PhysicalStatus.IMPOSSIBLE
                and (
                    not joint_copy_search
                    or row.copy_count <= _PHASE3_MAXIMUM_COPY_COUNT
                )
            ),
            key=lambda row: (
                row.crystal_id,
                row.rank_within_candidate,
                -row.matthews_prior,
                row.copy_count,
            ),
        )
        per_crystal_counts: dict[str, int] = {}
        for row in applicable:
            used = per_crystal_counts.get(row.crystal_id, 0)
            if used >= per_model_copy_cap:
                continue
            preflight = preflight_index[row.crystal_id]
            if preflight.decision is PreflightDecision.FAIL:
                continue
            if preflight.execution_status not in {
                ExecutionStatus.COMPLETED_SUCCESS,
                ExecutionStatus.COMPLETED_WARNING,
            }:
                continue
            if preflight.selected_observation_labels is None:
                raise FunnelInputError(
                    f"passing preflight lacks observation labels: {row.crystal_id}"
                )
            candidates.append(
                _make_diverse_candidate(
                    coordinate=coordinate,
                    model=model,
                    model_path=model_paths[model.model_id],
                    group=group,
                    matthews=row,
                    preflight=preflight,
                    profile=config.prototype.profile,
                    mapping=mapping,
                    joint_copy_search=joint_copy_search,
                )
            )
            per_crystal_counts[row.crystal_id] = used + 1
    candidates.sort(key=_diverse_candidate_sort_key)
    return candidates


def _select_diverse_candidates(
    candidates: Sequence[_Candidate],
    config: PipelineConfig,
    execution_cap: int | None,
    *,
    joint_copy_search: bool,
) -> tuple[tuple[_Candidate, ...], int]:
    if execution_cap is not None and not 1 <= execution_cap <= 1000:
        raise ValueError("maximum_first_copy_jobs must be between 1 and 1000")
    maximum_cap = _PHASE3_MAXIMUM_FIRST_COPY_JOBS if joint_copy_search else 1000
    requested_cap = (
        min(execution_cap, maximum_cap) if execution_cap is not None else maximum_cap
    )
    per_crystal_cap = min(
        _FIRST_COPY_PROFILE_CAPS[config.prototype.profile],
        config.search_limits.max_first_copy_jobs,
        requested_cap,
    )
    by_crystal: dict[str, list[_Candidate]] = {}
    for candidate in candidates:
        by_crystal.setdefault(candidate.hypothesis.crystal_id, []).append(candidate)
    selected: list[_Candidate] = []
    for crystal_id in sorted(by_crystal):
        buckets: dict[tuple[str, str, str], list[_Candidate]] = {}
        for candidate in by_crystal[crystal_id]:
            bucket = (
                candidate.hypothesis.sequence_group_id,
                candidate.coordinate.provider,
                candidate.model.variant_type,
            )
            buckets.setdefault(bucket, []).append(candidate)
        for values in buckets.values():
            values.sort(key=_diverse_candidate_sort_key)
        ordered_buckets = sorted(
            buckets, key=lambda key: _diverse_candidate_sort_key(buckets[key][0])
        )
        crystal_selected: list[_Candidate] = []
        round_index = 0
        while len(crystal_selected) < per_crystal_cap:
            added = False
            for bucket in ordered_buckets:
                values = buckets[bucket]
                if len(values) <= round_index:
                    continue
                crystal_selected.append(values[round_index])
                added = True
                if len(crystal_selected) >= per_crystal_cap:
                    break
            if not added:
                break
            round_index += 1
        selected.extend(crystal_selected)
    global_cap = min(
        config.search_limits.max_structural_hypotheses,
        config.search_limits.max_first_copy_jobs,
        requested_cap,
    )
    return tuple(selected[:global_cap]), per_crystal_cap


def _publish_all_eligible_models(
    output: Path,
    *,
    models: Sequence[ProcessedModelRecord],
    coordinates: Sequence[CoordinateSourceRecord],
    mappings: Sequence[CoordinateHitMappingRecord],
    model_paths: dict[str, _ModelPath],
    groups: Sequence[SequenceGroupRecord],
) -> tuple[AllEligibleModelRegistryOutput, dict[str, _ModelPath]]:
    """Publish every validated model independently of the A execution cap."""

    coordinate_index = _unique_index(
        coordinates, lambda item: item.coordinate_id, label="coordinate ID"
    )
    group_index = _unique_index(
        groups, lambda item: item.sequence_group_id, label="sequence-group ID"
    )
    mapping_index = _unique_index(
        mappings, lambda item: item.mapping_id, label="coordinate mapping ID"
    )
    registry_inputs: list[ValidatedProcessedModelInput] = []
    for model in models:
        coordinate = coordinate_index.get(model.coordinate_id)
        group = group_index.get(model.full_candidate_sequence_group_id)
        path = model_paths.get(model.model_id)
        if coordinate is None or group is None or path is None:
            raise FunnelInputError(
                f"processed model cannot enter all-model registry: {model.model_id}"
            )
        mapping_id = model.processing_parameters.get("mapping_id")
        mapping = mapping_index.get(mapping_id) if isinstance(mapping_id, str) else None
        registry_inputs.append(
            ValidatedProcessedModelInput(
                model=model,
                coordinate=coordinate,
                sequence_group=group,
                model_path=path.absolute_path,
                retained_fraction=path.retained_fraction,
                mapping=mapping,
            )
        )
    try:
        registry_output = build_all_eligible_model_registry(
            models=registry_inputs,
            sequence_groups=groups,
            output_directory=output / "model_registry",
        )
    except AllEligibleModelRegistryError as error:
        raise FunnelInputError(str(error)) from error
    aggregate_paths = {
        entry.model_id: _ModelPath(
            entry.model_path,
            registry_output.registry_directory / entry.model_path,
            entry.retained_fraction,
        )
        for inventory in registry_output.registry.sequence_groups
        for entry in inventory.models
    }
    return registry_output, aggregate_paths


def _diverse_input_digests(
    request: DiverseFirstCopyFunnelRequest,
) -> dict[str, str]:
    paths: list[tuple[str, Path]] = [
        *(
            (f"coordinate_sources_{index}", path)
            for index, path in enumerate(request.coordinate_sources_jsonl, start=1)
        ),
        *(
            (f"processed_models_{index}", path)
            for index, path in enumerate(request.processed_models_jsonl, start=1)
        ),
        *(
            (f"model_preparation_manifest_{index}", path)
            for index, path in enumerate(request.model_preparation_manifests, start=1)
        ),
        ("sequence_groups", request.sequence_groups_jsonl),
        ("matthews_hypotheses", request.matthews_hypotheses_jsonl),
        ("mtz_preflight", request.mtz_preflight_jsonl),
        ("pipeline_config", request.pipeline_config),
    ]
    if request.coordinate_hit_mappings_jsonl is not None:
        paths.append(("coordinate_hit_mappings", request.coordinate_hit_mappings_jsonl))
    return {
        name: sha256_file(path.resolve(strict=True), progress=False)
        for name, path in paths
    }


def build_diverse_first_copy_funnel(
    request: DiverseFirstCopyFunnelRequest,
) -> DiverseFirstCopyFunnelOutput:
    """Join predicted and experimental models under hard per-crystal job caps."""

    (
        config,
        coordinates,
        model_batches,
        mappings,
        groups,
        matthews_rows,
        preflights,
    ) = _load_diverse_inputs(request)
    model_paths = _diverse_model_paths(request, model_batches)
    models = tuple(item for batch in model_batches for item in batch)
    _unique_index(models, lambda item: item.model_id, label="model ID")
    candidates = _join_diverse_candidates(
        config=config,
        coordinates=coordinates,
        models=models,
        mappings=mappings,
        model_paths=model_paths,
        groups=groups,
        matthews_rows=matthews_rows,
        preflights=preflights,
        crystal_ids=request.crystal_ids,
        joint_copy_search=request.joint_copy_search,
    )
    selected, per_crystal_cap = _select_diverse_candidates(
        candidates,
        config,
        request.maximum_first_copy_jobs,
        joint_copy_search=request.joint_copy_search,
    )
    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise FunnelInputError(
            f"diverse-funnel output directory is not empty: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)
    input_sha256 = _diverse_input_digests(request)
    registry_output, aggregate_paths = _publish_all_eligible_models(
        output,
        models=models,
        coordinates=coordinates,
        mappings=mappings,
        model_paths=model_paths,
        groups=groups,
    )
    registry = registry_output.registry_directory
    hypotheses_jsonl = output / "mr_hypotheses.jsonl"
    atomic_write_text(
        hypotheses_jsonl,
        "".join(f"{canonical_json_text(item.hypothesis)}\n" for item in selected),
    )
    hypothesis_records = output / "hypotheses"
    hypothesis_records.mkdir()
    for item in selected:
        atomic_write_text(
            hypothesis_records / f"{item.hypothesis.hypothesis_id}.jsonl",
            f"{canonical_json_text(item.hypothesis)}\n",
        )
    hypotheses_tsv = output / "mr_hypotheses.tsv"
    _write_tsv(hypotheses_tsv, selected)
    per_crystal_counts: dict[str, int] = {}
    for item in selected:
        crystal_id = item.hypothesis.crystal_id
        per_crystal_counts[crystal_id] = per_crystal_counts.get(crystal_id, 0) + 1
    adapter_version = (
        _PHASE3_DIVERSE_ADAPTER_VERSION
        if request.joint_copy_search
        else _DIVERSE_ADAPTER_VERSION
    )
    phase3_copy_details = (
        {
            "copy_search_mode": "joint_declared_copies",
            "maximum_joint_copy_count": _PHASE3_MAXIMUM_COPY_COUNT,
        }
        if request.joint_copy_search
        else {}
    )
    manifest_identity = {
        "adapter_version": adapter_version,
        "input_sha256": input_sha256,
        "hypothesis_ids": [item.hypothesis.hypothesis_id for item in selected],
        "per_crystal_cap": per_crystal_cap,
        **phase3_copy_details,
    }
    manifest_path = output / "funnel_manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "funnel_id": content_id("funnel_", manifest_identity),
            "created_at": utc_now_iso(),
            "adapter_version": adapter_version,
            "scope": "multi_source_first_copy",
            "resource_profile": config.prototype.profile.value,
            "input_sha256": input_sha256,
            "candidate_count_before_caps": len(candidates),
            "selected_hypothesis_count": len(selected),
            "excluded_by_caps_count": len(candidates) - len(selected),
            "per_crystal_first_copy_cap": per_crystal_cap,
            "per_crystal_selected_counts": dict(sorted(per_crystal_counts.items())),
            "global_structural_cap": config.search_limits.max_structural_hypotheses,
            "global_first_copy_cap": config.search_limits.max_first_copy_jobs,
            "requested_execution_cap": request.maximum_first_copy_jobs,
            "per_model_copy_cap": (
                min(
                    _PHASE3_MAXIMUM_COPY_COUNT,
                    config.matthews.max_hypotheses_per_candidate,
                )
                if request.joint_copy_search
                else _copy_cap(config)
            ),
            **phase3_copy_details,
            "diversity_buckets": [
                "sequence_group_id",
                "coordinate_provider",
                "model_variant_type",
            ],
            "ordering_features": [
                "exact_sequence_mapping",
                "matthews_physical_status",
                "matthews_prior",
                "matthews_rank_within_candidate",
                "model_retained_fraction",
                "coordinate_provider",
                "coordinate_provider_accession",
                "model_id",
            ],
            "model_registry": {
                "path": registry.name,
                "scope": registry_output.registry.scope,
                "registry_id": registry_output.registry.registry_id,
                "registry_manifest_path": registry_output.registry_json.name,
                "registry_manifest_sha256": sha256_file(
                    registry_output.registry_json, progress=False
                ),
                "processed_models_sha256": (
                    registry_output.registry.processed_models_sha256
                ),
                "sequence_group_count": (registry_output.registry.sequence_group_count),
                "model_count": registry_output.registry.model_count,
                "unavailable_sequence_group_count": (
                    registry_output.registry.unavailable_sequence_group_count
                ),
            },
            "hypotheses": [
                {
                    "hypothesis_id": item.hypothesis.hypothesis_id,
                    "model_id": item.model.model_id,
                    "model_path": aggregate_paths[item.model.model_id].relative_path,
                    "model_sha256": item.model.model_sha256,
                    "coordinate_id": item.coordinate.coordinate_id,
                    "coordinate_provider": item.coordinate.provider,
                    "matthews_hypothesis_id": item.matthews.hypothesis_id,
                }
                for item in selected
            ],
            "execution_status": ExecutionStatus.COMPLETED_SUCCESS.value,
        },
    )
    _LOGGER.info(
        "multi-source first-copy funnel complete",
        extra={
            "candidate_count_before_caps": len(candidates),
            "selected_hypothesis_count": len(selected),
            "per_crystal_first_copy_cap": per_crystal_cap,
            "manifest": str(manifest_path),
        },
    )
    return DiverseFirstCopyFunnelOutput(
        hypotheses=tuple(item.hypothesis for item in selected),
        hypotheses_jsonl=hypotheses_jsonl,
        hypotheses_tsv=hypotheses_tsv,
        model_registry_directory=registry,
        manifest_json=manifest_path,
    )
