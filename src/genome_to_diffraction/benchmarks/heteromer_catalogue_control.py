"""Prepare the fixed full-catalogue 6RTZ partner-selection control."""

import gzip
import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from Bio import SeqIO

from genome_to_diffraction.benchmarks.heteromer_control import (
    HeteromerControlPreparationError,
    _control_pipeline_config,
    _prepared_file,
)
from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_sequence, content_id
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.schemas.manifests import CatalogueEntry, CatalogueManifest
from genome_to_diffraction.schemas.results import (
    ProcessedModelRecord,
    SequenceGroupRecord,
)

_CATALOGUE_ID = "cat-tmaritima"
_ASSEMBLY = "GCF_000008545.1"
_EXPECTED_PROTEIN_COUNT = 1846
_ADAPTER_VERSION = "6rtz-full-catalogue-partner-control-v1"
_PROTEOME_URL = (
    "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/008/545/"
    "GCF_000008545.1_ASM854v1/GCF_000008545.1_ASM854v1_protein.faa.gz"
)


@dataclass(frozen=True)
class HeteromerCatalogueControlRequest:
    """Protocol, fixed 6RTZ preparation, and optional frozen proteome."""

    protocol: Path
    control_preparation_manifest: Path
    output_directory: Path
    proteome_faa: Path | None = None
    download_missing: bool = False


@dataclass(frozen=True)
class HeteromerCatalogueControlResult:
    """Full FASTA, import manifest, config, and one-model HisH registry."""

    preparation_manifest: Path
    catalogue_manifest: Path
    pipeline_config: Path
    proteome_faa: Path
    partner_model_registry: Path
    protein_record_count: int
    parent_sequence_group_id: str
    partner_sequence_group_id: str


def _verify_proteome(path: Path, *, sha256: str, size_bytes: int) -> Path:
    resolved = path.resolve(strict=True)
    if (
        not resolved.is_file()
        or resolved.stat().st_size != size_bytes
        or sha256_file(resolved) != sha256
    ):
        raise HeteromerControlPreparationError("frozen Thermotoga proteome differs")
    return resolved


def _download_proteome(destination: Path, *, sha256: str, size_bytes: int) -> Path:
    if destination.exists():
        return _verify_proteome(destination, sha256=sha256, size_bytes=size_bytes)
    try:
        with urllib.request.urlopen(_PROTEOME_URL, timeout=120) as response:
            compressed = response.read(5 * 1024 * 1024 + 1)
        if len(compressed) > 5 * 1024 * 1024:
            raise HeteromerControlPreparationError(
                "compressed Thermotoga proteome exceeds fixed bound"
            )
        payload = gzip.decompress(compressed)
    except (OSError, urllib.error.URLError, gzip.BadGzipFile) as error:
        raise HeteromerControlPreparationError(
            f"cannot download fixed Thermotoga proteome: {error}"
        ) from error
    if len(payload) != size_bytes or hashlib.sha256(payload).hexdigest() != sha256:
        raise HeteromerControlPreparationError("downloaded Thermotoga proteome differs")
    atomic_write_bytes(destination, payload)
    return destination


def _sequence_groups(path: Path) -> dict[str, SequenceGroupRecord]:
    records: dict[str, SequenceGroupRecord] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = SequenceGroupRecord.model_validate_json(line)
            if record.sequence_group_id in records:
                raise HeteromerControlPreparationError(
                    "fixed 6RTZ sequence group is duplicated"
                )
            records[record.sequence_group_id] = record
    return records


