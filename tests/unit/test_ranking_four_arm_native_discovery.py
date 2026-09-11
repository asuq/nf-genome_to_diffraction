"""Whole original metadata/science replay; simulated searches, not native proof."""

import csv
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from genome_to_diffraction.benchmarks import m6_nextflow
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.rf_reference_evidence import REFERENCE_INPUT_COPIES
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    StructuralSearchResult,
)
from tests.fixtures import ranking_four_arm_native as native
from tests.fixtures.ranking_four_arm_aggregate import (
    ReferenceRunInputs,
    build_reference_run,
)
from tests.fixtures.ranking_four_arm_context import (
    ReferencePlanContext,
    ReferencePreparedContext,
)
from tests.fixtures.ranking_four_arm_native_discovery import verify_reference_discovery
from tests.fixtures.ranking_four_arm_plan import (
    ReferencePlanInputs,
    plan_reference_nextflow,
    validate_reference_plan,
)
from tests.fixtures.ranking_four_arm_prepared import (
    ReferencePreparedInputs,
    bind_reference_prepared_case,
)
from tests.unit.test_m6_benchmark import ROOT
from tests.unit.test_ranking_four_arm_native import _work
from tests.unit.test_ranking_four_arm_prepared import _inputs


def _simulated_search(request: object, *, provider: str) -> SimpleNamespace:
    assert isinstance(
        request,
        (
            m6_nextflow.PdbSequenceSearchRequest,
            m6_nextflow.ProstT5FoldseekSearchRequest,
        ),
    )
    root = request.output_directory
    (root / "raw").mkdir(parents=True)
    raw = root / "raw/results.tsv"
    raw.write_text("")
    log = root / "raw/commands.log"
    log.write_text("SIMULATED external search; no tool executed\n")
    groups = [
        SequenceGroupRecord.model_validate_json(line)
        for line in request.sequence_groups_jsonl.read_text().splitlines()
    ]
    records = [
        StructuralSearchResult(
            schema_version="1.0",
            search_id=content_id(
                "simulated_", {"provider": provider, "group": group.sequence_group_id}
            ),
            sequence_group_id=group.sequence_group_id,
            provider=provider,
            database_id="simulated",
            tool="simulated",
            tool_version="1",
            adapter_version="simulated",
            cache_key="a" * 64,
            execution_status="completed_no_hit",
            scientific_status="no_hit",
            hit_count=0,
            raw_result_pointer="raw/results.tsv",
            raw_result_sha256=sha256_file(raw),
            command_log_pointer="raw/commands.log",
            command_log_sha256=sha256_file(log),
        )
        for group in groups
    ]
    results = root / "search_results.jsonl"
    results.write_text("".join(f"{canonical_json_text(row)}\n" for row in records))
    hits = root / "structural_hits.jsonl"
    hits.write_text("")
    manifest = root / "search_manifest.json"
    atomic_write_json(manifest, {"simulation_only": True, "query_count": len(groups)})
    return SimpleNamespace(
        results_jsonl=results, hits_jsonl=hits, search_manifest=manifest
    )


