"""Run one Phase III multi-fixed-component Phaser expansion.

The adapter accepts two to five component-only coordinates already placed in
one parent frame, preserving each component's original Phaser identity/error
model. It fixes every existing component at the origin and searches only the
next ordered component. The output retains raw placement, packing, TFZ, and
incremental-LLG evidence but can never assert sequence or composition identity.

Inputs are one strict JSON manifest, complete catalogue sequence groups, one
preflight-qualified MTZ, and one executable-hashed Phenix manifest. Outputs are
the resolved PHIL file, command record, raw logs, optional combined PDB/MTZ,
and one typed result. Tool/parse/no-hit states remain distinct. The content ID
binds every sequence, coordinate, uncertainty, MTZ, runtime, and parameter.

Focused coverage lives in ``tests/unit/test_multi_fixed_phaser.py``. A real
installed-runtime 9ECN control is required before this adapter may become the
general B--F application execution boundary.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_digest, canonical_json_text, content_id
from genome_to_diffraction.mr.phaser import (
    PhaserInputError,
    PhaserParseError,
    parse_completed_phaser_outputs,
    read_phaser_evidence_text,
    read_phaser_solution_metrics,
)
from genome_to_diffraction.phenix.runtime import (
    capture_from_manifest,
    validate_manifest_environment,
)
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    PositiveInt,
    Sha256Hex,
)
from genome_to_diffraction.schemas.results import (
    MtzPreflightRecord,
    PreflightDecision,
    SequenceGroupRecord,
)
from genome_to_diffraction.schemas.v2.composition import ComponentLabel
from genome_to_diffraction.schemas.v2.diffraction import (
    DiffractionSelection,
    diffraction_dataset_id,
)
from genome_to_diffraction.status import ExecutionStatus
from genome_to_diffraction.time import utc_now_iso

_ADAPTER_VERSION = "phenix-multi-fixed-joint-component-v2-diffraction"
_INPUT_VERSION = "multi-fixed-component-search-input-v2"
_ROOT = "PHASER"
_LABELS = ("A", "B", "C", "D", "E", "F")
_PRIMARY_LLG = 100.0
_PRIMARY_TFZ = 10.0
_FALLBACK_LLG = 50.0
_FALLBACK_TFZ = 5.0
_NO_COMPLETE_COMPOSITION = re.compile(
    r"^\s*\*\*\s+Sorry\s+-\s+No solution with all components\s*$",
    re.I | re.M,
)
_INPUT_SOLUTION_NOT_EXTENDED = re.compile(
    r"^\s*\*\*\s+Search did not extend input solution with new components\s*$",
    re.I | re.M,
)
_SUCCESSFUL_EXIT = re.compile(r"^\s*EXIT STATUS:\s+SUCCESS\s*$", re.I | re.M)

type _ScoreCohort = Literal["primary", "fallback", "below_threshold"]


class FixedSearchComponent(ContractModel):
    """One component-only coordinate fixed in the parent frame."""

    schema_version: Literal["2.0"]
    label: ComponentLabel
    sequence_group_id: NonEmptyString
    model_id: NonEmptyString
    model_sha256: Sha256Hex
    coordinate_path: NonEmptyString
    coordinate_sha256: Sha256Hex
    requested_copy_count: PositiveInt
    observed_copy_count: PositiveInt
    phaser_identity_fraction: float = Field(gt=0, le=1)
    model_uncertainty_source: NonEmptyString
    model_uncertainty_evidence_sha256: Sha256Hex

    @model_validator(mode="after")
    def _validate_copies(self) -> Self:
        if self.observed_copy_count != self.requested_copy_count:
            raise ValueError("fixed component lacks every requested copy")
        return self


class CandidateSearchComponent(ContractModel):
    """The only component searched in this expansion attempt."""

    schema_version: Literal["2.0"]
    label: ComponentLabel
    sequence_group_id: NonEmptyString
    model_id: NonEmptyString
    model_sha256: Sha256Hex
    model_path: NonEmptyString
    requested_copy_count: PositiveInt
    phaser_identity_fraction: float = Field(gt=0, le=1)
    model_uncertainty_source: NonEmptyString
    model_uncertainty_evidence_sha256: Sha256Hex


class MultiFixedSearchManifest(ContractModel):
    """Strict path-bearing execution manifest for one dependent expansion."""

    schema_version: Literal["2.0"]
    adapter_version: Literal["multi-fixed-component-search-input-v2"]
    crystal_id: NonEmptyString
    diffraction_selection: DiffractionSelection
    parent_solution_id: NonEmptyString
    parent_combined_llg: float
    fixed_components: tuple[FixedSearchComponent, ...] = Field(
        min_length=2,
        max_length=5,
    )
    candidate: CandidateSearchComponent

    @model_validator(mode="after")
    def _validate_order(self) -> Self:
        if not math.isfinite(self.parent_combined_llg):
            raise ValueError("parent combined LLG must be finite")
        labels = tuple(item.label for item in self.fixed_components)
        if labels != _LABELS[: len(labels)]:
            raise ValueError("fixed components must be the ordered A--F prefix")
        if self.candidate.label != _LABELS[len(labels)]:
            raise ValueError("candidate is not the next ordered component")
        groups = tuple(item.sequence_group_id for item in self.fixed_components)
        if (
            len(groups) != len(set(groups))
            or self.candidate.sequence_group_id in groups
        ):
            raise ValueError("multi-fixed search repeats a sequence group")
        if self.diffraction_selection.crystal_id != self.crystal_id:
            raise ValueError("multi-fixed diffraction selection differs")
        return self


class MultiFixedSearchResult(ContractModel):
    """Terminal evidence for one multi-fixed search without a scientific claim."""

    schema_version: Literal["2.0"]
    adapter_version: Literal["phenix-multi-fixed-joint-component-v2-diffraction"]
    result_id: NonEmptyString
    search_id: NonEmptyString
    crystal_id: NonEmptyString
    tool_version: NonEmptyString
    input_manifest_sha256: Sha256Hex
    fixed_component_labels: tuple[ComponentLabel, ...] = Field(min_length=2)
    candidate_component_label: ComponentLabel
    requested_candidate_copy_count: PositiveInt
    execution_status: ExecutionStatus
    parent_combined_llg: float
    combined_llg: float | None = None
    incremental_llg: float | None = None
    candidate_tfz: float | None = None
    solution_count: int = Field(ge=0)
    top_solution_packed: bool
    fixed_components_observed: bool
    candidate_placement_count: int = Field(ge=0)
    candidate_placement_observed: bool
    score_cohort: Literal["primary", "fallback", "below_threshold"] | None = None
    combined_coordinate_path: str | None = None
    combined_coordinate_sha256: Sha256Hex | None = None
    output_mtz_path: str | None = None
    output_mtz_sha256: Sha256Hex | None = None
    mtz_sha256: Sha256Hex
    raw_log_pointer: NonEmptyString
    command_pointer: NonEmptyString
    parameters_pointer: NonEmptyString
    scientific_status: Literal["search_evidence_only"] = "search_evidence_only"
    exact_identity_claimed: Literal[False] = False
    complete_composition_claimed: Literal[False] = False
    warnings: tuple[str, ...] = ()
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def _validate_result(self) -> Self:
        metrics = (self.combined_llg, self.incremental_llg, self.candidate_tfz)
        if any(value is None for value in metrics) != all(
            value is None for value in metrics
        ):
            raise ValueError("multi-fixed metrics must be supplied together")
        if (
            self.combined_llg is not None
            and self.incremental_llg is not None
            and not math.isclose(
                self.incremental_llg,
                self.combined_llg - self.parent_combined_llg,
                rel_tol=1e-10,
                abs_tol=1e-8,
            )
        ):
            raise ValueError("multi-fixed incremental LLG is inconsistent")
        observed = self.fixed_components_observed and (
            self.candidate_placement_count == self.requested_candidate_copy_count
        )
        if self.candidate_placement_observed != observed:
            raise ValueError("candidate placement flag differs from markers")
        assets = (
            self.combined_coordinate_path,
            self.combined_coordinate_sha256,
            self.output_mtz_path,
            self.output_mtz_sha256,
        )
        if self.execution_status is ExecutionStatus.COMPLETED_HIT:
            if self.solution_count < 1 or any(value is None for value in assets):
                raise ValueError("completed multi-fixed hit lacks assets")
            if self.combined_llg is None or self.score_cohort is None:
                raise ValueError("completed multi-fixed hit lacks metrics")
        else:
            if self.solution_count != 0 or any(value is not None for value in assets):
                raise ValueError("non-hit multi-fixed result contains assets")
            if any(value is not None for value in metrics):
                raise ValueError("non-hit multi-fixed result contains metrics")
            if self.top_solution_packed or self.candidate_placement_observed:
                raise ValueError("non-hit multi-fixed result claims placement")
        return self


def _read_jsonl[T: ContractModel](
    path: Path,
    model: type[T],
    *,
    label: str,
) -> tuple[T, ...]:
    records: list[T] = []
    with path.resolve(strict=True).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(model.model_validate_json(line))
            except ValueError as error:
                raise PhaserInputError(
                    f"invalid {label} at line {line_number}"
                ) from error
    if not records:
        raise PhaserInputError(f"{label} input is empty")
    return tuple(records)


def _resolve_path(root: Path, value: str, *, label: str, digest: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or sha256_file(resolved, progress=False) != digest:
        raise PhaserInputError(f"{label} checksum differs")
    return resolved


def _score_cohort(delta: float, tfz: float) -> _ScoreCohort:
    if delta > _PRIMARY_LLG and tfz > _PRIMARY_TFZ:
        return "primary"
    if delta > _FALLBACK_LLG and tfz > _FALLBACK_TFZ:
        return "fallback"
    return "below_threshold"


def _parameters(
    manifest: MultiFixedSearchManifest,
    fixed_paths: tuple[Path, ...],
    candidate_path: Path,
    fasta_paths: dict[str, Path],
    mtz: Path,
    labels: str,
    threads: int,
) -> str:
    selection = manifest.diffraction_selection
    composition = "\n".join(
        "    chain {\n"
        "      chain_type = protein\n"
        "      comp_type = sequence_file\n"
        f"      sequence_file = {json.dumps(str(fasta_paths[item.label]))}\n"
        f"      num = {item.requested_copy_count}\n"
        "    }"
        for item in (*manifest.fixed_components, manifest.candidate)
    )
    fixed = "\n".join(
        "  ensemble {\n"
        f"    model_id = fixed_{item.label}\n"
        "    solution_at_origin = True\n"
        "    coordinates {\n"
        f"      pdb = {json.dumps(str(path))}\n"
        f"      identity = {item.phaser_identity_fraction:.12g}\n"
        "    }\n"
        "  }"
        for item, path in zip(manifest.fixed_components, fixed_paths, strict=True)
    )
    candidate = manifest.candidate
    symmetry = (
        "  crystal_symmetry {\n"
        f"    space_group = {json.dumps(selection.selected_space_group)}\n"
        "  }\n"
    )
    resolution = (
        "    resolution {\n"
        f"      low = {selection.resolution_low_a:.12g}\n"
        f"      high = {selection.resolution_high_a:.12g}\n"
        "    }\n"
    )
    return f"""phaser {{
  mode = MR_AUTO
  hklin = {json.dumps(str(mtz))}
  labin = {labels}
{symmetry}  composition {{
{composition}
  }}
{fixed}
  ensemble {{
    model_id = search_{candidate.label}
    coordinates {{
      pdb = {json.dumps(str(candidate_path))}
      identity = {candidate.phaser_identity_fraction:.12g}
    }}
  }}
  search {{
    ensembles = search_{candidate.label}
    copies = {candidate.requested_copy_count}
  }}
  keywords {{
    general {{
      root = {_ROOT}
      jobs = {threads}
      xyzout = True
      xyzout_ensemble = True
      keywords = True
    }}
    sgalternative {{ select = none }}
{resolution}
  }}
}}
"""


def run_multi_fixed_search(
    *,
    manifest_path: Path,
    sequence_groups_jsonl: Path,
    preflight_jsonl: Path,
    mtz_path: Path,
    phenix_manifest: Path,
    output_directory: Path,
    threads: int = 1,
    timeout_seconds: float | None = None,
) -> MultiFixedSearchResult:
    """Execute one multi-fixed expansion and retain claim-free evidence."""

    if threads < 1 or (timeout_seconds is not None and timeout_seconds <= 0):
        raise ValueError("threads and optional timeout must be positive")
    manifest_file = manifest_path.resolve(strict=True)
    manifest = MultiFixedSearchManifest.model_validate_json(manifest_file.read_bytes())
    manifest_sha256 = sha256_file(manifest_file, progress=False)
    root = manifest_file.parent
    fixed_paths = tuple(
        _resolve_path(
            root,
            item.coordinate_path,
            label=f"fixed component {item.label}",
            digest=item.coordinate_sha256,
        )
        for item in manifest.fixed_components
    )
    candidate_path = _resolve_path(
        root,
        manifest.candidate.model_path,
        label=f"candidate component {manifest.candidate.label}",
        digest=manifest.candidate.model_sha256,
    )
    groups = {
        item.sequence_group_id: item
        for item in _read_jsonl(
            sequence_groups_jsonl,
            SequenceGroupRecord,
            label="sequence group",
        )
    }
    required_groups = {item.sequence_group_id for item in manifest.fixed_components} | {
        manifest.candidate.sequence_group_id
    }
    if set(groups) != required_groups:
        raise PhaserInputError("sequence groups differ from the complete component set")
    preflights = _read_jsonl(
        preflight_jsonl,
        MtzPreflightRecord,
        label="MTZ preflight",
    )
    matches = tuple(
        item for item in preflights if item.crystal_id == manifest.crystal_id
    )
    if len(matches) != 1:
        raise PhaserInputError("multi-fixed search lacks one exact preflight")
    preflight = matches[0]
    if (
        preflight.decision is PreflightDecision.FAIL
        or preflight.selected_observation_labels is None
    ):
        raise PhaserInputError("multi-fixed preflight is not executable")
    selection = manifest.diffraction_selection
    if (
        selection.diffraction_dataset_id
        != diffraction_dataset_id(
            crystal_id=manifest.crystal_id,
            mtz_sha256=preflight.mtz_sha256,
        )
        or selection.mtz_sha256 != preflight.mtz_sha256
        or selection.preflight_id != preflight.preflight_id
        or selection.preflight_record_sha256 != canonical_digest(preflight)
        or selection.observation_dataset_id != preflight.selected_observation_dataset_id
        or selection.observation_labels
        != tuple(
            label.strip() for label in preflight.selected_observation_labels.split(",")
        )
        or selection.selected_space_group != preflight.space_group
        or selection.resolution_low_a != preflight.resolution_low_a
        or selection.resolution_high_a != preflight.resolution_high_a
    ):
        raise PhaserInputError(
            "multi-fixed diffraction selection differs from preflight"
        )
    mtz = mtz_path.resolve(strict=True)
    mtz_sha256 = sha256_file(mtz, progress=False)
    if mtz_sha256 != preflight.mtz_sha256:
        raise PhaserInputError("multi-fixed MTZ differs from preflight")
    runtime = validate_manifest_environment(phenix_manifest.resolve(strict=True))
    runtime_sha256 = sha256_file(phenix_manifest.resolve(strict=True), progress=False)
    output = output_directory.absolute()
    if output.exists() and any(output.iterdir()):
        raise PhaserInputError("multi-fixed output directory is not empty")
    output.mkdir(parents=True, exist_ok=True)
    fasta_paths: dict[str, Path] = {}
    for component in (*manifest.fixed_components, manifest.candidate):
        group = groups[component.sequence_group_id]
        fasta = output / f"component_{component.label}.fasta"
        atomic_write_text(fasta, f">{group.sequence_group_id}\n{group.sequence}\n")
        fasta_paths[component.label] = fasta
    parameters = output / "component_search.eff"
    atomic_write_text(
        parameters,
        _parameters(
            manifest,
            fixed_paths,
            candidate_path,
            fasta_paths,
            mtz,
            preflight.selected_observation_labels,
            threads,
        ),
    )
    parameters_sha256 = sha256_file(parameters, progress=False)
    identity = {
        "adapter_version": _ADAPTER_VERSION,
        "manifest_sha256": manifest_sha256,
        "fixed_coordinate_sha256s": [
            item.coordinate_sha256 for item in manifest.fixed_components
        ],
        "candidate_model_sha256": manifest.candidate.model_sha256,
        "mtz_sha256": mtz_sha256,
        "diffraction_selection_id": selection.diffraction_selection_id,
        "preflight_record_sha256": canonical_digest(preflight),
        "observation_labels": selection.observation_labels,
        "parameters_sha256": parameters_sha256,
        "phenix_manifest_sha256": runtime_sha256,
        "threads": threads,
    }
    search_id = content_id("multifixed_", identity)
    command = output / "phaser_command.json"
    arguments = ["phenix.phaser", str(parameters)]
    atomic_write_json(
        command,
        {
            "schema_version": "2.0",
            "adapter_version": _ADAPTER_VERSION,
            "created_at": utc_now_iso(),
            "search_id": search_id,
            "arguments": arguments,
            "parameters_sha256": sha256_file(parameters, progress=False),
            "input_manifest_sha256": manifest_sha256,
            **identity,
        },
    )
    try:
        completed = capture_from_manifest(
            phenix_manifest,
            arguments,
            working_directory=output,
            timeout_seconds=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        completed = subprocess.CompletedProcess(arguments, 124, b"", b"timed out")
    capture_log = output / "phenix.phaser.capture.log"
    atomic_write_bytes(capture_log, completed.stdout + completed.stderr)
    native_log = output / f"{_ROOT}.log"
    raw_log = native_log if native_log.is_file() else capture_log
    status = ExecutionStatus.FAILED_TOOL_EXECUTION
    combined_llg = incremental_llg = candidate_tfz = None
    solution_count = candidate_count = 0
    packed = fixed_observed = candidate_observed = False
    cohort: _ScoreCohort | None = None
    coordinate_path = coordinate_sha = result_mtz_path = result_mtz_sha = None
    warnings: list[str] = []
    rejection: str | None = None
    tool_version = runtime.phenix_version
    if completed.returncode != 0:
        rejection = (
            "phenix.phaser_timeout"
            if completed.returncode == 124
            else f"phenix.phaser_exit_{completed.returncode}"
        )
    else:
        try:
            text = read_phaser_evidence_text(raw_log)
            if (
                _NO_COMPLETE_COMPOSITION.search(text)
                and _INPUT_SOLUTION_NOT_EXTENDED.search(text)
                and _SUCCESSFUL_EXIT.search(text)
            ):
                status = ExecutionStatus.COMPLETED_NO_HIT
                rejection = "phaser_reported_no_component_extension"
            else:
                parsed = parse_completed_phaser_outputs(text, output)
                warnings.extend(parsed.parser_warnings)
                if parsed.phaser_version:
                    tool_version = (
                        f"Phenix {runtime.phenix_version}; "
                        f"Phaser {parsed.phaser_version}"
                    )
                if parsed.solution_count == 0:
                    status = ExecutionStatus.COMPLETED_NO_HIT
                    rejection = "phaser_reported_no_component_extension"
                else:
                    coordinate = output / f"{_ROOT}.1.pdb"
                    result_mtz = output / f"{_ROOT}.1.mtz"
                    if not coordinate.is_file() or not result_mtz.is_file():
                        raise PhaserParseError("multi-fixed hit lacks combined assets")
                    combined_llg, candidate_tfz, _, _ = read_phaser_solution_metrics(
                        parsed,
                        coordinate,
                    )
                    if combined_llg is None or candidate_tfz is None:
                        raise PhaserParseError("multi-fixed hit lacks final metrics")
                    coordinate_text = read_phaser_evidence_text(coordinate)
                    fixed_observed = all(
                        re.search(
                            rf"^REMARK ENSEMBLE\s+fixed_{item.label}(?:\s|$)",
                            coordinate_text,
                            re.I | re.M,
                        )
                        is not None
                        for item in manifest.fixed_components
                    )
                    candidate_count = len(
                        re.findall(
                            rf"^REMARK ENSEMBLE\s+search_"
                            rf"{manifest.candidate.label}(?:\s|$)",
                            coordinate_text,
                            re.I | re.M,
                        )
                    )
                    candidate_observed = fixed_observed and (
                        candidate_count == manifest.candidate.requested_copy_count
                    )
                    incremental_llg = combined_llg - manifest.parent_combined_llg
                    solution_count = parsed.solution_count
                    packed = parsed.packed_solution_count > 0
                    cohort = _score_cohort(incremental_llg, candidate_tfz)
                    coordinate_path = coordinate.name
                    coordinate_sha = sha256_file(coordinate, progress=False)
                    result_mtz_path = result_mtz.name
                    result_mtz_sha = sha256_file(result_mtz, progress=False)
                    status = ExecutionStatus.COMPLETED_HIT
                    if not fixed_observed:
                        warnings.append(
                            "combined_solution_lacks_fixed_component_markers"
                        )
                    if not candidate_observed:
                        warnings.append("combined_solution_lacks_candidate_markers")
                    if not packed:
                        warnings.append("component_solution_not_packing_supported")
                    if cohort == "below_threshold":
                        warnings.append("component_scores_below_fallback_threshold")
        except PhaserParseError as error:
            status = ExecutionStatus.FAILED_PARSE
            rejection = str(error)
    result_content = {
        "adapter_version": _ADAPTER_VERSION,
        "search_id": search_id,
        "crystal_id": manifest.crystal_id,
        "input_manifest_sha256": manifest_sha256,
        "diffraction_selection_id": selection.diffraction_selection_id,
        "preflight_record_sha256": canonical_digest(preflight),
        "observation_labels": selection.observation_labels,
        "parameters_sha256": parameters_sha256,
        "execution_status": status,
        "combined_coordinate_sha256": coordinate_sha,
        "output_mtz_sha256": result_mtz_sha,
    }
    result = MultiFixedSearchResult(
        schema_version="2.0",
        adapter_version=_ADAPTER_VERSION,
        result_id=content_id("multifixedresult_", result_content),
        search_id=search_id,
        crystal_id=manifest.crystal_id,
        tool_version=tool_version,
        input_manifest_sha256=manifest_sha256,
        fixed_component_labels=tuple(item.label for item in manifest.fixed_components),
        candidate_component_label=manifest.candidate.label,
        requested_candidate_copy_count=manifest.candidate.requested_copy_count,
        execution_status=status,
        parent_combined_llg=manifest.parent_combined_llg,
        combined_llg=combined_llg,
        incremental_llg=incremental_llg,
        candidate_tfz=candidate_tfz,
        solution_count=solution_count,
        top_solution_packed=packed,
        fixed_components_observed=fixed_observed,
        candidate_placement_count=candidate_count,
        candidate_placement_observed=candidate_observed,
        score_cohort=cohort,
        combined_coordinate_path=coordinate_path,
        combined_coordinate_sha256=coordinate_sha,
        output_mtz_path=result_mtz_path,
        output_mtz_sha256=result_mtz_sha,
        mtz_sha256=mtz_sha256,
        raw_log_pointer=raw_log.name,
        command_pointer=command.name,
        parameters_pointer=parameters.name,
        warnings=tuple(warnings),
        rejection_reason=rejection,
    )
    atomic_write_json(
        output / "component_search_result.json", result.model_dump(mode="json")
    )
    atomic_write_text(
        output / "component_search_result.jsonl",
        f"{canonical_json_text(result)}\n",
    )
    return result


__all__ = [
    "CandidateSearchComponent",
    "FixedSearchComponent",
    "MultiFixedSearchManifest",
    "MultiFixedSearchResult",
    "run_multi_fixed_search",
]
