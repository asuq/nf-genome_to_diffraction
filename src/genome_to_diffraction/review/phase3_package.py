"""Build one immutable Phase III crystallographic or A-seed review package.

Scientific purpose
------------------
The generator binds a human checkpoint to one crystal, one owned parent run,
one Phase III execution identity, every review target, and an explicit evidence
allow-list.  It does not interpret evidence or promote a scientific status.

Inputs and outputs
------------------
Callers supply an existing non-symlink input root, relative evidence paths, and
an existing empty output directory.  A successful build atomically replaces the
empty directory with a package containing the copied evidence, one generated
``review_targets.tsv``, and ``phase3_review_package_manifest.json``.  Generated
metadata contains portable relative paths only.

No external command or tool version is required.  Missing targets, duplicate
roles or paths, symlinks, path escape, input mutation, unexpected package files,
and checksum drift raise ``PhaseIIIReviewPackageError``.  Scientific holds and
rejections remain human decisions handled by the separate decision contract.

The cache key is ``review_package_id``.  It covers the parent and execution
bindings, checkpoint/crystal/targets, creation time, and the checksum inventory
of every copied or generated file.  Focused coverage lives in
``tests/unit/test_phase3_review_package.py``.
"""

import csv
import hashlib
import io
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    sha256_file,
)
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewEvidenceArtifact,
    PhaseIIIReviewPackageManifest,
    PhaseIIIReviewPackageTarget,
    PhaseIIIReviewTableArtifact,
)
from genome_to_diffraction.schemas.v2.review import (
    phase3_review_package_content_sha256,
    validate_phase3_review_relative_path,
)
from genome_to_diffraction.status import InputContractError

_ADAPTER_VERSION = "phase3-review-package-v1"
_MANIFEST_NAME = "phase3_review_package_manifest.json"
_REVIEW_TABLE_NAME = "review_targets.tsv"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_EXECUTION_ID = re.compile(r"^phase3exec_[a-f0-9]{64}$")
_TABLE_FIELDS = (
    "checkpoint",
    "crystal_id",
    "item_id",
    "allowed_decisions",
    "decision",
    "reviewer",
    "reviewed_at",
    "reason",
    "comment",
)
_ALLOWED_DECISIONS = {
    PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC: ("hold", "proceed"),
    PhaseIIIReviewCheckpoint.A_SEED: ("approve", "defer", "reject"),
}


class PhaseIIIReviewPackageError(InputContractError):
    """A review package cannot be assembled or verified safely."""


@dataclass(frozen=True, slots=True)
class PhaseIIIReviewEvidenceSource:
    """One explicitly allow-listed evidence file below the input root."""

    role: str
    relative_path: str


@dataclass(frozen=True, slots=True)
class PhaseIIIReviewPackageRequest:
    """Complete request for one checkpoint and one crystal."""

    checkpoint: PhaseIIIReviewCheckpoint
    owned_parent_run_id: str
    parent_profile: str
    parent_phase: str
    execution_identity_id: str
    crystal_id: str
    target_item_ids: tuple[str, ...]
    created_at: datetime
    input_root: Path
    evidence_sources: tuple[PhaseIIIReviewEvidenceSource, ...]
    output_directory: Path


@dataclass(frozen=True, slots=True)
class PhaseIIIReviewPackageOutput:
    """Paths and immutable identifiers for one published package."""

    review_package_id: str
    package_content_sha256: str
    manifest: Path
    review_table: Path
    evidence_files: tuple[Path, ...]


def _checkpoint(value: object) -> PhaseIIIReviewCheckpoint:
    try:
        checkpoint = PhaseIIIReviewCheckpoint(value)
    except (TypeError, ValueError) as error:
        raise PhaseIIIReviewPackageError("review checkpoint is invalid") from error
    if checkpoint not in _ALLOWED_DECISIONS:
        raise PhaseIIIReviewPackageError(
            "review-package-v1 supports crystallographic and A-seed review only"
        )
    return checkpoint


