"""Build and validate the file-based first-copy MR review checkpoint.

The review package joins immutable hypotheses to one normalised Phaser result,
catalogue provenance, Matthews/SDS context, commands, logs, and retained result
assets.  It presents independent evidence fields without collapsing them into a
single score.  The generated approval TSV is intentionally empty and
schema-valid: a reviewer must add explicit decisions before downstream work.

Solution identifiers are content-derived from the hypothesis, result, funnel,
and result-bundle checksums.  Approval validation therefore rejects stale or
edited identifiers before any same-component copy-placement work can start.
"""

import csv
import html
import io
import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import cast

from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_digest, content_id
from genome_to_diffraction.mr.policy import (
    LEGACY_SCORE_GATE_LLG,
    LEGACY_SCORE_GATE_TFZ,
    SCORE_GATE_ID,
    SCORE_GATE_LLG,
    SCORE_GATE_OPERATOR,
    SCORE_GATE_TFZ,
    passes_provisional_score_gate,
)
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import PipelineConfig
from genome_to_diffraction.schemas.results import (
    MatthewsHypothesis,
    MrHypothesis,
    NormalisedMrResult,
    ReviewDecisionManifest,
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError
from genome_to_diffraction.time import utc_now_iso

_LOGGER = logging.getLogger("genome_to_diffraction.review.mr_seed")
_ADAPTER_VERSION = "mr-seed-review-v3"
_HYPOTHESIS_ID = re.compile(r"^mrhyp_[a-f0-9]{64}$")
_SOLUTION_ID = re.compile(r"^sol_[a-f0-9]{64}$")
_TSV_COLUMNS = (
    "rank",
    "sequence_group_rank",
    "shortlist",
    "solution_id",
    "hypothesis_id",
    "sequence_group_id",
    "source_record_ids",
    "source_loci",
    "model_id",
    "model_source",
    "model_target",
    "exact_sequence_mapping",
    "candidate_source_sequence_identity",
    "copy_count_expected",
    "placed_copy_count",
    "matthews_coefficient",
    "solvent_fraction",
    "matthews_prior",
    "matthews_physical_status",
    "sds_page_prior_label",
    "sds_page_fractional_difference",
    "llg",
    "llgi",
    "tfz",
    "score_gate_passed",
    "top_solution_packed",
    "placed_copy_count_matches",
    "inspectable_solution",
    "execution_status",
    "preliminary_credibility_class",
    "rejection_reason",
    "warnings",
    "solution_coordinate",
    "output_mtz",
    "raw_log",
    "command",
)
_APPROVAL_COLUMNS = (
    "checkpoint",
    "item_id",
    "decision",
    "reviewer",
    "reviewed_at",
    "comment",
    "override_reason",
)


class MrSeedReviewError(InputContractError):
    """MR checkpoint inputs are inconsistent or no longer immutable."""


@dataclass(frozen=True)
class MrSeedReviewRequest:
    """Inputs required to assemble one bounded first-copy review package."""

    hypotheses_jsonl: Path
    results_jsonl: Path
    result_root: Path
    funnel_manifest: Path
    sequence_groups_jsonl: Path
    source_records_jsonl: Path
    matthews_hypotheses_jsonl: Path
    pipeline_config: Path
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True)
class MrSeedReviewOutput:
    """Stable files published for a human MR-seed checkpoint."""

    package_id: str
    candidate_count: int
    review_tsv: Path
    review_html: Path
    approval_candidates_tsv: Path
    approval_template_tsv: Path
    manifest_json: Path


@dataclass(frozen=True)
class MrSeedApprovalRequest:
    """One explicit approval file and the exact package it was reviewed against."""

    package_manifest: Path
    decisions: Path
    output_json: Path
    progress: bool = True


@dataclass(frozen=True)
class MrSeedApprovalOutput:
    """Validated decisions suitable for downstream checkpoint wiring."""

    review_id: str
    approved_solution_ids: tuple[str, ...]
    output_json: Path


@dataclass(frozen=True)
class _Bundle:
    """Integrity-checked result publication for one hypothesis."""

    directory_name: str
    file_paths: Mapping[str, Path]
    file_sha256: Mapping[str, str]


@dataclass(frozen=True)
class _Candidate:
    """Fully joined evidence for one review row before ranking."""

    hypothesis: MrHypothesis
    result: NormalisedMrResult
    sequence_group: SequenceGroupRecord
    sources: tuple[SourceProteinRecord, ...]
    matthews: MatthewsHypothesis
    funnel_entry: Mapping[str, object]
    funnel_order: int
    bundle: _Bundle
    solution_id: str
    solution_identity: Mapping[str, object]


