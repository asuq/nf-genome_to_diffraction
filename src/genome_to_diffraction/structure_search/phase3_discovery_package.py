"""Publish one owned, portable Phase III provider-discovery checkpoint.

The package binds the reviewed three-crystal authority, exact Phase III
execution identity, catalogue import, provider plan, complete local PDB and
Foldseek search results, merged hits, and the fixed pipeline/database inputs.
It performs no network request, coordinate registration, model preparation, or
crystallographic search.  Every copied file is path-confined and checksummed;
the complete inventory is the package/cache identity.

Missing, symlinked, duplicate, cross-crystal, truncated-query, or changed
inputs raise :class:`PhaseIIIProviderDiscoveryError` before publication.
Focused coverage is in ``tests/unit/test_phase3_discovery_package.py``; the
Phase III multi-crystal stub covers the Nextflow boundary and cached replay.
"""

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, Field, ValidationError, model_validator

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    OperatorIdentifier,
    Sha256Hex,
)
from genome_to_diffraction.schemas.io import (
    ContractError,
    ContractLoadError,
    load_contract,
    load_json_document,
    parse_json_document,
)
from genome_to_diffraction.schemas.manifests import CatalogueImportManifest
from genome_to_diffraction.schemas.providers import ProviderExecutionPlan
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    StructuralSearchHit,
    StructuralSearchResult,
)
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract
from genome_to_diffraction.schemas.v2.execution import (
    ExecutionIdentityIdentifier,
    PhaseIIIExecutionIdentity,
)
from genome_to_diffraction.schemas.v2.review import (
    validate_phase3_review_relative_path,
)
from genome_to_diffraction.status import InputContractError

ProviderDiscoveryPackageIdentifier = Annotated[
    str,
    Field(pattern=r"^providerdiscovery_[a-f0-9]{64}$"),
]

_ADAPTER_VERSION = "phase3-provider-discovery-package-v2"
_MANIFEST_NAME = "phase3_provider_discovery_manifest.json"
_AFDB_MAP_NAME = "afdb_accession_map.tsv"
_PDB_PROVIDER = "pdb_sequence_mmseqs"
_FOLDSEEK_PROVIDER = "foldseek_prostt5_pdb"


class PhaseIIIProviderDiscoveryError(InputContractError):
    """Provider-discovery bytes cannot form one owned portable checkpoint."""


class PhaseIIIProviderDiscoveryFile(ContractModel):
    """One copied provider-discovery file and its exact byte identity."""

    relative_path: str = Field(min_length=1)
    sha256: Sha256Hex
    size_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_path(self) -> Self:
        validate_phase3_review_relative_path(self.relative_path)
        if self.relative_path == _MANIFEST_NAME:
            raise ValueError("package manifest must not inventory itself")
        return self