def prepare_6rtz_partner_catalogue_control(
    request: HeteromerCatalogueControlRequest,
) -> HeteromerCatalogueControlResult:
    """Prepare the frozen 1,846-protein catalogue and exact HisH model registry."""

    output = request.output_directory.absolute()
    if output.exists() and any(output.iterdir()):
        raise HeteromerControlPreparationError(
            f"6RTZ catalogue-control output is not empty: {output}"
        )
    protocol = load_m6_protocol(request.protocol)
    catalogues = [
        item for item in protocol.catalogues if item.catalogue_id == _CATALOGUE_ID
    ]
    if len(catalogues) != 1:
        raise HeteromerControlPreparationError("Thermotoga catalogue is not unique")
    catalogue = catalogues[0]
    if request.download_missing:
        if request.proteome_faa is not None:
            raise HeteromerControlPreparationError(
                "download mode does not accept a proteome path"
            )
        proteome = _download_proteome(
            output / "sources" / f"{_ASSEMBLY}_protein.faa",
            sha256=catalogue.protein_fasta_sha256,
            size_bytes=catalogue.protein_fasta_size_bytes,
        )
    else:
        if request.proteome_faa is None:
            raise HeteromerControlPreparationError(
                "supply the frozen proteome or enable download mode"
            )
        source_proteome = _verify_proteome(
            request.proteome_faa,
            sha256=catalogue.protein_fasta_sha256,
            size_bytes=catalogue.protein_fasta_size_bytes,
        )
        proteome = output / "sources" / f"{_ASSEMBLY}_protein.faa"
        atomic_write_bytes(proteome, source_proteome.read_bytes())
    fasta_records = tuple(SeqIO.parse(proteome, "fasta"))
    if len(fasta_records) != _EXPECTED_PROTEIN_COUNT:
        raise HeteromerControlPreparationError(
            f"Thermotoga proteome contains {len(fasta_records)} proteins"
        )
    by_id = {record.id: canonical_sequence(str(record.seq)) for record in fasta_records}
    if len(by_id) != len(fasta_records):
        raise HeteromerControlPreparationError(
            "Thermotoga proteome contains duplicate protein IDs"
        )
    assumption = next(
        item for item in protocol.assumption_controls if item.target_key == "A01"
    )
    for protein in assumption.proteins:
        sequence = by_id.get(protein.protein_id)
        if (
            sequence is None
            or len(sequence) != protein.sequence_length
            or hashlib.sha256(sequence.encode("ascii")).hexdigest()
            != protein.sequence_sha256
        ):
            raise HeteromerControlPreparationError(
                f"Thermotoga catalogue protein differs: {protein.protein_id}"
            )

    output.mkdir(parents=True, exist_ok=True)
    catalogue_manifest = output / "catalogues.json"
    atomic_write_json(
        catalogue_manifest,
        CatalogueManifest(
            schema_version="1.0",
            catalogues=(
                CatalogueEntry(
                    catalogue_id=_CATALOGUE_ID,
                    proteome_faa=proteome.relative_to(output).as_posix(),
                    annotation_provider=catalogue.annotation_provider,
                    annotation_version="GCF_000008545.1-protein.faa-2026-08-17",
                    assembly_accession=_ASSEMBLY,
                    assembly_version="ASM854v1",
                    source_pipeline="NCBI Datasets",
                    is_contaminant_catalogue=False,
                    notes="Frozen full Thermotoga catalogue for the 6RTZ P5 control",
                ),
            ),
        ).model_dump(mode="json"),
    )
    pipeline_config = output / "pipeline_config.json"
    atomic_write_json(
        pipeline_config, _control_pipeline_config().model_dump(mode="json")
    )

    control_path = request.control_preparation_manifest.resolve(strict=True)
    raw_control = load_json_document(control_path)
    if not isinstance(raw_control, dict) or raw_control.get("crystal_id") != "6RTZ":
        raise HeteromerControlPreparationError("fixed 6RTZ preparation is invalid")
    parent_group_id = raw_control.get("parent_sequence_group_id")
    partner_group_id = raw_control.get("partner_sequence_group_id")
    files = raw_control.get("files")
    if not isinstance(parent_group_id, str) or not isinstance(partner_group_id, str):
        raise HeteromerControlPreparationError(
            "fixed 6RTZ sequence identities are absent"
        )
    partner_source = _prepared_file(
        control_path.parent,
        files,
        "partner_model",
    )
    control_groups = _sequence_groups(
        _prepared_file(control_path.parent, files, "sequence_groups")
    )
    partner_group = control_groups.get(partner_group_id)
    if partner_group is None or partner_group.molecular_mass_da is None:
        raise HeteromerControlPreparationError("fixed HisH sequence group is absent")
    model_sha256 = sha256_file(partner_source)
    registry = output / "partner_model_registry"
    model_path = registry / "models" / f"{model_sha256}.pdb"
    atomic_write_bytes(model_path, partner_source.read_bytes())
    mapping_id = content_id(
        "coordmap_",
        {"pdb_id": "6RTZ", "chain": "B", "sequence_sha256": partner_group.sha256},
    )
    coordinate_id = content_id(
        "coord_", {"mapping_id": mapping_id, "model_sha256": model_sha256}
    )
    model = ProcessedModelRecord(
        schema_version="1.0",
        model_id=content_id(
            "model_", {"coordinate_id": coordinate_id, "model_sha256": model_sha256}
        ),
        coordinate_id=coordinate_id,
        variant_type="experimental_cleaned_source_chain",
        residue_ranges=("B:polymer",),
        processing_tool="gemmi",
        processing_version="control-prepared",
        processing_parameters={
            "adapter_version": _ADAPTER_VERSION,
            "mapping_id": mapping_id,
            "sequence_identity": 1.0,
            "source_pdb_id": "6RTZ",
            "source_chain": "B",
        },
        model_mass_da=partner_group.molecular_mass_da,
        full_candidate_sequence_group_id=partner_group.sequence_group_id,
        model_sha256=model_sha256,
        quality_flags=("fixed_6rtz_exact_partner_control",),
    )
    processed_models = registry / "processed_models.jsonl"
    atomic_write_bytes(processed_models, f"{model.model_dump_json()}\n".encode())
    model_manifest = registry / "model_preparation_manifest.json"
    atomic_write_json(
        model_manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "processed_model_count": 1,
            "entries": [
                {
                    "model_id": model.model_id,
                    "model_path": model_path.relative_to(registry).as_posix(),
                    "model_sha256": model.model_sha256,
                    "retained_fraction": 1.0,
                }
            ],
        },
    )
    files_to_record = {
        "catalogue_manifest": catalogue_manifest,
        "pipeline_config": pipeline_config,
        "proteome_faa": proteome,
        "processed_models": processed_models,
        "model_registry_manifest": model_manifest,
        "partner_model": model_path,
    }
    preparation_manifest = output / "preparation_manifest.json"
    atomic_write_json(
        preparation_manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "catalogue_id": _CATALOGUE_ID,
            "assembly_accession": _ASSEMBLY,
            "protein_record_count": len(fasta_records),
            "parent_sequence_group_id": parent_group_id,
            "partner_sequence_group_id": partner_group_id,
            "partner_model_id": model.model_id,
            "source_proteome_url": _PROTEOME_URL,
            "source_proteome_sha256": catalogue.protein_fasta_sha256,
            "files": {
                role: {
                    "path": path.relative_to(output).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
                for role, path in files_to_record.items()
            },
        },
    )
    return HeteromerCatalogueControlResult(
        preparation_manifest=preparation_manifest,
        catalogue_manifest=catalogue_manifest,
        pipeline_config=pipeline_config,
        proteome_faa=proteome,
        partner_model_registry=registry,
        protein_record_count=len(fasta_records),
        parent_sequence_group_id=parent_group_id,
        partner_sequence_group_id=partner_group_id,
    )
