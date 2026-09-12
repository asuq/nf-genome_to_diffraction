"""Original-client import conservation, explicit completion and bounded transport."""

import hashlib
import json
import shutil
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError as ModelValidationError

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc import client as client_module
from genome_to_diffraction.hpc.cli import _build_parser
from genome_to_diffraction.hpc.client import SshTransport
from genome_to_diffraction.hpc.m6_coordinate_cache import inspect_coordinate_cache
from genome_to_diffraction.hpc.m6_coordinate_download import acquire_coordinate_prefetch
from genome_to_diffraction.hpc.m6_coordinate_import_client import (
    build_prefetch_archive,
    validate_import_response,
    validate_storage_preflight,
)
from genome_to_diffraction.hpc.m6_coordinate_prefetch import (
    authenticate_inspection,
    prevalidate_proposed_cache,
)
from genome_to_diffraction.hpc.m6_coordinate_requests import CASES
from genome_to_diffraction.hpc.m6_coordinate_storage import (
    coordinate_storage_reservations,
)
from genome_to_diffraction.hpc.models import (
    FailureClass,
    LocalRunRecord,
    RemoteOperationError,
    ValidationError,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.schemas.results import StructuralSearchHit
from tests.unit.test_hpc_client import (
    COMMIT,
    FakeTransport,
    _archive,
    _config,
    _controller,
)
from tests.unit.test_m6_coordinate_cache import _file_digests, _publish, _snapshot
from tests.unit.test_m6_coordinate_download import _http
from tests.unit.test_m6_coordinate_import import _import_fixture
from tests.unit.test_m6_coordinate_inspection import NEW_OWNER, OLD_OWNER
from tests.unit.test_m6_coordinate_inspection_client import NEW_RUN_ID
from tests.unit.test_m6_coordinate_prefetch import _bundle, _publish_plan
from tests.unit.test_pdb_coordinates import _compressed_mmcif, _group, _hit


def _identity(document: dict[str, Any], name: str, prefix: str) -> None:
    document.pop(name, None)
    document[name] = content_id(prefix, document)


def _fixture(tmp_path: Path, *, mixed: bool = False) -> dict[str, Any]:
    if mixed:
        first, second = _group("ACDE"), _group("FGHI")
        cases: dict[str, tuple[StructuralSearchHit, ...]] = {
            CASES[0]: (
                _hit(
                    first,
                    hit_id="hit_first",
                    rank=1,
                    pdb_id="1ABC",
                    source_sequence="ACDE",
                    identity=1.0,
                ),
            ),
            CASES[1]: (
                _hit(
                    second,
                    hit_id="hit_second",
                    rank=1,
                    pdb_id="1ABC",
                    source_sequence="FGHI",
                    identity=1.0,
                ),
            ),
        }
        snapshot, database, cache, checksum = _snapshot(
            tmp_path, cases=cases, group_records=(first, second)
        )
    else:
        snapshot, database, cache, checksum = _snapshot(tmp_path)
    previous = _publish(cache)
    root, inspection, bindings = _bundle(
        snapshot,
        database,
        checksum,
        payloads={"1ABC": _compressed_mmcif("1ABC", "FGHI")} if mixed else None,
    )
    inventory, original_report = authenticate_inspection(
        snapshot,
        inspection,
        expected_inventory_sha256=checksum,
        expected_inspection_sha256=sha256_file(inspection),
    )
    record = LocalRunRecord(
        NEW_RUN_ID, "marmic", COMMIT, "2" * 32, "m6-native-control", 1, None
    )
    original = LocalRunRecord(
        inventory.run_id, "marmic", COMMIT, "1" * 32, "m6-native-control", 1, None
    )
    archive = tmp_path / "coordinates.tar"
    manifest = build_prefetch_archive(
        root,
        archive,
        snapshot=snapshot,
        inspection_path=inspection,
        confirmed_manifest_sha256=bindings["expected_manifest_sha256"],
        confirmed_inventory_sha256=checksum,
        confirmed_inspection_sha256=sha256_file(inspection),
    )
    plan = prevalidate_proposed_cache(root, snapshot, database, inspection, **bindings)
    _publish_plan(plan)
    post = inspect_coordinate_cache(
        snapshot, database, expected_inventory_sha256=checksum
    )
    bundle = {
        "schema_version": "1.0",
        "adapter_version": "m6-coordinate-import-bundle-v1",
        "run_id": record.run_id,
        "commit": record.commit,
        "request_run_id": original.run_id,
        "producer_commit": original.commit,
        "request_inventory_sha256": checksum,
        "request_inventory_id": inventory.inventory_id,
        "inspection_sha256": sha256_file(inspection),
        "inspection_id": original_report.inspection_id,
        "database_manifest_sha256": inventory.database_manifest_sha256,
        "prefetch_manifest_sha256": bindings["expected_manifest_sha256"],
        "prefetch_id": manifest.prefetch_id,
        "archive_sha256": sha256_file(archive),
        "archive_size_bytes": archive.stat().st_size,
        "imported_coordinates": {
            value.source_id.upper(): value.as_json() for _, value in plan.coordinates
        },
        "total_coordinate_bytes": manifest.total_size_bytes,
        "imported_at": "2026-09-12T06:00:00Z",
        "network_acquisition_performed": False,
        "cache_import_performed": True,
        "status": "complete",
    }
    return {
        "snapshot": snapshot,
        "database": database,
        "root": root,
        "inspection": inspection,
        "bindings": bindings,
        "record": record,
        "original": original,
        "archive": archive,
        "manifest": manifest,
        "inventory": inventory,
        "original_report": original_report,
        "post": post,
        "bundle": bundle,
        "previous": previous,
    }


def _response(fixture: dict[str, Any], path: Path) -> None:
    report = fixture["post"]
    _identity(report, "inspection_id", "m6cache_")
    payload = (canonical_json_text(report) + "\n").encode("ascii")
    bundle = fixture["bundle"]
    bundle["postinspection_sha256"] = hashlib.sha256(payload).hexdigest()
    bundle["postinspection_size_bytes"] = len(payload)
    bundle["postinspection_id"] = report["inspection_id"]
    _identity(bundle, "bundle_id", "m6coordimport_")
    path.write_bytes(
        _archive(
            {
                "postinspection.json": payload,
                "import_bundle.json": (canonical_json_text(bundle) + "\n").encode(
                    "ascii"
                ),
            }
        )
    )


def _validate(fixture: dict[str, Any], tmp_path: Path) -> dict[str, object]:
    response = tmp_path / "response.tar.gz"
    _response(fixture, response)
    return validate_import_response(
        response,
        tmp_path / "response-payload",
        snapshot=fixture["snapshot"],
        inspection_path=fixture["inspection"],
        bundle_root=fixture["root"],
        upload_archive=fixture["archive"],
        record=fixture["record"],
        request_record=fixture["original"],
        confirmed_manifest_sha256=fixture["bindings"]["expected_manifest_sha256"],
        confirmed_inventory_sha256=fixture["bindings"]["expected_inventory_sha256"],
        confirmed_inspection_sha256=fixture["bindings"]["expected_inspection_sha256"],
    )


def test_complete_import_checks_actual_coordinates_and_every_mapping(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    result = _validate(fixture, tmp_path)
    assert result["imported_object_count"] == 2
    assert result["requested_mapping_count"] == 6
    assert result["missing_mapping_count"] == 0
    assert result["cache_import_performed"] is True
    assert result["native_control_accepted"] is False
    assert "mappings" not in json.dumps(result)


@pytest.mark.parametrize(
    "field",
    [
        "run_id",
        "commit",
        "request_run_id",
        "producer_commit",
        "request_inventory_sha256",
        "request_inventory_id",
        "inspection_sha256",
        "inspection_id",
        "database_manifest_sha256",
        "prefetch_manifest_sha256",
        "prefetch_id",
        "archive_sha256",
        "archive_size_bytes",
        "total_coordinate_bytes",
        "network_acquisition_performed",
        "cache_import_performed",
        "status",
        "imported_at",
    ],
)
def test_self_consistent_wrong_bundle_binding_is_rejected(
    tmp_path: Path, field: str
) -> None:
    fixture = _fixture(tmp_path)
    value = fixture["bundle"][field]
    if type(value) is bool:
        changed: Any = not value
    elif type(value) is int:
        changed = value + 1
    else:
        changed = "0" * len(value)
    fixture["bundle"][field] = changed
    with pytest.raises((ValidationError, ModelValidationError)):
        _validate(fixture, tmp_path)


@pytest.mark.parametrize(
    "field",
    [
        "source_url",
        "requested_url",
        "retrieved_at",
        "etag",
        "last_modified",
        "content_type",
        "object_sha256",
        "size_bytes",
        "metadata_relative_path",
    ],
)
def test_imported_provenance_cannot_be_relabelled(tmp_path: Path, field: str) -> None:
    fixture = _fixture(tmp_path)
    record = next(iter(fixture["bundle"]["imported_coordinates"].values()))
    record[field] = record[field] + 1 if type(record[field]) is int else "changed"
    with pytest.raises((ValidationError, ModelValidationError)):
        _validate(fixture, tmp_path)


@pytest.mark.parametrize(
    "mutation", ["order", "new_entity", "old_entity", "missing_object"]
)
def test_mapping_and_complete_object_inventory_are_checked(
    tmp_path: Path, mutation: str
) -> None:
    fixture = _fixture(tmp_path)
    case = fixture["post"]["cases"][CASES[0]]
    if mutation == "order":
        case["mappings"].reverse()
    elif mutation == "new_entity":
        case["mappings"][1]["entity_id"] = "invented_entity"
    elif mutation == "old_entity":
        case["mappings"][0]["entity_id"] = "invented_entity"
    else:
        fixture["bundle"]["imported_coordinates"].pop("2ABC")
    with pytest.raises(ValidationError):
        _validate(fixture, tmp_path)


def test_missing_case_cannot_falsely_claim_other_cases_older_coordinate(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, mixed=True)
    previous = fixture["previous"]
    post = fixture["post"]
    mapping = post["cases"][CASES[1]]["mappings"][0]
    mapping["coordinate_sha256"] = previous.object_sha256
    mapping["metadata_sha256"] = previous.metadata_sha256
    post["cached_coordinates"] = {previous.metadata_sha256: previous.as_json()}
    # Sequence claims and all report IDs/checksums remain internally consistent.
    with pytest.raises(ValidationError, match="repaired mapping"):
        _validate(fixture, tmp_path)


def _storage(fixture: dict[str, Any], *, split: bool = False) -> dict[str, str]:
    reservations = coordinate_storage_reservations(
        len(fixture["original_report"].missing_pdb_ids),
        artifacts_frsize_bytes=32768,
        cache_frsize_bytes=32768,
    )
    document = {
        "schema_version": "1.0",
        "adapter_version": "m6-coordinate-storage-preflight-v2",
        "run_id": fixture["record"].run_id,
        "commit": COMMIT,
        "request_run_id": fixture["original"].run_id,
        "producer_commit": COMMIT,
        "request_inventory_sha256": fixture["bindings"]["expected_inventory_sha256"],
        "inspection_sha256": fixture["bindings"]["expected_inspection_sha256"],
        "database_manifest_sha256": fixture["inventory"].database_manifest_sha256,
        "coordinate_total_limit_bytes": 3 * 1024**3,
        "coordinate_object_limit_bytes": 128 * 1024**2,
        "additional_disk_limit_bytes": 12 * 1024**3,
        "layout": {
            "artifacts": {"device": 0, "frsize_bytes": 32768},
            "cache": {"device": 1 if split else 0, "frsize_bytes": 32768},
        },
        "filesystems": [
            {
                "device": number,
                "free_bytes": 20 * 1024**3,
                "required_bytes": amount,
            }
            for number, amount in enumerate(reservations if split else [12 * 1024**3])
        ],
        "checked_at": "2026-09-12T06:00:00Z",
    }
    _identity(document, "preflight_id", "m6coordstorage_")
    return {
        "operation": "coordinate-import-preflight",
        "run_id": fixture["record"].run_id,
        "status": "ready",
        "storage_preflight": canonical_json_text(document),
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "split",
        "full_count",
        "full_count_split",
        "free",
        "cap",
        "object_cap",
        "disk_cap",
        "device",
        "reserve",
        "reserve_shift",
        "source",
        "bool",
        "layout_missing",
        "root_device",
        "frsize_zero",
        "frsize_bool",
        "layout_over_budget",
        "old_adapter",
    ],
)
def test_storage_preflight_checks_exact_caps_and_current_filesystems(
    tmp_path: Path, mutation: str
) -> None:
    fixture = _fixture(tmp_path)
    if mutation in {"full_count", "full_count_split"}:
        # The public client passes an already authenticated report; isolate its
        # layout cardinality here, independently of scientific mapping validation.
        fixture["original_report"] = fixture["original_report"].model_copy(
            update={
                "missing_pdb_ids": [f"{index + 0x1000:04X}" for index in range(4195)]
            }
        )
    fields = _storage(
        fixture,
        split=mutation in {"split", "full_count_split", "device", "reserve_shift"},
    )
    document = json.loads(fields["storage_preflight"])
    if mutation == "free":
        document["filesystems"][0]["free_bytes"] = 0
    elif mutation == "cap":
        document["coordinate_total_limit_bytes"] += 1
    elif mutation == "object_cap":
        document["coordinate_object_limit_bytes"] += 1
    elif mutation == "disk_cap":
        document["additional_disk_limit_bytes"] += 1
    elif mutation == "device":
        document["filesystems"][1]["device"] = document["filesystems"][0]["device"]
    elif mutation == "reserve":
        document["filesystems"][0]["required_bytes"] -= 1
    elif mutation == "reserve_shift":
        document["filesystems"][0]["required_bytes"] -= 1
        document["filesystems"][1]["required_bytes"] += 1
    elif mutation == "source":
        document["commit"] = "0" * 40
    elif mutation == "bool":
        document["filesystems"][0]["free_bytes"] = True
    elif mutation == "layout_missing":
        document["layout"].pop("cache")
    elif mutation == "root_device":
        document["layout"]["artifacts"]["device"] = 99
    elif mutation == "frsize_zero":
        document["layout"]["cache"]["frsize_bytes"] = 0
    elif mutation == "frsize_bool":
        document["layout"]["cache"]["frsize_bytes"] = True
    elif mutation == "layout_over_budget":
        document["layout"]["cache"]["frsize_bytes"] = 64 * 1024**2
    elif mutation == "old_adapter":
        document["adapter_version"] = "m6-coordinate-storage-preflight-v1"
    _identity(document, "preflight_id", "m6coordstorage_")
    fields["storage_preflight"] = canonical_json_text(document)
    kwargs = {
        "record": fixture["record"],
        "request_record": fixture["original"],
        "inventory": fixture["inventory"],
        "report": fixture["original_report"],
        "inspection_sha256": fixture["bindings"]["expected_inspection_sha256"],
    }
    if mutation in {"none", "split", "full_count", "full_count_split"}:
        assert validate_storage_preflight(fields, **kwargs)["run_id"] == NEW_RUN_ID
    else:
        with pytest.raises((ValidationError, ModelValidationError)):
            validate_storage_preflight(fields, **kwargs)


@pytest.mark.parametrize(
    "operation,confirmation",
    [
        ("coordinate-prefetch", "--confirm-inspection-sha256"),
        ("coordinate-prefetch-retained", "--confirm-inspection-sha256"),
        ("coordinate-import", "--confirm-prefetch-manifest-sha256"),
    ],
)
def test_cli_accepts_only_fixed_owned_run_and_digest_options(
    operation: str, confirmation: str
) -> None:
    parser = _build_parser()
    argv = [
        operation,
        "--run-id",
        NEW_RUN_ID,
        "--request-run-id",
        NEW_RUN_ID,
        confirmation,
        "a" * 64,
    ]
    parsed = parser.parse_args(argv)
    assert not {"url", "path", "case", "budget"} & vars(parsed).keys()
    with pytest.raises(SystemExit):
        parser.parse_args([*argv, "--path", "/arbitrary"])


@pytest.mark.parametrize("failure", ["none", "stdout", "stderr", "timeout"])
def test_transport_bounds_live_response_and_preserves_partial_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    transport = SshTransport(_config(tmp_path))
    archive = tmp_path / "upload.tar"
    archive.write_bytes(b"input")
    output = tmp_path / "response.tar.gz"
    if failure == "timeout":
        script = "import time; time.sleep(5)"
        monkeypatch.setattr(client_module, "SSH_OPERATION_TIMEOUT_SECONDS", 0.05)
    elif failure == "stderr":
        script = "import sys; sys.stderr.buffer.write(b'x' * 2048)"
        monkeypatch.setattr(client_module, "MAX_LOG_BYTES", 1024)
    elif failure == "stdout":
        script = "import sys; sys.stdout.buffer.write(b'x' * 2048)"
        monkeypatch.setattr(client_module, "MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES", 1024)
    else:
        script = (
            "import sys; assert sys.stdin.buffer.read() == b'input'; "
            "sys.stdout.buffer.write(b'response')"
        )

    def command(operation: str, arguments: list[str]) -> list[str]:
        assert operation == "import-coordinate-cache"
        assert arguments == ["fixed"]
        return [sys.executable, "-c", script]

    monkeypatch.setattr(transport, "_command", command)
    if failure == "none":
        transport.coordinate_import(["fixed"], archive, output)
        assert output.read_bytes() == b"response"
    else:
        with pytest.raises(RemoteOperationError) as caught:
            transport.coordinate_import(["fixed"], archive, output)
        assert caught.value.failure_class is FailureClass.TRANSFER_FAILURE
        assert output.is_file()
        assert output.stat().st_size <= client_module.MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES


@pytest.mark.parametrize("failure", ["none", "headroom", "receipt", "transport"])
@pytest.mark.parametrize("continuation", [False, True])
def test_original_controller_prefetch_import_with_real_remote_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    continuation: bool,
) -> None:
    from genome_to_diffraction.hpc import m6_coordinate_import as remote

    if continuation:
        from tests.unit import test_m6_coordinate_requests as request_fixture

        original_catalogue = request_fixture._catalogue

        def two_templates(root: Path):
            catalogue, policy, groups = original_catalogue(root)
            # Preserve all 93 hits and producer bindings, but require two PDB entries
            # so a real first success followed by a transport failure is possible.
            hits = [
                _hit(
                    group,
                    hit_id=f"hit_{index}_{rank}",
                    rank=rank,
                    pdb_id="1ABC" if rank == 1 else "2ABC",
                    source_sequence="ACDE" if rank == 1 else "ACDF",
                    identity=sum(
                        a == b
                        for a, b in zip(
                            group.sequence, "ACDE" if rank == 1 else "ACDF", strict=True
                        )
                    )
                    / 4,
                )
                for index, group in enumerate(groups[:-1])
                for rank in (1, 2, 3)
            ]
            (policy / "policy/accepted_structural_hits.jsonl").write_text(
                "".join(canonical_json_text(hit) + "\n" for hit in hits),
                encoding="ascii",
            )
            return catalogue, policy, groups

        monkeypatch.setattr(request_fixture, "_catalogue", two_templates)
    fixture = _import_fixture(tmp_path / "remote")
    base = fixture.base
    publications = base.new / "artifacts/m6-coordinate-inspection"
    local = tmp_path / "client"
    local.mkdir()
    transfer_calls: list[tuple[str, ...]] = []
    downloads: list[Path] = []

    class BoundaryTransport(FakeTransport):
        def run(self, operation: str, arguments: Sequence[str]) -> dict[str, str]:
            assert operation == "coordinate-import-preflight"
            assert list(arguments) == [
                base.new.name,
                NEW_OWNER,
                base.old.name,
                OLD_OWNER,
                fixture.inspection_sha,
            ]
            report = remote.storage_preflight(
                base.new,
                base.old,
                new_owner=NEW_OWNER,
                old_owner=OLD_OWNER,
                inspection_sha256=fixture.inspection_sha,
            )
            return {
                "operation": operation,
                "run_id": base.new.name,
                "status": "ready",
                "storage_preflight": canonical_json_text(report),
            }

        def coordinate_import(
            self, arguments: Sequence[str], archive: Path, destination: Path
        ) -> None:
            transfer_calls.append(tuple(arguments))
            assert list(arguments[:5]) == [
                base.new.name,
                NEW_OWNER,
                base.old.name,
                OLD_OWNER,
                fixture.inspection_sha,
            ]
            if failure == "transport":
                destination.write_bytes(b"incomplete response")
                raise RemoteOperationError(
                    "simulated interrupted transport",
                    failure_class=FailureClass.TRANSFER_FAILURE,
                )
            with archive.open("rb") as source, destination.open("xb") as output:
                remote.import_coordinate_cache(
                    base.new,
                    base.old,
                    new_owner=arguments[1],
                    old_owner=arguments[3],
                    inspection_sha256=arguments[4],
                    archive_sha256=arguments[5],
                    archive_size_bytes=int(arguments[6]),
                    prefetch_manifest_sha256=arguments[7],
                    request_stream=source,
                    response_stream=output,
                )

    controller = _controller(local, BoundaryTransport())
    commit_sources = {}
    for run, owner in ((base.new, NEW_OWNER), (base.old, OLD_OWNER)):
        commit = json.loads((run / "manifest.json").read_text())["commit"]
        record = LocalRunRecord(
            run.name, "marmic", commit, owner, "m6-native-control", 1, None
        )
        record.write(controller.config.local_state_root)
        commit_sources[commit] = run / "source"
    monkeypatch.setattr(
        controller.git,
        "read_file_at_commit",
        lambda commit, path: (commit_sources[commit] / path).read_bytes(),
    )
    parent = controller.config.local_state_root / base.new.name
    snapshot = (
        controller.config.local_state_root / base.old.name / "coordinate-requests"
    )
    shutil.copytree(publications / "request-snapshot", snapshot)
    inspection_root = parent / "coordinate-inspection"
    inspection_root.mkdir()
    for name in ("inspection.json", "inspection_bundle.json"):
        shutil.copy2(publications / name, inspection_root / name)

    continuation_kwargs: dict[str, str] = {}
    failed_parent = None
    retained_before = None
    http_calls = None
    if continuation:
        from genome_to_diffraction.databases.common import DatabaseError

        current = controller._owned_run(base.new.name)
        failed = replace(
            current, run_id=current.run_id[:-8] + "33333333", owner_id="3" * 32
        )
        failed.write(controller.config.local_state_root)
        failed_parent = controller.config.local_state_root / failed.run_id
        failed_inspection = failed_parent / "coordinate-inspection"
        shutil.copytree(inspection_root, failed_inspection)
        binding_path = failed_inspection / "inspection_bundle.json"
        binding = json.loads(binding_path.read_text())
        binding["run_id"] = failed.run_id
        _identity(binding, "bundle_id", "m6inspect_")
        atomic_write_json(binding_path, binding)
        historical = remote.storage_preflight(
            base.new,
            base.old,
            new_owner=NEW_OWNER,
            old_owner=OLD_OWNER,
            inspection_sha256=fixture.inspection_sha,
        )
        historical["run_id"] = failed.run_id
        _identity(historical, "preflight_id", "m6coordstorage_")
        atomic_write_json(
            failed_parent / "coordinate-prefetch-storage.json", historical
        )
        calls, _ = _http(monkeypatch, fail_open_pdb_id="2ABC")
        with pytest.raises(DatabaseError, match="Connection reset by peer"):
            acquire_coordinate_prefetch(
                snapshot,
                failed_inspection / "inspection.json",
                failed_parent / "coordinate-prefetch",
                expected_inventory_sha256=base.inventory_sha256,
                expected_inspection_sha256=fixture.inspection_sha,
            )
        assert calls == ["1ABC", "2ABC"]
        retained_before = _file_digests(failed_parent)
        inspected = controller.coordinate_prefetch_retained(
            failed.run_id,
            request_run_id=base.old.name,
            confirm_inspection_sha256=fixture.inspection_sha,
        )
        assert inspected["retained_object_count"] == 1
        assert inspected["network_acquisition_performed"] is False
        assert _file_digests(failed_parent) == retained_before
        continuation_kwargs = {
            "continue_from_run_id": failed.run_id,
            "confirm_retained_prefetch_sha256": str(
                inspected["retained_prefetch_sha256"]
            ),
        }
        http_calls, _ = _http(monkeypatch)
        with pytest.raises(ValidationError, match="exact retained"):
            controller.coordinate_prefetch(
                base.new.name,
                request_run_id=base.old.name,
                confirm_inspection_sha256=fixture.inspection_sha,
                continue_from_run_id=failed.run_id,
                confirm_retained_prefetch_sha256="0" * 64,
            )
        assert http_calls == []
        assert not (parent / "coordinate-prefetch-storage.json").exists()

    def acquire(
        snapshot_path: Path, inspection_path: Path, staging_root: Path, **kwargs: Any
    ) -> Path:
        assert (parent / "coordinate-prefetch-storage.json").is_file()
        assert snapshot_path == snapshot
        assert inspection_path == inspection_root / "inspection.json"
        assert kwargs["expected_inventory_sha256"] == base.inventory_sha256
        assert kwargs["expected_inspection_sha256"] == fixture.inspection_sha
        downloads.append(staging_root)
        if continuation:
            return acquire_coordinate_prefetch(
                snapshot_path, inspection_path, staging_root, **kwargs
            )
        staging_root.mkdir()
        shutil.copytree(
            tmp_path / "remote/local-prefetch-builder/prefetch bundle",
            staging_root / "bundle",
        )
        return staging_root / "bundle/prefetch_manifest.json"

    monkeypatch.setattr(client_module, "acquire_coordinate_prefetch", acquire)
    if failure == "headroom":
        monkeypatch.setattr(
            remote,
            "_filesystem",
            lambda path: (path.stat().st_dev, path.stat().st_ino, 0),
        )
        with pytest.raises(ValidationError, match="headroom"):
            controller.coordinate_prefetch(
                base.new.name,
                request_run_id=base.old.name,
                confirm_inspection_sha256=fixture.inspection_sha,
                **continuation_kwargs,
            )
        assert not downloads and not transfer_calls
        assert not (parent / "coordinate-prefetch").exists()
        return
    prefetched = controller.coordinate_prefetch(
        base.new.name,
        request_run_id=base.old.name,
        confirm_inspection_sha256=fixture.inspection_sha,
        **continuation_kwargs,
    )
    assert len(downloads) == 1
    assert prefetched["cache_import_performed"] is False
    assert not (base.new / "state/job-id").exists()
    if continuation:
        assert failed_parent is not None
        assert http_calls == ["2ABC"]
        assert _file_digests(failed_parent) == retained_before
    if failure == "receipt":
        receipt_path = (
            parent
            / "coordinate-prefetch"
            / ("retained-prefetch.json" if continuation else "prefetch_receipt.json")
        )
        receipt = json.loads(receipt_path.read_text())
        if continuation:
            receipt["objects"]["1ABC"]["etag"] = '"changed-original-provenance"'
        else:
            receipt["archive_sha256"] = "0" * 64
            _identity(receipt, "receipt_id", "m6coordprefetch_")
        atomic_write_json(receipt_path, receipt)
    arguments = {
        "request_run_id": base.old.name,
        "confirm_prefetch_manifest_sha256": str(prefetched["prefetch_manifest_sha256"]),
    }
    if failure == "none":
        imported = controller.coordinate_import(base.new.name, **arguments)
        assert imported["missing_mapping_count"] == 0
        assert imported["cache_import_performed"] is True
        assert imported["native_control_accepted"] is False
        assert (parent / "coordinate-import/verified/import_bundle.json").is_file()
        assert len(transfer_calls) == 1
    else:
        with pytest.raises((ValidationError, RemoteOperationError)):
            controller.coordinate_import(base.new.name, **arguments)
        assert not (parent / "coordinate-import/verified").exists()
        assert len(transfer_calls) == (1 if failure == "transport" else 0)
    if failure != "receipt":
        with pytest.raises(ValidationError, match="already has evidence"):
            controller.coordinate_import(base.new.name, **arguments)
        assert len(transfer_calls) == 1
