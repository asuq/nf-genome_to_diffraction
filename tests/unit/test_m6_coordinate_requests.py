"""Synthetic failed-run request conservation and immutable collection boundaries."""

import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
from dataclasses import replace
from pathlib import Path, PurePosixPath

import pytest

from genome_to_diffraction.benchmarks.m6_nextflow import (
    M6BundleManifest,
    M6CaseTask,
    M6CatalogueTask,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.cli import _build_parser
from genome_to_diffraction.hpc.m6_coordinate_requests import (
    CASES,
    COLLECTION,
    CORE_FILES,
    RUNNER,
    TRACE,
    extract_request_archive,
    freeze_request_inventory,
)
from genome_to_diffraction.hpc.models import LocalRunRecord, ValidationError
from tests.unit.test_hpc_client import (
    COMMIT,
    REPOSITORY,
    FakeTransport,
    _archive,
    _controller,
    _owned_terminal_files,
)
from tests.unit.test_m6_admission import _catalogue

RUN_ID = f"gtd-m6-native-control-20260912T120000Z-{COMMIT[:12]}-01234567"


def _write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("ascii") if isinstance(data, str) else data)


def _failed_coordinate_tree(
    run: Path, *, remote_root: PurePosixPath | None = None
) -> None:
    """Build two explicit synthetic cases, each with 93 retained model hits."""

    remote = remote_root or PurePosixPath(run)
    for name in CORE_FILES:
        _write(run / name, "{}\n")
    lock = hashlib.sha256(b"locked\n").hexdigest()
    atomic_write_json(
        run / "manifest.json",
        {
            "commit": COMMIT,
            "database_manifest_sha256": "c" * 64,
            "pixi_lock_sha256": lock,
        },
    )
    for name, value in {
        "owner-id": "1" * 32,
        "profile": "m6-native-control",
        "phase": "completed",
        "failure-class": "test_failure",
        "controller-kind": "slurm_job",
        "job-id": "42",
        "m6-execution-purpose": "native_control",
        "m6-track": "operational",
        "m6-runner-manifest-sha256": sha256_file(run / RUNNER),
    }.items():
        _write(run / "state" / name, value + "\n")
    rows: list[dict[str, str]] = []

    def task(process: str, tag: str, status: str = "COMPLETED") -> Path:
        index = len(rows) + 1
        short, suffix = f"{index:02x}", f"{index:030x}"
        relative = f"cache/m6-nextflow-operational/work/{short}/{suffix}"
        rows.append(
            {
                "task_id": str(index),
                "hash": f"{short}/{suffix[:6]}",
                "process": f"M6_VALIDATION_WORKFLOW:{process}",
                "tag": tag,
                "status": status,
                "exit": "0" if status == "COMPLETED" else "1",
                "attempt": "1",
                "workdir": str(remote / relative),
            }
        )
        return run / relative

    plan = task("M6_PLAN_TRACK", "m6-plan:operational") / "m6_track_plan"
    case_rows, catalogue_rows = [], []
    for letter, case_id in zip(("a", "b"), CASES, strict=True):
        key = letter * 64
        case = M6CaseTask(
            schema_version="1.0",
            case_id=case_id,
            track="operational",
            catalogue_key=key,
            reflections_sha256="f" * 64,
            analysis_config_sha256="6" * 64,
            model_policy_sha256="9" * 64,
        )
        case_path = plan / "case_tasks" / case_id / "task.json"
        atomic_write_json(case_path, case.model_dump(mode="json"))
        case_rows.append((case_id, key, f"case_tasks/{case_id}"))
        catalogue_rows.append((key, "8" * 64, f"catalogue_tasks/{key}"))
        catalogue_work = task("M6_IMPORT_CATALOGUE", f"m6-import:{key}")
        policy_work = task("M6_APPLY_POLICY", f"m6-policy:{case_id}")
        catalogue, policy, _ = _catalogue(run / "fixture-build" / case_id)
        catalogue_work.mkdir(parents=True)
        catalogue.rename(catalogue_work / "m6_catalogue_bundle")
        policy_work.mkdir(parents=True)
        policy.rename(policy_work / "m6_policy_bundle")
        catalogue = catalogue_work / "m6_catalogue_bundle"
        policy = policy_work / "m6_policy_bundle"
        cat_task = M6CatalogueTask(
            schema_version="1.0",
            catalogue_key=key,
            catalogue_sha256="7" * 64,
            analysis_config_sha256=case.analysis_config_sha256,
            software_lock_sha256=lock,
            import_cache_key="8" * 64,
        )
        atomic_write_json(
            catalogue / "catalogue_task.json", cat_task.model_dump(mode="json")
        )
        atomic_write_json(
            catalogue / "catalogue/catalogue_import_manifest.json", {"synthetic": True}
        )
        atomic_write_json(
            catalogue / "bundle_manifest.json",
            M6BundleManifest(
                schema_version="1.0",
                adapter_version="m6-nextflow-catalogue-v1",
                task_kind="catalogue_import",
                task_id=key,
                input_sha256={
                    "task": sha256_file(catalogue / "catalogue_task.json"),
                    "software_lock": lock,
                },
                output_sha256={
                    name: sha256_file(catalogue / relative)
                    for name, relative in {
                        "sequence_groups": "catalogue/sequence_groups.jsonl",
                        "source_records": "catalogue/source_records.jsonl",
                        "import_manifest": "catalogue/catalogue_import_manifest.json",
                    }.items()
                },
            ).model_dump(mode="json"),
        )
        partition = (
            task("M6_PARTITION_DISCOVERY", f"m6-partition:{key}")
            / "m6_discovery_partition"
        )
        for provider in ("pdb_bundle", "foldseek_bundle"):
            atomic_write_json(
                partition / provider / "bundle_manifest.json",
                M6BundleManifest(
                    schema_version="1.0",
                    adapter_version="m6-nextflow-discovery-partition-v1",
                    task_kind=provider,
                    task_id=key,
                    input_sha256={
                        "catalogue_bundle": sha256_file(
                            catalogue / "bundle_manifest.json"
                        )
                    },
                    output_sha256={},
                ).model_dump(mode="json"),
            )
        shutil.copyfile(case_path, policy / "case_task.json")
        atomic_write_json(
            policy / "bundle_manifest.json",
            M6BundleManifest(
                schema_version="1.0",
                adapter_version="m6-nextflow-model-policy-v2",
                task_kind="trusted_model_policy",
                task_id=case_id,
                input_sha256={
                    "case_task": sha256_file(case_path),
                    "database_manifest": "c" * 64,
                    "catalogue_bundle": sha256_file(catalogue / "bundle_manifest.json"),
                    **{
                        provider: sha256_file(
                            partition / provider / "bundle_manifest.json"
                        )
                        for provider in ("pdb_bundle", "foldseek_bundle")
                    },
                },
                output_sha256={
                    "accepted_hits": sha256_file(
                        policy / "policy/accepted_structural_hits.jsonl"
                    )
                },
            ).model_dump(mode="json"),
        )
        failed = task(
            "M6_STAGE_COORDINATES", f"m6-coordinate-stage:{case_id}", "FAILED"
        )
        _write(
            failed / ".command.sh",
            "#!/bin/bash\n"
            + "genome-to-diffraction --no-progress --log-format json "
            + "benchmark stage-m6-coordinates "
            + f"--task '{remote / case_path.parent.relative_to(run)}' "
            + f"--catalogue-bundle '{remote / catalogue.relative_to(run)}' "
            + f"--policy-bundle '{remote / policy.relative_to(run)}' "
            + "--database-manifest '/approved/database.json' "
            + "--outdir m6_coordinate_stage\n",
        )
    for name, header, values in (
        ("case_tasks", ("case_id", "catalogue_key", "task_directory"), case_rows),
        (
            "catalogue_tasks",
            ("catalogue_key", "import_cache_key", "task_directory"),
            catalogue_rows,
        ),
    ):
        with (plan / f"{name}.tsv").open("w") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(header)
            writer.writerows(values)
    atomic_write_json(
        plan / "track_plan.json",
        {
            "schema_version": "1.0",
            "adapter_version": "m6-native-control-plan-v1",
            "execution_purpose": "native_control",
            "track": "operational",
            "benchmark_acceptance_claim": False,
            "case_ids": list(CASES),
            "case_task_count": 2,
            "catalogue_task_count": 2,
            "input_sha256": {
                "runner_manifest": sha256_file(run / RUNNER),
                "database_manifest": "c" * 64,
                "software_lock": lock,
            },
            "outputs": {
                name: sha256_file(plan / f"{name}.tsv")
                for name in ("case_tasks", "catalogue_tasks")
            },
        },
    )
    with (run / TRACE).open("w") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _export(
    run: Path, *, file_limit: int = 128 * 1024 * 1024
) -> subprocess.CompletedProcess[bytes]:
    """Execute the actual dispatcher's read-only Python boundary glue locally."""

    source = (REPOSITORY / "bootstrap/nf-gtd-hpc-remote").read_text()
    body = (
        source.split("collect_coordinate_requests() {", 1)[1]
        .split("<<'PY'\n", 1)[1]
        .split("\nPY\n", 1)[0]
    )
    return subprocess.run(
        [sys.executable, "-I", "-", str(run), str(file_limit), str(512 * 1024 * 1024)],
        input=body.encode("ascii"),
        capture_output=True,
        check=False,
    )


