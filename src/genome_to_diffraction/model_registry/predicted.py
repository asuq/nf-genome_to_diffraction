"""Prepare sequence-mapped predicted coordinates for molecular replacement.

The adapter accepts immutable ``CoordinateSourceRecord`` and
``SequenceGroupRecord`` JSONL files, verifies their checksums and exact sequence
mapping, and invokes the verified Phenix 2.1
``phenix.process_predicted_model`` command in an isolated child shell.  It emits
content-addressed PDB models, ``ProcessedModelRecord`` JSONL, a preparation
manifest, and one raw command log per coordinate.

Only the bounded confidence-pruned, unsplit full-model variant is implemented
here.  A non-zero command, malformed coordinate, sequence mismatch, ambiguous
output, or non-exact model mass fails loudly.  The model cache identity is the
source coordinate digest, exact source alignment and retained ranges, Phenix
build and parameters, and output digest.  Unit tests use a fixed fake Phenix
boundary; the real pilot qualification uses Phenix 2.1-6048 and an exact AFDB
model.
"""

import hashlib
import logging
import math
import re
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import gemmi
from pydantic import JsonValue, ValidationError
from tqdm import tqdm

from genome_to_diffraction.catalogue.mass import assess_mass
from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id, sequence_digest
from genome_to_diffraction.phenix.runtime import (
    capture_from_manifest,
    validate_manifest_environment,
)
from genome_to_diffraction.schemas.base import ContractModel
from genome_to_diffraction.schemas.results import (
    CoordinateSourceRecord,
    ProcessedModelRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import (
    ExecutionStatus,
    InputContractError,
    ResultParseError,
    ToolExecutionError,
)
from genome_to_diffraction.time import utc_now_iso

_LOGGER = logging.getLogger("genome_to_diffraction.model_registry.predicted")
_ADAPTER_VERSION = "phenix-predicted-model-v1"
_VARIANT_TYPE = "predicted_confidence_pruned_full"
_SAFE_COORDINATE_ID = re.compile(r"^coord_[a-f0-9]{64}$")
_PREDICTED_PROVIDERS = frozenset({"afdb", "esm_atlas"})
_LOG_TAIL_BYTES = 16 * 1024
_LOG_TAIL_LINES = 40
_PHIL_PARAMETERS: dict[str, JsonValue] = {
    "output_files.target_output_format": "pdb",
    "process_predicted_model.remove_low_confidence_residues": True,
    "process_predicted_model.split_model_by_compact_regions": False,
    "process_predicted_model.b_value_field_is": "plddt",
    "process_predicted_model.input_plddt_is_fractional": False,
}


class PredictedModelInputError(InputContractError):
    """Predicted-model inputs cannot be mapped without changing their meaning."""


class PredictedModelToolError(ToolExecutionError):
    """Phenix failed or did not publish the requested deterministic variant."""


class PredictedModelParseError(ResultParseError):
    """A source or processed coordinate could not be interpreted safely."""


@dataclass(frozen=True)
class PredictedModelPreparationRequest:
    """Inputs and operational bounds for predicted-model preparation."""

    coordinate_sources_jsonl: Path
    sequence_groups_jsonl: Path
    phenix_manifest: Path
    output_directory: Path
    coordinate_ids: tuple[str, ...] = ()
    timeout_seconds: float | None = None
    progress: bool = True


@dataclass(frozen=True)
class PredictedModelPreparationOutput:
    """Published model records and their relocatable preparation manifest."""

    records: tuple[ProcessedModelRecord, ...]
    records_jsonl: Path
    manifest_json: Path


@dataclass(frozen=True)
class _CoordinateView:
    """One single-chain polymer and its original integer residue positions."""

    chain_id: str
    sequence: str
    positions: tuple[int, ...]
    residue_ranges: tuple[str, ...]


def _read_jsonl[T: ContractModel](
    path: Path,
    model: type[T],
    *,
    label: str,
    progress: bool,
) -> tuple[T, ...]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise PredictedModelInputError(f"{label} input is not a file: {resolved}")
    records: list[T] = []
    with resolved.open(encoding="utf-8") as handle:
        iterator = tqdm(
            enumerate(handle, start=1),
            desc=f"Validate {label}",
            unit="record",
            disable=not progress,
        )
        for line_number, line in iterator:
            if not line.strip():
                raise PredictedModelInputError(
                    f"blank {label} record at line {line_number}: {resolved}"
                )
            try:
                records.append(model.model_validate_json(line))
            except (ValidationError, TypeError, ValueError) as error:
                raise PredictedModelInputError(
                    f"invalid {label} record at line {line_number}: {resolved}"
                ) from error
    if not records:
        raise PredictedModelInputError(f"{label} input is empty: {resolved}")
    return tuple(records)


def _compress_ranges(chain_id: str, positions: Sequence[int]) -> tuple[str, ...]:
    if not positions:
        raise PredictedModelParseError("coordinate contains no polymer residues")
    ranges: list[str] = []
    start = positions[0]
    previous = start
    for position in positions[1:]:
        if position <= previous:
            raise PredictedModelParseError(
                "polymer residue numbers must be strictly increasing"
            )
        if position != previous + 1:
            ranges.append(
                f"{chain_id}:{start}"
                if start == previous
                else f"{chain_id}:{start}-{previous}"
            )
            start = position
        previous = position
    ranges.append(
        f"{chain_id}:{start}" if start == previous else f"{chain_id}:{start}-{previous}"
    )
    return tuple(ranges)


def _coordinate_view(path: Path, *, label: str) -> _CoordinateView:
    try:
        structure = gemmi.read_structure(str(path))
        structure.setup_entities()
    except (OSError, RuntimeError, ValueError) as error:
        raise PredictedModelParseError(
            f"{label} coordinate is not parseable: {path}: {error}"
        ) from error
    if len(structure) != 1:
        raise PredictedModelParseError(
            f"{label} coordinate must contain exactly one model"
        )
    polymer_chains = [
        (chain, list(chain.get_polymer()))
        for chain in structure[0]
        if len(chain.get_polymer()) > 0
    ]
    if len(polymer_chains) != 1:
        raise PredictedModelParseError(
            f"{label} coordinate must contain exactly one polymer chain"
        )
    chain, residues = polymer_chains[0]
    if not chain.name or any(character.isspace() for character in chain.name):
        raise PredictedModelParseError(f"{label} coordinate has an unsafe chain ID")
    letters: list[str] = []
    positions: list[int] = []
    for residue in residues:
        letter = gemmi.find_tabulated_residue(residue.name).one_letter_code
        if len(letter) != 1 or letter in {" ", "-", "?"}:
            raise PredictedModelParseError(
                f"{label} coordinate contains an unknown polymer residue: "
                f"{residue.name}"
            )
        letters.append(letter)
        if residue.seqid.icode.strip():
            raise PredictedModelParseError(
                f"{label} predicted coordinate cannot contain insertion codes"
            )
        position = residue.seqid.num
        if position is None:
            raise PredictedModelParseError(
                f"{label} predicted coordinate contains an unnumbered residue"
            )
        positions.append(position)
    sequence = "".join(letters)
    return _CoordinateView(
        chain_id=chain.name,
        sequence=sequence,
        positions=tuple(positions),
        residue_ranges=_compress_ranges(chain.name, positions),
    )


def _selected_sources(
    sources: Sequence[CoordinateSourceRecord], coordinate_ids: Sequence[str]
) -> tuple[CoordinateSourceRecord, ...]:
    by_id: dict[str, CoordinateSourceRecord] = {}
    for source in sources:
        if _SAFE_COORDINATE_ID.fullmatch(source.coordinate_id) is None:
            raise PredictedModelInputError(
                f"coordinate_id is not a content-derived coordinate ID: "
                f"{source.coordinate_id}"
            )
        if source.coordinate_id in by_id:
            raise PredictedModelInputError(
                f"duplicate coordinate_id: {source.coordinate_id}"
            )
        by_id[source.coordinate_id] = source
    requested = tuple(coordinate_ids)
    if len(set(requested)) != len(requested):
        raise PredictedModelInputError("coordinate selection contains duplicates")
    unknown = sorted(set(requested) - set(by_id))
    if unknown:
        raise PredictedModelInputError(
            "unknown selected coordinate_id(s): " + ", ".join(unknown)
        )
    selected = (
        tuple(by_id[coordinate_id] for coordinate_id in requested)
        if requested
        else tuple(
            source for source in sources if source.provider in _PREDICTED_PROVIDERS
        )
    )
    if not selected:
        raise PredictedModelInputError("no predicted coordinate sources were selected")
    unsupported = sorted(
        source.coordinate_id
        for source in selected
        if source.provider not in _PREDICTED_PROVIDERS
    )
    if unsupported:
        raise PredictedModelInputError(
            "predicted-model processing cannot accept experimental coordinates: "
            + ", ".join(unsupported)
        )
    return selected


def _group_index(
    groups: Sequence[SequenceGroupRecord],
) -> dict[str, SequenceGroupRecord]:
    by_digest: dict[str, SequenceGroupRecord] = {}
    for group in groups:
        if group.sha256 in by_digest:
            raise PredictedModelInputError(
                f"duplicate sequence digest in sequence groups: {group.sha256}"
            )
        by_digest[group.sha256] = group
    return by_digest


def _bounded_log_tail(text: str) -> str:
    bounded = text[-_LOG_TAIL_BYTES:]
    return "\n".join(bounded.splitlines()[-_LOG_TAIL_LINES:])


def _publish_model(path: Path, payload: bytes, digest: str) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise PredictedModelToolError(
                f"content-addressed model target is not a regular file: {path}"
            )
        if sha256_file(path) != digest:
            raise PredictedModelToolError(
                f"content-addressed model target has the wrong checksum: {path}"
            )
        return
    atomic_write_bytes(path, payload)
    if sha256_file(path) != digest:
        raise PredictedModelToolError(
            f"published model failed checksum verification: {path}"
        )


def _prepare_one(
    source: CoordinateSourceRecord,
    group: SequenceGroupRecord,
    *,
    phenix_manifest: Path,
    phenix_version: str,
    phenix_manifest_sha256: str,
    output_directory: Path,
    timeout_seconds: float | None,
    progress: bool,
) -> tuple[ProcessedModelRecord, dict[str, object]]:
    try:
        coordinate = Path(source.coordinate_path).resolve(strict=True)
    except FileNotFoundError as error:
        raise PredictedModelInputError(
            f"coordinate source does not exist: {source.coordinate_path}"
        ) from error
    if not coordinate.is_file():
        raise PredictedModelInputError(f"coordinate source is not a file: {coordinate}")
    source_sha256 = sha256_file(
        coordinate,
        progress=progress,
        logger=_LOGGER,
        description=f"Verify {source.coordinate_id[:18]}",
    )
    if source_sha256 != source.coordinate_sha256:
        raise PredictedModelInputError(
            f"coordinate checksum mismatch for {source.coordinate_id}"
        )
    source_view = _coordinate_view(coordinate, label="source")
    if source.source_sequence_sha256 is None:
        raise PredictedModelInputError(
            f"predicted coordinate lacks source_sequence_sha256: {source.coordinate_id}"
        )
    if source.source_sequence_sha256 != group.sha256:
        raise PredictedModelInputError(
            f"coordinate-to-catalogue digest mismatch for {source.coordinate_id}"
        )
    if sequence_digest(source_view.sequence) != group.sha256:
        raise PredictedModelInputError(
            f"coordinate polymer sequence does not match {group.sequence_group_id}"
        )
    if source_view.positions != tuple(range(1, group.length_aa + 1)):
        raise PredictedModelInputError(
            "predicted source must map exactly to catalogue positions "
            f"1-{group.length_aa}: {source.coordinate_id}"
        )

    raw_directory = output_directory / "raw" / source.coordinate_id
    command_log = raw_directory / "phenix.process_predicted_model.log"
    with tempfile.TemporaryDirectory(
        prefix=".phenix-predicted-", dir=output_directory
    ) as temporary:
        work = Path(temporary)
        prefix = work / "processed"
        arguments = (
            "phenix.process_predicted_model",
            str(coordinate),
            f"output_files.target_output_format={_PHIL_PARAMETERS['output_files.target_output_format']}",
            f"output_files.processed_model_prefix={prefix}",
            "process_predicted_model.remove_low_confidence_residues=True",
            "process_predicted_model.split_model_by_compact_regions=False",
            "process_predicted_model.b_value_field_is=plddt",
            "process_predicted_model.input_plddt_is_fractional=False",
        )
        _LOGGER.info(
            "predicted-model processing started",
            extra={
                "coordinate_id": source.coordinate_id,
                "sequence_group_id": group.sequence_group_id,
                "phenix_version": phenix_version,
            },
        )
        try:
            completed = capture_from_manifest(
                phenix_manifest,
                arguments,
                working_directory=work,
                timeout_seconds=timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            atomic_write_text(
                command_log,
                "phenix.process_predicted_model timed out after "
                f"{timeout_seconds} seconds\n",
            )
            raise PredictedModelToolError(
                f"phenix.process_predicted_model timed out; see {command_log.resolve()}"
            ) from error
        command_output = (completed.stdout + completed.stderr).decode(
            "utf-8", errors="replace"
        )
        atomic_write_text(
            command_log,
            command_output if command_output.endswith("\n") else f"{command_output}\n",
        )
        if completed.returncode != 0:
            tail = _bounded_log_tail(command_output)
            raise PredictedModelToolError(
                "phenix.process_predicted_model failed with exit status "
                f"{completed.returncode}; see {command_log.resolve()}"
                + (f"; bounded log tail:\n{tail}" if tail else "")
            )
        candidates = sorted(work.glob("processed_*.pdb"))
        if len(candidates) != 1:
            raise PredictedModelToolError(
                "Phenix must produce exactly one unsplit processed PDB, found "
                f"{len(candidates)}; see {command_log.resolve()}"
            )
        temporary_model = candidates[0]
        processed_view = _coordinate_view(temporary_model, label="processed")
        if processed_view.chain_id != source_view.chain_id:
            raise PredictedModelParseError(
                "Phenix changed the chain identifier of the unsplit model"
            )
        if any(
            position < 1 or position > group.length_aa
            for position in processed_view.positions
        ):
            raise PredictedModelParseError(
                "processed model residue range exceeds the catalogue sequence"
            )
        expected_processed_sequence = "".join(
            group.sequence[position - 1] for position in processed_view.positions
        )
        if processed_view.sequence != expected_processed_sequence:
            raise PredictedModelParseError(
                "processed model residues do not map exactly to catalogue positions"
            )
        model_payload = temporary_model.read_bytes()

    if sha256_file(coordinate) != source_sha256:
        raise PredictedModelInputError(
            f"coordinate source changed during processing: {source.coordinate_id}"
        )
    model_sha256 = hashlib.sha256(model_payload).hexdigest()
    mass = assess_mass(processed_view.sequence)
    if mass.exact_da is None:
        raise PredictedModelParseError(
            "processed predicted model has no exact sequence-derived mass"
        )
    processing_parameters: dict[str, JsonValue] = {
        "adapter_version": _ADAPTER_VERSION,
        "phenix_manifest_sha256": phenix_manifest_sha256,
        **_PHIL_PARAMETERS,
    }
    identity = {
        "coordinate_id": source.coordinate_id,
        "source_coordinate_sha256": source_sha256,
        "source_sequence_sha256": group.sha256,
        "source_alignment": f"1-{group.length_aa}",
        "retained_residue_ranges": processed_view.residue_ranges,
        "variant_type": _VARIANT_TYPE,
        "processing_tool": "phenix.process_predicted_model",
        "processing_version": phenix_version,
        "processing_parameters": processing_parameters,
        "model_sha256": model_sha256,
    }
    model_id = content_id("model_", identity)
    model_relative = Path("models") / model_sha256[:2] / f"{model_sha256}.pdb"
    model_path = output_directory / model_relative
    _publish_model(model_path, model_payload, model_sha256)
    removed_count = group.length_aa - len(processed_view.positions)
    quality_flags = ["predicted_model_confidence_processed"]
    if removed_count:
        quality_flags.append("low_confidence_residues_removed")
    record = ProcessedModelRecord(
        schema_version="1.0",
        model_id=model_id,
        coordinate_id=source.coordinate_id,
        variant_type=_VARIANT_TYPE,
        residue_ranges=processed_view.residue_ranges,
        processing_tool="phenix.process_predicted_model",
        processing_version=phenix_version,
        processing_parameters=processing_parameters,
        estimated_coordinate_error=None,
        model_mass_da=mass.exact_da,
        full_candidate_sequence_group_id=group.sequence_group_id,
        model_sha256=model_sha256,
        quality_flags=tuple(quality_flags),
    )
    entry: dict[str, object] = {
        "coordinate_id": source.coordinate_id,
        "coordinate_sha256": source_sha256,
        "source_sequence_group_id": group.sequence_group_id,
        "source_alignment": f"1-{group.length_aa}",
        "source_residue_count": group.length_aa,
        "retained_residue_count": len(processed_view.positions),
        "removed_residue_count": removed_count,
        "retained_fraction": len(processed_view.positions) / group.length_aa,
        "model_id": model_id,
        "model_path": model_relative.as_posix(),
        "model_sha256": model_sha256,
        "command_log": command_log.relative_to(output_directory).as_posix(),
        "execution_status": ExecutionStatus.COMPLETED_SUCCESS.value,
    }
    _LOGGER.info(
        "predicted-model processing completed",
        extra={
            "coordinate_id": source.coordinate_id,
            "model_id": model_id,
            "source_residue_count": group.length_aa,
            "retained_residue_count": len(processed_view.positions),
            "removed_residue_count": removed_count,
            "model_sha256": model_sha256,
        },
    )
    return record, entry


def prepare_predicted_models(
    request: PredictedModelPreparationRequest,
) -> PredictedModelPreparationOutput:
    """Verify, confidence-process, and publish selected predicted coordinates."""

    if request.timeout_seconds is not None and (
        not math.isfinite(request.timeout_seconds) or request.timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be positive and finite when supplied")
    sources = _read_jsonl(
        request.coordinate_sources_jsonl,
        CoordinateSourceRecord,
        label="coordinate source",
        progress=request.progress,
    )
    groups = _read_jsonl(
        request.sequence_groups_jsonl,
        SequenceGroupRecord,
        label="sequence group",
        progress=request.progress,
    )
    selected = _selected_sources(sources, request.coordinate_ids)
    groups_by_digest = _group_index(groups)
    phenix_manifest = request.phenix_manifest.resolve(strict=True)
    manifest_model = validate_manifest_environment(phenix_manifest)
    manifest_sha256 = sha256_file(
        phenix_manifest,
        progress=request.progress,
        logger=_LOGGER,
        description="Verify Phenix manifest",
    )
    output = request.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    _LOGGER.info(
        "predicted-model preparation batch selected",
        extra={
            "selected_coordinate_count": len(selected),
            "phenix_version": manifest_model.phenix_version,
            "output_directory": str(output),
        },
    )
    records: list[ProcessedModelRecord] = []
    entries: list[dict[str, object]] = []
    iterator = tqdm(
        selected,
        desc="Prepare predicted models",
        unit="model",
        disable=not request.progress,
    )
    for source in iterator:
        digest = source.source_sequence_sha256
        group = groups_by_digest.get(digest or "")
        if group is None:
            raise PredictedModelInputError(
                "predicted coordinate source does not map to a supplied sequence "
                f"group: {source.coordinate_id}"
            )
        record, entry = _prepare_one(
            source,
            group,
            phenix_manifest=phenix_manifest,
            phenix_version=manifest_model.phenix_version,
            phenix_manifest_sha256=manifest_sha256,
            output_directory=output,
            timeout_seconds=request.timeout_seconds,
            progress=request.progress,
        )
        records.append(record)
        entries.append(entry)

    records_path = output / "processed_models.jsonl"
    atomic_write_text(
        records_path,
        "".join(f"{canonical_json_text(record)}\n" for record in records),
    )
    manifest_path = output / "model_preparation_manifest.json"
    manifest_identity = {
        "adapter_version": _ADAPTER_VERSION,
        "phenix_manifest_sha256": manifest_sha256,
        "models": [record.model_id for record in records],
    }
    manifest = {
        "schema_version": "1.0",
        "preparation_id": content_id("modelprep_", manifest_identity),
        "created_at": utc_now_iso(),
        "adapter_version": _ADAPTER_VERSION,
        "variant_policy": "one confidence-pruned unsplit full predicted model",
        "phenix_version": manifest_model.phenix_version,
        "phenix_manifest_sha256": manifest_sha256,
        "coordinate_source_count": len(selected),
        "processed_model_count": len(records),
        "processed_models_jsonl": records_path.name,
        "entries": entries,
        "execution_status": ExecutionStatus.COMPLETED_SUCCESS.value,
    }
    atomic_write_json(manifest_path, manifest)
    _LOGGER.info(
        "predicted-model preparation complete",
        extra={
            "processed_model_count": len(records),
            "records": str(records_path),
            "manifest": str(manifest_path),
        },
    )
    return PredictedModelPreparationOutput(
        records=tuple(records),
        records_jsonl=records_path,
        manifest_json=manifest_path,
    )
