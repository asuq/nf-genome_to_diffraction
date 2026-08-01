"""Strict locus metadata adapters for trusted catalogue annotations."""

import csv
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Literal, cast
from urllib.parse import unquote

from Bio import SeqIO


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


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped and stripped != "." else None


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


def _add_unique(
    output: dict[str, LocusMetadata],
    protein_id: str,
    metadata: LocusMetadata,
    *,
    source: Path,
) -> None:
    existing = output.get(protein_id)
    if existing is not None and existing != metadata:
        raise ValueError(f"{source}: conflicting locus records for {protein_id!r}")
    output[protein_id] = metadata


def read_locus_tsv(path: Path) -> dict[str, LocusMetadata]:
    """Load an explicit protein-to-locus TSV with a required ``protein_id``."""

    output: dict[str, LocusMetadata] = {}
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
            strand = cast(Literal["+", "-", "."] | None, strand_text)
            _add_unique(
                output,
                protein_id,
                LocusMetadata(
                    locus_tag=_optional(row.get("locus_tag")),
                    contig=_optional(row.get("contig")),
                    start=start,
                    end=end,
                    strand=strand,
                    gene_name=_optional(row.get("gene_name")),
                    product=_optional(row.get("product")),
                ),
                source=path,
            )
    return output


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


def read_gff(path: Path) -> dict[str, LocusMetadata]:
    """Load CDS locus metadata from GFF3 attributes without inferring proteins."""

    output: dict[str, LocusMetadata] = {}
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
                gene_name=_optional(attributes.get("gene") or attributes.get("Name")),
                product=_optional(attributes.get("product")),
            )
            for alias in aliases:
                _add_unique(output, alias, metadata, source=path)
    return output


def _first_qualifier(qualifiers: dict[str, list[str]], name: str) -> str | None:
    values = qualifiers.get(name, [])
    return _optional(values[0]) if values else None


def read_gbff(path: Path) -> dict[str, LocusMetadata]:
    """Load CDS locus metadata from GenBank flat-file records."""

    output: dict[str, LocusMetadata] = {}
    for record in SeqIO.parse(path, "genbank"):  # type: ignore[no-untyped-call]
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
                gene_name=_first_qualifier(feature.qualifiers, "gene"),
                product=_first_qualifier(feature.qualifiers, "product"),
            )
            _add_unique(output, protein_id, metadata, source=path)
    return output


def merge_locus_maps(
    maps: list[tuple[Path, dict[str, LocusMetadata]]],
) -> dict[str, LocusMetadata]:
    """Merge compatible annotation sources and reject conflicting field values."""

    merged: dict[str, LocusMetadata] = {}
    for source, mapping in maps:
        for protein_id, incoming in mapping.items():
            existing = merged.get(protein_id)
            if existing is None:
                merged[protein_id] = incoming
                continue
            values: dict[str, str | int | None] = {}
            for field in fields(LocusMetadata):
                before = getattr(existing, field.name)
                after = getattr(incoming, field.name)
                if before is not None and after is not None and before != after:
                    raise ValueError(
                        f"{source}: conflicting {field.name} for protein "
                        f"{protein_id!r}: {before!r} != {after!r}"
                    )
                values[field.name] = before if before is not None else after
            merged[protein_id] = LocusMetadata(
                locus_tag=cast(str | None, values["locus_tag"]),
                contig=cast(str | None, values["contig"]),
                start=cast(int | None, values["start"]),
                end=cast(int | None, values["end"]),
                strand=cast(Literal["+", "-", "."] | None, values["strand"]),
                gene_name=cast(str | None, values["gene_name"]),
                product=cast(str | None, values["product"]),
            )
    return merged