def _snapshot(tmp_path: Path) -> tuple[Path, Path, Path]:
    run = tmp_path / RUN_ID
    _failed_coordinate_tree(run)
    result = _export(run)
    assert result.returncode == 0, result.stderr.decode()
    archive = tmp_path / "requests.tar.gz"
    archive.write_bytes(result.stdout)
    prior = tmp_path / "prior"
    for name in ("manifest.json", "state/job-result.json", TRACE, RUNNER):
        _write(prior / name, (run / name).read_bytes())
    return run, archive, prior


def test_complete_request_export_preserves_both_cases_and_more_than_25_hits(
    tmp_path: Path,
) -> None:
    run, archive, prior = _snapshot(tmp_path)
    before = {
        str(p.relative_to(run)): sha256_file(p) for p in run.rglob("*") if p.is_file()
    }
    root = tmp_path / "snapshot"
    collection = extract_request_archive(archive, root)
    result = freeze_request_inventory(
        root,
        collection=collection,
        prior=prior,
        remote_root=PurePosixPath(run),
        run_id=RUN_ID,
        source_commit=COMMIT,
    )
    assert result["pdb_ids"] == ["1ABC"]
    assert result["distinct_pdb_count"] == 1
    assert result["network_acquisition_performed"] is False
    cases = result["cases"]
    assert isinstance(cases, dict)
    for case in cases.values():
        assert case["accepted_hit_count"] == case["requested_mapping_count"] == 93
        assert case["eligible_group_count"] == 31
    assert before == {
        str(p.relative_to(run)): sha256_file(p) for p in run.rglob("*") if p.is_file()
    }
    assert not any("candidate_ranking" in name for name in collection.files)


