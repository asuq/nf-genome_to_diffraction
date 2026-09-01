"""Path-free ownership record for one completed Phase III run."""

from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.schemas.base import (
    ContractModel,
    OperatorIdentifier,
    Sha256Hex,
    UtcTimestamp,
)
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract
from genome_to_diffraction.schemas.v2.execution import (
    ExecutionIdentityIdentifier,
    GitObjectHex,
)
from genome_to_diffraction.schemas.v2.review import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewPackageIdentifier,
)

OwnedRunRegistryIdentifier = Annotated[
    str,
    Field(pattern=r"^phase3ownedrun_[a-f0-9]{64}$"),
]


class PhaseIIIOwnedReviewPackage(ContractModel):
    """One package whose own manifest is the exact per-file checksum allow-list."""

    checkpoint: PhaseIIIReviewCheckpoint
    crystal_id: OperatorIdentifier
    review_package_id: PhaseIIIReviewPackageIdentifier
    review_package_manifest_sha256: Sha256Hex
    package_content_sha256: Sha256Hex


class PhaseIIIOwnedRunRegistry(_ContentAddressedContract):
    """Canonical registration of one completed local Phase III parent run."""

    _identity_field: ClassVar[str] = "owned_run_registry_id"
    _identity_prefix: ClassVar[str] = "phase3ownedrun_"

    schema_version: Literal["2.0"]
    adapter_version: Literal[
        "phase3-owned-run-registry-v1",
        "phase3-owned-run-registry-v2",
    ]
    owned_run_registry_id: OwnedRunRegistryIdentifier
    run_id: OperatorIdentifier
    profile: OperatorIdentifier
    phase: OperatorIdentifier
    completed_at: UtcTimestamp
    execution_status: Literal["completed_success"]
    source_commit: GitObjectHex
    source_tree: GitObjectHex
    execution_identity_id: ExecutionIdentityIdentifier
    execution_identity_sha256: Sha256Hex
    execution_identity_size_bytes: int = Field(gt=0)
    packages: tuple[PhaseIIIOwnedReviewPackage, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_packages(self) -> Self:
        if self.adapter_version == "phase3-owned-run-registry-v1" and any(
            item.checkpoint
            not in {
                PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
                PhaseIIIReviewCheckpoint.A_SEED,
            }
            for item in self.packages
        ):
            raise ValueError(
                "owned-run registry v1 supports crystallographic and A-seed "
                "packages only"
            )
        keys = tuple(
            (item.crystal_id, item.checkpoint.value, item.review_package_id)
            for item in self.packages
        )
        if keys != tuple(sorted(keys)):
            raise ValueError("owned review packages must be unique and sorted")
        lookups = tuple((crystal, checkpoint) for crystal, checkpoint, _ in keys)
        if len(lookups) != len(set(lookups)):
            raise ValueError(
                "owned run cannot register two packages for one crystal/checkpoint"
            )
        package_ids = tuple(package_id for _, _, package_id in keys)
        if len(package_ids) != len(set(package_ids)):
            raise ValueError("owned run cannot register one package more than once")
        return self


__all__ = [
    "PhaseIIIOwnedReviewPackage",
    "PhaseIIIOwnedRunRegistry",
]
