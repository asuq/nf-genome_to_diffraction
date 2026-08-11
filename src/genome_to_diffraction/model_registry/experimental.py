"""Prepare one deterministic cleaned PDB source-chain variant per mapping.

This initial experimental-model path verifies a registered PDB coordinate and
its typed hit mapping, selects exactly one author chain from a single structural
model, removes non-polymer residues and hydrogens, remaps the output chain to
``A`` for portable PDB output, and records the unmodified experimental atom
coordinates as a content-addressed Phaser-readable model.  Alternate
conformations are retained.  Sequence adaptation, side-chain pruning, domain
splitting, ensembles, and multi-model entries are deliberately deferred.
"""

import hashlib
import logging
from collections.abc import Callable, Sequence
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
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.schemas.base import ContractModel
from genome_to_diffraction.schemas.results import (
    CoordinateHitMappingRecord,
    CoordinateSourceRecord,
    ProcessedModelRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import InputContractError, ResultParseError
from genome_to_diffraction.time import utc_now_iso

_LOGGER = logging.getLogger("genome_to_diffraction.model_registry.experimental")
_ADAPTER_VERSION = "gemmi-pdb-source-chain-v1"
_VARIANT_TYPE = "experimental_cleaned_source_chain"


class ExperimentalModelInputError(InputContractError):
    """Experimental coordinate, mapping, and catalogue records do not join."""


class ExperimentalModelParseError(ResultParseError):
    """A registered PDB source cannot produce the bounded source-chain variant."""


@dataclass(frozen=True)
class ExperimentalModelPreparationRequest:
    """Inputs for one cleaned source-chain model per selected PDB mapping."""

    coordinate_sources_jsonl: Path
    coordinate_hit_mappings_jsonl: Path
    sequence_groups_jsonl: Path
    output_directory: Path
    mapping_ids: tuple[str, ...] = ()
    progress: bool = True


@dataclass(frozen=True)
class ExperimentalModelPreparationOutput:
    """Published processed-model records and their relocatable manifest."""

    records: tuple[ProcessedModelRecord, ...]
    records_jsonl: Path
    manifest_json: Path


@dataclass(frozen=True)
class _CleanedChain:
    payload: bytes
    observed_sequence: str
    residue_ranges: tuple[str, ...]
    atom_count: int
    residue_count: int
    alternate_conformations_retained: bool


def _read_jsonl[T: ContractModel](
    path: Path,
    model: type[T],
    *,
    label: str,
    identifier: Callable[[T], str],
    progress: bool,
) -> tuple[T, ...]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ExperimentalModelInputError(f"{label} input is not a file: {resolved}")
    rows: list[T] = []
    seen: set[str] = set()
    with resolved.open(encoding="utf-8") as handle:
        iterator = tqdm(
            enumerate(handle, start=1),
            desc=f"Validate {label}",
            unit="record",
            disable=not progress,
        )
        for line_number, line in iterator:
            if not line.strip():
                raise ExperimentalModelInputError(
                    f"blank {label} record at line {line_number}: {resolved}"
                )
            try:
                record = model.model_validate_json(line)
            except (ValidationError, TypeError, ValueError) as error:
                raise ExperimentalModelInputError(
                    f"invalid {label} record at line {line_number}: {resolved}"
                ) from error
            record_id = identifier(record)
            if record_id in seen:
                raise ExperimentalModelInputError(f"duplicate {label} ID: {record_id}")
            seen.add(record_id)
            rows.append(record)
    if not rows:
        raise ExperimentalModelInputError(f"{label} input is empty: {resolved}")
    return tuple(rows)


def _selected_mappings(
    mappings: Sequence[CoordinateHitMappingRecord], requested: Sequence[str]
) -> tuple[CoordinateHitMappingRecord, ...]:
    by_id = {item.mapping_id: item for item in mappings}
    if len(set(requested)) != len(requested):
        raise ExperimentalModelInputError("mapping selection contains duplicates")
    unknown = sorted(set(requested) - set(by_id))
    if unknown:
        raise ExperimentalModelInputError(
            "unknown selected mapping_id(s): " + ", ".join(unknown)
        )
    return (
        tuple(by_id[item] for item in requested)
        if requested
        else tuple(sorted(mappings, key=lambda item: item.mapping_id))
    )


def _residue_label(number: int, insertion_code: str) -> str:
    return f"{number}{insertion_code.strip()}"


def _compress_ranges(
    chain_id: str, residues: Sequence[gemmi.Residue]
) -> tuple[str, ...]:
    if not residues:
        raise ExperimentalModelParseError("selected PDB chain has no polymer residues")
    ranges: list[str] = []
    start = residues[0].seqid
    previous = start
    for residue in residues[1:]:
        current = residue.seqid
        contiguous = (
            not previous.icode.strip()
            and not current.icode.strip()
            and current.num == previous.num + 1
        )
        if not contiguous:
            start_label = _residue_label(start.num, start.icode)
            previous_label = _residue_label(previous.num, previous.icode)
            ranges.append(
                f"{chain_id}:{start_label}"
                if start_label == previous_label
                else f"{chain_id}:{start_label}-{previous_label}"
            )
            start = current
        previous = current
    start_label = _residue_label(start.num, start.icode)
    previous_label = _residue_label(previous.num, previous.icode)
    ranges.append(
        f"{chain_id}:{start_label}"
        if start_label == previous_label
        else f"{chain_id}:{start_label}-{previous_label}"
    )
    return tuple(ranges)


def _clean_source_chain(
    path: Path, mapping: CoordinateHitMappingRecord
) -> _CleanedChain:
    try:
        structure = gemmi.read_structure(str(path))
        structure.setup_entities()
    except (OSError, RuntimeError, ValueError) as error:
        raise ExperimentalModelParseError(
            f"registered PDB coordinate is not parseable: {path}: {error}"
        ) from error
    if len(structure) != 1:
        raise ExperimentalModelParseError(
            "initial experimental-model path requires exactly one structural model"
        )
    matching = [chain for chain in structure[0] if chain.name == mapping.seqres_token]
    if len(matching) != 1:
        raise ExperimentalModelParseError(
            "registered author-chain token did not resolve to exactly one coordinate "
            f"chain: {mapping.pdb_id}_{mapping.seqres_token}"
        )
    selected = matching[0]
    polymer = list(selected.get_polymer())
    if not polymer:
        raise ExperimentalModelParseError("selected PDB chain has no polymer residues")
    letters: list[str] = []
    for residue in polymer:
        letter = gemmi.find_tabulated_residue(residue.name).one_letter_code.upper()
        if len(letter) != 1 or letter in {" ", "-", "?", "X"}:
            raise ExperimentalModelParseError(
                "selected PDB chain contains an unsupported observed residue: "
                f"{residue.name}"
            )
        letters.append(letter)
    observed_sequence = "".join(letters)
    cleaned = structure.clone()
    model = cleaned[0]
    for index in range(len(model) - 1, -1, -1):
        if model[index].name != mapping.seqres_token:
            del model[index]
    if len(model) != 1:
        raise AssertionError("validated source chain was lost during cleaning")
    chain = model[0]
    for index in range(len(chain) - 1, -1, -1):
        if chain[index].entity_type is not gemmi.EntityType.Polymer:
            del chain[index]
    alternate_conformations = any(
        atom.has_altloc() for residue in chain for atom in residue
    )
    cleaned.remove_hydrogens()
    chain.name = "A"
    payload = cleaned.make_pdb_string().encode("ascii")
    try:
        published = gemmi.read_pdb_string(payload.decode("ascii"))
        published.setup_entities()
    except (RuntimeError, ValueError) as error:
        raise ExperimentalModelParseError(
            f"cleaned experimental PDB is not parseable: {error}"
        ) from error
    published_polymer = list(published[0][0].get_polymer())
    published_sequence = "".join(
        gemmi.find_tabulated_residue(item.name).one_letter_code.upper()
        for item in published_polymer
    )
    if published_sequence != observed_sequence:
        raise ExperimentalModelParseError(
            "cleaned PDB output changed the observed source-chain sequence"
        )
    atom_count = sum(len(residue) for residue in published_polymer)
    if atom_count < 1:
        raise ExperimentalModelParseError("cleaned PDB output contains no atoms")
    return _CleanedChain(
        payload=payload,
        observed_sequence=observed_sequence,
        residue_ranges=_compress_ranges(mapping.seqres_token, polymer),
        atom_count=atom_count,
        residue_count=len(published_polymer),
        alternate_conformations_retained=alternate_conformations,
    )


def _publish_model(path: Path, payload: bytes, digest: str) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_file() or sha256_file(path) != digest:
            raise ExperimentalModelInputError(
                f"content-addressed experimental model is unsafe: {path}"
            )
        return
    atomic_write_bytes(path, payload)
    if sha256_file(path) != digest:
        raise ExperimentalModelInputError(
            f"published experimental-model checksum mismatch: {path}"
        )


def prepare_experimental_models(
    request: ExperimentalModelPreparationRequest,
) -> ExperimentalModelPreparationOutput:
    """Create one cleaned source-chain PDB model per selected direct-PDB mapping."""

    sources = _read_jsonl(
        request.coordinate_sources_jsonl,
        CoordinateSourceRecord,
        label="coordinate sources",
        identifier=lambda item: item.coordinate_id,
        progress=request.progress,
    )
    mappings = _read_jsonl(
        request.coordinate_hit_mappings_jsonl,
        CoordinateHitMappingRecord,
        label="coordinate-hit mappings",
        identifier=lambda item: item.mapping_id,
        progress=request.progress,
    )
    groups = _read_jsonl(
        request.sequence_groups_jsonl,
        SequenceGroupRecord,
        label="sequence groups",
        identifier=lambda item: item.sequence_group_id,
        progress=request.progress,
    )
    source_index = {item.coordinate_id: item for item in sources}
    group_index = {item.sequence_group_id: item for item in groups}
    selected = _selected_mappings(mappings, request.mapping_ids)
    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise ExperimentalModelInputError(
            f"experimental-model output directory is not empty: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)
    model_root = output / "models"
    model_root.mkdir()
    records: list[ProcessedModelRecord] = []
    entries: list[dict[str, object]] = []
    iterator = tqdm(
        selected,
        desc="Prepare experimental models",
        unit="model",
        disable=not request.progress,
    )
    for mapping in iterator:
        source = source_index.get(mapping.coordinate_id)
        group = group_index.get(mapping.sequence_group_id)
        if source is None or group is None:
            raise ExperimentalModelInputError(
                f"mapping cannot resolve its coordinate/group: {mapping.mapping_id}"
            )
        if source.provider != "pdb":
            raise ExperimentalModelInputError(
                "experimental-model mapping does not use a PDB source: "
                f"{mapping.mapping_id}"
            )
        if (
            source.source_sequence_sha256 != mapping.source_sequence_sha256
            or group.sha256 != mapping.candidate_sequence_sha256
        ):
            raise ExperimentalModelInputError(
                "mapping sequence identity differs from source/group: "
                f"{mapping.mapping_id}"
            )
        try:
            coordinate = Path(source.coordinate_path).resolve(strict=True)
        except FileNotFoundError as error:
            raise ExperimentalModelInputError(
                f"registered coordinate does not exist: {source.coordinate_path}"
            ) from error
        if not coordinate.is_file() or coordinate.is_symlink():
            raise ExperimentalModelInputError(
                f"registered coordinate is not a safe file: {coordinate}"
            )
        if (
            sha256_file(
                coordinate,
                progress=request.progress,
                logger=_LOGGER,
                description=f"Verify {source.coordinate_id[:18]}",
            )
            != source.coordinate_sha256
        ):
            raise ExperimentalModelInputError(
                f"coordinate checksum mismatch: {source.coordinate_id}"
            )
        cleaned = _clean_source_chain(coordinate, mapping)
        mass = assess_mass(cleaned.observed_sequence)
        if mass.exact_da is None:
            raise ExperimentalModelParseError(
                f"cleaned experimental model lacks an exact mass: {mapping.mapping_id}"
            )
        model_sha256 = hashlib.sha256(cleaned.payload).hexdigest()
        relative_model = Path("models") / model_sha256[:2] / f"{model_sha256}.pdb"
        model_path = output / relative_model
        model_path.parent.mkdir(parents=True, exist_ok=True)
        _publish_model(model_path, cleaned.payload, model_sha256)
        retained_fraction = cleaned.residue_count / mapping.source_sequence_length
        if not 0 < retained_fraction <= 1:
            raise ExperimentalModelParseError(
                f"observed source-chain coverage is invalid: {mapping.mapping_id}"
            )
        quality_flags = ["experimental_source_chain_variant_only"]
        if not mapping.exact_sequence_match:
            quality_flags.append("experimental_homologue")
        if mapping.query_coverage < 1:
            quality_flags.append("partial_candidate_alignment")
        if retained_fraction < 1:
            quality_flags.append("source_chain_missing_residues")
        if cleaned.alternate_conformations_retained:
            quality_flags.append("alternate_conformations_retained")
        parameters: dict[str, JsonValue] = {
            "adapter_version": _ADAPTER_VERSION,
            "mapping_id": mapping.mapping_id,
            "hit_id": mapping.hit_id,
            "source_author_chain": mapping.seqres_token,
            "output_chain": "A",
            "remove_non_polymer_residues": True,
            "remove_hydrogens": True,
            "retain_alternate_conformations": True,
            "sequence_adaptation": False,
            "side_chain_pruning": False,
            "domain_splitting": False,
            "query_range": [mapping.query_start, mapping.query_end],
            "target_range": [mapping.target_start, mapping.target_end],
            "query_coverage": mapping.query_coverage,
            "target_coverage": mapping.target_coverage,
            "sequence_identity": mapping.sequence_identity,
            "source_sequence_sha256": mapping.source_sequence_sha256,
            "candidate_sequence_sha256": mapping.candidate_sequence_sha256,
            "observed_sequence_sha256": hashlib.sha256(
                cleaned.observed_sequence.encode("ascii")
            ).hexdigest(),
            "observed_residue_count": cleaned.residue_count,
            "atom_count": cleaned.atom_count,
        }
        model_identity = {
            "coordinate_sha256": source.coordinate_sha256,
            "mapping_id": mapping.mapping_id,
            "variant_type": _VARIANT_TYPE,
            "residue_ranges": cleaned.residue_ranges,
            "processing_tool": "gemmi",
            "processing_version": gemmi.__version__,
            "processing_parameters": parameters,
            "model_sha256": model_sha256,
        }
        record = ProcessedModelRecord(
            schema_version="1.0",
            model_id=content_id("model_", model_identity),
            coordinate_id=source.coordinate_id,
            variant_type=_VARIANT_TYPE,
            residue_ranges=cleaned.residue_ranges,
            processing_tool="gemmi",
            processing_version=gemmi.__version__,
            processing_parameters=parameters,
            estimated_coordinate_error=None,
            model_mass_da=mass.exact_da,
            full_candidate_sequence_group_id=group.sequence_group_id,
            model_sha256=model_sha256,
            quality_flags=tuple(quality_flags),
        )
        records.append(record)
        entries.append(
            {
                "mapping_id": mapping.mapping_id,
                "model_id": record.model_id,
                "model_path": relative_model.as_posix(),
                "model_sha256": model_sha256,
                "retained_fraction": retained_fraction,
                "query_coverage": mapping.query_coverage,
                "sequence_identity": mapping.sequence_identity,
                "exact_sequence_match": mapping.exact_sequence_match,
                "quality_flags": quality_flags,
            }
        )
        _LOGGER.info(
            "experimental PDB model prepared",
            extra={
                "mapping_id": mapping.mapping_id,
                "model_id": record.model_id,
                "model_sha256": model_sha256,
                "observed_residue_count": cleaned.residue_count,
            },
        )
    records_path = output / "processed_models.jsonl"
    atomic_write_text(
        records_path,
        "".join(f"{canonical_json_text(item)}\n" for item in records),
    )
    input_sha256 = {
        "coordinate_sources": sha256_file(
            request.coordinate_sources_jsonl, progress=False
        ),
        "coordinate_hit_mappings": sha256_file(
            request.coordinate_hit_mappings_jsonl, progress=False
        ),
        "sequence_groups": sha256_file(request.sequence_groups_jsonl, progress=False),
    }
    manifest_identity = {
        "adapter_version": _ADAPTER_VERSION,
        "input_sha256": input_sha256,
        "model_ids": [item.model_id for item in records],
    }
    manifest_path = output / "model_preparation_manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "preparation_id": content_id("modelprep_", manifest_identity),
            "created_at": utc_now_iso(),
            "adapter_version": _ADAPTER_VERSION,
            "scope": "experimental_cleaned_source_chain_only",
            "processing_tool": "gemmi",
            "processing_version": gemmi.__version__,
            "input_sha256": input_sha256,
            "selected_mapping_count": len(selected),
            "processed_model_count": len(records),
            "entries": entries,
            "outputs": {
                "processed_models": {
                    "path": records_path.name,
                    "sha256": sha256_file(records_path, progress=False),
                }
            },
        },
    )
    return ExperimentalModelPreparationOutput(
        records=tuple(records),
        records_jsonl=records_path,
        manifest_json=manifest_path,
    )
