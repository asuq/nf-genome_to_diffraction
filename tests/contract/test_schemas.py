"""Contract tests for schemas, examples, and review files."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from genome_to_diffraction.schema_check import validate_repository

REPOSITORY = Path(__file__).resolve().parents[2]


def test_repository_schemas_and_examples_validate() -> None:
    assert validate_repository(REPOSITORY) == []


def test_nextflow_schema_is_draft_2020_12() -> None:
    schema = json.loads(
        (REPOSITORY / "nextflow_schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
