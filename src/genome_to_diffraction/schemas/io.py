"""JSON, YAML, and TSV adapters with precise validation diagnostics."""

import csv
import json
import logging
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Literal, cast

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from genome_to_diffraction.schemas.manifests import (
    CatalogueImportManifest,
    CatalogueManifest,
    CrystalManifest,
    DatabaseManifest,
    PhenixInstallManifest,
    PipelineConfig,
    RunManifest,
)
from genome_to_diffraction.schemas.results import (
    CoordinateSourceRecord,
    FreeRGenerationRecord,
    MatthewsHypothesis,
    MrHypothesis,
    MtzPreflightRecord,
    NormalisedMrResult,
    ProcessedModelRecord,
    ReviewDecisionManifest,
    ScientificStatusRecord,
    SequenceGroupRecord,
    SourceProteinRecord,
    StructuralSearchHit,
)

InputFormat = Literal["auto", "json", "yaml", "tsv"]
TsvAdapter = Callable[[Iterator[tuple[int, dict[str, str]]], Path], object]

_LOGGER = logging.getLogger("genome_to_diffraction.contracts")
_NULL_TEXT = frozenset({"", "na", "n/a", "none", "null", "."})


class ContractError(ValueError):
    """Base exception for contract loading and validation failures."""


class ContractLoadError(ContractError):
    """Input could not be parsed into a contract document."""


