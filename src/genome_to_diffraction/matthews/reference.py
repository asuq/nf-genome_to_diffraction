"""Qualify exact-mass Matthews calculations against local Phenix.

The selected crystal, preflight record, and exact sequence group are inputs.
The module runs the fixed ``mmtbx.matthews MTZ n_residues=N`` reference command
from a verified Phenix manifest, then writes its preserved log plus JSON and
Markdown comparison reports. External-command failures and malformed reference
tables fail loudly. A passing report demonstrates method compatibility only; it
does not establish molecular identity, ASU composition, or a positive control.

The cache key is the MTZ checksum, sequence digest and mass, configuration,
Phenix manifest/environment checksum, executable checksum, and comparison
tolerances. Unit tests cover parsing, comparisons, unsafe auxiliary executable
resolution, command failure, and the CLI. A real local Phenix run is retained in
the ignored M0 qualification dossier.
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.matthews.enumerate import enumerate_group
from genome_to_diffraction.phenix.runtime import (
    MatthewsReferenceExecution,
    capture_matthews_reference_from_manifest,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import (
    CrystalEntry,
    CrystalManifest,
    PipelineConfig,
)
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MtzPreflightRecord,
    PhysicalStatus,
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.status import (
    InputContractError,
    ResultParseError,
    ToolExecutionError,
)
from genome_to_diffraction.time import utc_now_iso

_LOGGER = logging.getLogger("genome_to_diffraction.matthews.reference")
_FLOAT = r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
_TABLE_ROW = re.compile(
    rf"^\s*\|\s*([0-9]+)\s*\|\s*({_FLOAT})\s*\|\s*({_FLOAT})\s*\|"
    rf"\s*({_FLOAT})\s*\|\s*$"
)
_BEST_GUESS = re.compile(
    r"^\s*Best\s+guess\s*:\s*([0-9]+)\s+cop(?:y|ies)\s+in\s+the\s+ASU\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
MAXIMUM_MASS_MODEL_RELATIVE_DIFFERENCE = 0.05


class MatthewsReferenceInputError(InputContractError):
    """Selected reference inputs are missing, inconsistent, or ambiguous."""


class MatthewsReferenceExecutionError(ToolExecutionError):
    """The fixed Phenix Matthews reference command failed."""


class MatthewsReferenceParseError(ResultParseError):
    """The Phenix Matthews output lacked a trustworthy result table."""


@dataclass(frozen=True)
class PhenixMatthewsRow:
    """One row from the Phenix Matthews probability table."""

    copy_count: int
    solvent_fraction: float
    matthews_coefficient: float
    probability: float


@dataclass(frozen=True)
class ParsedPhenixMatthews:
    """Parsed reference rows and Phenix's explicitly reported best copy count."""

    rows: tuple[PhenixMatthewsRow, ...]
    best_guess_copy_count: int


@dataclass(frozen=True)
class MatthewsReferenceRequest:
    """Inputs for one fixed method-reference qualification."""

    crystal_manifest: Path
    pipeline_config: Path
    preflight_jsonl: Path
    sequence_groups_jsonl: Path
    source_records_jsonl: Path
    phenix_manifest: Path
    crystal_id: str
    sequence_group_id: str
    output_directory: Path
    timeout_seconds: float = 600.0
    progress: bool = True


@dataclass(frozen=True)
class MatthewsReferenceResult:
    """Qualification status and stable local report paths."""

    status: Literal["passed", "failed"]
    comparison_id: str
    json_path: Path
    markdown_path: Path
    phenix_log_path: Path


