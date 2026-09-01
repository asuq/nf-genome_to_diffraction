"""Tests for immutable provider-plan resolution without provider execution."""

import json
from pathlib import Path
from typing import cast

import pytest

from genome_to_diffraction.cli import main
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import PipelineConfig
from genome_to_diffraction.schemas.providers import (
    ProviderExecutionPlan,
    ProviderKey,
    ProviderPlanEntry,
)
from genome_to_diffraction.structure_search.provider_plan import (
    ProviderPlanError,
    ProviderPlanRequest,
    load_enabled_provider_route,
    resolve_provider_plan,
)

REPOSITORY = Path(__file__).resolve().parents[2]
CONFIG = REPOSITORY / "examples/config.yaml"
DATABASE = REPOSITORY / "tests/fixtures/stubs/provider_plan_database_manifest.json"
EXAMPLE_PLAN = REPOSITORY / "examples/provider_plan.json"


def _config_document() -> dict[str, object]:
    model = load_contract(CONFIG, "pipeline-config", progress=False)
    assert isinstance(model, PipelineConfig)
    return model.model_dump(mode="json")


def _write_config(
    tmp_path: Path,
    *,
    provider: ProviderKey | None = None,
    enabled: bool | None = None,
    max_hits: int | None = None,
) -> Path:
    document = _config_document()
    if provider is not None:
        providers = cast(dict[str, object], document["providers"])
        provider_config = cast(dict[str, object], providers[provider.value])
        if enabled is not None:
            provider_config["enabled"] = enabled
        if max_hits is not None:
            provider_config["max_hits"] = max_hits
    path = tmp_path / "config.json"
    path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _resolve(tmp_path: Path, config: Path = CONFIG, *, name: str = "plan"):
    return resolve_provider_plan(
        ProviderPlanRequest(
            pipeline_config=config,
            database_manifest=DATABASE,
            output_directory=tmp_path / name,
        )
    )


def _entries(plan: ProviderExecutionPlan) -> dict[ProviderKey, ProviderPlanEntry]:
    return {entry.provider: entry for entry in plan.entries}


def test_default_provider_plan_is_typed_checksum_bound_and_matches_example(
    tmp_path: Path,
) -> None:
    output = _resolve(tmp_path)
    loaded = load_contract(output.plan_json, "provider-execution-plan", progress=False)

    assert isinstance(loaded, ProviderExecutionPlan)
    assert loaded == output.plan
    assert output.plan_json.read_bytes() == EXAMPLE_PLAN.read_bytes()
    assert output.plan.enabled_providers == (
        ProviderKey.AFDB_EXACT,
        ProviderKey.FOLDSEEK_PROSTT5_PDB,
        ProviderKey.PDB_SEQUENCE,
    )
    assert output.plan.disabled_providers == (ProviderKey.ESM_ATLAS,)
    entries = _entries(output.plan)
    assert entries[ProviderKey.PDB_SEQUENCE].effective_max_hits == 3
    assert entries[ProviderKey.FOLDSEEK_PROSTT5_PDB].effective_max_hits == 3
    assert entries[ProviderKey.AFDB_EXACT].effective_max_hits == 1
    assert entries[ProviderKey.ESM_ATLAS].effective_max_hits == 0
    assert entries[ProviderKey.ESM_ATLAS].database_resources == ()
    assert entries[ProviderKey.ESM_ATLAS].requests_per_minute == 10
    assert entries[ProviderKey.ESM_ATLAS].max_sequence_length == 1500
    for provider, path in output.entry_json.items():
        entry = ProviderPlanEntry.model_validate_json(path.read_text(encoding="utf-8"))
        assert entry.provider is provider
        assert output.plan.entry_sha256[provider]


