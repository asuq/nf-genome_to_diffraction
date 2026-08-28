"""Tests for the fixed private unknown-discovery input archive."""

import json
import tarfile
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.hpc.unknown_inputs import (
    UNKNOWN_DISCOVERY_SPEC_RELATIVE,
    UnknownDiscoveryInputError,
    _validate_localisation_authority,
    build_unknown_discovery_input_bundle,
    validate_unknown_discovery_input_tree,
)
from genome_to_diffraction.schemas.v2 import (
    ExecutionToolIdentity,
    PhaseIIIExecutionIdentity,
)
from tests.support.unknown_pass1_fixture import (
    materialise_neutral_localisation_fixture,
    materialise_unknown_pass1_public_fixture,
)


def _inputs(root: Path):
    fixture_root = root / "fixture"
    fixture_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(fixture_root)
    afdb_map = root / "afdb_accession_map.tsv"
    afdb_map.write_text(
        "source_record_id\tuniprot_accession\n",
        encoding="ascii",
    )
    localisation = materialise_neutral_localisation_fixture(
        root,
        gel_evidence=fixture_root / "inputs/gel_evidence.json",
    )
    crystal_manifest = root / "phase3_crystals.json"
    atomic_write_json(
        crystal_manifest,
        {
            "schema_version": "1.0",
            "crystals": [
                {
                    "crystal_id": crystal_id,
                    "mtz": f"/approved/p0/inputs/{crystal_id}.mtz",
                    "catalogue_id": "public_catalogue",
                    "free_r_test_value": 0,
                    "allow_remote_sequence_submission": False,
                }
                for crystal_id in sorted(item.crystal_id for item in fixture.crystals)
            ],
        },
    )
    spec = root / UNKNOWN_DISCOVERY_SPEC_RELATIVE
    spec.parent.mkdir(parents=True)
    atomic_write_json(
        spec,
        {
            "schema_version": "1.0",
            "crystallographic_review_stage": str(fixture.review_stage),
            "execution_identity": str(fixture.execution_identity),
            "afdb_accession_map": str(afdb_map),
            "crystal_manifest": str(crystal_manifest),
            "localisation_bundle": str(localisation),
        },
    )
    spec.chmod(0o600)
    return fixture, afdb_map, spec


def test_unknown_discovery_archive_is_deterministic(tmp_path: Path) -> None:
    fixture, _, _ = _inputs(tmp_path)

    first = build_unknown_discovery_input_bundle(
        repository=tmp_path,
        archive_path=tmp_path / "first.tar",
    )
    second = build_unknown_discovery_input_bundle(
        repository=tmp_path,
        archive_path=tmp_path / "second.tar",
    )

    assert first.archive_sha256 == second.archive_sha256
    assert (
        first.execution_identity_id
        == fixture.inventory.execution_identity.execution_identity_id
    )
    assert first.crystal_ids == tuple(sorted(first.crystal_ids))
    with tarfile.open(first.archive_path, mode="r") as archive:
        members = tuple(item.name for item in archive.getmembers())
    assert "unknown_discovery_input_manifest.json" in members
    assert "phase3_execution_identity.json" in members
    assert "afdb_accession_map.tsv" in members
    assert "phase3_crystals.json" in members
    assert "localisation_bundle/first_wave_policy.json" in members
    assert any(name.startswith("crystallographic_review_stage/") for name in members)
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(first.archive_path, mode="r") as archive:
        archive.extractall(extracted, filter="data")
    validate_unknown_discovery_input_tree(
        extracted,
        expected_input_id=first.input_id,
        expected_execution_identity_id=first.execution_identity_id,
        expected_review_stage_index_id=first.review_stage_index_id,
    )


def test_changed_extracted_file_fails(tmp_path: Path) -> None:
    _inputs(tmp_path)
    bundle = build_unknown_discovery_input_bundle(
        repository=tmp_path,
        archive_path=tmp_path / "inputs.tar",
    )
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(bundle.archive_path, mode="r") as archive:
        archive.extractall(extracted, filter="data")
    execution = extracted / "phase3_execution_identity.json"
    execution.write_bytes(execution.read_bytes() + b"\n")

    with pytest.raises(UnknownDiscoveryInputError, match="changed"):
        validate_unknown_discovery_input_tree(
            extracted,
            expected_input_id=bundle.input_id,
            expected_execution_identity_id=bundle.execution_identity_id,
            expected_review_stage_index_id=bundle.review_stage_index_id,
        )


