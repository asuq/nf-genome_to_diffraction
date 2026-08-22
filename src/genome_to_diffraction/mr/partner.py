"""Search one B component while retaining one fixed A solution.

This deliberately narrow v0.2 adapter accepts two exact catalogue sequence
groups, one checksum-bound placed A coordinate, one checksum-bound B search
model, one preflight-qualified MTZ, and a verified Phenix installation. It runs
``phenix.phaser`` in ``MR_AUTO`` mode with A fixed at the origin and B as the
only searched ensemble. The output therefore records B-specific TFZ and the
incremental LLG relative to the supplied A-only parent value.

The only supported composition is ``1A + 1B``. General ``nA + mB`` search is a
later milestone. A completed no-solution result is distinct from tool and parse
failure, and never claims that B is biologically absent. Packing and component
markers are retained as search evidence rather than treated as proof of the
composition. The adapter uses the installed ``phenix.phaser`` version recorded
by the required Phenix manifest; no Phenix version is bundled. It writes
``partner_search_result.json`` and JSONL, ``phaser_command.json``, the PHIL
parameter file, capture/native logs, and any combined ``PHASER.1`` PDB/MTZ.

The cache identity is the adapter version plus the two sequence digests, parent
solution/coordinate/LLG, B model identity, MTZ, and Phenix-manifest checksums.
Focused tests cover command construction, primary/fallback score
classification, no-solution, tool/parse failure, and checksum drift. A real
installed Phenix run is still required for P1 qualification.
"""

