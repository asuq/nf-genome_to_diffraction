"""Build the T12.5 sequence checkpoint from one completed T12 run.

The checkpoint retains every structural finalist and every scored catalogue
sequence.  Top-10 and top-25 files are bounded views for human review, not
filters or automatic decisions.  The approval template is intentionally empty.
"""

import csv
import html
import io
import json
import logging
import os
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.results import (
    BriefRefinementResult,
    SequenceMapCandidate,
    SequenceMapResult,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_LOGGER = logging.getLogger("genome_to_diffraction.review.sequence_checkpoint")
_ADAPTER_VERSION = "sequence-checkpoint-v1"
_APPROVAL_COLUMNS = (
    "checkpoint",
    "item_id",
    "decision",
    "reviewer",
    "reviewed_at",
    "comment",
    "override_reason",
)
_REVIEW_COLUMNS = (
    "seed_solution_id",
    "refinement_id",
    "candidate_rank",
    "sequence_group_id",
    "source_record_ids",
    "source_loci",
    "sequence_length",
    "raw_score",
    "score_z",
    "coverage",
    "segment_ranges",
    "final_r_work",
    "final_r_free",
    "rms_bonds",
    "rms_angles",
    "refined_model",
    "refined_mtz",
    "map_2mfo_dfc",
    "sequence_model",
    "warnings",
)
_ASSET_NAMES = (
    "brief_refine_001.pdb",
    "brief_refine_001.mtz",
    "brief_refine_2mFo-DFc.ccp4",
    "sequence_from_map.pdb",
)


class SequenceCheckpointError(InputContractError):
    """T12 evidence or finalist assets are incomplete or inconsistent."""


@dataclass(frozen=True)
class SequenceCheckpointRequest:
    """Inputs needed to render one immutable T12.5 checkpoint."""

    run_id: str
    refinement_results_jsonl: Path
    sequence_results_jsonl: Path
    stage_manifest_json: Path
    job_result_json: Path
    asset_root: Path
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True)
class SequenceCheckpointOutput:
    """Stable human-review files and their content-derived package ID."""

    package_id: str
    finalist_count: int
    top10_tsv: Path
    top25_tsv: Path
    full_tsv: Path
    review_html: Path
    approval_candidates_tsv: Path
    approval_template_tsv: Path
    manifest_json: Path


def _read_jsonl[T: BaseModel](
    path: Path,
    model: type[T],
    *,
    label: str,
) -> tuple[T, ...]:
    if path.is_symlink() or not path.is_file():
        raise SequenceCheckpointError(f"{label} is absent or unsafe")
    records: list[T] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(model.model_validate_json(line))
                except ValidationError as error:
                    raise SequenceCheckpointError(
                        f"invalid {label} record at line {line_number}"
                    ) from error
    except UnicodeError as error:
        raise SequenceCheckpointError(f"{label} is not valid UTF-8") from error
    if not records:
        raise SequenceCheckpointError(f"{label} contains no records")
    return tuple(records)


