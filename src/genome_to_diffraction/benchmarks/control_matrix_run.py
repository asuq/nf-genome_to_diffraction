"""Execute the fixed 23-case prokaryotic homomer benchmark on Viper.

The adapter runs one operational same-structure positive model for each of 11
truth-labelled homomers and seven independent size-matched wrong models.  Every
packed positive advances sequentially towards its expected ASU count (1, 2, 3,
4, or 6), retaining each parent and attempted child.  The two target-absent,
two wrong-catalogue, and one known-heteromer cases are typed identity or model-
assumption boundaries and do not fabricate molecular-replacement searches.

Outputs retain all raw first-copy, additional-copy, refinement, and sequence
records plus one result per suite case.  Candidate-level tool failures remain
evidence; malformed imports and checksum/contract failures abort.  The cache
identity is the imported matrix manifest and Phenix manifest.  Unit tests cover
input construction and truth classification; real acceptance requires Viper
with the licensed Phenix runtime.
"""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from genome_to_diffraction.benchmarks.control_slice_run import (
    ControlSliceRunError,
    _object,
    _pdb_sequence,
    _review_seed,
    _target_fasta,
)
from genome_to_diffraction.benchmarks.mr_controls import _model_record
from genome_to_diffraction.catalogue.mass import MASS_METHOD, assess_mass
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.diffraction.preflight import (
    PreflightRequest,
    preflight_crystals,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.mr.add_copy import (
    AddCopyRunRequest,
    AddCopySeriesOutput,
    run_additional_copy_series,
)
from genome_to_diffraction.mr.phaser import (
    PhaserRunOutput,
    PhaserRunRequest,
    run_first_copy_phaser,
)
from genome_to_diffraction.refinement.brief import (
    T12RunOutput,
    T12RunRequest,
    run_t12_candidate,
)
from genome_to_diffraction.schemas.manifests import PrototypeProfile
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    MtzPreflightRecord,
    ProcessedModelRecord,
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.status import ExecutionStatus
from genome_to_diffraction.time import utc_now_iso

_ADAPTER_VERSION = "public-homomer-matrix-run-v1"
_EXPECTED_CASE_KIND_COUNTS = {
    "positive": 11,
    "wrong_model_negative": 7,
    "target_absent_negative": 2,
    "wrong_catalogue_negative": 2,
    "assumption_violation": 1,
}


class ControlMatrixRunError(ControlSliceRunError):
    """The fixed matrix import or scientific relationship changed."""


@dataclass(frozen=True, slots=True)
class ControlMatrixRunRequest:
    """Fixed imported matrix inputs and bounded Viper resources."""

    import_root: Path
    phenix_manifest: Path
    output_directory: Path
    threads: int = 64
    progress: bool = True
    skip_xtriage: bool = False


@dataclass(frozen=True, slots=True)
class ControlMatrixRunOutput:
    """Stable aggregate evidence paths for the complete matrix attempt."""

    summary_json: Path
    case_results_jsonl: Path
    first_copy_results_jsonl: Path
    additional_copy_results_jsonl: Path
    refinement_results_jsonl: Path
    sequence_results_jsonl: Path
    first_copy_attempt_count: int
    additional_copy_attempt_count: int
    refinement_attempt_count: int


@dataclass(frozen=True, slots=True)
class _RuntimeInputs:
    groups: Path
    sources: Path
    models: Path
    model_manifest: Path
    hypotheses: tuple[MrHypothesis, ...]


def _mapping(record: object, *, label: str) -> dict[str, object]:
    if not isinstance(record, dict):
        raise ControlMatrixRunError(f"matrix manifest lacks {label}")
    return cast(dict[str, object], record)


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ControlMatrixRunError(f"{label} must be a positive integer")
    return value


def _write_runtime_inputs(
    root: Path,
    manifest: dict[str, object],
    preflights: tuple[MtzPreflightRecord, ...],
    output: Path,
) -> _RuntimeInputs:
    positives = _mapping(manifest.get("positive_controls"), label="positive controls")
    wrong_models = _mapping(
        manifest.get("wrong_model_controls"), label="wrong-model controls"
    )
    preflight_by_id = {record.crystal_id: record for record in preflights}
    groups: list[SequenceGroupRecord] = []
    sources: list[SourceProteinRecord] = []
    models: list[ProcessedModelRecord] = []
    hypotheses: list[MrHypothesis] = []
    model_entries: list[dict[str, object]] = []
    model_root = output / "models"
    hypothesis_root = output / "hypotheses"
    model_root.mkdir(parents=True)
    hypothesis_root.mkdir()

    positive_records: dict[str, dict[str, object]] = {}
    for control_id, raw_record in positives.items():
        if not isinstance(control_id, str):
            raise ControlMatrixRunError("positive control ID is invalid")
        record = _mapping(raw_record, label=f"positive {control_id}")
        positive_records[control_id] = record
        target_sha = str(record["target_sequence_sha256"])
        header, sequence = _target_fasta(
            root / f"controls/{control_id}/proteome.faa", target_sha
        )
        mass = assess_mass(sequence)
        if mass.exact_da is None:
            raise ControlMatrixRunError("fixed target sequence lacks an exact mass")
        group_id = f"seq_{target_sha}"
        groups.append(
            SequenceGroupRecord(
                schema_version="1.0",
                sequence_group_id=group_id,
                sha256=target_sha,
                sequence=sequence,
                length_aa=len(sequence),
                molecular_mass_da=mass.exact_da,
                mass_method=MASS_METHOD,
                residue_policy=mass.residue_policy,
                source_record_count=1,
                quality_flags=mass.quality_flags,
            )
        )
        protein_id = str(record["target_protein_id"])
        sources.append(
            SourceProteinRecord(
                schema_version="1.0",
                source_record_id=content_id(
                    "src_", {"control_id": control_id, "protein_id": protein_id}
                ),
                catalogue_id=str(record["catalogue_id"]),
                original_protein_id=protein_id,
                original_header=header,
                description=header,
                sequence_group_id=group_id,
                source_annotation_provider=str(record["annotation_provider"]),
            )
        )
        raw_model = _mapping(record.get("model"), label=f"model for {control_id}")
        model_name = str(raw_model["model_id"])
        source = root / str(raw_model["archive_path"])
        destination = model_root / f"{model_name}.pdb"
        shutil.copy2(source, destination)
        observed, residue_ranges, atom_count = _pdb_sequence(destination)
        if sha256_file(destination) != raw_model["sha256"]:
            raise ControlMatrixRunError("positive model checksum changed after import")
        if (
            sha256_file_bytes(observed.encode("ascii"))
            != raw_model["observed_sequence_sha256"]
        ):
            raise ControlMatrixRunError("positive observed-model sequence changed")
        mapping_id = content_id(
            "mapping_", {"control_id": control_id, "model_id": model_name}
        )
        model = _model_record(
            role="known_positive",
            coordinate_id=f"coord_{model_name}",
            model_id=model_name,
            sequence_group_id=group_id,
            model_sha256=str(raw_model["sha256"]),
            observed_sequence=observed,
            residue_ranges=residue_ranges,
            mapping_id=mapping_id,
            identity_fraction=1.0,
            negative_identity_percent=None,
            atom_count=atom_count,
        )
        models.append(model)
        model_entries.append(
            {
                "model_id": model.model_id,
                "coordinate_id": model.coordinate_id,
                "model_path": f"models/{destination.name}",
                "model_sha256": model.model_sha256,
            }
        )
        preflight = preflight_by_id.get(control_id)
        if preflight is None or preflight.selected_observation_labels is None:
            raise ControlMatrixRunError(f"usable preflight is absent: {control_id}")
        case_id = f"POS_{control_id.removeprefix('PDB_')}"
        hypotheses.append(
            MrHypothesis(
                schema_version="1.0",
                hypothesis_id=content_id("mrhyp_", {"case_id": case_id}),
                crystal_id=control_id,
                sequence_group_id=group_id,
                model_id=model.model_id,
                copy_count_expected=_positive_int(
                    record["expected_asu_copy_count"], label="expected ASU copy count"
                ),
                copy_number_to_search=1,
                space_group=preflight.space_group,
                obs_labels=preflight.selected_observation_labels,
                search_stage=MrSearchStage.FIRST_COPY,
                resource_profile=PrototypeProfile.PILOT,
                priority_features={
                    "control_case_id": case_id,
                    "control_role": "known_positive",
                    "exact_sequence_mapping": True,
                    "structural_source_class": "experimental",
                    "candidate_source_sequence_identity": 1.0,
                    "generalisation_claim": "none",
                },
                status=MrHypothesisStatus.QUEUED,
            )
        )

    for case_id, raw_case in wrong_models.items():
        if not isinstance(case_id, str):
            raise ControlMatrixRunError("wrong-model case ID is invalid")
        case = _mapping(raw_case, label=f"wrong-model case {case_id}")
        target_id = str(case["target_control_id"])
        target = positive_records[target_id]
        raw_model = _mapping(case.get("model"), label=f"wrong model {case_id}")
        source = root / str(raw_model["archive_path"])
        model_id = f"unrelated_{case_id.lower()}"
        destination = model_root / f"{model_id}.pdb"
        shutil.copy2(source, destination)
        observed, residue_ranges, atom_count = _pdb_sequence(destination)
        if sha256_file(destination) != raw_model["sha256"]:
            raise ControlMatrixRunError("wrong-model checksum changed after import")
        target_sha = str(target["target_sequence_sha256"])
        model = _model_record(
            role="deliberate_unrelated_negative",
            coordinate_id=f"coord_{model_id}",
            model_id=model_id,
            sequence_group_id=f"seq_{target_sha}",
            model_sha256=str(raw_model["sha256"]),
            observed_sequence=observed,
            residue_ranges=residue_ranges,
            mapping_id=None,
            identity_fraction=None,
            negative_identity_percent=1.0,
            atom_count=atom_count,
        )
        models.append(model)
        model_entries.append(
            {
                "model_id": model.model_id,
                "coordinate_id": model.coordinate_id,
                "model_path": f"models/{destination.name}",
                "model_sha256": model.model_sha256,
            }
        )
        preflight = preflight_by_id[target_id]
        hypotheses.append(
            MrHypothesis(
                schema_version="1.0",
                hypothesis_id=content_id("mrhyp_", {"case_id": case_id}),
                crystal_id=target_id,
                sequence_group_id=f"seq_{target_sha}",
                model_id=model.model_id,
                copy_count_expected=_positive_int(
                    target["expected_asu_copy_count"], label="expected ASU copy count"
                ),
                copy_number_to_search=1,
                space_group=preflight.space_group,
                obs_labels=preflight.selected_observation_labels,
                search_stage=MrSearchStage.FIRST_COPY,
                resource_profile=PrototypeProfile.PILOT,
                priority_features={
                    "control_case_id": case_id,
                    "control_role": "deliberate_unrelated_negative",
                    "exact_sequence_mapping": False,
                    "structural_source_class": "deliberate_unrelated_control",
                    "phaser_identity_percent": 1.0,
                    "identity_interpretation": (
                        "error_model_input_not_sequence_homology"
                    ),
                },
                status=MrHypothesisStatus.QUEUED,
            )
        )

    paths = _RuntimeInputs(
        groups=output / "sequence_groups.jsonl",
        sources=output / "source_records.jsonl",
        models=output / "processed_models.jsonl",
        model_manifest=output / "model_preparation_manifest.json",
        hypotheses=tuple(hypotheses),
    )
    atomic_write_text(
        paths.groups, "".join(f"{canonical_json_text(item)}\n" for item in groups)
    )
    atomic_write_text(
        paths.sources, "".join(f"{canonical_json_text(item)}\n" for item in sources)
    )
    atomic_write_text(
        paths.models, "".join(f"{canonical_json_text(item)}\n" for item in models)
    )
    atomic_write_json(
        paths.model_manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "entries": model_entries,
        },
    )
    for hypothesis in hypotheses:
        atomic_write_text(
            hypothesis_root / f"{hypothesis.hypothesis_id}.jsonl",
            f"{canonical_json_text(hypothesis)}\n",
        )
    atomic_write_text(
        output / "mr_hypotheses.jsonl",
        "".join(f"{canonical_json_text(item)}\n" for item in hypotheses),
    )
    return paths