def parse_phenix_matthews_output(text: str) -> ParsedPhenixMatthews:
    """Parse the documented four-column Phenix Matthews terminal table."""

    if (
        re.search(
            r"\|\s*Copies\s*\|\s*Solvent content\s*\|\s*Matthews coeff\.\s*\|"
            r"\s*P\(solvent content\)\s*\|",
            text,
            flags=re.IGNORECASE,
        )
        is None
    ):
        raise MatthewsReferenceParseError("Phenix Matthews table header is missing")
    rows: list[PhenixMatthewsRow] = []
    for line in text.splitlines():
        match = _TABLE_ROW.fullmatch(line)
        if match is None:
            continue
        row = PhenixMatthewsRow(
            copy_count=int(match.group(1)),
            solvent_fraction=float(match.group(2)),
            matthews_coefficient=float(match.group(3)),
            probability=float(match.group(4)),
        )
        if row.copy_count < 1:
            raise MatthewsReferenceParseError("Phenix copy count must be positive")
        if not 0 <= row.solvent_fraction <= 1:
            raise MatthewsReferenceParseError(
                "Phenix solvent fraction must be between zero and one"
            )
        if row.matthews_coefficient <= 0:
            raise MatthewsReferenceParseError(
                "Phenix Matthews coefficient must be positive"
            )
        if not 0 <= row.probability <= 1:
            raise MatthewsReferenceParseError(
                "Phenix solvent-content probability must be between zero and one"
            )
        rows.append(row)
    if not rows:
        raise MatthewsReferenceParseError(
            "no rows found in the Phenix Matthews probability table"
        )
    copies = [row.copy_count for row in rows]
    if len(copies) != len(set(copies)):
        raise MatthewsReferenceParseError(
            "duplicate copy counts in the Phenix Matthews probability table"
        )
    best_match = _BEST_GUESS.search(text)
    if best_match is None:
        raise MatthewsReferenceParseError("Phenix Matthews best guess is missing")
    best_guess = int(best_match.group(1))
    if best_guess not in set(copies):
        raise MatthewsReferenceParseError(
            "Phenix Matthews best guess is absent from its probability table"
        )
    expected_best = min(rows, key=lambda row: (-row.probability, row.copy_count))
    if best_guess != expected_best.copy_count:
        raise MatthewsReferenceParseError(
            "Phenix Matthews best guess disagrees with its probability ordering"
        )
    return ParsedPhenixMatthews(tuple(rows), best_guess)


def _load_selected_jsonl(
    path: Path,
    *,
    model: type[MtzPreflightRecord] | type[SequenceGroupRecord],
    identifier_name: Literal["crystal_id", "sequence_group_id"],
    identifier: str,
) -> MtzPreflightRecord | SequenceGroupRecord:
    selected: list[MtzPreflightRecord | SequenceGroupRecord] = []
    try:
        with path.resolve(strict=True).open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = model.model_validate_json(line)
                except (ValidationError, ValueError) as error:
                    raise MatthewsReferenceInputError(
                        f"{path}:{line_number}: invalid record: {error}"
                    ) from error
                if getattr(record, identifier_name) == identifier:
                    selected.append(record)
    except OSError as error:
        raise MatthewsReferenceInputError(f"cannot read {path}: {error}") from error
    if len(selected) != 1:
        raise MatthewsReferenceInputError(
            f"expected exactly one {identifier_name}={identifier!r} in {path}; "
            f"found {len(selected)}"
        )
    return selected[0]


def _selected_crystal(manifest: CrystalManifest, crystal_id: str) -> CrystalEntry:
    selected = [entry for entry in manifest.crystals if entry.crystal_id == crystal_id]
    if len(selected) != 1:
        raise MatthewsReferenceInputError(
            f"expected exactly one crystal_id={crystal_id!r}; found {len(selected)}"
        )
    return selected[0]


def _validate_catalogue_membership(
    path: Path,
    *,
    sequence_group_id: str,
    catalogue_id: str,
) -> tuple[str, ...]:
    matching_source_ids: list[str] = []
    try:
        with path.resolve(strict=True).open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    source = SourceProteinRecord.model_validate_json(line)
                except (ValidationError, ValueError) as error:
                    raise MatthewsReferenceInputError(
                        f"{path}:{line_number}: invalid source record: {error}"
                    ) from error
                if (
                    source.sequence_group_id == sequence_group_id
                    and source.catalogue_id == catalogue_id
                ):
                    matching_source_ids.append(source.source_record_id)
    except OSError as error:
        raise MatthewsReferenceInputError(f"cannot read {path}: {error}") from error
    if not matching_source_ids:
        raise MatthewsReferenceInputError(
            f"sequence group {sequence_group_id!r} is not linked to catalogue "
            f"{catalogue_id!r} by {path}"
        )
    return tuple(sorted(matching_source_ids))


