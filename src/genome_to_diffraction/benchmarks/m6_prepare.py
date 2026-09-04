"""Prepare sanitised, truth-isolated M6 discovery inputs from frozen sources.

This trusted local step verifies every public coordinate, structure-factor,
RCSB cluster-snapshot, and RefSeq catalogue file against the approved protocol.
It converts and sanitises MTZ files, replaces catalogue accessions with opaque
locus IDs, applies the predeclared catalogue/MTZ edge transformations, and
writes the 63-case preparation manifest consumed by :mod:`m6_runner`.

The private truth map remains outside the runner archive.  No network service
or scientific executable is invoked; Gemmi performs the deterministic
structure-factor conversion.  A changed source, missing target, unsafe path,
unsupported reflection block, or failed truth-isolation invariant aborts the
entire preparation.
"""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

import gemmi
import numpy as np
from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
from pydantic import Field, model_validator

from genome_to_diffraction.benchmarks.m6_edge import M6_RATE_LIMIT_HTTP_FIXTURE
from genome_to_diffraction.benchmarks.m6_protocol import (
    M6AssumptionControlSpec,
    M6BenchmarkProtocol,
    M6CaseSpec,
    M6PositiveTargetSpec,
    load_m6_protocol,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.diffraction.preflight import select_observations
from genome_to_diffraction.ids import canonical_sequence, content_id, sequence_digest
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    PositiveInt,
    Sha256Hex,
)

M6MtzVariation = Literal[
    "ordinary",
    "map_only",
    "equivalent_observation_arrays",
    "conflicting_observation_arrays",
]
M6ObservationType = Literal["intensity", "amplitude"]

_M6_HKL_DIGEST_DOMAIN = b"nf-gtd/m6/sanitised-hkl/v1\0"
_M6_FREE_R_DIGEST_DOMAIN = b"nf-gtd/m6/sanitised-hkl-free-r/v1\0"
_FREE_R_LABELS = frozenset(
    {
        "FREE",
        "FREER",
        "FREERFLAG",
        "FREERFLAGS",
        "RFREE",
        "RFREEFLAG",
        "RFREEFLAGS",
    }
)
_M6_MTZ_VARIATION_BY_CASE_KIND: dict[str, M6MtzVariation] = {
    "map_only_mtz": "map_only",
    "ambiguous_columns_equivalent": "equivalent_observation_arrays",
    "ambiguous_columns_conflicting": "conflicting_observation_arrays",
}


class M6MtzSanitisationRecord(ContractModel):
    """Path-free proof that one ordinary runner MTZ contains only safe arrays."""

    schema_version: Literal["1.0"]
    sanitisation_id: str = Field(pattern=r"^m6mtz_[a-f0-9]{64}$")
    contract: Literal["ordinary_observations_free_r_only_v1"]
    output_mtz_sha256: Sha256Hex
    output_mtz_size_bytes: PositiveInt
    reflection_count: PositiveInt
    output_column_labels: tuple[NonEmptyString, ...] = Field(min_length=6)
    observation_dataset_id: PositiveInt
    observation_labels: tuple[NonEmptyString, ...] = Field(min_length=2, max_length=4)
    observation_type: M6ObservationType
    free_r_dataset_id: PositiveInt
    free_r_label: NonEmptyString
    hkl_set_sha256: Sha256Hex
    hkl_to_free_r_membership_sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_content_address(self) -> Self:
        identity = self.model_dump(mode="json", exclude={"sanitisation_id"})
        expected = content_id("m6mtz_", identity)
        if self.sanitisation_id != expected:
            raise ValueError("M6 MTZ sanitisation ID differs from its content")
        expected_columns = ("H", "K", "L", *self.observation_labels, self.free_r_label)
        if self.output_column_labels != expected_columns:
            raise ValueError(
                "ordinary M6 output columns must be HKL, observations, and Free-R"
            )
        if self.free_r_dataset_id != self.observation_dataset_id:
            raise ValueError("ordinary M6 observations and Free-R must share a dataset")
        return self


@dataclass(frozen=True)
class M6InputPreparationRequest:
    """Paths for one bounded offline M6 input preparation."""

    protocol: Path
    rcsb_directory: Path
    catalogue_directories: tuple[Path, ...]
    output_directory: Path


@dataclass(frozen=True)
class M6InputPreparationResult:
    """Stable local artefacts at the trusted runner boundary."""

    protocol_id: str
    case_count: int
    preparation_manifest: Path
    private_truth_map: Path
    source_inventory: Path


@dataclass(frozen=True)
class _OpaqueRecord:
    opaque_id: str
    original_id: str
    sequence: str
    sequence_sha256: str


@dataclass(frozen=True)
class _VerifiedClusterSnapshot:
    """Checksum-bound RCSB snapshot evidence retained outside the runner."""

    identity_threshold_percent: int
    file_name: str
    source_url: str
    sha256: str
    size_bytes: int
    target_line_count: int

    def as_record(self) -> dict[str, object]:
        """Serialise stable, path-free snapshot provenance."""

        return {
            "identity_threshold_percent": self.identity_threshold_percent,
            "file_name": self.file_name,
            "source_url": self.source_url,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "target_line_count": self.target_line_count,
        }


@dataclass(frozen=True)
class _VerifiedFamily:
    """One target's independently verified RCSB family membership."""

    target_key: str
    source_pdb_entity_id: str
    cluster_30_line: str
    cluster_70_line: str
    cluster_30_line_sha256: str
    cluster_70_line_sha256: str
    cluster_30_entities: tuple[str, ...]
    cluster_70_entities: tuple[str, ...]
    operational_family_entities: tuple[str, ...]
    leakage_safe_family_entities: tuple[str, ...]
    frozen_allowed_30_to_70_model_count: int
    observed_allowed_30_to_70_model_count: int

    def as_record(self) -> dict[str, object]:
        """Serialise family truth for the private schema-1.1 boundary."""

        return {
            "target_key": self.target_key,
            "source_pdb_entity_id": self.source_pdb_entity_id,
            "cluster_30_line": self.cluster_30_line,
            "cluster_70_line": self.cluster_70_line,
            "cluster_30_line_sha256": self.cluster_30_line_sha256,
            "cluster_70_line_sha256": self.cluster_70_line_sha256,
            "cluster_30_entities": list(self.cluster_30_entities),
            "cluster_70_entities": list(self.cluster_70_entities),
            "operational_family_entities": list(self.operational_family_entities),
            "leakage_safe_family_entities": list(self.leakage_safe_family_entities),
            "frozen_allowed_30_to_70_model_count": (
                self.frozen_allowed_30_to_70_model_count
            ),
            "observed_allowed_30_to_70_model_count": (
                self.observed_allowed_30_to_70_model_count
            ),
        }


