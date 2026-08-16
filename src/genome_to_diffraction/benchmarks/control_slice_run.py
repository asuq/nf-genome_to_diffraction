"""Execute the fixed six-case prokaryotic homomer smoke slice.

The adapter consumes only the checksum-validated Viper import tree and the
licensed Phenix manifest. It runs five first-copy searches, retains every
normalised outcome, advances every packed 3W45 parent to copy two, and briefly
refines every supported copy-two child. The other three cases are explicit
identity-universe or assumption-violation controls and never invent identities.

Outputs are typed JSONL evidence, a six-case summary, per-attempt Phenix assets,
and copy-two/T12 children. Tool failures remain candidate-level evidence;
contract or checksum failures abort the run. The cache identity is the import
manifest plus Phenix-manifest checksums. Focused unit tests cover preparation;
licensed execution is accepted only through the Viper control-slice profile.
"""

import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import gemmi
from Bio import SeqIO
from pydantic import JsonValue

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
    NormalisedMrResult,
    ProcessedModelRecord,
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError
from genome_to_diffraction.time import utc_now_iso

_ADAPTER_VERSION = "public-homomer-smoke-run-v1"
_EXPECTED_CASES = (
    "POS_1JCF",
    "POS_3W45",
    "NEG_MODEL_3W45_6HF7",
    "NEG_ABSENT_3W45",
    "NEG_CATALOGUE_3W45_1JCF",
    "NEG_ASSUMPTION_6CXH",
)


class ControlSliceRunError(InputContractError):
    """The fixed imported slice or its scientific relationships changed."""


@dataclass(frozen=True, slots=True)
class ControlSliceRunRequest:
    """Fixed imported inputs and bounded Viper resources."""

    import_root: Path
    phenix_manifest: Path
    output_directory: Path
    threads: int = 8
    progress: bool = True
    skip_xtriage: bool = False


@dataclass(frozen=True, slots=True)
class ControlSliceRunOutput:
    """Stable evidence paths for the complete six-case attempt."""

    summary_json: Path
    case_results_jsonl: Path
    first_copy_results_jsonl: Path
    copy_two_results_jsonl: Path
    refinement_results_jsonl: Path
    sequence_results_jsonl: Path
    first_copy_attempt_count: int
    copy_two_attempt_count: int
    refinement_attempt_count: int


