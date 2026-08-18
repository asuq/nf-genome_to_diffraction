"""Apply the trusted M6 model-exclusion transition.

The blind discovery phase emits PDB-sequence and ProstT5/Foldseek hits for
opaque catalogue groups.  This trusted transition is the only phase allowed to
join those hits to the frozen case-to-deposition mapping.  It removes the exact
deposited structure in both tracks and, in the leakage track, removes every
model with MMseqs2 amino-acid identity at least 70% and query coverage at least
80%.

ProstT5/Foldseek identity is a 3Di-search metric and is never substituted for
amino-acid identity.  A Foldseek proposal advances only when the same candidate
and source-sequence digest has a pinned MMseqs2 alignment from the direct PDB
route.  Proposals lacking that independent amino-acid mapping fail closed as
model-ineligible annotations.  Catalogue candidates are never deleted.

Inputs are normalised discovery JSONL, the immutable database manifest, the
runner-visible model policy, and the truth-facing protocol.  Outputs are an
accepted-hit JSONL for the blind MR phase, a complete rejected-model JSONL, a
ranked retain-all candidate JSONL, and a transition report.  Missing metrics,
changed tool versions, incompatible policy, or malformed records abort.  The
cache identity is the checksums of all inputs plus the adapter version.  Unit
tests cover exact-deposition removal, query-relative leakage, Foldseek
qualification, and retain-all ranking.
"""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ValidationError

from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.databases.common import tool_version
from genome_to_diffraction.ids import canonical_digest, canonical_json_text
from genome_to_diffraction.schemas.io import load_contract, load_json_document
from genome_to_diffraction.schemas.manifests import DatabaseManifest
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    SourceProteinRecord,
    StructuralSearchHit,
)

_ADAPTER_VERSION = "m6-trusted-model-policy-v2"
_DIRECT_PROVIDER = "pdb_sequence_mmseqs"
_PROSTT5_PROVIDER = "foldseek_prostt5_pdb"
_EXPECTED_PROVIDERS = frozenset({_DIRECT_PROVIDER, _PROSTT5_PROVIDER})


@dataclass(frozen=True, slots=True)
class M6ModelPolicyRequest:
    """One trusted transition from blind discovery to blind MR inputs."""

    protocol: Path
    case_id: str
    model_policy: Path
    database_manifest: Path
    sequence_groups_jsonl: Path
    source_records_jsonl: Path
    pdb_hits_jsonl: Path
    prostt5_hits_jsonl: Path
    output_directory: Path


@dataclass(frozen=True, slots=True)
class M6ModelPolicyOutput:
    """Published accepted models, rejected annotations, and candidate ranks."""

    accepted_hits: tuple[StructuralSearchHit, ...]
    accepted_hits_jsonl: Path
    rejected_models_jsonl: Path
    candidate_ranking_jsonl: Path
    report_json: Path


def _read_jsonl[T: BaseModel](path: Path, model: type[T], label: str) -> tuple[T, ...]:
    resolved = path.resolve(strict=True)
    records: list[T] = []
    with resolved.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(model.model_validate_json(line))
            except (ValidationError, ValueError) as error:
                raise PublicControlError(
                    f"invalid {label} record at line {line_number}: {resolved}"
                ) from error
    return tuple(records)


def _object(path: Path, label: str) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    try:
        value = load_json_document(resolved)
    except (OSError, ValueError) as error:
        raise PublicControlError(f"cannot read {label} {resolved}: {error}") from error
    if not isinstance(value, dict):
        raise PublicControlError(f"{label} must be a JSON object: {resolved}")
    return cast(dict[str, object], value)


def _case_source_pdb(protocol_path: Path, case_id: str) -> tuple[str, str]:
    protocol = load_m6_protocol(protocol_path)
    cases = {case.case_id: case for case in protocol.cases}
    case = cases.get(case_id)
    if case is None:
        raise PublicControlError(f"M6 model policy received an unknown case: {case_id}")
    targets = {target.target_key: target.source.pdb_id for target in protocol.positives}
    targets.update(
        {
            control.target_key: control.source.pdb_id
            for control in protocol.assumption_controls
        }
    )
    return targets[case.target_key], case.case_kind


