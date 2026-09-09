"""Synthetic coordinate-to-production-funnel parity, without native MR claims."""

import gzip
import json
from dataclasses import replace
from itertools import product
from pathlib import Path

import gemmi
import pytest
import yaml

from genome_to_diffraction.benchmarks.m6_nextflow import (
    M6BundleManifest,
    M6CaseTask,
    M6CatalogueTask,
    M6HypothesisGroupTask,
    _write_eligible_inputs,
    run_m6_coordinate_stage_task,
    run_m6_prepare_case_task,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.catalogue.mass import assess_mass
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.databases.network import DownloadMetadata
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.model_registry import load_all_eligible_model_registry
from genome_to_diffraction.ranking import (
    DiverseFirstCopyFunnelRequest,
    build_diverse_first_copy_funnel,
)
from genome_to_diffraction.schemas.results import MrHypothesis, SequenceGroupRecord
from genome_to_diffraction.structure_search import pdb_coordinates
from tests.unit.test_experimental_model_preparation import _source_pdb
from tests.unit.test_pdb_coordinates import _group, _hit, _inputs, _request
from tests.unit.test_ranking_funnel import _request as _funnel_inputs


def _jsonl(path: Path, rows: tuple[object, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{canonical_json_text(row)}\n" for row in rows), encoding="ascii"
    )


def _bind_policy(policy: Path) -> None:
    atomic_write_json(
        policy / "bundle_manifest.json",
        M6BundleManifest(
            schema_version="1.0",
            adapter_version="m6-nextflow-model-policy-v2",
            task_kind="trusted_model_policy",
            task_id="test_crystal_01",
            input_sha256={},
            output_sha256={
                "accepted_hits": sha256_file(
                    policy / "policy/accepted_structural_hits.jsonl"
                )
            },
        ).model_dump(mode="json"),
    )


def _catalogue(tmp_path: Path) -> tuple[Path, Path, tuple[SequenceGroupRecord, ...]]:
    decoys = tuple(
        f"AC{a}{b}" for a, b in product("ACDEFG", repeat=2) if f"AC{a}{b}" != "ACDE"
    )[:30]
    sequences = (*decoys, "ACDE", "YYYY")
    groups = tuple(
        _group(sequence).model_copy(
            update={"molecular_mass_da": assess_mass(sequence).exact_da}
        )
        for sequence in sequences
    )
    catalogue, policy = tmp_path / "catalogue", tmp_path / "policy"
    _jsonl(catalogue / "catalogue/sequence_groups.jsonl", groups)
    _jsonl(
        catalogue / "catalogue/source_records.jsonl",
        tuple(
            {
                "schema_version": "1.0",
                "source_record_id": f"record_{index}",
                "catalogue_id": "synthetic_catalogue",
                "original_protein_id": f"protein_{index}",
                "original_header": f"protein_{index}",
                "sequence_group_id": group.sequence_group_id,
                "source_annotation_provider": "synthetic_fixture",
            }
            for index, group in enumerate(groups)
        ),
    )
    _jsonl(
        policy / "policy/accepted_structural_hits.jsonl",
        tuple(
            _hit(
                group,
                hit_id=f"hit_{index}_{rank}",
                rank=rank,
                pdb_id="1ABC",
                source_sequence="ACDE",
                identity=sum(
                    a == b for a, b in zip(group.sequence, "ACDE", strict=True)
                )
                / 4,
            )
            for index, group in enumerate(groups[:-1])
            for rank in (1, 2, 3)
        ),
    )
    _jsonl(
        policy / "policy/candidate_ranking.jsonl",
        tuple(
            {"sequence_group_id": group.sequence_group_id, "rank": rank}
            for rank, group in enumerate(groups, start=1)
        ),
    )
    _bind_policy(policy)
    return catalogue, policy, groups


def test_eligible_inputs_ignore_provider_order_and_retain_late_candidates(
    tmp_path: Path,
) -> None:
    catalogue, policy, groups = _catalogue(tmp_path)
    first = tmp_path / "first"
    first.mkdir()
    outputs = _write_eligible_inputs(catalogue, policy, first)
    assert len(outputs[0].read_text().splitlines()) == 31
    assert len(outputs[1].read_text().splitlines()) == 31
    assert len(outputs[2].read_text().splitlines()) == 93
    assert groups[30].sequence_group_id in outputs[0].read_text()
    assert groups[31].sequence_group_id not in outputs[0].read_text()
    for path in (
        catalogue / "catalogue/sequence_groups.jsonl",
        catalogue / "catalogue/source_records.jsonl",
        policy / "policy/accepted_structural_hits.jsonl",
        policy / "policy/candidate_ranking.jsonl",
    ):
        path.write_text("\n".join(reversed(path.read_text().splitlines())) + "\n")
    _bind_policy(policy)
    second = tmp_path / "second"
    second.mkdir()
    permuted = _write_eligible_inputs(catalogue, policy, second)
    assert [p.read_bytes() for p in permuted] == [p.read_bytes() for p in outputs]


@pytest.mark.parametrize("corruption", ["foreign_hit", "duplicate_hit", "lost_source"])
def test_eligible_inputs_fail_closed_on_broken_joins(
    tmp_path: Path, corruption: str
) -> None:
    catalogue, policy, _ = _catalogue(tmp_path)
    path = policy / "policy/accepted_structural_hits.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if corruption == "foreign_hit":
        rows[0]["sequence_group_id"] = "seq_foreign"
    elif corruption == "duplicate_hit":
        rows.append(rows[0])
    else:
        path = catalogue / "catalogue/source_records.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()][1:]
    _jsonl(path, tuple(rows))
    _bind_policy(policy)
    with pytest.raises(PublicControlError):
        _write_eligible_inputs(catalogue, policy, tmp_path)
    assert not (tmp_path / "eligible-candidates").exists()


def test_eligible_inputs_reject_changed_policy_hits(tmp_path: Path) -> None:
    catalogue, policy, _ = _catalogue(tmp_path)
    path = policy / "policy/accepted_structural_hits.jsonl"
    path.write_text(path.read_text().splitlines()[0] + "\n")
    with pytest.raises(PublicControlError, match="bound to the trusted policy"):
        _write_eligible_inputs(catalogue, policy, tmp_path)


def test_m6_uses_complete_coordinate_inventory_and_production_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The sole simulated external response is a tiny, explicit coordinate file.
    # Registration, model preparation, Matthews enumeration and both funnels run.
    structure = gemmi.read_pdb_string(_source_pdb())
    structure.name = "1ABC"
    structure[0][0].name = "A"
    structure.setup_entities()
    structure.entities[0].full_sequence = ["ALA", "CYS", "ASP", "GLU"]
    structure.assign_label_seq_id()
    block = structure.make_mmcif_document().sole_block()
    loop = block.find_loop("_entity_poly.entity_id").get_loop()
    assert loop is not None
    loop.add_columns(["_entity_poly.pdbx_seq_one_letter_code_can"], "ACDE")
    payload = gzip.compress(block.as_string().encode("ascii"), mtime=0)
    downloads: list[str] = []

    def download(url: str, destination: Path, **_kwargs: object) -> DownloadMetadata:
        assert url.endswith("/1abc.cif.gz")
        downloads.append(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return DownloadMetadata(
            requested_url=url,
            url=url,
            etag=None,
            last_modified=None,
            content_type="application/gzip",
            size_bytes=len(payload),
            sha256=sha256_file(destination),
        )

    monkeypatch.setattr(pdb_coordinates, "download_public_resource", download)
    hit_path, group_path, database, _ = _inputs(tmp_path)
    pdb_coordinates.register_pdb_coordinates(
        replace(_request(tmp_path, hit_path, group_path, database), maximum_mappings=1)
    )
    assert len(downloads) == 1
    catalogue, policy, groups = _catalogue(tmp_path)
    base = _funnel_inputs(tmp_path)
    case_task = tmp_path / "case_task"
    case_task.mkdir()
    (case_task / "reflections.mtz").write_bytes(b"synthetic preflight-only fixture")
    atomic_write_json(
        case_task / "analysis_config.json",
        yaml.safe_load(base.pipeline_config.read_text()),
    )
    base = replace(base, pipeline_config=case_task / "analysis_config.json")
    atomic_write_json(case_task / "model_policy.json", {})
    atomic_write_json(
        case_task / "task.json",
        M6CaseTask(
            schema_version="1.0",
            case_id="test_crystal_01",
            track="operational",
            catalogue_key="a" * 64,
            reflections_sha256=sha256_file(case_task / "reflections.mtz"),
            analysis_config_sha256=sha256_file(case_task / "analysis_config.json"),
            model_policy_sha256=sha256_file(case_task / "model_policy.json"),
        ).model_dump(mode="json"),
    )
    atomic_write_json(
        catalogue / "catalogue_task.json",
        M6CatalogueTask(
            schema_version="1.0",
            catalogue_key="a" * 64,
            catalogue_sha256="b" * 64,
            analysis_config_sha256=sha256_file(case_task / "analysis_config.json"),
            software_lock_sha256="c" * 64,
            import_cache_key="d" * 64,
        ).model_dump(mode="json"),
    )
    atomic_write_json(catalogue / "catalogue/catalogue_import_manifest.json", {})
    for root, task_id, outputs in (
        (
            catalogue,
            "a" * 64,
            {
                "sequence_groups": "catalogue/sequence_groups.jsonl",
                "source_records": "catalogue/source_records.jsonl",
                "import_manifest": "catalogue/catalogue_import_manifest.json",
            },
        ),
    ):
        atomic_write_json(
            root / "bundle_manifest.json",
            M6BundleManifest(
                schema_version="1.0",
                adapter_version="synthetic-fixture",
                task_kind="synthetic-fixture",
                task_id=task_id,
                input_sha256={},
                output_sha256={
                    name: sha256_file(root / p) for name, p in outputs.items()
                },
            ).model_dump(mode="json"),
        )
    stage = run_m6_coordinate_stage_task(
        case_task, catalogue, policy, database, tmp_path / "coordinate_stage"
    )
    registration = json.loads(
        (stage / "registration/registration_manifest.json").read_text()
    )
    assert registration["selected_mapping_count"] == 93
    assert registration["parameters"]["maximum_mappings"] == 93
    assert registration["downloaded_entry_count"] == 0
    assert len(downloads) == 1
    preflight = tmp_path / "preflight"
    (preflight / "preflight").mkdir(parents=True)
    (preflight / "preflight/mtz_preflight.jsonl").write_bytes(
        base.mtz_preflight_jsonl.read_bytes()
    )
    atomic_write_json(
        preflight / "crystal_manifest.json",
        {
            "schema_version": "1.0",
            "crystals": [
                {
                    "crystal_id": "test_crystal_01",
                    "mtz": "fixture.mtz",
                    "catalogue_id": "synthetic_catalogue",
                    "allow_remote_sequence_submission": False,
                }
            ],
        },
    )
    atomic_write_json(
        preflight / "bundle_manifest.json",
        M6BundleManifest(
            schema_version="1.0",
            adapter_version="synthetic-fixture",
            task_kind="preflight",
            task_id="test_crystal_01",
            input_sha256={},
            output_sha256={},
        ).model_dump(mode="json"),
    )
    case = run_m6_prepare_case_task(
        case_task, preflight, catalogue, policy, stage, tmp_path / "prepared_case"
    )
    plan = M6HypothesisGroupTask.model_validate_json(
        (case / "case_plan.json").read_bytes()
    )
    assert plan.hypothesis_count == 25
    registry = load_all_eligible_model_registry(
        case / "first-copy-funnel/model_registry/all_model_registry.json"
    )
    assert registry.manifest.model_count == 93
    scheduled = tuple(
        MrHypothesis.model_validate_json(path.read_bytes())
        for path in sorted((case / "first-copy-funnel/hypotheses").glob("*.jsonl"))
    )
    assert groups[30].sequence_group_id in {h.sequence_group_id for h in scheduled}
    assert all(h.copy_number_to_search == 1 for h in scheduled)
    matthews = next((case / "matthews").glob("*.jsonl"))
    production = build_diverse_first_copy_funnel(
        DiverseFirstCopyFunnelRequest(
            coordinate_sources_jsonl=(stage / "registration/coordinate_sources.jsonl",),
            processed_models_jsonl=(case / "model-preparation/processed_models.jsonl",),
            model_preparation_manifests=(
                case / "model-preparation/model_preparation_manifest.json",
            ),
            coordinate_hit_mappings_jsonl=stage
            / "registration/coordinate_hit_mappings.jsonl",
            sequence_groups_jsonl=case / "eligible-candidates/sequence_groups.jsonl",
            matthews_hypotheses_jsonl=matthews,
            mtz_preflight_jsonl=base.mtz_preflight_jsonl,
            pipeline_config=base.pipeline_config,
            output_directory=tmp_path / "independent_production_funnel",
            crystal_ids=("test_crystal_01",),
            maximum_first_copy_jobs=25,
            progress=False,
        )
    )
    assert {h.hypothesis_id for h in production.hypotheses} == set(plan.hypothesis_ids)
