"""Run the fixed T12 brief-refinement and sequence-narrowing protocol.

The adapter consumes one retained M4 parent coordinate/MTZ, the complete exact
sequence catalogue, source-record crosswalk, and verified Phenix manifest. It
runs a single conservative ``phenix.refine`` macrocycle, writes one sigma-scaled
cell ``2mFo-DFc`` map, and asks ``phenix.sequence_from_map`` to score every exact
sequence group. All scores and catalogue-to-locus ambiguity are retained.

Tool failures become typed candidate-level results; they do not discard other
finalists. The cache identity includes input/checkpoint hashes, the complete
catalogue, Phenix manifest, protocol version, resolution, and thread count.
Unit tests cover command construction, parsers, checksum rejection, and failed
tool execution. Real Phenix qualification remains mandatory on Viper.
"""

import logging
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.phenix.runtime import (
    capture_from_manifest,
    validate_manifest_environment,
)
from genome_to_diffraction.schemas.results import (
    BriefRefinementResult,
    SequenceGroupRecord,
    SequenceMapCandidate,
    SequenceMapResult,
    SourceProteinRecord,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_LOGGER = logging.getLogger("genome_to_diffraction.refinement.brief")
_PROTOCOL_VERSION = "phenix-t12-brief-v3"
_R_VALUES = re.compile(
    r"(?:R[-_ ]?work|r_work)\s*[=:]\s*([0-9]+(?:\.[0-9]+)?)"
    r"[^\n]{0,120}?(?:R[-_ ]?free|r_free)\s*[=:]\s*([0-9]+(?:\.[0-9]+)?)",
    re.I,
)
_RMS_BONDS = re.compile(
    r"(?:rmsd?\s*)?(?:bonds?|bond lengths?)\s*[=:]\s*([0-9.]+)", re.I
)
_RMS_ANGLES = re.compile(
    r"(?:rmsd?\s*)?(?:angles?|bond angles?)\s*[=:]\s*([0-9.]+)", re.I
)
_SCORE = re.compile(
    r"Score for sequence\s+\d+\s+\((\d+) residues\):\s+"
    r"(-?[0-9]+(?:\.[0-9]+)?)\s+\(>(seq_[0-9a-f]{64})\)"
)
_SCORE_SUMMARY = re.compile(
    r"Overall best Z-score:\s*(-?[0-9]+(?:\.[0-9]+)?)\s+"
    r"Mean and SD of scores:\s*(-?[0-9]+(?:\.[0-9]+)?)\s+\+/-\s+"
    r"([0-9]+(?:\.[0-9]+)?)",
    re.I,
)


class T12InputError(InputContractError):
    """A T12 candidate input does not match its checksum-bound identity."""


@dataclass(frozen=True)
class T12RunRequest:
    """Immutable input and resource controls for one retained finalist."""

    seed_solution_id: str
    sequence_group_id: str
    input_copy_count: int
    parent_coordinate: Path
    parent_coordinate_sha256: str
    parent_mtz: Path
    parent_mtz_sha256: str
    observation_labels: str
    sequence_groups_jsonl: Path
    source_records_jsonl: Path
    resolution: float
    phenix_manifest: Path
    output_directory: Path
    threads: int = 4
    timeout_seconds: float | None = None
    progress: bool = True


@dataclass(frozen=True)
class T12RunOutput:
    """Typed refinement and sequence results plus their stable files."""

    refinement: BriefRefinementResult
    sequence: SequenceMapResult
    refinement_json: Path
    refinement_jsonl: Path
    sequence_json: Path
    sequence_jsonl: Path
    command_json: Path


def _read_jsonl[T: BaseModel](
    path: Path, model: type[T], *, label: str
) -> tuple[T, ...]:
    records: list[T] = []
    resolved = path.resolve(strict=True)
    with resolved.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(model.model_validate_json(line))
            except ValidationError as error:
                raise T12InputError(
                    f"invalid {label} at line {line_number}: {resolved}"
                ) from error
    if not records:
        raise T12InputError(f"{label} input is empty: {resolved}")
    return tuple(records)


def _verified_file(path: Path, expected: str, *, label: str, progress: bool) -> Path:
    if path.is_symlink():
        raise T12InputError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise T12InputError(f"{label} is not a regular file")
    actual = sha256_file(
        resolved, progress=progress, description=f"Verify {label}", logger=_LOGGER
    )
    if actual != expected:
        raise T12InputError(f"{label} checksum mismatch")
    return resolved


def _write_catalogue_fasta(
    groups: tuple[SequenceGroupRecord, ...], path: Path, *, progress: bool
) -> None:
    lines: list[str] = []
    iterator = tqdm(
        groups,
        desc="Write exact catalogue",
        unit="group",
        disable=not progress,
        leave=False,
    )
    for group in iterator:
        lines.append(f">{group.sequence_group_id}")
        lines.extend(
            group.sequence[index : index + 80]
            for index in range(0, len(group.sequence), 80)
        )
    atomic_write_text(path, "\n".join(lines) + "\n")


def _refine_parameters(*, threads: int, map_name: str) -> str:
    return f"""refinement {{
  main {{
    number_of_macro_cycles = 1
    nproc = {threads}
    random_seed = 2679941
    simulated_annealing = False
    ordered_solvent = False
  }}
  refine {{
    strategy = individual_sites individual_adp
  }}
  output {{
    write_map_coefficients = True
    write_maps = True
    write_model_cif_file = False
    write_final_pdb_file = True
  }}
  electron_density_maps {{
    map_coefficients {{
      map_type = 2mFo-DFc
    }}
    map {{
      map_type = 2mFo-DFc
      format = ccp4
      file_name = {map_name}
      fill_missing_f_obs = False
      scale = sigma
      region = cell
    }}
  }}
}}
output {{
  prefix = brief_refine
  serial = 0
  overwrite = True
}}
"""


def _refinement_output_paths(outdir: Path) -> tuple[Path, Path, Path]:
    """Return the fixed Phenix serial-001 PDB/MTZ and explicit CCP4 names."""
    return (
        outdir / "brief_refine_001.pdb",
        outdir / "brief_refine_001.mtz",
        outdir / "brief_refine_2mFo-DFc.ccp4",
    )


def _observation_label_argument(labels: str) -> str:
    if not labels.strip() or "\n" in labels:
        raise T12InputError("observation_labels must be one non-empty line")
    return f"data_manager.miller_array.labels.name={labels}"


def _combined_log(completed: subprocess.CompletedProcess[bytes]) -> str:
    return (completed.stdout + completed.stderr).decode("utf-8", errors="replace")


def _refinement_metrics(text: str) -> tuple[float | None, ...]:
    matches = [(float(a), float(b)) for a, b in _R_VALUES.findall(text)]
    bonds = [float(value) for value in _RMS_BONDS.findall(text)]
    angles = [float(value) for value in _RMS_ANGLES.findall(text)]
    if not matches:
        return (
            None,
            None,
            None,
            None,
            bonds[-1] if bonds else None,
            angles[-1] if angles else None,
        )
    initial = matches[0]
    final = matches[-1]
    return (
        initial[0],
        initial[1],
        final[0],
        final[1],
        bonds[-1] if bonds else None,
        angles[-1] if angles else None,
    )


def _source_crosswalk(
    records: tuple[SourceProteinRecord, ...],
) -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    grouped: dict[str, list[SourceProteinRecord]] = {}
    for record in records:
        grouped.setdefault(record.sequence_group_id, []).append(record)
    return {
        group_id: (
            tuple(sorted(item.source_record_id for item in items)),
            tuple(
                sorted(
                    {
                        value
                        for item in items
                        for value in (item.locus_tag, item.gene_name)
                        if value
                    }
                )
            ),
        )
        for group_id, items in grouped.items()
    }


def _sequence_candidates(
    text: str,
    *,
    refinement_id: str,
    groups: dict[str, SequenceGroupRecord],
    crosswalk: dict[str, tuple[tuple[str, ...], tuple[str, ...]]],
) -> tuple[
    tuple[SequenceMapCandidate, ...],
    float | None,
    float | None,
    float | None,
    float | None,
]:
    raw = [
        (group_id, int(length), float(score))
        for length, score, group_id in _SCORE.findall(text)
    ]
    ordered = sorted(raw, key=lambda item: (-item[2], item[0]))
    summary = _SCORE_SUMMARY.search(text)
    best_z = float(summary.group(1)) if summary else None
    mean = float(summary.group(2)) if summary else None
    sd = float(summary.group(3)) if summary else None
    candidates: list[SequenceMapCandidate] = []
    for rank, (group_id, length, score) in enumerate(ordered, start=1):
        group = groups.get(group_id)
        source = crosswalk.get(group_id)
        if group is None or source is None or group.length_aa != length:
            raise T12InputError(
                f"sequence-from-map output does not map to catalogue group {group_id}"
            )
        score_z = (
            None if sd is None or sd == 0.0 or mean is None else (score - mean) / sd
        )
        candidates.append(
            SequenceMapCandidate(
                schema_version="1.0",
                refinement_id=refinement_id,
                rank=rank,
                sequence_group_id=group_id,
                sequence_length=length,
                raw_score=score,
                score_z=score_z if score_z is None or math.isfinite(score_z) else None,
                source_record_ids=source[0],
                source_loci=source[1],
                warnings=("exact_sequence_group_maps_to_multiple_source_records",)
                if len(source[0]) > 1
                else (),
            )
        )
    best = candidates[0].raw_score if candidates else None
    return tuple(candidates), best, mean, sd, best_z


def _write_result(path: Path, result: BaseModel) -> tuple[Path, Path]:
    atomic_write_json(path, result.model_dump(mode="json"))
    jsonl = path.with_suffix(".jsonl")
    atomic_write_text(jsonl, canonical_json_text(result) + "\n")
    return path, jsonl


def run_t12_candidate(request: T12RunRequest) -> T12RunOutput:
    """Run one retained finalist through fixed refinement, map, and sequence steps."""

    if request.input_copy_count < 1:
        raise T12InputError("input_copy_count must be positive")
    if request.threads < 1 or request.threads > 64:
        raise T12InputError("threads must be between 1 and 64")
    if request.resolution <= 0:
        raise T12InputError("resolution must be positive")
    observation_label_argument = _observation_label_argument(request.observation_labels)
    parent_coordinate = _verified_file(
        request.parent_coordinate,
        request.parent_coordinate_sha256,
        label="parent coordinate",
        progress=request.progress,
    )
    parent_mtz = _verified_file(
        request.parent_mtz,
        request.parent_mtz_sha256,
        label="parent MTZ",
        progress=request.progress,
    )
    groups = _read_jsonl(
        request.sequence_groups_jsonl, SequenceGroupRecord, label="sequence group"
    )
    source_records = _read_jsonl(
        request.source_records_jsonl, SourceProteinRecord, label="source record"
    )
    group_by_id = {group.sequence_group_id: group for group in groups}
    if len(group_by_id) != len(groups) or request.sequence_group_id not in group_by_id:
        raise T12InputError(
            "sequence groups are duplicated or finalist group is absent"
        )
    crosswalk = _source_crosswalk(source_records)
    if set(group_by_id) != set(crosswalk):
        raise T12InputError("complete sequence catalogue and source crosswalk differ")
    manifest_path = request.phenix_manifest.resolve(strict=True)
    manifest = validate_manifest_environment(manifest_path)
    outdir = request.output_directory.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    catalogue_fasta = outdir / "exact_sequence_catalogue.fasta"
    _write_catalogue_fasta(groups, catalogue_fasta, progress=request.progress)
    refinement_id = content_id(
        "refine_",
        {
            "protocol": _PROTOCOL_VERSION,
            "seed_solution_id": request.seed_solution_id,
            "sequence_group_id": request.sequence_group_id,
            "input_copy_count": request.input_copy_count,
            "parent_coordinate_sha256": request.parent_coordinate_sha256,
            "parent_mtz_sha256": request.parent_mtz_sha256,
            "observation_labels": request.observation_labels,
            "catalogue_sha256": sha256_file(request.sequence_groups_jsonl),
            "source_records_sha256": sha256_file(request.source_records_jsonl),
            "phenix_manifest_sha256": sha256_file(manifest_path),
            "resolution": request.resolution,
            "threads": request.threads,
        },
    )
    refined_model, refined_mtz, map_path = _refinement_output_paths(outdir)
    params_path = outdir / "brief_refine.eff"
    atomic_write_text(
        params_path,
        _refine_parameters(
            threads=request.threads, map_name="brief_refine_2mFo-DFc.ccp4"
        ),
    )
    refine_args = [
        "phenix.refine",
        str(parent_coordinate),
        str(parent_mtz),
        str(params_path),
        observation_label_argument,
    ]
    command_path = outdir / "t12_command.json"
    command_record: dict[str, object] = {
        "schema_version": "1.0",
        "protocol_version": _PROTOCOL_VERSION,
        "refinement_id": refinement_id,
        "refine_arguments": refine_args,
        "sequence_arguments": None,
        "inputs": {
            "parent_coordinate_sha256": request.parent_coordinate_sha256,
            "parent_mtz_sha256": request.parent_mtz_sha256,
            "observation_labels": request.observation_labels,
            "catalogue_fasta_sha256": sha256_file(catalogue_fasta),
            "phenix_manifest_sha256": sha256_file(manifest_path),
        },
    }
    atomic_write_json(command_path, command_record)
    _LOGGER.info(
        "brief refinement started",
        extra={
            "refinement_id": refinement_id,
            "seed_solution_id": request.seed_solution_id,
        },
    )
    completed = capture_from_manifest(
        manifest_path,
        refine_args,
        working_directory=outdir,
        timeout_seconds=request.timeout_seconds,
    )
    refine_log = outdir / "phenix.refine.log"
    refine_text = _combined_log(completed)
    atomic_write_text(refine_log, refine_text)
    initial_rw, initial_rf, final_rw, final_rf, rms_bonds, rms_angles = (
        _refinement_metrics(refine_text)
    )
    required_assets = (refined_model, refined_mtz, map_path)
    refinement_success = completed.returncode == 0 and all(
        path.is_file() for path in required_assets
    )
    refinement_warnings: list[str] = []
    if (
        refinement_success
        and final_rf is not None
        and initial_rf is not None
        and final_rf > initial_rf
    ):
        refinement_warnings.append("r_free_increased_during_brief_refinement")
    if completed.returncode == 0 and not refinement_success:
        refinement_warnings.append("phenix_refine_completed_without_required_assets")
    refinement = BriefRefinementResult(
        schema_version="1.0",
        refinement_id=refinement_id,
        seed_solution_id=request.seed_solution_id,
        sequence_group_id=request.sequence_group_id,
        input_copy_count=request.input_copy_count,
        tool_version=manifest.phenix_version,
        execution_status=(
            ExecutionStatus.COMPLETED_WARNING
            if refinement_success and refinement_warnings
            else ExecutionStatus.COMPLETED_SUCCESS
            if refinement_success
            else ExecutionStatus.FAILED_TOOL_EXECUTION
            if completed.returncode != 0
            else ExecutionStatus.FAILED_PARSE
        ),
        initial_r_work=initial_rw,
        initial_r_free=initial_rf,
        final_r_work=final_rw,
        final_r_free=final_rf,
        rms_bonds=rms_bonds,
        rms_angles=rms_angles,
        refined_model_path=refined_model.name if refinement_success else None,
        refined_model_sha256=sha256_file(refined_model) if refinement_success else None,
        refined_mtz_path=refined_mtz.name if refinement_success else None,
        refined_mtz_sha256=sha256_file(refined_mtz) if refinement_success else None,
        map_path=map_path.name if refinement_success else None,
        map_sha256=sha256_file(map_path) if refinement_success else None,
        command_pointer=command_path.name,
        raw_log_pointer=refine_log.name,
        warnings=tuple(refinement_warnings),
    )
    refinement_json, refinement_jsonl = _write_result(
        outdir / "brief_refinement_result.json", refinement
    )
    sequence_id = content_id(
        "seqmap_", {"refinement_id": refinement_id, "protocol": _PROTOCOL_VERSION}
    )
    sequence_log = outdir / "phenix.sequence_from_map.log"
    sequence_output_model = outdir / "sequence_from_map.pdb"
    sequence_args: list[str] = []
    sequence_completed: subprocess.CompletedProcess[bytes] | None = None
    if refinement_success:
        sequence_args = [
            "phenix.sequence_from_map",
            f"input_files.map_file={map_path}",
            f"input_files.model_file={refined_model}",
            f"input_files.multiple_seq_file={catalogue_fasta}",
            f"crystal_info.resolution={request.resolution:g}",
            f"output_files.pdb_out={sequence_output_model.name}",
            "control.verbose=True",
        ]
        command_record["sequence_arguments"] = sequence_args
        atomic_write_json(command_path, command_record)
        _LOGGER.info(
            "sequence-from-map started",
            extra={
                "refinement_id": refinement_id,
                "catalogue_group_count": len(groups),
            },
        )
        sequence_completed = capture_from_manifest(
            manifest_path,
            sequence_args,
            working_directory=outdir,
            timeout_seconds=request.timeout_seconds,
        )
        atomic_write_text(sequence_log, _combined_log(sequence_completed))
    else:
        atomic_write_text(
            sequence_log, "sequence-from-map skipped: refinement failed\n"
        )
    sequence_text = sequence_log.read_text(encoding="utf-8")
    candidates: tuple[SequenceMapCandidate, ...] = ()
    best = mean = sd = best_z = None
    sequence_warnings: list[str] = []
    sequence_status = ExecutionStatus.SKIPPED_INELIGIBLE
    if sequence_completed is not None:
        if sequence_completed.returncode != 0:
            sequence_status = ExecutionStatus.FAILED_TOOL_EXECUTION
        else:
            candidates, best, mean, sd, best_z = _sequence_candidates(
                sequence_text,
                refinement_id=refinement_id,
                groups=group_by_id,
                crosswalk=crosswalk,
            )
            sequence_status = (
                ExecutionStatus.COMPLETED_HIT
                if candidates
                else ExecutionStatus.COMPLETED_NO_HIT
            )
            if len(candidates) < len(groups):
                sequence_warnings.append("some_catalogue_groups_received_no_score")
    sequence = SequenceMapResult(
        schema_version="1.0",
        sequence_assessment_id=sequence_id,
        refinement_id=refinement_id,
        seed_solution_id=request.seed_solution_id,
        execution_status=sequence_status,
        tool_version=manifest.phenix_version,
        complete_catalogue_group_count=len(groups),
        scored_group_count=len(candidates),
        candidates=candidates,
        best_score=best,
        mean_score=mean,
        score_sd=sd,
        best_score_z=best_z,
        command_pointer=command_path.name,
        raw_log_pointer=sequence_log.name,
        output_model_path=sequence_output_model.name
        if sequence_output_model.is_file()
        else None,
        output_model_sha256=sha256_file(sequence_output_model)
        if sequence_output_model.is_file()
        else None,
        warnings=tuple(sequence_warnings),
    )
    sequence_json, sequence_jsonl = _write_result(
        outdir / "sequence_map_result.json", sequence
    )
    _LOGGER.info(
        "T12 candidate finished",
        extra={
            "refinement_id": refinement_id,
            "refinement_status": refinement.execution_status.value,
            "sequence_status": sequence.execution_status.value,
            "scored_group_count": len(candidates),
        },
    )
    return T12RunOutput(
        refinement=refinement,
        sequence=sequence,
        refinement_json=refinement_json,
        refinement_jsonl=refinement_jsonl,
        sequence_json=sequence_json,
        sequence_jsonl=sequence_jsonl,
        command_json=command_path,
    )
