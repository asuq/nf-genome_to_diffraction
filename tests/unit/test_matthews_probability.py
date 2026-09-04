"""Regression tests for resolution-aware dynamic Matthews probabilities."""

from __future__ import annotations

import pytest

from genome_to_diffraction.matthews.enumerate import (
    MatthewsInputError,
    dynamic_copy_counts,
)
from genome_to_diffraction.matthews.probability import (
    PRIOR_BACKEND,
    REFERENCE_RESOURCE_SHA256,
    SOLVENT_DENSITY_BACKEND,
    homooligomer_copy_probability,
    probability_distribution,
    reference_metadata,
)


def test_bundled_empirical_reference_is_checksum_bound_and_resolution_aware() -> None:
    metadata = reference_metadata()

    assert metadata["backend_id"] == PRIOR_BACKEND
    assert metadata["solvent_density_backend_id"] == SOLVENT_DENSITY_BACKEND
    assert metadata["resource_sha256"] == REFERENCE_RESOURCE_SHA256
    assert metadata["reference_record_count"] == 60_194
    assert metadata["copy_count_prior"]["reference_count"] == 50_190

    high_resolution = probability_distribution(1.42)
    assert high_resolution.reference_record_count == 3_941
    assert high_resolution.bandwidth_fraction == pytest.approx(0.01805840961086626)
    assert high_resolution.score(0.50) == pytest.approx(0.5752102459244015)
    assert high_resolution.score(0.85) == pytest.approx(0.0018811580598363242)


def test_single_component_prior_softly_downweights_uncommon_copy_counts() -> None:
    distribution = probability_distribution(1.42)

    assert homooligomer_copy_probability(1) == pytest.approx(21_984 / 50_190)
    assert homooligomer_copy_probability(4) == pytest.approx(5_440 / 50_190)
    assert homooligomer_copy_probability(67) == 0.0
    assert distribution.single_component_prior(1, 0.50) == pytest.approx(
        distribution.score(0.50) * 21_984 / 50_190
    )


def test_copy_count_prior_rejects_nonpositive_or_boolean_counts() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        homooligomer_copy_probability(0)
    with pytest.raises(ValueError, match="positive integer"):
        homooligomer_copy_probability(True)


def test_dynamic_copy_range_has_no_sixteen_copy_ceiling() -> None:
    copies, warnings = dynamic_copy_counts(
        v_asu_a3=859_654.62342144,
        mass_lower_da=7_766.0,
        mass_upper_da=7_766.0,
        minimum_solvent_fraction=0.10,
        maximum_solvent_fraction=0.90,
    )

    assert warnings == ()
    assert copies[0] == 1
    assert copies[-1] == 80
    assert 16 in copies
    assert len(copies) == 80


@pytest.mark.parametrize("asu_volume", [0.0, float("inf"), float("nan")])
def test_dynamic_copy_range_rejects_invalid_asu_volume(asu_volume: float) -> None:
    with pytest.raises(MatthewsInputError, match="ASU volume"):
        dynamic_copy_counts(
            v_asu_a3=asu_volume,
            mass_lower_da=7_766.0,
            mass_upper_da=7_766.0,
            minimum_solvent_fraction=0.10,
            maximum_solvent_fraction=0.90,
        )


def test_empirical_probability_rejects_invalid_resolution() -> None:
    with pytest.raises(ValueError, match="high-resolution limit must be positive"):
        probability_distribution(0.0)
