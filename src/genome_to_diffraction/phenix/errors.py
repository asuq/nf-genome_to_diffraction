"""Expected failures at the external Phenix boundary."""

from collections.abc import Sequence

from genome_to_diffraction.schemas.manifests import PhenixCommandRecord
from genome_to_diffraction.status import InfrastructureError, ToolExecutionError


class PhenixError(InfrastructureError):
    """Base class for actionable Phenix installation/runtime failures."""


class UnsafePhenixPathError(PhenixError):
    """A requested installation or temporary path is unsafe."""


class UnsupportedPhenixPlatformError(PhenixError):
    """The host platform is not supported by the bootstrap policy."""


class PhenixInstallerChecksumError(PhenixError):
    """The user-supplied installer does not match its expected checksum."""


class PhenixInstallationExistsError(PhenixError):
    """A versioned installation or manifest already exists."""


class PhenixRuntimeVerificationError(PhenixError):
    """An installed Phenix runtime failed environment or command checks."""

    def __init__(
        self,
        message: str,
        *,
        commands: Sequence[PhenixCommandRecord] = (),
        detected_version: str | None = None,
    ) -> None:
        super().__init__(message)
        self.commands = tuple(commands)
        self.detected_version = detected_version


class PhenixInstallCommandError(ToolExecutionError):
    """The official Phenix installer returned a non-zero exit status."""

    def __init__(self, returncode: int, log_path: str) -> None:
        super().__init__(
            f"Phenix installer failed with exit status {returncode}; see {log_path}"
        )
        self.returncode = returncode
        self.log_path = log_path