def _mmseqs_version(database_manifest: Path) -> tuple[str, str]:
    manifest = load_contract(database_manifest, "database-manifest", progress=False)
    if not isinstance(manifest, DatabaseManifest):
        raise AssertionError("database-manifest loader returned an unexpected model")
    resources = tuple(
        resource for resource in manifest.resources if resource.name == "pdb_sequences"
    )
    if len(resources) != 1 or resources[0].prepared_with.tool != "mmseqs":
        raise PublicControlError(
            "M6 requires exactly one MMseqs2-qualified PDB sequence resource"
        )
    prepared = resources[0].prepared_with.version
    observed = tool_version("mmseqs", arguments=("version",))
    if observed != prepared or observed != "18.8cc5c":
        raise PublicControlError(
            "M6 leakage policy requires the pinned MMseqs2 18.8cc5c runtime"
        )
    return observed, resources[0].database_id


def _target_sequence_sha256(hit: StructuralSearchHit) -> str:
    value = hit.raw_metrics.get("target_sequence_sha256")
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PublicControlError(
            f"M6 structural hit lacks a target sequence digest: {hit.hit_id}"
        )
    return value


def _complete_alignment(hit: StructuralSearchHit) -> bool:
    return all(
        value is not None
        for value in (
            hit.query_start,
            hit.query_end,
            hit.target_start,
            hit.target_end,
            hit.aligned_length,
            hit.query_coverage,
            hit.target_coverage,
            hit.sequence_identity,
        )
    )


def _alignment_key(hit: StructuralSearchHit) -> tuple[object, ...]:
    return (
        -(hit.sequence_identity or 0.0),
        -(hit.query_coverage or 0.0),
        hit.evalue if hit.evalue is not None else float("inf"),
        -(hit.bits or 0.0),
        hit.provider_rank,
        hit.hit_id,
    )


def _qualified_foldseek_hit(
    hit: StructuralSearchHit,
    direct_by_sequence: dict[tuple[str, str], StructuralSearchHit],
) -> StructuralSearchHit | None:
    source_sha256 = _target_sequence_sha256(hit)
    direct = direct_by_sequence.get((hit.sequence_group_id, source_sha256))
    if direct is None or not _complete_alignment(direct):
        return None
    raw_metrics = dict(hit.raw_metrics)
    raw_metrics.update(
        {
            "amino_acid_alignment_provider": _DIRECT_PROVIDER,
            "amino_acid_alignment_hit_id": direct.hit_id,
            "amino_acid_identity_fraction": direct.sequence_identity,
            "amino_acid_query_coverage": direct.query_coverage,
            "amino_acid_target_coverage": direct.target_coverage,
        }
    )
    return hit.model_copy(
        update={
            "query_start": direct.query_start,
            "query_end": direct.query_end,
            "target_start": direct.target_start,
            "target_end": direct.target_end,
            "aligned_length": direct.aligned_length,
            "query_coverage": direct.query_coverage,
            "target_coverage": direct.target_coverage,
            "sequence_identity": direct.sequence_identity,
            "raw_metrics": raw_metrics,
        }
    )


def _candidate_sort_key(
    group: SequenceGroupRecord,
    hits: tuple[StructuralSearchHit, ...],
) -> tuple[object, ...]:
    if not hits:
        return (1, 1, 1.0, 1.0, float("inf"), 0.0, group.sequence_group_id)
    best = min(hits, key=_alignment_key)
    exact = _target_sequence_sha256(best) == group.sha256
    return (
        0,
        0 if exact else 1,
        -(best.sequence_identity or 0.0),
        -(best.query_coverage or 0.0),
        best.evalue if best.evalue is not None else float("inf"),
        -(best.bits or 0.0),
        group.sequence_group_id,
    )


