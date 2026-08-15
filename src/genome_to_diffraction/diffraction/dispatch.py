"""Select one manifest-owned crystal for the first-copy MR boundary.

The normal workflow deliberately runs structural stages for one crystal per
invocation.  This module validates that boundary, verifies the MTZ against the
completed preflight record, and publishes a small immutable dispatch bundle.
It never accepts a caller-supplied crystal identifier or MTZ path.
"""

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    OperatorIdentifier,
    Sha256Hex,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import CrystalManifest
from genome_to_diffraction.schemas.results import MtzPreflightRecord, PreflightDecision
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_LOGGER = logging.getLogger("genome_to_diffraction.diffraction.dispatch")


class CrystalDispatchError(InputContractError):
    """The crystal manifest cannot safely enter the per-crystal MR workflow."""


class CrystalDispatchRecord(ContractModel):
    """Immutable provenance for one manifest-derived crystal dispatch."""

    schema_version: Literal["1.0"]
    dispatch_id: NonEmptyString
    crystal_id: OperatorIdentifier
    catalogue_id: NonEmptyString
    crystal_manifest_sha256: Sha256Hex
    preflight_jsonl_sha256: Sha256Hex
    preflight_id: NonEmptyString
    mtz_sha256: Sha256Hex
    staged_mtz: Literal["input.mtz"]


@dataclass(frozen=True)
class CrystalDispatchRequest:
    """Inputs for one normal-workflow crystal selection."""

    crystal_manifest: Path
    preflight_jsonl: Path
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True)
class CrystalDispatchOutput:
    """Files published for downstream first-copy MR."""

    record: CrystalDispatchRecord
    dispatch_json: Path
    crystal_id_txt: Path
    mtz: Path


def _read_preflights(path: Path) -> tuple[MtzPreflightRecord, ...]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise CrystalDispatchError(f"preflight JSONL is not a file: {resolved}")
    records: list[MtzPreflightRecord] = []
    with resolved.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(MtzPreflightRecord.model_validate_json(line))
            except ValidationError as error:
                raise CrystalDispatchError(
                    f"invalid MTZ preflight record at line {line_number}: {resolved}"
                ) from error
    if len(records) != 1:
        raise CrystalDispatchError(
            "first-copy dispatch requires exactly one MTZ preflight record; "
            f"found {len(records)}"
        )
    return tuple(records)


def _resolve_mtz(manifest: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = manifest.parent / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise CrystalDispatchError(
            f"cannot resolve crystal MTZ: {candidate}"
        ) from error
    if not resolved.is_file():
        raise CrystalDispatchError(f"crystal MTZ is not a file: {resolved}")
    return resolved


def _copy_atomic(source: Path, destination: Path) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            with source.open("rb") as input_handle:
                shutil.copyfileobj(input_handle, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def prepare_crystal_dispatch(
    request: CrystalDispatchRequest,
) -> CrystalDispatchOutput:
    """Validate and stage exactly one manifest-owned MTZ for first-copy MR."""

    manifest_path = request.crystal_manifest.resolve(strict=True)
    manifest = load_contract(
        manifest_path,
        "crystal-manifest",
        progress=False,
    )
    if not isinstance(manifest, CrystalManifest):
        raise TypeError("crystal dispatch received an unexpected contract")
    if len(manifest.crystals) != 1:
        raise CrystalDispatchError(
            "first-copy analysis requires a one-crystal manifest; "
            f"found {len(manifest.crystals)} crystals"
        )
    crystal = manifest.crystals[0]
    preflight_path = request.preflight_jsonl.resolve(strict=True)
    preflight = _read_preflights(preflight_path)[0]
    if preflight.crystal_id != crystal.crystal_id:
        raise CrystalDispatchError(
            "crystal manifest and MTZ preflight identifiers differ: "
            f"{crystal.crystal_id} != {preflight.crystal_id}"
        )
    if (
        preflight.decision is PreflightDecision.FAIL
        or preflight.execution_status
        not in {
            ExecutionStatus.COMPLETED_SUCCESS,
            ExecutionStatus.COMPLETED_WARNING,
        }
    ):
        raise CrystalDispatchError(
            f"crystal preflight is not eligible for MR: {preflight.decision.value}/"
            f"{preflight.execution_status.value}"
        )

    source_mtz = _resolve_mtz(manifest_path, crystal.mtz)
    mtz_sha256 = sha256_file(
        source_mtz,
        progress=request.progress,
        description=f"Verify {crystal.crystal_id} MTZ",
        logger=_LOGGER,
    )
    if mtz_sha256 != preflight.mtz_sha256:
        raise CrystalDispatchError(
            "manifest MTZ checksum does not match the completed preflight record"
        )

    requested_output = request.output_directory
    if requested_output.is_symlink():
        raise CrystalDispatchError(
            f"dispatch output must not be a symlink: {requested_output}"
        )
    output = requested_output.resolve()
    if output.exists() and not output.is_dir():
        raise CrystalDispatchError(f"dispatch output is not a directory: {output}")
    if output.exists() and any(output.iterdir()):
        raise CrystalDispatchError(f"dispatch output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    manifest_sha256 = sha256_file(manifest_path, progress=False)
    preflight_sha256 = sha256_file(preflight_path, progress=False)
    identity = {
        "crystal_id": crystal.crystal_id,
        "catalogue_id": crystal.catalogue_id,
        "crystal_manifest_sha256": manifest_sha256,
        "preflight_jsonl_sha256": preflight_sha256,
        "preflight_id": preflight.preflight_id,
        "mtz_sha256": mtz_sha256,
    }
    record = CrystalDispatchRecord(
        schema_version="1.0",
        dispatch_id=content_id("crdispatch_", identity),
        crystal_id=crystal.crystal_id,
        catalogue_id=crystal.catalogue_id,
        crystal_manifest_sha256=manifest_sha256,
        preflight_jsonl_sha256=preflight_sha256,
        preflight_id=preflight.preflight_id,
        mtz_sha256=mtz_sha256,
        staged_mtz="input.mtz",
    )
    staged_mtz = output / record.staged_mtz
    _copy_atomic(source_mtz, staged_mtz)
    if sha256_file(staged_mtz, progress=False) != mtz_sha256:
        raise CrystalDispatchError("staged MTZ checksum differs from its source")
    dispatch_json = output / "crystal_dispatch.json"
    crystal_id_txt = output / "crystal_id.txt"
    atomic_write_json(dispatch_json, record.model_dump(mode="json"))
    atomic_write_text(crystal_id_txt, f"{crystal.crystal_id}\n")
    _LOGGER.info(
        "single-crystal MR dispatch prepared",
        extra={
            "dispatch_id": record.dispatch_id,
            "crystal_id": record.crystal_id,
            "mtz_sha256": record.mtz_sha256,
            "output": str(output),
        },
    )
    return CrystalDispatchOutput(record, dispatch_json, crystal_id_txt, staged_mtz)
