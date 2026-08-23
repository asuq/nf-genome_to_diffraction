"""JSON, YAML, and TSV adapters with precise validation diagnostics."""

import csv
import io
import json
import logging
import math
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import IO, Literal, Protocol, cast

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from genome_to_diffraction.schemas.manifests import (
    CatalogueImportManifest,
    CatalogueManifest,
    CrystalManifest,
    DatabaseManifest,
    GelEvidenceManifest,
    PhenixInstallManifest,
    PipelineConfig,
    RunManifest,
)
from genome_to_diffraction.schemas.providers import ProviderExecutionPlan
from genome_to_diffraction.schemas.results import (
    CoordinateHitMappingRecord,
    CoordinateSourceRecord,
    CopyCountAssessment,
    FreeRGenerationRecord,
    MatthewsHypothesis,
    MrHypothesis,
    MtzPreflightRecord,
    NormalisedMrResult,
    ProcessedModelRecord,
    ResourceSummaryRecord,
    ReviewDecisionManifest,
    ScientificStatusRecord,
    SequenceGroupRecord,
    SourceProteinRecord,
    StructuralSearchHit,
    StructuralSearchResult,
)
from genome_to_diffraction.schemas.v2.review import (
    PhaseIIIReviewDecision,
    PhaseIIIReviewDecisionFile,
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
class _MappingPairs:
    """Mapping entries retained until duplicate keys can be located."""

    entries: tuple[tuple[object, object], ...]


@dataclass(frozen=True)
class _JsonNumericConstant:
    """Non-standard JSON numeric constant retained until its path is known."""

    value: str


class _PairsSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that preserves mapping pairs for strict validation."""


class _TsvReader(Protocol):
    """Structural type exposed by ``csv.reader``."""

    line_num: int

    def __iter__(self) -> Iterator[list[str]]: ...

    def __next__(self) -> list[str]: ...


@dataclass(frozen=True)
class ContractSpec:
    """Model, authoritative schema, and optional tabular adapter."""

    model: type[BaseModel]
    schema_filename: str | None = None
    tsv_adapter: TsvAdapter | None = None
    tsv_required_columns: tuple[str, ...] = ()


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


_PHASE3_REVIEW_TSV_COLUMNS = frozenset(
    {
        "checkpoint",
        "owned_parent_run_id",
        "review_package_id",
        "review_package_manifest_sha256",
        "crystal_id",
        "item_id",
        "decision",
        "reviewer",
        "reviewed_at",
        "reason",
        "comment",
    }
)


def _phase3_review_tsv(
    rows: Iterator[tuple[int, dict[str, str]]], path: Path
) -> object:
    metadata_fields = (
        "checkpoint",
        "owned_parent_run_id",
        "review_package_id",
        "review_package_manifest_sha256",
    )
    metadata: dict[str, str] | None = None
    decisions: list[dict[str, object]] = []
    for row_number, row in rows:
        unexpected = sorted(set(row) - _PHASE3_REVIEW_TSV_COLUMNS)
        if unexpected:
            raise ContractLoadError(
                f"{path}:{row_number}:{unexpected[0]}: unexpected TSV column"
            )
        row_metadata = {field: row[field].strip() for field in metadata_fields}
        if metadata is None:
            metadata = row_metadata
        elif row_metadata != metadata:
            raise ContractLoadError(
                f"{path}:{row_number}:checkpoint: Phase III review TSV mixes "
                "checkpoint or parent-package metadata"
            )
        decisions.append(
            _drop_nulls(
                {
                    "crystal_id": _optional(row["crystal_id"]),
                    "item_id": _optional(row["item_id"]),
                    "decision": _optional(row["decision"]),
                    "reviewer": _optional(row["reviewer"]),
                    "reviewed_at": _optional(row["reviewed_at"]),
                    "reason": _optional(row["reason"]),
                    "comment": _optional(row.get("comment", "")),
                }
            )
        )
    if metadata is None:
        raise ContractLoadError(f"{path}:2:row: Phase III review TSV has no decisions")
    try:
        decision_file = PhaseIIIReviewDecisionFile.from_content(
            checkpoint=metadata["checkpoint"],
            owned_parent_run_id=metadata["owned_parent_run_id"],
            review_package_id=metadata["review_package_id"],
            review_package_manifest_sha256=metadata["review_package_manifest_sha256"],
            decisions=tuple(
                PhaseIIIReviewDecision.model_validate(decision)
                for decision in decisions
            ),
        )
    except ValidationError as error:
        raise ContractLoadError(
            f"{path}: Phase III review TSV violates its typed contract: {error}"
        ) from error
    return decision_file.model_dump(mode="json", exclude_none=False)


def _gel_evidence_tsv(rows: Iterator[tuple[int, dict[str, str]]], path: Path) -> object:
    observations: list[dict[str, object]] = []
    for row_number, row in rows:
        converted: dict[str, object] = {
            key: _optional(value) for key, value in row.items()
        }
        for field in ("apparent_mass_kda", "absolute_uncertainty_kda"):
            converted[field] = _number(
                row.get(field, ""),
                converter=float,
                path=path,
                row=row_number,
                column=field,
            )
        observations.append(_drop_nulls(converted))
    return {"schema_version": "2.0", "observations": observations}


CONTRACTS: dict[str, ContractSpec] = {
    "catalogue-import-manifest": ContractSpec(CatalogueImportManifest),
    "catalogue-manifest": ContractSpec(
        CatalogueManifest,
        "catalogue_manifest.schema.json",
        _catalogue_tsv,
        (
            "catalogue_id",
            "proteome_faa",
            "annotation_provider",
            "annotation_version",
            "is_contaminant_catalogue",
        ),
    ),
    "crystal-manifest": ContractSpec(
        CrystalManifest,
        "crystal_manifest.schema.json",
        _crystal_tsv,
        (
            "crystal_id",
            "mtz",
            "catalogue_id",
            "allow_remote_sequence_submission",
        ),
    ),
    "database-manifest": ContractSpec(
        DatabaseManifest, "database_manifest.schema.json"
    ),
    "gel-evidence-manifest": ContractSpec(
        GelEvidenceManifest,
        "gel_evidence_manifest.schema.json",
        _gel_evidence_tsv,
        (
            "observation_id",
            "crystal_id",
            "method",
            "apparent_mass_kda",
            "absolute_uncertainty_kda",
            "condition",
            "band_role",
            "replicate_id",
            "source",
        ),
    ),
    "phenix-install-manifest": ContractSpec(
        PhenixInstallManifest, "phenix_install_manifest.schema.json"
    ),
    "pipeline-config": ContractSpec(PipelineConfig, "pipeline_config.schema.json"),
    "provider-execution-plan": ContractSpec(
        ProviderExecutionPlan, "provider_execution_plan.schema.json"
    ),
    "mr-hypothesis": ContractSpec(MrHypothesis, "mr_hypothesis.schema.json"),
    "review-decisions": ContractSpec(
        ReviewDecisionManifest,
        "review_decision.schema.json",
        _review_tsv,
        ("checkpoint", "item_id", "decision", "reviewer", "reviewed_at"),
    ),
    "phase3-review-decisions": ContractSpec(
        PhaseIIIReviewDecisionFile,
        tsv_adapter=_phase3_review_tsv,
        tsv_required_columns=(
            "checkpoint",
            "owned_parent_run_id",
            "review_package_id",
            "review_package_manifest_sha256",
            "crystal_id",
            "item_id",
            "decision",
            "reviewer",
            "reviewed_at",
            "reason",
        ),
    ),
    "resource-summary": ContractSpec(ResourceSummaryRecord),
    "run-manifest": ContractSpec(RunManifest),
    "sequence-group": ContractSpec(SequenceGroupRecord),
    "source-protein": ContractSpec(SourceProteinRecord),
    "structural-hit": ContractSpec(StructuralSearchHit),
    "structural-search-result": ContractSpec(StructuralSearchResult),
    "coordinate-source": ContractSpec(CoordinateSourceRecord),
    "coordinate-hit-mapping": ContractSpec(CoordinateHitMappingRecord),
    "free-r-generation": ContractSpec(FreeRGenerationRecord),
    "processed-model": ContractSpec(ProcessedModelRecord),
    "mtz-preflight": ContractSpec(MtzPreflightRecord),
    "matthews-hypothesis": ContractSpec(MatthewsHypothesis),
    "normalised-mr-result": ContractSpec(NormalisedMrResult),
    "copy-count-assessment": ContractSpec(CopyCountAssessment),
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


def _preserve_json_pairs(pairs: list[tuple[str, object]]) -> _MappingPairs:
    return _MappingPairs(tuple(pairs))


def _preserve_yaml_pairs(loader: yaml.SafeLoader, node: yaml.Node) -> _MappingPairs:
    if not isinstance(node, yaml.MappingNode):
        raise yaml.constructor.ConstructorError(
            None,
            None,
            f"expected a mapping node, but found {type(node).__name__}",
            node.start_mark,
        )
    loader.flatten_mapping(node)
    return _MappingPairs(
        tuple(
            (
                loader.construct_object(key_node, deep=True),
                loader.construct_object(value_node, deep=True),
            )
            for key_node, value_node in node.value
        )
    )


_PairsSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _preserve_yaml_pairs,
)


def _normalise_mapping_pairs(
    value: object,
    *,
    label: str | Path,
    parts: tuple[str | int, ...] = (),
) -> object:
    if isinstance(value, _MappingPairs):
        mapping: dict[object, object] = {}
        for key, item in value.entries:
            key_parts = (*parts, str(key))
            try:
                duplicate = key in mapping
            except TypeError as error:
                raise ContractLoadError(
                    f"{label}:{_json_pointer(key_parts)}: "
                    f"unhashable mapping key {key!r}"
                ) from error
            if duplicate:
                raise ContractLoadError(
                    f"{label}:{_json_pointer(key_parts)}: duplicate mapping key {key!r}"
                )
            mapping[key] = _normalise_mapping_pairs(
                item,
                label=label,
                parts=key_parts,
            )
        return mapping
    if isinstance(value, list):
        return [
            _normalise_mapping_pairs(item, label=label, parts=(*parts, index))
            for index, item in enumerate(value)
        ]
    if isinstance(value, _JsonNumericConstant):
        raise ContractLoadError(
            f"{label}:{_json_pointer(parts)}: non-standard JSON numeric constant "
            f"{value.value!r} is not allowed"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractLoadError(
            f"{label}:{_json_pointer(parts)}: non-finite numeric value is not allowed"
        )
    return value


def _read_json(handle: IO[str], label: str | Path) -> object:
    document = json.load(
        handle,
        object_pairs_hook=_preserve_json_pairs,
        parse_constant=_JsonNumericConstant,
    )
    return _normalise_mapping_pairs(document, label=label)


def _read_yaml(handle: IO[str], label: str | Path) -> object:
    document = yaml.load(handle, Loader=_PairsSafeLoader)
    return _normalise_mapping_pairs(document, label=label)


def parse_json_document(payload: str, *, label: str | Path) -> object:
    """Parse one finite JSON document with duplicate-key path diagnostics."""

    try:
        return _read_json(io.StringIO(payload), label)
    except json.JSONDecodeError as error:
        raise ContractLoadError(f"{label}:/: invalid JSON document: {error}") from error


def load_json_document(path: Path) -> object:
    """Load one finite JSON document without applying a scientific schema."""

    try:
        with path.open(encoding="utf-8") as handle:
            return _read_json(handle, path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractLoadError(
            f"{path}:/: cannot load JSON document: {error}"
        ) from error


def load_yaml_document(path: Path) -> object:
    """Load one finite YAML document without applying a scientific schema."""

    try:
        with path.open(encoding="utf-8") as handle:
            return _read_yaml(handle, path)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ContractLoadError(
            f"{path}:/: cannot load YAML document: {error}"
        ) from error


def _decode_tsv(path: Path) -> str:
    payload = path.read_bytes()
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        prefix = payload[: error.start]
        row = prefix.count(b"\n") + 1
        line_start = prefix.rfind(b"\n") + 1
        column = len(prefix[line_start:].decode("utf-8", errors="ignore")) + 1
        raise ContractLoadError(
            f"{path}:{row}:character-{column}: invalid UTF-8"
        ) from error


def _validated_tsv_rows(
    reader: _TsvReader,
    path: Path,
    *,
    required_columns: tuple[str, ...],
) -> Iterator[tuple[int, dict[str, str]]]:
    try:
        headers = next(reader)
    except StopIteration as error:
        raise ContractLoadError(f"{path}:1:header: TSV header is missing") from error
    except csv.Error as error:
        raise ContractLoadError(f"{path}:1:header: invalid TSV: {error}") from error
    if not headers:
        raise ContractLoadError(f"{path}:1:header: TSV header is missing")

    seen: dict[str, int] = {}
    for column_number, header in enumerate(headers, start=1):
        normalised = header.strip()
        if not normalised:
            raise ContractLoadError(
                f"{path}:1:column-{column_number}: TSV header is blank"
            )
        if header != normalised:
            raise ContractLoadError(
                f"{path}:1:{normalised}: TSV header has surrounding whitespace"
            )
        if normalised in seen:
            raise ContractLoadError(
                f"{path}:1:{normalised}: duplicate TSV header at columns "
                f"{seen[normalised]} and {column_number}"
            )
        seen[normalised] = column_number

    for required in required_columns:
        if required not in seen:
            raise ContractLoadError(
                f"{path}:1:{required}: required TSV header is missing"
            )

    while True:
        row_number = reader.line_num + 1
        try:
            values = next(reader)
        except StopIteration:
            return
        except csv.Error as error:
            raise ContractLoadError(
                f"{path}:{row_number}:row: invalid TSV: {error}"
            ) from error
        if len(values) < len(headers):
            missing_column = headers[len(values)]
            raise ContractLoadError(
                f"{path}:{row_number}:{missing_column}: TSV row has "
                f"{len(values)} fields; expected {len(headers)}"
            )
        if len(values) > len(headers):
            raise ContractLoadError(
                f"{path}:{row_number}:column-{len(headers) + 1}: TSV row has "
                f"{len(values)} fields; expected {len(headers)}"
            )
        row = dict(zip(headers, values, strict=True))
        for required in required_columns:
            value = row[required]
            if _is_null(value):
                raise ContractLoadError(
                    f"{path}:{row_number}:{required}: required TSV value is blank"
                )
        yield row_number, row


def _read_tsv(path: Path, spec: ContractSpec, *, progress: bool) -> object:
    adapter = spec.tsv_adapter
    if adapter is None:
        raise AssertionError("TSV reader requires an adapter")
    reader = csv.reader(
        io.StringIO(_decode_tsv(path), newline=""), delimiter="\t", strict=True
    )
    iterator = _validated_tsv_rows(
        reader,
        path,
        required_columns=spec.tsv_required_columns,
    )
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
            return _read_tsv(path, spec, progress=progress)
        if input_format == "json":
            return load_json_document(path)
        if input_format == "yaml":
            return load_yaml_document(path)
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
                schema = _read_json(handle, path)
            label = str(path)
        else:
            resource = resources.files("genome_to_diffraction").joinpath(
                "_schemas", spec.schema_filename
            )
            with resource.open("r", encoding="utf-8") as handle:
                schema = _read_json(handle, str(resource))
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
        wire_json = json.dumps(document, allow_nan=False, separators=(",", ":"))
        model = spec.model.model_validate_json(wire_json, strict=True)
    except ValidationError as error:
        raise ContractValidationError(
            [
                f"{path}:{_json_pointer(list(item['loc']))}: {item['msg']}"
                for item in error.errors(include_url=False)
            ]
        ) from error
    except (TypeError, ValueError) as error:
        raise ContractValidationError(
            [f"{path}:/: document is not valid finite JSON wire data: {error}"]
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
    if spec.schema_filename is not None:
        schema = _authoritative_schema(spec)
        if not isinstance(schema, Mapping):
            raise ContractLoadError(f"authoritative schema for {kind} is not an object")
        return dict(schema)
    schema = dict(spec.model.model_json_schema(mode="validation"))
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema.setdefault(
        "$id",
        f"https://example.org/genome-to-diffraction/generated/{kind}.schema.json",
    )
    return schema
