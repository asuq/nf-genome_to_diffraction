"""Materialise one deterministic enabled-no-hit bundle for a Nextflow stub.

This test helper never runs provider software. The non-stub process is a
separate fail-closed boundary; this helper only supplies typed scheduling
evidence for the dedicated provider-empty graph test.
"""

import argparse
from pathlib import Path

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_digest, canonical_json_text, content_id
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import DatabaseManifest
from genome_to_diffraction.schemas.providers import (
    ProviderExecutionClass,
    ProviderExecutionPlan,
    ProviderKey,
    ProviderPlanEntry,
)
from genome_to_diffraction.schemas.results import (
    SearchScientificStatus,
    SequenceGroupRecord,
    StructuralSearchResult,
)
from genome_to_diffraction.status import ExecutionStatus
from genome_to_diffraction.structure_search.provider_plan import (
    load_enabled_provider_route,
)

_ADAPTER_VERSION = "provider-no-hit-stub-v1"


def materialise_enabled_no_hit(
    *,
    provider_plan_json: Path,
    provider_entry_json: Path,
    database_manifest: Path,
    sequence_groups_jsonl: Path,
    output_directory: Path,
) -> Path:
    """Write a typed local no-hit bundle bound to the exact PDB plan entry."""

    route = load_enabled_provider_route(
        provider_plan_json=provider_plan_json,
        provider_entry_json=provider_entry_json,
        database_manifest=database_manifest,
        expected_provider=ProviderKey.PDB_SEQUENCE,
        expected_adapter_version="pdb-sequence-mmseqs-v4",
    )
    if route.entry.execution_class is not ProviderExecutionClass.LOCAL_COMPUTE:
        raise ValueError("stub refuses a non-local provider entry")
    plan = load_contract(provider_plan_json, "provider-execution-plan", progress=False)
    database = load_contract(database_manifest, "database-manifest", progress=False)
    if not isinstance(plan, ProviderExecutionPlan) or not isinstance(
        database, DatabaseManifest
    ):
        raise AssertionError("test helper loaded unexpected contracts")
    entry = ProviderPlanEntry.model_validate_json(provider_entry_json.read_bytes())
    groups = tuple(
        SequenceGroupRecord.model_validate_json(line)
        for line in sequence_groups_jsonl.read_text(encoding="utf-8").splitlines()
    )
    if not groups:
        raise ValueError("stub sequence group input is empty")
    resource = next(
        item
        for item in entry.database_resources
        if item.resource_name == "pdb_sequences"
    )
    output = output_directory.absolute()
    if output.exists():
        raise ValueError(f"stub output exists: {output}")
    raw = output / "raw"
    raw.mkdir(parents=True)
    raw_result = raw / "mmseqs-results.tsv"
    command_log = raw / "mmseqs.log"
    atomic_write_text(raw_result, "")
    atomic_write_text(command_log, "stub_only_no_provider_execution\n")
    results: list[StructuralSearchResult] = []
    for group in sorted(groups, key=lambda item: item.sequence_group_id):
        identity = {
            "adapter_version": _ADAPTER_VERSION,
            "provider_plan_id": plan.plan_id,
            "provider_entry_id": entry.entry_id,
            "sequence_group_id": group.sequence_group_id,
            "sequence_sha256": group.sha256,
        }
        results.append(
            StructuralSearchResult(
                schema_version="1.0",
                search_id=content_id("srch_", identity),
                sequence_group_id=group.sequence_group_id,
                provider=entry.result_provider,
                database_id=resource.database_id,
                tool="provider-empty-graph-stub",
                tool_version="1",
                adapter_version=_ADAPTER_VERSION,
                cache_key=canonical_digest(identity),
                execution_status=ExecutionStatus.COMPLETED_NO_HIT,
                scientific_status=SearchScientificStatus.NO_HIT,
                hit_count=0,
                hits=(),
                raw_result_pointer="raw/mmseqs-results.tsv",
                raw_result_sha256=sha256_file(raw_result, progress=False),
                command_log_pointer="raw/mmseqs.log",
                command_log_sha256=sha256_file(command_log, progress=False),
                warnings=("stub_only_no_provider_execution",),
            )
        )
    results_path = output / "search_results.jsonl"
    hits_path = output / "structural_hits.jsonl"
    coordinates_path = output / "coordinate_sources.jsonl"
    atomic_write_text(
        results_path,
        "".join(f"{canonical_json_text(item)}\n" for item in results),
    )
    atomic_write_text(hits_path, "")
    atomic_write_text(coordinates_path, "")
    manifest_path = output / "search_manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "provider": entry.provider.value,
            "provider_entry_id": entry.entry_id,
            "provider_entry_sha256": plan.entry_sha256[entry.provider],
            "provider_plan_id": plan.plan_id,
            "provider_plan_sha256": sha256_file(provider_plan_json, progress=False),
            "sequence_groups_sha256": sha256_file(
                sequence_groups_jsonl, progress=False
            ),
            "query_count": len(results),
            "hit_count": 0,
            "stub_only": True,
            "network_request_count": 0,
            "outputs": {
                "search_results": {
                    "path": results_path.name,
                    "sha256": sha256_file(results_path, progress=False),
                },
                "structural_hits": {
                    "path": hits_path.name,
                    "sha256": sha256_file(hits_path, progress=False),
                },
                "coordinate_sources": {
                    "path": coordinates_path.name,
                    "sha256": sha256_file(coordinates_path, progress=False),
                },
            },
        },
    )
    return manifest_path


def main() -> int:
    """Run the fixed test-only no-hit materialiser."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-plan", type=Path, required=True)
    parser.add_argument("--provider-entry", type=Path, required=True)
    parser.add_argument("--database-manifest", type=Path, required=True)
    parser.add_argument("--sequence-groups", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    arguments = parser.parse_args()
    materialise_enabled_no_hit(
        provider_plan_json=arguments.provider_plan,
        provider_entry_json=arguments.provider_entry,
        database_manifest=arguments.database_manifest,
        sequence_groups_jsonl=arguments.sequence_groups,
        output_directory=arguments.outdir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