def _load_object(path: Path, label: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise SequenceCheckpointError(f"{label} is absent or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise SequenceCheckpointError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise SequenceCheckpointError(f"{label} must be a JSON object")
    return value


def _safe_asset(root: Path, seed_solution_id: str, name: str, digest: str) -> Path:
    relative = Path("artifacts") / "t12" / f"t12_{seed_solution_id}" / name
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise SequenceCheckpointError(f"T12 finalist asset is absent: {relative}")
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if resolved_root not in resolved.parents:
        raise SequenceCheckpointError(
            f"T12 finalist asset escaped its root: {relative}"
        )
    if sha256_file(path) != digest:
        raise SequenceCheckpointError(
            f"T12 finalist asset checksum differs: {relative}"
        )
    return relative


def _copy_asset(source: Path, destination: Path, digest: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        shutil.copyfile(source, temporary)
        if sha256_file(temporary) != digest:
            raise SequenceCheckpointError("copied T12 finalist asset checksum differs")
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _tsv(rows: list[dict[str, object]], columns: tuple[str, ...]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=columns, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _joined(values: tuple[str, ...]) -> str:
    return ";".join(values)


def _row_int(value: object) -> int:
    if not isinstance(value, int):
        raise SequenceCheckpointError("internal checkpoint row integer is invalid")
    return value


def _row_float(value: object) -> float:
    if not isinstance(value, int | float):
        raise SequenceCheckpointError("internal checkpoint row number is invalid")
    return float(value)


def _review_row(
    refinement: BriefRefinementResult,
    sequence: SequenceMapResult,
    candidate: SequenceMapCandidate,
    assets: dict[str, str],
) -> dict[str, object]:
    warnings = (
        tuple(refinement.warnings)
        + tuple(sequence.warnings)
        + tuple(candidate.warnings)
    )
    return {
        "seed_solution_id": refinement.seed_solution_id,
        "refinement_id": refinement.refinement_id,
        "candidate_rank": candidate.rank,
        "sequence_group_id": candidate.sequence_group_id,
        "source_record_ids": _joined(candidate.source_record_ids),
        "source_loci": _joined(candidate.source_loci),
        "sequence_length": candidate.sequence_length,
        "raw_score": candidate.raw_score,
        "score_z": "" if candidate.score_z is None else candidate.score_z,
        "coverage": "" if candidate.coverage is None else candidate.coverage,
        "segment_ranges": _joined(candidate.segment_ranges),
        "final_r_work": refinement.final_r_work,
        "final_r_free": refinement.final_r_free,
        "rms_bonds": refinement.rms_bonds,
        "rms_angles": refinement.rms_angles,
        "refined_model": assets["brief_refine_001.pdb"],
        "refined_mtz": assets["brief_refine_001.mtz"],
        "map_2mfo_dfc": assets["brief_refine_2mFo-DFc.ccp4"],
        "sequence_model": assets["sequence_from_map.pdb"],
        "warnings": _joined(warnings),
    }


def _approval_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["sequence_group_id"])].append(row)
    output: list[dict[str, object]] = []
    for group_id, evidence in grouped.items():
        best = min(
            evidence,
            key=lambda row: (
                _row_int(row["candidate_rank"]),
                -_row_float(row["raw_score"]),
            ),
        )
        output.append(
            {
                "sequence_group_id": group_id,
                "best_candidate_rank": min(
                    _row_int(row["candidate_rank"]) for row in evidence
                ),
                "best_raw_score": max(_row_float(row["raw_score"]) for row in evidence),
                "best_score_z": best["score_z"],
                "supporting_finalist_count": len(
                    {str(row["seed_solution_id"]) for row in evidence}
                ),
                "source_record_ids": best["source_record_ids"],
                "source_loci": best["source_loci"],
            }
        )
    return sorted(
        output,
        key=lambda row: (
            _row_int(row["best_candidate_rank"]),
            -_row_float(row["best_raw_score"]),
            str(row["sequence_group_id"]),
        ),
    )


def _html(rows: list[dict[str, object]], package_id: str) -> str:
    body: list[str] = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{html.escape(str(row['seed_solution_id']))}</td>"
            f"<td>{row['candidate_rank']}</td>"
            f"<td>{html.escape(str(row['sequence_group_id']))}</td>"
            f"<td>{html.escape(str(row['source_loci']))}</td>"
            f"<td>{row['raw_score']}</td>"
            f"<td>{row['score_z']}</td>"
            f"<td>{row['final_r_work']}</td>"
            f"<td>{row['final_r_free']}</td>"
            f'<td><a href="{html.escape(str(row["refined_model"]))}">PDB</a> '
            f'<a href="{html.escape(str(row["refined_mtz"]))}">MTZ</a> '
            f'<a href="{html.escape(str(row["map_2mfo_dfc"]))}">map</a></td>'
            "</tr>"
        )
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        "<title>T12.5 sequence checkpoint</title>"
        "<style>body{font-family:sans-serif;margin:2rem}table{border-collapse:collapse}"
        "th,td{border:1px solid #bbb;padding:.3rem;vertical-align:top}"
        "th{position:sticky;top:0;background:#eee}</style></head><body>"
        "<h1>T12.5 sequence checkpoint</h1>"
        f"<p>Package <code>{html.escape(package_id)}</code>. All structural finalists "
        "are retained. Sequence scores and refinement statistics are review evidence, "
        "not automatic approval or structure validation.</p>"
        "<h2>Primary top-10 view per finalist</h2><table><thead><tr>"
        "<th>Finalist</th><th>rank</th><th>sequence group</th><th>loci</th>"
        "<th>score</th><th>z</th><th>Rwork</th><th>Rfree</th><th>assets</th>"
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table></body></html>\n"
    )


