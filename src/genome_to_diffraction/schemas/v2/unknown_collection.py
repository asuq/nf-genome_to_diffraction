"""Checksum manifests for the local Phase III unknown-pass collector.

The manifests describe copied bytes only.  They do not infer candidate identity,
composition, validation truth, or a panel-wide scientific status.  Their cache keys
are the full RFC-8785 content identifiers ``crystal_manifest_id`` and
``cross_manifest_id``.
"""

from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.schemas.base import (
    ContractModel,
    OperatorIdentifier,
    Sha256Hex,
)
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract
from genome_to_diffraction.schemas.v2.execution import ExecutionIdentityIdentifier
from genome_to_diffraction.schemas.v2.review import (
    validate_phase3_review_relative_path,
)
from genome_to_diffraction.schemas.v2.unknown_assessment import (
    UnknownPass1AssessmentIdentifier,
    UnknownPass1PanelIdentifier,
    UnknownPass1ScientificStatus,
)
from genome_to_diffraction.status import ExecutionStatus

UnknownPass1CrystalManifestIdentifier = Annotated[
    str,
    Field(pattern=r"^unknownpass1crystalmanifest_[a-f0-9]{64}$"),
]
UnknownPass1CrossManifestIdentifier = Annotated[
    str,
    Field(pattern=r"^unknownpass1crossmanifest_[a-f0-9]{64}$"),
]


class UnknownPass1CollectedFileKind(StrEnum):
    """Typed role of one byte-for-byte retained collector file."""

    ASSESSMENT = "assessment"
    COMMAND = "command"
    RESULT = "result"
    EVIDENCE = "evidence"
    CRYSTAL_MANIFEST = "crystal_manifest"
    ASSESSMENT_INVENTORY = "assessment_inventory"
    PANEL_SUMMARY = "panel_summary"
    HTML_REPORT = "html_report"


class UnknownPass1CollectedFile(ContractModel):
    """One portable output file and its exact byte identity."""

    kind: UnknownPass1CollectedFileKind
    role: OperatorIdentifier
    relative_path: str = Field(min_length=1)
    sha256: Sha256Hex
    size_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_relative_path(self) -> Self:
        validate_phase3_review_relative_path(self.relative_path)
        return self


class UnknownPass1CrystalChecksumManifest(_ContentAddressedContract):
    """Complete copied-file inventory for one terminal crystal assessment."""

    _identity_field: ClassVar[str] = "crystal_manifest_id"
    _identity_prefix: ClassVar[str] = "unknownpass1crystalmanifest_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["unknown-pass1-local-collector-v2"]
    crystal_manifest_id: UnknownPass1CrystalManifestIdentifier
    owned_parent_run_id: OperatorIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    crystal_id: OperatorIdentifier
    assessment_id: UnknownPass1AssessmentIdentifier
    execution_status: ExecutionStatus
    scientific_status: UnknownPass1ScientificStatus
    files: tuple[UnknownPass1CollectedFile, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def _validate_files(self) -> Self:
        keys = tuple(
            (item.kind.value, item.role, item.relative_path) for item in self.files
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("crystal collector files must be unique and sorted")
        paths = tuple(item.relative_path for item in self.files)
        roles = tuple(item.role for item in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("crystal collector file paths must be unique")
        if len(roles) != len(set(roles)):
            raise ValueError("crystal collector file roles must be unique")
        required_prefix = f"crystals/{self.crystal_id}/"
        if any(not path.startswith(required_prefix) for path in paths):
            raise ValueError("crystal collector files must remain below their crystal")
        assessments = tuple(
            item
            for item in self.files
            if item.kind is UnknownPass1CollectedFileKind.ASSESSMENT
        )
        if len(assessments) != 1 or assessments[0].role != "assessment_record":
            raise ValueError(
                "crystal manifest requires one canonical assessment record"
            )
        return self


class UnknownPass1CrossChecksumManifest(_ContentAddressedContract):
    """Complete cross-crystal output inventory, excluding this self-manifest."""

    _identity_field: ClassVar[str] = "cross_manifest_id"
    _identity_prefix: ClassVar[str] = "unknownpass1crossmanifest_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["unknown-pass1-local-collector-v2"]
    cross_manifest_id: UnknownPass1CrossManifestIdentifier
    owned_parent_run_id: OperatorIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    panel_id: UnknownPass1PanelIdentifier
    crystal_manifest_ids: tuple[
        UnknownPass1CrystalManifestIdentifier,
        UnknownPass1CrystalManifestIdentifier,
        UnknownPass1CrystalManifestIdentifier,
    ]
    files: tuple[UnknownPass1CollectedFile, ...] = Field(min_length=7)
    interpretation_boundary: Literal[
        "exploratory_non_validation_assessment_mirror_only"
    ]

    @model_validator(mode="after")
    def _validate_cross_inventory(self) -> Self:
        if self.crystal_manifest_ids != tuple(sorted(set(self.crystal_manifest_ids))):
            raise ValueError(
                "cross manifest requires three unique sorted crystal manifests"
            )
        keys = tuple(
            (item.relative_path, item.kind.value, item.role) for item in self.files
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("cross collector files must be unique and path-sorted")
        paths = tuple(item.relative_path for item in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("cross collector file paths must be unique")
        required_kinds = {
            UnknownPass1CollectedFileKind.ASSESSMENT_INVENTORY,
            UnknownPass1CollectedFileKind.PANEL_SUMMARY,
            UnknownPass1CollectedFileKind.HTML_REPORT,
            UnknownPass1CollectedFileKind.CRYSTAL_MANIFEST,
        }
        if not required_kinds.issubset({item.kind for item in self.files}):
            raise ValueError("cross manifest omits a required generated output")
        return self


__all__ = [
    "UnknownPass1CollectedFile",
    "UnknownPass1CollectedFileKind",
    "UnknownPass1CrossChecksumManifest",
    "UnknownPass1CrystalChecksumManifest",
]
