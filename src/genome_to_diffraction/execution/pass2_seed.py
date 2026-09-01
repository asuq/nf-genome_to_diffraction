"""Derive one executable depth-one state from credible pass-1 evidence.

The adapter authenticates the current pass-1 assessment, selected search
hypothesis, registry model, Phaser command/result/solution bytes, copy support,
and reviewed refinement assets. It derives component-A coordinates through the
same exact-model placement partition used by the public controls. The resulting
state remains identity-unresolved and is eligible only as a packed/refined
search parent; it makes no sequence or complete-composition claim.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.model_registry.all_eligible import (
    AllEligibleModelRegistryError,
    load_all_eligible_model_registry,
)
from genome_to_diffraction.mr import (
    ExpectedPhaserComponent,
    PhaserPerPlacementRequest,
    collect_phaser_per_placement_outputs,
)
from genome_to_diffraction.schemas.results import (
    CopyCountAssessment,
    MrHypothesis,
    NormalisedMrResult,
    SequenceGroupRecord,
)
from genome_to_diffraction.schemas.v2 import (
    ComponentIdentitySupport,
    ComponentPlacement,
    ComponentSpec,
    CompositionState,
    CompositionSupportState,
    PhaseIIIExecutionIdentity,
    UnknownPass1CrystalAssessment,
    UnknownPass1ScientificStatus,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_ADAPTER = "phase3-pass2-a-seed-v1"
_ENSEMBLE = re.compile(rb"^SOLU 6DIM ENSE\s+(\S+)", re.M)


class Pass2SeedError(InputContractError):
    """Credible pass-1 evidence cannot form one executable A parent."""


@dataclass(frozen=True, slots=True)
class Pass2SeedRequest:
    """Exact files needed to derive one depth-one composition state."""

    assessment: Path
    hypothesis_jsonl: Path
    copy_assessments_jsonl: Path
    packing_result: Path
    phaser_command: Path
    solution_file: Path
    combined_coordinate: Path
    source_mtz: Path
    output_mtz: Path
    sequence_groups_jsonl: Path
    model_registry: Path
    execution_identity: Path
    output_directory: Path


@dataclass(frozen=True, slots=True)
class Pass2SeedOutput:
    """Published state, fixed-component inventory, and complete checksums."""

    state: CompositionState
    state_json: Path
    component_inventory: Path
    checksums: Path


def _model(path: Path, model, label: str):
    if path.is_symlink() or not path.is_file():
        raise Pass2SeedError(f"{label} must be a regular file")
    try:
        return model.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise Pass2SeedError(f"{label} violates its contract") from error


def _records(path: Path, model, label: str) -> tuple:
    if path.is_symlink() or not path.is_file():
        raise Pass2SeedError(f"{label} must be a regular file")
    records = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    records.append(model.model_validate_json(line))
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise Pass2SeedError(f"{label} violates its contract") from error
    return tuple(records)


def build_pass2_a_seed(request: Pass2SeedRequest) -> Pass2SeedOutput:
    """Derive and publish one claim-free A parent for component expansion."""

    assessment = _model(
        request.assessment,
        UnknownPass1CrystalAssessment,
        "pass-1 assessment",
    )
    if (
        assessment.scientific_status
        not in {
            UnknownPass1ScientificStatus.CREDIBLE_SINGLE_COMPONENT_SOLUTION,
            UnknownPass1ScientificStatus.CREDIBLE_PARTIAL_OR_RESIDUAL,
        }
        or assessment.solution_evidence is None
    ):
        raise Pass2SeedError("pass-1 assessment does not retain a credible A state")
    solution = assessment.solution_evidence
    identity = _model(
        request.execution_identity,
        PhaseIIIExecutionIdentity,
        "execution identity",
    )
    adapters = dict(identity.adapter_versions)
    if (
        assessment.execution_identity_id != identity.execution_identity_id
        or adapters.get("phase3_pass2_a_seed") != _ADAPTER
        or adapters.get("phase3_all_model_registry") != "all-eligible-model-registry-v3"
        or adapters.get("phase3_component_coordinates")
        != "phaser-component-coordinate-inventory-v2"
    ):
        raise Pass2SeedError("pass-2 A seed uses another execution authority")
    hypotheses = _records(request.hypothesis_jsonl, MrHypothesis, "A hypotheses")
    copies = _records(
        request.copy_assessments_jsonl,
        CopyCountAssessment,
        "copy assessments",
    )
    copy_matches = tuple(
        item for item in copies if item.seed_solution_id == solution.state_id
    )
    if len(copy_matches) != 1:
        raise Pass2SeedError("copy evidence lacks one reviewed A state")
    copy = copy_matches[0]
    hypothesis_matches = tuple(
        item for item in hypotheses if item.hypothesis_id == copy.hypothesis_id
    )
    if len(hypothesis_matches) != 1:
        raise Pass2SeedError("A hypothesis evidence is missing or ambiguous")
    hypothesis = hypothesis_matches[0]
    packing = _model(request.packing_result, NormalisedMrResult, "packing result")
    groups = _records(
        request.sequence_groups_jsonl,
        SequenceGroupRecord,
        "sequence groups",
    )
    group_matches = tuple(
        item for item in groups if item.sequence_group_id == copy.sequence_group_id
    )
    if len(group_matches) != 1:
        raise Pass2SeedError("A search sequence group is missing or ambiguous")
    group = group_matches[0]
    try:
        registry = load_all_eligible_model_registry(request.model_registry)
    except (AllEligibleModelRegistryError, OSError) as error:
        raise Pass2SeedError("all-model registry is invalid") from error
    entries = tuple(
        entry
        for inventory in registry.manifest.sequence_groups
        for entry in inventory.models
        if entry.sequence_group_id == group.sequence_group_id
        and entry.model_id == hypothesis.model_id
    )
    if len(entries) != 1 or entries[0].model_sequence_identity <= 0:
        raise Pass2SeedError("A hypothesis lacks one usable registry model")
    entry = entries[0]
    command_path = request.phaser_command.resolve(strict=True)
    try:
        command = command_path.read_text(encoding="utf-8")
        command_record = json.loads(command)
    except (OSError, UnicodeError, ValueError) as error:
        raise Pass2SeedError("A Phaser command is invalid") from error
    combined = request.combined_coordinate.resolve(strict=True)
    source_mtz = request.source_mtz.resolve(strict=True)
    output_mtz = request.output_mtz.resolve(strict=True)
    solution_file = request.solution_file.resolve(strict=True)
    model_path = (registry.root / entry.model_path).resolve(strict=True)
    if any(
        path.is_symlink() or not path.is_file()
        for path in (
            command_path,
            combined,
            source_mtz,
            output_mtz,
            solution_file,
            model_path,
        )
    ):
        raise Pass2SeedError("A scientific asset is absent or unsafe")
    mtz_sha256 = sha256_file(source_mtz)
    mtz_artifacts = tuple(
        artifact
        for artifact in identity.crystal_artifacts
        if artifact.owner_id == assessment.crystal_id and artifact.role == "mtz"
    )
    ensembles = tuple(dict.fromkeys(_ENSEMBLE.findall(solution_file.read_bytes())))
    try:
        ensemble = ensembles[0].decode("ascii") if len(ensembles) == 1 else ""
    except UnicodeError as error:
        raise Pass2SeedError("A Phaser ensemble is not ASCII") from error
    if (
        not ensemble
        or command_record.get("phase3_hypothesis_id") != hypothesis.hypothesis_id
        or command_record.get("model_sha256") != entry.model_sha256
        or command_record.get("sequence_sha256") != group.sha256
        or command_record.get("mtz_sha256") != mtz_sha256
        or len(mtz_artifacts) != 1
        or mtz_artifacts[0].sha256 != mtz_sha256
        or mtz_artifacts[0].size_bytes != source_mtz.stat().st_size
        or command_record.get("model_identity_percent")
        != entry.model_sequence_identity * 100.0
        or packing.hypothesis_id != copy.hypothesis_id
        or packing.execution_status is not ExecutionStatus.COMPLETED_HIT
        or packing.llg is None
        or packing.tfz is None
        or packing.placed_copy_count != copy.best_supported_copy_count
        or packing.placed_copy_count != copy.expected_copy_count
        or packing.packing_summary.get("top_solution_packed") is not True
        or packing.solution_coordinate_sha256 != sha256_file(combined)
        or packing.output_mtz_sha256 != sha256_file(output_mtz)
        or solution.search_sequence_group_id != group.sequence_group_id
        or solution.requested_copy_count != copy.expected_copy_count
        or solution.observed_copy_count != copy.best_supported_copy_count
    ):
        raise Pass2SeedError("A command/result/review evidence differs")
    mass = group.molecular_mass_da
    if mass is None:
        raise Pass2SeedError("A search sequence lacks exact mass evidence")
    component = ComponentSpec.from_content(
        label="A",
        sequence_group_id=group.sequence_group_id,
        sequence_sha256=group.sha256,
        model_id=entry.model_id,
        model_sha256=entry.model_sha256,
        requested_copy_count=copy.best_supported_copy_count,
        sequence_mass_da=mass,
        mass_evidence_sha256=canonical_digest(group),
        model_evidence_sha256=entry.model_uncertainty_evidence_sha256,
        warnings=("pass1_map_identity_retained_separately",),
    )
    output = request.output_directory.resolve()
    if output.exists() or output.is_symlink():
        raise Pass2SeedError("pass-2 A-seed output must be absent")
    runtime = output / "runtime"
    runtime.mkdir(parents=True)
    copied_command = runtime / "phaser_command.json"
    copied_result = runtime / "normalised_mr_result.json"
    copied_solution = runtime / "PHASER.sol"
    copied_combined = runtime / "PHASER.1.pdb"
    copied_mtz = runtime / "PHASER.1.mtz"
    shutil.copy2(command_path, copied_command)
    shutil.copy2(request.packing_result, copied_result)
    shutil.copy2(solution_file, copied_solution)
    shutil.copy2(combined, copied_combined)
    shutil.copy2(output_mtz, copied_mtz)
    placement_output = collect_phaser_per_placement_outputs(
        PhaserPerPlacementRequest(
            crystal_id=assessment.crystal_id,
            search_id=hypothesis.hypothesis_id,
            phaser_version=packing.tool_version,
            output_directory=runtime,
            command_record=copied_command,
            result_record=copied_result,
            expected_components=(
                ExpectedPhaserComponent(
                    "A",
                    ensemble,
                    component.requested_copy_count,
                ),
            ),
            component_models=(("A", model_path),),
        )
    )
    placement_group = placement_output.inventory.component_groups[0]
    placement = ComponentPlacement.from_content(
        component_spec_id=component.component_spec_id,
        component_label="A",
        sequence_group_id=component.sequence_group_id,
        model_id=component.model_id,
        model_sha256=component.model_sha256,
        requested_copy_count=component.requested_copy_count,
        observed_copy_count=placement_group.observed_copy_count,
        execution_status=ExecutionStatus.COMPLETED_HIT,
        component_tfz=packing.tfz,
        incremental_llg=packing.llg,
        packing_passed=True,
        coordinate_sha256=placement_group.coordinate_sha256,
        identity_support=ComponentIdentitySupport.UNRESOLVED,
        warnings=("pass1_map_identity_retained_separately",),
    )
    state = CompositionState.from_content(
        crystal_id=assessment.crystal_id,
        diffraction_dataset_id=command_record["diffraction_selection"][
            "diffraction_dataset_id"
        ],
        diffraction_sha256=mtz_sha256,
        parent_state_id=None,
        depth=1,
        components=(component,),
        placements=(placement,),
        combined_coordinate_sha256=sha256_file(copied_combined),
        combined_mtz_sha256=sha256_file(copied_mtz),
        refinement_evidence_sha256=solution.refinement_evidence_sha256,
        map_evidence_sha256=solution.review_map_sha256,
        physical_mass_lower_da=mass * component.requested_copy_count,
        physical_mass_upper_da=mass * component.requested_copy_count,
        support_state=CompositionSupportState.REFINED,
        warnings=("identity_claim_requires_final_pass2_review",),
    )
    state_path = output / "composition_state.json"
    atomic_write_json(state_path, state.model_dump(mode="json"))
    manifest = output / "pass2_a_seed_manifest.json"
    atomic_write_json(
        manifest,
        {
            "schema_version": "2.0",
            "adapter_version": _ADAPTER,
            "assessment_id": assessment.assessment_id,
            "state_id": state.state_id,
            "model_registry_id": registry.manifest.registry_id,
            "component_inventory_sha256": sha256_file(placement_output.inventory_json),
            "exact_identity_claimed": False,
            "complete_composition_claimed": False,
        },
    )
    checksums = output / "pass2_a_seed_checksums.sha256"
    files = tuple(
        sorted(
            (
                path
                for path in output.rglob("*")
                if path.is_file() and path != checksums
            ),
            key=lambda path: path.relative_to(output).as_posix(),
        )
    )
    atomic_write_text(
        checksums,
        "".join(
            f"{sha256_file(path)}  {path.relative_to(output).as_posix()}\n"
            for path in files
        ),
    )
    return Pass2SeedOutput(
        state=state,
        state_json=state_path,
        component_inventory=placement_output.inventory_json,
        checksums=checksums,
    )


__all__ = [
    "Pass2SeedError",
    "Pass2SeedOutput",
    "Pass2SeedRequest",
    "build_pass2_a_seed",
]
