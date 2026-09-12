"""Confirmed continuation of a real simulated single-attempt acquisition failure."""

import fcntl
import json
import logging
import os
from dataclasses import replace
from pathlib import Path
from typing import TypedDict

import pytest
from pydantic import ValidationError as ModelValidationError

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.databases.common import DatabaseError, StorageLimitError
from genome_to_diffraction.hpc import m6_coordinate_download as download_module
from genome_to_diffraction.hpc.m6_coordinate_continuation import (
    RetainedPrefetch,
    inspect_retained_prefetch,
)
from genome_to_diffraction.hpc.m6_coordinate_download import acquire_coordinate_prefetch
from genome_to_diffraction.hpc.models import LocalRunRecord, ValidationError
from genome_to_diffraction.structure_search.pdb_coordinates import (
    PdbCoordinateParseError,
)
from tests.unit.test_m6_coordinate_cache import _file_digests
from tests.unit.test_m6_coordinate_download import Inputs, _acquire, _http, _inputs
from tests.unit.test_pdb_coordinates import _compressed_mmcif


class _InspectionArguments(TypedDict):
    record: LocalRunRecord
    request_record: LocalRunRecord
    expected_inventory_sha256: str
    expected_inspection_sha256: str


def _failed_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Inputs, Path, RetainedPrefetch, _InspectionArguments]:
    inputs = _inputs(tmp_path)
    calls, _ = _http(monkeypatch, fail_open_pdb_id="3ABC")
    root = tmp_path / "failed-acquisition"
    with pytest.raises(DatabaseError, match="Connection reset by peer"):
        _acquire(inputs, root)
    assert calls == ["2ABC", "3ABC"]
    inventory = json.loads((inputs.snapshot / "request_inventory.json").read_text())
    original = LocalRunRecord(
        inventory["run_id"], "marmic", "1" * 40, "a" * 32, "m6-native-control", 1, None
    )
    failed = LocalRunRecord(
        "gtd-m6-native-control-20260912T130000Z-" + "2" * 12 + "-01234567",
        "marmic",
        "2" * 40,
        "b" * 32,
        "m6-native-control",
        1,
        None,
    )
    arguments: _InspectionArguments = dict(
        record=failed,
        request_record=original,
        expected_inventory_sha256=inputs.inventory_sha256,
        expected_inspection_sha256=inputs.inspection_sha256,
    )
    retained = inspect_retained_prefetch(
        root, inputs.snapshot, inputs.inspection, **arguments
    )
    return inputs, root, retained, arguments


def test_confirmed_continuation_downloads_only_remaining_and_preserves_failed_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(
        logging.INFO, logger="genome_to_diffraction.hpc.m6_coordinate_download"
    )
    inputs, failed, retained, _ = _failed_prefix(tmp_path, monkeypatch)
    before = _file_digests(failed)
    assert list(retained.objects) == ["2ABC"]
    assert retained.failed_request_pdb_id == "3ABC"
    calls, _ = _http(monkeypatch)
    monkeypatch.setattr(download_module, "utc_now_iso", lambda: "2026-09-13T09:00:00Z")
    destination = tmp_path / "continued-acquisition"
    manifest_path = acquire_coordinate_prefetch(
        inputs.snapshot,
        inputs.inspection,
        destination,
        expected_inventory_sha256=inputs.inventory_sha256,
        expected_inspection_sha256=inputs.inspection_sha256,
        retained_source=failed,
        retained=retained,
        confirmed_retained_sha256=retained.checksum(),
    )
    manifest = json.loads(manifest_path.read_text())
    assert calls == ["3ABC"]
    assert set(manifest["objects"]) == {"2ABC", "3ABC"}
    assert manifest["objects"]["2ABC"] == retained.objects["2ABC"].model_dump(
        mode="json"
    )
    assert manifest["objects"]["3ABC"]["retrieved_at"] == "2026-09-13T09:00:00Z"
    assert _file_digests(failed) == before
    copied = manifest_path.parent / "objects/2abc.cif.gz"
    original = failed / ".pending-bundle/objects/2abc.cif.gz"
    assert sha256_file(copied) == sha256_file(original)
    assert copied.stat().st_ino != original.stat().st_ino
    assert copied.stat().st_nlink == original.stat().st_nlink == 1
    assert (destination / "retained-prefetch.json").is_file()


