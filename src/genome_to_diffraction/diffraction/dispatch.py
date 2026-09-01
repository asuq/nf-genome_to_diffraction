"""Select one manifest-owned crystal for a per-crystal MR boundary.

The v1 workflow selects the sole crystal implicitly. Phase III fan-out passes
an explicit manifest-owned crystal identifier for each Nextflow item and opts
into content-addressed diffraction-selection and exact Free-R identities. Both
paths verify the MTZ against the completed preflight record. A caller-supplied
MTZ path or guessed Free-R test convention is never accepted.
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
from genome_to_diffraction.diffraction.free_r_identity import (
    FreeRIdentityError,
    build_free_r_identity,
)
from genome_to_diffraction.diffraction.selection import (
    DiffractionSelectionError,
    build_diffraction_selection,
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
    crystal_id: str | None = None
    phase3_diffraction: bool = False


@dataclass(frozen=True)
class CrystalDispatchOutput:
    """Files published for downstream first-copy MR."""

    record: CrystalDispatchRecord
    dispatch_json: Path
    crystal_id_txt: Path
    mtz: Path
    diffraction_selection: Path | None = None
    free_r_identity: Path | None = None


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
    if not records:
        raise CrystalDispatchError("first-copy dispatch requires MTZ preflight records")
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
    if request.crystal_id is None:
        if len(manifest.crystals) != 1:
            raise CrystalDispatchError(
                "first-copy analysis requires a one-crystal manifest when "
                "crystal_id is omitted; "
                f"found {len(manifest.crystals)} crystals"
            )
        crystal = manifest.crystals[0]
    else:
        matching_crystals = tuple(
            crystal
            for crystal in manifest.crystals
            if crystal.crystal_id == request.crystal_id
        )
        if len(matching_crystals) != 1:
            raise CrystalDispatchError(
                "requested crystal_id is not uniquely present in the manifest: "
                f"{request.crystal_id}"
            )
        crystal = matching_crystals[0]
    preflight_path = request.preflight_jsonl.resolve(strict=True)
    matching_preflights = tuple(
        preflight
        for preflight in _read_preflights(preflight_path)
        if preflight.crystal_id == crystal.crystal_id
    )
    if len(matching_preflights) != 1:
        raise CrystalDispatchError(
            "crystal requires exactly one matching MTZ preflight record: "
            f"{crystal.crystal_id}; found {len(matching_preflights)}"
        )
    preflight = matching_preflights[0]
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

    manifest_sha256 = sha256_file(manifest_path, progress=False)
    diffraction_selection = None
    free_r_identity = None
    if request.phase3_diffraction:
        if preflight.free_flag_status not in {"present", "generated"} or (
            preflight.free_flag_labels is None
        ):
            raise CrystalDispatchError(
                "Phase III dispatch requires one existing selected Free-R array"
            )
        if crystal.free_r_test_value is None:
            raise CrystalDispatchError(
                "Phase III dispatch requires an explicit Free-R test value"
            )
        try:
            diffraction_selection = build_diffraction_selection(
                crystal=crystal,
                preflight=preflight,
                crystal_manifest_sha256=manifest_sha256,
            )
            free_r_identity = build_free_r_identity(
                selection=diffraction_selection,
                mtz_path=source_mtz,
                # Free-R flags are reflection metadata and may legitimately
                # live in a different MTZ dataset from F/SIGF or I/SIGI. The
                # identity builder still requires one unique integral column
                # and records its observed dataset ID and exact HKL mapping.
                free_r_dataset_id=None,
                free_r_label=preflight.free_flag_labels,
                test_flag_value=crystal.free_r_test_value,
            )
        except (DiffractionSelectionError, FreeRIdentityError) as error:
            raise CrystalDispatchError(
                f"Phase III diffraction selection is not safely bound: {error}"
            ) from error

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
    selection_json = None
    free_r_json = None
    if diffraction_selection is not None and free_r_identity is not None:
        selection_json = output / "phase3_diffraction_selection.json"
        free_r_json = output / "phase3_free_r_identity.json"
        atomic_write_json(selection_json, diffraction_selection.model_dump(mode="json"))
        atomic_write_json(free_r_json, free_r_identity.model_dump(mode="json"))
    _LOGGER.info(
        "single-crystal MR dispatch prepared",
        extra={
            "dispatch_id": record.dispatch_id,
            "crystal_id": record.crystal_id,
            "mtz_sha256": record.mtz_sha256,
            "output": str(output),
        },
    )
    return CrystalDispatchOutput(
        record,
        dispatch_json,
        crystal_id_txt,
        staged_mtz,
        selection_json,
        free_r_json,
    )
