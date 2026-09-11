"""Read-only RF-G4 admission comparison over actual production-validated inputs.

This fixture accepts one case's fixed M6 pilot funnel request after external
model/leakage policy. Production loaders verify model bytes, joins and complete
Matthews factors. Both arms construct hypotheses with the unchanged production
join; the solvent-only reference changes only retention and admission ordering.
The copy-weighted baseline uses the production selector. No tasks, output
bundles, truth evaluation, reviewer decisions or native acceptance are created.
Native source/input authority remains the qualification harness's responsibility.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from tests.fixtures.ranking_four_arm_reference import (
    AdmissionPrior,
    ReferencePriorRow,
    reference_prior_inventory,
)

from genome_to_diffraction.ranking.funnel import (
    DiverseFirstCopyFunnelRequest,
    _Candidate,
    _complete_matthews_rows,
    _copy_cap,
    _diverse_candidate_sort_key,
    _diverse_input_digests,
    _diverse_model_paths,
    _join_diverse_candidates,
    _load_diverse_inputs,
    _select_diverse_candidates,
    _unique_index,
)
from genome_to_diffraction.schemas.manifests import PrototypeProfile
from genome_to_diffraction.schemas.results import MatthewsHypothesis, MrHypothesis


@dataclass(frozen=True)
class ReferenceAdmissionRow:
    """Original executable hypothesis plus separately labelled comparison data."""

    hypothesis: MrHypothesis
    matthews: ReferencePriorRow
    diversity_bucket: tuple[str, str, str]
    order_key: tuple[object, ...]
    within_model_cap: bool


@dataclass(frozen=True)
class ReferenceAdmissionPlan:
    """Complete model-backed physical inventory and explicit cap dispositions."""

    admission_prior: AdmissionPrior
    input_sha256: dict[str, str]
    configured_matthews_retention: int
    per_model_copy_cap: int
    task_cap: int
    inventory: tuple[ReferenceAdmissionRow, ...]
    selected: tuple[ReferenceAdmissionRow, ...]
    deferred_copy: tuple[ReferenceAdmissionRow, ...]
    deferred_task: tuple[ReferenceAdmissionRow, ...]


def _solvent_selection(
    rows: Sequence[ReferenceAdmissionRow],
) -> tuple[ReferenceAdmissionRow, ...]:
    """Frozen reference of the existing bucket rounds, using solvent-only keys."""

    buckets: dict[tuple[str, str, str], list[ReferenceAdmissionRow]] = {}
    for row in sorted(rows, key=lambda item: item.order_key):
        buckets.setdefault(row.diversity_bucket, []).append(row)
    ordered = sorted(buckets.values(), key=lambda items: items[0].order_key)
    selected: list[ReferenceAdmissionRow] = []
    for index in range(max((len(items) for items in ordered), default=0)):
        for items in ordered:
            if index < len(items):
                selected.append(items[index])
                if len(selected) == 25:
                    return tuple(selected)
    return tuple(selected)


def reference_admission_plan(
    request: DiverseFirstCopyFunnelRequest, *, admission_prior: AdmissionPrior
) -> ReferenceAdmissionPlan:
    """Plan one fixed-budget reference cohort without rewriting raw production rows."""

    if (
        len(request.crystal_ids) != 1
        or request.maximum_first_copy_jobs != 25
        or request.localisation_bundle is not None
        or request.require_localisation_policy
        or request.review_selection is not None
    ):
        raise ValueError("comparison requires the single-case fixed M6 funnel request")
    before = _diverse_input_digests(request)
    config, coordinates, batches, mappings, groups, matthews, preflights = (
        _load_diverse_inputs(request)
    )
    if (
        config.prototype.profile is not PrototypeProfile.PILOT
        or config.matthews.max_hypotheses_per_candidate != 4
        or config.search_limits.max_first_copy_jobs != 25
        or config.search_limits.max_structural_hypotheses != 100
    ):
        raise ValueError("comparison differs from the fixed M6 admission budgets")
    preflight_index = _unique_index(
        preflights, lambda row: row.crystal_id, label="comparison preflight"
    )
    if tuple(preflight_index) != request.crystal_ids:
        raise ValueError("comparison must contain exactly its declared crystal")
    _unique_index(groups, lambda row: row.sequence_group_id, label="comparison group")
    by_group: dict[tuple[str, str], list[MatthewsHypothesis]] = {}
    for row in matthews:
        by_group.setdefault((row.crystal_id, row.sequence_group_id), []).append(row)
    expected_groups = {
        (request.crystal_ids[0], row.sequence_group_id) for row in groups
    }
    if set(by_group) != expected_groups:
        raise ValueError("comparison Matthews inventory differs from eligible groups")
    for group in groups:
        _complete_matthews_rows(
            group=group,
            rows_by_key=by_group,
            preflight_index=preflight_index,
            selected_crystals=set(request.crystal_ids),
            config=config,
        )
    priors = {
        row.original.hypothesis_id: row
        for row in reference_prior_inventory(
            matthews,
            admission_prior=admission_prior,
            maximum_hypotheses_per_candidate=4,
        )
    }
    models = tuple(row for batch in batches for row in batch)
    _unique_index(models, lambda row: row.model_id, label="comparison model")
    if any(
        (request.crystal_ids[0], model.full_candidate_sequence_group_id) not in by_group
        for model in models
    ):
        raise ValueError("comparison model has no eligible sequence group")
    paths = _diverse_model_paths(request, batches)
    # This internal join constructs all physical alternatives with the actual
    # production input checks. It creates no review decision or execution authority.
    candidates = _join_diverse_candidates(
        config=config,
        coordinates=coordinates,
        models=models,
        mappings=mappings,
        model_paths=paths,
        groups=groups,
        matthews_rows=matthews,
        preflights=preflights,
        crystal_ids=request.crystal_ids,
        build_resource_plans=False,
        localisation_by_group=None,
        selected_targets=frozenset(
            (model.model_id, row.hypothesis_id)
            for model in models
            for row in by_group[
                (request.crystal_ids[0], model.full_candidate_sequence_group_id)
            ]
        ),
    )
    model_cap = _copy_cap(config)
    inventory: list[ReferenceAdmissionRow] = []
    for candidate in candidates:
        prior = priors[candidate.matthews.hypothesis_id]
        production_key = _diverse_candidate_sort_key(candidate)
        key = (
            *production_key[:4],
            -prior.prior,
            prior.rank,
            *production_key[6:],
        )
        inventory.append(
            ReferenceAdmissionRow(
                hypothesis=candidate.hypothesis,
                matthews=prior,
                diversity_bucket=(
                    candidate.hypothesis.sequence_group_id,
                    candidate.coordinate.provider,
                    candidate.model.variant_type,
                ),
                order_key=key,
                within_model_cap=prior.retained and prior.rank <= model_cap,
            )
        )
    inventory.sort(key=lambda row: row.order_key)
    eligible = tuple(row for row in inventory if row.within_model_cap)
    if admission_prior == "copy_weighted":
        candidate_by_id: dict[str, _Candidate] = {
            row.hypothesis.hypothesis_id: row for row in candidates
        }
        selected_candidates, _ = _select_diverse_candidates(
            tuple(candidate_by_id[row.hypothesis.hypothesis_id] for row in eligible),
            config,
            25,
            phase3_screen=False,
        )
        by_id = {row.hypothesis.hypothesis_id: row for row in eligible}
        selected = tuple(
            by_id[row.hypothesis.hypothesis_id] for row in selected_candidates
        )
    else:
        selected = _solvent_selection(eligible)
    selected_ids = {row.hypothesis.hypothesis_id for row in selected}
    if _diverse_input_digests(request) != before:
        raise ValueError("comparison inputs changed while planning")
    return ReferenceAdmissionPlan(
        admission_prior=admission_prior,
        input_sha256=before,
        configured_matthews_retention=4,
        per_model_copy_cap=model_cap,
        task_cap=25,
        inventory=tuple(inventory),
        selected=selected,
        deferred_copy=tuple(row for row in inventory if not row.within_model_cap),
        deferred_task=tuple(
            row for row in eligible if row.hypothesis.hypothesis_id not in selected_ids
        ),
    )
