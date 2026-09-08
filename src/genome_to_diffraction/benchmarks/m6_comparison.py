"""Bounded file planning for the frozen M6 admission/review comparison.

Inputs are twelve current, truth-blind M6 case bundles and the checksum-frozen
recipe, protocol, software lock and Phenix manifest. Preparation reuses the
complete acquired-model inventory and production diversity admission. Outputs
are two native cohorts per case, then four checksum-bound seed bundles and a
separate exact continuation workload. Nextflow owns all native execution.

Missing, changed, duplicate or cross-arm evidence fails. Native first-copy
failures hold advancement; completed no-hits remain explicit empty outcomes.
No targets or truth-side annotations are read before result checksums freeze.
Case/model/content digests and the recipe identify every planned task; tests
cover shared evidence, admission parity, frozen bounds and stale plans.
"""

import csv
import io
import shutil
from pathlib import Path
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from genome_to_diffraction.benchmarks.m6_advancement import (
    M6_FROZEN_PROTOCOL_SHA256,
    validate_m6_advancement_authority,
)
from genome_to_diffraction.benchmarks.m6_comparison_policy import (
    M6_COMPARISON_ARMS,
    M6_COMPARISON_CASES,
    M6_COMPARISON_ID,
    M6_COMPARISON_SHA256,
    M6AdmissionPrior,
    M6ComparisonArm,
    M6ComparisonArmContext,
    M6ComparisonCohort,
    comparison_case_digest,
    load_comparison_cohort,
    validate_comparison_recipe,
)
from genome_to_diffraction.benchmarks.m6_nextflow import (
    M6CaseTask,
    M6HypothesisGroupTask,
    M6SeedTask,
    run_m6_empty_seeds_task,
    run_m6_select_seeds_task,
)
from genome_to_diffraction.benchmarks.m6_scientific import m6_track_case_ids
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.model_registry.all_eligible import (
    AllEligibleModelEntry,
    load_all_eligible_model_registry,
)
from genome_to_diffraction.ranking.funnel import select_diverse_hypothesis_inventory
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.io import load_contract, load_json_document
from genome_to_diffraction.schemas.manifests import PipelineConfig
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    NormalisedMrResult,
)
from genome_to_diffraction.status import ExecutionStatus


class M6ComparisonCohortEntry(ContractModel):
    """A portable cohort path derived only from its fixed case and prior."""

    cohort: M6ComparisonCohort
    case_path: str

    @model_validator(mode="after")
    def _validate_path(self) -> Self:
        if (
            self.case_path
            != f"cohorts/{self.cohort.case_id}/{self.cohort.admission_prior}"
        ):
            raise ValueError("M6 cohort path differs from its fixed scope")
        return self


class M6ComparisonPlan(ContractModel):
    """Exactly two native cohorts per case under one pinned execution environment."""

    schema_version: Literal["1.0"]
    comparison_id: Literal["m6_ranking_four_arm_v1"]
    comparison_spec_sha256: Sha256Hex
    protocol_sha256: Sha256Hex
    software_lock_sha256: Sha256Hex
    phenix_manifest_sha256: Sha256Hex
    source_commit: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    plan_id: str
    cohorts: tuple[M6ComparisonCohortEntry, ...] = Field(min_length=24, max_length=24)
    initial_hypothesis_count: Annotated[int, Field(ge=0, le=600)]
    continuation_is_frozen: Literal[False]
    truth_join_permitted: Literal[False]

    @model_validator(mode="after")
    def _validate_frozen_plan(self) -> Self:
        if (
            self.comparison_spec_sha256 != M6_COMPARISON_SHA256
            or self.protocol_sha256 != M6_FROZEN_PROTOCOL_SHA256
        ):
            raise ValueError("M6 comparison changes its frozen recipe or protocol")
        expected = {
            (case_id, prior)
            for case_id in M6_COMPARISON_CASES
            for prior in ("solvent_density", "copy_weighted")
        }
        if {
            (entry.cohort.case_id, entry.cohort.admission_prior)
            for entry in self.cohorts
        } != expected:
            raise ValueError("M6 comparison cohort partition differs")
        if self.initial_hypothesis_count != sum(
            len(entry.cohort.scheduled_hypothesis_ids) for entry in self.cohorts
        ):
            raise ValueError("M6 comparison initial task accounting differs")
        for case_id in M6_COMPARISON_CASES:
            if (
                len(
                    {
                        entry.cohort.source_case_sha256
                        for entry in self.cohorts
                        if entry.cohort.case_id == case_id
                    }
                )
                != 1
            ):
                raise ValueError(
                    "M6 admission cohorts do not share identical acquired inputs"
                )
        if self.plan_id != content_id(
            "m6compare_", self.model_dump(mode="json", exclude={"plan_id"})
        ):
            raise ValueError("M6 comparison plan identity differs")
        return self


