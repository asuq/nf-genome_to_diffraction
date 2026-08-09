"""Prepare or verify immutable PDB/Foldseek, ProstT5, and sequence resources.

Inputs are explicit resource switches, an absolute shared database root, storage
limits, and a verify/rebuild policy. Outputs are immutable resource sidecars and
one combined database manifest. Normal analysis never calls this module. Network
failures, incomplete resources, smoke-test failures, and storage violations fail
loudly; there is no scientific no-hit state at this administrative boundary.
"""

import gzip
import hashlib
import json
import logging
import math
import os
import re
import shlex
import shutil
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import gemmi
from pydantic import JsonValue, ValidationError
from tqdm import tqdm

from genome_to_diffraction import __version__
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.databases.cache import (
    exclusive_lock,
    initialise_coordinate_cache,
    publish_pdb_coordinate,
    verify_cached_pdb_coordinate,
    verify_coordinate_cache,
)
from genome_to_diffraction.databases.common import (
    DatabaseError,
    FileRecord,
    copy_inventoried_resource,
    enforce_free_space,
    enforce_storage_limit,
    inventory_resource,
    run_command,
    tool_version,
    tree_size,
    verify_inventory,
)
from genome_to_diffraction.databases.network import (
    DownloadMetadata,
    download_public_resource,
)
from genome_to_diffraction.databases.sources import (
    FOLDSEEK_PDB_ARCHIVE_URL,
    FOLDSEEK_PDB_VERSION_URL,
    FOLDSEEK_PROSTT5_ARCHIVE_URL,
    DatabaseSourceBundle,
    load_source_bundle,
)
from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.schemas.manifests import (
    DatabaseManifest,
    DatabaseResource,
    DatabaseResourceStatus,
    PreparedWith,
    SmokeTestStatus,
)
from genome_to_diffraction.time import utc_now

_LOGGER = logging.getLogger("genome_to_diffraction.databases")
PDB_SEQUENCE_URL = "https://files.rcsb.org/pub/pdb/derived_data/pdb_seqres.txt.gz"
PDB_COORDINATE_URL_TEMPLATE = "https://files.rcsb.org/download/{pdb_id}.cif.gz"
ESM_ATLAS_PROBE_URL = "https://api.esmatlas.com/fetchSequence/MGYP002537940442"
DEFAULT_STORAGE_LIMIT_BYTES = 1_800_000_000_000
DEFAULT_MINIMUM_FREE_BYTES = 200_000_000_000
_SMOKE_SEQUENCE = (
    "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"
)
_SMOKE_QUERY_ID = "ubiquitin_smoke"
_EXPECTED_SMOKE_TARGET = "1ubq_A"
_SMOKE_MAX_EVALUE = 1.0e-5
_SMOKE_MIN_BITS = 30.0
_SMOKE_MIN_COVERAGE = 0.9
_PDB_SEQRES_TARGET = re.compile(
    r"^(?P<pdb_id>[0-9][A-Za-z0-9]{3})"
    r"(?:-assembly(?P<assembly_number>[1-9][0-9]*))?"
    r"_(?P<seqres_token>[^\s\t]+)$"
)
_DECLARED_LENGTH = re.compile(r"(?:^|\s)length:(?P<length>[0-9]+)(?:\s|$)")
_PROTEIN_ALPHABET = frozenset("ABCDEFGHIKLMNPQRSTVWXYZOUJ")
_STAGING_NAME = re.compile(r"^\.staging-[0-9a-f]{32}$")
_FAILED_STAGING_NAME = re.compile(r"^\.?\.staging-[0-9a-f]{32}\.failed$")
_PDB_ARCHIVE_VERSION = re.compile(r"^(?P<md5>[0-9a-f]{32})[ \t]+pdb100\.tar\.gz$")
_PDB_DATE_VERSION = re.compile(r"^(?P<date>[0-9]{6})[ \t]+PDB_DATE$")
_FOLDSEEK_COMMIT_VERSION = re.compile(
    r"^(?P<commit>[0-9a-f]{40})[ \t]+FOLDSEEK_COMMIT$"
)


@dataclass(frozen=True)
class SmokeHit:
    """One strictly parsed bounded database-smoke result row."""

    query: str
    target: str
    evalue: float
    bits: float
    query_coverage: float
    target_coverage: float

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "query": self.query,
            "target": self.target,
            "evalue": self.evalue,
            "bits": self.bits,
            "query_coverage": self.query_coverage,
            "target_coverage": self.target_coverage,
        }


@dataclass(frozen=True)
class FoldseekPdbSnapshot:
    """Provider snapshot metadata retained by ``foldseek databases PDB``."""

    pdb_date: str
    archive_md5: str
    foldseek_commit: str
    version_file_sha256: str

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "pdb_date": self.pdb_date,
            "archive_basename": "pdb100.tar.gz",
            "archive_md5": self.archive_md5,
            "archive_digest_algorithm": "MD5 (provider record; not trust anchor)",
            "foldseek_database_commit": self.foldseek_commit,
            "version_file_sha256": self.version_file_sha256,
        }


@dataclass(frozen=True)
class DatabasePreparationRequest:
    """Operator choices for one explicit database-preparation run."""

    database_root: Path
    manifest_path: Path
    prepare_pdb_foldseek: bool = False
    prepare_pdb_sequences: bool = False
    prepare_prostt5: bool = False
    initialise_coordinate_cache: bool = False
    verify_esm_atlas_connectivity: bool = False
    verify_only: bool = False
    force_rebuild: bool = False
    full_verify: bool = False
    expected_manifest_path: Path | None = None
    expected_manifest_sha256: str | None = None
    storage_limit_bytes: int = DEFAULT_STORAGE_LIMIT_BYTES
    minimum_free_bytes: int = DEFAULT_MINIMUM_FREE_BYTES
    threads: int = 4
    lock_timeout_seconds: float = 30.0
    scratch_root: Path | None = None
    minimum_scratch_free_bytes: int = 0
    source_bundle_path: Path | None = None
    progress: bool = True
    pdb_sequence_url: str = PDB_SEQUENCE_URL
    pdb_coordinate_url_template: str = PDB_COORDINATE_URL_TEMPLATE
    esm_atlas_probe_url: str = ESM_ATLAS_PROBE_URL


def _parse_pdb_seqres_target(target: str) -> tuple[str, str]:
    """Resolve a SEQRES or Foldseek assembly-chain target to its PDB chain key."""

    match = _PDB_SEQRES_TARGET.fullmatch(target)
    if match is None:
        raise DatabaseError(f"unsupported PDB SEQRES target identifier: {target!r}")
    return match.group("pdb_id").upper(), match.group("seqres_token")


def _parse_smoke_result(path: Path) -> tuple[SmokeHit, ...]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
        raise DatabaseError(f"database smoke query produced no result rows: {path}")
    hits: list[SmokeHit] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 6 or any(not field for field in fields):
                raise DatabaseError(
                    f"malformed database smoke result at line {line_number}: {path}"
                )
            query, target, raw_evalue, raw_bits, raw_qcov, raw_tcov = fields
            try:
                evalue = float(raw_evalue)
                bits = float(raw_bits)
                query_coverage = float(raw_qcov)
                target_coverage = float(raw_tcov)
            except ValueError as error:
                raise DatabaseError(
                    f"non-numeric database smoke score at line {line_number}: {path}"
                ) from error
            if (
                query != _SMOKE_QUERY_ID
                or not math.isfinite(evalue)
                or evalue < 0
                or not math.isfinite(bits)
                or bits <= 0
                or not math.isfinite(query_coverage)
                or not 0 <= query_coverage <= 1
                or not math.isfinite(target_coverage)
                or not 0 <= target_coverage <= 1
            ):
                raise DatabaseError(
                    f"invalid database smoke row at line {line_number}: {path}"
                )
            hits.append(
                SmokeHit(
                    query=query,
                    target=target,
                    evalue=evalue,
                    bits=bits,
                    query_coverage=query_coverage,
                    target_coverage=target_coverage,
                )
            )
            if len(hits) > 1000:
                raise DatabaseError("database smoke query exceeded 1000 bounded hits")
    if not hits:
        raise DatabaseError(f"database smoke query produced no result rows: {path}")
    return tuple(hits)


def _select_functional_smoke_hit(hits: tuple[SmokeHit, ...]) -> SmokeHit:
    expected_key = _parse_pdb_seqres_target(_EXPECTED_SMOKE_TARGET)
    matches = [
        hit for hit in hits if _parse_pdb_seqres_target(hit.target) == expected_key
    ]
    _LOGGER.info(
        "database smoke results parsed",
        extra={
            "hit_count": len(hits),
            "expected_target": _EXPECTED_SMOKE_TARGET,
            "expected_match_count": len(matches),
            "top_hits": [
                {
                    "target": hit.target,
                    "evalue": hit.evalue,
                    "bits": hit.bits,
                    "query_coverage": hit.query_coverage,
                    "target_coverage": hit.target_coverage,
                }
                for hit in hits[:10]
            ],
            "top_hits_truncated": len(hits) > 10,
        },
    )
    hit = min(
        hits,
        key=lambda item: (
            item.evalue,
            -item.bits,
            -item.query_coverage,
            -item.target_coverage,
            _parse_pdb_seqres_target(item.target),
        ),
    )
    if (
        hit.evalue > _SMOKE_MAX_EVALUE
        or hit.bits < _SMOKE_MIN_BITS
        or hit.query_coverage < _SMOKE_MIN_COVERAGE
        or hit.target_coverage < _SMOKE_MIN_COVERAGE
    ):
        raise DatabaseError(
            "best database smoke hit failed significance or coverage thresholds"
        )
    return hit


def _smoke_query(path: Path) -> None:
    path.write_text(f">{_SMOKE_QUERY_ID}\n{_SMOKE_SEQUENCE}\n", encoding="ascii")


def _log_evidence(log_path: Path, *, progress: bool) -> dict[str, JsonValue]:
    return {
        "path": str(log_path),
        "sha256": sha256_file(log_path, progress=progress, logger=_LOGGER),
    }


def _preserve_smoke_file(
    database_root: Path,
    resource_name: str,
    label: str,
    source: Path,
    *,
    suffix: str,
) -> dict[str, JsonValue]:
    evidence_path = _log_path(database_root, resource_name, label).with_suffix(suffix)
    atomic_write_text(evidence_path, source.read_text(encoding="utf-8"))
    return _log_evidence(evidence_path, progress=False)