def _resolve_manifest_path(path_text: str, manifest_path: Path) -> Path:
    candidate = Path(path_text)
    if not candidate.is_absolute():
        candidate = manifest_path.resolve(strict=True).parent / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise MatthewsReferenceInputError(
            f"cannot resolve crystal MTZ {candidate}: {error}"
        ) from error
    if not resolved.is_file():
        raise MatthewsReferenceInputError(f"crystal MTZ is not a file: {resolved}")
    return resolved


def _reference_order(rows: tuple[PhenixMatthewsRow, ...]) -> tuple[int, ...]:
    return tuple(
        row.copy_count
        for row in sorted(rows, key=lambda row: (-row.probability, row.copy_count))
    )


def _pipeline_order(rows: tuple[MatthewsHypothesis, ...]) -> tuple[int, ...]:
    return tuple(
        row.copy_count
        for row in sorted(rows, key=lambda row: row.rank_within_candidate)
    )


def _comparison_document(
    *,
    crystal: CrystalEntry,
    preflight: MtzPreflightRecord,
    group: SequenceGroupRecord,
    matching_source_ids: tuple[str, ...],
    config: PipelineConfig,
    pipeline_rows: tuple[MatthewsHypothesis, ...],
    parsed: ParsedPhenixMatthews,
    execution: MatthewsReferenceExecution,
    mtz_path: Path,
    mtz_sha256: str,
    manifest_sha256: str,
) -> dict[str, object]:
    if group.molecular_mass_da is None:
        raise MatthewsReferenceInputError(
            "reference qualification requires one exact sequence-derived mass"
        )
    minimum = config.matthews.min_copy_count
    maximum = config.matthews.max_copy_count
    reference_rows = tuple(
        row for row in parsed.rows if minimum <= row.copy_count <= maximum
    )
    if not reference_rows:
        raise MatthewsReferenceInputError(
            "Phenix emitted no copy counts inside the configured pipeline range"
        )
    pipeline_by_copy = {row.copy_count: row for row in pipeline_rows}
    matched_pipeline = tuple(pipeline_by_copy[row.copy_count] for row in reference_rows)
    comparisons: list[dict[str, object]] = []
    mass_model_compatible = True
    for reference, pipeline in zip(reference_rows, matched_pipeline, strict=True):
        if pipeline.matthews_coefficient is None or pipeline.solvent_fraction is None:
            raise MatthewsReferenceInputError(
                "reference qualification requires exact pipeline Matthews metrics"
            )
        implied_mass = preflight.asu_volume_a3 / (
            reference.matthews_coefficient * reference.copy_count
        )
        relative_mass_difference = (
            abs(group.molecular_mass_da - implied_mass) / implied_mass
        )
        within_bound = (
            relative_mass_difference <= MAXIMUM_MASS_MODEL_RELATIVE_DIFFERENCE
        )
        mass_model_compatible = mass_model_compatible and within_bound
        comparisons.append(
            {
                "copy_count": reference.copy_count,
                "phenix_probability": reference.probability,
                "phenix_matthews_coefficient": reference.matthews_coefficient,
                "phenix_solvent_fraction": reference.solvent_fraction,
                "pipeline_matthews_coefficient": pipeline.matthews_coefficient,
                "pipeline_solvent_fraction": pipeline.solvent_fraction,
                "matthews_absolute_difference": abs(
                    pipeline.matthews_coefficient - reference.matthews_coefficient
                ),
                "solvent_absolute_difference": abs(
                    pipeline.solvent_fraction - reference.solvent_fraction
                ),
                "phenix_implied_monomer_mass_da": implied_mass,
                "sequence_exact_monomer_mass_da": group.molecular_mass_da,
                "mass_model_relative_difference": relative_mass_difference,
                "within_mass_model_compatibility_bound": within_bound,
            }
        )

    reference_copy_set = sorted(row.copy_count for row in reference_rows)
    pipeline_plausible_set = sorted(
        row.copy_count
        for row in pipeline_rows
        if row.physical_status is not PhysicalStatus.IMPOSSIBLE
    )
    copy_sets_match = reference_copy_set == pipeline_plausible_set
    reference_order = _reference_order(reference_rows)
    pipeline_order = _pipeline_order(matched_pipeline)
    ordering_matches = reference_order == pipeline_order
    status: Literal["passed", "failed"] = (
        "passed"
        if copy_sets_match and ordering_matches and mass_model_compatible
        else "failed"
    )
    identity = {
        "crystal_id": crystal.crystal_id,
        "mtz_sha256": mtz_sha256,
        "sequence_group_id": group.sequence_group_id,
        "sequence_sha256": group.sha256,
        "sequence_mass_da": group.molecular_mass_da,
        "preflight_id": preflight.preflight_id,
        "asu_volume_a3": preflight.asu_volume_a3,
        "catalogue_id": crystal.catalogue_id,
        "matching_source_ids": matching_source_ids,
        "pipeline_config": config.model_dump(mode="json"),
        "phenix_manifest_sha256": manifest_sha256,
        "phenix_executable_sha256": execution.executable_sha256,
        "maximum_mass_model_relative_difference": (
            MAXIMUM_MASS_MODEL_RELATIVE_DIFFERENCE
        ),
    }
    return {
        "schema_version": "1.0-local-qualification",
        "comparison_id": content_id("mref_", identity),
        "status": status,
        "scope": "method_reference_only",
        "scientific_interpretation": "identity_and_true_copy_count_unknown",
        "positive_control_status": "not_established",
        "generated_at": utc_now_iso(),
        "crystal_id": crystal.crystal_id,
        "sequence_group_id": group.sequence_group_id,
        "selection_note": (
            "The selected sequence is a deterministic method probe and is not "
            "asserted to be the crystallised protein."
        ),
        "inputs": {
            "mtz_path": str(mtz_path),
            "mtz_sha256": mtz_sha256,
            "preflight_id": preflight.preflight_id,
            "asu_volume_a3": preflight.asu_volume_a3,
            "general_position_multiplicity": preflight.general_position_multiplicity,
            "sequence_sha256": group.sha256,
            "sequence_length_aa": group.length_aa,
            "sequence_exact_mass_da": group.molecular_mass_da,
            "sequence_mass_method": group.mass_method,
            "catalogue_id": crystal.catalogue_id,
            "matching_source_ids": list(matching_source_ids),
        },
        "reference": {
            "tool": "mmtbx.matthews",
            "phenix_version": execution.phenix_version,
            "executable_path": str(execution.executable),
            "executable_sha256": execution.executable_sha256,
            "phenix_manifest_sha256": manifest_sha256,
            "mass_input_model": "n_residues_average_residue_mass",
            "best_guess_copy_count": parsed.best_guess_copy_count,
            "configured_copy_range": [minimum, maximum],
        },
        "comparison_policy": {
            "pipeline_mass_model": "exact_sequence_composition",
            "maximum_mass_model_relative_difference": (
                MAXIMUM_MASS_MODEL_RELATIVE_DIFFERENCE
            ),
            "bound_interpretation": (
                "engineering compatibility bound, not a fitted probability or "
                "biological acceptance threshold"
            ),
            "plausible_pipeline_statuses": ["plausible", "review"],
        },
        "comparisons": comparisons,
        "reference_plausible_copy_counts": reference_copy_set,
        "pipeline_plausible_copy_counts": pipeline_plausible_set,
        "reference_order": list(reference_order),
        "pipeline_order": list(pipeline_order),
        "checks": {
            "plausible_copy_sets_match": copy_sets_match,
            "probability_prior_order_matches": ordering_matches,
            "mass_models_within_compatibility_bound": mass_model_compatible,
        },
        "limitations": [
            (
                "Phenix n_residues uses a residue-count mass model; the pipeline "
                "uses exact sequence composition."
            ),
            "Printed Phenix coefficients and solvent fractions are rounded.",
            (
                "No crystallised catalogue identity or ASU copy-number ground "
                "truth was used."
            ),
            "This result cannot close the M0 positive-control gate.",
        ],
    }