def _object(path: Path) -> dict[str, object]:
    value = load_json_document(path)
    if not isinstance(value, dict):
        raise ValueError("M6 comparison requires an object record")
    return cast(dict[str, object], value)


def _hypotheses(path: Path) -> tuple[MrHypothesis, ...]:
    with path.open(encoding="utf-8") as handle:
        rows = tuple(MrHypothesis.model_validate_json(line) for line in handle)
    if len({row.hypothesis_id for row in rows}) != len(rows):
        raise ValueError("M6 comparison acquired inventory repeats a hypothesis")
    return rows


def _eligible_cohort_hypotheses(
    rows: tuple[MrHypothesis, ...],
    prior: M6AdmissionPrior,
    per_model_cap: int,
) -> tuple[MrHypothesis, ...]:
    if prior == "copy_weighted":
        eligible = tuple(
            row
            for row in rows
            if row.priority_features["initial_admission_eligible"] is True
        )
    else:
        by_model: dict[str, list[MrHypothesis]] = {}
        for row in rows:
            if row.priority_features["matthews_physical_status"] == "impossible":
                raise ValueError("M6 acquired inventory includes an impossible state")
            by_model.setdefault(row.model_id, []).append(row)
        eligible = tuple(
            row
            for model in sorted(by_model)
            for row in sorted(
                by_model[model],
                key=lambda row: (
                    {"plausible": 0, "review": 1}[
                        cast(str, row.priority_features["matthews_physical_status"])
                    ],
                    -cast(float, row.priority_features["solvent_density"]),
                    row.copy_count_expected,
                ),
            )[:per_model_cap]
        )
    return eligible


def _select_cohort(
    rows: tuple[MrHypothesis, ...],
    config: PipelineConfig,
    prior: M6AdmissionPrior,
    per_model_cap: int,
) -> tuple[MrHypothesis, ...]:
    eligible = _eligible_cohort_hypotheses(rows, prior, per_model_cap)
    selected, _ = select_diverse_hypothesis_inventory(
        eligible,
        config,
        25,
        phase3_screen=False,
        prior=prior,
    )
    return selected


def _write_cohort_hypotheses_tsv(
    path: Path,
    *,
    source: Path,
    rows: tuple[MrHypothesis, ...],
    models: dict[str, AllEligibleModelEntry],
) -> None:
    """Preserve the producer's table columns while publishing the actual cohort."""

    with source.open(encoding="utf-8", newline="") as handle:
        columns = csv.DictReader(handle, delimiter="\t").fieldnames
    if not columns:
        raise ValueError("M6 source hypothesis table has no columns")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=columns, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        values = {
            **row.priority_features,
            **row.model_dump(mode="json"),
            "coordinate_id": models[row.model_id].coordinate_id,
            "model_path": models[row.model_id].model_path,
        }
        writer.writerow({column: values[column] for column in columns})
    atomic_write_text(path, stream.getvalue())


