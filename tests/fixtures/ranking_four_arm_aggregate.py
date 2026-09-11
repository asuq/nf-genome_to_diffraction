"""Freeze the exact five completed RF cases before any truth-side comparison.

Inputs are the original plan context, one original prepared context per fixed
case and one completed identity context per materialised case. Every original
scientific boundary is authenticated again. Preflight-blocked and no-model
preparations retain their genuine early result, with no invented admission,
review, copy or identity evidence. Materialised empty admission and scheduled
no-hit retain their original four-arm identity/stage records.

The output freezes transport contexts, prepared/identity manifests and all
identity-owned output bytes under an explicit source/input/output inventory.
Full upstream native assets, commands, traces and resource provenance remain
separate required collector evidence. No external tool runs; metadata joins
never schedule science. Missing, duplicated, foreign or changed cases fail.
Reference content IDs bind the cache contract. This is neither native/M6
acceptance, a leakage parent nor a human decision, and it reads no truth labels.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field
from tests.fixtures.ranking_four_arm_advancement import _source_sha256
from tests.fixtures.ranking_four_arm_context import (
    ReferenceIdentityContext,
    ReferencePlanContext,
    ReferencePreparedContext,
)
from tests.fixtures.ranking_four_arm_identity import (
    ReferenceIdentityInputs,
    validate_reference_case_identity,
)
from tests.fixtures.ranking_four_arm_plan import _inventory, validate_reference_plan
from tests.fixtures.ranking_four_arm_prepared import (
    PreparedStatus,
    validate_reference_prepared_case,
)

from genome_to_diffraction.benchmarks.m6_advancement import _owned
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex

_MANIFEST = "reference_run.json"


@dataclass(frozen=True)
class ReferenceRunInputs:
    """Only original reference contexts, with no truth or scientific overrides."""

    plan_context: Path
    prepared_contexts: tuple[Path, ...]
    identity_contexts: tuple[Path, ...]


class ReferenceRunCase(ContractModel):
    """One authentic completion, without coercing early termination to identity."""

    case_id: str
    preparation_status: PreparedStatus
    production_early_outcome: str | None
    prepared_id: str
    case_identity_id: str | None


class ReferenceRun(ContractModel):
    """Frozen exact-case evidence; native provenance and truth assessment follow."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["rf-exact-five-completion-v1"] = (
        "rf-exact-five-completion-v1"
    )
    execution_authority_kind: Literal["truth_blind_rf_reference"] = (
        "truth_blind_rf_reference"
    )
    benchmark_acceptance_claim: Literal[False] = False
    native_acceptance_claim: Literal[False] = False
    human_approval_granted: Literal[False] = False
    truth_compared: Literal[False] = False
    reference_run_id: str
    plan_id: str
    cases: tuple[ReferenceRunCase, ...] = Field(min_length=5, max_length=5)
    source_sha256: dict[str, Sha256Hex]
    input_sha256: dict[str, Sha256Hex]
    output_sha256: dict[str, Sha256Hex]


def _read[T: ContractModel](path: Path, model: type[T]) -> T:
    if path.is_symlink() or not path.is_file():
        raise ValueError("reference aggregate context is not an original regular file")
    return model.model_validate_json(path.read_bytes())


def _unique_context_paths(paths: tuple[Path, ...]) -> None:
    if len(paths) != len({path.resolve(strict=True) for path in paths}):
        raise ValueError("reference aggregate repeats an original context path")