def test_unknown_discovery_spec_requires_mode_0600(tmp_path: Path) -> None:
    _, _, spec = _inputs(tmp_path)
    spec.chmod(0o644)

    with pytest.raises(UnknownDiscoveryInputError, match="mode-0600"):
        build_unknown_discovery_input_bundle(
            repository=tmp_path,
            archive_path=tmp_path / "inputs.tar",
        )


def test_cross_execution_review_stage_fails(tmp_path: Path) -> None:
    fixture, afdb_map, spec = _inputs(tmp_path)
    execution = PhaseIIIExecutionIdentity.model_validate_json(
        fixture.execution_identity.read_bytes()
    )
    values = execution.model_dump(mode="python")
    values.pop("execution_identity_id")
    values["source_commit"] = "9" * 40
    changed = PhaseIIIExecutionIdentity.from_content(**values)
    changed_path = tmp_path / "changed_execution.json"
    atomic_write_json(changed_path, changed.model_dump(mode="json"))
    atomic_write_json(
        spec,
        {
            "schema_version": "1.0",
            "crystallographic_review_stage": str(fixture.review_stage),
            "execution_identity": str(changed_path),
            "afdb_accession_map": str(afdb_map),
            "crystal_manifest": str(tmp_path / "phase3_crystals.json"),
            "localisation_bundle": str(tmp_path / "localisation"),
        },
    )
    spec.chmod(0o600)

    with pytest.raises(UnknownDiscoveryInputError, match="identities differ"):
        build_unknown_discovery_input_bundle(
            repository=tmp_path,
            archive_path=tmp_path / "inputs.tar",
        )


def test_symlinked_afdb_map_fails(tmp_path: Path) -> None:
    fixture, afdb_map, spec = _inputs(tmp_path)
    linked = tmp_path / "linked_map.tsv"
    linked.symlink_to(afdb_map)
    atomic_write_json(
        spec,
        {
            "schema_version": "1.0",
            "crystallographic_review_stage": str(fixture.review_stage),
            "execution_identity": str(fixture.execution_identity),
            "afdb_accession_map": str(linked),
            "crystal_manifest": str(tmp_path / "phase3_crystals.json"),
            "localisation_bundle": str(tmp_path / "localisation"),
        },
    )
    spec.chmod(0o600)

    with pytest.raises(UnknownDiscoveryInputError, match="must not be a symlink"):
        build_unknown_discovery_input_bundle(
            repository=tmp_path,
            archive_path=tmp_path / "inputs.tar",
        )


def test_unknown_discovery_requires_explicit_free_r_test_values(
    tmp_path: Path,
) -> None:
    _inputs(tmp_path)
    manifest_path = tmp_path / "phase3_crystals.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["crystals"][0]["free_r_test_value"] = None
    atomic_write_json(manifest_path, manifest)

    with pytest.raises(UnknownDiscoveryInputError, match="explicit Free-R"):
        build_unknown_discovery_input_bundle(
            repository=tmp_path,
            archive_path=tmp_path / "inputs.tar",
        )


def test_localisation_runtime_must_match_execution_identity(tmp_path: Path) -> None:
    fixture, _, _ = _inputs(tmp_path)
    execution = PhaseIIIExecutionIdentity.model_validate_json(
        fixture.execution_identity.read_bytes()
    )
    tools = tuple(
        ExecutionToolIdentity.from_content(
            name=tool.name,
            version=tool.version,
            executable_sha256="9" * 64,
            adapter_version=tool.adapter_version,
        )
        if tool.name == "PSORTb"
        else tool
        for tool in execution.tools
    )
    values = execution.model_dump(mode="python")
    values.pop("execution_identity_id")
    values["tools"] = tuple(sorted(tools, key=lambda item: item.name))
    changed = PhaseIIIExecutionIdentity.from_content(**values)

    with pytest.raises(UnknownDiscoveryInputError, match="runtime PSORTb differs"):
        _validate_localisation_authority(
            root=tmp_path / "localisation",
            execution=changed,
        )
