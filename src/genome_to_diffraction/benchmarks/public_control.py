"""Prepare a checksum-frozen public crystallographic positive control.

The preparer keeps downloaded crystallographic data outside Git.  Its tracked
specification records the scientific ground truth and immutable source hashes;
the generated local manifest records the exact paths and derived-file hashes.
"""

import hashlib
import logging
import os
import tempfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Protocol, Self
from urllib.parse import urlparse

import gemmi
from Bio.SeqIO.FastaIO import SimpleFastaParser
from pydantic import Field, model_validator
from tqdm import tqdm

from genome_to_diffraction import __version__
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.databases.network import (
    DownloadMetadata,
    download_public_resource,
)
from genome_to_diffraction.ids import canonical_sequence
from genome_to_diffraction.mr.policy import SCORE_GATE_LLG, SCORE_GATE_TFZ
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    OperatorIdentifier,
    PositiveFloat,
    PositiveInt,
    Sha256Hex,
)
from genome_to_diffraction.schemas.io import ContractLoadError, load_yaml_document
from genome_to_diffraction.schemas.manifests import (
    CatalogueEntry,
    CatalogueManifest,
    CrystalEntry,
    CrystalManifest,
)
from genome_to_diffraction.status import InputContractError
from genome_to_diffraction.time import utc_now

_LOGGER = logging.getLogger("genome_to_diffraction.benchmarks")
_REQUIRED_RESOURCE_ROLES = {
    "target_coordinates",
    "target_structure_factors",
    "exact_mr_coordinates",
    "homolog_mr_coordinates",
}


class PublicControlError(InputContractError):
    """Public-control source data or ground truth failed validation."""


def _gemmi_version() -> str:
    """Return Gemmi's runtime version without relying on incomplete type stubs."""
    value = getattr(gemmi, "__version__", None)
    if not isinstance(value, str) or not value:
        raise PublicControlError("Gemmi did not expose a non-empty runtime version")
    return value


class PublicResourceSpec(ContractModel):
    """One immutable public source file required by the control."""

    role: Literal[
        "target_coordinates",
        "target_structure_factors",
        "exact_mr_coordinates",
        "homolog_mr_coordinates",
    ]
    pdb_id: str = Field(pattern=r"^[0-9A-Z]{4}$")
    url: NonEmptyString
    filename: str = Field(pattern=r"^[0-9A-Za-z][0-9A-Za-z._-]*$")
    sha256: Sha256Hex
    size_bytes: PositiveInt

    @model_validator(mode="after")
    def _approved_public_route(self) -> Self:
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or parsed.hostname != "files.rcsb.org":
            raise ValueError("public-control resources must use files.rcsb.org HTTPS")
        if Path(self.filename).name != self.filename:
            raise ValueError("public-control filename must be a basename")
        return self


class DerivedMtzSpec(ContractModel):
    """Expected deterministic MTZ derived from deposited structure factors."""

    filename: str = Field(pattern=r"^[0-9A-Za-z][0-9A-Za-z._-]*\.mtz$")
    gemmi_version: NonEmptyString
    sha256: Sha256Hex
    reflection_count: PositiveInt
    space_group: NonEmptyString
    unit_cell: tuple[PositiveFloat, PositiveFloat, PositiveFloat, float, float, float]
    observation_labels: NonEmptyString
    free_flag_labels: NonEmptyString


class TargetConstructSpec(ContractModel):
    """Exact mapping between a deposited construct and its catalogue protein."""

    coordinate_sequence_length: PositiveInt
    coordinate_sequence_sha256: Sha256Hex
    catalogue_start: PositiveInt
    catalogue_end: PositiveInt
    coordinate_match_start: PositiveInt
    coordinate_match_end: PositiveInt

    @model_validator(mode="after")
    def _validate_ranges(self) -> Self:
        if self.catalogue_end < self.catalogue_start:
            raise ValueError("catalogue construct range is reversed")
        if self.coordinate_match_end < self.coordinate_match_start:
            raise ValueError("coordinate construct range is reversed")
        if self.coordinate_match_end > self.coordinate_sequence_length:
            raise ValueError("coordinate construct range exceeds the entity sequence")
        if (self.catalogue_end - self.catalogue_start) != (
            self.coordinate_match_end - self.coordinate_match_start
        ):
            raise ValueError("catalogue and coordinate construct spans differ")
        return self


