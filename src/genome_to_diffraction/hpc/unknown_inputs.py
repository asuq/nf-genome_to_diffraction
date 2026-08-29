"""Build the fixed private input archive for ``unknown-discovery`` staging.

The reviewed wrapper reads one mode-0600 untracked specification at
``.untracked/phase3-unknown-pass1/unknown-discovery-inputs.json``.  The spec
names the already staged three-crystal review directory, exact Phase III
execution identity, explicit AFDB accession map, and run-specific crystal
manifest carrying the reviewed Free-R test values. Paths never enter the
archive manifest: only canonical member names, sizes, checksums, typed IDs, and
the complete three-crystal inventory are retained.

The builder performs no network or scheduler operation.  Missing, symlinked,
cross-owned, malformed, duplicate, or changed inputs fail before a tar stream
is created.  The canonical content ID and archive checksum are the remote-stage
cache/ownership boundary.
"""

import argparse
import hashlib
import os
import re
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.execution import (
    validate_unknown_pass1_crystallographic_review_stages,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.localisation import validate_catalogue_localisation_batch
from genome_to_diffraction.review.owned_run import (
    PhaseIIIOwnedRunError,
    validate_phase3_owned_run_registry,
)
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.schemas.manifests import CrystalManifest
from genome_to_diffraction.schemas.v2 import PhaseIIIExecutionIdentity
from genome_to_diffraction.status import InputContractError

UNKNOWN_DISCOVERY_SPEC_RELATIVE = Path(
    ".untracked/phase3-unknown-pass1/unknown-discovery-inputs.json"
)
UNKNOWN_DISCOVERY_MANIFEST_NAME = "unknown_discovery_input_manifest.json"
_EXECUTION_NAME = "phase3_execution_identity.json"
_AFDB_MAP_NAME = "afdb_accession_map.tsv"
_CRYSTALS_NAME = "phase3_crystals.json"
_REVIEW_ROOT_NAME = "crystallographic_review_stage"
_REVIEW_REGISTRY_ROOT_NAME = "crystallographic_review_registry"
_LOCALISATION_ROOT_NAME = "localisation_bundle"
_MAX_SPEC_BYTES = 32 * 1024
_MAX_AFDB_MAP_BYTES = 4 * 1024 * 1024
_SPEC_KEYS = frozenset(
    {
        "schema_version",
        "crystallographic_review_stage",
        "crystallographic_review_registry",
        "execution_identity",
        "afdb_accession_map",
        "crystal_manifest",
        "localisation_bundle",
    }
)
_SOURCE_RECORD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_ACCESSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")


class UnknownDiscoveryInputError(InputContractError):
    """The fixed private unknown-discovery inputs are unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class UnknownDiscoveryInputBundle:
    """One canonical private archive and its path-free identity."""

    input_id: str
    execution_identity_id: str
    review_stage_index_id: str
    crystal_ids: tuple[str, str, str]
    archive_path: Path
    archive_sha256: str
    archive_size_bytes: int
    file_count: int


def _owned_spec(path: Path) -> dict[str, object]:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_uid != os.getuid()
        or path.stat().st_mode & 0o777 != 0o600
    ):
        raise UnknownDiscoveryInputError(
            "unknown-discovery input spec must be an owned mode-0600 regular file"
        )
    if path.stat().st_size < 1 or path.stat().st_size > _MAX_SPEC_BYTES:
        raise UnknownDiscoveryInputError(
            "unknown-discovery input spec size is outside the fixed bound"
        )
    try:
        document = load_json_document(path)
    except ContractLoadError as error:
        raise UnknownDiscoveryInputError(
            "unknown-discovery input spec is malformed"
        ) from error
    if (
        not isinstance(document, dict)
        or set(document) != _SPEC_KEYS
        or document.get("schema_version") != "1.0"
    ):
        raise UnknownDiscoveryInputError(
            "unknown-discovery input spec differs from its fixed fields"
        )
    return document


def _absolute_path(value: object, *, label: str) -> Path:
    if not isinstance(value, str) or not value.startswith("/"):
        raise UnknownDiscoveryInputError(f"{label} must be an absolute path")
    path = Path(value)
    if path.is_symlink():
        raise UnknownDiscoveryInputError(f"{label} must not be a symlink")
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise UnknownDiscoveryInputError(f"{label} is absent") from error


def _review_files(root: Path) -> tuple[tuple[str, Path], ...]:
    if not root.is_dir():
        raise UnknownDiscoveryInputError(
            "crystallographic review stage must be a directory"
        )
    files: list[tuple[str, Path]] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.is_symlink() or not path.is_file():
            raise UnknownDiscoveryInputError(
                "crystallographic review stage contains an unsafe member"
            )
        relative = path.relative_to(root).as_posix()
        if relative.startswith("../") or "/../" in relative:
            raise UnknownDiscoveryInputError(
                "crystallographic review stage contains an unsafe path"
            )
        files.append((f"{_REVIEW_ROOT_NAME}/{relative}", path))
    if not files:
        raise UnknownDiscoveryInputError("crystallographic review stage is empty")
    return tuple(files)


def _review_registry_files(root: Path) -> tuple[tuple[str, Path], ...]:
    try:
        validate_phase3_owned_run_registry(root)
    except (OSError, PhaseIIIOwnedRunError, ValueError) as error:
        raise UnknownDiscoveryInputError(
            f"crystallographic review registry is invalid: {error}"
        ) from error
    files = tuple(
        (
            f"{_REVIEW_REGISTRY_ROOT_NAME}/{path.relative_to(root).as_posix()}",
            path,
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )
    if not files:
        raise UnknownDiscoveryInputError("crystallographic review registry is empty")
    return files


def _localisation_files(root: Path) -> tuple[tuple[str, Path], ...]:
    validate_catalogue_localisation_batch(root)
    files = tuple(
        (
            f"{_LOCALISATION_ROOT_NAME}/{path.relative_to(root).as_posix()}",
            path,
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )
    if not files:
        raise UnknownDiscoveryInputError("localisation bundle is empty")
    return files


def _validate_localisation_authority(
    *,
    root: Path,
    execution: PhaseIIIExecutionIdentity,
) -> None:
    policy = validate_catalogue_localisation_batch(root)
    gel = tuple(
        artifact
        for artifact in execution.catalogue_artifacts
        if artifact.role == "gel_evidence"
    )
    if len(gel) != 1 or gel[0].sha256 != policy.gel_evidence_sha256:
        raise UnknownDiscoveryInputError(
            "localisation gel evidence differs from execution identity"
        )
    fasta = tuple(
        artifact
        for artifact in execution.catalogue_artifacts
        if artifact.role == "proteome_faa"
    )
    if len(fasta) != 1 or fasta[0].sha256 != policy.source_fasta_sha256:
        raise UnknownDiscoveryInputError(
            "localisation source FASTA differs from execution identity"
        )
    tools = {tool.name: tool for tool in execution.tools}
    expected_tools = {
        "PSORTb": policy.psortb_runtime,
        "DeepTMHMM": policy.deeptmhmm_runtime,
    }
    for name, runtime in expected_tools.items():
        tool = tools.get(name)
        if (
            tool is None
            or tool.version != runtime.tool_version
            or tool.executable_sha256 != runtime.image_manifest_sha256
            or tool.adapter_version != policy.adapter_version
        ):
            raise UnknownDiscoveryInputError(
                f"localisation runtime {name} differs from execution identity"
            )
    adapters = dict(execution.adapter_versions)
    if (
        adapters.get("phase3_localisation_batch") != policy.adapter_version
        or adapters.get("phase3_first_copy_funnel")
        != "multi-source-first-copy-funnel-v4-phase3-evidence"
        or adapters.get("phase3_all_model_registry") != "all-eligible-model-registry-v3"
        or adapters.get("phase3_composition_beam") != "phase3-composition-beam-depth-v1"
        or adapters.get("phase3_composition_depth")
        != "phase3-composition-depth-input-v1"
        or adapters.get("phase3_no_a_expansion") != "phase3-no-a-expansion-v2"
        or adapters.get("phase3_pass2_a_seed") != "phase3-pass2-a-seed-v1"
    ):
        raise UnknownDiscoveryInputError(
            "localisation adapters differ from execution identity"
        )


def _afdb_map(path: Path) -> bytes:
    if not path.is_file() or path.stat().st_size > _MAX_AFDB_MAP_BYTES:
        raise UnknownDiscoveryInputError(
            "AFDB accession map is absent or outside the fixed bound"
        )
    payload = path.read_bytes()
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise UnknownDiscoveryInputError("AFDB accession map must be ASCII") from error
    lines = text.splitlines()
    if not lines or lines[0] != "source_record_id\tuniprot_accession":
        raise UnknownDiscoveryInputError("AFDB accession map has invalid headers")
    if text != "\n".join(lines) + "\n":
        raise UnknownDiscoveryInputError(
            "AFDB accession map must be canonical LF-terminated text"
        )
    seen: set[str] = set()
    for line_number, line in enumerate(lines[1:], start=2):
        fields = line.split("\t")
        if (
            len(fields) != 2
            or _SOURCE_RECORD_ID.fullmatch(fields[0]) is None
            or _ACCESSION.fullmatch(fields[1]) is None
            or fields[0] in seen
        ):
            raise UnknownDiscoveryInputError(
                f"AFDB accession map has an invalid row at line {line_number}"
            )
        seen.add(fields[0])
    return payload


def _phase3_crystal_manifest(
    path: Path,
    *,
    crystal_ids: tuple[str, ...],
    execution: PhaseIIIExecutionIdentity,
    allowed_mtz_root: Path | None = None,
) -> CrystalManifest:
    try:
        document = CrystalManifest.model_validate_json(path.read_bytes())
    except (ContractLoadError, OSError, ValidationError, ValueError) as error:
        raise UnknownDiscoveryInputError(
            "Phase III crystal manifest violates its typed contract"
        ) from error
    observed_ids = tuple(item.crystal_id for item in document.crystals)
    if observed_ids != tuple(sorted(crystal_ids)):
        raise UnknownDiscoveryInputError(
            "Phase III crystal manifest must contain the exact sorted reviewed panel"
        )
    artifact_ids = {
        item.owner_id for item in execution.crystal_artifacts if item.role == "mtz"
    }
    if artifact_ids != set(crystal_ids):
        raise UnknownDiscoveryInputError(
            "execution identity must bind every Phase III crystal MTZ"
        )
    for crystal in document.crystals:
        mtz = PurePosixPath(crystal.mtz)
        if (
            not mtz.is_absolute()
            or ".." in mtz.parts
            or mtz.suffix.lower() != ".mtz"
            or crystal.allow_remote_sequence_submission
            or crystal.free_r_test_value is None
        ):
            raise UnknownDiscoveryInputError(
                "Phase III crystals require absolute MTZ paths, explicit Free-R "
                "test values, and prohibited remote sequence submission"
            )
        if allowed_mtz_root is not None:
            try:
                root = allowed_mtz_root.resolve(strict=True)
                resolved_mtz = Path(crystal.mtz).resolve(strict=True)
            except OSError as error:
                raise UnknownDiscoveryInputError(
                    f"Phase III MTZ is absent for {crystal.crystal_id}"
                ) from error
            artifacts = tuple(
                item
                for item in execution.crystal_artifacts
                if item.owner_id == crystal.crystal_id and item.role == "mtz"
            )
            if (
                len(artifacts) != 1
                or not resolved_mtz.is_file()
                or not resolved_mtz.is_relative_to(root)
                or resolved_mtz.stat().st_size != artifacts[0].size_bytes
                or sha256_file(resolved_mtz, progress=False) != artifacts[0].sha256
            ):
                raise UnknownDiscoveryInputError(
                    f"Phase III MTZ differs from its P0 authority: {crystal.crystal_id}"
                )
    return document


def _add_file(archive: tarfile.TarFile, name: str, source: Path) -> None:
    info = archive.gettarinfo(str(source), arcname=name)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.mode = 0o600
    with source.open("rb") as handle:
        archive.addfile(info, handle)


def build_unknown_discovery_input_bundle(
    *,
    repository: Path,
    archive_path: Path,
) -> UnknownDiscoveryInputBundle:
    """Validate fixed local inputs and write one deterministic tar archive."""

    spec_path = repository / UNKNOWN_DISCOVERY_SPEC_RELATIVE
    spec = _owned_spec(spec_path)
    review_root = _absolute_path(
        spec["crystallographic_review_stage"],
        label="crystallographic review stage",
    )
    review_registry_root = _absolute_path(
        spec["crystallographic_review_registry"],
        label="crystallographic review registry",
    )
    execution_path = _absolute_path(
        spec["execution_identity"],
        label="Phase III execution identity",
    )
    afdb_path = _absolute_path(
        spec["afdb_accession_map"],
        label="AFDB accession map",
    )
    crystals_path = _absolute_path(
        spec["crystal_manifest"],
        label="Phase III crystal manifest",
    )
    localisation_root = _absolute_path(
        spec["localisation_bundle"],
        label="Phase III localisation bundle",
    )
    if (
        not execution_path.is_file()
        or not afdb_path.is_file()
        or not crystals_path.is_file()
    ):
        raise UnknownDiscoveryInputError(
            "unknown-discovery execution/map/crystal inputs must be regular files"
        )
    try:
        execution = PhaseIIIExecutionIdentity.model_validate(
            load_json_document(execution_path)
        )
    except (ContractLoadError, ValidationError, ValueError) as error:
        raise UnknownDiscoveryInputError(
            "Phase III execution identity violates its contract"
        ) from error
    index_path = review_root / "unknown_pass1_review_stage_index.json"
    try:
        index = validate_unknown_pass1_crystallographic_review_stages(index_path)
    except InputContractError as error:
        raise UnknownDiscoveryInputError(
            f"crystallographic review stage is invalid: {error}"
        ) from error
    if index.execution_identity_id != execution.execution_identity_id:
        raise UnknownDiscoveryInputError(
            "crystallographic review and execution identities differ"
        )
    try:
        registry = validate_phase3_owned_run_registry(review_registry_root)
    except (OSError, PhaseIIIOwnedRunError, ValueError) as error:
        raise UnknownDiscoveryInputError(
            f"crystallographic review registry is invalid: {error}"
        ) from error
    if (
        registry.owned_run_registry_id != index.owned_run_registry_id
        or registry.execution_identity_id != execution.execution_identity_id
        or registry.run_id != index.owned_parent_run_id
    ):
        raise UnknownDiscoveryInputError(
            "crystallographic review registry differs from its stage index"
        )
    crystal_ids = tuple(item.crystal_id for item in index.review_bindings)
    if len(crystal_ids) != 3:
        raise UnknownDiscoveryInputError(
            "unknown discovery requires exactly three reviewed crystals"
        )
    _phase3_crystal_manifest(
        crystals_path,
        crystal_ids=crystal_ids,
        execution=execution,
    )
    _validate_localisation_authority(
        root=localisation_root,
        execution=execution,
    )
    afdb_payload = _afdb_map(afdb_path)
    review_files = _review_files(review_root)
    review_registry_files = _review_registry_files(review_registry_root)
    localisation_files = _localisation_files(localisation_root)
    members = (
        *review_files,
        *review_registry_files,
        *localisation_files,
        (_EXECUTION_NAME, execution_path),
        (_AFDB_MAP_NAME, afdb_path),
        (_CRYSTALS_NAME, crystals_path),
    )
    file_records = [
        {
            "relative_path": name,
            "sha256": sha256_file(path, progress=False),
            "size_bytes": path.stat().st_size,
        }
        for name, path in members
    ]
    identity = {
        "adapter_version": "unknown-discovery-input-bundle-v3",
        "execution_identity_id": execution.execution_identity_id,
        "review_stage_index_id": index.stage_index_id,
        "review_registry_id": registry.owned_run_registry_id,
        "crystal_ids": list(crystal_ids),
        "files": file_records,
    }
    input_id = content_id("unknowninputs_", identity)
    manifest = {
        "schema_version": "1.0",
        "input_id": input_id,
        **identity,
    }
    if archive_path.exists() or archive_path.is_symlink():
        raise UnknownDiscoveryInputError(
            "unknown-discovery archive output must be absent"
        )
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="nf-gtd-unknown-inputs-", dir="/tmp"
    ) as tmp:
        manifest_path = Path(tmp) / UNKNOWN_DISCOVERY_MANIFEST_NAME
        atomic_write_json(manifest_path, manifest)
        with tarfile.open(archive_path, mode="w") as archive:
            for name, path in members:
                _add_file(archive, name, path)
            _add_file(
                archive,
                UNKNOWN_DISCOVERY_MANIFEST_NAME,
                manifest_path,
            )
    afdb_record = next(
        item for item in file_records if item["relative_path"] == _AFDB_MAP_NAME
    )
    if hashlib.sha256(afdb_payload).hexdigest() != afdb_record["sha256"]:
        raise AssertionError("AFDB map changed during archive construction")
    return UnknownDiscoveryInputBundle(
        input_id=input_id,
        execution_identity_id=execution.execution_identity_id,
        review_stage_index_id=index.stage_index_id,
        crystal_ids=(crystal_ids[0], crystal_ids[1], crystal_ids[2]),
        archive_path=archive_path,
        archive_sha256=sha256_file(archive_path, progress=False),
        archive_size_bytes=archive_path.stat().st_size,
        file_count=len(file_records),
    )


def validate_unknown_discovery_input_tree(
    input_root: Path,
    *,
    expected_input_id: str,
    expected_execution_identity_id: str,
    expected_review_stage_index_id: str,
    expected_source_commit: str | None = None,
    expected_source_tree: str | None = None,
    expected_nf_helper_commit: str | None = None,
    expected_pixi_lock_sha256: str | None = None,
    allowed_mtz_root: Path | None = None,
) -> None:
    """Authenticate an extracted private input tree against controller IDs."""

    if input_root.is_symlink():
        raise UnknownDiscoveryInputError(
            "unknown-discovery input tree must not be a symlink"
        )
    try:
        root = input_root.resolve(strict=True)
    except OSError as error:
        raise UnknownDiscoveryInputError(
            "unknown-discovery input tree is absent"
        ) from error
    if not root.is_dir():
        raise UnknownDiscoveryInputError(
            "unknown-discovery input tree must be a directory"
        )
    manifest_path = root / UNKNOWN_DISCOVERY_MANIFEST_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise UnknownDiscoveryInputError(
            "unknown-discovery input manifest is absent or unsafe"
        )
    try:
        manifest = load_json_document(manifest_path)
    except ContractLoadError as error:
        raise UnknownDiscoveryInputError(
            "unknown-discovery input manifest is malformed"
        ) from error
    expected_keys = {
        "schema_version",
        "input_id",
        "adapter_version",
        "execution_identity_id",
        "review_stage_index_id",
        "review_registry_id",
        "crystal_ids",
        "files",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_keys:
        raise UnknownDiscoveryInputError(
            "unknown-discovery input manifest differs from its fixed fields"
        )
    identity = {
        key: manifest[key] for key in expected_keys - {"schema_version", "input_id"}
    }
    if (
        manifest.get("schema_version") != "1.0"
        or manifest.get("adapter_version") != "unknown-discovery-input-bundle-v3"
        or manifest.get("input_id") != expected_input_id
        or content_id("unknowninputs_", identity) != expected_input_id
        or manifest.get("execution_identity_id") != expected_execution_identity_id
        or manifest.get("review_stage_index_id") != expected_review_stage_index_id
    ):
        raise UnknownDiscoveryInputError(
            "unknown-discovery input manifest identity differs"
        )
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise UnknownDiscoveryInputError(
            "unknown-discovery input manifest has no file inventory"
        )
    expected_files: dict[str, tuple[str, int]] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "relative_path",
            "sha256",
            "size_bytes",
        }:
            raise UnknownDiscoveryInputError(
                "unknown-discovery file inventory is malformed"
            )
        relative = record.get("relative_path")
        digest = record.get("sha256")
        size = record.get("size_bytes")
        if (
            not isinstance(relative, str)
            or not relative
            or relative.startswith("/")
            or ".." in Path(relative).parts
            or relative in expected_files
            or not isinstance(digest, str)
            or re.fullmatch(r"[a-f0-9]{64}", digest) is None
            or not isinstance(size, int)
            or size < 0
        ):
            raise UnknownDiscoveryInputError(
                "unknown-discovery file inventory contains an unsafe record"
            )
        expected_files[relative] = (digest, size)
    actual_files: dict[str, Path] = {}
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if path.is_symlink() or not path.is_file():
            raise UnknownDiscoveryInputError(
                "unknown-discovery input tree contains an unsafe member"
            )
        relative = path.relative_to(root).as_posix()
        if relative != UNKNOWN_DISCOVERY_MANIFEST_NAME:
            actual_files[relative] = path
    if set(actual_files) != set(expected_files):
        raise UnknownDiscoveryInputError(
            "unknown-discovery input tree differs from its file inventory"
        )
    for relative, path in actual_files.items():
        digest, size = expected_files[relative]
        if (
            path.stat().st_size != size
            or sha256_file(
                path,
                progress=False,
            )
            != digest
        ):
            raise UnknownDiscoveryInputError(
                "unknown-discovery input file changed after review"
            )
    execution_path = root / _EXECUTION_NAME
    try:
        execution = PhaseIIIExecutionIdentity.model_validate(
            load_json_document(execution_path)
        )
    except (ContractLoadError, ValidationError, ValueError) as error:
        raise UnknownDiscoveryInputError(
            "extracted Phase III execution identity is invalid"
        ) from error
    review_index = validate_unknown_pass1_crystallographic_review_stages(
        root / _REVIEW_ROOT_NAME / "unknown_pass1_review_stage_index.json"
    )
    try:
        review_registry = validate_phase3_owned_run_registry(
            root / _REVIEW_REGISTRY_ROOT_NAME
        )
    except (OSError, PhaseIIIOwnedRunError, ValueError) as error:
        raise UnknownDiscoveryInputError(
            f"extracted review registry is invalid: {error}"
        ) from error
    if (
        execution.execution_identity_id != expected_execution_identity_id
        or review_index.stage_index_id != expected_review_stage_index_id
        or review_index.execution_identity_id != execution.execution_identity_id
        or review_registry.owned_run_registry_id != manifest.get("review_registry_id")
        or review_registry.owned_run_registry_id != review_index.owned_run_registry_id
        or review_registry.execution_identity_id != execution.execution_identity_id
        or review_registry.run_id != review_index.owned_parent_run_id
    ):
        raise UnknownDiscoveryInputError(
            "extracted review and execution authorities differ"
        )
    expected_source_values = (
        expected_source_commit,
        expected_source_tree,
        expected_nf_helper_commit,
        expected_pixi_lock_sha256,
    )
    if any(value is not None for value in expected_source_values) and (
        any(value is None for value in expected_source_values)
        or (
            execution.source_commit != expected_source_commit
            or execution.source_tree != expected_source_tree
            or execution.nf_helper_commit != expected_nf_helper_commit
            or execution.pixi_lock_sha256 != expected_pixi_lock_sha256
        )
    ):
        raise UnknownDiscoveryInputError(
            "extracted execution identity differs from the staged source"
        )
    _afdb_map(root / _AFDB_MAP_NAME)
    _phase3_crystal_manifest(
        root / _CRYSTALS_NAME,
        crystal_ids=tuple(item.crystal_id for item in review_index.review_bindings),
        execution=execution,
        allowed_mtz_root=allowed_mtz_root,
    )
    _validate_localisation_authority(
        root=root / _LOCALISATION_ROOT_NAME,
        execution=execution,
    )


def main() -> int:
    """Validate one extracted tree for the reviewed remote dispatcher."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--expected-input-id", required=True)
    parser.add_argument("--expected-execution-identity-id", required=True)
    parser.add_argument("--expected-review-stage-index-id", required=True)
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--expected-source-tree")
    parser.add_argument("--expected-nf-helper-commit")
    parser.add_argument("--expected-pixi-lock-sha256")
    parser.add_argument("--allowed-mtz-root", type=Path)
    args = parser.parse_args()
    validate_unknown_discovery_input_tree(
        args.input_root,
        expected_input_id=args.expected_input_id,
        expected_execution_identity_id=args.expected_execution_identity_id,
        expected_review_stage_index_id=args.expected_review_stage_index_id,
        expected_source_commit=args.expected_source_commit,
        expected_source_tree=args.expected_source_tree,
        expected_nf_helper_commit=args.expected_nf_helper_commit,
        expected_pixi_lock_sha256=args.expected_pixi_lock_sha256,
        allowed_mtz_root=args.allowed_mtz_root,
    )
    return 0


__all__ = [
    "UNKNOWN_DISCOVERY_MANIFEST_NAME",
    "UNKNOWN_DISCOVERY_SPEC_RELATIVE",
    "UnknownDiscoveryInputBundle",
    "UnknownDiscoveryInputError",
    "build_unknown_discovery_input_bundle",
    "validate_unknown_discovery_input_tree",
]


if __name__ == "__main__":
    sys.exit(main())