def _markdown(document: dict[str, object]) -> str:
    checks = document["checks"]
    assert isinstance(checks, dict)
    inputs = document["inputs"]
    assert isinstance(inputs, dict)
    reference = document["reference"]
    assert isinstance(reference, dict)
    comparisons = document["comparisons"]
    assert isinstance(comparisons, list)
    lines = [
        "# Matthews method-reference qualification",
        "",
        f"- Status: `{document['status']}`",
        f"- Comparison ID: `{document['comparison_id']}`",
        f"- Crystal: `{document['crystal_id']}`",
        f"- Sequence group: `{document['sequence_group_id']}`",
        f"- ASU volume: `{inputs['asu_volume_a3']}` Å³",
        f"- Phenix: `{reference['phenix_version']}` (`mmtbx.matthews`)",
        (
            "- Interpretation: method compatibility only; identity and true copy "
            "count remain unknown."
        ),
        "",
        "## Checks",
        "",
        f"- Plausible copy sets match: `{checks['plausible_copy_sets_match']}`",
        (
            "- Probability/prior order matches: "
            f"`{checks['probability_prior_order_matches']}`"
        ),
        (
            "- Mass-model difference is within the disclosed bound: "
            f"`{checks['mass_models_within_compatibility_bound']}`"
        ),
        "",
        "## Per-copy comparison",
        "",
        (
            "| Copies | Phenix VM | Pipeline VM | Phenix solvent | Pipeline "
            "solvent | Relative mass-model difference |"
        ),
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for raw in comparisons:
        assert isinstance(raw, dict)
        lines.append(
            "| {copy_count} | {phenix_matthews_coefficient:.4f} | "
            "{pipeline_matthews_coefficient:.4f} | {phenix_solvent_fraction:.4f} | "
            "{pipeline_solvent_fraction:.4f} | "
            "{mass_model_relative_difference:.4%} |".format(**raw)
        )
    lines.extend(
        [
            "",
            "## Scientific boundary",
            "",
            str(document["selection_note"]),
            (
                "The Phenix residue-count calculation and pipeline exact-sequence "
                "calculation use different mass models. The reported bound is an "
                "engineering compatibility check, not a tuned scientific prior. "
                "This report does not establish a positive control."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def qualify_matthews_reference(
    request: MatthewsReferenceRequest,
) -> MatthewsReferenceResult:
    """Run one local Phenix reference and publish an auditable comparison."""

    if request.timeout_seconds <= 0:
        raise MatthewsReferenceInputError("timeout_seconds must be positive")

    steps = tqdm(
        total=4,
        desc="Qualify Matthews reference",
        unit="step",
        disable=not request.progress,
    )
    try:
        crystal_manifest = load_contract(
            request.crystal_manifest.resolve(strict=True),
            "crystal-manifest",
            progress=False,
        )
        config = load_contract(
            request.pipeline_config.resolve(strict=True),
            "pipeline-config",
            progress=False,
        )
        if not isinstance(crystal_manifest, CrystalManifest) or not isinstance(
            config, PipelineConfig
        ):
            raise TypeError("Matthews reference received unexpected contracts")
        crystal = _selected_crystal(crystal_manifest, request.crystal_id)
        preflight = _load_selected_jsonl(
            request.preflight_jsonl,
            model=MtzPreflightRecord,
            identifier_name="crystal_id",
            identifier=request.crystal_id,
        )
        group = _load_selected_jsonl(
            request.sequence_groups_jsonl,
            model=SequenceGroupRecord,
            identifier_name="sequence_group_id",
            identifier=request.sequence_group_id,
        )
        if not isinstance(preflight, MtzPreflightRecord) or not isinstance(
            group, SequenceGroupRecord
        ):
            raise TypeError("Matthews reference selected unexpected record types")
        matching_source_ids = _validate_catalogue_membership(
            request.source_records_jsonl,
            sequence_group_id=group.sequence_group_id,
            catalogue_id=crystal.catalogue_id,
        )
        mtz_path = _resolve_manifest_path(crystal.mtz, request.crystal_manifest)
        mtz_sha256 = sha256_file(
            mtz_path,
            progress=request.progress,
            description=f"Verify {crystal.crystal_id} MTZ",
            logger=_LOGGER,
        )
        if mtz_sha256 != preflight.mtz_sha256:
            raise MatthewsReferenceInputError(
                "crystal MTZ checksum does not match the selected preflight record"
            )
        if preflight.asu_volume_a3 <= 0:
            raise MatthewsReferenceInputError("preflight ASU volume must be positive")
        pipeline_rows = enumerate_group(group, crystal, preflight, config)
        steps.update()
        _LOGGER.info(
            "Matthews reference inputs validated",
            extra={
                "crystal_id": crystal.crystal_id,
                "sequence_group_id": group.sequence_group_id,
                "sequence_length_aa": group.length_aa,
            },
        )

        output = request.output_directory.resolve()
        work = output / "work"
        try:
            execution = capture_matthews_reference_from_manifest(
                request.phenix_manifest,
                mtz_path=mtz_path,
                residue_count=group.length_aa,
                working_directory=work,
                timeout_seconds=request.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise MatthewsReferenceExecutionError(
                f"Phenix Matthews reference exceeded {request.timeout_seconds} seconds"
            ) from error
        steps.update()
        combined_output = execution.completed.stdout + execution.completed.stderr
        reference_text = combined_output.decode("utf-8", errors="replace")
        log_path = output / "phenix_matthews.log"
        atomic_write_text(log_path, reference_text)
        if execution.completed.returncode != 0:
            raise MatthewsReferenceExecutionError(
                "Phenix Matthews reference failed with exit status "
                f"{execution.completed.returncode}; preserved log: {log_path}"
            )
        parsed = parse_phenix_matthews_output(reference_text)
        steps.update()

        manifest_sha256 = sha256_file(request.phenix_manifest.resolve(strict=True))
        document = _comparison_document(
            crystal=crystal,
            preflight=preflight,
            group=group,
            matching_source_ids=matching_source_ids,
            config=config,
            pipeline_rows=pipeline_rows,
            parsed=parsed,
            execution=execution,
            mtz_path=mtz_path,
            mtz_sha256=mtz_sha256,
            manifest_sha256=manifest_sha256,
        )
        json_path = output / "matthews_reference.json"
        markdown_path = output / "matthews_reference.md"
        atomic_write_json(json_path, document)
        atomic_write_text(markdown_path, _markdown(document))
        steps.update()
    finally:
        steps.close()

    raw_status = document["status"]
    comparison_id = document["comparison_id"]
    if raw_status not in {"passed", "failed"} or not isinstance(comparison_id, str):
        raise AssertionError("invalid internal Matthews reference result")
    status: Literal["passed", "failed"] = (
        "passed" if raw_status == "passed" else "failed"
    )
    _LOGGER.info(
        "Matthews method-reference qualification complete",
        extra={
            "status": status,
            "comparison_id": comparison_id,
            "output_directory": str(request.output_directory.resolve()),
        },
    )
    return MatthewsReferenceResult(
        status=status,
        comparison_id=comparison_id,
        json_path=json_path,
        markdown_path=markdown_path,
        phenix_log_path=log_path,
    )
