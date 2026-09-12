"""Complete, read-only coordinate admission before any shared-cache write."""

import gzip
import json
from pathlib import Path

import pytest
from pydantic import ValidationError as ModelValidationError

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.databases.cache import publish_pdb_coordinate
from genome_to_diffraction.databases.common import DatabaseError
from genome_to_diffraction.hpc import m6_coordinate_prefetch as prefetch
from genome_to_diffraction.hpc.m6_coordinate_cache import inspect_coordinate_cache
from genome_to_diffraction.hpc.m6_coordinate_inspection_client import _Report
from genome_to_diffraction.hpc.m6_coordinate_prefetch import (
    PREFETCH_MANIFEST,
    CoordinateImportPlan,
    authenticate_inspection,
    fixed_pdb_url,
    load_prefetch_bundle,
    prevalidate_proposed_cache,
    validate_prefetched_mappings,
)
from genome_to_diffraction.hpc.m6_coordinate_requests import CASES
from genome_to_diffraction.hpc.models import ValidationError
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.results import StructuralSearchHit
from genome_to_diffraction.structure_search.pdb_coordinates import (
    PdbCoordinateParseError,
    _PdbEntity,
)
from tests.unit.test_m6_coordinate_cache import (
    _file_digests,
    _publish,
    _snapshot,
    _two_entities,
)
from tests.unit.test_pdb_coordinates import _compressed_mmcif, _group, _hit


def _write_manifest(root: Path, document: dict[str, object]) -> str:
    document.pop("prefetch_id", None)
    document["prefetch_id"] = content_id("m6prefetch_", document)
    atomic_write_json(root / PREFETCH_MANIFEST, document)
    return sha256_file(root / PREFETCH_MANIFEST)


def _bundle(
    snapshot: Path,
    database: Path,
    checksum: str,
    *,
    payloads: dict[str, bytes] | None = None,
) -> tuple[Path, Path, dict[str, str]]:
    report = inspect_coordinate_cache(
        snapshot, database, expected_inventory_sha256=checksum
    )
    inspection = snapshot.parent / "inspection.json"
    atomic_write_json(inspection, report)
    root = snapshot.parent / "prefetch bundle"
    (root / "objects").mkdir(parents=True)
    defaults = {"1ABC": "ACDE", "2ABC": "ACDF", "3ABC": "FGHA"}
    objects = {}
    total = 0
    for pdb_id in _Report.model_validate(report, strict=True).missing_pdb_ids:
        relative = f"objects/{pdb_id.lower()}.cif.gz"
        source = root / relative
        source.write_bytes(
            payloads[pdb_id]
            if payloads is not None
            else _compressed_mmcif(pdb_id, defaults[pdb_id])
        )
        objects[pdb_id] = {
            "relative_path": relative,
            "requested_url": fixed_pdb_url(pdb_id),
            "source_url": fixed_pdb_url(pdb_id),
            "retrieved_at": "2026-09-12T01:00:00Z",
            "etag": '"retained-provider-etag"',
            "last_modified": "Fri, 11 Sep 2026 12:00:00 GMT",
            "content_type": "application/gzip",
            "sha256": sha256_file(source),
            "size_bytes": source.stat().st_size,
        }
        total += source.stat().st_size
    manifest = {
        "schema_version": "1.0",
        "adapter_version": "m6-coordinate-prefetch-v1",
        "request_run_id": report["request_run_id"],
        "producer_commit": report["producer_commit"],
        "request_inventory_sha256": checksum,
        "request_inventory_id": report["request_inventory_id"],
        "inspection_sha256": sha256_file(inspection),
        "inspection_id": report["inspection_id"],
        "database_manifest_sha256": sha256_file(database),
        "objects": objects,
        "total_size_bytes": total,
    }
    return (
        root,
        inspection,
        {
            "expected_manifest_sha256": _write_manifest(root, manifest),
            "expected_inventory_sha256": checksum,
            "expected_inspection_sha256": sha256_file(inspection),
        },
    )


