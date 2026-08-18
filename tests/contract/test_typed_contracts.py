"""Contract tests for typed models, adapters, and generated schemas."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from genome_to_diffraction.schemas.base import ContractModel, UtcTimestamp
from genome_to_diffraction.schemas.io import (
    ContractLoadError,
    ContractValidationError,
    contract_json_schema,
    contract_kinds,
    load_contract,
)
from genome_to_diffraction.schemas.manifests import (
    CatalogueManifest,
    CrystalEntry,
    CrystalManifest,
    SmokeTestStatus,
    require_remote_submission_authorisation,
    validate_manifest_references,
)
from genome_to_diffraction.schemas.results import (
    AdditionalCopyResult,
    MtzPreflightRecord,
    NormalisedMrResult,
    SequenceGroupRecord,
    SourceProteinRecord,
    StructuralSearchHit,
    StructuralSearchResult,
)

REPOSITORY = Path(__file__).resolve().parents[2]


class _JsonWireDecodingProbe(ContractModel):
    """Exercise intentional JSON-mode conversion independently of schemas."""

    occurred_at: UtcTimestamp
    status: SmokeTestStatus
    path: Path


@pytest.mark.parametrize(
    ("kind", "relative_path"),
    (
        ("catalogue-manifest", "examples/catalogue_manifest.json"),
        ("catalogue-manifest", "examples/catalogues.tsv"),
        ("crystal-manifest", "examples/crystal_manifest.json"),
        ("crystal-manifest", "examples/crystals.tsv"),
        ("pipeline-config", "examples/config.yaml"),
        ("database-manifest", "tests/fixtures/stubs/database_manifest.json"),
        (
            "phenix-install-manifest",
            "tests/fixtures/stubs/phenix_install_manifest.json",
        ),
        ("mr-hypothesis", "tests/fixtures/stubs/mr_hypothesis.json"),
        ("review-decisions", "examples/approvals/approved_mr_seeds.tsv"),
    ),
)
def test_approved_examples_validate_with_application_models(
    kind: str, relative_path: str
) -> None:
    model = load_contract(REPOSITORY / relative_path, kind, progress=False)
    assert model.model_dump(mode="json")["schema_version"] == "1.0"


def test_duplicate_catalogue_ids_fail_with_precise_diagnostic(tmp_path: Path) -> None:
    document = json.loads(
        (REPOSITORY / "examples/catalogue_manifest.json").read_text(encoding="utf-8")
    )
    document["catalogues"].append(dict(document["catalogues"][0]))
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(
        ContractValidationError, match="catalogue_id values must be unique"
    ):
        load_contract(path, "catalogue-manifest", progress=False)


def test_missing_required_field_fails_at_exact_path(tmp_path: Path) -> None:
    document = json.loads(
        (REPOSITORY / "examples/catalogue_manifest.json").read_text(encoding="utf-8")
    )
    del document["catalogues"][0]["proteome_faa"]
    path = tmp_path / "missing.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ContractValidationError) as captured:
        load_contract(path, "catalogue-manifest", progress=False)
    assert f"{path}:/catalogues/0" in str(captured.value)
    assert "proteome_faa" in str(captured.value)


def test_unknown_field_fails_at_json_pointer(tmp_path: Path) -> None:
    document = json.loads(
        (REPOSITORY / "examples/crystal_manifest.json").read_text(encoding="utf-8")
    )
    document["crystals"][0]["observation_label_typo"] = "I,SIGI"
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ContractValidationError) as captured:
        load_contract(path, "crystal-manifest", progress=False)
    assert f"{path}:/crystals/0" in str(captured.value)
    assert "observation_label_typo" in str(captured.value)


@pytest.mark.parametrize(
    ("filename", "kind", "contents", "pointer", "duplicate_key"),
    (
        (
            "duplicate-top-level.json",
            "crystal-manifest",
            '{"schema_version":"1.0","schema_version":"1.0","crystals":[]}',
            "/schema_version",
            "schema_version",
        ),
        (
            "duplicate-path.json",
            "crystal-manifest",
            '{"schema_version":"1.0","crystals":[{"mtz":"a.mtz","mtz":"b.mtz"}]}',
            "/crystals/0/mtz",
            "mtz",
        ),
        (
            "duplicate-consent.json",
            "crystal-manifest",
            '{"schema_version":"1.0","crystals":['
            '{"allow_remote_sequence_submission":false,'
            '"allow_remote_sequence_submission":true}]}',
            "/crystals/0/allow_remote_sequence_submission",
            "allow_remote_sequence_submission",
        ),
        (
            "duplicate-top-level.yaml",
            "pipeline-config",
            'schema_version: "1.0"\nschema_version: "1.0"\n',
            "/schema_version",
            "schema_version",
        ),
        (
            "duplicate-provider.yaml",
            "pipeline-config",
            "providers:\n  pdb_sequence:\n    enabled: true\n    enabled: false\n",
            "/providers/pdb_sequence/enabled",
            "enabled",
        ),
        (
            "duplicate-config.yaml",
            "pipeline-config",
            "search_limits:\n  max_first_copy_jobs: 200\n  max_first_copy_jobs: 1\n",
            "/search_limits/max_first_copy_jobs",
            "max_first_copy_jobs",
        ),
    ),
)
def test_duplicate_mapping_keys_fail_before_contract_validation(
    tmp_path: Path,
    filename: str,
    kind: str,
    contents: str,
    pointer: str,
    duplicate_key: str,
) -> None:
    path = tmp_path / filename
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ContractLoadError) as captured:
        load_contract(path, kind, progress=False)

    assert f"{path}:{pointer}" in str(captured.value)
    assert f"duplicate mapping key {duplicate_key!r}" in str(captured.value)


@pytest.mark.parametrize(
    ("keys", "value", "pointer"),
    (
        (
            ("providers", "pdb_sequence", "enabled"),
            "false",
            "/providers/pdb_sequence/enabled",
        ),
        (
            ("search_limits", "max_first_copy_jobs"),
            "200",
            "/search_limits/max_first_copy_jobs",
        ),
        (
            ("search_limits", "max_first_copy_jobs"),
            200.0,
            "/search_limits/max_first_copy_jobs",
        ),
    ),
)
def test_contract_loader_rejects_wire_type_coercion(
    tmp_path: Path,
    keys: tuple[str, ...],
    value: object,
    pointer: str,
) -> None:
    document = yaml.safe_load(
        (REPOSITORY / "examples/config.yaml").read_text(encoding="utf-8")
    )
    target = document
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    path = tmp_path / "coercion.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ContractValidationError) as captured:
        load_contract(path, "pipeline-config", progress=False)

    assert f"{path}:{pointer}" in str(captured.value)


@pytest.mark.parametrize("constant", ("NaN", "Infinity", "-Infinity"))
def test_contract_loader_rejects_non_standard_json_numbers(
    tmp_path: Path, constant: str
) -> None:
    source = (
        REPOSITORY / "tests/fixtures/stubs/first_copy_phaser/normalised_mr_result.json"
    ).read_text(encoding="utf-8")
    path = tmp_path / "non-finite.json"
    path.write_text(
        source.replace('"llg": null', f'"llg": {constant}'),
        encoding="utf-8",
    )

    with pytest.raises(ContractLoadError, match="non-standard JSON numeric constant"):
        load_contract(path, "normalised-mr-result", progress=False)


@pytest.mark.parametrize("constant", (".nan", ".inf", "-.inf"))
def test_contract_loader_rejects_non_finite_yaml_numbers(
    tmp_path: Path, constant: str
) -> None:
    document = json.loads(
        (
            REPOSITORY
            / "tests/fixtures/stubs/first_copy_phaser/normalised_mr_result.json"
        ).read_text(encoding="utf-8")
    )
    text = yaml.safe_dump(document).replace("llg: null", f"llg: {constant}")
    path = tmp_path / "non-finite.yaml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ContractLoadError) as captured:
        load_contract(path, "normalised-mr-result", progress=False)

    assert f"{path}:/llg" in str(captured.value)
    assert "non-finite numeric value" in str(captured.value)


@pytest.mark.parametrize("value", ("4", 4.0))
def test_direct_jsonl_result_rejects_non_integer_wire_values(value: object) -> None:
    document = json.loads(
        (REPOSITORY / "tests/fixtures/stubs/sequence_groups.jsonl").read_text(
            encoding="utf-8"
        )
    )
    document["length_aa"] = value

    with pytest.raises(ValidationError, match="valid integer"):
        SequenceGroupRecord.model_validate_json(json.dumps(document))


def test_direct_jsonl_result_rejects_string_boolean() -> None:
    document = json.loads(
        (REPOSITORY / "tests/fixtures/stubs/additional_copy_result.json").read_text(
            encoding="utf-8"
        )
    )
    document["top_solution_packed"] = "true"

    with pytest.raises(ValidationError, match="valid boolean"):
        AdditionalCopyResult.model_validate_json(json.dumps(document))


@pytest.mark.parametrize("constant", ("NaN", "Infinity", "-Infinity"))
def test_direct_jsonl_result_rejects_non_finite_metrics(constant: str) -> None:
    source = (
        REPOSITORY / "tests/fixtures/stubs/first_copy_phaser/normalised_mr_result.json"
    ).read_text(encoding="utf-8")

    with pytest.raises(ValidationError, match="finite number"):
        NormalisedMrResult.model_validate_json(
            source.replace('"llg": null', f'"llg": {constant}')
        )


def test_strict_json_wire_mode_preserves_supported_string_decoding() -> None:
    model = _JsonWireDecodingProbe.model_validate_json(
        '{"occurred_at":"2026-08-18T12:34:56+02:00",'
        '"status":"not_run","path":"relative/input.mtz"}'
    )

    assert model.occurred_at.isoformat() == "2026-08-18T10:34:56+00:00"
    assert model.status is SmokeTestStatus.NOT_RUN
    assert model.path == Path("relative/input.mtz")


def test_tsv_error_includes_row_and_column(tmp_path: Path) -> None:
    path = tmp_path / "catalogues.tsv"
    path.write_text(
        "catalogue_id\tproteome_faa\tannotation_provider\tannotation_version\t"
        "is_contaminant_catalogue\ncat_a\ta.faa\tPGAP\t1\tmaybe\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ContractLoadError, match=r"catalogues\.tsv:2:is_contaminant_catalogue"
    ):
        load_contract(path, "catalogue-manifest", progress=False)


def test_cross_reference_validation_rejects_unknown_catalogue() -> None:
    catalogues = load_contract(
        REPOSITORY / "examples/catalogue_manifest.json",
        "catalogue-manifest",
        progress=False,
    )
    crystals = load_contract(
        REPOSITORY / "examples/crystal_manifest.json",
        "crystal-manifest",
        progress=False,
    )
    assert isinstance(catalogues, CatalogueManifest)
    assert isinstance(crystals, CrystalManifest)
    invalid = CrystalManifest.model_validate(
        {
            **crystals.model_dump(mode="json"),
            "crystals": [
                {
                    **crystals.model_dump(mode="json")["crystals"][0],
                    "catalogue_id": "missing",
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="unknown catalogue_id"):
        validate_manifest_references(catalogues, invalid)


def test_inconsistent_sds_arrays_fail_application_validation(tmp_path: Path) -> None:
    document = json.loads(
        (REPOSITORY / "examples/crystal_manifest.json").read_text(encoding="utf-8")
    )
    document["crystals"][0]["sds_page_mass_kda"] = [42.0, 24.0]
    document["crystals"][0]["sds_page_band_roles"] = ["dominant"]
    path = tmp_path / "sds.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ContractValidationError, match="sds_page_band_roles"):
        load_contract(path, "crystal-manifest", progress=False)


def test_remote_submission_requires_two_explicit_authorisations() -> None:
    crystal = CrystalEntry.model_validate(
        {
            "crystal_id": "crystal_a",
            "mtz": "input.mtz",
            "catalogue_id": "catalogue_a",
            "allow_remote_sequence_submission": False,
        }
    )
    with pytest.raises(ValueError, match="disabled for this run"):
        require_remote_submission_authorisation(crystal, run_allows_remote=False)
    with pytest.raises(ValueError, match="disabled for crystal"):
        require_remote_submission_authorisation(crystal, run_allows_remote=True)
    require_remote_submission_authorisation(
        crystal.model_copy(update={"allow_remote_sequence_submission": True}),
        run_allows_remote=True,
    )


def test_verified_phenix_manifest_cannot_contain_failed_command(tmp_path: Path) -> None:
    document = json.loads(
        (REPOSITORY / "tests/fixtures/stubs/phenix_install_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    document["status"] = "verified"
    path = tmp_path / "invalid-verified-phenix.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ContractValidationError, match="smoke_test_status"):
        load_contract(path, "phenix-install-manifest", progress=False)


def test_verified_phenix_manifest_requires_command_executable_digest(
    tmp_path: Path,
) -> None:
    document = json.loads(
        (REPOSITORY / "tests/fixtures/stubs/phenix_install_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    document["status"] = "verified"
    document["required_commands"][0]["smoke_test_status"] = "passed"
    path = tmp_path / "missing-command-digest.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ContractValidationError, match="executable_sha256"):
        load_contract(path, "phenix-install-manifest", progress=False)


@pytest.mark.parametrize("kind", contract_kinds())
def test_generated_contract_schema_is_draft_2020_12(kind: str) -> None:
    schema = contract_json_schema(kind)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_tqdm_progress_can_be_enabled_for_tabular_input(
    capsys: pytest.CaptureFixture[str],
) -> None:
    load_contract(
        REPOSITORY / "examples/catalogues.tsv",
        "catalogue-manifest",
        progress=True,
    )
    assert "Reading catalogues.tsv" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("filename", "model"),
    (
        ("sequence_groups.jsonl", SequenceGroupRecord),
        ("source_records.jsonl", SourceProteinRecord),
        ("mtz_preflight.jsonl", MtzPreflightRecord),
    ),
)
def test_task05_stub_jsonl_records_validate(
    filename: str,
    model: type[SequenceGroupRecord | SourceProteinRecord | MtzPreflightRecord],
) -> None:
    path = REPOSITORY / "tests/fixtures/stubs" / filename
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert lines
    for line in lines:
        model.model_validate_json(line)


@pytest.mark.parametrize(
    ("filename", "model"),
    (
        ("search_results.jsonl", StructuralSearchResult),
        ("structural_hits.jsonl", StructuralSearchHit),
    ),
)
def test_structural_search_stub_jsonl_records_validate(
    filename: str,
    model: type[StructuralSearchResult | StructuralSearchHit],
) -> None:
    path = REPOSITORY / "tests/fixtures/stubs/structure_search" / filename
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert lines
    for line in lines:
        model.model_validate_json(line)