class MrModelSpec(ContractModel):
    """Expected single-chain polymer-only MR model."""

    model_id: OperatorIdentifier
    source_role: Literal["exact_mr_coordinates", "homolog_mr_coordinates"]
    chain_id: str = Field(pattern=r"^[A-Za-z0-9]+$")
    filename: str = Field(pattern=r"^[0-9A-Za-z][0-9A-Za-z._-]*\.pdb$")
    source_sequence_sha256: Sha256Hex
    expected_model_sha256: Sha256Hex
    relationship_to_target: NonEmptyString
    leakage_class: Literal["operational_exact", "homolog_challenge"]
    target_fragment_start_in_source: PositiveInt | None = None
    target_fragment_end_in_source: PositiveInt | None = None

    @model_validator(mode="after")
    def _validate_exact_mapping(self) -> Self:
        bounds = (
            self.target_fragment_start_in_source,
            self.target_fragment_end_in_source,
        )
        if self.leakage_class == "operational_exact":
            if None in bounds:
                raise ValueError(
                    "an operational exact model requires target-fragment bounds"
                )
            assert bounds[0] is not None and bounds[1] is not None
            if bounds[1] < bounds[0]:
                raise ValueError("exact-model target-fragment range is reversed")
        elif bounds != (None, None):
            raise ValueError("a homolog challenge must not declare an exact match")
        return self


class ScoreGateSpec(ContractModel):
    """Provisional user-defined Phaser score gate for the control."""

    llg_greater_than: float
    tfz_greater_than: float
    combination: Literal["or"]


class PublicControlSpec(ContractModel):
    """Tracked scientific and provenance specification for one public control."""

    schema_version: Literal["1.0"]
    control_id: OperatorIdentifier
    benchmark_class: Literal["operational_public_positive_control"]
    organism: NonEmptyString
    assembly_accession: NonEmptyString
    assembly_version: NonEmptyString
    annotation_provider: NonEmptyString
    annotation_version: NonEmptyString
    expected_proteome_sha256: Sha256Hex
    catalogue_id: OperatorIdentifier
    target_protein_id: OperatorIdentifier
    target_sequence_length: PositiveInt
    target_sequence_sha256: Sha256Hex
    expected_exact_catalogue_records: tuple[OperatorIdentifier, ...] = Field(
        min_length=1
    )
    target_pdb_id: str = Field(pattern=r"^[0-9A-Z]{4}$")
    target_pdb_version: NonEmptyString
    expected_asu_copy_count: PositiveInt
    biological_assembly_copy_count: PositiveInt
    asu_model: Literal["single_protein_species_multi_copy"]
    target_construct: TargetConstructSpec
    processing_software: tuple[NonEmptyString, ...] = Field(min_length=1)
    sds_page_evidence: Literal["not_available"]
    resources: tuple[PublicResourceSpec, ...] = Field(min_length=4)
    derived_mtz: DerivedMtzSpec
    mr_models: tuple[MrModelSpec, ...] = Field(min_length=2)
    score_gate: ScoreGateSpec
    database_exclusions_for_homolog_challenge: tuple[str, ...]
    limitations: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _cross_validate_control(self) -> Self:
        roles = [resource.role for resource in self.resources]
        if set(roles) != _REQUIRED_RESOURCE_ROLES or len(roles) != len(set(roles)):
            raise ValueError(
                "public-control resource roles must be complete and unique"
            )
        model_ids = [model.model_id for model in self.mr_models]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("public-control model IDs must be unique")
        model_roles = {model.source_role for model in self.mr_models}
        if model_roles != {"exact_mr_coordinates", "homolog_mr_coordinates"}:
            raise ValueError("both exact and homolog MR models are required")
        if self.score_gate.llg_greater_than != SCORE_GATE_LLG:
            raise ValueError("the prototype control requires strict LLG > 50")
        if self.score_gate.tfz_greater_than != SCORE_GATE_TFZ:
            raise ValueError("the prototype control requires strict TFZ > 5")
        exact_models = [
            model
            for model in self.mr_models
            if model.leakage_class == "operational_exact"
        ]
        if len(exact_models) != 1:
            raise ValueError("exactly one operational exact MR model is required")
        if self.target_construct.catalogue_end > self.target_sequence_length:
            raise ValueError(
                "the construct mapping exceeds the target catalogue sequence"
            )
        return self


