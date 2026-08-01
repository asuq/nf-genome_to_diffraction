"""External Phenix installation, verification, and isolated execution."""

from genome_to_diffraction.phenix.installer import InstallRequest, install_phenix
from genome_to_diffraction.phenix.runtime import (
    REQUIRED_COMMANDS,
    execute_from_manifest,
    inspect_runtime,
    validate_manifest_environment,
    verify_manifest,
)

__all__ = [
    "REQUIRED_COMMANDS",
    "InstallRequest",
    "execute_from_manifest",
    "inspect_runtime",
    "install_phenix",
    "validate_manifest_environment",
    "verify_manifest",
]