def build_sequence_checkpoint(
    request: SequenceCheckpointRequest,
) -> SequenceCheckpointOutput:
    """Validate real T12 evidence and publish bounded plus full review views."""

    refinements = _read_jsonl(
        request.refinement_results_jsonl,
        BriefRefinementResult,
        label="T12 refinement results",
    )
    sequences = _read_jsonl(
        request.sequence_results_jsonl,
        SequenceMapResult,
        label="T12 sequence results",
    )
    stage = _load_object(request.stage_manifest_json, "T12 stage manifest")
    job = _load_object(request.job_result_json, "T12 job result")
    if not (
        job.get("run_id") == request.run_id
        and job.get("profile") == "t12"
        and job.get("scheduler_state") == "COMPLETED"
        and job.get("failure_class") == "success"
        and job.get("exit_code") == 0
    ):
        raise SequenceCheckpointError(
            "sequence checkpoint requires terminal successful T12 evidence"
        )
    if stage.get("seed_count") != len(refinements):
        raise SequenceCheckpointError("T12 stage and refinement counts differ")
    if len(refinements) != len(sequences):
        raise SequenceCheckpointError("refinement and sequence result counts differ")

    refinement_by_seed = {record.seed_solution_id: record for record in refinements}
    sequence_by_seed = {record.seed_solution_id: record for record in sequences}
    if len(refinement_by_seed) != len(refinements) or set(refinement_by_seed) != set(
        sequence_by_seed
    ):
        raise SequenceCheckpointError(
            "T12 result seed identities are duplicated or inconsistent"
        )

    output = request.output_directory
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    asset_inventory: dict[str, str] = {}
    iterator = tqdm(
        sorted(refinement_by_seed),
        desc="Building sequence checkpoint",
        unit="finalist",
        disable=not request.progress,
    )
    for seed in iterator:
        refinement = refinement_by_seed[seed]
        sequence = sequence_by_seed[seed]
        if refinement.execution_status not in {
            ExecutionStatus.COMPLETED_SUCCESS,
            ExecutionStatus.COMPLETED_WARNING,
        } or sequence.execution_status not in {
            ExecutionStatus.COMPLETED_HIT,
            ExecutionStatus.COMPLETED_WARNING,
        }:
            raise SequenceCheckpointError(
                "T12.5 requires completed refinement and sequence outcomes"
            )
        if refinement.refinement_id != sequence.refinement_id:
            raise SequenceCheckpointError("refinement and sequence identities differ")
        digests = {
            "brief_refine_001.pdb": refinement.refined_model_sha256,
            "brief_refine_001.mtz": refinement.refined_mtz_sha256,
            "brief_refine_2mFo-DFc.ccp4": refinement.map_sha256,
            "sequence_from_map.pdb": sequence.output_model_sha256,
        }
        if any(digest is None for digest in digests.values()):
            raise SequenceCheckpointError(
                "completed T12 result lacks an asset checksum"
            )
        assets: dict[str, str] = {}
        for name in _ASSET_NAMES:
            digest = str(digests[name])
            source_relative = _safe_asset(request.asset_root, seed, name, digest)
            package_relative = Path("assets") / seed / name
            _copy_asset(
                request.asset_root / source_relative,
                output / package_relative,
                digest,
            )
            assets[name] = package_relative.as_posix()
            asset_inventory[package_relative.as_posix()] = digest
        rows.extend(
            _review_row(refinement, sequence, candidate, assets)
            for candidate in sequence.candidates
        )

    top10_rows = [row for row in rows if _row_int(row["candidate_rank"]) <= 10]
    top25_rows = [row for row in rows if _row_int(row["candidate_rank"]) <= 25]
    approval_rows = _approval_rows(top10_rows)
    identity = {
        "adapter_version": _ADAPTER_VERSION,
        "run_id": request.run_id,
        "stage_manifest_sha256": sha256_file(request.stage_manifest_json),
        "job_result_sha256": sha256_file(request.job_result_json),
        "refinement_results_sha256": sha256_file(request.refinement_results_jsonl),
        "sequence_results_sha256": sha256_file(request.sequence_results_jsonl),
        "assets": asset_inventory,
    }
    package_id = content_id("seqreview_", identity)

    top10 = output / "sequence_candidates_top10.tsv"
    top25 = output / "sequence_candidates_top25.tsv"
    full = output / "sequence_candidates_full.tsv"
    review_html = output / "sequence_candidates.html"
    approval_candidates = output / "sequence_approval_candidates.tsv"
    approval_template = output / "approved_sequence_groups.tsv"
    manifest = output / "sequence_checkpoint_manifest.json"
    atomic_write_text(top10, _tsv(top10_rows, _REVIEW_COLUMNS))
    atomic_write_text(top25, _tsv(top25_rows, _REVIEW_COLUMNS))
    atomic_write_text(full, _tsv(rows, _REVIEW_COLUMNS))
    atomic_write_text(review_html, _html(top10_rows, package_id))
    approval_columns = (
        "sequence_group_id",
        "best_candidate_rank",
        "best_raw_score",
        "best_score_z",
        "supporting_finalist_count",
        "source_record_ids",
        "source_loci",
    )
    atomic_write_text(approval_candidates, _tsv(approval_rows, approval_columns))
    atomic_write_text(approval_template, _tsv([], _APPROVAL_COLUMNS))
    outputs = {
        path.name: sha256_file(path)
        for path in (
            top10,
            top25,
            full,
            review_html,
            approval_candidates,
            approval_template,
        )
    }
    atomic_write_json(
        manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "package_id": package_id,
            "run_id": request.run_id,
            "parent_run_id": stage.get("parent_run_id"),
            "finalist_count": len(refinements),
            "top10_row_count": len(top10_rows),
            "top25_row_count": len(top25_rows),
            "full_scored_row_count": len(rows),
            "approval_candidate_count": len(approval_rows),
            "selection_policy": "retain_all_finalists_and_all_scored_sequences",
            "automatic_approval": False,
            "identity": identity,
            "outputs": outputs,
        },
    )
    _LOGGER.info(
        "sequence checkpoint complete",
        extra={
            "package_id": package_id,
            "finalist_count": len(refinements),
            "full_scored_row_count": len(rows),
        },
    )
    return SequenceCheckpointOutput(
        package_id=package_id,
        finalist_count=len(refinements),
        top10_tsv=top10,
        top25_tsv=top25,
        full_tsv=full,
        review_html=review_html,
        approval_candidates_tsv=approval_candidates,
        approval_template_tsv=approval_template,
        manifest_json=manifest,
    )
