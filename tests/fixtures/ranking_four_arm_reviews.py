"""Freeze the exact first-copy union, then build authentic paired RF reviews.

Inputs are source-bound materialised cohorts, their original admission request,
source records and one completed bundle per emitted MR task. Output inventories
retain every supplied file and normalised result, then partition those genuine
results into the exact original cohorts. Production review construction and
validation are reused; only the explicitly reference-labelled paired authority
is written. Empty admission receives no manufactured review or authority.
This fixture executes no tools, applies no human approval and reads no truth.
Source/input/result/output hashes bind reuse. Duplicate, missing, foreign,
changed or symlinked results fail closed. Tests use explicit synthetic MR, not
native scientific acceptance. Native command/resource provenance remains a
separate fixed-route acceptance requirement.
"""

import shutil
from pathlib import Path
from typing import Literal

from tests.fixtures.ranking_four_arm_advancement import (
    _source_sha256,
    validate_reference_advancement,
    write_reference_advancement,
)
from tests.fixtures.ranking_four_arm_materialisation import (
    ReferenceMaterialisation,
    validate_reference_materialisation,
)
from tests.fixtures.ranking_four_arm_plan import _inventory
from tests.fixtures.ranking_four_arm_reference import AdmissionPrior

from genome_to_diffraction.benchmarks.m6_nextflow import _phaser_output
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.ranking import DiverseFirstCopyFunnelRequest
from genome_to_diffraction.review.mr_seed import (
    MrSeedReviewRequest,
    build_mr_seed_review,
)
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex

_MANIFEST = "reference_reviews.json"


class ReferenceCohortReview(ContractModel):
    """A review/authority pair, absent only for genuinely empty admission."""

    admission_prior: AdmissionPrior
    status: Literal["reviewed", "no_scheduled_hypotheses"]
    review_manifest: str | None
    advancement_manifest: str | None