@pytest.mark.parametrize(
    "mutation",
    [
        "object",
        "retrieval_sha",
        "retrieval_url",
        "request_url",
        "timestamp",
        "limit",
        "boolean_limit",
        "missing_set",
        "adapter",
        "unknown_file",
        "partial",
        "finished",
        "gap",
        "symlink",
        "hardlink",
        "request_source",
    ],
)
def test_retained_inspection_rejects_changed_unsafe_or_incomplete_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    inputs, failed, _, arguments = _failed_prefix(tmp_path, monkeypatch)
    object_path = failed / ".pending-bundle/objects/2abc.cif.gz"
    if mutation == "object":
        object_path.write_bytes(b"changed")
    elif mutation.startswith("retrieval_") or mutation == "timestamp":
        path = failed / "retrievals/2abc.retrieval.json"
        document = json.loads(path.read_text())
        if mutation == "retrieval_sha":
            document["sha256"] = "0" * 64
        elif mutation == "retrieval_url":
            document["url"] = "https://other.invalid/object"
        else:
            document["retrieved_at"] = "2026-09-12T08:59:59Z"
        atomic_write_json(path, document)
    elif mutation == "request_url":
        path = failed / "retrievals/3abc.request.json"
        document = json.loads(path.read_text())
        document["requested_url"] = "https://other.invalid/object"
        atomic_write_json(path, document)
    elif mutation in {"limit", "boolean_limit", "missing_set", "adapter"}:
        path = failed / "acquisition.json"
        document = json.loads(path.read_text())
        if mutation == "limit":
            document["object_limit_bytes"] += 1
        elif mutation == "boolean_limit":
            document["http_concurrency"] = True
        elif mutation == "missing_set":
            document["missing_pdb_ids"] = ["2ABC"]
        else:
            document["adapter_version"] = "unqualified-version"
        atomic_write_json(path, document)
    elif mutation == "unknown_file":
        (failed / "unrequested.json").write_text("{}\n")
    elif mutation == "partial":
        (failed / "incoming/.3abc.cif.gz.partial").write_bytes(b"partial")
    elif mutation == "finished":
        (failed / "bundle").mkdir()
    elif mutation == "gap":
        object_path.rename(object_path.with_name("3abc.cif.gz"))
    elif mutation == "symlink":
        external = tmp_path / "external.cif.gz"
        object_path.rename(external)
        object_path.symlink_to(external)
    elif mutation == "hardlink":
        os.link(object_path, tmp_path / "other-link.cif.gz")
    elif mutation == "request_source":
        arguments["request_record"] = replace(
            arguments["request_record"], commit="0" * 40
        )
    calls, _ = _http(monkeypatch)
    with pytest.raises((ValidationError, ModelValidationError)):
        inspect_retained_prefetch(
            failed, inputs.snapshot, inputs.inspection, **arguments
        )
    assert calls == []


def test_retained_inspection_refuses_an_active_download_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, failed, _, arguments = _failed_prefix(tmp_path, monkeypatch)
    lock = next((failed / "tmp/download-locks").iterdir())
    with lock.open("rb") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValidationError, match="active download lock"):
            inspect_retained_prefetch(
                failed, inputs.snapshot, inputs.inspection, **arguments
            )


@pytest.mark.parametrize("mutation", ["confirmation", "provenance", "source_bytes"])
def test_continuation_rejects_changed_confirmation_before_staging_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    inputs, failed, retained, _ = _failed_prefix(tmp_path, monkeypatch)
    confirmed = retained.checksum()
    if mutation == "confirmation":
        confirmed = "0" * 64
    elif mutation == "source_bytes":
        (failed / ".pending-bundle/objects/2abc.cif.gz").write_bytes(b"changed")
    else:
        path = failed / "retrievals/2abc.retrieval.json"
        document = json.loads(path.read_text())
        document["etag"] = '"changed-original-provenance"'
        atomic_write_json(path, document)
    calls, _ = _http(monkeypatch)
    destination = tmp_path / "new-acquisition"
    with pytest.raises(ValidationError, match="changed"):
        acquire_coordinate_prefetch(
            inputs.snapshot,
            inputs.inspection,
            destination,
            expected_inventory_sha256=inputs.inventory_sha256,
            expected_inspection_sha256=inputs.inspection_sha256,
            retained_source=failed,
            retained=retained,
            confirmed_retained_sha256=confirmed,
        )
    assert calls == []
    assert not destination.exists()


