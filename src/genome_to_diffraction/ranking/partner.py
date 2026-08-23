"""Build the bounded first-wave catalogue B search plan.

The selector joins one retained A composition with supplied catalogue sequence
groups, existing per-candidate SDS/Matthews rows, and one aggregate MR model
registry. It schedules at most 25 B candidates, retains every unscheduled row
with a reason, and treats missing gel evidence as neutral. Only a physically
impossible combined composition or absence of usable mass/model evidence makes
a candidate unsearchable.

This module performs no Phaser work and infers no biological identity. Its
outputs are ``partner_candidates.jsonl``, a typed ``partner_search_plan.json``,
and a plain selected-ID fan-out boundary. The content identity includes all input file
checksums, explicit A/B copy counts, the fixed cap, and the ordered candidate
states. Focused tests cover SDS ordering, neutral missing evidence, the 25-item
cap, physical exclusion, missing models, checksum-bound model paths, and
deterministic output.
"""

import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ValidationError

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.matthews.enumerate import physical_status, prior_score
from genome_to_diffraction.ranking.funnel import FunnelInputError, _manifest_model_paths
from genome_to_diffraction.schemas.io import (
    ContractLoadError,
    load_contract,
    load_json_document,
)
from genome_to_diffraction.schemas.manifests import PipelineConfig
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MtzPreflightRecord,
    PartnerCandidateRanking,
    PartnerCandidateSelectionStatus,
    PartnerSearchPlan,
    PhysicalStatus,
    PreflightDecision,
    ProcessedModelRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_ADAPTER_VERSION = "catalogue-partner-plan-v1"
_SELECTION_CAP = 25
_CATALOGUE_INELIGIBLE_FLAGS = frozenset(
    {
        "excluded_ambiguous_or_nonstandard_residue",
        "excluded_below_minimum_length",
        "internal_stop",
        "mass_unavailable",
    }
)


class PartnerPlanInputError(InputContractError):
    """Catalogue partner-plan inputs cannot be joined safely."""


@dataclass(frozen=True)
class PartnerPlanRequest:
    """Inputs for one explicit retained-A catalogue B planning operation."""

    crystal_id: str
    parent_sequence_group_id: str
    parent_copy_count: int
    partner_copy_count: int
    sequence_groups_jsonl: Path
    matthews_hypotheses_jsonl: Path
    mtz_preflight_jsonl: Path
    pipeline_config: Path
    model_registry_directory: Path
    output_directory: Path
    parent_state_sha256: str | None = None
    progress: bool = True


@dataclass(frozen=True)
class ApprovedPartnerPlanRequest:
    """Inputs for deriving the plan's A composition from an approved stage."""

    approved_stage: Path
    crystal_id: str
    partner_copy_count: int
    sequence_groups_jsonl: Path
    matthews_hypotheses_jsonl: Path
    mtz_preflight_jsonl: Path
    pipeline_config: Path
    model_registry_directory: Path
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True)
class PartnerPlanOutput:
    """Typed plan, retained rows, and selected-ID fan-out boundary."""

    plan: PartnerSearchPlan
    plan_json: Path
    candidates_jsonl: Path
    selected_candidate_ids: Path


@dataclass(frozen=True)
class _ModelChoice:
    record: ProcessedModelRecord
    relative_path: str
    retained_fraction: float
    sequence_identity: float | None


@dataclass(frozen=True)
class _Candidate:
    group: SequenceGroupRecord
    matthews: MatthewsHypothesis | None
    model: _ModelChoice | None
    physical_status: PhysicalStatus | None
    solvent_lower: float | None
    solvent_upper: float | None
    combined_prior: float | None
    base_status: PartnerCandidateSelectionStatus | None


def _read_jsonl[T: BaseModel](
    path: Path, model: type[T], *, label: str
) -> tuple[T, ...]:
    resolved = path.resolve(strict=True)
    records: list[T] = []
    with resolved.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(model.model_validate_json(line))
            except ValidationError as error:
                raise PartnerPlanInputError(
                    f"invalid {label} record at line {line_number}: {resolved}"
                ) from error
    if not records:
        raise PartnerPlanInputError(f"{label} input is empty: {resolved}")
    return tuple(records)


def _unique_index[T](
    records: Sequence[T], key: Callable[[T], str], *, label: str
) -> dict[str, T]:
    index: dict[str, T] = {}
    for record in records:
        identifier = key(record)
        if identifier in index:
            raise PartnerPlanInputError(f"duplicate {label}: {identifier}")
        index[identifier] = record
    return index


