"""Summarise every terminal result from one bounded partner-search plan."""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.mr.phaser import PhaserInputError
from genome_to_diffraction.schemas.results import (
    PartnerAttemptSummary,
    PartnerCandidateSelectionStatus,
    PartnerSearchPlan,
    PartnerSearchResult,
)
from genome_to_diffraction.status import ExecutionStatus


@dataclass(frozen=True)
class PartnerSummaryRequest:
    """One plan and every result directory emitted from its selected rows."""

    partner_plan_json: Path
    result_directories: tuple[Path, ...]
    output_json: Path


def summarize_partner_attempts(request: PartnerSummaryRequest) -> PartnerAttemptSummary:
    """Require a one-to-one selected-candidate/result inventory and summarise it."""

    plan_path = request.partner_plan_json.resolve(strict=True)
    try:
        plan = PartnerSearchPlan.model_validate_json(
            plan_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise PhaserInputError("partner search plan is invalid") from error
    plan_sha256 = sha256_file(plan_path)
    selected_ids = tuple(
        item.candidate_id
        for item in plan.candidates
        if item.selection_status is PartnerCandidateSelectionStatus.SELECTED
    )
    results: list[PartnerSearchResult] = []
    result_sha256: dict[str, str] = {}
    for directory in request.result_directories:
        path = directory.resolve(strict=True) / "partner_search_result.json"
        try:
            result = PartnerSearchResult.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as error:
            raise PhaserInputError(
                f"planned partner result is invalid: {path}"
            ) from error
        if (
            result.selection_plan_id != plan.plan_id
            or result.selection_plan_sha256 != plan_sha256
            or result.partner_candidate_id is None
        ):
            raise PhaserInputError("planned partner result provenance differs")
        if result.partner_candidate_id in result_sha256:
            raise PhaserInputError("planned partner candidate result is duplicated")
        result_sha256[result.partner_candidate_id] = sha256_file(path)
        results.append(result)
    results.sort(key=lambda item: item.partner_candidate_id or "")
    statuses = Counter(item.execution_status for item in results)
    identity = {
        "plan_id": plan.plan_id,
        "plan_sha256": plan_sha256,
        "result_sha256": result_sha256,
    }
    try:
        summary = PartnerAttemptSummary(
            schema_version="1.0",
            summary_id=content_id("partnersummary_", identity),
            plan_id=plan.plan_id,
            plan_sha256=plan_sha256,
            candidate_count=plan.candidate_count,
            selected_attempt_count=plan.selected_attempt_count,
            result_count=len(results),
            completed_hit_count=statuses[ExecutionStatus.COMPLETED_HIT],
            completed_no_hit_count=statuses[ExecutionStatus.COMPLETED_NO_HIT],
            failed_tool_execution_count=statuses[ExecutionStatus.FAILED_TOOL_EXECUTION],
            failed_parse_count=statuses[ExecutionStatus.FAILED_PARSE],
            deferred_cap_count=plan.deferred_cap_count,
            unsearchable_candidate_count=plan.unsearchable_candidate_count,
            selected_candidate_ids=selected_ids,
            result_candidate_ids=tuple(
                item.partner_candidate_id or "" for item in results
            ),
            result_search_ids=tuple(item.search_id for item in results),
        )
    except ValidationError as error:
        raise PhaserInputError("partner attempt inventory is incomplete") from error
    output = request.output_json.absolute()
    if output.exists():
        raise PhaserInputError(f"partner summary output already exists: {output}")
    atomic_write_json(output, summary.model_dump(mode="json"))
    return summary