def _prepare_cohort(case: Path, prior: M6AdmissionPrior, output: Path) -> Path:
    task = M6CaseTask.model_validate_json((case / "case_task.json").read_bytes())
    plan = M6HypothesisGroupTask.model_validate_json(
        (case / "case_plan.json").read_bytes()
    )
    if (
        task.case_id != plan.case_id
        or task.case_id not in m6_track_case_ids(task.track)
        or task.case_id not in M6_COMPARISON_CASES
    ):
        raise ValueError(
            "M6 comparison requires its twelve cases on their frozen tracks"
        )
    if (case / "comparison_cohort.json").exists():
        raise ValueError(
            "M6 comparison cannot derive a new cohort from another comparison"
        )
    for name, expected in (
        ("reflections.mtz", task.reflections_sha256),
        ("analysis_config.json", task.analysis_config_sha256),
    ):
        if sha256_file(case / name) != expected:
            raise ValueError("M6 comparison source case input checksum differs")
    source_digest = comparison_case_digest(case)
    shutil.copytree(case, output)
    selected: tuple[MrHypothesis, ...] = ()
    if plan.hypothesis_count:
        source_funnel = case / "first-copy-funnel"
        funnel = output / "first-copy-funnel"
        manifest = _object(source_funnel / "funnel_manifest.json")
        bundle = _object(case / "bundle_manifest.json")
        if cast(dict[str, str], bundle["output_sha256"])[
            "funnel_manifest"
        ] != sha256_file(source_funnel / "funnel_manifest.json"):
            raise ValueError("M6 source case funnel checksum differs")
        rows = _hypotheses(source_funnel / "complete_acquired_hypotheses.jsonl")
        if (
            len(rows) != manifest["complete_acquired_hypothesis_count"]
            or sha256_file(source_funnel / "complete_acquired_hypotheses.jsonl")
            != manifest["complete_acquired_hypotheses_sha256"]
        ):
            raise ValueError("M6 complete acquired inventory checksum differs")
        if any(
            row.crystal_id != task.case_id or row.copy_number_to_search != 1
            for row in rows
        ):
            raise ValueError(
                "M6 comparison inventory changes case or initial-copy policy"
            )
        cap = manifest["per_model_copy_cap"]
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
            raise ValueError("M6 comparison lacks a valid per-model admission cap")
        if any(
            row.priority_features["initial_per_model_copy_cap"] != cap for row in rows
        ):
            raise ValueError("M6 comparison model admission caps differ")
        config = load_contract(
            case / "analysis_config.json", "pipeline-config", progress=False
        )
        if not isinstance(config, PipelineConfig):
            raise TypeError("M6 comparison requires a pipeline configuration")
        production = _select_cohort(rows, config, "copy_weighted", cap)
        if tuple(row.hypothesis_id for row in production) != plan.hypothesis_ids:
            raise ValueError("M6 comparison cannot replay production admission exactly")
        selected = _select_cohort(rows, config, prior, cap)
        registry = load_all_eligible_model_registry(
            source_funnel / "model_registry/all_model_registry.json"
        )
        models = {
            entry.model_id: entry
            for group in registry.manifest.sequence_groups
            for entry in group.models
        }
        if any(row.model_id not in models for row in rows):
            raise ValueError("M6 comparison inventory has an unowned moving model")
        if prior == "solvent_density":
            eligible_ids = {
                row.hypothesis_id
                for row in _eligible_cohort_hypotheses(rows, prior, cap)
            }
            selected_ids = {row.hypothesis_id for row in selected}
            complete = tuple(
                row.model_copy(
                    update={
                        "status": MrHypothesisStatus.QUEUED
                        if row.hypothesis_id in selected_ids
                        else MrHypothesisStatus.SKIPPED,
                        "priority_features": {
                            **row.priority_features,
                            "source_initial_admission_eligible": row.priority_features[
                                "initial_admission_eligible"
                            ],
                            "initial_admission_eligible": row.hypothesis_id
                            in eligible_ids,
                            "comparison_admission_prior": prior,
                            "comparison_selected_for_execution": row.hypothesis_id
                            in selected_ids,
                            "first_copy_execution_disposition": (
                                "comparison_scheduled"
                                if row.hypothesis_id in selected_ids
                                else "comparison_deferred"
                            ),
                        },
                    }
                )
                for row in rows
            )
            complete_by_id = {row.hypothesis_id: row for row in complete}
            selected = tuple(complete_by_id[row.hypothesis_id] for row in selected)
            selected_by_id = {row.hypothesis_id: row for row in selected}
            atomic_write_text(
                funnel / "complete_acquired_hypotheses.jsonl",
                "".join(canonical_json_text(row) + "\n" for row in complete),
            )
            atomic_write_text(
                funnel / "mr_hypotheses.jsonl",
                "".join(canonical_json_text(row) + "\n" for row in selected),
            )
            _write_cohort_hypotheses_tsv(
                funnel / "mr_hypotheses.tsv",
                source=source_funnel / "mr_hypotheses.tsv",
                rows=selected,
                models=models,
            )
            atomic_write_text(
                funnel / "deferred_cap_hypotheses.jsonl",
                "".join(
                    canonical_json_text(row) + "\n"
                    for row in complete
                    if row.hypothesis_id not in selected_ids
                ),
            )
            # Replace only the owned generated task-record directory.
            for path in (funnel / "hypotheses").iterdir():
                if not path.is_file() or path.suffix != ".jsonl":
                    raise ValueError(
                        "M6 source hypothesis directory has an unexpected entry"
                    )
                path.unlink()
            for row in selected:
                atomic_write_text(
                    funnel / "hypotheses" / f"{row.hypothesis_id}.jsonl",
                    canonical_json_text(row) + "\n",
                )
            manifest.update(
                {
                    "funnel_id": content_id(
                        "funnel_",
                        {
                            "comparison_spec_sha256": M6_COMPARISON_SHA256,
                            "source_funnel_sha256": sha256_file(
                                source_funnel / "funnel_manifest.json"
                            ),
                            "prior": prior,
                            "hypothesis_ids": tuple(selected_by_id),
                        },
                    ),
                    "selected_hypothesis_count": len(selected),
                    "initial_admission_candidate_count": len(eligible_ids),
                    "excluded_by_caps_count": len(complete) - len(selected),
                    "per_crystal_selected_counts": {task.case_id: len(selected)},
                    "complete_acquired_hypotheses_sha256": sha256_file(
                        funnel / "complete_acquired_hypotheses.jsonl"
                    ),
                    "hypotheses": [
                        {
                            "hypothesis_id": row.hypothesis_id,
                            "model_id": row.model_id,
                            "model_path": models[row.model_id].model_path,
                            "model_sha256": models[row.model_id].model_sha256,
                            "coordinate_id": models[row.model_id].coordinate_id,
                            "coordinate_provider": models[row.model_id].provider,
                            "matthews_hypothesis_id": row.priority_features[
                                "matthews_hypothesis_id"
                            ],
                        }
                        for row in selected
                    ],
                    "comparison_admission_prior": prior,
                    "comparison_spec_sha256": M6_COMPARISON_SHA256,
                    "ordering_features": [
                        "solvent_density"
                        if feature == "matthews_prior"
                        else "copy_count_expected"
                        if feature == "matthews_rank_within_candidate"
                        else feature
                        for feature in cast(list[str], manifest["ordering_features"])
                    ],
                }
            )
            atomic_write_json(funnel / "funnel_manifest.json", manifest)
            plan = plan.model_copy(
                update={
                    "hypothesis_ids": tuple(row.hypothesis_id for row in selected),
                    "hypothesis_count": len(selected),
                }
            )
            atomic_write_json(output / "case_plan.json", plan.model_dump(mode="json"))
            cast(dict[str, str], bundle["output_sha256"])["case_plan"] = sha256_file(
                output / "case_plan.json"
            )
            cast(dict[str, str], bundle["output_sha256"])["funnel_manifest"] = (
                sha256_file(funnel / "funnel_manifest.json")
            )
            atomic_write_json(output / "bundle_manifest.json", bundle)
    payload = {
        "schema_version": "1.0",
        "comparison_id": M6_COMPARISON_ID,
        "comparison_spec_sha256": M6_COMPARISON_SHA256,
        "case_id": task.case_id,
        "admission_prior": prior,
        "source_case_sha256": source_digest,
        "case_sha256": comparison_case_digest(output),
        "scheduled_hypothesis_ids": tuple(row.hypothesis_id for row in selected),
    }
    cohort = M6ComparisonCohort.model_validate(
        {**payload, "cohort_id": content_id("m6cohort_", payload)}
    )
    atomic_write_json(output / "comparison_cohort.json", cohort.model_dump(mode="json"))
    return output


