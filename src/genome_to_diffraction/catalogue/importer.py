"""Trusted protein-catalogue normalisation with lossless source provenance."""

import csv
import io
import logging
import os
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl
from Bio.SeqIO.FastaIO import SimpleFastaParser
from tqdm import tqdm

from genome_to_diffraction import __version__
from genome_to_diffraction.catalogue.annotations import (
    LocusMetadata,
    merge_locus_maps,
    read_gbff,
    read_gff,
    read_locus_tsv,
)
from genome_to_diffraction.catalogue.mass import (
    AMBIGUOUS_RESIDUES,
    DEFINED_NONSTANDARD_RESIDUES,
    MASS_METHOD,
    assess_mass,
    invalid_residues,
)
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import (
    canonical_json_text,
    canonical_sequence,
    content_id,
    sequence_digest,
    sequence_group_id,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    AmbiguousResiduePolicy,
    CatalogueEntry,
    CatalogueImportManifest,
    CatalogueInputRecord,
    CatalogueManifest,
    OutputArtifactRecord,
    PipelineConfig,
)
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.time import utc_now

_LOGGER = logging.getLogger("genome_to_diffraction.catalogue")


@dataclass(frozen=True)
class CatalogueImportRequest:
    """Explicit paths and user-interface settings for catalogue import."""

    catalogue_manifest: Path
    pipeline_config: Path
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True)
class CatalogueImportResult:
    """Validated records and manifest produced by one import."""

    manifest: CatalogueImportManifest
    sequence_groups: tuple[SequenceGroupRecord, ...]
    source_records: tuple[SourceProteinRecord, ...]


@dataclass(frozen=True)
class _ParsedProtein:
    original_id: str
    original_header: str
    description: str | None
    sequence: str
    occurrence: int
    initial_flags: tuple[str, ...]


def _resolve_input(path_text: str, manifest_path: Path) -> Path:
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"catalogue input is not a regular file: {resolved}")
    return resolved


def _input_paths(entry: CatalogueEntry, manifest_path: Path) -> dict[str, Path]:
    roles = {
        "proteome_faa": entry.proteome_faa,
        "genome_fasta": entry.genome_fasta,
        "annotation_gff": entry.annotation_gff,
        "annotation_gbff": entry.annotation_gbff,
        "protein_locus_map": entry.protein_locus_map,
    }
    return {
        role: _resolve_input(value, manifest_path)
        for role, value in roles.items()
        if value is not None
    }


def _read_fasta(path: Path, *, progress: bool) -> list[_ParsedProtein]:
    parsed: list[tuple[str, str, str | None, str]] = []
    with path.open(encoding="utf-8") as handle:
        iterator = tqdm(
            SimpleFastaParser(handle),  # type: ignore[no-untyped-call]
            desc=f"Read {path.name}",
            unit="protein",
            disable=not progress,
        )
        for title, raw_sequence in iterator:
            header_parts = title.split(maxsplit=1)
            original_id = header_parts[0] if header_parts else ""
            description = header_parts[1].strip() if len(header_parts) == 2 else None
            if not original_id:
                raise ValueError(f"{path}: FASTA record has an empty identifier")
            sequence = canonical_sequence(raw_sequence)
            parsed.append(
                (
                    original_id,
                    title,
                    description or None,
                    sequence,
                )
            )
    if not parsed:
        raise ValueError(f"{path}: protein FASTA contains no records")

    counts = Counter(item[0] for item in parsed)
    occurrences: Counter[str] = Counter()
    output: list[_ParsedProtein] = []
    for original_id, title, description, sequence in parsed:
        occurrences[original_id] += 1
        flags = ("duplicate_original_protein_id",) if counts[original_id] > 1 else ()
        output.append(
            _ParsedProtein(
                original_id=original_id,
                original_header=title,
                description=description,
                sequence=sequence,
                occurrence=occurrences[original_id],
                initial_flags=flags,
            )
        )
    return output


def _metadata_for(
    entry: CatalogueEntry, paths: dict[str, Path]
) -> dict[str, LocusMetadata]:
    maps: list[tuple[Path, dict[str, LocusMetadata]]] = []
    if path := paths.get("protein_locus_map"):
        maps.append((path, read_locus_tsv(path)))
    if path := paths.get("annotation_gff"):
        maps.append((path, read_gff(path)))
    if path := paths.get("annotation_gbff"):
        maps.append((path, read_gbff(path)))
    merged = merge_locus_maps(maps)
    _LOGGER.info(
        "loaded catalogue locus metadata",
        extra={"catalogue_id": entry.catalogue_id, "mapped_proteins": len(merged)},
    )
    return merged


