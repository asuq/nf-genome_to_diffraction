"""Fixed Raven dispatch and evidence checks; all native records here are synthetic."""

import csv
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc import raven_identification as controller
from genome_to_diffraction.hpc import raven_qualification as qualification
from genome_to_diffraction.hpc.raven_m6 import (
    collection_manifest,
    operational_precheck,
    validate_operational_parent,
)


def _launch(root: Path, stage: str = "control-first-copy"):
    source = root / "sources" / ("a" * 40)
    source.mkdir(parents=True)
    (source / "external/nf-helper").mkdir(parents=True)
    (source / "pixi.lock").write_text("synthetic locked environment\n")
    inputs = root / "inputs"
    inputs.mkdir()
    parameters = {}
    for key in qualification._PARAMETERS[stage]:
        path = inputs / key
        if key in qualification._DIRECTORIES:
            path.mkdir()
            (path / "input.json").write_text("{}\n")
        else:
            path.write_text('{"crystal_id":"9ECN"}\n' if key == "preflight" else "{}\n")
        parameters[key] = key
    atomic_write_json(
        inputs / qualification.INPUT_DOCUMENT,
        {
            "schema_version": "1.0",
            "source_commit": "a" * 40,
            "control_id": "9ECN" if stage.startswith("control-") else None,
            "parameters": parameters,
        },
    )
    atomic_write_json(
        inputs / "exact-source-ci.json",
        {
            "schema_version": "1.0",
            "head_sha": "a" * 40,
            "run_id": 123,
            "job_id": 456,
            "conclusion": "success",
        },
    )
    phenix = root / "phenix.json"
    phenix.write_text("{}\n")
    migration = (
        root
        / "runs"
        / ("gtd-identification-screen-20260907T000000Z-" + "f" * 12 + "-01234567")
    )
    (migration / "collected").mkdir(parents=True)
    migration_spec = controller.RavenLaunch(
        schema_version="1.0",
        run_id=migration.name,
        owner_id="e" * 32,
        site_id="raven",
        account="test_cpu",
        source_commit="f" * 40,
        source_root=root / "sources" / ("f" * 40),
        input_root=root / "smoke",
        input_id="identificationinputs_" + "c" * 64,
        phenix_manifest=phenix,
        phenix_manifest_sha256=sha256_file(phenix),
        mtz_root=root / "mtz",
        run_mode="smoke",
    )
    atomic_write_json(migration / "launch.json", migration_spec.model_dump(mode="json"))
    _terminal(migration, migration_spec)
    state_path = migration / "state.json"
    state = json.loads(state_path.read_text())
    state["execution_case_count"] = 1
    atomic_write_json(state_path, state)
    case_id = "identcase_" + "7" * 64
    native = migration / "results/mr" / case_id / "run.json"
    native.parent.mkdir(parents=True)
    atomic_write_json(
        native,
        {
            "case_id": case_id,
            "status": "completed_no_hit",
            "exit_code": 0,
            "resources": {"cpus": 8, "memory_gb": 32, "time_hours": 24},
        },
    )
    atomic_write_json(
        migration / "collected/assessment.json",
        {
            "cases": [
                {
                    "case": {"case_id": case_id},
                    "selected_for_this_run": True,
                    "execution_state": "completed_no_hit",
                }
            ],
            "tasks": [
                {
                    "status": "COMPLETED",
                    "native_id": "100",
                    "tag": f"identification-mr:{case_id}",
                    "cpus": "8",
                    "memory": "32 GB",
                    "time": "24h",
                }
            ],
            "artifacts": [
                {
                    "path": f"mr/{case_id}/run.json",
                    "sha256": sha256_file(native),
                }
            ],
        },
    )
    run = root / "runs" / f"gtd-{stage}-20260908T000000Z-{'a' * 12}-01234567"
    run.mkdir()
    spec = qualification.RavenQualificationLaunch(
        schema_version="2.0",
        run_id=run.name,
        owner_id="b" * 32,
        site_id="raven",
        stage=stage,
        account="test_cpu",
        source_commit="a" * 40,
        source_tree="d" * 40,
        nf_helper_commit="c" * 40,
        pixi_version="0.55.0",
        pixi_lock_sha256=sha256_file(source / "pixi.lock"),
        source_root=source,
        input_root=inputs,
        input_id=qualification.input_identity(inputs),
        phenix_manifest=phenix,
        phenix_manifest_sha256=sha256_file(phenix),
        ci_evidence_sha256=sha256_file(inputs / "exact-source-ci.json"),
        migration_run=migration,
        migration_launch_sha256=sha256_file(migration / "launch.json"),
        migration_state_sha256=sha256_file(migration / "state.json"),
        migration_assessment_sha256=sha256_file(
            migration / "collected/assessment.json"
        ),
        operational_parent_run=root / "runs/parent" if stage == "m6-leakage" else None,
        operational_precheck_sha256="1" * 64 if stage == "m6-leakage" else None,
        runner_archive=phenix if stage in {"m6-operational", "m6-leakage"} else None,
        runner_archive_sha256=sha256_file(phenix)
        if stage in {"m6-operational", "m6-leakage"}
        else None,
        parent_run_id="screen-parent" if stage.startswith("unknown-") else None,
        sequence_parent_run_id="sequence-parent"
        if stage == "unknown-single-component"
        else None,
        screen_parent_run=root / "runs/screen-parent"
        if stage == "unknown-single-component"
        else None,
        continuation_handoff_root=inputs / run.name
        if stage == "unknown-single-component"
        else None,
    )
    return run, spec


