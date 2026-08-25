"""Provider-plan binding for enabled structural-search adapters."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks import m6_nextflow
from genome_to_diffraction.benchmarks.m6_execution import load_m6_execution_policy
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.cli import main
from genome_to_diffraction.ids import canonical_digest
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
    FrozenM6RawProviderAuthorisation,
    ProviderPlanError,
    ProviderPlanRequest,
    frozen_m6_raw_authorisation_payload,
    load_frozen_m6_raw_provider_route,
    resolve_provider_plan,
)

REPOSITORY = Path(__file__).resolve().parents[2]
CONFIG = REPOSITORY / "examples/config.yaml"
DATABASE = REPOSITORY / "tests/fixtures/stubs/provider_plan_database_manifest.json"
M6_POLICY = REPOSITORY / "benchmarks/m6/execution-nextflow-marmic-v1.yaml"
SOFTWARE_LOCK = REPOSITORY / "pixi.lock"


def _m6_authorisation(
    tmp_path: Path, provider: ProviderKey
) -> FrozenM6RawProviderAuthorisation:
    policy = load_m6_execution_policy(M6_POLICY)
    is_pdb = provider is ProviderKey.PDB_SEQUENCE
    threads = (
        policy.search_batching.mmseqs2.cpus
        if is_pdb
        else policy.search_batching.foldseek.cpus
    )
    parameters: dict[str, int | float | bool] = {
        "threads": threads,
        "maximum_hits_per_query": 25,
        "maximum_evalue": 1.0e-5 if is_pdb else 1.0e-3,
        "minimum_query_coverage": 0.5,
        "maximum_query_length": 10_000,
    }
    task_adapter = m6_nextflow._PDB_ADAPTER
    if not is_pdb:
        parameters.update({"maximum_queries": 0, "retain_unmapped_targets": True})
        task_adapter = m6_nextflow._FOLDSEEK_ADAPTER
    database_sha256 = sha256_file(DATABASE)
    policy_sha256 = sha256_file(M6_POLICY)
    lock_sha256 = sha256_file(SOFTWARE_LOCK)
    batch_id = "b" * 64
    task = m6_nextflow.M6SearchBatchTask(
        schema_version="1.0",
        batch_id=batch_id,
        provider="pdb_sequence" if is_pdb else "prostt5_foldseek",
        sequence_count=1,
        residue_count=4,
        threads=threads,
        database_manifest_sha256=database_sha256,
        software_lock_sha256=lock_sha256,
        execution_policy_sha256=policy_sha256,
        search_cache_key=canonical_digest(
            {
                "adapter_version": task_adapter,
                "batch_id": batch_id,
                "database_manifest_sha256": database_sha256,
                "software_lock_sha256": lock_sha256,
                "execution_policy_sha256": policy_sha256,
                "parameters": parameters,
            }
        ),
    )
    task_path = tmp_path / f"{provider.value}-task.json"
    task_path.write_text(task.model_dump_json(), encoding="utf-8")
    return FrozenM6RawProviderAuthorisation(
        batch_task_json=task_path,
        execution_policy=M6_POLICY,
        software_lock=SOFTWARE_LOCK,
    )


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


def test_adapters_reject_absent_provider_routes_before_execution() -> None:
    calls = (
        lambda: bind_pdb_route(
            PdbSequenceSearchRequest(
                Path("sequences.jsonl"),
                DATABASE,
                Path("output"),
            )
        ),
        lambda: bind_foldseek_route(
            ProstT5FoldseekSearchRequest(
                Path("sequences.jsonl"),
                DATABASE,
                Path("output"),
            )
        ),
        lambda: bind_afdb_route(
            AfdbExactRequest(
                Path("sequences.jsonl"),
                Path("sources.jsonl"),
                DATABASE,
                Path("output"),
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


@pytest.mark.parametrize(
    ("provider", "adapter_version"),
    (
        (ProviderKey.PDB_SEQUENCE, "pdb-sequence-mmseqs-v4"),
        (ProviderKey.FOLDSEEK_PROSTT5_PDB, "prostt5-foldseek-pdb-v6"),
    ),
)
def test_frozen_m6_provider_authorisation_preserves_blind_discovery_envelope(
    tmp_path: Path,
    provider: ProviderKey,
    adapter_version: str,
) -> None:
    authorisation = _m6_authorisation(tmp_path, provider)
    route = load_frozen_m6_raw_provider_route(
        authorisation=authorisation,
        database_manifest=DATABASE,
        expected_provider=provider,
        expected_adapter_version=adapter_version,
        threads=32,
        maximum_hits_per_query=25,
    )

    assert route.provider is provider
    assert route.site_id == "marmic"
    assert route.raw_hit_cap == 25
    assert route.accepted_hit_cap == 3
    payload = frozen_m6_raw_authorisation_payload(route)
    assert payload["authorisation_scope"] == "m6_frozen_raw_discovery"
    assert payload["provider_plan_sha256"] is None
    assert payload["provider_entry_sha256"] is None
    assert payload["batch_task_sha256"] == sha256_file(authorisation.batch_task_json)
    if provider is ProviderKey.PDB_SEQUENCE:
        bound = bind_pdb_route(
            PdbSequenceSearchRequest(
                tmp_path / "groups.jsonl",
                DATABASE,
                tmp_path / "output",
                frozen_m6_raw_authorisation=authorisation,
                threads=32,
                maximum_hits_per_query=25,
            )
        )
    else:
        bound = bind_foldseek_route(
            ProstT5FoldseekSearchRequest(
                tmp_path / "groups.jsonl",
                DATABASE,
                tmp_path / "output",
                frozen_m6_raw_authorisation=authorisation,
                threads=32,
                maximum_hits_per_query=25,
            )
        )
    assert bound.maximum_hits_per_query == 25


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("provider", "provider does not match"),
        ("threads", "thread allocation"),
        ("task_threads", "thread allocation"),
        ("raw_cap", "discovery hit cap"),
        ("database", "provenance changed"),
        ("policy", "provenance changed"),
        ("lock", "provenance changed"),
        ("cache_key", "search-cache identity"),
        ("adapter", "adapter version"),
    ),
)
def test_frozen_m6_provider_rejects_unowned_or_changed_task_evidence(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    authorisation = _m6_authorisation(tmp_path, ProviderKey.PDB_SEQUENCE)
    task = json.loads(authorisation.batch_task_json.read_text(encoding="utf-8"))
    threads = 32
    maximum_hits = 25
    adapter = "pdb-sequence-mmseqs-v4"
    database = DATABASE
    if mutation == "provider":
        task["provider"] = "prostt5_foldseek"
    elif mutation == "threads":
        threads = 31
    elif mutation == "task_threads":
        task["threads"] = 31
    elif mutation == "raw_cap":
        maximum_hits = 3
    elif mutation == "database":
        database = tmp_path / "changed-database.json"
        database.write_text(f"{DATABASE.read_text(encoding='utf-8')}\n")
    elif mutation == "policy":
        changed = tmp_path / "changed-policy.yaml"
        changed.write_text(f"{M6_POLICY.read_text(encoding='utf-8')}\n")
        authorisation = replace(authorisation, execution_policy=changed)
    elif mutation == "lock":
        changed = tmp_path / "changed-lock.lock"
        changed.write_text("not the frozen software lock\n", encoding="utf-8")
        authorisation = replace(authorisation, software_lock=changed)
    elif mutation == "cache_key":
        task["search_cache_key"] = "0" * 64
    elif mutation == "adapter":
        adapter = "pdb-sequence-mmseqs-v3"
    authorisation.batch_task_json.write_text(json.dumps(task), encoding="utf-8")

    with pytest.raises(ProviderPlanError, match=message):
        load_frozen_m6_raw_provider_route(
            authorisation=authorisation,
            database_manifest=database,
            expected_provider=ProviderKey.PDB_SEQUENCE,
            expected_adapter_version=adapter,
            threads=threads,
            maximum_hits_per_query=maximum_hits,
        )


@pytest.mark.parametrize(
    "provider",
    (ProviderKey.PDB_SEQUENCE, ProviderKey.FOLDSEEK_PROSTT5_PDB),
)
def test_provider_adapters_reject_mixed_application_and_m6_authorisation(
    tmp_path: Path,
    provider: ProviderKey,
) -> None:
    plan = _plan(tmp_path)
    authorisation = _m6_authorisation(tmp_path, provider)
    with pytest.raises(InputContractError, match="cannot mix"):
        if provider is ProviderKey.PDB_SEQUENCE:
            bind_pdb_route(
                PdbSequenceSearchRequest(
                    tmp_path / "groups.jsonl",
                    DATABASE,
                    tmp_path / "output",
                    provider_plan_json=plan.plan_json,
                    provider_entry_json=plan.entry_json[provider],
                    frozen_m6_raw_authorisation=authorisation,
                    threads=32,
                    maximum_hits_per_query=25,
                )
            )
        else:
            bind_foldseek_route(
                ProstT5FoldseekSearchRequest(
                    tmp_path / "groups.jsonl",
                    DATABASE,
                    tmp_path / "output",
                    provider_plan_json=plan.plan_json,
                    provider_entry_json=plan.entry_json[provider],
                    frozen_m6_raw_authorisation=authorisation,
                    threads=32,
                    maximum_hits_per_query=25,
                )
            )


@pytest.mark.parametrize("action", ("pdb-sequence", "prostt5-foldseek", "afdb-exact"))
def test_public_provider_commands_require_reviewed_plan_and_entry(
    capsys: pytest.CaptureFixture[str], action: str
) -> None:
    arguments = [
        "structure-search",
        action,
        "--sequence-groups",
        "groups.jsonl",
        "--database-manifest",
        "database.json",
        "--outdir",
        "output",
    ]
    if action == "afdb-exact":
        arguments.extend(("--source-records", "sources.jsonl"))

    with pytest.raises(SystemExit) as error:
        main(arguments)

    assert error.value.code == 2
    message = capsys.readouterr().err
    assert "--provider-plan" in message
    assert "--provider-entry" in message
