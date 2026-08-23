"""Focused final-metric gates for brief refinement."""

import pytest
from pydantic import ValidationError

from genome_to_diffraction.refinement.brief import _assess_refinement_completion
from genome_to_diffraction.schemas.results import (
    BriefRefinementResult,
    ExecutionStatus,
)

_SHA = "a" * 64


def test_zero_exit_without_final_r_values_is_failed_parse_evidence() -> None:
    completed, warnings = _assess_refinement_completion(
        returncode=0,
        required_assets_present=True,
        coefficients_valid=True,
        final_r_work=None,
        final_r_free=None,
    )

    assert completed is False
    assert warnings == ("phenix_refine_log_lacks_final_r_work_or_r_free",)


def test_zero_exit_requires_assets_coefficients_and_final_r_values() -> None:
    completed, warnings = _assess_refinement_completion(
        returncode=0,
        required_assets_present=True,
        coefficients_valid=True,
        final_r_work=0.24,
        final_r_free=0.28,
    )

    assert completed is True
    assert warnings == ()


@pytest.mark.parametrize("missing_metric", ("final_r_work", "final_r_free"))
def test_completed_refinement_contract_requires_both_final_r_values(
    missing_metric: str,
) -> None:
    fields: dict[str, object] = {
        "schema_version": "1.0",
        "refinement_id": "refine_test",
        "seed_solution_id": "seed_test",
        "sequence_group_id": "seq_test",
        "input_copy_count": 1,
        "tool_version": "2.1-6048",
        "execution_status": ExecutionStatus.COMPLETED_SUCCESS,
        "final_r_work": 0.24,
        "final_r_free": 0.28,
        "refined_model_path": "refined.pdb",
        "refined_model_sha256": _SHA,
        "refined_mtz_path": "refined.mtz",
        "refined_mtz_sha256": _SHA,
        "map_path": "2mfo-dfc.ccp4",
        "map_sha256": _SHA,
        "command_pointer": "command.json",
        "raw_log_pointer": "refine.log",
    }
    fields[missing_metric] = None

    with pytest.raises(
        ValidationError,
        match="completed refinement lacks final R values or model/map assets",
    ):
        BriefRefinementResult.model_validate(fields)


def test_failed_parse_refinement_may_retain_no_final_metrics() -> None:
    result = BriefRefinementResult(
        schema_version="1.0",
        refinement_id="refine_test",
        seed_solution_id="seed_test",
        sequence_group_id="seq_test",
        input_copy_count=1,
        tool_version="2.1-6048",
        execution_status=ExecutionStatus.FAILED_PARSE,
        command_pointer="command.json",
        raw_log_pointer="refine.log",
        warnings=("phenix_refine_log_lacks_final_r_work_or_r_free",),
    )

    assert result.final_r_work is None
    assert result.final_r_free is None
