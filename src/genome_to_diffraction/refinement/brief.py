"""Run the fixed T12 brief-refinement and sequence-narrowing protocol.

The adapter consumes one retained M4 parent coordinate/MTZ, the complete exact
sequence catalogue, source-record crosswalk, and verified Phenix manifest. It
runs a single conservative ``phenix.refine`` macrocycle, writes sigma-scaled
whole-cell ``2mFo-DFc`` and ``mFo-DFc`` maps, verifies both coefficient pairs in
the refined MTZ, and asks ``phenix.sequence_from_map`` to score every exact
sequence group against the ``2mFo-DFc`` map. All scores and catalogue-to-locus
ambiguity are retained. The generated sequence-assignment PDB is an
interpretation aid, not an independently refined final model.

Tool failures become typed candidate-level results; they do not discard other
finalists. The cache identity includes input/checkpoint hashes, the complete
catalogue, Phenix manifest, protocol version, resolution, and thread count.
Unit tests cover command construction, parsers, checksum rejection, and failed
tool execution. Real Phenix qualification remains mandatory on Viper.

The optional Phase III path verifies the dataset-qualified selection against
its exact preflight and requires a content-address-valid Free-R identity bound
to that selection.  The command record retains the exact Free-R label and
explicit or unresolved test-value convention.  A successful refined MTZ is
promoted only after its raw HKL-to-Free-R mapping compares exactly with the
source identity.  No Free-R convention, flag, or unqualified Phenix parameter
is inferred.
"""

