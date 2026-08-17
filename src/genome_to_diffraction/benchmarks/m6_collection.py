"""Assemble two collected opaque M6 tracks at the truth-side boundary.

The collector accepts only completed checksum-fixed operational and leakage
Viper collections.  It verifies their immutable software, runner, database,
Phenix, resource, resume, cache, and partial-output evidence before joining
opaque case IDs and sequence digests to the approved protocol.  It never
changes runner ranks, LLG/TFZ annotations, candidate counts, or copy evidence.

Inputs are the two local directories produced by the reviewed HPC collector
and the frozen protocol.  The output is one ``M6CollectedEvidence`` JSON
contract for ``evaluate-m6``.  A missing file, mismatched checksum, mixed
commit, incomplete case partition, malformed assessment, or unverified runtime
aborts rather than yielding partial evidence.  Unit tests cover profile and
checksum rejection plus positive, open-set, assumption, duplicate-locus, and
edge assessment joins.
"""

import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from genome_to_diffraction.benchmarks.m6_evaluation import (
    M6CaseAssessment,
    M6CollectedEvidence,
    M6SoftwareProvenance,
)
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

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class M6CollectionRequest:
    """Truth-side assembly request for exactly two collected Viper runs."""

    protocol: Path
    operational_collection: Path
    leakage_collection: Path
    output: Path


@dataclass(frozen=True, slots=True)
class M6CollectionResult:
    """One complete evidence contract and its immutable digest."""

    evidence: M6CollectedEvidence
    output: Path
    sha256: str


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
        value: object = json.loads(
            path.resolve(strict=True).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublicControlError(f"invalid collected M6 {label}: {path}") from error
    if not isinstance(value, dict):
        raise PublicControlError(f"collected M6 {label} is not an object: {path}")
    return cast(dict[str, object], value)


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
            value: object = json.loads(line)
        except json.JSONDecodeError as error:
            raise PublicControlError(
                f"invalid collected M6 {label} line {line_number}: {path}"
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


def _load_track(root: Path, track: M6ScientificTrack) -> _CollectedTrack:
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
    rankings = _jsonl_gzip(rankings_path, "candidate rankings")
    profile = f"m6-{track}"
    run_id = manifest.get("run_id")
    expected_case_ids = m6_track_case_ids(track)
    if (
        manifest.get("site_id") != "viper-cpu"
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
    if (
        runtime.get("maximum_cpu_count") != 8
        or runtime.get("maximum_memory_gb") != 16.0
        or runtime.get("maximum_concurrent_phenix_attempts") != 4
        or runtime.get("scheduler_ceiling_hours") != 24.0
        or runtime.get("tool_runtime_timeouts") is not False
    ):
        raise PublicControlError(f"collected M6 {track} resources changed")
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


def _positive_assessment(
    case: M6CaseSpec,
    target: M6PositiveTargetSpec,
    raw: dict[str, object],
    rankings: tuple[dict[str, object], ...],
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
            "correct_family_model_retained": (
                False
                if target_row is None
                else cast(int, target_row["accepted_model_hit_count"]) > 0
            ),
            "credible_seed_recovered": bool(target_seeds),
            "supported_copy_count": max(supported) if supported else None,
            "exact_identity_sequence_sha256": None,
        }
    )


def _assessment(
    protocol: M6BenchmarkProtocol,
    case: M6CaseSpec,
    raw: dict[str, object],
    rankings: tuple[dict[str, object], ...],
) -> M6CaseAssessment:
    targets = {target.target_key: target for target in protocol.positives}
    common = {
        "case_id": case.case_id,
        "execution_status": raw["execution_status"],
        "failure_class": raw.get("failure_class"),
        "candidate_count": raw["candidate_count"],
        "retained_candidate_count": raw["retained_candidate_count"],
        "all_candidates_retained": raw["all_candidates_retained"],
    }
    if case.case_kind in {"operational_positive", "leakage_positive"}:
        return _positive_assessment(case, targets[case.target_key], raw, rankings)
    if case.case_kind in {"target_absent", "wrong_related_catalogue"}:
        return M6CaseAssessment.model_validate(
            {
                **common,
                "scientific_status": "no_exact_assignment",
                "typed_outcome": "completed_no_exact_assignment",
                "exact_identity_sequence_sha256": None,
            }
        )
    if case.case_kind == "assumption_violation":
        seed_rows = raw.get("selected_seed_results", [])
        abstained = isinstance(seed_rows, list) and not seed_rows
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
    operational = _load_track(request.operational_collection, "operational")
    leakage = _load_track(request.leakage_collection, "leakage")
    tracks = (operational, leakage)
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
    if operational_inputs.get("protocol") != sha256_file(protocol_path):
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
        _assessment(protocol, case, raw_cases[case.case_id], rankings)
        for case in protocol.cases
    )
    pixi_version = cast(str, operational.manifest["pixi_version"])
    if pixi_version.startswith("pixi "):
        pixi_version = pixi_version.removeprefix("pixi ")
    evidence = M6CollectedEvidence(
        schema_version="1.0",
        protocol_id=protocol.protocol_id,
        protocol_sha256=sha256_file(protocol_path),
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
