"""Original-format Phenix log/command evidence, never simulated acceptance."""

import csv
import json
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc import rf_reference_evidence as evidence_module
from genome_to_diffraction.hpc.rf_reference_evidence import (
    REFERENCE_INPUT_COPIES,
    ReferenceNativeCommand,
    command_record_expectations,
    read_reference_native_task_log,
    reference_collection_files,
    reference_native_file_inventory,
    reference_staged_search_inputs,
    reference_trace_tasks,
)
from genome_to_diffraction.ids import content_id


def _events(root: Path) -> list[dict[str, object]]:
    return [
        {
            "logger": "genome_to_diffraction.phenix",
            "message": "executing captured Phenix command",
            "command": "phenix.phaser",
            "arguments": ["original.eff"],
            "working_directory": str(root),
        },
        {
            "logger": "genome_to_diffraction.phenix",
            "message": "captured Phenix command finished",
            "command": "phenix.phaser",
            "exit_status": 1,
        },
    ]


def test_native_task_log_preserves_numeric_failure_and_original_arguments(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".command.err"
    path.write_text(
        "retained non-tool diagnostic\n"
        + "\n".join(json.dumps(row) for row in _events(tmp_path))
        + "\n"
    )
    expected = (ReferenceNativeCommand(("phenix.phaser", "original.eff"), tmp_path),)
    evidence = read_reference_native_task_log(
        path, work_directory=tmp_path, expected=expected
    )
    assert evidence.invocations[0].command == expected[0]
    assert evidence.invocations[0].exit_status == 1
    assert evidence.invocations[0].start_line == 2
    assert evidence.invocations[0].finish_line == 3
    assert evidence.other_stderr_lines == 1


@pytest.mark.parametrize(
    "change", ["missing_exit", "boolean_exit", "wrong_command", "foreign_dir", "extra"]
)
def test_native_task_log_rejects_invented_or_unbound_execution(
    tmp_path: Path, change: str
) -> None:
    rows = _events(tmp_path)
    if change == "missing_exit":
        rows.pop()
    elif change == "boolean_exit":
        rows[1]["exit_status"] = True
    elif change == "wrong_command":
        rows[1]["command"] = "phenix.refine"
    elif change == "foreign_dir":
        rows[0]["working_directory"] = str(tmp_path.parent)
    else:
        rows += _events(tmp_path)
    path = tmp_path / ".command.err"
    path.write_text("\n".join(json.dumps(row) for row in rows))
    with pytest.raises(ValueError, match="reference native"):
        read_reference_native_task_log(
            path,
            work_directory=tmp_path,
            expected=(
                ReferenceNativeCommand(("phenix.phaser", "original.eff"), tmp_path),
            ),
        )


def test_native_command_records_keep_unexecuted_sequence_check_absent(
    tmp_path: Path,
) -> None:
    record = tmp_path / "t12_command.json"
    record.write_text(
        json.dumps(
            {
                "refine_arguments": ["phenix.refine", "original.pdb", "original.mtz"],
                "sequence_arguments": None,
            }
        )
    )
    assert command_record_expectations(record, work_directory=tmp_path) == (
        ReferenceNativeCommand(
            ("phenix.refine", "original.pdb", "original.mtz"), tmp_path
        ),
    )


def test_native_task_log_rejects_duplicate_exit_fields(tmp_path: Path) -> None:
    rows = _events(tmp_path)
    path = tmp_path / ".command.err"
    path.write_text(
        json.dumps(rows[0])
        + "\n"
        + json.dumps(rows[1]).replace(
            '"exit_status": 1', '"exit_status": 1, "exit_status": 0'
        )
    )
    with pytest.raises(ValueError, match="duplicate"):
        read_reference_native_task_log(
            path,
            work_directory=tmp_path,
            expected=(
                ReferenceNativeCommand(("phenix.phaser", "original.eff"), tmp_path),
            ),
        )


def _native_task(root: Path) -> tuple[Path, Path]:
    work = root / "cache/rf-reference/work/ab" / ("c" * 30)
    work.mkdir(parents=True)
    for name in (
        ".command.sh",
        ".command.run",
        ".command.out",
        ".command.err",
        ".command.log",
        ".command.trace",
        ".exitcode",
    ):
        (work / name).write_text("0\n")
    (work / "output").mkdir()
    (work / "output/result.json").write_text('{"actual_exit":1}\n')
    trace = root / "artifacts/qualification/rf-reference-first-pipeline-info/trace.tsv"
    trace.parent.mkdir(parents=True)
    row = {
        "task_id": "1",
        "hash": "ab/cccccc",
        "native_id": "30150000",
        "process": "RF_REFERENCE_WORKFLOW:RF_FIRST_COPY",
        "tag": "original",
        "status": "COMPLETED",
        "exit": "0",
        "workdir": str(work),
    }
    with trace.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row), delimiter="\t")
        writer.writeheader()
        writer.writerow(row)
    return work, trace


