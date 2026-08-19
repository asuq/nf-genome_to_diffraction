"""Provider-plan binding for enabled structural-search adapters."""

from pathlib import Path

import pytest

from genome_to_diffraction.schemas.providers import ProviderKey
from genome_to_diffraction.status import InputContractError
from genome_to_diffraction.structure_search.afdb_exact import (
    AfdbExactRequest,
)
from genome_to_diffraction.structure_search.afdb_exact import (
    _bind_provider_route as bind_afdb_route,
)
from genome_to_diffraction.structure_search.pdb_sequence import (
    PdbSequenceSearchRequest,
)
from genome_to_diffraction.structure_search.pdb_sequence import (
    _bind_provider_route as bind_pdb_route,
)
from genome_to_diffraction.structure_search.prostt5_foldseek import (
    ProstT5FoldseekSearchRequest,
)
from genome_to_diffraction.structure_search.prostt5_foldseek import (
    _bind_provider_route as bind_foldseek_route,
)
from genome_to_diffraction.structure_search.provider_plan import (
    ProviderPlanError,
    ProviderPlanRequest,
    resolve_provider_plan,
)

REPOSITORY = Path(__file__).resolve().parents[2]
CONFIG = REPOSITORY / "examples/config.yaml"
DATABASE = REPOSITORY / "tests/fixtures/stubs/provider_plan_database_manifest.json"


def _plan(tmp_path: Path):
    return resolve_provider_plan(
        ProviderPlanRequest(CONFIG, DATABASE, tmp_path / "provider-plan")
    )


def test_pdb_adapter_resolves_hit_cap_from_authenticated_plan(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    request = PdbSequenceSearchRequest(
        sequence_groups_jsonl=tmp_path / "sequences.jsonl",
        database_manifest=DATABASE,
        output_directory=tmp_path / "output",
        provider_plan_json=plan.plan_json,
        provider_entry_json=plan.entry_json[ProviderKey.PDB_SEQUENCE],
        maximum_hits_per_query=999,
    )

    bound = bind_pdb_route(request)

    assert bound.maximum_hits_per_query == 3
    assert bound.provider_plan_json == plan.plan_json


def test_foldseek_adapter_resolves_hit_cap_from_authenticated_plan(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    request = ProstT5FoldseekSearchRequest(
        sequence_groups_jsonl=tmp_path / "sequences.jsonl",
        database_manifest=DATABASE,
        output_directory=tmp_path / "output",
        provider_plan_json=plan.plan_json,
        provider_entry_json=plan.entry_json[ProviderKey.FOLDSEEK_PROSTT5_PDB],
        maximum_hits_per_query=999,
    )

    assert bind_foldseek_route(request).maximum_hits_per_query == 3


def test_afdb_adapter_authenticates_enabled_route(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    request = AfdbExactRequest(
        sequence_groups_jsonl=tmp_path / "sequences.jsonl",
        source_records_jsonl=tmp_path / "sources.jsonl",
        database_manifest=DATABASE,
        output_directory=tmp_path / "output",
        provider_plan_json=plan.plan_json,
        provider_entry_json=plan.entry_json[ProviderKey.AFDB_EXACT],
    )

    assert bind_afdb_route(request) == request


def test_adapters_reject_incomplete_provider_routes() -> None:
    calls = (
        lambda: bind_pdb_route(
            PdbSequenceSearchRequest(
                Path("sequences.jsonl"),
                DATABASE,
                Path("output"),
                provider_plan_json=Path("plan.json"),
            )
        ),
        lambda: bind_foldseek_route(
            ProstT5FoldseekSearchRequest(
                Path("sequences.jsonl"),
                DATABASE,
                Path("output"),
                provider_entry_json=Path("entry.json"),
            )
        ),
        lambda: bind_afdb_route(
            AfdbExactRequest(
                Path("sequences.jsonl"),
                Path("sources.jsonl"),
                DATABASE,
                Path("output"),
                provider_plan_json=Path("plan.json"),
            )
        ),
    )
    for call in calls:
        with pytest.raises(InputContractError, match="requires both provider plan"):
            call()


def test_adapter_rejects_entry_for_another_provider(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    request = PdbSequenceSearchRequest(
        sequence_groups_jsonl=tmp_path / "sequences.jsonl",
        database_manifest=DATABASE,
        output_directory=tmp_path / "output",
        provider_plan_json=plan.plan_json,
        provider_entry_json=plan.entry_json[ProviderKey.FOLDSEEK_PROSTT5_PDB],
    )

    with pytest.raises(ProviderPlanError, match="expected pdb_sequence"):
        bind_pdb_route(request)