def _normalise_sequence(
    parsed: _ParsedProtein,
    config: PipelineConfig,
    *,
    catalogue_id: str,
) -> tuple[str, tuple[str, ...]]:
    sequence = parsed.sequence
    flags = list(parsed.initial_flags)
    if sequence.endswith("*") and config.catalogue.remove_terminal_stop:
        sequence = sequence[:-1]
        flags.append("terminal_stop_removed")
        if not sequence:
            raise ValueError(
                f"{catalogue_id}:{parsed.original_id}: sequence is empty after "
                "terminal-stop removal"
            )
    elif sequence.endswith("*"):
        flags.append("terminal_stop_present")

    unsupported = invalid_residues(sequence)
    if unsupported:
        symbols = ", ".join(sorted(unsupported))
        raise ValueError(
            f"{catalogue_id}:{parsed.original_id}: unsupported residue symbols: "
            f"{symbols}"
        )
    review_residues = frozenset(sequence) & (
        frozenset(AMBIGUOUS_RESIDUES) | DEFINED_NONSTANDARD_RESIDUES
    )
    if review_residues:
        policy = config.catalogue.ambiguous_residue_policy
        rendered = ",".join(sorted(review_residues))
        if policy is AmbiguousResiduePolicy.ERROR:
            raise ValueError(
                f"{catalogue_id}:{parsed.original_id}: review residue(s) "
                f"{rendered} forbidden by ambiguous_residue_policy=error"
            )
        if policy is AmbiguousResiduePolicy.EXCLUDE:
            flags.append("excluded_ambiguous_or_nonstandard_residue")
        else:
            flags.append("review_ambiguous_or_nonstandard_residue")
    if len(sequence) < config.catalogue.min_length_aa:
        flags.append("excluded_below_minimum_length")
    return sequence, tuple(sorted(set(flags)))


def _source_record(
    *,
    parsed: _ParsedProtein,
    sequence: str,
    flags: tuple[str, ...],
    entry: CatalogueEntry,
    metadata: LocusMetadata | None,
) -> SourceProteinRecord:
    locus = metadata or LocusMetadata()
    group_id = sequence_group_id(sequence)
    identity = {
        "catalogue_id": entry.catalogue_id,
        "annotation_provider": entry.annotation_provider,
        "annotation_version": entry.annotation_version,
        "original_protein_id": parsed.original_id,
        "original_header": parsed.original_header,
        "occurrence": parsed.occurrence,
        "sequence_group_id": group_id,
        "locus_metadata": asdict(locus),
    }
    if metadata is None:
        flags = tuple(sorted({*flags, "locus_metadata_unavailable"}))
    return SourceProteinRecord(
        schema_version="1.0",
        source_record_id=content_id("src_", identity),
        catalogue_id=entry.catalogue_id,
        original_protein_id=parsed.original_id,
        original_header=parsed.original_header,
        description=parsed.description,
        sequence_group_id=group_id,
        locus_tag=locus.locus_tag,
        contig=locus.contig,
        start=locus.start,
        end=locus.end,
        strand=locus.strand,
        gene_name=locus.gene_name,
        product=locus.product,
        source_annotation_provider=entry.annotation_provider,
        quality_flags=flags,
    )


def _sequence_groups(
    sources: Sequence[SourceProteinRecord],
    sequences: dict[str, str],
) -> tuple[SequenceGroupRecord, ...]:
    grouped: dict[str, list[SourceProteinRecord]] = defaultdict(list)
    for source in sources:
        grouped[source.sequence_group_id].append(source)
    records: list[SequenceGroupRecord] = []
    for group_id in sorted(grouped):
        sequence = sequences[group_id]
        assessment = assess_mass(sequence)
        source_flags = {
            flag
            for source in grouped[group_id]
            for flag in source.quality_flags
            if flag
            not in {"duplicate_original_protein_id", "locus_metadata_unavailable"}
        }
        quality_flags = tuple(sorted(source_flags | set(assessment.quality_flags)))
        records.append(
            SequenceGroupRecord(
                schema_version="1.0",
                sequence_group_id=group_id,
                sha256=sequence_digest(sequence),
                sequence=sequence,
                length_aa=len(sequence),
                molecular_mass_da=assessment.exact_da,
                molecular_mass_lower_da=assessment.lower_da,
                molecular_mass_upper_da=assessment.upper_da,
                mass_method=MASS_METHOD,
                residue_policy=assessment.residue_policy,
                source_record_count=len(grouped[group_id]),
                quality_flags=quality_flags,
            )
        )
    return tuple(records)