def test_native_inventory_binds_original_outputs_and_all_logs(tmp_path: Path) -> None:
    work, trace = _native_task(tmp_path)
    (work / "staged-input").symlink_to(tmp_path.parent, target_is_directory=True)
    tasks = reference_trace_tasks(tmp_path, trace)
    inventory = reference_native_file_inventory(tmp_path, tasks)
    assert len(inventory) == 8
    assert all(
        relative.startswith("cache/rf-reference/work/ab/") for relative in inventory
    )
    assert any(relative.endswith("/.command.err") for relative in inventory)
    assert not any("staged-input" in relative for relative in inventory)
    assert tasks[0]["native_id"] == "30150000"
    original = dict(inventory)
    (work / "output/result.json").write_text('{"actual_exit":0}\n')
    assert reference_native_file_inventory(tmp_path, tasks) != original


@pytest.mark.parametrize(
    "change", ["parent_link", "foreign_work", "duplicate_task", "malformed"]
)
def test_native_trace_rejects_substituted_task_ownership(
    tmp_path: Path, change: str
) -> None:
    work, trace = _native_task(tmp_path)
    if change == "parent_link":
        parent = work.parent
        real_parent = parent.with_name("retained-original")
        parent.rename(real_parent)
        parent.symlink_to(real_parent, target_is_directory=True)
    elif change == "foreign_work":
        trace.write_text(trace.read_text().replace(str(work), str(tmp_path.parent)))
    elif change == "duplicate_task":
        trace.write_text(trace.read_text() + trace.read_text().splitlines()[1] + "\n")
    else:
        trace.write_text(trace.read_text().rstrip() + "\textra\n")
    with pytest.raises(ValueError):
        reference_trace_tasks(tmp_path, trace)


@pytest.mark.parametrize(
    "change", ["missing_log", "linked_log", "linked_output", "oversized"]
)
def test_native_inventory_refuses_missing_substituted_or_unbounded_bytes(
    tmp_path: Path, monkeypatch: MonkeyPatch, change: str
) -> None:
    work, trace = _native_task(tmp_path)
    tasks = reference_trace_tasks(tmp_path, trace)
    if change == "missing_log":
        (work / ".command.err").unlink()
    elif change == "linked_log":
        (work / ".command.err").unlink()
        (work / ".command.err").symlink_to(work / ".command.out")
    elif change == "linked_output":
        (work / "output/foreign").symlink_to(trace)
    else:
        monkeypatch.setattr(evidence_module, "_MAX_FILE_BYTES", 4)

        def forbidden_hash(path: Path) -> str:
            raise AssertionError(f"payload was hashed before size validation: {path}")

        monkeypatch.setattr(evidence_module, "sha256_file", forbidden_hash)
    with pytest.raises(ValueError, match="reference native"):
        reference_native_file_inventory(tmp_path, tasks)