@pytest.mark.parametrize(
    "corruption", ["path", "symlink", "missing_case", "duplicate_task", "size"]
)
def test_remote_request_export_rejects_unsafe_or_incomplete_producers(
    tmp_path: Path, corruption: str
) -> None:
    run = tmp_path / RUN_ID
    _failed_coordinate_tree(run)
    trace = run / TRACE
    lines = trace.read_text().splitlines()
    if corruption == "path":
        trace.write_text(
            "\n".join(lines).replace(str(run / "cache"), str(tmp_path / "cache")) + "\n"
        )
    elif corruption == "missing_case":
        trace.write_text(
            "\n".join(line for line in lines if "m6-policy:M6C025" not in line) + "\n"
        )
    elif corruption == "duplicate_task":
        trace.write_text("\n".join([*lines, lines[1]]) + "\n")
    elif corruption == "symlink":
        source = next(run.glob("cache/**/m6_policy_bundle/policy"))
        retained = tmp_path / "retained"
        source.rename(retained)
        source.symlink_to(retained, target_is_directory=True)
    result = _export(run, file_limit=16 if corruption == "size" else 128 * 1024 * 1024)
    assert result.returncode != 0
    assert not result.stdout


@pytest.mark.parametrize(
    "corruption",
    ["checksum", "case_join", "command_join", "search_join", "prior", "extra"],
)
def test_local_request_freeze_rejects_changed_producer_bindings(
    tmp_path: Path, corruption: str
) -> None:
    run, archive, prior = _snapshot(tmp_path)
    root = tmp_path / "snapshot"
    collection = extract_request_archive(archive, root)
    if corruption == "prior":
        (prior / TRACE).write_text("changed\n")
    elif corruption == "extra":
        collection.files["unexpected.json"] = next(iter(collection.files.values()))
    elif corruption == "command_join":
        path = next(root.glob("cache/**/.command.sh"))
        path.write_text(
            path.read_text().replace(
                "--outdir m6_coordinate_stage", "--outdir elsewhere"
            )
        )
    elif corruption == "checksum":
        next(root.glob("cache/**/accepted_structural_hits.jsonl")).write_text("{}\n")
    else:
        path = next(root.glob("cache/**/m6_policy_bundle/bundle_manifest.json"))
        value = json.loads(path.read_text())
        if corruption == "case_join":
            value["task_id"] = "M6C999"
        else:
            value["input_sha256"]["pdb_bundle"] = "0" * 64
        atomic_write_json(path, value)
    with pytest.raises((ValidationError, PublicControlError)):
        freeze_request_inventory(
            root,
            collection=collection,
            prior=prior,
            remote_root=PurePosixPath(run),
            run_id=RUN_ID,
            source_commit=COMMIT,
        )
    assert not (root / "request_inventory.json").exists()