@pytest.mark.parametrize(
    ("provider", "configured", "effective"),
    (
        (ProviderKey.PDB_SEQUENCE, 7, 7),
        (ProviderKey.FOLDSEEK_PROSTT5_PDB, 9, 9),
        (ProviderKey.AFDB_EXACT, 23, 1),
    ),
)
def test_enabled_provider_caps_resolve_once(
    tmp_path: Path,
    provider: ProviderKey,
    configured: int,
    effective: int,
) -> None:
    config = _write_config(tmp_path, provider=provider, max_hits=configured)

    entry = _entries(_resolve(tmp_path, config).plan)[provider]

    assert entry.enabled is True
    assert entry.configured_max_hits == configured
    assert entry.effective_max_hits == effective
    assert entry.database_resources


@pytest.mark.parametrize(
    "provider",
    (
        ProviderKey.PDB_SEQUENCE,
        ProviderKey.FOLDSEEK_PROSTT5_PDB,
        ProviderKey.AFDB_EXACT,
    ),
)
def test_disabled_provider_has_zero_effective_cap_and_no_resource_binding(
    tmp_path: Path, provider: ProviderKey
) -> None:
    config = _write_config(tmp_path, provider=provider, enabled=False, max_hits=77)

    entry = _entries(_resolve(tmp_path, config).plan)[provider]

    assert entry.enabled is False
    assert entry.configured_max_hits == 77
    assert entry.effective_max_hits == 0
    assert entry.database_resources == ()
    assert entry.disabled_reason == "disabled_by_pipeline_config"


def test_enabled_provider_rejects_zero_cap_before_output(tmp_path: Path) -> None:
    config = _write_config(
        tmp_path, provider=ProviderKey.PDB_SEQUENCE, enabled=True, max_hits=0
    )
    output = tmp_path / "rejected"

    with pytest.raises(ProviderPlanError, match="requires max_hits"):
        resolve_provider_plan(ProviderPlanRequest(config, DATABASE, output))

    assert not output.exists()


def test_provider_rejects_cap_above_supported_bound(tmp_path: Path) -> None:
    config = _write_config(
        tmp_path, provider=ProviderKey.FOLDSEEK_PROSTT5_PDB, max_hits=1001
    )
    output = tmp_path / "over-cap"

    with pytest.raises(ProviderPlanError, match="must not exceed 1000"):
        resolve_provider_plan(ProviderPlanRequest(config, DATABASE, output))

    assert not output.exists()


def test_enabled_provider_requires_ready_database_resource(tmp_path: Path) -> None:
    database_document = json.loads(DATABASE.read_text(encoding="utf-8"))
    database_document["resources"] = [
        resource
        for resource in database_document["resources"]
        if resource["name"] != "pdb_sequences"
    ]
    database = tmp_path / "missing-resource.json"
    database.write_text(
        json.dumps(database_document, sort_keys=True) + "\n", encoding="utf-8"
    )
    output = tmp_path / "missing resource plan"

    with pytest.raises(ProviderPlanError, match="requires database resource"):
        resolve_provider_plan(ProviderPlanRequest(CONFIG, database, output))

    assert not output.exists()


def test_enabled_esm_atlas_fails_closed_before_output(tmp_path: Path) -> None:
    config = _write_config(tmp_path, provider=ProviderKey.ESM_ATLAS, enabled=True)
    output = tmp_path / "esm must not produce output"

    with pytest.raises(ProviderPlanError, match=r"no adapter.*compute-network"):
        resolve_provider_plan(ProviderPlanRequest(config, DATABASE, output))

    assert not output.exists()


def test_provider_plan_is_byte_deterministic(tmp_path: Path) -> None:
    first = _resolve(tmp_path, name="first")
    second = _resolve(tmp_path, name="second")

    first_files = {
        path.relative_to(first.plan_json.parent): path.read_bytes()
        for path in first.plan_json.parent.rglob("*.json")
    }
    second_files = {
        path.relative_to(second.plan_json.parent): path.read_bytes()
        for path in second.plan_json.parent.rglob("*.json")
    }
    assert first.plan.plan_id == second.plan.plan_id
    assert first_files == second_files