def _staged_search_tasks(root: Path) -> tuple[tuple[dict[str, str], ...], Path]:
    cache = root / "cache/rf-reference/work"
    tasks = []
    partition = cache / "aa" / ("a" * 30)
    partition.mkdir(parents=True)
    tasks.append(
        {
            "process": "RF_REFERENCE_WORKFLOW:M6_PARTITION_DISCOVERY",
            "workdir": str(partition),
        }
    )
    planned_root = cache / "dd" / ("d" * 30) / "m6_batch_plan"
    planned_root.mkdir(parents=True)
    tasks.append(
        {
            "process": "RF_REFERENCE_WORKFLOW:M6_BUILD_SEARCH_BATCHES",
            "workdir": str(planned_root.parent),
        }
    )
    for provider, process, basename, prefix in (
        ("pdb", "M6_SEARCH_PDB", "m6_pdb_bundle", "bb"),
        ("foldseek", "M6_SEARCH_FOLDSEEK", "m6_foldseek_bundle", "cc"),
    ):
        for index in (1, 2):
            work = cache / prefix / (str(index) * 30)
            output = work / basename
            output.mkdir(parents=True)
            (output / "simulated.txt").write_text(f"SIMULATED {provider} {index}\n")
            tasks.append(
                {
                    "process": f"RF_REFERENCE_WORKFLOW:{process}",
                    "tag": f"m6-{provider}:{index:064x}",
                    "workdir": str(work),
                }
            )
            provider_root = (
                "pdb_sequence_batches"
                if provider == "pdb"
                else "prostt5_foldseek_batches"
            )
            planned = planned_root / provider_root / f"{index:064x}"
            planned.mkdir(parents=True)
            (work / "batch_task").mkdir()
            for filename in ("sequence_groups.jsonl", "task.json"):
                original = planned / filename
                original.write_text(f"SIMULATED {provider} {index} {filename}\\n")
                (work / "batch_task" / filename).symlink_to(original)
            parent = partition / f"{provider}-batch{index:02d}"
            parent.mkdir()
            (parent / basename).symlink_to(output, target_is_directory=True)
    generated = partition / "m6_discovery_partition"
    generated.mkdir()
    (generated / "simulated.txt").write_text("SIMULATED partition\n")
    for task in tasks:
        work = Path(task["workdir"])
        for name in evidence_module._TASK_LOGS:
            (work / name).write_text("0\n" if name == ".exitcode" else "SIMULATED\n")
    return tuple(tasks), partition


def test_complete_stages_bind_original_producers_and_reordering_changes_binding(
    tmp_path: Path,
) -> None:
    tasks, partition = _staged_search_tasks(tmp_path)
    first = reference_staged_search_inputs(tmp_path, tasks)
    assert len(first) == 12
    inventory = reference_native_file_inventory(tmp_path, tasks)
    assert len(inventory) == 55
    assert not (set(inventory) & set(first))
    assert sum(name.endswith("/simulated.txt") for name in inventory) == 5
    assert first == reference_staged_search_inputs(tmp_path, tuple(reversed(tasks)))
    links = tuple(partition / f"pdb-batch{index:02d}/m6_pdb_bundle" for index in (1, 2))
    targets = tuple(link.resolve(strict=True) for link in links)
    for link, target in zip(links, reversed(targets), strict=True):
        link.unlink()
        link.symlink_to(target, target_is_directory=True)
    changed = reference_staged_search_inputs(tmp_path, tasks)
    assert changed != first
    assert set(changed.values()) == set(first.values())


@pytest.mark.parametrize(
    "change",
    [
        "missing_link",
        "missing_parent",
        "duplicate_target",
        "foreign_target",
        "extra_contents",
        "parent_link",
        "producer_link",
        "index_gap",
        "not_link",
    ],
)
def test_indexed_stages_refuse_incomplete_or_substituted_inputs(
    tmp_path: Path, change: str
) -> None:
    tasks, partition = _staged_search_tasks(tmp_path)
    parent = partition / "pdb-batch01"
    link = parent / "m6_pdb_bundle"
    target = link.resolve(strict=True)
    if change == "missing_link":
        link.unlink()
    elif change == "missing_parent":
        parent.rename(tmp_path / "retained-parent")
    elif change in {"duplicate_target", "foreign_target", "not_link"}:
        link.unlink()
        if change == "not_link":
            link.mkdir()
        else:
            replacement = (partition / "pdb-batch02/m6_pdb_bundle").resolve(strict=True)
            if change == "foreign_target":
                replacement = tmp_path / "untraced-output"
                replacement.mkdir()
            link.symlink_to(replacement, target_is_directory=True)
    elif change == "extra_contents":
        (parent / "unexpected.txt").write_text("foreign\n")
    elif change == "parent_link":
        retained = tmp_path / "retained-parent"
        parent.rename(retained)
        parent.symlink_to(retained, target_is_directory=True)
    elif change == "producer_link":
        retained = tmp_path / "retained-producer"
        target.rename(retained)
        target.symlink_to(retained, target_is_directory=True)
    else:
        parent.rename(partition / "pdb-batch03")
    with pytest.raises(ValueError, match="reference"):
        reference_staged_search_inputs(tmp_path, tasks)


