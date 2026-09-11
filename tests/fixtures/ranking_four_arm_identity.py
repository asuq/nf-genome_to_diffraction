"""Freeze per-arm truthless identity evidence after exact RF finalist completion.

Inputs are the original continuation/finalist binding and complete unique native
refinement receipt union. Each arm contributes only its own authenticated
advanced seeds to the unchanged derive_m6_identity_decision implementation.
The complete selected-MR row retains native metrics and supported copy count;
refinement and sequence scores do not become new identity thresholds. Zero,
one and multiple groups remain abstained, reported and ambiguous respectively.

Outputs freeze all receipt documents, per-arm rows/stages and identity decisions
under source/input/output hashes before any truth comparison. Empty admission
is distinct from scheduled no-hit. This assembler runs no external command and
is not a completed M6 track, operational leakage parent or human approval.
Reference-only content IDs are the cache contract. Changed, missing, duplicate
or foreign evidence fails closed; tests use synthetic external responses.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tests.fixtures.ranking_four_arm_advancement import _source_sha256
from tests.fixtures.ranking_four_arm_continuation import ReferenceContinuationInputs
from tests.fixtures.ranking_four_arm_finalists import validate_reference_finalists
from tests.fixtures.ranking_four_arm_first_copy import ReferenceFirstCopyReceipt
from tests.fixtures.ranking_four_arm_plan import _inventory
from tests.fixtures.ranking_four_arm_reference import AdmissionPrior, ReviewOrder
from tests.fixtures.ranking_four_arm_refinement import (
    ReferenceRefinementReceipt,
    ReferenceRefinementRequest,
    _finalist_bundle,
    _validate_reference_refinement_outputs,
)

from genome_to_diffraction.benchmarks.m6_identity import (
    M6IdentityDecision,
    derive_m6_identity_decision,
)
from genome_to_diffraction.benchmarks.m6_stages import M6StageInventory
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.refinement.brief import _read_jsonl
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.results import (
    NormalisedMrResult,
    SequenceGroupRecord,
)

_MANIFEST = "reference_case_identity.json"
_ARMS: tuple[tuple[str, AdmissionPrior, ReviewOrder], ...] = (
    ("A", "solvent_density", "prior_first"),
    ("B", "copy_weighted", "prior_first"),
    ("C", "solvent_density", "mr_led"),
    ("D", "copy_weighted", "mr_led"),
)


class ReferenceArmIdentity(ContractModel):
    """One arm's actual work, never the other arm's selected seed union."""

    arm: str
    admission_prior: AdmissionPrior
    review_order: ReviewOrder
    admission_status: Literal["no_scheduled_hypotheses", "materialised"]
    stages: M6StageInventory | None
    selected_seed_results: tuple[dict[str, object], ...]
    refinement_receipt_sha256: dict[str, Sha256Hex]
    identity_decision: M6IdentityDecision


class ReferenceCaseIdentity(ContractModel):
    """Complete reference receipt join, not native or truth-side acceptance."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["rf-arm-identity-v1"] = "rf-arm-identity-v1"
    execution_authority_kind: Literal["truth_blind_rf_reference"] = (
        "truth_blind_rf_reference"
    )
    human_approval_granted: Literal[False] = False
    case_identity_id: str
    case_id: str
    finalists_id: str
    source_sha256: dict[str, Sha256Hex]
    input_sha256: dict[str, Sha256Hex]
    output_sha256: dict[str, Sha256Hex]
    arms: tuple[
        ReferenceArmIdentity,
        ReferenceArmIdentity,
        ReferenceArmIdentity,
        ReferenceArmIdentity,
    ]


@dataclass(frozen=True)
class ReferenceIdentityInputs:
    """Original inputs plus complete unique copy/refinement task receipts."""

    continuation: ReferenceContinuationInputs
    copy_receipts: tuple[Path, ...]
    finalists_path: Path
    refinement_receipts: tuple[Path, ...]


