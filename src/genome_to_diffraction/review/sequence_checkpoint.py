"""Build the T12.5 sequence checkpoint from one completed T12 run.

The checkpoint retains every structural finalist and every scored catalogue
sequence.  Top-10 and top-25 files are bounded views for human review, not
filters or automatic decisions.  The approval template is intentionally empty.
"""

import csv
import html
import io
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
from genome_to_diffraction.matthews.enumerate import (
    PRIOR_BACKEND,
    dynamic_copy_counts,
    physical_status,
    prior_score,
)
from genome_to_diffraction.matthews.probability import probability_distribution
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.schemas.results import (
    BriefRefinementResult,
    MtzPreflightRecord,
    SequenceGroupRecord,
    SequenceMapCandidate,
    SequenceMapResult,
    SourceProteinRecord,
)
from genome_to_diffraction.schemas.v2.diffraction import (
    DiffractionSelection,
    FreeRIdentity,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_LOGGER = logging.getLogger("genome_to_diffraction.review.sequence_checkpoint")
_ADAPTER_VERSION = "sequence-checkpoint-v3-mattprob"
_LIVE_ADAPTER_VERSION = "live-sequence-checkpoint-v3-mattprob"
_MATTHEWS_RETAINED_COUNT = 4
_MATTHEWS_MIN_SOLVENT_FRACTION = 0.10
_MATTHEWS_MAX_SOLVENT_FRACTION = 0.90
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
    "original_protein_ids",
    "locus_tags",
    "gene_names",
    "products",
    "annotation_providers",
    "sequence_length",
    "raw_score",
    "score_z",
    "coverage",
    "segment_ranges",
    "final_r_work",
    "final_r_free",
    "rms_bonds",
    "rms_angles",
    "refined_copy_count",
    "matthews_rank_at_refined_copy",
    "matthews_status_at_refined_copy",
    "matthews_coefficient_at_refined_copy",
    "solvent_fraction_at_refined_copy",
    "matthews_top_copy_counts",
    "refined_model",
    "refined_mtz",
    "map_2mfo_dfc",
    "map_mfo_dfc",
    "sequence_assignment_hypothesis",
    "warnings",
)
_ASSET_NAMES = (
    "brief_refine_001.pdb",
    "brief_refine_001.mtz",
    "brief_refine_2mFo-DFc.ccp4",
    "brief_refine_mFo-DFc.ccp4",
    "sequence_from_map.pdb",
)
_ANNOTATION_COLUMNS = (
    "sequence_group_id",
    "source_record_id",
    "catalogue_id",
    "original_protein_id",
    "locus_tag",
    "gene_name",
    "product",
    "description",
    "contig",
    "start",
    "end",
    "strand",
    "annotation_provider",
    "quality_flags",
)
_MATTHEWS_COLUMNS = (
    "crystal_id",
    "sequence_group_id",
    "copy_count",
    "sequence_mass_da",
    "sequence_mass_lower_da",
    "sequence_mass_upper_da",
    "matthews_coefficient",
    "matthews_coefficient_lower",
    "matthews_coefficient_upper",
    "solvent_fraction",
    "solvent_fraction_lower",
    "solvent_fraction_upper",
    "matthews_prior",
    "physical_status",
    "rank_within_candidate",
    "retained",
    "asu_volume_a3",
    "space_group",
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
    sequence_groups_jsonl: Path
    source_records_jsonl: Path
    preflight_jsonl: Path
    asset_root: Path
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True)
class LiveSequenceCheckpointRequest:
    """Normal-workflow T12 directories used to render one checkpoint."""

    stage_bundle: Path
    candidate_result_directories: tuple[Path, ...]
    output_directory: Path
    crystal_id: str | None = None
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
    gene_annotations_tsv: Path
    matthews_context_tsv: Path
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
        value = load_json_document(path)
    except ContractLoadError as error:
        raise SequenceCheckpointError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise SequenceCheckpointError(f"{label} must be a JSON object")
    return value


def _load_scientific_context(
    *,
    stage: dict[str, object],
    sequence_groups_jsonl: Path,
    source_records_jsonl: Path,
    preflight_jsonl: Path,
) -> tuple[
    dict[str, SequenceGroupRecord],
    dict[str, SourceProteinRecord],
    MtzPreflightRecord,
]:
    """Load checksum-bound catalogue annotation and crystal geometry."""

    paths = {
        "sequence_groups_sha256": sequence_groups_jsonl,
        "source_records_sha256": source_records_jsonl,
        "preflight_sha256": preflight_jsonl,
    }
    for digest_key, path in paths.items():
        expected = stage.get(digest_key)
        if not isinstance(expected, str) or sha256_file(path) != expected:
            raise SequenceCheckpointError(
                f"T12 scientific context checksum differs: {digest_key}"
            )
    groups = _read_jsonl(
        sequence_groups_jsonl,
        SequenceGroupRecord,
        label="T12 sequence groups",
    )
    sources = _read_jsonl(
        source_records_jsonl,
        SourceProteinRecord,
        label="T12 source records",
    )
    preflights = _read_jsonl(
        preflight_jsonl,
        MtzPreflightRecord,
        label="T12 MTZ preflight",
    )
    group_by_id = {group.sequence_group_id: group for group in groups}
    source_by_id = {source.source_record_id: source for source in sources}
    if len(group_by_id) != len(groups) or len(source_by_id) != len(sources):
        raise SequenceCheckpointError(
            "T12 catalogue context has duplicated stable identities"
        )
    mtz_sha256 = stage.get("parent_mtz_sha256") or stage.get("diffraction_mtz_sha256")
    if not isinstance(mtz_sha256, str):
        raise SequenceCheckpointError("T12 stage lacks diffraction MTZ provenance")
    matching_preflights = [
        preflight for preflight in preflights if preflight.mtz_sha256 == mtz_sha256
    ]
    if len(matching_preflights) != 1:
        raise SequenceCheckpointError(
            "T12 preflight does not uniquely match the diffraction MTZ"
        )
    return group_by_id, source_by_id, matching_preflights[0]


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