@pytest.mark.parametrize(
    "change", [None, "wrong_task", "mixed_tracks", "wrong_filename"]
)
def test_declared_catalogue_inputs_require_one_original_planned_task(
    tmp_path: Path, change: str | None
) -> None:
    cache = tmp_path / "cache/rf-reference/work"
    planner = cache / "ab" / ("c" * 30)
    importer = cache / "de" / ("f" * 30)
    source = planner / "reference_plan/bundle/production_plans"
    key = "1" * 64
    parent = importer / "catalogue_task"
    parent.mkdir(parents=True)
    for track, catalogue_key in (
        ("operational", key),
        ("leakage_controlled", key),
        ("operational", "2" * 64),
    ):
        original = source / track / "catalogue_tasks" / catalogue_key
        original.mkdir(parents=True)
        for filename in ("analysis_config.json", "catalogue.faa", "task.json"):
            (original / filename).write_text(
                f"SIMULATED {track} {catalogue_key} {filename}\n"
            )
            if track == "operational" and catalogue_key == key:
                (parent / filename).symlink_to(original / filename)
    tasks = (
        {"process": "RF_REFERENCE_WORKFLOW:RF_PLAN", "workdir": str(planner)},
        {
            "process": "RF_REFERENCE_WORKFLOW:M6_IMPORT_CATALOGUE",
            "tag": f"m6-import:{key}",
            "workdir": str(importer),
        },
    )
    if change is not None:
        link = parent / "task.json"
        link.unlink()
        track = "leakage_controlled" if change == "mixed_tracks" else "operational"
        catalogue_key = "2" * 64 if change == "wrong_task" else key
        filename = "catalogue.faa" if change == "wrong_filename" else "task.json"
        link.symlink_to(source / track / "catalogue_tasks" / catalogue_key / filename)
        with pytest.raises(ValueError, match="reference declared input"):
            reference_staged_search_inputs(tmp_path, tasks)
    else:
        assert len(reference_staged_search_inputs(tmp_path, tasks)) == 3


def test_declared_batch_inputs_refuse_a_different_original_batch(
    tmp_path: Path,
) -> None:
    tasks, _partition = _staged_search_tasks(tmp_path)
    searches = tuple(
        row for row in tasks if row["process"] == "RF_REFERENCE_WORKFLOW:M6_SEARCH_PDB"
    )
    first = Path(searches[0]["workdir"]) / "batch_task/task.json"
    second = Path(searches[1]["workdir"]) / "batch_task/task.json"
    first.unlink()
    first.symlink_to(second.resolve(strict=True))
    with pytest.raises(ValueError, match="another planned task"):
        reference_staged_search_inputs(tmp_path, tasks)


def _terminal_reference(root: Path, *, success: bool) -> Path:
    run = root / "runs/gtd-rf-reference-20260911T000000Z-111111111111-01234567"
    state = run / "state"
    state.mkdir(parents=True)
    for name, value in (("owner-id", "a" * 32), ("commit", "1" * 40)):
        (state / name).write_text(value + "\n")
    identity = {
        "schema_version": "1.0",
        "run_id": run.name,
        "owner_id": "a" * 32,
        "site_id": "raven",
        "profile": "rf-reference",
        "source_commit": "1" * 40,
        "controller_kind": "login_process",
        "started_at": "2026-09-11T00:00:00Z",
        "process": {
            "host": "raven03",
            "pid": 100,
            "start_ticks": "1000",
            "boot_id": "01234567-89ab-cdef-0123-456789abcdef",
        },
    }
    atomic_write_json(state / "controller.json", identity)
    atomic_write_json(
        state / "controller-result.json",
        {
            **identity,
            "completed_at": "2026-09-11T00:01:00Z",
            "standard_output": "logs/controller.log",
            "standard_error": "logs/controller.log",
            "application_log": "logs/rf-reference.log",
            "controller_state": "COMPLETED" if success else "FAILED",
            "exit_code": 0 if success else 1,
            "failure_class": "success" if success else "software_failure",
        },
    )
    atomic_write_json(
        run / "manifest.json",
        {
            "run_id": run.name,
            "profile": "rf-reference",
            "commit": "1" * 40,
            "site_id": "raven",
            "controller_kind": "login_process",
            "source_snapshot_status": "immutable",
        },
    )
    return run