def _read_jsonl[T: BaseModel](
    path: Path,
    model: type[T],
    *,
    label: str,
    progress: bool,
    allow_empty: bool = False,
) -> tuple[T, ...]:
    if path.is_symlink():
        raise MrSeedReviewError(f"{label} must not be a symlink: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise MrSeedReviewError(f"{label} is not a regular file: {resolved}")
    records: list[T] = []
    with resolved.open(encoding="utf-8") as handle:
        iterator = tqdm(
            handle,
            desc=f"Reading {label}",
            unit="record",
            disable=not progress,
        )
        for line_number, line in enumerate(iterator, start=1):
            if not line.strip():
                continue
            try:
                records.append(model.model_validate_json(line))
            except ValidationError as error:
                raise MrSeedReviewError(
                    f"invalid {label} record at line {line_number}: {resolved}"
                ) from error
    if not records and not allow_empty:
        raise MrSeedReviewError(f"{label} is empty: {resolved}")
    return tuple(records)


def _unique_index[T](
    records: Sequence[T], key: Callable[[T], str], *, label: str
) -> dict[str, T]:
    index: dict[str, T] = {}
    for record in records:
        item_id = key(record)
        if item_id in index:
            raise MrSeedReviewError(f"duplicate {label}: {item_id}")
        index[item_id] = record
    return index


def _load_json_object(path: Path, *, label: str) -> dict[str, object]:
    if path.is_symlink():
        raise MrSeedReviewError(f"{label} must not be a symlink: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise MrSeedReviewError(f"{label} is not a regular file: {resolved}")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MrSeedReviewError(f"invalid {label}: {resolved}") from error
    if not isinstance(value, dict):
        raise MrSeedReviewError(f"{label} must contain a JSON object: {resolved}")
    return cast(dict[str, object], value)


def _funnel_entries(
    document: Mapping[str, object], hypotheses: Sequence[MrHypothesis]
) -> tuple[str, tuple[Mapping[str, object], ...]]:
    if document.get("schema_version") != "1.0":
        raise MrSeedReviewError("funnel manifest schema_version must be 1.0")
    funnel_id = document.get("funnel_id")
    entries = document.get("hypotheses")
    selected_count = document.get("selected_hypothesis_count")
    if not isinstance(funnel_id, str) or not funnel_id:
        raise MrSeedReviewError("funnel manifest has no funnel_id")
    if not isinstance(entries, list) or not all(
        isinstance(item, dict) for item in entries
    ):
        raise MrSeedReviewError("funnel manifest hypotheses must be an object array")
    typed_entries = tuple(cast(dict[str, object], item) for item in entries)
    ids = [item.get("hypothesis_id") for item in typed_entries]
    expected = [item.hypothesis_id for item in hypotheses]
    if selected_count != len(expected) or ids != expected:
        raise MrSeedReviewError(
            "funnel manifest and hypothesis JSONL identities/order differ"
        )
    if document.get("execution_status") != ExecutionStatus.COMPLETED_SUCCESS.value:
        raise MrSeedReviewError("funnel did not complete successfully")
    return funnel_id, typed_entries


def _owned_file(directory: Path, pointer: str, *, label: str) -> Path:
    relative = PurePosixPath(pointer)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise MrSeedReviewError(f"unsafe {label} path: {pointer}")
    candidate = directory.joinpath(*relative.parts)
    if candidate.is_symlink():
        raise MrSeedReviewError(f"{label} must not be a symlink: {pointer}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise MrSeedReviewError(f"missing {label}: {pointer}") from error
    if not resolved.is_file():
        raise MrSeedReviewError(f"{label} is not a regular file: {pointer}")
    try:
        resolved.relative_to(directory.resolve(strict=True))
    except ValueError as error:
        raise MrSeedReviewError(
            f"{label} escapes its result bundle: {pointer}"
        ) from error
    return resolved


def _result_bundle(
    *,
    root: Path,
    hypothesis: MrHypothesis,
    aggregate_result: NormalisedMrResult,
    progress: bool,
) -> _Bundle:
    if _HYPOTHESIS_ID.fullmatch(hypothesis.hypothesis_id) is None:
        raise MrSeedReviewError(
            f"unexpected hypothesis identifier: {hypothesis.hypothesis_id}"
        )
    directory_name = f"first_copy_phaser_{hypothesis.hypothesis_id}"
    directory = root / directory_name
    if not directory.is_dir() or directory.is_symlink():
        raise MrSeedReviewError(f"result bundle is missing: {directory_name}")
    result_jsonl = _owned_file(
        directory, "normalised_mr_result.jsonl", label="normalised result"
    )
    bundle_results = _read_jsonl(
        result_jsonl,
        NormalisedMrResult,
        label=f"{hypothesis.hypothesis_id} result",
        progress=False,
    )
    if len(bundle_results) != 1 or bundle_results[0] != aggregate_result:
        raise MrSeedReviewError(
            f"aggregate and bundle results differ: {hypothesis.hypothesis_id}"
        )
    paths: dict[str, Path] = {
        "normalised_result": result_jsonl,
        "command": _owned_file(
            directory, "phaser_command.json", label="Phaser command"
        ),
        "raw_log": _owned_file(
            directory, aggregate_result.raw_log_pointer, label="Phaser raw log"
        ),
    }
    optional = (
        ("solution_coordinate", aggregate_result.solution_coordinate_path),
        ("solution_file", aggregate_result.solution_file_path),
        ("rotation_file", aggregate_result.rotation_file_path),
        ("output_mtz", aggregate_result.output_mtz_path),
    )
    for role, pointer in optional:
        if pointer is not None:
            paths[role] = _owned_file(directory, pointer, label=role.replace("_", " "))
    checksums = {
        role: sha256_file(path, progress=progress, logger=_LOGGER)
        for role, path in paths.items()
    }
    if (
        aggregate_result.solution_coordinate_sha256 is not None
        and checksums.get("solution_coordinate")
        != aggregate_result.solution_coordinate_sha256
    ):
        raise MrSeedReviewError(
            f"solution coordinate checksum differs: {hypothesis.hypothesis_id}"
        )
    if (
        aggregate_result.output_mtz_sha256 is not None
        and checksums.get("output_mtz") != aggregate_result.output_mtz_sha256
    ):
        raise MrSeedReviewError(
            f"output MTZ checksum differs: {hypothesis.hypothesis_id}"
        )
    if aggregate_result.execution_status is ExecutionStatus.COMPLETED_HIT and (
        "solution_coordinate" not in paths or "output_mtz" not in paths
    ):
        raise MrSeedReviewError(
            f"completed hit lacks solution assets: {hypothesis.hypothesis_id}"
        )
    return _Bundle(directory_name, paths, checksums)


def _join_candidates(
    request: MrSeedReviewRequest,
) -> tuple[
    PipelineConfig,
    str,
    dict[str, str],
    tuple[_Candidate, ...],
]:
    hypotheses = _read_jsonl(
        request.hypotheses_jsonl,
        MrHypothesis,
        label="MR hypotheses",
        progress=request.progress,
    )
    results = _read_jsonl(
        request.results_jsonl,
        NormalisedMrResult,
        label="normalised MR results",
        progress=request.progress,
    )
    groups = _read_jsonl(
        request.sequence_groups_jsonl,
        SequenceGroupRecord,
        label="sequence groups",
        progress=request.progress,
    )
    sources = _read_jsonl(
        request.source_records_jsonl,
        SourceProteinRecord,
        label="source proteins",
        progress=request.progress,
    )
    matthews_rows = _read_jsonl(
        request.matthews_hypotheses_jsonl,
        MatthewsHypothesis,
        label="Matthews hypotheses",
        progress=request.progress,
    )
    config = load_contract(
        request.pipeline_config.resolve(strict=True),
        "pipeline-config",
        progress=request.progress,
    )
    if not isinstance(config, PipelineConfig):
        raise TypeError("review builder received an unexpected config model")
    hypothesis_index = _unique_index(
        hypotheses, lambda item: item.hypothesis_id, label="hypothesis ID"
    )
    result_index = _unique_index(
        results, lambda item: item.hypothesis_id, label="result hypothesis ID"
    )
    if set(hypothesis_index) != set(result_index):
        raise MrSeedReviewError("hypothesis and result identifier sets differ")
    group_index = _unique_index(
        groups, lambda item: item.sequence_group_id, label="sequence-group ID"
    )
    matthews_index = _unique_index(
        matthews_rows, lambda item: item.hypothesis_id, label="Matthews hypothesis ID"
    )
    sources_by_group: dict[str, list[SourceProteinRecord]] = {}
    for source in sources:
        sources_by_group.setdefault(source.sequence_group_id, []).append(source)
    funnel_document = _load_json_object(
        request.funnel_manifest, label="funnel manifest"
    )
    funnel_id, entries = _funnel_entries(funnel_document, hypotheses)
    input_paths = {
        "hypotheses": request.hypotheses_jsonl,
        "results": request.results_jsonl,
        "funnel_manifest": request.funnel_manifest,
        "sequence_groups": request.sequence_groups_jsonl,
        "source_records": request.source_records_jsonl,
        "matthews_hypotheses": request.matthews_hypotheses_jsonl,
        "pipeline_config": request.pipeline_config,
    }
    input_sha256 = {
        name: sha256_file(path.resolve(strict=True), progress=False)
        for name, path in input_paths.items()
    }
    if request.result_root.is_symlink():
        raise MrSeedReviewError(
            f"result root must not be a symlink: {request.result_root}"
        )
    root = request.result_root.resolve(strict=True)
    if not root.is_dir():
        raise MrSeedReviewError(f"result root is not a directory: {root}")
    candidates: list[_Candidate] = []
    for order, (hypothesis, entry) in enumerate(
        tqdm(
            zip(hypotheses, entries, strict=True),
            total=len(hypotheses),
            desc="Joining MR review evidence",
            unit="hypothesis",
            disable=not request.progress,
        ),
        start=1,
    ):
        result = result_index[hypothesis.hypothesis_id]
        group = group_index.get(hypothesis.sequence_group_id)
        if group is None:
            raise MrSeedReviewError(
                "hypothesis references unknown sequence group: "
                f"{hypothesis.hypothesis_id}"
            )
        group_sources = tuple(
            sorted(
                sources_by_group.get(group.sequence_group_id, []),
                key=lambda item: item.source_record_id,
            )
        )
        if not group_sources or len(group_sources) != group.source_record_count:
            raise MrSeedReviewError(
                f"source provenance count differs: {group.sequence_group_id}"
            )
        matthews_id = hypothesis.priority_features.get("matthews_hypothesis_id")
        if not isinstance(matthews_id, str) or matthews_id not in matthews_index:
            raise MrSeedReviewError(
                f"hypothesis has no current Matthews record: {hypothesis.hypothesis_id}"
            )
        matthews = matthews_index[matthews_id]
        if (
            matthews.crystal_id != hypothesis.crystal_id
            or matthews.sequence_group_id != hypothesis.sequence_group_id
            or matthews.copy_count != hypothesis.copy_count_expected
        ):
            raise MrSeedReviewError(
                f"Matthews provenance differs: {hypothesis.hypothesis_id}"
            )
        bundle = _result_bundle(
            root=root,
            hypothesis=hypothesis,
            aggregate_result=result,
            progress=False,
        )
        solution_identity: dict[str, object] = {
            "adapter_version": _ADAPTER_VERSION,
            "funnel_id": funnel_id,
            "funnel_manifest_sha256": input_sha256["funnel_manifest"],
            "hypothesis_id": hypothesis.hypothesis_id,
            "hypothesis_sha256": canonical_digest(hypothesis),
            "result_sha256": canonical_digest(result),
            "result_bundle_sha256": dict(sorted(bundle.file_sha256.items())),
        }
        candidates.append(
            _Candidate(
                hypothesis=hypothesis,
                result=result,
                sequence_group=group,
                sources=group_sources,
                matthews=matthews,
                funnel_entry=entry,
                funnel_order=order,
                bundle=bundle,
                solution_id=content_id("sol_", solution_identity),
                solution_identity=solution_identity,
            )
        )
    return config, funnel_id, input_sha256, tuple(candidates)


def _boolean_feature(result: NormalisedMrResult, name: str) -> bool:
    value = result.packing_summary.get(name)
    return value is True


def _score_gate(result: NormalisedMrResult) -> bool:
    raw_gate = passes_provisional_score_gate(llg=result.llg, tfz=result.tfz)
    recorded = result.packing_summary.get("score_gate_passed")
    if recorded is None:
        return raw_gate
    if not isinstance(recorded, bool):
        raise MrSeedReviewError(
            f"stored score gate is not Boolean: {result.hypothesis_id}"
        )
    recorded_llg = result.packing_summary.get("score_gate_llg_strictly_greater_than")
    recorded_tfz = result.packing_summary.get("score_gate_tfz_strictly_greater_than")
    recorded_operator = result.packing_summary.get("score_gate_operator")
    metadata = (recorded_llg, recorded_tfz, recorded_operator)
    if metadata == (LEGACY_SCORE_GATE_LLG, LEGACY_SCORE_GATE_TFZ, None):
        return raw_gate
    if metadata != (None, None, None) and metadata != (
        SCORE_GATE_LLG,
        SCORE_GATE_TFZ,
        SCORE_GATE_OPERATOR,
    ):
        raise MrSeedReviewError(
            f"unsupported stored score-gate policy: {result.hypothesis_id}"
        )
    if recorded != raw_gate:
        raise MrSeedReviewError(
            f"stored and recomputed strict score gates differ: {result.hypothesis_id}"
        )
    return raw_gate


def _inspectable_solution(candidate: _Candidate) -> bool:
    """Return whether Coot-reviewable coordinate and MTZ assets are available."""

    return (
        candidate.result.execution_status
        in {ExecutionStatus.COMPLETED_HIT, ExecutionStatus.COMPLETED_NO_HIT}
        and "solution_coordinate" in candidate.bundle.file_paths
        and "output_mtz" in candidate.bundle.file_paths
    )


def _descending(value: float | None) -> float:
    return float("inf") if value is None else -value


def _candidate_sort_key(candidate: _Candidate) -> tuple[object, ...]:
    status_rank = {
        ExecutionStatus.COMPLETED_HIT: 0,
        ExecutionStatus.COMPLETED_NO_HIT: 1,
    }.get(candidate.result.execution_status, 2)
    return (
        0 if _inspectable_solution(candidate) else 1,
        status_rank,
        0 if _score_gate(candidate.result) else 1,
        0 if _boolean_feature(candidate.result, "top_solution_packed") else 1,
        0
        if candidate.result.placed_copy_count
        == candidate.hypothesis.copy_number_to_search
        else 1,
        _descending(candidate.result.llg),
        _descending(candidate.result.tfz),
        candidate.funnel_order,
    )


def _source_locus(source: SourceProteinRecord) -> str:
    fields = [source.catalogue_id, source.original_protein_id]
    if source.locus_tag:
        fields.append(source.locus_tag)
    elif source.contig and source.start is not None and source.end is not None:
        fields.append(f"{source.contig}:{source.start}-{source.end}")
    return ":".join(fields)


def _shortlist(group_rank: int, config: PipelineConfig) -> str:
    if group_rank <= config.review.primary_shortlist_size:
        return "primary"
    if group_rank <= config.review.extended_shortlist_size:
        return "extended"
    return "full_only"


def _copy_role(
    candidate: _Candidate,
    role: str,
    destination: Path,
) -> str:
    source = candidate.bundle.file_paths[role]
    names = {
        "normalised_result": "normalised_mr_result.jsonl",
        "command": "phaser_command.json",
        "raw_log": "phaser.log",
        "solution_coordinate": "solution.pdb",
        "solution_file": "solution.sol",
        "rotation_file": "rotation.rf",
        "output_mtz": "solution.mtz",
    }
    target = destination / names[role]
    atomic_write_bytes(target, source.read_bytes())
    if sha256_file(target, progress=False) != candidate.bundle.file_sha256[role]:
        raise MrSeedReviewError(f"copied review asset checksum differs: {role}")
    return target.as_posix()


def _row(
    *,
    candidate: _Candidate,
    rank: int,
    group_rank: int,
    config: PipelineConfig,
    copied: Mapping[str, str],
) -> dict[str, object]:
    features = candidate.hypothesis.priority_features
    matthews = candidate.matthews
    warnings = list(candidate.result.parser_warnings)
    model_flags = features.get("model_quality_flags")
    if isinstance(model_flags, list):
        warnings.extend(str(item) for item in model_flags)
    if rank > config.retention.max_full_artifact_finalists and any(
        role in candidate.bundle.file_paths
        for role in ("solution_file", "rotation_file")
    ):
        warnings.append("ancillary_phaser_assets_not_copied_due_to_retention_cap")
    return {
        "rank": rank,
        "sequence_group_rank": group_rank,
        "shortlist": _shortlist(group_rank, config),
        "solution_id": candidate.solution_id,
        "hypothesis_id": candidate.hypothesis.hypothesis_id,
        "sequence_group_id": candidate.hypothesis.sequence_group_id,
        "source_record_ids": ";".join(
            item.source_record_id for item in candidate.sources
        ),
        "source_loci": ";".join(_source_locus(item) for item in candidate.sources),
        "model_id": candidate.hypothesis.model_id,
        "model_source": features.get("structural_source_class", "unknown"),
        "model_target": features.get(
            "pdb_id", features.get("coordinate_provider_accession", "")
        ),
        "exact_sequence_mapping": features.get("exact_sequence_mapping", ""),
        "candidate_source_sequence_identity": features.get(
            "candidate_source_sequence_identity", ""
        ),
        "copy_count_expected": candidate.hypothesis.copy_count_expected,
        "placed_copy_count": candidate.result.placed_copy_count,
        "matthews_coefficient": matthews.matthews_coefficient or "",
        "solvent_fraction": matthews.solvent_fraction or "",
        "matthews_prior": matthews.matthews_prior,
        "matthews_physical_status": matthews.physical_status.value,
        "sds_page_prior_label": matthews.sds_page_prior_label,
        "sds_page_fractional_difference": (
            matthews.sds_page_fractional_difference
            if matthews.sds_page_fractional_difference is not None
            else ""
        ),
        "llg": candidate.result.llg if candidate.result.llg is not None else "",
        "llgi": candidate.result.llgi if candidate.result.llgi is not None else "",
        "tfz": candidate.result.tfz if candidate.result.tfz is not None else "",
        "score_gate_passed": _score_gate(candidate.result),
        "top_solution_packed": _boolean_feature(
            candidate.result, "top_solution_packed"
        ),
        "placed_copy_count_matches": (
            candidate.result.placed_copy_count
            == candidate.hypothesis.copy_number_to_search
        ),
        "inspectable_solution": _inspectable_solution(candidate),
        "execution_status": candidate.result.execution_status.value,
        "preliminary_credibility_class": (
            candidate.result.preliminary_credibility_class or ""
        ),
        "rejection_reason": candidate.result.rejection_reason or "",
        "warnings": ";".join(dict.fromkeys(warnings)),
        "solution_coordinate": copied.get("solution_coordinate", ""),
        "output_mtz": copied.get("output_mtz", ""),
        "raw_log": copied.get("raw_log", ""),
        "command": copied.get("command", ""),
    }


def _write_tsv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=_TSV_COLUMNS, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(path, stream.getvalue())


def _write_approval_candidates(
    path: Path, rows: Sequence[Mapping[str, object]]
) -> None:
    columns = (
        "solution_id",
        "hypothesis_id",
        "rank",
        "sequence_group_rank",
        "shortlist",
        "inspectable_solution",
        "preliminary_credibility_class",
        "warnings",
        "override_reason_required_for_approval",
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=columns, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                **{column: row[column] for column in columns[:-1]},
                "override_reason_required_for_approval": not cast(
                    bool, row["inspectable_solution"]
                ),
            }
        )
    atomic_write_text(path, stream.getvalue())


def _write_empty_approval_template(path: Path) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=_APPROVAL_COLUMNS, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    atomic_write_text(path, stream.getvalue())


def _html_report(
    *, package_id: str, rows: Sequence[Mapping[str, object]], config: PipelineConfig
) -> str:
    headings = (
        "rank",
        "sequence_group_rank",
        "shortlist",
        "solution_id",
        "source_loci",
        "model_source",
        "model_target",
        "copy_count_expected",
        "llg",
        "tfz",
        "top_solution_packed",
        "inspectable_solution",
        "warnings",
        "solution_coordinate",
        "output_mtz",
        "raw_log",
        "command",
    )
    body_rows: list[str] = []
    for row in rows:
        cells: list[str] = []
        for heading in headings:
            value = str(row[heading])
            if (
                heading
                in {
                    "solution_coordinate",
                    "output_mtz",
                    "raw_log",
                    "command",
                }
                and value
            ):
                escaped = html.escape(value, quote=True)
                rendered = f'<a href="{escaped}">{escaped}</a>'
            else:
                rendered = html.escape(value)
            cells.append(f"<td>{rendered}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>MR seed checkpoint</title>
<style>
body{font-family:system-ui,sans-serif;margin:2rem;color:#17202a}
table{border-collapse:collapse;font-size:.82rem}
th,td{border:1px solid #ccd1d1;padding:.35rem;vertical-align:top}
th{background:#eef2f3;position:sticky;top:0}
code{overflow-wrap:anywhere}.note{max-width:75rem}
</style>
</head><body>
<h1>First-copy MR seed checkpoint</h1>
<p><strong>Package:</strong> <code>PACKAGE_ID</code></p>
<p class="note">Every tested hypothesis is retained. Every parsed solution with
coordinate and MTZ assets is available for Coot inspection. Rows use explicit
lexicographic evidence: inspectable assets, execution class, the provisional
LLG &gt; 50 or TFZ &gt; 5 screen, packing, placed-copy agreement, raw LLG, raw
TFZ, then immutable funnel order. The numeric screen ranks and annotates; it
does not exclude candidates or grant approval.
This ranking is not a calibrated probability. Human map and packing inspection
remains required.</p>
<p>Primary sequence-group limit: PRIMARY. Extended sequence-group limit:
EXTENDED. Full-result-asset retention limit: RETENTION.</p>
<table><thead><tr>HEADINGS</tr></thead><tbody>ROWS</tbody></table>
</body></html>
""".replace("PACKAGE_ID", html.escape(package_id))
        .replace("PRIMARY", str(config.review.primary_shortlist_size))
        .replace("EXTENDED", str(config.review.extended_shortlist_size))
        .replace("RETENTION", str(config.retention.max_full_artifact_finalists))
        .replace(
            "HEADINGS", "".join(f"<th>{html.escape(item)}</th>" for item in headings)
        )
        .replace("ROWS", "".join(body_rows))
    )


def build_mr_seed_review(request: MrSeedReviewRequest) -> MrSeedReviewOutput:
    """Assemble the bounded first-copy report and empty approval template."""

    config, funnel_id, input_sha256, joined = _join_candidates(request)
    ranked = tuple(sorted(joined, key=_candidate_sort_key))
    created_at = utc_now_iso()
    if request.output_directory.is_symlink():
        raise MrSeedReviewError(
            f"review output directory must not be a symlink: {request.output_directory}"
        )
    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise MrSeedReviewError(f"review output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    group_ranks: dict[str, int] = {}
    rows: list[dict[str, object]] = []
    item_documents: list[dict[str, object]] = []
    for rank, candidate in enumerate(
        tqdm(
            ranked,
            desc="Publishing MR review package",
            unit="candidate",
            disable=not request.progress,
        ),
        start=1,
    ):
        group_id = candidate.hypothesis.sequence_group_id
        group_rank = group_ranks.setdefault(group_id, len(group_ranks) + 1)
        candidate_assets = output / "assets" / candidate.solution_id
        copied: dict[str, str] = {}
        roles = ["normalised_result", "command"]
        if (
            _inspectable_solution(candidate)
            or config.retention.retain_all_logs
            or (group_rank <= config.review.extended_shortlist_size)
        ):
            roles.append("raw_log")
        roles.extend(
            role
            for role in ("solution_coordinate", "output_mtz")
            if role in candidate.bundle.file_paths
        )
        if rank <= config.retention.max_full_artifact_finalists:
            roles.extend(
                role
                for role in ("solution_file", "rotation_file")
                if role in candidate.bundle.file_paths
            )
        for role in roles:
            copied[role] = str(
                Path(_copy_role(candidate, role, candidate_assets)).relative_to(output)
            )
        row = _row(
            candidate=candidate,
            rank=rank,
            group_rank=group_rank,
            config=config,
            copied=copied,
        )
        rows.append(row)
        item_documents.append(
            {
                "solution_id": candidate.solution_id,
                "hypothesis_id": candidate.hypothesis.hypothesis_id,
                "sequence_group_id": group_id,
                "rank": rank,
                "sequence_group_rank": group_rank,
                "shortlist": row["shortlist"],
                "inspectable_solution": row["inspectable_solution"],
                "solution_identity": candidate.solution_identity,
                "source_bundle": candidate.bundle.directory_name,
                "source_bundle_sha256": dict(
                    sorted(candidate.bundle.file_sha256.items())
                ),
                "copied_assets": dict(sorted(copied.items())),
                "copied_asset_sha256": {
                    role: candidate.bundle.file_sha256[role] for role in sorted(copied)
                },
                "warnings": str(row["warnings"]).split(";") if row["warnings"] else [],
            }
        )
    package_identity = {
        "adapter_version": _ADAPTER_VERSION,
        "created_at": created_at,
        "funnel_id": funnel_id,
        "input_sha256": input_sha256,
        "solution_ids": [item.solution_id for item in ranked],
        "primary_shortlist_size": config.review.primary_shortlist_size,
        "extended_shortlist_size": config.review.extended_shortlist_size,
        "max_full_artifact_finalists": config.retention.max_full_artifact_finalists,
        "score_gate_policy": SCORE_GATE_ID,
    }
    package_id = content_id("reviewpkg_", package_identity)
    review_tsv = output / "mr_seed_candidates.tsv"
    review_html = output / "mr_seed_candidates.html"
    approval_candidates = output / "mr_seed_approval_candidates.tsv"
    approval_template = output / "approved_mr_seeds.tsv"
    _write_tsv(review_tsv, rows)
    _write_approval_candidates(approval_candidates, rows)
    _write_empty_approval_template(approval_template)
    atomic_write_text(
        review_html, _html_report(package_id=package_id, rows=rows, config=config)
    )
    generated_paths = {
        "review_tsv": review_tsv,
        "review_html": review_html,
        "approval_candidates_tsv": approval_candidates,
        "approval_template_tsv": approval_template,
    }
    manifest = output / "mr_seed_review_manifest.json"
    atomic_write_json(
        manifest,
        {
            "schema_version": "1.0",
            "review_package_kind": "mr_seed",
            "adapter_version": _ADAPTER_VERSION,
            "package_id": package_id,
            "package_identity": package_identity,
            "created_at": created_at,
            "checkpoint": "mr_seed",
            "ordering_policy": [
                "inspectable_solution",
                "execution_status",
                SCORE_GATE_ID,
                "top_solution_packed",
                "placed_copy_count_matches",
                "llg_descending",
                "tfz_descending",
                "immutable_funnel_order",
            ],
            "ranking_is_calibrated_probability": False,
            "numeric_screen_excludes_candidates": False,
            "approval_requires_explicit_human_decision": True,
            "score_gate": {
                "policy_id": SCORE_GATE_ID,
                "llg_strictly_greater_than": SCORE_GATE_LLG,
                "tfz_strictly_greater_than": SCORE_GATE_TFZ,
                "operator": SCORE_GATE_OPERATOR,
            },
            "candidate_count": len(rows),
            "inspectable_solution_count": sum(
                1 for row in rows if row["inspectable_solution"] is True
            ),
            "sequence_group_count": len(group_ranks),
            "primary_shortlist_size": config.review.primary_shortlist_size,
            "extended_shortlist_size": config.review.extended_shortlist_size,
            "max_full_artifact_finalists": (
                config.retention.max_full_artifact_finalists
            ),
            "items": item_documents,
            "outputs": {
                name: {
                    "path": path.relative_to(output).as_posix(),
                    "sha256": sha256_file(path, progress=False),
                }
                for name, path in generated_paths.items()
            },
            "execution_status": ExecutionStatus.COMPLETED_SUCCESS.value,
        },
    )
    _LOGGER.info(
        "MR seed review package complete",
        extra={
            "package_id": package_id,
            "candidate_count": len(rows),
            "sequence_group_count": len(group_ranks),
            "manifest": str(manifest),
        },
    )
    return MrSeedReviewOutput(
        package_id=package_id,
        candidate_count=len(rows),
        review_tsv=review_tsv,
        review_html=review_html,
        approval_candidates_tsv=approval_candidates,
        approval_template_tsv=approval_template,
        manifest_json=manifest,
    )


def _validate_package_manifest(
    path: Path, *, progress: bool
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    document = _load_json_object(path, label="MR review manifest")
    if (
        document.get("schema_version") != "1.0"
        or document.get("review_package_kind") != "mr_seed"
        or document.get("checkpoint") != "mr_seed"
        or document.get("execution_status") != ExecutionStatus.COMPLETED_SUCCESS.value
    ):
        raise MrSeedReviewError("MR review manifest has invalid checkpoint metadata")
    package_identity = document.get("package_identity")
    package_id = document.get("package_id")
    if not isinstance(package_identity, dict) or not isinstance(package_id, str):
        raise MrSeedReviewError("MR review manifest lacks package identity")
    if content_id("reviewpkg_", package_identity) != package_id:
        raise MrSeedReviewError("MR review package identifier is stale or edited")
    outputs = document.get("outputs")
    if not isinstance(outputs, dict):
        raise MrSeedReviewError("MR review manifest has no output inventory")
    root = path.resolve(strict=True).parent
    for name, raw_record in outputs.items():
        if not isinstance(name, str) or not isinstance(raw_record, dict):
            raise MrSeedReviewError("MR review output inventory is invalid")
        record = cast(dict[str, object], raw_record)
        relative = record.get("path")
        expected_sha256 = record.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected_sha256, str):
            raise MrSeedReviewError(f"MR review output record is invalid: {name}")
        owned = _owned_file(root, relative, label=f"review output {name}")
        if sha256_file(owned, progress=progress, logger=_LOGGER) != expected_sha256:
            raise MrSeedReviewError(f"MR review output checksum differs: {name}")
    raw_items = document.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise MrSeedReviewError("MR review manifest contains no review items")
    items: dict[str, dict[str, object]] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise MrSeedReviewError("MR review item is not an object")
        item = cast(dict[str, object], raw_item)
        solution_id = item.get("solution_id")
        identity = item.get("solution_identity")
        if (
            not isinstance(solution_id, str)
            or _SOLUTION_ID.fullmatch(solution_id) is None
            or not isinstance(identity, dict)
            or content_id("sol_", identity) != solution_id
        ):
            raise MrSeedReviewError("MR review solution identifier is stale or edited")
        if solution_id in items:
            raise MrSeedReviewError(f"duplicate review solution ID: {solution_id}")
        items[solution_id] = item
    return document, items


def _validate_decided_item_assets(
    *, root: Path, solution_id: str, item: Mapping[str, object], progress: bool
) -> None:
    """Verify the bounded asset bundle for one explicitly decided solution."""

    copied = item.get("copied_assets")
    copied_sha256 = item.get("copied_asset_sha256")
    if not isinstance(copied, dict) or not isinstance(copied_sha256, dict):
        raise MrSeedReviewError(f"review item has no asset inventory: {solution_id}")
    if set(copied) != set(copied_sha256):
        raise MrSeedReviewError(f"review item asset inventories differ: {solution_id}")
    for role, relative in copied.items():
        expected = copied_sha256[role]
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise MrSeedReviewError(
                f"review item asset record is invalid: {solution_id}"
            )
        owned = _owned_file(root, relative, label=f"review asset {role}")
        if sha256_file(owned, progress=progress, logger=_LOGGER) != expected:
            raise MrSeedReviewError(
                f"MR review asset checksum differs: {solution_id}/{role}"
            )


def validate_mr_seed_approvals(
    request: MrSeedApprovalRequest,
) -> MrSeedApprovalOutput:
    """Validate explicit human decisions against one current review package."""

    manifest, items = _validate_package_manifest(
        request.package_manifest, progress=request.progress
    )
    decisions_model = load_contract(
        request.decisions.resolve(strict=True),
        "review-decisions",
        progress=request.progress,
    )
    if not isinstance(decisions_model, ReviewDecisionManifest):
        raise TypeError("approval validator received unexpected decision model")
    if not decisions_model.decisions:
        raise MrSeedReviewError("MR seed approval file contains no decisions")
    created_at_raw = manifest.get("created_at")
    if not isinstance(created_at_raw, str):
        raise MrSeedReviewError("MR review manifest has no creation timestamp")
    try:
        created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise MrSeedReviewError("MR review manifest timestamp is invalid") from error
    approved: list[str] = []
    package_root = request.package_manifest.resolve(strict=True).parent
    for decision in decisions_model.decisions:
        if decision.checkpoint != "mr_seed":
            raise MrSeedReviewError(
                f"decision targets the wrong checkpoint: {decision.item_id}"
            )
        item = items.get(decision.item_id)
        if item is None:
            raise MrSeedReviewError(
                f"approval refers to a stale or unknown solution: {decision.item_id}"
            )
        _validate_decided_item_assets(
            root=package_root,
            solution_id=decision.item_id,
            item=item,
            progress=request.progress,
        )
        if decision.reviewed_at < created_at:
            raise MrSeedReviewError(
                f"decision predates the current review package: {decision.item_id}"
            )
        if decision.reviewer.upper().startswith("REPLACE"):
            raise MrSeedReviewError(
                f"decision still contains a reviewer placeholder: {decision.item_id}"
            )
        inspectable_value = item.get("inspectable_solution")
        if isinstance(inspectable_value, bool):
            inspectable = inspectable_value
        else:
            copied_assets = item.get("copied_assets")
            inspectable = isinstance(copied_assets, dict) and {
                "solution_coordinate",
                "output_mtz",
            }.issubset(copied_assets)
        if (
            decision.decision == "approve"
            and not inspectable
            and not (decision.override_reason or "").strip()
        ):
            raise MrSeedReviewError(
                "approving a seed without Coot-inspectable assets requires an "
                f"override reason: {decision.item_id}"
            )
        if decision.decision == "approve":
            approved.append(decision.item_id)
    if not approved:
        raise MrSeedReviewError("MR seed checkpoint has no approved solution")
    decisions_sha256 = sha256_file(
        request.decisions.resolve(strict=True),
        progress=request.progress,
        logger=_LOGGER,
    )
    identity = {
        "package_id": manifest["package_id"],
        "decisions_sha256": decisions_sha256,
        "decisions": decisions_model,
        "approved_solution_ids": approved,
    }
    review_id = content_id("rev_", identity)
    if request.output_json.is_symlink():
        raise MrSeedReviewError(
            f"approval output must not be a symlink: {request.output_json}"
        )
    output = request.output_json.absolute()
    atomic_write_json(
        output,
        {
            "schema_version": "1.0",
            "review_id": review_id,
            "checkpoint": "mr_seed",
            "package_id": manifest["package_id"],
            "package_manifest_sha256": sha256_file(
                request.package_manifest.resolve(strict=True), progress=False
            ),
            "decisions_sha256": decisions_sha256,
            "validated_at": utc_now_iso(),
            "decision_count": len(decisions_model.decisions),
            "approved_solution_ids": approved,
            "decisions": [
                item.model_dump(mode="json", exclude_none=False)
                for item in decisions_model.decisions
            ],
            "execution_status": ExecutionStatus.COMPLETED_SUCCESS.value,
        },
    )
    _LOGGER.info(
        "MR seed approvals valid",
        extra={
            "review_id": review_id,
            "package_id": manifest["package_id"],
            "approved_solution_count": len(approved),
            "output": str(output),
        },
    )
    return MrSeedApprovalOutput(review_id, tuple(approved), output)
