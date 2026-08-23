"""Focused final-metric and sequence-parse gates for brief refinement."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from genome_to_diffraction.refinement.brief import (
    T12InputError,
    _assess_refinement_completion,
    _classify_sequence_output,
    _prepare_attempt_directory,
)
from genome_to_diffraction.schemas.results import (
    BriefRefinementResult,
    ExecutionStatus,
    SequenceGroupRecord,
)

_SHA = "a" * 64


def test_t12_attempt_directory_refuses_stale_outputs(tmp_path: Path) -> None:
    attempt = _prepare_attempt_directory(tmp_path / "attempt")
    assert attempt.is_dir()
    (attempt / "brief_refine_001.pdb").write_text("stale\n", encoding="utf-8")

    with pytest.raises(T12InputError, match="output directory is not empty"):
        _prepare_attempt_directory(attempt)


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


def test_unknown_sequence_from_map_group_becomes_typed_parse_failure() -> None:
    sequence = "ACDE"
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    group_id = f"seq_{digest}"
    group = SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=group_id,
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        mass_method="unit_test",
        residue_policy="unit_test",
        source_record_count=1,
    )
    unknown_id = f"seq_{'f' * 64}"
    text = f"Score for sequence 1 (4 residues): 12.5 (>{unknown_id})\n"

    status, candidates, best, mean, sd, best_z, warnings = _classify_sequence_output(
        text,
        refinement_id="refine_test",
        groups={group_id: group},
        crosswalk={group_id: (("source_01",), ("locus_01",))},
    )

    assert status is ExecutionStatus.FAILED_PARSE
    assert candidates == ()
    assert best is None
    assert mean is None
    assert sd is None
    assert best_z is None
    assert warnings == ("sequence_from_map_output_failed_catalogue_validation",)