def _identifier(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise PhaseIIIReviewPackageError(
            f"{label} must be a portable path-free identifier"
        )
    return value


def _input_root(path: Path) -> Path:
    if path.is_symlink():
        raise PhaseIIIReviewPackageError(
            "review-package input root must be a regular non-symlink directory"
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise PhaseIIIReviewPackageError(
            "review-package input root is absent or unreadable"
        ) from error
    if not resolved.is_dir():
        raise PhaseIIIReviewPackageError(
            "review-package input root must be a directory"
        )
    return resolved


def _empty_output_directory(path: Path) -> Path:
    if path.is_symlink():
        raise PhaseIIIReviewPackageError(
            "review-package output must be a regular empty directory"
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise PhaseIIIReviewPackageError(
            "review-package output must be an existing empty directory"
        ) from error
    if not resolved.is_dir() or any(resolved.iterdir()):
        raise PhaseIIIReviewPackageError(
            "review-package output must be an existing empty directory"
        )
    return resolved


def _source_file(root: Path, relative_path: str) -> Path:
    try:
        validate_phase3_review_relative_path(relative_path)
    except ValueError as error:
        raise PhaseIIIReviewPackageError(
            f"evidence source path is unsafe: {relative_path!r}"
        ) from error
    current = root
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if current.is_symlink():
            raise PhaseIIIReviewPackageError(
                f"evidence source contains a symlink: {relative_path}"
            )
    try:
        resolved = current.resolve(strict=True)
    except OSError as error:
        raise PhaseIIIReviewPackageError(
            f"evidence source is absent or unreadable: {relative_path}"
        ) from error
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise PhaseIIIReviewPackageError(
            "evidence source is not a regular file within the input root: "
            f"{relative_path}"
        )
    return resolved


def _copy_file_snapshot(source: Path, destination: Path) -> tuple[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with (
            source.open("rb") as source_handle,
            destination.open("xb") as output_handle,
        ):
            for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size_bytes += len(chunk)
                output_handle.write(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
    except OSError as error:
        raise PhaseIIIReviewPackageError(
            "review evidence could not be copied into the package"
        ) from error
    copied_sha256 = digest.hexdigest()
    try:
        current_sha256 = sha256_file(source, progress=False)
    except OSError as error:
        raise PhaseIIIReviewPackageError(
            "review evidence became unreadable during packaging"
        ) from error
    if current_sha256 != copied_sha256:
        raise PhaseIIIReviewPackageError(
            "review evidence changed while the package was being built"
        )
    return copied_sha256, size_bytes


def _review_table_bytes(
    *,
    checkpoint: PhaseIIIReviewCheckpoint,
    crystal_id: str,
    target_item_ids: tuple[str, ...],
) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(_TABLE_FIELDS)
    allowed = "|".join(_ALLOWED_DECISIONS[checkpoint])
    for item_id in target_item_ids:
        writer.writerow(
            (
                checkpoint.value,
                crystal_id,
                item_id,
                allowed,
                "",
                "",
                "",
                "",
                "",
            )
        )
    return buffer.getvalue().encode("ascii")


def _parse_review_table(
    payload: bytes,
    *,
    manifest: PhaseIIIReviewPackageManifest,
) -> None:
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise PhaseIIIReviewPackageError(
            "review target table is not ASCII text"
        ) from error
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if tuple(reader.fieldnames or ()) != _TABLE_FIELDS:
        raise PhaseIIIReviewPackageError("review target table header is invalid")
    rows = list(reader)
    expected_targets = tuple(target.item_id for target in manifest.permitted_targets)
    if len(rows) != len(expected_targets):
        raise PhaseIIIReviewPackageError(
            "review target table does not cover every permitted target"
        )
    allowed = "|".join(_ALLOWED_DECISIONS[manifest.checkpoint])
    observed_targets: list[str] = []
    for row in rows:
        if row["checkpoint"] != manifest.checkpoint.value:
            raise PhaseIIIReviewPackageError(
                "review target table checkpoint differs from its manifest"
            )
        if row["crystal_id"] != manifest.crystal_id:
            raise PhaseIIIReviewPackageError(
                "review target table crystal differs from its manifest"
            )
        if row["allowed_decisions"] != allowed:
            raise PhaseIIIReviewPackageError(
                "review target table decision vocabulary is invalid"
            )
        if any(row[field] for field in _TABLE_FIELDS[4:]):
            raise PhaseIIIReviewPackageError(
                "generated review target table contains a pre-filled decision"
            )
        observed_targets.append(row["item_id"])
    if tuple(observed_targets) != expected_targets:
        raise PhaseIIIReviewPackageError(
            "review target table target order or coverage is invalid"
        )


def _package_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in root.rglob("*"):
        relative_path = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise PhaseIIIReviewPackageError(
                f"review package contains a symlink: {relative_path}"
            )
        if path.is_dir():
            continue
        if not path.is_file():
            raise PhaseIIIReviewPackageError(
                f"review package contains a non-regular file: {relative_path}"
            )
        files[relative_path] = path
    return files


def validate_phase3_review_package(
    package_directory: Path,
) -> PhaseIIIReviewPackageManifest:
    """Revalidate one package directory, every allow-listed file, and its table."""

    root = _input_root(package_directory)
    files = _package_files(root)
    manifest_path = files.get(_MANIFEST_NAME)
    if manifest_path is None:
        raise PhaseIIIReviewPackageError("review package manifest is absent")
    try:
        manifest = PhaseIIIReviewPackageManifest.model_validate_json(
            manifest_path.read_bytes()
        )
    except (OSError, ValidationError, ValueError) as error:
        raise PhaseIIIReviewPackageError(
            f"review package manifest violates its typed contract: {error}"
        ) from error

    expected_files = {_MANIFEST_NAME}
    expected_files.update(
        artifact.relative_path for artifact in manifest.evidence_inventory
    )
    expected_files.update(table.relative_path for table in manifest.review_tables)
    if set(files) != expected_files:
        raise PhaseIIIReviewPackageError(
            "review package file inventory differs from the manifest allow-list"
        )

    for artifact in (*manifest.evidence_inventory, *manifest.review_tables):
        path = files[artifact.relative_path]
        if path.stat().st_size != artifact.size_bytes:
            raise PhaseIIIReviewPackageError(
                f"review package size differs for {artifact.relative_path}"
            )
        if sha256_file(path, progress=False) != artifact.sha256:
            raise PhaseIIIReviewPackageError(
                f"review package checksum differs for {artifact.relative_path}"
            )

    review_table = files[_REVIEW_TABLE_NAME]
    _parse_review_table(review_table.read_bytes(), manifest=manifest)
    return manifest


def build_phase3_review_package(
    request: PhaseIIIReviewPackageRequest,
) -> PhaseIIIReviewPackageOutput:
    """Build and atomically publish one path-free schema-v2 review package."""

    checkpoint = _checkpoint(request.checkpoint)
    parent_run_id = _identifier(
        request.owned_parent_run_id,
        label="owned parent run ID",
    )
    parent_profile = _identifier(request.parent_profile, label="parent profile")
    parent_phase = _identifier(request.parent_phase, label="parent phase")
    crystal_id = _identifier(request.crystal_id, label="crystal ID")
    if (
        not isinstance(request.execution_identity_id, str)
        or _EXECUTION_ID.fullmatch(request.execution_identity_id) is None
    ):
        raise PhaseIIIReviewPackageError(
            "execution identity must be a full phase3exec_ content identifier"
        )
    if request.created_at.tzinfo is None or request.created_at.utcoffset() is None:
        raise PhaseIIIReviewPackageError("package creation time must be timezone-aware")

    if not request.target_item_ids:
        raise PhaseIIIReviewPackageError("review package requires at least one target")
    target_item_ids = tuple(
        sorted(
            _identifier(item_id, label="target item ID")
            for item_id in request.target_item_ids
        )
    )
    if len(target_item_ids) != len(set(target_item_ids)):
        raise PhaseIIIReviewPackageError("review package target IDs must be unique")
    if not request.evidence_sources:
        raise PhaseIIIReviewPackageError(
            "review package requires at least one evidence file"
        )

    input_root = _input_root(request.input_root)
    output = _empty_output_directory(request.output_directory)
    evidence_inputs: list[tuple[str, str, Path, str]] = []
    for source in request.evidence_sources:
        role = _identifier(source.role, label="evidence role")
        source_path = _source_file(input_root, source.relative_path)
        package_path = f"evidence/{source.relative_path}"
        validate_phase3_review_relative_path(
            package_path,
            required_prefix="evidence",
        )
        evidence_inputs.append((role, package_path, source_path, source.relative_path))
    roles = tuple(role for role, _, _, _ in evidence_inputs)
    source_paths = tuple(source_path for _, _, source_path, _ in evidence_inputs)
    package_paths = tuple(path for _, path, _, _ in evidence_inputs)
    if len(roles) != len(set(roles)):
        raise PhaseIIIReviewPackageError("review evidence roles must be unique")
    if len(source_paths) != len(set(source_paths)):
        raise PhaseIIIReviewPackageError("review evidence source paths must be unique")
    if len(package_paths) != len(set(package_paths)):
        raise PhaseIIIReviewPackageError("review evidence package paths must be unique")
    evidence_inputs.sort(key=lambda item: (item[0], item[1]))

    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    published = False
    try:
        evidence_inventory: list[PhaseIIIReviewEvidenceArtifact] = []
        for role, package_path, source_path, _ in evidence_inputs:
            checksum, size_bytes = _copy_file_snapshot(
                source_path,
                temporary / package_path,
            )
            evidence_inventory.append(
                PhaseIIIReviewEvidenceArtifact(
                    role=role,
                    relative_path=package_path,
                    sha256=checksum,
                    size_bytes=size_bytes,
                )
            )

        table_bytes = _review_table_bytes(
            checkpoint=checkpoint,
            crystal_id=crystal_id,
            target_item_ids=target_item_ids,
        )
        table_path = temporary / _REVIEW_TABLE_NAME
        atomic_write_bytes(table_path, table_bytes)
        review_tables = (
            PhaseIIIReviewTableArtifact(
                role="review_targets",
                relative_path=_REVIEW_TABLE_NAME,
                sha256=hashlib.sha256(table_bytes).hexdigest(),
                size_bytes=len(table_bytes),
                row_count=len(target_item_ids),
                target_item_ids=target_item_ids,
            ),
        )
        evidence_tuple = tuple(evidence_inventory)
        package_content_sha256 = phase3_review_package_content_sha256(
            evidence_inventory=evidence_tuple,
            review_tables=review_tables,
        )
        manifest = PhaseIIIReviewPackageManifest.from_content(
            adapter_version=_ADAPTER_VERSION,
            checkpoint=checkpoint,
            owned_parent_run_id=parent_run_id,
            parent_profile=parent_profile,
            parent_phase=parent_phase,
            execution_identity_id=request.execution_identity_id,
            crystal_id=crystal_id,
            created_at=request.created_at,
            permitted_targets=tuple(
                PhaseIIIReviewPackageTarget(
                    crystal_id=crystal_id,
                    item_id=item_id,
                )
                for item_id in target_item_ids
            ),
            evidence_inventory=evidence_tuple,
            review_tables=review_tables,
            package_content_sha256=package_content_sha256,
        )
        atomic_write_json(
            temporary / _MANIFEST_NAME,
            manifest.model_dump(mode="json", exclude_none=False),
        )
        validate_phase3_review_package(temporary)
        os.replace(temporary, output)
        published = True
    except PhaseIIIReviewPackageError:
        raise
    except (OSError, ValidationError, ValueError) as error:
        raise PhaseIIIReviewPackageError(
            f"review package could not be published: {error}"
        ) from error
    finally:
        if not published and temporary.exists():
            shutil.rmtree(temporary)

    manifest_path = request.output_directory / _MANIFEST_NAME
    review_table_path = request.output_directory / _REVIEW_TABLE_NAME
    evidence_files = tuple(
        request.output_directory / artifact.relative_path
        for artifact in manifest.evidence_inventory
    )
    return PhaseIIIReviewPackageOutput(
        review_package_id=manifest.review_package_id,
        package_content_sha256=manifest.package_content_sha256,
        manifest=manifest_path,
        review_table=review_table_path,
        evidence_files=evidence_files,
    )


__all__ = [
    "PhaseIIIReviewEvidenceSource",
    "PhaseIIIReviewPackageError",
    "PhaseIIIReviewPackageOutput",
    "PhaseIIIReviewPackageRequest",
    "build_phase3_review_package",
    "validate_phase3_review_package",
]