@dataclass(frozen=True)
class PublicControlPreparationRequest:
    """Paths and safeguards for preparing one public positive control."""

    specification: Path
    output_directory: Path
    proteome_faa: Path | None = None
    catalogue_manifest: Path | None = None
    download_missing: bool = True
    progress: bool = True
    storage_limit_bytes: int = 256 * 1024 * 1024
    minimum_free_bytes: int = 64 * 1024 * 1024


@dataclass(frozen=True)
class PublicControlPreparationResult:
    """Stable outputs produced by public-control preparation."""

    control_id: str
    preparation_manifest: Path
    crystal_manifest: Path
    catalogue_manifest: Path
    target_fasta: Path
    mtz: Path
    exact_mr_model: Path
    homolog_mr_model: Path


class _DownloadRequest(Protocol):
    """Storage and network controls shared by public benchmark preparers."""

    @property
    def download_missing(self) -> bool: ...

    @property
    def progress(self) -> bool: ...

    @property
    def storage_limit_bytes(self) -> int: ...

    @property
    def minimum_free_bytes(self) -> int: ...


def load_public_control_spec(path: Path) -> PublicControlSpec:
    """Load and strictly validate one tracked public-control YAML specification."""

    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise PublicControlError(f"public-control specification is not a file: {path}")
    try:
        payload = load_yaml_document(resolved)
        return PublicControlSpec.model_validate(payload)
    except (ContractLoadError, ValueError) as error:
        raise PublicControlError(
            f"invalid public-control specification {resolved}: {error}"
        ) from error


