"""Tests for exact-accession AlphaFold DB retrieval and caching."""

import hashlib
import io
import json
import urllib.error
from email.message import Message
from pathlib import Path
from typing import TypedDict, cast

import gemmi
import pytest

from genome_to_diffraction.databases.cache import initialise_coordinate_cache
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import PipelineConfig
from genome_to_diffraction.schemas.providers import ProviderKey
from genome_to_diffraction.schemas.results import SequenceGroupRecord
from genome_to_diffraction.status import (
    ExecutionStatus,
    InfrastructureError,
    ResultParseError,
    TransientInfrastructureError,
)
from genome_to_diffraction.structure_search import AfdbExactRequest, search_afdb_exact
from genome_to_diffraction.structure_search import afdb_exact as afdb_module
from genome_to_diffraction.structure_search.provider_plan import (
    ProviderPlanRequest,
    resolve_provider_plan,
)

REPOSITORY = Path(__file__).resolve().parents[2]


class _ProviderRoute(TypedDict):
    provider_plan_json: Path
    provider_entry_json: Path


def _provider_route(tmp_path: Path, database_manifest: Path) -> _ProviderRoute:
    config = load_contract(
        REPOSITORY / "examples/config.yaml", "pipeline-config", progress=False
    )
    assert isinstance(config, PipelineConfig)
    document = config.model_dump(mode="json")
    providers = cast(dict[str, object], document["providers"])
    for key, value in providers.items():
        cast(dict[str, object], value)["enabled"] = key == ProviderKey.AFDB_EXACT.value
    config_path = tmp_path / "afdb-provider-config.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    output = resolve_provider_plan(
        ProviderPlanRequest(
            pipeline_config=config_path,
            database_manifest=database_manifest,
            output_directory=tmp_path / "afdb-provider-plan",
        )
    )
    return {
        "provider_plan_json": output.plan_json,
        "provider_entry_json": output.entry_json[ProviderKey.AFDB_EXACT],
    }


@pytest.mark.parametrize(
    ("http_status", "expected_error"),
    (
        (503, TransientInfrastructureError),
        (429, TransientInfrastructureError),
        (403, InfrastructureError),
    ),
)
def test_afdb_only_marks_temporary_http_failures_retryable(
    monkeypatch: pytest.MonkeyPatch,
    http_status: int,
    expected_error: type[InfrastructureError],
) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise urllib.error.HTTPError(
            "https://alphafold.ebi.ac.uk/test",
            http_status,
            "test failure",
            Message(),
            io.BytesIO(b""),
        )

    monkeypatch.setattr(afdb_module.urllib.request, "urlopen", fail)

    with pytest.raises(expected_error) as captured:
        afdb_module._http_get(
            "https://alphafold.ebi.ac.uk/test",
            accept="application/json",
            timeout_seconds=1,
            retry_count=1,
            maximum_bytes=1024,
        )
    assert type(captured.value) is expected_error


def _sequence_group(sequence: str) -> SequenceGroupRecord:
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=400.0,
        mass_method="test mass",
        residue_policy="test policy",
        source_record_count=1,
    )


def _mmcif(sequence: str) -> bytes:
    residue_names = {
        "A": "ALA",
        "C": "CYS",
        "D": "ASP",
        "E": "GLU",
        "F": "PHE",
        "G": "GLY",
        "H": "HIS",
        "I": "ILE",
    }
    atoms = "".join(
        f"ATOM  {index:5d}  CA  {residue_names[residue]} A{index:4d}    "
        f"{float(index):8.3f}{0.0:8.3f}{0.0:8.3f}  1.00 90.00           C\n"
        for index, residue in enumerate(sequence, start=1)
    )
    structure = gemmi.read_pdb_string(f"{atoms}END\n")
    structure.name = "afdb-test"
    structure.setup_entities()
    return str(structure.make_mmcif_document().as_string()).encode("ascii")