def _model_identity(model: ProcessedModelRecord) -> float | None:
    value = model.processing_parameters.get("sequence_identity")
    if isinstance(value, int | float) and not isinstance(value, bool):
        identity = float(value)
        if 0 <= identity <= 1 and math.isfinite(identity):
            return identity
    if model.variant_type == "predicted_confidence_pruned_full":
        return 1.0
    return None


def _load_model_registry(directory: Path) -> dict[str, tuple[_ModelChoice, ...]]:
    root = directory.resolve(strict=True)
    if not root.is_dir():
        raise PartnerPlanInputError(f"model registry is not a directory: {root}")
    models = _read_jsonl(
        root / "processed_models.jsonl",
        ProcessedModelRecord,
        label="processed models",
    )
    try:
        paths = _manifest_model_paths(
            root / "model_preparation_manifest.json",
            models,
            progress=False,
        )
    except FunnelInputError as error:
        raise PartnerPlanInputError(str(error)) from error
    by_group: dict[str, list[_ModelChoice]] = defaultdict(list)
    for model in models:
        path = paths[model.model_id]
        by_group[model.full_candidate_sequence_group_id].append(
            _ModelChoice(
                record=model,
                relative_path=path.relative_path,
                retained_fraction=path.retained_fraction,
                sequence_identity=_model_identity(model),
            )
        )
    for choices in by_group.values():
        choices.sort(key=_model_sort_key)
    return {group: tuple(choices) for group, choices in by_group.items()}


def _model_sort_key(model: _ModelChoice) -> tuple[object, ...]:
    error = model.record.estimated_coordinate_error
    identity = model.sequence_identity
    return (
        identity is None,
        -(identity or 0.0),
        -model.retained_fraction,
        error is None,
        error if error is not None else math.inf,
        model.record.variant_type,
        model.record.model_id,
    )


def _mass_bounds(group: SequenceGroupRecord) -> tuple[float, float] | None:
    if group.molecular_mass_da is not None:
        return group.molecular_mass_da, group.molecular_mass_da
    if (
        group.molecular_mass_lower_da is not None
        and group.molecular_mass_upper_da is not None
    ):
        return group.molecular_mass_lower_da, group.molecular_mass_upper_da
    return None


def _combined_metrics(
    parent: SequenceGroupRecord,
    partner: SequenceGroupRecord,
    *,
    parent_copy_count: int,
    partner_copy_count: int,
    asu_volume_a3: float,
    minimum_solvent: float,
    maximum_solvent: float,
) -> tuple[PhysicalStatus, float, float, float] | None:
    parent_mass = _mass_bounds(parent)
    partner_mass = _mass_bounds(partner)
    if parent_mass is None or partner_mass is None:
        return None
    total_lower = (
        parent_mass[0] * parent_copy_count + partner_mass[0] * partner_copy_count
    )
    total_upper = (
        parent_mass[1] * parent_copy_count + partner_mass[1] * partner_copy_count
    )
    solvent_lower = 1.0 - 1.23 * total_upper / asu_volume_a3
    solvent_upper = 1.0 - 1.23 * total_lower / asu_volume_a3
    status = physical_status(
        solvent_lower,
        solvent_upper,
        minimum=minimum_solvent,
        maximum=maximum_solvent,
    )
    prior = prior_score(
        (solvent_lower + solvent_upper) / 2,
        minimum=minimum_solvent,
        maximum=maximum_solvent,
    )
    return status, solvent_lower, solvent_upper, prior


def _candidate_sort_key(candidate: _Candidate) -> tuple[object, ...]:
    sds_rank = {"strong": 0, "compatible": 1, "unavailable": 2, "weak": 3}
    physical_rank = {
        PhysicalStatus.PLAUSIBLE: 0,
        PhysicalStatus.REVIEW: 1,
        None: 2,
        PhysicalStatus.IMPOSSIBLE: 3,
    }
    model = candidate.model
    model_key = (
        _model_sort_key(model)
        if model is not None
        else (True, 0, 0, True, math.inf, "", "")
    )
    return (
        candidate.base_status is not None,
        sds_rank[
            candidate.matthews.sds_page_prior_label
            if candidate.matthews is not None
            else "unavailable"
        ],
        physical_rank[candidate.physical_status],
        -(candidate.combined_prior or 0.0),
        *model_key,
        candidate.group.sequence_group_id,
    )


