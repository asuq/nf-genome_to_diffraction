"""Reference authority and real copy-adapter receipts with synthetic tool output."""

import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Never

import pytest

from genome_to_diffraction.benchmarks.m6_advancement import validate_m6_advancement
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.model_registry import load_all_eligible_model_registry
from genome_to_diffraction.mr.add_copy import (
    AddCopyRunRequest,
    run_additional_copy_phaser,
)
from genome_to_diffraction.mr.phaser import PhaserInputError
from genome_to_diffraction.ranking.funnel import DiverseFirstCopyFunnelRequest
from tests.fixtures.ranking_four_arm_advancement import (
    ReferenceAdvancementManifest,
    validate_reference_advancement,
    write_reference_advancement,
)
from tests.fixtures.ranking_four_arm_copy import (
    run_reference_copy_task,
    validate_reference_copy_receipt,
)
from tests.fixtures.ranking_four_arm_reference import AdmissionPrior
from tests.unit.test_add_copy_phaser import (
    NO_SOLUTION_LOG,
    POSITIVE_LOG,
    STUBS,
    _fake_runtime,
)
from tests.unit.test_ranking_four_arm_seeds import _review_case


def _unexpected_phenix(*_args: object, **_kwargs: object) -> Never:
    raise AssertionError("an already-complete seed must not invoke Phenix")


def _inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prior: AdmissionPrior = "copy_weighted",
    *,
    no_hits: bool = False,
    small_cell: bool = False,
) -> tuple[DiverseFirstCopyFunnelRequest, Path, Path, ReferenceAdvancementManifest]:
    admission, hypotheses, seeds = _review_case(
        tmp_path,
        monkeypatch,
        prior,
        no_hits=no_hits,
        crystal_id="M6C001",
        small_cell=small_cell,
    )
    path = seeds / "reference_advancement.json"
    manifest = write_reference_advancement(
        admission,
        hypotheses_jsonl=hypotheses,
        review_manifest=seeds / "review/mr_seed_review_manifest.json",
        admission_prior=prior,
        output_manifest=path,
    )
    return admission, hypotheses, path, manifest


def _copy_request(
    tmp_path: Path,
    admission: DiverseFirstCopyFunnelRequest,
    hypotheses: Path,
    manifest: ReferenceAdvancementManifest,
    *,
    seed_solution_id: str | None = None,
) -> AddCopyRunRequest:
    production_ids = {row.solution_id for row in manifest.arms[1].recommended}
    # The anti-prior synthetic fixture supplies seeds outside production's top
    # five, proving that this uses reference authority rather than spoofing M6.
    seed = (
        next(row for row in manifest.recommended if row.solution_id == seed_solution_id)
        if seed_solution_id is not None
        else next(
            row
            for row in manifest.arms[0].recommended
            if row.solution_id not in production_ids and row.expected_copy_count > 1
        )
    )
    registry_root = hypotheses.parent / "model_registry"
    registry = load_all_eligible_model_registry(
        registry_root / "all_model_registry.json"
    )
    model = next(
        row
        for row in registry.lookup(seed.sequence_group_id).models
        if row.model_id == seed.model_id
    )
    return AddCopyRunRequest(
        review_validation_json=None,
        review_package_manifest=None,
        seed_solution_id=seed.solution_id,
        hypotheses_jsonl=hypotheses,
        sequence_groups_jsonl=admission.sequence_groups_jsonl,
        preflight_jsonl=admission.mtz_preflight_jsonl,
        mtz=tmp_path / "case_task/reflections.mtz",
        search_model=registry_root / model.model_path,
        phenix_manifest=STUBS / "phenix_install_manifest.json",
        output_directory=tmp_path / "reference_copy",
        threads=16,
        progress=False,
    )


