"""Focused Phase III raw-input and runtime cache-identity tests."""

from collections.abc import Mapping
from typing import cast

import pytest
from pydantic import ValidationError

from genome_to_diffraction.schemas.v2.execution import (
    ExecutionArtifactIdentity,
    ExecutionToolIdentity,
    PhaseIIIExecutionIdentity,
)

_PHENIX = (
    "phenix.maps",
    "phenix.phaser",
    "phenix.process_predicted_model",
    "phenix.refine",
    "phenix.reflection_file_converter",
    "phenix.sequence_from_map",
    "phenix.xtriage",
)


def _artifact(
    scope: str,
    owner_id: str,
    role: str,
    digest_character: str,
) -> ExecutionArtifactIdentity:
    return ExecutionArtifactIdentity.from_content(
        scope=scope,
        owner_id=owner_id,
        role=role,
        sha256=digest_character * 64,
        size_bytes=100,
        release_or_source="frozen-test-source",
    )


def _tool(name: str, index: int) -> ExecutionToolIdentity:
    return ExecutionToolIdentity.from_content(
        name=name,
        version="2.1-6048",
        executable_sha256=f"{index:x}" * 64,
        adapter_version="phase3-test-v1",
    )


def _kwargs() -> dict[str, object]:
    catalogue = tuple(
        sorted(
            (
                _artifact("catalogue", "catalogue_01", "annotation_gff", "a"),
                _artifact("catalogue", "catalogue_01", "proteome_faa", "b"),
            ),
            key=lambda item: (item.owner_id, item.role, item.artifact_id),
        )
    )
    crystals = tuple(
        sorted(
            (
                _artifact("crystal", "AD4", "mtz", "c"),
                _artifact("crystal", "CD4", "mtz", "d"),
                _artifact("crystal", "CD6", "mtz", "e"),
            ),
            key=lambda item: (item.owner_id, item.role, item.artifact_id),
        )
    )
    databases = (_artifact("database", "pdb_2026_08", "database_manifest", "f"),)
    tools = tuple(
        sorted(
            (_tool(name, index) for index, name in enumerate(_PHENIX, start=1)),
            key=lambda item: (item.name, item.tool_identity_id),
        )
    )
    return {
        "source_commit": "1" * 40,
        "source_tree": "2" * 40,
        "nf_helper_commit": "3" * 40,
        "pixi_lock_sha256": "4" * 64,
        "execution_policy_sha256": "5" * 64,
        "catalogue_artifacts": catalogue,
        "crystal_artifacts": crystals,
        "database_artifacts": databases,
        "tools": tools,
        "adapter_versions": (
            ("composition_planner", "phase3-round-robin-v1"),
            ("diffraction_selection", "phase3-diffraction-selection-v1"),
        ),
    }


def _identity(values: Mapping[str, object] | None = None) -> PhaseIIIExecutionIdentity:
    payload = _kwargs()
    if values:
        payload.update(values)
    return PhaseIIIExecutionIdentity.from_content(**payload)


def test_complete_execution_identity_is_content_addressed() -> None:
    identity = _identity()

    assert identity.execution_identity_id.startswith("phase3exec_")
    assert identity.remote_sequence_submission is False
    assert identity.compute_network_access is False


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("source_commit", "6" * 40),
        ("source_tree", "7" * 40),
        ("nf_helper_commit", "8" * 40),
        ("pixi_lock_sha256", "9" * 64),
        ("execution_policy_sha256", "a" * 64),
        (
            "adapter_versions",
            (
                ("composition_planner", "phase3-round-robin-v2"),
                ("diffraction_selection", "phase3-diffraction-selection-v1"),
            ),
        ),
    ),
)
def test_source_environment_and_adapter_mutations_change_identity(
    field: str, replacement: object
) -> None:
    baseline = _identity()
    changed = _identity({field: replacement})

    assert changed.execution_identity_id != baseline.execution_identity_id


