"""Original-client complete-request transport and fail-closed report publication."""

import hashlib
import io
import json
import subprocess
import tarfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.cli import _build_parser
from genome_to_diffraction.hpc.client import (
    P0_INPUT_STAGE_TIMEOUT_SECONDS,
    HpcController,
    SshTransport,
)
from genome_to_diffraction.hpc.m6_coordinate_cache import inspect_coordinate_cache
from genome_to_diffraction.hpc.m6_coordinate_inspection_client import (
    _extract_response,
    build_request_archive,
)
from genome_to_diffraction.hpc.m6_coordinate_requests import (
    CASES,
    COLLECTION,
    extract_request_archive,
    freeze_request_inventory,
)
from genome_to_diffraction.hpc.models import (
    FailureClass,
    LocalRunRecord,
    RemoteOperationError,
    ValidationError,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from tests.unit.test_hpc_client import (
    COMMIT,
    FakeTransport,
    _archive,
    _config,
    _controller,
)
from tests.unit.test_m6_coordinate_cache import _freeze, _publish, _snapshot
from tests.unit.test_m6_coordinate_requests import RUN_ID
from tests.unit.test_m6_coordinate_requests import _snapshot as _producer_snapshot

NEW_RUN_ID = f"gtd-m6-native-control-20260912T130000Z-{COMMIT[:12]}-89abcdef"


class InspectionTransport(FakeTransport):
    def __init__(self, report: dict[str, Any], *, corruption: str = "") -> None:
        super().__init__()
        self.report = report
        self.corruption = corruption
        self.upload_names: list[str] = []

    def coordinate_inspect(
        self, arguments: Sequence[str], archive: Path, destination: Path
    ) -> None:
        self.calls.append(("inspect-coordinate-cache", tuple(arguments)))
        with tarfile.open(archive, "r:gz") as handle:
            self.upload_names = handle.getnames()
        report = json.loads(json.dumps(self.report))
        case = report["cases"][CASES[0]]
        if self.corruption == "order":
            case["mappings"].reverse()
        elif self.corruption == "missing":
            case["missing_mapping_count"] += 1
        elif self.corruption == "missing-union":
            report["missing_pdb_ids"] = []
        elif self.corruption == "target":
            case["mappings"][0]["target_sequence_sha256"] = "0" * 64
        elif self.corruption == "source-sequence":
            case["mappings"][0]["source_sequence_sha256"] = "0" * 64
        elif self.corruption == "fabricated":
            case["mappings"][1]["coordinate_sha256"] = "0" * 64
        elif self.corruption == "coordinate-path":
            next(iter(report["cached_coordinates"].values()))[
                "object_relative_path"
            ] = "../outside.cif.gz"
        elif self.corruption == "database":
            report["database_manifest_sha256"] = "0" * 64
        elif self.corruption == "truthy-count":
            case["cached_mapping_count"] = True
        elif self.corruption == "network":
            report["network_acquisition_performed"] = True
        report.pop("inspection_id")
        report["inspection_id"] = content_id("m6cache_", report)
        if self.corruption == "report-id":
            report["inspection_id"] = "m6cache_bad"
        payload = (canonical_json_text(report) + "\n").encode("ascii")
        bundle = {
            "schema_version": "1.0",
            "adapter_version": "m6-coordinate-inspection-bundle-v1",
            "run_id": arguments[0],
            "commit": COMMIT,
            "request_run_id": arguments[2],
            "producer_commit": COMMIT,
            "request_archive_sha256": arguments[4],
            "request_archive_size_bytes": int(arguments[5]),
            "request_inventory_sha256": arguments[6],
            "request_inventory_id": report["request_inventory_id"],
            "database_manifest_sha256": report["database_manifest_sha256"],
            "inspection_sha256": hashlib.sha256(payload).hexdigest(),
            "inspection_size_bytes": len(payload),
            "inspection_id": report["inspection_id"],
            "inspected_at": "2026-09-12T04:00:00Z",
            "network_acquisition_performed": False,
            "cache_import_performed": False,
        }
        if self.corruption == "run":
            bundle["run_id"] = RUN_ID
        elif self.corruption == "source":
            bundle["commit"] = "0" * 40
        elif self.corruption == "archive":
            bundle["request_archive_sha256"] = "0" * 64
        elif self.corruption == "timestamp":
            bundle["inspected_at"] = "2026-09-12T04:00:00"
        elif self.corruption == "report-sha":
            bundle["inspection_sha256"] = "0" * 64
        bundle["bundle_id"] = content_id("m6inspect_", bundle)
        if self.corruption == "bundle-id":
            bundle["bundle_id"] = "m6inspect_bad"
        destination.write_bytes(
            _archive(
                {
                    "inspection.json": payload,
                    "inspection_bundle.json": (
                        canonical_json_text(bundle) + "\n"
                    ).encode("ascii"),
                }
            )
        )


def _inspection_controller(
    tmp_path: Path, *, corruption: str = ""
) -> tuple[HpcController, InspectionTransport, str, str, Path]:
    snapshot, database, cache, _ = _snapshot(tmp_path)
    _publish(cache)
    inventory = json.loads((snapshot / "request_inventory.json").read_text())
    request_run_id = inventory["run_id"]
    (snapshot / "manifest.json").write_text("{}\n", encoding="ascii")
    atomic_write_json(
        snapshot / COLLECTION,
        {
            "schema_version": "1.0",
            "adapter_version": "m6-coordinate-request-collection-v1",
            "run_id": request_run_id,
            "remote_run_root": f"/owned/runs/{request_run_id}",
            "files": {
                "manifest.json": {
                    "sha256": sha256_file(snapshot / "manifest.json"),
                    "size_bytes": 3,
                }
            },
        },
    )
    for name in ("manifest.json", COLLECTION):
        inventory["input_and_request_sha256"][name] = sha256_file(snapshot / name)
    checksum = _freeze(snapshot, inventory)
    report = inspect_coordinate_cache(
        snapshot, database, expected_inventory_sha256=checksum
    )
    transport = InspectionTransport(report, corruption=corruption)
    controller = _controller(tmp_path, transport)
    for run_id in (NEW_RUN_ID, request_run_id):
        LocalRunRecord(
            run_id, "marmic", COMMIT, "1" * 32, "m6-native-control", 1, None
        ).write(controller.config.local_state_root)
    destination = (
        controller.config.local_state_root / request_run_id / "coordinate-requests"
    )
    snapshot.rename(destination)
    for relative in (
        "benchmarks/m6_nextflow.py",
        "structure_search/pdb_coordinates.py",
    ):
        path = tmp_path / "src/genome_to_diffraction" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixed selector\n", encoding="ascii")
    return controller, transport, request_run_id, checksum, destination


def _inspect(
    controller: HpcController, request_run_id: str, checksum: str
) -> dict[str, object]:
    return controller.coordinate_inspect(
        NEW_RUN_ID,
        request_run_id=request_run_id,
        confirm_request_inventory_sha256=checksum,
    )


def test_controller_publishes_verified_scalar_summary_preserving_snapshot(
    tmp_path: Path,
) -> None:
    controller, transport, old, checksum, snapshot = _inspection_controller(tmp_path)
    before = {
        str(path): sha256_file(path) for path in snapshot.rglob("*") if path.is_file()
    }
    result = _inspect(controller, old, checksum)
    assert result["missing_pdb_count"] == 2
    assert result["requested_mapping_count"] == 6
    assert result["network_acquisition_performed"] is False
    assert "mappings" not in json.dumps(result)
    assert transport.upload_names == [COLLECTION, "manifest.json"]
    arguments = transport.calls[-1][1]
    assert len(arguments) == 7
    assert arguments[:4] == (NEW_RUN_ID, "1" * 32, old, "1" * 32)
    assert arguments[-1] == checksum
    output = Path(str(result["destination"]))
    assert sorted(path.name for path in output.iterdir()) == [
        "inspection.json",
        "inspection_bundle.json",
    ]
    assert all(path.stat().st_mode & 0o222 == 0 for path in output.iterdir())
    assert before == {
        str(path): sha256_file(path) for path in snapshot.rglob("*") if path.is_file()
    }
    with pytest.raises(ValidationError, match="already exists"):
        _inspect(controller, old, checksum)
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "corruption",
    [
        "order",
        "missing",
        "missing-union",
        "target",
        "source-sequence",
        "fabricated",
        "coordinate-path",
        "database",
        "truthy-count",
        "network",
        "run",
        "source",
        "archive",
        "timestamp",
        "report-sha",
        "report-id",
        "bundle-id",
    ],
)
def test_forged_or_incomplete_report_is_not_published(
    tmp_path: Path, corruption: str
) -> None:
    controller, _, old, checksum, _ = _inspection_controller(
        tmp_path, corruption=corruption
    )
    with pytest.raises(ValidationError):
        _inspect(controller, old, checksum)
    parent = controller.config.local_state_root / NEW_RUN_ID
    assert not (parent / "coordinate-inspection").exists()
    assert not list(parent.glob(".coordinate-inspection-*"))


