"""Independent Gemmi MTZ inspection and isolated Phenix Xtriage preflight."""

import csv
import io
import logging
import re
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast

import gemmi
from pydantic import JsonValue
from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_text, sha256_file
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.phenix.runtime import capture_from_manifest
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    CrystalEntry,
    CrystalManifest,
    PhenixInstallManifest,
)
from genome_to_diffraction.schemas.results import (
    AssessmentStatus,
    MtzColumnRecord,
    MtzPreflightRecord,
    PreflightDecision,
)
from genome_to_diffraction.status import (
    ExecutionStatus,
    InputContractError,
    ToolExecutionError,
)

_LOGGER = logging.getLogger("genome_to_diffraction.diffraction")
_MAP_LABEL = re.compile(
    r"(?:^|[^A-Z0-9])(2?FOFC|DELFWT|FWT|PHWT|FMODEL|FC)(?:$|[^A-Z0-9])"
)


class MtzPreflightError(InputContractError):
    """An MTZ file cannot satisfy the diffraction input contract."""


class XtriageExecutionError(ToolExecutionError):
    """Phenix Xtriage returned a non-zero exit status."""


@dataclass(frozen=True)
class PreflightRequest:
    """Inputs for inspecting every crystal in one manifest."""

    crystal_manifest: Path
    output_directory: Path
    phenix_manifest: Path | None = None
    skip_xtriage: bool = False
    progress: bool = True
    xtriage_timeout_seconds: float = 3600.0


@dataclass(frozen=True)
class PreflightResult:
    """Machine records and stable output paths from a batch preflight."""

    records: tuple[MtzPreflightRecord, ...]
    jsonl_path: Path
    tsv_path: Path
    report_path: Path


@dataclass(frozen=True)
class _ObservationCandidate:
    labels: tuple[str, ...]
    observation_type: Literal["intensity", "amplitude"]
    rank: int

    @property
    def rendered(self) -> str:
        return ",".join(self.labels)


@dataclass(frozen=True)
class XtriageAssessment:
    """Normalised subset of Xtriage output used by preflight decisions."""

    version: str | None
    completeness: float | None
    mean_i_over_sigma: float | None
    anisotropy_status: AssessmentStatus
    tncs_status: AssessmentStatus
    twinning_status: AssessmentStatus
    symmetry_status: AssessmentStatus
    matthews_rows: tuple[XtriageMatthewsRow, ...]
    warning_codes: tuple[str, ...]
    summary: dict[str, JsonValue]


@dataclass(frozen=True)
class XtriageMatthewsRow:
    """Reference Matthews row parsed from a preserved Xtriage fixture/log."""

    copy_count: int
    matthews_coefficient: float
    solvent_fraction: float