def _load_inputs(
    request: PartnerPlanRequest,
) -> tuple[
    SequenceGroupRecord,
    tuple[_Candidate, ...],
    dict[str, str],
]:
    if (
        isinstance(request.parent_copy_count, bool)
        or isinstance(request.partner_copy_count, bool)
        or request.parent_copy_count < 1
        or request.partner_copy_count < 1
    ):
        raise ValueError("component copy counts must be positive")
    config = load_contract(
        request.pipeline_config,
        "pipeline-config",
        progress=request.progress,
    )
    if not isinstance(config, PipelineConfig):
        raise PartnerPlanInputError("pipeline config resolved to the wrong contract")
    groups = _read_jsonl(
        request.sequence_groups_jsonl,
        SequenceGroupRecord,
        label="sequence groups",
    )
    group_index = _unique_index(
        groups, lambda item: item.sequence_group_id, label="sequence group ID"
    )
    parent = group_index.get(request.parent_sequence_group_id)
    if parent is None:
        raise PartnerPlanInputError("parent sequence group is absent from catalogue")
    preflights = _read_jsonl(
        request.mtz_preflight_jsonl,
        MtzPreflightRecord,
        label="MTZ preflights",
    )
    matching_preflights = [
        item for item in preflights if item.crystal_id == request.crystal_id
    ]
    if len(matching_preflights) != 1:
        raise PartnerPlanInputError("partner crystal preflight is not unique")
    preflight = matching_preflights[0]
    if (
        preflight.decision is PreflightDecision.FAIL
        or preflight.execution_status
        not in {ExecutionStatus.COMPLETED_SUCCESS, ExecutionStatus.COMPLETED_WARNING}
    ):
        raise PartnerPlanInputError("cannot plan partners from a failed MTZ preflight")
    rows = _read_jsonl(
        request.matthews_hypotheses_jsonl,
        MatthewsHypothesis,
        label="Matthews hypotheses",
    )
    row_index: dict[str, MatthewsHypothesis] = {}
    for row in rows:
        if (
            row.crystal_id != request.crystal_id
            or row.copy_count != request.partner_copy_count
        ):
            continue
        if row.sequence_group_id in row_index:
            raise PartnerPlanInputError(
                f"duplicate partner Matthews row: {row.sequence_group_id}"
            )
        row_index[row.sequence_group_id] = row
    models = _load_model_registry(request.model_registry_directory)
    unknown_model_groups = set(models) - set(group_index)
    if unknown_model_groups:
        raise PartnerPlanInputError(
            "model registry contains sequence groups outside the catalogue: "
            + ",".join(sorted(unknown_model_groups))
        )
    candidates: list[_Candidate] = []
    for group in groups:
        if group.sequence_group_id == parent.sequence_group_id:
            continue
        matthews = row_index.get(group.sequence_group_id)
        if matthews is None:
            if not _CATALOGUE_INELIGIBLE_FLAGS.intersection(group.quality_flags):
                raise PartnerPlanInputError(
                    f"partner Matthews coverage missing: {group.sequence_group_id}"
                )
            candidates.append(
                _Candidate(
                    group=group,
                    matthews=None,
                    model=None,
                    physical_status=None,
                    solvent_lower=None,
                    solvent_upper=None,
                    combined_prior=None,
                    base_status=(
                        PartnerCandidateSelectionStatus.UNSEARCHABLE_CATALOGUE_INELIGIBLE
                    ),
                )
            )
            continue
        combined = _combined_metrics(
            parent,
            group,
            parent_copy_count=request.parent_copy_count,
            partner_copy_count=request.partner_copy_count,
            asu_volume_a3=preflight.asu_volume_a3,
            minimum_solvent=config.matthews.min_solvent_fraction,
            maximum_solvent=config.matthews.max_solvent_fraction,
        )
        choices = models.get(group.sequence_group_id, ())
        choice = choices[0] if choices else None
        if combined is None:
            status = PartnerCandidateSelectionStatus.UNSEARCHABLE_MASS
            physical = solvent_lower = solvent_upper = prior = None
        else:
            physical, solvent_lower, solvent_upper, prior = combined
            if physical is PhysicalStatus.IMPOSSIBLE:
                status = PartnerCandidateSelectionStatus.EXCLUDED_PHYSICAL_IMPOSSIBLE
            elif choice is None:
                status = PartnerCandidateSelectionStatus.UNSEARCHABLE_NO_MODEL
            elif choice.sequence_identity is None or choice.sequence_identity <= 0:
                status = PartnerCandidateSelectionStatus.UNSEARCHABLE_MODEL_IDENTITY
            else:
                status = None
        candidates.append(
            _Candidate(
                group=group,
                matthews=matthews,
                model=choice,
                physical_status=physical,
                solvent_lower=solvent_lower,
                solvent_upper=solvent_upper,
                combined_prior=prior,
                base_status=status,
            )
        )
    candidates.sort(key=_candidate_sort_key)
    input_sha256 = {
        "sequence_groups": sha256_file(
            request.sequence_groups_jsonl.resolve(strict=True)
        ),
        "matthews_hypotheses": sha256_file(
            request.matthews_hypotheses_jsonl.resolve(strict=True)
        ),
        "mtz_preflight": sha256_file(request.mtz_preflight_jsonl.resolve(strict=True)),
        "pipeline_config": sha256_file(request.pipeline_config.resolve(strict=True)),
        "processed_models": sha256_file(
            (request.model_registry_directory / "processed_models.jsonl").resolve(
                strict=True
            )
        ),
        "model_registry_manifest": sha256_file(
            (
                request.model_registry_directory / "model_preparation_manifest.json"
            ).resolve(strict=True)
        ),
    }
    return parent, tuple(candidates), input_sha256


