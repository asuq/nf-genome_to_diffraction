"""External Phenix installation, verification, and isolated execution."""

from genome_to_diffraction.phenix.installer import InstallRequest, install_phenix
from genome_to_diffraction.phenix.recovery import (
    RecoveryRequest,
    recover_failed_install,
)
from genome_to_diffraction.phenix.runtime import (
    REQUIRED_COMMANDS,
    MatthewsReferenceExecution,
    capture_matthews_reference_from_manifest,
    execute_from_manifest,
    inspect_runtime,
    validate_manifest_environment,
    verify_manifest,
)

__all__ = [
    "REQUIRED_COMMANDS",
    "InstallRequest",
    "MatthewsReferenceExecution",
    "RecoveryRequest",
    "capture_matthews_reference_from_manifest",
    "execute_from_manifest",
    "inspect_runtime",
    "install_phenix",
    "recover_failed_install",
    "validate_manifest_environment",
    "verify_manifest",
]
