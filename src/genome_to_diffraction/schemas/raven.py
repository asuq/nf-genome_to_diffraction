"""Raven launch ownership shared by the source controller and installed readers."""

from pathlib import Path
from typing import Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from genome_to_diffraction.schemas.base import Sha256Hex

QualificationStage = Literal[
    "control-first-copy",
    "control-additional-copy",
    "control-refinement",
    "control-composition-attempts",
    "control-reopening",
    "m6-operational",
    "m6-leakage",
    "m6-comparison-initial",
    "m6-comparison-continuation",
    "unknown-single-component",
    "unknown-pass2",
]
QUALIFICATION_RUN_PATTERN = (
    "gtd-(?:"
    + "|".join(get_args(QualificationStage))
    + r")-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}-[a-f0-9]{8}"
)


class RavenQualificationLaunch(BaseModel):
    """Source-bound fixed qualification authority, distinct from identification."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["2.0"]
    run_id: str = Field(pattern=f"^{QUALIFICATION_RUN_PATTERN}$")
    owner_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    site_id: Literal["raven"]
    stage: QualificationStage
    account: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    source_tree: str = Field(pattern=r"^[a-f0-9]{40}$")
    nf_helper_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    pixi_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    pixi_lock_sha256: Sha256Hex
    source_root: Path
    input_root: Path
    input_id: str = Field(pattern=r"^ravenqualificationinputs_[a-f0-9]{64}$")
    phenix_manifest: Path
    phenix_manifest_sha256: Sha256Hex
    ci_evidence_sha256: Sha256Hex
    migration_run: Path
    migration_launch_sha256: Sha256Hex
    migration_state_sha256: Sha256Hex
    migration_assessment_sha256: Sha256Hex
    operational_parent_run: Path | None = None
    operational_precheck_sha256: Sha256Hex | None = None
    runner_archive: Path | None = None
    runner_archive_sha256: Sha256Hex | None = None
    parent_run_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]+$")
    sequence_parent_run_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    screen_parent_run: Path | None = None
    continuation_handoff_root: Path | None = None

    @model_validator(mode="after")
    def _validate_scope(self) -> Self:
        if not self.run_id.startswith(f"gtd-{self.stage}-"):
            raise ValueError("Raven run ID differs from the fixed stage")
        if self.source_commit[:12] != self.run_id.split("-")[-2]:
            raise ValueError("Raven run name and source commit differ")
        leakage = self.stage == "m6-leakage"
        m6_track = self.stage in {"m6-operational", "m6-leakage"}
        if (self.runner_archive is not None) != m6_track or (
            self.runner_archive_sha256 is not None
        ) != m6_track:
            raise ValueError("M6 requires its original checksum-bound runner archive")
        if (self.operational_parent_run is not None) != leakage or (
            self.operational_precheck_sha256 is not None
        ) != leakage:
            raise ValueError("only M6 leakage requires an operational parent")
        continuation = self.stage in {"unknown-single-component", "unknown-pass2"}
        if (self.parent_run_id is not None) != continuation:
            raise ValueError("unknown continuation requires an explicit parent")
        if (self.sequence_parent_run_id is not None) != (
            self.stage == "unknown-single-component"
        ):
            raise ValueError("single-component continuation requires both parents")
        if continuation and self.parent_run_id == self.sequence_parent_run_id:
            raise ValueError("screen and sequence parent runs must be distinct")
        single = self.stage == "unknown-single-component"
        if (self.screen_parent_run is not None) != single or (
            self.continuation_handoff_root is not None
        ) != single:
            raise ValueError("single-component continuation requires its exact handoff")
        return self