@pytest.mark.parametrize(
    "member_name", ["../escape", "/absolute", "./noncanonical", "duplicate"]
)
def test_request_archive_rejects_unsafe_names_and_duplicates(
    tmp_path: Path, member_name: str
) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for _ in range(2):
            member = tarfile.TarInfo(member_name)
            member.size = 1
            handle.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ValidationError, match="unsafe"):
        extract_request_archive(archive, tmp_path / "out")


def test_coordinate_collect_option_has_no_path_url_or_scientific_override() -> None:
    parser = _build_parser()
    args = parser.parse_args(["collect", "--run-id", RUN_ID, "--coordinate-requests"])
    assert args.coordinate_requests is True
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "collect",
                "--run-id",
                RUN_ID,
                "--coordinate-requests",
                "--url",
                "https://example.invalid",
            ]
        )


@pytest.mark.parametrize("corruption", ["checksum", "missing", "extra", "symlink"])
def test_request_archive_verifies_complete_payload_before_derivation(
    tmp_path: Path,
    corruption: str,
) -> None:
    _, original, _ = _snapshot(tmp_path)
    with tarfile.open(original, "r:gz") as handle:
        payloads = {}
        for member in handle:
            source = handle.extractfile(member)
            assert source is not None
            payloads[member.name] = source.read()
    if corruption == "checksum":
        payloads[TRACE] += b"changed\n"
    elif corruption == "missing":
        payloads.pop(RUNNER)
    elif corruption == "extra":
        payloads["extra.json"] = b"{}\n"
    if corruption == "symlink":
        with tarfile.open(original, "w:gz") as handle:
            member = tarfile.TarInfo(COLLECTION)
            member.type = tarfile.SYMTYPE
            member.linkname = "/outside"
            handle.addfile(member)
    else:
        original.write_bytes(_archive(payloads))
    with pytest.raises(ValidationError):
        extract_request_archive(original, tmp_path / "rejected")
    assert not (tmp_path / "rejected/request_inventory.json").exists()


def test_controller_publishes_separate_snapshot_without_overwriting_prior(
    tmp_path: Path,
) -> None:
    transport = FakeTransport()
    controller = _controller(tmp_path, transport)
    record = LocalRunRecord(
        run_id=RUN_ID,
        site_id="marmic",
        commit=COMMIT,
        owner_id="1" * 32,
        profile="m6-native-control",
        iteration=1,
        parent_run_id=None,
    )
    record.write(controller.config.local_state_root)
    for relative in (
        "benchmarks/m6_nextflow.py",
        "structure_search/pdb_coordinates.py",
    ):
        _write(
            tmp_path / "src/genome_to_diffraction" / relative,
            (REPOSITORY / "src/genome_to_diffraction" / relative).read_bytes(),
        )
    run = tmp_path / "remote" / RUN_ID
    _failed_coordinate_tree(run)
    terminal = _owned_terminal_files(controller, RUN_ID)
    manifest = json.loads(terminal["manifest.json"])
    manifest["database_manifest_sha256"] = "c" * 64
    terminal["manifest.json"] = (json.dumps(manifest) + "\n").encode()
    for name, data in terminal.items():
        _write(run / name, data)
    # The raw exporter uses real local paths; configured dispatcher identity is
    # the synthetic run's parent, with no real transport involved.
    controller.config = replace(
        controller.config,
        remote_dispatcher=str(run.parent.parent / "_tooling/nf-gtd-hpc-remote"),
    )
    run_with_layout = run.parent.parent / "runs" / RUN_ID
    run.parent.rename(run.parent.parent / "runs")
    for path in (
        run_with_layout / TRACE,
        *run_with_layout.glob("cache/**/.command.sh"),
    ):
        path.write_text(path.read_text().replace(str(run), str(run_with_layout)))
    prior = controller.config.local_state_root / RUN_ID / "collected"
    for name in ("manifest.json", "state/job-result.json", TRACE, RUNNER):
        _write(prior / name, (run_with_layout / name).read_bytes())
    before = {
        str(p.relative_to(prior)): sha256_file(p)
        for p in prior.rglob("*")
        if p.is_file()
    }
    result = _export(run_with_layout)
    assert result.returncode == 0, result.stderr.decode()
    transport.archive = result.stdout
    collected = controller.collect_coordinate_requests(RUN_ID)
    assert collected["distinct_pdb_count"] == 1
    assert collected["collection_kind"] == "coordinate_requests"
    assert before == {
        str(p.relative_to(prior)): sha256_file(p)
        for p in prior.rglob("*")
        if p.is_file()
    }
    calls = len(transport.calls)
    with pytest.raises(ValidationError, match="already exists"):
        controller.collect_coordinate_requests(RUN_ID)
    assert len(transport.calls) == calls
