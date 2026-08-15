"""Strict locus metadata adapters for trusted catalogue annotations."""

import csv
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Literal, cast
from urllib.parse import unquote

from Bio import SeqIO

_LOGGER = logging.getLogger("genome_to_diffraction.catalogue.annotations")


@dataclass(frozen=True)
class LocusMetadata:
    """Optional genomic context associated with one source protein."""

    locus_tag: str | None = None
    contig: str | None = None
    start: int | None = None
    end: int | None = None
    strand: Literal["+", "-", "."] | None = None
    gene_name: str | None = None
    product: str | None = None
    quality_flags: tuple[str, ...] = ()


type LocusMap = dict[str, tuple[LocusMetadata, ...]]


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped and stripped != "." else None


def _annotation_text(value: str | None) -> str | None:
    text = _optional(value)
    if text is None:
        return None
    collapsed = " ".join(text.split())
    return re.sub(r"(?<=\S)-\s+(?=\S)", "-", collapsed)


def _coordinate(value: str | None, *, path: Path, row: int, field: str) -> int | None:
    text = _optional(value)
    if text is None:
        return None
    try:
        coordinate = int(text)
    except ValueError as error:
        raise ValueError(f"{path}:{row}:{field}: expected an integer") from error
    if coordinate < 1:
        raise ValueError(f"{path}:{row}:{field}: coordinate must be positive")
    return coordinate


def _locus_sort_key(
    metadata: LocusMetadata,
) -> tuple[str, int, int, str, str]:
    return (
        metadata.contig or "",
        metadata.start or 0,
        metadata.end or 0,
        metadata.strand or "",
        metadata.locus_tag or "",
    )


def _same_locus(before: LocusMetadata, after: LocusMetadata) -> bool:
    if before.locus_tag is not None and after.locus_tag is not None:
        return before.locus_tag == after.locus_tag
    coordinates = (
        before.contig,
        before.start,
        before.end,
        before.strand,
        after.contig,
        after.start,
        after.end,
        after.strand,
    )
    return (
        all(value is not None for value in coordinates)
        and coordinates[:4] == (coordinates[4:])
    )


def _merge_locus_metadata(
    existing: LocusMetadata,
    incoming: LocusMetadata,
    protein_id: str,
    *,
    source: Path,
) -> LocusMetadata:
    values: dict[str, str | int | None] = {}
    for field in fields(LocusMetadata):
        if field.name == "quality_flags":
            continue
        before = getattr(existing, field.name)
        after = getattr(incoming, field.name)
        if before is not None and after is not None and before != after:
            raise ValueError(
                f"{source}: conflicting {field.name} for protein "
                f"{protein_id!r}: {before!r} != {after!r}"
            )
        values[field.name] = before if before is not None else after
    return LocusMetadata(
        locus_tag=cast(str | None, values["locus_tag"]),
        contig=cast(str | None, values["contig"]),
        start=cast(int | None, values["start"]),
        end=cast(int | None, values["end"]),
        strand=cast(Literal["+", "-", "."] | None, values["strand"]),
        gene_name=cast(str | None, values["gene_name"]),
        product=cast(str | None, values["product"]),
        quality_flags=tuple(sorted({*existing.quality_flags, *incoming.quality_flags})),
    )


def _append_locus(
    output: dict[str, list[LocusMetadata]],
    protein_id: str,
    metadata: LocusMetadata,
    *,
    source: Path,
) -> None:
    records = output.setdefault(protein_id, [])
    for index, existing in enumerate(records):
        if existing == metadata:
            return
        if _same_locus(existing, metadata):
            records[index] = _merge_locus_metadata(
                existing, metadata, protein_id, source=source
            )
            return
    records.append(metadata)


