"""Contract tests for typed models, adapters, and generated schemas."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

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
    require_remote_submission_authorisation,
    validate_manifest_references,
)

REPOSITORY = Path(__file__).resolve().parents[2]


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