def _freeze_synthetic_collection(run: Path) -> tuple[Path, Path]:
    # Deliberately not a scientific ReferenceRun: these tests exercise transport
    # ownership/byte checks only and cannot supply native acceptance evidence.
    work, first_trace = _native_task(run)
    qualification = first_trace.parents[1]
    native_files = reference_native_file_inventory(
        run, reference_trace_tasks(run, first_trace)
    )
    published = (
        run / "artifacts/rf-reference-results/reference_run/bundle/reference_run.json"
    )
    published.parent.mkdir(parents=True)
    atomic_write_json(published, {"simulation_only": True, "output_sha256": {}})
    copies = qualification / "rf-reference-inputs"
    copies.mkdir()
    input_copies = {}
    input_digests = {}
    for role, name in REFERENCE_INPUT_COPIES.items():
        path = copies / name
        path.write_text(f"synthetic original {role}\n")
        input_digests[role] = sha256_file(path)
        input_copies[path.relative_to(run).as_posix()] = {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    invariant = {
        "run_id": run.name,
        "profile": "rf-reference",
        "reference_scope": "rf-fixed-five-v1",
        "source_commit": "1" * 40,
        "controller_identity": json.loads((run / "state/controller.json").read_bytes()),
        "native_files": native_files,
        "staged_search_inputs": {},
        "reference_result_sha256": sha256_file(published),
        "input_copies": input_copies,
        "input_sha256": input_digests,
        "published_files": {
            published.relative_to(run).as_posix(): {
                "sha256": sha256_file(published),
                "size_bytes": published.stat().st_size,
            }
        },
    }
    first_sha = None
    for phase in ("first", "resume"):
        trace = qualification / f"rf-reference-{phase}-pipeline-info/trace.tsv"
        if phase == "resume":
            trace.parent.mkdir()
            trace.write_text(first_trace.read_text().replace("COMPLETED", "CACHED"))
        child = qualification / f"rf-reference-{phase}-child-outputs.json"
        resources = qualification / f"rf-reference-{phase}-resource-evidence.json"
        for path in (child, resources):
            atomic_write_json(path, {"simulation_only": True})
        record = {
            "schema_version": "1.0",
            "adapter_version": "rf-native-verification-v1",
            "phase": phase,
            "native_acceptance_claim": False,
            "benchmark_acceptance_claim": False,
            "human_approval_granted": False,
            "truth_compared": False,
            "invariant": invariant,
            "first_verification_sha256": first_sha,
            "trace_sha256": sha256_file(trace),
            "child_checkpoint_sha256": sha256_file(child),
            "resource_evidence_sha256": sha256_file(resources),
        }
        record["verification_id"] = content_id("rfnative_", record)
        path = qualification / f"rf-reference-{phase}-verification.json"
        atomic_write_json(path, record)
        first_sha = sha256_file(path)
    return work, qualification


def test_reference_collection_keeps_terminal_failure_diagnostic_only(
    tmp_path: Path,
) -> None:
    run = _terminal_reference(tmp_path, success=False)
    assert reference_collection_files(run) == ()
    terminal = run / "state/controller-result.json"
    raw = json.loads(terminal.read_bytes())
    raw.update(controller_state="COMPLETED", exit_code=0, failure_class="success")
    atomic_write_json(terminal, raw)
    with pytest.raises(ValueError, match="lacks first"):
        reference_collection_files(run)


@pytest.mark.parametrize(
    "change",
    [
        None,
        "native_output",
        "missing_log",
        "missing_resume",
        "foreign_profile",
        "input_copy",
    ],
)
def test_reference_collection_only_enumerates_frozen_owned_payloads(
    tmp_path: Path, change: str | None
) -> None:
    run = _terminal_reference(tmp_path, success=True)
    work, qualification = _freeze_synthetic_collection(run)
    if change == "native_output":
        (work / "output/result.json").write_text("changed\n")
    elif change == "missing_log":
        (work / ".command.err").unlink()
    elif change == "missing_resume":
        (qualification / "rf-reference-resume-verification.json").unlink()
    elif change == "foreign_profile":
        path = run / "manifest.json"
        raw = json.loads(path.read_bytes())
        raw["profile"] = "m6-operational"
        atomic_write_json(path, raw)
    elif change == "input_copy":
        (qualification / "rf-reference-inputs/phenix_manifest.json").write_text(
            "changed\n"
        )
    if change is not None:
        with pytest.raises(ValueError, match="reference"):
            reference_collection_files(run)
    else:
        unrelated = work.parent.parent / "unrelated-secret"
        unrelated.write_text("must remain outside the collection\n")
        files = reference_collection_files(run)
        assert len(files) == 18
        assert all("unrelated" not in name for name in files)
        assert (
            "artifacts/qualification/rf-reference-inputs/phenix_manifest.json" in files
        )
        assert any(name.endswith("/.command.err") for name in files)