def _add_gff_segment(
    output: dict[tuple[str, str], LocusMetadata],
    protein_id: str,
    feature_key: str,
    metadata: LocusMetadata,
    *,
    source: Path,
    log_merge: bool,
) -> None:
    """Merge compatible rows for one compound CDS while rejecting conflicts."""

    key = (protein_id, feature_key)
    existing = output.get(key)
    if existing is None or existing == metadata:
        output[key] = metadata
        return

    values: dict[str, str | int | None] = {}
    for field_name in ("locus_tag", "contig", "strand", "gene_name", "product"):
        before = getattr(existing, field_name)
        after = getattr(metadata, field_name)
        if before is not None and after is not None and before != after:
            raise ValueError(
                f"{source}: conflicting {field_name} for split CDS "
                f"{protein_id!r}: {before!r} != {after!r}"
            )
        values[field_name] = before if before is not None else after

    if existing.start is None or existing.end is None:
        raise ValueError(f"{source}: split CDS {protein_id!r} lacks coordinates")
    if metadata.start is None or metadata.end is None:
        raise ValueError(f"{source}: split CDS {protein_id!r} lacks coordinates")

    merged = LocusMetadata(
        locus_tag=cast(str | None, values["locus_tag"]),
        contig=cast(str | None, values["contig"]),
        start=min(existing.start, metadata.start),
        end=max(existing.end, metadata.end),
        strand=cast(Literal["+", "-", "."] | None, values["strand"]),
        gene_name=cast(str | None, values["gene_name"]),
        product=cast(str | None, values["product"]),
        quality_flags=tuple(
            sorted(
                {
                    *existing.quality_flags,
                    *metadata.quality_flags,
                    "compound_cds_segments_merged",
                }
            )
        ),
    )
    output[key] = merged
    if log_merge:
        _LOGGER.warning(
            "merged compatible GFF CDS segments",
            extra={
                "protein_id": protein_id,
                "contig": merged.contig,
                "start": merged.start,
                "end": merged.end,
                "source": str(source),
            },
        )


def _freeze_locus_map(output: dict[str, list[LocusMetadata]]) -> LocusMap:
    return {
        protein_id: tuple(sorted(records, key=_locus_sort_key))
        for protein_id, records in output.items()
    }


