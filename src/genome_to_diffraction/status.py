"""Shared execution statuses and explicit foundation error classes."""

from enum import StrEnum


class ExecutionStatus(StrEnum):
    """Normalised execution outcomes for adapters and workflow stages."""

    COMPLETED_SUCCESS = "completed_success"
    COMPLETED_HIT = "completed_hit"
    COMPLETED_NO_HIT = "completed_no_hit"
    COMPLETED_WARNING = "completed_warning"
    SKIPPED_POLICY = "skipped_policy"
    SKIPPED_INELIGIBLE = "skipped_ineligible"
    FAILED_INPUT_CONTRACT = "failed_input_contract"
    FAILED_TOOL_EXECUTION = "failed_tool_execution"
    FAILED_PARSE = "failed_parse"
    FAILED_INFRASTRUCTURE = "failed_infrastructure"


class ScientificStatus(StrEnum):
    """Terminal scientific outcomes approved for the single-species prototype."""

    CREDIBLE_SINGLE_COMPONENT_SOLUTION = "credible_single_component_solution"
    CREDIBLE_PARTIAL_SOLUTION = "credible_partial_solution_residual_content_present"
    NO_CREDIBLE_MR_SOLUTION = "candidate_shortlist_no_credible_mr_solution"
    SUSPECTED_MULTI_COMPONENT = "suspected_multi_component_crystal"
    SUSPECTED_FRAGMENT_MISMATCH = "suspected_fragment_or_construct_mismatch"
    NO_SUPPORTED_CATALOGUE_CANDIDATE = "no_supported_catalogue_candidate"
    MTZ_OR_SYMMETRY_PROBLEM = "mtz_or_symmetry_problem"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class GenomeToDiffractionError(Exception):
    """Base class for expected pipeline errors."""


class InputContractError(GenomeToDiffractionError):
    """Input data did not satisfy a declared contract."""


class ToolExecutionError(GenomeToDiffractionError):
    """An external tool failed to execute correctly."""


class ResultParseError(GenomeToDiffractionError):
    """An external-tool result could not be parsed safely."""


class InfrastructureError(GenomeToDiffractionError):
    """The execution environment could not satisfy a runtime requirement."""


class TransientInfrastructureError(InfrastructureError):
    """A classified temporary infrastructure failure permits one scheduler retry."""


class FoundationOnlyError(GenomeToDiffractionError):
    """A caller requested scientific work before its milestone is implemented."""