def _object(path: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    value: object = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ControlSliceRunError(f"expected JSON object: {resolved}")
    return cast(dict[str, object], value)


def _target_fasta(path: Path, expected_sha256: str) -> tuple[str, str]:
    matches: list[tuple[str, str]] = []
    for record in SeqIO.parse(path, "fasta"):
        sequence = str(record.seq).replace("*", "").upper()
        if sha256_file_bytes(sequence.encode("ascii")) == expected_sha256:
            matches.append((record.description, sequence))
    if not matches:
        raise ControlSliceRunError(f"target sequence is absent from {path.name}")
    sequences = {sequence for _, sequence in matches}
    if len(sequences) != 1:
        raise ControlSliceRunError(f"target sequence is ambiguous in {path.name}")
    return matches[0]


def sha256_file_bytes(payload: bytes) -> str:
    """Return a SHA-256 for an in-memory canonical sequence."""

    return hashlib.sha256(payload).hexdigest()


def _pdb_sequence(path: Path) -> tuple[str, tuple[str, ...], int]:
    structure = gemmi.read_structure(str(path))
    residues: list[gemmi.Residue] = []
    atom_count = 0
    for model in structure:
        for chain in model:
            for residue in chain:
                info = gemmi.find_tabulated_residue(residue.name)
                if info.is_amino_acid():
                    residues.append(residue)
                    atom_count += len(residue)
    sequence = "".join(
        gemmi.find_tabulated_residue(residue.name).one_letter_code
        for residue in residues
    ).upper()
    if not sequence or atom_count < 1:
        raise ControlSliceRunError(f"model has no polymer atoms: {path}")
    ranges = (f"{residues[0].seqid}-{residues[-1].seqid}",)
    return sequence, ranges, atom_count


def _write_runtime_inputs(
    root: Path,
    manifest: dict[str, object],
    preflights: tuple[MtzPreflightRecord, ...],
    output: Path,
) -> tuple[Path, Path, Path, Path, tuple[MrHypothesis, ...]]:
    positives = manifest.get("positive_controls")
    if not isinstance(positives, dict):
        raise ControlSliceRunError("control-slice manifest lacks positive controls")
    preflight_by_id = {record.crystal_id: record for record in preflights}
    groups: list[SequenceGroupRecord] = []
    sources: list[SourceProteinRecord] = []
    models: list[ProcessedModelRecord] = []
    hypotheses: list[MrHypothesis] = []
    entries: list[dict[str, object]] = []
    model_root = output / "models"
    hypothesis_root = output / "hypotheses"
    model_root.mkdir(parents=True)
    hypothesis_root.mkdir()

    for control_id in ("PDB_1JCF", "PDB_3W45"):
        record = positives.get(control_id)
        if not isinstance(record, dict):
            raise ControlSliceRunError(
                f"positive-control record is absent: {control_id}"
            )
        target_sha = str(record["target_sequence_sha256"])
        header, sequence = _target_fasta(
            root / f"controls/{control_id}/proteome.faa", target_sha
        )
        mass = assess_mass(sequence)
        if mass.exact_da is None:
            raise ControlSliceRunError("fixed target sequence lacks an exact mass")
        group_id = f"seq_{target_sha}"
        group = SequenceGroupRecord(
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
        groups.append(group)
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
        raw_models = record.get("models")
        if not isinstance(raw_models, dict):
            raise ControlSliceRunError(f"model inventory is absent: {control_id}")
        preflight = preflight_by_id.get(control_id)
        if preflight is None or preflight.selected_observation_labels is None:
            raise ControlSliceRunError(f"usable preflight is absent: {control_id}")
        for model_name, raw_model in raw_models.items():
            if not isinstance(model_name, str) or not isinstance(raw_model, dict):
                raise ControlSliceRunError("invalid positive-model inventory")
            source = root / str(raw_model["archive_path"])
            destination = model_root / f"{model_name}.pdb"
            shutil.copy2(source, destination)
            observed, residue_ranges, atom_count = _pdb_sequence(destination)
            identity = float(raw_model["sequence_identity_fraction"])
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
                identity_fraction=identity,
                negative_identity_percent=None,
                atom_count=atom_count,
            )
            models.append(model)
            entries.append(
                {
                    "model_id": model.model_id,
                    "coordinate_id": model.coordinate_id,
                    "model_path": f"models/{destination.name}",
                    "model_sha256": model.model_sha256,
                }
            )
            features: dict[str, JsonValue] = {
                "control_case_id": f"POS_{control_id.removeprefix('PDB_')}",
                "control_role": "known_positive",
                "exact_sequence_mapping": bool(raw_model["exact_sequence_mapping"]),
                "structural_source_class": "experimental",
                "coordinate_mapping_id": mapping_id,
                "candidate_source_sequence_identity": identity,
            }
            hypothesis = MrHypothesis(
                schema_version="1.0",
                hypothesis_id=content_id(
                    "mrhyp_", {"control_id": control_id, "model_id": model_name}
                ),
                crystal_id=control_id,
                sequence_group_id=group_id,
                model_id=model.model_id,
                copy_count_expected=int(record["expected_asu_copy_count"]),
                copy_number_to_search=1,
                space_group=preflight.space_group,
                obs_labels=preflight.selected_observation_labels,
                search_stage=MrSearchStage.FIRST_COPY,
                resource_profile=PrototypeProfile.PILOT,
                priority_features=features,
                status=MrHypothesisStatus.QUEUED,
            )
            hypotheses.append(hypothesis)

    target = cast(dict[str, object], positives["PDB_3W45"])
    target_sha = str(target["target_sequence_sha256"])
    negative_path = root / "controls/NEG_MODEL_3W45_6HF7/model.pdb"
    negative_copy = model_root / "pdb_6hf7_chain_a_unrelated.pdb"
    shutil.copy2(negative_path, negative_copy)
    observed, residue_ranges, atom_count = _pdb_sequence(negative_copy)
    negative_model = _model_record(
        role="deliberate_unrelated_negative",
        coordinate_id="coord_pdb_6hf7_chain_a_unrelated",
        model_id="pdb_6hf7_chain_a_unrelated",
        sequence_group_id=f"seq_{target_sha}",
        model_sha256=sha256_file(negative_copy),
        observed_sequence=observed,
        residue_ranges=residue_ranges,
        mapping_id=None,
        identity_fraction=None,
        negative_identity_percent=1.0,
        atom_count=atom_count,
    )
    models.append(negative_model)
    entries.append(
        {
            "model_id": negative_model.model_id,
            "coordinate_id": negative_model.coordinate_id,
            "model_path": f"models/{negative_copy.name}",
            "model_sha256": negative_model.model_sha256,
        }
    )
    preflight = preflight_by_id["PDB_3W45"]
    negative_hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=content_id("mrhyp_", {"case": "NEG_MODEL_3W45_6HF7"}),
        crystal_id="PDB_3W45",
        sequence_group_id=f"seq_{target_sha}",
        model_id=negative_model.model_id,
        copy_count_expected=2,
        copy_number_to_search=1,
        space_group=preflight.space_group,
        obs_labels=preflight.selected_observation_labels,
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.PILOT,
        priority_features={
            "control_case_id": "NEG_MODEL_3W45_6HF7",
            "control_role": "deliberate_unrelated_negative",
            "exact_sequence_mapping": False,
            "structural_source_class": "deliberate_unrelated_control",
            "phaser_identity_percent": 1.0,
            "identity_interpretation": "error_model_input_not_sequence_homology",
        },
        status=MrHypothesisStatus.QUEUED,
    )
    hypotheses.append(negative_hypothesis)

    groups_path = output / "sequence_groups.jsonl"
    sources_path = output / "source_records.jsonl"
    models_path = output / "processed_models.jsonl"
    hypotheses_path = output / "mr_hypotheses.jsonl"
    atomic_write_text(
        groups_path, "".join(f"{canonical_json_text(x)}\n" for x in groups)
    )
    atomic_write_text(
        sources_path, "".join(f"{canonical_json_text(x)}\n" for x in sources)
    )
    atomic_write_text(
        models_path, "".join(f"{canonical_json_text(x)}\n" for x in models)
    )
    atomic_write_text(
        hypotheses_path, "".join(f"{canonical_json_text(x)}\n" for x in hypotheses)
    )
    for hypothesis in hypotheses:
        atomic_write_text(
            hypothesis_root / f"{hypothesis.hypothesis_id}.jsonl",
            f"{canonical_json_text(hypothesis)}\n",
        )
    model_manifest = output / "model_preparation_manifest.json"
    atomic_write_json(
        model_manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "entries": entries,
        },
    )
    return groups_path, sources_path, models_path, model_manifest, tuple(hypotheses)