@pytest.mark.parametrize("prior", ("copy_weighted", "solvent_density"))
def test_reference_authority_rederives_both_orders_and_separate_caps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prior: AdmissionPrior
) -> None:
    admission, hypotheses, path, manifest = _inputs(tmp_path, monkeypatch, prior)
    validated = validate_reference_advancement(
        path, admission, hypotheses_jsonl=hypotheses
    )
    assert validated.manifest == manifest
    assert [row.arm for row in manifest.arms] == (
        ["B", "D"] if prior == "copy_weighted" else ["A", "C"]
    )
    assert all(
        len(arm.rows) == 25 and len(arm.recommended) == 5 for arm in manifest.arms
    )
    assert 5 < len(manifest.recommended) <= 10
    assert manifest.human_approval_granted is False
    assert manifest.execution_authority_kind == "truth_blind_rf_reference"
    with pytest.raises(ValueError):
        validate_m6_advancement(path, hypotheses_jsonl=hypotheses)
    with pytest.raises(ValueError, match="already exist"):
        write_reference_advancement(
            admission,
            hypotheses_jsonl=hypotheses,
            review_manifest=validated.review_manifest,
            admission_prior=prior,
            output_manifest=path,
        )
    assert not tuple(tmp_path.rglob("mr_seed_approval.json"))
    assert not tuple(tmp_path.rglob("additional_copy_series_results.jsonl"))


@pytest.mark.parametrize(
    "corruption", ("recommendation", "source", "scope", "inputs", "policy")
)
def test_reference_authority_rejects_rehashed_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    admission, hypotheses, path, _ = _inputs(tmp_path, monkeypatch)
    document = json.loads(path.read_text())
    if corruption == "recommendation":
        row = document["arms"][0]["rows"][0]
        row["recommended"] = not row["recommended"]
    elif corruption == "source":
        document["source_sha256"]["tests/fixtures/ranking_four_arm_copy.py"] = "a" * 64
    elif corruption == "scope":
        document["crystal_id"] = "M6C010"
    elif corruption == "inputs":
        document["input_sha256"]["admission_sequence_groups"] = "a" * 64
    else:
        document["seed_cap_per_arm"] = 6
    document["advancement_id"] = content_id(
        "rfadvance_",
        {key: value for key, value in document.items() if key != "advancement_id"},
    )
    atomic_write_json(path, document)
    with pytest.raises(ValueError):
        validate_reference_advancement(path, admission, hypotheses_jsonl=hypotheses)


def test_reference_authority_rejects_operator_scope_and_accepts_no_hit_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admission, hypotheses, path, manifest = _inputs(tmp_path, monkeypatch, no_hits=True)
    assert not manifest.recommended
    assert all(len(arm.rows) == 25 for arm in manifest.arms)
    with pytest.raises(ValueError, match="fixed known-control cohort"):
        validate_reference_advancement(
            path,
            replace(admission, crystal_ids=("operator_crystal",)),
            hypotheses_jsonl=hypotheses,
        )


def test_reference_only_seed_runs_shared_copy_engine_and_has_authentic_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admission, hypotheses, path, manifest = _inputs(tmp_path, monkeypatch)
    request = _copy_request(tmp_path, admission, hypotheses, manifest)
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)
    with pytest.raises(PhaserInputError, match="approval pair"):
        run_additional_copy_phaser(request)
    root = run_reference_copy_task(request, admission, advancement_manifest=path)
    receipt, count = validate_reference_copy_receipt(
        root, request, admission, advancement_manifest=path
    )
    command = json.loads((root / "series/phaser_command.json").read_text())
    summary = json.loads((root / "additional_copy_series_summary.json").read_text())
    assert len(receipt) == 64 and count == 1
    assert command["execution_authority_kind"] == "truth_blind_rf_reference"
    assert command["adapter_version"] == "phenix-add-copy-rf-reference-v1"
    assert command["benchmark_advancement_id"] == manifest.advancement_id
    assert command["benchmark_advancement_manifest_sha256"] == sha256_file(path)
    assert command["human_approval_granted"] is False
    assert command["search_model_sha256"] == command["original_first_copy_model_sha256"]
    assert summary["best_supported_copy_count"] == 1
    assert summary["stop_reason"] == "additional_copy_not_supported"
    assert not tuple(tmp_path.rglob("mr_seed_approval.json"))


def test_reference_series_preserves_authenticated_sequential_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admission, hypotheses, path, manifest = _inputs(tmp_path, monkeypatch)
    request = _copy_request(tmp_path, admission, hypotheses, manifest)
    _fake_runtime(
        monkeypatch, log_text=POSITIVE_LOG, write_solution=True, placement_count=(2, 2)
    )
    root = run_reference_copy_task(request, admission, advancement_manifest=path)
    summary = json.loads((root / "additional_copy_series_summary.json").read_text())
    _, count = validate_reference_copy_receipt(
        root, request, admission, advancement_manifest=path
    )
    assert summary["best_supported_copy_count"] == 2
    assert count == (1 if summary["expected_copy_count"] == 2 else 2)
    if count == 2:
        second = json.loads((root / "series/copy_03/phaser_command.json").read_text())
        assert second["parent_copy_count"] == 2
        assert second["parent_result_sha256"] == sha256_file(
            root / "series/additional_copy_result.jsonl"
        )


