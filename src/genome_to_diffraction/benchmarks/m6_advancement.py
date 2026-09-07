"""Truth-blind M6 advancement authority over a real production review package.

The runner selects at most five inspectable, packed, interpreted copy states in
production review order. This is declared benchmark policy, never a human review
decision. Its content identity binds the frozen protocol, policy, case task,
scheduled hypotheses, production package and exact selected seeds/copy budgets.
Validation rechecks those dependencies before shared additional-copy execution.
No external tool is run here. Missing, changed or cross-scope evidence fails.
Focused tests cover production selection, authority mutation and mixed authority.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from genome_to_diffraction.benchmarks.m6_scientific import m6_track_case_ids
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.review.mr_seed import (
    MrSeedReviewError,
    mr_seed_copy_state,
    validate_mr_seed_review_evidence,
)
from genome_to_diffraction.schemas.base import ContractModel, NonEmptyString, Sha256Hex
from genome_to_diffraction.schemas.io import load_json_document, parse_json_document
from genome_to_diffraction.schemas.results import MrHypothesis, NormalisedMrResult
from genome_to_diffraction.status import ExecutionStatus

M6_FROZEN_PROTOCOL_SHA256 = (
    "c3fa4c04b78c7aae8d6da41f5f0c6dad47a6cea3d09cc76d285f512d58e95854"
)
M6_ADVANCEMENT_POLICY = {
    "policy_id": "m6_production_review_top_five_v1",
    "scope": "m6_bounded_validation",
    "maximum_first_copy_tasks": 25,
    "maximum_advanced_seeds": 5,
    "order": "production_mr_seed_review",
    "eligibility": "inspectable_packed_interpreted_copy_state",
    "authority_kind": "benchmark_policy",
    "human_approval": False,
}


class M6AuthorityFile(ContractModel):
    """One package-owned dependency with an exact content identity."""

    path: NonEmptyString
    sha256: Sha256Hex


class M6BenchmarkAdvancementAuthority(ContractModel):
    """Explicit bounded benchmark selection, distinct from human approval."""

    schema_version: Literal["1.0"]
    authority_kind: Literal["benchmark_policy"]
    authority_id: NonEmptyString
    policy_id: Literal["m6_production_review_top_five_v1"]
    policy_sha256: Sha256Hex
    protocol_sha256: Sha256Hex
    execution_scope: Literal["m6_bounded_validation"]
    case_id: Annotated[str, Field(pattern=r"^M6C[0-9]{3}$")]
    dependencies: dict[str, M6AuthorityFile]
    selected_solution_ids: tuple[str, ...] = Field(min_length=1, max_length=5)
    additional_copy_budget_by_seed: dict[str, Annotated[int, Field(ge=0)]]
    human_approval: Literal[False] = False

    @model_validator(mode="after")
    def _validate_policy_and_identity(self) -> Self:
        if self.case_id not in set(m6_track_case_ids("operational")) | set(
            m6_track_case_ids("leakage")
        ):
            raise ValueError("M6 advancement case is outside the frozen protocol")
        if self.protocol_sha256 != M6_FROZEN_PROTOCOL_SHA256:
            raise ValueError("M6 advancement uses another frozen protocol")
        if self.policy_sha256 != canonical_digest(M6_ADVANCEMENT_POLICY):
            raise ValueError("M6 advancement policy checksum differs")
        if set(self.dependencies) != {
            "case_task",
            "case_plan",
            "hypotheses",
            "review_package",
        }:
            raise ValueError("M6 advancement dependency inventory differs")
        if len(self.selected_solution_ids) != len(set(self.selected_solution_ids)):
            raise ValueError("M6 advancement duplicates a selected seed")
        if set(self.additional_copy_budget_by_seed) != set(self.selected_solution_ids):
            raise ValueError("M6 advancement copy budgets differ from selected seeds")
        if self.authority_id != content_id(
            "m6advance_", self.model_dump(mode="json", exclude={"authority_id"})
        ):
            raise ValueError("M6 advancement authority identity differs")
        return self


def _owned(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("M6 advancement dependency is not package-owned")
    candidate = root / path
    resolved = candidate.resolve(strict=True)
    if (
        candidate.is_symlink()
        or not resolved.is_file()
        or not resolved.is_relative_to(root.resolve(strict=True))
    ):
        raise ValueError("M6 advancement dependency is not a regular owned file")
    return resolved


def _object(path: Path) -> dict[str, object]:
    document = load_json_document(path)
    if not isinstance(document, dict):
        raise ValueError("M6 advancement requires a JSON object")
    return cast(dict[str, object], document)


def m6_review_seed_selection(
    *, package_manifest: Path, hypotheses_jsonl: Path, case_id: str
) -> tuple[tuple[dict[str, object], ...], dict[str, int]]:
    """Retain all eligible states in the authenticated production review order."""

    try:
        validate_mr_seed_review_evidence(
            package_manifest=package_manifest,
            hypotheses_jsonl=hypotheses_jsonl,
            crystal_id=case_id,
            progress=False,
        )
    except MrSeedReviewError as error:
        raise ValueError(f"M6 production review is invalid: {error}") from error
    hypotheses = {
        row.hypothesis_id: row
        for row in (
            MrHypothesis.model_validate(
                parse_json_document(line, label=hypotheses_jsonl)
            )
            for line in hypotheses_jsonl.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    document = _object(package_manifest)
    items = cast(list[dict[str, object]], document["items"])
    eligible: list[dict[str, object]] = []
    copy_budgets: dict[str, int] = {}
    for item in items:
        hypothesis = hypotheses[cast(str, item["hypothesis_id"])]
        if hypothesis.copy_number_to_search != 1:
            raise ValueError(
                "M6 benchmark advancement requires initial one-copy requests"
            )
        assets = cast(dict[str, str], item["copied_assets"])
        result_path = _owned(package_manifest.parent, assets["normalised_result"])
        result = NormalisedMrResult.model_validate(
            parse_json_document(
                result_path.read_text(encoding="utf-8").strip(), label=result_path
            )
        )
        if (
            item["inspectable_solution"] is True
            and result.execution_status
            in {ExecutionStatus.COMPLETED_HIT, ExecutionStatus.COMPLETED_NO_HIT}
            and result.packing_summary.get("top_solution_packed") is True
            and mr_seed_copy_state(hypothesis, result)
            in {"requested_copies_observed", "coupled_tncs"}
        ):
            eligible.append(item)
            copy_budgets[cast(str, item["solution_id"])] = max(
                0, hypothesis.copy_count_expected - result.placed_copy_count
            )
    return tuple(eligible), copy_budgets


def write_m6_advancement_authority(
    *, case_id: str, dependencies: dict[str, Path], output: Path
) -> M6BenchmarkAdvancementAuthority:
    """Freeze production's first five eligible states without a human decision."""

    eligible, budgets = m6_review_seed_selection(
        package_manifest=dependencies["review_package"],
        hypotheses_jsonl=dependencies["hypotheses"],
        case_id=case_id,
    )
    selected = tuple(cast(str, row["solution_id"]) for row in eligible[:5])
    payload = {
        "schema_version": "1.0",
        "authority_kind": "benchmark_policy",
        "policy_id": M6_ADVANCEMENT_POLICY["policy_id"],
        "policy_sha256": canonical_digest(M6_ADVANCEMENT_POLICY),
        "protocol_sha256": M6_FROZEN_PROTOCOL_SHA256,
        "execution_scope": "m6_bounded_validation",
        "case_id": case_id,
        "dependencies": {
            name: {
                "path": str(path.relative_to(output.parent)),
                "sha256": sha256_file(path),
            }
            for name, path in dependencies.items()
        },
        "selected_solution_ids": selected,
        "additional_copy_budget_by_seed": {
            seed_id: budgets[seed_id] for seed_id in selected
        },
        "human_approval": False,
    }
    authority = M6BenchmarkAdvancementAuthority.model_validate(
        {**payload, "authority_id": content_id("m6advance_", payload)}
    )
    atomic_write_json(output, authority.model_dump(mode="json"))
    validate_m6_advancement_authority(
        output, hypotheses_jsonl=dependencies["hypotheses"]
    )
    return authority


