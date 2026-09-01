"""Tests for bounded, inspectable exact and multi-source first-copy funnels."""

import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.model_registry import load_all_eligible_model_registry
from genome_to_diffraction.ranking import (
    DiverseFirstCopyFunnelRequest,
    ExactPredictedFunnelRequest,
    FunnelInputError,
    build_diverse_first_copy_funnel,
    build_exact_predicted_funnel,
)
from genome_to_diffraction.schemas.results import (
    CoordinateHitMappingRecord,
    CoordinateSourceRecord,
    MatthewsHypothesis,
    MrHypothesis,
    MrHypothesisStatus,
    PhysicalStatus,
    ProcessedModelRecord,
)
from tests.support.unknown_pass1_fixture import (
    materialise_neutral_localisation_fixture,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
SEQUENCE_GROUP_ID = (
    "seq_f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e"
)
COORDINATE_ID = "coord_" + "b" * 64


def _coordinate(path: Path) -> None:
    record = CoordinateSourceRecord(
        schema_version="1.0",
        coordinate_id=COORDINATE_ID,
        provider="afdb",
        provider_accession="AF-STUB-F1",
        retrieval_date=datetime(2026, 8, 11, tzinfo=UTC),
        source_release="v6",
        coordinate_path="coordinates/stub.cif",
        coordinate_sha256="b" * 64,
        source_sequence_sha256=SEQUENCE_GROUP_ID.removeprefix("seq_"),
        confidence_summary={"mean_plddt": 93.8},
        license_or_provenance="AlphaFold DB stub provenance",
    )
    path.write_text(f"{canonical_json_text(record)}\n", encoding="utf-8")


def _matthews(
    *,
    copy_count: int,
    rank: int,
    physical_status: PhysicalStatus,
    retained: bool = True,
) -> MatthewsHypothesis:
    return MatthewsHypothesis(
        schema_version="1.0",
        hypothesis_id=f"matthews_{copy_count}",
        crystal_id="test_crystal_01",
        sequence_group_id=SEQUENCE_GROUP_ID,
        copy_count=copy_count,
        sequence_mass_da=436.4375,
        total_mass_da=436.4375 * copy_count,
        v_asu_a3=250_000,
        matthews_coefficient=250_000 / (436.4375 * copy_count),
        solvent_fraction=0.50,
        matthews_prior=1.0 - rank / 10,
        prior_backend="test-prior",
        rank_within_candidate=rank,
        retained=retained,
        physical_status=physical_status,
        sds_page_prior_label="unavailable",
    )


def _request(
    tmp_path: Path, *, first_copy_cap: int = 200
) -> ExactPredictedFunnelRequest:
    model_preparation = tmp_path / "model preparation with spaces"
    shutil.copytree(STUBS / "predicted_model_preparation", model_preparation)
    coordinates = tmp_path / "coordinate sources.jsonl"
    _coordinate(coordinates)
    matthews = tmp_path / "Matthews hypotheses.jsonl"
    rows = (
        _matthews(copy_count=1, rank=1, physical_status=PhysicalStatus.PLAUSIBLE),
        _matthews(copy_count=2, rank=2, physical_status=PhysicalStatus.IMPOSSIBLE),
        _matthews(copy_count=3, rank=3, physical_status=PhysicalStatus.REVIEW),
        _matthews(
            copy_count=4,
            rank=4,
            physical_status=PhysicalStatus.PLAUSIBLE,
            retained=False,
        ),
    )
    matthews.write_text(
        "".join(f"{canonical_json_text(row)}\n" for row in rows),
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    config_text = (REPOSITORY / "examples/config.yaml").read_text(encoding="utf-8")
    config.write_text(
        config_text.replace(
            "max_first_copy_jobs: 200", f"max_first_copy_jobs: {first_copy_cap}"
        ),
        encoding="utf-8",
    )
    return ExactPredictedFunnelRequest(
        coordinate_sources_jsonl=coordinates,
        processed_models_jsonl=model_preparation / "processed_models.jsonl",
        model_preparation_manifest=(
            model_preparation / "model_preparation_manifest.json"
        ),
        sequence_groups_jsonl=STUBS / "sequence_groups.jsonl",
        matthews_hypotheses_jsonl=matthews,
        mtz_preflight_jsonl=STUBS / "mtz_preflight.jsonl",
        pipeline_config=config,
        output_directory=tmp_path / "funnel output",
        crystal_ids=("test_crystal_01",),
        progress=False,
    )


def test_funnel_excludes_impossible_rows_and_preserves_features(tmp_path: Path) -> None:
    result = build_exact_predicted_funnel(_request(tmp_path))

    assert [item.copy_count_expected for item in result.hypotheses] == [1, 3]
    assert all(item.copy_number_to_search == 1 for item in result.hypotheses)
    assert all(item.status == "queued" for item in result.hypotheses)
    first = result.hypotheses[0]
    assert first.priority_features["exact_sequence_mapping"] is True
    assert first.priority_features["coordinate_provider"] == "afdb"
    assert first.priority_features["model_retained_fraction"] == 1.0
    assert first.priority_features["matthews_physical_status"] == "plausible"
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["candidate_count_before_global_cap"] == 2
    assert manifest["selected_hypothesis_count"] == 2
    assert manifest["per_model_copy_cap"] == 3
    assert "matthews_prior" in manifest["ordering_features"]
    assert result.hypotheses_tsv.read_text(encoding="utf-8").count("\n") == 3
    records = sorted((result.manifest_json.parent / "hypotheses").glob("*.jsonl"))
    assert {record.stem for record in records} == {
        item.hypothesis_id for item in result.hypotheses
    }
    assert all(
        record.read_text(encoding="utf-8").count("\n") == 1 for record in records
    )


def test_funnel_applies_global_first_copy_cap_deterministically(tmp_path: Path) -> None:
    result = build_exact_predicted_funnel(_request(tmp_path, first_copy_cap=1))

    assert len(result.hypotheses) == 1
    assert result.hypotheses[0].copy_count_expected == 1
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["global_cap"] == 1
    assert manifest["excluded_by_global_cap_count"] == 1


def test_funnel_fails_before_publication_on_model_checksum_change(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    model = request.model_preparation_manifest.parent / "models/stub.pdb"
    model.write_text("changed\n", encoding="utf-8")

    with pytest.raises(FunnelInputError, match="checksum mismatch"):
        build_exact_predicted_funnel(request)
    assert not request.output_directory.exists()


def test_funnel_rejects_path_traversal_in_preparation_manifest(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    document = json.loads(
        request.model_preparation_manifest.read_text(encoding="utf-8")
    )
    document["entries"][0]["model_path"] = "../escaped.cif"
    request.model_preparation_manifest.write_text(
        json.dumps(document), encoding="utf-8"
    )

    with pytest.raises(FunnelInputError, match="unsafe processed-model path"):
        build_exact_predicted_funnel(request)


def _diverse_request(tmp_path: Path) -> DiverseFirstCopyFunnelRequest:
    base = _request(tmp_path)
    predicted_coordinates = base.coordinate_sources_jsonl
    predicted_preparation = base.model_preparation_manifest.parent
    experimental_preparation = tmp_path / "experimental preparation"
    shutil.copytree(STUBS / "experimental_model_preparation", experimental_preparation)
    experimental_coordinates = tmp_path / "experimental coordinates.jsonl"
    shutil.copyfile(
        STUBS / "pdb_coordinate_registration/coordinate_sources.jsonl",
        experimental_coordinates,
    )
    mappings = tmp_path / "coordinate hit mappings.jsonl"
    shutil.copyfile(
        STUBS / "pdb_coordinate_registration/coordinate_hit_mappings.jsonl",
        mappings,
    )
    return DiverseFirstCopyFunnelRequest(
        coordinate_sources_jsonl=(
            predicted_coordinates,
            experimental_coordinates,
        ),
        processed_models_jsonl=(
            predicted_preparation / "processed_models.jsonl",
            experimental_preparation / "processed_models.jsonl",
        ),
        model_preparation_manifests=(
            predicted_preparation / "model_preparation_manifest.json",
            experimental_preparation / "model_preparation_manifest.json",
        ),
        coordinate_hit_mappings_jsonl=mappings,
        sequence_groups_jsonl=base.sequence_groups_jsonl,
        source_records_jsonl=STUBS / "source_records.jsonl",
        matthews_hypotheses_jsonl=base.matthews_hypotheses_jsonl,
        mtz_preflight_jsonl=base.mtz_preflight_jsonl,
        pipeline_config=base.pipeline_config,
        output_directory=tmp_path / "diverse funnel output",
        crystal_ids=base.crystal_ids,
        progress=False,
    )


def test_diverse_funnel_preserves_predicted_and_experimental_sources(
    tmp_path: Path,
) -> None:
    result = build_diverse_first_copy_funnel(_diverse_request(tmp_path))

    assert len(result.hypotheses) == 4
    source_classes = {
        item.priority_features["structural_source_class"] for item in result.hypotheses
    }
    assert source_classes == {"experimental", "predicted"}
    experimental = next(
        item
        for item in result.hypotheses
        if item.priority_features["structural_source_class"] == "experimental"
    )
    mapping_id = experimental.priority_features["coordinate_mapping_id"]
    assert isinstance(mapping_id, str)
    assert mapping_id.startswith("coordmap_")
    assert experimental.priority_features["pdb_id"] == "1UBQ"
    registry = result.model_registry_directory
    records = registry / "processed_models.jsonl"
    assert records.read_text(encoding="utf-8").count("\n") == 2
    assert len(list((registry / "models").rglob("*.pdb"))) == 2
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["selected_hypothesis_count"] == 4
    assert manifest["per_crystal_selected_counts"] == {"test_crystal_01": 4}
    assert manifest["per_crystal_first_copy_cap"] == 200
    assert manifest["diversity_buckets"] == [
        "sequence_group_id",
        "coordinate_provider",
        "model_variant_type",
    ]


def test_phase3_diverse_funnel_searches_one_copy_and_retains_expectations(
    tmp_path: Path,
) -> None:
    request = _diverse_request(tmp_path)
    rows = tuple(
        _matthews(
            copy_count=copy_count,
            rank=rank,
            physical_status=PhysicalStatus.PLAUSIBLE,
        )
        for rank, copy_count in enumerate((5, 1, 2, 3, 4), start=1)
    )
    request.matthews_hypotheses_jsonl.write_text(
        "".join(f"{canonical_json_text(row)}\n" for row in rows),
        encoding="utf-8",
    )
    localisation = _phase3_localisation_bundle(
        tmp_path,
        sequence_groups_jsonl=request.sequence_groups_jsonl,
        source_records_jsonl=STUBS / "source_records.jsonl",
    )

    result = build_diverse_first_copy_funnel(
        replace(
            request,
            require_localisation_policy=True,
            localisation_bundle=localisation,
        )
    )

    assert len(result.hypotheses) == 6
    assert {
        (item.copy_count_expected, item.copy_number_to_search)
        for item in result.hypotheses
    } == {(1, 1), (2, 1), (5, 1)}
    assert all(
        item.priority_features["copy_search_mode"]
        == "single_copy_then_sequential_completion"
        for item in result.hypotheses
    )
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["adapter_version"] == (
        "multi-source-first-copy-funnel-v6-single-copy"
    )
    assert result.resource_plans_jsonl is not None
    resource_rows = tuple(
        json.loads(line)
        for line in result.resource_plans_jsonl.read_text(encoding="utf-8").splitlines()
    )
    assert {row["resource_plan"]["base_cpus"] for row in resource_rows} <= {4, 6, 8}
    assert {row["resource_plan"]["searched_copy_count"] for row in resource_rows} == {1}
    assert {row["resource_plan"]["owner_id"] for row in resource_rows} == {
        item.hypothesis_id for item in result.hypotheses
    } | {
        json.loads(line)["hypothesis_id"]
        for path in (
            result.deferred_cap_hypotheses_jsonl,
            result.deferred_localisation_hypotheses_jsonl,
        )
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    }
    assert all(
        "resource_plan" not in item.model_dump(mode="json")
        for item in result.hypotheses
    )
    assert manifest["copy_search_mode"] == ("single_copy_then_sequential_completion")
    assert manifest["initial_searched_copy_count"] == 1
    assert manifest["expected_copy_count_minimum"] == 1
    assert manifest["expected_copy_count_maximum"] == 16
    assert "maximum_joint_copy_count" not in manifest
    assert manifest["per_model_copy_cap"] == 3
    assert manifest["per_crystal_first_copy_cap"] == 25


def _phase3_localisation_bundle(
    tmp_path: Path,
    *,
    sequence_groups_jsonl: Path,
    source_records_jsonl: Path,
    psortb_label: str = "Cytoplasmic",
    deeptmhmm_type: str = "GLOB",
    deeptmhmm_topology_label: str = "O",
) -> Path:
    evidence_root = tmp_path / "phase3 localisation evidence"
    evidence_root.mkdir(parents=True)
    gel = evidence_root / "gel-evidence.json"
    gel.write_text(
        '{"schema_version":"2.0","observations":[]}\n',
        encoding="ascii",
    )
    return materialise_neutral_localisation_fixture(
        evidence_root,
        gel_evidence=gel,
        sequence_groups_jsonl=sequence_groups_jsonl,
        source_records_jsonl=source_records_jsonl,
        psortb_label=psortb_label,
        deeptmhmm_type=deeptmhmm_type,
        deeptmhmm_topology_label=deeptmhmm_topology_label,
    )


def test_phase3_diverse_funnel_requires_complete_localisation_authority(
    tmp_path: Path,
) -> None:
    request = replace(
        _diverse_request(tmp_path),
        require_localisation_policy=True,
    )

    with pytest.raises(FunnelInputError, match="requires its localisation/gel"):
        build_diverse_first_copy_funnel(request)
    assert not request.output_directory.exists()


def test_phase3_diverse_funnel_binds_active_localisation_evidence(
    tmp_path: Path,
) -> None:
    request = _diverse_request(tmp_path)
    bundle = _phase3_localisation_bundle(
        tmp_path,
        sequence_groups_jsonl=request.sequence_groups_jsonl,
        source_records_jsonl=STUBS / "source_records.jsonl",
    )

    result = build_diverse_first_copy_funnel(
        replace(
            request,
            require_localisation_policy=True,
            localisation_bundle=bundle,
        )
    )

    assert len(result.hypotheses) == 4
    assert all(
        item.priority_features["localisation_wave_disposition"] == "active"
        for item in result.hypotheses
    )
    assert all(
        isinstance(item.priority_features["localisation_evidence_id"], str)
        for item in result.hypotheses
    )
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["localisation_required"] is True
    assert manifest["localisation_excluded_sequence_group_count"] == 0
    assert manifest["gel_observation_count"] == 0
    assert manifest["localisation_policy_id"].startswith("batchlocalpolicy_")


def test_phase3_diverse_funnel_requires_bound_source_records(tmp_path: Path) -> None:
    request = _diverse_request(tmp_path)
    bundle = _phase3_localisation_bundle(
        tmp_path,
        sequence_groups_jsonl=request.sequence_groups_jsonl,
        source_records_jsonl=STUBS / "source_records.jsonl",
    )

    with pytest.raises(FunnelInputError, match="requires its exact source records"):
        build_diverse_first_copy_funnel(
            replace(
                request,
                require_localisation_policy=True,
                localisation_bundle=bundle,
                source_records_jsonl=None,
            )
        )


def test_phase3_diverse_funnel_retains_but_skips_first_wave_exclusions(
    tmp_path: Path,
) -> None:
    request = _diverse_request(tmp_path)
    bundle = _phase3_localisation_bundle(
        tmp_path,
        sequence_groups_jsonl=request.sequence_groups_jsonl,
        source_records_jsonl=STUBS / "source_records.jsonl",
        psortb_label="CytoplasmicMembrane",
        deeptmhmm_type="TM",
        deeptmhmm_topology_label="M",
    )

    result = build_diverse_first_copy_funnel(
        replace(
            request,
            require_localisation_policy=True,
            localisation_bundle=bundle,
        )
    )

    assert result.hypotheses == ()
    deferred = tuple(
        MrHypothesis.model_validate_json(line)
        for line in result.deferred_localisation_hypotheses_jsonl.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    )
    assert len(deferred) == 4
    assert all(item.status is MrHypothesisStatus.SKIPPED for item in deferred)
    assert all(
        item.priority_features["localisation_first_wave_reason"]
        == "retained_excluded_reopen_only_after_complete_zero_pack"
        for item in deferred
    )
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["localisation_excluded_sequence_group_count"] == 1
    assert manifest["retained_excluded_hypothesis_count"] == 4
    assert manifest["selected_hypothesis_count"] == 0


@pytest.mark.parametrize("all_providers_empty", (False, True))
def test_diverse_funnel_preserves_documented_empty_model_batches(
    tmp_path: Path, *, all_providers_empty: bool
) -> None:
    request = _diverse_request(tmp_path)
    empty_indexes = (0, 1) if all_providers_empty else (0,)
    for index in empty_indexes:
        request.coordinate_sources_jsonl[index].write_text("", encoding="utf-8")
        request.processed_models_jsonl[index].write_text("", encoding="utf-8")
        manifest_path = request.model_preparation_manifests[index]
        preparation = json.loads(manifest_path.read_text(encoding="utf-8"))
        preparation["processed_model_count"] = 0
        preparation["entries"] = []
        manifest_path.write_text(json.dumps(preparation), encoding="utf-8")
    if all_providers_empty:
        assert request.coordinate_hit_mappings_jsonl is not None
        request.coordinate_hit_mappings_jsonl.write_text("", encoding="utf-8")

    output = build_diverse_first_copy_funnel(request)
    registry = load_all_eligible_model_registry(
        output.model_registry_directory / "all_model_registry.json"
    )

    if all_providers_empty:
        assert output.hypotheses == ()
        assert output.hypotheses_jsonl.read_bytes() == b""
        assert registry.manifest.model_count == 0
        assert registry.manifest.unavailable_sequence_group_count == 1
        assert registry.manifest.sequence_groups[0].unavailable_reason is not None
    else:
        assert len(output.hypotheses) == 2
        assert all(
            item.priority_features["structural_source_class"] == "experimental"
            for item in output.hypotheses
        )
        assert registry.manifest.model_count == 1


def test_diverse_funnel_reserves_exact_mapping_before_homologue(
    tmp_path: Path,
) -> None:
    request = _diverse_request(tmp_path)
    pdb_sources = request.coordinate_sources_jsonl[1]
    pdb_source = CoordinateSourceRecord.model_validate_json(
        pdb_sources.read_text(encoding="utf-8")
    ).model_copy(update={"source_sequence_sha256": "1" * 64})
    pdb_sources.write_text(f"{canonical_json_text(pdb_source)}\n", encoding="utf-8")
    mappings_path = request.coordinate_hit_mappings_jsonl
    assert mappings_path is not None
    mapping = CoordinateHitMappingRecord.model_validate_json(
        mappings_path.read_text(encoding="utf-8")
    ).model_copy(
        update={
            "source_sequence_sha256": "1" * 64,
            "sequence_identity": 0.625,
            "exact_sequence_match": False,
        }
    )
    mappings_path.write_text(f"{canonical_json_text(mapping)}\n", encoding="utf-8")
    experimental_models = request.processed_models_jsonl[1]
    model = ProcessedModelRecord.model_validate_json(
        experimental_models.read_text(encoding="utf-8")
    )
    parameters = dict(model.processing_parameters)
    parameters.update({"source_sequence_sha256": "1" * 64, "sequence_identity": 0.625})
    homologue_model = model.model_copy(update={"processing_parameters": parameters})
    experimental_models.write_text(
        f"{canonical_json_text(homologue_model)}\n",
        encoding="utf-8",
    )
    request.pipeline_config.write_text(
        request.pipeline_config.read_text(encoding="utf-8").replace(
            "max_first_copy_jobs: 200", "max_first_copy_jobs: 1"
        ),
        encoding="utf-8",
    )

    result = build_diverse_first_copy_funnel(request)

    assert len(result.hypotheses) == 1
    assert result.hypotheses[0].priority_features["exact_sequence_mapping"] is True
    assert result.hypotheses[0].priority_features["structural_source_class"] == (
        "predicted"
    )


def test_diverse_smoke_funnel_enforces_twenty_five_jobs_per_crystal(
    tmp_path: Path,
) -> None:
    base = _request(tmp_path)
    preparation = base.model_preparation_manifest.parent
    original = ProcessedModelRecord.model_validate_json(
        (preparation / "processed_models.jsonl").read_text(encoding="utf-8")
    )
    models = tuple(
        original.model_copy(update={"model_id": f"model_{index:064x}"})
        for index in range(1, 31)
    )
    (preparation / "processed_models.jsonl").write_text(
        "".join(f"{canonical_json_text(item)}\n" for item in models),
        encoding="utf-8",
    )
    manifest = json.loads(
        (preparation / "model_preparation_manifest.json").read_text(encoding="utf-8")
    )
    template = manifest["entries"][0]
    manifest["entries"] = [{**template, "model_id": model.model_id} for model in models]
    manifest["processed_model_count"] = len(models)
    (preparation / "model_preparation_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    smoke_config = tmp_path / "smoke config.yaml"
    smoke_config.write_text(
        base.pipeline_config.read_text(encoding="utf-8").replace(
            "profile: pilot", "profile: smoke"
        ),
        encoding="utf-8",
    )
    request = DiverseFirstCopyFunnelRequest(
        coordinate_sources_jsonl=(base.coordinate_sources_jsonl,),
        processed_models_jsonl=(preparation / "processed_models.jsonl",),
        model_preparation_manifests=(preparation / "model_preparation_manifest.json",),
        sequence_groups_jsonl=base.sequence_groups_jsonl,
        matthews_hypotheses_jsonl=base.matthews_hypotheses_jsonl,
        mtz_preflight_jsonl=base.mtz_preflight_jsonl,
        pipeline_config=smoke_config,
        output_directory=tmp_path / "hard capped smoke funnel",
        crystal_ids=base.crystal_ids,
        progress=False,
    )

    result = build_diverse_first_copy_funnel(request)

    assert len(result.hypotheses) == 25
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["candidate_count_before_caps"] == 30
    assert manifest["per_crystal_first_copy_cap"] == 25
    assert manifest["per_crystal_selected_counts"] == {"test_crystal_01": 25}
    assert manifest["excluded_by_caps_count"] == 5
    registry = load_all_eligible_model_registry(
        result.model_registry_directory / "all_model_registry.json"
    )
    assert registry.manifest.model_count == 30


def test_diverse_funnel_applies_stricter_execution_cap(tmp_path: Path) -> None:
    request = replace(_diverse_request(tmp_path), maximum_first_copy_jobs=1)

    result = build_diverse_first_copy_funnel(request)

    assert len(result.hypotheses) == 1
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["per_crystal_first_copy_cap"] == 1
    assert manifest["requested_execution_cap"] == 1
    deferred = tuple(
        MrHypothesis.model_validate_json(line)
        for line in result.deferred_cap_hypotheses_jsonl.read_text().splitlines()
        if line
    )
    assert len(deferred) == manifest["candidate_count_before_caps"] - 1
    assert all(
        item.status is MrHypothesisStatus.SKIPPED
        and item.priority_features["first_copy_execution_disposition"]
        == "deferred_initial_25_cap_reopen_only_after_complete_zero_pack"
        for item in deferred
    )


def test_diverse_a_cap_does_not_change_all_model_registry_identity(
    tmp_path: Path,
) -> None:
    cap_one_request = replace(
        _diverse_request(tmp_path / "cap one"), maximum_first_copy_jobs=1
    )
    cap_two_request = replace(
        _diverse_request(tmp_path / "cap two"), maximum_first_copy_jobs=2
    )

    cap_one = build_diverse_first_copy_funnel(cap_one_request)
    cap_two = build_diverse_first_copy_funnel(cap_two_request)
    registry_one = load_all_eligible_model_registry(
        cap_one.model_registry_directory / "all_model_registry.json"
    )
    registry_two = load_all_eligible_model_registry(
        cap_two.model_registry_directory / "all_model_registry.json"
    )

    assert len(cap_one.hypotheses) == 1
    assert len(cap_two.hypotheses) == 2
    assert registry_one.manifest.registry_id == registry_two.manifest.registry_id
    assert (
        cap_one.model_registry_directory / "all_model_registry.json"
    ).read_bytes() == (
        cap_two.model_registry_directory / "all_model_registry.json"
    ).read_bytes()
