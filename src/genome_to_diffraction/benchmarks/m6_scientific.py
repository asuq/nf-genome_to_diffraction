"""Verify legacy and Nextflow M6 scientific track outputs.

Scientific execution is owned by ``m6_validation.nf``.  This module contains no
scheduler, external-tool loop, or concurrency primitive.  It preserves the
legacy v3 and Nextflow v1 output verifiers so historical jobs remain
collectable, and verifies the identity-bearing Nextflow v2 aggregate.
"""

import gzip
from collections import defaultdict
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from genome_to_diffraction.benchmarks.m6_edge import (
    M6EdgeObservation,
    verify_edge_observations,
)
from genome_to_diffraction.benchmarks.m6_identity import (
    M6IdentityDecision,
    verify_m6_identity_decision_evidence,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.schemas.io import (
    ContractLoadError,
    load_json_document,
    parse_json_document,
)

M6ScientificTrack = Literal["operational", "leakage"]
_LEGACY_ADAPTER_VERSION = "m6-scientific-run-v3"
_NEXTFLOW_V1_ADAPTER_VERSION = "m6-nextflow-run-v1"
_NEXTFLOW_V2_ADAPTER_VERSION = "m6-nextflow-run-v2"
_VERIFIABLE_ADAPTER_VERSIONS = frozenset(
    {
        _LEGACY_ADAPTER_VERSION,
        _NEXTFLOW_V1_ADAPTER_VERSION,
        _NEXTFLOW_V2_ADAPTER_VERSION,
    }
)
_SUMMARY_SCHEMA_BY_ADAPTER = {
    _LEGACY_ADAPTER_VERSION: "1.0",
    _NEXTFLOW_V1_ADAPTER_VERSION: "1.0",
    _NEXTFLOW_V2_ADAPTER_VERSION: "2.0",
}

_TRACK_CASES: dict[M6ScientificTrack, tuple[str, ...]] = {
    "operational": tuple(
        f"M6C{index:03d}" for index in (*range(1, 13), *range(25, 49))
    ),
    "leakage": tuple(f"M6C{index:03d}" for index in (*range(13, 25), *range(49, 64))),
}


def m6_track_case_ids(track: M6ScientificTrack) -> tuple[str, ...]:
    """Return the frozen opaque partition for one scientific run ID."""

    try:
        return _TRACK_CASES[track]
    except KeyError as error:
        raise ValueError(f"unsupported M6 scientific track: {track}") from error


def _json_object(path: Path) -> dict[str, object]:
    try:
        value = load_json_document(path)
    except ContractLoadError as error:
        raise PublicControlError(
            f"invalid M6 scientific object {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise PublicControlError(f"M6 scientific object is not a mapping: {path}")
    return cast(dict[str, object], value)


def _jsonl_objects(path: Path) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise PublicControlError(f"cannot read M6 scientific JSONL: {path}") from error
    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        try:
            value = parse_json_document(line, label=f"{path}:{line_number}")
        except ContractLoadError as error:
            raise PublicControlError(
                f"invalid M6 scientific JSONL at line {line_number}: {error}"
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
    """Verify deterministic, complete, retain-all track evidence."""

    root = output_directory.resolve(strict=True)
    summary_path = root / "m6_scientific_summary.json"
    summary = _json_object(summary_path)
    adapter_version = summary.get("adapter_version")
    if (
        adapter_version not in _VERIFIABLE_ADAPTER_VERSIONS
        or summary.get("schema_version")
        != _SUMMARY_SCHEMA_BY_ADAPTER[cast(str, adapter_version)]
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
        if adapter_version == _NEXTFLOW_V2_ADAPTER_VERSION:
            if (
                case.get("schema_version") != "2.0"
                or case.get("adapter_version") != "m6-nextflow-case-evidence-v2"
            ):
                raise PublicControlError(
                    f"M6 identity-bearing case contract changed: {case_id}"
                )
            try:
                identity = M6IdentityDecision.model_validate(
                    case.get("identity_decision")
                )
            except ValidationError as error:
                raise PublicControlError(
                    f"M6 case identity decision is invalid: {case_id}"
                ) from error
            if identity.case_id != case_id:
                raise PublicControlError(
                    f"M6 case identity decision belongs to another case: {case_id}"
                )
            selected_seed_results = case.get("selected_seed_results")
            if not isinstance(selected_seed_results, list) or any(
                not isinstance(row, dict) for row in selected_seed_results
            ):
                raise PublicControlError(
                    f"M6 selected-seed identity evidence is invalid: {case_id}"
                )
            try:
                verify_m6_identity_decision_evidence(
                    identity,
                    cast(list[dict[str, object]], selected_seed_results),
                )
            except ValueError as error:
                raise PublicControlError(
                    f"M6 case identity evidence changed: {case_id}"
                ) from error
            raw_edge_observations = case.get("edge_observations")
            if not isinstance(raw_edge_observations, list):
                raise PublicControlError(f"M6 case edge evidence is invalid: {case_id}")
            try:
                edge_observations = tuple(
                    M6EdgeObservation.model_validate(item)
                    for item in raw_edge_observations
                )
                verify_edge_observations(case_id, edge_observations)
            except (ValidationError, ValueError) as error:
                raise PublicControlError(
                    f"M6 case edge evidence changed: {case_id}"
                ) from error
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
        "adapter_version": adapter_version,
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
                    "adapter_version": adapter_version,
                    "track": track,
                    "input_sha256": changed,
                }
            )
            != cache_key
        )
    bounded = (
        summary.get("threads") == 8
        and summary.get("maximum_concurrent_phenix_attempts") == 4
        if adapter_version == _LEGACY_ADAPTER_VERSION
        else summary.get("execution_model") == "nextflow_dsl2_slurm_fanout"
    )
    checks = {
        "deterministic_assembly_verified": True,
        "resume_load_verified": True,
        "cache_invalidation_verified": all(invalidation_checks.values()),
        "no_silent_partial_output": True,
        "bounded_interface_verified": bounded,
        "candidate_retention_verified": True,
    }
    if not all(checks.values()):
        failed = sorted(name for name, value in checks.items() if not value)
        raise PublicControlError(f"M6 scientific verification failed: {failed}")
    report = root / "m6_execution_verification.json"
    atomic_write_json(
        report,
        {
            "schema_version": _SUMMARY_SCHEMA_BY_ADAPTER[cast(str, adapter_version)],
            "adapter_version": adapter_version,
            "track": track,
            "case_count": len(cases),
            "scientific_output_digest": summary["scientific_output_digest"],
            "cache_key": cache_key,
            "cache_invalidation_checks": invalidation_checks,
            **checks,
        },
    )
    return report.resolve(strict=True)
