from pathlib import Path

import pytest
from pydantic import ValidationError

from genome_to_diffraction.mr_resources import (
    MrResourcePlanError,
    build_mr_resource_plan,
    count_polymer_atoms,
    resources_for_attempt,
    verify_mr_thread_allocation,
)
from genome_to_diffraction.schemas.mr_resources import (
    MrResourcePlan,
    MrResourceTier,
)


def _plan_for_score_band(tier: MrResourceTier) -> MrResourcePlan:
    if tier is MrResourceTier.STANDARD:
        return build_mr_resource_plan(
            owner_kind="mr_hypothesis",
            owner_id="mrhyp_standard",
            reflection_count=10_000,
            moving_atom_count=1_000,
            searched_copy_count=1,
            fixed_atom_count=0,
            symmetry_multiplicity=4,
        )
    if tier is MrResourceTier.HEAVY:
        return build_mr_resource_plan(
            owner_kind="mr_hypothesis",
            owner_id="mrhyp_heavy",
            reflection_count=36_961,
            moving_atom_count=3_534,
            searched_copy_count=2,
            fixed_atom_count=0,
            symmetry_multiplicity=24,
        )
    return build_mr_resource_plan(
        owner_kind="mr_hypothesis",
        owner_id="mrhyp_very_heavy",
        reflection_count=1_112_031,
        moving_atom_count=3_811,
        searched_copy_count=2,
        fixed_atom_count=0,
        symmetry_multiplicity=2,
    )


@pytest.mark.parametrize(
    ("tier", "base", "retry"),
    (
        (MrResourceTier.STANDARD, (4, 16, 12), (8, 32, 24)),
        (MrResourceTier.HEAVY, (6, 24, 18), (12, 48, 36)),
        (MrResourceTier.VERY_HEAVY, (8, 32, 24), (16, 64, 48)),
    ),
)
def test_resource_tiers_and_linear_retry_are_bounded(
    tier: MrResourceTier,
    base: tuple[int, int, int],
    retry: tuple[int, int, int],
) -> None:
    plan = _plan_for_score_band(tier)

    assert plan.tier is tier
    assert (plan.base_cpus, plan.base_memory_gb, plan.base_time_hours) == base
    first = resources_for_attempt(plan, 1)
    second = resources_for_attempt(plan, 2)
    assert (first.cpus, first.memory_gb, first.time_hours) == base
    assert (second.cpus, second.memory_gb, second.time_hours) == retry


def test_resource_plan_caps_symmetry_cost_and_binds_content() -> None:
    plan = _plan_for_score_band(MrResourceTier.HEAVY)

    assert plan.symmetry_multiplicity == 24
    assert plan.symmetry_cost_factor == 8
    assert plan.coordinate_atom_workload == 7_068
    assert plan.workload_score == 2_089_922_784

    changed = plan.model_dump(mode="json")
    changed["workload_score"] = plan.workload_score + 1
    with pytest.raises(ValidationError, match="workload score is not derived"):
        MrResourcePlan.model_validate(changed)


def test_resource_attempt_and_threads_fail_closed() -> None:
    plan = _plan_for_score_band(MrResourceTier.STANDARD)

    assert (
        verify_mr_thread_allocation(
            plan=plan,
            resource_attempt=2,
            threads=8,
        ).cpus
        == 8
    )
    with pytest.raises(MrResourcePlanError, match="threads differ"):
        verify_mr_thread_allocation(
            plan=plan,
            resource_attempt=2,
            threads=4,
        )
    with pytest.raises(MrResourcePlanError, match="outside the retry policy"):
        resources_for_attempt(plan, 3)


def test_polymer_atom_count_uses_exact_coordinate_bytes() -> None:
    model = (
        Path(__file__).parents[1]
        / "fixtures/stubs/predicted_model_preparation/models/stub.pdb"
    )

    assert count_polymer_atoms(model) == 4
