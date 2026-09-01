"""Build and verify deterministic Phase III Phaser resource allocations."""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import gemmi

from genome_to_diffraction.schemas.mr_resources import (
    MR_RESOURCE_MAX_CPUS,
    MR_RESOURCE_MAX_MEMORY_GB,
    MR_RESOURCE_MAX_RETRIES,
    MR_RESOURCE_MAX_TIME_HOURS,
    MR_RESOURCE_SYMMETRY_CAP,
    MR_RESOURCE_TIER_RESOURCES,
    MrResourcePlan,
    mr_resource_tier,
)
from genome_to_diffraction.status import InputContractError


class MrResourcePlanError(InputContractError):
    """Pre-execution MR workload evidence is missing or contradictory."""


@dataclass(frozen=True, slots=True)
class MrAttemptResources:
    """Resolved scheduler resources for one execution attempt."""

    cpus: int
    memory_gb: int
    time_hours: int


@cache
def count_polymer_atoms(path: Path) -> int:
    """Count polymer atoms in the exact coordinate file supplied to Phaser."""

    if path.is_symlink():
        raise MrResourcePlanError("MR resource coordinate must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise MrResourcePlanError("MR resource coordinate is absent") from error
    if not resolved.is_file():
        raise MrResourcePlanError("MR resource coordinate is not a regular file")
    try:
        structure = gemmi.read_structure(str(resolved))
        structure.setup_entities()
    except (OSError, RuntimeError, ValueError) as error:
        raise MrResourcePlanError("MR resource coordinate cannot be parsed") from error
    atom_count = sum(
        len(residue)
        for model in structure
        for chain in model
        for residue in chain.get_polymer()
    )
    if atom_count < 1:
        raise MrResourcePlanError("MR resource coordinate has no polymer atoms")
    return atom_count


def build_mr_resource_plan(
    *,
    owner_kind: str,
    owner_id: str,
    reflection_count: int,
    moving_atom_count: int,
    searched_copy_count: int,
    fixed_atom_count: int,
    symmetry_multiplicity: int,
) -> MrResourcePlan:
    """Derive one reviewed first-attempt tier from immutable workload facts."""

    values = (
        reflection_count,
        moving_atom_count,
        searched_copy_count,
        symmetry_multiplicity,
    )
    if any(isinstance(value, bool) or value < 1 for value in values):
        raise MrResourcePlanError("MR resource workload values must be positive")
    if isinstance(fixed_atom_count, bool) or fixed_atom_count < 0:
        raise MrResourcePlanError("MR fixed-atom count must be non-negative")
    if owner_kind not in {"mr_hypothesis", "component_execution_input"} or not owner_id:
        raise MrResourcePlanError("MR resource owner is invalid")
    symmetry = min(symmetry_multiplicity, MR_RESOURCE_SYMMETRY_CAP)
    coordinate_workload = moving_atom_count * searched_copy_count + fixed_atom_count
    score = reflection_count * coordinate_workload * symmetry
    tier = mr_resource_tier(score)
    resources = MR_RESOURCE_TIER_RESOURCES[tier]
    return MrResourcePlan.from_content(
        owner_kind=owner_kind,
        owner_id=owner_id,
        reflection_count=reflection_count,
        moving_atom_count=moving_atom_count,
        searched_copy_count=searched_copy_count,
        fixed_atom_count=fixed_atom_count,
        symmetry_multiplicity=symmetry_multiplicity,
        symmetry_cost_factor=symmetry,
        coordinate_atom_workload=coordinate_workload,
        workload_score=score,
        tier=tier,
        base_cpus=resources[0],
        base_memory_gb=resources[1],
        base_time_hours=resources[2],
    )


def resources_for_attempt(
    plan: MrResourcePlan,
    resource_attempt: int,
) -> MrAttemptResources:
    """Apply nf-core-style linear attempt scaling under reviewed hard caps."""

    if (
        isinstance(resource_attempt, bool)
        or resource_attempt < 1
        or resource_attempt > MR_RESOURCE_MAX_RETRIES + 1
    ):
        raise MrResourcePlanError("MR resource attempt is outside the retry policy")
    return MrAttemptResources(
        cpus=min(plan.base_cpus * resource_attempt, MR_RESOURCE_MAX_CPUS),
        memory_gb=min(
            plan.base_memory_gb * resource_attempt,
            MR_RESOURCE_MAX_MEMORY_GB,
        ),
        time_hours=min(
            plan.base_time_hours * resource_attempt,
            MR_RESOURCE_MAX_TIME_HOURS,
        ),
    )


def verify_mr_thread_allocation(
    *,
    plan: MrResourcePlan,
    resource_attempt: int,
    threads: int,
) -> MrAttemptResources:
    """Require the executed Phaser thread count to match its resource plan."""

    expected = resources_for_attempt(plan, resource_attempt)
    if isinstance(threads, bool) or threads != expected.cpus:
        raise MrResourcePlanError(
            "Phaser threads differ from the deterministic MR resource plan"
        )
    return expected


__all__ = [
    "MrAttemptResources",
    "MrResourcePlanError",
    "build_mr_resource_plan",
    "count_polymer_atoms",
    "resources_for_attempt",
    "verify_mr_thread_allocation",
]
