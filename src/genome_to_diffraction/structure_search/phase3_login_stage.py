"""Bounded login-side coordinate staging for Phase III unknown pass 1.

This adapter consumes only a validated owned provider-discovery package.  It
uses the existing provider-plan-bound PDB and AFDB adapters, fixes direct-PDB
selection at three hits per sequence group and 25 mappings globally, retains a
typed disabled ESM Atlas branch, verifies every referenced coordinate object,
and publishes one content-addressed provider preparation for the later offline
screen.  No sequence is submitted to a public service: PDB accessions and
explicit UniProt accessions are the only network identifiers.

Missing, changed, cross-owned, over-cap, unsupported-provider, or incomplete
outputs raise :class:`PhaseIIIProviderLoginStageError`.  The preparation ID and
complete copied-file inventory form the cache identity.  Focused coverage is in
``tests/unit/test_phase3_provider_login_stage.py``.
"""

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, ValidationError, model_validator

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.schemas.base import (
    ContractModel,
    OperatorIdentifier,
    Sha256Hex,
)
from genome_to_diffraction.schemas.io import (
    ContractError,
    ContractLoadError,
    load_contract,
    load_json_document,
)
from genome_to_diffraction.schemas.providers import (
    ProviderExecutionPlan,
    ProviderKey,
)
from genome_to_diffraction.schemas.results import CoordinateSourceRecord
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract
from genome_to_diffraction.schemas.v2.execution import (
    ExecutionIdentityIdentifier,
    PhaseIIIExecutionIdentity,
)
from genome_to_diffraction.schemas.v2.review import (
    validate_phase3_review_relative_path,
)
from genome_to_diffraction.status import InputContractError
from genome_to_diffraction.structure_search.afdb_exact import (
    AfdbExactRequest,
    search_afdb_exact,
)
from genome_to_diffraction.structure_search.pdb_coordinates import (
    PdbCoordinateRegistrationRequest,
    register_pdb_coordinates,
)
from genome_to_diffraction.structure_search.phase3_discovery_package import (
    PhaseIIIProviderDiscoveryError,
    validate_phase3_provider_discovery_package,
)
from genome_to_diffraction.structure_search.provider_empty import (
    DisabledProviderBundleRequest,
    emit_disabled_provider_bundle,
)

ProviderPreparationIdentifier = Annotated[
    str,
    Field(pattern=r"^providerstage_[a-f0-9]{64}$"),
]
ProviderOfflineInputIdentifier = Annotated[
    str,
    Field(pattern=r"^provideroffline_[a-f0-9]{64}$"),
]

_ADAPTER_VERSION = "phase3-provider-login-stage-v1"
_MANIFEST_NAME = "provider_preparation.json"
_OFFLINE_INPUT_NAME = "phase3_offline_provider_input.json"
_MAXIMUM_HITS_PER_GROUP = 3
_MAXIMUM_MAPPINGS = 25
_AFDB_TIMEOUT_SECONDS = 60.0
_AFDB_RETRY_COUNT = 3


class PhaseIIIProviderLoginStageError(InputContractError):
    """Login-side provider coordinates cannot form one safe preparation."""


class PhaseIIIProviderLoginStageFile(ContractModel):
    """One copied login-stage file and its exact byte identity."""

    relative_path: str = Field(min_length=1)
    sha256: Sha256Hex
    size_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_path(self) -> Self:
        validate_phase3_review_relative_path(self.relative_path)
        if self.relative_path == _MANIFEST_NAME:
            raise ValueError("provider preparation must not inventory itself")
        return self


