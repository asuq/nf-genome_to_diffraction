"""Candidate-specific Matthews hypotheses and soft SDS-PAGE compatibility."""

import csv
import io
import logging
import math
import os
import tempfile
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_text
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.matthews.probability import (
    PRIOR_BACKEND,
    MatthewsProbabilityDistribution,
    probability_distribution,
    reference_metadata,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    CrystalEntry,
    CrystalManifest,
    PipelineConfig,
    SdsBandRole,
    SdsPageCondition,
)
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MtzPreflightRecord,
    PhysicalStatus,
    PreflightDecision,
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.status import InputContractError

_LOGGER = logging.getLogger("genome_to_diffraction.matthews")
COPY_RANGE_BACKEND = "asu_sequence_mass_solvent_overlap_v1"
MAXIMUM_SAFE_DYNAMIC_COPY_COUNT = 100_000
_EXCLUDED_SEQUENCE_FLAGS = frozenset(
    {
        "excluded_ambiguous_or_nonstandard_residue",
        "excluded_below_minimum_length",
        "internal_stop",
        "mass_unavailable",
    }
)


class MatthewsInputError(InputContractError):
    """Preflight, catalogue, or configuration records are inconsistent."""


@dataclass(frozen=True)
class MatthewsRequest:
    """Paths required for candidate-specific copy enumeration."""

    crystal_manifest: Path
    pipeline_config: Path
    preflight_jsonl: Path
    sequence_groups_jsonl: Path
    source_records_jsonl: Path
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True)
class MatthewsResult:
    """All enumerated hypotheses and stable published files."""

    hypotheses: tuple[MatthewsHypothesis, ...]
    jsonl_path: Path
    tsv_path: Path
    parquet_path: Path
    report_path: Path


@dataclass(frozen=True)
class SdsAssessment:
    """Nearest apparent SDS-PAGE band and a non-filtering compatibility label."""

    nearest_band_kda: float | None
    absolute_difference_kda: float | None
    fractional_difference: float | None
    label: Literal["strong", "compatible", "weak", "unavailable"]
    warnings: tuple[str, ...]