def _normalise_label(label: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", label.upper())


def _anomalous_sign(label: str) -> Literal["+", "-"] | None:
    stripped = label.strip()
    if stripped.endswith(("(+)", "+")):
        return "+"
    if stripped.endswith(("(-)", "-")):
        return "-"
    return None


def _without_anomalous_sign(label: str) -> str:
    return re.sub(r"\([+-]\)$|[+-]$", "", label.strip())


def _is_sigma_for(value_label: str, sigma_label: str) -> bool:
    value = _normalise_label(value_label)
    sigma = _normalise_label(sigma_label)
    return sigma == f"SIG{value}"


def _observation_rank(label: str, observation_type: str) -> int:
    base = _normalise_label(_without_anomalous_sign(label))
    priorities = (
        {"I": 0, "IMEAN": 1, "IOBS": 2}
        if observation_type == "intensity"
        else {"F": 0, "FP": 1, "FOBS": 2}
    )
    return priorities.get(base, 100)


def _is_map_coefficient(label: str) -> bool:
    padded = f" {label.upper()} "
    return _MAP_LABEL.search(padded) is not None


def _candidate_pairs(mtz: gemmi.Mtz) -> tuple[_ObservationCandidate, ...]:
    pairs: list[_ObservationCandidate] = []
    for value in mtz.columns:
        if value.type not in {"J", "F"} or _is_map_coefficient(value.label):
            continue
        observation_type: Literal["intensity", "amplitude"] = (
            "intensity" if value.type == "J" else "amplitude"
        )
        for sigma in mtz.columns:
            if (
                sigma.type == "Q"
                and sigma.dataset_id == value.dataset_id
                and _is_sigma_for(value.label, sigma.label)
            ):
                pairs.append(
                    _ObservationCandidate(
                        labels=(value.label, sigma.label),
                        observation_type=observation_type,
                        rank=_observation_rank(value.label, observation_type),
                    )
                )

    by_anomalous_base: dict[
        tuple[Literal["intensity", "amplitude"], str, int],
        dict[str, _ObservationCandidate],
    ] = {}
    ordinary: list[_ObservationCandidate] = []
    for pair in pairs:
        sign = _anomalous_sign(pair.labels[0])
        if sign is None:
            ordinary.append(pair)
            continue
        key = (
            pair.observation_type,
            _normalise_label(_without_anomalous_sign(pair.labels[0])),
            pair.rank,
        )
        by_anomalous_base.setdefault(key, {})[sign] = pair
    combined = list(ordinary)
    for (observation_type, _, rank), signed in by_anomalous_base.items():
        if set(signed) == {"+", "-"}:
            combined.append(
                _ObservationCandidate(
                    labels=(*signed["+"].labels, *signed["-"].labels),
                    observation_type=observation_type,
                    rank=rank,
                )
            )
        else:
            combined.extend(signed.values())
    return tuple(
        sorted(
            combined, key=lambda item: (item.observation_type, item.rank, item.labels)
        )
    )


def _explicit_candidate(mtz: gemmi.Mtz, labels_text: str) -> _ObservationCandidate:
    labels = tuple(item.strip() for item in labels_text.split(",") if item.strip())
    if len(labels) not in {2, 4}:
        raise MtzPreflightError(
            "obs_labels must contain one value/sigma pair or an anomalous quartet"
        )
    columns = {column.label: column for column in mtz.columns}
    try:
        selected = tuple(columns[label] for label in labels)
    except KeyError as error:
        raise MtzPreflightError(
            f"explicit observation column is missing: {error.args[0]}"
        ) from error
    value_columns = selected[::2]
    sigma_columns = selected[1::2]
    if any(_is_map_coefficient(column.label) for column in value_columns):
        raise MtzPreflightError("map coefficients cannot be selected as observations")
    value_types = {column.type for column in value_columns}
    if len(value_types) != 1 or value_types.pop() not in {"J", "F"}:
        raise MtzPreflightError("observation values must all be MTZ type J or F")
    if any(column.type != "Q" for column in sigma_columns):
        raise MtzPreflightError("observation sigma columns must be MTZ type Q")
    if any(
        not _is_sigma_for(value.label, sigma.label)
        for value, sigma in zip(value_columns, sigma_columns, strict=True)
    ):
        raise MtzPreflightError("explicit observation value/sigma labels do not pair")
    observation_type: Literal["intensity", "amplitude"] = (
        "intensity" if value_columns[0].type == "J" else "amplitude"
    )
    return _ObservationCandidate(labels, observation_type, -1)


def select_observations(
    mtz: gemmi.Mtz, override: str | None
) -> tuple[_ObservationCandidate | None, tuple[str, ...], tuple[str, ...]]:
    """Select observations by explicit override and deterministic type priority."""

    candidates = _candidate_pairs(mtz)
    rendered = tuple(candidate.rendered for candidate in candidates)
    if override is not None:
        return _explicit_candidate(mtz, override), rendered, ()
    for observation_type in ("intensity", "amplitude"):
        matching = [
            candidate
            for candidate in candidates
            if candidate.observation_type == observation_type
        ]
        if not matching:
            continue
        if len(matching) == 1:
            return matching[0], rendered, ()
        best_rank = min(candidate.rank for candidate in matching)
        best = [candidate for candidate in matching if candidate.rank == best_rank]
        if len(best) == 1:
            return best[0], rendered, ("observation_selection_deterministic",)
        return None, rendered, ("ambiguous_observation_arrays",)
    return None, rendered, ("no_observed_data",)


def _assessment_status(
    text: str, *, positive: tuple[str, ...], negative: tuple[str, ...]
) -> AssessmentStatus:
    lowered = text.lower()
    negative_detected = any(re.search(pattern, lowered) for pattern in negative)
    without_negative = lowered
    for pattern in negative:
        without_negative = re.sub(pattern, "", without_negative)
    if any(re.search(pattern, without_negative) for pattern in positive):
        return AssessmentStatus.SUSPECTED
    if negative_detected:
        return AssessmentStatus.NOT_DETECTED
    return AssessmentStatus.NOT_ASSESSED


def _metric(text: str, pattern: str, *, percentage: bool = False) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        return None
    value = float(match.group(1))
    return value / 100.0 if percentage else value


def parse_xtriage_output(text: str) -> XtriageAssessment:
    """Parse stable warning concepts while retaining the complete raw log."""

    anisotropy = _assessment_status(
        text,
        positive=(r"significant anisotrop", r"anisotropy.*(?:suspect|detected)"),
        negative=(r"no significant anisotrop",),
    )
    tncs = _assessment_status(
        text,
        positive=(r"translational ncs.*(?:present|detected|suspect|significant)",),
        negative=(r"no (?:significant )?translational ncs",),
    )
    twinning = _assessment_status(
        text,
        positive=(
            r"twinning.*(?:likely|suspect|detected|significant)",
            r"possible twin law",
        ),
        negative=(r"no (?:significant )?twinning",),
    )
    symmetry = _assessment_status(
        text,
        positive=(
            r"possible higher symmetry",
            r"systematic absence.*(?:problem|violation|inconsistent)",
        ),
        negative=(
            r"no indication of higher symmetry",
            r"systematic absences.*consistent",
        ),
    )
    status_codes = {
        "xtriage_anisotropy": anisotropy,
        "xtriage_tncs": tncs,
        "xtriage_twinning": twinning,
        "xtriage_symmetry": symmetry,
    }
    warnings = tuple(
        code
        for code, status in status_codes.items()
        if status is AssessmentStatus.SUSPECTED
    )
    version_match = re.search(
        r"(?:PHENIX(?:\.xtriage)?\s+(?:version\s*)?)([0-9][A-Za-z0-9_.-]+)",
        text,
        flags=re.IGNORECASE,
    )
    completeness = _metric(
        text, r"completeness[^\n:=]*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*%", percentage=True
    )
    mean_i_over_sigma = _metric(
        text, r"mean\s+I\s*/\s*sigma\s*\(?I\)?[^\n:=]*[:=]\s*([0-9]+(?:\.[0-9]+)?)"
    )
    matthews_rows = tuple(
        XtriageMatthewsRow(
            copy_count=int(match.group(1)),
            matthews_coefficient=float(match.group(2)),
            solvent_fraction=float(match.group(3)) / 100.0,
        )
        for match in re.finditer(
            r"(?:copies|n_copies)\s*[:=]\s*([0-9]+)"
            r"[^\n]*?(?:vm|matthews coefficient)\s*[:=]\s*"
            r"([0-9]+(?:\.[0-9]+)?)"
            r"[^\n]*?solvent(?: content)?\s*[:=]\s*"
            r"([0-9]+(?:\.[0-9]+)?)\s*%",
            text,
            flags=re.IGNORECASE,
        )
    )
    version = version_match.group(1) if version_match else None
    return XtriageAssessment(
        version=version,
        completeness=completeness,
        mean_i_over_sigma=mean_i_over_sigma,
        anisotropy_status=anisotropy,
        tncs_status=tncs,
        twinning_status=twinning,
        symmetry_status=symmetry,
        matthews_rows=matthews_rows,
        warning_codes=warnings,
        summary={
            "version": version,
            "completeness": completeness,
            "mean_i_over_sigma": mean_i_over_sigma,
            "anisotropy_status": anisotropy.value,
            "tncs_status": tncs.value,
            "twinning_status": twinning.value,
            "symmetry_status": symmetry.value,
            "matthews_rows": [
                {
                    "copy_count": row.copy_count,
                    "matthews_coefficient": row.matthews_coefficient,
                    "solvent_fraction": row.solvent_fraction,
                }
                for row in matthews_rows
            ],
        },
    )


def _run_xtriage(
    *,
    phenix_manifest: Path,
    mtz_path: Path,
    observation: _ObservationCandidate,
    entry: CrystalEntry,
    log_path: Path,
    timeout_seconds: float,
) -> tuple[XtriageAssessment, tuple[str, ...]]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_model = load_contract(
        phenix_manifest, "phenix-install-manifest", progress=False
    )
    if not isinstance(manifest_model, PhenixInstallManifest):
        raise TypeError("Xtriage received an unexpected Phenix contract")
    arguments = [
        "phenix.xtriage",
        f"scaling.input.xray_data.file_name={mtz_path}",
        f"scaling.input.xray_data.obs_labels={observation.rendered}",
    ]
    if entry.space_group_override is not None:
        arguments.append(
            f"scaling.input.xray_data.space_group={entry.space_group_override}"
        )
    if entry.high_resolution_override is not None:
        arguments.append(
            f"scaling.input.xray_data.high_resolution={entry.high_resolution_override}"
        )
    if entry.low_resolution_override is not None:
        arguments.append(
            f"scaling.input.xray_data.low_resolution={entry.low_resolution_override}"
        )
    with tempfile.TemporaryDirectory(
        prefix=f".{entry.crystal_id}.xtriage-", dir=log_path.parent
    ) as temporary:
        completed = capture_from_manifest(
            phenix_manifest,
            arguments,
            working_directory=Path(temporary),
            timeout_seconds=timeout_seconds,
        )
    output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
    atomic_write_text(log_path, output)
    if completed.returncode != 0:
        raise XtriageExecutionError(
            f"phenix.xtriage failed for {entry.crystal_id} with exit status "
            f"{completed.returncode}; see {log_path}"
        )
    assessment = parse_xtriage_output(output)
    if assessment.version is not None and not (
        assessment.version == manifest_model.phenix_version
        or assessment.version.startswith(f"{manifest_model.phenix_version}-")
        or manifest_model.phenix_version.startswith(f"{assessment.version}-")
    ):
        raise XtriageExecutionError(
            "Xtriage log version does not match the verified Phenix manifest: "
            f"{assessment.version!r} != {manifest_model.phenix_version!r}"
        )
    if assessment.version is None:
        summary = dict(assessment.summary)
        summary["version"] = manifest_model.phenix_version
        assessment = replace(
            assessment,
            version=manifest_model.phenix_version,
            summary=summary,
        )
    return assessment, tuple(arguments)


def inspect_crystal(
    entry: CrystalEntry,
    *,
    manifest_path: Path,
    output_directory: Path,
    phenix_manifest: Path | None,
    skip_xtriage: bool,
    progress: bool,
    xtriage_timeout_seconds: float,
) -> MtzPreflightRecord:
    """Inspect one MTZ and optionally enrich it with isolated Xtriage output."""

    mtz_path = Path(entry.mtz).expanduser()
    if not mtz_path.is_absolute():
        mtz_path = manifest_path.parent / mtz_path
    mtz_path = mtz_path.resolve(strict=True)
    mtz_sha = sha256_file(mtz_path, progress=progress)
    try:
        mtz = gemmi.read_mtz_file(str(mtz_path))
    except (OSError, RuntimeError) as error:
        raise MtzPreflightError(f"cannot read MTZ {mtz_path}: {error}") from error
    if mtz.nreflections < 1:
        raise MtzPreflightError(f"MTZ contains no reflections: {mtz_path}")

    warnings: list[str] = []
    spacegroup = mtz.spacegroup
    if entry.space_group_override is not None:
        spacegroup = gemmi.find_spacegroup_by_name(entry.space_group_override)
        if spacegroup is None:
            raise MtzPreflightError(
                f"unknown space-group override: {entry.space_group_override}"
            )
        warnings.append("space_group_override_applied")
    if spacegroup is None:
        raise MtzPreflightError(f"MTZ has no usable space group: {mtz_path}")
    multiplicity = len(spacegroup.operations())
    if multiplicity < 1:
        raise MtzPreflightError(
            f"space group has no symmetry operations: {spacegroup.xhm()}"
        )
    if not mtz.cell.is_compatible_with_spacegroup(spacegroup):
        warnings.append("unit_cell_space_group_incompatible")

    high_resolution = entry.high_resolution_override or mtz.resolution_high()
    low_resolution = entry.low_resolution_override or mtz.resolution_low()
    if high_resolution <= 0 or low_resolution <= 0 or high_resolution > low_resolution:
        raise MtzPreflightError(
            "invalid MTZ resolution range: "
            f"high={high_resolution}, low={low_resolution}"
        )
    observation, candidates, selection_warnings = select_observations(
        mtz, entry.obs_labels
    )
    warnings.extend(selection_warnings)

    free_column = None
    if entry.free_flag_labels is not None:
        free_column = mtz.column_with_label(entry.free_flag_labels)
        if free_column is None or free_column.type != "I":
            warnings.append("invalid_free_r_override")
    else:
        free_column = mtz.rfree_column()
    free_status: Literal["present", "missing", "generated"] = (
        "present" if free_column is not None and free_column.type == "I" else "missing"
    )
    if free_status == "missing":
        warnings.append("free_r_missing")

    assessment = XtriageAssessment(
        version=None,
        completeness=None,
        mean_i_over_sigma=None,
        anisotropy_status=AssessmentStatus.NOT_ASSESSED,
        tncs_status=AssessmentStatus.NOT_ASSESSED,
        twinning_status=AssessmentStatus.NOT_ASSESSED,
        symmetry_status=AssessmentStatus.NOT_ASSESSED,
        matthews_rows=(),
        warning_codes=(),
        summary={},
    )
    xtriage_command: tuple[str, ...] = ()
    xtriage_log: Path | None = None
    fatal_codes = {
        "no_observed_data",
        "ambiguous_observation_arrays",
        "invalid_free_r_override",
        "unit_cell_space_group_incompatible",
    }
    if observation is not None and not (set(warnings) & fatal_codes):
        if skip_xtriage:
            warnings.append("xtriage_not_run")
        else:
            if phenix_manifest is None:
                raise MtzPreflightError(
                    "a verified Phenix manifest is required unless Xtriage is skipped"
                )
            xtriage_log = output_directory / "xtriage" / f"{entry.crystal_id}.log"
            assessment, xtriage_command = _run_xtriage(
                phenix_manifest=phenix_manifest,
                mtz_path=mtz_path,
                observation=observation,
                entry=entry,
                log_path=xtriage_log,
                timeout_seconds=xtriage_timeout_seconds,
            )
            warnings.extend(assessment.warning_codes)

    decision = (
        PreflightDecision.FAIL
        if observation is None or set(warnings) & fatal_codes
        else PreflightDecision.PASS_WITH_REVIEW
        if warnings
        else PreflightDecision.PASS
    )
    execution_status = (
        ExecutionStatus.FAILED_INPUT_CONTRACT
        if decision is PreflightDecision.FAIL
        else ExecutionStatus.COMPLETED_WARNING
        if decision is PreflightDecision.PASS_WITH_REVIEW
        else ExecutionStatus.COMPLETED_SUCCESS
    )
    cell_volume = mtz.cell.volume
    columns = tuple(
        MtzColumnRecord(
            label=column.label,
            type_code=column.type,
            dataset_id=column.dataset_id,
        )
        for column in mtz.columns
    )
    selected_labels = observation.rendered if observation is not None else None
    identity = {
        "crystal_id": entry.crystal_id,
        "mtz_sha256": mtz_sha,
        "selected_observation_labels": selected_labels,
        "space_group": spacegroup.xhm(),
        "unit_cell": mtz.cell.parameters,
        "resolution_high_a": high_resolution,
        "resolution_low_a": low_resolution,
        "warnings": sorted(set(warnings)),
        "xtriage_version": assessment.version,
    }
    record = MtzPreflightRecord(
        schema_version="1.0",
        preflight_id=content_id("preflight_", identity),
        crystal_id=entry.crystal_id,
        mtz_sha256=mtz_sha,
        selected_observation_labels=selected_labels,
        selected_observation_type=(
            observation.observation_type if observation is not None else None
        ),
        free_flag_labels=free_column.label if free_column is not None else None,
        free_flag_status=free_status,
        unit_cell=cast(
            tuple[float, float, float, float, float, float], mtz.cell.parameters
        ),
        space_group=spacegroup.xhm(),
        general_position_multiplicity=multiplicity,
        cell_volume_a3=cell_volume,
        asu_volume_a3=cell_volume / multiplicity,
        resolution_low_a=low_resolution,
        resolution_high_a=high_resolution,
        reflection_count=mtz.nreflections,
        available_columns=columns,
        observation_candidates=candidates,
        completeness=assessment.completeness,
        mean_i_over_sigma=assessment.mean_i_over_sigma,
        anisotropy_status=assessment.anisotropy_status,
        tncs_status=assessment.tncs_status,
        twinning_status=assessment.twinning_status,
        symmetry_status=assessment.symmetry_status,
        xtriage_version=assessment.version,
        xtriage_command=xtriage_command,
        xtriage_log=(
            xtriage_log.relative_to(output_directory).as_posix()
            if xtriage_log is not None
            else None
        ),
        xtriage_summary=assessment.summary,
        decision=decision,
        warning_codes=tuple(sorted(set(warnings))),
        execution_status=execution_status,
    )
    _LOGGER.info(
        "MTZ preflight complete",
        extra={
            "crystal_id": entry.crystal_id,
            "decision": record.decision,
            "observations": selected_labels,
            "space_group": record.space_group,
            "resolution_high_a": record.resolution_high_a,
            "warning_codes": record.warning_codes,
        },
    )
    return record


def _write_preflight_outputs(
    output_directory: Path, records: tuple[MtzPreflightRecord, ...]
) -> tuple[Path, Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_directory / "mtz_preflight.jsonl"
    atomic_write_text(
        jsonl_path, "\n".join(canonical_json_text(record) for record in records) + "\n"
    )
    tsv_path = output_directory / "mtz_preflight.tsv"
    stream = io.StringIO(newline="")
    columns = (
        "preflight_id",
        "crystal_id",
        "decision",
        "selected_observation_labels",
        "selected_observation_type",
        "free_flag_labels",
        "free_flag_status",
        "space_group",
        "general_position_multiplicity",
        "cell_volume_a3",
        "asu_volume_a3",
        "resolution_low_a",
        "resolution_high_a",
        "reflection_count",
        "warning_codes",
        "execution_status",
    )
    writer = csv.DictWriter(
        stream, fieldnames=columns, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    for record in records:
        document = record.model_dump(mode="json")
        document["warning_codes"] = ";".join(record.warning_codes)
        writer.writerow({column: document.get(column, "") for column in columns})
    atomic_write_text(tsv_path, stream.getvalue())
    report_path = output_directory / "preflight_report.md"
    lines = ["# MTZ preflight report", ""]
    for record in records:
        unit_cell = ", ".join(f"{value:.3f}" for value in record.unit_cell)
        resolution = f"{record.resolution_low_a:.3f}-{record.resolution_high_a:.3f} A"
        lines.extend(
            (
                f"## {record.crystal_id}",
                "",
                f"- Decision: `{record.decision}`",
                f"- Observations: `{record.selected_observation_labels or 'none'}`",
                f"- Space group: `{record.space_group}`",
                f"- Unit cell: `{unit_cell}`",
                f"- Resolution: `{resolution}`",
                f"- ASU volume: `{record.asu_volume_a3:.3f} A^3`",
                f"- Free-R: `{record.free_flag_status}`",
                f"- Warnings: `{'; '.join(record.warning_codes) or 'none'}`",
                "",
            )
        )
    atomic_write_text(report_path, "\n".join(lines))
    return jsonl_path, tsv_path, report_path


def preflight_crystals(request: PreflightRequest) -> PreflightResult:
    """Inspect every crystal, publish reports, and fail after recording bad inputs."""

    manifest_path = request.crystal_manifest.resolve(strict=True)
    model = load_contract(manifest_path, "crystal-manifest", progress=request.progress)
    if not isinstance(model, CrystalManifest):
        raise TypeError("preflight received an unexpected crystal contract")
    output = request.output_directory.resolve()
    records = tuple(
        inspect_crystal(
            entry,
            manifest_path=manifest_path,
            output_directory=output,
            phenix_manifest=(
                request.phenix_manifest.resolve(strict=True)
                if request.phenix_manifest is not None
                else None
            ),
            skip_xtriage=request.skip_xtriage,
            progress=request.progress,
            xtriage_timeout_seconds=request.xtriage_timeout_seconds,
        )
        for entry in tqdm(
            model.crystals,
            desc="Preflight MTZ files",
            unit="crystal",
            disable=not request.progress,
        )
    )
    jsonl_path, tsv_path, report_path = _write_preflight_outputs(output, records)
    failed = [
        record.crystal_id
        for record in records
        if record.decision is PreflightDecision.FAIL
    ]
    if failed:
        raise MtzPreflightError(
            "MTZ preflight failed for crystal(s): " + ", ".join(failed)
        )
    return PreflightResult(records, jsonl_path, tsv_path, report_path)