def _optional_join(values: tuple[str | None, ...]) -> str:
    return ";".join(value or "" for value in values)


def _matthews_rows(
    group: SequenceGroupRecord,
    preflight: MtzPreflightRecord,
) -> list[dict[str, object]]:
    """Calculate the configured broad physical copy-number prior for review."""

    mass_lower = group.molecular_mass_da or group.molecular_mass_lower_da
    mass_upper = group.molecular_mass_da or group.molecular_mass_upper_da
    if mass_lower is None or mass_upper is None:
        raise SequenceCheckpointError(
            f"sequence group lacks usable molecular mass: {group.sequence_group_id}"
        )
    copy_counts, _ = dynamic_copy_counts(
        v_asu_a3=preflight.asu_volume_a3,
        mass_lower_da=mass_lower,
        mass_upper_da=mass_upper,
        minimum_solvent_fraction=_MATTHEWS_MIN_SOLVENT_FRACTION,
        maximum_solvent_fraction=_MATTHEWS_MAX_SOLVENT_FRACTION,
    )
    empirical = probability_distribution(preflight.resolution_high_a)
    rows: list[dict[str, object]] = []
    for copy_count in copy_counts:
        row: dict[str, object] = {
            "crystal_id": preflight.crystal_id,
            "sequence_group_id": group.sequence_group_id,
            "copy_count": copy_count,
            "sequence_mass_da": "",
            "sequence_mass_lower_da": "",
            "sequence_mass_upper_da": "",
            "matthews_coefficient": "",
            "matthews_coefficient_lower": "",
            "matthews_coefficient_upper": "",
            "solvent_fraction": "",
            "solvent_fraction_lower": "",
            "solvent_fraction_upper": "",
            "asu_volume_a3": preflight.asu_volume_a3,
            "space_group": preflight.space_group,
        }
        if group.molecular_mass_da is not None:
            coefficient = preflight.asu_volume_a3 / (
                copy_count * group.molecular_mass_da
            )
            solvent = 1.0 - 1.23 / coefficient
            row.update(
                {
                    "sequence_mass_da": group.molecular_mass_da,
                    "matthews_coefficient": coefficient,
                    "solvent_fraction": solvent,
                    "matthews_prior": prior_score(
                        solvent,
                        resolution_high_a=preflight.resolution_high_a,
                        copy_count=copy_count,
                    ),
                    "physical_status": physical_status(
                        solvent,
                        solvent,
                        minimum=_MATTHEWS_MIN_SOLVENT_FRACTION,
                        maximum=_MATTHEWS_MAX_SOLVENT_FRACTION,
                    ).value,
                }
            )
        elif (
            group.molecular_mass_lower_da is not None
            and group.molecular_mass_upper_da is not None
        ):
            coefficient_lower = preflight.asu_volume_a3 / (
                copy_count * group.molecular_mass_upper_da
            )
            coefficient_upper = preflight.asu_volume_a3 / (
                copy_count * group.molecular_mass_lower_da
            )
            solvent_lower = 1.0 - 1.23 / coefficient_lower
            solvent_upper = 1.0 - 1.23 / coefficient_upper
            row.update(
                {
                    "sequence_mass_lower_da": group.molecular_mass_lower_da,
                    "sequence_mass_upper_da": group.molecular_mass_upper_da,
                    "matthews_coefficient_lower": coefficient_lower,
                    "matthews_coefficient_upper": coefficient_upper,
                    "solvent_fraction_lower": solvent_lower,
                    "solvent_fraction_upper": solvent_upper,
                    "matthews_prior": empirical.single_component_interval_prior(
                        copy_count,
                        solvent_lower,
                        solvent_upper,
                    ),
                    "physical_status": physical_status(
                        solvent_lower,
                        solvent_upper,
                        minimum=_MATTHEWS_MIN_SOLVENT_FRACTION,
                        maximum=_MATTHEWS_MAX_SOLVENT_FRACTION,
                    ).value,
                }
            )
        rows.append(row)

    status_order = {"plausible": 0, "review": 1, "impossible": 2}
    ranked = sorted(
        rows,
        key=lambda row: (
            status_order[str(row["physical_status"])],
            -_row_float(row["matthews_prior"]),
            _row_int(row["copy_count"]),
        ),
    )
    for rank, row in enumerate(ranked, start=1):
        row["rank_within_candidate"] = rank
        row["retained"] = rank <= _MATTHEWS_RETAINED_COUNT
    return ranked