def _stable_smoke_evidence(
    qualification: object, *, keys: tuple[str, ...], label: str
) -> dict[str, JsonValue]:
    if not isinstance(qualification, dict):
        raise DatabaseError(f"missing database smoke qualification: {label}")
    stable: dict[str, JsonValue] = {}
    for key in keys:
        if key not in qualification:
            raise DatabaseError(f"incomplete database smoke qualification: {label}")
        value = qualification[key]
        if key in {"query", "result"}:
            if (
                not isinstance(value, dict)
                or set(value) != {"path", "sha256"}
                or not isinstance(value.get("sha256"), str)
            ):
                raise DatabaseError(
                    f"invalid database smoke file evidence: {label}.{key}"
                )
            stable[key] = {"sha256": value["sha256"]}
        else:
            stable[key] = value
    return stable


def _require_matching_smoke_evidence(
    expected: object,
    observed: object,
    *,
    keys: tuple[str, ...],
    label: str,
) -> None:
    if _stable_smoke_evidence(expected, keys=keys, label=label) != (
        _stable_smoke_evidence(observed, keys=keys, label=label)
    ):
        raise DatabaseError(f"{label} smoke differs from expected qualification")


_SEARCH_SMOKE_KEYS = (
    "kind",
    "query_id",
    "query_sequence_sha256",
    "thresholds",
    "hit_count",
    "selected_hit",
    "selected_hit_mapping",
    "mapping",
    "query",
    "result",
)
_PROSTT5_SMOKE_KEYS = (
    "kind",
    "query_id",
    "query_sequence_sha256",
    "query",
    "output_file_count",
    "output_manifest_sha256",
)


def _resource_base(database_root: Path, name: str) -> Path:
    return database_root / "resources" / name


def _current_root(database_root: Path, name: str) -> Path | None:
    base = _resource_base(database_root, name)
    current = base / "current"
    try:
        current.lstat()
    except FileNotFoundError:
        return None
    if not current.is_symlink():
        raise DatabaseError(f"database current pointer is not a symlink: {current}")
    try:
        root = current.resolve(strict=True)
        resolved_base = base.resolve(strict=True)
        root.relative_to(resolved_base)
    except (OSError, ValueError) as error:
        raise DatabaseError(
            "database current pointer is missing or escapes its resource base: "
            f"{current}"
        ) from error
    if root.parent != resolved_base or not root.is_dir() or root.is_symlink():
        raise DatabaseError(
            "database current pointer must name a direct real directory child: "
            f"{current}"
        )
    return root


def _resource_sidecar(root: Path) -> Path:
    return root / ".gtd-resource.json"


def _write_resource(resource: DatabaseResource) -> None:
    root = Path(resource.root_path)
    atomic_write_json(_resource_sidecar(root), resource.model_dump(mode="json"))


def _verify_log_evidence(
    database_root: Path, raw: object, *, label: str, progress: bool
) -> None:
    if not isinstance(raw, dict) or set(raw) != {"path", "sha256"}:
        raise DatabaseError(f"invalid database log evidence: {label}")
    path_value = raw.get("path")
    digest = raw.get("sha256")
    if not isinstance(path_value, str) or not isinstance(digest, str):
        raise DatabaseError(f"invalid database log evidence values: {label}")
    path = Path(path_value)
    logs_root = (database_root / "logs").resolve(strict=True)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(logs_root)
    except (OSError, ValueError) as error:
        raise DatabaseError(f"database log escaped its log root: {label}") from error
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise DatabaseError(f"database log is missing or unsafe: {label}")
    if sha256_file(path, progress=progress, logger=_LOGGER) != digest:
        raise DatabaseError(f"database log checksum mismatch: {label}")


def _verify_resource_logs(
    database_root: Path, resource: DatabaseResource, *, progress: bool
) -> None:
    preparation_log = resource.parameters.get("preparation_log")
    if preparation_log is not None:
        _verify_log_evidence(
            database_root,
            preparation_log,
            label=f"{resource.name}.preparation_log",
            progress=progress,
        )
    preparation_logs = resource.parameters.get("preparation_logs")
    if preparation_logs is not None:
        if not isinstance(preparation_logs, dict):
            raise DatabaseError(f"invalid preparation_logs: {resource.name}")
        for name, evidence in preparation_logs.items():
            _verify_log_evidence(
                database_root,
                evidence,
                label=f"{resource.name}.preparation_logs.{name}",
                progress=progress,
            )
    qualification = resource.parameters.get("qualification")
    if isinstance(qualification, dict):
        for evidence_name in ("log", "query", "result"):
            if evidence_name in qualification:
                _verify_log_evidence(
                    database_root,
                    qualification[evidence_name],
                    label=f"{resource.name}.qualification.{evidence_name}",
                    progress=progress,
                )


def _load_resource(
    database_root: Path,
    name: str,
    *,
    full_checksums: bool,
    progress: bool,
) -> DatabaseResource:
    root = _current_root(database_root, name)
    if root is None:
        raise DatabaseError(
            f"required database resource has no current version: {name}"
        )
    sidecar = _resource_sidecar(root)
    try:
        document = json.loads(sidecar.read_text(encoding="utf-8"))
        resource = DatabaseResource.model_validate(document)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise DatabaseError(
            f"invalid database resource sidecar {sidecar}: {error}"
        ) from error
    if Path(resource.root_path).resolve() != root:
        raise DatabaseError(
            f"resource root_path does not match current target: {sidecar}"
        )
    if resource.name != name:
        raise DatabaseError(
            f"resource sidecar name does not match current resource: {sidecar}"
        )
    if resource.status is not DatabaseResourceStatus.READY:
        raise DatabaseError(
            f"database resource is not ready: {name}: {resource.status}"
        )
    _verify_resource_logs(database_root, resource, progress=progress)
    if name == "coordinate_cache":
        digest, file_count, total_bytes = verify_coordinate_cache(root)
        if digest != resource.manifest_sha256:
            raise DatabaseError("coordinate-cache layout digest mismatch")
        qualification = resource.parameters.get("qualification")
        if qualification is not None:
            verify_cached_pdb_coordinate(
                root,
                qualification,
                full_checksum=full_checksums,
                progress=progress,
            )
    else:
        file_count, total_bytes = verify_inventory(
            root,
            resource.manifest_sha256,
            full_checksums=full_checksums,
            progress=progress,
        )
    if resource.file_count != file_count or resource.total_bytes != total_bytes:
        raise DatabaseError(f"resource count/size summary is inconsistent: {name}")
    expected_database_id = _database_id(name, resource.manifest_sha256)
    if resource.database_id != expected_database_id:
        raise DatabaseError(f"resource database_id is inconsistent: {name}")
    _LOGGER.info(
        "reusing verified database resource",
        extra={"database_id": resource.database_id, "resource_name": name},
    )
    return resource


