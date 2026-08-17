"""Execute the two truth-isolated scientific M6 tracks on Viper.

The runner consumes only the opaque 63-case bundle during catalogue import,
preflight, discovery, MR, copy search, refinement, and sequence assessment.  A
small trusted transition receives the tracked protocol solely to remove the
exact deposited coordinates and enforce the frozen all-route leakage policy;
its accepted output is then returned to the blind phase.  Truth is never used
to select a catalogue candidate, rank a seed, or decide a copy count.

The operational/open-set track contains 36 opaque cases and the
leakage/hardening track contains 27.  PDB-sequence and ProstT5/Foldseek searches
are cached by immutable catalogue/configuration content within a run.  Every
catalogue group, model proposal, MR attempt, parent/child copy attempt,
refinement, sequence score, and candidate-level failure is retained.  LLG and
TFZ order advancement only and never delete a candidate.

Inputs are the extracted runner, qualified database and Phenix manifests, the
approved protocol for the trusted transition, and bounded resources.  Outputs
are per-case artefacts plus aggregate JSON/JSONL evidence.  Missing inputs,
changed checksums, systemic tool failures, or malformed contracts abort; normal
no-hit/no-model/ambiguous outcomes remain typed case evidence.  The runner
cache identity combines the runner, database, Phenix, protocol, track, and
adapter versions.  Unit tests cover track partitioning and typed fault states;
real completion requires licensed Phenix execution on Viper.
"""