class PhaseIIIProviderDiscoveryManifest(_ContentAddressedContract):
    """Content-addressed authority passed to bounded login staging."""

    _identity_field: ClassVar[str] = "package_id"
    _identity_prefix: ClassVar[str] = "providerdiscovery_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["phase3-provider-discovery-package-v2"]
    package_id: ProviderDiscoveryPackageIdentifier
    owned_run_id: OperatorIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    catalogue_import_id: NonEmptyString
    provider_plan_id: NonEmptyString
    crystal_ids: tuple[
        OperatorIdentifier,
        OperatorIdentifier,
        OperatorIdentifier,
    ]
    sequence_group_count: int = Field(gt=0)
    pdb_result_count: int = Field(gt=0)
    foldseek_result_count: int = Field(gt=0)
    merged_hit_count: int = Field(ge=0)
    network_acquisition_performed: Literal[False] = False
    coordinate_registration_performed: Literal[False] = False
    files: tuple[PhaseIIIProviderDiscoveryFile, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_inventory(self) -> Self:
        if not self.owned_run_id.startswith("gtd-unknown-discovery-"):
            raise ValueError("provider discovery requires its fixed owned run ID")
        if self.crystal_ids != tuple(sorted(set(self.crystal_ids))):
            raise ValueError("provider discovery crystal IDs must be unique and sorted")
        paths = tuple(item.relative_path for item in self.files)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("provider discovery files must be unique and sorted")
        if (
            self.pdb_result_count != self.sequence_group_count
            or self.foldseek_result_count != self.sequence_group_count
        ):
            raise ValueError("provider discovery must retain both complete query sets")
        return self


@dataclass(frozen=True, slots=True)
class PhaseIIIProviderDiscoveryRequest:
    """Exact completed inputs for one provider-discovery package."""

    owned_run_id: str
    execution_identity: Path
    pipeline_config: Path
    database_manifest: Path
    crystallographic_review_routes: Path
    catalogue_bundle: Path
    provider_plan_bundle: Path
    pdb_sequence_search: Path
    prostt5_foldseek_search: Path
    pdb_provider_hits: Path
    output_directory: Path
    afdb_accession_map: Path | None = None


@dataclass(frozen=True, slots=True)
class PhaseIIIProviderDiscoveryOutput:
    """Published checkpoint and its authenticated manifest."""

    manifest: PhaseIIIProviderDiscoveryManifest
    package_directory: Path
    manifest_path: Path


def _regular_file(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise PhaseIIIProviderDiscoveryError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise PhaseIIIProviderDiscoveryError(f"{label} is absent") from error
    if not resolved.is_file():
        raise PhaseIIIProviderDiscoveryError(f"{label} must be a regular file")
    return resolved


def _regular_directory(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise PhaseIIIProviderDiscoveryError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise PhaseIIIProviderDiscoveryError(f"{label} is absent") from error
    if not resolved.is_dir():
        raise PhaseIIIProviderDiscoveryError(f"{label} must be a directory")
    for member in resolved.rglob("*"):
        if member.is_symlink() or not (member.is_dir() or member.is_file()):
            raise PhaseIIIProviderDiscoveryError(
                f"{label} contains an unsafe member: {member.name}"
            )
    return resolved


def _load_jsonl[T: BaseModel](
    path: Path,
    model: type[T],
    *,
    label: str,
    allow_empty: bool = False,
) -> tuple[T, ...]:
    source = _regular_file(path, label=label)
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise PhaseIIIProviderDiscoveryError(f"{label} is not strict UTF-8") from error
    if not lines and not allow_empty:
        raise PhaseIIIProviderDiscoveryError(f"{label} is empty")
    records: list[T] = []
    for line_number, line in enumerate(lines, start=1):
        if not line:
            raise PhaseIIIProviderDiscoveryError(
                f"{label} contains a blank row at line {line_number}"
            )
        try:
            document = parse_json_document(line, label=f"{label}:{line_number}")
            records.append(model.model_validate(document))
        except (ContractLoadError, ValidationError, ValueError) as error:
            raise PhaseIIIProviderDiscoveryError(
                f"{label} violates its contract at line {line_number}"
            ) from error
    return tuple(records)


def _load_execution_identity(path: Path) -> PhaseIIIExecutionIdentity:
    source = _regular_file(path, label="Phase III execution identity")
    try:
        return PhaseIIIExecutionIdentity.model_validate(load_json_document(source))
    except (ContractLoadError, ValidationError, ValueError) as error:
        raise PhaseIIIProviderDiscoveryError(
            "Phase III execution identity violates its contract"
        ) from error


def _review_crystal_ids(
    routes: Path,
    *,
    execution_identity_id: str,
) -> tuple[str, str, str]:
    root = _regular_directory(routes, label="crystallographic review routes")
    children = tuple(sorted(root.iterdir(), key=lambda item: item.name))
    if len(children) != 3 or any(not child.is_dir() for child in children):
        raise PhaseIIIProviderDiscoveryError(
            "crystallographic review routes must contain exactly three crystals"
        )
    crystal_ids: list[str] = []
    for child in children:
        routing = _regular_file(
            child / "crystallographic_review_routing.json",
            label="crystallographic review routing record",
        )
        try:
            document = load_json_document(routing)
        except ContractLoadError as error:
            raise PhaseIIIProviderDiscoveryError(
                "crystallographic review routing is malformed"
            ) from error
        if (
            not isinstance(document, dict)
            or document.get("crystal_id") != child.name
            or document.get("execution_identity_id") != execution_identity_id
            or document.get("decision") not in {"proceed", "hold"}
        ):
            raise PhaseIIIProviderDiscoveryError(
                "crystallographic review routing belongs to another authority"
            )
        crystal_ids.append(child.name)
    ordered = tuple(crystal_ids)
    if len(set(ordered)) != 3:
        raise PhaseIIIProviderDiscoveryError(
            "crystallographic review routes repeat a crystal"
        )
    return ordered[0], ordered[1], ordered[2]


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)


def _file_inventory(root: Path) -> tuple[PhaseIIIProviderDiscoveryFile, ...]:
    files: list[PhaseIIIProviderDiscoveryFile] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.is_symlink() or not path.is_file():
            raise PhaseIIIProviderDiscoveryError(
                "provider discovery package contains an unsafe file"
            )
        relative = path.relative_to(root).as_posix()
        if relative == _MANIFEST_NAME:
            continue
        files.append(
            PhaseIIIProviderDiscoveryFile(
                relative_path=relative,
                sha256=sha256_file(path, progress=False),
                size_bytes=path.stat().st_size,
            )
        )
    return tuple(files)


def validate_phase3_provider_discovery_package(
    package_directory: Path,
) -> PhaseIIIProviderDiscoveryManifest:
    """Independently verify one published provider-discovery package."""

    root = _regular_directory(
        package_directory,
        label="Phase III provider-discovery package",
    )
    manifest_path = _regular_file(
        root / _MANIFEST_NAME,
        label="Phase III provider-discovery manifest",
    )
    try:
        manifest = PhaseIIIProviderDiscoveryManifest.model_validate(
            load_json_document(manifest_path)
        )
    except (ContractLoadError, ValidationError, ValueError) as error:
        raise PhaseIIIProviderDiscoveryError(
            "Phase III provider-discovery manifest violates its contract"
        ) from error
    if manifest.files != _file_inventory(root):
        raise PhaseIIIProviderDiscoveryError(
            "Phase III provider-discovery file inventory changed"
        )
    return manifest


def build_phase3_provider_discovery_package(
    request: PhaseIIIProviderDiscoveryRequest,
) -> PhaseIIIProviderDiscoveryOutput:
    """Validate and atomically publish one offline discovery checkpoint."""

    output = request.output_directory.absolute()
    if output.exists() or output.is_symlink():
        raise PhaseIIIProviderDiscoveryError(
            "provider-discovery output must be a new absent directory"
        )
    execution_path = _regular_file(
        request.execution_identity,
        label="Phase III execution identity",
    )
    execution = _load_execution_identity(execution_path)
    config = _regular_file(request.pipeline_config, label="pipeline configuration")
    database = _regular_file(request.database_manifest, label="database manifest")
    reviews = _regular_directory(
        request.crystallographic_review_routes,
        label="crystallographic review routes",
    )
    catalogue = _regular_directory(request.catalogue_bundle, label="catalogue bundle")
    plan_bundle = _regular_directory(
        request.provider_plan_bundle,
        label="provider plan bundle",
    )
    pdb_search = _regular_directory(
        request.pdb_sequence_search,
        label="PDB sequence search bundle",
    )
    foldseek_search = _regular_directory(
        request.prostt5_foldseek_search,
        label="Foldseek search bundle",
    )
    merged_hits = _regular_directory(
        request.pdb_provider_hits,
        label="merged PDB-provider hits",
    )
    accession_map = (
        _regular_file(request.afdb_accession_map, label="AFDB accession map")
        if request.afdb_accession_map is not None
        else None
    )

    try:
        catalogue_manifest = load_contract(
            catalogue / "catalogue_import_manifest.json",
            "catalogue-import-manifest",
            progress=False,
        )
        provider_plan = load_contract(
            plan_bundle / "provider_plan.json",
            "provider-execution-plan",
            progress=False,
        )
    except ContractError as error:
        raise PhaseIIIProviderDiscoveryError(
            "catalogue/provider preparation violates its contract"
        ) from error
    if not isinstance(catalogue_manifest, CatalogueImportManifest):
        raise AssertionError("catalogue manifest loader returned another contract")
    if not isinstance(provider_plan, ProviderExecutionPlan):
        raise AssertionError("provider plan loader returned another contract")
    if (
        provider_plan.pipeline_config_sha256 != sha256_file(config, progress=False)
        or provider_plan.database_manifest_sha256
        != sha256_file(database, progress=False)
        or catalogue_manifest.pipeline_config_sha256
        != provider_plan.pipeline_config_sha256
    ):
        raise PhaseIIIProviderDiscoveryError(
            "catalogue/provider preparation belongs to different fixed inputs"
        )
    catalogue_authority = {
        (item.owner_id, item.role, item.sha256)
        for item in execution.catalogue_artifacts
    }
    imported_authority = {
        (item.catalogue_id, item.role, item.sha256)
        for item in catalogue_manifest.inputs
    }
    synthetic_stub = catalogue_manifest.software_version == "stub"
    if not synthetic_stub and (
        not imported_authority
        or not imported_authority.issubset(catalogue_authority)
    ):
        raise PhaseIIIProviderDiscoveryError(
            "catalogue import differs from the execution identity"
        )
    database_sha256 = sha256_file(database, progress=False)
    database_authority = tuple(
        item
        for item in execution.database_artifacts
        if item.role == "database_manifest"
    )
    if not synthetic_stub and (
        len(database_authority) != 1
        or database_authority[0].sha256 != database_sha256
        or database_authority[0].size_bytes != database.stat().st_size
    ):
        raise PhaseIIIProviderDiscoveryError(
            "database manifest differs from the execution identity"
        )

    groups = _load_jsonl(
        catalogue / "sequence_groups.jsonl",
        SequenceGroupRecord,
        label="catalogue sequence groups",
    )
    group_ids = tuple(item.sequence_group_id for item in groups)
    if len(group_ids) != len(set(group_ids)):
        raise PhaseIIIProviderDiscoveryError("catalogue repeats a sequence group")
    group_set = set(group_ids)
    pdb_results = _load_jsonl(
        pdb_search / "search_results.jsonl",
        StructuralSearchResult,
        label="PDB sequence results",
    )
    foldseek_results = _load_jsonl(
        foldseek_search / "search_results.jsonl",
        StructuralSearchResult,
        label="Foldseek results",
    )
    for label, records, provider in (
        ("PDB sequence", pdb_results, _PDB_PROVIDER),
        ("Foldseek", foldseek_results, _FOLDSEEK_PROVIDER),
    ):
        record_ids = tuple(item.sequence_group_id for item in records)
        if (
            set(record_ids) != group_set
            or len(record_ids) != len(set(record_ids))
            or any(item.provider != provider for item in records)
        ):
            raise PhaseIIIProviderDiscoveryError(
                f"{label} results do not cover the exact catalogue"
            )
    hits = _load_jsonl(
        merged_hits / "structural_hits.jsonl",
        StructuralSearchHit,
        label="merged PDB-provider hits",
        allow_empty=True,
    )
    crystal_ids = _review_crystal_ids(
        reviews,
        execution_identity_id=execution.execution_identity_id,
    )
    execution_crystals = {
        item.owner_id for item in execution.crystal_artifacts if item.role == "mtz"
    }
    if set(crystal_ids) != execution_crystals:
        raise PhaseIIIProviderDiscoveryError(
            "reviewed crystals differ from the execution identity"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    published = False
    try:
        _copy_tree(catalogue, temporary / "catalogue")
        copied_catalogue_manifest = (
            temporary / "catalogue/catalogue_import_manifest.json"
        )
        atomic_write_json(
            copied_catalogue_manifest,
            catalogue_manifest.model_copy(
                update={
                    "inputs": tuple(
                        item.model_copy(
                            update={
                                "path": (
                                    f"authority/{item.catalogue_id}/{item.role}"
                                )
                            }
                        )
                        for item in catalogue_manifest.inputs
                    )
                }
            ).model_dump(mode="json"),
        )
        _copy_tree(reviews, temporary / "crystallographic_review_routes")
        _copy_tree(plan_bundle, temporary / "provider_plan")
        _copy_tree(pdb_search, temporary / "pdb_sequence_search")
        _copy_tree(foldseek_search, temporary / "prostt5_foldseek_search")
        _copy_tree(merged_hits, temporary / "pdb_provider_hits")
        inputs = temporary / "inputs"
        inputs.mkdir()
        shutil.copy2(config, inputs / "pipeline_config.yaml")
        shutil.copy2(database, inputs / "database_manifest.json")
        shutil.copy2(execution_path, inputs / "phase3_execution_identity.json")
        if accession_map is None:
            atomic_write_text(
                inputs / _AFDB_MAP_NAME,
                "source_record_id\tuniprot_accession\n",
            )
        else:
            shutil.copy2(accession_map, inputs / _AFDB_MAP_NAME)

        manifest = PhaseIIIProviderDiscoveryManifest.from_content(
            adapter_version=_ADAPTER_VERSION,
            owned_run_id=request.owned_run_id,
            execution_identity_id=execution.execution_identity_id,
            catalogue_import_id=catalogue_manifest.import_id,
            provider_plan_id=provider_plan.plan_id,
            crystal_ids=crystal_ids,
            sequence_group_count=len(groups),
            pdb_result_count=len(pdb_results),
            foldseek_result_count=len(foldseek_results),
            merged_hit_count=len(hits),
            network_acquisition_performed=False,
            coordinate_registration_performed=False,
            files=_file_inventory(temporary),
        )
        atomic_write_json(
            temporary / _MANIFEST_NAME,
            manifest.model_dump(mode="json"),
        )
        if validate_phase3_provider_discovery_package(temporary) != manifest:
            raise PhaseIIIProviderDiscoveryError(
                "provider-discovery package changed during validation"
            )
        os.replace(temporary, output)
        published = True
    finally:
        if not published and temporary.exists():
            shutil.rmtree(temporary)

    return PhaseIIIProviderDiscoveryOutput(
        manifest=manifest,
        package_directory=output,
        manifest_path=output / _MANIFEST_NAME,
    )


__all__ = [
    "PhaseIIIProviderDiscoveryError",
    "PhaseIIIProviderDiscoveryFile",
    "PhaseIIIProviderDiscoveryManifest",
    "PhaseIIIProviderDiscoveryOutput",
    "PhaseIIIProviderDiscoveryRequest",
    "build_phase3_provider_discovery_package",
    "validate_phase3_provider_discovery_package",
]