def _terminal(root, spec, state="COMPLETED"):
    atomic_write_json(
        root / "controller.json",
        {
            "owner_id": spec.owner_id,
            "run_id": spec.run_id,
            "process": {"pid": 123, "start_ticks": "456", "boot_id": "synthetic"},
        },
    )
    atomic_write_json(
        root / "state.json",
        {
            "state": state,
            "owner_id": spec.owner_id,
            "run_id": spec.run_id,
            "source_commit": spec.source_commit,
            "input_id": spec.input_id,
            "exit_code": 0 if state == "COMPLETED" else 1,
        },
    )


class _Git:
    def __init__(self, path):
        self.path = path

    def resolve_commit(self, ref):
        if self.path.name == "nf-helper":
            return "c" * 40
        return ("d" if ref == "HEAD^{tree}" else "a") * 40

    def ensure_clean(self):
        return None


@pytest.mark.parametrize("stage", tuple(qualification._PARAMETERS))
def test_fixed_raven_commands_use_existing_graphs_and_owned_cache(tmp_path, stage):
    run, spec = _launch(tmp_path, stage)
    command = qualification.nextflow_command(run, spec)
    assert command[command.index("-profile") + 1] == "raven"
    assert command[command.index("-work-dir") + 1] == str(
        qualification.cache_root(run, spec) / "work"
    )
    assert ("-resume" in command) == (stage == "m6-leakage")
    assert "-resume" in qualification.nextflow_command(run, spec, resume=True)
    assert "-qs" not in command
    assert controller.parse_launch(spec.model_dump_json()) == spec
    assert controller.launch_profile(spec) == stage
    if stage == "unknown-pass2":
        assert "--phenix_manifest" not in command
        assert command[command.index("--phase3_operation") + 1] == "composition_beam"
    if stage.startswith("m6-") and "comparison" not in stage:
        assert command[command.index("--execution_policy") + 1].endswith(
            "execution-nextflow-raven-v1.yaml"
        )


def test_raven_rejects_stale_ci_input_mutation_and_parameter_escape(
    tmp_path, monkeypatch
):
    run, spec = _launch(tmp_path)
    monkeypatch.setattr(
        "genome_to_diffraction.hpc.client.SubprocessGitRepository", _Git
    )
    qualification.validate_launch(run, tmp_path, spec)
    ci = spec.input_root / "exact-source-ci.json"
    payload = json.loads(ci.read_text())
    payload["head_sha"] = "e" * 40
    atomic_write_json(ci, payload)
    with pytest.raises(ValueError, match="input identity changed"):
        qualification.validate_launch(run, tmp_path, spec)
    changed = spec.model_copy(
        update={
            "input_id": qualification.input_identity(spec.input_root),
            "ci_evidence_sha256": sha256_file(ci),
        }
    )
    with pytest.raises(ValueError, match="successful exact-source CI"):
        qualification.validate_launch(run, tmp_path, changed)
    document_path = spec.input_root / qualification.INPUT_DOCUMENT
    document = json.loads(document_path.read_text())
    document["parameters"]["mtz"] = "../phenix.json"
    atomic_write_json(document_path, document)
    with pytest.raises(ValueError, match="escapes"):
        qualification.load_parameters(spec)


