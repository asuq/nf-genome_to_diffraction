"""Tests for bounded Phase III login-side provider staging."""

from dataclasses import replace
from pathlib import Path

import pytest

import genome_to_diffraction.structure_search.phase3_login_stage as stage_module
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.results import (
    CoordinateSourceRecord,
    SearchScientificStatus,
    SequenceGroupRecord,
    StructuralSearchResult,
)
from genome_to_diffraction.status import ExecutionStatus
from genome_to_diffraction.structure_search import (
    PhaseIIIProviderLoginStageError,
    PhaseIIIProviderLoginStageRequest,
    build_phase3_provider_discovery_package,
    publish_phase3_offline_provider_input,
    stage_phase3_provider_coordinates,
    validate_phase3_provider_login_stage,
)
from genome_to_diffraction.structure_search.afdb_exact import (
    AfdbExactOutput,
    AfdbExactRequest,
)
from genome_to_diffraction.structure_search.pdb_coordinates import (
    PdbCoordinateRegistrationOutput,
    PdbCoordinateRegistrationRequest,
)
from tests.unit.test_phase3_discovery_package import _request


def _fake_pdb_registration(
    request: PdbCoordinateRegistrationRequest,
) -> PdbCoordinateRegistrationOutput:
    output = request.output_directory
    output.mkdir()
    coordinate = output / "cached-public-coordinate.cif"
    coordinate.write_text("data_public_stub\n", encoding="ascii")
    source = CoordinateSourceRecord(
        schema_version="1.0",
        coordinate_id="coord_public_login_stub",
        provider="pdb",
        provider_accession="1ABC:1:A",
        retrieval_date="2026-08-25T00:00:00Z",
        source_release="public-unit-fixture",
        coordinate_path=str(coordinate.resolve()),
        coordinate_sha256=sha256_file(coordinate, progress=False),
        confidence_summary={"coordinate_kind": "experimental"},
        license_or_provenance="public unit fixture",
    )
    sources_path = output / "coordinate_sources.jsonl"
    mappings_path = output / "coordinate_hit_mappings.jsonl"
    manifest_path = output / "registration_manifest.json"
    atomic_write_text(sources_path, f"{canonical_json_text(source)}\n")
    atomic_write_text(mappings_path, "")
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "registration_id": "coordreg_public_login_stub",
            "selected_mapping_count": 0,
            "coordinate_source_count": 1,
        },
    )
    return PdbCoordinateRegistrationOutput(
        coordinate_sources=(source,),
        mappings=(),
        coordinate_sources_jsonl=sources_path,
        mappings_jsonl=mappings_path,
        manifest_json=manifest_path,
    )


def _fake_pdb_registration_shared_object(
    request: PdbCoordinateRegistrationRequest,
) -> PdbCoordinateRegistrationOutput:
    registered = _fake_pdb_registration(request)
    first = registered.coordinate_sources[0]
    second = first.model_copy(
        update={
            "coordinate_id": "coord_public_login_stub_second_entity",
            "provider_accession": "1ABC:2:B",
        }
    )
    atomic_write_text(
        registered.coordinate_sources_jsonl,
        f"{canonical_json_text(first)}\n{canonical_json_text(second)}\n",
    )
    return replace(registered, coordinate_sources=(first, second))


