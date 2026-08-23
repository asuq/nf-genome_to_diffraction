"""Validate and compare schema-v2 Free-R identities with Gemmi.

Scientific purpose
------------------
This module commits the exact raw ``(H, K, L, flag)`` mapping selected from one
checksum-bound MTZ.  It validates finite integral flags and a non-constant
distribution, but never guesses which observed integer is the Free-R test
value.  A caller may supply a separately reviewed test value explicitly.

Inputs and outputs
------------------
``build_free_r_identity`` consumes a schema-v2 diffraction selection, its exact
source MTZ, and an explicit MTZ-internal dataset ID/label.  It returns a
content-addressed :class:`~genome_to_diffraction.schemas.v2.FreeRIdentity`.
``load_free_r_identity`` revalidates that content address, and
``verify_free_r_identity_selection`` requires an exact selection binding.
``compare_free_r_membership`` consumes that identity and a derived/refined MTZ;
it returns a comparison record only when the dataset-qualified label, HKL set,
distribution, and raw HKL-to-flag mapping are unchanged.

Runtime, failure, status, cache, and tests
-----------------------------------------
Gemmi and NumPy are the only runtime requirements; no external command runs and
no flags are generated.  Missing, ambiguous, conflicting-dataset, non-integer,
non-finite, constant, duplicate-HKL, missing-HKL, and changed-flag inputs raise
``FreeRIdentityError``.  Successful identities use the explicit validated
distribution status, and comparisons use
``preserved_exact_hkl_to_raw_flag_mapping``.  The complete canonical records,
including both SHA-256 mapping digests, form their cache identities.  Focused
coverage is in ``tests/unit/test_free_r_identity_v2.py``.

Digest format
-------------
Rows are converted to signed big-endian 64-bit integers, lexicographically
sorted by HKL (and raw flag for the four-column mapping), prefixed by a versioned
domain and unsigned big-endian row count, then SHA-256 hashed.  Duplicate HKLs
are rejected, so each HKL has exactly one raw flag and row permutation cannot
change either digest.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import gemmi
import numpy as np
from numpy.typing import NDArray
from pydantic import ValidationError

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.schemas.v2.diffraction import (
    DiffractionSelection,
    FreeRConventionStatus,
    FreeRDistributionSummary,
    FreeRFlagCount,
    FreeRIdentity,
    FreeRMembershipComparison,
)
from genome_to_diffraction.status import InputContractError

_HKL_DIGEST_DOMAIN = b"nf-gtd/free-r/sorted-hkl/v1\0"
_MEMBERSHIP_DIGEST_DOMAIN = b"nf-gtd/free-r/sorted-hkl-raw-flag/v1\0"


class FreeRIdentityError(InputContractError):
    """A source or derived MTZ cannot satisfy the Phase III Free-R contract."""


@dataclass(frozen=True)
class _FreeRInspection:
    """Validated in-memory facts used to construct immutable public records."""

    mtz_sha256: str
    dataset_id: int
    label: str
    distribution: FreeRDistributionSummary
    hkl_set_sha256: str
    hkl_to_flag_membership_sha256: str


def load_free_r_identity(path: Path) -> FreeRIdentity:
    """Load one content-address-valid schema-v2 Free-R identity document."""

    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise OSError("path is not a regular file")
        return FreeRIdentity.model_validate_json(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise FreeRIdentityError(f"invalid Free-R identity: {path}") from error


def verify_free_r_identity_selection(
    identity: FreeRIdentity,
    selection: DiffractionSelection,
) -> None:
    """Require one Free-R identity to describe the exact diffraction selection."""

    expected = (
        selection.diffraction_selection_id,
        selection.diffraction_dataset_id,
        selection.crystal_id,
        selection.mtz_sha256,
        selection.observation_dataset_id,
    )
    observed = (
        identity.diffraction_selection_id,
        identity.diffraction_dataset_id,
        identity.crystal_id,
        identity.mtz_sha256,
        identity.observation_dataset_id,
    )
    if observed != expected:
        raise FreeRIdentityError(
            "Free-R identity differs from the diffraction selection"
        )


def _exact_integral_values(
    values: NDArray[np.generic],
    *,
    description: str,
) -> NDArray[np.int64]:
    numeric = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(numeric)):
        raise FreeRIdentityError(f"{description} contain non-finite values")
    rounded = np.rint(numeric)
    if not np.array_equal(numeric, rounded):
        raise FreeRIdentityError(f"{description} must be exactly integral")
    bounds = np.iinfo(np.int64)
    if np.any(rounded < bounds.min) or np.any(rounded > bounds.max):
        raise FreeRIdentityError(f"{description} exceed signed 64-bit range")
    return rounded.astype(np.int64)


def _digest_integer_rows(
    rows: NDArray[np.int64],
    *,
    domain: bytes,
) -> str:
    digest = hashlib.sha256()
    digest.update(domain)
    digest.update(len(rows).to_bytes(8, byteorder="big", signed=False))
    digest.update(np.asarray(rows, dtype=">i8").tobytes(order="C"))
    return digest.hexdigest()


def _read_mtz(path: Path) -> tuple[Path, str, gemmi.Mtz]:
    try:
        resolved = path.resolve(strict=True)
        mtz_sha256 = sha256_file(resolved, progress=False)
        mtz = gemmi.read_mtz_file(str(resolved))
    except (OSError, RuntimeError) as error:
        raise FreeRIdentityError(f"cannot read Free-R MTZ {path}: {error}") from error
    if mtz.nreflections < 1:
        raise FreeRIdentityError("Free-R MTZ contains no reflections")
    return resolved, mtz_sha256, mtz


def _inspect_free_r_array(
    *,
    mtz_sha256: str,
    mtz: gemmi.Mtz,
    free_r_dataset_id: int,
    free_r_label: str,
) -> _FreeRInspection:
    matching_labels = tuple(
        column for column in mtz.columns if column.label == free_r_label
    )
    if not matching_labels:
        raise FreeRIdentityError(f"Free-R label is missing from MTZ: {free_r_label!r}")
    if len(matching_labels) != 1:
        dataset_ids = tuple(sorted(column.dataset_id for column in matching_labels))
        raise FreeRIdentityError(
            "Free-R label is duplicated across MTZ columns: "
            f"label={free_r_label!r}; dataset_ids={dataset_ids}"
        )
    column = matching_labels[0]
    if column.dataset_id != free_r_dataset_id:
        raise FreeRIdentityError(
            "Free-R label belongs to a conflicting MTZ dataset: "
            f"label={free_r_label!r}; expected={free_r_dataset_id}; "
            f"observed={column.dataset_id}"
        )
    if column.type != "I":
        raise FreeRIdentityError(
            "Free-R column must have integral MTZ type I: "
            f"label={free_r_label!r}; observed_type={column.type!r}"
        )

    flags = _exact_integral_values(
        np.asarray(column.array),
        description="Free-R flags",
    )
    hkl_raw = np.asarray(mtz.make_miller_array())
    if hkl_raw.ndim != 2 or hkl_raw.shape[1] != 3:
        raise FreeRIdentityError("MTZ Miller indices do not have H,K,L shape")
    if len(flags) != len(hkl_raw) or len(flags) != mtz.nreflections:
        raise FreeRIdentityError(
            "Free-R flags and Miller indices do not cover the same reflections"
        )
    hkl = _exact_integral_values(hkl_raw, description="MTZ Miller indices")
    mapping = np.column_stack((hkl, flags)).astype(np.int64, copy=False)
    order = np.lexsort((mapping[:, 3], mapping[:, 2], mapping[:, 1], mapping[:, 0]))
    sorted_mapping = mapping[order]
    if len(sorted_mapping) > 1:
        duplicate_hkl = np.all(
            sorted_mapping[1:, :3] == sorted_mapping[:-1, :3],
            axis=1,
        )
        if np.any(duplicate_hkl):
            raise FreeRIdentityError(
                "MTZ contains duplicate HKL rows; Free-R membership is ambiguous"
            )

    flag_values, flag_counts = np.unique(flags, return_counts=True)
    if len(flag_values) < 2:
        raise FreeRIdentityError(
            "Free-R flags are constant; no nontrivial reflection partition exists"
        )
    distribution = FreeRDistributionSummary(
        reflection_count=len(flags),
        distinct_flag_values=len(flag_values),
        flag_counts=tuple(
            FreeRFlagCount(
                flag_value=int(value),
                reflection_count=int(count),
            )
            for value, count in zip(flag_values, flag_counts, strict=True)
        ),
    )
    sorted_hkl = sorted_mapping[:, :3]
    return _FreeRInspection(
        mtz_sha256=mtz_sha256,
        dataset_id=column.dataset_id,
        label=column.label,
        distribution=distribution,
        hkl_set_sha256=_digest_integer_rows(
            sorted_hkl,
            domain=_HKL_DIGEST_DOMAIN,
        ),
        hkl_to_flag_membership_sha256=_digest_integer_rows(
            sorted_mapping,
            domain=_MEMBERSHIP_DIGEST_DOMAIN,
        ),
    )


def build_free_r_identity(
    *,
    selection: DiffractionSelection,
    mtz_path: Path,
    free_r_dataset_id: int,
    free_r_label: str,
    test_flag_value: int | None = None,
) -> FreeRIdentity:
    """Validate and bind one raw Free-R mapping to a diffraction selection.

    ``test_flag_value`` is never inferred.  Leave it as ``None`` unless the
    convention has been established from authoritative run metadata or review.
    """

    if free_r_dataset_id != selection.observation_dataset_id:
        raise FreeRIdentityError(
            "Free-R dataset conflicts with the selected observation dataset: "
            f"free_r={free_r_dataset_id}; "
            f"observations={selection.observation_dataset_id}"
        )
    if not free_r_label or free_r_label != free_r_label.strip():
        raise FreeRIdentityError("Free-R label must be non-empty exact text")
    if test_flag_value is not None and type(test_flag_value) is not int:
        raise FreeRIdentityError("Free-R test flag value must be an exact integer")
    _, mtz_sha256, mtz = _read_mtz(mtz_path)
    if mtz_sha256 != selection.mtz_sha256:
        raise FreeRIdentityError(
            "source MTZ digest differs from the diffraction selection"
        )
    inspected = _inspect_free_r_array(
        mtz_sha256=mtz_sha256,
        mtz=mtz,
        free_r_dataset_id=free_r_dataset_id,
        free_r_label=free_r_label,
    )
    observed_flag_values = {
        item.flag_value for item in inspected.distribution.flag_counts
    }
    if test_flag_value is not None and test_flag_value not in observed_flag_values:
        raise FreeRIdentityError(
            "supplied Free-R test flag value is absent from the distribution"
        )
    convention_status = (
        FreeRConventionStatus.UNRESOLVED
        if test_flag_value is None
        else FreeRConventionStatus.EXPLICIT_TEST_VALUE
    )
    return FreeRIdentity.from_content(
        diffraction_selection_id=selection.diffraction_selection_id,
        diffraction_dataset_id=selection.diffraction_dataset_id,
        crystal_id=selection.crystal_id,
        mtz_sha256=selection.mtz_sha256,
        observation_dataset_id=selection.observation_dataset_id,
        free_r_dataset_id=inspected.dataset_id,
        free_r_label=inspected.label,
        distribution=inspected.distribution,
        hkl_set_sha256=inspected.hkl_set_sha256,
        hkl_to_flag_membership_sha256=(inspected.hkl_to_flag_membership_sha256),
        convention_status=convention_status,
        test_flag_value=test_flag_value,
    )


def compare_free_r_membership(
    *,
    source: FreeRIdentity,
    derived_mtz_path: Path,
) -> FreeRMembershipComparison:
    """Prove exact raw Free-R membership preservation in a derived MTZ.

    The source dataset ID and label are the only accepted derived column
    identity.  A comparison record is not emitted when any invariant differs.
    """

    _, derived_mtz_sha256, derived_mtz = _read_mtz(derived_mtz_path)
    derived = _inspect_free_r_array(
        mtz_sha256=derived_mtz_sha256,
        mtz=derived_mtz,
        free_r_dataset_id=source.free_r_dataset_id,
        free_r_label=source.free_r_label,
    )
    if derived.hkl_set_sha256 != source.hkl_set_sha256:
        raise FreeRIdentityError(
            "derived MTZ does not preserve the exact source HKL set: "
            f"source_reflections={source.distribution.reflection_count}; "
            f"derived_reflections={derived.distribution.reflection_count}"
        )
    if derived.hkl_to_flag_membership_sha256 != source.hkl_to_flag_membership_sha256:
        raise FreeRIdentityError(
            "derived MTZ changed the exact HKL-to-Free-R-flag membership"
        )
    if derived.distribution != source.distribution:
        raise FreeRIdentityError("derived MTZ changed the Free-R distribution")

    return FreeRMembershipComparison.from_content(
        source_free_r_identity_id=source.free_r_identity_id,
        diffraction_selection_id=source.diffraction_selection_id,
        diffraction_dataset_id=source.diffraction_dataset_id,
        crystal_id=source.crystal_id,
        source_mtz_sha256=source.mtz_sha256,
        derived_mtz_sha256=derived.mtz_sha256,
        source_free_r_dataset_id=source.free_r_dataset_id,
        derived_free_r_dataset_id=derived.dataset_id,
        source_free_r_label=source.free_r_label,
        derived_free_r_label=derived.label,
        source_distribution=source.distribution,
        derived_distribution=derived.distribution,
        source_hkl_set_sha256=source.hkl_set_sha256,
        derived_hkl_set_sha256=derived.hkl_set_sha256,
        source_hkl_to_flag_membership_sha256=(source.hkl_to_flag_membership_sha256),
        derived_hkl_to_flag_membership_sha256=(derived.hkl_to_flag_membership_sha256),
        convention_status=source.convention_status,
        test_flag_value=source.test_flag_value,
    )


__all__ = [
    "FreeRIdentityError",
    "build_free_r_identity",
    "compare_free_r_membership",
    "load_free_r_identity",
    "verify_free_r_identity_selection",
]