def _complete_original_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[
    Path,
    dict[str, Path],
    tuple[dict[str, str], ...],
    ReferencePlanContext,
    tuple[ReferencePreparedContext, ...],
]:
    project = tmp_path / "project"
    seed_root = project / "simulated-external-inputs"
    seed_root.mkdir(parents=True)
    seed = _inputs(seed_root, monkeypatch, small=True, no_hits=True)
    run = project / "runs/simulated-reference"
    qualification = run / "artifacts/qualification"
    qualification.mkdir(parents=True)
    source = project / "source"
    source.mkdir()
    paths = {
        "runner_manifest": seed.plan_inputs.runner_root / "runner_manifest.json",
        "database_manifest": seed.plan_inputs.database_manifest,
    }
    for role, original in (
        ("software_lock", seed.plan_inputs.software_lock),
        ("phenix_manifest", seed.phenix_manifest),
        ("protocol", ROOT / "benchmarks/m6/protocol.yaml"),
        ("execution_policy", ROOT / "benchmarks/m6/execution-nextflow-raven-v2.yaml"),
    ):
        paths[role] = source / original.name
        shutil.copy2(original, paths[role])
    for role in ("controller_identity", "run_manifest", "phenix_verification_log"):
        paths[role] = qualification / f"simulated-{role}.json"
        atomic_write_json(paths[role], {"simulation_only": True, "role": role})
    assert set(paths) == set(REFERENCE_INPUT_COPIES)
    tasks = []

    def output(process: str, tag: str, relative: str, *, cpus: int = 2) -> Path:
        index = len(tasks) + 1
        work = _work(run, index)
        tasks.append(
            {
                "task_id": str(index),
                "hash": work.relative_to(run / "cache/rf-reference/work").as_posix(),
                "native_id": str(30151000 + index),
                "process": f"RF_REFERENCE_WORKFLOW:{process}",
                "tag": tag,
                "status": "COMPLETED",
                "exit": "0",
                "workdir": str(work),
                "cpus": str(cpus),
                "memory": "2 GB",
                "time": "1h",
                "start": "2026-09-11 01:00:00.000",
                "complete": "2026-09-11 01:00:01.000",
                "peak_rss": "1 MB",
                "%cpu": "100.0%",
            }
        )
        for name in (
            ".command.sh",
            ".command.run",
            ".command.out",
            ".command.err",
            ".command.log",
            ".command.trace",
        ):
            (work / name).write_text("SIMULATED task log\n")
        (work / ".exitcode").write_text("0\n")
        return work / relative

    plan_root = output("RF_PLAN", "rf-plan:fixed-five", "reference_plan")
    plan_inputs = ReferencePlanInputs(
        runner_root=seed.plan_inputs.runner_root,
        database_manifest=paths["database_manifest"],
        software_lock=paths["software_lock"],
    )
    plan_path = plan_reference_nextflow(plan_inputs, plan_root / "bundle")
    plan = validate_reference_plan(plan_path, plan_inputs)
    context = ReferencePlanContext(**plan_inputs.__dict__, plan_path=plan_path)
    atomic_write_json(plan_root / "context.json", context.model_dump(mode="json"))
    catalogues = {}
    for row in plan.catalogues:
        catalogue_output = output(
            "M6_IMPORT_CATALOGUE",
            f"m6-import:{row.task.catalogue_key}",
            "m6_catalogue_bundle",
        )
        staged_catalogue = catalogue_output.parent / "catalogue_task"
        staged_catalogue.mkdir()
        for filename in ("analysis_config.json", "catalogue.faa", "task.json"):
            (staged_catalogue / filename).symlink_to(
                plan_path.parent / row.task_directory / filename
            )
        catalogues[row.task.catalogue_key] = m6_nextflow.run_m6_catalogue_task(
            staged_catalogue,
            paths["software_lock"],
            catalogue_output,
        )
    batch_plan = m6_nextflow.build_m6_search_batches(
        tuple(catalogues.values()),
        paths["database_manifest"],
        paths["execution_policy"],
        paths["software_lock"],
        output("M6_BUILD_SEARCH_BATCHES", "m6-build-search-batches", "m6_batch_plan"),
    )
    monkeypatch.setattr(
        m6_nextflow,
        "search_pdb_sequences",
        lambda request: _simulated_search(request, provider="pdb_sequence_mmseqs"),
    )
    monkeypatch.setattr(
        m6_nextflow,
        "search_prostt5_foldseek",
        lambda request: _simulated_search(request, provider="foldseek_prostt5_pdb"),
    )
    searches = {}
    for provider, process, prefix, directory, execute in (
        (
            "pdb_sequence",
            "M6_SEARCH_PDB",
            "m6-pdb",
            "m6_pdb_bundle",
            m6_nextflow.run_m6_pdb_search_task,
        ),
        (
            "prostt5_foldseek",
            "M6_SEARCH_FOLDSEEK",
            "m6-foldseek",
            "m6_foldseek_bundle",
            m6_nextflow.run_m6_foldseek_search_task,
        ),
    ):
        bundles = []
        for planned in sorted((batch_plan / f"{provider}_batches").iterdir()):
            task = m6_nextflow.M6SearchBatchTask.model_validate_json(
                (planned / "task.json").read_bytes()
            )
            batch_output = output(
                process, f"{prefix}:{task.batch_id}", directory, cpus=task.threads
            )
            staged_batch = batch_output.parent / "batch_task"
            staged_batch.mkdir()
            for filename in ("sequence_groups.jsonl", "task.json"):
                (staged_batch / filename).symlink_to(planned / filename)
            bundles.append(
                execute(
                    staged_batch,
                    paths["database_manifest"],
                    paths["execution_policy"],
                    paths["software_lock"],
                    batch_output,
                    threads=task.threads,
                )
            )
        searches[provider] = tuple(bundles)
    partitions = {}
    for key, catalogue in catalogues.items():
        partition_output = output(
            "M6_PARTITION_DISCOVERY", f"m6-partition:{key}", "m6_discovery_partition"
        )
        staged = {}
        for provider, prefix in (
            ("pdb_sequence", "pdb"),
            ("prostt5_foldseek", "foldseek"),
        ):
            links = []
            for index, bundle in enumerate(searches[provider], start=1):
                parent = partition_output.parent / f"{prefix}-batch{index:02d}"
                parent.mkdir()
                link = parent / bundle.name
                link.symlink_to(bundle, target_is_directory=True)
                links.append(link)
            staged[provider] = tuple(links)
        partitions[key] = m6_nextflow.partition_m6_discovery_task(
            catalogue,
            batch_plan,
            staged["pdb_sequence"],
            staged["prostt5_foldseek"],
            partition_output,
        )
    contexts = []
    context_paths = []
    for row in plan.cases:
        case_id, key = row.task.case_id, row.task.catalogue_key
        case_task = plan_path.parent / row.task_directory
        preflight = m6_nextflow.run_m6_preflight_task(
            case_task,
            paths["phenix_manifest"],
            output(
                "M6_PREFLIGHT_CASE", f"m6-preflight:{case_id}", "m6_preflight_bundle"
            ),
        )
        assert (
            json.loads((preflight / "bundle_manifest.json").read_bytes())[
                "early_outcome"
            ]
            is None
        )
        policy = m6_nextflow.run_m6_model_policy_task(
            case_task,
            catalogues[key],
            partitions[key] / "pdb_bundle",
            partitions[key] / "foldseek_bundle",
            paths["protocol"],
            paths["database_manifest"],
            output("M6_APPLY_POLICY", f"m6-policy:{case_id}", "m6_policy_bundle"),
        )
        stage = m6_nextflow.run_m6_coordinate_stage_task(
            case_task,
            catalogues[key],
            policy,
            paths["database_manifest"],
            output(
                "M6_STAGE_COORDINATES",
                f"m6-coordinate-stage:{case_id}",
                "m6_coordinate_stage",
                cpus=1,
            ),
        )
        case = m6_nextflow.run_m6_prepare_case_task(
            case_task,
            preflight,
            catalogues[key],
            policy,
            stage,
            output("M6_PREPARE_ACTIVE_CASE", f"m6-case:{case_id}", "m6_case_bundle"),
        )
        inputs = ReferencePreparedInputs(
            plan_path,
            plan_inputs,
            case_id,
            catalogues[key],
            case,
            stage,
            paths["phenix_manifest"],
        )
        prepared_root = output(
            "RF_PREPARE", f"rf-prepare:{case_id}", "reference_prepared"
        )
        prepared_path = bind_reference_prepared_case(inputs, prepared_root / "bundle")
        prepared_context = ReferencePreparedContext(
            plan=context,
            case_id=case_id,
            catalogue_bundle=catalogues[key],
            prepared_case=case,
            coordinate_stage=stage,
            phenix_manifest=paths["phenix_manifest"],
            prepared_path=prepared_path,
        )
        context_path = prepared_root / "context.json"
        atomic_write_json(context_path, prepared_context.model_dump(mode="json"))
        contexts.append(prepared_context)
        context_paths.append(context_path)
    result_root = output(
        "RF_AGGREGATE", "rf-aggregate:fixed-five", "reference_run/bundle"
    )
    build_reference_run(
        ReferenceRunInputs(plan_root / "context.json", tuple(context_paths), ()),
        result_root,
    )
    shutil.copytree(
        result_root, run / "artifacts/rf-reference-results/reference_run/bundle"
    )
    for phase in ("first", "resume"):
        trace = qualification / f"rf-reference-{phase}-pipeline-info/trace.tsv"
        trace.parent.mkdir()
        with trace.open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(tasks[0]), delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(
                [
                    {**row, "status": "CACHED"} if phase == "resume" else row
                    for row in tasks
                ]
            )
    return run, paths, tuple(tasks), context, tuple(contexts)


