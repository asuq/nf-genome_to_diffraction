"""Truth-blind M6 continuation authority, never a human MR approval.

Inputs are the production MR review, its exact hypotheses and Matthews rows.
The complete, production-ordered inventory and the first five eligible states
are written with checksums and a content identity. Validation rederives the
shared ordering and eligibility before an additional-copy child may execute.
No external command, truth record, provider rank or new score threshold is used.
Malformed joins, stale assets and policy/cap changes fail closed. Tests exercise
production parity, selected packing/copy evidence and authority tampering.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.review.mr_seed import validate_mr_seed_review_evidence
from genome_to_diffraction.review.priority import (
    REVIEW_PRIORITY_POLICY,
    FirstCopyReviewEvidence,
    review_priority_key,
)
from genome_to_diffraction.schemas.base import ContractModel, PositiveInt, Sha256Hex
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MrHypothesis,
    NormalisedMrResult,
)
from genome_to_diffraction.status import ExecutionStatus

M6_ADVANCEMENT_POLICY = "m6-truth-blind-production-review-top-five-v1"
M6_SEED_CAP = 5


class M6AdvancementRow(ContractModel):
    """One scheduled hypothesis, whether eligible, recommended or deferred."""

    solution_id: str
    hypothesis_id: str
    sequence_group_id: str
    model_id: str
    expected_copy_count: PositiveInt
    first_copy_placed_count: int = Field(ge=0)
    review_priority_rank: PositiveInt
    recommendation_rank: PositiveInt | None
    advancement_disposition: Literal["recommended", "deferred_seed_cap", "ineligible"]
    selected_packing_state: str
    copy_state: str
    llg: float | None
    tfz: float | None


class M6AdvancementManifest(ContractModel):
    """Bounded benchmark execution authority with no human approval claim."""

    schema_version: Literal["1.0"] = "1.0"
    advancement_id: str
    execution_authority_kind: Literal["truth_blind_m6_benchmark"] = (
        "truth_blind_m6_benchmark"
    )
    policy: Literal["m6-truth-blind-production-review-top-five-v1"] = (
        M6_ADVANCEMENT_POLICY
    )
    review_priority_policy: Literal["selected-packing-copy-mr-matthews-v1"] = (
        REVIEW_PRIORITY_POLICY
    )
    seed_cap: Literal[5] = 5
    first_copy_hypothesis_cap: Literal[25] = 25
    human_approval_granted: Literal[False] = False
    crystal_id: str
    hypotheses_sha256: Sha256Hex
    review_manifest: str
    review_manifest_sha256: Sha256Hex
    matthews_hypotheses: str
    matthews_hypotheses_sha256: Sha256Hex
    rows: tuple[M6AdvancementRow, ...] = Field(min_length=1, max_length=25)

    @property
    def recommended(self) -> tuple[M6AdvancementRow, ...]:
        return tuple(
            row for row in self.rows if row.advancement_disposition == "recommended"
        )


@dataclass(frozen=True)
class ValidatedM6Advancement:
    """Validated benchmark authority and the actual production review package."""

    manifest: M6AdvancementManifest
    review_manifest: Path
    review_document: dict[str, object]


def _records[T: BaseModel](path: Path, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _object(path: Path) -> dict[str, object]:
    document = load_json_document(path)
    if not isinstance(document, dict):
        raise ValueError("M6 advancement requires a JSON object")
    return document


def _owned(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("M6 advancement asset must be package-relative")
    candidate = root / relative
    resolved = candidate.resolve(strict=True)
    if (
        candidate.is_symlink()
        or not resolved.is_file()
        or not resolved.is_relative_to(root)
    ):
        raise ValueError("M6 advancement asset escapes its package")
    return resolved


def _review_rows(
    review_manifest: Path, hypotheses_jsonl: Path, matthews_jsonl: Path, crystal_id: str
) -> tuple[M6AdvancementRow, ...]:
    solution_ids = validate_mr_seed_review_evidence(
        package_manifest=review_manifest,
        hypotheses_jsonl=hypotheses_jsonl,
        crystal_id=crystal_id,
    )
    document = _object(review_manifest)
    identity = cast(dict[str, object], document["package_identity"])
    inputs = cast(dict[str, object], identity["input_sha256"])
    if document.get("review_priority_policy") != REVIEW_PRIORITY_POLICY or inputs.get(
        "matthews_hypotheses"
    ) != sha256_file(matthews_jsonl):
        raise ValueError("M6 review policy or Matthews checksum changed")
    hypotheses = {
        row.hypothesis_id: row for row in _records(hypotheses_jsonl, MrHypothesis)
    }
    matthews_rows = _records(matthews_jsonl, MatthewsHypothesis)
    matthews = {row.hypothesis_id: row for row in matthews_rows}
    if len(matthews) != len(matthews_rows):
        raise ValueError("duplicate M6 Matthews hypothesis")
    evidence_rows: list[tuple[str, FirstCopyReviewEvidence]] = []
    root = review_manifest.resolve(strict=True).parent
    for rank, item in enumerate(cast(list[dict[str, object]], document["items"]), 1):
        hypothesis = hypotheses[cast(str, item["hypothesis_id"])]
        copied = cast(dict[str, object], item["copied_assets"])
        results = _records(
            _owned(root, copied["normalised_result"]), NormalisedMrResult
        )
        if len(results) != 1:
            raise ValueError("M6 review requires exactly one result per hypothesis")
        result = results[0]
        solution_identity = cast(dict[str, object], item["solution_identity"])
        if (
            result.hypothesis_id != hypothesis.hypothesis_id
            or solution_identity.get("result_sha256") != canonical_digest(result)
            or hypothesis.copy_number_to_search != 1
        ):
            raise ValueError("M6 review result or initial-copy identity differs")
        matthews_id = hypothesis.priority_features.get("matthews_hypothesis_id")
        if not isinstance(matthews_id, str) or matthews_id not in matthews:
            raise ValueError("M6 hypothesis lacks its Matthews record")
        prior = matthews[matthews_id]
        if (
            prior.crystal_id != crystal_id
            or prior.sequence_group_id != hypothesis.sequence_group_id
            or prior.copy_count != hypothesis.copy_count_expected
        ):
            raise ValueError("M6 Matthews hypothesis join differs")
        inspectable = (
            result.execution_status
            in {ExecutionStatus.COMPLETED_HIT, ExecutionStatus.COMPLETED_NO_HIT}
            and "solution_coordinate" in copied
            and "output_mtz" in copied
        )
        evidence = FirstCopyReviewEvidence(hypothesis, result, prior, inspectable)
        if (
            item.get("rank") != rank
            or item.get("review_priority_rank") != rank
            or item.get("inspectable_solution") != inspectable
            or item.get("selected_packing_state") != evidence.packing_state
            or item.get("copy_state") != evidence.copy_state
        ):
            raise ValueError("M6 review display evidence differs from typed evidence")
        evidence_rows.append((cast(str, item["solution_id"]), evidence))
    ordered = sorted(evidence_rows, key=lambda pair: review_priority_key(pair[1]))
    if tuple(solution_id for solution_id, _ in ordered) != solution_ids:
        raise ValueError("M6 review order differs from production policy")
    rows: list[M6AdvancementRow] = []
    eligible_count = 0
    for rank, (solution_id, evidence) in enumerate(ordered, 1):
        hypothesis, result = evidence.hypothesis, evidence.result
        eligible = (
            result.execution_status is ExecutionStatus.COMPLETED_HIT
            and evidence.inspectable
            and evidence.packing_state == "zero_clashes"
            and evidence.copy_state in {"literal", "tncs_coupled_pair"}
            and 1 <= result.placed_copy_count <= hypothesis.copy_count_expected
        )
        if eligible:
            eligible_count += 1
        rows.append(
            M6AdvancementRow(
                solution_id=solution_id,
                hypothesis_id=hypothesis.hypothesis_id,
                sequence_group_id=hypothesis.sequence_group_id,
                model_id=hypothesis.model_id,
                expected_copy_count=hypothesis.copy_count_expected,
                first_copy_placed_count=result.placed_copy_count,
                review_priority_rank=rank,
                recommendation_rank=eligible_count if eligible else None,
                advancement_disposition=(
                    "recommended"
                    if eligible and eligible_count <= M6_SEED_CAP
                    else "deferred_seed_cap"
                    if eligible
                    else "ineligible"
                ),
                selected_packing_state=evidence.packing_state,
                copy_state=evidence.copy_state,
                llg=result.llg,
                tfz=result.tfz,
            )
        )
    return tuple(rows)


def write_m6_advancement(
    *,
    review_manifest: Path,
    hypotheses_jsonl: Path,
    matthews_jsonl: Path,
    crystal_id: str,
    output_manifest: Path,
) -> M6AdvancementManifest:
    """Record production recommendations as bounded benchmark-only authority."""

    root = output_manifest.resolve().parent
    manifest = M6AdvancementManifest(
        advancement_id="pending",
        crystal_id=crystal_id,
        hypotheses_sha256=sha256_file(hypotheses_jsonl),
        review_manifest=review_manifest.resolve(strict=True)
        .relative_to(root)
        .as_posix(),
        review_manifest_sha256=sha256_file(review_manifest),
        matthews_hypotheses=matthews_jsonl.resolve(strict=True)
        .relative_to(root)
        .as_posix(),
        matthews_hypotheses_sha256=sha256_file(matthews_jsonl),
        rows=_review_rows(
            review_manifest, hypotheses_jsonl, matthews_jsonl, crystal_id
        ),
    )
    manifest = manifest.model_copy(
        update={
            "advancement_id": content_id(
                "m6advance_",
                manifest.model_dump(mode="json", exclude={"advancement_id"}),
            )
        }
    )
    atomic_write_json(output_manifest, manifest.model_dump(mode="json"))
    return manifest


def validate_m6_advancement(
    manifest_path: Path, *, hypotheses_jsonl: Path
) -> ValidatedM6Advancement:
    """Rederive benchmark continuation scope without manufacturing approvals."""

    path = manifest_path.resolve(strict=True)
    manifest = M6AdvancementManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if manifest.advancement_id != content_id(
        "m6advance_", manifest.model_dump(mode="json", exclude={"advancement_id"})
    ) or manifest.hypotheses_sha256 != sha256_file(hypotheses_jsonl):
        raise ValueError("M6 advancement identity or hypothesis checksum changed")
    review = _owned(path.parent, manifest.review_manifest)
    matthews = _owned(path.parent, manifest.matthews_hypotheses)
    if (
        sha256_file(review) != manifest.review_manifest_sha256
        or sha256_file(matthews) != manifest.matthews_hypotheses_sha256
    ):
        raise ValueError("M6 advancement input checksum changed")
    if manifest.rows != _review_rows(
        review, hypotheses_jsonl, matthews, manifest.crystal_id
    ):
        raise ValueError("M6 advancement inventory differs from production evidence")
    return ValidatedM6Advancement(manifest, review, _object(review))