def _derive(
    inputs: ReferenceRunInputs,
) -> tuple[str, tuple[ReferenceRunCase, ...], dict[str, str], dict[str, bytes]]:
    _unique_context_paths(inputs.prepared_contexts)
    _unique_context_paths(inputs.identity_contexts)
    plan_context = _read(inputs.plan_context, ReferencePlanContext)
    plan = validate_reference_plan(plan_context.plan_path, plan_context.inputs())
    expected = tuple(row.task.case_id for row in plan.cases)
    prepared: dict[str, tuple[Path, ReferencePreparedContext]] = {}
    for path in inputs.prepared_contexts:
        context = _read(path, ReferencePreparedContext)
        if context.case_id in prepared or context.plan != plan_context:
            raise ValueError("reference aggregate has duplicate or foreign preparation")
        prepared[context.case_id] = (path, context)
    if len(expected) != 5 or set(prepared) != set(expected):
        raise ValueError("reference aggregate requires all five exact prepared cases")
    identities: dict[str, tuple[Path, ReferenceIdentityContext]] = {}
    for path in inputs.identity_contexts:
        context = _read(path, ReferenceIdentityContext)
        case_id = context.finalists.review.prepared.case_id
        if case_id in identities or case_id not in prepared:
            raise ValueError("reference aggregate has duplicate or foreign identity")
        if context.finalists.review.prepared != prepared[case_id][1]:
            raise ValueError("reference identity differs from original preparation")
        identities[case_id] = (path, context)

    digests = {
        "plan_context": sha256_file(inputs.plan_context),
        "reference_plan": sha256_file(plan_context.plan_path),
    }
    files = {
        "plan/context.json": inputs.plan_context.read_bytes(),
        "plan/reference_plan.json": plan_context.plan_path.read_bytes(),
    }
    rows = []
    for case_id in expected:
        context_path, prepared_context = prepared[case_id]
        manifest, _ = validate_reference_prepared_case(
            prepared_context.prepared_path, prepared_context.inputs()
        )
        if manifest.task.case_id != case_id:
            raise ValueError("reference aggregate preparation changed case identity")
        if (manifest.status == "materialised") != (case_id in identities):
            raise ValueError("reference aggregate has missing or invented identity")
        prefix = f"cases/{case_id}"
        digests[f"{case_id}:prepared_context"] = sha256_file(context_path)
        digests[f"{case_id}:prepared_manifest"] = sha256_file(
            prepared_context.prepared_path
        )
        files[f"{prefix}/prepared_context.json"] = context_path.read_bytes()
        files[f"{prefix}/reference_prepared_case.json"] = (
            prepared_context.prepared_path.read_bytes()
        )
        identity_id = None
        if case_id in identities:
            identity_context_path, identity_context = identities[case_id]
            finalists = identity_context.finalists
            identity = validate_reference_case_identity(
                identity_context.identity_path,
                ReferenceIdentityInputs(
                    continuation=finalists.review.inputs(),
                    copy_receipts=finalists.copy_receipts,
                    finalists_path=finalists.finalists_path,
                    refinement_receipts=identity_context.refinement_receipts,
                ),
            )
            if identity.case_id != case_id:
                raise ValueError("reference aggregate identity changed case")
            identity_id = identity.case_identity_id
            digests[f"{case_id}:identity_context"] = sha256_file(identity_context_path)
            digests[f"{case_id}:identity_manifest"] = sha256_file(
                identity_context.identity_path
            )
            files[f"{prefix}/identity_context.json"] = (
                identity_context_path.read_bytes()
            )
            files[f"{prefix}/identity/reference_case_identity.json"] = (
                identity_context.identity_path.read_bytes()
            )
            for relative in identity.output_sha256:
                files[f"{prefix}/identity/{relative}"] = _owned(
                    identity_context.identity_path.parent, relative
                ).read_bytes()
        rows.append(
            ReferenceRunCase(
                case_id=case_id,
                preparation_status=manifest.status,
                production_early_outcome=manifest.production_early_outcome,
                prepared_id=manifest.prepared_id,
                case_identity_id=identity_id,
            )
        )
    return plan.plan_id, tuple(rows), digests, files


def _identity(manifest: ReferenceRun) -> str:
    return content_id(
        "rfrun_", manifest.model_dump(mode="json", exclude={"reference_run_id"})
    )


def build_reference_run(inputs: ReferenceRunInputs, output: Path) -> Path:
    """Freeze exact-case evidence, with original-path revalidation after writing."""

    if output.exists() or output.is_symlink():
        raise ValueError("reference aggregate output must not already exist")
    output = output.resolve()
    source = _source_sha256()
    plan_id, rows, digests, files = _derive(inputs)
    output.mkdir(parents=True, exist_ok=False)
    for relative, contents in files.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    manifest = ReferenceRun(
        reference_run_id="pending",
        plan_id=plan_id,
        cases=rows,
        source_sha256=source,
        input_sha256=digests,
        output_sha256=_inventory(output, _MANIFEST),
    )
    manifest = manifest.model_copy(update={"reference_run_id": _identity(manifest)})
    path = output / _MANIFEST
    atomic_write_json(path, manifest.model_dump(mode="json"))
    validate_reference_run(path, inputs)
    return path


def validate_reference_run(path: Path, inputs: ReferenceRunInputs) -> ReferenceRun:
    """Rederive every original case and reject missing, foreign or altered bytes."""

    if path.is_symlink() or path.name != _MANIFEST:
        raise ValueError("reference aggregate requires its owned canonical manifest")
    path = path.resolve(strict=True)
    manifest = ReferenceRun.model_validate_json(path.read_bytes())
    plan_id, rows, digests, files = _derive(inputs)
    if (
        manifest.reference_run_id != _identity(manifest)
        or manifest.source_sha256 != _source_sha256()
        or manifest.plan_id != plan_id
        or manifest.cases != rows
        or manifest.input_sha256 != digests
        or manifest.output_sha256 != _inventory(path.parent, _MANIFEST)
        or set(manifest.output_sha256) != set(files)
        or any(
            (path.parent / relative).read_bytes() != contents
            for relative, contents in files.items()
        )
    ):
        raise ValueError("reference aggregate cases, source, inputs or outputs changed")
    return manifest