def test_complete_original_graph_rejects_omitted_search_and_replays_all_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, paths, tasks, plan, prepared = _complete_original_graph(tmp_path, monkeypatch)
    evidence = verify_reference_discovery(run, paths, tasks, plan, prepared, ())
    assert len(evidence) >= 3
    omitted = tuple(
        row for row in tasks if not row["process"].endswith(":M6_SEARCH_FOLDSEEK")
    )
    with pytest.raises(ValueError, match="omits M6_SEARCH_FOLDSEEK"):
        verify_reference_discovery(run, paths, omitted, plan, prepared, ())
    # Only OS/live-controller binding is simulated. Both complete science passes,
    # task/receipt joins, metadata, resource reader and child checkpoint are real.
    monkeypatch.setattr(
        native, "_bind_run", lambda _run: ({"simulation_only": True}, paths)
    )
    first = native.verify_native_reference(run, phase="first", first_sha256=None)
    baseline = sha256_file(first)
    with pytest.raises(ValueError, match="externally frozen"):
        native.verify_native_reference(run, phase="resume", first_sha256="0" * 64)
    resume = native.verify_native_reference(run, phase="resume", first_sha256=baseline)
    first_record, resume_record = (
        json.loads(first.read_bytes()),
        json.loads(resume.read_bytes()),
    )
    assert first_record["invariant"] == resume_record["invariant"]
    assert first_record["invariant"]["discovery_provenance"] == evidence
    assert first_record["invariant"]["staged_search_inputs"]
    assert first_record["invariant"]["native_commands"] == []
    assert all(
        first_record[key] is False
        for key in (
            "native_acceptance_claim",
            "benchmark_acceptance_claim",
            "human_approval_granted",
            "truth_compared",
        )
    )
    assert sha256_file(first) == baseline
    assert not list((run / "artifacts/qualification").glob("rf-reference-metadata-*"))
