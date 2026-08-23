"""Tests for bounded direct-PDB coordinate registration."""

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from genome_to_diffraction.databases.cache import initialise_coordinate_cache
from genome_to_diffraction.databases.network import DownloadMetadata
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.results import (
    EligibilityStatus,
    SequenceGroupRecord,
    StructuralSearchHit,
)
from genome_to_diffraction.structure_search import (
    PdbCoordinateInputError,
    PdbCoordinateRegistrationRequest,
    register_pdb_coordinates,
)
from genome_to_diffraction.structure_search import (
    pdb_coordinates as pdb_coordinates_module,
)


def _group(sequence: str) -> SequenceGroupRecord:
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=400.0,
        mass_method="test mass",
        residue_policy="standard_exact",
        source_record_count=1,
    )


def _hit(
    group: SequenceGroupRecord,
    *,
    hit_id: str,
    rank: int,
    pdb_id: str,
    source_sequence: str,
    identity: float,
) -> StructuralSearchHit:
    return StructuralSearchHit(
        schema_version="1.0",
        hit_id=hit_id,
        sequence_group_id=group.sequence_group_id,
        provider="pdb_sequence_mmseqs",
        provider_rank=rank,
        target_id=f"{pdb_id.lower()}_A",
        model_key=f"pdb:{pdb_id}:legacy_seqres_suffix:A",
        target_chain_or_entity="A",
        pdb_id=pdb_id,
        identifier_namespace="legacy_seqres_suffix",
        query_start=1,
        query_end=4,
        target_start=1,
        target_end=4,
        aligned_length=4,
        query_coverage=1.0,
        target_coverage=1.0,
        sequence_identity=identity,
        evalue=1.0e-20 * rank,
        bits=100.0 - rank,
        database_id="db_test_pdb_sequences",
        raw_result_pointer="raw/mmseqs-results.tsv",
        raw_metrics={
            "identity_fraction": identity,
            "target_sequence_length": len(source_sequence),
            "target_sequence_sha256": hashlib.sha256(
                source_sequence.encode("ascii")
            ).hexdigest(),
        },
        eligibility_status=EligibilityStatus.SELECTED,
        eligibility_reason="test selected direct-PDB hit",
    )


def _compressed_mmcif(pdb_id: str, sequence: str) -> bytes:
    document = (
        f"data_{pdb_id}\n"
        f"_entry.id {pdb_id}\n"
        "loop_\n"
        "_struct_asym.id\n"
        "_struct_asym.entity_id\n"
        "A 1\n"
        "loop_\n"
        "_entity_poly.entity_id\n"
        "_entity_poly.type\n"
        "_entity_poly.pdbx_strand_id\n"
        "_entity_poly.pdbx_seq_one_letter_code_can\n"
        "1 'polypeptide(L)' A "
        f"{sequence}\n"
    ).encode("ascii")
    return gzip.compress(document, mtime=0)


