"""Fixed two-case planning and non-acceptance evidence, not native execution."""

import gzip
import json
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.m6_nextflow import (
    M6TrackPlanRequest,
    plan_m6_nextflow_track,
)
from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
from genome_to_diffraction.benchmarks.m6_runner import (
    M6RunnerBundleRequest,
    build_m6_runner_bundle,
)
from genome_to_diffraction.benchmarks.m6_scientific import (
    M6_NATIVE_CONTROL_ADAPTER,
    M6_NATIVE_CONTROL_CASE_IDS,
    m6_execution_case_ids,
    m6_track_case_ids,
    verify_m6_native_control_output,
    verify_m6_scientific_output,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.models import (
    ValidationError,
    controller_kind_for_profile,
)
from genome_to_diffraction.ids import canonical_digest
from tests.unit.test_hpc_client import FakeTransport, _config, _controller
from tests.unit.test_m6_benchmark import (
    PROTOCOL,
    ROOT,
    _prepared_manifest,
    _synthetic_scientific_output,
)


def test_native_control_plan_keeps_complete_inputs_and_separates_purpose(
    tmp_path: Path,
) -> None:
    preparation = _prepared_manifest(tmp_path, load_m6_protocol(PROTOCOL))
    bundle = build_m6_runner_bundle(
        M6RunnerBundleRequest(
            protocol=PROTOCOL,
            preparation_manifest=preparation,
            output_directory=tmp_path / "runner",
            archive=tmp_path / "runner.tar",
        )
    )
    before = {
        path.relative_to(bundle.runner_manifest.parent): sha256_file(path)
        for path in bundle.runner_manifest.parent.rglob("*")
        if path.is_file()
    }
    plans = {
        purpose: plan_m6_nextflow_track(
            M6TrackPlanRequest(
                runner_root=bundle.runner_manifest.parent,
                database_manifest=ROOT / "tests/fixtures/stubs/database_manifest.json",
                software_lock=ROOT / "pixi.lock",
                track="operational",
                output_directory=tmp_path / purpose,
                execution_purpose=purpose,
            )
        )
        for purpose in ("benchmark", "native_control")
    }
    full, native = plans["benchmark"], plans["native_control"]
    manifest = json.loads(native.plan_manifest.read_text())
    assert native.case_task_count == 2
    assert manifest["case_ids"] == list(M6_NATIVE_CONTROL_CASE_IDS)
    assert manifest["execution_purpose"] == "native_control"
    assert manifest["benchmark_acceptance_claim"] is False
    assert manifest["adapter_version"] == "m6-native-control-plan-v1"
    assert (
        json.loads(full.plan_manifest.read_text())["adapter_version"]
        != manifest["adapter_version"]
    )
    assert full.case_task_count == 36
    assert native.catalogue_task_count == 1
    for catalogue in native.plan_directory.glob("catalogue_tasks/*/catalogue.faa"):
        original = full.plan_directory / catalogue.relative_to(native.plan_directory)
        assert catalogue.read_bytes() == original.read_bytes()
    assert before == {
        path.relative_to(bundle.runner_manifest.parent): sha256_file(path)
        for path in bundle.runner_manifest.parent.rglob("*")
        if path.is_file()
    }


def _native_output(root: Path) -> Path:
    output = _synthetic_scientific_output(
        root, adapter_version="m6-nextflow-run-v3-stages"
    )
    old_summary = output / "m6_scientific_summary.json"
    summary = json.loads(old_summary.read_text())
    output_names = {
        "case_results": "m6_case_results.jsonl",
        "candidate_rankings": "m6_candidate_rankings.jsonl",
        "candidate_rankings_gzip": "m6_candidate_rankings.jsonl.gz",
        "model_policy_results": "m6_model_policy_results.jsonl",
        "first_copy_results": "m6_first_copy_results.jsonl",
        "additional_copy_results": "m6_additional_copy_results.jsonl",
        "refinement_results": "m6_refinement_results.jsonl",
        "sequence_results": "m6_sequence_results.jsonl",
        "sequence_summary": "m6_sequence_summary.jsonl",
    }
    for name in ("m6_case_results.jsonl", "m6_candidate_rankings.jsonl"):
        path = output / name
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows = [row for row in rows if row["case_id"] in M6_NATIVE_CONTROL_CASE_IDS]
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    ranking = (output / "m6_candidate_rankings.jsonl").read_bytes()
    (output / "m6_candidate_rankings.jsonl.gz").write_bytes(
        gzip.compress(ranking, mtime=0)
    )
    cases = tuple(
        json.loads(line)
        for line in (output / "m6_case_results.jsonl").read_text().splitlines()
    )
    hashes = {key: sha256_file(output / name) for key, name in output_names.items()}
    summary.update(
        adapter_version=M6_NATIVE_CONTROL_ADAPTER,
        case_count=2,
        case_ids=list(M6_NATIVE_CONTROL_CASE_IDS),
        execution_purpose="native_control",
        benchmark_acceptance_claim=False,
        case_evidence_digest=canonical_digest(cases),
        outputs=hashes,
        scientific_output_digest=canonical_digest(hashes),
    )
    summary["cache_key"] = canonical_digest(
        {
            "adapter_version": M6_NATIVE_CONTROL_ADAPTER,
            "track": "operational",
            "input_sha256": summary["input_sha256"],
        }
    )
    atomic_write_json(output / "m6_native_control_summary.json", summary)
    old_summary.unlink()
    return output


def test_native_control_output_is_never_full_benchmark_acceptance(
    tmp_path: Path,
) -> None:
    output = _native_output(tmp_path)
    report = json.loads(verify_m6_native_control_output(output).read_text())
    assert report["case_count"] == 2
    assert report["execution_purpose"] == "native_control"
    assert report["benchmark_acceptance_claim"] is False
    disguised = json.loads((output / "m6_native_control_summary.json").read_text())
    disguised["case_ids"] = list(m6_track_case_ids("operational"))
    atomic_write_json(output / "m6_scientific_summary.json", disguised)
    with pytest.raises(PublicControlError, match="summary identity"):
        verify_m6_scientific_output(output, "operational")


@pytest.mark.parametrize("value", (True, None, "false"))
def test_native_control_requires_explicit_false_acceptance_claim(
    tmp_path: Path, value: object
) -> None:
    output = _native_output(tmp_path)
    path = output / "m6_native_control_summary.json"
    summary = json.loads(path.read_text())
    summary["benchmark_acceptance_claim"] = value
    atomic_write_json(path, summary)
    with pytest.raises(PublicControlError, match="non-acceptance"):
        verify_m6_native_control_output(output)


def test_native_control_cannot_select_leakage_or_another_site() -> None:
    assert m6_execution_case_ids("operational", "native_control") == (
        "M6C001",
        "M6C025",
    )
    with pytest.raises(ValueError, match="fixed operational"):
        m6_execution_case_ids("leakage", "native_control")
    assert controller_kind_for_profile("raven", "m6-native-control") == "login_process"
    for site in ("marmic", "viper-cpu"):
        with pytest.raises(ValidationError, match="only for Raven"):
            controller_kind_for_profile(site, "m6-native-control")


def test_native_control_stage_keeps_the_confirmed_archive_and_purpose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / ".untracked/runner.tar"
    archive.parent.mkdir()
    archive.write_bytes(b"confirmed complete runner")
    digest = sha256_file(archive)
    monkeypatch.setattr(
        "genome_to_diffraction.hpc.client._inspect_m6_runner_archive",
        lambda candidate, **kwargs: (
            candidate,
            digest,
            candidate.stat().st_size,
            "9" * 64,
            63,
            65,
        ),
    )
    transport = FakeTransport(stage_site_id="raven")
    controller = _controller(tmp_path, transport)
    controller.config = _config(tmp_path, site_id="raven")
    result = controller.m6_scientific_stage(
        "HEAD",
        archive,
        digest,
        "operational",
        execution_purpose="native_control",
    )
    assert result["profile"] == "m6-native-control"
    assert result["execution_purpose"] == "native_control"
    assert result["case_count"] == 63 and result["object_count"] == 65
    assert result["maximum_cpu_count"] == 32 and result["maximum_memory_gb"] == 96.0
    assert transport.m6_scientific_archive == archive.read_bytes()
    operation, arguments = transport.calls[-1]
    assert operation == "m6-scientific-stage"
    assert arguments[9:] == ("operational", "native_control")


@pytest.mark.parametrize(
    ("site", "track", "purpose", "parent"),
    [
        ("marmic", "operational", "native_control", None),
        ("raven", "leakage", "native_control", None),
        ("raven", "operational", "native_control", "unreviewed-parent"),
        ("raven", "operational", "unreviewed-purpose", None),
    ],
)
def test_native_control_invalid_authority_never_reaches_transport(
    tmp_path: Path,
    site: str,
    track: str,
    purpose: str,
    parent: str | None,
) -> None:
    transport = FakeTransport(stage_site_id=site)
    controller = _controller(tmp_path, transport)
    controller.config = _config(tmp_path, site_id=site)
    with pytest.raises(
        ValidationError, match=r"native control requires|purpose is not reviewed"
    ):
        controller.m6_scientific_stage(
            "HEAD",
            tmp_path / "absent.tar",
            "a" * 64,
            track,
            execution_purpose=purpose,
            operational_parent_run_id=parent,
        )
    assert transport.calls == []
