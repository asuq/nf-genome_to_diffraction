"""Local ownership boundary for completed Phase III review packages.

One completed run, its exact execution identity, and human-review checkpoint
packages are snapshotted into caller-selected ignored storage.  Records contain
no machine paths.  Lookup revalidates parent/source/execution bindings and every
package's existing per-file checksum allow-list before returning runtime paths.

No external command is required.  Stale or cross-bound inputs, duplicates,
symlinks, missing/extra files, and checksum drift raise
``PhaseIIIOwnedRunError``.  The cache key is ``owned_run_registry_id``.  Focused
coverage is in ``tests/unit/test_phase3_owned_run_registry.py``.
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.review.phase3_package import (
    PhaseIIIReviewPackageError,
    validate_phase3_review_package,
)
from genome_to_diffraction.review.phase3_stage import OwnedPhaseIIIParentRun
from genome_to_diffraction.schemas.base import ContractModel
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIExecutionIdentity,
    PhaseIIIOwnedReviewPackage,
    PhaseIIIOwnedRunRegistry,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewPackageManifest,
)
from genome_to_diffraction.status import InputContractError

_LEGACY_CHECKPOINTS = frozenset(
    {
        PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        PhaseIIIReviewCheckpoint.A_SEED,
    }
)
_REGISTRY = "phase3_owned_run_registry.json"
_EXECUTION = "phase3_execution_identity.json"
_PACKAGES = "packages"
_PACKAGE_MANIFEST = "phase3_review_package_manifest.json"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class PhaseIIIOwnedRunError(InputContractError):
    """A completed run or package snapshot cannot be trusted locally."""


@dataclass(frozen=True, slots=True)
class OwnedPhaseIIIReviewPackageSource:
    """Declared lookup key and local source for one exact package."""

    crystal_id: str
    checkpoint: PhaseIIIReviewCheckpoint
    package_directory: Path


@dataclass(frozen=True, slots=True)
class ResolvedOwnedPhaseIIIReviewPackage:
    """One revalidated package ready for the existing local review stager."""

    owned_run_registry_id: str
    parent: OwnedPhaseIIIParentRun
    execution_identity_id: str
    crystal_id: str
    checkpoint: PhaseIIIReviewCheckpoint
    review_package_id: str
    package_directory: Path
    package_manifest: Path
    review_package_manifest_sha256: str


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise PhaseIIIOwnedRunError(f"{label} must be a portable path-free identifier")
    return value


def _checkpoint(value: object) -> PhaseIIIReviewCheckpoint:
    try:
        return PhaseIIIReviewCheckpoint(value)
    except (TypeError, ValueError) as error:
        raise PhaseIIIOwnedRunError("owned package checkpoint is invalid") from error


def _directory(path: Path, label: str, *, empty: bool = False) -> Path:
    if path.is_symlink():
        raise PhaseIIIOwnedRunError(f"{label} must be a non-symlink directory")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise PhaseIIIOwnedRunError(f"{label} is absent or unreadable") from error
    if not resolved.is_dir() or (empty and any(resolved.iterdir())):
        required = "an existing empty directory" if empty else "a directory"
        raise PhaseIIIOwnedRunError(f"{label} must be {required}")
    return resolved


def _file(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise PhaseIIIOwnedRunError(f"{label} must be a non-symlink file")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise PhaseIIIOwnedRunError(f"{label} is absent or unreadable") from error
    if not resolved.is_file():
        raise PhaseIIIOwnedRunError(f"{label} must be a regular file")
    return resolved


def _load[T: ContractModel](path: Path, model: type[T], label: str) -> T:
    try:
        return model.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise PhaseIIIOwnedRunError(
            f"{label} violates its typed contract: {error}"
        ) from error


def _canonical(record: ContractModel) -> bytes:
    payload = json.dumps(
        record.model_dump(mode="json", exclude_none=False),
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    return f"{payload}\n".encode()


def _has_mtz(identity: PhaseIIIExecutionIdentity, crystal_id: str) -> bool:
    return any(
        item.owner_id == crystal_id and item.role == "mtz"
        for item in identity.crystal_artifacts
    )


def _package(root: Path) -> PhaseIIIReviewPackageManifest:
    try:
        return validate_phase3_review_package(root)
    except PhaseIIIReviewPackageError as error:
        raise PhaseIIIOwnedRunError(
            f"owned review package is invalid: {error}"
        ) from error


def _assert_equal(observed: object, expected: object, message: str) -> None:
    if observed != expected:
        raise PhaseIIIOwnedRunError(message)


def _bind_package(
    manifest: PhaseIIIReviewPackageManifest,
    *,
    parent: OwnedPhaseIIIParentRun,
    completed_at: datetime,
    identity: PhaseIIIExecutionIdentity,
    crystal_id: str,
    checkpoint: PhaseIIIReviewCheckpoint,
) -> None:
    checks = (
        (manifest.owned_parent_run_id, parent.run_id, "parent run"),
        (manifest.parent_profile, parent.profile, "profile"),
        (manifest.parent_phase, parent.phase, "phase"),
        (
            manifest.execution_identity_id,
            identity.execution_identity_id,
            "execution identity",
        ),
        (manifest.crystal_id, crystal_id, "crystal"),
        (manifest.checkpoint, checkpoint, "checkpoint"),
    )
    for observed, expected, label in checks:
        _assert_equal(observed, expected, f"owned review package {label} differs")
    in_run_checkpoint = (
        checkpoint is PhaseIIIReviewCheckpoint.A_SEED
        and parent.profile in {"unknown-screen", "unknown-pass2"}
        and parent.phase
        in {
            "phase3-pass1",
            "phase3-pass2",
        }
    ) or (
        checkpoint
        in {
            PhaseIIIReviewCheckpoint.SEQUENCE,
            PhaseIIIReviewCheckpoint.COMPOSITION,
        }
        and parent.profile == "unknown-single-component"
        and parent.phase == "phase3-pass1"
    )
    if manifest.created_at < completed_at and not in_run_checkpoint:
        raise PhaseIIIOwnedRunError("owned review package predates the completed run")
    if not _has_mtz(identity, crystal_id):
        raise PhaseIIIOwnedRunError(
            "owned review-package crystal lacks an execution MTZ"
        )


def _record_package(
    source: OwnedPhaseIIIReviewPackageSource,
    *,
    parent: OwnedPhaseIIIParentRun,
    completed_at: datetime,
    identity: PhaseIIIExecutionIdentity,
) -> tuple[Path, PhaseIIIReviewPackageManifest, PhaseIIIOwnedReviewPackage]:
    crystal_id = _identifier(source.crystal_id, "owned package crystal ID")
    checkpoint = _checkpoint(source.checkpoint)
    root = _directory(source.package_directory, "owned review-package source")
    manifest = _package(root)
    _bind_package(
        manifest,
        parent=parent,
        completed_at=completed_at,
        identity=identity,
        crystal_id=crystal_id,
        checkpoint=checkpoint,
    )
    record = PhaseIIIOwnedReviewPackage(
        checkpoint=checkpoint,
        crystal_id=crystal_id,
        review_package_id=manifest.review_package_id,
        review_package_manifest_sha256=sha256_file(
            root / _PACKAGE_MANIFEST, progress=False
        ),
        package_content_sha256=manifest.package_content_sha256,
    )
    return root, manifest, record


def _validate_stored_package(
    root: Path,
    record: PhaseIIIOwnedReviewPackage,
    registry: PhaseIIIOwnedRunRegistry,
    identity: PhaseIIIExecutionIdentity,
) -> None:
    manifest = _package(root)
    parent = OwnedPhaseIIIParentRun(registry.run_id, registry.profile, registry.phase)
    _bind_package(
        manifest,
        parent=parent,
        completed_at=registry.completed_at,
        identity=identity,
        crystal_id=record.crystal_id,
        checkpoint=record.checkpoint,
    )
    _assert_equal(
        manifest.review_package_id, record.review_package_id, "owned package ID differs"
    )
    _assert_equal(
        manifest.package_content_sha256,
        record.package_content_sha256,
        "owned package content digest differs",
    )
    _assert_equal(
        sha256_file(root / _PACKAGE_MANIFEST, progress=False),
        record.review_package_manifest_sha256,
        "owned package manifest checksum differs",
    )


def validate_phase3_owned_run_registry(path: Path) -> PhaseIIIOwnedRunRegistry:
    """Revalidate one path-free run record, identity, and all package bytes."""

    root = _directory(path, "owned-run registry")
    if {item.name for item in root.iterdir()} != {_REGISTRY, _EXECUTION, _PACKAGES}:
        raise PhaseIIIOwnedRunError(
            "owned-run registry inventory differs from its allow-list"
        )
    registry_path = _file(root / _REGISTRY, "owned-run record")
    identity_path = _file(root / _EXECUTION, "owned-run execution identity")
    packages_root = _directory(root / _PACKAGES, "owned-run package store")
    registry = _load(registry_path, PhaseIIIOwnedRunRegistry, "owned-run record")
    identity = _load(identity_path, PhaseIIIExecutionIdentity, "execution identity")
    _assert_equal(
        registry_path.read_bytes(),
        _canonical(registry),
        "owned-run record is not canonical",
    )
    _assert_equal(
        identity_path.read_bytes(),
        _canonical(identity),
        "execution identity is not canonical",
    )
    _assert_equal(
        identity.execution_identity_id,
        registry.execution_identity_id,
        "execution identity differs",
    )
    _assert_equal(
        identity.source_commit, registry.source_commit, "source commit differs"
    )
    _assert_equal(identity.source_tree, registry.source_tree, "source tree differs")
    _assert_equal(
        sha256_file(identity_path, progress=False),
        registry.execution_identity_sha256,
        "execution-identity checksum differs",
    )
    _assert_equal(
        identity_path.stat().st_size,
        registry.execution_identity_size_bytes,
        "execution-identity size differs",
    )
    package_ids = {item.review_package_id for item in registry.packages}
    _assert_equal(
        {item.name for item in packages_root.iterdir()},
        package_ids,
        "owned-run package set differs from its allow-list",
    )
    for record in registry.packages:
        package_root = _directory(
            packages_root / record.review_package_id, "owned package"
        )
        _validate_stored_package(package_root, record, registry, identity)
    return registry


def register_phase3_owned_run(
    *,
    parent: OwnedPhaseIIIParentRun,
    completed_at: datetime,
    execution_identity: Path,
    packages: tuple[OwnedPhaseIIIReviewPackageSource, ...],
    output_directory: Path,
) -> PhaseIIIOwnedRunRegistry:
    """Snapshot and atomically publish one completed local run registry."""

    _identifier(parent.run_id, "owned run ID")
    _identifier(parent.profile, "owned run profile")
    _identifier(parent.phase, "owned run phase")
    if completed_at.tzinfo is None or completed_at.utcoffset() is None:
        raise PhaseIIIOwnedRunError("owned run completion time must be timezone-aware")
    if not packages:
        raise PhaseIIIOwnedRunError("owned-run registration requires a review package")
    output = _directory(output_directory, "owned-run output", empty=True)
    identity_path = _file(execution_identity, "Phase III execution identity")
    identity = _load(identity_path, PhaseIIIExecutionIdentity, "execution identity")
    source_identity_sha256 = sha256_file(identity_path, progress=False)
    prepared = tuple(
        _record_package(
            item,
            parent=parent,
            completed_at=completed_at,
            identity=identity,
        )
        for item in packages
    )
    lookup_keys = {(item[2].crystal_id, item[2].checkpoint) for item in prepared}
    if len(lookup_keys) != len(prepared):
        raise PhaseIIIOwnedRunError("duplicate crystal/checkpoint package")
    package_ids = {item[2].review_package_id for item in prepared}
    if len(package_ids) != len(prepared):
        raise PhaseIIIOwnedRunError("duplicate review package")

    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    published = False
    try:
        canonical_identity = _canonical(identity)
        (temporary / _EXECUTION).write_bytes(canonical_identity)
        package_store = temporary / _PACKAGES
        package_store.mkdir()
        for source, manifest, record in prepared:
            destination = package_store / record.review_package_id
            shutil.copytree(source, destination, symlinks=True)
            _assert_equal(
                _package(source), manifest, "source package changed during snapshot"
            )
            _assert_equal(
                _package(destination), manifest, "copied package differs from source"
            )
        _assert_equal(
            sha256_file(identity_path, progress=False),
            source_identity_sha256,
            "execution identity changed during registration",
        )
        records = tuple(
            sorted(
                (item[2] for item in prepared),
                key=lambda item: (
                    item.crystal_id,
                    item.checkpoint.value,
                    item.review_package_id,
                ),
            )
        )
        registry = PhaseIIIOwnedRunRegistry.from_content(
            adapter_version=(
                "phase3-owned-run-registry-v1"
                if all(record.checkpoint in _LEGACY_CHECKPOINTS for record in records)
                else "phase3-owned-run-registry-v2"
            ),
            run_id=parent.run_id,
            profile=parent.profile,
            phase=parent.phase,
            completed_at=completed_at,
            execution_status="completed_success",
            source_commit=identity.source_commit,
            source_tree=identity.source_tree,
            execution_identity_id=identity.execution_identity_id,
            execution_identity_sha256=hashlib.sha256(canonical_identity).hexdigest(),
            execution_identity_size_bytes=len(canonical_identity),
            packages=records,
        )
        atomic_write_json(
            temporary / _REGISTRY, registry.model_dump(mode="json", exclude_none=False)
        )
        _assert_equal(
            validate_phase3_owned_run_registry(temporary),
            registry,
            "registry changed during validation",
        )
        os.replace(temporary, output)
        published = True
    except PhaseIIIOwnedRunError:
        raise
    except (OSError, ValidationError, ValueError) as error:
        raise PhaseIIIOwnedRunError(
            f"owned-run registry could not be published: {error}"
        ) from error
    finally:
        if not published and temporary.exists():
            shutil.rmtree(temporary)
    return registry


def resolve_phase3_owned_review_package(
    path: Path,
    *,
    run_id: str,
    crystal_id: str,
    checkpoint: PhaseIIIReviewCheckpoint,
) -> ResolvedOwnedPhaseIIIReviewPackage:
    """Resolve one run/crystal/checkpoint package after complete revalidation."""

    root = _directory(path, "owned-run registry")
    registry = validate_phase3_owned_run_registry(root)
    _assert_equal(
        registry.run_id,
        _identifier(run_id, "requested run ID"),
        "requested run differs",
    )
    crystal = _identifier(crystal_id, "requested crystal ID")
    review_checkpoint = _checkpoint(checkpoint)
    matches = tuple(
        item
        for item in registry.packages
        if item.crystal_id == crystal and item.checkpoint is review_checkpoint
    )
    if len(matches) != 1:
        raise PhaseIIIOwnedRunError(
            "owned review package is missing for crystal/checkpoint"
        )
    record = matches[0]
    package_directory = root / _PACKAGES / record.review_package_id
    return ResolvedOwnedPhaseIIIReviewPackage(
        owned_run_registry_id=registry.owned_run_registry_id,
        parent=OwnedPhaseIIIParentRun(
            registry.run_id, registry.profile, registry.phase
        ),
        execution_identity_id=registry.execution_identity_id,
        crystal_id=record.crystal_id,
        checkpoint=record.checkpoint,
        review_package_id=record.review_package_id,
        package_directory=package_directory,
        package_manifest=package_directory / _PACKAGE_MANIFEST,
        review_package_manifest_sha256=record.review_package_manifest_sha256,
    )


__all__ = [
    "OwnedPhaseIIIReviewPackageSource",
    "PhaseIIIOwnedRunError",
    "ResolvedOwnedPhaseIIIReviewPackage",
    "register_phase3_owned_run",
    "resolve_phase3_owned_review_package",
    "validate_phase3_owned_run_registry",
]
