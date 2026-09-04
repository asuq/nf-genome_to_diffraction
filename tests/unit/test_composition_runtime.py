"""Focused tests for the real one-item Phase III composition executor."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.execution import (
    CompositionAttemptExecutionRequest,
    composition_runtime,
    execute_composition_attempt,
    write_composition_attempt_inventory,
)
from genome_to_diffraction.mr import PartnerSearchRequest, PhaserPerPlacementRequest
from genome_to_diffraction.schemas.manifests import PhenixInstallManifest
from genome_to_diffraction.schemas.v2 import (
    ComponentIdentitySupport,
    ComponentPlacement,
    CompositionAttemptInventory,
    CompositionSupportState,
    ExecutionArtifactIdentity,
    ExecutionToolIdentity,
    PhaseIIIExecutionIdentity,
    diffraction_dataset_id,
)
from genome_to_diffraction.status import ExecutionStatus
from tests.support.unknown_pass1_fixture import (
    materialise_unknown_pass1_public_fixture,
)
from tests.unit import test_composition_attempt_inventory as inventory_fixture

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: ExecutionStatus,
) -> tuple[CompositionAttemptExecutionRequest, CompositionAttemptInventory]:
    mtz = tmp_path / "input.mtz"
    mtz.write_bytes(b"synthetic MTZ bytes\n")
    mtz_sha256 = _sha(mtz)
    monkeypatch.setattr(inventory_fixture, "MTZ_SHA256", mtz_sha256)
    monkeypatch.setattr(
        inventory_fixture,
        "DIFFRACTION_DATASET_ID",
        diffraction_dataset_id(
            crystal_id=inventory_fixture.CRYSTAL_ID,
            mtz_sha256=mtz_sha256,
        ),
    )
    identity_root = tmp_path / "identity-fixture"
    identity_root.mkdir()
    identity_fixture = materialise_unknown_pass1_public_fixture(identity_root)
    base_identity = PhaseIIIExecutionIdentity.model_validate_json(
        identity_fixture.execution_identity.read_bytes()
    )
    legacy_phenix = PhenixInstallManifest.model_validate_json(
        (STUBS / "phenix_install_manifest.json").read_bytes()
    )
    strict_commands = tuple(
        command.model_copy(
            update={
                "executable_sha256": hashlib.sha256(command.name.encode()).hexdigest()
            }
        )
        for command in legacy_phenix.required_commands
    )
    phenix = legacy_phenix.model_copy(update={"required_commands": strict_commands})
    phenix_manifest = tmp_path / "phenix_manifest.json"
    atomic_write_json(phenix_manifest, phenix.model_dump(mode="json"))
    strict_by_name = {command.name: command for command in phenix.required_commands}
    tools = tuple(
        sorted(
            (
                ExecutionToolIdentity.from_content(
                    name=tool.name,
                    version=(
                        strict_by_name[tool.name].version_text or phenix.phenix_version
                        if tool.name in strict_by_name
                        else tool.version
                    ),
                    executable_sha256=(
                        strict_by_name[tool.name].executable_sha256
                        if tool.name in strict_by_name
                        else tool.executable_sha256
                    ),
                    adapter_version=(
                        "phase3-strict-phenix-manifest-v1"
                        if tool.name.startswith("phenix.")
                        else tool.adapter_version
                    ),
                )
                for tool in base_identity.tools
            ),
            key=lambda item: (item.name, item.tool_identity_id),
        )
    )
    identity_values = base_identity.model_dump(mode="python")
    identity_values.pop("execution_identity_id")
    identity_values["tools"] = tools
    identity_values["crystal_artifacts"] = (
        ExecutionArtifactIdentity.from_content(
            scope="crystal",
            owner_id=inventory_fixture.CRYSTAL_ID,
            role="mtz",
            sha256=mtz_sha256,
            size_bytes=mtz.stat().st_size,
            release_or_source="synthetic composition runtime",
        ),
    )
    identity = PhaseIIIExecutionIdentity.from_content(**identity_values)
    execution_identity = tmp_path / "phase3_execution_identity.json"
    atomic_write_json(execution_identity, identity.model_dump(mode="json"))
    monkeypatch.setattr(
        inventory_fixture,
        "EXECUTION_IDENTITY_ID",
        identity.execution_identity_id,
    )
    parent = inventory_fixture._parent(1)
    _, inventory = inventory_fixture._inventory(
        parents=(parent,),
        candidates=(
            inventory_fixture._candidate(
                parent=parent,
                rank=1,
                sequence_index=2,
            ),
        ),
    )
    inventory_path = write_composition_attempt_inventory(
        inventory,
        tmp_path / "composition_attempt_inventory.json",
    )
    fixed_root = tmp_path / "fixed"
    fixed_root.mkdir()
    fixed_path = fixed_root / "component_A.pdb"
    fixed_path.write_text("ATOM FIXED A\n", encoding="ascii")
    model_registry = tmp_path / "models"
    model_registry.mkdir()
    parent_model = model_registry / "parent.pdb"
    candidate_model = model_registry / "candidate.pdb"
    parent_model.write_text("ATOM MODEL A\n", encoding="ascii")
    candidate_model.write_text("ATOM MODEL B\n", encoding="ascii")
    fake_registry = SimpleNamespace(
        root=model_registry,
        manifest=SimpleNamespace(
            registry_id=inventory.model_registry_id,
            sequence_groups=(),
        ),
    )
    monkeypatch.setattr(
        composition_runtime,
        "load_all_eligible_model_registry",
        lambda _path: fake_registry,
    )
    monkeypatch.setattr(
        composition_runtime,
        "_fixed_paths",
        lambda _root, _execution: (fixed_path,),
    )
    candidate = inventory.execution_inputs[0].selected_candidate.hypothesis.component
    monkeypatch.setattr(
        composition_runtime,
        "_registry_entry_path",
        lambda _registry, *, model_id, model_sha256: (
            candidate_model if model_id == candidate.model_id else parent_model
        ),
    )
    monkeypatch.setattr(
        composition_runtime,
        "_sequence_groups",
        lambda _path, _required, output: output.write_text(
            "synthetic complete sequence-group subset\n",
            encoding="ascii",
        ),
    )
    monkeypatch.setattr(
        composition_runtime,
        "build_free_r_identity",
        lambda **_kwargs: inventory.free_r_identity,
    )

    def fake_search(**kwargs: object) -> SimpleNamespace:
        output_value = kwargs["output_directory"]
        assert isinstance(output_value, Path)
        output = output_value
        output.mkdir()
        result_path = output / "component_search_result.json"
        result_path.write_text(
            json.dumps({"execution_status": status.value}) + "\n",
            encoding="ascii",
        )
        if status is not ExecutionStatus.COMPLETED_HIT:
            return SimpleNamespace(
                execution_status=status,
                search_id="search_no_hit",
                tool_version="Phaser test",
                combined_llg=None,
                candidate_tfz=None,
                partner_tfz=None,
                top_solution_packed=False,
                combined_coordinate_path=None,
                combined_coordinate_sha256=None,
                output_mtz_path=None,
                output_mtz_sha256=None,
            )
        coordinate = output / "PHASER.1.pdb"
        output_mtz = output / "PHASER.1.mtz"
        coordinate.write_text("ATOM COMBINED A B\n", encoding="ascii")
        output_mtz.write_bytes(mtz.read_bytes())
        (output / "phaser_command.json").write_text("{}\n", encoding="ascii")
        return SimpleNamespace(
            execution_status=status,
            search_id="search_B",
            tool_version="Phaser test",
            combined_llg=1150.0,
            candidate_tfz=14.0,
            partner_tfz=14.0,
            top_solution_packed=True,
            combined_coordinate_path=coordinate.name,
            combined_coordinate_sha256=_sha(coordinate),
            output_mtz_path=output_mtz.name,
            output_mtz_sha256=_sha(output_mtz),
        )

    monkeypatch.setattr(composition_runtime, "run_multi_fixed_search", fake_search)

    def fake_partner(request: PartnerSearchRequest) -> SimpleNamespace:
        output = request.output_directory
        native = fake_search(output_directory=output)
        command = output / "phaser_command.json"
        if not command.exists():
            command.write_text("{}\n", encoding="ascii")
        return SimpleNamespace(
            result=native,
            result_json=output / "component_search_result.json",
            command_json=command,
        )

    monkeypatch.setattr(composition_runtime, "run_partner_search", fake_partner)
    if status is ExecutionStatus.COMPLETED_HIT:
        placement = ComponentPlacement.from_content(
            component_spec_id=candidate.component_spec_id,
            component_label=candidate.label,
            sequence_group_id=candidate.sequence_group_id,
            model_id=candidate.model_id,
            model_sha256=candidate.model_sha256,
            requested_copy_count=candidate.requested_copy_count,
            observed_copy_count=candidate.requested_copy_count,
            execution_status=ExecutionStatus.COMPLETED_HIT,
            component_tfz=14.0,
            incremental_llg=150.0,
            packing_passed=True,
            coordinate_sha256="8" * 64,
            identity_support=ComponentIdentitySupport.UNRESOLVED,
        )
        fake_inventory = SimpleNamespace()

        class FakeInventoryModel:
            @staticmethod
            def model_validate_json(_payload: str) -> SimpleNamespace:
                return fake_inventory

        class FakeScore:
            score_evidence_id = "compscore_" + "7" * 64

            def __init__(self) -> None:
                self.placement = placement

            def model_dump(self, *, mode: str) -> dict[str, str]:
                assert mode == "json"
                return {
                    "schema_version": "2.0",
                    "score_evidence_id": self.score_evidence_id,
                }

        class FakeScoreFactory:
            @staticmethod
            def from_observed(**_kwargs: object) -> FakeScore:
                return FakeScore()

        def fake_collect(request: PhaserPerPlacementRequest) -> SimpleNamespace:
            path = request.output_directory / "phaser_per_placement_inventory.json"
            path.write_text("{}\n", encoding="ascii")
            return SimpleNamespace(inventory_json=path)

        comparison = SimpleNamespace(
            comparison_id="freercompare_" + "6" * 64,
            model_dump=lambda *, mode: {
                "schema_version": "2.0",
                "comparison_id": "freercompare_" + "6" * 64,
            },
        )
        monkeypatch.setattr(
            composition_runtime,
            "PhaserPerPlacementInventory",
            FakeInventoryModel,
        )
        monkeypatch.setattr(
            composition_runtime,
            "ComponentExpansionScoreEvidence",
            FakeScoreFactory,
        )
        monkeypatch.setattr(
            composition_runtime,
            "collect_phaser_per_placement_outputs",
            fake_collect,
        )
        monkeypatch.setattr(
            composition_runtime,
            "compare_free_r_membership",
            lambda **_kwargs: comparison,
        )
    sequence_groups = tmp_path / "sequence_groups.jsonl"
    preflight = tmp_path / "preflight.jsonl"
    for path in (sequence_groups, preflight):
        path.write_text("stub\n", encoding="ascii")
    return (
        CompositionAttemptExecutionRequest(
            attempt_inventory=inventory_path,
            attempt_id=inventory.attempts[0].attempt_id,
            fixed_coordinate_root=fixed_root,
            model_registry=model_registry,
            sequence_groups_jsonl=sequence_groups,
            preflight_jsonl=preflight,
            mtz=mtz,
            phenix_manifest=phenix_manifest,
            execution_identity=execution_identity,
            output_directory=tmp_path / "output",
            threads=8,
        ),
        inventory,
    )


def test_composition_runtime_emits_packed_claim_free_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, inventory = _request(
        tmp_path,
        monkeypatch,
        status=ExecutionStatus.COMPLETED_HIT,
    )

    output = execute_composition_attempt(request)

    assert output.result.execution_status is ExecutionStatus.COMPLETED_HIT
    assert output.result.child_support_state is CompositionSupportState.PACKED
    assert output.result.exact_identity_claimed is False
    assert output.result.complete_composition_claimed is False
    assert output.child_state_json is not None
    child = json.loads(output.child_state_json.read_text(encoding="utf-8"))
    assert child["parent_state_id"] == inventory.parent_states[0].state_id
    assert child["depth"] == 2
    assert child["support_state"] == "packed"
    assert output.checksums.is_file()


def test_composition_runtime_retains_no_hit_without_child_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, _ = _request(
        tmp_path,
        monkeypatch,
        status=ExecutionStatus.COMPLETED_NO_HIT,
    )

    output = execute_composition_attempt(request)

    assert output.result.execution_status is ExecutionStatus.COMPLETED_NO_HIT
    assert output.result.child_state_id is None
    assert output.child_state_json is None
    assert not (request.output_directory / "composition_state.json").exists()
    assert output.checksums.is_file()


def test_composition_runtime_fails_closed_on_infrastructure_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, _ = _request(
        tmp_path,
        monkeypatch,
        status=ExecutionStatus.FAILED_INFRASTRUCTURE,
    )

    with pytest.raises(
        composition_runtime.CompositionAttemptExecutionError,
        match="failed as failed_infrastructure",
    ):
        execute_composition_attempt(request)

    assert (request.output_directory / "composition_attempt_execution.json").is_file()
    assert (request.output_directory / "composition_attempt_checksums.sha256").is_file()


def test_composition_runtime_rejects_stale_adapter_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, inventory = _request(
        tmp_path,
        monkeypatch,
        status=ExecutionStatus.COMPLETED_NO_HIT,
    )
    identity = PhaseIIIExecutionIdentity.model_validate_json(
        request.execution_identity.read_bytes()
    )
    values = identity.model_dump(mode="python")
    values.pop("execution_identity_id")
    values["adapter_versions"] = tuple(
        (name, "stale-composition-adapter")
        if name == "phase3_composition_attempt"
        else (name, version)
        for name, version in identity.adapter_versions
    )
    stale = PhaseIIIExecutionIdentity.from_content(**values)

    with pytest.raises(
        composition_runtime.CompositionAttemptExecutionError,
        match="lacks current composition adapters",
    ):
        composition_runtime._verify_execution_authority(
            identity=stale,
            execution_input=inventory.execution_inputs[0],
            phenix_manifest=request.phenix_manifest,
            mtz=request.mtz,
        )


def test_composition_runtime_rejects_swapped_phenix_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, inventory = _request(
        tmp_path,
        monkeypatch,
        status=ExecutionStatus.COMPLETED_NO_HIT,
    )
    identity = PhaseIIIExecutionIdentity.model_validate_json(
        request.execution_identity.read_bytes()
    )
    manifest = PhenixInstallManifest.model_validate_json(
        request.phenix_manifest.read_bytes()
    )
    commands = list(manifest.required_commands)
    commands[0] = commands[0].model_copy(update={"executable_sha256": "f" * 64})
    changed = manifest.model_copy(update={"required_commands": tuple(commands)})
    changed_path = tmp_path / "changed_phenix_manifest.json"
    atomic_write_json(changed_path, changed.model_dump(mode="json"))

    with pytest.raises(
        composition_runtime.CompositionAttemptExecutionError,
        match="Phenix runtime differs",
    ):
        composition_runtime._verify_execution_authority(
            identity=identity,
            execution_input=inventory.execution_inputs[0],
            phenix_manifest=changed_path,
            mtz=request.mtz,
        )


def test_composition_runtime_rejects_missing_parent_score_evidence(
    tmp_path: Path,
) -> None:
    parent = inventory_fixture._parent(1)
    _, inventory = inventory_fixture._inventory(
        parents=(parent,),
        candidates=(
            inventory_fixture._candidate(
                parent=parent,
                rank=1,
                sequence_index=2,
            ),
        ),
    )
    fixed_root = tmp_path / "fixed"
    fixed_root.mkdir()

    with pytest.raises(
        composition_runtime.CompositionAttemptExecutionError,
        match="parent score evidence is absent",
    ):
        composition_runtime._fixed_paths(
            fixed_root,
            inventory.execution_inputs[0],
        )