def build_partner_search_plan(request: PartnerPlanRequest) -> PartnerPlanOutput:
    """Build one deterministic 25-attempt catalogue B first wave."""

    output = request.output_directory.absolute()
    if output.exists() and any(output.iterdir()):
        raise PartnerPlanInputError(f"partner-plan output is not empty: {output}")
    parent, candidates, input_sha256 = _load_inputs(request)
    searchable_seen = 0
    rows: list[PartnerCandidateRanking] = []
    for rank, candidate in enumerate(candidates, start=1):
        model = candidate.model
        if candidate.base_status is None:
            searchable_seen += 1
            selection_status = (
                PartnerCandidateSelectionStatus.SELECTED
                if searchable_seen <= _SELECTION_CAP
                else PartnerCandidateSelectionStatus.DEFERRED_CAP
            )
        else:
            selection_status = candidate.base_status
        identity = {
            "adapter_version": _ADAPTER_VERSION,
            "crystal_id": request.crystal_id,
            "parent_sequence_group_id": parent.sequence_group_id,
            "parent_copy_count": request.parent_copy_count,
            "partner_sequence_group_id": candidate.group.sequence_group_id,
            "partner_copy_count": request.partner_copy_count,
            "parent_state_sha256": request.parent_state_sha256,
            "model_id": model.record.model_id if model is not None else None,
        }
        rows.append(
            # Matthews-absent rows are retained only for explicit catalogue
            # ineligibility and therefore carry neutral SDS evidence.
            PartnerCandidateRanking(
                schema_version="1.0",
                candidate_id=content_id("partnercand_", identity),
                rank=rank,
                sequence_group_id=candidate.group.sequence_group_id,
                selection_status=selection_status,
                model_id=model.record.model_id if model is not None else None,
                model_path=model.relative_path if model is not None else None,
                model_sha256=model.record.model_sha256 if model is not None else None,
                structural_class=(
                    model.record.variant_type if model is not None else None
                ),
                model_retained_fraction=(
                    model.retained_fraction if model is not None else None
                ),
                model_sequence_identity=(
                    model.sequence_identity if model is not None else None
                ),
                estimated_coordinate_error=(
                    model.record.estimated_coordinate_error
                    if model is not None
                    else None
                ),
                sds_page_prior_label=(
                    candidate.matthews.sds_page_prior_label
                    if candidate.matthews is not None
                    else "unavailable"
                ),
                sds_page_fractional_difference=(
                    candidate.matthews.sds_page_fractional_difference
                    if candidate.matthews is not None
                    else None
                ),
                combined_physical_status=candidate.physical_status,
                combined_solvent_fraction_lower=candidate.solvent_lower,
                combined_solvent_fraction_upper=candidate.solvent_upper,
                combined_matthews_prior=candidate.combined_prior,
                ordering_reasons=(
                    "sds_page:"
                    + (
                        candidate.matthews.sds_page_prior_label
                        if candidate.matthews is not None
                        else "unavailable"
                    ),
                    "native_page:unavailable_neutral",
                    "combined_matthews:"
                    + (
                        candidate.physical_status.value
                        if candidate.physical_status is not None
                        else "unavailable"
                    ),
                    "model:"
                    + (
                        model.record.variant_type
                        if model is not None
                        else "unavailable"
                    ),
                    f"selection:{selection_status.value}",
                ),
            )
        )
    selected = sum(
        item.selection_status is PartnerCandidateSelectionStatus.SELECTED
        for item in rows
    )
    deferred = sum(
        item.selection_status is PartnerCandidateSelectionStatus.DEFERRED_CAP
        for item in rows
    )
    searchable = selected + deferred
    plan_identity = {
        "adapter_version": _ADAPTER_VERSION,
        "crystal_id": request.crystal_id,
        "parent_sequence_group_id": parent.sequence_group_id,
        "parent_copy_count": request.parent_copy_count,
        "partner_copy_count": request.partner_copy_count,
        "selection_cap": _SELECTION_CAP,
        "input_sha256": input_sha256,
        "candidate_states": [
            [item.candidate_id, item.selection_status.value] for item in rows
        ],
    }
    plan = PartnerSearchPlan(
        schema_version="1.0",
        plan_id=content_id("partnerplan_", plan_identity),
        adapter_version=_ADAPTER_VERSION,
        crystal_id=request.crystal_id,
        parent_sequence_group_id=parent.sequence_group_id,
        parent_state_sha256=request.parent_state_sha256,
        parent_copy_count=request.parent_copy_count,
        partner_copy_count=request.partner_copy_count,
        candidate_count=len(rows),
        searchable_candidate_count=searchable,
        selected_attempt_count=selected,
        deferred_cap_count=deferred,
        unsearchable_candidate_count=len(rows) - searchable,
        candidates=tuple(rows),
    )
    output.mkdir(parents=True, exist_ok=True)
    plan_json = output / "partner_search_plan.json"
    candidates_jsonl = output / "partner_candidates.jsonl"
    selected_candidate_ids = output / "selected_partner_candidate_ids.txt"
    atomic_write_json(plan_json, plan.model_dump(mode="json"))
    atomic_write_text(
        candidates_jsonl,
        "".join(f"{canonical_json_text(item)}\n" for item in plan.candidates),
    )
    atomic_write_text(
        selected_candidate_ids,
        "".join(
            f"{item.candidate_id}\n"
            for item in plan.candidates
            if item.selection_status is PartnerCandidateSelectionStatus.SELECTED
        ),
    )
    return PartnerPlanOutput(plan, plan_json, candidates_jsonl, selected_candidate_ids)