import json
import logging
import math
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.mr.phaser import (
    PhaserInputError,
    PhaserParseError,
    parse_completed_phaser_outputs,
    read_phaser_solution_metrics,
)
from genome_to_diffraction.phenix.runtime import (
    capture_from_manifest,
    validate_manifest_environment,
)
from genome_to_diffraction.schemas.results import (
    MtzPreflightRecord,
    PartnerSearchResult,
    PreflightDecision,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import ExecutionStatus
from genome_to_diffraction.time import utc_now_iso

_LOGGER = logging.getLogger("genome_to_diffraction.mr.partner")
_ADAPTER_VERSION = "phenix-fixed-a-one-b-v1"
_ROOT = "PHASER"
_PRIMARY_LLG = 100.0
_PRIMARY_TFZ = 10.0
_FALLBACK_LLG = 50.0
_FALLBACK_TFZ = 5.0
_FIXED_PARENT_PLACEMENT = re.compile(
    r"^REMARK ENSEMBLE\s+fixed_parent(?:\s|$)", re.I | re.M
)
_SEARCH_PARTNER_PLACEMENT = re.compile(
    r"^REMARK ENSEMBLE\s+search_partner(?:\s|$)", re.I | re.M
)
_NO_COMPLETE_COMPOSITION = re.compile(
    r"^\s*\*\*\s+Sorry\s+-\s+No solution with all components\s*$", re.I | re.M
)
_INPUT_SOLUTION_NOT_EXTENDED = re.compile(
    r"^\s*\*\*\s+Search did not extend input solution with new components\s*$",
    re.I | re.M,
)
_SUCCESSFUL_EXIT = re.compile(r"^\s*EXIT STATUS:\s+SUCCESS\s*$", re.I | re.M)

type _ScoreCohort = Literal["primary", "fallback", "below_threshold"]


@dataclass(frozen=True)
class PartnerSearchRequest:
    """Immutable inputs for one checksum-bound ``1A + 1B`` Phaser search."""

    crystal_id: str
    parent_solution_id: str
    parent_sequence_group_id: str
    partner_sequence_group_id: str
    sequence_groups_jsonl: Path
    parent_coordinate: Path
    expected_parent_coordinate_sha256: str
    parent_llg: float
    partner_model: Path
    expected_partner_model_sha256: str
    partner_model_identity_fraction: float
    preflight_jsonl: Path
    mtz: Path
    phenix_manifest: Path
    output_directory: Path
    threads: int = 1
    timeout_seconds: float | None = None
    progress: bool = True


@dataclass(frozen=True)
class PartnerSearchOutput:
    """Typed result and retained files from one fixed-A/one-B attempt."""

    result: PartnerSearchResult
    result_json: Path
    result_jsonl: Path
    command_json: Path
    parameters_file: Path


@dataclass(frozen=True)
class _Resolved:
    parent_group: SequenceGroupRecord
    partner_group: SequenceGroupRecord
    preflight: MtzPreflightRecord
    parent_coordinate: Path
    parent_coordinate_sha256: str
    partner_model: Path
    partner_model_sha256: str
    mtz: Path
    mtz_sha256: str


def _read_jsonl[T: BaseModel](
    path: Path, model: type[T], *, label: str
) -> tuple[T, ...]:
    resolved = path.resolve(strict=True)
    records: list[T] = []
    with resolved.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(model.model_validate_json(line))
            except ValidationError as error:
                raise PhaserInputError(
                    f"invalid {label} record at line {line_number}: {resolved}"
                ) from error
    if not records:
        raise PhaserInputError(f"{label} input is empty: {resolved}")
    return tuple(records)


def _one_by_id[T](
    records: tuple[T, ...],
    *,
    identifier: str,
    key: Callable[[T], str],
    label: str,
) -> T:
    matches = [record for record in records if key(record) == identifier]
    if len(matches) != 1:
        raise PhaserInputError(
            f"expected exactly one {label} {identifier!r}; observed {len(matches)}"
        )
    return matches[0]


def _regular_file(path: Path, *, label: str) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise PhaserInputError(f"{label} is not a regular file: {resolved}")
    return resolved


def _resolve(request: PartnerSearchRequest) -> _Resolved:
    if not request.crystal_id.strip() or not request.parent_solution_id.strip():
        raise PhaserInputError("crystal and parent solution IDs must not be empty")
    if request.parent_sequence_group_id == request.partner_sequence_group_id:
        raise PhaserInputError("A and B must be distinct exact-sequence groups")
    if not math.isfinite(request.parent_llg):
        raise PhaserInputError("parent LLG must be finite")
    if not math.isfinite(request.partner_model_identity_fraction) or not (
        0 < request.partner_model_identity_fraction <= 1
    ):
        raise PhaserInputError("partner model identity fraction must be in (0, 1]")

    groups = _read_jsonl(
        request.sequence_groups_jsonl, SequenceGroupRecord, label="sequence groups"
    )
    parent_group = _one_by_id(
        groups,
        identifier=request.parent_sequence_group_id,
        key=lambda item: item.sequence_group_id,
        label="parent sequence group",
    )
    partner_group = _one_by_id(
        groups,
        identifier=request.partner_sequence_group_id,
        key=lambda item: item.sequence_group_id,
        label="partner sequence group",
    )
    preflights = _read_jsonl(
        request.preflight_jsonl, MtzPreflightRecord, label="MTZ preflights"
    )
    preflight = _one_by_id(
        preflights,
        identifier=request.crystal_id,
        key=lambda item: item.crystal_id,
        label="MTZ preflight",
    )
    if preflight.decision is PreflightDecision.FAIL:
        raise PhaserInputError("cannot run partner search against failed MTZ preflight")
    if preflight.selected_observation_labels is None:
        raise PhaserInputError("MTZ preflight lacks selected observation labels")

    parent_coordinate = _regular_file(
        request.parent_coordinate, label="fixed A coordinate"
    )
    parent_coordinate_sha256 = sha256_file(
        parent_coordinate,
        progress=request.progress,
        description="Verify fixed A coordinate",
        logger=_LOGGER,
    )
    if parent_coordinate_sha256 != request.expected_parent_coordinate_sha256:
        raise PhaserInputError("fixed A coordinate checksum differs from request")
    partner_model = _regular_file(request.partner_model, label="B search model")
    partner_model_sha256 = sha256_file(
        partner_model,
        progress=request.progress,
        description="Verify B search model",
        logger=_LOGGER,
    )
    if partner_model_sha256 != request.expected_partner_model_sha256:
        raise PhaserInputError("B search model checksum differs from request")
    mtz = _regular_file(request.mtz, label="MTZ")
    mtz_sha256 = sha256_file(
        mtz,
        progress=request.progress,
        description="Verify partner-search MTZ",
        logger=_LOGGER,
    )
    if mtz_sha256 != preflight.mtz_sha256:
        raise PhaserInputError("MTZ checksum differs from preflight")
    return _Resolved(
        parent_group=parent_group,
        partner_group=partner_group,
        preflight=preflight,
        parent_coordinate=parent_coordinate,
        parent_coordinate_sha256=parent_coordinate_sha256,
        partner_model=partner_model,
        partner_model_sha256=partner_model_sha256,
        mtz=mtz,
        mtz_sha256=mtz_sha256,
    )


def _parameters(
    resolved: _Resolved,
    parent_fasta: Path,
    partner_fasta: Path,
    identity_fraction: float,
    threads: int,
) -> str:
    mtz = json.dumps(str(resolved.mtz))
    parent_sequence = json.dumps(str(parent_fasta))
    partner_sequence = json.dumps(str(partner_fasta))
    parent = json.dumps(str(resolved.parent_coordinate))
    partner = json.dumps(str(resolved.partner_model))
    return f"""phaser {{
  mode = MR_AUTO
  hklin = {mtz}
  labin = {resolved.preflight.selected_observation_labels}
  composition {{
    chain {{
      chain_type = protein
      comp_type = sequence_file
      sequence_file = {parent_sequence}
      num = 1
    }}
    chain {{
      chain_type = protein
      comp_type = sequence_file
      sequence_file = {partner_sequence}
      num = 1
    }}
  }}
  ensemble {{
    model_id = fixed_parent
    solution_at_origin = True
    coordinates {{
      pdb = {parent}
      identity = 1.0
    }}
  }}
  ensemble {{
    model_id = search_partner
    coordinates {{
      pdb = {partner}
      identity = {identity_fraction:.12g}
    }}
  }}
  search {{
    ensembles = search_partner
    copies = 1
  }}
  keywords {{
    general {{
      root = {_ROOT}
      jobs = {threads}
    }}
    sgalternative {{ select = none }}
  }}
}}
"""


def _reported_no_partner_solution(text: str) -> bool:
    return (
        _NO_COMPLETE_COMPOSITION.search(text) is not None
        and _INPUT_SOLUTION_NOT_EXTENDED.search(text) is not None
        and _SUCCESSFUL_EXIT.search(text) is not None
    )


def _score_cohort(incremental_llg: float, tfz: float) -> _ScoreCohort:
    if incremental_llg > _PRIMARY_LLG and tfz > _PRIMARY_TFZ:
        return "primary"
    if incremental_llg > _FALLBACK_LLG and tfz > _FALLBACK_TFZ:
        return "fallback"
    return "below_threshold"


def _write_output(
    output: Path,
    result: PartnerSearchResult,
    command: Path,
    parameters: Path,
) -> PartnerSearchOutput:
    result_json = output / "partner_search_result.json"
    result_jsonl = output / "partner_search_result.jsonl"
    atomic_write_json(result_json, result.model_dump(mode="json"))
    atomic_write_text(result_jsonl, f"{canonical_json_text(result)}\n")
    return PartnerSearchOutput(result, result_json, result_jsonl, command, parameters)


def run_partner_search(request: PartnerSearchRequest) -> PartnerSearchOutput:
    """Run one fixed-A search for exactly one B copy."""

    if request.threads < 1:
        raise ValueError("threads must be positive")
    if request.timeout_seconds is not None and request.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive when supplied")
    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise PhaserInputError(
            f"partner-search output directory is not empty: {output}"
        )

    resolved = _resolve(request)
    phenix_manifest = validate_manifest_environment(
        request.phenix_manifest.resolve(strict=True)
    )
    phenix_manifest_sha256 = sha256_file(request.phenix_manifest.resolve(strict=True))
    output.mkdir(parents=True, exist_ok=True)
    parent_fasta = output / "component_A.fasta"
    partner_fasta = output / "component_B.fasta"
    atomic_write_text(
        parent_fasta,
        f">{resolved.parent_group.sequence_group_id}\n{resolved.parent_group.sequence}\n",
    )
    atomic_write_text(
        partner_fasta,
        f">{resolved.partner_group.sequence_group_id}\n{resolved.partner_group.sequence}\n",
    )
    parameters = output / "partner_search.eff"
    atomic_write_text(
        parameters,
        _parameters(
            resolved,
            parent_fasta,
            partner_fasta,
            request.partner_model_identity_fraction,
            request.threads,
        ),
    )
    search_identity = {
        "adapter_version": _ADAPTER_VERSION,
        "crystal_id": request.crystal_id,
        "parent_solution_id": request.parent_solution_id,
        "parent_sequence_sha256": resolved.parent_group.sha256,
        "partner_sequence_sha256": resolved.partner_group.sha256,
        "parent_coordinate_sha256": resolved.parent_coordinate_sha256,
        "parent_llg": request.parent_llg,
        "partner_model_sha256": resolved.partner_model_sha256,
        "partner_model_identity_fraction": request.partner_model_identity_fraction,
        "mtz_sha256": resolved.mtz_sha256,
        "phenix_manifest_sha256": phenix_manifest_sha256,
        "parent_copy_count": 1,
        "partner_copy_count": 1,
    }
    search_id = content_id("partner_", search_identity)
    arguments = ["phenix.phaser", str(parameters)]
    command_json = output / "phaser_command.json"
    atomic_write_json(
        command_json,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "created_at": utc_now_iso(),
            "search_id": search_id,
            "arguments": arguments,
            "threads": request.threads,
            "timeout_seconds": request.timeout_seconds,
            "parameters_sha256": sha256_file(parameters),
            "observation_labels": resolved.preflight.selected_observation_labels,
            "observation_dataset_id": (
                resolved.preflight.selected_observation_dataset_id
            ),
            "space_group": resolved.preflight.space_group,
            "primary_thresholds": {
                "incremental_llg": _PRIMARY_LLG,
                "partner_tfz": _PRIMARY_TFZ,
            },
            "fallback_thresholds": {
                "incremental_llg": _FALLBACK_LLG,
                "partner_tfz": _FALLBACK_TFZ,
            },
            **search_identity,
        },
    )
    _LOGGER.info(
        "fixed-A/one-B Phaser search started",
        extra={
            "search_id": search_id,
            "crystal_id": request.crystal_id,
            "threads": request.threads,
        },
    )
    with tqdm(
        total=1,
        desc="Run fixed-A/one-B Phaser",
        unit="composition",
        disable=not request.progress,
    ) as progress_bar:
        try:
            completed = capture_from_manifest(
                request.phenix_manifest,
                arguments,
                working_directory=output,
                timeout_seconds=request.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            completed = subprocess.CompletedProcess(arguments, 124, b"", b"timed out")
        progress_bar.update(1)

    capture_log = output / "phenix.phaser.capture.log"
    atomic_write_text(
        capture_log,
        (completed.stdout + completed.stderr).decode("utf-8", errors="replace"),
    )
    native_log = output / f"{_ROOT}.log"
    raw_log = native_log if native_log.is_file() else capture_log
    tool_version = phenix_manifest.phenix_version
    status = ExecutionStatus.FAILED_TOOL_EXECUTION
    combined_llg = incremental_llg = partner_tfz = None
    solution_count = partner_placement_count = 0
    top_solution_packed = fixed_parent_observed = partner_observed = False
    score_cohort: _ScoreCohort | None = None
    combined_solution_id = None
    coordinate_path = coordinate_sha256 = output_mtz_path = output_mtz_sha256 = None
    warnings: list[str] = []
    rejection_reason: str | None = None

    if completed.returncode != 0:
        rejection_reason = (
            "phenix.phaser_timeout"
            if completed.returncode == 124
            else f"phenix.phaser_exit_{completed.returncode}"
        )
    else:
        try:
            raw_text = raw_log.read_text(encoding="utf-8", errors="replace")
            if _reported_no_partner_solution(raw_text):
                status = ExecutionStatus.COMPLETED_NO_HIT
                rejection_reason = "phaser_reported_no_partner_solution"
            else:
                parsed = parse_completed_phaser_outputs(raw_text, output)
                warnings.extend(parsed.parser_warnings)
                if parsed.phaser_version is not None:
                    tool_version = (
                        f"Phenix {phenix_manifest.phenix_version}; "
                        f"Phaser {parsed.phaser_version}"
                    )
                if parsed.solution_count == 0:
                    status = ExecutionStatus.COMPLETED_NO_HIT
                    rejection_reason = "phaser_reported_no_partner_solution"
                else:
                    coordinate = output / f"{_ROOT}.1.pdb"
                    result_mtz = output / f"{_ROOT}.1.mtz"
                    if not coordinate.is_file() or not result_mtz.is_file():
                        raise PhaserParseError(
                            "partner solution lacks combined PDB or MTZ"
                        )
                    combined_llg, partner_tfz, _, _ = read_phaser_solution_metrics(
                        parsed, coordinate
                    )
                    if combined_llg is None or partner_tfz is None:
                        raise PhaserParseError(
                            "partner solution lacks final LLG or TFZ"
                        )
                    coordinate_text = coordinate.read_text(
                        encoding="utf-8", errors="replace"
                    )
                    fixed_parent_observed = (
                        _FIXED_PARENT_PLACEMENT.search(coordinate_text) is not None
                    )
                    partner_placement_count = len(
                        _SEARCH_PARTNER_PLACEMENT.findall(coordinate_text)
                    )
                    partner_observed = (
                        fixed_parent_observed and partner_placement_count == 1
                    )
                    incremental_llg = combined_llg - request.parent_llg
                    solution_count = parsed.solution_count
                    top_solution_packed = parsed.packed_solution_count > 0
                    score_cohort = _score_cohort(incremental_llg, partner_tfz)
                    coordinate_path = coordinate.name
                    coordinate_sha256 = sha256_file(coordinate)
                    output_mtz_path = result_mtz.name
                    output_mtz_sha256 = sha256_file(result_mtz)
                    combined_solution_id = content_id(
                        "composition_",
                        {
                            "search_id": search_id,
                            "coordinate_sha256": coordinate_sha256,
                            "mtz_sha256": output_mtz_sha256,
                        },
                    )
                    status = ExecutionStatus.COMPLETED_HIT
                    if not top_solution_packed:
                        warnings.append("partner_solution_not_packing_supported")
                        rejection_reason = "parsed_partner_solution_did_not_pack"
                    elif not partner_observed:
                        warnings.append("combined_solution_lacks_A_B_markers")
                        rejection_reason = "combined_solution_lacks_component_markers"
                    if score_cohort == "below_threshold":
                        warnings.append("partner_scores_below_fallback_threshold")
        except PhaserParseError as error:
            status = ExecutionStatus.FAILED_PARSE
            rejection_reason = str(error)

    result = PartnerSearchResult(
        schema_version="1.0",
        search_id=search_id,
        crystal_id=request.crystal_id,
        tool_version=tool_version,
        parent_solution_id=request.parent_solution_id,
        parent_sequence_group_id=resolved.parent_group.sequence_group_id,
        partner_sequence_group_id=resolved.partner_group.sequence_group_id,
        execution_status=status,
        parent_llg=request.parent_llg,
        combined_llg=combined_llg,
        incremental_llg=incremental_llg,
        partner_tfz=partner_tfz,
        solution_count=solution_count,
        top_solution_packed=top_solution_packed,
        fixed_parent_placement_observed=fixed_parent_observed,
        partner_placement_count=partner_placement_count,
        partner_placement_observed=partner_observed,
        score_cohort=score_cohort,
        combined_solution_id=combined_solution_id,
        combined_coordinate_path=coordinate_path,
        combined_coordinate_sha256=coordinate_sha256,
        output_mtz_path=output_mtz_path,
        output_mtz_sha256=output_mtz_sha256,
        parent_coordinate_sha256=resolved.parent_coordinate_sha256,
        partner_model_sha256=resolved.partner_model_sha256,
        mtz_sha256=resolved.mtz_sha256,
        raw_log_pointer=raw_log.name,
        command_pointer=command_json.name,
        parameters_pointer=parameters.name,
        warnings=tuple(warnings),
        rejection_reason=rejection_reason,
    )
    _LOGGER.info(
        "fixed-A/one-B Phaser search finished",
        extra={
            "search_id": search_id,
            "execution_status": status.value,
            "partner_tfz": partner_tfz,
            "incremental_llg": incremental_llg,
            "score_cohort": score_cohort,
        },
    )
    return _write_output(output, result, command_json, parameters)