class ReferenceReviews(ContractModel):
    """Frozen MR evidence and paired reference reviews, never native acceptance."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["rf-first-copy-review-union-v1"] = (
        "rf-first-copy-review-union-v1"
    )
    execution_authority_kind: Literal["truth_blind_rf_reference"] = (
        "truth_blind_rf_reference"
    )
    human_approval_granted: Literal[False] = False
    reviews_id: str
    source_sha256: dict[str, Sha256Hex]
    input_sha256: dict[str, Sha256Hex]
    first_copy_result_sha256: dict[str, dict[str, Sha256Hex]]
    output_sha256: dict[str, Sha256Hex]
    cohorts: tuple[ReferenceCohortReview, ReferenceCohortReview]


def _results(
    materialisation: ReferenceMaterialisation, roots: tuple[Path, ...]
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    seen: set[Path] = set()
    for root in roots:
        if root.is_symlink() or not root.is_dir():
            raise ValueError("reference MR result requires an owned directory")
        resolved = root.resolve(strict=True)
        hypothesis_id = _phaser_output(resolved).result.hypothesis_id
        if resolved in seen or hypothesis_id in paths:
            raise ValueError("reference MR result union contains duplicate evidence")
        seen.add(resolved)
        paths[hypothesis_id] = resolved
    if set(paths) != {task.hypothesis.hypothesis_id for task in materialisation.tasks}:
        raise ValueError("reference MR result union has missing or foreign hypotheses")
    return {key: paths[key] for key in sorted(paths)}


def _cohort_review(prior: AdmissionPrior, *, empty: bool) -> ReferenceCohortReview:
    return ReferenceCohortReview(
        admission_prior=prior,
        status="no_scheduled_hypotheses" if empty else "reviewed",
        review_manifest=None
        if empty
        else f"{prior}/review/mr_seed_review_manifest.json",
        advancement_manifest=None if empty else f"{prior}/reference_advancement.json",
    )


def _identity(manifest: ReferenceReviews) -> str:
    return content_id(
        "rfreviews_", manifest.model_dump(mode="json", exclude={"reviews_id"})
    )


def build_reference_reviews(
    materialisation_path: Path,
    admission: DiverseFirstCopyFunnelRequest,
    *,
    source_records_jsonl: Path,
    first_copy_results: tuple[Path, ...],
    output: Path,
) -> Path:
    """Freeze the exact result union, then build both real cohort review pairs."""

    if output.exists() or output.is_symlink():
        raise ValueError("reference review output must not already exist")
    materialisation = validate_reference_materialisation(
        materialisation_path, admission
    )
    source = _source_sha256()
    inputs = {
        "materialisation_manifest": sha256_file(materialisation_path),
        "source_records": sha256_file(source_records_jsonl),
    }
    originals = _results(materialisation, first_copy_results)
    original_digests = {key: _inventory(root, None) for key, root in originals.items()}
    root = output.resolve()
    results = root / "first-copy-results"
    results.mkdir(parents=True)
    for key, original in originals.items():
        destination = results / f"first_copy_phaser_{key}"
        shutil.copytree(original, destination)
        if _inventory(destination, None) != original_digests[key]:
            raise ValueError("reference MR evidence changed during freezing")
    atomic_write_json(root / "frozen_first_copy_inventory.json", original_digests)
    cohorts: list[ReferenceCohortReview] = []
    for cohort in materialisation.cohorts:
        prior = cohort.admission_prior
        record = _cohort_review(prior, empty=not cohort.hypotheses)
        cohorts.append(record)
        if not cohort.hypotheses:
            continue
        directory = root / prior
        directory.mkdir()
        aggregate = directory / "first_copy_results.jsonl"
        atomic_write_text(
            aggregate,
            "".join(
                canonical_json_text(
                    _phaser_output(
                        results / f"first_copy_phaser_{row.hypothesis_id}"
                    ).result
                )
                + "\n"
                for row in cohort.hypotheses
            ),
        )
        funnel = materialisation_path.resolve(strict=True).parent / prior
        hypotheses = funnel / "mr_hypotheses.jsonl"
        review = build_mr_seed_review(
            MrSeedReviewRequest(
                hypotheses_jsonl=hypotheses,
                results_jsonl=aggregate,
                result_root=results,
                funnel_manifest=funnel / "funnel_manifest.json",
                sequence_groups_jsonl=admission.sequence_groups_jsonl,
                source_records_jsonl=source_records_jsonl,
                matthews_hypotheses_jsonl=admission.matthews_hypotheses_jsonl,
                pipeline_config=admission.pipeline_config,
                output_directory=directory / "review",
                progress=False,
            )
        )
        write_reference_advancement(
            admission,
            hypotheses_jsonl=hypotheses,
            review_manifest=review.manifest_json,
            admission_prior=prior,
            output_manifest=directory / "reference_advancement.json",
        )
    if (
        original_digests
        != {key: _inventory(path, None) for key, path in originals.items()}
        or inputs["materialisation_manifest"] != sha256_file(materialisation_path)
        or inputs["source_records"] != sha256_file(source_records_jsonl)
        or source != _source_sha256()
    ):
        raise ValueError("reference review original evidence or source changed")
    manifest = ReferenceReviews(
        reviews_id="pending",
        source_sha256=source,
        input_sha256=inputs,
        first_copy_result_sha256=original_digests,
        output_sha256=_inventory(root, _MANIFEST),
        cohorts=(cohorts[0], cohorts[1]),
    )
    manifest = manifest.model_copy(update={"reviews_id": _identity(manifest)})
    path = root / _MANIFEST
    atomic_write_json(path, manifest.model_dump(mode="json"))
    validate_reference_reviews(
        path, materialisation_path, admission, source_records_jsonl=source_records_jsonl
    )
    return path


def validate_reference_reviews(
    path: Path,
    materialisation_path: Path,
    admission: DiverseFirstCopyFunnelRequest,
    *,
    source_records_jsonl: Path,
) -> ReferenceReviews:
    """Authenticate the frozen result union and both rederived review authorities."""

    root = path.resolve(strict=True).parent
    if path.is_symlink() or path.name != _MANIFEST:
        raise ValueError("reference review requires its owned canonical manifest")
    materialisation = validate_reference_materialisation(
        materialisation_path, admission
    )
    manifest = ReferenceReviews.model_validate_json(path.read_bytes())
    if (
        manifest.reviews_id != _identity(manifest)
        or manifest.source_sha256 != _source_sha256()
        or manifest.input_sha256
        != {
            "materialisation_manifest": sha256_file(materialisation_path),
            "source_records": sha256_file(source_records_jsonl),
        }
        or manifest.output_sha256 != _inventory(root, _MANIFEST)
    ):
        raise ValueError(
            "reference reviews identity, source, inputs or outputs changed"
        )
    results = _results(materialisation, tuple((root / "first-copy-results").iterdir()))
    if manifest.first_copy_result_sha256 != {
        key: _inventory(directory, None) for key, directory in results.items()
    }:
        raise ValueError("reference frozen MR result inventory changed")
    for cohort, record in zip(materialisation.cohorts, manifest.cohorts, strict=True):
        prior = cohort.admission_prior
        if record != _cohort_review(prior, empty=not cohort.hypotheses):
            raise ValueError("reference review cohort changed its admission identity")
        if record.advancement_manifest is None:
            continue
        hypotheses = (
            materialisation_path.resolve(strict=True).parent
            / prior
            / "mr_hypotheses.jsonl"
        )
        validated = validate_reference_advancement(
            root / record.advancement_manifest,
            admission,
            hypotheses_jsonl=hypotheses,
        )
        if validated.manifest.admission_prior != prior:
            raise ValueError("reference review authority changed its paired cohort")
    return manifest
