"""Preparation helpers for the retired 23-case direct benchmark driver.

Independent first-copy, copy-series, and refinement attempts formerly ran in
Python thread pools. That public execution surface is retired so Nextflow can
own scientific item fan-out, executor scheduling, retry, and resume. Shared
preparation/classification helpers remain for the Nextflow-owned M6 graph and
immutable historical evidence.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Never, cast

from genome_to_diffraction.benchmarks.control_slice_run import (
    ControlSliceRunError,
    _pdb_sequence,
    _target_fasta,
)
from genome_to_diffraction.benchmarks.mr_controls import _model_record
from genome_to_diffraction.catalogue.mass import MASS_METHOD, assess_mass
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.mr.phaser import PhaserRunOutput
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

_ADAPTER_VERSION = "public-homomer-matrix-run-v2"
_DEFAULT_THREADS = 8
_RETIRED_EXECUTION_MESSAGE = (
    "benchmark run-control-matrix is retired because it scheduled independent "
    "scientific attempts inside Python. Migrate the archival suite to a reviewed "
    "DSL2 workflow that emits one complete Nextflow channel item per hypothesis, "
    "seed, and finalist; the configured executor must own concurrency and resume."
)


class ControlMatrixRunError(ControlSliceRunError):
    """The fixed matrix import or scientific relationship changed."""


@dataclass(frozen=True, slots=True)
class ControlMatrixRunRequest:
    """Legacy invocation fields retained only for the migration diagnostic."""

    import_root: Path
    phenix_manifest: Path
    output_directory: Path
    threads: int = _DEFAULT_THREADS
    progress: bool = True
    skip_xtriage: bool = False


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
                    "coordinate_mapping_id": mapping_id,
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


def _supported_first_copy_count(
    attempt: PhaserRunOutput, *, expected_copy_count: int
) -> int:
    result = attempt.result
    if (
        attempt.result.execution_status is ExecutionStatus.COMPLETED_HIT
        and 1 <= result.placed_copy_count <= expected_copy_count
        and result.packing_summary.get("top_solution_packed") is True
        and result.solution_coordinate_path is not None
    ):
        return result.placed_copy_count
    return 0


def run_control_matrix(request: ControlMatrixRunRequest) -> Never:
    """Refuse the retired direct scientific scheduler before reading inputs."""

    del request
    raise ControlMatrixRunError(_RETIRED_EXECUTION_MESSAGE)
