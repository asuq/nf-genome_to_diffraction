"""Preparation helpers for the retired six-case direct benchmark driver.

The historical driver ran independent Phenix attempts in a Python thread pool.
That execution surface is intentionally retired: scientific fan-out belongs to
Nextflow channel items and the configured executor.  The retained helpers are
still used to prepare and classify immutable control evidence for newer
Nextflow-owned workflows.
"""

import hashlib
import shutil
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
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.mr.phaser import PhaserRunOutput
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
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

_ADAPTER_VERSION = "public-homomer-smoke-run-v1"


class ControlSliceRunError(InputContractError):
    """The fixed imported slice or its scientific relationships changed."""


def _object(path: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    try:
        value = load_json_document(resolved)
    except ContractLoadError as error:
        raise ControlSliceRunError(f"cannot load JSON object: {error}") from error
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
                if info.is_amino_acid() or residue.name == "KYN":
                    residues.append(residue)
                    atom_count += len(residue)
    sequence = "".join(
        "W"
        if residue.name == "KYN"
        else gemmi.find_tabulated_residue(residue.name).one_letter_code
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