def test_provider_entry_and_plan_reject_tampering(tmp_path: Path) -> None:
    output = _resolve(tmp_path)
    entry_document = json.loads(
        output.entry_json[ProviderKey.PDB_SEQUENCE].read_text(encoding="utf-8")
    )
    entry_document["effective_max_hits"] = 1
    with pytest.raises(ValueError, match="entry ID"):
        ProviderPlanEntry.model_validate(entry_document)

    plan_document = json.loads(output.plan_json.read_text(encoding="utf-8"))
    plan_document["entry_sha256"][ProviderKey.PDB_SEQUENCE.value] = "0" * 64
    with pytest.raises(ValueError, match="checksum inventory"):
        ProviderExecutionPlan.model_validate(plan_document)


def test_provider_plan_cli_writes_canonical_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "cli plan"

    assert (
        main(
            [
                "structure-search",
                "resolve-provider-plan",
                "--config",
                str(CONFIG),
                "--database-manifest",
                str(DATABASE),
                "--outdir",
                str(output),
            ]
        )
        == 0
    )

    assert "providerplan_" in capsys.readouterr().out
    assert (output / "provider_plan.json").is_file()
    assert len(tuple((output / "entries").glob("*.json"))) == 4


def test_enabled_provider_route_authenticates_plan_entry_and_database(
    tmp_path: Path,
) -> None:
    output = _resolve(tmp_path)

    route = load_enabled_provider_route(
        provider_plan_json=output.plan_json,
        provider_entry_json=output.entry_json[ProviderKey.PDB_SEQUENCE],
        database_manifest=DATABASE,
        expected_provider=ProviderKey.PDB_SEQUENCE,
        expected_adapter_version="pdb-sequence-mmseqs-v4",
    )

    assert route.plan == output.plan
    assert route.entry.provider is ProviderKey.PDB_SEQUENCE
    assert route.entry.effective_max_hits == 3


def test_enabled_provider_route_rejects_disabled_entry(tmp_path: Path) -> None:
    output = _resolve(tmp_path)

    with pytest.raises(ProviderPlanError, match="route is disabled"):
        load_enabled_provider_route(
            provider_plan_json=output.plan_json,
            provider_entry_json=output.entry_json[ProviderKey.ESM_ATLAS],
            database_manifest=DATABASE,
            expected_provider=ProviderKey.ESM_ATLAS,
            expected_adapter_version="unsupported",
        )


def test_enabled_provider_route_rejects_entry_checksum_drift(tmp_path: Path) -> None:
    output = _resolve(tmp_path)
    entry = output.entry_json[ProviderKey.PDB_SEQUENCE]
    entry.write_text(f"{entry.read_text(encoding='utf-8')}\n", encoding="utf-8")

    with pytest.raises(ProviderPlanError, match="checksum differs"):
        load_enabled_provider_route(
            provider_plan_json=output.plan_json,
            provider_entry_json=entry,
            database_manifest=DATABASE,
            expected_provider=ProviderKey.PDB_SEQUENCE,
            expected_adapter_version="pdb-sequence-mmseqs-v4",
        )


def test_enabled_provider_route_rejects_database_manifest_drift(tmp_path: Path) -> None:
    output = _resolve(tmp_path)
    database = tmp_path / "database-drift.json"
    database.write_text(f"{DATABASE.read_text(encoding='utf-8')}\n", encoding="utf-8")

    with pytest.raises(ProviderPlanError, match="database manifest checksum"):
        load_enabled_provider_route(
            provider_plan_json=output.plan_json,
            provider_entry_json=output.entry_json[ProviderKey.PDB_SEQUENCE],
            database_manifest=database,
            expected_provider=ProviderKey.PDB_SEQUENCE,
            expected_adapter_version="pdb-sequence-mmseqs-v4",
        )


def test_enabled_provider_route_rejects_adapter_version_drift(tmp_path: Path) -> None:
    output = _resolve(tmp_path)

    with pytest.raises(ProviderPlanError, match="adapter version"):
        load_enabled_provider_route(
            provider_plan_json=output.plan_json,
            provider_entry_json=output.entry_json[ProviderKey.PDB_SEQUENCE],
            database_manifest=DATABASE,
            expected_provider=ProviderKey.PDB_SEQUENCE,
            expected_adapter_version="wrong-adapter",
        )
