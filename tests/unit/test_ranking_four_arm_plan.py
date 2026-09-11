"""Fixed reference planning with the actual production truthless input producer."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
from genome_to_diffraction.benchmarks.m6_runner import (
    M6RunnerBundleRequest,
    build_m6_runner_bundle,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from tests.fixtures.ranking_four_arm_advancement import REFERENCE_CASE_IDS
from tests.fixtures.ranking_four_arm_plan import (
    ReferencePlanInputs,
    plan_reference_nextflow,
    validate_reference_plan,
)
from tests.unit.test_m6_benchmark import PROTOCOL, ROOT, _prepared_manifest


def _inputs(tmp_path: Path) -> ReferencePlanInputs:
    protocol = load_m6_protocol(PROTOCOL)
    preparation = _prepared_manifest(tmp_path, protocol)
    bundle = build_m6_runner_bundle(
        M6RunnerBundleRequest(
            protocol=PROTOCOL,
            preparation_manifest=preparation,
            output_directory=tmp_path / "runner",
            archive=tmp_path / "runner.tar",
        )
    )
    return ReferencePlanInputs(
        runner_root=bundle.runner_manifest.parent,
        database_manifest=ROOT / "tests/fixtures/stubs/database_manifest.json",
        software_lock=ROOT / "pixi.lock",
    )


def test_reference_plan_preserves_full_runner_and_original_tracks(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    before = {
        str(path): sha256_file(path)
        for path in inputs.runner_root.rglob("*")
        if path.is_file()
    }
    first = plan_reference_nextflow(inputs, tmp_path / "first")
    second = plan_reference_nextflow(inputs, tmp_path / "second")
    plan = validate_reference_plan(first, inputs)
    repeated = validate_reference_plan(second, inputs)
    # Audit timestamps remain genuine; scientific inputs and task tables repeat.
    assert plan.cases == repeated.cases
    assert plan.catalogues == repeated.catalogues
    assert plan.input_sha256 == repeated.input_sha256
    assert plan.source_sha256 == repeated.source_sha256
    assert (first.parent / "reference_case_tasks.tsv").read_bytes() == (
        second.parent / "reference_case_tasks.tsv"
    ).read_bytes()
    assert tuple(row.task.case_id for row in plan.cases) == REFERENCE_CASE_IDS
    assert len(plan.catalogues) == 1
    assert not plan.benchmark_acceptance_claim
    assert not plan.human_approval_granted
    assert {row.task.case_id: row.task.track for row in plan.cases} == {
        "M6C001": "operational",
        "M6C010": "operational",
        "M6C055": "leakage",
        "M6C025": "operational",
        "M6C037": "operational",
    }
    tables = (first.parent / "reference_case_tasks.tsv").read_text().splitlines()
    assert len(tables) == 6
    assert all(line.split("\t")[0] in REFERENCE_CASE_IDS for line in tables[1:])
    original = json.loads((inputs.runner_root / "runner_manifest.json").read_text())
    assert len(original["cases"]) == 63
    assert before == {str(path): sha256_file(path) for path in map(Path, before)}
    assert not tuple(first.parent.rglob("benchmark_advancement.json"))
    assert not tuple(first.parent.rglob("mr_seed_approval.json"))


@pytest.mark.parametrize(
    "corruption", ("case", "catalogue", "table", "foreign", "source")
)
def test_reference_plan_rejects_changed_or_foreign_outputs(
    tmp_path: Path, corruption: str
) -> None:
    inputs = _inputs(tmp_path)
    path = plan_reference_nextflow(inputs, tmp_path / "plan")
    plan = validate_reference_plan(path, inputs)
    if corruption == "case":
        target = path.parent / plan.cases[0].task_directory / "task.json"
        value = json.loads(target.read_text())
        value["track"] = "leakage"
        atomic_write_json(target, value)
    elif corruption == "catalogue":
        (path.parent / plan.catalogues[0].task_directory / "catalogue.faa").write_text(
            ">changed\nACDE\n"
        )
    elif corruption == "table":
        (path.parent / "reference_case_tasks.tsv").write_text("M6C002\n")
    elif corruption == "foreign":
        (path.parent / "unrecorded-result.json").write_text("{}\n")
    else:
        value = json.loads(path.read_text())
        value["source_sha256"]["tests/fixtures/ranking_four_arm_plan.py"] = "0" * 64
        atomic_write_json(path, value)
    with pytest.raises(ValueError, match="reference plan identity"):
        validate_reference_plan(path, inputs)


def test_reference_plan_rejects_changed_original_runner_object(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    path = plan_reference_nextflow(inputs, tmp_path / "plan")
    original = json.loads((inputs.runner_root / "runner_manifest.json").read_text())
    object_name = original["cases"][0]["objects"][0]["object"]
    target = inputs.runner_root / "objects" / object_name
    target.chmod(0o600)
    target.write_text("changed original input\n")
    with pytest.raises(PublicControlError, match="object size changed"):
        validate_reference_plan(path, inputs)
