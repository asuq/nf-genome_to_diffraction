"""Candidate-specific Matthews hypotheses and soft SDS-PAGE compatibility."""

import csv
import io
import logging
import os
import tempfile
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_text
from genome_to_diffraction.ids import canonical_json_text, content_id
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
PRIOR_BACKEND = "broad_solvent_centrality_v1_uncalibrated"
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


def _load_jsonl(path: Path, model: type[BaseModel]) -> tuple[BaseModel, ...]:
    records: list[BaseModel] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(model.model_validate_json(line))
                except (ValidationError, ValueError) as error:
                    raise MatthewsInputError(
                        f"{path}:{line_number}: invalid record: {error}"
                    ) from error
    except OSError as error:
        raise MatthewsInputError(f"cannot read {path}: {error}") from error
    if not records:
        raise MatthewsInputError(f"JSONL input contains no records: {path}")
    return tuple(records)


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


def _physical_status(
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


def _prior_score(solvent_midpoint: float, *, minimum: float, maximum: float) -> float:
    """Return a transparent bounded heuristic, not an empirical probability."""

    centre = (minimum + maximum) / 2
    half_width = (maximum - minimum) / 2
    if half_width <= 0:
        raise ValueError("solvent-fraction bounds must span a positive interval")
    return max(0.0, 1.0 - abs(solvent_midpoint - centre) / half_width)


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
    rows: list[MatthewsHypothesis] = []
    minimum = config.matthews.min_solvent_fraction
    maximum = config.matthews.max_solvent_fraction
    for copy_count in range(
        config.matthews.min_copy_count, config.matthews.max_copy_count + 1
    ):
        identity = {
            "preflight_id": preflight.preflight_id,
            "sequence_group_id": group.sequence_group_id,
            "copy_count": copy_count,
            "prior_backend": PRIOR_BACKEND,
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
        warnings = list(sds.warnings)
        if exact_mass is not None:
            total_mass = exact_mass * copy_count
            coefficient = preflight.asu_volume_a3 / total_mass
            solvent = 1.0 - 1.23 / coefficient
            status = _physical_status(
                solvent, solvent, minimum=minimum, maximum=maximum
            )
            prior = _prior_score(solvent, minimum=minimum, maximum=maximum)
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
            status = _physical_status(
                solvent_lower,
                solvent_upper,
                minimum=minimum,
                maximum=maximum,
            )
            prior = _prior_score(
                (solvent_lower + solvent_upper) / 2,
                minimum=minimum,
                maximum=maximum,
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
        f"Prior backend: `{PRIOR_BACKEND}`. This is a transparent broad physical",
        "ranking heuristic, not a calibrated empirical probability.",
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
    preflights_raw = _load_jsonl(
        request.preflight_jsonl.resolve(strict=True), MtzPreflightRecord
    )
    groups_raw = _load_jsonl(
        request.sequence_groups_jsonl.resolve(strict=True), SequenceGroupRecord
    )
    sources_raw = _load_jsonl(
        request.source_records_jsonl.resolve(strict=True), SourceProteinRecord
    )
    preflights = tuple(
        record for record in preflights_raw if isinstance(record, MtzPreflightRecord)
    )
    groups = tuple(
        record for record in groups_raw if isinstance(record, SequenceGroupRecord)
    )
    sources = tuple(
        record for record in sources_raw if isinstance(record, SourceProteinRecord)
    )
    preflight_by_crystal = {record.crystal_id: record for record in preflights}
    group_by_id = {group.sequence_group_id: group for group in groups}
    groups_by_catalogue: dict[str, set[str]] = defaultdict(set)
    for source in sources:
        if source.sequence_group_id not in group_by_id:
            raise MatthewsInputError(
                f"source record references missing group: {source.sequence_group_id}"
            )
        groups_by_catalogue[source.catalogue_id].add(source.sequence_group_id)

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
            hypotheses.extend(enumerate_group(group, crystal, preflight, config_model))
            enumerated_groups += 1
        if enumerated_groups == 0:
            raise MatthewsInputError(
                f"crystal {crystal.crystal_id} has no mass-eligible sequence groups"
            )
        _LOGGER.info(
            "Matthews enumeration complete for crystal",
            extra={
                "crystal_id": crystal.crystal_id,
                "sequence_groups": enumerated_groups,
                "copy_counts_per_group": (
                    config_model.matthews.max_copy_count
                    - config_model.matthews.min_copy_count
                    + 1
                ),
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
