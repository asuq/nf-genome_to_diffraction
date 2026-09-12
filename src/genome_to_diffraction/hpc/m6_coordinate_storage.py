"""Derive the fixed Marmic coordinate-import budget from its complete layout.

Inputs are the authenticated missing-entry count and observed per-root statvfs
fragment sizes. The unchanged conservative archive, extraction, report, cache
and atomic-publication bounds must fit the approved 12 GiB total. Reserve the
artifact bound first and assign the remaining budget to the cache; both are
positive and their sum is exactly the approved cap. No disk I/O, free-space or
quota guarantee, scientific selection, external command or persistent cache is
involved. The pinned Python runtime is sufficient. Invalid inputs and excessive
layouts raise ValidationError before writes. The importer and client use the
same calculation; tests cover full-count admission, rejection and report tampering.
"""

from genome_to_diffraction.hpc.m6_coordinate_prefetch import (
    MAX_ADDITIONAL_DISK_BYTES,
    MAX_COORDINATE_OBJECT_BYTES,
    MAX_COORDINATE_TOTAL_BYTES,
    MAX_PREFETCH_ARCHIVE_BYTES,
    MAX_PREFETCH_MANIFEST_BYTES,
)
from genome_to_diffraction.hpc.models import (
    MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES,
    MAX_REVIEW_ARTIFACT_FILE_BYTES,
    MAX_REVIEW_ARTIFACT_TOTAL_BYTES,
    ValidationError,
)


def coordinate_storage_reservations(
    missing_pdb_count: int, *, artifacts_frsize_bytes: int, cache_frsize_bytes: int
) -> tuple[int, int]:
    """Return artifact/cache reservations whose sum is exactly the approved cap."""

    if type(missing_pdb_count) is not int or missing_pdb_count < 0:
        raise ValidationError("coordinate import missing-entry count is invalid")
    if any(
        type(value) is not int or value <= 0
        for value in (artifacts_frsize_bytes, cache_frsize_bytes)
    ):
        raise ValidationError("coordinate import filesystem allocation unit is unknown")
    # Retain the complete simultaneous archive, extraction, report and spool bound.
    artifact_peak = (
        MAX_PREFETCH_ARCHIVE_BYTES
        + MAX_COORDINATE_TOTAL_BYTES
        + MAX_PREFETCH_MANIFEST_BYTES
        + MAX_REVIEW_ARTIFACT_TOTAL_BYTES
        + MAX_REVIEW_ARTIFACT_FILE_BYTES
        + MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES
        + (missing_pdb_count + 32) * artifacts_frsize_bytes
    )
    # Sidecars reuse manifest provenance. Retain 1 KiB of extra fields per entry,
    # eight allocation units per entry and the bounded shard-directory overhead.
    cache_peak = (
        MAX_COORDINATE_TOTAL_BYTES
        + MAX_COORDINATE_OBJECT_BYTES
        + MAX_PREFETCH_MANIFEST_BYTES
        + missing_pdb_count * 1024
        + (8 * missing_pdb_count + 512) * cache_frsize_bytes
    )
    if artifact_peak + cache_peak > MAX_ADDITIONAL_DISK_BYTES:
        raise ValidationError(
            "coordinate import declared layout cannot fit the approved disk budget"
            f"; missing_pdb_count={missing_pdb_count}"
            f" artifacts_frsize_bytes={artifacts_frsize_bytes}"
            f" cache_frsize_bytes={cache_frsize_bytes}"
            f" artifacts_estimated_peak_bytes={artifact_peak}"
            f" cache_estimated_peak_bytes={cache_peak}"
            f" total_estimated_peak_bytes={artifact_peak + cache_peak}"
            f" additional_disk_limit_bytes={MAX_ADDITIONAL_DISK_BYTES}"
        )
    return artifact_peak, MAX_ADDITIONAL_DISK_BYTES - artifact_peak