def _arm_identity(
    *,
    case_id: str,
    arm: str,
    prior: AdmissionPrior,
    review: ReviewOrder,
    stages: M6StageInventory | None,
    groups: tuple[SequenceGroupRecord, ...],
    first_results: dict[str, NormalisedMrResult],
    refinements: dict[tuple[AdmissionPrior, str], ReferenceRefinementReceipt],
    receipt_digests: dict[tuple[AdmissionPrior, str], str],
) -> ReferenceArmIdentity:
    rows: list[dict[str, object]] = []
    digests: dict[str, str] = {}
    if stages is not None:
        for stage in stages.rows:
            if stage.advanced_rank is None:
                continue
            seed_id = stage.solution_id
            first = first_results[stage.hypothesis_id]
            receipt = refinements[(prior, seed_id)]
            task = receipt.task.task
            if task.sequence_group_id != stage.sequence_group_id:
                raise ValueError("reference arm seed changed its sequence group")
            rows.append(
                {
                    "seed_solution_id": seed_id,
                    "hypothesis_id": stage.hypothesis_id,
                    "sequence_group_id": stage.sequence_group_id,
                    "model_id": stage.model_id,
                    "expected_copy_count": stage.expected_copy_count,
                    "first_copy_execution_status": first.execution_status.value,
                    "first_copy_placed_count": first.placed_copy_count,
                    "llg": first.llg,
                    "tfz": first.tfz,
                    "best_supported_copy_count": task.input_copy_count,
                    "parent_retained": True,
                }
            )
            digests[seed_id] = receipt_digests[(prior, seed_id)]
    return ReferenceArmIdentity(
        arm=arm,
        admission_prior=prior,
        review_order=review,
        admission_status="no_scheduled_hypotheses"
        if stages is None
        else "materialised",
        stages=stages,
        selected_seed_results=tuple(rows),
        refinement_receipt_sha256=digests,
        identity_decision=derive_m6_identity_decision(
            case_id=case_id,
            selected_seed_results=rows,
            sequence_groups=groups,
        ),
    )


def _derive(
    inputs: ReferenceIdentityInputs,
) -> tuple[
    str, str, tuple[ReferenceArmIdentity, ...], dict[str, str], dict[str, bytes]
]:
    finalists = validate_reference_finalists(
        inputs.finalists_path, inputs.continuation, copy_receipts=inputs.copy_receipts
    )
    parsed = tuple(
        ReferenceRefinementReceipt.model_validate_json(path.read_bytes())
        for path in inputs.refinement_receipts
    )
    keys = tuple(
        (receipt.task.admission_prior, receipt.task.task.seed_solution_id)
        for receipt in parsed
    )
    expected = {
        (task.admission_prior, task.task.seed_solution_id): task
        for task in finalists.tasks
    }
    if (
        len(keys) != len(expected)
        or set(keys) != set(expected)
        or len({path.resolve(strict=True) for path in inputs.refinement_receipts})
        != len(expected)
    ):
        raise ValueError(
            "reference identity requires the exact unique refinement union"
        )
    digests = {"reference_finalists": sha256_file(inputs.finalists_path)}
    receipts: dict[tuple[AdmissionPrior, str], ReferenceRefinementReceipt] = {}
    receipt_digests: dict[tuple[AdmissionPrior, str], str] = {}
    files: dict[str, bytes] = {}
    for key, path, receipt in zip(
        keys, inputs.refinement_receipts, parsed, strict=True
    ):
        _validate_reference_refinement_outputs(
            path,
            ReferenceRefinementRequest(
                inputs=inputs.continuation,
                copy_receipts=inputs.copy_receipts,
                finalists_path=inputs.finalists_path,
                admission_prior=key[0],
                seed_solution_id=key[1],
                threads=receipt.threads,
                output_directory=path.parent,
            ),
            finalists_id=finalists.finalists_id,
            task=expected[key],
            bundle=_finalist_bundle(inputs.finalists_path, expected[key]),
        )
        relative = f"refinement_receipts/{key[0]}/{key[1]}.json"
        digests[relative] = sha256_file(path)
        receipt_digests[key] = digests[relative]
        receipts[key] = receipt
        files[relative] = path.read_bytes()
    groups = _read_jsonl(
        inputs.continuation.prepared_inputs.prepared_case / "all_sequence_groups.jsonl",
        SequenceGroupRecord,
        label="sequence group",
    )
    first = tuple(
        ReferenceFirstCopyReceipt.model_validate_json(path.read_bytes())
        for path in inputs.continuation.first_copy_receipts
    )
    first_by_hypothesis = {row.result.hypothesis_id: row.result for row in first}
    stages = {arm.arm: arm for pair in finalists.stages for arm in pair.arms}
    arms: list[ReferenceArmIdentity] = []
    for arm, prior, review in _ARMS:
        current = stages.get(arm)
        if (current is None) != (prior in finalists.empty_admission_priors):
            raise ValueError("reference identity lost an arm's actual stage inventory")
        if current is not None and current.review_order != review:
            raise ValueError("reference identity changed its paired review order")
        arms.append(
            _arm_identity(
                case_id=finalists.case_id,
                arm=arm,
                prior=prior,
                review=review,
                stages=current.stages if current is not None else None,
                groups=groups,
                first_results=first_by_hypothesis,
                refinements=receipts,
                receipt_digests=receipt_digests,
            )
        )
    # Revalidate the complete upstream union at both boundaries, not repeatedly
    # for every receipt within this single join. There is no persistent cache.
    if (
        finalists
        != validate_reference_finalists(
            inputs.finalists_path,
            inputs.continuation,
            copy_receipts=inputs.copy_receipts,
        )
        or sha256_file(inputs.finalists_path) != digests["reference_finalists"]
    ):
        raise ValueError("reference finalist union changed during identity assembly")
    return finalists.case_id, finalists.finalists_id, tuple(arms), digests, files


