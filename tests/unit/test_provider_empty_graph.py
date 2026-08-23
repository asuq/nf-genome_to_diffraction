"""Focused tests for the fixed plan-driven provider empty graph."""

from pathlib import Path

import pytest

from genome_to_diffraction.execution.provider_empty_graph import (
    ProviderEmptyGraphError,
    ProviderEmptyGraphRequest,
    ProviderEmptyOutcome,
    complete_provider_empty_graph,
)
from genome_to_diffraction.schemas.providers import ProviderKey
from genome_to_diffraction.schemas.v2.composition import ModelUnavailableReason
from genome_to_diffraction.structure_search.provider_empty import (
    DisabledProviderBundleRequest,
    emit_disabled_provider_bundle,
)
from genome_to_diffraction.structure_search.provider_plan import (
    ProviderPlanRequest,
    resolve_provider_plan,
)
from tests.scripts.materialise_provider_no_hit import materialise_enabled_no_hit

REPOSITORY = Path(__file__).resolve().parents[2]
CONFIG = REPOSITORY / "tests/fixtures/stubs/provider_empty_graph/config.yaml"
DATABASE = REPOSITORY / "tests/fixtures/stubs/provider_plan_database_manifest.json"
SEQUENCES = REPOSITORY / "tests/fixtures/stubs/sequence_groups.jsonl"


def _branches(tmp_path: Path):
    plan = resolve_provider_plan(
        ProviderPlanRequest(CONFIG, DATABASE, tmp_path / "provider_plan")
    )
    bundles: list[Path] = []
    pdb = tmp_path / "pdb_sequence_search"
    materialise_enabled_no_hit(
        provider_plan_json=plan.plan_json,
        provider_entry_json=plan.entry_json[ProviderKey.PDB_SEQUENCE],
        database_manifest=DATABASE,
        sequence_groups_jsonl=SEQUENCES,
        output_directory=pdb,
    )
    bundles.append(pdb)
    for provider, name in (
        (ProviderKey.AFDB_EXACT, "afdb_exact_search"),
        (ProviderKey.ESM_ATLAS, "esm_atlas_search"),
        (ProviderKey.FOLDSEEK_PROSTT5_PDB, "prostt5_foldseek_search"),
    ):
        output = tmp_path / name
        emit_disabled_provider_bundle(
            DisabledProviderBundleRequest(
                provider_entry_json=plan.entry_json[provider],
                sequence_groups_jsonl=SEQUENCES,
                output_directory=output,
            )
        )
        bundles.append(output)
    return plan, tuple(bundles)


def _request(
    tmp_path: Path,
    *,
    config: Path = CONFIG,
    bundles: tuple[Path, ...] | None = None,
):
    plan, complete_bundles = _branches(tmp_path / "inputs")
    return ProviderEmptyGraphRequest(
        pipeline_config=config,
        provider_plan_json=plan.plan_json,
        sequence_groups_jsonl=SEQUENCES,
        provider_bundle_directories=(complete_bundles if bundles is None else bundles),
        output_directory=tmp_path / "completion",
    ), complete_bundles


def test_all_empty_branches_complete_with_content_addressed_no_model_registry(
    tmp_path: Path,
) -> None:
    request, _ = _request(tmp_path)
    output = complete_provider_empty_graph(request)

    assert output.completion.terminal_status == "completed_no_model"
    assert output.completion.network_request_count == 0
    assert [item.outcome for item in output.completion.branches] == [
        ProviderEmptyOutcome.DISABLED,
        ProviderEmptyOutcome.PROVIDER_UNAVAILABLE,
        ProviderEmptyOutcome.DISABLED,
        ProviderEmptyOutcome.ENABLED_NO_HIT,
    ]
    assert output.all_model_registry.model_count == 0
    assert output.all_model_registry.unavailable_sequence_group_count == 1
    assert {
        item.unavailable_reason for item in output.all_model_registry.sequence_groups
    } == {ModelUnavailableReason.NO_ELIGIBLE_MODEL}


def test_completion_is_byte_deterministic(tmp_path: Path) -> None:
    request, bundles = _request(tmp_path / "first")
    first = complete_provider_empty_graph(request)
    second = complete_provider_empty_graph(
        ProviderEmptyGraphRequest(
            pipeline_config=CONFIG,
            provider_plan_json=request.provider_plan_json,
            sequence_groups_jsonl=SEQUENCES,
            provider_bundle_directories=bundles,
            output_directory=tmp_path / "second",
        )
    )

    assert first.completion_json.read_bytes() == second.completion_json.read_bytes()
    assert (
        first.all_model_registry_json.read_bytes()
        == second.all_model_registry_json.read_bytes()
    )


def test_plan_and_config_mismatch_fails_before_output(tmp_path: Path) -> None:
    request, _ = _request(tmp_path, config=REPOSITORY / "examples/config.yaml")

    with pytest.raises(ProviderEmptyGraphError, match="config differs"):
        complete_provider_empty_graph(request)

    assert not request.output_directory.exists()


def test_missing_branch_fails_before_output(tmp_path: Path) -> None:
    request, bundles = _request(tmp_path)
    request = ProviderEmptyGraphRequest(
        request.pipeline_config,
        request.provider_plan_json,
        request.sequence_groups_jsonl,
        bundles[:-1],
        request.output_directory,
    )

    with pytest.raises(ProviderEmptyGraphError, match="requires four"):
        complete_provider_empty_graph(request)

    assert not request.output_directory.exists()


def test_duplicate_branch_fails_before_output(tmp_path: Path) -> None:
    request, bundles = _request(tmp_path)
    request = ProviderEmptyGraphRequest(
        request.pipeline_config,
        request.provider_plan_json,
        request.sequence_groups_jsonl,
        (*bundles[:-1], bundles[0]),
        request.output_directory,
    )

    with pytest.raises(ProviderEmptyGraphError, match="missing or duplicate"):
        complete_provider_empty_graph(request)

    assert not request.output_directory.exists()
