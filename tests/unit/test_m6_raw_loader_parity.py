"""Mutation parity for raw M6 authority and evidence documents."""

import json
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
import yaml

from genome_to_diffraction.benchmarks.m6_collection import (
    _json_object as load_collected_json_object,
)
from genome_to_diffraction.benchmarks.m6_collection import (
    _jsonl_text as load_collected_jsonl_text,
)
from genome_to_diffraction.benchmarks.m6_collection import (
    _load_private_truth,
)
from genome_to_diffraction.benchmarks.m6_edge import (
    _json_integer as load_edge_json_integer,
)
from genome_to_diffraction.benchmarks.m6_edge import (
    _json_object as load_edge_json_object,
)
from genome_to_diffraction.benchmarks.m6_evaluation import load_m6_evidence
from genome_to_diffraction.benchmarks.m6_execution import (
    M6ExecutionPolicy,
    load_m6_execution_policy,
)
from genome_to_diffraction.benchmarks.m6_model_policy import (
    _object as load_model_policy_object,
)
from genome_to_diffraction.benchmarks.m6_nextflow import (
    _json_integer as load_nextflow_json_integer,
)
from genome_to_diffraction.benchmarks.m6_nextflow import (
    _json_object as load_nextflow_json_object,
)
from genome_to_diffraction.benchmarks.m6_nextflow import (
    _jsonl_dicts as load_nextflow_jsonl_dicts,
)
from genome_to_diffraction.benchmarks.m6_protocol import (
    M6BenchmarkProtocol,
    load_m6_protocol,
)
from genome_to_diffraction.benchmarks.m6_runner import (
    load_m6_preparation_manifest,
)
from genome_to_diffraction.benchmarks.m6_scientific import (
    _json_object as load_scientific_json_object,
)
from genome_to_diffraction.benchmarks.m6_scientific import (
    _jsonl_objects as load_scientific_jsonl_objects,
)
from genome_to_diffraction.benchmarks.m6_verification import (
    _load_manifest as load_runner_manifest,
)
from genome_to_diffraction.benchmarks.m6_verification import (
    _verify_json as load_verified_json_object,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import sha256_file

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "benchmarks/m6/protocol.yaml"
EXECUTION_POLICIES = (
    ROOT / "benchmarks/m6/execution-nextflow-v1.yaml",
    ROOT / "benchmarks/m6/execution-nextflow-marmic-v1.yaml",
)
SCIENTIFIC_FIXTURE = (
    ROOT / "tests/fixtures/stubs/m6_nextflow/track_output/m6_scientific_summary.json"
)
SCIENTIFIC_JSONL_FIXTURE = (
    ROOT / "tests/fixtures/stubs/m6_nextflow/track_output/m6_case_results.jsonl"
)


def _invoke_loader(family: str, path: Path) -> None:
    if family == "protocol-yaml":
        load_m6_protocol(path)
    elif family == "execution-yaml":
        load_m6_execution_policy(path)
    elif family == "preparation-json":
        load_m6_preparation_manifest(path)
    elif family == "evaluation-json":
        load_m6_evidence(path)
    elif family == "scientific-json":
        load_scientific_json_object(path)
    elif family == "scientific-jsonl":
        load_scientific_jsonl_objects(path)
    elif family == "runner-manifest-json":
        load_runner_manifest(path)
    elif family == "verification-json":
        load_verified_json_object(path)
    elif family == "model-policy-json":
        load_model_policy_object(path, "M6 model policy")
    elif family == "collection-json":
        load_collected_json_object(path, "collection manifest")
    elif family == "collection-jsonl":
        load_collected_jsonl_text(path.read_text(encoding="utf-8"), path, "fixture")
    elif family == "edge-json":
        load_edge_json_object(path, "edge fixture")
    elif family == "nextflow-json":
        load_nextflow_json_object(path, "Nextflow fixture")
    elif family == "nextflow-jsonl":
        load_nextflow_jsonl_dicts(path, required=True)
    elif family == "private-truth-json":
        protocol = load_m6_protocol(PROTOCOL)
        _load_private_truth(
            path,
            protocol=protocol,
            protocol_sha256=sha256_file(PROTOCOL),
        )
    else:
        raise AssertionError(f"unhandled M6 raw-loader family: {family}")


@pytest.mark.parametrize(
    ("family", "input_format"),
    (
        ("protocol-yaml", "yaml"),
        ("execution-yaml", "yaml"),
        ("preparation-json", "json"),
        ("evaluation-json", "json"),
        ("scientific-json", "json"),
        ("scientific-jsonl", "jsonl"),
        ("runner-manifest-json", "json"),
        ("verification-json", "json"),
        ("model-policy-json", "json"),
        ("collection-json", "json"),
        ("collection-jsonl", "jsonl"),
        ("edge-json", "json"),
        ("nextflow-json", "json"),
        ("nextflow-jsonl", "jsonl"),
        ("private-truth-json", "json"),
    ),
)
@pytest.mark.parametrize("mutation", ("duplicate", "non-finite"))
def test_m6_raw_loader_families_reject_ambiguous_numeric_documents(
    tmp_path: Path,
    family: str,
    input_format: str,
    mutation: str,
) -> None:
    suffix = (
        "yaml"
        if input_format == "yaml"
        else "jsonl"
        if input_format == "jsonl"
        else "json"
    )
    path = tmp_path / f"{family}-{mutation}.{suffix}"
    if input_format == "yaml":
        contents = (
            "root:\n  value: 1\n  value: 2\n"
            if mutation == "duplicate"
            else "root:\n  value: .nan\n"
        )
    else:
        contents = (
            '{"root":{"value":1,"value":2}}'
            if mutation == "duplicate"
            else '{"root":{"value":NaN}}'
        )
        if input_format == "jsonl":
            contents = f"{contents}\n"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises((PublicControlError, ValueError)) as captured:
        _invoke_loader(family, path)

    assert f"{path}" in str(captured.value)
    assert "/root/value" in str(captured.value)
    expected = "duplicate mapping key" if mutation == "duplicate" else "numeric"
    assert expected in str(captured.value)


def test_valid_frozen_m6_yaml_documents_are_semantically_unchanged() -> None:
    protocol_document = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    expected_protocol = M6BenchmarkProtocol.model_validate(protocol_document)
    assert load_m6_protocol(PROTOCOL) == expected_protocol

    for path in EXECUTION_POLICIES:
        policy_document = yaml.safe_load(path.read_text(encoding="utf-8"))
        expected_policy = M6ExecutionPolicy.model_validate(policy_document)
        assert load_m6_execution_policy(path) == expected_policy


def test_valid_frozen_m6_scientific_documents_are_semantically_unchanged() -> None:
    expected_summary = json.loads(SCIENTIFIC_FIXTURE.read_text(encoding="utf-8"))
    expected_rows = tuple(
        json.loads(line)
        for line in SCIENTIFIC_JSONL_FIXTURE.read_text(encoding="utf-8").splitlines()
        if line
    )

    assert load_scientific_json_object(SCIENTIFIC_FIXTURE) == expected_summary
    assert load_verified_json_object(SCIENTIFIC_FIXTURE) == expected_summary
    assert load_model_policy_object(SCIENTIFIC_FIXTURE, "fixture") == expected_summary
    assert load_collected_json_object(SCIENTIFIC_FIXTURE, "fixture") == expected_summary
    assert load_scientific_jsonl_objects(SCIENTIFIC_JSONL_FIXTURE) == expected_rows


@pytest.mark.parametrize("value", ("1", True, 1.0, None, -1))
@pytest.mark.parametrize("loader", (load_edge_json_integer, load_nextflow_json_integer))
def test_m6_raw_integer_fields_reject_coercion_and_negative_values(
    loader: Callable[[Mapping[str, object], str, str], int], value: object
) -> None:
    with pytest.raises((PublicControlError, ValueError)):
        loader({"count": value}, "count", "fixture")
