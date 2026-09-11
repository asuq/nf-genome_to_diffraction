"""Strict transport for original RF inputs between independent Nextflow tasks.

These small context documents carry absolute original paths, not copied native
assets, new scientific options or execution authority. They live outside their
checksum-bound scientific bundles. Each CLI operation must reconstruct the
original request and use its existing full validator before acting; parsing a
context is not authentication, human approval or benchmark acceptance.

No scientific command runs here. Unknown fields and relative paths fail instead
of being silently ignored or interpreted against a different task directory.
Native result/receipt bytes and command paths remain untouched on transport.
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator
from tests.fixtures.ranking_four_arm_continuation import ReferenceContinuationInputs
from tests.fixtures.ranking_four_arm_plan import ReferencePlanInputs
from tests.fixtures.ranking_four_arm_prepared import ReferencePreparedInputs

from genome_to_diffraction.schemas.base import ContractModel, NonEmptyString


def _absolute(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("reference context requires an absolute original path")
    if ".." in path.parts:
        raise ValueError("reference context path contains parent traversal")
    return path


type OriginalPath = Annotated[Path, AfterValidator(_absolute)]


class ReferencePlanContext(ContractModel):
    """Original fixed-plan inputs; no track relabelling or truth arguments."""

    context_kind: Literal["rf-original-plan-context"] = "rf-original-plan-context"
    runner_root: OriginalPath
    database_manifest: OriginalPath
    software_lock: OriginalPath
    plan_path: OriginalPath

    def inputs(self) -> ReferencePlanInputs:
        """Reconstruct the existing planner request without changing any paths."""

        return ReferencePlanInputs(
            runner_root=self.runner_root,
            database_manifest=self.database_manifest,
            software_lock=self.software_lock,
        )


class ReferencePreparedContext(ContractModel):
    """The original preparation plus the separately owned reference manifest."""

    context_kind: Literal["rf-original-prepared-context"] = (
        "rf-original-prepared-context"
    )
    plan: ReferencePlanContext
    case_id: NonEmptyString
    catalogue_bundle: OriginalPath
    prepared_case: OriginalPath
    coordinate_stage: OriginalPath | None
    phenix_manifest: OriginalPath
    prepared_path: OriginalPath

    def inputs(self) -> ReferencePreparedInputs:
        """Preserve a genuine absent coordinate stage, not a guessed directory."""

        return ReferencePreparedInputs(
            plan_path=self.plan.plan_path,
            plan_inputs=self.plan.inputs(),
            case_id=self.case_id,
            catalogue_bundle=self.catalogue_bundle,
            prepared_case=self.prepared_case,
            coordinate_stage=self.coordinate_stage,
            phenix_manifest=self.phenix_manifest,
        )


class ReferenceReviewContext(ContractModel):
    """One prepared case and its exact original first-copy receipt union."""

    context_kind: Literal["rf-original-review-context"] = "rf-original-review-context"
    prepared: ReferencePreparedContext
    first_copy_receipts: tuple[OriginalPath, ...]
    reviews_path: OriginalPath

    def inputs(self) -> ReferenceContinuationInputs:
        """Reconstruct original continuation inputs; the original validator owns IDs."""

        return ReferenceContinuationInputs(
            prepared_path=self.prepared.prepared_path,
            prepared_inputs=self.prepared.inputs(),
            reviews_path=self.reviews_path,
            first_copy_receipts=self.first_copy_receipts,
        )


class ReferenceFinalistContext(ContractModel):
    """The complete copy union and original finalist manifest, without overrides."""

    context_kind: Literal["rf-original-finalist-context"] = (
        "rf-original-finalist-context"
    )
    review: ReferenceReviewContext
    copy_receipts: tuple[OriginalPath, ...]
    finalists_path: OriginalPath


class ReferenceIdentityContext(ContractModel):
    """Original per-arm identity inputs retained for the final exact-case join."""

    context_kind: Literal["rf-original-identity-context"] = (
        "rf-original-identity-context"
    )
    finalists: ReferenceFinalistContext
    refinement_receipts: tuple[OriginalPath, ...]
    identity_path: OriginalPath