def test_raven_migration_failed_native_case_cannot_unlock_qualification(tmp_path):
    _, spec = _launch(tmp_path)
    path = spec.migration_run / "collected/assessment.json"
    payload = json.loads(path.read_text())
    payload["cases"][0]["execution_state"] = "output_missing"
    atomic_write_json(path, payload)
    changed = spec.model_copy(update={"migration_assessment_sha256": sha256_file(path)})
    with pytest.raises(ValueError, match="incomplete native evidence"):
        qualification._migration_ready(changed, tmp_path)


@pytest.mark.parametrize("native_exit", [0, 1])
def test_raven_controller_retains_failed_work_and_records_resolved_time(
    tmp_path,
    monkeypatch,
    native_exit,
):
    run, spec = _launch(tmp_path)
    calls = []
    monkeypatch.setattr(controller, "SubprocessGitRepository", _Git)
    monkeypatch.setattr(
        "genome_to_diffraction.hpc.client.SubprocessGitRepository", _Git
    )
    monkeypatch.setattr(controller.signal, "signal", lambda *_: None)
    monkeypatch.setattr(controller, "_process_identity", lambda pid: {"pid": pid})
    monkeypatch.setattr(
        controller.subprocess, "run", lambda *_, **__: SimpleNamespace(returncode=0)
    )
    work = qualification.cache_root(run, spec) / "work/aa/task"
    work.mkdir(parents=True)
    (work / ".command.sh").write_text("synthetic native command\n")
    (work / "partial").mkdir()
    (work / "partial/PHASER.log").write_text("retained native failure\n")

    class Child:
        pid = 4321

        def __init__(self, command, **kwargs):
            calls.append(command)
            assert kwargs["env"]["TMPDIR"] == str(run / "tmp")
            assert kwargs["env"]["NXF_CACHE_DIR"].startswith(str(run / "cache"))

        def wait(self):
            output = run / "results"
            (output / "pipeline_info").mkdir(exist_ok=True)
            (output / "native.json").write_text('{"status":"completed_no_hit"}\n')
            (output / "native.mtz").write_bytes(b"synthetic MTZ bytes")
            fields = (
                "task_id",
                "hash",
                "attempt",
                "workdir",
                "time",
                "cpus",
                "memory",
                "native_id",
                "status",
            )
            with (output / "pipeline_info/trace.tsv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fields, delimiter="\t")
                writer.writeheader()
                writer.writerow(
                    dict(
                        zip(
                            fields,
                            (
                                "1",
                                "aa/task",
                                "1",
                                str(work),
                                "24h",
                                "8",
                                "32 GB",
                                "100",
                                "FAILED"
                                if native_exit
                                else "COMPLETED"
                                if len(calls) == 1
                                else "CACHED",
                            ),
                            strict=True,
                        )
                    )
                )
                if native_exit:
                    writer.writerow(
                        dict(
                            zip(
                                fields,
                                (
                                    "2",
                                    "-",
                                    "1",
                                    "-",
                                    "-",
                                    "-",
                                    "-",
                                    "-",
                                    "ABORTED",
                                ),
                                strict=True,
                            )
                        )
                    )
            return native_exit

    monkeypatch.setattr(controller.subprocess, "Popen", Child)
    assert controller._run(run, tmp_path, spec) == native_exit
    state = json.loads((run / "state.json").read_text())
    assert state["state"] == ("FAILED" if native_exit else "COMPLETED")
    assert len(calls) == (1 if native_exit else 2)
    evidence = json.loads((run / "collected/resource-evidence.json").read_text())
    assert evidence["controller_kind"] == "login_process"
    assert evidence["tasks"][0]["time"] == "24h"
    assert not (run / "collected/results/native.mtz").exists()
    if native_exit:
        assert evidence["all_resolved_allocations_verified"] is False
        assert evidence["tasks"][1]["status"] == "ABORTED"
        assert evidence["incomplete_evidence"]
        retained = run / "collected/tasks/1-attempt-1/native/partial/PHASER.log"
        assert retained.read_text() == "retained native failure\n"


def test_raven_collection_rejects_changed_qualification_snapshot(tmp_path):
    run, spec = _launch(tmp_path, "m6-operational")
    _terminal(run, spec)
    atomic_write_json(run / "launch.json", spec.model_dump(mode="json"))
    output = run / "qualification"
    output.mkdir()
    provenance = output / "m6-input-provenance.json"
    atomic_write_json(
        provenance,
        {
            "run_id": spec.run_id,
            "input_id": spec.input_id,
            "runner_archive_sha256": spec.runner_archive_sha256,
            "software_lock_sha256": spec.pixi_lock_sha256,
            "runner_manifest_sha256": "2" * 64,
            "database_manifest_sha256": "3" * 64,
        },
    )
    summary = output / "m6-scientific-summary.json"
    atomic_write_json(
        summary,
        {
            "input_sha256": {
                "software_lock": spec.pixi_lock_sha256,
                "phenix_manifest": spec.phenix_manifest_sha256,
                "runner_manifest": "2" * 64,
                "database_manifest": "3" * 64,
            }
        },
    )
    (output / "m6-scientific-checksums.sha256").write_text(
        f"{sha256_file(provenance)}  {provenance.name}\n"
        f"{sha256_file(summary)}  {summary.name}\n"
    )
    assert collection_manifest(run)["controller_kind"] == "login_process"
    provenance.write_text("{}\n")
    with pytest.raises(ValueError, match="checksum changed"):
        collection_manifest(run)


def test_raven_leakage_rejects_failed_parent_before_any_output_reuse(tmp_path):
    run, operational = _launch(tmp_path, "m6-operational")
    atomic_write_json(run / "launch.json", operational.model_dump(mode="json"))
    _terminal(run, operational, state="FAILED")
    leakage = operational.model_copy(
        update={
            "stage": "m6-leakage",
            "operational_parent_run": run,
            "operational_precheck_sha256": "4" * 64,
        }
    )
    with pytest.raises(ValueError, match="terminal binding differs"):
        validate_operational_parent(tmp_path, leakage)


def test_full_m6_collector_accepts_real_raven_record_shape(tmp_path):
    from genome_to_diffraction.benchmarks.m6_collection import (
        M6CollectionRequest,
        collect_m6_evidence,
    )
    from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
    from tests.unit.test_m6_benchmark import (
        EXECUTION_POLICY,
        _private_truth_file,
        _synthetic_collection,
        _synthetic_collection_protocol,
    )

    protocol_path = _synthetic_collection_protocol(tmp_path)
    policy = EXECUTION_POLICY.with_name("execution-nextflow-raven-v1.yaml")
    shutil.copyfile(policy, protocol_path.with_name(policy.name))
    protocol = load_m6_protocol(protocol_path)
    original_collections = {
        track: _synthetic_collection(
            tmp_path,
            track=track,
            adapter_version="m6-nextflow-run-v3",
            commit="a" * 40,
            protocol_path=protocol_path,
            controller_stage=True,
        )
        for track in ("operational", "leakage")
    }
    collections = []
    operational_spec = None
    for track in ("operational", "leakage"):
        root = original_collections[track]
        old = json.loads((root / "manifest.json").read_text())
        original = root / "artifacts/qualification"
        output = root / "qualification"
        shutil.copytree(original, output)
        _, spec = _launch(tmp_path / f"launch-{track}", f"m6-{track}")
        summary = json.loads((output / "m6-scientific-summary.json").read_text())
        inputs = summary["input_sha256"]
        updates = {
            "run_id": old["run_id"],
            "source_commit": old["commit"],
            "nf_helper_commit": old["nf_helper_commit"],
            "pixi_version": old["pixi_version"].removeprefix("pixi "),
            "pixi_lock_sha256": old["pixi_lock_sha256"],
            "phenix_manifest_sha256": inputs["phenix_manifest"],
            "runner_archive_sha256": (root / "state/m6-runner-archive-sha256")
            .read_text()
            .strip(),
        }
        if track == "leakage":
            assert operational_spec is not None
            updates.update(
                operational_parent_run=Path("/ptmp/test/runs")
                / operational_spec.run_id,
                operational_precheck_sha256=operational_precheck(collections[0]),
            )
        spec = spec.model_copy(update=updates)
        qualification.RavenQualificationLaunch.model_validate_json(
            spec.model_dump_json()
        )
        atomic_write_json(root / "launch.json", spec.model_dump(mode="json"))
        _terminal(root, spec)
        (root / "manifest.json").unlink()
        atomic_write_json(
            output / "m6-input-provenance.json",
            {
                "run_id": spec.run_id,
                "input_id": spec.input_id,
                "runner_archive_sha256": spec.runner_archive_sha256,
                "software_lock_sha256": spec.pixi_lock_sha256,
                "runner_manifest_sha256": inputs["runner_manifest"],
                "database_manifest_sha256": inputs["database_manifest"],
            },
        )
        for name in ("m6-runtime-provenance.json", "m6-child-resource-evidence.json"):
            path = output / name
            record = json.loads(path.read_text())
            if name == "m6-runtime-provenance.json":
                record["execution_policy"] = "m6_nextflow_slurm_raven_v1"
                record["controller_kind"] = "login_process"
            else:
                record["execution_policy_id"] = "m6_nextflow_slurm_raven_v1"
                record["execution_policy_sha256"] = sha256_file(policy)
            atomic_write_json(path, record)
        checksums = output / "m6-scientific-checksums.sha256"
        checksums.write_text(
            "".join(
                f"{sha256_file(path)}  {path.relative_to(output).as_posix()}\n"
                for path in sorted(output.rglob("*"))
                if path.is_file() and path != checksums
            )
        )
        collections.append(root)
        if track == "operational":
            operational_spec = spec
    truth = _private_truth_file(tmp_path, protocol_path, protocol)
    result = collect_m6_evidence(
        M6CollectionRequest(
            protocol=protocol_path,
            private_truth_map=truth,
            operational_collection=collections[0],
            leakage_collection=collections[1],
            output=tmp_path / "raven-evidence.json",
        )
    )
    assert result.evidence.execution_policy_id == "m6_nextflow_slurm_raven_v1"
    assert len(result.evidence.assessments) == 63
    assert result.evidence.child_job_count == 2


def test_raven_leakage_checks_cached_bytes_without_writing_parent(
    tmp_path, monkeypatch
):
    from genome_to_diffraction.hpc import raven_m6

    run, spec = _launch(tmp_path, "m6-operational")
    atomic_write_json(run / "launch.json", spec.model_dump(mode="json"))
    _terminal(run, spec)
    evidence = run / "qualification"
    evidence.mkdir()
    for name in ("m6-scientific-summary.json", "m6-scientific-checksums.sha256"):
        (evidence / name).write_text("{}\n")
    scientific = run / "results/m6_scientific"
    scientific.mkdir(parents=True)
    (scientific / "result.json").write_text("{}\n")
    atomic_write_json(
        evidence / "m6-first-output-inventory.json",
        {
            "result.json": sha256_file(scientific / "result.json"),
        },
    )
    work = run / "cache/qualification/work/aa/bb"
    work.mkdir(parents=True)
    cached = work / "catalogue.json"
    cached.write_text('{"catalogue":"synthetic"}\n')
    trace = evidence / "m6-first-pipeline-info/trace.tsv"
    trace.parent.mkdir()
    trace.write_text(f"process\ttag\tworkdir\nM6_IMPORT_CATALOGUE\tc1\t{work}\n")
    atomic_write_json(
        evidence / "m6-first-child-outputs.json",
        {
            "schema_version": "1.1",
            "track": "operational",
            "phase": "first",
            "trace_sha256": sha256_file(trace),
            "baseline_sha256": None,
            "task_count": 1,
            "tasks": [
                {
                    "process": "M6_IMPORT_CATALOGUE",
                    "tag": "c1",
                    "task_hash": "aa/bb",
                    "status": "COMPLETED",
                    "outputs": [
                        {
                            "relative_path": cached.name,
                            "sha256": sha256_file(cached),
                        }
                    ],
                }
            ],
        },
    )
    # Controller/collection shape is covered above; this test isolates the
    # actual on-disk cache check before leakage can invoke any scientific work.
    monkeypatch.setattr(raven_m6, "collection_manifest", lambda _: {})
    child = spec.model_copy(
        update={
            "stage": "m6-leakage",
            "run_id": spec.run_id.replace("m6-operational", "m6-leakage"),
            "operational_parent_run": run,
            "operational_precheck_sha256": operational_precheck(run),
        }
    )
    before = {
        path: path.stat().st_mtime_ns for path in run.rglob("*") if path.is_file()
    }
    validate_operational_parent(tmp_path, child)
    assert {path: path.stat().st_mtime_ns for path in before} == before
    cached.write_text("mutated cached catalogue\n")
    with pytest.raises(ValueError, match="truthless cache changed"):
        validate_operational_parent(tmp_path, child)