class PhaseIIIProviderLoginStageManifest(_ContentAddressedContract):
    """Owned provider preparation consumed by the offline unknown screen."""

    _identity_field: ClassVar[str] = "preparation_id"
    _identity_prefix: ClassVar[str] = "providerstage_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["phase3-provider-login-stage-v1"]
    preparation_id: ProviderPreparationIdentifier
    discovery_package_id: Annotated[
        str,
        Field(pattern=r"^providerdiscovery_[a-f0-9]{64}$"),
    ]
    discovery_owned_run_id: OperatorIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    provider_plan_id: str = Field(min_length=1)
    sequence_group_count: int = Field(gt=0)
    pdb_coordinate_source_count: int = Field(ge=0)
    pdb_mapping_count: int = Field(ge=0, le=_MAXIMUM_MAPPINGS)
    afdb_result_count: int = Field(gt=0)
    afdb_coordinate_source_count: int = Field(ge=0)
    esm_result_count: int = Field(gt=0)
    staged_coordinate_object_count: int = Field(ge=0)
    maximum_hits_per_sequence_group: Literal[3]
    maximum_mappings: Literal[25]
    execution_class: Literal["bounded_login_staging"]
    remote_sequence_submission: Literal[False] = False
    files: tuple[PhaseIIIProviderLoginStageFile, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_complete_stage(self) -> Self:
        if self.afdb_result_count != self.sequence_group_count:
            raise ValueError("AFDB staging must retain one result per sequence group")
        if self.esm_result_count != self.sequence_group_count:
            raise ValueError("ESM disabled staging must retain every sequence group")
        source_count = (
            self.pdb_coordinate_source_count + self.afdb_coordinate_source_count
        )
        if self.staged_coordinate_object_count > source_count or (
            source_count > 0 and self.staged_coordinate_object_count == 0
        ):
            raise ValueError("provider staging has an invalid coordinate inventory")
        paths = tuple(item.relative_path for item in self.files)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("provider staging files must be unique and sorted")
        return self


class PhaseIIIProviderOfflineInputManifest(_ContentAddressedContract):
    """Matched provider authority required before offline scientific work."""

    _identity_field: ClassVar[str] = "offline_input_id"
    _identity_prefix: ClassVar[str] = "provideroffline_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["phase3-offline-provider-input-v1"]
    offline_input_id: ProviderOfflineInputIdentifier
    discovery_package_id: Annotated[
        str,
        Field(pattern=r"^providerdiscovery_[a-f0-9]{64}$"),
    ]
    preparation_id: ProviderPreparationIdentifier
    execution_identity_id: ExecutionIdentityIdentifier
    provider_plan_id: str = Field(min_length=1)
    remote_sequence_submission: Literal[False] = False
    compute_network_access: Literal[False] = False


@dataclass(frozen=True, slots=True)
class PhaseIIIProviderLoginStageRequest:
    """One owned discovery package and a new output directory."""

    discovery_package: Path
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True, slots=True)
class PhaseIIIProviderLoginStageOutput:
    """Published provider preparation and its typed manifest."""

    manifest: PhaseIIIProviderLoginStageManifest
    preparation_directory: Path
    manifest_path: Path


@dataclass(frozen=True, slots=True)
class PhaseIIIProviderOfflineInputOutput:
    """Published path-free match record for one offline screen."""

    manifest: PhaseIIIProviderOfflineInputManifest
    manifest_path: Path


def _inventory(root: Path) -> tuple[PhaseIIIProviderLoginStageFile, ...]:
    files: list[PhaseIIIProviderLoginStageFile] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.is_symlink() or not path.is_file():
            raise PhaseIIIProviderLoginStageError(
                "provider staging contains an unsafe file"
            )
        relative = path.relative_to(root).as_posix()
        if relative == _MANIFEST_NAME:
            continue
        files.append(
            PhaseIIIProviderLoginStageFile(
                relative_path=relative,
                sha256=sha256_file(path, progress=False),
                size_bytes=path.stat().st_size,
            )
        )
    return tuple(files)


