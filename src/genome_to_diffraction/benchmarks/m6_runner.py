"""Build a truth-isolated, checksum-addressed M6 runner archive.

The preparer is a trusted boundary.  Its manifest may point at locally prepared
MTZ, anonymised catalogue, policy, and fault-injection inputs, but the emitted
archive contains only opaque case IDs and content hashes.  Every byte is scanned
for stable truth tokens before a deterministic tar archive is written.

The module does not download data or execute the scientific workflow.  Missing,
changed, symlinked, or truth-bearing inputs fail closed.  The archive checksum is
the cache key used by the remote runner.
"""

import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.benchmarks.m6_prepare import (
    M6MtzSanitisationRecord,
    is_m6_ordinary_case_kind,
    verify_m6_ordinary_mtz_sanitisation,
)
from genome_to_diffraction.benchmarks.m6_protocol import (
    M6BenchmarkProtocol,
    load_m6_protocol,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import (
    atomic_write_json,
    sha256_file,
)
from genome_to_diffraction.schemas.base import (
    ContractModel,
    OperatorIdentifier,
    PositiveInt,
    Sha256Hex,
)
from genome_to_diffraction.schemas.io import load_json_document


class M6PreparedObjectSpec(ContractModel):
    """One already sanitised local object offered to the archive builder."""

    role: Literal[
        "catalogue",
        "reflections",
        "analysis_config",
        "model_policy",
        "fault_control",
    ]
    path: str = Field(min_length=1)
    sha256: Sha256Hex
    size_bytes: PositiveInt
    media_type: Literal[
        "application/json",
        "application/x-mtz",
        "text/plain",
        "text/x-fasta",
    ]


class M6PreparedCaseSpec(ContractModel):
    """Prepared inputs for one opaque benchmark case."""

    case_id: str = Field(pattern=r"^M6C[0-9]{3}$")
    objects: tuple[M6PreparedObjectSpec, ...] = Field(min_length=2)
    reflection_sanitisation: M6MtzSanitisationRecord | None = None

    @model_validator(mode="after")
    def _validate_roles(self) -> Self:
        roles = [item.role for item in self.objects]
        if len(roles) != len(set(roles)):
            raise ValueError("prepared case object roles must be unique")
        if not {"catalogue", "reflections", "analysis_config"} <= set(roles):
            raise ValueError(
                "prepared case requires catalogue, reflections, and analysis_config"
            )
        if self.reflection_sanitisation is not None:
            reflections = next(
                item for item in self.objects if item.role == "reflections"
            )
            if (
                reflections.sha256 != self.reflection_sanitisation.output_mtz_sha256
                or reflections.size_bytes
                != self.reflection_sanitisation.output_mtz_size_bytes
            ):
                raise ValueError(
                    "reflection sanitisation does not bind the prepared MTZ object"
                )
        return self


class M6PreparationManifest(ContractModel):
    """Local truth-boundary output consumed by the blind archive builder."""

    schema_version: Literal["1.0"]
    protocol_id: OperatorIdentifier
    protocol_sha256: Sha256Hex
    cases: tuple[M6PreparedCaseSpec, ...] = Field(min_length=63, max_length=63)

    @model_validator(mode="after")
    def _validate_case_ids(self) -> Self:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("preparation-manifest case IDs must be unique")
        return self


@dataclass(frozen=True)
class M6RunnerBundleRequest:
    """One bounded request to create a new runner directory and archive."""

    protocol: Path
    preparation_manifest: Path
    output_directory: Path
    archive: Path


@dataclass(frozen=True)
class M6RunnerBundleResult:
    """Stable identifiers for one verified truth-isolated runner bundle."""

    protocol_id: str
    case_count: int
    object_count: int
    runner_manifest: Path
    runner_manifest_sha256: str
    archive: Path
    archive_sha256: str


def load_m6_preparation_manifest(path: Path) -> M6PreparationManifest:
    """Load the local preparation record without resolving its objects yet."""

    resolved = path.resolve(strict=True)
    try:
        payload = load_json_document(resolved)
        return M6PreparationManifest.model_validate(payload)
    except (OSError, ValueError) as error:
        raise PublicControlError(
            f"invalid M6 preparation manifest {resolved}: {error}"
        ) from error


def _truth_tokens(protocol: M6BenchmarkProtocol) -> tuple[bytes, ...]:
    tokens: set[str] = set()
    for target in protocol.positives:
        tokens.update(
            {
                target.source.pdb_id,
                target.catalogue_id,
                target.target_protein_id,
                target.target_sequence_sha256,
                target.rcsb_30_cluster_line_sha256,
                target.rcsb_70_cluster_line_sha256,
            }
        )
    for control in protocol.assumption_controls:
        tokens.update(
            {
                control.source.pdb_id,
                control.catalogue_id,
            }
        )
        for protein in control.proteins:
            tokens.update({protein.protein_id, protein.sequence_sha256})
    tokens.update(catalogue.assembly_accession for catalogue in protocol.catalogues)
    tokens.update(protocol.leakage_policy.m5_positive_30_cluster_line_sha256)
    return tuple(
        token.encode("ascii")
        for token in sorted(tokens, key=lambda value: (len(value), value))
    )


def _verify_prepared_object(spec: M6PreparedObjectSpec) -> Path:
    source = Path(spec.path)
    if source.is_symlink():
        raise PublicControlError(f"M6 prepared object is a symlink: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as error:
        raise PublicControlError(f"M6 prepared object is missing: {source}") from error
    if not resolved.is_file():
        raise PublicControlError(f"M6 prepared object is not a file: {source}")
    if resolved.stat().st_size != spec.size_bytes:
        raise PublicControlError(f"M6 prepared object size changed: {resolved}")
    if sha256_file(resolved) != spec.sha256:
        raise PublicControlError(f"M6 prepared object checksum changed: {resolved}")
    return resolved


def _scan_truth_tokens(root: Path, tokens: tuple[bytes, ...]) -> None:
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("ascii")
        payload = path.read_bytes()
        for token in tokens:
            if token in relative or token in payload:
                raise PublicControlError(
                    "truth-isolation failure: a forbidden truth token is present "
                    f"in runner object {path.relative_to(root)}"
                )
    manifest = load_json_document(root / "runner_manifest.json")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), list):
        raise PublicControlError("runner manifest case inventory is invalid")
    serialised_keys: set[str] = set()
    for case in manifest["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("objects"), list):
            raise PublicControlError("runner manifest case object list is invalid")
        for item in case["objects"]:
            if not isinstance(item, dict):
                raise PublicControlError("runner manifest object record is invalid")
            serialised_keys.update(str(key) for key in item)
    if any("expected" in key or "truth" in key for key in serialised_keys):
        raise PublicControlError("runner manifest exposes a truth-bearing field")


def verify_m6_runner_truth_isolation(protocol_path: Path, runner_root: Path) -> None:
    """Re-run the frozen protocol's byte-level truth scan on an extracted bundle."""

    protocol = load_m6_protocol(protocol_path.resolve(strict=True))
    _scan_truth_tokens(runner_root.resolve(strict=True), _truth_tokens(protocol))


def _write_deterministic_tar(root: Path, archive: Path) -> None:
    if archive.exists() or archive.is_symlink():
        raise PublicControlError(f"M6 archive target already exists: {archive}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, mode="w", format=tarfile.PAX_FORMAT) as handle:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix()
            info = tarfile.TarInfo(relative)
            info.size = path.stat().st_size
            info.mode = 0o444
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            with path.open("rb") as source:
                handle.addfile(info, source)


def build_m6_runner_bundle(
    request: M6RunnerBundleRequest,
) -> M6RunnerBundleResult:
    """Build and byte-scan one deterministic truth-isolated runner archive."""

    protocol_path = request.protocol.resolve(strict=True)
    protocol = load_m6_protocol(protocol_path)
    preparation = load_m6_preparation_manifest(request.preparation_manifest)
    protocol_sha256 = sha256_file(protocol_path)
    if preparation.protocol_id != protocol.protocol_id:
        raise PublicControlError("M6 preparation and protocol IDs disagree")
    if preparation.protocol_sha256 != protocol_sha256:
        raise PublicControlError("M6 preparation was made from another protocol file")
    protocol_case_ids = {case.case_id for case in protocol.cases}
    preparation_case_ids = {case.case_id for case in preparation.cases}
    if preparation_case_ids != protocol_case_ids:
        raise PublicControlError("M6 preparation does not cover the frozen case matrix")

    if request.output_directory.exists() or request.output_directory.is_symlink():
        raise PublicControlError(
            f"M6 runner output target already exists: {request.output_directory}"
        )
    request.output_directory.mkdir(parents=True)
    output_root = request.output_directory.resolve(strict=True)
    object_root = output_root / "objects"
    object_root.mkdir()
    object_records: dict[str, dict[str, object]] = {}
    case_records: list[dict[str, object]] = []
    ordinary_case_ids = {
        case.case_id
        for case in protocol.cases
        if is_m6_ordinary_case_kind(case.case_kind)
    }
    for case in sorted(preparation.cases, key=lambda item: item.case_id):
        if case.case_id in ordinary_case_ids and case.reflection_sanitisation is None:
            raise PublicControlError(
                f"ordinary M6 case requires reflection sanitisation: {case.case_id}"
            )
        case_objects: list[dict[str, object]] = []
        for spec in sorted(case.objects, key=lambda item: item.role):
            source = _verify_prepared_object(spec)
            if (
                spec.role == "reflections"
                and case.case_id in ordinary_case_ids
                and case.reflection_sanitisation is not None
            ):
                verify_m6_ordinary_mtz_sanitisation(
                    source,
                    case.reflection_sanitisation,
                )
            object_name = spec.sha256
            destination = object_root / object_name
            if not destination.exists():
                destination.write_bytes(source.read_bytes())
                destination.chmod(0o444)
            object_records[object_name] = {
                "sha256": spec.sha256,
                "size_bytes": spec.size_bytes,
                "media_type": spec.media_type,
            }
            case_objects.append(
                {
                    "role": spec.role,
                    "object": object_name,
                    "sha256": spec.sha256,
                    "size_bytes": spec.size_bytes,
                    "media_type": spec.media_type,
                }
            )
        case_records.append({"case_id": case.case_id, "objects": case_objects})

    runner_manifest = output_root / "runner_manifest.json"
    atomic_write_json(
        runner_manifest,
        {
            "schema_version": "1.0",
            "protocol_id": protocol.protocol_id,
            "case_count": len(case_records),
            "object_count": len(object_records),
            "objects": object_records,
            "cases": case_records,
        },
    )
    _scan_truth_tokens(output_root, _truth_tokens(protocol))
    _write_deterministic_tar(output_root, request.archive)
    return M6RunnerBundleResult(
        protocol_id=protocol.protocol_id,
        case_count=len(case_records),
        object_count=len(object_records),
        runner_manifest=runner_manifest,
        runner_manifest_sha256=sha256_file(runner_manifest),
        archive=request.archive.resolve(strict=True),
        archive_sha256=sha256_file(request.archive),
    )
