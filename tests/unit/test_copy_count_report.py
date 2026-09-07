"""Tests for retained-candidate copy-count comparison."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.mr import (
    CopyCountReportRequest,
    PhaserInputError,
    build_copy_count_report,
)
from genome_to_diffraction.schemas.results import (
    COPY_COUNT_UNASSESSED_REVIEW_FLAGS,
    AdditionalCopyResult,
)
from genome_to_diffraction.status import ExecutionStatus

SEED = "sol_" + "a" * 64
CHILD_TWO = "copystate_" + "b" * 64
CHILD_THREE = "copystate_" + "c" * 64
REVIEW = "rev_" + "d" * 64
HYPOTHESIS = "mrhyp_" + "e" * 64
GROUP = "seq_" + "f" * 64


def _result(
    copy_number: int,
    *,
    supported: bool,
    parent: str,
    child: str | None,
) -> AdditionalCopyResult:
    return AdditionalCopyResult(
        schema_version="1.0",
        attempt_id="addcopy_" + str(copy_number) * 64,
        review_id=REVIEW,
        seed_solution_id=SEED,
        parent_solution_id=parent,
        child_solution_id=child,
        hypothesis_id=HYPOTHESIS,
        sequence_group_id=GROUP,
        parent_copy_count=copy_number - 1,
        attempted_copy_number=copy_number,
        expected_copy_count=3,
        execution_status=(
            ExecutionStatus.COMPLETED_HIT
            if supported
            else ExecutionStatus.COMPLETED_NO_HIT
        ),
        llg=80.0 + copy_number if supported else None,
        llg_delta_from_parent=20.0 if supported else None,
        tfz=7.0 if supported else None,
        phaser_placement_count=copy_number if supported else 0,
        top_solution_packed=supported,
        additional_copy_supported=supported,
        best_supported_copy_count=copy_number if supported else copy_number - 1,
        output_coordinate_path="PHASER.1.pdb" if supported else None,
        output_coordinate_sha256="1" * 64 if supported else None,
        output_mtz_path="PHASER.1.mtz" if supported else None,
        output_mtz_sha256="2" * 64 if supported else None,
        raw_log_pointer="PHASER.log",
        command_pointer="phaser_command.json",
    )


def _write(path: Path, records: list[AdditionalCopyResult]) -> None:
    path.write_text(
        "".join(f"{canonical_json_text(item)}\n" for item in records),
        encoding="utf-8",
    )


def test_copy_report_records_expected_count_reached(tmp_path: Path) -> None:
    results = tmp_path / "results.jsonl"
    _write(
        results,
        [
            _result(2, supported=True, parent=SEED, child=CHILD_TWO),
            _result(3, supported=True, parent=CHILD_TWO, child=CHILD_THREE),
        ],
    )

    output = build_copy_count_report(
        CopyCountReportRequest(results, tmp_path / "report", progress=False)
    )

    assessment = output.assessments[0]
    assert assessment.expected_copy_count == 3
    assert assessment.best_supported_copy_count == 3
    assert assessment.reached_expected_copy_count is True
    assert assessment.final_placement_count == 3
    assert assessment.independent_completeness_status == "not_assessed"
    assert assessment.residual_content_status == "not_assessed"
    assert assessment.review_flags == COPY_COUNT_UNASSESSED_REVIEW_FLAGS
    manifest = json.loads(output.manifest_json.read_text(encoding="utf-8"))
    assert manifest["all_candidates_retained"] is True
    assert manifest["expected_count_reached_count"] == 1
    assert manifest["expected_count_proves_completeness"] is False
    assert "both remain not assessed" in output.report_markdown.read_text()


def test_copy_report_marks_unsupported_stop_without_absence_claim(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results.jsonl"
    _write(
        results,
        [
            _result(2, supported=True, parent=SEED, child=CHILD_TWO),
            _result(3, supported=False, parent=CHILD_TWO, child=None),
        ],
    )

    assessment = build_copy_count_report(
        CopyCountReportRequest(results, tmp_path / "report", progress=False)
    ).assessments[0]

    assert assessment.best_supported_copy_count == 2
    assert assessment.reached_expected_copy_count is False
    assert assessment.failed_addition_proves_absence is False
    assert "copy_absence_not_proven" in assessment.review_flags
    assert assessment.final_placement_count == 0
    assert assessment.independent_completeness_status == "not_assessed"
    assert assessment.residual_content_status == "not_assessed"


@pytest.mark.parametrize(
    ("first_attempt", "expected", "supported"),
    ((3, 3, True), (4, 6, False)),
)
def test_copy_report_starts_from_the_reviewed_multicopy_seed(
    tmp_path: Path,
    first_attempt: int,
    expected: int,
    supported: bool,
) -> None:
    result = _result(
        first_attempt,
        supported=supported,
        parent=SEED,
        child=CHILD_THREE if supported else None,
    ).model_copy(update={"expected_copy_count": expected})
    results = tmp_path / "results.jsonl"
    _write(results, [result])
    assessment = build_copy_count_report(
        CopyCountReportRequest(results, tmp_path / "report", progress=False)
    ).assessments[0]
    assert assessment.attempted_transition_count == 1
    assert assessment.best_supported_copy_count == 3
    assert assessment.reached_expected_copy_count is supported
    assert assessment.independent_completeness_status == "not_assessed"
    assert assessment.residual_content_status == "not_assessed"


def test_copy_report_keeps_failed_native_placement_missing_and_parent_supported(
    tmp_path: Path,
) -> None:
    result = _result(2, supported=False, parent=SEED, child=None).model_copy(
        update={"execution_status": ExecutionStatus.FAILED_TOOL_EXECUTION}
    )
    results = tmp_path / "results.jsonl"
    _write(results, [result])
    assessment = build_copy_count_report(
        CopyCountReportRequest(results, tmp_path / "report", progress=False)
    ).assessments[0]
    assert assessment.best_supported_copy_count == 1
    assert assessment.final_placement_count is None
    assert assessment.final_execution_status is ExecutionStatus.FAILED_TOOL_EXECUTION
    assert assessment.independent_completeness_status == "not_assessed"
    assert assessment.residual_content_status == "not_assessed"
    with pytest.raises(ValueError, match="observed final copy count"):
        type(assessment).model_validate(
            {**assessment.model_dump(), "final_execution_status": "completed_hit"}
        )


def test_copy_assessment_identity_binds_attempt_result_evidence(tmp_path: Path) -> None:
    result = _result(3, supported=True, parent=SEED, child=CHILD_THREE)
    results = tmp_path / "results.jsonl"
    _write(results, [result])
    first = build_copy_count_report(
        CopyCountReportRequest(results, tmp_path / "first", progress=False)
    ).assessments[0]
    _write(results, [result.model_copy(update={"llg": 90.0})])
    changed = build_copy_count_report(
        CopyCountReportRequest(results, tmp_path / "changed", progress=False)
    ).assessments[0]
    assert changed.assessment_id != first.assessment_id


def test_copy_report_rejects_broken_parent_child_lineage(tmp_path: Path) -> None:
    results = tmp_path / "results.jsonl"
    _write(
        results,
        [
            _result(2, supported=True, parent=SEED, child=CHILD_TWO),
            _result(3, supported=True, parent=CHILD_THREE, child=CHILD_THREE),
        ],
    )

    with pytest.raises(PhaserInputError, match="lineage breaks"):
        build_copy_count_report(
            CopyCountReportRequest(results, tmp_path / "report", progress=False)
        )