def _copy_coordinate_objects(
    records: tuple[CoordinateSourceRecord, ...],
    *,
    output_root: Path,
) -> int:
    seen: set[str] = set()
    for record in records:
        source = Path(record.coordinate_path)
        if not source.is_absolute():
            raise PhaseIIIProviderLoginStageError(
                "login-staged coordinate source must use its verified cache object"
            )
        if source.is_symlink():
            raise PhaseIIIProviderLoginStageError(
                "login-staged coordinate object must not be a symlink"
            )
        try:
            resolved = source.resolve(strict=True)
        except OSError as error:
            raise PhaseIIIProviderLoginStageError(
                "login-staged coordinate object is absent"
            ) from error
        if (
            not resolved.is_file()
            or sha256_file(
                resolved,
                progress=False,
            )
            != record.coordinate_sha256
        ):
            raise PhaseIIIProviderLoginStageError(
                "login-staged coordinate checksum differs from its record"
            )
        if record.coordinate_sha256 in seen:
            continue
        seen.add(record.coordinate_sha256)
        suffix = "".join(resolved.suffixes) or ".bin"
        destination = (
            output_root
            / record.coordinate_sha256[:2]
            / f"{record.coordinate_sha256}{suffix}"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved, destination)
    return len(seen)


def validate_phase3_provider_login_stage(
    preparation_directory: Path,
) -> PhaseIIIProviderLoginStageManifest:
    """Independently verify a published login-side provider preparation."""

    if preparation_directory.is_symlink():
        raise PhaseIIIProviderLoginStageError(
            "provider preparation must not be a symlink"
        )
    try:
        root = preparation_directory.resolve(strict=True)
    except OSError as error:
        raise PhaseIIIProviderLoginStageError(
            "provider preparation is absent"
        ) from error
    if not root.is_dir():
        raise PhaseIIIProviderLoginStageError(
            "provider preparation must be a directory"
        )
    manifest_path = root / _MANIFEST_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PhaseIIIProviderLoginStageError(
            "provider preparation manifest is absent or unsafe"
        )
    try:
        manifest = PhaseIIIProviderLoginStageManifest.model_validate(
            load_json_document(manifest_path)
        )
    except (ContractLoadError, OSError, ValidationError, ValueError) as error:
        raise PhaseIIIProviderLoginStageError(
            "provider preparation manifest violates its contract"
        ) from error
    if manifest.files != _inventory(root):
        raise PhaseIIIProviderLoginStageError(
            "provider preparation file inventory changed"
        )
    return manifest


def publish_phase3_offline_provider_input(
    *,
    discovery_package: Path,
    provider_preparation: Path,
    execution_identity: Path,
    output_directory: Path,
) -> PhaseIIIProviderOfflineInputOutput:
    """Match all provider/execution authorities and publish one barrier record."""

    try:
        discovery = validate_phase3_provider_discovery_package(discovery_package)
    except PhaseIIIProviderDiscoveryError as error:
        raise PhaseIIIProviderLoginStageError(
            f"offline provider discovery is invalid: {error}"
        ) from error
    preparation = validate_phase3_provider_login_stage(provider_preparation)
    if execution_identity.is_symlink():
        raise PhaseIIIProviderLoginStageError(
            "offline execution identity must not be a symlink"
        )
    try:
        execution_path = execution_identity.resolve(strict=True)
        execution = PhaseIIIExecutionIdentity.model_validate(
            load_json_document(execution_path)
        )
    except (ContractLoadError, OSError, ValidationError, ValueError) as error:
        raise PhaseIIIProviderLoginStageError(
            "offline execution identity violates its contract"
        ) from error
    if (
        preparation.discovery_package_id != discovery.package_id
        or preparation.discovery_owned_run_id != discovery.owned_run_id
        or preparation.execution_identity_id != discovery.execution_identity_id
        or preparation.provider_plan_id != discovery.provider_plan_id
        or execution.execution_identity_id != discovery.execution_identity_id
    ):
        raise PhaseIIIProviderLoginStageError(
            "offline provider authorities do not share one exact execution"
        )
    output = output_directory.absolute()
    if output.exists() or output.is_symlink():
        raise PhaseIIIProviderLoginStageError(
            "offline-provider output must be a new absent directory"
        )
    output.mkdir(parents=True)
    manifest = PhaseIIIProviderOfflineInputManifest.from_content(
        adapter_version="phase3-offline-provider-input-v1",
        discovery_package_id=discovery.package_id,
        preparation_id=preparation.preparation_id,
        execution_identity_id=execution.execution_identity_id,
        provider_plan_id=discovery.provider_plan_id,
        remote_sequence_submission=False,
        compute_network_access=False,
    )
    manifest_path = output / _OFFLINE_INPUT_NAME
    atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
    return PhaseIIIProviderOfflineInputOutput(
        manifest=manifest,
        manifest_path=manifest_path,
    )


