"""Fixed Marmic coordinate storage preflight and once-only offline import.

Both operations authenticate a fresh staged native-control inspection and its
original failed producer. Storage preflight observes available filesystem space;
it is not a reservation or quota guarantee. The approved 12 GiB additional-disk
budget reserves the conservative artifact bound and assigns the remainder to
cache publication, admitting only layouts whose combined bounds fit the cap.
Shared devices require the sum. The client rederives the same reservations from
the authenticated missing-entry count and reported per-root fragment sizes.
Rejected layouts report the raw statvfs fragment sizes and estimated peaks in
the owned failure log. These diagnostics are not a free-space or quota guarantee.

Import accepts only the exact plain TAR manifest and missing-ID object inventory.
All objects, proposed mappings and publication destinations pass core validation
before shared writes. Per-object durable receipts, incomplete transfers and failed
attempts remain under the new run; an existing attempt cannot be retried or
overwritten. Success requires complete offline reinspection equal to the proposed
report. Only postinspection.json and import_bundle.json are returned. Source,
input, manifest and report checksums bind the bundle; no persistent validity cache
is introduced. No network, scientific scheduler or native acceptance runs here.
Pinned Python/Gemmi and read-only Git are used. Tests exercise ownership, storage,
archives, batch preflight, partial I/O evidence and complete report publication.
"""