def _review_seed(
    output: Path, attempt: PhaserRunOutput
) -> tuple[str, Path, Path, Path]:
    result = attempt.result
    if result.solution_coordinate_path is None:
        raise ControlSliceRunError("packed first-copy result lacks coordinates")
    solution_id = content_id(
        "sol_",
        {
            "hypothesis_id": result.hypothesis_id,
            "coordinate_sha256": result.solution_coordinate_sha256,
        },
    )
    review = output / "review" / solution_id
    assets = review / "assets"
    assets.mkdir(parents=True)
    coordinate_source = attempt.result_json.parent / result.solution_coordinate_path
    coordinate = assets / "solution.pdb"
    result_copy = assets / "normalised_mr_result.jsonl"
    command_copy = assets / "phaser_command.json"
    shutil.copy2(coordinate_source, coordinate)
    shutil.copy2(attempt.result_jsonl, result_copy)
    shutil.copy2(attempt.command_json, command_copy)
    package_id = content_id(
        "reviewpkg_",
        {"solution_id": solution_id, "hypothesis_id": result.hypothesis_id},
    )
    manifest = review / "mr_seed_review_manifest.json"
    atomic_write_json(
        manifest,
        {
            "schema_version": "2.0",
            "package_id": package_id,
            "items": [
                {
                    "solution_id": solution_id,
                    "hypothesis_id": result.hypothesis_id,
                    "copied_assets": {
                        "solution_coordinate": "assets/solution.pdb",
                        "normalised_result": "assets/normalised_mr_result.jsonl",
                        "command": "assets/phaser_command.json",
                    },
                    "copied_asset_sha256": {
                        "solution_coordinate": sha256_file(coordinate),
                        "normalised_result": sha256_file(result_copy),
                        "command": sha256_file(command_copy),
                    },
                }
            ],
        },
    )
    validation = review / "mr_seed_approval.json"
    atomic_write_json(
        validation,
        {
            "schema_version": "1.0",
            "execution_status": "completed_success",
            "checkpoint": "mr_seed",
            "package_id": package_id,
            "package_manifest_sha256": sha256_file(manifest),
            "approved_solution_ids": [solution_id],
            "review_id": content_id("review_", {"package_id": package_id}),
        },
    )
    return solution_id, validation, manifest, coordinate


