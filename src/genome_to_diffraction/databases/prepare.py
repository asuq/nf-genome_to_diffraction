"""Prepare or verify immutable PDB/Foldseek, ProstT5, and sequence resources.

Inputs are explicit resource switches, an absolute shared database root, storage
limits, and a verify/rebuild policy. Outputs are immutable resource sidecars and
one combined database manifest. Normal analysis never calls this module. Network
failures, incomplete resources, smoke-test failures, and storage violations fail
loudly; there is no scientific no-hit state at this administrative boundary.
"""

import gzip
import json
import logging
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import JsonValue, ValidationError
from tqdm import tqdm

from genome_to_diffraction import __version__
from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.databases.cache import (
    initialise_coordinate_cache,
    verify_coordinate_cache,
)
from genome_to_diffraction.databases.common import (
    DatabaseError,
    enforce_storage_limit,
    inventory_resource,
    run_command,
    tool_version,
    tree_size,
    verify_inventory,
)
from genome_to_diffraction.databases.network import download_public_resource
from genome_to_diffraction.ids import content_id
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
ESM_ATLAS_PROBE_URL = "https://api.esmatlas.com/fetchSequence/MGYP002537940442"
DEFAULT_STORAGE_LIMIT_BYTES = 1_800_000_000_000
DEFAULT_MINIMUM_FREE_BYTES = 200_000_000_000
_SMOKE_SEQUENCE = (
    "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"
)


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
    storage_limit_bytes: int = DEFAULT_STORAGE_LIMIT_BYTES
    minimum_free_bytes: int = DEFAULT_MINIMUM_FREE_BYTES
    threads: int = 4
    progress: bool = True
    pdb_sequence_url: str = PDB_SEQUENCE_URL
    esm_atlas_probe_url: str = ESM_ATLAS_PROBE_URL


def _resource_base(database_root: Path, name: str) -> Path:
    return database_root / "resources" / name


def _current_root(database_root: Path, name: str) -> Path | None:
    current = _resource_base(database_root, name) / "current"
    if not current.exists():
        return None
    return current.resolve()


def _resource_sidecar(root: Path) -> Path:
    return root / ".gtd-resource.json"


def _write_resource(resource: DatabaseResource) -> None:
    root = Path(resource.root_path)
    atomic_write_json(_resource_sidecar(root), resource.model_dump(mode="json"))


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
    if resource.status is not DatabaseResourceStatus.READY:
        raise DatabaseError(
            f"database resource is not ready: {name}: {resource.status}"
        )
    if name == "coordinate_cache":
        digest, file_count, total_bytes = verify_coordinate_cache(root)
        if digest != resource.manifest_sha256:
            raise DatabaseError("coordinate-cache layout digest mismatch")
    else:
        file_count, total_bytes = verify_inventory(
            root,
            resource.manifest_sha256,
            full_checksums=full_checksums,
            progress=progress,
        )
    if resource.file_count != file_count or resource.total_bytes != total_bytes:
        raise DatabaseError(f"resource count/size summary is inconsistent: {name}")
    _LOGGER.info(
        "reusing verified database resource",
        extra={"database_id": resource.database_id, "resource_name": name},
    )
    return resource