def test_raw_catalogue_mtz_database_and_tool_mutations_change_identity() -> None:
    baseline = _identity()
    base = _kwargs()

    catalogue = list(
        cast(tuple[ExecutionArtifactIdentity, ...], base["catalogue_artifacts"])
    )
    catalogue[0] = _artifact("catalogue", "catalogue_01", "annotation_gff", "0")
    changed_catalogue = _identity(
        {
            "catalogue_artifacts": tuple(
                sorted(
                    catalogue,
                    key=lambda item: (item.owner_id, item.role, item.artifact_id),
                )
            )
        }
    )

    crystals = list(
        cast(tuple[ExecutionArtifactIdentity, ...], base["crystal_artifacts"])
    )
    crystals[0] = _artifact("crystal", "AD4", "mtz", "1")
    changed_crystal = _identity(
        {
            "crystal_artifacts": tuple(
                sorted(
                    crystals,
                    key=lambda item: (item.owner_id, item.role, item.artifact_id),
                )
            )
        }
    )
    changed_database = _identity(
        {
            "database_artifacts": (
                _artifact("database", "pdb_2026_08", "database_manifest", "2"),
            )
        }
    )

    tools = list(cast(tuple[ExecutionToolIdentity, ...], base["tools"]))
    tools[0] = ExecutionToolIdentity.from_content(
        name=tools[0].name,
        version=tools[0].version,
        executable_sha256="3" * 64,
        adapter_version=tools[0].adapter_version,
    )
    changed_tool = _identity(
        {
            "tools": tuple(
                sorted(tools, key=lambda item: (item.name, item.tool_identity_id))
            )
        }
    )

    changed_ids = {
        changed_catalogue.execution_identity_id,
        changed_crystal.execution_identity_id,
        changed_database.execution_identity_id,
        changed_tool.execution_identity_id,
    }
    assert baseline.execution_identity_id not in changed_ids
    assert len(changed_ids) == 4


def test_missing_annotation_mtz_or_phenix_identity_fails_closed() -> None:
    values = _kwargs()
    catalogue_artifacts = cast(
        tuple[ExecutionArtifactIdentity, ...], values["catalogue_artifacts"]
    )
    proteome_only = tuple(
        item for item in catalogue_artifacts if item.role == "proteome_faa"
    )
    with pytest.raises(ValidationError, match="lacks raw annotation identity"):
        _identity({"catalogue_artifacts": proteome_only})

    with pytest.raises(ValidationError, match="bind its raw MTZ"):
        _identity(
            {"crystal_artifacts": (_artifact("crystal", "AD4", "metadata", "c"),)}
        )

    with pytest.raises(ValidationError, match="lacks required Phenix tools"):
        _identity(
            {"tools": cast(tuple[ExecutionToolIdentity, ...], values["tools"])[:-1]}
        )


def test_unsorted_inventory_fails_instead_of_changing_task_order() -> None:
    catalogue = tuple(
        reversed(
            cast(
                tuple[ExecutionArtifactIdentity, ...],
                _kwargs()["catalogue_artifacts"],
            )
        )
    )

    with pytest.raises(ValidationError, match="must be unique and sorted"):
        _identity({"catalogue_artifacts": catalogue})


def test_duplicate_logical_artifact_or_tool_identity_fails() -> None:
    values = _kwargs()
    catalogue = list(
        cast(tuple[ExecutionArtifactIdentity, ...], values["catalogue_artifacts"])
    )
    catalogue.append(_artifact("catalogue", "catalogue_01", "proteome_faa", "0"))
    catalogue.sort(key=lambda item: (item.owner_id, item.role, item.artifact_id))
    with pytest.raises(ValidationError, match="owner/role values must be unique"):
        _identity({"catalogue_artifacts": tuple(catalogue)})

    tools = list(cast(tuple[ExecutionToolIdentity, ...], values["tools"]))
    tools.append(
        ExecutionToolIdentity.from_content(
            name=tools[0].name,
            version=tools[0].version,
            executable_sha256="0" * 64,
            adapter_version=tools[0].adapter_version,
        )
    )
    tools.sort(key=lambda item: (item.name, item.tool_identity_id))
    with pytest.raises(ValidationError, match="tool names must be unique"):
        _identity({"tools": tuple(tools)})
