"""Authenticate the complete original RF task and search-batch universe.

Inputs are already scientifically validated original contexts and an owned native
trace. Reuse the unchanged production metadata batching/partitioning functions to
rederive the complete query universe and catalogue joins, byte for byte. This
does not run search, model preparation, Phenix, ranking or any scheduler. Only
temporary metadata is written; original task files are never modified.

Every expected process/tag and context output must have exactly one original
trace task. Search receipts bind all planned queries, resources, inputs and raw
outputs; each case's original policy must consume the revalidated partitions.
Missing, extra, substituted or changed evidence raises ValueError. Returned
hashes describe provenance only, not native/scientific acceptance or truth.
Python 3.14 and the immutable source/runtime of the parent verifier are required.
There is no cache or compatibility path. Tests use simulated external responses.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from tests.fixtures.ranking_four_arm_context import (
    ReferenceIdentityContext,
    ReferencePlanContext,
    ReferencePreparedContext,
)
from tests.fixtures.ranking_four_arm_plan import ReferenceTaskPlan, _inventory
from tests.fixtures.ranking_four_arm_prepared import _bundle

from genome_to_diffraction.benchmarks.m6_nextflow import (
    _FOLDSEEK_ADAPTER,
    _PDB_ADAPTER,
    M6BundleManifest,
    M6SearchBatchTask,
    build_m6_search_batches,
    partition_m6_discovery_task,
)
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.hpc.rf_reference_evidence import (
    _owned_path,
    reference_owned_regular_file,
)
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    StructuralSearchResult,
)
from genome_to_diffraction.structure_search.pdb_sequence import (
    _PROVIDER as _PDB_PROVIDER,
)
from genome_to_diffraction.structure_search.prostt5_foldseek import (
    _PROVIDER as _FOLDSEEK_PROVIDER,
)


def _same_tree(run: Path, original: Path, expected: Path) -> None:
    _owned_path(run, original, directory=True)
    if _inventory(original, None) != _inventory(expected, None):
        raise ValueError(
            "reference original metadata differs from complete rederivation"
        )


def _search_bundle(
    run: Path, original: Path, planned: Path, paths: dict[str, Path]
) -> M6SearchBatchTask:
    task_path = reference_owned_regular_file(run, original / "batch_task.json")
    if task_path.read_bytes() != (planned / "task.json").read_bytes():
        raise ValueError("reference native search differs from its complete batch plan")
    task = M6SearchBatchTask.model_validate_json(task_path.read_bytes())
    _bundle(
        original,
        adapter=_PDB_ADAPTER if task.provider == "pdb_sequence" else _FOLDSEEK_ADAPTER,
        kind="pdb_sequence_search"
        if task.provider == "pdb_sequence"
        else "prostt5_foldseek_search",
        task_id=task.search_cache_key,
        inputs={
            "batch_task": planned / "task.json",
            "sequence_groups": planned / "sequence_groups.jsonl",
            "database_manifest": paths["database_manifest"],
            "execution_policy": paths["execution_policy"],
            "software_lock": paths["software_lock"],
        },
        outputs={
            "search_results": original / "search/search_results.jsonl",
            "structural_hits": original / "search/structural_hits.jsonl",
            "search_manifest": original / "search/search_manifest.json",
        },
    )
    groups = [
        SequenceGroupRecord.model_validate_json(line).sequence_group_id
        for line in (planned / "sequence_groups.jsonl").read_text().splitlines()
    ]
    results = [
        StructuralSearchResult.model_validate_json(line)
        for line in (original / "search/search_results.jsonl").read_text().splitlines()
    ]
    provider = _PDB_PROVIDER if task.provider == "pdb_sequence" else _FOLDSEEK_PROVIDER
    if sorted(record.sequence_group_id for record in results) != sorted(groups) or any(
        record.provider != provider for record in results
    ):
        raise ValueError(
            "reference native search lost, duplicated or substituted queries"
        )
    for record in results:
        for relative, digest in (
            (record.raw_result_pointer, record.raw_result_sha256),
            (record.command_log_pointer, record.command_log_sha256),
        ):
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError(
                    "reference native search raw pointer escapes its bundle"
                )
            raw = reference_owned_regular_file(run, original / "search" / relative)
            if sha256_file(raw) != digest:
                raise ValueError("reference native search raw bytes changed")
    return task


def verify_reference_discovery(
    run: Path,
    paths: dict[str, Path],
    tasks: tuple[dict[str, str], ...],
    plan_context: ReferencePlanContext,
    prepared: tuple[ReferencePreparedContext, ...],
    identities: tuple[ReferenceIdentityContext, ...],
) -> dict[str, str]:
    """Join every original task, rederive batches/partitions and bind policies."""

    indexed = {(row["process"].rsplit(":", 1)[-1], row["tag"]): row for row in tasks}
    if len(indexed) != len(tasks):
        raise ValueError("reference native trace duplicates a process/tag")
    # The caller separately authenticates this entire receipt-to-command union.
    expected = {
        key for key in indexed if key[0] in {"RF_FIRST_COPY", "RF_COPY", "RF_REFINE"}
    }

    def task_output(process: str, tag: str, relative: str) -> Path:
        key = (process, tag)
        if key not in indexed:
            raise ValueError(f"reference native trace omits {process}:{tag}")
        expected.add(key)
        path = Path(indexed[key]["workdir"]) / relative
        _owned_path(run, path, directory=path.is_dir())
        return path

    def original_output(path: Path, process: str, tag: str, relative: str) -> None:
        if path.resolve(strict=True) != task_output(process, tag, relative).resolve(
            strict=True
        ):
            raise ValueError(
                "reference context does not name its original trace output"
            )

    original_output(
        plan_context.plan_path,
        "RF_PLAN",
        "rf-plan:fixed-five",
        "reference_plan/bundle/reference_plan.json",
    )
    plan = ReferenceTaskPlan.model_validate_json(plan_context.plan_path.read_bytes())
    catalogues = {
        row.task.catalogue_key: task_output(
            "M6_IMPORT_CATALOGUE",
            f"m6-import:{row.task.catalogue_key}",
            "m6_catalogue_bundle",
        )
        for row in plan.catalogues
    }
    batch_plan = task_output(
        "M6_BUILD_SEARCH_BATCHES", "m6-build-search-batches", "m6_batch_plan"
    )
    evidence = {"batch_plan": sha256_file(batch_plan / "batch_plan.json")}
    # These unchanged producers operate on metadata only. Their outputs contain
    # no temporary paths and must equal the original bytes, not replace them.
    with TemporaryDirectory(
        prefix="rf-reference-metadata-", dir=run / "artifacts/qualification"
    ) as temporary:
        temporary_root = Path(temporary)
        derived_plan = build_m6_search_batches(
            tuple(catalogues[key] for key in sorted(catalogues)),
            paths["database_manifest"],
            paths["execution_policy"],
            paths["software_lock"],
            temporary_root / "batch_plan",
        )
        _same_tree(run, batch_plan, derived_plan)
        searches: dict[str, tuple[Path, ...]] = {}
        for provider, process, prefix, output in (
            ("pdb_sequence", "M6_SEARCH_PDB", "m6-pdb", "m6_pdb_bundle"),
            (
                "prostt5_foldseek",
                "M6_SEARCH_FOLDSEEK",
                "m6-foldseek",
                "m6_foldseek_bundle",
            ),
        ):
            bundles = []
            for planned in sorted((derived_plan / f"{provider}_batches").iterdir()):
                original = task_output(process, f"{prefix}:{planned.name}", output)
                task = _search_bundle(run, original, planned, paths)
                if indexed[(process, f"{prefix}:{planned.name}")]["cpus"] != str(
                    task.threads
                ):
                    raise ValueError("reference native search CPU binding differs")
                bundles.append(original)
                evidence[f"{provider}:{task.batch_id}"] = sha256_file(
                    original / "bundle_manifest.json"
                )
            searches[provider] = tuple(bundles)
        partitions = {}
        for key, catalogue in catalogues.items():
            original = task_output(
                "M6_PARTITION_DISCOVERY",
                f"m6-partition:{key}",
                "m6_discovery_partition",
            )
            derived = partition_m6_discovery_task(
                catalogue,
                batch_plan,
                searches["pdb_sequence"],
                searches["prostt5_foldseek"],
                temporary_root / key,
            )
            _same_tree(run, original, derived)
            partitions[key] = original
    case_keys = {row.task.case_id: row.task.catalogue_key for row in plan.cases}
    if {item.case_id for item in prepared} != set(case_keys) or len(prepared) != len(
        case_keys
    ):
        raise ValueError("reference native prepared case universe differs")
    for item in prepared:
        case_id = item.case_id
        key = case_keys[case_id]
        if item.catalogue_bundle.resolve(strict=True) != catalogues[key].resolve(
            strict=True
        ):
            raise ValueError("reference native case changed its imported catalogue")
        original_output(
            item.prepared_path,
            "RF_PREPARE",
            f"rf-prepare:{case_id}",
            "reference_prepared/bundle/reference_prepared_case.json",
        )
        preflight = task_output(
            "M6_PREFLIGHT_CASE", f"m6-preflight:{case_id}", "m6_preflight_bundle"
        )
        _same_tree(run, preflight, item.prepared_case / "preflight_bundle")
        active = item.coordinate_stage is not None
        original_output(
            item.prepared_case,
            "M6_PREPARE_ACTIVE_CASE" if active else "M6_PREPARE_EARLY_CASE",
            f"m6-case:{case_id}" if active else f"m6-early-case:{case_id}",
            "m6_case_bundle",
        )
        if active:
            assert item.coordinate_stage is not None
            original_output(
                item.coordinate_stage,
                "M6_STAGE_COORDINATES",
                f"m6-coordinate-stage:{case_id}",
                "m6_coordinate_stage",
            )
            policy = task_output(
                "M6_APPLY_POLICY", f"m6-policy:{case_id}", "m6_policy_bundle"
            )
            _same_tree(run, policy, item.prepared_case / "policy_bundle")
            manifest = M6BundleManifest.model_validate_json(
                (policy / "bundle_manifest.json").read_bytes()
            )
            for label in ("pdb_bundle", "foldseek_bundle"):
                if manifest.input_sha256.get(label) != sha256_file(
                    partitions[key] / label / "bundle_manifest.json"
                ):
                    raise ValueError(
                        "reference native policy changed its complete search partition"
                    )
    for identity in identities:
        case_id = identity.finalists.review.prepared.case_id
        for path, process, tag, directory in (
            (
                identity.finalists.review.reviews_path,
                "RF_REVIEWS",
                "rf-reviews",
                "reference_reviews",
            ),
            (
                identity.finalists.finalists_path,
                "RF_FINALISTS",
                "rf-finalists",
                "reference_finalists",
            ),
            (
                identity.identity_path,
                "RF_IDENTITY",
                "rf-identity",
                "reference_identity",
            ),
        ):
            original_output(
                path, process, f"{tag}:{case_id}", f"{directory}/bundle/{path.name}"
            )
    aggregate = task_output(
        "RF_AGGREGATE", "rf-aggregate:fixed-five", "reference_run/bundle"
    )
    _same_tree(
        run, aggregate, run / "artifacts/rf-reference-results/reference_run/bundle"
    )
    if set(indexed) != expected:
        raise ValueError("reference native trace has an extra or foreign task")
    return dict(sorted(evidence.items()))