def _publish_plan(plan: CoordinateImportPlan) -> None:
    for source, expected in plan.coordinates:
        actual = publish_pdb_coordinate(
            plan.cache_root,
            source,
            pdb_id=expected.source_id,
            requested_url=expected.requested_url,
            source_url=expected.source_url,
            retrieved_at=expected.retrieved_at,
            etag=expected.etag,
            last_modified=expected.last_modified,
            content_type=expected.content_type,
            progress=False,
        )
        assert actual == expected


def test_complete_plan_is_read_only_and_matches_unchanged_postinspection(
    tmp_path: Path,
) -> None:
    snapshot, database, cache, checksum = _snapshot(tmp_path)
    previous = _publish(cache)
    old_identity = (cache / previous.metadata_relative_path).stat().st_ino
    root, inspection, bindings = _bundle(snapshot, database, checksum)
    before = _file_digests(tmp_path)
    plan = prevalidate_proposed_cache(root, snapshot, database, inspection, **bindings)
    assert _file_digests(tmp_path) == before
    assert len(plan.coordinates) == 2
    assert plan.proposed_report["requested_mapping_count"] == 6
    assert plan.proposed_report["missing_pdb_ids"] == []
    _publish_plan(plan)
    assert (
        inspect_coordinate_cache(snapshot, database, expected_inventory_sha256=checksum)
        == plan.proposed_report
    )
    assert (cache / previous.metadata_relative_path).stat().st_ino == old_identity
    for _, record in plan.coordinates:
        assert record.etag == '"retained-provider-etag"'
        assert record.retrieved_at == "2026-09-12T01:00:00Z"


def test_empty_missing_set_accepts_only_empty_bundle(tmp_path: Path) -> None:
    snapshot, database, cache, checksum = _snapshot(tmp_path)
    for pdb_id, sequence in {"1ABC": "ACDE", "2ABC": "ACDF", "3ABC": "FGHA"}.items():
        _publish(cache, pdb_id=pdb_id, payload=_compressed_mmcif(pdb_id, sequence))
    root, inspection, bindings = _bundle(snapshot, database, checksum)
    before = _file_digests(tmp_path)
    plan = prevalidate_proposed_cache(root, snapshot, database, inspection, **bindings)
    assert plan.coordinates == ()
    assert plan.manifest.total_size_bytes == 0
    assert _file_digests(tmp_path) == before


@pytest.mark.parametrize(
    "field",
    [
        "request_run_id",
        "producer_commit",
        "request_inventory_id",
        "inspection_id",
        "database_manifest_sha256",
    ],
)
def test_changed_manifest_bindings_fail_without_cache_writes(
    tmp_path: Path, field: str
) -> None:
    snapshot, database, cache, checksum = _snapshot(tmp_path)
    root, inspection, bindings = _bundle(snapshot, database, checksum)
    manifest = json.loads((root / PREFETCH_MANIFEST).read_text())
    manifest[field] = "b" * 64
    bindings["expected_manifest_sha256"] = _write_manifest(root, manifest)
    before = _file_digests(cache)
    with pytest.raises(ValidationError, match="source bindings"):
        prevalidate_proposed_cache(root, snapshot, database, inspection, **bindings)
    assert _file_digests(cache) == before


