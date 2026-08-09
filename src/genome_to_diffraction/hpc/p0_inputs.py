"""Build the fixed, checksum-frozen three-crystal Marmic P0 input bundle.

The bundle contains only the trusted catalogue files and three MTZ inputs named
by the private M0 manifests. Local paths are rewritten to a content-addressed
remote layout; no local workstation path is transferred.
"""

import csv
import gzip
import hashlib
import io
import json
import logging
import os
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel
from tqdm import tqdm

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.hpc.models import ValidationError
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.schemas.io import ContractError, load_contract
from genome_to_diffraction.schemas.manifests import (
    CatalogueEntry,
    CatalogueManifest,
    CrystalEntry,
    CrystalManifest,
)

P0_SPEC_FILENAME = "p0-inputs.json"
P0_PATHS_FILENAME = "hpc-p0.paths"
P0_ARCHIVE_MAX_BYTES = 128 * 1024 * 1024
_SPEC_KEYS = frozenset(
    {
        "schema_version",
        "database_manifest_sha256",
        "phenix_manifest_sha256",
    }
)
_SHA256 = frozenset("0123456789abcdef")
_INVENTORY_HEADER = ("role", "logical_id", "size_bytes", "sha256", "path")
_EXPECTED_CRYSTALS = (
    "AD4QS1P4G2_18",
    "CD4QS2P2G1_15",
    "CD6QS2P2G1_5",
)


@dataclass(frozen=True, slots=True)
class FrozenInput:
    """One locally verified file and its fixed archive identity."""

    role: str
    logical_id: str
    source: Path
    archive_path: PurePosixPath
    size_bytes: int
    sha256: str

    def as_identity(self) -> dict[str, str | int]:
        """Return the path-independent identity retained in bundle provenance."""

        return {
            "role": self.role,
            "logical_id": self.logical_id,
            "archive_path": self.archive_path.as_posix(),
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class P0InputBundle:
    """Identity and transfer evidence for one deterministic P0 archive."""

    source_id: str
    archive_path: Path
    archive_sha256: str
    archive_size_bytes: int
    database_manifest_sha256: str
    phenix_manifest_sha256: str
    scientific_input_count: int


def _require_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _SHA256 for character in value)
    ):
        raise ValidationError(f"{label} must be a lowercase SHA-256")
    return value


