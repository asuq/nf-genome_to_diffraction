"""Validate and prepare the public methanogen/methanotroph X-ray panel.

The panel freezes public source identities, catalogue-to-construct mappings, and
expected prototype outcomes.  Preparation downloads only RCSB coordinate and
structure-factor files, verifies them, and derives deterministic MTZ files.
Genome catalogues remain operator-supplied inputs to individual control runs.
"""

import hashlib
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Self

import gemmi
import yaml
from pydantic import Field, model_validator
from tqdm import tqdm

from genome_to_diffraction import __version__
from genome_to_diffraction.benchmarks.public_control import (
    DerivedMtzSpec,
    PublicControlError,
    PublicResourceSpec,
    TargetConstructSpec,
    _atomic_gemmi_mtz,
    _ensure_resource,
    _gemmi_version,
    load_public_control_spec,
)
from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    OperatorIdentifier,
    PositiveFloat,
    PositiveInt,
    Sha256Hex,
    UtcTimestamp,
)
from genome_to_diffraction.time import utc_now

_LOGGER = logging.getLogger("genome_to_diffraction.benchmarks.panel")


class PanelCatalogueTargetSpec(ContractModel):
    """One catalogue protein mapped to one coordinate polymer entity."""

    protein_id: OperatorIdentifier
    sequence_length: PositiveInt
    sequence_sha256: Sha256Hex
    asu_copy_count: PositiveInt
    construct_mapping: TargetConstructSpec


class PublicPanelEntrySpec(ContractModel):
    """Frozen source and scientific expectation for one public PDB entry."""

    control_id: OperatorIdentifier
    pdb_id: str = Field(pattern=r"^[0-9A-Z]{4}$")
    pdb_version: NonEmptyString
    organism: NonEmptyString
    metabolic_group: Literal["methanogen", "methanotroph"]
    molecular_system: NonEmptyString
    expected_prototype_outcome: Literal["positive", "assumption_violation"]
    qualification_status: Literal[
        "runnable_control", "source_qualified", "assumption_violation"
    ]
    assembly_accession: NonEmptyString
    assembly_version: NonEmptyString
    annotation_provider: NonEmptyString
    annotation_version: NonEmptyString
    expected_proteome_sha256: Sha256Hex
    catalogue_targets: tuple[PanelCatalogueTargetSpec, ...] = Field(min_length=1)
    asu_distinct_protein_species: PositiveInt
    asu_protein_copy_count: PositiveInt
    biological_assembly_protein_copy_count: PositiveInt
    resolution_angstrom: PositiveFloat
    processing_software: tuple[NonEmptyString, ...] = Field(min_length=1)
    coordinates: PublicResourceSpec
    structure_factors: PublicResourceSpec
    reflection_block_count: PositiveInt
    derived_mtz: DerivedMtzSpec | None
    active_control_specification: str | None = Field(
        default=None, pattern=r"^[0-9A-Za-z][0-9A-Za-z._-]*\.yaml$"
    )
    limitations: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_entry(self) -> Self:
        if self.coordinates.role != "target_coordinates":
            raise ValueError("panel coordinates must have target_coordinates role")
        if self.structure_factors.role != "target_structure_factors":
            raise ValueError(
                "panel structure factors must have target_structure_factors role"
            )
        if {
            self.coordinates.pdb_id,
            self.structure_factors.pdb_id,
        } != {self.pdb_id}:
            raise ValueError("panel source PDB IDs must match the entry PDB ID")
        if len(self.catalogue_targets) != self.asu_distinct_protein_species:
            raise ValueError("catalogue target count differs from ASU species count")
        if sum(target.asu_copy_count for target in self.catalogue_targets) != (
            self.asu_protein_copy_count
        ):
            raise ValueError("catalogue target copies differ from ASU copy count")
        target_ids = [target.protein_id for target in self.catalogue_targets]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("panel catalogue target IDs must be unique")
        if self.expected_prototype_outcome == "positive":
            if self.asu_distinct_protein_species != 1:
                raise ValueError("a positive ASU=nA control must have one species")
            if self.qualification_status == "assumption_violation":
                raise ValueError("positive entry cannot be an assumption violation")
        else:
            if self.asu_distinct_protein_species < 2:
                raise ValueError("an assumption violation must have multiple species")
            if self.qualification_status != "assumption_violation":
                raise ValueError("assumption violation status is required")
        if self.qualification_status == "runnable_control":
            if self.active_control_specification is None:
                raise ValueError("runnable control lacks its active specification")
        elif self.active_control_specification is not None:
            raise ValueError("only runnable controls may name an active specification")
        if self.reflection_block_count == 1 and self.derived_mtz is None:
            raise ValueError(
                "single-block panel entry lacks a derived MTZ ground truth"
            )
        if self.reflection_block_count != 1 and self.derived_mtz is not None:
            raise ValueError("multi-block panel entry must not imply one derived MTZ")
        return self