@pytest.mark.parametrize(
    "change", ["subset", "extra", "lowercase", "reordered_mapping", "tampered_snapshot"]
)
def test_complete_original_request_is_mandatory(tmp_path: Path, change: str) -> None:
    snapshot, database, cache, checksum = _snapshot(tmp_path)
    root, inspection, bindings = _bundle(snapshot, database, checksum)
    if change in {"subset", "extra", "lowercase"}:
        manifest = json.loads((root / PREFETCH_MANIFEST).read_text())
        record = manifest["objects"]["1ABC"]
        if change != "extra":
            del manifest["objects"]["1ABC"]
        if change != "subset":
            manifest["objects"]["4ABC" if change == "extra" else "1abc"] = record
        bindings["expected_manifest_sha256"] = _write_manifest(root, manifest)
    elif change == "reordered_mapping":
        report = json.loads(inspection.read_text())
        report["cases"][CASES[0]]["mappings"].reverse()
        report.pop("inspection_id")
        report["inspection_id"] = content_id("m6cache_", report)
        atomic_write_json(inspection, report)
        bindings["expected_inspection_sha256"] = sha256_file(inspection)
    else:
        selected = snapshot / "requests" / CASES[0] / "selected_structural_hits.jsonl"
        selected.write_text(selected.read_text() + "\n")
    before = _file_digests(cache)
    with pytest.raises(ValidationError):
        prevalidate_proposed_cache(root, snapshot, database, inspection, **bindings)
    assert _file_digests(cache) == before


@pytest.mark.parametrize(
    "change",
    [
        "extra_file",
        "extra_directory",
        "symlink",
        "hardlink",
        "tampered_object",
        "tampered_manifest",
        "string_size",
        "arbitrary_url",
        "redirect_url",
        "traversal",
        "non_utc",
        "wrong_total",
    ],
)
def test_unsafe_or_unauthenticated_bundle_fails(tmp_path: Path, change: str) -> None:
    snapshot, database, cache, checksum = _snapshot(tmp_path)
    root, inspection, bindings = _bundle(snapshot, database, checksum)
    source = root / "objects" / "1abc.cif.gz"
    manifest = json.loads((root / PREFETCH_MANIFEST).read_text())
    if change == "extra_file":
        (root / "objects" / "1abc.cif.gz.partial").write_bytes(b"partial")
    elif change == "extra_directory":
        (root / "extra").mkdir()
    elif change in {"symlink", "hardlink"}:
        original = tmp_path / "outside.cif.gz"
        source.rename(original)
        if change == "symlink":
            source.symlink_to(original)
        else:
            source.hardlink_to(original)
    elif change == "tampered_object":
        source.write_bytes(source.read_bytes() + b"changed")
    elif change == "tampered_manifest":
        (root / PREFETCH_MANIFEST).write_text("{}\n")
    else:
        record = manifest["objects"]["1ABC"]
        if change == "string_size":
            record["size_bytes"] = str(record["size_bytes"])
        elif change in {"arbitrary_url", "redirect_url"}:
            record["requested_url" if change == "arbitrary_url" else "source_url"] = (
                "https://example.invalid/1abc.cif.gz"
            )
        elif change == "traversal":
            record["relative_path"] = "../objects/1abc.cif.gz"
        elif change == "non_utc":
            record["retrieved_at"] = "2026-09-12T01:00:00+09:00"
        else:
            manifest["total_size_bytes"] += 1
        bindings["expected_manifest_sha256"] = _write_manifest(root, manifest)
    before = _file_digests(cache)
    with pytest.raises((ValidationError, ModelValidationError)):
        prevalidate_proposed_cache(root, snapshot, database, inspection, **bindings)
    assert _file_digests(cache) == before


@pytest.mark.parametrize(
    "payload",
    [
        b"not gzip",
        gzip.compress(b""),
        gzip.compress(b"data_invalid\n"),
        _compressed_mmcif("9ABC", "ACDE"),
        _compressed_mmcif("1ABC", "AAAA"),
        _compressed_mmcif("1ABC", "ACDE")[:-4],
    ],
)
def test_malformed_or_incompatible_coordinates_fail_before_any_publication(
    tmp_path: Path, payload: bytes
) -> None:
    snapshot, database, cache, checksum = _snapshot(tmp_path)
    root, inspection, bindings = _bundle(
        snapshot,
        database,
        checksum,
        payloads={
            "1ABC": payload,
            "2ABC": _compressed_mmcif("2ABC", "ACDF"),
            "3ABC": _compressed_mmcif("3ABC", "FGHA"),
        },
    )
    before = _file_digests(cache)
    with pytest.raises(ValidationError):
        prevalidate_proposed_cache(root, snapshot, database, inspection, **bindings)
    assert _file_digests(cache) == before


