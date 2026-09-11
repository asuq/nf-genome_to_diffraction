"""Original runner-to-preparation RF binding with synthetic external responses."""

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import gemmi
import pytest

from genome_to_diffraction.benchmarks import m6_model_policy
from genome_to_diffraction.benchmarks.m6_nextflow import (
    run_m6_catalogue_task,
    run_m6_coordinate_stage_task,
    run_m6_model_policy_task,
    run_m6_preflight_task,
    run_m6_prepare_case_task,
)
from genome_to_diffraction.benchmarks.m6_prepare import write_m6_mtz_variant
from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
from genome_to_diffraction.benchmarks.m6_runner import (
    M6RunnerBundleRequest,
    build_m6_runner_bundle,
)
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.results import SequenceGroupRecord
from tests.fixtures.ranking_four_arm_plan import (
    ReferencePlanInputs,
    plan_reference_nextflow,
    validate_reference_plan,
)
from tests.fixtures.ranking_four_arm_prepared import (
    ReferencePreparedInputs,
    bind_reference_prepared_case,
    validate_reference_prepared_case,
)
from tests.unit.test_m6_admission import _prepared_case
from tests.unit.test_m6_benchmark import (
    PROTOCOL,
    ROOT,
    _m6_source_mtz,
    _prepared_manifest,
)
from tests.unit.test_pdb_coordinates import _hit


def _inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    no_hits: bool = False,
    small: bool = False,
) -> ReferencePreparedInputs:
    seed_root = tmp_path / "synthetic-coordinate-seed"
    seed_root.mkdir()
    seed_case = _prepared_case(seed_root, monkeypatch)
    # Reuse only the explicit synthetic coordinate-cache response. The runner,
    # catalogue import, preflight, model policy and preparation below are fresh.
    original = tmp_path / "original-inputs"
    original.mkdir()
    protocol = load_m6_protocol(PROTOCOL)
    prepared = _prepared_manifest(original, protocol)
    groups = tuple(
        SequenceGroupRecord.model_validate_json(line)
        for line in (seed_case / "all_sequence_groups.jsonl").read_text().splitlines()
    )
    if small:
        groups = tuple(group for group in groups if group.sequence in {"ACDE", "YYYY"})
    (original / "catalogue.fa").write_text(
        "".join(
            f">loc_{sha256(group.sequence.encode('ascii')).hexdigest()}\n{group.sequence}\n"
            for group in groups
        )
    )
    config = json.loads((original / "config.json").read_text())
    config["catalogue"]["min_length_aa"] = 1
    atomic_write_json(original / "config.json", config)
    policy_document = json.loads((original / "policy.json").read_text())
    policy_document.update(
        schema_version="1.0",
        exact_deposition_removed_by_trusted_transition=True,
        applies_to_all_model_routes=True,
        retain_rejected_model_annotations=True,
    )
    atomic_write_json(original / "policy.json", policy_document)
    mtz = _m6_source_mtz()
    mtz.set_cell_for_all(gemmi.UnitCell(20, 20, 20, 90, 90, 90))
    sanitisation = write_m6_mtz_variant(
        mtz, original / "reflections.mtz", opaque_id="M6C001", variation="ordinary"
    )
    assert sanitisation is not None
    preparation = json.loads(prepared.read_text())
    for case in preparation["cases"]:
        case["reflection_sanitisation"] = sanitisation.model_dump(mode="json")
        for item in case["objects"]:
            item["sha256"] = sha256_file(Path(item["path"]))
            item["size_bytes"] = Path(item["path"]).stat().st_size
    atomic_write_json(prepared, preparation)
    runner = build_m6_runner_bundle(
        M6RunnerBundleRequest(
            protocol=PROTOCOL,
            preparation_manifest=prepared,
            output_directory=tmp_path / "runner",
            archive=tmp_path / "runner.tar",
        )
    )
    plan_inputs = ReferencePlanInputs(
        runner_root=runner.runner_manifest.parent,
        database_manifest=seed_root / "database manifest.json",
        software_lock=ROOT / "pixi.lock",
    )
    path = plan_reference_nextflow(plan_inputs, tmp_path / "plan")
    plan = validate_reference_plan(path, plan_inputs)
    row = plan.cases[0]
    case_task = path.parent / row.task_directory
    catalogue_task = path.parent / plan.catalogues[0].task_directory
    catalogue = run_m6_catalogue_task(
        catalogue_task, plan_inputs.software_lock, tmp_path / "original-catalogue"
    )
    phenix = ROOT / "tests/fixtures/stubs/phenix_install_manifest.json"
    preflight = run_m6_preflight_task(
        case_task, phenix, tmp_path / "original-preflight"
    )
    imported = tuple(
        SequenceGroupRecord.model_validate_json(line)
        for line in (catalogue / "catalogue/sequence_groups.jsonl")
        .read_text()
        .splitlines()
    )
    hits = tuple(
        _hit(
            group,
            hit_id=f"hit_{index}_{rank}",
            rank=rank,
            pdb_id="1ABC",
            source_sequence="ACDE",
            identity=sum(a == b for a, b in zip(group.sequence, "ACDE", strict=True))
            / 4,
        )
        for index, group in enumerate(imported)
        if group.sequence != "YYYY"
        for rank in ((1,) if small else (1, 2, 3))
    )
    pdb, foldseek = (
        tmp_path / "synthetic-pdb-search",
        tmp_path / "synthetic-foldseek-search",
    )
    for root in (pdb, foldseek):
        (root / "search").mkdir(parents=True)
        atomic_write_json(
            root / "bundle_manifest.json", {"synthetic_external_response": True}
        )
        (root / "search/structural_hits.jsonl").write_text(
            "".join(f"{canonical_json_text(hit)}\n" for hit in hits)
            if root == pdb and not no_hits
            else ""
        )
    monkeypatch.setattr(
        m6_model_policy,
        "_mmseqs_version",
        lambda _path: ("synthetic-test", "db_test_pdb_sequences"),
    )
    policy = run_m6_model_policy_task(
        case_task,
        catalogue,
        pdb,
        foldseek,
        PROTOCOL,
        plan_inputs.database_manifest,
        tmp_path / "original-policy",
    )
    stage = run_m6_coordinate_stage_task(
        case_task,
        catalogue,
        policy,
        plan_inputs.database_manifest,
        tmp_path / "original-coordinate-stage",
    )
    case = run_m6_prepare_case_task(
        case_task,
        preflight,
        catalogue,
        policy,
        stage,
        tmp_path / "original-prepared-case",
    )
    return ReferencePreparedInputs(
        plan_path=path,
        plan_inputs=plan_inputs,
        case_id=row.task.case_id,
        catalogue_bundle=catalogue,
        prepared_case=case,
        coordinate_stage=stage,
        phenix_manifest=phenix,
    )