def _load_jsonl[T: BaseModel](path: Path, model: type[T]) -> tuple[tuple[int, T], ...]:
    records: list[tuple[int, T]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    records.append((line_number, model.model_validate_json(line)))
                except (ValidationError, ValueError) as error:
                    raise MatthewsInputError(
                        f"{path}:{line_number}: invalid record: {error}"
                    ) from error
    except OSError as error:
        raise MatthewsInputError(f"cannot read {path}: {error}") from error
    if not records:
        raise MatthewsInputError(f"JSONL input contains no records: {path}")
    return tuple(records)


def _unique_index[T](
    records: Sequence[tuple[int, T]],
    *,
    record_type: str,
    key_name: str,
    key: Callable[[T], str],
) -> dict[str, T]:
    index: dict[str, T] = {}
    first_line_by_id: dict[str, int] = {}
    for line_number, record in records:
        identifier = key(record)
        first_line = first_line_by_id.get(identifier)
        if first_line is not None:
            raise MatthewsInputError(
                f"duplicate {record_type}.{key_name} {identifier!r} "
                f"at lines {first_line} and {line_number}"
            )
        first_line_by_id[identifier] = line_number
        index[identifier] = record
    return index


def _require_exact_coverage(
    observed: set[str],
    expected: set[str],
    *,
    observed_name: str,
    expected_name: str,
) -> None:
    if observed == expected:
        return
    missing = ",".join(sorted(expected - observed)) or "none"
    unexpected = ",".join(sorted(observed - expected)) or "none"
    raise MatthewsInputError(
        f"{observed_name} coverage differs from {expected_name}: "
        f"missing={missing}; unexpected={unexpected}"
    )


def _bounded_distance(lower_kda: float, upper_kda: float, band_kda: float) -> float:
    if lower_kda <= band_kda <= upper_kda:
        return 0.0
    return min(abs(lower_kda - band_kda), abs(upper_kda - band_kda))


def assess_sds(group: SequenceGroupRecord, crystal: CrystalEntry) -> SdsAssessment:
    """Calculate a soft monomer-mass prior without excluding the candidate."""

    bands = crystal.sds_page_mass_kda
    if not bands:
        return SdsAssessment(None, None, None, "unavailable", ())
    if group.molecular_mass_da is not None:
        mass_kda = group.molecular_mass_da / 1000.0
        differences = [abs(mass_kda - band) for band in bands]
        warnings: list[str] = []
    elif (
        group.molecular_mass_lower_da is not None
        and group.molecular_mass_upper_da is not None
    ):
        lower_kda = group.molecular_mass_lower_da / 1000.0
        upper_kda = group.molecular_mass_upper_da / 1000.0
        differences = [_bounded_distance(lower_kda, upper_kda, band) for band in bands]
        warnings = ["sds_comparison_uses_mass_bounds"]
    else:
        return SdsAssessment(None, None, None, "unavailable", ("sds_mass_unavailable",))
    fractional = [
        difference / band for difference, band in zip(differences, bands, strict=True)
    ]
    nearest_index = min(range(len(bands)), key=lambda index: (fractional[index], index))
    nearest_band = bands[nearest_index]
    nearest_difference = differences[nearest_index]
    nearest_fractional = fractional[nearest_index]
    roles = crystal.sds_page_band_roles
    role = roles[nearest_index] if roles else None
    condition = crystal.sds_page_condition
    within = nearest_fractional <= crystal.sds_page_tolerance_fraction
    strong = (
        nearest_fractional <= crystal.sds_page_tolerance_fraction / 2
        and condition is SdsPageCondition.REDUCING
        and role in {None, SdsBandRole.DOMINANT}
    )
    label: Literal["strong", "compatible", "weak", "unavailable"] = (
        "strong" if strong else "compatible" if within else "weak"
    )
    if condition in {SdsPageCondition.NONREDUCING, SdsPageCondition.UNKNOWN, None}:
        warnings.append("sds_condition_reduces_prior_strength")
    return SdsAssessment(
        nearest_band,
        nearest_difference,
        nearest_fractional,
        label,
        tuple(sorted(warnings)),
    )


def physical_status(
    lower: float,
    upper: float,
    *,
    minimum: float,
    maximum: float,
) -> PhysicalStatus:
    if upper < minimum or lower > maximum:
        return PhysicalStatus.IMPOSSIBLE
    if lower < minimum or upper > maximum:
        return PhysicalStatus.REVIEW
    boundary_margin = min(0.05, (maximum - minimum) / 4)
    if lower < minimum + boundary_margin or upper > maximum - boundary_margin:
        return PhysicalStatus.REVIEW
    return PhysicalStatus.PLAUSIBLE


def prior_score(
    solvent_midpoint: float,
    *,
    resolution_high_a: float,
    copy_count: int,
) -> float:
    """Return the empirical single-component Matthews ranking prior."""

    return probability_distribution(resolution_high_a).single_component_prior(
        copy_count,
        solvent_midpoint,
    )


def dynamic_copy_counts(
    *,
    v_asu_a3: float,
    mass_lower_da: float,
    mass_upper_da: float,
    minimum_solvent_fraction: float,
    maximum_solvent_fraction: float,
) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Derive the complete finite copy range that overlaps physical bounds."""

    if not math.isfinite(v_asu_a3) or v_asu_a3 <= 0:
        raise MatthewsInputError("Matthews ASU volume must be finite and positive")
    if not 0 <= minimum_solvent_fraction < maximum_solvent_fraction <= 1:
        raise MatthewsInputError("Matthews solvent bounds do not span an interval")
    if (
        not math.isfinite(mass_lower_da)
        or not math.isfinite(mass_upper_da)
        or mass_lower_da <= 0
        or mass_upper_da < mass_lower_da
    ):
        raise MatthewsInputError("Matthews sequence-mass bounds are invalid")
    upper_real = v_asu_a3 * (1.0 - minimum_solvent_fraction) / (1.23 * mass_lower_da)
    first = 1
    last = math.floor(upper_real + 1e-12)
    warnings: tuple[str, ...] = ()
    if last < first:
        last = first
        warnings = ("no_positive_copy_count_reaches_minimum_solvent_bound",)
    if last > MAXIMUM_SAFE_DYNAMIC_COPY_COUNT:
        raise MatthewsInputError(
            "dynamic Matthews copy range exceeds the fail-closed safety bound"
        )
    return tuple(range(first, last + 1)), warnings


def _sds_fields(assessment: SdsAssessment, crystal: CrystalEntry) -> dict[str, object]:
    return {
        "sds_page_nearest_band_kda": assessment.nearest_band_kda,
        "sds_page_absolute_difference_kda": assessment.absolute_difference_kda,
        "sds_page_fractional_difference": assessment.fractional_difference,
        "sds_page_prior_label": assessment.label,
        "sds_page_condition": crystal.sds_page_condition,
    }


def enumerate_group(
    group: SequenceGroupRecord,
    crystal: CrystalEntry,
    preflight: MtzPreflightRecord,
    config: PipelineConfig,
    *,
    distribution: MatthewsProbabilityDistribution | None = None,
) -> tuple[MatthewsHypothesis, ...]:
    """Enumerate and rank all configured copy counts for one candidate."""

    if preflight.decision is PreflightDecision.FAIL:
        raise MatthewsInputError(
            f"cannot enumerate Matthews hypotheses for failed preflight "
            f"{preflight.crystal_id}"
        )
    exact_mass = group.molecular_mass_da
    lower_mass = group.molecular_mass_lower_da
    upper_mass = group.molecular_mass_upper_da
    if exact_mass is None and (lower_mass is None or upper_mass is None):
        raise MatthewsInputError(
            f"sequence group has no usable molecular mass: {group.sequence_group_id}"
        )
    sds = assess_sds(group, crystal)
    empirical = distribution or probability_distribution(preflight.resolution_high_a)
    rows: list[MatthewsHypothesis] = []
    minimum = config.matthews.min_solvent_fraction
    maximum = config.matthews.max_solvent_fraction
    mass_lower = exact_mass if exact_mass is not None else lower_mass
    mass_upper = exact_mass if exact_mass is not None else upper_mass
    assert mass_lower is not None and mass_upper is not None
    copy_counts, copy_range_warnings = dynamic_copy_counts(
        v_asu_a3=preflight.asu_volume_a3,
        mass_lower_da=mass_lower,
        mass_upper_da=mass_upper,
        minimum_solvent_fraction=minimum,
        maximum_solvent_fraction=maximum,
    )
    for copy_count in copy_counts:
        identity = {
            "preflight_id": preflight.preflight_id,
            "sequence_group_id": group.sequence_group_id,
            "copy_count": copy_count,
            "prior_backend": PRIOR_BACKEND,
            "copy_range_backend": COPY_RANGE_BACKEND,
        }
        common: dict[str, object] = {
            "schema_version": "1.0",
            "hypothesis_id": content_id("matthews_", identity),
            "crystal_id": crystal.crystal_id,
            "sequence_group_id": group.sequence_group_id,
            "copy_count": copy_count,
            "v_asu_a3": preflight.asu_volume_a3,
            "prior_backend": PRIOR_BACKEND,
            "rank_within_candidate": 1,
            "retained": False,
            **_sds_fields(sds, crystal),
        }
        warnings = [*sds.warnings, *copy_range_warnings]
        if exact_mass is not None:
            total_mass = exact_mass * copy_count
            coefficient = preflight.asu_volume_a3 / total_mass
            solvent = 1.0 - 1.23 / coefficient
            status = physical_status(solvent, solvent, minimum=minimum, maximum=maximum)
            prior = empirical.single_component_prior(copy_count, solvent)
            row = MatthewsHypothesis.model_validate(
                {
                    **common,
                    "sequence_mass_da": exact_mass,
                    "total_mass_da": total_mass,
                    "matthews_coefficient": coefficient,
                    "solvent_fraction": solvent,
                    "matthews_prior": prior,
                    "physical_status": status,
                    "warnings": tuple(warnings),
                }
            )
        else:
            assert lower_mass is not None and upper_mass is not None
            total_lower = lower_mass * copy_count
            total_upper = upper_mass * copy_count
            coefficient_lower = preflight.asu_volume_a3 / total_upper
            coefficient_upper = preflight.asu_volume_a3 / total_lower
            solvent_lower = 1.0 - 1.23 / coefficient_lower
            solvent_upper = 1.0 - 1.23 / coefficient_upper
            status = physical_status(
                solvent_lower,
                solvent_upper,
                minimum=minimum,
                maximum=maximum,
            )
            prior = empirical.single_component_interval_prior(
                copy_count,
                solvent_lower,
                solvent_upper,
            )
            warnings.append("matthews_uses_sequence_mass_bounds")
            row = MatthewsHypothesis.model_validate(
                {
                    **common,
                    "sequence_mass_lower_da": lower_mass,
                    "sequence_mass_upper_da": upper_mass,
                    "total_mass_lower_da": total_lower,
                    "total_mass_upper_da": total_upper,
                    "matthews_coefficient_lower": coefficient_lower,
                    "matthews_coefficient_upper": coefficient_upper,
                    "solvent_fraction_lower": solvent_lower,
                    "solvent_fraction_upper": solvent_upper,
                    "matthews_prior": prior,
                    "physical_status": status,
                    "warnings": tuple(sorted(warnings)),
                }
            )
        rows.append(row)

    status_order = {
        PhysicalStatus.PLAUSIBLE: 0,
        PhysicalStatus.REVIEW: 1,
        PhysicalStatus.IMPOSSIBLE: 2,
    }
    ranked = sorted(
        rows,
        key=lambda row: (
            status_order[row.physical_status],
            -row.matthews_prior,
            row.copy_count,
        ),
    )
    retained_count = config.matthews.max_hypotheses_per_candidate
    return tuple(
        row.model_copy(
            update={
                "rank_within_candidate": rank,
                "retained": rank <= retained_count,
            }
        )
        for rank, row in enumerate(ranked, start=1)
    )


def _write_parquet(path: Path, rows: Sequence[MatthewsHypothesis]) -> None:
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
        pl.DataFrame([row.model_dump(mode="json") for row in rows]).write_parquet(
            temporary
        )
        os.replace(temporary, path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _write_outputs(
    output: Path, hypotheses: tuple[MatthewsHypothesis, ...]
) -> tuple[Path, Path, Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    jsonl_path = output / "matthews_hypotheses.jsonl"
    atomic_write_text(
        jsonl_path,
        "\n".join(canonical_json_text(row) for row in hypotheses) + "\n",
    )
    tsv_path = output / "matthews_hypotheses.tsv"
    stream = io.StringIO(newline="")
    columns = tuple(MatthewsHypothesis.model_fields)
    writer = csv.DictWriter(
        stream, fieldnames=columns, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    for row in hypotheses:
        document = row.model_dump(mode="json")
        for key, value in tuple(document.items()):
            if isinstance(value, list):
                document[key] = ";".join(str(item) for item in value)
        writer.writerow(document)
    atomic_write_text(tsv_path, stream.getvalue())
    parquet_path = output / "matthews_hypotheses.parquet"
    _write_parquet(parquet_path, hypotheses)
    report_path = output / "matthews_report.md"
    lines = [
        "# Matthews and SDS-PAGE hypothesis report",
        "",
        f"Prior backend: `{PRIOR_BACKEND}`. This multiplies a resolution-conditioned",
        "relative solvent density by the published empirical ASU homooligomer-copy",
        "frequency. It is a soft ranking weight, not an identity probability.",
        f"Copy range backend: `{COPY_RANGE_BACKEND}`; no static copy ceiling.",
        f"Reference resource SHA-256: `{reference_metadata()['resource_sha256']}`.",
        "",
    ]
    for row in hypotheses:
        if not row.retained:
            continue
        coefficient = (
            f"{row.matthews_coefficient:.4f}"
            if row.matthews_coefficient is not None
            else (
                f"{row.matthews_coefficient_lower:.4f}-"
                f"{row.matthews_coefficient_upper:.4f}"
            )
        )
        lines.append(
            f"- `{row.crystal_id}` / `{row.sequence_group_id}`: copy "
            f"{row.copy_count}, Vm {coefficient} A^3/Da, "
            f"physical `{row.physical_status}`, SDS `{row.sds_page_prior_label}`"
        )
    atomic_write_text(report_path, "\n".join(lines) + "\n")
    return jsonl_path, tsv_path, parquet_path, report_path


def enumerate_matthews(request: MatthewsRequest) -> MatthewsResult:
    """Join catalogue/crystal records and publish all copy hypotheses."""

    crystals_model = load_contract(
        request.crystal_manifest.resolve(strict=True),
        "crystal-manifest",
        progress=request.progress,
    )
    config_model = load_contract(
        request.pipeline_config.resolve(strict=True),
        "pipeline-config",
        progress=request.progress,
    )
    if not isinstance(crystals_model, CrystalManifest) or not isinstance(
        config_model, PipelineConfig
    ):
        raise TypeError("Matthews enumeration received unexpected contracts")
    preflight_records = _load_jsonl(
        request.preflight_jsonl.resolve(strict=True), MtzPreflightRecord
    )
    group_records = _load_jsonl(
        request.sequence_groups_jsonl.resolve(strict=True), SequenceGroupRecord
    )
    source_records = _load_jsonl(
        request.source_records_jsonl.resolve(strict=True), SourceProteinRecord
    )
    preflight_by_crystal = _unique_index(
        preflight_records,
        record_type="MtzPreflightRecord",
        key_name="crystal_id",
        key=lambda record: record.crystal_id,
    )
    group_by_id = _unique_index(
        group_records,
        record_type="SequenceGroupRecord",
        key_name="sequence_group_id",
        key=lambda record: record.sequence_group_id,
    )
    source_by_id = _unique_index(
        source_records,
        record_type="SourceProteinRecord",
        key_name="source_record_id",
        key=lambda record: record.source_record_id,
    )
    _require_exact_coverage(
        set(preflight_by_crystal),
        {crystal.crystal_id for crystal in crystals_model.crystals},
        observed_name="MtzPreflightRecord.crystal_id",
        expected_name="CrystalManifest.crystal_id",
    )
    sources = tuple(source_by_id.values())
    _require_exact_coverage(
        set(group_by_id),
        {source.sequence_group_id for source in sources},
        observed_name="SequenceGroupRecord.sequence_group_id",
        expected_name="SourceProteinRecord.sequence_group_id",
    )
    source_count_by_group: dict[str, int] = defaultdict(int)
    groups_by_catalogue: dict[str, set[str]] = defaultdict(set)
    for source in sources:
        source_count_by_group[source.sequence_group_id] += 1
        groups_by_catalogue[source.catalogue_id].add(source.sequence_group_id)
    for group_id, group in group_by_id.items():
        source_count = source_count_by_group[group_id]
        if group.source_record_count != source_count:
            raise MatthewsInputError(
                "SequenceGroupRecord.source_record_count differs from unique "
                f"SourceProteinRecord coverage for {group_id}: "
                f"expected={group.source_record_count}; observed={source_count}"
            )

    hypotheses: list[MatthewsHypothesis] = []
    for crystal in tqdm(
        crystals_model.crystals,
        desc="Enumerate Matthews hypotheses",
        unit="crystal",
        disable=not request.progress,
    ):
        preflight = preflight_by_crystal.get(crystal.crystal_id)
        if preflight is None:
            raise MatthewsInputError(
                f"no preflight record for crystal {crystal.crystal_id}"
            )
        group_ids = sorted(groups_by_catalogue.get(crystal.catalogue_id, set()))
        if not group_ids:
            raise MatthewsInputError(
                f"catalogue {crystal.catalogue_id} has no imported sequence groups"
            )
        enumerated_groups = 0
        crystal_hypothesis_count = 0
        crystal_maximum_copy_count = 0
        empirical = probability_distribution(preflight.resolution_high_a)
        for group_id in tqdm(
            group_ids,
            desc=f"Matthews {crystal.crystal_id}",
            unit="candidate",
            disable=not request.progress,
            leave=False,
        ):
            group = group_by_id[group_id]
            if set(group.quality_flags) & _EXCLUDED_SEQUENCE_FLAGS:
                _LOGGER.warning(
                    "skipping sequence group ineligible for Matthews enumeration",
                    extra={
                        "crystal_id": crystal.crystal_id,
                        "sequence_group_id": group_id,
                        "quality_flags": group.quality_flags,
                    },
                )
                continue
            group_hypotheses = enumerate_group(
                group,
                crystal,
                preflight,
                config_model,
                distribution=empirical,
            )
            hypotheses.extend(group_hypotheses)
            enumerated_groups += 1
            crystal_hypothesis_count += len(group_hypotheses)
            crystal_maximum_copy_count = max(
                crystal_maximum_copy_count,
                max(row.copy_count for row in group_hypotheses),
            )
        if enumerated_groups == 0:
            raise MatthewsInputError(
                f"crystal {crystal.crystal_id} has no mass-eligible sequence groups"
            )
        _LOGGER.info(
            "Matthews enumeration complete for crystal",
            extra={
                "crystal_id": crystal.crystal_id,
                "sequence_groups": enumerated_groups,
                "dynamic_hypothesis_count": crystal_hypothesis_count,
                "maximum_dynamic_copy_count": crystal_maximum_copy_count,
                "probability_reference_records": empirical.reference_record_count,
            },
        )
    ordered = tuple(
        sorted(
            hypotheses,
            key=lambda row: (
                row.crystal_id,
                row.sequence_group_id,
                row.rank_within_candidate,
            ),
        )
    )
    paths = _write_outputs(request.output_directory.resolve(), ordered)
    _LOGGER.info(
        "all Matthews hypotheses published",
        extra={
            "hypotheses": len(ordered),
            "retained": sum(row.retained for row in ordered),
            "output_directory": str(request.output_directory.resolve()),
        },
    )
    return MatthewsResult(ordered, *paths)