def apply_m6_model_policy(request: M6ModelPolicyRequest) -> M6ModelPolicyOutput:
    """Enforce exact-deposition and leakage exclusions without candidate loss."""

    source_pdb, case_kind = _case_source_pdb(request.protocol, request.case_id)
    policy = _object(request.model_policy, "M6 model policy")
    if (
        policy.get("schema_version") != "1.0"
        or policy.get("applies_to_all_model_routes") is not True
        or policy.get("retain_rejected_model_annotations") is not True
        or policy.get("candidate_policy") != "retain_all"
        or policy.get("score_policy") != "llg_tfz_annotations_only"
        or policy.get("exact_deposition_removed_by_trusted_transition") is not True
    ):
        raise PublicControlError("M6 runner model policy changed or is incomplete")
    mode = policy.get("mode")
    if mode not in {"operational", "query_relative_leakage"}:
        raise PublicControlError("M6 model policy mode is invalid")
    if (case_kind == "leakage_positive") != (mode == "query_relative_leakage"):
        raise PublicControlError("M6 case and model-policy modes disagree")
    identity_threshold = policy.get("maximum_model_identity_fraction")
    coverage_threshold = policy.get("minimum_exclusion_coverage_fraction")
    if mode == "query_relative_leakage":
        if identity_threshold != 0.7 or coverage_threshold != 0.8:
            raise PublicControlError("M6 leakage thresholds differ from the protocol")
    else:
        identity_threshold = None
        coverage_threshold = None

    mmseqs_version, sequence_database_id = _mmseqs_version(request.database_manifest)
    groups = _read_jsonl(
        request.sequence_groups_jsonl, SequenceGroupRecord, "sequence group"
    )
    sources = _read_jsonl(
        request.source_records_jsonl, SourceProteinRecord, "source protein"
    )
    if not groups:
        raise PublicControlError("M6 catalogue import produced no candidates")
    group_by_id = {group.sequence_group_id: group for group in groups}
    if len(group_by_id) != len(groups):
        raise PublicControlError("M6 catalogue contains duplicate sequence groups")
    source_counts = Counter(source.sequence_group_id for source in sources)
    if set(source_counts) - set(group_by_id):
        raise PublicControlError("M6 source records reference an unknown candidate")

    direct_hits = _read_jsonl(
        request.pdb_hits_jsonl, StructuralSearchHit, "PDB sequence hit"
    )
    foldseek_hits = _read_jsonl(
        request.prostt5_hits_jsonl, StructuralSearchHit, "ProstT5/Foldseek hit"
    )
    if any(hit.provider != _DIRECT_PROVIDER for hit in direct_hits) or any(
        hit.provider != _PROSTT5_PROVIDER for hit in foldseek_hits
    ):
        raise PublicControlError("M6 discovery hit providers differ from the policy")
    if any(
        hit.sequence_group_id not in group_by_id
        for hit in (*direct_hits, *foldseek_hits)
    ):
        raise PublicControlError("M6 discovery hit references an unknown candidate")
    if any(hit.database_id != sequence_database_id for hit in direct_hits):
        raise PublicControlError("M6 PDB hits use another sequence database")
    if any(not _complete_alignment(hit) for hit in direct_hits):
        raise PublicControlError("M6 direct PDB hit lacks a complete MMseqs2 alignment")

    direct_by_sequence: dict[tuple[str, str], StructuralSearchHit] = {}
    for hit in sorted(direct_hits, key=_alignment_key):
        direct_by_sequence.setdefault(
            (hit.sequence_group_id, _target_sequence_sha256(hit)), hit
        )

    accepted: list[StructuralSearchHit] = []
    rejected: list[dict[str, object]] = []
    rejected_by_group: Counter[str] = Counter()
    rejection_reasons: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    for raw_hit in (*direct_hits, *foldseek_hits):
        hit = raw_hit
        reason: str | None = None
        if hit.provider == _PROSTT5_PROVIDER:
            if hit.raw_metrics.get("coordinate_mapping_status") == "unavailable":
                reason = "coordinate_mapping_unavailable"
            else:
                qualified = _qualified_foldseek_hit(hit, direct_by_sequence)
                if qualified is None:
                    reason = "amino_acid_alignment_unavailable"
                else:
                    hit = qualified
        if reason is None and (hit.pdb_id or "").upper() == source_pdb.upper():
            reason = "exact_deposited_coordinates"
        if reason is None and mode == "query_relative_leakage":
            identity = hit.sequence_identity
            coverage = hit.query_coverage
            if identity is None or coverage is None:
                raise PublicControlError(
                    f"M6 leakage hit lacks amino-acid metrics: {hit.hit_id}"
                )
            if identity >= cast(float, identity_threshold) and coverage >= cast(
                float, coverage_threshold
            ):
                reason = "query_relative_leakage"
        if reason is None:
            accepted.append(hit)
            route_counts[hit.provider] += 1
            continue
        rejected_by_group[hit.sequence_group_id] += 1
        rejection_reasons[reason] += 1
        rejected.append(
            {
                "schema_version": "1.0",
                "case_id": request.case_id,
                "hit": hit.model_dump(mode="json"),
                "rejection_reason": reason,
                "retained_as_annotation": True,
            }
        )

    accepted.sort(
        key=lambda hit: (hit.sequence_group_id, *_alignment_key(hit), hit.provider)
    )
    accepted_by_group: dict[str, list[StructuralSearchHit]] = defaultdict(list)
    for hit in accepted:
        accepted_by_group[hit.sequence_group_id].append(hit)
    ranked_groups = sorted(
        groups,
        key=lambda group: _candidate_sort_key(
            group, tuple(accepted_by_group.get(group.sequence_group_id, ()))
        ),
    )
    ranking_rows = [
        {
            "schema_version": "1.0",
            "case_id": request.case_id,
            "rank": rank,
            "sequence_group_id": group.sequence_group_id,
            "sequence_sha256": group.sha256,
            "source_record_count": source_counts[group.sequence_group_id],
            "accepted_model_hit_count": len(
                accepted_by_group.get(group.sequence_group_id, ())
            ),
            "rejected_model_hit_count": rejected_by_group[group.sequence_group_id],
            "all_candidate_records_retained": True,
        }
        for rank, group in enumerate(ranked_groups, start=1)
    ]

    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise PublicControlError(f"M6 model-policy output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    accepted_path = output / "accepted_structural_hits.jsonl"
    rejected_path = output / "rejected_model_annotations.jsonl"
    ranking_path = output / "candidate_ranking.jsonl"
    report_path = output / "model_policy_report.json"
    atomic_write_text(
        accepted_path,
        "".join(f"{canonical_json_text(hit)}\n" for hit in accepted),
    )
    atomic_write_text(
        rejected_path,
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rejected),
    )
    atomic_write_text(
        ranking_path,
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in ranking_rows),
    )
    input_sha256 = {
        "protocol": sha256_file(request.protocol),
        "model_policy": sha256_file(request.model_policy),
        "database_manifest": sha256_file(request.database_manifest),
        "sequence_groups": sha256_file(request.sequence_groups_jsonl),
        "source_records": sha256_file(request.source_records_jsonl),
        "pdb_hits": sha256_file(request.pdb_hits_jsonl),
        "prostt5_hits": sha256_file(request.prostt5_hits_jsonl),
    }
    atomic_write_json(
        report_path,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "case_id": request.case_id,
            "mode": mode,
            "sequence_tool": "MMseqs2",
            "sequence_tool_version": mmseqs_version,
            "identity_exclusion_fraction": identity_threshold,
            "coverage_exclusion_fraction": coverage_threshold,
            "exact_deposition_excluded": True,
            "all_model_routes_checked": True,
            "candidate_count": len(groups),
            "retained_candidate_count": len(groups),
            "all_candidates_retained": True,
            "model_proposal_count": len(direct_hits) + len(foldseek_hits),
            "accepted_model_count": len(accepted),
            "rejected_model_count": len(rejected),
            "accepted_route_counts": dict(sorted(route_counts.items())),
            "rejection_reason_counts": dict(sorted(rejection_reasons.items())),
            "score_policy": "LLG/TFZ_are_ranking_annotations_only",
            "input_sha256": input_sha256,
            "cache_key": canonical_digest(
                {"adapter_version": _ADAPTER_VERSION, "input_sha256": input_sha256}
            ),
            "outputs": {
                "accepted_structural_hits": sha256_file(accepted_path),
                "rejected_model_annotations": sha256_file(rejected_path),
                "candidate_ranking": sha256_file(ranking_path),
            },
        },
    )
    return M6ModelPolicyOutput(
        accepted_hits=tuple(accepted),
        accepted_hits_jsonl=accepted_path,
        rejected_models_jsonl=rejected_path,
        candidate_ranking_jsonl=ranking_path,
        report_json=report_path,
    )