class PublicControlPanelSpec(ContractModel):
    """Versioned collection of diverse public crystallographic controls."""

    schema_version: Literal["1.0"]
    panel_id: OperatorIdentifier
    frozen_at: UtcTimestamp
    selection_policy: tuple[NonEmptyString, ...] = Field(min_length=1)
    entries: tuple[PublicPanelEntrySpec, ...] = Field(min_length=8, max_length=12)

    @model_validator(mode="after")
    def _validate_panel(self) -> Self:
        control_ids = [entry.control_id for entry in self.entries]
        pdb_ids = [entry.pdb_id for entry in self.entries]
        if len(control_ids) != len(set(control_ids)):
            raise ValueError("panel control IDs must be unique")
        if len(pdb_ids) != len(set(pdb_ids)):
            raise ValueError("panel PDB IDs must be unique")
        if {entry.metabolic_group for entry in self.entries} != {
            "methanogen",
            "methanotroph",
        }:
            raise ValueError("panel must include methanogens and methanotrophs")
        if not any(
            entry.expected_prototype_outcome == "assumption_violation"
            for entry in self.entries
        ):
            raise ValueError("panel must include an assumption-violation control")
        if (
            sum(
                entry.qualification_status == "runnable_control"
                for entry in self.entries
            )
            < 3
        ):
            raise ValueError("panel must contain at least three runnable controls")
        return self


@dataclass(frozen=True)
class PublicPanelPreparationRequest:
    """Bounded source-preparation request for the public panel."""

    specification: Path
    output_directory: Path
    download_missing: bool = True
    progress: bool = True
    storage_limit_bytes: int = 1024 * 1024 * 1024
    minimum_free_bytes: int = 128 * 1024 * 1024


@dataclass(frozen=True)
class PublicPanelPreparationResult:
    """Stable aggregate record emitted after panel source preparation."""

    panel_id: str
    entry_count: int
    preparation_manifest: Path


def load_public_control_panel(path: Path) -> PublicControlPanelSpec:
    """Load a panel and cross-check every referenced runnable control spec."""

    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise PublicControlError(f"public-control panel is not a file: {path}")
    try:
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
        panel = PublicControlPanelSpec.model_validate(payload)
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise PublicControlError(
            f"invalid public-control panel {resolved}: {error}"
        ) from error

    for entry in panel.entries:
        if entry.active_control_specification is None:
            continue
        control = load_public_control_spec(
            resolved.parent / entry.active_control_specification
        )
        if (
            control.control_id != entry.control_id
            or control.target_pdb_id != entry.pdb_id
        ):
            raise PublicControlError(
                f"panel and active control specification disagree: {entry.control_id}"
            )
        panel_target = entry.catalogue_targets[0]
        if (
            control.target_protein_id != panel_target.protein_id
            or control.target_sequence_sha256 != panel_target.sequence_sha256
            or control.target_construct != panel_target.construct_mapping
        ):
            raise PublicControlError(
                "panel and active control catalogue mapping disagree: "
                f"{entry.control_id}"
            )
    return panel


def _reflection_block_count(path: Path) -> int:
    try:
        return len(gemmi.as_refln_blocks(gemmi.cif.read_file(str(path))))
    except (RuntimeError, ValueError) as error:
        raise PublicControlError(
            f"cannot inspect public structure factors {path}: {error}"
        ) from error