import logging
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import gemmi
from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.diffraction.free_r_identity import (
    FreeRIdentityError,
    compare_free_r_membership,
    load_free_r_identity,
    verify_free_r_identity_selection,
)
from genome_to_diffraction.diffraction.selection import (
    build_diffraction_command_binding,
    load_diffraction_selection,
    verify_diffraction_selection,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.phenix.runtime import (
    capture_from_manifest,
    validate_manifest_environment,
)
from genome_to_diffraction.schemas.results import (
    BriefRefinementResult,
    MtzPreflightRecord,
    SequenceGroupRecord,
    SequenceMapCandidate,
    SequenceMapResult,
    SourceProteinRecord,
)
from genome_to_diffraction.schemas.v2.diffraction import (
    DiffractionCommandBinding,
    DiffractionCommandConsumer,
    DiffractionSelection,
    FreeRIdentity,
    FreeRMembershipComparison,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_LOGGER = logging.getLogger("genome_to_diffraction.refinement.brief")
_PROTOCOL_VERSION = "phenix-t12-brief-v5"
_PHASE3_PROTOCOL_VERSION = "phenix-t12-brief-v7-phase3-free-r-preservation"
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
    crystal_id: str | None = None
    diffraction_selection_json: Path | None = None
    preflight_jsonl: Path | None = None
    free_r_identity_json: Path | None = None
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
    free_r_comparison: FreeRMembershipComparison | None
    free_r_comparison_json: Path | None
    free_r_comparison_jsonl: Path | None


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


def _normalised_observation_labels(value: str) -> tuple[str, ...]:
    labels = tuple(item.strip() for item in value.split(",") if item.strip())
    if len(labels) not in {2, 4}:
        raise T12InputError(
            "observation labels must be one value/sigma pair or anomalous quartet"
        )
    return labels


def _resolve_phase3_diffraction(
    request: T12RunRequest,
) -> tuple[DiffractionSelection, FreeRIdentity] | None:
    supplied = (
        request.crystal_id is not None,
        request.diffraction_selection_json is not None,
        request.preflight_jsonl is not None,
        request.free_r_identity_json is not None,
    )
    if not any(supplied):
        return None
    if not all(supplied):
        raise T12InputError(
            "Phase III refinement requires crystal ID, diffraction selection, "
            "preflight, and Free-R identity"
        )
    assert request.crystal_id is not None
    assert request.diffraction_selection_json is not None
    assert request.preflight_jsonl is not None
    assert request.free_r_identity_json is not None
    selection = load_diffraction_selection(request.diffraction_selection_json)
    if selection.crystal_id != request.crystal_id:
        raise T12InputError("Phase III refinement crystal identity differs")
    preflights = _read_jsonl(
        request.preflight_jsonl,
        MtzPreflightRecord,
        label="MTZ preflight",
    )
    matching_preflights = tuple(
        preflight
        for preflight in preflights
        if preflight.crystal_id == request.crystal_id
    )
    if len(matching_preflights) != 1:
        raise T12InputError(
            "Phase III refinement requires exactly one matching MTZ preflight"
        )
    verify_diffraction_selection(selection, matching_preflights[0])
    if _normalised_observation_labels(request.observation_labels) != (
        selection.observation_labels
    ):
        raise T12InputError(
            "refinement observation labels differ from diffraction selection"
        )
    if not math.isclose(
        request.resolution,
        selection.resolution_high_a,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise T12InputError(
            "refinement high-resolution limit differs from diffraction selection"
        )
    try:
        free_r_identity = load_free_r_identity(request.free_r_identity_json)
        verify_free_r_identity_selection(free_r_identity, selection)
    except FreeRIdentityError as error:
        raise T12InputError(str(error)) from error
    return selection, free_r_identity


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


def _refine_parameters(*, threads: int, map_name: str, difference_map_name: str) -> str:
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
      mtz_label_amplitudes = 2FOFCWT
      mtz_label_phases = PH2FOFCWT
    }}
    map_coefficients {{
      map_type = mFo-DFc
      mtz_label_amplitudes = FOFCWT
      mtz_label_phases = PHFOFCWT
    }}
    map {{
      map_type = 2mFo-DFc
      format = ccp4
      file_name = {map_name}
      fill_missing_f_obs = False
      scale = sigma
      region = cell
    }}
    map {{
      map_type = mFo-DFc
      format = ccp4
      file_name = {difference_map_name}
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


def _refinement_output_paths(outdir: Path) -> tuple[Path, Path, Path, Path]:
    """Return the fixed PDB/MTZ and both explicit review-map names."""
    return (
        outdir / "brief_refine_001.pdb",
        outdir / "brief_refine_001.mtz",
        outdir / "brief_refine_2mFo-DFc.ccp4",
        outdir / "brief_refine_mFo-DFc.ccp4",
    )


def _prepare_attempt_directory(path: Path) -> Path:
    """Create or verify one empty attempt-owned output directory."""

    if path.is_symlink():
        raise T12InputError("T12 output directory cannot be a symlink")
    resolved = path.resolve()
    if resolved.exists():
        if not resolved.is_dir():
            raise T12InputError("T12 output path is not a directory")
        if any(resolved.iterdir()):
            raise T12InputError("T12 output directory is not empty")
    else:
        resolved.mkdir(parents=True)
    return resolved


def _has_required_map_coefficients(path: Path) -> bool:
    """Return whether the refined MTZ contains both review-map coefficient pairs."""

    try:
        mtz = gemmi.read_mtz_file(str(path))
    except OSError, RuntimeError, ValueError:
        return False
    columns = {column.label: column.type for column in mtz.columns}
    return all(
        columns.get(label) == type_code
        for label, type_code in (
            ("2FOFCWT", "F"),
            ("PH2FOFCWT", "P"),
            ("FOFCWT", "F"),
            ("PHFOFCWT", "P"),
        )
    )


def _observation_label_argument(labels: str) -> str:
    if not labels.strip() or "\n" in labels:
        raise T12InputError("observation_labels must be one non-empty line")
    return f"data_manager.miller_array.labels.name={labels}"


def _free_r_arguments(identity: FreeRIdentity) -> tuple[str, ...]:
    """Return the officially documented Phenix Free-R selection parameters."""

    if not identity.free_r_label.strip() or "\n" in identity.free_r_label:
        raise T12InputError("Free-R label must be one non-empty line")
    arguments = [
        f"data_manager.miller_array.labels.name={identity.free_r_label}",
        "data_manager.fmodel.xray_data.r_free_flags.required=True",
        "data_manager.fmodel.xray_data.r_free_flags.generate=False",
    ]
    if identity.test_flag_value is not None:
        arguments.append(
            "data_manager.fmodel.xray_data.r_free_flags.test_flag_value="
            f"{identity.test_flag_value}"
        )
    return tuple(arguments)


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


def _classify_sequence_output(
    text: str,
    *,
    refinement_id: str,
    groups: dict[str, SequenceGroupRecord],
    crosswalk: dict[str, tuple[tuple[str, ...], tuple[str, ...]]],
) -> tuple[
    ExecutionStatus,
    tuple[SequenceMapCandidate, ...],
    float | None,
    float | None,
    float | None,
    float | None,
    tuple[str, ...],
]:
    """Turn malformed catalogue mappings into one typed candidate-level failure."""

    try:
        candidates, best, mean, sd, best_z = _sequence_candidates(
            text,
            refinement_id=refinement_id,
            groups=groups,
            crosswalk=crosswalk,
        )
    except T12InputError:
        return (
            ExecutionStatus.FAILED_PARSE,
            (),
            None,
            None,
            None,
            None,
            ("sequence_from_map_output_failed_catalogue_validation",),
        )
    warnings = (
        ("some_catalogue_groups_received_no_score",)
        if len(candidates) < len(groups)
        else ()
    )
    return (
        ExecutionStatus.COMPLETED_HIT
        if candidates
        else ExecutionStatus.COMPLETED_NO_HIT,
        candidates,
        best,
        mean,
        sd,
        best_z,
        warnings,
    )


def _write_result(path: Path, result: BaseModel) -> tuple[Path, Path]:
    atomic_write_json(path, result.model_dump(mode="json"))
    jsonl = path.with_suffix(".jsonl")
    atomic_write_text(jsonl, canonical_json_text(result) + "\n")
    return path, jsonl


def _assess_refinement_completion(
    *,
    returncode: int,
    required_assets_present: bool,
    coefficients_valid: bool,
    final_r_work: float | None,
    final_r_free: float | None,
) -> tuple[bool, tuple[str, ...]]:
    """Classify a zero-exit refinement only after final evidence is parsed."""

    if returncode != 0:
        return False, ()
    warnings: list[str] = []
    if not required_assets_present:
        warnings.append("phenix_refine_completed_without_required_assets")
    if required_assets_present and not coefficients_valid:
        warnings.append("refined_mtz_lacks_required_2mfo_dfc_or_mfo_dfc_coefficients")
    if final_r_work is None or final_r_free is None:
        warnings.append("phenix_refine_log_lacks_final_r_work_or_r_free")
    return not warnings, tuple(warnings)


def _phase3_refinement_command_identity(
    *,
    refinement_id: str,
    refine_arguments: list[str],
    binding: DiffractionCommandBinding,
    inputs: dict[str, object],
) -> str:
    """Bind the verified diffraction selection into the refine command identity."""

    return content_id(
        "refinecmd_",
        {
            "protocol_version": _PHASE3_PROTOCOL_VERSION,
            "refinement_id": refinement_id,
            "refine_arguments": refine_arguments,
            "diffraction_command_binding_id": binding.binding_id,
            "inputs": inputs,
        },
    )


def _phase3_sequence_command_identity(
    *,
    refinement_id: str,
    sequence_arguments: list[str],
    binding: DiffractionCommandBinding,
) -> str:
    """Bind the selected high-resolution limit into sequence-from-map identity."""

    return content_id(
        "seqmapcmd_",
        {
            "protocol_version": _PHASE3_PROTOCOL_VERSION,
            "refinement_id": refinement_id,
            "sequence_arguments": sequence_arguments,
            "diffraction_command_binding_id": binding.binding_id,
        },
    )


def run_t12_candidate(request: T12RunRequest) -> T12RunOutput:
    """Run one retained finalist through fixed refinement, map, and sequence steps."""

    if request.input_copy_count < 1:
        raise T12InputError("input_copy_count must be positive")
    if request.threads < 1 or request.threads > 64:
        raise T12InputError("threads must be between 1 and 64")
    if request.resolution <= 0:
        raise T12InputError("resolution must be positive")
    phase3_diffraction = _resolve_phase3_diffraction(request)
    if phase3_diffraction is None:
        diffraction_selection = None
        free_r_identity = None
    else:
        diffraction_selection, free_r_identity = phase3_diffraction
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
    outdir = _prepare_attempt_directory(request.output_directory)
    catalogue_fasta = outdir / "exact_sequence_catalogue.fasta"
    _write_catalogue_fasta(groups, catalogue_fasta, progress=request.progress)
    protocol_version = (
        _PHASE3_PROTOCOL_VERSION
        if diffraction_selection is not None
        else _PROTOCOL_VERSION
    )
    refinement_identity: dict[str, object] = {
        "protocol": protocol_version,
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
    }
    if diffraction_selection is not None:
        refinement_identity["diffraction_selection_id"] = (
            diffraction_selection.diffraction_selection_id
        )
        assert free_r_identity is not None
        refinement_identity["free_r_identity_id"] = free_r_identity.free_r_identity_id
    refinement_id = content_id("refine_", refinement_identity)
    refined_model, refined_mtz, map_path, difference_map_path = (
        _refinement_output_paths(outdir)
    )
    params_path = outdir / "brief_refine.eff"
    atomic_write_text(
        params_path,
        _refine_parameters(
            threads=request.threads,
            map_name="brief_refine_2mFo-DFc.ccp4",
            difference_map_name="brief_refine_mFo-DFc.ccp4",
        ),
    )
    refine_args = [
        "phenix.refine",
        str(parent_coordinate),
        str(parent_mtz),
        str(params_path),
        observation_label_argument,
    ]
    if free_r_identity is not None:
        refine_args.extend(_free_r_arguments(free_r_identity))
    command_path = outdir / "t12_command.json"
    command_inputs: dict[str, object] = {
        "parent_coordinate_sha256": request.parent_coordinate_sha256,
        "parent_mtz_sha256": request.parent_mtz_sha256,
        "observation_labels": request.observation_labels,
        "catalogue_fasta_sha256": sha256_file(catalogue_fasta),
        "phenix_manifest_sha256": sha256_file(manifest_path),
    }
    command_record: dict[str, object] = {
        "schema_version": "1.0",
        "protocol_version": protocol_version,
        "refinement_id": refinement_id,
        "refine_arguments": refine_args,
        "sequence_arguments": None,
        "inputs": command_inputs,
    }
    diffraction_binding: DiffractionCommandBinding | None = None
    if diffraction_selection is not None:
        assert free_r_identity is not None
        diffraction_binding = build_diffraction_command_binding(
            consumer=DiffractionCommandConsumer.BRIEF_REFINEMENT,
            command_owner_id=refinement_id,
            selection=diffraction_selection,
            free_r_identity=free_r_identity,
        )
        command_record.update(
            {
                "schema_version": "2.0",
                "phase3_refine_command_id": _phase3_refinement_command_identity(
                    refinement_id=refinement_id,
                    refine_arguments=refine_args,
                    binding=diffraction_binding,
                    inputs=command_inputs,
                ),
                "diffraction_selection": diffraction_selection.model_dump(mode="json"),
                "diffraction_command_binding": diffraction_binding.model_dump(
                    mode="json"
                ),
                "free_r_identity": free_r_identity.model_dump(mode="json"),
                "free_r_membership_comparison_status": (
                    "pending_successful_refined_mtz"
                ),
                "free_r_membership_comparison": None,
            }
        )
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
    required_assets = (refined_model, refined_mtz, map_path, difference_map_path)
    required_assets_present = all(path.is_file() for path in required_assets)
    coefficients_valid = (
        completed.returncode == 0
        and required_assets_present
        and _has_required_map_coefficients(refined_mtz)
    )
    refinement_success, completion_warnings = _assess_refinement_completion(
        returncode=completed.returncode,
        required_assets_present=required_assets_present,
        coefficients_valid=coefficients_valid,
        final_r_work=final_rw,
        final_r_free=final_rf,
    )
    refinement_warnings = list(completion_warnings)
    free_r_comparison: FreeRMembershipComparison | None = None
    free_r_comparison_json: Path | None = None
    free_r_comparison_jsonl: Path | None = None
    if free_r_identity is not None:
        if refinement_success:
            try:
                free_r_comparison = compare_free_r_membership(
                    source=free_r_identity,
                    derived_mtz_path=refined_mtz,
                )
            except FreeRIdentityError as error:
                refinement_success = False
                refinement_warnings.append(
                    "refined_mtz_free_r_membership_comparison_failed"
                )
                command_record.update(
                    {
                        "free_r_membership_comparison_status": "failed_contract",
                        "free_r_membership_comparison_error": str(error),
                    }
                )
                _LOGGER.warning(
                    "refined MTZ failed Free-R membership comparison",
                    extra={
                        "refinement_id": refinement_id,
                        "free_r_identity_id": free_r_identity.free_r_identity_id,
                        "error": str(error),
                    },
                )
            else:
                free_r_comparison_json, free_r_comparison_jsonl = _write_result(
                    outdir / "free_r_membership_comparison.json",
                    free_r_comparison,
                )
                command_record.update(
                    {
                        "free_r_membership_comparison_status": "preserved_exact",
                        "free_r_membership_comparison": free_r_comparison.model_dump(
                            mode="json"
                        ),
                        "free_r_membership_comparison_pointer": (
                            free_r_comparison_json.name
                        ),
                    }
                )
        else:
            command_record["free_r_membership_comparison_status"] = (
                "not_attempted_refinement_incomplete"
            )
        atomic_write_json(command_path, command_record)
    if (
        refinement_success
        and final_rf is not None
        and initial_rf is not None
        and final_rf > initial_rf
    ):
        refinement_warnings.append("r_free_increased_during_brief_refinement")
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
        difference_map_path=difference_map_path.name if refinement_success else None,
        difference_map_sha256=sha256_file(difference_map_path)
        if refinement_success
        else None,
        command_pointer=command_path.name,
        raw_log_pointer=refine_log.name,
        warnings=tuple(refinement_warnings),
    )
    refinement_json, refinement_jsonl = _write_result(
        outdir / "brief_refinement_result.json", refinement
    )
    sequence_id = content_id(
        "seqmap_", {"refinement_id": refinement_id, "protocol": protocol_version}
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
        if diffraction_binding is not None:
            command_record["phase3_sequence_command_id"] = (
                _phase3_sequence_command_identity(
                    refinement_id=refinement_id,
                    sequence_arguments=sequence_args,
                    binding=diffraction_binding,
                )
            )
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
            (
                sequence_status,
                candidates,
                best,
                mean,
                sd,
                best_z,
                parsed_warnings,
            ) = _classify_sequence_output(
                sequence_text,
                refinement_id=refinement_id,
                groups=group_by_id,
                crosswalk=crosswalk,
            )
            sequence_warnings.extend(parsed_warnings)
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
        output_model_role=(
            "map_derived_sequence_assignment_hypothesis_not_independently_refined"
        ),
        input_map_type="2mFo-DFc",
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
        free_r_comparison=free_r_comparison,
        free_r_comparison_json=free_r_comparison_json,
        free_r_comparison_jsonl=free_r_comparison_jsonl,
    )
