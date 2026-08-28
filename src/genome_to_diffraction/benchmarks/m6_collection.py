"""Assemble two collected opaque M6 tracks at the truth-side boundary.

The collector accepts only completed checksum-fixed operational and leakage
Viper collections.  It verifies their immutable software, runner, database,
Phenix, resource, resume, cache, identity-decision, and partial-output evidence
before joining opaque case IDs and sequence digests to the approved protocol
and private family truth. Corrected acceptance requires two identity-bearing v2
tracks; legacy results remain independently verifiable but cannot enter this
gate. The collector never changes runner ranks, LLG/TFZ annotations, candidate
counts, or copy evidence.

Inputs are the two local directories produced by the reviewed HPC collector
and the frozen protocol.  The output is one ``M6CollectedEvidence`` JSON
contract for ``evaluate-m6``.  A missing file, mismatched checksum, incomplete
case partition, malformed assessment, or unverified runtime aborts rather than
yielding partial evidence.  Unit tests cover profile and
checksum rejection plus positive, open-set, assumption, duplicate-locus, and
edge assessment joins.
"""

import gzip
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from genome_to_diffraction.benchmarks.m6_edge import (
    M6EdgeObservation,
    M6MatthewsEdgeEvidence,
    verify_edge_observations,
)
from genome_to_diffraction.benchmarks.m6_evaluation import (
    M6CaseAssessment,
    M6CollectedEvidence,
    M6FamilyModelEvidence,
    M6SoftwareProvenance,
)
from genome_to_diffraction.benchmarks.m6_execution import (
    M6ChildOutputEvidence,
    M6ResourceEvidence,
)
from genome_to_diffraction.benchmarks.m6_identity import M6IdentityDecision
from genome_to_diffraction.benchmarks.m6_nextflow import M6CaseEvidence
from genome_to_diffraction.benchmarks.m6_protocol import (
    M6BenchmarkProtocol,
    M6CaseSpec,
    M6PositiveTargetSpec,
    load_m6_protocol,
)
from genome_to_diffraction.benchmarks.m6_scientific import (
    M6ScientificTrack,
    m6_track_case_ids,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.schemas.base import (
    ContractModel,
    NonEmptyString,
    OperatorIdentifier,
    PositiveInt,
    Sha256Hex,
)
from genome_to_diffraction.schemas.io import (
    ContractLoadError,
    load_json_document,
    parse_json_document,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class M6CollectionRequest:
    """Truth-side assembly request for exactly two collected Viper runs."""

    protocol: Path
    private_truth_map: Path
    operational_collection: Path
    leakage_collection: Path
    output: Path


@dataclass(frozen=True, slots=True)
class M6CollectionResult:
    """One complete evidence contract and its immutable digest."""

    evidence: M6CollectedEvidence
    output: Path
    sha256: str


class _M6PrivateClusterSnapshot(ContractModel):
    """Checksum-fixed cluster-snapshot provenance at the truth boundary."""

    identity_threshold_percent: Literal[30, 70]
    file_name: NonEmptyString
    source_url: NonEmptyString
    sha256: Sha256Hex
    size_bytes: PositiveInt
    target_line_count: Literal[12]


class _M6PrivateFamily(ContractModel):
    """Verified target-family membership unavailable to the runner."""

    target_key: OperatorIdentifier
    source_pdb_entity_id: NonEmptyString
    cluster_30_line: NonEmptyString
    cluster_70_line: NonEmptyString
    cluster_30_line_sha256: Sha256Hex
    cluster_70_line_sha256: Sha256Hex
    cluster_30_entities: tuple[NonEmptyString, ...]
    cluster_70_entities: tuple[NonEmptyString, ...]
    operational_family_entities: tuple[NonEmptyString, ...]
    leakage_safe_family_entities: tuple[NonEmptyString, ...]
    frozen_allowed_30_to_70_model_count: int
    observed_allowed_30_to_70_model_count: int


class _M6PrivateCaseTruth(ContractModel):
    """One opaque case-to-truth join retained outside the runner."""

    case_id: str
    case_kind: NonEmptyString
    target_key: OperatorIdentifier
    source_pdb_id: NonEmptyString
    target_sequence_sha256: tuple[Sha256Hex, ...]
    target_opaque_loci: dict[Sha256Hex, tuple[NonEmptyString, ...]]
    expected_asu_copy_count: PositiveInt | None


class _M6PrivateTruthMap(ContractModel):
    """Complete trusted family and case truth required for corrected M6."""

    schema_version: Literal["1.1"]
    protocol_id: OperatorIdentifier
    protocol_sha256: Sha256Hex
    cluster_snapshots: tuple[_M6PrivateClusterSnapshot, ...]
    verified_families: tuple[_M6PrivateFamily, ...]
    cases: tuple[_M6PrivateCaseTruth, ...]


@dataclass(frozen=True, slots=True)
class _CollectedTrack:
    track: M6ScientificTrack
    run_id: str
    manifest: dict[str, object]
    summary: dict[str, object]
    verification: dict[str, object]
    resume: dict[str, object]
    runtime: dict[str, object]
    cases: tuple[dict[str, object], ...]
    rankings: tuple[dict[str, object], ...]
    runner_archive_sha256: str
    runner_manifest_sha256: str


def _json_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = load_json_document(path.resolve(strict=True))
    except (OSError, ContractLoadError) as error:
        raise PublicControlError(
            f"invalid collected M6 {label} {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise PublicControlError(f"collected M6 {label} is not an object: {path}")
    return cast(dict[str, object], value)


def _load_private_truth(
    path: Path,
    *,
    protocol: M6BenchmarkProtocol,
    protocol_sha256: str,
) -> _M6PrivateTruthMap:
    """Load and cross-check the trusted family/case map outside the runner."""

    resolved = path.resolve(strict=True)
    try:
        truth = _M6PrivateTruthMap.model_validate(load_json_document(resolved))
    except (
        OSError,
        ContractLoadError,
        ValidationError,
    ) as error:
        raise PublicControlError(
            f"invalid M6 private truth map {resolved}: {error}"
        ) from error
    if (
        truth.protocol_id != protocol.protocol_id
        or truth.protocol_sha256 != protocol_sha256
    ):
        raise PublicControlError("M6 private truth map uses another protocol")
    snapshots = {
        item.identity_threshold_percent: item for item in truth.cluster_snapshots
    }
    if len(snapshots) != 2 or set(snapshots) != {30, 70}:
        raise PublicControlError("M6 private truth map lacks both cluster snapshots")
    for threshold, spec in (
        (30, protocol.leakage_policy.rcsb_30_snapshot),
        (70, protocol.leakage_policy.rcsb_70_snapshot),
    ):
        snapshot = snapshots[threshold]
        if (
            snapshot.file_name != Path(spec.url).name
            or snapshot.source_url != spec.url
            or snapshot.sha256 != spec.sha256
            or snapshot.size_bytes != spec.size_bytes
            or snapshot.target_line_count != len(protocol.positives)
        ):
            raise PublicControlError(
                f"M6 private {threshold}% cluster-snapshot provenance changed"
            )
    family_by_target = {item.target_key: item for item in truth.verified_families}
    if len(family_by_target) != len(truth.verified_families) or set(
        family_by_target
    ) != {target.target_key for target in protocol.positives}:
        raise PublicControlError("M6 private family truth does not cover the positives")
    for target in protocol.positives:
        family = family_by_target[target.target_key]
        cluster_30 = set(family.cluster_30_entities)
        cluster_70 = set(family.cluster_70_entities)
        line_30_entities = family.cluster_30_line.split()
        line_70_entities = family.cluster_70_line.split()
        line_30_sha256 = hashlib.sha256(
            f"{family.cluster_30_line}\n".encode("ascii")
        ).hexdigest()
        line_70_sha256 = hashlib.sha256(
            f"{family.cluster_70_line}\n".encode("ascii")
        ).hexdigest()
        if (
            family.source_pdb_entity_id != target.source_pdb_entity_id
            or family.cluster_30_line_sha256 != target.rcsb_30_cluster_line_sha256
            or family.cluster_70_line_sha256 != target.rcsb_70_cluster_line_sha256
            or line_30_sha256 != family.cluster_30_line_sha256
            or line_70_sha256 != family.cluster_70_line_sha256
            or len(line_30_entities) != len(set(line_30_entities))
            or len(line_70_entities) != len(set(line_70_entities))
            or set(line_30_entities) != cluster_30
            or set(line_70_entities) != cluster_70
            or family.source_pdb_entity_id not in cluster_30
            or family.source_pdb_entity_id not in cluster_70
            or set(family.operational_family_entities)
            != cluster_30 - {family.source_pdb_entity_id}
            or set(family.leakage_safe_family_entities) != cluster_30 - cluster_70
            or family.frozen_allowed_30_to_70_model_count
            != target.allowed_30_to_70_model_count
            or family.observed_allowed_30_to_70_model_count
            != target.allowed_30_to_70_model_count
            or len(cluster_30 - cluster_70) != target.allowed_30_to_70_model_count
        ):
            raise PublicControlError(
                f"M6 private family truth changed for {target.target_key}"
            )
    case_by_id = {item.case_id: item for item in truth.cases}
    if len(case_by_id) != len(truth.cases) or set(case_by_id) != {
        case.case_id for case in protocol.cases
    }:
        raise PublicControlError("M6 private case truth does not cover the matrix")
    for case in protocol.cases:
        private_case = case_by_id[case.case_id]
        if (
            private_case.case_kind != case.case_kind
            or private_case.target_key != case.target_key
        ):
            raise PublicControlError(
                f"M6 private case truth changed for {case.case_id}"
            )
    return truth


def _jsonl(path: Path, label: str) -> tuple[dict[str, object], ...]:
    try:
        text = path.resolve(strict=True).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise PublicControlError(f"cannot read collected M6 {label}: {path}") from error
    return _jsonl_text(text, path, label)


def _jsonl_gzip(path: Path, label: str) -> tuple[dict[str, object], ...]:
    try:
        with gzip.open(
            path.resolve(strict=True), mode="rt", encoding="utf-8"
        ) as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        raise PublicControlError(f"cannot read collected M6 {label}: {path}") from error
    return _jsonl_text(text, path, label)


def _jsonl_text(text: str, path: Path, label: str) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            continue
        try:
            value = parse_json_document(line, label=f"{path}:{line_number}")
        except ContractLoadError as error:
            raise PublicControlError(
                f"invalid collected M6 {label} line {line_number}: {error}"
            ) from error
        if not isinstance(value, dict):
            raise PublicControlError(f"collected M6 {label} row is not an object")
        rows.append(cast(dict[str, object], value))
    return tuple(rows)


def _state_text(root: Path, name: str) -> str:
    path = root / "state" / name
    try:
        value = path.resolve(strict=True).read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as error:
        raise PublicControlError(f"missing collected M6 state: {name}") from error
    if not value:
        raise PublicControlError(f"empty collected M6 state: {name}")
    return value


def _verify_child_output_evidence(
    qualification: Path,
    track: M6ScientificTrack,
    resources: M6ResourceEvidence,
    resume_cache: dict[str, object],
) -> None:
    """Require the same complete checksum-bound outputs after cached resume."""

    baseline_path = qualification / "m6-first-child-outputs.json"
    resumed_path = qualification / "m6-resume-child-outputs.json"
    try:
        baseline = M6ChildOutputEvidence.model_validate(
            _json_object(baseline_path, "first-pass child output evidence")
        )
        resumed = M6ChildOutputEvidence.model_validate(
            _json_object(resumed_path, "cached child output evidence")
        )
        first_trace_sha256 = sha256_file(
            qualification / "m6-first-pipeline-info/trace.tsv"
        )
        resume_trace_sha256 = sha256_file(
            qualification / "m6-resume-pipeline-info/trace.tsv"
        )
    except (OSError, ValidationError) as error:
        raise PublicControlError(
            f"collected M6 {track} child output evidence is invalid"
        ) from error

    expected_tasks = tuple(
        sorted(
            (job.process, job.tag)
            for job in (*resources.jobs, *resources.controller_stages)
            if job.tag is not None
        )
    )
    observed_tasks = tuple((task.process, task.tag) for task in baseline.tasks)
    if (
        baseline.phase != "first"
        or resumed.phase != "resume"
        or baseline.trace_sha256 != first_trace_sha256
        or resumed.trace_sha256 != resume_trace_sha256
        or resumed.baseline_sha256 != sha256_file(baseline_path)
        or resume_cache.get("first_child_output_sha256") != sha256_file(baseline_path)
        or resume_cache.get("resume_child_output_sha256") != sha256_file(resumed_path)
        or baseline.task_count != resume_cache.get("first_task_count")
        or resumed.task_count != resume_cache.get("cached_resume_task_count")
        or observed_tasks != expected_tasks
        or any(
            first.process != cached.process
            or first.tag != cached.tag
            or first.task_hash != cached.task_hash
            or first.outputs != cached.outputs
            for first, cached in zip(baseline.tasks, resumed.tasks, strict=False)
        )
    ):
        raise PublicControlError(
            f"collected M6 {track} cached child output evidence changed"
        )


def _load_track(
    root: Path,
    track: M6ScientificTrack,
    expected_site_id: str,
    expected_execution_policy_id: str,
    expected_execution_policy_sha256: str,
) -> _CollectedTrack:
    resolved = root.resolve(strict=True)
    qualification = resolved / "artifacts" / "qualification"
    manifest = _json_object(resolved / "manifest.json", "collection manifest")
    summary = _json_object(
        qualification / "m6-scientific-summary.json", "scientific summary"
    )
    verification = _json_object(
        qualification / "m6-execution-verification.json", "execution verification"
    )
    resume = _json_object(qualification / "m6-resume-check.json", "resume check")
    runtime = _json_object(
        qualification / "m6-runtime-provenance.json", "runtime provenance"
    )
    cases_path = qualification / "m6-case-results.jsonl"
    rankings_path = qualification / "m6-candidate-rankings.jsonl.gz"
    cases = _jsonl(cases_path, "case results")
    if summary.get("adapter_version") == "m6-nextflow-run-v2":
        try:
            cases = tuple(
                cast(
                    dict[str, object],
                    M6CaseEvidence.model_validate(row).model_dump(mode="json"),
                )
                for row in cases
            )
        except ValidationError as error:
            raise PublicControlError(
                f"collected M6 {track} identity-bearing case evidence is invalid"
            ) from error
    rankings = _jsonl_gzip(rankings_path, "candidate rankings")
    profile = f"m6-{track}"
    run_id = manifest.get("run_id")
    expected_case_ids = m6_track_case_ids(track)
    if (
        manifest.get("site_id") != expected_site_id
        or manifest.get("profile") != profile
        or not isinstance(run_id, str)
        or not run_id.startswith(f"gtd-{profile}-")
        or summary.get("track") != track
        or summary.get("case_ids") != list(expected_case_ids)
        or verification.get("track") != track
        or runtime.get("track") != track
        or runtime.get("profile") != profile
    ):
        raise PublicControlError(f"collected M6 {track} identity is inconsistent")
    job_result = _json_object(resolved / "state/job-result.json", "job result")
    if (
        job_result.get("scheduler_state") != "COMPLETED"
        or job_result.get("exit_code") != 0
        or job_result.get("failure_class") != "success"
        or _state_text(resolved, "failure-class") != "success"
        or _state_text(resolved, "exit-code") != "0"
    ):
        raise PublicControlError(f"collected M6 {track} job did not succeed")
    case_ids = tuple(cast(str, row.get("case_id")) for row in cases)
    if case_ids != expected_case_ids:
        raise PublicControlError(f"collected M6 {track} cases are incomplete")
    outputs = summary.get("outputs")
    if not isinstance(outputs, dict):
        raise PublicControlError(f"collected M6 {track} output checksums are absent")
    output_sha = cast(dict[str, object], outputs)
    if sha256_file(cases_path) != output_sha.get("case_results") or sha256_file(
        rankings_path
    ) != output_sha.get("candidate_rankings_gzip"):
        raise PublicControlError(f"collected M6 {track} evidence checksum changed")
    inputs = summary.get("input_sha256")
    if not isinstance(inputs, dict):
        raise PublicControlError(f"collected M6 {track} input checksums are absent")
    required_verification = (
        "deterministic_assembly_verified",
        "resume_load_verified",
        "cache_invalidation_verified",
        "no_silent_partial_output",
        "bounded_interface_verified",
        "candidate_retention_verified",
    )
    if any(verification.get(name) is not True for name in required_verification):
        raise PublicControlError(f"collected M6 {track} verification is incomplete")
    if (
        resume.get("deterministic_replay_equivalent") is not True
        or resume.get("resume_equivalent") is not True
    ):
        raise PublicControlError(f"collected M6 {track} resume differs")
    if runtime.get("execution_model") == "nextflow_dsl2_slurm_fanout":
        try:
            resource_evidence = M6ResourceEvidence.model_validate(
                _json_object(
                    qualification / "m6-child-resource-evidence.json",
                    "child resource evidence",
                )
            )
        except ValueError as error:
            raise PublicControlError(
                f"collected M6 {track} child resource evidence is invalid"
            ) from error
        resume_cache = _json_object(
            qualification / "m6-resume-cache-evidence.json",
            "resume-cache evidence",
        )
        if summary.get("adapter_version") == "m6-nextflow-run-v2":
            _verify_child_output_evidence(
                qualification, track, resource_evidence, resume_cache
            )
        if (
            runtime.get("maximum_cpu_count") != 32
            or runtime.get("maximum_memory_gb") != 16.0
            or runtime.get("scheduler_ceiling_hours") != 24.0
            or runtime.get("tool_runtime_timeouts") is not False
            or runtime.get("execution_policy") != expected_execution_policy_id
            or resource_evidence.per_job_bounds_passed is not True
            or resource_evidence.execution_policy_id != expected_execution_policy_id
            or resource_evidence.execution_policy_sha256
            != expected_execution_policy_sha256
            or resource_evidence.child_job_count != runtime.get("child_job_count")
            or resource_evidence.maximum_cpu_per_job > 32
            or resource_evidence.maximum_memory_gb_per_job > 16.0
            or resource_evidence.maximum_scheduler_hours_per_job > 24.0
            or resource_evidence.peak_running_jobs != runtime.get("peak_running_jobs")
            or resource_evidence.peak_aggregate_cpus
            != runtime.get("peak_aggregate_cpu_count")
            or resource_evidence.peak_aggregate_memory_gb
            != runtime.get("peak_aggregate_memory_gb")
            or resource_evidence.peak_concurrent_phenix_jobs
            != runtime.get("maximum_concurrent_phenix_attempts")
            or any(job.status != "COMPLETED" for job in resource_evidence.jobs)
            or any(
                re.fullmatch(r"[0-9]+", job.native_job_id) is None
                for job in resource_evidence.jobs
            )
            or resume_cache.get("schema_version") != "1.0"
            or resume_cache.get("cache_mechanism") != "nextflow_resume"
            or resume_cache.get("fully_cached_resume") is not True
            or resume_cache.get("first_task_count") != resume.get("first_task_count")
            or resume_cache.get("cached_resume_task_count")
            != resume.get("cached_resume_task_count")
            or resume_cache.get("first_task_count")
            != resource_evidence.child_job_count
            + len(resource_evidence.controller_stages)
            or resume_cache.get("cached_resume_task_count")
            != resource_evidence.child_job_count
            + len(resource_evidence.controller_stages)
        ):
            raise PublicControlError(f"collected M6 {track} fan-out resources changed")
    elif (
        runtime.get("maximum_cpu_count") != 8
        or runtime.get("maximum_memory_gb") != 16.0
        or runtime.get("maximum_concurrent_phenix_attempts") != 4
        or runtime.get("scheduler_ceiling_hours") != 24.0
        or runtime.get("tool_runtime_timeouts") is not False
    ):
        raise PublicControlError(f"collected M6 {track} legacy resources changed")
    runner_archive = _state_text(resolved, "m6-runner-archive-sha256")
    runner_manifest = _state_text(resolved, "m6-runner-manifest-sha256")
    if (
        _SHA256_RE.fullmatch(runner_archive) is None
        or _SHA256_RE.fullmatch(runner_manifest) is None
    ):
        raise PublicControlError(f"collected M6 {track} runner checksum is invalid")
    if (
        inputs.get("runner_manifest") != runner_manifest
        or inputs.get("database_manifest") != manifest.get("database_manifest_sha256")
        or verification.get("scientific_output_digest")
        != summary.get("scientific_output_digest")
    ):
        raise PublicControlError(f"collected M6 {track} provenance is inconsistent")
    return _CollectedTrack(
        track=track,
        run_id=run_id,
        manifest=manifest,
        summary=summary,
        verification=verification,
        resume=resume,
        runtime=runtime,
        cases=cases,
        rankings=rankings,
        runner_archive_sha256=runner_archive,
        runner_manifest_sha256=runner_manifest,
    )


def _runner_identity_decision(
    raw: dict[str, object], case_id: str
) -> M6IdentityDecision:
    """Load the checksum-bound runner decision without inferring from case kind."""

    try:
        decision = M6IdentityDecision.model_validate(raw.get("identity_decision"))
    except ValidationError as error:
        raise PublicControlError(
            f"M6 case lacks a valid runner identity decision: {case_id}"
        ) from error
    if decision.case_id != case_id:
        raise PublicControlError(
            f"M6 runner identity decision belongs to another case: {case_id}"
        )
    return decision


def _reported_identity_digest(decision: M6IdentityDecision) -> str | None:
    """Return the sole reported digest; ambiguous/abstained decisions are null."""

    return (
        decision.candidates[0].sequence_sha256
        if decision.decision == "reported"
        else None
    )


def _runner_edge_observations(
    raw: dict[str, object], case_id: str
) -> tuple[M6EdgeObservation, ...]:
    """Load canonical runner observations without consulting the case descriptor."""

    raw_observations = raw.get("edge_observations", [])
    if not isinstance(raw_observations, list):
        raise PublicControlError(f"M6 edge observations are malformed: {case_id}")
    try:
        observations = tuple(
            M6EdgeObservation.model_validate(item) for item in raw_observations
        )
        return verify_edge_observations(case_id, observations)
    except (ValidationError, ValueError) as error:
        raise PublicControlError(
            f"M6 edge observations failed validation: {case_id}"
        ) from error


def _edge_outcome_verified(
    case: M6CaseSpec,
    private_case: _M6PrivateCaseTruth,
    observations: tuple[M6EdgeObservation, ...],
) -> bool | None:
    """Truth-join only SDS/Matthews rows; all other edges stay runner-observed."""

    edge_kinds = {
        "missing_pdb_model",
        "wrong_sds_mass",
        "non_top_matthews",
        "map_only_mtz",
        "ambiguous_columns_equivalent",
        "ambiguous_columns_conflicting",
        "remote_disabled",
        "remote_rate_limited",
        "missing_phenix",
    }
    if case.case_kind not in edge_kinds:
        if observations:
            raise PublicControlError(
                f"non-edge M6 case emitted edge evidence: {case.case_id}"
            )
        return None
    if len(observations) != 1 or observations[0].edge_kind != case.case_kind:
        return False
    observation = observations[0]
    if observation.measurement_status != "measured":
        return False
    if case.case_kind not in {"wrong_sds_mass", "non_top_matthews"}:
        return True
    evidence = observation.evidence
    if not isinstance(evidence, M6MatthewsEdgeEvidence):
        return False
    if len(private_case.target_sequence_sha256) != 1:
        raise PublicControlError(
            f"M6 Matthews edge has non-single target truth: {case.case_id}"
        )
    target_digest = private_case.target_sequence_sha256[0]
    matches = [
        item
        for item in evidence.candidate_summaries
        if item.sequence_sha256 == target_digest
    ]
    if len(matches) != 1:
        return False
    target_summary = matches[0]
    if case.case_kind == "wrong_sds_mass":
        return target_summary.sds_page_prior_label == "weak" and bool(
            target_summary.retained_hypotheses
        )
    expected_copy_count = private_case.expected_asu_copy_count
    if expected_copy_count is None:
        return False
    return any(
        item.copy_count == expected_copy_count and item.rank_within_candidate > 1
        for item in target_summary.retained_hypotheses
    )


def _family_model_evidence(
    raw: dict[str, object],
    *,
    sequence_group_id: str | None,
    family: _M6PrivateFamily,
    leakage: bool,
) -> tuple[M6FamilyModelEvidence, ...]:
    """Classify attempted PDB/entity models against private verified clusters."""

    if sequence_group_id is None:
        return ()
    raw_rows = raw.get("first_copy_results", [])
    if not isinstance(raw_rows, list) or any(
        not isinstance(row, dict) for row in raw_rows
    ):
        raise PublicControlError("M6 first-copy family evidence is malformed")
    cluster_70 = set(family.cluster_70_entities)
    verified = set(
        family.leakage_safe_family_entities
        if leakage
        else family.operational_family_entities
    )
    records: list[M6FamilyModelEvidence] = []
    seen: set[str] = set()
    for raw_row in raw_rows:
        row = cast(dict[str, object], raw_row)
        hypothesis = row.get("hypothesis")
        if not isinstance(hypothesis, dict):
            raise PublicControlError("M6 first-copy row lacks its hypothesis")
        if hypothesis.get("sequence_group_id") != sequence_group_id:
            continue
        features = hypothesis.get("priority_features")
        if not isinstance(features, dict):
            raise PublicControlError("M6 first-copy hypothesis lacks priority features")
        pdb_id = features.get("pdb_id")
        entity_id = features.get("pdb_entity_id")
        if pdb_id is None and entity_id is None:
            continue
        if (
            not isinstance(pdb_id, str)
            or re.fullmatch(r"[0-9A-Za-z]{4}", pdb_id) is None
            or isinstance(entity_id, bool)
            or not isinstance(entity_id, int)
            or entity_id < 1
        ):
            raise PublicControlError("M6 attempted PDB family identity is malformed")
        hypothesis_id = hypothesis.get("hypothesis_id")
        model_id = hypothesis.get("model_id")
        if not isinstance(hypothesis_id, str) or not isinstance(model_id, str):
            raise PublicControlError("M6 attempted family model lacks identifiers")
        if hypothesis_id in seen:
            raise PublicControlError(
                f"M6 family hypothesis is duplicated: {hypothesis_id}"
            )
        seen.add(hypothesis_id)
        entity_token = f"{pdb_id.upper()}_{entity_id}"
        classification: Literal[
            "verified_family",
            "excluded_close_family",
            "exact_deposition",
            "off_family",
        ]
        if entity_token == family.source_pdb_entity_id.upper():
            classification = "exact_deposition"
        elif entity_token in verified:
            classification = "verified_family"
        elif leakage and entity_token in cluster_70:
            classification = "excluded_close_family"
        else:
            classification = "off_family"
        records.append(
            M6FamilyModelEvidence(
                hypothesis_id=hypothesis_id,
                model_id=model_id,
                pdb_id=pdb_id.upper(),
                pdb_entity_id=entity_id,
                classification=classification,
            )
        )
    return tuple(sorted(records, key=lambda item: (item.hypothesis_id, item.model_id)))


def _positive_assessment(
    case: M6CaseSpec,
    target: M6PositiveTargetSpec,
    raw: dict[str, object],
    rankings: tuple[dict[str, object], ...],
    family: _M6PrivateFamily,
) -> M6CaseAssessment:
    matches = [
        row
        for row in rankings
        if row.get("case_id") == case.case_id
        and row.get("sequence_sha256") == target.target_sequence_sha256
    ]
    if len(matches) > 1:
        raise PublicControlError(f"M6 target ranking is duplicated: {case.case_id}")
    target_row = matches[0] if matches else None
    group_id = None if target_row is None else target_row.get("sequence_group_id")
    seed_rows = raw.get("selected_seed_results", [])
    if not isinstance(seed_rows, list) or any(
        not isinstance(row, dict) for row in seed_rows
    ):
        raise PublicControlError(f"M6 seed evidence is malformed: {case.case_id}")
    target_seeds = [
        cast(dict[str, object], row)
        for row in seed_rows
        if cast(dict[str, object], row).get("sequence_group_id") == group_id
    ]
    supported = [
        cast(int, row["best_supported_copy_count"])
        for row in target_seeds
        if isinstance(row.get("best_supported_copy_count"), int)
    ]
    identity_decision = _runner_identity_decision(raw, case.case_id)
    family_evidence = _family_model_evidence(
        raw,
        sequence_group_id=cast(str | None, group_id),
        family=family,
        leakage=case.case_kind == "leakage_positive",
    )
    return M6CaseAssessment.model_validate(
        {
            "case_id": case.case_id,
            "execution_status": raw["execution_status"],
            "scientific_status": (
                "candidate_evidence" if target_row is not None else "abstained"
            ),
            "typed_outcome": (
                "target_evidence_retained"
                if target_row is not None
                else "completed_no_target_evidence"
            ),
            "failure_class": raw.get("failure_class"),
            "candidate_count": raw["candidate_count"],
            "retained_candidate_count": raw["retained_candidate_count"],
            "all_candidates_retained": raw["all_candidates_retained"],
            "target_sequence_rank": (
                None if target_row is None else target_row["rank"]
            ),
            "correct_family_model_retained": any(
                item.classification == "verified_family" for item in family_evidence
            ),
            "credible_seed_recovered": bool(target_seeds),
            "supported_copy_count": max(supported) if supported else None,
            "runner_identity_decision": identity_decision,
            "family_model_evidence": family_evidence,
            "exact_identity_sequence_sha256": _reported_identity_digest(
                identity_decision
            ),
        }
    )


def _assessment(
    protocol: M6BenchmarkProtocol,
    case: M6CaseSpec,
    raw: dict[str, object],
    rankings: tuple[dict[str, object], ...],
    families: dict[str, _M6PrivateFamily],
    private_cases: dict[str, _M6PrivateCaseTruth],
) -> M6CaseAssessment:
    targets = {target.target_key: target for target in protocol.positives}
    identity_decision = _runner_identity_decision(raw, case.case_id)
    edge_observations = _runner_edge_observations(raw, case.case_id)
    common = {
        "case_id": case.case_id,
        "execution_status": raw["execution_status"],
        "failure_class": raw.get("failure_class"),
        "candidate_count": raw["candidate_count"],
        "retained_candidate_count": raw["retained_candidate_count"],
        "all_candidates_retained": raw["all_candidates_retained"],
        "runner_identity_decision": identity_decision,
        "exact_identity_sequence_sha256": _reported_identity_digest(identity_decision),
        "edge_observations": edge_observations,
        "edge_outcome_verified": _edge_outcome_verified(
            case,
            private_cases[case.case_id],
            edge_observations,
        ),
    }
    if case.case_kind in {"operational_positive", "leakage_positive"}:
        return _positive_assessment(
            case,
            targets[case.target_key],
            raw,
            rankings,
            families[case.target_key],
        )
    if case.case_kind in {"target_absent", "wrong_related_catalogue"}:
        reported = identity_decision.decision == "reported"
        return M6CaseAssessment.model_validate(
            {
                **common,
                "scientific_status": (
                    "candidate_evidence" if reported else "no_exact_assignment"
                ),
                "typed_outcome": (
                    "reported_open_set_identity"
                    if reported
                    else "completed_ambiguous_identity"
                    if identity_decision.decision == "ambiguous"
                    else "completed_no_exact_assignment"
                ),
            }
        )
    if case.case_kind == "assumption_violation":
        abstained = identity_decision.decision == "abstained"
        return M6CaseAssessment.model_validate(
            {
                **common,
                "scientific_status": (
                    "assumption_violation" if abstained else "candidate_evidence"
                ),
                "typed_outcome": (
                    "assumption_violation"
                    if abstained
                    else "single_component_seed_on_assumption_violation"
                ),
            }
        )
    if case.case_kind == "duplicate_locus":
        target = targets[case.target_key]
        matches = [
            row
            for row in rankings
            if row.get("case_id") == case.case_id
            and row.get("sequence_sha256") == target.target_sequence_sha256
        ]
        retained = (
            len(matches) == 1
            and isinstance(matches[0].get("source_record_count"), int)
            and cast(int, matches[0]["source_record_count"]) >= 2
        )
        return M6CaseAssessment.model_validate(
            {
                **common,
                "scientific_status": (
                    "ambiguous_multiple_loci" if retained else "not_assessed"
                ),
                "typed_outcome": (
                    "duplicate_loci_retained"
                    if retained
                    else "duplicate_locus_ambiguity_lost"
                ),
            }
        )
    return M6CaseAssessment.model_validate(
        {
            **common,
            "scientific_status": raw["scientific_status"],
            "typed_outcome": raw["typed_outcome"],
        }
    )


def collect_m6_evidence(request: M6CollectionRequest) -> M6CollectionResult:
    """Verify, truth-join, and write one complete two-run M6 evidence file."""

    protocol_path = request.protocol.resolve(strict=True)
    protocol = load_m6_protocol(protocol_path)
    protocol_sha256 = sha256_file(protocol_path)
    private_truth_path = request.private_truth_map.resolve(strict=True)
    private_truth = _load_private_truth(
        private_truth_path,
        protocol=protocol,
        protocol_sha256=protocol_sha256,
    )
    family_by_target = {
        item.target_key: item for item in private_truth.verified_families
    }
    private_case_by_id = {item.case_id: item for item in private_truth.cases}
    operational_manifest = _json_object(
        request.operational_collection.resolve(strict=True) / "manifest.json",
        "operational collection manifest",
    )
    leakage_manifest = _json_object(
        request.leakage_collection.resolve(strict=True) / "manifest.json",
        "leakage collection manifest",
    )
    site_id = operational_manifest.get("site_id")
    site_policies = {
        "viper-cpu": ("m6_nextflow_slurm_v1", "execution-nextflow-v1.yaml"),
        "marmic": (
            "m6_nextflow_slurm_marmic_v1",
            "execution-nextflow-marmic-v1.yaml",
        ),
    }
    if (
        not isinstance(site_id, str)
        or site_id not in site_policies
        or leakage_manifest.get("site_id") != site_id
    ):
        raise PublicControlError("M6 tracks must use the same reviewed HPC site")
    execution_policy_id, execution_policy_name = site_policies[site_id]
    execution_policy_path = protocol_path.with_name(execution_policy_name)
    if not execution_policy_path.is_file():
        raise PublicControlError("M6 Nextflow execution policy is absent")
    execution_policy_sha256 = sha256_file(execution_policy_path)
    operational = _load_track(
        request.operational_collection,
        "operational",
        site_id,
        execution_policy_id,
        execution_policy_sha256,
    )
    leakage = _load_track(
        request.leakage_collection,
        "leakage",
        site_id,
        execution_policy_id,
        execution_policy_sha256,
    )
    tracks = (operational, leakage)
    if any(
        track.summary.get("adapter_version") != "m6-nextflow-run-v2"
        or track.summary.get("schema_version") != "2.0"
        for track in tracks
    ):
        raise PublicControlError(
            "corrected M6 acceptance requires two identity-bearing v2 tracks"
        )
    if operational.run_id == leakage.run_id:
        raise PublicControlError("M6 requires two distinct scientific run IDs")
    common_manifest_fields = ("commit", "nf_helper_commit", "pixi_lock_sha256")
    for name in common_manifest_fields:
        if operational.manifest.get(name) != leakage.manifest.get(name):
            raise PublicControlError(f"M6 collected runs disagree on {name}")
    for name in ("runner_archive_sha256", "runner_manifest_sha256"):
        if getattr(operational, name) != getattr(leakage, name):
            raise PublicControlError(f"M6 collected runs disagree on {name}")
    operational_inputs = operational.summary.get("input_sha256")
    leakage_inputs = leakage.summary.get("input_sha256")
    if not isinstance(operational_inputs, dict) or not isinstance(leakage_inputs, dict):
        raise PublicControlError("M6 collected summaries lack input provenance")
    for name in ("protocol", "database_manifest", "phenix_manifest"):
        if operational_inputs.get(name) != leakage_inputs.get(name):
            raise PublicControlError(f"M6 collected runs disagree on {name}")
    if operational_inputs.get("protocol") != protocol_sha256:
        raise PublicControlError("M6 collected runs use another protocol")
    if operational_inputs.get("runner_manifest") != operational.runner_manifest_sha256:
        raise PublicControlError("M6 collected runner-manifest checksum disagrees")

    raw_cases = {
        cast(str, row["case_id"]): row for track in tracks for row in track.cases
    }
    if set(raw_cases) != {case.case_id for case in protocol.cases}:
        raise PublicControlError("M6 collected cases do not cover the frozen matrix")
    rankings = tuple(row for track in tracks for row in track.rankings)
    assessments = tuple(
        _assessment(
            protocol,
            case,
            raw_cases[case.case_id],
            rankings,
            family_by_target,
            private_case_by_id,
        )
        for case in protocol.cases
    )
    pixi_version = cast(str, operational.manifest["pixi_version"])
    if pixi_version.startswith("pixi "):
        pixi_version = pixi_version.removeprefix("pixi ")
    evidence = M6CollectedEvidence(
        schema_version="1.1",
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol_sha256,
        private_truth_map_sha256=sha256_file(private_truth_path),
        run_ids=(operational.run_id, leakage.run_id),
        provenance=M6SoftwareProvenance(
            source_commit=cast(str, operational.manifest["commit"]),
            nf_helper_commit=cast(str, operational.manifest["nf_helper_commit"]),
            pixi_version=pixi_version,
            pixi_lock_sha256=cast(str, operational.manifest["pixi_lock_sha256"]),
            phenix_release=cast(str, operational.summary["phenix_release"]),
            phenix_manifest_sha256=cast(str, operational_inputs["phenix_manifest"]),
            database_manifest_sha256=cast(str, operational_inputs["database_manifest"]),
            runner_archive_sha256=operational.runner_archive_sha256,
            runner_manifest_sha256=operational.runner_manifest_sha256,
            track_source_commits={
                "operational": cast(str, operational.manifest["commit"]),
                "leakage": cast(str, leakage.manifest["commit"]),
            },
        ),
        maximum_cpu_count=max(
            cast(int, track.runtime["maximum_cpu_count"]) for track in tracks
        ),
        maximum_memory_gb=max(
            cast(float, track.runtime["maximum_memory_gb"]) for track in tracks
        ),
        maximum_concurrent_phenix_attempts=max(
            cast(int, track.runtime["maximum_concurrent_phenix_attempts"])
            for track in tracks
        ),
        scheduler_ceiling_hours=max(
            cast(float, track.runtime["scheduler_ceiling_hours"]) for track in tracks
        ),
        execution_policy_id=(
            execution_policy_id
            if any(
                track.runtime.get("execution_model") == "nextflow_dsl2_slurm_fanout"
                for track in tracks
            )
            else None
        ),
        execution_policy_sha256=(
            execution_policy_sha256
            if any(
                track.runtime.get("execution_model") == "nextflow_dsl2_slurm_fanout"
                for track in tracks
            )
            else None
        ),
        child_job_count=sum(
            cast(int, track.runtime.get("child_job_count", 1)) for track in tracks
        ),
        peak_running_jobs=max(
            cast(int, track.runtime.get("peak_running_jobs", 1)) for track in tracks
        ),
        peak_aggregate_cpu_count=max(
            cast(int, track.runtime.get("peak_aggregate_cpu_count", 8))
            for track in tracks
        ),
        peak_aggregate_memory_gb=max(
            cast(float, track.runtime.get("peak_aggregate_memory_gb", 16.0))
            for track in tracks
        ),
        deterministic_replay_equivalent=all(
            track.resume["deterministic_replay_equivalent"] is True for track in tracks
        ),
        resume_equivalent=all(
            track.resume["resume_equivalent"] is True for track in tracks
        ),
        cache_invalidation_verified=all(
            track.verification["cache_invalidation_verified"] is True
            for track in tracks
        ),
        no_silent_partial_output=all(
            track.verification["no_silent_partial_output"] is True for track in tracks
        ),
        bounded_interface_verified=all(
            track.verification["bounded_interface_verified"] is True for track in tracks
        ),
        assessments=assessments,
    )
    atomic_write_json(request.output, evidence.model_dump(mode="json"))
    output = request.output.resolve(strict=True)
    return M6CollectionResult(
        evidence=evidence,
        output=output,
        sha256=sha256_file(output),
    )
