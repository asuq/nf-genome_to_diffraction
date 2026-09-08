"""Stage-specific, truth-blind M6 admission and advancement evidence.

This contract retains scheduled production hypotheses, production recommendations
and checksum-bound observed advancement separately. It records no target truth.
The collector joins sequence/family truth only after the case record is fixed.
Unknown IDs, duplicate states, missing stages and budget inconsistencies fail.
No external commands or mutable caches are used; canonical content is its identity.
Unit/collection tests cover stage conservation, unique proteins and false recovery.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.benchmarks.m6_comparison_policy import M6ComparisonArmContext
from genome_to_diffraction.schemas.base import ContractModel, PositiveInt, Sha256Hex
from genome_to_diffraction.schemas.results import MrHypothesis

M6_DECISION_POLICY = "m6_production_scheduled25_advanced5_v1"


class M6SeedRecommendation(ContractModel):
    """An inspectable review disposition before any benchmark advancement."""

    schema_version: Literal["1.0"]
    case_id: str
    hypothesis_id: str
    solution_id: str
    sequence_group_id: str
    production_review_rank: PositiveInt
    independent_mr_rank: PositiveInt
    independent_matthews_rank: PositiveInt
    recommendation_rank: PositiveInt | None
    advancement_disposition: Literal[
        "recommended", "deferred_seed_cap", "not_eligible_for_benchmark_advancement"
    ]
    advancement_observed: Literal[False]
    human_approval: Literal[False]

    @model_validator(mode="after")
    def _validate_disposition(self) -> Self:
        expected = (
            "not_eligible_for_benchmark_advancement"
            if self.recommendation_rank is None
            else "recommended"
            if self.recommendation_rank <= 5
            else "deferred_seed_cap"
        )
        if self.advancement_disposition != expected:
            raise ValueError("M6 recommendation rank and disposition differ")
        return self


class M6ObservedAdvancement(ContractModel):
    """Evidence of a completed benchmark continuation stage for a selected seed."""

    solution_id: str
    hypothesis_id: str
    sequence_group_id: str
    authority_kind: Literal["benchmark_policy"]
    authority_sha256: Sha256Hex
    terminal_record_sha256: Sha256Hex
    advancement_observed: Literal[True]
    human_approval: Literal[False]


class M6DecisionTrace(ContractModel):
    """Exact inventories at the scheduled-25 and advanced-five boundaries."""

    schema_version: Literal["1.0"]
    policy_id: Literal[
        "m6_production_scheduled25_advanced5_v1", "m6_ranking_four_arm_v1"
    ]
    case_id: str
    scheduled_hypotheses: tuple[MrHypothesis, ...] = Field(max_length=25)
    recommendations: tuple[M6SeedRecommendation, ...] = Field(max_length=25)
    observed_advancement: tuple[M6ObservedAdvancement, ...] = Field(max_length=5)
    provider_ranks_are_diagnostic: Literal[True]
    comparison_context: M6ComparisonArmContext | None = None

    @model_validator(mode="after")
    def _validate_stage_joins(self) -> Self:
        if (self.comparison_context is None) != (self.policy_id == M6_DECISION_POLICY):
            raise ValueError("M6 decision policy and comparison scope differ")
        if self.comparison_context is not None and (
            self.comparison_context.cohort.case_id != self.case_id
            or self.comparison_context.cohort.scheduled_hypothesis_ids
            != tuple(row.hypothesis_id for row in self.scheduled_hypotheses)
        ):
            raise ValueError("M6 comparison trace has another initial cohort")
        hypotheses = {row.hypothesis_id: row for row in self.scheduled_hypotheses}
        if len(hypotheses) != len(self.scheduled_hypotheses):
            raise ValueError("M6 scheduled hypotheses are duplicated")
        if any(
            row.crystal_id != self.case_id or row.copy_number_to_search != 1
            for row in self.scheduled_hypotheses
        ):
            raise ValueError(
                "M6 scheduled hypothesis has another case or initial-copy policy"
            )
        recommendations = {row.solution_id: row for row in self.recommendations}
        if len(recommendations) != len(self.recommendations):
            raise ValueError("M6 recommendation solution IDs are duplicated")
        if {row.hypothesis_id for row in self.recommendations} != set(
            hypotheses
        ) or len(self.recommendations) != len(hypotheses):
            raise ValueError(
                "M6 production review omitted or duplicated scheduled hypotheses"
            )
        if tuple(row.production_review_rank for row in self.recommendations) != tuple(
            range(1, len(self.recommendations) + 1)
        ):
            raise ValueError("M6 production review order is not complete")
        for row in self.recommendations:
            if (
                row.case_id != self.case_id
                or row.sequence_group_id
                != hypotheses[row.hypothesis_id].sequence_group_id
            ):
                raise ValueError("M6 recommendation ownership differs from admission")
        eligible_ranks = tuple(
            row.recommendation_rank
            for row in self.recommendations
            if row.recommendation_rank is not None
        )
        if (
            eligible_ranks
            if self.comparison_context is None
            else tuple(sorted(eligible_ranks))
        ) != tuple(range(1, len(eligible_ranks) + 1)):
            raise ValueError("M6 eligible recommendation order is incomplete")
        advanced_ids = [row.solution_id for row in self.observed_advancement]
        if len(advanced_ids) != len(set(advanced_ids)):
            raise ValueError("M6 observed advancement is duplicated")
        for row in self.observed_advancement:
            recommendation = recommendations.get(row.solution_id)
            if (
                recommendation is None
                or recommendation.advancement_disposition != "recommended"
                or (row.hypothesis_id, row.sequence_group_id)
                != (recommendation.hypothesis_id, recommendation.sequence_group_id)
            ):
                raise ValueError(
                    "M6 observed advancement was not production-recommended"
                )
        expected_order = tuple(
            row.solution_id
            for row in sorted(
                self.recommendations,
                key=lambda row: row.recommendation_rank or 26,
            )
            if row.solution_id in set(advanced_ids)
        )
        if tuple(advanced_ids) != expected_order:
            raise ValueError(
                "M6 advancement order differs from its recommendation inventory"
            )
        return self

    @property
    def scheduled_unique_sequence_count(self) -> int:
        return len({row.sequence_group_id for row in self.scheduled_hypotheses})

    @property
    def recommended_unique_sequence_count(self) -> int:
        return len(
            {
                row.sequence_group_id
                for row in self.recommendations
                if row.advancement_disposition == "recommended"
            }
        )

    @property
    def advanced_unique_sequence_count(self) -> int:
        return len({row.sequence_group_id for row in self.observed_advancement})


class M6StageMetrics(ContractModel):
    """Truth-side metrics with unambiguous inventory and stage definitions."""

    trace_sha256: Sha256Hex
    policy_id: Literal[
        "m6_production_scheduled25_advanced5_v1", "m6_ranking_four_arm_v1"
    ]
    target_rank_stage: Literal["scheduled_hypothesis_prefix"]
    provider_diagnostic_rank: PositiveInt | None
    scheduled_hypothesis_count: Annotated[int, Field(ge=0, le=25)]
    scheduled_unique_sequence_count: Annotated[int, Field(ge=0, le=25)]
    recommended_seed_count: Annotated[int, Field(ge=0, le=5)]
    recommended_unique_sequence_count: Annotated[int, Field(ge=0, le=5)]
    advanced_seed_count: Annotated[int, Field(ge=0, le=5)]
    advanced_unique_sequence_count: Annotated[int, Field(ge=0, le=5)]
    target_scheduled_unique_sequence_rank: PositiveInt | None
    target_recommended_seed_rank: PositiveInt | None
    target_advanced_seed_rank: PositiveInt | None

    @model_validator(mode="after")
    def _validate_metric_counts(self) -> Self:
        if (
            self.scheduled_unique_sequence_count > self.scheduled_hypothesis_count
            or self.recommended_unique_sequence_count > self.recommended_seed_count
            or self.advanced_unique_sequence_count > self.advanced_seed_count
            or self.advanced_seed_count > self.recommended_seed_count
        ):
            raise ValueError("M6 stage metrics have inconsistent distinct/state counts")
        for rank, count in (
            (
                self.target_scheduled_unique_sequence_rank,
                self.scheduled_unique_sequence_count,
            ),
            (self.target_recommended_seed_rank, self.recommended_seed_count),
            (self.target_advanced_seed_rank, self.advanced_seed_count),
        ):
            if rank is not None and rank > count:
                raise ValueError("M6 target rank exceeds its stage inventory")
        return self
