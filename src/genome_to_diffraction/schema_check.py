"""Repository-level JSON Schema and example validation."""

import csv
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from genome_to_diffraction.schemas.io import (
    ContractError,
    ContractLoadError,
    load_contract,
    load_json_document,
    load_yaml_document,
)
from genome_to_diffraction.schemas.manifests import (
    CatalogueManifest,
    CrystalManifest,
    validate_manifest_references,
)

_FIXTURE_MAP = {
    "catalogue_manifest.schema.json": Path("examples/catalogue_manifest.json"),
    "crystal_manifest.schema.json": Path("examples/crystal_manifest.json"),
    "database_manifest.schema.json": Path(
        "tests/fixtures/stubs/database_manifest.json"
    ),
    "mr_hypothesis.schema.json": Path("tests/fixtures/stubs/mr_hypothesis.json"),
    "phenix_install_manifest.schema.json": Path(
        "tests/fixtures/stubs/phenix_install_manifest.json"
    ),
    "pipeline_config.schema.json": Path("examples/config.yaml"),
    "provider_execution_plan.schema.json": Path("examples/provider_plan.json"),
    "review_decision.schema.json": Path("tests/fixtures/stubs/review_decision.json"),
}

_REVIEW_COLUMNS = (
    "checkpoint",
    "item_id",
    "decision",
    "reviewer",
    "reviewed_at",
    "comment",
    "override_reason",
)

_TYPED_FIXTURES = (
    ("catalogue-manifest", Path("examples/catalogue_manifest.json")),
    ("catalogue-manifest", Path("examples/catalogues.tsv")),
    ("crystal-manifest", Path("examples/crystal_manifest.json")),
    ("crystal-manifest", Path("examples/crystals.tsv")),
    ("pipeline-config", Path("examples/config.yaml")),
    ("provider-execution-plan", Path("examples/provider_plan.json")),
    ("database-manifest", Path("tests/fixtures/stubs/database_manifest.json")),
    (
        "phenix-install-manifest",
        Path("tests/fixtures/stubs/phenix_install_manifest.json"),
    ),
    ("mr-hypothesis", Path("tests/fixtures/stubs/mr_hypothesis.json")),
    ("review-decisions", Path("examples/approvals/approved_mr_seeds.tsv")),
    (
        "review-decisions",
        Path("examples/approvals/approved_sequence_groups.tsv"),
    ),
)


def _load_document(path: Path) -> Any:
    if path.suffix in {".yaml", ".yml"}:
        return load_yaml_document(path)
    return load_json_document(path)


def _format_validation_error(error: ValidationError) -> str:
    location = "/".join(str(part) for part in error.absolute_path) or "<root>"
    return f"{location}: {error.message}"


def _validate_review_tsvs(repository: Path) -> Iterable[str]:
    approval_root = repository / "examples" / "approvals"
    for path in sorted(approval_root.glob("*.tsv")):
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if tuple(reader.fieldnames or ()) != _REVIEW_COLUMNS:
                yield f"{path}: unexpected review TSV columns"
                continue
            for row_number, row in enumerate(reader, start=2):
                if row["checkpoint"] not in {"mr_seed", "sequence_candidate"}:
                    yield f"{path}:{row_number}: invalid checkpoint"
                if row["decision"] not in {
                    "approve",
                    "reject",
                    "defer",
                    "retain_alternative",
                }:
                    yield f"{path}:{row_number}: invalid decision"


def validate_repository(repository: Path) -> list[str]:
    """Return all schema and example errors found under *repository*."""

    repository = repository.resolve()
    schema_root = repository / "schemas"
    errors: list[str] = []

    if not schema_root.is_dir():
        return [f"schema directory not found: {schema_root}"]

    schema_paths = sorted(schema_root.glob("*.schema.json"))
    actual_schema_names = {path.name for path in schema_paths}
    expected_schema_names = set(_FIXTURE_MAP)
    if actual_schema_names != expected_schema_names:
        missing = sorted(expected_schema_names - actual_schema_names)
        unexpected = sorted(actual_schema_names - expected_schema_names)
        if missing:
            errors.append(f"missing schemas: {', '.join(missing)}")
        if unexpected:
            errors.append(f"schemas without fixtures: {', '.join(unexpected)}")

    for schema_path in schema_paths:
        try:
            schema = _load_document(schema_path)
            Draft202012Validator.check_schema(schema)
        except (ContractLoadError, SchemaError) as error:
            errors.append(f"{schema_path}: invalid schema: {error}")
            continue

        fixture_relative = _FIXTURE_MAP.get(schema_path.name)
        if fixture_relative is None:
            continue
        fixture_path = repository / fixture_relative
        try:
            instance = _load_document(fixture_path)
        except ContractLoadError as error:
            errors.append(f"{fixture_path}: cannot load fixture: {error}")
            continue

        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validation_errors = sorted(
            validator.iter_errors(instance), key=lambda item: str(item.path)
        )
        for validation_error in validation_errors:
            errors.append(
                f"{fixture_path} against {schema_path.name}: "
                f"{_format_validation_error(validation_error)}"
            )

    nextflow_schema_path = repository / "nextflow_schema.json"
    try:
        nextflow_schema = _load_document(nextflow_schema_path)
        Draft202012Validator.check_schema(nextflow_schema)
    except (ContractLoadError, SchemaError) as error:
        errors.append(f"{nextflow_schema_path}: invalid schema: {error}")

    errors.extend(_validate_review_tsvs(repository))

    typed_models: dict[str, list[Any]] = {}
    for kind, relative_path in _TYPED_FIXTURES:
        fixture_path = repository / relative_path
        try:
            model = load_contract(fixture_path, kind, progress=False)
        except ContractError as error:
            errors.append(
                f"{fixture_path}: application-model validation failed: {error}"
            )
            continue
        typed_models.setdefault(kind, []).append(model)

    catalogue_models = typed_models.get("catalogue-manifest", [])
    crystal_models = typed_models.get("crystal-manifest", [])
    if catalogue_models and crystal_models:
        catalogue = catalogue_models[0]
        crystal = crystal_models[0]
        if isinstance(catalogue, CatalogueManifest) and isinstance(
            crystal, CrystalManifest
        ):
            try:
                validate_manifest_references(catalogue, crystal)
            except ValueError as error:
                errors.append(f"manifest cross-reference validation failed: {error}")
    return errors