@pytest.mark.parametrize(
    "corruption", ["confirmation", "snapshot", "same-run", "destination-link"]
)
def test_local_preflight_fails_without_transport(
    tmp_path: Path, corruption: str
) -> None:
    controller, transport, old, checksum, snapshot = _inspection_controller(tmp_path)
    if corruption == "confirmation":
        checksum = "0" * 64
    elif corruption == "snapshot":
        (snapshot / "manifest.json").write_text("changed\n", encoding="ascii")
    elif corruption == "same-run":
        old = NEW_RUN_ID
    else:
        (
            controller.config.local_state_root / NEW_RUN_ID / "coordinate-inspection"
        ).symlink_to(tmp_path / "absent")
    with pytest.raises(ValidationError):
        _inspect(controller, old, checksum)
    assert not transport.calls


def test_request_archive_round_trip_retains_complete_producers(tmp_path: Path) -> None:
    run, original, prior = _producer_snapshot(tmp_path)
    snapshot = tmp_path / "snapshot"
    collection = extract_request_archive(original, snapshot)
    freeze_request_inventory(
        snapshot,
        collection=collection,
        prior=prior,
        remote_root=PurePosixPath(run),
        run_id=RUN_ID,
        source_commit=COMMIT,
    )
    record = LocalRunRecord(
        RUN_ID, "marmic", COMMIT, "1" * 32, "m6-native-control", 1, None
    )
    archive = tmp_path / "upload.tar.gz"
    build_request_archive(
        snapshot,
        archive,
        record=record,
        confirmed_sha256=sha256_file(snapshot / "request_inventory.json"),
    )
    extracted = tmp_path / "round-trip"
    assert extract_request_archive(archive, extracted) == collection
    assert not (extracted / "requests").exists()