def _safe_output_root(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise PublicControlError(f"public-control output root is unsafe: {path}")
    return path.resolve(strict=True)


def _verify_regular_file(path: Path, *, label: str) -> Path:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file():
        raise PublicControlError(f"{label} is not a regular non-symlink file: {path}")
    return resolved


def _verify_file_identity(
    path: Path,
    *,
    expected_sha256: str,
    expected_size: int | None,
    progress: bool,
    label: str,
) -> str:
    resolved = _verify_regular_file(path, label=label)
    actual_size = resolved.stat().st_size
    if expected_size is not None and actual_size != expected_size:
        raise PublicControlError(
            f"{label} size mismatch: {actual_size} != {expected_size}: {resolved}"
        )
    actual_sha256 = sha256_file(
        resolved,
        progress=progress,
        description=f"Verify {resolved.name}",
        logger=_LOGGER,
    )
    if actual_sha256 != expected_sha256:
        raise PublicControlError(
            f"{label} SHA-256 mismatch: {actual_sha256} != {expected_sha256}: "
            f"{resolved}"
        )
    return actual_sha256


def _ensure_resource(
    resource: PublicResourceSpec,
    *,
    source_directory: Path,
    storage_root: Path,
    request: _DownloadRequest,
) -> tuple[Path, DownloadMetadata | None]:
    destination = source_directory / resource.filename
    metadata: DownloadMetadata | None = None
    if not destination.exists():
        if not request.download_missing:
            raise PublicControlError(
                f"public-control source is missing and downloads are disabled: "
                f"{destination}"
            )
        metadata = download_public_resource(
            resource.url,
            destination,
            storage_root=storage_root,
            storage_limit_bytes=request.storage_limit_bytes,
            minimum_free_bytes=request.minimum_free_bytes,
            progress=request.progress,
        )
    _verify_file_identity(
        destination,
        expected_sha256=resource.sha256,
        expected_size=resource.size_bytes,
        progress=request.progress,
        label=resource.role,
    )
    return destination.resolve(strict=True), metadata


def _fasta_records(path: Path, *, progress: bool) -> Iterable[tuple[str, str, str]]:
    with path.open(encoding="utf-8") as handle:
        iterator = tqdm(
            SimpleFastaParser(handle),
            desc=f"Inspect {path.name}",
            unit="protein",
            disable=not progress,
        )
        for title, raw_sequence in iterator:
            identifier = title.split(maxsplit=1)[0]
            yield identifier, title, canonical_sequence(raw_sequence)


def _target_catalogue_sequence(
    proteome: Path, spec: PublicControlSpec, *, progress: bool
) -> tuple[str, str]:
    target_sequence: str | None = None
    exact_identifiers: list[str] = []
    for identifier, _title, sequence in _fasta_records(proteome, progress=progress):
        digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
        if digest == spec.target_sequence_sha256:
            exact_identifiers.append(identifier)
        if identifier == spec.target_protein_id:
            if target_sequence is not None:
                raise PublicControlError(
                    f"target protein ID is duplicated in the proteome: {identifier}"
                )
            target_sequence = sequence
    if target_sequence is None:
        raise PublicControlError(
            f"target protein is absent from the supplied proteome: "
            f"{spec.target_protein_id}"
        )
    if len(target_sequence) != spec.target_sequence_length:
        raise PublicControlError(
            "target catalogue sequence length does not match ground truth"
        )
    target_digest = hashlib.sha256(target_sequence.encode("ascii")).hexdigest()
    if target_digest != spec.target_sequence_sha256:
        raise PublicControlError(
            "target catalogue protein sequence does not match ground truth"
        )
    if tuple(exact_identifiers) != spec.expected_exact_catalogue_records:
        raise PublicControlError(
            "exact-sequence catalogue records do not match ground truth: "
            f"{exact_identifiers} != {list(spec.expected_exact_catalogue_records)}"
        )
    return target_sequence, target_digest


def _entity_polymer_sequences(path: Path) -> tuple[str, ...]:
    try:
        block = gemmi.cif.read_file(str(path)).sole_block()
    except (RuntimeError, ValueError) as error:
        raise PublicControlError(
            f"cannot parse coordinate mmCIF {path}: {error}"
        ) from error
    sequences = tuple(
        canonical_sequence(value.strip().strip(";"))
        for value in block.find_values("_entity_poly.pdbx_seq_one_letter_code_can")
    )
    if not sequences:
        raise PublicControlError(
            f"coordinate mmCIF has no canonical polymer sequence: {path}"
        )
    return sequences


def _sequence_with_digest(sequences: Iterable[str], digest: str, *, label: str) -> str:
    matches = [
        sequence
        for sequence in sequences
        if hashlib.sha256(sequence.encode("ascii")).hexdigest() == digest
    ]
    if len(matches) != 1:
        raise PublicControlError(
            f"{label} must contain exactly one entity sequence with SHA-256 {digest}"
        )
    return matches[0]


def _one_based_fragment(sequence: str, start: int, end: int, *, label: str) -> str:
    if start < 1 or end < start or end > len(sequence):
        raise PublicControlError(
            f"{label} range {start}-{end} is outside a {len(sequence)}-residue sequence"
        )
    return sequence[start - 1 : end]


def _atomic_gemmi_mtz(
    structure_factors: Path,
    output: Path,
    spec: DerivedMtzSpec,
    *,
    target_pdb_id: str,
) -> str:
    try:
        document = gemmi.cif.read_file(str(structure_factors))
        reflection_blocks = gemmi.as_refln_blocks(document)
        if len(reflection_blocks) != 1:
            raise PublicControlError(
                "public-control structure-factor CIF must contain one reflection block"
            )
        mtz = gemmi.CifToMtz().convert_block_to_mtz(reflection_blocks[0])
        mtz.ensure_asu()
        mtz.sort()
        mtz.history = [
            *mtz.history,
            f"nf-genome_to_diffraction public control PDB {target_pdb_id}",
        ]
    except (RuntimeError, ValueError) as error:
        raise PublicControlError(
            f"cannot convert public structure factors to MTZ: {error}"
        ) from error

    labels = {column.label for column in mtz.columns}
    required_labels = {
        *spec.observation_labels.split(","),
        spec.free_flag_labels,
    }
    if not required_labels <= labels:
        raise PublicControlError(
            f"derived MTZ lacks required columns: {sorted(required_labels - labels)}"
        )
    if mtz.nreflections != spec.reflection_count:
        raise PublicControlError(
            f"derived MTZ reflection count differs from ground truth: "
            f"{mtz.nreflections} != {spec.reflection_count}"
        )
    if mtz.spacegroup is None or mtz.spacegroup.xhm() != spec.space_group:
        actual = None if mtz.spacegroup is None else mtz.spacegroup.xhm()
        raise PublicControlError(
            f"derived MTZ space group differs from ground truth: "
            f"{actual} != {spec.space_group}"
        )
    for actual, expected in zip(mtz.cell.parameters, spec.unit_cell, strict=True):
        if abs(actual - expected) > 0.001:
            raise PublicControlError(
                "derived MTZ unit cell differs from ground truth: "
                f"{mtz.cell.parameters} != {spec.unit_cell}"
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        mtz.write_to_file(str(temporary))
        digest = _verify_file_identity(
            temporary,
            expected_sha256=spec.sha256,
            expected_size=None,
            progress=False,
            label="derived MTZ",
        )
        os.replace(temporary, output)
        return digest
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _atomic_polymer_chain_model(
    source: Path, output: Path, model_spec: MrModelSpec
) -> str:
    try:
        structure = gemmi.read_structure(str(source))
        selected = gemmi.Selection(
            f"/1/{model_spec.chain_id};polymer"
        ).copy_structure_selection(structure)
    except (RuntimeError, ValueError) as error:
        raise PublicControlError(
            f"cannot extract MR model from {source}: {error}"
        ) from error
    if len(selected) != 1 or len(selected[0]) != 1:
        raise PublicControlError(
            f"MR model selection did not yield exactly one chain: {model_spec.model_id}"
        )
    chain = selected[0][0]
    if chain.name != model_spec.chain_id or len(chain) != len(chain.get_polymer()):
        raise PublicControlError(
            f"MR model is not one polymer-only chain: {model_spec.model_id}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        selected.write_minimal_pdb(str(temporary))
        digest = _verify_file_identity(
            temporary,
            expected_sha256=model_spec.expected_model_sha256,
            expected_size=None,
            progress=False,
            label=model_spec.model_id,
        )
        os.replace(temporary, output)
        return digest
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _write_target_fasta(
    path: Path, identifier: str, sequence: str, *, target_pdb_id: str
) -> None:
    lines = [f">{identifier} public positive control PDB {target_pdb_id}"]
    lines.extend(sequence[index : index + 80] for index in range(0, len(sequence), 80))
    atomic_write_text(path, "\n".join(lines) + "\n")


def prepare_public_control(
    request: PublicControlPreparationRequest,
) -> PublicControlPreparationResult:
    """Prepare and verify the tracked public positive control outside Git."""

    if request.storage_limit_bytes < 1 or request.minimum_free_bytes < 0:
        raise ValueError("public-control storage bounds must be non-negative")
    spec = load_public_control_spec(request.specification)
    gemmi_version = _gemmi_version()
    if gemmi_version != spec.derived_mtz.gemmi_version:
        raise PublicControlError(
            "Gemmi version differs from the frozen MTZ conversion: "
            f"{gemmi_version} != {spec.derived_mtz.gemmi_version}"
        )
    output_root = _safe_output_root(request.output_directory)
    if (request.proteome_faa is None) == (request.catalogue_manifest is None):
        raise PublicControlError(
            "supply exactly one of proteome_faa or catalogue_manifest"
        )
    if request.catalogue_manifest is not None:
        catalogue_path = _verify_regular_file(
            request.catalogue_manifest, label="catalogue manifest"
        )
        try:
            catalogue_document = CatalogueManifest.model_validate_json(
                catalogue_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise PublicControlError(
                f"invalid catalogue manifest {catalogue_path}: {error}"
            ) from error
        matches = [
            entry
            for entry in catalogue_document.catalogues
            if entry.catalogue_id == spec.catalogue_id
            and entry.assembly_accession == spec.assembly_accession
        ]
        if len(matches) != 1:
            raise PublicControlError(
                "catalogue manifest does not uniquely bind the public-control "
                "catalogue and assembly"
            )
        proteome_candidate = Path(matches[0].proteome_faa)
    else:
        assert request.proteome_faa is not None
        proteome_candidate = request.proteome_faa
    proteome = _verify_regular_file(proteome_candidate, label="proteome FASTA")
    _verify_file_identity(
        proteome,
        expected_sha256=spec.expected_proteome_sha256,
        expected_size=None,
        progress=request.progress,
        label="frozen proteome FASTA",
    )
    target_sequence, target_digest = _target_catalogue_sequence(
        proteome, spec, progress=request.progress
    )

    source_directory = output_root / "sources"
    source_directory.mkdir(parents=True, exist_ok=True)
    source_paths: dict[str, Path] = {}
    download_records: dict[str, dict[str, object]] = {}
    for resource in tqdm(
        spec.resources,
        desc="Prepare public sources",
        unit="resource",
        disable=not request.progress,
    ):
        path, metadata = _ensure_resource(
            resource,
            source_directory=source_directory,
            storage_root=output_root,
            request=request,
        )
        source_paths[resource.role] = path
        download_records[resource.role] = {
            "reused": metadata is None,
            "metadata": None if metadata is None else asdict(metadata),
        }

    catalogue_fragment = _one_based_fragment(
        target_sequence,
        spec.target_construct.catalogue_start,
        spec.target_construct.catalogue_end,
        label="catalogue construct",
    )
    target_entities = _entity_polymer_sequences(source_paths["target_coordinates"])
    target_entity = _sequence_with_digest(
        target_entities,
        spec.target_construct.coordinate_sequence_sha256,
        label="target coordinates",
    )
    if len(target_entity) != spec.target_construct.coordinate_sequence_length:
        raise PublicControlError(
            "target coordinate entity length differs from the frozen construct"
        )
    coordinate_fragment = _one_based_fragment(
        target_entity,
        spec.target_construct.coordinate_match_start,
        spec.target_construct.coordinate_match_end,
        label="target-coordinate construct",
    )
    if coordinate_fragment != catalogue_fragment:
        raise PublicControlError(
            "target coordinate construct does not match the frozen catalogue segment"
        )
    for model_spec in spec.mr_models:
        model_entities = _entity_polymer_sequences(source_paths[model_spec.source_role])
        model_entity = _sequence_with_digest(
            model_entities,
            model_spec.source_sequence_sha256,
            label=model_spec.model_id,
        )
        if model_spec.leakage_class == "operational_exact":
            assert model_spec.target_fragment_start_in_source is not None
            assert model_spec.target_fragment_end_in_source is not None
            model_fragment = _one_based_fragment(
                model_entity,
                model_spec.target_fragment_start_in_source,
                model_spec.target_fragment_end_in_source,
                label=f"{model_spec.model_id} target fragment",
            )
            if model_fragment != catalogue_fragment:
                raise PublicControlError(
                    "operational exact MR source does not match the catalogue "
                    f"construct: {model_spec.model_id}"
                )

    derived_directory = output_root / "derived"
    model_directory = output_root / "models"
    manifest_directory = output_root / "manifests"
    target_fasta = derived_directory / f"{spec.target_protein_id}.faa"
    mtz_path = derived_directory / spec.derived_mtz.filename
    _write_target_fasta(
        target_fasta,
        spec.target_protein_id,
        target_sequence,
        target_pdb_id=spec.target_pdb_id,
    )
    mtz_digest = _atomic_gemmi_mtz(
        source_paths["target_structure_factors"],
        mtz_path,
        spec.derived_mtz,
        target_pdb_id=spec.target_pdb_id,
    )

    model_paths: dict[str, Path] = {}
    model_digests: dict[str, str] = {}
    for model_spec in spec.mr_models:
        output = model_directory / model_spec.filename
        model_paths[model_spec.leakage_class] = output
        model_digests[model_spec.leakage_class] = _atomic_polymer_chain_model(
            source_paths[model_spec.source_role], output, model_spec
        )

    catalogue_manifest = CatalogueManifest(
        schema_version="1.0",
        catalogues=(
            CatalogueEntry(
                catalogue_id=spec.catalogue_id,
                proteome_faa=str(proteome),
                annotation_provider=spec.annotation_provider,
                annotation_version=spec.annotation_version,
                assembly_accession=spec.assembly_accession,
                assembly_version=spec.assembly_version,
                is_contaminant_catalogue=False,
                notes=f"Public positive control {spec.control_id}",
            ),
        ),
    )
    crystal_manifest = CrystalManifest(
        schema_version="1.0",
        crystals=(
            CrystalEntry(
                crystal_id=spec.control_id,
                mtz=str(mtz_path.resolve(strict=True)),
                catalogue_id=spec.catalogue_id,
                obs_labels=spec.derived_mtz.observation_labels,
                free_flag_labels=spec.derived_mtz.free_flag_labels,
                allow_remote_sequence_submission=False,
                notes=(
                    "Public operational positive control; no SDS-PAGE evidence. "
                    "Ground truth is held in the separate generated manifest."
                ),
            ),
        ),
    )
    catalogue_manifest_path = manifest_directory / "catalogues.json"
    crystal_manifest_path = manifest_directory / "crystals.json"
    atomic_write_json(
        catalogue_manifest_path, catalogue_manifest.model_dump(mode="json")
    )
    atomic_write_json(crystal_manifest_path, crystal_manifest.model_dump(mode="json"))

    resource_records = {
        resource.role: {
            "pdb_id": resource.pdb_id,
            "requested_url": resource.url,
            "path": str(source_paths[resource.role]),
            "sha256": resource.sha256,
            "size_bytes": resource.size_bytes,
            **download_records[resource.role],
        }
        for resource in spec.resources
    }
    preparation_manifest_path = manifest_directory / "preparation.json"
    atomic_write_json(
        preparation_manifest_path,
        {
            "schema_version": "1.0",
            "control_id": spec.control_id,
            "prepared_at": utc_now().isoformat(),
            "software": {
                "nf_genome_to_diffraction": __version__,
                "gemmi": gemmi_version,
            },
            "benchmark_class": spec.benchmark_class,
            "catalogue_ground_truth": {
                "assembly_accession": spec.assembly_accession,
                "catalogue_id": spec.catalogue_id,
                "target_protein_id": spec.target_protein_id,
                "target_sequence_sha256": target_digest,
                "target_sequence_length": len(target_sequence),
                "exact_catalogue_records": list(spec.expected_exact_catalogue_records),
                "construct_mapping": spec.target_construct.model_dump(mode="json"),
            },
            "crystallographic_ground_truth": {
                "target_pdb_id": spec.target_pdb_id,
                "target_pdb_version": spec.target_pdb_version,
                "expected_asu_copy_count": spec.expected_asu_copy_count,
                "biological_assembly_copy_count": (spec.biological_assembly_copy_count),
                "asu_model": spec.asu_model,
                "processing_software": list(spec.processing_software),
                "sds_page_evidence": spec.sds_page_evidence,
            },
            "resources": resource_records,
            "derived": {
                "mtz": {
                    "path": str(mtz_path.resolve(strict=True)),
                    "sha256": mtz_digest,
                    "observation_labels": spec.derived_mtz.observation_labels,
                    "free_flag_labels": spec.derived_mtz.free_flag_labels,
                },
                "target_fasta": {
                    "path": str(target_fasta.resolve(strict=True)),
                    "sha256": sha256_file(target_fasta),
                },
                "exact_mr_model": {
                    "path": str(model_paths["operational_exact"].resolve(strict=True)),
                    "sha256": model_digests["operational_exact"],
                },
                "homolog_mr_model": {
                    "path": str(model_paths["homolog_challenge"].resolve(strict=True)),
                    "sha256": model_digests["homolog_challenge"],
                },
            },
            "score_gate": spec.score_gate.model_dump(mode="json"),
            "database_exclusions_for_homolog_challenge": list(
                spec.database_exclusions_for_homolog_challenge
            ),
            "limitations": list(spec.limitations),
        },
    )
    _LOGGER.info(
        "public positive control prepared",
        extra={
            "control_id": spec.control_id,
            "output_directory": str(output_root),
            "mtz_sha256": mtz_digest,
        },
    )
    return PublicControlPreparationResult(
        control_id=spec.control_id,
        preparation_manifest=preparation_manifest_path,
        crystal_manifest=crystal_manifest_path,
        catalogue_manifest=catalogue_manifest_path,
        target_fasta=target_fasta,
        mtz=mtz_path,
        exact_mr_model=model_paths["operational_exact"],
        homolog_mr_model=model_paths["homolog_challenge"],
    )
