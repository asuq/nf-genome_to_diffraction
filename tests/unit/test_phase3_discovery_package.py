"""Tests for the owned offline Phase III provider-discovery checkpoint."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.execution.unknown_screen import (
    publish_unknown_pass1_crystallographic_review_routes,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    CatalogueImportManifest,
    CatalogueInputRecord,
    CatalogueManifest,
    OutputArtifactRecord,
)
from genome_to_diffraction.schemas.v2 import PhaseIIIExecutionIdentity
from genome_to_diffraction.structure_search import (
    PhaseIIIProviderDiscoveryError,
    PhaseIIIProviderDiscoveryRequest,
    ProviderHitMergeRequest,
    ProviderPlanRequest,
    build_phase3_provider_discovery_package,
    merge_pdb_provider_hits,
    resolve_provider_plan,
    validate_phase3_provider_discovery_package,
)
from tests.support.unknown_pass1_fixture import (
    materialise_unknown_pass1_public_fixture,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
CONFIG = REPOSITORY / "examples/config.yaml"
CATALOGUES = REPOSITORY / "examples/catalogue_manifest.json"
DATABASE = STUBS / "provider_plan_database_manifest.json"


def _catalogue_bundle(root: Path, execution_identity: Path) -> Path:
    bundle = root / "catalogue"
    bundle.mkdir()
    for name in ("sequence_groups.jsonl", "source_records.jsonl"):
        shutil.copy2(STUBS / name, bundle / name)
    fasta = bundle / "exact_sequences.faa"
    fasta.write_text(
        ">seq_f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e\nACDE\n",
        encoding="ascii",
    )
    execution = PhaseIIIExecutionIdentity.model_validate_json(
        execution_identity.read_bytes()
    )
    catalogue_manifest = load_contract(CATALOGUES, "catalogue-manifest", progress=False)
    assert isinstance(catalogue_manifest, CatalogueManifest)
    outputs = tuple(
        OutputArtifactRecord(
            role=role,
            path=path.name,
            size_bytes=path.stat().st_size,
            sha256=sha256_file(path, progress=False),
        )
        for role, path in (
            ("exact_sequences", fasta),
            ("sequence_groups", bundle / "sequence_groups.jsonl"),
            ("source_records", bundle / "source_records.jsonl"),
        )
    )
    identity = {
        "catalogue_manifest_sha256": sha256_file(CATALOGUES, progress=False),
        "pipeline_config_sha256": sha256_file(CONFIG, progress=False),
        "outputs": [item.model_dump(mode="json") for item in outputs],
    }
    record = CatalogueImportManifest(
        schema_version="1.0",
        import_id=content_id("catimport_", identity),
        created_at="2026-01-01T00:00:00Z",
        software_version="unit-fixture",
        catalogue_ids=tuple(
            sorted({item.owner_id for item in execution.catalogue_artifacts})
        ),
        catalogue_manifest_sha256=identity["catalogue_manifest_sha256"],
        pipeline_config_sha256=identity["pipeline_config_sha256"],
        inputs=tuple(
            CatalogueInputRecord(
                catalogue_id=item.owner_id,
                role=item.role,
                path=f"fixture/{item.role}",
                sha256=item.sha256,
            )
            for item in execution.catalogue_artifacts
            if item.role
            in {
                "annotation_gbff",
                "annotation_gff",
                "genome_fasta",
                "proteome_faa",
                "protein_locus_map",
            }
        ),
        outputs=outputs,
        source_record_count=1,
        sequence_group_count=1,
        warning_count=0,
    )
    atomic_write_json(
        bundle / "catalogue_import_manifest.json",
        record.model_dump(mode="json"),
    )
    return bundle


def _request(root: Path) -> PhaseIIIProviderDiscoveryRequest:
    public_root = root / "public"
    public_root.mkdir()
    public = materialise_unknown_pass1_public_fixture(
        public_root,
        database_manifest_override=DATABASE,
    )
    crystals = root / "crystals.json"
    atomic_write_json(
        crystals,
        {
            "schema_version": "1.0",
            "crystals": [
                {
                    "crystal_id": item.crystal_id,
                    "mtz": str(item.mtz),
                    "catalogue_id": "example_archaeon_refseq",
                    "sds_page_mass_kda": [],
                    "allow_remote_sequence_submission": False,
                }
                for item in public.crystals
            ],
        },
    )
    review_routes = root / "review_routes"
    publish_unknown_pass1_crystallographic_review_routes(
        review_stage_index=public.review_stage_index,
        execution_identity=public.execution_identity,
        crystal_manifest=crystals,
        output_directory=review_routes,
    )
    provider_plan = root / "provider_plan"
    resolve_provider_plan(
        ProviderPlanRequest(
            pipeline_config=CONFIG,
            database_manifest=DATABASE,
            output_directory=provider_plan,
        )
    )
    pdb_search = root / "pdb_sequence_search"
    foldseek_search = root / "prostt5_foldseek_search"
    shutil.copytree(STUBS / "structure_search", pdb_search)
    shutil.copytree(STUBS / "prostt5_foldseek_search", foldseek_search)
    merged_hits = root / "pdb_provider_hits"
    merge_pdb_provider_hits(
        ProviderHitMergeRequest(
            pdb_sequence_hits_jsonl=pdb_search / "structural_hits.jsonl",
            foldseek_hits_jsonl=foldseek_search / "structural_hits.jsonl",
            output_directory=merged_hits,
        )
    )
    accession_map = root / "afdb_accession_map.tsv"
    accession_map.write_text(
        "source_record_id\tuniprot_accession\n",
        encoding="ascii",
    )
    return PhaseIIIProviderDiscoveryRequest(
        owned_run_id="gtd-unknown-discovery-20260825T000000Z-aaaaaaaaaaaa-bbbbbbbb",
        execution_identity=public.execution_identity,
        pipeline_config=CONFIG,
        database_manifest=DATABASE,
        crystallographic_review_routes=review_routes,
        catalogue_bundle=_catalogue_bundle(root, public.execution_identity),
        provider_plan_bundle=provider_plan,
        pdb_sequence_search=pdb_search,
        prostt5_foldseek_search=foldseek_search,
        pdb_provider_hits=merged_hits,
        afdb_accession_map=accession_map,
        output_directory=root / "package",
    )


def test_owned_provider_discovery_package_round_trips(tmp_path: Path) -> None:
    packaged = build_phase3_provider_discovery_package(_request(tmp_path))

    observed = validate_phase3_provider_discovery_package(packaged.package_directory)

    assert observed == packaged.manifest
    assert observed.sequence_group_count == 1
    assert observed.pdb_result_count == 1
    assert observed.foldseek_result_count == 1
    assert observed.network_acquisition_performed is False
    assert observed.coordinate_registration_performed is False
    copied_catalogue = load_contract(
        packaged.package_directory / "catalogue/catalogue_import_manifest.json",
        "catalogue-import-manifest",
        progress=False,
    )
    assert isinstance(copied_catalogue, CatalogueImportManifest)
    assert all(
        item.path == f"authority/{item.catalogue_id}/{item.role}"
        for item in copied_catalogue.inputs
    )


def test_incomplete_provider_query_inventory_fails(tmp_path: Path) -> None:
    request = _request(tmp_path)
    (request.pdb_sequence_search / "search_results.jsonl").write_text(
        "",
        encoding="utf-8",
    )

    with pytest.raises(PhaseIIIProviderDiscoveryError, match="results is empty"):
        build_phase3_provider_discovery_package(request)


def test_catalogue_input_must_match_execution_identity(tmp_path: Path) -> None:
    request = _request(tmp_path)
    manifest_path = request.catalogue_bundle / "catalogue_import_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["inputs"][0]["sha256"] = "f" * 64
    atomic_write_json(manifest_path, manifest)

    with pytest.raises(PhaseIIIProviderDiscoveryError, match="catalogue import"):
        build_phase3_provider_discovery_package(request)


def test_changed_packaged_file_fails_validation(tmp_path: Path) -> None:
    packaged = build_phase3_provider_discovery_package(_request(tmp_path))
    config = packaged.package_directory / "inputs/pipeline_config.yaml"
    config.write_bytes(config.read_bytes() + b"\n")

    with pytest.raises(PhaseIIIProviderDiscoveryError, match="inventory changed"):
        validate_phase3_provider_discovery_package(packaged.package_directory)


def test_symlinked_scientific_input_fails(tmp_path: Path) -> None:
    request = _request(tmp_path)
    linked = tmp_path / "linked_execution.json"
    linked.symlink_to(request.execution_identity)
    changed = replace(request, execution_identity=linked)

    with pytest.raises(PhaseIIIProviderDiscoveryError, match="must not be a symlink"):
        build_phase3_provider_discovery_package(changed)