def _load_spec(path: Path, confirmation: str) -> tuple[str, str, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
        raise ValidationError("P0 input specification must be an owned regular file")
    payload = path.read_bytes()
    if not payload or len(payload) > 4096:
        raise ValidationError("P0 input specification must contain 1..4096 bytes")
    actual = hashlib.sha256(payload).hexdigest()
    if confirmation != actual:
        raise ValidationError(
            "P0 input specification confirmation must exactly equal its SHA-256"
        )
    try:
        document: Any = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(
            "P0 input specification must be valid UTF-8 JSON"
        ) from error
    if not isinstance(document, dict) or set(document) != _SPEC_KEYS:
        raise ValidationError(
            "P0 input specification must contain only the three documented keys"
        )
    if document.get("schema_version") != "1.0":
        raise ValidationError("P0 input specification schema_version must be '1.0'")
    return (
        actual,
        _require_sha256(
            document.get("database_manifest_sha256"),
            "database_manifest_sha256",
        ),
        _require_sha256(
            document.get("phenix_manifest_sha256"),
            "phenix_manifest_sha256",
        ),
    )


def _load_inventory(path: Path) -> dict[Path, tuple[str, str, int, str]]:
    if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
        raise ValidationError("frozen M0 input inventory is absent or unsafe")
    records: dict[Path, tuple[str, str, int, str]] = {}
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if tuple(reader.fieldnames or ()) != _INVENTORY_HEADER:
                raise ValidationError("frozen M0 input inventory header is invalid")
            for line_number, row in enumerate(reader, start=2):
                if None in row or any(
                    row[field] is None for field in _INVENTORY_HEADER
                ):
                    raise ValidationError(
                        f"frozen M0 input inventory row {line_number} is malformed"
                    )
                source = Path(row["path"])
                if not source.is_absolute() or source in records:
                    raise ValidationError(
                        f"invalid frozen M0 inventory path at row {line_number}"
                    )
                try:
                    size_bytes = int(row["size_bytes"])
                except ValueError as error:
                    raise ValidationError(
                        f"invalid frozen M0 inventory size at row {line_number}"
                    ) from error
                if size_bytes < 1:
                    raise ValidationError(
                        f"invalid frozen M0 inventory size at row {line_number}"
                    )
                digest = _require_sha256(
                    row["sha256"], f"inventory SHA-256 at row {line_number}"
                )
                records[source] = (
                    row["role"],
                    row["logical_id"],
                    size_bytes,
                    digest,
                )
    except OSError as error:
        raise ValidationError(
            f"cannot read frozen M0 input inventory: {error}"
        ) from error
    if not records:
        raise ValidationError("frozen M0 input inventory contains no records")
    return records


def _load_typed(path: Path, kind: str) -> BaseModel:
    if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
        raise ValidationError(f"fixed {kind} input is absent or unsafe")
    try:
        return load_contract(path, kind, progress=False)
    except ContractError as error:
        raise ValidationError(f"fixed {kind} input is invalid: {error}") from error


def _verify_input(
    source_value: str,
    *,
    role: str,
    logical_id: str,
    archive_path: str,
    data_root: Path,
    inventory: dict[Path, tuple[str, str, int, str]],
    progress: bool,
    logger: logging.Logger,
) -> FrozenInput:
    source = Path(source_value)
    if (
        not source.is_absolute()
        or source.is_symlink()
        or not source.is_file()
        or source.stat().st_uid != os.getuid()
    ):
        raise ValidationError(f"{role} input must be an absolute regular file")
    try:
        resolved = source.resolve(strict=True)
    except OSError as error:
        raise ValidationError(f"cannot resolve {role} input: {source}") from error
    if resolved != source or not resolved.is_relative_to(data_root):
        raise ValidationError(
            f"{role} input must remain below the fixed project data root"
        )
    record = inventory.get(source)
    if record is None:
        raise ValidationError(f"{role} input is absent from the frozen M0 inventory")
    recorded_role, recorded_id, recorded_size, recorded_digest = record
    if recorded_role != role or recorded_id != logical_id:
        raise ValidationError(f"{role} input inventory role or logical ID differs")
    size_bytes = source.stat().st_size
    if size_bytes != recorded_size:
        raise ValidationError(f"{role} input size differs from the frozen M0 inventory")
    digest = sha256_file(
        source,
        progress=progress,
        description=f"Verifying {role}",
        logger=logger,
        log_interval_bytes=64 * 1024 * 1024,
    )
    if digest != recorded_digest:
        raise ValidationError(
            f"{role} input SHA-256 differs from the frozen M0 inventory"
        )
    return FrozenInput(
        role=role,
        logical_id=logical_id,
        source=source,
        archive_path=PurePosixPath(archive_path),
        size_bytes=size_bytes,
        sha256=digest,
    )


def _json_bytes(model: BaseModel) -> bytes:
    return (
        json.dumps(
            model.model_dump(mode="json", exclude_none=False),
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _tar_info(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.size = size
    info.mode = 0o444
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def _write_archive(
    archive_path: Path,
    *,
    generated: dict[str, bytes],
    inputs: tuple[FrozenInput, ...],
    progress: bool,
) -> None:
    total_bytes = sum(len(value) for value in generated.values()) + sum(
        item.size_bytes for item in inputs
    )
    with (
        archive_path.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as tar,
        tqdm(
            total=total_bytes,
            desc="Packing P0 inputs",
            unit="B",
            unit_scale=True,
            disable=not progress,
        ) as bar,
    ):
        for name in sorted(generated):
            payload = generated[name]
            tar.addfile(_tar_info(name, len(payload)), io.BytesIO(payload))
            bar.update(len(payload))
        for item in sorted(inputs, key=lambda value: value.archive_path.as_posix()):
            info = _tar_info(item.archive_path.as_posix(), item.size_bytes)
            with item.source.open("rb") as handle:
                tar.addfile(info, handle)
            bar.update(item.size_bytes)


def build_p0_input_bundle(
    *,
    repository: Path,
    remote_root: PurePosixPath,
    spec_confirmation: str,
    archive_path: Path,
    progress: bool,
    logger: logging.Logger,
) -> P0InputBundle:
    """Validate frozen P0 inputs and write one deterministic transfer archive."""

    qualification_root = repository / ".untracked" / "m0-qualification"
    spec_path = qualification_root / P0_SPEC_FILENAME
    spec_sha256, database_sha256, phenix_sha256 = _load_spec(
        spec_path, spec_confirmation
    )
    data_root = repository.parent / "data"
    try:
        resolved_data_root = data_root.resolve(strict=True)
    except OSError as error:
        raise ValidationError("fixed project data root is absent") from error
    if (
        resolved_data_root != data_root
        or not data_root.is_dir()
        or data_root.stat().st_uid != os.getuid()
    ):
        raise ValidationError("fixed project data root is unsafe")

    catalogue_model = _load_typed(
        qualification_root / "manifests" / "catalogues.json", "catalogue-manifest"
    )
    crystal_model = _load_typed(
        qualification_root / "manifests" / "crystals.json", "crystal-manifest"
    )
    _load_typed(qualification_root / "manifests" / "config.yaml", "pipeline-config")
    if not isinstance(catalogue_model, CatalogueManifest) or not isinstance(
        crystal_model, CrystalManifest
    ):
        raise AssertionError("typed P0 contracts resolved to unexpected models")
    if len(catalogue_model.catalogues) != 1:
        raise ValidationError("fixed P0 bundle requires exactly one trusted catalogue")
    catalogue = catalogue_model.catalogues[0]
    if catalogue.protein_locus_map is not None:
        raise ValidationError(
            "fixed P0 bundle does not support an extra locus-map file"
        )
    crystal_by_id = {entry.crystal_id: entry for entry in crystal_model.crystals}
    if tuple(sorted(crystal_by_id)) != tuple(sorted(_EXPECTED_CRYSTALS)):
        raise ValidationError(
            "fixed P0 bundle requires the three frozen pilot crystals"
        )
    if any(
        entry.catalogue_id != catalogue.catalogue_id
        or entry.allow_remote_sequence_submission
        for entry in crystal_model.crystals
    ):
        raise ValidationError(
            "fixed P0 crystals must use one catalogue with remote submission disabled"
        )

    inventory = _load_inventory(qualification_root / "input-inventory.tsv")
    required_catalogue_paths = (
        (catalogue.proteome_faa, "proteome_faa", "inputs/proteome.faa"),
        (catalogue.genome_fasta, "genome_fasta", "inputs/genome.fna"),
        (catalogue.annotation_gff, "annotation_gff", "inputs/annotation.gff"),
        (catalogue.annotation_gbff, "annotation_gbff", "inputs/annotation.gbff"),
    )
    if any(value is None for value, _, _ in required_catalogue_paths):
        raise ValidationError(
            "fixed P0 catalogue lacks a required annotated-genome file"
        )
    inputs: list[FrozenInput] = []
    for value, role, archive_name in required_catalogue_paths:
        if value is None:
            raise AssertionError("required catalogue path unexpectedly absent")
        inputs.append(
            _verify_input(
                value,
                role=role,
                logical_id=catalogue.assembly_accession or catalogue.catalogue_id,
                archive_path=archive_name,
                data_root=data_root,
                inventory=inventory,
                progress=progress,
                logger=logger,
            )
        )
    for crystal_id in _EXPECTED_CRYSTALS:
        entry = crystal_by_id[crystal_id]
        inputs.append(
            _verify_input(
                entry.mtz,
                role="mtz",
                logical_id=crystal_id,
                archive_path=f"inputs/{crystal_id}.mtz",
                data_root=data_root,
                inventory=inventory,
                progress=progress,
                logger=logger,
            )
        )

    catalogue_source_sha = sha256_file(
        qualification_root / "manifests" / "catalogues.json"
    )
    crystal_source_sha = sha256_file(qualification_root / "manifests" / "crystals.json")
    config_path = qualification_root / "manifests" / "config.yaml"
    config_sha = sha256_file(config_path)
    identity = {
        "schema_version": "1.0",
        "spec_sha256": spec_sha256,
        "database_manifest_sha256": database_sha256,
        "phenix_manifest_sha256": phenix_sha256,
        "catalogue_manifest_sha256": catalogue_source_sha,
        "crystal_manifest_sha256": crystal_source_sha,
        "pipeline_config_sha256": config_sha,
        "inputs": [
            item.as_identity()
            for item in sorted(inputs, key=lambda value: value.archive_path.as_posix())
        ],
    }
    source_id = canonical_digest(identity)
    destination = remote_root / "_p0_inputs" / f"p0i_{source_id}"

    rewritten_catalogue = CatalogueManifest(
        schema_version="1.0",
        catalogues=(
            CatalogueEntry.model_validate(
                {
                    **catalogue.model_dump(mode="python"),
                    "proteome_faa": str(destination / "inputs/proteome.faa"),
                    "genome_fasta": str(destination / "inputs/genome.fna"),
                    "annotation_gff": str(destination / "inputs/annotation.gff"),
                    "annotation_gbff": str(destination / "inputs/annotation.gbff"),
                }
            ),
        ),
    )
    rewritten_crystals = CrystalManifest(
        schema_version="1.0",
        crystals=tuple(
            CrystalEntry.model_validate(
                {
                    **crystal_by_id[crystal_id].model_dump(mode="python"),
                    "mtz": str(destination / f"inputs/{crystal_id}.mtz"),
                }
            )
            for crystal_id in _EXPECTED_CRYSTALS
        ),
    )
    generated: dict[str, bytes] = {
        "manifests/catalogues.json": _json_bytes(rewritten_catalogue),
        "manifests/crystals.json": _json_bytes(rewritten_crystals),
        "manifests/config.yaml": config_path.read_bytes(),
    }
    bundle_manifest = {
        **identity,
        "source_id": f"p0i_{source_id}",
        "remote_layout": {
            "catalogue_manifest": "manifests/catalogues.json",
            "crystal_manifest": "manifests/crystals.json",
            "pipeline_config": "manifests/config.yaml",
        },
    }
    generated["bundle.json"] = (
        json.dumps(
            bundle_manifest,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")

    inventory_rows: list[str] = ["sha256\tsize_bytes\tpath"]
    for name in sorted(generated):
        payload = generated[name]
        inventory_rows.append(
            f"{hashlib.sha256(payload).hexdigest()}\t{len(payload)}\t{name}"
        )
    for item in sorted(inputs, key=lambda value: value.archive_path.as_posix()):
        inventory_rows.append(
            f"{item.sha256}\t{item.size_bytes}\t{item.archive_path.as_posix()}"
        )
    generated["inventory.tsv"] = ("\n".join(inventory_rows) + "\n").encode("ascii")

    logger.info(
        "building fixed P0 input archive",
        extra={
            "source_id": f"p0i_{source_id}",
            "scientific_input_count": len(inputs),
            "scientific_input_bytes": sum(item.size_bytes for item in inputs),
        },
    )
    _write_archive(
        archive_path,
        generated=generated,
        inputs=tuple(inputs),
        progress=progress,
    )
    archive_size = archive_path.stat().st_size
    if archive_size < 1 or archive_size > P0_ARCHIVE_MAX_BYTES:
        raise ValidationError(
            f"fixed P0 archive must contain 1..{P0_ARCHIVE_MAX_BYTES} bytes"
        )
    archive_sha = sha256_file(
        archive_path,
        progress=progress,
        description="Checksumming P0 archive",
        logger=logger,
        log_interval_bytes=64 * 1024 * 1024,
    )
    logger.info(
        "fixed P0 input archive ready",
        extra={
            "source_id": f"p0i_{source_id}",
            "archive_sha256": archive_sha,
            "archive_size_bytes": archive_size,
        },
    )
    return P0InputBundle(
        source_id=source_id,
        archive_path=archive_path,
        archive_sha256=archive_sha,
        archive_size_bytes=archive_size,
        database_manifest_sha256=database_sha256,
        phenix_manifest_sha256=phenix_sha256,
        scientific_input_count=len(inputs),
    )