import argparse
import base64
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import traceback
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.databases.cache import (
    CachedCoordinate,
    exclusive_lock,
    publish_pdb_coordinate,
)
from genome_to_diffraction.hpc.m6_coordinate_archive import extract_prefetch_archive
from genome_to_diffraction.hpc.m6_coordinate_cache import (
    _Inventory,
    inspect_coordinate_cache,
)
from genome_to_diffraction.hpc.m6_coordinate_inspection import (
    PUBLICATION_RELATIVE,
    _database_binding,
    _object,
    _owned_path,
    _ResponseStreamingError,
    _run_manifest,
    _source_bindings,
)
from genome_to_diffraction.hpc.m6_coordinate_inspection_client import _Bundle, _Report
from genome_to_diffraction.hpc.m6_coordinate_prefetch import (
    MAX_ADDITIONAL_DISK_BYTES,
    MAX_COORDINATE_OBJECT_BYTES,
    MAX_COORDINATE_TOTAL_BYTES,
    MAX_PREFETCH_ARCHIVE_BYTES,
    MAX_PREFETCH_MANIFEST_BYTES,
    authenticate_inspection,
    prevalidate_proposed_cache,
)
from genome_to_diffraction.hpc.m6_coordinate_storage import (
    coordinate_storage_reservations,
)
from genome_to_diffraction.hpc.models import (
    MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES,
    MAX_REVIEW_ARTIFACT_FILE_BYTES,
    MAX_REVIEW_ARTIFACT_TOTAL_BYTES,
    ValidationError,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.structure_search.pdb_coordinates import _resources
from genome_to_diffraction.time import utc_now_iso

IMPORT_RELATIVE = Path("artifacts/m6-coordinate-import")
RESPONSE_FILES = ("postinspection.json", "import_bundle.json")
_Role = Literal["artifacts", "cache"]


@dataclass(frozen=True)
class _Context:
    new: Path
    old: Path
    commit: str
    producer_commit: str
    database: Path
    snapshot: Path
    inspection: Path
    inspection_bundle_sha256: str
    inventory: _Inventory
    report: _Report
    cache_root: Path


def _context(
    new: Path, old: Path, new_owner: str, old_owner: str, inspection_sha: str
) -> _Context:
    if (
        new.is_symlink()
        or old.is_symlink()
        or re.fullmatch(r"[0-9a-f]{64}", inspection_sha) is None
    ):
        raise ValidationError("coordinate import run or inspection identity is invalid")
    new, old = new.resolve(strict=True), old.resolve(strict=True)
    if new == old or new.parent != old.parent or new.parent.name != "runs":
        raise ValidationError(
            "coordinate import needs distinct owned runs in one namespace"
        )
    manifests = (
        _run_manifest(new, new_owner, original=False),
        _run_manifest(old, old_owner, original=True),
    )
    _source_bindings(new, old, manifests)
    database = _database_binding(new, old, manifests)
    publication = _owned_path(new, PUBLICATION_RELATIVE.as_posix(), directory=True)
    inspection = _owned_path(publication, "inspection.json")
    raw_bundle = _object(publication, "inspection_bundle.json")
    bundle = _Bundle.model_validate_json(
        _owned_path(publication, "inspection_bundle.json").read_bytes(), strict=True
    )
    if (
        bundle.bundle_id
        != content_id(
            "m6inspect_",
            {key: value for key, value in raw_bundle.items() if key != "bundle_id"},
        )
        or bundle.run_id != new.name
        or bundle.commit != manifests[0]["commit"]
        or bundle.request_run_id != old.name
        or bundle.producer_commit != manifests[1]["commit"]
        or bundle.inspection_sha256 != inspection_sha
        or sha256_file(inspection) != inspection_sha
        or bundle.inspection_size_bytes != inspection.stat().st_size
        or bundle.database_manifest_sha256 != manifests[0]["database_manifest_sha256"]
    ):
        raise ValidationError(
            "coordinate import fresh inspection publication binding changed"
        )
    snapshot = _owned_path(publication, "request-snapshot", directory=True)
    inventory, report = authenticate_inspection(
        snapshot,
        inspection,
        expected_inventory_sha256=bundle.request_inventory_sha256,
        expected_inspection_sha256=inspection_sha,
    )
    if (
        bundle.inspection_id != report.inspection_id
        or bundle.request_inventory_id != inventory.inventory_id
    ):
        raise ValidationError("coordinate import inspection content identities differ")
    _, _, resource = _resources(database)
    return _Context(
        new,
        old,
        str(manifests[0]["commit"]),
        str(manifests[1]["commit"]),
        database,
        snapshot,
        inspection,
        sha256_file(publication / "inspection_bundle.json"),
        inventory,
        report,
        Path(resource.root_path).resolve(strict=True),
    )


def _filesystem(path: Path) -> tuple[int, int, int]:
    state = path.lstat()
    if not stat.S_ISDIR(state.st_mode) or state.st_uid != os.getuid():
        raise ValidationError(
            "coordinate import filesystem root is not an owned directory"
        )
    return state.st_dev, state.st_ino, shutil.disk_usage(path).free


def _allocated(path: Path) -> int:
    try:
        state = path.lstat()
    except FileNotFoundError:
        return 0
    if (
        not (stat.S_ISREG(state.st_mode) or stat.S_ISDIR(state.st_mode))
        or state.st_uid != os.getuid()
    ):
        raise ValidationError(
            "coordinate import storage accounting encountered an unsafe path"
        )
    return state.st_blocks * 512


class _Space:
    """Track allocated growth against layout-derived, fixed-total reservations."""

    def __init__(self, context: _Context):
        self.roots: dict[_Role, Path] = {
            "artifacts": context.new / "artifacts",
            "cache": context.cache_root,
        }
        self.identities = {
            role: _filesystem(path)[:2] for role, path in self.roots.items()
        }
        self.baseline: dict[_Role, dict[Path, int]] = {"artifacts": {}, "cache": {}}
        self.growth: dict[_Role, dict[Path, int]] = {"artifacts": {}, "cache": {}}
        for role, path in self.roots.items():
            self.watch(role, (path,))
        self.layout = {
            role: {
                "device": self.identities[role][0],
                "frsize_bytes": os.statvfs(path).f_frsize,
            }
            for role, path in self.roots.items()
        }
        artifact_reserve, cache_reserve = coordinate_storage_reservations(
            len(context.report.missing_pdb_ids),
            artifacts_frsize_bytes=self.layout["artifacts"]["frsize_bytes"],
            cache_frsize_bytes=self.layout["cache"]["frsize_bytes"],
        )
        self.limits: dict[_Role, int] = {
            "artifacts": artifact_reserve,
            "cache": cache_reserve,
        }

    def _paths(self, role: _Role, paths: Iterable[Path]) -> set[Path]:
        root = self.roots[role]
        result = set()
        for path in paths:
            path.relative_to(root)
            result.add(path)
            result.update(
                parent
                for parent in path.parents
                if parent == root or parent.is_relative_to(root)
            )
        return result

    def watch(self, role: _Role, paths: Iterable[Path]) -> None:
        for path in self._paths(role, paths):
            if path not in self.baseline[role]:
                self.baseline[role][path] = _allocated(path)
                self.growth[role][path] = 0

    def refresh(self, role: _Role, paths: Iterable[Path]) -> None:
        for path in self._paths(role, paths):
            self.growth[role][path] = max(
                _allocated(path) - self.baseline[role].get(path, 0), 0
            )

    def used(self, role: _Role) -> int:
        return sum(self.growth[role].values())

    def check(
        self, role: _Role | None = None, pending: int = 0
    ) -> list[dict[str, int]]:
        if pending < 0 or (role is None and pending):
            raise ValidationError("coordinate import pending storage is invalid")
        by_device: dict[int, dict[str, int]] = {}
        for name, root in self.roots.items():
            used = self.used(name)
            if used + (pending if name == role else 0) > self.limits[name]:
                raise ValidationError(
                    "coordinate import exceeds its approved additional-disk allocation"
                )
            device, inode, free = _filesystem(root)
            if (device, inode) != self.identities[name]:
                raise ValidationError("coordinate import filesystem identity changed")
            row = by_device.setdefault(
                device, {"device": device, "free_bytes": free, "required_bytes": 0}
            )
            row["free_bytes"] = min(row["free_bytes"], free)
            row["required_bytes"] += self.limits[name] - used
        rows = [by_device[key] for key in sorted(by_device)]
        for row in rows:
            if row["free_bytes"] < row["required_bytes"]:
                raise ValidationError(
                    "coordinate import filesystem lacks headroom: "
                    f"device={row['device']} free={row['free_bytes']} "
                    f"required={row['required_bytes']}"
                )
        return rows

    def write_json(self, path: Path, document: object) -> None:
        payload = _json_bytes(document)
        if len(payload) > MAX_REVIEW_ARTIFACT_FILE_BYTES:
            raise ValidationError(
                "coordinate import control record exceeds its byte bound"
            )
        self.check("artifacts", 2 * len(payload))
        atomic_write_json(path, document)
        self.refresh("artifacts", (path,))


def _json_bytes(document: object) -> bytes:
    return (
        json.dumps(
            document, ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False
        )
        + "\n"
    ).encode("ascii")


def _storage_report(context: _Context, space: _Space) -> dict[str, object]:
    report = {
        "schema_version": "1.0",
        "adapter_version": "m6-coordinate-storage-preflight-v2",
        "run_id": context.new.name,
        "commit": context.commit,
        "request_run_id": context.old.name,
        "producer_commit": context.producer_commit,
        "request_inventory_sha256": context.report.request_inventory_sha256,
        "inspection_sha256": sha256_file(context.inspection),
        "database_manifest_sha256": context.inventory.database_manifest_sha256,
        "coordinate_total_limit_bytes": MAX_COORDINATE_TOTAL_BYTES,
        "coordinate_object_limit_bytes": MAX_COORDINATE_OBJECT_BYTES,
        "additional_disk_limit_bytes": MAX_ADDITIONAL_DISK_BYTES,
        "layout": space.layout,
        "filesystems": space.check(),
        "checked_at": utc_now_iso(),
    }
    report["preflight_id"] = content_id("m6coordstorage_", report)
    return report


def storage_preflight(
    new: Path, old: Path, *, new_owner: str, old_owner: str, inspection_sha256: str
) -> dict[str, object]:
    """Authenticate current cache state and inspect storage without writing."""

    context = _context(new, old, new_owner, old_owner, inspection_sha256)
    if inspect_coordinate_cache(
        context.snapshot,
        context.database,
        expected_inventory_sha256=context.report.request_inventory_sha256,
    ) != context.report.model_dump(mode="json"):
        raise ValidationError(
            "coordinate cache changed since the authenticated inspection"
        )
    return _storage_report(context, _Space(context))


def _copy_bounded(
    source: BinaryIO, destination: Path, size: int, space: _Space
) -> None:
    remaining = size
    with destination.open("xb") as output:
        while remaining:
            block = source.read(min(remaining, 1024 * 1024))
            if not block:
                raise ValidationError("coordinate import stream is truncated")
            space.check("artifacts", len(block))
            output.write(block)
            output.flush()
            space.refresh("artifacts", (destination,))
            remaining -= len(block)
        os.fsync(output.fileno())


def _cache_paths(root: Path, record: CachedCoordinate) -> tuple[Path, ...]:
    return (
        root / record.object_relative_path,
        root / record.metadata_relative_path,
        root / "digest_index" / f"{record.object_sha256}.json",
        root / "pdb/locks" / f"{record.source_id}.lock",
    )


def _response_archive(attempt: Path, space: _Space) -> Path:
    total = sum(_owned_path(attempt, name).stat().st_size for name in RESPONSE_FILES)
    if total > MAX_REVIEW_ARTIFACT_TOTAL_BYTES:
        raise ValidationError("coordinate import response exceeds its total byte bound")
    space.check("artifacts", MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES)
    response = attempt / "response.tar.gz"
    with (
        response.open("xb") as output,
        tarfile.open(
            fileobj=output, mode="w:gz", format=tarfile.USTAR_FORMAT
        ) as archive,
    ):
        for name in RESPONSE_FILES:
            path = attempt / name
            member = tarfile.TarInfo(name)
            member.size = path.stat().st_size
            member.mode = 0o444
            with path.open("rb") as source:
                archive.addfile(member, source)
    if response.stat().st_size > MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES:
        raise ValidationError(
            "coordinate import response archive exceeds its byte bound"
        )
    space.refresh("artifacts", (response,))
    return response


def import_coordinate_cache(
    new: Path,
    old: Path,
    *,
    new_owner: str,
    old_owner: str,
    inspection_sha256: str,
    archive_sha256: str,
    archive_size_bytes: int,
    prefetch_manifest_sha256: str,
    request_stream: BinaryIO,
    response_stream: BinaryIO,
) -> dict[str, object]:
    """Perform one fully preflighted import, retaining any partial attempt intact."""

    for digest in (archive_sha256, prefetch_manifest_sha256):
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValidationError(
                "coordinate import archive or manifest checksum is invalid"
            )
    if (
        type(archive_size_bytes) is not int
        or not 1 <= archive_size_bytes <= MAX_PREFETCH_ARCHIVE_BYTES
    ):
        raise ValidationError("coordinate import archive exceeds the approved bound")
    context = _context(new, old, new_owner, old_owner, inspection_sha256)
    space = _Space(context)
    storage = _storage_report(context, space)
    attempt = context.new / IMPORT_RELATIVE
    lock = context.new / "state/m6-coordinate-import.lock"
    if lock.exists() or lock.is_symlink():
        _owned_path(context.new, "state/m6-coordinate-import.lock")
    imported: dict[str, dict[str, object]] = {}
    phase, active_id = "receiving", None
    with exclusive_lock(lock, progress=False):
        if attempt.exists() or attempt.is_symlink():
            raise ValidationError(
                "coordinate import attempt already exists; preserve it without retry"
            )
        space.check("artifacts", archive_size_bytes)
        attempt.mkdir(mode=0o700)
        space.refresh("artifacts", (attempt,))
        state = {
            "schema_version": "1.0",
            "adapter_version": "m6-coordinate-import-attempt-v1",
            "run_id": context.new.name,
            "commit": context.commit,
            "request_run_id": context.old.name,
            "producer_commit": context.producer_commit,
            "inspection_sha256": inspection_sha256,
            "inspection_bundle_sha256": context.inspection_bundle_sha256,
            "archive_sha256": archive_sha256,
            "archive_size_bytes": archive_size_bytes,
            "prefetch_manifest_sha256": prefetch_manifest_sha256,
            "started_at": utc_now_iso(),
            "status": "in_progress",
            "phase": phase,
        }
        try:
            space.write_json(attempt / "attempt.json", state)
            space.write_json(attempt / "storage_preflight.json", storage)
            archive = attempt / "prefetch.tar"
            _copy_bounded(request_stream, archive, archive_size_bytes, space)
            if request_stream.read(1) or sha256_file(archive) != archive_sha256:
                raise ValidationError(
                    "coordinate import archive stream size or checksum changed"
                )
            phase = "validating"
            space.write_json(attempt / "attempt.json", {**state, "phase": phase})
            incoming = attempt / "prefetch"
            space.check(
                "artifacts", MAX_COORDINATE_TOTAL_BYTES + MAX_PREFETCH_MANIFEST_BYTES
            )
            extract_prefetch_archive(
                archive, incoming, expected_pdb_ids=context.report.missing_pdb_ids
            )
            space.refresh("artifacts", (incoming, *incoming.rglob("*")))
            space.check()
            plan = prevalidate_proposed_cache(
                incoming,
                context.snapshot,
                context.database,
                context.inspection,
                expected_manifest_sha256=prefetch_manifest_sha256,
                expected_inventory_sha256=context.report.request_inventory_sha256,
                expected_inspection_sha256=inspection_sha256,
            )
            if plan.cache_root != context.cache_root:
                raise ValidationError("coordinate import proposed cache root differs")
            # Bound all receipt bytes before any shared-store publication.
            receipt_lines = [
                (
                    canonical_json_text(
                        {
                            "pdb_id": record.source_id.upper(),
                            "status": "started",
                            "coordinate": record.as_json(),
                        }
                    )
                    + "\n",
                    canonical_json_text(
                        {
                            "pdb_id": record.source_id.upper(),
                            "status": "published",
                            "object_sha256": record.object_sha256,
                            "metadata_sha256": record.metadata_sha256,
                        }
                    )
                    + "\n",
                )
                for _, record in plan.coordinates
            ]
            if (
                sum(
                    len(line.encode("ascii")) for pair in receipt_lines for line in pair
                )
                > MAX_REVIEW_ARTIFACT_FILE_BYTES
            ):
                raise ValidationError(
                    "coordinate import receipt inventory exceeds its bound"
                )
            space.write_json(attempt / "proposed_inspection.json", plan.proposed_report)
            space.watch(
                "cache",
                (
                    path
                    for _, record in plan.coordinates
                    for path in _cache_paths(context.cache_root, record)
                ),
            )
            if _context(new, old, new_owner, old_owner, inspection_sha256) != context:
                raise ValidationError(
                    "coordinate import authority changed before cache publication"
                )
            phase = "publishing"
            space.write_json(attempt / "attempt.json", {**state, "phase": phase})
            receipts = attempt / "publication_receipts.jsonl"
            with receipts.open("x", encoding="ascii") as handle:
                for (source, proposal), (started_line, published_line) in zip(
                    plan.coordinates, receipt_lines, strict=True
                ):
                    active_id = proposal.source_id.upper()
                    paths = _cache_paths(context.cache_root, proposal)
                    space.refresh("cache", paths)
                    space.check(
                        "cache", proposal.size_bytes + MAX_COORDINATE_OBJECT_BYTES
                    )
                    space.check("artifacts", len(started_line) + len(published_line))
                    handle.write(started_line)
                    handle.flush()
                    os.fsync(handle.fileno())
                    space.refresh("artifacts", (receipts,))
                    actual = publish_pdb_coordinate(
                        context.cache_root,
                        source,
                        pdb_id=active_id,
                        requested_url=proposal.requested_url,
                        source_url=proposal.source_url,
                        retrieved_at=proposal.retrieved_at,
                        etag=proposal.etag,
                        last_modified=proposal.last_modified,
                        content_type=proposal.content_type,
                        progress=False,
                    )
                    if actual != proposal:
                        raise ValidationError(
                            "published coordinate differs from complete preflight"
                        )
                    imported[active_id] = dict(actual.as_json())
                    handle.write(published_line)
                    handle.flush()
                    os.fsync(handle.fileno())
                    space.refresh("artifacts", (receipts,))
                    space.refresh("cache", paths)
                    space.check()
                    if len(imported) % 100 == 0:
                        print(
                            f"coordinate_import_published={len(imported)} "
                            f"expected={len(plan.coordinates)}",
                            file=sys.stderr,
                            flush=True,
                        )
            active_id = None
            phase = "postinspection"
            space.write_json(attempt / "attempt.json", {**state, "phase": phase})
            postinspection = inspect_coordinate_cache(
                context.snapshot,
                context.database,
                expected_inventory_sha256=context.report.request_inventory_sha256,
            )
            if postinspection != plan.proposed_report or set(imported) != set(
                plan.manifest.objects
            ):
                raise ValidationError(
                    "complete postimport inspection differs from the approved proposal"
                )
            if _context(new, old, new_owner, old_owner, inspection_sha256) != context:
                raise ValidationError(
                    "coordinate import authority changed before success publication"
                )
            space.write_json(attempt / "postinspection.json", postinspection)
            post_path = attempt / "postinspection.json"
            bundle = {
                "schema_version": "1.0",
                "adapter_version": "m6-coordinate-import-bundle-v1",
                "run_id": context.new.name,
                "commit": context.commit,
                "request_run_id": context.old.name,
                "producer_commit": context.producer_commit,
                "request_inventory_sha256": context.report.request_inventory_sha256,
                "request_inventory_id": context.inventory.inventory_id,
                "inspection_sha256": inspection_sha256,
                "inspection_id": context.report.inspection_id,
                "database_manifest_sha256": context.inventory.database_manifest_sha256,
                "prefetch_manifest_sha256": prefetch_manifest_sha256,
                "prefetch_id": plan.manifest.prefetch_id,
                "archive_sha256": archive_sha256,
                "archive_size_bytes": archive_size_bytes,
                "postinspection_sha256": sha256_file(post_path),
                "postinspection_size_bytes": post_path.stat().st_size,
                "postinspection_id": postinspection["inspection_id"],
                "imported_coordinates": imported,
                "total_coordinate_bytes": plan.manifest.total_size_bytes,
                "imported_at": utc_now_iso(),
                "network_acquisition_performed": False,
                "cache_import_performed": True,
                "status": "complete",
            }
            bundle["bundle_id"] = content_id("m6coordimport_", bundle)
            space.write_json(attempt / "import_bundle.json", bundle)
            control_files = (
                "attempt.json",
                "storage_preflight.json",
                "proposed_inspection.json",
                "publication_receipts.jsonl",
                *RESPONSE_FILES,
            )
            if (
                sum((attempt / name).stat().st_size for name in control_files)
                > MAX_REVIEW_ARTIFACT_TOTAL_BYTES
            ):
                raise ValidationError(
                    "coordinate import control records exceed their total bound"
                )
            response = _response_archive(attempt, space)
            space.check()
            space.write_json(
                attempt / "attempt.json",
                {
                    **state,
                    "phase": "complete",
                    "status": "complete",
                    "imported_pdb_count": len(imported),
                    "completed_at": utc_now_iso(),
                },
            )
            for path in attempt.rglob("*"):
                if path.is_file():
                    path.chmod(0o444)
        except Exception as error:
            # This is evidence retention, not recovery: never remove staged input,
            # retry a publication, or try to repair an existing cache destination.
            atomic_write_json(
                attempt / "attempt.json",
                {
                    **state,
                    "status": "failed",
                    "phase": phase,
                    "imported_pdb_count": len(imported),
                    "active_pdb_id": active_id,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "failed_at": utc_now_iso(),
                },
            )
            raise
        try:
            with response.open("rb") as source:
                shutil.copyfileobj(source, response_stream)
        except OSError as error:
            raise _ResponseStreamingError(
                "coordinate import response transfer failed; preserve completed import"
            ) from error
    return bundle


def main() -> int:
    """Internal original-dispatcher boundary, without URL/path execution."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("preflight", "import"))
    parser.add_argument("new", type=Path)
    parser.add_argument("new_owner")
    parser.add_argument("old", type=Path)
    parser.add_argument("old_owner")
    parser.add_argument("inspection_sha256")
    parser.add_argument("archive_sha256", nargs="?")
    parser.add_argument("archive_size_bytes", type=int, nargs="?")
    parser.add_argument("prefetch_manifest_sha256", nargs="?")
    args = parser.parse_args()
    try:
        new = args.new.resolve(strict=True)
        expected = _owned_path(
            new, "source/src/genome_to_diffraction/hpc/m6_coordinate_import.py"
        )
        environment = _owned_path(new, "environment/.pixi", directory=True)
        if (
            Path(__file__).resolve() != expected
            or (new / "source/.pixi").resolve(strict=True) != environment
            or Path(sys.executable).resolve()
            != (environment / "envs/hpc/bin/python").resolve(strict=True)
        ):
            raise ValidationError(
                "coordinate import is not using its fresh pinned source/runtime"
            )
        if args.operation == "preflight":
            if any(
                value is not None
                for value in (
                    args.archive_sha256,
                    args.archive_size_bytes,
                    args.prefetch_manifest_sha256,
                )
            ):
                raise ValidationError(
                    "coordinate storage preflight does not accept archive arguments"
                )
            report = storage_preflight(
                args.new,
                args.old,
                new_owner=args.new_owner,
                old_owner=args.old_owner,
                inspection_sha256=args.inspection_sha256,
            )
            for key, value in {
                "operation": "coordinate-import-preflight",
                "run_id": new.name,
                "status": "ready",
                "storage_preflight": canonical_json_text(report),
            }.items():
                print(f"{key}\t{base64.b64encode(value.encode()).decode('ascii')}")
        else:
            if any(
                value is None
                for value in (
                    args.archive_sha256,
                    args.archive_size_bytes,
                    args.prefetch_manifest_sha256,
                )
            ):
                raise ValidationError(
                    "coordinate import requires all confirmed archive arguments"
                )
            import_coordinate_cache(
                args.new,
                args.old,
                new_owner=args.new_owner,
                old_owner=args.old_owner,
                inspection_sha256=args.inspection_sha256,
                archive_sha256=args.archive_sha256,
                archive_size_bytes=args.archive_size_bytes,
                prefetch_manifest_sha256=args.prefetch_manifest_sha256,
                request_stream=sys.stdin.buffer,
                response_stream=sys.stdout.buffer,
            )
    except _ResponseStreamingError:
        traceback.print_exc(file=sys.stderr)
        return 1
    except Exception:
        traceback.print_exc(file=sys.stderr)
        for key, value in {
            "failure_class": "wrapper_failure",
            "message": "coordinate storage/import failed; inspect owned import log",
        }.items():
            print(f"{key}\t{base64.b64encode(value.encode()).decode('ascii')}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