def test_reference_binds_genuine_production_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path, monkeypatch)
    path = bind_reference_prepared_case(inputs, tmp_path / "reference")
    manifest, admission = validate_reference_prepared_case(path, inputs)
    assert manifest.status == "materialised"
    assert manifest.task.case_id == "M6C001"
    assert manifest.task.track == "operational"
    assert not manifest.mr_executed and not manifest.human_approval_granted
    assert admission is not None
    assert inputs.coordinate_stage is not None
    assert admission.pipeline_config == inputs.prepared_case / "analysis_config.json"
    assert admission.coordinate_sources_jsonl == (
        inputs.coordinate_stage / "registration/coordinate_sources.jsonl",
    )
    assert (
        len(
            (inputs.prepared_case / "all_sequence_groups.jsonl")
            .read_text()
            .splitlines()
        )
        == 32
    )
    cohorts = json.loads((path.parent / "cohorts/reference_cohorts.json").read_text())
    assert 25 <= len(cohorts["tasks"]) <= 50
    assert all(len(cohort["hypotheses"]) == 25 for cohort in cohorts["cohorts"])
    assert not tuple(path.parent.rglob("benchmark_advancement.json"))
    assert not tuple(path.parent.rglob("normalised_mr_result.json"))


def test_reference_preserves_genuine_empty_coordinate_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path, monkeypatch, no_hits=True)
    path = bind_reference_prepared_case(inputs, tmp_path / "reference")
    manifest, admission = validate_reference_prepared_case(path, inputs)
    assert manifest.status == manifest.production_early_outcome == "completed_no_model"
    assert admission is None
    assert manifest.materialisation_path is None
    assert manifest.output_sha256 == {}
    assert not (path.parent / "cohorts").exists()


@pytest.mark.parametrize(
    "corruption",
    ("original_mtz", "full_catalogue", "coordinate_stage", "reference_output"),
)
def test_reference_prepared_rejects_post_binding_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    inputs = _inputs(tmp_path, monkeypatch)
    path = bind_reference_prepared_case(inputs, tmp_path / "reference")
    assert inputs.coordinate_stage is not None
    target = {
        "original_mtz": inputs.prepared_case / "reflections.mtz",
        "full_catalogue": inputs.prepared_case / "all_sequence_groups.jsonl",
        "coordinate_stage": inputs.coordinate_stage
        / "registration/coordinate_sources.jsonl",
        "reference_output": path.parent / "cohorts/reference_first_copy_tasks.tsv",
    }[corruption]
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(
        ValueError, match="identity, original inputs or outputs changed"
    ):
        validate_reference_prepared_case(path, inputs)


@pytest.mark.parametrize(
    "corruption", ("missing_stage", "foreign_case", "changed_catalogue", "changed_mtz")
)
def test_reference_prepared_rejects_incorrect_original_join_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    inputs = _inputs(tmp_path, monkeypatch)
    if corruption == "missing_stage":
        inputs = replace(inputs, coordinate_stage=None)
    elif corruption == "foreign_case":
        inputs = replace(inputs, case_id="M6C002")
    elif corruption == "changed_catalogue":
        target = inputs.prepared_case / "all_sequence_groups.jsonl"
        target.write_text(target.read_text().splitlines()[0] + "\n")
    else:
        (inputs.prepared_case / "reflections.mtz").write_bytes(b"changed")
    with pytest.raises(ValueError):
        bind_reference_prepared_case(inputs, tmp_path / "reference")
    assert not (tmp_path / "reference").exists()
