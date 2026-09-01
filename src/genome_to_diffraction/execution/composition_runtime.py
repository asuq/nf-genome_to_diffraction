"""Execute one selected Phase III B--F composition attempt.

The adapter consumes one complete composition-attempt inventory and resolves
exact fixed-component coordinates plus all parent/candidate models from
checksum-validated run-owned roots.  It verifies the source MTZ, raw Free-R
membership, global Phase III execution identity, and all-model registry before
running the installed, 9ECN-qualified multi-fixed Phaser adapter.

One invocation executes exactly one attempt.  Completed hit, no-hit, tool,
parse, and infrastructure outcomes are retained as typed results so sibling
Nextflow items can continue.  A hit is converted to candidate-specific score
evidence and one child composition state without asserting sequence identity
or complete composition.  Depths four through six are explicitly provisional.

The attempt inventory, fixed/model roots, sequence groups, MTZ, preflight,
Phenix manifest, execution identity, adapter version, raw outputs, and final
checksums form the cache/evidence boundary.  Focused unit and Nextflow-stub
coverage lives in ``tests/unit/test_composition_runtime.py`` and
``tests/scripts/check_composition_attempt_fanout.py``.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import ClassVar, Literal, Self

from pydantic import Field, ValidationError, model_validator

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.diffraction.free_r_identity import (
    build_free_r_identity,
    compare_free_r_membership,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.model_registry.all_eligible import (
    AllEligibleModelRegistry,
    AllEligibleModelRegistryError,
    load_all_eligible_model_registry,
)
from genome_to_diffraction.mr import (
    CandidateSearchComponent,
    ExpectedPhaserComponent,
    FixedSearchComponent,
    MultiFixedSearchManifest,
    PartnerSearchRequest,
    PhaserPerPlacementRequest,
    collect_phaser_per_placement_outputs,
    run_multi_fixed_search,
    run_partner_search,
)
from genome_to_diffraction.mr_resources import (
    MrResourcePlanError,
    verify_mr_thread_allocation,
)
from genome_to_diffraction.schemas.base import NonEmptyString, Sha256Hex
from genome_to_diffraction.schemas.manifests import PhenixInstallManifest
from genome_to_diffraction.schemas.results import (
    NormalisedMrResult,
    SequenceGroupRecord,
)
from genome_to_diffraction.schemas.v2 import (
    ComponentExpansionExecutionInput,
    ComponentExpansionScoreEvidence,
    ComponentSpec,
    CompositionState,
    CompositionSupportState,
    FreeRMembershipComparison,
    PhaseIIIExecutionIdentity,
    PhaserPerPlacementInventory,
)
from genome_to_diffraction.schemas.v2.composition import (
    _ContentAddressedContract,
)
from genome_to_diffraction.schemas.v2.composition_attempts import (
    CompositionAttemptIdentifier,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_ADAPTER_VERSION = "phase3-composition-attempt-execution-v2-resource-plan"
_PARTNER_ADAPTER_VERSION = "phenix-fixed-a-joint-b-v8-phase3-diffraction"
_MULTI_FIXED_ADAPTER_VERSION = "phenix-multi-fixed-joint-component-v2-diffraction"
_PLACEMENT_ADAPTER_VERSION = "phaser-component-coordinate-inventory-v2"
_TERMINAL_WITHOUT_STATE = frozenset(
    {
        ExecutionStatus.COMPLETED_NO_HIT,
        ExecutionStatus.FAILED_TOOL_EXECUTION,
        ExecutionStatus.FAILED_PARSE,
        ExecutionStatus.FAILED_INFRASTRUCTURE,
        ExecutionStatus.FAILED_INPUT_CONTRACT,
    }
)


class CompositionAttemptExecutionError(InputContractError):
    """One selected attempt cannot be resolved or authenticated."""


class CompositionAttemptExecutionResult(_ContentAddressedContract):
    """Typed terminal attempt result and optional child-state evidence."""

    _identity_field: ClassVar[str] = "attempt_result_id"
    _identity_prefix: ClassVar[str] = "compattemptresult_"

    schema_version: Literal["2.0"]
    adapter_version: Literal[
        "phase3-composition-attempt-execution-v2-resource-plan"
    ] = _ADAPTER_VERSION
    attempt_result_id: NonEmptyString
    attempt_id: CompositionAttemptIdentifier
    resource_plan_id: NonEmptyString
    resource_attempt: int = Field(ge=1, le=2)
    execution_input_id: NonEmptyString
    crystal_id: NonEmptyString
    parent_state_id: NonEmptyString
    candidate_component_spec_id: NonEmptyString
    execution_status: ExecutionStatus
    search_result_sha256: Sha256Hex
    placement_inventory_sha256: Sha256Hex | None = None
    score_evidence_id: NonEmptyString | None = None
    score_evidence_sha256: Sha256Hex | None = None
    child_state_id: NonEmptyString | None = None
    child_state_sha256: Sha256Hex | None = None
    free_r_comparison_id: NonEmptyString | None = None
    free_r_comparison_sha256: Sha256Hex | None = None
    child_support_state: CompositionSupportState | None = None
    scientific_status: Literal["search_evidence_only"] = "search_evidence_only"
    exact_identity_claimed: Literal[False] = False
    complete_composition_claimed: Literal[False] = False
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_terminal_evidence(self) -> Self:
        evidence = (
            self.placement_inventory_sha256,
            self.score_evidence_id,
            self.score_evidence_sha256,
            self.child_state_id,
            self.child_state_sha256,
            self.free_r_comparison_id,
            self.free_r_comparison_sha256,
            self.child_support_state,
        )
        if self.execution_status is ExecutionStatus.COMPLETED_HIT:
            if any(value is None for value in evidence):
                raise ValueError("completed composition attempt lacks child evidence")
        elif self.execution_status in _TERMINAL_WITHOUT_STATE:
            if any(value is not None for value in evidence):
                raise ValueError("non-hit composition attempt contains child evidence")
        else:
            raise ValueError("composition attempt status is not terminal")
        return self


@dataclass(frozen=True, slots=True)
class CompositionAttemptExecutionRequest:
    """Complete run-owned files for one selected attempt."""

    attempt_inventory: Path
    attempt_id: str
    fixed_coordinate_root: Path
    model_registry: Path
    sequence_groups_jsonl: Path
    preflight_jsonl: Path
    mtz: Path
    phenix_manifest: Path
    execution_identity: Path
    output_directory: Path
    threads: int = 1
    resource_attempt: int = 1
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class CompositionAttemptExecutionOutput:
    """Published typed result, optional child state, and checksums."""

    result: CompositionAttemptExecutionResult
    result_json: Path
    child_state_json: Path | None
    checksums: Path


def _regular_root(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise CompositionAttemptExecutionError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise CompositionAttemptExecutionError(f"{label} is absent") from error
    if not resolved.is_dir():
        raise CompositionAttemptExecutionError(f"{label} is not a directory")
    return resolved


def _regular_file(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise CompositionAttemptExecutionError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise CompositionAttemptExecutionError(f"{label} is absent") from error
    if not resolved.is_file():
        raise CompositionAttemptExecutionError(f"{label} is not a regular file")
    return resolved


def _load_execution_identity(path: Path) -> PhaseIIIExecutionIdentity:
    try:
        resolved = _regular_file(path, label="Phase III execution identity")
        return PhaseIIIExecutionIdentity.model_validate_json(
            resolved.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise CompositionAttemptExecutionError(
            "Phase III execution identity is invalid"
        ) from error


def _verify_execution_authority(
    *,
    identity: PhaseIIIExecutionIdentity,
    execution_input: ComponentExpansionExecutionInput,
    phenix_manifest: Path,
    mtz: Path,
) -> Path:
    adapters = dict(identity.adapter_versions)
    route_name, route_version = (
        ("phase3_partner_search", _PARTNER_ADAPTER_VERSION)
        if execution_input.parent_state.depth == 1
        else ("phase3_multi_fixed_search", _MULTI_FIXED_ADAPTER_VERSION)
    )
    required_adapters = {
        "phase3_all_model_registry": "all-eligible-model-registry-v3",
        "phase3_composition_attempt": _ADAPTER_VERSION,
        "phase3_component_coordinates": _PLACEMENT_ADAPTER_VERSION,
        "phase3_mr_resources": "phase3-mr-resource-allocation-v1",
        route_name: route_version,
    }
    if any(
        adapters.get(name) != version for name, version in required_adapters.items()
    ):
        raise CompositionAttemptExecutionError(
            "Phase III execution identity lacks current composition adapters"
        )
    crystal = execution_input.parent_state.crystal_id
    mtz_artifacts = tuple(
        artifact
        for artifact in identity.crystal_artifacts
        if artifact.owner_id == crystal and artifact.role == "mtz"
    )
    if (
        len(mtz_artifacts) != 1
        or mtz_artifacts[0].sha256 != sha256_file(mtz, progress=False)
        or mtz_artifacts[0].size_bytes != mtz.stat().st_size
    ):
        raise CompositionAttemptExecutionError(
            "Phase III execution identity uses a different crystal MTZ"
        )
    manifest_path = _regular_file(phenix_manifest, label="attempt Phenix manifest")
    try:
        manifest = PhenixInstallManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise CompositionAttemptExecutionError(
            "attempt Phenix manifest is invalid"
        ) from error
    execution_tools = {tool.name: tool for tool in identity.tools}
    commands = {
        command.name: command
        for command in manifest.required_commands
        if command.executable_sha256 is not None
    }
    if len(commands) != len(manifest.required_commands) or any(
        name not in execution_tools
        or execution_tools[name].executable_sha256 != command.executable_sha256
        or execution_tools[name].version
        != (command.version_text or manifest.phenix_version)
        or execution_tools[name].adapter_version != "phase3-strict-phenix-manifest-v1"
        for name, command in commands.items()
    ):
        raise CompositionAttemptExecutionError(
            "attempt Phenix runtime differs from execution identity"
        )
    return manifest_path


def _file_index(root: Path) -> dict[str, tuple[Path, ...]]:
    indexed: dict[str, list[Path]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise CompositionAttemptExecutionError(
                "fixed-coordinate root contains a symlink"
            )
        if not path.is_file():
            continue
        digest = sha256_file(path, progress=False)
        indexed.setdefault(digest, []).append(path)
    return {digest: tuple(paths) for digest, paths in indexed.items()}


def _fixed_paths(
    root: Path,
    execution_input: ComponentExpansionExecutionInput,
) -> tuple[Path, ...]:
    index = _file_index(root)
    parent = execution_input.parent_state
    if execution_input.parent_score_evidence_sha256 not in index:
        raise CompositionAttemptExecutionError("parent score evidence is absent")
    valid_parent_score = False
    for score_path in index[execution_input.parent_score_evidence_sha256]:
        try:
            if parent.depth == 1:
                score = NormalisedMrResult.model_validate_json(
                    score_path.read_text(encoding="utf-8")
                )
                valid_parent_score = (
                    score.execution_status is ExecutionStatus.COMPLETED_HIT
                    and score.llg == execution_input.parent_combined_llg
                    and score.solution_coordinate_sha256
                    == parent.combined_coordinate_sha256
                )
            else:
                score = ComponentExpansionScoreEvidence.model_validate_json(
                    score_path.read_text(encoding="utf-8")
                )
                valid_parent_score = (
                    score.combined_llg == execution_input.parent_combined_llg
                    and score.placement == parent.placements[-1]
                    and score.execution_input.selected_candidate.hypothesis.component
                    == parent.components[-1]
                )
        except OSError, UnicodeError, ValidationError, ValueError:
            continue
        if valid_parent_score:
            break
    if not valid_parent_score:
        raise CompositionAttemptExecutionError("parent score evidence differs")
    if parent.combined_coordinate_sha256 not in index:
        raise CompositionAttemptExecutionError(
            "parent combined coordinate evidence is absent"
        )
    paths: list[Path] = []
    for component, evidence in zip(
        parent.components,
        execution_input.fixed_components,
        strict=True,
    ):
        matches = index.get(evidence.fixed_coordinate_sha256, ())
        if not matches:
            raise CompositionAttemptExecutionError(
                "fixed component coordinate is absent"
            )
        derivations = index.get(evidence.coordinate_derivation_evidence_sha256, ())
        if not derivations:
            raise CompositionAttemptExecutionError(
                "fixed component derivation evidence is absent"
            )
        valid_inventory = False
        for derivation in derivations:
            try:
                inventory = PhaserPerPlacementInventory.model_validate_json(
                    derivation.read_text(encoding="utf-8")
                )
            except OSError, UnicodeError, ValidationError, ValueError:
                continue
            groups = tuple(
                group
                for group in inventory.component_groups
                if group.component_label == component.label
            )
            if (
                inventory.crystal_id == parent.crystal_id
                and inventory.combined_coordinate_sha256
                == parent.combined_coordinate_sha256
                and len(groups) == 1
                and groups[0].coordinate_sha256 == evidence.fixed_coordinate_sha256
            ):
                valid_inventory = True
                break
        if not valid_inventory:
            raise CompositionAttemptExecutionError(
                "fixed component derivation inventory differs"
            )
        paths.append(matches[0])
    return tuple(paths)


def _registry_entry_path(
    registry: AllEligibleModelRegistry,
    *,
    model_id: str,
    model_sha256: str,
) -> Path:
    entries = tuple(
        entry
        for inventory in registry.manifest.sequence_groups
        for entry in inventory.models
        if entry.model_id == model_id and entry.model_sha256 == model_sha256
    )
    if len(entries) != 1:
        raise CompositionAttemptExecutionError(
            "model registry lacks one exact attempt model"
        )
    relative = PurePosixPath(entries[0].model_path)
    path = (registry.root / Path(*relative.parts)).resolve(strict=True)
    if not path.is_file() or sha256_file(path, progress=False) != model_sha256:
        raise CompositionAttemptExecutionError("attempt model checksum differs")
    return path


def _sequence_groups(
    path: Path,
    required_ids: frozenset[str],
    output: Path,
) -> None:
    records: dict[str, SequenceGroupRecord] = {}
    try:
        lines = (
            _regular_file(path, label="sequence-group input")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    except (OSError, UnicodeError) as error:
        raise CompositionAttemptExecutionError("cannot read sequence groups") from error
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = SequenceGroupRecord.model_validate_json(line)
        except ValueError as error:
            raise CompositionAttemptExecutionError(
                f"invalid sequence group at line {line_number}"
            ) from error
        if record.sequence_group_id in records:
            raise CompositionAttemptExecutionError("duplicate sequence group")
        records[record.sequence_group_id] = record
    if not required_ids <= set(records):
        raise CompositionAttemptExecutionError(
            "sequence groups lack the complete attempt composition"
        )
    atomic_write_text(
        output,
        "".join(
            f"{canonical_json_text(records[group_id])}\n"
            for group_id in sorted(required_ids)
        ),
    )


def _mass_bounds(component: ComponentSpec) -> tuple[float, float]:
    exact = component.sequence_mass_da
    lower = component.sequence_mass_lower_da
    upper = component.sequence_mass_upper_da
    copies = component.requested_copy_count
    if exact is not None:
        return float(exact) * copies, float(exact) * copies
    if lower is None or upper is None:
        raise CompositionAttemptExecutionError(
            "selected component lacks physical mass evidence"
        )
    return float(lower) * copies, float(upper) * copies


def _write_checksums(root: Path) -> Path:
    checksums = root / "composition_attempt_checksums.sha256"
    retained = tuple(
        sorted(
            (path for path in root.rglob("*") if path.is_file() and path != checksums),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    )
    atomic_write_text(
        checksums,
        "".join(
            f"{sha256_file(path, progress=False)}  "
            f"{path.relative_to(root).as_posix()}\n"
            for path in retained
        ),
    )
    return checksums


def execute_composition_attempt(
    request: CompositionAttemptExecutionRequest,
) -> CompositionAttemptExecutionOutput:
    """Resolve, execute, and retain one selected B--F attempt."""

    if request.threads < 1 or (
        request.timeout_seconds is not None and request.timeout_seconds <= 0
    ):
        raise ValueError("threads and optional timeout must be positive")
    from genome_to_diffraction.execution.composition import (
        load_composition_attempt_inventory,
    )

    inventory_path = _regular_file(
        request.attempt_inventory,
        label="composition-attempt inventory",
    )
    inventory = load_composition_attempt_inventory(inventory_path)
    attempts = tuple(
        attempt
        for attempt in inventory.attempts
        if attempt.attempt_id == request.attempt_id
    )
    if len(attempts) != 1:
        raise CompositionAttemptExecutionError(
            "attempt inventory lacks one exact selected attempt"
        )
    attempt = attempts[0]
    try:
        verify_mr_thread_allocation(
            plan=attempt.resource_plan,
            resource_attempt=request.resource_attempt,
            threads=request.threads,
        )
    except MrResourcePlanError as error:
        raise CompositionAttemptExecutionError(str(error)) from error
    execution_inputs = tuple(
        item
        for item in inventory.execution_inputs
        if item.execution_input_id == attempt.component_execution_input_id
    )
    if len(execution_inputs) != 1:
        raise CompositionAttemptExecutionError(
            "attempt lacks one exact component execution input"
        )
    execution_input = execution_inputs[0]
    global_identity = _load_execution_identity(request.execution_identity)
    if global_identity.execution_identity_id != inventory.execution_identity_id:
        raise CompositionAttemptExecutionError(
            "attempt uses a different Phase III execution identity"
        )
    mtz = _regular_file(request.mtz, label="attempt MTZ")
    phenix_file = _verify_execution_authority(
        identity=global_identity,
        execution_input=execution_input,
        phenix_manifest=request.phenix_manifest,
        mtz=mtz,
    )
    try:
        registry_root = _regular_root(request.model_registry, label="model registry")
        registry = load_all_eligible_model_registry(
            registry_root / "all_model_registry.json"
        )
    except (OSError, AllEligibleModelRegistryError) as error:
        raise CompositionAttemptExecutionError(
            "attempt all-model registry is invalid"
        ) from error
    if registry.manifest.registry_id != inventory.model_registry_id:
        raise CompositionAttemptExecutionError(
            "attempt uses a different model registry"
        )

    fixed_root = _regular_root(
        request.fixed_coordinate_root,
        label="fixed-coordinate root",
    )
    fixed_paths = _fixed_paths(fixed_root, execution_input)
    parent = execution_input.parent_state
    candidate = execution_input.selected_candidate.hypothesis.component
    parent_model_paths = tuple(
        _registry_entry_path(
            registry,
            model_id=component.model_id,
            model_sha256=component.model_sha256,
        )
        for component in parent.components
    )
    candidate_model = _registry_entry_path(
        registry,
        model_id=candidate.model_id,
        model_sha256=candidate.model_sha256,
    )
    if (
        sha256_file(mtz, progress=False)
        != execution_input.diffraction_selection.mtz_sha256
    ):
        raise CompositionAttemptExecutionError("attempt MTZ differs from selection")
    observed_free_r = build_free_r_identity(
        selection=execution_input.diffraction_selection,
        mtz_path=mtz,
        free_r_dataset_id=execution_input.free_r_identity.free_r_dataset_id,
        free_r_label=execution_input.free_r_identity.free_r_label,
        test_flag_value=execution_input.free_r_identity.test_flag_value,
    )
    if observed_free_r != execution_input.free_r_identity:
        raise CompositionAttemptExecutionError("attempt Free-R identity differs")

    output = request.output_directory.absolute()
    if output.exists() or output.is_symlink():
        raise CompositionAttemptExecutionError("composition attempt output exists")
    output.mkdir(parents=True)
    staged_models = output / "models"
    staged_models.mkdir()
    staged_fixed_paths: list[Path] = []
    for component, source in zip(parent.components, fixed_paths, strict=True):
        destination = staged_models / f"fixed_{component.label}.pdb"
        shutil.copy2(source, destination)
        if sha256_file(destination) != sha256_file(source):
            raise CompositionAttemptExecutionError(
                "staged fixed-component checksum differs"
            )
        staged_fixed_paths.append(destination)
    staged_candidate_model = staged_models / f"candidate_{candidate.label}.pdb"
    candidate_source_sha256 = sha256_file(candidate_model)
    shutil.copy2(candidate_model, staged_candidate_model)
    if sha256_file(staged_candidate_model) != candidate_source_sha256:
        raise CompositionAttemptExecutionError("staged candidate checksum differs")
    fixed_paths = tuple(staged_fixed_paths)
    candidate_model = staged_candidate_model
    subset = output / "attempt_sequence_groups.jsonl"
    required_groups = frozenset(
        component.sequence_group_id for component in (*parent.components, candidate)
    )
    _sequence_groups(request.sequence_groups_jsonl, required_groups, subset)
    search_root = output / "search"
    preflight_file = _regular_file(
        request.preflight_jsonl,
        label="attempt preflight",
    )
    if parent.depth == 1:
        parent_component = parent.components[0]
        parent_evidence = execution_input.fixed_components[0]
        partner_output = run_partner_search(
            PartnerSearchRequest(
                crystal_id=parent.crystal_id,
                parent_solution_id=parent.state_id,
                parent_sequence_group_id=parent_component.sequence_group_id,
                partner_sequence_group_id=candidate.sequence_group_id,
                sequence_groups_jsonl=subset,
                parent_coordinate=fixed_paths[0],
                expected_parent_coordinate_sha256=(
                    parent_evidence.fixed_coordinate_sha256
                ),
                parent_llg=execution_input.parent_combined_llg,
                parent_model_identity_fraction=(
                    parent_evidence.phaser_identity_fraction
                ),
                parent_model_uncertainty_source=(
                    parent_evidence.model_uncertainty_source
                ),
                parent_copy_count=parent_component.requested_copy_count,
                partner_model=candidate_model,
                expected_partner_model_sha256=candidate.model_sha256,
                partner_model_identity_fraction=(
                    execution_input.candidate_phaser_identity_fraction
                ),
                partner_copy_count=candidate.requested_copy_count,
                preflight_jsonl=preflight_file,
                mtz=mtz,
                phenix_manifest=phenix_file,
                output_directory=search_root,
                diffraction_selection=execution_input.diffraction_selection,
                threads=request.threads,
                timeout_seconds=request.timeout_seconds,
                progress=False,
            )
        )
        native_result = partner_output.result
        search_result_path = partner_output.result_json
        command_record = partner_output.command_json
        component_tfz = native_result.partner_tfz
        score_ensemble_id = "search_partner"
        expected_components = (
            ExpectedPhaserComponent(
                parent_component.label,
                "fixed_parent",
                parent_component.requested_copy_count,
            ),
            ExpectedPhaserComponent(
                candidate.label,
                "search_partner",
                candidate.requested_copy_count,
            ),
        )
    else:
        fixed_manifest = output / "multi_fixed_search_input.json"
        atomic_write_json(
            fixed_manifest,
            MultiFixedSearchManifest(
                schema_version="2.0",
                adapter_version="multi-fixed-component-search-input-v2",
                crystal_id=parent.crystal_id,
                diffraction_selection=execution_input.diffraction_selection,
                parent_solution_id=parent.state_id,
                parent_combined_llg=execution_input.parent_combined_llg,
                fixed_components=tuple(
                    FixedSearchComponent(
                        schema_version="2.0",
                        label=component.label,
                        sequence_group_id=component.sequence_group_id,
                        model_id=component.model_id,
                        model_sha256=component.model_sha256,
                        coordinate_path=path.relative_to(output).as_posix(),
                        coordinate_sha256=evidence.fixed_coordinate_sha256,
                        requested_copy_count=component.requested_copy_count,
                        observed_copy_count=placement.observed_copy_count,
                        phaser_identity_fraction=evidence.phaser_identity_fraction,
                        model_uncertainty_source=evidence.model_uncertainty_source,
                        model_uncertainty_evidence_sha256=(
                            evidence.model_uncertainty_evidence_sha256
                        ),
                    )
                    for component, placement, evidence, path in zip(
                        parent.components,
                        parent.placements,
                        execution_input.fixed_components,
                        fixed_paths,
                        strict=True,
                    )
                ),
                candidate=CandidateSearchComponent(
                    schema_version="2.0",
                    label=candidate.label,
                    sequence_group_id=candidate.sequence_group_id,
                    model_id=candidate.model_id,
                    model_sha256=candidate.model_sha256,
                    model_path=candidate_model.relative_to(output).as_posix(),
                    requested_copy_count=candidate.requested_copy_count,
                    phaser_identity_fraction=(
                        execution_input.candidate_phaser_identity_fraction
                    ),
                    model_uncertainty_source=(
                        execution_input.candidate_model_uncertainty_source
                    ),
                    model_uncertainty_evidence_sha256=(
                        execution_input.candidate_model_uncertainty_evidence_sha256
                    ),
                ),
            ).model_dump(mode="json"),
        )
        native_result = run_multi_fixed_search(
            manifest_path=fixed_manifest,
            sequence_groups_jsonl=subset,
            preflight_jsonl=preflight_file,
            mtz_path=mtz,
            phenix_manifest=phenix_file,
            output_directory=search_root,
            threads=request.threads,
            timeout_seconds=request.timeout_seconds,
        )
        search_result_path = search_root / "component_search_result.json"
        command_record = search_root / "phaser_command.json"
        component_tfz = native_result.candidate_tfz
        score_ensemble_id = f"search_{candidate.label}"
        expected_components = (
            *(
                ExpectedPhaserComponent(
                    component.label,
                    f"fixed_{component.label}",
                    component.requested_copy_count,
                )
                for component in parent.components
            ),
            ExpectedPhaserComponent(
                candidate.label,
                f"search_{candidate.label}",
                candidate.requested_copy_count,
            ),
        )
    execution_status = native_result.execution_status
    search_id = native_result.search_id
    tool_version = native_result.tool_version
    combined_llg = native_result.combined_llg
    top_solution_packed = native_result.top_solution_packed
    combined_coordinate_path = native_result.combined_coordinate_path
    combined_coordinate_sha256 = native_result.combined_coordinate_sha256
    output_mtz_path = native_result.output_mtz_path
    output_mtz_sha256 = native_result.output_mtz_sha256
    search_sha256 = sha256_file(search_result_path, progress=False)
    result_json = output / "composition_attempt_execution.json"
    child_state_json: Path | None = None
    warnings = (
        ("provisional_unvalidated_component_depth",) if parent.depth + 1 >= 4 else ()
    )
    if execution_status is not ExecutionStatus.COMPLETED_HIT:
        result = CompositionAttemptExecutionResult.from_content(
            attempt_id=attempt.attempt_id,
            resource_plan_id=attempt.resource_plan.resource_plan_id,
            resource_attempt=request.resource_attempt,
            execution_input_id=execution_input.execution_input_id,
            crystal_id=parent.crystal_id,
            parent_state_id=parent.state_id,
            candidate_component_spec_id=candidate.component_spec_id,
            execution_status=execution_status,
            search_result_sha256=search_sha256,
            warnings=warnings,
        )
        atomic_write_json(result_json, result.model_dump(mode="json"))
        checksums = _write_checksums(output)
        if execution_status in {
            ExecutionStatus.FAILED_INPUT_CONTRACT,
            ExecutionStatus.FAILED_INFRASTRUCTURE,
        }:
            raise CompositionAttemptExecutionError(
                f"composition attempt failed as {execution_status.value}"
            )
        return CompositionAttemptExecutionOutput(
            result=result,
            result_json=result_json,
            child_state_json=None,
            checksums=checksums,
        )

    placement = collect_phaser_per_placement_outputs(
        PhaserPerPlacementRequest(
            crystal_id=parent.crystal_id,
            search_id=search_id,
            phaser_version=tool_version,
            output_directory=search_root,
            command_record=command_record,
            result_record=search_result_path,
            expected_components=expected_components,
            component_models=(
                *(
                    (component.label, path)
                    for component, path in zip(
                        parent.components,
                        parent_model_paths,
                        strict=True,
                    )
                ),
                (candidate.label, candidate_model),
            ),
        )
    )
    placement_inventory = PhaserPerPlacementInventory.model_validate_json(
        placement.inventory_json.read_text(encoding="utf-8")
    )
    if combined_llg is None or component_tfz is None:
        raise CompositionAttemptExecutionError(
            "completed composition attempt lacks component scores"
        )
    score = ComponentExpansionScoreEvidence.from_observed(
        execution_input=execution_input,
        placement_inventory=placement_inventory,
        score_ensemble_id=score_ensemble_id,
        combined_llg=combined_llg,
        component_tfz=component_tfz,
        packing_passed=top_solution_packed,
        warnings=warnings,
    )
    score_json = output / "component_score_evidence.json"
    atomic_write_json(score_json, score.model_dump(mode="json"))
    if output_mtz_path is None:
        raise CompositionAttemptExecutionError(
            "completed composition attempt lacks output MTZ"
        )
    output_mtz = (search_root / output_mtz_path).resolve(strict=True)
    if search_root not in output_mtz.parents:
        raise CompositionAttemptExecutionError("attempt output MTZ escaped its root")
    free_r_comparison: FreeRMembershipComparison = compare_free_r_membership(
        source=execution_input.free_r_identity,
        derived_mtz_path=output_mtz,
    )
    free_r_json = output / "free_r_membership.json"
    atomic_write_json(free_r_json, free_r_comparison.model_dump(mode="json"))
    candidate_lower, candidate_upper = _mass_bounds(candidate)
    support = (
        CompositionSupportState.PACKED
        if top_solution_packed
        and score.placement.observed_copy_count == candidate.requested_copy_count
        else CompositionSupportState.SEARCH_EVIDENCE_ONLY
    )
    child_state = CompositionState.from_content(
        crystal_id=parent.crystal_id,
        diffraction_dataset_id=parent.diffraction_dataset_id,
        diffraction_sha256=parent.diffraction_sha256,
        parent_state_id=parent.state_id,
        depth=parent.depth + 1,
        components=(*parent.components, candidate),
        placements=(*parent.placements, score.placement),
        combined_coordinate_sha256=combined_coordinate_sha256,
        combined_mtz_sha256=output_mtz_sha256,
        physical_mass_lower_da=parent.physical_mass_lower_da + candidate_lower,
        physical_mass_upper_da=parent.physical_mass_upper_da + candidate_upper,
        support_state=support,
        warnings=tuple((*parent.warnings, *warnings)),
    )
    child_state_json = output / "composition_state.json"
    atomic_write_json(child_state_json, child_state.model_dump(mode="json"))
    artifacts_json = output / "composition_state_artifacts.json"
    atomic_write_json(
        artifacts_json,
        {
            "schema_version": "1.0",
            "state_id": child_state.state_id,
            "combined_coordinate_path": (f"search/{combined_coordinate_path}"),
            "combined_coordinate_sha256": combined_coordinate_sha256,
            "combined_mtz_path": f"search/{output_mtz_path}",
            "combined_mtz_sha256": output_mtz_sha256,
            "placement_inventory_path": "search/phaser_per_placement_inventory.json",
            "placement_inventory_sha256": sha256_file(
                placement.inventory_json,
                progress=False,
            ),
        },
    )
    result = CompositionAttemptExecutionResult.from_content(
        attempt_id=attempt.attempt_id,
        resource_plan_id=attempt.resource_plan.resource_plan_id,
        resource_attempt=request.resource_attempt,
        execution_input_id=execution_input.execution_input_id,
        crystal_id=parent.crystal_id,
        parent_state_id=parent.state_id,
        candidate_component_spec_id=candidate.component_spec_id,
        execution_status=execution_status,
        search_result_sha256=search_sha256,
        placement_inventory_sha256=sha256_file(
            placement.inventory_json,
            progress=False,
        ),
        score_evidence_id=score.score_evidence_id,
        score_evidence_sha256=sha256_file(score_json, progress=False),
        child_state_id=child_state.state_id,
        child_state_sha256=sha256_file(child_state_json, progress=False),
        free_r_comparison_id=free_r_comparison.comparison_id,
        free_r_comparison_sha256=sha256_file(free_r_json, progress=False),
        child_support_state=child_state.support_state,
        warnings=warnings,
    )
    atomic_write_json(result_json, result.model_dump(mode="json"))
    return CompositionAttemptExecutionOutput(
        result=result,
        result_json=result_json,
        child_state_json=child_state_json,
        checksums=_write_checksums(output),
    )


__all__ = [
    "CompositionAttemptExecutionError",
    "CompositionAttemptExecutionOutput",
    "CompositionAttemptExecutionRequest",
    "CompositionAttemptExecutionResult",
    "execute_composition_attempt",
]