def _annotation_row(record: SourceProteinRecord) -> dict[str, object]:
    return {
        "sequence_group_id": record.sequence_group_id,
        "source_record_id": record.source_record_id,
        "catalogue_id": record.catalogue_id,
        "original_protein_id": record.original_protein_id,
        "locus_tag": record.locus_tag or "",
        "gene_name": record.gene_name or "",
        "product": record.product or "",
        "description": record.description or "",
        "contig": record.contig or "",
        "start": record.start or "",
        "end": record.end or "",
        "strand": record.strand or "",
        "annotation_provider": record.source_annotation_provider,
        "quality_flags": _joined(record.quality_flags),
    }


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
    source_records: tuple[SourceProteinRecord, ...],
    matthews: list[dict[str, object]],
) -> dict[str, object]:
    warnings = (
        tuple(refinement.warnings)
        + tuple(sequence.warnings)
        + tuple(candidate.warnings)
    )
    at_refined_copy = next(
        row for row in matthews if row["copy_count"] == refinement.input_copy_count
    )
    top_copy_counts = tuple(
        str(row["copy_count"]) for row in matthews if bool(row["retained"])
    )
    coefficient = at_refined_copy["matthews_coefficient"]
    if coefficient == "":
        coefficient = (
            f"{at_refined_copy['matthews_coefficient_lower']}.."
            f"{at_refined_copy['matthews_coefficient_upper']}"
        )
    solvent = at_refined_copy["solvent_fraction"]
    if solvent == "":
        solvent = (
            f"{at_refined_copy['solvent_fraction_lower']}.."
            f"{at_refined_copy['solvent_fraction_upper']}"
        )
    return {
        "seed_solution_id": refinement.seed_solution_id,
        "refinement_id": refinement.refinement_id,
        "candidate_rank": candidate.rank,
        "sequence_group_id": candidate.sequence_group_id,
        "source_record_ids": _joined(candidate.source_record_ids),
        "source_loci": _joined(candidate.source_loci),
        "original_protein_ids": _joined(
            tuple(record.original_protein_id for record in source_records)
        ),
        "locus_tags": _optional_join(
            tuple(record.locus_tag for record in source_records)
        ),
        "gene_names": _optional_join(
            tuple(record.gene_name for record in source_records)
        ),
        "products": _optional_join(tuple(record.product for record in source_records)),
        "annotation_providers": _joined(
            tuple(record.source_annotation_provider for record in source_records)
        ),
        "sequence_length": candidate.sequence_length,
        "raw_score": candidate.raw_score,
        "score_z": "" if candidate.score_z is None else candidate.score_z,
        "coverage": "" if candidate.coverage is None else candidate.coverage,
        "segment_ranges": _joined(candidate.segment_ranges),
        "final_r_work": refinement.final_r_work,
        "final_r_free": refinement.final_r_free,
        "rms_bonds": refinement.rms_bonds,
        "rms_angles": refinement.rms_angles,
        "refined_copy_count": refinement.input_copy_count,
        "matthews_rank_at_refined_copy": at_refined_copy["rank_within_candidate"],
        "matthews_status_at_refined_copy": at_refined_copy["physical_status"],
        "matthews_coefficient_at_refined_copy": coefficient,
        "solvent_fraction_at_refined_copy": solvent,
        "matthews_top_copy_counts": _joined(top_copy_counts),
        "refined_model": assets["brief_refine_001.pdb"],
        "refined_mtz": assets["brief_refine_001.mtz"],
        "map_2mfo_dfc": assets["brief_refine_2mFo-DFc.ccp4"],
        "map_mfo_dfc": assets["brief_refine_mFo-DFc.ccp4"],
        "sequence_assignment_hypothesis": assets["sequence_from_map.pdb"],
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
                "original_protein_ids": best["original_protein_ids"],
                "locus_tags": best["locus_tags"],
                "gene_names": best["gene_names"],
                "products": best["products"],
                "annotation_providers": best["annotation_providers"],
                "refined_copy_count": best["refined_copy_count"],
                "matthews_rank_at_refined_copy": best["matthews_rank_at_refined_copy"],
                "matthews_status_at_refined_copy": best[
                    "matthews_status_at_refined_copy"
                ],
                "matthews_coefficient_at_refined_copy": best[
                    "matthews_coefficient_at_refined_copy"
                ],
                "solvent_fraction_at_refined_copy": best[
                    "solvent_fraction_at_refined_copy"
                ],
                "matthews_top_copy_counts": best["matthews_top_copy_counts"],
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
            f"<td>{html.escape(str(row['locus_tags']))}</td>"
            f"<td>{html.escape(str(row['gene_names']))}</td>"
            f"<td>{html.escape(str(row['products']))}</td>"
            f"<td>{row['raw_score']}</td>"
            f"<td>{row['score_z']}</td>"
            f"<td>{row['final_r_work']}</td>"
            f"<td>{row['final_r_free']}</td>"
            f"<td>{row['refined_copy_count']}</td>"
            f"<td>{html.escape(str(row['matthews_top_copy_counts']))}</td>"
            f"<td>{html.escape(str(row['matthews_status_at_refined_copy']))}</td>"
            f'<td><a href="{html.escape(str(row["refined_model"]))}">PDB</a> '
            f'<a href="{html.escape(str(row["refined_mtz"]))}">MTZ</a> '
            f'<a href="{html.escape(str(row["map_2mfo_dfc"]))}">2mFo-DFc</a> '
            f'<a href="{html.escape(str(row["map_mfo_dfc"]))}">mFo-DFc</a> '
            f'<a href="{html.escape(str(row["sequence_assignment_hypothesis"]))}">'
            "sequence-assignment hypothesis</a></td>"
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
        "not automatic approval or structure validation. Matthews coefficients are "
        "physical copy-number priors, not proof that ASU = nA or that the crystal "
        "contains only one protein species. The sequence-assignment PDB is derived "
        "from the refined model and 2mFo-DFc map; it is not independently refined. "
        "All compatible genome annotations are retained rather than selecting one "
        "duplicate locus. Finalists without scored sequence rows remain explicit in "
        "the manifest and retained evidence.</p>"
        "<h2>Primary top-10 view per finalist</h2><table><thead><tr>"
        "<th>Finalist</th><th>rank</th><th>sequence group</th><th>locus tags</th>"
        "<th>genes</th><th>products</th><th>score</th><th>z</th><th>Rwork</th>"
        "<th>Rfree</th><th>refined copies</th><th>Matthews top copies</th>"
        "<th>status at refined copies</th><th>assets</th>"
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table></body></html>\n"
    )


def _safe_relative_file(
    root: Path,
    relative: str,
    *,
    label: str,
    digest: str | None = None,
) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise SequenceCheckpointError(f"{label} path is unsafe")
    if root.is_symlink() or not root.is_dir():
        raise SequenceCheckpointError(f"{label} root is absent or unsafe")
    root_resolved = root.resolve(strict=True)
    path = root / candidate
    if path.is_symlink() or not path.is_file():
        raise SequenceCheckpointError(f"{label} is absent or unsafe")
    resolved = path.resolve(strict=True)
    if root_resolved not in resolved.parents:
        raise SequenceCheckpointError(f"{label} escaped its root")
    if digest is not None and sha256_file(path) != digest:
        raise SequenceCheckpointError(f"{label} checksum differs")
    return path