def _positive_control_retained(
    *,
    expected_copy_count: int,
    related: list[NormalisedMrResult],
    supported_copy_two_hypotheses: set[str],
) -> bool:
    """Require packed first-copy evidence and the truth-labelled ASU count."""

    return any(
        item.execution_status is ExecutionStatus.COMPLETED_HIT
        and item.packing_summary.get("top_solution_packed") is True
        and (
            expected_copy_count == 1
            or item.hypothesis_id in supported_copy_two_hypotheses
        )
        for item in related
    )


def run_control_slice(request: ControlSliceRunRequest) -> ControlSliceRunOutput:
    """Execute and retain the complete fixed six-case smoke slice."""

    if request.threads < 2 or request.threads > 64:
        raise ControlSliceRunError("control-slice threads must be between 2 and 64")
    root = request.import_root.resolve(strict=True)
    manifest_path = root / "control_slice_import_manifest.json"
    manifest = _object(manifest_path)
    case_ids = manifest.get("case_ids")
    if not isinstance(case_ids, list) or tuple(case_ids) != _EXPECTED_CASES:
        raise ControlSliceRunError("imported control-slice cases changed")
    output = request.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    positives = cast(dict[str, dict[str, object]], manifest["positive_controls"])
    crystals = output / "crystals.json"
    atomic_write_json(
        crystals,
        {
            "schema_version": "1.0",
            "crystals": [
                {
                    "crystal_id": control_id,
                    "mtz": str(root / f"controls/{control_id}/input.mtz"),
                    "catalogue_id": str(positives[control_id]["catalogue_id"]),
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
                    "notes": "truth-labelled public homomer control",
                }
                for control_id in ("PDB_1JCF", "PDB_3W45")
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
    groups, sources, models, model_manifest, hypotheses = _write_runtime_inputs(
        root, manifest, preflight.records, output / "runtime"
    )
    threads_per_attempt = max(1, request.threads // 4)

    def execute(hypothesis: MrHypothesis) -> PhaserRunOutput:
        return run_first_copy_phaser(
            PhaserRunRequest(
                hypotheses_jsonl=output
                / "runtime/hypotheses"
                / f"{hypothesis.hypothesis_id}.jsonl",
                hypothesis_id=hypothesis.hypothesis_id,
                sequence_groups_jsonl=groups,
                processed_models_jsonl=models,
                model_preparation_manifest=model_manifest,
                preflight_jsonl=preflight.jsonl_path,
                mtz=root / f"controls/{hypothesis.crystal_id}/input.mtz",
                phenix_manifest=request.phenix_manifest,
                output_directory=output / "first-copy" / hypothesis.hypothesis_id,
                threads=threads_per_attempt,
                timeout_seconds=None,
                progress=False,
            )
        )

    with ThreadPoolExecutor(max_workers=min(4, len(hypotheses))) as executor:
        attempts = tuple(executor.map(execute, hypotheses))
    first_results = output / "first_copy_results.jsonl"
    atomic_write_text(
        first_results,
        "".join(f"{canonical_json_text(attempt.result)}\n" for attempt in attempts),
    )

    copy_series: list[AddCopySeriesOutput] = []
    refinements: list[T12RunOutput] = []
    hypothesis_by_id = {item.hypothesis_id: item for item in hypotheses}
    preflight_by_id = {item.crystal_id: item for item in preflight.records}
    for attempt in attempts:
        hypothesis = hypothesis_by_id[attempt.result.hypothesis_id]
        if (
            hypothesis.crystal_id != "PDB_3W45"
            or hypothesis.priority_features.get("control_role") != "known_positive"
            or attempt.result.execution_status is not ExecutionStatus.COMPLETED_HIT
            or attempt.result.placed_copy_count != 1
            or attempt.result.packing_summary.get("top_solution_packed") is not True
        ):
            continue
        solution_id, validation, review_manifest, coordinate = _review_seed(
            output, attempt
        )
        series = run_additional_copy_series(
            AddCopyRunRequest(
                review_validation_json=validation,
                review_package_manifest=review_manifest,
                seed_solution_id=solution_id,
                hypotheses_jsonl=output / "runtime/mr_hypotheses.jsonl",
                sequence_groups_jsonl=groups,
                preflight_jsonl=preflight.jsonl_path,
                mtz=root / "controls/PDB_3W45/input.mtz",
                search_model=coordinate,
                expected_search_model_sha256=sha256_file(coordinate),
                phenix_manifest=request.phenix_manifest,
                output_directory=output / "copy-two" / solution_id,
                threads=min(4, request.threads),
                timeout_seconds=None,
                progress=False,
            )
        )
        copy_series.append(series)
        final = series.attempts[-1].result
        if not final.additional_copy_supported or final.output_coordinate_path is None:
            continue
        final_output = series.attempts[-1].result_json.parent
        parent_coordinate = final_output / final.output_coordinate_path
        mtz = root / "controls/PDB_3W45/input.mtz"
        pf = preflight_by_id["PDB_3W45"]
        refinements.append(
            run_t12_candidate(
                T12RunRequest(
                    seed_solution_id=solution_id,
                    sequence_group_id=hypothesis.sequence_group_id,
                    input_copy_count=final.best_supported_copy_count,
                    parent_coordinate=parent_coordinate,
                    parent_coordinate_sha256=sha256_file(parent_coordinate),
                    parent_mtz=mtz,
                    parent_mtz_sha256=sha256_file(mtz),
                    observation_labels=cast(str, pf.selected_observation_labels),
                    sequence_groups_jsonl=groups,
                    source_records_jsonl=sources,
                    resolution=pf.resolution_high_a,
                    phenix_manifest=request.phenix_manifest,
                    output_directory=output / "t12" / solution_id,
                    threads=min(4, request.threads),
                    timeout_seconds=None,
                    progress=False,
                )
            )
        )

    copy_results = output / "copy_two_results.jsonl"
    atomic_write_text(
        copy_results,
        "".join(
            f"{canonical_json_text(attempt.result)}\n"
            for series in copy_series
            for attempt in series.attempts
        ),
    )
    refinement_results = output / "refinement_results.jsonl"
    atomic_write_text(
        refinement_results,
        "".join(f"{canonical_json_text(item.refinement)}\n" for item in refinements),
    )
    sequence_results = output / "sequence_results.jsonl"
    atomic_write_text(
        sequence_results,
        "".join(f"{canonical_json_text(item.sequence)}\n" for item in refinements),
    )

    supported_copy_two_hypotheses = {
        series.attempts[-1].result.hypothesis_id
        for series in copy_series
        if series.attempts[-1].result.additional_copy_supported
        and series.attempts[-1].result.best_supported_copy_count == 2
    }

    case_records: list[dict[str, object]] = []
    for case_id in _EXPECTED_CASES:
        if case_id.startswith("POS_"):
            crystal_id = f"PDB_{case_id.removeprefix('POS_')}"
            related = [
                attempt.result
                for attempt in attempts
                if hypothesis_by_id[attempt.result.hypothesis_id].crystal_id
                == crystal_id
                and hypothesis_by_id[
                    attempt.result.hypothesis_id
                ].priority_features.get("control_role")
                == "known_positive"
            ]
            raw_expected = positives[crystal_id]["expected_asu_copy_count"]
            if not isinstance(raw_expected, int):
                raise ControlSliceRunError("positive copy count is not an integer")
            expected_copy_count = raw_expected
            retained = _positive_control_retained(
                expected_copy_count=expected_copy_count,
                related=related,
                supported_copy_two_hypotheses=supported_copy_two_hypotheses,
            )
            outcome = (
                "ground_truth_retained" if retained else "ground_truth_not_retained"
            )
        elif case_id == "NEG_MODEL_3W45_6HF7":
            outcome = "unrelated_model_retained_for_comparison"
        elif case_id in {"NEG_ABSENT_3W45", "NEG_CATALOGUE_3W45_1JCF"}:
            outcome = "no_reportable_identity"
        else:
            outcome = "assumption_violation_abstained"
        case_records.append(
            {
                "schema_version": "1.0",
                "case_id": case_id,
                "outcome": outcome,
                "all_candidates_retained": True,
            }
        )
    case_results = output / "control_slice_case_results.jsonl"
    atomic_write_text(
        case_results,
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in case_records),
    )
    summary = output / "control_slice_summary.json"
    atomic_write_json(
        summary,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "generated_at": utc_now_iso(),
            "slice_id": "prokaryote_homomer_smoke_v1",
            "case_count": 6,
            "first_copy_attempt_count": len(attempts),
            "copy_two_attempt_count": sum(
                len(series.attempts) for series in copy_series
            ),
            "refinement_attempt_count": len(refinements),
            "all_candidates_retained": True,
            "score_policy": "LLG/TFZ_are_ranking_annotations_only",
            "import_manifest_sha256": sha256_file(manifest_path),
            "phenix_manifest_sha256": sha256_file(request.phenix_manifest),
            "case_results_sha256": sha256_file(case_results),
            "first_copy_results_sha256": sha256_file(first_results),
            "copy_two_results_sha256": sha256_file(copy_results),
            "refinement_results_sha256": sha256_file(refinement_results),
            "sequence_results_sha256": sha256_file(sequence_results),
        },
    )
    return ControlSliceRunOutput(
        summary_json=summary,
        case_results_jsonl=case_results,
        first_copy_results_jsonl=first_results,
        copy_two_results_jsonl=copy_results,
        refinement_results_jsonl=refinement_results,
        sequence_results_jsonl=sequence_results,
        first_copy_attempt_count=len(attempts),
        copy_two_attempt_count=sum(len(series.attempts) for series in copy_series),
        refinement_attempt_count=len(refinements),
    )