def prepare_public_control_panel(
    request: PublicPanelPreparationRequest,
) -> PublicPanelPreparationResult:
    """Download, verify, and derive the ten public panel datasets outside Git."""

    if request.storage_limit_bytes < 1 or request.minimum_free_bytes < 0:
        raise ValueError("public-panel storage bounds must be non-negative")
    panel = load_public_control_panel(request.specification)
    request.output_directory.mkdir(parents=True, exist_ok=True)
    if request.output_directory.is_symlink() or not request.output_directory.is_dir():
        raise PublicControlError(
            f"public-panel output root is unsafe: {request.output_directory}"
        )
    output_root = request.output_directory.resolve(strict=True)
    gemmi_version = _gemmi_version()
    entry_records: list[dict[str, object]] = []
    _LOGGER.info(
        "preparing public control panel",
        extra={
            "panel_id": panel.panel_id,
            "entry_count": len(panel.entries),
            "output_directory": str(output_root),
        },
    )

    for entry in tqdm(
        panel.entries,
        desc="Prepare public panel",
        unit="structure",
        disable=not request.progress,
    ):
        entry_root = output_root / entry.control_id
        source_root = entry_root / "sources"
        source_root.mkdir(parents=True, exist_ok=True)
        source_records: dict[str, object] = {}
        source_paths: dict[str, Path] = {}
        for resource in (entry.coordinates, entry.structure_factors):
            path, metadata = _ensure_resource(
                resource,
                source_directory=source_root,
                storage_root=output_root,
                request=request,
            )
            source_paths[resource.role] = path
            source_records[resource.role] = {
                "path": str(path),
                "pdb_id": resource.pdb_id,
                "url": resource.url,
                "sha256": resource.sha256,
                "size_bytes": resource.size_bytes,
                "reused": metadata is None,
                "download": None if metadata is None else asdict(metadata),
            }

        actual_blocks = _reflection_block_count(
            source_paths["target_structure_factors"]
        )
        if actual_blocks != entry.reflection_block_count:
            raise PublicControlError(
                f"{entry.control_id} reflection-block count differs from ground "
                f"truth: {actual_blocks} != {entry.reflection_block_count}"
            )
        derived_record: dict[str, object] | None = None
        if entry.derived_mtz is not None:
            if gemmi_version != entry.derived_mtz.gemmi_version:
                raise PublicControlError(
                    "Gemmi version differs from the frozen panel conversion: "
                    f"{gemmi_version} != {entry.derived_mtz.gemmi_version}"
                )
            mtz_path = entry_root / "derived" / entry.derived_mtz.filename
            digest = _atomic_gemmi_mtz(
                source_paths["target_structure_factors"],
                mtz_path,
                entry.derived_mtz,
                target_pdb_id=entry.pdb_id,
            )
            derived_record = {
                "path": str(mtz_path.resolve(strict=True)),
                "sha256": digest,
                "reflection_count": entry.derived_mtz.reflection_count,
                "observation_labels": entry.derived_mtz.observation_labels,
                "free_flag_labels": entry.derived_mtz.free_flag_labels,
            }

        entry_manifest = entry_root / "preparation.json"
        record: dict[str, object] = {
            "schema_version": "1.0",
            "panel_id": panel.panel_id,
            "control_id": entry.control_id,
            "pdb_id": entry.pdb_id,
            "expected_prototype_outcome": entry.expected_prototype_outcome,
            "qualification_status": entry.qualification_status,
            "reflection_block_count": actual_blocks,
            "sources": source_records,
            "derived_mtz": derived_record,
            "catalogue_mapping_digest": hashlib.sha256(
                "".join(
                    target.sequence_sha256 for target in entry.catalogue_targets
                ).encode("ascii")
            ).hexdigest(),
        }
        atomic_write_json(entry_manifest, record)
        entry_records.append({**record, "entry_manifest": str(entry_manifest)})
        _LOGGER.info(
            "public panel entry prepared",
            extra={
                "panel_id": panel.panel_id,
                "control_id": entry.control_id,
                "pdb_id": entry.pdb_id,
                "qualification_status": entry.qualification_status,
            },
        )

    aggregate = output_root / "preparation.json"
    atomic_write_json(
        aggregate,
        {
            "schema_version": "1.0",
            "panel_id": panel.panel_id,
            "prepared_at": utc_now().isoformat(),
            "software": {
                "nf_genome_to_diffraction": __version__,
                "gemmi": gemmi_version,
            },
            "entry_count": len(entry_records),
            "entries": entry_records,
        },
    )
    _LOGGER.info(
        "public control panel prepared",
        extra={
            "panel_id": panel.panel_id,
            "entry_count": len(entry_records),
            "preparation_manifest": str(aggregate),
        },
    )
    return PublicPanelPreparationResult(
        panel_id=panel.panel_id,
        entry_count=len(entry_records),
        preparation_manifest=aggregate,
    )