def prepare_m6_comparison(
    *,
    cases: tuple[Path, ...],
    recipe: Path,
    protocol: Path,
    software_lock: Path,
    phenix_manifest: Path,
    source_commit: str,
    output: Path,
) -> Path:
    """Freeze exactly 24 bounded cohorts without running a scientific tool."""

    validate_comparison_recipe(recipe)
    if sha256_file(protocol) != M6_FROZEN_PROTOCOL_SHA256:
        raise ValueError("M6 comparison changes the frozen base protocol")
    by_case: dict[str, Path] = {}
    for path in cases:
        case = path.resolve(strict=True)
        task = M6CaseTask.model_validate_json((case / "case_task.json").read_bytes())
        if task.case_id in by_case:
            raise ValueError("M6 comparison repeats a case")
        by_case[task.case_id] = case
    if set(by_case) != set(M6_COMPARISON_CASES):
        raise ValueError("M6 comparison requires all twelve frozen cases")
    output.mkdir(parents=True, exist_ok=False)
    entries: list[dict[str, object]] = []
    for case_id in M6_COMPARISON_CASES:
        for prior in ("solvent_density", "copy_weighted"):
            cohort_path = _prepare_cohort(
                by_case[case_id], prior, output / "cohorts" / case_id / prior
            )
            cohort = load_comparison_cohort(cohort_path)
            entries.append(
                {
                    "cohort": cohort.model_dump(mode="json"),
                    "case_path": cohort_path.relative_to(output).as_posix(),
                }
            )
    initial_count = sum(
        len(M6ComparisonCohort.model_validate(entry["cohort"]).scheduled_hypothesis_ids)
        for entry in entries
    )
    if initial_count > 600:
        raise ValueError("M6 comparison exceeds the 600 initial-hypothesis budget")
    payload = {
        "schema_version": "1.0",
        "comparison_id": M6_COMPARISON_ID,
        "comparison_spec_sha256": M6_COMPARISON_SHA256,
        "protocol_sha256": sha256_file(protocol),
        "software_lock_sha256": sha256_file(software_lock),
        "phenix_manifest_sha256": sha256_file(phenix_manifest),
        "source_commit": source_commit,
        "cohorts": entries,
        "initial_hypothesis_count": initial_count,
        "continuation_is_frozen": False,
        "truth_join_permitted": False,
    }
    plan = M6ComparisonPlan.model_validate(
        {**payload, "plan_id": content_id("m6compare_", payload)}
    )
    atomic_write_json(output / "comparison_plan.json", plan.model_dump(mode="json"))
    return output