@pytest.mark.parametrize(
    "bound",
    [
        "MAX_COORDINATE_OBJECT_BYTES",
        "MAX_COORDINATE_TOTAL_BYTES",
        "MAX_EXPANDED_COORDINATE_BYTES",
        "MAX_PREFETCH_MANIFEST_BYTES",
    ],
)
def test_streaming_resource_limits_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bound: str
) -> None:
    snapshot, database, cache, checksum = _snapshot(tmp_path)
    root, inspection, bindings = _bundle(snapshot, database, checksum)
    monkeypatch.setattr(prefetch, bound, 1)
    before = _file_digests(cache)
    with pytest.raises(ValidationError):
        prevalidate_proposed_cache(root, snapshot, database, inspection, **bindings)
    assert _file_digests(cache) == before


@pytest.mark.parametrize("collision", ["object", "index", "metadata"])
def test_all_destinations_preflight_before_first_publication(
    tmp_path: Path, collision: str
) -> None:
    snapshot, database, cache, checksum = _snapshot(tmp_path)
    root, inspection, bindings = _bundle(snapshot, database, checksum)
    initial = prevalidate_proposed_cache(
        root, snapshot, database, inspection, **bindings
    )
    last = initial.coordinates[-1][1]
    relative = {
        "object": last.object_relative_path,
        "index": f"digest_index/{last.object_sha256}.json",
        "metadata": last.metadata_relative_path,
    }[collision]
    path = cache / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n")
    before = _file_digests(cache)
    with pytest.raises(DatabaseError):
        prevalidate_proposed_cache(root, snapshot, database, inspection, **bindings)
    assert _file_digests(cache) == before
    assert not (cache / initial.coordinates[0][1].object_relative_path).exists()


def test_changed_inspected_cache_requires_fresh_authenticated_request(
    tmp_path: Path,
) -> None:
    snapshot, database, cache, checksum = _snapshot(tmp_path)
    root, inspection, bindings = _bundle(snapshot, database, checksum)
    _publish(cache)
    before = _file_digests(cache)
    with pytest.raises(ValidationError, match="cache changed"):
        prevalidate_proposed_cache(root, snapshot, database, inspection, **bindings)
    assert _file_digests(cache) == before


def test_proposed_union_can_keep_different_objects_for_the_two_cases(
    tmp_path: Path,
) -> None:
    cases: dict[str, tuple[StructuralSearchHit, ...]] = {
        case: (
            _hit(
                _group(sequence),
                hit_id=f"hit_{case}",
                rank=1,
                pdb_id="1ABC",
                source_sequence=sequence,
                identity=1.0,
            ),
        )
        for case, sequence in zip(CASES, ("ACDE", "FGHI"), strict=True)
    }
    snapshot, database, cache, checksum = _snapshot(tmp_path, cases=cases)
    old = _publish(cache)
    root, inspection, bindings = _bundle(
        snapshot,
        database,
        checksum,
        payloads={"1ABC": _compressed_mmcif("1ABC", "FGHI")},
    )
    validate_prefetched_mappings(root, snapshot, inspection, **bindings)
    before = _file_digests(cache)
    plan = prevalidate_proposed_cache(root, snapshot, database, inspection, **bindings)
    assert _file_digests(cache) == before
    _publish_plan(plan)
    observed = inspect_coordinate_cache(
        snapshot, database, expected_inventory_sha256=checksum
    )
    assert observed == plan.proposed_report
    report = _Report.model_validate(observed, strict=True)
    assert report.cases[CASES[0]].mappings[0].coordinate_sha256 == old.object_sha256
    assert len(report.cached_coordinates) == 2


