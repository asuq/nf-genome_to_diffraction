"""Immutable Phase III execution and cache identity.

The identity binds raw catalogue, annotation, MTZ, database, source-tree,
environment, tool, and adapter content before any Phase III task is scheduled.
It contains no machine path and performs no I/O; staging code must checksum the
actual files and construct these records before Nextflow receives an item.
"""

from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.schemas.base import NonEmptyString, Sha256Hex
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract

GitObjectHex = Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
ExecutionIdentityIdentifier = Annotated[
    str,
    Field(pattern=r"^phase3exec_[a-f0-9]{64}$"),
]

_REQUIRED_PHENIX_COMMANDS = frozenset(
    {
        "phenix.maps",
        "phenix.phaser",
        "phenix.process_predicted_model",
        "phenix.refine",
        "phenix.reflection_file_converter",
        "phenix.sequence_from_map",
        "phenix.xtriage",
    }
)


class ExecutionArtifactIdentity(_ContentAddressedContract):
    """One path-free raw input or prepared database inventory identity."""

    _identity_field: ClassVar[str] = "artifact_id"
    _identity_prefix: ClassVar[str] = "execartifact_"

    schema_version: Literal["2.0"]
    artifact_id: Annotated[str, Field(pattern=r"^execartifact_[a-f0-9]{64}$")]
    scope: Literal["catalogue", "crystal", "database"]
    owner_id: NonEmptyString
    role: NonEmptyString
    sha256: Sha256Hex
    size_bytes: int = Field(ge=0)
    release_or_source: NonEmptyString | None = None


class ExecutionToolIdentity(_ContentAddressedContract):
    """One exact executable and adapter semantic identity."""

    _identity_field: ClassVar[str] = "tool_identity_id"
    _identity_prefix: ClassVar[str] = "exectool_"

    schema_version: Literal["2.0"]
    tool_identity_id: Annotated[str, Field(pattern=r"^exectool_[a-f0-9]{64}$")]
    name: NonEmptyString
    version: NonEmptyString
    executable_sha256: Sha256Hex
    adapter_version: NonEmptyString


class PhaseIIIExecutionIdentity(_ContentAddressedContract):
    """Complete path-free cache identity shared by Phase III task items."""

    _identity_field: ClassVar[str] = "execution_identity_id"
    _identity_prefix: ClassVar[str] = "phase3exec_"

    schema_version: Literal["2.0"]
    execution_identity_id: ExecutionIdentityIdentifier
    source_commit: GitObjectHex
    source_tree: GitObjectHex
    nf_helper_commit: GitObjectHex
    pixi_lock_sha256: Sha256Hex
    execution_policy_sha256: Sha256Hex
    catalogue_artifacts: tuple[ExecutionArtifactIdentity, ...] = Field(min_length=1)
    crystal_artifacts: tuple[ExecutionArtifactIdentity, ...] = Field(min_length=1)
    database_artifacts: tuple[ExecutionArtifactIdentity, ...] = Field(min_length=1)
    tools: tuple[ExecutionToolIdentity, ...] = Field(min_length=1)
    adapter_versions: tuple[tuple[NonEmptyString, NonEmptyString], ...] = Field(
        min_length=1
    )
    remote_sequence_submission: Literal[False] = False
    compute_network_access: Literal[False] = False

    @model_validator(mode="after")
    def _validate_complete_identity(self) -> Self:
        artifact_groups = (
            ("catalogue", self.catalogue_artifacts),
            ("crystal", self.crystal_artifacts),
            ("database", self.database_artifacts),
        )
        for scope, artifacts in artifact_groups:
            if any(artifact.scope != scope for artifact in artifacts):
                raise ValueError(f"{scope} artifact inventory contains another scope")
            sort_keys = tuple(
                (item.owner_id, item.role, item.artifact_id) for item in artifacts
            )
            logical_keys = tuple((item.owner_id, item.role) for item in artifacts)
            if sort_keys != tuple(sorted(sort_keys)):
                raise ValueError(f"{scope} artifacts must be unique and sorted")
            if len(logical_keys) != len(set(logical_keys)):
                raise ValueError(f"{scope} artifact owner/role values must be unique")

        catalogue_roles: dict[str, set[str]] = {}
        for artifact in self.catalogue_artifacts:
            catalogue_roles.setdefault(artifact.owner_id, set()).add(artifact.role)
        for owner_id, roles in catalogue_roles.items():
            if "proteome_faa" not in roles:
                raise ValueError(f"catalogue {owner_id} lacks raw proteome_faa")
            if not roles.intersection(
                {"annotation_gff", "annotation_gbff", "protein_locus_map"}
            ):
                raise ValueError(f"catalogue {owner_id} lacks raw annotation identity")

        crystal_roles: dict[str, set[str]] = {}
        for artifact in self.crystal_artifacts:
            crystal_roles.setdefault(artifact.owner_id, set()).add(artifact.role)
        if any("mtz" not in roles for roles in crystal_roles.values()):
            raise ValueError("every crystal must bind its raw MTZ")

        tool_keys = tuple((tool.name, tool.tool_identity_id) for tool in self.tools)
        if tool_keys != tuple(sorted(tool_keys)):
            raise ValueError("tool identities must be unique and sorted")
        tool_names = tuple(tool.name for tool in self.tools)
        if len(tool_names) != len(set(tool_names)):
            raise ValueError("tool names must be unique")
        missing_phenix = sorted(_REQUIRED_PHENIX_COMMANDS - set(tool_names))
        if missing_phenix:
            raise ValueError(
                "execution identity lacks required Phenix tools: "
                + ", ".join(missing_phenix)
            )

        if self.adapter_versions != tuple(sorted(self.adapter_versions)):
            raise ValueError("adapter versions must be sorted")
        adapter_names = tuple(name for name, _ in self.adapter_versions)
        if len(adapter_names) != len(set(adapter_names)):
            raise ValueError("adapter names must be unique")
        return self


__all__ = [
    "ExecutionArtifactIdentity",
    "ExecutionToolIdentity",
    "PhaseIIIExecutionIdentity",
]