def select_m6_comparison_seeds(
    *,
    case: Path,
    results: tuple[Path, ...],
    arm: M6ComparisonArm,
    output: Path,
) -> Path:
    """Review shared native results under exactly one of the frozen arm orders."""

    cohort = load_comparison_cohort(case)
    context = M6ComparisonArmContext(schema_version="1.0", arm=arm, cohort=cohort)
    if cohort.scheduled_hypothesis_ids:
        return run_m6_select_seeds_task(case, results, output, comparison_arm=arm)
    if results:
        raise ValueError("M6 empty comparison cohort received native results")
    run_m6_empty_seeds_task(case, output)
    atomic_write_text(output / "first_copy_results.jsonl", "")
    atomic_write_json(
        output / "comparison_context.json", context.model_dump(mode="json")
    )
    return output


def validate_m6_comparison_plan(
    root: Path,
    *,
    software_lock: Path,
    phenix_manifest: Path,
) -> M6ComparisonPlan:
    """Recheck every cohort and the fixed runtime before initial native scheduling."""

    plan = M6ComparisonPlan.model_validate_json(
        (root / "comparison_plan.json").read_bytes()
    )
    if (
        sha256_file(software_lock) != plan.software_lock_sha256
        or sha256_file(phenix_manifest) != plan.phenix_manifest_sha256
    ):
        raise ValueError("M6 comparison execution environment changed")
    for entry in plan.cohorts:
        if load_comparison_cohort(root / entry.case_path) != entry.cohort:
            raise ValueError("M6 comparison case differs from the initial plan")
    return plan