@pytest.mark.parametrize("boundary", ["after_copy", "after_download"])
def test_retained_source_rechecked_across_copy_and_acquisition_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    inputs, failed, retained, _ = _failed_prefix(tmp_path, monkeypatch)
    calls, _ = _http(monkeypatch)
    original_verify = download_module.verify_retained_prefetch
    verifications = 0

    def mutate_before_verification(root: Path, expected: RetainedPrefetch) -> None:
        nonlocal verifications
        verifications += 1
        if verifications == (2 if boundary == "after_copy" else 3):
            atomic_write_json(root / "retrievals/2abc.request.json", {"tampered": True})
        original_verify(root, expected)

    monkeypatch.setattr(
        download_module, "verify_retained_prefetch", mutate_before_verification
    )
    destination = tmp_path / "new-acquisition"
    with pytest.raises(ValidationError, match="changed"):
        acquire_coordinate_prefetch(
            inputs.snapshot,
            inputs.inspection,
            destination,
            expected_inventory_sha256=inputs.inventory_sha256,
            expected_inspection_sha256=inputs.inspection_sha256,
            retained_source=failed,
            retained=retained,
            confirmed_retained_sha256=retained.checksum(),
        )
    assert calls == ([] if boundary == "after_copy" else ["3ABC"])
    assert not (destination / "bundle").exists()


@pytest.mark.parametrize("invalid", ["gzip", "mapping"])
def test_retained_objects_still_require_full_gzip_and_frozen_mapping_qualification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    inputs, failed, _, arguments = _failed_prefix(tmp_path, monkeypatch)
    path = failed / ".pending-bundle/objects/2abc.cif.gz"
    path.write_bytes(
        b"not-gzip" if invalid == "gzip" else _compressed_mmcif("2ABC", "ACDE")
    )
    retrieval_path = failed / "retrievals/2abc.retrieval.json"
    retrieval = json.loads(retrieval_path.read_text())
    retrieval.update(sha256=sha256_file(path), size_bytes=path.stat().st_size)
    atomic_write_json(retrieval_path, retrieval)
    retained = inspect_retained_prefetch(
        failed, inputs.snapshot, inputs.inspection, **arguments
    )
    before = _file_digests(failed)
    calls, _ = _http(monkeypatch)
    destination = tmp_path / "new-acquisition"
    with pytest.raises(
        (ValidationError, PdbCoordinateParseError), match=r"gzip|SEQRES"
    ):
        acquire_coordinate_prefetch(
            inputs.snapshot,
            inputs.inspection,
            destination,
            expected_inventory_sha256=inputs.inventory_sha256,
            expected_inspection_sha256=inputs.inspection_sha256,
            retained_source=failed,
            retained=retained,
            confirmed_retained_sha256=retained.checksum(),
        )
    assert calls == ["3ABC"]
    assert _file_digests(failed) == before


def test_failed_continuation_preserves_both_attempts_and_cannot_chain_or_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, failed, retained, arguments = _failed_prefix(tmp_path, monkeypatch)
    original_before = _file_digests(failed)
    calls, _ = _http(monkeypatch, fail_open_pdb_id="3ABC")
    destination = tmp_path / "new-acquisition"

    def continue_once() -> Path:
        return acquire_coordinate_prefetch(
            inputs.snapshot,
            inputs.inspection,
            destination,
            expected_inventory_sha256=inputs.inventory_sha256,
            expected_inspection_sha256=inputs.inspection_sha256,
            retained_source=failed,
            retained=retained,
            confirmed_retained_sha256=retained.checksum(),
        )

    with pytest.raises(DatabaseError, match="after 1 attempts"):
        continue_once()
    after = _file_digests(destination)
    with pytest.raises(ValidationError, match="already exists"):
        continue_once()
    with pytest.raises(ValidationError):
        inspect_retained_prefetch(
            destination, inputs.snapshot, inputs.inspection, **arguments
        )
    assert calls == ["3ABC"]
    assert _file_digests(failed) == original_before
    assert _file_digests(destination) == after
    assert not (destination / "bundle").exists()
    assert not (destination / "bundle").exists()


def test_continuation_cannot_reset_the_additional_disk_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, failed, retained, _ = _failed_prefix(tmp_path, monkeypatch)
    before = _file_digests(failed)
    calls, _ = _http(monkeypatch)
    monkeypatch.setattr(
        download_module, "MAX_ADDITIONAL_DISK_BYTES", retained.allocated_bytes
    )
    destination = tmp_path / "new-acquisition"
    with pytest.raises(StorageLimitError, match="retained evidence"):
        acquire_coordinate_prefetch(
            inputs.snapshot,
            inputs.inspection,
            destination,
            expected_inventory_sha256=inputs.inventory_sha256,
            expected_inspection_sha256=inputs.inspection_sha256,
            retained_source=failed,
            retained=retained,
            confirmed_retained_sha256=retained.checksum(),
        )
    assert calls == []
    assert _file_digests(failed) == before