def test_new_first_choice_cannot_break_an_already_cached_later_hit(
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
    different = second.model_copy(
        update={
            "hit_id": "different",
            "raw_metrics": second.raw_metrics
            | {"target_sequence_sha256": _group("FFFF").sha256},
        }
    )
    snapshot, database, cache, checksum = _snapshot(
        tmp_path, cases={CASES[0]: (first, second), CASES[1]: (different,)}
    )
    _publish(cache, payload=_two_entities("FGHI"))
    root, inspection, bindings = _bundle(
        snapshot, database, checksum, payloads={"1ABC": _two_entities("FFFF")}
    )
    before = _file_digests(cache)
    with pytest.raises(PdbCoordinateParseError, match="searched SEQRES snapshot"):
        prevalidate_proposed_cache(root, snapshot, database, inspection, **bindings)
    assert _file_digests(cache) == before


@pytest.mark.parametrize("tamper", [False, True])
def test_local_mapping_memo_is_call_scoped_and_exit_authenticated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: bool,
) -> None:
    snapshot, database, _, checksum = _snapshot(tmp_path)
    root, inspection, bindings = _bundle(snapshot, database, checksum)
    calls: list[str] = []
    original = prefetch._pdb_entity

    def observe(source: Path, *, hit: StructuralSearchHit) -> _PdbEntity:
        entity = original(source, hit=hit)
        calls.append(hit.hit_id)
        if tamper and len(calls) == 3:
            changed = root / "objects" / "1abc.cif.gz"
            changed.write_bytes(changed.read_bytes() + b"changed")
        return entity

    monkeypatch.setattr(prefetch, "_pdb_entity", observe)
    if tamper:
        with pytest.raises(ValidationError, match="checksum"):
            validate_prefetched_mappings(root, snapshot, inspection, **bindings)
        assert len(calls) == 3
    else:
        before = _file_digests(tmp_path)
        validate_prefetched_mappings(root, snapshot, inspection, **bindings)
        assert len(calls) == 3  # Both cases' six mappings have three exact keys.
        validate_prefetched_mappings(root, snapshot, inspection, **bindings)
        assert len(calls) == 6  # No memo or validity promise survives the call.
        assert _file_digests(tmp_path) == before


def test_local_qualification_rejects_later_missing_mapping_mismatch(
    tmp_path: Path,
) -> None:
    snapshot, database, _, checksum = _snapshot(tmp_path)
    root, inspection, bindings = _bundle(
        snapshot,
        database,
        checksum,
        payloads={
            "1ABC": _compressed_mmcif("1ABC", "ACDE"),
            "2ABC": _compressed_mmcif("2ABC", "ACDF"),
            "3ABC": _compressed_mmcif("3ABC", "AAAA"),
        },
    )
    before = _file_digests(tmp_path)
    with pytest.raises(PdbCoordinateParseError, match="searched SEQRES snapshot"):
        validate_prefetched_mappings(root, snapshot, inspection, **bindings)
    assert _file_digests(tmp_path) == before


def test_inspection_authentication_and_fixed_public_url(tmp_path: Path) -> None:
    snapshot, database, _, checksum = _snapshot(tmp_path)
    root, inspection, bindings = _bundle(snapshot, database, checksum)
    inventory, report = authenticate_inspection(
        snapshot,
        inspection,
        expected_inventory_sha256=checksum,
        expected_inspection_sha256=bindings["expected_inspection_sha256"],
    )
    assert report.request_inventory_id == inventory.inventory_id
    assert (
        fixed_pdb_url("1ABC")
        == "https://files.rcsb.org/pub/pdb/data/structures/divided/mmCIF/ab/1abc.cif.gz"
    )
    for invalid in ("1abc", "../1ABC", "ABCD", "1ABC?other"):
        with pytest.raises(ValidationError):
            fixed_pdb_url(invalid)
    assert (
        load_prefetch_bundle(root, snapshot, inspection, **bindings).total_size_bytes
        > 0
    )