def _fake_afdb_exact(request: AfdbExactRequest) -> AfdbExactOutput:
    output = request.output_directory
    output.mkdir()
    groups = tuple(
        SequenceGroupRecord.model_validate_json(line)
        for line in request.sequence_groups_jsonl.read_text(
            encoding="utf-8"
        ).splitlines()
    )
    raw = output / "raw"
    raw.mkdir()
    raw_result = raw / "afdb-results.json"
    raw_log = raw / "afdb.log"
    raw_result.write_text("{}\n", encoding="ascii")
    raw_log.write_text("no explicit accessions\n", encoding="ascii")
    results = tuple(
        StructuralSearchResult(
            schema_version="1.0",
            search_id=f"afdb_no_hit_{group.sequence_group_id}",
            sequence_group_id=group.sequence_group_id,
            provider="afdb_exact",
            database_id="afdb_public_unit_fixture",
            tool="AlphaFold DB prediction API",
            tool_version="unit-fixture",
            adapter_version="afdb-exact-v3",
            cache_key="a" * 64,
            execution_status=ExecutionStatus.COMPLETED_NO_HIT,
            scientific_status=SearchScientificStatus.NO_HIT,
            hit_count=0,
            hits=(),
            raw_result_pointer="raw/afdb-results.json",
            raw_result_sha256=sha256_file(raw_result, progress=False),
            command_log_pointer="raw/afdb.log",
            command_log_sha256=sha256_file(raw_log, progress=False),
        )
        for group in groups
    )
    results_path = output / "search_results.jsonl"
    hits_path = output / "structural_hits.jsonl"
    coordinates_path = output / "coordinate_sources.jsonl"
    manifest_path = output / "search_manifest.json"
    atomic_write_text(
        results_path,
        "".join(f"{canonical_json_text(item)}\n" for item in results),
    )
    atomic_write_text(hits_path, "")
    atomic_write_text(coordinates_path, "")
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "search_count": len(results),
            "coordinate_source_count": 0,
        },
    )
    return AfdbExactOutput(
        results=results,
        coordinate_sources=(),
        results_jsonl=results_path,
        hits_jsonl=hits_path,
        coordinate_sources_jsonl=coordinates_path,
        search_manifest=manifest_path,
    )


def _stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    discovery = build_phase3_provider_discovery_package(_request(tmp_path))
    monkeypatch.setattr(
        stage_module,
        "register_pdb_coordinates",
        _fake_pdb_registration,
    )
    monkeypatch.setattr(stage_module, "search_afdb_exact", _fake_afdb_exact)
    staged = stage_phase3_provider_coordinates(
        PhaseIIIProviderLoginStageRequest(
            discovery_package=discovery.package_directory,
            output_directory=tmp_path / "provider_stage",
            progress=False,
        )
    )
    return discovery, staged