def build_approved_partner_search_plan(
    request: ApprovedPartnerPlanRequest,
) -> PartnerPlanOutput:
    """Derive one complete approved A composition and build its B plan."""

    stage = request.approved_stage.resolve(strict=True)
    manifest_path = stage / "live_m4_stage_manifest.json"
    try:
        document = load_json_document(manifest_path)
    except ContractLoadError as error:
        raise PartnerPlanInputError(f"cannot load approved A stage: {error}") from error
    if not isinstance(document, dict):
        raise PartnerPlanInputError("approved A stage manifest must be an object")
    approved = document.get("approved_solution_ids")
    sources = document.get("model_sources")
    if (
        document.get("execution_status") != ExecutionStatus.COMPLETED_SUCCESS.value
        or document.get("approved_seed_count") != 1
        or not isinstance(approved, list)
        or len(approved) != 1
        or not isinstance(approved[0], str)
        or not isinstance(sources, dict)
        or not isinstance(sources.get(approved[0]), dict)
    ):
        raise PartnerPlanInputError("approved A stage is not one complete seed")
    source = cast(dict[str, object], sources[approved[0]])
    sequence_group_id = source.get("sequence_group_id")
    copy_count = source.get("expected_copy_count")
    if (
        not isinstance(sequence_group_id, str)
        or isinstance(copy_count, bool)
        or not isinstance(copy_count, int)
        or copy_count < 1
        or source.get("requires_additional_copy") is not False
    ):
        raise PartnerPlanInputError("approved A composition is incomplete")
    return build_partner_search_plan(
        PartnerPlanRequest(
            crystal_id=request.crystal_id,
            parent_sequence_group_id=sequence_group_id,
            parent_copy_count=copy_count,
            partner_copy_count=request.partner_copy_count,
            sequence_groups_jsonl=request.sequence_groups_jsonl,
            matthews_hypotheses_jsonl=request.matthews_hypotheses_jsonl,
            mtz_preflight_jsonl=request.mtz_preflight_jsonl,
            pipeline_config=request.pipeline_config,
            model_registry_directory=request.model_registry_directory,
            output_directory=request.output_directory,
            parent_state_sha256=sha256_file(manifest_path),
            progress=request.progress,
        )
    )
