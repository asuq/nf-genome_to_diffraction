"""Frozen comparison admission, paired evidence and pre-submission workloads."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from genome_to_diffraction.benchmarks.m6_advancement import m6_order_eligible_seeds
from genome_to_diffraction.benchmarks.m6_comparison import (
    _prepare_cohort,
    freeze_m6_comparison_advancement,
    prepare_m6_comparison,
    select_m6_comparison_seeds,
    validate_m6_comparison_advancement,
    validate_m6_comparison_plan,
)
from genome_to_diffraction.benchmarks.m6_comparison_policy import (
    M6_COMPARISON_ARMS,
    M6_COMPARISON_CASES,
    M6_COMPARISON_SHA256,
    M6ComparisonArmContext,
    M6ComparisonCohort,
    comparison_case_digest,
    load_comparison_cohort,
)
from genome_to_diffraction.benchmarks.m6_evaluation import M6CollectedEvidence
from genome_to_diffraction.benchmarks.m6_nextflow import (
    M6CaseTask,
    M6HypothesisGroupTask,
)
from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
from genome_to_diffraction.benchmarks.m6_scientific import m6_track_case_ids
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.matthews.enumerate import enumerate_group
from genome_to_diffraction.ranking.funnel import build_diverse_first_copy_funnel
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import CrystalEntry, PipelineConfig
from genome_to_diffraction.schemas.results import (
    MtzPreflightRecord,
    SequenceGroupRecord,
)
from tests.unit.test_m6_benchmark import _evidence
from tests.unit.test_m6_seed_selection import _case
from tests.unit.test_ranking_funnel import _diverse_request

ROOT = Path(__file__).resolve().parents[2]
RECIPE = ROOT / "benchmarks/m6/ranking-comparison-v1.yaml"
PROTOCOL = ROOT / "benchmarks/m6/protocol.yaml"
PHENIX = ROOT / "tests/fixtures/stubs/phenix_install_manifest.json"


def _prepared_case(tmp_path: Path, case_id: str, *, active: bool) -> Path:
    case = tmp_path / case_id
    case.mkdir(parents=True)
    request = _diverse_request(tmp_path / f"inputs-{case_id}", asu_volume_a3=40_000.0)
    config = case / "analysis_config.json"
    atomic_write_json(config, yaml.safe_load(request.pipeline_config.read_text()))
    (case / "reflections.mtz").write_bytes(b"synthetic fixed reflections")
    for name, source in (
        ("all_sequence_groups.jsonl", request.sequence_groups_jsonl),
        ("all_source_records.jsonl", request.source_records_jsonl),
    ):
        assert source is not None
        shutil.copy2(source, case / name)
    task = M6CaseTask(
        schema_version="1.0",
        case_id=case_id,
        track="operational"
        if case_id in m6_track_case_ids("operational")
        else "leakage",
        catalogue_key="a" * 64,
        reflections_sha256=sha256_file(case / "reflections.mtz"),
        analysis_config_sha256=sha256_file(config),
        model_policy_sha256="b" * 64,
    )
    atomic_write_json(case / "case_task.json", task.model_dump(mode="json"))
    hypotheses = ()
    outputs = {}
    if active:
        preflight = MtzPreflightRecord.model_validate_json(
            request.mtz_preflight_jsonl.read_bytes()
        ).model_copy(update={"crystal_id": case_id})
        atomic_write_text(
            request.mtz_preflight_jsonl, canonical_json_text(preflight) + "\n"
        )
        group = SequenceGroupRecord.model_validate_json(
            request.sequence_groups_jsonl.read_bytes()
        )
        typed_config = load_contract(config, "pipeline-config", progress=False)
        assert isinstance(typed_config, PipelineConfig)
        rows = enumerate_group(
            group,
            CrystalEntry(
                crystal_id=case_id,
                mtz="input.mtz",
                catalogue_id="example_archaeon_refseq",
                allow_remote_sequence_submission=False,
            ),
            preflight,
            typed_config,
        )
        matthews = case / "matthews/matthews_hypotheses.jsonl"
        matthews.parent.mkdir()
        atomic_write_text(
            matthews, "".join(canonical_json_text(row) + "\n" for row in rows)
        )
        result = build_diverse_first_copy_funnel(
            replace(
                request,
                pipeline_config=config,
                crystal_ids=(case_id,),
                matthews_hypotheses_jsonl=matthews,
                output_directory=case / "first-copy-funnel",
                maximum_first_copy_jobs=25,
            )
        )
        hypotheses = result.hypotheses
        outputs["funnel_manifest"] = sha256_file(result.manifest_json)
    plan = M6HypothesisGroupTask(
        schema_version="1.0",
        adapter_version="m6-nextflow-case-v3-production-admission",
        case_id=case_id,
        catalogue_key=task.catalogue_key,
        early_outcome=None if active else "completed_no_model",
        hypothesis_count=len(hypotheses),
        hypothesis_ids=tuple(row.hypothesis_id for row in hypotheses),
    )
    atomic_write_json(case / "case_plan.json", plan.model_dump(mode="json"))
    outputs["case_plan"] = sha256_file(case / "case_plan.json")
    atomic_write_json(case / "bundle_manifest.json", {"output_sha256": outputs})
    return case


def _plan(tmp_path: Path) -> Path:
    cases = tuple(
        _prepared_case(tmp_path / "source", case_id, active=False)
        for case_id in M6_COMPARISON_CASES
    )
    return prepare_m6_comparison(
        cases=cases,
        recipe=RECIPE,
        protocol=PROTOCOL,
        software_lock=ROOT / "pixi.lock",
        phenix_manifest=PHENIX,
        source_commit="a" * 40,
        output=tmp_path / "plan",
    )


def test_comparison_cohorts_replay_production_and_preserve_all_model_bytes(
    tmp_path: Path,
) -> None:
    source = _prepared_case(tmp_path, "M6C001", active=True)
    weighted = _prepare_cohort(source, "copy_weighted", tmp_path / "weighted")
    solvent = _prepare_cohort(source, "solvent_density", tmp_path / "solvent")
    original = json.loads((source / "case_plan.json").read_text())
    weighted_scope = load_comparison_cohort(weighted)
    solvent_scope = load_comparison_cohort(solvent)
    assert weighted_scope.scheduled_hypothesis_ids == tuple(original["hypothesis_ids"])
    assert (
        solvent_scope.scheduled_hypothesis_ids
        != weighted_scope.scheduled_hypothesis_ids
    )
    assert weighted_scope.source_case_sha256 == solvent_scope.source_case_sha256
    registry = "first-copy-funnel/model_registry"
    assert comparison_case_digest(weighted / registry) == comparison_case_digest(
        solvent / registry
    )
    for case in (weighted, solvent):
        manifest = json.loads(
            (case / "first-copy-funnel/funnel_manifest.json").read_text()
        )
        for row in manifest["hypotheses"]:
            model = (
                case
                / "first-copy-funnel"
                / manifest["model_registry"]["path"]
                / row["model_path"]
            )
            assert sha256_file(model) == row["model_sha256"]


def test_comparison_freezes_complete_empty_case_accounting_and_rejects_mutation(
    tmp_path: Path,
) -> None:
    root = _plan(tmp_path)
    plan = validate_m6_comparison_plan(
        root, software_lock=ROOT / "pixi.lock", phenix_manifest=PHENIX
    )
    assert len(plan.cohorts) == 24
    seeds = []
    for entry in plan.cohorts:
        for arm, (prior, _) in M6_COMPARISON_ARMS.items():
            if prior == entry.cohort.admission_prior:
                seeds.append(
                    select_m6_comparison_seeds(
                        case=root / entry.case_path,
                        results=(),
                        arm=arm,
                        output=tmp_path / "seeds" / entry.cohort.case_id / arm,
                    )
                )
    frozen = freeze_m6_comparison_advancement(
        plan_root=root, seed_bundles=tuple(seeds), output=tmp_path / "frozen"
    )
    validated = validate_m6_comparison_advancement(
        frozen, software_lock=ROOT / "pixi.lock", phenix_manifest=PHENIX
    )
    assert validated["continuation_chain_count"] == 0
    assert validated["additional_copy_attempt_budget"] == 0
    assert validated["continuation_authorised"] is True
    arms = validated["arms"]
    assert isinstance(arms, list)
    assert len(arms) == 48
    (seeds[0] / "first-copy-results/changed-native.log").write_text("changed\n")
    with pytest.raises(ValueError, match="identical native evidence"):
        freeze_m6_comparison_advancement(
            plan_root=root, seed_bundles=tuple(seeds), output=tmp_path / "changed-pair"
        )
    path = frozen / "comparison_advancement.json"
    payload = json.loads(path.read_text())
    payload["additional_copy_attempt_budget"] = 1
    atomic_write_json(path, payload)
    with pytest.raises(ValueError, match="differs from retained"):
        validate_m6_comparison_advancement(
            frozen, software_lock=ROOT / "pixi.lock", phenix_manifest=PHENIX
        )


def test_frozen_comparison_rejects_other_cases_and_recipe_edits(tmp_path: Path) -> None:
    altered = tmp_path / "recipe.yaml"
    altered.write_text(RECIPE.read_text().replace("600", "601"))
    with pytest.raises(ValueError, match="frozen approval"):
        prepare_m6_comparison(
            cases=(),
            recipe=altered,
            protocol=PROTOCOL,
            software_lock=ROOT / "pixi.lock",
            phenix_manifest=PHENIX,
            source_commit="a" * 40,
            output=tmp_path / "output",
        )
    with pytest.raises(ValueError, match="twelve frozen cases"):
        prepare_m6_comparison(
            cases=(),
            recipe=RECIPE,
            protocol=PROTOCOL,
            software_lock=ROOT / "pixi.lock",
            phenix_manifest=PHENIX,
            source_commit="a" * 40,
            output=tmp_path / "output",
        )


def test_comparison_review_uses_the_same_native_results_and_explicit_arm(
    tmp_path: Path,
) -> None:
    case, native = _case(tmp_path, expected_copies=2)
    plan = json.loads((case / "case_plan.json").read_text())
    digest = comparison_case_digest(case)
    payload = {
        "schema_version": "1.0",
        "comparison_id": "m6_ranking_four_arm_v1",
        "comparison_spec_sha256": M6_COMPARISON_SHA256,
        "case_id": "M6C001",
        "admission_prior": "copy_weighted",
        "source_case_sha256": digest,
        "case_sha256": digest,
        "scheduled_hypothesis_ids": plan["hypothesis_ids"],
    }
    cohort = M6ComparisonCohort.model_validate(
        {**payload, "cohort_id": content_id("m6cohort_", payload)}
    )
    atomic_write_json(case / "comparison_cohort.json", cohort.model_dump(mode="json"))
    prior = select_m6_comparison_seeds(
        case=case, results=(native,), arm="B", output=tmp_path / "prior"
    )
    production = select_m6_comparison_seeds(
        case=case, results=(native,), arm="D", output=tmp_path / "production"
    )
    assert comparison_case_digest(
        prior / "first-copy-results"
    ) == comparison_case_digest(production / "first-copy-results")
    authority = json.loads((prior / "benchmark_advancement_manifest.json").read_text())
    assert authority["comparison_context"]["arm"] == "B"
    assert authority["policy_id"] == "m6_ranking_four_arm_v1"
    assert authority["human_approval"] is False
    assert sum(authority["additional_copy_budget_by_seed"].values()) == 1
    with pytest.raises(ValueError, match="another admission cohort"):
        select_m6_comparison_seeds(
            case=case, results=(native,), arm="A", output=tmp_path / "wrong"
        )


def test_reference_review_reorders_eligible_states_using_only_the_declared_prior(
    tmp_path: Path,
) -> None:
    source = _prepared_case(tmp_path, "M6C001", active=True)
    case = _prepare_cohort(source, "copy_weighted", tmp_path / "cohort")
    hypotheses = case / "first-copy-funnel/mr_hypotheses.jsonl"
    rows = [json.loads(line) for line in hypotheses.read_text().splitlines()]
    by_status = {}
    for row in rows:
        by_status.setdefault(
            row["priority_features"]["matthews_physical_status"], []
        ).append(row)
    same_physical_class = next(
        group
        for group in by_status.values()
        if len({row["priority_features"]["matthews_prior"] for row in group}) > 1
    )
    high = max(
        same_physical_class, key=lambda row: row["priority_features"]["matthews_prior"]
    )
    low = min(
        same_physical_class, key=lambda row: row["priority_features"]["matthews_prior"]
    )
    # The input sequence is the already-authenticated production MR review order.
    eligible = (
        {"hypothesis_id": low["hypothesis_id"], "review_priority_rank": 1},
        {"hypothesis_id": high["hypothesis_id"], "review_priority_rank": 2},
    )
    cohort = load_comparison_cohort(case)
    reference = M6ComparisonArmContext(schema_version="1.0", arm="B", cohort=cohort)
    production = M6ComparisonArmContext(schema_version="1.0", arm="D", cohort=cohort)
    assert m6_order_eligible_seeds(
        eligible, reference, hypotheses_jsonl=hypotheses
    ) == tuple(reversed(eligible))
    assert (
        m6_order_eligible_seeds(eligible, production, hypotheses_jsonl=hypotheses)
        == eligible
    )


def test_comparison_assessment_cannot_enter_full_m6_acceptance() -> None:
    evidence = _evidence(load_m6_protocol(PROTOCOL)).model_dump(mode="json")
    evidence["assessments"][0]["stage_metrics"]["policy_id"] = "m6_ranking_four_arm_v1"
    with pytest.raises(ValueError, match="cannot consume comparison arms"):
        M6CollectedEvidence.model_validate(evidence)
