"""Offline complete-request inspection without changing registration selection."""

import gzip
import json
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.databases.cache import (
    CachedCoordinate,
    publish_pdb_coordinate,
)
from genome_to_diffraction.databases.common import DatabaseError
from genome_to_diffraction.hpc import m6_coordinate_cache as inspection_module
from genome_to_diffraction.hpc.m6_coordinate_cache import inspect_coordinate_cache
from genome_to_diffraction.hpc.m6_coordinate_requests import CASES
from genome_to_diffraction.hpc.models import ValidationError
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    StructuralSearchHit,
)
from genome_to_diffraction.structure_search import pdb_coordinates
from genome_to_diffraction.structure_search.pdb_coordinates import (
    PdbCoordinateParseError,
    PdbCoordinateRegistrationRequest,
    _PdbEntity,
)
from tests.unit.test_pdb_coordinates import _compressed_mmcif, _group, _hit, _inputs


def _freeze(snapshot: Path, inventory: dict[str, object]) -> str:
    inventory.pop("inventory_id", None)
    inventory["inventory_id"] = content_id("m6coords_", inventory)
    atomic_write_json(snapshot / "request_inventory.json", inventory)
    return sha256_file(snapshot / "request_inventory.json")


def _snapshot(
    tmp_path: Path,
    *,
    cases: dict[str, tuple[StructuralSearchHit, ...]] | None = None,
    group_records: tuple[SequenceGroupRecord, ...] | None = None,
) -> tuple[Path, Path, Path, str]:
    _, groups, database, hits = _inputs(tmp_path)
    if group_records is not None:
        groups.write_text(
            "".join(f"{canonical_json_text(group)}\n" for group in group_records),
            encoding="ascii",
        )
    snapshot = tmp_path / "frozen requests"
    reports = {}
    all_entries: set[str] = set()
    for case_id in CASES:
        selected = cases[case_id] if cases is not None else hits
        case_root = snapshot / "requests" / case_id
        eligible = case_root / "eligible-candidates"
        eligible.mkdir(parents=True)
        (eligible / "sequence_groups.jsonl").write_bytes(groups.read_bytes())
        selected_path = case_root / "selected_structural_hits.jsonl"
        selected_path.write_text(
            "".join(f"{canonical_json_text(hit)}\n" for hit in selected),
            encoding="ascii",
        )
        entries = {str(hit.pdb_id).upper() for hit in selected}
        all_entries.update(entries)
        reports[case_id] = {
            "catalogue_key": ("a" if case_id == CASES[0] else "b") * 64,
            "eligible_group_count": len(group_records)
            if group_records is not None
            else 2,
            "accepted_hit_count": len(selected),
            "registration_mapping_bound": len(selected),
            "requested_mapping_count": len(selected),
            "pdb_ids": sorted(entries),
            "selected_hits_sha256": sha256_file(selected_path),
        }
    inventory = {
        "schema_version": "1.0",
        "adapter_version": "m6-coordinate-requests-v1",
        "run_id": "gtd-m6-native-control-20260912T120000Z-" + "1" * 12 + "-01234567",
        "producer_commit": "1" * 40,
        "database_manifest_sha256": sha256_file(database),
        "cases": reports,
        "distinct_pdb_count": len(all_entries),
        "pdb_ids": sorted(all_entries),
        "input_and_request_sha256": {
            path.relative_to(snapshot).as_posix(): sha256_file(path)
            for path in snapshot.rglob("*")
            if path.is_file()
        },
        "network_acquisition_performed": False,
        "cache_import_performed": False,
    }
    return (
        snapshot,
        database,
        tmp_path / "coordinate cache with spaces",
        _freeze(snapshot, inventory),
    )


def _publish(
    root: Path,
    *,
    pdb_id: str = "1ABC",
    payload: bytes | None = None,
    retrieved_at: str = "2026-08-11T00:00:00Z",
) -> CachedCoordinate:
    source = root.parent / "synthetic-public.cif.gz"
    source.write_bytes(payload or _compressed_mmcif(pdb_id, "ACDE"))
    url = f"https://files.rcsb.org/download/{pdb_id.lower()}.cif.gz"
    return publish_pdb_coordinate(
        root,
        source,
        pdb_id=pdb_id,
        requested_url=url,
        source_url=url,
        retrieved_at=retrieved_at,
        etag=None,
        last_modified=None,
        content_type="application/gzip",
        progress=False,
    )


