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
_FLOAT_PATTERN = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
_OBSERVATION_TYPES: dict[str, Literal["intensity", "amplitude"]] = {
    "J": "intensity",
    "K": "intensity",
    "F": "amplitude",
    "G": "amplitude",
}
_SIGMA_TYPES = {"J": "Q", "K": "M", "F": "Q", "G": "L"}


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
    xtriage_timeout_seconds: float | None = 3600.0


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
    return sigma == f"SIG{value}" and _anomalous_sign(value_label) == _anomalous_sign(
        sigma_label
    )


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
        if value.type not in _OBSERVATION_TYPES or _is_map_coefficient(value.label):
            continue
        observation_type = _OBSERVATION_TYPES[value.type]
        for sigma in mtz.columns:
            if (
                sigma.type == _SIGMA_TYPES[value.type]
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
    if len(value_types) != 1 or not value_types.issubset(_OBSERVATION_TYPES):
        raise MtzPreflightError(
            "observation values must all use one MTZ observation type"
        )
    value_type = value_columns[0].type
    if any(column.type != _SIGMA_TYPES[value_type] for column in sigma_columns):
        raise MtzPreflightError(
            "observation sigma columns do not match the MTZ observation type"
        )
    if any(
        not _is_sigma_for(value.label, sigma.label)
        for value, sigma in zip(value_columns, sigma_columns, strict=True)
    ):
        raise MtzPreflightError("explicit observation value/sigma labels do not pair")
    observation_type = _OBSERVATION_TYPES[value_type]
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
    flags = re.IGNORECASE | re.MULTILINE
    negative_detected = any(
        re.search(pattern, lowered, flags=flags) for pattern in negative
    )
    without_negative = lowered
    for pattern in negative:
        without_negative = re.sub(pattern, "", without_negative, flags=flags)
    if any(re.search(pattern, without_negative, flags=flags) for pattern in positive):
        return AssessmentStatus.SUSPECTED
    if negative_detected:
        return AssessmentStatus.NOT_DETECTED
    return AssessmentStatus.NOT_ASSESSED


def _metric(text: str, pattern: str, *, percentage: bool = False) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if match is None:
        return None
    value = float(match.group(1))
    return value / 100.0 if percentage else value


def _spanning_metric(text: str, pattern: str) -> float | None:
    match = re.search(
        pattern,
        text,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return float(match.group(1)) if match is not None else None


def _final_verdict(text: str) -> str:
    """Return only Xtriage's final-verdict body, or an empty string."""

    match = re.search(
        r"^\s*-+\s*Final verdict\s*-+\s*$"
        r"(?P<body>.*?)"
        r"(?=^\s*-+\s*Statistics independent|\Z)",
        text,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return match.group("body") if match is not None else ""


def _point_group_assessment(
    text: str, verdict: str
) -> tuple[AssessmentStatus, str | None, str | None, bool | None, bool | None]:
    """Compare Xtriage's input and likely point groups without conflating settings."""

    dictated_match = re.search(
        r"^The point group of data as dictated by the space group is\s+(.+?)\s*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    likely_match = re.search(
        r"^The likely point group of the data is:\s+(.+?)\s*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    dictated = dictated_match.group(1).strip() if dictated_match else None
    likely = likely_match.group(1).strip() if likely_match else None
    absence_match = re.search(
        r"^.*\(input space group\):\s+no "
        r"(?:systematic )?absences (?:found|possible)\s*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    input_absences_consistent: bool | None = True if absence_match is not None else None

    equivalent: bool | None = None
    if dictated is not None and likely is not None:
        # Xtriage may append a change-of-basis operator, for example
        # ``C 1 2 1 (x+y,z,2*x)``.  Compare crystallographic point-group types,
        # not literal setting strings, so an equivalent centred setting is not
        # reported as higher symmetry.
        dictated_symbol = dictated.split(" (", maxsplit=1)[0]
        likely_symbol = likely.split(" (", maxsplit=1)[0]
        dictated_group = gemmi.find_spacegroup_by_name(dictated_symbol)
        likely_group = gemmi.find_spacegroup_by_name(likely_symbol)
        if dictated_group is not None and likely_group is not None:
            equivalent = (
                dictated_group.point_group_hm() == likely_group.point_group_hm()
            )

    if re.search(
        r"symmetry (?:of the lattice and intensity|of the intensities).*"
        r"(?:input(?: input)?|assumed) space group is too low",
        verdict,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        return (
            AssessmentStatus.SUSPECTED,
            dictated,
            likely,
            equivalent,
            input_absences_consistent,
        )
    if equivalent is None:
        return (
            AssessmentStatus.NOT_ASSESSED,
            dictated,
            likely,
            None,
            input_absences_consistent,
        )

    if not equivalent:
        status = AssessmentStatus.SUSPECTED
    elif input_absences_consistent is True:
        status = AssessmentStatus.NOT_DETECTED
    else:
        status = AssessmentStatus.NOT_ASSESSED
    return status, dictated, likely, equivalent, input_absences_consistent


def parse_xtriage_output(text: str) -> XtriageAssessment:
    """Parse stable warning concepts while retaining the complete raw log."""

    verdict = _final_verdict(text)
    anisotropy = _assessment_status(
        text,
        positive=(
            r"^\s*The data show severe anisotropy\.\s*$",
            r"^\s*The data are moderately anisotropic\.\s*$",
        ),
        negative=(r"^\s*The data are not significantly anisotropic\.\s*$",),
    )
    tncs = _assessment_status(
        verdict,
        positive=(
            r"indicating pseudo[- ]?translational\s+symmetry\.",
            r"the detected translational ncs",
        ),
        negative=(
            r"no significant pseudo[- ]?translation is detected\.",
            r"no (?:significant )?translational "
            r"(?:ncs|pseudo[- ]?symmetry) (?:is )?(?:detected|suspected)\.",
        ),
    )
    twinning = _assessment_status(
        verdict,
        positive=(
            r"twinning could\s+be the reason for the departure of the "
            r"intensity statistics from normality",
            r"as twinning is however suspected",
        ),
        negative=(
            r"no twinning is suspected\.",
            r"no significant twinning (?:is )?detected\.",
        ),
    )
    (
        symmetry,
        dictated_point_group,
        likely_point_group,
        equivalent,
        input_absences_consistent,
    ) = _point_group_assessment(text, verdict)
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
        text,
        r"^\s*Completeness in resolution range:\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*$",
    )
    if completeness is None:
        completeness = _metric(
            text,
            r"^\s*Completeness(?: overall)?:\s*"
            r"([0-9]+(?:\.[0-9]+)?)\s*%\s*$",
            percentage=True,
        )
    mean_i_over_sigma = _metric(
        text,
        r"^\s*Mean\s+I\s*/\s*sigma\s*\(?I\)?\s*:\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*$",
    )
    if mean_i_over_sigma is None:
        mean_i_over_sigma = _metric(
            text,
            r"^\s*Overall\s+<I\s*/\s*sigma>\s+for\s+this\s+dataset\s+is\s+"
            r"([0-9]+(?:\.[0-9]+)?)\s*$",
        )
    xtriage_resolution_match = re.search(
        r"^\s*Resolution:\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*-\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    xtriage_resolution_low_a = (
        float(xtriage_resolution_match.group(1))
        if xtriage_resolution_match is not None
        else None
    )
    xtriage_resolution_high_a = (
        float(xtriage_resolution_match.group(2))
        if xtriage_resolution_match is not None
        else None
    )
    xtriage_reflection_count_match = re.search(
        r"^\s*Number of reflections:\s*([0-9]+)\s*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    xtriage_reflection_count = (
        int(xtriage_reflection_count_match.group(1))
        if xtriage_reflection_count_match is not None
        else None
    )
    patterson_peak_fraction = _metric(
        text,
        rf"^\s*Height relative to origin\s*:\s*({_FLOAT_PATTERN})\s*%\s*$",
        percentage=True,
    )
    if patterson_peak_fraction is None:
        patterson_peak_fraction = _metric(
            text,
            r"^\s*The largest off-origin peak in the Patterson function is\s+"
            r"([0-9]+(?:\.[0-9]+)?)% of the\s*$",
            percentage=True,
        )
    patterson_peak_p_value = _metric(
        text,
        rf"^\s*p_value\(height\)\s*:\s*({_FLOAT_PATTERN})\s*$",
    )
    l_test_multivariate_z = _metric(
        text,
        r"^\s*Multivariate Z score L-test:\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*$",
    )
    anisotropy_noise_z_least_affected = _spanning_metric(
        text,
        r"The quarter of Intensities \*least\* affected by the anisotropy "
        r"correction show.*?Fraction of I/sigI > 3\s*:\s*\S+\s*"
        r"\(\s*Z\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*\)",
    )
    anisotropy_noise_z_most_affected = _spanning_metric(
        text,
        r"The quarter of Intensities \*most\* affected by the anisotropy "
        r"correction show.*?Fraction of I/sigI > 3\s*:\s*\S+\s*"
        r"\(\s*Z\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*\)",
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
    direction_dependent_resolution = bool(
        re.search(
            r"resolution limit appears to be direction-dependent",
            text,
            flags=re.IGNORECASE,
        )
    )
    extra_warnings: list[str] = []
    if direction_dependent_resolution:
        extra_warnings.append("xtriage_direction_dependent_resolution")
    if completeness is not None and completeness < 0.9:
        extra_warnings.append("xtriage_completeness_below_90_percent")
    if patterson_peak_p_value is not None and patterson_peak_p_value < 0.05:
        extra_warnings.append("xtriage_patterson_peak_review")
    warnings = (*warnings, *extra_warnings)
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
            "xtriage_resolution_low_a": xtriage_resolution_low_a,
            "xtriage_resolution_high_a": xtriage_resolution_high_a,
            "xtriage_reflection_count": xtriage_reflection_count,
            "patterson_off_origin_peak_fraction": patterson_peak_fraction,
            "patterson_peak_p_value": patterson_peak_p_value,
            "l_test_multivariate_z": l_test_multivariate_z,
            "anisotropy_noise_z_least_affected": (anisotropy_noise_z_least_affected),
            "anisotropy_noise_z_most_affected": (anisotropy_noise_z_most_affected),
            "anisotropy_status": anisotropy.value,
            "tncs_status": tncs.value,
            "twinning_status": twinning.value,
            "symmetry_status": symmetry.value,
            "dictated_point_group": dictated_point_group,
            "likely_point_group": likely_point_group,
            "point_group_equivalent": equivalent,
            "input_space_group_absences_consistent": input_absences_consistent,
            "direction_dependent_resolution": direction_dependent_resolution,
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
    timeout_seconds: float | None,
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
    xtriage_timeout_seconds: float | None,
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
        mtz_resolution = (
            f"{record.resolution_low_a:.3f}-{record.resolution_high_a:.3f} A"
        )
        completeness = (
            f"{record.completeness * 100:.2f}%"
            if record.completeness is not None
            else "not available"
        )
        mean_i_over_sigma = (
            f"{record.mean_i_over_sigma:.3f}"
            if record.mean_i_over_sigma is not None
            else "not available"
        )
        summary_numbers: dict[str, float | None] = {}
        for key in (
            "xtriage_resolution_low_a",
            "xtriage_resolution_high_a",
            "patterson_off_origin_peak_fraction",
            "patterson_peak_p_value",
            "l_test_multivariate_z",
            "anisotropy_noise_z_least_affected",
            "anisotropy_noise_z_most_affected",
        ):
            value = record.xtriage_summary.get(key)
            summary_numbers[key] = (
                float(value)
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else None
            )
        patterson_peak = summary_numbers["patterson_off_origin_peak_fraction"]
        patterson_p_value = summary_numbers["patterson_peak_p_value"]
        l_test_z = summary_numbers["l_test_multivariate_z"]
        least_anisotropy_z = summary_numbers["anisotropy_noise_z_least_affected"]
        most_anisotropy_z = summary_numbers["anisotropy_noise_z_most_affected"]
        xtriage_resolution_low = summary_numbers["xtriage_resolution_low_a"]
        xtriage_resolution_high = summary_numbers["xtriage_resolution_high_a"]
        xtriage_resolution = (
            f"{xtriage_resolution_low:.3f}-{xtriage_resolution_high:.3f} A"
            if xtriage_resolution_low is not None
            and xtriage_resolution_high is not None
            else "not available"
        )
        xtriage_reflection_count = record.xtriage_summary.get(
            "xtriage_reflection_count"
        )
        xtriage_reflection_count_display = (
            str(xtriage_reflection_count)
            if isinstance(xtriage_reflection_count, int)
            and not isinstance(xtriage_reflection_count, bool)
            else "not available"
        )
        patterson_display = (
            f"{patterson_peak * 100:.2f}%"
            if patterson_peak is not None
            else "not available"
        )
        l_test_display = f"{l_test_z:.3f}" if l_test_z is not None else "not available"
        patterson_p_value_display = (
            f"{patterson_p_value:.3e}"
            if patterson_p_value is not None
            else "not available"
        )
        least_anisotropy_display = (
            f"{least_anisotropy_z:.2f}"
            if least_anisotropy_z is not None
            else "not available"
        )
        most_anisotropy_display = (
            f"{most_anisotropy_z:.2f}"
            if most_anisotropy_z is not None
            else "not available"
        )
        lines.extend(
            (
                f"## {record.crystal_id}",
                "",
                f"- Decision: `{record.decision}`",
                f"- Observations: `{record.selected_observation_labels or 'none'}`",
                f"- Space group: `{record.space_group}`",
                f"- Unit cell: `{unit_cell}`",
                f"- MTZ row resolution: `{mtz_resolution}`",
                f"- Xtriage selected-data resolution: `{xtriage_resolution}`",
                f"- MTZ row count: `{record.reflection_count}`",
                "- Xtriage selected reflection count: "
                f"`{xtriage_reflection_count_display}`",
                f"- ASU volume: `{record.asu_volume_a3:.3f} A^3`",
                f"- Free-R: `{record.free_flag_status}`",
                f"- Xtriage version: `{record.xtriage_version or 'not run'}`",
                f"- Completeness: `{completeness}`",
                f"- Overall mean I/sigma: `{mean_i_over_sigma}`",
                "- Xtriage assessments: "
                f"`anisotropy={record.anisotropy_status}; "
                f"tncs={record.tncs_status}; "
                f"twinning={record.twinning_status}; "
                f"symmetry={record.symmetry_status}`",
                f"- Patterson off-origin peak: `{patterson_display}`",
                f"- Patterson peak p-value: `{patterson_p_value_display}`",
                f"- Multivariate L-test Z: `{l_test_display}`",
                "- Anisotropy-noise Z (least/most affected quarters): "
                f"`{least_anisotropy_display} / {most_anisotropy_display}`",
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