def _advancement_payload(
    *,
    plan_root: Path,
    seed_bundles: tuple[Path, ...],
) -> tuple[
    dict[str, object],
    dict[tuple[str, M6ComparisonArm], tuple[Path, M6ComparisonArmContext]],
]:
    """Derive the exact workload from every arm's authenticated native evidence."""

    plan = M6ComparisonPlan.model_validate_json(
        (plan_root / "comparison_plan.json").read_bytes()
    )
    cohorts = {entry.cohort.cohort_id: entry for entry in plan.cohorts}
    by_arm: dict[tuple[str, M6ComparisonArm], tuple[Path, M6ComparisonArmContext]] = {}
    for path in seed_bundles:
        root = path.resolve(strict=True)
        context = M6ComparisonArmContext.model_validate_json(
            (root / "comparison_context.json").read_bytes()
        )
        key = (context.cohort.case_id, context.arm)
        if (
            key in by_arm
            or context.cohort.cohort_id not in cohorts
            or context.cohort != cohorts[context.cohort.cohort_id].cohort
        ):
            raise ValueError("M6 comparison seed bundle repeats or substitutes an arm")
        by_arm[key] = (root, context)
    if set(by_arm) != {
        (case_id, arm) for case_id in M6_COMPARISON_CASES for arm in M6_COMPARISON_ARMS
    }:
        raise ValueError("M6 comparison requires all forty-eight case/arm reviews")
    entries: list[dict[str, object]] = []
    native_by_cohort: dict[str, str] = {}
    failed_cohorts: set[str] = set()
    total_chains = 0
    total_copies = 0
    for (case_id, arm), (root, context) in sorted(by_arm.items()):
        native_digest = comparison_case_digest(
            root / "first-copy-results", allow_empty=True
        )
        cohort_id = context.cohort.cohort_id
        if (
            cohort_id in native_by_cohort
            and native_by_cohort[cohort_id] != native_digest
        ):
            raise ValueError(
                "paired M6 review arms do not reuse identical native evidence"
            )
        native_by_cohort[cohort_id] = native_digest
        native = tuple(
            NormalisedMrResult.model_validate_json(line)
            for line in (root / "first_copy_results.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        retained_native = tuple(
            NormalisedMrResult.model_validate_json(path.read_bytes())
            for path in sorted(
                (root / "first-copy-results").glob("*/normalised_mr_result.json")
            )
        )
        if sorted(native, key=lambda row: row.hypothesis_id) != sorted(
            retained_native, key=lambda row: row.hypothesis_id
        ):
            raise ValueError(
                "M6 comparison aggregate differs from its retained native records"
            )
        if {row.hypothesis_id for row in native} != set(
            context.cohort.scheduled_hypothesis_ids
        ) or len(native) != len(context.cohort.scheduled_hypothesis_ids):
            raise ValueError("M6 comparison initial native partition is incomplete")
        if any(
            row.execution_status
            not in {ExecutionStatus.COMPLETED_HIT, ExecutionStatus.COMPLETED_NO_HIT}
            for row in native
        ):
            failed_cohorts.add(cohort_id)
        seed_plan = _object(root / "seed_plan.json")
        tasks = tuple(
            M6SeedTask.model_validate_json((path / "task.json").read_bytes())
            for path in sorted((root / "seed_tasks").iterdir())
        )
        if len(tasks) > 5 or len(tasks) != seed_plan["selected_seed_count"]:
            raise ValueError("M6 comparison seed budget differs from its review")
        if tasks:
            authority, _ = validate_m6_advancement_authority(
                root / "benchmark_advancement_manifest.json",
                hypotheses_jsonl=root / "scheduled_hypotheses.jsonl",
            )
            if authority.comparison_context != context or set(
                authority.selected_solution_ids
            ) != {task.seed_solution_id for task in tasks}:
                raise ValueError(
                    "M6 comparison selected tasks differ from their authority"
                )
            budgets = authority.additional_copy_budget_by_seed
        else:
            budgets = {}
        for task in tasks:
            if (
                task.case_id != case_id
                or task.advancement_authority_sha256
                != sha256_file(root / "benchmark_advancement_manifest.json")
                or budgets[task.seed_solution_id]
                != max(0, task.expected_copy_count - task.first_copy_placed_count)
            ):
                raise ValueError(
                    "M6 comparison copy workload differs from selected evidence"
                )
        total_chains += len(tasks)
        total_copies += sum(budgets.values())
        entries.append(
            {
                "case_id": case_id,
                "arm": arm,
                "cohort_id": cohort_id,
                "case_path": "initial_plan/" + cohorts[cohort_id].case_path,
                "seed_path": f"arms/{case_id}/{arm}",
                "seed_bundle_sha256": comparison_case_digest(root),
                "native_first_copy_sha256": native_digest,
                "selected_seed_ids": sorted(budgets),
                "additional_copy_budget_by_seed": budgets,
            }
        )
    if total_chains > 240:
        raise ValueError("M6 comparison exceeds 240 advancement chains")
    payload = {
        "schema_version": "1.0",
        "comparison_id": M6_COMPARISON_ID,
        "initial_plan_id": plan.plan_id,
        "initial_plan_sha256": sha256_file(plan_root / "comparison_plan.json"),
        "arms": entries,
        "initial_hypothesis_count": plan.initial_hypothesis_count,
        "continuation_chain_count": total_chains,
        "additional_copy_attempt_budget": total_copies,
        "failed_initial_cohort_ids": sorted(failed_cohorts),
        "continuation_authorised": not failed_cohorts,
        "truth_join_permitted": False,
    }
    return payload, by_arm


def freeze_m6_comparison_advancement(
    *, plan_root: Path, seed_bundles: tuple[Path, ...], output: Path
) -> Path:
    """Freeze exact copy workloads only after both reviews of every native cohort."""

    payload, by_arm = _advancement_payload(
        plan_root=plan_root, seed_bundles=seed_bundles
    )
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(plan_root, output / "initial_plan")
    for (case_id, arm), (root, _) in by_arm.items():
        shutil.copytree(root, output / "arms" / case_id / arm)
    atomic_write_json(
        output / "comparison_advancement.json",
        {**payload, "freeze_id": content_id("m6freeze_", payload)},
    )
    return output


def validate_m6_comparison_advancement(
    root: Path,
    *,
    software_lock: Path,
    phenix_manifest: Path,
) -> dict[str, object]:
    """Re-derive budgets and paired native evidence before continuation submission."""

    validate_m6_comparison_plan(
        root / "initial_plan",
        software_lock=software_lock,
        phenix_manifest=phenix_manifest,
    )
    payload, _ = _advancement_payload(
        plan_root=root / "initial_plan",
        seed_bundles=tuple(
            root / "arms" / case_id / arm
            for case_id in M6_COMPARISON_CASES
            for arm in M6_COMPARISON_ARMS
        ),
    )
    expected = {**payload, "freeze_id": content_id("m6freeze_", payload)}
    if _object(root / "comparison_advancement.json") != expected:
        raise ValueError("M6 frozen advancement differs from retained native evidence")
    if expected["continuation_authorised"] is not True:
        raise ValueError(
            "M6 comparison continuation is held by incomplete native execution"
        )
    return expected