class ContractValidationError(ContractError):
    """Input parsed but violated its declared contract."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = tuple(errors)


@dataclass(frozen=True)
class ContractSpec:
    """Model, authoritative schema, and optional tabular adapter."""

    model: type[BaseModel]
    schema_filename: str | None = None
    tsv_adapter: TsvAdapter | None = None


def _is_null(value: str) -> bool:
    return value.strip().lower() in _NULL_TEXT


def _optional(value: str) -> str | None:
    stripped = value.strip()
    return None if _is_null(stripped) else stripped


def _boolean(value: str, *, path: Path, row: int, column: str) -> bool:
    normalised = value.strip().lower()
    if normalised == "true":
        return True
    if normalised == "false":
        return False
    raise ContractLoadError(f"{path}:{row}:{column}: expected true or false")


def _number(
    value: str,
    *,
    converter: Callable[[str], int | float],
    path: Path,
    row: int,
    column: str,
) -> int | float | None:
    optional = _optional(value)
    if optional is None:
        return None
    try:
        return converter(optional)
    except ValueError as error:
        raise ContractLoadError(
            f"{path}:{row}:{column}: invalid numeric value {value!r}"
        ) from error


def _split(value: str) -> list[str]:
    optional = _optional(value)
    if optional is None:
        return []
    return [item.strip() for item in re.split(r"[;,]", optional) if item.strip()]


def _drop_nulls(row: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in row.items() if value is not None}


def _catalogue_tsv(rows: Iterator[tuple[int, dict[str, str]]], path: Path) -> object:
    catalogues: list[dict[str, object]] = []
    for row_number, row in rows:
        converted: dict[str, object] = {
            key: _optional(value) for key, value in row.items()
        }
        converted["translation_table"] = _number(
            row.get("translation_table", ""),
            converter=int,
            path=path,
            row=row_number,
            column="translation_table",
        )
        converted["is_contaminant_catalogue"] = _boolean(
            row.get("is_contaminant_catalogue", ""),
            path=path,
            row=row_number,
            column="is_contaminant_catalogue",
        )
        catalogues.append(_drop_nulls(converted))
    return {"schema_version": "1.0", "catalogues": catalogues}


def _crystal_tsv(rows: Iterator[tuple[int, dict[str, str]]], path: Path) -> object:
    crystals: list[dict[str, object]] = []
    float_fields = (
        "high_resolution_override",
        "low_resolution_override",
        "sds_page_tolerance_fraction",
    )
    for row_number, row in rows:
        converted: dict[str, object] = {
            key: _optional(value) for key, value in row.items()
        }
        for field in float_fields:
            converted[field] = _number(
                row.get(field, ""),
                converter=float,
                path=path,
                row=row_number,
                column=field,
            )
        converted["sds_page_mass_kda"] = [
            float(item) for item in _split(row.get("sds_page_mass_kda", ""))
        ]
        converted["sds_page_band_roles"] = _split(row.get("sds_page_band_roles", ""))
        converted["allow_remote_sequence_submission"] = _boolean(
            row.get("allow_remote_sequence_submission", ""),
            path=path,
            row=row_number,
            column="allow_remote_sequence_submission",
        )
        crystals.append(_drop_nulls(converted))
    return {"schema_version": "1.0", "crystals": crystals}


def _review_tsv(rows: Iterator[tuple[int, dict[str, str]]], path: Path) -> object:
    del path
    decisions = [
        _drop_nulls({key: _optional(value) for key, value in row.items()})
        for _, row in rows
    ]
    return {"schema_version": "1.0", "decisions": decisions}


CONTRACTS: dict[str, ContractSpec] = {
    "catalogue-import-manifest": ContractSpec(CatalogueImportManifest),
    "catalogue-manifest": ContractSpec(
        CatalogueManifest, "catalogue_manifest.schema.json", _catalogue_tsv
    ),
    "crystal-manifest": ContractSpec(
        CrystalManifest, "crystal_manifest.schema.json", _crystal_tsv
    ),
    "database-manifest": ContractSpec(
        DatabaseManifest, "database_manifest.schema.json"
    ),
    "phenix-install-manifest": ContractSpec(
        PhenixInstallManifest, "phenix_install_manifest.schema.json"
    ),
    "pipeline-config": ContractSpec(PipelineConfig, "pipeline_config.schema.json"),
    "mr-hypothesis": ContractSpec(MrHypothesis, "mr_hypothesis.schema.json"),
    "review-decisions": ContractSpec(
        ReviewDecisionManifest, "review_decision.schema.json", _review_tsv
    ),
    "run-manifest": ContractSpec(RunManifest),
    "sequence-group": ContractSpec(SequenceGroupRecord),
    "source-protein": ContractSpec(SourceProteinRecord),
    "structural-hit": ContractSpec(StructuralSearchHit),
    "coordinate-source": ContractSpec(CoordinateSourceRecord),
    "free-r-generation": ContractSpec(FreeRGenerationRecord),
    "processed-model": ContractSpec(ProcessedModelRecord),
    "mtz-preflight": ContractSpec(MtzPreflightRecord),
    "matthews-hypothesis": ContractSpec(MatthewsHypothesis),
    "normalised-mr-result": ContractSpec(NormalisedMrResult),
    "scientific-status": ContractSpec(ScientificStatusRecord),
}


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_format(path: Path, requested: InputFormat) -> InputFormat:
    if requested != "auto":
        return requested
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix == ".tsv":
        return "tsv"
    raise ContractLoadError(f"{path}: cannot infer input format from suffix")


def _read_tsv(path: Path, adapter: TsvAdapter, *, progress: bool) -> object:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise ContractLoadError(f"{path}: TSV header is missing")
        iterator = ((number, dict(row)) for number, row in enumerate(reader, start=2))
        visible = tqdm(
            iterator,
            desc=f"Reading {path.name}",
            unit="row",
            disable=not progress,
        )
        return adapter(iter(visible), path)


def _read_document(
    path: Path, spec: ContractSpec, input_format: InputFormat, *, progress: bool
) -> object:
    try:
        if input_format == "tsv":
            if spec.tsv_adapter is None:
                raise ContractLoadError(
                    f"{path}: TSV is not supported for this contract kind"
                )
            return _read_tsv(path, spec.tsv_adapter, progress=progress)
        with path.open(encoding="utf-8") as handle:
            if input_format == "json":
                return json.load(handle)
            if input_format == "yaml":
                return yaml.safe_load(handle)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise ContractLoadError(f"{path}: cannot parse input: {error}") from error
    raise AssertionError(f"unhandled input format: {input_format}")


def _json_pointer(parts: object) -> str:
    if not isinstance(parts, list | tuple):
        return "/"
    encoded = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(encoded) if encoded else "/"


def _authoritative_schema(spec: ContractSpec) -> Mapping[str, object] | bool:
    if spec.schema_filename is None:
        return cast(
            Mapping[str, object], spec.model.model_json_schema(mode="validation")
        )
    path = _repository_root() / "schemas" / spec.schema_filename
    try:
        if path.is_file():
            with path.open(encoding="utf-8") as handle:
                schema = json.load(handle)
            label = str(path)
        else:
            resource = resources.files("genome_to_diffraction").joinpath(
                "_schemas", spec.schema_filename
            )
            with resource.open("r", encoding="utf-8") as handle:
                schema = json.load(handle)
            label = str(resource)
    except (OSError, json.JSONDecodeError) as error:
        raise ContractLoadError(
            f"authoritative JSON Schema {spec.schema_filename} cannot be loaded: "
            f"{error}"
        ) from error
    if not isinstance(schema, dict | bool):
        raise ContractLoadError(f"{label}: JSON Schema must be an object or boolean")
    return cast(Mapping[str, object] | bool, schema)


def _validate_wire(document: object, spec: ContractSpec, path: Path) -> None:
    schema = _authoritative_schema(spec)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        raise ContractValidationError(
            [
                f"{path}:{_json_pointer(list(error.absolute_path))}: {error.message}"
                for error in errors
            ]
        )


def load_contract(
    path: Path,
    kind: str,
    *,
    input_format: InputFormat = "auto",
    progress: bool = True,
) -> BaseModel:
    """Load, wire-validate, and construct one typed contract."""

    spec = CONTRACTS.get(kind)
    if spec is None:
        raise ContractLoadError(f"unknown contract kind: {kind}")
    resolved_format = _resolve_format(path, input_format)
    _LOGGER.info(
        "loading contract",
        extra={"contract_kind": kind, "path": str(path), "format": resolved_format},
    )
    document = _read_document(path, spec, resolved_format, progress=progress)
    _validate_wire(document, spec, path)
    try:
        model = spec.model.model_validate(document)
    except ValidationError as error:
        raise ContractValidationError(
            [
                f"{path}:{_json_pointer(list(item['loc']))}: {item['msg']}"
                for item in error.errors(include_url=False)
            ]
        ) from error
    _LOGGER.info(
        "contract valid",
        extra={"contract_kind": kind, "path": str(path)},
    )
    return model


def contract_kinds() -> tuple[str, ...]:
    """Return stable CLI choices for supported contracts."""

    return tuple(sorted(CONTRACTS))


def contract_json_schema(kind: str) -> dict[str, object]:
    """Return a Draft 2020-12 schema for a supported contract kind."""

    spec = CONTRACTS.get(kind)
    if spec is None:
        raise ContractLoadError(f"unknown contract kind: {kind}")
    schema = dict(spec.model.model_json_schema(mode="validation"))
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema.setdefault(
        "$id",
        f"https://example.org/genome-to-diffraction/generated/{kind}.schema.json",
    )
    return schema