def read_locus_tsv(path: Path) -> LocusMap:
    """Load an explicit protein-to-locus TSV with a required ``protein_id``."""

    output: dict[str, list[LocusMetadata]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or "protein_id" not in reader.fieldnames:
            raise ValueError(f"{path}: locus TSV requires a protein_id column")
        for row_number, row in enumerate(reader, start=2):
            protein_id = _optional(row.get("protein_id"))
            if protein_id is None:
                raise ValueError(f"{path}:{row_number}:protein_id: value is required")
            start = _coordinate(
                row.get("start"), path=path, row=row_number, field="start"
            )
            end = _coordinate(row.get("end"), path=path, row=row_number, field="end")
            if (start is None) != (end is None):
                raise ValueError(
                    f"{path}:{row_number}: start and end must occur together"
                )
            if start is not None and end is not None and start > end:
                raise ValueError(f"{path}:{row_number}: start must not exceed end")
            strand_text = _optional(row.get("strand"))
            if strand_text not in {None, "+", "-", "."}:
                raise ValueError(f"{path}:{row_number}:strand: expected +, -, or .")
            strand = strand_text
            _append_locus(
                output,
                protein_id,
                LocusMetadata(
                    locus_tag=_optional(row.get("locus_tag")),
                    contig=_optional(row.get("contig")),
                    start=start,
                    end=end,
                    strand=strand,
                    gene_name=_annotation_text(row.get("gene_name")),
                    product=_annotation_text(row.get("product")),
                ),
                source=path,
            )
    return _freeze_locus_map(output)


def _gff_attributes(text: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for item in text.split(";"):
        if not item:
            continue
        key, separator, value = item.partition("=")
        if not separator:
            continue
        attributes[unquote(key)] = unquote(value)
    return attributes


def read_gff(path: Path) -> LocusMap:
    """Load CDS locus metadata from GFF3 attributes without inferring proteins."""

    segments: dict[tuple[str, str], LocusMetadata] = {}
    with path.open(encoding="utf-8") as handle:
        for row_number, line in enumerate(handle, start=1):
            if line.startswith("##FASTA"):
                break
            if not line.strip() or line.startswith("#"):
                continue
            columns = line.rstrip("\n").split("\t")
            if len(columns) != 9:
                raise ValueError(f"{path}:{row_number}: expected nine GFF3 columns")
            if columns[2] != "CDS":
                continue
            attributes = _gff_attributes(columns[8])
            aliases: list[str] = []
            for key in ("protein_id", "ID", "Parent", "locus_tag"):
                aliases.extend(
                    value for value in attributes.get(key, "").split(",") if value
                )
            aliases = list(dict.fromkeys(aliases))
            if not aliases:
                continue
            start = _coordinate(columns[3], path=path, row=row_number, field="start")
            end = _coordinate(columns[4], path=path, row=row_number, field="end")
            metadata = LocusMetadata(
                locus_tag=_optional(attributes.get("locus_tag")),
                contig=_optional(columns[0]),
                start=start,
                end=end,
                strand=cast(Literal["+", "-", "."] | None, _optional(columns[6])),
                gene_name=_annotation_text(attributes.get("gene")),
                product=_annotation_text(attributes.get("product")),
            )
            primary_alias = _optional(attributes.get("protein_id")) or aliases[0]
            feature_key = (
                _optional(attributes.get("locus_tag"))
                or _optional(attributes.get("ID"))
                or _optional(attributes.get("Parent"))
                or f"{columns[0]}:{columns[3]}-{columns[4]}:{columns[6]}"
            )
            for alias in aliases:
                _add_gff_segment(
                    segments,
                    alias,
                    feature_key,
                    metadata,
                    source=path,
                    log_merge=alias == primary_alias,
                )
    output: dict[str, list[LocusMetadata]] = defaultdict(list)
    for (alias, _), metadata in segments.items():
        _append_locus(output, alias, metadata, source=path)
    return _freeze_locus_map(output)


def _first_qualifier(qualifiers: dict[str, list[str]], name: str) -> str | None:
    values = qualifiers.get(name, [])
    return _optional(values[0]) if values else None


def read_gbff(path: Path) -> LocusMap:
    """Load CDS locus metadata from GenBank flat-file records."""

    output: dict[str, list[LocusMetadata]] = {}
    for record in SeqIO.parse(path, "genbank"):
        for feature in record.features:
            if feature.type != "CDS":
                continue
            protein_id = _first_qualifier(feature.qualifiers, "protein_id")
            if protein_id is None:
                continue
            strand_number = feature.location.strand
            strand: Literal["+", "-", "."] = (
                "+" if strand_number == 1 else "-" if strand_number == -1 else "."
            )
            metadata = LocusMetadata(
                locus_tag=_first_qualifier(feature.qualifiers, "locus_tag"),
                contig=record.id,
                start=int(feature.location.start) + 1,
                end=int(feature.location.end),
                strand=strand,
                gene_name=_annotation_text(
                    _first_qualifier(feature.qualifiers, "gene")
                ),
                product=_annotation_text(
                    _first_qualifier(feature.qualifiers, "product")
                ),
                quality_flags=(
                    ("compound_cds_segments_merged",)
                    if len(feature.location.parts) > 1
                    else ()
                ),
            )
            _append_locus(output, protein_id, metadata, source=path)
    return _freeze_locus_map(output)


def merge_locus_maps(
    maps: list[tuple[Path, LocusMap]],
) -> LocusMap:
    """Merge compatible annotation sources and reject conflicting field values."""

    merged: dict[str, list[LocusMetadata]] = {}
    for source, mapping in maps:
        for protein_id, incoming_records in mapping.items():
            for incoming in incoming_records:
                _append_locus(merged, protein_id, incoming, source=source)
    return _freeze_locus_map(merged)