def _atomic_current(base: Path, target: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    resolved_base = base.resolve(strict=True)
    resolved_target = target.resolve(strict=True)
    if (
        resolved_target.parent != resolved_base
        or not resolved_target.is_dir()
        or resolved_target.is_symlink()
    ):
        raise DatabaseError("database current target must be a direct real child")
    current = base / "current"
    temporary = base / f".current.{uuid.uuid4().hex}.tmp"
    try:
        os.symlink(target.name, temporary, target_is_directory=True)
        os.replace(temporary, current)
    finally:
        temporary.unlink(missing_ok=True)


def _database_id(name: str, inventory_digest: str) -> str:
    """Return a path- and timestamp-independent resource content identity."""

    return content_id(
        "db_", {"name": name, "inventory_manifest_sha256": inventory_digest}
    )


def _manifest_id(resources: tuple[DatabaseResource, ...]) -> str:
    """Bind a combined manifest to resource content and qualification evidence."""

    return content_id(
        "dbm_",
        [
            {
                "database_id": resource.database_id,
                "name": resource.name,
                "smoke_test_status": resource.smoke_test_status,
                "qualification": resource.parameters.get("qualification"),
            }
            for resource in resources
        ],
    )


def _load_expected_manifest(
    request: DatabasePreparationRequest,
) -> DatabaseManifest | None:
    if not request.verify_only:
        if (
            request.expected_manifest_path is not None
            or request.expected_manifest_sha256 is not None
        ):
            raise DatabaseError(
                "expected manifest inputs are valid only with verify-only mode"
            )
        return None
    if request.force_rebuild:
        raise DatabaseError("verify-only and force-rebuild are mutually exclusive")
    if (
        request.expected_manifest_path is None
        or request.expected_manifest_sha256 is None
    ):
        raise DatabaseError(
            "verify-only requires an expected manifest path and SHA-256 trust anchor"
        )
    expected_digest = request.expected_manifest_sha256
    if len(expected_digest) != 64 or any(
        character not in "0123456789abcdef" for character in expected_digest
    ):
        raise DatabaseError("expected manifest SHA-256 is invalid")
    path = request.expected_manifest_path
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise DatabaseError(
            "expected database manifest must be an absolute regular non-symlink file"
        )
    if path.resolve(strict=True) == request.manifest_path.resolve():
        raise DatabaseError("verification output must not overwrite the trust anchor")
    try:
        payload = path.read_bytes()
        actual_digest = hashlib.sha256(payload).hexdigest()
        document = json.loads(payload)
        manifest = DatabaseManifest.model_validate(document)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise DatabaseError(
            f"invalid expected database manifest {path}: {error}"
        ) from error
    if actual_digest != expected_digest:
        raise DatabaseError("expected database manifest SHA-256 mismatch")
    if manifest.manifest_id != _manifest_id(manifest.resources):
        raise DatabaseError("expected database manifest_id is inconsistent")
    names = [resource.name for resource in manifest.resources]
    if len(names) != len(set(names)):
        raise DatabaseError("expected database manifest has duplicate resource names")
    return manifest


def _finish_immutable_resource(
    staging: Path,
    *,
    database_root: Path,
    name: str,
    source: str,
    release_or_snapshot: str | None,
    retrieved_at: datetime | None,
    prepared_with: PreparedWith,
    parameters: dict[str, JsonValue],
    smoke_status: SmokeTestStatus,
    progress: bool,
    warnings: tuple[str, ...] = (),
    inventory: tuple[list[FileRecord], str] | None = None,
) -> DatabaseResource:
    records, inventory_digest = (
        inventory
        if inventory is not None
        else inventory_resource(staging, progress=progress)
    )
    database_id = _database_id(name, inventory_digest)
    final_root = staging.parent / database_id
    if final_root.exists():
        shutil.rmtree(staging)
        try:
            existing = DatabaseResource.model_validate(
                json.loads(_resource_sidecar(final_root).read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise DatabaseError(
                f"existing content-addressed resource is invalid: {final_root}: {error}"
            ) from error
        if (
            existing.name != name
            or existing.database_id != database_id
            or existing.manifest_sha256 != inventory_digest
        ):
            raise DatabaseError(
                "existing content-addressed resource identity is inconsistent: "
                f"{final_root}"
            )
        existing_count, existing_bytes = verify_inventory(
            final_root,
            inventory_digest,
            full_checksums=True,
            progress=progress,
        )
        if (
            existing.file_count != existing_count
            or existing.total_bytes != existing_bytes
        ):
            raise DatabaseError(
                "existing content-addressed resource summary is inconsistent: "
                f"{final_root}"
            )
        _atomic_current(_resource_base(database_root, name), final_root)
        return existing
    os.replace(staging, final_root)
    total_bytes = sum(record.size_bytes for record in records)
    resource = DatabaseResource(
        database_id=database_id,
        name=name,
        source=source,
        release_or_snapshot=release_or_snapshot,
        retrieved_at=retrieved_at,
        root_path=str(final_root),
        prepared_with=prepared_with,
        parameters=parameters,
        prepared_at=utc_now(),
        file_count=len(records),
        total_bytes=total_bytes,
        manifest_sha256=inventory_digest,
        smoke_test_status=smoke_status,
        status=DatabaseResourceStatus.READY,
        warnings=warnings,
    )
    _write_resource(resource)
    _atomic_current(_resource_base(database_root, name), final_root)
    return resource


def _staging(database_root: Path, name: str) -> Path:
    base = _resource_base(database_root, name)
    base.mkdir(parents=True, exist_ok=True)
    retained = sorted(
        child
        for child in base.iterdir()
        if _STAGING_NAME.fullmatch(child.name)
        or _FAILED_STAGING_NAME.fullmatch(child.name)
    )
    if retained:
        raise DatabaseError(
            "retained incomplete database staging blocks a new build; inspect and "
            "recover or remove it through an approved administrative action: "
            f"{retained[0]}"
        )
    path = base / f".staging-{uuid.uuid4().hex}"
    path.mkdir()
    return path


def _retain_failed_staging(staging: Path) -> None:
    """Retain an incomplete resource without permitting an automatic retry."""

    if not staging.exists():
        return
    failed = staging.with_name(f"{staging.name}.failed")
    if failed.exists():
        raise DatabaseError(f"failed staging destination already exists: {failed}")
    os.replace(staging, failed)
    _LOGGER.error(
        "retained incomplete database staging",
        extra={"staging_path": str(failed)},
    )


@contextmanager
def _resource_build_staging(
    request: DatabasePreparationRequest,
    durable_staging: Path,
    administration_scratch: Path,
    label: str,
) -> Iterator[tuple[Path, tuple[Path, ...], int]]:
    """Yield durable staging locally or a disposable compute-memory build root."""

    if request.scratch_root is None:
        _LOGGER.info(
            "database resource build uses durable staging",
            extra={"build_root": str(durable_staging), "resource": label},
        )
        yield durable_staging, (), 0
        return
    with tempfile.TemporaryDirectory(
        prefix=f"{label}-resource-", dir=administration_scratch
    ) as temporary:
        build_staging = Path(temporary)
        _LOGGER.info(
            "database resource build uses compute scratch",
            extra={
                "build_root": str(build_staging),
                "durable_staging": str(durable_staging),
                "resource": label,
            },
        )
        yield (
            build_staging,
            (build_staging,),
            request.minimum_scratch_free_bytes,
        )


def _publish_resource_build(
    request: DatabasePreparationRequest,
    database_root: Path,
    build_staging: Path,
    durable_staging: Path,
) -> tuple[list[FileRecord], str]:
    """Inventory a resource and, when needed, verify one durable copy-back."""

    inventory = inventory_resource(build_staging, progress=request.progress)
    if build_staging == durable_staging:
        return inventory
    records, inventory_digest = inventory
    copy_inventoried_resource(
        build_staging,
        durable_staging,
        records,
        inventory_digest,
        storage_root=database_root,
        storage_limit_bytes=request.storage_limit_bytes,
        minimum_free_bytes=request.minimum_free_bytes,
        progress=request.progress,
    )
    return inventory


@contextmanager
def _offline_foldseek_environment(
    staging: Path,
    database_root: Path,
    bundle: DatabaseSourceBundle,
    tool_scratch: Path,
) -> Iterator[dict[str, str]]:
    """Serve Foldseek's fixed HTTPS requests from a verified durable bundle."""

    aria2c = shutil.which("aria2c")
    if aria2c is None or not Path(aria2c).is_absolute():
        raise DatabaseError("pinned aria2c is required for offline Foldseek extraction")
    copy_command = shutil.which("cp")
    realpath_command = shutil.which("realpath")
    if copy_command is None or not Path(copy_command).is_absolute():
        raise DatabaseError(
            "an absolute cp executable is required for offline extraction"
        )
    if realpath_command is None or not Path(realpath_command).is_absolute():
        raise DatabaseError(
            "an absolute realpath executable is required for offline extraction"
        )
    wrapper_root = staging / ".offline-tools"
    wrapper_root.mkdir()
    mappings = (
        (
            FOLDSEEK_PDB_ARCHIVE_URL,
            bundle.path(database_root, "foldseek_pdb_archive"),
        ),
        (
            FOLDSEEK_PDB_VERSION_URL,
            bundle.path(database_root, "foldseek_pdb_version"),
        ),
        (
            FOLDSEEK_PROSTT5_ARCHIVE_URL,
            bundle.path(database_root, "foldseek_prostt5_archive"),
        ),
    )
    cases = "\n".join(
        f"    {shlex.quote(url)}) source_path={shlex.quote(str(local_path))}; "
        'source_url="$argument" ;;'
        for url, local_path in mappings
    )
    wrapper_text = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'tool="${0##*/}"\n'
        "source_path=\n"
        "source_url=\n"
        "source_count=0\n"
        "destination=\n"
        "download_dir=\n"
        "output_name=\n"
        "remote_name=false\n"
        'arguments=("$@")\n'
        'for argument in "$@"; do\n'
        '  case "$argument" in\n'
        f"{cases}\n"
        "    http://*|https://*)\n"
        "      printf 'unapproved network URL in offline Foldseek extraction: %s\\n' "
        '"$argument" >&2\n'
        "      exit 64\n"
        "      ;;\n"
        "    *) ;;\n"
        "  esac\n"
        '  [[ -z "$source_url" || "$argument" != "$source_url" ]] || '
        "((source_count+=1))\n"
        "done\n"
        '[[ -n "$source_path" && -n "$source_url" && "$source_count" -eq 1 ]] || {\n'
        "  printf 'offline Foldseek downloader requires one approved URL\\n' >&2\n"
        "  exit 64\n"
        "}\n"
        "for ((index=0; index<${#arguments[@]}; index++)); do\n"
        '  argument="${arguments[$index]}"\n'
        '  case "$tool:$argument" in\n'
        "    aria2c:-o|aria2c:--out)\n"
        "      ((++index < ${#arguments[@]})) || exit 64\n"
        '      output_name="${arguments[$index]}" ;;\n'
        '    aria2c:--out=*) output_name="${argument#*=}" ;;\n'
        "    aria2c:-d|aria2c:--dir)\n"
        "      ((++index < ${#arguments[@]})) || exit 64\n"
        '      download_dir="${arguments[$index]}" ;;\n'
        '    aria2c:--dir=*) download_dir="${argument#*=}" ;;\n'
        "    curl:-o|curl:--output)\n"
        "      ((++index < ${#arguments[@]})) || exit 64\n"
        '      destination="${arguments[$index]}" ;;\n'
        '    curl:--output=*) destination="${argument#*=}" ;;\n'
        "    curl:-O|curl:--remote-name) remote_name=true ;;\n"
        "    wget:-O|wget:--output-document)\n"
        "      ((++index < ${#arguments[@]})) || exit 64\n"
        '      destination="${arguments[$index]}" ;;\n'
        '    wget:--output-document=*) destination="${argument#*=}" ;;\n'
        "  esac\n"
        "done\n"
        'case "$tool" in\n'
        "  aria2c)\n"
        '    download_dir="${download_dir:-$PWD}"\n'
        '    output_name="${output_name:-${source_url##*/}}"\n'
        '    if [[ "$output_name" == /* ]]; then\n'
        '      destination="$output_name"\n'
        "    else\n"
        '      destination="${download_dir%/}/$output_name"\n'
        "    fi ;;\n"
        "  curl)\n"
        '    if [[ "$remote_name" == true ]]; then\n'
        '      destination="$PWD/${source_url##*/}"\n'
        "    fi\n"
        '    [[ -n "$destination" ]] || {\n'
        "      printf 'offline curl invocation requires an output file\\n' >&2\n"
        "      exit 64\n"
        "    } ;;\n"
        '  wget) destination="${destination:-$PWD/${source_url##*/}}" ;;\n'
        "  *) printf 'unsupported offline downloader: %s\\n' \"$tool\" >&2; "
        "exit 64 ;;\n"
        "esac\n"
        '[[ "$destination" == /* ]] || destination="$PWD/$destination"\n'
        'case "$destination" in\n'
        f"  {shlex.quote(str(staging.resolve()))}/*) ;;\n"
        "  *) printf 'offline download destination escaped staging\\n' >&2; "
        "exit 64 ;;\n"
        "esac\n"
        '[[ ! -L "$destination" ]] || {\n'
        "  printf 'offline download destination must not be a symlink\\n' >&2\n"
        "  exit 64\n"
        "}\n"
        'destination_parent="${destination%/*}"\n'
        f'resolved_parent="$({shlex.quote(realpath_command)} -e -- '
        '"$destination_parent")" || exit 64\n'
        'case "$resolved_parent" in\n'
        f"  {shlex.quote(str(staging.resolve()))}|"
        f"{shlex.quote(str(staging.resolve()))}/*) ;;\n"
        "  *) printf 'offline download parent escaped staging\\n' >&2; exit 64 ;;\n"
        "esac\n"
        'destination="$resolved_parent/${destination##*/}"\n'
        '[[ -f "$source_path" && ! -L "$source_path" ]] || {\n'
        "  printf 'verified offline source is missing or unsafe\\n' >&2\n"
        "  exit 66\n"
        "}\n"
        f'{shlex.quote(copy_command)} -- "$source_path" "$destination"\n'
        "printf 'offline Foldseek source copied via %s: %s\\n' "
        '"$tool" "${source_url##*/}" >&2\n'
    )
    for name in ("aria2c", "curl", "wget"):
        wrapper = wrapper_root / name
        wrapper.write_text(wrapper_text, encoding="utf-8")
        wrapper.chmod(0o555)
    try:
        yield {
            "PATH": f"{wrapper_root}{os.pathsep}{os.environ.get('PATH', '')}",
            "TMPDIR": str(tool_scratch),
        }
    finally:
        shutil.rmtree(wrapper_root, ignore_errors=True)


def _copy_bundle_source(
    bundle: DatabaseSourceBundle,
    database_root: Path,
    name: str,
    destination: Path,
) -> DownloadMetadata:
    """Copy one already verified immutable source into resource staging."""

    record = bundle.record(name)
    source = bundle.path(database_root, name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if destination.stat().st_size != record.size_bytes:
        raise DatabaseError(f"copied database source size changed: {name}")
    return record.download_metadata()


def _log_path(database_root: Path, name: str, action: str) -> Path:
    return database_root / "logs" / f"{name}.{action}.{uuid.uuid4().hex}.log"


def _parse_foldseek_pdb_snapshot(path: Path) -> FoldseekPdbSnapshot:
    """Parse the exact provider version record emitted beside the PDB database."""

    if not path.is_file() or path.is_symlink():
        raise DatabaseError("Foldseek PDB version record is missing or unsafe")
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as error:
        raise DatabaseError("cannot read Foldseek PDB version record") from error
    if len(lines) != 3:
        raise DatabaseError("Foldseek PDB version record must contain three lines")
    archive = _PDB_ARCHIVE_VERSION.fullmatch(lines[0])
    pdb_date = _PDB_DATE_VERSION.fullmatch(lines[1])
    commit = _FOLDSEEK_COMMIT_VERSION.fullmatch(lines[2])
    if archive is None or pdb_date is None or commit is None:
        raise DatabaseError("Foldseek PDB version record has an unsupported format")
    raw_date = pdb_date.group("date")
    try:
        parsed_date = datetime.strptime(raw_date, "%y%m%d").date()
    except ValueError as error:
        raise DatabaseError(
            "Foldseek PDB version record has an invalid date"
        ) from error
    if parsed_date.year < 2000:
        raise DatabaseError("Foldseek PDB snapshot date predates supported releases")
    return FoldseekPdbSnapshot(
        pdb_date=parsed_date.isoformat(),
        archive_md5=archive.group("md5"),
        foldseek_commit=commit.group("commit"),
        version_file_sha256=sha256_file(path, progress=False),
    )


def _prepare_foldseek_resource(
    request: DatabasePreparationRequest,
    database_root: Path,
    administration_scratch: Path,
    name: str,
    source_bundle: DatabaseSourceBundle | None,
) -> DatabaseResource:
    if not request.force_rebuild:
        current = _current_root(database_root, name)
        if current is not None:
            return _load_resource(
                database_root,
                name,
                full_checksums=request.full_verify,
                progress=request.progress,
            )
    if request.verify_only:
        raise DatabaseError(f"verify-only mode cannot build missing resource: {name}")
    foldseek_version = tool_version("foldseek", arguments=("version",))
    staging = _staging(database_root, name)
    database_name = "PDB" if name == "pdb_foldseek" else "ProstT5"
    prefix_name = "pdb" if name == "pdb_foldseek" else "weights"
    download_log = _log_path(database_root, name, "download")
    try:
        with _resource_build_staging(
            request, staging, administration_scratch, name
        ) as (build_staging, scratch_roots, minimum_scratch_free_bytes):
            tool_scratch = build_staging / "tmp"
            tool_scratch.mkdir()
            command = [
                "foldseek",
                "databases",
                database_name,
                str(build_staging / prefix_name),
                str(tool_scratch),
                "--threads",
                str(request.threads),
            ]
            if source_bundle is None:
                run_command(
                    command,
                    log_path=download_log,
                    storage_root=database_root,
                    write_roots=(staging,),
                    storage_limit_bytes=request.storage_limit_bytes,
                    minimum_free_bytes=request.minimum_free_bytes,
                    progress=request.progress,
                    scratch_roots=scratch_roots,
                    minimum_scratch_free_bytes=minimum_scratch_free_bytes,
                    environment_overrides={"TMPDIR": str(tool_scratch)},
                )
            else:
                with _offline_foldseek_environment(
                    build_staging, database_root, source_bundle, tool_scratch
                ) as environment:
                    run_command(
                        command,
                        log_path=download_log,
                        storage_root=database_root,
                        write_roots=(staging,),
                        storage_limit_bytes=request.storage_limit_bytes,
                        minimum_free_bytes=request.minimum_free_bytes,
                        progress=request.progress,
                        scratch_roots=scratch_roots,
                        minimum_scratch_free_bytes=minimum_scratch_free_bytes,
                        environment_overrides=environment,
                    )
            shutil.rmtree(tool_scratch)
            retrieved_at = utc_now()
            pdb_snapshot = (
                _parse_foldseek_pdb_snapshot(build_staging / "pdb.version")
                if name == "pdb_foldseek"
                else None
            )
            parameters: dict[str, JsonValue] = {
                "command": [
                    "foldseek",
                    "databases",
                    database_name,
                    prefix_name,
                    "tmp",
                    "--threads",
                    str(request.threads),
                ],
                "gpu": False,
                "build_storage": (
                    "compute_scratch"
                    if request.scratch_root is not None
                    else "durable_staging"
                ),
                "data_license": ("CC0-1.0" if name == "pdb_foldseek" else "MIT"),
                "preparation_log": _log_evidence(
                    download_log, progress=request.progress
                ),
            }
            if pdb_snapshot is not None:
                parameters["provider_snapshot"] = pdb_snapshot.as_json()
            if source_bundle is not None:
                parameters["source_bundle_id"] = source_bundle.bundle_id
            warning = (
                "Provider records only an archive MD5; the retained version file and "
                "full deployed-file inventory are the immutable trust evidence."
                if pdb_snapshot is not None
                else (
                    "Checksummed source bundle and full deployed-file inventory define "
                    "this resource."
                    if source_bundle is not None
                    else (
                        "Downloader does not expose an exact source snapshot; "
                        "retrieval "
                        "date and full file inventory define this resource."
                    )
                )
            )
            inventory = _publish_resource_build(
                request, database_root, build_staging, staging
            )
            return _finish_immutable_resource(
                staging,
                database_root=database_root,
                name=name,
                source=(
                    "RCSB PDB via foldseek databases PDB"
                    if name == "pdb_foldseek"
                    else "ProstT5 weights via foldseek databases ProstT5"
                ),
                release_or_snapshot=(
                    f"pdb-{pdb_snapshot.pdb_date}"
                    if pdb_snapshot is not None
                    else f"retrieved-{retrieved_at.date().isoformat()}"
                ),
                retrieved_at=retrieved_at,
                prepared_with=PreparedWith(tool="foldseek", version=foldseek_version),
                parameters=parameters,
                smoke_status=SmokeTestStatus.NOT_RUN,
                progress=request.progress,
                warnings=(warning,),
                inventory=inventory,
            )
    except BaseException:
        _retain_failed_staging(staging)
        raise


def _normalise_pdb_sequences(
    compressed: Path, fasta: Path, mapping: Path, *, progress: bool
) -> tuple[int, int]:
    """Preserve validated protein SEQRES IDs and their explicit suffix tokens."""

    count = 0
    skipped_non_protein = 0
    seen: set[tuple[str, str]] = set()
    current_header: str | None = None
    current_target: str | None = None
    current_pdb_id: str | None = None
    current_token: str | None = None
    current_declared_length: int | None = None
    current_is_protein = False
    sequence_parts: list[str] = []
    with (
        gzip.open(compressed, "rt", encoding="utf-8") as source,
        fasta.open("w", encoding="utf-8") as fasta_handle,
        mapping.open("w", encoding="utf-8") as mapping_handle,
        tqdm(
            desc="Normalise PDB sequences", unit="sequence", disable=not progress
        ) as bar,
    ):
        mapping_handle.write(
            "target_id\tpdb_id\tidentifier_namespace\tseqres_token\t"
            "sequence_length\tsequence_sha256\toriginal_header\n"
        )

        def flush_record() -> None:
            nonlocal count, skipped_non_protein
            if current_header is None:
                return
            if not current_is_protein:
                skipped_non_protein += 1
                return
            if (
                current_target is None
                or current_pdb_id is None
                or current_token is None
                or current_declared_length is None
            ):
                raise AssertionError("protein SEQRES state is incomplete")
            sequence = "".join(sequence_parts).upper()
            if not sequence:
                raise DatabaseError(
                    f"PDB protein SEQRES target has no sequence: {current_target}"
                )
            invalid = sorted(set(sequence) - _PROTEIN_ALPHABET)
            if invalid:
                raise DatabaseError(
                    "PDB protein SEQRES target has unsupported residue symbols: "
                    f"{current_target}: {''.join(invalid)}"
                )
            if len(sequence) != current_declared_length:
                raise DatabaseError(
                    "PDB protein SEQRES declared length mismatch: "
                    f"{current_target}: {current_declared_length} != {len(sequence)}"
                )
            # Entry IDs are case-insensitive, but wwPDB chain IDs explicitly
            # distinguish upper- and lower-case tokens (for example A and a).
            key = (current_pdb_id, current_token)
            if key in seen:
                raise DatabaseError(
                    f"duplicate PDB protein SEQRES target: {current_target}"
                )
            seen.add(key)
            mapping_handle.write(
                f"{current_target}\t{current_pdb_id}\tlegacy_seqres_suffix\t"
                f"{current_token}\t{len(sequence)}\t"
                f"{hashlib.sha256(sequence.encode('ascii')).hexdigest()}\t"
                f"{current_header}\n"
            )
            fasta_handle.write(f">{current_target}\n{sequence}\n")
            count += 1
            bar.update(1)

        for line_number, line in enumerate(source, start=1):
            if line.startswith(">"):
                flush_record()
                header = line[1:].rstrip("\n")
                if "\t" in header or not header:
                    raise DatabaseError(
                        f"invalid PDB SEQRES header at line {line_number}"
                    )
                target = header.split(maxsplit=1)[0]
                current_is_protein = "mol:protein" in header.split()
                current_header = header
                current_target = target
                sequence_parts = []
                if current_is_protein:
                    current_pdb_id, current_token = _parse_pdb_seqres_target(target)
                    length_match = _DECLARED_LENGTH.search(header)
                    if length_match is None:
                        raise DatabaseError(
                            "PDB protein SEQRES header lacks a declared length at "
                            f"line {line_number}: {target}"
                        )
                    current_declared_length = int(length_match.group("length"))
                else:
                    current_pdb_id = None
                    current_token = None
                    current_declared_length = None
                continue
            if current_header is None:
                if line.strip():
                    raise DatabaseError(
                        "PDB sequence data begins before a FASTA header at "
                        f"line {line_number}"
                    )
                continue
            sequence_line = line.strip()
            if current_is_protein and sequence_line:
                if any(character.isspace() for character in sequence_line):
                    raise DatabaseError(
                        f"PDB sequence line contains internal whitespace: {line_number}"
                    )
                sequence_parts.append(sequence_line)
        flush_record()
    if count == 0:
        raise DatabaseError("RCSB PDB sequence resource contains no protein records")
    return count, skipped_non_protein


def _require_seqres_mapping(sequence_root: Path, target: str) -> dict[str, JsonValue]:
    mapping_path = sequence_root / "target_mapping.tsv"
    expected_header = (
        "target_id\tpdb_id\tidentifier_namespace\tseqres_token\tsequence_length\t"
        "sequence_sha256\toriginal_header"
    )
    target_key = _parse_pdb_seqres_target(target)
    try:
        with mapping_path.open("r", encoding="utf-8") as handle:
            header = handle.readline().rstrip("\n")
            if header != expected_header:
                raise DatabaseError(
                    f"unexpected PDB target-mapping header: {mapping_path}"
                )
            for line_number, line in enumerate(handle, start=2):
                fields = line.rstrip("\n").split("\t")
                if len(fields) != 7:
                    raise DatabaseError(
                        f"malformed PDB target mapping at line {line_number}"
                    )
                (
                    mapped_target,
                    pdb_id,
                    namespace,
                    token,
                    raw_sequence_length,
                    sequence_sha256,
                    _,
                ) = fields
                parsed_pdb_id, parsed_token = _parse_pdb_seqres_target(mapped_target)
                if (parsed_pdb_id, parsed_token) != target_key:
                    continue
                if (
                    pdb_id != parsed_pdb_id
                    or token != parsed_token
                    or namespace != "legacy_seqres_suffix"
                ):
                    raise DatabaseError(
                        f"inconsistent PDB target mapping at line {line_number}"
                    )
                try:
                    sequence_length = int(raw_sequence_length)
                except ValueError as error:
                    raise DatabaseError(
                        f"invalid PDB target-mapping length at line {line_number}"
                    ) from error
                if (
                    sequence_length < 1
                    or len(sequence_sha256) != 64
                    or any(
                        character not in "0123456789abcdef"
                        for character in sequence_sha256
                    )
                ):
                    raise DatabaseError(
                        f"invalid PDB target-mapping sequence at line {line_number}"
                    )
                return {
                    "target_id": mapped_target,
                    "pdb_id": pdb_id,
                    "identifier_namespace": namespace,
                    "seqres_token": token,
                    "sequence_length": sequence_length,
                    "sequence_sha256": sequence_sha256,
                }
    except OSError as error:
        raise DatabaseError(
            f"cannot read PDB target mapping: {mapping_path}"
        ) from error
    raise DatabaseError(f"database smoke target does not map to PDB SEQRES: {target}")


def _require_query_equivalent_smoke_mapping(
    sequence_root: Path, hit: SmokeHit
) -> dict[str, JsonValue]:
    mapping = _require_seqres_mapping(sequence_root, hit.target)
    expected_digest = hashlib.sha256(_SMOKE_SEQUENCE.encode("ascii")).hexdigest()
    if (
        mapping.get("sequence_length") != len(_SMOKE_SEQUENCE)
        or mapping.get("sequence_sha256") != expected_digest
    ):
        raise DatabaseError(
            "selected database smoke hit is not sequence-equivalent to the fixed query"
        )
    return mapping


def _require_expected_smoke_mapping(sequence_root: Path) -> dict[str, JsonValue]:
    mapping = _require_seqres_mapping(sequence_root, _EXPECTED_SMOKE_TARGET)
    expected_digest = hashlib.sha256(_SMOKE_SEQUENCE.encode("ascii")).hexdigest()
    if (
        mapping.get("target_id") != _EXPECTED_SMOKE_TARGET
        or mapping.get("sequence_length") != len(_SMOKE_SEQUENCE)
        or mapping.get("sequence_sha256") != expected_digest
    ):
        raise DatabaseError(
            "expected 1UBQ_A SEQRES mapping does not match the fixed ubiquitin query"
        )
    return mapping


def _smoke_thresholds() -> dict[str, JsonValue]:
    return {
        "maximum_evalue": _SMOKE_MAX_EVALUE,
        "minimum_bits": _SMOKE_MIN_BITS,
        "minimum_query_coverage": _SMOKE_MIN_COVERAGE,
        "minimum_target_coverage": _SMOKE_MIN_COVERAGE,
        "maximum_hits": 1000,
    }


def _run_pdb_sequence_smoke(
    request: DatabasePreparationRequest,
    database_root: Path,
    sequence_root: Path,
) -> dict[str, JsonValue]:
    sequence_is_scratch = not sequence_root.resolve(strict=True).is_relative_to(
        database_root.resolve(strict=True)
    )
    scratch_roots = (sequence_root,) if sequence_is_scratch else ()
    minimum_scratch_free_bytes = (
        request.minimum_scratch_free_bytes if sequence_is_scratch else 0
    )
    with tempfile.TemporaryDirectory(
        prefix="pdb-sequence-smoke-", dir=database_root / "tmp"
    ) as temporary:
        smoke = Path(temporary)
        query = smoke / "query.faa"
        result = smoke / "result.tsv"
        _smoke_query(query)
        log_path = _log_path(database_root, "pdb_sequences", "smoke")
        run_command(
            [
                "mmseqs",
                "easy-search",
                str(query),
                str(sequence_root / "pdb_seqres"),
                str(result),
                str(smoke / "tmp"),
                "--threads",
                "1",
                "--max-seqs",
                "1000",
                "-e",
                str(_SMOKE_MAX_EVALUE),
                "-c",
                str(_SMOKE_MIN_COVERAGE),
                "--cov-mode",
                "0",
                "--format-output",
                "query,target,evalue,bits,qcov,tcov",
            ],
            log_path=log_path,
            storage_root=database_root,
            write_roots=(smoke,),
            storage_limit_bytes=request.storage_limit_bytes,
            minimum_free_bytes=request.minimum_free_bytes,
            progress=request.progress,
            scratch_roots=scratch_roots,
            minimum_scratch_free_bytes=minimum_scratch_free_bytes,
        )
        hits = _parse_smoke_result(result)
        selected_hit = _select_functional_smoke_hit(hits)
        selected_hit_mapping = _require_query_equivalent_smoke_mapping(
            sequence_root, selected_hit
        )
        mapping = _require_expected_smoke_mapping(sequence_root)
        return {
            "kind": "known_ubiquitin_mmseqs_search",
            "query_id": _SMOKE_QUERY_ID,
            "query_sequence_sha256": hashlib.sha256(
                _SMOKE_SEQUENCE.encode("ascii")
            ).hexdigest(),
            "thresholds": _smoke_thresholds(),
            "hit_count": len(hits),
            "selected_hit": selected_hit.as_json(),
            "selected_hit_mapping": selected_hit_mapping,
            "mapping": mapping,
            "query": _preserve_smoke_file(
                database_root,
                "pdb_sequences",
                "smoke-query",
                query,
                suffix=".faa",
            ),
            "result": _preserve_smoke_file(
                database_root,
                "pdb_sequences",
                "smoke-result",
                result,
                suffix=".tsv",
            ),
            "log": _log_evidence(log_path, progress=request.progress),
        }


def _prepare_pdb_sequences(
    request: DatabasePreparationRequest,
    database_root: Path,
    administration_scratch: Path,
    source_bundle: DatabaseSourceBundle | None,
) -> DatabaseResource:
    name = "pdb_sequences"
    if not request.force_rebuild and _current_root(database_root, name) is not None:
        return _load_resource(
            database_root,
            name,
            full_checksums=request.full_verify,
            progress=request.progress,
        )
    if request.verify_only:
        raise DatabaseError(f"verify-only mode cannot build missing resource: {name}")
    mmseqs_version = tool_version("mmseqs", arguments=("version",))
    staging = _staging(database_root, name)
    retrieved_at = utc_now()
    try:
        with _resource_build_staging(
            request, staging, administration_scratch, name
        ) as (build_staging, scratch_roots, minimum_scratch_free_bytes):
            sequence_path = build_staging / "pdb_seqres.txt.gz"
            if source_bundle is None and build_staging == staging:
                metadata = download_public_resource(
                    request.pdb_sequence_url,
                    sequence_path,
                    storage_root=database_root,
                    storage_limit_bytes=request.storage_limit_bytes,
                    minimum_free_bytes=request.minimum_free_bytes,
                    progress=request.progress,
                )
            elif source_bundle is None:
                durable_download = staging / ".pdb_seqres.txt.gz.download"
                metadata = download_public_resource(
                    request.pdb_sequence_url,
                    durable_download,
                    storage_root=database_root,
                    storage_limit_bytes=request.storage_limit_bytes,
                    minimum_free_bytes=request.minimum_free_bytes,
                    progress=request.progress,
                )
                shutil.copyfile(durable_download, sequence_path)
                durable_download.unlink()
            else:
                metadata = _copy_bundle_source(
                    source_bundle,
                    database_root,
                    "pdb_sequences",
                    sequence_path,
                )
            sequence_count, skipped_non_protein = _normalise_pdb_sequences(
                sequence_path,
                build_staging / "pdb_seqres.faa",
                build_staging / "target_mapping.tsv",
                progress=request.progress,
            )
            createdb_log = _log_path(database_root, name, "createdb")
            run_command(
                [
                    "mmseqs",
                    "createdb",
                    str(build_staging / "pdb_seqres.faa"),
                    str(build_staging / "pdb_seqres"),
                ],
                log_path=createdb_log,
                storage_root=database_root,
                write_roots=(staging,),
                storage_limit_bytes=request.storage_limit_bytes,
                minimum_free_bytes=request.minimum_free_bytes,
                progress=request.progress,
                scratch_roots=scratch_roots,
                minimum_scratch_free_bytes=minimum_scratch_free_bytes,
            )
            tool_scratch = build_staging / "tmp"
            tool_scratch.mkdir()
            createindex_log = _log_path(database_root, name, "createindex")
            run_command(
                [
                    "mmseqs",
                    "createindex",
                    str(build_staging / "pdb_seqres"),
                    str(tool_scratch),
                    "--threads",
                    str(request.threads),
                ],
                log_path=createindex_log,
                storage_root=database_root,
                write_roots=(staging,),
                storage_limit_bytes=request.storage_limit_bytes,
                minimum_free_bytes=request.minimum_free_bytes,
                progress=request.progress,
                scratch_roots=scratch_roots,
                minimum_scratch_free_bytes=minimum_scratch_free_bytes,
            )
            shutil.rmtree(tool_scratch, ignore_errors=True)
            qualification = _run_pdb_sequence_smoke(
                request, database_root, build_staging
            )
            parameters: dict[str, JsonValue] = {
                "requested_url": metadata.requested_url,
                "url": metadata.url,
                "etag": metadata.etag,
                "last_modified": metadata.last_modified,
                "content_type": metadata.content_type,
                "sequence_count": sequence_count,
                "skipped_non_protein_count": skipped_non_protein,
                "createindex_threads": request.threads,
                "build_storage": (
                    "compute_scratch"
                    if request.scratch_root is not None
                    else "durable_staging"
                ),
                "mapping": (
                    "legacy SEQRES target suffix retained without conflating namespaces"
                ),
                "data_license": "CC0-1.0",
                "preparation_logs": {
                    "createdb": _log_evidence(createdb_log, progress=request.progress),
                    "createindex": _log_evidence(
                        createindex_log, progress=request.progress
                    ),
                },
                "qualification": qualification,
            }
            if source_bundle is not None:
                parameters["source_bundle_id"] = source_bundle.bundle_id
            inventory = _publish_resource_build(
                request, database_root, build_staging, staging
            )
            return _finish_immutable_resource(
                staging,
                database_root=database_root,
                name=name,
                source="RCSB PDB SEQRES",
                release_or_snapshot=metadata.last_modified,
                retrieved_at=retrieved_at,
                prepared_with=PreparedWith(tool="mmseqs", version=mmseqs_version),
                parameters=parameters,
                smoke_status=SmokeTestStatus.PASSED,
                progress=request.progress,
                inventory=inventory,
            )
    except BaseException:
        _retain_failed_staging(staging)
        raise


def _smoke_prostt5(
    request: DatabasePreparationRequest,
    database_root: Path,
    resource: DatabaseResource,
    *,
    persist: bool,
) -> tuple[DatabaseResource, dict[str, JsonValue]]:
    root = Path(resource.root_path)
    current_version = tool_version("foldseek", arguments=("version",))
    if current_version != resource.prepared_with.version:
        raise DatabaseError("current Foldseek version differs from ProstT5 provenance")
    with tempfile.TemporaryDirectory(
        prefix="prostt5-smoke-", dir=database_root / "tmp"
    ) as temporary:
        smoke = Path(temporary)
        query = smoke / "query.faa"
        _smoke_query(query)
        log_path = _log_path(database_root, "prostt5", "smoke")
        run_command(
            [
                "foldseek",
                "createdb",
                str(query),
                str(smoke / "query_db"),
                "--prostt5-model",
                str(root / "weights"),
                "--threads",
                "1",
            ],
            log_path=log_path,
            storage_root=database_root,
            write_roots=(smoke,),
            storage_limit_bytes=request.storage_limit_bytes,
            minimum_free_bytes=request.minimum_free_bytes,
            progress=request.progress,
        )
        outputs = sorted(
            path
            for path in smoke.glob("query_db*")
            if path.is_file() and not path.is_symlink() and path.stat().st_size > 0
        )
        if not outputs:
            raise DatabaseError("ProstT5 smoke created no non-empty query database")
        output_records = [
            {
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path, progress=False),
            }
            for path in outputs
        ]
        qualification: dict[str, JsonValue] = {
            "kind": "known_ubiquitin_prostt5_createdb",
            "query_id": _SMOKE_QUERY_ID,
            "query_sequence_sha256": hashlib.sha256(
                _SMOKE_SEQUENCE.encode("ascii")
            ).hexdigest(),
            "query": _preserve_smoke_file(
                database_root,
                "prostt5",
                "smoke-query",
                query,
                suffix=".faa",
            ),
            "output_file_count": len(outputs),
            "output_manifest_sha256": canonical_digest(output_records),
            "log": _log_evidence(log_path, progress=request.progress),
        }
    existing = resource.parameters.get("qualification")
    if not persist:
        _require_matching_smoke_evidence(
            existing,
            qualification,
            keys=_PROSTT5_SMOKE_KEYS,
            label="ProstT5",
        )
        return resource, qualification
    parameters = dict(resource.parameters)
    parameters["qualification"] = qualification
    updated = resource.model_copy(
        update={
            "parameters": parameters,
            "smoke_test_status": SmokeTestStatus.PASSED,
        }
    )
    _write_resource(updated)
    return updated, qualification


def _validate_pdb_coordinate(
    coordinate_path: Path,
    *,
    pdb_id: str,
    seqres_token: str,
    expected_sequence_length: int,
    expected_sequence_sha256: str,
) -> dict[str, JsonValue]:
    try:
        with gzip.open(coordinate_path, "rt", encoding="utf-8") as handle:
            document = gemmi.cif.read_string(handle.read())
        block = document.sole_block()
    except (OSError, RuntimeError, ValueError) as error:
        raise DatabaseError(
            f"downloaded PDB coordinate is not valid mmCIF: {error}"
        ) from error
    entry_id = block.find_value("_entry.id")
    if entry_id is None or entry_id.upper() != pdb_id.upper():
        raise DatabaseError(
            f"downloaded PDB coordinate entry does not match {pdb_id}: {entry_id!r}"
        )
    labels_by_entity: dict[str, list[str]] = {}
    for row in block.find(["_struct_asym.id", "_struct_asym.entity_id"]):
        label_asym_id, entity_id = (gemmi.cif.as_string(str(value)) for value in row)
        labels_by_entity.setdefault(entity_id, []).append(label_asym_id)
    candidates: list[tuple[str, str, str]] = []
    for row in block.find(
        [
            "_entity_poly.entity_id",
            "_entity_poly.type",
            "_entity_poly.pdbx_strand_id",
            "_entity_poly.pdbx_seq_one_letter_code_can",
        ]
    ):
        entity_id, polymer_type, raw_chains, raw_sequence = (
            gemmi.cif.as_string(str(value)) for value in row
        )
        author_chains = {
            chain.strip() for chain in raw_chains.split(",") if chain.strip()
        }
        if seqres_token not in author_chains:
            continue
        if not polymer_type.casefold().startswith("polypeptide("):
            continue
        candidates.append((entity_id, polymer_type, raw_sequence))
    if len(candidates) != 1:
        raise DatabaseError(
            "PDB SEQRES author-chain suffix did not resolve to exactly one protein "
            f"polymer entity: {pdb_id}_{seqres_token}"
        )
    entity_id, polymer_type, raw_sequence = candidates[0]
    label_asym_ids: list[JsonValue] = []
    label_asym_ids.extend(sorted(set(labels_by_entity.get(entity_id, []))))
    if not label_asym_ids:
        raise DatabaseError(
            f"PDB protein polymer entity has no struct_asym mapping: {entity_id}"
        )
    sequence = "".join(raw_sequence.split()).upper()
    invalid = sorted(set(sequence) - _PROTEIN_ALPHABET)
    if not sequence or invalid:
        raise DatabaseError(
            "PDB coordinate polymer has an invalid canonical sequence: "
            f"{pdb_id}_{seqres_token}"
        )
    sequence_sha256 = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    if (
        len(sequence) != expected_sequence_length
        or sequence_sha256 != expected_sequence_sha256
    ):
        raise DatabaseError(
            "PDB coordinate polymer sequence differs from the mapped SEQRES record: "
            f"{pdb_id}_{seqres_token}"
        )
    return {
        "entry_id": entry_id.upper(),
        "seqres_token": seqres_token,
        "resolved_identifier_namespace": (
            "auth_asym_id_via_entity_poly.pdbx_strand_id"
        ),
        "entity_id": entity_id,
        "label_asym_ids": label_asym_ids,
        "polymer_type": polymer_type,
        "sequence_length": len(sequence),
        "sequence_sha256": sequence_sha256,
    }


def _smoke_pdb_foldseek(
    request: DatabasePreparationRequest,
    database_root: Path,
    pdb: DatabaseResource,
    prostt5: DatabaseResource,
    sequences: DatabaseResource,
    coordinate_cache: DatabaseResource,
    source_bundle: DatabaseSourceBundle | None,
    *,
    persist: bool,
) -> tuple[DatabaseResource, DatabaseResource, dict[str, JsonValue]]:
    current_version = tool_version("foldseek", arguments=("version",))
    if (
        current_version != pdb.prepared_with.version
        or current_version != prostt5.prepared_with.version
    ):
        raise DatabaseError("current Foldseek version differs from database provenance")
    with tempfile.TemporaryDirectory(
        prefix="pdb-foldseek-smoke-", dir=database_root / "tmp"
    ) as temporary:
        smoke = Path(temporary)
        query = smoke / "query.faa"
        result = smoke / "result.tsv"
        _smoke_query(query)
        log_path = _log_path(database_root, "pdb_foldseek", "smoke")
        run_command(
            [
                "foldseek",
                "easy-search",
                str(query),
                str(Path(pdb.root_path) / "pdb"),
                str(result),
                str(smoke / "tmp"),
                "--prostt5-model",
                str(Path(prostt5.root_path) / "weights"),
                "--threads",
                "1",
                "--max-seqs",
                "1000",
                "-e",
                str(_SMOKE_MAX_EVALUE),
                "-c",
                str(_SMOKE_MIN_COVERAGE),
                "--cov-mode",
                "0",
                "--format-output",
                "query,target,evalue,bits,qcov,tcov",
            ],
            log_path=log_path,
            storage_root=database_root,
            write_roots=(smoke,),
            storage_limit_bytes=request.storage_limit_bytes,
            minimum_free_bytes=request.minimum_free_bytes,
            progress=request.progress,
        )
        hits = _parse_smoke_result(result)
        selected_hit = _select_functional_smoke_hit(hits)
        selected_hit_mapping = _require_seqres_mapping(
            Path(sequences.root_path), selected_hit.target
        )
        mapping = _require_expected_smoke_mapping(Path(sequences.root_path))
        pdb_id = mapping["pdb_id"]
        seqres_token = mapping["seqres_token"]
        sequence_length = mapping["sequence_length"]
        sequence_sha256 = mapping["sequence_sha256"]
        if (
            not isinstance(pdb_id, str)
            or not isinstance(seqres_token, str)
            or not isinstance(sequence_length, int)
            or isinstance(sequence_length, bool)
            or not isinstance(sequence_sha256, str)
        ):
            raise AssertionError("validated PDB mapping has unexpected value types")
        base_qualification: dict[str, JsonValue] = {
            "kind": "known_ubiquitin_prostt5_foldseek_pdb_search",
            "query_id": _SMOKE_QUERY_ID,
            "query_sequence_sha256": hashlib.sha256(
                _SMOKE_SEQUENCE.encode("ascii")
            ).hexdigest(),
            "thresholds": _smoke_thresholds(),
            "hit_count": len(hits),
            "selected_hit": selected_hit.as_json(),
            "selected_hit_mapping": selected_hit_mapping,
            "mapping": mapping,
            "query": _preserve_smoke_file(
                database_root,
                "pdb_foldseek",
                "smoke-query",
                query,
                suffix=".faa",
            ),
            "result": _preserve_smoke_file(
                database_root,
                "pdb_foldseek",
                "smoke-result",
                result,
                suffix=".tsv",
            ),
            "log": _log_evidence(log_path, progress=request.progress),
        }
        if not persist:
            existing_pdb = pdb.parameters.get("qualification")
            existing_cache = coordinate_cache.parameters.get("qualification")
            _require_matching_smoke_evidence(
                existing_pdb,
                base_qualification,
                keys=_SEARCH_SMOKE_KEYS,
                label="PDB Foldseek",
            )
            if (
                not isinstance(existing_pdb, dict)
                or existing_pdb.get("cache_entry") != existing_cache
            ):
                raise DatabaseError("PDB/cache qualification records do not match")
            cached = verify_cached_pdb_coordinate(
                Path(coordinate_cache.root_path),
                existing_cache,
                full_checksum=request.full_verify,
                progress=request.progress,
            )
            coordinate_mapping = _validate_pdb_coordinate(
                Path(coordinate_cache.root_path) / cached.object_relative_path,
                pdb_id=pdb_id,
                seqres_token=seqres_token,
                expected_sequence_length=sequence_length,
                expected_sequence_sha256=sequence_sha256,
            )
            if existing_pdb.get("coordinate_mapping") != coordinate_mapping:
                raise DatabaseError(
                    "cached PDB coordinate mapping differs from qualification"
                )
            base_qualification["coordinate_mapping"] = coordinate_mapping
            base_qualification["cache_entry"] = cached.as_json()
            return pdb, coordinate_cache, base_qualification

        pending_parameters = dict(pdb.parameters)
        pending_parameters.pop("qualification", None)
        pdb = pdb.model_copy(
            update={
                "parameters": pending_parameters,
                "smoke_test_status": SmokeTestStatus.NOT_RUN,
            }
        )
        _write_resource(pdb)
        try:
            coordinate_url = request.pdb_coordinate_url_template.format(
                pdb_id=pdb_id.lower()
            )
        except (KeyError, ValueError) as error:
            raise DatabaseError("invalid PDB coordinate URL template") from error
        coordinate_path = smoke / f"{pdb_id.lower()}.cif.gz"
        if source_bundle is None:
            coordinate_metadata = download_public_resource(
                coordinate_url,
                coordinate_path,
                storage_root=database_root,
                storage_limit_bytes=request.storage_limit_bytes,
                minimum_free_bytes=request.minimum_free_bytes,
                progress=request.progress,
            )
        else:
            coordinate_metadata = _copy_bundle_source(
                source_bundle,
                database_root,
                "pdb_coordinate_1ubq",
                coordinate_path,
            )
        coordinate_mapping = _validate_pdb_coordinate(
            coordinate_path,
            pdb_id=pdb_id,
            seqres_token=seqres_token,
            expected_sequence_length=sequence_length,
            expected_sequence_sha256=sequence_sha256,
        )
        retrieved_at = utc_now().isoformat().replace("+00:00", "Z")
        cache_entry = publish_pdb_coordinate(
            Path(coordinate_cache.root_path),
            coordinate_path,
            pdb_id=pdb_id,
            requested_url=coordinate_metadata.requested_url,
            source_url=coordinate_metadata.url,
            retrieved_at=retrieved_at,
            etag=coordinate_metadata.etag,
            last_modified=coordinate_metadata.last_modified,
            content_type=coordinate_metadata.content_type,
            progress=request.progress,
        )
        base_qualification["coordinate_mapping"] = coordinate_mapping
        base_qualification["cache_entry"] = cache_entry.as_json()
    pdb_parameters = dict(pdb.parameters)
    pdb_parameters["qualification"] = base_qualification
    updated_pdb = pdb.model_copy(
        update={
            "parameters": pdb_parameters,
            "smoke_test_status": SmokeTestStatus.PASSED,
        }
    )
    cache_parameters = dict(coordinate_cache.parameters)
    cache_parameters["qualification"] = cache_entry.as_json()
    updated_cache = coordinate_cache.model_copy(
        update={
            "parameters": cache_parameters,
            "smoke_test_status": SmokeTestStatus.PASSED,
        }
    )
    # Publish the cache evidence first. If the final PDB sidecar write is
    # interrupted, its NOT_RUN state makes the coupled smoke safely repeat.
    _write_resource(updated_cache)
    _write_resource(updated_pdb)
    return updated_pdb, updated_cache, base_qualification


def _coupled_pdb_cache_qualification_complete(
    pdb: DatabaseResource, coordinate_cache: DatabaseResource
) -> bool:
    """Return whether coupled PDB/cache evidence is complete; reject mismatches."""

    if (
        pdb.smoke_test_status is not SmokeTestStatus.PASSED
        or coordinate_cache.smoke_test_status is not SmokeTestStatus.PASSED
    ):
        return False
    pdb_qualification = pdb.parameters.get("qualification")
    cache_qualification = coordinate_cache.parameters.get("qualification")
    if not isinstance(pdb_qualification, dict) or not isinstance(
        cache_qualification, dict
    ):
        return False
    if pdb_qualification.get("cache_entry") != cache_qualification:
        raise DatabaseError("PDB/cache qualification records do not match")
    return isinstance(pdb_qualification.get("coordinate_mapping"), dict)


def _coordinate_cache(
    request: DatabasePreparationRequest, database_root: Path
) -> DatabaseResource:
    name = "coordinate_cache"
    if not request.force_rebuild and _current_root(database_root, name) is not None:
        return _load_resource(
            database_root,
            name,
            full_checksums=request.full_verify,
            progress=request.progress,
        )
    root = _resource_base(database_root, name) / "cache"
    digest, file_count, total_bytes = initialise_coordinate_cache(
        root, progress=request.progress
    )
    resource = DatabaseResource(
        database_id=_database_id(name, digest),
        name=name,
        source="local content-addressed coordinate cache",
        release_or_snapshot="layout-1.0",
        retrieved_at=None,
        root_path=str(root),
        prepared_with=PreparedWith(tool="genome-to-diffraction", version=__version__),
        parameters={
            "providers": ["pdb", "afdb", "esm_atlas"],
            "object_addressing": "sha256",
            "remote_submission_default": False,
        },
        prepared_at=utc_now(),
        file_count=file_count,
        total_bytes=total_bytes,
        manifest_sha256=digest,
        smoke_test_status=SmokeTestStatus.PASSED,
        status=DatabaseResourceStatus.READY,
        warnings=(),
    )
    _write_resource(resource)
    _atomic_current(_resource_base(database_root, name), root)
    return resource


def _esm_atlas_connectivity(
    request: DatabasePreparationRequest, database_root: Path
) -> DatabaseResource:
    name = "esm_atlas_connectivity"
    if not request.force_rebuild and _current_root(database_root, name) is not None:
        return _load_resource(
            database_root,
            name,
            full_checksums=request.full_verify,
            progress=request.progress,
        )
    if request.verify_only:
        raise DatabaseError(f"verify-only mode cannot build missing resource: {name}")
    staging = _staging(database_root, name)
    retrieved_at = utc_now()
    try:
        response_path = staging / "public_probe_response.json"
        metadata = download_public_resource(
            request.esm_atlas_probe_url,
            response_path,
            storage_root=database_root,
            storage_limit_bytes=request.storage_limit_bytes,
            minimum_free_bytes=request.minimum_free_bytes,
            progress=request.progress,
        )
        if metadata.content_type is not None and "json" not in metadata.content_type:
            raise DatabaseError(
                "ESM Atlas connectivity probe returned unexpected content type: "
                f"{metadata.content_type}"
            )
        try:
            document = json.loads(response_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DatabaseError(
                f"ESM Atlas connectivity probe returned invalid JSON: {error}"
            ) from error
        sequence = document.get("sequence") if isinstance(document, dict) else None
        if not isinstance(sequence, str) or not sequence.isascii() or not sequence:
            raise DatabaseError(
                "ESM Atlas connectivity probe lacks a non-empty ASCII sequence"
            )
        return _finish_immutable_resource(
            staging,
            database_root=database_root,
            name=name,
            source="ESM Metagenomic Atlas public API",
            release_or_snapshot="connectivity-probe",
            retrieved_at=retrieved_at,
            prepared_with=PreparedWith(
                tool="genome-to-diffraction", version=__version__
            ),
            parameters={
                "requested_url": metadata.requested_url,
                "url": metadata.url,
                "etag": metadata.etag,
                "last_modified": metadata.last_modified,
                "content_type": metadata.content_type,
                "query_kind": "public_accession_only",
                "submitted_user_sequence": False,
                "response_license": "CC-BY-4.0",
            },
            smoke_status=SmokeTestStatus.PASSED,
            progress=request.progress,
            warnings=(
                "Connectivity probe only; sequence-search API use remains experimental "
                "and user-sequence submission remains disabled by default.",
            ),
        )
    except BaseException:
        _retain_failed_staging(staging)
        raise


def _validate_request(request: DatabasePreparationRequest) -> Path:
    root = request.database_root.expanduser().resolve()
    if not request.database_root.is_absolute():
        raise DatabaseError("database_root must be an absolute path")
    if root == Path("/") or root == Path.home().resolve():
        raise DatabaseError("database_root must not be / or the home-directory root")
    if request.threads < 1:
        raise ValueError("database preparation threads must be positive")
    if request.minimum_free_bytes < 0:
        raise ValueError("minimum free bytes must not be negative")
    if request.lock_timeout_seconds <= 0:
        raise ValueError("database lock timeout must be positive")
    if request.scratch_root is None and request.minimum_scratch_free_bytes != 0:
        raise ValueError("scratch headroom requires an explicit scratch root")
    if request.scratch_root is not None and request.minimum_scratch_free_bytes <= 0:
        raise ValueError("scratch minimum free bytes must be positive")
    root.mkdir(parents=True, exist_ok=True)
    (root / "tmp").mkdir(exist_ok=True)
    enforce_free_space(root, request.minimum_free_bytes)
    enforce_storage_limit(root, request.storage_limit_bytes)
    return root


def _device_id(path: Path) -> int:
    return path.stat().st_dev


def _validate_scratch_root(
    request: DatabasePreparationRequest, database_root: Path
) -> Path:
    raw = request.scratch_root
    if raw is None:
        return database_root / "tmp"
    if not raw.is_absolute() or raw.is_symlink() or not raw.is_dir():
        raise DatabaseError(
            "scratch_root must be an existing absolute non-symlink directory"
        )
    scratch = raw.resolve(strict=True)
    if scratch != raw or scratch in {Path("/"), Path.home().resolve()}:
        raise DatabaseError("scratch_root must be canonical and narrowly scoped")
    if (
        scratch == database_root
        or scratch.is_relative_to(database_root)
        or database_root.is_relative_to(scratch)
    ):
        raise DatabaseError("scratch_root must not overlap database_root")
    if _device_id(scratch) == _device_id(database_root):
        raise DatabaseError("scratch_root must use a distinct filesystem")
    enforce_free_space(scratch, request.minimum_scratch_free_bytes)
    return scratch


def prepare(request: DatabasePreparationRequest) -> DatabaseManifest:
    """Prepare/reuse selected resources and write one combined immutable manifest."""

    expected_manifest = _load_expected_manifest(request)
    root = _validate_request(request)
    lock_path = root / "tmp" / "locks" / "database-administration.lock"
    with exclusive_lock(
        lock_path,
        timeout_seconds=request.lock_timeout_seconds,
        progress=request.progress,
    ):
        scratch_parent = _validate_scratch_root(request, root)
        if request.scratch_root is None:
            return _prepare_locked(request, root, expected_manifest, scratch_parent)
        with tempfile.TemporaryDirectory(
            prefix="nf-gtd-database-administration-", dir=scratch_parent
        ) as temporary:
            administration_scratch = Path(temporary)
            _LOGGER.info(
                "database administration scratch created",
                extra={"scratch_path": str(administration_scratch)},
            )
            return _prepare_locked(
                request,
                root,
                expected_manifest,
                administration_scratch,
            )


def _prepare_locked(
    request: DatabasePreparationRequest,
    root: Path,
    expected_manifest: DatabaseManifest | None,
    administration_scratch: Path,
) -> DatabaseManifest:
    """Execute one preparation or verification while the root lock is held."""

    selected = {
        "pdb_foldseek": request.prepare_pdb_foldseek,
        "pdb_sequences": request.prepare_pdb_sequences,
        "prostt5": request.prepare_prostt5,
        "coordinate_cache": request.initialise_coordinate_cache,
        "esm_atlas_connectivity": request.verify_esm_atlas_connectivity,
    }
    if not any(selected.values()):
        raise DatabaseError("at least one database resource must be selected")
    if request.prepare_pdb_foldseek:
        required_companions = {
            "prepare_prostt5": request.prepare_prostt5,
            "prepare_pdb_sequences": request.prepare_pdb_sequences,
            "initialise_coordinate_cache": request.initialise_coordinate_cache,
        }
        missing = [name for name, enabled in required_companions.items() if not enabled]
        if missing:
            raise DatabaseError(
                "PDB Foldseek qualification requires companion resources: "
                + ", ".join(missing)
            )
    selected_names = {name for name, enabled in selected.items() if enabled}
    if expected_manifest is not None:
        expected_names = {resource.name for resource in expected_manifest.resources}
        if expected_names != selected_names:
            raise DatabaseError(
                "selected resources do not exactly match the expected manifest"
            )
    _LOGGER.info(
        "database preparation started",
        extra={
            "database_root": str(root),
            "force_rebuild": request.force_rebuild,
            "verify_only": request.verify_only,
            "selected": [name for name, enabled in selected.items() if enabled],
        },
    )
    source_bundle = (
        load_source_bundle(
            root,
            request.source_bundle_path,
            full_verify=True,
            progress=request.progress,
        )
        if request.source_bundle_path is not None
        else None
    )
    resources: dict[str, DatabaseResource] = {}
    if request.prepare_prostt5:
        resources["prostt5"] = _prepare_foldseek_resource(
            request, root, administration_scratch, "prostt5", source_bundle
        )
    if request.prepare_pdb_foldseek:
        resources["pdb_foldseek"] = _prepare_foldseek_resource(
            request, root, administration_scratch, "pdb_foldseek", source_bundle
        )
    if request.prepare_pdb_sequences:
        resources["pdb_sequences"] = _prepare_pdb_sequences(
            request, root, administration_scratch, source_bundle
        )
    if request.initialise_coordinate_cache:
        if request.verify_only:
            resources["coordinate_cache"] = _load_resource(
                root,
                "coordinate_cache",
                full_checksums=request.full_verify,
                progress=request.progress,
            )
        else:
            resources["coordinate_cache"] = _coordinate_cache(request, root)
    if request.verify_esm_atlas_connectivity:
        resources["esm_atlas_connectivity"] = _esm_atlas_connectivity(request, root)

    sequences = resources.get("pdb_sequences")
    prostt5 = resources.get("prostt5")
    pdb = resources.get("pdb_foldseek")
    coordinate_cache = resources.get("coordinate_cache")
    verification_checks: dict[str, JsonValue] = {}
    if request.verify_only:
        if sequences is not None:
            current_mmseqs = tool_version("mmseqs", arguments=("version",))
            if current_mmseqs != sequences.prepared_with.version:
                raise DatabaseError(
                    "current MMseqs2 version differs from PDB-sequence provenance"
                )
            sequence_verification = _run_pdb_sequence_smoke(
                request, root, Path(sequences.root_path)
            )
            expected_sequence_qualification = sequences.parameters.get("qualification")
            _require_matching_smoke_evidence(
                expected_sequence_qualification,
                sequence_verification,
                keys=_SEARCH_SMOKE_KEYS,
                label="PDB-sequence",
            )
            verification_checks["pdb_sequences"] = sequence_verification
        if prostt5 is not None:
            resources["prostt5"], prostt5_verification = _smoke_prostt5(
                request, root, prostt5, persist=False
            )
            verification_checks["prostt5"] = prostt5_verification
        if (
            pdb is not None
            and prostt5 is not None
            and sequences is not None
            and coordinate_cache is not None
        ):
            (
                resources["pdb_foldseek"],
                resources["coordinate_cache"],
                foldseek_verification,
            ) = _smoke_pdb_foldseek(
                request,
                root,
                pdb,
                prostt5,
                sequences,
                coordinate_cache,
                source_bundle,
                persist=False,
            )
            verification_checks["pdb_foldseek"] = foldseek_verification
    else:
        if (
            prostt5 is not None
            and prostt5.smoke_test_status is not SmokeTestStatus.PASSED
        ):
            resources["prostt5"], _ = _smoke_prostt5(
                request, root, prostt5, persist=True
            )
            prostt5 = resources["prostt5"]
        if (
            pdb is not None
            and prostt5 is not None
            and sequences is not None
            and coordinate_cache is not None
            and not _coupled_pdb_cache_qualification_complete(pdb, coordinate_cache)
        ):
            (
                resources["pdb_foldseek"],
                resources["coordinate_cache"],
                _,
            ) = _smoke_pdb_foldseek(
                request,
                root,
                pdb,
                prostt5,
                sequences,
                coordinate_cache,
                source_bundle,
                persist=True,
            )
    required_unverified = [
        name
        for name, resource in resources.items()
        if resource.smoke_test_status is not SmokeTestStatus.PASSED
    ]
    if required_unverified:
        raise DatabaseError(
            "database resources lack required smoke tests: "
            + ", ".join(required_unverified)
        )

    ordered = tuple(resources[name] for name in sorted(resources))
    if expected_manifest is not None:
        expected_by_name = {
            resource.name: resource for resource in expected_manifest.resources
        }
        for resource in ordered:
            expected_resource = expected_by_name[resource.name]
            if resource.model_dump(mode="json") != expected_resource.model_dump(
                mode="json"
            ):
                raise DatabaseError(
                    "verified database resource differs from expected manifest: "
                    f"{resource.name}"
                )
    manifest_id = _manifest_id(ordered)
    manifest = DatabaseManifest(
        schema_version="1.0",
        manifest_id=manifest_id,
        created_at=datetime.now(UTC),
        resources=ordered,
    )
    atomic_write_json(request.manifest_path, manifest.model_dump(mode="json"))
    if request.verify_only:
        if (
            request.expected_manifest_path is None
            or request.expected_manifest_sha256 is None
        ):
            raise AssertionError("verify-only trust anchor was already validated")
        output_sha256 = sha256_file(request.manifest_path, progress=False)
        verification_body: dict[str, JsonValue] = {
            "schema_version": "1.0",
            "created_at": utc_now().isoformat().replace("+00:00", "Z"),
            "verification_level": (
                "full_checksums_and_functional_smoke"
                if request.full_verify
                else "inventory_metadata_and_functional_smoke"
            ),
            "full_checksums": request.full_verify,
            "expected_manifest_path": str(request.expected_manifest_path),
            "expected_manifest_sha256": request.expected_manifest_sha256,
            "output_manifest_path": str(request.manifest_path),
            "output_manifest_sha256": output_sha256,
            "checks": verification_checks,
        }
        verification_body["verification_id"] = content_id("dbv_", verification_body)
        atomic_write_json(
            request.manifest_path.with_suffix(".verification.json"),
            verification_body,
        )
    used_bytes = tree_size(root)
    _LOGGER.info(
        "database preparation complete",
        extra={
            "manifest": str(request.manifest_path),
            "manifest_id": manifest.manifest_id,
            "resource_count": len(ordered),
            "used_bytes": used_bytes,
        },
    )
    return manifest
