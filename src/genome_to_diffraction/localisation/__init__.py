"""Offline Phase III protein-localisation adapter contracts."""

from genome_to_diffraction.localisation.adapters import (
    PSortbOutput,
    build_psortb_command,
    parse_psortb_terse,
    plan_deeptmhmm_invocation,
    run_psortb,
    write_sequence_group_fasta,
)
from genome_to_diffraction.localisation.contracts import (
    DeepTMHMMInvocationPlan,
    DeepTMHMMRuntimeContract,
    LocalisationOutcome,
    LocalisationResult,
    OfflineExecutionProvenance,
    PSortbCommandRecord,
    PSortbRuntimeContract,
    resolve_localisation_outcome,
)

__all__ = (
    "DeepTMHMMInvocationPlan",
    "DeepTMHMMRuntimeContract",
    "LocalisationOutcome",
    "LocalisationResult",
    "OfflineExecutionProvenance",
    "PSortbCommandRecord",
    "PSortbOutput",
    "PSortbRuntimeContract",
    "build_psortb_command",
    "parse_psortb_terse",
    "plan_deeptmhmm_invocation",
    "resolve_localisation_outcome",
    "run_psortb",
    "write_sequence_group_fasta",
)