@pytest.mark.parametrize(
    "bad",
    [
        "../inspection.json",
        "./inspection.json",
        "extra",
        "symlink",
        "duplicate",
        "missing",
    ],
)
def test_response_archive_rejects_unsafe_or_inexact_inventory(
    tmp_path: Path, bad: str
) -> None:
    archive = tmp_path / "response.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for name in ["inspection.json", "inspection_bundle.json"]:
            member = tarfile.TarInfo(name)
            member.size = 3
            handle.addfile(member, io.BytesIO(b"{}\n"))
            if bad == "missing":
                break
        if bad != "missing":
            member = tarfile.TarInfo(
                "inspection.json" if bad in {"symlink", "duplicate"} else bad
            )
            if bad == "symlink":
                member.type = tarfile.SYMTYPE
                member.linkname = "/outside"
                handle.addfile(member)
            else:
                member.size = 3
                handle.addfile(member, io.BytesIO(b"{}\n"))
    with pytest.raises(ValidationError):
        _extract_response(archive, tmp_path / "response")


def test_cli_only_accepts_owned_runs_and_explicit_checksum() -> None:
    parser = _build_parser()
    argv = [
        "coordinate-inspect",
        "--run-id",
        NEW_RUN_ID,
        "--request-run-id",
        RUN_ID,
        "--confirm-request-inventory-sha256",
        "a" * 64,
    ]
    parsed = parser.parse_args(argv)
    assert parsed.request_run_id == RUN_ID
    assert not {"url", "path", "case", "coordinates"} & vars(parsed).keys()
    with pytest.raises(SystemExit):
        parser.parse_args([*argv, "--path", "/arbitrary"])


@pytest.mark.parametrize("timeout", [False, True])
def test_transport_streams_fixed_operation_with_bounded_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout: bool
) -> None:
    archive = tmp_path / "upload.tar.gz"
    archive.write_bytes(b"request bytes")
    destination = tmp_path / "response.tar.gz"
    arguments = [NEW_RUN_ID, "1" * 32, RUN_ID, "1" * 32, "a" * 64, "13", "b" * 64]

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert "inspect-coordinate-cache" in command[-1]
        assert kwargs["timeout"] == P0_INPUT_STAGE_TIMEOUT_SECONDS == 900
        assert kwargs["stdin"].read() == b"request bytes"
        assert "input" not in kwargs and "capture_output" not in kwargs
        if timeout:
            raise subprocess.TimeoutExpired(command, 900)
        kwargs["stdout"].write(b"response bytes")
        return subprocess.CompletedProcess(command, 0, stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    transport = SshTransport(_config(tmp_path))
    if timeout:
        with pytest.raises(RemoteOperationError) as caught:
            transport.coordinate_inspect(arguments, archive, destination)
        assert caught.value.failure_class is FailureClass.TRANSFER_FAILURE
    else:
        transport.coordinate_inspect(arguments, archive, destination)
        assert destination.read_bytes() == b"response bytes"