def _file_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_complete_two_case_inventory_and_shared_missing_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot, database, cache, checksum = _snapshot(tmp_path)
    cached = _publish(cache)
    before = _file_digests(tmp_path)

    def unexpected_download(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline inspection attempted a download")

    monkeypatch.setattr(
        pdb_coordinates, "download_public_resource", unexpected_download
    )
    report = inspect_coordinate_cache(
        snapshot, database, expected_inventory_sha256=checksum
    )
    assert _file_digests(tmp_path) == before
    assert report["missing_pdb_ids"] == ["2ABC", "3ABC"]
    assert report["requested_mapping_count"] == 6
    assert report["cached_coordinates"] == {cached.metadata_sha256: cached.as_json()}
    cases = report["cases"]
    assert isinstance(cases, dict)
    for case_id in CASES:
        assert cases[case_id]["cached_mapping_count"] == 1
        assert cases[case_id]["missing_mapping_count"] == 2
        mappings = cases[case_id]["mappings"]
        assert [item["hit_id"] for item in mappings] == [
            "hit_first_best",
            "hit_first_second",
            "hit_second_best",
        ]
        assert mappings[0]["coordinate_sha256"] == cached.object_sha256
        assert mappings[0]["metadata_sha256"] == cached.metadata_sha256
        assert mappings[1]["coordinate_sha256"] is None


def test_preserves_many_mapping_ids_and_order_without_reselection(
    tmp_path: Path,
) -> None:
    residues = "ACDEFGHIKLMNPQRSTVWY"
    groups = tuple(
        _group(f"AC{residues[index // len(residues)]}{residues[index % len(residues)]}")
        for index in range(31)
    )
    hits = tuple(
        _hit(
            groups[number // 3],
            hit_id=f"hit_{number:03}",
            rank=number % 3 + 1,
            pdb_id="1ABC",
            source_sequence="ACDE",
            identity=1.0,
        )
        for number in range(93)
    )
    selected = {CASES[0]: hits, CASES[1]: tuple(reversed(hits))}
    snapshot, database, cache, checksum = _snapshot(
        tmp_path, cases=selected, group_records=groups
    )
    _publish(cache)
    report = inspect_coordinate_cache(
        snapshot, database, expected_inventory_sha256=checksum
    )
    assert report["requested_mapping_count"] == 186
    assert report["missing_pdb_ids"] == []
    cases = report["cases"]
    assert isinstance(cases, dict)
    for case_id in CASES:
        assert [item["hit_id"] for item in cases[case_id]["mappings"]] == [
            hit.hit_id for hit in selected[case_id]
        ]


def test_offline_resolver_is_called_once_per_case_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = _group("ACDE")
    hits = tuple(
        _hit(
            group,
            hit_id=f"hit_{i}",
            rank=i + 1,
            pdb_id="1ABC",
            source_sequence="ACDE",
            identity=1.0,
        )
        for i in range(3)
    )
    snapshot, database, _, checksum = _snapshot(
        tmp_path, cases={case: hits for case in CASES}
    )
    calls = []
    original = inspection_module._cached_or_downloaded

    def observe(
        root: Path,
        *,
        hit: StructuralSearchHit,
        request: PdbCoordinateRegistrationRequest,
    ) -> tuple[CachedCoordinate, _PdbEntity, bool]:
        calls.append(hit)
        return original(root, hit=hit, request=request)

    monkeypatch.setattr(inspection_module, "_cached_or_downloaded", observe)
    report = inspect_coordinate_cache(
        snapshot, database, expected_inventory_sha256=checksum
    )
    assert len(calls) == 2
    assert report["requested_mapping_count"] == 6
    assert report["missing_pdb_ids"] == ["1ABC"]


def test_same_entry_cached_in_one_case_can_be_missing_in_the_other(
    tmp_path: Path,
) -> None:
    selected: dict[str, tuple[StructuralSearchHit, ...]] = {
        case_id: (
            _hit(
                _group(sequence),
                hit_id=f"hit_{case_id}",
                rank=1,
                pdb_id="1ABC",
                source_sequence=sequence,
                identity=1.0,
            ),
        )
        for case_id, sequence in zip(CASES, ("ACDE", "FGHI"), strict=True)
    }
    snapshot, database, cache, checksum = _snapshot(tmp_path, cases=selected)
    _publish(cache)
    report = inspect_coordinate_cache(
        snapshot, database, expected_inventory_sha256=checksum
    )
    cases = report["cases"]
    assert isinstance(cases, dict)
    assert cases[CASES[0]]["mappings"][0]["status"] == "cached"
    assert cases[CASES[1]]["mappings"][0]["status"] == "missing"
    assert (
        cases[CASES[1]]["mappings"][0]["target_sequence_sha256"]
        == _group("FGHI").sha256
    )
    assert report["missing_pdb_ids"] == ["1ABC"]


@pytest.mark.parametrize("corruption", ["object", "metadata", "index"])
def test_existing_integrity_errors_are_not_missing(
    tmp_path: Path, corruption: str
) -> None:
    snapshot, database, cache, checksum = _snapshot(tmp_path)
    cached = _publish(cache)
    relative = {
        "object": cached.object_relative_path,
        "metadata": cached.metadata_relative_path,
        "index": f"digest_index/{cached.object_sha256}.json",
    }[corruption]
    (cache / relative).write_bytes(b"invalid\n")
    with pytest.raises(DatabaseError):
        inspect_coordinate_cache(snapshot, database, expected_inventory_sha256=checksum)


def _two_entities(second_sequence: str) -> bytes:
    return gzip.compress(
        (
            "data_1ABC\n_entry.id 1ABC\nloop_\n_struct_asym.id\n"
            "_struct_asym.entity_id\nA 1\nB 2\nloop_\n_entity_poly.entity_id\n"
            "_entity_poly.type\n_entity_poly.pdbx_strand_id\n"
            "_entity_poly.pdbx_seq_one_letter_code_can\n"
            "1 'polypeptide(L)' A ACDE\n"
            f"2 'polypeptide(L)' B {second_sequence}\n"
        ).encode("ascii"),
        mtime=0,
    )


def test_first_selected_object_later_hit_conflict_does_not_use_older_object(
    tmp_path: Path,
) -> None:
    first = _hit(
        _group("ACDE"),
        hit_id="first",
        rank=1,
        pdb_id="1ABC",
        source_sequence="ACDE",
        identity=1.0,
    )
    second = _hit(
        _group("FGHI"),
        hit_id="second",
        rank=1,
        pdb_id="1ABC",
        source_sequence="FGHI",
        identity=1.0,
    ).model_copy(
        update={
            "target_id": "1abc_B",
            "target_chain_or_entity": "B",
            "model_key": "pdb:1ABC:legacy_seqres_suffix:B",
        }
    )
    snapshot, database, cache, checksum = _snapshot(
        tmp_path, cases={case: (first, second) for case in CASES}
    )
    _publish(cache, payload=_two_entities("FGHI"))
    _publish(cache, payload=_two_entities("FFFF"), retrieved_at="2026-09-11T00:00:00Z")
    before = _file_digests(tmp_path)
    with pytest.raises(PdbCoordinateParseError, match="searched SEQRES snapshot"):
        inspect_coordinate_cache(snapshot, database, expected_inventory_sha256=checksum)
    assert _file_digests(tmp_path) == before


@pytest.mark.parametrize(
    "binding", ["confirmed_inventory", "database", "input", "count"]
)
def test_changed_frozen_binding_fails(tmp_path: Path, binding: str) -> None:
    snapshot, database, _, checksum = _snapshot(tmp_path)
    if binding == "confirmed_inventory":
        checksum = "0" * 64
    elif binding == "database":
        database.write_text("{}\n", encoding="ascii")
    elif binding == "input":
        (
            snapshot / "requests" / CASES[0] / "selected_structural_hits.jsonl"
        ).write_text("", encoding="ascii")
    else:
        inventory = json.loads((snapshot / "request_inventory.json").read_text())
        inventory["cases"][CASES[0]]["requested_mapping_count"] += 1
        checksum = _freeze(snapshot, inventory)
    with pytest.raises(ValidationError):
        inspect_coordinate_cache(snapshot, database, expected_inventory_sha256=checksum)
