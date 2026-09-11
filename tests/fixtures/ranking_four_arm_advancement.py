"""Frozen-source RF reference authority for a paired known-control cohort.

This fixture alone supplies reference continuation policy; the installed
application never imports it or offers a reference ranking switch. Inputs are
the exact admission request, its hypotheses and a production-validated review.
Both declared review orders are rederived and each retains at most five seeds.
Their union permits one native chain per identical solution within this pair;
it never increases an individual arm's budget or creates a human approval.

The manifest binds all input digests and the reference/executor source files.
Changed source, joins, assets, scope or recommendations fail closed. No external
command runs here. Native fixed-profile/input provenance and full execution
receipts remain necessary; this manifest is authority, not acceptance evidence.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field
from tests.fixtures.ranking_four_arm_reference import AdmissionPrior, ReviewOrder
from tests.fixtures.ranking_four_arm_seeds import reference_seed_recommendations

from genome_to_diffraction.benchmarks.m6_advancement import (
    M6AdvancementRow,
    _object,
    _owned,
)
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.ranking.funnel import DiverseFirstCopyFunnelRequest
from genome_to_diffraction.schemas.base import ContractModel, PositiveInt, Sha256Hex

REFERENCE_CASE_IDS = ("M6C001", "M6C010", "M6C055", "M6C025", "M6C037")
REFERENCE_AUTHORITY_KIND = "truth_blind_rf_reference"
REFERENCE_COPY_ADAPTER = "phenix-add-copy-rf-reference-v1"
_PROTOCOL_SHA256 = "d735b3dfd9aae43df2f55a5fe5e25ad5e087eb933ffccd37eeb20f0519f159de"
_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_PATHS = (
    "tests/fixtures/ranking_four_arm_reference.py",
    "tests/fixtures/ranking_four_arm_admission.py",
    "tests/fixtures/ranking_four_arm_seeds.py",
    "tests/fixtures/ranking_four_arm_advancement.py",
    "tests/fixtures/ranking_four_arm_copy.py",
    "tests/fixtures/ranking_four_arm_stages.py",
    "tests/fixtures/ranking_four_arm_plan.py",
    "tests/fixtures/ranking_four_arm_materialisation.py",
    "tests/fixtures/ranking_four_arm_reviews.py",
    "tests/fixtures/ranking_four_arm_prepared.py",
    "tests/fixtures/ranking_four_arm_first_copy.py",
    "tests/fixtures/ranking_four_arm_continuation.py",
    "tests/fixtures/ranking_four_arm_finalists.py",
    "tests/fixtures/ranking_four_arm_refinement.py",
    "tests/fixtures/ranking_four_arm_identity.py",
    "src/genome_to_diffraction/refinement/brief.py",
    "src/genome_to_diffraction/benchmarks/m6_identity.py",
    "src/genome_to_diffraction/mr/phaser.py",
    "src/genome_to_diffraction/review/mr_seed.py",
    "src/genome_to_diffraction/model_registry/all_eligible.py",
    "src/genome_to_diffraction/mr/add_copy.py",
    "src/genome_to_diffraction/benchmarks/m6_advancement.py",
    "src/genome_to_diffraction/benchmarks/m6_stages.py",
    "src/genome_to_diffraction/benchmarks/m6_nextflow.py",
    "src/genome_to_diffraction/benchmarks/m6_runner.py",
    "src/genome_to_diffraction/benchmarks/m6_scientific.py",
    "src/genome_to_diffraction/benchmarks/m6_verification.py",
    "src/genome_to_diffraction/ranking/funnel.py",
    "src/genome_to_diffraction/review/priority.py",
    "benchmarks/m6/protocol.yaml",
    "pixi.lock",
)


class ReferenceRecommendationRow(ContractModel):
    """The original production row and independent reference annotations."""

    original: M6AdvancementRow
    review_rank: PositiveInt
    recommendation_rank: PositiveInt | None
    recommended: bool


class ReferenceArmRecommendations(ContractModel):
    """One declared comparison arm, preserving its complete ordered inventory."""

    arm: Literal["A", "B", "C", "D"]
    review_order: ReviewOrder
    rows: tuple[ReferenceRecommendationRow, ...] = Field(min_length=1, max_length=25)

    @property
    def recommended(self) -> tuple[M6AdvancementRow, ...]:
        return tuple(row.original for row in self.rows if row.recommended)


class ReferenceAdvancementManifest(ContractModel):
    """Reference-only union authority, never production or human approval."""

    schema_version: Literal["1.0"] = "1.0"
    advancement_id: str
    execution_authority_kind: Literal["truth_blind_rf_reference"] = (
        REFERENCE_AUTHORITY_KIND
    )
    policy: Literal["rf-paired-review-top-five-v1"] = "rf-paired-review-top-five-v1"
    human_approval_granted: Literal[False] = False
    seed_cap_per_arm: Literal[5] = 5
    first_copy_hypothesis_cap_per_arm: Literal[25] = 25
    crystal_id: str
    admission_prior: AdmissionPrior
    source_sha256: dict[str, Sha256Hex]
    input_sha256: dict[str, Sha256Hex]
    review_manifest: str
    arms: tuple[ReferenceArmRecommendations, ReferenceArmRecommendations]

    @property
    def recommended(self) -> tuple[M6AdvancementRow, ...]:
        """Execute identical solutions once while retaining separate arm lists."""

        by_solution: dict[str, M6AdvancementRow] = {}
        for arm in self.arms:
            for row in arm.recommended:
                if (
                    row.solution_id in by_solution
                    and by_solution[row.solution_id] != row
                ):
                    raise ValueError("reference arms disagree about a shared solution")
                by_solution[row.solution_id] = row
        return tuple(
            sorted(
                by_solution.values(),
                key=lambda row: (row.hypothesis_id, row.solution_id),
            )
        )


@dataclass(frozen=True)
class ValidatedReferenceAdvancement:
    """Rederived reference scope plus the authenticated original review."""

    manifest: ReferenceAdvancementManifest
    review_manifest: Path
    review_document: dict[str, object]


def _source_sha256() -> dict[str, str]:
    observed = {name: sha256_file(_SOURCE_ROOT / name) for name in _SOURCE_PATHS}
    if observed["benchmarks/m6/protocol.yaml"] != _PROTOCOL_SHA256:
        raise ValueError("reference comparison protocol differs from its frozen cohort")
    return observed


def _derive_manifest(
    request: DiverseFirstCopyFunnelRequest,
    *,
    hypotheses_jsonl: Path,
    review_manifest: Path,
    admission_prior: AdmissionPrior,
    output_manifest: Path,
) -> ReferenceAdvancementManifest:
    if (
        len(request.crystal_ids) != 1
        or request.crystal_ids[0] not in REFERENCE_CASE_IDS
    ):
        raise ValueError(
            "reference advancement is limited to the fixed known-control cohort"
        )
    source_sha256 = _source_sha256()
    root = output_manifest.resolve().parent
    relative_review = review_manifest.resolve(strict=True).relative_to(root).as_posix()
    review = _owned(root, relative_review)
    plans = tuple(
        reference_seed_recommendations(
            request,
            hypotheses_jsonl=hypotheses_jsonl,
            review_manifest=review,
            admission_prior=admission_prior,
            review_order=order,
        )
        for order in ("prior_first", "mr_led")
    )
    if plans[0].input_sha256 != plans[1].input_sha256:
        raise ValueError("paired reference inputs changed between review orders")
    labels: tuple[Literal["A", "B", "C", "D"], Literal["A", "B", "C", "D"]] = (
        ("A", "C") if admission_prior == "solvent_density" else ("B", "D")
    )
    inventories = tuple(
        ReferenceArmRecommendations(
            arm=label,
            review_order=plan.review_order,
            rows=tuple(
                ReferenceRecommendationRow.model_validate(asdict(row))
                for row in plan.rows
            ),
        )
        for label, plan in zip(labels, plans, strict=True)
    )
    if any(len(arm.recommended) > 5 for arm in inventories):
        raise ValueError("reference arm exceeds the five-seed budget")
    manifest = ReferenceAdvancementManifest(
        advancement_id="pending",
        crystal_id=request.crystal_ids[0],
        admission_prior=admission_prior,
        source_sha256=source_sha256,
        input_sha256=plans[0].input_sha256,
        review_manifest=relative_review,
        arms=(inventories[0], inventories[1]),
    )
    if _source_sha256() != source_sha256:
        raise ValueError("reference executable source changed during planning")
    return manifest.model_copy(
        update={
            "advancement_id": content_id(
                "rfadvance_",
                manifest.model_dump(mode="json", exclude={"advancement_id"}),
            )
        }
    )


def write_reference_advancement(
    request: DiverseFirstCopyFunnelRequest,
    *,
    hypotheses_jsonl: Path,
    review_manifest: Path,
    admission_prior: AdmissionPrior,
    output_manifest: Path,
) -> ReferenceAdvancementManifest:
    """Write only a new, fully rederived reference-pair execution authority."""

    if output_manifest.exists() or output_manifest.is_symlink():
        raise ValueError("reference advancement output must not already exist")
    manifest = _derive_manifest(
        request,
        hypotheses_jsonl=hypotheses_jsonl,
        review_manifest=review_manifest,
        admission_prior=admission_prior,
        output_manifest=output_manifest,
    )
    atomic_write_json(output_manifest, manifest.model_dump(mode="json"))
    return manifest


def validate_reference_advancement(
    manifest_path: Path,
    request: DiverseFirstCopyFunnelRequest,
    *,
    hypotheses_jsonl: Path,
) -> ValidatedReferenceAdvancement:
    """Authenticate source, complete paired recommendations and every input."""

    if manifest_path.is_symlink():
        raise ValueError("reference advancement must not be a symlink")
    path = manifest_path.resolve(strict=True)
    manifest = ReferenceAdvancementManifest.model_validate_json(path.read_bytes())
    if manifest.source_sha256 != _source_sha256():
        raise ValueError("reference advancement executable source changed")
    review = _owned(path.parent, manifest.review_manifest)
    expected = _derive_manifest(
        request,
        hypotheses_jsonl=hypotheses_jsonl,
        review_manifest=review,
        admission_prior=manifest.admission_prior,
        output_manifest=path,
    )
    if manifest != expected:
        raise ValueError("reference advancement differs from rederived paired evidence")
    return ValidatedReferenceAdvancement(manifest, review, _object(review))