def _read_single_result[T: BaseModel](
    directory: Path,
    basename: str,
    model: type[T],
    *,
    label: str,
) -> tuple[T, Path, Path]:
    json_path = _safe_relative_file(directory, f"{basename}.json", label=label)
    jsonl_path = _safe_relative_file(directory, f"{basename}.jsonl", label=label)
    records = _read_jsonl(jsonl_path, model, label=label)
    if len(records) != 1:
        raise SequenceCheckpointError(f"{label} must contain exactly one record")
    try:
        json_record = model.model_validate_json(json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as error:
        raise SequenceCheckpointError(f"invalid {label} JSON") from error
    if json_record.model_dump(mode="json") != records[0].model_dump(mode="json"):
        raise SequenceCheckpointError(f"{label} JSON and JSONL differ")
    return records[0], json_path, jsonl_path


def _finalist_seed_ids(path: Path) -> tuple[str, ...]:
    if path.is_symlink() or not path.is_file():
        raise SequenceCheckpointError("T12 finalists are absent or unsafe")
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames is None or "seed_solution_id" not in reader.fieldnames:
                raise SequenceCheckpointError("T12 finalists lack seed_solution_id")
            seeds = tuple(row["seed_solution_id"] for row in reader)
    except (OSError, UnicodeError) as error:
        raise SequenceCheckpointError("T12 finalists are unreadable") from error
    if not seeds or len(set(seeds)) != len(seeds) or any(not seed for seed in seeds):
        raise SequenceCheckpointError("T12 finalist identities are empty or duplicated")
    return seeds


def _register_source(
    sources: dict[str, tuple[Path, str]],
    destination: Path,
    source: Path,
    digest: str,
) -> None:
    relative = destination.as_posix()
    existing = sources.get(relative)
    if existing is not None and existing != (source, digest):
        raise SequenceCheckpointError("checkpoint evidence destination is duplicated")
    sources[relative] = (source, digest)


def _publish_sequence_checkpoint(
    *,
    run_id: str,
    refinements: tuple[BriefRefinementResult, ...],
    sequences: tuple[SequenceMapResult, ...],
    stage: dict[str, object],
    identity_base: dict[str, object],
    asset_sources: dict[str, dict[str, tuple[Path, str]]],
    retained_sources: dict[str, tuple[Path, str]],
    sequence_groups: dict[str, SequenceGroupRecord],
    source_records: dict[str, SourceProteinRecord],
    preflight: MtzPreflightRecord,
    output: Path,
    adapter_version: str,
    progress: bool,
    require_all_completed: bool,
    extra_manifest: dict[str, object] | None = None,
) -> SequenceCheckpointOutput:
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

    output.mkdir(parents=True, exist_ok=True)
    retained_inventory: dict[str, str] = {}
    for relative, (source, digest) in sorted(retained_sources.items()):
        destination = Path(relative)
        if destination.is_absolute() or ".." in destination.parts:
            raise SequenceCheckpointError("checkpoint evidence destination is unsafe")
        _copy_asset(source, output / destination, digest)
        retained_inventory[relative] = digest

    rows: list[dict[str, object]] = []
    reviewed_group_ids: set[str] = set()
    matthews_by_group: dict[str, list[dict[str, object]]] = {}
    asset_inventory: dict[str, str] = {}
    candidate_outcomes: list[dict[str, object]] = []
    reviewable_finalists = 0
    successful_refinement_statuses = {
        ExecutionStatus.COMPLETED_SUCCESS,
        ExecutionStatus.COMPLETED_WARNING,
    }
    scored_sequence_statuses = {
        ExecutionStatus.COMPLETED_HIT,
        ExecutionStatus.COMPLETED_WARNING,
    }
    iterator = tqdm(
        sorted(refinement_by_seed),
        desc="Building sequence checkpoint",
        unit="finalist",
        disable=not progress,
    )
    for seed in iterator:
        refinement = refinement_by_seed[seed]
        sequence = sequence_by_seed[seed]
        refinement_completed = (
            refinement.execution_status in successful_refinement_statuses
        )
        sequence_scored = sequence.execution_status in scored_sequence_statuses
        if require_all_completed and not (refinement_completed and sequence_scored):
            raise SequenceCheckpointError(
                "T12.5 requires completed refinement and sequence outcomes"
            )
        if refinement.refinement_id != sequence.refinement_id:
            raise SequenceCheckpointError("refinement and sequence identities differ")
        if not refinement_completed and sequence.execution_status != (
            ExecutionStatus.SKIPPED_INELIGIBLE
        ):
            raise SequenceCheckpointError(
                "failed refinement must have a skipped sequence outcome"
            )
        if sequence.execution_status == ExecutionStatus.COMPLETED_HIT and not (
            sequence.candidates
        ):
            raise SequenceCheckpointError("completed-hit sequence result has no rows")
        if sequence.candidates and not sequence_scored:
            raise SequenceCheckpointError(
                "unscored sequence outcome contains candidate rows"
            )

        digests = {
            "brief_refine_001.pdb": refinement.refined_model_sha256,
            "brief_refine_001.mtz": refinement.refined_mtz_sha256,
            "brief_refine_2mFo-DFc.ccp4": refinement.map_sha256,
            "brief_refine_mFo-DFc.ccp4": refinement.difference_map_sha256,
            "sequence_from_map.pdb": sequence.output_model_sha256,
        }
        required_names: list[str] = []
        if refinement_completed:
            required_names.extend(_ASSET_NAMES[:4])
        if sequence.output_model_sha256 is not None:
            required_names.append(_ASSET_NAMES[4])
        if sequence.candidates and _ASSET_NAMES[4] not in required_names:
            raise SequenceCheckpointError(
                "scored sequence result lacks its output-model checksum"
            )
        if any(digests[name] is None for name in required_names):
            raise SequenceCheckpointError(
                "completed T12 result lacks an asset checksum"
            )
        package_assets: dict[str, str] = {}
        for name in required_names:
            digest = str(digests[name])
            try:
                source, recorded_digest = asset_sources[seed][name]
            except KeyError as error:
                raise SequenceCheckpointError(
                    f"T12 finalist asset is absent: {seed}/{name}"
                ) from error
            if recorded_digest != digest:
                raise SequenceCheckpointError(
                    f"T12 finalist asset checksum differs: {seed}/{name}"
                )
            package_relative = Path("assets") / seed / name
            _copy_asset(source, output / package_relative, digest)
            package_assets[name] = package_relative.as_posix()
            asset_inventory[package_relative.as_posix()] = digest
        if sequence.candidates:
            if set(package_assets) != set(_ASSET_NAMES):
                raise SequenceCheckpointError(
                    "scored sequence result lacks complete Coot assets"
                )
            reviewable_finalists += 1
            for candidate in sequence.candidates:
                try:
                    group = sequence_groups[candidate.sequence_group_id]
                    candidate_sources = tuple(
                        source_records[source_id]
                        for source_id in candidate.source_record_ids
                    )
                except KeyError as error:
                    raise SequenceCheckpointError(
                        "scored sequence lacks its catalogue or annotation record"
                    ) from error
                all_group_source_ids = {
                    source.source_record_id
                    for source in source_records.values()
                    if source.sequence_group_id == candidate.sequence_group_id
                }
                if (
                    not candidate_sources
                    or any(
                        source.sequence_group_id != candidate.sequence_group_id
                        for source in candidate_sources
                    )
                    or set(candidate.source_record_ids) != all_group_source_ids
                    or group.source_record_count != len(all_group_source_ids)
                    or group.length_aa != candidate.sequence_length
                ):
                    raise SequenceCheckpointError(
                        "scored sequence and genome annotation crosswalk differ"
                    )
                reviewed_group_ids.add(candidate.sequence_group_id)
                if candidate.sequence_group_id not in matthews_by_group:
                    matthews_by_group[candidate.sequence_group_id] = _matthews_rows(
                        group, preflight
                    )
                matthews = matthews_by_group[candidate.sequence_group_id]
                rows.append(
                    _review_row(
                        refinement,
                        sequence,
                        candidate,
                        package_assets,
                        candidate_sources,
                        matthews,
                    )
                )
        candidate_outcomes.append(
            {
                "seed_solution_id": seed,
                "refinement_id": refinement.refinement_id,
                "refinement_execution_status": refinement.execution_status.value,
                "sequence_execution_status": sequence.execution_status.value,
                "scored_group_count": sequence.scored_group_count,
                "review_row_count": len(sequence.candidates),
                "retained": True,
            }
        )

    top10_rows = [row for row in rows if _row_int(row["candidate_rank"]) <= 10]
    top25_rows = [row for row in rows if _row_int(row["candidate_rank"]) <= 25]
    approval_rows = _approval_rows(top10_rows)
    identity = {**identity_base, "assets": asset_inventory}
    if retained_inventory:
        identity["retained_evidence"] = retained_inventory
    package_id = content_id("seqreview_", identity)

    top10 = output / "sequence_candidates_top10.tsv"
    top25 = output / "sequence_candidates_top25.tsv"
    full = output / "sequence_candidates_full.tsv"
    review_html = output / "sequence_candidates.html"
    approval_candidates = output / "sequence_approval_candidates.tsv"
    approval_template = output / "approved_sequence_groups.tsv"
    gene_annotations = output / "sequence_gene_annotations.tsv"
    matthews_context = output / "sequence_matthews_context.tsv"
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
        "original_protein_ids",
        "locus_tags",
        "gene_names",
        "products",
        "annotation_providers",
        "refined_copy_count",
        "matthews_rank_at_refined_copy",
        "matthews_status_at_refined_copy",
        "matthews_coefficient_at_refined_copy",
        "solvent_fraction_at_refined_copy",
        "matthews_top_copy_counts",
    )
    atomic_write_text(approval_candidates, _tsv(approval_rows, approval_columns))
    atomic_write_text(approval_template, _tsv([], _APPROVAL_COLUMNS))
    annotation_rows = [
        _annotation_row(record)
        for record in sorted(
            source_records.values(),
            key=lambda record: (record.sequence_group_id, record.source_record_id),
        )
        if record.sequence_group_id in reviewed_group_ids
    ]
    context_rows = sorted(
        (row for group_id in reviewed_group_ids for row in matthews_by_group[group_id]),
        key=lambda row: (
            str(row["sequence_group_id"]),
            _row_int(row["copy_count"]),
        ),
    )
    atomic_write_text(gene_annotations, _tsv(annotation_rows, _ANNOTATION_COLUMNS))
    atomic_write_text(matthews_context, _tsv(context_rows, _MATTHEWS_COLUMNS))
    outputs = {
        path.name: sha256_file(path)
        for path in (
            top10,
            top25,
            full,
            review_html,
            approval_candidates,
            approval_template,
            gene_annotations,
            matthews_context,
        )
    }
    manifest_document: dict[str, object] = {
        "schema_version": "1.0",
        "adapter_version": adapter_version,
        "package_id": package_id,
        "run_id": run_id,
        "parent_run_id": stage.get("parent_run_id"),
        "finalist_count": len(refinements),
        "retained_finalist_count": len(refinements),
        "reviewable_finalist_count": reviewable_finalists,
        "top10_row_count": len(top10_rows),
        "top25_row_count": len(top25_rows),
        "full_scored_row_count": len(rows),
        "approval_candidate_count": len(approval_rows),
        "selection_policy": "retain_all_finalists_and_all_scored_sequences",
        "automatic_approval": False,
        "crystal_context": {
            "crystal_id": preflight.crystal_id,
            "crystal_id_role": "experimental_diffraction_dataset_identifier",
            "mtz_sha256": preflight.mtz_sha256,
            "space_group": preflight.space_group,
            "asu_volume_a3": preflight.asu_volume_a3,
        },
        "matthews_policy": {
            "prior_backend": PRIOR_BACKEND,
            "copy_count_policy": "dynamic_by_asu_sequence_mass_and_solvent_bounds",
            "static_copy_count_ceiling": None,
            "retained_count": _MATTHEWS_RETAINED_COUNT,
            "min_solvent_fraction": _MATTHEWS_MIN_SOLVENT_FRACTION,
            "max_solvent_fraction": _MATTHEWS_MAX_SOLVENT_FRACTION,
            "is_physical_prior_not_asu_identity_proof": True,
            "asu_equals_nA_assumption_status": "unknown_pending_human_review",
        },
        "sequence_assignment_model_role": (
            "map_derived_sequence_assignment_hypothesis_not_independently_refined"
        ),
        "gene_annotation_row_count": len(annotation_rows),
        "matthews_context_row_count": len(context_rows),
        "candidate_outcomes": candidate_outcomes,
        "identity": identity,
        "outputs": outputs,
    }
    if extra_manifest is not None:
        manifest_document.update(extra_manifest)
    atomic_write_json(manifest, manifest_document)
    _LOGGER.info(
        "sequence checkpoint complete",
        extra={
            "package_id": package_id,
            "finalist_count": len(refinements),
            "reviewable_finalist_count": reviewable_finalists,
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
        gene_annotations_tsv=gene_annotations,
        matthews_context_tsv=matthews_context,
        manifest_json=manifest,
    )


def build_sequence_checkpoint(
    request: SequenceCheckpointRequest,
) -> SequenceCheckpointOutput:
    """Validate scheduled T12 evidence and publish bounded plus full views."""

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
    sequence_groups, source_records, preflight = _load_scientific_context(
        stage=stage,
        sequence_groups_jsonl=request.sequence_groups_jsonl,
        source_records_jsonl=request.source_records_jsonl,
        preflight_jsonl=request.preflight_jsonl,
    )
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
    asset_sources: dict[str, dict[str, tuple[Path, str]]] = {}
    sequence_by_seed = {sequence.seed_solution_id: sequence for sequence in sequences}
    for refinement in refinements:
        try:
            sequence = sequence_by_seed[refinement.seed_solution_id]
        except KeyError as error:
            raise SequenceCheckpointError(
                "T12 result seed identities are inconsistent"
            ) from error
        digests = {
            "brief_refine_001.pdb": refinement.refined_model_sha256,
            "brief_refine_001.mtz": refinement.refined_mtz_sha256,
            "brief_refine_2mFo-DFc.ccp4": refinement.map_sha256,
            "brief_refine_mFo-DFc.ccp4": refinement.difference_map_sha256,
            "sequence_from_map.pdb": sequence.output_model_sha256,
        }
        if any(digest is None for digest in digests.values()):
            raise SequenceCheckpointError(
                "completed T12 result lacks an asset checksum"
            )
        asset_sources[refinement.seed_solution_id] = {
            name: (
                request.asset_root
                / _safe_asset(
                    request.asset_root,
                    refinement.seed_solution_id,
                    name,
                    str(digest),
                ),
                str(digest),
            )
            for name, digest in digests.items()
        }
    identity: dict[str, object] = {
        "adapter_version": _ADAPTER_VERSION,
        "run_id": request.run_id,
        "stage_manifest_sha256": sha256_file(request.stage_manifest_json),
        "job_result_sha256": sha256_file(request.job_result_json),
        "refinement_results_sha256": sha256_file(request.refinement_results_jsonl),
        "sequence_results_sha256": sha256_file(request.sequence_results_jsonl),
        "sequence_groups_sha256": sha256_file(request.sequence_groups_jsonl),
        "source_records_sha256": sha256_file(request.source_records_jsonl),
        "preflight_sha256": sha256_file(request.preflight_jsonl),
    }
    retained_sources = {
        "provenance/sequence_groups.jsonl": (
            request.sequence_groups_jsonl,
            identity["sequence_groups_sha256"],
        ),
        "provenance/source_records.jsonl": (
            request.source_records_jsonl,
            identity["source_records_sha256"],
        ),
        "provenance/preflight.jsonl": (
            request.preflight_jsonl,
            identity["preflight_sha256"],
        ),
    }
    return _publish_sequence_checkpoint(
        run_id=request.run_id,
        refinements=refinements,
        sequences=sequences,
        stage=stage,
        identity_base=identity,
        asset_sources=asset_sources,
        retained_sources={
            relative: (source, str(digest))
            for relative, (source, digest) in retained_sources.items()
        },
        sequence_groups=sequence_groups,
        source_records=source_records,
        preflight=preflight,
        output=request.output_directory,
        adapter_version=_ADAPTER_VERSION,
        progress=request.progress,
        require_all_completed=True,
    )


def build_live_sequence_checkpoint(
    request: LiveSequenceCheckpointRequest,
) -> SequenceCheckpointOutput:
    """Build T12.5 directly from checksum-authenticated normal-workflow outputs."""

    stage_root = request.stage_bundle
    stage_manifest = _safe_relative_file(
        stage_root,
        "t12_stage_manifest.json",
        label="normal T12 stage manifest",
    )
    stage = _load_object(stage_manifest, "normal T12 stage manifest")
    expected_profile = (
        "phase3_reviewed_single_component"
        if request.crystal_id is not None
        else "normal_workflow"
    )
    if not (
        stage.get("profile") == expected_profile
        and stage.get("execution_status") == ExecutionStatus.COMPLETED_SUCCESS.value
        and stage.get("all_approved_seeds_retained") is True
        and stage.get("numeric_score_filter_applied") is False
        and stage.get("failed_addition_proves_absence") is False
    ):
        raise SequenceCheckpointError("normal T12 stage lost retain-all semantics")
    stage_id = stage.get("stage_id")
    if not isinstance(stage_id, str) or not stage_id:
        raise SequenceCheckpointError("normal T12 stage lacks its immutable ID")
    candidate_documents = stage.get("candidates")
    if not isinstance(candidate_documents, list) or not all(
        isinstance(candidate, dict) for candidate in candidate_documents
    ):
        raise SequenceCheckpointError("normal T12 stage lacks candidate provenance")
    stage_candidates = {
        str(candidate.get("seed_solution_id")): candidate
        for candidate in candidate_documents
    }
    if (
        len(stage_candidates) != len(candidate_documents)
        or stage.get("seed_count") != len(stage_candidates)
        or "None" in stage_candidates
    ):
        raise SequenceCheckpointError("normal T12 stage candidate identities differ")

    sequence_groups_path = _safe_relative_file(
        stage_root,
        "inputs/sequence_groups.jsonl",
        label="normal T12 sequence groups",
    )
    source_records_path = _safe_relative_file(
        stage_root,
        "inputs/source_records.jsonl",
        label="normal T12 source records",
    )
    preflight_path = _safe_relative_file(
        stage_root,
        "inputs/preflight.jsonl",
        label="normal T12 MTZ preflight",
    )
    sequence_groups, source_records, preflight = _load_scientific_context(
        stage=stage,
        sequence_groups_jsonl=sequence_groups_path,
        source_records_jsonl=source_records_path,
        preflight_jsonl=preflight_path,
    )
    if request.crystal_id is not None and request.crystal_id != preflight.crystal_id:
        raise SequenceCheckpointError("Phase III sequence checkpoint crystal differs")

    finalists = _safe_relative_file(
        stage_root, "finalists.tsv", label="normal T12 finalists"
    )
    finalists_digest = stage.get("finalists_sha256")
    if not isinstance(finalists_digest, str) or sha256_file(finalists) != (
        finalists_digest
    ):
        raise SequenceCheckpointError("normal T12 finalists checksum differs")
    if set(_finalist_seed_ids(finalists)) != set(stage_candidates):
        raise SequenceCheckpointError("normal T12 finalists and stage differ")

    retained_sources: dict[str, tuple[Path, str]] = {}
    for source in (sequence_groups_path, source_records_path, preflight_path):
        _register_source(
            retained_sources,
            Path("provenance") / source.name,
            source,
            sha256_file(source),
        )
    provenance_files = (
        ("t12_stage_manifest.json", "stage_manifest_sha256"),
        ("finalists.tsv", "finalists_sha256"),
        ("copy_count_report.tsv", "copy_report_tsv_sha256"),
        ("copy_count_report.md", "copy_report_markdown_sha256"),
    )
    for name, digest_key in provenance_files:
        source = _safe_relative_file(stage_root, name, label=f"normal T12 {name}")
        digest = (
            sha256_file(source)
            if digest_key == "stage_manifest_sha256"
            else stage.get(digest_key)
        )
        if not isinstance(digest, str) or sha256_file(source) != digest:
            raise SequenceCheckpointError(f"normal T12 {name} checksum differs")
        _register_source(retained_sources, Path("provenance") / name, source, digest)
    if request.crystal_id is not None:
        copy_assessments = _safe_relative_file(
            stage_root,
            "copy_count_assessments.jsonl",
            label="Phase III copy-count assessments",
        )
        copy_assessments_sha256 = stage.get("copy_count_assessments_sha256")
        if (
            not isinstance(copy_assessments_sha256, str)
            or sha256_file(copy_assessments) != copy_assessments_sha256
        ):
            raise SequenceCheckpointError(
                "Phase III copy-count assessment checksum differs"
            )
        _register_source(
            retained_sources,
            Path("provenance/copy_count_assessments.jsonl"),
            copy_assessments,
            copy_assessments_sha256,
        )

    refinements: list[BriefRefinementResult] = []
    sequences: list[SequenceMapResult] = []
    asset_sources: dict[str, dict[str, tuple[Path, str]]] = {}
    result_identity: dict[str, object] = {}
    seen_seeds: set[str] = set()
    shared_diffraction: tuple[str, str] | None = None
    phase3_diffraction_identity: tuple[str, str] | None = None
    for directory in request.candidate_result_directories:
        if directory.is_symlink() or not directory.is_dir():
            raise SequenceCheckpointError("normal T12 result directory is unsafe")
        refinement, refinement_json, refinement_jsonl = _read_single_result(
            directory,
            "brief_refinement_result",
            BriefRefinementResult,
            label="normal T12 refinement result",
        )
        sequence, sequence_json, sequence_jsonl = _read_single_result(
            directory,
            "sequence_map_result",
            SequenceMapResult,
            label="normal T12 sequence result",
        )
        seed = refinement.seed_solution_id
        expected_directory = (
            f"phase3_t12_{request.crystal_id}_{seed}"
            if request.crystal_id is not None
            else f"t12_{seed}"
        )
        if (
            seed in seen_seeds
            or directory.name != expected_directory
            or sequence.seed_solution_id != seed
            or refinement.refinement_id != sequence.refinement_id
        ):
            raise SequenceCheckpointError(
                "normal T12 result directory identities are inconsistent"
            )
        seen_seeds.add(seed)
        try:
            candidate = stage_candidates[seed]
        except KeyError as error:
            raise SequenceCheckpointError(
                "normal T12 result is absent from its stage"
            ) from error
        if not (
            candidate.get("sequence_group_id") == refinement.sequence_group_id
            and candidate.get("best_supported_copy_count")
            == refinement.input_copy_count
        ):
            raise SequenceCheckpointError(
                "normal T12 result and staged finalist provenance differ"
            )

        candidate_assets: dict[str, tuple[Path, str]] = {}
        result_assets = (
            (
                "brief_refine_001.pdb",
                refinement.refined_model_path,
                refinement.refined_model_sha256,
            ),
            (
                "brief_refine_001.mtz",
                refinement.refined_mtz_path,
                refinement.refined_mtz_sha256,
            ),
            (
                "brief_refine_2mFo-DFc.ccp4",
                refinement.map_path,
                refinement.map_sha256,
            ),
            (
                "brief_refine_mFo-DFc.ccp4",
                refinement.difference_map_path,
                refinement.difference_map_sha256,
            ),
            (
                "sequence_from_map.pdb",
                sequence.output_model_path,
                sequence.output_model_sha256,
            ),
        )
        for expected_name, relative, digest in result_assets:
            if relative is None and digest is None:
                continue
            if relative != expected_name or not isinstance(digest, str):
                raise SequenceCheckpointError(
                    "normal T12 result asset metadata is incomplete"
                )
            source = _safe_relative_file(
                directory,
                relative,
                label=f"normal T12 {expected_name}",
                digest=digest,
            )
            candidate_assets[expected_name] = (source, digest)
        asset_sources[seed] = candidate_assets

        evidence_paths = {
            "brief_refinement_result.json": refinement_json,
            "brief_refinement_result.jsonl": refinement_jsonl,
            "sequence_map_result.json": sequence_json,
            "sequence_map_result.jsonl": sequence_jsonl,
        }
        for pointer, label in (
            (refinement.command_pointer, "T12 command"),
            (refinement.raw_log_pointer, "refinement log"),
            (sequence.raw_log_pointer, "sequence log"),
        ):
            source = _safe_relative_file(directory, pointer, label=label)
            evidence_paths[pointer] = source
        if request.crystal_id is not None:
            command = _load_object(
                evidence_paths[refinement.command_pointer],
                "Phase III refinement command",
            )
            try:
                selection = DiffractionSelection.model_validate(
                    command.get("diffraction_selection")
                )
                free_r = FreeRIdentity.model_validate(command.get("free_r_identity"))
            except ValidationError as error:
                raise SequenceCheckpointError(
                    "Phase III refinement command lacks complete diffraction evidence"
                ) from error
            if not (
                command.get("schema_version") == "2.0"
                and command.get("refinement_id") == refinement.refinement_id
                and selection.crystal_id == request.crystal_id
                and selection.mtz_sha256 == preflight.mtz_sha256
                and selection.preflight_id == preflight.preflight_id
                and free_r.crystal_id == request.crystal_id
                and free_r.mtz_sha256 == preflight.mtz_sha256
                and free_r.diffraction_selection_id
                == selection.diffraction_selection_id
            ):
                raise SequenceCheckpointError(
                    "Phase III sequence checkpoint diffraction identities differ"
                )
            current_identity = (
                selection.diffraction_selection_id,
                free_r.free_r_identity_id,
            )
            if (
                phase3_diffraction_identity is not None
                and phase3_diffraction_identity != current_identity
            ):
                raise SequenceCheckpointError(
                    "Phase III sequence finalists use different diffraction identities"
                )
            phase3_diffraction_identity = current_identity
        evidence_identity: dict[str, str] = {}
        for name, source in sorted(evidence_paths.items()):
            digest = sha256_file(source)
            _register_source(
                retained_sources,
                Path("evidence") / seed / name,
                source,
                digest,
            )
            evidence_identity[name] = digest

        parent_relative = candidate.get("staged_parent_coordinate")
        parent_digest = candidate.get("source_coordinate_sha256")
        solution_relative = candidate.get("staged_solution_mtz")
        solution_digest = candidate.get("source_solution_mtz_sha256")
        diffraction_relative = candidate.get("refinement_mtz")
        diffraction_digest = candidate.get("refinement_mtz_sha256")
        if not all(
            isinstance(value, str)
            for value in (
                parent_relative,
                parent_digest,
                solution_relative,
                solution_digest,
                diffraction_relative,
                diffraction_digest,
            )
        ):
            raise SequenceCheckpointError("normal T12 staged assets are incomplete")
        parent = _safe_relative_file(
            stage_root,
            str(parent_relative),
            label="normal T12 staged parent",
            digest=str(parent_digest),
        )
        solution = _safe_relative_file(
            stage_root,
            str(solution_relative),
            label="normal T12 Phaser solution MTZ",
            digest=str(solution_digest),
        )
        diffraction = _safe_relative_file(
            stage_root,
            str(diffraction_relative),
            label="normal T12 diffraction MTZ",
            digest=str(diffraction_digest),
        )
        _register_source(
            retained_sources,
            Path("assets") / seed / "staged_parent.pdb",
            parent,
            str(parent_digest),
        )
        _register_source(
            retained_sources,
            Path("assets") / seed / "phaser_solution.mtz",
            solution,
            str(solution_digest),
        )
        current_diffraction = (str(diffraction_relative), str(diffraction_digest))
        if shared_diffraction is not None and shared_diffraction != current_diffraction:
            raise SequenceCheckpointError(
                "normal T12 candidates use different diffraction inputs"
            )
        shared_diffraction = current_diffraction
        _register_source(
            retained_sources,
            Path("assets/shared/diffraction.mtz"),
            diffraction,
            str(diffraction_digest),
        )
        result_identity[seed] = {
            "refinement_id": refinement.refinement_id,
            "refinement_execution_status": refinement.execution_status.value,
            "sequence_execution_status": sequence.execution_status.value,
            "evidence": evidence_identity,
        }
        refinements.append(refinement)
        sequences.append(sequence)

    if seen_seeds != set(stage_candidates):
        raise SequenceCheckpointError(
            "normal T12 stage and candidate-result identities differ"
        )
    identity: dict[str, object] = {
        "adapter_version": _LIVE_ADAPTER_VERSION,
        "execution_mode": "normal_workflow",
        "run_id": stage_id,
        "stage_manifest_sha256": sha256_file(stage_manifest),
        "candidate_results": result_identity,
    }
    extra_manifest: dict[str, object] = {
        "execution_mode": "normal_workflow",
        "stage_id": stage_id,
        "all_finalists_retained": True,
        "typed_failures_are_evidence": True,
    }
    if request.crystal_id is not None:
        if phase3_diffraction_identity is None:
            raise SequenceCheckpointError(
                "Phase III sequence checkpoint has no finalists"
            )
        identity.update(
            {
                "execution_mode": "phase3_reviewed_single_component",
                "crystal_id": request.crystal_id,
                "diffraction_selection_id": phase3_diffraction_identity[0],
                "free_r_identity_id": phase3_diffraction_identity[1],
            }
        )
        extra_manifest.update(
            {
                "execution_mode": "phase3_reviewed_single_component",
                "diffraction_selection_id": phase3_diffraction_identity[0],
                "free_r_identity_id": phase3_diffraction_identity[1],
            }
        )
    return _publish_sequence_checkpoint(
        run_id=stage_id,
        refinements=tuple(refinements),
        sequences=tuple(sequences),
        stage=stage,
        identity_base=identity,
        asset_sources=asset_sources,
        retained_sources=retained_sources,
        sequence_groups=sequence_groups,
        source_records=source_records,
        preflight=preflight,
        output=request.output_directory,
        adapter_version=_LIVE_ADAPTER_VERSION,
        progress=request.progress,
        require_all_completed=False,
        extra_manifest=extra_manifest,
    )
