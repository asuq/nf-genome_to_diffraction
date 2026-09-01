"""Publish and query the Phase III all-eligible processed-model registry.

Scientific purpose
------------------
The registry is the model universe for later B--F composition planning.  It is
built from already prepared
:class:`~genome_to_diffraction.schemas.results.ProcessedModelRecord` objects and
is deliberately independent of a crystal's bounded A-search shortlist.  Every
supplied catalogue sequence group is represented: groups
with models retain every validated provider/variant, while groups without a
processed model retain the typed ``no_eligible_model`` reason.

Inputs are immutable sequence-group, coordinate-source, optional PDB mapping,
and processed-model records plus their model files.  Outputs are a deterministic
schema-v2 JSON registry, canonical ``processed_models.jsonl``, and
content-addressed model files.  No compatibility manifest or competing model
authority is generated.  No external command is run and no provider, Phaser,
localisation, or candidate-search work is performed.

Any malformed identity, unsupported provider mapping, duplicate, unsafe path,
or checksum mismatch raises :class:`AllEligibleModelRegistryError` before the
registry is published.  Scientific absence is not an execution error: it is
represented by :class:`ModelUnavailableReason`.  ``registry_id`` is the cache
key and covers the complete canonical registry payload except itself; execution
caps and crystal-specific evidence are not inputs.  Focused mutation, ordering,
checksum, lookup, and A-cap separation coverage lives in
``tests/unit/test_all_eligible_model_registry.py`` and
``tests/unit/test_ranking_funnel.py``.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_digest, canonical_json_text, content_id
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    PositiveFloat,
    Sha256Hex,
)
from genome_to_diffraction.schemas.results import (
    CoordinateHitMappingRecord,
    CoordinateSourceRecord,
    ProcessedModelRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.schemas.v2.composition import (
    AllModelRegistryIdentifier,
    ModelUnavailableReason,
)
from genome_to_diffraction.status import InputContractError

_ADAPTER_VERSION = "all-eligible-model-registry-v3"
_PREDICTED_PROVIDERS = frozenset({"afdb", "esm_atlas"})
_REGISTRY_FILENAME = "all_model_registry.json"
_PROCESSED_MODELS_FILENAME = "processed_models.jsonl"

SequenceGroupIdentifier = Annotated[
    str,
    Field(pattern=r"^seq_[a-f0-9]{64}$"),
]


class AllEligibleModelRegistryError(InputContractError):
    """The complete processed-model universe cannot be represented safely."""


class AllEligibleModelEntry(ContractModel):
    """One checksum-bound provider/variant available for one sequence group."""

    schema_version: Literal["2.0"]
    sequence_group_id: SequenceGroupIdentifier
    sequence_sha256: Sha256Hex
    model_id: NonEmptyString
    model_path: NonEmptyString
    model_sha256: Sha256Hex
    processed_model_record_sha256: Sha256Hex
    coordinate_id: NonEmptyString
    coordinate_sha256: Sha256Hex
    coordinate_record_sha256: Sha256Hex
    provider: NonEmptyString
    provider_accession: NonEmptyString
    variant_type: NonEmptyString
    processing_tool: NonEmptyString
    processing_version: NonEmptyString
    model_mass_da: PositiveFloat
    retained_fraction: float = Field(gt=0, le=1)
    estimated_coordinate_error: float | None = Field(default=None, ge=0)
    model_sequence_identity: float = Field(ge=0, le=1)
    model_uncertainty_source: NonEmptyString
    model_uncertainty_evidence_sha256: Sha256Hex
    quality_flags: tuple[str, ...] = ()
    mapping_id: str | None = None
    mapping_record_sha256: Sha256Hex | None = None

    @model_validator(mode="after")
    def _validate_complete_identity(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError("sequence_group_id does not match sequence_sha256")
        if (self.mapping_id is None) != (self.mapping_record_sha256 is None):
            raise ValueError("mapping ID and mapping-record checksum must be paired")
        relative = PurePosixPath(self.model_path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or self.model_path != relative.as_posix()
        ):
            raise ValueError("model_path must be a safe canonical relative path")
        return self


class SequenceGroupModelInventory(ContractModel):
    """All eligible models, or one typed absence, for a catalogue sequence."""

    schema_version: Literal["2.0"]
    sequence_group_id: SequenceGroupIdentifier
    sequence_sha256: Sha256Hex
    models: tuple[AllEligibleModelEntry, ...] = ()
    unavailable_reason: Literal[ModelUnavailableReason.NO_ELIGIBLE_MODEL] | None = None

    @model_validator(mode="after")
    def _validate_inventory(self) -> Self:
        if self.sequence_group_id != f"seq_{self.sequence_sha256}":
            raise ValueError("sequence_group_id does not match sequence_sha256")
        if bool(self.models) == (self.unavailable_reason is not None):
            raise ValueError(
                "inventory requires models or no_eligible_model, but not both"
            )
        expected = tuple(sorted(self.models, key=_entry_sort_key))
        if self.models != expected:
            raise ValueError("model entries are not in deterministic order")
        model_ids: set[str] = set()
        for model in self.models:
            if (
                model.sequence_group_id != self.sequence_group_id
                or model.sequence_sha256 != self.sequence_sha256
            ):
                raise ValueError("model entry does not match its sequence inventory")
            if model.model_id in model_ids:
                raise ValueError("duplicate model ID in sequence inventory")
            model_ids.add(model.model_id)
        return self


class AllEligibleModelRegistryManifest(ContractModel):
    """Immutable complete model universe and its relocatable output checksums."""

    schema_version: Literal["2.0"]
    registry_id: AllModelRegistryIdentifier
    adapter_version: Literal["all-eligible-model-registry-v3"]
    scope: Literal["all_eligible_processed_models"]
    processed_models_path: Literal["processed_models.jsonl"]
    processed_models_sha256: Sha256Hex
    sequence_group_count: int = Field(ge=1)
    model_count: int = Field(ge=0)
    unavailable_sequence_group_count: int = Field(ge=0)
    sequence_groups: tuple[SequenceGroupModelInventory, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_registry(self) -> Self:
        expected_groups = tuple(
            sorted(self.sequence_groups, key=lambda item: item.sequence_group_id)
        )
        if self.sequence_groups != expected_groups:
            raise ValueError("sequence-group inventories are not deterministic")
        if self.sequence_group_count != len(self.sequence_groups):
            raise ValueError("sequence_group_count does not match inventories")
        if len({item.sequence_group_id for item in self.sequence_groups}) != len(
            self.sequence_groups
        ):
            raise ValueError("duplicate sequence-group inventory")
        entries = tuple(
            model for inventory in self.sequence_groups for model in inventory.models
        )
        if self.model_count != len(entries):
            raise ValueError("model_count does not match inventories")
        if len({entry.model_id for entry in entries}) != len(entries):
            raise ValueError("duplicate model ID across registry")
        unavailable = sum(
            inventory.unavailable_reason is not None
            for inventory in self.sequence_groups
        )
        if self.unavailable_sequence_group_count != unavailable:
            raise ValueError(
                "unavailable_sequence_group_count does not match inventories"
            )
        payload = self.model_dump(mode="python", exclude={"registry_id"})
        if self.registry_id != content_id("allmodelreg_", payload):
            raise ValueError("registry_id does not match canonical registry content")
        return self


@dataclass(frozen=True)
class ValidatedProcessedModelInput:
    """One prepared model plus the source identities required for eligibility."""

    model: ProcessedModelRecord
    coordinate: CoordinateSourceRecord
    sequence_group: SequenceGroupRecord
    model_path: Path
    retained_fraction: float
    mapping: CoordinateHitMappingRecord | None = None


@dataclass(frozen=True)
class AllEligibleModelRegistryOutput:
    """Published all-model registry paths and validated immutable manifest."""

    registry: AllEligibleModelRegistryManifest
    registry_directory: Path
    registry_json: Path
    processed_models_jsonl: Path


@dataclass(frozen=True)
class AllEligibleModelLookupResult:
    """Typed result of one sequence/provider/variant registry query."""

    sequence_group_id: str
    models: tuple[AllEligibleModelEntry, ...]
    unavailable_reason: ModelUnavailableReason | None

    @property
    def available(self) -> bool:
        """Return whether at least one checksum-verified model matched."""

        return bool(self.models)


@dataclass(frozen=True)
class AllEligibleModelRegistry:
    """Loaded checksum-verified registry with deterministic group lookup."""

    root: Path
    manifest: AllEligibleModelRegistryManifest

    def lookup(
        self,
        sequence_group_id: str,
        *,
        provider: str | None = None,
        variant_type: str | None = None,
    ) -> AllEligibleModelLookupResult:
        """Find models for later component planning without applying search caps."""

        inventory = next(
            (
                item
                for item in self.manifest.sequence_groups
                if item.sequence_group_id == sequence_group_id
            ),
            None,
        )
        if inventory is None:
            return AllEligibleModelLookupResult(
                sequence_group_id=sequence_group_id,
                models=(),
                unavailable_reason=(
                    ModelUnavailableReason.SEQUENCE_GROUP_NOT_REGISTERED
                ),
            )
        if not inventory.models:
            return AllEligibleModelLookupResult(
                sequence_group_id=sequence_group_id,
                models=(),
                unavailable_reason=ModelUnavailableReason.NO_ELIGIBLE_MODEL,
            )
        models = inventory.models
        if provider is not None:
            models = tuple(item for item in models if item.provider == provider)
            if not models:
                return AllEligibleModelLookupResult(
                    sequence_group_id=sequence_group_id,
                    models=(),
                    unavailable_reason=ModelUnavailableReason.PROVIDER_UNAVAILABLE,
                )
        if variant_type is not None:
            models = tuple(item for item in models if item.variant_type == variant_type)
            if not models:
                return AllEligibleModelLookupResult(
                    sequence_group_id=sequence_group_id,
                    models=(),
                    unavailable_reason=ModelUnavailableReason.VARIANT_UNAVAILABLE,
                )
        return AllEligibleModelLookupResult(
            sequence_group_id=sequence_group_id,
            models=models,
            unavailable_reason=None,
        )


def _entry_sort_key(entry: AllEligibleModelEntry) -> tuple[str, ...]:
    return (
        entry.provider,
        entry.variant_type,
        entry.provider_accession,
        entry.model_id,
    )


def _validated_record[T: ContractModel](record: T, model: type[T], label: str) -> T:
    try:
        return model.model_validate(record.model_dump(mode="python"))
    except (TypeError, ValueError) as error:
        raise AllEligibleModelRegistryError(f"invalid {label} record") from error


def _validate_source(
    item: ValidatedProcessedModelInput,
) -> tuple[
    ProcessedModelRecord,
    CoordinateSourceRecord,
    SequenceGroupRecord,
    CoordinateHitMappingRecord | None,
    Path,
    str,
    float,
]:
    model = _validated_record(item.model, ProcessedModelRecord, "processed-model")
    coordinate = _validated_record(
        item.coordinate, CoordinateSourceRecord, "coordinate-source"
    )
    group = _validated_record(
        item.sequence_group, SequenceGroupRecord, "sequence-group"
    )
    mapping = (
        _validated_record(item.mapping, CoordinateHitMappingRecord, "PDB mapping")
        if item.mapping is not None
        else None
    )
    if model.coordinate_id != coordinate.coordinate_id:
        raise AllEligibleModelRegistryError(
            f"model coordinate identity mismatch: {model.model_id}"
        )
    if model.full_candidate_sequence_group_id != group.sequence_group_id:
        raise AllEligibleModelRegistryError(
            f"model sequence-group identity mismatch: {model.model_id}"
        )
    if coordinate.provider in _PREDICTED_PROVIDERS:
        if mapping is not None:
            raise AllEligibleModelRegistryError(
                f"predicted model cannot carry a PDB mapping: {model.model_id}"
            )
        if coordinate.source_sequence_sha256 != group.sha256:
            raise AllEligibleModelRegistryError(
                f"predicted model is not exact-sequence mapped: {model.model_id}"
            )
    elif coordinate.provider == "pdb":
        mapping_id = model.processing_parameters.get("mapping_id")
        if (
            mapping is None
            or mapping_id != mapping.mapping_id
            or mapping.coordinate_id != coordinate.coordinate_id
            or mapping.sequence_group_id != group.sequence_group_id
            or mapping.source_sequence_sha256 != coordinate.source_sequence_sha256
            or mapping.candidate_sequence_sha256 != group.sha256
        ):
            raise AllEligibleModelRegistryError(
                f"experimental model mapping does not match inputs: {model.model_id}"
            )
    else:
        raise AllEligibleModelRegistryError(
            f"unsupported coordinate provider: {coordinate.provider}"
        )
    if isinstance(item.retained_fraction, bool) or not 0 < item.retained_fraction <= 1:
        raise AllEligibleModelRegistryError(
            f"invalid retained fraction for model: {model.model_id}"
        )
    path = item.model_path.resolve(strict=True)
    if not path.is_file():
        raise AllEligibleModelRegistryError(
            f"processed model is not a file: {model.model_id}"
        )
    digest = sha256_file(path, progress=False)
    if digest != model.model_sha256:
        raise AllEligibleModelRegistryError(
            f"processed-model checksum mismatch: {model.model_id}"
        )
    return model, coordinate, group, mapping, path, digest, item.retained_fraction


def build_all_eligible_model_registry(
    *,
    models: Sequence[ValidatedProcessedModelInput],
    sequence_groups: Sequence[SequenceGroupRecord],
    output_directory: Path,
) -> AllEligibleModelRegistryOutput:
    """Publish every valid processed model without consulting execution caps."""

    validated_groups: dict[str, SequenceGroupRecord] = {}
    for raw_group in sequence_groups:
        group = _validated_record(raw_group, SequenceGroupRecord, "sequence-group")
        if group.sequence_group_id in validated_groups:
            raise AllEligibleModelRegistryError(
                f"duplicate sequence-group ID: {group.sequence_group_id}"
            )
        validated_groups[group.sequence_group_id] = group
    if not validated_groups:
        raise AllEligibleModelRegistryError(
            "all-model registry requires at least one sequence group"
        )

    validated: list[
        tuple[
            ProcessedModelRecord,
            CoordinateSourceRecord,
            SequenceGroupRecord,
            CoordinateHitMappingRecord | None,
            Path,
            str,
            float,
        ]
    ] = []
    model_ids: set[str] = set()
    for raw_model in models:
        item = _validate_source(raw_model)
        model, _, group, _, _, _, _ = item
        registered_group = validated_groups.get(group.sequence_group_id)
        if registered_group is None or registered_group != group:
            raise AllEligibleModelRegistryError(
                f"model sequence group is outside the registry universe: "
                f"{model.model_id}"
            )
        if model.model_id in model_ids:
            raise AllEligibleModelRegistryError(
                f"duplicate processed-model ID: {model.model_id}"
            )
        model_ids.add(model.model_id)
        validated.append(item)

    output = output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise AllEligibleModelRegistryError(
            f"all-model registry output directory is not empty: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)

    entries: list[AllEligibleModelEntry] = []
    records_by_model: dict[str, ProcessedModelRecord] = {}
    for (
        model,
        coordinate,
        group,
        mapping,
        source_path,
        digest,
        retained_fraction,
    ) in validated:
        relative = PurePosixPath("models", digest[:2], f"{digest}.pdb").as_posix()
        destination = output / Path(*PurePosixPath(relative).parts)
        if destination.exists():
            if destination.is_symlink() or sha256_file(destination) != digest:
                raise AllEligibleModelRegistryError(
                    f"registry model target is unsafe: {destination}"
                )
        else:
            atomic_write_bytes(destination, source_path.read_bytes())
        if sha256_file(destination, progress=False) != digest:
            raise AllEligibleModelRegistryError(
                f"registry model checksum mismatch: {model.model_id}"
            )
        entry = AllEligibleModelEntry(
            schema_version="2.0",
            sequence_group_id=group.sequence_group_id,
            sequence_sha256=group.sha256,
            model_id=model.model_id,
            model_path=relative,
            model_sha256=digest,
            processed_model_record_sha256=canonical_digest(model),
            coordinate_id=coordinate.coordinate_id,
            coordinate_sha256=coordinate.coordinate_sha256,
            coordinate_record_sha256=canonical_digest(coordinate),
            provider=coordinate.provider,
            provider_accession=coordinate.provider_accession,
            variant_type=model.variant_type,
            processing_tool=model.processing_tool,
            processing_version=model.processing_version,
            model_mass_da=model.model_mass_da,
            retained_fraction=retained_fraction,
            estimated_coordinate_error=model.estimated_coordinate_error,
            model_sequence_identity=(
                mapping.sequence_identity if mapping is not None else 1.0
            ),
            model_uncertainty_source=(
                "pdb_mapping_sequence_identity"
                if mapping is not None
                else "exact_catalogue_sequence_model"
            ),
            model_uncertainty_evidence_sha256=canonical_digest(
                {
                    "processed_model": model,
                    "mapping": mapping,
                    "model_sequence_identity": (
                        mapping.sequence_identity if mapping is not None else 1.0
                    ),
                }
            ),
            quality_flags=model.quality_flags,
            mapping_id=mapping.mapping_id if mapping is not None else None,
            mapping_record_sha256=(
                canonical_digest(mapping) if mapping is not None else None
            ),
        )
        entries.append(entry)
        records_by_model[model.model_id] = model
    entries.sort(key=lambda item: (item.sequence_group_id, *_entry_sort_key(item)))

    ordered_records = tuple(records_by_model[entry.model_id] for entry in entries)
    processed_models_path = output / _PROCESSED_MODELS_FILENAME
    atomic_write_text(
        processed_models_path,
        "".join(f"{canonical_json_text(record)}\n" for record in ordered_records),
    )
    processed_models_sha256 = sha256_file(processed_models_path, progress=False)

    entries_by_group: dict[str, list[AllEligibleModelEntry]] = {
        group_id: [] for group_id in validated_groups
    }
    for entry in entries:
        entries_by_group[entry.sequence_group_id].append(entry)
    inventories = tuple(
        SequenceGroupModelInventory(
            schema_version="2.0",
            sequence_group_id=group_id,
            sequence_sha256=validated_groups[group_id].sha256,
            models=tuple(entries_by_group[group_id]),
            unavailable_reason=(
                None
                if entries_by_group[group_id]
                else ModelUnavailableReason.NO_ELIGIBLE_MODEL
            ),
        )
        for group_id in sorted(validated_groups)
    )
    payload = {
        "schema_version": "2.0",
        "adapter_version": _ADAPTER_VERSION,
        "scope": "all_eligible_processed_models",
        "processed_models_path": _PROCESSED_MODELS_FILENAME,
        "processed_models_sha256": processed_models_sha256,
        "sequence_group_count": len(inventories),
        "model_count": len(entries),
        "unavailable_sequence_group_count": sum(
            inventory.unavailable_reason is not None for inventory in inventories
        ),
        "sequence_groups": inventories,
    }
    registry = AllEligibleModelRegistryManifest.model_validate(
        {
            **payload,
            "registry_id": content_id("allmodelreg_", payload),
        }
    )
    registry_path = output / _REGISTRY_FILENAME
    atomic_write_json(registry_path, registry.model_dump(mode="json"))
    return AllEligibleModelRegistryOutput(
        registry=registry,
        registry_directory=output,
        registry_json=registry_path,
        processed_models_jsonl=processed_models_path,
    )


def load_all_eligible_model_registry(
    registry_json: Path,
) -> AllEligibleModelRegistry:
    """Load a registry and verify every retained processed record and model."""

    resolved = registry_json.resolve(strict=True)
    if not resolved.is_file():
        raise AllEligibleModelRegistryError(
            f"all-model registry manifest is not a file: {resolved}"
        )
    try:
        manifest = AllEligibleModelRegistryManifest.model_validate_json(
            resolved.read_text(encoding="utf-8")
        )
    except (TypeError, ValueError) as error:
        raise AllEligibleModelRegistryError(
            f"invalid all-model registry manifest: {resolved}"
        ) from error
    root = resolved.parent
    processed_models = root / manifest.processed_models_path
    if sha256_file(processed_models, progress=False) != (
        manifest.processed_models_sha256
    ):
        raise AllEligibleModelRegistryError(
            "all-model processed-record checksum mismatch"
        )
    records: dict[str, ProcessedModelRecord] = {}
    with processed_models.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise AllEligibleModelRegistryError(
                    f"blank processed-model record at line {line_number}"
                )
            try:
                record = ProcessedModelRecord.model_validate_json(line)
            except (TypeError, ValueError) as error:
                raise AllEligibleModelRegistryError(
                    f"invalid processed-model record at line {line_number}"
                ) from error
            if record.model_id in records:
                raise AllEligibleModelRegistryError(
                    f"duplicate processed-model record: {record.model_id}"
                )
            records[record.model_id] = record

    entries = tuple(
        entry for inventory in manifest.sequence_groups for entry in inventory.models
    )
    if set(records) != {entry.model_id for entry in entries}:
        raise AllEligibleModelRegistryError(
            "processed-model records do not match registry entries"
        )
    for entry in entries:
        record = records[entry.model_id]
        if (
            record.full_candidate_sequence_group_id != entry.sequence_group_id
            or record.model_sha256 != entry.model_sha256
            or canonical_digest(record) != entry.processed_model_record_sha256
        ):
            raise AllEligibleModelRegistryError(
                f"processed-model record does not match registry: {entry.model_id}"
            )
        relative = PurePosixPath(entry.model_path)
        model_path = (root / Path(*relative.parts)).resolve(strict=True)
        if not model_path.is_file() or not model_path.is_relative_to(root):
            raise AllEligibleModelRegistryError(
                f"registry model escaped its root: {entry.model_id}"
            )
        if sha256_file(model_path, progress=False) != entry.model_sha256:
            raise AllEligibleModelRegistryError(
                f"registry model checksum mismatch: {entry.model_id}"
            )
    return AllEligibleModelRegistry(root=root, manifest=manifest)
