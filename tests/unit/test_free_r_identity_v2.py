"""Focused Phase III Free-R identity and preservation regressions."""

from pathlib import Path

import gemmi
import numpy as np
import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.diffraction.free_r_identity import (
    FreeRIdentityError,
    build_free_r_identity,
    compare_free_r_membership,
)
from genome_to_diffraction.schemas.v2.diffraction import (
    DiffractionSelection,
    DiffractionValueSource,
    FreeRConventionStatus,
    FreeRIdentity,
    diffraction_dataset_id,
)

_HKL = (
    (1, 0, 0),
    (0, 1, 0),
    (0, 0, 1),
    (1, 1, 0),
    (1, 0, 1),
    (0, 1, 1),
)
_FLAGS = (0, 1, 0, 0, 1, 0)


def _write_mtz(
    path: Path,
    *,
    hkl: tuple[tuple[int, int, int], ...] = _HKL,
    free_columns: tuple[tuple[str, int, tuple[float, ...]], ...] = (
        ("FreeR_flag", 1, _FLAGS),
    ),
) -> None:
    if any(len(flags) != len(hkl) for _, _, flags in free_columns):
        raise ValueError("test Free-R arrays must match the HKL row count")
    mtz = gemmi.Mtz(with_base=True)
    mtz.spacegroup = gemmi.find_spacegroup_by_name("P 1")
    mtz.set_cell_for_all(gemmi.UnitCell(40, 50, 60, 90, 90, 90))
    observations = mtz.add_dataset("observations")
    other = mtz.add_dataset("other")
    assert observations.id == 1
    assert other.id == 2
    mtz.add_column("I", "J", observations.id)
    mtz.add_column("SIGI", "Q", observations.id)
    for label, dataset_id, _ in free_columns:
        mtz.add_column(label, "I", dataset_id)
    rows = tuple(
        (
            *indices,
            float(100 + row_index),
            float(10 + row_index),
            *(flags[row_index] for _, _, flags in free_columns),
        )
        for row_index, indices in enumerate(hkl)
    )
    mtz.set_data(np.asarray(rows, dtype=np.float32))
    mtz.update_reso()
    mtz.write_to_file(str(path))


def _selection(path: Path) -> DiffractionSelection:
    mtz_sha256 = sha256_file(path, progress=False)
    crystal_id = "crystal_free_r"
    return DiffractionSelection.from_content(
        crystal_id=crystal_id,
        diffraction_dataset_id=diffraction_dataset_id(
            crystal_id=crystal_id,
            mtz_sha256=mtz_sha256,
        ),
        mtz_sha256=mtz_sha256,
        preflight_id="preflight_" + "a" * 64,
        preflight_record_sha256="b" * 64,
        crystal_manifest_sha256="c" * 64,
        observation_dataset_id=1,
        observation_labels=("I", "SIGI"),
        observation_type="intensity",
        selected_space_group="P 1",
        resolution_low_a=40.0,
        resolution_high_a=2.0,
        observation_source=DiffractionValueSource.MTZ_PREFLIGHT_AUTOMATIC,
        space_group_source=DiffractionValueSource.MTZ_HEADER,
        resolution_low_source=DiffractionValueSource.MTZ_RESOLUTION_RANGE,
        resolution_high_source=DiffractionValueSource.MTZ_RESOLUTION_RANGE,
    )


def _identity(path: Path) -> FreeRIdentity:
    return build_free_r_identity(
        selection=_selection(path),
        mtz_path=path,
        free_r_dataset_id=1,
        free_r_label="FreeR_flag",
    )


def test_identity_is_dataset_qualified_integral_and_convention_unresolved(
    tmp_path: Path,
) -> None:
    mtz_path = tmp_path / "source.mtz"
    _write_mtz(mtz_path)

    identity = _identity(mtz_path)

    assert identity.observation_dataset_id == 1
    assert identity.free_r_dataset_id == 1
    assert identity.free_r_label == "FreeR_flag"
    assert identity.distribution.validation_status.endswith("non_constant")
    assert identity.distribution.reflection_count == 6
    assert tuple(
        (item.flag_value, item.reflection_count)
        for item in identity.distribution.flag_counts
    ) == ((0, 4), (1, 2))
    assert identity.convention_status is FreeRConventionStatus.UNRESOLVED
    assert identity.test_flag_value is None
    assert identity.membership_digest_algorithm.endswith("hkl_flag_v1")


def test_different_valid_flag_labels_have_distinct_identities(tmp_path: Path) -> None:
    mtz_path = tmp_path / "two-valid-flags.mtz"
    _write_mtz(
        mtz_path,
        free_columns=(
            ("FreeA", 1, _FLAGS),
            ("FreeB", 1, (1, 0, 1, 1, 0, 1)),
        ),
    )
    selection = _selection(mtz_path)

    free_a = build_free_r_identity(
        selection=selection,
        mtz_path=mtz_path,
        free_r_dataset_id=1,
        free_r_label="FreeA",
    )
    free_b = build_free_r_identity(
        selection=selection,
        mtz_path=mtz_path,
        free_r_dataset_id=1,
        free_r_label="FreeB",
    )

    assert free_a.free_r_identity_id != free_b.free_r_identity_id
    assert free_a.hkl_to_flag_membership_sha256 != free_b.hkl_to_flag_membership_sha256