def _write_inputs(
    tmp_path: Path, *, protein_id: str, sequence: str = "ACDE"
) -> tuple[Path, Path, Path, SequenceGroupRecord]:
    group = _sequence_group(sequence)
    input_root = tmp_path / "input with spaces"
    input_root.mkdir()
    sequence_path = input_root / "sequence groups.jsonl"
    sequence_path.write_text(f"{canonical_json_text(group)}\n", encoding="utf-8")
    source_path = input_root / "source records.jsonl"
    source_path.write_text(
        canonical_json_text(
            {
                "schema_version": "1.0",
                "source_record_id": "source_test",
                "catalogue_id": "catalogue_test",
                "original_protein_id": protein_id,
                "original_header": protein_id,
                "sequence_group_id": group.sequence_group_id,
                "source_annotation_provider": "test",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cache_root = tmp_path / "coordinate cache with spaces"
    layout_digest, file_count, total_bytes = initialise_coordinate_cache(
        cache_root, progress=False
    )
    manifest_path = input_root / "database manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "manifest_id": "dbm_afdb_test",
                "created_at": "2026-08-10T00:00:00Z",
                "resources": [
                    {
                        "database_id": "db_coordinate_cache_test",
                        "name": "coordinate_cache",
                        "source": "test cache",
                        "release_or_snapshot": "layout-1.0",
                        "root_path": str(cache_root),
                        "prepared_with": {
                            "tool": "genome-to-diffraction",
                            "version": "0.1.0",
                        },
                        "parameters": {},
                        "prepared_at": "2026-08-10T00:00:00Z",
                        "file_count": file_count,
                        "total_bytes": total_bytes,
                        "manifest_sha256": layout_digest,
                        "smoke_test_status": "passed",
                        "status": "ready",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return sequence_path, source_path, manifest_path, group


def _metadata(sequence: str, *, cif_url: str) -> bytes:
    return json.dumps(
        [
            {
                "modelEntityId": "AF-P69905-F1",
                "uniprotAccession": "P69905",
                "sequence": sequence,
                "sequenceStart": 1,
                "sequenceEnd": len(sequence),
                "latestVersion": 6,
                "cifUrl": cif_url,
                "globalMetricValue": 98.06,
                "providerId": "GDM",
                "entityType": "protein",
                "isComplex": False,
                "isUniProtReviewed": True,
                "isUniProtReferenceProteome": True,
            }
        ]
    ).encode("utf-8")


def test_afdb_exact_verifies_api_and_coordinate_sequence_and_caches_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sequence_path, source_path, manifest_path, group = _write_inputs(
        tmp_path, protein_id="WP_012345678.1"
    )
    accession_map = tmp_path / "input with spaces" / "AFDB accession map.tsv"
    accession_map.write_text(
        "source_record_id\tuniprot_accession\nsource_test\tP69905\n",
        encoding="utf-8",
    )
    cif_url = "https://alphafold.ebi.ac.uk/files/AF-P69905-F1-model_v6.cif"
    requests: list[str] = []

    def fake_http_get(url: str, **_: object) -> afdb_module._HttpResponse:
        requests.append(url)
        body = _mmcif("ACDE") if url == cif_url else _metadata("ACDE", cif_url=cif_url)
        return afdb_module._HttpResponse(
            requested_url=url,
            url=url,
            status=200,
            headers={"content-type": "chemical/x-mmcif"},
            body=body,
        )

    monkeypatch.setattr(afdb_module, "_http_get", fake_http_get)
    output = search_afdb_exact(
        AfdbExactRequest(
            sequence_groups_jsonl=sequence_path,
            source_records_jsonl=source_path,
            database_manifest=manifest_path,
            output_directory=tmp_path / "output with spaces",
            **_provider_route(tmp_path, manifest_path),
            accession_map_tsv=accession_map,
            progress=False,
        )
    )

    assert len(requests) == 2
    assert output.results[0].execution_status is ExecutionStatus.COMPLETED_HIT
    hit = output.results[0].hits[0]
    assert hit.sequence_group_id == group.sequence_group_id
    assert hit.model_key == "afdb:AF-P69905-F1:v6"
    assert hit.sequence_identity == 1.0
    assert hit.raw_metrics["global_metric_value"] == 98.06
    assert len(output.coordinate_sources) == 1
    coordinate = output.coordinate_sources[0]
    assert coordinate.source_sequence_sha256 == group.sha256
    assert Path(coordinate.coordinate_path).is_file()
    assert Path(coordinate.coordinate_path).read_bytes() == _mmcif("ACDE")
    metadata_paths = list(
        (tmp_path / "coordinate cache with spaces" / "afdb" / "metadata").rglob(
            "*.json"
        )
    )
    assert len(metadata_paths) == 1
    cache_metadata = json.loads(metadata_paths[0].read_text(encoding="utf-8"))
    assert cache_metadata["exact_sequence_match"] is True
    assert cache_metadata["source_sequence_sha256"] == group.sha256
    assert cache_metadata["license_or_provenance"] == "AlphaFold DB CC-BY-4.0"


def test_afdb_exact_refseq_only_record_is_ineligible_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sequence_path, source_path, manifest_path, _ = _write_inputs(
        tmp_path, protein_id="WP_012345678.1"
    )

    def unexpected_request(*_: object, **__: object) -> afdb_module._HttpResponse:
        raise AssertionError("RefSeq-only source triggered an AFDB request")

    monkeypatch.setattr(afdb_module, "_http_get", unexpected_request)
    output = search_afdb_exact(
        AfdbExactRequest(
            sequence_groups_jsonl=sequence_path,
            source_records_jsonl=source_path,
            database_manifest=manifest_path,
            output_directory=tmp_path / "ineligible output",
            **_provider_route(tmp_path, manifest_path),
            progress=False,
        )
    )

    result = output.results[0]
    assert result.execution_status is ExecutionStatus.SKIPPED_INELIGIBLE
    assert result.hit_count == 0
    assert "no strict UniProt accession" in result.warnings[0]
    assert (output.search_manifest.parent / "raw/http.log").read_text() == ""


def test_afdb_exact_rejects_non_exact_api_mapping_without_fetching_coordinates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sequence_path, source_path, manifest_path, _ = _write_inputs(
        tmp_path, protein_id="P69905"
    )
    cif_url = "https://alphafold.ebi.ac.uk/files/AF-P69905-F1-model_v6.cif"
    requests: list[str] = []

    def fake_http_get(url: str, **_: object) -> afdb_module._HttpResponse:
        requests.append(url)
        return afdb_module._HttpResponse(
            requested_url=url,
            url=url,
            status=200,
            headers={"content-type": "application/json"},
            body=_metadata("ACDF", cif_url=cif_url),
        )

    monkeypatch.setattr(afdb_module, "_http_get", fake_http_get)
    output = search_afdb_exact(
        AfdbExactRequest(
            sequence_groups_jsonl=sequence_path,
            source_records_jsonl=source_path,
            database_manifest=manifest_path,
            output_directory=tmp_path / "mismatch output",
            **_provider_route(tmp_path, manifest_path),
            progress=False,
        )
    )

    assert len(requests) == 1
    result = output.results[0]
    assert result.execution_status is ExecutionStatus.COMPLETED_NO_HIT
    assert result.hit_count == 0
    raw = json.loads(
        (output.search_manifest.parent / result.raw_result_pointer).read_text()
    )
    assert raw["rejections"][0]["reason"] == "AFDB source sequence is not exact"


def test_afdb_exact_fails_loudly_when_coordinate_sequence_disagrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sequence_path, source_path, manifest_path, _ = _write_inputs(
        tmp_path, protein_id="P69905"
    )
    cif_url = "https://alphafold.ebi.ac.uk/files/AF-P69905-F1-model_v6.cif"

    def fake_http_get(url: str, **_: object) -> afdb_module._HttpResponse:
        body = _mmcif("ACDF") if url == cif_url else _metadata("ACDE", cif_url=cif_url)
        return afdb_module._HttpResponse(
            requested_url=url,
            url=url,
            status=200,
            headers={},
            body=body,
        )

    monkeypatch.setattr(afdb_module, "_http_get", fake_http_get)
    with pytest.raises(ResultParseError, match="coordinate sequence differs"):
        search_afdb_exact(
            AfdbExactRequest(
                sequence_groups_jsonl=sequence_path,
                source_records_jsonl=source_path,
                database_manifest=manifest_path,
                output_directory=tmp_path / "bad coordinate output",
                **_provider_route(tmp_path, manifest_path),
                progress=False,
            )
        )