def stage_phase3_provider_coordinates(
    request: PhaseIIIProviderLoginStageRequest,
) -> PhaseIIIProviderLoginStageOutput:
    """Run bounded login acquisition and publish the offline preparation."""

    try:
        discovery = validate_phase3_provider_discovery_package(
            request.discovery_package
        )
    except PhaseIIIProviderDiscoveryError as error:
        raise PhaseIIIProviderLoginStageError(
            f"provider discovery package is invalid: {error}"
        ) from error
    discovery_root = request.discovery_package.resolve(strict=True)
    output = request.output_directory.absolute()
    if output.exists() or output.is_symlink():
        raise PhaseIIIProviderLoginStageError(
            "provider-staging output must be a new absent directory"
        )
    plan_path = discovery_root / "provider_plan/provider_plan.json"
    try:
        plan = load_contract(
            plan_path,
            "provider-execution-plan",
            progress=False,
        )
    except ContractError as error:
        raise PhaseIIIProviderLoginStageError(
            "provider discovery plan violates its contract"
        ) from error
    if not isinstance(plan, ProviderExecutionPlan) or plan.plan_id != (
        discovery.provider_plan_id
    ):
        raise PhaseIIIProviderLoginStageError(
            "provider discovery plan changed before login staging"
        )
    entries = {entry.provider: entry for entry in plan.entries}
    afdb_entry = entries.get(ProviderKey.AFDB_EXACT)
    esm_entry = entries.get(ProviderKey.ESM_ATLAS)
    if afdb_entry is None or esm_entry is None or esm_entry.enabled:
        raise PhaseIIIProviderLoginStageError(
            "provider staging requires explicit AFDB and disabled ESM routes"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    published = False
    try:
        pdb_output = register_pdb_coordinates(
            PdbCoordinateRegistrationRequest(
                structural_hits_jsonl=(
                    discovery_root / "pdb_provider_hits/structural_hits.jsonl"
                ),
                provider_search_results_jsonl=(
                    discovery_root / "pdb_sequence_search/search_results.jsonl",
                    discovery_root / "prostt5_foldseek_search/search_results.jsonl",
                ),
                sequence_groups_jsonl=(
                    discovery_root / "catalogue/sequence_groups.jsonl"
                ),
                database_manifest=(discovery_root / "inputs/database_manifest.json"),
                output_directory=temporary / "pdb_coordinate_registration",
                maximum_hits_per_sequence_group=_MAXIMUM_HITS_PER_GROUP,
                maximum_mappings=_MAXIMUM_MAPPINGS,
                materialise_coordinate_objects=False,
                progress=request.progress,
            )
        )
        afdb_output_directory = temporary / "afdb_exact_search"
        if afdb_entry.enabled:
            afdb_output = search_afdb_exact(
                AfdbExactRequest(
                    sequence_groups_jsonl=(
                        discovery_root / "catalogue/sequence_groups.jsonl"
                    ),
                    source_records_jsonl=(
                        discovery_root / "catalogue/source_records.jsonl"
                    ),
                    database_manifest=(
                        discovery_root / "inputs/database_manifest.json"
                    ),
                    provider_plan_json=plan_path,
                    provider_entry_json=(
                        discovery_root / "provider_plan/entries/afdb_exact.json"
                    ),
                    accession_map_tsv=(
                        discovery_root / "inputs/afdb_accession_map.tsv"
                    ),
                    request_timeout_seconds=_AFDB_TIMEOUT_SECONDS,
                    retry_count=_AFDB_RETRY_COUNT,
                    output_directory=afdb_output_directory,
                    progress=request.progress,
                )
            )
            afdb_coordinates = afdb_output.coordinate_sources
        else:
            afdb_output = emit_disabled_provider_bundle(
                DisabledProviderBundleRequest(
                    provider_entry_json=(
                        discovery_root / "provider_plan/entries/afdb_exact.json"
                    ),
                    sequence_groups_jsonl=(
                        discovery_root / "catalogue/sequence_groups.jsonl"
                    ),
                    output_directory=afdb_output_directory,
                )
            )
            afdb_coordinates = ()
        esm_output = emit_disabled_provider_bundle(
            DisabledProviderBundleRequest(
                provider_entry_json=(
                    discovery_root / "provider_plan/entries/esm_atlas.json"
                ),
                sequence_groups_jsonl=(
                    discovery_root / "catalogue/sequence_groups.jsonl"
                ),
                output_directory=temporary / "esm_atlas_search",
            )
        )
        coordinate_count = _copy_coordinate_objects(
            (*pdb_output.coordinate_sources, *afdb_coordinates),
            output_root=temporary / "coordinate_objects",
        )
        shutil.copy2(
            discovery_root / "phase3_provider_discovery_manifest.json",
            temporary / "phase3_provider_discovery_manifest.json",
        )
        try:
            manifest = PhaseIIIProviderLoginStageManifest.from_content(
                adapter_version=_ADAPTER_VERSION,
                discovery_package_id=discovery.package_id,
                discovery_owned_run_id=discovery.owned_run_id,
                execution_identity_id=discovery.execution_identity_id,
                provider_plan_id=discovery.provider_plan_id,
                sequence_group_count=discovery.sequence_group_count,
                pdb_coordinate_source_count=len(pdb_output.coordinate_sources),
                pdb_mapping_count=len(pdb_output.mappings),
                afdb_result_count=len(afdb_output.results),
                afdb_coordinate_source_count=len(afdb_coordinates),
                esm_result_count=len(esm_output.results),
                staged_coordinate_object_count=coordinate_count,
                maximum_hits_per_sequence_group=_MAXIMUM_HITS_PER_GROUP,
                maximum_mappings=_MAXIMUM_MAPPINGS,
                execution_class="bounded_login_staging",
                remote_sequence_submission=False,
                files=_inventory(temporary),
            )
        except ValidationError as error:
            raise PhaseIIIProviderLoginStageError(
                "provider staging outputs violate their fixed contract"
            ) from error
        atomic_write_json(
            temporary / _MANIFEST_NAME,
            manifest.model_dump(mode="json"),
        )
        if validate_phase3_provider_login_stage(temporary) != manifest:
            raise PhaseIIIProviderLoginStageError(
                "provider preparation changed during validation"
            )
        os.replace(temporary, output)
        published = True
    finally:
        if not published and temporary.exists():
            shutil.rmtree(temporary)

    return PhaseIIIProviderLoginStageOutput(
        manifest=manifest,
        preparation_directory=output,
        manifest_path=output / _MANIFEST_NAME,
    )


__all__ = [
    "PhaseIIIProviderLoginStageError",
    "PhaseIIIProviderLoginStageFile",
    "PhaseIIIProviderLoginStageManifest",
    "PhaseIIIProviderLoginStageOutput",
    "PhaseIIIProviderLoginStageRequest",
    "PhaseIIIProviderOfflineInputManifest",
    "PhaseIIIProviderOfflineInputOutput",
    "publish_phase3_offline_provider_input",
    "stage_phase3_provider_coordinates",
    "validate_phase3_provider_login_stage",
]