def _inputs(
    tmp_path: Path,
) -> tuple[Path, Path, Path, tuple[StructuralSearchHit, ...]]:
    first_group = _group("ACDE")
    second_group = _group("FGHI")
    groups = tmp_path / "sequence groups.jsonl"
    groups.write_text(
        "".join(
            f"{canonical_json_text(item)}\n" for item in (first_group, second_group)
        ),
        encoding="utf-8",
    )
    hits = (
        _hit(
            first_group,
            hit_id="hit_first_best",
            rank=1,
            pdb_id="1ABC",
            source_sequence="ACDE",
            identity=1.0,
        ),
        _hit(
            first_group,
            hit_id="hit_first_second",
            rank=2,
            pdb_id="2ABC",
            source_sequence="ACDF",
            identity=0.75,
        ),
        _hit(
            second_group,
            hit_id="hit_second_best",
            rank=1,
            pdb_id="3ABC",
            source_sequence="FGHA",
            identity=0.75,
        ),
    )
    hit_path = tmp_path / "structural hits.jsonl"
    hit_path.write_text(
        "".join(f"{canonical_json_text(item)}\n" for item in hits),
        encoding="utf-8",
    )
    sequence_root = tmp_path / "PDB sequence resource"
    sequence_root.mkdir()
    foldseek_root = tmp_path / "PDB Foldseek resource"
    foldseek_root.mkdir()
    cache_root = tmp_path / "coordinate cache with spaces"
    initialise_coordinate_cache(cache_root, progress=False)
    common = {
        "source": "test",
        "prepared_at": "2026-08-11T00:00:00Z",
        "manifest_sha256": "a" * 64,
        "smoke_test_status": "passed",
        "status": "ready",
    }
    manifest = tmp_path / "database manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "manifest_id": "dbm_pdb_coordinate_test",
                "created_at": "2026-08-11T00:00:00Z",
                "resources": [
                    {
                        **common,
                        "database_id": "db_test_pdb_sequences",
                        "name": "pdb_sequences",
                        "root_path": str(sequence_root),
                        "release_or_snapshot": "pdb-2026-08-11",
                        "prepared_with": {"tool": "mmseqs", "version": "test"},
                    },
                    {
                        **common,
                        "database_id": "db_test_pdb_foldseek",
                        "name": "pdb_foldseek",
                        "root_path": str(foldseek_root),
                        "release_or_snapshot": "pdb-2026-08-11",
                        "prepared_with": {"tool": "foldseek", "version": "test"},
                    },
                    {
                        **common,
                        "database_id": "db_test_coordinate_cache",
                        "name": "coordinate_cache",
                        "root_path": str(cache_root),
                        "prepared_with": {
                            "tool": "genome-to-diffraction",
                            "version": "test",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return hit_path, groups, manifest, hits


def _fake_download(monkeypatch: pytest.MonkeyPatch, *, fail: bool = False) -> list[str]:
    calls: list[str] = []
    sequences = {"1abc": "ACDE", "2abc": "ACDF", "3abc": "FGHA"}

    def download(
        url: str,
        destination: Path,
        **_kwargs: object,
    ) -> DownloadMetadata:
        if fail:
            raise AssertionError("cached coordinate unexpectedly downloaded again")
        pdb_id = url.rsplit("/", 1)[1].split(".", 1)[0]
        calls.append(pdb_id)
        payload = _compressed_mmcif(pdb_id.upper(), sequences[pdb_id])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return DownloadMetadata(
            requested_url=url,
            url=url,
            etag=f'"{pdb_id}"',
            last_modified="Tue, 11 Aug 2026 00:00:00 GMT",
            content_type="application/gzip",
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )

    monkeypatch.setattr(pdb_coordinates_module, "download_public_resource", download)
    return calls


def _request(
    tmp_path: Path,
    hits: Path,
    groups: Path,
    manifest: Path,
    *,
    suffix: str = "",
    materialise: bool = False,
) -> PdbCoordinateRegistrationRequest:
    return PdbCoordinateRegistrationRequest(
        structural_hits_jsonl=hits,
        sequence_groups_jsonl=groups,
        database_manifest=manifest,
        output_directory=tmp_path / f"registered PDB coordinates{suffix}",
        maximum_hits_per_sequence_group=3,
        maximum_mappings=2,
        minimum_free_bytes=0,
        materialise_coordinate_objects=materialise,
        progress=False,
    )


def test_registration_reserves_sequence_diversity_and_reuses_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hit_path, groups, manifest, _ = _inputs(tmp_path)
    calls = _fake_download(monkeypatch)
    output = register_pdb_coordinates(_request(tmp_path, hit_path, groups, manifest))

    assert [item.hit_id for item in output.mappings] == [
        "hit_first_best",
        "hit_second_best",
    ]
    assert calls == ["1abc", "3abc"]
    assert len(output.coordinate_sources) == 2
    assert [item.exact_sequence_match for item in output.mappings] == [True, False]
    assert all(
        Path(item.coordinate_path).is_file() for item in output.coordinate_sources
    )
    registration = json.loads(output.manifest_json.read_text(encoding="utf-8"))
    assert registration["selected_mapping_count"] == 2
    assert registration["downloaded_entry_count"] == 2
    assert registration["parameters"]["selection_policy"] == (
        "diversity_rounds_then_alignment_quality"
    )

    _fake_download(monkeypatch, fail=True)
    reused = register_pdb_coordinates(
        _request(tmp_path, hit_path, groups, manifest, suffix=" reused")
    )
    reused_manifest = json.loads(reused.manifest_json.read_text(encoding="utf-8"))
    assert reused_manifest["cache_reused_entry_count"] == 2
    assert reused_manifest["downloaded_entry_count"] == 0
    assert [item.coordinate_id for item in reused.coordinate_sources] == [
        item.coordinate_id for item in output.coordinate_sources
    ]


def test_registration_requires_search_snapshot_sequence_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hit_path, groups, manifest, hits = _inputs(tmp_path)
    malformed = hits[0].model_copy(update={"raw_metrics": {"identity_fraction": 1.0}})
    hit_path.write_text(f"{canonical_json_text(malformed)}\n", encoding="utf-8")
    _fake_download(monkeypatch)

    with pytest.raises(PdbCoordinateInputError, match="rerun pdb-sequence adapter v2"):
        register_pdb_coordinates(_request(tmp_path, hit_path, groups, manifest))


def test_registration_materialises_one_relative_object_for_reused_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hit_path, groups, manifest, hits = _inputs(tmp_path)
    repeated = hits[0].model_copy(
        update={"hit_id": "hit_first_repeated", "provider_rank": 2}
    )
    hit_path.write_text(
        "".join(f"{canonical_json_text(item)}\n" for item in (hits[0], repeated)),
        encoding="utf-8",
    )
    calls = _fake_download(monkeypatch)

    output = register_pdb_coordinates(
        _request(
            tmp_path,
            hit_path,
            groups,
            manifest,
            suffix=" staged",
            materialise=True,
        )
    )

    assert calls == ["1abc"]
    assert len(output.coordinate_sources) == 1
    assert len(output.mappings) == 2
    relative = Path(output.coordinate_sources[0].coordinate_path)
    assert not relative.is_absolute()
    assert (output.manifest_json.parent / relative).is_file()
    registration = json.loads(output.manifest_json.read_text(encoding="utf-8"))
    assert registration["parameters"]["materialise_coordinate_objects"] is True