def _write_jsonl(path: Path, records: Iterable[object]) -> None:
    lines = [canonical_json_text(record) for record in records]
    atomic_write_text(path, "\n".join(lines) + "\n")


def _tsv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, list | tuple):
        return ";".join(str(item) for item in value)
    return value


def _write_tsv(path: Path, records: Sequence[object], columns: Sequence[str]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=columns, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    for record in records:
        if not hasattr(record, "model_dump"):
            raise TypeError("TSV records must be Pydantic models")
        document = record.model_dump(mode="json")
        writer.writerow(
            {column: _tsv_value(document.get(column)) for column in columns}
        )
    atomic_write_text(path, stream.getvalue())


def _write_parquet(path: Path, records: Sequence[object]) -> None:
    documents = []
    for record in records:
        if not hasattr(record, "model_dump"):
            raise TypeError("Parquet records must be Pydantic models")
        documents.append(record.model_dump(mode="json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        pl.DataFrame(documents).write_parquet(temporary)
        os.replace(temporary, path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _write_outputs(
    output: Path,
    groups: tuple[SequenceGroupRecord, ...],
    sources: tuple[SourceProteinRecord, ...],
) -> dict[str, Path]:
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "exact_sequences_fasta": output / "exact_sequences.faa",
        "sequence_groups_jsonl": output / "sequence_groups.jsonl",
        "sequence_groups_tsv": output / "sequence_groups.tsv",
        "sequence_groups_parquet": output / "sequence_groups.parquet",
        "source_records_jsonl": output / "source_records.jsonl",
        "source_records_tsv": output / "source_records.tsv",
        "source_records_parquet": output / "source_records.parquet",
        "sequence_group_to_source_tsv": output / "sequence_group_to_source.tsv",
    }
    excluded_flags = {
        "excluded_ambiguous_or_nonstandard_residue",
        "excluded_below_minimum_length",
        "internal_stop",
    }
    fasta = "".join(
        f">{group.sequence_group_id} source_records={group.source_record_count}\n"
        f"{group.sequence}\n"
        for group in groups
        if not (set(group.quality_flags) & excluded_flags)
    )
    atomic_write_text(paths["exact_sequences_fasta"], fasta)
    _write_jsonl(paths["sequence_groups_jsonl"], groups)
    _write_tsv(
        paths["sequence_groups_tsv"],
        groups,
        tuple(SequenceGroupRecord.model_fields),
    )
    _write_parquet(paths["sequence_groups_parquet"], groups)
    _write_jsonl(paths["source_records_jsonl"], sources)
    _write_tsv(
        paths["source_records_tsv"],
        sources,
        tuple(SourceProteinRecord.model_fields),
    )
    _write_parquet(paths["source_records_parquet"], sources)
    mapping_stream = io.StringIO(newline="")
    writer = csv.writer(mapping_stream, delimiter="\t", lineterminator="\n")
    writer.writerow(
        ("sequence_group_id", "source_record_id", "catalogue_id", "original_protein_id")
    )
    for source in sources:
        writer.writerow(
            (
                source.sequence_group_id,
                source.source_record_id,
                source.catalogue_id,
                source.original_protein_id,
            )
        )
    atomic_write_text(paths["sequence_group_to_source_tsv"], mapping_stream.getvalue())
    return paths


def import_catalogues(request: CatalogueImportRequest) -> CatalogueImportResult:
    """Normalise trusted catalogues and write deterministic provenance outputs."""

    catalogue_path = request.catalogue_manifest.resolve(strict=True)
    config_path = request.pipeline_config.resolve(strict=True)
    output = request.output_directory.resolve()
    _LOGGER.info(
        "starting catalogue import",
        extra={
            "catalogue_manifest": str(catalogue_path),
            "pipeline_config": str(config_path),
            "output_directory": str(output),
        },
    )
    catalogues = load_contract(
        catalogue_path, "catalogue-manifest", progress=request.progress
    )
    config = load_contract(config_path, "pipeline-config", progress=request.progress)
    if not isinstance(catalogues, CatalogueManifest) or not isinstance(
        config, PipelineConfig
    ):
        raise TypeError("catalogue importer received unexpected contract models")

    manifest_sha = sha256_file(catalogue_path, progress=request.progress)
    config_sha = sha256_file(config_path, progress=request.progress)
    input_records: list[CatalogueInputRecord] = []
    source_records: list[SourceProteinRecord] = []
    sequences: dict[str, str] = {}

    for entry in tqdm(
        catalogues.catalogues,
        desc="Import catalogues",
        unit="catalogue",
        disable=not request.progress,
    ):
        paths = _input_paths(entry, catalogue_path)
        for role, path in sorted(paths.items()):
            input_records.append(
                CatalogueInputRecord(
                    catalogue_id=entry.catalogue_id,
                    role=role,
                    path=str(path),
                    sha256=sha256_file(path, progress=request.progress),
                )
            )
        metadata = _metadata_for(entry, paths)
        proteins = _read_fasta(paths["proteome_faa"], progress=request.progress)
        _LOGGER.info(
            "normalising trusted protein catalogue",
            extra={
                "catalogue_id": entry.catalogue_id,
                "protein_records": len(proteins),
                "annotation_provider": entry.annotation_provider,
            },
        )
        for parsed in tqdm(
            proteins,
            desc=f"Normalise {entry.catalogue_id}",
            unit="protein",
            disable=not request.progress,
            leave=False,
        ):
            sequence, flags = _normalise_sequence(
                parsed, config, catalogue_id=entry.catalogue_id
            )
            group_id = sequence_group_id(sequence)
            sequences[group_id] = sequence
            source_records.append(
                _source_record(
                    parsed=parsed,
                    sequence=sequence,
                    flags=flags,
                    entry=entry,
                    metadata=metadata.get(parsed.original_id),
                )
            )

    sources = tuple(sorted(source_records, key=lambda record: record.source_record_id))
    groups = _sequence_groups(sources, sequences)
    paths = _write_outputs(output, groups, sources)
    artifacts = tuple(
        OutputArtifactRecord(
            role=role,
            path=path.relative_to(output).as_posix(),
            size_bytes=path.stat().st_size,
            sha256=sha256_file(path, progress=request.progress),
        )
        for role, path in sorted(paths.items())
    )
    warning_counts = Counter(
        flag
        for flags in (
            *(group.quality_flags for group in groups),
            *(source.quality_flags for source in sources),
        )
        for flag in flags
    )
    warning_codes = tuple(sorted(warning_counts))
    if warning_counts:
        _LOGGER.warning(
            "catalogue import retained records requiring review",
            extra={"quality_flag_counts": dict(sorted(warning_counts.items()))},
        )
    identity = {
        "pipeline_config_sha256": config_sha,
        "catalogues": [
            entry.model_dump(
                mode="json",
                exclude={
                    "proteome_faa",
                    "genome_fasta",
                    "annotation_gff",
                    "annotation_gbff",
                    "protein_locus_map",
                },
            )
            for entry in catalogues.catalogues
        ],
        "inputs": [
            {
                "catalogue_id": record.catalogue_id,
                "role": record.role,
                "sha256": record.sha256,
            }
            for record in input_records
        ],
        "sequence_group_ids": [group.sequence_group_id for group in groups],
        "source_record_ids": [source.source_record_id for source in sources],
    }
    manifest = CatalogueImportManifest(
        schema_version="1.0",
        import_id=content_id("catimp_", identity),
        created_at=utc_now(),
        software_version=__version__,
        catalogue_ids=tuple(entry.catalogue_id for entry in catalogues.catalogues),
        catalogue_manifest_sha256=manifest_sha,
        pipeline_config_sha256=config_sha,
        inputs=tuple(input_records),
        outputs=artifacts,
        source_record_count=len(sources),
        sequence_group_count=len(groups),
        warning_count=sum(warning_counts.values()),
        warnings=warning_codes,
    )
    manifest_path = output / "catalogue_import_manifest.json"
    atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
    _LOGGER.info(
        "catalogue import complete",
        extra={
            "import_id": manifest.import_id,
            "catalogues": len(catalogues.catalogues),
            "source_records": len(sources),
            "sequence_groups": len(groups),
            "warnings": manifest.warning_count,
            "output_directory": str(output),
        },
    )
    return CatalogueImportResult(manifest, groups, sources)
