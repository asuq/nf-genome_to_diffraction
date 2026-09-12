"""Fixed remote bridge for read-only Marmic coordinate-cache availability.

Inputs are two authenticated native-control runs, the confirmed original producer
archive on stdin, and its byte/checksum and frozen-inventory bindings. The new run
must be staged; the original run and scientific selector bytes stay immutable.
The bridge reconstructs the complete truthless request snapshot with the existing
export adapter and inspects only the already bound cache. It never downloads,
publishes cache objects, submits jobs, or alters scientific selection.

Only the new run receives a once-published ``artifacts/m6-coordinate-inspection``
directory: ``request-snapshot/``, ``inspection.json``, and
``inspection_bundle.json``. Stdout contains a bounded gzip tar of only the latter
two files. The bundle content ID binds source/request/database/report checksums
and inspection time; it is evidence of an observation, not a durable cache key.
Failures before streaming return the fixed dispatcher's nonzero scalar protocol;
diagnostics go to stderr without capability values. The pinned Python/Gemmi runtime
and local read-only Git are required. Tests cover ownership, state, source/DB,
archive/conservation/size boundaries, immutable original evidence, and publication.
"""

import argparse
import base64
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import traceback
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.databases.cache import exclusive_lock
from genome_to_diffraction.hpc.m6_coordinate_cache import inspect_coordinate_cache
from genome_to_diffraction.hpc.m6_coordinate_requests import (
    RUNNER,
    extract_request_archive,
    freeze_request_inventory,
)
from genome_to_diffraction.hpc.models import (
    MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES,
    MAX_REVIEW_ARTIFACT_FILE_BYTES,
    MAX_REVIEW_ARTIFACT_TOTAL_BYTES,
    HpcInterfaceError,
    ValidationError,
    validate_commit,
    validate_owner_id,
    validate_run_id,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.status import GenomeToDiffractionError
from genome_to_diffraction.time import utc_now_iso

REPORT_FILES = ("inspection.json", "inspection_bundle.json")
PUBLICATION_RELATIVE = Path("artifacts/m6-coordinate-inspection")
_SELECTORS = (
    "src/genome_to_diffraction/benchmarks/m6_nextflow.py",
    "src/genome_to_diffraction/structure_search/pdb_coordinates.py",
)


class _ResponseStreamingError(OSError):
    """A validated publication exists, but its binary transfer did not finish."""


def _owned_path(root: Path, relative: str, *, directory: bool = False) -> Path:
    """Read only regular owned paths beneath an already canonical owned root."""

    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or parts.as_posix() != relative:
        raise ValidationError("coordinate inspection path is not canonical")
    current = root
    for index, part in enumerate(parts.parts):
        current /= part
        record = current.lstat()
        is_directory = index < len(parts.parts) - 1 or directory
        expected_type = stat.S_ISDIR if is_directory else stat.S_ISREG
        if not expected_type(record.st_mode) or record.st_uid != os.getuid():
            raise ValidationError(
                "coordinate inspection path is not owned and link-free"
            )
        if not is_directory and record.st_size > MAX_REVIEW_ARTIFACT_FILE_BYTES:
            raise ValidationError("coordinate inspection record exceeds its file bound")
    return current


def _text(run: Path, relative: str) -> str:
    return _owned_path(run, relative).read_text(encoding="ascii").removesuffix("\n")


def _object(run: Path, relative: str) -> dict[str, object]:
    value = load_json_document(_owned_path(run, relative))
    if not isinstance(value, dict):
        raise ValidationError("coordinate inspection record is not a JSON object")
    return value


def _run_manifest(run: Path, owner: str, *, original: bool) -> dict[str, object]:
    validate_run_id(run.name)
    validate_owner_id(owner)
    _owned_path(run.parent, run.name, directory=True)
    for relative in ("state", "source", "logs", "artifacts"):
        _owned_path(run, relative, directory=True)
    if _text(run, "state/owner-id") != owner:
        raise ValidationError("coordinate inspection ownership does not match")
    expected = {
        "profile": "m6-native-control",
        "site-id": "marmic",
        "controller-kind": "slurm_job",
        "m6-execution-purpose": "native_control",
        "m6-track": "operational",
        "phase": "completed" if original else "staged",
    }
    if any(_text(run, f"state/{name}") != value for name, value in expected.items()):
        raise ValidationError(
            "coordinate inspection run state is outside the fixed scope"
        )
    if original:
        job_id = _text(run, "state/job-id")
        result = _object(run, "state/job-result.json")
        if (
            not job_id.isdecimal()
            or int(job_id) < 1
            or type(result.get("exit_code")) is not int
            or _text(run, "state/failure-class") != "test_failure"
            or any(
                result.get(key) != value
                for key, value in {
                    "run_id": run.name,
                    "profile": "m6-native-control",
                    "job_id": job_id,
                    "exit_code": 1,
                    "failure_class": "test_failure",
                }.items()
            )
        ):
            raise ValidationError("original native control is not the recorded failure")
    else:
        for name in (
            "job-id",
            "job-result.json",
            "controller.json",
            "controller-result.json",
        ):
            marker = run / "state" / name
            if marker.exists() or marker.is_symlink():
                raise ValidationError(
                    "new coordinate inspection run has execution evidence"
                )
    commit = validate_commit(_text(run, "state/commit"))
    manifest = _object(run, "manifest.json")
    if run.name.split("-")[-2] != commit[:12] or any(
        manifest.get(key) != value
        for key, value in {
            "run_id": run.name,
            "site_id": "marmic",
            "profile": "m6-native-control",
            "controller_kind": "slurm_job",
            "commit": commit,
            "source_snapshot_status": "immutable",
        }.items()
    ):
        raise ValidationError("coordinate inspection source manifest binding changed")
    return manifest


def _git(source: Path, arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(source), *arguments],
        env={
            **{
                key: value
                for key, value in os.environ.items()
                if not key.startswith("GIT_")
            },
            "GIT_OPTIONAL_LOCKS": "0",
        },
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValidationError("coordinate inspection immutable Git source check failed")
    return result.stdout.decode("ascii").strip()


def _source_bindings(
    new: Path, old: Path, manifests: tuple[dict[str, object], ...]
) -> None:
    for run, manifest in zip((new, old), manifests, strict=True):
        source = _owned_path(run, "source", directory=True)
        _owned_path(source, ".git", directory=True)
        if _git(source, ["rev-parse", "HEAD"]) != manifest["commit"]:
            raise ValidationError("coordinate inspection Git commit changed")
        environment = _owned_path(run, "environment/.pixi", directory=True)
        if (
            not (source / ".pixi").is_symlink()
            or (source / ".pixi").resolve(strict=True) != environment
        ):
            raise ValidationError(
                "coordinate inspection owned environment link changed"
            )
        if _git(source, ["rev-parse", "--show-toplevel"]) != str(source) or _git(
            source,
            [
                "status",
                "--porcelain=v1",
                "--untracked-files=normal",
                "--",
                ".",
                ":(exclude).pixi",
            ],
        ):
            raise ValidationError("coordinate inspection source checkout changed")
        lock = sha256_file(_owned_path(source, "pixi.lock"))
        if lock != manifest.get("pixi_lock_sha256") or lock != _text(
            run, "state/pixi-lock-sha256"
        ):
            raise ValidationError("coordinate inspection locked source binding changed")
    for relative in ("pixi.lock", *_SELECTORS):
        if (
            _owned_path(new / "source", relative).read_bytes()
            != _owned_path(old / "source", relative).read_bytes()
        ):
            raise ValidationError(
                "coordinate inspection differs from original selectors or lock"
            )


def _database_binding(
    new: Path, old: Path, manifests: tuple[dict[str, object], ...]
) -> Path:
    paths = tuple(_text(run, "state/database-manifest") for run in (new, old))
    if paths[0] != paths[1] or not Path(paths[0]).is_absolute():
        raise ValidationError("coordinate inspection database paths differ")
    database = Path(paths[0])
    if database.is_symlink() or database.resolve(strict=True) != database:
        raise ValidationError("coordinate inspection database path is not link-free")
    _owned_path(database.parent, database.name)
    digest = sha256_file(database)
    for run, manifest in zip((new, old), manifests, strict=True):
        if digest != manifest.get("database_manifest_sha256") or digest != _text(
            run, "state/database-manifest-sha256"
        ):
            raise ValidationError("coordinate inspection frozen database changed")
        if sha256_file(_owned_path(run, RUNNER)) != _text(
            run, "state/m6-runner-manifest-sha256"
        ):
            raise ValidationError("coordinate inspection runner checksum changed")
    if _text(new, "state/m6-runner-manifest-sha256") != _text(
        old, "state/m6-runner-manifest-sha256"
    ):
        raise ValidationError("coordinate inspection original runner binding differs")
    return database


def _receive_archive(
    stream: BinaryIO, destination: Path, size: int, checksum: str
) -> None:
    digest = hashlib.sha256()
    remaining = size
    with destination.open("xb") as output:
        while remaining:
            chunk = stream.read(min(remaining, 1024 * 1024))
            if not chunk:
                raise ValidationError("coordinate request archive is truncated")
            output.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
        if stream.read(1):
            raise ValidationError(
                "coordinate request archive exceeds its confirmed size"
            )
    if digest.hexdigest() != checksum:
        raise ValidationError("coordinate request archive checksum changed")


def _report_archive(payload: Path, archive_path: Path) -> None:
    total = 0
    for name in REPORT_FILES:
        size = _owned_path(payload, name).stat().st_size
        if size < 1:
            raise ValidationError("coordinate inspection report is empty")
        total += size
    if total > MAX_REVIEW_ARTIFACT_TOTAL_BYTES:
        raise ValidationError("coordinate inspection report exceeds the total bound")
    with tarfile.open(archive_path, "w:gz") as archive:
        for name in REPORT_FILES:
            path = payload / name
            member = tarfile.TarInfo(name)
            member.size = path.stat().st_size
            member.mode = 0o444
            with path.open("rb") as source:
                archive.addfile(member, source)
    if archive_path.stat().st_size > MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES:
        raise ValidationError(
            "coordinate inspection response exceeds its archive bound"
        )


def inspect_owned_coordinate_cache(
    new_run: Path,
    old_run: Path,
    *,
    new_owner: str,
    old_owner: str,
    request_archive_sha256: str,
    request_archive_size_bytes: int,
    request_inventory_sha256: str,
    request_stream: BinaryIO,
    response_stream: BinaryIO,
) -> dict[str, object]:
    """Publish a fully validated new-run observation and stream only its two reports."""

    if new_run.is_symlink() or old_run.is_symlink():
        raise ValidationError("coordinate inspection run directory is a symlink")
    new, old = new_run.resolve(strict=True), old_run.resolve(strict=True)
    if new == old or new.parent != old.parent or new.parent.name != "runs":
        raise ValidationError(
            "coordinate inspection needs distinct runs in one owned namespace"
        )
    for digest in (request_archive_sha256, request_inventory_sha256):
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValidationError("coordinate inspection checksum is invalid")
    if (
        type(request_archive_size_bytes) is not int
        or not 1 <= request_archive_size_bytes <= MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES
    ):
        raise ValidationError(
            "coordinate request archive exceeds the existing byte bound"
        )
    manifests = (
        _run_manifest(new, new_owner, original=False),
        _run_manifest(old, old_owner, original=True),
    )
    _source_bindings(new, old, manifests)
    database = _database_binding(new, old, manifests)
    destination = new / PUBLICATION_RELATIVE
    lock = new / "state/m6-coordinate-inspection.lock"
    if lock.exists() or lock.is_symlink():
        _owned_path(new, "state/m6-coordinate-inspection.lock")
    with exclusive_lock(lock, progress=False):
        if destination.exists() or destination.is_symlink():
            raise ValidationError("coordinate inspection already exists; preserve it")
        with tempfile.TemporaryDirectory(
            prefix=".m6-coordinate-inspection-", dir=new / "artifacts"
        ) as temporary:
            staging = Path(temporary)
            archive_path = staging / "original-requests.tar.gz"
            _receive_archive(
                request_stream,
                archive_path,
                request_archive_size_bytes,
                request_archive_sha256,
            )
            payload = staging / "payload"
            payload.mkdir()
            snapshot = payload / "request-snapshot"
            collection = extract_request_archive(archive_path, snapshot)
            inventory = freeze_request_inventory(
                snapshot,
                collection=collection,
                prior=old,
                remote_root=PurePosixPath(old),
                run_id=old.name,
                source_commit=str(manifests[1]["commit"]),
            )
            if (
                sha256_file(snapshot / "request_inventory.json")
                != request_inventory_sha256
            ):
                raise ValidationError(
                    "reconstructed coordinate request inventory changed"
                )
            report = inspect_coordinate_cache(
                snapshot, database, expected_inventory_sha256=request_inventory_sha256
            )
            atomic_write_json(payload / "inspection.json", report)
            inspection_path = _owned_path(payload, "inspection.json")
            bundle = {
                "schema_version": "1.0",
                "adapter_version": "m6-coordinate-inspection-bundle-v1",
                "run_id": new.name,
                "commit": manifests[0]["commit"],
                "request_run_id": old.name,
                "producer_commit": manifests[1]["commit"],
                "request_archive_sha256": request_archive_sha256,
                "request_archive_size_bytes": request_archive_size_bytes,
                "request_inventory_sha256": request_inventory_sha256,
                "request_inventory_id": inventory["inventory_id"],
                "database_manifest_sha256": manifests[0]["database_manifest_sha256"],
                "inspection_sha256": sha256_file(inspection_path),
                "inspection_size_bytes": inspection_path.stat().st_size,
                "inspection_id": report["inspection_id"],
                "inspected_at": utc_now_iso(),
                "network_acquisition_performed": False,
                "cache_import_performed": False,
            }
            bundle["bundle_id"] = content_id("m6inspect_", bundle)
            atomic_write_json(payload / "inspection_bundle.json", bundle)
            response = staging / "inspection-response.tar.gz"
            _report_archive(payload, response)
            if (
                _run_manifest(new, new_owner, original=False) != manifests[0]
                or _run_manifest(old, old_owner, original=True) != manifests[1]
                or _database_binding(new, old, manifests) != database
            ):
                raise ValidationError(
                    "coordinate inspection authority changed before publication"
                )
            _source_bindings(new, old, manifests)
            for path in payload.rglob("*"):
                if path.is_file():
                    path.chmod(0o444)
            payload.rename(destination)
            try:
                with response.open("rb") as source:
                    shutil.copyfileobj(source, response_stream)
            except OSError as error:
                raise _ResponseStreamingError(
                    "coordinate inspection response transfer failed"
                ) from error
    return bundle


def main() -> int:
    """Internal fixed-dispatcher entry point; not another user-facing client."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_run", type=Path)
    parser.add_argument("new_owner")
    parser.add_argument("old_run", type=Path)
    parser.add_argument("old_owner")
    parser.add_argument("request_archive_sha256")
    parser.add_argument("request_archive_size_bytes", type=int)
    parser.add_argument("request_inventory_sha256")
    args = parser.parse_args()
    try:
        new = args.new_run.resolve(strict=True)
        expected_module = _owned_path(
            new, "source/src/genome_to_diffraction/hpc/m6_coordinate_inspection.py"
        )
        environment = _owned_path(new, "environment/.pixi", directory=True)
        if (
            Path(__file__).resolve() != expected_module
            or (new / "source/.pixi").resolve(strict=True) != environment
            or Path(sys.executable).resolve()
            != (environment / "envs/hpc/bin/python").resolve(strict=True)
        ):
            raise ValidationError(
                "coordinate inspection is not using its new pinned source/runtime"
            )
        inspect_owned_coordinate_cache(
            args.new_run,
            args.old_run,
            new_owner=args.new_owner,
            old_owner=args.old_owner,
            request_archive_sha256=args.request_archive_sha256,
            request_archive_size_bytes=args.request_archive_size_bytes,
            request_inventory_sha256=args.request_inventory_sha256,
            request_stream=sys.stdin.buffer,
            response_stream=sys.stdout.buffer,
        )
    except _ResponseStreamingError:
        traceback.print_exc(file=sys.stderr)
        return 1
    except (
        HpcInterfaceError,
        GenomeToDiffractionError,
        OSError,
        ValueError,
        tarfile.TarError,
    ):
        traceback.print_exc(file=sys.stderr)
        for key, value in (
            ("failure_class", "wrapper_failure"),
            (
                "message",
                "coordinate inspection failed; inspect the owned fixed inspection log",
            ),
        ):
            print(f"{key}\t{base64.b64encode(value.encode()).decode('ascii')}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
