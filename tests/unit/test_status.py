"""Unit tests for explicit status and error semantics."""

from genome_to_diffraction.status import (
    ExecutionStatus,
    FoundationOnlyError,
    GenomeToDiffractionError,
    ScientificStatus,
)


def test_no_hit_is_not_an_execution_failure() -> None:
    assert ExecutionStatus.COMPLETED_NO_HIT.value == "completed_no_hit"
    assert not ExecutionStatus.COMPLETED_NO_HIT.value.startswith("failed_")


def test_scientific_and_execution_status_values_are_disjoint() -> None:
    execution_values = {status.value for status in ExecutionStatus}
    scientific_values = {status.value for status in ScientificStatus}
    assert execution_values.isdisjoint(scientific_values)


def test_foundation_error_is_a_pipeline_error() -> None:
    assert issubclass(FoundationOnlyError, GenomeToDiffractionError)
