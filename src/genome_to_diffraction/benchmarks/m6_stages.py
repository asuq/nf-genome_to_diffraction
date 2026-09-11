"""Truth-blind M6 stage inventories and authenticated copy-chain receipts.

Inputs are the production-ordered scheduled hypotheses, catalogue groups,
production review authority and completed child bundles. Outputs distinguish
proteins, models, expected-copy states and tasks at scheduling, recommendation
and execution. No external command or benchmark truth is used. Missing,
duplicate, foreign or stale evidence fails; zero-copy-attempt continuation is
explicit, not an inferred native search. The case adapter/content identity
binds this contract. Tests cover real adapter receipts with simulated Phenix,
conservation and tampering, without claiming native qualification.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Self, cast

from pydantic import Field, model_validator

from genome_to_diffraction.benchmarks.m6_advancement import validate_m6_advancement
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_digest, canonical_json_text
from genome_to_diffraction.schemas.base import ContractModel, PositiveInt, Sha256Hex
from genome_to_diffraction.schemas.io import load_json_document, parse_json_document
from genome_to_diffraction.schemas.results import (
    AdditionalCopyResult,
    MrHypothesis,
    NormalisedMrResult,
    SequenceGroupRecord,
)


class M6StageRow(ContractModel):
    """One scheduled hypothesis and its distinct downstream stage evidence."""

    hypothesis_id: str
    sequence_group_id: str
    sequence_sha256: Sha256Hex
    model_id: str
    expected_copy_count: PositiveInt
    scheduled_rank: PositiveInt
    solution_id: str
    review_priority_rank: PositiveInt
    recommendation_rank: PositiveInt | None
    recommended: bool
    advanced_rank: PositiveInt | None
    continuation_receipt_sha256: Sha256Hex | None
    additional_copy_attempt_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_stages(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError("M6 stage sequence identity differs from its digest")
        if self.recommended != (
            self.recommendation_rank is not None and self.recommendation_rank <= 5
        ):
            raise ValueError("M6 stage recommendation disagrees with its bounded rank")
        if (self.advanced_rank is None) != (self.continuation_receipt_sha256 is None):
            raise ValueError("M6 advanced stage lacks its continuation receipt")
        if self.advanced_rank is not None and (
            not self.recommended or self.advanced_rank != self.recommendation_rank
        ):
            raise ValueError("M6 advanced stage differs from its recommendation")
        if self.additional_copy_attempt_count and self.advanced_rank is None:
            raise ValueError("M6 unadvanced hypothesis has copy attempts")
        return self


class M6StageCounts(ContractModel):
    """Non-interchangeable cardinalities within one execution stage."""

    unique_proteins: int = Field(ge=0)
    unique_models: int = Field(ge=0)
    expected_copy_states: int = Field(ge=0)
    hypothesis_tasks: int = Field(ge=0)


def stage_counts(rows: Sequence[M6StageRow]) -> M6StageCounts:
    """Count sequence equivalence groups, model IDs, copy states and tasks."""

    return M6StageCounts(
        unique_proteins=len({row.sequence_group_id for row in rows}),
        unique_models=len({row.model_id for row in rows}),
        expected_copy_states=len(
            {(row.sequence_group_id, row.expected_copy_count) for row in rows}
        ),
        hypothesis_tasks=len(rows),
    )


class M6StageInventory(ContractModel):
    """Complete scheduled inventory, never a provider-ranking surrogate."""

    schema_version: Literal["1.0"] = "1.0"
    case_id: str
    hypotheses_sha256: Sha256Hex | None
    benchmark_advancement_sha256: Sha256Hex | None
    rows: tuple[M6StageRow, ...] = Field(max_length=25)
    scheduled: M6StageCounts
    recommended: M6StageCounts
    advanced: M6StageCounts

    @model_validator(mode="after")
    def _validate_conservation(self) -> Self:
        if [row.scheduled_rank for row in self.rows] != list(
            range(1, len(self.rows) + 1)
        ):
            raise ValueError("M6 scheduled ranks are not complete and ordered")
        for field in ("hypothesis_id", "solution_id", "review_priority_rank"):
            if len({getattr(row, field) for row in self.rows}) != len(self.rows):
                raise ValueError(f"M6 stage inventory has duplicate {field}")
        if sorted(row.review_priority_rank for row in self.rows) != list(
            range(1, len(self.rows) + 1)
        ):
            raise ValueError("M6 review rank inventory changed")
        eligible = sorted(
            row.recommendation_rank
            for row in self.rows
            if row.recommendation_rank is not None
        )
        if eligible != list(range(1, len(eligible) + 1)):
            raise ValueError("M6 eligible recommendation ranks changed")
        if bool(self.rows) != (self.benchmark_advancement_sha256 is not None):
            raise ValueError("M6 stage inventory authority binding changed")
        if self.rows and self.hypotheses_sha256 is None:
            raise ValueError("M6 stage inventory lacks its scheduled input checksum")
        partitions = (
            (self.scheduled, self.rows),
            (self.recommended, tuple(row for row in self.rows if row.recommended)),
            (
                self.advanced,
                tuple(row for row in self.rows if row.advanced_rank is not None),
            ),
        )
        if any(counts != stage_counts(rows) for counts, rows in partitions):
            raise ValueError("M6 stage counts disagree with their inventories")
        return self


def target_stage_ranks(
    inventory: M6StageInventory, sequence_sha256: str | None
) -> dict[str, int | None]:
    """Join an evaluator-supplied digest without admitting truth to the runner."""

    rows = [row for row in inventory.rows if row.sequence_sha256 == sequence_sha256]
    return {
        "target_scheduled_rank": min(
            (row.scheduled_rank for row in rows), default=None
        ),
        "target_recommended_rank": min(
            (
                row.recommendation_rank
                for row in rows
                if row.recommended and row.recommendation_rank is not None
            ),
            default=None,
        ),
        "target_advanced_rank": min(
            (row.advanced_rank for row in rows if row.advanced_rank is not None),
            default=None,
        ),
    }


def _object(path: Path) -> dict[str, object]:
    value = load_json_document(path)
    if not isinstance(value, dict):
        raise ValueError("M6 stage evidence requires a JSON object")
    return value


def _owned(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("M6 stage evidence path must be package-relative")
    path = root / relative
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file() or not resolved.is_relative_to(root):
        raise ValueError("M6 stage evidence path escapes its bundle")
    return resolved


def _records[T: ContractModel](path: Path, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _copy_receipt(
    root: Path,
    *,
    task: dict[str, object],
    parent_sha256: str,
    parent_result_sha256: str,
    mtz_sha256: str,
) -> tuple[str, int]:
    """Authenticate the retained parent and every native attempt in one chain."""

    return _validate_copy_receipt(
        root,
        task=task,
        parent_sha256=parent_sha256,
        parent_result_sha256=parent_result_sha256,
        mtz_sha256=mtz_sha256,
        authority_kind="truth_blind_m6_benchmark",
        adapter_version="phenix-add-copy-mr-v9-m6-truth-blind",
    )


def _validate_copy_receipt(
    root: Path,
    *,
    task: dict[str, object],
    parent_sha256: str,
    parent_result_sha256: str,
    mtz_sha256: str,
    authority_kind: str,
    adapter_version: str,
) -> tuple[str, int]:
    """Shared chain validation after a caller authenticates its benchmark policy.

    Production always supplies the fixed M6 binding above. The isolated RF
    reference fixture supplies its independently validated reference binding;
    neither caller may substitute a recommendation for an execution receipt.
    """

    seed_id = task["seed_solution_id"]
    if _object(root / "seed_task.json") != task:
        raise ValueError("M6 continuation receipt differs from its seed task")
    summary = _object(root / "additional_copy_series_summary.json")
    parent = _object(root / "best_parent.json")
    authority = {
        "execution_authority_kind": authority_kind,
        "benchmark_advancement_id": task["advancement_id"],
        "benchmark_advancement_manifest_sha256": task["advancement_manifest_sha256"],
        "human_approval_granted": False,
        "seed_solution_id": seed_id,
        "parent_retained": True,
    }
    if any(
        record.get(key) != value or type(record.get(key)) is not type(value)
        for record in (summary, parent)
        for key, value in authority.items()
    ):
        raise ValueError("M6 continuation receipt authority changed")
    attempts = _records(
        root / "additional_copy_series_results.jsonl", AdditionalCopyResult
    )
    best_count = cast(int, task["first_copy_placed_count"])
    expected_count = cast(int, task["expected_copy_count"])
    parent_id = seed_id
    native_sha256: dict[str, str] = {}
    paths = summary.get("result_paths", [])
    checksums = summary.get("result_sha256", [])
    if (
        not isinstance(paths, list)
        or not isinstance(checksums, list)
        or len(paths) != len(attempts)
        or len(checksums) != len(attempts)
        or summary.get("attempt_count") != len(attempts)
        or type(summary.get("attempt_count")) is not int
        or summary.get("expected_copy_count") != expected_count
        or (not attempts) != (best_count == expected_count)
    ):
        raise ValueError("M6 continuation receipt attempt inventory changed")
    if attempts and (
        sha256_file(root / "series/additional_copy_series_results.jsonl")
        != sha256_file(root / "additional_copy_series_results.jsonl")
        or sha256_file(root / "series/additional_copy_series_summary.json")
        != sha256_file(root / "additional_copy_series_summary.json")
        or summary.get("attempt_ids") != [row.attempt_id for row in attempts]
        or summary.get("attempted_copy_numbers")
        != [row.attempted_copy_number for row in attempts]
    ):
        raise ValueError("M6 continuation receipt differs from native series")
    for index, attempt in enumerate(attempts):
        result_path = _owned(root / "series", paths[index])
        if sha256_file(result_path) != checksums[index] or _records(
            result_path, AdditionalCopyResult
        ) != (attempt,):
            raise ValueError("M6 continuation native result checksum changed")
        if (
            attempt.seed_solution_id != seed_id
            or attempt.review_id != task["advancement_id"]
            or attempt.hypothesis_id != task["hypothesis_id"]
            or attempt.sequence_group_id != task["sequence_group_id"]
            or attempt.expected_copy_count != expected_count
            or attempt.parent_solution_id != parent_id
            or attempt.parent_copy_count != best_count
            or best_count >= expected_count
        ):
            raise ValueError("M6 continuation native parent-child identity changed")
        command_path = _owned(result_path.parent, attempt.command_pointer)
        command = _object(command_path)
        parameters = _owned(result_path.parent, "add_copy.eff")
        command_expected = {
            **authority,
            "attempt_id": attempt.attempt_id,
            "parent_coordinate_sha256": parent_sha256,
            "parent_result_sha256": parent_result_sha256,
            "parent_solution_id": parent_id,
            "parent_copy_count": best_count,
            "mtz_sha256": mtz_sha256,
            "adapter_version": adapter_version,
            "parameters_sha256": sha256_file(parameters),
            "search_model_sha256": task["search_model_sha256"],
            "original_first_copy_model_sha256": task["search_model_sha256"],
        }
        command_expected.pop("parent_retained")
        if any(command.get(key) != value for key, value in command_expected.items()):
            raise ValueError("M6 continuation native command binding changed")
        log = _owned(result_path.parent, attempt.raw_log_pointer)
        for label, asset in (
            ("result", result_path),
            ("command", command_path),
            ("parameters", parameters),
            ("log", log),
        ):
            native_sha256[f"attempt_{index}_{label}"] = sha256_file(asset)
        if attempt.additional_copy_supported:
            coordinate = _owned(result_path.parent, attempt.output_coordinate_path)
            mtz = _owned(result_path.parent, attempt.output_mtz_path)
            if (
                sha256_file(coordinate) != attempt.output_coordinate_sha256
                or sha256_file(mtz) != attempt.output_mtz_sha256
            ):
                raise ValueError("M6 continuation native child assets changed")
            parent_sha256 = attempt.output_coordinate_sha256
            parent_result_sha256 = sha256_file(result_path)
            native_sha256[f"attempt_{index}_coordinate"] = sha256_file(coordinate)
            native_sha256[f"attempt_{index}_mtz"] = sha256_file(mtz)
            parent_id = attempt.child_solution_id
            best_count = attempt.best_supported_copy_count
        elif index != len(attempts) - 1:
            raise ValueError("M6 continuation proceeded after an unsupported addition")
    expected_stop = (
        "first_copy_already_reached_expected_count"
        if not attempts
        else "expected_copy_count_reached"
        if best_count == expected_count
        else "additional_copy_not_supported"
    )
    if (
        summary.get("best_supported_copy_count") != best_count
        or parent.get("best_supported_copy_count") != best_count
        or parent.get("case_id") != task["case_id"]
        or parent.get("sequence_group_id") != task["sequence_group_id"]
        or parent.get("parent_coordinate_sha256") != parent_sha256
        or sha256_file(root / "best_parent.pdb") != parent_sha256
        or summary.get("stop_reason") != expected_stop
        or summary.get("reached_expected_copy_count")
        is not (best_count == expected_count)
        or (
            attempts
            and attempts[-1].additional_copy_supported
            and best_count < expected_count
        )
    ):
        raise ValueError("M6 continuation retained parent or terminal state changed")
    receipt = {
        name: sha256_file(root / name)
        for name in (
            "seed_task.json",
            "additional_copy_series_summary.json",
            "additional_copy_series_results.jsonl",
            "best_parent.json",
            "best_parent.pdb",
        )
    }
    return canonical_digest({**receipt, **native_sha256}), len(attempts)


def build_m6_stage_inventory(
    case: Path, seeds: Path, add_copy_results: tuple[Path, ...]
) -> M6StageInventory:
    """Reconstruct stages from production order and authenticated child evidence."""

    case, seeds = case.resolve(strict=True), seeds.resolve(strict=True)
    plan = _object(case / "case_plan.json")
    case_id = cast(str, plan["case_id"])
    seed_plan = _object(seeds / "seed_plan.json")
    hypotheses_path = case / "first-copy-funnel/mr_hypotheses.jsonl"
    hypotheses = (
        _records(hypotheses_path, MrHypothesis) if hypotheses_path.is_file() else ()
    )
    if (
        len(hypotheses) != plan["hypothesis_count"]
        or len({row.hypothesis_id for row in hypotheses}) != len(hypotheses)
        or {row.hypothesis_id for row in hypotheses}
        != set(cast(list[str], plan["hypothesis_ids"]))
        or seed_plan.get("case_id") != case_id
    ):
        raise ValueError("M6 stage scheduled hypothesis partition changed")
    authority_path = seeds / "benchmark_advancement.json"
    if not hypotheses and authority_path.exists():
        raise ValueError("M6 empty scheduled inventory has an unexpected authority")
    authority = (
        validate_m6_advancement(authority_path, hypotheses_jsonl=hypotheses_path)
        if hypotheses
        else None
    )
    if authority is not None and authority.manifest.crystal_id != case_id:
        raise ValueError("M6 stage authority belongs to another case")
    first_root = seeds / "first-copy-results"
    expected_bundles = {f"first_copy_phaser_{row.hypothesis_id}" for row in hypotheses}
    if {
        path.name for path in first_root.iterdir() if path.is_dir()
    } != expected_bundles:
        raise ValueError("M6 stage first-copy result partition changed")
    if authority is not None:
        for item in cast(list[dict[str, object]], authority.review_document["items"]):
            result_path = _owned(
                first_root,
                f"first_copy_phaser_{item['hypothesis_id']}/normalised_mr_result.json",
            )
            result = NormalisedMrResult.model_validate_json(result_path.read_bytes())
            if (
                canonical_digest(result)
                != cast(dict[str, object], item["solution_identity"])["result_sha256"]
            ):
                raise ValueError(
                    "M6 stage first-copy result differs from production review"
                )
    recommendations = (
        {}
        if authority is None
        else {row.solution_id: row for row in authority.manifest.recommended}
    )
    by_seed: dict[str, Path] = {}
    for root in add_copy_results:
        root = root.resolve(strict=True)
        seed_id = cast(str, _object(root / "seed_task.json")["seed_solution_id"])
        if seed_id in by_seed:
            raise ValueError("M6 stage contains duplicate continuation receipts")
        by_seed[seed_id] = root
    if set(by_seed) != set(recommendations):
        raise ValueError("M6 stage missing or foreign continuation receipts")
    if seed_plan.get("selected_seed_count") != len(recommendations):
        raise ValueError("M6 stage recommendation count changed")
    seed_rows = tuple(
        parse_json_document(line, label="M6 seed task row")
        for line in (seeds / "seed_tasks.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    )
    if len(seed_rows) != len(recommendations) or any(
        not isinstance(row, dict) for row in seed_rows
    ):
        raise ValueError("M6 stage seed task inventory changed")
    seed_by_id = {
        row["seed_solution_id"]: row
        for row in cast(tuple[dict[str, object], ...], seed_rows)
    }
    if set(seed_by_id) != set(recommendations):
        raise ValueError("M6 stage seed task partition changed")
    groups = _records(case / "all_sequence_groups.jsonl", SequenceGroupRecord)
    by_group = {row.sequence_group_id: row for row in groups}
    if len(by_group) != len(groups):
        raise ValueError("M6 stage catalogue has duplicate sequence groups")
    by_hypothesis = (
        {}
        if authority is None
        else {row.hypothesis_id: row for row in authority.manifest.rows}
    )
    receipts: dict[str, tuple[str, int]] = {}
    for seed_id, recommendation in recommendations.items():
        if authority is None:
            raise ValueError("M6 recommendation lacks its benchmark authority")
        task = _object(_owned(seeds, f"seed_tasks/{seed_id}/task.json"))
        expected_task = {
            "schema_version": "2.0",
            "case_id": case_id,
            "seed_solution_id": seed_id,
            "hypothesis_id": recommendation.hypothesis_id,
            "sequence_group_id": recommendation.sequence_group_id,
            "model_id": recommendation.model_id,
            "expected_copy_count": recommendation.expected_copy_count,
            "first_copy_placed_count": recommendation.first_copy_placed_count,
            "advancement_id": authority.manifest.advancement_id,
            "advancement_manifest_sha256": sha256_file(authority_path),
        }
        item = next(
            row
            for row in cast(list[dict[str, object]], authority.review_document["items"])
            if row["solution_id"] == seed_id
        )
        assets = cast(dict[str, str], item["copied_assets"])
        review_root = authority.review_manifest.parent
        command = _object(_owned(review_root, assets["command"]))
        expected_task["search_model_sha256"] = command["model_sha256"]
        expected_row = {
            **expected_task,
            "benchmark_advancement": "benchmark_advancement.json",
            "review_manifest": authority.review_manifest.relative_to(seeds).as_posix(),
            "search_model": f"seed_tasks/{seed_id}/search_model.pdb",
        }
        if seed_by_id[seed_id] != expected_row:
            raise ValueError("M6 stage seed manifest differs from its task")
        if (
            task != expected_task
            or any(
                type(task[key]) is not type(value)
                for key, value in expected_task.items()
            )
            or sha256_file(_owned(seeds, f"seed_tasks/{seed_id}/search_model.pdb"))
            != task["search_model_sha256"]
        ):
            raise ValueError("M6 stage task differs from its production recommendation")
        receipts[seed_id] = _copy_receipt(
            by_seed[seed_id],
            task=task,
            parent_sha256=sha256_file(
                _owned(review_root, assets["solution_coordinate"])
            ),
            parent_result_sha256=sha256_file(
                _owned(review_root, assets["normalised_result"])
            ),
            mtz_sha256=sha256_file(case / "reflections.mtz"),
        )
    rows: list[M6StageRow] = []
    for rank, hypothesis in enumerate(hypotheses, start=1):
        recommendation = by_hypothesis[hypothesis.hypothesis_id]
        receipt = receipts.get(recommendation.solution_id)
        rows.append(
            M6StageRow(
                hypothesis_id=hypothesis.hypothesis_id,
                sequence_group_id=hypothesis.sequence_group_id,
                sequence_sha256=by_group[hypothesis.sequence_group_id].sha256,
                model_id=hypothesis.model_id,
                expected_copy_count=hypothesis.copy_count_expected,
                scheduled_rank=rank,
                solution_id=recommendation.solution_id,
                review_priority_rank=recommendation.review_priority_rank,
                recommendation_rank=recommendation.recommendation_rank,
                recommended=recommendation.advancement_disposition == "recommended",
                advanced_rank=None
                if receipt is None
                else recommendation.recommendation_rank,
                continuation_receipt_sha256=None if receipt is None else receipt[0],
                additional_copy_attempt_count=0 if receipt is None else receipt[1],
            )
        )
    return M6StageInventory(
        case_id=case_id,
        hypotheses_sha256=sha256_file(hypotheses_path)
        if hypotheses_path.is_file()
        else None,
        benchmark_advancement_sha256=sha256_file(authority_path) if authority else None,
        rows=tuple(rows),
        scheduled=stage_counts(rows),
        recommended=stage_counts([row for row in rows if row.recommended]),
        advanced=stage_counts([row for row in rows if row.advanced_rank is not None]),
    )


def verify_m6_stage_evidence(
    stages: M6StageInventory,
    first_copy_results: Sequence[dict[str, object]],
    selected_seed_results: Sequence[dict[str, object]],
    additional_copy_results: Sequence[dict[str, object]],
) -> None:
    """Check conserved identities in the compact collected case contract."""

    first = tuple(
        (
            MrHypothesis.model_validate_json(canonical_json_text(row["hypothesis"])),
            NormalisedMrResult.model_validate_json(canonical_json_text(row["result"])),
        )
        for row in first_copy_results
    )
    by_hypothesis = {row.hypothesis_id: row for row in stages.rows}
    if len(first) != len(by_hypothesis) or {
        hypothesis.hypothesis_id for hypothesis, _ in first
    } != set(by_hypothesis):
        raise ValueError("M6 first-copy results differ from scheduled inventory")
    first_by_id = {hypothesis.hypothesis_id: result for hypothesis, result in first}
    for hypothesis, result in first:
        row = by_hypothesis[hypothesis.hypothesis_id]
        if (
            result.hypothesis_id != hypothesis.hypothesis_id
            or hypothesis.crystal_id != stages.case_id
            or hypothesis.sequence_group_id != row.sequence_group_id
            or hypothesis.model_id != row.model_id
            or hypothesis.copy_count_expected != row.expected_copy_count
            or hypothesis.copy_number_to_search != 1
        ):
            raise ValueError("M6 scheduled result scientific identity changed")
    advanced = {
        row.solution_id: row for row in stages.rows if row.advanced_rank is not None
    }
    if stages.recommended != stages.advanced or len(selected_seed_results) != len(
        advanced
    ):
        raise ValueError("M6 completed case lacks recommended child receipts")
    if {row.get("seed_solution_id") for row in selected_seed_results} != set(advanced):
        raise ValueError("M6 selected seeds differ from executed continuation")
    copies = tuple(
        AdditionalCopyResult.model_validate_json(canonical_json_text(row))
        for row in additional_copy_results
    )
    if len({row.attempt_id for row in copies}) != len(copies) or any(
        row.seed_solution_id not in advanced for row in copies
    ):
        raise ValueError("M6 copy results contain duplicate or foreign attempts")
    for row in selected_seed_results:
        stage = advanced[cast(str, row["seed_solution_id"])]
        if any(
            row.get(field) != getattr(stage, field)
            for field in (
                "hypothesis_id",
                "sequence_group_id",
                "model_id",
                "expected_copy_count",
            )
        ):
            raise ValueError("M6 selected seed scientific identity changed")
        child_rows = [
            item for item in copies if item.seed_solution_id == stage.solution_id
        ]
        if len(child_rows) != stage.additional_copy_attempt_count or any(
            item.hypothesis_id != stage.hypothesis_id
            or item.sequence_group_id != stage.sequence_group_id
            or item.expected_copy_count != stage.expected_copy_count
            for item in child_rows
        ):
            raise ValueError("M6 copy attempts differ from continuation receipts")
        first_result = first_by_id[stage.hypothesis_id]
        if row.get(
            "first_copy_placed_count"
        ) != first_result.placed_copy_count or row.get(
            "best_supported_copy_count"
        ) != max(
            [
                first_result.placed_copy_count,
                *(item.best_supported_copy_count for item in child_rows),
            ]
        ):
            raise ValueError("M6 selected seed copy counts differ from child results")