def sha256_file_bytes(payload: bytes) -> str:
    """Return a SHA-256 for canonical in-memory sequence content."""

    import hashlib

    return hashlib.sha256(payload).hexdigest()


def _packed(attempt: PhaserRunOutput) -> bool:
    return (
        attempt.result.execution_status is ExecutionStatus.COMPLETED_HIT
        and attempt.result.placed_copy_count == 1
        and attempt.result.packing_summary.get("top_solution_packed") is True
        and attempt.result.solution_coordinate_path is not None
    )


def run_control_matrix(request: ControlMatrixRunRequest) -> ControlMatrixRunOutput:
    """Execute and retain the complete fixed 23-case benchmark matrix."""

    if request.threads < 8 or request.threads > 64:
        raise ControlMatrixRunError("control-matrix threads must be between 8 and 64")
    root = request.import_root.resolve(strict=True)
    manifest_path = root / "control_matrix_import_manifest.json"
    manifest = _object(manifest_path)
    case_ids = manifest.get("case_ids")
    counts = manifest.get("case_kind_counts")
    if (
        not isinstance(case_ids, list)
        or len(case_ids) != 23
        or len(set(case_ids)) != 23
        or counts != _EXPECTED_CASE_KIND_COUNTS
    ):
        raise ControlMatrixRunError("imported control matrix changed")
    positives = _mapping(manifest.get("positive_controls"), label="positive controls")
    wrong_models = _mapping(
        manifest.get("wrong_model_controls"), label="wrong-model controls"
    )
    typed_cases = _mapping(
        manifest.get("typed_boundary_cases"), label="typed boundary cases"
    )
    if len(positives) != 11 or len(wrong_models) != 7 or len(typed_cases) != 5:
        raise ControlMatrixRunError("imported matrix inventory changed")

    output = request.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    crystals = output / "crystals.json"
    atomic_write_json(
        crystals,
        {
            "schema_version": "1.0",
            "crystals": [
                {
                    "crystal_id": control_id,
                    "mtz": str(root / f"controls/{control_id}/input.mtz"),
                    "catalogue_id": str(
                        _mapping(record, label=control_id)["catalogue_id"]
                    ),
                    "obs_labels": None,
                    "free_flag_labels": None,
                    "space_group_override": None,
                    "high_resolution_override": None,
                    "low_resolution_override": None,
                    "sds_page_mass_kda": [],
                    "sds_page_condition": None,
                    "sds_page_band_roles": [],
                    "sds_page_tolerance_fraction": 0.3,
                    "allow_remote_sequence_submission": False,
                    "notes": "truth-labelled public homomer operational control",
                }
                for control_id, record in positives.items()
            ],
        },
    )
    preflight = preflight_crystals(
        PreflightRequest(
            crystal_manifest=crystals,
            output_directory=output / "preflight",
            phenix_manifest=request.phenix_manifest,
            skip_xtriage=request.skip_xtriage,
            progress=request.progress,
            xtriage_timeout_seconds=None,
        )
    )
    runtime = _write_runtime_inputs(
        root, manifest, preflight.records, output / "runtime"
    )
    hypothesis_by_id = {item.hypothesis_id: item for item in runtime.hypotheses}
    max_workers = min(7, len(runtime.hypotheses))
    threads_per_attempt = max(1, request.threads // max_workers)

    def execute_first(hypothesis: MrHypothesis) -> PhaserRunOutput:
        return run_first_copy_phaser(
            PhaserRunRequest(
                hypotheses_jsonl=(
                    output / "runtime/hypotheses" / f"{hypothesis.hypothesis_id}.jsonl"
                ),
                hypothesis_id=hypothesis.hypothesis_id,
                sequence_groups_jsonl=runtime.groups,
                processed_models_jsonl=runtime.models,
                model_preparation_manifest=runtime.model_manifest,
                preflight_jsonl=preflight.jsonl_path,
                mtz=root / f"controls/{hypothesis.crystal_id}/input.mtz",
                phenix_manifest=request.phenix_manifest,
                output_directory=output / "first-copy" / hypothesis.hypothesis_id,
                threads=threads_per_attempt,
                timeout_seconds=None,
                progress=False,
            )
        )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        attempts = tuple(executor.map(execute_first, runtime.hypotheses))
    first_results = output / "first_copy_results.jsonl"
    atomic_write_text(
        first_results,
        "".join(f"{canonical_json_text(item.result)}\n" for item in attempts),
    )

    packed_positive: list[
        tuple[PhaserRunOutput, MrHypothesis, str, Path, Path, Path]
    ] = []
    for attempt in attempts:
        hypothesis = hypothesis_by_id[attempt.result.hypothesis_id]
        if hypothesis.priority_features.get(
            "control_role"
        ) != "known_positive" or not _packed(attempt):
            continue
        solution_id, validation, review_manifest, coordinate = _review_seed(
            output, attempt
        )
        packed_positive.append(
            (attempt, hypothesis, solution_id, validation, review_manifest, coordinate)
        )

    def execute_series(
        item: tuple[PhaserRunOutput, MrHypothesis, str, Path, Path, Path],
    ) -> AddCopySeriesOutput | None:
        _, hypothesis, solution_id, validation, review_manifest, coordinate = item
        if hypothesis.copy_count_expected == 1:
            return None
        return run_additional_copy_series(
            AddCopyRunRequest(
                review_validation_json=validation,
                review_package_manifest=review_manifest,
                seed_solution_id=solution_id,
                hypotheses_jsonl=output / "runtime/mr_hypotheses.jsonl",
                sequence_groups_jsonl=runtime.groups,
                preflight_jsonl=preflight.jsonl_path,
                mtz=root / f"controls/{hypothesis.crystal_id}/input.mtz",
                search_model=coordinate,
                expected_search_model_sha256=sha256_file(coordinate),
                phenix_manifest=request.phenix_manifest,
                output_directory=output / "additional-copies" / solution_id,
                threads=threads_per_attempt,
                timeout_seconds=None,
                progress=False,
            )
        )

    with ThreadPoolExecutor(
        max_workers=min(7, max(1, len(packed_positive)))
    ) as executor:
        series_outputs = tuple(executor.map(execute_series, packed_positive))
    series_by_hypothesis = {
        item[1].hypothesis_id: series
        for item, series in zip(packed_positive, series_outputs, strict=True)
        if series is not None
    }
    additional_results = output / "additional_copy_results.jsonl"
    atomic_write_text(
        additional_results,
        "".join(
            f"{canonical_json_text(attempt.result)}\n"
            for series in series_by_hypothesis.values()
            for attempt in series.attempts
        ),
    )

    preflight_by_id = {item.crystal_id: item for item in preflight.records}

    def execute_refinement(
        item: tuple[PhaserRunOutput, MrHypothesis, str, Path, Path, Path],
    ) -> T12RunOutput:
        _, hypothesis, solution_id, _, _, first_coordinate = item
        parent_coordinate = first_coordinate
        input_copy_count = 1
        series = series_by_hypothesis.get(hypothesis.hypothesis_id)
        if series is not None:
            supported = [
                child
                for child in series.attempts
                if child.result.additional_copy_supported
                and child.result.output_coordinate_path is not None
            ]
            if supported:
                latest = supported[-1]
                parent_coordinate = latest.result_json.parent / cast(
                    str, latest.result.output_coordinate_path
                )
                input_copy_count = latest.result.best_supported_copy_count
        mtz = root / f"controls/{hypothesis.crystal_id}/input.mtz"
        pf = preflight_by_id[hypothesis.crystal_id]
        return run_t12_candidate(
            T12RunRequest(
                seed_solution_id=solution_id,
                sequence_group_id=hypothesis.sequence_group_id,
                input_copy_count=input_copy_count,
                parent_coordinate=parent_coordinate,
                parent_coordinate_sha256=sha256_file(parent_coordinate),
                parent_mtz=mtz,
                parent_mtz_sha256=sha256_file(mtz),
                observation_labels=cast(str, pf.selected_observation_labels),
                sequence_groups_jsonl=runtime.groups,
                source_records_jsonl=runtime.sources,
                resolution=pf.resolution_high_a,
                phenix_manifest=request.phenix_manifest,
                output_directory=output / "t12" / solution_id,
                threads=min(4, threads_per_attempt),
                timeout_seconds=None,
                progress=False,
            )
        )

    with ThreadPoolExecutor(
        max_workers=min(7, max(1, len(packed_positive)))
    ) as executor:
        refinements = tuple(executor.map(execute_refinement, packed_positive))
    refinement_results = output / "refinement_results.jsonl"
    sequence_results = output / "sequence_results.jsonl"
    atomic_write_text(
        refinement_results,
        "".join(f"{canonical_json_text(item.refinement)}\n" for item in refinements),
    )
    atomic_write_text(
        sequence_results,
        "".join(f"{canonical_json_text(item.sequence)}\n" for item in refinements),
    )

    attempts_by_case = {
        cast(
            str,
            hypothesis_by_id[item.result.hypothesis_id].priority_features[
                "control_case_id"
            ],
        ): item
        for item in attempts
    }
    best_copy_by_hypothesis: dict[str, int] = {}
    for item in packed_positive:
        hypothesis = item[1]
        series = series_by_hypothesis.get(hypothesis.hypothesis_id)
        best_copy_by_hypothesis[hypothesis.hypothesis_id] = (
            series.attempts[-1].result.best_supported_copy_count
            if series is not None
            else 1
        )

    case_records: list[dict[str, object]] = []
    for raw_case_id in case_ids:
        case_id = cast(str, raw_case_id)
        if case_id.startswith("POS_"):
            attempt = attempts_by_case[case_id]
            hypothesis = hypothesis_by_id[attempt.result.hypothesis_id]
            best = best_copy_by_hypothesis.get(hypothesis.hypothesis_id, 0)
            retained = _packed(attempt) and best == hypothesis.copy_count_expected
            outcome = (
                "ground_truth_retained" if retained else "ground_truth_not_retained"
            )
            detail: dict[str, object] = {
                "expected_asu_copy_count": hypothesis.copy_count_expected,
                "best_supported_copy_count": best,
                "first_copy_execution_status": attempt.result.execution_status.value,
            }
        elif case_id in wrong_models:
            attempt = attempts_by_case[case_id]
            outcome = "unrelated_model_retained_for_comparison"
            detail = {
                "first_copy_execution_status": attempt.result.execution_status.value,
                "llg": attempt.result.llg,
                "tfz": attempt.result.tfz,
                "ground_truth_displacement_allowed": False,
            }
        else:
            typed = _mapping(typed_cases[case_id], label=case_id)
            outcome = (
                "assumption_violation_abstained"
                if typed["case_kind"] == "assumption_violation"
                else "no_reportable_identity"
            )
            detail = {"real_mr_search_required": False}
        case_records.append(
            {
                "schema_version": "1.0",
                "case_id": case_id,
                "outcome": outcome,
                "all_candidates_retained": True,
                **detail,
            }
        )
    case_results = output / "control_matrix_case_results.jsonl"
    atomic_write_text(
        case_results,
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in case_records),
    )
    summary = output / "control_matrix_summary.json"
    additional_attempt_count = sum(
        len(series.attempts) for series in series_by_hypothesis.values()
    )
    atomic_write_json(
        summary,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "generated_at": utc_now_iso(),
            "suite_id": "prokaryote_homomer_workflow_v1",
            "case_count": 23,
            "positive_count": 11,
            "wrong_model_count": 7,
            "typed_boundary_count": 5,
            "first_copy_attempt_count": len(attempts),
            "additional_copy_attempt_count": additional_attempt_count,
            "refinement_attempt_count": len(refinements),
            "positive_expected_copy_counts": [1, 2, 3, 4, 6],
            "all_candidates_retained": True,
            "score_policy": "LLG/TFZ_are_ranking_annotations_only",
            "generalisation_claim": "none_operational_same_structure_controls",
            "import_manifest_sha256": sha256_file(manifest_path),
            "phenix_manifest_sha256": sha256_file(request.phenix_manifest),
            "case_results_sha256": sha256_file(case_results),
            "first_copy_results_sha256": sha256_file(first_results),
            "additional_copy_results_sha256": sha256_file(additional_results),
            "refinement_results_sha256": sha256_file(refinement_results),
            "sequence_results_sha256": sha256_file(sequence_results),
        },
    )
    return ControlMatrixRunOutput(
        summary_json=summary,
        case_results_jsonl=case_results,
        first_copy_results_jsonl=first_results,
        additional_copy_results_jsonl=additional_results,
        refinement_results_jsonl=refinement_results,
        sequence_results_jsonl=sequence_results,
        first_copy_attempt_count=len(attempts),
        additional_copy_attempt_count=additional_attempt_count,
        refinement_attempt_count=len(refinements),
    )
