"""Resolution-aware empirical Matthews priors for protein crystals.

The estimator follows the cumulative-resolution kernel strategy described by
Weichenberger & Rupp (2014) and their 2015 implementation note. A compact,
identifier-free copy of the published 2013 protein reference supplies the
resolution/solvent pairs and homooligomer copy frequencies needed for the
calculation.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any

import numpy as np
from numpy.typing import NDArray

PRIOR_BACKEND = "mattprob_kde_2013_resolution_cumulative_pn_v1"
SOLVENT_DENSITY_BACKEND = "mattprob_kde_2013_resolution_cumulative_v1"
REFERENCE_RESOURCE = "data/protein_mattprob_2013.json.gz"
REFERENCE_RESOURCE_SHA256 = (
    "4114691d739f79ade662dc9ee1df5bd5f0e89c0499d1175337c7295b0191d906"
)
REFERENCE_ARCHIVE_SHA256 = (
    "232dd75da88abb1990be1dd20f71d56ea54193d252166d6df6efca57ba62c031"
)
REFERENCE_MEMBER_SHA256 = (
    "3432ae0a2b4771e17a3cc2b8eec63999cabdfe0d3cacb16bc2bd5c485f5c30d0"
)
MINIMUM_REFERENCE_RECORDS = 200
KDE_GRID_SIZE = 2001
KDE_GAUSSIAN_SUPPORT_BANDWIDTHS = 4.0


class MatthewsProbabilityError(ValueError):
    """The empirical reference or requested probability is invalid."""


@dataclass(frozen=True)
class MatthewsProbabilityDistribution:
    """One cumulative-resolution solvent-fraction density estimate."""

    resolution_high_a: float
    reference_record_count: int
    bandwidth_fraction: float
    solvent_grid: NDArray[np.float64]
    relative_density: NDArray[np.float64]

    def score(self, solvent_fraction: float) -> float:
        """Return relative empirical density in the closed interval [0, 1]."""

        if not math.isfinite(solvent_fraction):
            raise MatthewsProbabilityError("solvent fraction must be finite")
        if not 0 <= solvent_fraction <= 1:
            return 0.0
        return float(
            np.interp(solvent_fraction, self.solvent_grid, self.relative_density)
        )

    def score_interval(self, lower: float, upper: float) -> float:
        """Average the relative density across one bounded solvent interval."""

        if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
            raise MatthewsProbabilityError("solvent interval is invalid")
        clipped_lower = max(0.0, lower)
        clipped_upper = min(1.0, upper)
        if clipped_lower > clipped_upper:
            return 0.0
        if clipped_lower == clipped_upper:
            return self.score(clipped_lower)
        interior = self.solvent_grid[
            (self.solvent_grid > clipped_lower) & (self.solvent_grid < clipped_upper)
        ]
        points = np.concatenate(
            (
                np.asarray([clipped_lower], dtype=np.float64),
                interior,
                np.asarray([clipped_upper], dtype=np.float64),
            )
        )
        values = np.interp(points, self.solvent_grid, self.relative_density)
        return float(np.trapezoid(values, points) / (clipped_upper - clipped_lower))

    def single_component_prior(
        self,
        copy_count: int,
        solvent_fraction: float,
    ) -> float:
        """Weight solvent density by the published empirical copy frequency."""

        return self.score(solvent_fraction) * homooligomer_copy_probability(copy_count)

    def single_component_interval_prior(
        self,
        copy_count: int,
        lower: float,
        upper: float,
    ) -> float:
        """Weight a bounded solvent-density score by empirical copy frequency."""

        return self.score_interval(lower, upper) * homooligomer_copy_probability(
            copy_count
        )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def _reference() -> tuple[NDArray[np.float64], NDArray[np.float64], dict[str, Any]]:
    resource = resources.files("genome_to_diffraction.matthews").joinpath(
        REFERENCE_RESOURCE
    )
    compressed = resource.read_bytes()
    if _sha256(compressed) != REFERENCE_RESOURCE_SHA256:
        raise MatthewsProbabilityError("bundled MATTPROB resource checksum differs")
    try:
        document = json.loads(gzip.decompress(compressed))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MatthewsProbabilityError(
            "bundled MATTPROB resource is invalid"
        ) from error
    if not isinstance(document, dict):
        raise MatthewsProbabilityError("bundled MATTPROB document is not an object")
    if document.get("schema_version") != "1.0":
        raise MatthewsProbabilityError("bundled MATTPROB schema version differs")
    if document.get("backend_id") != PRIOR_BACKEND:
        raise MatthewsProbabilityError("bundled MATTPROB backend identity differs")
    if document.get("solvent_density_backend_id") != SOLVENT_DENSITY_BACKEND:
        raise MatthewsProbabilityError(
            "bundled MATTPROB solvent-density identity differs"
        )
    source = document.get("source")
    if not isinstance(source, dict):
        raise MatthewsProbabilityError("bundled MATTPROB source metadata is absent")
    if source.get("archive_sha256") != REFERENCE_ARCHIVE_SHA256:
        raise MatthewsProbabilityError("bundled MATTPROB archive identity differs")
    if source.get("member_sha256") != REFERENCE_MEMBER_SHA256:
        raise MatthewsProbabilityError("bundled MATTPROB member identity differs")
    records = document.get("records")
    if not isinstance(records, list) or len(records) < 50_000:
        raise MatthewsProbabilityError("bundled MATTPROB records are incomplete")
    compact_records = json.dumps(records, separators=(",", ":")).encode("ascii")
    if _sha256(compact_records) != document.get("records_sha256"):
        raise MatthewsProbabilityError("bundled MATTPROB record checksum differs")
    try:
        quantised = np.asarray(records, dtype=np.int64)
    except (TypeError, ValueError) as error:
        raise MatthewsProbabilityError(
            "bundled MATTPROB records are malformed"
        ) from error
    if quantised.ndim != 2 or quantised.shape[1] != 2:
        raise MatthewsProbabilityError("bundled MATTPROB record shape differs")
    if int(document.get("reference_record_count", -1)) != quantised.shape[0]:
        raise MatthewsProbabilityError("bundled MATTPROB record count differs")
    copy_count_rows = document.get("homooligomer_copy_count_occurrences")
    if not isinstance(copy_count_rows, list) or any(
        not isinstance(row, list)
        or len(row) != 2
        or type(row[0]) is not int
        or type(row[1]) is not int
        for row in copy_count_rows
    ):
        raise MatthewsProbabilityError(
            "bundled MATTPROB copy-count occurrences are malformed"
        )
    copy_count_occurrences = {
        copy_count: occurrences for copy_count, occurrences in copy_count_rows
    }
    if (
        len(copy_count_occurrences) != len(copy_count_rows)
        or tuple(copy_count_occurrences) != tuple(sorted(copy_count_occurrences))
        or any(
            copy_count <= 0 or occurrences <= 0
            for copy_count, occurrences in copy_count_occurrences.items()
        )
    ):
        raise MatthewsProbabilityError(
            "bundled MATTPROB copy-count occurrences are invalid"
        )
    copy_reference_count = document.get("homooligomer_copy_count_reference_count")
    if type(copy_reference_count) is not int or copy_reference_count <= 0:
        raise MatthewsProbabilityError(
            "bundled MATTPROB copy-count reference count is invalid"
        )
    if sum(copy_count_occurrences.values()) != copy_reference_count:
        raise MatthewsProbabilityError(
            "bundled MATTPROB copy-count reference count differs"
        )
    if np.any(quantised[:, 0] <= 0):
        raise MatthewsProbabilityError("bundled MATTPROB resolution is invalid")
    if np.any((quantised[:, 1] <= 0) | (quantised[:, 1] >= 1_000_000)):
        raise MatthewsProbabilityError("bundled MATTPROB solvent fraction is invalid")
    if np.any(
        np.lexsort((quantised[:, 1], quantised[:, 0])) != np.arange(len(quantised))
    ):
        raise MatthewsProbabilityError("bundled MATTPROB records are not sorted")
    resolutions = quantised[:, 0].astype(np.float64) / 1000.0
    solvents = quantised[:, 1].astype(np.float64) / 1_000_000.0
    resolutions.setflags(write=False)
    solvents.setflags(write=False)
    return resolutions, solvents, document


def reference_metadata() -> dict[str, Any]:
    """Return path-free provenance for the bundled empirical reference."""

    _, _, document = _reference()
    return {
        "backend_id": PRIOR_BACKEND,
        "solvent_density_backend_id": SOLVENT_DENSITY_BACKEND,
        "resource_sha256": REFERENCE_RESOURCE_SHA256,
        "source": document["source"],
        "filters": document["filters"],
        "reference_record_count": document["reference_record_count"],
        "excluded_record_count": document["excluded_record_count"],
        "kde": {
            "kernel": "gaussian",
            "bandwidth": "KernSmooth_bkde_oversmoothed_Wand_Jones",
            "grid_size": KDE_GRID_SIZE,
            "support_bandwidths": KDE_GAUSSIAN_SUPPORT_BANDWIDTHS,
            "density_scale": "maximum_equals_one",
        },
        "copy_count_prior": {
            "population": "protein_homooligomers_with_positive_ncs_count",
            "reference_count": document["homooligomer_copy_count_reference_count"],
            "occurrences": document["homooligomer_copy_count_occurrences"],
            "unobserved_copy_count_probability": 0.0,
        },
        "combined_score": {
            "formula": "relative_solvent_density_times_empirical_copy_probability",
            "ranking_is_calibrated_identity_probability": False,
        },
    }


def homooligomer_copy_probability(copy_count: int) -> float:
    """Return the published 2013 empirical P(n) for one ASU copy count."""

    if (
        isinstance(copy_count, bool)
        or not isinstance(copy_count, int)
        or copy_count < 1
    ):
        raise MatthewsProbabilityError("copy count must be a positive integer")
    _, _, document = _reference()
    occurrences = dict(document["homooligomer_copy_count_occurrences"])
    reference_count = int(document["homooligomer_copy_count_reference_count"])
    return float(occurrences.get(copy_count, 0) / reference_count)


def _oversmoothed_bandwidth(values: NDArray[np.float64]) -> float:
    count = len(values)
    if count < MINIMUM_REFERENCE_RECORDS:
        raise MatthewsProbabilityError(
            "too few empirical records at the requested resolution"
        )
    variance = float(np.var(values, ddof=1))
    if not math.isfinite(variance) or variance <= 0:
        raise MatthewsProbabilityError("empirical solvent variance is invalid")
    canonical = (1.0 / (4.0 * math.pi)) ** 0.1
    return canonical * (243.0 / (35.0 * count)) ** 0.2 * math.sqrt(variance)


def _linear_bin(values: NDArray[np.float64], grid_size: int) -> NDArray[np.float64]:
    positions = values * (grid_size - 1)
    left = np.floor(positions).astype(np.int64)
    right_weight = positions - left
    left = np.clip(left, 0, grid_size - 1)
    right = np.clip(left + 1, 0, grid_size - 1)
    counts = np.zeros(grid_size, dtype=np.float64)
    np.add.at(counts, left, 1.0 - right_weight)
    np.add.at(counts, right, right_weight)
    return counts


@lru_cache(maxsize=64)
def probability_distribution(
    resolution_high_a: float,
) -> MatthewsProbabilityDistribution:
    """Build one deterministic cumulative-resolution empirical KDE."""

    if not math.isfinite(resolution_high_a) or resolution_high_a <= 0:
        raise MatthewsProbabilityError("high-resolution limit must be positive")
    resolutions, solvents, _ = _reference()
    selected = solvents[resolutions <= resolution_high_a]
    bandwidth = _oversmoothed_bandwidth(selected)
    grid = np.linspace(0.0, 1.0, KDE_GRID_SIZE, dtype=np.float64)
    counts = _linear_bin(selected, KDE_GRID_SIZE)
    spacing = 1.0 / (KDE_GRID_SIZE - 1)
    support = min(
        math.floor(KDE_GAUSSIAN_SUPPORT_BANDWIDTHS * bandwidth / spacing),
        KDE_GRID_SIZE - 1,
    )
    if support < 1:
        raise MatthewsProbabilityError("empirical KDE bandwidth is below grid scale")
    offsets = np.arange(-support, support + 1, dtype=np.float64) * spacing
    kernel = np.exp(-0.5 * np.square(offsets / bandwidth))
    kernel /= float(np.sum(kernel))
    density = np.convolve(counts, kernel, mode="same")
    maximum = float(np.max(density))
    if not math.isfinite(maximum) or maximum <= 0:
        raise MatthewsProbabilityError("empirical KDE density is invalid")
    density /= maximum
    grid.setflags(write=False)
    density.setflags(write=False)
    return MatthewsProbabilityDistribution(
        resolution_high_a=resolution_high_a,
        reference_record_count=len(selected),
        bandwidth_fraction=bandwidth,
        solvent_grid=grid,
        relative_density=density,
    )


__all__ = [
    "PRIOR_BACKEND",
    "SOLVENT_DENSITY_BACKEND",
    "MatthewsProbabilityDistribution",
    "MatthewsProbabilityError",
    "homooligomer_copy_probability",
    "probability_distribution",
    "reference_metadata",
]