def test_duplicate_label_and_conflicting_dataset_fail_closed(tmp_path: Path) -> None:
    duplicated = tmp_path / "duplicated.mtz"
    _write_mtz(
        duplicated,
        free_columns=(
            ("FreeR_flag", 1, _FLAGS),
            ("FreeR_flag", 2, _FLAGS),
        ),
    )
    with pytest.raises(FreeRIdentityError, match="duplicated across MTZ columns"):
        _identity(duplicated)

    conflicting = tmp_path / "conflicting-dataset.mtz"
    _write_mtz(
        conflicting,
        free_columns=(("FreeR_flag", 2, _FLAGS),),
    )
    with pytest.raises(FreeRIdentityError, match="conflicting MTZ dataset"):
        _identity(conflicting)

    selection = _selection(conflicting)
    observed = build_free_r_identity(
        selection=selection,
        mtz_path=conflicting,
        free_r_dataset_id=None,
        free_r_label="FreeR_flag",
    )
    assert observed.observation_dataset_id == 1
    assert observed.free_r_dataset_id == 2


def test_non_integral_flags_fail_closed(tmp_path: Path) -> None:
    mtz_path = tmp_path / "non-integral.mtz"
    _write_mtz(
        mtz_path,
        free_columns=(("FreeR_flag", 1, (0, 1, 0.5, 0, 1, 0)),),
    )

    with pytest.raises(FreeRIdentityError, match="exactly integral"):
        _identity(mtz_path)


def test_non_finite_flags_fail_closed(tmp_path: Path) -> None:
    mtz_path = tmp_path / "non-finite.mtz"
    _write_mtz(
        mtz_path,
        free_columns=(("FreeR_flag", 1, (0, 1, float("nan"), 0, 1, 0)),),
    )

    with pytest.raises(FreeRIdentityError, match="non-finite"):
        _identity(mtz_path)


def test_constant_flags_fail_closed(tmp_path: Path) -> None:
    mtz_path = tmp_path / "constant.mtz"
    _write_mtz(
        mtz_path,
        free_columns=(("FreeR_flag", 1, (0, 0, 0, 0, 0, 0)),),
    )

    with pytest.raises(FreeRIdentityError, match="flags are constant"):
        _identity(mtz_path)


def test_explicit_test_value_is_recorded_but_never_inferred(tmp_path: Path) -> None:
    mtz_path = tmp_path / "declared-convention.mtz"
    _write_mtz(mtz_path)
    selection = _selection(mtz_path)

    identity = build_free_r_identity(
        selection=selection,
        mtz_path=mtz_path,
        free_r_dataset_id=1,
        free_r_label="FreeR_flag",
        test_flag_value=1,
    )

    assert identity.convention_status is FreeRConventionStatus.EXPLICIT_TEST_VALUE
    assert identity.test_flag_value == 1
    with pytest.raises(FreeRIdentityError, match="absent from the distribution"):
        build_free_r_identity(
            selection=selection,
            mtz_path=mtz_path,
            free_r_dataset_id=1,
            free_r_label="FreeR_flag",
            test_flag_value=2,
        )


def test_membership_digest_and_comparison_are_row_permutation_invariant(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.mtz"
    derived_path = tmp_path / "derived-reordered.mtz"
    _write_mtz(source_path)
    order = (5, 2, 0, 4, 1, 3)
    _write_mtz(
        derived_path,
        hkl=tuple(_HKL[index] for index in order),
        free_columns=(("FreeR_flag", 1, tuple(_FLAGS[index] for index in order)),),
    )
    source = _identity(source_path)

    comparison = compare_free_r_membership(
        source=source,
        derived_mtz_path=derived_path,
    )

    assert comparison.preservation_status.startswith("preserved_exact")
    assert (
        comparison.source_hkl_to_flag_membership_sha256
        == comparison.derived_hkl_to_flag_membership_sha256
    )
    assert comparison.source_hkl_set_sha256 == comparison.derived_hkl_set_sha256


def test_missing_hkl_in_derived_mtz_fails_preservation(tmp_path: Path) -> None:
    source_path = tmp_path / "source.mtz"
    derived_path = tmp_path / "derived-missing-hkl.mtz"
    _write_mtz(source_path)
    _write_mtz(
        derived_path,
        hkl=_HKL[:-1],
        free_columns=(("FreeR_flag", 1, _FLAGS[:-1]),),
    )

    with pytest.raises(FreeRIdentityError, match="exact source HKL set"):
        compare_free_r_membership(
            source=_identity(source_path),
            derived_mtz_path=derived_path,
        )


def test_changed_flag_in_derived_mtz_fails_preservation(tmp_path: Path) -> None:
    source_path = tmp_path / "source.mtz"
    derived_path = tmp_path / "derived-changed-flag.mtz"
    _write_mtz(source_path)
    _write_mtz(
        derived_path,
        free_columns=(("FreeR_flag", 1, (1, 1, 0, 0, 1, 0)),),
    )

    with pytest.raises(FreeRIdentityError, match="changed the exact HKL-to-Free-R"):
        compare_free_r_membership(
            source=_identity(source_path),
            derived_mtz_path=derived_path,
        )