def _atomic_current(base: Path, target: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    current = base / "current"
    temporary = base / f".current.{uuid.uuid4().hex}.tmp"
    try:
        os.symlink(target, temporary, target_is_directory=True)
        os.replace(temporary, current)
    finally:
        temporary.unlink(missing_ok=True)


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
) -> DatabaseResource:
    records, inventory_digest = inventory_resource(staging, progress=progress)
    identity = {
        "name": name,
        "source": source,
        "release_or_snapshot": release_or_snapshot,
        "retrieved_at": retrieved_at,
        "prepared_with": prepared_with,
        "parameters": parameters,
        "manifest_sha256": inventory_digest,
    }
    database_id = content_id("db_", identity)
    final_root = staging.parent / database_id
    if final_root.exists():
        shutil.rmtree(staging)
        existing = DatabaseResource.model_validate(
            json.loads(_resource_sidecar(final_root).read_text(encoding="utf-8"))
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
    path = base / f".staging-{uuid.uuid4().hex}"
    path.mkdir()
    return path


def _log_path(database_root: Path, name: str, action: str) -> Path:
    return database_root / "logs" / f"{name}.{action}.{uuid.uuid4().hex}.log"


def _prepare_foldseek_resource(
    request: DatabasePreparationRequest, database_root: Path, name: str
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
    foldseek_version = tool_version("foldseek")
    staging = _staging(database_root, name)
    database_name = "PDB" if name == "pdb_foldseek" else "ProstT5"
    prefix_name = "pdb" if name == "pdb_foldseek" else "weights"
    command = [
        "foldseek",
        "databases",
        database_name,
        str(staging / prefix_name),
        str(staging / "tmp"),
    ]
    try:
        run_command(
            command,
            log_path=_log_path(database_root, name, "download"),
            storage_root=database_root,
            storage_limit_bytes=request.storage_limit_bytes,
            progress=request.progress,
        )
        shutil.rmtree(staging / "tmp", ignore_errors=True)
        retrieved_at = utc_now()
        return _finish_immutable_resource(
            staging,
            database_root=database_root,
            name=name,
            source=(
                "RCSB PDB via foldseek databases PDB"
                if name == "pdb_foldseek"
                else "ProstT5 weights via foldseek databases ProstT5"
            ),
            release_or_snapshot=f"retrieved-{retrieved_at.date().isoformat()}",
            retrieved_at=retrieved_at,
            prepared_with=PreparedWith(tool="foldseek", version=foldseek_version),
            parameters={
                "command": [
                    "foldseek",
                    "databases",
                    database_name,
                    prefix_name,
                    "tmp",
                ],
                "gpu": False,
                "data_license": ("CC0-1.0" if name == "pdb_foldseek" else "MIT"),
            },
            smoke_status=SmokeTestStatus.NOT_RUN,
            progress=request.progress,
            warnings=(
                "Downloader does not expose an exact source snapshot; retrieval date "
                "and full file inventory define this resource.",
            ),
        )
    except BaseException:
        failed = staging.parent / f".{staging.name}.failed"
        if staging.exists():
            os.replace(staging, failed)
        raise


def _normalise_pdb_sequences(
    compressed: Path, fasta: Path, mapping: Path, *, progress: bool
) -> int:
    """Preserve RCSB target IDs and write explicit PDB/chain-or-entity mappings."""

    count = 0
    seen: set[str] = set()
    current_target: str | None = None
    with (
        gzip.open(compressed, "rt", encoding="utf-8") as source,
        fasta.open("w", encoding="utf-8") as fasta_handle,
        mapping.open("w", encoding="utf-8") as mapping_handle,
        tqdm(
            desc="Normalise PDB sequences", unit="sequence", disable=not progress
        ) as bar,
    ):
        mapping_handle.write("target_id\tpdb_id\tchain_or_entity\toriginal_header\n")
        for line_number, line in enumerate(source, start=1):
            if line.startswith(">"):
                header = line[1:].rstrip("\n")
                target = header.split(maxsplit=1)[0]
                if len(target) < 4 or target in seen:
                    raise DatabaseError(
                        "invalid or duplicate PDB sequence target at "
                        f"line {line_number}: {target}"
                    )
                seen.add(target)
                pdb_id = target[:4].upper()
                chain_or_entity = target[5:] if len(target) > 5 else ""
                mapping_handle.write(
                    f"{target}\t{pdb_id}\t{chain_or_entity}\t{header}\n"
                )
                fasta_handle.write(f">{target}\n")
                current_target = target
                count += 1
                bar.update(1)
                continue
            if current_target is None:
                if line.strip():
                    raise DatabaseError(
                        "PDB sequence data begins before a FASTA header at "
                        f"line {line_number}"
                    )
                continue
            fasta_handle.write(line.upper())
    if count == 0:
        raise DatabaseError("RCSB PDB sequence resource contains no FASTA records")
    return count


def _prepare_pdb_sequences(
    request: DatabasePreparationRequest, database_root: Path
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
    mmseqs_version = tool_version("mmseqs")
    staging = _staging(database_root, name)
    retrieved_at = utc_now()
    try:
        metadata = download_public_resource(
            request.pdb_sequence_url,
            staging / "pdb_seqres.txt.gz",
            storage_root=database_root,
            storage_limit_bytes=request.storage_limit_bytes,
            progress=request.progress,
        )
        sequence_count = _normalise_pdb_sequences(
            staging / "pdb_seqres.txt.gz",
            staging / "pdb_seqres.faa",
            staging / "target_mapping.tsv",
            progress=request.progress,
        )
        run_command(
            [
                "mmseqs",
                "createdb",
                str(staging / "pdb_seqres.faa"),
                str(staging / "pdb_seqres"),
            ],
            log_path=_log_path(database_root, name, "createdb"),
            storage_root=database_root,
            storage_limit_bytes=request.storage_limit_bytes,
            progress=request.progress,
        )
        tmp = staging / "tmp"
        run_command(
            [
                "mmseqs",
                "createindex",
                str(staging / "pdb_seqres"),
                str(tmp),
                "--threads",
                str(request.threads),
            ],
            log_path=_log_path(database_root, name, "createindex"),
            storage_root=database_root,
            storage_limit_bytes=request.storage_limit_bytes,
            progress=request.progress,
        )
        shutil.rmtree(tmp, ignore_errors=True)
        smoke_dir = staging / "smoke"
        smoke_dir.mkdir()
        query = smoke_dir / "query.faa"
        query.write_text(f">ubiquitin_smoke\n{_SMOKE_SEQUENCE}\n", encoding="ascii")
        run_command(
            [
                "mmseqs",
                "easy-search",
                str(query),
                str(staging / "pdb_seqres"),
                str(smoke_dir / "result.tsv"),
                str(smoke_dir / "tmp"),
                "--threads",
                "1",
                "--format-output",
                "query,target,evalue,bits",
            ],
            log_path=_log_path(database_root, name, "smoke"),
            storage_root=database_root,
            storage_limit_bytes=request.storage_limit_bytes,
            progress=request.progress,
        )
        shutil.rmtree(smoke_dir)
        parameters: dict[str, JsonValue] = {
            "url": metadata.url,
            "etag": metadata.etag,
            "last_modified": metadata.last_modified,
            "content_type": metadata.content_type,
            "sequence_count": sequence_count,
            "createindex_threads": request.threads,
            "mapping": "target_id to PDB entry and chain/entity token",
            "data_license": "CC0-1.0",
        }
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
        )
    except BaseException:
        failed = staging.parent / f".{staging.name}.failed"
        if staging.exists():
            os.replace(staging, failed)
        raise


def _smoke_prostt5(
    request: DatabasePreparationRequest,
    database_root: Path,
    resource: DatabaseResource,
) -> DatabaseResource:
    root = Path(resource.root_path)
    with tempfile.TemporaryDirectory(
        prefix="prostt5-smoke-", dir=database_root / "tmp"
    ) as temporary:
        smoke = Path(temporary)
        query = smoke / "query.faa"
        query.write_text(f">ubiquitin_smoke\n{_SMOKE_SEQUENCE}\n", encoding="ascii")
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
            log_path=_log_path(database_root, "prostt5", "smoke"),
            storage_root=database_root,
            storage_limit_bytes=request.storage_limit_bytes,
            progress=request.progress,
        )
    updated = resource.model_copy(update={"smoke_test_status": SmokeTestStatus.PASSED})
    _write_resource(updated)
    return updated


def _smoke_pdb_foldseek(
    request: DatabasePreparationRequest,
    database_root: Path,
    pdb: DatabaseResource,
    prostt5: DatabaseResource,
) -> DatabaseResource:
    with tempfile.TemporaryDirectory(
        prefix="pdb-foldseek-smoke-", dir=database_root / "tmp"
    ) as temporary:
        smoke = Path(temporary)
        query = smoke / "query.faa"
        query.write_text(f">ubiquitin_smoke\n{_SMOKE_SEQUENCE}\n", encoding="ascii")
        run_command(
            [
                "foldseek",
                "easy-search",
                str(query),
                str(Path(pdb.root_path) / "pdb"),
                str(smoke / "result.tsv"),
                str(smoke / "tmp"),
                "--prostt5-model",
                str(Path(prostt5.root_path) / "weights"),
                "--threads",
                "1",
                "--format-output",
                "query,target,evalue,bits",
            ],
            log_path=_log_path(database_root, "pdb_foldseek", "smoke"),
            storage_root=database_root,
            storage_limit_bytes=request.storage_limit_bytes,
            progress=request.progress,
        )
    updated = pdb.model_copy(update={"smoke_test_status": SmokeTestStatus.PASSED})
    _write_resource(updated)
    return updated


def _coordinate_cache(
    request: DatabasePreparationRequest, database_root: Path
) -> DatabaseResource:
    name = "coordinate_cache"
    if not request.force_rebuild and _current_root(database_root, name) is not None:
        return _load_resource(
            database_root,
            name,
            full_checksums=False,
            progress=request.progress,
        )
    root = _resource_base(database_root, name) / "cache"
    digest, file_count, total_bytes = initialise_coordinate_cache(
        root, progress=request.progress
    )
    identity = {
        "name": name,
        "layout_sha256": digest,
        "layout_version": "1.0",
    }
    resource = DatabaseResource(
        database_id=content_id("db_", identity),
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
        failed = staging.parent / f".{staging.name}.failed"
        if staging.exists():
            os.replace(staging, failed)
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
    root.mkdir(parents=True, exist_ok=True)
    (root / "tmp").mkdir(exist_ok=True)
    free_bytes = shutil.disk_usage(root).free
    if free_bytes < request.minimum_free_bytes:
        raise DatabaseError(
            f"database filesystem has {free_bytes} free bytes; "
            f"{request.minimum_free_bytes} required"
        )
    enforce_storage_limit(root, request.storage_limit_bytes)
    return root


def prepare(request: DatabasePreparationRequest) -> DatabaseManifest:
    """Prepare/reuse selected resources and write one combined immutable manifest."""

    root = _validate_request(request)
    selected = {
        "pdb_foldseek": request.prepare_pdb_foldseek,
        "pdb_sequences": request.prepare_pdb_sequences,
        "prostt5": request.prepare_prostt5,
        "coordinate_cache": request.initialise_coordinate_cache,
        "esm_atlas_connectivity": request.verify_esm_atlas_connectivity,
    }
    if not any(selected.values()):
        raise DatabaseError("at least one database resource must be selected")
    _LOGGER.info(
        "database preparation started",
        extra={
            "database_root": str(root),
            "force_rebuild": request.force_rebuild,
            "verify_only": request.verify_only,
            "selected": [name for name, enabled in selected.items() if enabled],
        },
    )
    resources: dict[str, DatabaseResource] = {}
    if request.prepare_prostt5:
        resources["prostt5"] = _prepare_foldseek_resource(request, root, "prostt5")
    if request.prepare_pdb_foldseek:
        resources["pdb_foldseek"] = _prepare_foldseek_resource(
            request, root, "pdb_foldseek"
        )
    if request.prepare_pdb_sequences:
        resources["pdb_sequences"] = _prepare_pdb_sequences(request, root)
    if request.initialise_coordinate_cache:
        if request.verify_only:
            resources["coordinate_cache"] = _load_resource(
                root,
                "coordinate_cache",
                full_checksums=False,
                progress=request.progress,
            )
        else:
            resources["coordinate_cache"] = _coordinate_cache(request, root)
    if request.verify_esm_atlas_connectivity:
        resources["esm_atlas_connectivity"] = _esm_atlas_connectivity(request, root)

    if not request.verify_only:
        prostt5 = resources.get("prostt5")
        if (
            prostt5 is not None
            and prostt5.smoke_test_status is not SmokeTestStatus.PASSED
        ):
            resources["prostt5"] = _smoke_prostt5(request, root, prostt5)
        pdb = resources.get("pdb_foldseek")
        prostt5 = resources.get("prostt5")
        if (
            pdb is not None
            and prostt5 is not None
            and pdb.smoke_test_status is not SmokeTestStatus.PASSED
        ):
            resources["pdb_foldseek"] = _smoke_pdb_foldseek(request, root, pdb, prostt5)
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
    manifest_id = content_id(
        "dbm_", [{"database_id": item.database_id} for item in ordered]
    )
    manifest = DatabaseManifest(
        schema_version="1.0",
        manifest_id=manifest_id,
        created_at=datetime.now(UTC),
        resources=ordered,
    )
    atomic_write_json(request.manifest_path, manifest.model_dump(mode="json"))
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