def validate_m6_advancement_authority(
    manifest_path: Path, *, hypotheses_jsonl: Path
) -> tuple[M6BenchmarkAdvancementAuthority, Path]:
    """Verify scope, exact dependencies and the production-recommended selection."""

    authority = M6BenchmarkAdvancementAuthority.model_validate_json(
        manifest_path.read_bytes()
    )
    paths: dict[str, Path] = {}
    for role, dependency in authority.dependencies.items():
        path = _owned(manifest_path.parent, dependency.path)
        if sha256_file(path) != dependency.sha256:
            raise ValueError(f"M6 advancement {role} checksum differs")
        paths[role] = path
    if sha256_file(hypotheses_jsonl) != authority.dependencies["hypotheses"].sha256:
        raise ValueError("M6 advancement hypotheses differ from the execution input")
    task = _object(paths["case_task"])
    plan = _object(paths["case_plan"])
    if (
        task.get("case_id") != authority.case_id
        or plan.get("case_id") != authority.case_id
    ):
        raise ValueError("M6 advancement case ownership differs")
    track = task.get("track")
    if track not in {
        "operational",
        "leakage",
    } or authority.case_id not in m6_track_case_ids(
        cast(Literal["operational", "leakage"], track)
    ):
        raise ValueError("M6 advancement case and frozen track differ")
    identifiers = plan.get("hypothesis_ids")
    if (
        plan.get("adapter_version") != "m6-nextflow-case-v3-production-admission"
        or not isinstance(identifiers, list)
        or any(
            not isinstance(identifier, str) or not identifier
            for identifier in identifiers
        )
        or not 1 <= len(identifiers) <= 25
        or len(identifiers) != len(set(identifiers))
        or plan.get("hypothesis_count") != len(identifiers)
    ):
        raise ValueError("M6 advancement lacks its bounded production admission plan")
    hypotheses = tuple(
        MrHypothesis.model_validate(parse_json_document(line, label=hypotheses_jsonl))
        for line in hypotheses_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if tuple(row.hypothesis_id for row in hypotheses) != tuple(identifiers):
        raise ValueError("M6 advancement scheduled hypothesis inventory differs")
    eligible, budgets = m6_review_seed_selection(
        package_manifest=paths["review_package"],
        hypotheses_jsonl=paths["hypotheses"],
        case_id=authority.case_id,
    )
    selected = tuple(cast(str, item["solution_id"]) for item in eligible[:5])
    if (
        authority.selected_solution_ids != selected
        or authority.additional_copy_budget_by_seed
        != {seed_id: budgets[seed_id] for seed_id in selected}
    ):
        raise ValueError("M6 advancement differs from the production recommendation")
    return authority, paths["review_package"]