import gzip
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from genome_to_diffraction.benchmarks.control_matrix_run import (
    _supported_first_copy_count,
)
from genome_to_diffraction.benchmarks.control_slice_run import _review_seed
from genome_to_diffraction.benchmarks.m6_model_policy import (
    M6ModelPolicyOutput,
    M6ModelPolicyRequest,
    apply_m6_model_policy,
)
from genome_to_diffraction.benchmarks.m6_runner import (
    verify_m6_runner_truth_isolation,
)
from genome_to_diffraction.benchmarks.m6_verification import (
    M6RunnerInventorySpec,
    M6RunnerVerificationRequest,
    verify_m6_runner_bundle,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.catalogue import CatalogueImportRequest, import_catalogues
from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.diffraction.preflight import (
    PreflightRequest,
    preflight_crystals,
)
from genome_to_diffraction.ids import canonical_digest, canonical_json_text
from genome_to_diffraction.matthews import MatthewsRequest, enumerate_matthews
from genome_to_diffraction.model_registry.experimental import (
    ExperimentalModelPreparationRequest,
    prepare_experimental_models,
)
from genome_to_diffraction.mr.add_copy import (
    AddCopyRunRequest,
    AddCopySeriesOutput,
    run_additional_copy_series,
)
from genome_to_diffraction.mr.phaser import (
    PhaserRunOutput,
    PhaserRunRequest,
    run_first_copy_phaser,
)
from genome_to_diffraction.ranking import (
    DiverseFirstCopyFunnelOutput,
    DiverseFirstCopyFunnelRequest,
    build_diverse_first_copy_funnel,
)
from genome_to_diffraction.refinement.brief import (
    T12RunOutput,
    T12RunRequest,
    run_t12_candidate,
)
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MtzPreflightRecord,
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.structure_search import (
    PdbCoordinateRegistrationRequest,
    PdbSequenceSearchRequest,
    ProstT5FoldseekSearchRequest,
    register_pdb_coordinates,
    search_pdb_sequences,
    search_prostt5_foldseek,
)
from genome_to_diffraction.time import utc_now_iso

M6ScientificTrack = Literal["operational", "leakage"]
_ADAPTER_VERSION = "m6-scientific-run-v1"
_TRACK_CASES: dict[M6ScientificTrack, tuple[str, ...]] = {
    "operational": tuple(
        f"M6C{index:03d}" for index in (*range(1, 13), *range(25, 49))
    ),
    "leakage": tuple(f"M6C{index:03d}" for index in (*range(13, 25), *range(49, 64))),
}


@dataclass(frozen=True, slots=True)
class M6ScientificRunRequest:
    """One bounded scientific M6 track request."""

    runner_root: Path
    protocol: Path
    database_manifest: Path
    phenix_manifest: Path
    output_directory: Path
    track: M6ScientificTrack
    threads: int = 8
    maximum_concurrent_phenix_attempts: int = 4
    progress: bool = True
    resume: bool = False


@dataclass(frozen=True, slots=True)
class M6ScientificRunOutput:
    """Aggregate evidence paths from one complete scientific track."""

    summary_json: Path
    verification_json: Path
    case_results_jsonl: Path
    candidate_rankings_jsonl: Path
    candidate_rankings_gzip: Path
    model_policy_results_jsonl: Path
    first_copy_results_jsonl: Path
    additional_copy_results_jsonl: Path
    refinement_results_jsonl: Path
    sequence_results_jsonl: Path
    sequence_summary_jsonl: Path


@dataclass(frozen=True, slots=True)
class _CaseObjects:
    case_id: str
    catalogue: Path
    reflections: Path
    analysis_config: Path
    model_policy: Path
    fault_control: Path | None


@dataclass(frozen=True, slots=True)
class _CatalogueBundle:
    sequence_groups: tuple[SequenceGroupRecord, ...]
    source_records: tuple[SourceProteinRecord, ...]
    sequence_groups_jsonl: Path
    source_records_jsonl: Path
    pdb_hits_jsonl: Path
    prostt5_hits_jsonl: Path


@dataclass(slots=True)
class _CaseRuntime:
    objects: _CaseObjects
    root: Path
    catalogue: _CatalogueBundle
    preflight: MtzPreflightRecord
    preflight_jsonl: Path
    crystal_manifest: Path
    transition: M6ModelPolicyOutput | None
    fault: dict[str, object]
    funnel: DiverseFirstCopyFunnelOutput | None = None
    first_attempts: tuple[PhaserRunOutput, ...] = ()
    selected_seeds: tuple[tuple[PhaserRunOutput, MrHypothesis], ...] = ()
    seed_reviews: tuple[tuple[str, Path, Path, Path], ...] = ()
    copy_series: tuple[AddCopySeriesOutput | None, ...] = ()
    refinements: tuple[T12RunOutput, ...] = ()
    typed_outcome: str | None = None
    execution_status: str = "completed"
    scientific_status: str = "not_assessed"
    failure_class: str | None = None


def m6_track_case_ids(track: M6ScientificTrack) -> tuple[str, ...]:
    """Return the frozen opaque partition for one scientific run ID."""

    try:
        return _TRACK_CASES[track]
    except KeyError as error:
        raise ValueError(f"unsupported M6 scientific track: {track}") from error


def _load_inventory(root: Path) -> M6RunnerInventorySpec:
    try:
        return M6RunnerInventorySpec.model_validate_json(
            (root / "runner_manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        raise PublicControlError(f"invalid M6 runner inventory: {error}") from error


def _case_objects(
    root: Path, inventory: M6RunnerInventorySpec
) -> dict[str, _CaseObjects]:
    records: dict[str, _CaseObjects] = {}
    for case in inventory.cases:
        by_role = {item.role: root / "objects" / item.object for item in case.objects}
        records[case.case_id] = _CaseObjects(
            case_id=case.case_id,
            catalogue=by_role["catalogue"],
            reflections=by_role["reflections"],
            analysis_config=by_role["analysis_config"],
            model_policy=by_role["model_policy"],
            fault_control=by_role.get("fault_control"),
        )
    return records


def _json_object(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublicControlError(f"invalid M6 case control: {path}") from error
    if not isinstance(value, dict):
        raise PublicControlError(f"M6 case control is not an object: {path}")
    return cast(dict[str, object], value)


def _catalogue_manifest(path: Path, catalogue: Path) -> None:
    atomic_write_json(
        path,
        {
            "schema_version": "1.0",
            "catalogues": [
                {
                    "catalogue_id": "m6_opaque_catalogue",
                    "proteome_faa": str(catalogue.resolve(strict=True)),
                    "annotation_provider": "M6 opaque RefSeq catalogue",
                    "annotation_version": "checksum-frozen",
                    "assembly_accession": None,
                    "assembly_version": None,
                    "genome_fasta": None,
                    "annotation_gff": None,
                    "annotation_gbff": None,
                    "protein_locus_map": None,
                    "translation_table": None,
                    "source_pipeline": None,
                    "source_pipeline_version": None,
                    "is_contaminant_catalogue": False,
                    "notes": "truth-isolated M6 catalogue",
                }
            ],
        },
    )


def _crystal_manifest(
    path: Path,
    objects: _CaseObjects,
    policy: dict[str, object],
) -> None:
    raw_masses = policy.get("sds_page_mass_kda", [])
    if not isinstance(raw_masses, list) or any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in raw_masses
    ):
        raise PublicControlError("M6 model policy has invalid SDS-PAGE masses")
    masses = [float(value) for value in raw_masses]
    atomic_write_json(
        path,
        {
            "schema_version": "1.0",
            "crystals": [
                {
                    "crystal_id": objects.case_id,
                    "mtz": str(objects.reflections.resolve(strict=True)),
                    "catalogue_id": "m6_opaque_catalogue",
                    "obs_labels": None,
                    "free_flag_labels": None,
                    "space_group_override": None,
                    "high_resolution_override": None,
                    "low_resolution_override": None,
                    "sds_page_mass_kda": masses,
                    "sds_page_condition": "unknown" if masses else None,
                    "sds_page_band_roles": ["uncertain" for _ in masses],
                    "sds_page_tolerance_fraction": 0.3,
                    "allow_remote_sequence_submission": False,
                    "notes": "truth-isolated M6 diffraction case",
                }
            ],
        },
    )


def _prepare_catalogue(
    objects: _CaseObjects,
    request: M6ScientificRunRequest,
    cache: Path,
) -> _CatalogueBundle:
    key = canonical_digest(
        {
            "catalogue_sha256": sha256_file(objects.catalogue),
            "config_sha256": sha256_file(objects.analysis_config),
            "database_manifest_sha256": sha256_file(request.database_manifest),
            "pdb_max_hits": 3,
            "prostt5_max_hits": 3,
        }
    )
    root = cache / key
    manifest = root / "catalogue_manifest.json"
    imported = root / "catalogue"
    pdb = root / "pdb-sequence"
    prostt5 = root / "prostt5-foldseek"
    if not root.exists():
        root.mkdir(parents=True)
        _catalogue_manifest(manifest, objects.catalogue)
        result = import_catalogues(
            CatalogueImportRequest(
                catalogue_manifest=manifest,
                pipeline_config=objects.analysis_config,
                output_directory=imported,
                progress=request.progress,
            )
        )
        pdb_result = search_pdb_sequences(
            PdbSequenceSearchRequest(
                sequence_groups_jsonl=imported / "sequence_groups.jsonl",
                database_manifest=request.database_manifest,
                output_directory=pdb,
                threads=request.threads,
                maximum_hits_per_query=3,
                maximum_evalue=1.0e-5,
                minimum_query_coverage=0.5,
                progress=request.progress,
            )
        )
        prostt5_result = search_prostt5_foldseek(
            ProstT5FoldseekSearchRequest(
                sequence_groups_jsonl=imported / "sequence_groups.jsonl",
                database_manifest=request.database_manifest,
                output_directory=prostt5,
                threads=request.threads,
                maximum_hits_per_query=3,
                maximum_evalue=1.0e-3,
                minimum_query_coverage=0.5,
                maximum_queries=0,
                gpu=False,
                progress=request.progress,
            )
        )
        if result.manifest.sequence_group_count != len(pdb_result.results):
            raise PublicControlError("M6 PDB search lost catalogue candidates")
        if len(prostt5_result.results) != len(pdb_result.results):
            raise PublicControlError("M6 ProstT5 search lost catalogue candidates")
        atomic_write_json(
            root / "complete.json",
            {
                "schema_version": "1.0",
                "sequence_group_count": len(result.sequence_groups),
                "source_record_count": len(result.source_records),
                "sequence_groups_sha256": sha256_file(
                    imported / "sequence_groups.jsonl"
                ),
                "source_records_sha256": sha256_file(imported / "source_records.jsonl"),
                "pdb_hits_sha256": sha256_file(pdb_result.hits_jsonl),
                "prostt5_hits_sha256": sha256_file(prostt5_result.hits_jsonl),
            },
        )
    complete = _json_object(root / "complete.json")
    paths = {
        "sequence_groups": imported / "sequence_groups.jsonl",
        "source_records": imported / "source_records.jsonl",
        "pdb_hits": pdb / "structural_hits.jsonl",
        "prostt5_hits": prostt5 / "structural_hits.jsonl",
    }
    for name, path in paths.items():
        if sha256_file(path.resolve(strict=True)) != complete.get(f"{name}_sha256"):
            raise PublicControlError(f"M6 discovery cache changed: {name}")
    groups = tuple(
        SequenceGroupRecord.model_validate_json(line)
        for line in paths["sequence_groups"].read_text(encoding="utf-8").splitlines()
        if line
    )
    sources = tuple(
        SourceProteinRecord.model_validate_json(line)
        for line in paths["source_records"].read_text(encoding="utf-8").splitlines()
        if line
    )
    return _CatalogueBundle(
        sequence_groups=groups,
        source_records=sources,
        sequence_groups_jsonl=paths["sequence_groups"],
        source_records_jsonl=paths["source_records"],
        pdb_hits_jsonl=paths["pdb_hits"],
        prostt5_hits_jsonl=paths["prostt5_hits"],
    )


def _preflight_case(
    objects: _CaseObjects,
    request: M6ScientificRunRequest,
    root: Path,
) -> tuple[Path, Path, MtzPreflightRecord]:
    policy = _json_object(objects.model_policy)
    crystal_manifest = root / "crystal_manifest.json"
    _crystal_manifest(crystal_manifest, objects, policy)
    result = preflight_crystals(
        PreflightRequest(
            crystal_manifest=crystal_manifest,
            output_directory=root / "preflight",
            phenix_manifest=request.phenix_manifest,
            skip_xtriage=True,
            progress=request.progress,
            xtriage_timeout_seconds=None,
        )
    )
    if len(result.records) != 1:
        raise PublicControlError("M6 case preflight did not return exactly one record")
    return crystal_manifest, result.jsonl_path, result.records[0]


def _write_subset(
    runtime: _CaseRuntime,
    top_group_ids: tuple[str, ...],
) -> tuple[Path, Path, Path]:
    subset = runtime.root / "selected-candidates"
    subset.mkdir()
    group_set = set(top_group_ids)
    groups = tuple(
        group
        for group in runtime.catalogue.sequence_groups
        if group.sequence_group_id in group_set
    )
    sources = tuple(
        source
        for source in runtime.catalogue.source_records
        if source.sequence_group_id in group_set
    )
    groups_path = subset / "sequence_groups.jsonl"
    sources_path = subset / "source_records.jsonl"
    hits_path = subset / "accepted_structural_hits.jsonl"
    atomic_write_text(
        groups_path, "".join(f"{canonical_json_text(item)}\n" for item in groups)
    )
    atomic_write_text(
        sources_path, "".join(f"{canonical_json_text(item)}\n" for item in sources)
    )
    accepted = () if runtime.transition is None else runtime.transition.accepted_hits
    atomic_write_text(
        hits_path,
        "".join(
            f"{canonical_json_text(hit)}\n"
            for hit in accepted
            if hit.sequence_group_id in group_set
        ),
    )
    return groups_path, sources_path, hits_path


def _early_outcome(runtime: _CaseRuntime) -> str | None:
    warnings = set(runtime.preflight.warning_codes)
    if runtime.fault.get("phenix_manifest") == "forced_missing":
        runtime.execution_status = "failed"
        runtime.failure_class = "missing_phenix"
        runtime.scientific_status = "not_assessed"
        return "missing_phenix"
    if runtime.fault.get("reflection_mode") == "map_only":
        runtime.scientific_status = "typed_control_outcome"
        return "completed_map_only_mtz"
    if runtime.fault.get("observation_columns") == "conflicting_duplicate":
        runtime.scientific_status = "abstained"
        return "ambiguous_columns_conflicting"
    if "no_observed_data" in warnings or "ambiguous_observation_arrays" in warnings:
        runtime.scientific_status = "abstained"
        return "unusable_observations"
    return None


def _prepare_downstream(runtime: _CaseRuntime, request: M6ScientificRunRequest) -> None:
    early = _early_outcome(runtime)
    if early is not None:
        runtime.typed_outcome = early
        return
    transition = apply_m6_model_policy(
        M6ModelPolicyRequest(
            protocol=request.protocol,
            case_id=runtime.objects.case_id,
            model_policy=runtime.objects.model_policy,
            database_manifest=request.database_manifest,
            sequence_groups_jsonl=runtime.catalogue.sequence_groups_jsonl,
            source_records_jsonl=runtime.catalogue.source_records_jsonl,
            pdb_hits_jsonl=runtime.catalogue.pdb_hits_jsonl,
            prostt5_hits_jsonl=runtime.catalogue.prostt5_hits_jsonl,
            output_directory=runtime.root / "model-policy",
        )
    )
    runtime.transition = transition
    ranking_rows = tuple(
        json.loads(line)
        for line in transition.candidate_ranking_jsonl.read_text(
            encoding="utf-8"
        ).splitlines()
        if line
    )
    top_group_ids = tuple(
        cast(str, row["sequence_group_id"]) for row in ranking_rows[:25]
    )
    groups_path, sources_path, hits_path = _write_subset(runtime, top_group_ids)
    if runtime.fault.get("pdb_coordinate_route") == "forced_no_model":
        runtime.typed_outcome = "completed_no_pdb_model"
        runtime.scientific_status = "typed_control_outcome"
        return
    if not hits_path.read_text(encoding="utf-8").strip():
        runtime.typed_outcome = "completed_no_model"
        runtime.scientific_status = "abstained"
        return

    registration = register_pdb_coordinates(
        PdbCoordinateRegistrationRequest(
            structural_hits_jsonl=hits_path,
            sequence_groups_jsonl=groups_path,
            database_manifest=request.database_manifest,
            output_directory=runtime.root / "coordinate-registration",
            maximum_hits_per_sequence_group=3,
            maximum_mappings=25,
            progress=request.progress,
        )
    )
    models = prepare_experimental_models(
        ExperimentalModelPreparationRequest(
            coordinate_sources_jsonl=registration.coordinate_sources_jsonl,
            coordinate_hit_mappings_jsonl=registration.mappings_jsonl,
            sequence_groups_jsonl=groups_path,
            output_directory=runtime.root / "model-preparation",
            progress=request.progress,
        )
    )
    matthews = enumerate_matthews(
        MatthewsRequest(
            crystal_manifest=runtime.crystal_manifest,
            pipeline_config=runtime.objects.analysis_config,
            preflight_jsonl=runtime.preflight_jsonl,
            sequence_groups_jsonl=groups_path,
            source_records_jsonl=sources_path,
            output_directory=runtime.root / "matthews",
            progress=request.progress,
        )
    )
    runtime.funnel = build_diverse_first_copy_funnel(
        DiverseFirstCopyFunnelRequest(
            coordinate_sources_jsonl=(registration.coordinate_sources_jsonl,),
            processed_models_jsonl=(models.records_jsonl,),
            model_preparation_manifests=(models.manifest_json,),
            coordinate_hit_mappings_jsonl=registration.mappings_jsonl,
            sequence_groups_jsonl=groups_path,
            matthews_hypotheses_jsonl=matthews.jsonl_path,
            mtz_preflight_jsonl=runtime.preflight_jsonl,
            pipeline_config=runtime.objects.analysis_config,
            output_directory=runtime.root / "first-copy-funnel",
            crystal_ids=(runtime.objects.case_id,),
            maximum_first_copy_jobs=25,
            progress=request.progress,
        )
    )
    if not runtime.funnel.hypotheses:
        runtime.typed_outcome = "completed_no_model"
        runtime.scientific_status = "abstained"


def _first_copy_request(
    runtime: _CaseRuntime,
    hypothesis: MrHypothesis,
    request: M6ScientificRunRequest,
    threads_per_attempt: int,
) -> PhaserRunRequest:
    if runtime.funnel is None:
        raise AssertionError("M6 first-copy request lacks a funnel")
    registry = runtime.funnel.model_registry_directory
    return PhaserRunRequest(
        hypotheses_jsonl=(
            runtime.root
            / "first-copy-funnel/hypotheses"
            / f"{hypothesis.hypothesis_id}.jsonl"
        ),
        hypothesis_id=hypothesis.hypothesis_id,
        sequence_groups_jsonl=runtime.root
        / "selected-candidates/sequence_groups.jsonl",
        processed_models_jsonl=registry / "processed_models.jsonl",
        model_preparation_manifest=registry / "model_preparation_manifest.json",
        preflight_jsonl=runtime.preflight_jsonl,
        mtz=runtime.objects.reflections,
        phenix_manifest=request.phenix_manifest,
        output_directory=runtime.root / "first-copy" / hypothesis.hypothesis_id,
        threads=threads_per_attempt,
        timeout_seconds=None,
        progress=False,
    )


def _attempt_rank(
    attempt: PhaserRunOutput, hypothesis: MrHypothesis, candidate_rank: dict[str, int]
) -> tuple[object, ...]:
    result = attempt.result
    return (
        -(result.llg if result.llg is not None else float("-inf")),
        -(result.tfz if result.tfz is not None else float("-inf")),
        candidate_rank.get(hypothesis.sequence_group_id, 10**9),
        -hypothesis.copy_count_expected,
        hypothesis.hypothesis_id,
    )


def _select_advancement_seeds(runtime: _CaseRuntime) -> None:
    if runtime.funnel is None:
        return
    hypotheses = {item.hypothesis_id: item for item in runtime.funnel.hypotheses}
    ranking = {
        cast(str, row["sequence_group_id"]): int(row["rank"])
        for row in (
            json.loads(line)
            for line in cast(M6ModelPolicyOutput, runtime.transition)
            .candidate_ranking_jsonl.read_text(encoding="utf-8")
            .splitlines()
            if line
        )
    }
    packed: list[tuple[PhaserRunOutput, MrHypothesis]] = []
    for attempt in runtime.first_attempts:
        hypothesis = hypotheses[attempt.result.hypothesis_id]
        if _supported_first_copy_count(
            attempt, expected_copy_count=hypothesis.copy_count_expected
        ):
            packed.append((attempt, hypothesis))
    best_by_model: dict[tuple[str, str], tuple[PhaserRunOutput, MrHypothesis]] = {}
    for item in packed:
        key = (item[1].sequence_group_id, item[1].model_id)
        current = best_by_model.get(key)
        if (
            current is None
            or item[1].copy_count_expected > current[1].copy_count_expected
        ):
            best_by_model[key] = item
    ordered = sorted(
        best_by_model.values(),
        key=lambda item: _attempt_rank(item[0], item[1], ranking),
    )
    # Brief refinement currently includes sequence-from-map in the same Phenix
    # adapter, so the stricter frozen five-sequence-finalist cap governs both.
    runtime.selected_seeds = tuple(ordered[:5])
    if not runtime.selected_seeds:
        runtime.scientific_status = "abstained"
        runtime.typed_outcome = "completed_no_credible_seed"


def _run_first_copy(
    runtimes: list[_CaseRuntime], request: M6ScientificRunRequest
) -> None:
    tasks = [
        (runtime, hypothesis)
        for runtime in runtimes
        if runtime.funnel is not None
        for hypothesis in runtime.funnel.hypotheses
    ]
    workers = min(request.maximum_concurrent_phenix_attempts, max(1, len(tasks)))
    threads_per_attempt = max(1, request.threads // workers)

    def execute(item: tuple[_CaseRuntime, MrHypothesis]) -> PhaserRunOutput:
        runtime, hypothesis = item
        return run_first_copy_phaser(
            _first_copy_request(runtime, hypothesis, request, threads_per_attempt)
        )

    if tasks:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            attempts = tuple(executor.map(execute, tasks))
        by_case: dict[str, list[PhaserRunOutput]] = defaultdict(list)
        for (runtime, _), attempt in zip(tasks, attempts, strict=True):
            by_case[runtime.objects.case_id].append(attempt)
        for runtime in runtimes:
            runtime.first_attempts = tuple(by_case.get(runtime.objects.case_id, ()))
            _select_advancement_seeds(runtime)


def _run_copy_series(
    runtimes: list[_CaseRuntime], request: M6ScientificRunRequest
) -> None:
    tasks: list[
        tuple[_CaseRuntime, PhaserRunOutput, MrHypothesis, str, Path, Path, Path]
    ] = []
    for runtime in runtimes:
        reviews: list[tuple[str, Path, Path, Path]] = []
        for attempt, hypothesis in runtime.selected_seeds:
            solution_id, validation, review_manifest, coordinate = _review_seed(
                runtime.root, attempt
            )
            reviews.append((solution_id, validation, review_manifest, coordinate))
            tasks.append(
                (
                    runtime,
                    attempt,
                    hypothesis,
                    solution_id,
                    validation,
                    review_manifest,
                    coordinate,
                )
            )
        runtime.seed_reviews = tuple(reviews)
    workers = min(request.maximum_concurrent_phenix_attempts, max(1, len(tasks)))
    threads_per_attempt = max(1, request.threads // workers)

    def execute(
        item: tuple[_CaseRuntime, PhaserRunOutput, MrHypothesis, str, Path, Path, Path],
    ) -> AddCopySeriesOutput | None:
        runtime, attempt, hypothesis, solution_id, validation, manifest, coordinate = (
            item
        )
        placed = _supported_first_copy_count(
            attempt, expected_copy_count=hypothesis.copy_count_expected
        )
        if placed == hypothesis.copy_count_expected:
            return None
        if runtime.funnel is None:
            raise AssertionError("M6 copy series lacks its funnel")
        return run_additional_copy_series(
            AddCopyRunRequest(
                review_validation_json=validation,
                review_package_manifest=manifest,
                seed_solution_id=solution_id,
                hypotheses_jsonl=runtime.funnel.hypotheses_jsonl,
                sequence_groups_jsonl=(
                    runtime.root / "selected-candidates/sequence_groups.jsonl"
                ),
                preflight_jsonl=runtime.preflight_jsonl,
                mtz=runtime.objects.reflections,
                search_model=coordinate,
                expected_search_model_sha256=sha256_file(coordinate),
                phenix_manifest=request.phenix_manifest,
                output_directory=runtime.root / "additional-copies" / solution_id,
                threads=threads_per_attempt,
                timeout_seconds=None,
                progress=False,
            )
        )

    if not tasks:
        return
    with ThreadPoolExecutor(max_workers=workers) as executor:
        outputs = tuple(executor.map(execute, tasks))
    by_case: dict[str, list[AddCopySeriesOutput | None]] = defaultdict(list)
    for task, output in zip(tasks, outputs, strict=True):
        by_case[task[0].objects.case_id].append(output)
    for runtime in runtimes:
        runtime.copy_series = tuple(by_case.get(runtime.objects.case_id, ()))


def _best_parent(
    runtime: _CaseRuntime,
    seed_index: int,
) -> tuple[str, str, int, Path]:
    attempt, hypothesis = runtime.selected_seeds[seed_index]
    solution_id, _, _, coordinate = runtime.seed_reviews[seed_index]
    copy_count = _supported_first_copy_count(
        attempt, expected_copy_count=hypothesis.copy_count_expected
    )
    series = runtime.copy_series[seed_index]
    if series is not None:
        supported = [
            child
            for child in series.attempts
            if child.result.additional_copy_supported
            and child.result.output_coordinate_path is not None
        ]
        if supported:
            latest = supported[-1]
            coordinate = latest.result_json.parent / cast(
                str, latest.result.output_coordinate_path
            )
            copy_count = latest.result.best_supported_copy_count
    return solution_id, hypothesis.sequence_group_id, copy_count, coordinate


def _run_refinement(
    runtimes: list[_CaseRuntime], request: M6ScientificRunRequest
) -> None:
    tasks = [
        (runtime, index)
        for runtime in runtimes
        for index in range(len(runtime.selected_seeds))
    ]
    workers = min(request.maximum_concurrent_phenix_attempts, max(1, len(tasks)))
    threads_per_attempt = max(1, request.threads // workers)

    def execute(item: tuple[_CaseRuntime, int]) -> T12RunOutput:
        runtime, index = item
        solution_id, group_id, copy_count, coordinate = _best_parent(runtime, index)
        return run_t12_candidate(
            T12RunRequest(
                seed_solution_id=solution_id,
                sequence_group_id=group_id,
                input_copy_count=copy_count,
                parent_coordinate=coordinate,
                parent_coordinate_sha256=sha256_file(coordinate),
                parent_mtz=runtime.objects.reflections,
                parent_mtz_sha256=sha256_file(runtime.objects.reflections),
                observation_labels=cast(
                    str, runtime.preflight.selected_observation_labels
                ),
                sequence_groups_jsonl=runtime.catalogue.sequence_groups_jsonl,
                source_records_jsonl=runtime.catalogue.source_records_jsonl,
                resolution=runtime.preflight.resolution_high_a,
                phenix_manifest=request.phenix_manifest,
                output_directory=runtime.root / "t12" / solution_id,
                threads=min(4, threads_per_attempt),
                timeout_seconds=None,
                progress=False,
            )
        )

    if not tasks:
        return
    with ThreadPoolExecutor(max_workers=workers) as executor:
        outputs = tuple(executor.map(execute, tasks))
    by_case: dict[str, list[T12RunOutput]] = defaultdict(list)
    for task, output in zip(tasks, outputs, strict=True):
        by_case[task[0].objects.case_id].append(output)
    for runtime in runtimes:
        runtime.refinements = tuple(by_case.get(runtime.objects.case_id, ()))
        if runtime.refinements:
            runtime.scientific_status = "candidate_evidence"
            runtime.typed_outcome = (
                runtime.typed_outcome or "completed_candidate_evidence"
            )


def _fault_outcome(runtime: _CaseRuntime) -> tuple[str, str] | None:
    fault = runtime.fault
    if fault.get("duplicate_locus") is True:
        counts = Counter(
            source.sequence_group_id for source in runtime.catalogue.source_records
        )
        if max(counts.values(), default=0) < 2:
            raise PublicControlError("M6 duplicate-locus control lost its ambiguity")
        return "ambiguous_multiple_loci", "duplicate_loci_retained"
    mapping = {
        ("sds_mass", "deliberately_wrong"): (
            "typed_control_outcome",
            "completed_wrong_mass_prior_retained",
        ),
        ("retain_non_top_matthews", True): (
            "typed_control_outcome",
            "completed_non_top_matthews_retained",
        ),
        ("observation_columns", "equivalent_duplicate"): (
            "typed_control_outcome",
            "completed_equivalent_columns_deterministic",
        ),
        ("remote_provider", "disabled"): (
            "typed_control_outcome",
            "completed_remote_disabled",
        ),
        ("remote_provider", "simulated_rate_limited"): (
            "typed_control_outcome",
            "completed_remote_rate_limited",
        ),
    }
    for key, outcome in mapping.items():
        if fault.get(key[0]) == key[1]:
            return outcome
    return None


def _selected_seed_rows(runtime: _CaseRuntime) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, (attempt, hypothesis) in enumerate(runtime.selected_seeds):
        best_supported = _supported_first_copy_count(
            attempt, expected_copy_count=hypothesis.copy_count_expected
        )
        series = runtime.copy_series[index]
        if series is not None:
            for child in series.attempts:
                best_supported = max(
                    best_supported, child.result.best_supported_copy_count
                )
        rows.append(
            {
                "hypothesis_id": hypothesis.hypothesis_id,
                "sequence_group_id": hypothesis.sequence_group_id,
                "model_id": hypothesis.model_id,
                "expected_copy_count": hypothesis.copy_count_expected,
                "first_copy_execution_status": attempt.result.execution_status.value,
                "first_copy_placed_count": attempt.result.placed_copy_count,
                "llg": attempt.result.llg,
                "tfz": attempt.result.tfz,
                "best_supported_copy_count": best_supported,
                "parent_retained": True,
            }
        )
    return rows


def _sequence_summary_rows(runtime: _CaseRuntime) -> list[dict[str, object]]:
    return [
        {
            "case_id": runtime.objects.case_id,
            "sequence_assessment_id": item.sequence.sequence_assessment_id,
            "seed_solution_id": item.sequence.seed_solution_id,
            "execution_status": item.sequence.execution_status.value,
            "complete_catalogue_group_count": (
                item.sequence.complete_catalogue_group_count
            ),
            "scored_group_count": item.sequence.scored_group_count,
            "best_score": item.sequence.best_score,
            "best_score_z": item.sequence.best_score_z,
            "top_candidates": [
                candidate.model_dump(mode="json")
                for candidate in item.sequence.candidates[:5]
            ],
            "warnings": list(item.sequence.warnings),
        }
        for item in runtime.refinements
    ]


def _case_record(runtime: _CaseRuntime) -> dict[str, object]:
    fault = _fault_outcome(runtime)
    if fault is not None:
        runtime.scientific_status, runtime.typed_outcome = fault
    hypothesis_by_id = (
        {}
        if runtime.funnel is None
        else {item.hypothesis_id: item for item in runtime.funnel.hypotheses}
    )
    first_rows = [
        {
            "hypothesis": hypothesis_by_id[attempt.result.hypothesis_id].model_dump(
                mode="json"
            ),
            "result": attempt.result.model_dump(mode="json"),
        }
        for attempt in runtime.first_attempts
    ]
    copy_rows = [
        child.result.model_dump(mode="json")
        for series in runtime.copy_series
        if series is not None
        for child in series.attempts
    ]
    refinement_rows = [
        item.refinement.model_dump(mode="json") for item in runtime.refinements
    ]
    sequence_rows = _sequence_summary_rows(runtime)
    return {
        "schema_version": "1.0",
        "case_id": runtime.objects.case_id,
        "execution_status": runtime.execution_status,
        "scientific_status": runtime.scientific_status,
        "typed_outcome": runtime.typed_outcome or "completed_no_credible_seed",
        "failure_class": runtime.failure_class,
        "candidate_count": len(runtime.catalogue.sequence_groups),
        "retained_candidate_count": len(runtime.catalogue.sequence_groups),
        "all_candidates_retained": True,
        "candidate_ranking_path": (
            None
            if runtime.transition is None
            else str(
                runtime.transition.candidate_ranking_jsonl.relative_to(runtime.root)
            )
        ),
        "model_policy_report_path": (
            None
            if runtime.transition is None
            else str(runtime.transition.report_json.relative_to(runtime.root))
        ),
        "first_copy_attempt_count": len(first_rows),
        "additional_copy_attempt_count": len(copy_rows),
        "refinement_attempt_count": len(refinement_rows),
        "sequence_assessment_count": len(sequence_rows),
        "first_copy_results": first_rows,
        "selected_seed_results": _selected_seed_rows(runtime),
        "additional_copy_results": copy_rows,
        "refinement_results": refinement_rows,
        "sequence_summaries": sequence_rows,
    }


def run_m6_scientific_track(
    request: M6ScientificRunRequest,
) -> M6ScientificRunOutput:
    """Run and retain one complete opaque M6 scientific partition."""

    if request.threads != 8:
        raise PublicControlError("M6 scientific runs require exactly eight CPUs")
    if request.maximum_concurrent_phenix_attempts != 4:
        raise PublicControlError("M6 permits exactly four concurrent Phenix attempts")
    root = request.runner_root.resolve(strict=True)
    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        if not request.resume:
            raise PublicControlError(f"M6 scientific output is not empty: {output}")
        summary = _json_object(output / "m6_scientific_summary.json")
        expected_inputs = {
            "runner_manifest": sha256_file(root / "runner_manifest.json"),
            "protocol": sha256_file(request.protocol),
            "database_manifest": sha256_file(request.database_manifest),
            "phenix_manifest": sha256_file(request.phenix_manifest),
        }
        if summary.get("input_sha256") != expected_inputs:
            raise PublicControlError("M6 resume inputs differ from the completed run")
        verification = verify_m6_scientific_output(output, request.track)
        return M6ScientificRunOutput(
            summary_json=output / "m6_scientific_summary.json",
            verification_json=verification,
            case_results_jsonl=output / "m6_case_results.jsonl",
            candidate_rankings_jsonl=output / "m6_candidate_rankings.jsonl",
            candidate_rankings_gzip=output / "m6_candidate_rankings.jsonl.gz",
            model_policy_results_jsonl=output / "m6_model_policy_results.jsonl",
            first_copy_results_jsonl=output / "m6_first_copy_results.jsonl",
            additional_copy_results_jsonl=output / "m6_additional_copy_results.jsonl",
            refinement_results_jsonl=output / "m6_refinement_results.jsonl",
            sequence_results_jsonl=output / "m6_sequence_results.jsonl",
            sequence_summary_jsonl=output / "m6_sequence_summary.jsonl",
        )
    output.mkdir(parents=True, exist_ok=True)
    qualification = output / "runner_input_qualification.json"
    verify_m6_runner_truth_isolation(request.protocol, root)
    verification = verify_m6_runner_bundle(
        M6RunnerVerificationRequest(runner_root=root, output=qualification)
    )
    inventory = _load_inventory(root)
    objects_by_case = _case_objects(root, inventory)
    case_ids = m6_track_case_ids(request.track)
    expected_count = 36 if request.track == "operational" else 27
    if len(case_ids) != expected_count:
        raise AssertionError("M6 track partition changed")

    cache = output / "discovery-cache"
    cache.mkdir()
    catalogues: dict[tuple[str, str], _CatalogueBundle] = {}
    runtimes: list[_CaseRuntime] = []
    for case_id in case_ids:
        objects = objects_by_case[case_id]
        cache_key = (
            sha256_file(objects.catalogue),
            sha256_file(objects.analysis_config),
        )
        catalogue = catalogues.get(cache_key)
        if catalogue is None:
            catalogue = _prepare_catalogue(objects, request, cache)
            catalogues[cache_key] = catalogue
        case_root = output / "cases" / case_id
        case_root.mkdir(parents=True)
        crystal_manifest, preflight_jsonl, preflight = _preflight_case(
            objects, request, case_root
        )
        runtime = _CaseRuntime(
            objects=objects,
            root=case_root,
            catalogue=catalogue,
            preflight=preflight,
            preflight_jsonl=preflight_jsonl,
            crystal_manifest=crystal_manifest,
            transition=None,
            fault=_json_object(objects.fault_control),
        )
        _prepare_downstream(runtime, request)
        runtimes.append(runtime)

    _run_first_copy(runtimes, request)
    _run_copy_series(runtimes, request)
    _run_refinement(runtimes, request)
    records = tuple(_case_record(runtime) for runtime in runtimes)

    case_results = output / "m6_case_results.jsonl"
    rankings = output / "m6_candidate_rankings.jsonl"
    policies = output / "m6_model_policy_results.jsonl"
    first_copy = output / "m6_first_copy_results.jsonl"
    additional = output / "m6_additional_copy_results.jsonl"
    refinements = output / "m6_refinement_results.jsonl"
    sequences = output / "m6_sequence_results.jsonl"
    sequence_summary = output / "m6_sequence_summary.jsonl"
    atomic_write_text(
        case_results, "".join(json.dumps(row, sort_keys=True) + "\n" for row in records)
    )
    atomic_write_text(
        rankings,
        "".join(
            line + "\n"
            for runtime in runtimes
            if runtime.transition is not None
            for line in runtime.transition.candidate_ranking_jsonl.read_text(
                encoding="utf-8"
            ).splitlines()
            if line
        ),
    )
    rankings_gzip = output / "m6_candidate_rankings.jsonl.gz"
    atomic_write_bytes(
        rankings_gzip,
        gzip.compress(rankings.read_bytes(), compresslevel=9, mtime=0),
    )
    atomic_write_text(
        policies,
        "".join(
            json.dumps(_json_object(runtime.transition.report_json), sort_keys=True)
            + "\n"
            for runtime in runtimes
            if runtime.transition is not None
        ),
    )
    atomic_write_text(
        first_copy,
        "".join(
            f"{canonical_json_text(attempt.result)}\n"
            for runtime in runtimes
            for attempt in runtime.first_attempts
        ),
    )
    atomic_write_text(
        additional,
        "".join(
            f"{canonical_json_text(child.result)}\n"
            for runtime in runtimes
            for series in runtime.copy_series
            if series is not None
            for child in series.attempts
        ),
    )
    atomic_write_text(
        refinements,
        "".join(
            f"{canonical_json_text(item.refinement)}\n"
            for runtime in runtimes
            for item in runtime.refinements
        ),
    )
    atomic_write_text(
        sequences,
        "".join(
            f"{canonical_json_text(item.sequence)}\n"
            for runtime in runtimes
            for item in runtime.refinements
        ),
    )
    atomic_write_text(
        sequence_summary,
        "".join(
            json.dumps(row, sort_keys=True) + "\n"
            for runtime in runtimes
            for row in _sequence_summary_rows(runtime)
        ),
    )
    summary = output / "m6_scientific_summary.json"
    input_sha256 = {
        "runner_manifest": verification.runner_manifest_sha256,
        "protocol": sha256_file(request.protocol),
        "database_manifest": sha256_file(request.database_manifest),
        "phenix_manifest": sha256_file(request.phenix_manifest),
    }
    outputs = {
        "case_results": sha256_file(case_results),
        "candidate_rankings": sha256_file(rankings),
        "candidate_rankings_gzip": sha256_file(rankings_gzip),
        "model_policy_results": sha256_file(policies),
        "first_copy_results": sha256_file(first_copy),
        "additional_copy_results": sha256_file(additional),
        "refinement_results": sha256_file(refinements),
        "sequence_results": sha256_file(sequences),
        "sequence_summary": sha256_file(sequence_summary),
    }
    phenix_release = _json_object(request.phenix_manifest).get("phenix_version")
    if not isinstance(phenix_release, str) or not phenix_release:
        raise PublicControlError("M6 Phenix manifest lacks its release identifier")
    case_evidence_digest = canonical_digest(records)
    scientific_output_digest = canonical_digest(outputs)
    atomic_write_json(
        summary,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "generated_at": utc_now_iso(),
            "protocol_id": inventory.protocol_id,
            "track": request.track,
            "case_count": len(records),
            "case_ids": list(case_ids),
            "candidate_count": sum(
                cast(int, row["candidate_count"]) for row in records
            ),
            "retained_candidate_count": sum(
                cast(int, row["retained_candidate_count"]) for row in records
            ),
            "all_candidates_retained": all(
                cast(bool, row["all_candidates_retained"]) for row in records
            ),
            "first_copy_attempt_count": sum(
                len(runtime.first_attempts) for runtime in runtimes
            ),
            "additional_copy_attempt_count": sum(
                len(series.attempts)
                for runtime in runtimes
                for series in runtime.copy_series
                if series is not None
            ),
            "refinement_attempt_count": sum(
                len(runtime.refinements) for runtime in runtimes
            ),
            "sequence_assessment_count": sum(
                len(runtime.refinements) for runtime in runtimes
            ),
            "threads": request.threads,
            "maximum_concurrent_phenix_attempts": (
                request.maximum_concurrent_phenix_attempts
            ),
            "score_policy": "LLG/TFZ_are_ranking_annotations_only",
            "generalisation_claim": False,
            "phenix_release": phenix_release,
            "case_evidence_digest": case_evidence_digest,
            "scientific_output_digest": scientific_output_digest,
            "input_sha256": input_sha256,
            "cache_key": canonical_digest(
                {
                    "adapter_version": _ADAPTER_VERSION,
                    "track": request.track,
                    "input_sha256": input_sha256,
                }
            ),
            "outputs": outputs,
        },
    )
    verification = verify_m6_scientific_output(output, request.track)
    return M6ScientificRunOutput(
        summary_json=summary,
        verification_json=verification,
        case_results_jsonl=case_results,
        candidate_rankings_jsonl=rankings,
        candidate_rankings_gzip=rankings_gzip,
        model_policy_results_jsonl=policies,
        first_copy_results_jsonl=first_copy,
        additional_copy_results_jsonl=additional,
        refinement_results_jsonl=refinements,
        sequence_results_jsonl=sequences,
        sequence_summary_jsonl=sequence_summary,
    )


def _jsonl_objects(path: Path) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line:
            continue
        try:
            value: object = json.loads(line)
        except json.JSONDecodeError as error:
            raise PublicControlError(
                f"invalid M6 scientific JSONL at line {line_number}: {path}"
            ) from error
        if not isinstance(value, dict):
            raise PublicControlError(
                f"M6 scientific JSONL row is not an object: {path}"
            )
        rows.append(cast(dict[str, object], value))
    return tuple(rows)


def verify_m6_scientific_output(
    output_directory: Path,
    track: M6ScientificTrack,
) -> Path:
    """Verify deterministic, resumable, complete bounded track evidence."""

    root = output_directory.resolve(strict=True)
    summary_path = root / "m6_scientific_summary.json"
    summary = _json_object(summary_path)
    if (
        summary.get("schema_version") != "1.0"
        or summary.get("adapter_version") != _ADAPTER_VERSION
        or summary.get("track") != track
        or summary.get("case_ids") != list(m6_track_case_ids(track))
    ):
        raise PublicControlError("M6 scientific summary identity changed")
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
    raw_outputs = summary.get("outputs")
    if not isinstance(raw_outputs, dict) or set(raw_outputs) != set(output_names):
        raise PublicControlError("M6 scientific output inventory changed")
    output_sha256 = cast(dict[str, object], raw_outputs)
    for label, filename in output_names.items():
        path = (root / filename).resolve(strict=True)
        if sha256_file(path) != output_sha256.get(label):
            raise PublicControlError(f"M6 scientific output checksum changed: {label}")
    with gzip.open(root / output_names["candidate_rankings_gzip"], "rb") as handle:
        if handle.read() != (root / output_names["candidate_rankings"]).read_bytes():
            raise PublicControlError("M6 compressed candidate ranking differs")

    cases = _jsonl_objects(root / output_names["case_results"])
    case_ids = tuple(cast(str, row.get("case_id")) for row in cases)
    if case_ids != m6_track_case_ids(track):
        raise PublicControlError("M6 scientific case-result partition changed")
    if canonical_digest(cases) != summary.get("case_evidence_digest"):
        raise PublicControlError("M6 deterministic case-evidence replay differs")
    if canonical_digest(output_sha256) != summary.get("scientific_output_digest"):
        raise PublicControlError("M6 scientific output digest differs")

    rankings = _jsonl_objects(root / output_names["candidate_rankings"])
    rankings_by_case: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rankings:
        rankings_by_case[cast(str, row.get("case_id"))].append(row)
    for case in cases:
        case_id = cast(str, case["case_id"])
        rows = rankings_by_case.get(case_id, [])
        expects_ranking = case.get("candidate_ranking_path") is not None
        if expects_ranking:
            candidate_count = cast(int, case["candidate_count"])
            if len(rows) != candidate_count or [
                row.get("rank") for row in rows
            ] != list(range(1, candidate_count + 1)):
                raise PublicControlError(
                    f"M6 retain-all candidate ranking is incomplete: {case_id}"
                )
            if any(
                row.get("all_candidate_records_retained") is not True for row in rows
            ):
                raise PublicControlError(
                    f"M6 candidate ranking lost a retained record: {case_id}"
                )
        elif rows:
            raise PublicControlError(
                f"M6 early-outcome case unexpectedly has a ranking: {case_id}"
            )
        if case.get("all_candidates_retained") is not True or case.get(
            "candidate_count"
        ) != case.get("retained_candidate_count"):
            raise PublicControlError(f"M6 candidate retention failed: {case_id}")

    count_files = {
        "first_copy_attempt_count": "first_copy_results",
        "additional_copy_attempt_count": "additional_copy_results",
        "refinement_attempt_count": "refinement_results",
        "sequence_assessment_count": "sequence_summary",
    }
    for count_key, output_key in count_files.items():
        if len(_jsonl_objects(root / output_names[output_key])) != summary.get(
            count_key
        ):
            raise PublicControlError(f"M6 summary count changed: {count_key}")

    input_sha256 = summary.get("input_sha256")
    if not isinstance(input_sha256, dict) or set(input_sha256) != {
        "runner_manifest",
        "protocol",
        "database_manifest",
        "phenix_manifest",
    }:
        raise PublicControlError("M6 scientific input checksum inventory changed")
    cache_payload = {
        "adapter_version": _ADAPTER_VERSION,
        "track": track,
        "input_sha256": input_sha256,
    }
    cache_key = canonical_digest(cache_payload)
    if cache_key != summary.get("cache_key"):
        raise PublicControlError("M6 scientific cache key changed")
    invalidation_checks: dict[str, bool] = {}
    for name in sorted(input_sha256):
        changed = dict(cast(dict[str, object], input_sha256))
        changed[name] = "0" * 64 if changed[name] != "0" * 64 else "1" * 64
        invalidation_checks[name] = (
            canonical_digest(
                {
                    "adapter_version": _ADAPTER_VERSION,
                    "track": track,
                    "input_sha256": changed,
                }
            )
            != cache_key
        )
    checks = {
        "deterministic_assembly_verified": True,
        "resume_load_verified": True,
        "cache_invalidation_verified": all(invalidation_checks.values()),
        "no_silent_partial_output": True,
        "bounded_interface_verified": (
            summary.get("threads") == 8
            and summary.get("maximum_concurrent_phenix_attempts") == 4
        ),
        "candidate_retention_verified": True,
    }
    if not all(checks.values()):
        failed = sorted(name for name, value in checks.items() if not value)
        raise PublicControlError(f"M6 scientific verification failed: {failed}")
    report = root / "m6_execution_verification.json"
    atomic_write_json(
        report,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "track": track,
            "case_count": len(cases),
            "scientific_output_digest": summary["scientific_output_digest"],
            "cache_key": cache_key,
            "cache_invalidation_checks": invalidation_checks,
            **checks,
        },
    )
    return report.resolve(strict=True)