def _identity(manifest: ReferenceCaseIdentity) -> str:
    return content_id(
        "rfcaseidentity_",
        manifest.model_dump(mode="json", exclude={"case_identity_id"}),
    )


def build_reference_case_identity(
    inputs: ReferenceIdentityInputs, output: Path
) -> Path:
    """Freeze all four arms' completed evidence before any truth-side comparison."""

    if output.exists() or output.is_symlink():
        raise ValueError("reference case identity output must not already exist")
    output = output.resolve()
    source = _source_sha256()
    case_id, finalists_id, arms, digests, files = _derive(inputs)
    output.mkdir(parents=True, exist_ok=False)
    for relative, contents in files.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    manifest = ReferenceCaseIdentity(
        case_identity_id="pending",
        case_id=case_id,
        finalists_id=finalists_id,
        source_sha256=source,
        input_sha256=digests,
        output_sha256=_inventory(output, _MANIFEST),
        arms=(arms[0], arms[1], arms[2], arms[3]),
    )
    manifest = manifest.model_copy(update={"case_identity_id": _identity(manifest)})
    path = output / _MANIFEST
    atomic_write_json(path, manifest.model_dump(mode="json"))
    validate_reference_case_identity(path, inputs)
    return path


def validate_reference_case_identity(
    path: Path, inputs: ReferenceIdentityInputs
) -> ReferenceCaseIdentity:
    """Reconstruct per-arm identities from the complete original native receipts."""

    if path.is_symlink() or path.name != _MANIFEST:
        raise ValueError("reference identity requires its owned canonical manifest")
    path = path.resolve(strict=True)
    manifest = ReferenceCaseIdentity.model_validate_json(path.read_bytes())
    case_id, finalists_id, arms, digests, files = _derive(inputs)
    if (
        manifest.case_identity_id != _identity(manifest)
        or manifest.case_id != case_id
        or manifest.finalists_id != finalists_id
        or manifest.arms != arms
        or manifest.input_sha256 != digests
        or manifest.source_sha256 != _source_sha256()
        or manifest.output_sha256 != _inventory(path.parent, _MANIFEST)
        or set(manifest.output_sha256) != set(files)
        or any(
            (path.parent / relative).read_bytes() != contents
            for relative, contents in files.items()
        )
    ):
        raise ValueError(
            "reference identity arms, original receipts or outputs changed"
        )
    return manifest