def test_reference_complete_root_has_zero_attempts_without_native_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admission, hypotheses, path, manifest = _inputs(
        tmp_path, monkeypatch, small_cell=True
    )
    seed = next(row for row in manifest.recommended if row.expected_copy_count == 1)
    request = _copy_request(
        tmp_path, admission, hypotheses, manifest, seed_solution_id=seed.solution_id
    )
    monkeypatch.setattr(
        "genome_to_diffraction.mr.add_copy.capture_from_manifest",
        _unexpected_phenix,
    )
    root = run_reference_copy_task(request, admission, advancement_manifest=path)
    _, count = validate_reference_copy_receipt(
        root, request, admission, advancement_manifest=path
    )
    summary = json.loads((root / "additional_copy_series_summary.json").read_text())
    assert count == 0
    assert summary["stop_reason"] == "first_copy_already_reached_expected_count"
    assert summary["best_supported_copy_count"] == 1
    assert not (root / "series").exists()
    assert not tuple(root.rglob("phaser_command.json"))


@pytest.mark.parametrize("override", ("seed", "production", "model_override", "mtz"))
def test_reference_executor_rejects_foreign_inputs_before_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: str
) -> None:
    admission, hypotheses, path, manifest = _inputs(tmp_path, monkeypatch)
    request = _copy_request(tmp_path, admission, hypotheses, manifest)
    if override == "seed":
        selected = {row.solution_id for row in manifest.recommended}
        other = next(
            row.original.solution_id
            for row in manifest.arms[0].rows
            if row.original.solution_id not in selected
        )
        request = replace(request, seed_solution_id=other)
    elif override == "production":
        request = replace(
            request,
            benchmark_advancement_manifest=path.parent / "benchmark_advancement.json",
        )
    elif override == "model_override":
        request = replace(
            request, expected_search_model_sha256=sha256_file(request.search_model)
        )
    else:
        request.mtz.write_bytes(b"changed synthetic diffraction")
    with pytest.raises(PhaserInputError):
        run_reference_copy_task(request, admission, advancement_manifest=path)
    assert not request.output_directory.exists()


def test_reference_native_failure_is_not_relabelled_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admission, hypotheses, path, manifest = _inputs(tmp_path, monkeypatch)
    request = _copy_request(tmp_path, admission, hypotheses, manifest)
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)
    monkeypatch.setattr(
        "genome_to_diffraction.mr.add_copy.capture_from_manifest",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 1, b"", b"synthetic failure"
        ),
    )
    root = run_reference_copy_task(request, admission, advancement_manifest=path)
    result = json.loads((root / "series/additional_copy_result.json").read_text())
    assert result["execution_status"] == "failed_tool_execution"
    assert result["additional_copy_supported"] is False
    assert result["best_supported_copy_count"] == 1
    assert result["child_solution_id"] is None


@pytest.mark.parametrize(
    "corruption", ("model", "parent", "parameters", "log", "authority")
)
def test_reference_receipt_rejects_changed_native_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    admission, hypotheses, path, manifest = _inputs(tmp_path, monkeypatch)
    request = _copy_request(tmp_path, admission, hypotheses, manifest)
    _fake_runtime(monkeypatch, log_text=NO_SOLUTION_LOG, write_solution=False)
    root = run_reference_copy_task(request, admission, advancement_manifest=path)
    if corruption in {"model", "authority"}:
        command_path = root / "series/phaser_command.json"
        command = json.loads(command_path.read_text())
        command[
            "search_model_sha256"
            if corruption == "model"
            else "execution_authority_kind"
        ] = "changed"
        atomic_write_json(command_path, command)
    elif corruption == "parent":
        (root / "best_parent.pdb").write_text("changed synthetic parent\n")
    elif corruption == "parameters":
        (root / "series/add_copy.eff").write_text("changed synthetic parameters\n")
    else:
        (root / "series/PHASER.log").unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        validate_reference_copy_receipt(
            root, request, admission, advancement_manifest=path
        )