def _verify_file(path: Path, *, sha256: str, size_bytes: int, label: str) -> Path:
    if path.is_symlink():
        raise PublicControlError(f"{label} is a symlink: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise PublicControlError(f"{label} is missing: {path}") from error
    if not resolved.is_file():
        raise PublicControlError(f"{label} is not a file: {resolved}")
    if resolved.stat().st_size != size_bytes:
        raise PublicControlError(f"{label} size differs from the protocol: {resolved}")
    if sha256_file(resolved) != sha256:
        raise PublicControlError(
            f"{label} checksum differs from the protocol: {resolved}"
        )
    return resolved


def _target_cluster_lines(
    path: Path,
    *,
    target_entities: frozenset[str],
    label: str,
) -> dict[str, tuple[tuple[str, ...], str, str]]:
    """Read target cluster lines while hashing their exact LF-terminated bytes."""

    found: dict[str, tuple[tuple[str, ...], str, str]] = {}
    try:
        with path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if not raw_line.endswith(b"\n") or raw_line.endswith(b"\r\n"):
                    raise PublicControlError(
                        f"{label} line {line_number} is not LF terminated"
                    )
                try:
                    entities = tuple(raw_line[:-1].decode("ascii").split())
                except UnicodeDecodeError as error:
                    raise PublicControlError(
                        f"{label} line {line_number} is not ASCII"
                    ) from error
                if not entities:
                    raise PublicControlError(f"{label} line {line_number} is empty")
                if len(entities) != len(set(entities)):
                    raise PublicControlError(
                        f"{label} line {line_number} repeats an entity"
                    )
                matched = target_entities.intersection(entities)
                if not matched:
                    continue
                line_sha256 = hashlib.sha256(raw_line).hexdigest()
                sorted_entities = tuple(sorted(entities))
                for entity in matched:
                    if entity in found:
                        raise PublicControlError(
                            f"{label} repeats target entity {entity}"
                        )
                    found[entity] = (
                        sorted_entities,
                        raw_line[:-1].decode("ascii"),
                        line_sha256,
                    )
    except OSError as error:
        raise PublicControlError(f"cannot read {label} {path}: {error}") from error
    missing = sorted(target_entities - found.keys())
    if missing:
        raise PublicControlError(f"{label} lacks target entities: {', '.join(missing)}")
    return found


def _verify_m6_family_snapshots(
    protocol: M6BenchmarkProtocol,
    rcsb_root: Path,
) -> tuple[tuple[_VerifiedClusterSnapshot, ...], tuple[_VerifiedFamily, ...]]:
    """Verify frozen RCSB snapshots and derive private target-family truth."""

    snapshot_specs = (
        (
            30,
            "clusters-by-entity-30.txt",
            protocol.leakage_policy.rcsb_30_snapshot,
        ),
        (
            70,
            "clusters-by-entity-70.txt",
            protocol.leakage_policy.rcsb_70_snapshot,
        ),
    )
    target_entities = frozenset(
        target.source_pdb_entity_id for target in protocol.positives
    )
    if len(target_entities) != len(protocol.positives):
        raise PublicControlError("M6 positives must use distinct PDB entities")

    snapshots: list[_VerifiedClusterSnapshot] = []
    lines_by_threshold: dict[int, dict[str, tuple[tuple[str, ...], str, str]]] = {}
    for threshold, file_name, spec in snapshot_specs:
        verified = _verify_file(
            rcsb_root / file_name,
            sha256=spec.sha256,
            size_bytes=spec.size_bytes,
            label=f"M6 RCSB {threshold}% cluster snapshot",
        )
        target_lines = _target_cluster_lines(
            verified,
            target_entities=target_entities,
            label=f"M6 RCSB {threshold}% cluster snapshot",
        )
        lines_by_threshold[threshold] = target_lines
        snapshots.append(
            _VerifiedClusterSnapshot(
                identity_threshold_percent=threshold,
                file_name=file_name,
                source_url=spec.url,
                sha256=spec.sha256,
                size_bytes=spec.size_bytes,
                target_line_count=len(target_lines),
            )
        )

    families: list[_VerifiedFamily] = []
    for target in sorted(protocol.positives, key=lambda item: item.target_key):
        source_entity = target.source_pdb_entity_id
        cluster_30, line_30, line_30_sha256 = lines_by_threshold[30][source_entity]
        cluster_70, line_70, line_70_sha256 = lines_by_threshold[70][source_entity]
        if line_30_sha256 != target.rcsb_30_cluster_line_sha256:
            raise PublicControlError(
                f"M6 target {target.target_key} 30% cluster-line checksum changed"
            )
        if line_70_sha256 != target.rcsb_70_cluster_line_sha256:
            raise PublicControlError(
                f"M6 target {target.target_key} 70% cluster-line checksum changed"
            )
        cluster_30_set = set(cluster_30)
        cluster_70_set = set(cluster_70)
        if source_entity not in cluster_30_set or source_entity not in cluster_70_set:
            raise PublicControlError(
                f"M6 target {target.target_key} is absent from its own cluster"
            )
        operational_family = tuple(sorted(cluster_30_set - {source_entity}))
        leakage_safe_family = tuple(sorted(cluster_30_set - cluster_70_set))
        observed_count = len(leakage_safe_family)
        if observed_count != target.allowed_30_to_70_model_count:
            raise PublicControlError(
                f"M6 target {target.target_key} frozen 30%-minus-70% count "
                f"is {target.allowed_30_to_70_model_count}, observed {observed_count}"
            )
        families.append(
            _VerifiedFamily(
                target_key=target.target_key,
                source_pdb_entity_id=source_entity,
                cluster_30_line=line_30,
                cluster_70_line=line_70,
                cluster_30_line_sha256=line_30_sha256,
                cluster_70_line_sha256=line_70_sha256,
                cluster_30_entities=cluster_30,
                cluster_70_entities=cluster_70,
                operational_family_entities=operational_family,
                leakage_safe_family_entities=leakage_safe_family,
                frozen_allowed_30_to_70_model_count=(
                    target.allowed_30_to_70_model_count
                ),
                observed_allowed_30_to_70_model_count=observed_count,
            )
        )
    return tuple(snapshots), tuple(families)


def _catalogue_path(roots: tuple[Path, ...], assembly_accession: str) -> Path:
    candidates = tuple(
        candidate
        for root in roots
        for candidate in (
            root / assembly_accession / "protein.faa",
            root / "ncbi_dataset" / "data" / assembly_accession / "protein.faa",
        )
    )
    matches = tuple(path for path in candidates if path.is_file())
    if len(matches) != 1:
        raise PublicControlError(
            f"expected one protein.faa for {assembly_accession}; found {len(matches)}"
        )
    return matches[0]


def _read_catalogue(path: Path) -> tuple[SeqRecord, ...]:
    try:
        records = tuple(SeqIO.parse(path, "fasta"))
    except (OSError, ValueError) as error:
        raise PublicControlError(
            f"cannot parse RefSeq catalogue {path}: {error}"
        ) from error
    if not records:
        raise PublicControlError(f"RefSeq catalogue is empty: {path}")
    if any(not record.id for record in records):
        raise PublicControlError(f"RefSeq catalogue has an empty ID: {path}")
    identifiers = [record.id for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise PublicControlError(f"RefSeq catalogue has duplicate IDs: {path}")
    return records


def anonymise_m6_catalogue(
    records: tuple[SeqRecord, ...],
    *,
    remove_sequence_sha256: str | None = None,
    duplicate_sequence_sha256: str | None = None,
    duplicate_case_id: str | None = None,
) -> tuple[tuple[_OpaqueRecord, ...], dict[str, tuple[str, ...]]]:
    """Replace source IDs and optionally remove or duplicate one exact sequence."""

    if (duplicate_sequence_sha256 is None) != (duplicate_case_id is None):
        raise ValueError("duplicate sequence and case ID must be supplied together")
    opaque: list[_OpaqueRecord] = []
    source_by_digest: dict[str, list[str]] = {}
    duplicate_sequence: str | None = None
    for record in records:
        source_id = record.id
        if not source_id:
            raise PublicControlError("M6 catalogue record has an empty source ID")
        sequence = canonical_sequence(str(record.seq))
        digest = sequence_digest(sequence)
        source_by_digest.setdefault(digest, []).append(source_id)
        if digest == duplicate_sequence_sha256:
            duplicate_sequence = sequence
            continue
        if digest == remove_sequence_sha256:
            continue
        locus_digest = hashlib.sha256(
            f"{source_id}\0{record.description}".encode()
        ).hexdigest()
        opaque.append(
            _OpaqueRecord(
                opaque_id=f"loc_{locus_digest}",
                original_id=source_id,
                sequence=sequence,
                sequence_sha256=digest,
            )
        )

    if remove_sequence_sha256 is not None and remove_sequence_sha256 not in (
        source_by_digest
    ):
        raise PublicControlError("target-absent transform could not find its target")
    if duplicate_sequence_sha256 is not None:
        if duplicate_sequence is None or duplicate_case_id is None:
            raise PublicControlError("duplicate-locus transform could not find target")
        for index in (1, 2):
            locus_digest = hashlib.sha256(
                f"{duplicate_case_id}\0{index}\0{duplicate_sequence_sha256}".encode(
                    "ascii"
                )
            ).hexdigest()
            opaque.append(
                _OpaqueRecord(
                    opaque_id=f"loc_{locus_digest}",
                    original_id=f"<generated-duplicate-{index}>",
                    sequence=duplicate_sequence,
                    sequence_sha256=duplicate_sequence_sha256,
                )
            )
    opaque.sort(key=lambda item: item.opaque_id)
    if len({item.opaque_id for item in opaque}) != len(opaque):
        raise PublicControlError("opaque catalogue locus collision")
    return tuple(opaque), {
        digest: tuple(sorted(source_ids))
        for digest, source_ids in sorted(source_by_digest.items())
    }


def _write_opaque_catalogue(path: Path, records: tuple[_OpaqueRecord, ...]) -> None:
    if not records:
        raise PublicControlError("M6 catalogue transformation produced no proteins")
    atomic_write_text(
        path,
        "".join(f">{record.opaque_id}\n{record.sequence}\n" for record in records),
        encoding="ascii",
    )


def _sanitise_mtz(mtz: gemmi.Mtz, opaque_id: str) -> None:
    mtz.title = f"sanitised M6 reflections {opaque_id}"
    mtz.history = ["nf-genome_to_diffraction M6 sanitised conversion"]
    for dataset in mtz.datasets:
        dataset.project_name = "M6"
        dataset.crystal_name = "opaque"
        dataset.dataset_name = "opaque"
    mtz.ensure_asu()
    mtz.sort()
    mtz.update_reso()


def _normalise_mtz_label(label: str) -> str:
    return "".join(character for character in label.upper() if character.isalnum())


def _exact_integer_array(values: np.ndarray, *, label: str) -> np.ndarray:
    numeric = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(numeric)):
        raise PublicControlError(f"M6 {label} contains non-finite values")
    rounded = np.rint(numeric)
    if not np.array_equal(numeric, rounded):
        raise PublicControlError(f"M6 {label} must be exactly integral")
    return rounded.astype(np.int64)


def _digest_integer_rows(rows: np.ndarray, *, domain: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(domain)
    digest.update(len(rows).to_bytes(8, byteorder="big", signed=False))
    digest.update(np.asarray(rows, dtype=">i8").tobytes(order="C"))
    return digest.hexdigest()


def _free_r_column(
    mtz: gemmi.Mtz,
    *,
    observation_dataset_id: int,
) -> gemmi.Mtz.Column:
    recognised = [
        column
        for column in mtz.columns
        if column.type == "I" and _normalise_mtz_label(column.label) in _FREE_R_LABELS
    ]
    inferred = mtz.rfree_column()
    if inferred is not None and not any(
        column.label == inferred.label and column.dataset_id == inferred.dataset_id
        for column in recognised
    ):
        recognised.append(inferred)
    if len(recognised) != 1:
        raise PublicControlError(
            "ordinary M6 MTZ must contain exactly one recognised Free-R array"
        )
    selected = recognised[0]
    if selected.type != "I":
        raise PublicControlError("ordinary M6 Free-R array must use MTZ type I")
    if selected.dataset_id != observation_dataset_id:
        raise PublicControlError(
            "ordinary M6 Free-R and observations belong to different MTZ datasets"
        )
    return selected


def _hkl_free_r_digests(
    mtz: gemmi.Mtz,
    *,
    free_r_dataset_id: int,
    free_r_label: str,
) -> tuple[str, str]:
    matching = tuple(
        column
        for column in mtz.columns
        if column.dataset_id == free_r_dataset_id and column.label == free_r_label
    )
    if len(matching) != 1:
        raise PublicControlError(
            "ordinary M6 Free-R array is missing or ambiguous after selection"
        )
    flags = _exact_integer_array(
        np.asarray(matching[0].array),
        label="Free-R array",
    )
    if len(np.unique(flags)) < 2:
        raise PublicControlError("ordinary M6 Free-R array is constant")
    hkl = _exact_integer_array(
        np.asarray(mtz.make_miller_array()),
        label="Miller indices",
    )
    if hkl.ndim != 2 or hkl.shape[1] != 3:
        raise PublicControlError("ordinary M6 Miller indices do not have H,K,L shape")
    if len(hkl) != len(flags) or len(flags) != mtz.nreflections:
        raise PublicControlError(
            "ordinary M6 HKL and Free-R arrays cover different reflections"
        )
    mapping = np.column_stack((hkl, flags)).astype(np.int64, copy=False)
    order = np.lexsort((mapping[:, 3], mapping[:, 2], mapping[:, 1], mapping[:, 0]))
    sorted_mapping = mapping[order]
    if len(sorted_mapping) > 1 and np.any(
        np.all(sorted_mapping[1:, :3] == sorted_mapping[:-1, :3], axis=1)
    ):
        raise PublicControlError(
            "ordinary M6 MTZ contains duplicate HKL rows with ambiguous "
            "Free-R membership"
        )
    return (
        _digest_integer_rows(
            sorted_mapping[:, :3],
            domain=_M6_HKL_DIGEST_DOMAIN,
        ),
        _digest_integer_rows(
            sorted_mapping,
            domain=_M6_FREE_R_DIGEST_DOMAIN,
        ),
    )


def _column_in_dataset(
    mtz: gemmi.Mtz,
    *,
    dataset_id: int,
    label: str,
) -> gemmi.Mtz.Column:
    matching = tuple(
        column
        for column in mtz.columns
        if column.dataset_id == dataset_id and column.label == label
    )
    if len(matching) != 1:
        raise PublicControlError(
            "ordinary M6 selected column is missing or ambiguous: "
            f"dataset_id={dataset_id}; label={label!r}"
        )
    return matching[0]


def _ordinary_mtz(
    source: gemmi.Mtz,
    *,
    opaque_id: str,
) -> tuple[gemmi.Mtz, tuple[str, ...], M6ObservationType, int, str, str]:
    observation, _, warnings = select_observations(source, None)
    if observation is None:
        reason = ",".join(warnings) or "missing_observation_arrays"
        raise PublicControlError(
            f"ordinary M6 MTZ lacks one unambiguous observation selection: {reason}"
        )
    free_r = _free_r_column(
        source,
        observation_dataset_id=observation.dataset_id,
    )
    source_hkl_sha256, source_membership_sha256 = _hkl_free_r_digests(
        source,
        free_r_dataset_id=free_r.dataset_id,
        free_r_label=free_r.label,
    )
    retained = tuple(
        (
            column.label,
            column.type,
            np.asarray(column.array),
        )
        for column in (
            *(
                _column_in_dataset(
                    source,
                    dataset_id=observation.dataset_id,
                    label=label,
                )
                for label in observation.labels
            ),
            free_r,
        )
    )
    result = _subset_mtz(source, retained, opaque_id)
    expected_labels = ("H", "K", "L", *observation.labels, free_r.label)
    observed_labels = tuple(column.label for column in result.columns)
    if observed_labels != expected_labels:
        raise PublicControlError(
            "ordinary M6 MTZ retained a column outside HKL, observations, and Free-R"
        )
    result_hkl_sha256, result_membership_sha256 = _hkl_free_r_digests(
        result,
        free_r_dataset_id=result.datasets[-1].id,
        free_r_label=free_r.label,
    )
    if result_hkl_sha256 != source_hkl_sha256:
        raise PublicControlError("ordinary M6 sanitisation changed the exact HKL set")
    if result_membership_sha256 != source_membership_sha256:
        raise PublicControlError(
            "ordinary M6 sanitisation changed exact HKL-to-Free-R membership"
        )
    for label in observation.labels:
        source_values = np.asarray(
            _column_in_dataset(
                source,
                dataset_id=observation.dataset_id,
                label=label,
            ).array
        )
        result_values = np.asarray(
            _column_in_dataset(
                result,
                dataset_id=result.datasets[-1].id,
                label=label,
            ).array
        )
        if not np.array_equal(source_values, result_values, equal_nan=True):
            raise PublicControlError(
                f"ordinary M6 sanitisation changed selected observation {label!r}"
            )
    return (
        result,
        observation.labels,
        observation.observation_type,
        result.datasets[-1].id,
        result_hkl_sha256,
        result_membership_sha256,
    )


def verify_m6_ordinary_mtz_sanitisation(
    path: Path,
    record: M6MtzSanitisationRecord,
) -> Path:
    """Revalidate one ordinary MTZ against its path-free sanitisation record."""

    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise OSError("path is not a regular file")
        mtz = gemmi.read_mtz_file(str(resolved))
    except (OSError, RuntimeError) as error:
        raise PublicControlError(
            f"cannot read ordinary M6 sanitised MTZ {path}: {error}"
        ) from error
    if (
        sha256_file(resolved) != record.output_mtz_sha256
        or resolved.stat().st_size != record.output_mtz_size_bytes
    ):
        raise PublicControlError(
            "ordinary M6 sanitisation record differs from the prepared MTZ object"
        )
    if mtz.nreflections != record.reflection_count:
        raise PublicControlError("ordinary M6 sanitisation reflection count changed")
    if tuple(column.label for column in mtz.columns) != record.output_column_labels:
        raise PublicControlError(
            "ordinary M6 prepared MTZ contains a column outside its whitelist"
        )
    observation, _, _ = select_observations(mtz, None)
    if observation is None or (
        observation.dataset_id,
        observation.labels,
        observation.observation_type,
    ) != (
        record.observation_dataset_id,
        record.observation_labels,
        record.observation_type,
    ):
        raise PublicControlError(
            "ordinary M6 prepared MTZ changed its selected observations"
        )
    free_r = _free_r_column(
        mtz,
        observation_dataset_id=observation.dataset_id,
    )
    if (free_r.dataset_id, free_r.label) != (
        record.free_r_dataset_id,
        record.free_r_label,
    ):
        raise PublicControlError("ordinary M6 prepared MTZ changed its Free-R identity")
    hkl_sha256, membership_sha256 = _hkl_free_r_digests(
        mtz,
        free_r_dataset_id=free_r.dataset_id,
        free_r_label=free_r.label,
    )
    if (
        hkl_sha256 != record.hkl_set_sha256
        or membership_sha256 != record.hkl_to_free_r_membership_sha256
    ):
        raise PublicControlError(
            "ordinary M6 prepared MTZ changed its HKL/Free-R membership"
        )
    return resolved


def _converted_observation_mtz(structure_factors: Path, opaque_id: str) -> gemmi.Mtz:
    try:
        blocks = gemmi.as_refln_blocks(gemmi.cif.read_file(str(structure_factors)))
        candidates: list[gemmi.Mtz] = []
        for block in blocks:
            mtz = gemmi.CifToMtz().convert_block_to_mtz(block)
            observation, _, _ = select_observations(mtz, None)
            if observation is not None:
                candidates.append(mtz)
        if len(candidates) != 1:
            raise PublicControlError(
                "M6 structure factors must contain exactly one observed-data block"
            )
        mtz = candidates[0]
        _sanitise_mtz(mtz, opaque_id)
        return mtz
    except (RuntimeError, ValueError) as error:
        raise PublicControlError(
            f"cannot convert M6 structure factors {structure_factors}: {error}"
        ) from error


def _subset_mtz(
    source: gemmi.Mtz,
    columns: tuple[tuple[str, str, np.ndarray], ...],
    opaque_id: str,
) -> gemmi.Mtz:
    result = gemmi.Mtz(with_base=True)
    result.spacegroup = source.spacegroup
    result.set_cell_for_all(source.cell)
    dataset = result.add_dataset("opaque")
    for label, column_type, _ in columns:
        result.add_column(label, column_type, dataset.id)
    base = tuple(np.asarray(source.column_with_label(label).array) for label in "HKL")
    data = np.column_stack((*base, *(values for _, _, values in columns))).astype(
        np.float32
    )
    result.set_data(data)
    _sanitise_mtz(result, opaque_id)
    return result


def _map_columns(source: gemmi.Mtz) -> tuple[tuple[str, str, np.ndarray], ...]:
    labels = {column.label: column for column in source.columns}
    if not {"FWT", "PHWT"} <= labels.keys():
        raise PublicControlError("map-only M6 source lacks FWT/PHWT coefficients")
    selected: list[tuple[str, str, np.ndarray]] = []
    if "FreeR_flag" in labels:
        selected.append(
            (
                "FreeR_flag",
                labels["FreeR_flag"].type,
                np.asarray(labels["FreeR_flag"].array),
            )
        )
    selected.extend(
        (
            label,
            labels[label].type,
            np.asarray(labels[label].array),
        )
        for label in ("FWT", "PHWT")
    )
    return tuple(selected)


def _ambiguous_columns(
    source: gemmi.Mtz,
    *,
    conflicting: bool,
) -> tuple[tuple[str, str, np.ndarray], ...]:
    observation, _, _ = select_observations(source, None)
    if observation is None or len(observation.labels) != 2:
        raise PublicControlError("ambiguous-column source lacks one ordinary pair")
    value = source.column_with_label(observation.labels[0])
    sigma = source.column_with_label(observation.labels[1])
    prefix = "I" if observation.observation_type == "intensity" else "F"
    value_one = np.asarray(value.array)
    sigma_one = np.asarray(sigma.array)
    value_two = np.array(value_one, copy=True)
    sigma_two = np.array(sigma_one, copy=True)
    if conflicting:
        finite = np.isfinite(value_two)
        value_two[finite] = value_two[finite] * np.float32(1.25) + np.float32(1.0)
    columns: list[tuple[str, str, np.ndarray]] = []
    labels = {column.label: column for column in source.columns}
    if "FreeR_flag" in labels:
        columns.append(
            (
                "FreeR_flag",
                labels["FreeR_flag"].type,
                np.asarray(labels["FreeR_flag"].array),
            )
        )
    columns.extend(
        (
            (f"{prefix}X", value.type, value_one),
            (f"SIG{prefix}X", sigma.type, sigma_one),
            (f"{prefix}Y", value.type, value_two),
            (f"SIG{prefix}Y", sigma.type, sigma_two),
        )
    )
    return tuple(columns)


def write_m6_mtz_variant(
    source: gemmi.Mtz,
    output: Path,
    *,
    opaque_id: str,
    variation: M6MtzVariation,
) -> M6MtzSanitisationRecord | None:
    """Write one sanitised ordinary or predeclared MTZ edge-case variant."""

    ordinary_details: (
        tuple[tuple[str, ...], M6ObservationType, int, str, str] | None
    ) = None
    if variation == "ordinary":
        (
            result,
            observation_labels,
            observation_type,
            output_dataset_id,
            hkl_set_sha256,
            membership_sha256,
        ) = _ordinary_mtz(source, opaque_id=opaque_id)
        ordinary_details = (
            observation_labels,
            observation_type,
            output_dataset_id,
            hkl_set_sha256,
            membership_sha256,
        )
    elif variation == "map_only":
        result = _subset_mtz(source, _map_columns(source), opaque_id)
    elif variation == "equivalent_observation_arrays":
        result = _subset_mtz(
            source,
            _ambiguous_columns(source, conflicting=False),
            opaque_id,
        )
    else:
        result = _subset_mtz(
            source,
            _ambiguous_columns(source, conflicting=True),
            opaque_id,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        result.write_to_file(str(temporary))
        os.replace(temporary, output)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    if ordinary_details is None:
        return None

    try:
        written = gemmi.read_mtz_file(str(output.resolve(strict=True)))
    except (OSError, RuntimeError) as error:
        raise PublicControlError(
            f"cannot re-read ordinary M6 sanitised MTZ {output}: {error}"
        ) from error
    (
        observation_labels,
        observation_type,
        output_dataset_id,
        hkl_set_sha256,
        membership_sha256,
    ) = ordinary_details
    written_labels = tuple(column.label for column in written.columns)
    expected_labels = ("H", "K", "L", *observation_labels)
    if len(written_labels) != len(expected_labels) + 1:
        raise PublicControlError(
            "ordinary M6 sanitised MTZ column count changed after writing"
        )
    free_r_label = written_labels[-1]
    if written_labels != (*expected_labels, free_r_label):
        raise PublicControlError(
            "ordinary M6 sanitised MTZ column order changed after writing"
        )
    written_hkl_sha256, written_membership_sha256 = _hkl_free_r_digests(
        written,
        free_r_dataset_id=output_dataset_id,
        free_r_label=free_r_label,
    )
    if (
        written_hkl_sha256 != hkl_set_sha256
        or written_membership_sha256 != membership_sha256
    ):
        raise PublicControlError(
            "ordinary M6 sanitised MTZ changed HKL/Free-R membership on disk"
        )
    identity = {
        "schema_version": "1.0",
        "contract": "ordinary_observations_free_r_only_v1",
        "output_mtz_sha256": sha256_file(output),
        "output_mtz_size_bytes": output.stat().st_size,
        "reflection_count": written.nreflections,
        "output_column_labels": written_labels,
        "observation_dataset_id": output_dataset_id,
        "observation_labels": observation_labels,
        "observation_type": observation_type,
        "free_r_dataset_id": output_dataset_id,
        "free_r_label": free_r_label,
        "hkl_set_sha256": written_hkl_sha256,
        "hkl_to_free_r_membership_sha256": written_membership_sha256,
    }
    return M6MtzSanitisationRecord(
        schema_version="1.0",
        sanitisation_id=content_id("m6mtz_", identity),
        contract="ordinary_observations_free_r_only_v1",
        output_mtz_sha256=sha256_file(output),
        output_mtz_size_bytes=output.stat().st_size,
        reflection_count=written.nreflections,
        output_column_labels=written_labels,
        observation_dataset_id=output_dataset_id,
        observation_labels=observation_labels,
        observation_type=observation_type,
        free_r_dataset_id=output_dataset_id,
        free_r_label=free_r_label,
        hkl_set_sha256=written_hkl_sha256,
        hkl_to_free_r_membership_sha256=written_membership_sha256,
    )


def _target_maps(
    protocol: M6BenchmarkProtocol,
) -> tuple[
    dict[str, M6PositiveTargetSpec | M6AssumptionControlSpec],
    dict[str, M6PositiveTargetSpec],
]:
    positives = {target.target_key: target for target in protocol.positives}
    all_targets: dict[str, M6PositiveTargetSpec | M6AssumptionControlSpec] = {
        **positives,
        **{control.target_key: control for control in protocol.assumption_controls},
    }
    return all_targets, positives


def _case_catalogue_id(
    case: M6CaseSpec,
    target: M6PositiveTargetSpec | M6AssumptionControlSpec,
) -> str:
    return case.wrong_catalogue_id or target.catalogue_id


def _mtz_variation(case: M6CaseSpec) -> M6MtzVariation:
    return _M6_MTZ_VARIATION_BY_CASE_KIND.get(case.case_kind, "ordinary")


def is_m6_ordinary_case_kind(case_kind: str) -> bool:
    """Return whether one frozen case uses the ordinary MTZ contract."""

    return case_kind not in _M6_MTZ_VARIATION_BY_CASE_KIND


def _fault_control(case: M6CaseSpec) -> dict[str, object] | None:
    controls: dict[str, dict[str, object]] = {
        "duplicate_locus": {"duplicate_locus": True},
        "missing_pdb_model": {
            "edge_stimulus": "missing_pdb_model",
            "pdb_coordinate_route": "forced_no_model",
        },
        "wrong_sds_mass": {
            "edge_stimulus": "wrong_sds_mass",
            "sds_mass": "deliberately_wrong",
        },
        "non_top_matthews": {
            "edge_stimulus": "non_top_matthews",
            "retain_non_top_matthews": True,
        },
        "map_only_mtz": {
            "edge_stimulus": "map_only_mtz",
            "reflection_mode": "map_only",
        },
        "ambiguous_columns_equivalent": {
            "edge_stimulus": "ambiguous_columns_equivalent",
            "observation_columns": "equivalent_duplicate",
        },
        "ambiguous_columns_conflicting": {
            "edge_stimulus": "ambiguous_columns_conflicting",
            "observation_columns": "conflicting_duplicate",
        },
        "remote_disabled": {
            "edge_stimulus": "remote_disabled",
            "remote_provider": "disabled",
        },
        "remote_rate_limited": {
            "edge_stimulus": "remote_rate_limited",
            "remote_provider": "local_http_fixture",
            "local_http_response": M6_RATE_LIMIT_HTTP_FIXTURE,
        },
        "missing_phenix": {
            "edge_stimulus": "missing_phenix",
            "phenix_manifest": "isolated_missing_runtime",
        },
    }
    payload = controls.get(case.case_kind)
    if payload is None:
        return None
    return {"schema_version": "1.0", **payload}


def _prepared_object(role: str, path: Path, media_type: str) -> dict[str, object]:
    return {
        "role": role,
        "path": str(path.resolve(strict=True)),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "media_type": media_type,
    }


def prepare_m6_inputs(
    request: M6InputPreparationRequest,
) -> M6InputPreparationResult:
    """Verify frozen sources and prepare all 63 sanitised discovery cases."""

    protocol_path = request.protocol.resolve(strict=True)
    protocol = load_m6_protocol(protocol_path)
    if request.output_directory.exists() or request.output_directory.is_symlink():
        raise PublicControlError(
            f"M6 preparation output target already exists: {request.output_directory}"
        )
    request.output_directory.mkdir(parents=True)
    output_root = request.output_directory.resolve(strict=True)
    rcsb_root = request.rcsb_directory.resolve(strict=True)
    catalogue_roots = tuple(
        root.resolve(strict=True) for root in request.catalogue_directories
    )
    protocol_sha256 = sha256_file(protocol_path)
    verified_snapshots, verified_families = _verify_m6_family_snapshots(
        protocol, rcsb_root
    )

    catalogue_records: dict[str, tuple[SeqRecord, ...]] = {}
    source_inventory: list[dict[str, object]] = [
        {"role": "cluster_snapshot", **snapshot.as_record()}
        for snapshot in verified_snapshots
    ]
    for catalogue in protocol.catalogues:
        path = _catalogue_path(catalogue_roots, catalogue.assembly_accession)
        verified = _verify_file(
            path,
            sha256=catalogue.protein_fasta_sha256,
            size_bytes=catalogue.protein_fasta_size_bytes,
            label=f"M6 catalogue {catalogue.catalogue_id}",
        )
        catalogue_records[catalogue.catalogue_id] = _read_catalogue(verified)
        source_inventory.append(
            {
                "role": "catalogue",
                "catalogue_id": catalogue.catalogue_id,
                "sha256": catalogue.protein_fasta_sha256,
                "size_bytes": catalogue.protein_fasta_size_bytes,
            }
        )

    all_targets, positives = _target_maps(protocol)
    base_mtz: dict[str, gemmi.Mtz] = {}
    for target in all_targets.values():
        source = target.source
        coordinates = _verify_file(
            rcsb_root / f"{source.pdb_id}.cif",
            sha256=source.coordinates.sha256,
            size_bytes=source.coordinates.size_bytes,
            label=f"M6 coordinates {source.pdb_id}",
        )
        structure_factors = _verify_file(
            rcsb_root / f"{source.pdb_id}-sf.cif",
            sha256=source.structure_factors.sha256,
            size_bytes=source.structure_factors.size_bytes,
            label=f"M6 structure factors {source.pdb_id}",
        )
        source_inventory.append(
            {
                "role": "coordinates",
                "pdb_id": source.pdb_id,
                "sha256": sha256_file(coordinates),
                "size_bytes": coordinates.stat().st_size,
            }
        )
        source_inventory.append(
            {
                "role": "structure_factors",
                "pdb_id": source.pdb_id,
                "sha256": sha256_file(structure_factors),
                "size_bytes": structure_factors.stat().st_size,
            }
        )
        base_mtz[target.target_key] = _converted_observation_mtz(
            structure_factors, target.target_key
        )

    catalogue_cache: dict[
        tuple[str, str, str | None], tuple[Path, tuple[_OpaqueRecord, ...]]
    ] = {}
    mtz_cache: dict[
        tuple[str, M6MtzVariation],
        tuple[Path, M6MtzSanitisationRecord | None],
    ] = {}
    prepared_cases: list[dict[str, object]] = []
    private_cases: list[dict[str, object]] = []
    for case in protocol.cases:
        target = all_targets[case.target_key]
        catalogue_id = _case_catalogue_id(case, target)
        records = catalogue_records[catalogue_id]
        remove_digest: str | None = None
        duplicate_digest: str | None = None
        duplicate_case: str | None = None
        if case.case_kind == "target_absent":
            remove_digest = positives[case.target_key].target_sequence_sha256
        elif case.case_kind == "wrong_related_catalogue":
            target_digest = positives[case.target_key].target_sequence_sha256
            if any(
                sequence_digest(str(record.seq)) == target_digest for record in records
            ):
                raise PublicControlError(
                    f"wrong-related catalogue contains target in {case.case_id}"
                )
        elif case.case_kind == "duplicate_locus":
            duplicate_digest = positives[case.target_key].target_sequence_sha256
            duplicate_case = case.case_id
        cache_key = (catalogue_id, remove_digest or "", duplicate_case)
        catalogue_entry = catalogue_cache.get(cache_key)
        if catalogue_entry is None:
            opaque_records, _ = anonymise_m6_catalogue(
                records,
                remove_sequence_sha256=remove_digest,
                duplicate_sequence_sha256=duplicate_digest,
                duplicate_case_id=duplicate_case,
            )
            catalogue_path = output_root / "catalogues" / f"{case.case_id}.faa"
            _write_opaque_catalogue(catalogue_path, opaque_records)
            catalogue_entry = (catalogue_path, opaque_records)
            catalogue_cache[cache_key] = catalogue_entry
        catalogue_path, opaque_records = catalogue_entry

        variation = _mtz_variation(case)
        mtz_key = (case.target_key, variation)
        mtz_entry = mtz_cache.get(mtz_key)
        if mtz_entry is None:
            mtz_path = output_root / "reflections" / f"{case.case_id}.mtz"
            sanitisation_record = write_m6_mtz_variant(
                base_mtz[case.target_key],
                mtz_path,
                opaque_id=case.case_id,
                variation=variation,
            )
            mtz_entry = (mtz_path, sanitisation_record)
            mtz_cache[mtz_key] = mtz_entry
        mtz_path, sanitisation_record = mtz_entry

        sds_mass = []
        if case.case_kind == "wrong_sds_mass":
            sds_mass = [1.0 if case.case_id.endswith("053") else 1000.0]
        config_path = output_root / "configs" / f"{case.case_id}.json"
        atomic_write_json(
            config_path,
            {
                "schema_version": "1.0",
                "prototype": {
                    "asu_model": "single_protein_species_multi_copy",
                    "profile": "pilot",
                },
                "catalogue": {
                    "min_length_aa": 30,
                    "ambiguous_residue_policy": "warn",
                    "remove_terminal_stop": True,
                },
                "providers": {
                    "pdb_sequence": {"enabled": True, "max_hits": 3},
                    "foldseek_prostt5_pdb": {"enabled": True, "max_hits": 3},
                    "esm_atlas": {
                        "enabled": case.case_kind == "remote_rate_limited",
                        "max_hits": 2,
                        "requests_per_minute": 10,
                        "max_sequence_length": 1500,
                    },
                    "afdb_exact": {"enabled": False, "max_hits": 1},
                },
                "matthews": {
                    "max_hypotheses_per_candidate": 4,
                    "min_solvent_fraction": 0.1,
                    "max_solvent_fraction": 0.9,
                },
                "search_limits": {
                    "max_structural_hypotheses": 100,
                    "max_first_copy_jobs": 25,
                },
                "review": {
                    "primary_shortlist_size": 10,
                    "extended_shortlist_size": 25,
                },
                "retention": {
                    "max_full_artifact_finalists": 25,
                    "retain_all_logs": True,
                },
            },
        )
        leakage = case.case_kind == "leakage_positive"
        policy_path = output_root / "policies" / f"{case.case_id}.json"
        atomic_write_json(
            policy_path,
            {
                "schema_version": "1.0",
                "mode": "query_relative_leakage" if leakage else "operational",
                "maximum_model_identity_fraction": (
                    protocol.leakage_policy.maximum_allowed_identity_fraction
                    if leakage
                    else None
                ),
                "minimum_exclusion_coverage_fraction": (
                    protocol.leakage_policy.minimum_exclusion_coverage_fraction
                    if leakage
                    else None
                ),
                "exact_deposition_removed_by_trusted_transition": True,
                "applies_to_all_model_routes": True,
                "retain_rejected_model_annotations": True,
                "candidate_policy": "retain_all",
                "score_policy": "llg_tfz_annotations_only",
                "afdb_exact_disabled_because_source_ids_are_opaque": True,
                "sds_page_mass_kda": sds_mass,
                "threads": 8,
                "maximum_concurrent_phenix_attempts": 4,
                "trusted_model_transition_required": True,
            },
        )
        objects = [
            _prepared_object("catalogue", catalogue_path, "text/x-fasta"),
            _prepared_object("reflections", mtz_path, "application/x-mtz"),
            _prepared_object("analysis_config", config_path, "application/json"),
            _prepared_object("model_policy", policy_path, "application/json"),
        ]
        fault = _fault_control(case)
        if fault is not None:
            fault_path = output_root / "controls" / f"{case.case_id}.json"
            atomic_write_json(fault_path, fault)
            objects.append(
                _prepared_object("fault_control", fault_path, "application/json")
            )
        prepared_case: dict[str, object] = {
            "case_id": case.case_id,
            "objects": objects,
        }
        if sanitisation_record is not None:
            prepared_case["reflection_sanitisation"] = sanitisation_record.model_dump(
                mode="json"
            )
        prepared_cases.append(prepared_case)

        target_digests: tuple[str, ...]
        expected_copy_count: int | None
        source_pdb_id: str
        if isinstance(target, M6PositiveTargetSpec):
            target_digests = (target.target_sequence_sha256,)
            expected_copy_count = target.expected_asu_copy_count
            source_pdb_id = target.source.pdb_id
        else:
            target_digests = tuple(
                protein.sequence_sha256 for protein in target.proteins
            )
            expected_copy_count = None
            source_pdb_id = target.source.pdb_id
        target_loci = {
            digest: [
                record.opaque_id
                for record in opaque_records
                if record.sequence_sha256 == digest
            ]
            for digest in target_digests
        }
        private_cases.append(
            {
                "case_id": case.case_id,
                "case_kind": case.case_kind,
                "target_key": case.target_key,
                "source_pdb_id": source_pdb_id,
                "target_sequence_sha256": list(target_digests),
                "target_opaque_loci": target_loci,
                "expected_asu_copy_count": expected_copy_count,
            }
        )

    preparation_manifest = output_root / "preparation.json"
    atomic_write_json(
        preparation_manifest,
        {
            "schema_version": "1.0",
            "protocol_id": protocol.protocol_id,
            "protocol_sha256": protocol_sha256,
            "cases": prepared_cases,
        },
    )
    private_truth_map = output_root / "private_truth_map.json"
    atomic_write_json(
        private_truth_map,
        {
            "schema_version": "1.1",
            "protocol_id": protocol.protocol_id,
            "protocol_sha256": protocol_sha256,
            "cluster_snapshots": [
                snapshot.as_record() for snapshot in verified_snapshots
            ],
            "verified_families": [family.as_record() for family in verified_families],
            "cases": private_cases,
        },
    )
    source_inventory_path = output_root / "source_inventory.json"
    atomic_write_json(
        source_inventory_path,
        {
            "schema_version": "1.1",
            "protocol_id": protocol.protocol_id,
            "protocol_sha256": protocol_sha256,
            "source_count": len(source_inventory),
            "sources": source_inventory,
        },
    )
    return M6InputPreparationResult(
        protocol_id=protocol.protocol_id,
        case_count=len(prepared_cases),
        preparation_manifest=preparation_manifest,
        private_truth_map=private_truth_map,
        source_inventory=source_inventory_path,
    )
