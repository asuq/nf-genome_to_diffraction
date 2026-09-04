"""Build the bundled MATTPROB protein reference from the published 2013 data.

This developer-only tool never downloads data.  Supply the exact
``kernel_data_tables_2013.zip`` archive published with Weichenberger & Rupp
(2014). The output is a deterministic, identifier-free gzip JSON resource
containing only resolution/solvent pairs and homooligomer copy frequencies
needed by the runtime probability estimator.
"""

from __future__ import annotations

import argparse
import collections
import csv
import gzip
import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

SOURCE_URL = "https://www.ruppweb.org/mattprob/kernel_data_tables_2013.zip"
SOURCE_ARCHIVE_SHA256 = (
    "232dd75da88abb1990be1dd20f71d56ea54193d252166d6df6efca57ba62c031"
)
PROTEIN_MEMBER = "pdb_02_06_2013_pro_sorted_flagged_highest_cs.csv"
PROTEIN_MEMBER_SHA256 = (
    "3432ae0a2b4771e17a3cc2b8eec63999cabdfe0d3cacb16bc2bd5c485f5c30d0"
)
BACKEND_ID = "mattprob_kde_2013_resolution_cumulative_pn_v1"
SOLVENT_DENSITY_BACKEND = "mattprob_kde_2013_resolution_cumulative_v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_source(
    archive: Path,
) -> tuple[bytes, list[tuple[int, int]], int, collections.Counter[int]]:
    archive_bytes = archive.read_bytes()
    if _sha256(archive_bytes) != SOURCE_ARCHIVE_SHA256:
        raise ValueError("MATTPROB source archive checksum differs")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as handle:
        if tuple(sorted(handle.namelist())) != (
            "pdb_02_06_2013_mix_sorted_flagged_highest_cs.csv",
            "pdb_02_06_2013_nuc_sorted_flagged_highest_cs.csv",
            PROTEIN_MEMBER,
        ):
            raise ValueError("MATTPROB source archive member inventory differs")
        member_bytes = handle.read(PROTEIN_MEMBER)
    if _sha256(member_bytes) != PROTEIN_MEMBER_SHA256:
        raise ValueError("MATTPROB protein reference checksum differs")

    reader = csv.DictReader(io.StringIO(member_bytes.decode("ascii")))
    expected_columns = {
        "code",
        "ncs",
        "reso",
        "vs",
    }
    if reader.fieldnames is None or not expected_columns.issubset(reader.fieldnames):
        raise ValueError("MATTPROB protein reference columns differ")
    records: list[tuple[int, int]] = []
    copy_counts: collections.Counter[int] = collections.Counter()
    excluded = 0
    for row_number, row in enumerate(reader, start=2):
        try:
            resolution = float(row["reso"])
            solvent_percent = float(row["vs"])
            asu_copy_count = int(row["ncs"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid MATTPROB reference row {row_number}") from error
        if asu_copy_count > 0:
            copy_counts[asu_copy_count] += 1
        if resolution <= 0 or not 0 < solvent_percent < 100:
            excluded += 1
            continue
        records.append(
            (
                round(resolution * 1000),
                round((solvent_percent / 100.0) * 1_000_000),
            )
        )
    if len(records) < 50_000:
        raise ValueError("MATTPROB protein reference has too few usable rows")
    if sum(copy_counts.values()) != 50_190:
        raise ValueError("MATTPROB homooligomer copy-count inventory differs")
    records.sort()
    return member_bytes, records, excluded, copy_counts


def _payload(archive: Path) -> bytes:
    member_bytes, records, excluded, copy_counts = _read_source(archive)
    records_bytes = json.dumps(records, separators=(",", ":")).encode("ascii")
    document = {
        "schema_version": "1.0",
        "backend_id": BACKEND_ID,
        "solvent_density_backend_id": SOLVENT_DENSITY_BACKEND,
        "source": {
            "url": SOURCE_URL,
            "archive_sha256": SOURCE_ARCHIVE_SHA256,
            "member": PROTEIN_MEMBER,
            "member_sha256": _sha256(member_bytes),
            "citation": (
                "Weichenberger CX, Rupp B. Acta Cryst D70, 1579-1588 (2014); "
                "doi:10.1107/S1399004714005550"
            ),
        },
        "filters": {
            "macromolecule_type": "protein",
            "resolution_a": "finite_and_strictly_positive",
            "solvent_fraction": "strictly_between_zero_and_one",
            "resolution_conditioning": (
                "reference_resolution_less_than_or_equal_to_query"
            ),
        },
        "quantisation": {
            "resolution": "milliangstrom",
            "solvent_fraction": "parts_per_million",
        },
        "source_row_count": len(records) + excluded,
        "reference_record_count": len(records),
        "excluded_record_count": excluded,
        "homooligomer_copy_count_reference_count": sum(copy_counts.values()),
        "homooligomer_copy_count_occurrences": sorted(copy_counts.items()),
        "records_sha256": _sha256(records_bytes),
        "records": records,
    }
    return json.dumps(
        document,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def build_reference(archive: Path, output: Path) -> None:
    """Validate the published archive and write one deterministic resource."""

    payload = _payload(archive.resolve(strict=True))
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as raw_handle:
            temporary = Path(raw_handle.name)
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_handle,
                mtime=0,
            ) as compressed:
                compressed.write(payload)
        temporary.chmod(0o644)
        os.replace(temporary, output)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    build_reference(arguments.archive, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