def test_bounded_login_stage_round_trips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery, staged = _stage(tmp_path, monkeypatch)

    observed = validate_phase3_provider_login_stage(staged.preparation_directory)

    assert observed == staged.manifest
    assert observed.maximum_hits_per_sequence_group == 3
    assert observed.maximum_mappings == 25
    assert observed.remote_sequence_submission is False
    assert observed.pdb_coordinate_source_count == 1
    assert observed.afdb_result_count == observed.sequence_group_count
    assert observed.esm_result_count == observed.sequence_group_count
    assert observed.staged_coordinate_object_count == 1
    owned_sources = tuple(
        CoordinateSourceRecord.model_validate_json(line)
        for line in (
            staged.preparation_directory
            / "pdb_coordinate_registration/owned_coordinate_sources.jsonl"
        )
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(owned_sources) == 1
    assert owned_sources[0].coordinate_path.startswith("../coordinate_objects/")
    owned_coordinate = (
        staged.preparation_directory
        / "pdb_coordinate_registration"
        / owned_sources[0].coordinate_path
    ).resolve(strict=True)
    assert owned_coordinate.is_relative_to(
        staged.preparation_directory / "coordinate_objects"
    )
    assert owned_coordinate.is_file()
    assert sha256_file(owned_coordinate, progress=False) == (
        owned_sources[0].coordinate_sha256
    )
    offline = publish_phase3_offline_provider_input(
        discovery_package=discovery.package_directory,
        provider_preparation=staged.preparation_directory,
        execution_identity=(
            discovery.package_directory / "inputs/phase3_execution_identity.json"
        ),
        output_directory=tmp_path / "offline_provider",
    )
    assert offline.manifest.remote_sequence_submission is False
    assert offline.manifest.compute_network_access is False
    workflow = (
        Path(__file__).resolve().parents[2] / "workflows/phase3_application_workflow.nf"
    ).read_text(encoding="utf-8")
    assert "afdb_exact_search/owned_coordinate_sources.jsonl" in workflow
    assert "pdb_coordinate_registration/owned_coordinate_sources.jsonl" in workflow


def test_bounded_login_stage_retains_records_that_share_one_coordinate_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery = build_phase3_provider_discovery_package(_request(tmp_path))
    monkeypatch.setattr(
        stage_module,
        "register_pdb_coordinates",
        _fake_pdb_registration_shared_object,
    )
    monkeypatch.setattr(stage_module, "search_afdb_exact", _fake_afdb_exact)

    staged = stage_phase3_provider_coordinates(
        PhaseIIIProviderLoginStageRequest(
            discovery_package=discovery.package_directory,
            output_directory=tmp_path / "provider_stage",
            progress=False,
        )
    )
    relocated_parent = tmp_path / "relocated"
    relocated_parent.mkdir()
    relocated = relocated_parent / "provider_stage"
    staged.preparation_directory.rename(relocated)
    observed = validate_phase3_provider_login_stage(relocated)
    owned_sources = tuple(
        CoordinateSourceRecord.model_validate_json(line)
        for line in (
            relocated / "pdb_coordinate_registration/owned_coordinate_sources.jsonl"
        )
        .read_text(encoding="utf-8")
        .splitlines()
    )

    assert observed.pdb_coordinate_source_count == 2
    assert observed.staged_coordinate_object_count == 1
    assert len(owned_sources) == 2
    assert len({source.coordinate_id for source in owned_sources}) == 2
    assert len({source.coordinate_path for source in owned_sources}) == 1
    assert not Path(owned_sources[0].coordinate_path).is_absolute()


def test_changed_login_stage_file_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, staged = _stage(tmp_path, monkeypatch)
    manifest = staged.preparation_directory / "afdb_exact_search/search_manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"\n")

    with pytest.raises(PhaseIIIProviderLoginStageError, match="inventory changed"):
        validate_phase3_provider_login_stage(staged.preparation_directory)


def test_cross_owned_login_stage_fails_offline_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_root = tmp_path / "first"
    first_root.mkdir()
    first_request = _request(first_root)
    first = build_phase3_provider_discovery_package(first_request)
    second_root = tmp_path / "second"
    second_root.mkdir()
    second_request = _request(second_root)
    second_request = replace(
        second_request,
        owned_run_id=("gtd-unknown-discovery-20260825T000001Z-cccccccccccc-dddddddd"),
    )
    second = build_phase3_provider_discovery_package(second_request)
    monkeypatch.setattr(
        stage_module,
        "register_pdb_coordinates",
        _fake_pdb_registration,
    )
    monkeypatch.setattr(stage_module, "search_afdb_exact", _fake_afdb_exact)
    staged = stage_phase3_provider_coordinates(
        PhaseIIIProviderLoginStageRequest(
            discovery_package=second.package_directory,
            output_directory=tmp_path / "provider_stage",
            progress=False,
        )
    )

    with pytest.raises(PhaseIIIProviderLoginStageError, match="do not share"):
        publish_phase3_offline_provider_input(
            discovery_package=first.package_directory,
            provider_preparation=staged.preparation_directory,
            execution_identity=(
                first.package_directory / "inputs/phase3_execution_identity.json"
            ),
            output_directory=tmp_path / "offline_provider",
        )


def test_symlinked_discovery_package_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery = build_phase3_provider_discovery_package(_request(tmp_path))
    linked = tmp_path / "linked_discovery"
    linked.symlink_to(discovery.package_directory, target_is_directory=True)
    monkeypatch.setattr(
        stage_module,
        "register_pdb_coordinates",
        _fake_pdb_registration,
    )
    monkeypatch.setattr(stage_module, "search_afdb_exact", _fake_afdb_exact)

    with pytest.raises(PhaseIIIProviderLoginStageError, match="must not be a symlink"):
        stage_phase3_provider_coordinates(
            PhaseIIIProviderLoginStageRequest(
                discovery_package=linked,
                output_directory=tmp_path / "provider_stage",
                progress=False,
            )
        )
